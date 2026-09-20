"""Phase 8N-J decision-cost probe (engineering measurement, not strategy evidence).

Runs the optimized driver WITHOUT the intent injector so every quote is
skipped and the measured cost is decision evaluation + skip overhead.
Two caps separate the per-decision cost from the per-skip overhead.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtests.replay_performance_control import (  # noqa: E402
    _benchmark_cell,
    _benchmark_interval,
    _peak_working_set_bytes,
    _resolve_bindings,
)
from bot.validation import development_evaluation_runner as runner  # noqa: E402
from bot.validation import empirical_input_pipeline as pipeline  # noqa: E402
from bot.validation import replay_input_index as replay  # noqa: E402


def main() -> int:
    import pandas as pd

    bindings = _resolve_bindings(type("Args", (), {
        "tick_verification_depth": "identity-chain",
        "evidence_root": r"C:/Users/chips/forex-signal-bot-data/phase8/evidence",
        "worktree": r"C:/Users/chips/forex-signal-bot-phase8",
        "contamination_path": r"C:/Users/chips/forex-signal-bot-phase8/baseline/phase8_contamination_register.json",
    })())
    plan = bindings.plan
    fold, bench_start_ms, bench_end_ms = _benchmark_interval(plan)
    cell = _benchmark_cell(plan, fold)

    warmup_start_ms = int(pd.Timestamp(fold["warmup"]["start"]).value // 1_000_000)
    eval_end_ms = int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000)
    candle_frames = pipeline.materialize_candle_frames(
        bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
    )
    constituent_frames = pipeline.materialize_constituent_frames(
        bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
    )

    build_started = time.perf_counter()
    index = replay.build_replay_input_index(bindings, fold=fold)
    build_seconds = time.perf_counter() - build_started

    results = {}
    for cap in (1000, 6000):
        context = pipeline.CellExecutionContext(
            cell=cell, fold=fold, scenario=cell["scenario"], bindings=bindings,
            cell_dir=Path("_probe_cell") / f"cap{cap}",
        )
        handler = pipeline.CellEventHandler(
            context, candle_frames=candle_frames, constituent_frames=constituent_frames,
        )
        driver = replay.OptimizedCellDriver(context, handler, index=index)
        counters: dict[str, int] = {}
        cpu0 = time.process_time()
        started = time.perf_counter()
        driver.run(
            checkpoint_every=0, counters=counters,
            batch_rows=200_000, max_processed=cap, finish=False,
        )
        wall = time.perf_counter() - started
        cpu = time.process_time() - cpu0
        results[cap] = {
            "wall_seconds": round(wall, 2),
            "cpu_seconds": round(cpu, 2),
            "decisions_processed": counters["decisions_processed"],
            "idle_quotes_skipped": counters["idle_quotes_skipped"],
            "idle_spans": counters["idle_spans"],
            "last_event_ts_ms": counters["last_event_ts_ms"],
        }

    r1, r2 = results[1000], results[6000]
    extra_decisions = r2["decisions_processed"] - r1["decisions_processed"]
    extra_wall = r2["wall_seconds"] - r1["wall_seconds"]
    extra_skips = r2["idle_quotes_skipped"] - r1["idle_quotes_skipped"]
    summary = {
        "label": "EMPIRICAL ENGINEERING BENCHMARK — NOT STRATEGY EVIDENCE",
        "index_build_seconds": round(build_seconds, 2),
        "index_decisions": len(index.decisions),
        "runs": results,
        "derived": {
            "wall_per_decision_ms": round(1000 * extra_wall / extra_decisions, 2) if extra_decisions else None,
            "cpu_per_decision_ms": round(1000 * extra_cpu_ms / 1000 / max(1, extra_decisions), 2) if extra_decisions else None,
            "extra_wall_seconds": round(extra_wall, 2),
            "extra_decisions": extra_decisions,
            "extra_skips": extra_skips,
        },
        "peak_working_set_bytes": _peak_working_set_bytes(),
    }
    print(json.dumps(summary, indent=2))
    Path("_probe_decision_cost.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
