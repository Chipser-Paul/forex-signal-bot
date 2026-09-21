from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import MetaTrader5 as mt5  # pyright: ignore[reportMissingImports]
import pandas as pd  # pyright: ignore[reportMissingModuleSource]

from bot.data.candles import (
    CandleDataError,
    TIMEFRAMES,
    causal_snapshot,
    get_timeframe_spec,
    normalize_candles,
)

TIMEFRAME_MAP: dict[str, int] = {
    name: getattr(mt5, spec.mt5_attribute) for name, spec in TIMEFRAMES.items()
}


@dataclass(frozen=True)
class MarketDataRequest:
    symbol: str
    timeframe: str
    bars: int = 500


def normalize_rates_frame(
    rates,
    timeframe: str = "M5",
    *,
    final_candle_complete: bool = False,
) -> pd.DataFrame | None:
    """Normalize raw MT5 rates using the shared causal candle contract."""
    if rates is None:
        return None
    if len(rates) == 0:
        return None
    frame = normalize_candles(
        rates,
        timeframe,
        final_candle_complete=final_candle_complete,
    )
    return frame if not frame.empty else None


def get_mt5_timeframe(timeframe: str) -> int:
    spec = get_timeframe_spec(timeframe)
    try:
        return TIMEFRAME_MAP[spec.name]
    except (AttributeError, KeyError) as exc:
        raise CandleDataError(f"MT5 does not support timeframe: {spec.name}") from exc


def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    bars: int = 500,
    *,
    include_current: bool = False,
    decision_timestamp: object | None = None,
) -> pd.DataFrame | None:
    """Fetch OHLCV data from MT5 with a stable normalized output shape.

    By default, strategy code reads only fully closed candles. MT5 position 0 is
    the still-forming candle, which can create live signals that never exist in
    a completed-candle backtest.
    """
    if int(bars) <= 0:
        raise CandleDataError("bars must be positive")
    spec = get_timeframe_spec(timeframe)
    mt5_timeframe = get_mt5_timeframe(spec.name)
    start_pos = 0 if include_current else 1
    rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, start_pos, int(bars))
    frame = normalize_rates_frame(
        rates,
        spec.name,
        final_candle_complete=not include_current,
    )
    if frame is None:
        return None

    decision = decision_timestamp or datetime.now(timezone.utc)
    snapshot = causal_snapshot(frame, decision, max_bars=int(bars))
    return snapshot if not snapshot.empty else None


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
