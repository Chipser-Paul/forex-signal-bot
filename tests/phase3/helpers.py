from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bot.execution.lifecycle import (
    Direction,
    FillKind,
    ManagementConfig,
    MarketEvent,
    MarketEventKind,
    ReadinessStyle,
    create_entry_state,
    new_entry_intent,
    process_entry_event,
    record_fill,
)


UTC = timezone.utc
SOURCE_OPEN = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
SIGNAL_AT = datetime(2026, 1, 5, 10, 5, tzinfo=UTC)


def intent(
    direction: Direction | str = Direction.BUY,
    *,
    readiness: ReadinessStyle | str = ReadinessStyle.PULLBACK,
    expires_minutes: int | None = 120,
):
    direction = Direction(direction)
    trigger = 100.0
    stop = 90.0 if direction is Direction.BUY else 110.0
    target = 120.0 if direction is Direction.BUY else 80.0
    expiry = None if expires_minutes is None else SIGNAL_AT + timedelta(minutes=expires_minutes)
    return new_entry_intent(
        symbol="TEST",
        direction=direction,
        source_timeframe="M5",
        source_candle_open_time=SOURCE_OPEN,
        signal_available_at=SIGNAL_AT,
        requested_trigger=trigger,
        stop_loss=stop,
        final_target=target,
        readiness_style=readiness,
        expires_at=expiry,
        source_event_id="source-1000",
        source_sequence=0,
        configuration_id="phase3-test",
    )


def bar(
    event_id: str,
    minute: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
    *,
    open_minute: int | None = None,
    atr: float | None = None,
    source_candle_id: str | None = None,
    emergency_reason: str | None = None,
    structure_trail_level: float | None = None,
) -> MarketEvent:
    timestamp = SOURCE_OPEN + timedelta(minutes=minute)
    candle_open = SOURCE_OPEN + timedelta(minutes=open_minute if open_minute is not None else minute - 5)
    return MarketEvent(
        event_id=event_id,
        timestamp=timestamp,
        symbol="TEST",
        source="historical",
        kind=MarketEventKind.BAR,
        sequence=minute,
        open=open_price,
        high=high,
        low=low,
        close=close,
        bar_open_time=candle_open,
        source_candle_id=source_candle_id,
        atr=atr,
        emergency_reason=emergency_reason,
        structure_trail_level=structure_trail_level,
    )


def tick(
    event_id: str,
    minute: int,
    price: float,
    *,
    atr: float | None = None,
    emergency_reason: str | None = None,
    structure_trail_level: float | None = None,
) -> MarketEvent:
    return MarketEvent(
        event_id=event_id,
        timestamp=SOURCE_OPEN + timedelta(minutes=minute),
        symbol="TEST",
        source="live_mock",
        kind=MarketEventKind.TICK,
        sequence=minute,
        bid=price,
        ask=price,
        close=price,
        atr=atr,
        emergency_reason=emergency_reason,
        structure_trail_level=structure_trail_level,
    )


def open_position(
    direction: Direction | str = Direction.BUY,
    *,
    quantity: float = 1.0,
    fill_price: float = 100.0,
):
    entry_intent = intent(direction, readiness=ReadinessStyle.IMMEDIATE)
    event = tick("fill", 6, fill_price)
    decision = process_entry_event(create_entry_state(entry_intent), event)
    assert decision.triggered
    return record_fill(
        decision.state,
        event,
        fill_price=fill_price,
        quantity=quantity,
        fill_kind=FillKind.LIVE_MARKET,
        adapter_metadata={"source": "test"},
    )


def config(**overrides) -> ManagementConfig:
    values = {
        "partial_close_fraction": 0.5,
        "partial_target_r": 1.0,
        "volume_min": 0.01,
        "volume_step": 0.01,
        "pnl_per_price_unit": 1.0,
        "trailing_enabled": False,
    }
    values.update(overrides)
    return ManagementConfig(**values)
