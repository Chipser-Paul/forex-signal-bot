from __future__ import annotations

import math

import pytest

from bot.data import market_data


def _rate(timestamp: int, close: float) -> dict[str, float | int]:
    return {
        "time": timestamp,
        "open": close - 0.2,
        "high": close + 0.3,
        "low": close - 0.4,
        "close": close,
        "tick_volume": 100,
    }


@pytest.mark.unit
@pytest.mark.characterization
def test_live_fetch_requests_closed_candles_in_deterministic_order(fake_mt5):
    fake_mt5.rates = [_rate(1_700_000_000, 100.0), _rate(1_700_000_300, 101.0)]

    frame = market_data.fetch_ohlcv("XAUUSDm", "M5", bars=2)

    fetch_call = next(call for call in fake_mt5.calls if call[0] == "copy_rates_from_pos")
    assert fetch_call[1][2] == 1
    assert list(frame["close"]) == [100.0, 101.0]
    assert frame["time"].is_monotonic_increasing
    assert set(("time", "open", "high", "low", "close", "tick_volume")) <= set(frame.columns)


@pytest.mark.unit
@pytest.mark.characterization
def test_include_current_is_an_explicit_opt_in(fake_mt5):
    fake_mt5.rates = [_rate(1_700_000_000, 100.0)]
    market_data.fetch_ohlcv("XAUUSDm", "M5", bars=1, include_current=True)
    fetch_call = next(call for call in fake_mt5.calls if call[0] == "copy_rates_from_pos")
    assert fetch_call[1][2] == 0


@pytest.mark.unit
@pytest.mark.characterization
def test_normalization_rejects_duplicates_and_missing_ohlc_fields():
    incomplete_rates = [
        {"time": 1_700_000_000, "open": 1.0, "close": 1.1},
        {"time": 1_700_000_000, "open": 1.0, "close": 1.1},
    ]
    with pytest.raises(ValueError, match="missing required fields"):
        market_data.normalize_rates_frame(incomplete_rates)

    duplicate_rates = [_rate(1_700_000_000, 1.1), _rate(1_700_000_000, 1.2)]
    with pytest.raises(ValueError, match="Duplicate candle open_time"):
        market_data.normalize_rates_frame(duplicate_rates, final_candle_complete=True)


@pytest.mark.unit
def test_unsupported_timeframe_fails_before_an_mt5_call(fake_mt5):
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        market_data.fetch_ohlcv("XAUUSDm", "NOT_A_TIMEFRAME")
    assert not fake_mt5.calls


@pytest.mark.unit
def test_normalized_prices_are_finite_for_valid_fake_rates(fake_mt5):
    fake_mt5.rates = [_rate(1_700_000_000, 100.0)]
    frame = market_data.fetch_ohlcv("XAUUSDm", "M5", bars=1)
    assert all(math.isfinite(float(value)) for value in frame["close"])
