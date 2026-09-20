"""Bounded sample evidence and resource estimates; no complete export path."""
from __future__ import annotations

import gzip
import json
import math
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.data.candles import TIMEFRAMES
from .gateway import ReadOnlyMT5Gateway
from .models import (AcquisitionError, CoverageReport, DiskEstimate, EXECUTABLE_SYMBOL,
                     EXPORT_TOOL_VERSION, ExportConfig, SampleManifest, utc_datetime)
from .storage import ChunkStore, atomic_json, output_size
from .plan import DataInterval, append_access_record, classify_interval

UTC = timezone.utc
COVERAGE_PROBE_DAYS = 90
GIB = 1024**3


class AcquisitionPreflight:
    def __init__(self, gateway: ReadOnlyMT5Gateway, config: ExportConfig, store: ChunkStore) -> None:
        self.gateway = gateway
        self.config = config
        self.store = store

    @staticmethod
    def _sample_id(start: datetime, end: datetime) -> str:
        return f"sample-{start:%Y%m%dT%H%M%S}-{end:%Y%m%dT%H%M%S}"

    def _sample_paths(self, start: datetime, end: datetime) -> tuple[str, Path]:
        sample_id = self._sample_id(start, end)
        relative = f"samples/{EXECUTABLE_SYMBOL}/{sample_id}.jsonl.gz"
        manifest = self.config.output_root / "samples" / EXECUTABLE_SYMBOL / f"{sample_id}.manifest.json"
        return relative, manifest

    def write_sample(self, start: datetime, end: datetime) -> SampleManifest:
        start = utc_datetime(start, "sample start")
        end = utc_datetime(end, "sample end")
        if end <= start or (end - start) > timedelta(hours=1):
            raise AcquisitionError("sample interval must be increasing and no longer than one hour")
        relative, manifest_path = self._sample_paths(start, end)
        final_path = self.config.output_root / relative
        marker_path = final_path.with_suffix(final_path.suffix + ".complete.json")
        partial_path = final_path.with_suffix(final_path.suffix + ".partial")
        if any(path.exists() for path in (final_path, marker_path, partial_path, manifest_path)):
            raise FileExistsError("sample destination already exists; verify it or clean it deliberately")

        acquired_at = time.perf_counter()
        from .exporter import normalize_ticks

        records, diagnostics = normalize_ticks(
            self.gateway.copy_ticks_range(EXECUTABLE_SYMBOL, start, end - timedelta(microseconds=1)),
            symbol=EXECUTABLE_SYMBOL,
            chunk_id=self._sample_id(start, end),
        )
        acquisition_elapsed = max(time.perf_counter() - acquired_at, 1e-9)
        append_access_record(
            self.config.output_root / "manifests" / "data_access_log.json",
            {
                "access_id": f"sample-read-{self._sample_id(start, end)}", "start": start,
                "end_exclusive": end, "classification": classify_interval(DataInterval(start, end)),
                "purpose": "bounded-acquisition-integrity-sample", "strategy_evaluated": False,
                "row_count": len(records),
            },
        )
        if not records:
            raise AcquisitionError("bounded sample returned no history")
        returned_start = datetime.fromisoformat(str(records[0]["timestamp"]).replace("Z", "+00:00"))
        returned_end = datetime.fromisoformat(str(records[-1]["timestamp"]).replace("Z", "+00:00"))
        if returned_start < start or returned_end >= end:
            raise AcquisitionError("bounded sample returned records outside the requested interval")

        written_at = time.perf_counter()
        summary = self.store.write(
            relative,
            records,
            chunk_id=self._sample_id(start, end),
            start=returned_start,
            end=returned_end,
            diagnostics=diagnostics,
        )
        write_elapsed = max(time.perf_counter() - written_at, 1e-9)
        verified = self.store.verify(relative)
        if verified != summary:
            raise AcquisitionError("sample verification result is inconsistent")
        manifest = SampleManifest(
            schema_version=1,
            exporter_version=EXPORT_TOOL_VERSION,
            sample_id=summary.chunk_id,
            symbol=EXECUTABLE_SYMBOL,
            requested_start=start,
            requested_end=end,
            returned_start=returned_start,
            returned_end=returned_end,
            row_count=summary.record_count,
            compressed_bytes=summary.size_bytes,
            sha256=summary.sha256,
            relative_path=summary.relative_path,
            completion_marker=marker_path.relative_to(self.config.output_root).as_posix(),
            duplicate_count=summary.duplicate_count,
            crossed_quote_count=summary.crossed_quote_count,
            zero_quote_count=summary.zero_quote_count,
            non_finite_quote_count=int(diagnostics.get("non_finite_quote_count", 0)),
            gap_summary={
                "unexplained_gap_count": summary.gap_count,
                "weekend_gap_count": int(diagnostics.get("weekend_gap_count", 0)),
                "maximum_gap_seconds": int(diagnostics.get("max_gap_seconds", 0)),
            },
            acquisition_elapsed_seconds=acquisition_elapsed,
            write_elapsed_seconds=write_elapsed,
            completion_status="COMPLETE",
        )
        atomic_json(manifest_path, asdict(manifest))
        return manifest

    def load_sample(self, start: datetime, end: datetime) -> tuple[SampleManifest, tuple[dict[str, object], ...]]:
        start = utc_datetime(start, "sample start")
        end = utc_datetime(end, "sample end")
        relative, manifest_path = self._sample_paths(start, end)
        if not manifest_path.is_file():
            raise AcquisitionError("completed sample manifest is missing")
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = SampleManifest(
                schema_version=int(raw["schema_version"]),
                exporter_version=str(raw["exporter_version"]),
                sample_id=str(raw["sample_id"]),
                symbol=str(raw["symbol"]),
                requested_start=datetime.fromisoformat(str(raw["requested_start"]).replace("Z", "+00:00")),
                requested_end=datetime.fromisoformat(str(raw["requested_end"]).replace("Z", "+00:00")),
                returned_start=datetime.fromisoformat(str(raw["returned_start"]).replace("Z", "+00:00")),
                returned_end=datetime.fromisoformat(str(raw["returned_end"]).replace("Z", "+00:00")),
                row_count=int(raw["row_count"]),
                compressed_bytes=int(raw["compressed_bytes"]),
                sha256=str(raw["sha256"]),
                relative_path=str(raw["relative_path"]),
                completion_marker=str(raw["completion_marker"]),
                duplicate_count=int(raw["duplicate_count"]),
                crossed_quote_count=int(raw["crossed_quote_count"]),
                zero_quote_count=int(raw["zero_quote_count"]),
                non_finite_quote_count=int(raw["non_finite_quote_count"]),
                gap_summary=dict(raw["gap_summary"]),
                acquisition_elapsed_seconds=float(raw["acquisition_elapsed_seconds"]),
                write_elapsed_seconds=float(raw["write_elapsed_seconds"]),
                completion_status=str(raw["completion_status"]),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AcquisitionError("sample manifest is malformed") from exc
        summary = self.store.verify(relative)
        expected_marker = Path(relative).with_suffix(Path(relative).suffix + ".complete.json").as_posix()
        if (
            manifest.schema_version != 1
            or manifest.exporter_version != EXPORT_TOOL_VERSION
            or manifest.symbol != EXECUTABLE_SYMBOL
            or manifest.completion_status != "COMPLETE"
            or manifest.relative_path != relative
            or manifest.completion_marker != expected_marker
            or manifest.sha256 != summary.sha256
            or manifest.compressed_bytes != summary.size_bytes
            or manifest.row_count != summary.record_count
            or manifest.requested_start != start
            or manifest.requested_end != end
            or manifest.sample_id != summary.chunk_id
            or manifest.returned_start != summary.start
            or manifest.returned_end != summary.end
            or manifest.duplicate_count != summary.duplicate_count
        ):
            raise AcquisitionError("sample manifest does not match its completed stream")
        records: list[dict[str, object]] = []
        with gzip.open(self.config.output_root / relative, "rt", encoding="utf-8") as handle:
            for line in handle:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise AcquisitionError("sample stream record is malformed")
                records.append(value)
        from .exporter import normalize_ticks

        normalized, diagnostics = normalize_ticks(records, symbol=EXECUTABLE_SYMBOL, chunk_id=manifest.sample_id)
        if tuple(records) != normalized or diagnostics["duplicate_count"] != manifest.duplicate_count:
            raise AcquisitionError("sample stream violates its normalized schema")
        return manifest, tuple(records)

    def discover_coverage(self) -> CoverageReport:
        from .exporter import _rows, _value

        timestamps: set[datetime] = set()
        probe_count = empty_count = 0
        maximum_span = 0
        cursor = self.config.start
        timeframe = self.gateway.timeframe_value(TIMEFRAMES["D1"].mt5_attribute)
        while cursor < self.config.end:
            probe_end = min(cursor + timedelta(days=COVERAGE_PROBE_DAYS), self.config.end)
            maximum_span = max(maximum_span, int((probe_end - cursor).total_seconds()))
            probe_count += 1
            response = self.gateway.copy_rates_range(EXECUTABLE_SYMBOL, timeframe, cursor, probe_end - timedelta(microseconds=1))
            if response is None:
                raise AcquisitionError("coverage query failed; unavailable history cannot be estimated")
            rows = _rows(response)
            if not rows:
                empty_count += 1
            for row in rows:
                seconds = int(_value(row, "time", 0) or 0)
                if seconds <= 0:
                    raise AcquisitionError("coverage probe returned a malformed timestamp")
                timestamp = datetime.fromtimestamp(seconds, tz=UTC)
                if not cursor <= timestamp < probe_end:
                    raise AcquisitionError("coverage response exceeds its bounded query")
                timestamps.add(timestamp)
            cursor = probe_end
        ordered = sorted(timestamps)
        append_access_record(
            self.config.output_root / "manifests" / "data_access_log.json",
            {
                "access_id": f"coverage-probe-{self.config.start:%Y%m%d}-{self.config.end:%Y%m%d}",
                "start": self.config.start, "end_exclusive": self.config.end,
                "classification": classify_interval(DataInterval(self.config.start, self.config.end)),
                "purpose": "bounded-D1-open-time-coverage-proxy", "strategy_evaluated": False,
                "row_count": len(ordered), "probe_count": probe_count,
            },
        )
        return CoverageReport(
            requested_start=self.config.start,
            requested_end=self.config.end,
            earliest_available=ordered[0] if ordered else None,
            latest_available=ordered[-1] if ordered else None,
            active_days=len({item.date() for item in ordered}),
            probe_count=probe_count,
            empty_probe_count=empty_count,
            maximum_probe_span_seconds=maximum_span,
        )

    def estimate(self, sample: SampleManifest, coverage: CoverageReport) -> DiskEstimate:
        sample_seconds = (sample.requested_end - sample.requested_start).total_seconds()
        if sample.row_count <= 0 or sample_seconds <= 0 or sample.compressed_bytes <= 0:
            raise AcquisitionError("completed bounded sample is required before estimating")
        if coverage.requested_start != self.config.start or coverage.requested_end != self.config.end:
            raise AcquisitionError("coverage interval does not match estimate configuration")
        calendar_seconds = (coverage.requested_end - coverage.requested_start).total_seconds()
        calendar_days = calendar_seconds / 86400
        rows_per_second = sample.row_count / sample_seconds
        rows_per_active_hour = rows_per_second * 3600
        rows_per_active_day = rows_per_second * 86400
        projected_rows = math.ceil(rows_per_active_day * coverage.active_days)
        bytes_per_row = sample.compressed_bytes / sample.row_count
        projected_bytes = math.ceil(projected_rows * bytes_per_row)
        estimated_low = math.floor(projected_bytes * 0.75)
        estimated_high = math.ceil(projected_bytes * 1.50)
        sampling_throughput = sample.row_count / sample.acquisition_elapsed_seconds
        export_throughput = sample.compressed_bytes / sample.write_elapsed_seconds
        duration = (
            projected_rows / sampling_throughput + projected_bytes / export_throughput
            if projected_rows else 0.0
        )
        free = self.store.free_bytes()
        existing = output_size(self.config.output_root)
        safety_margin = max(GIB, math.ceil(estimated_high * 0.25))
        safe = bool(
            coverage.active_days
            and not coverage.empty_probe_count
            and sample.gap_summary.get("unexplained_gap_count", 0) == 0
            and existing + estimated_high <= self.config.maximum_output_bytes
            and free >= estimated_high + safety_margin
        )
        bytes_per_month = rows_per_active_day * 31 * bytes_per_row
        recommended_chunk = "P1M" if bytes_per_month <= min(2 * GIB, max(free - safety_margin, 0) / 4) else "P7D"
        uncertainty = "HIGH_SINGLE_WINDOW_SAMPLE"
        if coverage.empty_probe_count:
            uncertainty += "_WITH_EMPTY_COVERAGE_PROBES"
        return DiskEstimate(
            requested_start=coverage.requested_start,
            requested_end=coverage.requested_end,
            coverage_earliest=coverage.earliest_available,
            coverage_latest=coverage.latest_available,
            coverage_basis=coverage.basis,
            coverage_probe_count=coverage.probe_count,
            coverage_empty_probe_count=coverage.empty_probe_count,
            coverage_active_days=coverage.active_days,
            calendar_days=calendar_days,
            sample_rows=sample.row_count,
            sample_bytes=sample.compressed_bytes,
            sample_duration_seconds=sample_seconds,
            rows_per_active_hour=rows_per_active_hour,
            rows_per_active_day=rows_per_active_day,
            rows_per_active_month=rows_per_active_day * 30,
            compressed_bytes_per_row=bytes_per_row,
            estimated_rows=projected_rows,
            estimated_bytes=projected_bytes,
            estimated_bytes_low=estimated_low,
            estimated_bytes_high=estimated_high,
            sampling_throughput_rows_per_second=sampling_throughput,
            export_throughput_bytes_per_second=export_throughput,
            estimated_export_duration_seconds=duration,
            free_bytes=free,
            budget_bytes=self.config.maximum_output_bytes,
            existing_output_bytes=existing,
            required_safety_margin_bytes=safety_margin,
            recommended_chunk=recommended_chunk,
            uncertainty=uncertainty,
            safe_to_continue=safe,
        )
