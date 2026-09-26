# -*- coding: utf-8 -*-
"""Synthetic tests for the frozen D005 diagnostic tooling (H003).

No store access, no empirical data, no Fold-01 read.  Proves the
preregistered D005 surfaces of ``docs/PHASE8_V2_DIAGNOSTIC_D005.md``: the
primary population, the causal FVG history, the final-surface reconciliation,
the temporal universe, the ordering-only H003 rule, the exhaustive attrition
categories, the distance surface and the fail-closed guards.  Reuses the
proven V002/D001 synthetic fixtures; no expected empirical count is encoded.

D005-TC001 (causal formation clock): FVG formation is timestamped with the
COMPLETION candle's ``available_at`` (``fvg_formation_available_at``), the
same causal clock as the canonical OB ``confirmed_at``; the completion
candle's ``open_time`` is descriptive metadata only
(``fvg_completion_open_time``).  Same-candle / next-candle / previous-candle
regressions pin the boundary semantics and the frozen 81c6a6f tooling is
proven defective in-process.

D005-TC002 (post-exposure measurement correction): the reference partition
is the four-cell contingency over (structurally_active, fvg_associated)
built from individual frozen V002 observations — the aggregate marginals are
reconciliation totals only and are never subtracted
(``fvg_associated`` is NOT a subset of ``structurally_active``); D005
decision IDs must equal the primary decision-ID set exactly; and the CLI
performs a structured pre-open boundary check that never misreads hash
fragments (``4068``/``3525``) in the authorized store basename as years.
No empirical Fold-01 value is encoded anywhere in this file.
"""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys_path_done = True  # noqa: F401  (pytest conftest handles sys.path)

from backtests import phase8_v2_diagnostic_d005 as d005
from backtests import phase8_v2_variant_v002_eval as v002_eval
from bot.strategy.config import StrategyConfig
from bot.strategy.models import StrategySide
from bot.strategy.variant_v002 import evaluate_v002_structural_pair
from tests.test_phase8_v2_v002_variant import build_rows, to_frame

UTC = timezone.utc
AT = datetime(2024, 5, 1, 11, 50, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Reusable synthetic observation/decision fixtures (proven V002 patterns)
# ---------------------------------------------------------------------------


def _observation(**overrides):
    base = {
        "decision_id": "decision-1",
        "available_at_ms": int(AT.timestamp() * 1000),
        "v002_pair_state": "ACTIVE",
        "v002_pair_reason": "structurally_active_block",
        "v002_structurally_active": True,
        "v002_side": "LONG",
        "v002_age_bars": 3,
        "v002_block_id": "blk",
        "v002_fvg_associated": False,
        "v002_fvg_direction": None,
        "v002_exact_overlap_descriptive": None,
        "v002_gate11_passed": False,
        "v002_strategy_eligible": False,
        "v002_entry_ready": False,
        "legacy_score_passed": False,
    }
    base.update(overrides)
    return base


class _Table:
    def __init__(self, rows):
        self._rows = rows

    def column(self, name):
        from tests.test_phase8_v2_d001_tooling import _Snapshot

        if name == "available_at_ms":
            return [int(row.available_at_ms) for row in self._rows]
        return [getattr(row, name) for row in self._rows]

    def __len__(self):
        return len(self._rows)


class _SnapView:
    def __init__(self, payload, at: datetime, decision_id: str = "decision-1"):
        self.available_at_ms = int(at.timestamp() * 1000)
        self.gate_payload = json.dumps(payload)
        self.decision_id = decision_id


def _decision_payload(
    frame: pd.DataFrame,
    *,
    htf_bias: str = "bullish",
    persisted_fvgs=None,
    zone=(2390.0, 2399.0),
    confirmed_at: str | None = None,
):
    rows = [
        {
            "open_time": stamp.isoformat(),
            "available_at": (stamp + timedelta(minutes=5)).isoformat(),
            "open": float(row["open"]), "high": float(row["high"]),
            "low": float(row["low"]), "close": float(row["close"]),
        }
        for stamp, row in zip(frame["open_time"], frame.to_dict("records"))
    ]
    ob_context = {}
    if zone is not None:
        ob_context = {
            "valid": False, "reason": "legacy_detector_no_block", "type": "order_block",
            "zone": list(zone), "distance_atr": 1.0, "mitigated": False,
            "in_pd_zone": True, "fresh": False,
            "confirmed_at": confirmed_at,
        }
    return {
        "schema": "phase8_v2_gate_inputs_v1",
        "profile": {}, "htf_bias": htf_bias,
        "bias_snapshot": {}, "bias_resolution": {"direction": htf_bias},
        "liquidity_context": {
            "structure_context": {
                "structure": htf_bias, "state": "confirmed",
                "discount_zone": (2380.0, 2395.0),
            },
            "liquidity_pools": [],
        },
        "liquidity_signal": {"side": "sell", "type": "equal_lows"},
        "displacement": {"valid": True, "fvg": (2391.0, 2393.0)},
        "fvgs": persisted_fvgs if persisted_fvgs is not None else [],
        "internal_structure": {"event": "BOS"},
        "ob_result": ob_context,
        "atr": 1.0,
        "structure_len": len(rows), "entry_rows": rows,
        "sources": [], "profile_version": "synthetic",
        "news_context": {"news_clear": True},
        "session_context": {"session_allowed": True, "active_session": "london"},
        "dxy_context": {"available": True, "dxy_bias": "bearish" if htf_bias == "bullish" else "bullish"},
    }


def _bullish_frame(pre: int = 30, post: int = 3) -> pd.DataFrame:
    """The proven V002 synthetic bullish displacement fixture."""
    return to_frame(build_rows(pre=pre, post=post))


def _decision_at(frame: pd.DataFrame) -> datetime:
    return pd.Timestamp(frame["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)


def _at_for(frame: pd.DataFrame) -> datetime:
    return _decision_at(frame)


def _zone_of(frame: pd.DataFrame, pre: int) -> tuple[float, float]:
    from tests.test_phase8_v2_v002_variant import zone_of

    rows_low = float(frame["low"].iloc[pre])
    rows_high = float(frame["high"].iloc[pre])
    return rows_low, rows_high


# ---------------------------------------------------------------------------
# §32 cases 1-6: attrition categories through the REAL canonical detector
# ---------------------------------------------------------------------------


def _primary_observation(frame, *, persisted_fvgs=None, zone=None, decision_id="decision-1"):
    pre = 30
    config = StrategyConfig()
    from bot.strategy.order_blocks import detect_order_blocks

    blocks = [b for b in detect_order_blocks(frame, config) if b.side is StrategySide.LONG]
    block = sorted(blocks, key=lambda b: (b.confirmed_at, -b.zone_high + b.zone_low, b.block_id))[-1]
    payload = _decision_payload(
        frame,
        persisted_fvgs=persisted_fvgs if persisted_fvgs is not None else [],
        zone=zone if zone is not None else (block.zone_low, block.zone_high),
    )
    snapshot = _SnapView(payload, _at_for(frame), decision_id)
    observation = _observation(
        decision_id=decision_id,
        available_at_ms=int(_at_for(frame).timestamp() * 1000),
        v002_block_id=block.block_id,
    )
    return observation, snapshot, config


def test_case_1_active_ob_no_fvg_ever():
    # The base fixture's post-confirmation candle lifted to exactly the block
    # zone top: the frozen gap predicate (c1.high < c3.low) no longer fires,
    # and the candle is the FIRST retest on the FINAL available candle, so
    # V002 reports RETEST_ELIGIBLE (structurally_active).  No FVG exists.
    frame = to_frame(build_rows(pre=30, post=1))
    frame.iloc[32, frame.columns.get_loc("low")] = 2401.0
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    assert record["attrition_category"] == "NO_SAME_DIRECTION_FVG_EVER"
    assert record["h003_temporal_association"] is False
    assert record["causal_fvg_count_total"] == 0
    assert record["causal_fvg_count_same_direction"] == 0
    assert record["final_surface_reconciled"] is True


def test_case_2_active_ob_same_direction_fvg_after_ob_is_h003_temporal():
    # The base fixture inherently contains a same-direction bullish FVG whose
    # formation candle opens after the OB confirmation (verified: source
    # index 31, filled within the causal window).
    frame = _bullish_frame()
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    assert record["causal_fvg_count_same_direction"] >= 1
    assert record["h003_temporal_association"] is True
    assert record["attrition_category"] == "SAME_DIRECTION_FVG_EXISTED_BUT_FILLED"
    assert record["temporal_distance_signed_bars"]
    assert all(distance >= 0 for distance in record["temporal_distance_signed_bars"])


def test_case_3_active_ob_same_direction_fvg_before_ob_only():
    # Kill the base fixture's post-OB FVG (boundary retest candle) and build
    # a PRE-OB same-direction FVG with valid OHLC past the ATR warm-up:
    # c1 = row 19 (high 2400.0), c2 = row 20 (displacement body 7.9 >=
    # 1.5 * ATR ~ 6), c3 = row 21 (low 2407.2 > c1.high 2400.0 -> bullish
    # gap, verified source_index 20), row 22 fills the zone so it stays out
    # of the persisted final surface.  Blocks @20 and @31 both exist; the
    # selection ordering keeps the rows-30/31 block (retest on the final
    # candle) as the observed one.
    frame = to_frame(build_rows(pre=30, post=1))
    frame.iloc[32, frame.columns.get_loc("low")] = 2401.0
    for column, value in (
        ("open", 2399.8), ("high", 2400.0), ("low", 2399.4), ("close", 2399.6),
    ):
        frame.iloc[19, frame.columns.get_loc(column)] = value
    for column, value in (
        ("open", 2399.6), ("high", 2408.0), ("low", 2399.2), ("close", 2407.5),
    ):
        frame.iloc[20, frame.columns.get_loc(column)] = value
    for column, value in (
        ("open", 2407.5), ("high", 2408.2), ("low", 2407.2), ("close", 2408.0),
    ):
        frame.iloc[21, frame.columns.get_loc(column)] = value
    for column, value in (
        ("open", 2408.0), ("high", 2408.5), ("low", 2407.0), ("close", 2408.2),
    ):
        frame.iloc[22, frame.columns.get_loc(column)] = value
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    same = [
        universe for universe in record["temporal_fvg_universe"]
        if universe["fvg_direction"] == "bullish"
    ]
    assert same and all(
        universe["formation_order_relative_to_ob"] == "BEFORE_OB_CONFIRMATION"
        for universe in same
    )
    assert record["h003_temporal_association"] is False
    assert record["attrition_category"] == "SAME_DIRECTION_FVG_PRE_OB_ONLY"


def test_case_4_active_ob_same_direction_fvg_formed_then_filled():
    # Primary-population decisions with a post-OB same-direction FVG
    # necessarily have it filled before the decision (an unfilled one would
    # be a member of the persisted final surface): the fill state is
    # descriptive and must be reported as filled in the universe record.
    frame = _bullish_frame()
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    assert record["h003_temporal_association"] is True
    assert record["attrition_category"] == "SAME_DIRECTION_FVG_EXISTED_BUT_FILLED"
    qualifying = record["temporal_distance_records"]
    assert qualifying and all(
        universe["filled_before_decision"] is True
        and universe["unfilled_at_decision"] is False
        for universe in qualifying
    )


def test_case_5_reference_case_final_unfilled_same_direction_fvg_is_not_primary():
    # post=1 with the post-confirmation candle lifted clear of the zone: the
    # bullish FVG (rows 30-32) has no later candle, so it is UNFILLED and
    # joins the persisted final surface.  V002 reports fvg_associated=True:
    # NOT primary population — the observer refuses it (reference R1) AFTER
    # the final-surface reconciliation succeeds.
    # post=1 with the post-confirmation candle lifted clear of the gap zone
    # (low 2404.5 > top 2404.0): the bullish FVG (rows 30-32) has no later
    # touching candle, so it is UNFILLED and joins the persisted final
    # surface.
    frame = to_frame(build_rows(pre=30, post=1))
    frame.iloc[32, frame.columns.get_loc("low")] = 2404.5
    from bot.analysis import get_unfilled_fvgs

    final = get_unfilled_fvgs(frame, timeframe="M5", direction="bullish")
    assert final, "fixture must produce an unfilled bullish FVG"
    observation, snapshot, config = _primary_observation(frame, persisted_fvgs=final)
    observation = _observation(
        v002_block_id=observation["v002_block_id"], v002_fvg_associated=True,
        available_at_ms=observation["available_at_ms"],
    )
    with pytest.raises(d005.ReconciliationError) as error:
        d005.observe_d005_decision(observation, snapshot, config=config)
    assert "R1" in str(error.value)


def test_case_6_opposite_direction_fvg_only():
    # A frame whose only detectable FVG is bearish while the side is LONG.
    frame = _bearish_fvg_only_frame()
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    assert record["causal_fvg_count_same_direction"] == 0
    assert record["causal_fvg_count_opposite_direction"] >= 1
    assert record["attrition_category"] == "OPPOSITE_DIRECTION_ONLY"
    assert record["h003_temporal_association"] is False


def _bearish_fvg_only_frame() -> pd.DataFrame:
    """Valid-OHLC frame whose only causal FVG is BEARISH (pre-OB, filled)
    while the selected block (rows 30/31) is bullish and untouched.  The
    base post-OB bullish FVG is killed by the boundary retest candle
    (row 32 low = 2401.0 = zone top, post=1 so it is the final candle);
    rows 19-22 (past the ATR warm-up) manufacture the bearish FVG:
    c1 = row 19 (low 2400.2), c2 = row 20 (downward displacement body 7.4
    vs ATR ~ 4), c3 = row 21 (high 2399.9 < c1.low 2400.2), row 22 fills
    the zone so it stays out of the persisted final surface."""
    frame = to_frame(build_rows(pre=30, post=1))
    frame.iloc[32, frame.columns.get_loc("low")] = 2401.0
    for column, value in (
        ("open", 2400.3), ("high", 2400.5), ("low", 2400.2), ("close", 2400.4),
    ):
        frame.iloc[19, frame.columns.get_loc(column)] = value
    for column, value in (
        ("open", 2400.4), ("high", 2400.6), ("low", 2392.8), ("close", 2393.0),
    ):
        frame.iloc[20, frame.columns.get_loc(column)] = value
    for column, value in (
        ("open", 2399.4), ("high", 2399.9), ("low", 2399.2), ("close", 2399.6),
    ):
        frame.iloc[21, frame.columns.get_loc(column)] = value
    for column, value in (
        ("open", 2399.8), ("high", 2400.9), ("low", 2399.5), ("close", 2400.6),
    ):
        frame.iloc[22, frame.columns.get_loc(column)] = value
    return frame


# ---------------------------------------------------------------------------
# §32 cases 7-9: sides and causality
# ---------------------------------------------------------------------------


def test_case_7_long_side_recorded():
    frame = _bullish_frame()
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    assert record["h003_side"] == "LONG"
    assert record["v002_block_id"] == observation["v002_block_id"]


def _same_candle_frame() -> pd.DataFrame:
    """TC001 same-candle fixture (verified against the real detectors):
    FVG c1=row29, c2=row30 (displacement), c3=row31 -> completion row 31
    whose ``available_at`` (11:40) EQUALS the block confirmation
    availability (row 31 -> confirmed_at 11:40).  True distance 0 bars; the
    completion candle's open_time (11:35) is one bar earlier — exactly the
    clock the frozen 81c6a6f tooling wrongly used."""
    frame = _bullish_frame()
    for index, (open_, high, low, close) in {
        28: (2400.0, 2401.0, 2398.0, 2399.0),
        29: (2400.0, 2401.0, 2398.0, 2399.0),
        30: (2405.0, 2405.0, 2388.0, 2390.0),
        31: (2404.0, 2421.0, 2403.0, 2420.0),
        32: (2406.0, 2408.0, 2402.0, 2406.0),
    }.items():
        for column, value in (("open", open_), ("high", high), ("low", low), ("close", close)):
            frame.iloc[index, frame.columns.get_loc(column)] = value
    return frame


def _prev_candle_frame() -> pd.DataFrame:
    """TC001 previous-candle fixture (verified against the real detectors):
    FVG c1=row28, c2=row29 (displacement), c3=row30 -> completion row 30
    whose ``available_at`` (11:35) is exactly ONE M5 candle BEFORE the block
    confirmation (row 31, confirmed_at 11:40).  True distance -1 bars."""
    frame = _bullish_frame()
    for index, (open_, high, low, close) in {
        29: (2402.0, 2413.0, 2401.0, 2412.0),
        30: (2414.0, 2414.0, 2405.0, 2411.0),
        31: (2404.0, 2421.0, 2403.0, 2420.0),
    }.items():
        for column, value in (("open", open_), ("high", high), ("low", low), ("close", close)):
            frame.iloc[index, frame.columns.get_loc(column)] = value
    return frame


def _mirror_frame(frame: pd.DataFrame, pivot: float = 4900.0) -> pd.DataFrame:
    """Reflect OHLC prices around ``pivot``: bullish structures become
    bearish with identical geometry, ATR and causality.  Reflection swaps
    the high/low columns (high' = pivot - low, low' = pivot - high) so the
    reflected frame keeps valid OHLC invariants."""
    mirrored = frame.copy()
    mirrored["open"] = pivot - frame["open"].astype(float)
    mirrored["close"] = pivot - frame["close"].astype(float)
    mirrored["high"] = pivot - frame["low"].astype(float)
    mirrored["low"] = pivot - frame["high"].astype(float)
    return mirrored


def test_case_8_short_side_end_to_end():
    # Bearish mirror of the TC001 same-candle fixture: a SHORT block whose
    # confirmation and the bearish FVG completion become causally available
    # on the SAME M5 candle (true distance 0), exercising the AT branch on
    # the SHORT side.
    from bot.strategy.order_blocks import detect_order_blocks

    frame = _mirror_frame(_same_candle_frame())
    config = StrategyConfig()
    blocks = [b for b in detect_order_blocks(frame, config) if b.side is StrategySide.SHORT]
    assert blocks, "mirrored fixture must produce a SHORT block"
    block = sorted(blocks, key=lambda b: (b.confirmed_at, -b.zone_high + b.zone_low, b.block_id))[-1]
    decision_at = pd.Timestamp(frame["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)
    from bot.analysis import get_unfilled_fvgs

    persisted = get_unfilled_fvgs(frame, timeframe="M5", direction="bearish")
    assert persisted == []
    payload = _decision_payload(
        frame, htf_bias="bearish", persisted_fvgs=persisted,
        zone=(block.zone_low, block.zone_high),
    )
    snapshot = _SnapView(payload, decision_at, "decision-short")
    observation = _observation(
        decision_id="decision-short", v002_side="SHORT", v002_block_id=block.block_id,
        available_at_ms=int(decision_at.timestamp() * 1000),
    )
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    assert record["h003_side"] == "SHORT"
    assert record["h003_temporal_association"] is True
    assert record["attrition_category"] == "SAME_DIRECTION_FVG_EXISTED_BUT_FILLED"
    assert 0 in record["temporal_distance_signed_bars"], (
        "the AT_OB_CONFIRMATION ordering branch must be exercised"
    )


# ---------------------------------------------------------------------------
# D005-TC001: causal formation clock (completion-candle available_at)
# ---------------------------------------------------------------------------


D005_TC001_DEFECTIVE_COMMIT = "81c6a6f53a0e456a800f2fdddc957e34c1dc9064"


def test_tc001_same_candle_regression_available_at_clock():
    # FVG completion causally available on the SAME M5 candle as the OB
    # confirmation: availability-to-availability distance MUST be 0 and the
    # order AT_OB_CONFIRMATION.  The frozen 81c6a6f tooling used the
    # completion candle's open_time and reported one bar early (proven in
    # test_tc001_old_bug_reproduction_same_candle_and_next_candle).
    frame = _same_candle_frame()
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    assert record["temporal_distance_signed_bars"] == [0]
    item = record["temporal_distance_records"][0]
    assert item["formation_order_relative_to_ob"] == "AT_OB_CONFIRMATION"
    assert item["signed_bar_distance"] == 0
    assert item["elapsed_minutes"] == 0.0
    assert item["fvg_formation_available_at"] == item["ob_confirmed_at"]
    assert pd.Timestamp(item["fvg_completion_open_time"]) < pd.Timestamp(
        item["fvg_formation_available_at"]
    )


def test_tc001_next_candle_regression():
    # FVG completion exactly one M5 candle AFTER the OB confirmation candle:
    # AFTER_OB_CONFIRMATION, distance +1, elapsed 5 minutes.  The base
    # fixture's FVG (source 31, completion row 32: open 11:40, available
    # 11:45; OB confirmed_at 11:40) is exactly this shape.
    frame = _bullish_frame()
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    assert record["temporal_distance_signed_bars"] == [1]
    item = record["temporal_distance_records"][0]
    assert item["formation_order_relative_to_ob"] == "AFTER_OB_CONFIRMATION"
    assert item["signed_bar_distance"] == 1
    assert item["elapsed_minutes"] == 5.0
    assert pd.Timestamp(item["fvg_completion_open_time"]) == pd.Timestamp(item["ob_confirmed_at"])
    assert pd.Timestamp(item["fvg_formation_available_at"]) == (
        pd.Timestamp(item["ob_confirmed_at"]) + timedelta(minutes=5)
    )


def test_tc001_prev_candle_regression():
    # FVG completion exactly one M5 candle BEFORE the OB confirmation:
    # BEFORE_OB_CONFIRMATION, distance -1, elapsed -5 minutes.  A pre-OB
    # same-direction FVG does NOT satisfy the H003 ordering rule, so it is
    # reported in the temporal universe (descriptive) and is correctly
    # absent from the qualifying distance surface.
    frame = _prev_candle_frame()
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    same = [
        item for item in record["temporal_fvg_universe"]
        if item["fvg_direction"] == "bullish"
    ]
    assert len(same) == 1
    item = same[0]
    assert item["formation_order_relative_to_ob"] == "BEFORE_OB_CONFIRMATION"
    assert item["signed_bar_distance"] == -1
    assert item["elapsed_minutes"] == -5.0
    assert pd.Timestamp(item["fvg_formation_available_at"]) == (
        pd.Timestamp(item["ob_confirmed_at"]) - timedelta(minutes=5)
    )
    assert record["h003_temporal_association"] is False
    assert record["temporal_distance_signed_bars"] == []
    assert record["attrition_category"] == "SAME_DIRECTION_FVG_PRE_OB_ONLY"


def test_tc001_formation_field_is_causal_availability_clock():
    # The formation field is the completion candle's available_at (the same
    # causal clock as the OB confirmed_at); the ambiguous old name
    # ``fvg_open_time`` is retired from the output entirely.
    frame = _bullish_frame()
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    for universe in record["temporal_fvg_universe"]:
        assert "fvg_formation_available_at" in universe
        assert "fvg_completion_open_time" in universe
        assert "fvg_open_time" not in universe
        completion_index = int(universe["source_index"]) + 1
        assert pd.Timestamp(universe["fvg_formation_available_at"]) == pd.Timestamp(
            frame["available_at"].iloc[completion_index]
        )
        assert pd.Timestamp(universe["fvg_completion_open_time"]) == pd.Timestamp(
            frame["open_time"].iloc[completion_index]
        )
        assert pd.Timestamp(universe["fvg_completion_open_time"]) < pd.Timestamp(
            universe["fvg_formation_available_at"]
        )


def test_tc001_open_time_is_descriptive_and_cannot_affect_membership():
    # (a) For ordinary M5 candles the completion open_time precedes the
    # formation available_at (proven on the fixture above).
    # (b) Structurally: NO consumer of the descriptive field exists — the
    # order category, signed distance and H003 membership are computed from
    # the formation available_at only, so mutating the open_time cannot move
    # any of them.
    kwargs = dict(
        zone={"direction": "bullish", "filled": True, "source_index": 31},
        fvg_formation_available_at=datetime(2024, 5, 1, 11, 45, tzinfo=UTC),
        block_confirmed_at=datetime(2024, 5, 1, 11, 40, tzinfo=UTC),
        decision_at=datetime(2024, 5, 1, 11, 50, tzinfo=UTC),
    )
    base_record = d005._fvg_universe_record(
        decision_id="d",
        fvg_completion_open_time=datetime(2024, 5, 1, 11, 40, tzinfo=UTC),
        **kwargs,
    )
    mutated = d005._fvg_universe_record(
        decision_id="d",
        fvg_completion_open_time=datetime(2034, 5, 1, 11, 40, tzinfo=UTC),
        **kwargs,
    )

    def _strip(record):
        return {k: v for k, v in record.items() if k != "fvg_completion_open_time"}

    assert _strip(base_record) == _strip(mutated)
    assert base_record["formation_order_relative_to_ob"] == "AFTER_OB_CONFIRMATION"
    assert base_record["signed_bar_distance"] == 1


def test_tc001_grid_invariant_and_no_manual_compensation():
    # The bar distance is the raw availability difference divided by 300 s
    # with the fail-closed grid invariant; there is no -1/+1 offset
    # anywhere.  The three boundary fixtures land exactly on 0 / +1 / -1.
    with pytest.raises(d005.D005Error) as error:
        d005._bar_distance(
            "d",
            datetime(2024, 5, 1, 11, 40, tzinfo=UTC),
            datetime(2024, 5, 1, 11, 40, tzinfo=UTC) + timedelta(seconds=150),
        )
    assert "M5 bar grid" in str(error.value)
    for frame, expected in (
        (_same_candle_frame(), [0]),
        (_bullish_frame(), [1]),
    ):
        observation, snapshot, config = _primary_observation(frame)
        record = d005.observe_d005_decision(observation, snapshot, config=config)
        assert record["temporal_distance_signed_bars"] == expected
    # The pre-OB fixture lands exactly on -1 in the descriptive universe
    # (it is not an H003-qualifying distance by the ordering rule).
    observation, snapshot, config = _primary_observation(_prev_candle_frame())
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    same = [
        item for item in record["temporal_fvg_universe"]
        if item["fvg_direction"] == "bullish"
    ]
    assert [item["signed_bar_distance"] for item in same] == [-1]


def _defective_d005_bytes() -> bytes:
    """Exact committed bytes of the frozen (defective) TC001-baseline D005
    tooling at 81c6a6f, snapshotted verbatim into the fixture tree; the
    opt-in byte-identity test guards the copy against drift."""
    return (Path(__file__).parent / "fixtures" / "d005_tooling_81c6a6f.py").read_bytes()


def _exec_defective_d005_module():
    source = _defective_d005_bytes()
    module_name = "_d005_tooling_defective_81c6a6f"
    assert module_name not in sys.modules
    module = types.ModuleType(module_name)
    module.__file__ = str(Path(__file__).parent / "fixtures" / "d005_tooling_81c6a6f.py")
    module.__dict__["__name__"] = module_name
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    sys.modules[module_name] = module
    return module


def test_tc001_old_bug_reproduction_same_candle_and_next_candle():
    """The frozen 81c6a6f tooling misclassifies both boundary cases — it
    timestamps FVG formation with the completion candle's open_time.  The
    defective bytes are executed in-process (no subprocess, no checkout).
    No empirical Fold-01 values are involved."""
    module = _exec_defective_d005_module()
    # Same-candle case: the corrected clock requires AT_OB_CONFIRMATION / 0
    # AND h003_temporal_association True; the defective tooling reports the
    # completion open_time (one bar early) -> BEFORE / -1 and flips the H003
    # membership decision to False.
    observation, snapshot, config = _primary_observation(_same_candle_frame())
    old_record = module.observe_d005_decision(observation, snapshot, config=config)
    old_universe = [
        u for u in old_record["temporal_fvg_universe"] if u["fvg_direction"] == "bullish"
    ][0]
    assert old_universe["formation_order_relative_to_ob"] == "BEFORE_OB_CONFIRMATION"
    assert old_universe["signed_bar_distance"] == -1
    assert old_record["h003_temporal_association"] is False
    assert "fvg_open_time" in old_universe
    assert "fvg_formation_available_at" not in old_universe
    # Next-candle case: the corrected clock requires AFTER_OB_CONFIRMATION /
    # +1; the defective tooling reports AT / 0.
    observation2, snapshot2, config2 = _primary_observation(_bullish_frame())
    old_next = module.observe_d005_decision(observation2, snapshot2, config=config2)
    old_next_item = old_next["temporal_distance_records"][0]
    assert old_next_item["formation_order_relative_to_ob"] == "AT_OB_CONFIRMATION"
    assert old_next_item["signed_bar_distance"] == 0


def test_tc001_defective_fixture_matches_committed_bytes():
    """Byte-identity of the defective-tooling fixture copy against the real
    committed blob at 81c6a6f (opt-in because the production check shells
    out to git, which the suite firewall forbids)."""
    import os
    import subprocess

    if os.environ.get("D005_TC001_VERIFY_COMMITTED_BYTES") != "1":
        pytest.skip(
            "subprocess git cat-file is prohibited inside the suite; run with "
            "D005_TC001_VERIFY_COMMITTED_BYTES=1 to byte-verify the fixture copy"
        )
    committed = subprocess.run(
        ["git", "cat-file", "blob",
         D005_TC001_DEFECTIVE_COMMIT + ":backtests/phase8_v2_diagnostic_d005.py"],
        cwd=".", capture_output=True, check=True,
    ).stdout
    assert committed == _defective_d005_bytes()


def test_case_9_post_decision_fvg_excluded_causally():
    # A non-causal trailing candle that would create an FVG must be excluded
    # from the causal frame entirely and counted, never inspected.  The edit
    # keeps valid OHLC (a tall candle far above the zone).
    base = _bullish_frame()
    frame = base.copy()
    last = frame.index[-1]
    for column, value in (
        ("open", 2421.0), ("high", 2425.0), ("low", 2420.0), ("close", 2422.0),
    ):
        frame.iloc[last, frame.columns.get_loc(column)] = value
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    # decision_at is the LAST row's availability, so nothing is excluded in
    # this shape; the would-be FVG (rows 31-33 geometry unchanged) is still
    # causal here — the strong exclusion proof is
    # test_post_decision_fvg_is_never_counted.
    assert record["non_causal_rows_excluded"] == 0
    assert record["causal_fvg_count_same_direction"] >= 1


def test_post_decision_fvg_is_never_counted():
    # Strong causality proof: observe with a decision time INSIDE the frame
    # (row 32's availability).  Rows 33+ are non-causal; the edited row 33
    # (valid OHLC, low 2420) would create a bullish FVG with c1 = row 31 if
    # it were inspected — it must be excluded and never counted.  The
    # persisted final surface is the EXACT causal recomputation (empty:
    # row 32 is the boundary retest candle that kills the base zone within
    # the causal window), so reconciliation holds.
    base = _bullish_frame()
    frame = base.copy()
    frame.iloc[32, frame.columns.get_loc("low")] = 2401.0
    for column, value in (
        ("open", 2421.0), ("high", 2425.0), ("low", 2420.0), ("close", 2422.0),
    ):
        frame.iloc[33, frame.columns.get_loc(column)] = value
    config = StrategyConfig()
    from bot.strategy.order_blocks import detect_order_blocks

    blocks = [b for b in detect_order_blocks(frame, config) if b.side is StrategySide.LONG]
    block = sorted(blocks, key=lambda b: (b.confirmed_at, -b.zone_high + b.zone_low, b.block_id))[-1]
    decision_at = pd.Timestamp(frame["available_at"].iloc[32]).to_pydatetime().astimezone(UTC)
    from bot.analysis import get_unfilled_fvgs

    causal_slice = frame.iloc[:33].reset_index(drop=True)
    persisted = get_unfilled_fvgs(causal_slice, timeframe="M5", direction="bullish")
    payload = _decision_payload(
        frame, persisted_fvgs=persisted, zone=(block.zone_low, block.zone_high),
    )
    snapshot = _SnapView(payload, decision_at, "decision-early")
    observation = _observation(
        decision_id="decision-early", v002_block_id=block.block_id,
        available_at_ms=int(decision_at.timestamp() * 1000),
    )
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    assert record["non_causal_rows_excluded"] >= 1
    assert all(
        pd.Timestamp(u["fvg_formation_available_at"]) <= pd.Timestamp(decision_at)
        for u in record["temporal_fvg_universe"]
    )
    assert not any(
        pd.Timestamp(u["fvg_formation_available_at"])
        == pd.Timestamp(frame["available_at"].iloc[33])
        for u in record["temporal_fvg_universe"]
    )


# ---------------------------------------------------------------------------
# §32 cases 10-11: reconciliation and distance arithmetic
# ---------------------------------------------------------------------------


def test_case_10_persisted_final_fvg_reconciliation_exact_match():
    # The persisted surface is EXACTLY the causal recomputation (the unfilled
    # rows-30..32 bullish zone): reconciliation succeeds, the decision is NOT
    # primary (fvg_associated=True) and the observer refuses it as R1 —
    # proving the reconciliation ran before the population gate.
    frame = to_frame(build_rows(pre=30, post=1))
    frame.iloc[32, frame.columns.get_loc("low")] = 2404.5
    from bot.analysis import get_unfilled_fvgs

    final = get_unfilled_fvgs(frame, timeframe="M5", direction="bullish")
    assert final, "fixture must produce an unfilled bullish FVG"
    observation, snapshot, config = _primary_observation(frame, persisted_fvgs=final)
    observation = _observation(
        v002_block_id=observation["v002_block_id"], v002_fvg_associated=True,
        available_at_ms=observation["available_at_ms"],
    )
    with pytest.raises(d005.ReconciliationError) as error:
        d005.observe_d005_decision(observation, snapshot, config=config)
    assert "R1" in str(error.value)


def test_final_surface_mismatch_fails_closed():
    frame = _bullish_frame()
    observation, snapshot, config = _primary_observation(
        frame,
        persisted_fvgs=[
            {"direction": "bullish", "top": 2407.0, "bottom": 2406.0,
             "filled": False, "timeframe": "M5", "source_index": 31},
        ],
    )
    with pytest.raises(d005.FinalSurfaceMismatch) as error:
        d005.observe_d005_decision(observation, snapshot, config=config)
    assert "reconcile" in str(error.value)


def test_case_11_exact_temporal_distance_arithmetic():
    base = _bullish_frame()
    frame = base.copy()
    frame.iloc[32, frame.columns.get_loc("low")] = 2405.0
    observation, snapshot, config = _primary_observation(frame)
    record = d005.observe_d005_decision(observation, snapshot, config=config)
    assert record["temporal_distance_records"]
    for universe in record["temporal_distance_records"]:
        signed = universe["signed_bar_distance"]
        assert universe["absolute_bar_distance"] == abs(signed)
        assert universe["elapsed_minutes"] == signed * 5.0
        assert universe["formation_order_relative_to_ob"] == (
            "AFTER_OB_CONFIRMATION" if signed > 0 else
            "BEFORE_OB_CONFIRMATION" if signed < 0 else "AT_OB_CONFIRMATION"
        )


# ---------------------------------------------------------------------------
# §32 cases 12-14: fail-closed guards
# ---------------------------------------------------------------------------


def test_case_12_malformed_timestamp_fails_closed():
    frame = _bullish_frame()
    observation, snapshot, config = _primary_observation(frame)
    payload = json.loads(snapshot.gate_payload)
    payload["entry_rows"][3]["open_time"] = "not-a-timestamp"
    snapshot.gate_payload = json.dumps(payload)
    with pytest.raises(d005.D005Error) as error:
        d005.observe_d005_decision(observation, snapshot, config=config)
    assert "malformed" in str(error.value) or "timestamp" in str(error.value)


def test_case_13_block_identity_mismatch_fails_closed():
    frame = _bullish_frame()
    observation, snapshot, config = _primary_observation(frame)
    observation = _observation(
        v002_block_id="not-the-real-block",
        available_at_ms=observation["available_at_ms"],
    )
    with pytest.raises(d005.ReconciliationError) as error:
        d005.observe_d005_decision(observation, snapshot, config=config)
    assert "block-identity mismatch" in str(error.value)


def test_case_14_final_fvg_list_mismatch_fails_closed():
    # A persisted surface the causal recomputation cannot reproduce must be
    # rejected before any temporal observation is derived.
    frame = _bullish_frame()
    observation, snapshot, config = _primary_observation(
        frame,
        persisted_fvgs=[
            {"direction": "bearish", "top": 2407.0, "bottom": 2406.0,
             "filled": False, "timeframe": "M5", "source_index": 31},
        ],
    )
    with pytest.raises(d005.FinalSurfaceMismatch):
        d005.observe_d005_decision(observation, snapshot, config=config)


def test_case_15_no_counterfactual_candidate_keys():
    record = {
        "h003_temporal_association_decisions": 5,
        "evil": {"candidate_if_temporal": True},
    }
    with pytest.raises(d005.D005Error) as error:
        d005._reject_banned_keys(record)
    assert "candidate_if_temporal" in str(error.value)


def test_banned_concepts_are_structurally_refused():
    for concept in (
        "candidate_if_temporal", "rescued_candidate", "alternate_lag",
        "optimal_lag", "temporal_threshold", "candidate_without_final_fvg",
        "pnl", "profit", "win_rate", "sharpe",
    ):
        with pytest.raises(d005.D005Error):
            d005._reject_banned_keys({concept: 1})


# ---------------------------------------------------------------------------
# Aggregation, partition, headroom classification (D005-TC002 corrected:
# four-cell contingency from individual V002 observations; marginals are
# reconciliation totals only — never subtracted)
# ---------------------------------------------------------------------------


def _surface(entrants=10, active=4, associated=1):
    return {
        "gate11_entrants_observed": entrants,
        "v002_structurally_active_count": active,
        "v002_associated_same_direction_fvg_count": associated,
    }


def _v002_obs(decision_id, *, active, associated):
    """Minimal frozen-V002-observation shape for partition classification."""
    return {
        "decision_id": decision_id,
        "v002_structurally_active": active,
        "v002_fvg_associated": associated,
    }


def _d005_obs(decision_id, category, temporal, side="LONG"):
    record = {
        "decision_id": decision_id,
        "h003_side": side,
        "attrition_category": category,
        "h003_temporal_association": temporal,
        "h003_qualifying_fvg_count": 1 if temporal else 0,
        "temporal_distance_signed_bars": [4] if temporal else [],
        "temporal_distance_records": (
            [{
                "fvg_direction": "bullish",
                "formation_order_relative_to_ob": "AFTER_OB_CONFIRMATION",
                "signed_bar_distance": 4,
                "absolute_bar_distance": 4,
                "elapsed_minutes": 20.0,
                "ob_confirmed_at": "2024-05-01T10:10:00+00:00",
                "fvg_formation_available_at": "2024-05-01T10:30:00+00:00",
                "fvg_completion_open_time": "2024-05-01T10:25:00+00:00",
                "unfilled_at_decision": False,
                "filled_before_decision": True,
                "source_index": 31,
            }] if temporal else []
        ),
        "causal_fvg_count_total": 2,
        "causal_fvg_count_same_direction": 1,
        "causal_fvg_count_opposite_direction": 1,
        "non_causal_rows_excluded": 0,
        "temporal_fvg_universe": [
            {
                "fvg_direction": "bullish",
                "formation_order_relative_to_ob": "AFTER_OB_CONFIRMATION",
                "signed_bar_distance": 4,
                "absolute_bar_distance": 4,
                "elapsed_minutes": 20.0,
                "ob_confirmed_at": "2024-05-01T10:10:00+00:00",
                "fvg_formation_available_at": "2024-05-01T10:30:00+00:00",
                "fvg_completion_open_time": "2024-05-01T10:25:00+00:00",
                "unfilled_at_decision": False,
                "filled_before_decision": True,
                "source_index": 31,
            }
        ] if temporal else [
            {
                "fvg_direction": "bearish",
                "formation_order_relative_to_ob": "BEFORE_OB_CONFIRMATION",
                "signed_bar_distance": -10,
                "absolute_bar_distance": 10,
                "elapsed_minutes": -50.0,
                "ob_confirmed_at": "2024-05-01T09:50:00+00:00",
                "fvg_formation_available_at": "2024-05-01T09:00:00+00:00",
                "fvg_completion_open_time": "2024-05-01T08:55:00+00:00",
                "unfilled_at_decision": False,
                "filled_before_decision": True,
                "source_index": 6,
            }
        ],
    }
    d005._reject_banned_keys(record)
    return record


def test_aggregate_partition_headroom_and_categories():
    observations = [
        _d005_obs("a", "SAME_DIRECTION_FVG_EXISTED_BUT_FILLED", True),
        _d005_obs("b", "SAME_DIRECTION_FVG_EXISTED_BUT_FILLED", True, side="SHORT"),
        _d005_obs("c", "SAME_DIRECTION_FVG_PRE_OB_ONLY", False),
        _d005_obs("d", "NO_SAME_DIRECTION_FVG_EVER", False),
        _d005_obs("e", "OPPOSITE_DIRECTION_ONLY", False),
    ]
    # primary=5 (cell B) => R2=5; cell A=1 => R1=1; entrants=12 => R3=6
    v002_observations = (
        [_v002_obs(name, active=True, associated=False) for name in ("a", "b", "c", "d", "e")]
        + [_v002_obs("x", active=True, associated=True)]
        + [_v002_obs(f"n{i}", active=False, associated=False) for i in range(6)]
    )
    aggregate = d005.aggregate_d005(
        observations, v002_observations, _surface(entrants=12, active=6, associated=1)
    )
    assert aggregate["D005_population"]["primary_population"] == 5
    partition = aggregate["D005_population"]["reference_populations_partition"]
    assert partition["partitions_entrants_exactly"] is True
    assert partition["primary_equals_R2"] is True
    contingency = aggregate["D005_population"]["four_cell_contingency"]
    assert contingency["ACTIVE_ASSOCIATED"] == 1
    assert contingency["ACTIVE_NOT_ASSOCIATED"] == 5
    assert contingency["NONACTIVE_ASSOCIATED"] == 0
    assert contingency["NONACTIVE_NOT_ASSOCIATED"] == 6
    assert contingency["sums_to_entrants_exactly"] is True
    assert contingency["marginals_are_reconciliation_totals_only"] is True
    assert contingency["associated_is_not_a_subset_of_active"] is True
    assert contingency["marginal_subtraction_prohibited"] is True
    assert aggregate["D005_population"][
        "primary_decision_id_set_reconciles_exactly"
    ] is True
    assert aggregate["final_surface_attrition"]["categories"] == {
        "NO_SAME_DIRECTION_FVG_EVER": 1,
        "OPPOSITE_DIRECTION_ONLY": 1,
        "SAME_DIRECTION_FVG_EXISTED_BUT_FILLED": 2,
        "SAME_DIRECTION_FVG_PRE_OB_ONLY": 1,
    }
    h003 = aggregate["h003_temporal_association"]
    assert h003["h003_temporal_association_decisions"] == 2
    assert h003["structural_count_only"] is True and h003["never_a_candidate_count"] is True
    headroom = aggregate["headroom_feasibility"]
    assert headroom["classification"] == "TEMPORAL_VARIANT_HEADROOM_INSUFFICIENT"
    assert headroom["tier_a_arithmetic_headroom_observations"] == 29
    assert headroom["necessary_condition_only"] is True
    summary = aggregate["temporal_distance_surface"]["summary"]
    assert summary["count"] == 2 and summary["signed_min"] == summary["signed_max"] == 4
    assert aggregate["temporal_fvg_universe_surface"]["formation_orders"][
        "AFTER_OB_CONFIRMATION"
    ] >= 2


def test_headroom_possible_boundary_at_29():
    observations = [
        _d005_obs(f"d{i}", "SAME_DIRECTION_FVG_EXISTED_BUT_FILLED", True)
        for i in range(29)
    ]
    v002_observations = [_v002_obs(f"d{i}", active=True, associated=False) for i in range(29)] + [
        _v002_obs(f"n{i}", active=False, associated=False) for i in range(11)
    ]
    aggregate = d005.aggregate_d005(
        observations, v002_observations, _surface(entrants=40, active=29, associated=0)
    )
    assert aggregate["headroom_feasibility"]["classification"] == (
        "TEMPORAL_VARIANT_HEADROOM_POSSIBLE"
    )
    assert aggregate["h003_temporal_association"][
        "h003_temporal_association_decisions"
    ] == 29


def test_aggregate_fails_closed_on_marginal_mismatch():
    # active marginal disagrees with the four-cell construction
    v002_observations = [
        _v002_obs("a", active=True, associated=False),
        _v002_obs("b", active=False, associated=False),
    ]
    with pytest.raises(d005.ReconciliationError):
        d005.aggregate_d005(
            [_d005_obs("a", "NO_SAME_DIRECTION_FVG_EVER", False)],
            v002_observations,
            _surface(entrants=2, active=3, associated=0),  # active 3 != A+B 1
        )
    # associated marginal disagrees with the four-cell construction
    with pytest.raises(d005.ReconciliationError):
        d005.aggregate_d005(
            [_d005_obs("a", "NO_SAME_DIRECTION_FVG_EVER", False)],
            v002_observations,
            _surface(entrants=2, active=1, associated=2),  # associated 2 != A+C 0
        )


def test_aggregate_fails_closed_when_contingency_misses_entrants():
    v002_observations = [
        _v002_obs("a", active=True, associated=False),
        _v002_obs("b", active=False, associated=False),
    ]
    with pytest.raises(d005.ReconciliationError) as error:
        d005.aggregate_d005(
            [_d005_obs("a", "NO_SAME_DIRECTION_FVG_EVER", False)],
            v002_observations,
            _surface(entrants=7, active=1, associated=0),  # 2 != 7
        )
    assert "!= entrants" in str(error.value)


def test_aggregate_fails_closed_on_unknown_category():
    v002_observations = [_v002_obs("a", active=True, associated=False)]
    with pytest.raises(d005.ReconciliationError):
        d005.aggregate_d005(
            [_d005_obs("a", "SOME_NEW_CATEGORY", False)],
            v002_observations,
            _surface(entrants=1, active=1, associated=0),
        )


def test_aggregate_fails_closed_when_h003_exceeds_primary():
    # The accumulated H003 count versus the primary population is a
    # structural invariant; membership can only inflate via corrupted
    # per-decision state, and a qualifying-count divergence fails closed
    # before any inflated count could survive.
    observations = [_d005_obs("a", "NO_SAME_DIRECTION_FVG_EVER", False)]
    observations[0]["h003_temporal_association"] = True  # corrupt
    observations[0]["h003_qualifying_fvg_count"] = 2  # inconsistent with distances
    with pytest.raises(d005.ReconciliationError):
        d005.aggregate_d005(
            observations,
            [_v002_obs("a", active=True, associated=False)],
            _surface(entrants=1, active=1, associated=0),
        )


# ---------------------------------------------------------------------------
# Distance summary shapes
# ---------------------------------------------------------------------------


def test_distance_summary_permitted_summaries_only():
    summary = d005._distance_summary([-8, -8, 4, 12, 20])
    assert summary["count"] == 5
    assert summary["signed_min"] == -8 and summary["signed_max"] == 20
    assert summary["absolute_min"] == 4 and summary["absolute_max"] == 20
    assert set(summary["exact_integer_histogram_signed"]) == {"-8", "4", "12", "20"}
    assert set(summary["quantiles_signed"]) == {"p25", "p50", "p75"}
    assert d005._distance_summary([]) == {"count": 0}


# ---------------------------------------------------------------------------
# Full-loop discipline over a synthetic store (D001 classification reused)
# ---------------------------------------------------------------------------


def test_run_d005_loop_discipline_on_mocked_store(monkeypatch):
    from bot.strategy.setup_state import StrategyState, record_from_state
    from tests.test_phase8_v2_d001_tooling import _Snapshot, _Table as _V2Table
    from tests.test_phase8_v2_v002_eval_tooling import (
        _displacement_snapview,
        _fake_blob_source,
        _store_identity,
    )

    snapshot = _displacement_snapview(AT, monkeypatch)
    from backtests.phase8_v2_diagnostic_d001 import evaluate_orchestration_decision

    seed = datetime(2024, 1, 1, tzinfo=UTC)
    prior = record_from_state(StrategyState(event_time=seed), event_at=seed)
    row, _next = evaluate_orchestration_decision(snapshot, prior)
    assert "gate_11_confluence_score" in row["gate_results"]

    early = _Snapshot(
        available_at_ms=int(AT.timestamp() * 1000) - 1,
        gate_status="early_exit",
    )
    table = _V2Table([early, snapshot])
    store = type("Store", (), {})()
    store.identity = _store_identity()
    store.table = table

    doc, rendered = d005.run_d005(
        store,
        v002_implementation_commit="a" * 40,
        tooling_commit="a" * 40,
        blob_source=_fake_blob_source(),
    )
    accounting = doc["decision_accounting"]
    assert accounting["scheduled"] == 2
    assert accounting["missing_history"] == 1
    assert accounting["reducer_classified"] == 1
    assert accounting["reconciles"] is True
    surface = doc["v002_reference_surface"]
    assert surface["gate11_entrants_observed"] == 1
    partition = doc["D005_population"]["reference_populations_partition"]
    assert partition["partitions_entrants_exactly"] is True
    assert doc["h003_temporal_association"]["structural_count_only"] is True
    assert doc["headroom_feasibility"]["classification"] in (
        "TEMPORAL_VARIANT_HEADROOM_POSSIBLE",
        "TEMPORAL_VARIANT_HEADROOM_INSUFFICIENT",
    )
    assert doc["counterfactual_arithmetic_performed"] is False
    assert doc["no_lag_optimization_performed"] is True
    assert doc["d005_is_read_only"] is True
    assert doc["provenance"]["hypothesis_id"] == "phase8-v2-H003"
    assert doc["provenance"]["v002_implementation_commit"] == "a" * 40
    blob = rendered.decode("utf-8")
    for concept in ("candidate_if_temporal", "rescued_candidate", "optimal_lag", "pnl"):
        assert concept not in blob


def test_run_d005_refuses_wrong_fold(monkeypatch):
    from tests.test_phase8_v2_d001_tooling import _Table as _V2Table
    from tests.test_phase8_v2_v002_eval_tooling import _store_identity

    store = type("Store", (), {})()
    store.identity = dict(_store_identity(), fold_id="fold-02")
    store.table = _V2Table([])
    with pytest.raises(Exception) as error:
        d005.run_d005(
            store,
            v002_implementation_commit="a" * 40,
            tooling_commit="a" * 40,
            blob_source=lambda commit, path: b"x",
        )
    assert "fold-02" in str(error.value) or "refused" in str(error.value)


def test_write_result_refuses_overwrite(tmp_path):
    material = {"x": 1}
    target_dir = tmp_path / "d005"
    target_dir.mkdir()
    (target_dir / "phase8-v2-D005_result.json").write_bytes(b"existing")
    with pytest.raises(d005.D005Error):
        d005.write_result(material, b"{}-not-used", target_dir)


def test_boundary_guards_reused_from_v002():
    assert d005.HISTORICAL_STORE_ID == "fold-01-1d710826193a6767"
    identity = {
        "fold_id": "fold-01-1d710826193a6767", "decision_timeframe": "M5",
        "evaluation_start_ms": d005.FOLD01_START_MS,
        "evaluation_end_ms": d005.FOLD01_END_MS, "coverage": "full",
    }
    with pytest.raises(Exception) as error:
        d005.check_store_boundary(identity)
    assert "refused" in str(error.value)


# ---------------------------------------------------------------------------
# D005-TC002 regressions: four-cell partition, primary-ID set reconciliation,
# real V002 semantics, structured pre-open CLI boundary guard.
#
# NO empirical Fold-01 value is encoded: attempt-1 counts (42/34/8) are
# incident history only and appear in NO assertion anywhere.
# ---------------------------------------------------------------------------


def test_tc002_four_cell_partition_synthetic():
    """Cells A/B/C/D each populated; R1=1, R2=1, R3=2; marginals = 2 each.

    Also proves the PROHIBITED old arithmetic (active − associated) would
    yield 0 instead of the true R2 = 1 — the exact defect class that blocked
    attempt 1 — from set semantics, not from any empirical value.
    """
    v002_observations = [
        _v002_obs("cell-a", active=True, associated=True),
        _v002_obs("cell-b", active=True, associated=False),
        _v002_obs("cell-c", active=False, associated=True),
        _v002_obs("cell-d", active=False, associated=False),
    ]
    surface = _surface(entrants=4, active=2, associated=2)
    aggregate = d005.aggregate_d005(
        [_d005_obs("cell-b", "NO_SAME_DIRECTION_FVG_EVER", False)],
        v002_observations,
        surface,
    )
    contingency = aggregate["D005_population"]["four_cell_contingency"]
    assert contingency["ACTIVE_ASSOCIATED"] == 1
    assert contingency["ACTIVE_NOT_ASSOCIATED"] == 1
    assert contingency["NONACTIVE_ASSOCIATED"] == 1
    assert contingency["NONACTIVE_NOT_ASSOCIATED"] == 1
    partition = aggregate["D005_population"]["reference_populations_partition"]
    assert partition["R1_active_with_final_same_direction_fvg"] == 1
    assert partition["R2_active_without_final_same_direction_fvg"] == 1
    assert partition["R3_v002_non_active"] == 2
    assert partition["partitions_entrants_exactly"] is True
    assert partition["primary_equals_R2"] is True
    assert surface["v002_structurally_active_count"] == 2
    assert surface["v002_associated_same_direction_fvg_count"] == 2
    assert surface["v002_structurally_active_count"] - surface[
        "v002_associated_same_direction_fvg_count"
    ] == 0  # the PROHIBITED subtraction: 0 != true R2 = 1


def test_tc002_primary_id_set_reconciliation_exact():
    v002_observations = (
        [_v002_obs("p1", active=True, associated=False),
         _v002_obs("p2", active=True, associated=False)]
        + [_v002_obs("cell-a", active=True, associated=True)]
        + [_v002_obs("cell-c", active=False, associated=True),
           _v002_obs("cell-d", active=False, associated=False)]
    )
    d005_observations = [
        _d005_obs("p1", "NO_SAME_DIRECTION_FVG_EVER", False),
        _d005_obs("p2", "OPPOSITE_DIRECTION_ONLY", False),
    ]
    aggregate = d005.aggregate_d005(
        d005_observations, v002_observations,
        _surface(entrants=5, active=3, associated=2),
    )
    assert aggregate["D005_population"]["primary_population"] == 2
    # Every primary V002 observation received exactly one D005 observation.
    assert aggregate["D005_population"][
        "primary_decision_id_set_reconciles_exactly"
    ] is True


def test_tc002_primary_id_set_mismatch_fails_closed():
    """Equal counts but divergent decision-ID sets fail closed on the exact
    set-equality requirement: one D005 observation carries a non-primary V002
    decision id, so the missing primary AND the extra non-primary are both
    named (a count-only reconciliation would pass this case)."""
    v002_observations = [
        _v002_obs("p1", active=True, associated=False),
        _v002_obs("p2", active=True, associated=False),
        _v002_obs("cell-d", active=False, associated=False),
    ]
    with pytest.raises(d005.ReconciliationError) as error:
        d005.aggregate_d005(
            [
                _d005_obs("p1", "NO_SAME_DIRECTION_FVG_EVER", False),
                _d005_obs("cell-d", "OPPOSITE_DIRECTION_ONLY", False),
            ],
            v002_observations,
            _surface(entrants=3, active=2, associated=0),
        )
    message = str(error.value)
    assert "missing" in message and "p2" in message
    assert "extra" in message and "cell-d" in message


def test_tc002_duplicate_primary_id_fails_closed():
    v002_observations = [
        _v002_obs("p1", active=True, associated=False),
        _v002_obs("p1", active=True, associated=False),
    ]
    with pytest.raises(d005.ReconciliationError) as error:
        d005.aggregate_d005(
            [_d005_obs("p1", "NO_SAME_DIRECTION_FVG_EVER", False)],
            v002_observations,
            _surface(entrants=2, active=2, associated=0),
        )
    assert "duplicate decision IDs in the V002 observations" in str(error.value)


def test_tc002_duplicate_d005_id_fails_closed():
    v002_observations = [
        _v002_obs("p1", active=True, associated=False),
        _v002_obs("p2", active=True, associated=False),
    ]
    with pytest.raises(d005.ReconciliationError) as error:
        d005.aggregate_d005(
            [
                _d005_obs("p1", "NO_SAME_DIRECTION_FVG_EVER", False),
                _d005_obs("p1", "OPPOSITE_DIRECTION_ONLY", False),
            ],
            v002_observations,
            _surface(entrants=2, active=2, associated=0),
        )
    assert "duplicate decision IDs in the D005 observations" in str(error.value)


def test_tc002_v002_observation_count_mismatch_fails_closed():
    with pytest.raises(d005.ReconciliationError) as error:
        d005.aggregate_d005(
            [],
            [_v002_obs("p1", active=True, associated=False)],
            _surface(entrants=5, active=1, associated=0),
        )
    assert "!= entrants" in str(error.value)


def test_tc002_real_v002_mitigated_block_is_nonactive_but_associated():
    """Real evaluate_v002_structural_pair: MITIGATED pair still carries the
    same-direction final FVG association (associated ⊄ active).

    Purely synthetic frames; no Fold-01 data.  The second post-confirmation
    candle touches the block zone; while it is the LAST available candle the
    pair is structurally active (RETEST_ELIGIBLE); one candle later the same
    pair reports MITIGATED — non-active — while the persisted same-direction
    final FVG association stays attached in both states.
    """
    from tests.test_phase8_v2_v002_variant import candle, to_frame

    config = StrategyConfig()
    rows = build_rows(pre=30, post=2)
    zone_low, zone_high = 2390.0, 2401.0  # build_rows candidate low..high
    # Make the FIRST post-confirmation candle touch the zone (low enters the
    # zone; close stays above the zone low, so no invalidation).
    touch_open_time = datetime(2024, 5, 1, 9, 0, tzinfo=UTC) + timedelta(minutes=5 * 32)
    rows[32] = candle(touch_open_time, 2405.0, 2406.0, 2398.0, 2404.0)
    frame = to_frame(rows)
    fvgs = ({"direction": "bullish", "top": 2402.0, "bottom": 2399.0},)
    decision_active = pd.Timestamp(rows[32]["available_at"]).to_pydatetime()
    active_pair = evaluate_v002_structural_pair(
        frame, StrategySide.LONG, decision_active, config, fvgs=fvgs,
    )
    assert active_pair.structurally_active is True
    assert active_pair.state == "RETEST_ELIGIBLE"
    assert active_pair.fvg_associated is True
    # Re-decide one candle LATER: the touching candle is no longer the last
    # available one, so the frozen evaluator reports MITIGATED — non-active —
    # while the same persisted same-direction final FVG stays associated.
    mitigated_pair = evaluate_v002_structural_pair(
        frame, StrategySide.LONG,
        pd.Timestamp(rows[33]["available_at"]).to_pydatetime(),
        config, fvgs=fvgs,
    )
    assert mitigated_pair.structurally_active is False
    assert mitigated_pair.state == "MITIGATED"
    assert mitigated_pair.fvg_associated is True
    assert float(zone_low) < float(zone_high)


def test_tc002_authorized_store_hash_path_passes_preopen():
    """The numeric fragments 4068 and 3525 inside the authorized store
    basename are hash material, not calendar years: the structured pre-open
    guard passes the authorized path that the inherited substring-year scan
    refused."""
    d005.validate_authorized_store_path(
        "C:/Users/chips/forex-signal-bot-data/phase8/evidence/"
        "market-feature-store/fold-01-a8b406884ab3525a"
    )  # must not raise
    for fragment in ("4068", "3525"):
        assert fragment in d005.AUTHORIZED_FOLD01_STORE_BASENAME
        assert int(fragment) >= 2025  # would be 'future years' under the old scan


def test_tc002_preopen_refuses_reserved_paths():
    authorized = "C:/data/phase8/evidence/market-feature-store/fold-01-a8b406884ab3525a"
    d005.validate_authorized_store_path(authorized)
    refusals = [
        "C:/data/phase8/holdout/fold-01-a8b406884ab3525a",
        "C:/data/phase8/final_validation/x",
        "C:/data/2025/store",
        "C:/data/year=2025/store",
        "C:/data/2026-01-01/store",
        "C:/data/phase8/evidence/market-feature-store/fold-02-55c55daef9809b63",
        "C:/data/phase8/evidence/market-feature-store/fold-01-1d710826193a6767",
    ]
    for path in refusals:
        with pytest.raises(d005.BoundaryError):
            d005.validate_authorized_store_path(path)


def test_tc002_preopen_refuses_wrong_fold_basename():
    with pytest.raises(d005.BoundaryError):
        d005.validate_authorized_store_path(
            "C:/data/phase8/evidence/market-feature-store/fold-01-deadbeefcafe1234"
        )


def test_tc002_defective_attempt1_fixture_partition_reproduction():
    """The frozen attempt-1 tooling bytes (7c9608d5) reproduce the exact
    blocked reconciliation from set semantics on a synthetic four-cell case
    (marginal subtraction), then the corrected tooling succeeds on the SAME
    inputs.  Byte-identity of the snapshot vs the committed blob is verified
    separately (opt-in, git plumbing outside the suite firewall).  No
    empirical Fold-01 value is used.
    """
    source = (
        Path(__file__).parent / "fixtures" / "d005_tooling_7c9608d5.py"
    ).read_bytes()
    module_name = "_d005_tooling_attempt1_7c9608d5"
    assert module_name not in sys.modules
    module = types.ModuleType(module_name)
    module.__file__ = str(
        Path(__file__).parent / "fixtures" / "d005_tooling_7c9608d5.py"
    )
    module.__dict__["__name__"] = module_name
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    sys.modules[module_name] = module
    # Four-cell synthetic population: one entrant in each cell.  The frozen
    # attempt-1 arithmetic (R1 = associated, R2 = active − associated)
    # derives R2 = 0 and refuses the single primary D005 observation.
    v002_observations = [
        {"decision_id": "cell-a", "v002_structurally_active": True,
         "v002_fvg_associated": True},
        {"decision_id": "cell-b", "v002_structurally_active": True,
         "v002_fvg_associated": False},
        {"decision_id": "cell-c", "v002_structurally_active": False,
         "v002_fvg_associated": True},
        {"decision_id": "cell-d", "v002_structurally_active": False,
         "v002_fvg_associated": False},
    ]
    d005_observations = [_d005_obs("cell-b", "NO_SAME_DIRECTION_FVG_EVER", False)]
    surface = _surface(entrants=4, active=2, associated=2)
    with pytest.raises(module.ReconciliationError):
        module.aggregate_d005(d005_observations, surface)
    # The corrected tooling succeeds on exactly the same inputs.
    corrected = d005.aggregate_d005(d005_observations, v002_observations, surface)
    assert corrected["D005_population"]["primary_population"] == 1
    assert corrected["D005_population"]["four_cell_contingency"][
        "ACTIVE_NOT_ASSOCIATED"
    ] == 1


def test_tc002_attempt1_fixture_bytes_match_frozen_commit():
    """Byte-identity of the attempt-1 tooling snapshot against the committed
    7c9608d5 blob (opt-in; real git plumbing is outside the suite firewall)."""
    import os
    import subprocess

    if os.environ.get("D005_TC002_VERIFY_COMMITTED_BYTES") != "1":
        pytest.skip(
            "subprocess git cat-file is prohibited inside the suite; run with "
            "D005_TC002_VERIFY_COMMITTED_BYTES=1 to byte-verify the fixture copy"
        )
    committed = subprocess.run(
        ["git", "cat-file", "blob",
         "7c9608d5b9871414a830e38395d1a67f7efacad2"
         ":backtests/phase8_v2_diagnostic_d005.py"],
        cwd=".", capture_output=True, check=True,
    ).stdout
    assert committed == (
        Path(__file__).parent / "fixtures" / "d005_tooling_7c9608d5.py"
    ).read_bytes()
