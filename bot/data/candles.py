from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable, Mapping

import numpy as np
import pandas as pd  # pyright: ignore[reportMissingModuleSource]


class CandleDataError(ValueError):
    """Raised when candle data cannot satisfy the canonical causal contract."""


@dataclass(frozen=True)
class TimeframeSpec:
    name: str
    mt5_attribute: str
    duration: timedelta
    pandas_frequency: str
    rank: int


TIMEFRAMES: dict[str, TimeframeSpec] = {
    "M1": TimeframeSpec("M1", "TIMEFRAME_M1", timedelta(minutes=1), "1min", 1),
    "M5": TimeframeSpec("M5", "TIMEFRAME_M5", timedelta(minutes=5), "5min", 2),
    "M15": TimeframeSpec("M15", "TIMEFRAME_M15", timedelta(minutes=15), "15min", 3),
    "M30": TimeframeSpec("M30", "TIMEFRAME_M30", timedelta(minutes=30), "30min", 4),
    "H1": TimeframeSpec("H1", "TIMEFRAME_H1", timedelta(hours=1), "1h", 5),
    "H4": TimeframeSpec("H4", "TIMEFRAME_H4", timedelta(hours=4), "4h", 6),
    "D1": TimeframeSpec("D1", "TIMEFRAME_D1", timedelta(days=1), "1D", 7),
    "W1": TimeframeSpec("W1", "TIMEFRAME_W1", timedelta(days=7), "1W-MON", 8),
}

PRICE_COLUMNS = ("open", "high", "low", "close")
VOLUME_COLUMNS = ("tick_volume", "real_volume")
CANONICAL_COLUMNS = (
    "open_time",
    "available_at",
    "time",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "real_volume",
    "timeframe",
)


@dataclass(frozen=True)
class CausalAlignment:
    frame: pd.DataFrame
    diagnostics: dict[str, dict[str, object]]


def get_timeframe_spec(timeframe: str) -> TimeframeSpec:
    name = str(timeframe).strip().upper()
    try:
        return TIMEFRAMES[name]
    except KeyError as exc:
        display_name = name if name.isalnum() and len(name) <= 8 else "<invalid>"
        raise CandleDataError(f"Unsupported timeframe: {display_name or '<empty>'}") from exc


def as_utc_timestamp(value: object, *, field: str = "timestamp") -> pd.Timestamp:
    """Return a UTC timestamp while rejecting ambiguous naive values."""
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise CandleDataError(f"Invalid {field}") from exc
    if pd.isna(timestamp):
        raise CandleDataError(f"Invalid {field}")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise CandleDataError(f"{field} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _empty_candle_frame(timeframe: str) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "open_time": pd.Series(dtype="datetime64[ns, UTC]"),
            "available_at": pd.Series(dtype="datetime64[ns, UTC]"),
            "time": pd.Series(dtype="datetime64[ns, UTC]"),
            "open": pd.Series(dtype="float64"),
            "high": pd.Series(dtype="float64"),
            "low": pd.Series(dtype="float64"),
            "close": pd.Series(dtype="float64"),
            "tick_volume": pd.Series(dtype="float64"),
            "spread": pd.Series(dtype="float64"),
            "real_volume": pd.Series(dtype="float64"),
            "timeframe": pd.Series(dtype="object"),
        }
    )
    frame.attrs.update(causal_normalized=True, timeframe=timeframe)
    return frame


def _extract_open_times(frame: pd.DataFrame) -> pd.Series:
    if "open_time" in frame.columns:
        values = frame["open_time"]
    elif "time" in frame.columns:
        values = frame["time"]
    elif isinstance(frame.index, pd.DatetimeIndex):
        values = pd.Series(frame.index, index=frame.index)
    else:
        raise CandleDataError("Candle data requires a time or open_time field")

    if pd.api.types.is_numeric_dtype(values.dtype):
        parsed = pd.to_datetime(values, unit="s", utc=True, errors="coerce")
        if parsed.isna().any():
            raise CandleDataError("Candle open_time contains invalid Unix seconds")
        return pd.Series(parsed, index=frame.index)

    if isinstance(values.dtype, pd.DatetimeTZDtype):
        return pd.Series(values.dt.tz_convert("UTC"), index=frame.index)
    if pd.api.types.is_datetime64_dtype(values.dtype):
        raise CandleDataError("candle open_time must be timezone-aware")

    normalized: list[pd.Timestamp] = []
    for value in values:
        normalized.append(as_utc_timestamp(value, field="candle open_time"))
    return pd.Series(normalized, index=frame.index, dtype="datetime64[ns, UTC]")


def normalize_candles(
    data: object,
    timeframe: str,
    *,
    final_candle_complete: bool = False,
    final_available_at: object | None = None,
) -> pd.DataFrame:
    """Normalize raw candles without mutating the caller's data.

    Observed next-open timestamps determine availability for every non-final row.
    The final row is retained only when its completion is explicit. In that case,
    a supplied boundary wins; otherwise the validated nominal duration is used.
    """
    spec = get_timeframe_spec(timeframe)
    source = pd.DataFrame(data).copy(deep=True)
    if source.empty:
        return _empty_candle_frame(spec.name)

    missing = [column for column in PRICE_COLUMNS if column not in source.columns]
    if missing:
        raise CandleDataError(f"Candle data missing required fields: {', '.join(missing)}")

    source["open_time"] = _extract_open_times(source)
    for column in PRICE_COLUMNS:
        try:
            source[column] = pd.to_numeric(source[column], errors="raise").astype(float)
        except (TypeError, ValueError) as exc:
            raise CandleDataError(f"Candle field {column} must be numeric") from exc

    for column in ("tick_volume", "spread", "real_volume"):
        if column not in source.columns:
            source[column] = np.nan
        else:
            try:
                source[column] = pd.to_numeric(source[column], errors="raise").astype(float)
            except (TypeError, ValueError) as exc:
                raise CandleDataError(f"Candle field {column} must be numeric") from exc

    source.sort_values("open_time", kind="mergesort", inplace=True)
    source.reset_index(drop=True, inplace=True)
    duplicate_mask = source["open_time"].duplicated(keep=False)
    if duplicate_mask.any():
        duplicate = source.loc[duplicate_mask, "open_time"].iloc[0].isoformat()
        raise CandleDataError(f"Duplicate candle open_time: {duplicate}")

    prices = source.loc[:, PRICE_COLUMNS].to_numpy(dtype=float)
    if not np.isfinite(prices).all():
        raise CandleDataError("Candle prices must be finite")
    invalid_ohlc = (
        (source["high"] < source["open"])
        | (source["high"] < source["close"])
        | (source["high"] < source["low"])
        | (source["low"] > source["open"])
        | (source["low"] > source["close"])
    )
    if invalid_ohlc.any():
        raise CandleDataError("Candle OHLC relationships are invalid")
    for column in VOLUME_COLUMNS:
        if (source[column].dropna() < 0).any():
            raise CandleDataError(f"Candle field {column} cannot be negative")

    source["available_at"] = source["open_time"].shift(-1)
    if final_available_at is not None:
        final_boundary = as_utc_timestamp(final_available_at, field="final_available_at")
        if final_boundary < source["open_time"].iloc[-1]:
            raise CandleDataError("final_available_at cannot precede the final open_time")
        source.loc[source.index[-1], "available_at"] = final_boundary
    elif final_candle_complete:
        source.loc[source.index[-1], "available_at"] = (
            source["open_time"].iloc[-1] + spec.duration
        )
    else:
        source = source.iloc[:-1].copy()

    if source.empty:
        return _empty_candle_frame(spec.name)

    source["available_at"] = pd.to_datetime(source["available_at"], utc=True)
    source["time"] = source["open_time"]
    source["timeframe"] = spec.name
    result = source.loc[:, CANONICAL_COLUMNS].copy()
    result.index = pd.DatetimeIndex(result["open_time"], name="candle_open_time")
    result.attrs.update(causal_normalized=True, timeframe=spec.name)
    _validate_normalized_frame(result)
    return result


def _validate_normalized_frame(frame: pd.DataFrame) -> None:
    missing = [column for column in CANONICAL_COLUMNS if column not in frame.columns]
    if missing:
        raise CandleDataError(f"Normalized candle data missing: {', '.join(missing)}")
    for column in ("open_time", "available_at"):
        dtype = frame[column].dtype
        if not isinstance(dtype, pd.DatetimeTZDtype) or str(dtype.tz) != "UTC":
            raise CandleDataError(f"{column} must be timezone-aware UTC")
        if frame[column].isna().any():
            raise CandleDataError(f"{column} cannot contain missing timestamps")
    if not frame["open_time"].is_monotonic_increasing:
        raise CandleDataError("Candle open_time must be sorted")
    if frame["open_time"].duplicated().any():
        raise CandleDataError("Candle open_time must be unique")
    if not frame["available_at"].is_monotonic_increasing:
        raise CandleDataError("Candle available_at must be sorted")
    if (frame["available_at"] < frame["open_time"]).any():
        raise CandleDataError("Candle availability cannot precede its open_time")


def causal_snapshot(
    candles: pd.DataFrame,
    decision_timestamp: object,
    *,
    max_bars: int | None = None,
) -> pd.DataFrame:
    """Select the most recent candles available at a UTC decision timestamp."""
    decision = as_utc_timestamp(decision_timestamp, field="decision_timestamp")
    if max_bars is not None and max_bars < 0:
        raise CandleDataError("max_bars cannot be negative")
    if candles.empty:
        return candles.copy(deep=True)
    if not candles.attrs.get("causal_normalized"):
        _validate_normalized_frame(candles)

    end = int(candles["available_at"].searchsorted(decision, side="right"))
    start = 0 if max_bars is None else max(0, end - max_bars)
    snapshot = candles.iloc[start:end].copy(deep=True)
    snapshot.attrs.update(candles.attrs)
    if not snapshot.empty and (snapshot["available_at"] > decision).any():
        raise CandleDataError("Causal snapshot contains future candle data")
    return snapshot


def causal_end_positions(
    candles: pd.DataFrame,
    decision_timestamps: Iterable[object],
) -> np.ndarray:
    """Vectorized exclusive end positions for repeated causal snapshots."""
    if not candles.empty and not candles.attrs.get("causal_normalized"):
        _validate_normalized_frame(candles)
    decisions = np.array(
        [as_utc_timestamp(value, field="decision_timestamp").value for value in decision_timestamps],
        dtype=np.int64,
    )
    available = candles["available_at"].astype("int64").to_numpy()
    return np.searchsorted(available, decisions, side="right")


def align_causal_observations(
    frames: Mapping[str, pd.DataFrame],
    decision_timestamp: object,
    *,
    value_column: str = "close",
    max_staleness: timedelta = timedelta(0),
) -> CausalAlignment:
    """Backward-align observations on availability time with bounded staleness."""
    decision = as_utc_timestamp(decision_timestamp, field="decision_timestamp")
    if max_staleness < timedelta(0):
        raise CandleDataError("max_staleness cannot be negative")
    if not frames:
        return CausalAlignment(pd.DataFrame(), {})

    snapshots: dict[str, pd.DataFrame] = {}
    anchor = pd.DatetimeIndex([], tz="UTC")
    diagnostics: dict[str, dict[str, object]] = {}
    for name in sorted(frames):
        frame = frames[name]
        if value_column not in frame.columns:
            raise CandleDataError(f"Observation {name} is missing {value_column}")
        snapshot = causal_snapshot(frame, decision)
        snapshots[name] = snapshot
        anchor = anchor.union(pd.DatetimeIndex(snapshot["available_at"]))

    anchor = anchor.sort_values()
    aligned = pd.DataFrame(index=anchor)
    aligned.index.name = "available_at"
    tolerance = pd.Timedelta(max_staleness)
    for name in sorted(snapshots):
        snapshot = snapshots[name]
        values = pd.Series(index=anchor, dtype=float)
        source_times = pd.Series(index=anchor, dtype="datetime64[ns, UTC]")
        if not snapshot.empty and len(anchor):
            observed_times = pd.DatetimeIndex(snapshot["available_at"])
            positions = observed_times.searchsorted(anchor, side="right") - 1
            valid = positions >= 0
            valid_indices = np.flatnonzero(valid)
            if len(valid_indices):
                chosen = positions[valid]
                chosen_times = observed_times.take(chosen)
                ages = anchor[valid] - chosen_times
                fresh = ages <= tolerance
                fresh_indices = valid_indices[fresh]
                if len(fresh_indices):
                    values.iloc[fresh_indices] = (
                        snapshot[value_column].astype(float).to_numpy()[chosen[fresh]]
                    )
                    source_times.iloc[fresh_indices] = chosen_times[fresh]
                stale_count = int((~fresh).sum())
            else:
                stale_count = 0
        else:
            stale_count = 0
        aligned[name] = values
        diagnostics[name] = {
            "missing_count": int(values.isna().sum()),
            "stale_rejections": stale_count,
            "latest_source_at": (
                source_times.dropna().iloc[-1].isoformat()
                if not source_times.dropna().empty
                else None
            ),
        }

    aligned.dropna(how="any", inplace=True)
    return CausalAlignment(aligned, diagnostics)
