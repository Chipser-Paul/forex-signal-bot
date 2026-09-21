from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .models import MarketRegime, RegimeResult


def _unsafe(reason: str) -> RegimeResult:
    return RegimeResult(MarketRegime.DATA_UNSAFE, None, None, None, reason)


def atr_series(frame: pd.DataFrame, period: int) -> pd.Series:
    required = {"high", "low", "close"}
    if frame is None or not required.issubset(frame.columns):
        return pd.Series(dtype=float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    previous = close.shift(1)
    true_range = pd.concat(
        (high - low, (high - previous).abs(), (low - previous).abs()),
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period, min_periods=period).mean()


def classify_regime(frame: pd.DataFrame, config: StrategyConfig) -> RegimeResult:
    required = {"open", "high", "low", "close"}
    if frame is None or not required.issubset(frame.columns):
        return _unsafe("missing_ohlc")
    minimum = max(
        config.atr_period_bars + config.regime_baseline_bars,
        config.regime_trend_lookback_bars,
    )
    if len(frame) < minimum:
        return _unsafe("insufficient_warmup")
    values = frame.loc[:, ["open", "high", "low", "close"]].astype(float)
    if not np.isfinite(values.to_numpy()).all() or (values <= 0).any().any():
        return _unsafe("invalid_price")
    if not (
        (values["high"] >= values["open"]).all()
        and (values["high"] >= values["close"]).all()
        and (values["high"] >= values["low"]).all()
        and (values["low"] <= values["open"]).all()
        and (values["low"] <= values["close"]).all()
    ):
        return _unsafe("invalid_ohlc")

    atr = atr_series(values, config.atr_period_bars)
    normalized = atr / values["close"]
    current_atr = float(atr.iloc[-1])
    current_normalized = float(normalized.iloc[-1])
    baseline = normalized.iloc[-(config.regime_baseline_bars + 1) : -1]
    if (
        not math.isfinite(current_atr)
        or current_atr <= 0
        or not math.isfinite(current_normalized)
        or current_normalized <= 0
        or len(baseline) < config.regime_baseline_bars
        or not np.isfinite(baseline.to_numpy()).all()
    ):
        return _unsafe("invalid_atr")
    baseline_mean = float(baseline.mean())
    if baseline_mean <= 0:
        return _unsafe("invalid_atr_baseline")

    volatility_ratio = current_normalized / baseline_mean
    lookback = values["close"].iloc[-config.regime_trend_lookback_bars :]
    trend_strength = (float(lookback.iloc[-1]) - float(lookback.iloc[0])) / current_atr
    if volatility_ratio >= config.high_volatility_ratio:
        state = MarketRegime.HIGH_VOLATILITY
        reason = "normalized_atr_at_or_above_high_boundary"
    elif trend_strength >= config.trend_strength_atr:
        state = MarketRegime.TRENDING_UP
        reason = "positive_close_displacement_at_or_above_trend_boundary"
    elif trend_strength <= -config.trend_strength_atr:
        state = MarketRegime.TRENDING_DOWN
        reason = "negative_close_displacement_at_or_above_trend_boundary"
    else:
        state = MarketRegime.RANGING
        reason = "trend_and_high_volatility_boundaries_not_met"
    return RegimeResult(
        state,
        current_normalized,
        volatility_ratio,
        trend_strength,
        reason,
    )
