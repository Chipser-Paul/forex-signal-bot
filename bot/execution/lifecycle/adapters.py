from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .entry import create_entry_state, process_entry_event, record_fill
from .management import manage_position, normalized_outcome
from .models import (
    EntryIntent,
    EntryState,
    FillKind,
    LifecycleAction,
    ManagementConfig,
    MarketEvent,
    MarketEventKind,
    PositionState,
    TradeOutcome,
)


FillResolver = Callable[[EntryIntent, MarketEvent, float], float]


@dataclass(frozen=True)
class LifecycleRun:
    entry_state: EntryState
    position: PositionState | None
    actions: tuple[LifecycleAction, ...]
    outcome: TradeOutcome | None


def _run(
    *,
    intent: EntryIntent,
    events: Iterable[MarketEvent],
    quantity: float,
    config: ManagementConfig,
    required_kind: MarketEventKind,
    fill_resolver: FillResolver | None,
    source: str,
    tolerance: float,
) -> LifecycleRun:
    entry_state = create_entry_state(intent)
    position: PositionState | None = None
    actions: list[LifecycleAction] = []

    for event in events:
        if event.kind is not required_kind:
            raise ValueError(f"{source} adapter received {event.kind.value} event")
        if position is None:
            decision = process_entry_event(entry_state, event, tolerance=tolerance)
            entry_state = decision.state
            if not decision.triggered:
                continue
            assert decision.proposed_fill_price is not None and decision.fill_kind is not None
            fill_price = decision.proposed_fill_price
            fill_kind = decision.fill_kind
            if fill_resolver is not None:
                fill_price = fill_resolver(intent, event, fill_price)
                fill_kind = FillKind.LIVE_MARKET
            position = record_fill(
                entry_state,
                event,
                fill_price=fill_price,
                quantity=quantity,
                fill_kind=fill_kind,
                adapter_metadata={"source": source, "cost_basis": "gross_before_costs"},
            )
            # The eligible fill event is also the first management observation.
            # This intentionally applies conservative entry-bar ambiguity handling.
            result = manage_position(position, event, config)
            position = result.position
            actions.extend(result.actions)
            continue

        result = manage_position(position, event, config)
        position = result.position
        actions.extend(result.actions)

    outcome = normalized_outcome(position) if position is not None and position.exit_time is not None else None
    return LifecycleRun(
        entry_state=entry_state,
        position=position,
        actions=tuple(actions),
        outcome=outcome,
    )


def run_historical_lifecycle(
    intent: EntryIntent,
    events: Iterable[MarketEvent],
    *,
    quantity: float,
    config: ManagementConfig,
    tolerance: float = 0.0,
) -> LifecycleRun:
    return _run(
        intent=intent,
        events=events,
        quantity=quantity,
        config=config,
        required_kind=MarketEventKind.BAR,
        fill_resolver=None,
        source="historical",
        tolerance=tolerance,
    )


def run_live_mock_lifecycle(
    intent: EntryIntent,
    events: Iterable[MarketEvent],
    *,
    quantity: float,
    config: ManagementConfig,
    fill_resolver: FillResolver | None = None,
    tolerance: float = 0.0,
) -> LifecycleRun:
    return _run(
        intent=intent,
        events=events,
        quantity=quantity,
        config=config,
        required_kind=MarketEventKind.TICK,
        fill_resolver=fill_resolver,
        source="live_mock",
        tolerance=tolerance,
    )


def normalized_trace(run: LifecycleRun) -> tuple[dict[str, object], ...]:
    transitions = run.position.transitions if run.position is not None else run.entry_state.transitions
    trace: list[dict[str, object]] = [
        {
            "kind": "transition",
            "from": transition.from_status.value,
            "to": transition.to_status.value,
            "reason": transition.reason,
        }
        for transition in transitions
    ]
    trace.extend(
        {
            "kind": "action",
            "action": action.action_type.value,
            "quantity": round(action.quantity, 10),
            "reason": action.reason.value if hasattr(action.reason, "value") else action.reason,
            "new_stop": None if action.new_stop is None else round(action.new_stop, 10),
        }
        for action in run.actions
    )
    return tuple(trace)
