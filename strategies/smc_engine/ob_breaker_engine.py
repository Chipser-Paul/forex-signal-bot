from __future__ import annotations

import pandas as pd
import numpy as np

from utils.indicators import calculate_atr

LEVEL_PAD_ATR_MULT = 0.20
DISPLACEMENT_BODY_ATR_MULT = 1.5


def _find_order_block(
    df: pd.DataFrame,
    structure_dir: str,
    impulse_idx: int,
    search_back: int,
):
    start = max(1, impulse_idx - search_back)
    for i in range(impulse_idx - 1, start - 1, -1):
        o = float(df["open"].iloc[i])
        c = float(df["close"].iloc[i])
        h = float(df["high"].iloc[i])
        l = float(df["low"].iloc[i])

        if structure_dir == "bullish":
            # Bullish OB: last bearish candle before upward impulse
            if c < o:
                return {"index": i, "zone_low": l, "zone_high": h}
        else:
            # Bearish OB: last bullish candle before downward impulse
            if c > o:
                return {"index": i, "zone_low": l, "zone_high": h}
    return None


def _is_displacement_candle(df: pd.DataFrame, candle_index: int, atr_val: float) -> bool:
    if candle_index < 0 or candle_index >= len(df) or atr_val <= 0:
        return False
    body = abs(float(df["close"].iloc[candle_index]) - float(df["open"].iloc[candle_index]))
    return body >= (atr_val * DISPLACEMENT_BODY_ATR_MULT)


def _zone_mitigated(df: pd.DataFrame, ob_index: int, zone_low: float, zone_high: float) -> bool:
    mitigated, _ = _zone_mitigated_age(df, ob_index, zone_low, zone_high)
    return mitigated


def _zone_mitigated_age(df: pd.DataFrame, ob_index: int, zone_low: float, zone_high: float) -> tuple[bool, int]:
    """
    Returns (is_mitigated, bars_ago) where bars_ago is how many bars since the most recent mitigation.
    If not mitigated, returns (False, -1).
    """
    if ob_index + 1 >= len(df):
        return False, -1
    later = df.iloc[ob_index + 1 :]
    if later.empty:
        return False, -1

    overlaps = (later["low"].astype(float) <= zone_high) & (
        later["high"].astype(float) >= zone_low
    )
    touched = np.flatnonzero(overlaps.to_numpy())
    if len(touched) == 0:
        return False, -1

    most_recent_absolute = ob_index + 1 + touched[-1]
    bars_ago = len(df) - 1 - most_recent_absolute
    return True, int(bars_ago)


def _zone_in_dealing_area(
    structure_dir: str,
    zone_low: float,
    zone_high: float,
    premium_zone: dict | None,
    discount_zone: dict | None,
    equilibrium_level: float | None,
) -> bool:
    zone_mid = (zone_low + zone_high) / 2.0
    if structure_dir == "bullish":
        if discount_zone:
            return float(discount_zone["bottom"]) <= zone_mid <= float(discount_zone["top"])
        if equilibrium_level is not None:
            return zone_mid <= float(equilibrium_level)
    if structure_dir == "bearish":
        if premium_zone:
            return float(premium_zone["bottom"]) <= zone_mid <= float(premium_zone["top"])
        if equilibrium_level is not None:
            return zone_mid >= float(equilibrium_level)
    return True


def _find_breaker(df: pd.DataFrame, structure_dir: str, lookback: int, atr_val: float):
    if len(df) < lookback + 5:
        return None

    recent = df.iloc[-(lookback + 3) : -3]
    level_pad = atr_val * LEVEL_PAD_ATR_MULT

    if structure_dir == "bullish":
        level = float(recent["high"].max())
        last3 = df.iloc[-3:]
        if float(last3["close"].iloc[-1]) > level and float(last3["low"].min()) <= (level + level_pad):
            return {
                "level": level,
                "zone_low": level - level_pad,
                "zone_high": level + level_pad,
            }
    else:
        level = float(recent["low"].min())
        last3 = df.iloc[-3:]
        if float(last3["close"].iloc[-1]) < level and float(last3["high"].max()) >= (level - level_pad):
            return {
                "level": level,
                "zone_low": level - level_pad,
                "zone_high": level + level_pad,
            }

    return None


def detect_ob_breaker(
    df: pd.DataFrame,
    structure_dir: str,
    lookback: int = 30,
    search_back: int = 12,
    premium_zone: dict | None = None,
    discount_zone: dict | None = None,
    equilibrium_level: float | None = None,
):
    """
    Lightweight OB/Breaker validator for SMC flow.
    Used as a quality gate after displacement confirmation.
    """
    if df is None or df.empty or structure_dir not in ("bullish", "bearish"):
        return {"valid": False, "reason": "invalid_input", "type": "none"}

    if len(df) < max(lookback, 20):
        return {"valid": False, "reason": "insufficient_data", "type": "none"}

    atr_val = float(calculate_atr(df, 14) or 0.0)
    if atr_val <= 0:
        return {"valid": False, "reason": "invalid_atr", "type": "none"}

    recent = df.iloc[-lookback:]
    body = (recent["close"] - recent["open"]).abs()
    impulse_offset = int(body.values.argmax())
    impulse_idx = len(df) - lookback + impulse_offset

    ob = _find_order_block(df, structure_dir, impulse_idx=impulse_idx, search_back=search_back)
    if ob:
        last_close = float(df["close"].iloc[-1])
        zone_low = float(ob["zone_low"])
        zone_high = float(ob["zone_high"])
        zone_mid = (zone_low + zone_high) / 2.0
        distance_atr = abs(last_close - zone_mid) / atr_val
        mitigated = _zone_mitigated(df, int(ob["index"]), zone_low, zone_high)
        displacement_valid = _is_displacement_candle(df, impulse_idx, atr_val)
        in_pd_zone = _zone_in_dealing_area(
            structure_dir,
            zone_low,
            zone_high,
            premium_zone=premium_zone,
            discount_zone=discount_zone,
            equilibrium_level=equilibrium_level,
        )

        # Invalidation check: close beyond far side of zone.
        if structure_dir == "bullish" and last_close < zone_low:
            return {
                "valid": False,
                "reason": "ob_invalidated",
                "type": "order_block",
                "zone": [zone_low, zone_high],
                "distance_atr": round(distance_atr, 3),
                "mitigated": mitigated,
            }
        if structure_dir == "bearish" and last_close > zone_high:
            return {
                "valid": False,
                "reason": "ob_invalidated",
                "type": "order_block",
                "zone": [zone_low, zone_high],
                "distance_atr": round(distance_atr, 3),
                "mitigated": mitigated,
            }

        mitigated, bars_ago = _zone_mitigated_age(df, int(ob["index"]), zone_low, zone_high)
        recently_mitigated = mitigated and bars_ago <= 3
        stale_mitigated = mitigated and bars_ago > 3

        if stale_mitigated:
            return {
                "valid": False,
                "reason": "ob_mitigated",
                "type": "order_block",
                "zone": [zone_low, zone_high],
                "distance_atr": round(distance_atr, 3),
                "mitigated": True,
                "bars_ago": bars_ago,
            }

        if not displacement_valid:
            return {
                "valid": False,
                "reason": "ob_no_displacement",
                "type": "order_block",
                "zone": [zone_low, zone_high],
                "distance_atr": round(distance_atr, 3),
                "mitigated": False,
            }

        if not in_pd_zone:
            return {
                "valid": False,
                "reason": "ob_outside_pd_zone",
                "type": "order_block",
                "zone": [zone_low, zone_high],
                "distance_atr": round(distance_atr, 3),
                "mitigated": False,
            }

        return {
            "valid": True,
            "reason": "ob_aligned",
            "type": "order_block",
            "zone": [zone_low, zone_high],
            "distance_atr": round(distance_atr, 3),
            "impulse_index": int(impulse_idx),
            "mitigated": False,
            "recently_mitigated": recently_mitigated,
            "bars_ago": bars_ago if recently_mitigated else None,
            "fresh": True,
            "in_pd_zone": True,
        }

    breaker = _find_breaker(df, structure_dir, lookback=lookback, atr_val=atr_val)
    if breaker:
        return {
            "valid": True,
            "reason": "breaker_aligned",
            "type": "breaker",
            "zone": [float(breaker["zone_low"]), float(breaker["zone_high"])],
            "level": float(breaker["level"]),
            "impulse_index": int(impulse_idx),
            "fresh": True,
        }

    return {"valid": False, "reason": "no_ob_or_breaker", "type": "none"}
