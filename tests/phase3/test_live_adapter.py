from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from bot.execution.lifecycle import ActionType, Direction, LifecycleAction, stable_id
from bot.execution.live_adapter import (
    dispatch_actions,
    intent_from_strategy_entry,
    management_config_from_live,
    market_event_from_tick,
    order_request_for_action,
)


def test_tick_normalization_uses_broker_utc_time_and_bid_ask():
    tick = SimpleNamespace(time_msc=1_767_610_000_123, bid=99.9, ask=100.1)
    event = market_event_from_tick("TEST", tick)
    assert event.timestamp.tzinfo is timezone.utc
    assert event.sequence == tick.time_msc
    assert event.bid == 99.9
    assert event.ask == 100.1


def test_tick_without_broker_time_requires_explicit_aware_time():
    tick = SimpleNamespace(time_msc=0, time=0, bid=99.9, ask=100.1)
    with pytest.raises(ValueError, match="broker timestamp"):
        market_event_from_tick("TEST", tick)
    event = market_event_from_tick(
        "TEST",
        tick,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert event.timestamp == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_strategy_entry_becomes_source_candle_aware_intent():
    frame = pd.DataFrame(
        {
            "open_time": [pd.Timestamp("2026-01-01T10:00:00Z")],
            "available_at": [pd.Timestamp("2026-01-01T10:05:00Z")],
            "close": [100.0],
        }
    )
    result = intent_from_strategy_entry(
        symbol="TEST",
        source_timeframe="M5",
        entry={"direction": "buy", "entry_type": "limit", "limit_entry": 99.0},
        entry_frame=frame,
        stop_loss=90.0,
        final_target=120.0,
        partial_close_fraction=0.5,
        configuration_id="profile-v1",
    )
    assert result.requested_trigger == 99.0
    assert result.source_candle_open_time == datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    assert result.signal_available_at == datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc)


def test_management_config_uses_existing_profile_and_symbol_metadata():
    info = SimpleNamespace(point=0.01, volume_min=0.02, volume_step=0.01, trade_contract_size=100.0)
    result = management_config_from_live(
        profile={"trailing": {"mode": "atr_3x", "atr_mult": 3.0, "min_distance_points": 100}},
        symbol_info=info,
        partial_close_fraction=0.5,
    )
    assert result.volume_min == 0.02
    assert result.trailing_min_distance == 1.0
    assert result.pnl_per_price_unit == 100.0


def _action(kind: ActionType, **kwargs):
    return LifecycleAction(
        action_id=stable_id("action", kind.value),
        event_id="event",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        symbol="TEST",
        trade_id="trade",
        action_type=kind,
        **kwargs,
    )


def test_order_translation_separates_partial_close_and_stop_modification():
    constants = {
        "TRADE_ACTION_DEAL": 1,
        "TRADE_ACTION_SLTP": 2,
        "ORDER_TYPE_BUY": 3,
        "ORDER_TYPE_SELL": 4,
    }
    partial = order_request_for_action(
        _action(ActionType.PARTIAL_CLOSE, quantity=0.5),
        symbol="TEST",
        ticket=7,
        direction=Direction.BUY,
        current_tp=120.0,
        bid=110.0,
        ask=110.1,
        constants=constants,
        digits=2,
        deviation=5,
        magic=771234,
    )
    modify = order_request_for_action(
        _action(ActionType.MODIFY_STOP, new_stop=100.123),
        symbol="TEST",
        ticket=7,
        direction=Direction.BUY,
        current_tp=120.0,
        bid=110.0,
        ask=110.1,
        constants=constants,
        digits=2,
        deviation=5,
        magic=771234,
    )
    assert partial["action"] == 1 and partial["volume"] == 0.5
    assert modify == {"action": 2, "symbol": "TEST", "position": 7, "sl": 100.12, "tp": 120.0}


def test_legacy_dispatch_is_incapable_of_broker_mutation():
    action = _action(ActionType.PARTIAL_CLOSE, quantity=0.5)
    calls = []
    with pytest.raises(RuntimeError, match="disabled"):
        dispatch_actions(
            (action,),
            request_builder=lambda _action: {"safe": True},
            send_order=lambda request: calls.append(request),
            success_retcode=10009,
        )
    assert calls == []
