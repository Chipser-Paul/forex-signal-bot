from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from bot.validation.models import CandidateRecord, HoldoutIdentity, StudyPeriod, ValidationError
from bot.validation.study import (
    CandidateRegistry,
    ContaminationRegister,
    HoldoutLock,
    build_walk_forward_folds,
    verify_frozen_candidate,
)

from .helpers import accepted_report, plan


UTC = timezone.utc
NOW = datetime(2024, 1, 2, tzinfo=UTC)


def candidate(identifier: str, *, final: bool = False) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=identifier,
        parent_candidate_id=None,
        parameter_difference={},
        reason="frozen Phase 6 candidate",
        dataset_periods_accessed=("development",),
        metrics_examined=("net_expectancy",),
        seed=8001,
        registered_at=NOW,
        outcome="REGISTERED",
        rejection_reason=None,
        final_holdout_accessed=final,
    )


def identity(study_plan, candidate_id: str = "phase6-frozen-v1") -> HoldoutIdentity:
    return HoldoutIdentity(
        dataset_hash=study_plan.dataset_hash,
        period=study_plan.final_holdout,
        strategy_fingerprint=study_plan.strategy_fingerprint,
        execution_fingerprint=study_plan.execution_fingerprint,
        validation_plan_hash=study_plan.plan_hash,
        candidate_id=candidate_id,
    )


@pytest.mark.parametrize("mode", ["ANCHORED", "ROLLING"])
def test_walk_forward_folds_are_chronological_with_purge_embargo_and_warmup(mode):
    folds = build_walk_forward_folds(plan(mode=mode))
    assert len(folds) == 4
    for index, fold in enumerate(folds):
        assert fold.training.end.timestamp() + fold.purge_seconds <= fold.evaluation.start.timestamp()
        assert fold.warmup.end == fold.evaluation.start
        assert fold.warmup.start >= fold.training.start
        if index:
            assert fold.evaluation.start.timestamp() - folds[index - 1].evaluation.end.timestamp() == fold.embargo_seconds
    assert len({fold.manifest_hash for fold in folds}) == 4


def test_validation_plan_is_hashed_and_rejects_overlapping_periods():
    study_plan = plan()
    assert study_plan.plan_hash == study_plan.plan_hash
    with pytest.raises(ValidationError, match="development"):
        replace(study_plan, validation_period=StudyPeriod(
            datetime(2020, 12, 1, tzinfo=UTC), datetime(2022, 1, 1, tzinfo=UTC), "bad"
        ))


def test_frozen_strategy_execution_and_risk_fingerprints_are_verified():
    study_plan = plan()
    checks = verify_frozen_candidate(
        study_plan,
        strategy_fingerprint=study_plan.strategy_fingerprint,
        execution_fingerprint=study_plan.execution_fingerprint,
    )
    assert all(checks.values())
    with pytest.raises(ValidationError, match="frozen"):
        verify_frozen_candidate(
            replace(study_plan, strategy_fingerprint="changed"),
            strategy_fingerprint=study_plan.strategy_fingerprint,
            execution_fingerprint=study_plan.execution_fingerprint,
        )


def test_candidate_registry_is_append_only_and_discloses_multiple_testing(tmp_path):
    registry = CandidateRegistry(tmp_path / "candidates.jsonl", maximum_trials=2)
    first_hash = registry.register(candidate("phase6-frozen-v1"))
    assert len(first_hash) == 64
    registry.register(candidate("candidate-2"))
    disclosure = registry.disclosure()
    assert disclosure["registered_trials"] == 2
    assert disclosure["multiple_testing_required"] is True
    assert disclosure["bonferroni_alpha"] == pytest.approx(0.025)
    with pytest.raises(ValidationError, match="already"):
        registry.register(candidate("candidate-2"))
    with pytest.raises(ValidationError, match="limit"):
        registry.register(candidate("candidate-3"))


def test_candidate_registry_rejects_sensitive_parameter_fields(tmp_path):
    registry = CandidateRegistry(tmp_path / "candidates.jsonl", maximum_trials=2)
    unsafe = replace(candidate("unsafe"), parameter_difference={"api" + "_key": "prohibited"})
    with pytest.raises(ValidationError, match="sensitive"):
        registry.register(unsafe)


def test_candidate_registry_enforces_preregistered_candidates_and_parentage(tmp_path):
    registry = CandidateRegistry(
        tmp_path / "candidates.jsonl",
        maximum_trials=2,
        permitted_candidate_ids=("phase6-frozen-v1", "candidate-2"),
    )
    with pytest.raises(ValidationError, match="not permitted"):
        registry.register(candidate("unregistered-choice"))
    orphan = replace(candidate("candidate-2"), parent_candidate_id="missing-parent")
    with pytest.raises(ValidationError, match="parent"):
        registry.register(orphan)
    registry.register(candidate("phase6-frozen-v1"))
    registry.register(replace(candidate("candidate-2"), parent_candidate_id="phase6-frozen-v1"))
    assert len(registry.records()) == 2


def test_contamination_register_contains_all_results_and_current_caches():
    register = ContaminationRegister.from_path(
        __import__("pathlib").Path(__file__).resolve().parents[2] / "baseline" / "phase8_contamination_register.json"
    )
    results = [item for item in register.artifacts if item.category == "LEGACY_RESULT"]
    caches = [item for item in register.artifacts if item.category == "LEGACY_CACHE_PICKLE"]
    assert len(results) == 16
    assert len(caches) == 48
    overlap = register.overlaps(StudyPeriod(
        datetime(2026, 4, 1, tzinfo=UTC), datetime(2026, 5, 1, tzinfo=UTC), "candidate"
    ))
    assert overlap


def test_synthetic_fixture_cannot_unlock_holdout_and_attempts_are_recorded(tmp_path):
    study_plan = plan(dataset_hash="synthetic-hash")
    lock = HoldoutLock(tmp_path / "holdout.json", tmp_path / "holdout_access.jsonl")
    held = identity(study_plan)
    lock.seal(held, finalized_at=NOW)
    report = accepted_report(package_hash=held.dataset_hash, synthetic=True)
    assert lock.request_access(held, report, now=NOW, explicit=True, justification="test") is False
    assert lock.request_access(held, report, now=NOW, explicit=True, justification="test again") is False
    records = lock.access_records()
    assert len(records) == 2
    assert len({item["access_id"] for item in records}) == 2
    assert {item["reason_code"] for item in records} == {"SYNTHETIC_HOLDOUT_PROHIBITED"}


def test_holdout_requires_explicit_access_and_matching_identity(tmp_path):
    study_plan = plan(dataset_hash="empirical-package-hash")
    lock = HoldoutLock(tmp_path / "holdout.json", tmp_path / "holdout_access.jsonl")
    held = identity(study_plan)
    lock.seal(held, finalized_at=NOW)
    report = accepted_report(package_hash=held.dataset_hash, synthetic=False)
    assert lock.request_access(held, report, now=NOW, explicit=False, justification="") is False
    changed = replace(held, candidate_id="changed-after-plan")
    assert lock.request_access(changed, report, now=NOW, explicit=True, justification="invalid candidate") is False
    reasons = [item["reason_code"] for item in lock.access_records()]
    assert reasons == ["EXPLICIT_ACCESS_REQUIRED", "HOLDOUT_IDENTITY_MISMATCH"]


def test_first_access_and_repeats_are_visible_in_registry(tmp_path):
    study_plan = plan(dataset_hash="empirical-package-hash")
    lock = HoldoutLock(tmp_path / "holdout.json", tmp_path / "holdout_access.jsonl")
    held = identity(study_plan)
    lock.seal(held, finalized_at=NOW)
    report = accepted_report(package_hash=held.dataset_hash, synthetic=False)
    assert lock.request_access(held, report, now=NOW, explicit=True, justification="owner-authorized final evaluation")
    changed = replace(held, candidate_id="candidate-after-access")
    assert not lock.request_access(changed, report, now=NOW, explicit=True, justification="invalid change")
    assert not lock.request_access(held, report, now=NOW, explicit=True, justification="repeat")
    assert lock.request_access(held, report, now=NOW, explicit=True, justification="audited rerun", repeat_authorized=True)
    assert [item["reason_code"] for item in lock.access_records()] == [
        "ACCESS_GRANTED", "CANDIDATE_CHANGED_AFTER_HOLDOUT",
        "REPEAT_ACCESS_REQUIRES_AUTHORIZATION", "REPEATED_ACCESS_GRANTED_AND_RECORDED"
    ]
