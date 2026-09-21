"""Acquisition-side preparation for the supported orchestrator setup gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Mapping

import pandas as pd

from bot.analysis import get_unfilled_fvgs
from bot.analysis.structural_shift_variants import (
    calculate_variant_a_strength, check_variant_b_sequence, check_freshness_window,
)
from bot.strategy.config import StrategyConfig
from strategies.smc_engine.displacement_engine import detect_displacement
from strategies.smc_engine.liquidity_engine import detect_liquidity_sweep
from strategies.smc_engine.market_structure import analyze_market_structure
from strategies.smc_engine.ob_breaker_engine import detect_ob_breaker
from utils.indicators import calculate_atr


INPUT_SCHEMA = "phase8n.gate-inputs.v1"


class GateInputError(ValueError):
    """Already-acquired data cannot safely support the setup gates."""


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise GateInputError("gate event time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _freeze(value: Any, *, profile: bool = False) -> Any:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            raise GateInputError("gate input contains missing timestamp")
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise GateInputError("gate input contains non-string key")
        return {key: _freeze(item, profile=profile) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_freeze(item, profile=profile) for item in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        return _freeze(value.item(), profile=profile)
    if isinstance(value, float):
        if math.isinf(value) and value > 0 and profile:
            return {"__unbounded_profile_max__": True}
        if not math.isfinite(value):
            raise GateInputError("gate input contains non-finite value")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise GateInputError(f"unsupported gate input type: {type(value).__name__}")


def _thaw(value: Any) -> Any:
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    if isinstance(value, dict):
        if value == {"__unbounded_profile_max__": True}:
            return float("inf")
        return {key: _thaw(item) for key, item in value.items()}
    return value


def displacement_tier_result(profile: Mapping[str, Any], displacement: Mapping[str, Any]) -> dict[str, Any]:
    """Single interpretation shared by acquisition short-circuit and reducer."""
    tiers = profile.get("displacement_tiers", {})
    result = {"enabled": tiers.get("enabled", False), "tier": None, "action": None, "position_size_pct": 1.0}
    if tiers.get("enabled", False):
        multiplier = float(displacement.get("atr_multiplier", 0.0))
        for name, tier in tiers.items():
            if name.startswith("tier_") and tier.get("min_atr_mult", 0.0) <= multiplier < tier.get("max_atr_mult", float("inf")):
                result.update({"tier": name, "action": tier.get("action"), "position_size_pct": tier.get("position_size_pct", 1.0)})
                break
    return result


def structural_variant_result(
    *, profile: Mapping[str, Any], sweep: Mapping[str, Any],
    displacement: Mapping[str, Any], internal: Mapping[str, Any],
    atr: float, timing: Mapping[str, str],
) -> tuple[dict[str, Any], str | None]:
    structural = profile.get("structural_shift", {})
    variant = structural.get("variant", "original")
    result: dict[str, Any] = {"variant": variant, "enabled": variant != "original", "pass": True, "details": {}}
    if variant == "variant_a" and structural.get("variant_a", {}).get("enabled", False):
        result["details"]["variant_a"] = calculate_variant_a_strength(
            liquidity_signal=sweep, displacement=displacement,
            internal_structure=internal, atr=atr, config=structural,
        )
    elif variant == "variant_b" and structural.get("variant_b", {}).get("enabled", False):
        sequence = check_variant_b_sequence(
            liquidity_signal=sweep, displacement=displacement,
            internal_structure=internal, config=structural,
        )
        result["details"]["variant_b"] = sequence
        result["pass"] = sequence["pass"]
        if not sequence["pass"]:
            return result, f"variant_b_sequence_failed_{sequence['missing_stage']}"
    if structural.get("freshness_window", {}).get("enabled", False):
        freshness = check_freshness_window(timing_info=dict(timing), config=structural)
        result["details"]["freshness_window"] = freshness
        if not freshness["pass"]:
            return result, f"freshness_window_failed_{freshness['failed_stage']}"
    return result, None


def _source_identity(timeframe: str, frame: pd.DataFrame, event_at: datetime) -> str:
    if frame is None or frame.empty or not {"open_time", "available_at"}.issubset(frame.columns):
        raise GateInputError(f"missing causal source identity: {timeframe}")
    if frame["open_time"].isna().any() or frame["available_at"].isna().any():
        raise GateInputError(f"invalid causal source identity: {timeframe}")
    opened = pd.Timestamp(frame["open_time"].iloc[-1])
    available = pd.Timestamp(frame["available_at"].iloc[-1])
    if opened.tzinfo is None or available.tzinfo is None:
        raise GateInputError(f"naive causal source identity: {timeframe}")
    try:
        opens = pd.DatetimeIndex(frame["open_time"])
        availability = pd.DatetimeIndex(frame["available_at"])
    except (TypeError, ValueError) as exc:
        raise GateInputError(f"malformed causal source identity: {timeframe}") from exc
    if opens.tz is None or availability.tz is None:
        raise GateInputError(f"naive causal source identity: {timeframe}")
    if not opens.is_monotonic_increasing or opens.has_duplicates or not availability.is_monotonic_increasing:
        raise GateInputError(f"unsorted or duplicate causal source: {timeframe}")
    if (availability <= opens).any():
        raise GateInputError(f"invalid candle availability: {timeframe}")
    if available > pd.Timestamp(event_at) or (frame["available_at"] > pd.Timestamp(event_at)).any():
        raise GateInputError(f"future causal source candle: {timeframe}")
    return f"{timeframe}:{opened.tz_convert('UTC').isoformat()}:{available.tz_convert('UTC').isoformat()}"


@dataclass(frozen=True)
class StrategyEvaluationInputs:
    symbol: str
    event_at: datetime
    event_id: str
    source_identities: tuple[tuple[str, str], ...]
    config_fingerprint: str
    payload: str

    def decoded(self) -> dict[str, Any]:
        try:
            data = json.loads(self.payload)
        except (TypeError, ValueError) as exc:
            raise GateInputError("gate payload is malformed") from exc
        if not isinstance(data, dict) or data.get("schema") != INPUT_SCHEMA:
            raise GateInputError("gate input schema mismatch")
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if canonical != self.payload:
            raise GateInputError("gate input is not canonical")
        expected = gate_event_id(
            symbol=self.symbol, event_at=self.event_at,
            sources=self.source_identities, side=data["htf_bias"],
            payload=self.payload, config_fingerprint=self.config_fingerprint,
        )
        if self.event_id != expected:
            raise GateInputError("gate input identity does not match evidence")
        return _thaw(data)


def gate_event_id(
    *, symbol: str, event_at: datetime, sources: tuple[tuple[str, str], ...],
    side: str, payload: str, config_fingerprint: str,
) -> str:
    material = json.dumps({
        "schema": INPUT_SCHEMA, "symbol": symbol, "decision_at": _utc(event_at).isoformat(),
        "sources": sorted(sources), "side": side,
        "analysis_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "config": config_fingerprint,
    }, sort_keys=True, separators=(",", ":"))
    return "e8n1_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def build_gate_inputs(
    *, symbol: str, event_at: datetime, frames: Mapping[str, pd.DataFrame],
    profile: Mapping[str, Any], htf_bias: str, bias_snapshot: Mapping[str, Any],
    bias_resolution: Mapping[str, Any],
    liquidity_context: Mapping[str, Any], dxy_context: Mapping[str, Any],
    news_context: Mapping[str, Any], session_context: Mapping[str, Any],
    config: StrategyConfig,
) -> StrategyEvaluationInputs:
    """Run the existing analyzers outside the pure transition boundary."""
    event = _utc(event_at)
    if symbol != "XAUUSDm" or htf_bias not in ("bullish", "bearish"):
        raise GateInputError("gate symbol or side is not executable")
    required = ("H1", "M5", "M15")
    if not all(timeframe in frames for timeframe in required):
        raise GateInputError("required setup timeframe missing")
    sources = tuple(sorted(
        (timeframe, _source_identity(timeframe, frames[timeframe], event))
        for timeframe in frames
    ))
    structure = frames["H1"]
    entry = frames["M5"]
    internal = frames["M15"]
    structure_context = dict(liquidity_context.get("structure_context") or {})
    sweep = detect_liquidity_sweep(
        structure, structure_dir=htf_bias,
        lookback=int(profile.get("liquidity", {}).get("lookback", 20)),
        sweep_window=int(profile.get("liquidity", {}).get("sweep_window", 3)),
    ) or {}
    displacement: dict[str, Any] = {}
    fvgs: list[Any] = []
    internal_structure: dict[str, Any] = {}
    ob_result: dict[str, Any] = {}
    atr = 0.0
    if sweep:
        displacement = detect_displacement(
            entry, htf_bias, atr_period=14,
            impulse_atr_mult=float(profile.get("displacement", {}).get("impulse_atr_mult", 1.2)),
            lookback_candles=int(profile.get("displacement", {}).get("lookback_candles", 3)),
        ) or {}
    tier = displacement_tier_result(profile, displacement)
    tier_rejects = tier["tier"] == "tier_1" and tier["action"] == "log_only"
    if displacement.get("valid") and not tier_rejects:
        fvgs = get_unfilled_fvgs(entry, timeframe="M5", direction=htf_bias) or []
        internal_structure = analyze_market_structure(internal, silent=True) or {}
        internal_event = internal_structure.get("event")
        early_event = (internal_structure.get("early_event") or {}).get("event")
        if internal_event in ("BOS", "CHOCH") or early_event in ("BOS", "CHOCH"):
            atr = float(calculate_atr(entry, 14) or 0.0)
            timing = {"displacement_detected": event.isoformat(), "internal_structure_detected": event.isoformat()}
            if sweep.get("side") in ("buy", "sell"):
                timing["sweep_detected"] = event.isoformat()
            _, variant_failure = structural_variant_result(
                profile=profile, sweep=sweep, displacement=displacement,
                internal=internal_structure, atr=atr, timing=timing,
            )
            if variant_failure is None:
                ob_result = detect_ob_breaker(
                    entry, htf_bias, premium_zone=structure_context.get("premium_zone"),
                    discount_zone=structure_context.get("discount_zone"),
                    equilibrium_level=structure_context.get("equilibrium_level"),
                ) or {}
    payload = {
        "schema": INPUT_SCHEMA,
        "profile": _freeze(profile, profile=True),
        "htf_bias": htf_bias,
        "bias_snapshot": _freeze(bias_snapshot),
        "bias_resolution": _freeze(bias_resolution),
        "liquidity_context": _freeze(liquidity_context),
        "liquidity_signal": _freeze(sweep),
        "displacement": _freeze(displacement),
        "fvgs": _freeze(fvgs),
        "internal_structure": _freeze(internal_structure),
        "ob_result": _freeze(ob_result),
        "atr": _freeze(atr),
        "structure_len": len(structure),
        "entry_rows": _freeze(entry.to_dict("records")),
        "dxy_context": _freeze(dxy_context),
        "news_context": _freeze(news_context),
        "session_context": _freeze(session_context),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    event_id = gate_event_id(
        symbol=symbol, event_at=event, sources=sources, side=htf_bias,
        payload=serialized, config_fingerprint=config.fingerprint(),
    )
    return StrategyEvaluationInputs(symbol, event, event_id, sources, config.fingerprint(), serialized)
