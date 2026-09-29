# -*- coding: utf-8 -*-
"""Synthetic invariant tests for the V003 structural-pair evaluator (H003).

No store access, no empirical data.  Proves the preregistered invariants of
``docs/PHASE8_V2_VARIANT_V003.md``:
- V002 baseline preservation (exact equivalence when final FVG is present);
- Temporal FVG evidence memory (all 10 required scenarios);
- Score invariance (2/1/2/1/2, max 8, threshold 8/8);
- Strict live-zone separation (historical filled zone never becomes live zone).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import pytest

from bot.strategy.config import StrategyConfig
from bot.strategy.models import StrategySide
from bot.strategy.variant_v002 import (
    evaluate_v002_structural_pair,
    score_v002_setup,
)
from bot.strategy.variant_v003 import (
    SPEC_SHA256,
    V003_ACTIVE,
    V003_FVG_LABEL,
    V003_OB_LABEL,
    V003_RETEST_ELIGIBLE,
    V003VariantError,
    evaluate_v003_structural_pair,
    score_v003_setup,
)

UTC = timezone.utc
BASE = datetime(2024, 5, 1, 9, 0, tzinfo=UTC)
BAR = timedelta(minutes=5)


def candle(open_time: datetime, o: float, h: float, l: float, c: float) -> dict[str, Any]:
    return {
        "open_time": open_time.isoformat(),
        "available_at": (open_time + BAR).isoformat(),
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
    }


def make_bullish_ob_with_temporal_fvg(
    post_count: int = 5,
    fill_fvg: bool = True,
) -> tuple[pd.DataFrame, datetime, StrategyConfig]:
    """Active bullish OB confirmed at candle 16 with a bullish FVG at offset +1."""
    rows = [candle(BASE + BAR * i, 2400.0, 2402.0, 2398.0, 2400.0) for i in range(15)]
    # Candle 15 (candidate): zone [2390.0, 2401.0]
    rows.append(candle(BASE + BAR * 15, 2400.0, 2401.0, 2390.0, 2391.0))
    # Candle 16 (confirmation + FVG displacement): body = 21.0
    rows.append(candle(BASE + BAR * 16, 2391.0, 2413.0, 2389.0, 2412.0))
    # Candle 17 (FVG completion candle): low = 2410.0 > candidate high (2401.0)
    rows.append(candle(BASE + BAR * 17, 2412.0, 2415.0, 2410.0, 2414.0))

    if fill_fvg:
        # Candle 18: retraces to fill the FVG at 2405.0 (<= 2410.0), stays safely above OB zone (2401.0)
        rows.append(candle(BASE + BAR * 18, 2414.0, 2415.0, 2405.0, 2412.0))
        post_start = 19
    else:
        post_start = 18

    for i in range(post_start, post_start + post_count):
        rows.append(candle(BASE + BAR * i, 2412.0, 2415.0, 2408.0, 2412.0))

    frame = pd.DataFrame(rows)
    for col in ("open_time", "available_at"):
        frame[col] = pd.to_datetime(frame[col], utc=True)
    decision_at = pd.Timestamp(frame["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)
    return frame, decision_at, StrategyConfig()


def make_bearish_ob_with_temporal_fvg(
    post_count: int = 5,
    fill_fvg: bool = True,
) -> tuple[pd.DataFrame, datetime, StrategyConfig]:
    """Active bearish OB confirmed at candle 16 with a bearish FVG at offset +1."""
    rows = [candle(BASE + BAR * i, 2400.0, 2402.0, 2398.0, 2400.0) for i in range(15)]
    # Candle 15 (candidate): bullish candle, zone [2399.0, 2410.0]
    rows.append(candle(BASE + BAR * 15, 2400.0, 2410.0, 2399.0, 2409.0))
    # Candle 16 (confirmation + FVG displacement): bearish displacement breaking below 2399.0
    rows.append(candle(BASE + BAR * 16, 2409.0, 2411.0, 2385.0, 2386.0))
    # Candle 17 (FVG completion candle): high = 2390.0 < candidate low (2399.0)
    rows.append(candle(BASE + BAR * 17, 2386.0, 2390.0, 2384.0, 2385.0))

    if fill_fvg:
        # Candle 18: retraces up to fill the FVG at 2395.0 (>= 2390.0), stays safely below OB zone (2399.0)
        rows.append(candle(BASE + BAR * 18, 2385.0, 2395.0, 2384.0, 2388.0))
        post_start = 19
    else:
        post_start = 18

    for i in range(post_start, post_start + post_count):
        rows.append(candle(BASE + BAR * i, 2388.0, 2392.0, 2385.0, 2388.0))

    frame = pd.DataFrame(rows)
    for col in ("open_time", "available_at"):
        frame[col] = pd.to_datetime(frame[col], utc=True)
    decision_at = pd.Timestamp(frame["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)
    return frame, decision_at, StrategyConfig()


# ===========================================================================
# Section 35: Required V002 Baseline Preservation Tests
# ===========================================================================


def test_v002_baseline_equivalence_with_final_fvg():
    """When a final same-direction FVG exists on the final surface, V003 must be
    bit-for-bit / behaviorally identical to V002."""
    frame, decision_at, config = make_bullish_ob_with_temporal_fvg(post_count=5, fill_fvg=False)

    # Provide a final canonical FVG matching V002 format
    final_fvgs = [
        {"direction": "bullish", "top": 2420.0, "bottom": 2410.0, "timeframe": "M5"}
    ]

    res_v002 = evaluate_v002_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=final_fvgs
    )
    res_v003 = evaluate_v003_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=final_fvgs
    )

    assert res_v003.state == res_v002.state == V003_ACTIVE
    assert res_v003.reason == res_v002.reason
    assert res_v003.structurally_active == res_v002.structurally_active is True
    assert res_v003.block_id == res_v002.block_id
    assert res_v003.zone_low == res_v002.zone_low
    assert res_v003.zone_high == res_v002.zone_high
    assert res_v003.age_bars == res_v002.age_bars
    assert res_v003.final_fvg_associated == res_v002.fvg_associated is True
    assert res_v003.v003_fvg_evidence is True
    assert res_v003.fvg_evidence_source == "FINAL_SURFACE"
    assert res_v003.live_fvg_top == res_v002.fvg_top == 2420.0
    assert res_v003.live_fvg_bottom == res_v002.fvg_bottom == 2410.0
    assert res_v003.exact_overlap == res_v002.exact_overlap

    # Gate-11 score equivalence
    score_v2 = score_v002_setup(
        pair=res_v002, htf_bias="bullish", price_in_discount_or_premium=True, liquidity_swept=True
    )
    score_v3 = score_v003_setup(
        pair=res_v003, htf_bias="bullish", price_in_discount_or_premium=True, liquidity_swept=True
    )
    assert score_v3["score"] == score_v2["score"] == 8
    assert score_v3["passes_threshold"] == score_v2["passes_threshold"] is True
    assert score_v3["grade"] == score_v2["grade"] == "A+"


# ===========================================================================
# Section 36: Required Temporal-Memory Tests (10 minimum scenarios)
# ===========================================================================


def test_scenario_1_bullish_temporal_fvg_one_bar_after_ob_filled_before_decision():
    """Scenario 1: Active bullish OB + no final FVG + bullish FVG forms one bar
    after OB + filled before decision:
    - temporal evidence True
    - v003 FVG evidence True
    - live FVG zone None
    - temporal offset = 1 bar."""
    frame, decision_at, config = make_bullish_ob_with_temporal_fvg(post_count=5, fill_fvg=True)

    # Empty final FVG surface (the FVG filled so it is absent from final surface)
    final_fvgs = []

    res = evaluate_v003_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=final_fvgs
    )
    assert res.structurally_active is True
    assert res.final_fvg_associated is False
    assert res.temporal_fvg_evidence is True
    assert res.v003_fvg_evidence is True
    assert res.fvg_evidence_source == "TEMPORAL_MEMORY"
    assert res.live_fvg_top is None
    assert res.live_fvg_bottom is None
    assert res.temporal_fvg_offset_bars == 1
    assert res.fvg_direction == "bullish"


def test_scenario_2_bearish_temporal_fvg_short_equivalent():
    """Scenario 2: Active bearish OB + no final FVG + bearish FVG forms after OB
    + filled before decision: SHORT equivalent."""
    frame, decision_at, config = make_bearish_ob_with_temporal_fvg(post_count=5, fill_fvg=True)

    final_fvgs = []
    res = evaluate_v003_structural_pair(
        frame, StrategySide.SHORT, decision_at, config, fvgs=final_fvgs
    )
    assert res.structurally_active is True
    assert res.final_fvg_associated is False
    assert res.temporal_fvg_evidence is True
    assert res.v003_fvg_evidence is True
    assert res.fvg_evidence_source == "TEMPORAL_MEMORY"
    assert res.live_fvg_top is None
    assert res.live_fvg_bottom is None
    assert res.temporal_fvg_offset_bars == 1
    assert res.fvg_direction == "bearish"


def test_scenario_3_fvg_formed_at_ob_confirmation():
    """Scenario 3: Same-direction FVG formed AT OB confirmation (offset = 0):
    - temporal evidence True, offset = 0 bars."""
    rows = [candle(BASE + BAR * i, 2390.0, 2391.0, 2389.0, 2390.0) for i in range(14)]
    rows.append(candle(BASE + BAR * 14, 2390.0, 2391.0, 2389.0, 2390.0))
    # Candle 15: c2 & OB candidate: open 2406, high 2407, low 2389, close 2390
    rows.append(candle(BASE + BAR * 15, 2406.0, 2407.0, 2389.0, 2390.0))
    # Candle 16: c3 & OB confirmation: open 2392, high 2420, low 2392, close 2419
    rows.append(candle(BASE + BAR * 16, 2392.0, 2420.0, 2392.0, 2419.0))
    for i in range(17, 21):
        rows.append(candle(BASE + BAR * i, 2419.0, 2422.0, 2410.0, 2418.0))

    frame = pd.DataFrame(rows)
    for col in ("open_time", "available_at"):
        frame[col] = pd.to_datetime(frame[col], utc=True)
    decision_at = pd.Timestamp(frame["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)

    config = StrategyConfig()
    res = evaluate_v003_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=[]
    )
    assert res.structurally_active is True
    assert res.temporal_fvg_evidence is True
    assert res.v003_fvg_evidence is True
    assert res.temporal_fvg_offset_bars == 0


def test_scenario_4_fvg_formed_before_ob_only():
    """Scenario 4: Same-direction FVG formed BEFORE OB only:
    - temporal evidence False when no final surface FVG exists."""
    rows = [candle(BASE + BAR * i, 2400.0, 2405.0, 2395.0, 2400.0) for i in range(14)]
    # Early FVG completed at candle 15 (c1=13, c2=14, c3=15)
    rows.append(candle(BASE + BAR * 14, 2400.0, 2421.0, 2399.0, 2420.0))
    rows.append(candle(BASE + BAR * 15, 2420.0, 2422.0, 2408.0, 2421.0))
    # OB candidate at candle 16: open 2421, close 2415, high 2422, low 2410 (zone [2410, 2422])
    rows.append(candle(BASE + BAR * 16, 2421.0, 2422.0, 2410.0, 2415.0))
    # OB confirmation at candle 17: body = 14 >= 1.0*atr, < 1.5*atr
    rows.append(candle(BASE + BAR * 17, 2415.0, 2430.0, 2414.0, 2429.0))
    for i in range(18, 25):
        rows.append(candle(BASE + BAR * i, 2429.0, 2432.0, 2426.0, 2430.0))

    frame = pd.DataFrame(rows)
    for col in ("open_time", "available_at"):
        frame[col] = pd.to_datetime(frame[col], utc=True)
    decision_at = pd.Timestamp(frame["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)

    config = StrategyConfig(order_block_displacement_atr=1.0)
    res = evaluate_v003_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=[]
    )
    assert res.structurally_active is True
    assert res.final_fvg_associated is False
    assert res.temporal_fvg_evidence is False
    assert res.v003_fvg_evidence is False
    assert res.fvg_evidence_source == "NONE"


def test_scenario_5_opposite_direction_post_ob_fvg():
    """Scenario 5: Opposite-direction post-OB FVG:
    - temporal evidence False."""
    # Build bullish OB (pre=15, candidate=15, confirmation=16)
    rows = [candle(BASE + BAR * i, 2400.0, 2405.0, 2395.0, 2400.0) for i in range(15)]
    rows.append(candle(BASE + BAR * 15, 2400.0, 2401.0, 2390.0, 2391.0))
    rows.append(candle(BASE + BAR * 16, 2391.0, 2404.0, 2390.0, 2403.5))
    # Post candles drifting at 2430
    for i in range(17, 22):
        rows.append(candle(BASE + BAR * i, 2430.0, 2432.0, 2428.0, 2430.0))
    # Inject a BEARISH FVG at index 23 (c1=21, c2=22, c3=23)
    rows.append(candle(BASE + BAR * 22, 2430.0, 2431.0, 2408.0, 2409.0))
    rows.append(candle(BASE + BAR * 23, 2409.0, 2415.0, 2405.0, 2408.0))
    for i in range(24, 27):
        rows.append(candle(BASE + BAR * i, 2408.0, 2412.0, 2405.0, 2408.0))

    frame = pd.DataFrame(rows)
    for col in ("open_time", "available_at"):
        frame[col] = pd.to_datetime(frame[col], utc=True)
    decision_at = pd.Timestamp(frame["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)

    config = StrategyConfig(order_block_displacement_atr=1.0)
    res = evaluate_v003_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=[]
    )
    assert res.temporal_fvg_evidence is False
    assert res.v003_fvg_evidence is False
    assert res.fvg_evidence_source == "NONE"


def test_scenario_6_post_decision_fvg_excluded():
    """Scenario 6: Post-decision FVG:
    - excluded from temporal evidence (causality check)."""
    frame, _, config = make_bullish_ob_with_temporal_fvg(post_count=5, fill_fvg=True)

    # Set decision_at BEFORE the FVG completed (candle 17 completion available_at)
    # Candle 16 confirmation available_at:
    decision_at = pd.Timestamp(frame["available_at"].iloc[16]).to_pydatetime().astimezone(UTC)

    res = evaluate_v003_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=[]
    )
    # The FVG completed at candle 17, which is post-decision, so excluded!
    assert res.temporal_fvg_evidence is False
    assert res.v003_fvg_evidence is False


def test_scenario_7_final_fvg_present_overrides_temporal():
    """Scenario 7: Final same-direction V002 FVG present:
    - final branch wins, exact V002 equivalence."""
    frame, decision_at, config = make_bullish_ob_with_temporal_fvg(post_count=5, fill_fvg=True)

    final_fvgs = [
        {"direction": "bullish", "top": 2450.0, "bottom": 2445.0, "timeframe": "M5"}
    ]

    res = evaluate_v003_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=final_fvgs
    )
    assert res.final_fvg_associated is True
    assert res.v003_fvg_evidence is True
    assert res.fvg_evidence_source == "FINAL_SURFACE"
    assert res.live_fvg_top == 2450.0
    assert res.live_fvg_bottom == 2445.0


def test_scenario_8_filled_temporal_fvg_never_becomes_live_zone():
    """Scenario 8: Filled temporal FVG:
    - evidence True, but live_fvg_top and live_fvg_bottom MUST remain None."""
    frame, decision_at, config = make_bullish_ob_with_temporal_fvg(post_count=5, fill_fvg=True)

    res = evaluate_v003_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=[]
    )
    assert res.temporal_fvg_evidence is True
    assert res.v003_fvg_evidence is True
    assert res.live_fvg_top is None
    assert res.live_fvg_bottom is None


def test_scenario_9_multiple_qualifying_temporal_fvgs():
    """Scenario 9: Multiple qualifying temporal FVGs:
    - evidence boolean is deterministic;
    - descriptive selection picks the earliest by formation timestamp."""
    frame, decision_at, config = make_bullish_ob_with_temporal_fvg(post_count=15, fill_fvg=True)
    # Inject second FVG at candle 22 (c1=20, c2=21, c3=22)
    rows = list(frame.to_dict("records"))
    t21 = pd.Timestamp(rows[21]["open_time"]).to_pydatetime()
    t22 = pd.Timestamp(rows[22]["open_time"]).to_pydatetime()
    # Large upward displacement at 21
    rows[21] = candle(t21, 2412.0, 2435.0, 2411.0, 2434.0)
    # Candle 22 low strictly above candle 20 high (2415.0)
    rows[22] = candle(t22, 2434.0, 2438.0, 2425.0, 2436.0)

    frame_multi = pd.DataFrame(rows)
    for col in ("open_time", "available_at"):
        frame_multi[col] = pd.to_datetime(frame_multi[col], utc=True)
    dec_at = pd.Timestamp(frame_multi["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)

    res = evaluate_v003_structural_pair(
        frame_multi, StrategySide.LONG, dec_at, config, fvgs=[]
    )
    assert res.temporal_fvg_evidence is True
    assert res.temporal_fvg_count >= 2
    # Selected descriptive offset is the earliest (offset 1)
    assert res.temporal_fvg_offset_bars == 1


def test_scenario_10_large_offset_temporal_fvg_qualifies():
    """Scenario 10: +87-bar temporal FVG:
    - qualifies under ordering-only semantics; proves no hidden lag threshold."""
    rows = [candle(BASE + BAR * i, 2400.0, 2405.0, 2395.0, 2400.0) for i in range(15)]
    # Candle 15: candidate: open 2400, high 2401, low 2390, close 2391 (zone [2390, 2401])
    rows.append(candle(BASE + BAR * 15, 2400.0, 2401.0, 2390.0, 2391.0))
    # Candle 16: confirmation: open 2391, close 2403.5. Body = 12.5 (>= 1.0*atr, < 1.5*atr)
    rows.append(candle(BASE + BAR * 16, 2391.0, 2404.0, 2390.0, 2403.5))

    # Candles 17..100: flat candles drifting around 2404
    for i in range(17, 101):
        rows.append(candle(BASE + BAR * i, 2403.5, 2406.0, 2402.0, 2404.0))

    # Candle 101: c1 for FVG: high = 2405.0
    rows.append(candle(BASE + BAR * 101, 2404.0, 2405.0, 2402.0, 2404.0))
    # Candle 102: c2 displacement candle: open 2404, close 2435, high 2436, low 2403
    rows.append(candle(BASE + BAR * 102, 2404.0, 2436.0, 2403.0, 2435.0))
    # Candle 103: c3 completion candle: open 2435, close 2436, low 2415, high 2438 (low 2415 > 2405)
    rows.append(candle(BASE + BAR * 103, 2435.0, 2438.0, 2415.0, 2436.0))
    # Candle 104: fills FVG (low 2404 <= 2415, stays above OB 2401)
    rows.append(candle(BASE + BAR * 104, 2436.0, 2436.0, 2404.0, 2410.0))

    frame = pd.DataFrame(rows)
    for col in ("open_time", "available_at"):
        frame[col] = pd.to_datetime(frame[col], utc=True)
    decision_at = pd.Timestamp(frame["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)

    config = StrategyConfig(order_block_displacement_atr=1.0)
    res = evaluate_v003_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=[]
    )
    assert res.structurally_active is True
    assert res.temporal_fvg_evidence is True
    assert res.v003_fvg_evidence is True
    assert res.temporal_fvg_count == 1
    assert res.temporal_fvg_offset_bars == 87


# ===========================================================================
# Section 40: Required Score Test
# ===========================================================================


def test_v003_confluence_score_architecture():
    """V003 score architecture must preserve 2/1/2/1/2 weights, max 8, threshold 8.
    Temporal evidence satisfies only the 1-point FVG component."""
    frame, decision_at, config = make_bullish_ob_with_temporal_fvg(post_count=5, fill_fvg=True)

    res_temporal = evaluate_v003_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=[]
    )
    assert res_temporal.v003_fvg_evidence is True

    # 1. Full 8/8 pass
    score_full = score_v003_setup(
        pair=res_temporal, htf_bias="bullish", price_in_discount_or_premium=True, liquidity_swept=True
    )
    assert score_full["score"] == 8
    assert score_full["max_score"] == 8
    assert score_full["passes_threshold"] is True
    assert score_full["grade"] == "A+"

    # Check individual check points
    checks = {c["label"]: c["points"] for c in score_full["checks"]}
    assert checks["HTF bias aligns with trade direction"] == 2
    assert checks["Price located in premium/discount zone"] == 1
    assert checks[V003_OB_LABEL] == 2
    assert checks[V003_FVG_LABEL] == 1
    assert checks["Liquidity sweep occurred before entry"] == 2

    # 2. When FVG evidence is missing (e.g. no temporal or final FVG), score is 7/8 and FAILS threshold 8
    # Create pair with no FVG
    rows_no_fvg = [candle(BASE + BAR * i, 2400.0, 2405.0, 2395.0, 2400.0) for i in range(14)]
    rows_no_fvg.append(candle(BASE + BAR * 14, 2400.0, 2421.0, 2399.0, 2420.0))
    rows_no_fvg.append(candle(BASE + BAR * 15, 2420.0, 2422.0, 2408.0, 2421.0))
    rows_no_fvg.append(candle(BASE + BAR * 16, 2421.0, 2422.0, 2410.0, 2415.0))
    rows_no_fvg.append(candle(BASE + BAR * 17, 2415.0, 2430.0, 2414.0, 2429.0))
    for i in range(18, 25):
        rows_no_fvg.append(candle(BASE + BAR * i, 2429.0, 2432.0, 2426.0, 2430.0))
    frame_no_fvg = pd.DataFrame(rows_no_fvg)
    for col in ("open_time", "available_at"):
        frame_no_fvg[col] = pd.to_datetime(frame_no_fvg[col], utc=True)
    dec_no_fvg = pd.Timestamp(frame_no_fvg["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)

    res_no_fvg = evaluate_v003_structural_pair(
        frame_no_fvg, StrategySide.LONG, dec_no_fvg, StrategyConfig(order_block_displacement_atr=1.0), fvgs=[]
    )
    assert res_no_fvg.v003_fvg_evidence is False

    score_no_fvg = score_v003_setup(
        pair=res_no_fvg, htf_bias="bullish", price_in_discount_or_premium=True, liquidity_swept=True
    )
    assert score_no_fvg["score"] == 7
    assert score_no_fvg["passes_threshold"] is False
    assert score_no_fvg["grade"] == "SKIP"

    # 3. Unresolved bias fails closed
    with pytest.raises(V003VariantError, match="requires a resolved HTF bias"):
        score_v003_setup(
            pair=res_temporal, htf_bias="neutral", price_in_discount_or_premium=True, liquidity_swept=True
        )
