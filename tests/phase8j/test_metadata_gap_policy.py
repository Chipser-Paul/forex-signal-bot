"""Focused Phase 8J tests using synthetic evidence only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.acquisition.evidence_contracts import canonical_hash  # noqa: E402
from bot.acquisition.evidence_store import (  # noqa: E402
    EvidenceStoreError,
    build_evidence_package,
    publish_evidence_package,
)
from bot.validation import cost_policy_activation as cpa  # noqa: E402
from bot.validation import metadata_gap_policy as mgp  # noqa: E402


DECISION_UTC = "2026-09-15T00:00:00Z"


def _review() -> dict:
    categories = [dict(item) for item in cpa.ACCEPTANCE_REVIEW_CATEGORIES]
    statuses = {str(item["category"]): str(item["status"]) for item in categories}
    content = {
        "schema_version": cpa.ACCEPTANCE_SCHEMA_VERSION,
        "status": "ACCEPTED_DEVELOPMENT_ONLY",
        "categories": categories,
        "statuses": statuses,
        "accepted_categories": [],
        "insufficient_categories": ["BROKER_METADATA"],
        "blocked_categories": ["HOLDOUT"],
        "development_evaluation_sufficient": False,
        "final_validation_authorized": False,
        "holdout_access_authorized": False,
        "strategy_evaluation_authorized": False,
        "accepted_for_final_validation": False,
        "review_basis": {
            "cost_policy_fingerprint": "a" * 64,
            "verified_evidence_packages": {"broker_support_revision": "evidence-broker_support-v1-active"},
            "verified_market_data_chain": {"tick_year": "t" * 64, "dxy": "d" * 64},
            "verified_official_news": {"package_id": "evidence-official_news-v1-news", "content_canonical_sha256": "n" * 64},
        },
    }
    content["review_canonical_sha256"] = canonical_hash(content)
    return content


def _activation() -> dict:
    return {
        "activation_state": "ACTIVE_FOR_DEVELOPMENT_VALIDATION",
        "activated_policy": {"package_id": "evidence-development_cost_policy-v1-policy", "policy_fingerprint": "a" * 64},
    }


@pytest.fixture(autouse=True)
def _activation_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 8I separately tests full activation/review validation.

    Here the fixture isolates the Phase 8J overlay's field and hash contract.
    """

    monkeypatch.setattr(cpa, "verify_activation_record", lambda content: {"verified": True})
    monkeypatch.setattr(cpa, "verify_acceptance_review", lambda content: {"verified": True})


def _policy() -> dict:
    return mgp.build_metadata_gap_policy(
        acceptance_review=_review(),
        acceptance_review_package_id="evidence-dataset_acceptance_review-v1-review",
        acceptance_review_content_sha256="r" * 64,
        policy_report={
            "package_id": "evidence-development_cost_policy-v1-policy",
            "policy_fingerprint": "a" * 64,
        },
        activation_content=_activation(),
        activation_package_id="evidence-cost_policy_activation-v1-activation",
        activation_content_sha256="c" * 64,
        broker_support_revisions=[
            {"package_id": "evidence-broker_support-v1-old", "content_canonical_sha256": "1" * 64},
            {"package_id": "evidence-broker_support-v1-active", "content_canonical_sha256": "2" * 64},
        ],
        decision_utc=DECISION_UTC,
    )


def test_field_by_field_policy_is_deterministic_and_fails_closed() -> None:
    first = _policy()
    second = _policy()
    assert first == second
    assert mgp.verify_metadata_gap_policy(first)["acceptable"] is False
    assert first["development_metadata_gap_acceptable"] is False
    assert first["development_evaluation_sufficient"] is False
    assert first["strategy_evaluation_authorized"] is False
    assert first["accepted_for_final_validation"] is False
    fields = {entry["field"]: entry for entry in first["fields"]}
    assert fields["digits_price_precision"]["historical_status"] == mgp.EMPIRICALLY_DERIVED
    assert fields["trading_sessions_instrument_availability"]["conservatively_bounded"] is True
    assert fields["contract_size"]["blocks_development_evaluation"] is True
    assert fields["stops_level"]["historical_status"] == mgp.UNAVAILABLE
    assert "contract_size" in first["unresolved_blockers"]
    assert first["bindings"]["current_broker_metadata_evidence"] == {
        "package_id": "evidence-broker_support-v1-active"
    }


def test_policy_rejects_tampering_and_promoted_gate() -> None:
    tampered = json.loads(json.dumps(_policy()))
    tampered["fields"][0]["blocks_development_evaluation"] = False
    with pytest.raises(mgp.MetadataGapPolicyError, match="blocker list drifted"):
        mgp.verify_metadata_gap_policy(tampered)
    promoted = json.loads(json.dumps(_policy()))
    promoted["strategy_evaluation_authorized"] = True
    promoted["policy_canonical_sha256"] = canonical_hash(
        {key: value for key, value in promoted.items() if key != "policy_canonical_sha256"}
    )
    with pytest.raises(mgp.MetadataGapPolicyError, match="strategy_evaluation_authorized"):
        mgp.verify_metadata_gap_policy(promoted)


def test_readiness_is_hash_bound_and_never_authorizes_strategy() -> None:
    policy = _policy()
    readiness = mgp.build_metadata_gap_readiness(
        policy,
        policy_package_id="evidence-broker_metadata_gap_policy-v1-test",
        policy_content_sha256="p" * 64,
    )
    assert mgp.verify_metadata_gap_readiness(readiness)["acceptable"] is False
    assert readiness["strategy_evaluation_authorized"] is False
    tampered = json.loads(json.dumps(readiness))
    tampered["accepted_for_final_validation"] = True
    with pytest.raises(mgp.MetadataGapPolicyError, match="accepted_for_final_validation"):
        mgp.verify_metadata_gap_readiness(tampered)


def test_broker_support_revision_loading_is_hash_verified(tmp_path: Path) -> None:
    package, package_id = build_evidence_package(
        kind="broker_support", content={"schema_version": "fixture", "status": "CURRENT_ONLY"}, source_path=None
    )
    target, _ = publish_evidence_package(package, evidence_root=tmp_path)
    assert mgp._load_broker_support_revisions(tmp_path) == [
        {"package_id": package_id, "content_canonical_sha256": package["manifest"]["content_canonical_sha256"]}
    ]
    (target / "package.json").write_text("{}", encoding="utf-8")
    with pytest.raises(EvidenceStoreError, match="envelope disagrees|content hash mismatch"):
        mgp._load_broker_support_revisions(tmp_path)


def test_publication_is_idempotent_and_conflicting_prior_policy_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _policy()
    readiness = mgp.build_metadata_gap_readiness(
        policy,
        policy_package_id="placeholder",
        policy_content_sha256="p" * 64,
    )
    monkeypatch.setattr(mgp, "build_from_evidence_root", lambda **_: (policy, readiness))
    first = mgp.publish_from_evidence_root(data_root=tmp_path, decision_utc=DECISION_UTC)
    second = mgp.publish_from_evidence_root(data_root=tmp_path, decision_utc=DECISION_UTC)
    assert first == second
    conflict, _ = build_evidence_package(
        kind="broker_metadata_gap_policy",
        content={"schema_version": mgp.POLICY_SCHEMA_VERSION, "different": True}, source_path=None,
    )
    publish_evidence_package(conflict, evidence_root=tmp_path / "evidence")
    with pytest.raises(mgp.MetadataGapPolicyError, match="conflicting Phase 8J"):
        mgp.publish_from_evidence_root(data_root=tmp_path, decision_utc=DECISION_UTC)


def test_phase8j_imports_are_mt5_and_network_free() -> None:
    before = sys.modules.get("MetaTrader5")
    import bot.validation.metadata_gap_policy as module  # noqa: F401
    import backtests.metadata_gap_policy_control as cli  # noqa: F401

    assert sys.modules.get("MetaTrader5") is before
    for relative in ("bot/validation/metadata_gap_policy.py", "backtests/metadata_gap_policy_control.py"):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for forbidden in ("MetaTrader5", "import requests", "import socket", "order_send", "account_info"):
            assert forbidden not in source
