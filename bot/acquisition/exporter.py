from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from bot.data.candles import TIMEFRAMES, normalize_candles
from bot.validation.datasets import file_sha256
from bot.validation.models import canonical_data

from .gateway import ReadOnlyMT5Gateway
from .models import (
    AcquisitionError,
    ChunkSummary,
    CoverageReport,
    DiskEstimate,
    DXY_BASE_SYMBOLS,
    EXECUTABLE_SYMBOL,
    EXPORT_TOOL_VERSION,
    ExportConfig,
    ExportInspection,
    ExportStatus,
    SampleManifest,
    SymbolMapping,
)
from .storage import ChunkStore, atomic_json
from .preflight import AcquisitionPreflight
from .columnar import ParquetBarStore, ParquetTickStore
from .plan import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    DataInterval,
    append_access_record,
    calibration_blocks,
    chunk_ranges,
    classify_interval,
)


UTC = timezone.utc
XAU_TIMEFRAMES = ("M5", "M15", "H1", "H4", "D1", "W1")
DXY_TIMEFRAMES = ("M5", "H1")
TICK_GAP_SECONDS = 15 * 60


def _value(record: object, key: str, default: object = None) -> object:
    if isinstance(record, Mapping):
        return record.get(key, default)
    try:
        return record[key]  # type: ignore[index]
    except (IndexError, KeyError, TypeError, ValueError):
        return getattr(record, key, default)


def _rows(raw: object) -> tuple[object, ...]:
    if raw is None:
        return ()
    try:
        return tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise AcquisitionError("MT5 history response is not iterable") from exc


def _iso_from_milliseconds(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def normalize_ticks(
    raw: object,
    *,
    symbol: str,
    chunk_id: str,
) -> tuple[tuple[dict[str, object], ...], dict[str, int]]:
    if symbol != EXECUTABLE_SYMBOL:
        raise AcquisitionError("tick export is restricted to exact XAUUSDm")
    candidates: list[tuple[int, int, dict[str, object]]] = []
    crossed = zero = non_finite = 0
    for source_ordinal, item in enumerate(_rows(raw)):
        seconds = int(_value(item, "time", 0) or 0)
        milliseconds = int(_value(item, "time_msc", seconds * 1000) or seconds * 1000)
        bid = float(_value(item, "bid", 0) or 0)
        ask = float(_value(item, "ask", 0) or 0)
        last = float(_value(item, "last", 0) or 0)
        volume = float(_value(item, "volume", 0) or 0)
        volume_real = float(_value(item, "volume_real", 0) or 0)
        flags = int(_value(item, "flags", 0) or 0)
        if milliseconds <= 0:
            raise AcquisitionError("tick contains a malformed timestamp or non-finite value")
        if not all(math.isfinite(value) for value in (bid, ask, last, volume, volume_real)):
            non_finite += 1
            continue
        if bid <= 0 or ask <= 0:
            zero += 1
            continue
        if ask < bid:
            crossed += 1
            continue
        payload = {
            "symbol": symbol,
            "timestamp": _iso_from_milliseconds(milliseconds),
            "time": seconds,
            "time_msc": milliseconds,
            "bid": bid,
            "ask": ask,
            "last": last if last > 0 else None,
            "volume": volume,
            "volume_real": volume_real,
            "flags": flags,
            "source_chunk_id": chunk_id,
        }
        candidates.append((milliseconds, source_ordinal, payload))
    if crossed or zero or non_finite:
        raise AcquisitionError("tick sample contains crossed or zero/non-finite bid/ask values")
    candidates.sort(key=lambda item: (item[0], item[1]))

    duplicate_count = 0
    prior_core: tuple[object, ...] | None = None
    records: list[dict[str, object]] = []
    for ordinal, (_milliseconds, _source_ordinal, payload) in enumerate(candidates):
        core = (
            payload["time_msc"], payload["bid"], payload["ask"], payload["last"],
            payload["volume"], payload["volume_real"], payload["flags"],
        )
        duplicate_count += int(core == prior_core)
        prior_core = core
        identity_payload = json.dumps(core, separators=(",", ":"), ensure_ascii=True)
        payload["sequence_id"] = f"{chunk_id}:{ordinal:012d}"
        payload["row_identity"] = hashlib.sha256(
            f"{chunk_id}:{ordinal}:{identity_payload}".encode("utf-8")
        ).hexdigest()
        records.append(payload)

    gap_count = weekend_gap_count = max_gap_seconds = 0
    for previous, current in zip(records, records[1:]):
        delta_ms = int(current["time_msc"]) - int(previous["time_msc"])
        if delta_ms > TICK_GAP_SECONDS * 1000:
            max_gap_seconds = max(max_gap_seconds, delta_ms // 1000)
            before = datetime.fromtimestamp(int(previous["time_msc"]) / 1000, tz=UTC)
            after = datetime.fromtimestamp(int(current["time_msc"]) / 1000, tz=UTC)
            if before.weekday() == 4 and after.weekday() in {6, 0}:
                weekend_gap_count += 1
            else:
                gap_count += 1
    return tuple(records), {
        "duplicate_count": duplicate_count,
        "crossed_quote_count": crossed,
        "zero_quote_count": zero,
        "non_finite_quote_count": non_finite,
        "gap_count": gap_count,
        "weekend_gap_count": weekend_gap_count,
        "max_gap_seconds": max_gap_seconds,
    }


def normalize_rates(
    raw: object,
    *,
    symbol: str,
    timeframe: str,
    end_exclusive: datetime,
) -> tuple[dict[str, object], ...]:
    frame = normalize_candles(
        pd.DataFrame(raw),
        timeframe,
        final_candle_complete=True,
    )
    if frame.empty:
        return ()
    end = pd.Timestamp(end_exclusive)
    frame = frame[frame["available_at"] <= end].copy()
    records: list[dict[str, object]] = []
    for ordinal, row in frame.iterrows():
        records.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "open_time": row["open_time"].isoformat().replace("+00:00", "Z"),
            "available_at": row["available_at"].isoformat().replace("+00:00", "Z"),
            "timestamp": row["available_at"].isoformat().replace("+00:00", "Z"),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "tick_volume": None if pd.isna(row["tick_volume"]) else float(row["tick_volume"]),
            "spread": None if pd.isna(row["spread"]) else float(row["spread"]),
            "real_volume": None if pd.isna(row["real_volume"]) else float(row["real_volume"]),
            "sequence_id": f"{symbol}:{timeframe}:{len(records):012d}",
        })
    return tuple(records)


def month_ranges(start: datetime, end: datetime, *, months: int = 1) -> tuple[tuple[datetime, datetime], ...]:
    if months < 1:
        raise AcquisitionError("tick chunk months must be positive")
    ranges: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        boundary = cursor
        for _ in range(months):
            if boundary.month == 12:
                boundary = boundary.replace(year=boundary.year + 1, month=1, day=1)
            else:
                boundary = boundary.replace(month=boundary.month + 1, day=1)
        chunk_end = min(boundary, end)
        ranges.append((cursor, chunk_end))
        cursor = chunk_end
    return tuple(ranges)


def tick_ranges(config: ExportConfig) -> tuple[tuple[datetime, datetime], ...]:
    if config.tick_chunk_days is not None:
        return tuple((item.start, item.end) for item in chunk_ranges(config.start, config.end, days=config.tick_chunk_days))
    return month_ranges(config.start, config.end, months=config.tick_chunk_months)


def tick_partition_path(start: datetime, end: datetime, *, storage_format: str) -> tuple[str, str]:
    iso_year, iso_week, _weekday = start.isocalendar()
    chunk_id = f"xau-ticks-{start:%Y%m%dT%H%M%S}-{end:%Y%m%dT%H%M%S}"
    suffix = "parquet" if storage_format == "parquet-zstd" else "jsonl.gz"
    relative = (
        f"ticks/{EXECUTABLE_SYMBOL}/year={start:%Y}/month={start:%m}/"
        f"iso_week={iso_year}-W{iso_week:02d}/{chunk_id}.{suffix}"
    )
    return chunk_id, relative


def _mapping_from(raw: Mapping[str, object], base: str) -> SymbolMapping:
    return SymbolMapping(
        base_symbol=base,
        broker_symbol=str(raw.get("name") or ""),
        description=str(raw.get("description") or ""),
        currency_base=str(raw.get("currency_base") or ""),
        currency_profit=str(raw.get("currency_profit") or ""),
        digits=int(raw.get("digits") or 0),
        point=float(raw.get("point") or 0),
    )


class EmpiricalExporter:
    def __init__(self, gateway: ReadOnlyMT5Gateway, config: ExportConfig) -> None:
        self.gateway = gateway
        self.config = config
        self.store = ChunkStore(config.output_root, maximum_output_bytes=config.maximum_output_bytes)
        self.parquet_store = ParquetTickStore(
            config.output_root,
            maximum_output_bytes=config.maximum_output_bytes,
            minimum_free_bytes=config.minimum_free_bytes,
        )
        self.parquet_bar_store = ParquetBarStore(
            config.output_root,
            maximum_output_bytes=config.maximum_output_bytes,
            minimum_free_bytes=config.minimum_free_bytes,
        )

    def inspect(self) -> ExportInspection:
        mappings: dict[str, SymbolMapping] = {}
        missing: list[str] = []
        ambiguous: list[str] = []
        xau = self.gateway.symbol_info(EXECUTABLE_SYMBOL)
        if xau is None or xau.get("name") != EXECUTABLE_SYMBOL:
            missing.append(EXECUTABLE_SYMBOL)
        else:
            mappings[EXECUTABLE_SYMBOL] = _mapping_from(xau, EXECUTABLE_SYMBOL)

        for base in DXY_BASE_SYMBOLS:
            expected_base, expected_profit = base[:3], base[3:]
            candidates = [
                item for item in self.gateway.discover_symbols(base)
                if str(item.get("name") or "").startswith(base)
                and str(item.get("currency_base") or "").upper() == expected_base
                and str(item.get("currency_profit") or "").upper() == expected_profit
            ]
            exact = [item for item in candidates if item.get("name") == base]
            selected = exact if exact else candidates
            if len(selected) == 1:
                mappings[base] = _mapping_from(selected[0], base)
            elif selected:
                ambiguous.append(base)
            else:
                missing.append(base)
        status = (
            ExportStatus.MAPPING_AMBIGUOUS if ambiguous
            else ExportStatus.SYMBOL_MISSING if missing
            else ExportStatus.TOOL_VERIFIED
        )
        return ExportInspection(status, dict(sorted(mappings.items())), tuple(sorted(missing)), tuple(sorted(ambiguous)))

    def write_sample(self, start: datetime, end: datetime) -> SampleManifest:
        return AcquisitionPreflight(self.gateway, self.config, self.store).write_sample(start, end)

    def load_sample(self, start: datetime, end: datetime) -> tuple[SampleManifest, tuple[dict[str, object], ...]]:
        return AcquisitionPreflight(self.gateway, self.config, self.store).load_sample(start, end)

    def discover_coverage(self) -> CoverageReport:
        return AcquisitionPreflight(self.gateway, self.config, self.store).discover_coverage()

    def estimate(self, sample: SampleManifest, coverage: CoverageReport) -> DiskEstimate:
        return AcquisitionPreflight(self.gateway, self.config, self.store).estimate(sample, coverage)

    def export_ticks(self, *, resume: bool) -> tuple[ChunkSummary, ...]:
        summaries: list[ChunkSummary] = []
        for start, end in tick_ranges(self.config):
            summaries.extend(self._export_tick_interval(start, end, resume=resume))
        return tuple(summaries)

    def export_calibration_ticks(self, *, resume: bool) -> tuple[ChunkSummary, ...]:
        if self.config.start != DEVELOPMENT_START or self.config.end != DEVELOPMENT_END:
            raise AcquisitionError("calibration export requires the exact development interval")
        if self.config.bulk_format != "parquet-zstd" or self.config.tick_chunk_days != 7:
            raise AcquisitionError("calibration export requires weekly Parquet/Zstandard storage")
        summaries: list[ChunkSummary] = []
        for interval in calibration_blocks():
            summaries.extend(self._export_tick_interval(interval.start, interval.end, resume=resume))
        return tuple(summaries)

    def _export_tick_interval(self, start: datetime, end: datetime, *, resume: bool) -> tuple[ChunkSummary, ...]:
        chunk_id, relative = tick_partition_path(start, end, storage_format=self.config.bulk_format)
        store = self.parquet_store if self.config.bulk_format == "parquet-zstd" else self.store
        final_path = self.config.output_root / relative
        marker_path = final_path.with_suffix(final_path.suffix + ".complete.json")
        if resume and final_path.exists() and marker_path.exists():
            return (store.verify(relative),)
        request_end = end - timedelta(milliseconds=1)
        raw = self.gateway.copy_ticks_range(EXECUTABLE_SYMBOL, start, request_end)
        records, diagnostics = normalize_ticks(
            raw,
            symbol=EXECUTABLE_SYMBOL,
            chunk_id=chunk_id,
        )
        append_access_record(
            self.config.output_root / "manifests" / "data_access_log.json",
            {
                "access_id": f"tick-read-{chunk_id}", "start": start, "end_exclusive": end,
                "classification": classify_interval(DataInterval(start, end)),
                "purpose": "read-only-tick-acquisition", "strategy_evaluated": False,
                "row_count": len(records),
            },
        )
        if len(records) > self.config.maximum_rows_per_tick_chunk:
            duration = end - start
            if duration <= timedelta(days=1):
                raise AcquisitionError("one-day tick response exceeds the configured row safety limit")
            midpoint = start + duration / 2
            return (
                *self._export_tick_interval(start, midpoint, resume=resume),
                *self._export_tick_interval(midpoint, end, resume=resume),
            )
        if self.config.bulk_format == "parquet-zstd":
            return (
                self.parquet_store.write(
                    relative,
                    records,
                    chunk_id=chunk_id,
                    requested_start=start,
                    requested_end=end,
                    diagnostics=diagnostics,
                    resume=resume,
                ),
            )
        if not records:
            empty_path = self.config.output_root / "manifests" / "empty_tick_chunks" / f"{chunk_id}.json"
            atomic_json(
                empty_path,
                {"tool_version": EXPORT_TOOL_VERSION, "chunk_id": chunk_id, "start": start, "end": end,
                 "reason": "EMPTY_SERVER_RESPONSE"},
                refuse_overwrite=not resume,
            )
            return ()
        actual_start = datetime.fromisoformat(str(records[0]["timestamp"]).replace("Z", "+00:00"))
        actual_end = datetime.fromisoformat(str(records[-1]["timestamp"]).replace("Z", "+00:00"))
        return (
            self.store.write(
                relative,
                records,
                chunk_id=chunk_id,
                start=actual_start,
                end=actual_end,
                diagnostics=diagnostics,
                resume=resume,
            ),
        )

    def export_bars(
        self,
        mappings: Mapping[str, SymbolMapping],
        *,
        resume: bool,
    ) -> tuple[ChunkSummary, ...]:
        requested: list[tuple[str, str]] = [(EXECUTABLE_SYMBOL, timeframe) for timeframe in XAU_TIMEFRAMES]
        requested.extend((mappings[base].broker_symbol, timeframe) for base in DXY_BASE_SYMBOLS for timeframe in DXY_TIMEFRAMES)
        summaries: list[ChunkSummary] = []
        for symbol, timeframe in requested:
            chunk_id = f"bars-{symbol}-{timeframe}-{self.config.start:%Y%m%d}-{self.config.end:%Y%m%d}"
            suffix = "parquet" if self.config.bulk_format == "parquet-zstd" else "jsonl.gz"
            relative = f"bars/{symbol}/{timeframe}/{chunk_id}.{suffix}"
            final_path = self.config.output_root / relative
            marker_path = final_path.with_suffix(final_path.suffix + ".complete.json")
            if resume and final_path.exists() and marker_path.exists():
                store = self.parquet_bar_store if self.config.bulk_format == "parquet-zstd" else self.store
                summaries.append(store.verify(relative))
                continue
            spec = TIMEFRAMES[timeframe]
            raw = self.gateway.copy_rates_range(
                symbol,
                self.gateway.timeframe_value(spec.mt5_attribute),
                self.config.start,
                self.config.end,
            )
            records = normalize_rates(raw, symbol=symbol, timeframe=timeframe, end_exclusive=self.config.end)
            append_access_record(
                self.config.output_root / "manifests" / "data_access_log.json",
                {
                    "access_id": f"bar-read-{chunk_id}", "start": self.config.start,
                    "end_exclusive": self.config.end,
                    "classification": classify_interval(DataInterval(self.config.start, self.config.end)),
                    "purpose": "read-only-analysis-bar-acquisition", "strategy_evaluated": False,
                    "row_count": len(records),
                },
            )
            if not records:
                continue
            if self.config.bulk_format == "parquet-zstd":
                summaries.append(self.parquet_bar_store.write(
                    relative,
                    records,
                    chunk_id=chunk_id,
                    requested_start=self.config.start,
                    requested_end=self.config.end,
                    resume=resume,
                ))
                continue
            summaries.append(self.store.write(
                relative,
                records,
                chunk_id=chunk_id,
                start=datetime.fromisoformat(str(records[0]["available_at"]).replace("Z", "+00:00")),
                end=datetime.fromisoformat(str(records[-1]["available_at"]).replace("Z", "+00:00")),
                resume=resume,
            ))
        return tuple(summaries)

    def export_safe_metadata(self, *, exported_at: datetime, resume: bool) -> Path:
        path = self.config.output_root / "metadata" / "XAUUSDm.current-symbol-snapshot.json"
        if resume and path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise AcquisitionError("existing metadata snapshot is malformed") from exc
            if existing.get("symbol") != EXECUTABLE_SYMBOL:
                raise AcquisitionError("existing metadata snapshot has the wrong symbol")
            return path
        atomic_json(
            path,
            {
                **asdict(self.gateway.safe_metadata(EXECUTABLE_SYMBOL, exported_at)),
                "commission": {"status": "MISSING", "reason": "commission evidence is outside this authorization"},
                "historical_slippage": {"status": "MISSING", "reason": "quote history does not prove execution slippage"},
                "rollover_timezone": {"status": "MISSING", "reason": "symbol metadata does not establish timezone"},
                "effective_from": exported_at,
                "effective_to": None,
                "tool_version": EXPORT_TOOL_VERSION,
            },
            refuse_overwrite=not resume,
        )
        return path

    def write_export_manifest(
        self,
        *,
        inspection: ExportInspection,
        chunks: Iterable[ChunkSummary],
        metadata_path: Path | None,
        status: ExportStatus,
        git_commit: str,
        cross_checks: Mapping[str, object] | None = None,
    ) -> Path:
        path = self.config.output_root / "manifests" / "export_manifest.json"
        value = {
            "schema_version": 1,
            "tool_version": EXPORT_TOOL_VERSION,
            "git_commit": git_commit,
            "configuration": {
                "start": self.config.start,
                "end_exclusive": self.config.end,
                "maximum_output_bytes": self.config.maximum_output_bytes,
            },
            "configuration_fingerprint": hashlib.sha256(
                json.dumps(
                    canonical_data({
                        "start": self.config.start,
                        "end_exclusive": self.config.end,
                        "maximum_output_bytes": self.config.maximum_output_bytes,
                        "tick_chunk_months": self.config.tick_chunk_months,
                        "tick_chunk_days": self.config.tick_chunk_days,
                        "bulk_format": self.config.bulk_format,
                        "sample_minutes": self.config.sample_minutes,
                    }),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "status": status,
            "symbol_mappings": inspection.mappings,
            "missing_symbols": inspection.missing_symbols,
            "ambiguous_symbols": inspection.ambiguous_symbols,
            "chunks": tuple(chunks),
            "cross_checks": dict(cross_checks or {}),
            "metadata": None if metadata_path is None else metadata_path.relative_to(self.config.output_root).as_posix(),
            "outstanding_inputs": (
                "historical_usd_news",
                "observed_historical_slippage",
                "commission_schedule",
                "rollover_timezone",
                "historically_effective_metadata_segments",
            ),
            "raw_data_outside_git": True,
            "account_data_collected": False,
            "trade_data_collected": False,
        }
        atomic_json(path, value)
        return path


def compare_tick_derived_bars(
    ticks: Iterable[Mapping[str, object]],
    native_bars: Iterable[Mapping[str, object]],
    *,
    timeframe: str,
    price_tolerance: float,
) -> dict[str, object]:
    """Compare bounded bid ticks with native MT5 bars without mutating either source."""
    if timeframe not in TIMEFRAMES or price_tolerance < 0:
        raise AcquisitionError("bar comparison arguments are invalid")
    tick_rows = tuple(ticks)
    native_rows = tuple(native_bars)
    if not tick_rows or not native_rows:
        return {"compared_bars": 0, "discrepancy_count": 0, "status": "INSUFFICIENT_OVERLAP"}
    tick_frame = pd.DataFrame({
        "timestamp": pd.to_datetime([row["timestamp"] for row in tick_rows], utc=True),
        "bid": [float(row["bid"]) for row in tick_rows],
    }).set_index("timestamp")
    derived = tick_frame["bid"].resample(TIMEFRAMES[timeframe].pandas_frequency).ohlc().dropna()
    native = {
        pd.Timestamp(row["open_time"]): row
        for row in native_rows
    }
    compared = discrepancies = 0
    fields = ("open", "high", "low", "close")
    for timestamp, row in derived.iterrows():
        candidate = native.get(timestamp)
        if candidate is None:
            continue
        compared += 1
        discrepancies += int(any(
            abs(float(row[field]) - float(candidate[field])) > price_tolerance
            for field in fields
        ))
    return {
        "compared_bars": compared,
        "discrepancy_count": discrepancies,
        "status": "COMPARED" if compared else "INSUFFICIENT_OVERLAP",
        "feed_side": "BID_TICKS_VS_NATIVE_MT5_BARS",
    }
