"""Pure construction of the existing orchestrator's absolute SMC trade levels."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence


@dataclass(frozen=True)
class LevelInputs:
    direction: str
    entry_price: float
    entry_mode: str | None
    ob_zone: Sequence[float] | None
    internal_structure: Mapping[str, object]
    recent_lows: tuple[float, ...]
    recent_highs: tuple[float, ...]
    structure_context: Mapping[str, object]
    liquidity_pools: tuple[Mapping[str, object], ...]
    atr: float
    point: float
    stops_level: int
    digits: int
    level_config: Mapping[str, object]
    min_rr: float
    min_rr_buffer: float = 0.0


@dataclass(frozen=True)
class LevelResult:
    stop: float | None
    target: float | None
    reason: str


def _anchor(inputs: LevelInputs) -> float | None:
    candidates: list[float] = []
    structure = inputs.internal_structure
    for key in ("last_choch_level", "last_bos_level"):
        value = structure.get(key)
        if value is not None:
            candidates.append(float(value))
    if inputs.direction == "buy":
        candidates.extend(float(s["price"]) for s in (structure.get("swing_lows") or [])[-6:] if "price" in s)
        if inputs.recent_lows:
            candidates.append(min(inputs.recent_lows))
        below = [level for level in candidates if level < inputs.entry_price]
        return max(below) if below else None
    candidates.extend(float(s["price"]) for s in (structure.get("swing_highs") or [])[-6:] if "price" in s)
    if inputs.recent_highs:
        candidates.append(max(inputs.recent_highs))
    above = [level for level in candidates if level > inputs.entry_price]
    return min(above) if above else None


def _rr(entry: float, stop: float, target: float) -> float:
    return abs(target - entry) / abs(entry - stop)


def _target(inputs: LevelInputs, stop: float) -> float:
    distance = abs(inputs.entry_price - stop)
    fallback = inputs.entry_price + distance * inputs.min_rr if inputs.direction == "buy" else inputs.entry_price - distance * inputs.min_rr
    ahead: list[float] = []
    for pool in inputs.liquidity_pools:
        if not isinstance(pool, Mapping) or pool.get("price") is None:
            continue
        price = float(pool["price"])
        if (inputs.direction == "buy" and price > inputs.entry_price) or (inputs.direction == "sell" and price < inputs.entry_price):
            ahead.append(price)
    if not ahead:
        return fallback
    ordered = sorted(ahead, reverse=inputs.direction == "sell")[:3]
    for candidate in reversed(ordered):
        if _rr(inputs.entry_price, stop, candidate) >= inputs.min_rr:
            return candidate
    return fallback


def build_trade_levels(inputs: LevelInputs) -> LevelResult:
    if inputs.direction not in ("buy", "sell") or not math.isfinite(inputs.entry_price) or inputs.entry_price <= 0:
        return LevelResult(None, None, "invalid_entry_reference")
    if not math.isfinite(inputs.atr) or inputs.atr < 0 or not math.isfinite(inputs.min_rr) or inputs.min_rr <= 0:
        return LevelResult(None, None, "invalid_level_inputs")
    cfg = inputs.level_config
    buffer = max(
        inputs.atr * float(cfg.get("anchor_buffer_atr_mult", 0.0) or 0.0),
        float(cfg.get("anchor_buffer_price", 0.0) or 0.0),
    )
    stop: float | None = None
    reason = "unresolved"
    if inputs.entry_mode == "aggressive" and inputs.ob_zone:
        low, high = sorted((float(inputs.ob_zone[0]), float(inputs.ob_zone[1])))
        stop = low - buffer if inputs.direction == "buy" else high + buffer
        reason = "aggressive_ob_boundary"
    if stop is None:
        anchor = _anchor(inputs)
        if anchor is not None:
            stop = anchor - buffer if inputs.direction == "buy" else anchor + buffer
            reason = "internal_structure_anchor"
    if stop is None:
        zone = inputs.structure_context.get("discount_zone" if inputs.direction == "buy" else "premium_zone")
        if zone:
            stop = float(zone[0]) - buffer if inputs.direction == "buy" else float(zone[1]) + buffer
            reason = "discount_zone_floor" if inputs.direction == "buy" else "premium_zone_ceiling"
    if stop is None or not math.isfinite(stop) or stop <= 0:
        return LevelResult(None, None, "no_smc_stop_anchor")
    if inputs.direction == "buy" and stop >= inputs.entry_price:
        return LevelResult(None, None, f"invalid_buy_sl:{reason}")
    if inputs.direction == "sell" and stop <= inputs.entry_price:
        return LevelResult(None, None, f"invalid_sell_sl:{reason}")
    broker_min = float(inputs.stops_level or 10) * inputs.point
    atr_floor = inputs.atr * float(cfg.get("min_stop_atr_mult", 0.35) or 0.0) if inputs.atr > 0 else 0.0
    point_floor = inputs.point * float(cfg.get("min_stop_points", 500) or 0.0) if inputs.point > 0 else 0.0
    price_floor = float(cfg.get("min_stop_price", 0.0) or 0.0)
    minimum = max(broker_min, atr_floor, point_floor, price_floor)
    distance = abs(inputs.entry_price - stop)
    if minimum > 0 and distance < minimum:
        return LevelResult(None, None, f"smc_stop_too_tight({distance:.3f}<{minimum:.3f})")
    max_atr = inputs.atr * float(cfg.get("max_stop_atr_mult", 0.0) or 0.0) if inputs.atr > 0 else 0.0
    max_price = float(cfg.get("max_stop_price", 0.0) or 0.0)
    limits = [value for value in (max_atr, max_price) if value > 0]
    maximum = min(limits) if limits else 0.0
    if maximum > 0 and distance > maximum:
        return LevelResult(None, None, f"exceeds_max_stop({distance:.1f}>{maximum:.1f})")
    if distance <= 0:
        return LevelResult(None, None, "invalid_stop_distance")
    target = _target(inputs, stop)
    if inputs.min_rr_buffer > 0:
        required = inputs.min_rr + float(inputs.min_rr_buffer)
        if round(_rr(inputs.entry_price, stop, target), 4) < required:
            target = inputs.entry_price + distance * required if inputs.direction == "buy" else inputs.entry_price - distance * required
    if not math.isfinite(target) or _rr(inputs.entry_price, stop, target) < inputs.min_rr:
        return LevelResult(None, None, "rr_below_orchestrator_minimum")
    return LevelResult(round(float(stop), inputs.digits), round(float(target), inputs.digits), reason)
