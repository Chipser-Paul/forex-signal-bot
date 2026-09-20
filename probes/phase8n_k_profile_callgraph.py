"""Phase 8N-K decision-path call-graph profile (engineering, not strategy evidence).

cProfile over a bounded optimized-driver run without the intent injector
(every quote skipped), so the profile isolates the per-decision path:
acquisition callbacks, analyzers, reducer, persistence.  Emits a per-
function cost table grouped by stage, with call counts.
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

STAGES = {
    "causal_snapshots": ("causal_snapshot",),
    "frame_copy": ("copy",),
    "bias": ("bias_snapshot_from_frames", "resolve_trade_bias"),
    "liquidity": ("build_liquidity_map_from_frames", "detect_liquidity_sweep"),
    "structure": ("analyze_market_structure", "detect_displacement"),
    "fvg": ("detect_fvg", "detect_fair_value_gap"),
    "premium_discount": ("premium_discount", "premium_discount_zone"),
    "atr": ("atr", "average_true_range", "compute_atr"),
    "dxy": ("prepare_dxy_context", "analyze_dxy"),
    "news_session": ("news_context_for", "get_session_context"),
    "gate_inputs": ("build_gate_inputs",),
    "reducer": ("evaluate_symbol", "evaluate_strategy_gates", "evaluate_gates"),
    "persistence": ("_publish_decision", "publish_decision", "mutate"),
    "serialization": ("json.dumps", "canonical", "canonical_data"),
}


def main() -> int:
    import pandas as pd

    out_path = Path(__file__).with_name("phase8n_k_callgraph.json")

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
        cell_dir=Path(__file__).parent / "_k_profile_cell",
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
        batch_rows=200_000, max_processed=10, finish=False,
    )
    profiler.disable()
    wall = time.perf_counter() - started

    stats = pstats.Stats(profiler)
    top = []
    for func, (cc, nc, tt, ct, callers) in sorted(
        stats.stats.items(), key=lambda item: -item[1][3],
    )[:80]:
        top.append({
            "file": func[0], "line": func[1], "name": func[2],
            "primitive_calls": cc, "calls": nc,
            "tottime_s": round(tt, 4), "cumtime_s": round(ct, 4),
        })
    # caller map for the hottest reducers/analyzers (caller values are
    # (cc, nc, tt, ct) tuples in this Python version)
    callers_of = {}
    for func, (cc, nc, tt, ct, callers) in stats.stats.items():
        if ct > 0.05 and callers:
            callers_of[f"{func[0].split('/')[-1]}:{func[2]}"] = {
                f"{caller[0].split('/')[-1]}:{caller[2]}": round(cval[3], 4)
                for caller, cval in sorted(
                    callers.items(), key=lambda kv: -kv[1][3],
                )[:6]
            }
    out_path.write_text(json.dumps({
        "label": "EMPIRICAL ENGINEERING BENCHMARK — NOT STRATEGY EVIDENCE",
        "wall_seconds": round(wall, 2),
        "counters": dict(counters),
        "decisions_profiled": counters.get("decisions_processed", 0),
        "top_by_cumtime": top,
        "callers": callers_of,
    }, indent=2), encoding="utf-8")
    print(json.dumps({
        "wall_seconds": round(wall, 2),
        "decisions": counters.get("decisions_processed", 0),
        "top15": [
            f"{Path(r['file']).name}:{r['name']} cum={r['cumtime_s']} tot={r['tottime_s']} n={r['calls']}"
            for r in top[:15]
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
