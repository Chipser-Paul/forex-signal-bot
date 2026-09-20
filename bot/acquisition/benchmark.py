from __future__ import annotations

import gzip
import json
import math
import shutil
import statistics
import time
import tracemalloc
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from bot.validation.models import canonical_data

from .columnar import ParquetTickStore, canonical_tick_hash, read_tick_records
from .exporter import normalize_ticks
from .gateway import ReadOnlyMT5Gateway
from .coverage_probe import classify_response, response_shape
from .journal import BenchmarkJournal
from .models import AcquisitionError, EXECUTABLE_SYMBOL
from .plan import (
    BENCHMARK_END,
    BENCHMARK_START,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    PROPOSED_HOLDOUT_END,
    PROPOSED_HOLDOUT_START,
    append_access_record,
    calibration_blocks,
    classify_interval,
    DataInterval,
    require_development_access,
)
from .storage import ChunkStore, atomic_json, file_sha256, output_size


UTC = timezone.utc
BENCHMARK_MAX_BYTES = 1024**3
BENCHMARK_SCHEMA_VERSION = "phase8b.benchmark-stage.v2"
BENCHMARK_INTERVALS = {
    "hour": (
        datetime(2024, 8, 5, 12, tzinfo=UTC),
        datetime(2024, 8, 5, 13, tzinfo=UTC),
    ),
    "day": (BENCHMARK_START, BENCHMARK_START + timedelta(days=1)),
    "week": (BENCHMARK_START, BENCHMARK_END),
}
STAGE_PREDECESSOR = {"hour": None, "day": "hour", "week": "day"}


def _free_bytes(path: Path) -> int:
    usage = shutil.disk_usage(path)
    return int(usage.free if hasattr(usage, "free") else usage[2])


@dataclass(frozen=True)
class BenchmarkSample:
    run_id: str
    stage: str
    requested_start: datetime
    requested_end: datetime
    returned_start: datetime
    returned_end: datetime
    rows: int
    request_seconds: float
    normalization_seconds: float
    logical_json_bytes: int
    gzip_bytes: int
    parquet_bytes: int
    gzip_write_seconds: float
    parquet_write_seconds: float
    gzip_verify_seconds: float
    parquet_verify_seconds: float
    gzip_readback_seconds: float
    parquet_readback_seconds: float
    hash_seconds: float
    peak_python_bytes: int
    duplicate_count: int
    crossed_quote_count: int
    zero_quote_count: int
    non_finite_quote_count: int
    gap_count: int
    weekend_gap_count: int
    maximum_gap_seconds: int
    ordering_violations: int
    spread_price_minimum: float
    spread_price_median: float
    spread_price_p95: float
    spread_price_maximum: float
    spread_points_minimum: float
    spread_points_median: float
    spread_points_p95: float
    spread_points_maximum: float
    first_bid: float
    first_ask: float
    last_bid: float
    last_ask: float
    gzip_sha256: str
    parquet_sha256: str
    canonical_content_sha256: str
    readback_equal: bool
    schema_version: str


def _elapsed(call: Callable[[], object]) -> tuple[object, float]:
    started = time.perf_counter()
    value = call()
    return value, max(time.perf_counter() - started, 1e-9)


def _logical_bytes(records: tuple[Mapping[str, object], ...]) -> int:
    return sum(
        len(json.dumps(canonical_data(item), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")) + 1
        for item in records
    )


def _gzip_records(path: Path) -> tuple[dict[str, object], ...]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return tuple(json.loads(line) for line in handle)
    except (OSError, EOFError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError("benchmark gzip read-back failed") from exc


def _percentile(values: tuple[float, ...], percentile: float) -> float:
    if not values:
        raise AcquisitionError("benchmark spread distribution requires quotes")
    ordered = sorted(values)
    index = min(int(math.ceil((len(ordered) - 1) * percentile)), len(ordered) - 1)
    return float(ordered[index])


def _spread_distribution(records: tuple[Mapping[str, object], ...], point: float) -> dict[str, float]:
    if not math.isfinite(point) or point <= 0:
        raise AcquisitionError("benchmark symbol point is invalid")
    spreads = tuple(float(item["ask"]) - float(item["bid"]) for item in records)
    if not spreads or any(not math.isfinite(item) or item < 0 for item in spreads):
        raise AcquisitionError("benchmark spread observations are invalid")
    points = tuple(item / point for item in spreads)
    return {
        "spread_price_minimum": min(spreads),
        "spread_price_median": float(statistics.median(spreads)),
        "spread_price_p95": _percentile(spreads, 0.95),
        "spread_price_maximum": max(spreads),
        "spread_points_minimum": min(points),
        "spread_points_median": float(statistics.median(points)),
        "spread_points_p95": _percentile(points, 0.95),
        "spread_points_maximum": max(points),
    }


def benchmark_root(output_root: Path) -> Path:
    return Path(output_root) / "benchmarks" / "development-20240805-20240812"


def verified_stage_runs(output_root: Path, stage: str) -> tuple[Path, ...]:
    if stage not in BENCHMARK_INTERVALS:
        raise AcquisitionError("benchmark stage is invalid")
    stage_root = benchmark_root(output_root) / "runs" / stage
    if not stage_root.exists():
        return ()
    verified: list[Path] = []
    for run_dir in sorted(path for path in stage_root.iterdir() if path.is_dir()):
        try:
            verify_stage_run(run_dir)
        except (AcquisitionError, OSError, ValueError, json.JSONDecodeError):
            continue
        verified.append(run_dir)
    return tuple(verified)


def verify_stage_run(run_dir: Path) -> dict[str, object]:
    run_dir = Path(run_dir)
    try:
        manifest = json.loads((run_dir / "stage.complete.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise AcquisitionError("benchmark stage completion is unavailable") from exc
    if (
        manifest.get("schema_version") != BENCHMARK_SCHEMA_VERSION
        or manifest.get("status") != "VERIFIED"
        or manifest.get("run_id") != run_dir.name
    ):
        raise AcquisitionError("benchmark stage completion is incompatible")
    stage = str(manifest.get("stage"))
    expected = BENCHMARK_INTERVALS.get(stage)
    if expected is None:
        raise AcquisitionError("benchmark completion stage is invalid")
    artifacts = run_dir / "artifacts"
    gzip_relative = str(manifest["gzip"]["relative_path"])
    parquet_relative = str(manifest["parquet"]["relative_path"])
    gzip_summary = ChunkStore(artifacts, maximum_output_bytes=BENCHMARK_MAX_BYTES).verify(gzip_relative)
    parquet_summary = ParquetTickStore(
        artifacts, maximum_output_bytes=BENCHMARK_MAX_BYTES, minimum_free_bytes=0
    ).verify(parquet_relative)
    gzip_rows = _gzip_records(artifacts / gzip_relative)
    parquet_rows = read_tick_records(artifacts / parquet_relative)
    gzip_hash = canonical_tick_hash(gzip_rows)
    parquet_hash = canonical_tick_hash(parquet_rows)
    if (
        gzip_summary.record_count != parquet_summary.record_count
        or gzip_hash != parquet_hash
        or gzip_hash != manifest.get("canonical_content_sha256")
    ):
        raise AcquisitionError("benchmark stage read-back identity failed")
    journal = BenchmarkJournal.open(run_dir)
    records = journal.records()
    if not any(item["event"] == "RUN_COMPLETED" for item in records):
        raise AcquisitionError("benchmark stage journal is incomplete")
    return manifest


class AcquisitionBenchmark:
    def __init__(
        self,
        gateway: ReadOnlyMT5Gateway,
        output_root: Path,
        *,
        stage: str,
        journal: BenchmarkJournal,
        symbol_point: float,
        minimum_free_bytes: int,
        maximum_output_bytes: int = BENCHMARK_MAX_BYTES,
        interval: tuple[datetime, datetime] | None = None,
        mt5_session_count: int = 1,
        heartbeat_seconds: float | None = None,
    ) -> None:
        self.gateway = gateway
        if stage not in BENCHMARK_INTERVALS or journal.benchmark_stage not in {stage, "coverage"}:
            raise AcquisitionError("benchmark stage and journal disagree")
        self.stage = stage
        self.journal = journal
        self.symbol_point = float(symbol_point)
        self.benchmark_root = benchmark_root(output_root)
        self.root = journal.run_dir / "artifacts"
        self.minimum_free_bytes = int(minimum_free_bytes)
        self.maximum_output_bytes = int(maximum_output_bytes)
        self.interval = interval
        self.mt5_session_count = int(mt5_session_count)
        del heartbeat_seconds  # Supervisor heartbeats are intentionally process-external.
        self.gzip_store = ChunkStore(self.root, maximum_output_bytes=self.maximum_output_bytes)
        self.parquet_store = ParquetTickStore(
            self.root,
            maximum_output_bytes=self.maximum_output_bytes,
            minimum_free_bytes=self.minimum_free_bytes,
        )

    def run(self, *, initialization_seconds: float) -> dict[str, object]:
        start, end = self.interval or BENCHMARK_INTERVALS[self.stage]
        require_development_access(start, end, operation="benchmark stage")
        predecessor = STAGE_PREDECESSOR[self.stage]
        if predecessor and not verified_stage_runs(self.benchmark_root.parent.parent, predecessor):
            raise AcquisitionError("verified preceding benchmark stage is required")
        if output_size(self.journal.run_dir) >= self.maximum_output_bytes:
            raise AcquisitionError("benchmark output budget is already exhausted")
        if _free_bytes(self.root) <= self.minimum_free_bytes:
            raise AcquisitionError("benchmark blocked by the disk safety reserve")
        sample = self._run_sample(start, end)
        if output_size(self.journal.run_dir) > self.maximum_output_bytes:
            raise AcquisitionError("benchmark exceeded its hard output limit")
        estimate = estimate_hybrid_storage(sample)
        manifest = {
            "schema_version": BENCHMARK_SCHEMA_VERSION,
            "status": "VERIFIED",
            "run_id": self.journal.run_id,
            "stage": self.stage,
            "initialization_seconds": initialization_seconds,
            "sample": sample,
            "estimates": estimate,
            "gzip": {
                "relative_path": f"{self.stage}/{self._chunk_id(start, end)}.jsonl.gz",
                "size_bytes": sample.gzip_bytes,
                "sha256": sample.gzip_sha256,
            },
            "parquet": {
                "relative_path": f"{self.stage}/{self._chunk_id(start, end)}.parquet",
                "size_bytes": sample.parquet_bytes,
                "sha256": sample.parquet_sha256,
            },
            "canonical_content_sha256": sample.canonical_content_sha256,
            "combined_output_bytes": output_size(self.journal.run_dir),
            "maximum_output_bytes": self.maximum_output_bytes,
            "minimum_free_bytes": self.minimum_free_bytes,
            "free_bytes_after": _free_bytes(self.root),
            "holdout_accessed": False,
            "strategy_evaluated": False,
            "mt5_session_count": self.mt5_session_count,
        }
        atomic_json(self.journal.run_dir / "stage.complete.json", manifest)
        return canonical_data(manifest)

    @staticmethod
    def _chunk_id(start: datetime, end: datetime) -> str:
        return f"benchmark-{start:%Y%m%dT%H%M%S}-{end:%Y%m%dT%H%M%S}"

    def _run_sample(self, start: datetime, end: datetime) -> BenchmarkSample:
        interval = require_development_access(start, end, operation="benchmark sample")
        chunk_id = self._chunk_id(start, end)
        tracemalloc.start()
        self.journal.append("REQUEST_STARTED", status="RUNNING")
        request_started = time.perf_counter()
        request_raised = False
        try:
            raw = self.gateway.copy_ticks_range(
                EXECUTABLE_SYMBOL, start, end - timedelta(milliseconds=1)
            )
        except AcquisitionError:
            raw = None
            request_raised = True
        mt5_status = self.gateway.last_error_status()
        request_seconds = max(time.perf_counter() - request_started, 1e-9)
        response_kind, response_rows = response_shape(raw)
        request_classification = classify_response(response_kind, mt5_status, raised=request_raised)
        request_details = {
            "request_kind": "TICKS",
            "response_kind": response_kind,
            "row_count": response_rows,
            "mt5_error_code": mt5_status.code,
            "requested_start": start.isoformat().replace("+00:00", "Z"),
            "requested_end": end.isoformat().replace("+00:00", "Z"),
        }
        self.journal.append(
            "REQUEST_RESULT_CLASSIFIED",
            status=request_classification,
            error_category=request_classification if request_classification != "DATA_AVAILABLE" else None,
            details=request_details,
        )
        self.journal.append("REQUEST_COMPLETED", status=request_classification, details=request_details)
        if request_classification == "API_ERROR":
            raise AcquisitionError("benchmark tick history API error")
        if request_classification == "INVALID_RESPONSE":
            raise AcquisitionError("benchmark tick history response is invalid")
        if response_rows == 0:
            raise AcquisitionError("benchmark interval returned no quotes")
        self.journal.append("NORMALIZATION_STARTED", status="RUNNING")
        normalized, normalization_seconds = _elapsed(
            lambda: normalize_ticks(raw, symbol=EXECUTABLE_SYMBOL, chunk_id=chunk_id)
        )
        records, diagnostics = normalized
        if not records:
            raise AcquisitionError("benchmark interval returned no quotes")
        self.journal.append("NORMALIZATION_COMPLETED", status="PASSED")
        logical = _logical_bytes(records)
        if _free_bytes(self.root) - (logical * 2) <= self.minimum_free_bytes:
            raise AcquisitionError("benchmark serialization would breach the disk safety reserve")
        gzip_relative = f"{self.stage}/{chunk_id}.jsonl.gz"
        parquet_relative = f"{self.stage}/{chunk_id}.parquet"
        self.journal.append("GZIP_WRITE_STARTED", status="RUNNING")
        gzip_summary, gzip_write = _elapsed(
            lambda: self.gzip_store.write(
                gzip_relative, records, chunk_id=chunk_id, start=start, end=end,
                diagnostics=diagnostics,
            )
        )
        self.journal.append("GZIP_WRITE_COMPLETED", status="PASSED")
        self.journal.append("PARQUET_WRITE_STARTED", status="RUNNING")
        parquet_summary, parquet_write = _elapsed(
            lambda: self.parquet_store.write(
                parquet_relative, records, chunk_id=chunk_id,
                requested_start=start, requested_end=end, diagnostics=diagnostics,
            )
        )
        self.journal.append("PARQUET_WRITE_COMPLETED", status="PASSED")
        self.journal.append("HASH_VERIFICATION_STARTED", status="RUNNING")
        _gzip_verified, gzip_verify = _elapsed(lambda: self.gzip_store.verify(gzip_relative))
        _parquet_verified, parquet_verify = _elapsed(lambda: self.parquet_store.verify(parquet_relative))
        (gzip_sha, parquet_sha), hash_seconds = _elapsed(
            lambda: (
                file_sha256(self.root / gzip_relative),
                file_sha256(self.root / parquet_relative),
            )
        )
        self.journal.append("HASH_VERIFICATION_COMPLETED", status="PASSED")
        self.journal.append("READBACK_STARTED", status="RUNNING")
        gzip_rows, gzip_readback = _elapsed(lambda: _gzip_records(self.root / gzip_relative))
        parquet_rows, parquet_readback = _elapsed(lambda: read_tick_records(self.root / parquet_relative))
        gzip_content_hash = canonical_tick_hash(gzip_rows)
        parquet_content_hash = canonical_tick_hash(parquet_rows)
        if gzip_content_hash != parquet_content_hash or len(gzip_rows) != len(parquet_rows):
            raise AcquisitionError("benchmark read-back content differs by format")
        self.journal.append("READBACK_COMPLETED", status="PASSED")
        spread = _spread_distribution(records, self.symbol_point)
        ordering_violations = sum(
            int(int(current["time_msc"]) < int(previous["time_msc"]))
            for previous, current in zip(records, records[1:])
        )
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        del current
        # append_access_record accepts only serializable metadata; keep the call
        # separate from the timed data path so access evidence cannot be omitted.
        access_path = self.benchmark_root.parent.parent / "manifests" / "data_access_log.json"
        append_access_record(access_path, {
            "access_id": f"{self.journal.run_id}:{chunk_id}",
            "start": interval.start,
            "end_exclusive": interval.end,
            "classification": classify_interval(interval),
            "purpose": f"storage-throughput-benchmark-{self.stage}",
            "strategy_evaluated": False,
            "row_count": len(records),
        })
        returned_start = datetime.fromtimestamp(int(records[0]["time_msc"]) / 1000, tz=UTC)
        returned_end = datetime.fromtimestamp(int(records[-1]["time_msc"]) / 1000, tz=UTC)
        return BenchmarkSample(
            run_id=self.journal.run_id, stage=self.stage,
            requested_start=start, requested_end=end,
            returned_start=returned_start, returned_end=returned_end,
            rows=len(records), request_seconds=request_seconds,
            normalization_seconds=normalization_seconds, logical_json_bytes=logical,
            gzip_bytes=gzip_summary.size_bytes, parquet_bytes=parquet_summary.size_bytes,
            gzip_write_seconds=gzip_write, parquet_write_seconds=parquet_write,
            gzip_verify_seconds=gzip_verify, parquet_verify_seconds=parquet_verify,
            gzip_readback_seconds=gzip_readback, parquet_readback_seconds=parquet_readback,
            hash_seconds=hash_seconds, peak_python_bytes=peak,
            duplicate_count=int(diagnostics["duplicate_count"]),
            crossed_quote_count=int(diagnostics["crossed_quote_count"]),
            zero_quote_count=int(diagnostics["zero_quote_count"]),
            non_finite_quote_count=int(diagnostics["non_finite_quote_count"]),
            gap_count=int(diagnostics["gap_count"]),
            weekend_gap_count=int(diagnostics["weekend_gap_count"]),
            maximum_gap_seconds=int(diagnostics["max_gap_seconds"]),
            ordering_violations=ordering_violations,
            first_bid=float(records[0]["bid"]), first_ask=float(records[0]["ask"]),
            last_bid=float(records[-1]["bid"]), last_ask=float(records[-1]["ask"]),
            gzip_sha256=gzip_sha, parquet_sha256=parquet_sha,
            canonical_content_sha256=gzip_content_hash,
            readback_equal=True, schema_version=BENCHMARK_SCHEMA_VERSION,
            **spread,
        )


def estimate_hybrid_storage(sample: BenchmarkSample) -> dict[str, object]:
    seconds = max((sample.requested_end - sample.requested_start).total_seconds(), 1.0)
    parquet_per_second = sample.parquet_bytes / seconds
    gzip_per_second = sample.gzip_bytes / seconds
    active_ratio = 5 / 7
    calibration_seconds = sum((item.end - item.start).total_seconds() for item in calibration_blocks()) * active_ratio
    holdout_seconds = (PROPOSED_HOLDOUT_END - PROPOSED_HOLDOUT_START).total_seconds() * active_ratio
    development_seconds = (DEVELOPMENT_END - DEVELOPMENT_START).total_seconds()
    m5_rows = development_seconds / 300 * active_ratio
    xau_bar_rows = m5_rows * (1 + 1 / 3 + 1 / 12 + 1 / 48 + 1 / 288 + 1 / 2016)
    dxy_rows = 6 * m5_rows * (1 + 1 / 12)

    def scenarios(baseline: float) -> dict[str, int]:
        return {"lower": int(baseline * 0.75), "baseline": int(baseline), "upper": int(baseline * 1.5)}

    bars = scenarios(xau_bar_rows * 96)
    dxy = scenarios(dxy_rows * 96)
    calibration = scenarios(parquet_per_second * calibration_seconds)
    holdout = scenarios(parquet_per_second * holdout_seconds)
    combined = {
        key: bars[key] + dxy[key] + calibration[key] + holdout[key]
        for key in ("lower", "baseline", "upper")
    }
    warm_rows_per_second = sample.rows / max(sample.request_seconds, 1e-9)
    weekly_chunks = len(calibration_blocks()) + int((PROPOSED_HOLDOUT_END - PROPOSED_HOLDOUT_START).days / 7) + 1
    duration = weekly_chunks * sample.request_seconds + combined["baseline"] / max(
        sample.parquet_bytes / max(sample.parquet_write_seconds + sample.parquet_verify_seconds, 1e-9), 1.0
    )
    return {
        "scenario_ranges_are_not_confidence_intervals": True,
        "xau_development_bars_bytes": bars,
        "dxy_development_bars_bytes": dxy,
        "calibration_ticks_bytes": calibration,
        "continuous_proposed_holdout_ticks_bytes": holdout,
        "combined_bytes": combined,
        "temporary_working_bytes": max(sample.gzip_bytes + sample.parquet_bytes, combined["upper"] // max(weekly_chunks, 1)),
        "required_safety_reserve_bytes": 15 * 1024**3,
        "observed_parquet_bytes_per_active_second": parquet_per_second,
        "observed_gzip_bytes_per_active_second": gzip_per_second,
        "observed_warm_rows_per_second": warm_rows_per_second,
        "estimated_duration_seconds": duration,
    }
