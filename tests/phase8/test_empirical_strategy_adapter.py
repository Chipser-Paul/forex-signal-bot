from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from bot.analysis import bias_engine, liquidity_map
from bot.data.candles import TIMEFRAMES
from bot.strategy.models import StrategySide
from bot.validation.empirical_strategy_adapter import (
    EmpiricalMappingError, derive_causal_bias, prepare_causal_frames,
)


DECISION = datetime(2024, 6, 3, tzinfo=timezone.utc)
TIMEFRAMES_USED = ("M5", "M15", "H1", "H4", "D1", "W1")


def _frames(close: float = 11.0):
    frames = {}
    for timeframe in TIMEFRAMES_USED:
        spec = TIMEFRAMES[timeframe]
        dates = pd.date_range(
            end=pd.Timestamp(DECISION) - spec.duration,
            periods=22, freq=spec.pandas_frequency, tz="UTC",
        )
        frames[timeframe] = pd.DataFrame({
            "open_time": dates,
            "available_at": dates + spec.duration,
            "time": dates,
            "open": [10.0] * len(dates),
            "high": [12.0] * len(dates),
            "low": [8.0] * len(dates),
            "close": [close] * len(dates),
            "tick_volume": [1] * len(dates),
            "spread": [0] * len(dates),
            "real_volume": [0] * len(dates),
            "timeframe": [timeframe] * len(dates),
        })
    return frames


def _structure(frame, silent=False):
    direction = "bullish" if frame["close"].iloc[-1] > 10 else "bearish"
    return {
        "structure": direction, "state": "confirmed", "confidence": 80,
        "event": "BOS", "equal_highs": [], "equal_lows": [],
    }


@pytest.mark.parametrize("close,side", [(11.0, StrategySide.LONG), (9.0, StrategySide.SHORT)])
def test_bias_uses_same_production_reducer_on_live_and_causal_frames(monkeypatch, close, side):
    frames = _frames(close)
    monkeypatch.setattr(bias_engine, "analyze_market_structure", _structure)
    prepared = prepare_causal_frames(frames, DECISION)
    from bot.data import market_data

    monkeypatch.setattr(
        market_data, "fetch_batch",
        lambda requests: {(item.symbol, item.timeframe): prepared[item.timeframe] for item in requests},
    )
    offline = derive_causal_bias(frames, DECISION)
    live = bias_engine.get_bias_snapshot("XAUUSDm", silent=True)
    assert dict(offline.snapshot) == live
    assert dict(offline.resolution) == bias_engine.resolve_trade_bias(live)
    assert offline.requested_side is side
    assert live["htf_bias"]["contributors"]["W1"]["direction"] == (
        "bullish" if side is StrategySide.LONG else "bearish"
    )


def test_liquidity_map_live_wrapper_reuses_injected_frame_computation(monkeypatch):
    frames = prepare_causal_frames(_frames(), DECISION)
    monkeypatch.setattr(liquidity_map, "analyze_market_structure", _structure)
    from bot.data import market_data

    monkeypatch.setattr(
        market_data, "fetch_batch",
        lambda requests: {(item.symbol, item.timeframe): frames[item.timeframe] for item in requests},
    )
    assert liquidity_map.build_liquidity_map("XAUUSDm", silent=True) == (
        liquidity_map.build_liquidity_map_from_frames("XAUUSDm", frames, silent=True)
    )


def test_exact_availability_boundary_and_no_future_htf():
    frames = _frames()
    at_boundary = prepare_causal_frames(frames, DECISION)
    before = prepare_causal_frames(frames, DECISION - timedelta(microseconds=1))
    assert len(at_boundary["W1"]) == len(before["W1"]) + 1
    assert at_boundary["W1"]["available_at"].iloc[-1] == pd.Timestamp(DECISION)
    assert all((frame["available_at"] <= pd.Timestamp(DECISION)).all() for frame in at_boundary.values())
    assert all((frame["available_at"] < pd.Timestamp(DECISION)).all() for frame in before.values())


def test_missing_and_insufficient_history_fail_closed():
    frames = _frames()
    frames.pop("H4")
    with pytest.raises(EmpiricalMappingError, match="MISSING_OR_UNEXPECTED_TIMEFRAME"):
        prepare_causal_frames(frames, DECISION)
    frames = _frames()
    frames["W1"] = frames["W1"].iloc[-19:].copy()
    with pytest.raises(EmpiricalMappingError, match="INSUFFICIENT_CAUSAL_HISTORY:W1"):
        prepare_causal_frames(frames, DECISION)
