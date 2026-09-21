"""Phase 8N-K full-cell measurement (engineering benchmark, NOT strategy evidence).

Runs the optimized cell driver end-to-end over one complete fold-01
scenario cell — the full quote stream with idle-span skipping, decisions
served from the published full-coverage feature store, no intent
injection — and measures wall/CPU time, skipped quotes, and memory peak.

This is the representative-cell projection input: per-cell decision path
plus true idle-skip cost at fold scale.  Runs inside the engineering
benchmark root (never the empirical output root); no strategy metrics,
profitability, acceptance, or evidence output.
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.validation import market_feature_store as features
from bot.validation import replay_input_index as replay
from backtests.replay_performance_control import BENCHMARK_LABEL, _resolve_bindings

ENGINEERING_ROOT = Path(
    "C:/Users/chips/forex-signal-bot-data/phase8/engineering_benchmark_8nk"
)


def peak_working_set_bytes() -> int:
    class PMC(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    psapi = ctypes.windll.psapi
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
        return 0
    return int(pmc.PeakWorkingSetSize)


def main() -> int:
    from bot.validation import empirical_input_pipeline as pipeline

    class _Args:
        evidence_root = "C:/Users/chips/forex-signal-bot-data/phase8/evidence"
        worktree = str(Path(__file__).resolve().parents[1])
        contamination_path = str(
            Path(__file__).resolve().parents[1]
            / "baseline" / "phase8_contamination_register.json"
        )
        tick_verification_depth = "identity-chain"

    bindings = _resolve_bindings(_Args())
    plan = bindings.plan
    fold = plan["folds"][0]
    cell = plan["scenario_cell_contract"]["cells"][0]  # first cell of fold-01

    index = replay.build_replay_input_index(bindings, fold=fold)
    store_hit = features.load_published_feature_store_for_index(
        bindings, index, evidence_root=bindings.evidence_root,
    )
    if store_hit is None:
        raise SystemExit("fold-01 full-coverage feature store not published yet")
    store_path, _sha = store_hit
    store = features.load_feature_store(store_path)

    scenario = None
    for candidate in plan["scenario_cell_contract"]["cells"]:
        if candidate["cell_id"] == cell["cell_id"]:
            from bot.validation.development_evaluation_runner import scenario_for_cell
            scenario = scenario_for_cell(plan, candidate)
            break

    cell_dir = ENGINEERING_ROOT / "full_cell" / cell["cell_id"]
    context = pipeline.CellExecutionContext(
        cell=cell, fold=fold, scenario=scenario, bindings=bindings,
        cell_dir=cell_dir,
    )
    from bot.validation.development_evaluation_runner import pd_ts

    warmup_start_ms = int(pd_ts(fold["warmup"]["start"]).value // 1_000_000)
    eval_end_ms = min(
        int(pd_ts(fold["evaluation"]["end"]).value // 1_000_000),
        pipeline.DEVELOPMENT_END_MS,
    )
    handler = pipeline.CellEventHandler(
        context,
        candle_frames=pipeline.materialize_candle_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        ),
        constituent_frames=pipeline.materialize_constituent_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        ),
    )
    handler.feature_provider = features.FoldFeatureProvider(store, index=index)

    driver = replay.OptimizedCellDriver(context, handler, index=index)
    counters: dict[str, int] = {}
    cpu0 = time.process_time()
    started = time.perf_counter()
    driver.run(checkpoint_every=0, counters=counters, finish=True)
    wall = time.perf_counter() - started
    cpu = time.process_time() - cpu0

    result = {
        "classification": BENCHMARK_LABEL,
        "cell_id": cell["cell_id"],
        "fold": fold["fold_id"],
        "store": store_path.name,
        "counters": dict(counters),
        "decisions": len(context.decisions),
        "fills": len(context.engine.fills),
        "rejections": len(context.rejections),
        "wall_seconds": round(wall, 1),
        "cpu_seconds": round(cpu, 1),
        "peak_working_set_bytes": peak_working_set_bytes(),
        "note": (
            "representative full-cell measurement: optimized driver over the "
            "complete fold-01 quote stream with memoized feature serving; "
            "input for the 64-cell runtime projection only"
        ),
    }
    out = ENGINEERING_ROOT / "full_cell_run_fold01.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
