from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .models import (
    AccountSnapshot,
    CircuitStatus,
    ClosedTradeOutcome,
    DrawdownSnapshot,
    RiskError,
    RiskPolicy,
    RiskState,
    SCHEMA_VERSION,
    utc_datetime,
)


def daily_period_id(timestamp: datetime) -> str:
    return utc_datetime(timestamp, "period timestamp").date().isoformat()


def weekly_period_id(timestamp: datetime) -> str:
    value = utc_datetime(timestamp, "period timestamp")
    monday = value.date() - timedelta(days=value.weekday())
    return monday.isoformat()


def initialize_risk_state(
    snapshot: AccountSnapshot,
    policy: RiskPolicy,
    *,
    known_strategy_positions: int,
) -> RiskState:
    if known_strategy_positions != 0:
        raise RiskError("risk state can only initialize with zero known strategy positions")
    equity = snapshot.equity
    return RiskState(
        schema_version=SCHEMA_VERSION,
        account_ref=snapshot.account_ref,
        policy_version=policy.policy_version,
        initialized_at=snapshot.timestamp,
        validation_starting_equity=equity,
        current_equity=equity,
        daily_period=daily_period_id(snapshot.timestamp),
        daily_starting_equity=equity,
        daily_high_water_equity=equity,
        weekly_period=weekly_period_id(snapshot.timestamp),
        weekly_starting_equity=equity,
        weekly_high_water_equity=equity,
        overall_high_water_equity=equity,
        last_snapshot_at=snapshot.timestamp,
    )


def _drawdown(current: float, *references: float) -> float:
    return max(0.0, *((reference - current) / reference for reference in references))


def drawdown_snapshot(state: RiskState) -> DrawdownSnapshot:
    return DrawdownSnapshot(
        daily_fraction=_drawdown(
            state.current_equity,
            state.daily_starting_equity,
            state.daily_high_water_equity,
        ),
        weekly_fraction=_drawdown(
            state.current_equity,
            state.weekly_starting_equity,
            state.weekly_high_water_equity,
        ),
        total_fraction=_drawdown(
            state.current_equity,
            state.validation_starting_equity,
            state.overall_high_water_equity,
        ),
    )


def apply_account_snapshot(
    state: RiskState,
    snapshot: AccountSnapshot,
    policy: RiskPolicy,
    *,
    now: datetime,
) -> tuple[RiskState, DrawdownSnapshot]:
    now = utc_datetime(now, "risk evaluation time")
    if state.account_ref != snapshot.account_ref:
        raise RiskError("account identity does not match persisted risk state")
    if state.policy_version != policy.policy_version:
        raise RiskError("policy identity does not match persisted risk state")
    if not snapshot.is_fresh(now, policy.account_snapshot_freshness_seconds):
        unsafe = replace(state, circuit_status=CircuitStatus.DATA_UNSAFE)
        return unsafe, drawdown_snapshot(unsafe)

    daily_period = daily_period_id(now)
    weekly_period = weekly_period_id(now)
    daily_changed = daily_period != state.daily_period
    weekly_changed = weekly_period != state.weekly_period
    daily_start = snapshot.equity if daily_changed else state.daily_starting_equity
    daily_high = snapshot.equity if daily_changed else max(state.daily_high_water_equity, snapshot.equity)
    weekly_start = snapshot.equity if weekly_changed else state.weekly_starting_equity
    weekly_high = snapshot.equity if weekly_changed else max(state.weekly_high_water_equity, snapshot.equity)
    overall_high = max(state.overall_high_water_equity, snapshot.equity)
    candidate = replace(
        state,
        current_equity=snapshot.equity,
        daily_period=daily_period,
        daily_starting_equity=daily_start,
        daily_high_water_equity=daily_high,
        weekly_period=weekly_period,
        weekly_starting_equity=weekly_start,
        weekly_high_water_equity=weekly_high,
        overall_high_water_equity=overall_high,
        last_snapshot_at=snapshot.timestamp,
    )
    drawdown = drawdown_snapshot(candidate)
    if state.circuit_status is CircuitStatus.HARD_STOPPED or drawdown.total_fraction >= policy.total_drawdown_limit:
        status = CircuitStatus.HARD_STOPPED
    elif state.circuit_status is CircuitStatus.WEEKLY_PAUSED and not weekly_changed:
        status = CircuitStatus.WEEKLY_PAUSED
    elif drawdown.weekly_fraction >= policy.weekly_drawdown_limit:
        status = CircuitStatus.WEEKLY_PAUSED
    elif state.circuit_status is CircuitStatus.DAILY_PAUSED and not daily_changed:
        status = CircuitStatus.DAILY_PAUSED
    elif drawdown.daily_fraction >= policy.daily_drawdown_limit:
        status = CircuitStatus.DAILY_PAUSED
    elif candidate.consecutive_losses >= policy.consecutive_loss_limit:
        status = CircuitStatus.LOSS_STREAK_PAUSED
    else:
        status = CircuitStatus.ACTIVE
    return replace(candidate, circuit_status=status), drawdown


def consume_closed_outcome(
    state: RiskState,
    outcome: ClosedTradeOutcome,
    policy: RiskPolicy,
) -> tuple[RiskState, bool]:
    if not outcome.final:
        return state, False
    if outcome.outcome_id in state.processed_outcome_ids:
        return state, False
    if state.last_trade_at is not None and outcome.timestamp < state.last_trade_at:
        raise RiskError("trade outcome timestamps cannot move backward")
    if outcome.gross_realized_pnl < 0:
        consecutive = state.consecutive_losses + 1
    elif outcome.gross_realized_pnl > 0:
        consecutive = 0
    else:
        consecutive = state.consecutive_losses
    status = state.circuit_status
    if status is not CircuitStatus.HARD_STOPPED:
        if consecutive >= policy.consecutive_loss_limit:
            status = CircuitStatus.LOSS_STREAK_PAUSED
        elif outcome.gross_realized_pnl > 0 and status is CircuitStatus.LOSS_STREAK_PAUSED:
            status = CircuitStatus.ACTIVE
    updated = replace(
        state,
        circuit_status=status,
        consecutive_losses=consecutive,
        realized_strategy_pnl=state.realized_strategy_pnl + outcome.gross_realized_pnl,
        processed_outcome_ids=state.processed_outcome_ids + (outcome.outcome_id,),
        last_trade_at=outcome.timestamp,
    )
    return updated, True
