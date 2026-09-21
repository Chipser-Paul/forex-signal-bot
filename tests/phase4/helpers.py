from __future__ import annotations

from datetime import datetime, timezone

from bot.execution.risk import (
    AccountSnapshot,
    SymbolRiskSpecification,
    initialize_risk_state,
    validation_policy,
)


UTC = timezone.utc
NOW = datetime(2026, 1, 14, 12, 0, tzinfo=UTC)


def policy():
    return validation_policy({})


def snapshot(
    equity: float = 1000.0,
    *,
    balance: float = 1000.0,
    timestamp: datetime = NOW,
    account_ref: str = "account-test",
    source: str = "simulation",
):
    return AccountSnapshot(
        account_ref=account_ref,
        balance=balance,
        equity=equity,
        floating_pnl=equity - balance,
        margin=0.0,
        free_margin=equity,
        currency="USD",
        timestamp=timestamp,
        source=source,
    )


def specification(
    *,
    tick_size: float = 0.1,
    tick_value: float = 1.0,
    volume_min: float = 0.01,
    volume_max: float = 100.0,
    volume_step: float = 0.01,
):
    return SymbolRiskSpecification(
        symbol="TEST",
        tick_size=tick_size,
        tick_value=tick_value,
        volume_min=volume_min,
        volume_max=volume_max,
        volume_step=volume_step,
        price_precision=2,
        contract_size=100.0,
    )


def state(account=None, risk_policy=None):
    return initialize_risk_state(
        account or snapshot(),
        risk_policy or policy(),
        known_strategy_positions=0,
    )
