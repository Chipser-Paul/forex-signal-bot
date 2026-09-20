"""Phase 8N-K real-strategy activity-density probe (engineering measurement,
NOT strategy evidence).

Sequentially serves every decision of a fold from the published feature
store, runs the shared reducer with chained setup state exactly like the
pipeline, and when the frozen reducer emits ``candidate_ready``:
  1. builds trade levels / entry intent through the frozen constructors;
  2. determines fill vs rejection from causal M1 quotes in decision order
     (certain ordering, identical semantics to the driver's decision path);
  3. if filled, bounds entry-to-exit by candle-touch detection over the
     position lifetime (M1 extrema bound tick extrema, so every counted
     touch is a real touch; misses only widen the bound);
  4. charges frozen execution costs and adds the exit P&L to balance.

Produces only an activity-density and runtime measurement for the 8N-K
runtime projection. No strategy metrics, acceptance, or evidence output.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from bot.validation import market_feature_store as features
from bot.validation import replay_input_index as replay
from bot.validation.empirical_input_pipeline import (
    DEVELOPMENT_END_MS,
    FROZEN_MIN_RR,
    materialize_candle_frames,
)
from bot.validation.empirical_strategy_adapter import evaluate_setup_inputs
from bot.validation.replay_input_index import latest_quote_at_or_before
from bot.strategy.setup_intent import SetupSymbolMetadata
from bot.strategy.setup_state import StrategyState, record_from_state

EVIDENCE_ROOT = Path("C:/Users/chips/forex-signal-bot-data/phase8/evidence")
ENGINEERING_ROOT = Path(
    "C:/Users/chips/forex-signal-bot-data/phase8/engineering_benchmark_8nk"
)


def resolve_bindings():
    from backtests.replay_performance_control import _resolve_bindings as resolve

    class _Args:
        evidence_root = str(EVIDENCE_ROOT)
        worktree = str(Path(__file__).resolve().parents[1])
        contamination_path = str(
            Path(__file__).resolve().parents[1]
            / "baseline" / "phase8_contamination_register.json"
        )
        tick_verification_depth = "identity-chain"

    return resolve(_Args())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fold", required=True)
    parser.add_argument(
        "--out", default=str(Path(__file__).parent / "real_activity_density.json")
    )
    args = parser.parse_args()

    import pyarrow.parquet as pq

    from bot.execution.lifecycle.serialization import entry_intent_from_payload
    from bot.validation.replay_input_index import QuoteCursor

    bindings = resolve_bindings()
    plan = bindings.plan
    fold = next(f for f in plan["folds"] if f["fold_id"] == args.fold)
    index = replay.build_replay_input_index(bindings, fold=fold)
    store_hit = features.load_published_feature_store_for_index(
        bindings, index, evidence_root=EVIDENCE_ROOT,
    )
    if store_hit is None:
        raise SystemExit(
            f"no published full-coverage feature store for {args.fold}; "
            "run build-feature-stores first"
        )
    store_path, _sha = store_hit
    store = features.load_feature_store(store_path)

    eval_start_ms = int(pd.Timestamp(fold["evaluation"]["start"]).value // 1_000_000)
    warmup_start_ms = int(pd.Timestamp(fold["warmup"]["start"]).value // 1_000_000)
    eval_end_ms = min(
        int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000),
        DEVELOPMENT_END_MS,
    )

    # Tick row-group registry (monthly partitions, time_msc min/max per row
    # group) for exact-touch scans over the accepted raw tick data.
    tick_row_groups: list[tuple[str, int, int, int]] = []  # path, rg, min_ms, max_ms
    for monthly in bindings.monthly_roots:
        for part in sorted(monthly.rglob("part-*.parquet")):
            pf = pq.ParquetFile(part)
            for rg in range(pf.num_row_groups):
                stats = pf.metadata.row_group(rg).column(4).statistics  # time_msc
                if stats is None or stats.min is None:
                    raise SystemExit(f"missing time_msc statistics: {part.name} rg{rg}")
                tick_row_groups.append((str(part), rg, int(stats.min), int(stats.max)))
    tick_row_groups.sort(key=lambda item: (item[2], item[0], item[1]))

    def scan_touch(entry_ms: int, side: str, stop: float, target: float):
        """First touch of stop/target in accepted tick order (exact rows).

        Bound discipline: min(bid,ask)/max(bid,ask) tests can only trigger
        earlier than the exact bid/ask-side rules, so counted activity is an
        upper bound on true position-active quote processing.
        """
        import numpy as np

        rows_scanned = 0
        for path, rg, rg_min, rg_max in tick_row_groups:
            if rg_max < entry_ms:
                continue
            table = pq.ParquetFile(path).read_row_group(
                rg, columns=["time_msc", "bid", "ask"]
            )
            times = table.column("time_msc").to_numpy()
            bid = table.column("bid").to_numpy()
            ask = table.column("ask").to_numpy()
            mask = times >= entry_ms if rows_scanned == 0 else np.ones(len(times), dtype=bool)
            times = times[mask]
            bid = bid[mask]
            ask = ask[mask]
            if len(times) == 0:
                continue
            low = np.minimum(bid, ask)
            high = np.maximum(bid, ask)
            if side == "long":
                stop_hits = np.nonzero(low <= stop)[0]
                target_hits = np.nonzero(high >= target)[0]
            else:
                stop_hits = np.nonzero(high >= stop)[0]
                target_hits = np.nonzero(low <= target)[0]
            stop_i = int(stop_hits[0]) if len(stop_hits) else None
            target_i = int(target_hits[0]) if len(target_hits) else None
            if stop_i is not None and (target_i is None or stop_i <= target_i):
                return rows_scanned + stop_i + 1, rows_scanned + stop_i, "stop", int(times[stop_i])
            if target_i is not None:
                return rows_scanned + target_i + 1, rows_scanned + target_i, "target", int(times[target_i])
            rows_scanned += len(times)
            if rg_max >= eval_end_ms:
                break
        return rows_scanned, rows_scanned, "fold_end", eval_end_ms

    table = store.table
    cols = {name: table.column(name) for name in table.column_names}

    from bot.execution.risk.models import RiskPolicy  # noqa: F401  (frozen policy source)
    from bot.strategy.config import StrategyConfig

    config = StrategyConfig()
    metadata = SetupSymbolMetadata(
        "XAUUSDm", 0.001, 10, 3,
        datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, tzinfo=timezone.utc),
        "phase8n-development-proxy",
    )
    max_concurrent = 2
    state_record = record_from_state(
        StrategyState(event_time=datetime(2024, 1, 1, tzinfo=timezone.utc)),
        event_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    import numpy as np

    counts: Counter[str] = Counter()
    candidates = 0
    filled = 0
    quotes_with_open_position = 0
    entry_to_exit_seconds = []
    per_reason: Counter[str] = Counter()
    started = time.perf_counter()

    positions_open = 0
    for position in range(table.num_rows):
        avail_ms = int(cols["available_at_ms"][position].as_py())
        identity = str(cols["identity"][position].as_py())
        snapshot = features._snapshot_from_row({
            name: cols[name][position].as_py() for name in table.column_names
        })
        counts["decisions"] += 1
        if not snapshot.check_passes:
            counts["check_fail"] += 1
            continue
        if not snapshot.news_context.get("news_clear", False):
            counts["news_blocked"] += 1
            continue
        decision_at = datetime.fromtimestamp(avail_ms / 1000, tz=timezone.utc)
        decision, record = features.evaluate_orchestration_from_features(
            snapshot,
            decision_at=decision_at,
            prior_state=state_record,
            active_trade_count=positions_open,
            max_concurrent_trades=max_concurrent,
        )
        if record is not None:
            state_record = record
        action = decision.action
        counts[f"action_{action}"] += 1
        if action != "candidate_ready" or positions_open >= max_concurrent:
            if action == "candidate_ready":
                counts["candidate_skipped_position_cap"] += 1
            continue
        candidates += 1
        # Frozen level/intent construction from the memoized inputs.
        inputs = snapshot.strategy_evaluation_inputs()
        evaluated = evaluate_setup_inputs(
            state_record, inputs, config,
            metadata=metadata, min_rr=FROZEN_MIN_RR, partial_close_fraction=0.5,
        )
        if evaluated.intent_json is None:
            counts["no_intent"] += 1
            continue
        intent = entry_intent_from_payload(json.loads(evaluated.intent_json))
        # Certain-order entry resolution: last quote at/before the decision.
        quote = latest_quote_at_or_before(index, avail_ms)
        if quote is None:
            counts["no_quote"] += 1
            continue
        ask = float(quote["ask"])
        bid = float(quote["bid"])
        side = str(intent.side)
        if side == "long":
            if ask > float(intent.entry_price):
                counts["rejected_market_beyond_entry"] += 1
                continue
            stop = float(intent.stop_price)
            target = float(intent.target_price)
        else:
            if bid < float(intent.entry_price):
                counts["rejected_market_beyond_entry"] += 1
                continue
            stop = float(intent.stop_price)
            target = float(intent.target_price)
        counts["filled"] += 1
        filled += 1
        positions_open += 1
        # Exact first-touch resolution over accepted tick rows (bound
        # discipline: min/max tests trigger at least as early as exact
        # side rules; counted activity is an upper bound).
        scanned, active_quotes, exit_kind, exit_ms = scan_touch(
            avail_ms, side, stop, target
        )
        duration_s = (exit_ms - avail_ms) / 1000
        entry_to_exit_seconds.append(duration_s)
        quotes_with_open_position += active_quotes
        per_reason[exit_kind] += 1
        # Exit P&L from the frozen cost shape: spread cost at entry plus
        # stop/target movement in points (projection-only; never evidence).
        spread_cost = (ask - bid) * 1.0  # USD per point on the frozen contract
        pnl = (
            (target - float(intent.entry_price)) - spread_cost
            if exit_kind == "target"
            else (stop - float(intent.entry_price)) - spread_cost
        )
        if state_record is not None:
            counts["balance_delta_usd_sum"] = counts.get("balance_delta_usd_sum", 0) + round(pnl, 2)
        # Positions close at first touch in this bounding model; the
        # projection is bounds-only, so no overlap handling is required.
        positions_open -= 1
    elapsed = time.perf_counter() - started
    result = {
        "classification": "EMPIRICAL ENGINEERING BENCHMARK — NOT STRATEGY EVIDENCE",
        "fold": args.fold,
        "decisions": counts["decisions"],
        "candidates": candidates,
        "filled": filled,
        "actions": {k: v for k, v in counts.items() if k.startswith("action_")},
        "candidate_reasons": {
            k: v for k, v in counts.items() if k not in ("decisions",)
            and not k.startswith("action_")
        },
        "quotes_with_open_position_estimate": quotes_with_open_position,
        "mean_entry_to_exit_seconds": (
            round(sum(entry_to_exit_seconds) / len(entry_to_exit_seconds), 1)
            if entry_to_exit_seconds else None
        ),
        "max_entry_to_exit_seconds": (
            max(entry_to_exit_seconds) if entry_to_exit_seconds else None
        ),
        "probe_wall_seconds": round(elapsed, 1),
        "note": (
            "fill ordering certain (quotes read in decision order); exits "
            "resolved by exact first-touch over accepted tick rows with "
            "min/max bound discipline. Activity density input for the "
            "8N-K runtime projection only."
        ),
    }
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
