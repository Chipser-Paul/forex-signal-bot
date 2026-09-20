from __future__ import annotations

import calendar
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from filelock import FileLock

from bot.validation.models import canonical_data

from .models import AcquisitionError, utc_datetime
from .storage import _atomic_json_locked


UTC = timezone.utc
DEVELOPMENT_START = datetime(2019, 1, 1, tzinfo=UTC)
DEVELOPMENT_END = datetime(2025, 1, 1, tzinfo=UTC)
PROPOSED_HOLDOUT_START = datetime(2025, 1, 1, tzinfo=UTC)
PROPOSED_HOLDOUT_END = datetime(2026, 8, 1, tzinfo=UTC)
BENCHMARK_START = datetime(2024, 8, 5, tzinfo=UTC)
BENCHMARK_END = datetime(2024, 8, 12, tzinfo=UTC)
PLAN_VERSION = "phase8b-hybrid-v1"


@dataclass(frozen=True)
class DataInterval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", utc_datetime(self.start, "interval start"))
        object.__setattr__(self, "end", utc_datetime(self.end, "interval end"))
        if self.end <= self.start:
            raise AcquisitionError("data interval must increase")

    def overlaps(self, other: "DataInterval") -> bool:
        return self.start < other.end and other.start < self.end


def first_complete_monday_week(year: int, month: int) -> DataInterval:
    first = datetime(year, month, 1, tzinfo=UTC)
    offset = (calendar.MONDAY - first.weekday()) % 7
    start = first + timedelta(days=offset)
    return DataInterval(start, start + timedelta(days=7))


def calibration_blocks() -> tuple[DataInterval, ...]:
    blocks = tuple(
        first_complete_monday_week(year, month)
        for year in range(2019, 2025)
        for month in (1, 4, 7, 10)
    )
    if any(block.end > DEVELOPMENT_END for block in blocks):
        raise AcquisitionError("calibration selection escaped the development period")
    return blocks


def chunk_ranges(start: datetime, end: datetime, *, days: int) -> tuple[DataInterval, ...]:
    begin = utc_datetime(start, "chunk start")
    finish = utc_datetime(end, "chunk end")
    if finish <= begin or days < 1:
        raise AcquisitionError("chunk interval and duration must be positive")
    result: list[DataInterval] = []
    cursor = begin
    while cursor < finish:
        boundary = min(cursor + timedelta(days=days), finish)
        result.append(DataInterval(cursor, boundary))
        cursor = boundary
    if any(left.end != right.start for left, right in zip(result, result[1:])):
        raise AcquisitionError("chunk plan has a gap or overlap")
    return tuple(result)


def classify_interval(interval: DataInterval) -> str:
    development = DataInterval(DEVELOPMENT_START, DEVELOPMENT_END)
    holdout = DataInterval(PROPOSED_HOLDOUT_START, PROPOSED_HOLDOUT_END)
    if interval.start >= development.start and interval.end <= development.end:
        return "DEVELOPMENT"
    if interval.start >= holdout.start and interval.end <= holdout.end:
        return "PROPOSED_UNTOUCHED_HOLDOUT"
    if interval.overlaps(holdout):
        return "CROSSES_PROPOSED_HOLDOUT"
    return "OUTSIDE_PROPOSED_HOLDOUT"


def require_development_access(start: datetime, end: datetime, *, operation: str) -> DataInterval:
    interval = DataInterval(start, end)
    if classify_interval(interval) != "DEVELOPMENT":
        raise AcquisitionError(f"{operation} is restricted to the preregistered development interval")
    return interval


def plan_payload() -> dict[str, object]:
    blocks = calibration_blocks()
    payload: dict[str, object] = {
        "schema_version": 1,
        "plan_version": PLAN_VERSION,
        "status": "PROPOSED_NOT_FINALIZED",
        "development": {
            "start": DEVELOPMENT_START,
            "end_exclusive": DEVELOPMENT_END,
            "purpose": "development-regime-sensitivity-and-stress-evidence",
        },
        "tick_calibration": {
            "selection_rule": "first Monday-starting seven-day UTC block in January, April, July, and October of each development year",
            "selection_basis": "calendar-only-no-performance-or-volatility-selection",
            "continuous_coverage_claimed": False,
            "blocks": [asdict(item) for item in blocks],
        },
        "proposed_untouched_tick_holdout": {
            "start": PROPOSED_HOLDOUT_START,
            "end_exclusive": PROPOSED_HOLDOUT_END,
            "locked": True,
            "performance_access_permitted": False,
            "status": "PROVISIONAL_UNTIL_FINAL_PLAN_HASHED",
        },
        "benchmark": {"start": BENCHMARK_START, "end_exclusive": BENCHMARK_END, "maximum_output_bytes": 1024**3},
        "bulk_storage": {"format": "parquet", "compression": "zstd", "tick_chunk_days": 7},
        "outstanding_inputs": [
            "licensed_historical_usd_high_impact_news",
            "commission_schedule",
            "historical_or_preregistered_slippage",
            "rollover_timezone",
            "historically_effective_symbol_metadata",
            "licensing_declarations",
        ],
        "prior_access": [
            {
                "access_id": "phase8b-sample-20260831T120000-20260831T121500",
                "start": datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
                "end_exclusive": datetime(2026, 8, 31, 12, 15, tzinfo=UTC),
                "classification": "OUTSIDE_PROPOSED_HOLDOUT",
                "purpose": "bounded-acquisition-integrity-sample",
                "strategy_evaluated": False,
                "integrity_manifest": "samples/XAUUSDm/sample-20260831T120000-20260831T121500.manifest.json",
            }
        ],
    }
    canonical = canonical_data(payload)
    payload["plan_content_sha256"] = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()
    return payload


def append_access_record(path: Path, record: dict[str, object]) -> None:
    required = {"access_id", "start", "end_exclusive", "classification", "purpose", "strategy_evaluated"}
    if not required <= set(record):
        raise AcquisitionError("access record is incomplete")
    if record["strategy_evaluated"] is not False:
        raise AcquisitionError("acquisition access log cannot record strategy evaluation")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock", timeout=10):
        existing: list[dict[str, object]] = []
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise AcquisitionError("access log is malformed") from exc
            if not isinstance(loaded, list):
                raise AcquisitionError("access log must contain an array")
            existing = loaded
        if any(item.get("access_id") == record["access_id"] for item in existing):
            return
        existing.append(canonical_data(record))
        existing.sort(key=lambda item: str(item["access_id"]))
        _atomic_json_locked(path, existing, refuse_overwrite=False)
