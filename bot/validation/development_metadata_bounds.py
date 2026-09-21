"""Phase 8L — owner-authorized, development-only broker metadata proxies.

The contract turns documented absence of historical broker terms into a fixed
scenario ladder. It is not a historical specification and cannot authorize a
strategy run, holdout access, final validation, or deployment.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_FLOOR
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from datetime import timezone
from pathlib import Path
from typing import Any, Mapping

from bot.acquisition.evidence_contracts import DEVELOPMENT_ONLY_CLASSIFICATION, canonical_hash
from bot.acquisition.evidence_store import build_evidence_package, load_evidence_package, publish_evidence_package
from bot.validation import cost_policy
from bot.validation import metadata_recovery


UNAVAILABILITY_SCHEMA_VERSION = "phase8l.official-historical-metadata-unavailable.v1"
POLICY_SCHEMA_VERSION = "phase8l.development-metadata-bounds.v1"
READINESS_SCHEMA_VERSION = "phase8l.development-metadata-bounds-readiness.v1"
OFFICIAL_UNAVAILABLE = "OFFICIAL_HISTORICAL_METADATA_UNAVAILABLE"
PROXY_ASSUMPTION = "ASSUMPTION_ONLY_DEVELOPMENT_PROXY"
CURRENT_REFERENCE = "CURRENT_ONLY_REFERENCE"
EMPIRICAL = "EMPIRICALLY_DERIVED_FROM_2024_DATA"

REQUIRED_NEGATIVE_STATEMENTS = {
    "ARCHIVED_2024_CONTRACT_SPECIFICATION_UNAVAILABLE": "archived contract specification document",
    "HISTORICAL_TRADING_TERMS_PAGE_UNAVAILABLE": "historical trading terms page",
    "HISTORICAL_MARGIN_RULES_UNAVAILABLE": "historical margin rules",
    "HISTORICAL_STOP_DISTANCES_UNAVAILABLE": "stop distances",
    "HISTORICAL_EXECUTION_MODES_UNAVAILABLE": "execution modes",
}
SCENARIO_ORDER = (
    "BASELINE_CURRENT_REFERENCE_PROXY",
    "REDUCED_MAXIMUM_VOLUME",
    "STRICTER_MARGIN_REQUIREMENT",
    "CONSTRAINED_FREE_MARGIN",
    "FOK_MISSED_FILL_STRESS",
    "PARTIAL_FILL_REDUCED_LIQUIDITY",
    "STOP_FREEZE_RESTRICTION_GUARD",
    "MINIMUM_VOLUME_RISK_BUDGET_FAILURE",
    "STALE_METADATA_REJECTION",
    "COMBINED_ADVERSE_BROKER_CONDITIONS",
)


class DevelopmentMetadataBoundsError(RuntimeError):
    """Raised for unsafe email evidence, policy drift, or publication conflict."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _content_hash(package: Mapping[str, Any]) -> str:
    value = str(package.get("manifest", {}).get("content_canonical_sha256", ""))
    if len(value) != 64:
        raise DevelopmentMetadataBoundsError("evidence package has no content hash")
    return value


def _load_exact_kind(root: Path, kind: str) -> tuple[str, dict[str, Any]]:
    matches = sorted(Path(root).glob(f"evidence-{kind}-v1-*"))
    if len(matches) != 1:
        raise DevelopmentMetadataBoundsError(f"expected exactly one {kind} package")
    package = load_evidence_package(matches[0])
    if package["manifest"].get("kind") != kind:
        raise DevelopmentMetadataBoundsError(f"{kind} package kind mismatch")
    return str(package["manifest"]["package_id"]), package


def _plain_reply(message: Any) -> str:
    parts = [
        part.get_content()
        for part in message.walk()
        if part.get_content_type() == "text/plain" and not part.get_content_disposition()
    ]
    if len(parts) != 1 or not isinstance(parts[0], str):
        raise DevelopmentMetadataBoundsError("email has no unambiguous primary plain-text reply")
    return parts[0].split("--------------- Original Message", 1)[0].casefold()


def build_unavailability_evidence(*, eml_path: Path, pdf_path: Path) -> dict[str, Any]:
    """Parse the EML as primary evidence and bind a PDF rendition by hash.

    No email addresses, people, message ids, route headers, or body text are
    copied into the derived record.
    """
    eml_path, pdf_path = Path(eml_path), Path(pdf_path)
    if not eml_path.is_file() or not pdf_path.is_file():
        raise DevelopmentMetadataBoundsError("required EML/PDF evidence is missing")
    pdf_bytes = pdf_path.read_bytes()
    if not pdf_bytes.startswith(b"%PDF-") or b"%%EOF" not in pdf_bytes[-4096:]:
        raise DevelopmentMetadataBoundsError("PDF rendition failed structural validation")
    message = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
    sender = parseaddr(str(message.get("from", "")))[1].rsplit("@", 1)[-1].casefold()
    if sender != "exness.com" and not sender.endswith(".exness.com"):
        raise DevelopmentMetadataBoundsError("EML sender domain is not an Exness domain")
    try:
        message_date = parsedate_to_datetime(str(message["date"]))
    except (TypeError, ValueError, IndexError) as exc:
        raise DevelopmentMetadataBoundsError("EML has no valid message date") from exc
    if message_date.tzinfo is None:
        raise DevelopmentMetadataBoundsError("EML message date is timezone-ambiguous")
    reply = _plain_reply(message)
    absent = sorted(identifier for identifier, phrase in REQUIRED_NEGATIVE_STATEMENTS.items() if phrase in reply)
    if len(absent) != len(REQUIRED_NEGATIVE_STATEMENTS):
        raise DevelopmentMetadataBoundsError("EML does not contain every required historical-metadata statement")
    content: dict[str, Any] = {
        "schema_version": UNAVAILABILITY_SCHEMA_VERSION,
        "classification": OFFICIAL_UNAVAILABLE,
        "record": "official Exness statement: historical 2024 XAUUSDm metadata unavailable",
        "symbol": "XAUUSDm",
        "primary_source": {
            "format": "EML",
            "source_file_name": eml_path.name,
            "sha256": _sha256_file(eml_path),
            "sender_domain": sender,
            "message_date_utc": message_date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "parsed_as_primary": True,
        },
        "rendition": {"format": "PDF", "source_file_name": pdf_path.name, "sha256": _sha256_file(pdf_path), "parsed_as_primary": False},
        "statements": absent,
        "current_conditions_only": True,
        "historical_numeric_metadata_supplied": False,
        "sanitization": {
            "personal_addresses_redacted": True,
            "personal_names_redacted": True,
            "message_identifiers_redacted": True,
            "mail_routing_headers_redacted": True,
            "raw_subject_and_body_excluded": True,
        },
    }
    content["evidence_canonical_sha256"] = canonical_hash(content)
    verify_unavailability_evidence(content)
    return content


def verify_unavailability_evidence(content: Mapping[str, Any]) -> dict[str, Any]:
    if content.get("schema_version") != UNAVAILABILITY_SCHEMA_VERSION or content.get("classification") != OFFICIAL_UNAVAILABLE:
        raise DevelopmentMetadataBoundsError("unavailability evidence schema/classification mismatch")
    if set(content.get("statements", ())) != set(REQUIRED_NEGATIVE_STATEMENTS):
        raise DevelopmentMetadataBoundsError("unavailability evidence statement set mismatch")
    if content.get("historical_numeric_metadata_supplied") is not False or content.get("current_conditions_only") is not True:
        raise DevelopmentMetadataBoundsError("unavailability evidence improperly promotes historical metadata")
    for source in (content.get("primary_source", {}), content.get("rendition", {})):
        if len(str(source.get("sha256", ""))) != 64:
            raise DevelopmentMetadataBoundsError("unavailability evidence source hash missing")
    serialized = json.dumps(content, sort_keys=True)
    if "@" in serialized or any(key in serialized.casefold() for key in ("message-id", "received:", "reply-to")):
        raise DevelopmentMetadataBoundsError("derived evidence contains forbidden mail identity data")
    payload = {key: value for key, value in content.items() if key != "evidence_canonical_sha256"}
    if content.get("evidence_canonical_sha256") != canonical_hash(payload):
        raise DevelopmentMetadataBoundsError("unavailability evidence hash mismatch")
    return {"verified": True}


def derive_tick_value_proxy(*, contract_size_oz: float, tick_size_price: float) -> float:
    """USD/tick/lot only under explicitly assumed USD-per-ounce economics."""
    if contract_size_oz <= 0 or tick_size_price <= 0:
        raise DevelopmentMetadataBoundsError("contract size and tick size must be positive")
    return round(contract_size_oz * tick_size_price, 12)


def _scenarios() -> list[dict[str, Any]]:
    observed_max_spread_price = 9.026
    baseline = {"max_volume_lots": 20.0, "margin_rate": 0.005, "min_free_margin_fraction": 0.10, "fill_fraction": 1.0, "minimum_volume_lots": 0.01}
    scenarios = [
        ("BASELINE_CURRENT_REFERENCE_PROXY", "baseline", baseline),
        ("REDUCED_MAXIMUM_VOLUME", "adverse", {**baseline, "max_volume_lots": 0.10}),
        ("STRICTER_MARGIN_REQUIREMENT", "adverse", {**baseline, "margin_rate": 0.01}),
        ("CONSTRAINED_FREE_MARGIN", "adverse", {**baseline, "min_free_margin_fraction": 0.80}),
        ("FOK_MISSED_FILL_STRESS", "adverse", {**baseline, "filling_mode": "FOK", "missed_fill_on_rejection": True}),
        ("PARTIAL_FILL_REDUCED_LIQUIDITY", "adverse", {**baseline, "fill_fraction": 0.50}),
        ("STOP_FREEZE_RESTRICTION_GUARD", "adverse", {**baseline, "minimum_stop_freeze_distance_price": observed_max_spread_price}),
        ("MINIMUM_VOLUME_RISK_BUDGET_FAILURE", "adverse", {**baseline, "minimum_volume_lots": 0.10, "reject_if_minimum_exceeds_risk_budget": True}),
        ("STALE_METADATA_REJECTION", "adverse", {**baseline, "metadata_state": "STALE", "entry_permitted": False}),
        ("COMBINED_ADVERSE_BROKER_CONDITIONS", "adverse", {**baseline, "max_volume_lots": 0.10, "margin_rate": 0.01, "min_free_margin_fraction": 0.80, "fill_fraction": 0.50, "minimum_volume_lots": 0.10, "minimum_stop_freeze_distance_price": observed_max_spread_price}),
    ]
    return [
        {"scenario_id": identifier, "role": role, "classification": PROXY_ASSUMPTION,
         "values": values, "selection_by_profit_prohibited": True,
         "observed_spread_anchor_price": observed_max_spread_price if "STOP_FREEZE" in identifier or "COMBINED" in identifier else None}
        for identifier, role, values in scenarios
    ]


def normalize_volume_down(volume: float, step: float) -> float:
    """Normalize a development proxy volume downward; never increase risk."""
    if volume <= 0 or step <= 0:
        raise DevelopmentMetadataBoundsError("volume and step must be positive")
    normalized = (Decimal(str(volume)) / Decimal(str(step))).to_integral_value(rounding=ROUND_FLOOR) * Decimal(str(step))
    return float(normalized)


def evaluate_scenario_guard(
    scenario: Mapping[str, Any], *, requested_volume: float, risk_budget_volume: float,
    metadata_fresh: bool, free_margin_fraction: float, stop_distance_price: float,
    fok_fill_available: bool = True,
) -> str:
    """Evaluate only proxy safety constraints; it cannot create an order."""
    values = scenario.get("values", {})
    if not metadata_fresh or values.get("metadata_state") == "STALE":
        return "REJECT_METADATA_STALE"
    minimum = float(values["minimum_volume_lots"])
    maximum = float(values["max_volume_lots"])
    normalized = normalize_volume_down(requested_volume, 0.01)
    if normalized < minimum:
        return "REJECT_MINIMUM_VOLUME"
    if values.get("reject_if_minimum_exceeds_risk_budget") and minimum > risk_budget_volume:
        return "REJECT_MINIMUM_VOLUME_EXCEEDS_RISK_BUDGET"
    if normalized > maximum:
        return "REJECT_MAXIMUM_VOLUME"
    if free_margin_fraction < float(values["min_free_margin_fraction"]):
        return "REJECT_FREE_MARGIN"
    required_distance = values.get("minimum_stop_freeze_distance_price")
    if required_distance is not None and stop_distance_price < float(required_distance):
        return "REJECT_STOP_FREEZE_GUARD"
    if values.get("filling_mode") == "FOK" and (values.get("missed_fill_on_rejection") or not fok_fill_available):
        return "REJECT_FOK_MISSED_FILL"
    if float(values["fill_fraction"]) < 1.0:
        return "PARTIAL_FILL_STRESS"
    return "APPROVED_PROXY_GUARD"


def policy_fingerprint(content: Mapping[str, Any]) -> str:
    return canonical_hash({key: value for key, value in content.items() if key != "policy_fingerprint"})


def build_development_metadata_bounds(
    *, unavailability_evidence: Mapping[str, Any], unavailability_package_id: str,
    unavailability_content_sha256: str, recovery: Mapping[str, Any], recovery_package_id: str,
    recovery_content_sha256: str, recovery_readiness: Mapping[str, Any], recovery_readiness_package_id: str,
    recovery_readiness_content_sha256: str, cost_policy_report: Mapping[str, Any], bindings: Mapping[str, Any], decision_utc: str,
) -> dict[str, Any]:
    verify_unavailability_evidence(unavailability_evidence)
    metadata_recovery.verify_metadata_recovery(recovery)
    metadata_recovery.verify_metadata_recovery_readiness(recovery_readiness)
    if canonical_hash(dict(unavailability_evidence)) != unavailability_content_sha256:
        raise DevelopmentMetadataBoundsError("official unavailability evidence hash mismatch")
    if canonical_hash(dict(recovery)) != recovery_content_sha256:
        raise DevelopmentMetadataBoundsError("Phase 8K recovery hash mismatch")
    if canonical_hash(dict(recovery_readiness)) != recovery_readiness_content_sha256:
        raise DevelopmentMetadataBoundsError("Phase 8K recovery readiness hash mismatch")
    scenarios = _scenarios()
    if tuple(item["scenario_id"] for item in scenarios) != SCENARIO_ORDER:
        raise DevelopmentMetadataBoundsError("mandatory metadata scenario order drifted")
    content: dict[str, Any] = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "record": "owner-authorized conservative development metadata bounds",
        "policy_state": "PREREGISTERED_DEVELOPMENT_PREPARATION_ONLY",
        "decision_utc": decision_utc,
        "symbol": "XAUUSDm",
        "baseline_proxy": {
            "digits": {"value": 3, "classification": EMPIRICAL},
            "point_tick_size": {"value": 0.001, "classification": PROXY_ASSUMPTION, "not_historical_fact": True},
            "contract_size_troy_ounces_per_lot": {"value": 100.0, "classification": PROXY_ASSUMPTION, "source": CURRENT_REFERENCE},
            "profit_currency": {"value": "USD", "classification": PROXY_ASSUMPTION},
            "minimum_volume_lots": {"value": 0.01, "classification": PROXY_ASSUMPTION, "source": CURRENT_REFERENCE},
            "volume_step_lots": {"value": 0.01, "classification": PROXY_ASSUMPTION, "source": CURRENT_REFERENCE},
            "maximum_volume_lots": {"value": 20.0, "classification": PROXY_ASSUMPTION, "source": "MOST_RESTRICTIVE_CURRENT_REFERENCE_DAY_NIGHT_LIMIT"},
            "execution_mode": {"value": "MARKET", "classification": PROXY_ASSUMPTION, "source": CURRENT_REFERENCE},
            "filling_capabilities": {"value": ["FOK", "IOC"], "classification": PROXY_ASSUMPTION, "source": CURRENT_REFERENCE},
            "commission": {"value": "ZERO_STANDARD_ACCOUNT_REFERENCE", "classification": CURRENT_REFERENCE},
            "spread": {"value": "OBSERVED_2024_BID_ASK_ONLY", "classification": EMPIRICAL},
            "swap_slippage": {"value": "PHASE8H_PREREGISTERED_SCENARIOS", "classification": PROXY_ASSUMPTION},
            "stops_freeze": {"value": "UNRESOLVED_GUARDED_BY_MANDATORY_STRESS", "classification": "UNAVAILABLE"},
            "margin_leverage": {"value": "UNRESOLVED_GUARDED_BY_MANDATORY_SCENARIOS", "classification": "UNAVAILABLE"},
        },
        "derived_tick_value_proxy": {"formula": "assumed_contract_size_troy_ounces_per_lot * assumed_tick_size_price", "contract_size_troy_ounces_per_lot": 100.0, "tick_size_price": 0.001, "usd_per_tick_per_lot": derive_tick_value_proxy(contract_size_oz=100.0, tick_size_price=0.001), "classification": "DERIVED_FROM_ASSUMED_CONTRACT_SIZE", "historical_fact": False},
        "mandatory_scenarios": scenarios,
        "restrictions": {"run_all_mandatory_scenarios": True, "cheapest_scenario_selection": "PROHIBITED", "scenario_failure_visibility": "REQUIRED", "results_label": "DEVELOPMENT_PROXY_NOT_HISTORICALLY_VALIDATED", "no_profitability_selection": True},
        "bindings": {"phase8k_recovery": {"package_id": recovery_package_id, "content_canonical_sha256": recovery_content_sha256}, "phase8k_readiness": {"package_id": recovery_readiness_package_id, "content_canonical_sha256": recovery_readiness_content_sha256}, "official_unavailability_evidence": {"package_id": unavailability_package_id, "content_canonical_sha256": unavailability_content_sha256}, "development_cost_policy": {"package_id": str(cost_policy_report["package_id"]), "policy_fingerprint": str(cost_policy_report["policy_fingerprint"])}, **dict(bindings)},
        "development_metadata_gap_acceptable": True,
        "development_evaluation_sufficient": True,
        "strategy_evaluation_authorized": False,
        "accepted_for_final_validation": False,
        "holdout_access_authorized": False,
        "phase9_authorized": False,
    }
    content["policy_fingerprint"] = policy_fingerprint(content)
    verify_development_metadata_bounds(content)
    return content


def verify_development_metadata_bounds(content: Mapping[str, Any]) -> dict[str, Any]:
    if content.get("schema_version") != POLICY_SCHEMA_VERSION or content.get("policy_state") != "PREREGISTERED_DEVELOPMENT_PREPARATION_ONLY":
        raise DevelopmentMetadataBoundsError("metadata-bounds policy schema/state mismatch")
    if content.get("symbol") != "XAUUSDm":
        raise DevelopmentMetadataBoundsError("metadata-bounds policy symbol mismatch")
    if content.get("policy_fingerprint") != policy_fingerprint(content):
        raise DevelopmentMetadataBoundsError("metadata-bounds policy fingerprint mismatch")
    if tuple(item.get("scenario_id") for item in content.get("mandatory_scenarios", ())) != SCENARIO_ORDER:
        raise DevelopmentMetadataBoundsError("mandatory metadata scenarios are missing or reordered")
    if any(item.get("classification") != PROXY_ASSUMPTION or item.get("selection_by_profit_prohibited") is not True for item in content["mandatory_scenarios"]):
        raise DevelopmentMetadataBoundsError("metadata scenarios must remain preregistered assumptions")
    if content["restrictions"].get("cheapest_scenario_selection") != "PROHIBITED" or content["restrictions"].get("run_all_mandatory_scenarios") is not True:
        raise DevelopmentMetadataBoundsError("metadata scenario selection guard drifted")
    proxy = content["derived_tick_value_proxy"]
    if proxy.get("usd_per_tick_per_lot") != derive_tick_value_proxy(contract_size_oz=float(proxy["contract_size_troy_ounces_per_lot"]), tick_size_price=float(proxy["tick_size_price"])):
        raise DevelopmentMetadataBoundsError("derived tick-value proxy formula drifted")
    for gate in ("strategy_evaluation_authorized", "accepted_for_final_validation", "holdout_access_authorized", "phase9_authorized"):
        if content.get(gate) is not False:
            raise DevelopmentMetadataBoundsError(f"metadata-bounds gate {gate} must remain false")
    if content.get("development_metadata_gap_acceptable") is not True or content.get("development_evaluation_sufficient") is not True:
        raise DevelopmentMetadataBoundsError("owner-authorized development preparation gates are missing")
    return {"verified": True, "policy_fingerprint": str(content["policy_fingerprint"])}


def build_readiness(policy_content: Mapping[str, Any], *, policy_package_id: str, policy_content_sha256: str) -> dict[str, Any]:
    verify_development_metadata_bounds(policy_content)
    content = {"schema_version": READINESS_SCHEMA_VERSION, "classification": DEVELOPMENT_ONLY_CLASSIFICATION, "record": "Phase 8L development metadata bounds readiness", "policy": {"package_id": policy_package_id, "content_canonical_sha256": policy_content_sha256, "policy_fingerprint": policy_content["policy_fingerprint"]}, "development_metadata_gap_acceptable": True, "development_evaluation_sufficient": True, "strategy_evaluation_authorized": False, "accepted_for_final_validation": False, "holdout_access_authorized": False, "phase9_authorized": False, "next_checkpoint": "separate explicit authorization may prepare a development-only all-scenario evaluation; no historical-validation claim is permitted"}
    content["readiness_canonical_sha256"] = canonical_hash(content)
    verify_readiness(content)
    return content


def verify_readiness(content: Mapping[str, Any]) -> dict[str, Any]:
    if content.get("schema_version") != READINESS_SCHEMA_VERSION:
        raise DevelopmentMetadataBoundsError("metadata-bounds readiness schema mismatch")
    for gate in ("strategy_evaluation_authorized", "accepted_for_final_validation", "holdout_access_authorized", "phase9_authorized"):
        if content.get(gate) is not False:
            raise DevelopmentMetadataBoundsError(f"metadata-bounds readiness gate {gate} must remain false")
    payload = {key: value for key, value in content.items() if key != "readiness_canonical_sha256"}
    if content.get("readiness_canonical_sha256") != canonical_hash(payload):
        raise DevelopmentMetadataBoundsError("metadata-bounds readiness hash mismatch")
    return {"verified": True}


def publish_from_evidence_root(*, data_root: Path, eml_path: Path, pdf_path: Path, decision_utc: str) -> dict[str, str]:
    root = Path(data_root) / "evidence"
    evidence = build_unavailability_evidence(eml_path=eml_path, pdf_path=pdf_path)
    evidence_package, evidence_id = build_evidence_package(kind="broker_metadata_unavailability", content=evidence, source_path=Path(eml_path))
    existing = sorted(root.glob("evidence-broker_metadata_unavailability-v1-*"))
    if any(path.name != evidence_id for path in existing):
        raise DevelopmentMetadataBoundsError("conflicting official metadata-unavailability evidence already published")
    _, evidence_id = publish_evidence_package(evidence_package, evidence_root=root)
    recovery_id, recovery_package = _load_exact_kind(root, "broker_metadata_recovery")
    readiness_id, readiness_package = _load_exact_kind(root, "metadata_recovery_readiness")
    cost_report = cost_policy_activation_report(root)
    bindings = cost_policy.build_bindings(data_root=Path(data_root), broker_support_content_sha256=str(cost_report["broker_support_content_sha256"]))
    policy_content = build_development_metadata_bounds(unavailability_evidence=evidence, unavailability_package_id=evidence_id, unavailability_content_sha256=_content_hash(evidence_package), recovery=dict(recovery_package["content"]), recovery_package_id=recovery_id, recovery_content_sha256=_content_hash(recovery_package), recovery_readiness=dict(readiness_package["content"]), recovery_readiness_package_id=readiness_id, recovery_readiness_content_sha256=_content_hash(readiness_package), cost_policy_report=cost_report, bindings=bindings, decision_utc=decision_utc)
    package, policy_id = build_evidence_package(kind="development_metadata_bounds", content=policy_content, source_path=None)
    existing = sorted(root.glob("evidence-development_metadata_bounds-v1-*"))
    if any(path.name != policy_id for path in existing):
        raise DevelopmentMetadataBoundsError("conflicting development metadata-bounds policy already published")
    _, policy_id = publish_evidence_package(package, evidence_root=root)
    readiness = build_readiness(policy_content, policy_package_id=policy_id, policy_content_sha256=_content_hash(package))
    readiness_package, readiness_id = build_evidence_package(kind="development_metadata_bounds_readiness", content=readiness, source_path=None)
    existing = sorted(root.glob("evidence-development_metadata_bounds_readiness-v1-*"))
    if any(path.name != readiness_id for path in existing):
        raise DevelopmentMetadataBoundsError("conflicting development metadata-bounds readiness already published")
    publish_evidence_package(readiness_package, evidence_root=root)
    return {"unavailability_package_id": evidence_id, "policy_package_id": policy_id, "readiness_package_id": readiness_id}


def cost_policy_activation_report(evidence_root: Path) -> dict[str, Any]:
    """Load the active frozen cost policy without importing a broker adapter."""
    package_id, package = _load_exact_kind(Path(evidence_root), "development_cost_policy")
    report = cost_policy.verify_cost_policy(dict(package["content"]))
    bindings = package["content"].get("bindings", {})
    report["package_id"] = package_id
    report["broker_support_content_sha256"] = str(bindings.get("broker_support_revision", {}).get("content_canonical_sha256", ""))
    if len(report["broker_support_content_sha256"]) != 64:
        raise DevelopmentMetadataBoundsError("cost policy has no broker-support hash")
    return report
