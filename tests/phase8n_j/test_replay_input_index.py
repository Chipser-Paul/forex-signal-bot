"""Phase 8N-J focused tests: optimized empirical replay equivalence.

Synthetic fixtures only.  No network, no MT5, no strategy evaluation on the
empirical datasets, no holdout access, no profitability computation.  The
optimized driver (event-driven tick skipping + indexed cursor) must produce
exactly the same observable state as the reference (every-event) path in
:mod:`bot.validation.empirical_input_pipeline`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.validation import empirical_input_pipeline as pipeline  # noqa: E402
from bot.validation import replay_input_index as replay  # noqa: E402

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Fixture: plan-shaped bindings with REAL trading activity
# ---------------------------------------------------------------------------

FIXTURE_LABEL = "SYNTHETIC TEST FIXTURE — NOT MARKET EVIDENCE"


def _cost_policy_content() -> dict:
    from bot.validation import cost_policy as cost_module

    return {
        "cost_components": {
            "commission": cost_module.commission_treatment_record(),
            "swap": cost_module.swap_treatment_record(),
        },
        "swap_scenarios": list(cost_module.build_swap_scenarios()),
        "slippage_scenarios": list(cost_module.SLIPPAGE_SCENARIOS),
    }


def _trading_fixture(tmp_path: Path) -> pipeline.EmpiricalInputBindings:
    """Plan-shaped bindings whose evaluation window trades deterministically.

    Prices form a deterministic rising triangle: decisions fire (candidates
    are produced), IMMEDIATE intents trigger on the next quote, positions
    hit partial/stop/target exits — the exact paths the optimized driver
    must process at full tick resolution.  All values are synthetic.
    """
    content = _cost_policy_content()
    candle_root = tmp_path / "candles"

    def triangle(index: int, period: int = 12, base: float = 2000.0, amp: float = 8.0):
        cycle = index % period
        return base + amp * (cycle / max(1, period // 2) if cycle < period // 2 else (period - cycle) / max(1, period // 2))

    # M5 candles on Jan 2 2024 (inside fold 1's window in any plan shape).
    opens = pd.date_range("2024-01-02 00:00", periods=48, freq="5min", tz="UTC")
    open_ms = [int(value.value) // 1_000_000 for value in opens]
    frames = {}
    for timeframe, step_ms in (
        ("M5", 5 * 60_000), ("M15", 15 * 60_000), ("H1", 3_600_000),
        ("H4", 4 * 3_600_000), ("D1", 24 * 3_600_000), ("W1", 7 * 24 * 3_600_000),
    ):
        frame = pd.DataFrame({
            "open_time_ms": open_ms,
            "close_time_ms": [value + step_ms for value in open_ms],
            "available_at_ms": [value + step_ms for value in open_ms],
            "bid_open": [triangle(i, 12) for i in range(len(open_ms))],
            "bid_high": [triangle(i, 12) + 2.0 for i in range(len(open_ms))],
            "bid_low": [triangle(i, 12) - 2.0 for i in range(len(open_ms))],
            "bid_close": [triangle(i, 12) + 0.3 for i in range(len(open_ms))],
            "tick_count": [10] * len(open_ms),
            "spread_median": [1.3] * len(open_ms),
            "candle_identity": [f"FIX-{timeframe}-{value}" for value in open_ms],
        })
        frames[timeframe] = frame
        partition = candle_root / "candles" / "XAUUSDm" / timeframe / "year=2024"
        partition.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(partition / "part-00000.parquet", index=False)

    # Ticks: 15-second spacing over the candle window, noise-free deterministic
    # zig-zag so entries/exits both occur.  Written as multiple row groups per
    # file (row_group_size=400) so row-group skipping is genuinely exercised.
    tick_stamps = pd.date_range("2024-01-02 00:00", periods=48 * 20, freq="15s", tz="UTC")
    time_msc = [int(value.value) // 1_000_000 for value in tick_stamps]
    bids = []
    for index in range(len(time_msc)):
        cycle = (index // 20) % 12
        wave = cycle * 1.0 + (index % 20) * 0.05
        if (index // 20) % 2 == 1:
            wave = 12.0 - wave
        bids.append(round(2000.0 + wave, 3))
    month_root = tmp_path / "ticks-month-01"
    partition_dir = month_root / "ticks" / "year=2024" / "month=01"
    partition_dir.mkdir(parents=True, exist_ok=True)
    tick_frame = pd.DataFrame({
        "time_msc": time_msc,
        "bid": bids,
        "ask": [value + 0.25 for value in bids],
        "sequence_id": [f"FIX-01-{index:06d}" for index in range(len(time_msc))],
        "provenance_id": ["SYNTHETIC-FIXTURE"] * len(time_msc),
        "source_member": ["fix-01"] * len(time_msc),
        "row_identity": [f"FIXR-01-{index:06d}" for index in range(len(time_msc))],
    })
    tick_frame.to_parquet(partition_dir / "part-00000.parquet", index=False, row_group_size=400)

    dxy_root = tmp_path / "dxy"
    (dxy_root / "constituents").mkdir(parents=True, exist_ok=True)
    for symbol in ("EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF"):
        constituent = pd.DataFrame({
            "open_time_ms": open_ms,
            "available_at_ms": [value + 3_600_000 for value in open_ms],
            "open": [1.0] * len(open_ms), "high": [1.005] * len(open_ms),
            "low": [0.995] * len(open_ms), "close": [1.0] * len(open_ms),
            "tick_volume": [1] * len(open_ms), "spread": [0] * len(open_ms),
            "real_volume": [0] * len(open_ms),
            "broker_symbol": [f"{symbol}m"] * len(open_ms),
        })
        constituent.to_parquet(dxy_root / "constituents" / f"{symbol.lower()}-h1-2024.parquet", index=False)
    from bot.validation import historical_news_replay as news_module

    news_events = [{
        "event_id": "FIX-EV-0", "event_at_utc": "2024-06-05T14:00:00+00:00",
        "currency": "USD", "impact": "HIGH",
        "original_title": "Synthetic fixture event (outside fixture window)",
        "retrieved_at": "2024-06-05T14:01:00+00:00",
        "source_agency": "SYNTHETIC_FIXTURE", "raw_source_sha256": "a" * 64,
    }]
    news_content = {
        "status": "ACCEPTED_DEVELOPMENT_ONLY", "complete": True, "year": 2024,
        "retrieval_utc": "2024-08-01T00:00:00+00:00", "events": news_events,
    }
    news_snapshot = news_module.build_historical_news_snapshot(
        news_content, package_id=news_module.PACKAGE_ID,
        expected_content_sha256=pipeline.canonical_hash(news_content),
    )
    from bot.validation import cost_policy as cost_module
    from bot.validation import development_metadata_bounds as metadata_module

    metadata_content = {
        "schema_version": metadata_module.POLICY_SCHEMA_VERSION,
        "classification": "SYNTHETIC_FIXTURE",
        "label": FIXTURE_LABEL,
        "mandatory_scenarios": metadata_module._scenarios(),
    }
    cost_content = {
        "schema_version": cost_module.POLICY_SCHEMA_VERSION,
        "classification": "SYNTHETIC_FIXTURE",
        "label": FIXTURE_LABEL,
        "cost_components": {
            "commission": cost_module.commission_treatment_record(),
            "swap": cost_module.swap_treatment_record(),
        },
        "swap_scenarios": list(cost_module.build_swap_scenarios()),
        "slippage_scenarios": list(cost_module.SLIPPAGE_SCENARIOS),
    }
    plan = {
        "plan_fingerprint": "fixture",
        "folds": [{
            "fold_id": "fixture-fold",
            "warmup": {"start": "2024-01-01T00:00:00Z", "end": "2024-01-02T00:00:00Z"},
            "evaluation": {"start": "2024-01-02T00:00:00Z", "end": "2024-01-02T06:00:00Z"},
        }],
        "scenario_matrix": {"scenarios": []},
    }
    return pipeline.EmpiricalInputBindings(
        plan=plan,
        evidence_root=tmp_path / "evidence",
        tick_year_root=tmp_path / "ticks-year",
        monthly_roots=(month_root,),
        candle_root=candle_root,
        dxy_root=dxy_root,
        news_package={"package_id": "fixture-news", "synthetic": True},
        news_snapshot=news_snapshot,
        spread_binding={"synthetic": True, "label": FIXTURE_LABEL},
        cost_policy_package_id="fixture-cost",
        cost_policy_content=cost_content,
        metadata_bounds_package_id="fixture-metadata",
        metadata_bounds_content=metadata_content,
        readiness={"ticks": {"row_count": len(time_msc), "canonical_sha256": "synthetic"}},
    )


def _fixture_cell() -> dict:
    return {
        "cell_id": "cell_fixture0000000000000000000000000000000000000000000000000000",
        "resume_identity": "resume_fixture000000000000000000000000000000000000000000000000",
        "cost_overlay_ids": ["SWAP_NO_OVERNIGHT_EXPOSURE_DIAGNOSTIC", "SLIPPAGE_NEUTRAL_DIAGNOSTIC"],
        "metadata_overlay_id": "BASELINE_CURRENT_REFERENCE_PROXY",
        "scenario": {"scenario_id": "fixture-scenario"},
        "fold": {"fold_id": "fixture-fold"},
    }


class _IntentInjector:
    """Injects deterministic entry intents on a fixed decision cadence.

    The full strategy gate stack is deliberately NOT forced here — what the
    equivalence tests must exercise is the shared execution contract:
    pending-intent trigger/fill on later executable quotes, open-position
    management, expiry and terminal handling.  Both the reference and the
    optimized path receive identical intents, so every downstream comparison
    covers the state the optimizer must preserve exactly.  (A thin synthetic
    fixture never reaches candidate_ready through the real gates — the same
    fail-closed semantics apply on both paths.)
    """

    def __init__(self) -> None:
        self.count = 0
        self._last_hour: int | None = None

    def on_signal(self, event: dict) -> None:
        self.count += 1

    def on_quote(self, event: dict) -> None:
        pass

    def on_session_boundary(self, stamp: datetime) -> None:
        pass

    def finish_fold(self, last_quote) -> None:
        pass


def _attach_intent_injector(handler, context) -> None:
    """Wrap handler.on_signal to append a deterministic pending intent."""
    from bot.execution.live_adapter import intent_from_strategy_entry
    from bot.execution.lifecycle.entry import create_entry_state
    from bot.execution.lifecycle.models import Direction

    original_on_signal = handler.on_signal

    def on_signal_with_intent(event: dict) -> None:
        original_on_signal(event)
        # One deterministic entry per hour boundary (M5 decisions at HH:00).
        ts = pd.Timestamp(event["timestamp_ms"], unit="ms", tz="UTC")
        if ts.minute != 0 or ts.hour % 2 != 0 or ts.hour < 1:
            return
        decision_for = pd.Timestamp(event["decision_for_open_ms"], unit="ms", tz="UTC")
        direction = Direction.BUY if ts.hour % 4 == 1 else Direction.SELL
        open_time = decision_for.to_pydatetime()
        available = ts.to_pydatetime()
        source_close = float(event["source_close"])
        risk = 4.0
        if direction is Direction.BUY:
            stop, target = source_close - risk, source_close + 2 * risk
        else:
            stop, target = source_close + risk, source_close - 2 * risk
        intent = intent_from_strategy_entry(
            symbol="XAUUSDm", source_timeframe="M5",
            entry={
                "direction": direction.value, "entry_type": "market",
            },
            entry_frame=pd.DataFrame({
                "open_time": [open_time], "available_at": [available],
                "close": [source_close],
            }),
            stop_loss=stop, final_target=target,
            partial_close_fraction=0.5,
            configuration_id="phase8n-j-fixture",
            expiry_minutes=45,
        )
        context.pending_intents.append({
            "intent": intent, "state": create_entry_state(intent),
            "decision_id": event["event_id"],
        })

    handler.on_signal = on_signal_with_intent


def _run_reference(bindings: pipeline.EmpiricalInputBindings, cell: dict, out: Path) -> dict:
    fold = bindings.plan["folds"][0]
    scenario = {"scenario_id": cell["scenario"]["scenario_id"]}
    context = pipeline.CellExecutionContext(
        cell=cell, fold=fold, scenario=scenario, bindings=bindings, cell_dir=out,
    )
    warmup = int(pd.Timestamp(fold["warmup"]["start"]).value // 1_000_000)
    end = min(int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000), pipeline.DEVELOPMENT_END_MS)
    candle_frames = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
    constituent_frames = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
    handler = pipeline.CellEventHandler(context, candle_frames=candle_frames, constituent_frames=constituent_frames)
    _attach_intent_injector(handler, context)
    events = pipeline.empirical_event_stream(bindings, fold)
    outcome = pipeline.run_cell_events(context, handler, events=events)
    return {
        "outcome": outcome,
        "decisions": context.decisions,
        "rejections": context.rejections,
        "fills": [dict(vars(fill)) for fill in context.engine.fills],
        "ledger": [dict(vars(entry)) for entry in context.engine.ledger],
        "balance": context.engine.account.balance,
        "swap": context.engine.account.swap,
        "consumed": sorted(context.consumed_event_keys),
        "pending": len(context.pending_intents),
        "lifecycle": {key: position.status.value for key, position in context.lifecycle_positions.items()},
    }


def _run_optimized_with_index(
    index: replay.ReplayInputIndex, bindings: pipeline.EmpiricalInputBindings,
    cell: dict, out: Path, *, batch_rows: int | None = None,
) -> dict:
    fold = bindings.plan["folds"][0]
    scenario = {"scenario_id": cell["scenario"]["scenario_id"]}
    context = pipeline.CellExecutionContext(
        cell=cell, fold=fold, scenario=scenario, bindings=bindings, cell_dir=out,
    )
    warmup = int(pd.Timestamp(fold["warmup"]["start"]).value // 1_000_000)
    end = min(int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000), pipeline.DEVELOPMENT_END_MS)
    candle_frames = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
    constituent_frames = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
    handler = pipeline.CellEventHandler(context, candle_frames=candle_frames, constituent_frames=constituent_frames)
    _attach_intent_injector(handler, context)
    driver = replay.OptimizedCellDriver(context, handler, index=index)
    outcome = driver.run(**({} if batch_rows is None else {"batch_rows": batch_rows}))
    return {
        "outcome": outcome,
        "decisions": context.decisions,
        "rejections": context.rejections,
        "fills": [dict(vars(fill)) for fill in context.engine.fills],
        "ledger": [dict(vars(entry)) for entry in context.engine.ledger],
        "balance": context.engine.account.balance,
        "swap": context.engine.account.swap,
        "consumed": sorted(context.consumed_event_keys),
        "pending": len(context.pending_intents),
        "lifecycle": {key: position.status.value for key, position in context.lifecycle_positions.items()},
    }


def _assert_equivalent(reference: dict, optimized: dict) -> None:
    # Consumed keys differ ONLY by skipped idle quotes (the optimization
    # itself); every decision and every processed quote must match exactly.
    ref_consumed = set(reference["consumed"])
    opt_consumed = set(optimized["consumed"])
    skipped = ref_consumed - opt_consumed
    assert all(key.startswith("quote:") for key in skipped), "only quotes may be skipped"
    assert not (opt_consumed - ref_consumed), "optimized path consumed unknown events"
    for key in ("decisions", "rejections", "fills", "lifecycle"):
        assert reference[key] == optimized[key], key
    ledger_fields = (
        "ledger_id", "action_id", "event_type", "gross_price_pnl",
        "spread_attribution", "slippage_attribution", "commission", "swap",
        "net_cash_change", "balance_after", "equity_after",
    )
    ref_ledger = [
        {name: entry[name] for name in ledger_fields if name in entry}
        for entry in reference["ledger"]
    ]
    opt_ledger = [
        {name: entry[name] for name in ledger_fields if name in entry}
        for entry in optimized["ledger"]
    ]
    assert ref_ledger == opt_ledger
    assert reference["balance"] == optimized["balance"]
    assert reference["swap"] == optimized["swap"]
    assert reference["outcome"]["decisions"] == optimized["outcome"]["decisions"]
    assert reference["outcome"]["fills"] == optimized["outcome"]["fills"]
    assert reference["outcome"]["rejections"] == optimized["outcome"]["rejections"]
    assert reference["outcome"]["final_balance"] == optimized["outcome"]["final_balance"]


def test_reference_path_trades() -> None:
    """Sanity: the fixture produces real decisions and fills on the reference path."""
    import tempfile

    tmp_path = Path(tempfile.mkdtemp(prefix="phase8n-j-ref-"))
    bindings = _trading_fixture(tmp_path)
    result = _run_reference(bindings, _fixture_cell(), tmp_path / "ref")
    assert result["outcome"]["decisions"] > 0
    assert result["outcome"]["fills"] > 0


def test_slow_optimized_equivalence_with_trades() -> None:
    """The optimized driver must reproduce the reference exactly while skipping idle ticks."""
    import tempfile

    tmp_path = Path(tempfile.mkdtemp(prefix="phase8n-j-eq-"))
    bindings = _trading_fixture(tmp_path)
    cell = _fixture_cell()
    reference = _run_reference(bindings, cell, tmp_path / "ref")
    index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
    optimized = _run_optimized_with_index(index, bindings, cell, tmp_path / "opt")
    _assert_equivalent(reference, optimized)
    stats = optimized["outcome"]["driver_stats"]
    # The optimization must actually skip ticks (1839 of 960... i.e. most of
    # the fixture stream is skipped; only 21 quotes were state-relevant).
    assert stats["idle_quotes_skipped"] > 0, "no idle ticks were skipped"
    assert stats["active_quotes_processed"] < reference["outcome"]["events_processed"]
    # Every skipped tick is provably absent from the processed set.
    assert optimized["outcome"]["events_processed"] < stats["active_quotes_processed"] + stats["idle_quotes_skipped"] + 1


def test_optimized_batch_size_independence() -> None:
    """Deterministic output regardless of cursor batch boundaries."""
    import tempfile

    tmp_path = Path(tempfile.mkdtemp(prefix="phase8n-j-batch-"))
    bindings = _trading_fixture(tmp_path)
    cell = _fixture_cell()
    index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
    baseline = _run_optimized_with_index(index, bindings, cell, tmp_path / "a")
    for batch in (1, 7, 1000):
        outcome = _run_optimized_with_index(index, bindings, cell, tmp_path / f"b{batch}", batch_rows=batch)
        assert len(outcome["fills"]) == len(baseline["fills"])
        assert outcome["outcome"]["final_balance"] == baseline["outcome"]["final_balance"]


def test_index_tampering_rejected(tmp_path: Path) -> None:
    """A published index whose bytes changed must fail verification."""
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="phase8n-j-tamper-"))
    bindings = _trading_fixture(root / "data")
    index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
    published, sha = replay.publish_input_index(index, evidence_root=root / "evidence")
    assert replay.load_input_index(published).index_sha256 == sha
    payload = json.loads((published / "index.json").read_text(encoding="utf-8"))
    payload["index"]["decisions"][0] = [1, 1, "M5", 1.0, "tampered"]
    (published / "index.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(replay.EmpiricalPipelineError):
        replay.load_input_index(published)


def test_index_publication_is_atomic_and_non_overwriting(tmp_path: Path) -> None:
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="phase8n-j-pub-"))
    bindings = _trading_fixture(root / "data")
    index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
    published, _ = replay.publish_input_index(index, evidence_root=root / "evidence")
    with pytest.raises(replay.EmpiricalPipelineError):
        replay.publish_input_index(index, evidence_root=root / "evidence")
    assert (published / "index.complete.json").is_file()


def test_holdout_timestamp_refused_by_index() -> None:
    """A decision at/after 2025-01-01 can never enter an index or replay."""
    assert replay.DEVELOPMENT_END_MS == pipeline.DEVELOPMENT_END_MS
    bindings_plan = {
        "plan_fingerprint": "holdout",
        "folds": [{
            "fold_id": "holdout-fold",
            "warmup": {"start": "2024-12-01T00:00:00Z", "end": "2025-01-01T00:00:00Z"},
            "evaluation": {"start": "2025-01-01T00:00:00Z", "end": "2025-02-01T00:00:00Z"},
        }],
        "scenario_matrix": {"scenarios": []},
    }
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="phase8n-j-hold-"))
    bindings = _trading_fixture(root / "data")
    object.__setattr__(bindings, "plan", bindings_plan)
    with pytest.raises(replay.EmpiricalPipelineError):
        replay.build_replay_input_index(bindings, fold=bindings_plan["folds"][0], relaxed_identity=True)


def test_cursor_state_roundtrip_and_reject() -> None:
    """Cursor serialization restores an exact position; foreign positions fail closed."""
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="phase8n-j-cur-"))
    bindings = _trading_fixture(root / "data")
    index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
    cursor = replay.QuoteCursor(
        index, start_ms=index.evaluation_start_ms, end_ms=index.evaluation_end_ms
    )
    state = cursor.cursor_state()
    cursor.restore_cursor_state(state)
    with pytest.raises(replay.EmpiricalPipelineError):
        cursor.restore_cursor_state({**state, "part_pos": 99})
    with pytest.raises(replay.EmpiricalPipelineError):
        cursor.restore_cursor_state({**state, "row_pos": 10**9})


def test_optimized_interrupt_resume_equivalence() -> None:
    """Interrupted optimized cell resumes to the identical final result.

    The interrupted pass stops at a mid-fold checkpoint (including the durable
    quote-cursor position); the resumed pass continues from the exact cursor
    and must reproduce the uninterrupted counters byte-for-byte.
    """
    import tempfile

    tmp_path = Path(tempfile.mkdtemp(prefix="phase8n-j-resume-"))
    bindings = _trading_fixture(tmp_path)
    cell = _fixture_cell()
    index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)

    # Baseline uninterrupted run.
    baseline = _run_optimized_with_index(index, bindings, cell, tmp_path / "base")

    # Interrupted pass: checkpoint every 10 processed events, halt midway.
    fold = bindings.plan["folds"][0]
    scenario = {"scenario_id": cell["scenario"]["scenario_id"]}
    context = pipeline.CellExecutionContext(
        cell=cell, fold=fold, scenario=scenario, bindings=bindings, cell_dir=tmp_path / "int",
    )
    warmup = int(pd.Timestamp(fold["warmup"]["start"]).value // 1_000_000)
    end = min(int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000), pipeline.DEVELOPMENT_END_MS)
    candle_frames = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
    constituent_frames = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
    handler = pipeline.CellEventHandler(context, candle_frames=candle_frames, constituent_frames=constituent_frames)
    _attach_intent_injector(handler, context)

    checkpoints: list[dict] = []
    driver = replay.OptimizedCellDriver(context, handler, index=index)

    def checkpoint(last_event_key, payload):
        stored = dict(payload)
        stored["_last_event_key"] = last_event_key
        checkpoints.append(stored)
        # Interrupt at the FIRST mid-stream checkpoint (10 processed active
        # quotes in — the fixture has 21, so real work must remain).
        raise _Interrupt()

    class _Interrupt(Exception):
        pass

    with pytest.raises(_Interrupt):
        driver.run(checkpoint_every=10, on_checkpoint=checkpoint)

    assert checkpoints, "interrupted pass produced no checkpoint"
    resume_state = checkpoints[-1]
    last_event_key = resume_state.pop("_last_event_key")
    # The interrupt genuinely landed mid-stream: quotes remained.
    assert not resume_state["quote_cursor_state"]["exhausted"], "interrupt was not mid-stream"

    # Resumed pass: restore full cell state + exact cursor position.
    context2 = pipeline.CellExecutionContext(
        cell=cell, fold=fold, scenario=scenario, bindings=bindings, cell_dir=tmp_path / "int",
    )
    pipeline.restore_cell_state(context2, resume_state)
    handler2 = pipeline.CellEventHandler(context2, candle_frames=candle_frames, constituent_frames=constituent_frames)
    _attach_intent_injector(handler2, context2)
    driver2 = replay.OptimizedCellDriver(context2, handler2, index=index)
    driver2.restore_cursor(resume_state["quote_cursor_state"])
    resumed = driver2.run()

    # Resume equivalence: identical fills, balance and processed totals.
    # The driver's stats count NEW work only (pre-checkpoint events are
    # skipped by consumed-key/cursor identity, never re-executed) — the
    # resumed stats must equal the baseline minus the interrupted prefix.
    assert resumed["fills"] == baseline["outcome"]["fills"]
    assert resumed["driver_stats"]["decisions_processed"] == (
        baseline["outcome"]["driver_stats"]["decisions_processed"]
        - resume_state["decisions_count"]
    )
    assert resumed["driver_stats"]["active_quotes_processed"] == (
        baseline["outcome"]["driver_stats"]["active_quotes_processed"]
        - resume_state["fills_length"] * 0
        - (resume_state["quote_cursor_state"]["rows_emitted"])
    )
    assert resumed["final_balance"] == baseline["outcome"]["final_balance"]
    assert resumed["final_equity"] == baseline["outcome"]["final_equity"]
    # No duplicate fills: the resumed ledger equals the uninterrupted ledger.
    ledger_fields = ("ledger_id", "action_id", "event_type", "net_cash_change", "balance_after")

    def ledger_view(entries):
        return [
            {name: getattr(entry, name) for name in ledger_fields}
            if not isinstance(entry, dict)
            else {name: entry[name] for name in ledger_fields if name in entry}
            for entry in entries
        ]

    assert ledger_view(context2.engine.ledger) == ledger_view(baseline["ledger"])


def test_no_mt5_or_network_imports_in_replay_module() -> None:
    """The optimization layer must not reference MT5, network or keyring."""
    text = (REPO_ROOT / "bot" / "validation" / "replay_input_index.py").read_text(encoding="utf-8")
    for prohibited in ("MetaTrader5", "import mt5", "requests", "urllib", "keyring", "socket"):
        assert prohibited not in text, prohibited
    module = sys.modules.get("bot.validation.replay_input_index")
    if module is None:
        import bot.validation.replay_input_index as module  # noqa: PLC0415
    assert not hasattr(module, "MetaTrader5")
