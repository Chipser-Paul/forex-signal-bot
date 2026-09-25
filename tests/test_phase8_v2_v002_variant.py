# -*- coding: utf-8 -*-
"""Synthetic invariant tests for the V002 structural-pair evaluator (H007).

No store access, no empirical data.  Proves the preregistered invariants of
``docs/PHASE8_V2_VARIANT_V002.md`` section 21 for the pair evaluator and the
V002 Gate-11 scorer.  Downstream-consistency tests live in
``tests/test_phase8_v2_v002_downstream.py``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import pytest

from bot.strategy.config import StrategyConfig
from bot.strategy.models import BlockState, StrategySide
from bot.strategy.order_blocks import detect_order_blocks, evaluate_order_block
from bot.strategy.variant_v002 import (
    V002_ACTIVE,
    V002_CONSUMED,
    V002_DATA_UNSAFE,
    V002_FVG_LABEL,
    V002_INVALIDATED,
    V002_MITIGATED,
    V002_OB_LABEL,
    V002_PREMATURE,
    V002_RETEST_ELIGIBLE,
    evaluate_v002_structural_pair,
    score_v002_setup,
)

UTC = timezone.utc
BASE = datetime(2024, 5, 1, 9, 0, tzinfo=UTC)
BAR = timedelta(minutes=5)


def candle(open_time: datetime, o: float, h: float, l: float, c: float) -> dict[str, Any]:
    return {
        "open_time": open_time.isoformat(),
        "available_at": (open_time + BAR).isoformat(),
        "open": o, "high": h, "low": l, "close": c,
    }


def build_rows(pre: int, post: int, price: float = 2400.0, start: datetime = BASE) -> list[dict[str, Any]]:
    """Quiet range, bearish candidate candle, bullish displacement confirmation,
    then quiet post-confirmation candles drifting above the block zone."""
    rows = [
        candle(start + BAR * i, price, price + 2.0, price - 2.0, price)
        for i in range(pre)
    ]
    candidate = candle(start + BAR * pre, price, price + 1.0, price - 10.0, price - 9.0)
    confirmation = candle(
        start + BAR * (pre + 1), price - 9.0, price + 13.0, price - 11.0, price + 12.0
    )
    rows += [candidate, confirmation]
    t = start + BAR * (pre + 2)
    for _ in range(post):
        rows.append(candle(t, price + 6.0, price + 8.0, price + 4.0, price + 6.0))
        t += BAR
    return rows


def zone_of(rows: list[dict[str, Any]], pre: int) -> tuple[float, float]:
    """The canonical block zone is the candidate candle's low..high."""
    candidate = rows[pre]
    return float(candidate["low"]), float(candidate["high"])


def to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True)
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True)
    return frame


def bullish_fixture(pre: int, post: int):
    rows = build_rows(pre, post)
    frame = to_frame(rows)
    config = StrategyConfig()
    blocks = detect_order_blocks(frame, config)
    assert blocks, "fixture must produce a bullish displacement block"
    block = blocks[-1]
    assert block.side is StrategySide.LONG
    decision_at = BASE + BAR * (pre + 2 + post)
    return frame, config, block, decision_at


def fvgs(bottom: float, top: float, direction: str = "bullish") -> tuple[dict[str, Any], ...]:
    return ({"direction": direction, "top": float(top), "bottom": float(bottom)},)


def test_young_untouched_block_remains_structurally_active():
    frame, config, _block, decision_at = bullish_fixture(pre=30, post=3)
    result = evaluate_v002_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=())
    assert result.structurally_active
    assert result.state == V002_ACTIVE
    assert result.reason == "structurally_active_block"
    assert result.age_bars == 3
    assert result.fvg_associated is False
    assert result.exact_overlap is None
    canonical = evaluate_order_block(frame, StrategySide.LONG, decision_at, config)
    assert canonical.state is BlockState.ELIGIBLE
    assert v002_matches_canonical(result, canonical)


def v002_matches_canonical(result, canonical) -> bool:
    return (
        result.block_id == canonical.block_id
        and result.zone_low == canonical.zone_low
        and result.zone_high == canonical.zone_high
    )


def test_over_30_bar_untouched_block_active_under_v002_while_canonical_expires():
    frame, config, _block, decision_at = bullish_fixture(pre=30, post=33)
    v002 = evaluate_v002_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=())
    assert v002.structurally_active
    assert v002.state == V002_ACTIVE
    assert v002.reason == "structurally_active_block"
    assert v002.age_bars == 33
    assert v002.age_bars > 30
    canonical = evaluate_order_block(frame, StrategySide.LONG, decision_at, config)
    assert canonical.state is BlockState.EXPIRED
    assert canonical.reason == "block_expired"
    assert v002_matches_canonical(v002, canonical)
    assert v002.fvg_associated is False


def test_age_is_recorded_as_metadata_deep_past_thirty_bars():
    frame, config, _block, decision_at = bullish_fixture(pre=30, post=63)
    v002 = evaluate_v002_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=())
    assert v002.state == V002_ACTIVE
    assert v002.age_bars == 63
    assert v002.age_bars > 30
    canonical = evaluate_order_block(frame, StrategySide.LONG, decision_at, config)
    assert canonical.state is BlockState.EXPIRED
    assert v002_matches_canonical(v002, canonical)


def test_over_30_bar_touched_block_is_not_structurally_active():
    rows = build_rows(pre=30, post=40)
    zone_low, zone_high = zone_of(rows, 30)
    assert zone_low < zone_high
    # The block touches the zone a few bars after confirmation (low enters
    # the zone, close does not invalidate it); the decision happens far
    # past 30 bars of age.  Touch, not age, is what disqualifies the pair.
    touch_open_time = BASE + BAR * 33
    rows[33] = candle(touch_open_time, zone_high + 2.0, zone_high + 3.0, zone_high - 1.5, zone_high + 1.0)
    frame = to_frame(rows)
    config = StrategyConfig()
    decision_at = BASE + BAR * 72
    v002 = evaluate_v002_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=())
    assert not v002.structurally_active
    assert v002.state == V002_MITIGATED
    assert v002.reason == "block_already_mitigated"
    assert v002.age_bars == 40
    assert v002.age_bars > 30
    canonical = evaluate_order_block(frame, StrategySide.LONG, decision_at, config)
    assert canonical.state is BlockState.EXPIRED, "canonical age short-circuit still precedes mitigation"


def test_over_30_bar_invalidated_block_is_not_structurally_active():
    rows = build_rows(pre=30, post=5)
    zone_low, _zone_high = zone_of(rows, 30)
    break_open_time = BASE + BAR * 33
    rows[33] = candle(break_open_time, zone_low - 0.5, zone_low + 0.5, zone_low - 4.0, zone_low - 3.0)
    frame = to_frame(rows)
    config = StrategyConfig()
    decision_at = BASE + BAR * 37
    v002 = evaluate_v002_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=())
    assert not v002.structurally_active
    assert v002.state == V002_INVALIDATED
    assert v002.reason == "close_below_bullish_zone"


def test_consumed_block_is_rejected():
    frame, config, block, decision_at = bullish_fixture(pre=30, post=3)
    v002 = evaluate_v002_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=(),
        consumed_ids=frozenset({block.block_id}),
    )
    assert v002.state == V002_CONSUMED
    assert v002.reason == "block_already_consumed"
    assert not v002.structurally_active


def test_premature_confirmation_is_rejected():
    frame, config, block, _decision_at = bullish_fixture(pre=30, post=3)
    assert block.confirmed_at is not None
    decision_at = block.confirmed_at - timedelta(seconds=1)
    v002 = evaluate_v002_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=())
    assert v002.state == V002_PREMATURE
    assert v002.reason == "confirmation_not_available"


def test_no_confirmed_block_is_unavailable():
    rows = build_rows(pre=30, post=3)[:-4]
    frame = to_frame(rows)
    config = StrategyConfig()
    decision_at = BASE + BAR * 31
    v002 = evaluate_v002_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=())
    assert v002.state == "UNAVAILABLE"
    assert v002.reason == "no_confirmed_block"
    assert not v002.structurally_active


def test_data_unsafe_inputs_fail_closed():
    config = StrategyConfig()
    naive = datetime(2024, 5, 1, 10, 0)
    v002 = evaluate_v002_structural_pair(pd.DataFrame(), StrategySide.LONG, naive, config)
    assert v002.state == V002_DATA_UNSAFE
    assert v002.reason == "invalid_decision_time"


def test_short_side_structural_pair():
    price = 2400.0
    rows = [
        candle(BASE + BAR * i, price, price + 2.0, price - 2.0, price)
        for i in range(30)
    ]
    candidate = candle(BASE + BAR * 30, price, price + 10.0, price - 1.0, price + 9.0)
    confirmation = candle(BASE + BAR * 31, price + 9.0, price + 11.0, price - 13.0, price - 12.0)
    rows += [candidate, confirmation]
    t = BASE + BAR * 32
    for _ in range(3):
        rows.append(candle(t, price - 6.0, price - 4.0, price - 8.0, price - 6.0))
        t += BAR
    frame = to_frame(rows)
    config = StrategyConfig()
    blocks = detect_order_blocks(frame, config)
    assert blocks and blocks[-1].side is StrategySide.SHORT
    decision_at = BASE + BAR * 35
    v002 = evaluate_v002_structural_pair(frame, StrategySide.SHORT, decision_at, config, fvgs=())
    assert v002.structurally_active
    assert v002.state == V002_ACTIVE
    assert v002.side is StrategySide.SHORT
    canonical = evaluate_order_block(frame, StrategySide.SHORT, decision_at, config)
    assert canonical.block_id == v002.block_id


def test_same_direction_fvg_associates_and_opposite_does_not():
    frame, config, block, decision_at = bullish_fixture(pre=30, post=3)
    same = evaluate_v002_structural_pair(
        frame, StrategySide.LONG, decision_at, config,
        fvgs=fvgs(block.zone_low - 2.0, block.zone_low + 2.0),
    )
    assert same.fvg_associated is True
    assert same.fvg_direction == "bullish"
    assert same.structurally_active
    opposite = evaluate_v002_structural_pair(
        frame, StrategySide.LONG, decision_at, config,
        fvgs=fvgs(block.zone_high + 1.0, block.zone_high + 6.0, "bearish"),
    )
    assert opposite.fvg_associated is False
    assert opposite.state == V002_ACTIVE


def test_exact_overlap_true_and_false_pairs_both_accepted():
    frame, config, block, decision_at = bullish_fixture(pre=30, post=3)
    inside = evaluate_v002_structural_pair(
        frame, StrategySide.LONG, decision_at, config,
        fvgs=fvgs(block.zone_low + 1.0, block.zone_high - 1.0),
    )
    assert inside.fvg_associated is True
    assert inside.exact_overlap is True
    assert inside.structurally_active
    far_below = evaluate_v002_structural_pair(
        frame, StrategySide.LONG, decision_at, config,
        fvgs=fvgs(block.zone_low - 500.0, block.zone_low - 495.0),
    )
    assert far_below.fvg_associated is True
    assert far_below.exact_overlap is False
    assert far_below.structurally_active, "exact overlap is descriptive only; membership must not require it"


def test_first_retest_on_final_candle_is_retest_eligible():
    rows = build_rows(pre=30, post=0)
    zone_low, zone_high = zone_of(rows, 30)
    touch = candle(BASE + BAR * 32, zone_high + 2.0, zone_high + 3.0, zone_high - 1.5, zone_high + 1.0)
    frame = to_frame(rows + [touch])
    config = StrategyConfig()
    decision_at = BASE + BAR * 33
    v002 = evaluate_v002_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=())
    assert v002.state == V002_RETEST_ELIGIBLE
    assert v002.structurally_active
    assert v002.reason == "first_post_confirmation_retest"
    assert v002.age_bars == 1


def test_v002_gate11_architecture_frozen_2_1_2_1_2_threshold_8():
    frame, config, block, decision_at = bullish_fixture(pre=30, post=3)
    pair = evaluate_v002_structural_pair(
        frame, StrategySide.LONG, decision_at, config,
        fvgs=fvgs(block.zone_low - 2.0, block.zone_low + 2.0),
    )
    score = score_v002_setup(
        pair=pair, htf_bias="bullish", price_in_discount_or_premium=True, liquidity_swept=True,
    )
    assert score["max_score"] == 8
    assert score["min_score_to_trade"] == 8
    assert score["score"] == 8 and score["passes_threshold"] is True
    labels = [check["label"] for check in score["checks"]]
    assert labels == [
        "HTF bias aligns with trade direction",
        "Price located in premium/discount zone",
        V002_OB_LABEL,
        V002_FVG_LABEL,
        "Liquidity sweep occurred before entry",
    ]
    weights = [check["max_points"] for check in score["checks"]]
    assert weights == [2, 1, 2, 1, 2]
    text = repr(score)
    assert "exact" not in text.lower(), "V002 outputs must not label the FVG component as exact overlap"


def test_v002_gate11_below_threshold_without_pair():
    frame, config, _block, decision_at = bullish_fixture(pre=30, post=3)
    pair = evaluate_v002_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=())
    score = score_v002_setup(
        pair=pair, htf_bias="bullish", price_in_discount_or_premium=False, liquidity_swept=True,
    )
    assert score["score"] == 6
    assert score["passes_threshold"] is False


def test_gate11_still_requires_full_score_for_pass():
    frame, config, block, decision_at = bullish_fixture(pre=30, post=3)
    pair = evaluate_v002_structural_pair(
        frame, StrategySide.LONG, decision_at, config,
        fvgs=fvgs(block.zone_low - 2.0, block.zone_low + 2.0),
    )
    score7 = score_v002_setup(
        pair=pair, htf_bias="bullish", price_in_discount_or_premium=False, liquidity_swept=True,
    )
    assert score7["score"] == 7
    assert score7["passes_threshold"] is False


def test_config_fingerprint_unchanged_by_v002():
    config = StrategyConfig()
    assert config.version == "phase6-strategy-v1"
    assert config.order_block_expiry_bars == 30
    assert config.confluence_threshold == 8
    assert config.order_block_displacement_atr == 1.5
    fingerprint = config.fingerprint()
    assert len(fingerprint) == 24
    int(fingerprint, 16)
    assert fingerprint == StrategyConfig().fingerprint()
    from bot.strategy import StrategyConfig as ExportedConfig

    assert ExportedConfig is StrategyConfig
