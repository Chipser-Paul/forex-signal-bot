"""Deterministic fake-broker replay for the Phase 5 execution boundary."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.execution.broker import (
    ExecutionAction,
    ExecutionPolicy,
    ExecutionRegistry,
    ExecutionRegistryStore,
    SecureBrokerExecutor,
    stable_execution_id,
)


NOW = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)


class ReplayBroker:
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    SYMBOL_TRADE_EXECUTION_MARKET = 2
    SYMBOL_TRADE_MODE_DISABLED = 0
    SYMBOL_TRADE_MODE_LONGONLY = 1
    SYMBOL_TRADE_MODE_SHORTONLY = 2
    SYMBOL_TRADE_MODE_CLOSEONLY = 3
    SYMBOL_TRADE_MODE_FULL = 4
    TRADE_RETCODE_REQUOTE = 10004
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_TIMEOUT = 10012
    TRADE_RETCODE_INVALID_STOPS = 10016
    TRADE_RETCODE_TRADE_DISABLED = 10017
    TRADE_RETCODE_MARKET_CLOSED = 10018
    TRADE_RETCODE_NO_MONEY = 10019
    TRADE_RETCODE_PRICE_CHANGED = 10020
    TRADE_RETCODE_PRICE_OFF = 10021

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.terminal = SimpleNamespace(connected=True, trade_allowed=True)
        self.account = SimpleNamespace(
            equity=1000.0,
            margin=100.0,
            margin_free=900.0,
            trade_allowed=True,
        )
        self.symbol = SimpleNamespace(
            visible=True,
            trade_mode=self.SYMBOL_TRADE_MODE_FULL,
            trade_exemode=self.SYMBOL_TRADE_EXECUTION_MARKET,
            filling_mode=self.SYMBOL_FILLING_FOK | self.SYMBOL_FILLING_IOC,
            point=0.01,
            digits=2,
            trade_stops_level=10,
            trade_freeze_level=5,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
        )
        self.tick = SimpleNamespace(
            bid=100.0,
            ask=100.01,
            time_msc=int(NOW.timestamp() * 1000),
        )
        self.positions: list[object] = []
        self.orders: list[object] = []
        self.deals: list[object] = []
        self.margin_result = 20.0
        self.send_results: list[object | None] = [self.done()]

    def done(self, *, volume=0.1, retcode=None):
        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE if retcode is None else retcode,
            order=101,
            deal=201,
            position=301,
            volume=volume,
            price=100.01,
        )

    def terminal_info(self):
        return self.terminal

    def account_info(self):
        return self.account

    def symbol_info(self, _symbol):
        return self.symbol

    def symbol_select(self, _symbol, _enabled):
        return True

    def symbol_info_tick(self, _symbol):
        return self.tick

    def positions_get(self, **_kwargs):
        return list(self.positions)

    def orders_get(self, **_kwargs):
        return list(self.orders)

    def history_deals_get(self, *_args):
        return list(self.deals)

    def order_calc_margin(self, *_args):
        self.calls.append("order_calc_margin")
        return self.margin_result

    def order_check(self, request):
        self.calls.append("order_check")
        return SimpleNamespace(retcode=0, volume=request.get("volume", 0.0))

    def order_send(self, _request):
        self.calls.append("order_send")
        return self.send_results.pop(0)


def policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        magic_number=771234,
        maximum_spread_points={"XAUUSDm": 25.0},
        maximum_deviation_points={"XAUUSDm": 5},
    )


def engine(root: Path, broker: ReplayBroker, name: str) -> SecureBrokerExecutor:
    return SecureBrokerExecutor(
        broker,
        policy(),
        ExecutionRegistry(ExecutionRegistryStore(root / f"{name}.json")),
        clock=lambda: NOW,
    )


def entry(executor: SecureBrokerExecutor, name: str = "entry"):
    return executor.entry_request(
        action_id=stable_execution_id(name),
        signal_id="signal-1",
        trade_id="trade-123456789",
        symbol="XAUUSDm",
        direction="buy",
        volume=0.1,
        requested_trigger=100.0,
        executable_price=100.01,
        stop_price=99.0,
        target_price=102.0,
        risk_decision_id="risk-1",
        approved_volume=0.1,
        approved_stop=99.0,
        created_at=NOW,
    )


def normalized(result) -> dict:
    return {
        "status": result.status.value,
        "reason": result.reason.value,
        "requested_volume": result.requested_volume,
        "executed_volume": result.executed_volume,
        "reconciliation_required": result.reconciliation_required,
    }


def run_broker_replay(root: Path) -> dict[str, dict]:
    output: dict[str, dict] = {}

    broker = ReplayBroker()
    executor = engine(root, broker, "success")
    output["successful_order"] = normalized(
        executor.execute(entry(executor), risk_recheck=lambda _e, _s, volume: volume)
    )

    broker = ReplayBroker()
    broker.tick.ask = 100.5
    executor = engine(root, broker, "spread")
    output["spread_rejection"] = normalized(executor.execute(entry(executor)))

    broker = ReplayBroker()
    broker.tick.time_msc = int((NOW - timedelta(seconds=11)).timestamp() * 1000)
    executor = engine(root, broker, "stale")
    output["stale_tick_rejection"] = normalized(executor.execute(entry(executor)))

    broker = ReplayBroker()
    broker.margin_result = 101.0
    executor = engine(root, broker, "margin")
    output["margin_rejection"] = normalized(executor.execute(entry(executor)))

    broker = ReplayBroker()
    broker.send_results = [
        broker.done(volume=0.0, retcode=broker.TRADE_RETCODE_INVALID_STOPS),
        broker.done(volume=0.05),
    ]
    executor = engine(root, broker, "stops")
    output["invalid_stop_lower_volume"] = normalized(
        executor.execute(entry(executor), risk_recheck=lambda _e, _s, _v: 0.05)
    )

    broker = ReplayBroker()
    broker.send_results = [broker.done(volume=0.04, retcode=broker.TRADE_RETCODE_DONE_PARTIAL)]
    executor = engine(root, broker, "partial")
    output["partial_fill"] = normalized(executor.execute(entry(executor)))

    broker = ReplayBroker()
    broker.send_results = [
        broker.done(volume=0.0, retcode=broker.TRADE_RETCODE_REQUOTE),
        broker.done(),
    ]
    executor = engine(root, broker, "requote")
    output["requote_safe_retry"] = normalized(
        executor.execute(entry(executor), risk_recheck=lambda _e, _s, volume: volume)
    )

    broker = ReplayBroker()
    broker.send_results = [None]
    executor = engine(root, broker, "timeout")
    request = entry(executor)
    uncertain = executor.execute(request)
    broker.positions = [
        SimpleNamespace(
            ticket=301,
            position_id=301,
            symbol="XAUUSDm",
            magic=policy().magic_number,
            comment=f"p5:{request.trade_id[:8]}:{request.action_id[:8]}",
            volume=0.1,
        )
    ]
    reconciled = executor.reconciler.reconcile_action(
        request.action_id,
        orders=[],
        positions=broker.positions,
        deals=[],
        now=NOW,
    )
    output["timeout_reconciliation"] = {
        **normalized(uncertain),
        "reconciled": reconciled.state.value,
    }

    broker = ReplayBroker()
    executor = engine(root, broker, "duplicate")
    request = entry(executor)
    executor.execute(request, risk_recheck=lambda _e, _s, volume: volume)
    output["duplicate_action"] = normalized(executor.execute(request))

    broker = ReplayBroker()
    executor = engine(root, broker, "ownership")
    manual = SimpleNamespace(
        ticket=301,
        symbol="XAUUSDm",
        magic=0,
        comment="manual",
        type=broker.ORDER_TYPE_BUY,
        volume=0.1,
        sl=99.0,
        tp=102.0,
    )
    broker.positions = [manual]
    close_request = executor.position_request(
        action_id=stable_execution_id("manual-close"),
        signal_id="signal-1",
        trade_id="trade-123456789",
        symbol="XAUUSDm",
        direction="buy",
        action_type=ExecutionAction.FULL_CLOSE,
        volume=0.1,
        executable_price=100.0,
        position_ticket=301,
        risk_decision_id="risk-1",
        approved_volume=0.1,
        created_at=NOW,
    )
    output["manual_position_isolation"] = normalized(executor.execute(close_request))

    broker = ReplayBroker()
    executor = engine(root, broker, "startup")
    owned = SimpleNamespace(
        ticket=301,
        symbol="XAUUSDm",
        magic=policy().magic_number,
        comment="p5:trade-12:entry123",
        type=broker.ORDER_TYPE_BUY,
        volume=0.1,
        price_open=100.01,
        sl=99.0,
        tp=102.0,
    )
    deal = SimpleNamespace(position_id=301, magic=policy().magic_number)
    recovered = executor.reconciler.reconcile_startup(
        [],
        broker_positions=[owned],
        broker_orders=[],
        recent_deals=[deal],
        now=NOW,
    )[0]
    output["startup_recovery"] = {"state": recovered.state.value, "blocked": recovered.block_new_entries}

    broker = ReplayBroker()
    executor = engine(root, broker, "liquidation")
    foreign = SimpleNamespace(**{**owned.__dict__, "ticket": 900, "magic": 999, "comment": "foreign"})
    broker.positions = [owned, foreign]
    broker.send_results = [broker.done()]
    liquidated = executor.liquidate_owned(broker.positions, reason_root="hard-stop", now=NOW)
    output["owned_only_liquidation"] = {
        "results": len(liquidated),
        "send_count": broker.calls.count("order_send"),
    }
    return output


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="phase5-broker-replay-") as raw:
        print(json.dumps(run_broker_replay(Path(raw)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
