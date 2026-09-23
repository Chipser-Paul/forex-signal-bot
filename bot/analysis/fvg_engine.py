from __future__ import annotations

import pandas as pd  # pyright: ignore[reportMissingModuleSource]

from bot.strategy.regime import atr_series


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

    V001 (phase6-development-v2-V001, hypothesis phase8-v2-H005, audit
    phase8-v2-S001): the per-window ATR dependency is supplied by the
    canonical rolling helper ``bot.strategy.regime.atr_series`` so the
    detector evaluates every candidate window. The previous implementation
    derived its ATR from the scalar ``utils.indicators.calculate_atr``
    surface and skipped every window because a scalar float has no
    ``.iloc``. Windows without an available (non-NaN, positive) rolling ATR
    at the displacement candle are skipped, preserving the frozen
    ``atr_val <= 0`` availability intent across the ATR warm-up head. All
    thresholds (``atr_period = 14``, ``displacement_mult = 1.5``), gap
    geometry, fill status, direction filtering and ``source_index = i - 1``
    attribution are unchanged.
    """
    if df is None or len(df) < atr_period + 3:
        return []

    atr_values = atr_series(df, atr_period)
    fvgs: list[dict[str, object]] = []

    for i in range(2, len(df)):
        c1 = df.iloc[i - 2]
        c2 = df.iloc[i - 1]
        c3 = df.iloc[i]

        if i - 1 >= len(atr_values):
            continue

        atr_val = atr_values.iloc[i - 1]
        if pd.isna(atr_val) or float(atr_val) <= 0:
            continue
        atr_val = float(atr_val)

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
