from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd

from bot.execution.lifecycle import (
    Direction,
    FillKind,
    ReadinessStyle,
    create_entry_state,
    new_entry_intent,
    process_entry_event,
    record_fill,
)
from bot.execution.lifecycle.serialization import update_trade_record
from bot.execution.live_adapter import market_event_from_tick


def _frame(periods: int, frequency: str = "5min") -> pd.DataFrame:
    opens = pd.date_range("2026-01-05T08:00:00Z", periods=periods, freq=frequency)
    values = [100.0 + index * 0.01 for index in range(periods)]
    return pd.DataFrame(
        {
            "open_time": opens,
            "available_at": opens + pd.Timedelta(frequency),
            "open": values,
            "high": [value + 0.2 for value in values],
            "low": [value - 0.2 for value in values],
            "close": values,
        }
    )


def _live_trade_record():
    source_open = datetime(2026, 1, 5, 9, 55, tzinfo=timezone.utc)
    available = source_open + timedelta(minutes=5)
    intent = new_entry_intent(
        symbol="XAUUSDm",
        direction=Direction.BUY,
        source_timeframe="M5",
        source_candle_open_time=source_open,
        signal_available_at=available,
        requested_trigger=100.0,
        stop_loss=90.0,
        final_target=120.0,
        readiness_style=ReadinessStyle.IMMEDIATE,
        source_event_id="source",
    )
    tick = SimpleNamespace(
        time_msc=int(datetime(2026, 1, 5, 10, 5, tzinfo=timezone.utc).timestamp() * 1000),
        bid=100.0,
        ask=100.0,
    )
    event = market_event_from_tick("XAUUSDm", tick)
    decision = process_entry_event(create_entry_state(intent), event)
    position = record_fill(
        decision.state,
        event,
        fill_price=100.0,
        quantity=1.0,
        fill_kind=FillKind.LIVE_MARKET,
        adapter_metadata={"source": "live_mt5", "ticket": 7},
    )
    return update_trade_record(
        {
            "ticket": 7,
            "symbol": "XAUUSDm",
            "direction": "buy",
            "opened_at": event.timestamp.isoformat(),
        },
        position,
    )


def test_live_monitor_dispatches_shared_actions_once(
    monkeypatch,
    fake_mt5,
    allow_fake_order,
    tmp_path,
):
    import main
    from tests.phase5.helpers import configure_broker, executor

    trade = _live_trade_record()
    configure_broker(fake_mt5)
    observed_at = datetime(2026, 1, 5, 10, 10, tzinfo=timezone.utc)
    fake_mt5.positions = [
        SimpleNamespace(
            ticket=7,
            symbol="XAUUSDm",
            volume=1.0,
            sl=90.0,
            tp=120.0,
            type=fake_mt5.ORDER_TYPE_BUY,
            profit=10.0,
            magic=771234,
            comment=f"p5:{trade['trade_id'][:8]}:entry123",
        )
    ]
    fake_mt5.tick = SimpleNamespace(
        time_msc=int(observed_at.timestamp() * 1000),
        bid=110.0,
        ask=110.0,
    )
    broker_executor = executor(fake_mt5, tmp_path)
    broker_executor.clock = lambda: observed_at
    fake_mt5.tick = SimpleNamespace(
        time_msc=int(observed_at.timestamp() * 1000),
        bid=110.0,
        ask=110.0,
    )
    fake_mt5.order_check_response = lambda request: SimpleNamespace(
        retcode=0,
        volume=request.get("volume", 0.0),
    )
    allow_fake_order(
        lambda request: SimpleNamespace(
            retcode=fake_mt5.TRADE_RETCODE_DONE,
            price=110.0,
            volume=request.get("volume", 0.0),
            position=7,
        )
    )
    monkeypatch.setattr(main, "_live_broker_executor", lambda _symbols: broker_executor)
    frames = {
        "M15": _frame(10, "15min"),
        "M5": _frame(20, "5min"),
        "H1": _frame(5, "1h"),
    }
    monkeypatch.setattr(main, "fetch_ohlcv", lambda _symbol, timeframe, bars: frames[timeframe].copy())
    monkeypatch.setattr(
        main,
        "apply_symbol_profile",
        lambda _symbol: {
            "trailing": {"mode": "atr_3x", "atr_mult": 3.0, "min_distance_points": 100}
        },
    )
    saved = []
    monkeypatch.setattr(main, "save_open_trades", lambda payload: saved.append(payload))
    monkeypatch.setattr(main, "log_trade_event", lambda **_kwargs: None)

    first = main.monitor_trades({"XAUUSDm": [trade]})
    order_calls_after_first = [call for call in fake_mt5.calls if call[0] == "order_send"]
    assert len(order_calls_after_first) == 2
    assert first["XAUUSDm"][0]["partial_taken"] is True

    second = main.monitor_trades(first)
    order_calls_after_second = [call for call in fake_mt5.calls if call[0] == "order_send"]
    assert len(order_calls_after_second) == len(order_calls_after_first)
    assert second == first
    assert saved


def test_shadow_backtest_active_path_uses_shared_pending_and_management_lifecycle():
    from backtests import shadow_mode_backtest

    source = inspect.getsource(shadow_mode_backtest.run_backtest)
    assert "pending_entry = PendingEntry" in source
    assert "process_entry_event(" in source
    assert "manage_position(" in source
    assert "open_positions.append(Position(" not in source
    assert "_apply_trailing(" not in source


def test_legacy_live_analysis_path_cannot_bypass_shared_entry_lifecycle():
    import main

    source = inspect.getsource(main.evaluate_symbol)
    shared = source.index("intent_from_strategy_entry", source.index("if trading_allowed:"))
    order = source.index("_submit_live_entry", shared)
    assert shared < order
    assert "process_entry_event" in source[shared:order]
    assert "record_fill" in source[order:]
