from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .models import BlockState, OrderBlockResult, StrategySide
from .regime import atr_series


@dataclass(frozen=True)
class OrderBlock:
    block_id: str
    side: StrategySide
    zone_low: float
    zone_high: float
    candidate_open_time: datetime
    confirmed_at: datetime
    confirmation_index: int


def _result(block: OrderBlock | None, state: BlockState, reason: str) -> OrderBlockResult:
    return OrderBlockResult(
        state=state,
        side=StrategySide.FLAT if block is None else block.side,
        block_id=None if block is None else block.block_id,
        zone_low=None if block is None else block.zone_low,
        zone_high=None if block is None else block.zone_high,
        confirmed_at=None if block is None else block.confirmed_at,
        reason=reason,
    )


def _valid_frame(frame: pd.DataFrame) -> bool:
    required = {"open_time", "available_at", "open", "high", "low", "close"}
    if frame is None or not required.issubset(frame.columns):
        return False
    prices = frame[["open", "high", "low", "close"]].astype(float)
    if not np.isfinite(prices.to_numpy()).all():
        return False
    if not (
        (prices["high"] >= prices["open"]).all()
        and (prices["high"] >= prices["close"]).all()
        and (prices["high"] >= prices["low"]).all()
        and (prices["low"] <= prices["open"]).all()
        and (prices["low"] <= prices["close"]).all()
    ):
        return False
    try:
        opens = [pd.Timestamp(value) for value in frame["open_time"]]
        availability = [pd.Timestamp(value) for value in frame["available_at"]]
    except (TypeError, ValueError):
        return False
    return bool(opens) and all(
        opened.tzinfo is not None
        and available.tzinfo is not None
        and available > opened
        for opened, available in zip(opens, availability)
    ) and len(set(opens)) == len(opens)


def detect_order_blocks(frame: pd.DataFrame, config: StrategyConfig) -> tuple[OrderBlock, ...]:
    if frame is None or len(frame) < config.atr_period_bars + 2 or not _valid_frame(frame):
        return ()
    ordered = frame.sort_values("open_time", kind="mergesort").reset_index(drop=True)
    prices = ordered[["open", "high", "low", "close"]].astype(float)
    if not np.isfinite(prices.to_numpy()).all():
        return ()
    atr = atr_series(prices, config.atr_period_bars)
    blocks: list[OrderBlock] = []
    for confirmation_index in range(1, len(ordered)):
        candidate_index = confirmation_index - 1
        candidate = ordered.iloc[candidate_index]
        confirmation = ordered.iloc[confirmation_index]
        atr_value = float(atr.iloc[confirmation_index])
        if not math.isfinite(atr_value) or atr_value <= 0:
            continue
        body = abs(float(confirmation["close"]) - float(confirmation["open"]))
        bullish = (
            float(candidate["close"]) < float(candidate["open"])
            and float(confirmation["close"]) > float(candidate["high"])
            and body >= atr_value * config.order_block_displacement_atr
        )
        bearish = (
            float(candidate["close"]) > float(candidate["open"])
            and float(confirmation["close"]) < float(candidate["low"])
            and body >= atr_value * config.order_block_displacement_atr
        )
        if not bullish and not bearish:
            continue
        side = StrategySide.LONG if bullish else StrategySide.SHORT
        confirmed_at = pd.Timestamp(confirmation["available_at"]).to_pydatetime()
        candidate_open = pd.Timestamp(candidate["open_time"]).to_pydatetime()
        material = f"{side.value}|{candidate_open.isoformat()}|{confirmed_at.isoformat()}"
        blocks.append(
            OrderBlock(
                hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
                side,
                float(candidate["low"]),
                float(candidate["high"]),
                candidate_open,
                confirmed_at,
                confirmation_index,
            )
        )
    return tuple(blocks)


def evaluate_order_block(
    frame: pd.DataFrame,
    side: StrategySide,
    decision_at: datetime,
    config: StrategyConfig,
    *,
    consumed_ids: frozenset[str] = frozenset(),
) -> OrderBlockResult:
    if not isinstance(decision_at, datetime) or decision_at.tzinfo is None:
        return _result(None, BlockState.DATA_UNSAFE, "invalid_decision_time")
    if not _valid_frame(frame):
        return _result(None, BlockState.DATA_UNSAFE, "malformed_or_naive_candle_frame")
    blocks = [block for block in detect_order_blocks(frame, config) if block.side is side]
    if not blocks:
        return _result(None, BlockState.UNAVAILABLE, "no_confirmed_block")
    block = sorted(blocks, key=lambda item: (item.confirmed_at, -item.zone_high + item.zone_low, item.block_id))[-1]
    if block.confirmed_at > decision_at:
        return _result(block, BlockState.PREMATURE, "confirmation_not_available")
    if block.block_id in consumed_ids:
        return _result(block, BlockState.CONSUMED, "block_already_consumed")

    ordered = frame.sort_values("open_time", kind="mergesort").reset_index(drop=True)
    later = ordered.iloc[block.confirmation_index + 1 :]
    later = later[pd.to_datetime(later["available_at"], utc=True) <= pd.Timestamp(decision_at)]
    if len(later) > config.order_block_expiry_bars:
        return _result(block, BlockState.EXPIRED, "block_expired")
    for position, (_index, candle) in enumerate(later.iterrows()):
        close = float(candle["close"])
        if side is StrategySide.LONG and close < block.zone_low:
            return _result(block, BlockState.INVALIDATED, "close_below_bullish_zone")
        if side is StrategySide.SHORT and close > block.zone_high:
            return _result(block, BlockState.INVALIDATED, "close_above_bearish_zone")
        overlaps = float(candle["low"]) <= block.zone_high and float(candle["high"]) >= block.zone_low
        if overlaps:
            if position == len(later) - 1:
                return _result(block, BlockState.RETEST_ELIGIBLE, "first_post_confirmation_retest")
            return _result(block, BlockState.MITIGATED, "block_already_mitigated")
    return _result(block, BlockState.ELIGIBLE, "confirmed_unmitigated_block")
