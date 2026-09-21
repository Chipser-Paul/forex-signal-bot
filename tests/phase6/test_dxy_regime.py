from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from bot.analysis.dxy_filter import DXY_BASKET, DXY_SCALE, build_synthetic_dxy_from_frames
from bot.strategy import DirectionState, MarketRegime, StrategyConfig, evaluate_dxy
from bot.strategy.regime import classify_regime
from tests.phase2.helpers import normalized_candles


def basket_frames(*, periods=25, start="2026-01-01T00:00:00Z"):
    bases = {"EURUSDm": 1.1, "USDJPYm": 140.0, "GBPUSDm": 1.25, "USDCADm": 1.35, "USDSEKm": 10.0, "USDCHFm": 0.9}
    return {
        symbol: normalized_candles(start, periods, "1h", "H1", base=base)
        for symbol, base in bases.items()
    }


@pytest.mark.unit
def test_official_style_geometric_dxy_formula():
    frames = basket_frames(periods=2)
    values, count, diagnostics = build_synthetic_dxy_from_frames(
        frames, "H1", 2, "2026-01-01T02:00:00Z"
    )
    expected = DXY_SCALE
    for symbol, weight, inverted in DXY_BASKET:
        expected *= float(frames[symbol]["close"].iloc[-1]) ** (-weight if inverted else weight)
    assert count == 6
    assert values is not None and values[-1] == pytest.approx(expected)
    assert diagnostics["formula"] == "official_style_geometric"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("symbol", "raises_index"),
    [("EURUSDm", False), ("USDJPYm", True), ("GBPUSDm", False), ("USDCADm", True), ("USDSEKm", True), ("USDCHFm", True)],
)
def test_each_constituent_has_documented_direction(symbol, raises_index):
    frames = basket_frames(periods=2)
    baseline, _, _ = build_synthetic_dxy_from_frames(frames, "H1", 2, "2026-01-01T02:00:00Z")
    changed = {key: value.copy() for key, value in frames.items()}
    changed[symbol].loc[changed[symbol].index[-1], "close"] *= 1.01
    updated, _, _ = build_synthetic_dxy_from_frames(changed, "H1", 2, "2026-01-01T02:00:00Z")
    assert bool(updated[-1] > baseline[-1]) is raises_index


@pytest.mark.unit
def test_missing_or_stale_dxy_constituent_is_data_unsafe():
    config = replace(StrategyConfig(), dxy_max_staleness=timedelta(minutes=30))
    missing = basket_frames()
    missing.pop("USDCHFm")
    assert evaluate_dxy(missing, "2026-01-02T01:00:00Z", config).state is DirectionState.DATA_UNSAFE
    stale = basket_frames()
    assert evaluate_dxy(stale, "2026-01-02T02:00:00Z", config).state is DirectionState.DATA_UNSAFE


def regime_frame(scale=1.0, widths=None, drift=0.0):
    widths = widths or [0.2] * 50
    closes = 100.0 + np.arange(len(widths)) * drift
    return pd.DataFrame({
        "open": closes * scale,
        "high": (closes + np.asarray(widths)) * scale,
        "low": (closes - np.asarray(widths)) * scale,
        "close": (closes + 0.01) * scale,
    })


@pytest.mark.unit
def test_normalized_atr_is_price_scale_invariant():
    config = StrategyConfig()
    first = classify_regime(regime_frame(drift=0.05), config)
    scaled = classify_regime(regime_frame(scale=100.0, drift=0.05), config)
    assert first.state is scaled.state
    assert first.normalized_atr == pytest.approx(scaled.normalized_atr)
    assert first.volatility_ratio == pytest.approx(scaled.volatility_ratio)


@pytest.mark.unit
def test_regime_warmup_flat_trend_and_expansion():
    config = StrategyConfig()
    assert classify_regime(regime_frame(widths=[0.2] * 20), config).state is MarketRegime.DATA_UNSAFE
    assert classify_regime(regime_frame(), config).state is MarketRegime.RANGING
    assert classify_regime(regime_frame(drift=0.2), config).state is MarketRegime.TRENDING_UP
    assert classify_regime(regime_frame(drift=-0.2), config).state is MarketRegime.TRENDING_DOWN
    widths = [0.2] * 45 + [4.0] * 5
    assert classify_regime(regime_frame(widths=widths), config).state is MarketRegime.HIGH_VOLATILITY


@pytest.mark.unit
@pytest.mark.parametrize("bad", [np.nan, np.inf, -1.0])
def test_regime_rejects_invalid_prices(bad):
    frame = regime_frame()
    frame.loc[frame.index[-1], "close"] = bad
    assert classify_regime(frame, StrategyConfig()).state is MarketRegime.DATA_UNSAFE
