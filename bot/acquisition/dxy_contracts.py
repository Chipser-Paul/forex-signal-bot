"""Phase 8D causal DXY development-input contracts (pure, offline-safe).

Defines the development-only constituent-bar contract, the deterministic
H1-bar normalization for guarded read-only MT5 retrieval, canonical record
hashing, and the causal DXY series computation that mirrors the committed
``build_synthetic_dxy_from_frames`` semantics exactly (same formula, same
exponent signs, same multiplication order, same 1-hour staleness bound on
``available_at``).

The development interval is [2024-01-01T00:00:00Z, 2025-01-01T00:00:00Z).
No record with an availability timestamp on or after 2025-01-01T00:00:00Z
may be produced: the final 2024-12-31T23:00Z H1 bar completes exactly at the
holdout boundary and is therefore excluded, never accessed for validation.

DXY is built only from the six canonical constituent closes using the
unchanged committed formula:

    DXY = 50.14348112 * EURUSD^-0.576 * USDJPY^0.136 * GBPUSD^-0.119
                       * USDCAD^0.091 * USDSEK^0.042 * USDCHF^0.036

Missing or stale constituents yield explicit rejections (DATA_UNSAFE
semantics); no value is ever fabricated or forward-filled.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Sequence

from bot.analysis.dxy_filter import DXY_BASKET, DXY_SCALE
from bot.validation.models import canonical_data

from .models import AcquisitionError

UTC = timezone.utc

DEVELOPMENT_START = datetime(2024, 1, 1, tzinfo=UTC)
DEVELOPMENT_END = datetime(2025, 1, 1, tzinfo=UTC)
H1_DURATION_MS = 3_600_000
H1_DURATION = timedelta(hours=1)

CLASSIFICATION = "DEVELOPMENT_ONLY"
LABEL = "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE"
CONSTITUENT_SCHEMA_VERSION = "phase8d.constituent-bar.v1"
DXY_SCHEMA_VERSION = "phase8d.causal-dxy.v1"
PROVENANCE_ID = "mt5-read-only-h1-bars-v1"

TIMEFRAME = "H1"

# Canonical constituent -> broker symbol mapping (verified against
# symbol_info currency fields before any acquisition).
DXY_SYMBOL_MAP: dict[str, str] = {
    "EURUSD": "EURUSDm",
    "USDJPY": "USDJPYm",
    "GBPUSD": "GBPUSDm",
    "USDCAD": "USDCADm",
    "USDSEK": "USDSEKm",
    "USDCHF": "USDCHFm",
}

# Exact currency_base/currency_profit expectations used to verify that each
# broker symbol really is the intended analytical pair.
MAPPING_CURRENCY_EXPECTATIONS: dict[str, tuple[str, str]] = {
    "EURUSD": ("EUR", "USD"),
    "USDJPY": ("USD", "JPY"),
    "GBPUSD": ("GBP", "USD"),
    "USDCAD": ("USD", "CAD"),
    "USDSEK": ("USD", "SEK"),
    "USDCHF": ("USD", "CHF"),
}

# Canonical exponent per constituent.  DXY_BASKET carries broker symbols and
# sign flags; map them onto the canonical constituent names in the same order.
_BROKER_TO_CANONICAL = {broker: canon for canon, broker in DXY_SYMBOL_MAP.items()}
DXY_EXPONENTS: tuple[tuple[str, float], ...] = tuple(
    (_BROKER_TO_CANONICAL[symbol], -weight if invert else weight)
    for symbol, weight, invert in DXY_BASKET
)
DXY_CONSTITUENT_ORDER: tuple[str, ...] = tuple(
    _BROKER_TO_CANONICAL[symbol] for symbol, _weight, _invert in DXY_BASKET
)


def assert_development_interval(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Fail closed unless [start, end) is UTC-aware and inside development."""
    from .models import utc_datetime

    start = utc_datetime(start, "development start")
    end = utc_datetime(end, "development end")
    if end <= start:
        raise AcquisitionError("DXY_INTERVAL_NOT_INCREASING")
    if start < DEVELOPMENT_START or end > DEVELOPMENT_END:
        raise AcquisitionError("DXY_INTERVAL_OUTSIDE_DEVELOPMENT_YEAR")
    return start, end


def iter_development_month_chunks() -> tuple[tuple[datetime, datetime], ...]:
    """Deterministic monthly chunks covering the 2024 development year."""
    chunks: list[tuple[datetime, datetime]] = []
    month = DEVELOPMENT_START
    while month < DEVELOPMENT_END:
        if month.month == 12:
            nxt = datetime(month.year + 1, 1, 1, tzinfo=UTC)
        else:
            nxt = datetime(month.year, month.month + 1, 1, tzinfo=UTC)
        chunks.append((month, min(nxt, DEVELOPMENT_END)))
        month = nxt
    return tuple(chunks)


def ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def from_ms(value_ms: int) -> datetime:
    return datetime.fromtimestamp(value_ms / 1000, tz=UTC)


def iso_z(value_ms: int) -> str:
    return from_ms(value_ms).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(
        canonical_data(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


# ---------------------------------------------------------------------------
# Constituent-bar normalization (guarded read-only MT5 rates)
# ---------------------------------------------------------------------------

_RATE_FIELDS = ("open", "high", "low", "close")


def _finite_positive_float(value: object, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AcquisitionError(f"DXY_BAR_FIELD_NOT_NUMERIC: {name}") from exc
    import math

    if not math.isfinite(number) or number <= 0:
        raise AcquisitionError(f"DXY_BAR_FIELD_NOT_POSITIVE_FINITE: {name}")
    return number


def normalize_rate_chunk(
    canonical_symbol: str,
    broker_symbol: str,
    rates: object,
    chunk_start: datetime,
    chunk_end: datetime,
    *,
    retrieved_utc: datetime,
    terminal_build: str | None,
) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
    """Normalize one raw MT5 rates response into contract bar records.

    Returns ``(records, diagnostics)`` where diagnostics capture empty and
    null responses distinctly.  Records are filtered to open times within
    ``[chunk_start, chunk_end)`` and availability strictly before the
    development end, so the holdout boundary is never crossed.  Duplicate
    open times, disorder, non-finite/non-positive fields and OHLC violations
    fail closed.
    """
    import numpy as np

    chunk_start, chunk_end = assert_development_interval(chunk_start, chunk_end)
    if canonical_symbol not in DXY_SYMBOL_MAP or DXY_SYMBOL_MAP[canonical_symbol] != broker_symbol:
        raise AcquisitionError("DXY_SYMBOL_MAPPING_UNVERIFIED")

    if rates is None:
        return (), {"response_class": "NULL_RESPONSE", "returned_count": 0}
    try:
        rows = len(rates)
    except TypeError as exc:
        raise AcquisitionError("DXY_RATES_RESPONSE_MALFORMED") from exc
    if rows == 0:
        return (), {"response_class": "EMPTY_RESPONSE", "returned_count": 0}

    chunk_start_ms = ms(chunk_start)
    chunk_end_ms = ms(chunk_end)
    development_end_ms = ms(DEVELOPMENT_END)

    try:
        times = np.asarray(rates)["time"].astype("int64", casting="safe")
    except (TypeError, ValueError, KeyError) as exc:
        raise AcquisitionError("DXY_RATES_RESPONSE_MALFORMED") from exc

    records: list[dict[str, object]] = []
    for index in range(rows):
        open_time_ms = int(times[index]) * 1000
        if not chunk_start_ms <= open_time_ms < chunk_end_ms:
            continue
        available_at_ms = open_time_ms + H1_DURATION_MS
        if available_at_ms >= development_end_ms:
            # The bar completes at or beyond the holdout boundary.
            continue
        prices = {
            name: _finite_positive_float(rates[index][name], name) for name in _RATE_FIELDS
        }
        if (
            prices["high"] < max(prices["open"], prices["close"])
            or prices["low"] > min(prices["open"], prices["close"])
            or prices["high"] < prices["low"]
        ):
            raise AcquisitionError(f"DXY_BAR_OHLC_INVALID: {canonical_symbol}")

        tick_volume: float | None
        spread: float | None
        real_volume: float | None
        try:
            raw_tick_volume = rates[index]["tick_volume"]
            raw_spread = rates[index]["spread"]
            raw_real_volume = rates[index]["real_volume"]
        except (KeyError, TypeError, ValueError):
            tick_volume = spread = real_volume = None
        else:
            tick_volume = float(raw_tick_volume) if raw_tick_volume is not None else None
            spread = float(raw_spread) if raw_spread is not None else None
            real_volume = float(raw_real_volume) if raw_real_volume is not None else None
            for name, value in (
                ("tick_volume", tick_volume), ("spread", spread), ("real_volume", real_volume)
            ):
                if value is not None and value < 0:
                    raise AcquisitionError(f"DXY_BAR_AUX_FIELD_NEGATIVE: {name}")

        record: dict[str, object] = {
            "canonical_symbol": canonical_symbol,
            "broker_symbol": broker_symbol,
            "timeframe": TIMEFRAME,
            "open_time_ms": open_time_ms,
            "close_time_ms": available_at_ms,
            "available_at_ms": available_at_ms,
            "open": prices["open"],
            "high": prices["high"],
            "low": prices["low"],
            "close": prices["close"],
            "tick_volume": tick_volume,
            "spread": spread,
            "real_volume": real_volume,
            "provenance_id": PROVENANCE_ID,
            "retrieved_utc": retrieved_utc.isoformat().replace("+00:00", "Z"),
            "terminal_build": terminal_build,
            "source_interval_start": iso_z(chunk_start_ms),
            "source_interval_end": iso_z(chunk_end_ms),
            "sequence_id": f"{canonical_symbol}-{TIMEFRAME}-{open_time_ms}",
        }
        record["row_identity"] = constituent_row_identity(record)
        records.append(record)

    opens = [int(record["open_time_ms"]) for record in records]
    if opens != sorted(opens):
        raise AcquisitionError(f"DXY_BAR_ORDER_VIOLATION: {canonical_symbol}")
    if len(set(opens)) != len(opens):
        raise AcquisitionError(f"DXY_BAR_DUPLICATE_OPEN_TIME: {canonical_symbol}")
    return (
        tuple(records),
        {"response_class": "OK", "returned_count": len(records)},
    )


def canonical_constituent_record(record: Mapping[str, object]) -> dict[str, object]:
    """Canonical serialization shape of a constituent bar (floats via repr)."""
    return {
        "canonical_symbol": str(record["canonical_symbol"]),
        "broker_symbol": str(record["broker_symbol"]),
        "timeframe": str(record["timeframe"]),
        "open_time": iso_z(int(record["open_time_ms"])),
        "close_time": iso_z(int(record["close_time_ms"])),
        "available_at": iso_z(int(record["available_at_ms"])),
        "open": repr(float(record["open"])),
        "high": repr(float(record["high"])),
        "low": repr(float(record["low"])),
        "close": repr(float(record["close"])),
        "tick_volume": (
            None if record.get("tick_volume") is None else repr(float(record["tick_volume"]))
        ),
        "spread": None if record.get("spread") is None else repr(float(record["spread"])),
        "real_volume": (
            None if record.get("real_volume") is None else repr(float(record["real_volume"]))
        ),
        "sequence_id": str(record["sequence_id"]),
        "provenance_id": str(record["provenance_id"]),
    }


def constituent_row_identity(record: Mapping[str, object]) -> str:
    core = {
        "canonical_symbol": str(record["canonical_symbol"]),
        "broker_symbol": str(record["broker_symbol"]),
        "timeframe": str(record["timeframe"]),
        "open_time_ms": int(record["open_time_ms"]),
        "close_time_ms": int(record["close_time_ms"]),
        "open": repr(float(record["open"])),
        "high": repr(float(record["high"])),
        "low": repr(float(record["low"])),
        "close": repr(float(record["close"])),
        "tick_volume": (
            None if record.get("tick_volume") is None else repr(float(record["tick_volume"]))
        ),
        "spread": None if record.get("spread") is None else repr(float(record["spread"])),
        "real_volume": (
            None if record.get("real_volume") is None else repr(float(record["real_volume"]))
        ),
        "sequence_id": str(record["sequence_id"]),
    }
    return hashlib.sha256(_canonical_json(core).encode("ascii")).hexdigest()


def canonical_constituent_hash(records: Iterable[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(_canonical_json(canonical_constituent_record(record)).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def deduplicate_chunk_records(
    existing: Mapping[int, Mapping[str, object]],
    incoming: Sequence[Mapping[str, object]],
    canonical_symbol: str,
) -> dict[int, dict[str, object]]:
    """Merge monthly chunks deterministically; identical overlap is kept.

    The same H1 bar can be returned by adjacent monthly requests; only
    byte-identical rows (same identity and content) may overlap.  Conflicting
    duplicates fail closed.
    """
    merged: dict[int, dict[str, object]] = dict(existing)
    for record in incoming:
        open_time_ms = int(record["open_time_ms"])
        previous = merged.get(open_time_ms)
        if previous is None:
            merged[open_time_ms] = dict(record)
            continue
        if str(previous["row_identity"]) != str(record["row_identity"]):
            raise AcquisitionError(f"DXY_CHUNK_OVERLAP_CONFLICT: {canonical_symbol}")
    return merged


# ---------------------------------------------------------------------------
# Gap reporting
# ---------------------------------------------------------------------------

def compute_gap_report(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Missing H1 windows and gap runs for one symbol over the dev year.

    ``missing_window_count`` is measured against the full 2024 theoretical
    H1 calendar (8,784 windows in the leap year); ``gap_runs`` counts maximal
    consecutive missing-window runs between the first and last observed
    opens.  Missing windows stay missing — no forward filling.
    """
    theoretical = 8784
    opens = sorted(int(record["open_time_ms"]) for record in records)
    if not opens:
        return {
            "observed_windows": 0,
            "theoretical_windows": theoretical,
            "missing_window_count": theoretical,
            "gap_runs": 0,
            "first_open": None,
            "last_open": None,
        }
    observed = set(opens)
    gap_runs = 0
    previous: int | None = None
    for open_ms in opens:
        if previous is not None:
            missing_between = (open_ms - previous) // H1_DURATION_MS - 1
            if missing_between > 0:
                gap_runs += 1
        previous = open_ms
    return {
        "observed_windows": len(observed),
        "theoretical_windows": theoretical,
        "missing_window_count": theoretical - len(observed),
        "gap_runs": gap_runs,
        "first_open": iso_z(opens[0]),
        "last_open": iso_z(opens[-1]),
    }


# ---------------------------------------------------------------------------
# Causal DXY computation (mirrors build_synthetic_dxy_from_frames exactly)
# ---------------------------------------------------------------------------

def _fresh_close(
    bars: Sequence[Mapping[str, object]],
    anchor_ms: int,
) -> tuple[Mapping[str, object] | None, int | None, str | None]:
    """Latest bar with available_at <= anchor and age <= 1h (H1 duration)."""
    # bars are sorted by available_at ascending.
    low, high = 0, len(bars)
    while low < high:
        mid = (low + high) // 2
        if int(bars[mid]["available_at_ms"]) <= anchor_ms:
            low = mid + 1
        else:
            high = mid
    if low == 0:
        return None, None, "MISSING_CONSTITUENT"
    chosen = bars[low - 1]
    age_ms = anchor_ms - int(chosen["available_at_ms"])
    if age_ms > H1_DURATION_MS:
        return None, None, "STALE_CONSTITUENT"
    return chosen, age_ms, None


def compute_causal_dxy_rows(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    interval_start_ms: int | None = None,
    interval_end_ms: int | None = None,
) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
    """Compute the causal DXY series from six constituent close series.

    Anchors are the sorted union of all constituent availability timestamps
    inside the (optionally bounded) interval, exactly like the committed
    ``align_causal_observations`` anchor semantics.  An anchor is accepted
    only when all six constituents have a fresh (age <= 1h) observation at
    or before the anchor; otherwise the anchor is rejected with a stable
    reason and never fabricated.  Accepted rows record the six source row
    identities and alignment ages.
    """
    missing_symbols = [s for s in DXY_CONSTITUENT_ORDER if not bars_by_symbol.get(s)]
    if missing_symbols:
        raise AcquisitionError(f"DXY_CONSTITUENT_SERIES_EMPTY: {','.join(sorted(missing_symbols))}")
    for symbol in DXY_CONSTITUENT_ORDER:
        bars = bars_by_symbol[symbol]
        available = [int(bar["available_at_ms"]) for bar in bars]
        if available != sorted(available) or len(set(available)) != len(available):
            raise AcquisitionError(f"DXY_CONSTITUENT_SERIES_UNORDERED: {symbol}")

    start = DEVELOPMENT_START_MS if interval_start_ms is None else int(interval_start_ms)
    end = DEVELOPMENT_END_MS if interval_end_ms is None else int(interval_end_ms)
    anchors = sorted(
        {
            int(bar["available_at_ms"])
            for symbol in DXY_CONSTITUENT_ORDER
            for bar in bars_by_symbol[symbol]
            if start <= int(bar["available_at_ms"]) < end
        }
    )

    accepted: list[dict[str, object]] = []
    rejections: dict[str, int] = {}
    for anchor_ms in anchors:
        chosen: dict[str, Mapping[str, object]] = {}
        ages: dict[str, int] = {}
        reject_reason: str | None = None
        reject_symbol: str | None = None
        for symbol in DXY_CONSTITUENT_ORDER:
            bar, age_ms, reason = _fresh_close(bars_by_symbol[symbol], anchor_ms)
            if bar is None:
                reject_reason = reason
                reject_symbol = symbol
                break
            chosen[symbol] = bar
            ages[symbol] = int(age_ms)
        if reject_reason is not None:
            key = f"{reject_reason}:{reject_symbol}"
            rejections[key] = rejections.get(key, 0) + 1
            continue

        value = DXY_SCALE
        for symbol, exponent in DXY_EXPONENTS:
            value *= float(chosen[symbol]["close"]) ** exponent
        if value != value or value in (float("inf"), float("-inf")):
            raise AcquisitionError("DXY_VALUE_NON_FINITE")

        row: dict[str, object] = {
            "available_at_ms": anchor_ms,
            "dxy": value,
            "sources": {
                symbol: {
                    "row_identity": str(chosen[symbol]["row_identity"]),
                    "open_time_ms": int(chosen[symbol]["open_time_ms"]),
                    "age_ms": ages[symbol],
                }
                for symbol in DXY_CONSTITUENT_ORDER
            },
            "provenance_id": PROVENANCE_ID,
        }
        row["row_identity"] = dxy_row_identity(row)
        accepted.append(row)

    summary = {
        "anchor_count": len(anchors),
        "accepted_rows": len(accepted),
        "rejected_rows": sum(rejections.values()),
        "rejections_by_reason": dict(sorted(rejections.items())),
    }
    return tuple(accepted), summary


DEVELOPMENT_START_MS = ms(DEVELOPMENT_START)
DEVELOPMENT_END_MS = ms(DEVELOPMENT_END)


def dxy_row_identity(row_without_identity: Mapping[str, object]) -> str:
    core = {
        "available_at_ms": int(row_without_identity["available_at_ms"]),
        "dxy": repr(float(row_without_identity["dxy"])),
        "sources": {
            symbol: {
                "row_identity": str(values["row_identity"]),
                "open_time_ms": int(values["open_time_ms"]),
                "age_ms": int(values["age_ms"]),
            }
            for symbol, values in sorted(row_without_identity["sources"].items())
        },
    }
    return hashlib.sha256(_canonical_json(core).encode("ascii")).hexdigest()


def canonical_dxy_row(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "available_at": iso_z(int(row["available_at_ms"])),
        "dxy": repr(float(row["dxy"])),
        "sources": {
            symbol: {
                "row_identity": str(values["row_identity"]),
                "open_time": iso_z(int(values["open_time_ms"])),
                "age_ms": int(values["age_ms"]),
            }
            for symbol, values in sorted(row["sources"].items())
        },
        "provenance_id": str(row["provenance_id"]),
        "row_identity": str(row["row_identity"]),
    }


def canonical_dxy_hash(rows: Iterable[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(_canonical_json(canonical_dxy_row(row)).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()
