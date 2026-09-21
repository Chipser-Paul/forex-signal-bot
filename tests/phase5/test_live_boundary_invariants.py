from __future__ import annotations

import inspect
from dataclasses import replace
from types import SimpleNamespace

import pytest

from bot.execution.broker import (
    ExecutionAction,
    ExecutionReason,
    ExecutionStatus,
    LocalPosition,
    stable_execution_id,
)
from bot.execution.lifecycle import (
    ActionConfirmation,
    ActionType,
    manage_position,
    reconcile_action_fill,
    reconcile_confirmed_actions,
)
from tests.phase3.helpers import config, open_position, tick
from tests.phase5.helpers import NOW, entry_request, executor, owned_position


def test_legacy_trade_executor_fails_closed_without_secured_adapter(fake_mt5):
    import trade_executor

    assert trade_executor.execute_trade("XAUUSDm", "buy", 0.1, 99.0, 102.0) is None
    assert not [call for call in fake_mt5.calls if call[0] == "order_send"]


def test_trade_executor_uses_actual_partial_fill(fake_mt5, tmp_path, monkeypatch):
    import trade_executor

    engine = executor(fake_mt5, tmp_path)
    fake_mt5.order_response = SimpleNamespace(
        retcode=fake_mt5.TRADE_RETCODE_DONE_PARTIAL,
        order=101,
        deal=201,
        position=301,
        volume=0.04,
        price=100.01,
    )
    fake_mt5.order_check_response = lambda request: SimpleNamespace(
        retcode=0, volume=request.get("volume", 0.0)
    )
    monkeypatch.setattr(trade_executor, "send_alert", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trade_executor, "log_trade", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trade_executor, "log_trade_open", lambda **_kwargs: None)
    result = trade_executor.execute_trade(
        "XAUUSDm",
        "buy",
        0.1,
        99.0,
        102.0,
        executor=engine,
        action_id="entry-action",
        signal_id="signal-1",
        trade_id="trade-123456789",
        risk_decision_id="risk-1",
        approved_volume=0.1,
        approved_stop=99.0,
        requested_trigger=100.0,
        created_at=NOW,
        risk_recheck=lambda _entry, _stop, volume: volume,
    )
    assert result["lot"] == 0.04
    assert result["requested_lot"] == 0.1


def test_no_live_mutation_path_bypasses_secured_adapter():
    import main
    import trade_executor
    import trade_manager
    from bot.execution.broker import adapter

    assert "mt5.order_send" not in inspect.getsource(main)
    assert "order_send" not in inspect.getsource(trade_executor)
    assert "order_send" not in inspect.getsource(trade_manager)
    assert "self.broker.order_send(final_payload)" in inspect.getsource(adapter)


def test_stop_widening_without_risk_reapproval_never_sends(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    request = replace(entry_request(engine), stop_price=98.0)
    result = engine.execute(request)
    assert result.reason is ExecutionReason.STOP_WIDENING_REQUIRES_RISK
    assert not [call for call in fake_mt5.calls if call[0] == "order_send"]


def test_partial_broker_fill_reconciles_phase3_quantity_and_pnl():
    position = open_position(quantity=1.0)
    planned = manage_position(position, tick("partial", 10, 110.0), config())
    action = next(action for action in planned.actions if action.action_type is ActionType.PARTIAL_CLOSE)
    reconciled = reconcile_action_fill(
        planned.position,
        action,
        110.0,
        config(),
        actual_quantity=0.2,
    )
    assert reconciled.closed_quantity == pytest.approx(0.2)
    assert reconciled.remaining_quantity == pytest.approx(0.8)
    assert reconciled.pnl_components[-1].quantity == pytest.approx(0.2)
    assert reconciled.realized_gross_pnl == pytest.approx(2.0)


def test_confirmed_partial_survives_rejected_followup_stop_change():
    position = open_position(quantity=1.0)
    settings = config(trailing_enabled=True, trailing_atr_multiple=3.0)
    planned = manage_position(position, tick("partial-trail", 10, 110.0, atr=1.0), settings)
    partial = next(
        action for action in planned.actions if action.action_type is ActionType.PARTIAL_CLOSE
    )
    assert any(action.action_type is ActionType.MODIFY_STOP for action in planned.actions)

    reconciled = reconcile_confirmed_actions(
        position,
        planned,
        [ActionConfirmation(partial.action_id, 0.2, 110.0)],
        settings,
    )

    assert reconciled.closed_quantity == pytest.approx(0.2)
    assert reconciled.remaining_quantity == pytest.approx(0.8)
    assert reconciled.current_stop == position.current_stop
    assert reconciled.processed_event_ids[-1] == "partial-trail"


def test_unconfirmed_final_close_is_not_applied_after_confirmed_partial():
    position = open_position(quantity=1.0)
    settings = config()
    planned = manage_position(position, tick("partial-final", 10, 120.0), settings)
    partial = next(
        action for action in planned.actions if action.action_type is ActionType.PARTIAL_CLOSE
    )
    assert any(action.action_type is ActionType.FINAL_CLOSE for action in planned.actions)

    reconciled = reconcile_confirmed_actions(
        position,
        planned,
        [ActionConfirmation(partial.action_id, partial.quantity, 120.0)],
        settings,
    )

    assert reconciled.status.value == "PARTIALLY_CLOSED"
    assert reconciled.remaining_quantity == pytest.approx(0.5)
    assert reconciled.exit_time is None
    assert reconciled.exit_reason is None


def test_every_broker_mutation_uses_stable_action_and_reason(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    request = entry_request(engine)
    first = engine.execute(request, risk_recheck=lambda _entry, _stop, volume: volume)
    second = engine.execute(request, risk_recheck=lambda _entry, _stop, volume: volume)
    assert first.action_id == request.action_id
    assert first.reason is ExecutionReason.CONFIRMED
    assert second.reason is ExecutionReason.DUPLICATE_ACTION
    assert first.attempt_id == stable_execution_id(request.action_id, "attempt", 1)


def test_duplicate_partial_result_preserves_actual_execution_details(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    request = entry_request(engine)
    fake_mt5.order_response = SimpleNamespace(
        retcode=fake_mt5.TRADE_RETCODE_DONE_PARTIAL,
        order=101,
        deal=201,
        position=301,
        volume=0.04,
        price=100.02,
    )

    first = engine.execute(request, risk_recheck=lambda _entry, _stop, volume: volume)
    duplicate = engine.execute(request, risk_recheck=lambda _entry, _stop, volume: volume)

    assert first.status is ExecutionStatus.PARTIALLY_FILLED
    assert duplicate.status is ExecutionStatus.PARTIALLY_FILLED
    assert duplicate.executed_volume == pytest.approx(0.04)
    assert duplicate.executed_price == pytest.approx(100.02)
    assert duplicate.remaining_unfilled_volume == pytest.approx(0.06)
    assert len([call for call in fake_mt5.calls if call[0] == "order_send"]) == 1


def test_execution_registry_records_no_raw_broker_snapshot(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    engine.execute(entry_request(engine), risk_recheck=lambda _entry, _stop, volume: volume)
    payload = (tmp_path / "execution.json").read_text(encoding="utf-8").lower()
    for forbidden in ("password", "token", "balance", "equity", "margin_free"):
        assert forbidden not in payload


def test_startup_reconciliation_accepts_exact_match(fake_mt5, tmp_path, monkeypatch):
    import main

    engine = executor(fake_mt5, tmp_path)
    request = entry_request(engine)
    position = owned_position(engine, request)
    fake_mt5.positions = [position]
    trade = {
        "ticket": 301,
        "symbol": "XAUUSDm",
        "trade_id": request.trade_id,
        "signal_id": request.signal_id,
        "direction": "buy",
        "remaining_quantity": 0.1,
        "sl": 99.0,
        "tp": 102.0,
    }
    monkeypatch.setattr(main, "_live_broker_executor", lambda _symbols: engine)
    monkeypatch.setattr(main, "SYMBOLS", ["XAUUSDm"])
    monkeypatch.setattr(main, "save_open_trades", lambda _payload: None)
    assert main.reconcile_broker_startup({"XAUUSDm": [trade]})


def test_startup_reconciliation_blocks_ambiguous_owned_position(fake_mt5, tmp_path, monkeypatch):
    import main

    engine = executor(fake_mt5, tmp_path)
    fake_mt5.positions = [
        owned_position(engine, comment="ambiguous", magic=engine.policy.magic_number)
    ]
    monkeypatch.setattr(main, "_live_broker_executor", lambda _symbols: engine)
    monkeypatch.setattr(main, "SYMBOLS", ["XAUUSDm"])
    assert not main.reconcile_broker_startup({})


def test_startup_recovery_reconstructs_only_evidenced_owned_position(
    fake_mt5,
    tmp_path,
    monkeypatch,
):
    import main

    engine = executor(fake_mt5, tmp_path)
    request = entry_request(engine)
    position = owned_position(engine, request)
    fake_mt5.positions = [position]
    fake_mt5.deals = [
        SimpleNamespace(
            ticket=201,
            position_id=301,
            magic=engine.policy.magic_number,
            symbol="XAUUSDm",
            comment=position.comment,
            volume=0.1,
        )
    ]
    local = {}
    monkeypatch.setattr(main, "_live_broker_executor", lambda _symbols: engine)
    monkeypatch.setattr(main, "SYMBOLS", ["XAUUSDm"])
    monkeypatch.setattr(main, "save_open_trades", lambda _payload: None)
    assert main.reconcile_broker_startup(local)
    assert local["XAUUSDm"][0]["reconciliation_state"] == "RECOVERED"
    assert local["XAUUSDm"][0]["partial_history"] == "UNKNOWN"
