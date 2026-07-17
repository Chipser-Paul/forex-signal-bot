from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import MetaTrader5 as mt5  # pyright: ignore[reportMissingImports]
import pandas as pd  # pyright: ignore[reportMissingModuleSource]


TIMEFRAME_MAP: dict[str, int] = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
}


@dataclass(frozen=True)
class MarketDataRequest:
    symbol: str
    timeframe: str
    bars: int = 500


def normalize_rates_frame(rates) -> pd.DataFrame | None:
    """Normalize raw MT5 rates into a consistent OHLCV dataframe."""
    if rates is None:
        return None

    df = pd.DataFrame(rates)
    if df.empty:
        return None

    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

    expected = ["time", "open", "high", "low", "close", "tick_volume"]
    for col in expected:
        if col not in df.columns:
            df[col] = None

    return df


def get_mt5_timeframe(timeframe: str) -> int:
    try:
        return TIMEFRAME_MAP[timeframe.upper()]
    except KeyError as exc:
        raise ValueError(f"Unsupported timeframe: {timeframe}") from exc


def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    bars: int = 500,
    *,
    include_current: bool = False,
) -> pd.DataFrame | None:
    """Fetch OHLCV data from MT5 with a stable normalized output shape.

    By default, strategy code reads only fully closed candles. MT5 position 0 is
    the still-forming candle, which can create live signals that never exist in
    a completed-candle backtest.
    """
    mt5_timeframe = get_mt5_timeframe(timeframe)
    start_pos = 0 if include_current else 1
    rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, start_pos, int(bars))
    return normalize_rates_frame(rates)


def fetch_batch(requests: Iterable[MarketDataRequest]) -> dict[tuple[str, str], pd.DataFrame | None]:
    """Fetch multiple symbol/timeframe datasets in one pass-friendly helper."""
    results: dict[tuple[str, str], pd.DataFrame | None] = {}
    for req in requests:
        results[(req.symbol, req.timeframe)] = fetch_ohlcv(
            req.symbol,
            req.timeframe,
            bars=req.bars,
        )
    return results
