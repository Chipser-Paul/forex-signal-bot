from __future__ import annotations

import pandas as pd
import pytest

from bot.data.market_data import fetch_ohlcv


def _rate(open_time: str, close: float) -> dict[str, float | int]:
    timestamp = int(pd.Timestamp(open_time).timestamp())
    return {
        "time": timestamp,
        "open": close,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "tick_volume": 100,
    }


@pytest.mark.unit
def test_live_fetch_excludes_unexpected_active_candle(fake_mt5):
    fake_mt5.rates = [
        _rate("2026-01-01T11:55:00Z", 100.0),
        _rate("2026-01-01T12:00:00Z", 101.0),
    ]
    result = fetch_ohlcv(
        "XAUUSDm",
        "M5",
        bars=2,
        decision_timestamp="2026-01-01T12:02:00Z",
    )
    assert list(result["open_time"]) == [pd.Timestamp("2026-01-01T11:55:00Z")]
    assert (result["available_at"] <= pd.Timestamp("2026-01-01T12:02:00Z")).all()


@pytest.mark.unit
def test_live_fetch_uses_closed_candle_offset(fake_mt5):
    fake_mt5.rates = [_rate("2026-01-01T11:55:00Z", 100.0)]
    fetch_ohlcv(
        "XAUUSDm",
        "M5",
        bars=1,
        decision_timestamp="2026-01-01T12:00:00Z",
    )
    call = next(item for item in fake_mt5.calls if item[0] == "copy_rates_from_pos")
    assert call[1][2] == 1


@pytest.mark.unit
def test_include_current_request_still_excludes_uncertain_final_row(fake_mt5):
    fake_mt5.rates = [
        _rate("2026-01-01T11:55:00Z", 100.0),
        _rate("2026-01-01T12:00:00Z", 101.0),
    ]
    result = fetch_ohlcv(
        "XAUUSDm",
        "M5",
        bars=2,
        include_current=True,
        decision_timestamp="2026-01-01T12:00:00Z",
    )
    call = next(item for item in fake_mt5.calls if item[0] == "copy_rates_from_pos")
    assert call[1][2] == 0
    assert list(result["open_time"]) == [pd.Timestamp("2026-01-01T11:55:00Z")]


@pytest.mark.unit
def test_empty_live_response_is_safe(fake_mt5):
    fake_mt5.rates = []
    assert fetch_ohlcv("XAUUSDm", "M5", bars=10) is None


@pytest.mark.unit
def test_short_closed_response_is_utc_and_explicit(fake_mt5):
    fake_mt5.rates = [_rate("2026-01-01T11:55:00Z", 100.0)]
    result = fetch_ohlcv(
        "XAUUSDm",
        "M5",
        bars=1,
        decision_timestamp="2026-01-01T12:00:00Z",
    )
    assert len(result) == 1
    assert str(result["open_time"].dtype) == "datetime64[ns, UTC]"
    assert result["available_at"].iloc[0] == pd.Timestamp("2026-01-01T12:00:00Z")


@pytest.mark.unit
def test_live_fetch_never_initializes_or_orders(fake_mt5):
    fake_mt5.rates = [_rate("2026-01-01T11:55:00Z", 100.0)]
    fetch_ohlcv(
        "XAUUSDm",
        "M5",
        bars=1,
        decision_timestamp="2026-01-01T12:00:00Z",
    )
    prohibited = {"initialize", "account_info", "order_check", "order_send"}
    assert not [call for call in fake_mt5.calls if call[0] in prohibited]
