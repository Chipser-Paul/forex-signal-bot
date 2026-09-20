"""Metadata-only append-only invalidation and frozen-plan correction.

No datasets or workers are opened here. Timestamps belong to envelope
provenance, never to the semantic disposition identity.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Mapping

from bot.acquisition.evidence_contracts import canonical_hash
from bot.acquisition.evidence_store import build_evidence_package, load_evidence_package, publish_evidence_package
from bot.strategy.setup_consumption import RECOVERY_OUTCOME_SCHEMA
from bot.validation.development_plan_revision import build_revision, verify_revision


DISPOSITION_SCHEMA = "phase8nf.development-plan-disposition.v1"
CORRECTION_SCHEMA = "phase8n.superseding-development-plan.v2"
DEFECTIVE_COMMIT = "e3e9ac4f8bb99ece9c3364097cdfaf82af3e2fd7"
REGRESSION_PATH = "tests/phase8/test_recovery_outcomes.py"
DISCOVERY_TEST = REGRESSION_PATH + "::test_rejected_entry_cleanup_is_not_consumption"
DEFECT_REASON = "REJECTED_ENTRY_CLEANUP_STATE_MUTATION_MISCLASSIFIED_AS_CONSUMED_WITH_ZERO_CONSUMPTION_EVENTS"


def _digest(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("reviewed SHA256 fingerprint required")


def _package_id(kind: str, content: Mapping[str, Any]) -> str:
    return build_evidence_package(kind=kind, content=content, source_path=None)[1]


def regression_fingerprint(worktree: Path) -> str:
    return hashlib.sha256((Path(worktree) / REGRESSION_PATH).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build_disposition(faulty: Mapping[str, Any], faulty_package_id: str) -> dict[str, Any]:
    if faulty_package_id != _package_id("development_evaluation_plan", faulty):
        raise ValueError("faulty plan package identity mismatch")
    if any(value is not False for value in faulty["gates"].values()):
        raise ValueError("invalidation requires a never-authorized plan")
    content = {
        "schema_version": DISPOSITION_SCHEMA, "classification": "INVALIDATED_BEFORE_EXECUTION",
        "package_id": faulty_package_id, "old_fingerprint": faulty["plan_fingerprint"],
        "defective_code_commit": DEFECTIVE_COMMIT, "defect_reason": DEFECT_REASON,
        "discovery_test": DISCOVERY_TEST, "discovery_result": "FAILED_ON_EXACT_DEFECTIVE_COMMIT",
        "empirical_cells_executed": 0, "empirical_execution": False,
        "original_package_mutated": False, "timestamp_policy": "ENVELOPE_PROVENANCE_ONLY",
    }
    return {**content, "disposition_fingerprint": canonical_hash(content)}


def build_corrected_revision(original: Mapping[str, Any], faulty: Mapping[str, Any],
                             faulty_package_id: str, fingerprints: Mapping[str, str], *,
                             regression_sha256: str, proof: Mapping[str, Any]) -> dict[str, Any]:
    verify_revision(faulty, original)
    _digest(regression_sha256)
    _digest(proof.get("correction_code_sha256"))
    for value in fingerprints.values():
        _digest(value)
    if proof.get("recovery_outcomes_passed") is not True or proof.get("recovery_regressions_passed", 0) < 23:
        raise ValueError("corrected aggregate recovery proof required")
    disposition = build_disposition(faulty, faulty_package_id)
    original_package_id = _package_id("development_evaluation_plan", original)
    if faulty["supersedes"]["package_id"] != original_package_id:
        raise ValueError("frozen original package relationship mismatch")
    corrected = build_revision(original, original_package_id, fingerprints, proof=proof)
    corrected.update({
        "schema_version": CORRECTION_SCHEMA, "plan_id": "phase8nf.development-evaluation-plan.v3",
        "invalidates": {
            "package_id": faulty_package_id, "fingerprint": faulty["plan_fingerprint"],
            "status": "INVALIDATED_BEFORE_EXECUTION",
            "disposition_package_id": _package_id("development_plan_disposition", disposition),
            "disposition_fingerprint": disposition["disposition_fingerprint"],
            "defective_code_commit": DEFECTIVE_COMMIT, "original_package_mutated": False,
        },
        "recovery_outcome_contract": {
            "schema": RECOVERY_OUTCOME_SCHEMA, "regression_sha256": regression_sha256,
            "publication_code_sha256": proof["correction_code_sha256"],
            "regression_test": DISCOVERY_TEST,
            "dimensions": ["state_changed", "consumption_applied", "consumption_already_present",
                           "binding_released", "reconciliation_required", "outcome"],
            "consumed_requires": "AUTHORITATIVE_POSITIVE_ENTRY_FILL_AND_APPLIED_CONSUMPTION",
            "rejected_unfilled": "UNRELATED_FILL_IGNORED",
            "matched_consumption_replay": "DUPLICATE_IGNORED",
            "aggregate_priority": ["STATE_CORRUPT", "IDENTITY_MISMATCH_BLOCKED", "UNCERTAIN_BLOCKED",
                                   "CONSUMED", "UNRELATED_FILL_IGNORED", "DUPLICATE_IGNORED"],
        },
        "prior_implementation_fingerprints": deepcopy(faulty["orchestration_contract"]["fingerprints"]),
    })
    corrected["plan_fingerprint"] = canonical_hash({key: value for key, value in corrected.items() if key != "plan_fingerprint"})
    return corrected


def verify_corrected_revision(corrected: Mapping[str, Any], original: Mapping[str, Any],
                              faulty: Mapping[str, Any]) -> None:
    expected = build_corrected_revision(original, faulty, corrected["invalidates"]["package_id"],
        corrected["orchestration_contract"]["fingerprints"],
        regression_sha256=corrected["recovery_outcome_contract"]["regression_sha256"],
        proof=corrected["synthetic_acceptance_proof"])
    if dict(corrected) != expected:
        raise ValueError("corrected frozen plan contract mismatch")


def _files(directory: Path) -> dict[str, str]:
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("PUBLISHED", "manifest.json", "manifest.sha256", "package.json")}


def publish_correction(evidence_root: Path, corrected: Mapping[str, Any], *, recorded_at: datetime) -> dict[str, Any]:
    if recorded_at.tzinfo is None:
        raise ValueError("disposition provenance timestamp must be aware")
    root = Path(evidence_root)
    faulty_id = corrected["invalidates"]["package_id"]
    original_id = corrected["supersedes"]["package_id"]
    # Read only the two exact frozen metadata packages, not their data sources.
    originals = {identity: _files(root / identity) for identity in (original_id, faulty_id)}
    original = load_evidence_package(root / original_id)["content"]
    faulty = load_evidence_package(root / faulty_id)["content"]
    verify_corrected_revision(corrected, original, faulty)
    disposition = build_disposition(faulty, faulty_id)
    envelope, disposition_id = build_evidence_package(kind="development_plan_disposition", content=disposition, source_path=None)
    envelope["manifest"]["recorded_at_utc"] = recorded_at.astimezone(timezone.utc).isoformat()
    publish_evidence_package(envelope, evidence_root=root)
    if load_evidence_package(root / disposition_id)["content"] != disposition:
        raise ValueError("published invalidation evidence mismatch")
    envelope, corrected_id = build_evidence_package(kind="development_evaluation_plan", content=corrected, source_path=None)
    publish_evidence_package(envelope, evidence_root=root)
    if load_evidence_package(root / corrected_id)["content"] != dict(corrected):
        raise ValueError("published corrected plan mismatch")
    if originals != {identity: _files(root / identity) for identity in originals}:
        raise ValueError("immutable predecessor package changed")
    return {"disposition_package_id": disposition_id, "package_id": corrected_id,
            "plan_fingerprint": corrected["plan_fingerprint"], "predecessor_file_hashes": originals}
