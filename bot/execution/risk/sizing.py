from __future__ import annotations

import math
from decimal import Decimal, ROUND_FLOOR
from typing import Callable, Iterable

from .models import (
    AccountSnapshot,
    CircuitStatus,
    OpenRiskItem,
    RiskDecision,
    RiskPolicy,
    RiskReason,
    RiskState,
    SymbolRiskSpecification,
    finite,
    stable_ref,
    utc_datetime,
)


ProfitCalculator = Callable[[str, str, float, float, float], float | None]


def loss_for_volume(
    direction: str,
    specification: SymbolRiskSpecification,
    entry: float,
    stop: float,
    volume: float,
    *,
    profit_calculator: ProfitCalculator | None = None,
) -> tuple[float, str]:
    entry = finite(entry, "entry")
    stop = finite(stop, "stop")
    volume = finite(volume, "volume")
    if volume <= 0 or entry == stop:
        raise ValueError("volume and stop distance must be positive")
    if direction == "buy" and stop >= entry:
        raise ValueError("buy stop must be below entry")
    if direction == "sell" and stop <= entry:
        raise ValueError("sell stop must be above entry")
    if direction not in ("buy", "sell"):
        raise ValueError("direction must be buy or sell")
    if profit_calculator is not None:
        try:
            calculated = profit_calculator(direction, specification.symbol, volume, entry, stop)
        except Exception as exc:
            raise ValueError("broker profit calculation failed") from exc
        if calculated is not None:
            loss = abs(finite(calculated, "broker loss calculation"))
            if loss > 0:
                return loss, "broker_order_calc_profit"
    loss = abs(entry - stop) / specification.tick_size * specification.tick_value * volume
    if not math.isfinite(loss) or loss <= 0:
        raise ValueError("symbol metadata cannot calculate monetary loss")
    return loss, "tick_value_fallback"


def normalize_volume_down(raw_volume: float, specification: SymbolRiskSpecification) -> float:
    raw = Decimal(str(finite(raw_volume, "raw volume")))
    step = Decimal(str(specification.volume_step))
    maximum = Decimal(str(specification.volume_max))
    bounded = min(raw, maximum)
    units = (bounded / step).to_integral_value(rounding=ROUND_FLOOR)
    normalized = units * step
    return float(normalized)


def aggregate_open_risk(items: Iterable[OpenRiskItem]) -> tuple[float | None, str | None]:
    total = 0.0
    for item in items:
        if item.current_stop is None or item.estimated_loss is None:
            return None, item.trade_id
        total += item.estimated_loss
    return total, None


def _reject(
    reason: RiskReason,
    *,
    now,
    policy: RiskPolicy,
    state: RiskState | None = None,
    snapshot: AccountSnapshot | None = None,
    requested: float | None = None,
    permitted: float | None = None,
    budget: float | None = None,
    raw_volume: float | None = None,
    normalized_volume: float | None = None,
    normalized_loss: float | None = None,
    aggregate_before: float | None = None,
    aggregate_after: float | None = None,
    calculation_method: str | None = None,
    diagnostics: dict | None = None,
) -> RiskDecision:
    timestamp = utc_datetime(now, "risk decision time")
    return RiskDecision(
        approved=False,
        reason=reason,
        decision_id=stable_ref(policy.policy_version, reason.value, timestamp.isoformat(), requested),
        timestamp=timestamp,
        policy_version=policy.policy_version,
        equity_basis=None if snapshot is None else snapshot.conservative_equity_basis,
        requested_risk_fraction=requested,
        permitted_risk_fraction=permitted,
        monetary_risk_budget=budget,
        raw_volume=raw_volume,
        normalized_volume=normalized_volume,
        estimated_normalized_loss=normalized_loss,
        aggregate_open_risk_before=aggregate_before,
        aggregate_open_risk_after=aggregate_after,
        circuit_status=None if state is None else state.circuit_status,
        calculation_method=calculation_method,
        diagnostics=dict(diagnostics or {}),
    )


def assess_trade_risk(
    *,
    policy: RiskPolicy,
    state: RiskState,
    snapshot: AccountSnapshot,
    specification: SymbolRiskSpecification,
    direction: str,
    entry: float,
    stop: float,
    open_risk_items: Iterable[OpenRiskItem],
    now,
    requested_risk_fraction: float | None = None,
    profit_calculator: ProfitCalculator | None = None,
    numeric_tolerance: float = 1e-9,
) -> RiskDecision:
    timestamp = utc_datetime(now, "risk decision time")
    requested = policy.base_risk_fraction if requested_risk_fraction is None else finite(
        requested_risk_fraction,
        "requested risk fraction",
    )
    if state.account_ref != snapshot.account_ref:
        return _reject(RiskReason.ACCOUNT_IDENTITY_MISMATCH, now=timestamp, policy=policy, state=state, snapshot=snapshot, requested=requested)
    if not snapshot.is_fresh(timestamp, policy.account_snapshot_freshness_seconds):
        return _reject(RiskReason.ACCOUNT_DATA_STALE, now=timestamp, policy=policy, state=state, snapshot=snapshot, requested=requested)
    if state.circuit_status is not CircuitStatus.ACTIVE:
        reason = {
            CircuitStatus.DAILY_PAUSED: RiskReason.DAILY_DRAWDOWN_LIMIT,
            CircuitStatus.WEEKLY_PAUSED: RiskReason.WEEKLY_DRAWDOWN_LIMIT,
            CircuitStatus.HARD_STOPPED: RiskReason.TOTAL_DRAWDOWN_LIMIT,
            CircuitStatus.LOSS_STREAK_PAUSED: RiskReason.LOSS_STREAK_LIMIT,
            CircuitStatus.STATE_CORRUPT: RiskReason.RISK_STATE_CORRUPT,
            CircuitStatus.DATA_UNSAFE: RiskReason.ACCOUNT_DATA_STALE,
        }[state.circuit_status]
        return _reject(reason, now=timestamp, policy=policy, state=state, snapshot=snapshot, requested=requested)
    if requested <= 0:
        return _reject(RiskReason.INVALID_RISK_FRACTION, now=timestamp, policy=policy, state=state, snapshot=snapshot, requested=requested)
    if requested > policy.absolute_risk_ceiling + numeric_tolerance:
        return _reject(
            RiskReason.RISK_ABOVE_HARD_CEILING,
            now=timestamp,
            policy=policy,
            state=state,
            snapshot=snapshot,
            requested=requested,
            permitted=policy.absolute_risk_ceiling,
            diagnostics={"ceiling": policy.absolute_risk_ceiling},
        )
    items = tuple(open_risk_items)
    same_symbol = sum(1 for item in items if item.symbol == specification.symbol)
    if same_symbol >= policy.max_strategy_ideas_per_symbol:
        return _reject(RiskReason.SYMBOL_IDEA_LIMIT, now=timestamp, policy=policy, state=state, snapshot=snapshot, requested=requested)
    aggregate_before, unsafe_trade = aggregate_open_risk(items)
    if aggregate_before is None:
        return _reject(
            RiskReason.UNBOUNDED_OPEN_RISK,
            now=timestamp,
            policy=policy,
            state=state,
            snapshot=snapshot,
            requested=requested,
            diagnostics={"unsafe_trade_ref": stable_ref(unsafe_trade)},
        )
    equity_basis = snapshot.conservative_equity_basis
    budget = equity_basis * requested
    try:
        checked_entry = finite(entry, "entry")
        checked_stop = finite(stop, "stop")
        if direction not in ("buy", "sell"):
            raise ValueError("direction must be buy or sell")
        if checked_entry == checked_stop:
            raise ValueError("stop distance must be positive")
        if direction == "buy" and checked_stop >= checked_entry:
            raise ValueError("buy stop must be below entry")
        if direction == "sell" and checked_stop <= checked_entry:
            raise ValueError("sell stop must be above entry")
    except (ValueError, TypeError):
        return _reject(RiskReason.INVALID_STOP, now=timestamp, policy=policy, state=state, snapshot=snapshot, requested=requested, aggregate_before=aggregate_before)
    try:
        one_lot_loss, method = loss_for_volume(
            direction,
            specification,
            entry,
            stop,
            1.0,
            profit_calculator=profit_calculator,
        )
    except (ValueError, TypeError):
        return _reject(RiskReason.LOSS_CALCULATION_FAILED, now=timestamp, policy=policy, state=state, snapshot=snapshot, requested=requested, aggregate_before=aggregate_before)
    raw_volume = budget / one_lot_loss
    if raw_volume < specification.volume_min - numeric_tolerance:
        return _reject(
            RiskReason.MINIMUM_VOLUME_EXCEEDS_RISK,
            now=timestamp,
            policy=policy,
            state=state,
            snapshot=snapshot,
            requested=requested,
            permitted=requested,
            budget=budget,
            raw_volume=raw_volume,
            aggregate_before=aggregate_before,
            calculation_method=method,
            diagnostics={"raw_volume": raw_volume, "minimum_volume": specification.volume_min},
        )
    normalized = normalize_volume_down(raw_volume, specification)
    if normalized < specification.volume_min - numeric_tolerance or normalized <= 0:
        return _reject(RiskReason.VOLUME_NORMALIZATION_FAILED, now=timestamp, policy=policy, state=state, snapshot=snapshot, requested=requested, permitted=requested, budget=budget, raw_volume=raw_volume, normalized_volume=normalized, aggregate_before=aggregate_before, calculation_method=method)
    try:
        normalized_loss, method = loss_for_volume(
            direction,
            specification,
            entry,
            stop,
            normalized,
            profit_calculator=profit_calculator,
        )
    except (ValueError, TypeError):
        return _reject(RiskReason.LOSS_CALCULATION_FAILED, now=timestamp, policy=policy, state=state, snapshot=snapshot, requested=requested, permitted=requested, budget=budget, raw_volume=raw_volume, normalized_volume=normalized, aggregate_before=aggregate_before, calculation_method=method)
    if normalized_loss > budget + numeric_tolerance:
        return _reject(RiskReason.POST_NORMALIZATION_RISK_EXCEEDED, now=timestamp, policy=policy, state=state, snapshot=snapshot, requested=requested, permitted=requested, budget=budget, raw_volume=raw_volume, normalized_volume=normalized, normalized_loss=normalized_loss, aggregate_before=aggregate_before, calculation_method=method)
    aggregate_after = aggregate_before + normalized_loss
    aggregate_cap = equity_basis * policy.aggregate_open_risk_ceiling
    if aggregate_after > aggregate_cap + numeric_tolerance:
        return _reject(
            RiskReason.AGGREGATE_RISK_LIMIT,
            now=timestamp,
            policy=policy,
            state=state,
            snapshot=snapshot,
            requested=requested,
            permitted=requested,
            budget=budget,
            raw_volume=raw_volume,
            normalized_volume=normalized,
            normalized_loss=normalized_loss,
            aggregate_before=aggregate_before,
            aggregate_after=aggregate_after,
            calculation_method=method,
            diagnostics={"aggregate_after": aggregate_after, "aggregate_cap": aggregate_cap},
        )
    return RiskDecision(
        approved=True,
        reason=RiskReason.APPROVED,
        decision_id=stable_ref(policy.policy_version, specification.symbol, timestamp.isoformat(), normalized),
        timestamp=timestamp,
        policy_version=policy.policy_version,
        equity_basis=equity_basis,
        requested_risk_fraction=requested,
        permitted_risk_fraction=requested,
        monetary_risk_budget=budget,
        raw_volume=raw_volume,
        normalized_volume=normalized,
        estimated_normalized_loss=normalized_loss,
        aggregate_open_risk_before=aggregate_before,
        aggregate_open_risk_after=aggregate_after,
        circuit_status=state.circuit_status,
        calculation_method=method,
        diagnostics={"aggregate_cap": aggregate_cap},
    )
