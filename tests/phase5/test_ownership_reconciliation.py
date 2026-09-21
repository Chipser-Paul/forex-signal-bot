from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.execution.broker import (
    ExecutionAction,
    ExecutionReason,
    ExecutionStatus,
    LocalPosition,
    ReconciliationState,
    StartupReconciler,
    stable_execution_id,
)
from bot.execution.broker.reconciliation import is_owned_position
from tests.phase5.helpers import NOW, entry_request, executor, owned_position


def management_request(engine, position, action_type=ExecutionAction.PARTIAL_CLOSE, **changes):
    values = {
        "action_id": stable_execution_id("trade-123456789", action_type.value),
        "signal_id": "signal-1",
        "trade_id": "trade-123456789",
        "symbol": "XAUUSDm",
        "direction": "buy",
        "action_type": action_type,
        "volume": 0.05 if action_type is ExecutionAction.PARTIAL_CLOSE else 0.1,
        "executable_price": 100.0,
        "position_ticket": position.ticket,
        "risk_decision_id": "risk-1",
        "approved_volume": 0.1,
        "created_at": NOW,
        "stop_price": 99.5 if action_type is ExecutionAction.MODIFY_STOP else None,
        "target_price": 102.0 if action_type is ExecutionAction.MODIFY_STOP else None,
        "approved_stop": 99.0 if action_type is ExecutionAction.MODIFY_STOP else None,
    }
    values.update(changes)
    return engine.position_request(**values)


def test_ownership_requires_magic_symbol_ticket_and_trade_identity(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    request = entry_request(engine)
    position = owned_position(engine, request)
    assert is_owned_position(
        position,
        magic_number=engine.policy.magic_number,
        symbol="XAUUSDm",
        ticket=301,
        trade_id=request.trade_id,
    )
    for changed in (
        {"magic": 0},
        {"magic": 999},
        {"symbol": "BTCUSDm"},
        {"ticket": 302},
        {"comment": "p5:anotherx:actionxx"},
    ):
        assert not is_owned_position(
            owned_position(engine, request, **changed),
            magic_number=engine.policy.magic_number,
            symbol="XAUUSDm",
            ticket=301,
            trade_id=request.trade_id,
        )


@pytest.mark.parametrize("magic", [0, 999999])
def test_manual_or_foreign_position_is_never_closed(fake_mt5, tmp_path, magic):
    engine = executor(fake_mt5, tmp_path)
    position = owned_position(engine, magic=magic)
    fake_mt5.positions = [position]
    result = engine.execute(management_request(engine, position))
    assert result.reason is ExecutionReason.OWNERSHIP_UNPROVEN
    assert not [call for call in fake_mt5.calls if call[0] == "order_send"]


def test_ticket_mismatch_is_never_mutated(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    position = owned_position(engine)
    fake_mt5.positions = [position]
    request = management_request(engine, position, position_ticket=999)
    result = engine.execute(request)
    assert result.reason is ExecutionReason.POSITION_NOT_FOUND
    assert not [call for call in fake_mt5.calls if call[0] == "order_send"]


def test_owned_partial_close_runs_preflight_and_never_exceeds_remaining(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    position = owned_position(engine, volume=0.05)
    fake_mt5.positions = [position]
    fake_mt5.order_check_response = lambda request: SimpleNamespace(
        retcode=0, volume=request.get("volume", 0.0)
    )
    fake_mt5.order_response = SimpleNamespace(
        retcode=fake_mt5.TRADE_RETCODE_DONE,
        order=401,
        deal=402,
        position=301,
        volume=0.05,
        price=100.0,
    )
    success = engine.execute(management_request(engine, position, volume=0.05))
    assert success.status is ExecutionStatus.CONFIRMED

    second_engine = executor(fake_mt5, tmp_path / "too-much")
    position = owned_position(second_engine, volume=0.05)
    fake_mt5.positions = [position]
    rejected = second_engine.execute(management_request(second_engine, position, volume=0.1))
    assert rejected.reason is ExecutionReason.CLOSE_VOLUME_EXCEEDS_POSITION


def test_stop_modification_must_tighten_and_respect_ownership(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    position = owned_position(engine, sl=99.0)
    fake_mt5.positions = [position]
    fake_mt5.order_check_response = lambda request: SimpleNamespace(retcode=0, volume=0.0)
    fake_mt5.order_response = SimpleNamespace(
        retcode=fake_mt5.TRADE_RETCODE_DONE,
        order=0,
        deal=0,
        position=301,
        volume=0.0,
        price=0.0,
    )
    tightened = engine.execute(
        management_request(engine, position, ExecutionAction.MODIFY_STOP, stop_price=99.5)
    )
    assert tightened.status is ExecutionStatus.CONFIRMED

    second = executor(fake_mt5, tmp_path / "loosen")
    position = owned_position(second, sl=99.5)
    fake_mt5.positions = [position]
    loosened = second.execute(
        management_request(second, position, ExecutionAction.MODIFY_STOP, stop_price=99.0)
    )
    assert loosened.reason is ExecutionReason.STOP_NOT_IMPROVED


def local_position() -> LocalPosition:
    return LocalPosition("trade-123456789", "XAUUSDm", 301, "buy", 0.1, 99.0, 102.0)


def test_startup_exact_match_and_foreign_position(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    owned = owned_position(engine)
    foreign = owned_position(engine, ticket=900, magic=999, comment="manual")
    results = engine.reconciler.reconcile_startup(
        [local_position()],
        broker_positions=[owned, foreign],
        broker_orders=[],
        recent_deals=[],
        now=NOW,
    )
    states = {result.position_ticket: result.state for result in results}
    assert states[301] is ReconciliationState.MATCHED
    assert states[900] is ReconciliationState.FOREIGN_IGNORED


def test_broker_only_owned_position_requires_history_to_recover(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    position = owned_position(engine)
    deal = SimpleNamespace(
        ticket=201,
        position_id=301,
        magic=engine.policy.magic_number,
        symbol="XAUUSDm",
        comment=position.comment,
        volume=0.1,
    )
    recovered = engine.reconciler.reconcile_startup(
        [],
        broker_positions=[position],
        broker_orders=[],
        recent_deals=[deal],
        now=NOW,
    )[0]
    assert recovered.state is ReconciliationState.RECOVERED
    assert recovered.recovered["partial_history"] == "UNKNOWN"

    ambiguous = engine.reconciler.reconcile_startup(
        [],
        broker_positions=[position],
        broker_orders=[],
        recent_deals=[],
        now=NOW,
    )[0]
    assert ambiguous.state is ReconciliationState.REQUIRED
    assert ambiguous.block_new_entries


def test_local_only_state_needs_confirmed_broker_close(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    ambiguous = engine.reconciler.reconcile_startup(
        [local_position()],
        broker_positions=[],
        broker_orders=[],
        recent_deals=[],
        now=NOW,
    )[0]
    assert ambiguous.state is ReconciliationState.REQUIRED

    deal = SimpleNamespace(
        ticket=201,
        position_id=301,
        magic=engine.policy.magic_number,
        symbol="XAUUSDm",
        comment="p5:trade-12:close123",
    )
    confirmed = engine.reconciler.reconcile_startup(
        [local_position()],
        broker_positions=[],
        broker_orders=[],
        recent_deals=[deal],
        now=NOW,
    )[0]
    assert confirmed.state is ReconciliationState.CLOSED_CONFIRMED


def test_uncertain_action_reconciles_found_or_proven_absent(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    request = entry_request(engine)
    engine.registry.prepare(
        action_id=request.action_id,
        trade_id=request.trade_id,
        symbol=request.symbol,
        action_type=request.action_type,
        now=NOW,
    )
    engine.registry.transition(
        request.action_id,
        ExecutionStatus.UNCERTAIN,
        NOW,
        reason=ExecutionReason.BROKER_OUTCOME_UNCERTAIN,
        attempt_count=1,
    )
    found = SimpleNamespace(
        ticket=301,
        position_id=301,
        order=101,
        deal=201,
        symbol="XAUUSDm",
        magic=engine.policy.magic_number,
        comment=f"p5:{request.trade_id[:8]}:{request.action_id[:8]}",
        volume=0.1,
    )
    matched = engine.reconciler.reconcile_action(
        request.action_id,
        orders=[],
        positions=[found],
        deals=[],
        now=NOW,
    )
    assert matched.state is ReconciliationState.MATCHED
    assert engine.registry.get(request.action_id).state is ExecutionStatus.CONFIRMED

    absent_engine = executor(fake_mt5, tmp_path / "absent")
    absent_request = entry_request(absent_engine, action_id=stable_execution_id("absent"))
    absent_engine.registry.prepare(
        action_id=absent_request.action_id,
        trade_id=absent_request.trade_id,
        symbol=absent_request.symbol,
        action_type=absent_request.action_type,
        now=NOW,
    )
    absent = absent_engine.reconciler.reconcile_action(
        absent_request.action_id,
        orders=[],
        positions=[],
        deals=[],
        now=NOW,
        absence_proven=True,
    )
    assert absent.state is ReconciliationState.ABSENT_CONFIRMED


def test_startup_reconciliation_is_idempotent(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    inputs = dict(
        broker_positions=[owned_position(engine)],
        broker_orders=[],
        recent_deals=[],
        now=NOW,
    )
    first = engine.reconciler.reconcile_startup([local_position()], **inputs)
    second = engine.reconciler.reconcile_startup([local_position()], **inputs)
    assert first == second


def test_liquidation_mutates_only_proven_owned_positions(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    owned = owned_position(engine)
    foreign = owned_position(engine, ticket=900, magic=999, comment="manual")
    fake_mt5.positions = [owned, foreign]
    fake_mt5.order_check_response = lambda request: SimpleNamespace(
        retcode=0, volume=request.get("volume", 0.0)
    )
    fake_mt5.order_response = SimpleNamespace(
        retcode=fake_mt5.TRADE_RETCODE_DONE,
        order=401,
        deal=402,
        position=301,
        volume=0.1,
        price=100.0,
    )
    results = engine.liquidate_owned([owned, foreign], reason_root="hard-stop", now=NOW)
    assert len(results) == 1
    assert results[0].status is ExecutionStatus.CONFIRMED
    sends = [call[1][0] for call in fake_mt5.calls if call[0] == "order_send"]
    assert [request["position"] for request in sends] == [301]
