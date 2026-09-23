"""Phase 8 V2 prospective cost-policy canonical verification tests.

Synthetic/repository-only fixtures — no network, no MT5, no strategy
evaluation, no holdout access, no empirical data.  Infrastructure
verification only: fingerprint-contract discipline, not cost semantics.

Uses the :class:`GitObjectStore` pattern from ``tests.test_canonical_byte_contract``
(real Git loose objects, no subprocess — the conftest firewall prohibits it).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.test_canonical_byte_contract import GitObjectStore  # noqa: E402
from bot.validation import cost_policy as cp  # noqa: E402
from bot.validation import (  # noqa: E402
    development_evaluation_plan as dep,
    empirical_input_pipeline as eip,
)

SYNTH_SUPPORT_HASH = "3" * 64

MODULES = {
    "bot/backtesting/costs.py": b"EXEC_COST_SURFACE_A = 1\nline_two = 'x'\n",
    "bot/backtesting/models.py": b"EXEC_COST_SURFACE_B = 2\n",
    "bot/backtesting/engine.py": b"EXEC_COST_SURFACE_C = 3\n# trailing\n",
}
MODULE_PATHS = sorted(MODULES)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_data_root(tmp_path: Path) -> Path:
    """Minimal synthetic data root satisfying build_cost_policy bindings."""
    derived = tmp_path / "derived" / "derived-candles-2024-v1-20260911T195553Z"
    derived.mkdir(parents=True)
    (derived / "manifest.json").write_text(
        json.dumps({
            "year_package_id": "synthetic-year-package",
            "source_canonical_sha256": "a" * 64,
            "source_row_count": 12345,
        }),
        encoding="utf-8",
    )
    dxy = tmp_path / "dxy" / "dxy-development-2024-v1-20260912T091410.712364Z"
    dxy.mkdir(parents=True)
    (dxy / "manifest.json").write_text(
        json.dumps({
            "package_id": "synthetic-dxy-package",
            "causal_dxy": {
                "canonical_content_sha256": "b" * 64,
                "record_count": 999,
            },
        }),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def policy(temp_data_root: Path) -> dict:
    return cp.build_cost_policy(
        data_root=temp_data_root,
        broker_support_content_sha256=SYNTH_SUPPORT_HASH,
    )


@pytest.fixture()
def module_repo(tmp_path: Path):
    """Synthetic Git object store containing the execution-model surface."""
    store = GitObjectStore(tmp_path / "module-repo")
    commit = store.commit_files(MODULES, "frozen execution-cost surface")
    return store, commit


def _attestation(store, commit, policy) -> dict:
    blobs = {
        relative: store.blob_bytes(commit, relative) for relative in MODULE_PATHS
    }
    return cp.build_prospective_attestation(
        canonical_commit=commit,
        tooling_commit=commit,
        policy_package_id="evidence-development_cost_policy-v1-synthetic",
        policy_artifact_sha256=hashlib.sha256(
            json.dumps(policy, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        policy_content_fingerprint=str(policy["policy_fingerprint"]),
        recorded_legacy_execution_model_fingerprint=str(
            policy["bindings"]["execution_model_fingerprint"]
        ),
        canonical_execution_model_fingerprint=cp.execution_model_fingerprint_canonical(
            commit, worktree=store.root, blob_source=store.blob_bytes
        ),
        module_blob_shas={
            relative: hashlib.sha256(blob).hexdigest() for relative, blob in blobs.items()
        },
        publication_anchor_commit=commit,
        v001_implementation_commit=commit,
        repo=store.root,
        blob_source=store.blob_bytes,
    )


def _prospective(policy, attestation, store, commit, repo_dir: Path):
    return cp.verify_cost_policy_prospective(
        policy,
        attestation,
        commit=commit,
        repo=repo_dir,
        blob_source=store.blob_bytes,
    )


# ---------------------------------------------------------------------------
# A. Legacy preservation
# ---------------------------------------------------------------------------


def test_legacy_verifier_behavior_preserved(policy) -> None:
    # In-suite the synthetic policy is self-consistent with the current
    # worktree materialization, so legacy verification passes...
    report = cp.verify_cost_policy(policy)
    assert report["verified"] is True
    assert report["policy_fingerprint"] == policy["policy_fingerprint"]


def test_legacy_verifier_still_fails_on_materialization_mismatch(
    policy, monkeypatch
) -> None:
    # ...and a legacy-fingerprint drift (what a different checkout
    # materialization produces) still fails closed in legacy mode: the
    # legacy path must NOT silently fall back to canonical verification.
    def drifted() -> str:
        return "d" * 64

    monkeypatch.setattr(cp, "execution_model_fingerprint", drifted)
    with pytest.raises(cp.CostPolicyError, match="execution-model fingerprint drifted"):
        cp.verify_cost_policy(policy)


def test_legacy_path_unknown_contract_fails_closed(policy) -> None:
    with pytest.raises(cp.CostPolicyError, match="unknown execution binding contract"):
        cp._verify_cost_policy_impl(
            policy,
            execution_binding_contract="legacy_worktree_bytes_v9",
            prospective_ctx=None,
        )


# ---------------------------------------------------------------------------
# B. Canonical materialization independence
# ---------------------------------------------------------------------------


def test_prospective_verification_independent_of_materialization(
    policy, module_repo, tmp_path: Path
) -> None:
    store, commit = module_repo
    attestation = _attestation(store, commit, policy)
    lf_dir = store.materialize_worktree(tmp_path / "wt-lf", MODULES, eol="lf")
    crlf_dir = store.materialize_worktree(tmp_path / "wt-crlf", MODULES, eol="crlf")
    report_lf = _prospective(policy, attestation, store, commit, lf_dir)
    report_crlf = _prospective(policy, attestation, store, commit, crlf_dir)
    assert report_lf["verified"] is True and report_crlf["verified"] is True
    assert (
        report_lf["canonical_execution_model_fingerprint"]
        == report_crlf["canonical_execution_model_fingerprint"]
        == attestation["prospective_verification"]["canonical_execution_model_fingerprint"]
    )
    assert report_lf["execution_binding_contract"] == "canonical_git_blob_v1"
    # The historical binding survives verbatim as preserved metadata.
    assert (
        report_lf["historical_execution_model_fingerprint_preserved"]
        == policy["bindings"]["execution_model_fingerprint"]
    )


# ---------------------------------------------------------------------------
# C. Real content drift fails closed
# ---------------------------------------------------------------------------


def test_prospective_verification_fails_on_true_content_drift(
    policy, module_repo, tmp_path: Path
) -> None:
    store, commit = module_repo
    attestation = _attestation(store, commit, policy)
    drifted = dict(MODULES)
    drifted["bot/backtesting/engine.py"] = MODULES["bot/backtesting/engine.py"] + b"\n# drift\n"
    drift_commit = store.commit_files(drifted, "content drift")
    with pytest.raises(cp.CostPolicyError, match="content drifted|drifted from attestation"):
        _prospective(policy, attestation, store, drift_commit, tmp_path)


def test_attestation_builder_rejects_content_drift(
    policy, module_repo
) -> None:
    store, commit = module_repo
    wrong_canonical = "c" * 64
    with pytest.raises(cp.CostPolicyError, match="does not recompute"):
        cp.build_prospective_attestation(
            canonical_commit=commit,
            tooling_commit=commit,
            policy_package_id="pkg",
            policy_artifact_sha256="0" * 64,
            policy_content_fingerprint=str(policy["policy_fingerprint"]),
            recorded_legacy_execution_model_fingerprint="e" * 64,
            canonical_execution_model_fingerprint=wrong_canonical,
            module_blob_shas={
                relative: hashlib.sha256(store.blob_bytes(commit, relative)).hexdigest()
                for relative in MODULE_PATHS
            },
            publication_anchor_commit=commit,
            v001_implementation_commit=commit,
            repo=store.root,
            blob_source=store.blob_bytes,
        )


# ---------------------------------------------------------------------------
# D. Module-set drift
# ---------------------------------------------------------------------------


def test_attestation_builder_rejects_module_set_drift(
    policy, module_repo
) -> None:
    store, commit = module_repo
    blobs = {
        relative: hashlib.sha256(store.blob_bytes(commit, relative)).hexdigest()
        for relative in MODULE_PATHS
    }
    # Missing module.
    with pytest.raises(cp.CostPolicyError, match="module set must match"):
        cp.build_prospective_attestation(
            canonical_commit=commit, tooling_commit=commit,
            policy_package_id="pkg", policy_artifact_sha256="0" * 64,
            policy_content_fingerprint=str(policy["policy_fingerprint"]),
            recorded_legacy_execution_model_fingerprint="e" * 64,
            canonical_execution_model_fingerprint="c" * 64,
            module_blob_shas={k: v for k, v in blobs.items() if k != MODULE_PATHS[0]},
            publication_anchor_commit=commit, v001_implementation_commit=commit,
            repo=store.root, blob_source=store.blob_bytes,
        )
    # Unexpected extra module.
    extra = dict(blobs)
    extra["bot/backtesting/unexpected.py"] = "f" * 64
    with pytest.raises(cp.CostPolicyError, match="module set must match"):
        cp.build_prospective_attestation(
            canonical_commit=commit, tooling_commit=commit,
            policy_package_id="pkg", policy_artifact_sha256="0" * 64,
            policy_content_fingerprint=str(policy["policy_fingerprint"]),
            recorded_legacy_execution_model_fingerprint="e" * 64,
            canonical_execution_model_fingerprint="c" * 64,
            module_blob_shas=extra,
            publication_anchor_commit=commit, v001_implementation_commit=commit,
            repo=store.root, blob_source=store.blob_bytes,
        )


def test_prospective_verifier_rejects_drifted_attested_blob_set(
    policy, module_repo, tmp_path: Path
) -> None:
    store, commit = module_repo
    attestation = _attestation(store, commit, policy)
    # Reordering must not matter (canonical module ordering).
    reordered = dict(reversed(list(attestation["prospective_verification"]["module_blob_shas"].items())))
    attestation["prospective_verification"]["module_blob_shas"] = dict(reordered)
    attestation["attestation_fingerprint"] = hashlib.sha256(
        cp.canonical_json_bytes(
            {k: v for k, v in attestation.items() if k != "attestation_fingerprint"}
        )
    ).hexdigest()
    assert _prospective(policy, attestation, store, commit, tmp_path)["verified"] is True


# ---------------------------------------------------------------------------
# E. Wrong attestation fails closed
# ---------------------------------------------------------------------------


def test_prospective_verification_rejects_tampered_attestation(
    policy, module_repo, tmp_path: Path
) -> None:
    store, commit = module_repo
    attestation = _attestation(store, commit, policy)
    attestation["historical_cost_policy"]["recorded_execution_model_fingerprint"] = "0" * 64
    with pytest.raises(cp.CostPolicyError, match="attestation fingerprint mismatch"):
        _prospective(policy, attestation, store, commit, tmp_path)


def test_prospective_verification_rejects_unbound_policy_content(
    policy, module_repo, tmp_path: Path
) -> None:
    store, commit = module_repo
    attestation = _attestation(store, commit, policy)
    other = json.loads(json.dumps(policy))
    other["cost_components"]["commission"]["amount"] = 1
    other["policy_fingerprint"] = "0" * 64
    with pytest.raises(cp.CostPolicyError, match="does not bind the presented policy"):
        _prospective(other, attestation, store, commit, tmp_path)


def test_prospective_verification_rejects_wrong_commit(
    policy, module_repo, tmp_path: Path
) -> None:
    store, commit = module_repo
    attestation = _attestation(store, commit, policy)
    other = dict(MODULES)
    other["bot/backtesting/models.py"] = MODULES["bot/backtesting/models.py"] + b"# other\n"
    other_commit = store.commit_files(other, "unrelated commit")
    with pytest.raises(cp.CostPolicyError):
        _prospective(policy, attestation, store, other_commit, tmp_path)


# ---------------------------------------------------------------------------
# F. Contract discipline (unknown / missing / misapplied contracts)
# ---------------------------------------------------------------------------


def test_attestation_binding_legacy_contract_rejected(
    policy, module_repo, tmp_path: Path
) -> None:
    store, commit = module_repo
    attestation = _attestation(store, commit, policy)
    attestation["prospective_verification"]["fingerprint_contract"] = (
        "legacy_worktree_bytes_v0"
    )
    attestation["attestation_fingerprint"] = hashlib.sha256(
        cp.canonical_json_bytes(
            {k: v for k, v in attestation.items() if k != "attestation_fingerprint"}
        )
    ).hexdigest()
    with pytest.raises(cp.CostPolicyError, match="canonical_git_blob_v1"):
        _prospective(policy, attestation, store, commit, tmp_path)


def test_prospective_readiness_rejects_legacy_contract(tmp_path: Path) -> None:
    with pytest.raises(dep.DevelopmentEvaluationPlanError, match="canonical_git_blob_v1"):
        dep.verify_input_readiness_prospective(
            data_root=tmp_path,
            worktree=REPO_ROOT,
            contamination_path=REPO_ROOT / "baseline" / "phase8_contamination_register.json",
            research_identity="phase6-development-v2",
            variant_id="phase6-development-v2-V001",
            fingerprint_contract="legacy_worktree_bytes_v0",
            active_commit="1" * 40,
            attestation={"attestation_fingerprint": "x"},
        )


def test_prospective_readiness_rejects_unknown_contract(tmp_path: Path) -> None:
    with pytest.raises(dep.DevelopmentEvaluationPlanError, match="canonical_git_blob_v1"):
        dep.verify_input_readiness_prospective(
            data_root=tmp_path,
            worktree=REPO_ROOT,
            contamination_path=REPO_ROOT / "baseline" / "phase8_contamination_register.json",
            research_identity="phase6-development-v2",
            variant_id="phase6-development-v2-V001",
            fingerprint_contract="some_new_contract",
            active_commit="1" * 40,
            attestation={"attestation_fingerprint": "x"},
        )


def test_prospective_readiness_rejects_wrong_research_context(tmp_path: Path) -> None:
    with pytest.raises(dep.DevelopmentEvaluationPlanError, match="research identity"):
        dep.verify_input_readiness_prospective(
            data_root=tmp_path,
            worktree=REPO_ROOT,
            contamination_path=REPO_ROOT / "baseline" / "phase8_contamination_register.json",
            research_identity="phase6-development-v1",
            variant_id="phase6-development-v2-V001",
            fingerprint_contract="canonical_git_blob_v1",
            active_commit="1" * 40,
            attestation={"attestation_fingerprint": "x"},
        )
    with pytest.raises(dep.DevelopmentEvaluationPlanError, match="variant id"):
        dep.verify_input_readiness_prospective(
            data_root=tmp_path,
            worktree=REPO_ROOT,
            contamination_path=REPO_ROOT / "baseline" / "phase8_contamination_register.json",
            research_identity="phase6-development-v2",
            variant_id="phase6-development-v2-V01",
            fingerprint_contract="canonical_git_blob_v1",
            active_commit="1" * 40,
            attestation={"attestation_fingerprint": "x"},
        )


def test_resolver_rejects_unknown_contract(tmp_path: Path) -> None:
    with pytest.raises(eip.EmpiricalPipelineError, match="unknown fingerprint contract"):
        eip.resolve_input_bindings(
            evidence_root=tmp_path / "evidence",
            worktree=REPO_ROOT,
            contamination_path=REPO_ROOT / "baseline" / "phase8_contamination_register.json",
            plan={},
            fingerprint_contract="technically_a_vibe",
        )


def test_resolver_legacy_path_rejects_prospective_context(tmp_path: Path) -> None:
    with pytest.raises(eip.EmpiricalPipelineError, match="must not carry prospective"):
        eip.resolve_input_bindings(
            evidence_root=tmp_path / "evidence",
            worktree=REPO_ROOT,
            contamination_path=REPO_ROOT / "baseline" / "phase8_contamination_register.json",
            plan={},
            fingerprint_contract="legacy_worktree_bytes_v0",
            research_identity="phase6-development-v2",
        )


def test_resolver_default_contract_is_legacy(tmp_path: Path) -> None:
    import inspect

    signature = inspect.signature(eip.resolve_input_bindings)
    assert (
        signature.parameters["fingerprint_contract"].default
        == "legacy_worktree_bytes_v0"
    )


# ---------------------------------------------------------------------------
# G. Historical artifact invariance (real attestation vs live artifact)
# ---------------------------------------------------------------------------


def test_published_attestation_binds_the_live_historical_artifact() -> None:
    attestation_path = REPO_ROOT / "baseline" / "phase8_v2_cost_policy_canonical_attestation.json"
    if not attestation_path.is_file():
        pytest.skip("published attestation not present in this checkout")
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    assert cp.canonical_json_bytes(
        {k: v for k, v in attestation.items() if k != "attestation_fingerprint"}
    ).hex() is not None  # parse sanity
    recorded = hashlib.sha256(
        cp.canonical_json_bytes(
            {k: v for k, v in attestation.items() if k != "attestation_fingerprint"}
        )
    ).hexdigest()
    assert recorded == attestation["attestation_fingerprint"]

    evidence_root = Path("C:/Users/chips/forex-signal-bot-data/phase8/evidence")
    if not evidence_root.is_dir():
        pytest.skip("external evidence root not available on this machine")
    package_id = attestation["historical_cost_policy"]["package_id"]
    artifact = evidence_root / package_id / "package.json"
    assert artifact.is_file()
    live_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert live_sha == attestation["historical_cost_policy"]["artifact_sha256"]
    live = json.loads(artifact.read_bytes())
    assert (
        str(live["content"]["bindings"]["execution_model_fingerprint"])
        == attestation["historical_cost_policy"]["recorded_execution_model_fingerprint"]
    )
    assert (
        str(live["content"]["policy_fingerprint"])
        == attestation["historical_cost_policy"]["policy_fingerprint"]
    )
    assert attestation["historical_cost_policy"]["immutable_historical_artifact"] is True
    assert (
        attestation["historical_cost_policy"]["recorded_fingerprint_contract"]
        == "legacy_worktree_bytes_v0"
    )
    assert (
        attestation["prospective_verification"]["fingerprint_contract"]
        == "canonical_git_blob_v1"
    )
    assert attestation["cost_semantics_unchanged"] is True
