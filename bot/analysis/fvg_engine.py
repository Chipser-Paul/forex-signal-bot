from __future__ import annotations

import pandas as pd  # pyright: ignore[reportMissingModuleSource]

from utils.indicators import calculate_atr


def _mark_fill_status(df: pd.DataFrame, start_index: int, zone_top: float, zone_bottom: float) -> bool:
    later = df.iloc[start_index + 1 :]
    if later.empty:
        return False
    touched = (later["low"] <= zone_top) & (later["high"] >= zone_bottom)
    return bool(touched.any())


def detect_fvgs(
    df: pd.DataFrame,
    timeframe: str,
    atr_period: int = 14,
    displacement_mult: float = 1.5,
):
    """
    Detect bullish/bearish FVGs with displacement and fill tracking.
    Returns a list of standardized zone dictionaries.
    """
    if df is None or len(df) < atr_period + 3:
        return []

    atr = calculate_atr(df, atr_period)
    atr_series = atr if hasattr(atr, "iloc") else None
    fvgs: list[dict[str, object]] = []

    for i in range(2, len(df)):
        c1 = df.iloc[i - 2]
        c2 = df.iloc[i - 1]
        c3 = df.iloc[i]

        if atr_series is None or i - 1 >= len(atr_series):
            continue

        atr_val = float(atr_series.iloc[i - 1])
        if atr_val <= 0:
            continue

        displacement_body = abs(float(c2["close"]) - float(c2["open"]))
        if displacement_body < atr_val * displacement_mult:
            continue

        bullish_gap = float(c1["high"]) < float(c3["low"])
        bearish_gap = float(c1["low"]) > float(c3["high"])

        if bullish_gap:
            bottom = float(c1["high"])
            top = float(c3["low"])
            fvgs.append(
                {
                    "type": "bullish_fvg",
                    "direction": "bullish",
                    "top": top,
                    "bottom": bottom,
                    "filled": _mark_fill_status(df, i, top, bottom),
                    "timeframe": timeframe,
                    "source_index": i - 1,
                    "displacement_body": displacement_body,
                }
            )
        elif bearish_gap:
            top = float(c1["low"])
            bottom = float(c3["high"])
            fvgs.append(
                {
                    "type": "bearish_fvg",
                    "direction": "bearish",
                    "top": top,
                    "bottom": bottom,
                    "filled": _mark_fill_status(df, i, top, bottom),
                    "timeframe": timeframe,
                    "source_index": i - 1,
                    "displacement_body": displacement_body,
                }
            )

    return fvgs


def get_unfilled_fvgs(df: pd.DataFrame, timeframe: str, direction: str | None = None):
    fvgs = detect_fvgs(df, timeframe=timeframe)
    zones = [zone for zone in fvgs if not zone["filled"]]
    if direction in ("bullish", "bearish"):
        zones = [zone for zone in zones if zone["direction"] == direction]
    return zones

