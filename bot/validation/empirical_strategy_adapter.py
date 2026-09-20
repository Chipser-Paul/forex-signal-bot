"""Offline causal acquisition and shared production setup-gate evaluation.

This module performs no broker, network or filesystem access. Evaluation is
synthetic-only until complete parity and plan supersession are verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from types import MappingProxyType
from typing import Mapping

import pandas as pd

from bot.analysis.bias_engine import BIAS_TIMEFRAMES, DEFAULT_BARS, bias_snapshot_from_frames, resolve_trade_bias
from bot.analysis.dxy_filter import build_synthetic_dxy_from_frames, dxy_context_from_values
from bot.analysis.liquidity_map import build_liquidity_map_from_frames
from bot.data.candles import CandleDataError, as_utc_timestamp, causal_snapshot
from bot.strategy.models import StrategySide
from bot.strategy.config import StrategyConfig
from bot.strategy.setup_state import SetupStateRecord
from bot.strategy.setup_intent import (
    SetupSymbolMetadata, intent_from_setup_levels, level_inputs_from_setup,
)
from bot.strategy.trade_levels import build_trade_levels
from bot.state.gate_inputs import StrategyEvaluationInputs, build_gate_inputs
from bot.state.gate_reducer import StrategyGateTransition, evaluate_strategy_gates
from bot.state.orchestrator import OrchestratorAcquisition, StrategyOrchestrator
from bot.utils.session_clock import get_session_context
from config.symbol_profiles import get_symbol_profile
from config.symbol_profiles.xauusdm import PROFILE
from strategies.smc_engine.market_structure import CONDITION_ATR_WINDOW
from strategies.smc_engine.market_structure import analyze_market_structure
from strategies.smc_engine.strategy_state import StrategyState


REQUIRED_TIMEFRAMES = ("M5", "M15", "H1", "H4", "D1", "W1")
MAPPING_VERSION = "phase8n.empirical-decision-mapping.v2-setup-replay"


class EmpiricalMappingError(ValueError):
    """An empirical input cannot be translated without changing semantics."""


@dataclass(frozen=True)
class PreparedBias:
    decision_at: datetime
    requested_side: StrategySide
    resolution: Mapping[str, object]
    snapshot: Mapping[str, object]
    source_open_times: Mapping[str, datetime]


def prepare_causal_frames(
    normalized: Mapping[str, pd.DataFrame], decision_at: datetime,
) -> Mapping[str, pd.DataFrame]:
    """Select closed, bounded production timeframe inputs without OHLC fill."""
    timestamp = as_utc_timestamp(decision_at, field="decision_at")
    if PROFILE["entry_tf"] != "M5":
        raise EmpiricalMappingError("PRODUCTION_ENTRY_TIMEFRAME_DRIFT")
    if set(normalized) != set(REQUIRED_TIMEFRAMES):
        raise EmpiricalMappingError("MISSING_OR_UNEXPECTED_TIMEFRAME")
    result: dict[str, pd.DataFrame] = {}
    for timeframe in REQUIRED_TIMEFRAMES:
        lookback = DEFAULT_BARS.get(timeframe, PROFILE["entry_bars"])
        frame = causal_snapshot(normalized[timeframe], timestamp, max_bars=lookback)
        if len(frame) < CONDITION_ATR_WINDOW:
            raise EmpiricalMappingError(f"INSUFFICIENT_CAUSAL_HISTORY:{timeframe}")
        if (frame["available_at"] > timestamp).any():
            raise CandleDataError("future candle in empirical snapshot")
        result[timeframe] = frame
    return MappingProxyType(result)


def derive_causal_bias(
    normalized: Mapping[str, pd.DataFrame], decision_at: datetime,
) -> PreparedBias:
    """Use the existing W1/D1/H4/H1/M15 bias calculation and resolver."""
    frames = prepare_causal_frames(normalized, decision_at)
    snapshot = bias_snapshot_from_frames("XAUUSDm", frames, silent=True)
    resolution = resolve_trade_bias(snapshot)
    requested = {
        "bullish": StrategySide.LONG,
        "bearish": StrategySide.SHORT,
    }.get(str(resolution["direction"]), StrategySide.FLAT)
    sources = {
        tf: frames[tf]["open_time"].iloc[-1].to_pydatetime()
        for tf in BIAS_TIMEFRAMES
    }
    return PreparedBias(
        decision_at=as_utc_timestamp(decision_at).to_pydatetime(),
        requested_side=requested,
        resolution=MappingProxyType(dict(resolution)),
        snapshot=MappingProxyType(dict(snapshot)),
        source_open_times=MappingProxyType(sources),
    )


def prepare_setup_inputs(
    normalized: Mapping[str, pd.DataFrame], decision_at: datetime, *,
    dxy_context: Mapping[str, object], news_context: Mapping[str, object],
    config: StrategyConfig,
) -> StrategyEvaluationInputs:
    """Build the identical aggregate from already accepted replay frames."""
    frames = prepare_causal_frames(normalized, decision_at)
    bias = bias_snapshot_from_frames("XAUUSDm", frames, silent=True)
    resolution = resolve_trade_bias(bias)
    profile = get_symbol_profile("XAUUSDm")
    liquidity_frames = {
        "H1": frames["H1"].tail(320), "M15": frames["M15"].tail(320),
        "D1": frames["D1"].tail(10), "W1": frames["W1"].tail(10),
    }
    liquidity = build_liquidity_map_from_frames("XAUUSDm", liquidity_frames, silent=True)
    setup_frames = {
        "H1": frames["H1"].tail(int(profile["structure_bars"])),
        "M5": frames["M5"].tail(int(profile["entry_bars"])),
        "M15": frames["M15"].tail(220),
    }
    return build_gate_inputs(
        symbol="XAUUSDm", event_at=decision_at, frames=setup_frames,
        profile=profile, htf_bias=str(resolution["direction"]),
        bias_snapshot=bias, bias_resolution=resolution,
        liquidity_context=liquidity, dxy_context=dxy_context,
        news_context=news_context, session_context=get_session_context(decision_at),
        config=config,
    )


def prepare_dxy_context(
    constituent_frames: Mapping[str, pd.DataFrame], gold_structure: Mapping[str, object],
    decision_at: datetime,
) -> dict[str, object]:
    """Share the live basket and correlation reducer, including its boundaries."""
    values, count, _diagnostics = build_synthetic_dxy_from_frames(
        dict(constituent_frames), "H1", 100, decision_at,
    )
    gold = {
        "direction": gold_structure.get("structure", "neutral"),
        "state": gold_structure.get("state", "range"),
        "lead_bias": (gold_structure.get("lead_bias") or {}).get("direction"),
    }
    return dxy_context_from_values(gold, values, count)


def historical_acquisition(
    normalized: Mapping[str, pd.DataFrame], *,
    constituent_frames: Mapping[str, pd.DataFrame], decision_at: datetime,
    news_context: Mapping[str, object],
) -> OrchestratorAcquisition:
    """Expose exactly the production acquisition calls over accepted inputs."""
    decision = as_utc_timestamp(decision_at).to_pydatetime()
    candle_inputs = {name: frame.copy(deep=True) for name, frame in normalized.items()}
    constituents = {name: frame.copy(deep=True) for name, frame in constituent_frames.items()}
    news_payload = json.dumps(dict(news_context), sort_keys=True, separators=(",", ":"), allow_nan=False)

    def candles(symbol: str, timeframe: str, bars: int):
        if symbol != "XAUUSDm" or timeframe not in REQUIRED_TIMEFRAMES:
            raise EmpiricalMappingError("UNSUPPORTED_ACQUISITION")
        frame = candle_inputs.get(timeframe)
        if frame is None:
            return None
        return causal_snapshot(frame, decision, max_bars=bars)

    def require_symbol(symbol: str):
        if symbol != "XAUUSDm":
            raise EmpiricalMappingError("SYMBOL_NOT_EXECUTABLE")

    def session(now: datetime):
        if now != decision:
            raise EmpiricalMappingError("ACQUISITION_EVENT_TIME_MISMATCH")
        return get_session_context(now)

    def news(symbol: str, *, now: datetime):
        require_symbol(symbol)
        if now != decision:
            raise EmpiricalMappingError("ACQUISITION_EVENT_TIME_MISMATCH")
        return json.loads(news_payload)

    def bias(symbol: str, *, silent: bool):
        require_symbol(symbol)
        return bias_snapshot_from_frames(symbol, {
            tf: candles(symbol, tf, DEFAULT_BARS[tf]) for tf in BIAS_TIMEFRAMES
        }, silent=silent)

    def liquidity(symbol: str, *, silent: bool):
        require_symbol(symbol)
        return build_liquidity_map_from_frames(symbol, {
            tf: candles(symbol, tf, bars)
            for tf, bars in (("H1", 320), ("M15", 320), ("D1", 10), ("W1", 10))
        }, silent=silent)

    def dxy(symbol: str, *, silent: bool, decision_timestamp):
        require_symbol(symbol)
        if decision_timestamp != decision:
            raise EmpiricalMappingError("ACQUISITION_EVENT_TIME_MISMATCH")
        gold_frame = candles(symbol, "H1", 220)
        structure = analyze_market_structure(gold_frame, silent=silent) if gold_frame is not None and not gold_frame.empty else {}
        return prepare_dxy_context(constituents, structure or {}, decision)

    return OrchestratorAcquisition(candles, session, news, bias, liquidity, dxy)


@dataclass(frozen=True)
class HistoricalConcurrencyGate:
    """Injected equivalent of the legacy count gate, not a risk authority."""
    max_concurrent_trades: int

    def can_open_more_trades(self, active_trade_count: int) -> bool:
        return active_trade_count < self.max_concurrent_trades


def evaluate_historical_orchestration(
    normalized: Mapping[str, pd.DataFrame], *,
    constituent_frames: Mapping[str, pd.DataFrame], decision_at: datetime,
    news_context: Mapping[str, object], prior_state: SetupStateRecord,
    active_trade_count: int, max_concurrent_trades: int,
):
    """Run the supported wrapper with read-only acquisition and no diagnostics."""
    from bot.strategy.setup_state import restore_setup_for_evaluation

    state = restore_setup_for_evaluation(prior_state, decision_at)
    acquisition = historical_acquisition(
        normalized, constituent_frames=constituent_frames,
        decision_at=decision_at, news_context=news_context,
    )
    result = StrategyOrchestrator(
        risk_engine=HistoricalConcurrencyGate(max_concurrent_trades),
        acquisition=acquisition, emit_diagnostics=False,
    ).evaluate_symbol(
        "XAUUSDm", state, event_at=decision_at, account_balance=0,
        daily_pnl=0, active_trade_count=active_trade_count,
    )
    return result, getattr(state, "_gate_record", None)


@dataclass(frozen=True)
class EvaluatedSetup:
    transition: StrategyGateTransition
    levels_json: str | None
    intent_json: str | None


def consume_confirmed_historical_entry(recovery, binding, position):
    """Consume only after Phase 7 fill journal durability, never on a trigger.

    The injected shared coordinator reads the run's authoritative persisted
    fills. No empirical input or broker is acquired here.
    """
    return recovery.confirm(binding, position=position)


def evaluate_setup_inputs(
    prior_state: SetupStateRecord, inputs: StrategyEvaluationInputs,
    config: StrategyConfig, *, metadata: SetupSymbolMetadata,
    min_rr: float, partial_close_fraction: float,
) -> EvaluatedSetup:
    """Call the production reducer and existing level/intent constructors."""
    transition = evaluate_strategy_gates(prior_state, inputs, inputs.event_at, config)
    result = transition.result()
    if result["action"] != "candidate_ready":
        return EvaluatedSetup(transition, None, None)
    data = inputs.decoded()
    frame = pd.DataFrame(data["entry_rows"])
    for field in ("open_time", "available_at"):
        frame[field] = pd.to_datetime(frame[field], utc=True)
    context = dict(result["context"])
    context["market_conditions"] = result["market_conditions"]
    levels = build_trade_levels(level_inputs_from_setup(
        context=context, entry_frame=frame, metadata=metadata,
        decision_at=inputs.event_at, profile=data["profile"], min_rr=min_rr,
    ))
    levels_json = json.dumps(
        {"stop": levels.stop, "target": levels.target, "reason": levels.reason},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    if levels.stop is None or levels.target is None:
        return EvaluatedSetup(transition, levels_json, None)
    intent = intent_from_setup_levels(
        symbol=inputs.symbol, source_timeframe="M5", context=context,
        entry_frame=frame, levels=levels, partial_close_fraction=partial_close_fraction,
        configuration_id=f"{inputs.symbol}:M5:phase3",
    )
    from bot.execution.lifecycle.serialization import entry_intent_to_payload

    return EvaluatedSetup(transition, levels_json, json.dumps(
        entry_intent_to_payload(intent), sort_keys=True, separators=(",", ":"), allow_nan=False,
    ))
