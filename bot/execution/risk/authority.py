from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable

from .models import (
    AccountSnapshot,
    CircuitStatus,
    ClosedTradeOutcome,
    OpenRiskItem,
    RiskDecision,
    RiskPolicy,
    RiskReason,
    RiskState,
    SymbolRiskSpecification,
    stable_ref,
    utc_datetime,
)
from .sizing import ProfitCalculator, assess_trade_risk
from .state import apply_account_snapshot, consume_closed_outcome, initialize_risk_state
from .store import RiskStateStore, StoreStatus


def unavailable_decision(
    reason: RiskReason,
    *,
    policy: RiskPolicy,
    now: datetime,
    status: CircuitStatus,
) -> RiskDecision:
    timestamp = utc_datetime(now, "risk decision time")
    return RiskDecision(
        approved=False,
        reason=reason,
        decision_id=stable_ref(policy.policy_version, reason.value, timestamp.isoformat()),
        timestamp=timestamp,
        policy_version=policy.policy_version,
        circuit_status=status,
    )


class PersistentRiskAuthority:
    def __init__(self, policy: RiskPolicy, store: RiskStateStore) -> None:
        self.policy = policy
        self.store = store

    def initialize(self, snapshot: AccountSnapshot, *, known_strategy_positions: int) -> RiskState:
        state = initialize_risk_state(
            snapshot,
            self.policy,
            known_strategy_positions=known_strategy_positions,
        )
        self.store.initialize(state)
        return state

    def _load_refresh(self, snapshot: AccountSnapshot, now: datetime) -> tuple[RiskState | None, RiskDecision | None]:
        loaded = self.store.load()
        if loaded.status is StoreStatus.UNINITIALIZED:
            return None, unavailable_decision(
                RiskReason.RISK_STATE_UNINITIALIZED,
                policy=self.policy,
                now=now,
                status=CircuitStatus.DATA_UNSAFE,
            )
        if loaded.status is StoreStatus.MISSING_PRIMARY:
            return None, unavailable_decision(
                RiskReason.RISK_STATE_CORRUPT,
                policy=self.policy,
                now=now,
                status=CircuitStatus.STATE_CORRUPT,
            )
        if loaded.status is StoreStatus.STATE_CORRUPT or loaded.state is None:
            return None, unavailable_decision(
                RiskReason.RISK_STATE_CORRUPT,
                policy=self.policy,
                now=now,
                status=CircuitStatus.STATE_CORRUPT,
            )
        if loaded.state.account_ref != snapshot.account_ref:
            return None, unavailable_decision(
                RiskReason.ACCOUNT_IDENTITY_MISMATCH,
                policy=self.policy,
                now=now,
                status=CircuitStatus.DATA_UNSAFE,
            )
        if loaded.state.policy_version != self.policy.policy_version:
            return None, unavailable_decision(
                RiskReason.POLICY_IDENTITY_MISMATCH,
                policy=self.policy,
                now=now,
                status=CircuitStatus.DATA_UNSAFE,
            )
        try:
            state, _ = apply_account_snapshot(loaded.state, snapshot, self.policy, now=now)
        except ValueError:
            return None, unavailable_decision(
                RiskReason.ACCOUNT_IDENTITY_MISMATCH,
                policy=self.policy,
                now=now,
                status=CircuitStatus.DATA_UNSAFE,
            )
        self.store.save(state)
        return state, None

    def decide(
        self,
        *,
        snapshot: AccountSnapshot,
        specification: SymbolRiskSpecification,
        direction: str,
        entry: float,
        stop: float,
        open_risk_items: Iterable[OpenRiskItem],
        now: datetime,
        requested_risk_fraction: float | None = None,
        profit_calculator: ProfitCalculator | None = None,
    ) -> RiskDecision:
        state, unavailable = self._load_refresh(snapshot, now)
        if unavailable is not None:
            return unavailable
        assert state is not None
        return assess_trade_risk(
            policy=self.policy,
            state=state,
            snapshot=snapshot,
            specification=specification,
            direction=direction,
            entry=entry,
            stop=stop,
            open_risk_items=open_risk_items,
            now=now,
            requested_risk_fraction=requested_risk_fraction,
            profit_calculator=profit_calculator,
        )

    def consume_outcome(
        self,
        snapshot: AccountSnapshot,
        outcome: ClosedTradeOutcome,
        *,
        now: datetime,
    ) -> tuple[RiskState | None, bool]:
        state, unavailable = self._load_refresh(snapshot, now)
        if unavailable is not None or state is None:
            return None, False
        updated, consumed = consume_closed_outcome(state, outcome, self.policy)
        if consumed:
            self.store.save(updated)
        return updated, consumed


class InMemoryRiskAuthority:
    def __init__(self, policy: RiskPolicy, initial_state: RiskState) -> None:
        self.policy = policy
        self.state = initial_state

    def refresh(self, snapshot: AccountSnapshot, *, now: datetime) -> RiskState:
        self.state, _ = apply_account_snapshot(self.state, snapshot, self.policy, now=now)
        return self.state

    def decide(self, **kwargs) -> RiskDecision:
        snapshot = kwargs["snapshot"]
        now = kwargs["now"]
        self.refresh(snapshot, now=now)
        return assess_trade_risk(policy=self.policy, state=self.state, **kwargs)

    def consume_outcome(self, outcome: ClosedTradeOutcome) -> bool:
        self.state, consumed = consume_closed_outcome(self.state, outcome, self.policy)
        return consumed
