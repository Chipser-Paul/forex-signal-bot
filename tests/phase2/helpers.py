from __future__ import annotations

import pandas as pd

from bot.data.candles import normalize_candles


def raw_candles(
    start: str,
    periods: int,
    frequency: str,
    *,
    base: float = 100.0,
) -> pd.DataFrame:
    open_times = pd.date_range(start, periods=periods, freq=frequency)
    closes = [base + index for index in range(periods)]
    return pd.DataFrame(
        {
            "time": open_times,
            "open": closes,
            "high": [value + 0.5 for value in closes],
            "low": [value - 0.5 for value in closes],
            "close": closes,
            "tick_volume": [100] * periods,
        }
    )


def normalized_candles(
    start: str,
    periods: int,
    frequency: str,
    timeframe: str,
    *,
    base: float = 100.0,
    final_candle_complete: bool = True,
):
    return normalize_candles(
        raw_candles(start, periods, frequency, base=base),
        timeframe,
        final_candle_complete=final_candle_complete,
    )
