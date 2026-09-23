"""V001 prospective-readiness completion regression tests.

Infrastructure verification only — synthetic fixtures, repository-only.
No empirical access, no strategy evaluation, no profitability.

These regressions were produced by supervisory review of commit
``bf1196a`` and fail against that revision:

* the readiness tail recomputed the legacy execution-model fingerprint
  unconditionally (the exact LF/CRLF representation defect V001 hit);
* the historical cost-policy package identity was recorded in the
  attestation but not enforced by the readiness layer;
* the attestation bound a single ``canonical_commit`` with no
  anchor/active distinction (stale-commit evasion).

Covers the required matrix: legacy preservation, LF/CRLF materialization
independence through the COMPLETE readiness path, active-commit content
drift, exact historical artifact identity, module-surface fail-closed
cases, and contract discipline.
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


MODULES = {
    "bot/backtesting/costs.py": b"EXEC_SURFACE_A = 1\nline = 'x'\n",
    "bot/backtesting/models.py": b"EXEC_SURFACE_B = 2\n",
    "bot/backtesting/engine.py": b"EXEC_SURFACE_C = 3\n",
}
MODULE_PATHS = sorted(MODULES)


# ---------------------------------------------------------------------------
# Synthetic Git-fixture infrastructure
# ---------------------------------------------------------------------------


@pytest.fixture()
def module_repo(tmp_path: Path):
    """Commit A: execution-model blobs matching the frozen surface."""
    store = GitObjectStore(tmp_path / "lineage-repo")
    commit_a = store.commit_files(MODULES, "attested execution-cost surface")
    return store, commit_a


def _infra_descendant(store, commit_a: str) -> str:
    """Infrastructure-only descendant: identical execution-model blobs."""
    files = dict(MODULES)
    files["docs/note.md"] = b"infrastructure-only change\n"
    return store.commit_files(files, "infrastructure-only commit")


def _drifted_descendant(store, commit_a: str) -> str:
    """Commit B: real execution-model content drift."""
    files = dict(MODULES)
    files["bot/backtesting/engine.py"] = (
        MODULES["bot/backtesting/engine.py"] + b"\n# REAL DRIFT\n"
    )
    return store.commit_files(files, "execution-model drift")


def _cost_artifact_bytes(policy: dict) -> bytes:
    return json.dumps(
        {
            "manifest": {
                "package_id": dep.COST_POLICY_ID,
                "kind": "development_cost_policy",
                "content_canonical_sha256": "3" * 64,
            },
            "content": policy,
        },
        sort_keys=True,
    ).encode("utf-8")


def _attestation_for(store, anchor_commit: str, policy: dict) -> dict:
    blobs = {
        relative: hashlib.sha256(store.blob_bytes(anchor_commit, relative)).hexdigest()
        for relative in MODULE_PATHS
    }
    return cp.build_prospective_attestation(
        canonical_commit=anchor_commit,
        tooling_commit=anchor_commit,
        policy_package_id=dep.COST_POLICY_ID,
        policy_artifact_sha256=hashlib.sha256(_cost_artifact_bytes(policy)).hexdigest(),
        policy_content_fingerprint=str(policy["policy_fingerprint"]),
        recorded_legacy_execution_model_fingerprint=str(
            policy["bindings"]["execution_model_fingerprint"]
        ),
        canonical_execution_model_fingerprint=cp.execution_model_fingerprint_canonical(
            anchor_commit, worktree=store.root, blob_source=store.blob_bytes
        ),
        module_blob_shas=blobs,
        publication_anchor_commit=anchor_commit,
        v001_implementation_commit=anchor_commit,
        repo=store.root,
        blob_source=store.blob_bytes,
    )


# ---------------------------------------------------------------------------
# §12 — the COMPLETE prospective readiness path succeeds under
# representation drift (would fail at bf1196a: the readiness tail called
# execution_model_fingerprint() unconditionally).
# ---------------------------------------------------------------------------


def test_complete_prospective_readiness_reproves_lf_crlf_fix(
    module_repo, tmp_path: Path, monkeypatch
) -> None:
    store, commit_a = module_repo
    policy = _synthetic_policy_with_bindings(store, commit_a)
    attestation = _attestation_for(store, commit_a, policy)

    _make_input_roots(tmp_path)
    stub = _ReadyStub(policy, store, commit_a)
    # The conftest firewall forbids subprocess launches; point the cost
    # policy's blob source at the fixture object store (same contract,
    # no external process).
    monkeypatch.setattr(cp, "make_git_blob_source", lambda repo: store.blob_bytes)
    monkeypatch.setattr(dep, "verify_year_package_identity_chain", stub.verify_ticks)
    monkeypatch.setattr(dep, "verify_candles", stub.verify_candles)
    monkeypatch.setattr(dep, "verify_dxy", stub.verify_dxy)
    monkeypatch.setattr(dep, "_load_evidence", stub.load_evidence)
    monkeypatch.setattr(
        dep, "verify_development_metadata_bounds", lambda content: None
    )
    monkeypatch.setattr(dep.ContaminationRegister, "from_path", stub.contamination)
    monkeypatch.setattr(dep, "_sha256_file", lambda path: "0" * 64)

    # The historical binding carries the LEGACY (CRLF-era) fingerprint while
    # this clone's materialization differs; the committed canonical blobs
    # match the attestation.  Legacy mode must fail; prospective must pass.
    def drifted_legacy() -> str:
        return "d" * 64

    monkeypatch.setattr(cp, "execution_model_fingerprint", drifted_legacy)

    # Legacy mode must still fail under representation drift (the historical
    # verifier fails closed inside the policy verification itself; post-fix
    # the tail no longer recomputes the legacy fingerprint unconditionally).
    with pytest.raises((dep.DevelopmentEvaluationPlanError, cp.CostPolicyError)):
        dep.verify_input_readiness(
            data_root=tmp_path,
            worktree=REPO_ROOT,
            contamination_path=tmp_path / "contamination.json",
        )

    report = dep.verify_input_readiness_prospective(
        data_root=tmp_path,
        worktree=REPO_ROOT,
        contamination_path=tmp_path / "contamination.json",
        research_identity="phase6-development-v2",
        variant_id="phase6-development-v2-V001",
        fingerprint_contract="canonical_git_blob_v1",
        active_commit=commit_a,
        attestation=attestation,
    )
    fingerprints = report["fingerprints"]
    assert fingerprints["execution_contract"] == "canonical_git_blob_v1"
    assert fingerprints["execution"] == attestation["prospective_verification"][
        "canonical_execution_model_fingerprint"
    ]
    assert (
        fingerprints["historical_execution_legacy"]
        == policy["bindings"]["execution_model_fingerprint"]
    )
    # The LF worktree legacy hash must never appear as the live identity.
    assert fingerprints["execution"] != drifted_legacy()
    assert report["active_commit"] == commit_a
    assert report["historical_identity"]["cost_policy_package_id"] == dep.COST_POLICY_ID
    assert (
        report["historical_identity"]["cost_policy_artifact_sha256"]
        == attestation["historical_cost_policy"]["artifact_sha256"]
    )
    assert report["prospective_binding"]["fingerprint_contract"] == (
        "canonical_git_blob_v1"
    )


# ---------------------------------------------------------------------------
# §13 — legacy readiness still fails under the same drift (no fallback).
# (Covered inside the test above via the legacy assertion; the standalone
# legacy verifier case remains in test_phase8_v2_cost_policy_canonical.py.)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# §14 — active-commit semantics: anchor provenance, active verification.
# ---------------------------------------------------------------------------


def test_active_infra_descendant_passes_and_drift_fails(
    module_repo, tmp_path: Path, monkeypatch
) -> None:
    store, commit_a = module_repo
    policy = _synthetic_policy_with_bindings(store, commit_a)
    attestation = _attestation_for(store, commit_a, policy)
    infra = _infra_descendant(store, commit_a)
    drift = _drifted_descendant(store, commit_a)

    _make_input_roots(tmp_path)
    stub = _ReadyStub(policy, store, commit_a)
    # The conftest firewall forbids subprocess launches; point the cost
    # policy's blob source at the fixture object store (same contract,
    # no external process).
    monkeypatch.setattr(cp, "make_git_blob_source", lambda repo: store.blob_bytes)
    monkeypatch.setattr(dep, "verify_year_package_identity_chain", stub.verify_ticks)
    monkeypatch.setattr(dep, "verify_candles", stub.verify_candles)
    monkeypatch.setattr(dep, "verify_dxy", stub.verify_dxy)
    monkeypatch.setattr(dep, "_load_evidence", stub.load_evidence)
    monkeypatch.setattr(
        dep, "verify_development_metadata_bounds", lambda content: None
    )
    monkeypatch.setattr(dep.ContaminationRegister, "from_path", stub.contamination)
    monkeypatch.setattr(dep, "_sha256_file", lambda path: "0" * 64)

    def drifted_legacy() -> str:
        return "d" * 64

    monkeypatch.setattr(cp, "execution_model_fingerprint", drifted_legacy)

    common = dict(
        data_root=tmp_path,
        worktree=REPO_ROOT,
        contamination_path=tmp_path / "contamination.json",
        research_identity="phase6-development-v2",
        variant_id="phase6-development-v2-V001",
        fingerprint_contract="canonical_git_blob_v1",
        attestation=attestation,
    )

    # Active = anchor itself: PASS.
    report = dep.verify_input_readiness_prospective(active_commit=commit_a, **common)
    assert report["fingerprints"]["execution"] == attestation["prospective_verification"][
        "canonical_execution_model_fingerprint"
    ]

    # Infrastructure-only descendant: PASS (identical execution blobs).
    report = dep.verify_input_readiness_prospective(active_commit=infra, **common)
    assert report["fingerprints"]["execution"] == attestation["prospective_verification"][
        "canonical_execution_model_fingerprint"
    ]

    # Real module drift at the active commit: FAIL.
    with pytest.raises(Exception, match="drifted"):
        dep.verify_input_readiness_prospective(active_commit=drift, **common)

    # Stale-anchor evasion: declaring the drifted commit as active with the
    # anchor's attestation must not pass.
    with pytest.raises(Exception, match="drifted"):
        dep.verify_input_readiness_prospective(
            active_commit=drift,
            **{**common, "attestation": attestation},
        )


# ---------------------------------------------------------------------------
# §15 — exact historical artifact identity enforcement.
# ---------------------------------------------------------------------------


def test_prospective_readiness_enforces_historical_identity_exact(
    module_repo, tmp_path: Path, monkeypatch
) -> None:
    """The REAL historical package passes the identity gate."""
    evidence_root = Path("C:/Users/chips/forex-signal-bot-data/phase8/evidence")
    if not evidence_root.is_dir():
        pytest.skip("external evidence root not available")
    package_dir = evidence_root / dep.COST_POLICY_ID
    if not (package_dir / "package.json").is_file():
        pytest.skip("historical cost policy not present")
    attestation_path = REPO_ROOT / "baseline" / "phase8_v2_cost_policy_canonical_attestation.json"
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    package = dep._load_evidence(evidence_root, dep.COST_POLICY_ID, "development_cost_policy")
    sha = dep._verify_prospective_historical_identity(
        evidence_root=evidence_root,
        package_id=dep.COST_POLICY_ID,
        content=package["content"],
        attestation=attestation,
    )
    assert sha == attestation["historical_cost_policy"]["artifact_sha256"]


def test_prospective_identity_rejects_wrong_package_id(module_repo, tmp_path: Path) -> None:
    store, commit_a = module_repo
    policy = _synthetic_policy_with_bindings(store, commit_a)
    attestation = _attestation_for(store, commit_a, policy)
    with pytest.raises(dep.DevelopmentEvaluationPlanError, match="package id does not match"):
        dep._verify_prospective_historical_identity(
            evidence_root=tmp_path,
            package_id="evidence-development_cost_policy-v1-other",
            content=policy,
            attestation=attestation,
        )


def test_prospective_identity_rejects_wrong_artifact_sha(module_repo, tmp_path: Path) -> None:
    store, commit_a = module_repo
    policy = _synthetic_policy_with_bindings(store, commit_a)
    attestation = _attestation_for(store, commit_a, policy)
    pkg_dir = tmp_path / attestation["historical_cost_policy"]["package_id"]
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "package.json").write_bytes(b'{"different": "bytes"}')
    with pytest.raises(dep.DevelopmentEvaluationPlanError, match="artifact SHA does not match"):
        dep._verify_prospective_historical_identity(
            evidence_root=tmp_path,
            package_id=attestation["historical_cost_policy"]["package_id"],
            content=policy,
            attestation=attestation,
        )


def test_prospective_identity_rejects_wrong_content_fingerprint(
    module_repo, tmp_path: Path
) -> None:
    store, commit_a = module_repo
    policy = _synthetic_policy_with_bindings(store, commit_a)
    attestation = _attestation_for(store, commit_a, policy)
    other = json.loads(json.dumps(policy))
    other["policy_fingerprint"] = "1" * 64
    pkg_dir = tmp_path / attestation["historical_cost_policy"]["package_id"]
    pkg_dir.mkdir(parents=True)
    # Real attested bytes so the raw-SHA gate passes; the tampered CONTENT
    # fingerprint is what must fail.
    (pkg_dir / "package.json").write_bytes(_cost_artifact_bytes(policy))
    with pytest.raises(dep.DevelopmentEvaluationPlanError, match="content fingerprint does not match"):
        dep._verify_prospective_historical_identity(
            evidence_root=tmp_path,
            package_id=attestation["historical_cost_policy"]["package_id"],
            content=other,
            attestation=attestation,
        )


# ---------------------------------------------------------------------------
# §16 — module-surface fail-closed coverage (kept from the original matrix).
# ---------------------------------------------------------------------------


def test_module_surface_fail_closed_matrix(module_repo, tmp_path: Path) -> None:
    store, commit_a = module_repo
    policy = _synthetic_policy_with_bindings(store, commit_a)
    blobs = {
        relative: hashlib.sha256(store.blob_bytes(commit_a, relative)).hexdigest()
        for relative in MODULE_PATHS
    }
    base = dict(
        canonical_commit=commit_a,
        tooling_commit=commit_a,
        policy_package_id="pkg",
        policy_artifact_sha256="0" * 64,
        policy_content_fingerprint=str(policy["policy_fingerprint"]),
        recorded_legacy_execution_model_fingerprint="e" * 64,
        canonical_execution_model_fingerprint=cp.execution_model_fingerprint_canonical(
            commit_a, worktree=store.root, blob_source=store.blob_bytes
        ),
        module_blob_shas=blobs,
        publication_anchor_commit=commit_a,
        v001_implementation_commit=commit_a,
        repo=store.root,
        blob_source=store.blob_bytes,
    )
    with pytest.raises(cp.CostPolicyError, match="module set must match"):
        cp.build_prospective_attestation(
            **{**base, "module_blob_shas": {k: v for k, v in blobs.items() if k != MODULE_PATHS[0]}}
        )
    extra = dict(blobs)
    extra["bot/backtesting/extra.py"] = "f" * 64
    with pytest.raises(cp.CostPolicyError, match="module set must match"):
        cp.build_prospective_attestation(**{**base, "module_blob_shas": extra})
    changed = dict(blobs)
    changed[MODULE_PATHS[1]] = "9" * 64
    with pytest.raises(cp.CostPolicyError, match="does not recompute"):
        cp.build_prospective_attestation(**{**base, "module_blob_shas": changed})
    with pytest.raises(cp.CostPolicyError, match="does not recompute"):
        cp.build_prospective_attestation(
            **{**base, "canonical_execution_model_fingerprint": "c" * 64}
        )


def test_unknown_contract_still_fails_closed(tmp_path: Path) -> None:
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
    with pytest.raises(eip.EmpiricalPipelineError, match="unknown fingerprint contract"):
        eip.resolve_input_bindings(
            evidence_root=tmp_path / "evidence",
            worktree=REPO_ROOT,
            contamination_path=REPO_ROOT / "baseline" / "phase8_contamination_register.json",
            plan={},
            fingerprint_contract="mystery_contract",
        )


# ---------------------------------------------------------------------------
# Synthetic readiness fixture helpers
# ---------------------------------------------------------------------------


def _synthetic_policy_with_bindings(store, commit_a: str) -> dict:
    """Real build_cost_policy content with synthetic execution binding."""
    from bot.strategy.config import StrategyConfig
    from bot.execution.risk.models import RiskPolicy

    policy = cp.build_cost_policy(
        data_root=_synthetic_data_root(),
        broker_support_content_sha256="3" * 64,
    )
    # Bind the FIXTURE execution surface so the attestation (which
    # fingerprints the fixture blobs) matches the policy's binding exactly.
    canonical = cp.execution_model_fingerprint_canonical(
        commit_a, worktree=store.root, blob_source=store.blob_bytes
    )
    policy["bindings"]["execution_model_fingerprint"] = canonical
    policy["bindings"]["strategy_fingerprint"] = cp.strategy_fingerprint(StrategyConfig())
    policy["bindings"]["risk_policy_fingerprint"] = cp.risk_policy_fingerprint(RiskPolicy())
    policy["policy_fingerprint"] = cp.policy_fingerprint(policy)
    return policy


def _synthetic_data_root() -> Path:
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="v001-policy-"))
    derived = root / "derived" / "derived-candles-2024-v1-20260911T195553Z"
    derived.mkdir(parents=True)
    (derived / "manifest.json").write_text(
        json.dumps({
            "year_package_id": "synthetic-year-package",
            "source_canonical_sha256": "a" * 64,
            "source_row_count": 12345,
        }),
        encoding="utf-8",
    )
    dxy = root / "dxy" / "dxy-development-2024-v1-20260912T091410.712364Z"
    dxy.mkdir(parents=True)
    (dxy / "manifest.json").write_text(
        json.dumps({
            "package_id": "synthetic-dxy-package",
            "causal_dxy": {"canonical_content_sha256": "b" * 64, "record_count": 999},
        }),
        encoding="utf-8",
    )
    return root


def _make_input_roots(data_root: Path) -> None:
    for relative in (
        "exness-tick-history/processed/year-packages/exness-xauusdm-2024-development-b2a0234a470dd397",
        "derived/derived-candles-2024-v1-20260911T195553Z",
        "dxy/dxy-development-2024-v1-20260912T091410.712364Z",
        "evidence",
    ):
        (data_root / relative).mkdir(parents=True, exist_ok=True)
    # The readiness impl derives the monthly package list from the year
    # manifest itself before the (stubbed) identity-chain verifier runs.
    year = data_root / "exness-tick-history/processed/year-packages/exness-xauusdm-2024-development-b2a0234a470dd397"
    monthly_ids = [f"synthetic-month-{i:02d}" for i in range(12)]
    (year / "manifest.json").write_text(
        json.dumps({"monthly_packages": [{"package_id": m} for m in monthly_ids]}),
        encoding="utf-8",
    )
    packages = data_root / "exness-tick-history/processed/packages"
    for m in monthly_ids:
        (packages / m).mkdir(parents=True, exist_ok=True)


class _ReadyStub:
    """Stub for the heavy empirical verifiers in the readiness impl.

    Synthetic identity values only; no empirical data is read or created.
    """

    def __init__(self, policy: dict, store, commit: str) -> None:
        self.policy = policy
        self.store = store
        self.commit = commit
        evidence = Path("evidence")
        self.packages = {
            dep.OFFICIAL_NEWS_ID: {
                "manifest": {
                    "package_id": dep.OFFICIAL_NEWS_ID,
                    "kind": "official_news",
                    "content_canonical_sha256": "1" * 64,
                },
                "content": {
                    "status": "ACCEPTED_DEVELOPMENT_ONLY",
                    "events": [{"event_id": "synthetic"}],
                    "complete": True,
                },
            },
            dep.OBSERVED_SPREAD_ID: {
                "manifest": {
                    "package_id": dep.OBSERVED_SPREAD_ID,
                    "kind": "observed_spread",
                    "content_canonical_sha256": "2" * 64,
                },
                "content": {"status": "ACCEPTED_DEVELOPMENT_ONLY"},
            },
            dep.COST_POLICY_ID: {
                "manifest": {
                    "package_id": dep.COST_POLICY_ID,
                    "kind": "development_cost_policy",
                    "content_canonical_sha256": "3" * 64,
                },
                "content": policy,
            },
            dep.METADATA_POLICY_ID: {
                "manifest": {
                    "package_id": dep.METADATA_POLICY_ID,
                    "kind": "development_metadata_bounds",
                    "content_canonical_sha256": "4" * 64,
                },
                "content": {
                    "policy_fingerprint": "5" * 64,
                    "development_evaluation_sufficient": True,
                    "strategy_evaluation_authorized": False,
                    "accepted_for_final_validation": False,
                    "holdout_access_authorized": False,
                    "phase9_authorized": False,
                    "mandatory_scenarios": [{"scenario_id": "synthetic"}],
                },
            },
        }

    def verify_ticks(self, *args, **kwargs):
        return {
            "package_id": "synthetic-tick-year",
            "symbol": dep.SYMBOL,
            "period": {"start_inclusive": dep.DEVELOPMENT_START, "end_exclusive": dep.DEVELOPMENT_END},
            "statistics": {"canonical_normalized_sha256": "a" * 64, "row_count": 42},
        }

    def verify_candles(self, root):
        return {
            "source_canonical_sha256": "a" * 64,
            "original_manifest_sha256": "b" * 64,
            "partitions": [{"timeframe": tf} for tf in dep.TIMEFRAMES],
        }

    def verify_dxy(self, root):
        return {
            "package_id": "synthetic-dxy",
            "constituents": ["EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF"],
            "causal_dxy": {"canonical_content_sha256": "c" * 64, "record_count": 7},
            "source_year_canonical_sha256": "a" * 64,
        }

    def load_evidence(self, evidence_root, package_id, expected_kind):
        package = self.packages[package_id]
        # The cost policy must also pass the raw-artifact identity gate,
        # which reads the real package.json bytes from disk.
        if package_id == dep.COST_POLICY_ID:
            pkg_dir = Path(evidence_root) / package_id
            pkg_dir.mkdir(parents=True, exist_ok=True)
            artifact = pkg_dir / "package.json"
            artifact.write_bytes(self.cost_artifact_bytes)
            return package
        return package

    @property
    def cost_artifact_bytes(self) -> bytes:
        return _cost_artifact_bytes(self.policy)

    def contamination(self, path):
        register = type("R", (), {"artifacts": [{"a": 1}], "source": "synthetic"})
        return register
