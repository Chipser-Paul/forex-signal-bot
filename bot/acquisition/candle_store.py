"""Phase 8C Parquet storage for bid/ask candles.

Provides a typed schema and atomic, non-overwriting publication for
causal XAUUSDm bid/ask candle partitions.

All read-back verification enforces:
  - ask >= bid for every price field pair
  - OHLC invariants (high >= open,close,low; low <= open,close)
  - available_at_ms >= close_time_ms (causal constraint)
  - open_time_ms ordering (strictly increasing open times)
  - Unique candle identities
  - No empty/synthetic candles

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Mapping

from filelock import FileLock

from bot.validation.models import canonical_data

from .candle_pipeline import SCHEMA_VERSION, CLASSIFICATION_LABEL, stable_candle_identity
from .models import AcquisitionError, EXECUTABLE_SYMBOL, utc_datetime
from .storage import _inside, atomic_json, file_sha256, output_size, validate_output_root


UTC = timezone.utc
PRICE_SCALE = 8
CANDLE_SCHEMA_VERSION = SCHEMA_VERSION


def _arrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise AcquisitionError(
            "Parquet support requires the pinned requirements-data.txt environment"
        ) from exc
    return pa, pq


def bidask_candle_schema():
    """Return the canonical PyArrow schema for bid/ask candle partitions."""
    pa, _ = _arrow()
    return pa.schema(
        [
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("timeframe", pa.string(), nullable=False),
            pa.field("open_time_ms", pa.int64(), nullable=False),
            pa.field("close_time_ms", pa.int64(), nullable=False),
            pa.field("available_at_ms", pa.int64(), nullable=False),
            pa.field("bid_open", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("bid_high", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("bid_low", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("bid_close", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("ask_open", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("ask_high", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("ask_low", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("ask_close", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("tick_count", pa.int64(), nullable=False),
            pa.field("spread_min", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("spread_max", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("spread_median", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("spread_close", pa.decimal128(20, PRICE_SCALE), nullable=False),
            pa.field("first_tick_ms", pa.int64(), nullable=False),
            pa.field("last_tick_ms", pa.int64(), nullable=False),
            pa.field("source_package_ids", pa.string(), nullable=False),  # JSON array
            pa.field("candle_identity", pa.string(), nullable=False),
            pa.field("schema_version", pa.string(), nullable=False),
            pa.field("classification", pa.string(), nullable=False),
        ],
        metadata={b"schema_version": CANDLE_SCHEMA_VERSION.encode("ascii")},
    )


def _dec(value: object, name: str) -> Decimal:
    """Convert a field to Decimal, raising AcquisitionError on failure."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AcquisitionError(f"candle field {name!r} is not representable as Decimal") from exc
    if not d.is_finite():
        raise AcquisitionError(f"candle field {name!r} must be finite")
    return d.quantize(Decimal(1).scaleb(-PRICE_SCALE))


def _validate_record(record: Mapping) -> dict:
    """Validate and normalise one candle record dict.

    Returns a cleaned dict.  Raises AcquisitionError on any invariant failure.
    """
    symbol = str(record.get("symbol", ""))
    if symbol != EXECUTABLE_SYMBOL:
        raise AcquisitionError(f"Candle symbol must be {EXECUTABLE_SYMBOL!r}, got {symbol!r}")

    timeframe = str(record.get("timeframe", ""))
    open_ms = int(record["open_time_ms"])
    close_ms = int(record["close_time_ms"])
    avail_ms = int(record["available_at_ms"])

    if close_ms <= open_ms:
        raise AcquisitionError(
            f"Candle close_time_ms ({close_ms}) must be > open_time_ms ({open_ms})"
        )
    if avail_ms < close_ms:
        raise AcquisitionError(
            f"Candle available_at_ms ({avail_ms}) must be >= close_time_ms ({close_ms})"
        )

    bid_open  = _dec(record["bid_open"],  "bid_open")
    bid_high  = _dec(record["bid_high"],  "bid_high")
    bid_low   = _dec(record["bid_low"],   "bid_low")
    bid_close = _dec(record["bid_close"], "bid_close")
    ask_open  = _dec(record["ask_open"],  "ask_open")
    ask_high  = _dec(record["ask_high"],  "ask_high")
    ask_low   = _dec(record["ask_low"],   "ask_low")
    ask_close = _dec(record["ask_close"], "ask_close")

    # OHLC invariants — bid side
    if not (bid_high >= bid_open and bid_high >= bid_close and bid_high >= bid_low):
        raise AcquisitionError("bid_high must be >= bid_open, bid_close, bid_low")
    if not (bid_low <= bid_open and bid_low <= bid_close):
        raise AcquisitionError("bid_low must be <= bid_open and bid_close")

    # OHLC invariants — ask side
    if not (ask_high >= ask_open and ask_high >= ask_close and ask_high >= ask_low):
        raise AcquisitionError("ask_high must be >= ask_open, ask_close, ask_low")
    if not (ask_low <= ask_open and ask_low <= ask_close):
        raise AcquisitionError("ask_low must be <= ask_open and ask_close")

    # ask >= bid for every corresponding field
    for bid_val, ask_val, label in (
        (bid_open,  ask_open,  "open"),
        (bid_high,  ask_high,  "high"),
        (bid_low,   ask_low,   "low"),
        (bid_close, ask_close, "close"),
    ):
        if ask_val < bid_val:
            raise AcquisitionError(
                f"ask_{label} ({ask_val}) must be >= bid_{label} ({bid_val})"
            )

    spread_min    = _dec(record["spread_min"],    "spread_min")
    spread_max    = _dec(record["spread_max"],    "spread_max")
    spread_median = _dec(record["spread_median"], "spread_median")
    spread_close  = _dec(record["spread_close"],  "spread_close")

    if spread_min < 0:
        raise AcquisitionError("spread_min must be non-negative")
    if spread_max < spread_min:
        raise AcquisitionError("spread_max must be >= spread_min")
    if not (spread_min <= spread_median <= spread_max):
        raise AcquisitionError("spread_median must be between spread_min and spread_max")

    tick_count = int(record["tick_count"])
    if tick_count < 1:
        raise AcquisitionError("tick_count must be >= 1")

    first_tick_ms = int(record["first_tick_ms"])
    last_tick_ms  = int(record["last_tick_ms"])
    if not (open_ms <= first_tick_ms <= last_tick_ms < close_ms):
        raise AcquisitionError(
            "first_tick_ms/last_tick_ms must be within [open_time_ms, close_time_ms)"
        )

    src_ids = record.get("source_package_ids", [])
    if isinstance(src_ids, str):
        try:
            src_ids = json.loads(src_ids)
        except json.JSONDecodeError as exc:
            raise AcquisitionError("source_package_ids is not valid JSON") from exc
    if not isinstance(src_ids, list) or not src_ids:
        raise AcquisitionError("source_package_ids must be a non-empty list")

    identity = str(record.get("candle_identity", ""))
    expected_identity = stable_candle_identity(symbol, timeframe, open_ms, close_ms)
    if identity != expected_identity:
        raise AcquisitionError(
            f"candle_identity mismatch: stored={identity!r} expected={expected_identity!r}"
        )

    schema_ver = str(record.get("schema_version", ""))
    if schema_ver != CANDLE_SCHEMA_VERSION:
        raise AcquisitionError(
            f"schema_version mismatch: {schema_ver!r} vs {CANDLE_SCHEMA_VERSION!r}"
        )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time_ms": open_ms,
        "close_time_ms": close_ms,
        "available_at_ms": avail_ms,
        "bid_open": bid_open,
        "bid_high": bid_high,
        "bid_low": bid_low,
        "bid_close": bid_close,
        "ask_open": ask_open,
        "ask_high": ask_high,
        "ask_low": ask_low,
        "ask_close": ask_close,
        "tick_count": tick_count,
        "spread_min": spread_min,
        "spread_max": spread_max,
        "spread_median": spread_median,
        "spread_close": spread_close,
        "first_tick_ms": first_tick_ms,
        "last_tick_ms": last_tick_ms,
        "source_package_ids": json.dumps(sorted(src_ids), separators=(",", ":")),
        "candle_identity": identity,
        "schema_version": schema_ver,
        "classification": CLASSIFICATION_LABEL,
    }


def _build_table(validated_records: list[dict]):
    """Build a PyArrow table from a list of validated candle dicts."""
    pa, _ = _arrow()
    schema = bidask_candle_schema()
    if not validated_records:
        return pa.table(
            {field.name: [] for field in schema},
            schema=schema,
        )
    cols: dict = {
        "symbol":           [r["symbol"] for r in validated_records],
        "timeframe":        [r["timeframe"] for r in validated_records],
        "open_time_ms":     [r["open_time_ms"] for r in validated_records],
        "close_time_ms":    [r["close_time_ms"] for r in validated_records],
        "available_at_ms":  [r["available_at_ms"] for r in validated_records],
        "bid_open":         [r["bid_open"] for r in validated_records],
        "bid_high":         [r["bid_high"] for r in validated_records],
        "bid_low":          [r["bid_low"] for r in validated_records],
        "bid_close":        [r["bid_close"] for r in validated_records],
        "ask_open":         [r["ask_open"] for r in validated_records],
        "ask_high":         [r["ask_high"] for r in validated_records],
        "ask_low":          [r["ask_low"] for r in validated_records],
        "ask_close":        [r["ask_close"] for r in validated_records],
        "tick_count":       [r["tick_count"] for r in validated_records],
        "spread_min":       [r["spread_min"] for r in validated_records],
        "spread_max":       [r["spread_max"] for r in validated_records],
        "spread_median":    [r["spread_median"] for r in validated_records],
        "spread_close":     [r["spread_close"] for r in validated_records],
        "first_tick_ms":    [r["first_tick_ms"] for r in validated_records],
        "last_tick_ms":     [r["last_tick_ms"] for r in validated_records],
        "source_package_ids": [r["source_package_ids"] for r in validated_records],
        "candle_identity":  [r["candle_identity"] for r in validated_records],
        "schema_version":   [r["schema_version"] for r in validated_records],
        "classification":   [r["classification"] for r in validated_records],
    }
    return pa.Table.from_pydict(cols, schema=schema)


def canonical_candle_hash(records: Iterable[Mapping]) -> str:
    """Compute a deterministic SHA-256 content hash over an ordered candle sequence."""
    digest = hashlib.sha256()
    for record in records:
        payload = json.dumps(
            {
                "symbol": str(record.get("symbol", "")),
                "timeframe": str(record.get("timeframe", "")),
                "open_time_ms": int(record["open_time_ms"]),
                "close_time_ms": int(record["close_time_ms"]),
                "available_at_ms": int(record["available_at_ms"]),
                "bid_open":  str(record.get("bid_open",  "")),
                "bid_high":  str(record.get("bid_high",  "")),
                "bid_low":   str(record.get("bid_low",   "")),
                "bid_close": str(record.get("bid_close", "")),
                "ask_open":  str(record.get("ask_open",  "")),
                "ask_high":  str(record.get("ask_high",  "")),
                "ask_low":   str(record.get("ask_low",   "")),
                "ask_close": str(record.get("ask_close", "")),
                "tick_count": int(record["tick_count"]),
                "candle_identity": str(record.get("candle_identity", "")),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        digest.update(payload)
        digest.update(b"\n")
    return digest.hexdigest()


def read_candle_records(path: Path) -> list[dict]:
    """Read back a Parquet candle partition as a list of dicts."""
    _pa, pq = _arrow()
    path = Path(path)
    try:
        table = pq.read_table(path)
    except Exception as exc:
        raise AcquisitionError(f"Candle Parquet partition is unreadable: {path.name}") from exc
    if table.schema != bidask_candle_schema():
        raise AcquisitionError(f"Candle Parquet schema mismatch: {path.name}")
    rows = []
    for item in table.to_pylist():
        rows.append({
            **item,
            "bid_open":      str(item["bid_open"]),
            "bid_high":      str(item["bid_high"]),
            "bid_low":       str(item["bid_low"]),
            "bid_close":     str(item["bid_close"]),
            "ask_open":      str(item["ask_open"]),
            "ask_high":      str(item["ask_high"]),
            "ask_low":       str(item["ask_low"]),
            "ask_close":     str(item["ask_close"]),
            "spread_min":    str(item["spread_min"]),
            "spread_max":    str(item["spread_max"]),
            "spread_median": str(item["spread_median"]),
            "spread_close":  str(item["spread_close"]),
        })
    return rows


@dataclass
class CandlePartitionSummary:
    """Summary of a written and verified candle partition."""
    partition_id: str
    relative_path: str
    timeframe: str
    sha256: str
    canonical_content_sha256: str
    record_count: int
    size_bytes: int
    first_open_ms: int
    last_open_ms: int
    schema_version: str
    complete: bool


class ParquetBidAskCandleStore:
    """Atomic, non-overwriting Parquet store for bid/ask candle partitions.

    Follows the same publication pattern as ParquetTickStore in columnar.py:
    - Write to a `.partial` file first.
    - fsync the partial.
    - Check disk reserve.
    - os.replace into final path.
    - Write completion marker atomically.
    - Raise on any existing final or partial path (refuse overwrite).
    """

    def __init__(
        self,
        root: Path,
        *,
        maximum_output_bytes: int,
        minimum_free_bytes: int = 0,
    ) -> None:
        self.root = validate_output_root(root, forbidden_roots=())
        self.maximum_output_bytes = int(maximum_output_bytes)
        self.minimum_free_bytes = int(minimum_free_bytes)
        if self.maximum_output_bytes <= 0 or self.minimum_free_bytes < 0:
            raise AcquisitionError("candle storage limits are invalid")
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def canonical_digest_of_stream(records: Iterable[Mapping]) -> str:
        """Hash a candle record stream with the canonical content hash.

        Consumes the iterator lazily so a second streaming aggregation pass
        can be verified without materialising the records in memory.
        """
        return canonical_candle_hash(records)

    def write(
        self,
        relative_path: str,
        records: Iterable[Mapping],
        *,
        partition_id: str,
        timeframe: str,
    ) -> CandlePartitionSummary:
        with FileLock(str(self.root / ".candle.lock"), timeout=60):
            return self._write_locked(
                relative_path,
                list(records),
                partition_id=partition_id,
                timeframe=timeframe,
            )

    def _write_locked(
        self,
        relative_path: str,
        records: list[Mapping],
        *,
        partition_id: str,
        timeframe: str,
    ) -> CandlePartitionSummary:
        final_path = self._safe_path(relative_path)
        marker_path = final_path.with_suffix(final_path.suffix + ".complete.json")
        partial_path = final_path.with_suffix(final_path.suffix + ".partial")

        if final_path.exists() or marker_path.exists():
            raise FileExistsError(
                f"Candle partition already exists (non-overwriting): {final_path.name}"
            )
        if partial_path.exists():
            raise AcquisitionError(
                f"Partial candle partition requires investigation: {partial_path.name}"
            )

        # Validate and normalise all records before writing
        validated = [_validate_record(r) for r in records]

        # Verify ordering
        open_times = [r["open_time_ms"] for r in validated]
        if open_times != sorted(open_times):
            raise AcquisitionError("Candle records must be in open_time_ms order")

        # Verify unique identities
        identities = [r["candle_identity"] for r in validated]
        if len(identities) != len(set(identities)):
            raise AcquisitionError("Candle records contain duplicate identities")

        content_hash = canonical_candle_hash(validated)
        final_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            _, pq = _arrow()
            pq.write_table(
                _build_table(validated),
                partial_path,
                compression="zstd",
                compression_level=9,
                use_dictionary=("symbol", "timeframe", "schema_version", "classification"),
                write_statistics=True,
                row_group_size=100_000,
            )
            with partial_path.open("r+b") as handle:
                os.fsync(handle.fileno())

            projected = output_size(self.root)
            free_after = shutil.disk_usage(self.root).free - partial_path.stat().st_size
            if projected > self.maximum_output_bytes:
                raise AcquisitionError("candle output budget would be exceeded")
            if free_after < self.minimum_free_bytes:
                raise AcquisitionError("disk safety reserve would be breached by candle output")

            os.replace(partial_path, final_path)

            summary = CandlePartitionSummary(
                partition_id=partition_id,
                relative_path=final_path.relative_to(self.root).as_posix(),
                timeframe=timeframe,
                sha256=file_sha256(final_path),
                canonical_content_sha256=content_hash,
                record_count=len(validated),
                size_bytes=final_path.stat().st_size,
                first_open_ms=validated[0]["open_time_ms"] if validated else 0,
                last_open_ms=validated[-1]["open_time_ms"] if validated else 0,
                schema_version=CANDLE_SCHEMA_VERSION,
                complete=True,
            )
            atomic_json(marker_path, asdict(summary))
            return summary

        except Exception:
            partial_path.unlink(missing_ok=True)
            if final_path.exists() and not marker_path.exists():
                final_path.unlink()
            raise

    def verify(self, relative_path: str) -> CandlePartitionSummary:
        """Re-read a completed partition and verify all invariants."""
        final_path = self._safe_path(relative_path)
        marker_path = final_path.with_suffix(final_path.suffix + ".complete.json")
        if not final_path.is_file() or not marker_path.is_file():
            raise AcquisitionError(f"Candle partition is incomplete: {final_path.name}")
        try:
            import json as _json
            raw = _json.loads(marker_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise AcquisitionError("Candle completion marker is unreadable") from exc

        # Physical hash check
        if file_sha256(final_path) != raw.get("sha256"):
            raise AcquisitionError(f"Candle partition SHA-256 mismatch: {final_path.name}")
        if final_path.stat().st_size != int(raw.get("size_bytes", -1)):
            raise AcquisitionError(f"Candle partition size mismatch: {final_path.name}")

        # Full read-back
        rows = read_candle_records(final_path)

        if len(rows) != int(raw.get("record_count", -1)):
            raise AcquisitionError("Candle partition row count mismatch")

        # Recompute canonical hash
        if canonical_candle_hash(rows) != raw.get("canonical_content_sha256"):
            raise AcquisitionError("Candle canonical content hash mismatch")

        # Validate every record and check ordering + unique identities
        validated = [_validate_record(r) for r in rows]
        open_times = [r["open_time_ms"] for r in validated]
        if open_times != sorted(open_times):
            raise AcquisitionError("Candle records are out of order in read-back")
        identities = [r["candle_identity"] for r in validated]
        if len(identities) != len(set(identities)):
            raise AcquisitionError("Duplicate candle identities in read-back")

        return CandlePartitionSummary(
            partition_id=str(raw["partition_id"]),
            relative_path=str(raw["relative_path"]),
            timeframe=str(raw["timeframe"]),
            sha256=str(raw["sha256"]),
            canonical_content_sha256=str(raw["canonical_content_sha256"]),
            record_count=int(raw["record_count"]),
            size_bytes=int(raw["size_bytes"]),
            first_open_ms=int(raw.get("first_open_ms", 0)),
            last_open_ms=int(raw.get("last_open_ms", 0)),
            schema_version=str(raw["schema_version"]),
            complete=bool(raw.get("complete")),
        )

    def _safe_path(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise AcquisitionError("candle partition path must be package-relative")
        path = (self.root / relative).resolve(strict=False)
        if not _inside(path, self.root.resolve(strict=False)):
            raise AcquisitionError("candle partition path escapes the output root")
        return path
