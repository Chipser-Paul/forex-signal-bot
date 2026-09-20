"""Phase 8J — immutable broker-metadata uncertainty decisions.

This module deliberately does not turn a current broker specification into a
historical fact.  It creates a separate, hash-bound decision record that sits
beside the Phase 8I acceptance review.  The record is an overlay: it neither
rewrites the review nor starts a strategy evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from bot.acquisition.evidence_contracts import DEVELOPMENT_ONLY_CLASSIFICATION, canonical_hash
from bot.acquisition.evidence_store import (
    EvidenceStoreError,
    build_evidence_package,
    load_evidence_package,
    publish_evidence_package,
)
from bot.validation import cost_policy_activation as activation


POLICY_SCHEMA_VERSION = "phase8j.broker-metadata-gap-policy.v1"
READINESS_SCHEMA_VERSION = "phase8j.metadata-gap-readiness.v1"

HISTORICALLY_VERIFIED = "HISTORICALLY_VERIFIED"
EMPIRICALLY_DERIVED = "EMPIRICALLY_DERIVED_FROM_2024_DATA"
CURRENT_ONLY = "CURRENT_ONLY"
ASSUMPTION_ONLY = "ASSUMPTION_ONLY"
UNAVAILABLE = "UNAVAILABLE"
_HISTORICAL_STATUSES = frozenset(
    {HISTORICALLY_VERIFIED, EMPIRICALLY_DERIVED, CURRENT_ONLY, ASSUMPTION_ONLY, UNAVAILABLE}
)


class MetadataGapPolicyError(RuntimeError):
    """Raised when the append-only metadata-gap decision is not trustworthy."""


def _content_hash(package: Mapping[str, Any]) -> str:
    manifest = package.get("manifest", {})
    value = str(manifest.get("content_canonical_sha256", ""))
    if len(value) != 64:
        raise MetadataGapPolicyError("evidence package is missing its content identity")
    return value


def _load_exact_kind(evidence_root: Path, kind: str) -> tuple[str, dict[str, Any]]:
    matches = sorted(evidence_root.glob(f"evidence-{kind}-v1-*"))
    if len(matches) != 1:
        raise MetadataGapPolicyError(f"expected exactly one {kind} evidence package")
    package = load_evidence_package(matches[0])
    if package["manifest"].get("kind") != kind:
        raise MetadataGapPolicyError(f"{kind} package kind mismatch")
    return str(package["manifest"]["package_id"]), package


def _load_broker_support_revisions(evidence_root: Path) -> list[dict[str, str]]:
    revisions: list[dict[str, str]] = []
    for package_dir in sorted(evidence_root.glob("evidence-broker_support-v1-*")):
        package = load_evidence_package(package_dir)
        manifest = package["manifest"]
        if manifest.get("kind") != "broker_support":
            raise MetadataGapPolicyError("broker-support package kind mismatch")
        revisions.append(
            {
                "package_id": str(manifest["package_id"]),
                "content_canonical_sha256": _content_hash(package),
            }
        )
    if not revisions:
        raise MetadataGapPolicyError("no broker-support evidence revision is available")
    return revisions


def _field(
    field_id: str,
    *,
    available_evidence: Sequence[str],
    evidence_strength: str,
    historical_status: str,
    material: bool,
    conservatively_bounded: bool,
    conservative_treatment: str,
    blocks_development: bool,
) -> dict[str, Any]:
    if historical_status not in _HISTORICAL_STATUSES:
        raise MetadataGapPolicyError("unknown historical-status classification")
    if blocks_development and (not material or conservatively_bounded):
        raise MetadataGapPolicyError("only material, unbounded fields may block development")
    return {
        "field": field_id,
        "available_evidence": list(available_evidence),
        "evidence_strength": evidence_strength,
        "historical_status": historical_status,
        "material_to_strategy_evaluation": material,
        "conservatively_bounded": conservatively_bounded,
        "conservative_treatment": conservative_treatment,
        "blocks_development_evaluation": blocks_development,
    }


def _field_review() -> list[dict[str, Any]]:
    """Classify every execution-relevant metadata field without extrapolation.

    The current support record is deliberately useful only as an explicit
    current reference.  A missing historical upper/lower bound is not repaired
    by choosing a convenient numeric value.
    """

    current = ["current broker-support claim revision; not 2024-effective"]
    empirical_ticks = ["accepted 2024 XAUUSDm tick/candle/spread evidence"]
    return [
        _field(
            "contract_size",
            available_evidence=current + ["support.contract_size_100_oz"],
            evidence_strength=CURRENT_ONLY,
            historical_status=CURRENT_ONLY,
            material=True,
            conservatively_bounded=False,
            conservative_treatment="FAIL_CLOSED_NO_NUMERIC_CONTRACT_SIZE_ASSUMPTION",
            blocks_development=True,
        ),
        _field(
            "digits_price_precision",
            available_evidence=empirical_ticks + ["current MT5 specification observation"],
            evidence_strength=EMPIRICALLY_DERIVED,
            historical_status=EMPIRICALLY_DERIVED,
            material=True,
            conservatively_bounded=True,
            conservative_treatment=(
                "use only observed 2024 quote representation for replay parsing; "
                "do not infer a historical broker order-normalization rule"
            ),
            blocks_development=False,
        ),
        _field(
            "point_tick_size",
            available_evidence=current + ["support.pip_size_0_01", "current MT5 point observation"],
            evidence_strength=CURRENT_ONLY,
            historical_status=CURRENT_ONLY,
            material=True,
            conservatively_bounded=False,
            conservative_treatment="FAIL_CLOSED_NO_HISTORICAL_POINT_OR_TICK_SIZE_ASSUMPTION",
            blocks_development=True,
        ),
        _field(
            "tick_value",
            available_evidence=current + ["current unit-normalization reference"],
            evidence_strength=CURRENT_ONLY,
            historical_status=CURRENT_ONLY,
            material=True,
            conservatively_bounded=False,
            conservative_treatment="FAIL_CLOSED_NO_HISTORICAL_TICK_VALUE_ASSUMPTION",
            blocks_development=True,
        ),
        _field(
            "minimum_lot",
            available_evidence=current + ["support.volume_min_0_01"],
            evidence_strength=CURRENT_ONLY,
            historical_status=CURRENT_ONLY,
            material=True,
            conservatively_bounded=False,
            conservative_treatment="FAIL_CLOSED_NO_HISTORICAL_MINIMUM_LOT_ASSUMPTION",
            blocks_development=True,
        ),
        _field(
            "maximum_lot",
            available_evidence=current + ["support.volume_max_day_night"],
            evidence_strength=CURRENT_ONLY,
            historical_status=CURRENT_ONLY,
            material=True,
            conservatively_bounded=False,
            conservative_treatment="FAIL_CLOSED_NO_HISTORICAL_MAXIMUM_LOT_ASSUMPTION",
            blocks_development=True,
        ),
        _field(
            "volume_step",
            available_evidence=current,
            evidence_strength=CURRENT_ONLY,
            historical_status=CURRENT_ONLY,
            material=True,
            conservatively_bounded=False,
            conservative_treatment="FAIL_CLOSED_NO_HISTORICAL_VOLUME_STEP_ASSUMPTION",
            blocks_development=True,
        ),
        _field(
            "margin_leverage_rules",
            available_evidence=current + ["support.margin_fixed_1_200", "margin-display conflict"],
            evidence_strength=CURRENT_ONLY,
            historical_status=CURRENT_ONLY,
            material=True,
            conservatively_bounded=False,
            conservative_treatment="FAIL_CLOSED_MARGIN_AND_LEVERAGE_CONFLICT_UNRESOLVED",
            blocks_development=True,
        ),
        _field(
            "execution_mode",
            available_evidence=current + ["support.market_execution"],
            evidence_strength=CURRENT_ONLY,
            historical_status=ASSUMPTION_ONLY,
            material=True,
            conservatively_bounded=True,
            conservative_treatment=(
                "development-only MARKET_ON_TRIGGER model with adverse-cost scenarios; "
                "never claim historical broker execution-mode verification"
            ),
            blocks_development=False,
        ),
        _field(
            "order_filling_modes",
            available_evidence=current,
            evidence_strength=CURRENT_ONLY,
            historical_status=CURRENT_ONLY,
            material=True,
            conservatively_bounded=False,
            conservative_treatment="FAIL_CLOSED_NO_HISTORICAL_FILLING_MODE_ASSUMPTION",
            blocks_development=True,
        ),
        _field(
            "stops_level",
            available_evidence=["no effective-dated 2024 stop-distance evidence"],
            evidence_strength=UNAVAILABLE,
            historical_status=UNAVAILABLE,
            material=True,
            conservatively_bounded=False,
            conservative_treatment="FAIL_CLOSED_NO_HISTORICAL_STOPS_LEVEL_BOUND",
            blocks_development=True,
        ),
        _field(
            "freeze_level",
            available_evidence=["no effective-dated 2024 freeze-level evidence"],
            evidence_strength=UNAVAILABLE,
            historical_status=UNAVAILABLE,
            material=True,
            conservatively_bounded=False,
            conservative_treatment="FAIL_CLOSED_NO_HISTORICAL_FREEZE_LEVEL_BOUND",
            blocks_development=True,
        ),
        _field(
            "trading_sessions_instrument_availability",
            available_evidence=empirical_ticks,
            evidence_strength=EMPIRICALLY_DERIVED,
            historical_status=EMPIRICALLY_DERIVED,
            material=True,
            conservatively_bounded=True,
            conservative_treatment=(
                "replay only observed 2024 bid/ask availability; missing intervals remain "
                "unavailable and are not represented as broker-published session policy"
            ),
            blocks_development=False,
        ),
        _field(
            "symbol_specific_execution_or_pnl_restrictions",
            available_evidence=current + ["support conditions are not effective-dated"],
            evidence_strength=CURRENT_ONLY,
            historical_status=CURRENT_ONLY,
            material=True,
            conservatively_bounded=False,
            conservative_treatment="FAIL_CLOSED_UNKNOWN_HISTORICAL_SYMBOL_RESTRICTIONS",
            blocks_development=True,
        ),
    ]


def _verify_hash_bound_policy(content: Mapping[str, Any]) -> dict[str, Any]:
    if content.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise MetadataGapPolicyError("metadata-gap policy schema mismatch")
    fields = content.get("fields")
    if not isinstance(fields, list) or not fields:
        raise MetadataGapPolicyError("metadata-gap policy requires a field review")
    field_names = [str(item.get("field", "")) for item in fields if isinstance(item, Mapping)]
    if len(field_names) != len(fields) or len(field_names) != len(set(field_names)):
        raise MetadataGapPolicyError("metadata-gap policy field identities are invalid")
    blockers = sorted(
        str(item["field"])
        for item in fields
        if item.get("material_to_strategy_evaluation") and item.get("blocks_development_evaluation")
    )
    if content.get("unresolved_blockers") != blockers:
        raise MetadataGapPolicyError("metadata-gap policy blocker list drifted")
    acceptable = not blockers
    if content.get("development_metadata_gap_acceptable") is not acceptable:
        raise MetadataGapPolicyError("metadata-gap policy acceptability drifted")
    for gate in ("strategy_evaluation_authorized", "accepted_for_final_validation"):
        if content.get(gate) is not False:
            raise MetadataGapPolicyError(f"metadata-gap policy gate {gate} must remain false")
    if content.get("development_evaluation_sufficient") is not acceptable:
        raise MetadataGapPolicyError("metadata-gap policy development sufficiency drifted")
    recorded = content.get("policy_canonical_sha256")
    payload = {key: value for key, value in content.items() if key != "policy_canonical_sha256"}
    if recorded != canonical_hash(payload):
        raise MetadataGapPolicyError("metadata-gap policy hash mismatch (tampering detected)")
    return {"verified": True, "unresolved_blockers": blockers, "acceptable": acceptable}


def build_metadata_gap_policy(
    *,
    acceptance_review: Mapping[str, Any],
    acceptance_review_package_id: str,
    acceptance_review_content_sha256: str,
    policy_report: Mapping[str, Any],
    activation_content: Mapping[str, Any],
    activation_package_id: str,
    activation_content_sha256: str,
    broker_support_revisions: Sequence[Mapping[str, str]],
    decision_utc: str,
) -> dict[str, Any]:
    """Build a deterministic, non-promoting Phase 8J policy record."""

    activation.verify_activation_record(activation_content)
    activation.verify_acceptance_review(acceptance_review)
    review_basis = acceptance_review.get("review_basis", {})
    if not isinstance(review_basis, Mapping):
        raise MetadataGapPolicyError("Phase 8I review has no review basis")
    if str(review_basis.get("cost_policy_fingerprint")) != str(policy_report.get("policy_fingerprint")):
        raise MetadataGapPolicyError("Phase 8I review does not bind the active cost-policy fingerprint")
    activated = activation_content.get("activated_policy", {})
    if (
        str(activated.get("package_id")) != str(policy_report.get("package_id"))
        or str(activated.get("policy_fingerprint")) != str(policy_report.get("policy_fingerprint"))
    ):
        raise MetadataGapPolicyError("active swap policy does not bind the reviewed cost policy")
    support_ids = {str(item.get("package_id", "")) for item in broker_support_revisions}
    active_support = str(review_basis.get("verified_evidence_packages", {}).get("broker_support_revision", ""))
    if not active_support or active_support not in support_ids:
        raise MetadataGapPolicyError("current broker-metadata evidence is not among verified support revisions")

    fields = _field_review()
    blockers = sorted(str(item["field"]) for item in fields if item["blocks_development_evaluation"])
    market_chain = review_basis.get("verified_market_data_chain", {})
    official_news = review_basis.get("verified_official_news", {})
    content: dict[str, Any] = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "record": "Phase 8J historical broker metadata gap policy",
        "owner_decision": {
            "decision": "REVIEW_ASSUMPTION_ONLY_BROKER_METADATA_GAP_FOR_DEVELOPMENT_ONLY",
            "decision_utc": decision_utc,
            "historical_effective_dated_2024_metadata_available": False,
            "official_exness_request_pending": True,
            "exness_definitively_cannot_provide_historical_metadata": False,
        },
        "bindings": {
            "phase8i_acceptance_review": {
                "package_id": acceptance_review_package_id,
                "content_canonical_sha256": acceptance_review_content_sha256,
                "review_canonical_sha256": str(acceptance_review.get("review_canonical_sha256", "")),
            },
            "phase8h_development_cost_policy": {
                "package_id": str(policy_report["package_id"]),
                "policy_fingerprint": str(policy_report["policy_fingerprint"]),
            },
            "phase8i_swap_policy_activation": {
                "package_id": activation_package_id,
                "content_canonical_sha256": activation_content_sha256,
                "activation_state": str(activation_content.get("activation_state", "")),
            },
            "broker_support_revisions": sorted((dict(item) for item in broker_support_revisions), key=lambda item: item["package_id"]),
            "current_broker_metadata_evidence": {"package_id": active_support},
            "accepted_2024_evidence": {
                "ticks_candles_spread_dxy": dict(market_chain),
                "official_news": dict(official_news),
            },
        },
        "fields": fields,
        "unresolved_blockers": blockers,
        "development_metadata_gap_acceptable": not blockers,
        "development_evaluation_sufficient": not blockers,
        "strategy_evaluation_authorized": False,
        "accepted_for_final_validation": False,
        "prohibitions": [
            "CHERRY_PICKING_ASSUMPTIONS_PROHIBITED",
            "CURRENT_METADATA_AS_HISTORICAL_FACT_PROHIBITED",
            "METADATA_SCENARIO_PARAMETER_OPTIMIZATION_PROHIBITED",
            "DROP_ADVERSE_METADATA_SCENARIO_PROHIBITED",
            "RETROACTIVE_ASSUMPTION_CHANGE_AFTER_RESULTS_PROHIBITED",
            "HOLDOUT_ACCESS_PROHIBITED",
            "STRATEGY_EVALUATION_REQUIRES_SEPARATE_EXPLICIT_AUTHORIZATION",
        ],
        "future_official_metadata_protocol": [
            "INGEST_NEW_IMMUTABLE_EVIDENCE_REVISION",
            "COMPARE_OFFICIAL_VALUES_TO_EVERY_PROVISIONAL_ASSUMPTION",
            "REPORT_ALL_MISMATCHES",
            "RERUN_DATASET_ACCEPTANCE",
            "INVALIDATE_OR_RERUN_MATERIALLY_AFFECTED_DEVELOPMENT_RESULTS",
            "NEVER_REPLACE_PRIOR_ASSUMPTIONS_SILENTLY",
        ],
    }
    content["policy_canonical_sha256"] = canonical_hash(content)
    _verify_hash_bound_policy(content)
    return content


def verify_metadata_gap_policy(content: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a policy loaded from an immutable evidence package."""
    return _verify_hash_bound_policy(content)


def build_metadata_gap_readiness(
    policy: Mapping[str, Any],
    *,
    policy_package_id: str,
    policy_content_sha256: str,
) -> dict[str, Any]:
    """Create the append-only readiness overlay; it never authorizes a run."""
    report = verify_metadata_gap_policy(policy)
    acceptable = bool(report["acceptable"])
    content: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "record": "Phase 8J metadata-gap dataset acceptance and readiness overlay",
        "metadata_gap_policy": {
            "package_id": policy_package_id,
            "content_canonical_sha256": policy_content_sha256,
            "policy_canonical_sha256": str(policy["policy_canonical_sha256"]),
        },
        "development_metadata_gap_acceptable": acceptable,
        "development_evaluation_sufficient": acceptable,
        "strategy_evaluation_authorized": False,
        "accepted_for_final_validation": False,
        "holdout_access_authorized": False,
        "unresolved_blockers": list(report["unresolved_blockers"]),
        "next_checkpoint": (
            "obtain effective-dated 2024 broker metadata that bounds every unresolved "
            "material field, then issue a new immutable evidence revision and re-review"
        ),
    }
    content["readiness_canonical_sha256"] = canonical_hash(content)
    return content


def verify_metadata_gap_readiness(content: Mapping[str, Any]) -> dict[str, Any]:
    if content.get("schema_version") != READINESS_SCHEMA_VERSION:
        raise MetadataGapPolicyError("metadata-gap readiness schema mismatch")
    acceptable = bool(content.get("development_metadata_gap_acceptable"))
    if content.get("development_evaluation_sufficient") is not acceptable:
        raise MetadataGapPolicyError("metadata-gap readiness sufficiency drifted")
    for gate in ("strategy_evaluation_authorized", "accepted_for_final_validation", "holdout_access_authorized"):
        if content.get(gate) is not False:
            raise MetadataGapPolicyError(f"metadata-gap readiness gate {gate} must remain false")
    payload = {key: value for key, value in content.items() if key != "readiness_canonical_sha256"}
    if content.get("readiness_canonical_sha256") != canonical_hash(payload):
        raise MetadataGapPolicyError("metadata-gap readiness hash mismatch (tampering detected)")
    if not acceptable and not content.get("unresolved_blockers"):
        raise MetadataGapPolicyError("blocked readiness requires explicit blockers")
    return {"verified": True, "acceptable": acceptable}


def build_from_evidence_root(*, data_root: Path, decision_utc: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load all bound evidence read-only and build the policy plus readiness overlay."""
    evidence_root = Path(data_root) / "evidence"
    review_id, review_package = _load_exact_kind(evidence_root, "dataset_acceptance_review")
    review = dict(review_package["content"])
    activation_id, activation_package = _load_exact_kind(evidence_root, "cost_policy_activation")
    policy_report = activation.verify_published_policy(evidence_root)
    policy = build_metadata_gap_policy(
        acceptance_review=review,
        acceptance_review_package_id=review_id,
        acceptance_review_content_sha256=_content_hash(review_package),
        policy_report=policy_report,
        activation_content=dict(activation_package["content"]),
        activation_package_id=activation_id,
        activation_content_sha256=_content_hash(activation_package),
        broker_support_revisions=_load_broker_support_revisions(evidence_root),
        decision_utc=decision_utc,
    )
    policy_package, policy_id = build_evidence_package(
        kind="broker_metadata_gap_policy", content=policy, source_path=None
    )
    readiness = build_metadata_gap_readiness(
        policy,
        policy_package_id=policy_id,
        policy_content_sha256=_content_hash(policy_package),
    )
    return policy, readiness


def publish_from_evidence_root(*, data_root: Path, decision_utc: str) -> dict[str, str]:
    """Atomically publish the two append-only Phase 8J records.

    A conflicting existing Phase 8J policy is rejected instead of being silently
    superseded.  A later official evidence intake must deliberately introduce a
    new schema/review path and preserve this record.
    """
    evidence_root = Path(data_root) / "evidence"
    policy, readiness = build_from_evidence_root(data_root=data_root, decision_utc=decision_utc)
    policy_package, policy_id = build_evidence_package(
        kind="broker_metadata_gap_policy", content=policy, source_path=None
    )
    existing = sorted(evidence_root.glob("evidence-broker_metadata_gap_policy-v1-*"))
    if any(path.name != policy_id for path in existing):
        raise MetadataGapPolicyError("conflicting Phase 8J metadata-gap policy already published")
    policy_dir, published_policy_id = publish_evidence_package(policy_package, evidence_root=evidence_root)
    readiness = build_metadata_gap_readiness(
        policy,
        policy_package_id=published_policy_id,
        policy_content_sha256=_content_hash(policy_package),
    )
    readiness_package, readiness_id = build_evidence_package(
        kind="metadata_gap_readiness", content=readiness, source_path=None
    )
    existing_readiness = sorted(evidence_root.glob("evidence-metadata_gap_readiness-v1-*"))
    if any(path.name != readiness_id for path in existing_readiness):
        raise MetadataGapPolicyError("conflicting Phase 8J metadata-gap readiness already published")
    readiness_dir, published_readiness_id = publish_evidence_package(
        readiness_package, evidence_root=evidence_root
    )
    if not policy_dir.is_dir() or not readiness_dir.is_dir():
        raise MetadataGapPolicyError("metadata-gap publication did not complete")
    return {"policy_package_id": published_policy_id, "readiness_package_id": published_readiness_id}
