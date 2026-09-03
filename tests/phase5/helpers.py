from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from bot.execution.broker import (
    ExecutionPolicy,
    ExecutionRegistry,
    ExecutionRegistryStore,
    SecureBrokerExecutor,
    stable_execution_id,
)


NOW = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)


def policy(**changes) -> ExecutionPolicy:
    values = {
        "magic_number": 771234,
        "maximum_spread_points": {"XAUUSDm": 25.0},
        "maximum_deviation_points": {"XAUUSDm": 5},
    }
    values.update(changes)
    return ExecutionPolicy(**values)


def configure_broker(fake_mt5, *, now: datetime = NOW) -> None:
    fake_mt5.terminal = SimpleNamespace(connected=True, trade_allowed=True)
    fake_mt5.account = SimpleNamespace(
        login=1,
        server="fake",
        balance=1000.0,
        equity=1000.0,
        profit=0.0,
        margin=100.0,
        margin_free=900.0,
        currency="USD",
        trade_allowed=True,
    )
    fake_mt5.tick = SimpleNamespace(
        bid=100.00,
        ask=100.01,
        time=int(now.timestamp()),
        time_msc=int(now.timestamp() * 1000),
    )
    fake_mt5.symbol = SimpleNamespace(
        name="XAUUSDm",
        visible=True,
        trade_mode=fake_mt5.SYMBOL_TRADE_MODE_FULL,
        trade_exemode=fake_mt5.SYMBOL_TRADE_EXECUTION_MARKET,
        filling_mode=fake_mt5.SYMBOL_FILLING_FOK | fake_mt5.SYMBOL_FILLING_IOC,
        point=0.01,
        digits=2,
        stops_level=10,
        trade_stops_level=10,
        trade_freeze_level=5,
        trade_tick_value=1.0,
        trade_tick_size=0.01,
        trade_contract_size=100.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )
    fake_mt5.order_calc_margin_response = 20.0
    fake_mt5.allow_order_check = True
    fake_mt5.order_check_response = SimpleNamespace(retcode=0, volume=0.1)
    fake_mt5.allow_order_send = True
    fake_mt5.order_response = SimpleNamespace(
        retcode=fake_mt5.TRADE_RETCODE_DONE,
        order=101,
        deal=201,
        position=301,
        volume=0.1,
        price=100.01,
    )


def executor(fake_mt5, tmp_path: Path, *, custom_policy: ExecutionPolicy | None = None):
    configure_broker(fake_mt5)
    registry = ExecutionRegistry(ExecutionRegistryStore(tmp_path / "execution.json"))
    return SecureBrokerExecutor(
        fake_mt5,
        custom_policy or policy(),
        registry,
        clock=lambda: NOW,
    )


def entry_request(engine: SecureBrokerExecutor, **changes):
    action_id = changes.pop("action_id", stable_execution_id("signal-1", "entry"))
    values = {
        "action_id": action_id,
        "signal_id": "signal-1",
        "trade_id": "trade-123456789",
        "symbol": "XAUUSDm",
        "direction": "buy",
        "volume": 0.1,
        "requested_trigger": 100.0,
        "executable_price": 100.01,
        "stop_price": 99.0,
        "target_price": 102.0,
        "risk_decision_id": "risk-1",
        "approved_volume": 0.1,
        "approved_stop": 99.0,
        "created_at": NOW,
    }
    values.update(changes)
    return engine.entry_request(**values)


def owned_position(engine: SecureBrokerExecutor, request=None, **changes):
    request = request or entry_request(engine)
    values = {
        "ticket": 301,
        "symbol": "XAUUSDm",
        "magic": engine.policy.magic_number,
        "comment": f"p5:{request.trade_id[:8]}:{request.action_id[:8]}",
        "type": engine.broker.ORDER_TYPE_BUY,
        "volume": 0.1,
        "price_open": 100.01,
        "sl": 99.0,
        "tp": 102.0,
    }
    values.update(changes)
    return SimpleNamespace(**values)
