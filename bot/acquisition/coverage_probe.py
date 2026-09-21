from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from bot.validation.models import canonical_data

from .gateway import ReadOnlyMT5Gateway, SafeMT5Error
from .journal import BenchmarkJournal
from .models import AcquisitionError, EXECUTABLE_SYMBOL
from .storage import atomic_json


UTC = timezone.utc
PROBE_SCHEMA_VERSION = "phase8b.tick-coverage.v1"
PROBE_WINDOW = timedelta(minutes=15)
MAX_TICK_REQUESTS = 30
MAX_BAR_REQUESTS = 10
MAX_WALL_SECONDS = 30 * 60
RECENT_CONTROL = datetime(2026, 8, 31, 12, tzinfo=UTC)
TARGET_CONTROL = datetime(2024, 8, 5, 12, tzinfo=UTC)
DEVELOPMENT_END = datetime(2025, 1, 1, tzinfo=UTC)
COARSE_STARTS = (
    datetime(2024, 11, 5, 12, tzinfo=UTC),
    datetime(2025, 2, 4, 12, tzinfo=UTC),
    datetime(2025, 5, 6, 12, tzinfo=UTC),
    datetime(2025, 8, 5, 12, tzinfo=UTC),
    datetime(2025, 11, 4, 12, tzinfo=UTC),
    datetime(2026, 2, 3, 12, tzinfo=UTC),
    datetime(2026, 5, 5, 12, tzinfo=UTC),
    datetime(2026, 8, 4, 12, tzinfo=UTC),
)


@dataclass(frozen=True)
class ProbeObservation:
    interval_id: str
    request_kind: str
    requested_start: datetime
    requested_end: datetime
    response_kind: str
    classification: str
    row_count: int
    elapsed_seconds: float
    mt5_error_code: int | None
    mt5_error_category: str
    error_description_sha256: str

    @property
    def available(self) -> bool:
        return self.classification == "DATA_AVAILABLE" and self.row_count > 0


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def response_shape(raw: object) -> tuple[str, int]:
    if raw is None:
        return "NONE", 0
    try:
        count = len(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "INVALID", 0
    return ("EMPTY_ARRAY", 0) if count == 0 else ("ROWS", int(count))


def classify_response(response_kind: str, status: SafeMT5Error, *, raised: bool) -> str:
    if raised or response_kind == "NONE" or status.category not in {"SUCCESS"}:
        return "API_ERROR"
    if response_kind == "INVALID":
        return "INVALID_RESPONSE"
    if response_kind == "EMPTY_ARRAY":
        return "EMPTY_SUCCESS_RESPONSE"
    return "DATA_AVAILABLE"


def _first_tuesday(year: int, month: int) -> datetime:
    value = datetime(year, month, 1, 12, tzinfo=UTC)
    return value + timedelta(days=(1 - value.weekday()) % 7)


def _monthly_starts(after: datetime, before: datetime) -> tuple[datetime, ...]:
    year, month = after.year, after.month
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    result: list[datetime] = []
    while (year, month) < (before.year, before.month):
        result.append(_first_tuesday(year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return tuple(result)


class TickCoverageProbe:
    def __init__(
        self,
        gateway: ReadOnlyMT5Gateway,
        output_root: Path,
        journal: BenchmarkJournal,
        *,
        m5_timeframe: int,
        monotonic: Callable[[], float] = time.monotonic,
        maximum_tick_requests: int = MAX_TICK_REQUESTS,
        maximum_bar_requests: int = MAX_BAR_REQUESTS,
        maximum_wall_seconds: float = MAX_WALL_SECONDS,
    ) -> None:
        if journal.benchmark_stage != "coverage":
            raise AcquisitionError("coverage probe requires a coverage journal")
        if maximum_tick_requests < 2 or maximum_tick_requests > MAX_TICK_REQUESTS:
            raise AcquisitionError("coverage tick request cap is invalid")
        if maximum_bar_requests < 1 or maximum_bar_requests > MAX_BAR_REQUESTS:
            raise AcquisitionError("coverage bar request cap is invalid")
        if maximum_wall_seconds <= 0 or maximum_wall_seconds > MAX_WALL_SECONDS:
            raise AcquisitionError("coverage wall limit is invalid")
        self.gateway = gateway
        self.output_root = Path(output_root)
        self.journal = journal
        self.m5_timeframe = int(m5_timeframe)
        self.monotonic = monotonic
        self.maximum_tick_requests = int(maximum_tick_requests)
        self.maximum_bar_requests = int(maximum_bar_requests)
        self.maximum_wall_seconds = float(maximum_wall_seconds)
        self._started = monotonic()
        self._tick_requests = 0
        self._bar_requests = 0
        self._observations: list[ProbeObservation] = []

    def _check_budget(self, request_kind: str) -> None:
        if self.monotonic() - self._started > self.maximum_wall_seconds:
            raise TimeoutError("coverage probe wall limit exceeded")
        if request_kind == "TICKS" and self._tick_requests >= self.maximum_tick_requests:
            raise AcquisitionError("coverage tick request cap reached")
        if request_kind == "BARS" and self._bar_requests >= self.maximum_bar_requests:
            raise AcquisitionError("coverage bar request cap reached")

    def _request(self, interval_id: str, request_kind: str, start: datetime) -> ProbeObservation:
        self._check_budget(request_kind)
        end = start + PROBE_WINDOW
        if start.weekday() >= 5:
            raise AcquisitionError("coverage probes cannot request weekend intervals")
        if request_kind == "TICKS":
            self._tick_requests += 1
        else:
            self._bar_requests += 1
        details = {
            "interval_id": interval_id,
            "request_kind": request_kind,
            "requested_start": start.isoformat().replace("+00:00", "Z"),
            "requested_end": end.isoformat().replace("+00:00", "Z"),
        }
        self.journal.append("PROBE_INTERVAL_STARTED", status="RUNNING", details=details)
        request_started = self.monotonic()
        raised = False
        try:
            if request_kind == "TICKS":
                raw = self.gateway.copy_ticks_range(
                    EXECUTABLE_SYMBOL, start, end - timedelta(milliseconds=1)
                )
            else:
                raw = self.gateway.copy_rates_range(
                    EXECUTABLE_SYMBOL, self.m5_timeframe, start, end - timedelta(milliseconds=1)
                )
        except AcquisitionError:
            raw = None
            raised = True
        status = self.gateway.last_error_status()
        elapsed = max(self.monotonic() - request_started, 0.0)
        response_kind, row_count = response_shape(raw)
        classification = classify_response(response_kind, status, raised=raised)
        observation = ProbeObservation(
            interval_id=interval_id,
            request_kind=request_kind,
            requested_start=start,
            requested_end=end,
            response_kind=response_kind,
            classification=classification,
            row_count=row_count,
            elapsed_seconds=elapsed,
            mt5_error_code=status.code,
            mt5_error_category=status.category,
            error_description_sha256=status.description_sha256,
        )
        classified = {
            **details,
            "response_kind": response_kind,
            "row_count": row_count,
            "mt5_error_code": status.code,
        }
        self.journal.append(
            "REQUEST_RESULT_CLASSIFIED",
            status=classification,
            error_category=classification if classification != "DATA_AVAILABLE" else None,
            details=classified,
        )
        self.journal.append("PROBE_INTERVAL_COMPLETED", status=classification, details=classified)
        self._observations.append(observation)
        return observation

    def _tick(self, interval_id: str, start: datetime) -> ProbeObservation:
        return self._request(interval_id, "TICKS", start)

    def _bar(self, interval_id: str, start: datetime) -> ProbeObservation:
        return self._request(interval_id, "BARS", start)

    def run(self) -> dict[str, object]:
        recent = self._tick("recent-positive-control", RECENT_CONTROL)
        target = self._tick("target-2024-control", TARGET_CONTROL)
        target_bar = self._bar("target-2024-bar-control", TARGET_CONTROL)

        earliest_candidate = target if target.available else None
        latest_unavailable = target if not target.available else None
        if recent.available and not target.available:
            first_coarse_available: ProbeObservation | None = None
            for index, start in enumerate(COARSE_STARTS, start=1):
                observed = self._tick(f"coarse-{index:02d}", start)
                if observed.available:
                    first_coarse_available = observed
                    break
                latest_unavailable = observed
            if first_coarse_available is None:
                first_coarse_available = recent
            earliest_candidate = first_coarse_available
            if latest_unavailable is not None:
                for index, start in enumerate(
                    _monthly_starts(latest_unavailable.requested_start, earliest_candidate.requested_start),
                    start=1,
                ):
                    observed = self._tick(f"monthly-{index:02d}", start)
                    if observed.available:
                        earliest_candidate = observed
                        break
                    latest_unavailable = observed

        complete_hour_start: datetime | None = None
        hour_checks: list[ProbeObservation] = []
        if earliest_candidate is not None and earliest_candidate.available and earliest_candidate.requested_start < DEVELOPMENT_END:
            hour_checks.append(earliest_candidate)
            for quarter in range(1, 4):
                hour_checks.append(
                    self._tick(
                        f"hour-quarter-{quarter + 1}",
                        earliest_candidate.requested_start + quarter * PROBE_WINDOW,
                    )
                )
            if all(item.available for item in hour_checks):
                complete_hour_start = earliest_candidate.requested_start

        tick_observations = sorted(
            (item for item in self._observations if item.request_kind == "TICKS"),
            key=lambda item: (item.requested_start, item.interval_id),
        )
        availability = [item.available for item in tick_observations]
        first_available_index = next((index for index, value in enumerate(availability) if value), None)
        monotonic = first_available_index is None or all(availability[first_available_index:])
        ambiguous = any(
            item.classification in {"API_ERROR", "INVALID_RESPONSE"} for item in self._observations
        ) or not monotonic
        if not recent.available:
            conclusion = "GATEWAY_SESSION_DEFECT"
        elif ambiguous:
            conclusion = "INTERMITTENT_OR_AMBIGUOUS"
        elif target.available:
            conclusion = "TARGET_TICK_HISTORY_AVAILABLE"
        elif target_bar.available:
            conclusion = "TICK_RETENTION_LIMITATION"
        else:
            conclusion = "SYMBOL_HISTORY_LIMITATION"

        available_ticks = [item for item in tick_observations if item.available]
        earliest_available = available_ticks[0] if available_ticks else None
        unavailable_before = [
            item
            for item in tick_observations
            if not item.available
            and earliest_available is not None
            and item.requested_start < earliest_available.requested_start
        ]
        latest_unavailable_before = unavailable_before[-1] if unavailable_before else None
        timings = [item.elapsed_seconds for item in self._observations]
        result = canonical_data({
            "schema_version": PROBE_SCHEMA_VERSION,
            "status": "VERIFIED",
            "run_id": self.journal.run_id,
            "symbol": EXECUTABLE_SYMBOL,
            "probe_window_seconds": int(PROBE_WINDOW.total_seconds()),
            "tick_request_count": self._tick_requests,
            "bar_request_count": self._bar_requests,
            "maximum_tick_requests": self.maximum_tick_requests,
            "maximum_bar_requests": self.maximum_bar_requests,
            "observations": [asdict(item) for item in self._observations],
            "recent_positive_control_rows": recent.row_count,
            "recent_previous_rows": 3136,
            "recent_row_difference": recent.row_count - 3136,
            "target_tick_rows": target.row_count,
            "target_bar_rows": target_bar.row_count,
            "conclusion": conclusion,
            "availability_monotonic": monotonic,
            "earliest_confirmed_available_start": (
                earliest_available.requested_start if earliest_available is not None else None
            ),
            "latest_confirmed_unavailable_before_start": (
                latest_unavailable_before.requested_start if latest_unavailable_before is not None else None
            ),
            "complete_development_hour_start": complete_hour_start,
            "conditional_benchmark_authorized": complete_hour_start is not None and not ambiguous,
            "request_timing_seconds": {
                "minimum": min(timings),
                "median": statistics.median(timings),
                "maximum": max(timings),
                "total": sum(timings),
            },
            "raw_ticks_persisted": False,
            "strategy_evaluated": False,
            "profitability_evaluated": False,
        })
        result_path = self.journal.run_dir / "probe.result.json"
        atomic_json(result_path, result)
        completion = {
            "schema_version": PROBE_SCHEMA_VERSION,
            "status": "VERIFIED",
            "run_id": self.journal.run_id,
            "result_relative_path": result_path.name,
            "result_sha256": _file_sha256(result_path),
        }
        atomic_json(self.journal.run_dir / "probe.complete.json", completion)
        self.journal.append(
            "PROBE_COMPLETED",
            status=conclusion,
            details={
                "benchmark_authorized": bool(result["conditional_benchmark_authorized"]),
                "row_count": int(result["recent_positive_control_rows"]),
            },
        )
        return result


def verify_coverage_probe(run_dir: Path) -> dict[str, object]:
    run_dir = Path(run_dir)
    try:
        completion = json.loads((run_dir / "probe.complete.json").read_text(encoding="utf-8"))
        result_path = run_dir / str(completion["result_relative_path"])
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AcquisitionError("coverage probe completion is unavailable") from exc
    if (
        completion.get("schema_version") != PROBE_SCHEMA_VERSION
        or completion.get("status") != "VERIFIED"
        or completion.get("run_id") != run_dir.name
        or completion.get("result_sha256") != _file_sha256(result_path)
        or result.get("run_id") != run_dir.name
        or result.get("raw_ticks_persisted") is not False
        or int(result.get("tick_request_count", MAX_TICK_REQUESTS + 1)) > MAX_TICK_REQUESTS
        or int(result.get("bar_request_count", MAX_BAR_REQUESTS + 1)) > MAX_BAR_REQUESTS
    ):
        raise AcquisitionError("coverage probe completion is incompatible")
    records = BenchmarkJournal.open(run_dir).records()
    if not any(item["event"] == "PROBE_COMPLETED" for item in records):
        raise AcquisitionError("coverage probe journal is incomplete")
    return result
