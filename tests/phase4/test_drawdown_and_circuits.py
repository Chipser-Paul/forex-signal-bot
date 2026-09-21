from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from bot.execution.risk import (
    CircuitStatus,
    ClosedTradeOutcome,
    apply_account_snapshot,
    assess_trade_risk,
    consume_closed_outcome,
)
from tests.phase4.helpers import NOW, policy, snapshot, specification, state


def refresh(current, equity, timestamp=NOW):
    account = snapshot(equity=equity, timestamp=timestamp)
    return apply_account_snapshot(current, account, policy(), now=timestamp)[0]


@pytest.mark.parametrize(
    ("equity", "expected"),
    [(980.0, CircuitStatus.DAILY_PAUSED), (960.0, CircuitStatus.WEEKLY_PAUSED), (920.0, CircuitStatus.HARD_STOPPED)],
)
def test_one_thousand_account_drawdown_thresholds(equity, expected):
    assert refresh(state(), equity).circuit_status is expected


def test_floating_loss_changes_drawdown_immediately():
    account = snapshot(equity=979.0, balance=1000.0)
    updated, drawdown = apply_account_snapshot(state(), account, policy(), now=NOW)
    assert account.floating_pnl == -21.0
    assert drawdown.daily_fraction == pytest.approx(0.021)
    assert updated.circuit_status is CircuitStatus.DAILY_PAUSED


def test_high_water_marks_are_conservative_references():
    raised = refresh(state(), 1100.0)
    lowered = refresh(raised, 1077.0, NOW + timedelta(seconds=1))
    assert lowered.daily_high_water_equity == 1100.0
    assert lowered.circuit_status is CircuitStatus.DAILY_PAUSED


def outcome(index, pnl, timestamp=None):
    return ClosedTradeOutcome(
        outcome_id=f"outcome-{index}",
        trade_id=f"trade-{index}",
        timestamp=timestamp or NOW + timedelta(minutes=index),
        gross_realized_pnl=pnl,
        metadata={"cost_basis": "gross_before_costs"},
    )


def test_three_losses_pause_and_duplicate_outcome_is_idempotent():
    current = state()
    for index in range(1, 4):
        current, consumed = consume_closed_outcome(current, outcome(index, -1.0), policy())
        assert consumed
    duplicate, consumed = consume_closed_outcome(current, outcome(3, -1.0), policy())
    assert current.circuit_status is CircuitStatus.LOSS_STREAK_PAUSED
    assert current.consecutive_losses == 3
    assert consumed is False and duplicate == current


def test_break_even_does_not_extend_streak_and_winner_resets_it():
    current, _ = consume_closed_outcome(state(), outcome(1, -1.0), policy())
    break_even, _ = consume_closed_outcome(current, outcome(2, 0.0), policy())
    winner, _ = consume_closed_outcome(break_even, outcome(3, 2.0), policy())
    assert break_even.consecutive_losses == 1
    assert winner.consecutive_losses == 0


def test_partial_outcome_is_not_consumed_as_complete_trade():
    partial = replace(outcome(1, 2.0), final=False)
    updated, consumed = consume_closed_outcome(state(), partial, policy())
    assert consumed is False
    assert updated == state()


def test_daily_reset_does_not_clear_weekly_or_hard_stop():
    weekly = replace(state(), circuit_status=CircuitStatus.WEEKLY_PAUSED)
    next_day = NOW + timedelta(days=1)
    weekly_after = refresh(weekly, 1000.0, next_day)
    hard = replace(state(), circuit_status=CircuitStatus.HARD_STOPPED)
    next_week = NOW + timedelta(days=7)
    hard_after = refresh(hard, 1000.0, next_week)
    assert weekly_after.circuit_status is CircuitStatus.WEEKLY_PAUSED
    assert hard_after.circuit_status is CircuitStatus.HARD_STOPPED


def test_weekly_pause_survives_daily_boundary_with_same_week_drawdown():
    weekly = refresh(state(), 950.0)
    next_day = NOW + timedelta(days=1)
    result = refresh(weekly, 950.0, next_day)
    assert result.circuit_status is CircuitStatus.WEEKLY_PAUSED


def test_stale_snapshot_enters_data_unsafe_and_rejects():
    stale_account = snapshot(timestamp=NOW - timedelta(seconds=61))
    updated, _ = apply_account_snapshot(state(), stale_account, policy(), now=NOW)
    decision = assess_trade_risk(
        policy=policy(),
        state=updated,
        snapshot=stale_account,
        specification=specification(),
        direction="buy",
        entry=100.0,
        stop=99.0,
        open_risk_items=(),
        now=NOW,
    )
    assert updated.circuit_status is CircuitStatus.DATA_UNSAFE
    assert not decision.approved


def test_normal_strategy_state_fields_do_not_refresh_risk_periods():
    current = state()
    updated, _ = consume_closed_outcome(current, outcome(1, 1.0), policy())
    assert updated.initialized_at == current.initialized_at
    assert updated.daily_period == current.daily_period
    assert updated.weekly_period == current.weekly_period
