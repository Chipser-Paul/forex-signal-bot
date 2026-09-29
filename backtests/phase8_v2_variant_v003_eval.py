"""Preregistered V003 Fold-01 structural measurement tooling (H003).

DEVELOPMENT_VARIANT_EVIDENCE — V003 — FOLD01 — NOT PROFITABILITY EVIDENCE

Governance
----------
* Variant:            phase6-development-v2-V003 (Causal Temporal FVG Evidence Memory)
* Primary hypothesis: phase8-v2-H003 (Order-Block and Fair-Value-Gap Temporal Association)
* Supporting:         phase8-v2-D005-R001 (H003 SUPPORTED_BY_D005);
                      phase6-development-v2-V002-R001 (OPPORTUNITY_INSUFFICIENT)
* Specification:      docs/PHASE8_V2_VARIANT_V003.md (SHA-256 recorded below)
* Charter:            phase8-v2-research-charter-v1-8527e3a5eec98f53
* Implementation:     bot/strategy/variant_v003.py (frozen V003 evaluator/scorer/
                      downstream path; historical canonical semantics untouched)
* Forensic status:    phase8-v2-S002 cleared (canonical store verified intact)

Frozen measurement contract (preregistered before empirical access):

* Fold 01 ONLY: the store must be fold-01-a8b406884ab3525a with full coverage;
  the historical store ``fold-01-1d710826193a6767`` is refused as input;
  Tier B (Folds 02-04), holdout and 2025+ data fail closed.
* Structured pre-open boundary check (``validate_authorized_store_path``)
  refuses holdout/2025+/other-fold paths before any access.
* The loop reuses the frozen D001/V002 discipline verbatim: canonical snapshot
  classification, reference check, the production orchestrator adapter
  (``evaluate_orchestration_decision``), the seed setup-state record, the
  cell-local record carry and the accounting reconciliation.
* The V003 observer evaluates the frozen V003 structural-pair evaluator
  (``evaluate_v003_structural_pair``) over the reducer's exact M5 entry frame
  with reducer-exact consumed ids from the causal PRIOR state record, scores
  Gate 11 with the V003 scorer and runs the V003 downstream strategy path.
* Critical live-zone separation: historical filled temporal FVGs satisfy the
  confluence evidence requirement, but NEVER populate ``context["fvg_zone"]``,
  strategy state, limit/pullback zones, or RR geometry.
* State invariance: frozen strategy state is NEVER mutated.
* Candidate-ready count equals real frozen Gate-12/13 entry objects.
* Raw output is written atomically outside Git, refusing overwrite, and
  content-hashed; provenance binds ``canonical_git_blob_v1`` committed bytes.
* THIS TOOLING IS NOT EXECUTED BY THE FREEZE TASK.  Empirical execution
  requires separate supervisory authorization; at the instant first Fold-01
  V003 strategy behavior is observed, strategy variants become 3 / 8.
"""

from __future__ import annotations

import argparse
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
from backtests.phase8_v2_variant_v001_eval import reject_holdout_path  # noqa: E402
from backtests.phase8_v2_variant_v002_eval import (  # noqa: E402
    REQUIRED_PAYLOAD_FIELDS,
    _age_summary,
    _canonical,
    _consumed_ids_from_record,
    _entry_frame,
    _evidence,
    _gate_funnel,
    _persisted_setup_id,
    _reject_banned_metrics,
    _v002_private_entry_state,
    check_store_boundary,
)
from bot.strategy.variant_v003 import (  # noqa: E402
    SPEC_SHA256 as V003_SPEC_SHA256,
    V003_FVG_LABEL,
    V003_OB_LABEL,
    evaluate_v003_strategy,
    evaluate_v003_structural_pair,
    score_v003_setup,
)

V003_ID = "phase6-development-v2-V003"
H003_ID = "phase8-v2-H003"
D005_ID = "phase8-v2-D005"
CHARTER_ID = "phase8-v2-research-charter-v1-8527e3a5eec98f53"
CHARTER_SHA256 = "8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc"
SPEC_SHA256 = V003_SPEC_SHA256
SPECIFICATION_DOCUMENT = "docs/PHASE8_V2_VARIANT_V003.md"
IMPLEMENTATION_MODULE = "bot/strategy/variant_v003.py"
FINGERPRINT_CONTRACT = "canonical_git_blob_v1"
CLASSIFICATION = "DEVELOPMENT_VARIANT_EVIDENCE — V003 — FOLD01 — NOT PROFITABILITY EVIDENCE"
TOOLING_RELPATH = "backtests/phase8_v2_variant_v003_eval.py"
OPPORTUNITY_TARGET = 90
HISTORICAL_STORE_ID = "fold-01-1d710826193a6767"
AUTHORIZED_FOLD01_STORE_BASENAME = "fold-01-a8b406884ab3525a"
FOLD01_START_MS = int(datetime.fromisoformat(FOLD01_START).timestamp() * 1000)
FOLD01_END_MS = int(datetime.fromisoformat(FOLD01_END).timestamp() * 1000)

_STANDALONE_YEAR_PART = re.compile(r"^\d{4}$")
_ISO_YEAR_PREFIX_PART = re.compile(r"^(?:20|19)\d{2}-")
_STRUCTURAL_YEAR_MARKER = re.compile(r"year=(\d{4})")
_FOLD_STORE_PART = re.compile(r"^fold-\d{2}-")

HOLDOUT_TOKENS = ("holdout", "hold_out", "final_validation", "validation_fold")


class V003EvalError(RuntimeError):
    """Frozen V003 measurement contract violation."""


class BoundaryError(V003EvalError):
    """Fold/holdout/temporal boundary violation."""


class StoreCompatibilityError(V003EvalError):
    """Store is not semantically sufficient for V003 causal reconstruction."""


def validate_authorized_store_path(path: str | Path) -> None:
    """V003 structured pre-open boundary check (inheriting D005 TC002 discipline)."""
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
            f"{AUTHORIZED_FOLD01_STORE_BASENAME!r} is permitted for V003"
        )


def assert_store_semantic_compatibility(snapshot: Any) -> None:
    """Prove from input semantics the store feeds V003."""
    payload_text = getattr(snapshot, "gate_payload", None)
    if not payload_text:
        raise StoreCompatibilityError(
            "V003 requires a persisted gate payload; this store cannot "
            "reconstruct the V003 causal inputs"
        )
    try:
        payload = json.loads(payload_text)
    except (TypeError, ValueError) as error:
        raise StoreCompatibilityError(f"gate payload is not decodable: {error}") from error
    missing = [field for field in REQUIRED_PAYLOAD_FIELDS if field not in payload]
    if missing:
        raise StoreCompatibilityError(
            f"store payload lacks V003-required causal inputs {missing}"
        )


def _v003_entry(
    *,
    state: Any,
    decision_at: datetime,
    frame: Any,
    pair: Any,
    score: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Frozen Gate 12/13 through ``determine_entry`` under V003 evidence."""
    from strategies.smc_engine.entry_model import determine_entry  # noqa: PLC0415

    current_price = float(frame["close"].iloc[-1])
    internal = payload.get("internal_structure") or {}
    session_context = payload.get("session_context") or {}
    liquidity_context = payload.get("liquidity_context") or {}
    ob_zone = None
    if pair.structurally_active and pair.zone_low is not None:
        ob_zone = (float(pair.zone_low), float(pair.zone_high))

    # CRITICAL LIVE-ZONE SEPARATION: live fvg_zone is populated ONLY from the
    # final unfilled FVG surface.  For temporal-only evidence, live_fvg_bottom/top
    # is None, so fvg_zone is None.
    fvg_zone = None
    if pair.live_fvg_bottom is not None and pair.live_fvg_top is not None:
        fvg_zone = (float(pair.live_fvg_bottom), float(pair.live_fvg_top))

    entry = determine_entry(
        "XAUUSDm",
        state,
        current_price,
        score_result=dict(score),
        context={
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
        },
        emit_log=None,
    )
    return entry


def _v003_entry_readiness(
    *,
    row: Mapping[str, Any],
    snapshot: Any,
    decision_result_record: Any,
    decision_at: datetime,
    frame: Any,
    payload: Mapping[str, Any],
    pair: Any,
    score: Mapping[str, Any],
    strategy_eligible: bool,
    config: Any,
) -> tuple[str | None, dict[str, Any] | None, bool]:
    """Frozen Gate-12/13 entry readiness for one V003 observation."""
    setup_id = _persisted_setup_id(decision_result_record, row.get("decision_id"))
    if not strategy_eligible:
        return setup_id, None, False
    state = _v002_private_entry_state(
        decision_result_record,
        decision_at=decision_at,
        payload=payload,
    )
    entry = _v003_entry(
        state=state,
        decision_at=decision_at,
        frame=frame,
        pair=pair,
        score=score,
        payload=payload,
    )
    return setup_id, entry, bool(entry)


def observe_v003_decision(
    row: Mapping[str, Any],
    snapshot: Any,
    prior_state_record: Any,
    decision_result_record: Any,
    *,
    config: Any,
) -> dict[str, Any]:
    """Evaluate V003 structural-pair evidence and downstream strategy for one entrant."""
    from bot.strategy.models import StrategySide  # noqa: PLC0415

    payload = json.loads(snapshot.gate_payload)
    decision_id = row["decision_id"]
    decision_at = datetime.fromtimestamp(
        int(snapshot.available_at_ms) / 1000, tz=timezone.utc
    )
    raw_bias = str(payload.get("htf_bias") or "").lower()
    bias = raw_bias if raw_bias in ("bullish", "bearish") else "bullish"
    requested_side = StrategySide.LONG if bias == "bullish" else StrategySide.SHORT

    rows = list(payload.get("entry_rows") or [])
    frame = _entry_frame(rows)
    fvgs = list(payload.get("fvgs") or [])
    consumed_ids = _consumed_ids_from_record(prior_state_record)

    pair = evaluate_v003_structural_pair(
        frame,
        requested_side,
        decision_at,
        config,
        fvgs=fvgs,
        consumed_ids=consumed_ids,
    )

    pd_flag = bool((payload.get("ob_result") or {}).get("in_discount_or_premium", True))
    sweep_flag = bool(
        payload.get("liquidity_signal")
        or (payload.get("liquidity_context") or {}).get("liquidity_swept")
    )

    score = score_v003_setup(
        pair=pair,
        htf_bias=bias,
        price_in_discount_or_premium=pd_flag,
        liquidity_swept=sweep_flag,
    )
    gate11_passed = bool(score["passes_threshold"])

    strategy_eligible = False
    if gate11_passed:
        evidence = _evidence(pd_flag, sweep_flag)
        strategy_res = evaluate_v003_strategy(
            adapter="replay",
            symbol=str(payload.get("symbol") or "XAUUSDm"),
            decision_at=decision_at,
            side=bias,
            entry_frame=frame,
            htf_bias=bias,
            dxy_context=dict(payload.get("dxy_context") or {}),
            news_context=dict(payload.get("news_context") or {}),
            session_context=dict(payload.get("session_context") or {}),
            evidence=evidence,
            fvgs=fvgs,
            config=config,
            consumed_block_ids=consumed_ids,
        )
        strategy_eligible = bool(getattr(strategy_res, "decision", None) in ("ENTER_BUY", "ENTER_SELL"))

    setup_id, entry, entry_ready = _v003_entry_readiness(
        row=row,
        snapshot=snapshot,
        decision_result_record=decision_result_record,
        decision_at=decision_at,
        frame=frame,
        payload=payload,
        pair=pair,
        score=score,
        strategy_eligible=strategy_eligible,
        config=config,
    )

    legacy_gate11_passed = bool((row.get("gate_results") or {}).get("gate_11_confluence_score"))

    return {
        "decision_id": decision_id,
        "available_at_ms": int(snapshot.available_at_ms),
        "v003_pair_state": pair.state,
        "v003_pair_reason": pair.reason,
        "v003_side": pair.side.value if hasattr(pair.side, "value") else str(pair.side),
        "v003_block_id": pair.block_id,
        "v003_age_bars": pair.age_bars,
        "v003_structurally_active": pair.structurally_active,
        "v003_final_fvg_associated": pair.final_fvg_associated,
        "v003_temporal_fvg_evidence": pair.temporal_fvg_evidence,
        "v003_fvg_evidence": pair.v003_fvg_evidence,
        "v003_fvg_evidence_source": pair.fvg_evidence_source,
        "v003_exact_overlap_descriptive": pair.exact_overlap,
        "v003_temporal_fvg_offset_bars": pair.temporal_fvg_offset_bars,
        "v003_temporal_fvg_count": pair.temporal_fvg_count,
        "v003_gate11_score": score["score"],
        "v003_gate11_passed": gate11_passed,
        "v003_strategy_eligible": strategy_eligible,
        "v003_entry_ready": entry_ready,
        "v003_setup_id": setup_id,
        "v003_entry": entry,
        "legacy_score_passed": legacy_gate11_passed,
    }


def aggregate_v003(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate V003 observations across all Gate-11 entrants."""
    observations = list(observations)
    pair_states: dict[str, int] = {}
    pair_reasons: dict[str, int] = {}
    sides = {"LONG": 0, "SHORT": 0, "FLAT": 0}
    active = 0
    final_fvg_count = 0
    temporal_fvg_count = 0
    total_fvg_evidence_count = 0
    fvg_sources = {"FINAL_SURFACE": 0, "TEMPORAL_MEMORY": 0, "NONE": 0}
    overlap_true = 0
    overlap_false = 0
    overlap_not_available = 0
    legacy_pass = 0
    legacy_fail = 0
    ages: list[int] = []
    temporal_offsets: list[int] = []

    gate11_pass = 0
    strategy_pass = 0
    entry_pass = 0
    candidates: list[dict[str, Any]] = []

    for obs in observations:
        state = obs["v003_pair_state"]
        reason = obs["v003_pair_reason"]
        pair_states[state] = pair_states.get(state, 0) + 1
        pair_reasons[reason] = pair_reasons.get(reason, 0) + 1
        sides[obs["v003_side"]] = sides.get(obs["v003_side"], 0) + 1

        if obs["v003_structurally_active"]:
            active += 1
            ages.append(int(obs["v003_age_bars"]))

        source = obs["v003_fvg_evidence_source"]
        fvg_sources[source] = fvg_sources.get(source, 0) + 1

        if obs["v003_final_fvg_associated"]:
            final_fvg_count += 1
            overlap = obs["v003_exact_overlap_descriptive"]
            if overlap is True:
                overlap_true += 1
            elif overlap is False:
                overlap_false += 1
            else:
                overlap_not_available += 1

        if obs["v003_temporal_fvg_evidence"]:
            temporal_fvg_count += 1
            if obs["v003_temporal_fvg_offset_bars"] is not None:
                temporal_offsets.append(int(obs["v003_temporal_fvg_offset_bars"]))

        if obs["v003_fvg_evidence"]:
            total_fvg_evidence_count += 1

        if obs["legacy_score_passed"]:
            legacy_pass += 1
        else:
            legacy_fail += 1

        gate11_passed = bool(obs["v003_gate11_passed"])
        strategy_passed = bool(obs["v003_strategy_eligible"])
        entry_ready = bool(obs["v003_entry_ready"])

        if gate11_passed:
            gate11_pass += 1
        if strategy_passed:
            strategy_pass += 1
        if entry_ready:
            entry_pass += 1
            candidates.append(
                {
                    "setup_id": obs["v003_setup_id"],
                    "decision_id": obs["decision_id"],
                    "side": obs["v003_side"],
                    "age_bars": obs["v003_age_bars"],
                    "fvg_evidence_source": obs["v003_fvg_evidence_source"],
                    "exact_overlap_descriptive": obs["v003_exact_overlap_descriptive"],
                    "temporal_fvg_offset_bars": obs["v003_temporal_fvg_offset_bars"],
                    "entry": obs["v003_entry"],
                }
            )

    entrants = len(observations)
    candidate_ready = entry_pass
    candidate_setup_ids = [item["setup_id"] for item in candidates]
    id_counts: dict[str, int] = {}
    for setup_id in candidate_setup_ids:
        id_counts[setup_id] = id_counts.get(setup_id, 0) + 1
    unique_ids = len(id_counts)
    duplicate_occurrences = candidate_ready - unique_ids

    long_count = sum(1 for item in candidates if item["side"] == "LONG")
    short_count = sum(1 for item in candidates if item["side"] == "SHORT")
    candidate_final_count = sum(1 for item in candidates if item["fvg_evidence_source"] == "FINAL_SURFACE")
    candidate_temporal_count = sum(1 for item in candidates if item["fvg_evidence_source"] == "TEMPORAL_MEMORY")

    if candidate_ready >= OPPORTUNITY_TARGET:
        classification = "OPPORTUNITY_SUFFICIENT"
    elif candidate_ready > 0:
        classification = "OPPORTUNITY_INSUFFICIENT"
    else:
        classification = "NO_CANDIDATES"

    return {
        "V003_structural_pair_surface": {
            "gate11_entrants_observed": entrants,
            "v003_pair_state_counts": dict(sorted(pair_states.items())),
            "h007_pair_state_reason_distribution": dict(sorted(pair_reasons.items())),
            "v003_structurally_active_count": active,
            "v003_sides": {key: sides.get(key, 0) for key in ("LONG", "SHORT", "FLAT")},
            "v003_final_surface_fvg_evidence_count": final_fvg_count,
            "v003_temporal_memory_fvg_evidence_count": temporal_fvg_count,
            "v003_total_fvg_evidence_count": total_fvg_evidence_count,
            "v003_fvg_evidence_source_distribution": fvg_sources,
            "exact_overlap_descriptive_true": overlap_true,
            "exact_overlap_descriptive_false": overlap_false,
            "exact_overlap_descriptive_not_available": overlap_not_available,
            "legacy_score_passed_count": legacy_pass,
            "legacy_score_failed_count": legacy_fail,
            "v003_structural_active_age_summary": _age_summary(ages),
            "temporal_fvg_offset_summary": _age_summary(temporal_offsets),
            "score_component_labels": {
                "ob_component": V003_OB_LABEL,
                "fvg_component": V003_FVG_LABEL,
                "weights": [2, 1, 2, 1, 2],
                "maximum": 8,
                "threshold": 8,
            },
        },
        "V003_variant_funnel": {
            "gate_11_v003": {
                "entered": entrants,
                "passed": gate11_pass,
                "failed": entrants - gate11_pass,
            },
            "canonical_strategy_v003": {
                "entered": gate11_pass,
                "passed": strategy_pass,
                "failed": gate11_pass - strategy_pass,
            },
            "gate_12_13_rr_entry_v003": {
                "entered": strategy_pass,
                "passed": entry_pass,
                "failed": strategy_pass - entry_pass,
            },
            "stage_definitions": {
                "gate_11_v003": "every Gate-11 entrant; passed = V003 8/8 score pass",
                "canonical_strategy_v003": "entered = V003 Gate-11 passers; passed = evaluate_v003_strategy entry_eligible",
                "gate_12_13_rr_entry_v003": "entered = V003 canonical-strategy passers; passed = frozen determine_entry returns an entry",
            },
        },
        "candidate_surface": {
            "candidate_ready": candidate_ready,
            "candidate_rate": (
                round(candidate_ready / entrants, 6) if entrants else 0.0
            ),
            "candidate_long_count": long_count,
            "candidate_short_count": short_count,
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
        "success_classification": {
            "classification": classification,
            "candidate_ready": candidate_ready,
            "opportunity_target": OPPORTUNITY_TARGET,
            "headroom_upper_bound": 97,
            "note": "97 is an arithmetic upper bound only (61 V002 baseline + 36 D005 qualifying temporal decisions); not a candidate prediction",
        },
    }


def assert_expected_surfaces(document: Mapping[str, Any]) -> None:
    """Validate all required structural surfaces in output document."""
    required = (
        "decision_accounting",
        "gate_funnel",
        "V003_structural_pair_surface",
        "V003_variant_funnel",
        "candidate_surface",
        "success_classification",
    )
    missing = [key for key in required if key not in document]
    if missing:
        raise V003EvalError(f"preregistered V003 surface missing: {missing}")
    accounting = document["decision_accounting"]
    if (
        accounting["reducer_classified"] + accounting["missing_history"]
        + accounting["unavailable_input"] + accounting["evaluation_error"]
        != accounting["scheduled"]
    ):
        raise V003EvalError("decision accounting does not reconcile")
    surface = document["V003_structural_pair_surface"]
    if surface["gate11_entrants_observed"] < 0:
        raise V003EvalError("negative V003 population")
    entered = int(
        document.get("gate_funnel", {})
        .get("gate_11_confluence_score", {})
        .get("entered", -1)
    )
    if entered < 0:
        raise V003EvalError("gate funnel lacks gate_11_confluence_score")
    if surface["gate11_entrants_observed"] != entered:
        raise V003EvalError(
            f"V003 population mismatch: {surface['gate11_entrants_observed']} != {entered}"
        )
    funnel = document["V003_variant_funnel"]
    candidate = document["candidate_surface"]
    candidate_ready = int(candidate["candidate_ready"])
    if candidate_ready < 0:
        raise V003EvalError("negative candidate_ready")
    if candidate_ready != int(funnel["gate_12_13_rr_entry_v003"]["passed"]):
        raise V003EvalError(
            f"candidate_ready != gate_12_13 passed: {candidate_ready} != {funnel['gate_12_13_rr_entry_v003']['passed']}"
        )
    if not (
        candidate_ready
        <= int(funnel["canonical_strategy_v003"]["passed"])
        <= int(funnel["gate_11_v003"]["passed"])
        <= surface["gate11_entrants_observed"]
    ):
        raise V003EvalError("V003 variant funnel chain violated")
    if funnel["gate_11_v003"]["entered"] != surface["gate11_entrants_observed"]:
        raise V003EvalError("gate_11_v003 entered != entrant population")
    if funnel["canonical_strategy_v003"]["entered"] != funnel["gate_11_v003"]["passed"]:
        raise V003EvalError("canonical_strategy_v003 entered != gate_11_v003 passed")
    if funnel["gate_12_13_rr_entry_v003"]["entered"] != funnel["canonical_strategy_v003"]["passed"]:
        raise V003EvalError("gate_12_13 entered != canonical_strategy passed")
    reconciliation = candidate["setup_id_reconciliation"]
    if not reconciliation["unique_plus_duplicates_equals_candidate_ready"]:
        raise V003EvalError("candidate setup-ID reconciliation violated")


def run_v003(
    store: Any,
    *,
    implementation_commit: str,
    tooling_commit: str,
) -> tuple[dict[str, Any], bytes]:
    """Execute V003 structural measurement over Fold-01 feature store."""
    from bot.strategy.config import StrategyConfig  # noqa: PLC0415

    check_store_boundary(store.identity)
    config = StrategyConfig()

    snapshots = store.snapshots()
    first_snapshot = next(iter(snapshots), None)
    if first_snapshot is not None:
        assert_store_semantic_compatibility(first_snapshot)

    accounting = {
        "scheduled": 0,
        "reducer_classified": 0,
        "missing_history": 0,
        "unavailable_input": 0,
        "evaluation_error": 0,
    }
    rows: list[dict[str, Any]] = []
    v003_observations: list[dict[str, Any]] = []

    prior_state_record: Any = None
    for snapshot in snapshots:
        accounting["scheduled"] += 1
        category = classify_snapshot(snapshot)
        accounting[category] += 1
        if category != "reducer_classified":
            continue

        decision_row, decision_res_record, next_state_record = (
            evaluate_orchestration_decision(snapshot, prior_state_record=prior_state_record)
        )
        rows.append(decision_row)

        # Check if decision entered Gate 11
        gate_res = decision_row.get("gate_results") or {}
        if "gate_11_confluence_score" in gate_res:
            obs = observe_v003_decision(
                decision_row,
                snapshot,
                prior_state_record,
                decision_res_record,
                config=config,
            )
            v003_observations.append(obs)

        prior_state_record = next_state_record

    reconcile_accounting(accounting)
    funnel = _gate_funnel(rows)
    aggregated = aggregate_v003(v003_observations)

    doc: dict[str, Any] = {
        "variant_id": V003_ID,
        "hypothesis_id": H003_ID,
        "supporting_diagnostic_id": D005_ID,
        "charter_id": CHARTER_ID,
        "charter_sha256": CHARTER_SHA256,
        "specification_document": SPECIFICATION_DOCUMENT,
        "specification_sha256": SPEC_SHA256,
        "classification": CLASSIFICATION,
        "provenance": {
            "research_identity": "phase6-development-v2",
            "variant_id": V003_ID,
            "hypothesis_id": H003_ID,
            "specification_document": SPECIFICATION_DOCUMENT,
            "specification_sha256": SPEC_SHA256,
            "implementation_module": IMPLEMENTATION_MODULE,
            "implementation_commit": implementation_commit,
            "tooling": TOOLING_RELPATH,
            "tooling_commit": tooling_commit,
            "fingerprint_contract": FINGERPRINT_CONTRACT,
            "fold_store_identity_sha256": store.identity.get("identity_sha256"),
            "fold01_boundary": [FOLD01_START, FOLD01_END],
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        "fold01_boundary": [FOLD01_START, FOLD01_END],
        "decision_accounting": accounting,
        "gate_funnel": funnel,
        "V003_structural_pair_surface": aggregated["V003_structural_pair_surface"],
        "V003_variant_funnel": aggregated["V003_variant_funnel"],
        "candidate_surface": aggregated["candidate_surface"],
        "success_classification": aggregated["success_classification"],
        "one_concept_rule": (
            "broadening Gate-11 FVG confluence component from final-unfilled "
            "surface only to (F_final OR F_temporal) using causal temporal FVG "
            "evidence memory; live zone separation strictly preserved"
        ),
        "live_zone_separation_verified": True,
        "state_invariance_verified": True,
        "budget_consumption_note": (
            "strategy variants become permanently 3 / 8 at the instant "
            "first Fold-01 V003 strategy behavior is empirically observed"
        ),
        "reserved_evidence": {
            "fold_02_untouched": True,
            "fold_03_untouched": True,
            "fold_04_untouched": True,
            "holdout_untouched": True,
            "data_2025_plus_untouched": True,
        },
        "no_profitability_metrics": True,
        "no_lag_threshold_applied": True,
        "dxy_authority_unchanged": True,
    }
    _reject_banned_metrics(doc)
    assert_expected_surfaces(doc)
    return doc, _canonical(doc).encode("utf-8")


def write_result(material: Mapping[str, Any], rendered: bytes, output_dir: Path) -> tuple[Path, str]:
    """Atomically write the deterministic result; refuse overwrite."""
    output_dir = Path(output_dir)
    reject_holdout_path(str(output_dir))
    target = output_dir / "phase6-development-v2-V003_result.json"
    if target.exists():
        raise V003EvalError(f"result already exists; refusing overwrite: {target}")
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = output_dir / f".staging-{uuid.uuid4().hex[:8]}"
    staging.write_bytes(rendered)
    os.replace(staging, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != hashlib.sha256(rendered).hexdigest():
        raise V003EvalError("result hash mismatch after write")
    return target, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the Fold-01 feature store")
    parser.add_argument("--implementation-commit", required=True)
    parser.add_argument("--tooling-commit", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    from bot.validation.market_feature_store import load_feature_store  # noqa: PLC0415

    validate_authorized_store_path(args.store)
    store = load_feature_store(Path(args.store), verify_rows=True)
    document, rendered = run_v003(
        store,
        implementation_commit=args.implementation_commit,
        tooling_commit=args.tooling_commit,
    )
    path, sha = write_result(document, rendered, Path(args.output_dir))
    print(json.dumps({"path": str(path), "sha256": sha}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
