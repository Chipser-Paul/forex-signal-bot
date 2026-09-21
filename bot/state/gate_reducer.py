"""Deterministic setup-gate transition over frozen, already-acquired inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any

import pandas as pd

from bot.execution.confluence_scorer import score_setup
from bot.strategy.config import StrategyConfig
from bot.strategy.legacy_adapter import evaluate_legacy_context
from bot.strategy.models import SetupEvidence
from bot.strategy.setup_state import (
    SetupStateRecord, record_from_state, stable_setup_id, state_from_record,
)
from bot.strategy.setup_consumption import semantic_id, setup_reuse_reason
from bot.state.gate_inputs import (
    StrategyEvaluationInputs, displacement_tier_result, structural_variant_result,
)
from strategies.smc_engine.entry_model import determine_entry


REDUCER_VERSION = "phase8n.setup-gates.v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class StrategyGateTransition:
    event_id: str
    setup_id: str
    setup_status: str
    result_json: str
    state_record: SetupStateRecord

    def result(self) -> dict[str, Any]:
        return json.loads(self.result_json)


def _entry_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in ("open_time", "available_at"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], utc=True)
    return frame


def evaluate_strategy_gates(
    prior_state: SetupStateRecord, inputs: StrategyEvaluationInputs,
    event_time: datetime, config: StrategyConfig,
) -> StrategyGateTransition:
    """Apply gates 8–13 without fetchers, clock reads, logging or broker calls."""
    if event_time != inputs.event_at or config.fingerprint() != inputs.config_fingerprint:
        raise ValueError("gate event time or frozen configuration mismatch")
    state = state_from_record(prior_state, event_time)
    data = inputs.decoded()
    previous = prior_state.data()
    if previous["last_event_id"] == inputs.event_id and not previous["consumption"]["events"] and not previous["consumption"]["blocked"]:
        if previous["last_result"] is None:
            raise ValueError("duplicate gate event has no persisted result")
        cached = json.loads(previous["last_result"])
        return StrategyGateTransition(
            inputs.event_id, cached["setup_id"], cached["setup_status"],
            previous["last_result"], prior_state,
        )

    profile = data["profile"]
    htf_bias = data["htf_bias"]
    structure_context = data["liquidity_context"].get("structure_context") or {}
    sources = dict(inputs.source_identities)
    setup_id = stable_setup_id(
        symbol=inputs.symbol, side=htf_bias,
        decision_at=event_time,
        source_identities=sources,
        structure_identity=_identity(structure_context),
        ob_identity=_identity(data["ob_result"]) if data["ob_result"] else None,
        fvg_identity=_identity(data["fvgs"]) if data["fvgs"] else None,
        sweep_identity=_identity(data["liquidity_signal"]) if data["liquidity_signal"] else None,
        config_fingerprint=config.fingerprint(),
        evaluation_identity=hashlib.sha256(inputs.payload.encode("utf-8")).hexdigest(),
    )
    evidence_id = semantic_id("evidence_", {
        "symbol": inputs.symbol, "side": htf_bias, "sources": sources,
        "structure": structure_context, "ob": data["ob_result"],
        "fvgs": data["fvgs"], "sweep": data["liquidity_signal"],
        "entry_rows": data["entry_rows"],
        "config": config.fingerprint(), "profile": json.loads(inputs.payload)["profile"],
    })
    context: dict[str, Any] = {
        "symbol": inputs.symbol, "setup_id": setup_id,
        "decision_id": inputs.event_id, "source_identities": sources,
        "signal_available_at": data["entry_rows"][-1]["available_at"],
        "source_close": data["entry_rows"][-1]["close"],
        "config_fingerprint": semantic_id("", {
            "strategy": config.fingerprint(), "profile": json.loads(inputs.payload)["profile"],
            "reducer": REDUCER_VERSION,
        }), "evidence_id": evidence_id,
        "bias": data["bias_snapshot"], "bias_resolution": data["bias_resolution"],
        "dxy": data["dxy_context"], "news": data["news_context"],
        "session": data["session_context"],
    }
    if "min_rr" in profile:
        context["profile_min_rr"] = float(profile["min_rr"])
    gates: dict[str, Any] = {}
    timing: dict[str, str] = {}
    conditions: dict[str, Any] = {}
    event_iso = event_time.isoformat()

    def finish(action: str, reason: str, status: str) -> StrategyGateTransition:
        result = {
            "version": REDUCER_VERSION, "event_id": inputs.event_id,
            "setup_id": setup_id, "setup_status": status,
            "action": action, "reason": reason, "state_name": state.state_name,
            "context": context, "gate_results": gates,
            "timing_info": timing, "market_conditions": conditions,
        }
        rendered = _canonical(result)
        next_state = record_from_state(
            state, event_at=event_time,
            last_event_id=inputs.event_id, last_result=rendered,
        )
        return StrategyGateTransition(inputs.event_id, setup_id, status, rendered, next_state)

    reuse_reason = setup_reuse_reason(prior_state, setup_id, evidence_id)
    if reuse_reason:
        return finish("skip", reuse_reason, "CONSUMED_SETUP" if reuse_reason == "setup_already_consumed" else "RECONCILIATION_REQUIRED_SETUP")

    state.update_session(data["session_context"])
    state.update_news(data["news_context"])
    state.set_daily_limit_hit(False)
    state.update_bias(data["bias_snapshot"])

    # Gate 8: fetched frame sufficiency, structure update and liquidity sweep.
    context["liquidity"] = data["liquidity_context"]
    if data["structure_len"] <= 0 or not data["entry_rows"]:
        gates["gate_8_liquidity"] = {"pass": False, "raw": {"reason": "insufficient_market_data"}}
        return finish("wait", "insufficient_market_data", "DATA_UNSAFE_SETUP")
    structure_dir = str(structure_context.get("structure", ""))
    structure_state = str(structure_context.get("state", ""))
    if structure_dir in ("bullish", "bearish") and structure_state in ("confirmed", "transition", "range"):
        state.update_structure(structure_dir, structure_state)
    sweep = data["liquidity_signal"]
    context["liquidity_signal"] = sweep
    gates["gate_8_liquidity"] = {"pass": bool(sweep), "raw": sweep}
    if not sweep:
        state.reject_setup("liquidity_sweep_missing")
        return finish("wait", "liquidity_sweep_missing", "NO_SETUP")
    if sweep.get("side") in ("buy", "sell"):
        state.update_liquidity(
            side=sweep["side"], index=int(data["structure_len"] - 1),
            liquidity_type=sweep.get("type"),
        )
        timing["sweep_detected"] = event_iso

    # Gate 9: M5 displacement and the existing optional tier rule.
    displacement = data["displacement"]
    context["displacement"] = displacement
    valid_displacement = bool(displacement.get("valid"))
    gates["gate_9_displacement"] = {"pass": valid_displacement, "raw": displacement}
    if not valid_displacement:
        state.reject_setup("displacement_missing")
        return finish("wait", "displacement_missing", "REJECTED_SETUP")
    fvg = displacement.get("fvg")
    state.update_displacement(tuple(fvg) if isinstance(fvg, list) else fvg)
    timing["displacement_detected"] = event_iso
    tier_result = displacement_tier_result(profile, displacement)
    if tier_result["enabled"]:
        if tier_result["tier"] == "tier_1" and tier_result["action"] == "log_only":
            state.reject_setup("displacement_tier_1_log_only")
            return finish("skip", "displacement_tier_1_log_only", "REJECTED_SETUP")
        if tier_result["tier"] in ("tier_2", "tier_3"):
            context["displacement_tier_adjustment"] = tier_result
    context["displacement_tier"] = tier_result
    gates["displacement_tier"] = tier_result

    # Gate 10: M15 confirmation, optional structural variant and freshness.
    fvgs = data["fvgs"]
    internal = data["internal_structure"]
    context["fvgs"] = fvgs
    context["internal_structure"] = internal
    internal_event = internal.get("event")
    early = (internal.get("early_event") or {}).get("event")
    confirmed = internal_event in ("BOS", "CHOCH") or early in ("BOS", "CHOCH")
    gates["gate_10_internal_structure"] = {
        "pass": confirmed, "raw": {
            "event": internal_event, "early_event": early, "internal_structure": internal,
        },
    }
    if not confirmed:
        state.reject_setup("internal_structure_missing")
        return finish("skip", "internal_structure_missing", "REJECTED_SETUP")
    timing["internal_structure_detected"] = event_iso
    variant_result, variant_failure = structural_variant_result(
        profile=profile, sweep=sweep, displacement=displacement,
        internal=internal, atr=float(data["atr"]), timing=timing,
    )
    if "variant_a" in variant_result["details"]:
        context["structural_shift_strength"] = variant_result["details"]["variant_a"]
    if variant_failure:
        state.reject_setup(variant_failure)
        status = "EXPIRED_SETUP" if variant_failure.startswith("freshness_window_failed_") else "REJECTED_SETUP"
        return finish("skip", variant_failure, status)
    context["structural_shift_variant"] = variant_result
    gates["structural_shift_variant"] = variant_result
    ob = data["ob_result"]
    context["ob"] = ob
    atr = float(data["atr"])
    conditions.update({
        "atr": atr, "spread": 20.0,
        "session": data["session_context"].get("active_session"),
        "day_of_week": event_time.weekday(), "hour_utc": event_time.hour,
        "volatility_percentile": 0.5, "trend_strength": htf_bias,
        "distance_to_htf_ob": 0.0, "distance_to_daily_open": 0.0,
    })

    # Gate 11: same setup-only score, then same canonical Phase 6 reducer.
    first_fvg = fvgs[0] if fvgs else None
    ob_zone = ob.get("zone") if ob.get("valid") else None
    fvg_in_ob = False
    if first_fvg and ob_zone:
        try:
            tolerance = atr * 0.30
            fvg_low, fvg_high = float(first_fvg["bottom"]), float(first_fvg["top"])
            ob_low, ob_high = float(ob_zone[0]), float(ob_zone[1])
            gap = fvg_low - ob_high if fvg_low > ob_high else ob_low - fvg_high if fvg_high < ob_low else 0.0
            fvg_in_ob = gap <= tolerance
        except (TypeError, ValueError, KeyError, IndexError):
            fvg_in_ob = False
    score = score_setup({
        "htf_bias": htf_bias, "trade_direction": htf_bias,
        "price_in_discount_or_premium": bool(
            structure_context.get("discount_zone" if htf_bias == "bullish" else "premium_zone")
        ),
        "valid_ob_present": bool(ob.get("valid")),
        "fvg_in_ob_zone": fvg_in_ob,
        "liquidity_swept_before_entry": bool(sweep),
        "internal_bos_early": bool(
            internal.get("event") not in ("BOS", "CHOCH")
            and (internal.get("early_event") or {}).get("event") in ("BOS", "CHOCH")
        ),
    })
    context["score"] = score
    gates["gate_11_confluence_score"] = {"pass": score.get("passes_threshold", False), "raw": score}
    if not score.get("passes_threshold", False):
        state.reject_setup("score_below_threshold")
        return finish("skip", "score_below_threshold", "REJECTED_SETUP")
    entry_frame = _entry_frame(data["entry_rows"])
    canonical = evaluate_legacy_context(
        adapter="live", symbol=inputs.symbol, decision_at=event_time,
        side=htf_bias, entry_frame=entry_frame, htf_bias=htf_bias,
        dxy_context=data["dxy_context"], news_context=data["news_context"],
        session_context=data["session_context"],
        evidence=SetupEvidence(
            bool(structure_context.get("discount_zone" if htf_bias == "bullish" else "premium_zone")),
            bool(ob.get("valid")), fvg_in_ob, bool(sweep),
        ),
        config=config,
        consumed_block_ids=frozenset(
            binding.get("block_id") for key, binding in previous["consumption"]["bindings"].items()
            if key in previous["consumption"]["events"] and binding.get("block_id")
        ),
    )
    decision = canonical.to_dict()
    context["strategy_decision"] = decision
    gates["canonical_strategy"] = {"pass": canonical.entry_eligible, "raw": decision}
    if not canonical.entry_eligible:
        status = {
            "PREMATURE": "PREMATURE_SETUP", "MITIGATED": "MITIGATED_SETUP",
            "CONSUMED": "CONSUMED_SETUP", "INVALIDATED": "INVALIDATED_SETUP",
            "EXPIRED": "EXPIRED_SETUP", "DATA_UNSAFE": "DATA_UNSAFE_SETUP",
        }.get(decision.get("order_block"), "REJECTED_SETUP")
        return finish("skip", canonical.reasons[0].value.lower(), status)

    # Gates 12–13: unchanged entry model over the private replay-state copy.
    current_price = float(entry_frame["close"].iloc[-1])
    entry = determine_entry(
        inputs.symbol, state, current_price, score_result=score,
        context={
            "ob_zone": ob_zone, "fvg_zone": first_fvg,
            "after_london_open": data["session_context"].get("active_session") == "london",
            "asian_liquidity_swept": any(
                pool.get("type") in ("asian_high", "asian_low")
                for pool in data["liquidity_context"].get("liquidity_pools", [])
            ),
            "sweep_rejected": bool(internal.get("event") in ("CHOCH", "BOS")),
            "internal_structure_event": internal.get("event"),
            "htf_zone_alignment": bool(ob.get("valid")),
        },
        emit_log=None,
    )
    context["entry"] = entry
    gates["gate_12_13_rr_entry"] = {
        "pass": bool(entry), "raw": {"entry": entry, "current_price": current_price},
    }
    if entry:
        timing["entry_ready"] = event_iso
        return finish("candidate_ready", "setup_passed_all_gates", "ELIGIBLE_SETUP")
    return finish("wait", "entry_not_ready", "CANDIDATE_SETUP")
