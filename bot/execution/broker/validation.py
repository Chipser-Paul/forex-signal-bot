from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Callable

from .models import (
    BrokerSnapshot,
    BrokerSymbol,
    BrokerTick,
    ExecutionAction,
    ExecutionPolicy,
    ExecutionReason,
    ExecutionRejected,
    ExecutionRequest,
    FillingMode,
)


def tick_from_mt5(raw_tick: Any) -> BrokerTick:
    if raw_tick is None:
        raise ExecutionRejected(ExecutionReason.TICK_MISSING, "broker tick is missing")
    time_msc = int(getattr(raw_tick, "time_msc", 0) or 0)
    seconds = int(getattr(raw_tick, "time", 0) or 0)
    if time_msc > 0:
        timestamp = datetime.fromtimestamp(time_msc / 1000.0, tz=timezone.utc)
    elif seconds > 0:
        timestamp = datetime.fromtimestamp(seconds, tz=timezone.utc)
    else:
        raise ExecutionRejected(ExecutionReason.TICK_INVALID, "broker tick has no timestamp")
    try:
        return BrokerTick(timestamp, float(raw_tick.bid), float(raw_tick.ask))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ExecutionRejected(ExecutionReason.TICK_INVALID, "broker tick prices are invalid") from exc


def validate_tick(tick: BrokerTick, now: datetime, policy: ExecutionPolicy) -> None:
    if now.tzinfo is None:
        raise ExecutionRejected(ExecutionReason.TICK_INVALID, "validation time must be aware")
    age = (now.astimezone(timezone.utc) - tick.timestamp).total_seconds()
    if age < -policy.future_tick_tolerance_seconds:
        raise ExecutionRejected(ExecutionReason.TICK_FUTURE, "broker tick is future-dated")
    if age > policy.maximum_tick_age_seconds:
        raise ExecutionRejected(ExecutionReason.TICK_STALE, "broker tick is stale")


def validate_spread(
    symbol: BrokerSymbol,
    tick: BrokerTick,
    stop_price: float | None,
    policy: ExecutionPolicy,
) -> tuple[float, float | None]:
    try:
        absolute_limit = policy.spread_limit(symbol.symbol)
    except Exception as exc:
        raise ExecutionRejected(
            ExecutionReason.SPREAD_CONFIGURATION_MISSING,
            f"spread configuration is missing for {symbol.symbol}",
        ) from exc
    spread = tick.ask - tick.bid
    spread_points = spread / symbol.point
    if not math.isfinite(spread_points) or spread_points < 0:
        raise ExecutionRejected(ExecutionReason.TICK_INVALID, "calculated spread is invalid")
    if spread_points > absolute_limit + 1e-9:
        raise ExecutionRejected(
            ExecutionReason.SPREAD_ABSOLUTE_LIMIT,
            "broker spread exceeds the configured absolute limit",
        )
    ratio = None
    if stop_price is not None:
        reference = tick.ask if stop_price < tick.bid else tick.bid
        stop_distance = abs(reference - float(stop_price))
        if stop_distance <= 0 or not math.isfinite(stop_distance):
            raise ExecutionRejected(ExecutionReason.STOP_INVALID, "stop distance is invalid")
        ratio = spread / stop_distance
        if ratio > policy.maximum_spread_to_stop_fraction + 1e-12:
            raise ExecutionRejected(
                ExecutionReason.SPREAD_RELATIVE_LIMIT,
                "broker spread exceeds the stop-relative limit",
            )
    return spread_points, ratio


def normalize_price(value: float, digits: int) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ExecutionRejected(ExecutionReason.SYMBOL_METADATA_INVALID, "price is invalid")
    return round(number, digits)


def normalize_volume_down(volume: float, symbol: BrokerSymbol) -> float:
    raw = Decimal(str(volume))
    step = Decimal(str(symbol.volume_step))
    normalized = (raw / step).to_integral_value(rounding=ROUND_FLOOR) * step
    normalized = min(normalized, Decimal(str(symbol.volume_max)))
    value = float(normalized)
    if value < symbol.volume_min - 1e-12 or value <= 0:
        raise ExecutionRejected(ExecutionReason.VOLUME_INVALID, "normalized volume is below minimum")
    if value > float(volume) + 1e-12:
        raise ExecutionRejected(ExecutionReason.VOLUME_INVALID, "volume normalization increased volume")
    return value


def validate_directional_levels(
    direction: str,
    executable_price: float,
    stop_price: float | None,
    target_price: float | None,
    symbol: BrokerSymbol,
    tick: BrokerTick,
    *,
    modification: bool = False,
) -> tuple[float | None, float | None]:
    entry = normalize_price(executable_price, symbol.digits)
    stop = None if stop_price is None else normalize_price(stop_price, symbol.digits)
    target = None if target_price is None else normalize_price(target_price, symbol.digits)
    if stop is None and not modification:
        raise ExecutionRejected(ExecutionReason.STOP_INVALID, "an entry requires a stop")
    if direction == "buy":
        if stop is not None and stop >= entry:
            raise ExecutionRejected(ExecutionReason.STOP_INVALID, "buy stop must be below entry")
        if target is not None and target <= entry:
            raise ExecutionRejected(ExecutionReason.TARGET_INVALID, "buy target must be above entry")
    elif direction == "sell":
        if stop is not None and stop <= entry:
            raise ExecutionRejected(ExecutionReason.STOP_INVALID, "sell stop must be above entry")
        if target is not None and target >= entry:
            raise ExecutionRejected(ExecutionReason.TARGET_INVALID, "sell target must be below entry")
    else:
        raise ExecutionRejected(ExecutionReason.STOP_INVALID, "direction is invalid")

    minimum = symbol.stops_level_points * symbol.point
    freeze = symbol.freeze_level_points * symbol.point
    reference = tick.bid if direction == "buy" else tick.ask
    for level, label in ((stop, "stop"), (target, "target")):
        if level is None:
            continue
        distance = abs(reference - level)
        if distance + 1e-12 < minimum:
            raise ExecutionRejected(
                ExecutionReason.STOP_DISTANCE_VIOLATION,
                f"{label} violates the broker minimum distance",
            )
        if modification and distance + 1e-12 < freeze:
            raise ExecutionRejected(
                ExecutionReason.FREEZE_LEVEL_VIOLATION,
                f"{label} violates the broker freeze distance",
            )
    return stop, target


def stop_widened(direction: str, approved_stop: float | None, proposed_stop: float | None) -> bool:
    if approved_stop is None or proposed_stop is None:
        return False
    if direction == "buy":
        return proposed_stop < approved_stop - 1e-12
    return proposed_stop > approved_stop + 1e-12


def stop_improves(direction: str, current_stop: float, proposed_stop: float) -> bool:
    if direction == "buy":
        return proposed_stop > current_stop + 1e-12
    return proposed_stop < current_stop - 1e-12


def validate_margin(
    *,
    required_margin: float | None,
    snapshot: BrokerSnapshot,
    policy: ExecutionPolicy,
) -> tuple[float, float, float]:
    try:
        required = float(required_margin)
    except (TypeError, ValueError) as exc:
        raise ExecutionRejected(
            ExecutionReason.MARGIN_CALCULATION_FAILED,
            "broker margin calculation is missing",
        ) from exc
    if not math.isfinite(required) or required < 0:
        raise ExecutionRejected(
            ExecutionReason.MARGIN_CALCULATION_FAILED,
            "broker margin calculation is invalid",
        )
    projected_margin = snapshot.margin + required
    projected_free = snapshot.free_margin - required
    if projected_free <= 0:
        raise ExecutionRejected(
            ExecutionReason.FREE_MARGIN_INSUFFICIENT,
            "projected free margin is not positive",
        )
    if required > snapshot.equity * policy.maximum_new_order_margin_fraction + 1e-9:
        raise ExecutionRejected(
            ExecutionReason.NEW_ORDER_MARGIN_LIMIT,
            "new-order margin exceeds its equity fraction limit",
        )
    projected_level = math.inf if projected_margin == 0 else snapshot.equity / projected_margin * 100.0
    if projected_level < policy.minimum_projected_margin_level_percent - 1e-9:
        raise ExecutionRejected(
            ExecutionReason.MARGIN_LEVEL_TOO_LOW,
            "projected margin level is below the policy minimum",
        )
    return required, projected_free, projected_level


def select_filling_mode(broker: Any, symbol: BrokerSymbol, policy: ExecutionPolicy) -> FillingMode:
    flag_fok = int(getattr(broker, "SYMBOL_FILLING_FOK", 1))
    flag_ioc = int(getattr(broker, "SYMBOL_FILLING_IOC", 2))
    market_execution = int(getattr(broker, "SYMBOL_TRADE_EXECUTION_MARKET", 2))
    supported: set[FillingMode] = set()
    if symbol.filling_flags & flag_fok:
        supported.add(FillingMode.FOK)
    if symbol.filling_flags & flag_ioc:
        supported.add(FillingMode.IOC)
    if symbol.execution_mode != market_execution:
        supported.add(FillingMode.RETURN)
    for mode in policy.filling_preference:
        if mode in supported:
            return mode
    raise ExecutionRejected(
        ExecutionReason.FILLING_MODE_UNSUPPORTED,
        "symbol exposes no policy-approved filling mode",
    )


def broker_filling_constant(broker: Any, mode: FillingMode) -> int:
    attribute = {
        FillingMode.FOK: "ORDER_FILLING_FOK",
        FillingMode.IOC: "ORDER_FILLING_IOC",
        FillingMode.RETURN: "ORDER_FILLING_RETURN",
    }[mode]
    if not hasattr(broker, attribute):
        raise ExecutionRejected(
            ExecutionReason.FILLING_MODE_UNSUPPORTED,
            f"broker does not expose {attribute}",
        )
    return int(getattr(broker, attribute))


def corrected_absolute_levels(
    request: ExecutionRequest,
    symbol: BrokerSymbol,
    tick: BrokerTick,
) -> tuple[float, float | None]:
    if request.stop_price is None:
        raise ExecutionRejected(ExecutionReason.STOP_INVALID, "stop correction requires a stop")
    minimum = max(symbol.stops_level_points, symbol.freeze_level_points) * symbol.point
    if minimum <= 0:
        raise ExecutionRejected(
            ExecutionReason.BROKER_INVALID_STOPS,
            "broker provided no safe stop-correction distance",
        )
    if request.direction == "buy":
        stop = normalize_price(tick.bid - minimum, symbol.digits)
        target = request.target_price
        if target is not None and target <= tick.ask:
            target = normalize_price(tick.ask + minimum, symbol.digits)
    else:
        stop = normalize_price(tick.ask + minimum, symbol.digits)
        target = request.target_price
        if target is not None and target >= tick.bid:
            target = normalize_price(tick.bid - minimum, symbol.digits)
    return stop, target


def with_reapproved_stop(
    request: ExecutionRequest,
    stop: float,
    target: float | None,
    approved_volume: float,
) -> ExecutionRequest:
    if approved_volume > request.approved_volume + 1e-12:
        raise ExecutionRejected(
            ExecutionReason.RISK_APPROVAL_INVALID,
            "risk reapproval cannot increase approved volume",
        )
    return replace(
        request,
        volume=min(request.volume, approved_volume),
        approved_volume=approved_volume,
        stop_price=stop,
        target_price=target,
        approved_stop=stop,
        risk_reapproved=True,
    )
