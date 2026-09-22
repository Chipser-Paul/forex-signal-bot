"""Preregistered V2 diagnostic D001 tooling (phase8-v2-D001).

Frozen OB/FVG Structural Attrition Decomposition.

DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE

Governance
----------
* Charter:                 phase8-v2-research-charter-v1-8527e3a5eec98f53
* Charter SHA-256:         8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc
* Research identity:       phase6-development-v2
* Preregistration commit:  8985fb2f8396a999dbddcc8b51342788823dc2c2
* Provenance correction:   phase8-v2-PC001
* Specification:           docs/PHASE8_V2_DIAGNOSTIC_D001.md
  (status REGISTERED_NOT_EXECUTED at tooling time; the first successful
  empirical execution consumes 1 / 12 diagnostic investigations)

Canonical semantic reuse (nothing is redefined here)
----------------------------------------------------
* decisions are classified and evaluated exactly like the empirical
  reference pipeline: ``bot.validation.market_feature_store.
  evaluate_orchestration_from_features`` runs canonical gates 1-7 plus the
  untouched frozen reducer ``bot.state.gate_reducer.evaluate_strategy_gates``
  (gates 8-13), with cell-local state carry identical to the production
  runner (``bot.validation.empirical_input_pipeline._ReplayContext``:
  seed ``StrategyState(event_time=2024-01-01Z)``, sequential record carry,
  ``max_concurrent_trades=2``, ``active_trade_count=0``);
* gate names, gate order and reasons are read from the reducer's persisted
  render (``state_record.data()["last_result"]``) — never renamed;
* ``bot.execution.confluence_scorer.score_setup`` remains the scoring
  authority; the production overlap boolean is read from its canonical
  check label "FVG overlaps the order block zone".

The only computed geometry is ``mirror_fvg_in_ob``: a read-only
explanatory mirror of the exact gate-11 overlap expression in
``bot/state/gate_reducer.py`` (tolerance ``atr * 0.30``; gap
``fvg_low - ob_high`` / ``ob_low - fvg_high`` / else ``0.0``; pass when
``gap <= tolerance``).  It reproduces the production boolean and adds the
preregistered descriptive quantities (D001 spec section 3.F).  Equivalence
is proven against production behaviour in
``tests/test_phase8_v2_d001_tooling.py``; any disagreement fails closed
(:class:`MirrorMismatch`) *before* any aggregation is emitted.

Absolutely preregistered boundaries (specification sections 5, 8 and 13):

* no alternative-overlap, proximity, sequential-association or 7/8
  counterfactual candidate counts of any kind;
* no fills, closed trades, P&L, win rate, expectancy, profit factor,
  drawdown, Sharpe or return distributions;
* no threshold search and no candidate-count-versus-distance curves;
* no OB-to-FVG temporal-distance analysis (H003 is NOT tested here);
* Fold 01 only: ``[2024-04-01T00:00:00Z, 2024-06-08T00:00:00Z)``;
* Folds 02-04, 2025+ data and holdout are unreachable by construction.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

__all__ = [
    "DIAGNOSTIC_ID",
    "CLASSIFICATION",
    "LABEL",
    "FOLD01_START",
    "FOLD01_END",
    "D001Error",
    "BoundaryError",
    "ReconciliationError",
    "MirrorMismatch",
    "PROVENANCE",
    "provenance",
    "mirror_fvg_in_ob",
    "reconcile_accounting",
    "evaluate_orchestration_decision",
    "run_d001",
]

DIAGNOSTIC_ID = "phase8-v2-D001"
CLASSIFICATION = "DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE"
LABEL = CLASSIFICATION

#: Preregistered Fold-01 evaluation boundary (canonical fold definitions).
FOLD01_START = "2024-04-01T00:00:00+00:00"
FOLD01_END = "2024-06-08T00:00:00+00:00"

#: Canonical gate order (frozen reducer); recorded verbatim, never renamed.
GATE_ORDER = (
    "gate_8_liquidity",
    "gate_9_displacement",
    "gate_10_internal_structure",
    "gate_11_confluence_score",
    "canonical_strategy",
    "gate_12_13_rr_entry",
)

#: Canonical scored confluence labels (bot/execution/confluence_scorer.py).
SCORE_LABELS = (
    "HTF bias aligns with trade direction",
    "Price located in premium/discount zone",
    "Valid order block present",
    "FVG overlaps the order block zone",
    "Liquidity sweep occurred before entry",
)
OVERLAP_LABEL = "FVG overlaps the order block zone"

PROVENANCE = {
    "diagnostic_id": DIAGNOSTIC_ID,
    "research_identity": "phase6-development-v2",
    "charter_identity": "phase8-v2-research-charter-v1-8527e3a5eec98f53",
    "charter_sha256": "8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc",
    "hypothesis_ids": ["phase8-v2-H001", "phase8-v2-H002"],
    "registered_later_direction_not_tested": ["phase8-v2-H003"],
    "preregistration_commit": "8985fb2f8396a999dbddcc8b51342788823dc2c2",
    "provenance_correction": "phase8-v2-PC001",
    "fingerprint_contract": "canonical_git_blob_v1",
    "fold01_boundary": [FOLD01_START, FOLD01_END],
    "classification": CLASSIFICATION,
}


class D001Error(RuntimeError):
    """D001 scientific/provenance violation (fail closed)."""


class BoundaryError(D001Error):
    """Fold-boundary or data-boundary violation."""


class ReconciliationError(D001Error):
    """Decision accounting does not reconcile."""


class MirrorMismatch(D001Error):
    """Explanatory mirror disagrees with production semantics."""


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def provenance(
    *,
    canonical_commit: str,
    tooling_commit: str,
    store_identity: Mapping[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Provenance block bound to this tooling run (fail closed)."""
    if not canonical_commit or len(canonical_commit) != 40:
        raise D001Error("canonical source commit identity invalid")
    if not tooling_commit or len(tooling_commit) != 40:
        raise D001Error("tooling commit identity invalid")
    blob = json.dumps(store_identity, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        **PROVENANCE,
        "canonical_source_commit_used": canonical_commit,
        "tooling_commit": tooling_commit,
        "tooling_fingerprint": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fold_store_identity_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "generated_at_utc": generated_at or _iso(datetime.now(timezone.utc)),
    }


def mirror_fvg_in_ob(
    fvg: Mapping[str, Any] | None,
    ob_zone: Iterable[float] | None,
    atr: float,
) -> tuple[bool, dict[str, Any]]:
    """Read-only explanatory mirror of the exact gate-11 overlap geometry.

    Production expression (``bot/state/gate_reducer.py``, gate 11)::

        tolerance = atr * 0.30
        gap = fvg_low - ob_high if fvg_low > ob_high
              else ob_low - fvg_high if fvg_high < ob_low
              else 0.0
        fvg_in_ob = gap <= tolerance

    Returns the identical boolean plus the preregistered descriptive
    quantities (intersection flag, containment flag, signed/absolute
    separation, region widths).  Never evaluates an alternative rule.
    """
    geometry: dict[str, Any] = {
        "intersection": None,
        "containment": None,
        "signed_separation": None,
        "absolute_separation": None,
        "fvg_width": None,
        "ob_width": None,
    }
    if not fvg or not ob_zone:
        return False, geometry
    try:
        tolerance = atr * 0.30
        fvg_low, fvg_high = float(fvg["bottom"]), float(fvg["top"])
        ob_low, ob_high = float(ob_zone[0]), float(ob_zone[1])
    except (TypeError, ValueError, KeyError, IndexError):
        return False, geometry
    gap = (
        fvg_low - ob_high if fvg_low > ob_high
        else ob_low - fvg_high if fvg_high < ob_low
        else 0.0
    )
    decision = bool(gap <= tolerance)
    geometry["intersection"] = bool(gap == 0.0)
    geometry["containment"] = bool(ob_low <= fvg_low and fvg_high <= ob_high)
    geometry["signed_separation"] = float(gap)
    geometry["absolute_separation"] = float(abs(gap))
    geometry["fvg_width"] = float(fvg_high - fvg_low)
    geometry["ob_width"] = float(ob_high - ob_low)
    return decision, geometry


def reconcile_accounting(
    *, scheduled: int, classified: int, missing_history: int,
    unavailable_input: int, evaluation_error: int,
) -> None:
    """Fail closed unless every scheduled decision is classified exactly once."""
    total = classified + missing_history + unavailable_input + evaluation_error
    if total != scheduled:
        raise ReconciliationError(
            f"accounting mismatch: {classified}+{missing_history}+"
            f"{unavailable_input}+{evaluation_error} != {scheduled}"
        )


def _decision_datetime(available_at_ms: int) -> datetime:
    """Canonical decision-time conversion (empirical_input_pipeline)."""
    return datetime.fromtimestamp(available_at_ms / 1000, tz=timezone.utc)


def classify_snapshot(snapshot: Any) -> tuple[str, str] | None:
    """Preregistered store-row classification (canonical decision tree).

    Returns ``(bucket, canonical_reason)`` for rows that never reach the
    frozen reducer, or ``None`` for reducer-path rows.  Mirrors
    ``evaluate_orchestration_from_features`` and the store's own
    ``gate_status`` semantics:

    * ``early_exit``            -> missing_history (session/news single-pass)
    * ``dxy_blocked``           -> unavailable_input
    * ``insufficient_data``     -> unavailable_input
    * ``causal_input_unsafe``   -> evaluation_error
    """
    status = snapshot.gate_status
    if status == "early_exit":
        return ("missing_history", status)
    if status in ("dxy_blocked", "insufficient_data"):
        return ("unavailable_input", status)
    if status == "causal_input_unsafe":
        return ("evaluation_error", status)
    if status != "ok":
        raise D001Error(f"unknown canonical gate status: {status!r}")
    if snapshot.gate_payload is None:
        raise D001Error("gate status ok without a persisted gate payload")
    return None


def _reference_check_failed(snapshot: Any) -> bool:
    """True when the scenario-invariant single-pass reference check failed.

    The empirical pipeline skips such rows before any decision is made;
    D001 classifies them as ``evaluation_error`` (input reference failed)
    so accounting still reconciles over every scheduled decision.
    """
    return not bool(getattr(snapshot, "check_passes", True))


def evaluate_orchestration_decision(
    snapshot: Any,
    prior_state_record: Any,
    *,
    max_concurrent_trades: int = 2,
) -> tuple[dict[str, Any], Any]:
    """One canonical decision through the production orchestrator path.

    Calls ``evaluate_orchestration_from_features`` verbatim (gates 1-7 plus
    the frozen reducer) with the cell-local state carry used by the
    empirical reference pipeline.  Returns ``(row, next_state_record)``;
    ``next_state_record`` must be carried into the next decision exactly
    like ``context.state_record`` in the production runner.
    """
    from bot.validation.market_feature_store import (  # noqa: PLC0415
        evaluate_orchestration_from_features,
    )

    decision_at = _decision_datetime(int(snapshot.available_at_ms))
    try:
        decision, next_record = evaluate_orchestration_from_features(
            snapshot,
            decision_at=decision_at,
            prior_state=prior_state_record,
            active_trade_count=0,
            max_concurrent_trades=max_concurrent_trades,
        )
    except Exception as error:  # noqa: BLE001 — the canonical orchestrator
        # wraps its own errors into action="error"; any residual failure
        # must also be CLASSIFIED (section 3.A), never crash the audit.
        return {
            "decision_id": snapshot.gate_event_id or f"row-{int(snapshot.available_at_ms)}",
            "available_at_ms": int(snapshot.available_at_ms),
            "action": "error",
            "reason": "orchestrator_input_unsafe",
            "state_name": "unknown",
            "error_type": type(error).__name__,
        }, prior_state_record
    context: dict[str, Any] = dict(decision.context)
    row: dict[str, Any] = {
        "decision_id": snapshot.gate_event_id or f"row-{int(snapshot.available_at_ms)}",
        "available_at_ms": int(snapshot.available_at_ms),
        "action": decision.action,
        "reason": decision.reason,
        "state_name": decision.state_name,
    }
    if decision.action == "error":
        row["error_type"] = context.get("error_type")
        return row, next_record

    # Recover the reducer's persisted render for THIS decision (canonical
    # gate_results + context).  Fail closed on any provenance mismatch.
    if next_record is None:
        raise D001Error(f"reducer decision without persisted state record at {row['decision_id']}")
    data = next_record.data()
    if data.get("last_event_id") != snapshot.gate_event_id:
        raise D001Error(
            f"state record event mismatch at {row['decision_id']}: "
            f"{data.get('last_event_id')!r}"
        )
    rendered = data.get("last_result")
    if not rendered:
        raise D001Error(f"reducer result not persisted at {row['decision_id']}")
    gate = json.loads(rendered)
    row["gate_results"] = {
        name: bool(gate["gate_results"][name]["pass"])
        for name in GATE_ORDER if name in gate.get("gate_results", {})
    }
    gate_context: dict[str, Any] = gate.get("context") or {}

    # --- OB decomposition (canonical ob_result state; H002 surface) --------
    ob = gate_context.get("ob") or {}
    ob_zone = ob.get("zone") if ob.get("valid") else None
    htf_bias = (gate_context.get("bias_resolution") or {}).get("direction")
    row["ob"] = {
        "present": bool(ob),
        "valid": bool(ob.get("valid")),
        # detect_ob_breaker is invoked with structure_dir == htf_bias, so the
        # canonical OB search direction is the resolved HTF bias.
        "direction": htf_bias,
        "type": ob.get("type"),
        "reason": ob.get("reason"),
        "zone_low": float(ob_zone[0]) if ob_zone is not None else None,
        "zone_high": float(ob_zone[1]) if ob_zone is not None else None,
        "distance_atr": ob.get("distance_atr"),
        "mitigated": ob.get("mitigated"),
        "in_pd_zone": ob.get("in_pd_zone"),
    }

    # --- FVG decomposition (canonical displacement/fvgs state) -------------
    displacement = gate_context.get("displacement") or {}
    fvgs = gate_context.get("fvgs") or []
    first_fvg = fvgs[0] if fvgs else None
    row["fvg"] = {
        "present": bool(first_fvg),
        "count": len(fvgs),
        "displacement_valid": bool(displacement.get("valid")),
        "direction": first_fvg.get("direction") if isinstance(first_fvg, dict) else None,
    }

    # --- confluence decomposition (canonical scorer checks) ----------------
    score = gate_context.get("score") or {}
    checks = score.get("checks") or []
    row["score"] = {
        "score": score.get("score"),
        "max_score": score.get("max_score"),
        "grade": score.get("grade"),
        "min_score_to_trade": score.get("min_score_to_trade"),
        "passes_threshold": bool(score.get("passes_threshold")),
        "checks_passed": {
            str(check.get("label")): bool(check.get("passed")) for check in checks
        },
    }

    # --- canonical overlap boolean + mirrored geometry (H001 surface) ------
    atr = float((gate.get("market_conditions") or {}).get("atr") or 0.0)
    mirror_decision, geometry = mirror_fvg_in_ob(first_fvg, ob_zone, atr)
    production_overlap = row["score"]["checks_passed"].get(OVERLAP_LABEL)
    if production_overlap is not None and bool(production_overlap) != mirror_decision:
        raise MirrorMismatch(
            f"mirror/production overlap disagreement at {row['decision_id']}"
        )
    row["overlap"] = {
        "canonical_fvg_in_ob": (
            bool(production_overlap) if production_overlap is not None else mirror_decision
        ),
        "production_overlap_available": production_overlap is not None,
        **geometry,
    }

    # --- direction consistency (production-derived, no assumptions) --------
    # A present OB was searched with structure_dir == htf_bias, so it is
    # direction-consistent by construction unless the canonical legacy
    # decision records ORDER_BLOCK_DIRECTION_CONFLICT.
    strategy_decision = gate_context.get("strategy_decision") or {}
    reasons = [str(reason) for reason in (strategy_decision.get("reasons") or [])]
    if not ob:
        row["direction"] = "undefined_no_ob"
    elif "ORDER_BLOCK_DIRECTION_CONFLICT" in reasons:
        row["direction"] = "opposite"
    else:
        row["direction"] = "same"
    return row, next_record


def _snapshot_rows(store: Any):
    """Iterate the store table as verified snapshots (canonical machinery).

    Enforces the preregistered Fold-01 M5 decision boundary on the store
    identity and on every row (fail closed).
    """
    from bot.validation.market_feature_store import (  # noqa: PLC0415
        _snapshot_from_row,
    )

    identity = store.identity
    if identity.get("decision_timeframe") != "M5":
        raise BoundaryError(
            f"store decision timeframe is not M5: {identity.get('decision_timeframe')!r}"
        )
    expected_start = int(datetime.fromisoformat(FOLD01_START).timestamp() * 1000)
    expected_end = int(datetime.fromisoformat(FOLD01_END).timestamp() * 1000)
    if int(identity["evaluation_start_ms"]) != expected_start or int(
        identity["evaluation_end_ms"]
    ) != expected_end:
        raise BoundaryError(
            "store evaluation window is not Fold 01: "
            f"[{identity.get('evaluation_start_ms')}, {identity.get('evaluation_end_ms')})"
        )
    for position in range(store.table.num_rows):
        row = {
            name: store.table.column(name)[position].as_py()
            for name in store.table.column_names
        }
        available_at_ms = int(row["available_at_ms"])
        if not expected_start <= available_at_ms < expected_end:
            raise BoundaryError(f"decision outside Fold 01 boundary: {available_at_ms}")
        yield _snapshot_from_row(row)


def _summary(values: list[float]) -> dict[str, Any]:
    """Preregistered descriptive summary: count/min/max/median/quartiles."""
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    n = len(ordered)

    def q(p: float) -> float:
        if n == 1:
            return ordered[0]
        position = p * (n - 1)
        low = int(position)
        high = min(low + 1, n - 1)
        weight = position - low
        return ordered[low] * (1 - weight) + ordered[high] * weight

    return {
        "count": n,
        "min": ordered[0],
        "max": ordered[-1],
        "median": q(0.5),
        "q1": q(0.25),
        "q3": q(0.75),
    }


def _aggregate(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    actions: dict[str, int] = {}
    reasons: dict[str, int] = {}
    funnel: dict[str, dict[str, Any]] = {}
    ob_type: dict[str, int] = {}
    ob_reason: dict[str, int] = {}
    ob_direction: dict[str, int] = {}
    ob_conditions: dict[str, int] = {"mitigated_true": 0, "in_pd_zone_true": 0}
    fvg_direction: dict[str, int] = {}
    score_distribution: dict[str, int] = {}
    score_checks: dict[str, dict[str, int]] = {
        label: {"passed": 0, "failed": 0} for label in SCORE_LABELS
    }
    directions = {"same": 0, "opposite": 0, "undefined_no_ob": 0}
    contingency: dict[str, int] = {}
    geometry: list[dict[str, Any]] = []
    overlap_true = 0
    for row in rows:
        actions[str(row["action"])] = actions.get(str(row["action"]), 0) + 1
        reasons[str(row["reason"])] = reasons.get(str(row["reason"]), 0) + 1
        for name, passed in row.get("gate_results", {}).items():
            slot = funnel.setdefault(name, {"entered": 0, "passed": 0, "failed": 0})
            slot["entered"] += 1
            slot["passed" if passed else "failed"] += 1
        ob = row["ob"]
        ob_type[str(ob.get("type"))] = ob_type.get(str(ob.get("type")), 0) + 1
        ob_reason[str(ob.get("reason"))] = ob_reason.get(str(ob.get("reason")), 0) + 1
        ob_direction[str(ob.get("direction"))] = ob_direction.get(str(ob.get("direction")), 0) + 1
        if ob.get("mitigated") is True:
            ob_conditions["mitigated_true"] += 1
        if ob.get("in_pd_zone") is True:
            ob_conditions["in_pd_zone_true"] += 1
        fvg = row["fvg"]
        fvg_direction[str(fvg.get("direction"))] = fvg_direction.get(str(fvg.get("direction")), 0) + 1
        score = row["score"]
        score_value = score.get("score")
        if score_value is not None:
            # Only decisions that reached confluence scoring carry a score;
            # early-exit rows legitimately have none and are excluded from
            # the distribution (they remain in the action/reason counts).
            score_distribution[str(score_value)] = (
                score_distribution.get(str(score_value), 0) + 1
            )
        for label, passed in score.get("checks_passed", {}).items():
            bucket = score_checks.setdefault(label, {"passed": 0, "failed": 0})
            bucket["passed" if passed else "failed"] += 1
        directions[str(row["direction"])] = directions.get(str(row["direction"]), 0) + 1
        key = (
            f"valid_ob={str(bool(ob.get('valid')))}/"
            f"fvg_present={str(bool(fvg.get('present')))}/"
            f"overlap={str(bool(row['overlap']['canonical_fvg_in_ob']))}"
        )
        contingency[key] = contingency.get(key, 0) + 1
        if row["overlap"]["canonical_fvg_in_ob"]:
            overlap_true += 1
        # Section 3.F population: both relevant regions must EXIST
        # (a valid OB zone and a present FVG) — an invalidated OB has no
        # region and must not enter the geometry observations.
        if ob.get("valid") and fvg.get("present"):
            geometry.append({
                key_: row["overlap"][key_]
                for key_ in (
                    "intersection", "containment", "signed_separation",
                    "absolute_separation", "fvg_width", "ob_width",
                )
            })
    for name, slot in funnel.items():
        entered = slot["entered"] or 1
        slot["pass_rate"] = round(slot["passed"] / entered, 6)
        slot["failure_rate"] = round(slot["failed"] / entered, 6)
    return {
        "actions": dict(sorted(actions.items())),
        "reasons": dict(sorted(reasons.items())),
        "gate_funnel": {name: funnel[name] for name in GATE_ORDER if name in funnel},
        "ob_type_counts": dict(sorted(ob_type.items())),
        "ob_reason_counts": dict(sorted(ob_reason.items())),
        "ob_direction_counts": dict(sorted(ob_direction.items())),
        "ob_condition_counts": ob_conditions,
        "fvg_direction_counts": dict(sorted(fvg_direction.items())),
        "score_distribution": dict(sorted(
            score_distribution.items(), key=lambda item: float(item[0])
        )),
        "score_check_pass_counts": {
            label: score_checks[label] for label in SCORE_LABELS if label in score_checks
        },
        "direction_consistency": directions,
        "ob_x_fvg_x_overlap_counts": dict(sorted(contingency.items())),
        "overlap_true_decisions": overlap_true,
        "overlap_geometry_observations": geometry,
    }


def run_d001(store: Any, *, canonical_commit: str, tooling_commit: str) -> tuple[dict[str, Any], bytes]:
    """Execute preregistered D001 over a loaded Fold-01 ``FoldFeatureStore``.

    Fail-closed on: boundary mismatch, store coverage/fold mismatch,
    accounting non-reconciliation, mirror/production disagreement, missing
    reducer renders.  Returns ``(document, canonical_json_bytes)``.
    """
    from bot.strategy.setup_state import (  # noqa: PLC0415
        StrategyState,
        record_from_state,
    )

    identity = store.identity
    if identity.get("fold_id") not in (None, "fold-01"):
        raise BoundaryError(f"store fold is not fold-01: {identity.get('fold_id')!r}")
    if identity.get("coverage") != "full":
        raise BoundaryError(f"store coverage is not full: {identity.get('coverage')!r}")

    seed_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    state_record = record_from_state(
        StrategyState(event_time=seed_time), event_at=seed_time,
    )
    buckets = {
        "missing_history": 0,
        "unavailable_input": 0,
        "evaluation_error": 0,
    }
    bucket_statuses: dict[str, dict[str, int]] = {}
    rows: list[dict[str, Any]] = []
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
        row, next_record = evaluate_orchestration_decision(snapshot, state_record)
        if row["action"] == "error":
            # Failed evaluation: classify and keep the prior state record so
            # subsequent decisions continue from the same carried state.
            buckets["evaluation_error"] += 1
            error_rows.append({
                "decision_id": row["decision_id"],
                "error_type": row.get("error_type"),
            })
            continue
        state_record = next_record
        rows.append(row)
    reconcile_accounting(
        scheduled=scheduled,
        classified=len(rows),
        missing_history=buckets["missing_history"],
        unavailable_input=buckets["unavailable_input"],
        evaluation_error=buckets["evaluation_error"],
    )
    agg = _aggregate(rows)
    geometry_rows = agg["overlap_geometry_observations"]
    doc: dict[str, Any] = {
        "diagnostic_id": DIAGNOSTIC_ID,
        "classification": CLASSIFICATION,
        "label": LABEL,
        "provenance": None,  # filled by the caller (binds the tooling commit)
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
        },
        "orchestrator_errors": error_rows,
        "results": agg,
        "descriptive_summaries": {
            "absolute_separation": _summary(
                [g["absolute_separation"] for g in geometry_rows if g["absolute_separation"] is not None]
            ),
            "fvg_width": _summary(
                [g["fvg_width"] for g in geometry_rows if g["fvg_width"] is not None]
            ),
            "ob_width": _summary(
                [g["ob_width"] for g in geometry_rows if g["ob_width"] is not None]
            ),
        },
        "h001_disposition": None,  # assigned by the analyst, not the tooling
        "h002_disposition": None,
        "h003_status": "NOT_TESTED_BY_D001",
        "prohibited_outputs_check": "none emitted (see module docstring)",
    }
    payload = json.dumps(doc, sort_keys=True, indent=1, allow_nan=False).encode("utf-8")
    return doc, payload
