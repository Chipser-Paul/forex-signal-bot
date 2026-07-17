# strategies/smc_engine/displacement_engine.py
# Displacement Engine - multi-candle impulse + realistic FVG detection (SMC-aware)

import pandas as pd
from utils.log import log

IMPULSE_ATR_MULT_DEFAULT = 1.2
LOOKBACK_CANDLES_DEFAULT = 3


def detect_displacement(
    df: pd.DataFrame,
    structure_dir: str,
    atr_period: int = 14,
    impulse_atr_mult: float = IMPULSE_ATR_MULT_DEFAULT,  # relaxed (was 1.5)
    lookback_candles: int = LOOKBACK_CANDLES_DEFAULT,      # impulse can span 2-3 candles
):
    """
    Detects displacement as a price move (not a single candle)
    and optionally identifies a realistic FVG.

    Returns:
        dict or None
    """

    if df is None or len(df) < atr_period + lookback_candles + 2:
        log("Displacement : NO data", "red")
        return None

    high = df["high"]
    low = df["low"]
    close = df["close"]

    # -------------------------------------------------
    # ATR (robust)
    # -------------------------------------------------
    tr = (
        (high - low)
        .combine((high - close.shift()).abs(), max)
        .combine((low - close.shift()).abs(), max)
    )
    atr = tr.rolling(atr_period).mean().iloc[-1]

    if atr is None or atr <= 0:
        log("Displacement : ATR invalid", "red")
        return None

    # -------------------------------------------------
    # Multi-candle impulse detection
    # -------------------------------------------------
    recent = df.iloc[-lookback_candles:]

    impulse_high = recent["high"].max()
    impulse_low = recent["low"].min()
    impulse_range = impulse_high - impulse_low

    if impulse_range < atr * impulse_atr_mult:
        log("Displacement : No impulsive move", "yellow")
        return {
            "valid": False,
            "type": "none",
        }

    # Direction via CLOSE-to-CLOSE expansion (more reliable)
    start_close = close.iloc[-lookback_candles]
    end_close = close.iloc[-1]

    direction = "up" if end_close > start_close else "down"

    # Strength score (0 -> weak, 1 -> very strong)
    strength = min(1.0, impulse_range / (atr * 2.5))

    # -------------------------------------------------
    # Expected direction from structure
    # -------------------------------------------------
    expected_dir = "down" if structure_dir == "bearish" else "up"

    # -------------------------------------------------
    # FVG Detection (scan impulse candles, not just last)
    # -------------------------------------------------
    fvg = None
    wick_tolerance = atr * 0.25  # realistic for XAU / indices

    impulse_df = df.iloc[-(lookback_candles + 1):]

    for i in range(2, len(impulse_df)):
        c1 = impulse_df.iloc[i - 2]
        c2 = impulse_df.iloc[i - 1]
        c3 = impulse_df.iloc[i]

        # Bullish FVG
        if direction == "up":
            if c3["low"] > c1["high"] - wick_tolerance:
                fvg_low = c1["high"]
                fvg_high = c3["low"]
                if fvg_high > fvg_low:
                    fvg = (fvg_low, fvg_high)
                    break

        # Bearish FVG
        else:
            if c3["high"] < c1["low"] + wick_tolerance:
                fvg_high = c1["low"]
                fvg_low = c3["high"]
                if fvg_high > fvg_low:
                    fvg = (fvg_low, fvg_high)
                    break

    # -------------------------------------------------
    # Classification
    # -------------------------------------------------
    if direction != expected_dir:
        log(
            f"Displacement : {direction.upper()} pullback/mitigation",
            "yellow",
        )
        return {
            "valid": False,
            "type": "pullback",
            "direction": direction,
            "fvg": fvg,
            "strength": strength,
        }

    # Confirmation with structure
    msg = "FVG present" if fvg else "No FVG (acceptable)"
    log(
        f"Displacement : {direction.upper()} CONFIRMATION | {msg}",
        "green",
    )

    return {
        "valid": True,
        "type": "confirmation",
        "direction": direction,
        "fvg": fvg,
        "strength": strength,
        "impulse_range": impulse_range,
        "atr": atr,
    }
