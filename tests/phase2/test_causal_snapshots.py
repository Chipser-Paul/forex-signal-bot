from __future__ import annotations

import pandas as pd
import pytest

from bot.data.candles import (
    CandleDataError,
    causal_end_positions,
    causal_snapshot,
    normalize_candles,
)
from tests.phase2.helpers import normalized_candles, raw_candles


@pytest.mark.unit
def test_exact_availability_boundary_is_inclusive():
    candles = normalized_candles("2026-01-01T12:00:00Z", 3, "5min", "M5")
    before = causal_snapshot(candles, "2026-01-01T12:04:59.999999Z")
    exact = causal_snapshot(candles, "2026-01-01T12:05:00Z")
    assert before.empty
    assert list(exact["open_time"]) == [pd.Timestamp("2026-01-01T12:00:00Z")]


@pytest.mark.unit
def test_snapshot_returns_last_completed_candle_and_maximum_lookback():
    candles = normalized_candles("2026-01-01T12:00:00Z", 5, "5min", "M5")
    result = causal_snapshot(candles, "2026-01-01T12:20:00Z", max_bars=2)
    assert list(result["open_time"]) == [
        pd.Timestamp("2026-01-01T12:10:00Z"),
        pd.Timestamp("2026-01-01T12:15:00Z"),
    ]


@pytest.mark.unit
def test_timestamp_before_history_returns_empty_result():
    candles = normalized_candles("2026-01-01T12:00:00Z", 2, "5min", "M5")
    assert causal_snapshot(candles, "2026-01-01T11:59:00Z").empty


@pytest.mark.unit
def test_snapshot_does_not_mutate_input():
    candles = normalized_candles("2026-01-01T12:00:00Z", 3, "5min", "M5")
    before = candles.copy(deep=True)
    causal_snapshot(candles, "2026-01-01T12:10:00Z", max_bars=1)
    pd.testing.assert_frame_equal(candles, before)


@pytest.mark.unit
def test_naive_decision_timestamp_is_rejected():
    candles = normalized_candles("2026-01-01T12:00:00Z", 2, "5min", "M5")
    with pytest.raises(CandleDataError, match="timezone-aware"):
        causal_snapshot(candles, pd.Timestamp("2026-01-01T12:05:00"))


@pytest.mark.unit
def test_unsorted_input_is_normalized_before_snapshot_selection():
    source = raw_candles("2026-01-01T12:00:00Z", 3, "5min").iloc[::-1]
    candles = normalize_candles(source, "M5", final_candle_complete=True)
    result = causal_snapshot(candles, "2026-01-01T12:10:00Z")
    assert result["open_time"].is_monotonic_increasing
    assert result["open_time"].iloc[-1] == pd.Timestamp("2026-01-01T12:05:00Z")


@pytest.mark.unit
def test_missing_interval_is_not_forward_filled_with_ohlc():
    source = raw_candles("2026-01-01T12:00:00Z", 3, "5min").drop(index=1)
    candles = normalize_candles(source, "M5", final_candle_complete=True)
    result = causal_snapshot(candles, "2026-01-01T12:10:00Z")
    assert list(result["open_time"]) == [pd.Timestamp("2026-01-01T12:00:00Z")]
    assert len(result) == 1


@pytest.mark.unit
def test_vectorized_end_positions_match_simple_correctness_oracle():
    candles = normalized_candles("2026-01-01T00:00:00Z", 20, "5min", "M5")
    decisions = pd.date_range("2025-12-31T23:59:00Z", periods=25, freq="4min")
    actual = causal_end_positions(candles, decisions)
    expected = [int((candles["available_at"] <= decision).sum()) for decision in decisions]
    assert actual.tolist() == expected


@pytest.mark.unit
def test_causal_invariant_holds_across_generated_decisions():
    candles = normalized_candles("2026-01-01T00:00:00Z", 50, "5min", "M5")
    decisions = pd.date_range("2026-01-01T00:00:00Z", periods=80, freq="3min")
    for decision in decisions:
        snapshot = causal_snapshot(candles, decision, max_bars=12)
        assert snapshot.empty or (snapshot["available_at"] <= decision).all()


@pytest.mark.unit
def test_negative_maximum_lookback_is_rejected():
    candles = normalized_candles("2026-01-01T00:00:00Z", 2, "5min", "M5")
    with pytest.raises(CandleDataError, match="max_bars cannot be negative"):
        causal_snapshot(candles, "2026-01-01T00:05:00Z", max_bars=-1)


@pytest.mark.unit
def test_session_gap_does_not_make_candle_visible_before_next_observed_open():
    source = raw_candles("2026-01-02T00:00:00Z", 2, "1D")
    source.loc[1, "time"] = pd.Timestamp("2026-01-05T00:00:00Z")
    candles = normalize_candles(source, "D1", final_candle_complete=True)
    assert causal_snapshot(candles, "2026-01-04T23:59:59Z").empty
    assert len(causal_snapshot(candles, "2026-01-05T00:00:00Z")) == 1
