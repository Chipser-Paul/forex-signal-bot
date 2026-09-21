from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from bot.data.candles import (
    CANONICAL_COLUMNS,
    CandleDataError,
    TIMEFRAMES,
    get_timeframe_spec,
    normalize_candles,
)
from tests.phase2.helpers import raw_candles


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "duration", "mt5_attribute", "pandas_frequency"),
    [
        ("M1", timedelta(minutes=1), "TIMEFRAME_M1", "1min"),
        ("M5", timedelta(minutes=5), "TIMEFRAME_M5", "5min"),
        ("M15", timedelta(minutes=15), "TIMEFRAME_M15", "15min"),
        ("M30", timedelta(minutes=30), "TIMEFRAME_M30", "30min"),
        ("H1", timedelta(hours=1), "TIMEFRAME_H1", "1h"),
        ("H4", timedelta(hours=4), "TIMEFRAME_H4", "4h"),
        ("D1", timedelta(days=1), "TIMEFRAME_D1", "1D"),
        ("W1", timedelta(days=7), "TIMEFRAME_W1", "1W-MON"),
    ],
)
def test_timeframe_metadata_is_central_and_validated(
    name, duration, mt5_attribute, pandas_frequency
):
    spec = get_timeframe_spec(name.lower())
    assert (spec.name, spec.duration, spec.mt5_attribute, spec.pandas_frequency) == (
        name,
        duration,
        mt5_attribute,
        pandas_frequency,
    )


@pytest.mark.unit
def test_unsupported_timeframe_is_rejected_without_echoing_data():
    with pytest.raises(CandleDataError, match="Unsupported timeframe: T2"):
        get_timeframe_spec("T2")
    with pytest.raises(CandleDataError) as error:
        get_timeframe_spec("invalid/value/that/should/not/be/echoed")
    assert "invalid/value" not in str(error.value)


@pytest.mark.unit
def test_timeframe_comparison_order_is_deterministic():
    assert [TIMEFRAMES[name].rank for name in TIMEFRAMES] == list(range(1, 9))


@pytest.mark.unit
def test_unix_seconds_are_explicitly_normalized_to_utc():
    frame = raw_candles("2026-01-01T00:00:00Z", 2, "5min")
    frame["time"] = frame["time"].astype("int64") // 1_000_000_000
    result = normalize_candles(frame, "M5", final_candle_complete=True)
    assert str(result["open_time"].dtype) == "datetime64[ns, UTC]"
    assert result["open_time"].iloc[0] == pd.Timestamp("2026-01-01T00:00:00Z")


@pytest.mark.unit
def test_aware_mixed_offsets_are_converted_to_utc():
    frame = raw_candles("2026-01-01T00:00:00Z", 2, "5min")
    frame["time"] = ["2026-01-01T01:05:00+01:00", "2026-01-01T00:00:00Z"]
    result = normalize_candles(frame, "M5", final_candle_complete=True)
    assert list(result["open_time"]) == [
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-01T00:05:00Z"),
    ]


@pytest.mark.unit
def test_naive_open_time_is_rejected():
    frame = raw_candles("2026-01-01T00:00:00Z", 2, "5min")
    frame["time"] = frame["time"].dt.tz_localize(None)
    with pytest.raises(CandleDataError, match="timezone-aware"):
        normalize_candles(frame, "M5", final_candle_complete=True)


@pytest.mark.unit
def test_normalization_sorts_without_mutating_input():
    source = raw_candles("2026-01-01T00:00:00Z", 3, "5min").iloc[::-1]
    before = source.copy(deep=True)
    result = normalize_candles(source, "M5", final_candle_complete=True)
    pd.testing.assert_frame_equal(source, before)
    assert result["open_time"].is_monotonic_increasing
    assert tuple(result.columns) == CANONICAL_COLUMNS


@pytest.mark.unit
def test_duplicate_open_times_are_rejected():
    frame = raw_candles("2026-01-01T00:00:00Z", 2, "5min")
    frame.loc[1, "time"] = frame.loc[0, "time"]
    with pytest.raises(CandleDataError, match="Duplicate candle open_time"):
        normalize_candles(frame, "M5", final_candle_complete=True)


@pytest.mark.unit
def test_missing_required_ohlc_field_is_rejected():
    frame = raw_candles("2026-01-01T00:00:00Z", 2, "5min").drop(columns="high")
    with pytest.raises(CandleDataError, match="missing required fields: high"):
        normalize_candles(frame, "M5", final_candle_complete=True)


@pytest.mark.unit
@pytest.mark.parametrize(
    "changes",
    [
        {"high": 99.0},
        {"low": 101.0},
        {"high": 99.0, "low": 101.0},
    ],
)
def test_invalid_ohlc_relationships_are_rejected(changes):
    frame = raw_candles("2026-01-01T00:00:00Z", 2, "5min")
    for column, value in changes.items():
        frame.loc[0, column] = value
    with pytest.raises(CandleDataError, match="OHLC relationships"):
        normalize_candles(frame, "M5", final_candle_complete=True)


@pytest.mark.unit
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_non_finite_prices_are_rejected(value):
    frame = raw_candles("2026-01-01T00:00:00Z", 2, "5min")
    frame.loc[0, "close"] = value
    with pytest.raises(CandleDataError, match="prices must be finite"):
        normalize_candles(frame, "M5", final_candle_complete=True)


@pytest.mark.unit
@pytest.mark.parametrize("column", ["tick_volume", "real_volume"])
def test_negative_volume_is_rejected(column):
    frame = raw_candles("2026-01-01T00:00:00Z", 2, "5min")
    frame[column] = [10, -1]
    with pytest.raises(CandleDataError, match=f"{column} cannot be negative"):
        normalize_candles(frame, "M5", final_candle_complete=True)


@pytest.mark.unit
def test_empty_data_has_the_deterministic_schema():
    result = normalize_candles(pd.DataFrame(), "M5")
    assert result.empty
    assert tuple(result.columns) == CANONICAL_COLUMNS
    assert str(result["available_at"].dtype) == "datetime64[ns, UTC]"


@pytest.mark.unit
def test_uncertain_final_candle_is_excluded():
    source = raw_candles("2026-01-01T00:00:00Z", 2, "5min")
    result = normalize_candles(source, "M5")
    assert len(result) == 1
    assert result["available_at"].iloc[0] == pd.Timestamp("2026-01-01T00:05:00Z")
    assert normalize_candles(source.iloc[:1], "M5").empty


@pytest.mark.unit
def test_explicit_final_boundary_is_respected():
    source = raw_candles("2026-01-01T00:00:00Z", 1, "5min")
    result = normalize_candles(
        source,
        "M5",
        final_available_at="2026-01-01T00:08:00Z",
    )
    assert result["available_at"].iloc[-1] == pd.Timestamp("2026-01-01T00:08:00Z")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("timeframe", "expected"),
    [
        ("M5", "2026-01-01T00:05:00Z"),
        ("H1", "2026-01-01T01:00:00Z"),
        ("H4", "2026-01-01T04:00:00Z"),
        ("D1", "2026-01-02T00:00:00Z"),
        ("W1", "2026-01-08T00:00:00Z"),
    ],
)
def test_nominal_final_availability_by_timeframe(timeframe, expected):
    source = raw_candles("2026-01-01T00:00:00Z", 1, "5min")
    result = normalize_candles(source, timeframe, final_candle_complete=True)
    assert result["available_at"].iloc[0] == pd.Timestamp(expected)


@pytest.mark.unit
def test_next_observed_open_handles_weekend_gap_conservatively():
    source = raw_candles("2026-01-02T00:00:00Z", 2, "1D")
    source.loc[1, "time"] = pd.Timestamp("2026-01-05T00:00:00Z")
    result = normalize_candles(source, "D1", final_candle_complete=True)
    assert result["available_at"].iloc[0] == pd.Timestamp("2026-01-05T00:00:00Z")
