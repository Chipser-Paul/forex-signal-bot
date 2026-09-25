"""Preregistered V2 diagnostic D003 tooling (phase8-v2-D003).

Frozen Canonical Gate-11 / Order-Block Lifecycle Decomposition.

DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE

Governance
----------
* Charter:           phase8-v2-research-charter-v1-8527e3a5eec98f53
* Charter SHA-256:   8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc
* Research identity: phase6-development-v2
* Preregistration:   docs/PHASE8_V2_DIAGNOSTIC_D003.md (Phase-A commit),
  register record ``phase8-v2-D003`` (status REGISTERED_NOT_EXECUTED).
* Motivation only: V001 R001 (FUNCTIONAL_REPAIR_NO_CANDIDATES) motivates
  this diagnostic; no observed V001 count is used as a target or oracle.

Scope (frozen)
--------------
Empirical universe (future authorized execution only): TIER_A_FOLD01,
preserved V001 store ``fold-01-a8b406884ab3525a``.  Primary population:
decisions that pass canonical classification, pass the reference check,
evaluate successfully through the canonical orchestration path, pass
Gate 10 and enter Gate 11 (Gate-11 scored; entrant regardless of the
Gate-11 outcome — key presence in the frozen ``gate_results`` render).

Metric surfaces A–H exactly as preregistered:

* A accounting (D001 classification/reference-check/accounting reuse);
* B exact frozen Gate-11 score components (five checks, points, score
  distribution, five-boolean co-occurrence);
* C descriptive premium/discount x legacy-OB x FVG-overlap contingency;
* D canonical ``evaluate_order_block`` lifecycle decomposition
  (eligibility = ELIGIBLE + RETEST_ELIGIBLE only);
* E acquisition (`ob_result.valid`) vs canonical (`eligible`) agreement;
* F canonical failure reasons (ungrouped);
* G contextual FVG coexistence with the D001 mirror geometry;
* H premium/discount context.

Canonical inputs are reconstructed ONLY from already-persisted causal
snapshot data (M5 ``entry_rows``, persisted ``htf_bias``, decision
timestamp, exact frozen ``StrategyConfig``, reducer-exact ``consumed_ids``
from the prior setup-state record).  The lifecycle observer is READ-ONLY
relative to strategy evaluation and never mutates reducer state.

Absolutely prohibited (structural output guard): pnl, profit, fills,
closed trades, win rate, expectancy, drawdown, Sharpe, returns, alternate
thresholds, score-at-X counterfactuals, candidates-if-condition-removed,
temporal lags.  Deterministic; fails closed on any accounting,
provenance or structural violation.  No MT5, no trading, no holdout, no
2025+ data.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

# Reuse the canonical D001 classification/adapter/accounting contracts
# verbatim (MR003 discipline: no gate-status interpretation outside D001),
# including D001's boundary-enforcing snapshot iteration.
from backtests.phase8_v2_diagnostic_d001 import (  # noqa: E402
    CLASSIFICATION,
    FOLD01_END,
    FOLD01_START,
    OVERLAP_LABEL,
    SCORE_LABELS,
    BoundaryError,
    D001Error,
    _reference_check_failed,
    _snapshot_rows,
    classify_snapshot,
    evaluate_orchestration_decision,
    mirror_fvg_in_ob,
    reconcile_accounting,
)

__all__ = [
    "DIAGNOSTIC_ID",
    "LABEL",
    "SPECIFICATION_SHA256",
    "D003Error",
    "REJECTED_D003_METRIC_KEY",
    "assert_expected_surfaces",
    "aggregate_d003",
    "canonical_ob_lifecycle",
    "observe_decision",
    "run_d003",
    "write_result",
]

DIAGNOSTIC_ID = "phase8-v2-D003"
LABEL = CLASSIFICATION
SPECIFICATION_SHA256 = "2b5204925a700cc2faa817835e77d298d778138f811bdfb2ad06cfe9c007cc46"

PROVENANCE = {
    "diagnostic_id": DIAGNOSTIC_ID,
    "research_identity": "phase6-development-v2",
    "charter_identity": "phase8-v2-research-charter-v1-8527e3a5eec98f53",
    "charter_sha256": "8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc",
    "linked_hypothesis": "phase8-v2-H002",
    "contextual_hypothesis": "phase8-v2-H001",
    "not_tested_hypotheses": ["phase8-v2-H003"],
    "not_reopened_hypotheses": ["phase8-v2-H005"],
    "specification_document": "docs/PHASE8_V2_DIAGNOSTIC_D003.md",
    "specification_sha256": SPECIFICATION_SHA256,
    "motivation_result_commit": "72bdcb7c9b3a520c501efbc9b2aa2139cc0ba455",
    "fingerprint_contract": "canonical_git_blob_v1",
    "fold01_boundary": [FOLD01_START, FOLD01_END],
    "classification": CLASSIFICATION,
}

REJECTED_D003_METRIC_KEY = "prohibited metric key"

# Repository root and tooling identity path for canonical_git_blob_v1
# fingerprints (established backtests convention: parents[1] of this file).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLING_RELPATH = "backtests/phase8_v2_diagnostic_d003.py"

# §30 banned-output guard: exact keys + counterfactual-family substrings,
# in the established V001 style (honest negation keys still pass).
BANNED_METRIC_KEYS = frozenset(
    {
        "pnl", "profit", "profit_factor", "win_rate", "expectancy",
        "drawdown", "sharpe", "returns", "return", "closed_trades", "trades",
        "fills", "fill_count",
    }
)
BANNED_METRIC_SUBSTRINGS = (
    "candidate_count_at_", "threshold_curve", "temporal_lag",
    "lag_distribution", "alternative_", "seven_of_eight", "partial_overlap",
    "optimal_", "sweep_for_", "alternate_score", "score_at_",
    "counterfactual_",
)


class D003Error(D001Error):
    """D003 preregistered-contract violation (fail closed)."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def canonical_ob_frame(rows: list[dict[str, Any]]) -> Any:
    """Rebuild the reducer's exact M5 entry frame from persisted rows.

    ``bot/state/gate_reducer.py::_entry_frame`` verbatim semantics,
    applied to the snapshot's already-persisted ``entry_rows`` — never
    from external candles or later bars.
    """
    import pandas as pd  # noqa: PLC0415

    frame = pd.DataFrame(rows)
    for column in ("open_time", "available_at"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], utc=True)
    return frame


def consumed_ids_from_record(prior_state_record: Any) -> frozenset[str]:
    """Reducer-exact causal consumed block ids from the prior state record.

    ``bot/state/gate_reducer.py`` (canonical legacy context)::

        consumed_block_ids = frozenset(
            binding.get("block_id") for key, binding in
            previous["consumption"]["bindings"].items()
            if key in previous["consumption"]["events"] and binding.get("block_id")
        )

    Read-only; the empty set is never assumed — it is derived.
    """
    if prior_state_record is None:
        return frozenset()
    previous = prior_state_record.data()
    consumption = previous.get("consumption") or {}
    bindings = consumption.get("bindings") or {}
    events = consumption.get("events") or {}
    return frozenset(
        binding.get("block_id")
        for key, binding in bindings.items()
        if key in events and binding.get("block_id")
    )


def canonical_ob_lifecycle(
    snapshot: Any,
    *,
    htf_bias: str,
    prior_state_record: Any,
    config: Any,
) -> dict[str, Any]:
    """READ-ONLY canonical lifecycle evaluation for one causal decision.

    Reconstructs the reducer's exact inputs from already-persisted causal
    snapshot data (M5 ``entry_rows`` + persisted ``htf_bias`` + decision
    timestamp + frozen ``StrategyConfig`` + reducer-exact consumed ids)
    and calls the frozen ``evaluate_order_block`` with them.  Never
    mutates reducer state and never feeds its result back into the
    strategy evaluation.
    """
    from bot.strategy.models import StrategySide  # noqa: PLC0415
    from bot.strategy.order_blocks import evaluate_order_block  # noqa: PLC0415

    payload = json.loads(snapshot.gate_payload)
    rows = list(payload.get("entry_rows") or [])
    decision_at = datetime.fromtimestamp(
        int(snapshot.available_at_ms) / 1000, tz=timezone.utc
    )
    side = {"bullish": StrategySide.LONG, "bearish": StrategySide.SHORT}.get(
        htf_bias, StrategySide.FLAT
    )
    consumed = consumed_ids_from_record(prior_state_record)
    result = evaluate_order_block(
        canonical_ob_frame(rows),
        side,
        decision_at,
        config,
        consumed_ids=consumed,
    )
    return {
        "state": result.state.value,
        "reason": result.reason,
        "side": result.side.value,
        "eligible": bool(result.eligible),
        "block_id": result.block_id,
        "zone_low": result.zone_low,
        "zone_high": result.zone_high,
        "consumed_ids_derived": sorted(consumed),
    }


def _reconcile_decision_render(
    row: Mapping[str, Any],
    decision_result_record: Any,
    checks: Mapping[str, bool],
) -> dict[str, Any]:
    """Reconcile the CURRENT decision's canonical persisted render against
    the frozen D001 row before any flattened-away field is used (TC003 §9).

    Read-only.  ``decision_result_record`` is the successful ``next_record``
    of THIS decision — a concept strictly separate from the causal
    ``prior_state_record`` (TC001), which alone drives consumed-id and
    lifecycle semantics.  This render may only supply fields the flattened
    D001 row contract does not retain (per-check awarded points, raw
    first-FVG geometry, ATR).  Any disagreement fails closed.
    """
    decision_id = row.get("decision_id")
    data = decision_result_record.data()
    if data.get("last_event_id") != decision_id:
        raise D003Error(
            f"current-decision render event mismatch at {decision_id!r}: "
            f"{data.get('last_event_id')!r}"
        )
    rendered = data.get("last_result")
    if not rendered:
        raise D003Error(f"current-decision render missing at {decision_id!r}")
    gate = json.loads(rendered)
    context = gate.get("context") or {}

    for name, value in (row.get("gate_results") or {}).items():
        rendered_gate = (gate.get("gate_results") or {}).get(name)
        if rendered_gate is not None and bool(rendered_gate.get("pass")) != value:
            raise D003Error(f"render gate disagreement at {decision_id!r}: {name}")

    render_score = context.get("score") or {}
    row_score = row.get("score") or {}
    for field in ("score", "max_score", "passes_threshold"):
        if render_score.get(field) != row_score.get(field):
            raise D003Error(
                f"render score {field} disagreement at {decision_id!r}"
            )
    render_checks = {
        str(check.get("label")): bool(check.get("passed"))
        for check in (render_score.get("checks") or [])
    }
    if render_checks != dict(checks):
        raise D003Error(f"render scorer checks disagreement at {decision_id!r}")
    if bool(render_checks.get(OVERLAP_LABEL)) != bool(
        (row.get("overlap") or {}).get("canonical_fvg_in_ob")
    ):
        raise D003Error(f"render overlap disagreement at {decision_id!r}")
    points = {
        str(check.get("label")): int(check.get("points", 0))
        for check in (render_score.get("checks") or [])
    }

    render_ob = context.get("ob") or {}
    if bool(render_ob.get("valid")) != bool((row.get("ob") or {}).get("valid")):
        raise D003Error(f"render OB validity disagreement at {decision_id!r}")

    render_fvgs = list(context.get("fvgs") or [])
    row_fvg = row.get("fvg") or {}
    if bool(render_fvgs) != bool(row_fvg.get("present")):
        raise D003Error(f"render FVG presence disagreement at {decision_id!r}")
    if len(render_fvgs) != int(row_fvg.get("count") or 0):
        raise D003Error(f"render FVG count disagreement at {decision_id!r}")
    if render_fvgs:
        render_direction = (
            render_fvgs[0].get("direction")
            if isinstance(render_fvgs[0], dict) else None
        )
        if render_direction != row_fvg.get("direction"):
            raise D003Error(f"render FVG direction disagreement at {decision_id!r}")

    render_bias = str(
        (context.get("bias_resolution") or {}).get("direction") or ""
    )
    row_direction = str((row.get("ob") or {}).get("direction") or "")
    if render_bias and row_direction and render_bias != row_direction:
        raise D003Error(f"render bias/direction disagreement at {decision_id!r}")

    return {
        "awarded_points": points,
        "raw_fvgs": render_fvgs,
        "atr": float((gate.get("market_conditions") or {}).get("atr") or 0.0),
    }


def observe_decision(
    row: Mapping[str, Any],
    prior_state_record: Any,
    *,
    snapshot: Any,
    config: Any,
    decision_result_record: Any,
) -> dict[str, Any]:
    """Augment one successful D001 row with the D003 decomposition.

    ``row`` is the canonical orchestration row produced by
    ``evaluate_orchestration_decision``; ``snapshot`` is the store row it
    was evaluated from and ``prior_state_record`` is the state record in
    effect at that decision (the record the reducer actually consumed —
    the one just advanced on success).  The augmentation is strictly
    read-only relative to strategy evaluation: the canonical lifecycle
    call observes already-persisted causal inputs and never mutates the
    setup-state chain.

    TC003 extraction contract: every preregistered surface is read from
    the FROZEN flattened D001 row (``row['score']``, ``row['ob']``,
    ``row['fvg']``, ``row['overlap']``, ``row['direction']``) — never
    from a ``gate_context`` key, which the D001 row contract does not
    publish.  ``decision_result_record`` is the successful ``next_record``
    of the CURRENT decision, used READ-ONLY after §9 reconciliation to
    recover fields flattened away by D001 (awarded points, raw FVG
    geometry, ATR); it is never used for consumed-id or lifecycle
    semantics, which remain bound exclusively to ``prior_state_record``.
    A Gate-11 entrant with a missing/degenerate score surface (the
    attempt-1 artifact) fails closed instead of emitting constants.
    """
    gate_results = row.get("gate_results") or {}
    gate_11_entered = "gate_11_confluence_score" in gate_results
    observation: dict[str, Any] = {
        "decision_id": row.get("decision_id"),
        "gate_10_pass": bool(gate_results.get("gate_10_internal_structure")),
        "gate_11_entered": gate_11_entered,
        "canonical_lifecycle": None,
    }
    if not gate_11_entered:
        return observation

    # --- frozen D001 row surfaces (TC003): never a fictional gate_context --
    score = row.get("score")
    if (
        not isinstance(score, Mapping)
        or score.get("score") is None
        or score.get("max_score") is None
        or score.get("passes_threshold") is None
    ):
        raise D003Error(
            "degenerate Gate-11 score surface at "
            f"{row.get('decision_id')!r}: frozen row score is missing or "
            "non-numeric (attempt-1 pattern must never be emitted)"
        )
    checks: dict[str, bool] = {}
    for label in SCORE_LABELS:
        value = (score.get("checks_passed") or {}).get(label)
        if value is None:
            raise D003Error(
                "degenerate Gate-11 score surface at "
                f"{row.get('decision_id')!r}: frozen check {label!r} missing"
            )
        checks[label] = bool(value)
    if bool(gate_results.get("gate_11_confluence_score")) != bool(
        score.get("passes_threshold")
    ):
        raise D003Error(
            "Gate-11 self-consistency violation at "
            f"{row.get('decision_id')!r}: gate pass boolean disagrees with "
            "the persisted score threshold boolean"
        )

    ob = row.get("ob") or {}
    fvg = row.get("fvg") or {}
    overlap = row.get("overlap") or {}
    final_fvg_present = bool(fvg.get("present"))
    final_fvg_direction = fvg.get("direction")
    htf_bias = str(ob.get("direction") or "")
    if htf_bias not in ("bullish", "bearish"):
        raise D003Error(
            "Gate-11 entrant at "
            f"{row.get('decision_id')!r} lacks a resolved canonical OB "
            f"direction ({ob.get('direction')!r}); refusing to map to FLAT"
        )

    pd_flag = bool(checks[SCORE_LABELS[1]])
    ob_flag = bool(checks[SCORE_LABELS[2]])
    overlap_flag = bool(checks[OVERLAP_LABEL])
    if overlap_flag != bool(overlap.get("canonical_fvg_in_ob")):
        raise D003Error(
            f"overlap reconciliation failure at {row.get('decision_id')!r}: "
            "scorer FVG-in-OB check disagrees with the frozen D001 "
            "canonical_fvg_in_ob boolean"
        )
    if ob_flag != bool(ob.get("valid")):
        raise D003Error(
            f"legacy OB reconciliation failure at {row.get('decision_id')!r}: "
            "scorer valid-OB check disagrees with row['ob']['valid']"
        )

    # --- current-decision render: ONLY for fields flattened away by D001 ---
    render = _reconcile_decision_render(row, decision_result_record, checks)
    points = render["awarded_points"]
    raw_fvgs = render["raw_fvgs"]
    first_fvg = raw_fvgs[0] if raw_fvgs else None

    lifecycle = canonical_ob_lifecycle(
        snapshot,
        htf_bias=htf_bias,
        prior_state_record=prior_state_record,
        config=config,
    )
    canonical_zone = None
    if lifecycle.get("eligible") and lifecycle.get("zone_low") is not None:
        canonical_zone = (lifecycle["zone_low"], lifecycle["zone_high"])
    _, canonical_geometry = mirror_fvg_in_ob(
        first_fvg, canonical_zone, float(render.get("atr") or 0.0)
    )

    observation["score"] = {
        "score": score.get("score"),
        "max_score": score.get("max_score"),
        "grade": score.get("grade"),
        "min_score_to_trade": score.get("min_score_to_trade"),
        "passes_threshold": bool(score.get("passes_threshold")),
        "checks_passed": {label: checks[label] for label in SCORE_LABELS},
        "awarded_points": {label: points.get(label, 0) for label in SCORE_LABELS},
    }
    observation["contingency"] = {
        "premium_discount": pd_flag,
        "legacy_ob_valid": ob_flag,
        "legacy_fvg_in_ob": overlap_flag,
        "legacy_ob": {
            "present": bool(ob.get("present")),
            "valid": bool(ob.get("valid")),
            "direction": ob.get("direction"),
            "type": ob.get("type"),
            "reason": ob.get("reason"),
        },
    }
    observation["canonical_lifecycle"] = lifecycle
    observation["final_fvg_present"] = final_fvg_present
    observation["final_fvg_direction"] = final_fvg_direction
    # D001 row overlap block (production legacy pair, mirror-verified) is
    # carried for context; the preregistered §18 canonical-pair geometry is
    # computed with the same frozen mirror function over the canonical
    # lifecycle zone (read-only, separation geometry only).
    observation["overlap_mirror"] = dict(overlap)
    observation["canonical_pair_geometry"] = canonical_geometry
    return observation


_DIRECTION_ALIASES = {
    "bullish": "LONG",
    "long": "LONG",
    "bearish": "SHORT",
    "short": "SHORT",
}


def _semantic_direction(value: Any) -> str | None:
    """Normalize a direction token to its semantic LONG/SHORT form (TC004).

    Legacy/acquisition vocabulary (``bullish``/``bearish``) and canonical
    vocabulary (``LONG``/``SHORT``) describe the same two directions, so
    Surface E must compare semantics, not spellings.  Mapping
    (case-insensitive): bullish/long -> LONG; bearish/short -> SHORT;
    absent/empty/FLAT -> None (directionally unavailable, never silently
    agreed or disagreed).  Any unexpected meaningful token fails closed.
    """
    if value is None:
        return None
    token = str(value).strip().lower()
    if token in ("", "flat"):
        return None
    normalized = _DIRECTION_ALIASES.get(token)
    if normalized is None:
        raise D003Error(f"unexpected direction token: {value!r}")
    return normalized


def aggregate_d003(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Reduce Gate-11 observations into the preregistered D003 surfaces."""
    obs = list(observations)
    gate11 = [o for o in obs if o.get("gate_11_entered")]
    check_pass: dict[str, int] = {label: 0 for label in SCORE_LABELS}
    check_fail: dict[str, int] = {label: 0 for label in SCORE_LABELS}
    points_awarded: dict[str, int] = {label: 0 for label in SCORE_LABELS}
    score_distribution: dict[str, int] = {}
    combo_counts: dict[str, int] = {}
    lifecycle_states: dict[str, int] = {}
    lifecycle_reasons: dict[str, int] = {}
    lifecycle_sides: dict[str, int] = {}
    state_reason: dict[str, dict[str, int]] = {}
    state_direction: dict[str, dict[str, int]] = {}
    agreement = {
        "legacy_false_canonical_false": 0,
        "legacy_false_canonical_true": 0,
        "legacy_true_canonical_false": 0,
        "legacy_true_canonical_true": 0,
    }
    direction_agreement = {"agree": 0, "disagree": 0, "not_available": 0}
    coexistence = {
        "canonical_eligible_and_final_fvg": 0,
        "canonical_eligible_no_final_fvg": 0,
        "canonical_not_eligible_with_final_fvg": 0,
        "neither": 0,
        "pairs_with_both": 0,
        "direction_agreement": {"agree": 0, "disagree": 0, "not_available": 0},
        "canonical_overlap_true": 0,
        "canonical_overlap_false": 0,
    }
    pd_lifecycle_fvg: dict[str, int] = {}
    for o in gate11:
        score = o.get("score") or {}
        passed = score.get("checks_passed") or {}
        awarded = score.get("awarded_points") or {}
        for label in SCORE_LABELS:
            flag = bool(passed.get(label))
            check_pass[label] += int(flag)
            check_fail[label] += int(not flag)
            points_awarded[label] += int(awarded.get(label, 0))
        score_distribution[str(score.get("score"))] = score_distribution.get(
            str(score.get("score")), 0
        ) + 1
        cont = o.get("contingency") or {}
        combo = "pd={} ob={} fvg={}".format(
            bool(cont.get("premium_discount")),
            bool(cont.get("legacy_ob_valid")),
            bool(cont.get("legacy_fvg_in_ob")),
        )
        combo_counts[combo] = combo_counts.get(combo, 0) + 1

        lifecycle = o.get("canonical_lifecycle") or {}
        state = str(lifecycle.get("state"))
        reason = str(lifecycle.get("reason"))
        side = str(lifecycle.get("side"))
        lifecycle_states[state] = lifecycle_states.get(state, 0) + 1
        lifecycle_reasons[reason] = lifecycle_reasons.get(reason, 0) + 1
        lifecycle_sides[side] = lifecycle_sides.get(side, 0) + 1
        per_state_reason = state_reason.setdefault(state, {})
        per_state_reason[reason] = per_state_reason.get(reason, 0) + 1
        per_state_direction = state_direction.setdefault(state, {})
        per_state_direction[side] = per_state_direction.get(side, 0) + 1

        legacy_valid = bool(cont.get("legacy_ob_valid"))
        canonical_eligible = bool(lifecycle.get("eligible"))
        cell = "legacy_{}_canonical_{}".format(
            "true" if legacy_valid else "false",
            "true" if canonical_eligible else "false",
        )
        agreement[cell] = agreement.get(cell, 0) + 1
        legacy_direction = (cont.get("legacy_ob") or {}).get("direction")
        # TC004 (Surface E only): compare SEMANTIC directions — the legacy
        # vocabulary (bullish/bearish) and the canonical lifecycle vocabulary
        # (LONG/SHORT) are equivalent spellings of the same two directions.
        # FLAT/unavailable -> not_available; unknown tokens fail closed via
        # _semantic_direction.  Surface G below keeps its original
        # like-vocabulary comparison untouched.
        legacy_semantic = _semantic_direction(legacy_direction)
        canonical_semantic = _semantic_direction(lifecycle.get("side"))
        if legacy_semantic is None or canonical_semantic is None:
            direction_agreement["not_available"] += 1
        elif legacy_semantic == canonical_semantic:
            direction_agreement["agree"] += 1
        else:
            direction_agreement["disagree"] += 1

        final_fvg = bool(o.get("final_fvg_present"))
        if canonical_eligible and final_fvg:
            coexistence["canonical_eligible_and_final_fvg"] += 1
            coexistence["pairs_with_both"] += 1
            if legacy_direction is None or o.get("final_fvg_direction") is None:
                coexistence["direction_agreement"]["not_available"] += 1
            elif str(legacy_direction) == str(o.get("final_fvg_direction")):
                coexistence["direction_agreement"]["agree"] += 1
            else:
                coexistence["direction_agreement"]["disagree"] += 1
            geometry = o.get("canonical_pair_geometry") or {}
            if bool(geometry.get("intersection")) or bool(geometry.get("containment")) or (
                geometry.get("signed_separation") is not None
                and float(geometry["signed_separation"]) <= 0.0
            ):
                coexistence["canonical_overlap_true"] += 1
            else:
                coexistence["canonical_overlap_false"] += 1
        elif canonical_eligible:
            coexistence["canonical_eligible_no_final_fvg"] += 1
        elif final_fvg:
            coexistence["canonical_not_eligible_with_final_fvg"] += 1
        else:
            coexistence["neither"] += 1

        combo3 = "pd={} eligible_ob={} fvg={}".format(
            bool(cont.get("premium_discount")),
            canonical_eligible,
            final_fvg,
        )
        pd_lifecycle_fvg[combo3] = pd_lifecycle_fvg.get(combo3, 0) + 1

    eligible_total = (
        lifecycle_states.get("ELIGIBLE", 0) + lifecycle_states.get("RETEST_ELIGIBLE", 0)
    )
    return {
        "gate11_entrants": len(gate11),
        "B_frozen_score_components": {
            "check_pass": check_pass,
            "check_fail": check_fail,
            "points_awarded": points_awarded,
            "score_distribution": dict(sorted(score_distribution.items())),
            "combination_frequencies": dict(sorted(combo_counts.items())),
        },
        "C_discriminating_contingency": dict(sorted(combo_counts.items())),
        "D_canonical_ob_lifecycle": {
            "state_distribution": dict(sorted(lifecycle_states.items())),
            "reason_distribution": dict(sorted(lifecycle_reasons.items())),
            "side_distribution": dict(sorted(lifecycle_sides.items())),
            "eligible_count": eligible_total,
            "non_eligible_count": len(gate11) - eligible_total,
            "state_x_reason": {
                state: dict(sorted(reasons.items()))
                for state, reasons in sorted(state_reason.items())
            },
            "state_x_direction": {
                state: dict(sorted(directions.items()))
                for state, directions in sorted(state_direction.items())
            },
        },
        "E_acquisition_canonical_agreement": {
            **agreement,
            "direction_agreement": direction_agreement,
        },
        "F_canonical_failure_reasons": dict(sorted(lifecycle_reasons.items())),
        "G_contextual_fvg_coexistence": coexistence,
        "H_premium_discount_context": dict(sorted(pd_lifecycle_fvg.items())),
    }


def _gate_funnel(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Preregistered surface A: gate entered/pass/fail accounting."""
    order = (
        "gate_8_liquidity",
        "gate_9_displacement",
        "gate_10_internal_structure",
        "gate_11_confluence_score",
        "canonical_strategy",
    )
    funnel: dict[str, dict[str, int]] = {
        name: {"entered": 0, "passed": 0, "failed": 0} for name in order
    }
    for row in rows:
        gate_results = row.get("gate_results") or {}
        for name in order:
            if name not in gate_results:
                continue
            funnel[name]["entered"] += 1
            funnel[name]["passed" if gate_results[name] else "failed"] += 1
    return funnel


def _canonical_blob_source():
    """Production committed-byte source: real Git plumbing on this repo."""
    from bot.scientific.canonical_bytes import make_git_blob_source  # noqa: PLC0415

    return make_git_blob_source(_REPO_ROOT)


def provenance(
    *,
    canonical_commit: str,
    tooling_commit: str,
    store_identity: Mapping[str, Any],
    generated_at: str | None = None,
    blob_source=None,
) -> dict[str, Any]:
    """Provenance block bound to this tooling run (fail closed).

    ``tooling_fingerprint`` is the SHA-256 of the committed Git blob of this
    tooling file at ``tooling_commit`` under the declared
    ``canonical_git_blob_v1`` contract — checkout-independent, never
    worktree bytes (TC002).  Any unresolvable commit/path/blob fails
    closed with :class:`D003Error`; there is no worktree or normalized
    fallback.  ``blob_source`` injects an alternative committed-byte
    reader (synthetic tests); production resolves via real Git plumbing.
    """
    from bot.scientific.canonical_bytes import canonical_file_digest  # noqa: PLC0415

    if not canonical_commit or len(canonical_commit) != 40:
        raise D003Error("canonical source commit identity invalid")
    if not tooling_commit or len(tooling_commit) != 40:
        raise D003Error("tooling commit identity invalid")
    try:
        tooling_fingerprint = canonical_file_digest(
            _TOOLING_RELPATH,
            commit=tooling_commit,
            repo=_REPO_ROOT,
            blob_source=(
                blob_source if blob_source is not None else _canonical_blob_source()
            ),
        )
    except Exception as exc:  # fail closed: no worktree/normalized fallback
        raise D003Error(f"D003 tooling fingerprint unresolvable: {exc}") from exc
    blob = json.dumps(store_identity, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        **PROVENANCE,
        "canonical_source_commit_used": canonical_commit,
        "tooling_commit": tooling_commit,
        "tooling_fingerprint": tooling_fingerprint,
        "fold_store_identity_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "generated_at_utc": generated_at or _iso(datetime.now(timezone.utc)),
    }


def _reject_banned_metrics(node: Any, path: str = "document") -> None:
    """Structurally refuse any prohibited metric key anywhere in the output.

    Exact-key bans and counterfactual-family substrings only, so honest
    negation/record keys (e.g. ``no_profitability_metrics``) pass while
    any real performance or counterfactual metric name is refused.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            key_text = str(key).lower()
            if key_text in BANNED_METRIC_KEYS or any(
                banned in key_text for banned in BANNED_METRIC_SUBSTRINGS
            ):
                raise D003Error(f"{REJECTED_D003_METRIC_KEY} {path}.{key}")
            _reject_banned_metrics(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_banned_metrics(value, f"{path}[{index}]")


def run_d003(
    store: Any,
    *,
    canonical_commit: str,
    tooling_commit: str,
    blob_source=None,
) -> tuple[dict[str, Any], bytes]:
    """Execute preregistered D003 over a loaded Fold-01 ``FoldFeatureStore``.

    Reuses D001's canonical classification, reference check, orchestration
    adapter, seed, carry, boundary-enforced snapshot iteration and
    accounting verbatim.  Fails closed on boundary, accounting or
    structural violations.  Returns ``(document, canonical_json_bytes)``.
    ``blob_source`` optionally injects the committed-byte reader used for
    the canonical tooling fingerprint (tests use a pure-Python Git object
    store; production resolves through real Git plumbing).
    """
    from bot.strategy.config import StrategyConfig  # noqa: PLC0415
    from bot.strategy.setup_state import (  # noqa: PLC0415
        StrategyState,
        record_from_state,
    )

    identity = store.identity
    if identity.get("fold_id") not in (None, "fold-01"):
        raise BoundaryError(f"store fold is not fold-01: {identity.get('fold_id')!r}")
    if identity.get("coverage") != "full":
        raise BoundaryError(f"store coverage is not full: {identity.get('coverage')!r}")

    config = StrategyConfig()
    seed_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    state_record = record_from_state(
        StrategyState(event_time=seed_time), event_at=seed_time,
    )
    buckets = {"missing_history": 0, "unavailable_input": 0, "evaluation_error": 0}
    bucket_statuses: dict[str, dict[str, int]] = {}
    rows: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    scheduled = 0
    for snapshot in _snapshot_rows(store):
        scheduled += 1
        bucket = classify_snapshot(snapshot)
        if bucket is not None:
            name, status = bucket
            buckets[name] += 1
            per_status = bucket_statuses.setdefault(name, {})
            per_status[status] = per_status.get(status, 0) + 1
            continue
        if _reference_check_failed(snapshot):
            buckets["evaluation_error"] += 1
            per_status = bucket_statuses.setdefault("evaluation_error", {})
            per_status["reference_check_failed"] = per_status.get("reference_check_failed", 0) + 1
            continue
        prior_state_record = state_record
        row, next_record = evaluate_orchestration_decision(
            snapshot, prior_state_record,
        )
        if row["action"] == "error":
            # Failed evaluation: classify and keep the prior state record so
            # subsequent decisions continue from the same carried state.
            buckets["evaluation_error"] += 1
            error_rows.append({
                "decision_id": row.get("decision_id"),
                "error_type": row.get("error_type"),
            })
            continue
        rows.append(row)
        # Read-only D003 augmentation of the successful decision; the
        # observer receives the exact causal PRIOR state record consumed by
        # the reducer for this decision — never the post-decision
        # ``next_record`` — for lifecycle/consumed-id semantics.  The
        # CURRENT decision's ``next_record`` is passed separately (TC003
        # §8) and is used read-only for flattened-field recovery only.
        observations.append(
            observe_decision(
                row,
                prior_state_record,
                snapshot=snapshot,
                config=config,
                decision_result_record=next_record,
            )
        )
        state_record = next_record
    reconcile_accounting(
        scheduled=scheduled,
        classified=len(rows),
        missing_history=buckets["missing_history"],
        unavailable_input=buckets["unavailable_input"],
        evaluation_error=buckets["evaluation_error"],
    )

    aggregate = aggregate_d003(observations)
    doc: dict[str, Any] = {
        "diagnostic_id": DIAGNOSTIC_ID,
        "classification": CLASSIFICATION,
        "label": LABEL,
        "specification_document": "docs/PHASE8_V2_DIAGNOSTIC_D003.md",
        "specification_sha256": SPECIFICATION_SHA256,
        "provenance": provenance(
            canonical_commit=canonical_commit,
            tooling_commit=tooling_commit,
            store_identity=dict(identity),
            blob_source=blob_source,
        ),
        "fold01_boundary": [FOLD01_START, FOLD01_END],
        "bucket_semantics": {
            "missing_history": "store gate_status=early_exit (session/news single-pass)",
            "unavailable_input": "store gate_status in {dxy_blocked, insufficient_data}",
            "evaluation_error": (
                "store gate_status=causal_input_unsafe or canonical orchestrator action=error"
            ),
        },
        "decision_accounting": {
            "scheduled": scheduled,
            "reducer_classified": len(rows),
            "missing_history": buckets["missing_history"],
            "unavailable_input": buckets["unavailable_input"],
            "evaluation_error": buckets["evaluation_error"],
            "missing_history_statuses": dict(sorted(bucket_statuses.get("missing_history", {}).items())),
            "unavailable_input_statuses": dict(sorted(bucket_statuses.get("unavailable_input", {}).items())),
            "evaluation_error_statuses": dict(sorted(bucket_statuses.get("evaluation_error", {}).items())),
            "reconciles": True,
        },
        "gate_funnel": _gate_funnel(rows),
        "evaluation_error_rows": error_rows,
        **aggregate,
        "budget_consumption_note": "2 / 12 diagnostics upon this first empirical execution",
        "reserved_evidence": {
            "fold_02_untouched": True,
            "fold_03_untouched": True,
            "fold_04_untouched": True,
            "holdout_untouched": True,
            "data_2025_plus_untouched": True,
        },
        "no_profitability_metrics": True,
        "no_other_configuration_scored": True,
    }
    _reject_banned_metrics(doc)
    assert_expected_surfaces(doc)
    return doc, _canonical(doc).encode("utf-8")


def assert_expected_surfaces(document: Mapping[str, Any]) -> None:
    """Structural verification of the exact preregistered surface."""
    required = (
        "decision_accounting",
        "gate_funnel",
        "B_frozen_score_components",
        "C_discriminating_contingency",
        "D_canonical_ob_lifecycle",
        "E_acquisition_canonical_agreement",
        "F_canonical_failure_reasons",
        "G_contextual_fvg_coexistence",
        "H_premium_discount_context",
    )
    missing = [key for key in required if key not in document]
    if missing:
        raise D003Error(f"preregistered surface missing: {missing}")
    lifecycle = document["D_canonical_ob_lifecycle"]
    if (
        lifecycle["eligible_count"] + lifecycle["non_eligible_count"]
        != document["gate11_entrants"]
    ):
        raise D003Error("lifecycle eligibility does not partition the entrants")
    accounting = document["decision_accounting"]
    if (
        accounting["reducer_classified"]
        + accounting["missing_history"]
        + accounting["unavailable_input"]
        + accounting["evaluation_error"]
        != accounting["scheduled"]
    ):
        raise D003Error("decision accounting does not reconcile")


def write_result(
    document: Mapping[str, Any],
    rendered: bytes,
    output_dir: Path,
) -> tuple[Path, str]:
    """Atomically write the deterministic result; refuse overwrite.

    Reuses the MR001 boundary scanner (``reject_holdout_path``) for the
    output path, exactly like the V001 tooling.
    """
    from backtests.phase8_v2_variant_v001_eval import reject_holdout_path  # noqa: PLC0415

    output_dir = Path(output_dir)
    reject_holdout_path(str(output_dir))
    target = output_dir / "phase8-v2-D003_result.json"
    if target.exists():
        raise D003Error(f"result already exists; refusing overwrite: {target}")
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = output_dir / f".staging-{uuid.uuid4().hex[:8]}"
    staging.write_bytes(rendered)
    import os  # noqa: PLC0415

    os.replace(staging, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != hashlib.sha256(rendered).hexdigest():
        raise D003Error("result hash mismatch after write")
    return target, digest
