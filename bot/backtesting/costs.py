from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .models import (
    BrokerSymbolMetadata,
    CommissionKind,
    HistoricalExecutionError,
    Side,
    SlippageKind,
    SlippageModel,
    SwapCalculation,
    utc_datetime,
)


def deterministic_slippage_points(
    model: SlippageModel,
    *,
    seed: int,
    action_id: str,
) -> float:
    if model.kind is SlippageKind.NONE:
        return 0.0
    if model.kind is SlippageKind.FIXED_ADVERSE_POINTS:
        return model.points
    material = f"{seed}|{action_id}|phase7-slippage".encode("utf-8")
    unit = int.from_bytes(hashlib.sha256(material).digest()[:8], "big") / float(2**64 - 1)
    return unit * model.points


def adverse_fill_price(
    reference_price: float,
    transaction_side: Side,
    model: SlippageModel,
    metadata: BrokerSymbolMetadata,
    *,
    seed: int,
    action_id: str,
) -> tuple[float, float]:
    points = deterministic_slippage_points(model, seed=seed, action_id=action_id)
    price_amount = points * metadata.point_size
    fill = reference_price + price_amount if transaction_side is Side.BUY else reference_price - price_amount
    return fill, price_amount


def commission_for_fill(
    metadata: BrokerSymbolMetadata,
    *,
    volume: float,
    fill_price: float,
) -> float:
    schedule = metadata.commission
    if schedule.kind is CommissionKind.PER_LOT_PER_SIDE:
        return schedule.amount * volume
    if schedule.kind is CommissionKind.PER_LOT_ROUND_TURN:
        return schedule.amount * volume / 2.0
    if schedule.kind is CommissionKind.FIXED_PER_ORDER:
        return schedule.amount
    if schedule.kind is CommissionKind.PERCENT_NOTIONAL:
        return fill_price * metadata.contract_size * volume * schedule.amount
    raise HistoricalExecutionError("unsupported commission schedule")


def rollover_instants(
    start: datetime,
    end: datetime,
    metadata: BrokerSymbolMetadata,
) -> tuple[datetime, ...]:
    start_utc = utc_datetime(start, "swap interval start")
    end_utc = utc_datetime(end, "swap interval end")
    if end_utc < start_utc:
        raise HistoricalExecutionError("swap interval moves backward")
    zone = ZoneInfo(metadata.swap.rollover_timezone)
    local_start = start_utc.astimezone(zone)
    local_end = end_utc.astimezone(zone)
    current: date = local_start.date() - timedelta(days=1)
    final = local_end.date() + timedelta(days=1)
    result: list[datetime] = []
    while current <= final:
        local_rollover = datetime.combine(current, metadata.swap.rollover_time, tzinfo=zone)
        instant = local_rollover.astimezone(ZoneInfo("UTC"))
        if start_utc < instant <= end_utc:
            result.append(instant)
        current += timedelta(days=1)
    return tuple(sorted(result))


def swap_for_rollover(
    metadata: BrokerSymbolMetadata,
    *,
    direction: Side,
    volume: float,
    rollover: datetime,
) -> tuple[float, int]:
    instant = utc_datetime(rollover, "rollover")
    local_weekday = instant.astimezone(ZoneInfo(metadata.swap.rollover_timezone)).weekday()
    multiplier = 3 if local_weekday == metadata.swap.triple_swap_weekday else 1
    rate = metadata.swap.long_rate if direction is Side.BUY else metadata.swap.short_rate
    if metadata.swap.calculation is SwapCalculation.ACCOUNT_CURRENCY_PER_LOT:
        amount = rate * volume * multiplier
    elif metadata.swap.calculation is SwapCalculation.POINTS_PER_LOT:
        amount = (
            rate
            * metadata.point_size
            / metadata.tick_size
            * metadata.tick_value
            * volume
            * multiplier
        )
    else:
        raise HistoricalExecutionError("unsupported swap calculation")
    return amount, multiplier
