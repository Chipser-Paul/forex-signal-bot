from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Iterator, Mapping

from filelock import FileLock

from bot.backtesting.models import HistoricalQuote
from bot.validation.models import canonical_data

from .models import AcquisitionError, ChunkSummary, EXECUTABLE_SYMBOL, utc_datetime
from .storage import _inside, atomic_json, file_sha256, output_size, validate_output_root


UTC = timezone.utc
TICK_SCHEMA_VERSION = "phase8b.tick.v1"
BAR_SCHEMA_VERSION = "phase8b.bar.v1"
PRICE_SCALE = 8
VOLUME_SCALE = 8


def _arrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise AcquisitionError(
            "Parquet support is optional; install requirements-data.txt in the acquisition environment"
        ) from exc
    return pa, pq


def tick_schema():
    pa, _pq = _arrow()
    return pa.schema(
        [
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("timestamp", pa.timestamp("ms", tz="UTC"), nullable=False),
            pa.field("time_msc", pa.int64(), nullable=False),
            pa.field("bid", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("ask", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("last", pa.decimal128(20, PRICE_SCALE), nullable=True),
            pa.field("volume", pa.decimal128(24, VOLUME_SCALE), nullable=False),
            pa.field("volume_real", pa.decimal128(24, VOLUME_SCALE), nullable=False),
            pa.field("flags", pa.uint32(), nullable=False),
            pa.field("sequence_id", pa.string(), nullable=False),
            pa.field("row_identity", pa.string(), nullable=False),
            pa.field("source_chunk_id", pa.string(), nullable=False),
            pa.field("provenance_id", pa.string(), nullable=False),
        ],
        metadata={b"schema_version": TICK_SCHEMA_VERSION.encode("ascii")},
    )


def bar_schema():
    pa, _pq = _arrow()
    return pa.schema(
        [
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("timeframe", pa.string(), nullable=False),
            pa.field("open_time", pa.timestamp("ms", tz="UTC"), nullable=False),
            pa.field("available_at", pa.timestamp("ms", tz="UTC"), nullable=False),
            pa.field("open", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("high", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("low", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("close", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("tick_volume", pa.decimal128(24, VOLUME_SCALE), nullable=True),
            pa.field("spread", pa.decimal128(20, PRICE_SCALE), nullable=True),
            pa.field("real_volume", pa.decimal128(24, VOLUME_SCALE), nullable=True),
            pa.field("sequence_id", pa.string(), nullable=False),
            pa.field("provenance_id", pa.string(), nullable=False),
        ],
        metadata={b"schema_version": BAR_SCHEMA_VERSION.encode("ascii")},
    )


def _decimal(value: object, *, scale: int, nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    try:
        number = Decimal(str(value))
        quantized = number.quantize(Decimal(1).scaleb(-scale))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AcquisitionError("tick numeric field is not representable in the columnar schema") from exc
    if not number.is_finite():
        raise AcquisitionError("tick numeric field must be finite")
    return quantized


def _timestamp_from_record(record: Mapping[str, object]) -> datetime:
    milliseconds = int(record["time_msc"])
    timestamp = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    supplied = datetime.fromisoformat(str(record["timestamp"]).replace("Z", "+00:00"))
    if supplied.tzinfo is None or supplied.astimezone(UTC) != timestamp:
        raise AcquisitionError("tick timestamp and source millisecond value disagree")
    return timestamp


def _canonical_tick(record: Mapping[str, object]) -> dict[str, object]:
    if str(record.get("symbol")) != EXECUTABLE_SYMBOL:
        raise AcquisitionError("columnar tick data is restricted to exact XAUUSDm")
    return {
        "symbol": str(record["symbol"]),
        "time_msc": int(record["time_msc"]),
        "bid": format(_decimal(record["bid"], scale=PRICE_SCALE), "f"),
        "ask": format(_decimal(record["ask"], scale=PRICE_SCALE), "f"),
        "last": None if record.get("last") is None else format(_decimal(record["last"], scale=PRICE_SCALE), "f"),
        "volume": format(_decimal(record.get("volume", 0), scale=VOLUME_SCALE), "f"),
        "volume_real": format(_decimal(record.get("volume_real", 0), scale=VOLUME_SCALE), "f"),
        "flags": int(record.get("flags", 0)),
        "sequence_id": str(record["sequence_id"]),
        "row_identity": str(record["row_identity"]),
        "source_chunk_id": str(record["source_chunk_id"]),
        "provenance_id": str(record.get("provenance_id") or "mt5-read-only-history-v1"),
    }


def canonical_tick_hash(records: Iterable[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        encoded = json.dumps(
            _canonical_tick(record), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
        digest.update(encoded)
        digest.update(b"\n")
    return digest.hexdigest()


def _table(records: tuple[Mapping[str, object], ...]):
    pa, _pq = _arrow()
    schema = tick_schema()
    columns = {
        "symbol": [str(item["symbol"]) for item in records],
        "timestamp": [_timestamp_from_record(item) for item in records],
        "time_msc": [int(item["time_msc"]) for item in records],
        "bid": [_decimal(item["bid"], scale=PRICE_SCALE) for item in records],
        "ask": [_decimal(item["ask"], scale=PRICE_SCALE) for item in records],
        "last": [_decimal(item.get("last"), scale=PRICE_SCALE, nullable=True) for item in records],
        "volume": [_decimal(item.get("volume", 0), scale=VOLUME_SCALE) for item in records],
        "volume_real": [_decimal(item.get("volume_real", 0), scale=VOLUME_SCALE) for item in records],
        "flags": [int(item.get("flags", 0)) for item in records],
        "sequence_id": [str(item["sequence_id"]) for item in records],
        "row_identity": [str(item["row_identity"]) for item in records],
        "source_chunk_id": [str(item["source_chunk_id"]) for item in records],
        "provenance_id": [str(item.get("provenance_id") or "mt5-read-only-history-v1") for item in records],
    }
    return pa.Table.from_pydict(columns, schema=schema)


def read_tick_records(path: Path) -> tuple[dict[str, object], ...]:
    _pa, pq = _arrow()
    path = Path(path)
    try:
        table = pq.read_table(path)
    except Exception as exc:
        raise AcquisitionError("Parquet tick partition is unreadable") from exc
    if table.schema != tick_schema():
        raise AcquisitionError("Parquet tick schema is incompatible")
    rows: list[dict[str, object]] = []
    for item in table.to_pylist():
        if item["symbol"] != EXECUTABLE_SYMBOL:
            raise AcquisitionError("Parquet tick partition contains a non-executable symbol")
        timestamp = item["timestamp"].astimezone(UTC)
        rows.append(
            {
                "symbol": item["symbol"],
                "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                "time": int(item["time_msc"]) // 1000,
                "time_msc": int(item["time_msc"]),
                "bid": format(item["bid"], "f"),
                "ask": format(item["ask"], "f"),
                "last": None if item["last"] is None else format(item["last"], "f"),
                "volume": format(item["volume"], "f"),
                "volume_real": format(item["volume_real"], "f"),
                "flags": int(item["flags"]),
                "sequence_id": item["sequence_id"],
                "row_identity": item["row_identity"],
                "source_chunk_id": item["source_chunk_id"],
                "provenance_id": item["provenance_id"],
            }
        )
    return tuple(rows)


def iter_historical_quotes(path: Path) -> Iterator[HistoricalQuote]:
    for item in read_tick_records(path):
        yield HistoricalQuote(
            symbol=str(item["symbol"]),
            timestamp=datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00")),
            bid=float(item["bid"]),
            ask=float(item["ask"]),
            source=str(item["provenance_id"]),
            dataset_id=str(item["source_chunk_id"]),
            sequence_id=str(item["sequence_id"]),
            bid_volume=float(item["volume"]),
            ask_volume=float(item["volume"]),
        )


class ParquetTickStore:
    def __init__(self, root: Path, *, maximum_output_bytes: int, minimum_free_bytes: int = 0) -> None:
        self.root = validate_output_root(root, forbidden_roots=())
        self.maximum_output_bytes = int(maximum_output_bytes)
        self.minimum_free_bytes = int(minimum_free_bytes)
        if self.maximum_output_bytes <= 0 or self.minimum_free_bytes < 0:
            raise AcquisitionError("columnar storage limits are invalid")
        self.root.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        relative_path: str,
        records: Iterable[Mapping[str, object]],
        *,
        chunk_id: str,
        requested_start: datetime,
        requested_end: datetime,
        diagnostics: Mapping[str, int] | None = None,
        resume: bool = False,
    ) -> ChunkSummary:
        with FileLock(str(self.root / ".parquet.lock"), timeout=30):
            return self._write_locked(
                relative_path,
                tuple(records),
                chunk_id=chunk_id,
                requested_start=requested_start,
                requested_end=requested_end,
                diagnostics=diagnostics,
                resume=resume,
            )

    def _write_locked(self, relative_path: str, records: tuple[Mapping[str, object], ...], **kwargs) -> ChunkSummary:
        chunk_id = str(kwargs["chunk_id"])
        requested_start = utc_datetime(kwargs["requested_start"], "requested chunk start")
        requested_end = utc_datetime(kwargs["requested_end"], "requested chunk end")
        diagnostics = kwargs.get("diagnostics") or {}
        resume = bool(kwargs.get("resume"))
        if requested_end <= requested_start:
            raise AcquisitionError("requested chunk interval must increase")
        final_path = self._safe_path(relative_path)
        marker_path = final_path.with_suffix(final_path.suffix + ".complete.json")
        if final_path.exists() or marker_path.exists():
            if resume and final_path.is_file() and marker_path.is_file():
                return self.verify(relative_path)
            raise FileExistsError(f"completed partition already exists: {final_path.name}")
        partial_path = final_path.with_suffix(final_path.suffix + ".partial")
        if partial_path.exists():
            raise AcquisitionError("partial Parquet partition must be removed after investigation")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        ordered = tuple(sorted(records, key=lambda item: (int(item["time_msc"]), str(item["sequence_id"]))))
        if records != ordered:
            raise AcquisitionError("Parquet tick input must be deterministically ordered")
        content_hash = canonical_tick_hash(ordered)
        start = requested_start if not ordered else _timestamp_from_record(ordered[0])
        end = requested_end if not ordered else _timestamp_from_record(ordered[-1])
        try:
            _pa, pq = _arrow()
            pq.write_table(
                _table(ordered), partial_path, compression="zstd", compression_level=9,
                use_dictionary=("symbol", "source_chunk_id", "provenance_id"),
                write_statistics=True, row_group_size=250_000,
            )
            with partial_path.open("r+b") as handle:
                os.fsync(handle.fileno())
            projected = output_size(self.root)
            free_after = shutil.disk_usage(self.root).free - partial_path.stat().st_size
            if projected > self.maximum_output_bytes:
                raise AcquisitionError("output budget would be exceeded")
            if free_after < self.minimum_free_bytes:
                raise AcquisitionError("disk safety reserve would be breached")
            os.replace(partial_path, final_path)
            summary = ChunkSummary(
                chunk_id=chunk_id,
                relative_path=final_path.relative_to(self.root).as_posix(),
                sha256=file_sha256(final_path),
                record_count=len(ordered),
                start=start,
                end=end,
                size_bytes=final_path.stat().st_size,
                duplicate_count=int(diagnostics.get("duplicate_count", 0)),
                crossed_quote_count=int(diagnostics.get("crossed_quote_count", 0)),
                zero_quote_count=int(diagnostics.get("zero_quote_count", 0)),
                gap_count=int(diagnostics.get("gap_count", 0)),
                complete=True,
                canonical_content_sha256=content_hash,
                schema_version=TICK_SCHEMA_VERSION,
                storage_format="parquet",
                compression="zstd",
                requested_start=requested_start,
                requested_end=requested_end,
            )
            atomic_json(marker_path, asdict(summary))
            return summary
        except Exception:
            partial_path.unlink(missing_ok=True)
            if final_path.exists() and not marker_path.exists():
                final_path.unlink()
            raise

    def verify(self, relative_path: str) -> ChunkSummary:
        final_path = self._safe_path(relative_path)
        marker_path = final_path.with_suffix(final_path.suffix + ".complete.json")
        if not final_path.is_file() or not marker_path.is_file():
            raise AcquisitionError("Parquet partition is incomplete")
        try:
            raw = json.loads(marker_path.read_text(encoding="utf-8"))
            summary = ChunkSummary(
                chunk_id=str(raw["chunk_id"]), relative_path=str(raw["relative_path"]),
                sha256=str(raw["sha256"]), record_count=int(raw["record_count"]),
                start=datetime.fromisoformat(str(raw["start"]).replace("Z", "+00:00")),
                end=datetime.fromisoformat(str(raw["end"]).replace("Z", "+00:00")),
                size_bytes=int(raw["size_bytes"]), duplicate_count=int(raw["duplicate_count"]),
                crossed_quote_count=int(raw["crossed_quote_count"]), zero_quote_count=int(raw["zero_quote_count"]),
                gap_count=int(raw["gap_count"]), complete=raw["complete"] is True,
                canonical_content_sha256=str(raw["canonical_content_sha256"]),
                schema_version=str(raw["schema_version"]), storage_format=str(raw["storage_format"]),
                compression=str(raw["compression"]),
                requested_start=datetime.fromisoformat(str(raw["requested_start"]).replace("Z", "+00:00")),
                requested_end=datetime.fromisoformat(str(raw["requested_end"]).replace("Z", "+00:00")),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AcquisitionError("Parquet completion marker is invalid") from exc
        if (
            not summary.complete or summary.schema_version != TICK_SCHEMA_VERSION
            or summary.storage_format != "parquet" or summary.compression != "zstd"
            or summary.relative_path != final_path.relative_to(self.root).as_posix()
        ):
            raise AcquisitionError("Parquet completion marker is incompatible")
        if file_sha256(final_path) != summary.sha256 or final_path.stat().st_size != summary.size_bytes:
            raise AcquisitionError("Parquet file hash or size mismatch")
        requested_start = utc_datetime(summary.requested_start, "marker requested start")
        requested_end = utc_datetime(summary.requested_end, "marker requested end")
        if requested_end <= requested_start:
            raise AcquisitionError("Parquet marker interval is invalid")
        records = read_tick_records(final_path)
        if len(records) != summary.record_count or canonical_tick_hash(records) != summary.canonical_content_sha256:
            raise AcquisitionError("Parquet canonical content hash or row count mismatch")
        timestamps = tuple(_timestamp_from_record(item) for item in records)
        if timestamps != tuple(sorted(timestamps)) or any(not requested_start <= item < requested_end for item in timestamps):
            raise AcquisitionError("Parquet rows violate ordering or requested coverage")
        expected_start = requested_start if not timestamps else timestamps[0]
        expected_end = requested_end if not timestamps else timestamps[-1]
        if summary.start != expected_start or summary.end != expected_end:
            raise AcquisitionError("Parquet marker timestamps do not match content")
        return summary

    def _safe_path(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise AcquisitionError("partition path must be package-relative")
        path = (self.root / relative).resolve(strict=False)
        if not _inside(path, self.root.resolve(strict=False)):
            raise AcquisitionError("partition path escapes the output root")
        return path


def _bar_time(value: object, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise AcquisitionError(f"bar {name} is malformed") from exc
    return utc_datetime(parsed, f"bar {name}")


def _canonical_bar(record: Mapping[str, object]) -> dict[str, object]:
    result = {
        "symbol": str(record["symbol"]), "timeframe": str(record["timeframe"]),
        "open_time": _bar_time(record["open_time"], "open time").isoformat(),
        "available_at": _bar_time(record["available_at"], "availability").isoformat(),
        "sequence_id": str(record["sequence_id"]),
        "provenance_id": str(record.get("provenance_id") or "mt5-read-only-history-v1"),
    }
    for name in ("open", "high", "low", "close"):
        result[name] = format(_decimal(record[name], scale=PRICE_SCALE), "f")
    for name, scale in (("tick_volume", VOLUME_SCALE), ("spread", PRICE_SCALE), ("real_volume", VOLUME_SCALE)):
        result[name] = None if record.get(name) is None else format(_decimal(record[name], scale=scale), "f")
    return result


def canonical_bar_hash(records: Iterable[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(json.dumps(_canonical_bar(record), sort_keys=True, separators=(",", ":")).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _bar_table(records: tuple[Mapping[str, object], ...]):
    pa, _pq = _arrow()
    canonical = tuple(_canonical_bar(item) for item in records)
    return pa.Table.from_pydict(
        {
            "symbol": [item["symbol"] for item in canonical],
            "timeframe": [item["timeframe"] for item in canonical],
            "open_time": [datetime.fromisoformat(str(item["open_time"])) for item in canonical],
            "available_at": [datetime.fromisoformat(str(item["available_at"])) for item in canonical],
            "open": [Decimal(str(item["open"])) for item in canonical],
            "high": [Decimal(str(item["high"])) for item in canonical],
            "low": [Decimal(str(item["low"])) for item in canonical],
            "close": [Decimal(str(item["close"])) for item in canonical],
            "tick_volume": [None if item["tick_volume"] is None else Decimal(str(item["tick_volume"])) for item in canonical],
            "spread": [None if item["spread"] is None else Decimal(str(item["spread"])) for item in canonical],
            "real_volume": [None if item["real_volume"] is None else Decimal(str(item["real_volume"])) for item in canonical],
            "sequence_id": [item["sequence_id"] for item in canonical],
            "provenance_id": [item["provenance_id"] for item in canonical],
        },
        schema=bar_schema(),
    )


def read_bar_records(path: Path) -> tuple[dict[str, object], ...]:
    _pa, pq = _arrow()
    try:
        table = pq.read_table(Path(path))
    except Exception as exc:
        raise AcquisitionError("Parquet bar partition is unreadable") from exc
    if table.schema != bar_schema():
        raise AcquisitionError("Parquet bar schema is incompatible")
    rows: list[dict[str, object]] = []
    for item in table.to_pylist():
        rows.append({
            **item,
            "open_time": item["open_time"].astimezone(UTC).isoformat(),
            "available_at": item["available_at"].astimezone(UTC).isoformat(),
            "timestamp": item["available_at"].astimezone(UTC).isoformat(),
            "open": str(item["open"]), "high": str(item["high"]),
            "low": str(item["low"]), "close": str(item["close"]),
            "tick_volume": None if item["tick_volume"] is None else str(item["tick_volume"]),
            "spread": None if item["spread"] is None else str(item["spread"]),
            "real_volume": None if item["real_volume"] is None else str(item["real_volume"]),
        })
    return tuple(rows)


class ParquetBarStore:
    def __init__(self, root: Path, *, maximum_output_bytes: int, minimum_free_bytes: int = 0) -> None:
        self.root = validate_output_root(root, forbidden_roots=())
        self.maximum_output_bytes = int(maximum_output_bytes)
        self.minimum_free_bytes = int(minimum_free_bytes)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(
        self, relative_path: str, records: Iterable[Mapping[str, object]], *, chunk_id: str,
        requested_start: datetime, requested_end: datetime, resume: bool = False,
    ) -> ChunkSummary:
        with FileLock(str(self.root / ".parquet.lock"), timeout=30):
            final_path = self._safe_path(relative_path)
            marker_path = final_path.with_suffix(final_path.suffix + ".complete.json")
            if final_path.exists() or marker_path.exists():
                if resume and final_path.is_file() and marker_path.is_file():
                    return self.verify(relative_path)
                raise FileExistsError(f"completed partition already exists: {final_path.name}")
            partial = final_path.with_suffix(final_path.suffix + ".partial")
            if partial.exists():
                raise AcquisitionError("partial Parquet partition must be removed after investigation")
            rows = tuple(records)
            ordered = tuple(sorted(rows, key=lambda item: (_bar_time(item["open_time"], "open time"), str(item["sequence_id"]))))
            if rows != ordered:
                raise AcquisitionError("Parquet bar input must be deterministically ordered")
            final_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                _pa, pq = _arrow()
                pq.write_table(_bar_table(ordered), partial, compression="zstd", compression_level=9,
                               use_dictionary=("symbol", "timeframe", "provenance_id"), write_statistics=True)
                with partial.open("r+b") as handle:
                    os.fsync(handle.fileno())
                if output_size(self.root) > self.maximum_output_bytes:
                    raise AcquisitionError("output budget would be exceeded")
                if shutil.disk_usage(self.root).free - partial.stat().st_size < self.minimum_free_bytes:
                    raise AcquisitionError("disk safety reserve would be breached")
                os.replace(partial, final_path)
                start = utc_datetime(requested_start, "bar chunk start") if not ordered else _bar_time(ordered[0]["open_time"], "open time")
                end = utc_datetime(requested_end, "bar chunk end") if not ordered else _bar_time(ordered[-1]["available_at"], "availability")
                summary = ChunkSummary(
                    chunk_id=chunk_id, relative_path=final_path.relative_to(self.root).as_posix(),
                    sha256=file_sha256(final_path), record_count=len(ordered), start=start, end=end,
                    size_bytes=final_path.stat().st_size, duplicate_count=0, crossed_quote_count=0,
                    zero_quote_count=0, gap_count=0, complete=True,
                    canonical_content_sha256=canonical_bar_hash(ordered), schema_version=BAR_SCHEMA_VERSION,
                    storage_format="parquet", compression="zstd", requested_start=requested_start,
                    requested_end=requested_end,
                )
                atomic_json(marker_path, asdict(summary))
                return summary
            except Exception:
                partial.unlink(missing_ok=True)
                if final_path.exists() and not marker_path.exists():
                    final_path.unlink()
                raise

    def verify(self, relative_path: str) -> ChunkSummary:
        final = self._safe_path(relative_path)
        marker = final.with_suffix(final.suffix + ".complete.json")
        if not final.is_file() or not marker.is_file():
            raise AcquisitionError("Parquet bar partition is incomplete")
        try:
            raw = json.loads(marker.read_text(encoding="utf-8"))
            _pa, pq = _arrow()
            table = pq.read_table(final)
        except Exception as exc:
            raise AcquisitionError("Parquet bar partition is unreadable") from exc
        if table.schema != bar_schema() or raw.get("schema_version") != BAR_SCHEMA_VERSION:
            raise AcquisitionError("Parquet bar schema is incompatible")
        if file_sha256(final) != raw.get("sha256") or final.stat().st_size != int(raw.get("size_bytes", -1)):
            raise AcquisitionError("Parquet bar file hash or size mismatch")
        rows = read_bar_records(final)
        if len(rows) != int(raw.get("record_count", -1)) or canonical_bar_hash(rows) != raw.get("canonical_content_sha256"):
            raise AcquisitionError("Parquet bar canonical content mismatch")
        summary = ChunkSummary(
            chunk_id=str(raw["chunk_id"]), relative_path=str(raw["relative_path"]), sha256=str(raw["sha256"]),
            record_count=int(raw["record_count"]), start=datetime.fromisoformat(str(raw["start"]).replace("Z", "+00:00")),
            end=datetime.fromisoformat(str(raw["end"]).replace("Z", "+00:00")), size_bytes=int(raw["size_bytes"]),
            duplicate_count=0, crossed_quote_count=0, zero_quote_count=0, gap_count=0, complete=True,
            canonical_content_sha256=str(raw["canonical_content_sha256"]), schema_version=BAR_SCHEMA_VERSION,
            storage_format="parquet", compression="zstd",
            requested_start=datetime.fromisoformat(str(raw["requested_start"]).replace("Z", "+00:00")),
            requested_end=datetime.fromisoformat(str(raw["requested_end"]).replace("Z", "+00:00")),
        )
        requested_start = utc_datetime(summary.requested_start, "bar marker requested start")
        requested_end = utc_datetime(summary.requested_end, "bar marker requested end")
        times = tuple(_bar_time(item["open_time"], "open time") for item in rows)
        if requested_end <= requested_start or times != tuple(sorted(times)):
            raise AcquisitionError("Parquet bar marker interval or ordering is invalid")
        if any(not requested_start <= item < requested_end for item in times):
            raise AcquisitionError("Parquet bar rows exceed requested coverage")
        return summary

    def _safe_path(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise AcquisitionError("partition path must be package-relative")
        path = (self.root / relative).resolve(strict=False)
        if not _inside(path, self.root.resolve(strict=False)):
            raise AcquisitionError("partition path escapes the output root")
        return path
