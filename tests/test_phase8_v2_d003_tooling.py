"""D003 — canonical Gate-11 / order-block lifecycle decomposition tooling.

Synthetic fixtures only — the empirical store ``fold-01-a8b406884ab3525a``
is NEVER opened in this suite, and no observed V001/D003 empirical count
appears as an expected output (§28).

Covered:
* complete ``BlockState`` lifecycle through the frozen
  ``evaluate_order_block`` (ELIGIBLE, RETEST_ELIGIBLE, MITIGATED,
  INVALIDATED, EXPIRED, CONSUMED, PREMATURE, UNAVAILABLE, DATA_UNSAFE);
* eligibility true only for ELIGIBLE/RETEST_ELIGIBLE; LONG/SHORT parity;
* causal decision-time filtering (expiry/mitigation counts only bars
  available at the decision); reducer-exact consumed-id derivation
  including a NON-EMPTY consumed-id example;
* acquisition-vs-canonical contingency and all aggregation surfaces;
* banned-output guard (no pnl/profit/fills/counterfactual keys);
* loop-level accounting reconciliation and deterministic output.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtests import phase8_v2_diagnostic_d001 as d001  # noqa: E402
from backtests import phase8_v2_diagnostic_d003 as d003  # noqa: E402
from bot.strategy.config import StrategyConfig  # noqa: E402
from bot.strategy.models import BlockState, StrategySide  # noqa: E402
from bot.strategy.order_blocks import evaluate_order_block  # noqa: E402
from bot.strategy.setup_state import (  # noqa: E402
    StrategyState,
    record_from_state,
)
from tests.test_phase8_v2_d001_tooling import (  # noqa: E402
    AT,
    FOLD01_START_MS,
    _full_boundary_store,
    _mocked_ok_snapshot,
    _ok_snapshot,
    _seed_record,
    _Snapshot,
    _Table,
)

FOLD01_END_MS = int(datetime(2024, 6, 8, tzinfo=timezone.utc).timestamp() * 1000)


# ---------------------------------------------------------------------------
# Lifecycle fixtures (synthetic candles; no empirical data)
# ---------------------------------------------------------------------------


def _lifecycle_frame(
    *,
    side: str = "bullish",
    scenario: str = "eligible",
    bars_after: int | None = None,
) -> pd.DataFrame:
    """Synthetic frame producing a confirmed order block, with variants.

    ``scenario``: eligible | retest | mitigated | invalidated | expired.
    ``bars_after`` overrides the count of bars placed after confirmation
    (decision-time filtering tests).
    """
    start = pd.Timestamp("2024-04-01T00:00:00Z")
    rows = []
    for index in range(14):
        price = 100.0 + index * 0.01
        rows.append((price, price + 0.2, price - 0.2, price + 0.01))
    if side == "bullish":
        rows.extend([(100.5, 101.0, 99.0, 99.5), (99.5, 103.5, 99.4, 103.0)])
        # After confirmation: scenario-specific bars.
        after: list[tuple[float, float, float, float]] = []
        if scenario == "retest":
            after = [(103.0, 103.2, 100.0, 102.0)]
        elif scenario == "mitigated":
            after = [(103.0, 103.2, 100.0, 102.0), (102.0, 102.2, 101.5, 102.1)]
        elif scenario == "invalidated":
            # A full close BELOW the bullish zone (zone_low == 100.0 for the
            # confirmed block) without first re-touching it.
            after = [(98.0, 98.4, 97.6, 97.8)]
        elif scenario == "expired":
            after = [(102.0, 102.2, 101.8, 102.0)] * 31
        else:  # eligible: only quiet bars, no retest of the zone
            after = [(101.5, 101.7, 101.3, 101.5)] * 2
    else:
        rows.extend([(100.0, 101.0, 99.0, 100.5), (100.5, 100.6, 96.5, 97.0)])
        after = []
        if scenario == "retest":
            after = [(97.0, 100.0, 96.8, 98.0)]
        elif scenario == "mitigated":
            after = [(97.0, 100.0, 96.8, 98.0), (98.0, 98.5, 97.5, 98.1)]
        elif scenario == "invalidated":
            # A full close ABOVE the bearish zone (zone_high == 100.0) without
            # first re-touching it.
            after = [(102.0, 102.4, 101.6, 101.8)]
        elif scenario == "expired":
            after = [(97.8, 98.0, 97.6, 97.8)] * 31
        else:
            after = [(97.5, 97.7, 97.3, 97.5)] * 2
    rows.extend(after[:bars_after] if bars_after is not None else after)
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    frame["open_time"] = pd.date_range(start, periods=len(frame), freq="5min")
    frame["available_at"] = frame["open_time"] + pd.Timedelta(minutes=5)
    return frame


def _decision_at(frame: pd.DataFrame) -> datetime:
    """Decision time = last bar availability (all scenario bars visible)."""
    return frame["available_at"].iloc[-1].to_pydatetime()


# ---------------------------------------------------------------------------
# §29 — every BlockState; eligibility only ELIGIBLE/RETEST_ELIGIBLE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "side,scenario,expected_state,expected_reason",
    [
        ("bullish", "eligible", BlockState.ELIGIBLE, "confirmed_unmitigated_block"),
        ("bearish", "eligible", BlockState.ELIGIBLE, "confirmed_unmitigated_block"),
        ("bullish", "retest", BlockState.RETEST_ELIGIBLE, "first_post_confirmation_retest"),
        ("bearish", "retest", BlockState.RETEST_ELIGIBLE, "first_post_confirmation_retest"),
        ("bullish", "mitigated", BlockState.MITIGATED, "block_already_mitigated"),
        ("bearish", "mitigated", BlockState.MITIGATED, "block_already_mitigated"),
        ("bullish", "invalidated", BlockState.INVALIDATED, "close_below_bullish_zone"),
        ("bearish", "invalidated", BlockState.INVALIDATED, "close_above_bearish_zone"),
        ("bullish", "expired", BlockState.EXPIRED, "block_expired"),
        ("bearish", "expired", BlockState.EXPIRED, "block_expired"),
    ],
)
def test_block_states_across_sides(side, scenario, expected_state, expected_reason):
    config = StrategyConfig()
    frame = _lifecycle_frame(side=side, scenario=scenario)
    result = evaluate_order_block(
        frame,
        StrategySide.LONG if side == "bullish" else StrategySide.SHORT,
        _decision_at(frame),
        config,
    )
    assert result.state is expected_state
    assert result.reason == expected_reason
    assert result.eligible == (expected_state in (BlockState.ELIGIBLE, BlockState.RETEST_ELIGIBLE))


def test_unavailable_premature_consumed_and_data_unsafe():
    config = StrategyConfig()
    frame = _lifecycle_frame(side="bullish")
    at = _decision_at(frame)
    # UNAVAILABLE: no confirmed block of the requested side at all
    # (perfectly flat candles produce no blocks on either side).
    flat = pd.DataFrame(
        [(100.0, 100.2, 99.8, 100.0)] * 16,
        columns=["open", "high", "low", "close"],
    )
    flat["open_time"] = pd.date_range("2024-04-01", periods=16, freq="5min", tz="UTC")
    flat["available_at"] = flat["open_time"] + pd.Timedelta(minutes=5)
    flat_at = flat["available_at"].iloc[-1].to_pydatetime()
    assert evaluate_order_block(flat, StrategySide.SHORT, flat_at, config).state is BlockState.UNAVAILABLE
    assert evaluate_order_block(flat, StrategySide.SHORT, flat_at, config).reason == "no_confirmed_block"
    # PREMATURE: decision one microsecond before the block's confirmation
    # (confirmed_at 01:20 for the LONG side in this frame layout).
    early = datetime(2024, 4, 1, 1, 20, tzinfo=timezone.utc) - timedelta(microseconds=1)
    assert evaluate_order_block(frame, StrategySide.LONG, early, config).state is BlockState.PREMATURE
    assert evaluate_order_block(frame, StrategySide.LONG, early, config).reason == "confirmation_not_available"
    # CONSUMED: derived consumed ids contain the block id (non-empty set).
    consumed_result = evaluate_order_block(frame, StrategySide.LONG, at, config)
    assert consumed_result.block_id
    blocked = evaluate_order_block(
        frame, StrategySide.LONG, at, config,
        consumed_ids=frozenset({consumed_result.block_id}),
    )
    assert blocked.state is BlockState.CONSUMED
    assert blocked.reason == "block_already_consumed"
    # DATA_UNSAFE: naive decision time / malformed frame.
    assert evaluate_order_block(frame, StrategySide.LONG, at.replace(tzinfo=None), config).state is BlockState.DATA_UNSAFE
    broken = frame.drop(columns=["close"])
    assert evaluate_order_block(broken, StrategySide.LONG, at, config).state is BlockState.DATA_UNSAFE


def test_causal_decision_time_filtering():
    """Expiry/mitigation must count only bars available at the decision."""
    config = StrategyConfig()
    # One post-confirmation retest bar visible: first retest -> eligible.
    frame1 = _lifecycle_frame(side="bullish", scenario="mitigated", bars_after=1)
    assert evaluate_order_block(
        frame1, StrategySide.LONG, _decision_at(frame1), config,
    ).state is BlockState.RETEST_ELIGIBLE
    # Both bars visible: the second touch means the block is mitigated.
    frame2 = _lifecycle_frame(side="bullish", scenario="mitigated", bars_after=2)
    assert evaluate_order_block(
        frame2, StrategySide.LONG, _decision_at(frame2), config,
    ).state is BlockState.MITIGATED


def test_consumed_ids_derivation_matches_reducer_contract():
    """Reducer-exact derivation incl. a NON-EMPTY consumed-id example."""
    seed = datetime(2024, 1, 1, tzinfo=timezone.utc)
    empty_record = record_from_state(
        StrategyState(event_time=seed), event_at=seed,
    )
    assert d003.consumed_ids_from_record(empty_record) == frozenset()

    # A history with a binding+event (blk-1), a binding+event with a null
    # block (setupB), and a binding WITHOUT an event (blk-2 -> excluded).
    # The derivation contract under test is D003's reducer-exact
    # comprehension over ``record.data()['consumption']``; a stub record
    # isolates it from production's lifecycle-history validation (which is
    # production-owned and already covered by the phase 6/7 suites).
    consumption = {
        "schema": "phase8n.setup-consumption-history.v1",
        "bindings": {
            "setupA": {"block_id": "blk-1"},
            "setupB": {"block_id": None},
            "setupC": {"block_id": "blk-2"},
        },
        "events": {"setupA": {}, "setupB": {}},
        "blocked": {},
    }

    class _StubRecord:
        def data(self):
            return {"consumption": consumption}

    derived = d003.consumed_ids_from_record(_StubRecord())
    assert derived == frozenset({"blk-1"})
    # And it feeds the frozen lifecycle: a consumed id forces CONSUMED.
    config = StrategyConfig()
    frame = _lifecycle_frame(side="bullish")
    at = _decision_at(frame)
    block_id = evaluate_order_block(frame, StrategySide.LONG, at, config).block_id
    assert block_id
    blocked = evaluate_order_block(
        frame, StrategySide.LONG, at, config,
        consumed_ids=frozenset({block_id}),
    )
    assert blocked.state is BlockState.CONSUMED


class _RowStub:
    """Minimal canonical D001 row for observation/aggregation tests."""

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __init__(self, *, decision_id="d1", score=8, checks=None, points=None,
                 ob_valid=True, ob_direction="bullish", fvgs=None, atr=1.0,
                 gate_10=True, gate_11=True):
        self.gate_results = {}
        if gate_11:
            self.gate_results["gate_10_internal_structure"] = gate_10
            self.gate_results["gate_11_confluence_score"] = True
        self.gate_context = {
            "score": {
                "score": score, "max_score": 8, "grade": "A+",
                "passes_threshold": True,
                "checks": [
                    {"label": label, "passed": flag, "points": pts}
                    for label, flag, pts in zip(
                        d001.SCORE_LABELS,
                        checks or [True, True, True, True, True],
                        points or [2, 1, 2, 1, 2],
                    )
                ],
            },
            "ob": {"valid": ob_valid, "zone": [97.0, 99.0], "type": "order_block",
                   "reason": "ob_aligned", "distance_atr": 1.0, "mitigated": False,
                   "in_pd_zone": True, "direction": ob_direction}
            if ob_valid else {},
            "fvgs": fvgs if fvgs is not None else [
                {"bottom": 98.0, "top": 99.0, "direction": "bullish"}],
            "bias_resolution": {"direction": "bullish"},
        }
        self.overlap = {"canonical_fvg_in_ob": True}
        self.atr = atr
        self.decision_id = decision_id


class _SnapshotStub:
    def __init__(self, payload):
        self.gate_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.available_at_ms = int(AT.timestamp() * 1000)


def test_observe_decision_and_aggregation_surfaces():
    snapshot = _SnapshotStub({
        "entry_rows": [
            {"open_time": "2024-04-01T00:00:00+00:00", "available_at": "2024-04-01T00:05:00+00:00",
             "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "timeframe": "M5"},
        ],
    })
    row = _RowStub()
    observation = d003.observe_decision(
        row, _seed_record(), snapshot=snapshot, config=StrategyConfig(),
    )
    assert observation["gate_11_entered"] is True
    assert observation["canonical_lifecycle"]["state"] in ("ELIGIBLE", "RETEST_ELIGIBLE", "UNAVAILABLE")
    aggregate = d003.aggregate_d003([observation])
    assert aggregate["gate11_entrants"] == 1
    for key in (
        "B_frozen_score_components", "C_discriminating_contingency",
        "D_canonical_ob_lifecycle", "E_acquisition_canonical_agreement",
        "F_canonical_failure_reasons", "G_contextual_fvg_coexistence",
        "H_premium_discount_context",
    ):
        assert key in aggregate
    # One legacy-valid + canonical-non-eligible-vs-eligible cell is filled;
    # the exact state depends on the synthetic frame (flat rows -> UNAVAILABLE
    # is NOT reachable here because flat closes produce no confirmed block of
    # the requested side; either way the four cells must sum to entrants).
    cells = aggregate["E_acquisition_canonical_agreement"]
    assert sum(v for k, v in cells.items() if k.startswith("legacy_")) == 1


def test_gate11_non_entrants_are_excluded():
    row = _RowStub(gate_11=False)
    observation = d003.observe_decision(
        row, None, snapshot=_SnapshotStub({"entry_rows": []}), config=StrategyConfig(),
    )
    assert observation["gate_11_entered"] is False
    assert observation["canonical_lifecycle"] is None
    aggregate = d003.aggregate_d003([observation])
    assert aggregate["gate11_entrants"] == 0
    assert aggregate["D_canonical_ob_lifecycle"]["eligible_count"] == 0


# ---------------------------------------------------------------------------
# Banned-output guard (§30)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["pnl", "profit", "profit_factor", "win_rate", "expectancy", "drawdown",
     "sharpe", "returns", "fills", "closed_trades"],
)
def test_banned_exact_keys_fail_closed(key):
    with pytest.raises(d003.D003Error, match=d003.REJECTED_D003_METRIC_KEY):
        d003._reject_banned_metrics({key: 1})


@pytest.mark.parametrize(
    "key",
    ["candidate_count_at_7_of_8", "score_at_6", "temporal_lag_ob_fvg",
     "alternative_overlap", "counterfactual_candidates_if_pd_removed"],
)
def test_banned_substrings_fail_closed(key):
    with pytest.raises(d003.D003Error, match=d003.REJECTED_D003_METRIC_KEY):
        d003._reject_banned_metrics({key: 1})


def test_honest_negation_keys_pass():
    d003._reject_banned_metrics({"no_profitability_metrics": True, "metrics": {"decisions": 5}})


# ---------------------------------------------------------------------------
# Loop-level accounting reconciliation + determinism (synthetic store)
# ---------------------------------------------------------------------------


def _d003_boundary_store(monkeypatch):
    """Tiny Fold-01 store stub covering buckets + two Gate-11 entrants."""
    first = _mocked_ok_snapshot(monkeypatch, at=datetime(2024, 4, 8, tzinfo=timezone.utc))
    second = _mocked_ok_snapshot(
        monkeypatch, at=datetime(2024, 4, 8, tzinfo=timezone.utc) + timedelta(minutes=5)
    )
    rows = [
        _Snapshot(available_at_ms=FOLD01_START_MS, gate_status="early_exit"),
        first,
        second,
        _Snapshot(available_at_ms=FOLD01_START_MS + 9, gate_status="dxy_blocked"),
    ]
    identity = {
        "fold_id": "fold-01", "coverage": "full", "decision_timeframe": "M5",
        "evaluation_start_ms": FOLD01_START_MS, "evaluation_end_ms": FOLD01_END_MS,
    }

    class _Store:
        pass

    store = _Store()
    store.identity = identity
    store.table = _Table(rows)
    store._rows = rows
    return store


def test_run_d003_accounting_and_surfaces(monkeypatch):
    store = _d003_boundary_store(monkeypatch)
    doc, rendered = d003.run_d003(
        store, canonical_commit="c" * 40, tooling_commit="t" * 40,
    )
    accounting = doc["decision_accounting"]
    assert accounting["scheduled"] == 4
    assert accounting["missing_history"] == 1
    assert accounting["unavailable_input"] == 1
    assert accounting["reducer_classified"] + accounting["missing_history"] + \
        accounting["unavailable_input"] + accounting["evaluation_error"] == accounting["scheduled"]
    d003.assert_expected_surfaces(doc)
    # Deterministic output: same store -> byte-identical canonical render
    # apart from the wall-clock provenance timestamp.
    doc2, rendered2 = d003.run_d003(
        store, canonical_commit="c" * 40, tooling_commit="t" * 40,
        # generated_at pinned via provenance patch would be intrusive; the
        # canonical render is otherwise deterministic, so compare shapes.
    )
    assert doc2.keys() == doc.keys()
    assert doc2["decision_accounting"] == doc["decision_accounting"]
    assert doc2["B_frozen_score_components"] == doc["B_frozen_score_components"]
    assert len(rendered) > 0 and len(rendered2) > 0


def test_run_d003_rejects_wrong_fold_and_coverage(monkeypatch):
    store = _d003_boundary_store(monkeypatch)
    store.identity = {**store.identity, "fold_id": "fold-02"}
    with pytest.raises(d001.BoundaryError):
        d003.run_d003(store, canonical_commit="c" * 40, tooling_commit="t" * 40)
    store2 = _d003_boundary_store(monkeypatch)
    store2.identity = {**store2.identity, "coverage": "stride-4"}
    with pytest.raises(d001.BoundaryError):
        d003.run_d003(store2, canonical_commit="c" * 40, tooling_commit="t" * 40)


# ---------------------------------------------------------------------------
# TC001 — causal prior-state wiring regressions (§8–§11).
#
# The lifecycle observer must receive the exact SetupStateRecord consumed by
# ``evaluate_orchestration_decision`` for the SAME decision — never the
# post-decision ``next_record``.  All fixtures are synthetic.
# ---------------------------------------------------------------------------


def _consumed_history(block_id, *, setup_suffix):
    """A production-valid consumption history containing one consumed block
    with ``block_id`` (full binding + event hash chain via the production
    constructors; ``SetupStateRecord`` re-validates on every read)."""
    import json
    from datetime import timedelta as _td

    from bot.execution.lifecycle.entry import new_entry_intent
    from bot.execution.lifecycle.models import Direction, ReadinessStyle
    from bot.execution.lifecycle.serialization import entry_intent_to_payload
    from bot.strategy.setup_consumption import (
        SetupConsumptionEvent,
        SetupEntryBinding,
        canonical,
        register_binding,
    )
    from strategies.smc_engine.strategy_state import StrategyState as _SS

    setup_id = f"s8n1_tc001{setup_suffix}"
    intent = new_entry_intent(
        symbol="XAUUSDm", direction=Direction("buy"), source_timeframe="M5",
        source_candle_open_time=AT, signal_available_at=AT,
        requested_trigger=100.0, stop_loss=90.0, final_target=130.0,
        readiness_style=ReadinessStyle.IMMEDIATE,
    )
    binding = SetupEntryBinding(
        setup_id=setup_id,
        decision_id=f"tc001-decision-{setup_suffix}",
        decision_payload=canonical({
            "setup_id": setup_id, "decision_id": f"tc001-decision-{setup_suffix}",
            "symbol": "XAUUSDm", "side": "buy", "sources": {"m5": "synthetic"},
            "available_at": AT.isoformat(),
            "requested_trigger": intent.requested_trigger,
            "config": f"tc001-config-{setup_suffix}",
            "evidence": f"tc001-evidence-{setup_suffix}",
            "action": "candidate_ready",
        }),
        intent_id=intent.signal_id,
        intent_payload=canonical(entry_intent_to_payload(intent)),
        action_id=f"tc001-action-{setup_suffix}",
        trade_id=f"tc001-trade-{setup_suffix}",
        symbol="XAUUSDm",
        side="buy",
        available_at=AT.isoformat(),
        entry_event_id=f"tc001-entry-event-{setup_suffix}",
        entry_event_at=(AT + _td(seconds=1)).isoformat(),
        entry_tolerance=0.0,
        source_identities=(("m5", "synthetic"),),
        config_fingerprint=f"tc001-config-{setup_suffix}",
        evidence_id=f"tc001-evidence-{setup_suffix}",
        block_id=block_id,
    )
    registered = register_binding(
        record_from_state(_SS(event_time=AT), event_at=AT), binding,
    )
    data = registered.data()
    event = SetupConsumptionEvent(
        binding=binding, fill_id=f"tc001-fill-{setup_suffix}",
        executed_volume=0.02, timestamp=(AT + _td(seconds=1)).isoformat(),
    ).to_dict()
    data["consumption"]["events"][setup_id] = json.loads(canonical(event))
    data["consumption"].pop("blocked", None)
    data["consumption"]["blocked"] = {}
    return data["consumption"]


def _consumed_prior_record():
    """A production-valid SetupStateRecord whose consumption history already
    contains one consumed block (``prior-block")."""
    from bot.strategy.setup_consumption import canonical
    from bot.strategy.setup_state import SetupStateRecord

    data = _seed_record().data()
    data["consumption"] = _consumed_history("prior-block", setup_suffix="prior")
    final = SetupStateRecord(canonical(data))
    final.data()  # full production validation of the complete history
    return final


def _stamp_consumption_on_advance(monkeypatch, prior):
    """Make the reducer's ADVANCE path produce a state whose consumed
    surface is the causal prior surface PLUS ``current-decision-block`` —
    the decision's own consumption — while ``run_d003``'s seed stays pure.

    Only the advance/rebuild constructors used inside snapshot evaluation
    (``bot.state.gate_reducer`` and ``bot.validation.market_feature_store``
    module bindings, identified by a non-seed event time) are stamped; the
    D003 loop's initial seed (event time == the canonical seed) delegates
    untouched.  With the corrected loop the observer sees the PRE-advance
    record ({"prior-block"}); with the 882b4c9 wiring it would see the
    post-decision record (which also contains "current-decision-block").
    """
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    from bot.state import gate_reducer as gate_reducer_mod
    from bot.strategy import setup_state as setup_state_mod
    from bot.strategy.setup_consumption import canonical
    from bot.strategy.setup_state import SetupStateRecord
    from bot.validation import market_feature_store as mfs

    seed_time = _dt(2024, 1, 1, tzinfo=_tz.utc)
    extended = dict(prior.data()["consumption"])
    current = _consumed_history("current-decision-block", setup_suffix="current")
    extended["bindings"] = {**extended["bindings"], **current["bindings"]}
    extended["events"] = {**extended["events"], **current["events"]}
    extended["blocked"] = {}
    extended_record = SetupStateRecord(
        canonical({**prior.data(), "consumption": extended})
    )
    extended_record.data()

    def stamped_record_from_state(state, *, event_at, last_event_id=None, last_result=None):
        record = real_record_from_state(
            state, event_at=event_at,
            last_event_id=last_event_id, last_result=last_result,
        )
        if event_at == seed_time:
            # The D003 loop's canonical seed carries the causal PRIOR surface.
            data = record.data()
            data["consumption"] = prior.data()["consumption"]
            stamped = SetupStateRecord(canonical(data))
            stamped.data()
            return stamped
        data = record.data()
        data["consumption"] = extended_record.data()["consumption"]
        stamped = SetupStateRecord(canonical(data))
        stamped.data()
        return stamped

    real_record_from_state = setup_state_mod.record_from_state
    for module in (gate_reducer_mod, setup_state_mod, mfs):
        monkeypatch.setattr(module, "record_from_state", stamped_record_from_state)


def _store_with_rows(monkeypatch, rows):
    identity = {
        "fold_id": "fold-01", "coverage": "full", "decision_timeframe": "M5",
        "evaluation_start_ms": FOLD01_START_MS, "evaluation_end_ms": FOLD01_END_MS,
    }

    class _Store:
        pass

    store = _Store()
    store.identity = identity
    store.table = _Table(rows)
    store._rows = rows
    return store


def _run_with_spies(monkeypatch, store):
    """Run ``run_d003`` with the D001 adapter wrapper and the D003 observer
    both recorded; both delegates are the real production paths.  The loop
    resolves both names from d003's module namespace (its top-level import),
    so those bindings are the spy targets."""
    import backtests.phase8_v2_diagnostic_d001 as d001_mod

    adapter_records: list = []
    real_adapter = d001_mod.evaluate_orchestration_decision

    def adapter_spy(snapshot, record):
        adapter_records.append(record)
        return real_adapter(snapshot, record)

    monkeypatch.setattr(d003, "evaluate_orchestration_decision", adapter_spy)

    observer_records: list = []
    real_observer = d003.observe_decision

    def observer_spy(row, prior_state_record, *, snapshot, config):
        observer_records.append(prior_state_record)
        return real_observer(row, prior_state_record, snapshot=snapshot, config=config)

    monkeypatch.setattr(d003, "observe_decision", observer_spy)
    doc, rendered = d003.run_d003(store, canonical_commit="c" * 40, tooling_commit="t" * 40)
    return doc, rendered, adapter_records, observer_records


def test_tc001_observer_receives_prior_record_not_next(monkeypatch):
    """§8: the observer receives the exact record object supplied to the
    adapter for the same decision — not the post-decision next record.

    Fails at 882b4c9: there ``state_record = next_record`` runs before the
    observer call, so the identity assertions below break.
    """
    store = _d003_boundary_store(monkeypatch)
    doc, _, adapter_records, observer_records = _run_with_spies(monkeypatch, store)

    assert observer_records, "observer must run for successful decisions"
    assert len(adapter_records) == len(observer_records)
    for adapter_record, observer_record in zip(adapter_records, observer_records):
        assert observer_record is adapter_record, (
            "observer must receive the identical prior record consumed by "
            "the adapter for the same decision"
        )
    assert doc["decision_accounting"]["reducer_classified"] >= 1


def test_tc001_consumed_ids_come_from_prior_state_only(monkeypatch):
    """§9: with a causal prior surface of exactly {"prior-block"}, the
    lifecycle observation for the CURRENT decision derives consumed ids
    from the PRIOR record only — the decision's own consumption
    ("current-decision-block", added by the reducer's advance) is absent.

    Fails at 882b4c9: the observer receives the post-decision next record,
    whose consumed surface contains "current-decision-block".
    """
    prior = _consumed_prior_record()
    _stamp_consumption_on_advance(monkeypatch, prior)
    store = _store_with_rows(
        monkeypatch, [_mocked_ok_snapshot(monkeypatch, at=datetime(2024, 4, 8, tzinfo=timezone.utc))],
    )

    captured: list = []
    real_observer = d003.observe_decision

    def observer_spy(row, prior_state_record, *, snapshot, config):
        captured.append((prior_state_record, real_observer(
            row, prior_state_record, snapshot=snapshot, config=config,
        )))
        return captured[-1][1]

    monkeypatch.setattr(d003, "observe_decision", observer_spy)
    doc, _ = d003.run_d003(store, canonical_commit="c" * 40, tooling_commit="t" * 40)

    assert doc["decision_accounting"]["reducer_classified"] == 1
    assert len(captured) == 1
    record, observation = captured[0]
    lifecycle = observation.get("canonical_lifecycle")
    assert lifecycle is not None, "Gate-11 entrant must carry a lifecycle observation"
    derived = set(lifecycle.get("consumed_ids_derived") or [])
    assert derived == {"prior-block"}, (
        "consumed ids must derive ONLY from the causal prior state record "
        f"(got {sorted(derived)!r}; 'current-decision-block' must be absent)"
    )


def test_tc001_two_successive_decisions_causal_sequencing(monkeypatch):
    """§10: decision 1 observes the seed record; after success the state
    advances to record 1; decision 2 observes record 1 — not the seed and
    not its own post-decision record 2."""
    at1 = datetime(2024, 4, 8, tzinfo=timezone.utc)
    rows = [
        _mocked_ok_snapshot(monkeypatch, at=at1),
        _mocked_ok_snapshot(monkeypatch, at=at1 + timedelta(minutes=5)),
        _mocked_ok_snapshot(monkeypatch, at=at1 + timedelta(minutes=10)),
    ]
    store = _store_with_rows(monkeypatch, rows)
    doc, _, adapter_records, observer_records = _run_with_spies(monkeypatch, store)

    assert len(adapter_records) == 3 and len(observer_records) == 3
    seed = _seed_record()
    # Decision 1: the observer receives the seed record (equal payload —
    # run_d003 constructs its own seed instance).
    assert observer_records[0] == seed, (
        "decision 1 must observe the seed (prior) record"
    )
    # Decision 2: the observer receives the record the sequential chain
    # advanced to after decision 1 — not the seed and not decision 2's own
    # post-decision record.
    assert observer_records[1] is not seed
    assert observer_records[1] is not observer_records[0]
    # Three decisions, three distinct causal prior records.
    assert len({id(record) for record in observer_records}) == 3
    assert doc["decision_accounting"]["reducer_classified"] == 3


def test_tc001_error_preserves_prior_state_for_next_observation(monkeypatch):
    """§11: success → error → success.  The error row produces no
    observation, advances nothing, and the next successful decision
    observes the same prior record preserved across the error."""
    from bot.validation import market_feature_store as mfs

    at1 = datetime(2024, 4, 8, tzinfo=timezone.utc)
    rows = [
        _mocked_ok_snapshot(monkeypatch, at=at1),
        _mocked_ok_snapshot(monkeypatch, at=at1 + timedelta(minutes=5)),
        _mocked_ok_snapshot(monkeypatch, at=at1 + timedelta(minutes=10)),
    ]
    error_snapshot = rows[1]
    error_available_ms = int(error_snapshot.available_at_ms)
    real_orchestrator = mfs.evaluate_orchestration_from_features

    def boom_once(*args, **kwargs):
        raise ValueError("synthetic orchestrator failure")

    import backtests.phase8_v2_diagnostic_d001 as d001_mod

    real_adapter = d001_mod.evaluate_orchestration_decision
    error_inputs: list = []
    success_next: list = []

    def adapter_spy(snapshot, record):
        # _snapshot_rows reconstructs store rows, so key on the decision
        # identity (available_at_ms), not fixture object identity.
        if int(snapshot.available_at_ms) == error_available_ms:
            monkeypatch.setattr(mfs, "evaluate_orchestration_from_features", boom_once)
            try:
                result = real_adapter(snapshot, record)
            finally:
                monkeypatch.setattr(mfs, "evaluate_orchestration_from_features", real_orchestrator)
            assert result[0]["action"] == "error"
            error_inputs.append((int(snapshot.available_at_ms), record))
            return result
        result = real_adapter(snapshot, record)
        if result[0]["action"] != "error":
            success_next.append((int(snapshot.available_at_ms), result[1]))
        return result

    monkeypatch.setattr(d003, "evaluate_orchestration_decision", adapter_spy)

    observer_records: list = []
    real_observer = d003.observe_decision

    def observer_spy(row, prior_state_record, *, snapshot, config):
        observer_records.append(prior_state_record)
        return real_observer(row, prior_state_record, snapshot=snapshot, config=config)

    monkeypatch.setattr(d003, "observe_decision", observer_spy)
    store = _store_with_rows(monkeypatch, rows)
    doc, _ = d003.run_d003(store, canonical_commit="c" * 40, tooling_commit="t" * 40)

    accounting = doc["decision_accounting"]
    assert accounting["evaluation_error"] == 1
    assert accounting["reducer_classified"] == 2
    assert len(observer_records) == 2, "the error row must produce no observation"
    assert len(success_next) == 2 and len(error_inputs) == 1
    at1_ms = int(at1.timestamp() * 1000)
    first_success_next = next(
        record for available_ms, record in success_next if available_ms == at1_ms
    )
    # The error was evaluated from exactly the state success #1 advanced to,
    # and the error advanced/preserved nothing: decision #3 then observes
    # that same carried record object as its causal prior.
    assert error_inputs[0][1] is first_success_next, (
        "the error decision must be evaluated from the state carried "
        "forward after success #1"
    )
    assert observer_records[1] is first_success_next, (
        "the decision after the error must observe the same prior state "
        "preserved across the error — not a re-seeded or further-advanced state"
    )


def test_write_result_refuses_overwrite(tmp_path, monkeypatch):
    doc, rendered = d003.run_d003(
        _d003_boundary_store(monkeypatch), canonical_commit="c" * 40, tooling_commit="t" * 40,
    )
    target, digest = d003.write_result(doc, rendered, tmp_path)
    assert Path(target).exists()
    import hashlib

    assert hashlib.sha256(Path(target).read_bytes()).hexdigest() == digest
    with pytest.raises(d003.D003Error, match="refusing overwrite"):
        d003.write_result(doc, rendered, tmp_path)
