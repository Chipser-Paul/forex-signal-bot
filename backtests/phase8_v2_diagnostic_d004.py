"""Preregistered V2 diagnostic D004 tooling (phase8-v2-D004).

Frozen Expired Order-Block Structural Fate Decomposition.

DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE

Governance
----------
* Charter:           phase8-v2-research-charter-v1-8527e3a5eec98f53
* Charter SHA-256:   8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc
* Research identity: phase6-development-v2
* Preregistration:   docs/PHASE8_V2_DIAGNOSTIC_D004.md (Phase-A commit
  e37b522238ad1b7b2548da75055080832f4099b6), register records
  ``phase8-v2-H006`` (REGISTERED) and ``phase8-v2-D004``
  (REGISTERED_NOT_EXECUTED).
* Motivation only: D003 R001 (H002 SUPPORTED_BY_D003) motivates this
  diagnostic; no observed D003 count is used as a target, expectation or
  oracle, and H002 is never reopened.

Scope (frozen)
--------------
Empirical universe (future authorized execution only): TIER_A_FOLD01,
preserved V001 store ``fold-01-a8b406884ab3525a``.  Primary population:
Gate-11 entrants (the exact D003 observer loop, reused verbatim) whose
frozen canonical ``evaluate_order_block`` classification is
``BlockState.EXPIRED`` with a confirmed same-side block.  Reference
populations ELIGIBLE / RETEST_ELIGIBLE / MITIGATED / INVALIDATED carry the
same descriptive predicates (UNAVAILABLE is counted but has no geometry).

Preregistered surfaces: read-only fate predicates; fate categories as RAW
predicate counts (overlap allowed, never called eligible); the exact
post-confirmation age histogram (never an alternative threshold); final
canonical FVG context via the frozen D001 mirror geometry (no
redetection); the fate x FVG x direction x overlap contingency; and
reference-population predicates labeled by canonical BlockState.

Causality: only candles with ``available_at <= decision_at`` are ever
inspected — the exact frozen ``evaluate_order_block`` causality filter —
and the setup-state chain follows the D003/TC001 discipline (the observer
receives the causal PRIOR state record; the current decision's
``next_record`` is used read-only for render reconciliation only).

Absolutely prohibited (structural output guard): pnl, profit, fills,
closed trades, win rate, expectancy, drawdown, Sharpe, returns,
alternate-expiry surfaces (expiry_31/40/45/60/90, no-expiry),
counterfactual candidates, candidate_if_expiry_removed,
eligible_without_expiry, temporal lags.  Deterministic; fails closed on
any accounting, provenance, consumption, reconciliation or structural
violation.  No MT5, no trading, no holdout, no 2025+ data.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

# Reuse the validated D003/D001 infrastructure verbatim: the frozen D001
# classification/adapter/accounting contracts and the D003 canonical
# lifecycle observer patterns (TC001 prior-state discipline included).
from backtests.phase8_v2_diagnostic_d001 import (  # noqa: E402
    CLASSIFICATION,
    FOLD01_END,
    FOLD01_START,
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
from backtests.phase8_v2_diagnostic_d003 import (  # noqa: E402
    _reconcile_decision_render,
    canonical_ob_frame,
    canonical_ob_lifecycle as _d003_canonical_ob_lifecycle,
    consumed_ids_from_record,  # re-exported reuse (reducer-exact derivation)
    observe_decision as _d003_observe_decision,
    _semantic_direction,
)

__all__ = [
    "DIAGNOSTIC_ID",
    "LABEL",
    "SPECIFICATION_SHA256",
    "D004Error",
    "REJECTED_D004_METRIC_KEY",
    "assert_expected_surfaces",
    "aggregate_d004",
    "canonical_ob_lifecycle",
    "decompose_expired_block",
    "expired_fate_categories",
    "observe_decision",
    "provenance",
    "run_d004",
    "write_result",
]

DIAGNOSTIC_ID = "phase8-v2-D004"
LABEL = CLASSIFICATION
SPECIFICATION_SHA256 = "cededb5f495d142d5713f691eec8c9b7efb604082ca4b722f6cfb72881a86392"

PROVENANCE = {
    "diagnostic_id": DIAGNOSTIC_ID,
    "research_identity": "phase6-development-v2",
    "charter_identity": "phase8-v2-research-charter-v1-8527e3a5eec98f53",
    "charter_sha256": "8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc",
    "linked_hypothesis": "phase8-v2-H006",
    "contextual_prior": "phase8-v2-H002 = SUPPORTED_BY_D003",
    "not_reopened_hypotheses": [
        "phase8-v2-H001",
        "phase8-v2-H002",
        "phase8-v2-H003",
        "phase8-v2-H005",
    ],
    "specification_document": "docs/PHASE8_V2_DIAGNOSTIC_D004.md",
    "specification_sha256": SPECIFICATION_SHA256,
    "motivation_result_commit": "5f9b1e9e8dac9775bbf586174e94cfef039c23c0",
    "fingerprint_contract": "canonical_git_blob_v1",
    "fold01_boundary": [FOLD01_START, FOLD01_END],
    "classification": CLASSIFICATION,
}

REJECTED_D004_METRIC_KEY = "prohibited metric key"

# Repository root and tooling identity path for canonical_git_blob_v1
# fingerprints (established backtests convention: parents[1] of this file).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLING_RELPATH = "backtests/phase8_v2_diagnostic_d004.py"

# §31 banned-output guard: exact keys + semantic substring families in the
# established V001/D003 style.  Performance words stay EXACT-key only (so
# the honest negation key ``no_profitability_metrics`` passes); counter-
# factual and alternate-expiry families are substring-scanned.  Honest
# output keys in this module deliberately avoid every banned stem.
BANNED_METRIC_KEYS = frozenset(
    {
        "pnl", "profit", "profit_factor", "win_rate", "expectancy",
        "drawdown", "sharpe", "returns", "return", "closed_trades", "trades",
        "fills", "fill_count", "expiry_31", "expiry_40", "expiry_45",
        "expiry_60", "expiry_90", "alternate_expiry", "no_expiry",
        "candidate_if_expiry_removed", "eligible_without_expiry",
        "counterfactual_candidate",
    }
)
BANNED_METRIC_SUBSTRINGS = (
    "candidate_if_expiry_removed", "eligible_without_expiry",
    "alternate_expiry", "alternative_expiry", "alt_expiry",
    "if_expiry_removed", "without_expiry", "expiry_31", "expiry_40",
    "expiry_45", "expiry_60", "expiry_90", "counterfactual_",
    "temporal_lag", "temporal_fvg_lag", "lag_distribution",
    "threshold_curve", "would_pass_at", "pass_at_", "optimal_",
    "sweep_for_",
)

# Preregistered fate categories (raw predicate counts; overlap allowed
# except where definitions make categories exclusive).
EXPIRED_FATE_CATEGORIES = (
    "EXPIRED_UNTOUCHED",
    "EXPIRED_TOUCHED",
    "EXPIRED_INVALIDATED",
    "EXPIRED_FIRST_RETEST_AT_DECISION",
)

# Reference populations carrying the same descriptive predicates
# (UNAVAILABLE is counted but has no block geometry).
FATE_REFERENCE_STATES = (
    "ELIGIBLE",
    "RETEST_ELIGIBLE",
    "MITIGATED",
    "INVALIDATED",
)


class D004Error(D001Error):
    """D004 preregistered-contract violation (fail closed)."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def canonical_ob_lifecycle(
    snapshot: Any,
    *,
    htf_bias: str,
    prior_state_record: Any,
    config: Any,
) -> dict[str, Any]:
    """READ-ONLY canonical lifecycle evaluation for one causal decision.

    Semantics-preserving reuse of the D003 observer (TC001/TC003
    discipline included): reconstructs the reducer's exact inputs from
    already-persisted causal snapshot data (M5 ``entry_rows`` + persisted
    ``htf_bias`` + decision timestamp + frozen ``StrategyConfig`` +
    reducer-exact consumed ids from the causal PRIOR state record) and
    calls the frozen ``evaluate_order_block``.  Never mutates reducer
    state and never feeds its result back into strategy evaluation.
    """
    return _d003_canonical_ob_lifecycle(
        snapshot,
        htf_bias=htf_bias,
        prior_state_record=prior_state_record,
        config=config,
    )


def decompose_expired_block(
    snapshot: Any,
    *,
    decision_at: datetime,
    lifecycle: Mapping[str, Any],
    config: Any,
) -> dict[str, Any]:
    """Read-only fate decomposition of one canonically evaluated block.

    Reuses ``detect_order_blocks`` with the exact canonical selection
    ordering of ``evaluate_order_block`` and reconciles the analyzed
    block identity against the frozen canonical evaluation (block id and
    zone; any mismatch FAILS CLOSED — no parallel detector).  Only
    candles with ``available_at <= decision_at`` are inspected (the
    frozen evaluator's own causality filter).  For EXPIRED blocks the
    consumption invariant is asserted: a returned-EXPIRED block cannot be
    in the causal consumed set under frozen semantics (the evaluator
    checks consumed ids before its expiry short-circuit).
    """
    from bot.strategy.models import StrategySide  # noqa: PLC0415
    from bot.strategy.order_blocks import detect_order_blocks  # noqa: PLC0415

    side_value = str(lifecycle.get("side") or "")
    if side_value not in ("LONG", "SHORT"):
        raise D004Error(
            f"fate decomposition requires a directional block, got side {side_value!r}"
        )
    side = StrategySide[side_value]
    payload = json.loads(snapshot.gate_payload)
    frame = canonical_ob_frame(list(payload.get("entry_rows") or []))

    blocks = [block for block in detect_order_blocks(frame, config) if block.side is side]
    if not blocks:
        raise D004Error("block identity reconciliation failed: no same-side detected block")
    selected = sorted(
        blocks, key=lambda item: (item.confirmed_at, -item.zone_high + item.zone_low, item.block_id)
    )[-1]
    if lifecycle.get("block_id") is None or selected.block_id != lifecycle.get("block_id"):
        raise D004Error(
            "block identity reconciliation failed: detected block "
            f"{selected.block_id!r} != frozen canonical block {lifecycle.get('block_id')!r}"
        )
    if abs(selected.zone_low - float(lifecycle["zone_low"])) > 1e-9 or abs(
        selected.zone_high - float(lifecycle["zone_high"])
    ) > 1e-9:
        raise D004Error("block zone reconciliation failed against the frozen canonical evaluation")

    ordered = frame.sort_values("open_time", kind="mergesort").reset_index(drop=True)
    later = ordered.iloc[selected.confirmation_index + 1 :]
    later = later[pd_to_datetime(later["available_at"]) <= pd_to_timestamp(decision_at)]

    expiry_bars = int(config.order_block_expiry_bars)
    post_bars = int(len(later))
    first_overlap: int | None = None
    first_invalidating: int | None = None
    for position, (_index, candle) in enumerate(later.iterrows()):
        if first_overlap is None and (
            float(candle["low"]) <= selected.zone_high
            and float(candle["high"]) >= selected.zone_low
        ):
            first_overlap = position
        if first_invalidating is None:
            if side is StrategySide.LONG and float(candle["close"]) < selected.zone_low:
                first_invalidating = position
            elif side is StrategySide.SHORT and float(candle["close"]) > selected.zone_high:
                first_invalidating = position

    consumed = set(lifecycle.get("consumed_ids_derived") or [])
    expired = str(lifecycle.get("state")) == "EXPIRED"
    if expired and selected.block_id in consumed:
        raise D004Error(
            "consumption invariant violated: frozen canonical evaluation returned "
            f"EXPIRED for block {selected.block_id!r}, which the causal prior state "
            "record already consumed (the frozen evaluator checks consumed ids "
            "before expiry)"
        )

    return {
        "block_confirmed_at": _iso(selected.confirmed_at),
        "block_candidate_open_time": _iso(selected.candidate_open_time),
        "decision_at": _iso(decision_at),
        "post_confirmation_bars": post_bars,
        "bars_beyond_expiry_boundary": post_bars - expiry_bars,
        "zone_overlap_before_decision": first_overlap is not None,
        "first_zone_overlap_index": first_overlap,
        "invalidating_close": first_invalidating is not None,
        "first_invalidating_close_index": first_invalidating,
        "untouched_through_decision": first_overlap is None and first_invalidating is None,
        "first_retest_on_final_candle": bool(
            first_overlap is not None and first_overlap == post_bars - 1
        ),
        "block_side": side_value,
        "block_zone": {
            "zone_low": float(selected.zone_low),
            "zone_high": float(selected.zone_high),
        },
        "frozen_expiry_bars": expiry_bars,
        "block_already_consumed": bool(selected.block_id in consumed),
        "consumed_invariant_holds": True,
        "state": str(lifecycle.get("state")),
        "reason": str(lifecycle.get("reason")),
        "block_id": selected.block_id,
    }


def _pd():
    import pandas as pd  # noqa: PLC0415

    return pd


def pd_to_datetime(series: Any) -> Any:
    return _pd().to_datetime(series, utc=True)


def pd_to_timestamp(value: datetime) -> Any:
    return _pd().Timestamp(value)


def expired_fate_categories(fate: Mapping[str, Any]) -> dict[str, bool]:
    """Preregistered descriptive categories from raw predicates.

    Categories may overlap where mathematically unavoidable, except where
    definitions make them exclusive (UNTOUCHED excludes TOUCHED and
    INVALIDATED by construction).  No category is ever called eligible.
    """
    untouched = bool(fate["untouched_through_decision"])
    touched = bool(fate["zone_overlap_before_decision"])
    invalidated = bool(fate["invalidating_close"])
    return {
        "EXPIRED_UNTOUCHED": untouched,
        "EXPIRED_TOUCHED": touched,
        "EXPIRED_INVALIDATED": invalidated,
        "EXPIRED_FIRST_RETEST_AT_DECISION": bool(fate["first_retest_on_final_candle"]),
    }


def observe_decision(
    row: Mapping[str, Any],
    prior_state_record: Any,
    *,
    snapshot: Any,
    config: Any,
    decision_result_record: Any,
) -> dict[str, Any]:
    """Augment one successful D001 row with the D004 fate decomposition.

    Delegates the full D003 Gate-11 extraction/reconciliation (frozen row
    surfaces, score degeneracy/self-consistency fail-closed checks, render
    reconciliation) verbatim, then adds the read-only D004 surface: fate
    predicates/categories for every canonically-blocked entrant, the
    consumption invariant for EXPIRED blocks, and the final-FVG context
    computed with the frozen D001 mirror geometry over the block's
    canonical zone.  Strictly read-only relative to strategy evaluation.
    """
    gate_results = row.get("gate_results") or {}
    observation: dict[str, Any] = {
        "decision_id": row.get("decision_id"),
        "gate_10_pass": bool(gate_results.get("gate_10_internal_structure")),
        "gate_11_entered": "gate_11_confluence_score" in gate_results,
        "canonical_state": None,
        "fate": None,
        "fvg_context": None,
    }
    if not observation["gate_11_entered"]:
        return observation

    base = _d003_observe_decision(
        row,
        prior_state_record,
        snapshot=snapshot,
        config=config,
        decision_result_record=decision_result_record,
    )
    lifecycle = base["canonical_lifecycle"]
    state = str(lifecycle.get("state"))
    observation["canonical_state"] = state
    observation["final_fvg_present"] = bool(base.get("final_fvg_present"))
    observation["final_fvg_direction"] = base.get("final_fvg_direction")

    if state in ("EXPIRED",) + FATE_REFERENCE_STATES:
        decision_at = datetime.fromtimestamp(
            int(snapshot.available_at_ms) / 1000, tz=timezone.utc
        )
        fate = decompose_expired_block(
            snapshot, decision_at=decision_at, lifecycle=lifecycle, config=config,
        )
        observation["fate"] = fate
        observation["fate_categories"] = (
            expired_fate_categories(fate) if state == "EXPIRED" else None
        )

        # Final FVG context: the persisted first canonical FVG geometry
        # (recovered through D003's render reconciliation) against the
        # block's canonical zone with the SAME frozen mirror observer.
        score = row.get("score") or {}
        checks: dict[str, bool] = {}
        for label in SCORE_LABELS:
            value = (score.get("checks_passed") or {}).get(label)
            if value is None:
                raise D004Error(
                    "degenerate Gate-11 score surface at "
                    f"{row.get('decision_id')!r}: frozen check {label!r} missing"
                )
            checks[label] = bool(value)
        render = _reconcile_decision_render(row, decision_result_record, checks)
        first_fvg = render["raw_fvgs"][0] if render["raw_fvgs"] else None
        atr = float(render.get("atr") or 0.0)
        overlap_passed, geometry = mirror_fvg_in_ob(
            first_fvg,
            (float(lifecycle["zone_low"]), float(lifecycle["zone_high"])),
            atr,
        )
        block_semantic = _semantic_direction(lifecycle.get("side"))
        fvg_semantic = _semantic_direction(base.get("final_fvg_direction"))
        if not base.get("final_fvg_present") or fvg_semantic is None:
            agreement = "not_available"
        elif block_semantic is None:
            raise D004Error(
                "directional block with unresolvable semantic side at "
                f"{row.get('decision_id')!r}"
            )
        elif block_semantic == fvg_semantic:
            agreement = "agree"
        else:
            agreement = "disagree"
        observation["fvg_context"] = {
            "final_fvg_present": bool(base.get("final_fvg_present")),
            "raw_canonical_fvg_count": int((row.get("fvg") or {}).get("count") or 0),
            "direction_agreement": agreement,
            "canonical_overlap": bool(overlap_passed),
            "separation_geometry": geometry,
        }
    return observation


def _quantile(sorted_values: list[int], q: float) -> float:
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return float(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction)


def _age_summary(ages: list[int]) -> dict[str, Any]:
    ordered = sorted(ages)
    if not ordered:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "median": None,
            "histogram": {},
            "quantiles": {"p25": None, "p50": None, "p75": None},
        }
    histogram: dict[str, int] = {}
    for age in ordered:
        histogram[str(age)] = histogram.get(str(age), 0) + 1
    median = float(ordered[len(ordered) // 2]) if len(ordered) % 2 else _quantile(ordered, 0.5)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        "median": median,
        "histogram": dict(sorted(histogram.items())),
        "quantiles": {
            "p25": _quantile(ordered, 0.25),
            "p50": _quantile(ordered, 0.50),
            "p75": _quantile(ordered, 0.75),
        },
    }


def _empty_predicate_counts() -> dict[str, int]:
    return {
        "blocks": 0,
        "zone_overlap_before_decision": 0,
        "no_zone_overlap": 0,
        "invalidating_close": 0,
        "untouched_through_decision": 0,
        "first_retest_on_final_candle": 0,
    }


def _contingency_cell(fate: Mapping[str, Any], fvg: Mapping[str, Any]) -> str:
    agreement = str(fvg["direction_agreement"])
    overlap = str(fvg["canonical_overlap"]).lower() if fvg["final_fvg_present"] else "not_available"
    return (
        f"untouched={fate['untouched_through_decision']}"
        f"/touched={fate['zone_overlap_before_decision']}"
        f"/invalidated={fate['invalidating_close']}"
        f"/first_retest_final={fate['first_retest_on_final_candle']}"
        f"/fvg_present={fvg['final_fvg_present']}"
        f"/fvg_agreement={agreement}"
        f"/overlap={overlap}"
    )


def aggregate_d004(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Reduce Gate-11 observations into the preregistered D004 surfaces."""
    obs = [o for o in observations if o.get("gate_11_entered")]
    expired_categories: dict[str, int] = {name: 0 for name in EXPIRED_FATE_CATEGORIES}
    expired_predicates = _empty_predicate_counts()
    expired_ages: list[int] = []
    fvg_summary = {
        "expired_with_final_fvg": 0,
        "expired_without_final_fvg": 0,
        "direction_agreement": {"agree": 0, "disagree": 0, "not_available": 0},
        "canonical_overlap_true": 0,
        "canonical_overlap_false": 0,
    }
    contingency: dict[str, int] = {}
    reference: dict[str, dict[str, Any]] = {
        state: {"blocks": 0, "predicates": _empty_predicate_counts(), "ages": []}
        for state in FATE_REFERENCE_STATES
    }
    count_only_states: dict[str, int] = {}
    invariant_violations = 0
    for o in obs:
        state = o.get("canonical_state")
        if state is None:
            raise D004Error(f"Gate-11 entrant {o.get('decision_id')!r} lacks a canonical state")
        fate = o.get("fate")
        if fate is None:
            count_only_states[str(state)] = count_only_states.get(str(state), 0) + 1
            continue
        if not fate.get("consumed_invariant_holds"):
            invariant_violations += 1
        ages = fate["post_confirmation_bars"]
        if str(state) == "EXPIRED":
            expired_predicates["blocks"] += 1
            expired_ages.append(int(ages))
            for name, flag in o["fate_categories"].items():
                if flag:
                    expired_categories[name] += 1
            if fate["zone_overlap_before_decision"]:
                expired_predicates["zone_overlap_before_decision"] += 1
            else:
                expired_predicates["no_zone_overlap"] += 1
            expired_predicates["invalidating_close"] += int(bool(fate["invalidating_close"]))
            expired_predicates["untouched_through_decision"] += int(
                bool(fate["untouched_through_decision"])
            )
            expired_predicates["first_retest_on_final_candle"] += int(
                bool(fate["first_retest_on_final_candle"])
            )
            fvg = o.get("fvg_context") or {}
            if fvg.get("final_fvg_present"):
                fvg_summary["expired_with_final_fvg"] += 1
                fvg_summary["direction_agreement"][str(fvg["direction_agreement"])] += 1
                if fvg.get("canonical_overlap"):
                    fvg_summary["canonical_overlap_true"] += 1
                else:
                    fvg_summary["canonical_overlap_false"] += 1
            else:
                fvg_summary["expired_without_final_fvg"] += 1
                fvg_summary["direction_agreement"]["not_available"] += 1
            cell = _contingency_cell(fate, fvg)
            contingency[cell] = contingency.get(cell, 0) + 1
        elif str(state) in reference:
            bucket = reference[str(state)]
            bucket["blocks"] += 1
            bucket["ages"].append(int(ages))
            bucket["predicates"]["blocks"] += 1
            bucket["predicates"]["zone_overlap_before_decision"] += int(
                bool(fate["zone_overlap_before_decision"])
            )
            bucket["predicates"]["no_zone_overlap"] += int(
                not bool(fate["zone_overlap_before_decision"])
            )
            bucket["predicates"]["invalidating_close"] += int(bool(fate["invalidating_close"]))
            bucket["predicates"]["untouched_through_decision"] += int(
                bool(fate["untouched_through_decision"])
            )
            bucket["predicates"]["first_retest_on_final_candle"] += int(
                bool(fate["first_retest_on_final_candle"])
            )
        else:
            count_only_states[str(state)] = count_only_states.get(str(state), 0) + 1
    if invariant_violations:
        raise D004Error(
            f"{invariant_violations} observation(s) violated the EXPIRED consumption invariant"
        )
    reference_out = {
        state: {
            "blocks": bucket["blocks"],
            "fate_predicates": bucket["predicates"],
            "age_summary": _age_summary(bucket["ages"]),
        }
        for state, bucket in reference.items()
    }
    return {
        "gate11_entrants": len(obs),
        "expired_population": {
            "count": expired_predicates["blocks"],
            "fate_predicate_counts": expired_predicates,
            "fate_categories": expired_categories,
            "age_surface": _age_summary(expired_ages),
        },
        "fvg_context_summary": fvg_summary,
        "fate_x_fvg_contingency": dict(sorted(contingency.items())),
        "reference_populations": reference_out,
        "count_only_states": dict(sorted(count_only_states.items())),
    }


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

    ``tooling_fingerprint`` is the SHA-256 of the committed Git blob of
    this tooling file at ``tooling_commit`` under the declared
    ``canonical_git_blob_v1`` contract — checkout-independent, never
    worktree bytes.  Any unresolvable commit/path/blob fails closed with
    :class:`D004Error`; there is no worktree or normalized fallback.
    """
    from bot.scientific.canonical_bytes import canonical_file_digest  # noqa: PLC0415

    if not canonical_commit or len(canonical_commit) != 40:
        raise D004Error("canonical source commit identity invalid")
    if not tooling_commit or len(tooling_commit) != 40:
        raise D004Error("tooling commit identity invalid")
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
        raise D004Error(f"D004 tooling fingerprint unresolvable: {exc}") from exc
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

    Exact-key bans plus semantic substring families (§31); honest
    negation keys such as ``no_profitability_metrics`` pass because the
    performance vocabulary is banned as exact keys only and every honest
    key in this module avoids the banned substring stems.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            key_text = str(key).lower()
            if key_text in BANNED_METRIC_KEYS or any(
                banned in key_text for banned in BANNED_METRIC_SUBSTRINGS
            ):
                raise D004Error(f"{REJECTED_D004_METRIC_KEY} {path}.{key}")
            _reject_banned_metrics(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_banned_metrics(value, f"{path}[{index}]")


def _gate_funnel(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Preregistered accounting surface: gate entered/pass/fail (D003)."""
    from backtests.phase8_v2_diagnostic_d003 import _gate_funnel as _d003_funnel

    return _d003_funnel(rows)


def run_d004(
    store: Any,
    *,
    canonical_commit: str,
    tooling_commit: str,
    blob_source=None,
) -> tuple[dict[str, Any], bytes]:
    """Execute preregistered D004 over a loaded Fold-01 ``FoldFeatureStore``.

    The decision loop is the D003 loop verbatim (classification,
    reference check, canonical adapter, causal seed/carry, accounting);
    the observer is the D004 fate decomposition.  Fails closed on any
    boundary, accounting, consumption, reconciliation or structural
    violation.  Returns ``(document, canonical_json_bytes)``.
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
            buckets["evaluation_error"] += 1
            error_rows.append({
                "decision_id": row.get("decision_id"),
                "error_type": row.get("error_type"),
            })
            continue
        rows.append(row)
        # Read-only D004 augmentation of the successful decision; the
        # observer receives the exact causal PRIOR state record (TC001).
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

    aggregate = aggregate_d004(observations)
    doc: dict[str, Any] = {
        "diagnostic_id": DIAGNOSTIC_ID,
        "classification": CLASSIFICATION,
        "label": LABEL,
        "specification_document": "docs/PHASE8_V2_DIAGNOSTIC_D004.md",
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
        "frozen_configuration": {
            "order_block_expiry_bars": int(config.order_block_expiry_bars),
            "evaluation_performed_only_at_frozen_threshold": True,
        },
        **aggregate,
        "budget_consumption_note": "3 / 12 diagnostics upon this first empirical execution",
        "reserved_evidence": {
            "fold_02_untouched": True,
            "fold_03_untouched": True,
            "fold_04_untouched": True,
            "holdout_untouched": True,
            "data_2025_plus_untouched": True,
        },
        "no_profitability_metrics": True,
        "no_alternate_configuration_scored": True,
        "h002_not_reopened": True,
    }
    _reject_banned_metrics(doc)
    assert_expected_surfaces(doc)
    return doc, _canonical(doc).encode("utf-8")


def assert_expected_surfaces(document: Mapping[str, Any]) -> None:
    """Structural verification of the exact preregistered surface."""
    required = (
        "decision_accounting",
        "gate_funnel",
        "expired_population",
        "fvg_context_summary",
        "fate_x_fvg_contingency",
        "reference_populations",
        "count_only_states",
    )
    missing = [key for key in required if key not in document]
    if missing:
        raise D004Error(f"preregistered surface missing: {missing}")
    expired = document["expired_population"]
    histogram = expired["age_surface"]["histogram"]
    if sum(histogram.values()) != expired["fate_predicate_counts"]["blocks"]:
        raise D004Error("age histogram does not cover the expired population")
    partitions = expired["count"] + sum(
        bucket["blocks"] for bucket in document["reference_populations"].values()
    ) + sum(document["count_only_states"].values())
    if partitions != document["gate11_entrants"]:
        raise D004Error("expired/reference/count-only populations do not partition entrants")
    accounting = document["decision_accounting"]
    if (
        accounting["reducer_classified"]
        + accounting["missing_history"]
        + accounting["unavailable_input"]
        + accounting["evaluation_error"]
        != accounting["scheduled"]
    ):
        raise D004Error("decision accounting does not reconcile")


def write_result(
    document: Mapping[str, Any],
    rendered: bytes,
    output_dir: Path,
) -> tuple[Path, str]:
    """Atomically write the deterministic result; refuse overwrite."""
    from backtests.phase8_v2_variant_v001_eval import reject_holdout_path  # noqa: PLC0415

    output_dir = Path(output_dir)
    reject_holdout_path(str(output_dir))
    target = output_dir / "phase8-v2-D004_result.json"
    if target.exists():
        raise D004Error(f"result already exists; refusing overwrite: {target}")
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = output_dir / f".staging-{uuid.uuid4().hex[:8]}"
    staging.write_bytes(rendered)
    import os  # noqa: PLC0415

    os.replace(staging, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != hashlib.sha256(rendered).hexdigest():
        raise D004Error("result hash mismatch after write")
    return target, digest
