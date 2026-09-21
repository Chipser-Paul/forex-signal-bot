from __future__ import annotations

import pandas as pd
import pytest

from backtests.shadow_mode_backtest import (
    _causal_timeframe_views,
    _normalize_historical_frame,
)
from bot.data.candles import CandleDataError, causal_snapshot
from tests.phase2.helpers import normalized_candles, raw_candles


def _historical_frames() -> dict[str, pd.DataFrame]:
    return {
        "W1": normalized_candles("2025-12-22T00:00:00Z", 3, "7D", "W1"),
        "D1": normalized_candles("2025-12-30T00:00:00Z", 5, "1D", "D1"),
        "H4": normalized_candles("2026-01-01T04:00:00Z", 5, "4h", "H4"),
        "H1": normalized_candles("2026-01-01T10:00:00Z", 8, "1h", "H1"),
        "M15": normalized_candles("2026-01-01T10:00:00Z", 20, "15min", "M15"),
    }


@pytest.mark.unit
def test_completed_m5_signal_candle_is_visible_at_its_close():
    m5 = normalized_candles("2026-01-01T12:00:00Z", 2, "5min", "M5")
    visible = causal_snapshot(m5, "2026-01-01T12:05:00Z")
    assert visible["open_time"].iloc[-1] == pd.Timestamp("2026-01-01T12:00:00Z")


@pytest.mark.unit
def test_kd_data_001_m5_decision_during_h1_excludes_current_h1():
    views, reason = _causal_timeframe_views(_historical_frames(), "2026-01-01T12:05:00Z")
    assert reason is None
    assert views["H1"]["open_time"].iloc[-1] == pd.Timestamp("2026-01-01T11:00:00Z")
    assert pd.Timestamp("2026-01-01T12:00:00Z") not in set(views["H1"]["open_time"])


@pytest.mark.unit
def test_h1_candle_becomes_visible_at_exact_close():
    views, _reason = _causal_timeframe_views(_historical_frames(), "2026-01-01T13:00:00Z")
    assert views["H1"]["open_time"].iloc[-1] == pd.Timestamp("2026-01-01T12:00:00Z")


@pytest.mark.unit
def test_m5_decision_during_h4_excludes_current_h4():
    views, _reason = _causal_timeframe_views(_historical_frames(), "2026-01-01T12:05:00Z")
    assert views["H4"]["open_time"].iloc[-1] == pd.Timestamp("2026-01-01T08:00:00Z")
    assert pd.Timestamp("2026-01-01T12:00:00Z") not in set(views["H4"]["open_time"])


@pytest.mark.unit
def test_h4_candle_becomes_visible_at_exact_close():
    views, _reason = _causal_timeframe_views(_historical_frames(), "2026-01-01T16:00:00Z")
    assert views["H4"]["open_time"].iloc[-1] == pd.Timestamp("2026-01-01T12:00:00Z")


@pytest.mark.unit
def test_d1_candle_becomes_visible_only_at_next_daily_boundary():
    before, _reason = _causal_timeframe_views(_historical_frames(), "2026-01-01T23:59:59Z")
    exact, _reason = _causal_timeframe_views(_historical_frames(), "2026-01-02T00:00:00Z")
    assert before["D1"]["open_time"].iloc[-1] == pd.Timestamp("2025-12-31T00:00:00Z")
    assert exact["D1"]["open_time"].iloc[-1] == pd.Timestamp("2026-01-01T00:00:00Z")


@pytest.mark.unit
def test_insufficient_completed_htf_history_has_deterministic_reason():
    frames = _historical_frames()
    frames["W1"] = frames["W1"].iloc[0:0]
    views, reason = _causal_timeframe_views(frames, "2026-01-01T12:05:00Z")
    assert views["W1"].empty
    assert reason == "insufficient_completed_htf_history:W1"


@pytest.mark.unit
def test_every_backtest_htf_view_satisfies_causal_invariant():
    decision = pd.Timestamp("2026-01-01T12:05:00Z")
    views, _reason = _causal_timeframe_views(_historical_frames(), decision)
    for view in views.values():
        assert (view["available_at"] <= decision).all()


@pytest.mark.unit
def test_historical_normalizer_excludes_uncertain_final_row():
    raw = raw_candles("2026-01-01T12:00:00Z", 2, "5min")
    result = _normalize_historical_frame(raw, "M5")
    assert len(result) == 1
    assert result["available_at"].iloc[-1] == pd.Timestamp("2026-01-01T12:05:00Z")


@pytest.mark.unit
def test_historical_normalizer_rejects_naive_timestamps():
    raw = raw_candles("2026-01-01T12:00:00Z", 2, "5min")
    raw["time"] = raw["time"].dt.tz_localize(None)
    with pytest.raises(CandleDataError, match="timezone-aware"):
        _normalize_historical_frame(raw, "M5")
