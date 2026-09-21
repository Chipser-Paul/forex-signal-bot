"""Tests for stable candle identity."""

from bot.acquisition.candle_pipeline import stable_candle_identity

def test_stable_identity():
    id1 = stable_candle_identity("XAUUSDm", "M5", 1000000, 1300000)
    id2 = stable_candle_identity("XAUUSDm", "M5", 1000000, 1300000)
    
    # Must be deterministic
    assert id1 == id2
    
    # Changing any part changes the hash
    assert stable_candle_identity("XAUUSD", "M5", 1000000, 1300000) != id1
    assert stable_candle_identity("XAUUSDm", "H1", 1000000, 1300000) != id1
    assert stable_candle_identity("XAUUSDm", "M5", 1000001, 1300000) != id1
    assert stable_candle_identity("XAUUSDm", "M5", 1000000, 1300001) != id1
    
    # Ensure stable (regression check - hash is fixed)
    # The JSON payload is: {"close_time_ms":1300000,"open_time_ms":1000000,"symbol":"XAUUSDm","timeframe":"M5"}
    import hashlib, json
    expected_payload = json.dumps({
        "symbol": "XAUUSDm",
        "timeframe": "M5",
        "open_time_ms": 1000000,
        "close_time_ms": 1300000,
    }, sort_keys=True, separators=(",", ":")).encode("ascii")
    expected_hash = hashlib.sha256(expected_payload).hexdigest()
    
    assert id1 == expected_hash
