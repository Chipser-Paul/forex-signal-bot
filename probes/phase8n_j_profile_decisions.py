"""Phase 8N-J decision-cost profile (engineering measurement, not strategy evidence).

cProfile over a small bounded optimized-driver run without the intent
injector: every quote is skipped, so the profile isolates decision
evaluation + skip overhead. Results are written to a file so the
measurement survives even if the driving console is interrupted.
"""

from __future__ import annotations

import cProfile
import json
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtests.replay_performance_control import (  # noqa: E402
    _benchmark_cell,
    _benchmark_interval,
    _resolve_bindings,
)
from bot.validation import empirical_input_pipeline as pipeline  # noqa: E402
from bot.validation import replay_input_index as replay  # noqa: E402


def main() -> int:
    import pandas as pd

    out_path = Path(__file__).with_name("decision_profile.json")

    bindings = _resolve_bindings(type("Args", (), {
        "tick_verification_depth": "identity-chain",
        "evidence_root": r"C:/Users/chips/forex-signal-bot-data/phase8/evidence",
        "worktree": r"C:/Users/chips/forex-signal-bot-phase8",
        "contamination_path": r"C:/Users/chips/forex-signal-bot-phase8/baseline/phase8_contamination_register.json",
    })())
    plan = bindings.plan
    fold, _s, _e = _benchmark_interval(plan)
    cell = _benchmark_cell(plan, fold)
    ws = int(pd.Timestamp(fold["warmup"]["start"]).value // 1_000_000)
    ee = int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000)
    cf = pipeline.materialize_candle_frames(bindings, start_ms=ws, end_ms=ee)
    cons = pipeline.materialize_constituent_frames(bindings, start_ms=ws, end_ms=ee)
    index = replay.build_replay_input_index(bindings, fold=fold)

    context = pipeline.CellExecutionContext(
        cell=cell, fold=fold, scenario=cell["scenario"], bindings=bindings,
        cell_dir=Path(__file__).parent / "_profile_cell",
    )
    handler = pipeline.CellEventHandler(
        context, candle_frames=cf, constituent_frames=cons,
    )
    driver = replay.OptimizedCellDriver(context, handler, index=index)
    counters: dict[str, int] = {}
    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.enable()
    driver.run(
        checkpoint_every=0, counters=counters,
        batch_rows=200_000, max_processed=20, finish=False,
    )
    profiler.disable()
    wall = time.perf_counter() - started

    import pstats as _pstats  # noqa: PLC0415
    stats = _pstats.Stats(profiler)
    rows = []
    for func, (cc, nc, tt, ct, callers) in sorted(
        stats.stats.items(), key=lambda item: -item[1][3],
    )[:40]:
        rows.append({
            "file": func[0], "line": func[1], "name": func[2],
            "ncalls": nc, "tottime": round(tt, 4), "cumtime": round(ct, 4),
        })
    out_path.write_text(json.dumps({
        "label": "EMPIRICAL ENGINEERING BENCHMARK — NOT STRATEGY EVIDENCE",
        "wall_seconds": round(wall, 2),
        "counters": dict(counters),
        "top_by_cumtime": rows,
    }, indent=2), encoding="utf-8")
    print(json.dumps({
        "wall_seconds": round(wall, 2),
        "counters": {k: counters[k] for k in (
            "decisions_processed", "idle_quotes_skipped", "idle_spans",
        )},
        "top": [
            f"{row['name']} ({Path(row['file']).name}:{row['line']}) "
            f"cum={row['cumtime']}s tot={row['tottime']}s ncalls={row['ncalls']}"
            for row in rows[:15]
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
