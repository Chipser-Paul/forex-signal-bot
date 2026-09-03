from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


SCHEMA_VERSION = 1


class ExecutionError(ValueError):
    """Raised when execution input cannot be handled without broker risk."""


class ExecutionAction(str, Enum):
    ENTRY = "ENTRY"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    FULL_CLOSE = "FULL_CLOSE"
    MODIFY_STOP = "MODIFY_STOP"
    LIQUIDATE = "LIQUIDATE"


class ExecutionStatus(str, Enum):
    PREPARED = "PREPARED"
    CHECKED = "CHECKED"
    SUBMITTING = "SUBMITTING"
    CONFIRMED = "CONFIRMED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ResultClass(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    RETRYABLE_REJECTION = "RETRYABLE_REJECTION"
    PERMANENT_REJECTION = "PERMANENT_REJECTION"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_STOPS = "INVALID_STOPS"
    TRADING_UNAVAILABLE = "TRADING_UNAVAILABLE"
    PRICE_CHANGED = "PRICE_CHANGED"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    CONNECTION_FAILURE = "CONNECTION_FAILURE"
    UNCERTAIN = "UNCERTAIN"


class ExecutionReason(str, Enum):
    APPROVED = "APPROVED"
    CONFIRMED = "CONFIRMED"
    PARTIAL_FILL = "PARTIAL_FILL"
    CONFIGURATION_MISSING = "CONFIGURATION_MISSING"
    INVALID_MAGIC = "INVALID_MAGIC"
    CONNECTION_UNAVAILABLE = "CONNECTION_UNAVAILABLE"
    TRADING_DISABLED = "TRADING_DISABLED"
    SYMBOL_MISSING = "SYMBOL_MISSING"
    SYMBOL_SELECTION_FAILED = "SYMBOL_SELECTION_FAILED"
    SYMBOL_NOT_VISIBLE = "SYMBOL_NOT_VISIBLE"
    SYMBOL_TRADE_MODE_REJECTED = "SYMBOL_TRADE_MODE_REJECTED"
    SYMBOL_METADATA_INVALID = "SYMBOL_METADATA_INVALID"
    TICK_MISSING = "TICK_MISSING"
    TICK_STALE = "TICK_STALE"
    TICK_FUTURE = "TICK_FUTURE"
    TICK_INVALID = "TICK_INVALID"
    SPREAD_CONFIGURATION_MISSING = "SPREAD_CONFIGURATION_MISSING"
    SPREAD_ABSOLUTE_LIMIT = "SPREAD_ABSOLUTE_LIMIT"
    SPREAD_RELATIVE_LIMIT = "SPREAD_RELATIVE_LIMIT"
    SPREAD_CHANGED_AFTER_CHECK = "SPREAD_CHANGED_AFTER_CHECK"
    STOP_INVALID = "STOP_INVALID"
    TARGET_INVALID = "TARGET_INVALID"
    STOP_DISTANCE_VIOLATION = "STOP_DISTANCE_VIOLATION"
    FREEZE_LEVEL_VIOLATION = "FREEZE_LEVEL_VIOLATION"
    STOP_WIDENING_REQUIRES_RISK = "STOP_WIDENING_REQUIRES_RISK"
    RISK_APPROVAL_INVALID = "RISK_APPROVAL_INVALID"
    VOLUME_INVALID = "VOLUME_INVALID"
    MARGIN_CALCULATION_FAILED = "MARGIN_CALCULATION_FAILED"
    FREE_MARGIN_INSUFFICIENT = "FREE_MARGIN_INSUFFICIENT"
    MARGIN_LEVEL_TOO_LOW = "MARGIN_LEVEL_TOO_LOW"
    NEW_ORDER_MARGIN_LIMIT = "NEW_ORDER_MARGIN_LIMIT"
    FILLING_MODE_UNSUPPORTED = "FILLING_MODE_UNSUPPORTED"
    PREFLIGHT_MISSING = "PREFLIGHT_MISSING"
    PREFLIGHT_REJECTED = "PREFLIGHT_REJECTED"
    PREFLIGHT_VOLUME_INCREASE = "PREFLIGHT_VOLUME_INCREASE"
    DUPLICATE_ACTION = "DUPLICATE_ACTION"
    ACTION_UNCERTAIN = "ACTION_UNCERTAIN"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    BROKER_REJECTED = "BROKER_REJECTED"
    BROKER_INVALID_REQUEST = "BROKER_INVALID_REQUEST"
    BROKER_INVALID_STOPS = "BROKER_INVALID_STOPS"
    BROKER_TRADING_UNAVAILABLE = "BROKER_TRADING_UNAVAILABLE"
    BROKER_PRICE_CHANGED = "BROKER_PRICE_CHANGED"
    BROKER_INSUFFICIENT_MARGIN = "BROKER_INSUFFICIENT_MARGIN"
    BROKER_CONNECTION_FAILURE = "BROKER_CONNECTION_FAILURE"
    BROKER_OUTCOME_UNCERTAIN = "BROKER_OUTCOME_UNCERTAIN"
    OWNERSHIP_UNPROVEN = "OWNERSHIP_UNPROVEN"
    POSITION_NOT_FOUND = "POSITION_NOT_FOUND"
    POSITION_IDENTITY_MISMATCH = "POSITION_IDENTITY_MISMATCH"
    CLOSE_VOLUME_EXCEEDS_POSITION = "CLOSE_VOLUME_EXCEEDS_POSITION"
    STOP_NOT_IMPROVED = "STOP_NOT_IMPROVED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    RECONCILED_CONFIRMED = "RECONCILED_CONFIRMED"
    RECONCILED_ABSENT = "RECONCILED_ABSENT"
    RECOVERED_POSITION = "RECOVERED_POSITION"


class ExecutionRejected(ExecutionError):
    def __init__(self, reason: ExecutionReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class FillingMode(str, Enum):
    FOK = "FOK"
    IOC = "IOC"
    RETURN = "RETURN"


class ReconciliationState(str, Enum):
    MATCHED = "MATCHED"
    RECOVERED = "RECOVERED"
    CLOSED_CONFIRMED = "CLOSED_CONFIRMED"
    FOREIGN_IGNORED = "FOREIGN_IGNORED"
    ABSENT_CONFIRMED = "ABSENT_CONFIRMED"
    REQUIRED = "REQUIRED"


def stable_execution_id(*parts: object) -> str:
    material = "|".join(str(part) for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ExecutionError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def finite(value: float, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ExecutionError(f"{field_name} must be finite")
    return number


def positive(value: float, field_name: str, *, allow_zero: bool = False) -> float:
    number = finite(value, field_name)
    if number < 0 or (number == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ExecutionError(f"{field_name} must be {qualifier}")
    return number


def sanitized_comment(trade_id: str, action_id: str, *, prefix: str = "p5") -> str:
    clean_prefix = re.sub(r"[^A-Za-z0-9_-]", "", prefix)[:4] or "p5"
    clean_trade = re.sub(r"[^A-Za-z0-9]", "", trade_id)[:8]
    clean_action = re.sub(r"[^A-Za-z0-9]", "", action_id)[:8]
    if not clean_trade or not clean_action:
        raise ExecutionError("trade and action identifiers must produce a safe comment")
    return f"{clean_prefix}:{clean_trade}:{clean_action}"[:31]


@dataclass(frozen=True)
class ExecutionPolicy:
    policy_version: str = "phase5-broker-safety-v1"
    maximum_tick_age_seconds: float = 10.0
    future_tick_tolerance_seconds: float = 1.0
    maximum_spread_to_stop_fraction: float = 0.10
    minimum_projected_margin_level_percent: float = 500.0
    maximum_new_order_margin_fraction: float = 0.10
    maximum_automatic_retries: int = 1
    magic_number: int = 0
    maximum_spread_points: Mapping[str, float] = field(default_factory=dict)
    maximum_deviation_points: Mapping[str, int] = field(default_factory=dict)
    filling_preference: tuple[FillingMode, ...] = (
        FillingMode.FOK,
        FillingMode.IOC,
        FillingMode.RETURN,
    )
    uncertain_requires_reconciliation: bool = True
    retry_unfilled_partial: bool = False
    ownership_requires_identity: bool = True

    def __post_init__(self) -> None:
        positive(self.maximum_tick_age_seconds, "maximum tick age")
        positive(self.future_tick_tolerance_seconds, "future tick tolerance", allow_zero=True)
        ratio = finite(self.maximum_spread_to_stop_fraction, "spread-to-stop fraction")
        if not 0 < ratio <= 1:
            raise ExecutionError("spread-to-stop fraction must be in (0, 1]")
        positive(self.minimum_projected_margin_level_percent, "minimum margin level")
        margin_fraction = finite(self.maximum_new_order_margin_fraction, "margin fraction")
        if not 0 < margin_fraction <= 1:
            raise ExecutionError("new-order margin fraction must be in (0, 1]")
        if self.maximum_automatic_retries != 1:
            raise ExecutionError("Phase 5 permits exactly one automatic retry")
        if not isinstance(self.magic_number, int) or self.magic_number <= 0:
            raise ExecutionError("a stable non-zero magic number is required")
        if not self.filling_preference or len(set(self.filling_preference)) != len(self.filling_preference):
            raise ExecutionError("filling preference must be non-empty and unique")
        for symbol, limit in self.maximum_spread_points.items():
            if not symbol or positive(limit, "maximum spread points") <= 0:
                raise ExecutionError("spread limits require valid symbols and positive values")
        for symbol, deviation in self.maximum_deviation_points.items():
            if not symbol or not isinstance(deviation, int) or deviation <= 0:
                raise ExecutionError("deviation limits require valid symbols and positive integers")
        if not self.uncertain_requires_reconciliation or self.retry_unfilled_partial:
            raise ExecutionError("Phase 5 uncertainty and partial-fill policies are conservative")

    def spread_limit(self, symbol: str) -> float:
        try:
            return positive(self.maximum_spread_points[symbol], "maximum spread points")
        except KeyError as exc:
            raise ExecutionError(f"maximum spread is not configured for {symbol}") from exc

    def deviation_limit(self, symbol: str) -> int:
        try:
            value = self.maximum_deviation_points[symbol]
        except KeyError as exc:
            raise ExecutionError(f"maximum deviation is not configured for {symbol}") from exc
        if not isinstance(value, int) or value <= 0:
            raise ExecutionError(f"maximum deviation is invalid for {symbol}")
        return value


@dataclass(frozen=True)
class BrokerTick:
    timestamp: datetime
    bid: float
    ask: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", utc_datetime(self.timestamp, "tick timestamp"))
        object.__setattr__(self, "bid", positive(self.bid, "bid"))
        object.__setattr__(self, "ask", positive(self.ask, "ask"))
        if self.ask < self.bid:
            raise ExecutionError("ask cannot be below bid")


@dataclass(frozen=True)
class BrokerSymbol:
    symbol: str
    visible: bool
    trade_mode: int
    execution_mode: int
    filling_flags: int
    point: float
    digits: int
    stops_level_points: int
    freeze_level_points: int
    volume_min: float
    volume_max: float
    volume_step: float

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ExecutionError("symbol identity is required")
        object.__setattr__(self, "point", positive(self.point, "symbol point"))
        if not isinstance(self.digits, int) or self.digits < 0:
            raise ExecutionError("symbol digits must be a non-negative integer")
        if self.stops_level_points < 0 or self.freeze_level_points < 0:
            raise ExecutionError("stop and freeze levels cannot be negative")
        for name in ("volume_min", "volume_max", "volume_step"):
            object.__setattr__(self, name, positive(getattr(self, name), name))
        if self.volume_max < self.volume_min:
            raise ExecutionError("maximum volume cannot be below minimum volume")


@dataclass(frozen=True)
class BrokerSnapshot:
    timestamp: datetime
    connected: bool
    trading_available: bool
    equity: float
    margin: float
    free_margin: float
    symbol: BrokerSymbol
    tick: BrokerTick
    orders: tuple[Any, ...] = ()
    positions: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", utc_datetime(self.timestamp, "snapshot timestamp"))
        object.__setattr__(self, "equity", positive(self.equity, "equity"))
        object.__setattr__(self, "margin", positive(self.margin, "margin", allow_zero=True))
        object.__setattr__(self, "free_margin", finite(self.free_margin, "free margin"))


@dataclass(frozen=True)
class ExecutionRequest:
    action_id: str
    signal_id: str
    trade_id: str
    symbol: str
    direction: str
    action_type: ExecutionAction
    volume: float
    requested_trigger: float
    executable_price: float
    stop_price: float | None
    target_price: float | None
    deviation_points: int
    filling_mode: FillingMode | None
    magic_number: int
    comment: str
    risk_decision_id: str
    approved_volume: float
    approved_stop: float | None
    created_at: datetime
    expires_at: datetime | None = None
    position_ticket: int | None = None
    risk_reapproved: bool = False

    def __post_init__(self) -> None:
        required = (self.action_id, self.signal_id, self.trade_id, self.symbol, self.risk_decision_id)
        if any(not value for value in required):
            raise ExecutionError("execution identities are required")
        if self.direction not in ("buy", "sell"):
            raise ExecutionError("direction must be buy or sell")
        object.__setattr__(self, "volume", positive(self.volume, "volume"))
        object.__setattr__(self, "approved_volume", positive(self.approved_volume, "approved volume"))
        if self.volume > self.approved_volume + 1e-12:
            raise ExecutionError("execution volume cannot exceed Phase 4 approval")
        for name in ("requested_trigger", "executable_price"):
            object.__setattr__(self, name, positive(getattr(self, name), name.replace("_", " ")))
        if self.stop_price is not None:
            object.__setattr__(self, "stop_price", positive(self.stop_price, "stop price"))
        if self.target_price is not None:
            object.__setattr__(self, "target_price", positive(self.target_price, "target price"))
        if self.approved_stop is not None:
            object.__setattr__(self, "approved_stop", positive(self.approved_stop, "approved stop"))
        if not isinstance(self.deviation_points, int) or self.deviation_points <= 0:
            raise ExecutionError("deviation must be a positive integer")
        if self.magic_number <= 0:
            raise ExecutionError("execution request requires a non-zero magic number")
        if len(self.comment) > 31 or not self.comment:
            raise ExecutionError("execution comment must be non-empty and at most 31 characters")
        object.__setattr__(self, "created_at", utc_datetime(self.created_at, "creation timestamp"))
        if self.expires_at is not None:
            expiry = utc_datetime(self.expires_at, "expiry timestamp")
            if expiry <= self.created_at:
                raise ExecutionError("execution expiry must follow creation")
            object.__setattr__(self, "expires_at", expiry)
        if self.action_type is not ExecutionAction.ENTRY and self.position_ticket is None:
            raise ExecutionError("position mutation requires a broker position ticket")


@dataclass(frozen=True)
class ExecutionResult:
    action_id: str
    attempt_id: str
    status: ExecutionStatus
    reason: ExecutionReason
    result_class: ResultClass
    timestamp: datetime
    broker_retcode: int | None = None
    order_ticket: int | None = None
    deal_ticket: int | None = None
    position_ticket: int | None = None
    requested_volume: float = 0.0
    executed_volume: float = 0.0
    requested_price: float | None = None
    executed_price: float | None = None
    remaining_unfilled_volume: float = 0.0
    retry_eligible: bool = False
    reconciliation_required: bool = False
    filling_mode: FillingMode | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action_id or not self.attempt_id:
            raise ExecutionError("result identities are required")
        object.__setattr__(self, "timestamp", utc_datetime(self.timestamp, "result timestamp"))
        for name in ("requested_volume", "executed_volume", "remaining_unfilled_volume"):
            object.__setattr__(self, name, positive(getattr(self, name), name, allow_zero=True))
        if self.executed_volume > self.requested_volume + 1e-12:
            raise ExecutionError("executed volume cannot exceed requested volume")
        expected_remaining = max(0.0, self.requested_volume - self.executed_volume)
        if not math.isclose(self.remaining_unfilled_volume, expected_remaining, abs_tol=1e-9):
            raise ExecutionError("unfilled volume must reconcile with requested and executed volume")
        if self.requested_price is not None:
            object.__setattr__(self, "requested_price", positive(self.requested_price, "requested price"))
        if self.executed_price is not None:
            object.__setattr__(self, "executed_price", positive(self.executed_price, "executed price"))


@dataclass(frozen=True)
class RegistryRecord:
    action_id: str
    trade_id: str
    symbol: str
    action_type: ExecutionAction
    state: ExecutionStatus
    created_at: datetime
    updated_at: datetime
    attempt_count: int = 0
    broker_retcode: int | None = None
    order_ticket: int | None = None
    deal_ticket: int | None = None
    position_ticket: int | None = None
    executed_volume: float = 0.0
    executed_price: float | None = None
    last_attempt_id: str | None = None
    reason: ExecutionReason = ExecutionReason.APPROVED

    def __post_init__(self) -> None:
        if not self.action_id or not self.trade_id or not self.symbol:
            raise ExecutionError("registry identities are required")
        object.__setattr__(self, "created_at", utc_datetime(self.created_at, "registry creation"))
        object.__setattr__(self, "updated_at", utc_datetime(self.updated_at, "registry update"))
        if self.updated_at < self.created_at or self.attempt_count < 0:
            raise ExecutionError("registry chronology or attempt count is invalid")
        object.__setattr__(self, "executed_volume", positive(self.executed_volume, "executed volume", allow_zero=True))
        if self.executed_price is not None:
            object.__setattr__(self, "executed_price", positive(self.executed_price, "executed price"))


@dataclass(frozen=True)
class ReconciliationResult:
    reconciliation_id: str
    state: ReconciliationState
    reason: ExecutionReason
    timestamp: datetime
    trade_id: str | None = None
    action_id: str | None = None
    position_ticket: int | None = None
    block_new_entries: bool = False
    recovered: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reconciliation_id:
            raise ExecutionError("reconciliation identity is required")
        object.__setattr__(self, "timestamp", utc_datetime(self.timestamp, "reconciliation timestamp"))
