from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterator, Mapping

from filelock import FileLock

from bot.validation.models import canonical_data

from .models import AcquisitionError, EXECUTABLE_SYMBOL
from .storage import atomic_json, file_sha256, output_size, validate_output_root


UTC = timezone.utc
ARCHIVE_SCHEMA_VERSION = "phase8b.exness-archive.v1"
PARQUET_SCHEMA_VERSION = "phase8b.exness-tick.v1"
EXPECTED_HEADER = ("Exness", "Symbol", "Timestamp", "Bid", "Ask")
EXPECTED_SOURCE = "Exness"
SOURCE_PAGE = "https://www.exness.com/tick-history/"
MAX_ARCHIVE_MEMBERS = 400
MAX_TOTAL_UNCOMPRESSED_BYTES = 10 * 1024**3
MAX_MEMBER_UNCOMPRESSED_BYTES = 5 * 1024**3
MAX_COMPRESSION_RATIO = 100.0
MAX_LINE_BYTES = 16 * 1024
MAX_SPREAD_VALUES = 100_000
PRICE_SCALE = 8
PRICE_QUANTUM = Decimal(1).scaleb(-PRICE_SCALE)
LONG_GAP_SECONDS = 60 * 60
MINIMUM_RESERVE_BYTES = 15 * 1024**3
_DRIVE_PATH = re.compile(r"^[A-Za-z]:")
_EXNESS_FILENAME = re.compile(
    r"^Exness_(?P<symbol>[A-Za-z0-9._-]+)_(?P<year>\d{4})"
    r"(?:_(?P<month>0[1-9]|1[0-2]))?$"
)
_EXECUTABLE_SUFFIXES = frozenset({
    ".bat", ".cmd", ".com", ".dll", ".exe", ".js", ".msi", ".ps1",
    ".py", ".scr", ".sh", ".vbs",
})


@dataclass(frozen=True)
class ArchiveMember:
    name: str
    compressed_bytes: int
    uncompressed_bytes: int
    compression_ratio: float
    crc32: str


@dataclass(frozen=True)
class ArchiveInspection:
    filename: str
    size_bytes: int
    sha256: str
    created_time_utc: datetime
    modified_time_utc: datetime
    archive_type: str
    members: tuple[ArchiveMember, ...]
    total_compressed_bytes: int
    total_uncompressed_bytes: int
    maximum_compression_ratio: float


@dataclass(frozen=True)
class ArchiveIdentity:
    symbol: str
    year: int
    month: int | None

    @property
    def period(self) -> str:
        return f"{self.year:04d}" if self.month is None else f"{self.year:04d}-{self.month:02d}"


def _arrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise AcquisitionError(
            "Parquet support requires the pinned requirements-data.txt environment"
        ) from exc
    return pa, pq


def exness_tick_schema():
    pa, _pq = _arrow()
    return pa.schema(
        [
            pa.field("source", pa.string(), nullable=False),
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("timestamp_raw", pa.string(), nullable=False),
            pa.field("timestamp", pa.timestamp("ms", tz="UTC"), nullable=False),
            pa.field("time_msc", pa.int64(), nullable=False),
            pa.field("bid_raw", pa.string(), nullable=False),
            pa.field("ask_raw", pa.string(), nullable=False),
            pa.field("bid", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("ask", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("sequence_id", pa.int64(), nullable=False),
            pa.field("row_identity", pa.string(), nullable=False),
            pa.field("source_member", pa.string(), nullable=False),
            pa.field("member_sha256", pa.string(), nullable=False),
            pa.field("archive_sha256", pa.string(), nullable=False),
            pa.field("provenance_id", pa.string(), nullable=False),
        ],
        metadata={b"schema_version": PARQUET_SCHEMA_VERSION.encode("ascii")},
    )


def _unsafe_member_reason(info: zipfile.ZipInfo) -> str | None:
    name = info.filename
    posix = PurePosixPath(name.replace("\\", "/"))
    windows = PureWindowsPath(name)
    if not name or name.startswith(("/", "\\")) or posix.is_absolute():
        return "ARCHIVE_ABSOLUTE_PATH"
    if _DRIVE_PATH.match(name) or windows.drive or name.startswith("\\\\"):
        return "ARCHIVE_WINDOWS_PATH"
    if ".." in posix.parts:
        return "ARCHIVE_PATH_TRAVERSAL"
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        return "ARCHIVE_LINK_ENTRY"
    if info.flag_bits & 0x1:
        return "ARCHIVE_ENCRYPTED_ENTRY"
    if Path(name).suffix.lower() in _EXECUTABLE_SUFFIXES:
        return "ARCHIVE_EXECUTABLE_ENTRY"
    return None


def inspect_exness_archive(
    archive_path: Path,
    *,
    maximum_members: int = MAX_ARCHIVE_MEMBERS,
    maximum_total_uncompressed_bytes: int = MAX_TOTAL_UNCOMPRESSED_BYTES,
    maximum_member_uncompressed_bytes: int = MAX_MEMBER_UNCOMPRESSED_BYTES,
    maximum_compression_ratio: float = MAX_COMPRESSION_RATIO,
) -> ArchiveInspection:
    path = Path(archive_path).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise AcquisitionError("Exness archive must be one existing ZIP file")
    archive_hash = file_sha256(path)
    try:
        with zipfile.ZipFile(path) as archive:
            infos = tuple(info for info in archive.infolist() if not info.is_dir())
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise AcquisitionError("ARCHIVE_CORRUPT_OR_UNREADABLE") from exc
    if not infos or len(infos) > maximum_members:
        raise AcquisitionError("ARCHIVE_MEMBER_COUNT_UNSAFE")
    names: set[str] = set()
    case_names: set[str] = set()
    members: list[ArchiveMember] = []
    for info in infos:
        reason = _unsafe_member_reason(info)
        if reason:
            raise AcquisitionError(reason)
        if info.filename in names:
            raise AcquisitionError("ARCHIVE_DUPLICATE_MEMBER")
        folded = info.filename.casefold()
        if folded in case_names:
            raise AcquisitionError("ARCHIVE_CASE_COLLISION")
        names.add(info.filename)
        case_names.add(folded)
        if Path(info.filename).suffix.lower() != ".csv":
            raise AcquisitionError("ARCHIVE_UNEXPECTED_MEMBER_TYPE")
        ratio = info.file_size / max(info.compress_size, 1)
        if info.file_size > maximum_member_uncompressed_bytes or ratio > maximum_compression_ratio:
            raise AcquisitionError("ARCHIVE_MEMBER_EXPANSION_UNSAFE")
        members.append(ArchiveMember(
            name=info.filename,
            compressed_bytes=info.compress_size,
            uncompressed_bytes=info.file_size,
            compression_ratio=ratio,
            crc32=f"{info.CRC:08x}",
        ))
    total_uncompressed = sum(item.uncompressed_bytes for item in members)
    if total_uncompressed > maximum_total_uncompressed_bytes:
        raise AcquisitionError("ARCHIVE_TOTAL_EXPANSION_UNSAFE")
    stat_result = path.stat()
    return ArchiveInspection(
        filename=path.name,
        size_bytes=stat_result.st_size,
        sha256=archive_hash,
        created_time_utc=datetime.fromtimestamp(stat_result.st_ctime, tz=UTC),
        modified_time_utc=datetime.fromtimestamp(stat_result.st_mtime, tz=UTC),
        archive_type="ZIP",
        members=tuple(members),
        total_compressed_bytes=sum(item.compressed_bytes for item in members),
        total_uncompressed_bytes=total_uncompressed,
        maximum_compression_ratio=max(item.compression_ratio for item in members),
    )


@dataclass(frozen=True)
class _QuoteRow:
    source: str
    symbol: str
    timestamp_raw: str
    timestamp: datetime
    time_msc: int
    bid_raw: str
    ask_raw: str
    bid: Decimal
    ask: Decimal
    sequence_id: int
    row_identity: str


def _bounded_example(examples: dict[str, list[dict[str, object]]], code: str, **detail: object) -> None:
    bucket = examples.setdefault(code, [])
    if len(bucket) < 3:
        bucket.append(canonical_data(detail))


def _decimal_price(raw: str, name: str) -> Decimal:
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise AcquisitionError(f"{name.upper()}_UNPARSABLE") from exc
    if not value.is_finite() or value <= 0:
        raise AcquisitionError(f"{name.upper()}_NON_POSITIVE_OR_NON_FINITE")
    quantized = value.quantize(PRICE_QUANTUM)
    if value != quantized:
        raise AcquisitionError(f"{name.upper()}_PRECISION_UNSUPPORTED")
    return quantized


def _parse_timestamp(raw: str) -> tuple[datetime, int]:
    if not raw.endswith("Z"):
        raise AcquisitionError("TIMESTAMP_TIMEZONE_UNPROVEN")
    try:
        value = datetime.fromisoformat(raw[:-1] + "+00:00")
    except ValueError as exc:
        raise AcquisitionError("TIMESTAMP_UNPARSABLE") from exc
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise AcquisitionError("TIMESTAMP_NOT_UTC")
    value = value.astimezone(UTC)
    if value.microsecond % 1000:
        raise AcquisitionError("TIMESTAMP_PRECISION_UNSUPPORTED")
    return value, int(value.timestamp() * 1000)


def _decimal_places(raw: str) -> int:
    value = raw.strip().lower()
    if "e" in value:
        return max(-Decimal(value).as_tuple().exponent, 0)
    return len(value.partition(".")[2])


def _canonical_row_payload(
    *, symbol: str, time_msc: int, bid: Decimal, ask: Decimal, sequence_id: int
) -> bytes:
    value = {
        "ask": format(ask, "f"),
        "bid": format(bid, "f"),
        "sequence_id": sequence_id,
        "symbol": symbol,
        "time_msc": time_msc,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _row_identity(
    archive_sha256: str, member_name: str, sequence_id: int, canonical_payload: bytes
) -> str:
    digest = hashlib.sha256()
    digest.update(archive_sha256.encode("ascii"))
    digest.update(b"\0")
    digest.update(member_name.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(sequence_id).encode("ascii"))
    digest.update(b"\0")
    digest.update(canonical_payload)
    return digest.hexdigest()


def _parse_row(
    fields: list[str], *, sequence_id: int, archive_sha256: str, member_name: str
) -> _QuoteRow:
    if len(fields) != len(EXPECTED_HEADER):
        raise AcquisitionError("ROW_FIELD_COUNT_INVALID")
    source, symbol, timestamp_raw, bid_raw, ask_raw = (item.strip() for item in fields)
    if source.casefold() != EXPECTED_SOURCE.casefold():
        raise AcquisitionError("SOURCE_VALUE_MISMATCH")
    if symbol != EXECUTABLE_SYMBOL:
        raise AcquisitionError("SYMBOL_MISMATCH")
    timestamp, time_msc = _parse_timestamp(timestamp_raw)
    bid = _decimal_price(bid_raw, "bid")
    ask = _decimal_price(ask_raw, "ask")
    if ask < bid:
        raise AcquisitionError("CROSSED_QUOTE")
    payload = _canonical_row_payload(
        symbol=symbol, time_msc=time_msc, bid=bid, ask=ask, sequence_id=sequence_id
    )
    return _QuoteRow(
        source=source,
        symbol=symbol,
        timestamp_raw=timestamp_raw,
        timestamp=timestamp,
        time_msc=time_msc,
        bid_raw=bid_raw,
        ask_raw=ask_raw,
        bid=bid,
        ask=ask,
        sequence_id=sequence_id,
        row_identity=_row_identity(archive_sha256, member_name, sequence_id, payload),
    )


def _iter_member_rows(
    archive_path: Path,
    inspection: ArchiveInspection,
    *,
    include_member_hash: bool = False,
) -> Iterator[tuple[_QuoteRow | None, str | None, int, str | None]]:
    member_name = inspection.members[0].name
    digest = hashlib.sha256()
    try:
        with zipfile.ZipFile(archive_path) as archive, archive.open(member_name, "r") as stream:
            header_seen = False
            sequence_id = 0
            last_had_newline = True
            for line_number, raw_line in enumerate(stream, start=1):
                digest.update(raw_line)
                last_had_newline = raw_line.endswith((b"\n", b"\r"))
                if len(raw_line) > MAX_LINE_BYTES:
                    yield None, "ROW_EXCEEDS_SIZE_LIMIT", line_number, None
                    continue
                try:
                    text = raw_line.decode("utf-8-sig" if line_number == 1 else "utf-8")
                    parsed = next(csv.reader([text], strict=True))
                except (UnicodeError, csv.Error, StopIteration):
                    yield None, "ROW_DECODING_OR_CSV_INVALID", line_number, None
                    continue
                if not header_seen:
                    header_seen = True
                    if tuple(item.strip() for item in parsed) != EXPECTED_HEADER:
                        yield None, "HEADER_MISMATCH", line_number, None
                    continue
                if not any(item.strip() for item in parsed):
                    yield None, "EMPTY_DATA_LINE", line_number, None
                    continue
                sequence_id += 1
                try:
                    row = _parse_row(
                        parsed,
                        sequence_id=sequence_id,
                        archive_sha256=inspection.sha256,
                        member_name=member_name,
                    )
                except AcquisitionError as exc:
                    yield None, str(exc), line_number, None
                    continue
                yield row, None, line_number, None
            if not header_seen:
                yield None, "EMPTY_MEMBER", 0, None
            if not last_had_newline:
                yield None, "TRUNCATION_INDICATOR_MISSING_FINAL_NEWLINE", line_number, None
    except (OSError, EOFError, RuntimeError, zipfile.BadZipFile) as exc:
        raise AcquisitionError("ARCHIVE_MEMBER_READ_OR_CRC_FAILED") from exc
    if include_member_hash:
        yield None, None, 0, digest.hexdigest()


def _has_weekend_between(previous: datetime, current: datetime) -> bool:
    value = previous.date()
    while value <= current.date():
        if value.weekday() >= 5:
            return True
        value += timedelta(days=1)
    return False


def _weighted_percentile(counts: Mapping[Decimal, int], quantile: float) -> Decimal:
    total = sum(counts.values())
    if total <= 0:
        raise AcquisitionError("SPREAD_DISTRIBUTION_EMPTY")
    target = int(math.ceil((total - 1) * quantile))
    cumulative = 0
    for value, count in sorted(counts.items()):
        cumulative += count
        if cumulative > target:
            return value
    raise AcquisitionError("SPREAD_PERCENTILE_FAILED")


def scan_exness_archive(archive_path: Path, inspection: ArchiveInspection) -> dict[str, object]:
    if len(inspection.members) != 1:
        raise AcquisitionError("ARCHIVE_MEMBER_LAYOUT_UNSUPPORTED")
    month_counts: Counter[str] = Counter()
    day_counts: Counter[str] = Counter()
    spread_counts: Counter[Decimal] = Counter()
    bid_precision: Counter[int] = Counter()
    ask_precision: Counter[int] = Counter()
    issue_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, object]]] = {}
    canonical_hash = hashlib.sha256()
    first: datetime | None = None
    last: datetime | None = None
    previous: datetime | None = None
    current_timestamp: datetime | None = None
    current_quotes: set[tuple[Decimal, Decimal]] = set()
    row_count = 0
    exact_duplicates = 0
    duplicate_timestamps_different_prices = 0
    locked_quotes = 0
    long_gap_count = 0
    weekend_gap_count = 0
    unexplained_gap_count = 0
    maximum_gap_seconds = 0.0
    member_sha256 = ""

    for row, reason, line_number, member_hash in _iter_member_rows(
        Path(archive_path), inspection, include_member_hash=True
    ):
        if member_hash:
            member_sha256 = member_hash
            continue
        if reason:
            issue_counts[reason] += 1
            _bounded_example(examples, reason, line_number=line_number)
            continue
        assert row is not None
        row_count += 1
        if first is None or row.timestamp < first:
            first = row.timestamp
        if previous is not None:
            if row.timestamp < previous:
                issue_counts["NON_MONOTONIC_TIMESTAMP"] += 1
                _bounded_example(
                    examples,
                    "NON_MONOTONIC_TIMESTAMP",
                    line_number=line_number,
                    timestamp=row.timestamp,
                    previous_timestamp=previous,
                )
            gap_seconds = (row.timestamp - previous).total_seconds()
            if gap_seconds > LONG_GAP_SECONDS:
                long_gap_count += 1
                maximum_gap_seconds = max(maximum_gap_seconds, gap_seconds)
                classification = (
                    "WEEKEND_ASSOCIATED" if _has_weekend_between(previous, row.timestamp)
                    else "WEEKDAY_OR_HOLIDAY_UNVERIFIED"
                )
                weekend_gap_count += int(classification == "WEEKEND_ASSOCIATED")
                unexplained_gap_count += int(classification != "WEEKEND_ASSOCIATED")
                _bounded_example(
                    examples,
                    "LONG_GAP",
                    previous_timestamp=previous,
                    timestamp=row.timestamp,
                    seconds=gap_seconds,
                    classification=classification,
                )
        previous = row.timestamp
        if last is None or row.timestamp > last:
            last = row.timestamp
        if row.timestamp != current_timestamp:
            current_timestamp = row.timestamp
            current_quotes.clear()
        quote = (row.bid, row.ask)
        if quote in current_quotes:
            exact_duplicates += 1
        elif current_quotes:
            duplicate_timestamps_different_prices += 1
        current_quotes.add(quote)
        locked_quotes += int(row.ask == row.bid)
        month_counts[row.timestamp.strftime("%Y-%m")] += 1
        day_counts[row.timestamp.date().isoformat()] += 1
        bid_precision[_decimal_places(row.bid_raw)] += 1
        ask_precision[_decimal_places(row.ask_raw)] += 1
        spread_counts[row.ask - row.bid] += 1
        if len(spread_counts) > MAX_SPREAD_VALUES:
            raise AcquisitionError("SPREAD_CARDINALITY_UNSAFE")
        payload = _canonical_row_payload(
            symbol=row.symbol,
            time_msc=row.time_msc,
            bid=row.bid,
            ask=row.ask,
            sequence_id=row.sequence_id,
        )
        canonical_hash.update(payload)
        canonical_hash.update(b"\n")

    fatal_codes = tuple(sorted(
        code for code in issue_counts
        if code not in {
            "NON_MONOTONIC_TIMESTAMP",
            "TRUNCATION_INDICATOR_MISSING_FINAL_NEWLINE",
        }
    ))
    if row_count == 0 or first is None or last is None:
        fatal_codes = tuple(sorted(set(fatal_codes) | {"NO_VALID_ROWS"}))
    if not member_sha256:
        fatal_codes = tuple(sorted(set(fatal_codes) | {"MEMBER_HASH_MISSING"}))
    if fatal_codes:
        raise AcquisitionError("ARCHIVE_CONTENT_REJECTED:" + ",".join(fatal_codes))

    median_spread = _weighted_percentile(spread_counts, 0.50)
    p95_spread = _weighted_percentile(spread_counts, 0.95)
    p99_spread = _weighted_percentile(spread_counts, 0.99)
    outlier_threshold = p99_spread * Decimal(5)
    suspicious_outliers = sum(count for spread, count in spread_counts.items() if spread > outlier_threshold)
    present_dates = {date.fromisoformat(value) for value in day_counts}
    missing_weekdays: list[str] = []
    day = first.date()
    while day <= last.date():
        if day.weekday() < 5 and day not in present_dates:
            missing_weekdays.append(day.isoformat())
        day += timedelta(days=1)

    return canonical_data({
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "header": EXPECTED_HEADER,
        "delimiter": ",",
        "encoding": "UTF-8",
        "timestamp_timezone": "UTC_EXPLICIT_Z",
        "timestamp_precision": "MILLISECONDS",
        "symbol": EXECUTABLE_SYMBOL,
        "row_count": row_count,
        "first_timestamp": first,
        "last_timestamp": last,
        "utc_date_count": len(day_counts),
        "month_counts": dict(sorted(month_counts.items())),
        "trading_day_counts": dict(sorted(day_counts.items())),
        "completely_missing_weekdays": missing_weekdays,
        "non_monotonic_rows": issue_counts["NON_MONOTONIC_TIMESTAMP"],
        "exact_duplicate_rows": exact_duplicates,
        "duplicate_timestamps_different_prices": duplicate_timestamps_different_prices,
        "invalid_timestamp_rows": sum(
            issue_counts[code] for code in issue_counts if code.startswith("TIMESTAMP_")
        ),
        "non_finite_or_non_positive_price_rows": sum(
            issue_counts[code] for code in issue_counts
            if "NON_POSITIVE_OR_NON_FINITE" in code
        ),
        "crossed_quote_rows": issue_counts["CROSSED_QUOTE"],
        "locked_quote_rows": locked_quotes,
        "symbol_mismatch_rows": issue_counts["SYMBOL_MISMATCH"],
        "malformed_line_rows": sum(
            issue_counts[code] for code in issue_counts
            if code in {"ROW_FIELD_COUNT_INVALID", "ROW_DECODING_OR_CSV_INVALID", "ROW_EXCEEDS_SIZE_LIMIT"}
        ),
        "empty_line_rows": issue_counts["EMPTY_DATA_LINE"],
        "truncation_indicators": issue_counts["TRUNCATION_INDICATOR_MISSING_FINAL_NEWLINE"],
        "price_precision": {
            "bid_decimal_places": {str(key): value for key, value in sorted(bid_precision.items())},
            "ask_decimal_places": {str(key): value for key, value in sorted(ask_precision.items())},
        },
        "spread_price": {
            "minimum": format(min(spread_counts), "f"),
            "median": format(median_spread, "f"),
            "p95": format(p95_spread, "f"),
            "p99": format(p99_spread, "f"),
            "maximum": format(max(spread_counts), "f"),
            "suspicious_outlier_threshold": format(outlier_threshold, "f"),
            "suspicious_outlier_count": suspicious_outliers,
            "distinct_values": len(spread_counts),
        },
        "gaps": {
            "long_gap_threshold_seconds": LONG_GAP_SECONDS,
            "long_gap_count": long_gap_count,
            "weekend_associated_count": weekend_gap_count,
            "weekday_or_holiday_unverified_count": unexplained_gap_count,
            "maximum_gap_seconds": maximum_gap_seconds,
        },
        "issue_counts": dict(sorted(issue_counts.items())),
        "bounded_examples": examples,
        "member_sha256": member_sha256,
        "canonical_normalized_sha256": canonical_hash.hexdigest(),
    })


def _record_mapping(
    row: _QuoteRow,
    *,
    inspection: ArchiveInspection,
    member_sha256: str,
    provenance_id: str,
) -> dict[str, object]:
    return {
        "source": row.source,
        "symbol": row.symbol,
        "timestamp_raw": row.timestamp_raw,
        "timestamp": row.timestamp,
        "time_msc": row.time_msc,
        "bid_raw": row.bid_raw,
        "ask_raw": row.ask_raw,
        "bid": row.bid,
        "ask": row.ask,
        "sequence_id": row.sequence_id,
        "row_identity": row.row_identity,
        "source_member": inspection.members[0].name,
        "member_sha256": member_sha256,
        "archive_sha256": inspection.sha256,
        "provenance_id": provenance_id,
    }


def _table(records: list[dict[str, object]]):
    pa, _pq = _arrow()
    return pa.Table.from_pydict(
        {name: [record[name] for record in records] for name in exness_tick_schema().names},
        schema=exness_tick_schema(),
    )


def _fsync_file(path: Path) -> None:
    with Path(path).open("r+b") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _write_partitions(
    archive_path: Path,
    package_root: Path,
    inspection: ArchiveInspection,
    scan: Mapping[str, object],
    *,
    minimum_free_bytes: int,
    maximum_output_bytes: int,
    batch_size: int,
) -> list[dict[str, object]]:
    _pa, pq = _arrow()
    member_sha256 = str(scan["member_sha256"])
    provenance_id = f"exness-owner-download-2024-{inspection.sha256[:16]}"
    records: list[dict[str, object]] = []
    current_month: str | None = None
    writer = None
    partial_path: Path | None = None
    unsorted_path: Path | None = None
    final_path: Path | None = None
    partitions: list[dict[str, object]] = []
    partition_count = 0
    partition_first: datetime | None = None
    partition_last: datetime | None = None

    def close_partition() -> None:
        nonlocal writer, partial_path, unsorted_path, final_path
        nonlocal partition_count, partition_first, partition_last
        if (
            writer is None
            or partial_path is None
            or unsorted_path is None
            or final_path is None
            or current_month is None
        ):
            return
        if records:
            writer.write_table(_table(records), row_group_size=batch_size)
            records.clear()
        writer.close()
        writer = None
        _fsync_file(unsorted_path)
        if output_size(package_root) > maximum_output_bytes:
            raise AcquisitionError("ARCHIVE_OUTPUT_BUDGET_EXCEEDED")
        if shutil.disk_usage(package_root).free <= minimum_free_bytes:
            raise AcquisitionError("ARCHIVE_DISK_RESERVE_BREACHED")
        table = pq.read_table(unsorted_path, schema=exness_tick_schema())
        table = table.sort_by([("timestamp", "ascending"), ("sequence_id", "ascending")])
        pq.write_table(
            table,
            partial_path,
            compression="zstd",
            compression_level=9,
            use_dictionary=(
                "source", "symbol", "source_member", "member_sha256",
                "archive_sha256", "provenance_id",
            ),
            write_statistics=True,
            row_group_size=batch_size,
        )
        del table
        _fsync_file(partial_path)
        unsorted_path.unlink()
        if output_size(package_root) > maximum_output_bytes:
            raise AcquisitionError("ARCHIVE_OUTPUT_BUDGET_EXCEEDED")
        if shutil.disk_usage(package_root).free <= minimum_free_bytes:
            raise AcquisitionError("ARCHIVE_DISK_RESERVE_BREACHED")
        os.replace(partial_path, final_path)
        partitions.append({
            "month": current_month,
            "relative_path": final_path.relative_to(package_root).as_posix(),
            "record_count": partition_count,
            "first_timestamp": partition_first,
            "last_timestamp": partition_last,
            "size_bytes": final_path.stat().st_size,
            "sha256": file_sha256(final_path),
            "ordering": "TIMESTAMP_ASC_THEN_SOURCE_SEQUENCE_ASC",
        })
        partial_path = None
        unsorted_path = None
        final_path = None
        partition_count = 0
        partition_first = None
        partition_last = None

    try:
        for row, reason, _line_number, _member_hash in _iter_member_rows(Path(archive_path), inspection):
            if reason:
                if reason == "TRUNCATION_INDICATOR_MISSING_FINAL_NEWLINE":
                    continue
                raise AcquisitionError("ARCHIVE_CHANGED_BETWEEN_SCAN_AND_CONVERSION")
            if row is None:
                continue
            month = row.timestamp.strftime("%Y-%m")
            if current_month != month:
                close_partition()
                if current_month is not None and month <= current_month:
                    raise AcquisitionError("ARCHIVE_PARTITION_ORDER_INVALID")
                current_month = month
                directory = package_root / "ticks" / f"year={row.timestamp:%Y}" / f"month={row.timestamp:%m}"
                directory.mkdir(parents=True, exist_ok=True)
                final_path = directory / "part-00000.parquet"
                partial_path = directory / "part-00000.parquet.partial"
                unsorted_path = directory / "part-00000.unsorted.parquet.partial"
                if final_path.exists() or partial_path.exists() or unsorted_path.exists():
                    raise AcquisitionError("ARCHIVE_PARTITION_ALREADY_EXISTS")
                writer = pq.ParquetWriter(
                    unsorted_path,
                    exness_tick_schema(),
                    compression="zstd",
                    compression_level=9,
                    use_dictionary=(
                        "source", "symbol", "source_member", "member_sha256",
                        "archive_sha256", "provenance_id",
                    ),
                    write_statistics=True,
                )
            records.append(_record_mapping(
                row,
                inspection=inspection,
                member_sha256=member_sha256,
                provenance_id=provenance_id,
            ))
            partition_count += 1
            if partition_first is None or row.timestamp < partition_first:
                partition_first = row.timestamp
            if partition_last is None or row.timestamp > partition_last:
                partition_last = row.timestamp
            if len(records) >= batch_size:
                assert writer is not None
                writer.write_table(_table(records), row_group_size=batch_size)
                records.clear()
                if output_size(package_root) > maximum_output_bytes:
                    raise AcquisitionError("ARCHIVE_OUTPUT_BUDGET_EXCEEDED")
                if shutil.disk_usage(package_root).free <= minimum_free_bytes:
                    raise AcquisitionError("ARCHIVE_DISK_RESERVE_BREACHED")
        close_partition()
    finally:
        if writer is not None:
            writer.close()
    return partitions


def _canonical_from_parquet_values(
    *, symbol: str, time_msc: int, bid: Decimal, ask: Decimal, sequence_id: int
) -> bytes:
    return _canonical_row_payload(
        symbol=symbol,
        time_msc=time_msc,
        bid=bid.quantize(PRICE_QUANTUM),
        ask=ask.quantize(PRICE_QUANTUM),
        sequence_id=sequence_id,
    )


def _readback_partitions(
    package_root: Path, partitions: list[dict[str, object]], inspection: ArchiveInspection
) -> dict[str, object]:
    _pa, pq = _arrow()
    digest = hashlib.sha256()
    count = 0
    first: datetime | None = None
    last: datetime | None = None
    previous: datetime | None = None
    current_timestamp: datetime | None = None
    current_quotes: set[tuple[Decimal, Decimal]] = set()
    exact_duplicates = 0
    duplicate_timestamps_different_prices = 0
    long_gap_count = 0
    weekend_gap_count = 0
    unexplained_gap_count = 0
    maximum_gap_seconds = 0.0
    for partition in partitions:
        path = package_root / str(partition["relative_path"])
        parquet = pq.ParquetFile(path)
        if parquet.schema_arrow != exness_tick_schema():
            raise AcquisitionError("PARQUET_SCHEMA_MISMATCH")
        partition_count = 0
        for batch in parquet.iter_batches(batch_size=100_000):
            columns = batch.to_pydict()
            for index in range(batch.num_rows):
                symbol = columns["symbol"][index]
                archive_sha256 = columns["archive_sha256"][index]
                if symbol != EXECUTABLE_SYMBOL or archive_sha256 != inspection.sha256:
                    raise AcquisitionError("PARQUET_IDENTITY_MISMATCH")
                timestamp = columns["timestamp"][index].astimezone(UTC)
                time_msc = int(columns["time_msc"][index])
                if int(timestamp.timestamp() * 1000) != time_msc:
                    raise AcquisitionError("PARQUET_TIMESTAMP_MISMATCH")
                if previous is not None and timestamp < previous:
                    raise AcquisitionError("PARQUET_ORDERING_MISMATCH")
                if previous is not None:
                    gap_seconds = (timestamp - previous).total_seconds()
                    if gap_seconds > LONG_GAP_SECONDS:
                        long_gap_count += 1
                        maximum_gap_seconds = max(maximum_gap_seconds, gap_seconds)
                        if _has_weekend_between(previous, timestamp):
                            weekend_gap_count += 1
                        else:
                            unexplained_gap_count += 1
                if timestamp != current_timestamp:
                    current_timestamp = timestamp
                    current_quotes.clear()
                quote = (
                    columns["bid"][index].quantize(PRICE_QUANTUM),
                    columns["ask"][index].quantize(PRICE_QUANTUM),
                )
                if quote in current_quotes:
                    exact_duplicates += 1
                elif current_quotes:
                    duplicate_timestamps_different_prices += 1
                current_quotes.add(quote)
                previous = timestamp
                first = first or timestamp
                last = timestamp
                sequence_id = int(columns["sequence_id"][index])
                payload = _canonical_from_parquet_values(
                    symbol=symbol,
                    time_msc=time_msc,
                    bid=quote[0],
                    ask=quote[1],
                    sequence_id=sequence_id,
                )
                expected_identity = _row_identity(
                    inspection.sha256,
                    str(columns["source_member"][index]),
                    sequence_id,
                    payload,
                )
                if columns["row_identity"][index] != expected_identity:
                    raise AcquisitionError("PARQUET_ROW_IDENTITY_MISMATCH")
                digest.update(payload)
                digest.update(b"\n")
                count += 1
                partition_count += 1
        if partition_count != int(partition["record_count"]):
            raise AcquisitionError("PARQUET_PARTITION_COUNT_MISMATCH")
    return canonical_data({
        "record_count": count,
        "first_timestamp": first,
        "last_timestamp": last,
        "canonical_normalized_sha256": digest.hexdigest(),
        "exact_duplicate_rows": exact_duplicates,
        "duplicate_timestamps_different_prices": duplicate_timestamps_different_prices,
        "gaps": {
            "long_gap_threshold_seconds": LONG_GAP_SECONDS,
            "long_gap_count": long_gap_count,
            "weekend_associated_count": weekend_gap_count,
            "weekday_or_holiday_unverified_count": unexplained_gap_count,
            "maximum_gap_seconds": maximum_gap_seconds,
        },
        "reconciled": True,
    })


def _manifest_hash(path: Path) -> str:
    return file_sha256(path)


def verify_exness_package(package_root: Path, *, deep: bool = False) -> dict[str, object]:
    root = Path(package_root)
    try:
        completion = json.loads((root / "package.complete.json").read_text(encoding="utf-8"))
        manifest_path = root / str(completion["manifest_relative_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AcquisitionError("EXNESS_PACKAGE_COMPLETION_INVALID") from exc
    if (
        completion.get("schema_version") != ARCHIVE_SCHEMA_VERSION
        or completion.get("status") != "COMPLETE"
        or completion.get("package_id") != root.name
        or completion.get("manifest_sha256") != _manifest_hash(manifest_path)
        or manifest.get("package_id") != root.name
    ):
        raise AcquisitionError("EXNESS_PACKAGE_IDENTITY_MISMATCH")
    for partition in manifest.get("partitions", []):
        path = root / str(partition["relative_path"])
        if (
            not path.is_file()
            or path.stat().st_size != int(partition["size_bytes"])
            or file_sha256(path) != partition["sha256"]
        ):
            raise AcquisitionError("EXNESS_PACKAGE_PARTITION_HASH_MISMATCH")
    if deep:
        inspection_raw = manifest["archive"]
        inspection = ArchiveInspection(
            filename=str(inspection_raw["filename"]),
            size_bytes=int(inspection_raw["size_bytes"]),
            sha256=str(inspection_raw["sha256"]),
            created_time_utc=datetime.fromtimestamp(0, tz=UTC),
            modified_time_utc=datetime.fromtimestamp(0, tz=UTC),
            archive_type="ZIP",
            members=tuple(),
            total_compressed_bytes=0,
            total_uncompressed_bytes=0,
            maximum_compression_ratio=0,
        )
        readback = _readback_partitions(root, list(manifest["partitions"]), inspection)
        if (
            readback["record_count"] != manifest["statistics"]["row_count"]
            or readback["first_timestamp"] != manifest["statistics"]["first_timestamp"]
            or readback["last_timestamp"] != manifest["statistics"]["last_timestamp"]
            or readback["canonical_normalized_sha256"] != manifest["canonical_normalized_sha256"]
        ):
            raise AcquisitionError("EXNESS_PACKAGE_DEEP_RECONCILIATION_FAILED")
    return manifest


def _storage_projection(
    *,
    archive_bytes: int,
    parquet_bytes: int,
    current_free_bytes: int,
    observed_period_months: int = 12,
) -> dict[str, object]:
    if observed_period_months not in {1, 12}:
        raise AcquisitionError("ARCHIVE_STORAGE_PERIOD_UNSUPPORTED")
    observed_period_bytes = archive_bytes + parquet_bytes
    remaining_years = 5
    annual_multiplier = 1 if observed_period_months == 12 else 12
    annual_lower = int(observed_period_bytes * annual_multiplier * 0.75)
    annual_baseline = observed_period_bytes * annual_multiplier
    annual_upper = int(observed_period_bytes * annual_multiplier * 1.5)
    lower = annual_lower * remaining_years
    baseline = annual_baseline * remaining_years
    upper = annual_upper * remaining_years
    temporary = int(max(archive_bytes, parquet_bytes) * 1.5)
    return {
        "basis": (
            "2024_OBSERVED_SIZE_SCENARIO_NOT_A_FORECAST"
            if observed_period_months == 12
            else "DECEMBER_2024_MONTHLY_SIZE_SCENARIO_WITH_SEASONALITY_UNCERTAINTY"
        ),
        "observed_period_months": observed_period_months,
        "observed_period_bytes": observed_period_bytes,
        "estimated_twelve_month_archive_and_parquet_bytes": {
            "lower": annual_lower,
            "baseline": annual_baseline,
            "upper": annual_upper,
        },
        "remaining_preregistered_development_years": [2019, 2020, 2021, 2022, 2023],
        "lower_bytes": lower,
        "baseline_bytes": baseline,
        "upper_bytes": upper,
        "temporary_working_bytes": temporary,
        "required_reserve_bytes": MINIMUM_RESERVE_BYTES,
        "required_free_for_upper_bytes": upper + MINIMUM_RESERVE_BYTES,
        "current_free_bytes": current_free_bytes,
        "upper_scenario_fits_current_disk": current_free_bytes > upper + MINIMUM_RESERVE_BYTES,
        "recommended_sequence": [2023, 2022, 2021, 2020, 2019],
        "one_archive_at_a_time": True,
    }


def parse_archive_identity(filename: str) -> ArchiveIdentity:
    match = _EXNESS_FILENAME.fullmatch(Path(filename).stem)
    if match is None:
        raise AcquisitionError("ARCHIVE_FILENAME_IDENTITY_UNPROVEN")
    month = match.group("month")
    return ArchiveIdentity(
        symbol=match.group("symbol"),
        year=int(match.group("year")),
        month=int(month) if month is not None else None,
    )


def _parse_manifest_timestamp(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise AcquisitionError("ARCHIVE_MANIFEST_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        raise AcquisitionError("ARCHIVE_MANIFEST_TIMESTAMP_NAIVE")
    return parsed.astimezone(UTC)


def ingest_exness_archive(
    archive_path: Path,
    output_root: Path,
    *,
    claimed_year: int = 2024,
    claimed_month: int | None = None,
    minimum_free_bytes: int = MINIMUM_RESERVE_BYTES,
    maximum_output_bytes: int = 5 * 1024**3,
    batch_size: int = 100_000,
    forbidden_roots: tuple[Path, ...] = (),
    package_id_override: str | None = None,
) -> dict[str, object]:
    if claimed_year != 2024 or (claimed_month is not None and claimed_month not in range(1, 13)):
        raise AcquisitionError("ONLY_OWNER_SUPPLIED_2024_ARCHIVE_IS_AUTHORIZED")
    if minimum_free_bytes < MINIMUM_RESERVE_BYTES:
        raise AcquisitionError("ARCHIVE_MINIMUM_RESERVE_CANNOT_BE_WEAKENED")
    if maximum_output_bytes <= 0 or batch_size < 1 or batch_size > 500_000:
        raise AcquisitionError("ARCHIVE_INGEST_LIMITS_INVALID")
    archive = Path(archive_path).resolve(strict=True)
    root = validate_output_root(Path(output_root), forbidden_roots=forbidden_roots)
    raw_root = archive.parent.resolve()
    if root == raw_root or raw_root in root.parents or root in raw_root.parents:
        raise AcquisitionError("ARCHIVE_OUTPUT_MUST_BE_SEPARATE_FROM_RAW")
    inspection = inspect_exness_archive(archive)
    archive_identity = parse_archive_identity(inspection.filename)
    member_identity = parse_archive_identity(inspection.members[0].name)
    if (
        archive_identity.symbol != EXECUTABLE_SYMBOL
        or member_identity.symbol != EXECUTABLE_SYMBOL
        or archive_identity != member_identity
        or archive_identity.year != claimed_year
        or archive_identity.month != claimed_month
    ):
        raise AcquisitionError("ARCHIVE_FILENAME_SYMBOL_OR_YEAR_MISMATCH")
    period_slug = f"{claimed_year:04d}" if claimed_month is None else f"{claimed_year:04d}-{claimed_month:02d}"
    default_package_id = f"exness-xauusdm-{period_slug}-{inspection.sha256[:16]}"
    if package_id_override is None:
        package_id = default_package_id
    else:
        package_id = str(package_id_override)
        if not re.fullmatch(rf"{re.escape(default_package_id)}-recovery-\d{{4}}", package_id):
            raise AcquisitionError("ARCHIVE_RECOVERY_PACKAGE_ID_INVALID")
    packages_root = root / "packages"
    final_root = packages_root / package_id
    if final_root.exists():
        manifest = verify_exness_package(final_root)
        if manifest.get("archive", {}).get("sha256") != inspection.sha256:
            raise AcquisitionError("EXISTING_PACKAGE_ARCHIVE_MISMATCH")
        result = dict(manifest)
        result["idempotent_existing_package"] = True
        return canonical_data(result)

    free_before = shutil.disk_usage(root.parent if not root.exists() else root).free
    projected_temporary = min(inspection.total_uncompressed_bytes, maximum_output_bytes)
    if free_before - projected_temporary <= minimum_free_bytes:
        raise AcquisitionError("ARCHIVE_DISK_RESERVE_WOULD_BE_BREACHED")

    statistics = scan_exness_archive(archive, inspection)
    first = _parse_manifest_timestamp(statistics["first_timestamp"])
    last = _parse_manifest_timestamp(statistics["last_timestamp"])
    if first.year != claimed_year or last.year != claimed_year or any(
        not str(month).startswith(f"{claimed_year}-") for month in statistics["month_counts"]
    ):
        raise AcquisitionError("ARCHIVE_CLAIMED_YEAR_MISMATCH")
    if claimed_month is not None:
        claimed_period = f"{claimed_year:04d}-{claimed_month:02d}"
        if set(statistics["month_counts"]) != {claimed_period}:
            raise AcquisitionError("ARCHIVE_CLAIMED_MONTH_MISMATCH")

    packages_root.mkdir(parents=True, exist_ok=True)
    partial_root = packages_root / f".{package_id}.partial"
    with FileLock(str(packages_root / ".exness-ingest.lock"), timeout=30):
        if final_root.exists():
            return verify_exness_package(final_root)
        if partial_root.exists():
            raise AcquisitionError("ARCHIVE_PARTIAL_PACKAGE_REQUIRES_REVIEW")
        partial_root.mkdir()
        try:
            partitions = _write_partitions(
                archive,
                partial_root,
                inspection,
                statistics,
                minimum_free_bytes=minimum_free_bytes,
                maximum_output_bytes=maximum_output_bytes,
                batch_size=batch_size,
            )
            if file_sha256(archive) != inspection.sha256:
                raise AcquisitionError("RAW_ARCHIVE_CHANGED_DURING_INGEST")
            readback = _readback_partitions(partial_root, partitions, inspection)
            if (
                readback["record_count"] != statistics["row_count"]
                or readback["first_timestamp"] != statistics["first_timestamp"]
                or readback["last_timestamp"] != statistics["last_timestamp"]
            ):
                raise AcquisitionError("ARCHIVE_PARQUET_RECONCILIATION_FAILED")
            statistics = dict(statistics)
            statistics["source_order_canonical_sha256"] = statistics.pop(
                "canonical_normalized_sha256"
            )
            statistics["canonical_normalized_sha256"] = readback[
                "canonical_normalized_sha256"
            ]
            statistics["exact_duplicate_rows"] = readback["exact_duplicate_rows"]
            statistics["duplicate_timestamps_different_prices"] = readback[
                "duplicate_timestamps_different_prices"
            ]
            statistics["gaps"] = readback["gaps"]
            parquet_bytes = sum(int(item["size_bytes"]) for item in partitions)
            free_after_conversion = shutil.disk_usage(partial_root).free
            projection = _storage_projection(
                archive_bytes=inspection.size_bytes,
                parquet_bytes=parquet_bytes,
                current_free_bytes=free_after_conversion,
                observed_period_months=1 if claimed_month is not None else 12,
            )
            archive_manifest = {
                "filename": inspection.filename,
                "size_bytes": inspection.size_bytes,
                "sha256": inspection.sha256,
                "archive_type": inspection.archive_type,
                "member_count": len(inspection.members),
                "total_compressed_bytes": inspection.total_compressed_bytes,
                "total_uncompressed_bytes": inspection.total_uncompressed_bytes,
                "maximum_compression_ratio": inspection.maximum_compression_ratio,
                "members": [
                    {
                        **asdict(member),
                        "sha256": statistics["member_sha256"],
                    }
                    for member in inspection.members
                ],
            }
            manifest = canonical_data({
                "schema_version": ARCHIVE_SCHEMA_VERSION,
                "package_id": package_id,
                "classification": "DEVELOPMENT_ONLY",
                "classification_reason_codes": [
                    "PREREGISTERED_DEVELOPMENT_YEAR",
                    "INDICATIVE_SOURCE_ONLY",
                    "TRADING_SERVER_IDENTITY_UNRESOLVED",
                    "REDISTRIBUTION_RIGHTS_UNPROVEN",
                    "HISTORICAL_COST_AND_METADATA_INPUTS_INCOMPLETE",
                ],
                "phase7_fidelity": "TICK_BID_ASK",
                "source": "Exness Tick History",
                "source_page": SOURCE_PAGE,
                "acquisition_method": "OWNER_MANUAL_PERSONAL_AREA_DOWNLOAD",
                "owner_supplied": True,
                "account_type_evidence": "NOT_PRESENT_IN_ARCHIVE",
                "specific_trading_server_evidence": "NOT_PRESENT_IN_ARCHIVE",
                "source_warning": "EXNESS_DESCRIBES_TICK_HISTORY_AS_INDICATIVE",
                "licensing": {
                    "redistribution_rights_proven": False,
                    "research_use_rights_proven": False,
                    "restriction_status": "OWNER_REVIEW_REQUIRED",
                },
                "claimed_year": claimed_year,
                "claimed_month": claimed_month,
                "claimed_period": archive_identity.period,
                "archive": archive_manifest,
                "observed_schema": {
                    "header": list(EXPECTED_HEADER),
                    "delimiter": ",",
                    "encoding": "UTF-8",
                    "partitioning": (
                        "SINGLE_YEARLY_CSV_MEMBER_TO_MONTHLY_PARQUET"
                        if claimed_month is None
                        else "SINGLE_MONTHLY_CSV_MEMBER_TO_MONTHLY_PARQUET"
                    ),
                    "ordering_normalization": "TIMESTAMP_ASC_THEN_SOURCE_SEQUENCE_ASC",
                    "source_order_defects_preserved_in_statistics": True,
                },
                "timestamp_contract": {
                    "raw_timezone_evidence": "EXPLICIT_Z_SUFFIX_PER_ROW",
                    "canonical_timezone": "UTC",
                    "precision": "MILLISECONDS",
                    "dst_or_server_time_ambiguity": False,
                },
                "symbol_contract": {
                    "archive_filename_symbol": archive_identity.symbol,
                    "member_filename_symbol": member_identity.symbol,
                    "row_symbol": EXECUTABLE_SYMBOL,
                    "suffix_translation_applied": False,
                },
                "statistics": statistics,
                "canonical_normalized_sha256": statistics["canonical_normalized_sha256"],
                "partitions": partitions,
                "parquet_total_bytes": parquet_bytes,
                "readback": readback,
                "provenance_limitations": [
                    "EXNESS_ARCHIVE_IS_DESCRIBED_AS_INDICATIVE",
                    "SPECIFIC_TRADING_SERVER_CANNOT_BE_PROVEN_FROM_ARCHIVE",
                    "REDISTRIBUTION_AND_RESEARCH_USE_RIGHTS_NOT_PROVEN",
                    "BID_ASK_DO_NOT_PROVE_SLIPPAGE_COMMISSION_SWAP_OR_ACTUAL_FILL",
                ],
                "storage_projection": projection,
                "raw_data_outside_git": True,
                "raw_archive_modified": False,
                "raw_rows_committed": False,
                "holdout_accessed": False,
                "strategy_evaluated": False,
                "profitability_evaluated": False,
                "mt5_accessed": False,
                "network_accessed": False,
                "phase9_authorized": False,
            })
            inspection_record = canonical_data({
                "schema_version": ARCHIVE_SCHEMA_VERSION,
                "notice": "FILESYSTEM_TIMESTAMPS_ARE_OBSERVATIONS_NOT_DOWNLOAD_PROVENANCE",
                "filename": inspection.filename,
                "created_time_utc": inspection.created_time_utc,
                "modified_time_utc": inspection.modified_time_utc,
                "size_bytes": inspection.size_bytes,
                "sha256": inspection.sha256,
            })
            atomic_json(partial_root / "archive.inspection.json", inspection_record)
            manifest_path = partial_root / "manifest.json"
            atomic_json(manifest_path, manifest)
            completion = {
                "schema_version": ARCHIVE_SCHEMA_VERSION,
                "status": "COMPLETE",
                "package_id": package_id,
                "manifest_relative_path": "manifest.json",
                "manifest_sha256": _manifest_hash(manifest_path),
                "canonical_normalized_sha256": statistics["canonical_normalized_sha256"],
                "record_count": statistics["row_count"],
            }
            atomic_json(partial_root / "package.complete.json", completion)
            if output_size(partial_root) > maximum_output_bytes:
                raise AcquisitionError("ARCHIVE_OUTPUT_BUDGET_EXCEEDED")
            if shutil.disk_usage(partial_root).free <= minimum_free_bytes:
                raise AcquisitionError("ARCHIVE_DISK_RESERVE_BREACHED")
            os.replace(partial_root, final_root)
        except Exception:
            shutil.rmtree(partial_root, ignore_errors=True)
            raise
    verified = verify_exness_package(final_root, deep=True)
    result = dict(verified)
    result["idempotent_existing_package"] = False
    return canonical_data(result)
