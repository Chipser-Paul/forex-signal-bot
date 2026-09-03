from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime
from typing import Any, Mapping

from .models import (
    Direction,
    EntryDecision,
    EntryIntent,
    EntryMode,
    EntryState,
    FillKind,
    LifecycleError,
    LifecycleStatus,
    MarketEvent,
    MarketEventKind,
    PositionState,
    ReadinessStyle,
    TERMINAL_STATUSES,
    as_utc,
    finite,
    make_transition,
    positive,
    stable_id,
    transition_entry,
)


def new_entry_intent(
    *,
    symbol: str,
    direction: Direction | str,
    source_timeframe: str,
    source_candle_open_time: datetime,
    signal_available_at: datetime,
    requested_trigger: float,
    stop_loss: float,
    final_target: float,
    readiness_style: ReadinessStyle | str,
    partial_close_fraction: float = 0.5,
    partial_target_r: float = 1.0,
    expires_at: datetime | None = None,
    source_event_id: str | None = None,
    source_sequence: int = 0,
    strategy_metadata: Mapping[str, Any] | None = None,
    configuration_id: str = "default",
) -> EntryIntent:
    direction = Direction(direction)
    readiness_style = ReadinessStyle(readiness_style)
    open_time = as_utc(source_candle_open_time, "source candle open time")
    available = as_utc(signal_available_at, "signal availability")
    trigger = finite(requested_trigger, "requested trigger")
    stop = finite(stop_loss, "stop loss")
    risk = abs(trigger - stop)
    positive(risk, "initial risk distance")
    partial_target = trigger + direction.sign * risk * positive(partial_target_r, "partial target R")
    source_id = source_event_id or stable_id(symbol, source_timeframe, open_time.isoformat())
    signal_id = stable_id(
        symbol,
        direction.value,
        source_timeframe,
        open_time.isoformat(),
        available.isoformat(),
        trigger,
        source_id,
        configuration_id,
    )
    return EntryIntent(
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        source_timeframe=source_timeframe,
        source_candle_open_time=open_time,
        signal_available_at=available,
        requested_trigger=trigger,
        entry_mode=EntryMode.MARKET_ON_TRIGGER,
        readiness_style=readiness_style,
        stop_loss=stop,
        final_target=finite(final_target, "final target"),
        initial_risk_distance=risk,
        partial_target=partial_target,
        partial_close_fraction=partial_close_fraction,
        source_event_id=source_id,
        source_sequence=source_sequence,
        expires_at=expires_at,
        strategy_metadata=dict(strategy_metadata or {}),
        configuration_id=configuration_id,
    )


def create_entry_state(intent: EntryIntent) -> EntryState:
    return EntryState(intent=intent, status=LifecycleStatus.CREATED)


def is_price_ready(
    direction: Direction | str,
    readiness_style: ReadinessStyle | str,
    trigger: float,
    observed_price: float,
    tolerance: float = 0.0,
) -> bool:
    direction = Direction(direction)
    readiness_style = ReadinessStyle(readiness_style)
    trigger = finite(trigger, "entry trigger")
    observed = finite(observed_price, "observed price")
    tolerance = finite(tolerance, "entry tolerance")
    if tolerance < 0:
        raise LifecycleError("entry tolerance cannot be negative")
    if readiness_style is ReadinessStyle.IMMEDIATE:
        return True
    if direction is Direction.BUY:
        return observed <= trigger + tolerance
    return observed >= trigger - tolerance


def _source_barrier_applies(intent: EntryIntent, event: MarketEvent) -> bool:
    if event.source_candle_id and event.source_candle_id == intent.source_event_id:
        return True
    if event.kind is MarketEventKind.BAR and event.bar_open_time == intent.source_candle_open_time:
        return True
    return (
        event.timestamp == intent.signal_available_at
        and event.sequence <= intent.source_sequence
    )


def prospective_bar_fill(
    intent: EntryIntent,
    event: MarketEvent,
    tolerance: float = 0.0,
) -> tuple[float, FillKind] | None:
    """Return the deterministic Phase 3 historical fill without changing state."""
    if event.kind is not MarketEventKind.BAR:
        raise LifecycleError("prospective historical fill requires a bar event")
    assert event.open is not None and event.high is not None and event.low is not None
    if intent.readiness_style is ReadinessStyle.IMMEDIATE:
        return event.open, FillKind.SIMULATED_OPEN

    if intent.direction is Direction.BUY:
        threshold = intent.requested_trigger + tolerance
        if event.open <= threshold:
            return event.open, FillKind.SIMULATED_OPEN
        if event.low <= threshold:
            return intent.requested_trigger, FillKind.SIMULATED_TRIGGER
    else:
        threshold = intent.requested_trigger - tolerance
        if event.open >= threshold:
            return event.open, FillKind.SIMULATED_OPEN
        if event.high >= threshold:
            return intent.requested_trigger, FillKind.SIMULATED_TRIGGER
    return None


def _mark_processed(state: EntryState, event: MarketEvent) -> EntryState:
    return replace(
        state,
        processed_event_ids=state.processed_event_ids + (event.event_id,),
        last_event_time=event.timestamp,
    )


def process_entry_event(
    state: EntryState,
    event: MarketEvent,
    *,
    tolerance: float = 0.0,
) -> EntryDecision:
    intent = state.intent
    if event.symbol != intent.symbol:
        raise LifecycleError("entry event symbol does not match intent")
    if event.event_id in state.processed_event_ids:
        return EntryDecision(state=state, triggered=False, reason="duplicate_event")
    if state.status in TERMINAL_STATUSES or state.status is LifecycleStatus.OPEN:
        return EntryDecision(state=state, triggered=False, reason="terminal_state")
    if state.last_event_time is not None and event.timestamp < state.last_event_time:
        raise LifecycleError("entry event timestamps cannot move backward")

    tolerance = finite(tolerance, "entry tolerance")
    if tolerance < 0:
        raise LifecycleError("entry tolerance cannot be negative")

    if intent.expires_at is not None and event.timestamp >= intent.expires_at:
        expired = transition_entry(state, LifecycleStatus.EXPIRED, event, "signal_expired")
        return EntryDecision(state=_mark_processed(expired, event), triggered=False, reason="signal_expired")

    if event.timestamp < intent.signal_available_at or _source_barrier_applies(intent, event):
        waiting = state
        if state.status is LifecycleStatus.CREATED:
            reason = "before_signal_availability" if event.timestamp < intent.signal_available_at else "source_candle_barrier"
            waiting = transition_entry(state, LifecycleStatus.WAITING, event, reason)
        elif state.status is LifecycleStatus.ELIGIBLE:
            waiting = transition_entry(state, LifecycleStatus.WAITING, event, "source_candle_barrier")
        reason = "before_signal_availability" if event.timestamp < intent.signal_available_at else "source_candle_barrier"
        return EntryDecision(state=_mark_processed(waiting, event), triggered=False, reason=reason)

    eligible = state
    if state.status in (LifecycleStatus.CREATED, LifecycleStatus.WAITING):
        eligible = transition_entry(state, LifecycleStatus.ELIGIBLE, event, "post_signal_event_eligible")

    proposed: tuple[float, FillKind] | None
    if event.kind is MarketEventKind.BAR:
        proposed = prospective_bar_fill(intent, event, tolerance)
    else:
        observed = event.price_for(intent.direction)
        proposed = (
            (observed, FillKind.LIVE_MARKET)
            if is_price_ready(
                intent.direction,
                intent.readiness_style,
                intent.requested_trigger,
                observed,
                tolerance,
            )
            else None
        )

    if proposed is None:
        waiting = transition_entry(eligible, LifecycleStatus.WAITING, event, "entry_trigger_not_ready")
        return EntryDecision(
            state=_mark_processed(waiting, event),
            triggered=False,
            reason="entry_trigger_not_ready",
        )

    triggered = transition_entry(
        eligible,
        LifecycleStatus.ENTRY_TRIGGERED,
        event,
        "market_on_trigger_ready",
        {"fill_kind": proposed[1].value},
    )
    return EntryDecision(
        state=_mark_processed(triggered, event),
        triggered=True,
        proposed_fill_price=proposed[0],
        fill_kind=proposed[1],
        reason="market_on_trigger_ready",
    )


def record_fill(
    state: EntryState,
    event: MarketEvent,
    *,
    fill_price: float,
    quantity: float,
    fill_kind: FillKind,
    executed_stop: float | None = None,
    executed_target: float | None = None,
    initial_risk_account_currency: float | None = None,
    adapter_metadata: Mapping[str, Any] | None = None,
) -> PositionState:
    if state.status is not LifecycleStatus.ENTRY_TRIGGERED:
        raise LifecycleError("fill requires an ENTRY_TRIGGERED intent")
    intent = state.intent
    fill = finite(fill_price, "fill price")
    quantity = positive(quantity, "fill quantity")
    stop = intent.stop_loss if executed_stop is None else finite(executed_stop, "executed stop")
    target = intent.final_target if executed_target is None else finite(executed_target, "executed target")
    if intent.direction is Direction.BUY and not (stop < fill < target):
        raise LifecycleError("buy fill must remain between stop and final target")
    if intent.direction is Direction.SELL and not (target < fill < stop):
        raise LifecycleError("sell fill must remain between final target and stop")
    risk = abs(fill - stop)
    positive(risk, "filled initial risk")
    partial_r = abs(intent.partial_target - intent.requested_trigger) / intent.initial_risk_distance
    partial_target = fill + intent.direction.sign * risk * partial_r
    trade_id = stable_id(intent.signal_id, event.event_id, fill_kind.value)
    opened = make_transition(
        event_id=event.event_id,
        timestamp=event.timestamp,
        from_status=LifecycleStatus.ENTRY_TRIGGERED,
        to_status=LifecycleStatus.OPEN,
        reason="fill_recorded",
        metadata={"fill_kind": fill_kind.value, "simulated": fill_kind is not FillKind.LIVE_MARKET},
    )
    risk_currency = None
    if initial_risk_account_currency is not None:
        risk_currency = positive(initial_risk_account_currency, "initial account-currency risk")
    return PositionState(
        trade_id=trade_id,
        signal_id=intent.signal_id,
        symbol=intent.symbol,
        direction=intent.direction,
        status=LifecycleStatus.OPEN,
        requested_entry=intent.requested_trigger,
        fill_price=fill,
        fill_timestamp=event.timestamp,
        fill_kind=fill_kind,
        initial_quantity=quantity,
        remaining_quantity=quantity,
        closed_quantity=0.0,
        initial_stop=stop,
        current_stop=stop,
        final_target=target,
        initial_risk_price=risk,
        initial_risk_account_currency=risk_currency,
        partial_target=partial_target,
        partial_close_fraction=intent.partial_close_fraction,
        highest_favorable_price=fill,
        lowest_favorable_price=fill,
        transitions=state.transitions + (opened,),
        adapter_metadata=dict(adapter_metadata or {}),
    )
