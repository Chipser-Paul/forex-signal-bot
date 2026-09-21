from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from filelock import FileLock

from .models import (
    AcceptanceOutcome,
    AcceptanceReport,
    CandidateRecord,
    FoldManifest,
    HoldoutIdentity,
    StudyPeriod,
    ValidationError,
    ValidationPlan,
    canonical_data,
    canonical_hash,
    canonical_json,
    parse_utc,
    utc_datetime,
)


SENSITIVE_KEY_PARTS = ("PASSWORD", "SECRET", "TOKEN", "CREDENTIAL", "API_KEY", "MT5_LOGIN")


def load_validation_plan(path: Path) -> ValidationPlan:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))

        def period(name: str) -> StudyPeriod:
            item = raw[name]
            return StudyPeriod(parse_utc(item["start"], f"{name} start"), parse_utc(item["end"], f"{name} end"), item["name"])

        return ValidationPlan(
            schema_version=raw["schema_version"],
            plan_id=raw["plan_id"],
            research_hypothesis=raw["research_hypothesis"],
            strategy_fingerprint=raw["strategy_fingerprint"],
            execution_fingerprint=raw["execution_fingerprint"],
            risk_policy_version=raw["risk_policy_version"],
            initial_capital=raw["initial_capital"],
            dataset_hash=raw["dataset_hash"],
            development_period=period("development_period"),
            validation_period=period("validation_period"),
            final_holdout=period("final_holdout"),
            walk_forward_mode=raw["walk_forward_mode"],
            fold_count=raw["fold_count"],
            purge_seconds=raw["purge_seconds"],
            embargo_seconds=raw["embargo_seconds"],
            warmup_seconds=raw["warmup_seconds"],
            primary_metrics=tuple(raw["primary_metrics"]),
            secondary_metrics=tuple(raw["secondary_metrics"]),
            acceptance_policy_version=raw["acceptance_policy_version"],
            stress_scenarios=tuple(raw["stress_scenarios"]),
            sensitivity_spec={key: tuple(value) for key, value in raw["sensitivity_spec"].items()},
            statistical_procedures=tuple(raw["statistical_procedures"]),
            random_seeds=tuple(raw["random_seeds"]),
            permitted_candidate_ids=tuple(raw["permitted_candidate_ids"]),
            maximum_trials=raw["maximum_trials"],
            invalidation_conditions=tuple(raw["invalidation_conditions"]),
            finalized_at=parse_utc(raw["finalized_at"], "plan finalization time"),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("validation plan is malformed") from exc


def _atomic_text(path: Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if any(part in str(key).upper() for part in SENSITIVE_KEY_PARTS):
                raise ValidationError("candidate records cannot contain sensitive configuration")
            _reject_sensitive(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_sensitive(item)


@dataclass(frozen=True)
class ContaminatedArtifact:
    artifact_id: str
    category: str
    period: StudyPeriod | None
    parameter_configuration: str
    reason: str


@dataclass(frozen=True)
class ContaminationRegister:
    schema_version: int
    artifacts: tuple[ContaminatedArtifact, ...]
    source: str

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not self.source:
            raise ValidationError("unsupported contamination register")
        ids = [item.artifact_id for item in self.artifacts]
        if len(ids) != len(set(ids)):
            raise ValidationError("contamination artifact IDs must be unique")

    def overlaps(self, period: StudyPeriod) -> tuple[ContaminatedArtifact, ...]:
        return tuple(item for item in self.artifacts if item.period and item.period.overlaps(period))

    @classmethod
    def from_path(cls, path: Path) -> "ContaminationRegister":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        artifacts = []
        for item in raw["artifacts"]:
            period = None
            if item.get("start") and item.get("end"):
                period = StudyPeriod(
                    start=parse_utc(item["start"], "contamination start"),
                    end=parse_utc(item["end"], "contamination end"),
                    name=item["artifact_id"],
                )
            artifacts.append(ContaminatedArtifact(
                artifact_id=item["artifact_id"],
                category=item["category"],
                period=period,
                parameter_configuration=item["parameter_configuration"],
                reason=item["reason"],
            ))
        for cache_path in raw.get("cache_inventory", {}).get("paths", []):
            artifacts.append(ContaminatedArtifact(
                artifact_id=cache_path,
                category="LEGACY_CACHE_PICKLE",
                period=None,
                parameter_configuration="unknown cached market-data input",
                reason="previously available during strategy development; not holdout evidence",
            ))
        return cls(schema_version=raw["schema_version"], artifacts=tuple(artifacts), source=raw["source"])


def build_walk_forward_folds(plan: ValidationPlan) -> tuple[FoldManifest, ...]:
    validation_seconds = (plan.validation_period.end - plan.validation_period.start).total_seconds()
    usable_seconds = validation_seconds - plan.embargo_seconds * (plan.fold_count - 1)
    if usable_seconds <= 0:
        raise ValidationError("embargo consumes the validation period")
    evaluation_seconds = usable_seconds / plan.fold_count
    development_width = plan.development_period.end - plan.development_period.start
    folds = []
    evaluation_start = plan.validation_period.start
    for index in range(plan.fold_count):
        evaluation_end = (
            plan.validation_period.end
            if index == plan.fold_count - 1
            else evaluation_start + timedelta(seconds=evaluation_seconds)
        )
        training_end = evaluation_start - timedelta(seconds=plan.purge_seconds)
        if training_end <= plan.development_period.start:
            raise ValidationError("insufficient history before fold after purge")
        training_start = plan.development_period.start
        if plan.walk_forward_mode == "ROLLING":
            training_start = max(plan.development_period.start, training_end - development_width)
        warmup_start = max(training_start, evaluation_start - timedelta(seconds=plan.warmup_seconds))
        folds.append(FoldManifest(
            fold_id=f"fold-{index + 1:02d}",
            training=StudyPeriod(training_start, training_end, f"fold-{index + 1}-training"),
            warmup=StudyPeriod(warmup_start, evaluation_start, f"fold-{index + 1}-warmup"),
            evaluation=StudyPeriod(evaluation_start, evaluation_end, f"fold-{index + 1}-evaluation"),
            purge_seconds=plan.purge_seconds,
            embargo_seconds=plan.embargo_seconds,
        ))
        evaluation_start = evaluation_end + timedelta(seconds=plan.embargo_seconds)
    return tuple(folds)


def verify_frozen_candidate(
    plan: ValidationPlan,
    *,
    strategy_fingerprint: str,
    execution_fingerprint: str,
) -> Mapping[str, Any]:
    checks = {
        "strategy_fingerprint_matches": plan.strategy_fingerprint == strategy_fingerprint,
        "execution_fingerprint_matches": plan.execution_fingerprint == execution_fingerprint,
        "frozen_candidate_registered": "phase6-frozen-v1" in plan.permitted_candidate_ids,
        "phase4_risk_policy_preserved": plan.risk_policy_version == "phase4-validation-v1",
    }
    if not all(checks.values()):
        raise ValidationError("validation plan does not preserve the frozen initial candidate")
    return checks


class CandidateRegistry:
    def __init__(
        self,
        path: Path,
        *,
        maximum_trials: int,
        permitted_candidate_ids: tuple[str, ...] | None = None,
    ) -> None:
        if maximum_trials < 1:
            raise ValidationError("maximum trials must be positive")
        self.path = Path(path)
        self.maximum_trials = maximum_trials
        self.permitted_candidate_ids = frozenset(permitted_candidate_ids or ())
        self.lock = FileLock(str(self.path) + ".lock")

    def records(self) -> tuple[Mapping[str, Any], ...]:
        if not self.path.exists():
            return ()
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return tuple(records)

    def register(self, record: CandidateRecord) -> str:
        _reject_sensitive(record.parameter_difference)
        with self.lock:
            existing = self.records()
            if self.permitted_candidate_ids and record.candidate_id not in self.permitted_candidate_ids:
                raise ValidationError("candidate is not permitted by the preregistered plan")
            if any(item["candidate_id"] == record.candidate_id for item in existing):
                raise ValidationError("candidate ID is already registered")
            if record.parent_candidate_id and not any(
                item["candidate_id"] == record.parent_candidate_id for item in existing
            ):
                raise ValidationError("candidate parent is not registered")
            if len(existing) >= self.maximum_trials:
                raise ValidationError("preregistered trial limit has been reached")
            records = (*existing, canonical_data(record))
            _atomic_text(self.path, "".join(canonical_json(item) + "\n" for item in records))
        return canonical_hash(record)

    def disclosure(self) -> Mapping[str, Any]:
        count = len(self.records())
        return {
            "registered_trials": count,
            "maximum_trials": self.maximum_trials,
            "multiple_testing_required": count > 1,
            "bonferroni_alpha": None if count == 0 else 0.05 / count,
        }


class HoldoutLock:
    def __init__(self, lock_path: Path, access_log_path: Path) -> None:
        self.lock_path = Path(lock_path)
        self.access_log_path = Path(access_log_path)
        self.lock = FileLock(str(self.lock_path) + ".lock")

    def seal(self, identity: HoldoutIdentity, *, finalized_at: datetime) -> None:
        with self.lock:
            if self.lock_path.exists():
                current = json.loads(self.lock_path.read_text(encoding="utf-8"))
                if current["identity_hash"] != identity.identity_hash:
                    raise ValidationError("holdout lock already belongs to another study")
                return
            payload = {
                "schema_version": 1,
                "identity": canonical_data(identity),
                "identity_hash": identity.identity_hash,
                "sealed_at": canonical_data(utc_datetime(finalized_at, "holdout seal time")),
                "first_access_at": None,
                "first_access_candidate": None,
                "untouched": True,
            }
            _atomic_text(self.lock_path, json.dumps(payload, sort_keys=True, indent=2) + "\n")

    def _append_access(self, record: Mapping[str, Any]) -> None:
        existing = self.access_log_path.read_text(encoding="utf-8") if self.access_log_path.exists() else ""
        _atomic_text(self.access_log_path, existing + canonical_json(record) + "\n")

    def request_access(
        self,
        identity: HoldoutIdentity,
        report: AcceptanceReport,
        *,
        now: datetime,
        explicit: bool,
        justification: str,
        repeat_authorized: bool = False,
    ) -> bool:
        timestamp = utc_datetime(now, "holdout access time")
        with self.lock:
            if not self.lock_path.exists():
                raise ValidationError("holdout must be sealed before access")
            state = json.loads(self.lock_path.read_text(encoding="utf-8"))
            reason = "ACCESS_GRANTED"
            granted = True
            if state["first_access_at"] and state["first_access_candidate"] != identity.candidate_id:
                granted, reason = False, "CANDIDATE_CHANGED_AFTER_HOLDOUT"
                state["untouched"] = False
            elif state["identity_hash"] != identity.identity_hash:
                granted, reason = False, "HOLDOUT_IDENTITY_MISMATCH"
            elif report.package_hash != identity.dataset_hash:
                granted, reason = False, "DATASET_HASH_MISMATCH"
            elif report.synthetic_label:
                granted, reason = False, "SYNTHETIC_HOLDOUT_PROHIBITED"
            elif report.outcome is not AcceptanceOutcome.ACCEPTED_FOR_FINAL_VALIDATION:
                granted, reason = False, "DATASET_NOT_FINAL_VALIDATION_ACCEPTED"
            elif not explicit or not justification.strip():
                granted, reason = False, "EXPLICIT_ACCESS_REQUIRED"
            elif state["first_access_at"] and not repeat_authorized:
                granted, reason = False, "REPEAT_ACCESS_REQUIRES_AUTHORIZATION"
            elif state["first_access_at"]:
                reason = "REPEATED_ACCESS_GRANTED_AND_RECORDED"
            if granted and state["first_access_at"] is None:
                state["first_access_at"] = canonical_data(timestamp)
                state["first_access_candidate"] = identity.candidate_id
                state["untouched"] = False
            access = {
                "access_id": canonical_hash((
                    identity.identity_hash,
                    canonical_data(timestamp),
                    reason,
                    len(self.access_records()) + 1,
                )),
                "timestamp": timestamp,
                "identity_hash": identity.identity_hash,
                "candidate_id": identity.candidate_id,
                "granted": granted,
                "reason_code": reason,
                "justification": justification,
                "repeat_authorized": repeat_authorized,
            }
            self._append_access(access)
            _atomic_text(self.lock_path, json.dumps(canonical_data(state), sort_keys=True, indent=2) + "\n")
            return granted

    def access_records(self) -> tuple[Mapping[str, Any], ...]:
        if not self.access_log_path.exists():
            return ()
        return tuple(json.loads(line) for line in self.access_log_path.read_text(encoding="utf-8").splitlines() if line)
