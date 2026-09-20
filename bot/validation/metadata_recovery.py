"""Phase 8K — append-only recovery of historical broker-metadata evidence.

This overlay is intentionally stricter than a generic metadata importer.  It
can describe what local 2024 quote evidence establishes, but it cannot promote
current broker support material or source-code defaults to historical facts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from bot.acquisition.evidence_contracts import DEVELOPMENT_ONLY_CLASSIFICATION, canonical_hash
from bot.acquisition.evidence_store import (
    build_evidence_package,
    load_evidence_package,
    publish_evidence_package,
)
from bot.validation import metadata_gap_policy as gap_policy


RECOVERY_SCHEMA_VERSION = "phase8k.broker-metadata-recovery.v1"
READINESS_SCHEMA_VERSION = "phase8k.metadata-recovery-readiness.v1"

HISTORICALLY_VERIFIED = "HISTORICALLY_VERIFIED"
EMPIRICALLY_DERIVED = "EMPIRICALLY_DERIVED_FROM_2024_DATA"
EMPIRICALLY_BOUNDED = "EMPIRICALLY_BOUNDED"
CURRENT_ONLY = "CURRENT_ONLY"
ASSUMPTION_ONLY = "ASSUMPTION_ONLY"
UNAVAILABLE = "UNAVAILABLE"
VALID_STATUSES = frozenset(
    {
        HISTORICALLY_VERIFIED,
        EMPIRICALLY_DERIVED,
        EMPIRICALLY_BOUNDED,
        CURRENT_ONLY,
        ASSUMPTION_ONLY,
        UNAVAILABLE,
    }
)


class MetadataRecoveryError(RuntimeError):
    """Raised when a recovery record is incomplete, promoted, or tampered."""


def _content_hash(package: Mapping[str, Any]) -> str:
    value = str(package.get("manifest", {}).get("content_canonical_sha256", ""))
    if len(value) != 64:
        raise MetadataRecoveryError("evidence package has no content identity")
    return value


def _load_exact_kind(evidence_root: Path, kind: str) -> tuple[str, dict[str, Any]]:
    matches = sorted(evidence_root.glob(f"evidence-{kind}-v1-*"))
    if len(matches) != 1:
        raise MetadataRecoveryError(f"expected exactly one {kind} evidence package")
    package = load_evidence_package(matches[0])
    if package["manifest"].get("kind") != kind:
        raise MetadataRecoveryError(f"{kind} package kind mismatch")
    return str(package["manifest"]["package_id"]), package


def _field(
    name: str,
    *,
    phase8j_status: str,
    classification: str,
    sources: Sequence[str],
    derivation_or_bound: str,
    material: bool = True,
    conservatively_bounded: bool = False,
) -> dict[str, Any]:
    if classification not in VALID_STATUSES:
        raise MetadataRecoveryError("unknown metadata-recovery classification")
    return {
        "field": name,
        "phase8j_status": phase8j_status,
        "phase8k_classification": classification,
        "evidence_sources": list(sources),
        "derivation_or_bound": derivation_or_bound,
        "material_to_strategy_evaluation": material,
        "conservatively_bounded": conservatively_bounded,
        "blocker_resolved": bool(conservatively_bounded and material),
    }


def _quote_representation_from_manifests(data_root: Path) -> dict[str, Any]:
    """Derive only raw quote serialization evidence from 2024 manifests.

    This deliberately reads small, already-verified manifests rather than tick
    data. The resulting decimal ceiling is not a broker tick-size assertion.
    """
    package_root = Path(data_root) / "exness-tick-history" / "processed"
    manifests = sorted(package_root.glob("year-packages/exness-xauusdm-2024-development-*/manifest.json"))
    if len(manifests) != 1:
        raise MetadataRecoveryError("expected exactly one accepted 2024 tick-year manifest")
    year_path = manifests[0]
    year = json.loads(year_path.read_text(encoding="utf-8"))
    if year.get("symbol") != "XAUUSDm" or year.get("period", {}).get("start_inclusive") != "2024-01-01T00:00:00Z":
        raise MetadataRecoveryError("accepted tick-year manifest identity mismatch")
    annual_hash = str(year.get("statistics", {}).get("canonical_normalized_sha256", ""))
    if len(annual_hash) != 64:
        raise MetadataRecoveryError("accepted tick-year manifest lacks canonical identity")
    monthly = year.get("monthly_packages")
    if not isinstance(monthly, list) or len(monthly) != 12:
        raise MetadataRecoveryError("accepted tick-year manifest lacks twelve monthly identities")
    max_places = 0
    bound_months: list[dict[str, Any]] = []
    for item in monthly:
        package_id = str(item.get("package_id", ""))
        period = str(item.get("period", ""))
        manifest_path = package_root / "packages" / package_id / "manifest.json"
        if not package_id.startswith("exness-xauusdm-2024-") or not manifest_path.is_file():
            raise MetadataRecoveryError("monthly quote manifest is missing or outside 2024")
        actual_manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if actual_manifest_sha != str(item.get("manifest_sha256", "")):
            raise MetadataRecoveryError("monthly quote manifest hash disagrees with annual package")
        monthly_content = json.loads(manifest_path.read_text(encoding="utf-8"))
        precision = monthly_content.get("statistics", {}).get("price_precision", {})
        for side in ("bid_decimal_places", "ask_decimal_places"):
            places = precision.get(side, {})
            if not isinstance(places, Mapping) or not places:
                raise MetadataRecoveryError("monthly quote manifest lacks price precision evidence")
            max_places = max(max_places, max(int(value) for value in places))
        bound_months.append({"period": period, "package_id": package_id, "manifest_sha256": actual_manifest_sha})
    return {
        "year_package_id": str(year.get("package_id", "")),
        "year_canonical_sha256": annual_hash,
        "year_manifest_sha256": hashlib.sha256(year_path.read_bytes()).hexdigest(),
        "months": sorted(bound_months, key=lambda item: item["period"]),
        "maximum_observed_decimal_places": max_places,
        "scope": "RAW_2024_QUOTE_SERIALIZATION_ONLY_NOT_BROKER_ORDER_NORMALIZATION",
    }


def _reconciliation(phase8j: Mapping[str, Any], quote_representation: Mapping[str, Any]) -> list[dict[str, Any]]:
    prior = {str(item["field"]): str(item["historical_status"]) for item in phase8j["fields"]}
    current = ["current broker-support revision; not effective-dated for 2024"]
    quotes = ["accepted 2024 XAUUSDm tick-year manifest", "monthly quote archive manifests"]
    linked = (
        "No accepted 2024 order, fill, account-statement, margin, or P&L record "
        "independently establishes this economic/order constraint; retain fail-closed gate."
    )
    fields = [
        _field("contract_size", phase8j_status=prior["contract_size"], classification=CURRENT_ONLY,
               sources=current, derivation_or_bound=linked),
        _field("point_tick_size", phase8j_status=prior["point_tick_size"], classification=EMPIRICALLY_DERIVED,
               sources=quotes,
               derivation_or_bound=(
                   f"2024 raw quotes serialize up to {quote_representation['maximum_observed_decimal_places']} decimal places, "
                   "establishing observed quote representation only; it does not establish broker point or trade-tick size."
               )),
        _field("tick_value", phase8j_status=prior["tick_value"], classification=UNAVAILABLE,
               sources=["no accepted 2024 account P&L plus independently verified contract relationship"],
               derivation_or_bound=linked),
        _field("minimum_lot", phase8j_status=prior["minimum_lot"], classification=CURRENT_ONLY,
               sources=current + ["2024 archives contain quote ticks, not accepted order volumes"], derivation_or_bound=linked),
        _field("maximum_lot", phase8j_status=prior["maximum_lot"], classification=CURRENT_ONLY,
               sources=current + ["2024 archives contain quote ticks, not accepted order volumes"], derivation_or_bound=linked),
        _field("volume_step", phase8j_status=prior["volume_step"], classification=UNAVAILABLE,
               sources=["no accepted 2024 order/fill volume series"], derivation_or_bound=linked),
        _field("margin_leverage_rules", phase8j_status=prior["margin_leverage_rules"], classification=CURRENT_ONLY,
               sources=current + ["current support/display conflict retained"], derivation_or_bound=linked),
        _field("order_filling_modes", phase8j_status=prior["order_filling_modes"], classification=CURRENT_ONLY,
               sources=current, derivation_or_bound=linked),
        _field("stops_level", phase8j_status=prior["stops_level"], classification=UNAVAILABLE,
               sources=["no effective-dated 2024 stop-distance export or terminal log"], derivation_or_bound=(
                   "No predeclared numeric bound is demonstrably stricter than an unknown historical "
                   "broker constraint across all execution behavior; retain fail-closed gate."
               )),
        _field("freeze_level", phase8j_status=prior["freeze_level"], classification=UNAVAILABLE,
               sources=["no effective-dated 2024 freeze-level export or terminal log"], derivation_or_bound=(
                   "No predeclared numeric bound is demonstrably stricter than an unknown historical "
                   "broker constraint across all execution behavior; retain fail-closed gate."
               )),
        _field("symbol_specific_execution_or_pnl_restrictions",
               phase8j_status=prior["symbol_specific_execution_or_pnl_restrictions"], classification=CURRENT_ONLY,
               sources=current + ["accepted quote archives do not carry account or execution restrictions"],
               derivation_or_bound=linked),
    ]
    return fields


def build_metadata_recovery(
    *,
    phase8j_policy: Mapping[str, Any],
    phase8j_policy_package_id: str,
    phase8j_policy_content_sha256: str,
    phase8j_readiness: Mapping[str, Any],
    phase8j_readiness_package_id: str,
    phase8j_readiness_content_sha256: str,
    accepted_review: Mapping[str, Any],
    accepted_review_package_id: str,
    accepted_review_content_sha256: str,
    quote_representation: Mapping[str, Any],
    decision_utc: str,
) -> dict[str, Any]:
    """Build a deterministic recovery record without changing Phase 8J."""
    gap_policy.verify_metadata_gap_policy(phase8j_policy)
    gap_policy.verify_metadata_gap_readiness(phase8j_readiness)
    if str(phase8j_readiness["metadata_gap_policy"]["package_id"]) != phase8j_policy_package_id:
        raise MetadataRecoveryError("Phase 8J readiness does not bind supplied policy")
    if int(quote_representation.get("maximum_observed_decimal_places", 0)) <= 0:
        raise MetadataRecoveryError("quote representation has no observed precision")
    if len(str(quote_representation.get("year_canonical_sha256", ""))) != 64:
        raise MetadataRecoveryError("quote representation lacks annual canonical identity")
    fields = _reconciliation(phase8j_policy, quote_representation)
    blockers = sorted(item["field"] for item in fields if item["material_to_strategy_evaluation"] and not item["conservatively_bounded"])
    content: dict[str, Any] = {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "record": "Phase 8K historical broker metadata recovery and conservative bounding",
        "decision_utc": decision_utc,
        "recovery_method": "LOCAL_READ_ONLY_ARTIFACT_AUDIT",
        "bindings": {
            "phase8j_policy": {"package_id": phase8j_policy_package_id, "content_canonical_sha256": phase8j_policy_content_sha256},
            "phase8j_readiness": {"package_id": phase8j_readiness_package_id, "content_canonical_sha256": phase8j_readiness_content_sha256},
            "phase8i_acceptance_review": {"package_id": accepted_review_package_id, "content_canonical_sha256": accepted_review_content_sha256},
            "accepted_2024_quote_representation": dict(quote_representation),
        },
        "sources_searched": [
            "repository source and diagnostic filenames (read-only; implementation defaults excluded as broker evidence)",
            "Phase 8 immutable evidence packages and accepted 2024 tick/candle/spread manifests",
            "owner-preserved 2024 XAUUSDm quote archives (read-only filename/member audit)",
            "owner Documents, Desktop, and Downloads filename audit for reports, statements, logs, exports, and screenshots",
        ],
        "source_audit_findings": [
            "accepted 2024 archive schema is quote-only: provider, symbol, timestamp, bid, ask",
            "no local effective-dated 2024 broker specification, order/fill report, account statement, terminal journal, or symbol_info dump was discovered",
            "current broker-support/screenshot evidence remains current-only and is not promoted",
            "source-code defaults and synthetic fixtures are expressly excluded as broker metadata evidence",
        ],
        "fields": fields,
        "all_material_metadata_bounded": not blockers,
        "development_metadata_gap_acceptable": not blockers,
        "development_evaluation_sufficient": False,
        "strategy_evaluation_authorized": False,
        "accepted_for_final_validation": False,
        "remaining_blockers": blockers,
        "future_official_metadata_protocol": list(phase8j_policy["future_official_metadata_protocol"]),
        "strategy_execution_checkpoint": "SEPARATE_EXPLICIT_GOVERNANCE_REQUIRED",
    }
    content["recovery_canonical_sha256"] = canonical_hash(content)
    verify_metadata_recovery(content)
    return content


def verify_metadata_recovery(content: Mapping[str, Any]) -> dict[str, Any]:
    if content.get("schema_version") != RECOVERY_SCHEMA_VERSION:
        raise MetadataRecoveryError("metadata-recovery schema mismatch")
    fields = content.get("fields")
    if not isinstance(fields, list) or not fields:
        raise MetadataRecoveryError("metadata recovery requires a field reconciliation")
    names = [str(item.get("field", "")) for item in fields if isinstance(item, Mapping)]
    if len(names) != len(fields) or len(names) != len(set(names)):
        raise MetadataRecoveryError("metadata recovery field identities are invalid")
    blockers = sorted(str(item["field"]) for item in fields if item.get("material_to_strategy_evaluation") and not item.get("conservatively_bounded"))
    if content.get("remaining_blockers") != blockers:
        raise MetadataRecoveryError("metadata recovery blocker list drifted")
    bounded = not blockers
    if content.get("all_material_metadata_bounded") is not bounded:
        raise MetadataRecoveryError("metadata recovery bounded gate drifted")
    if content.get("development_metadata_gap_acceptable") is not bounded:
        raise MetadataRecoveryError("metadata recovery acceptability drifted")
    for gate in ("development_evaluation_sufficient", "strategy_evaluation_authorized", "accepted_for_final_validation"):
        if content.get(gate) is not False:
            raise MetadataRecoveryError(f"metadata recovery gate {gate} must remain false")
    for item in fields:
        if item.get("phase8k_classification") not in VALID_STATUSES:
            raise MetadataRecoveryError("metadata recovery has an unknown classification")
        if item.get("blocker_resolved") != bool(item.get("material_to_strategy_evaluation") and item.get("conservatively_bounded")):
            raise MetadataRecoveryError("metadata recovery blocker resolution drifted")
    payload = {key: value for key, value in content.items() if key != "recovery_canonical_sha256"}
    if content.get("recovery_canonical_sha256") != canonical_hash(payload):
        raise MetadataRecoveryError("metadata recovery hash mismatch (tampering detected)")
    return {"verified": True, "all_material_metadata_bounded": bounded, "remaining_blockers": blockers}


def build_metadata_recovery_readiness(
    recovery: Mapping[str, Any], *, recovery_package_id: str, recovery_content_sha256: str
) -> dict[str, Any]:
    report = verify_metadata_recovery(recovery)
    content: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "record": "Phase 8K metadata recovery readiness overlay",
        "metadata_recovery": {"package_id": recovery_package_id, "content_canonical_sha256": recovery_content_sha256,
                              "recovery_canonical_sha256": str(recovery["recovery_canonical_sha256"])},
        "all_material_metadata_bounded": bool(report["all_material_metadata_bounded"]),
        "development_metadata_gap_acceptable": bool(report["all_material_metadata_bounded"]),
        "development_evaluation_sufficient": False,
        "strategy_evaluation_authorized": False,
        "accepted_for_final_validation": False,
        "holdout_access_authorized": False,
        "remaining_blockers": list(report["remaining_blockers"]),
        "next_checkpoint": "obtain effective-dated 2024 broker metadata or independently verifiable historical execution records, then issue a new immutable review",
    }
    content["readiness_canonical_sha256"] = canonical_hash(content)
    verify_metadata_recovery_readiness(content)
    return content


def verify_metadata_recovery_readiness(content: Mapping[str, Any]) -> dict[str, Any]:
    if content.get("schema_version") != READINESS_SCHEMA_VERSION:
        raise MetadataRecoveryError("metadata recovery readiness schema mismatch")
    for gate in ("development_evaluation_sufficient", "strategy_evaluation_authorized", "accepted_for_final_validation", "holdout_access_authorized"):
        if content.get(gate) is not False:
            raise MetadataRecoveryError(f"metadata recovery readiness gate {gate} must remain false")
    payload = {key: value for key, value in content.items() if key != "readiness_canonical_sha256"}
    if content.get("readiness_canonical_sha256") != canonical_hash(payload):
        raise MetadataRecoveryError("metadata recovery readiness hash mismatch (tampering detected)")
    return {"verified": True, "all_material_metadata_bounded": bool(content["all_material_metadata_bounded"])}


def build_from_evidence_root(*, data_root: Path, decision_utc: str) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence_root = Path(data_root) / "evidence"
    policy_id, policy_package = _load_exact_kind(evidence_root, "broker_metadata_gap_policy")
    readiness_id, readiness_package = _load_exact_kind(evidence_root, "metadata_gap_readiness")
    review_id, review_package = _load_exact_kind(evidence_root, "dataset_acceptance_review")
    quote_representation = _quote_representation_from_manifests(data_root)
    recovery = build_metadata_recovery(
        phase8j_policy=dict(policy_package["content"]), phase8j_policy_package_id=policy_id,
        phase8j_policy_content_sha256=_content_hash(policy_package),
        phase8j_readiness=dict(readiness_package["content"]), phase8j_readiness_package_id=readiness_id,
        phase8j_readiness_content_sha256=_content_hash(readiness_package),
        accepted_review=dict(review_package["content"]), accepted_review_package_id=review_id,
        accepted_review_content_sha256=_content_hash(review_package), quote_representation=quote_representation,
        decision_utc=decision_utc,
    )
    package, package_id = build_evidence_package(kind="broker_metadata_recovery", content=recovery, source_path=None)
    readiness = build_metadata_recovery_readiness(recovery, recovery_package_id=package_id, recovery_content_sha256=_content_hash(package))
    return recovery, readiness


def publish_from_evidence_root(*, data_root: Path, decision_utc: str) -> dict[str, str]:
    evidence_root = Path(data_root) / "evidence"
    recovery, readiness = build_from_evidence_root(data_root=data_root, decision_utc=decision_utc)
    package, recovery_id = build_evidence_package(kind="broker_metadata_recovery", content=recovery, source_path=None)
    existing = sorted(evidence_root.glob("evidence-broker_metadata_recovery-v1-*"))
    if any(path.name != recovery_id for path in existing):
        raise MetadataRecoveryError("conflicting Phase 8K metadata recovery already published")
    _, recovery_id = publish_evidence_package(package, evidence_root=evidence_root)
    readiness = build_metadata_recovery_readiness(recovery, recovery_package_id=recovery_id, recovery_content_sha256=_content_hash(package))
    readiness_package, readiness_id = build_evidence_package(kind="metadata_recovery_readiness", content=readiness, source_path=None)
    existing = sorted(evidence_root.glob("evidence-metadata_recovery_readiness-v1-*"))
    if any(path.name != readiness_id for path in existing):
        raise MetadataRecoveryError("conflicting Phase 8K metadata recovery readiness already published")
    publish_evidence_package(readiness_package, evidence_root=evidence_root)
    return {"recovery_package_id": recovery_id, "readiness_package_id": readiness_id}
