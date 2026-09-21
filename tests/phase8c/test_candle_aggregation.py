"""Tests for causal tick-to-candle aggregation logic."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bot.acquisition.models import AcquisitionError
from bot.acquisition.candle_pipeline import _WindowAccumulator


UTC = timezone.utc


def test_window_accumulator_happy_path():
    acc = _WindowAccumulator(
        open_time=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 10, 5, tzinfo=UTC),
        timeframe="M5",
    )
    
    assert acc.is_empty()
    
    # Tick 1
    acc.add_tick(
        timestamp=datetime(2024, 1, 1, 10, 1, tzinfo=UTC),
        bid=Decimal("2000.10"),
        ask=Decimal("2000.20"),
        package_id="pkg1",
    )
    
    # Tick 2 (Higher High)
    acc.add_tick(
        timestamp=datetime(2024, 1, 1, 10, 2, tzinfo=UTC),
        bid=Decimal("2000.50"),
        ask=Decimal("2000.60"),
        package_id="pkg1",
    )
    
    # Tick 3 (Lower Low)
    acc.add_tick(
        timestamp=datetime(2024, 1, 1, 10, 3, tzinfo=UTC),
        bid=Decimal("1999.90"),
        ask=Decimal("2000.00"),
        package_id="pkg2",
    )
    
    assert not acc.is_empty()
    record = acc.to_record()
    
    assert record["symbol"] == "XAUUSDm"
    assert record["timeframe"] == "M5"
    assert record["tick_count"] == 3
    assert record["source_package_ids"] == ["pkg1", "pkg2"]
    
    # OHLC Bid
    assert record["bid_open"] == "2000.10000000"
    assert record["bid_high"] == "2000.50000000"
    assert record["bid_low"] == "1999.90000000"
    assert record["bid_close"] == "1999.90000000"
    
    # OHLC Ask
    assert record["ask_open"] == "2000.20000000"
    assert record["ask_high"] == "2000.60000000"
    assert record["ask_low"] == "2000.00000000"
    assert record["ask_close"] == "2000.00000000"
    
    # Spreads: 0.10, 0.10, 0.10
    assert record["spread_min"] == "0.10000000"
    assert record["spread_max"] == "0.10000000"
    assert record["spread_median"] == "0.10000000"


def test_window_accumulator_empty():
    acc = _WindowAccumulator(
        open_time=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 10, 5, tzinfo=UTC),
        timeframe="M5",
    )
    with pytest.raises(AcquisitionError, match="Cannot materialise an empty window"):
        acc.to_record()


def test_spread_median_even_number_of_ticks():
    acc = _WindowAccumulator(
        open_time=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 10, 5, tzinfo=UTC),
        timeframe="M5",
    )
    
    spreads_to_add = ["0.10", "0.20", "0.30", "0.40"]
    for s in spreads_to_add:
        # constant bid, varying ask to test spread
        acc.add_tick(
            timestamp=datetime(2024, 1, 1, 10, 1, tzinfo=UTC),
            bid=Decimal("2000.00"),
            ask=Decimal("2000.00") + Decimal(s),
            package_id="pkg",
        )
    
    record = acc.to_record()
    # middle values are 0.20 and 0.30, average is 0.25
    assert record["spread_median"] == "0.25000000"
