from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


SCHEMA_VERSION = 1
RISK_GATE_ORDER = (
    "policy_configuration",
    "account_identity",
    "fresh_account_snapshot",
    "risk_state_integrity",
    "circuit_status",
    "equity_drawdown",
    "consecutive_losses",
    "same_symbol_idea_limit",
    "aggregate_open_risk",
    "proposed_stop",
    "raw_volume",
    "downward_volume_normalization",
    "post_normalization_risk",
    "final_risk_approval",
    "entry_intent_eligibility",
)


class RiskError(ValueError):
    """Raised when risk-domain input violates the fail-closed contract."""


class CircuitStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DAILY_PAUSED = "DAILY_PAUSED"
    WEEKLY_PAUSED = "WEEKLY_PAUSED"
    LOSS_STREAK_PAUSED = "LOSS_STREAK_PAUSED"
    HARD_STOPPED = "HARD_STOPPED"
    DATA_UNSAFE = "DATA_UNSAFE"
    STATE_CORRUPT = "STATE_CORRUPT"


class RiskReason(str, Enum):
    APPROVED = "APPROVED"
    INVALID_POLICY = "INVALID_POLICY"
    ACCOUNT_IDENTITY_MISMATCH = "ACCOUNT_IDENTITY_MISMATCH"
    POLICY_IDENTITY_MISMATCH = "POLICY_IDENTITY_MISMATCH"
    ACCOUNT_DATA_MISSING = "ACCOUNT_DATA_MISSING"
    ACCOUNT_DATA_STALE = "ACCOUNT_DATA_STALE"
    INVALID_EQUITY = "INVALID_EQUITY"
    RISK_STATE_UNINITIALIZED = "RISK_STATE_UNINITIALIZED"
    RISK_STATE_CORRUPT = "RISK_STATE_CORRUPT"
    DAILY_DRAWDOWN_LIMIT = "DAILY_DRAWDOWN_LIMIT"
    WEEKLY_DRAWDOWN_LIMIT = "WEEKLY_DRAWDOWN_LIMIT"
    TOTAL_DRAWDOWN_LIMIT = "TOTAL_DRAWDOWN_LIMIT"
    LOSS_STREAK_LIMIT = "LOSS_STREAK_LIMIT"
    INVALID_RISK_FRACTION = "INVALID_RISK_FRACTION"
    RISK_ABOVE_HARD_CEILING = "RISK_ABOVE_HARD_CEILING"
    SYMBOL_IDEA_LIMIT = "SYMBOL_IDEA_LIMIT"
    UNBOUNDED_OPEN_RISK = "UNBOUNDED_OPEN_RISK"
    AGGREGATE_RISK_LIMIT = "AGGREGATE_RISK_LIMIT"
    INVALID_STOP = "INVALID_STOP"
    INVALID_SYMBOL_SPEC = "INVALID_SYMBOL_SPEC"
    LOSS_CALCULATION_FAILED = "LOSS_CALCULATION_FAILED"
    MINIMUM_VOLUME_EXCEEDS_RISK = "MINIMUM_VOLUME_EXCEEDS_RISK"
    VOLUME_NORMALIZATION_FAILED = "VOLUME_NORMALIZATION_FAILED"
    POST_NORMALIZATION_RISK_EXCEEDED = "POST_NORMALIZATION_RISK_EXCEEDED"


def stable_ref(*parts: object) -> str:
    material = "|".join(str(part) for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RiskError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def finite(value: float, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise RiskError(f"{field_name} must be finite")
    return number


def positive(value: float, field_name: str, *, allow_zero: bool = False) -> float:
    number = finite(value, field_name)
    if number < 0 or (not allow_zero and number == 0):
        qualifier = "non-negative" if allow_zero else "positive"
        raise RiskError(f"{field_name} must be {qualifier}")
    return number


@dataclass(frozen=True)
class RiskPolicy:
    policy_version: str = "phase4-validation-v1"
    base_risk_fraction: float = 0.0035
    absolute_risk_ceiling: float = 0.0050
    aggregate_open_risk_ceiling: float = 0.0100
    daily_drawdown_limit: float = 0.0200
    weekly_drawdown_limit: float = 0.0400
    total_drawdown_limit: float = 0.0800
    consecutive_loss_limit: int = 3
    max_strategy_ideas_per_symbol: int = 1
    daily_reset_timezone: str = "UTC"
    weekly_reset_definition: str = "MONDAY_00_UTC"
    account_snapshot_freshness_seconds: int = 60
    risk_increase_policy: str = "DISABLED"
    missing_state_policy: str = "FAIL_CLOSED"
    corrupt_state_policy: str = "FAIL_CLOSED"

    def __post_init__(self) -> None:
        fractions = (
            self.base_risk_fraction,
            self.absolute_risk_ceiling,
            self.aggregate_open_risk_ceiling,
            self.daily_drawdown_limit,
            self.weekly_drawdown_limit,
            self.total_drawdown_limit,
        )
        if any(not 0 < finite(value, "policy fraction") < 1 for value in fractions):
            raise RiskError("policy fractions must be between zero and one")
        if self.base_risk_fraction > self.absolute_risk_ceiling:
            raise RiskError("base risk cannot exceed the absolute ceiling")
        if self.absolute_risk_ceiling > self.aggregate_open_risk_ceiling:
            raise RiskError("per-trade ceiling cannot exceed aggregate ceiling")
        if not (
            self.daily_drawdown_limit
            <= self.weekly_drawdown_limit
            <= self.total_drawdown_limit
        ):
            raise RiskError("drawdown limits must be ordered daily, weekly, total")
        if self.consecutive_loss_limit < 1 or self.max_strategy_ideas_per_symbol < 1:
            raise RiskError("circuit and idea limits must be positive integers")
        if self.account_snapshot_freshness_seconds < 1:
            raise RiskError("account freshness must be positive")
        if self.daily_reset_timezone != "UTC" or self.weekly_reset_definition != "MONDAY_00_UTC":
            raise RiskError("Phase 4 validation periods must use UTC boundaries")
        if self.risk_increase_policy != "DISABLED":
            raise RiskError("automatic risk increases are prohibited")
        if self.missing_state_policy != "FAIL_CLOSED" or self.corrupt_state_policy != "FAIL_CLOSED":
            raise RiskError("missing and corrupt risk state must fail closed")


@dataclass(frozen=True)
class AccountSnapshot:
    account_ref: str
    balance: float
    equity: float
    floating_pnl: float
    margin: float
    free_margin: float
    currency: str
    timestamp: datetime
    source: str

    def __post_init__(self) -> None:
        if not self.account_ref or not self.source:
            raise RiskError("sanitized account reference and snapshot source are required")
        object.__setattr__(self, "timestamp", utc_datetime(self.timestamp, "account timestamp"))
        object.__setattr__(self, "balance", positive(self.balance, "account balance"))
        object.__setattr__(self, "equity", positive(self.equity, "account equity"))
        object.__setattr__(self, "floating_pnl", finite(self.floating_pnl, "floating P&L"))
        object.__setattr__(self, "margin", positive(self.margin, "margin", allow_zero=True))
        object.__setattr__(self, "free_margin", finite(self.free_margin, "free margin"))

    @property
    def conservative_equity_basis(self) -> float:
        return min(self.balance, self.equity)

    def is_fresh(self, now: datetime, maximum_age_seconds: int) -> bool:
        age = (utc_datetime(now, "decision timestamp") - self.timestamp).total_seconds()
        return 0 <= age <= maximum_age_seconds


@dataclass(frozen=True)
class SymbolRiskSpecification:
    symbol: str
    tick_size: float
    tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float
    price_precision: int
    contract_size: float | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise RiskError("symbol is required")
        for name in ("tick_size", "tick_value", "volume_min", "volume_max", "volume_step"):
            object.__setattr__(self, name, positive(getattr(self, name), name))
        if self.volume_max < self.volume_min:
            raise RiskError("maximum volume cannot be below minimum volume")
        if self.price_precision < 0:
            raise RiskError("price precision cannot be negative")
        if self.contract_size is not None:
            object.__setattr__(self, "contract_size", positive(self.contract_size, "contract size"))


@dataclass(frozen=True)
class OpenRiskItem:
    trade_id: str
    symbol: str
    direction: str
    remaining_volume: float
    current_reference_price: float
    current_stop: float | None
    estimated_loss: float | None
    ownership: str
    calculation_method: str
    entry_price: float | None = None

    def __post_init__(self) -> None:
        if not self.trade_id or not self.symbol or self.direction not in ("buy", "sell"):
            raise RiskError("open-risk identity and direction are required")
        object.__setattr__(self, "remaining_volume", positive(self.remaining_volume, "remaining volume"))
        object.__setattr__(self, "current_reference_price", finite(self.current_reference_price, "reference price"))
        if self.current_stop is not None:
            object.__setattr__(self, "current_stop", finite(self.current_stop, "current stop"))
        if self.estimated_loss is not None:
            object.__setattr__(self, "estimated_loss", positive(self.estimated_loss, "estimated loss", allow_zero=True))
        if self.entry_price is not None:
            object.__setattr__(self, "entry_price", finite(self.entry_price, "entry price"))


@dataclass(frozen=True)
class DrawdownSnapshot:
    daily_fraction: float
    weekly_fraction: float
    total_fraction: float


@dataclass(frozen=True)
class RiskState:
    schema_version: int
    account_ref: str
    policy_version: str
    initialized_at: datetime
    validation_starting_equity: float
    current_equity: float
    daily_period: str
    daily_starting_equity: float
    daily_high_water_equity: float
    weekly_period: str
    weekly_starting_equity: float
    weekly_high_water_equity: float
    overall_high_water_equity: float
    circuit_status: CircuitStatus = CircuitStatus.ACTIVE
    consecutive_losses: int = 0
    realized_strategy_pnl: float = 0.0
    processed_outcome_ids: tuple[str, ...] = ()
    last_trade_at: datetime | None = None
    last_snapshot_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise RiskError("unsupported risk-state schema version")
        if not self.account_ref or not self.policy_version:
            raise RiskError("risk-state account and policy identities are required")
        object.__setattr__(self, "initialized_at", utc_datetime(self.initialized_at, "initialization time"))
        for name in (
            "validation_starting_equity",
            "current_equity",
            "daily_starting_equity",
            "daily_high_water_equity",
            "weekly_starting_equity",
            "weekly_high_water_equity",
            "overall_high_water_equity",
        ):
            object.__setattr__(self, name, positive(getattr(self, name), name))
        object.__setattr__(self, "realized_strategy_pnl", finite(self.realized_strategy_pnl, "realized strategy P&L"))
        if self.consecutive_losses < 0:
            raise RiskError("consecutive losses cannot be negative")
        if len(set(self.processed_outcome_ids)) != len(self.processed_outcome_ids):
            raise RiskError("processed outcome IDs must be unique")
        if self.last_trade_at is not None:
            object.__setattr__(self, "last_trade_at", utc_datetime(self.last_trade_at, "last trade time"))
        if self.last_snapshot_at is not None:
            object.__setattr__(self, "last_snapshot_at", utc_datetime(self.last_snapshot_at, "last snapshot time"))


@dataclass(frozen=True)
class ClosedTradeOutcome:
    outcome_id: str
    trade_id: str
    timestamp: datetime
    gross_realized_pnl: float
    final: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.outcome_id or not self.trade_id:
            raise RiskError("outcome and trade identities are required")
        object.__setattr__(self, "timestamp", utc_datetime(self.timestamp, "outcome timestamp"))
        object.__setattr__(self, "gross_realized_pnl", finite(self.gross_realized_pnl, "gross realized P&L"))


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: RiskReason
    decision_id: str
    timestamp: datetime
    policy_version: str
    equity_basis: float | None = None
    requested_risk_fraction: float | None = None
    permitted_risk_fraction: float | None = None
    monetary_risk_budget: float | None = None
    raw_volume: float | None = None
    normalized_volume: float | None = None
    estimated_normalized_loss: float | None = None
    aggregate_open_risk_before: float | None = None
    aggregate_open_risk_after: float | None = None
    circuit_status: CircuitStatus | None = None
    calculation_method: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", utc_datetime(self.timestamp, "risk decision time"))
        for name in (
            "equity_basis",
            "requested_risk_fraction",
            "permitted_risk_fraction",
            "monetary_risk_budget",
            "raw_volume",
            "normalized_volume",
            "estimated_normalized_loss",
            "aggregate_open_risk_before",
            "aggregate_open_risk_after",
        ):
            value = getattr(self, name)
            if value is not None:
                finite(value, name)
        if self.approved and self.reason is not RiskReason.APPROVED:
            raise RiskError("approved decisions require APPROVED reason")
