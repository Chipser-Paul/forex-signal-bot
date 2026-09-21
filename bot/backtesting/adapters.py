from __future__ import annotations

from dataclasses import replace

from bot.execution.lifecycle.entry import process_entry_event, record_fill
from bot.execution.lifecycle.management import manage_position, reconcile_confirmed_actions
from bot.execution.lifecycle.models import (
    ActionConfirmation,
    ActionType,
    Direction,
    EntryDecision,
    EntryState,
    FillKind,
    LifecycleStatus,
    ManagementConfig,
    MarketEvent,
    MarketEventKind,
    PositionState,
    stable_id as lifecycle_stable_id,
)

from .engine import HistoricalExecutionEngine
from .models import BidAskBar, HistoricalExecutionError, HistoricalQuote, Side


def quote_event(
    quote: HistoricalQuote,
    *,
    sequence: int,
    atr: float | None = None,
) -> MarketEvent:
    return MarketEvent(
        event_id=lifecycle_stable_id(quote.dataset_id, quote.sequence_id),
        timestamp=quote.timestamp,
        symbol=quote.symbol,
        source="phase7_historical_quote",
        kind=MarketEventKind.TICK,
        sequence=sequence,
        bid=quote.bid,
        ask=quote.ask,
        atr=atr,
        metadata={"dataset_id": quote.dataset_id, "observed_bid_ask": True},
    )


def bar_event(
    bar: BidAskBar,
    *,
    direction: Direction,
    sequence: int,
    purpose: str,
) -> MarketEvent:
    if purpose not in {"entry", "management"}:
        raise HistoricalExecutionError("bar adapter purpose must be entry or management")
    use_ask = (purpose == "entry" and direction is Direction.BUY) or (
        purpose == "management" and direction is Direction.SELL
    )
    prefix = "ask" if use_ask else "bid"
    return MarketEvent(
        event_id=lifecycle_stable_id(bar.dataset_id, bar.sequence_id, purpose, direction.value),
        timestamp=bar.available_at,
        symbol=bar.symbol,
        source="phase7_historical_bar",
        kind=MarketEventKind.BAR,
        sequence=sequence,
        open=getattr(bar, f"{prefix}_open"),
        high=getattr(bar, f"{prefix}_high"),
        low=getattr(bar, f"{prefix}_low"),
        close=getattr(bar, f"{prefix}_close"),
        bar_open_time=bar.open_time,
        source_candle_id=lifecycle_stable_id(bar.symbol, bar.dataset_id, bar.open_time.isoformat()),
        metadata={"quote_side": prefix, "dataset_id": bar.dataset_id},
    )


def process_quote_entry(
    engine: HistoricalExecutionEngine,
    state: EntryState,
    quote: HistoricalQuote,
    *,
    sequence: int,
    quantity: float,
    tolerance: float = 0.0,
    available_volume: float | None = None,
    setup_recovery=None,
    setup_record=None,
    fill_journal=None,
) -> tuple[EntryDecision, PositionState | None]:
    event = quote_event(quote, sequence=sequence)
    decision = process_entry_event(state, event, tolerance=tolerance)
    if not decision.triggered:
        return decision, None
    intent = decision.state.intent
    fill_kind = FillKind.SIMULATED_TRIGGER
    trade_id = lifecycle_stable_id(intent.signal_id, event.event_id, fill_kind.value)
    direction = Side.BUY if intent.direction is Direction.BUY else Side.SELL
    action_id = lifecycle_stable_id(intent.signal_id, event.event_id, "historical-entry")
    binding = None
    if setup_recovery is not None:
        if setup_record is None or fill_journal is None:
            raise HistoricalExecutionError("setup recovery requires a durable decision and fill journal")
        binding = setup_recovery.prepare(
            setup_record, intent, action_id=action_id, trade_id=trade_id, entry_event=event, tolerance=tolerance,
        )
    try:
        _historical_position, fill = engine.open_market(
            action_id=action_id,
            trade_id=trade_id,
            direction=direction,
            requested_volume=quantity,
            stop_price=intent.stop_loss,
            target_price=intent.final_target,
            quote=quote,
            signal_available_at=intent.signal_available_at,
            source_event_id=intent.source_event_id,
            market_event_id=event.event_id,
            available_volume=available_volume,
        )
    except HistoricalExecutionError:
        if binding is not None:
            rejected = next((item for item in reversed(engine.rejections) if item["action_id"] == action_id), None)
            if rejected is not None:
                fill_journal.publish_rejection(binding, rejected)
                setup_recovery.confirm(binding)
        raise
    if binding is not None:
        fill_journal.publish(fill)
        consumed = setup_recovery.confirm(binding)
        if consumed.outcome not in ("CONSUMED", "DUPLICATE_IGNORED"):
            raise HistoricalExecutionError("confirmed historical fill requires setup reconciliation")
    position = record_fill(
        decision.state,
        event,
        fill_price=fill.fill_price,
        quantity=fill.volume,
        fill_kind=fill_kind,
        adapter_metadata={
            "source": "phase7_historical_execution",
            "fill_id": fill.fill_id,
            "position_id": fill.position_id,
            "fidelity": engine.policy.fidelity.value,
        },
    )
    if position.trade_id != trade_id:
        raise HistoricalExecutionError("historical and lifecycle trade identities diverged")
    return decision, position


def process_bar_entry(
    engine: HistoricalExecutionEngine,
    state: EntryState,
    bar: BidAskBar,
    *,
    sequence: int,
    quantity: float,
    tolerance: float = 0.0,
    available_volume: float | None = None,
) -> tuple[EntryDecision, PositionState | None]:
    intent = state.intent
    event = bar_event(bar, direction=intent.direction, sequence=sequence, purpose="entry")
    decision = process_entry_event(state, event, tolerance=tolerance)
    if not decision.triggered:
        return decision, None
    assert decision.proposed_fill_price is not None and decision.fill_kind is not None
    observed_spread = max(
        bar.ask_open - bar.bid_open,
        bar.ask_high - bar.bid_high,
        bar.ask_low - bar.bid_low,
        bar.ask_close - bar.bid_close,
    )
    if intent.direction is Direction.BUY:
        ask, bid = decision.proposed_fill_price, decision.proposed_fill_price - observed_spread
        direction = Side.BUY
    else:
        bid, ask = decision.proposed_fill_price, decision.proposed_fill_price + observed_spread
        direction = Side.SELL
    execution_quote = HistoricalQuote(
        symbol=bar.symbol,
        timestamp=bar.available_at,
        bid=bid,
        ask=ask,
        source=f"{bar.source}:conservative-bar-fill",
        dataset_id=bar.dataset_id,
        sequence_id=f"{bar.sequence_id}:entry",
    )
    fill_kind = decision.fill_kind
    trade_id = lifecycle_stable_id(intent.signal_id, event.event_id, fill_kind.value)
    _, fill = engine.open_market(
        action_id=lifecycle_stable_id(intent.signal_id, event.event_id, "historical-bar-entry"),
        trade_id=trade_id,
        direction=direction,
        requested_volume=quantity,
        stop_price=intent.stop_loss,
        target_price=intent.final_target,
        quote=execution_quote,
        signal_available_at=intent.signal_available_at,
        source_event_id=intent.source_event_id,
        market_event_id=event.event_id,
        available_volume=available_volume,
    )
    position = record_fill(
        decision.state,
        event,
        fill_price=fill.fill_price,
        quantity=fill.volume,
        fill_kind=fill_kind,
        adapter_metadata={
            "source": "phase7_historical_bar",
            "fill_id": fill.fill_id,
            "position_id": fill.position_id,
            "fidelity": engine.policy.fidelity.value,
            "intrabar_path": "unknown_conservative",
        },
    )
    return decision, position


def manage_quote_position(
    engine: HistoricalExecutionEngine,
    position: PositionState,
    quote: HistoricalQuote,
    *,
    sequence: int,
    config: ManagementConfig,
    atr: float | None = None,
) -> PositionState:
    event = quote_event(quote, sequence=sequence, atr=atr)
    planned = manage_position(position, event, config)
    confirmations: list[ActionConfirmation] = []
    historical_position_id = str(position.adapter_metadata.get("position_id", ""))
    if not historical_position_id:
        raise HistoricalExecutionError("lifecycle position has no historical position identity")

    for action in planned.actions:
        if action.action_type is ActionType.PARTIAL_SKIPPED:
            continue
        if action.action_type is ActionType.MODIFY_STOP:
            historical = engine.positions[historical_position_id]
            if action.new_stop is None:
                raise HistoricalExecutionError("stop action has no absolute stop price")
            loosens = (
                historical.direction is Side.BUY and action.new_stop < historical.stop_price
            ) or (
                historical.direction is Side.SELL and action.new_stop > historical.stop_price
            )
            if loosens:
                raise HistoricalExecutionError("historical stop modification cannot loosen protection")
            engine.positions[historical_position_id] = replace(historical, stop_price=action.new_stop)
            confirmations.append(ActionConfirmation(action_id=action.action_id))
            continue
        if action.action_type not in (ActionType.PARTIAL_CLOSE, ActionType.FINAL_CLOSE):
            raise HistoricalExecutionError("unsupported lifecycle management action")
        reason = action.reason.value if hasattr(action.reason, "value") else str(action.reason)
        limit_fill = reason == "TAKE_PROFIT"
        fill = engine.close_market(
            action_id=action.action_id,
            position_id=historical_position_id,
            quote=quote,
            requested_volume=action.quantity,
            reason_code=reason,
            reference_override=action.requested_price,
            limit_fill=limit_fill,
        )
        confirmations.append(
            ActionConfirmation(
                action_id=action.action_id,
                executed_quantity=fill.volume,
                executed_price=fill.fill_price,
            )
        )
    confirmed = reconcile_confirmed_actions(position, planned, confirmations, config)
    if confirmed.status is LifecycleStatus.CLOSED:
        historical = engine.positions[historical_position_id]
        if historical.remaining_volume > config.numeric_tolerance:
            raise HistoricalExecutionError("lifecycle closed before historical volume reconciled")
    return confirmed
