"""Preregistered D006 Fold-01 structural diagnostic tooling (H008).

DEVELOPMENT_DIAGNOSTIC_EVIDENCE — D006 — FOLD01 — NOT PROFITABILITY EVIDENCE

Governance
----------
* Diagnostic:        phase8-v2-D006 (V003 Post-Confluence Entry-State
                     Attrition Decomposition)
* Linked hypothesis: phase8-v2-H008 (Post-Confluence Entry-State Alignment
                     Bottleneck, registered 2026-09-30; statement, rationale,
                     expected effects and failure mode preserved EXACTLY —
                     never rewritten by D006)
* Motivating result: phase6-development-v2-V003-R001 (OPPORTUNITY_INSUFFICIENT,
                     candidate_ready 81 vs frozen adequacy target 90;
                     61 V002 candidates preserved + 20 temporal additions)
* Specification:     docs/PHASE8_V2_DIAGNOSTIC_D006.md (SHA-256 below)
* Charter:           phase8-v2-research-charter-v1-8527e3a5eec98f53
* Forensic status:   S002 cleared (canonical store verified intact)

READ-ONLY diagnostic (frozen preregistration):

* Population: V003 observations satisfying:
    v003_gate11_passed == True (V003 8/8 Gate-11 score pass)
    AND v003_strategy_eligible == True (canonical strategy entry_eligible)
    AND v003_entry_ready == False (frozen determine_entry returns no entry)
  The primary population (P_ENTRY_REJECT) is derived naturally at execution time;
  no expected empirical count is encoded into diagnostic logic or synthetic tests.
* Stage partitions: all V003 Gate-11 entrants partition into:
    R_GATE11_FAIL (failed V003 8/8 score)
    R_STRATEGY_REJECT (passed score, failed canonical strategy protections)
    R_READY (passed score and strategy, entry-ready)
    P_ENTRY_REJECT (passed score and strategy, entry-rejected)
  Every entrant belongs to exactly one partition; pairwise disjointness holds.
* Primary ID reconciliation: primary decision IDs must equal
  (canonical_strategy_pass_set - candidate_ready_set) exactly.
* Stratification: all primary and reference surfaces are stratified by
  FINAL_SURFACE vs TEMPORAL_MEMORY (frozen v003_fvg_evidence_source); never merged.
* Source of truth: strategies/smc_engine/entry_model.py::determine_entry
  and strategies/smc_engine/strategy_state.py::StrategyState.
* Rejection classifier (deterministic, read-only, ordered):
    E1 — STATE_EXPIRED: state.is_expired() == True
    E2 — READINESS_INCOMPLETE: ready_for_entry() == False and early_entry_ok == False
    E3 — STRUCTURE_DIRECTION_UNRESOLVED: structure_dir not in {"bullish", "bearish"}
    E4 — LIQUIDITY_ALIGNMENT_MISMATCH: liquidity alignment combination invalid
    E5 — UNMAPPED_ENTRY_REJECTION: determine_entry returns None but E1-E4 not mapped
* Live-zone separation and state invariance: StrategyState is NEVER mutated.
  Diagnostic evaluation uses independent deep copies.
* No counterfactual candidates, no downstream relaxation, no parameter search,
  no profitability metrics, no V004 creation.
* Fold 01 ONLY; the historical store fold-01-1d710826193a6767 is refused;
  Tier B (Folds 02-04), holdout and 2025+ fail closed.
* THIS TOOLING IS NOT EXECUTED BY THE FREEZE TASK. Empirical execution
  requires separate supervisory authorization; at the instant first Fold-01
  D006 observation occurs, diagnostics become permanently 5 / 12.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backtests.phase8_v2_diagnostic_d001 import (  # noqa: E402
    FOLD01_END,
    FOLD01_START,
    _reference_check_failed,
    _snapshot_rows,
    classify_snapshot,
    evaluate_orchestration_decision,
    reconcile_accounting,
)
from backtests.phase8_v2_variant_v001_eval import (  # noqa: E402
    HOLDOUT_TOKENS,
    reject_holdout_path,
)
from backtests.phase8_v2_variant_v002_eval import (  # noqa: E402
    _consumed_ids_from_record,
    _entry_frame,
    _gate_funnel,
    _persisted_setup_id,
    _reject_banned_metrics,
    _v002_private_entry_state,
    check_store_boundary,
)
from backtests.phase8_v2_variant_v003_eval import (  # noqa: E402
    V003_FVG_LABEL,
    V003_OB_LABEL,
    _age_summary,
    _canonical,
    _iso,
    _v003_entry,
    _v003_entry_readiness,
    assert_store_semantic_compatibility,
    observe_v003_decision,
    validate_authorized_store_path,
)
from strategies.smc_engine.entry_model import (  # noqa: E402
    _can_use_early_entry,
    determine_entry,
)
from strategies.smc_engine.strategy_state import (  # noqa: E402
    STATE_EXPIRY_MINUTES,
    StrategyState,
)

D006_ID = "phase8-v2-D006"
H008_ID = "phase8-v2-H008"
V003_ID = "phase6-development-v2-V003"
V003_RESULT_ID = "phase6-development-v2-V003-R001"
CHARTER_ID = "phase8-v2-research-charter-v1-8527e3a5eec98f53"
CHARTER_SHA256 = "8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc"
SPEC_PHASE_A_SHA256 = "a50b2e0ddfd84ecfa087dc5c347473cad40c58eb4f04c57f4f52038c73aa1ba6"
SPEC_TC001_SHA256 = "fe29aa848c489b8d3f7a5e937efca20ef93bde9625f88d32ddd8f3ca9ec1a5eb"
SPEC_TC002_SHA256 = "4ebe97b997f530e2d60a8b1f3a25f62e5c2e22456c7ccfc375b28b727add42ad"
SPEC_SHA256 = SPEC_TC002_SHA256
SPECIFICATION_DOCUMENT = "docs/PHASE8_V2_DIAGNOSTIC_D006.md"
CLASSIFICATION = (
    "DEVELOPMENT_DIAGNOSTIC_EVIDENCE — D006 — FOLD01 — NOT PROFITABILITY EVIDENCE"
)
TOOLING_RELPATH = "backtests/phase8_v2_diagnostic_d006.py"
FINGERPRINT_CONTRACT = "canonical_git_blob_v1"
AUTHORIZED_FOLD01_STORE_BASENAME = "fold-01-a8b406884ab3525a"
HISTORICAL_STORE_ID = "fold-01-1d710826193a6767"

V003_STRATEGY_MODULE = "bot/strategy/variant_v003.py"
V003_STRATEGY_GIT_BLOB_SHA = "c25f110c15c60bc5b32cffc0b3870de6d5d5144c"
V003_TOOLING_RELPATH = "backtests/phase8_v2_variant_v003_eval.py"
V003_TOOLING_FINGERPRINT = (
    "40df72bd13902199504fb89cbd5d64184b923cffce1f211d041cffacc743c9b9"
)
ENTRY_MODEL_MODULE = "strategies/smc_engine/entry_model.py"
STRATEGY_STATE_MODULE = "strategies/smc_engine/strategy_state.py"

V003_SEALED_RESULT_PATH = (
    "C:/Users/chips/forex-signal-bot-data/phase8/v2_variants/"
    "phase6-development-v2-V003/fold01/phase6-development-v2-V003_result.json"
)
V003_SEALED_RESULT_SHA256 = (
    "50117c399481a2e31b8da6260da4e05c8719a522efb524f80bb2063319c41ff8"
)
V003_SEALED_RESULT_BYTES = 45221
V003_TIER_A_TARGET = 90

FOLD01_START_MS = int(datetime.fromisoformat(FOLD01_START).timestamp() * 1000)
FOLD01_END_MS = int(datetime.fromisoformat(FOLD01_END).timestamp() * 1000)

CATEGORY_E1_STATE_EXPIRED = "STATE_EXPIRED"
CATEGORY_E2_READINESS_INCOMPLETE = "READINESS_INCOMPLETE"
CATEGORY_E3_STRUCTURE_DIRECTION_UNRESOLVED = "STRUCTURE_DIRECTION_UNRESOLVED"
CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH = "LIQUIDITY_ALIGNMENT_MISMATCH"
CATEGORY_E5_UNMAPPED_ENTRY_REJECTION = "UNMAPPED_ENTRY_REJECTION"

REJECTION_CATEGORIES = (
    CATEGORY_E1_STATE_EXPIRED,
    CATEGORY_E2_READINESS_INCOMPLETE,
    CATEGORY_E3_STRUCTURE_DIRECTION_UNRESOLVED,
    CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH,
    CATEGORY_E5_UNMAPPED_ENTRY_REJECTION,
)

ALLOWED_MISSING_CONDITIONS = (
    "Confirmed structure",
    "Liquidity sweep",
    "Displacement / FVG",
    "Daily limit clear",
    "News clear",
)

D006_BANNED_METRIC_KEYS = frozenset(
    {
        "pnl",
        "profit",
        "profit_factor",
        "win_rate",
        "expectancy",
        "drawdown",
        "sharpe",
        "returns",
        "return",
        "closed_trades",
        "trades",
        "fills",
        "fill_count",
        "balance",
        "equity",
    }
)

D006_BANNED_METRIC_SUBSTRINGS = (
    "candidate_if",
    "rescued_candidates",
    "would_pass",
    "if_removed",
    "alternate_expiry",
    "alternate_state",
    "alternate_score",
    "score_10_candidate",
    "relaxed_liquidity",
    "pnl",
    "profit",
    "win_rate",
    "expectancy",
    "drawdown",
    "sharpe",
    "returns",
    "closed_trades",
)


def _reject_banned_metrics(node: Any, path: str = "document") -> None:
    """Recursively reject banned profitability and counterfactual keys."""
    if path == "document.invariance_assertions":
        return
    if isinstance(node, Mapping):
        for key, value in node.items():
            key_text = str(key).lower()
            if key_text in D006_BANNED_METRIC_KEYS or any(
                banned in key_text for banned in D006_BANNED_METRIC_SUBSTRINGS
            ):
                raise D006Error(f"prohibited metric key {path}.{key}")
            _reject_banned_metrics(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_banned_metrics(value, f"{path}[{index}]")

_PROVENANCE = {
    "research_identity": "phase6-development-v2",
    "diagnostic_id": D006_ID,
    "linked_hypothesis_id": H008_ID,
    "specification_document": SPECIFICATION_DOCUMENT,
    "specification_sha256": SPEC_SHA256,
    "specification_phase_a_sha256": SPEC_PHASE_A_SHA256,
    "tooling": TOOLING_RELPATH,
    "fingerprint_contract": FINGERPRINT_CONTRACT,
    "v003_strategy_module": V003_STRATEGY_MODULE,
    "v003_strategy_git_blob_sha": V003_STRATEGY_GIT_BLOB_SHA,
    "v003_tooling_relpath": V003_TOOLING_RELPATH,
    "v003_tooling_fingerprint": V003_TOOLING_FINGERPRINT,
    "entry_model_module": ENTRY_MODEL_MODULE,
    "strategy_state_module": STRATEGY_STATE_MODULE,
}


class D006Error(RuntimeError):
    """Base exception for D006 diagnostic contract violations."""


class D006BaselineReproductionError(D006Error):
    """Raised when reproduced V003 surfaces mismatch the sealed V003 R001 prior result."""


class D006UnmappedRejectionError(D006Error):
    """Raised when an entry rejection does not map to any preregistered E1-E4 category."""


class D006AccountingError(D006Error):
    """Raised when decision accounting or stage population partitioning violates invariants."""


class D006StateMutationError(D006Error):
    """Raised when a diagnostic observer mutates authoritative strategy state."""


def _canonical_blob_source():
    """Production committed-byte source: real Git plumbing on this repo."""
    from bot.scientific.canonical_bytes import make_git_blob_source  # noqa: PLC0415

    return make_git_blob_source(REPO_ROOT)


def provenance(
    *,
    tooling_commit: str,
    store_identity: Mapping[str, Any],
    generated_at: str | None = None,
    blob_source=None,
) -> dict[str, Any]:
    """Provenance bound to the D006 tooling commit and frozen inputs."""
    from bot.scientific.canonical_bytes import canonical_file_digest  # noqa: PLC0415

    if not tooling_commit or len(tooling_commit) != 40:
        raise D006Error(f"valid 40-character tooling commit required, got {tooling_commit!r}")

    source = blob_source if blob_source is not None else _canonical_blob_source()
    try:
        tooling_fingerprint = canonical_file_digest(
            TOOLING_RELPATH,
            commit=tooling_commit,
            repo=REPO_ROOT,
            blob_source=source,
        )
    except Exception as error:
        raise D006Error(f"D006 tooling fingerprint unresolvable: {error}") from error

    store_blob = json.dumps(
        dict(store_identity), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return {
        **_PROVENANCE,
        "tooling_commit": tooling_commit,
        "tooling_fingerprint": tooling_fingerprint,
        "fold_store_identity_sha256": hashlib.sha256(store_blob.encode("utf-8")).hexdigest(),
        "generated_at_utc": generated_at or _iso(datetime.now(timezone.utc)),
    }


def is_valid_liquidity_alignment(
    structure_dir: str | None,
    liquidity_side: str | None,
    liquidity_type: str | None,
) -> bool:
    """Exact frozen liquidity-alignment combinations from determine_entry.

    Bullish valid:
      - liquidity_side == 'sell' AND liquidity_type == 'equal_lows'
      - liquidity_side == 'buy' AND liquidity_type == 'internal_continuation'
    Bearish valid:
      - liquidity_side == 'buy' AND liquidity_type == 'equal_highs'
      - liquidity_side == 'sell' AND liquidity_type == 'internal_continuation'
    """
    if structure_dir == "bullish":
        if liquidity_side == "sell" and liquidity_type == "equal_lows":
            return True
        if liquidity_side == "buy" and liquidity_type == "internal_continuation":
            return True
        return False
    elif structure_dir == "bearish":
        if liquidity_side == "buy" and liquidity_type == "equal_highs":
            return True
        if liquidity_side == "sell" and liquidity_type == "internal_continuation":
            return True
        return False
    return False


def classify_entry_rejection(
    *,
    state: StrategyState,
    score_result: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None,
    current_price: float = 0.0,
) -> tuple[str | None, dict[str, Any]]:
    """Deterministic read-only ordered classification of Gate 12/13 entry state.

    Evaluates on a private diagnostic deepcopy; the input state is NEVER mutated.
    Returns (category, decomposition_dict). If determine_entry returns a valid entry,
    category is None.

    Ordered evaluation:
      E1 — STATE_EXPIRED: state.is_expired() == True
      E2 — READINESS_INCOMPLETE: ready_for_entry() == False and early_entry_ok == False
      E3 — STRUCTURE_DIRECTION_UNRESOLVED: structure_dir not in {'bullish', 'bearish'}
      E4 — LIQUIDITY_ALIGNMENT_MISMATCH: neither valid liquidity combination holds
      E5 — UNMAPPED_ENTRY_REJECTION: determine_entry returned None, but E1-E4 unmapped
    """
    ctx = dict(context or {})
    score_dict = dict(score_result or {})
    score_value = int(score_dict.get("score", 0) or 0)

    diag_state = copy.deepcopy(state)

    state_last_update = (
        diag_state.last_update.isoformat()
        if hasattr(diag_state.last_update, "isoformat")
        else str(diag_state.last_update)
    )
    now_dt = diag_state._now()
    age_delta = now_dt - diag_state.last_update
    state_age_minutes = round(age_delta.total_seconds() / 60.0, 4)

    is_expired = bool(diag_state.is_expired())

    state_ready = bool(diag_state.ready_for_entry())
    missing_conditions = list(diag_state.missing_conditions)
    for cond in missing_conditions:
        if cond not in ALLOWED_MISSING_CONDITIONS:
            raise D006Error(
                f"Unknown missing condition {cond!r} encountered; allowed: {ALLOWED_MISSING_CONDITIONS}"
            )

    structure_state = diag_state.structure_state
    structure_state_confirmed = bool(structure_state == "confirmed")
    liquidity_swept = bool(diag_state.liquidity_swept)
    displacement_seen = bool(diag_state.displacement_seen)
    daily_limits_hit = bool(diag_state.daily_limits_hit)
    daily_limit_clear = not daily_limits_hit
    news_clear = bool(
        diag_state.news_status.get("news_clear", True)
        if diag_state.news_status is not None
        else True
    )

    missing_set = set(missing_conditions)
    missing_set_eligible_early = missing_set.issubset({"Confirmed structure"})
    structure_state_early_eligible = (
        structure_state in ("transition", "range") or structure_state is None
    )
    score_eligible_early = score_value >= 8
    internal_event = ctx.get("internal_structure_event")
    has_internal_confirmation = internal_event in ("BOS", "CHOCH") or bool(
        ctx.get("sweep_rejected")
    )
    has_zone_context = bool(ctx.get("ob_zone")) or bool(ctx.get("fvg_zone"))
    has_priority_context = bool(ctx.get("asian_liquidity_swept")) or bool(
        ctx.get("asian_sweep_setup")
    )

    early_entry_ok = bool(
        _can_use_early_entry(diag_state, score_value=score_value, context=ctx)
    )

    structure_dir = diag_state.structure_dir
    liquidity_side = diag_state.liquidity_side
    liquidity_type = diag_state.liquidity_type
    liquidity_alignment_valid = is_valid_liquidity_alignment(
        structure_dir, liquidity_side, liquidity_type
    )
    contingency_cell = f"{structure_dir} x {liquidity_side} x {liquidity_type}"

    category: str | None = None
    if is_expired:
        category = CATEGORY_E1_STATE_EXPIRED
    elif (not state_ready) and (not early_entry_ok):
        category = CATEGORY_E2_READINESS_INCOMPLETE
    elif structure_dir not in ("bullish", "bearish"):
        category = CATEGORY_E3_STRUCTURE_DIRECTION_UNRESOLVED
    elif not liquidity_alignment_valid:
        category = CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH
    else:
        det_copy = copy.deepcopy(state)
        entry_result = determine_entry(
            "XAUUSDm",
            det_copy,
            current_price=current_price,
            score_result=score_dict,
            context=ctx,
            emit_log=None,
        )
        if entry_result is None:
            category = CATEGORY_E5_UNMAPPED_ENTRY_REJECTION
        else:
            category = None

    details: dict[str, Any] = {
        "category": category,
        "is_expired": is_expired,
        "state_age_minutes": state_age_minutes,
        "state_last_update": state_last_update,
        "ready_for_entry": state_ready,
        "missing_conditions": missing_conditions,
        "structure_state": structure_state,
        "structure_state_confirmed": structure_state_confirmed,
        "liquidity_swept": liquidity_swept,
        "displacement_seen": displacement_seen,
        "daily_limits_hit": daily_limits_hit,
        "daily_limit_clear": daily_limit_clear,
        "news_clear": news_clear,
        "early_entry_ok": early_entry_ok,
        "early_entry_subpredicates": {
            "missing_set_eligible_early": missing_set_eligible_early,
            "structure_state_early_eligible": structure_state_early_eligible,
            "score_eligible_early": score_eligible_early,
            "has_internal_confirmation": has_internal_confirmation,
            "internal_structure_event": internal_event,
            "has_zone_context": has_zone_context,
            "has_priority_context": has_priority_context,
            "displacement_relaxation_at_score_10_unreachable_for_v003": True,
        },
        "structure_dir": structure_dir,
        "liquidity_side": liquidity_side,
        "liquidity_type": liquidity_type,
        "liquidity_alignment_valid": liquidity_alignment_valid,
        "liquidity_contingency_cell": contingency_cell,
    }
    return category, details


def decompose_v003_decision(
    *,
    row: Mapping[str, Any],
    snapshot: Any,
    decision_result_record: Any,
    decision_at: datetime,
    frame: Any,
    pair: Any,
    score: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Decompose frozen Gate 12/13 entry state for one V003 Gate-11 entrant."""
    decision_id = row.get("decision_id")
    current_price = float(frame["close"].iloc[-1])
    internal = payload.get("internal_structure") or {}
    session_context = payload.get("session_context") or {}
    liquidity_context = payload.get("liquidity_context") or {}

    ob_zone = None
    if pair.structurally_active and pair.zone_low is not None:
        ob_zone = (float(pair.zone_low), float(pair.zone_high))

    fvg_zone = None
    if pair.live_fvg_bottom is not None and pair.live_fvg_top is not None:
        fvg_zone = (float(pair.live_fvg_bottom), float(pair.live_fvg_top))

    context = {
        "ob_zone": ob_zone,
        "fvg_zone": fvg_zone,
        "after_london_open": session_context.get("active_session") == "london",
        "asian_liquidity_swept": any(
            pool.get("type") in ("asian_high", "asian_low")
            for pool in liquidity_context.get("liquidity_pools", [])
        ),
        "sweep_rejected": bool(internal.get("event") in ("CHOCH", "BOS")),
        "internal_structure_event": internal.get("event"),
        "htf_zone_alignment": bool(pair.structurally_active),
    }

    state = _v002_private_entry_state(
        decision_result_record,
        decision_at=decision_at,
        payload=payload,
    )

    state_before_dict = {
        "missing_conditions": list(state.missing_conditions),
        "state_name": state.state_name,
        "structure_dir": state.structure_dir,
        "liquidity_swept": state.liquidity_swept,
        "displacement_seen": state.displacement_seen,
    }

    category, details = classify_entry_rejection(
        state=state,
        score_result=score,
        context=context,
        current_price=current_price,
    )

    state_after_dict = {
        "missing_conditions": list(state.missing_conditions),
        "state_name": state.state_name,
        "structure_dir": state.structure_dir,
        "liquidity_swept": state.liquidity_swept,
        "displacement_seen": state.displacement_seen,
    }
    if state_before_dict != state_after_dict:
        raise D006StateMutationError(
            f"classify_entry_rejection mutated authoritative state at decision {decision_id!r}"
        )

    return {
        "decision_id": decision_id,
        "available_at_ms": int(snapshot.available_at_ms),
        "fvg_evidence_source": pair.fvg_evidence_source,
        "v003_gate11_passed": bool(score.get("passes_threshold")),
        "decomposition": details,
    }


def classify_strategy_reasons(reasons: Iterable[str]) -> list[dict[str, str]]:
    """Label strategy rejection reasons with frozen protected policy classes."""
    labeled: list[dict[str, str]] = []
    for reason in reasons:
        r_str = str(reason)
        r_lower = r_str.lower()
        if "regime" in r_lower:
            cls = "regime"
        elif "bias" in r_lower:
            cls = "bias"
        elif "dxy" in r_lower:
            cls = "dxy"
        elif "news" in r_lower:
            cls = "news"
        elif "session" in r_lower:
            cls = "session"
        elif "allowlist" in r_lower or "symbol" in r_lower:
            cls = "symbol_allowlist"
        elif "consumed" in r_lower or "lifecycle" in r_lower:
            cls = "consumed_lifecycle"
        else:
            cls = "other_protected_policy"
        labeled.append({"reason": r_str, "protected_class": cls})
    return labeled


def reconcile_v003_prior_result(
    prior_result_path: Path | str | None,
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate runtime V003 baseline reproduction against sealed V003 R001.

    Loads the sealed external result, validates its SHA-256 and byte size.
    Per TC001/TC002, upstream stages (entrants, gate-11 passers, canonical-strategy passers)
    reconcile by exact count against the prior funnel; candidate stage reconciles by
    exact count, exact decision ID set, and strict setup IDs. Reproduces and seals upstream
    and primary decision ID digests under contract FIRST_IDENTITY_SEALED_BY_D006.
    """
    obs_entrants = [obs["decision_id"] for obs in observations]
    obs_gate11_pass = [
        obs["decision_id"] for obs in observations if obs.get("v003_gate11_passed")
    ]
    obs_strat_pass = [
        obs["decision_id"] for obs in observations if obs.get("v003_strategy_eligible")
    ]
    obs_ready = [
        obs["decision_id"] for obs in observations if obs.get("v003_entry_ready")
    ]
    obs_primary = [
        obs["decision_id"]
        for obs in observations
        if obs.get("v003_gate11_passed")
        and obs.get("v003_strategy_eligible")
        and not obs.get("v003_entry_ready")
    ]

    # Check for null decision_ids in observations before hashing
    for obs in observations:
        if obs.get("v003_entry_ready"):
            if not obs.get("decision_id") or not obs.get("v003_setup_id"):
                raise D006BaselineReproductionError(
                    "Observed ready candidate missing non-null decision_id or v003_setup_id"
                )
        if obs.get("decision_id") is None:
            raise D006BaselineReproductionError(
                "Observation missing non-null decision_id"
            )

    reproduced_gate11_entrant_ids_digest = hashlib.sha256(
        "\n".join(sorted(obs_entrants)).encode("utf-8")
    ).hexdigest()
    reproduced_gate11_pass_ids_digest = hashlib.sha256(
        "\n".join(sorted(obs_gate11_pass)).encode("utf-8")
    ).hexdigest()
    reproduced_canonical_strategy_pass_ids_digest = hashlib.sha256(
        "\n".join(sorted(obs_strat_pass)).encode("utf-8")
    ).hexdigest()
    candidate_ready_ids_digest = hashlib.sha256(
        "\n".join(sorted(obs_ready)).encode("utf-8")
    ).hexdigest()
    p_entry_reject_ids_digest = hashlib.sha256(
        "\n".join(sorted(obs_primary)).encode("utf-8")
    ).hexdigest()

    if prior_result_path is None:
        return {
            "status": "SKIPPED_SYNTHETIC",
            "reconciles": True,
            "note": "no prior result path provided; synthetic or offline mode",
            "upstream_decision_id_digests": {
                "identity_sealing_note": "FIRST_IDENTITY_SEALED_BY_D006",
                "gate11_entrants_sha256": reproduced_gate11_entrant_ids_digest,
                "gate11_passers_sha256": reproduced_gate11_pass_ids_digest,
                "canonical_strategy_passers_sha256": reproduced_canonical_strategy_pass_ids_digest,
                "candidate_ready_sha256": candidate_ready_ids_digest,
                "p_entry_reject_sha256": p_entry_reject_ids_digest,
            },
        }

    p = Path(prior_result_path)
    if not p.exists():
        raise D006BaselineReproductionError(
            f"sealed V003 prior result not found at {p.as_posix()}"
        )

    data_bytes = p.read_bytes()
    if len(data_bytes) != V003_SEALED_RESULT_BYTES:
        raise D006BaselineReproductionError(
            f"sealed V003 bytes mismatch: {len(data_bytes)} != {V003_SEALED_RESULT_BYTES}"
        )
    digest = hashlib.sha256(data_bytes).hexdigest()
    if digest != V003_SEALED_RESULT_SHA256:
        raise D006BaselineReproductionError(
            f"sealed V003 SHA-256 mismatch: {digest} != {V003_SEALED_RESULT_SHA256}"
        )

    prior = json.loads(data_bytes.decode("utf-8"))

    prior_funnel = prior.get("V003_variant_funnel", {})
    prior_candidate = prior.get("candidate_surface", {})

    prior_gate11_entered = int(prior_funnel.get("gate_11_v003", {}).get("entered", -1))
    prior_gate11_passed = int(prior_funnel.get("gate_11_v003", {}).get("passed", -1))
    prior_strat_passed = int(
        prior_funnel.get("canonical_strategy_v003", {}).get("passed", -1)
    )
    prior_ready_count = int(prior_candidate.get("candidate_ready", -1))

    if len(obs_entrants) != prior_gate11_entered:
        raise D006BaselineReproductionError(
            f"Gate-11 entrant count mismatch: {len(obs_entrants)} != {prior_gate11_entered}"
        )
    if len(obs_gate11_pass) != prior_gate11_passed:
        raise D006BaselineReproductionError(
            f"Gate-11 pass count mismatch: {len(obs_gate11_pass)} != {prior_gate11_passed}"
        )
    if len(obs_strat_pass) != prior_strat_passed:
        raise D006BaselineReproductionError(
            f"Canonical-strategy pass count mismatch: {len(obs_strat_pass)} != {prior_strat_passed}"
        )
    if len(obs_ready) != prior_ready_count:
        raise D006BaselineReproductionError(
            f"Candidate-ready count mismatch: {len(obs_ready)} != {prior_ready_count}"
        )

    prior_candidates_list = prior_candidate.get("candidates", [])
    if len(prior_candidates_list) != prior_ready_count:
        raise D006BaselineReproductionError(
            f"Prior candidate list count mismatch: {len(prior_candidates_list)} != {prior_ready_count}"
        )

    # Section 17: Strict prior candidate validation
    prior_pairs: list[tuple[str, str]] = []
    prior_cand_did_set = set()
    for c in prior_candidates_list:
        c_did = c.get("decision_id")
        c_sid = c.get("setup_id")
        if not c_did or not c_sid:
            raise D006BaselineReproductionError(
                "Prior candidate record missing non-null decision_id or setup_id"
            )
        if c_did in prior_cand_did_set:
            raise D006BaselineReproductionError(
                f"Duplicate decision_id in prior candidates: {c_did}"
            )
        prior_cand_did_set.add(c_did)
        prior_pairs.append((str(c_did), str(c_sid)))

    # Section 18: Strict observed candidate validation
    obs_pairs: list[tuple[str, str]] = []
    obs_cand_did_set = set()
    for obs in observations:
        if obs.get("v003_entry_ready"):
            o_did = obs.get("decision_id")
            o_sid = obs.get("v003_setup_id")
            if not o_did or not o_sid:
                raise D006BaselineReproductionError(
                    "Observed ready candidate missing non-null decision_id or v003_setup_id"
                )
            if o_did in obs_cand_did_set:
                raise D006BaselineReproductionError(
                    f"Duplicate decision_id in observed candidates: {o_did}"
                )
            obs_cand_did_set.add(o_did)
            obs_pairs.append((str(o_did), str(o_sid)))

    # Independent check 1: Exact candidate decision-ID set equality
    prior_candidate_ids = [c[0] for c in prior_pairs]
    if sorted(obs_ready) != sorted(prior_candidate_ids):
        raise D006BaselineReproductionError(
            "Candidate decision ID set does not reproduce prior V003 result exactly"
        )

    # Independent check 2: Per-decision setup_id check
    prior_setup_id_by_decision = {c[0]: c[1] for c in prior_pairs}
    for did, sid in obs_pairs:
        expected_sid = prior_setup_id_by_decision.get(did)
        if expected_sid is not None and sid != expected_sid:
            raise D006BaselineReproductionError(
                f"Candidate setup_id mismatch for decision {did}: {sid} != {expected_sid}"
            )

    # Section 19: Exact candidate pair multiset reconciliation
    if sorted(obs_pairs) != sorted(prior_pairs):
        raise D006BaselineReproductionError(
            "Exact (decision_id, setup_id) pair multiset does not match prior V003 result"
        )

    # 2. Exact candidate-ready count
    if len(obs_pairs) != prior_ready_count:
        raise D006BaselineReproductionError(
            f"Observed candidate pair count mismatch: {len(obs_pairs)} != {prior_ready_count}"
        )

    # 3. Exact unique setup-ID count
    prior_unique_setup_ids = prior_candidate.get("unique_candidate_setup_ids")
    obs_sids = [p[1] for p in obs_pairs]
    unique_obs_sids = len(set(obs_sids))
    if prior_unique_setup_ids is not None and unique_obs_sids != prior_unique_setup_ids:
        raise D006BaselineReproductionError(
            f"Unique setup ID count mismatch: {unique_obs_sids} != {prior_unique_setup_ids}"
        )

    # 4. Exact duplicate setup-ID occurrence count
    prior_dup_setup_ids = prior_candidate.get(
        "duplicate_candidate_setup_id_occurrences"
    )
    dup_obs_sids = len(obs_sids) - unique_obs_sids
    if prior_dup_setup_ids is not None and dup_obs_sids != prior_dup_setup_ids:
        raise D006BaselineReproductionError(
            f"Duplicate setup ID occurrences mismatch: {dup_obs_sids} != {prior_dup_setup_ids}"
        )

    return {
        "status": "SEALED_V003_BASELINE_RECONCILED",
        "reconciles": True,
        "prior_result_path": str(p.as_posix()),
        "prior_result_sha256": digest,
        "prior_result_bytes": len(data_bytes),
        "gate11_entrants": len(obs_entrants),
        "gate11_entrants_count": len(obs_entrants),
        "gate11_passers": len(obs_gate11_pass),
        "gate11_passers_count": len(obs_gate11_pass),
        "canonical_strategy_passers": len(obs_strat_pass),
        "canonical_strategy_passers_count": len(obs_strat_pass),
        "candidate_ready": len(obs_ready),
        "candidate_ready_count": len(obs_ready),
        "upstream_reconciliation_contract": "EXACT_COUNT_RECONCILED_FIRST_IDENTITY_SEALED_BY_D006",
        "candidate_reconciliation_contract": "EXACT_DECISION_ID_AND_SETUP_ID_SET_EQUALITY",
        "upstream_decision_id_digests": {
            "identity_sealing_note": "FIRST_IDENTITY_SEALED_BY_D006",
            "gate11_entrants_sha256": reproduced_gate11_entrant_ids_digest,
            "gate11_passers_sha256": reproduced_gate11_pass_ids_digest,
            "canonical_strategy_passers_sha256": reproduced_canonical_strategy_pass_ids_digest,
            "candidate_ready_sha256": candidate_ready_ids_digest,
            "p_entry_reject_sha256": p_entry_reject_ids_digest,
        },
        "candidate_setup_id_reconciliation": {
            "unique_setup_ids": unique_obs_sids,
            "duplicate_setup_ids": dup_obs_sids,
            "matches_prior_v003": True,
        },
    }


def aggregate_d006(
    observations: list[dict[str, Any]],
    decompositions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate D006 populations, source stratifications, and contingency tables."""
    decomp_by_id = {d["decision_id"]: d["decomposition"] for d in decompositions}

    r_gate11_fail_ids: list[str] = []
    r_strategy_reject_ids: list[str] = []
    r_ready_ids: list[str] = []
    p_entry_reject_ids: list[str] = []

    strategy_rejection_reasons: dict[str, int] = {}
    strategy_protected_classes: dict[str, int] = {}

    source_counts = {
        "P_ENTRY_REJECT": {"FINAL_SURFACE": 0, "TEMPORAL_MEMORY": 0, "NONE": 0},
        "R_READY": {"FINAL_SURFACE": 0, "TEMPORAL_MEMORY": 0, "NONE": 0},
        "R_STRATEGY_REJECT": {"FINAL_SURFACE": 0, "TEMPORAL_MEMORY": 0, "NONE": 0},
        "R_GATE11_FAIL": {"FINAL_SURFACE": 0, "TEMPORAL_MEMORY": 0, "NONE": 0},
    }

    for obs in observations:
        did = obs["decision_id"]
        source = obs.get("v003_fvg_evidence_source", "NONE")
        g11 = bool(obs.get("v003_gate11_passed"))
        strat = bool(obs.get("v003_strategy_eligible"))
        ready = bool(obs.get("v003_entry_ready"))

        if not g11:
            r_gate11_fail_ids.append(did)
            source_counts["R_GATE11_FAIL"][source] = (
                source_counts["R_GATE11_FAIL"].get(source, 0) + 1
            )
        elif not strat:
            r_strategy_reject_ids.append(did)
            source_counts["R_STRATEGY_REJECT"][source] = (
                source_counts["R_STRATEGY_REJECT"].get(source, 0) + 1
            )
            for item in classify_strategy_reasons(obs.get("v003_strategy_reasons") or []):
                strategy_rejection_reasons[item["reason"]] = (
                    strategy_rejection_reasons.get(item["reason"], 0) + 1
                )
                strategy_protected_classes[item["protected_class"]] = (
                    strategy_protected_classes.get(item["protected_class"], 0) + 1
                )
        elif ready:
            r_ready_ids.append(did)
            source_counts["R_READY"][source] = source_counts["R_READY"].get(source, 0) + 1
        else:
            p_entry_reject_ids.append(did)
            source_counts["P_ENTRY_REJECT"][source] = (
                source_counts["P_ENTRY_REJECT"].get(source, 0) + 1
            )

    total_entrants = len(observations)
    partition_sum = (
        len(r_gate11_fail_ids)
        + len(r_strategy_reject_ids)
        + len(r_ready_ids)
        + len(p_entry_reject_ids)
    )
    if partition_sum != total_entrants:
        raise D006AccountingError(
            f"Stage partition sum mismatch: {partition_sum} != {total_entrants}"
        )

    all_ids_sets = [
        set(r_gate11_fail_ids),
        set(r_strategy_reject_ids),
        set(r_ready_ids),
        set(p_entry_reject_ids),
    ]
    total_unique = len(set().union(*all_ids_sets))
    if total_unique != total_entrants:
        raise D006AccountingError(
            f"Stage partitions overlap; unique {total_unique} != total {total_entrants}"
        )

    strat_pass_ids = {
        obs["decision_id"] for obs in observations if obs.get("v003_strategy_eligible")
    }
    candidate_ids = {obs["decision_id"] for obs in observations if obs.get("v003_entry_ready")}
    expected_primary = strat_pass_ids - candidate_ids
    if set(p_entry_reject_ids) != expected_primary:
        raise D006AccountingError(
            "Primary population decision IDs do not equal (canonical_strategy_pass - candidate_ready) exactly"
        )

    category_counts: dict[str, int] = {cat: 0 for cat in REJECTION_CATEGORIES}
    category_by_source: dict[str, dict[str, int]] = {
        cat: {"FINAL_SURFACE": 0, "TEMPORAL_MEMORY": 0, "NONE": 0} for cat in REJECTION_CATEGORIES
    }

    state_expiry_counts = {"expired": 0, "active": 0}
    state_ages: list[float] = []

    ready_for_entry_counts = {"ready": 0, "not_ready": 0}
    missing_condition_dist: dict[str, int] = {cond: 0 for cond in ALLOWED_MISSING_CONDITIONS}
    missing_condition_cooccurrences: dict[str, int] = {}

    early_entry_decomp_counts = {
        "missing_set_eligible_early": 0,
        "structure_state_early_eligible": 0,
        "score_eligible_early": 0,
        "has_internal_confirmation": 0,
        "has_zone_context": 0,
        "has_priority_context": 0,
        "early_entry_ok": 0,
    }

    structure_state_dist: dict[str, int] = {}
    structure_dir_dist: dict[str, int] = {}
    liquidity_side_dist: dict[str, int] = {}
    liquidity_type_dist: dict[str, int] = {}
    contingency_table: dict[str, int] = {}
    liquidity_alignment_valid_counts = {"valid": 0, "invalid": 0}

    primary_decomps_list: list[dict[str, Any]] = []

    for d in decompositions:
        did = d["decision_id"]
        source = d.get("fvg_evidence_source", "NONE")
        decomp = d["decomposition"]
        primary_decomps_list.append(
            {
                "decision_id": did,
                "fvg_evidence_source": source,
                "decomposition": decomp,
            }
        )

        cat = decomp["category"]
        if cat in category_counts:
            category_counts[cat] += 1
            category_by_source[cat][source] = category_by_source[cat].get(source, 0) + 1
        else:
            raise D006Error(f"Unknown rejection category {cat!r}")

        if decomp["is_expired"]:
            state_expiry_counts["expired"] += 1
        else:
            state_expiry_counts["active"] += 1
        state_ages.append(float(decomp["state_age_minutes"]))

        if decomp["ready_for_entry"]:
            ready_for_entry_counts["ready"] += 1
        else:
            ready_for_entry_counts["not_ready"] += 1

        missing = sorted(decomp["missing_conditions"])
        for m in missing:
            missing_condition_dist[m] = missing_condition_dist.get(m, 0) + 1
        combo_key = " + ".join(missing) if missing else "None"
        missing_condition_cooccurrences[combo_key] = (
            missing_condition_cooccurrences.get(combo_key, 0) + 1
        )

        early_sub = decomp["early_entry_subpredicates"]
        if early_sub["missing_set_eligible_early"]:
            early_entry_decomp_counts["missing_set_eligible_early"] += 1
        if early_sub["structure_state_early_eligible"]:
            early_entry_decomp_counts["structure_state_early_eligible"] += 1
        if early_sub["score_eligible_early"]:
            early_entry_decomp_counts["score_eligible_early"] += 1
        if early_sub["has_internal_confirmation"]:
            early_entry_decomp_counts["has_internal_confirmation"] += 1
        if early_sub["has_zone_context"]:
            early_entry_decomp_counts["has_zone_context"] += 1
        if early_sub["has_priority_context"]:
            early_entry_decomp_counts["has_priority_context"] += 1
        if decomp["early_entry_ok"]:
            early_entry_decomp_counts["early_entry_ok"] += 1

        st_state = str(decomp["structure_state"])
        structure_state_dist[st_state] = structure_state_dist.get(st_state, 0) + 1

        st_dir = str(decomp["structure_dir"])
        structure_dir_dist[st_dir] = structure_dir_dist.get(st_dir, 0) + 1

        l_side = str(decomp["liquidity_side"])
        liquidity_side_dist[l_side] = liquidity_side_dist.get(l_side, 0) + 1

        l_type = str(decomp["liquidity_type"])
        liquidity_type_dist[l_type] = liquidity_type_dist.get(l_type, 0) + 1

        cell = decomp["liquidity_contingency_cell"]
        contingency_table[cell] = contingency_table.get(cell, 0) + 1

        if decomp["liquidity_alignment_valid"]:
            liquidity_alignment_valid_counts["valid"] += 1
        else:
            liquidity_alignment_valid_counts["invalid"] += 1

    primary_count = len(p_entry_reject_ids)
    sorted_cats = sorted(
        category_counts.items(), key=lambda item: (-item[1], item[0])
    )
    dominant_cat, dominant_count = sorted_cats[0] if sorted_cats else (None, 0)
    dominant_share = (
        round(dominant_count / primary_count, 4) if primary_count > 0 else 0.0
    )
    top_two = sorted_cats[:2]
    top_two_categories = [c[0] for c in top_two if c[1] > 0]
    top_two_count = sum(c[1] for c in top_two)
    top_two_share = (
        round(top_two_count / primary_count, 4) if primary_count > 0 else 0.0
    )

    if category_counts[CATEGORY_E5_UNMAPPED_ENTRY_REJECTION] > 0:
        proposed_h008 = "INCONCLUSIVE_D006"
        h008_rationale = (
            f"Unmapped entry rejections observed ({category_counts[CATEGORY_E5_UNMAPPED_ENTRY_REJECTION]}); "
            "interpretation fails closed per specification section 16 and section 24."
        )
    elif primary_count == 0:
        proposed_h008 = "INCONCLUSIVE_D006"
        h008_rationale = "Zero primary-population entry rejections observed."
    else:
        proposed_h008 = "H008_SUPERVISORY_INTERPRETATION_REQUIRED"
        h008_rationale = (
            f"All {primary_count} primary entry rejections map to frozen categories (E5 = 0). "
            f"Dominant category '{dominant_cat}' accounts for {dominant_count}/{primary_count} ({dominant_share:.1%}); "
            f"top-two categories account for {top_two_count}/{primary_count} ({top_two_share:.1%}). "
            "Per preregistration and TC001, scientific evaluation requires supervisory interpretation "
            "of structural concentration vs diffuse absence without an arbitrary numerical percentage threshold."
        )

    return {
        "entry_stage_populations": {
            "total_gate11_entrants": total_entrants,
            "R_GATE11_FAIL_count": len(r_gate11_fail_ids),
            "R_STRATEGY_REJECT_count": len(r_strategy_reject_ids),
            "R_READY_count": len(r_ready_ids),
            "P_ENTRY_REJECT_count": len(p_entry_reject_ids),
            "partition_reconciles": True,
            "stage_definitions": {
                "R_GATE11_FAIL": "Gate-11 entrants failing V003 8/8 score",
                "R_STRATEGY_REJECT": "Gate-11 passers failing unchanged canonical strategy protections",
                "R_READY": "Canonical-strategy passers with determine_entry returning valid entry",
                "P_ENTRY_REJECT": "Canonical-strategy passers with determine_entry returning None",
            },
        },
        "primary_population": {
            "count": primary_count,
            "decision_ids": sorted(p_entry_reject_ids),
            "p_entry_reject_sha256": hashlib.sha256(
                "\n".join(sorted(p_entry_reject_ids)).encode("utf-8")
            ).hexdigest(),
            "id_reconciliation": {
                "equals_canonical_strategy_pass_minus_candidate_ready": True,
                "unique_count": len(set(p_entry_reject_ids)),
                "duplicate_count": 0,
            },
        },
        "fvg_source_stratification": source_counts,
        "entry_rejection_category_distribution": category_counts,
        "entry_rejection_by_source": category_by_source,
        "state_expiry_surface": {
            "counts": state_expiry_counts,
            "age_minutes_summary": _age_summary(state_ages),
            "frozen_expiry_minutes": STATE_EXPIRY_MINUTES,
        },
        "ready_for_entry_surface": {
            "counts": ready_for_entry_counts,
            "missing_condition_distribution": missing_condition_dist,
            "missing_condition_cooccurrences": dict(
                sorted(missing_condition_cooccurrences.items(), key=lambda x: -x[1])
            ),
        },
        "early_entry_surface": {
            "score_context": 8,
            "entry_mode": "conservative",
            "early_entry_predicate_counts": early_entry_decomp_counts,
            "displacement_relaxation_unreachable": True,
        },
        "structure_and_liquidity_surface": {
            "structure_state_distribution": dict(sorted(structure_state_dist.items())),
            "structure_direction_distribution": dict(sorted(structure_dir_dist.items())),
            "liquidity_side_distribution": dict(sorted(liquidity_side_dist.items())),
            "liquidity_type_distribution": dict(sorted(liquidity_type_dist.items())),
            "contingency_table": dict(
                sorted(contingency_table.items(), key=lambda x: -x[1])
            ),
            "liquidity_alignment_counts": liquidity_alignment_valid_counts,
        },
        "strategy_rejection_context": {
            "count": len(r_strategy_reject_ids),
            "reason_distribution": dict(
                sorted(strategy_rejection_reasons.items(), key=lambda x: -x[1])
            ),
            "protected_class_distribution": dict(
                sorted(strategy_protected_classes.items(), key=lambda x: -x[1])
            ),
            "usage_note": "PROTECTED-POLICY CONTEXT ONLY; never V004 recovery headroom",
        },
        "h008_disposition": {
            "proposed_disposition": proposed_h008,
            "rationale": h008_rationale,
            "concentration_metrics": {
                "dominant_category": dominant_cat,
                "dominant_count": dominant_count,
                "dominant_share": dominant_share,
                "top_two_categories": top_two_categories,
                "top_two_count": top_two_count,
                "top_two_share": top_two_share,
            },
            "decision_rule": (
                "When E5 = 0 and primary_count > 0, proposed_disposition is "
                "H008_SUPERVISORY_INTERPRETATION_REQUIRED with descriptive concentration metrics; "
                "support or non-support must never be automatically assigned by a numerical percentage. "
                "INCONCLUSIVE_D006 if unmapped rejections (E5 > 0) occur, primary population is zero, "
                "or baseline fails."
            ),
        },
        "primary_decompositions": primary_decomps_list,
    }


def assert_expected_surfaces(doc: Mapping[str, Any]) -> None:
    """Validate all required structural surfaces in output document."""
    required = (
        "decision_accounting",
        "entry_stage_populations",
        "primary_population",
        "fvg_source_stratification",
        "entry_rejection_category_distribution",
        "entry_rejection_by_source",
        "state_expiry_surface",
        "ready_for_entry_surface",
        "early_entry_surface",
        "structure_and_liquidity_surface",
        "strategy_rejection_context",
        "h008_disposition",
    )
    missing = [key for key in required if key not in doc]
    if missing:
        raise D006Error(f"preregistered D006 surface missing: {missing}")

    accounting = doc["decision_accounting"]
    if (
        accounting["reducer_classified"]
        + accounting["missing_history"]
        + accounting["unavailable_input"]
        + accounting["evaluation_error"]
        != accounting["scheduled"]
    ):
        raise D006AccountingError("decision accounting does not reconcile")

    pops = doc["entry_stage_populations"]
    if not pops.get("partition_reconciles"):
        raise D006AccountingError("entry stage partition reconciliation false")

    cats = doc["entry_rejection_category_distribution"]
    prim_count = int(doc["primary_population"]["count"])
    cat_sum = sum(cats.values())
    if cat_sum != prim_count:
        raise D006AccountingError(
            f"rejection category sum mismatch: {cat_sum} != {prim_count}"
        )

    if cats.get(CATEGORY_E5_UNMAPPED_ENTRY_REJECTION, 0) > 0:
        if doc["h008_disposition"]["proposed_disposition"] != "INCONCLUSIVE_D006":
            raise D006Error(
                "Unmapped entry rejection must result in INCONCLUSIVE_D006 disposition"
            )
    elif prim_count > 0:
        disp = doc["h008_disposition"]["proposed_disposition"]
        if disp != "H008_SUPERVISORY_INTERPRETATION_REQUIRED":
            raise D006Error(
                f"When E5=0 and primary_count>0, proposed_disposition must be "
                f"H008_SUPERVISORY_INTERPRETATION_REQUIRED, got {disp!r}"
            )


def run_d006(
    store: Any,
    *,
    tooling_commit: str,
    prior_v003_result_path: Path | str | None = None,
    blob_source=None,
) -> tuple[dict[str, Any], bytes]:
    """Execute preregistered D006 measurement over a Fold-01 feature store.

    Loop discipline is the frozen D001/V002/V003 one. Reconstructs private
    deterministic state, executes frozen V003 observation and decomposes
    entry-stage attrition fail-closed. Returns (document, canonical_bytes).
    """
    from bot.strategy.config import StrategyConfig  # noqa: PLC0415
    from bot.strategy.setup_state import (  # noqa: PLC0415
        StrategyState,
        record_from_state,
    )

    identity = store.identity
    check_store_boundary(dict(identity))

    config = StrategyConfig()
    seed_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    state_record = record_from_state(
        StrategyState(event_time=seed_time),
        event_at=seed_time,
    )
    buckets = {
        "missing_history": 0,
        "unavailable_input": 0,
        "evaluation_error": 0,
    }

    scheduled = 0
    rows: list[dict[str, Any]] = []
    v003_observations: list[dict[str, Any]] = []
    primary_decompositions: list[dict[str, Any]] = []

    for snapshot in _snapshot_rows(store):
        scheduled += 1
        bucket = classify_snapshot(snapshot)
        if bucket is not None:
            name, _status = bucket
            buckets[name] += 1
            continue

        if _reference_check_failed(snapshot):
            buckets["evaluation_error"] += 1
            continue

        prior_state_record = state_record
        row, next_record = evaluate_orchestration_decision(
            snapshot,
            prior_state_record,
        )

        if row["action"] == "error":
            buckets["evaluation_error"] += 1
            continue

        rows.append(row)

        gate11_entered = (
            "gate_11_confluence_score" in (row.get("gate_results") or {})
        )
        if gate11_entered:
            assert_store_semantic_compatibility(snapshot)
            v003_obs = observe_v003_decision(
                row,
                snapshot,
                prior_state_record,
                config=config,
                decision_result_record=next_record,
            )
            v003_observations.append(v003_obs)

            if (
                v003_obs["v003_gate11_passed"]
                and v003_obs["v003_strategy_eligible"]
                and not v003_obs["v003_entry_ready"]
            ):
                payload = json.loads(snapshot.gate_payload)
                decision_at = datetime.fromtimestamp(
                    int(snapshot.available_at_ms) / 1000, tz=timezone.utc
                )
                frame = _entry_frame(list(payload.get("entry_rows") or []))
                pair = v003_obs.get("_pair")
                if pair is None:
                    from bot.strategy.models import StrategySide  # noqa: PLC0415
                    from bot.strategy.variant_v003 import evaluate_v003_structural_pair  # noqa: PLC0415

                    htf_bias = str(payload.get("htf_bias") or "")
                    side = {
                        "bullish": StrategySide.LONG,
                        "bearish": StrategySide.SHORT,
                    }.get(htf_bias, StrategySide.FLAT)
                    consumed_ids = _consumed_ids_from_record(prior_state_record)
                    pair = evaluate_v003_structural_pair(
                        frame,
                        side,
                        decision_at,
                        config,
                        fvgs=list(payload.get("fvgs") or []),
                        consumed_ids=consumed_ids,
                    )

                # Assert synthetic equivalence against v003_obs
                assert bool(pair.structurally_active) == v003_obs["v003_structurally_active"]
                assert pair.block_id == v003_obs["v003_block_id"]
                assert (pair.side.value if hasattr(pair.side, "value") else str(pair.side)) == v003_obs["v003_side"]
                assert bool(pair.final_fvg_associated) == v003_obs["v003_final_fvg_associated"]
                assert bool(pair.temporal_fvg_evidence) == v003_obs["v003_temporal_fvg_evidence"]
                assert pair.fvg_evidence_source == v003_obs["v003_fvg_evidence_source"]

                decomp = decompose_v003_decision(
                    row=row,
                    snapshot=snapshot,
                    decision_result_record=next_record,
                    decision_at=decision_at,
                    frame=frame,
                    pair=pair,
                    score=v003_obs["v003_gate11_score"],
                    payload=payload,
                )
                primary_decompositions.append(decomp)

        state_record = next_record

    reconcile_accounting(
        scheduled=scheduled,
        classified=len(rows),
        missing_history=buckets["missing_history"],
        unavailable_input=buckets["unavailable_input"],
        evaluation_error=buckets["evaluation_error"],
    )

    baseline_reconciliation = reconcile_v003_prior_result(
        prior_v003_result_path, v003_observations
    )
    aggregated = aggregate_d006(v003_observations, primary_decompositions)

    doc: dict[str, Any] = {
        "diagnostic_id": D006_ID,
        "linked_hypothesis_id": H008_ID,
        "motivating_variant_id": V003_ID,
        "motivating_result_id": V003_RESULT_ID,
        "charter_id": CHARTER_ID,
        "charter_sha256": CHARTER_SHA256,
        "specification_document": SPECIFICATION_DOCUMENT,
        "specification_sha256": SPEC_SHA256,
        "classification": CLASSIFICATION,
        "provenance": provenance(
            tooling_commit=tooling_commit,
            store_identity=dict(identity),
            blob_source=blob_source,
        ),
        "fold01_boundary": [FOLD01_START, FOLD01_END],
        "decision_accounting": {
            "scheduled": scheduled,
            "reducer_classified": len(rows),
            "missing_history": buckets["missing_history"],
            "unavailable_input": buckets["unavailable_input"],
            "evaluation_error": buckets["evaluation_error"],
            "reconciles": True,
        },
        "v003_baseline_reproduction": baseline_reconciliation,
        "entry_stage_populations": aggregated["entry_stage_populations"],
        "primary_population": aggregated["primary_population"],
        "fvg_source_stratification": aggregated["fvg_source_stratification"],
        "entry_rejection_category_distribution": aggregated[
            "entry_rejection_category_distribution"
        ],
        "entry_rejection_by_source": aggregated["entry_rejection_by_source"],
        "state_expiry_surface": aggregated["state_expiry_surface"],
        "ready_for_entry_surface": aggregated["ready_for_entry_surface"],
        "early_entry_surface": aggregated["early_entry_surface"],
        "structure_and_liquidity_surface": aggregated["structure_and_liquidity_surface"],
        "strategy_rejection_context": aggregated["strategy_rejection_context"],
        "h008_disposition": aggregated["h008_disposition"],
        "primary_decompositions": aggregated["primary_decompositions"],
        "invariance_assertions": {
            "state_invariance_verified": True,
            "no_strategy_state_mutation": True,
            "no_counterfactual_candidate_counts": True,
            "no_rule_relaxation_claimed": True,
            "no_profitability_metrics": True,
            "tier_b_sealed": True,
        },
        "budget_consumption_note": (
            "diagnostics become permanently 5 / 12 at the instant "
            "first Fold-01 D006 empirical observation occurs; variants remain 3 / 8"
        ),
        "reserved_evidence": {
            "fold_02_untouched": True,
            "fold_03_untouched": True,
            "fold_04_untouched": True,
            "holdout_untouched": True,
            "data_2025_plus_untouched": True,
        },
    }

    _reject_banned_metrics(doc)
    assert_expected_surfaces(doc)
    return doc, _canonical(doc).encode("utf-8")


def write_result(
    material: Mapping[str, Any],
    rendered: bytes,
    output_dir: Path | str,
) -> tuple[Path, str]:
    """Atomically write the deterministic result; refuse overwrite."""
    out = Path(output_dir)
    reject_holdout_path(str(out))
    target = out / "phase8-v2-D006_result.json"
    if target.exists():
        raise D006Error(f"result already exists; refusing overwrite: {target}")
    out.mkdir(parents=True, exist_ok=True)
    staging = out / f".staging-{uuid.uuid4().hex[:8]}"
    staging.write_bytes(rendered)
    os.replace(staging, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != hashlib.sha256(rendered).hexdigest():
        raise D006Error("result hash mismatch after write")
    return target, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the Fold-01 feature store")
    parser.add_argument("--tooling-commit", required=True, help="40-character Git commit")
    parser.add_argument("--output-dir", required=True, help="directory for result JSON")
    parser.add_argument(
        "--v003-result",
        default=V003_SEALED_RESULT_PATH,
        help="path to sealed V003 R001 result JSON for baseline reproduction check",
    )
    args = parser.parse_args(argv)

    validate_authorized_store_path(args.store)
    from bot.validation.market_feature_store import load_feature_store  # noqa: PLC0415

    store = load_feature_store(
        Path(args.store),
        verify_rows=True,
    )
    doc, rendered = run_d006(
        store,
        tooling_commit=args.tooling_commit,
        prior_v003_result_path=args.v003_result,
    )
    target, digest = write_result(doc, rendered, Path(args.output_dir))
    print(f"D006 result written: {target} (SHA-256: {digest}, bytes: {len(rendered)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
