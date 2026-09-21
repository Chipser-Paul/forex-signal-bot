from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from bot.data.candles import (
    align_causal_observations,
    as_utc_timestamp,
    causal_snapshot,
    get_timeframe_spec,
)

# NOTE (Phase 8H import-safety): ``bot.data.market_data`` imports MetaTrader5
# at module level.  ``fetch_ohlcv`` is therefore imported inside the
# live-fetch helpers below so that importing this module (and the pure
# strategy layer that depends on it) never requires the MT5 terminal
# library.  Call-time behaviour is unchanged.


DXY_SYMBOL_CANDIDATES = (
    "DXY",
    "USDX", 
    "USDXm",
    "USDOLLAR",
    "USDX.i",
)

DXY_BASKET = (
    ("EURUSDm", 0.576, True),
    ("USDJPYm", 0.136, False),
    ("GBPUSDm", 0.119, True),
    ("USDCADm", 0.091, False),
    ("USDSEKm", 0.042, False),
    ("USDCHFm", 0.036, False),
)
DXY_SCALE = 50.14348112

def _resolve_dxy_symbol(symbol_candidates: tuple[str, ...] = DXY_SYMBOL_CANDIDATES) -> str | None:
    """Try to find a working DXY symbol from MT5"""
    from bot.data.market_data import fetch_ohlcv

    for candidate in symbol_candidates:
        df = fetch_ohlcv(candidate, "H1", bars=50)
        if df is not None and not df.empty:
            return candidate
    return None


def build_synthetic_dxy_from_frames(
    frames: dict[str, pd.DataFrame],
    timeframe: str,
    bars: int,
    decision_timestamp: object,
) -> tuple[np.ndarray | None, int, dict[str, object]]:
    """Build the official-style geometric DXY basket from causal closes."""
    spec = get_timeframe_spec(timeframe)
    decision = as_utc_timestamp(decision_timestamp, field="decision_timestamp")
    min_bars = max(2, int(bars * 0.8))
    usable: dict[str, pd.DataFrame] = {}
    missing: list[str] = []

    for symbol, weight, invert in DXY_BASKET:
        frame = frames.get(symbol)
        snapshot = (
            causal_snapshot(frame, decision, max_bars=bars)
            if frame is not None and not frame.empty
            else pd.DataFrame()
        )
        if len(snapshot) >= min_bars:
            usable[symbol] = snapshot
        else:
            missing.append(symbol)

    if missing:
        return None, len(usable), {
            "reason": "missing_required_components",
            "missing": tuple(sorted(missing)),
            "components": {},
        }

    alignment = align_causal_observations(
        usable,
        decision,
        max_staleness=spec.duration,
    )
    aligned = alignment.frame.tail(bars)
    if len(aligned) < min_bars:
        return None, len(usable), {
            "reason": "insufficient_aligned_history",
            "components": alignment.diagnostics,
        }

    values = np.full(len(aligned), DXY_SCALE, dtype=float)
    for symbol, weight, invert in DXY_BASKET:
        closes = aligned[symbol].astype(float).to_numpy()
        if not np.isfinite(closes).all() or np.any(closes <= 0):
            return None, len(usable), {
                "reason": f"invalid_component:{symbol}",
                "components": alignment.diagnostics,
            }
        exponent = -weight if invert else weight
        values *= np.power(closes, exponent)

    return values, len(usable), {
        "formula": "official_style_geometric",
        "reason": None,
        "rows": len(aligned),
        "latest_available_at": aligned.index[-1].isoformat(),
        "components": alignment.diagnostics,
    }


def get_synthetic_dxy(timeframe="H1", bars=100, decision_timestamp=None):
    """
    Build synthetic DXY from all 6 required pairs using geometric weights.
    Returns array of synthetic DXY values or None if insufficient data.
    """
    decision = as_utc_timestamp(
        decision_timestamp or datetime.now(timezone.utc),
        field="decision_timestamp",
    )
    from bot.data.market_data import fetch_ohlcv

    frames: dict[str, pd.DataFrame] = {}
    for symbol, _weight, _invert in DXY_BASKET:
        rates = fetch_ohlcv(
            symbol,
            timeframe,
            bars=bars,
            decision_timestamp=decision,
        )
        if rates is not None and not rates.empty:
            frames[symbol] = rates

    values, count, _diagnostics = build_synthetic_dxy_from_frames(
        frames,
        timeframe,
        bars,
        decision,
    )
    return values, count


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
    recent = np.asarray(dxy_values[-lookback:], dtype=float)
    if not np.isfinite(recent).all() or np.any(recent <= 0):
        return "unavailable"
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


def _gold_direction_snapshot(
    symbol: str,
    silent: bool = False,
    decision_timestamp: object | None = None,
) -> dict[str, object]:
    """Get gold direction from market structure analysis"""
    from strategies.smc_engine.market_structure import analyze_market_structure
    from bot.data.market_data import fetch_ohlcv

    df = fetch_ohlcv(
        symbol,
        "H1",
        bars=220,
        decision_timestamp=decision_timestamp,
    )
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


def analyze_dxy_correlation(
    symbol: str = "XAUUSDm", silent: bool = False,
    decision_timestamp: object | None = None,
) -> dict[str, object]:
    """
    Returns the full DXY block for the log and scorer.
    Uses synthetic DXY implementation.
    """
    decision = as_utc_timestamp(
        decision_timestamp or datetime.now(timezone.utc), field="decision_timestamp",
    )
    gold = _gold_direction_snapshot(
        symbol,
        silent=silent,
        decision_timestamp=decision,
    )
    # Try to get synthetic DXY with pair count
    dxy_values, basket_pairs_used = get_synthetic_dxy(
        "H1",
        100,
        decision_timestamp=decision,
    )
    return dxy_context_from_values(gold, dxy_values, basket_pairs_used)


def dxy_context_from_values(
    gold: dict[str, object], dxy_values: np.ndarray | None,
    basket_pairs_used: int,
) -> dict[str, object]:
    """Apply the existing correlation interpretation to acquired causal values."""
    gold_dir = str(gold["direction"])
    gold_state = str(gold["state"])
    gold_lead_bias = gold.get("lead_bias")
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
