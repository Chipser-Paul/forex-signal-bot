"""Preregistered V002 Fold-01 structural measurement tooling (H007).

DEVELOPMENT_VARIANT_EVIDENCE — V002 — FOLD01 — NOT PROFITABILITY EVIDENCE

Governance
----------
* Variant:            phase6-development-v2-V002 (Canonical Structural OB/FVG Pair)
* Primary hypothesis: phase8-v2-H007 (Canonical OB/FVG Structural-Pair Semantics)
* Supporting:         H002 SUPPORTED_BY_D003; H006 SUPPORTED_BY_D004;
                      H001 SUPPORTED_BY_D003_D004_SYNTHESIS
* Specification:      docs/PHASE8_V2_VARIANT_V002.md (SHA-256 recorded below)
* Charter:            phase8-v2-research-charter-v1-8527e3a5eec98f53
* Implementation:     bot/strategy/variant_v002.py (frozen V002 evaluator/scorer/
                      downstream path; historical canonical semantics untouched)

Frozen measurement contract (preregistered before empirical access):

* Fold 01 ONLY: the store must be fold-01 with full coverage; the historical
  store ``fold-01-1d710826193a6767`` is refused as input; Tier B (Folds 02-04),
  holdout and 2025+ data fail closed.
* The loop reuses the frozen D001/D003 discipline verbatim: canonical snapshot
  classification, reference check, the production orchestrator adapter
  (``evaluate_orchestration_decision``), the seed setup-state record, the
  cell-local record carry and the accounting reconciliation.
* The V002 observer is the ONLY variant semantics: it evaluates the frozen
  V002 structural-pair evaluator (``evaluate_v002_structural_pair``) over the
  reducer's exact M5 entry frame with reducer-exact consumed ids from the
  causal PRIOR state record, scores Gate 11 with the V002 scorer and runs the
  V002 downstream strategy path.  The frozen D001 row (canonical/reducer
  semantics) is never modified.
* Store-compatibility rule (spec section 22): the V001 store is reusable ONLY
  because every V002-required causal input (M5 entry_rows, persisted
  fvgs surface, htf_bias, decision timestamp, StrategyConfig, consumed ids)
  is reconstructable causally from the existing snapshots; V002 strategy
  outputs are not stored as immutable inputs.  This is asserted from input
  semantics at runtime (``assert_store_semantic_compatibility``) — any
  missing required payload field fails closed.
* Only the preregistered structural metrics are emitted; profitability/
  counterfactual metric names are structurally rejected; the exact-overlap
  observer keeps the frozen geometry as a descriptive field only.
* Raw output is written atomically outside Git, refusing overwrite, and
  content-hashed; provenance binds ``canonical_git_blob_v1`` committed bytes.
* THIS TOOLING IS NOT EXECUTED BY THE FREEZE TASK.  Empirical execution
  requires separate supervisory authorization; at the instant first Fold-01
  V002 strategy behavior is observed, strategy variants become 2 / 8.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
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
from bot.strategy.variant_v002 import (  # noqa: E402
    V002_FVG_LABEL,
    V002_OB_LABEL,
    evaluate_v002_strategy,
    evaluate_v002_structural_pair,
)

V002_ID = "phase6-development-v2-V002"
H007_ID = "phase8-v2-H007"
CHARTER_ID = "phase8-v2-research-charter-v1-8527e3a5eec98f53"
CHARTER_SHA256 = "8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc"
SPEC_SHA256 = "f53f27c4e7700adf63194392e05f4c523d65312ecde7081dc427ec7347aa8703"
IMPLEMENTATION_MODULE = "bot/strategy/variant_v002.py"
FINGERPRINT_CONTRACT = "canonical_git_blob_v1"
CLASSIFICATION = "DEVELOPMENT_VARIANT_EVIDENCE — V002 — FOLD01 — NOT PROFITABILITY EVIDENCE"
TOOLING_RELPATH = "backtests/phase8_v2_variant_v002_eval.py"
OPPORTUNITY_TARGET = 90
HISTORICAL_STORE_ID = "fold-01-1d710826193a6767"
FOLD01_START_MS = int(datetime.fromisoformat(FOLD01_START).timestamp() * 1000)
FOLD01_END_MS = int(datetime.fromisoformat(FOLD01_END).timestamp() * 1000)

#: Payload fields every V002-required causal input depends on.  A store
#: snapshot whose payload lacks any of these cannot drive V002 evaluation
#: and fails closed (store-compatibility decision, spec section 22).
REQUIRED_PAYLOAD_FIELDS = (
    "entry_rows", "fvgs", "htf_bias", "atr", "ob_result", "displacement",
)

BANNED_METRIC_KEYS = frozenset(
    {
        "pnl", "profit", "profit_factor", "win_rate", "expectancy",
        "drawdown", "sharpe", "returns", "return", "closed_trades", "trades",
        "fills", "fill_count", "balance", "equity",
    }
)
BANNED_METRIC_SUBSTRINGS = (
    "candidate_count_at_", "threshold_curve", "temporal_lag",
    "lag_distribution", "alternative_", "seven_of_eight", "partial_overlap",
    "optimal_", "expiry_45", "expiry_60", "expiry_90", "expiry_31",
    "expiry_40", "counterfactual_candidate", "alternate_expiry",
    "candidate_if_expiry_removed", "eligible_without_expiry",
)

DEVELOPMENT_END_DATE = date(2024, 12, 31)
HOLDOUT_TOKENS = ("holdout", "hold_out", "final_validation", "validation_fold")
FOLD_PREFIX_ALLOWED = ("fold-01",)


class V002EvalError(RuntimeError):
    """Frozen V002 measurement contract violation."""


class BoundaryError(V002EvalError):
    """Fold/holdout/temporal boundary violation."""


class StoreCompatibilityError(V002EvalError):
    """Store is not semantically sufficient for V002 causal reconstruction."""


# ---------------------------------------------------------------------------
# Boundary and store-compatibility guards (fail closed)
# ---------------------------------------------------------------------------


def check_store_boundary(identity: Mapping[str, Any]) -> None:
    fold_id = str(identity.get("fold_id", ""))
    if fold_id and not fold_id.startswith(FOLD_PREFIX_ALLOWED):
        raise BoundaryError(f"reserved fold store refused for V002: {fold_id!r}")
    if HISTORICAL_STORE_ID in json.dumps(dict(identity), sort_keys=True):
        raise V002EvalError(
            "the historical pre-adapter store fold-01-1d710826193a6767 is "
            "refused as a V002 input"
        )
    timeframe = str(identity.get("decision_timeframe", "M5"))
    if timeframe != "M5":
        raise BoundaryError(f"store decision timeframe is not M5: {timeframe!r}")
    start = int(identity.get("evaluation_start_ms", FOLD01_START_MS))
    end = int(identity.get("evaluation_end_ms", FOLD01_END_MS))
    if (start, end) != (FOLD01_START_MS, FOLD01_END_MS):
        raise BoundaryError(
            "store evaluation window is not Fold 01: "
            f"[{start}, {end}) expected [{FOLD01_START_MS}, {FOLD01_END_MS})"
        )
    coverage = str(identity.get("coverage", "full"))
    if coverage != "full":
        raise BoundaryError(f"store coverage is not full: {coverage!r}")


def assert_store_semantic_compatibility(snapshot: Any) -> None:
    """Spec section 22: prove, from input semantics, the store feeds V002.

    The V002 observer reconstructs every required causal input from the
    snapshot payload (M5 entry_rows, the persisted final-FVG surface, the
    persisted htf_bias, the decision timestamp, the frozen StrategyConfig
    and reducer-exact consumed ids).  If any required field is absent the
    store is NOT semantically sufficient and a fresh rebuild is mandatory;
    this tooling then refuses to run.
    """
    import json as _json

    payload_text = getattr(snapshot, "gate_payload", None)
    if not payload_text:
        raise StoreCompatibilityError(
            "V002 requires a persisted gate payload; this store cannot "
            "reconstruct the V002 causal inputs and needs a fresh rebuild"
        )
    try:
        payload = _json.loads(payload_text)
    except (TypeError, ValueError) as error:
        raise StoreCompatibilityError(f"gate payload is not decodable: {error}") from error
    missing = [field for field in REQUIRED_PAYLOAD_FIELDS if field not in payload]
    if missing:
        raise StoreCompatibilityError(
            "store payload lacks V002-required causal inputs "
            f"{missing}; per spec section 22 a fresh Fold-01 rebuild is "
            "REQUIRED before V002 execution"
        )


# ---------------------------------------------------------------------------
# V002 observation (the ONLY variant semantics; frozen D001 row untouched)
# ---------------------------------------------------------------------------


def observe_v002_decision(
    row: Mapping[str, Any],
    snapshot: Any,
    prior_state_record: Any,
    *,
    config: Any,
) -> dict[str, Any]:
    """Read-only V002 structural-pair evaluation for one Gate-11 entrant.

    Only decisions that legitimately ENTERED frozen Gate 11 under the
    unchanged upstream pipeline (``gate_11_confluence_score`` present in
    the frozen funnel row) belong to the V002 population — TC001.  The
    BOOLEAN VALUE of the historical Gate-11 result is DESCRIPTIVE
    comparison metadata only and never decides membership or fails the
    observation: a historical Gate-11 failure is precisely one of the
    decisions V002 may legitimately classify differently.
    """
    from bot.strategy.models import StrategySide  # noqa: PLC0415

    decision_id = row.get("decision_id")
    payload = json.loads(snapshot.gate_payload)
    rows = list(payload.get("entry_rows") or [])
    fvgs = list(payload.get("fvgs") or [])
    htf_bias = str(payload.get("htf_bias") or "")
    decision_at = datetime.fromtimestamp(
        int(snapshot.available_at_ms) / 1000, tz=timezone.utc
    )
    side = {"bullish": StrategySide.LONG, "bearish": StrategySide.SHORT}.get(
        htf_bias, StrategySide.FLAT
    )
    if side is StrategySide.FLAT:
        raise V002EvalError(
            f"Gate-11 entrant {decision_id!r} lacks a resolved htf_bias; "
            "V002 refuses to map it to FLAT"
        )
    frame = _entry_frame(rows)
    consumed = _consumed_ids_from_record(prior_state_record)
    pair = evaluate_v002_structural_pair(
        frame, side, decision_at, config,
        fvgs=fvgs, consumed_ids=consumed,
    )
    dxy_context = dict(payload.get("dxy_context") or {})
    news_context = dict(payload.get("news_context") or {})
    session_context = dict(payload.get("session_context") or {})
    structure_context = (payload.get("liquidity_context") or {}).get(
        "structure_context"
    ) or {}
    pd_flag = bool(
        structure_context.get("discount_zone" if htf_bias == "bullish" else "premium_zone")
    )
    sweep_flag = bool(payload.get("liquidity_signal"))
    evidence = _evidence(pd_flag, sweep_flag)
    strategy = evaluate_v002_strategy(
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
        consumed_block_ids=consumed,
    )
    score = _score_v002(
        pair=pair, htf_bias=htf_bias, pd_flag=pd_flag, sweep_flag=sweep_flag,
    )
    observation: dict[str, Any] = {
        "decision_id": decision_id,
        "available_at_ms": int(snapshot.available_at_ms),
        "v002_pair_state": pair.state,
        "v002_pair_reason": pair.reason,
        "v002_structurally_active": bool(pair.structurally_active),
        "v002_side": pair.side.value,
        "v002_age_bars": int(pair.age_bars),
        "v002_block_id": pair.block_id,
        "v002_fvg_associated": bool(pair.fvg_associated),
        "v002_fvg_direction": pair.fvg_direction,
        "v002_exact_overlap_descriptive": (
            None if pair.exact_overlap is None else bool(pair.exact_overlap)
        ),
        "v002_gate11_score": score,
        "v002_strategy_eligible": bool(strategy.entry_eligible),
        "v002_strategy_reasons": [str(reason) for reason in strategy.reasons],
        "v002_strategy_order_block_state": strategy.order_block.value,
        "legacy_canonical_fvg_in_ob": bool(
            (row.get("overlap") or {}).get("canonical_fvg_in_ob")
        ),
        "legacy_score_passed": bool(row["score"].get("passes_threshold")),
    }
    # TC001: the historical Gate-11 outcome is DESCRIPTIVE comparison
    # metadata only.  A historical Gate-11 failure must NOT fail closed —
    # V002 changes the Gate-11 OB/FVG structural semantics, so a decision
    # the old semantics rejected is exactly one the new semantics may
    # accept (the semantic effect V002 exists to measure).
    return observation


def _entry_frame(rows: list[dict[str, Any]]):
    import pandas as pd  # noqa: PLC0415

    frame = pd.DataFrame(rows)
    for column in ("open_time", "available_at"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], utc=True)
    return frame


def _consumed_ids_from_record(prior_state_record: Any) -> frozenset[str]:
    """Reducer-exact causal consumed block ids (D003 discipline verbatim)."""
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


def _evidence(pd_flag: bool, sweep_flag: bool):
    from bot.strategy.models import SetupEvidence  # noqa: PLC0415

    return SetupEvidence(
        price_in_discount_or_premium=bool(pd_flag),
        order_block_present=True,
        fvg_overlaps_order_block=True,
        liquidity_swept=bool(sweep_flag),
    )


def _score_v002(*, pair, htf_bias: str, pd_flag: bool, sweep_flag: bool) -> dict[str, Any]:
    from bot.strategy.variant_v002 import score_v002_setup  # noqa: PLC0415

    return score_v002_setup(
        pair=pair, htf_bias=htf_bias,
        price_in_discount_or_premium=bool(pd_flag),
        liquidity_swept=bool(sweep_flag),
    )


# ---------------------------------------------------------------------------
# Aggregate (structural metrics only)
# ---------------------------------------------------------------------------


def aggregate_v002(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    observations = list(observations)
    pair_states: dict[str, int] = {}
    pair_reasons: dict[str, int] = {}
    sides = {"LONG": 0, "SHORT": 0, "FLAT": 0}
    active = 0
    fvg_associated = 0
    overlap_true = 0
    overlap_false = 0
    overlap_not_available = 0
    gate11_v002_pass = 0
    legacy_pass = 0
    legacy_fail = 0
    strategy_eligible: list[dict[str, Any]] = []
    ages: list[int] = []
    for observation in observations:
        pair_states[observation["v002_pair_state"]] = (
            pair_states.get(observation["v002_pair_state"], 0) + 1
        )
        pair_reasons[observation["v002_pair_reason"]] = (
            pair_reasons.get(observation["v002_pair_reason"], 0) + 1
        )
        sides[observation["v002_side"]] = sides.get(observation["v002_side"], 0) + 1
        if observation["v002_structurally_active"]:
            active += 1
            ages.append(int(observation["v002_age_bars"]))
        if observation["v002_fvg_associated"]:
            fvg_associated += 1
            overlap = observation["v002_exact_overlap_descriptive"]
            if overlap is True:
                overlap_true += 1
            elif overlap is False:
                overlap_false += 1
            else:
                overlap_not_available += 1
        if observation["v002_gate11_score"]["passes_threshold"]:
            gate11_v002_pass += 1
        # TC001: descriptive legacy comparison counts — neither gates V002.
        if observation["legacy_score_passed"]:
            legacy_pass += 1
        else:
            legacy_fail += 1
        if observation["v002_strategy_eligible"]:
            strategy_eligible.append(
                {
                    "decision_id": observation["decision_id"],
                    "available_at_ms": observation["available_at_ms"],
                    "side": observation["v002_side"],
                    "age_bars": observation["v002_age_bars"],
                    "exact_overlap_descriptive": observation[
                        "v002_exact_overlap_descriptive"
                    ],
                }
            )
    candidate_ready = len(strategy_eligible)
    entrants = len(observations)
    long_count = sum(1 for item in strategy_eligible if item["side"] == "LONG")
    short_count = sum(1 for item in strategy_eligible if item["side"] == "SHORT")
    return {
        "V002_structural_pair_surface": {
            "gate11_entrants_observed": entrants,
            "v002_pair_state_counts": dict(sorted(pair_states.items())),
            "h007_pair_state_reason_distribution": dict(sorted(pair_reasons.items())),
            "v002_structurally_active_count": active,
            "v002_sides": {key: sides.get(key, 0) for key in ("LONG", "SHORT", "FLAT")},
            "v002_associated_same_direction_fvg_count": fvg_associated,
            "exact_overlap_descriptive_true": overlap_true,
            "exact_overlap_descriptive_false": overlap_false,
            "exact_overlap_descriptive_not_available": overlap_not_available,
            "v002_structural_active_age_summary": _age_summary(ages),
            "gate11_v002_score_pass_count": gate11_v002_pass,
            "legacy_score_passed_count": legacy_pass,
            "legacy_score_failed_count": legacy_fail,
            "score_component_labels": {
                "ob_component": V002_OB_LABEL,
                "fvg_component": V002_FVG_LABEL,
                "weights": [2, 1, 2, 1, 2],
                "maximum": 8,
                "threshold": 8,
            },
        },
        "candidate_surface": {
            "candidate_ready": candidate_ready,
            "candidate_rate": (
                round(candidate_ready / entrants, 6) if entrants else 0.0
            ),
            "candidate_long_count": long_count,
            "candidate_short_count": short_count,
            "candidate_setup_ids": [item["decision_id"] for item in strategy_eligible],
            "candidate_age_bars": [
                item["age_bars"] for item in strategy_eligible
            ],
            "candidate_exact_overlap_descriptive": [
                item["exact_overlap_descriptive"] for item in strategy_eligible
            ],
        },
        "success_classification_rule": {
            "OPPORTUNITY_SUFFICIENT": "candidate_ready >= 90",
            "OPPORTUNITY_INSUFFICIENT": "0 < candidate_ready < 90",
            "NO_CANDIDATES": "candidate_ready == 0",
            "IMPLEMENTATION_FAILED": "only if H007 semantics malfunction",
            "note": "classification is applied by the supervisory review of the sealed result; no target is encoded anywhere in tooling or tests",
        },
    }


def _age_summary(ages: list[int]) -> dict[str, Any]:
    if not ages:
        return {"count": 0}
    ordered = sorted(ages)

    def _quantile(fraction: float) -> float:
        position = fraction * (len(ordered) - 1)
        low = int(position)
        high = min(low + 1, len(ordered) - 1)
        weight = position - low
        return round(ordered[low] * (1 - weight) + ordered[high] * weight, 1)

    return {
        "count": len(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        "median": _quantile(0.5),
        "quantiles": {
            "p25": _quantile(0.25),
            "p50": _quantile(0.5),
            "p75": _quantile(0.75),
        },
    }


# ---------------------------------------------------------------------------
# Provenance, banned metrics, runner
# ---------------------------------------------------------------------------

_PROVENANCE = {
    "tooling": TOOLING_RELPATH,
    "variant_id": V002_ID,
    "hypothesis_id": H007_ID,
    "implementation_module": IMPLEMENTATION_MODULE,
    "charter_id": CHARTER_ID,
    "charter_sha256": CHARTER_SHA256,
    "specification_document": "docs/PHASE8_V2_VARIANT_V002.md",
    "specification_sha256": SPEC_SHA256,
    "fingerprint_contract": FINGERPRINT_CONTRACT,
    "classification": CLASSIFICATION,
    "research_identity": "phase6-development-v2",
    "fold01_boundary": [FOLD01_START, FOLD01_END],
    "store_compatibility_decision": (
        "B — the preserved immutable V001 store is semantically sufficient: "
        "every V002-required causal input (M5 entry_rows, persisted final-FVG "
        "surface, persisted htf_bias, decision timestamp, frozen "
        "StrategyConfig, reducer-exact consumed ids) is reconstructable "
        "causally from existing snapshots; V002 strategy outputs are not "
        "stored as immutable inputs; asserted per snapshot by "
        "assert_store_semantic_compatibility, fail closed"
    ),
}


def provenance(
    *,
    implementation_commit: str,
    tooling_commit: str,
    store_identity: Mapping[str, Any],
    generated_at: str | None = None,
    blob_source=None,
) -> dict[str, Any]:
    """Provenance bound to the V002 implementation commit and this tooling."""
    from bot.scientific.canonical_bytes import canonical_file_digest  # noqa: PLC0415

    if not implementation_commit or len(implementation_commit) != 40:
        raise V002EvalError("V002 implementation commit identity invalid")
    if not tooling_commit or len(tooling_commit) != 40:
        raise V002EvalError("tooling commit identity invalid")
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
        raise V002EvalError(f"V002 tooling fingerprint unresolvable: {error}") from error
    blob = json.dumps(store_identity, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        **_PROVENANCE,
        "implementation_commit": implementation_commit,
        "tooling_commit": tooling_commit,
        "tooling_fingerprint": tooling_fingerprint,
        "fold_store_identity_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "generated_at_utc": generated_at or _iso(datetime.now(timezone.utc)),
    }


def _canonical_blob_source():
    """Production committed-byte source: real Git plumbing on this repo."""
    from bot.scientific.canonical_bytes import make_git_blob_source  # noqa: PLC0415

    return make_git_blob_source(REPO_ROOT)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _reject_banned_metrics(node: Any, path: str = "document") -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            key_text = str(key).lower()
            if key_text in BANNED_METRIC_KEYS or any(
                banned in key_text for banned in BANNED_METRIC_SUBSTRINGS
            ):
                raise V002EvalError(f"prohibited metric key {path}.{key}")
            _reject_banned_metrics(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_banned_metrics(value, f"{path}[{index}]")


def run_v002(
    store: Any,
    *,
    implementation_commit: str,
    tooling_commit: str,
    blob_source=None,
) -> tuple[dict[str, Any], bytes]:
    """Execute preregistered V002 measurement over a Fold-01 feature store.

    Loop discipline is the frozen D001/D003 one; the V002 observer is the
    only variant semantics.  Fails closed on boundary, store-compatibility,
    accounting or structural violations.  Returns ``(document, bytes)``.
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
    observations: list[dict[str, Any]] = []
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
        # TC001: V002 population = every decision that legitimately ENTERED
        # frozen Gate 11 under the unchanged upstream pipeline (Gate 8/9/10
        # passed).  The historical Gate-11 BOOLEAN must not act as an
        # eligibility filter for the new strategy's own semantics.
        gate11_entered = "gate_11_confluence_score" in (
            row.get("gate_results") or {}
        )
        if gate11_entered:
            assert_store_semantic_compatibility(snapshot)
            observations.append(
                observe_v002_decision(
                    row, snapshot, prior_state_record, config=config,
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
    doc: dict[str, Any] = {
        "variant_id": V002_ID,
        "hypothesis_id": H007_ID,
        "classification": CLASSIFICATION,
        "specification_document": "docs/PHASE8_V2_VARIANT_V002.md",
        "specification_sha256": SPEC_SHA256,
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
        "gate_funnel": _gate_funnel(rows),
        **aggregate_v002(observations),
        "budget_consumption_note": (
            "strategy variants become permanently 2 / 8 at the instant "
            "first Fold-01 V002 strategy behavior is empirically observed"
        ),
        "reserved_evidence": {
            "fold_02_untouched": True,
            "fold_03_untouched": True,
            "fold_04_untouched": True,
            "holdout_untouched": True,
            "data_2025_plus_untouched": True,
        },
        "no_profitability_metrics": True,
        "no_numeric_expiry_evaluated": True,
        "dxy_authority_unchanged": True,
    }
    _reject_banned_metrics(doc)
    assert_expected_surfaces(doc)
    return doc, _canonical(doc).encode("utf-8")


def assert_expected_surfaces(document: Mapping[str, Any]) -> None:
    required = (
        "decision_accounting",
        "gate_funnel",
        "V002_structural_pair_surface",
        "candidate_surface",
        "success_classification_rule",
    )
    missing = [key for key in required if key not in document]
    if missing:
        raise V002EvalError(f"preregistered V002 surface missing: {missing}")
    accounting = document["decision_accounting"]
    if (
        accounting["reducer_classified"] + accounting["missing_history"]
        + accounting["unavailable_input"] + accounting["evaluation_error"]
        != accounting["scheduled"]
    ):
        raise V002EvalError("decision accounting does not reconcile")
    surface = document["V002_structural_pair_surface"]
    if surface["gate11_entrants_observed"] < 0:
        raise V002EvalError("negative V002 population")
    # TC001 hard reconciliation: the observed V002 population must equal
    # the frozen funnel's Gate-11 entered count exactly — no silent
    # population truncation (passer-based filtering) may ever recur.
    entered = int(
        document.get("gate_funnel", {})
        .get("gate_11_confluence_score", {})
        .get("entered", -1)
    )
    if entered < 0:
        raise V002EvalError(
            "gate funnel lacks a gate_11_confluence_score entry; the V002 "
            "population cannot be reconciled"
        )
    if surface["gate11_entrants_observed"] != entered:
        raise V002EvalError(
            "V002 population mismatch (TC001): observed "
            f"{surface['gate11_entrants_observed']} Gate-11 entrants != "
            f"funnel entered {entered}"
        )
    candidate = document["candidate_surface"]
    if candidate["candidate_ready"] < 0:
        raise V002EvalError("negative candidate_ready")
    # TC001 hard reconciliation: a downstream candidate must be a subset of
    # the V002 Gate-11 score passes (unchanged downstream protections such
    # as DXY may still reject; they can never create candidates).
    if not (
        candidate["candidate_ready"]
        <= surface["gate11_v002_score_pass_count"]
        <= surface["gate11_entrants_observed"]
    ):
        raise V002EvalError(
            "candidate/score reconciliation violated (TC001): "
            f"candidate_ready {candidate['candidate_ready']} > "
            f"v002 score passes {surface['gate11_v002_score_pass_count']} "
            f"> entrants {surface['gate11_entrants_observed']}"
        )


def _gate_funnel(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    funnel: dict[str, dict[str, int]] = {}
    for row in rows:
        for name, passed in (row.get("gate_results") or {}).items():
            slot = funnel.setdefault(name, {"entered": 0, "passed": 0, "failed": 0})
            slot["entered"] += 1
            slot["passed" if passed else "failed"] += 1
    return dict(sorted(funnel.items()))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_result(material: Mapping[str, Any], rendered: bytes, output_dir: Path) -> tuple[Path, str]:
    """Atomically write the deterministic result; refuse overwrite."""
    output_dir = Path(output_dir)
    reject_holdout_path(str(output_dir))
    target = output_dir / "phase6-development-v2-V002_result.json"
    if target.exists():
        raise V002EvalError(f"result already exists; refusing overwrite: {target}")
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = output_dir / f".staging-{uuid.uuid4().hex[:8]}"
    staging.write_bytes(rendered)
    os.replace(staging, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != hashlib.sha256(rendered).hexdigest():
        raise V002EvalError("result hash mismatch after write")
    return target, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the Fold-01 feature store")
    parser.add_argument("--implementation-commit", required=True)
    parser.add_argument("--tooling-commit", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    from bot.validation.market_feature_store import FoldFeatureStore  # noqa: PLC0415

    reject_holdout_path(args.store)
    store = FoldFeatureStore.open(args.store)
    document, rendered = run_v002(
        store,
        implementation_commit=args.implementation_commit,
        tooling_commit=args.tooling_commit,
    )
    path, sha = write_result(document, rendered, Path(args.output_dir))
    print(json.dumps({"path": str(path), "sha256": sha}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
