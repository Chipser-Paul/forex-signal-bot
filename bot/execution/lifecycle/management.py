from __future__ import annotations

import math
from dataclasses import replace
from typing import Iterable

from .models import (
    ActionConfirmation,
    ActionType,
    Direction,
    ExitReason,
    LifecycleAction,
    LifecycleError,
    LifecycleStatus,
    ManagementConfig,
    ManagementResult,
    MarketEvent,
    MarketEventKind,
    PnlComponent,
    PositionState,
    TradeOutcome,
    finite,
    make_transition,
    positive,
    stable_id,
    validate_position,
)


def _tick_price(position: PositionState, event: MarketEvent) -> float:
    # Closing a buy uses bid; closing a sell uses ask.
    value = event.bid if position.direction is Direction.BUY else event.ask
    if value is None:
        value = event.close
    if value is None:
        raise LifecycleError("management event has no usable exit price")
    return finite(value, "management price")


def _stop_observation(position: PositionState, event: MarketEvent) -> tuple[bool, float | None]:
    stop = position.current_stop
    if event.kind is MarketEventKind.TICK:
        price = _tick_price(position, event)
        hit = price <= stop if position.direction is Direction.BUY else price >= stop
        return hit, price if hit else None
    assert event.open is not None and event.high is not None and event.low is not None
    if position.direction is Direction.BUY:
        if event.open <= stop:
            return True, event.open
        return (True, stop) if event.low <= stop else (False, None)
    if event.open >= stop:
        return True, event.open
    return (True, stop) if event.high >= stop else (False, None)


def _favorable_observation(
    position: PositionState,
    event: MarketEvent,
    level: float,
) -> tuple[bool, float | None]:
    if event.kind is MarketEventKind.TICK:
        price = _tick_price(position, event)
        hit = price >= level if position.direction is Direction.BUY else price <= level
        return hit, price if hit else None
    assert event.open is not None and event.high is not None and event.low is not None
    if position.direction is Direction.BUY:
        if event.open >= level:
            return True, event.open
        return (True, level) if event.high >= level else (False, None)
    if event.open <= level:
        return True, event.open
    return (True, level) if event.low <= level else (False, None)


def _stop_reason(position: PositionState, tolerance: float) -> ExitReason:
    if math.isclose(position.current_stop, position.fill_price, abs_tol=tolerance):
        return ExitReason.BREAK_EVEN
    improved = (
        position.current_stop > position.fill_price
        if position.direction is Direction.BUY
        else position.current_stop < position.fill_price
    )
    return ExitReason.TRAILING_STOP if improved else ExitReason.STOP_LOSS


def _action_id(position: PositionState, event: MarketEvent, kind: ActionType, ordinal: int) -> str:
    return stable_id(position.trade_id, event.event_id, kind.value, ordinal)


def _gross_pnl(
    position: PositionState,
    quantity: float,
    exit_price: float,
    config: ManagementConfig,
) -> float:
    return (
        position.direction.sign
        * (exit_price - position.fill_price)
        * quantity
        * config.pnl_per_price_unit
    )


def _gross_r(position: PositionState, gross_pnl: float, config: ManagementConfig) -> float:
    denominator = position.initial_risk_account_currency
    if denominator is None:
        denominator = (
            position.initial_risk_price
            * position.initial_quantity
            * config.pnl_per_price_unit
        )
    return gross_pnl / denominator if denominator and denominator > 0 else 0.0


def _append_processed(position: PositionState, event: MarketEvent) -> PositionState:
    return replace(
        position,
        processed_event_ids=position.processed_event_ids + (event.event_id,),
        last_processed_event_id=event.event_id,
        last_event_time=event.timestamp,
    )


def _close_component(
    position: PositionState,
    event: MarketEvent,
    config: ManagementConfig,
    *,
    quantity: float,
    price: float,
    reason: ExitReason | str,
    final: bool,
    ordinal: int,
    metadata: dict[str, object] | None = None,
) -> tuple[PositionState, LifecycleAction]:
    quantity = min(finite(quantity, "close quantity"), position.remaining_quantity)
    if quantity <= config.numeric_tolerance:
        raise LifecycleError("close quantity must be positive")
    price = finite(price, "close price")
    kind = ActionType.FINAL_CLOSE if final else ActionType.PARTIAL_CLOSE
    action_id = _action_id(position, event, kind, ordinal)
    if action_id in position.processed_action_ids:
        raise LifecycleError("management action identity was already applied")
    component = PnlComponent(
        action_id=action_id,
        timestamp=event.timestamp,
        quantity=quantity,
        entry_price=position.fill_price,
        exit_price=price,
        gross_pnl=_gross_pnl(position, quantity, price, config),
        reason=reason,
    )
    components = position.pnl_components + (component,)
    gross = sum(item.gross_pnl for item in components)
    closed_quantity = position.closed_quantity + quantity
    remaining = max(0.0, position.initial_quantity - closed_quantity)
    next_status = LifecycleStatus.CLOSED if final else LifecycleStatus.PARTIALLY_CLOSED
    transition = make_transition(
        event_id=event.event_id,
        timestamp=event.timestamp,
        from_status=position.status,
        to_status=next_status,
        reason=str(reason.value if isinstance(reason, ExitReason) else reason),
        metadata=dict(metadata or {}),
    )
    updated = replace(
        position,
        status=next_status,
        remaining_quantity=0.0 if final else remaining,
        closed_quantity=position.initial_quantity if final else closed_quantity,
        partial_close_attempted=True if not final else position.partial_close_attempted,
        partial_close_occurred=True if not final else position.partial_close_occurred,
        realized_gross_pnl=gross,
        current_r_multiple=_gross_r(position, gross, config),
        processed_action_ids=position.processed_action_ids + (action_id,),
        pnl_components=components,
        transitions=position.transitions + (transition,),
        exit_time=event.timestamp if final else position.exit_time,
        exit_price=price if final else position.exit_price,
        exit_reason=reason if final else position.exit_reason,
    )
    action = LifecycleAction(
        action_id=action_id,
        event_id=event.event_id,
        timestamp=event.timestamp,
        symbol=position.symbol,
        trade_id=position.trade_id,
        action_type=kind,
        quantity=quantity,
        requested_price=price,
        reason=reason,
        metadata=dict(metadata or {}),
    )
    return updated, action


def _volume_decimals(step: float) -> int:
    text = f"{step:.12f}".rstrip("0")
    return len(text.split(".", 1)[1]) if "." in text else 0


def _partial_quantity(position: PositionState, config: ManagementConfig) -> tuple[float | None, str | None]:
    requested = position.initial_quantity * config.partial_close_fraction
    units = math.floor((requested + config.numeric_tolerance) / config.volume_step)
    normalized = round(units * config.volume_step, _volume_decimals(config.volume_step))
    if normalized < config.volume_min - config.numeric_tolerance:
        return None, "partial_below_minimum_volume"
    if normalized >= position.remaining_quantity - config.numeric_tolerance:
        return None, "partial_would_close_full_position"
    remainder = position.remaining_quantity - normalized
    if remainder < config.volume_min - config.numeric_tolerance:
        return None, "partial_would_leave_subminimum_remainder"
    return normalized, None


def _skip_partial(
    position: PositionState,
    event: MarketEvent,
    reason: str,
    ordinal: int,
) -> tuple[PositionState, LifecycleAction]:
    action_id = _action_id(position, event, ActionType.PARTIAL_SKIPPED, ordinal)
    updated = replace(
        position,
        partial_close_attempted=True,
        partial_close_skip_reason=reason,
        processed_action_ids=position.processed_action_ids + (action_id,),
    )
    action = LifecycleAction(
        action_id=action_id,
        event_id=event.event_id,
        timestamp=event.timestamp,
        symbol=position.symbol,
        trade_id=position.trade_id,
        action_type=ActionType.PARTIAL_SKIPPED,
        reason=reason,
        metadata={"remaining_quantity": position.remaining_quantity},
    )
    return updated, action


def _favorable_extreme(position: PositionState, event: MarketEvent) -> tuple[float, float]:
    if event.kind is MarketEventKind.BAR:
        assert event.high is not None and event.low is not None
        high, low = event.high, event.low
    else:
        price = _tick_price(position, event)
        high = low = price
    highest = max(position.highest_favorable_price or position.fill_price, high)
    lowest = min(position.lowest_favorable_price or position.fill_price, low)
    return highest, lowest


def _trailing_candidate(
    position: PositionState,
    event: MarketEvent,
    config: ManagementConfig,
    highest: float,
    lowest: float,
) -> tuple[float | None, str | None]:
    candidates: list[tuple[float, str]] = []
    if config.trailing_enabled and event.atr is not None and event.atr > 0:
        distance = max(
            event.atr * config.trailing_atr_multiple,
            config.trailing_min_distance,
        )
        if position.direction is Direction.BUY:
            candidate = highest - distance
            if candidate >= position.fill_price:
                candidates.append((candidate, "atr_trailing"))
        else:
            candidate = lowest + distance
            if candidate <= position.fill_price:
                candidates.append((candidate, "atr_trailing"))
    if event.structure_trail_level is not None:
        structure_level = event.structure_trail_level
        is_protective = (
            position.current_stop < structure_level < position.final_target
            if position.direction is Direction.BUY
            else position.final_target < structure_level < position.current_stop
        )
        if is_protective:
            candidates.append((structure_level, "structure_trailing"))
    if not candidates:
        return None, None
    if position.direction is Direction.BUY:
        candidate, reason = max(candidates, key=lambda item: item[0])
        if candidate <= position.current_stop + config.numeric_tolerance:
            return None, None
    else:
        candidate, reason = min(candidates, key=lambda item: item[0])
        if candidate >= position.current_stop - config.numeric_tolerance:
            return None, None
    return candidate, reason


def _apply_stop_update(
    position: PositionState,
    event: MarketEvent,
    new_stop: float,
    reason: str,
    ordinal: int,
) -> tuple[PositionState, LifecycleAction]:
    action_id = _action_id(position, event, ActionType.MODIFY_STOP, ordinal)
    updated = replace(
        position,
        current_stop=new_stop,
        processed_action_ids=position.processed_action_ids + (action_id,),
    )
    action = LifecycleAction(
        action_id=action_id,
        event_id=event.event_id,
        timestamp=event.timestamp,
        symbol=position.symbol,
        trade_id=position.trade_id,
        action_type=ActionType.MODIFY_STOP,
        new_stop=new_stop,
        reason=reason,
        metadata={"effective_from_next_event": True},
    )
    return updated, action


def _any_favorable_hit(position: PositionState, event: MarketEvent) -> bool:
    partial, _ = _favorable_observation(position, event, position.partial_target)
    target, _ = _favorable_observation(position, event, position.final_target)
    return partial or target


def manage_position(
    position: PositionState,
    event: MarketEvent,
    config: ManagementConfig,
) -> ManagementResult:
    if event.symbol != position.symbol:
        raise LifecycleError("management event symbol does not match position")
    if event.event_id in position.processed_event_ids:
        return ManagementResult(position=position, actions=(), duplicate_event=True)
    if position.status is LifecycleStatus.CLOSED:
        return ManagementResult(position=position, actions=())
    if position.status not in (LifecycleStatus.OPEN, LifecycleStatus.PARTIALLY_CLOSED):
        raise LifecycleError("only open positions can be managed")
    if event.timestamp < position.fill_timestamp:
        raise LifecycleError("management event predates the fill")
    if position.last_event_time is not None and event.timestamp < position.last_event_time:
        raise LifecycleError("management event timestamps cannot move backward")

    actions: list[LifecycleAction] = []
    current = position

    # Existing protection is always evaluated before any favorable or new-stop logic.
    stop_hit, stop_price = _stop_observation(current, event)
    favorable_hit = _any_favorable_hit(current, event)
    if stop_hit:
        assert stop_price is not None
        ambiguous = favorable_hit and event.kind is MarketEventKind.BAR
        current, action = _close_component(
            current,
            event,
            config,
            quantity=current.remaining_quantity,
            price=stop_price,
            reason=_stop_reason(current, config.numeric_tolerance),
            final=True,
            ordinal=0,
            metadata={
                "ambiguity_policy": config.ambiguity_policy.value if ambiguous else None,
                "intrabar_ambiguous": ambiguous,
                "existing_stop_checked_first": True,
            },
        )
        current = replace(current, ambiguity_policy_used=current.ambiguity_policy_used or ambiguous)
        actions.append(action)
        current = _append_processed(current, event)
        return ManagementResult(position=current, actions=tuple(actions))

    if event.emergency_reason:
        exit_price = event.close if event.close is not None else _tick_price(current, event)
        current, action = _close_component(
            current,
            event,
            config,
            quantity=current.remaining_quantity,
            price=exit_price,
            reason=ExitReason.EMERGENCY,
            final=True,
            ordinal=0,
            metadata={"emergency_reason": event.emergency_reason},
        )
        actions.append(action)
        current = _append_processed(current, event)
        return ManagementResult(position=current, actions=tuple(actions))

    partial_hit, partial_price = _favorable_observation(current, event, current.partial_target)
    target_hit, target_price = _favorable_observation(current, event, current.final_target)

    if partial_hit and not current.partial_close_attempted:
        quantity, skip_reason = _partial_quantity(current, config)
        if skip_reason:
            current, action = _skip_partial(current, event, skip_reason, len(actions))
        else:
            assert quantity is not None and partial_price is not None
            current, action = _close_component(
                current,
                event,
                config,
                quantity=quantity,
                price=partial_price,
                reason="PARTIAL_TARGET",
                final=False,
                ordinal=len(actions),
                metadata={"target_r": config.partial_target_r},
            )
        actions.append(action)

    if target_hit:
        assert target_price is not None
        current, action = _close_component(
            current,
            event,
            config,
            quantity=current.remaining_quantity,
            price=target_price,
            reason=ExitReason.TAKE_PROFIT,
            final=True,
            ordinal=len(actions),
            metadata={"partial_processed_same_event": partial_hit},
        )
        actions.append(action)
        current = _append_processed(current, event)
        return ManagementResult(position=current, actions=tuple(actions))

    highest, lowest = _favorable_extreme(current, event)
    current = replace(
        current,
        highest_favorable_price=highest,
        lowest_favorable_price=lowest,
    )
    new_stop, trail_reason = _trailing_candidate(current, event, config, highest, lowest)
    if new_stop is not None and trail_reason is not None:
        current, action = _apply_stop_update(
            current,
            event,
            new_stop,
            trail_reason,
            len(actions),
        )
        actions.append(action)

    current = _append_processed(current, event)
    validate_position(current)
    return ManagementResult(position=current, actions=tuple(actions))


def force_close(
    position: PositionState,
    event: MarketEvent,
    config: ManagementConfig,
    *,
    reason: ExitReason | str = ExitReason.END_OF_DATA,
) -> ManagementResult:
    if position.status is LifecycleStatus.CLOSED:
        return ManagementResult(position=position, actions=())
    if event.event_id in position.processed_event_ids:
        return ManagementResult(position=position, actions=(), duplicate_event=True)
    price = event.close if event.close is not None else _tick_price(position, event)
    closed, action = _close_component(
        position,
        event,
        config,
        quantity=position.remaining_quantity,
        price=price,
        reason=reason,
        final=True,
        ordinal=0,
    )
    return ManagementResult(position=_append_processed(closed, event), actions=(action,))


def reconcile_action_fill(
    position: PositionState,
    action: LifecycleAction,
    actual_price: float,
    config: ManagementConfig,
    actual_quantity: float | None = None,
) -> PositionState:
    """Reconcile planned close accounting with the broker's actual fill."""
    if action.action_type not in (ActionType.PARTIAL_CLOSE, ActionType.FINAL_CLOSE):
        return position
    actual_price = finite(actual_price, "actual close fill")
    quantity = action.quantity if actual_quantity is None else positive(
        actual_quantity,
        "actual close quantity",
    )
    if quantity > action.quantity + 1e-12:
        raise LifecycleError("actual close quantity cannot exceed the requested quantity")
    found = False
    components: list[PnlComponent] = []
    for component in position.pnl_components:
        if component.action_id != action.action_id:
            components.append(component)
            continue
        found = True
        components.append(
            replace(
                component,
                quantity=quantity,
                exit_price=actual_price,
                gross_pnl=_gross_pnl(position, quantity, actual_price, config),
            )
        )
    if not found:
        raise LifecycleError("confirmed fill does not match a lifecycle close action")
    gross = sum(component.gross_pnl for component in components)
    unfilled = float(action.quantity) - quantity
    closed_quantity = position.closed_quantity - unfilled
    remaining_quantity = position.remaining_quantity + unfilled
    final_completed = (
        action.action_type is ActionType.FINAL_CLOSE
        and remaining_quantity <= config.numeric_tolerance
    )
    return replace(
        position,
        pnl_components=tuple(components),
        realized_gross_pnl=gross,
        current_r_multiple=_gross_r(position, gross, config),
        closed_quantity=closed_quantity,
        remaining_quantity=0.0 if final_completed else remaining_quantity,
        status=(
            LifecycleStatus.CLOSED
            if final_completed
            else LifecycleStatus.PARTIALLY_CLOSED
        ),
        exit_time=position.exit_time if final_completed else None,
        exit_price=actual_price if final_completed else None,
        exit_reason=position.exit_reason if final_completed else None,
    )


def reconcile_confirmed_actions(
    original: PositionState,
    planned: ManagementResult,
    confirmations: Iterable[ActionConfirmation],
    config: ManagementConfig,
) -> PositionState:
    """Apply only broker-confirmed actions from an optimistic management plan."""
    actions = {action.action_id: action for action in planned.actions}
    confirmed = {confirmation.action_id: confirmation for confirmation in confirmations}
    unknown = set(confirmed) - set(actions)
    if unknown:
        raise LifecycleError("confirmation does not belong to the management plan")

    current = original
    accepted_any = False
    for action in planned.actions:
        if action.action_type is ActionType.PARTIAL_SKIPPED:
            current = replace(
                current,
                partial_close_attempted=True,
                partial_close_skip_reason=str(action.reason),
                processed_action_ids=current.processed_action_ids + (action.action_id,),
            )
            accepted_any = True
            continue

        confirmation = confirmed.get(action.action_id)
        if confirmation is None:
            continue
        accepted_any = True

        if action.action_type is ActionType.MODIFY_STOP:
            if action.new_stop is None:
                raise LifecycleError("confirmed stop action has no stop price")
            current = replace(
                current,
                current_stop=action.new_stop,
                processed_action_ids=current.processed_action_ids + (action.action_id,),
            )
            continue

        if action.action_type not in (ActionType.PARTIAL_CLOSE, ActionType.FINAL_CLOSE):
            raise LifecycleError("unsupported confirmed lifecycle action")
        if confirmation.executed_quantity is None or confirmation.executed_price is None:
            raise LifecycleError("confirmed close requires executed quantity and price")
        if confirmation.executed_quantity > action.quantity + config.numeric_tolerance:
            raise LifecycleError("confirmed close exceeds its planned quantity")
        if confirmation.executed_quantity > current.remaining_quantity + config.numeric_tolerance:
            raise LifecycleError("confirmed close exceeds remaining position quantity")

        quantity = min(confirmation.executed_quantity, current.remaining_quantity)
        remaining = max(0.0, current.remaining_quantity - quantity)
        component = PnlComponent(
            action_id=action.action_id,
            timestamp=action.timestamp,
            quantity=quantity,
            entry_price=current.fill_price,
            exit_price=confirmation.executed_price,
            gross_pnl=_gross_pnl(current, quantity, confirmation.executed_price, config),
            reason=action.reason or "broker_confirmed_close",
        )
        components = current.pnl_components + (component,)
        gross = sum(item.gross_pnl for item in components)
        closes_position = remaining <= config.numeric_tolerance
        next_status = (
            LifecycleStatus.CLOSED if closes_position else LifecycleStatus.PARTIALLY_CLOSED
        )
        transitions = current.transitions
        if next_status is not current.status:
            transitions += (
                make_transition(
                    event_id=action.event_id,
                    timestamp=action.timestamp,
                    from_status=current.status,
                    to_status=next_status,
                    reason=str(
                        action.reason.value
                        if isinstance(action.reason, ExitReason)
                        else action.reason
                    ),
                ),
            )
        current = replace(
            current,
            status=next_status,
            remaining_quantity=0.0 if closes_position else remaining,
            closed_quantity=current.initial_quantity if closes_position else current.closed_quantity + quantity,
            partial_close_attempted=(
                True
                if action.action_type is ActionType.PARTIAL_CLOSE
                else current.partial_close_attempted
            ),
            partial_close_occurred=(
                True
                if action.action_type is ActionType.PARTIAL_CLOSE
                else current.partial_close_occurred
            ),
            realized_gross_pnl=gross,
            current_r_multiple=_gross_r(current, gross, config),
            processed_action_ids=current.processed_action_ids + (action.action_id,),
            pnl_components=components,
            transitions=transitions,
            exit_time=action.timestamp if closes_position else None,
            exit_price=confirmation.executed_price if closes_position else None,
            exit_reason=action.reason if closes_position else None,
        )

    if not accepted_any:
        return original
    current = replace(
        current,
        highest_favorable_price=planned.position.highest_favorable_price,
        lowest_favorable_price=planned.position.lowest_favorable_price,
        ambiguity_policy_used=(
            current.ambiguity_policy_used or planned.position.ambiguity_policy_used
        ),
        processed_event_ids=planned.position.processed_event_ids,
        last_processed_event_id=planned.position.last_processed_event_id,
        last_event_time=planned.position.last_event_time,
    )
    validate_position(current)
    return current


def normalized_outcome(position: PositionState) -> TradeOutcome:
    if position.status is not LifecycleStatus.CLOSED:
        raise LifecycleError("normalized outcome requires a closed position")
    assert position.exit_time is not None and position.exit_price is not None and position.exit_reason is not None
    return TradeOutcome(
        trade_id=position.trade_id,
        signal_id=position.signal_id,
        symbol=position.symbol,
        direction=position.direction,
        exit_time=position.exit_time,
        exit_price=position.exit_price,
        exit_reason=position.exit_reason,
        initial_quantity=position.initial_quantity,
        realized_gross_pnl=position.realized_gross_pnl,
        gross_r_multiple=position.current_r_multiple,
        components=position.pnl_components,
        adapter_source=str(position.adapter_metadata.get("source", "unknown")),
        ambiguity_policy_used=position.ambiguity_policy_used,
    )


def action_types(actions: Iterable[LifecycleAction]) -> tuple[str, ...]:
    return tuple(action.action_type.value for action in actions)
