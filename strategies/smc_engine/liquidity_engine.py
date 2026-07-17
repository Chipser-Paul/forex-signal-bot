# strategies/smc_engine/liquidity_engine.py
# Institutional-Grade Liquidity Engine (Gold Optimized)

import pandas as pd
from utils.log import log
from utils.indicators import calculate_atr

SWEEP_STRENGTH_MIN = 0.20
BODY_DOMINANCE_MIN = 0.30
EQ_TOL_ATR_MULT = 0.15
LOW_VOL_SKIP_RATIO = 0.60


def detect_liquidity_sweep(
    df: pd.DataFrame,
    structure_dir: str = None,
    lookback: int = 40,
    min_equal_points: int = 2,
    sweep_window: int = 1,
):
    """
    Institutional-Grade Liquidity Detection
    Optimized for XAUUSD (M15 / H1)

    Features:
    - Strength-based sweep filtering (ATR-based)
    - Volatility regime filter
    - Strict internal continuation logic
    - Directional bias scoring
    """

    # ---------------------------------------------------------
    # Basic validation
    # ---------------------------------------------------------
    if df is None or len(df) < lookback + 5:
        return None

    highs = df["high"]
    lows = df["low"]
    closes = df["close"]
    opens = df["open"]

    # ---------------------------------------------------------
    # ATR & Volatility Filter
    # ---------------------------------------------------------
    atr_series = calculate_atr(df, 14)

    if atr_series is None:
        return None

    if hasattr(atr_series, "iloc"):
        if len(atr_series) < 20:
            return None
        atr_val = float(atr_series.iloc[-1])
        rolling_atr_mean = atr_series.rolling(20).mean().iloc[-1]
    else:
        # Fallback if calculate_atr returns a scalar
        atr_val = float(atr_series)
        rolling_atr_mean = atr_val

    if atr_val <= 0:
        return None

    # Skip low volatility chop (Asia kill-switch)
    if atr_val < rolling_atr_mean * LOW_VOL_SKIP_RATIO:
        log("Liquidity Sweep : Skipped (low volatility regime)", "yellow")
        return None

    eq_tol = atr_val * EQ_TOL_ATR_MULT

    sweep_window = max(1, int(sweep_window))
    start_idx = max(1, len(df) - sweep_window)

    for candidate_idx in range(len(df) - 1, start_idx - 1, -1):
        candidate = df.iloc[candidate_idx]
        prev = df.iloc[candidate_idx - 1]
        candidate_index = df.index[candidate_idx]

        recent_highs = highs.iloc[max(0, candidate_idx - lookback):candidate_idx]
        recent_lows = lows.iloc[max(0, candidate_idx - lookback):candidate_idx]
        if recent_highs.empty or recent_lows.empty:
            continue

        max_high = recent_highs.max()
        min_low = recent_lows.min()

        candidate_high = candidate["high"]
        candidate_low = candidate["low"]
        candidate_close = candidate["close"]
        candidate_open = candidate["open"]
        prev_high = prev["high"]
        prev_low = prev["low"]
        body_size = abs(candidate_close - candidate_open)

        # ==========================================================
        # 1) EXTERNAL BUY-SIDE SWEEP (Equal Highs)
        # ==========================================================
        eq_highs = recent_highs[abs(recent_highs - max_high) <= eq_tol]

        if len(eq_highs) >= min_equal_points and candidate_high > max_high:
            sweep_size = candidate_high - max_high
            strength = sweep_size / atr_val
            if strength >= SWEEP_STRENGTH_MIN and candidate_close < max_high:
                direction_hint = "sell"
                classification = "continuation" if structure_dir == "bearish" else "reversal"
                confidence = min(1.0, 0.7 + strength * 0.2)
                log(f"Liquidity Sweep : Strong BUY-side raid ({classification})", "green")
                return {
                    "swept": True,
                    "side": "buy",
                    "classification": classification,
                    "direction_hint": direction_hint,
                    "price": max_high,
                    "index": candidate_index,
                    "type": "equal_highs",
                    "confidence": confidence,
                    "bars_ago": len(df) - 1 - candidate_idx,
                }

        # ==========================================================
        # 2) EXTERNAL SELL-SIDE SWEEP (Equal Lows)
        # ==========================================================
        eq_lows = recent_lows[abs(recent_lows - min_low) <= eq_tol]

        if len(eq_lows) >= min_equal_points and candidate_low < min_low:
            sweep_size = min_low - candidate_low
            strength = sweep_size / atr_val
            if strength >= SWEEP_STRENGTH_MIN and candidate_close > min_low:
                direction_hint = "buy"
                classification = "continuation" if structure_dir == "bullish" else "reversal"
                confidence = min(1.0, 0.7 + strength * 0.2)
                log(f"Liquidity Sweep : Strong SELL-side raid ({classification})", "green")
                return {
                    "swept": True,
                    "side": "sell",
                    "classification": classification,
                    "direction_hint": direction_hint,
                    "price": min_low,
                    "index": candidate_index,
                    "type": "equal_lows",
                    "confidence": confidence,
                    "bars_ago": len(df) - 1 - candidate_idx,
                }

        # ==========================================================
        # 3) STRICT INTERNAL CONTINUATION
        # ==========================================================
        if structure_dir == "bullish" and candidate_high > prev_high and candidate_close > prev_high:
            sweep_size = candidate_high - prev_high
            strength = sweep_size / atr_val
            if strength >= SWEEP_STRENGTH_MIN and body_size >= atr_val * BODY_DOMINANCE_MIN:
                log("Liquidity Sweep : Strong Internal Continuation (bullish)", "blue")
                return {
                    "swept": True,
                    "side": "buy",
                    "classification": "continuation",
                    "direction_hint": "buy",
                    "price": prev_high,
                    "index": candidate_index,
                    "type": "internal_continuation",
                    "confidence": 0.6,
                    "bars_ago": len(df) - 1 - candidate_idx,
                }

        if structure_dir == "bearish" and candidate_low < prev_low and candidate_close < prev_low:
            sweep_size = prev_low - candidate_low
            strength = sweep_size / atr_val
            if strength >= SWEEP_STRENGTH_MIN and body_size >= atr_val * BODY_DOMINANCE_MIN:
                log("Liquidity Sweep : Strong Internal Continuation (bearish)", "blue")
                return {
                    "swept": True,
                    "side": "sell",
                    "classification": "continuation",
                    "direction_hint": "sell",
                    "price": prev_low,
                    "index": candidate_index,
                    "type": "internal_continuation",
                    "confidence": 0.6,
                    "bars_ago": len(df) - 1 - candidate_idx,
                }

    # ----------------------------------------------------------
    # No liquidity detected
    # ----------------------------------------------------------
    return None
