"""Phase 8I focused tests: swap-policy activation + dataset-acceptance review.

Synthetic fixtures only — no network, no MT5, no strategy evaluation, no
holdout access.  The activation record binds the frozen Phase 8H policy
without ever modifying it.  Fixture roots monkeypatch the pinned-identity
map so the production pinned-identity guard is exercised against synthetic
ids (same code path as production, different constant table).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.acquisition.evidence_store import (  # noqa: E402
    EvidenceStoreError,
    build_evidence_package,
    load_evidence_package,
    publish_evidence_package,
)
from bot.validation import cost_policy as cp  # noqa: E402
from bot.validation import cost_policy_activation as cpa  # noqa: E402

# Synthetic SHA-256 binding value (fixture constant; matches nothing real).
SYNTH_SUPPORT_HASH = "3" * 64

DECISION_UTC = "2026-09-15T00:00:00Z"
DECISION_SCOPE = "Activate the preregistered assumption-only swap policy (synthetic test scope)"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_data_root(tmp_path: Path) -> Path:
    """Synthetic data root: derived manifest, tick package, DXY, evidence."""

    derived = tmp_path / "derived" / "derived-candles-2024-v1-20260911T195553Z"
    derived.mkdir(parents=True)
    (derived / "manifest.json").write_text(
        json.dumps(
            {
                "year_package_id": "synthetic-year-package",
                "source_canonical_sha256": "a" * 64,
                "source_row_count": 12345,
            }
        ),
        encoding="utf-8",
    )
    att_dir = tmp_path / "derived" / "attestations" / cpa.ATTESTATION_DIR
    att_dir.mkdir(parents=True)
    attestation = {
        "attestation_id": cpa.ATTESTATION_DIR,
        "schema_version": "phase8c.provenance-attestation.v1",
        "classification": "DEVELOPMENT_ONLY",
        "holdout_accessed": False,
        "mt5_or_trading_accessed": False,
        "package": {
            "package_id": "derived-candles-2024-v1-20260911T195553Z",
            # Written after the manifest exists (hash of real bytes).
            "manifest_sha256": None,
            "source_canonical_sha256": "a" * 64,
            "source_row_count": 12345,
            "source_year_package_id": "synthetic-year-package",
        },
    }
    att_dir / "attestation.json"
    manifest_path = derived / "manifest.json"
    attestation["package"]["manifest_sha256"] = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    (att_dir / "attestation.json").write_text(json.dumps(attestation), encoding="utf-8")
    tick_dir = (
        tmp_path / "exness-tick-history" / "processed" / "year-packages" / "synthetic-year-package"
    )
    tick_dir.mkdir(parents=True)
    (tick_dir / "manifest.json").write_text(
        json.dumps(
            {
                "package_id": "synthetic-year-package",
                "statistics": {
                    "canonical_normalized_sha256": "a" * 64,
                    "row_count": 12345,
                },
            }
        ),
        encoding="utf-8",
    )
    dxy = tmp_path / "dxy" / "dxy-development-2024-v1-20260912T091410.712364Z"
    dxy.mkdir(parents=True)
    (dxy / "manifest.json").write_text(
        json.dumps(
            {
                "package_id": "dxy-development-2024-v1-synthetic",
                "causal_dxy": {"canonical_content_sha256": "b" * 64, "record_count": 100},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _publish_package(content: dict, kind: str, evidence_root: Path) -> str:
    package, package_id = build_evidence_package(
        kind=kind, content=content, source_path=None
    )
    publish_evidence_package(package, evidence_root=evidence_root)
    return package_id


def _synthetic_policy_content(
    temp_data_root: Path, evidence_root: Path, support_id: str, spread_id: str
) -> dict:
    content = cp.build_cost_policy(
        data_root=temp_data_root,
        broker_support_content_sha256=SYNTH_SUPPORT_HASH,
    )
    content["bindings"]["broker_support_revision"]["package_id"] = support_id
    content["bindings"]["observed_spread_evidence"]["package_id"] = spread_id
    content["policy_fingerprint"] = cp.policy_fingerprint(content)
    return content


@pytest.fixture()
def seeded_root(temp_data_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Full synthetic root: policy + synthetic evidence + news, pinned ids patched."""

    evidence_root = temp_data_root / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)

    # Synthetic revisions first, so the policy can bind their ids.
    support_id = _publish_package(
        {
            "schema_version": "phase8e.synthetic-fixture.v1",
            "classification": "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE",
            "status": "ACCEPTED_DEVELOPMENT_ONLY",
            "note": "synthetic support revision",
        },
        "broker_support",
        evidence_root,
    )
    spread_id = _publish_package(
        {
            "schema_version": "phase8e.synthetic-fixture.v1",
            "classification": "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE",
            "status": "ACCEPTED_DEVELOPMENT_ONLY",
            "note": "synthetic spread revision",
        },
        "observed_spread",
        evidence_root,
    )
    content = _synthetic_policy_content(temp_data_root, evidence_root, support_id, spread_id)
    _publish_package(content, "development_cost_policy", evidence_root)

    news_id = _publish_package(
        {
            "schema_version": "phase8f.official-usd-news.v1",
            "classification": "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE",
            "status": "ACCEPTED_DEVELOPMENT_ONLY",
            "complete": True,
            "coverage_gaps": [],
            "months_covered": list(range(1, 13)),
            "events": [
                {
                    "event_id": f"e{i:023d}",
                    "event_at_utc": "2024-01-02T14:30:00Z",
                    "category": "EMPLOYMENT_SITUATION",
                }
                for i in range(12)
            ],
        },
        "official_news",
        evidence_root,
    )
    assert news_id

    pinned = {
        "development_cost_policy": sorted(
            evidence_root.glob("evidence-development_cost_policy-v1-*")
        )[-1].name,
        "broker_support_revision": support_id,
        "observed_spread_evidence": spread_id,
    }
    monkeypatch.setattr(cpa, "REQUIRED_EVIDENCE_PACKAGES", pinned)
    return temp_data_root


# ---------------------------------------------------------------------------
# Activation record
# ---------------------------------------------------------------------------


def test_activation_record_builds_and_verifies(seeded_root: Path) -> None:
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    report = cpa.verify_activation_record(activation)
    assert report["verified"] is True
    assert report["activation_state"] == "ACTIVE_FOR_DEVELOPMENT_VALIDATION"
    assert activation["activated_policy"]["policy_state_remains"] == "PREREGISTERED_INACTIVE"


def test_activation_binds_exact_policy_fingerprint(seeded_root: Path) -> None:
    evidence_root = seeded_root / "evidence"
    policy_report = cpa.verify_published_policy(evidence_root)
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    assert (
        activation["activated_policy"]["policy_fingerprint"]
        == policy_report["policy_fingerprint"]
    )


def test_frozen_scenario_order_and_multipliers(seeded_root: Path) -> None:
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    ids = [s["scenario_id"] for s in activation["swap_scenarios_activated"]]
    assert ids == list(cp.SWAP_SCENARIO_ORDER)
    multipliers = [
        s["multiplier_vs_email_reference"] for s in activation["swap_scenarios_activated"]
    ]
    assert multipliers == [0.0, 1.0, 2.0, 3.0]


def test_required_adverse_boundary_is_3x_and_last(seeded_root: Path) -> None:
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    scenarios = activation["swap_scenarios_activated"]
    assert scenarios[-1]["scenario_id"] == "SWAP_EMAIL_3X_ADVERSE"
    assert activation["scope_and_restrictions"]["required_adverse_boundary"] == (
        "SWAP_EMAIL_3X_ADVERSE"
    )


def test_triple_wednesday_and_no_positive_credit(seeded_root: Path) -> None:
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    for scenario in activation["swap_scenarios_activated"]:
        assert scenario["triple_swap_weekday"] == "WEDNESDAY"
        assert scenario["no_favorable_positive_swap_credit"] is True
        assert scenario["long_usd_per_lot_per_day"] <= 0
        assert scenario["short_usd_per_lot_per_day"] <= 0


def test_activation_gates_all_false_and_label_carried(seeded_root: Path) -> None:
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    restrictions = activation["scope_and_restrictions"]
    for gate in (
        "final_validation_authorized",
        "holdout_access_authorized",
        "strategy_evaluation_authorized",
    ):
        assert restrictions[gate] is False
    for scenario in activation["swap_scenarios_activated"]:
        assert scenario["historical_swap_uncertain_label"] == "HISTORICAL_SWAP_UNCERTAIN"
        assert scenario["classification"] == "ASSUMPTION_ONLY"


def test_slippage_ladder_activated_assumption_only(seeded_root: Path) -> None:
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    slip = activation["slippage_scenarios_activated"]
    assert [s["points"] for s in slip] == [0.0, 1.0, 3.0]
    assert all(s["classification"] == "ASSUMPTION_ONLY" for s in slip)


def test_policy_package_untouched_by_activation(seeded_root: Path) -> None:
    evidence_root = seeded_root / "evidence"

    def snapshot() -> list:
        return sorted(
            (
                p.name,
                hashlib.sha256(p.read_bytes()).hexdigest(),
            )
            for d in sorted(evidence_root.glob("evidence-development_cost_policy-v1-*"))
            for p in [d / "package.json"]
        )

    before = snapshot()
    cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    assert snapshot() == before


def test_activation_requires_published_policy(temp_data_root: Path) -> None:
    with pytest.raises(cpa.CostPolicyActivationError, match="no published"):
        cpa.build_activation_record(
            data_root=temp_data_root,
            decision_utc=DECISION_UTC,
            decision_scope=DECISION_SCOPE,
        )


def test_activation_rejects_missing_required_package(
    seeded_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence_root = seeded_root / "evidence"
    support_dir = sorted(evidence_root.glob("evidence-broker_support-v1-*"))[0]
    shutil.rmtree(support_dir)
    with pytest.raises(cpa.CostPolicyActivationError, match="missing on disk"):
        cpa.build_activation_record(
            data_root=seeded_root,
            decision_utc=DECISION_UTC,
            decision_scope=DECISION_SCOPE,
        )


def test_activation_rejects_tampered_policy_ladder(seeded_root: Path) -> None:
    evidence_root = seeded_root / "evidence"
    policy_dir = sorted(evidence_root.glob("evidence-development_cost_policy-v1-*"))[-1]
    package = load_evidence_package(policy_dir)
    # Drop the 3x adverse scenario and re-sign: a sophisticated tamperer.
    package["content"]["swap_scenarios"] = package["content"]["swap_scenarios"][:3]
    package["content"]["policy_fingerprint"] = cp.policy_fingerprint(package["content"])
    fresh, _ = build_evidence_package(
        kind="development_cost_policy", content=package["content"], source_path=None
    )
    shutil.rmtree(policy_dir)
    publish_evidence_package(fresh, evidence_root=evidence_root)
    # verify_published_policy (the frozen 8H verifier) rejects the drifted
    # ladder before the activation-level guard can run.
    with pytest.raises(
        (cpa.CostPolicyActivationError, cp.CostPolicyError),
        match="ladder|scenario order",
    ):
        cpa.build_activation_record(
            data_root=seeded_root,
            decision_utc=DECISION_UTC,
            decision_scope=DECISION_SCOPE,
        )


def test_activation_rejects_positive_swap_credit(seeded_root: Path) -> None:
    # A policy that grants a favorable credit can never pass the ladder guard.
    evidence_root = seeded_root / "evidence"
    policy_dir = sorted(evidence_root.glob("evidence-development_cost_policy-v1-*"))[-1]
    package = load_evidence_package(policy_dir)
    package["content"]["swap_scenarios"][1]["long_usd_per_lot_per_day"] = 3.85
    package["content"]["policy_fingerprint"] = cp.policy_fingerprint(package["content"])
    fresh, _ = build_evidence_package(
        kind="development_cost_policy", content=package["content"], source_path=None
    )
    shutil.rmtree(policy_dir)
    publish_evidence_package(fresh, evidence_root=evidence_root)
    # The frozen 8H verifier rejects the flipped sign via its scenario-value
    # guards before the activation-level credit guard can run.
    with pytest.raises(
        (cpa.CostPolicyActivationError, cp.CostPolicyError),
        match="positive swap credit|drifted from the frozen value",
    ):
        cpa.build_activation_record(
            data_root=seeded_root,
            decision_utc=DECISION_UTC,
            decision_scope=DECISION_SCOPE,
        )


# ---------------------------------------------------------------------------
# Publication, idempotency, tampering (store level)
# ---------------------------------------------------------------------------


def test_activation_publication_is_idempotent(seeded_root: Path) -> None:
    evidence_root = seeded_root / "evidence"
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    package, package_id = build_evidence_package(
        kind="cost_policy_activation", content=activation, source_path=None
    )
    target1, id1 = publish_evidence_package(package, evidence_root=evidence_root)
    target2, id2 = publish_evidence_package(package, evidence_root=evidence_root)
    assert id1 == id2 == package_id
    assert target1 == target2
    matches = list(evidence_root.glob("evidence-cost_policy_activation-v1-*"))
    assert len(matches) == 1


def test_conflicting_content_same_id_fails_closed(seeded_root: Path) -> None:
    evidence_root = seeded_root / "evidence"
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    package, _ = build_evidence_package(
        kind="cost_policy_activation", content=activation, source_path=None
    )
    publish_evidence_package(package, evidence_root=evidence_root)
    original_id = package["manifest"]["package_id"]
    tampered = json.loads(json.dumps(package))
    tampered["content"]["owner_decision"]["decision_scope"] = "conflicting rewrite"
    tampered["manifest"]["content_canonical_sha256"] = "f" * 64
    # Same content-derived id, different content identity: the store must
    # refuse rather than overwrite.
    tampered["manifest"]["package_id"] = original_id
    with pytest.raises(EvidenceStoreError, match="conflicting evidence package"):
        publish_evidence_package(tampered, evidence_root=evidence_root)


def test_verify_detects_activation_tampering(seeded_root: Path) -> None:
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    tampered = json.loads(json.dumps(activation))
    tampered["scope_and_restrictions"]["final_validation_authorized"] = True
    with pytest.raises(cpa.CostPolicyActivationError, match="must remain false"):
        cpa.verify_activation_record(tampered)
    rescaled = json.loads(json.dumps(activation))
    rescaled["swap_scenarios_activated"][1]["multiplier_vs_email_reference"] = 0.5
    with pytest.raises(cpa.CostPolicyActivationError, match="multipliers drifted"):
        cpa.verify_activation_record(rescaled)
    relabelled = json.loads(json.dumps(activation))
    relabelled["owner_decision"]["historical_swap_reinterpreted"] = True
    with pytest.raises(cpa.CostPolicyActivationError, match="not be reinterpreted"):
        cpa.verify_activation_record(relabelled)


def test_activation_record_hash_is_deterministic(seeded_root: Path) -> None:
    a1 = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    a2 = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    assert a1 == a2
    assert (
        a1["activation_record_sha256"] == a2["activation_record_sha256"]
    )


# ---------------------------------------------------------------------------
# Dataset-acceptance review
# ---------------------------------------------------------------------------


def test_acceptance_review_builds_and_verifies(seeded_root: Path) -> None:
    review = cpa.build_acceptance_review(data_root=seeded_root)
    report = cpa.verify_acceptance_review(review)
    assert report["verified"] is True
    statuses = review["statuses"]
    assert statuses["XAUUSDM_TICKS_2024"] == "ACCEPTED_EMPIRICAL"
    assert statuses["XAUUSDM_CAUSAL_CANDLES"] == "ACCEPTED_EMPIRICAL"
    assert statuses["OBSERVED_SPREAD"] == "ACCEPTED_EMPIRICAL"
    assert statuses["OFFICIAL_USD_NEWS"] == "ACCEPTED_DEVELOPMENT_ONLY"
    assert statuses["COMMISSION"] == "ACCEPTED_DEVELOPMENT_ONLY"
    assert statuses["SWAP_ROLLOVER"] == "ACCEPTED_DEVELOPMENT_ONLY"
    assert statuses["SLIPPAGE_FILLS"] == "ACCEPTED_DEVELOPMENT_ONLY"
    assert statuses["BROKER_METADATA"] == "INSUFFICIENT"
    assert statuses["HOLDOUT"] == "BLOCKED"
    assert review["accepted_for_final_validation"] is False
    assert review["strategy_evaluation_authorized"] is False
    assert review["holdout_access_authorized"] is False
    # BROKER_METADATA (and only it, plus holdout) blocks development sufficiency.
    assert review["development_evaluation_sufficient"] is False


def test_acceptance_review_binds_verified_market_chain(seeded_root: Path) -> None:
    review = cpa.build_acceptance_review(data_root=seeded_root)
    chain = review["review_basis"]["verified_market_data_chain"]
    assert chain["source_year_package_id"] == "synthetic-year-package"
    assert chain["source_row_count"] == 12345
    assert chain["attestation_id"] == cpa.ATTESTATION_DIR
    assert chain["derived_manifest_sha256"] == chain["derived_manifest_sha256"]
    news = review["review_basis"]["verified_official_news"]
    assert news["event_count"] == 12
    assert news["months_covered"] == 12
    dxy_category = next(
        c for c in review["categories"] if c["category"] == "DXY_DEVELOPMENT_INPUT"
    )
    assert dxy_category["verified_package_id"] == "dxy-development-2024-v1-synthetic"


def test_acceptance_review_fails_closed_without_news(seeded_root: Path) -> None:
    evidence_root = seeded_root / "evidence"
    for d in sorted(evidence_root.glob("evidence-official_news-v1-*")):
        shutil.rmtree(d)
    with pytest.raises(cpa.CostPolicyActivationError, match="official-news"):
        cpa.build_acceptance_review(data_root=seeded_root)


def test_acceptance_review_fails_closed_with_incomplete_news(seeded_root: Path) -> None:
    evidence_root = seeded_root / "evidence"
    news_dir = sorted(evidence_root.glob("evidence-official_news-v1-*"))[-1]
    package = load_evidence_package(news_dir)
    package["content"]["complete"] = False
    package["content"]["coverage_gaps"] = ["OCTOBER"]
    fresh, _ = build_evidence_package(
        kind="official_news", content=package["content"], source_path=None
    )
    shutil.rmtree(news_dir)
    publish_evidence_package(fresh, evidence_root=evidence_root)
    with pytest.raises(cpa.CostPolicyActivationError, match="incomplete"):
        cpa.build_acceptance_review(data_root=seeded_root)


def test_acceptance_review_rejects_market_chain_drift(seeded_root: Path) -> None:
    # Make the attested manifest hash disagree with the actual manifest bytes.
    derived_manifest = (
        seeded_root
        / "derived"
        / "derived-candles-2024-v1-20260911T195553Z"
        / "manifest.json"
    )
    manifest = json.loads(derived_manifest.read_text(encoding="utf-8"))
    manifest["source_row_count"] = 999
    derived_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(cpa.CostPolicyActivationError, match="attested manifest"):
        cpa.build_acceptance_review(data_root=seeded_root)


def test_acceptance_review_rejects_ambiguous_tick_packages(seeded_root: Path) -> None:
    # A second tick manifest with the same canonical hash is ambiguous.
    dup = (
        seeded_root
        / "exness-tick-history"
        / "processed"
        / "year-packages"
        / "duplicate-year-package"
    )
    dup.mkdir(parents=True)
    (dup / "manifest.json").write_text(
        json.dumps(
            {
                "package_id": "duplicate-year-package",
                "statistics": {"canonical_normalized_sha256": "a" * 64, "row_count": 12345},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(cpa.CostPolicyActivationError, match="ambiguous tick year"):
        cpa.build_acceptance_review(data_root=seeded_root)


def test_acceptance_review_rejects_missing_tick_row_count_match(seeded_root: Path) -> None:
    tick_dir = (
        seeded_root
        / "exness-tick-history"
        / "processed"
        / "year-packages"
        / "synthetic-year-package"
    )
    tick_manifest = json.loads((tick_dir / "manifest.json").read_text(encoding="utf-8"))
    tick_manifest["statistics"]["row_count"] = 42
    (tick_dir / "manifest.json").write_text(json.dumps(tick_manifest), encoding="utf-8")
    with pytest.raises(cpa.CostPolicyActivationError, match="row count"):
        cpa.build_acceptance_review(data_root=seeded_root)


def test_review_gates_cannot_flip(seeded_root: Path) -> None:
    review = cpa.build_acceptance_review(data_root=seeded_root)
    review["accepted_for_final_validation"] = True
    with pytest.raises(cpa.CostPolicyActivationError, match="must remain false"):
        cpa.verify_acceptance_review(review)
    altered = cpa.build_acceptance_review(data_root=seeded_root)
    altered["statuses"]["HOLDOUT"] = "ACCEPTED_EMPIRICAL"
    with pytest.raises(cpa.CostPolicyActivationError, match="statuses drifted"):
        cpa.verify_acceptance_review(altered)
    hidden = cpa.build_acceptance_review(data_root=seeded_root)
    hidden["statuses"] = dict(hidden["statuses"])
    hidden["statuses"]["COMMISSION"] = "MISSING"
    with pytest.raises(cpa.CostPolicyActivationError, match="statuses drifted"):
        cpa.verify_acceptance_review(hidden)


# ---------------------------------------------------------------------------
# Matrix/readiness integration (collector level)
# ---------------------------------------------------------------------------


def test_collector_maps_activation_and_review_kinds(seeded_root: Path) -> None:
    from backtests.evidence_intake_control import collect_evidence_statuses  # noqa: F401

    evidence_root = seeded_root / "evidence"
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    package_id = _publish_package(activation, "cost_policy_activation", evidence_root)
    review = cpa.build_acceptance_review(data_root=seeded_root)
    review_id = _publish_package(review, "dataset_acceptance_review", evidence_root)
    found = collect_evidence_statuses(evidence_root)
    assert found["cost_policy_activation"]["package_id"] == package_id
    assert found["cost_policy_activation"]["status"] == "ACTIVE_FOR_DEVELOPMENT_VALIDATION"
    assert found["dataset_acceptance_review"]["package_id"] == review_id
    assert found["dataset_acceptance_review"]["status"] == "ACCEPTED_DEVELOPMENT_ONLY"


def test_readiness_gates_stay_false_with_activation(
    seeded_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backtests import evidence_intake_control as eic

    # The matrix builder recomputes observed-spread statistics from the M5
    # partition; this synthetic root has none, so pin the spread entry like
    # the Phase 8F matrix tests do.
    monkeypatch.setattr(
        eic,
        "_spread_matrix_entry",
        lambda spread_content: {
            "category": "OBSERVED_SPREAD",
            "status": "ACCEPTED_DEVELOPMENT_ONLY",
            "sha256": "0" * 64,
            "schema_version": "phase8e.observed-spread-evidence.v1",
            "permitted_uses": [],
            "prohibited_uses": [],
        },
    )
    monkeypatch.setattr(
        eic,
        "build_observed_spread_evidence",
        lambda data_root: {"status": "ACCEPTED_DEVELOPMENT_ONLY"},
    )
    build_matrix_package = eic.build_matrix_package
    build_readiness_package = eic.build_readiness_package

    evidence_root = seeded_root / "evidence"
    activation = cpa.build_activation_record(
        data_root=seeded_root,
        decision_utc=DECISION_UTC,
        decision_scope=DECISION_SCOPE,
    )
    _publish_package(activation, "cost_policy_activation", evidence_root)
    review = cpa.build_acceptance_review(data_root=seeded_root)
    _publish_package(review, "dataset_acceptance_review", evidence_root)
    matrix = build_matrix_package(evidence_root, seeded_root)
    readiness = build_readiness_package(matrix)
    assert matrix["statuses"]["COST_POLICY_ACTIVATION"] == "ACTIVE_FOR_DEVELOPMENT_VALIDATION"
    assert matrix["statuses"]["DATASET_ACCEPTANCE_REVIEW"] == "ACCEPTED_DEVELOPMENT_ONLY"
    # Activation never satisfies the raw 8E categories nor authorizes anything.
    assert readiness["strategy_evaluation_authorized"] is False
    assert readiness["accepted_for_final_validation"] is False
    assert readiness["holdout_access_authorized"] is False
    assert matrix["all_categories_accepted"] is False


# ---------------------------------------------------------------------------
# Import safety
# ---------------------------------------------------------------------------


def test_no_mt5_or_network_imports() -> None:
    """Process-level MT5-freedom plus source-level network/exec prohibition."""

    mt5_before = sys.modules.get("MetaTrader5")
    import bot.validation.cost_policy_activation as activation_module  # noqa: F401
    import backtests.cost_policy_control as control_module  # noqa: F401

    # Pure validation modules must not transitively require the terminal
    # library (Phase 8H import-safety regression convention).
    assert sys.modules.get("MetaTrader5") is mt5_before

    for module_name in (
        "bot/validation/cost_policy_activation.py",
        "backtests/cost_policy_control.py",
    ):
        source = (REPO_ROOT / module_name).read_text(encoding="utf-8")
        for forbidden in (
            "MetaTrader5",
            "import requests",
            "import socket",
            "order_send",
            "account_info",
        ):
            assert forbidden not in source, f"{module_name} references {forbidden}"
