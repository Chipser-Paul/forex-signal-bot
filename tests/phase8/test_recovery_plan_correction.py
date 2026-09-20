from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path

import pytest

from bot.acquisition.evidence_contracts import canonical_hash
from bot.acquisition.evidence_store import build_evidence_package, load_evidence_package, publish_evidence_package
from bot.validation.development_plan_revision import build_revision
from bot.validation.recovery_plan_correction import (
    build_corrected_revision, build_disposition, publish_correction, regression_fingerprint,
    verify_corrected_revision,
)
from tests.phase8.test_development_plan_revision import _revision


def _correction(tmp_path):
    original, faulty = _revision()
    envelope, original_id = build_evidence_package(kind="development_evaluation_plan", content=original, source_path=None)
    publish_evidence_package(envelope, evidence_root=tmp_path)
    faulty = build_revision(original, original_id, faulty["orchestration_contract"]["fingerprints"], proof=faulty["synthetic_acceptance_proof"])
    envelope, faulty_id = build_evidence_package(kind="development_evaluation_plan", content=faulty, source_path=None)
    publish_evidence_package(envelope, evidence_root=tmp_path)
    root = Path(__file__).resolve().parents[2]
    proof = {**faulty["synthetic_acceptance_proof"], "recovery_outcomes_passed": True,
             "recovery_regressions_passed": 23,
             "correction_code_sha256": hashlib.sha256((root / "bot/validation/recovery_plan_correction.py").read_bytes().replace(b"\r\n", b"\n")).hexdigest()}
    corrected = build_corrected_revision(original, faulty, faulty_id,
        faulty["orchestration_contract"]["fingerprints"], regression_sha256=regression_fingerprint(root), proof=proof)
    return original, faulty, corrected


def test_correction_preserves_frozen_inputs_and_64_cells_with_all_gates_closed(tmp_path):
    original, faulty, corrected = _correction(tmp_path)
    verify_corrected_revision(corrected, original, faulty)
    for key in ("candidate", "input_readiness", "cost_scenarios", "metadata_scenarios", "folds", "gates"):
        assert corrected[key] == original[key]
    assert corrected["scenario_matrix"] == faulty["scenario_matrix"]
    assert corrected["scenario_cell_contract"]["cell_count"] == 64
    assert all(value is False for value in corrected["gates"].values())
    assert corrected["plan_fingerprint"] != faulty["plan_fingerprint"]
    assert corrected["invalidates"]["status"] == "INVALIDATED_BEFORE_EXECUTION"
    assert corrected["prior_implementation_fingerprints"] == faulty["orchestration_contract"]["fingerprints"]


def test_disposition_timestamp_is_provenance_only_and_publication_is_append_only(tmp_path):
    original, faulty, corrected = _correction(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.glob("*/*") if path.is_file()}
    first = publish_correction(tmp_path, corrected, recorded_at=datetime(2026, 9, 16, tzinfo=timezone.utc))
    disposition_dir = tmp_path / first["disposition_package_id"]
    first_bytes = {path: path.read_bytes() for path in disposition_dir.iterdir()}
    assert first == publish_correction(tmp_path, corrected, recorded_at=datetime(2026, 9, 17, tzinfo=timezone.utc))
    assert first_bytes == {path: path.read_bytes() for path in disposition_dir.iterdir()}
    assert before == {path: path.read_bytes() for path in before}
    package = load_evidence_package(disposition_dir)
    assert package["manifest"]["recorded_at_utc"].startswith("2026-09-16")
    assert "recorded_at_utc" not in package["content"]
    assert package["content"]["empirical_cells_executed"] == 0
    assert package["content"] == build_disposition(faulty, corrected["invalidates"]["package_id"])


@pytest.mark.parametrize("key", ["candidate", "gates", "folds", "invalidates", "recovery_outcome_contract",
    "prior_implementation_fingerprints", "scenario_cell_contract", "plan_fingerprint"])
def test_tampering_rejected_even_with_recomputed_fingerprint(tmp_path, key):
    original, faulty, corrected = _correction(tmp_path)
    corrupted = deepcopy(corrected)
    corrupted[key] = {} if isinstance(corrected[key], dict) else "tampered"
    if key != "plan_fingerprint":
        corrupted["plan_fingerprint"] = canonical_hash({name: value for name, value in corrupted.items() if name != "plan_fingerprint"})
    with pytest.raises((ValueError, KeyError, TypeError)):
        verify_corrected_revision(corrupted, original, faulty)


def test_missing_recovery_proof_or_false_package_identity_cannot_publish(tmp_path):
    original, faulty, corrected = _correction(tmp_path)
    proof = dict(corrected["synthetic_acceptance_proof"])
    proof["recovery_outcomes_passed"] = False
    with pytest.raises(ValueError):
        build_corrected_revision(original, faulty, corrected["invalidates"]["package_id"],
            corrected["orchestration_contract"]["fingerprints"],
            regression_sha256=corrected["recovery_outcome_contract"]["regression_sha256"], proof=proof)
    with pytest.raises(ValueError, match="identity"):
        build_disposition(faulty, "incorrect-package")
    with pytest.raises(ValueError, match="aware"):
        publish_correction(tmp_path, corrected, recorded_at=datetime(2026, 9, 16))
