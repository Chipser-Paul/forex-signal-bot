from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


EXECUTABLE_SYMBOL = "XAUUSDm"
EXECUTION_MODEL_VERSION = "phase7-execution-v1"


class HistoricalExecutionError(ValueError):
    """Raised when historical input cannot be used without inventing facts."""


class FidelityClass(str, Enum):
    TICK_BID_ASK = "TICK_BID_ASK"
    BAR_BID_ASK = "BAR_BID_ASK"
    MID_BAR_WITH_OBSERVED_COSTS = "MID_BAR_WITH_OBSERVED_COSTS"
    MID_BAR_WITH_ASSUMED_COSTS = "MID_BAR_WITH_ASSUMED_COSTS"
    INSUFFICIENT_FOR_VALIDATION = "INSUFFICIENT_FOR_VALIDATION"


class RunMode(str, Enum):
    VALIDATION = "VALIDATION"
    DIAGNOSTIC = "DIAGNOSTIC"


class CostSource(str, Enum):
    OBSERVED = "OBSERVED"
    ASSUMED = "ASSUMED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1


class CommissionKind(str, Enum):
    PER_LOT_PER_SIDE = "PER_LOT_PER_SIDE"
    PER_LOT_ROUND_TURN = "PER_LOT_ROUND_TURN"
    FIXED_PER_ORDER = "FIXED_PER_ORDER"
    PERCENT_NOTIONAL = "PERCENT_NOTIONAL"


class SwapCalculation(str, Enum):
    ACCOUNT_CURRENCY_PER_LOT = "ACCOUNT_CURRENCY_PER_LOT"
    POINTS_PER_LOT = "POINTS_PER_LOT"


class SlippageKind(str, Enum):
    NONE = "NONE"
    FIXED_ADVERSE_POINTS = "FIXED_ADVERSE_POINTS"
    UNIFORM_ADVERSE_POINTS = "UNIFORM_ADVERSE_POINTS"


class LedgerEventType(str, Enum):
    ENTRY_FILL = "ENTRY_FILL"
    EXIT_PNL = "EXIT_PNL"
    COMMISSION = "COMMISSION"
    SWAP = "SWAP"
    EQUITY_MARK = "EQUITY_MARK"


def utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise HistoricalExecutionError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def finite(value: float, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise HistoricalExecutionError(f"{field_name} must be finite")
    return number


def positive(value: float, field_name: str, *, allow_zero: bool = False) -> float:
    number = finite(value, field_name)
    if number < 0 or (not allow_zero and number == 0):
        qualifier = "non-negative" if allow_zero else "positive"
        raise HistoricalExecutionError(f"{field_name} must be {qualifier}")
    return number


def stable_id(*parts: object) -> str:
    material = "|".join(str(part) for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class HistoricalQuote:
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    source: str
    dataset_id: str
    sequence_id: str
    bid_volume: float | None = None
    ask_volume: float | None = None
    market_open: bool = True
    flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.symbol != EXECUTABLE_SYMBOL:
            raise HistoricalExecutionError("historical execution is restricted to XAUUSDm")
        if not self.source or not self.dataset_id or not self.sequence_id:
            raise HistoricalExecutionError("quote provenance and sequence identity are required")
        object.__setattr__(self, "timestamp", utc_datetime(self.timestamp, "quote timestamp"))
        object.__setattr__(self, "bid", positive(self.bid, "bid"))
        object.__setattr__(self, "ask", positive(self.ask, "ask"))
        if self.ask < self.bid:
            raise HistoricalExecutionError("crossed historical quote")
        for field_name in ("bid_volume", "ask_volume"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, positive(value, field_name, allow_zero=True))

    @property
    def spread_price(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class SpreadObservation:
    symbol: str
    timestamp: datetime
    spread_price: float
    source: str
    dataset_id: str
    sequence_id: str

    def __post_init__(self) -> None:
        if self.symbol != EXECUTABLE_SYMBOL:
            raise HistoricalExecutionError("spread observations are restricted to XAUUSDm")
        if not self.source or not self.dataset_id or not self.sequence_id:
            raise HistoricalExecutionError("spread provenance and sequence identity are required")
        object.__setattr__(self, "timestamp", utc_datetime(self.timestamp, "spread timestamp"))
        object.__setattr__(self, "spread_price", positive(self.spread_price, "spread price", allow_zero=True))


@dataclass(frozen=True)
class MidBar:
    symbol: str
    open_time: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    source: str
    dataset_id: str
    sequence_id: str
    feed_side: str = "MID"

    def __post_init__(self) -> None:
        if self.symbol != EXECUTABLE_SYMBOL:
            raise HistoricalExecutionError("historical execution is restricted to XAUUSDm")
        if self.feed_side not in {"MID", "BID"}:
            raise HistoricalExecutionError("mid-bar feed side must be MID or BID")
        object.__setattr__(self, "open_time", utc_datetime(self.open_time, "mid-bar open time"))
        object.__setattr__(self, "available_at", utc_datetime(self.available_at, "mid-bar availability"))
        if self.available_at <= self.open_time:
            raise HistoricalExecutionError("mid-bar availability must follow open time")
        for field_name in ("open", "high", "low", "close"):
            object.__setattr__(self, field_name, positive(getattr(self, field_name), field_name))
        if self.high < max(self.open, self.low, self.close) or self.low > min(self.open, self.high, self.close):
            raise HistoricalExecutionError("mid-bar OHLC is inconsistent")
        if not self.source or not self.dataset_id or not self.sequence_id:
            raise HistoricalExecutionError("mid-bar provenance and identity are required")


@dataclass(frozen=True)
class BidAskBar:
    symbol: str
    open_time: datetime
    available_at: datetime
    bid_open: float
    bid_high: float
    bid_low: float
    bid_close: float
    ask_open: float
    ask_high: float
    ask_low: float
    ask_close: float
    source: str
    dataset_id: str
    sequence_id: str

    def __post_init__(self) -> None:
        if self.symbol != EXECUTABLE_SYMBOL:
            raise HistoricalExecutionError("historical execution is restricted to XAUUSDm")
        if not self.source or not self.dataset_id or not self.sequence_id:
            raise HistoricalExecutionError("bar provenance and sequence identity are required")
        open_time = utc_datetime(self.open_time, "bar open time")
        available_at = utc_datetime(self.available_at, "bar availability")
        if available_at <= open_time:
            raise HistoricalExecutionError("bar availability must follow its opening time")
        object.__setattr__(self, "open_time", open_time)
        object.__setattr__(self, "available_at", available_at)
        for field_name in (
            "bid_open", "bid_high", "bid_low", "bid_close",
            "ask_open", "ask_high", "ask_low", "ask_close",
        ):
            object.__setattr__(self, field_name, positive(getattr(self, field_name), field_name))
        if self.bid_high < max(self.bid_open, self.bid_low, self.bid_close):
            raise HistoricalExecutionError("bid OHLC is inconsistent")
        if self.bid_low > min(self.bid_open, self.bid_high, self.bid_close):
            raise HistoricalExecutionError("bid OHLC is inconsistent")
        if self.ask_high < max(self.ask_open, self.ask_low, self.ask_close):
            raise HistoricalExecutionError("ask OHLC is inconsistent")
        if self.ask_low > min(self.ask_open, self.ask_high, self.ask_close):
            raise HistoricalExecutionError("ask OHLC is inconsistent")
        if min(self.ask_open - self.bid_open, self.ask_high - self.bid_high,
               self.ask_low - self.bid_low, self.ask_close - self.bid_close) < 0:
            raise HistoricalExecutionError("bid/ask bar contains crossed quote sides")


@dataclass(frozen=True)
class DatasetDiagnostics:
    record_count: int
    duplicate_count: int = 0
    expected_interval_seconds: float | None = None
    unexplained_gaps: tuple[tuple[str, str], ...] = ()
    market_closure_gaps: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CommissionSchedule:
    kind: CommissionKind
    amount: float
    currency: str
    source: CostSource

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", positive(self.amount, "commission amount", allow_zero=True))
        if not self.currency:
            raise HistoricalExecutionError("commission currency is required")
        if self.kind is CommissionKind.PERCENT_NOTIONAL and self.amount >= 1:
            raise HistoricalExecutionError("notional commission must be a fraction below one")


@dataclass(frozen=True)
class SwapSchedule:
    calculation: SwapCalculation
    long_rate: float
    short_rate: float
    rollover_time: time
    rollover_timezone: str
    triple_swap_weekday: int
    source: CostSource

    def __post_init__(self) -> None:
        object.__setattr__(self, "long_rate", finite(self.long_rate, "long swap rate"))
        object.__setattr__(self, "short_rate", finite(self.short_rate, "short swap rate"))
        if self.rollover_time.tzinfo is not None:
            raise HistoricalExecutionError("rollover time must be local and timezone-free")
        if self.triple_swap_weekday not in range(7):
            raise HistoricalExecutionError("triple-swap weekday must be in 0..6")
        try:
            ZoneInfo(self.rollover_timezone)
        except ZoneInfoNotFoundError as exc:
            raise HistoricalExecutionError("rollover timezone is unknown") from exc


@dataclass(frozen=True)
class BrokerSymbolMetadata:
    symbol: str
    version: str
    broker_source: str
    effective_from: datetime
    effective_to: datetime | None
    digits: int
    point_size: float
    tick_size: float
    tick_value: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    account_currency: str
    profit_currency: str
    margin_currency: str
    margin_rate: float
    commission: CommissionSchedule
    swap: SwapSchedule
    provenance: str

    def __post_init__(self) -> None:
        if self.symbol != EXECUTABLE_SYMBOL:
            raise HistoricalExecutionError("broker metadata must describe exactly XAUUSDm")
        if not self.version or not self.broker_source or not self.provenance:
            raise HistoricalExecutionError("versioned metadata provenance is required")
        start = utc_datetime(self.effective_from, "metadata effective_from")
        end = None if self.effective_to is None else utc_datetime(self.effective_to, "metadata effective_to")
        if end is not None and end <= start:
            raise HistoricalExecutionError("metadata effective range is invalid")
        object.__setattr__(self, "effective_from", start)
        object.__setattr__(self, "effective_to", end)
        if not isinstance(self.digits, int) or self.digits < 0 or self.digits > 12:
            raise HistoricalExecutionError("price digits are invalid")
        for field_name in (
            "point_size", "tick_size", "tick_value", "contract_size",
            "volume_min", "volume_max", "volume_step", "margin_rate",
        ):
            object.__setattr__(self, field_name, positive(getattr(self, field_name), field_name))
        if self.volume_min > self.volume_max or self.volume_step > self.volume_max:
            raise HistoricalExecutionError("volume metadata is inconsistent")
        if self.tick_size < self.point_size:
            raise HistoricalExecutionError("tick size cannot be smaller than point size")
        if not self.account_currency or not self.profit_currency or not self.margin_currency:
            raise HistoricalExecutionError("metadata currencies are required")
        if self.commission.currency != self.account_currency:
            raise HistoricalExecutionError(
                "commission currency conversion is unavailable; account-currency commission is required"
            )
        if self.profit_currency != self.account_currency:
            raise HistoricalExecutionError(
                "profit currency conversion is unavailable for this metadata segment"
            )

    def applies_at(self, timestamp: datetime) -> bool:
        value = utc_datetime(timestamp, "metadata lookup timestamp")
        return value >= self.effective_from and (self.effective_to is None or value < self.effective_to)


@dataclass(frozen=True)
class BrokerMetadataCatalog:
    segments: tuple[BrokerSymbolMetadata, ...]

    def __post_init__(self) -> None:
        if not self.segments:
            raise HistoricalExecutionError("metadata catalog requires at least one segment")
        ordered = tuple(sorted(self.segments, key=lambda item: item.effective_from))
        for previous, current in zip(ordered, ordered[1:]):
            if previous.effective_to is None or previous.effective_to > current.effective_from:
                raise HistoricalExecutionError("broker metadata segments overlap")
        object.__setattr__(self, "segments", ordered)

    def at(self, timestamp: datetime) -> BrokerSymbolMetadata:
        matches = [segment for segment in self.segments if segment.applies_at(timestamp)]
        if len(matches) != 1:
            raise HistoricalExecutionError("no unambiguous broker metadata segment is effective")
        return matches[0]


@dataclass(frozen=True)
class SlippageModel:
    kind: SlippageKind = SlippageKind.NONE
    points: float = 0.0
    source: CostSource = CostSource.NOT_AVAILABLE

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", positive(self.points, "slippage points", allow_zero=True))
        if self.kind is SlippageKind.NONE and self.points != 0:
            raise HistoricalExecutionError("NONE slippage cannot carry a non-zero amount")
        if self.kind is not SlippageKind.NONE and self.source is CostSource.NOT_AVAILABLE:
            raise HistoricalExecutionError("configured slippage requires provenance classification")


@dataclass(frozen=True)
class HistoricalExecutionPolicy:
    mode: RunMode
    fidelity: FidelityClass
    maximum_spread_points: float
    maximum_spread_to_stop_fraction: float = 0.10
    maximum_deviation_points: int = 1
    minimum_projected_margin_level_percent: float = 500.0
    maximum_new_order_margin_fraction: float = 0.10
    slippage: SlippageModel = field(default_factory=SlippageModel)
    random_seed: int = 0
    account_currency_digits: int = 2

    def __post_init__(self) -> None:
        object.__setattr__(self, "maximum_spread_points", positive(self.maximum_spread_points, "maximum spread points"))
        ratio = positive(self.maximum_spread_to_stop_fraction, "spread-to-stop fraction")
        if ratio > 1:
            raise HistoricalExecutionError("spread-to-stop fraction cannot exceed one")
        if not isinstance(self.maximum_deviation_points, int) or self.maximum_deviation_points < 0:
            raise HistoricalExecutionError("maximum deviation points must be a non-negative integer")
        positive(self.minimum_projected_margin_level_percent, "minimum margin level")
        margin_fraction = positive(self.maximum_new_order_margin_fraction, "maximum margin fraction")
        if margin_fraction > 1:
            raise HistoricalExecutionError("maximum margin fraction cannot exceed one")
        if self.account_currency_digits not in range(0, 9):
            raise HistoricalExecutionError("account currency digits are invalid")
        if self.mode is RunMode.VALIDATION:
            eligible = {
                FidelityClass.TICK_BID_ASK,
                FidelityClass.BAR_BID_ASK,
                FidelityClass.MID_BAR_WITH_OBSERVED_COSTS,
            }
            if self.fidelity not in eligible:
                raise HistoricalExecutionError("dataset fidelity is not validation-eligible")
            sources = (
                self.slippage.source,
            )
            if CostSource.ASSUMED in sources or CostSource.NOT_AVAILABLE in sources:
                raise HistoricalExecutionError("validation mode requires observed slippage provenance")

    @property
    def result_label(self) -> str:
        if self.mode is RunMode.VALIDATION:
            return "VALIDATION-ELIGIBLE EXECUTION DATA"
        return "DIAGNOSTIC \u2014 NOT VALIDATED"


@dataclass(frozen=True)
class SimulatedFill:
    fill_id: str
    action_id: str
    trade_id: str
    position_id: str
    timestamp: datetime
    symbol: str
    side: Side
    volume: float
    reference_price: float
    executable_quote: float
    fill_price: float
    slippage_price: float
    spread_price: float
    partial: bool
    reason_code: str
    fidelity: FidelityClass

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", utc_datetime(self.timestamp, "fill timestamp"))
        if not self.fill_id or not self.action_id or not self.trade_id or not self.position_id:
            raise HistoricalExecutionError("fill identities are required")
        if self.symbol != EXECUTABLE_SYMBOL:
            raise HistoricalExecutionError("simulated fills are restricted to XAUUSDm")
        object.__setattr__(self, "volume", positive(self.volume, "fill volume"))
        for field_name in ("reference_price", "executable_quote", "fill_price"):
            object.__setattr__(self, field_name, positive(getattr(self, field_name), field_name))
        object.__setattr__(self, "slippage_price", positive(self.slippage_price, "slippage", allow_zero=True))
        object.__setattr__(self, "spread_price", positive(self.spread_price, "spread", allow_zero=True))


@dataclass(frozen=True)
class HistoricalPosition:
    position_id: str
    trade_id: str
    symbol: str
    direction: Side
    opened_at: datetime
    entry_price: float
    initial_volume: float
    remaining_volume: float
    stop_price: float
    target_price: float
    last_swap_at: datetime
    closed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "opened_at", utc_datetime(self.opened_at, "position open time"))
        object.__setattr__(self, "last_swap_at", utc_datetime(self.last_swap_at, "last swap time"))
        if self.closed_at is not None:
            object.__setattr__(self, "closed_at", utc_datetime(self.closed_at, "position close time"))
        if not self.position_id or not self.trade_id or self.symbol != EXECUTABLE_SYMBOL:
            raise HistoricalExecutionError("position identity must reference XAUUSDm")
        for field_name in ("entry_price", "initial_volume", "stop_price", "target_price"):
            object.__setattr__(self, field_name, positive(getattr(self, field_name), field_name))
        remaining = positive(self.remaining_volume, "remaining volume", allow_zero=True)
        if remaining > self.initial_volume:
            raise HistoricalExecutionError("remaining volume exceeds initial volume")
        if self.direction is Side.BUY and not self.stop_price < self.target_price:
            raise HistoricalExecutionError("long position levels are invalid")
        if self.direction is Side.SELL and not self.target_price < self.stop_price:
            raise HistoricalExecutionError("short position levels are invalid")
        if (remaining == 0) != (self.closed_at is not None):
            raise HistoricalExecutionError("closed position state and remaining volume disagree")


@dataclass(frozen=True)
class LedgerEntry:
    ledger_id: str
    run_id: str
    trade_id: str | None
    position_id: str | None
    action_id: str
    timestamp: datetime
    event_type: LedgerEventType
    symbol: str
    side: Side | None
    volume: float
    reference_price: float | None
    executable_quote: float | None
    fill_price: float | None
    gross_price_pnl: float
    spread_attribution: float
    slippage_attribution: float
    commission: float
    swap: float
    net_cash_change: float
    balance_after: float
    equity_after: float
    provenance: str
    fidelity: FidelityClass

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", utc_datetime(self.timestamp, "ledger timestamp"))
        if not self.ledger_id or not self.run_id or not self.action_id:
            raise HistoricalExecutionError("ledger identities are required")
        if self.symbol != EXECUTABLE_SYMBOL:
            raise HistoricalExecutionError("ledger symbol must be XAUUSDm")
        object.__setattr__(self, "volume", positive(self.volume, "ledger volume", allow_zero=True))
        for field_name in (
            "gross_price_pnl", "spread_attribution", "slippage_attribution",
            "commission", "swap", "net_cash_change", "balance_after", "equity_after",
        ):
            object.__setattr__(self, field_name, finite(getattr(self, field_name), field_name))
        if self.spread_attribution < 0 or self.slippage_attribution < 0 or self.commission < 0:
            raise HistoricalExecutionError("ledger cost attribution cannot be negative")


@dataclass
class HistoricalAccountState:
    initial_balance: float
    balance: float
    equity: float
    used_margin: float = 0.0
    free_margin: float = 0.0
    realized_gross_pnl: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    unrealized_pnl: float = 0.0
    high_water_equity: float = 0.0

    def __post_init__(self) -> None:
        for field_name in ("initial_balance", "balance", "equity"):
            positive(getattr(self, field_name), field_name)
        if self.high_water_equity == 0:
            self.high_water_equity = self.equity
        self.free_margin = self.equity - self.used_margin


def enum_json(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return utc_datetime(value, "serialized timestamp").isoformat().replace("+00:00", "Z")
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): enum_json(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [enum_json(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return enum_json(asdict(value))
    return value
