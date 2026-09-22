"""Phase 8H — frozen development-only transaction-cost policy.

Preregisters ``phase8h.development-cost-policy.v1``: a hash-bound, immutable
description of how transaction costs are accounted during 2024 development
evaluation.  The policy freezes — before any strategy result is observed —

- the evidence basis of every cost component (observed spread, commission
  NONE bound to broker-support evidence, unresolved swap units, uncalibrated
  slippage);
- the ordered swap and slippage scenario ladder (no cheapest-scenario
  selection is possible by construction);
- the unresolved swap-unit conflict (points vs USD per lot), preserved
  verbatim with conversion and selection prohibited;
- the binding set (strategy / execution-model / risk-policy fingerprints,
  2024 dataset, derived candles, broker-support revision, observed spread).

The policy is never activated for evaluation here.  Publishing is atomic,
non-overwriting and content-addressed through the existing Phase 8E evidence
store.  ``ACTIVE`` is not a representable state: any attempt to set it fails
closed.

Safety: no strategy evaluation, no holdout access, no MT5, no network, no
account or trading surface.  Everything remains
DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from bot.acquisition.evidence_contracts import (
    DEVELOPMENT_ONLY_CLASSIFICATION,
    EvidenceError,
    canonical_hash,
)
from bot.strategy.config import StrategyConfig
from bot.execution.risk.models import RiskPolicy

POLICY_SCHEMA_VERSION = "phase8h.development-cost-policy.v1"
POLICY_LABEL = "frozen development transaction-cost policy (preregistered, inactive)"

SYMBOL = "XAUUSDm"
ACCOUNT_TYPE = "Exness Standard MT5"
DEVELOPMENT_INTERVAL = ("2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z")

# Current support-reference swap values (email, USD per 1.00 lot per day).
# CURRENT_SUPPORT_REFERENCE — never historical 2024 evidence.
SWAP_EMAIL_LONG_USD_PER_LOT = -3.85
SWAP_EMAIL_SHORT_USD_PER_LOT = -0.25
# Current platform display (screenshot, points per lot, swap type "In points").
# The short value was not clearly readable and is recorded as unavailable.
SWAP_SCREENSHOT_LONG_POINTS = -534.9
TRIPLE_SWAP_WEEKDAY = "WEDNESDAY"
TRIPLE_SWAP_MULTIPLIER = 3

# Slippage scenario points (0.001 MT5 points; one pip = 10 points; one point
# on one lot = 0.10 USD).  Anchored to the Phase 7 execution-model boundary —
# the replay engine's adverse-entry diagnostic uses FIXED_ADVERSE_POINTS=1 —
# and extended by conservative integer multipliers chosen without reference
# to any strategy outcome.  Source: CostSource.ASSUMED (uncalibrated).
SLIPPAGE_ANCHOR_POINTS = 1.0
SLIPPAGE_SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "scenario_id": "SLIPPAGE_NEUTRAL_DIAGNOSTIC",
        "kind": "FIXED_ADVERSE_POINTS",
        "points": 0.0,
        "usd_per_point_per_lot": 0.10,
        "classification": "ASSUMPTION_ONLY",
        "rationale": "diagnostic only: quantifies execution-model behaviour without adverse assumption",
    },
    {
        "scenario_id": "SLIPPAGE_MODERATE_ADVERSE",
        "kind": "FIXED_ADVERSE_POINTS",
        "points": 1.0,
        "usd_per_point_per_lot": 0.10,
        "classification": "ASSUMPTION_ONLY",
        "rationale": (
            "Phase 7 realistic-execution replay already exercises the engine at "
            "FIXED_ADVERSE_POINTS=1 (execution-model boundary); adopted as the "
            "moderate rung without inspecting any strategy result"
        ),
    },
    {
        "scenario_id": "SLIPPAGE_SEVERE_ADVERSE",
        "kind": "FIXED_ADVERSE_POINTS",
        "points": 3.0,
        "usd_per_point_per_lot": 0.10,
        "classification": "ASSUMPTION_ONLY",
        "rationale": (
            "conservative 3x multiple of the execution-model anchor (3 pips on "
            "gold = 3 USD per lot adverse); chosen a priori, not from outcomes"
        ),
    },
)

# Ordered scenario ladders.  Order is part of the frozen contract; a
# cheapest-passing scenario can never be selected because disclosure must
# cover every scenario and the required adverse boundary is fixed below.
SWAP_SCENARIO_ORDER = (
    "SWAP_NO_OVERNIGHT_EXPOSURE_DIAGNOSTIC",
    "SWAP_EMAIL_REFERENCE",
    "SWAP_EMAIL_2X_ADVERSE",
    "SWAP_EMAIL_3X_ADVERSE",
)
REQUIRED_ADVERSE_BOUNDARY = "SWAP_EMAIL_3X_ADVERSE"


class CostPolicyError(EvidenceError):
    """Raised when the frozen cost policy is violated or tampered with."""


# ---------------------------------------------------------------------------
# Frozen component records
# ---------------------------------------------------------------------------


def spread_treatment_record() -> dict[str, Any]:
    return {
        "component": "SPREAD",
        "basis": "OBSERVED_EMPIRICAL_BID_ASK_ONLY",
        "classification": "OBSERVED_EMPIRICAL",
        "source": "observed_spread-v1-e25bdb9bf028a5be (2024 XAUUSDm bid/ask tick dataset)",
        "rule": (
            "historical spread comes directly from observed bid/ask data; "
            "fixed spreads, advertised spreads and forward-filled quotes are prohibited"
        ),
        "forward_fill_prohibited": True,
        "fixed_spread_substitution_prohibited": True,
    }


def commission_treatment_record() -> dict[str, Any]:
    return {
        "component": "COMMISSION",
        "basis": "BROKER_SUPPORT_ASSERTED_NONE",
        "classification": "DEVELOPMENT_ONLY",
        "mode": "NONE",
        "amount": 0,
        "currency": "USD",
        "per_side_charge": 0,
        "round_turn_charge": 0,
        "minimum_charge": 0,
        "effective_interval_established": False,
        "limitation": (
            "no historically dated 2024 change archive exists; the zero rate is "
            "broker-asserted for the Standard account, not dated effective evidence"
        ),
        "final_validation_eligible": False,
    }


def swap_treatment_record() -> dict[str, Any]:
    return {
        "component": "SWAP",
        "basis": "UNRESOLVED_UNITS_CONFLICT",
        "classification": "HISTORICAL_VALUE_UNAVAILABLE",
        "single_historical_value_presented_as_truth": False,
        "email_reference": {
            "classification": "CURRENT_SUPPORT_REFERENCE",
            "long_usd_per_lot_per_day": SWAP_EMAIL_LONG_USD_PER_LOT,
            "short_usd_per_lot_per_day": SWAP_EMAIL_SHORT_USD_PER_LOT,
            "note": "current support reference; not verified historical 2024 swap",
        },
        "screenshot_reference": {
            "classification": "CURRENT_ONLY_NOT_HISTORICAL",
            "long_points_per_lot": SWAP_SCREENSHOT_LONG_POINTS,
            "short_points_per_lot": None,
            "short_readability": "NOT_CLEARLY_READABLE_TRUNCATED",
            "swap_type": "points",
        },
        "unit_conflict_preserved": True,
        "conversion_prohibited": True,
        "averaging_prohibited": True,
        "single_source_selection_prohibited": True,
        "triple_swap_weekday": TRIPLE_SWAP_WEEKDAY,
        "holiday_adjustments": "unspecified",
        "historical_2024_values": None,
        "historical_change_dates": None,
    }


def slippage_treatment_record() -> dict[str, Any]:
    return {
        "component": "SLIPPAGE",
        "basis": "NO_CALIBRATED_HISTORICAL_EVIDENCE",
        "classification": "ASSUMPTION_ONLY",
        "silent_zero_for_acceptance_prohibited": True,
        "scenario_values_derived_from": (
            "Phase 7 execution-model boundary (adverse-entry replay uses "
            "FIXED_ADVERSE_POINTS=1) extended by conservative integer multiples; "
            "no strategy outcome was inspected to select them"
        ),
    }


def build_swap_scenarios() -> tuple[dict[str, Any], ...]:
    long_ref = SWAP_EMAIL_LONG_USD_PER_LOT
    short_ref = SWAP_EMAIL_SHORT_USD_PER_LOT

    def scenario(scenario_id: str, multiplier: float, role: str) -> dict[str, Any]:
        applied_long = round(long_ref * multiplier, 10) + 0.0  # +0.0 normalizes -0.0
        applied_short = round(short_ref * multiplier, 10) + 0.0
        return {
            "scenario_id": scenario_id,
            "classification": "ASSUMPTION_ONLY",
            "swap_multiplier_vs_email_reference": multiplier,
            "long_usd_per_lot_per_day": applied_long,
            "short_usd_per_lot_per_day": applied_short,
            "no_favorable_positive_swap_credit": True,
            "triple_swap_weekday": TRIPLE_SWAP_WEEKDAY,
            "triple_swap_multiplier": TRIPLE_SWAP_MULTIPLIER,
            "applicability": {
                "long_positions": applied_long != 0.0,
                "short_positions": applied_short != 0.0,
                "partial_volume": "charged pro rata on open volume per day",
                "rollover_crossing_required": True,
            },
            "role": role,
        }

    return (
        scenario(
            "SWAP_NO_OVERNIGHT_EXPOSURE_DIAGNOSTIC",
            0.0,
            "diagnostic: isolates intraday behaviour by zeroing swap; never the "
            "primary acceptance result when trades cross rollover",
        ),
        scenario(
            "SWAP_EMAIL_REFERENCE",
            1.0,
            "development reference: current support-reference values used as-is",
        ),
        scenario(
            "SWAP_EMAIL_2X_ADVERSE",
            2.0,
            "adverse rung: doubles the (already negative) email reference",
        ),
        scenario(
            "SWAP_EMAIL_3X_ADVERSE",
            3.0,
            "required adverse boundary: results failing here must be visible and "
            "cannot be discarded",
        ),
    )


def build_acceptance_restrictions() -> dict[str, Any]:
    return {
        "disclose_all_scenarios": True,
        "cheapest_scenario_pass_rule": "PROHIBITED",
        "required_adverse_boundary": REQUIRED_ADVERSE_BOUNDARY,
        "per_scenario_disclosure": (
            "expectancy, profit factor, drawdown and circuit behaviour must be "
            "reported scenario-by-scenario"
        ),
        "automatic_parameter_selection": "PROHIBITED",
        "uncertainty_labeling": (
            "every relevant result must carry the historical-swap uncertainty label"
        ),
        "uncertainty_label": "HISTORICAL_SWAP_UNCERTAIN",
        "final_validation_authorized": False,
        "holdout_access_authorized": False,
        "strategy_evaluation_authorized": False,
    }


# ---------------------------------------------------------------------------
# Binding set
# ---------------------------------------------------------------------------

#: Files whose content defines the execution-cost-surface fingerprint
#: (shared verbatim by the legacy working-tree fingerprint and the
#: prospective canonical_git_blob_v1 fingerprint).
_EXECUTION_MODEL_MODULES = (
    "bot/backtesting/costs.py",
    "bot/backtesting/models.py",
    "bot/backtesting/engine.py",
)


def strategy_fingerprint(config: StrategyConfig | None = None) -> str:
    config = config or StrategyConfig()
    return canonical_hash(config.fingerprint())


def risk_policy_fingerprint(policy: RiskPolicy | None = None) -> str:
    policy = policy or RiskPolicy()
    payload = json.dumps(
        dataclasses.asdict(policy), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def execution_model_fingerprint() -> str:
    """Fingerprint the committed execution-cost surface (content hash)."""
    worktree = Path(__file__).resolve().parents[2]
    modules = _EXECUTION_MODEL_MODULES
    module_hashes: dict[str, str] = {}
    for relative in modules:
        blob = (worktree / relative).read_bytes()
        module_hashes[relative] = hashlib.sha256(blob).hexdigest()
    payload = json.dumps(
        {"modules": dict(sorted(module_hashes.items()))},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def execution_model_fingerprint_canonical(
    commit: str, worktree: Path | None = None, *, blob_source=None
) -> str:
    """Prospective ``canonical_git_blob_v1`` execution-cost-surface fingerprint.

    Same module surface (``bot/backtesting/costs.py``, ``models.py``,
    ``engine.py`` — lexicographically ordered by the canonical contract) but
    hashed from the **committed Git blobs** at ``commit`` through the versioned
    canonical-byte contract (``bot.scientific.canonical_bytes``).  Checkout
    representation (``core.autocrlf``, CRLF vs LF) cannot influence the
    digest.

    Mandatory for all future (post-V1) scientific freezes.  The legacy
    :func:`execution_model_fingerprint` keeps its historical
    raw-working-tree-bytes semantics (``legacy_worktree_bytes_v0``) and is
    retained solely for verifying already-published historical artifacts such
    as the published cost policy.  The two are different contracts and are
    never interchangeable.
    """
    from bot.scientific.canonical_bytes import canonical_framed_digest

    root = Path(worktree) if worktree is not None else Path(__file__).resolve().parents[2]
    return canonical_framed_digest(
        _EXECUTION_MODEL_MODULES, commit=commit, repo=root, blob_source=blob_source
    )


def build_bindings(
    *,
    data_root: Path,
    broker_support_content_sha256: str,
    strategy_config: StrategyConfig | None = None,
    risk_policy: RiskPolicy | None = None,
) -> dict[str, Any]:
    data_root = Path(data_root)
    derived_manifest_path = (
        data_root
        / "derived"
        / "derived-candles-2024-v1-20260911T195553Z"
        / "manifest.json"
    )
    if not derived_manifest_path.is_file():
        raise CostPolicyError("derived candle package manifest is missing")
    derived = json.loads(derived_manifest_path.read_text(encoding="utf-8"))
    dxy_manifest_path = (
        data_root
        / "dxy"
        / "dxy-development-2024-v1-20260912T091410.712364Z"
        / "manifest.json"
    )
    if not dxy_manifest_path.is_file():
        raise CostPolicyError("DXY development package manifest is missing")
    dxy = json.loads(dxy_manifest_path.read_text(encoding="utf-8"))
    causal = dxy["causal_dxy"]

    identity_basis = (
        "content identity: canonical content hashes and package ids; "
        "no absolute local path is part of the identity"
    )
    return {
        "identity_basis": identity_basis,
        "strategy_fingerprint": strategy_fingerprint(strategy_config),
        "execution_model_fingerprint": execution_model_fingerprint(),
        "risk_policy_fingerprint": risk_policy_fingerprint(risk_policy),
        "development_dataset": {
            "year_package_id": derived["year_package_id"],
            "source_canonical_sha256": derived["source_canonical_sha256"],
            "source_row_count": derived["source_row_count"],
        },
        "derived_candles": {
            "package_id": "derived-candles-2024-v1-6715e5c64d888215",
            "manifest_sha256": "6715e5c64d888215ea9c88a6ab77e5340046f367ed6250813158f6b1f096d316",
            "attestation_id": "derived-candles-attestation-v1-6715e5c64d888215",
        },
        "broker_support_revision": {
            "package_id": "evidence-broker_support-v1-3b68b4203a9109b9",
            "content_canonical_sha256": broker_support_content_sha256,
        },
        "observed_spread_evidence": {
            "package_id": "observed_spread-v1-e25bdb9bf028a5be",
            "content_canonical_sha256": (
                "e25bdb9bf028a5bebf4af229e9baf31769391f128008e5923bee11db2ef47dce"
            ),
        },
        "dxy_development_input": {
            "package_id": str(dxy["package_id"]),
            "dxy_canonical_sha256": str(causal["canonical_content_sha256"]),
            "dxy_row_count": int(causal["record_count"]),
        },
    }


# ---------------------------------------------------------------------------
# Policy assembly and verification
# ---------------------------------------------------------------------------


def build_cost_policy(
    *,
    data_root: Path,
    broker_support_content_sha256: str,
    strategy_config: StrategyConfig | None = None,
    risk_policy: RiskPolicy | None = None,
) -> dict[str, Any]:
    swap_scenarios = build_swap_scenarios()
    if tuple(s["scenario_id"] for s in swap_scenarios) != SWAP_SCENARIO_ORDER:
        raise CostPolicyError("swap scenario order drifted from the frozen ladder")
    multipliers = [s["swap_multiplier_vs_email_reference"] for s in swap_scenarios]
    if multipliers != sorted(multipliers):
        raise CostPolicyError("swap scenario ladder must be ordered non-decreasing")
    required = next(
        s for s in swap_scenarios if s["scenario_id"] == REQUIRED_ADVERSE_BOUNDARY
    )
    if required["swap_multiplier_vs_email_reference"] != 3.0:
        raise CostPolicyError("required adverse boundary must be the 3x scenario")
    for s in swap_scenarios:
        if s["long_usd_per_lot_per_day"] > 0 or s["short_usd_per_lot_per_day"] > 0:
            raise CostPolicyError("no favorable positive swap credit is permitted")
    slip_points = [s["points"] for s in SLIPPAGE_SCENARIOS]
    if slip_points != sorted(slip_points):
        raise CostPolicyError("slippage scenario points must be ordered non-decreasing")

    content: dict[str, Any] = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "label": POLICY_LABEL,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "symbol": SYMBOL,
        "account_type": ACCOUNT_TYPE,
        "development_interval": list(DEVELOPMENT_INTERVAL),
        "policy_state": "PREREGISTERED_INACTIVE",
        # Matrix-facing alias of policy_state (Phase 8E collector reads
        # content["status"]); verification requires the two to agree.
        "status": "PREREGISTERED_INACTIVE",
        "activation_authorized": False,
        "cost_components": {
            "spread": spread_treatment_record(),
            "commission": commission_treatment_record(),
            "swap": swap_treatment_record(),
            "slippage": slippage_treatment_record(),
        },
        "swap_scenarios": list(swap_scenarios),
        "slippage_scenarios": [dict(s) for s in SLIPPAGE_SCENARIOS],
        "acceptance_restrictions": build_acceptance_restrictions(),
    }
    content["bindings"] = build_bindings(
        data_root=data_root,
        broker_support_content_sha256=broker_support_content_sha256,
        strategy_config=strategy_config,
        risk_policy=risk_policy,
    )
    content["policy_fingerprint"] = policy_fingerprint(content)
    return content


def policy_fingerprint(content: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical policy JSON excluding the fingerprint field."""
    payload = {k: v for k, v in content.items() if k != "policy_fingerprint"}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def verify_cost_policy(content: Mapping[str, Any]) -> dict[str, Any]:
    """Full readback verification.  Raises CostPolicyError on any violation."""
    if str(content.get("schema_version")) != POLICY_SCHEMA_VERSION:
        raise CostPolicyError("policy schema version mismatch")
    if str(content.get("policy_state")) != "PREREGISTERED_INACTIVE":
        raise CostPolicyError("policy must remain PREREGISTERED_INACTIVE")
    if content.get("status", content.get("policy_state")) != content.get("policy_state"):
        raise CostPolicyError("status alias must agree with policy_state")
    if content.get("activation_authorized") is not False:
        raise CostPolicyError("policy activation must remain unauthorized")
    recorded = content.get("policy_fingerprint")
    if not recorded or policy_fingerprint(content) != str(recorded):
        raise CostPolicyError("policy fingerprint mismatch (tampering detected)")

    components = content["cost_components"]
    spread = components["spread"]
    if spread["basis"] != "OBSERVED_EMPIRICAL_BID_ASK_ONLY":
        raise CostPolicyError("spread must be observed bid/ask only")
    if not spread["fixed_spread_substitution_prohibited"]:
        raise CostPolicyError("fixed-spread substitution must remain prohibited")
    commission = components["commission"]
    if commission["mode"] != "NONE" or commission["amount"] != 0:
        raise CostPolicyError("commission must remain the evidence-bound NONE record")
    if commission["final_validation_eligible"] is not False:
        raise CostPolicyError("commission must not claim final-validation eligibility")
    swap = components["swap"]
    if not swap["unit_conflict_preserved"] or not swap["conversion_prohibited"]:
        raise CostPolicyError("swap-unit conflict must stay preserved with conversion prohibited")
    if swap["historical_2024_values"] is not None:
        raise CostPolicyError("no historical 2024 swap value may be presented")
    slip = components["slippage"]
    if slip["classification"] != "ASSUMPTION_ONLY":
        raise CostPolicyError("slippage must remain assumption-only")

    scenarios = content["swap_scenarios"]
    if tuple(s["scenario_id"] for s in scenarios) != SWAP_SCENARIO_ORDER:
        raise CostPolicyError("swap scenario order mismatch")
    if scenarios[0]["long_usd_per_lot_per_day"] != 0.0:
        raise CostPolicyError("diagnostic swap scenario must be the zero-exposure case")
    if scenarios[1]["long_usd_per_lot_per_day"] != SWAP_EMAIL_LONG_USD_PER_LOT:
        raise CostPolicyError("email-reference scenario drifted from the frozen value")
    if scenarios[1]["short_usd_per_lot_per_day"] != SWAP_EMAIL_SHORT_USD_PER_LOT:
        raise CostPolicyError("email-reference short scenario drifted from the frozen value")
    for s in scenarios:
        if s["triple_swap_weekday"] != TRIPLE_SWAP_WEEKDAY:
            raise CostPolicyError("triple-swap Wednesday must be preserved in every scenario")
        if s["triple_swap_multiplier"] != TRIPLE_SWAP_MULTIPLIER:
            raise CostPolicyError("triple-swap multiplier must remain 3")
        if s["long_usd_per_lot_per_day"] > 0 or s["short_usd_per_lot_per_day"] > 0:
            raise CostPolicyError("positive swap credit is not permitted")
    slip_scenarios = content["slippage_scenarios"]
    if [s["points"] for s in slip_scenarios] != [0.0, 1.0, 3.0]:
        raise CostPolicyError("slippage scenario values drifted from the frozen ladder")

    restrictions = content["acceptance_restrictions"]
    if restrictions["cheapest_scenario_pass_rule"] != "PROHIBITED":
        raise CostPolicyError("cheapest-scenario selection must stay prohibited")
    if restrictions["required_adverse_boundary"] != REQUIRED_ADVERSE_BOUNDARY:
        raise CostPolicyError("required adverse boundary drifted")
    for gate in (
        "final_validation_authorized",
        "holdout_access_authorized",
        "strategy_evaluation_authorized",
    ):
        if restrictions[gate] is not False:
            raise CostPolicyError(f"{gate} must remain false")

    bindings = content["bindings"]
    for field in (
        "strategy_fingerprint",
        "execution_model_fingerprint",
        "risk_policy_fingerprint",
    ):
        value = str(bindings.get(field, ""))
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise CostPolicyError(f"binding {field} must be a SHA-256 fingerprint")
    if str(bindings["execution_model_fingerprint"]) != execution_model_fingerprint():
        raise CostPolicyError(
            "execution-model fingerprint drifted from the committed cost surface; "
            "the policy must be re-preregistered under a new revision"
        )
    for binding_name in ("broker_support_revision", "observed_spread_evidence"):
        digest = str(
            bindings.get(binding_name, {}).get("content_canonical_sha256", "")
        )
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise CostPolicyError(f"binding {binding_name} must carry a SHA-256 hash")
    if "absolute_path" in bindings or any(
        "C:\\" in json.dumps(v) for v in bindings.values() if isinstance(v, str)
    ):
        raise CostPolicyError("absolute paths must never appear in bindings")
    return {
        "verified": True,
        "policy_fingerprint": str(recorded),
        "policy_state": str(content["policy_state"]),
        "schema_version": POLICY_SCHEMA_VERSION,
    }
