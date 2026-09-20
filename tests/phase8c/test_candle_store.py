"""Tests for causal bid/ask candle Parquet storage."""

import os
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal

import pytest

from bot.acquisition.models import AcquisitionError
from bot.acquisition.candle_store import ParquetBidAskCandleStore, _validate_record


UTC = timezone.utc


@pytest.fixture
def temp_store(tmp_path):
    return ParquetBidAskCandleStore(
        tmp_path, 
        maximum_output_bytes=100 * 1024**2,
        minimum_free_bytes=0,
    )


def test_validate_record_happy():
    # Construct a valid record
    rec = {
        "symbol": "XAUUSDm",
        "timeframe": "M5",
        "open_time_ms": 1000000,
        "close_time_ms": 1300000,
        "available_at_ms": 1300000,
        "bid_open": "2000.00",
        "bid_high": "2001.00",
        "bid_low": "1999.00",
        "bid_close": "2000.50",
        "ask_open": "2000.10",
        "ask_high": "2001.10",
        "ask_low": "1999.10",
        "ask_close": "2000.60",
        "tick_count": 10,
        "spread_min": "0.10",
        "spread_max": "0.10",
        "spread_median": "0.10",
        "spread_close": "0.10",
        "first_tick_ms": 1000050,
        "last_tick_ms": 1299950,
        "source_package_ids": ["pkg1"],
        "schema_version": "phase8c.bidask-candles.v1",
    }
    
    # Calculate identity
    from bot.acquisition.candle_pipeline import stable_candle_identity
    rec["candle_identity"] = stable_candle_identity(
        "XAUUSDm", "M5", 1000000, 1300000
    )
    
    validated = _validate_record(rec)
    assert validated["symbol"] == "XAUUSDm"
    assert validated["bid_open"] == Decimal("2000.00")


def test_validate_record_invariant_failures():
    # Base valid record
    rec = {
        "symbol": "XAUUSDm",
        "timeframe": "M5",
        "open_time_ms": 1000000,
        "close_time_ms": 1300000,
        "available_at_ms": 1300000,
        "bid_open": "2000.00",
        "bid_high": "2001.00",
        "bid_low": "1999.00",
        "bid_close": "2000.50",
        "ask_open": "2000.10",
        "ask_high": "2001.10",
        "ask_low": "1999.10",
        "ask_close": "2000.60",
        "tick_count": 10,
        "spread_min": "0.10",
        "spread_max": "0.10",
        "spread_median": "0.10",
        "spread_close": "0.10",
        "first_tick_ms": 1000050,
        "last_tick_ms": 1299950,
        "source_package_ids": ["pkg1"],
        "schema_version": "phase8c.bidask-candles.v1",
    }
    from bot.acquisition.candle_pipeline import stable_candle_identity
    rec["candle_identity"] = stable_candle_identity("XAUUSDm", "M5", 1000000, 1300000)

    # Cross quotes
    bad_cross = dict(rec)
    bad_cross["ask_close"] = "2000.00" # bid_close is 2000.50
    with pytest.raises(AcquisitionError, match="must be >="):
        _validate_record(bad_cross)
        
    # Bad OHLC
    bad_ohlc = dict(rec)
    bad_ohlc["bid_high"] = "1999.50" # lower than open
    with pytest.raises(AcquisitionError, match="bid_high must be >="):
        _validate_record(bad_ohlc)
        
    # Bad causality
    bad_causal = dict(rec)
    bad_causal["available_at_ms"] = 1299999 # before close
    with pytest.raises(AcquisitionError, match="available_at_ms \\(1299999\\) must be >="):
        _validate_record(bad_causal)


def test_candle_store_write_and_verify(temp_store):
    rec = {
        "symbol": "XAUUSDm",
        "timeframe": "M5",
        "open_time_ms": 1000000,
        "close_time_ms": 1300000,
        "available_at_ms": 1300000,
        "bid_open": "2000.00",
        "bid_high": "2001.00",
        "bid_low": "1999.00",
        "bid_close": "2000.50",
        "ask_open": "2000.10",
        "ask_high": "2001.10",
        "ask_low": "1999.10",
        "ask_close": "2000.60",
        "tick_count": 10,
        "spread_min": "0.10",
        "spread_max": "0.10",
        "spread_median": "0.10",
        "spread_close": "0.10",
        "first_tick_ms": 1000050,
        "last_tick_ms": 1299950,
        "source_package_ids": ["pkg1"],
        "schema_version": "phase8c.bidask-candles.v1",
    }
    from bot.acquisition.candle_pipeline import stable_candle_identity
    rec["candle_identity"] = stable_candle_identity("XAUUSDm", "M5", 1000000, 1300000)

    summary = temp_store.write("candles.parquet", [rec], partition_id="part1", timeframe="M5")
    
    assert summary.complete
    assert summary.record_count == 1
    
    # Non-overwriting check
    with pytest.raises(FileExistsError):
        temp_store.write("candles.parquet", [rec], partition_id="part2", timeframe="M5")
        
    # Verify readback
    verified = temp_store.verify("candles.parquet")
    assert verified.record_count == 1
    assert verified.canonical_content_sha256 == summary.canonical_content_sha256
