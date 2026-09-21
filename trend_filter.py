# trend_filter.py – Updated with Dynamic Slope + Crossover Boost

import pandas as pd # pyright: ignore[reportMissingModuleSource]
import numpy as np # pyright: ignore[reportMissingImports]

# Constants
LONG_EMA = 200
SHORT_EMA = 50
ATR_LEN = 14
BASE_SLOPE_THR = 0.00005  # Dynamic, based on ATR/price ratio

def detect_trend(df: pd.DataFrame) -> tuple[str, int]:
    """
    Detects trend direction and confidence level.

    Returns:
        trend (str): 'up', 'down', or 'sideways'
        confidence (int): from 0 (no confidence) to 5 (very confident)
    """
    if df is None or len(df) < LONG_EMA + 5:
        return "sideways", 0

    close = df["close"]
    high = df["high"]
    low = df["low"]

    ema_short = close.ewm(span=SHORT_EMA).mean()
    ema_long = close.ewm(span=LONG_EMA).mean()
    atr = (high - low).rolling(ATR_LEN).mean()

    # Dynamic slope threshold
    atr_val = atr.iloc[-1]
    avg_price = close.mean()
    dynamic_slope_thr = BASE_SLOPE_THR * (atr_val / avg_price) * 100

    # Slope over last 3 bars
    slope = ema_short.iloc[-1] - ema_short.iloc[-3]
    slope_pct = slope / close.iloc[-1]

    # Initial trend direction
    direction = "up" if slope > 0 else "down"

    # Filter sideways
    if abs(slope_pct) < dynamic_slope_thr or atr_val < avg_price * 0.0005:
        return "sideways", 0

    # EMA crossover boost
    ema_cross_boost = 1 if (
        (direction == "up" and ema_short.iloc[-1] > ema_long.iloc[-1]) or
        (direction == "down" and ema_short.iloc[-1] < ema_long.iloc[-1])
    ) else 0

    # Confidence scaling
    raw_conf = abs(slope_pct) / (dynamic_slope_thr * 3)
    confidence = int(min(5, max(1, raw_conf + ema_cross_boost)))

    return direction, confidence