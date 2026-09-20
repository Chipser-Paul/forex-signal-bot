"""Tests for determinism in causal candle derivation."""

from datetime import datetime, timezone
from decimal import Decimal
import json

from bot.acquisition.candle_store import canonical_candle_hash


def test_canonical_content_hash_determinism():
    records = [
        {
            "symbol": "XAUUSDm",
            "timeframe": "M5",
            "open_time_ms": 1000000,
            "close_time_ms": 1300000,
            "available_at_ms": 1300000,
            "bid_open": Decimal("2000.00"),
            "bid_high": Decimal("2001.00"),
            "bid_low": Decimal("1999.00"),
            "bid_close": Decimal("2000.50"),
            "ask_open": Decimal("2000.10"),
            "ask_high": Decimal("2001.10"),
            "ask_low": Decimal("1999.10"),
            "ask_close": Decimal("2000.60"),
            "tick_count": 10,
            "candle_identity": "test_id_1"
        },
        {
            "symbol": "XAUUSDm",
            "timeframe": "M5",
            "open_time_ms": 1300000,
            "close_time_ms": 1600000,
            "available_at_ms": 1600000,
            "bid_open": Decimal("2000.50"),
            "bid_high": Decimal("2002.00"),
            "bid_low": Decimal("2000.00"),
            "bid_close": Decimal("2001.50"),
            "ask_open": Decimal("2000.60"),
            "ask_high": Decimal("2002.10"),
            "ask_low": Decimal("2000.10"),
            "ask_close": Decimal("2001.60"),
            "tick_count": 15,
            "candle_identity": "test_id_2"
        }
    ]
    
    hash1 = canonical_candle_hash(records)
    
    # Must be deterministic for identical input
    hash2 = canonical_candle_hash(records)
    assert hash1 == hash2
    
    # Check stable JSON ordering properties
    # Using floats instead of Decimals should still hash identical because of str() casting
    # inside canonical_candle_hash
    records_float = []
    for r in records:
        rf = dict(r)
        rf["bid_open"] = str(r["bid_open"])
        rf["bid_high"] = str(r["bid_high"])
        rf["bid_low"] = str(r["bid_low"])
        rf["bid_close"] = str(r["bid_close"])
        rf["ask_open"] = str(r["ask_open"])
        rf["ask_high"] = str(r["ask_high"])
        rf["ask_low"] = str(r["ask_low"])
        rf["ask_close"] = str(r["ask_close"])
        records_float.append(rf)
        
    hash3 = canonical_candle_hash(records_float)
    assert hash1 == hash3
