from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from bot.backtesting import (
    BidAskBar,
    HistoricalExecutionEngine,
    HistoricalExecutionError,
    LedgerEventType,
    Side,
)
from tests.phase7.helpers import T0, engine, metadata, open_long, policy, quote


@pytest.mark.unit
def test_long_enters_at_ask_marks_and_exits_at_bid():
    execution, position, fill = open_long()
    assert fill.fill_price == 100.0
    assert execution.account.unrealized_pnl == pytest.approx(-1.0)
    closed = execution.close_market(
        action_id="exit-long",
        position_id=position.position_id,
        quote=quote(2, 101.90, 102.00),
        reason_code="MANUAL_TEST_EXIT",
    )
    assert closed.fill_price == 101.90
    assert execution.account.realized_gross_pnl == pytest.approx(19.0)
    assert execution.account.balance == pytest.approx(1018.50)
    assert execution.reconcile()["difference"] == pytest.approx(0.0)


@pytest.mark.unit
def test_short_enters_at_bid_and_exits_at_ask():
    execution = engine()
    position, fill = execution.open_market(
        action_id="entry-short",
        trade_id="trade-short",
        direction=Side.SELL,
        requested_volume=0.10,
        stop_price=101.0,
        target_price=98.0,
        quote=quote(1, 100.0, 100.1),
        signal_available_at=T0,
        source_event_id="signal",
        market_event_id="q-1",
    )
    assert fill.fill_price == 100.0
    assert execution.account.unrealized_pnl == pytest.approx(-1.0)
    closed = execution.close_market(
        action_id="exit-short",
        position_id=position.position_id,
        quote=quote(2, 98.0, 98.1),
        reason_code="MANUAL_TEST_EXIT",
    )
    assert closed.fill_price == 98.1
    assert execution.account.realized_gross_pnl == pytest.approx(19.0)
    assert execution.account.balance == pytest.approx(1018.50)


@pytest.mark.unit
def test_adverse_slippage_has_correct_direction_on_both_sides():
    execution, position, entry = open_long(slippage_points=1)
    assert entry.fill_price == 100.01
    exit_fill = execution.close_market(
        action_id="slipped-exit",
        position_id=position.position_id,
        quote=quote(2, 101.90, 102.0),
        reason_code="TEST",
    )
    assert exit_fill.fill_price == 101.89
    assert execution.account.realized_gross_pnl == pytest.approx(18.8)


@pytest.mark.unit
def test_variable_spread_and_phase5_absolute_gate():
    execution = engine(max_spread_points=5)
    with pytest.raises(HistoricalExecutionError, match="SPREAD_ABSOLUTE_LIMIT"):
        execution.open_market(
            action_id="wide-spread",
            trade_id="trade",
            direction=Side.BUY,
            requested_volume=0.1,
            stop_price=99,
            target_price=102,
            quote=quote(1, 100, 100.10),
            signal_available_at=T0,
            source_event_id="signal",
            market_event_id="quote",
        )


@pytest.mark.unit
def test_relative_spread_gate_is_independent_of_absolute_limit():
    execution = engine(max_spread_points=100)
    with pytest.raises(HistoricalExecutionError, match="SPREAD_RELATIVE_LIMIT"):
        execution.open_market(
            action_id="relative-spread",
            trade_id="trade",
            direction=Side.BUY,
            requested_volume=0.1,
            stop_price=99.5,
            target_price=101,
            quote=quote(1, 100, 100.10),
            signal_available_at=T0,
            source_event_id="signal",
            market_event_id="quote",
        )


@pytest.mark.unit
def test_gap_stop_uses_first_executable_price_not_unavailable_stop():
    execution, position, _ = open_long()
    fill = execution.evaluate_quote(position.position_id, quote(2, 98.5, 98.6))
    assert fill is not None
    assert fill.reason_code == "STOP_TRIGGER"
    assert fill.fill_price == 98.5


@pytest.mark.unit
def test_take_profit_is_not_given_favorable_gap_improvement():
    execution, position, _ = open_long(target=102)
    fill = execution.evaluate_quote(position.position_id, quote(2, 103, 103.1))
    assert fill is not None
    assert fill.reason_code == "TAKE_PROFIT_LIMIT"
    assert fill.fill_price == 102


@pytest.mark.unit
def test_partial_close_costs_only_actual_volume_and_preserves_runner():
    execution, position, _ = open_long()
    fill = execution.close_market(
        action_id="partial",
        position_id=position.position_id,
        quote=quote(2, 101, 101.1),
        requested_volume=0.04,
        reason_code="PARTIAL_TARGET",
    )
    assert fill.partial
    assert execution.positions[position.position_id].remaining_volume == pytest.approx(0.06)
    assert execution.account.realized_gross_pnl == pytest.approx(4.0)
    assert execution.account.commission == pytest.approx(0.35)


@pytest.mark.unit
def test_partial_entry_fill_uses_explicit_available_volume_only():
    execution = engine()
    position, fill = execution.open_market(
        action_id="partial-entry",
        trade_id="trade",
        direction=Side.BUY,
        requested_volume=0.10,
        stop_price=99,
        target_price=102,
        quote=quote(1, 99.9, 100, ask_volume=0.04),
        signal_available_at=T0,
        source_event_id="signal",
        market_event_id="quote",
        available_volume=0.04,
    )
    assert fill.partial
    assert fill.volume == pytest.approx(0.04)
    assert position.initial_volume == pytest.approx(0.04)


@pytest.mark.unit
def test_duplicate_action_cannot_duplicate_fill_or_cash():
    execution, position, _ = open_long()
    execution.close_market(
        action_id="once",
        position_id=position.position_id,
        quote=quote(2, 101, 101.1),
        requested_volume=0.04,
        reason_code="PARTIAL",
    )
    balance = execution.account.balance
    duplicate = execution.close_market(
        action_id="once",
        position_id=position.position_id,
        quote=quote(2, 101, 101.1),
        requested_volume=0.04,
        reason_code="PARTIAL",
    )
    assert execution.account.balance == balance
    assert duplicate.action_id == "once"
    assert [fill.action_id for fill in execution.fills].count("once") == 1


@pytest.mark.unit
def test_reused_action_id_with_different_command_fails_closed():
    execution, position, _ = open_long()
    execution.close_market(
        action_id="stable", position_id=position.position_id,
        quote=quote(2, 101, 101.1), requested_volume=0.04, reason_code="PARTIAL",
    )
    with pytest.raises(HistoricalExecutionError, match="ACTION_ID_CONFLICT"):
        execution.close_market(
            action_id="stable", position_id=position.position_id,
            quote=quote(2, 101, 101.1), requested_volume=0.03, reason_code="PARTIAL",
        )


@pytest.mark.unit
def test_same_source_event_cannot_fill_signal():
    execution = engine()
    with pytest.raises(HistoricalExecutionError, match="SOURCE_CANDLE_ENTRY_FORBIDDEN"):
        execution.open_market(
            action_id="same-source",
            trade_id="trade",
            direction=Side.BUY,
            requested_volume=0.1,
            stop_price=99,
            target_price=102,
            quote=quote(0, 99.9, 100),
            signal_available_at=T0,
            source_event_id="same",
            market_event_id="same",
        )


@pytest.mark.unit
def test_margin_policy_rejects_excessive_requirement():
    execution = HistoricalExecutionEngine(
        run_id="margin",
        metadata=metadata(margin_rate=1.0),
        policy=policy(),
        initial_balance=1000,
    )
    with pytest.raises(HistoricalExecutionError, match="NEW_ORDER_MARGIN_LIMIT"):
        execution.open_market(
            action_id="margin-entry",
            trade_id="trade",
            direction=Side.BUY,
            requested_volume=0.1,
            stop_price=99,
            target_price=102,
            quote=quote(1, 99.9, 100),
            signal_available_at=T0,
            source_event_id="signal",
            market_event_id="quote",
        )


@pytest.mark.unit
def test_ambiguous_bid_ask_bar_is_stop_first():
    execution, position, _ = open_long()
    bar = BidAskBar(
        symbol="XAUUSDm",
        open_time=datetime(2026, 1, 5, 12, 1, tzinfo=timezone.utc),
        available_at=datetime(2026, 1, 5, 12, 6, tzinfo=timezone.utc),
        bid_open=100, bid_high=103, bid_low=98, bid_close=101,
        ask_open=100.1, ask_high=103.1, ask_low=98.1, ask_close=101.1,
        source="fixture", dataset_id="bars", sequence_id="bar-1",
    )
    fill = execution.evaluate_bar(position.position_id, bar)
    assert fill is not None
    assert fill.reason_code == "AMBIGUOUS_BAR_STOP_FIRST"
    assert fill.fill_price == 99


@pytest.mark.unit
def test_floating_equity_uses_executable_close_side_for_phase4_snapshot():
    execution, _position, _ = open_long()
    execution.mark_to_market(quote(2, 95, 95.1))
    snapshot = execution.risk_account_snapshot(quote(2, 95, 95.1).timestamp)
    assert snapshot.floating_pnl == pytest.approx(-50.0)
    assert snapshot.equity == pytest.approx(execution.account.balance - 50.0)


@pytest.mark.unit
def test_ledger_uses_separate_commission_events_and_reconciles():
    execution, position, _ = open_long()
    execution.close_market(
        action_id="final",
        position_id=position.position_id,
        quote=quote(2, 101.9, 102),
        reason_code="TEST",
    )
    assert [entry.event_type for entry in execution.ledger].count(LedgerEventType.COMMISSION) == 2
    assert execution.reconcile()["difference"] == pytest.approx(0)


@pytest.mark.unit
def test_swap_applies_to_remaining_volume_and_is_idempotent():
    execution, position, _ = open_long()
    execution.close_market(
        action_id="before-rollover-partial",
        position_id=position.position_id,
        quote=quote(60, 101, 101.1),
        requested_volume=0.04,
        reason_code="PARTIAL",
    )
    after_rollover = datetime(2026, 1, 5, 23, tzinfo=timezone.utc)
    first = execution.apply_swap_until(position.position_id, after_rollover)
    second = execution.apply_swap_until(position.position_id, after_rollover)
    assert len(first) == 1
    assert first[0].swap == pytest.approx(-0.06)
    assert second == ()


@pytest.mark.unit
def test_closed_position_accrues_no_later_swap():
    execution, position, _ = open_long()
    execution.close_market(
        action_id="close-before-rollover",
        position_id=position.position_id,
        quote=quote(60, 101, 101.1),
        reason_code="CLOSED",
    )
    entries = execution.apply_swap_until(
        position.position_id, datetime(2026, 1, 5, 23, tzinfo=timezone.utc)
    )
    assert entries == ()


@pytest.mark.unit
def test_volume_normalization_is_downward_for_non_decimal_step():
    custom = replace(metadata(), volume_min=0.25, volume_step=0.25)
    execution = HistoricalExecutionEngine(
        run_id="step", metadata=custom, policy=policy(), initial_balance=1000
    )
    position, _ = execution.open_market(
        action_id="entry",
        trade_id="trade",
        direction=Side.BUY,
        requested_volume=0.74,
        stop_price=99,
        target_price=102,
        quote=quote(1, 99.9, 100),
        signal_available_at=T0,
        source_event_id="signal",
        market_event_id="quote",
    )
    assert position.initial_volume == 0.5
