"""Synthetic tests for the append-only Phase 8K recovery overlay."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.acquisition.evidence_contracts import canonical_hash  # noqa: E402
from bot.acquisition.evidence_store import build_evidence_package, publish_evidence_package  # noqa: E402
from bot.validation import cost_policy_activation as cpa  # noqa: E402
from bot.validation import metadata_gap_policy as mgp  # noqa: E402
from bot.validation import metadata_recovery as recovery  # noqa: E402


DECISION_UTC = "2026-09-15T00:00:00Z"


@pytest.fixture(autouse=True)
def _phase8j_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cpa, "verify_activation_record", lambda content: {"verified": True})
    monkeypatch.setattr(cpa, "verify_acceptance_review", lambda content: {"verified": True})


def _phase8j_policy() -> dict:
    categories = [dict(item) for item in cpa.ACCEPTANCE_REVIEW_CATEGORIES]
    review = {
        "schema_version": cpa.ACCEPTANCE_SCHEMA_VERSION,
        "status": "ACCEPTED_DEVELOPMENT_ONLY",
        "categories": categories,
        "statuses": {str(item["category"]): str(item["status"]) for item in categories},
        "accepted_categories": [], "insufficient_categories": ["BROKER_METADATA"],
        "blocked_categories": ["HOLDOUT"], "development_evaluation_sufficient": False,
        "final_validation_authorized": False, "holdout_access_authorized": False,
        "strategy_evaluation_authorized": False, "accepted_for_final_validation": False,
        "review_basis": {"cost_policy_fingerprint": "a" * 64,
                         "verified_evidence_packages": {"broker_support_revision": "evidence-broker_support-v1-active"},
                         "verified_market_data_chain": {}, "verified_official_news": {}},
    }
    review["review_canonical_sha256"] = canonical_hash(review)
    return mgp.build_metadata_gap_policy(
        acceptance_review=review, acceptance_review_package_id="evidence-dataset_acceptance_review-v1-review",
        acceptance_review_content_sha256="r" * 64,
        policy_report={"package_id": "evidence-development_cost_policy-v1-policy", "policy_fingerprint": "a" * 64},
        activation_content={"activation_state": "ACTIVE_FOR_DEVELOPMENT_VALIDATION",
                            "activated_policy": {"package_id": "evidence-development_cost_policy-v1-policy", "policy_fingerprint": "a" * 64}},
        activation_package_id="evidence-cost_policy_activation-v1-activation", activation_content_sha256="c" * 64,
        broker_support_revisions=[{"package_id": "evidence-broker_support-v1-active", "content_canonical_sha256": "b" * 64}],
        decision_utc=DECISION_UTC,
    )


def _recovery() -> tuple[dict, dict]:
    policy = _phase8j_policy()
    readiness = mgp.build_metadata_gap_readiness(policy, policy_package_id="evidence-broker_metadata_gap_policy-v1-policy", policy_content_sha256="p" * 64)
    result = recovery.build_metadata_recovery(
        phase8j_policy=policy, phase8j_policy_package_id="evidence-broker_metadata_gap_policy-v1-policy",
        phase8j_policy_content_sha256="p" * 64, phase8j_readiness=readiness,
        phase8j_readiness_package_id="evidence-metadata_gap_readiness-v1-readiness", phase8j_readiness_content_sha256="q" * 64,
        accepted_review={}, accepted_review_package_id="evidence-dataset_acceptance_review-v1-review",
        accepted_review_content_sha256="r" * 64,
        quote_representation={"year_package_id": "year", "year_canonical_sha256": "y" * 64,
                              "maximum_observed_decimal_places": 3, "months": [], "scope": "fixture"},
        decision_utc=DECISION_UTC,
    )
    return result, policy


def test_recovery_is_deterministic_and_preserves_fail_closed_gates() -> None:
    first, _ = _recovery()
    second, _ = _recovery()
    assert first == second
    report = recovery.verify_metadata_recovery(first)
    assert report["all_material_metadata_bounded"] is False
    assert first["development_metadata_gap_acceptable"] is False
    assert first["development_evaluation_sufficient"] is False
    assert first["strategy_evaluation_authorized"] is False
    assert first["accepted_for_final_validation"] is False
    fields = {item["field"]: item for item in first["fields"]}
    assert fields["point_tick_size"]["phase8k_classification"] == recovery.EMPIRICALLY_DERIVED
    assert fields["point_tick_size"]["conservatively_bounded"] is False
    assert fields["contract_size"]["phase8k_classification"] == recovery.CURRENT_ONLY
    assert fields["tick_value"]["phase8k_classification"] == recovery.UNAVAILABLE
    assert "contract_size" in first["remaining_blockers"]


def test_recovery_rejects_tampering_or_attempted_promotion() -> None:
    record, _ = _recovery()
    tampered = json.loads(json.dumps(record))
    tampered["fields"][0]["conservatively_bounded"] = True
    with pytest.raises(recovery.MetadataRecoveryError, match="blocker list drifted"):
        recovery.verify_metadata_recovery(tampered)
    promoted = json.loads(json.dumps(record))
    promoted["strategy_evaluation_authorized"] = True
    promoted["recovery_canonical_sha256"] = canonical_hash({key: value for key, value in promoted.items() if key != "recovery_canonical_sha256"})
    with pytest.raises(recovery.MetadataRecoveryError, match="strategy_evaluation_authorized"):
        recovery.verify_metadata_recovery(promoted)


def test_readiness_never_authorizes_strategy_even_if_recovery_changes() -> None:
    record, _ = _recovery()
    readiness = recovery.build_metadata_recovery_readiness(record, recovery_package_id="evidence-broker_metadata_recovery-v1-test", recovery_content_sha256="x" * 64)
    assert recovery.verify_metadata_recovery_readiness(readiness)["all_material_metadata_bounded"] is False
    tampered = json.loads(json.dumps(readiness))
    tampered["development_evaluation_sufficient"] = True
    tampered["readiness_canonical_sha256"] = canonical_hash({key: value for key, value in tampered.items() if key != "readiness_canonical_sha256"})
    with pytest.raises(recovery.MetadataRecoveryError, match="development_evaluation_sufficient"):
        recovery.verify_metadata_recovery_readiness(tampered)


def test_publication_is_idempotent_and_conflicting_recovery_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record, _ = _recovery()
    readiness = recovery.build_metadata_recovery_readiness(record, recovery_package_id="placeholder", recovery_content_sha256="p" * 64)
    monkeypatch.setattr(recovery, "build_from_evidence_root", lambda **_: (record, readiness))
    first = recovery.publish_from_evidence_root(data_root=tmp_path, decision_utc=DECISION_UTC)
    second = recovery.publish_from_evidence_root(data_root=tmp_path, decision_utc=DECISION_UTC)
    assert first == second
    conflict, _ = build_evidence_package(kind="broker_metadata_recovery", content={"schema_version": recovery.RECOVERY_SCHEMA_VERSION, "different": True}, source_path=None)
    publish_evidence_package(conflict, evidence_root=tmp_path / "evidence")
    with pytest.raises(recovery.MetadataRecoveryError, match="conflicting Phase 8K"):
        recovery.publish_from_evidence_root(data_root=tmp_path, decision_utc=DECISION_UTC)


def test_phase8k_imports_are_mt5_and_network_free() -> None:
    before = sys.modules.get("MetaTrader5")
    import bot.validation.metadata_recovery as module  # noqa: F401
    import backtests.metadata_recovery_control as cli  # noqa: F401
    assert sys.modules.get("MetaTrader5") is before
    for relative in ("bot/validation/metadata_recovery.py", "backtests/metadata_recovery_control.py"):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for forbidden in ("MetaTrader5", "import requests", "import socket", "order_send", "account_info"):
            assert forbidden not in source
