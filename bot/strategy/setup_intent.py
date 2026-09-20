"""Shared conversion of an approved setup into levels and a Phase 3 intent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Mapping, Any

from bot.execution.live_adapter import intent_from_strategy_entry
from bot.strategy.trade_levels import LevelInputs, LevelResult


@dataclass(frozen=True)
class SetupSymbolMetadata:
    symbol: str
    point: float
    stops_level: int
    digits: int
    effective_from: datetime
    effective_until: datetime
    provenance: str

    def validate_at(self, decision_at: datetime) -> None:
        timestamps = (self.effective_from, self.effective_until, decision_at)
        if any(item.tzinfo is None or item.utcoffset() is None for item in timestamps):
            raise ValueError("setup metadata timestamps must be timezone-aware")
        if self.symbol != "XAUUSDm" or not self.provenance:
            raise ValueError("setup metadata identity is invalid")
        if not self.effective_from <= decision_at < self.effective_until:
            raise ValueError("setup metadata is not effective at decision time")
        if not math.isfinite(self.point) or self.point <= 0:
            raise ValueError("setup metadata point must be positive and finite")
        if isinstance(self.digits, bool) or not isinstance(self.digits, int) or not 0 <= self.digits <= 10:
            raise ValueError("setup metadata digits are invalid")
        if isinstance(self.stops_level, bool) or not isinstance(self.stops_level, int) or self.stops_level < 0:
            raise ValueError("setup metadata stops level is invalid")


def level_inputs_from_setup(
    *, context: Mapping[str, Any], entry_frame, metadata: SetupSymbolMetadata,
    decision_at: datetime, profile: Mapping[str, Any], min_rr: float,
    min_rr_buffer: float = 0.10,
) -> LevelInputs:
    """Map the same live fields; do not introduce substitute level formulas."""
    metadata.validate_at(decision_at)
    entry = context.get("entry") or {}
    if not entry or entry_frame is None or entry_frame.empty:
        raise ValueError("approved entry and causal entry frame required")
    if (entry_frame["available_at"] > decision_at).any():
        raise ValueError("future candle in setup level input")
    trigger = float(entry["limit_entry"]) if entry.get("entry_type") == "limit" and entry.get("limit_entry") is not None else float(entry_frame["close"].iloc[-1])
    ob = context.get("ob") or {}
    return LevelInputs(
        direction=entry["direction"], entry_price=trigger,
        entry_mode=entry.get("entry_mode"),
        ob_zone=ob.get("zone") if ob.get("valid") else entry.get("ob_zone"),
        internal_structure=context.get("internal_structure") or {},
        recent_lows=tuple(float(value) for value in entry_frame["low"].tail(10)),
        recent_highs=tuple(float(value) for value in entry_frame["high"].tail(10)),
        structure_context=(context.get("liquidity") or {}).get("structure_context") or {},
        liquidity_pools=tuple((context.get("liquidity") or {}).get("liquidity_pools") or ()),
        atr=float((context.get("market_conditions") or {}).get("atr", 0.0)),
        point=metadata.point, stops_level=metadata.stops_level, digits=metadata.digits,
        level_config=profile.get("execution_levels") or {},
        min_rr=min_rr, min_rr_buffer=min_rr_buffer,
    )


def intent_from_setup_levels(
    *, symbol: str, source_timeframe: str, context: Mapping[str, Any],
    entry_frame, levels: LevelResult, partial_close_fraction: float,
    configuration_id: str,
):
    if levels.stop is None or levels.target is None or not context.get("entry"):
        raise ValueError("setup without valid entry levels cannot create an intent")
    entry = dict(context["entry"])
    ob = context.get("ob") or {}
    if ob.get("valid") and ob.get("zone"):
        entry["ob_zone"] = ob["zone"]
    score = context.get("score") or {}
    return intent_from_strategy_entry(
        symbol=symbol, source_timeframe=source_timeframe,
        entry=entry, entry_frame=entry_frame,
        stop_loss=levels.stop, final_target=levels.target,
        partial_close_fraction=partial_close_fraction,
        configuration_id=configuration_id,
        strategy_metadata={
            "strategy": "SMC_COURTROOM_ORCHESTRATOR",
            "setup_score": score.get("score"), "setup_grade": score.get("grade"),
        },
    )
