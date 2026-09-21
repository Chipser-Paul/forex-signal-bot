from __future__ import annotations

from datetime import timedelta

import pytest

from bot.execution.lifecycle import (
    Direction,
    FillKind,
    LifecycleError,
    LifecycleStatus,
    MarketEvent,
    MarketEventKind,
    ReadinessStyle,
    create_entry_state,
    new_entry_intent,
    process_entry_event,
    record_fill,
)
from tests.phase3.helpers import SIGNAL_AT, SOURCE_OPEN, bar, intent, tick


def test_partial_target_cannot_extend_beyond_final_target():
    with pytest.raises(LifecycleError, match="directionally valid"):
        new_entry_intent(
            symbol="TEST",
            direction=Direction.BUY,
            source_timeframe="M5",
            source_candle_open_time=SOURCE_OPEN,
            signal_available_at=SIGNAL_AT,
            requested_trigger=100.0,
            stop_loss=90.0,
            final_target=105.0,
            readiness_style=ReadinessStyle.IMMEDIATE,
        )


@pytest.mark.parametrize("direction", [Direction.BUY, Direction.SELL])
def test_signal_cannot_fill_from_source_candle(direction):
    entry = intent(direction)
    source = bar(
        "source-event",
        5,
        100.0,
        125.0,
        75.0,
        100.0,
        open_minute=0,
        source_candle_id=entry.source_event_id,
    )
    decision = process_entry_event(create_entry_state(entry), source)
    assert not decision.triggered
    assert decision.reason == "source_candle_barrier"
    assert decision.state.status is LifecycleStatus.WAITING


@pytest.mark.parametrize(
    ("direction", "later", "expected_price", "expected_kind"),
    [
        (Direction.BUY, (102.0, 103.0, 99.0, 101.0), 100.0, FillKind.SIMULATED_TRIGGER),
        (Direction.SELL, (98.0, 101.0, 97.0, 99.0), 100.0, FillKind.SIMULATED_TRIGGER),
        (Direction.BUY, (98.0, 101.0, 97.0, 100.0), 98.0, FillKind.SIMULATED_OPEN),
        (Direction.SELL, (102.0, 103.0, 99.0, 100.0), 102.0, FillKind.SIMULATED_OPEN),
    ],
)
def test_later_bar_uses_deterministic_market_on_trigger_fill(direction, later, expected_price, expected_kind):
    event = bar("later", 10, *later, open_minute=5)
    decision = process_entry_event(create_entry_state(intent(direction)), event)
    assert decision.triggered
    assert decision.proposed_fill_price == expected_price
    assert decision.fill_kind is expected_kind


def test_distinct_bar_open_at_signal_boundary_is_eligible():
    event = MarketEvent(
        event_id="next-open",
        timestamp=SIGNAL_AT,
        symbol="TEST",
        source="historical",
        kind=MarketEventKind.BAR,
        sequence=1,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        bar_open_time=SIGNAL_AT,
    )
    decision = process_entry_event(create_entry_state(intent()), event)
    assert decision.triggered


def test_live_tick_after_signal_can_trigger_with_actual_market_price():
    decision = process_entry_event(create_entry_state(intent()), tick("post-signal", 6, 99.5))
    assert decision.triggered
    assert decision.proposed_fill_price == 99.5
    assert decision.fill_kind is FillKind.LIVE_MARKET


def test_tick_before_signal_is_never_retroactively_evaluated():
    state = create_entry_state(intent())
    early = process_entry_event(state, tick("early", 4, 95.0))
    assert not early.triggered
    assert early.reason == "before_signal_availability"
    later = process_entry_event(early.state, tick("later", 6, 105.0))
    assert not later.triggered


def test_expired_signal_cannot_reopen_on_later_trigger():
    entry = intent(expires_minutes=10)
    expired = process_entry_event(create_entry_state(entry), tick("expiry", 15, 100.0))
    assert expired.state.status is LifecycleStatus.EXPIRED
    late = process_entry_event(expired.state, tick("late", 20, 95.0))
    assert late.state.status is LifecycleStatus.EXPIRED
    assert not late.triggered


def test_duplicate_entry_event_is_idempotent():
    event = tick("same", 6, 105.0)
    first = process_entry_event(create_entry_state(intent()), event)
    second = process_entry_event(first.state, event)
    assert second.reason == "duplicate_event"
    assert second.state == first.state


def test_record_fill_keeps_requested_and_actual_prices_separate():
    event = tick("fill", 6, 99.0)
    decision = process_entry_event(create_entry_state(intent()), event)
    position = record_fill(
        decision.state,
        event,
        fill_price=98.75,
        quantity=1.0,
        fill_kind=FillKind.LIVE_MARKET,
    )
    assert position.requested_entry == 100.0
    assert position.fill_price == 98.75
    assert position.initial_risk_price == 8.75


def test_naive_event_timestamp_is_rejected():
    with pytest.raises(LifecycleError, match="timezone-aware"):
        MarketEvent(
            event_id="naive",
            timestamp=(SOURCE_OPEN + timedelta(minutes=6)).replace(tzinfo=None),
            symbol="TEST",
            source="test",
            kind=MarketEventKind.TICK,
            sequence=1,
            bid=100.0,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_market_price_is_rejected(value):
    with pytest.raises(LifecycleError, match="finite"):
        tick("bad", 6, value)


def test_event_timestamps_cannot_move_backward():
    state = create_entry_state(intent(readiness=ReadinessStyle.PULLBACK))
    state = process_entry_event(state, tick("first", 7, 110.0)).state
    with pytest.raises(LifecycleError, match="backward"):
        process_entry_event(state, tick("older", 6, 99.0))
