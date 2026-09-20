"""Phase 8I — swap-scenario activation record and dataset-acceptance review.

Owner decision checkpoint (offline, fail-closed, no strategy evaluation):

- The frozen Phase 8H policy ``phase8h.development-cost-policy.v1`` stays
  byte-immutable.  Activation is represented by a *separate* content-derived
  evidence package (kind ``cost_policy_activation``) that cryptographically
  binds the exact published policy fingerprint and re-verifies the frozen
  scenario ladder at build and verify time.  ``ACTIVE`` was never a
  representable policy state, and this module does not add one.
- The dataset-acceptance review (kind ``dataset_acceptance_review``) records
  the explicit, per-category classification of every remaining owner-kit
  evidence category after re-checking all package identities on disk.

Classification vocabulary (single source of truth for this checkpoint;
values map onto the Phase 8E evidence statuses — no parallel terminology):

- ``ACCEPTED_EMPIRICAL``          hash-verified observed 2024 market evidence.
- ``ACCEPTED_DEVELOPMENT_ONLY``   accepted for development evaluation under
                                  the frozen Phase 8H restrictions only.
- ``ASSUMPTION_ONLY``             preregistered assumption, never empirical.
- ``INSUFFICIENT``                present evidence does not satisfy the
                                  committed acceptance requirements.
- ``BLOCKED``                     no acceptable evidence path exists yet.

Historical 2024 swap values remain ``HISTORICAL_VALUE_UNAVAILABLE``; every
swap scenario stays ``ASSUMPTION_ONLY`` with the
``HISTORICAL_SWAP_UNCERTAIN`` label carried forward.  Nothing here
upgrades development-strength evidence to final-validation strength and no
gate may become true through this module.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from bot.acquisition.evidence_contracts import canonical_hash
from bot.validation.cost_policy import (
    POLICY_SCHEMA_VERSION,
    REQUIRED_ADVERSE_BOUNDARY,
    SWAP_SCENARIO_ORDER,
    TRIPLE_SWAP_WEEKDAY,
    verify_cost_policy,
)

ACTIVATION_SCHEMA_VERSION = "phase8i.cost-policy-activation.v1"
ACCEPTANCE_SCHEMA_VERSION = "phase8i.dataset-acceptance-review.v1"

# Pinned Phase 8 deployment identities used by the acceptance review.
DERIVED_PACKAGE_DIR = "derived-candles-2024-v1-20260911T195553Z"
ATTESTATION_DIR = "derived-candles-attestation-v1-6715e5c64d888215"
DXY_PACKAGE_DIR = "dxy-development-2024-v1-20260912T091410.712364Z"

ACTIVATION_STATE = "ACTIVE_FOR_DEVELOPMENT_VALIDATION"
DEVELOPMENT_ONLY_CLASSIFICATION = (
    "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE"
)

# Minimum evidence identities evaluation may proceed against.  The policy
# package itself contributes two of these via its own frozen bindings (the
# pinned Phase 8H ids); every entry must exist and hash-verify on disk
# before an activation record can be built.  Tests may override the set.
REQUIRED_EVIDENCE_PACKAGES: dict[str, str] = {
    "broker_support_revision": "evidence-broker_support-v1-3b68b4203a9109b9",
    "observed_spread_evidence": "observed_spread-v1-e25bdb9bf028a5be",
    "development_cost_policy": "evidence-development_cost_policy-v1-6b1a986b1f8d7b81",
}

# The frozen swap ladder, restated as the activation contract.  Build and
# verify both fail closed if the published policy ladder has drifted.
FROZEN_SWAP_MULTIPLIERS: dict[str, float] = {
    "SWAP_NO_OVERNIGHT_EXPOSURE_DIAGNOSTIC": 0.0,
    "SWAP_EMAIL_REFERENCE": 1.0,
    "SWAP_EMAIL_2X_ADVERSE": 2.0,
    "SWAP_EMAIL_3X_ADVERSE": 3.0,
}

# Per-category dataset-acceptance review (Phase 8I).  ``status`` uses the
# Phase 8E acceptance vocabulary; ``strength`` states the honest evidence
# strength achieved.  Final-validation strength is never claimed.
ACCEPTANCE_REVIEW_CATEGORIES: tuple[dict[str, Any], ...] = (
    {
        "category": "XAUUSDM_TICKS_2024",
        "status": "ACCEPTED_EMPIRICAL",
        "strength": "EMPIRICAL",
        "identity": "exness-xauusdm-2024-development (39,715,935 verified rows)",
        "basis": "hash-verified raw tick year package; unchanged since Phase 8A",
    },
    {
        "category": "XAUUSDM_CAUSAL_CANDLES",
        "status": "ACCEPTED_EMPIRICAL",
        "strength": "EMPIRICAL",
        "identity": "derived-candles-2024-v1-20260911T195553Z (attested provenance)",
        "basis": "manifest + attestation + discovery record verified at hash level",
    },
    {
        "category": "OBSERVED_SPREAD",
        "status": "ACCEPTED_EMPIRICAL",
        "strength": "EMPIRICAL",
        "identity": "observed_spread-v1-e25bdb9bf028a5be",
        "basis": "observed bid/ask evidence re-verified; primary 2024 spread basis",
    },
    {
        "category": "OFFICIAL_USD_NEWS",
        "status": "ACCEPTED_DEVELOPMENT_ONLY",
        "strength": "DEVELOPMENT_ONLY",
        "identity": "evidence-official_news-v1-57b086042344524c (80 events, 7 categories)",
        "basis": (
            "official government sources (Fed/BEA/Census/BLS); full 2024 coverage "
            "accepted for development news-window filtering; not final-validation evidence"
        ),
    },
    {
        "category": "COMMISSION",
        "status": "ACCEPTED_DEVELOPMENT_ONLY",
        "strength": "DEVELOPMENT_ONLY",
        "identity": "evidence-broker_support-v1-3b68b4203a9109b9 (Standard, mode NONE)",
        "basis": (
            "broker-support-asserted zero Standard commission; no dated 2024 "
            "change archive; effective-interval not established"
        ),
    },
    {
        "category": "SWAP_ROLLOVER",
        "status": "ACCEPTED_DEVELOPMENT_ONLY",
        "strength": "ASSUMPTION_ONLY",
        "identity": "cost policy activation over evidence-broker_support-v1-3b68b4203a9109b9",
        "basis": (
            "historical 2024 swap values and change dates remain "
            "HISTORICAL_VALUE_UNAVAILABLE; the points-vs-USD conflict is preserved; "
            "accounting proceeds only under the frozen assumption-only scenario "
            "ladder with the HISTORICAL_SWAP_UNCERTAIN label"
        ),
    },
    {
        "category": "SLIPPAGE_FILLS",
        "status": "ACCEPTED_DEVELOPMENT_ONLY",
        "strength": "ASSUMPTION_ONLY",
        "identity": "cost policy slippage ladder (0/1/3 points)",
        "basis": (
            "no calibrated historical fills exist; preregistered assumption-only "
            "scenarios only; silent zero-for-acceptance remains prohibited"
        ),
    },
    {
        "category": "BROKER_METADATA",
        "status": "INSUFFICIENT",
        "strength": "CURRENT_ONLY_NOT_HISTORICAL",
        "identity": "sanitized MT5 specification screenshots (2026-09-13)",
        "basis": (
            "current-platform observations cannot establish 2024-effective "
            "values; margin-display conflict remains unresolved"
        ),
    },
    {
        "category": "DXY_DEVELOPMENT_INPUT",
        "status": "ACCEPTED_DEVELOPMENT_ONLY",
        "strength": "EMPIRICAL_CONSTITUENTS",
        "identity": "dxy-development-2024-v1-20260912T091410.712364Z (6,216 causal values)",
        "basis": "six verified H1 constituent datasets; unchanged formula and alignment",
    },
    {
        "category": "HOLDOUT",
        "status": "BLOCKED",
        "strength": "NONE",
        "identity": "unavailable and untouched by policy",
        "basis": "no holdout access is authorized at any point in this checkpoint",
    },
)


class CostPolicyActivationError(RuntimeError):
    """Raised when activation or acceptance review would be unsound."""


def _policy_from_evidence_root(evidence_root: Path) -> tuple[dict[str, Any], Path]:
    """Load the single published Phase 8H policy package (fail closed)."""

    matches = sorted(evidence_root.glob("evidence-development_cost_policy-v1-*"))
    if not matches:
        raise CostPolicyActivationError(
            "no published development-cost-policy package exists; "
            "activation requires the preregistered Phase 8H policy"
        )
    if len(matches) > 1:
        raise CostPolicyActivationError(
            "ambiguous cost-policy state: multiple published policy revisions; "
            "activation must bind exactly one"
        )
    package_dir = matches[0]
    manifest = json.loads(
        (package_dir / "manifest.json").read_text(encoding="utf-8")
    )
    content = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))[
        "content"
    ]
    content_hash = str(manifest.get("content_canonical_sha256", ""))
    if not content_hash or canonical_hash(content) != content_hash:
        raise CostPolicyActivationError(
            "cost-policy package content hash mismatch (tampering detected)"
        )
    return content, package_dir


def verify_published_policy(evidence_root: Path) -> dict[str, Any]:
    """Re-verify the published policy: envelope + full Phase 8H verification."""

    content, package_dir = _policy_from_evidence_root(evidence_root)
    report = verify_cost_policy(content)
    report["package_id"] = str(
        json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))[
            "package_id"
        ]
    )
    return report


def _enforce_frozen_ladder(policy_content: Mapping[str, Any]) -> None:
    scenarios = policy_content["swap_scenarios"]
    ids = tuple(s["scenario_id"] for s in scenarios)
    if ids != SWAP_SCENARIO_ORDER:
        raise CostPolicyActivationError(
            "published policy swap-scenario ladder drifted from the frozen order"
        )
    multipliers = {s["scenario_id"]: s["swap_multiplier_vs_email_reference"] for s in scenarios}
    if multipliers != FROZEN_SWAP_MULTIPLIERS:
        raise CostPolicyActivationError(
            "published policy swap-scenario multipliers drifted from the frozen ladder"
        )
    required = next(
        (s for s in scenarios if s["scenario_id"] == REQUIRED_ADVERSE_BOUNDARY), None
    )
    if required is None:
        raise CostPolicyActivationError("required adverse boundary scenario is missing")
    if float(required["swap_multiplier_vs_email_reference"]) != 3.0:
        raise CostPolicyActivationError("required adverse boundary must be the 3x scenario")
    for scenario in scenarios:
        if scenario["triple_swap_weekday"] != TRIPLE_SWAP_WEEKDAY:
            raise CostPolicyActivationError("triple-swap Wednesday must be preserved")
        if scenario["long_usd_per_lot_per_day"] > 0 or scenario["short_usd_per_lot_per_day"] > 0:
            raise CostPolicyActivationError("no favorable positive swap credit is permitted")
    restrictions = policy_content["acceptance_restrictions"]
    if restrictions.get("cheapest_scenario_pass_rule") != "PROHIBITED":
        raise CostPolicyActivationError("cheapest-scenario selection must stay prohibited")
    for gate in (
        "strategy_evaluation_authorized",
        "final_validation_authorized",
        "holdout_access_authorized",
    ):
        if policy_content["acceptance_restrictions"].get(gate) is not False:
            raise CostPolicyActivationError(f"policy gate {gate} must remain false")


def _required_from_policy(
    policy_content: Mapping[str, Any], policy_package_id: str
) -> dict[str, str]:
    """Derive the required-package set from the policy's own frozen bindings.

    The 8H policy binds the broker-support revision and observed-spread
    package ids; the policy package itself is always required.  The derived
    set is authoritative because it is what the policy cryptographically
    commits to.
    """

    bindings = policy_content.get("bindings", {})
    derived: dict[str, str] = {
        "development_cost_policy": policy_package_id,
        "broker_support_revision": str(
            bindings.get("broker_support_revision", {}).get("package_id", "")
        ),
        "observed_spread_evidence": str(
            bindings.get("observed_spread_evidence", {}).get("package_id", "")
        ),
    }
    for binding, package_id in list(derived.items()):
        if not package_id:
            raise CostPolicyActivationError(
                f"policy binding {binding} is missing a package id; cannot activate"
            )
    return derived


def _check_pinned_identities(derived: Mapping[str, str]) -> None:
    """Fail closed if the derived bindings contradict the pinned Phase 8H ids.

    Production guard only (the default code path): a policy revision that
    binds different evidence packages must not be activated silently — the
    pinned map must be consciously updated first.  The policy's own package
    id is compared too: on the default path the published revision must be
    exactly the preregistered Phase 8H package.
    """

    if dict(derived) != dict(REQUIRED_EVIDENCE_PACKAGES):
        raise CostPolicyActivationError(
            "policy bindings contradict the pinned Phase 8H evidence identities"
        )


def _verify_required_packages_on_disk(
    evidence_root: Path, required_packages: Mapping[str, str]
) -> dict[str, str]:
    """Hash-verify every required evidence package identity; return binding->id."""

    identities: dict[str, str] = {}
    for binding, package_id in sorted(required_packages.items()):
        package_dir = evidence_root / package_id
        if not package_dir.is_dir():
            raise CostPolicyActivationError(
                f"required evidence package missing on disk: {package_id}"
            )
        manifest = json.loads(
            (package_dir / "manifest.json").read_text(encoding="utf-8")
        )
        recorded = str(manifest.get("content_canonical_sha256", ""))
        content = json.loads(
            (package_dir / "package.json").read_text(encoding="utf-8")
        )["content"]
        if not recorded or canonical_hash(content) != recorded:
            raise CostPolicyActivationError(
                f"evidence package hash mismatch: {package_id} (tampering detected)"
            )
        identities[binding] = package_id
    return identities


def build_activation_record(
    *,
    data_root: Path,
    decision_utc: str,
    decision_scope: str,
    required_packages: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the activation record binding the exact published Phase 8H policy.

    Fails closed unless: the policy package verifies completely, the frozen
    scenario ladder is intact, and every required evidence identity exists
    and hash-verifies on disk.  ``required_packages`` defaults to the pinned
    Phase 8H identities; tests may bind synthetic revisions instead.
    """

    data_root = Path(data_root)
    evidence_root = data_root / "evidence"

    policy_report = verify_published_policy(evidence_root)
    policy_content, _policy_dir = _policy_from_evidence_root(evidence_root)
    if str(policy_content.get("schema_version")) != POLICY_SCHEMA_VERSION:
        raise CostPolicyActivationError("unexpected policy schema version")
    _enforce_frozen_ladder(policy_content)
    derived = _required_from_policy(policy_content, str(policy_report["package_id"]))
    if required_packages is None:
        _check_pinned_identities(derived)
        required = dict(derived)
    else:
        required = {**derived, **dict(required_packages)}
    identities = _verify_required_packages_on_disk(evidence_root, required)

    swap_scenarios = [
        {
            "scenario_id": s["scenario_id"],
            "classification": "ASSUMPTION_ONLY",
            "multiplier_vs_email_reference": s["swap_multiplier_vs_email_reference"],
            "long_usd_per_lot_per_day": s["long_usd_per_lot_per_day"],
            "short_usd_per_lot_per_day": s["short_usd_per_lot_per_day"],
            "triple_swap_weekday": s["triple_swap_weekday"],
            "no_favorable_positive_swap_credit": True,
            "historical_swap_uncertain_label": "HISTORICAL_SWAP_UNCERTAIN",
        }
        for s in policy_content["swap_scenarios"]
    ]

    content: dict[str, Any] = {
        "schema_version": ACTIVATION_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "record": "swap-scenario activation for development validation only",
        "owner_decision": {
            "decision": "ACTIVATE_ASSUMPTION_ONLY_SWAP_STRESS_POLICY",
            "decision_utc": decision_utc,
            "decision_scope": decision_scope,
            "historical_swap_reinterpreted": False,
        },
        "activated_policy": {
            "schema_version": str(policy_content["schema_version"]),
            "policy_fingerprint": str(policy_content["policy_fingerprint"]),
            "package_id": str(policy_report["package_id"]),
            "policy_state_remains": str(policy_content["policy_state"]),
            "policy_content_unchanged": True,
        },
        "activation_state": ACTIVATION_STATE,
        "scope_and_restrictions": {
            "development_validation_only": True,
            "disclose_all_scenarios": True,
            "cheapest_scenario_pass_rule": "PROHIBITED",
            "required_adverse_boundary": REQUIRED_ADVERSE_BOUNDARY,
            "automatic_parameter_selection": "PROHIBITED",
            "scenario_results_never_tune_parameters": True,
            "uncertainty_label": "HISTORICAL_SWAP_UNCERTAIN",
            "historical_2024_swap_values": "HISTORICAL_VALUE_UNAVAILABLE",
            "unit_conflict_preserved": True,
            "conversion_prohibited": True,
            "final_validation_authorized": False,
            "holdout_access_authorized": False,
            "strategy_evaluation_authorized": False,
            "note": (
                "activation authorizes future scenario-based development "
                "accounting only under the frozen Phase 8H governance rules; "
                "it does not itself start any evaluation"
            ),
        },
        "swap_scenarios_activated": swap_scenarios,
        "slippage_scenarios_activated": [
            {
                "scenario_id": s["scenario_id"],
                "points": s["points"],
                "classification": "ASSUMPTION_ONLY",
            }
            for s in policy_content["slippage_scenarios"]
        ],
        "bound_evidence_packages": identities,
    }
    # Matrix-facing alias of activation_state (the Phase 8E collector reads
    # content["status"]); it is added before the record hash so verification
    # recomputes over identical content.
    content["status"] = ACTIVATION_STATE
    content["activation_record_sha256"] = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    ).hexdigest()
    return content


def verify_activation_record(content: Mapping[str, Any]) -> dict[str, Any]:
    """Full readback verification of a published activation record."""

    if str(content.get("schema_version")) != ACTIVATION_SCHEMA_VERSION:
        raise CostPolicyActivationError("activation schema version mismatch")
    if content.get("activation_state") != ACTIVATION_STATE:
        raise CostPolicyActivationError("activation state mismatch")
    if content.get("status", content.get("activation_state")) != content.get("activation_state"):
        raise CostPolicyActivationError("status alias must agree with activation_state")
    decision = content.get("owner_decision", {})
    if decision.get("decision") != "ACTIVATE_ASSUMPTION_ONLY_SWAP_STRESS_POLICY":
        raise CostPolicyActivationError("activation decision mismatch")
    if decision.get("historical_swap_reinterpreted") is not False:
        raise CostPolicyActivationError("historical swap evidence must not be reinterpreted")
    policy = content.get("activated_policy", {})
    if policy.get("policy_state_remains") != "PREREGISTERED_INACTIVE":
        raise CostPolicyActivationError("the underlying policy must remain preregistered-inactive")
    if policy.get("policy_content_unchanged") is not True:
        raise CostPolicyActivationError("activation must not modify the policy content")
    if not policy.get("policy_fingerprint"):
        raise CostPolicyActivationError("activation must bind a policy fingerprint")
    restrictions = content.get("scope_and_restrictions", {})
    if restrictions.get("cheapest_scenario_pass_rule") != "PROHIBITED":
        raise CostPolicyActivationError("cheapest-scenario selection must stay prohibited")
    if restrictions.get("required_adverse_boundary") != REQUIRED_ADVERSE_BOUNDARY:
        raise CostPolicyActivationError("required adverse boundary drifted")
    if restrictions.get("automatic_parameter_selection") != "PROHIBITED":
        raise CostPolicyActivationError("automatic parameter selection must stay prohibited")
    for gate in ("final_validation_authorized", "holdout_access_authorized", "strategy_evaluation_authorized"):
        if restrictions.get(gate) is not False:
            raise CostPolicyActivationError(f"activation gate {gate} must remain false")
    scenarios = content.get("swap_scenarios_activated", [])
    if tuple(s["scenario_id"] for s in scenarios) != SWAP_SCENARIO_ORDER:
        raise CostPolicyActivationError("activated swap-scenario order drifted")
    multipliers = {
        s["scenario_id"]: float(s["multiplier_vs_email_reference"]) for s in scenarios
    }
    if multipliers != FROZEN_SWAP_MULTIPLIERS:
        raise CostPolicyActivationError("activated swap-scenario multipliers drifted")
    for scenario in scenarios:
        if scenario["classification"] != "ASSUMPTION_ONLY":
            raise CostPolicyActivationError("swap scenarios must remain assumption-only")
        if scenario["historical_swap_uncertain_label"] != "HISTORICAL_SWAP_UNCERTAIN":
            raise CostPolicyActivationError("uncertainty label must be carried forward")
        if scenario["no_favorable_positive_swap_credit"] is not True:
            raise CostPolicyActivationError("no positive swap credit is permitted")
    if scenarios[-1]["scenario_id"] != REQUIRED_ADVERSE_BOUNDARY:
        raise CostPolicyActivationError("required adverse boundary must be last in the ladder")
    slip = content.get("slippage_scenarios_activated", [])
    if [s["points"] for s in slip] != [0.0, 1.0, 3.0]:
        raise CostPolicyActivationError("activated slippage ladder drifted")
    for scenario in slip:
        if scenario["classification"] != "ASSUMPTION_ONLY":
            raise CostPolicyActivationError("slippage scenarios must remain assumption-only")
    recorded = content.get("activation_record_sha256")
    payload = {k: v for k, v in content.items() if k != "activation_record_sha256"}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    if recorded != digest:
        raise CostPolicyActivationError("activation record hash mismatch (tampering detected)")
    return {
        "verified": True,
        "activation_state": ACTIVATION_STATE,
        "policy_fingerprint": str(policy.get("policy_fingerprint")),
        "activation_record_sha256": str(recorded),
    }


def _verify_market_data_chain(data_root: Path) -> dict[str, Any]:
    """Cross-verify the derived/attestation/tick identity chain (read-only).

    Fails closed unless: the derived manifest exists, the attestation exists,
    the attestation's manifest hash matches the actual derived manifest
    bytes, the attestation's source canonical hash matches the derived
    manifest's source canonical hash, and exactly one tick year package on
    disk carries that canonical hash.  Returns the verified identities.
    """

    data_root = Path(data_root)
    derived_manifest_path = data_root / "derived" / DERIVED_PACKAGE_DIR / "manifest.json"
    attestation_path = data_root / "derived" / "attestations" / ATTESTATION_DIR / "attestation.json"
    for path in (derived_manifest_path, attestation_path):
        if not path.is_file():
            raise CostPolicyActivationError(f"required artifact missing: {path.name}")
    manifest = json.loads(derived_manifest_path.read_text(encoding="utf-8"))
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    package = attestation.get("package", {})

    manifest_digest = hashlib.sha256(derived_manifest_path.read_bytes()).hexdigest()
    if str(package.get("manifest_sha256", "")) != manifest_digest:
        raise CostPolicyActivationError(
            "derived manifest bytes no longer match the attested manifest hash"
        )
    source_canonical = str(manifest.get("source_canonical_sha256", ""))
    if not source_canonical or str(package.get("source_canonical_sha256", "")) != source_canonical:
        raise CostPolicyActivationError(
            "attested source canonical hash disagrees with the derived manifest"
        )
    if attestation.get("holdout_accessed") is not False or attestation.get("mt5_or_trading_accessed") is not False:
        raise CostPolicyActivationError("attestation safety statements must remain false-flagged")

    year_packages_root = data_root / "exness-tick-history" / "processed" / "year-packages"
    tick_manifest = None
    if year_packages_root.is_dir():
        for candidate in sorted(year_packages_root.glob("*/manifest.json")):
            data = json.loads(candidate.read_text(encoding="utf-8"))
            stats = data.get("statistics") or {}
            if str(stats.get("canonical_normalized_sha256", "")) == source_canonical:
                if tick_manifest is not None:
                    raise CostPolicyActivationError(
                        "ambiguous tick year package: two manifests share the canonical hash"
                    )
                tick_manifest = data
    if tick_manifest is None:
        raise CostPolicyActivationError(
            "no tick year package matches the attested source canonical hash"
        )
    row_count = int(manifest.get("source_row_count", 0))
    if row_count <= 0 or int(tick_manifest.get("statistics", {}).get("row_count", 0)) != row_count:
        raise CostPolicyActivationError(
            "tick year row count disagrees with the derived source row count"
        )

    dxy_manifest_path = data_root / "dxy" / DXY_PACKAGE_DIR / "manifest.json"
    if not dxy_manifest_path.is_file():
        raise CostPolicyActivationError("DXY development package manifest is missing")
    dxy = json.loads(dxy_manifest_path.read_text(encoding="utf-8"))
    causal = dxy.get("causal_dxy") or {}
    if not causal.get("canonical_content_sha256") or int(causal.get("record_count", 0)) <= 0:
        raise CostPolicyActivationError("DXY package identity fields are incomplete")

    return {
        "derived_package_id": str(package.get("package_id", DERIVED_PACKAGE_DIR)),
        "derived_manifest_sha256": manifest_digest,
        "attestation_id": str(attestation.get("attestation_id", "")),
        "source_year_package_id": str(tick_manifest.get("package_id", "")),
        "source_year_canonical_sha256": source_canonical,
        "source_row_count": row_count,
        "dxy_package_id": str(dxy.get("package_id", "")),
        "dxy_canonical_sha256": str(causal["canonical_content_sha256"]),
        "dxy_record_count": int(causal["record_count"]),
    }


def _verify_official_news_revision(evidence_root: Path) -> dict[str, Any]:
    """Verify the active official-news revision (succession rules) on disk."""

    from backtests.evidence_intake_control import collect_evidence_statuses  # noqa: PLC0415

    found = collect_evidence_statuses(evidence_root)
    record = found.get("official_news")
    if record is None:
        raise CostPolicyActivationError("no official-news package published")
    package = json.loads(
        (evidence_root / record["package_id"] / "package.json").read_text(encoding="utf-8")
    )["content"]
    if str(package.get("status")) != "ACCEPTED_DEVELOPMENT_ONLY":
        raise CostPolicyActivationError(
            "active official-news revision is not accepted for development use"
        )
    if package.get("complete") is not True or package.get("coverage_gaps"):
        raise CostPolicyActivationError("official-news revision is incomplete")
    months = package.get("months_covered")
    if not isinstance(months, (list, tuple)) or len(set(months)) != 12:
        raise CostPolicyActivationError("official-news revision must cover all 12 months")
    if not package.get("events"):
        raise CostPolicyActivationError("official-news revision carries no events")
    return {
        "package_id": str(record["package_id"]),
        "content_canonical_sha256": str(record["content_canonical_sha256"]),
        "event_count": len(package["events"]),
        "months_covered": len(set(months)),
    }


def build_acceptance_review(
    *,
    data_root: Path,
    evidence_root: Path | None = None,
    required_packages: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the dataset-acceptance review after re-checking identities on disk.

    Fail-closed: the frozen 8H policy package must exist, verify, and bind the
    same evidence identities reviewed here; otherwise the review is refused.
    """

    data_root = Path(data_root)
    evidence_root = Path(evidence_root) if evidence_root is not None else data_root / "evidence"

    policy_report = verify_published_policy(evidence_root)
    policy_content, _policy_dir = _policy_from_evidence_root(evidence_root)
    _enforce_frozen_ladder(policy_content)
    derived = _required_from_policy(policy_content, str(policy_report["package_id"]))
    if required_packages is None:
        _check_pinned_identities(derived)
        required = dict(derived)
    else:
        required = {**derived, **dict(required_packages)}
    identities = _verify_required_packages_on_disk(evidence_root, required)
    market_chain = _verify_market_data_chain(data_root)
    news_chain = _verify_official_news_revision(evidence_root)

    categories: list[dict[str, Any]] = []
    for template in ACCEPTANCE_REVIEW_CATEGORIES:
        category = dict(template)
        identity = str(category["identity"])
        for binding, package_id in identities.items():
            if package_id in identity:
                category["verified_package_id"] = package_id
                break
        name = str(category["category"])
        if name == "XAUUSDM_TICKS_2024":
            category["verified_package_id"] = market_chain["source_year_package_id"]
            category["verified_canonical_sha256"] = market_chain["source_year_canonical_sha256"]
            category["verified_row_count"] = market_chain["source_row_count"]
        elif name == "XAUUSDM_CAUSAL_CANDLES":
            category["verified_package_id"] = market_chain["derived_package_id"]
            category["verified_manifest_sha256"] = market_chain["derived_manifest_sha256"]
            category["verified_attestation_id"] = market_chain["attestation_id"]
        elif name == "OFFICIAL_USD_NEWS":
            category["verified_package_id"] = news_chain["package_id"]
            category["verified_canonical_sha256"] = news_chain["content_canonical_sha256"]
            category["verified_event_count"] = news_chain["event_count"]
        elif name == "DXY_DEVELOPMENT_INPUT":
            category["verified_package_id"] = market_chain["dxy_package_id"]
            category["verified_canonical_sha256"] = market_chain["dxy_canonical_sha256"]
            category["verified_row_count"] = market_chain["dxy_record_count"]
        categories.append(category)

    statuses = {str(c["category"]): str(c["status"]) for c in categories}
    accepted = {k for k, v in statuses.items() if v in {"ACCEPTED_EMPIRICAL", "ACCEPTED_DEVELOPMENT_ONLY"}}
    insufficient = {k for k, v in statuses.items() if v == "INSUFFICIENT"}
    blocked = {k for k, v in statuses.items() if v == "BLOCKED"}

    content: dict[str, Any] = {
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "record": "Phase 8I dataset-acceptance review of remaining owner-kit categories",
        "review_basis": {
            "cost_policy_package_id": str(policy_report["package_id"]),
            "cost_policy_fingerprint": str(policy_report["policy_fingerprint"]),
            "verified_evidence_packages": identities,
            "verified_market_data_chain": market_chain,
            "verified_official_news": news_chain,
        },
        "categories": categories,
        "statuses": statuses,
        "accepted_categories": sorted(accepted),
        "insufficient_categories": sorted(insufficient),
        "blocked_categories": sorted(blocked),
        "development_evaluation_sufficient": insufficient == set() and blocked == {"HOLDOUT"},
        "final_validation_authorized": False,
        "holdout_access_authorized": False,
        "strategy_evaluation_authorized": False,
        "accepted_for_final_validation": False,
        "notes": (
            "development-strength acceptance never upgrades to final-validation "
            "strength; effective-dated broker metadata remains insufficient and "
            "final-validation-strength commission/swap/slippage evidence remains open"
        ),
    }
    # Matrix-facing alias: the review as a whole is an accepted development
    # record; per-category truth lives in content["statuses"].  Added before
    # the review hash so verification recomputes over identical content.
    content["status"] = "ACCEPTED_DEVELOPMENT_ONLY"
    content["review_canonical_sha256"] = canonical_hash(
        {k: v for k, v in content.items() if k != "review_canonical_sha256"}
    )
    return content


def verify_acceptance_review(content: Mapping[str, Any]) -> dict[str, Any]:
    """Readback verification of a published acceptance-review package."""

    if str(content.get("schema_version")) != ACCEPTANCE_SCHEMA_VERSION:
        raise CostPolicyActivationError("acceptance-review schema version mismatch")
    if content.get("status") != "ACCEPTED_DEVELOPMENT_ONLY":
        raise CostPolicyActivationError("acceptance-review status alias drifted")
    categories = content.get("categories", [])
    if not categories:
        raise CostPolicyActivationError("acceptance review requires categories")
    expected = {str(t["category"]): str(t["status"]) for t in ACCEPTANCE_REVIEW_CATEGORIES}
    actual = {str(c["category"]): str(c["status"]) for c in categories}
    if actual != expected:
        raise CostPolicyActivationError("acceptance-review category statuses drifted")
    # The flat statuses map must agree with the per-category entries.
    if content.get("statuses") != actual:
        raise CostPolicyActivationError("acceptance-review statuses drifted from categories")
    for gate in (
        "final_validation_authorized",
        "holdout_access_authorized",
        "strategy_evaluation_authorized",
        "accepted_for_final_validation",
    ):
        if content.get(gate) is not False:
            raise CostPolicyActivationError(f"acceptance gate {gate} must remain false")
    if content.get("development_evaluation_sufficient") is True and (
        content.get("insufficient_categories") or content.get("blocked_categories") != ["HOLDOUT"]
    ):
        raise CostPolicyActivationError(
            "development sufficiency claimed while insufficient or blocked categories remain"
        )
    recorded = content.get("review_canonical_sha256")
    payload = {k: v for k, v in content.items() if k != "review_canonical_sha256"}
    if recorded != canonical_hash(payload):
        raise CostPolicyActivationError("acceptance-review hash mismatch (tampering detected)")
    return {
        "verified": True,
        "accepted_categories": list(content.get("accepted_categories", [])),
        "review_canonical_sha256": str(recorded),
    }
