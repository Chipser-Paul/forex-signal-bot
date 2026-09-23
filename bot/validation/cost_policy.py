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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from bot.acquisition.evidence_contracts import (
    DEVELOPMENT_ONLY_CLASSIFICATION,
    EvidenceError,
    canonical_hash,
)
from bot.scientific.canonical_bytes import make_git_blob_source
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
    """Full readback verification (historical legacy binding contract)."""
    return _verify_cost_policy_impl(
        content,
        execution_binding_contract=LEGACY_FINGERPRINT_CONTRACT,
        prospective_ctx=None,
    )


def _verify_cost_policy_impl(
    content: Mapping[str, Any],
    *,
    execution_binding_contract: str,
    prospective_ctx: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Full policy readback; execution-model binding per explicit contract.

    ``execution_binding_contract`` selects — explicitly, with no automatic
    fallback — how the artifact's execution-model binding is verified:

    * ``legacy_worktree_bytes_v0``: historical working-tree-byte comparison
      (unchanged historical semantics, including its checkout dependence);
    * ``canonical_git_blob_v1``: the artifact's recorded historical binding
      must be preserved verbatim as metadata while the live verification is
      performed by :func:`verify_cost_policy_prospective` against committed
      blobs.
    """
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
    if execution_binding_contract == LEGACY_FINGERPRINT_CONTRACT:
        if str(bindings["execution_model_fingerprint"]) != execution_model_fingerprint():
            raise CostPolicyError(
                "execution-model fingerprint drifted from the committed cost surface; "
                "the policy must be re-preregistered under a new revision"
            )
    elif execution_binding_contract == PROSPECTIVE_FINGERPRINT_CONTRACT:
        historical_fp = str((prospective_ctx or {}).get("historical_execution_model_fingerprint", ""))
        if not historical_fp:
            raise CostPolicyError("prospective binding requires the attested historical fingerprint")
        if str(bindings["execution_model_fingerprint"]) != historical_fp:
            raise CostPolicyError(
                "historical execution-model binding changed; policy artifact tampering detected"
            )
    else:
        raise CostPolicyError(
            f"unknown execution binding contract: {execution_binding_contract!r}"
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


# ---------------------------------------------------------------------------
# Prospective V2 canonical verification (canonical_git_blob_v1)
# ---------------------------------------------------------------------------

#: Fingerprint contracts.
LEGACY_FINGERPRINT_CONTRACT = "legacy_worktree_bytes_v0"
PROSPECTIVE_FINGERPRINT_CONTRACT = "canonical_git_blob_v1"

#: Schema for the prospective V2 compatibility attestation.
#:
#: v2 semantics: ``attestation_anchor_commit`` records where the attested
#: execution-model blobs were established (provenance anchor only).  The
#: LIVE verification commit is always caller-supplied (the active
#: evidence/source commit) and must independently reproduce the attested
#: canonical fingerprint — an anchor is never accepted as proof for
#: different committed code (no stale-commit evasion).
PROSPECTIVE_ATTESTATION_SCHEMA_VERSION = "phase8v2.cost-policy-canonical-attestation.v2"

_PROSPECTIVE_ATTESTATION_CLASSIFICATION = (
    "PROSPECTIVE_V2_COMPATIBILITY_ATTESTATION — NOT A REWRITE OF HISTORICAL POLICY"
)


def _git_blob_id(content: bytes) -> str:
    """Content-addressed Git blob object ID (SHA-1) for raw blob bytes."""
    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\x00" + content).hexdigest()


def build_prospective_attestation(
    *,
    canonical_commit: str,
    tooling_commit: str,
    policy_package_id: str,
    policy_artifact_sha256: str,
    policy_content_fingerprint: str,
    recorded_legacy_execution_model_fingerprint: str,
    canonical_execution_model_fingerprint: str,
    module_blob_shas: Mapping[str, str],
    publication_anchor_commit: str,
    v001_implementation_commit: str,
    canonical_readiness_commits: Sequence[str] = (),
    repo: Path | None = None,
    blob_source=None,
) -> dict[str, Any]:
    """Build the prospective V2 cost-policy compatibility attestation.

    Records — without rewriting — that the immutable historical cost-policy
    artifact binds its execution-model surface under the historical
    ``legacy_worktree_bytes_v0`` contract, and that the prospective V2
    verification contract for the identical frozen cost surface is
    ``canonical_git_blob_v1`` over the committed module blobs at
    ``canonical_commit``.
    """
    root = repo if repo is not None else Path(__file__).resolve().parents[2]
    modules = list(_EXECUTION_MODEL_MODULES)
    if tuple(sorted(module_blob_shas)) != tuple(sorted(modules)):
        raise CostPolicyError("attestation module set must match the execution-model surface exactly")
    source = blob_source if blob_source is not None else make_git_blob_source(root)
    git_blob_ids: dict[str, str] = {}
    for relative in modules:
        blob = source(canonical_commit, relative)
        observed = hashlib.sha256(blob).hexdigest()
        if observed != str(module_blob_shas[relative]):
            raise CostPolicyError(
                f"module blob SHA does not recompute from committed content: {relative}"
            )
        git_blob_ids[relative] = _git_blob_id(blob)
    recomputed = execution_model_fingerprint_canonical(
        canonical_commit, worktree=root, blob_source=source
    )
    if recomputed != canonical_execution_model_fingerprint:
        raise CostPolicyError(
            "canonical execution-model fingerprint does not recompute from committed blobs"
        )
    attestation: dict[str, Any] = {
        "schema_version": PROSPECTIVE_ATTESTATION_SCHEMA_VERSION,
        "classification": _PROSPECTIVE_ATTESTATION_CLASSIFICATION,
        "research_identity": "phase6-development-v2",
        "historical_cost_policy": {
            "package_id": policy_package_id,
            "artifact_sha256": policy_artifact_sha256,
            "policy_fingerprint": policy_content_fingerprint,
            "immutable_historical_artifact": True,
            "recorded_execution_model_fingerprint": recorded_legacy_execution_model_fingerprint,
            "recorded_fingerprint_contract": LEGACY_FINGERPRINT_CONTRACT,
            "publication_anchor_commit": publication_anchor_commit,
        },
        "prospective_verification": {
            "fingerprint_contract": PROSPECTIVE_FINGERPRINT_CONTRACT,
            "attestation_anchor_commit": canonical_commit,
            "execution_model_modules": list(modules),
            "module_blob_shas": dict(sorted(module_blob_shas.items())),
            "module_git_blob_ids": dict(sorted(git_blob_ids.items())),
            "canonical_execution_model_fingerprint": canonical_execution_model_fingerprint,
        },
        "v001_lineage": {
            "implementation_commit": v001_implementation_commit,
            "measurement_tooling_commit": tooling_commit,
            "canonical_readiness_commits": list(canonical_readiness_commits),
        },
        "representation_drift_statement": (
            "representation drift only; no execution-cost source-content drift"
        ),
        "cost_semantics_unchanged": True,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    attestation["attestation_fingerprint"] = hashlib.sha256(
        canonical_json_bytes({k: v for k, v in attestation.items() if k != "attestation_fingerprint"})
    ).hexdigest()
    return attestation


def verify_cost_policy_prospective(
    content: Mapping[str, Any],
    attestation: Mapping[str, Any],
    *,
    commit: str,
    repo: Path | None = None,
    blob_source=None,
) -> dict[str, Any]:
    """Explicit prospective V2 cost-policy verification.

    Full historical policy-content verification (cost values, acceptance
    semantics, restrictions — everything :func:`verify_cost_policy` checks)
    plus ``canonical_git_blob_v1`` execution-model binding against committed
    blobs at ``commit`` (the ACTIVE evidence/source commit) and against a
    required compatibility attestation whose anchor must cover the same
    blobs.  A stale anchor presented for drifted active code fails closed.

    The caller must explicitly present the attestation and the active
    commit; there is no automatic fallback from legacy verification.
    """
    if not isinstance(attestation, Mapping) or not attestation:
        raise CostPolicyError("prospective verification requires a compatibility attestation")
    if attestation.get("schema_version") != PROSPECTIVE_ATTESTATION_SCHEMA_VERSION:
        raise CostPolicyError("attestation schema version mismatch")
    if attestation.get("classification") != _PROSPECTIVE_ATTESTATION_CLASSIFICATION:
        raise CostPolicyError("attestation classification mismatch")
    if attestation.get("research_identity") != "phase6-development-v2":
        raise CostPolicyError("attestation research identity mismatch")
    recorded_fp = attestation.get("attestation_fingerprint")
    if not recorded_fp or hashlib.sha256(
        canonical_json_bytes({k: v for k, v in attestation.items() if k != "attestation_fingerprint"})
    ).hexdigest() != str(recorded_fp):
        raise CostPolicyError("attestation fingerprint mismatch (tampering detected)")

    prospective = attestation["prospective_verification"]
    if prospective.get("fingerprint_contract") != PROSPECTIVE_FINGERPRINT_CONTRACT:
        raise CostPolicyError(
            "attestation must bind the canonical_git_blob_v1 contract"
        )
    historical = attestation["historical_cost_policy"]
    if historical.get("recorded_fingerprint_contract") != LEGACY_FINGERPRINT_CONTRACT:
        raise CostPolicyError("historical contract metadata must remain legacy_worktree_bytes_v0")
    if historical.get("immutable_historical_artifact") is not True:
        raise CostPolicyError("historical artifact must be declared immutable")
    attested_policy_fp = historical.get("policy_fingerprint")
    if not attested_policy_fp or str(attested_policy_fp) != str(content.get("policy_fingerprint")):
        raise CostPolicyError("attestation does not bind the presented policy content")
    if attestation.get("cost_semantics_unchanged") is not True:
        raise CostPolicyError("attestation must declare cost semantics unchanged")

    modules = list(_EXECUTION_MODEL_MODULES)
    if list(prospective.get("execution_model_modules", [])) != modules:
        raise CostPolicyError("attested execution-model module set drifted")
    attested_blobs = prospective.get("module_blob_shas", {})
    if tuple(sorted(attested_blobs)) != tuple(sorted(modules)):
        raise CostPolicyError("attested module blob set drifted")
    attested_canonical = str(prospective.get("canonical_execution_model_fingerprint", ""))
    if not attested_canonical:
        raise CostPolicyError("attestation must bind a canonical execution-model fingerprint")

    root = repo if repo is not None else Path(__file__).resolve().parents[2]
    source = blob_source if blob_source is not None else make_git_blob_source(root)
    attested_git_ids = prospective.get("module_git_blob_ids", {})
    if tuple(sorted(attested_git_ids)) != tuple(sorted(modules)):
        raise CostPolicyError("attested module git blob id set drifted")
    for relative in modules:
        blob = source(commit, relative)
        if hashlib.sha256(blob).hexdigest() != str(attested_blobs[relative]):
            raise CostPolicyError(
                f"execution-model module content drifted from attestation: {relative}"
            )
        if _git_blob_id(blob) != str(attested_git_ids[relative]):
            raise CostPolicyError(
                f"execution-model module git blob id drifted from attestation: {relative}"
            )
    recomputed = execution_model_fingerprint_canonical(
        commit, worktree=root, blob_source=source
    )
    if recomputed != attested_canonical:
        raise CostPolicyError(
            "canonical execution-model fingerprint drifted from attestation"
        )

    # Full historical policy-content verification (cost values and
    # acceptance semantics are NOT relaxed for V2).  The artifact's
    # historical legacy binding is verified verbatim as preserved metadata;
    # the live execution-model check is the canonical blob verification above.
    report = _verify_cost_policy_impl(
        content,
        execution_binding_contract=PROSPECTIVE_FINGERPRINT_CONTRACT,
        prospective_ctx={
            "historical_execution_model_fingerprint": str(
                historical["recorded_execution_model_fingerprint"]
            ),
        },
    )
    report["execution_binding_contract"] = PROSPECTIVE_FINGERPRINT_CONTRACT
    report["canonical_execution_model_fingerprint"] = recomputed
    report["attestation_fingerprint"] = str(recorded_fp)
    report["historical_execution_model_fingerprint_preserved"] = str(
        historical["recorded_execution_model_fingerprint"]
    )
    return report
