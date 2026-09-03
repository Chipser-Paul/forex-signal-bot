from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class LifecycleError(ValueError):
    """Raised when lifecycle data or a state transition violates the contract."""


class Direction(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        return 1 if self is Direction.BUY else -1


class EntryMode(str, Enum):
    MARKET_ON_TRIGGER = "MARKET_ON_TRIGGER"
    PENDING_LIMIT = "PENDING_LIMIT"


class ReadinessStyle(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    PULLBACK = "PULLBACK"


class LifecycleStatus(str, Enum):
    CREATED = "CREATED"
    WAITING = "WAITING"
    ELIGIBLE = "ELIGIBLE"
    ENTRY_TRIGGERED = "ENTRY_TRIGGERED"
    OPEN = "OPEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class MarketEventKind(str, Enum):
    TICK = "TICK"
    BAR = "BAR"


class FillKind(str, Enum):
    LIVE_MARKET = "LIVE_MARKET"
    SIMULATED_OPEN = "SIMULATED_OPEN"
    SIMULATED_TRIGGER = "SIMULATED_TRIGGER"


class ActionType(str, Enum):
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    PARTIAL_SKIPPED = "PARTIAL_SKIPPED"
    MODIFY_STOP = "MODIFY_STOP"
    FINAL_CLOSE = "FINAL_CLOSE"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    BREAK_EVEN = "BREAK_EVEN"
    TRAILING_STOP = "TRAILING_STOP"
    TAKE_PROFIT = "TAKE_PROFIT"
    EMERGENCY = "EMERGENCY"
    END_OF_DATA = "END_OF_DATA"


class AmbiguityPolicy(str, Enum):
    STOP_FIRST = "STOP_FIRST"


TERMINAL_STATUSES = {
    LifecycleStatus.CLOSED,
    LifecycleStatus.CANCELLED,
    LifecycleStatus.EXPIRED,
    LifecycleStatus.REJECTED,
}

LEGAL_TRANSITIONS: dict[LifecycleStatus, set[LifecycleStatus]] = {
    LifecycleStatus.CREATED: {
        LifecycleStatus.WAITING,
        LifecycleStatus.ELIGIBLE,
        LifecycleStatus.CANCELLED,
        LifecycleStatus.EXPIRED,
        LifecycleStatus.REJECTED,
    },
    LifecycleStatus.WAITING: {
        LifecycleStatus.ELIGIBLE,
        LifecycleStatus.CANCELLED,
        LifecycleStatus.EXPIRED,
        LifecycleStatus.REJECTED,
    },
    LifecycleStatus.ELIGIBLE: {
        LifecycleStatus.WAITING,
        LifecycleStatus.ENTRY_TRIGGERED,
        LifecycleStatus.CANCELLED,
        LifecycleStatus.EXPIRED,
        LifecycleStatus.REJECTED,
    },
    LifecycleStatus.ENTRY_TRIGGERED: {
        LifecycleStatus.OPEN,
        LifecycleStatus.CANCELLED,
        LifecycleStatus.EXPIRED,
        LifecycleStatus.REJECTED,
    },
    LifecycleStatus.OPEN: {
        LifecycleStatus.PARTIALLY_CLOSED,
        LifecycleStatus.CLOSED,
    },
    LifecycleStatus.PARTIALLY_CLOSED: {LifecycleStatus.CLOSED},
    LifecycleStatus.CLOSED: set(),
    LifecycleStatus.CANCELLED: set(),
    LifecycleStatus.EXPIRED: set(),
    LifecycleStatus.REJECTED: set(),
}


def stable_id(*parts: object) -> str:
    material = "|".join(str(part) for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def as_utc(value: datetime, field_name: str) -> datetime:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise LifecycleError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def finite(value: float, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise LifecycleError(f"{field_name} must be finite")
    return number


def positive(value: float, field_name: str) -> float:
    number = finite(value, field_name)
    if number <= 0:
        raise LifecycleError(f"{field_name} must be positive")
    return number


@dataclass(frozen=True)
class LifecycleTransition:
    transition_id: str
    event_id: str
    timestamp: datetime
    from_status: LifecycleStatus
    to_status: LifecycleStatus
    reason: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", as_utc(self.timestamp, "transition timestamp"))


@dataclass(frozen=True)
class EntryIntent:
    signal_id: str
    symbol: str
    direction: Direction
    source_timeframe: str
    source_candle_open_time: datetime
    signal_available_at: datetime
    requested_trigger: float
    entry_mode: EntryMode
    readiness_style: ReadinessStyle
    stop_loss: float
    final_target: float
    initial_risk_distance: float
    partial_target: float
    partial_close_fraction: float
    source_event_id: str
    source_sequence: int = 0
    expires_at: datetime | None = None
    strategy_metadata: Mapping[str, Any] = field(default_factory=dict)
    configuration_id: str = "default"

    def __post_init__(self) -> None:
        if not self.signal_id or not self.symbol or not self.source_event_id:
            raise LifecycleError("signal, symbol and source event identities are required")
        open_time = as_utc(self.source_candle_open_time, "source candle open time")
        available = as_utc(self.signal_available_at, "signal availability")
        if available < open_time:
            raise LifecycleError("signal cannot be available before its source candle opens")
        object.__setattr__(self, "source_candle_open_time", open_time)
        object.__setattr__(self, "signal_available_at", available)
        if self.expires_at is not None:
            expiry = as_utc(self.expires_at, "signal expiry")
            if expiry <= available:
                raise LifecycleError("signal expiry must follow availability")
            object.__setattr__(self, "expires_at", expiry)

        trigger = finite(self.requested_trigger, "requested trigger")
        stop = finite(self.stop_loss, "stop loss")
        target = finite(self.final_target, "final target")
        risk = positive(self.initial_risk_distance, "initial risk distance")
        partial = finite(self.partial_target, "partial target")
        fraction = finite(self.partial_close_fraction, "partial close fraction")
        if not 0 < fraction < 1:
            raise LifecycleError("partial close fraction must be between zero and one")
        if self.direction is Direction.BUY and not (
            stop < trigger < partial <= target
        ):
            raise LifecycleError("buy intent levels are not directionally valid")
        if self.direction is Direction.SELL and not (
            target <= partial < trigger < stop
        ):
            raise LifecycleError("sell intent levels are not directionally valid")
        if not math.isclose(abs(trigger - stop), risk, rel_tol=1e-9, abs_tol=1e-12):
            raise LifecycleError("initial risk distance must match requested trigger and stop")


@dataclass(frozen=True)
class MarketEvent:
    event_id: str
    timestamp: datetime
    symbol: str
    source: str
    kind: MarketEventKind
    sequence: int
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    bid: float | None = None
    ask: float | None = None
    bar_open_time: datetime | None = None
    source_candle_id: str | None = None
    atr: float | None = None
    emergency_reason: str | None = None
    structure_trail_level: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id or not self.symbol or not self.source:
            raise LifecycleError("event identity, symbol and source are required")
        object.__setattr__(self, "timestamp", as_utc(self.timestamp, "event timestamp"))
        if self.bar_open_time is not None:
            object.__setattr__(
                self,
                "bar_open_time",
                as_utc(self.bar_open_time, "bar open time"),
            )
        for field_name in (
            "open",
            "high",
            "low",
            "close",
            "bid",
            "ask",
            "atr",
            "structure_trail_level",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, finite(value, field_name))
        if self.kind is MarketEventKind.BAR:
            if any(value is None for value in (self.open, self.high, self.low, self.close)):
                raise LifecycleError("bar event requires open, high, low and close")
            if self.high < max(self.open, self.close, self.low):
                raise LifecycleError("bar high is inconsistent with OHLC")
            if self.low > min(self.open, self.close, self.high):
                raise LifecycleError("bar low is inconsistent with OHLC")
        elif self.bid is None and self.ask is None and self.close is None:
            raise LifecycleError("tick event requires bid, ask or neutral price")
        if self.atr is not None and self.atr < 0:
            raise LifecycleError("ATR cannot be negative")

    def price_for(self, direction: Direction) -> float:
        value = self.ask if direction is Direction.BUY else self.bid
        if value is None:
            value = self.close
        if value is None:
            raise LifecycleError("market event has no usable execution price")
        return finite(value, "execution price")


@dataclass(frozen=True)
class EntryState:
    intent: EntryIntent
    status: LifecycleStatus
    processed_event_ids: tuple[str, ...] = ()
    last_event_time: datetime | None = None
    transitions: tuple[LifecycleTransition, ...] = ()


@dataclass(frozen=True)
class EntryDecision:
    state: EntryState
    triggered: bool
    proposed_fill_price: float | None = None
    fill_kind: FillKind | None = None
    reason: str = ""


@dataclass(frozen=True)
class PnlComponent:
    action_id: str
    timestamp: datetime
    quantity: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    reason: ExitReason | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", as_utc(self.timestamp, "P&L timestamp"))


@dataclass(frozen=True)
class PositionState:
    trade_id: str
    signal_id: str
    symbol: str
    direction: Direction
    status: LifecycleStatus
    requested_entry: float
    fill_price: float
    fill_timestamp: datetime
    fill_kind: FillKind
    initial_quantity: float
    remaining_quantity: float
    closed_quantity: float
    initial_stop: float
    current_stop: float
    final_target: float
    initial_risk_price: float
    initial_risk_account_currency: float | None
    partial_target: float
    partial_close_fraction: float
    partial_close_attempted: bool = False
    partial_close_occurred: bool = False
    partial_close_skip_reason: str | None = None
    realized_gross_pnl: float = 0.0
    current_r_multiple: float = 0.0
    highest_favorable_price: float | None = None
    lowest_favorable_price: float | None = None
    processed_event_ids: tuple[str, ...] = ()
    processed_action_ids: tuple[str, ...] = ()
    pnl_components: tuple[PnlComponent, ...] = ()
    transitions: tuple[LifecycleTransition, ...] = ()
    last_processed_event_id: str | None = None
    last_event_time: datetime | None = None
    exit_time: datetime | None = None
    exit_price: float | None = None
    exit_reason: ExitReason | str | None = None
    ambiguity_policy_used: bool = False
    adapter_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fill_timestamp", as_utc(self.fill_timestamp, "fill timestamp"))
        if self.last_event_time is not None:
            object.__setattr__(self, "last_event_time", as_utc(self.last_event_time, "last event time"))
        if self.exit_time is not None:
            object.__setattr__(self, "exit_time", as_utc(self.exit_time, "exit time"))
        validate_position(self)


@dataclass(frozen=True)
class LifecycleAction:
    action_id: str
    event_id: str
    timestamp: datetime
    symbol: str
    trade_id: str
    action_type: ActionType
    quantity: float = 0.0
    requested_price: float | None = None
    new_stop: float | None = None
    reason: ExitReason | str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", as_utc(self.timestamp, "action timestamp"))


@dataclass(frozen=True)
class ActionConfirmation:
    """Broker-confirmed execution details for one planned lifecycle action."""

    action_id: str
    executed_quantity: float | None = None
    executed_price: float | None = None

    def __post_init__(self) -> None:
        if not self.action_id:
            raise LifecycleError("confirmed action identity is required")
        if self.executed_quantity is not None:
            object.__setattr__(
                self,
                "executed_quantity",
                positive(self.executed_quantity, "confirmed action quantity"),
            )
        if self.executed_price is not None:
            object.__setattr__(
                self,
                "executed_price",
                positive(self.executed_price, "confirmed action price"),
            )


@dataclass(frozen=True)
class ManagementConfig:
    partial_close_fraction: float = 0.5
    partial_target_r: float = 1.0
    volume_min: float = 0.01
    volume_step: float = 0.01
    pnl_per_price_unit: float = 1.0
    trailing_enabled: bool = True
    trailing_atr_multiple: float = 3.0
    trailing_min_distance: float = 0.0
    ambiguity_policy: AmbiguityPolicy = AmbiguityPolicy.STOP_FIRST
    numeric_tolerance: float = 1e-9

    def __post_init__(self) -> None:
        if not 0 < self.partial_close_fraction < 1:
            raise LifecycleError("partial close fraction must be between zero and one")
        positive(self.partial_target_r, "partial target R")
        positive(self.volume_min, "minimum volume")
        positive(self.volume_step, "volume step")
        positive(self.pnl_per_price_unit, "P&L multiplier")
        positive(self.trailing_atr_multiple, "trailing ATR multiple")
        if self.trailing_min_distance < 0:
            raise LifecycleError("minimum trailing distance cannot be negative")


@dataclass(frozen=True)
class ManagementResult:
    position: PositionState
    actions: tuple[LifecycleAction, ...]
    duplicate_event: bool = False


@dataclass(frozen=True)
class TradeOutcome:
    trade_id: str
    signal_id: str
    symbol: str
    direction: Direction
    exit_time: datetime
    exit_price: float
    exit_reason: ExitReason | str
    initial_quantity: float
    realized_gross_pnl: float
    gross_r_multiple: float
    components: tuple[PnlComponent, ...]
    adapter_source: str
    ambiguity_policy_used: bool


def make_transition(
    *,
    event_id: str,
    timestamp: datetime,
    from_status: LifecycleStatus,
    to_status: LifecycleStatus,
    reason: str,
    metadata: Mapping[str, Any] | None = None,
) -> LifecycleTransition:
    if to_status not in LEGAL_TRANSITIONS[from_status]:
        raise LifecycleError(f"illegal lifecycle transition: {from_status.value} -> {to_status.value}")
    return LifecycleTransition(
        transition_id=stable_id(event_id, from_status.value, to_status.value, reason),
        event_id=event_id,
        timestamp=timestamp,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        metadata=dict(metadata or {}),
    )


def transition_entry(
    state: EntryState,
    to_status: LifecycleStatus,
    event: MarketEvent,
    reason: str,
    metadata: Mapping[str, Any] | None = None,
) -> EntryState:
    transition = make_transition(
        event_id=event.event_id,
        timestamp=event.timestamp,
        from_status=state.status,
        to_status=to_status,
        reason=reason,
        metadata=metadata,
    )
    return replace(state, status=to_status, transitions=state.transitions + (transition,))


def validate_position(position: PositionState, tolerance: float = 1e-8) -> None:
    for field_name in (
        "requested_entry",
        "fill_price",
        "initial_quantity",
        "remaining_quantity",
        "closed_quantity",
        "initial_stop",
        "current_stop",
        "final_target",
        "initial_risk_price",
        "partial_target",
        "realized_gross_pnl",
        "current_r_multiple",
    ):
        finite(getattr(position, field_name), field_name)
    positive(position.initial_quantity, "initial quantity")
    positive(position.initial_risk_price, "initial risk")
    if position.remaining_quantity < -tolerance or position.closed_quantity < -tolerance:
        raise LifecycleError("position quantities cannot be negative")
    if position.closed_quantity > position.initial_quantity + tolerance:
        raise LifecycleError("closed quantity exceeds initial quantity")
    if not math.isclose(
        position.closed_quantity + position.remaining_quantity,
        position.initial_quantity,
        abs_tol=tolerance,
    ):
        raise LifecycleError("closed and remaining quantities do not reconcile")
    if position.status is LifecycleStatus.CLOSED:
        if abs(position.remaining_quantity) > tolerance:
            raise LifecycleError("closed position must have zero remaining quantity")
        if position.exit_time is None or position.exit_price is None or position.exit_reason is None:
            raise LifecycleError("closed position requires normalized exit fields")
    elif position.status in (LifecycleStatus.OPEN, LifecycleStatus.PARTIALLY_CLOSED):
        if position.remaining_quantity <= tolerance:
            raise LifecycleError("open position requires positive remaining quantity")
        if position.direction is Direction.BUY:
            if position.current_stop > position.final_target:
                raise LifecycleError("buy stop cannot exceed final target")
        elif position.current_stop < position.final_target:
            raise LifecycleError("sell stop cannot be below final target")
