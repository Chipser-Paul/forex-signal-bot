from copy import deepcopy
from pathlib import Path

import pytest

from bot.acquisition.evidence_contracts import canonical_hash
from bot.acquisition.evidence_store import build_evidence_package, publish_evidence_package
from bot.validation.development_metadata_bounds import SCENARIO_ORDER
from bot.validation.development_evaluation_plan import build_development_evaluation_plan
from bot.validation.development_plan_revision import CODE_COMPONENTS, build_revision, component_fingerprints, publish_revision, verify_revision
from tests.phase8m.test_development_evaluation_plan import _readiness


def _revision():
    readiness = _readiness()
    readiness["metadata_bounds"]["mandatory_scenarios"] = list(SCENARIO_ORDER)
    parent = build_development_evaluation_plan(readiness)
    proof = {"consumption_restart_passed": True, "live_offline_parity_passed": True,
             "scenario_cells_verified": 64, "unexpected_failures": 0, "unexpected_xpasses": 0,
             "empirical_execution": False}
    fingerprints = component_fingerprints(Path(__file__).resolve().parents[2])
    return parent, build_revision(parent, "synthetic-parent", fingerprints, proof=proof)


def test_revision_binds_unchanged_candidate_inputs_costs_folds_and_closed_gates():
    parent, revision = _revision()
    verify_revision(revision, parent)
    assert revision["supersedes"]["parent_status"] == "SUPERSEDED_BEFORE_EXECUTION"
    assert revision["scenario_cell_contract"]["cell_count"] == 64
    assert all(value is False for value in revision["gates"].values())


def test_append_only_publication_twice_is_idempotent_and_parent_unchanged(tmp_path):
    parent, revision = _revision()
    package, parent_id = build_evidence_package(kind="development_evaluation_plan", content=parent, source_path=None)
    publish_evidence_package(package, evidence_root=tmp_path)
    before = {path.name: path.read_bytes() for path in (tmp_path / parent_id).iterdir() if path.is_file()}
    revision["supersedes"]["package_id"] = parent_id
    revision["plan_fingerprint"] = canonical_hash({key: value for key, value in revision.items() if key != "plan_fingerprint"})
    first = publish_revision(tmp_path, parent_id, revision)
    assert first == publish_revision(tmp_path, parent_id, revision)
    after = {path.name: path.read_bytes() for path in (tmp_path / parent_id).iterdir() if path.is_file()}
    assert before == after


@pytest.mark.parametrize("key", ["candidate", "folds", "gates", "input_readiness", "scenario_cell_contract", "plan_fingerprint"])
def test_tampered_revision_rejected(key):
    parent, revision = _revision()
    revision[key] = "changed"
    with pytest.raises((ValueError, TypeError, KeyError)):
        verify_revision(revision, parent)


def test_incomplete_consumption_proof_cannot_build_frozen_plan():
    parent, revision = _revision()
    with pytest.raises(ValueError):
        build_revision(parent, "synthetic-parent", revision["orchestration_contract"]["fingerprints"], proof={})


def test_implementation_fingerprint_is_independent_of_checkout_newlines(tmp_path):
    root = Path(__file__).resolve().parents[2]
    for relative in {path for paths in CODE_COMPONENTS.values() for path in paths}:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        normalized = (root / relative).read_bytes().replace(b"\r\n", b"\n")
        target.write_bytes(normalized.replace(b"\n", b"\r\n"))
    assert component_fingerprints(root) == component_fingerprints(tmp_path)
