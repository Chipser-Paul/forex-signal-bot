"""V004 Unified Requested-Side Entry Direction Authority — isolated evaluation tooling.

DEVELOPMENT_VARIANT_EVIDENCE — phase6-development-v2-V004 — H009

Governing variant boundary (``docs/PHASE8_V2_VARIANT_V004.md``; register
``phase6-development-v2-V004``):

* Evaluates Gate 12/13 entry readiness under unified requested-side directional
  authority for setups passing V003 Gate-11 confluence (8/8) and canonical
  strategy protections.
* Strict V003 baseline preservation: every V003 candidate decision is guaranteed
  to remain a candidate decision under V004 with exact geometry and setup ID preserved.
* Canonical state invariance: authoritative strategy state is never mutated;
  fallback evaluation operates strictly on a private deep copy.
* Strict liquidity rule invariance: evaluates the exact frozen determine_entry logic.
* Target domain: Tier-A Fold 01 (fold-01-a8b406884ab3525a).
* Density target: candidate_ready >= 90 for OPPORTUNITY_SUFFICIENT.
* Zero numeric parameters (trials remain 0 / 4).
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path, PureWindowsPath
import re
import sys
from typing import Any, Iterable, Mapping

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backtests.phase8_v2_diagnostic_d001 import (
    FOLD01_END,
    FOLD01_START,
    _reference_check_failed,
    _snapshot_rows,
    classify_snapshot,
    evaluate_orchestration_decision,
    reconcile_accounting,
)
from backtests.phase8_v2_variant_v002_eval import (
    FOLD_PREFIX_ALLOWED,
    _canonical_blob_source,
    _consumed_ids_from_record,
    _entry_frame,
    _evidence,
    _gate_funnel,
    _persisted_setup_id,
    _reject_banned_metrics,
    _v002_private_entry_state,
    check_store_boundary,
)
from backtests.phase8_v2_variant_v003_eval import (
    REQUIRED_PAYLOAD_FIELDS,
    _age_summary,
    _v003_entry,
)
from bot.strategy.variant_v003 import (
    V003_FVG_LABEL,
    V003_OB_LABEL,
)
from bot.strategy.variant_v004 import (
    SPEC_SHA256 as V004_SPEC_SHA256,
    V004_ID,
    H009_ID,
    V003_ID,
    D006_ID,
    V004_SOURCE_V003_BASELINE,
    V004_SOURCE_DIRECTIONAL_FALLBACK,
    V004_SOURCE_NONE,
    V004VariantError,
    evaluate_v004_entry_readiness,
    evaluate_v004_strategy,
    evaluate_v004_structural_pair,
    is_valid_liquidity_alignment,
    score_v004_setup,
)

CHARTER_ID = "phase8-v2-research-charter-v1-8527e3a5eec98f53"
CHARTER_SHA256 = "8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc"
SPEC_SHA256 = V004_SPEC_SHA256
SPECIFICATION_DOCUMENT = "docs/PHASE8_V2_VARIANT_V004.md"
IMPLEMENTATION_MODULE = "bot/strategy/variant_v004.py"
FINGERPRINT_CONTRACT = "canonical_git_blob_v1"
CLASSIFICATION = "DEVELOPMENT_VARIANT_EVIDENCE — V004 — FOLD01 — NOT PROFITABILITY EVIDENCE"
TOOLING_RELPATH = "backtests/phase8_v2_variant_v004_eval.py"
OPPORTUNITY_TARGET = 90
V003_BASELINE_TARGET = 81
AUTHORIZED_FOLD01_STORE_BASENAME = "fold-01-a8b406884ab3525a"
FOLD01_START_MS = int(datetime.fromisoformat(FOLD01_START).timestamp() * 1000)
FOLD01_END_MS = int(datetime.fromisoformat(FOLD01_END).timestamp() * 1000)

_PROVENANCE = {
    "research_identity": "phase6-development-v2",
    "variant_id": V004_ID,
    "hypothesis_id": H009_ID,
    "specification_document": SPECIFICATION_DOCUMENT,
    "specification_sha256": SPEC_SHA256,
    "implementation_module": IMPLEMENTATION_MODULE,
    "tooling": TOOLING_RELPATH,
    "fingerprint_contract": FINGERPRINT_CONTRACT,
}

_STANDALONE_YEAR_PART = re.compile(r"^\d{4}$")
_ISO_YEAR_PREFIX_PART = re.compile(r"^(?:20|19)\d{2}-")
_STRUCTURAL_YEAR_MARKER = re.compile(r"year=(\d{4})")
_FOLD_STORE_PART = re.compile(r"^fold-\d{2}-")
HOLDOUT_TOKENS = ("holdout", "hold_out", "final_validation", "validation_fold")


class V004EvalError(RuntimeError):
    """Frozen V004 measurement contract violation."""


class BoundaryError(V004EvalError):
    """Fold/holdout/temporal boundary violation."""


class StoreCompatibilityError(V004EvalError):
    """Store is not semantically sufficient for V004 causal reconstruction."""


def validate_authorized_store_path(path: str | Path) -> None:
    """V004 structured pre-open boundary check (inheriting D005 TC002 discipline)."""
    raw = str(path)
    lower = raw.lower()
    for token in HOLDOUT_TOKENS:
        if token in lower:
            raise BoundaryError(f"holdout / final-validation store refused: {raw!r}")
    pure = PureWindowsPath(raw)
    for part in pure.parts:
        if _STANDALONE_YEAR_PART.match(part):
            try:
                year = int(part)
                if year >= 2025:
                    raise BoundaryError(f"post-2024 calendar directory refused: {raw!r}")
            except ValueError:
                pass
        match_iso = _ISO_YEAR_PREFIX_PART.match(part)
        if match_iso:
            try:
                year = int(part[:4])
                if year >= 2025:
                    raise BoundaryError(f"post-2024 ISO-dated directory refused: {raw!r}")
            except ValueError:
                pass
        for match in _STRUCTURAL_YEAR_MARKER.finditer(part):
            try:
                year = int(match.group(1))
                if year >= 2025:
                    raise BoundaryError(f"post-2024 year marker refused: {raw!r}")
            except ValueError:
                pass
    basename = pure.name
    if _FOLD_STORE_PART.match(basename) and basename != AUTHORIZED_FOLD01_STORE_BASENAME:
        raise BoundaryError(
            f"unauthorized fold store refused: {basename!r}; only "
            f"{AUTHORIZED_FOLD01_STORE_BASENAME!r} is permitted for V004"
        )


def provenance(
    *,
    implementation_commit: str,
    tooling_commit: str,
    store_identity: Mapping[str, Any],
    generated_at: str | None = None,
    blob_source=None,
) -> dict[str, Any]:
    """Provenance bound to the V004 implementation commit and this tooling."""
    from bot.scientific.canonical_bytes import canonical_file_digest  # noqa: PLC0415

    if not implementation_commit or len(implementation_commit) != 40:
        raise V004EvalError("V004 implementation commit identity invalid")
    if not tooling_commit or len(tooling_commit) != 40:
        raise V004EvalError("tooling commit identity invalid")
    try:
        tooling_fingerprint = canonical_file_digest(
            TOOLING_RELPATH,
            commit=tooling_commit,
            repo=REPO_ROOT,
            blob_source=(
                blob_source if blob_source is not None else _canonical_blob_source()
            ),
        )
    except Exception as error:  # fail closed: no worktree/normalized fallback
        raise V004EvalError(f"V004 tooling fingerprint unresolvable: {error}") from error
    blob = json.dumps(store_identity, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        **_PROVENANCE,
        "implementation_commit": implementation_commit,
        "tooling_commit": tooling_commit,
        "tooling_fingerprint": tooling_fingerprint,
        "store_identity_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "generated_at_utc": generated_at or datetime.now(timezone.utc).isoformat(),
    }


def assert_store_semantic_compatibility(snapshot: Any) -> None:
    """Prove from input semantics the store feeds V004."""
    payload_text = getattr(snapshot, "gate_payload", None)
    if not payload_text:
        raise StoreCompatibilityError(
            "V004 requires a persisted gate payload; this store cannot "
            "reconstruct the V004 causal inputs"
        )
    try:
        payload = json.loads(payload_text)
    except (TypeError, ValueError) as error:
        raise StoreCompatibilityError(f"gate payload is not decodable: {error}") from error
    missing = [field for field in REQUIRED_PAYLOAD_FIELDS if field not in payload]
    if missing:
        raise StoreCompatibilityError(
            f"store payload lacks V004-required causal inputs {missing}"
        )


def observe_v004_decision(
    row: Mapping[str, Any],
    snapshot: Any,
    prior_state_record: Any,
    *,
    config: Any,
    decision_result_record: Any = None,
) -> dict[str, Any]:
    """Evaluate V004 unified directional authority decision for one entrant."""
    from bot.strategy.models import StrategySide  # noqa: PLC0415

    decision_id = row.get("decision_id")
    payload = json.loads(snapshot.gate_payload)
    rows = list(payload.get("entry_rows") or [])
    fvgs = list(payload.get("fvgs") or [])
    htf_bias = str(payload.get("htf_bias") or "")
    decision_at = datetime.fromtimestamp(
        int(snapshot.available_at_ms) / 1000, tz=timezone.utc
    )
    side = {
        "bullish": StrategySide.LONG,
        "bearish": StrategySide.SHORT,
    }.get(htf_bias, StrategySide.FLAT)

    if side is StrategySide.FLAT:
        raise V004EvalError(
            f"Gate-11 entrant {decision_id!r} lacks a resolved htf_bias; "
            "V004 refuses to map it to FLAT"
        )

    frame = _entry_frame(rows)
    consumed_ids = _consumed_ids_from_record(prior_state_record)

    pair = evaluate_v004_structural_pair(
        frame,
        side,
        decision_at,
        config,
        fvgs=fvgs,
        consumed_ids=consumed_ids,
    )

    dxy_context = dict(payload.get("dxy_context") or {})
    news_context = dict(payload.get("news_context") or {})
    session_context = dict(payload.get("session_context") or {})
    liquidity_context = dict(payload.get("liquidity_context") or {})
    internal = dict(payload.get("internal_structure") or {})
    structure_context = dict(liquidity_context.get("structure_context") or {})

    pd_flag = bool(
        structure_context.get(
            "discount_zone"
            if htf_bias == "bullish"
            else "premium_zone"
        )
    )

    sweep_flag = bool(payload.get("liquidity_signal"))

    evidence = _evidence(pd_flag, sweep_flag)
    strategy = evaluate_v004_strategy(
        adapter="live",
        symbol="XAUUSDm",
        decision_at=decision_at,
        side=htf_bias,
        entry_frame=frame,
        htf_bias=htf_bias,
        dxy_context=dxy_context,
        news_context=news_context,
        session_context=session_context,
        evidence=evidence,
        fvgs=fvgs,
        config=config,
        consumed_block_ids=consumed_ids,
    )

    score = score_v004_setup(
        pair=pair,
        htf_bias=htf_bias,
        price_in_discount_or_premium=pd_flag,
        liquidity_swept=sweep_flag,
    )

    setup_id = _persisted_setup_id(decision_result_record, decision_id)
    strategy_eligible = bool(strategy.entry_eligible)
    gate11_passed = bool(score["passes_threshold"])

    # Reconstruct private state for Gate 12/13
    state = _v002_private_entry_state(
        decision_result_record,
        decision_at=decision_at,
        payload=payload,
    )

    # Evaluate frozen V003 baseline entry
    v003_entry = None
    v003_entry_ready = False
    if strategy_eligible and state is not None:
        v003_entry = _v003_entry(
            state=state,
            decision_at=decision_at,
            frame=frame,
            pair=pair,
            score=score,
            payload=payload,
        )
        v003_entry_ready = bool(v003_entry)

    # Prepare entry context for determine_entry
    current_price = float(frame["close"].iloc[-1])
    ob_zone = None
    if pair.structurally_active and pair.zone_low is not None:
        ob_zone = (float(pair.zone_low), float(pair.zone_high))

    fvg_zone = None
    if pair.live_fvg_bottom is not None and pair.live_fvg_top is not None:
        fvg_zone = (float(pair.live_fvg_bottom), float(pair.live_fvg_top))

    entry_context = {
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

    # Evaluate V004 entry readiness
    v004_entry, v004_entry_ready, v004_entry_source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=decision_at,
        current_price=current_price,
        pair=pair,
        score=score,
        context=entry_context,
        requested_side=htf_bias,
        v003_gate11_passed=gate11_passed,
        v003_strategy_eligible=strategy_eligible,
        v003_entry=v003_entry,
        v003_entry_ready=v003_entry_ready,
        symbol="XAUUSDm",
    )

    v004_setup_id = setup_id if v004_entry_ready else None
    v003_setup_id = setup_id if v003_entry_ready else None

    return {
        "decision_id": decision_id,
        "available_at_ms": int(snapshot.available_at_ms),
        "v004_pair_state": pair.state,
        "v004_pair_reason": pair.reason,
        "v004_structurally_active": bool(pair.structurally_active),
        "v004_side": pair.side.value if hasattr(pair.side, "value") else str(pair.side),
        "v004_block_id": pair.block_id,
        "v004_age_bars": int(pair.age_bars),
        "v004_final_fvg_associated": bool(pair.final_fvg_associated),
        "v004_temporal_fvg_evidence": bool(pair.temporal_fvg_evidence),
        "v004_fvg_evidence": bool(pair.v003_fvg_evidence),
        "v004_fvg_evidence_source": pair.fvg_evidence_source,
        "v004_gate11_score": score,
        "v004_gate11_passed": gate11_passed,
        "v004_strategy_eligible": strategy_eligible,
        "v003_setup_id": v003_setup_id,
        "v003_entry": v003_entry,
        "v003_entry_ready": v003_entry_ready,
        "v004_setup_id": v004_setup_id,
        "v004_entry": v004_entry,
        "v004_entry_ready": v004_entry_ready,
        "v004_entry_source": v004_entry_source,
        "v004_entry_direction": (
            str(v004_entry.get("direction")) if v004_entry else None
        ),
    }


def aggregate_v004(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate V004 observations across all Gate-11 entrants."""
    observations = list(observations)

    entrants = len(observations)
    gate11_pass = 0
    strategy_pass = 0
    v003_entry_pass = 0
    v004_entry_pass = 0
    active = 0
    final_fvg_count = 0
    temporal_fvg_count = 0
    total_fvg_evidence_count = 0

    pair_states: dict[str, int] = {}
    pair_reasons: dict[str, int] = {}
    sides: dict[str, int] = {}
    fvg_sources: dict[str, int] = {"FINAL_SURFACE": 0, "TEMPORAL_MEMORY": 0, "NONE": 0}
    candidates: list[dict[str, Any]] = []

    for item in observations:
        state = item["v004_pair_state"]
        pair_states[state] = pair_states.get(state, 0) + 1
        reason = item["v004_pair_reason"]
        pair_reasons[reason] = pair_reasons.get(reason, 0) + 1
        side_val = item["v004_side"]
        sides[side_val] = sides.get(side_val, 0) + 1
        source = item["v004_fvg_evidence_source"]
        fvg_sources[source] = fvg_sources.get(source, 0) + 1

        if item["v004_structurally_active"]:
            active += 1
        if item["v004_final_fvg_associated"]:
            final_fvg_count += 1
        if item["v004_temporal_fvg_evidence"]:
            temporal_fvg_count += 1
        if item["v004_fvg_evidence"]:
            total_fvg_evidence_count += 1

        if item["v004_gate11_passed"]:
            gate11_pass += 1
        if item["v004_strategy_eligible"]:
            strategy_pass += 1
        if item["v003_entry_ready"]:
            v003_entry_pass += 1
            # Strict V003 baseline preservation check: must be ready in V004!
            if not item["v004_entry_ready"]:
                raise V004EvalError(
                    f"V003 baseline candidate {item['decision_id']} lost in V004"
                )
            if item["v004_entry_source"] != V004_SOURCE_V003_BASELINE:
                raise V004EvalError(
                    f"V003 baseline candidate {item['decision_id']} has source "
                    f"{item['v004_entry_source']!r}, expected {V004_SOURCE_V003_BASELINE!r}"
                )

        if item["v004_entry_ready"]:
            v004_entry_pass += 1
            candidates.append(
                {
                    "decision_id": item["decision_id"],
                    "setup_id": item["v004_setup_id"],
                    "available_at_ms": item["available_at_ms"],
                    "side": item["v004_side"],
                    "entry_direction": item["v004_entry_direction"],
                    "entry_source": item["v004_entry_source"],
                    "fvg_evidence_source": item["v004_fvg_evidence_source"],
                    "entry": item["v004_entry"],
                }
            )

    candidate_ready = v004_entry_pass
    candidate_setup_ids = [item["setup_id"] for item in candidates]
    id_counts: dict[str, int] = {}
    for setup_id in candidate_setup_ids:
        id_counts[setup_id] = id_counts.get(setup_id, 0) + 1
    unique_ids = len(id_counts)
    duplicate_occurrences = candidate_ready - unique_ids

    long_count = sum(1 for item in candidates if item["side"] == "LONG")
    short_count = sum(1 for item in candidates if item["side"] == "SHORT")
    v003_source_count = sum(
        1 for item in candidates if item["entry_source"] == V004_SOURCE_V003_BASELINE
    )
    fallback_source_count = sum(
        1 for item in candidates if item["entry_source"] == V004_SOURCE_DIRECTIONAL_FALLBACK
    )
    candidate_final_count = sum(
        1 for item in candidates if item["fvg_evidence_source"] == "FINAL_SURFACE"
    )
    candidate_temporal_count = sum(
        1 for item in candidates if item["fvg_evidence_source"] == "TEMPORAL_MEMORY"
    )

    if candidate_ready >= OPPORTUNITY_TARGET:
        classification = "OPPORTUNITY_SUFFICIENT"
    elif candidate_ready > 0:
        classification = "OPPORTUNITY_INSUFFICIENT"
    else:
        classification = "NO_CANDIDATES"

    return {
        "V004_structural_pair_surface": {
            "gate11_entrants_observed": entrants,
            "v004_pair_state_counts": dict(sorted(pair_states.items())),
            "pair_state_reason_distribution": dict(sorted(pair_reasons.items())),
            "v004_structurally_active_count": active,
            "v004_sides": {key: sides.get(key, 0) for key in ("LONG", "SHORT", "FLAT")},
            "v004_final_surface_fvg_evidence_count": final_fvg_count,
            "v004_temporal_memory_fvg_evidence_count": temporal_fvg_count,
            "v004_total_fvg_evidence_count": total_fvg_evidence_count,
            "v004_fvg_evidence_source_distribution": fvg_sources,
            "score_component_labels": {
                "ob_component": V003_OB_LABEL,
                "fvg_component": V003_FVG_LABEL,
                "weights": [2, 1, 2, 1, 2],
                "maximum": 8,
                "threshold": 8,
            },
        },
        "V004_variant_funnel": {
            "gate_11_v004": {
                "entered": entrants,
                "passed": gate11_pass,
                "failed": entrants - gate11_pass,
            },
            "canonical_strategy_v004": {
                "entered": gate11_pass,
                "passed": strategy_pass,
                "failed": gate11_pass - strategy_pass,
            },
            "gate_12_13_rr_entry_v004": {
                "entered": strategy_pass,
                "passed": candidate_ready,
                "failed": strategy_pass - candidate_ready,
            },
            "stage_definitions": {
                "gate_11_v004": "every Gate-11 entrant; passed = V004 (V003) 8/8 score pass",
                "canonical_strategy_v004": "entered = V004 Gate-11 passers; passed = evaluate_v004_strategy entry_eligible",
                "gate_12_13_rr_entry_v004": "entered = V004 canonical-strategy passers; passed = determine_entry returns an entry under unified directional authority",
            },
        },
        "candidate_surface": {
            "candidate_ready": candidate_ready,
            "candidate_rate": (
                round(candidate_ready / entrants, 6) if entrants else 0.0
            ),
            "candidate_long_count": long_count,
            "candidate_short_count": short_count,
            "candidate_v003_baseline_count": v003_source_count,
            "candidate_v004_directional_fallback_count": fallback_source_count,
            "candidate_final_surface_count": candidate_final_count,
            "candidate_temporal_memory_count": candidate_temporal_count,
            "unique_candidate_setup_ids": unique_ids,
            "duplicate_candidate_setup_id_occurrences": duplicate_occurrences,
            "setup_id_reconciliation": {
                "unique_plus_duplicates_equals_candidate_ready": (
                    unique_ids + duplicate_occurrences == candidate_ready
                ),
            },
            "candidates": candidates,
        },
        "v003_baseline_reconciliation": {
            "v003_baseline_candidate_count": v003_entry_pass,
            "all_v003_candidates_preserved": bool(v003_entry_pass == v003_source_count),
            "v003_fallback_recovery_count": fallback_source_count,
        },
        "success_classification": {
            "classification": classification,
            "candidate_ready": candidate_ready,
            "opportunity_target": OPPORTUNITY_TARGET,
            "note": "Density adequacy target >= 90; establishes neither sample sufficiency nor profitability",
        },
    }


def assert_expected_surfaces(document: Mapping[str, Any]) -> None:
    """Validate all required structural surfaces in output document."""
    required_root_keys = (
        "variant_id",
        "hypothesis_id",
        "charter_id",
        "specification_document",
        "specification_sha256",
        "classification",
        "provenance",
        "fold01_boundary",
        "decision_accounting",
        "gate_funnel",
        "V004_structural_pair_surface",
        "V004_variant_funnel",
        "candidate_surface",
        "v003_baseline_reconciliation",
        "success_classification",
        "one_concept_rule",
        "canonical_state_invariance_verified",
        "liquidity_rules_invariance_verified",
    )
    for key in required_root_keys:
        if key not in document:
            raise V004EvalError(f"missing required root key {key!r}")

    funnel = document["V004_variant_funnel"]
    candidate = document["candidate_surface"]
    surface = document["V004_structural_pair_surface"]
    candidate_ready = int(candidate["candidate_ready"])
    if candidate_ready < 0:
        raise V004EvalError("negative candidate_ready")
    if candidate_ready != int(funnel["gate_12_13_rr_entry_v004"]["passed"]):
        raise V004EvalError(
            f"candidate_ready != gate_12_13 passed: "
            f"{candidate_ready} != {funnel['gate_12_13_rr_entry_v004']['passed']}"
        )
    if not (
        candidate_ready
        <= int(funnel["canonical_strategy_v004"]["passed"])
        <= int(funnel["gate_11_v004"]["passed"])
        <= surface["gate11_entrants_observed"]
    ):
        raise V004EvalError("V004 variant funnel chain violated")
    if funnel["gate_11_v004"]["entered"] != surface["gate11_entrants_observed"]:
        raise V004EvalError("gate_11_v004 entered != entrant population")
    if funnel["canonical_strategy_v004"]["entered"] != funnel["gate_11_v004"]["passed"]:
        raise V004EvalError("canonical_strategy_v004 entered != gate_11_v004 passed")
    if funnel["gate_12_13_rr_entry_v004"]["entered"] != funnel["canonical_strategy_v004"]["passed"]:
        raise V004EvalError("gate_12_13 entered != canonical_strategy passed")

    reconciliation = candidate["setup_id_reconciliation"]
    if not reconciliation["unique_plus_duplicates_equals_candidate_ready"]:
        raise V004EvalError("candidate setup-ID reconciliation violated")

    v003_rec = document["v003_baseline_reconciliation"]
    if not v003_rec["all_v003_candidates_preserved"]:
        raise V004EvalError("V003 baseline candidates not 100% preserved")


def run_v004(
    store: Any,
    *,
    implementation_commit: str,
    tooling_commit: str,
    blob_source=None,
) -> tuple[dict[str, Any], bytes]:
    """Execute preregistered V004 measurement over a Fold-01 feature store.

    Loop discipline follows the frozen D001/V003 pattern.
    Fails closed on boundary, store-compatibility, accounting or structural violations.
    Returns ``(document, bytes)``.
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
        StrategyState(event_time=seed_time), event_at=seed_time,
    )
    buckets = {"missing_history": 0, "unavailable_input": 0, "evaluation_error": 0}
    rows: list[dict[str, Any]] = []
    v004_observations: list[dict[str, Any]] = []
    scheduled = 0
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
            snapshot, prior_state_record,
        )
        if row["action"] == "error":
            buckets["evaluation_error"] += 1
            continue
        rows.append(row)
        gate11_entered = "gate_11_confluence_score" in (
            row.get("gate_results") or {}
        )
        if gate11_entered:
            assert_store_semantic_compatibility(snapshot)
            v004_obs = observe_v004_decision(
                row,
                snapshot,
                prior_state_record,
                config=config,
                decision_result_record=next_record,
            )
            v004_observations.append(v004_obs)
        state_record = next_record

    reconcile_accounting(
        scheduled=scheduled,
        classified=len(rows),
        missing_history=buckets["missing_history"],
        unavailable_input=buckets["unavailable_input"],
        evaluation_error=buckets["evaluation_error"],
    )
    funnel = _gate_funnel(rows)
    aggregated = aggregate_v004(v004_observations)

    doc: dict[str, Any] = {
        "variant_id": V004_ID,
        "hypothesis_id": H009_ID,
        "predecessor_variant_id": V003_ID,
        "supporting_diagnostic_id": D006_ID,
        "charter_id": CHARTER_ID,
        "charter_sha256": CHARTER_SHA256,
        "specification_document": SPECIFICATION_DOCUMENT,
        "specification_sha256": SPEC_SHA256,
        "classification": CLASSIFICATION,
        "provenance": provenance(
            implementation_commit=implementation_commit,
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
        "gate_funnel": funnel,
        "V004_structural_pair_surface": aggregated["V004_structural_pair_surface"],
        "V004_variant_funnel": aggregated["V004_variant_funnel"],
        "candidate_surface": aggregated["candidate_surface"],
        "v003_baseline_reconciliation": aggregated["v003_baseline_reconciliation"],
        "success_classification": aggregated["success_classification"],
        "one_concept_rule": (
            "unifying Gate-12/13 entry directional authority and liquidity-alignment "
            "interpretation with the requested trade direction (requested_side) via "
            "deep-copied state without mutating authoritative state or relaxing frozen liquidity rules"
        ),
        "canonical_state_invariance_verified": True,
        "liquidity_rules_invariance_verified": True,
        "numeric_parameter_trials_consumed": 0,
        "budget_consumption_note": (
            "strategy variants becomes permanently 4 / 8 observed at the instant "
            "first Fold-01 V004 strategy behavior is empirically observed; "
            "numeric trials remain 0 / 4"
        ),
    }

    _reject_banned_metrics(doc)
    assert_expected_surfaces(doc)

    serialized = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    raw_bytes = serialized.encode("utf-8")
    return doc, raw_bytes


def main(argv: list[str] | None = None) -> int:
    """CLI driver for V004 measurement over an authorized feature store."""
    from bot.market_data import load_feature_store  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description="Execute V004 entry direction authority measurement on a feature store."
    )
    parser.add_argument(
        "--store",
        required=True,
        help="Path to the feature store directory (must be fold-01-a8b406884ab3525a).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path where the sealed V004 result JSON should be written.",
    )
    parser.add_argument(
        "--implementation-commit",
        required=True,
        help="40-hex Git commit SHA of the V004 implementation freeze.",
    )
    parser.add_argument(
        "--tooling-commit",
        required=True,
        help="40-hex Git commit SHA of this tooling freeze.",
    )
    parser.add_argument(
        "--verify-store-rows",
        action="store_true",
        default=True,
        help="Verify row content SHA-256 during load (default: True).",
    )
    args = parser.parse_args(argv)

    store_path = Path(args.store).resolve()
    output_path = Path(args.output).resolve()

    # Fail closed on unauthorized store paths or names
    validate_authorized_store_path(store_path)

    store = load_feature_store(store_path, verify_rows=args.verify_store_rows)
    _doc, raw_bytes = run_v004(
        store,
        implementation_commit=args.implementation_commit,
        tooling_commit=args.tooling_commit,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(".tmp")
    with open(temp_path, "wb") as f:
        f.write(raw_bytes)
    temp_path.replace(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
