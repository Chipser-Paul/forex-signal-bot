# strategies/smc_engine/market_structure.py
# Smart Money Concepts - Market Structure Detection
# Continuous confidence + state + transition awareness

import pandas as pd
from utils.log import log
from utils.indicators import calculate_atr
from strategies.smc_engine.displacement_engine import (
    detect_displacement as detect_displacement_engine,
)

SWING_LOOKBACK = 3
DISPLACEMENT_ATR_MULT = 1.2

CONDITION_ATR_WINDOW = 20
LOW_VOL_RATIO = 0.7
HIGH_VOL_RATIO = 1.5
MIN_SWING_ATR_MULT = 0.6
PRESSURE_LOOKBACK = 5
PRESSURE_MIN_MOVE_ATR = 1.2
PRESSURE_MIN_BAR_COUNT = 4
LEAD_BIAS_LOOKBACK = 8
LEAD_BIAS_MIN_MOVE_ATR = 0.8
LEAD_BIAS_MIN_BAR_SHARE = 0.625
LEAD_BIAS_MIN_BODY_SHARE = 0.55
EQUAL_LEVEL_TOL_ATR_MULT = 0.20

# Developing swing / early BOS parameters
DEVELOPING_MIN_BREAK_ATR = 0.15  # minimum break distance (ATR units) for early signal
DEVELOPING_CONFIRM_BREAK_ATR = 0.30  # break distance requiring no close confirmation


# ------------------------------------------------------------------
# 1) SWING DETECTION
# ------------------------------------------------------------------
def detect_swings(df: pd.DataFrame):
    swings = []

    for i in range(SWING_LOOKBACK, len(df) - SWING_LOOKBACK):
        high = df["high"].iloc[i]
        low = df["low"].iloc[i]

        if high == max(df["high"].iloc[i - SWING_LOOKBACK : i + SWING_LOOKBACK + 1]):
            swings.append({"index": i, "price": high, "type": "high"})

        if low == min(df["low"].iloc[i - SWING_LOOKBACK : i + SWING_LOOKBACK + 1]):
            swings.append({"index": i, "price": low, "type": "low"})

    return swings


def filter_swings_by_distance(swings, min_distance: float):
    if not swings or min_distance <= 0:
        return swings
    filtered = [swings[0]]
    for s in swings[1:]:
        if abs(s["price"] - filtered[-1]["price"]) >= min_distance:
            filtered.append(s)
    return filtered


def split_swings(swings):
    swing_highs = [s for s in swings if s["type"] == "high"]
    swing_lows = [s for s in swings if s["type"] == "low"]
    return swing_highs, swing_lows


def detect_equal_levels(level_swings, tolerance: float, level_type: str):
    if not level_swings or tolerance <= 0:
        return []

    sorted_swings = sorted(level_swings, key=lambda x: x["price"])
    clusters = []
    current_cluster = [sorted_swings[0]]

    for swing in sorted_swings[1:]:
        cluster_prices = [item["price"] for item in current_cluster]
        cluster_mid = sum(cluster_prices) / len(cluster_prices)
        if abs(swing["price"] - cluster_mid) <= tolerance:
            current_cluster.append(swing)
        else:
            if len(current_cluster) >= 2:
                prices = [item["price"] for item in current_cluster]
                clusters.append(
                    {
                        "type": level_type,
                        "price": sum(prices) / len(prices),
                        "top": max(prices),
                        "bottom": min(prices),
                        "count": len(current_cluster),
                        "indices": [item["index"] for item in current_cluster],
                    }
                )
            current_cluster = [swing]

    if len(current_cluster) >= 2:
        prices = [item["price"] for item in current_cluster]
        clusters.append(
            {
                "type": level_type,
                "price": sum(prices) / len(prices),
                "top": max(prices),
                "bottom": min(prices),
                "count": len(current_cluster),
                "indices": [item["index"] for item in current_cluster],
            }
        )

    return clusters


def get_event_reference_level(structure: str | None, event: str | None, swing_highs, swing_lows):
    if event not in ("BOS", "CHOCH") or structure not in ("bullish", "bearish"):
        return None

    if structure == "bullish":
        if event == "BOS" and swing_highs:
            return float(swing_highs[-1]["price"])
        if event == "CHOCH" and swing_lows:
            return float(swing_lows[-1]["price"])

    if structure == "bearish":
        if event == "BOS" and swing_lows:
            return float(swing_lows[-1]["price"])
        if event == "CHOCH" and swing_highs:
            return float(swing_highs[-1]["price"])

    return None


def build_dealing_range(swing_highs, swing_lows):
    if not swing_highs or not swing_lows:
        return None

    range_high = float(swing_highs[-1]["price"])
    range_low = float(swing_lows[-1]["price"])
    if range_high < range_low:
        range_high, range_low = range_low, range_high

    equilibrium = (range_high + range_low) / 2.0
    return {
        "range_high": range_high,
        "range_low": range_low,
        "equilibrium_level": equilibrium,
        "premium_zone": {
            "top": range_high,
            "bottom": equilibrium,
        },
        "discount_zone": {
            "top": equilibrium,
            "bottom": range_low,
        },
    }


# ------------------------------------------------------------------
# 2) STRUCTURE CLASSIFICATION (GEOMETRY ONLY)
# ------------------------------------------------------------------
def classify_structure(swings):
    highs = [s for s in swings if s["type"] == "high"]
    lows = [s for s in swings if s["type"] == "low"]

    if len(highs) < 2 or len(lows) < 2:
        return None

    last_high, prev_high = highs[-1], highs[-2]
    last_low, prev_low = lows[-1], lows[-2]

    if last_high["price"] > prev_high["price"] and last_low["price"] > prev_low["price"]:
        return "bullish"

    if last_high["price"] < prev_high["price"] and last_low["price"] < prev_low["price"]:
        return "bearish"

    return "range"


# ------------------------------------------------------------------
# 3) BOS / CHOCH (CLOSE-BASED)
# ------------------------------------------------------------------
def detect_bos_or_choch(df: pd.DataFrame, structure, swings):
    close = df["close"].iloc[-1]
    highs = [s for s in swings if s["type"] == "high"]
    lows = [s for s in swings if s["type"] == "low"]
    if not highs or not lows:
        return None

    last_swing_high = highs[-1]["price"]
    last_swing_low = lows[-1]["price"]

    if structure == "bullish":
        if close < last_swing_low:
            return "CHOCH"
        if close > last_swing_high:
            return "BOS"

    if structure == "bearish":
        if close > last_swing_high:
            return "CHOCH"
        if close < last_swing_low:
            return "BOS"

    return None


# ------------------------------------------------------------------
# 2b) DEVELOPING EXTREMES — track highest high / lowest low since last confirmed swing
# ------------------------------------------------------------------
def detect_developing_extremes(df: pd.DataFrame, swings: list) -> dict:
    """
    Track the highest high and lowest low since the last confirmed swing.
    This lets us detect BOS/CHOCH early, without waiting for 3-bar
    swing confirmation on the right side.

    Returns dict with 'high' (float), 'low' (float), 'since_index' (int).
    Both values are None if no swings exist.
    """
    if not swings:
        return {"high": None, "low": None, "since_index": None}

    last_idx = swings[-1]["index"]

    # Slice from the bar after the last confirmed swing to the end
    since_slice = df.iloc[last_idx + 1:]
    if since_slice.empty:
        return {
            "high": float(df["high"].iloc[-1]),
            "low": float(df["low"].iloc[-1]),
            "since_index": last_idx,
        }

    return {
        "high": float(since_slice["high"].max()),
        "low": float(since_slice["low"].min()),
        "since_index": last_idx,
    }


# ------------------------------------------------------------------
# 2c) EARLY BOS/ChoCH — responsive detection using developing extremes
# ------------------------------------------------------------------
def detect_early_event(
    df: pd.DataFrame,
    structure: str | None,
    swings: list,
    developing: dict,
    atr_val: float,
) -> dict:
    """
    Detect BOS/CHOCH earlier by comparing developing extremes to the last
    confirmed swing level.  Catches breaks 1-3 bars before the standard
    close-based method.

    Conservative triggers:
      - Break >= 0.3 ATR → signal even without a closed-candle confirmation
      - Break >= 0.15 ATR + any recent close beyond the level → signal
      - Otherwise → no signal (ignores minor wicks)

    Returns dict with:
      event (str | None)  — "BOS" / "CHOCH" / None
      confirmed (bool)     — a closed candle confirms the break
      confidence_modifier  — 0.0-1.0; multiply the base confidence by this
      break_atr (float)    — how far beyond the swing level (ATR units)
    """
    result = {"event": None, "confirmed": False, "confidence_modifier": 0.0, "break_atr": 0.0}

    if not swings or structure not in ("bullish", "bearish") or atr_val <= 0:
        return result

    highs = [s for s in swings if s["type"] == "high"]
    lows = [s for s in swings if s["type"] == "low"]
    if not highs or not lows:
        return result

    last_swing_high = float(highs[-1]["price"])
    last_swing_low = float(lows[-1]["price"])
    dev_high = developing.get("high")
    dev_low = developing.get("low")

    if dev_high is None or dev_low is None:
        return result

    last_close = float(df["close"].iloc[-1])

    # Check whether any of the last 3 candles closed past the level
    recent_closes_above = any(
        float(df["close"].iloc[i]) > last_swing_high
        for i in range(max(0, len(df) - 3), len(df))
    )
    recent_closes_below = any(
        float(df["close"].iloc[i]) < last_swing_low
        for i in range(max(0, len(df) - 3), len(df))
    )

    candidates = []

    def _score_break(
        break_type: str,
        extreme: float,
        level: float,
        close_confirms: bool,
        direction: str,  # "above" or "below"
    ) -> tuple:
        distance = abs(extreme - level) / max(atr_val, 1e-6)
        is_confirmed = close_confirms or distance >= DEVELOPING_CONFIRM_BREAK_ATR
        # Confidence scales from 0.4 (minimal break) to 1.0 (strong break)
        mod = min(1.0, 0.4 + distance * 0.6)
        if is_confirmed:
            mod = max(mod, 0.75)
        return (break_type, distance, is_confirmed, mod)

    if structure == "bullish":
        # BOS — price broke above the last swing high
        if dev_high > last_swing_high and (dev_high - last_swing_high) / max(atr_val, 1e-6) >= DEVELOPING_MIN_BREAK_ATR:
            candidates.append(_score_break("BOS", dev_high, last_swing_high, recent_closes_above or last_close > last_swing_high, "above"))
        # CHOCH — price broke below the last swing low
        if dev_low < last_swing_low and (last_swing_low - dev_low) / max(atr_val, 1e-6) >= DEVELOPING_MIN_BREAK_ATR:
            candidates.append(_score_break("CHOCH", dev_low, last_swing_low, recent_closes_below or last_close < last_swing_low, "below"))

    elif structure == "bearish":
        if dev_low < last_swing_low and (last_swing_low - dev_low) / max(atr_val, 1e-6) >= DEVELOPING_MIN_BREAK_ATR:
            candidates.append(_score_break("BOS", dev_low, last_swing_low, recent_closes_below or last_close < last_swing_low, "below"))
        if dev_high > last_swing_high and (dev_high - last_swing_high) / max(atr_val, 1e-6) >= DEVELOPING_MIN_BREAK_ATR:
            candidates.append(_score_break("CHOCH", dev_high, last_swing_high, recent_closes_above or last_close > last_swing_high, "above"))

    if not candidates:
        return result

    # Pick the most significant break (highest break_atr)
    candidates.sort(key=lambda x: x[1], reverse=True)
    return {
        "event": candidates[0][0],
        "confirmed": candidates[0][2],
        "confidence_modifier": candidates[0][3],
        "break_atr": candidates[0][1],
    }


def displacement_confirmed(df: pd.DataFrame, structure_dir: str) -> bool:
    if structure_dir not in ("bullish", "bearish"):
        return False

    result = detect_displacement_engine(
        df,
        structure_dir,
        atr_period=14,
        impulse_atr_mult=DISPLACEMENT_ATR_MULT,
    )

    if isinstance(result, dict):
        return bool(result.get("valid"))

    return False


def detect_directional_pressure(df: pd.DataFrame, atr_val: float) -> dict:
    if df is None or len(df) < PRESSURE_LOOKBACK or atr_val <= 0:
        return {"direction": None, "strength": 0.0, "label": "none"}

    recent = df.iloc[-PRESSURE_LOOKBACK:]
    bearish_bars = int((recent["close"] < recent["open"]).sum())
    bullish_bars = int((recent["close"] > recent["open"]).sum())
    start_close = float(recent["close"].iloc[0])
    last_close = float(recent["close"].iloc[-1])
    move_atr = abs(last_close - start_close) / max(atr_val, 1e-6)

    recent_low_break = last_close < float(df["low"].iloc[-(PRESSURE_LOOKBACK + 3):-1].min())
    recent_high_break = last_close > float(df["high"].iloc[-(PRESSURE_LOOKBACK + 3):-1].max())

    pressure_range = max(float(recent["high"].max()) - float(recent["low"].min()), 1e-6)
    close_location = (last_close - float(recent["low"].min())) / pressure_range

    if (
        bearish_bars >= PRESSURE_MIN_BAR_COUNT
        and last_close < start_close
        and move_atr >= PRESSURE_MIN_MOVE_ATR
        and recent_low_break
        and close_location <= 0.35
    ):
        return {
            "direction": "bearish",
            "strength": min(1.0, move_atr / 2.0),
            "label": "bearish_pressure",
        }

    if (
        bullish_bars >= PRESSURE_MIN_BAR_COUNT
        and last_close > start_close
        and move_atr >= PRESSURE_MIN_MOVE_ATR
        and recent_high_break
        and close_location >= 0.65
    ):
        return {
            "direction": "bullish",
            "strength": min(1.0, move_atr / 2.0),
            "label": "bullish_pressure",
        }

    return {"direction": None, "strength": 0.0, "label": "none"}


def detect_lead_bias(df: pd.DataFrame, atr_val: float) -> dict:
    if df is None or len(df) < LEAD_BIAS_LOOKBACK + 3 or atr_val <= 0:
        return {"direction": None, "strength": 0.0, "label": "none"}

    recent = df.iloc[-LEAD_BIAS_LOOKBACK:]
    bullish_bars = int((recent["close"] > recent["open"]).sum())
    bearish_bars = int((recent["close"] < recent["open"]).sum())
    total_bars = max(len(recent), 1)
    bullish_share = bullish_bars / total_bars
    bearish_share = bearish_bars / total_bars

    start_close = float(recent["close"].iloc[0])
    last_close = float(recent["close"].iloc[-1])
    move_atr = abs(last_close - start_close) / max(atr_val, 1e-6)

    body_sum = float((recent["close"] - recent["open"]).abs().sum())
    range_sum = float((recent["high"] - recent["low"]).clip(lower=1e-6).sum())
    body_share = body_sum / max(range_sum, 1e-6)

    prior_slice = df.iloc[-(LEAD_BIAS_LOOKBACK + 3):-3]
    broke_recent_high = last_close > float(prior_slice["high"].max())
    broke_recent_low = last_close < float(prior_slice["low"].min())

    price_range = max(float(recent["high"].max()) - float(recent["low"].min()), 1e-6)
    close_location = (last_close - float(recent["low"].min())) / price_range
    strength = min(1.0, (move_atr / max(LEAD_BIAS_MIN_MOVE_ATR, 1e-6)))

    if (
        bearish_share >= LEAD_BIAS_MIN_BAR_SHARE
        and body_share >= LEAD_BIAS_MIN_BODY_SHARE
        and move_atr >= LEAD_BIAS_MIN_MOVE_ATR
        and broke_recent_low
        and close_location <= 0.35
    ):
        return {"direction": "bearish", "strength": strength, "label": "lead_bearish"}

    if (
        bullish_share >= LEAD_BIAS_MIN_BAR_SHARE
        and body_share >= LEAD_BIAS_MIN_BODY_SHARE
        and move_atr >= LEAD_BIAS_MIN_MOVE_ATR
        and broke_recent_high
        and close_location >= 0.65
    ):
        return {"direction": "bullish", "strength": strength, "label": "lead_bullish"}

    return {"direction": None, "strength": 0.0, "label": "none"}


def combine_lead_bias(primary: dict, support: dict | None, structure: str | None) -> dict:
    if not support or support.get("direction") not in ("bullish", "bearish"):
        return primary

    primary_dir = primary.get("direction")
    support_dir = support.get("direction")
    primary_strength = float(primary.get("strength", 0.0) or 0.0)
    support_strength = float(support.get("strength", 0.0) or 0.0)

    # H1 remains the main driver; M30 only assists.
    if primary_dir in ("bullish", "bearish"):
        if support_dir == primary_dir:
            return {
                "direction": primary_dir,
                "strength": min(1.0, primary_strength * 0.75 + support_strength * 0.25),
                "label": f"{primary.get('label', 'lead')}_supported",
            }
        return {
            "direction": primary_dir,
            "strength": max(0.0, primary_strength * 0.85),
            "label": primary.get("label", "lead"),
        }

    if structure in ("bullish", "bearish") and support_dir == structure:
        return {
            "direction": structure,
            "strength": min(1.0, support_strength * 0.25),
            "label": f"support_{support.get('label', 'lead')}",
        }

    return support


# ------------------------------------------------------------------
# 4) MARKET CONDITION TAG
# ------------------------------------------------------------------
def detect_market_condition(df: pd.DataFrame, swings) -> str:
    atr = calculate_atr(df, 14)
    atr_val = atr.iloc[-1] if hasattr(atr, "iloc") else atr
    if pd.isna(atr_val) or atr_val <= 0:
        return "unknown"

    atr_series = atr if hasattr(atr, "rolling") else None
    atr_mean = (
        atr_series.rolling(CONDITION_ATR_WINDOW).mean().iloc[-1]
        if atr_series is not None and len(atr_series) >= CONDITION_ATR_WINDOW
        else atr_val
    )
    vol_ratio = atr_val / max(atr_mean, 1e-6)

    recent = swings[-6:] if len(swings) >= 6 else swings
    highs = [s["price"] for s in recent if s["type"] == "high"]
    lows = [s["price"] for s in recent if s["type"] == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return "unknown"

    # Trend vs range via normalized slope
    slope = (
        abs(highs[-1] - highs[0]) +
        abs(lows[-1] - lows[0])
    ) / (2 * atr_val)

    if vol_ratio >= HIGH_VOL_RATIO:
        return "vol_expansion"
    if vol_ratio <= LOW_VOL_RATIO:
        return "low_vol"
    if slope >= 0.9:
        return "trend"
    return "range"


# ------------------------------------------------------------------
# 5) CONTINUOUS CONFIDENCE ENGINE
# ------------------------------------------------------------------
def compute_structure_confidence(df, structure, event, swings, displacement_ok: bool, condition: str, pressure: dict, lead_bias: dict | None = None):
    if structure not in ("bullish", "bearish"):
        return 0

    atr = calculate_atr(df, 14)
    atr_val = atr.iloc[-1] if hasattr(atr, "iloc") else atr
    if pd.isna(atr_val):
        return 0
    atr_val = max(atr_val, 1e-6)

    score = 0.0
    weight = 0.0

    recent = swings[-8:]
    highs = [s["price"] for s in recent if s["type"] == "high"]
    lows = [s["price"] for s in recent if s["type"] == "low"]
    if len(highs) < 2 or len(lows) < 2:
        if pressure.get("direction") == structure:
            base_score = pressure.get("strength", 0.0) * 55
            if displacement_ok:
                base_score += 5
            return int(max(0, min(60, base_score)))
        if lead_bias and lead_bias.get("direction") == structure:
            base_score = lead_bias.get("strength", 0.0) * 40
            if displacement_ok:
                base_score += 5
            return int(max(0, min(50, base_score)))
        return 0

    # 1) Structure slope strength (continuous)
    if len(highs) >= 2 and len(lows) >= 2:
        slope = (
            abs(highs[-1] - highs[0]) +
            abs(lows[-1] - lows[0])
        ) / (2 * atr_val)
        slope_score = min(1.0, slope)
        slope_weight = 35 if condition == "trend" else 25
        score += slope_score * slope_weight
        weight += slope_weight

    # 2) BOS strength (distance-based)
    if event == "BOS":
        last_price = df["close"].iloc[-1]
        ref = swings[-1]["price"]
        bos_strength = min(1.0, abs(last_price - ref) / atr_val)
        bos_weight = 30 if condition in ("trend", "vol_expansion") else 20
        score += bos_strength * bos_weight
        weight += bos_weight

    # 3) Swing clarity
    distances = [
        abs(swings[i]["price"] - swings[i - 1]["price"])
        for i in range(1, len(swings))
    ]
    if distances:
        clarity = min(1.0, (sum(distances) / len(distances)) / atr_val)
        clarity_weight = 25 if condition == "range" else 15
        score += clarity * clarity_weight
        weight += clarity_weight

    # 4) Volatility expansion
    body = abs(df["close"].iloc[-1] - df["open"].iloc[-1])
    vol_score = min(1.0, body / atr_val)
    vol_weight = 25 if condition == "vol_expansion" else 15
    score += vol_score * vol_weight
    weight += vol_weight

    # 5) CHOCH penalty
    if event == "CHOCH":
        score *= 0.6

    # 6) Strong directional pressure can upgrade a reversal-in-progress.
    if pressure.get("direction") == structure:
        score += float(pressure.get("strength", 0.0)) * 20
        weight += 20

    # 7) Lead bias helps the engine recognize earlier directional development.
    if lead_bias and lead_bias.get("direction") == structure:
        score += float(lead_bias.get("strength", 0.0)) * 15
        weight += 15

    if weight == 0:
        return 0

    # Hard cap: no displacement = weak confidence (relaxed a bit in range/low-vol)
    if not displacement_ok:
        if condition in ("range", "low_vol"):
            score *= 0.75
        else:
            score *= 0.6

    return int(max(0, min(100, (score / weight) * 100)))


# ------------------------------------------------------------------
# 6) STATE ENGINE
# ------------------------------------------------------------------
def determine_structure_state(confidence, displacement_ok, condition: str, event: str | None):
    if event == "PRESSURE_REVERSAL":
        if confidence >= 45:
            return "transition"
        return "range"

    # Confirmed requires displacement, except allow range to confirm with higher confidence
    if confidence >= 65 and (displacement_ok or condition == "range"):
        return "confirmed"

    # Transition = internal / weak / unconfirmed
    if confidence >= 50:
        return "transition"

    return "range"


# ------------------------------------------------------------------
# 7) MAIN ANALYSIS FUNCTION
# ------------------------------------------------------------------
def analyze_market_structure(df: pd.DataFrame, state=None, support_df: pd.DataFrame | None = None, silent: bool = False):
    if df is None or df.empty:
        if not silent:
            log("Market Structure : NO data", "red")
        return None

    atr = calculate_atr(df, 14)
    atr_val = atr.iloc[-1] if hasattr(atr, "iloc") else atr
    if pd.isna(atr_val) or atr_val <= 0:
        if not silent:
            log("Market Structure : ATR invalid", "yellow")
        return None

    swings = detect_swings(df)
    swings = filter_swings_by_distance(swings, atr_val * MIN_SWING_ATR_MULT)
    if len(swings) < 4:
        if not silent:
            log("Market Structure : Not enough swings", "yellow")
        return None

    swing_highs, swing_lows = split_swings(swings)
    equal_highs = detect_equal_levels(
        swing_highs,
        atr_val * EQUAL_LEVEL_TOL_ATR_MULT,
        "equal_highs",
    )
    equal_lows = detect_equal_levels(
        swing_lows,
        atr_val * EQUAL_LEVEL_TOL_ATR_MULT,
        "equal_lows",
    )

    structure = classify_structure(swings)
    pressure = detect_directional_pressure(df, atr_val)
    lead_bias = detect_lead_bias(df, atr_val)
    support_lead_bias = None
    if support_df is not None and not support_df.empty:
        support_atr = calculate_atr(support_df, 14)
        support_atr_val = support_atr.iloc[-1] if hasattr(support_atr, "iloc") else support_atr
        if not pd.isna(support_atr_val) and support_atr_val > 0:
            support_lead_bias = detect_lead_bias(support_df, float(support_atr_val))
            lead_bias = combine_lead_bias(lead_bias, support_lead_bias, structure)
    pressure_override = False
    if structure == "bullish" and pressure.get("direction") == "bearish":
        structure = "bearish"
        pressure_override = True
    elif structure == "bearish" and pressure.get("direction") == "bullish":
        structure = "bullish"
        pressure_override = True
    elif structure == "range" and pressure.get("direction") in ("bullish", "bearish"):
        structure = pressure.get("direction")
        pressure_override = True
    elif structure == "range" and lead_bias.get("direction") in ("bullish", "bearish"):
        structure = lead_bias.get("direction")
        pressure_override = True

    event = detect_bos_or_choch(df, structure, swings)
    if pressure_override and event is None:
        event = "PRESSURE_REVERSAL" if pressure.get("direction") == structure else "LEAD_BIAS"
    displacement_ok = displacement_confirmed(df, structure)
    condition = detect_market_condition(df, swings)
    event_reference_level = get_event_reference_level(structure, event, swing_highs, swing_lows)
    dealing_range = build_dealing_range(swing_highs, swing_lows)

    confidence = compute_structure_confidence(
        df,
        structure,
        event,
        swings,
        displacement_ok,
        condition,
        pressure,
        lead_bias,
    )
    state_label = determine_structure_state(confidence, displacement_ok, condition, event)

    # ---- DEVELOPING / EARLY DETECTION ----
    # Check for BOS/CHOCH using developing extremes (responsive, not lagging).
    # This detects structure breaks 1-3 bars before the close-based method.
    developing = detect_developing_extremes(df, swings)
    early_event = detect_early_event(df, structure, swings, developing, atr_val)
    # Only report early event when the standard event hasn't caught up yet,
    # so it genuinely adds lead time rather than duplicating.
    if early_event["event"] == event:
        early_event = {"event": None, "confirmed": False, "confidence_modifier": 0.0, "break_atr": 0.0}

    # If structure is fully confirmed with BOS, the environment should not stay tagged as range.
    if (
        state_label == "confirmed"
        and event == "BOS"
        and structure in ("bullish", "bearish")
        and condition == "range"
    ):
        condition = "trend"

    # Logging
    if not silent:
        if state_label == "range":
            log(
                f"Market Structure : RANGE | Confidence {confidence}% | Cond={condition} | LeadBias={lead_bias.get('direction') or 'none'}",
                "yellow",
            )
        elif state_label == "transition":
            log(
                f"Market Structure : TRANSITION ({structure.upper()}) | Confidence {confidence}% | Cond={condition} | LeadBias={lead_bias.get('direction') or 'none'}",
                "yellow",
            )
        else:
            log(
                f"Market Structure : {structure.upper()} CONFIRMED | Confidence {confidence}% | Event={event} | Cond={condition} | LeadBias={lead_bias.get('direction') or 'none'}",
                "green",
            )

    # Structure persistence (direction memory only; no state promotion)
    if state and structure in ("bullish", "bearish"):
        if state.structure_dir == structure:
            pass

    return {
        "structure": structure,
        "state": state_label,
        "event": event,
        "last_bos_level": event_reference_level if event == "BOS" else None,
        "last_choch_level": event_reference_level if event == "CHOCH" else None,
        "confidence": confidence,
        "swings": swings[-6:],
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
        "equal_highs": equal_highs,
        "equal_lows": equal_lows,
        "displacement": displacement_ok,
        "condition": condition,
        "pressure": pressure,
        "lead_bias": lead_bias,
        "support_lead_bias": support_lead_bias,
        "equilibrium_level": (dealing_range or {}).get("equilibrium_level"),
        "premium_zone": (dealing_range or {}).get("premium_zone"),
        "discount_zone": (dealing_range or {}).get("discount_zone"),
        "dealing_range": dealing_range,
        "developing_extremes": developing,
        "early_event": early_event,
    }
