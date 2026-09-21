from __future__ import annotations

from datetime import timedelta
from dataclasses import replace
from types import SimpleNamespace

import pytest

from bot.execution.risk import (
    CircuitStatus,
    ClosedTradeOutcome,
    PersistentRiskAuthority,
    RiskError,
    RiskReason,
    RiskStateStore,
    account_identity_ref,
    account_snapshot_from_mt5,
    mt5_profit_calculator,
    open_risk_items_from_mt5,
    symbol_specification_from_mt5,
)
from tests.phase4.helpers import NOW, policy


def configure_account(fake_mt5, *, equity=1000.0, balance=1000.0):
    fake_mt5.account = SimpleNamespace(
        login=123456,
        server="Test-Server",
        balance=balance,
        equity=equity,
        profit=equity - balance,
        margin=10.0,
        margin_free=equity - 10.0,
        currency="USD",
    )
    return account_snapshot_from_mt5(
        fake_mt5,
        now=NOW,
        expected_login=123456,
        expected_server="test-server",
    )


def test_account_adapter_uses_equity_and_hashed_identity(fake_mt5):
    result = configure_account(fake_mt5, equity=975.0)
    assert result.equity == 975.0
    assert result.floating_pnl == -25.0
    assert result.account_ref == account_identity_ref(123456, "Test-Server")
    assert "123456" not in result.account_ref


def test_account_adapter_rejects_missing_or_wrong_identity(fake_mt5):
    with pytest.raises(RiskError, match="unavailable"):
        account_snapshot_from_mt5(fake_mt5, now=NOW)
    fake_mt5.account = SimpleNamespace(login=2, server="wrong", balance=1000, equity=1000)
    with pytest.raises(RiskError, match="identity"):
        account_snapshot_from_mt5(fake_mt5, now=NOW, expected_login=1)


def test_symbol_adapter_and_broker_loss_calculation(fake_mt5):
    fake_mt5.order_calc_profit_response = lambda _kind, _symbol, volume, entry, close: (
        close - entry
    ) * volume * 100
    specification = symbol_specification_from_mt5(fake_mt5, "XAUUSDm")
    calculator = mt5_profit_calculator(fake_mt5)
    assert specification.volume_step == 0.01
    assert calculator("buy", "XAUUSDm", 0.1, 100.0, 99.0) == -10.0
    assert any(call[0] == "order_calc_profit" for call in fake_mt5.calls)


def test_open_risk_adapter_includes_manual_and_partial_remaining_positions(fake_mt5):
    fake_mt5.tick = SimpleNamespace(bid=100.0, ask=100.1)
    positions = [
        SimpleNamespace(ticket=1, symbol="XAUUSDm", type=fake_mt5.ORDER_TYPE_BUY, volume=0.05, sl=99.0),
        SimpleNamespace(ticket=2, symbol="XAUUSDm", type=fake_mt5.ORDER_TYPE_SELL, volume=0.02, sl=0.0),
    ]
    tracked = {1: {"trade_id": "known", "entry_price": 100.0}}
    items = open_risk_items_from_mt5(fake_mt5, positions=positions, tracked_trades=tracked)
    assert items[0].ownership == "strategy" and items[0].remaining_volume == 0.05
    assert items[0].estimated_loss == pytest.approx(5.0)
    assert items[1].ownership == "manual_or_unknown" and items[1].estimated_loss is None


def test_locked_profit_stop_reduces_known_capital_risk_to_zero(fake_mt5):
    fake_mt5.tick = SimpleNamespace(bid=110.0, ask=110.1)
    position = SimpleNamespace(
        ticket=1,
        symbol="XAUUSDm",
        type=fake_mt5.ORDER_TYPE_BUY,
        volume=0.05,
        sl=105.0,
    )
    item = open_risk_items_from_mt5(
        fake_mt5,
        positions=(position,),
        tracked_trades={1: {"trade_id": "known", "entry_price": 100.0}},
    )[0]
    assert item.estimated_loss == 0.0
    assert item.calculation_method == "locked_profit_floor"


def test_persistent_authority_requires_explicit_initialization(tmp_path, fake_mt5):
    snapshot = configure_account(fake_mt5)
    authority = PersistentRiskAuthority(policy(), RiskStateStore(tmp_path / "risk.json"))
    decision = authority.decide(
        snapshot=snapshot,
        specification=symbol_specification_from_mt5(fake_mt5, "XAUUSDm"),
        direction="buy",
        entry=100.0,
        stop=99.0,
        open_risk_items=(),
        now=NOW,
    )
    assert decision.reason is RiskReason.RISK_STATE_UNINITIALIZED
    authority.initialize(snapshot, known_strategy_positions=0)
    approved = authority.decide(
        snapshot=snapshot,
        specification=symbol_specification_from_mt5(fake_mt5, "XAUUSDm"),
        direction="buy",
        entry=100.0,
        stop=99.0,
        open_risk_items=(),
        now=NOW,
    )
    assert approved.approved


def test_persistent_outcomes_are_consumed_once_and_survive_restart(tmp_path, fake_mt5):
    snapshot = configure_account(fake_mt5)
    path = tmp_path / "risk.json"
    authority = PersistentRiskAuthority(policy(), RiskStateStore(path))
    authority.initialize(snapshot, known_strategy_positions=0)
    outcome = ClosedTradeOutcome("outcome", "trade", NOW, -2.0)
    first, consumed = authority.consume_outcome(snapshot, outcome, now=NOW)
    restarted = PersistentRiskAuthority(policy(), RiskStateStore(path))
    second, repeated = restarted.consume_outcome(snapshot, outcome, now=NOW)
    assert consumed is True and repeated is False
    assert first.consecutive_losses == second.consecutive_losses == 1


def test_corrupt_authority_state_returns_fail_closed_decision(tmp_path, fake_mt5):
    snapshot = configure_account(fake_mt5)
    store = RiskStateStore(tmp_path / "risk.json")
    authority = PersistentRiskAuthority(policy(), store)
    authority.initialize(snapshot, known_strategy_positions=0)
    store.path.write_text("{", encoding="utf-8")
    store.backup_path.write_text("{", encoding="utf-8")
    decision = authority.decide(
        snapshot=snapshot,
        specification=symbol_specification_from_mt5(fake_mt5, "XAUUSDm"),
        direction="buy",
        entry=100.0,
        stop=99.0,
        open_risk_items=(),
        now=NOW,
    )
    assert decision.reason is RiskReason.RISK_STATE_CORRUPT
    assert decision.circuit_status is CircuitStatus.STATE_CORRUPT


def test_unexpected_primary_disappearance_is_not_first_initialization(tmp_path, fake_mt5):
    snapshot = configure_account(fake_mt5)
    store = RiskStateStore(tmp_path / "risk.json")
    authority = PersistentRiskAuthority(policy(), store)
    authority.initialize(snapshot, known_strategy_positions=0)
    store.path.unlink()
    decision = authority.decide(
        snapshot=snapshot,
        specification=symbol_specification_from_mt5(fake_mt5, "XAUUSDm"),
        direction="buy",
        entry=100.0,
        stop=99.0,
        open_risk_items=(),
        now=NOW,
    )
    assert decision.reason is RiskReason.RISK_STATE_CORRUPT
    assert decision.circuit_status is CircuitStatus.STATE_CORRUPT


@pytest.mark.parametrize(
    ("authority_policy", "changed_snapshot", "reason"),
    [
        (policy(), True, RiskReason.ACCOUNT_IDENTITY_MISMATCH),
        (replace(policy(), policy_version="different-policy"), False, RiskReason.POLICY_IDENTITY_MISMATCH),
    ],
)
def test_persisted_account_and_policy_identity_mismatches_fail_closed(
    tmp_path,
    fake_mt5,
    authority_policy,
    changed_snapshot,
    reason,
):
    snapshot = configure_account(fake_mt5)
    path = tmp_path / "risk.json"
    initial = PersistentRiskAuthority(policy(), RiskStateStore(path))
    initial.initialize(snapshot, known_strategy_positions=0)
    checked_snapshot = (
        replace(snapshot, account_ref="different-sanitized-ref")
        if changed_snapshot
        else snapshot
    )
    decision = PersistentRiskAuthority(
        authority_policy,
        RiskStateStore(path),
    ).decide(
        snapshot=checked_snapshot,
        specification=symbol_specification_from_mt5(fake_mt5, "XAUUSDm"),
        direction="buy",
        entry=100.0,
        stop=99.0,
        open_risk_items=(),
        now=NOW,
    )
    assert not decision.approved
    assert decision.reason is reason
