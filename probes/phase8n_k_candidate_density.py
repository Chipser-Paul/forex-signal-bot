"""Phase 8N-K candidate-density probe (engineering measurement, not strategy evidence).

Runs the shared reducer over the sampled feature stores (1,000 mechanically
sampled decisions across all four folds) and counts orchestrator actions.
This measures how many decisions reach ``candidate_ready`` at zero open
trades — the input density the runtime projection needs.  No strategy
outcome, profitability number or acceptance decision is produced.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.strategy.setup_state import StrategyState, record_from_state
from bot.validation import market_feature_store as features

ROOT = Path(
    "C:/Users/chips/forex-signal-bot-data/phase8/engineering_benchmark_8nk"
)
OUT = Path(__file__).resolve().parent / "candidate_density.json"


def main() -> int:
    seed = record_from_state(
        StrategyState(event_time=datetime(2024, 1, 1, tzinfo=timezone.utc)),
        event_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    actions: Counter[str] = Counter()
    rows = 0
    started = time.perf_counter()
    per_fold: dict[str, dict] = {}
    for directory in sorted((ROOT / "market-feature-store").iterdir()):
        if not directory.is_dir():
            continue
        store = features.load_feature_store(directory)
        table = store.table
        fold_actions: Counter[str] = Counter()
        for position in range(table.num_rows):
            row = {
                name: table.column(name)[position].as_py()
                for name in table.column_names
            }
            snapshot = features._snapshot_from_row(row)
            if not snapshot.check_passes:
                fold_actions["check_fail"] += 1
                continue
            if not snapshot.news_context.get("news_clear", False):
                fold_actions["news_blocked"] += 1
                continue
            decision_at = datetime.fromtimestamp(
                int(row["available_at_ms"]) / 1000, tz=timezone.utc
            )
            decision, _record = features.evaluate_orchestration_from_features(
                snapshot,
                decision_at=decision_at,
                prior_state=seed,
                active_trade_count=0,
                max_concurrent_trades=2,
            )
            fold_actions[decision.action] += 1
        per_fold[directory.name] = {
            "rows": int(table.num_rows),
            "actions": dict(fold_actions),
        }
        actions.update(fold_actions)
        rows += int(table.num_rows)
    elapsed = time.perf_counter() - started
    result = {
        "classification": "EMPIRICAL ENGINEERING BENCHMARK - NOT STRATEGY EVIDENCE",
        "rows": rows,
        "elapsed_seconds": round(elapsed, 3),
        "pooled_actions": dict(actions),
        "candidate_fraction_at_zero_positions": (
            actions.get("candidate_ready", 0) / rows if rows else None
        ),
        "per_fold": per_fold,
        "note": (
            "active_trade_count=0 throughout; counts decisions reaching "
            "candidate_ready when the cell is idle — the density the "
            "runtime projection uses for reference-path fallback work"
        ),
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "per_fold"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
