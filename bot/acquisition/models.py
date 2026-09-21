from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Mapping


UTC = timezone.utc
EXECUTABLE_SYMBOL = "XAUUSDm"
DXY_BASE_SYMBOLS = ("EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF")
REQUESTED_START = datetime(2019, 1, 1, tzinfo=UTC)
REQUESTED_END = datetime(2026, 9, 1, tzinfo=UTC)
DEFAULT_OUTPUT_ROOT = Path(r"C:\Users\chips\forex-signal-bot-data\phase8")
DEFAULT_MAX_OUTPUT_BYTES = 50 * 1024**3
EXPORT_TOOL_VERSION = "phase8b-stage1-v3"


class AcquisitionError(RuntimeError):
    """Raised when acquisition cannot continue without weakening a guard."""


class ExportStatus(str, Enum):
    TOOL_VERIFIED = "TOOL_VERIFIED"
    TERMINAL_UNAVAILABLE = "TERMINAL_UNAVAILABLE"
    ACTIVE_BOT_DETECTED = "ACTIVE_BOT_DETECTED"
    INSUFFICIENT_DISK = "INSUFFICIENT_DISK"
    SYMBOL_MISSING = "SYMBOL_MISSING"
    MAPPING_AMBIGUOUS = "MAPPING_AMBIGUOUS"
    PARTIAL_EXPORT = "PARTIAL_EXPORT"
    EXPORT_COMPLETE = "EXPORT_COMPLETE"
    DEVELOPMENT_ONLY = "PACKAGE_DEVELOPMENT_ONLY"
    PACKAGE_REJECTED = "PACKAGE_REJECTED"
    READY_FOR_FINAL_VALIDATION = "PACKAGE_READY_FOR_FINAL_VALIDATION"


def utc_datetime(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AcquisitionError(f"{name} must be timezone-aware UTC")
    normalized = value.astimezone(UTC)
    if value.utcoffset() != UTC.utcoffset(value):
        raise AcquisitionError(f"{name} must be expressed in UTC")
    return normalized


def finite_positive(value: object, name: str, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AcquisitionError(f"{name} must be numeric") from exc
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        raise AcquisitionError(f"{name} must be {'non-negative' if allow_zero else 'positive'}")
    return number


@dataclass(frozen=True)
class ExportConfig:
    output_root: Path = DEFAULT_OUTPUT_ROOT
    start: datetime = REQUESTED_START
    end: datetime = REQUESTED_END
    maximum_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    tick_chunk_months: int = 1
    tick_chunk_days: int | None = None
    bulk_format: str = "gzip-jsonl"
    maximum_rows_per_tick_chunk: int = 5_000_000
    minimum_free_bytes: int = 15 * 1024**3
    sample_minutes: int = 15

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_root", Path(self.output_root))
        object.__setattr__(self, "start", utc_datetime(self.start, "export start"))
        object.__setattr__(self, "end", utc_datetime(self.end, "export end"))
        if self.end <= self.start:
            raise AcquisitionError("export interval must be increasing")
        if self.maximum_output_bytes <= 0 or self.tick_chunk_months < 1 or self.sample_minutes < 1:
            raise AcquisitionError("export budgets and chunk sizes must be positive")
        if self.tick_chunk_days is not None and self.tick_chunk_days < 1:
            raise AcquisitionError("tick chunk days must be positive")
        if self.maximum_rows_per_tick_chunk < 1 or self.minimum_free_bytes < 0:
            raise AcquisitionError("tick row and disk limits are invalid")
        if self.bulk_format not in {"gzip-jsonl", "parquet-zstd"}:
            raise AcquisitionError("bulk format must be gzip-jsonl or parquet-zstd")


@dataclass(frozen=True)
class SafeSymbolMetadata:
    symbol: str
    description: str
    currency_base: str
    currency_profit: str
    currency_margin: str
    digits: int
    point: float
    trade_tick_size: float
    trade_tick_value: float
    trade_tick_value_profit: float
    trade_tick_value_loss: float
    trade_contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    trade_stops_level: int
    trade_freeze_level: int
    filling_mode: int
    trade_exemode: int
    swap_long: float
    swap_short: float
    swap_mode: int
    swap_rollover3days: int
    exported_at: datetime
    provenance: str = "already-authenticated-demo-terminal-symbol-info"
    missing_fields: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.symbol or self.digits < 0:
            raise AcquisitionError("safe symbol metadata identity is invalid")
        for name in (
            "point", "trade_tick_size", "trade_contract_size", "volume_min", "volume_max", "volume_step"
        ):
            finite_positive(getattr(self, name), name)
        for name in ("trade_tick_value", "trade_tick_value_profit", "trade_tick_value_loss"):
            finite_positive(getattr(self, name), name, allow_zero=True)
        for name in ("swap_long", "swap_short"):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise AcquisitionError(f"{name} must be finite")
        object.__setattr__(self, "exported_at", utc_datetime(self.exported_at, "metadata export time"))


@dataclass(frozen=True)
class SymbolMapping:
    base_symbol: str
    broker_symbol: str
    description: str
    currency_base: str
    currency_profit: str
    digits: int
    point: float

    def __post_init__(self) -> None:
        if not self.base_symbol or not self.broker_symbol:
            raise AcquisitionError("symbol mapping identity is required")
        finite_positive(self.point, "mapping point")


@dataclass(frozen=True)
class DiskEstimate:
    requested_start: datetime
    requested_end: datetime
    coverage_earliest: datetime | None
    coverage_latest: datetime | None
    coverage_basis: str
    coverage_probe_count: int
    coverage_empty_probe_count: int
    coverage_active_days: int
    calendar_days: float
    sample_rows: int
    sample_bytes: int
    sample_duration_seconds: float
    rows_per_active_hour: float
    rows_per_active_day: float
    rows_per_active_month: float
    compressed_bytes_per_row: float
    estimated_rows: int
    estimated_bytes: int
    estimated_bytes_low: int
    estimated_bytes_high: int
    sampling_throughput_rows_per_second: float
    export_throughput_bytes_per_second: float
    estimated_export_duration_seconds: float
    free_bytes: int
    budget_bytes: int
    existing_output_bytes: int
    required_safety_margin_bytes: int
    recommended_chunk: str
    uncertainty: str
    safe_to_continue: bool


@dataclass(frozen=True)
class CoverageReport:
    requested_start: datetime
    requested_end: datetime
    earliest_available: datetime | None
    latest_available: datetime | None
    active_days: int
    probe_count: int
    empty_probe_count: int
    maximum_probe_span_seconds: int
    basis: str = "BOUNDED_D1_OPEN_TIME_PROXY"


@dataclass(frozen=True)
class SampleManifest:
    schema_version: int
    exporter_version: str
    sample_id: str
    symbol: str
    requested_start: datetime
    requested_end: datetime
    returned_start: datetime
    returned_end: datetime
    row_count: int
    compressed_bytes: int
    sha256: str
    relative_path: str
    completion_marker: str
    duplicate_count: int
    crossed_quote_count: int
    zero_quote_count: int
    non_finite_quote_count: int
    gap_summary: Mapping[str, int]
    acquisition_elapsed_seconds: float
    write_elapsed_seconds: float
    completion_status: str

    def __post_init__(self) -> None:
        for name in ("requested_start", "requested_end", "returned_start", "returned_end"):
            utc_datetime(getattr(self, name), name)
        if not (self.requested_start <= self.returned_start <= self.returned_end < self.requested_end):
            raise AcquisitionError("sample timestamps violate the requested interval")
        if (self.requested_end - self.requested_start).total_seconds() > 3600:
            raise AcquisitionError("sample exceeds the one-hour bound")
        for name in ("row_count", "compressed_bytes", "acquisition_elapsed_seconds", "write_elapsed_seconds"):
            finite_positive(getattr(self, name), name)
        if self.symbol != EXECUTABLE_SYMBOL or self.completion_status != "COMPLETE":
            raise AcquisitionError("sample identity or completion is invalid")
        for name in ("duplicate_count", "crossed_quote_count", "zero_quote_count", "non_finite_quote_count"):
            finite_positive(getattr(self, name), name, allow_zero=True)
        if self.crossed_quote_count or self.zero_quote_count or self.non_finite_quote_count:
            raise AcquisitionError("sample quote integrity is unsafe")


@dataclass(frozen=True)
class ChunkSummary:
    chunk_id: str
    relative_path: str
    sha256: str
    record_count: int
    start: datetime
    end: datetime
    size_bytes: int
    duplicate_count: int
    crossed_quote_count: int
    zero_quote_count: int
    gap_count: int
    complete: bool
    canonical_content_sha256: str | None = None
    schema_version: str | None = None
    storage_format: str = "gzip-jsonl"
    compression: str = "gzip"
    requested_start: datetime | None = None
    requested_end: datetime | None = None


@dataclass(frozen=True)
class ExportInspection:
    status: ExportStatus
    mappings: Mapping[str, SymbolMapping]
    missing_symbols: tuple[str, ...]
    ambiguous_symbols: tuple[str, ...]
    tool_version: str = EXPORT_TOOL_VERSION
