from __future__ import annotations

import hashlib
import gzip
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from bot.backtesting.models import FidelityClass
from bot.acquisition.models import AcquisitionError

from .models import (
    AcceptanceIssue,
    AcceptanceOutcome,
    AcceptanceReport,
    DataStreamKind,
    DataStreamManifest,
    EmpiricalPackageManifest,
    SYNTHETIC_LABEL,
    ValidationError,
    parse_utc,
    StudyPeriod,
    canonical_data,
)


UTC = timezone.utc
EXECUTABLE_SYMBOL = "XAUUSDm"
DXY_CONSTITUENTS = frozenset({"EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF"})
REQUIRED_ANALYSIS_TIMEFRAMES = frozenset({"M5", "M15", "H1", "H4", "D1", "W1"})
DEFAULT_WARMUP_RECORDS = {
    "M5": 35,
    "M15": 2,
    "H1": 20,
    "H4": 20,
    "D1": 20,
    "W1": 2,
}
VALIDATION_FIDELITIES = frozenset({
    FidelityClass.TICK_BID_ASK,
    FidelityClass.BAR_BID_ASK,
    FidelityClass.MID_BAR_WITH_OBSERVED_COSTS,
})


def load_empirical_package_manifest(path: Path) -> EmpiricalPackageManifest:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        period = raw["evaluation_period"]
        streams = tuple(DataStreamManifest(
            name=item["name"],
            kind=DataStreamKind(item["kind"]),
            relative_path=item["relative_path"],
            sha256=item["sha256"],
            symbol=item["symbol"],
            start=parse_utc(item["start"], f"{item['name']} start"),
            end=parse_utc(item["end"], f"{item['name']} end"),
            record_count=item["record_count"],
            provenance=item["provenance"],
            license_or_restrictions=item["license_or_restrictions"],
            timeframe=item.get("timeframe"),
            maximum_expected_gap_seconds=item.get("maximum_expected_gap_seconds"),
        ) for item in raw["streams"])
        return EmpiricalPackageManifest(
            schema_version=raw["schema_version"],
            package_id=raw["package_id"],
            broker_source=raw["broker_source"],
            fidelity=FidelityClass(raw["fidelity"]),
            evaluation_period=StudyPeriod(
                parse_utc(period["start"], "evaluation start"),
                parse_utc(period["end"], "evaluation end"),
                period["name"],
            ),
            streams=streams,
            synthetic=raw["synthetic"],
            collection_method=raw["collection_method"],
            created_at=parse_utc(raw["created_at"], "package creation time"),
            raw_data_outside_git=raw["raw_data_outside_git"],
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("empirical package manifest is malformed") from exc


@dataclass(frozen=True)
class _InspectedStream:
    manifest: DataStreamManifest
    records: tuple[Mapping[str, Any], ...]
    timestamps: tuple[datetime, ...]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_acceptance_report(path: Path, report: AcceptanceReport) -> None:
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"acceptance report already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            json.dump(canonical_data(report), handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def load_acceptance_report(path: Path) -> AcceptanceReport:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return AcceptanceReport(
            package_id=raw["package_id"],
            package_hash=raw["package_hash"],
            outcome=AcceptanceOutcome(raw["outcome"]),
            checked_at=parse_utc(raw["checked_at"], "acceptance check time"),
            issues=tuple(AcceptanceIssue(
                reason_code=item["reason_code"],
                stream=item.get("stream"),
                detail=item["detail"],
                fatal=item.get("fatal", True),
            ) for item in raw["issues"]),
            accepted_stream_hashes=raw["accepted_stream_hashes"],
            fidelity=FidelityClass(raw["fidelity"]),
            synthetic_label=raw.get("synthetic_label"),
            framework_version=raw["framework_version"],
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("acceptance report is malformed") from exc


def _issue(code: str, stream: str | None, detail: str, *, fatal: bool = True) -> AcceptanceIssue:
    return AcceptanceIssue(reason_code=code, stream=stream, detail=detail, fatal=fatal)


def _load_records(path: Path, stream: DataStreamManifest) -> tuple[Mapping[str, Any], ...]:
    try:
        if stream.kind is DataStreamKind.BROKER_METADATA:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, Mapping):
                raise ValidationError("metadata root must be an object")
            return (value,)
        if path.suffix.lower() == ".parquet":
            from bot.acquisition.columnar import read_bar_records, read_tick_records

            if stream.kind is DataStreamKind.EXECUTION_QUOTES:
                return read_tick_records(path)
            if stream.kind in {DataStreamKind.ANALYSIS_CANDLES, DataStreamKind.DXY_CONSTITUENT}:
                return read_bar_records(path)
            raise ValidationError("Parquet is unsupported for this stream kind")
        records = []
        opener = gzip.open if path.suffix.lower() == ".gz" else Path.open
        with opener(path, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, Mapping):
                    raise ValidationError(f"record {line_number} is not an object")
                records.append(value)
        return tuple(records)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, AcquisitionError) as exc:
        raise ValidationError(f"cannot parse {stream.name}: {type(exc).__name__}") from exc


def _record_timestamp(record: Mapping[str, Any], stream: DataStreamManifest) -> datetime:
    if stream.kind is DataStreamKind.BROKER_METADATA:
        key = "effective_from"
    elif stream.kind is DataStreamKind.ANALYSIS_CANDLES:
        key = "available_at"
    else:
        key = "timestamp"
    if key not in record:
        raise ValidationError(f"{stream.name} record is missing {key}")
    return parse_utc(str(record[key]), f"{stream.name} {key}")


def _finite_positive(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValidationError(f"{field_name} must be positive and finite")
    return number


def _validate_quote(record: Mapping[str, Any], stream: DataStreamManifest) -> None:
    bid = _finite_positive(record.get("bid"), f"{stream.name} bid")
    ask = _finite_positive(record.get("ask"), f"{stream.name} ask")
    if ask < bid:
        raise ValidationError(f"{stream.name} contains a crossed quote")


def _validate_candle(record: Mapping[str, Any], stream: DataStreamManifest) -> None:
    open_price = _finite_positive(record.get("open"), f"{stream.name} open")
    high = _finite_positive(record.get("high"), f"{stream.name} high")
    low = _finite_positive(record.get("low"), f"{stream.name} low")
    close = _finite_positive(record.get("close"), f"{stream.name} close")
    open_time = parse_utc(str(record.get("open_time")), f"{stream.name} open_time")
    available_at = parse_utc(str(record.get("available_at")), f"{stream.name} available_at")
    if available_at <= open_time:
        raise ValidationError(f"{stream.name} candle availability must follow opening")
    if high < max(open_price, close, low) or low > min(open_price, close, high):
        raise ValidationError(f"{stream.name} contains invalid OHLC relationships")


def _validate_news(record: Mapping[str, Any], stream: DataStreamManifest) -> None:
    required = ("event_id", "currency", "impact", "name", "provider", "retrieved_at")
    if any(not record.get(key) for key in required):
        raise ValidationError(f"{stream.name} contains malformed news data")
    if str(record["impact"]).upper() not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValidationError(f"{stream.name} contains unknown impact")
    parse_utc(str(record["retrieved_at"]), f"{stream.name} retrieval time")


def _validate_metadata(record: Mapping[str, Any], stream: DataStreamManifest) -> None:
    required_positive = (
        "digits", "point_size", "tick_size", "tick_value", "contract_size",
        "volume_min", "volume_max", "volume_step", "margin_rate",
    )
    if record.get("symbol") != EXECUTABLE_SYMBOL:
        raise ValidationError("broker metadata must describe exactly XAUUSDm")
    for key in required_positive:
        _finite_positive(record.get(key), f"metadata {key}")
    for key in ("account_currency", "profit_currency", "margin_currency", "broker_source"):
        if not record.get(key):
            raise ValidationError(f"metadata {key} is required")
    for key in ("commission", "swap"):
        value = record.get(key)
        if not isinstance(value, Mapping) or str(value.get("source", "")).upper() != "OBSERVED":
            raise ValidationError(f"metadata {key} requires observed provenance")
    parse_utc(str(record.get("effective_to")), "metadata effective_to")


def _validate_record(record: Mapping[str, Any], stream: DataStreamManifest) -> None:
    if stream.kind is DataStreamKind.EXECUTION_QUOTES:
        _validate_quote(record, stream)
    elif stream.kind is DataStreamKind.ANALYSIS_CANDLES:
        _validate_candle(record, stream)
    elif stream.kind in {DataStreamKind.DXY_CONSTITUENT, DataStreamKind.DIRECT_DXY}:
        _finite_positive(record.get("close"), f"{stream.name} close")
    elif stream.kind is DataStreamKind.NEWS_EVENTS:
        _validate_news(record, stream)
    elif stream.kind is DataStreamKind.BROKER_METADATA:
        _validate_metadata(record, stream)
    elif stream.kind is DataStreamKind.SLIPPAGE_OBSERVATIONS:
        value = float(record.get("slippage_price", float("nan")))
        if not math.isfinite(value) or value < 0:
            raise ValidationError(f"{stream.name} slippage must be finite and non-negative")


def _recognized_weekend_gap(previous: datetime, current: datetime) -> bool:
    return previous.weekday() == 4 and current.weekday() in {6, 0}


def _inspect_stream(root: Path, stream: DataStreamManifest) -> tuple[_InspectedStream | None, list[AcceptanceIssue]]:
    path = Path(root) / Path(stream.relative_path)
    if not path.is_file():
        return None, [_issue("STREAM_FILE_MISSING", stream.name, "required stream file is missing")]
    actual_hash = file_sha256(path)
    if actual_hash != stream.sha256:
        return None, [_issue("HASH_MISMATCH", stream.name, "stream SHA-256 does not match manifest")]
    try:
        records = _load_records(path, stream)
    except ValidationError as exc:
        return None, [_issue("STREAM_CORRUPT", stream.name, str(exc))]
    if len(records) != stream.record_count:
        return None, [_issue("RECORD_COUNT_MISMATCH", stream.name, "record count does not match manifest")]
    timestamps: list[datetime] = []
    try:
        for record in records:
            timestamp = _record_timestamp(record, stream)
            _validate_record(record, stream)
            timestamps.append(timestamp)
    except ValidationError as exc:
        return None, [_issue("STREAM_CONTENT_INVALID", stream.name, str(exc))]
    if timestamps != sorted(timestamps):
        return None, [_issue("TIMESTAMPS_UNSORTED", stream.name, "records are not chronological")]
    if stream.kind is DataStreamKind.EXECUTION_QUOTES:
        if len(timestamps) != len(set(timestamps)):
            identities = [(timestamp, str(record.get("sequence_id") or "")) for timestamp, record in zip(timestamps, records)]
            if any(not identity[1] for identity in identities) or len(identities) != len(set(identities)):
                return None, [_issue("DUPLICATE_TIMESTAMP", stream.name, "same-time ticks require unique sequence identities")]
    elif len(timestamps) != len(set(timestamps)):
        return None, [_issue("DUPLICATE_TIMESTAMP", stream.name, "duplicate timestamps are prohibited")]
    if timestamps and (timestamps[0] < stream.start or timestamps[-1] > stream.end):
        return None, [_issue("TIMESTAMP_OUTSIDE_MANIFEST", stream.name, "record lies outside declared coverage")]
    issues: list[AcceptanceIssue] = []
    maximum_gap = stream.maximum_expected_gap_seconds
    if maximum_gap:
        for previous, current in zip(timestamps, timestamps[1:]):
            if (current - previous).total_seconds() > maximum_gap and not _recognized_weekend_gap(previous, current):
                issues.append(_issue("UNEXPLAINED_GAP", stream.name, "gap exceeds declared maximum"))
                break
    return _InspectedStream(stream, records, tuple(timestamps)), issues


def _required_stream_issues(
    manifest: EmpiricalPackageManifest,
    inspected: Iterable[_InspectedStream],
    warmup_records: Mapping[str, int],
) -> list[AcceptanceIssue]:
    issues: list[AcceptanceIssue] = []
    streams = tuple(item.manifest for item in inspected)
    execution = [item for item in streams if item.kind is DataStreamKind.EXECUTION_QUOTES and item.symbol == EXECUTABLE_SYMBOL]
    if not execution:
        issues.append(_issue("EXECUTION_STREAM_REQUIRED", None, "one or more XAUUSDm execution chunks are required"))
    analysis_groups: dict[str | None, list[DataStreamManifest]] = {}
    for item in streams:
        if item.kind is DataStreamKind.ANALYSIS_CANDLES and item.symbol == EXECUTABLE_SYMBOL:
            analysis_groups.setdefault(item.timeframe, []).append(item)
    analysis = {timeframe: values[0] for timeframe, values in analysis_groups.items()}
    missing_timeframes = REQUIRED_ANALYSIS_TIMEFRAMES - set(analysis)
    if missing_timeframes:
        issues.append(_issue("ANALYSIS_TIMEFRAME_MISSING", None, ",".join(sorted(missing_timeframes))))
    inspected_by_name = {item.manifest.name: item for item in inspected}
    for item in inspected:
        if item.manifest.kind is DataStreamKind.BROKER_METADATA:
            effective_to = parse_utc(str(item.records[0].get("effective_to")), "metadata effective_to")
            if item.timestamps[0] > manifest.evaluation_period.start or effective_to < manifest.evaluation_period.end:
                issues.append(_issue("METADATA_PERIOD_MISMATCH", item.manifest.name, "metadata does not cover evaluation"))
        elif not item.timestamps or item.timestamps[0] > manifest.evaluation_period.start or item.timestamps[-1] < manifest.evaluation_period.end:
            issues.append(_issue("COVERAGE_MISMATCH", item.manifest.name, "records do not cover the evaluation period"))
    for timeframe, minimum in warmup_records.items():
        timeframe_streams = analysis_groups.get(timeframe, [])
        record_count = sum(
            len(inspected_by_name[item.name].records)
            for item in timeframe_streams
            if item.name in inspected_by_name
        )
        if timeframe_streams and record_count < minimum:
            issues.append(_issue("INSUFFICIENT_WARMUP", timeframe_streams[0].name, f"{timeframe} requires at least {minimum} records"))
    direct_dxy = [item for item in streams if item.kind is DataStreamKind.DIRECT_DXY]
    constituents = {item.symbol for item in streams if item.kind is DataStreamKind.DXY_CONSTITUENT}
    if not direct_dxy and constituents != DXY_CONSTITUENTS:
        missing = DXY_CONSTITUENTS - constituents
        issues.append(_issue("DXY_COVERAGE_INCOMPLETE", None, ",".join(sorted(missing))))
    if not any(item.kind is DataStreamKind.NEWS_EVENTS for item in streams):
        issues.append(_issue("NEWS_HISTORY_MISSING", None, "historical news coverage is required"))
    if not any(item.kind is DataStreamKind.BROKER_METADATA for item in streams):
        issues.append(_issue("BROKER_METADATA_MISSING", None, "dated broker metadata is required"))
    if not any(item.kind is DataStreamKind.SLIPPAGE_OBSERVATIONS for item in streams):
        issues.append(_issue("SLIPPAGE_PROVENANCE_MISSING", None, "slippage evidence is required"))
    grouped: dict[tuple[DataStreamKind, str, str | None], list[DataStreamManifest]] = {}
    for stream in streams:
        if stream.kind is DataStreamKind.BROKER_METADATA:
            continue
        grouped.setdefault((stream.kind, stream.symbol, stream.timeframe), []).append(stream)
    for (_kind, _symbol, _timeframe), parts in grouped.items():
        tolerance_seconds = max((item.maximum_expected_gap_seconds or 0) for item in parts)
        tolerance = timedelta(seconds=tolerance_seconds)
        if (
            min(item.start for item in parts) - tolerance > manifest.evaluation_period.start
            or max(item.end for item in parts) + tolerance < manifest.evaluation_period.end
        ):
            issues.append(_issue("COVERAGE_MISMATCH", parts[0].name, "combined stream chunks do not cover the evaluation period"))
        ordered = sorted(parts, key=lambda item: item.start)
        if any(current.start < previous.end for previous, current in zip(ordered, ordered[1:])):
            issues.append(_issue("CHUNK_OVERLAP", parts[0].name, "logical stream chunks overlap"))
        for previous, current in zip(ordered, ordered[1:]):
            if (
                tolerance_seconds
                and (current.start - previous.end).total_seconds() > tolerance_seconds
                and not _recognized_weekend_gap(previous.end, current.start)
            ):
                issues.append(_issue("CHUNK_GAP", parts[0].name, "logical stream chunks have an unexplained gap"))
                break
    for stream in streams:
        if "NO_VALIDATION" in stream.license_or_restrictions.upper():
            issues.append(_issue("LICENSE_RESTRICTS_VALIDATION", stream.name, "recorded license disallows validation"))
    return issues


def validate_dataset_package(
    manifest: EmpiricalPackageManifest,
    package_root: Path,
    *,
    checked_at: datetime,
    warmup_records: Mapping[str, int] = DEFAULT_WARMUP_RECORDS,
) -> AcceptanceReport:
    inspected: list[_InspectedStream] = []
    issues: list[AcceptanceIssue] = []
    hashes: dict[str, str] = {}
    provenance_values = [manifest.broker_source, manifest.collection_method]
    provenance_values.extend(stream.provenance for stream in manifest.streams)
    if not manifest.synthetic and any("SYNTHETIC" in value.upper() for value in provenance_values):
        issues.append(_issue("SYNTHETIC_PACKAGE_MISLABELED", None, "synthetic provenance cannot be declared empirical"))
    for stream in manifest.streams:
        item, stream_issues = _inspect_stream(Path(package_root), stream)
        issues.extend(stream_issues)
        if item:
            inspected.append(item)
            hashes[stream.name] = stream.sha256
    issues.extend(_required_stream_issues(manifest, inspected, warmup_records))
    if manifest.fidelity not in VALIDATION_FIDELITIES:
        issues.append(_issue("FIDELITY_NOT_VALIDATION_ELIGIBLE", None, manifest.fidelity.value, fatal=False))
    if any(issue.fatal for issue in issues):
        outcome = AcceptanceOutcome.REJECTED
    elif manifest.fidelity not in VALIDATION_FIDELITIES:
        outcome = AcceptanceOutcome.DIAGNOSTIC_ONLY
    elif manifest.synthetic:
        outcome = AcceptanceOutcome.ACCEPTED_FOR_DEVELOPMENT_ONLY
    else:
        outcome = AcceptanceOutcome.ACCEPTED_FOR_FINAL_VALIDATION
    return AcceptanceReport(
        package_id=manifest.package_id,
        package_hash=manifest.package_hash,
        outcome=outcome,
        checked_at=checked_at,
        issues=tuple(issues),
        accepted_stream_hashes=dict(sorted(hashes.items())),
        fidelity=manifest.fidelity,
        synthetic_label=SYNTHETIC_LABEL if manifest.synthetic else None,
    )
