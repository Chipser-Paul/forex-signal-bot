"""Tests for causal timeframe boundaries."""

from datetime import datetime, timezone
import pytest

from bot.acquisition.models import AcquisitionError
from bot.acquisition.candle_pipeline import (
    window_open_time,
    window_close_time,
    timeframe_duration,
)


UTC = timezone.utc


def test_timeframe_durations():
    assert timeframe_duration("M5").total_seconds() == 300
    assert timeframe_duration("H1").total_seconds() == 3600
    assert timeframe_duration("D1").total_seconds() == 86400
    assert timeframe_duration("W1").total_seconds() == 7 * 86400


def test_m5_boundaries():
    # Exactly on boundary
    t1 = datetime(2024, 1, 1, 10, 5, 0, tzinfo=UTC)
    assert window_open_time(t1, "M5") == t1
    assert window_close_time(t1, "M5") == datetime(2024, 1, 1, 10, 10, 0, tzinfo=UTC)

    # Middle of window
    t2 = datetime(2024, 1, 1, 10, 7, 30, tzinfo=UTC)
    assert window_open_time(t2, "M5") == t1

    # Just before boundary
    t3 = datetime(2024, 1, 1, 10, 9, 59, 999000, tzinfo=UTC)
    assert window_open_time(t3, "M5") == t1


def test_h1_boundaries():
    t1 = datetime(2024, 1, 1, 10, 59, 59, tzinfo=UTC)
    assert window_open_time(t1, "H1") == datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)


def test_w1_boundaries_monday():
    # 2024-01-01 is a Monday
    monday = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    
    # Monday early morning
    t1 = datetime(2024, 1, 1, 5, 30, 0, tzinfo=UTC)
    assert window_open_time(t1, "W1") == monday
    
    # Wednesday
    t2 = datetime(2024, 1, 3, 12, 0, 0, tzinfo=UTC)
    assert window_open_time(t2, "W1") == monday
    
    # Sunday evening
    t3 = datetime(2024, 1, 7, 23, 59, 59, tzinfo=UTC)
    assert window_open_time(t3, "W1") == monday
    
    # Next Monday
    t4 = datetime(2024, 1, 8, 0, 0, 0, tzinfo=UTC)
    assert window_open_time(t4, "W1") == datetime(2024, 1, 8, 0, 0, 0, tzinfo=UTC)


def test_unsupported_timeframe():
    with pytest.raises(AcquisitionError, match="Unsupported timeframe"):
        window_open_time(datetime(2024, 1, 1, tzinfo=UTC), "INVALID")
