from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class StrategyError(ValueError):
    """Raised when strategy input cannot be interpreted safely."""


class StrategySide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    DATA_UNSAFE = "DATA_UNSAFE"


class DirectionState(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    DATA_UNSAFE = "DATA_UNSAFE"


class SafetyState(str, Enum):
    CLEAR = "CLEAR"
    BLOCKED = "BLOCKED"
    DATA_UNSAFE = "DATA_UNSAFE"


class BlockState(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    RETEST_ELIGIBLE = "RETEST_ELIGIBLE"
    MITIGATED = "MITIGATED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"
    PREMATURE = "PREMATURE"
    UNAVAILABLE = "UNAVAILABLE"
    DATA_UNSAFE = "DATA_UNSAFE"


class StrategyReason(str, Enum):
    APPROVED = "APPROVED"
    SYMBOL_NOT_EXECUTABLE = "SYMBOL_NOT_EXECUTABLE"
    DECISION_TIME_INVALID = "DECISION_TIME_INVALID"
    SOURCE_DATA_UNSAFE = "SOURCE_DATA_UNSAFE"
    SOURCE_CANDLE_IN_FUTURE = "SOURCE_CANDLE_IN_FUTURE"
    REGIME_DATA_UNSAFE = "REGIME_DATA_UNSAFE"
    REGIME_HIGH_VOLATILITY = "REGIME_HIGH_VOLATILITY"
    REGIME_DIRECTION_CONFLICT = "REGIME_DIRECTION_CONFLICT"
    BIAS_DATA_UNSAFE = "BIAS_DATA_UNSAFE"
    BIAS_NEUTRAL = "BIAS_NEUTRAL"
    BIAS_DIRECTION_CONFLICT = "BIAS_DIRECTION_CONFLICT"
    DXY_DATA_UNSAFE = "DXY_DATA_UNSAFE"
    DXY_DIRECTION_CONFLICT = "DXY_DIRECTION_CONFLICT"
    NEWS_BLOCKED = "NEWS_BLOCKED"
    NEWS_DATA_UNSAFE = "NEWS_DATA_UNSAFE"
    SESSION_CLOSED = "SESSION_CLOSED"
    SESSION_DATA_UNSAFE = "SESSION_DATA_UNSAFE"
    ORDER_BLOCK_UNAVAILABLE = "ORDER_BLOCK_UNAVAILABLE"
    ORDER_BLOCK_DIRECTION_CONFLICT = "ORDER_BLOCK_DIRECTION_CONFLICT"
    CONFLUENCE_BELOW_THRESHOLD = "CONFLUENCE_BELOW_THRESHOLD"
    SIDE_FLAT = "SIDE_FLAT"


def utc_datetime(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise StrategyError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def finite(value: float, name: str, *, positive: bool = False) -> float:
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        qualifier = "positive and finite" if positive else "finite"
        raise StrategyError(f"{name} must be {qualifier}")
    return number


@dataclass(frozen=True)
class SourceCandle:
    candle_id: str
    timeframe: str
    open_time: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        if not self.candle_id or not self.timeframe:
            raise StrategyError("source candle identity is required")
        opened = utc_datetime(self.open_time, "source open time")
        available = utc_datetime(self.available_at, "source availability")
        if available <= opened:
            raise StrategyError("source availability must follow its open time")
        object.__setattr__(self, "open_time", opened)
        object.__setattr__(self, "available_at", available)


@dataclass(frozen=True)
class RegimeResult:
    state: MarketRegime
    normalized_atr: float | None
    volatility_ratio: float | None
    trend_strength_atr: float | None
    reason: str


@dataclass(frozen=True)
class DirectionResult:
    state: DirectionState
    reason: str
    strength: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "strength", finite(self.strength, "direction strength"))


@dataclass(frozen=True)
class SafetyResult:
    state: SafetyState
    reason: str
    event_ids: tuple[str, ...] = ()
    provenance: str | None = None


@dataclass(frozen=True)
class SessionResult:
    state: SafetyState
    reason: str
    session_name: str
    priority: bool


@dataclass(frozen=True)
class OrderBlockResult:
    state: BlockState
    side: StrategySide
    block_id: str | None
    zone_low: float | None
    zone_high: float | None
    confirmed_at: datetime | None
    reason: str

    def __post_init__(self) -> None:
        if self.confirmed_at is not None:
            object.__setattr__(self, "confirmed_at", utc_datetime(self.confirmed_at, "block confirmation"))
        if self.zone_low is not None or self.zone_high is not None:
            low = finite(self.zone_low, "block zone low")
            high = finite(self.zone_high, "block zone high")
            if low > high:
                raise StrategyError("block zone low cannot exceed zone high")
            object.__setattr__(self, "zone_low", low)
            object.__setattr__(self, "zone_high", high)

    @property
    def eligible(self) -> bool:
        return self.state in (BlockState.ELIGIBLE, BlockState.RETEST_ELIGIBLE)


@dataclass(frozen=True)
class SetupEvidence:
    price_in_discount_or_premium: bool
    order_block_present: bool
    fvg_overlaps_order_block: bool
    liquidity_swept: bool


@dataclass(frozen=True)
class ConfluenceResult:
    score: int
    maximum: int
    threshold: int
    passed: bool
    components: tuple[tuple[str, int, bool], ...]


@dataclass(frozen=True)
class StrategyInput:
    symbol: str
    decision_at: datetime
    requested_side: StrategySide
    regime: RegimeResult
    bias: DirectionResult
    dxy: DirectionResult
    news: SafetyResult
    session: SessionResult
    order_block: OrderBlockResult
    evidence: SetupEvidence
    source_candles: tuple[SourceCandle, ...]
    invalidation: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.symbol:
            raise StrategyError("strategy symbol is required")
        object.__setattr__(self, "decision_at", utc_datetime(self.decision_at, "decision time"))
        object.__setattr__(self, "invalidation", MappingProxyType(dict(self.invalidation)))


@dataclass(frozen=True)
class StrategyDecision:
    symbol: str
    decision_at: datetime
    side: StrategySide
    entry_eligible: bool
    regime: MarketRegime
    bias: DirectionState
    dxy: DirectionState
    news: SafetyState
    session: SafetyState
    order_block: BlockState
    confluence: ConfluenceResult
    source_candles: tuple[SourceCandle, ...]
    reasons: tuple[StrategyReason, ...]
    configuration_fingerprint: str
    strategy_version: str
    invalidation: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_at", utc_datetime(self.decision_at, "decision time"))
        object.__setattr__(self, "invalidation", MappingProxyType(dict(self.invalidation)))

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, datetime):
                return value.astimezone(timezone.utc).isoformat()
            if isinstance(value, Mapping):
                return {str(key): convert(item) for key, item in sorted(value.items())}
            if isinstance(value, (tuple, list)):
                return [convert(item) for item in value]
            if is_dataclass(value):
                return {
                    item.name: convert(getattr(value, item.name))
                    for item in fields(value)
                }
            return value

        return convert(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
