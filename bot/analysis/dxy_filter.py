from __future__ import annotations

import numpy as np
import pandas as pd

from bot.analysis.bias_engine import analyze_timeframe_bias
from bot.data.market_data import fetch_ohlcv
from strategies.smc_engine.market_structure import analyze_market_structure


DXY_SYMBOL_CANDIDATES = (
    "DXY",
    "USDX", 
    "USDXm",
    "USDOLLAR",
    "USDX.i",
)


def _close_array(rates) -> np.ndarray | None:
    """Extract closes from either a pandas DataFrame or a sequence of rate dicts."""
    if rates is None:
        return None
    if isinstance(rates, pd.DataFrame):
        if rates.empty or "close" not in rates.columns:
            return None
        return rates["close"].astype(float).to_numpy()
    if isinstance(rates, (list, tuple)):
        closes = []
        for row in rates:
            if isinstance(row, dict) and row.get("close") is not None:
                closes.append(float(row["close"]))
        return np.array(closes, dtype=float) if closes else None
    return None


def _resolve_dxy_symbol(symbol_candidates: tuple[str, ...] = DXY_SYMBOL_CANDIDATES) -> str | None:
    """Try to find a working DXY symbol from MT5"""
    for candidate in symbol_candidates:
        df = fetch_ohlcv(candidate, "H1", bars=50)
        if df is not None and not df.empty:
            return candidate
    return None


def get_synthetic_dxy(timeframe="H1", bars=100):
    """
    Build synthetic DXY from 6 major pairs using ICE basket weights.
    Returns array of synthetic DXY values or None if insufficient data.
    """
    # ICE basket weights (approximate)
    BASKET = [
        ("EURUSDm", 0.576, True),   # Inverted
        ("USDJPYm", 0.136, False),  # Direct  
        ("GBPUSDm", 0.119, True),   # Inverted
        ("USDCADm", 0.091, False),  # Direct
        ("USDSEKm", 0.042, False),  # Direct
        ("USDCHFm", 0.036, False),  # Direct
    ]
    
    available_components = []
    total_available_weight = 0.0
    missing_weight = 0.0
    
    # Issue: Relax strict bars check to 80% of requested bars
    MIN_BARS = int(bars * 0.8)
    
    for symbol, weight, invert in BASKET:
        rates = fetch_ohlcv(symbol, timeframe, bars=bars)
        if rates is not None and len(rates) >= MIN_BARS:
            available_components.append((symbol, weight, invert, rates))
            total_available_weight += weight
        else:
            missing_weight += weight
    
    if not available_components:
        return None, 0
        
    # Redistribute missing weight proportionally across available components
    weighted_closes = None
    for symbol, weight, invert, rates in available_components:
        # Calculate adjusted weight including redistributed portion
        adjusted_weight = weight + (weight / total_available_weight) * missing_weight
        closes = _close_array(rates)
        if closes is None or len(closes) < MIN_BARS:
            continue
        if invert:
            # Issue 3 fix: Handle division by zero for inverted pairs
            closes = np.where(closes > 0, 1.0 / closes, np.nan)
            if np.any(np.isnan(closes)):
                continue  # skip this pair for this scan
        component = closes * adjusted_weight
        if weighted_closes is None:
            weighted_closes = component
        else:
            # Align symbols with slightly different history lengths.
            min_len = min(len(weighted_closes), len(component))
            weighted_closes = weighted_closes[-min_len:]
            component = component[-min_len:]
            weighted_closes += component

    if weighted_closes is None or len(weighted_closes) < MIN_BARS:
        return None, 0

    return weighted_closes, len(available_components)  # array of synthetic DXY values, number of pairs used


def get_dxy_bias(timeframe="H1", bars=100, lookback=20):
    """
    Returns dxy_bias as 'bullish', 'bearish', or 'neutral'
    by comparing recent DXY slope and structure.
    """
    dxy, _ = get_synthetic_dxy(timeframe, bars)
    if dxy is None or len(dxy) < lookback:
        return "unavailable"

    recent = dxy[-lookback:]
    try:
        slope = np.polyfit(range(len(recent)), recent, 1)[0]
    except Exception:
        return "neutral"

    last = dxy[-1]
    mean_recent = np.mean(recent)
    # Issue 4 fix: Add minimum slope threshold
    mean_val = np.mean(recent)
    slope_pct = abs(slope) / mean_val if mean_val != 0 else 0
    MIN_SLOPE_PCT = 0.0001  # 0.01% per bar minimum
    
    if slope > 0 and last > mean_recent and slope_pct > MIN_SLOPE_PCT:
        return "bullish"
    elif slope < 0 and last < mean_recent and slope_pct > MIN_SLOPE_PCT:
        return "bearish"
    else:
        return "neutral"


def get_dxy_bias_from_array(dxy_values, lookback=20):
    """Accept pre-computed DXY array instead of re-fetching."""
    if dxy_values is None or len(dxy_values) < lookback:
        return "unavailable"
    recent = dxy_values[-lookback:]
    try:
        slope = np.polyfit(range(len(recent)), recent, 1)[0]
    except Exception:
        return "neutral"
    last = dxy_values[-1]
    mean_recent = np.mean(recent)
    # Issue 4 fix: Add minimum slope threshold
    mean_val = np.mean(recent)
    slope_pct = abs(slope) / mean_val if mean_val != 0 else 0
    MIN_SLOPE_PCT = 0.0001  # 0.01% per bar minimum
    
    if slope > 0 and last > mean_recent and slope_pct > MIN_SLOPE_PCT:
        return "bullish"
    elif slope < 0 and last < mean_recent and slope_pct > MIN_SLOPE_PCT:
        return "bearish"
    else:
        return "neutral"


def _gold_direction_snapshot(symbol: str, silent: bool = False) -> dict[str, object]:
    """Get gold direction from market structure analysis"""
    df = fetch_ohlcv(symbol, "H1", bars=220)
    result = analyze_market_structure(df, silent=silent) if df is not None and not df.empty else None
    if not result:
        return {
            "direction": "neutral",
            "state": "range",
            "lead_bias": None,
            "confidence": 0,
        }

    return {
        "direction": result.get("structure", "neutral"),
        "state": result.get("state", "range"),
        "lead_bias": (result.get("lead_bias") or {}).get("direction"),
        "confidence": int(result.get("confidence", 0) or 0),
    }


def analyze_dxy_correlation(symbol: str = "XAUUSDm", silent: bool = False) -> dict[str, object]:
    """
    Returns the full DXY block for the log and scorer.
    Uses synthetic DXY implementation.
    """
    gold = _gold_direction_snapshot(symbol, silent=silent)
    gold_dir = str(gold["direction"])
    gold_state = str(gold["state"])
    gold_lead_bias = gold.get("lead_bias")

    # Try to get synthetic DXY with pair count
    dxy_values, basket_pairs_used = get_synthetic_dxy("H1", 100)
    if dxy_values is None:
        return {
            "available": False,
            "source": "unavailable",
            "dxy_bias": "unavailable",
            "gold_bias": gold_dir,
            "relationship": "unavailable",
            "confirms_bias": False,
            "reduce_size": False,
            "basket_pairs_used": None,
            "note": "No DXY symbol available from MT5.",
        }

    dxy_dir = get_dxy_bias_from_array(dxy_values)

    if dxy_dir == "unavailable":
        return {
            "available": False,
            "source": "synthetic_basket",
            "dxy_bias": "unavailable",
            "gold_bias": gold_dir,
            "relationship": "unavailable",
            "confirms_bias": False,
            "reduce_size": False,
            "basket_pairs_used": basket_pairs_used,
            "note": "Synthetic DXY calculation failed.",
        }

    # Inverse relationship logic
    confirms = (
        (gold_dir == "bullish" and dxy_dir == "bearish")
        or (gold_dir == "bearish" and dxy_dir == "bullish")
    )
    
    # Divergence: DXY moves one way, but Gold shows strength in opposite direction via lead bias/state
    divergence = (
        (dxy_dir == "bullish" and gold_state in ("range", "transition") and gold_lead_bias == "bullish")
        or (dxy_dir == "bearish" and gold_state in ("range", "transition") and gold_lead_bias == "bearish")
    )
    
    conflicts = (
        gold_dir in ("bullish", "bearish")
        and dxy_dir in ("bullish", "bearish")
        and not confirms
        and not divergence
    )

    if confirms:
        relationship = "inverse_confirmed"
    elif divergence:
        relationship = "divergence"
    elif conflicts:
        relationship = "conflict"
    else:
        relationship = "neutral"

    return {
        "available": True,
        "source": "synthetic_basket",
        "dxy_bias": dxy_dir,
        "gold_bias": gold_dir,
        "gold_state": gold_state,
        "gold_lead_bias": gold_lead_bias,
        "relationship": relationship,
        "confirms_bias": confirms,          # only true inverse
        "reduce_size": conflicts,            # same-direction conflict
        "basket_pairs_used": basket_pairs_used,
        "note": (
            "Inverse correlation confirmed."
            if confirms
            else "DXY/Gold divergence noted."
            if divergence
            else "DXY conflicts with gold bias."
            if conflicts
            else "No meaningful DXY edge."
        ),
    }
