from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from bot.backtesting.models import FidelityClass


UTC = timezone.utc
SYNTHETIC_LABEL = "SYNTHETIC TEST FIXTURE - NOT MARKET EVIDENCE"
FRAMEWORK_VERSION = "phase8a-validation-v1"


class ValidationError(ValueError):
    """Raised when a study boundary cannot be validated safely."""


class AcceptanceOutcome(str, Enum):
    ACCEPTED_FOR_FINAL_VALIDATION = "ACCEPTED_FOR_FINAL_VALIDATION"
    ACCEPTED_FOR_DEVELOPMENT_ONLY = "ACCEPTED_FOR_DEVELOPMENT_ONLY"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    REJECTED = "REJECTED"


class DataStreamKind(str, Enum):
    EXECUTION_QUOTES = "EXECUTION_QUOTES"
    ANALYSIS_CANDLES = "ANALYSIS_CANDLES"
    DXY_CONSTITUENT = "DXY_CONSTITUENT"
    DIRECT_DXY = "DIRECT_DXY"
    NEWS_EVENTS = "NEWS_EVENTS"
    BROKER_METADATA = "BROKER_METADATA"
    SLIPPAGE_OBSERVATIONS = "SLIPPAGE_OBSERVATIONS"


def utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValidationError(f"{field_name} must be timezone-aware")
    normalized = value.astimezone(UTC)
    if value.utcoffset() != timedelta(0):
        raise ValidationError(f"{field_name} must be expressed in UTC")
    return normalized


def parse_utc(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be an ISO UTC timestamp") from exc
    return utc_datetime(parsed, field_name)


def finite(value: float, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(f"{field_name} must be finite")
    return number


def canonical_data(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return utc_datetime(value, "serialized timestamp").isoformat().replace("+00:00", "Z")
    if isinstance(value, timedelta):
        return value.total_seconds()
    if is_dataclass(value):
        return canonical_data(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): canonical_data(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value) if isinstance(value, (set, frozenset)) else value
        return [canonical_data(item) for item in items]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(canonical_data(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StudyPeriod:
    start: datetime
    end: datetime
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", utc_datetime(self.start, f"{self.name} start"))
        object.__setattr__(self, "end", utc_datetime(self.end, f"{self.name} end"))
        if not self.name or self.end <= self.start:
            raise ValidationError("study periods require a name and increasing UTC boundaries")

    def overlaps(self, other: "StudyPeriod") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class DataStreamManifest:
    name: str
    kind: DataStreamKind
    relative_path: str
    sha256: str
    symbol: str
    start: datetime
    end: datetime
    record_count: int
    provenance: str
    license_or_restrictions: str
    timeframe: str | None = None
    maximum_expected_gap_seconds: int | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.provenance or not self.license_or_restrictions:
            raise ValidationError("stream identity, provenance and licensing notes are required")
        path = PurePosixPath(self.relative_path.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValidationError("stream paths must be safe package-relative paths")
        if len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256.lower()):
            raise ValidationError("stream hashes must be lowercase SHA-256 values")
        object.__setattr__(self, "start", utc_datetime(self.start, f"{self.name} start"))
        object.__setattr__(self, "end", utc_datetime(self.end, f"{self.name} end"))
        if self.end < self.start or self.record_count < 1:
            raise ValidationError("stream coverage and record count are invalid")
        if self.maximum_expected_gap_seconds is not None and self.maximum_expected_gap_seconds < 1:
            raise ValidationError("maximum expected gap must be positive")


@dataclass(frozen=True)
class EmpiricalPackageManifest:
    schema_version: int
    package_id: str
    broker_source: str
    fidelity: FidelityClass
    evaluation_period: StudyPeriod
    streams: tuple[DataStreamManifest, ...]
    synthetic: bool
    collection_method: str
    created_at: datetime
    raw_data_outside_git: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not self.package_id or not self.broker_source:
            raise ValidationError("unsupported package schema or missing package identity")
        if not self.collection_method:
            raise ValidationError("collection or export method is required")
        object.__setattr__(self, "created_at", utc_datetime(self.created_at, "package creation time"))
        if not self.raw_data_outside_git:
            raise ValidationError("raw empirical data must remain outside Git")
        names = [stream.name for stream in self.streams]
        if len(names) != len(set(names)):
            raise ValidationError("stream names must be unique")

    @property
    def package_hash(self) -> str:
        return canonical_hash(self)


@dataclass(frozen=True)
class AcceptanceIssue:
    reason_code: str
    stream: str | None
    detail: str
    fatal: bool = True


@dataclass(frozen=True)
class AcceptanceReport:
    package_id: str
    package_hash: str
    outcome: AcceptanceOutcome
    checked_at: datetime
    issues: tuple[AcceptanceIssue, ...]
    accepted_stream_hashes: Mapping[str, str]
    fidelity: FidelityClass
    synthetic_label: str | None
    framework_version: str = FRAMEWORK_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", utc_datetime(self.checked_at, "acceptance check time"))
        if self.outcome is AcceptanceOutcome.ACCEPTED_FOR_FINAL_VALIDATION and self.synthetic_label:
            raise ValidationError("synthetic packages cannot be accepted for final validation")

    @property
    def permits_final_validation(self) -> bool:
        return self.outcome is AcceptanceOutcome.ACCEPTED_FOR_FINAL_VALIDATION


@dataclass(frozen=True)
class ValidationPlan:
    schema_version: int
    plan_id: str
    research_hypothesis: str
    strategy_fingerprint: str
    execution_fingerprint: str
    risk_policy_version: str
    initial_capital: float
    dataset_hash: str
    development_period: StudyPeriod
    validation_period: StudyPeriod
    final_holdout: StudyPeriod
    walk_forward_mode: str
    fold_count: int
    purge_seconds: int
    embargo_seconds: int
    warmup_seconds: int
    primary_metrics: tuple[str, ...]
    secondary_metrics: tuple[str, ...]
    acceptance_policy_version: str
    stress_scenarios: tuple[str, ...]
    sensitivity_spec: Mapping[str, tuple[float, ...]]
    statistical_procedures: tuple[str, ...]
    random_seeds: tuple[int, ...]
    permitted_candidate_ids: tuple[str, ...]
    maximum_trials: int
    invalidation_conditions: tuple[str, ...]
    finalized_at: datetime

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not self.plan_id or not self.research_hypothesis:
            raise ValidationError("validation plan identity and hypothesis are required")
        for value, name in (
            (self.strategy_fingerprint, "strategy fingerprint"),
            (self.execution_fingerprint, "execution fingerprint"),
            (self.dataset_hash, "dataset hash"),
        ):
            if not value:
                raise ValidationError(f"{name} is required")
        capital = finite(self.initial_capital, "initial capital")
        if capital <= 0 or self.fold_count < 1 or self.maximum_trials < 1:
            raise ValidationError("capital, folds and trials must be positive")
        if self.maximum_trials < len(self.permitted_candidate_ids):
            raise ValidationError("trial limit cannot be below permitted candidates")
        if any(value < 0 for value in (self.purge_seconds, self.embargo_seconds, self.warmup_seconds)):
            raise ValidationError("purge, embargo and warm-up cannot be negative")
        if self.walk_forward_mode not in {"ANCHORED", "ROLLING"}:
            raise ValidationError("walk-forward mode must be ANCHORED or ROLLING")
        if not self.development_period.end <= self.validation_period.start:
            raise ValidationError("development must end before validation")
        if not self.validation_period.end <= self.final_holdout.start:
            raise ValidationError("validation must end before final holdout")
        if not self.primary_metrics or not self.acceptance_policy_version:
            raise ValidationError("primary metrics and acceptance policy are required")
        object.__setattr__(self, "finalized_at", utc_datetime(self.finalized_at, "plan finalization time"))

    @property
    def plan_hash(self) -> str:
        return canonical_hash(self)


@dataclass(frozen=True)
class FoldManifest:
    fold_id: str
    training: StudyPeriod
    warmup: StudyPeriod
    evaluation: StudyPeriod
    purge_seconds: int
    embargo_seconds: int
    manifest_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.fold_id or self.purge_seconds < 0 or self.embargo_seconds < 0:
            raise ValidationError("fold identity and non-negative boundaries are required")
        if self.training.end + timedelta(seconds=self.purge_seconds) > self.evaluation.start:
            raise ValidationError("fold purge boundary is violated")
        if not (self.warmup.end <= self.evaluation.start and self.warmup.start >= self.training.start):
            raise ValidationError("warm-up must be historical and excluded from evaluation")
        payload = {
            "fold_id": self.fold_id,
            "training": self.training,
            "warmup": self.warmup,
            "evaluation": self.evaluation,
            "purge_seconds": self.purge_seconds,
            "embargo_seconds": self.embargo_seconds,
        }
        object.__setattr__(self, "manifest_hash", canonical_hash(payload))


@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    parent_candidate_id: str | None
    parameter_difference: Mapping[str, Any]
    reason: str
    dataset_periods_accessed: tuple[str, ...]
    metrics_examined: tuple[str, ...]
    seed: int
    registered_at: datetime
    outcome: str
    rejection_reason: str | None
    final_holdout_accessed: bool

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.reason or not self.outcome:
            raise ValidationError("candidate identity, reason and outcome are required")
        object.__setattr__(self, "registered_at", utc_datetime(self.registered_at, "candidate registration time"))


@dataclass(frozen=True)
class TradeSample:
    trade_id: str
    opened_at: datetime
    closed_at: datetime
    side: str
    gross_pnl: float
    net_pnl: float
    net_r: float
    costs: float
    exposure_seconds: float
    turnover: float
    regime: str
    session: str
    spread_environment: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "opened_at", utc_datetime(self.opened_at, "trade open time"))
        object.__setattr__(self, "closed_at", utc_datetime(self.closed_at, "trade close time"))
        if not self.trade_id or self.closed_at < self.opened_at:
            raise ValidationError("trade identity and chronology are required")
        if self.side not in {"LONG", "SHORT"}:
            raise ValidationError("trade side must be LONG or SHORT")
        for field_name in ("gross_pnl", "net_pnl", "net_r", "costs", "exposure_seconds", "turnover"):
            object.__setattr__(self, field_name, finite(getattr(self, field_name), field_name))
        if self.costs < 0 or self.exposure_seconds < 0 or self.turnover < 0:
            raise ValidationError("cost, exposure and turnover values cannot be negative")


@dataclass(frozen=True)
class HoldoutIdentity:
    dataset_hash: str
    period: StudyPeriod
    strategy_fingerprint: str
    execution_fingerprint: str
    validation_plan_hash: str
    candidate_id: str

    @property
    def identity_hash(self) -> str:
        return canonical_hash(self)
