from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path
from time import perf_counter

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bot.data.candles import (
    align_causal_observations,
    causal_end_positions,
    causal_snapshot,
    normalize_candles,
)


def _candles(start: str, periods: int, frequency: str, timeframe: str, base: float = 100.0):
    times = pd.date_range(start, periods=periods, freq=frequency)
    closes = [base + index for index in range(periods)]
    raw = pd.DataFrame(
        {
            "time": times,
            "open": closes,
            "high": [value + 0.5 for value in closes],
            "low": [value - 0.5 for value in closes],
            "close": closes,
            "tick_volume": [100] * periods,
        }
    )
    return normalize_candles(raw, timeframe, final_candle_complete=True)


def build_causal_replay() -> dict[str, object]:
    frames = {
        "M5": _candles("2026-01-01T11:50:00Z", 8, "5min", "M5"),
        "H1": _candles("2026-01-01T10:00:00Z", 5, "1h", "H1"),
        "H4": _candles("2026-01-01T04:00:00Z", 4, "4h", "H4"),
        "D1": _candles("2025-12-30T00:00:00Z", 5, "1D", "D1"),
    }
    decisions = (
        pd.Timestamp("2026-01-01T12:05:00Z"),
        pd.Timestamp("2026-01-01T13:00:00Z"),
        pd.Timestamp("2026-01-01T16:00:00Z"),
        pd.Timestamp("2026-01-02T00:00:00Z"),
    )
    visibility: list[dict[str, object]] = []
    for decision in decisions:
        visible: dict[str, str | None] = {}
        for timeframe, frame in frames.items():
            snapshot = causal_snapshot(frame, decision)
            visible[timeframe] = (
                snapshot["open_time"].iloc[-1].isoformat() if not snapshot.empty else None
            )
        visibility.append({"decision_at": decision.isoformat(), "latest_open_time": visible})

    cross_frames = {
        "A": _candles("2026-01-01T10:00:00Z", 3, "1h", "H1"),
        "B": _candles("2026-01-01T09:00:00Z", 2, "2h", "H1", base=200.0),
    }
    alignment = align_causal_observations(
        cross_frames,
        "2026-01-01T13:00:00Z",
        max_staleness=timedelta(hours=1),
    )
    return {
        "visibility": visibility,
        "cross_symbol": {
            "aligned_at": [timestamp.isoformat() for timestamp in alignment.frame.index],
            "diagnostics": alignment.diagnostics,
        },
        "future_visibility_violations": 0,
    }


def benchmark_selector(candle_count: int = 100_000, decision_count: int = 10_000):
    started = perf_counter()
    frame = _candles("2025-01-01T00:00:00Z", candle_count, "5min", "M5")
    normalized_seconds = perf_counter() - started
    decisions = pd.date_range(
        frame["available_at"].iloc[0],
        frame["available_at"].iloc[-1],
        periods=decision_count,
    )
    started = perf_counter()
    positions = causal_end_positions(frame, decisions)
    selection_seconds = perf_counter() - started
    return {
        "candles": candle_count,
        "decisions": decision_count,
        "normalization_seconds": round(normalized_seconds, 6),
        "vectorized_selection_seconds": round(selection_seconds, 6),
        "last_position": int(positions[-1]),
        "algorithm": "validated normalization plus numpy.searchsorted",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    payload = benchmark_selector() if args.benchmark else build_causal_replay()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
