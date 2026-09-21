"""Phase 8N-J replay-performance control CLI.

Engineering commands over the plan-bound empirical inputs.  Nothing here
executes a development-evaluation cell, computes a strategy metric, or
touches holdout/2025+ data:

- ``build-input-index``   build + atomically publish the fold-scoped index;
- ``verify-input-index``  load + re-verify a published index (read-only);
- ``benchmark-pipeline``  bounded DEVELOPMENT-ONLY engineering benchmark
  (equivalence + throughput on a pre-declared interval — NOT STRATEGY
  EVIDENCE);
- ``estimate-optimized``  project the 64-cell optimized runtime from the
  measured index build cost and replay mechanics (ESTIMATE, NOT A
  GUARANTEE).

The empirical ``run``/``resume`` commands remain in
``development_evaluation_control.py`` unchanged.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes  # noqa: F401  (ctypes.wintypes attribute access)
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.acquisition.evidence_contracts import canonical_hash  # noqa: E402
from bot.validation import development_evaluation_runner as runner  # noqa: E402
from bot.validation import market_feature_store as features  # noqa: E402
from bot.validation import replay_input_index as replay  # noqa: E402

BENCHMARK_LABEL = "EMPIRICAL ENGINEERING BENCHMARK — NOT STRATEGY EVIDENCE"


def _evidence_root(args: argparse.Namespace) -> Path:
    return Path(args.evidence_root)


def _resolve_bindings(args: argparse.Namespace):
    from bot.validation.empirical_input_pipeline import resolve_input_bindings

    return resolve_input_bindings(
        evidence_root=_evidence_root(args),
        worktree=Path(args.worktree),
        contamination_path=Path(args.contamination_path),
        plan=runner.load_corrected_plan(_evidence_root(args)),
        tick_verification_depth=getattr(args, "tick_verification_depth", "identity-chain"),
    )


def _plan(args: argparse.Namespace):
    return runner.load_corrected_plan(_evidence_root(args))


def _first_fold(plan):
    return plan["folds"][0]


def _peak_working_set_bytes() -> int:
    """Windows peak working set via ctypes (no third-party dependency)."""
    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_uint32),
            ("PageFaultCount", ctypes.c_uint32),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    psapi = ctypes.windll.psapi
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
        ctypes.wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        return 0
    return int(counters.PeakWorkingSetSize)


def cmd_build_input_index(args: argparse.Namespace) -> int:
    bindings = _resolve_bindings(args)
    plan = bindings.plan
    built = []
    for fold in plan["folds"]:
        index = replay.build_replay_input_index(bindings, fold=fold)
        evidence_root = Path(bindings.evidence_root)
        try:
            existing = replay.find_published_index(
                evidence_root, fold_id=index.fold_id, index_sha256=index.index_sha256,
            )
        except Exception:  # noqa: BLE001 — absent index is the expected first-run case
            existing = None
        if existing is not None:
            replay.load_input_index(existing)
            built.append({
                "fold_id": index.fold_id, "index_sha256": index.index_sha256,
                "status": "ALREADY_PUBLISHED", "path": str(existing),
            })
            continue
        path, digest = replay.publish_input_index(index, evidence_root=evidence_root)
        if digest != index.index_sha256:
            raise runner.RunnerError("published input index digest mismatch")
        replay.load_input_index(path)
        built.append({
            "fold_id": index.fold_id, "index_sha256": index.index_sha256,
            "status": "PUBLISHED", "path": str(path),
        })
    print(json.dumps({
        "schema": runner.RUNNER_SCHEMA, "mode": "BUILD_INPUT_INDEX",
        "indexes": built, "plan_fingerprint": plan["plan_fingerprint"],
    }, sort_keys=True, indent=2))
    return 0


def cmd_verify_input_index(args: argparse.Namespace) -> int:
    bindings = _resolve_bindings(args)
    plan = bindings.plan
    verified = []
    for fold in plan["folds"]:
        index = replay.build_replay_input_index(bindings, fold=fold)
        path = replay.find_published_index(
            Path(bindings.evidence_root), fold_id=index.fold_id, index_sha256=index.index_sha256,
        )
        loaded = replay.load_input_index(path)
        replay.verify_index_matches_bindings(loaded, bindings)
        verified.append({
            "fold_id": loaded.fold_id, "index_sha256": loaded.index_sha256,
            "decisions": len(loaded.decisions),
            "partitions": len(loaded.partitions),
            "pipeline_fingerprint": loaded.pipeline_fingerprint[:16],
            "verified": True,
        })
    print(json.dumps({
        "schema": runner.RUNNER_SCHEMA, "mode": "VERIFY_INPUT_INDEX",
        "indexes": verified, "plan_fingerprint": plan["plan_fingerprint"],
    }, sort_keys=True, indent=2))
    return 0


def _benchmark_interval(plan) -> tuple[dict, int, int]:
    """Pre-declared engineering interval: fold 1's first 6 hours of 2024.

    Fixed by contract (first evaluation hours of the first fold) — chosen for
    engineering coverage, not market outcomes.  6 hours guarantees idle spans
    (no injected intent pending, no open position) so the benchmark exercises
    the event-driven skip path on real data.
    """
    import pandas as pd

    fold = _first_fold(plan)
    start_ms = int(pd.Timestamp(fold["evaluation"]["start"]).value // 1_000_000)
    end_ms = start_ms + 6 * 3_600_000
    return fold, start_ms, end_ms


def cmd_benchmark_pipeline(args: argparse.Namespace) -> int:
    import numpy as np
    import pandas as pd

    from bot.validation import empirical_input_pipeline as pipeline

    bindings = _resolve_bindings(args)
    plan = bindings.plan
    fold, bench_start_ms, bench_end_ms = _benchmark_interval(plan)
    prepared = datetime.now(timezone.utc).isoformat()

    # -- build/load the fold index (build cost is part of the measurement) --
    build_started = time.perf_counter()
    index = replay.build_replay_input_index(bindings, fold=fold)
    build_seconds = time.perf_counter() - build_started
    evidence_root = Path(bindings.evidence_root)
    try:
        existing = replay.find_published_index(
            evidence_root, fold_id=index.fold_id, index_sha256=index.index_sha256,
        )
    except Exception:  # noqa: BLE001
        existing = None
    if existing is None:
        path, digest = replay.publish_input_index(index, evidence_root=evidence_root)
        if digest != index.index_sha256:
            raise runner.RunnerError("published input index digest mismatch")
        index = replay.load_input_index(path)
    else:
        index = replay.load_input_index(existing)
    replay.verify_index_matches_bindings(index, bindings)

    warmup_start_ms = int(pd.Timestamp(fold["warmup"]["start"]).value // 1_000_000)
    eval_end_ms = min(
        int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000),
        pipeline.DEVELOPMENT_END_MS,
    )

    def materialize():
        return pipeline.materialize_candle_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        ), pipeline.materialize_constituent_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        )

    cell = _benchmark_cell(plan, fold)

    # ------------------------------------------------------------------
    # Pass 1: OPTIMIZED driver with a bounded event cap.  Its last
    # processed event timestamp defines the shared merge-consistent
    # horizon; the reference pass is then bounded to the identical
    # horizon so both compare the exact same event set.
    # ------------------------------------------------------------------
    candle_frames2, constituent_frames2 = materialize()
    opt_context = pipeline.CellExecutionContext(
        cell=cell, fold=fold, scenario=cell["scenario"], bindings=bindings,
        cell_dir=Path(args.benchmark_root) / "optimized",
    )
    opt_handler = pipeline.CellEventHandler(
        opt_context, candle_frames=candle_frames2, constituent_frames=constituent_frames2,
    )
    _inject_benchmark_intents(opt_handler)

    driver = replay.OptimizedCellDriver(opt_context, opt_handler, index=index)
    counters: dict[str, int] = {}
    cpu0 = time.process_time()
    started = time.perf_counter()
    driver.run(
        checkpoint_every=0, counters=counters,
        batch_rows=int(args.batch_rows), max_processed=int(args.max_processed),
        finish=False,
    )
    opt_wall = time.perf_counter() - started
    opt_cpu = time.process_time() - cpu0
    horizon_ms = int(counters.get("last_event_ts_ms", 0))
    if horizon_ms <= 0:
        raise runner.RunnerError("optimized pass produced no event horizon")
    peak_bytes = _peak_working_set_bytes()

    # ------------------------------------------------------------------
    # Pass 1b: FEATURE-SNAPSHOT fast path over the identical horizon and
    # event cap.  Builds the sampled (partial-coverage) store once — its
    # build cost is the measured fold-amortized construction — then runs
    # the SAME optimized driver with the provider attached.  Identical
    # semantics, identical skipping mechanics; only the feature source
    # differs (reference construction vs memoized store).  Any decision
    # not covered by the store fails the pass loudly (KeyError).
    # ------------------------------------------------------------------
    fast_root = Path(args.benchmark_root) / "fast"
    fast_context = pipeline.CellExecutionContext(
        cell=cell, fold=fold, scenario=cell["scenario"], bindings=bindings,
        cell_dir=fast_root,
    )
    fast_handler = pipeline.CellEventHandler(
        fast_context, candle_frames=candle_frames2, constituent_frames=constituent_frames2,
    )
    _inject_benchmark_intents(fast_handler)
    fast_build_started = time.perf_counter()
    fast_records = list(features.build_feature_records(
        bindings, index,
        candle_frames=candle_frames2, constituent_frames=constituent_frames2,
        available_at_range=(bench_start_ms, horizon_ms + 1),
    ))
    fast_build_seconds = time.perf_counter() - fast_build_started
    # Publishes into the benchmark-scoped root; the identity automatically
    # carries coverage "partial:N-of-M" so no production loader can ever
    # adopt this engineering-benchmark store.
    fast_store_path, _fast_sha = features.publish_feature_store(
        fast_records, evidence_root=Path(args.benchmark_root),
        bindings=bindings, index=index,
    )
    fast_store = features.load_feature_store(fast_store_path)
    fast_handler.feature_provider = features.FoldFeatureProvider(
        fast_store, index=index
    )

    fast_driver = replay.OptimizedCellDriver(fast_context, fast_handler, index=index)
    fast_counters: dict[str, int] = {}
    cpu0 = time.process_time()
    started = time.perf_counter()
    fast_driver.run(
        checkpoint_every=0, counters=fast_counters,
        batch_rows=int(args.batch_rows), max_processed=int(args.max_processed),
        finish=False,
    )
    fast_wall = time.perf_counter() - started
    fast_cpu = time.process_time() - cpu0
    fast_serve_count = fast_handler.feature_provider.serve_count

    # Fast-path equivalence: served decision identities equal the
    # optimized pass's decision set; semantic quote states are identical.
    fast_decision_ids = [item["decision_id"] for item in fast_context.decisions]
    if fast_decision_ids != [item["decision_id"] for item in opt_context.decisions]:
        raise runner.RunnerError(
            "BENCHMARK_EQUIVALENCE_FAILED: fast-path decision identities "
            f"diverge (fast={len(fast_decision_ids)} "
            f"opt={len(opt_context.decisions)})"
        )
    last_fast = _last_quote_state(fast_context, semantic_only=True)
    if last_fast != _last_quote_state(opt_context, semantic_only=True):
        raise runner.RunnerError(
            "BENCHMARK_EQUIVALENCE_FAILED: fast-path quote-state divergence "
            f"(fast={last_fast})"
        )

    # ------------------------------------------------------------------
    # Pass 2: REFERENCE pipeline over the identical horizon.
    # ------------------------------------------------------------------
    candle_frames, constituent_frames = materialize()
    ref_context = pipeline.CellExecutionContext(
        cell=cell, fold=fold, scenario=cell["scenario"], bindings=bindings,
        cell_dir=Path(args.benchmark_root) / "reference",
    )
    ref_handler = pipeline.CellEventHandler(
        ref_context, candle_frames=candle_frames, constituent_frames=constituent_frames,
    )
    # Identical injected intents on both paths: the cadence depends only on
    # decision timestamps, so reference and optimized receive the same
    # pending intents and exercise the same fill/management contracts.
    _inject_benchmark_intents(ref_handler)

    def reference_events():
        for event in pipeline.empirical_event_stream(bindings, fold):
            if int(event["timestamp_ms"]) > horizon_ms:
                return
            yield event

    cpu0 = time.process_time()
    started = time.perf_counter()
    ref_decisions = []
    ref_quotes = 0
    for event in reference_events():
        key = str(event["event_id"])
        if event["event_kind"] == "DECISION":
            ref_handler.on_signal(event)
            ref_decisions.append(key)
        else:
            ref_handler.on_quote(event)
            ref_quotes += 1
        stamp = datetime.fromtimestamp(
            (int(event["timestamp_ms"]) // 3_600_000) * 3600, tz=timezone.utc
        )
        ref_handler.on_session_boundary(stamp)
        ref_context.consumed_event_keys.add(key)
    ref_wall = time.perf_counter() - started
    ref_cpu = time.process_time() - cpu0

    # ------------------------------------------------------------------
    # Equivalence: identical decision identities; identical quote states.
    # ------------------------------------------------------------------
    opt_decision_ids = [item["decision_id"] for item in opt_context.decisions]
    opt_decision_set = set(opt_decision_ids)
    missing = [key for key in ref_decisions if key not in opt_decision_set]
    extra = sorted(opt_decision_set - set(ref_decisions))
    last_ref = _last_quote_state(ref_context, semantic_only=True)
    last_opt = _last_quote_state(opt_context, semantic_only=True)
    if missing or extra:
        raise runner.RunnerError(
            f"BENCHMARK_EQUIVALENCE_FAILED: missing={missing} extra={extra}"
        )
    if last_ref != last_opt:
        raise runner.RunnerError(
            "BENCHMARK_EQUIVALENCE_FAILED: quote-state divergence "
            f"(reference={last_ref} optimized={last_opt})"
        )

    # ------------------------------------------------------------------
    # Interval measurement: ticks in [start, end) per partition statistics.
    # ------------------------------------------------------------------
    interval_rows = 0
    for part in index.partitions:
        for low, high, _start_row, num_rows in part.row_groups:
            if high < bench_start_ms or low >= bench_end_ms:
                continue
            if low >= bench_start_ms and high < bench_end_ms:
                interval_rows += num_rows
            else:
                # Edge row group: count rows inside the interval exactly.
                import pyarrow.parquet as pq  # noqa: PLC0415

                table = pq.ParquetFile(part.path).read_row_group(
                    part.row_groups.index((low, high, _start_row, num_rows)),
                    columns=["time_msc"],
                )
                times = np.asarray(table.column("time_msc").to_pylist(), dtype=np.int64)
                interval_rows += int(
                    np.searchsorted(times, bench_end_ms, side="left")
                    - np.searchsorted(times, bench_start_ms, side="left")
                )

    total_source_rows = sum(part.row_count for part in index.partitions)
    total_events = ref_decisions.__len__() + ref_quotes
    ref_throughput = total_events / ref_wall if ref_wall > 0 else 0.0
    projected_cell_seconds = total_source_rows / ref_throughput if ref_throughput > 0 else None
    opt_effective = (
        counters.get("decisions_processed", 0) + counters.get("active_quotes_processed", 0)
    )
    opt_throughput = opt_effective / opt_wall if opt_wall > 0 else 0.0

    report = {
        "schema": runner.RUNNER_SCHEMA,
        "label": BENCHMARK_LABEL,
        "classification": "DEVELOPMENT_ENGINEERING_ONLY",
        "strategy_metrics_produced": False,
        "prepared_at_utc": prepared,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_fingerprint": plan["plan_fingerprint"],
        "fold_id": fold["fold_id"],
        "interval": {
            "start_utc": datetime.fromtimestamp(bench_start_ms / 1000, tz=timezone.utc).isoformat(),
            "end_utc": datetime.fromtimestamp(bench_end_ms / 1000, tz=timezone.utc).isoformat(),
            "selection_rule": "first 6 evaluation hours of fold 1, pre-declared",
        },
        "input_index": {
            "sha256": index.index_sha256,
            "build_seconds": round(build_seconds, 3),
            "decisions": len(index.decisions),
            "partitions": len(index.partitions),
            "source_rows": total_source_rows,
        },
        "reference": {
            "decision_events": len(ref_decisions),
            "quote_events": ref_quotes,
            "wall_seconds": round(ref_wall, 3),
            "cpu_seconds": round(ref_cpu, 3),
            "events_per_second": round(ref_throughput, 1),
        },
        "optimized": {
            "decision_events": counters.get("decisions_processed", 0),
            "active_quote_events": counters.get("active_quotes_processed", 0),
            "idle_quotes_skipped": counters.get("idle_quotes_skipped", 0),
            "idle_spans": counters.get("idle_spans", 0),
            "row_groups_decoded": counters.get("row_groups_decoded", 0),
            "row_groups_total": counters.get("row_groups_total", 0),
            "batch_rows": int(args.batch_rows),
            "wall_seconds": round(opt_wall, 3),
            "cpu_seconds": round(opt_cpu, 3),
            "effective_events_per_second": round(opt_throughput, 1),
        },
        "feature_snapshot": {
            "store_rows": len(fast_records),
            "coverage_window_ms": [int(bench_start_ms), int(horizon_ms + 1)],
            "build_seconds": round(fast_build_seconds, 3),
            "serve_count": fast_serve_count,
            "row_groups_decoded": fast_counters.get("row_groups_decoded", 0),
            "decision_events": fast_counters.get("decisions_processed", 0),
            "active_quote_events": fast_counters.get("active_quotes_processed", 0),
            "idle_quotes_skipped": fast_counters.get("idle_quotes_skipped", 0),
            "wall_seconds": round(fast_wall, 3),
            "cpu_seconds": round(fast_cpu, 3),
            "speedup_vs_reference_construction": (
                round(opt_wall / fast_wall, 3) if fast_wall > 0 else None
            ),
            "equivalence": {
                "decision_identities_equal": True,
                "quote_state_equal": True,
            },
        },
        "equivalence": {
            "decision_identities_equal": True,
            "quote_state_equal": True,
            "checked_decisions": len(ref_decisions),
        },
        "interval_rows": interval_rows,
        "peak_working_set_bytes": peak_bytes,
    }
    root = Path(args.benchmark_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / "benchmark_report.json"
    if target.exists():
        raise runner.RunnerError(f"benchmark report already published: {target}")
    _atomic_write_text(target, json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


def _benchmark_cell(plan, fold) -> dict:
    cell = next(
        (candidate for candidate in plan["scenario_cell_contract"]["cells"]
         if candidate["fold"]["fold_id"] == fold["fold_id"]),
        None,
    )
    if cell is None:
        raise runner.RunnerError("plan defines no cell for the benchmark fold")
    return dict(cell)


def _inject_benchmark_intents(handler) -> None:
    """Deterministic entry intents on a fixed decision cadence.

    Mirrors the Phase 8N-J test injector: the benchmark exercises the shared
    execution contracts (pending-intent fills, position management), not the
    strategy gates; no market outcome is recorded.
    """
    from bot.execution.live_adapter import intent_from_strategy_entry
    from bot.execution.lifecycle.entry import create_entry_state
    from bot.execution.lifecycle.models import Direction
    from bot.strategy.setup_state import record_from_state, state_from_record
    from bot.validation.empirical_input_pipeline import _publish_decision
    import hashlib
    import json
    import pandas as pd

    original_on_signal = handler.on_signal

    def on_signal_with_intent(event: dict) -> None:
        context = handler.context
        original_on_signal(event)
        ts = pd.Timestamp(event["timestamp_ms"], unit="ms", tz="UTC")
        if ts.minute != 0 or ts.hour < 1:
            return
        decision_for = pd.Timestamp(event["decision_for_open_ms"], unit="ms", tz="UTC")
        direction = Direction.BUY if ts.hour % 2 == 1 else Direction.SELL
        source_close = float(event["source_close"])
        # Bracket sized against real XAUUSDm tick spreads (about 200-301
        # points = $0.20-$0.30): the frozen maximum_spread_to_stop_fraction
        # is 0.10, so stop >= $3.02 keeps every entry executable, while the
        # stop still resolves quickly so the benchmark exercises idle spans
        # (skip path) between hourly intents as well as full pending/open
        # processing.
        risk = 3.5 if direction is Direction.BUY else 2.8
        if direction is Direction.BUY:
            stop, target = source_close - risk, source_close + 2 * risk
        else:
            stop, target = source_close + risk, source_close - 2 * risk
        intent = intent_from_strategy_entry(
            symbol="XAUUSDm", source_timeframe="M5",
            entry={"direction": direction.value, "entry_type": "market"},
            entry_frame=pd.DataFrame({
                "open_time": [decision_for.to_pydatetime()],
                "available_at": [ts.to_pydatetime()],
                "close": [source_close],
            }),
            stop_loss=stop, final_target=target,
            partial_close_fraction=0.5,
            configuration_id="phase8n-j-engineering-benchmark",
            expiry_minutes=45,
        )
        # Publish a synthetic approved (candidate_ready) decision through the
        # same durable setup store real candidates use, derived from the
        # intent so the fill-time binding contract validates exactly.
        decision_at = ts.to_pydatetime()
        state = state_from_record(context.state_record, decision_at)
        state.entry_started = True
        state.last_update = decision_at.replace(tzinfo=None)
        source = (
            f"M5:{intent.source_candle_open_time.isoformat()}"
            f":{intent.signal_available_at.isoformat()}"
        )
        setup_id = "s8nj_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:32]
        result = {
            "action": "candidate_ready",
            "event_id": event["event_id"],
            "setup_id": setup_id,
            "context": {
                "setup_id": setup_id,
                "event_id": event["event_id"],
                "symbol": intent.symbol,
                "source_close": float(intent.requested_trigger),
                "entry": {
                    "direction": intent.direction.value,
                    "entry_type": "market",
                },
                "source_identities": {"M5": source},
                "signal_available_at": intent.signal_available_at.isoformat(),
                "config_fingerprint": "phase8n-j-engineering-benchmark",
                "evidence_id": "phase8n-j-engineering-benchmark",
            },
        }
        record = record_from_state(
            state, event_at=decision_at, last_event_id=event["event_id"],
            last_result=json.dumps(
                result, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ),
        )
        context.state_record = _publish_decision(context, record)
        context.pending_intents.append({
            "intent": intent, "state": create_entry_state(intent),
            "decision_id": event["event_id"],
        })

    handler.on_signal = on_signal_with_intent


def _last_quote_state(context, *, semantic_only: bool = False) -> dict:
    """Normalized terminal state after every processed event.

    ``semantic_only`` drops cursors that legitimately differ by design under
    event-driven skipping (consumed-key count, handler sequence): skipped
    idle quotes never enter orchestration, which is exactly the optimization.
    """
    engine = context.engine
    return {
        "balance": engine.account.balance,
        "equity": engine.account.equity,
        "commission": engine.account.commission,
        "swap": engine.account.swap,
        "realized_gross_pnl": engine.account.realized_gross_pnl,
        "fills": len(engine.fills),
        "ledger": len(engine.ledger),
        "rejections": len(context.rejections),
        "pending": len(context.pending_intents),
        "positions": len(context.lifecycle_positions),
        **({} if semantic_only else {
            "consumed": len(context.consumed_event_keys),
            "quote_sequence": context.quote_sequence,
        }),
    }


def cmd_benchmark_features(args: argparse.Namespace) -> int:
    """Mechanically sampled fast-path benchmark across ALL FOUR folds.

    Window rule (pre-declared, mechanical, outcome-blind): every fold is
    benchmarked over the first N evaluation decisions in decision-time
    order; N is chosen once per invocation so the pooled sample is >= 1,000
    decisions.  Strategy metrics are never computed; only construction and
    serving costs are measured.
    """
    import pandas as pd  # noqa: PLC0415

    from bot.validation import empirical_input_pipeline as pipeline

    bindings = _resolve_bindings(args)
    plan = bindings.plan
    cells = plan["scenario_cell_contract"]["cells"]
    folds = plan["folds"]
    cells_per_fold = len(cells) // len(folds)
    if len(cells) != 64 or cells_per_fold * len(folds) != 64:
        raise runner.RunnerError("plan cell count does not match the frozen 64-cell matrix")

    MIN_SAMPLE = 1_000
    per_fold_sample = (MIN_SAMPLE + len(folds) - 1) // len(folds)  # ceil(1000/4)
    prepared = datetime.now(timezone.utc).isoformat()

    fold_reports = []
    for fold in folds:
        build_started = time.perf_counter()
        index = replay.build_replay_input_index(bindings, fold=fold)
        build_seconds = time.perf_counter() - build_started
        decisions = index.decisions
        if len(decisions) < per_fold_sample:
            raise runner.RunnerError(
                f"fold {fold['fold_id']} has fewer decisions ({len(decisions)}) "
                f"than the sampled benchmark requires ({per_fold_sample})"
            )
        window_start_ms = int(decisions[0][0])
        window_end_ms = int(decisions[per_fold_sample - 1][0])
        sample_n = per_fold_sample

        cell = _benchmark_cell(plan, fold)
        warmup_start_ms = int(
            pd.Timestamp(fold["warmup"]["start"]).value // 1_000_000
        )
        eval_end_ms = min(
            int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000),
            pipeline.DEVELOPMENT_END_MS,
        )

        # Cold-cache build of the sampled store (full construction cost).
        candle_frames, constituent_frames = (
            pipeline.materialize_candle_frames(
                bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
            ),
            pipeline.materialize_constituent_frames(
                bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
            ),
        )
        build_started = time.perf_counter()
        fast_records = list(features.build_feature_records(
            bindings, index,
            candle_frames=candle_frames, constituent_frames=constituent_frames,
            available_at_range=(window_start_ms, window_end_ms + 1),
        ))
        if len(fast_records) != sample_n:
            raise runner.RunnerError(
                f"sampled store build covered {len(fast_records)} decisions, "
                f"expected {sample_n}"
            )
        fast_build_seconds = time.perf_counter() - build_started
        # Benchmark-scoped publication; the identity records coverage as
        # "partial:N-of-M" so no production loader can adopt this store.
        fast_store_path, _fast_sha = features.publish_feature_store(
            fast_records, evidence_root=Path(args.benchmark_root),
            bindings=bindings, index=index,
        )
        fast_store = features.load_feature_store(fast_store_path)
        provider = features.FoldFeatureProvider(fast_store, index=index)

        # Cold-cache serve: first-touch cost per decision.
        cold_started = time.perf_counter()
        for record in fast_records:
            provider.features_for(int(record["available_at_ms"]), str(record["identity"]))
        cold_serve_seconds = time.perf_counter() - cold_started

        # Warm-cache serve: repeat the identical pass (OS/file cache warm).
        warm_started = time.perf_counter()
        for record in fast_records:
            provider.features_for(int(record["available_at_ms"]), str(record["identity"]))
        warm_serve_seconds = time.perf_counter() - warm_started

        # Cell-local reducer throughput over the served inputs (pure gate
        # work; construction excluded by construction of the measurement).
        from bot.strategy.setup_state import record_from_state, StrategyState
        from bot.validation.market_feature_store import (
            evaluate_orchestration_from_features,
        )

        # Mirror the pipeline's seeded initial setup record exactly.
        seed_record = record_from_state(
            StrategyState(event_time=datetime(2024, 1, 1, tzinfo=timezone.utc)),
            event_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        reducer_started = time.perf_counter()
        reducer_decisions = 0
        for record in fast_records:
            snap = provider.features_for(
                int(record["available_at_ms"]), str(record["identity"])
            )
            if snap.check_passes and snap.news_context.get("news_clear", False):
                evaluate_orchestration_from_features(
                    snap,
                    decision_at=_decision_datetime_ms(int(record["available_at_ms"])),
                    prior_state=seed_record,
                    active_trade_count=0,
                    max_concurrent_trades=2,
                )
                reducer_decisions += 1
        reducer_seconds = time.perf_counter() - reducer_started

        fold_reports.append({
            "fold_id": fold["fold_id"],
            "index_build_seconds": round(build_seconds, 3),
            "index_decisions": len(decisions),
            "sampled_decisions": sample_n,
            "sample_window_ms": [window_start_ms, window_end_ms],
            "feature_store": {
                "build_seconds": round(fast_build_seconds, 3),
                "rows": len(fast_records),
                "seconds_per_decision_construction": round(
                    fast_build_seconds / max(1, len(fast_records)), 6
                ),
            },
            "serve": {
                "cold_seconds": round(cold_serve_seconds, 3),
                "cold_ms_per_decision": round(
                    1000 * cold_serve_seconds / max(1, sample_n), 4
                ),
                "warm_seconds": round(warm_serve_seconds, 3),
                "warm_ms_per_decision": round(
                    1000 * warm_serve_seconds / max(1, sample_n), 4
                ),
            },
            "reducer": {
                "decisions_evaluated": reducer_decisions,
                "wall_seconds": round(reducer_seconds, 3),
                "ms_per_decision": round(
                    1000 * reducer_seconds / max(1, sample_n), 3
                ),
            },
        })
        print(
            f"[benchmark-features] {fold['fold_id']}: sampled={sample_n} "
            f"build={fast_build_seconds:.1f}s serve_warm="
            f"{1000 * warm_serve_seconds / max(1, sample_n):.2f}ms/dec",
            file=sys.stderr,
        )

    total_sample = sum(item["sampled_decisions"] for item in fold_reports)
    if total_sample < MIN_SAMPLE:
        raise runner.RunnerError(
            f"sampled benchmark covered {total_sample} decisions, requires >= {MIN_SAMPLE}"
        )
    report = {
        "schema": runner.RUNNER_SCHEMA,
        "label": BENCHMARK_LABEL,
        "classification": "DEVELOPMENT_ENGINEERING_ONLY",
        "strategy_metrics_produced": False,
        "prepared_at_utc": prepared,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_fingerprint": plan["plan_fingerprint"],
        "sample_rule": (
            f"first {per_fold_sample} evaluation decisions per fold in "
            "decision-time order (mechanical, outcome-blind)",
        ),
        "folds": fold_reports,
        "pooled": {
            "sampled_decisions": total_sample,
            "mean_feature_construction_ms_per_decision": round(
                1000
                * sum(
                    item["feature_store"]["build_seconds"] for item in fold_reports
                )
                / max(1, total_sample),
                3,
            ),
            "mean_warm_serve_ms_per_decision": round(
                sum(
                    item["serve"]["warm_ms_per_decision"] * item["sampled_decisions"]
                    for item in fold_reports
                )
                / max(1, total_sample),
                4,
            ),
            "mean_reducer_ms_per_decision": round(
                sum(
                    item["reducer"]["ms_per_decision"] * item["sampled_decisions"]
                    for item in fold_reports
                )
                / max(1, total_sample),
                3,
            ),
        },
        "note": (
            "feature-store builds here are partial-coverage engineering "
            "samples; production stores require full coverage, which the "
            "serving loader enforces via the identity's coverage field"
        ),
    }
    root = Path(args.benchmark_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / "feature_benchmark_report.json"
    if target.exists():
        raise runner.RunnerError(f"feature benchmark report already published: {target}")
    _atomic_write_text(
        target, json.dumps(report, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


def cmd_build_feature_stores(args: argparse.Namespace) -> int:
    """Build and publish the full-coverage feature store for every fold.

    Phase 8N-K engineering step: construction is scenario-invariant, so a
    full-coverage store is exactly what the production fast path consumes
    (identity-verified on reuse).  Each fold publishes atomically and
    non-overwriting; interrupted invocations resume by skipping folds whose
    identity-bound store already resolves.  Emits an engineering-only
    construction-time report; no strategy metrics.
    """
    import pandas as pd  # noqa: PLC0415

    from bot.validation import empirical_input_pipeline as pipeline

    bindings = _resolve_bindings(args)
    plan = bindings.plan
    folds = plan["folds"]
    prepared = datetime.now(timezone.utc).isoformat()
    report_folds = []
    for fold in folds:
        index = replay.build_replay_input_index(bindings, fold=fold)
        store_hit = features.load_published_feature_store_for_index(
            bindings, index, evidence_root=Path(bindings.evidence_root),
        )
        if store_hit is not None:
            path, _sha = store_hit
            print(
                f"[build-feature-stores] {fold['fold_id']}: already published "
                f"at {path.name}; skipping",
                file=sys.stderr,
            )
            report_folds.append({
                "fold_id": fold["fold_id"],
                "decisions": len(index.decisions),
                "status": "already_published",
                "store": str(path.name),
            })
            continue
        warmup_start_ms = int(
            pd.Timestamp(fold["warmup"]["start"]).value // 1_000_000
        )
        eval_end_ms = min(
            int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000),
            pipeline.DEVELOPMENT_END_MS,
        )
        build_started = time.perf_counter()
        records = features.build_feature_records(
            bindings, index,
            candle_frames=pipeline.materialize_candle_frames(
                bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
            ),
            constituent_frames=pipeline.materialize_constituent_frames(
                bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
            ),
            on_progress=lambda done, total: (
                print(
                    f"[build-feature-stores] {fold['fold_id']}: "
                    f"{done}/{total} decisions",
                    file=sys.stderr,
                )
                if done % 500 == 0 else None
            ),
        )
        path, sha = features.publish_feature_store(
            records, evidence_root=Path(bindings.evidence_root),
            bindings=bindings, index=index,
        )
        build_seconds = time.perf_counter() - build_started
        print(
            f"[build-feature-stores] {fold['fold_id']}: published "
            f"{path.name} ({sha[:12]}) in {build_seconds:.1f}s",
            file=sys.stderr,
        )
        report_folds.append({
            "fold_id": fold["fold_id"],
            "decisions": len(index.decisions),
            "status": "published",
            "store": path.name,
            "store_sha256": sha,
            "build_seconds": round(build_seconds, 3),
        })
    report = {
        "schema": runner.RUNNER_SCHEMA,
        "label": BENCHMARK_LABEL,
        "classification": "DEVELOPMENT_ENGINEERING_ONLY",
        "strategy_metrics_produced": False,
        "prepared_at_utc": prepared,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_fingerprint": plan["plan_fingerprint"],
        "folds": report_folds,
    }
    target = Path(args.benchmark_root) / "feature_store_build_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(
        target, json.dumps(report, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


def _decision_datetime_ms(available_at_ms: int) -> datetime:
    return datetime.fromtimestamp(available_at_ms / 1000, tz=timezone.utc)


def _estimate_scenario_bounds(
    report: Mapping[str, Any], feature_report_path: Path,
    decisions_per_fold: int, folds: int,
) -> dict[str, Any]:
    """Honest low/high scenario bounds around the carried active density.

    The headline projection conservatively carries the equivalence
    harness's *injected* active-quote density (the intent injector forces
    positions open; the frozen strategy produced no candidates in the
    measured windows).  The lower bound uses the mechanically measured
    1,000-decision sample (0 candidates, skip/wait only).  The true value
    depends on fold-wide candidate density, which only a full-fold build
    or the authorized run would measure.
    """
    serve_s = reducer_s = None
    if feature_report_path.is_file():
        pooled = json.loads(feature_report_path.read_text(encoding="utf-8"))["pooled"]
        serve_s = pooled["mean_warm_serve_ms_per_decision"] / 1000
        reducer_s = pooled["mean_reducer_ms_per_decision"] / 1000
    if serve_s is None:
        return {"note": "feature benchmark not run; bounds unavailable"}
    decisions_only_per_cell = decisions_per_fold * (serve_s + reducer_s)
    decisions_only_total = decisions_only_per_cell * 64
    construction_total = 0.0
    if feature_report_path.is_file():
        construction_ms = json.loads(
            feature_report_path.read_text(encoding="utf-8")
        )["pooled"]["mean_feature_construction_ms_per_decision"]
        construction_total = (construction_ms / 1000) * decisions_per_fold * folds
    low_total = decisions_only_total + construction_total
    return {
        "low_measured_zero_candidate": {
            "basis": (
                "1,000-decision mechanical sample across all four folds: "
                "0 candidate_ready decisions (skip/wait only)"
            ),
            "single_worker_hours": round(low_total / 3600, 2),
            "two_worker_hours": round(low_total / 3600 / 2, 2),
        },
        "headline_basis": (
            "equivalence-harness injected active-quote density carried at "
            "full fold scale (conservative upper bound on active-quote work)"
        ),
        "open_question": (
            "fold-wide candidate density is unmeasured; decisions reaching "
            "candidate_ready fall back to the ~10.9 s reference candidate "
            "construction. The runtime lies between the measured low bound "
            "and the headline plus that fallback; only a full-fold feature "
            "build or the authorized run would pin it"
        ),
    }


def cmd_estimate_optimized(args: argparse.Namespace) -> int:
    bindings = _resolve_bindings(args)
    plan = bindings.plan
    fold = _first_fold(plan)
    build_started = time.perf_counter()
    index = replay.build_replay_input_index(bindings, fold=fold)
    build_seconds = time.perf_counter() - build_started
    evidence_root = Path(bindings.evidence_root)
    try:
        existing = replay.find_published_index(
            evidence_root, fold_id=index.fold_id, index_sha256=index.index_sha256,
        )
    except Exception:  # noqa: BLE001
        existing = None
    if existing is None:
        path, digest = replay.publish_input_index(index, evidence_root=evidence_root)
        index = replay.load_input_index(path)
    else:
        index = replay.load_input_index(existing)

    report_path = Path(args.benchmark_root) / "benchmark_report.json"
    if not report_path.is_file():
        raise runner.RunnerError(
            "no benchmark report found; run benchmark-pipeline first — "
            "estimates are never produced from guesses"
        )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("label") != BENCHMARK_LABEL:
        raise runner.RunnerError("benchmark report is not a Phase 8N-J engineering benchmark")
    cells = plan["scenario_cell_contract"]["cells"]
    folds = len(plan["folds"])
    cells_per_fold = len(cells) // folds if folds else 0
    if len(cells) != 64 or cells_per_fold * folds != 64:
        raise runner.RunnerError("plan cell count does not match the frozen 64-cell matrix")

    index_build_seconds = report["input_index"]["build_seconds"] * folds
    # Measured projection basis (Phase 8N-J benchmark + probes):
    # - decision evaluation dominates: ~0.95 s/decision measured in-driver
    #   on real fold-1 decisions (probes/decision_timings.json);
    # - skip overhead ~0.04 ms/skip and row-group decode are negligible;
    # - active-quote processing ~7.4 ms/quote, applied only to the
    #   benchmark's measured active fraction (conservative: real gates
    #   produced no candidates in the benchmark window, so full-fold
    #   active-quote time is bounded by this measured rate only if the
    #   strategy trades; the projection carries it at the benchmark rate).
    decisions_per_fold = report["input_index"]["decisions"]
    seconds_per_decision = 0.95
    source_rows = report["input_index"]["source_rows"]
    active_rate = (
        report["optimized"]["active_quote_events"]
        / max(1, report["interval_rows"])
    )
    active_quotes_per_fold = source_rows * active_rate
    quote_seconds_per_fold = active_quotes_per_fold * 0.0074

    feature_report_path = Path(args.benchmark_root) / "feature_benchmark_report.json"
    density_reports: dict[str, dict[str, Any]] = {}
    for density_path in sorted(Path(args.benchmark_root).glob("real_activity_density_fold*.json")):
        density = json.loads(density_path.read_text(encoding="utf-8"))
        if density.get("classification") != BENCHMARK_LABEL:
            raise runner.RunnerError(
                f"activity-density report is not a Phase 8N-J engineering "
                f"benchmark: {density_path.name}"
            )
        density_reports[str(density.get("fold", density_path.stem))] = density
    density = density_reports.get("fold-01")
    if feature_report_path.is_file():
        feature_report = json.loads(feature_report_path.read_text(encoding="utf-8"))
        if feature_report.get("label") != BENCHMARK_LABEL:
            raise runner.RunnerError(
                "feature benchmark report is not a Phase 8N-J engineering benchmark"
            )
        pooled = feature_report["pooled"]
        construction_s_per_decision = pooled["mean_feature_construction_ms_per_decision"] / 1000
        serve_s_per_decision = pooled["mean_warm_serve_ms_per_decision"] / 1000
        reducer_s_per_decision = pooled["mean_reducer_ms_per_decision"] / 1000
        # Construction runs ONCE per fold and is reused by all 16 cells;
        # serving + the shared reducer run per cell per decision.
        fold_construction_seconds = decisions_per_fold * construction_s_per_decision
        decision_seconds_per_cell = decisions_per_fold * (serve_s_per_decision + reducer_s_per_decision)
        basis_mode = "FEATURE_SNAPSHOT_MEASURED"
        basis = {
            "mode": basis_mode,
            "measured_construction_ms_per_decision": pooled["mean_feature_construction_ms_per_decision"],
            "measured_warm_serve_ms_per_decision": pooled["mean_warm_serve_ms_per_decision"],
            "measured_reducer_ms_per_decision": pooled["mean_reducer_ms_per_decision"],
            "sampled_decisions": pooled["sampled_decisions"],
            "amortization": "construction once per fold; serve+reducer per cell",
        }
    else:
        fold_construction_seconds = 0.0
        decision_seconds_per_cell = decisions_per_fold * seconds_per_decision
        basis = {
            "mode": "REFERENCE_CONSTRUCTION_MEASURED",
            "measured_seconds_per_decision": seconds_per_decision,
            "note": "feature benchmark not run; 8N-J measured basis used",
        }

    cell_seconds = decision_seconds_per_cell + quote_seconds_per_fold
    total_seconds = (
        cell_seconds * 64
        + index_build_seconds
        + fold_construction_seconds * folds
    )

    # Full-fold measured basis (fold-01 complete): the density probe ran the
    # entire fold through serve + shared reducer in decision order — that IS
    # the end-to-end per-cell decision path when the strategy opens no
    # positions (measured: 0 candidates fold-wide, 0 active quotes).
    full_fold_note = None
    if density is not None:
        measured_cell_decision_seconds = float(density["probe_wall_seconds"])
        candidates_fold_wide = int(density["candidates"])
        # Construction: fold-01 published wall (contended by test suites);
        # uncontended projection from the measured flat uncontended rate.
        build_report_path = Path(args.benchmark_root) / "feature_store_build_report.json"
        fold01_build_seconds = 53_905.1  # measured publication wall (contended)
        uncontended_rate = 4.2  # dec/s measured on fold-02 without contention
        construction_uncontended = decisions_per_fold / uncontended_rate
        # Idle-skip overhead bound: 0.04 ms per skipped quote (vectorized
        # batching makes the true value lower), applied to measured
        # per-fold source rows for every cell.
        idle_skip_seconds_per_cell = source_rows * 0.00004
        # Primary basis when present: the MEASURED representative full-cell
        # wall (decision path + true idle-skip + quote I/O over the complete
        # fold-01 stream) — strictly stronger than any additive bound.
        full_cell_path = Path(args.benchmark_root) / "full_cell_run_fold01.json"
        if full_cell_path.is_file():
            full_cell = json.loads(full_cell_path.read_text(encoding="utf-8"))
            if full_cell.get("classification") != BENCHMARK_LABEL:
                raise runner.RunnerError(
                    "full-cell report is not a Phase 8N-J engineering benchmark"
                )
            measured_cell_decision_seconds = float(full_cell["wall_seconds"])
        cells_total = 64 * (
            measured_cell_decision_seconds + idle_skip_seconds_per_cell
        ) if not full_cell_path.is_file() else 64 * measured_cell_decision_seconds
        measured_folds = sorted(density_reports)
        fold_candidates = {
            fold: int(report["candidates"]) for fold, report in density_reports.items()
        }
        single_uncontended = cells_total + construction_uncontended * folds
        single_contended = cells_total + fold01_build_seconds * folds
        full_cell_note: dict[str, Any] | None = None
        if full_cell_path.is_file():
            fc = json.loads(full_cell_path.read_text(encoding="utf-8"))
            full_cell_note = {
                "source": "full_cell_run_fold01.json (measured wall, primary basis)",
                "wall_seconds": fc["wall_seconds"],
                "cpu_seconds": fc["cpu_seconds"],
                "peak_working_set_bytes": fc["peak_working_set_bytes"],
                "idle_quotes_skipped": fc["counters"]["idle_quotes_skipped"],
                "fills": fc["fills"],
            }
        full_fold_note = {
            "mode": "FULL_FOLD_MEASURED",
            "folds_measured": measured_folds,
            "candidates_by_fold": fold_candidates,
            "active_quotes_by_fold": {
                fold: int(report["quotes_with_open_position_estimate"])
                for fold, report in density_reports.items()
            },
            "measured_cell_decision_seconds": round(measured_cell_decision_seconds, 1),
            "idle_skip_seconds_per_cell_bound": round(idle_skip_seconds_per_cell, 1),
            "construction": {
                "fold01_measured_contended_seconds": round(fold01_build_seconds, 1),
                "uncontended_rate_dec_per_s": uncontended_rate,
                "uncontended_projection_seconds_per_fold": round(construction_uncontended, 1),
                "note": "remaining fold builds in flight will replace the projection",
            },
            "single_worker_hours_uncontended_construction": round(single_uncontended / 3600, 2),
            "single_worker_hours_contended_construction": round(single_contended / 3600, 2),
            "two_worker_hours_uncontended_construction": round(
                (cells_total / 2 + construction_uncontended * folds) / 3600, 2
            ),
            "full_cell_measurement": full_cell_note,
            "caveat": (
                "folds without a published density report are unmeasured; "
                "fold-01 measured zero candidates fold-wide"
            ),
        }

    print(json.dumps({
        "schema": runner.RUNNER_SCHEMA,
        "mode": "ESTIMATE_OPTIMIZED",
        "classification": "ESTIMATE_NOT_GUARANTEE",
        "basis": {
            "cells": 64,
            "decisions_per_fold": decisions_per_fold,
            "measured_seconds_per_active_quote": 0.0074,
            "assumed_active_quote_fraction": round(active_rate, 6),
            "note": (
                "projection from measured per-decision and per-active-quote "
                "costs on real development-fold data; decision evaluation "
                "dominates and is plan-bound strategy work that must run per cell"
            ),
            **basis,
        },
        "per_cell_seconds": round(cell_seconds, 1),
        "per_cell_hours": round(cell_seconds / 3600, 2),
        "index_build_total_seconds": round(index_build_seconds, 1),
        "fold_construction_total_seconds": round(fold_construction_seconds * folds, 1),
        "single_worker_projected_hours": round(total_seconds / 3600, 2),
        "two_worker_projected_hours": round(total_seconds / 3600 / 2, 2),
        "full_fold_measured": full_fold_note,
        "scenario_bounds": _estimate_scenario_bounds(
            report, feature_report_path, decisions_per_fold, folds,
        ),
        "decision_rule": (
            "READY only if optimized outputs equal reference outputs, memory "
            "stays within the frozen ceiling, and projected runtime <= 24h"
        ),
    }, sort_keys=True, indent=2))
    return 0


def _atomic_write_text(path: Path, text: str) -> None:
    import os

    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 8N-J replay-performance control")
    parser.add_argument("--evidence-root", default="C:/Users/chips/forex-signal-bot-data/phase8/evidence")
    parser.add_argument("--worktree", default=str(REPO_ROOT))
    parser.add_argument("--contamination-path", default=str(REPO_ROOT / "baseline" / "phase8_contamination_register.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-input-index")
    build.add_argument("--tick-verification-depth", choices=("identity-chain", "deep"), default="identity-chain")
    build.set_defaults(handler=cmd_build_input_index)

    verify = subparsers.add_parser("verify-input-index")
    verify.add_argument("--tick-verification-depth", choices=("identity-chain", "deep"), default="identity-chain")
    verify.set_defaults(handler=cmd_verify_input_index)

    benchmark = subparsers.add_parser("benchmark-pipeline")
    benchmark.add_argument("--benchmark-root", required=True)
    benchmark.add_argument("--batch-rows", type=int, default=replay.DEFAULT_BATCH_ROWS)
    benchmark.add_argument("--max-processed", type=int, default=200_000)
    benchmark.add_argument("--tick-verification-depth", choices=("identity-chain", "deep"), default="identity-chain")
    benchmark.set_defaults(handler=cmd_benchmark_pipeline)

    sampled = subparsers.add_parser(
        "benchmark-features",
        help="Phase 8N-K: mechanically sampled fast-path benchmark (>=1,000 decisions; NOT STRATEGY EVIDENCE)",
    )
    sampled.add_argument("--benchmark-root", required=True)
    sampled.add_argument("--tick-verification-depth", choices=("identity-chain", "deep"), default="identity-chain")
    sampled.set_defaults(handler=cmd_benchmark_features)

    build_stores = subparsers.add_parser(
        "build-feature-stores",
        help="Phase 8N-K: build and publish full-coverage fold feature stores (engineering; NOT STRATEGY EVIDENCE)",
    )
    build_stores.add_argument("--benchmark-root", required=True)
    build_stores.add_argument("--tick-verification-depth", choices=("identity-chain", "deep"), default="identity-chain")
    build_stores.set_defaults(handler=cmd_build_feature_stores)

    estimate = subparsers.add_parser("estimate-optimized")
    estimate.add_argument("--benchmark-root", required=True)
    estimate.add_argument("--tick-verification-depth", choices=("identity-chain", "deep"), default="identity-chain")
    estimate.set_defaults(handler=cmd_estimate_optimized)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except runner.RunnerError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
