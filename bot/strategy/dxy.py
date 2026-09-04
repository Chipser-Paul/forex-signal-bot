from __future__ import annotations

import math

import numpy as np
import pandas as pd

from bot.analysis.dxy_filter import build_synthetic_dxy_from_frames
from bot.data.candles import causal_snapshot

from .config import StrategyConfig
from .models import DirectionResult, DirectionState


def _direction(values: np.ndarray, config: StrategyConfig) -> DirectionResult:
    if len(values) < config.dxy_lookback_bars:
        return DirectionResult(DirectionState.DATA_UNSAFE, "insufficient_dxy_warmup")
    recent = np.asarray(values[-config.dxy_lookback_bars :], dtype=float)
    if not np.isfinite(recent).all() or np.any(recent <= 0):
        return DirectionResult(DirectionState.DATA_UNSAFE, "invalid_dxy_values")
    slope = float(np.polyfit(np.arange(len(recent), dtype=float), recent, 1)[0])
    mean_value = float(recent.mean())
    slope_fraction = slope / mean_value
    threshold = config.dxy_slope_threshold_fraction_per_bar
    if slope_fraction >= threshold and recent[-1] >= mean_value:
        return DirectionResult(DirectionState.BULLISH, "positive_normalized_slope", abs(slope_fraction))
    if slope_fraction <= -threshold and recent[-1] <= mean_value:
        return DirectionResult(DirectionState.BEARISH, "negative_normalized_slope", abs(slope_fraction))
    return DirectionResult(DirectionState.NEUTRAL, "normalized_slope_below_threshold", abs(slope_fraction))


def evaluate_dxy(
    frames: dict[str, pd.DataFrame],
    decision_at,
    config: StrategyConfig,
    *,
    timeframe: str = "H1",
    direct_frame: pd.DataFrame | None = None,
) -> DirectionResult:
    if direct_frame is not None:
        snapshot = causal_snapshot(
            direct_frame,
            decision_at,
            max_bars=config.dxy_lookback_bars,
        )
        if len(snapshot) < config.dxy_lookback_bars:
            return DirectionResult(DirectionState.DATA_UNSAFE, "direct_dxy_insufficient_or_stale")
        latest_age = pd.Timestamp(decision_at) - pd.Timestamp(snapshot["available_at"].iloc[-1])
        if latest_age > config.dxy_max_staleness:
            return DirectionResult(DirectionState.DATA_UNSAFE, "direct_dxy_stale")
        return _direction(snapshot["close"].to_numpy(dtype=float), config)

    mapped = {
        broker_symbol: frames[broker_symbol]
        for broker_symbol in config.dxy_symbol_map.values()
        if broker_symbol in frames
    }
    values, count, diagnostics = build_synthetic_dxy_from_frames(
        mapped,
        timeframe,
        config.dxy_lookback_bars,
        decision_at,
    )
    if values is None or count != len(config.dxy_symbol_map):
        return DirectionResult(
            DirectionState.DATA_UNSAFE,
            str(diagnostics.get("reason") or "dxy_unavailable"),
        )
    latest = diagnostics.get("latest_available_at")
    if latest is None or pd.Timestamp(decision_at) - pd.Timestamp(latest) > config.dxy_max_staleness:
        return DirectionResult(DirectionState.DATA_UNSAFE, "dxy_constituents_stale")
    return _direction(values, config)
