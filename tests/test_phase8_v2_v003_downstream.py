# -*- coding: utf-8 -*-
"""V003 downstream-consistency and safety tests (spec sections 37, 38, 39, 41).

Invariants proved:
1. Strategy State Invariance (Section 37): V003 does NOT write or mutate
   state.displacement_seen, state.fvg_zone, state.structure_state,
   state.liquidity_swept or any state field.
2. Entry Context Interception (Section 38): For temporal-only evidence,
   context["ob_zone"] is the live active OB, while context["fvg_zone"] is None.
   Historical filled temporal FVG geometry NEVER appears in entry context.
3. Final-FVG Context Preservation (Section 39): When a final canonical unfilled
   FVG exists, context["fvg_zone"] equals the exact final FVG geometry.
4. Natural Downstream Failure (Section 41): Temporal evidence enables an 8/8
   Gate-11 score, but setup fails candidate_ready naturally if canonical
   strategy protections (DXY, news, session) reject or determine_entry returns None.
5. Over-30-bar structural pair acceptance in downstream V003 strategy.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from backtests.phase8_v2_variant_v003_eval import (
    _v003_entry,
    _v003_entry_readiness,
)
from bot.strategy.config import StrategyConfig
from bot.strategy.models import (
    BlockState,
    SetupEvidence,
    StrategyReason,
    StrategySide,
)
from bot.strategy.variant_v003 import (
    V003PairResult,
    evaluate_v003_strategy,
    evaluate_v003_structural_pair,
    score_v003_setup,
)
from strategies.smc_engine.strategy_state import StrategyState

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


def make_bullish_temporal_frame():
    rows = [candle(BASE + BAR * i, 2400.0, 2402.0, 2398.0, 2400.0) for i in range(15)]
    # Candle 15 (candidate): zone [2390.0, 2401.0]
    rows.append(candle(BASE + BAR * 15, 2400.0, 2401.0, 2390.0, 2391.0))
    # Candle 16 (confirmation): body = 21.0
    rows.append(candle(BASE + BAR * 16, 2391.0, 2413.0, 2389.0, 2412.0))
    # Candle 17 (FVG completion candle): low = 2410.0 > candidate high (2401.0)
    rows.append(candle(BASE + BAR * 17, 2412.0, 2415.0, 2410.0, 2414.0))
    # Candle 18 (fills FVG at 2405.0)
    rows.append(candle(BASE + BAR * 18, 2414.0, 2415.0, 2405.0, 2412.0))
    for i in range(19, 25):
        rows.append(candle(BASE + BAR * i, 2412.0, 2415.0, 2408.0, 2412.0))

    frame = pd.DataFrame(rows)
    for col in ("open_time", "available_at"):
        frame[col] = pd.to_datetime(frame[col], utc=True)
    decision_at = pd.Timestamp(frame["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)
    return frame, decision_at


def _make_state(decision_at: datetime):
    state = StrategyState(decision_at)
    state.displacement_seen = False
    state.fvg_zone = None
    state.structure_state = "IDLE"
    state.liquidity_swept = False
    return state


class MockDecisionRecord:
    def __init__(self, decision_id: str, setup_id: str = "mock_setup_001"):
        import json
        self._data = {
            "last_event_id": decision_id,
            "last_result": json.dumps({"setup_id": setup_id}),
            "private_state": {},
        }

    def data(self):
        return self._data


def _make_payload():
    return {
        "symbol": "XAUUSDm",
        "htf_bias": "bullish",
        "dxy_context": {"dxy_bias": "bearish", "available": True},
        "news_context": {"news_clear": True, "state": "CLEAR", "source": "fixture"},
        "session_context": {
            "session_allowed": True,
            "state": "CLEAR",
            "active_session": "london",
            "is_priority_session": True,
        },
        "liquidity_context": {"liquidity_swept": True, "liquidity_pools": []},
        "internal_structure": {"event": "CHOCH"},
        "ob_result": {"in_discount_or_premium": True},
    }


# ===========================================================================
# Section 37: Strategy State Invariance Tests
# ===========================================================================


def test_strategy_state_invariance_before_and_after_v003_evaluation():
    """Section 37: For temporal-only evidence, prove V003 does NOT mutate
    state.displacement_seen, state.fvg_zone, state.structure_state,
    state.liquidity_swept or any state field."""
    frame, decision_at = make_bullish_temporal_frame()
    config = StrategyConfig()
    pair = evaluate_v003_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=[])
    assert pair.temporal_fvg_evidence is True
    assert pair.final_fvg_associated is False

    score = score_v003_setup(
        pair=pair, htf_bias="bullish", price_in_discount_or_premium=True, liquidity_swept=True
    )
    payload = _make_payload()
    state = _make_state(decision_at)

    # Deep snapshot before
    state_dict_before = copy.deepcopy(state.__dict__)

    # Execute downstream entry determination
    _v003_entry(
        state=state,
        decision_at=decision_at,
        frame=frame,
        pair=pair,
        score=score,
        payload=payload,
    )

    # V003 critical state fields must be completely unmutated
    assert state.displacement_seen == state_dict_before["displacement_seen"] is False
    assert state.fvg_zone == state_dict_before["fvg_zone"] is None
    assert state.structure_state == state_dict_before["structure_state"] == "IDLE"
    assert state.liquidity_swept == state_dict_before["liquidity_swept"] is False
    assert state.ob_zone == state_dict_before["ob_zone"] is None


# ===========================================================================
# Section 38: Entry Context Interception Tests (Temporal-Only Evidence)
# ===========================================================================


def test_entry_context_interception_temporal_only_evidence():
    """Section 38: Intercept frozen determine_entry for temporal-only evidence:
    - context['ob_zone'] is live active OB zone;
    - context['fvg_zone'] is None;
    - Historical filled temporal FVG geometry NEVER appears in context."""
    frame, decision_at = make_bullish_temporal_frame()
    config = StrategyConfig()
    pair = evaluate_v003_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=[])
    assert pair.temporal_fvg_evidence is True
    assert pair.live_fvg_top is None
    assert pair.live_fvg_bottom is None

    score = score_v003_setup(
        pair=pair, htf_bias="bullish", price_in_discount_or_premium=True, liquidity_swept=True
    )
    payload = _make_payload()
    state = _make_state(decision_at)

    captured_context = {}

    def mock_determine_entry(symbol, st, current_price, score_result=None, context=None, emit_log=None):
        nonlocal captured_context
        captured_context = dict(context or {})
        return {"entry_type": "limit", "price": current_price}

    with patch("strategies.smc_engine.entry_model.determine_entry", side_effect=mock_determine_entry):
        entry = _v003_entry(
            state=state,
            decision_at=decision_at,
            frame=frame,
            pair=pair,
            score=score,
            payload=payload,
        )

    assert entry is not None
    assert captured_context["ob_zone"] == (float(pair.zone_low), float(pair.zone_high))
    assert captured_context["fvg_zone"] is None
    assert captured_context["htf_zone_alignment"] is True


# ===========================================================================
# Section 39: Final FVG Context Preservation Tests
# ===========================================================================


def test_entry_context_final_fvg_evidence_preserved():
    """Section 39: When final canonical unfilled FVG exists, context['fvg_zone']
    equals V002's exact final FVG geometry."""
    frame, decision_at = make_bullish_temporal_frame()
    config = StrategyConfig()
    final_fvgs = [{"direction": "bullish", "top": 2425.0, "bottom": 2420.0, "timeframe": "M5"}]
    pair = evaluate_v003_structural_pair(
        frame, StrategySide.LONG, decision_at, config, fvgs=final_fvgs
    )
    assert pair.final_fvg_associated is True
    assert pair.live_fvg_top == 2425.0
    assert pair.live_fvg_bottom == 2420.0

    score = score_v003_setup(
        pair=pair, htf_bias="bullish", price_in_discount_or_premium=True, liquidity_swept=True
    )
    payload = _make_payload()
    state = _make_state(decision_at)

    captured_context = {}

    def mock_determine_entry(symbol, st, current_price, score_result=None, context=None, emit_log=None):
        nonlocal captured_context
        captured_context = dict(context or {})
        return {"entry_type": "limit", "price": current_price}

    with patch("strategies.smc_engine.entry_model.determine_entry", side_effect=mock_determine_entry):
        _v003_entry(
            state=state,
            decision_at=decision_at,
            frame=frame,
            pair=pair,
            score=score,
            payload=payload,
        )

    assert captured_context["ob_zone"] == (float(pair.zone_low), float(pair.zone_high))
    assert captured_context["fvg_zone"] == (2420.0, 2425.0)


# ===========================================================================
# Section 41: Natural Downstream Failure Tests
# ===========================================================================


def test_downstream_natural_failure_when_session_blocked():
    """Section 41: Decision passes Gate 11 with 8/8 but fails canonical strategy
    due to session protection."""
    frame, decision_at = make_bullish_temporal_frame()
    config = StrategyConfig()
    evidence = SetupEvidence(
        price_in_discount_or_premium=True,
        order_block_present=True,
        fvg_overlaps_order_block=True,
        liquidity_swept=True,
    )
    payload = _make_payload()
    payload["session_context"] = {
        "session_allowed": False,
        "reason": "outside_allowed_session",
        "active_session": "asian",
    }

    res = evaluate_v003_strategy(
        adapter="live",
        symbol="XAUUSDm",
        decision_at=decision_at,
        side="bullish",
        entry_frame=frame,
        htf_bias="bullish",
        dxy_context=dict(payload["dxy_context"]),
        news_context=dict(payload["news_context"]),
        session_context=dict(payload["session_context"]),
        evidence=evidence,
        fvgs=[],
        config=config,
    )
    assert res.entry_eligible is False
    assert StrategyReason.SESSION_CLOSED in res.reasons

    # In readiness helper:
    mock_record = MockDecisionRecord("dec_1", "setup_001")
    setup_id, entry, ready = _v003_entry_readiness(
        row={"decision_id": "dec_1"},
        snapshot=None,
        decision_result_record=mock_record,
        decision_at=decision_at,
        frame=frame,
        payload=payload,
        pair=evaluate_v003_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=[]),
        score={"passes_threshold": True, "score": 8},
        strategy_eligible=False,
        config=config,
    )
    assert setup_id == "setup_001"
    assert ready is False
    assert entry is None


def test_downstream_natural_failure_when_dxy_conflicts():
    """Section 41: Decision fails downstream when DXY conflicts."""
    frame, decision_at = make_bullish_temporal_frame()
    config = StrategyConfig()
    evidence = SetupEvidence(
        price_in_discount_or_premium=True,
        order_block_present=True,
        fvg_overlaps_order_block=True,
        liquidity_swept=True,
    )
    payload = _make_payload()
    payload["dxy_context"] = {"dxy_bias": "bullish", "available": True}

    res = evaluate_v003_strategy(
        adapter="live",
        symbol="XAUUSDm",
        decision_at=decision_at,
        side="bullish",
        entry_frame=frame,
        htf_bias="bullish",
        dxy_context=dict(payload["dxy_context"]),
        news_context=dict(payload["news_context"]),
        session_context=dict(payload["session_context"]),
        evidence=evidence,
        fvgs=[],
        config=config,
    )
    assert res.entry_eligible is False
    assert StrategyReason.DXY_DIRECTION_CONFLICT in res.reasons


def test_downstream_natural_failure_when_news_blocks():
    """Section 41: Decision fails downstream when news blocks."""
    frame, decision_at = make_bullish_temporal_frame()
    config = StrategyConfig()
    evidence = SetupEvidence(
        price_in_discount_or_premium=True,
        order_block_present=True,
        fvg_overlaps_order_block=True,
        liquidity_swept=True,
    )
    payload = _make_payload()
    payload["news_context"] = {"news_clear": False, "reason": "high_impact_news", "source": "calendar"}

    res = evaluate_v003_strategy(
        adapter="live",
        symbol="XAUUSDm",
        decision_at=decision_at,
        side="bullish",
        entry_frame=frame,
        htf_bias="bullish",
        dxy_context=dict(payload["dxy_context"]),
        news_context=dict(payload["news_context"]),
        session_context=dict(payload["session_context"]),
        evidence=evidence,
        fvgs=[],
        config=config,
    )
    assert res.entry_eligible is False
    assert StrategyReason.NEWS_BLOCKED in res.reasons


def test_downstream_natural_failure_when_determine_entry_returns_none():
    """Section 41: When strategy is eligible but determine_entry returns None,
    candidate_ready is naturally False."""
    frame, decision_at = make_bullish_temporal_frame()
    config = StrategyConfig()
    pair = evaluate_v003_structural_pair(frame, StrategySide.LONG, decision_at, config, fvgs=[])
    score = score_v003_setup(
        pair=pair, htf_bias="bullish", price_in_discount_or_premium=True, liquidity_swept=True
    )
    payload = _make_payload()
    mock_record = MockDecisionRecord("dec_1", "setup_001")

    with patch("backtests.phase8_v2_variant_v003_eval._v002_private_entry_state", return_value=_make_state(decision_at)), \
         patch("strategies.smc_engine.entry_model.determine_entry", return_value=None):
        setup_id, entry, ready = _v003_entry_readiness(
            row={"decision_id": "dec_1"},
            snapshot=None,
            decision_result_record=mock_record,
            decision_at=decision_at,
            frame=frame,
            payload=payload,
            pair=pair,
            score=score,
            strategy_eligible=True,
            config=config,
        )

    assert setup_id == "setup_001"
    assert ready is False
    assert entry is None


def test_downstream_accepts_over_30_bar_pair_under_v003_semantics():
    """Age > 30 bars alone does NOT reject the pair in downstream V003 strategy."""
    frame, decision_at = make_bullish_temporal_frame()
    # Add 40 post candles so age > 30 bars
    rows = list(frame.to_dict("records"))
    last_t = pd.Timestamp(rows[-1]["open_time"]).to_pydatetime()
    for i in range(1, 41):
        rows.append(candle(last_t + BAR * i, 2412.0, 2415.0, 2408.0, 2412.0))
    frame_old = pd.DataFrame(rows)
    for col in ("open_time", "available_at"):
        frame_old[col] = pd.to_datetime(frame_old[col], utc=True)
    dec_at = pd.Timestamp(frame_old["available_at"].iloc[-1]).to_pydatetime().astimezone(UTC)

    config = StrategyConfig()
    payload = _make_payload()
    evidence = SetupEvidence(
        price_in_discount_or_premium=True,
        order_block_present=True,
        fvg_overlaps_order_block=True,
        liquidity_swept=True,
    )

    res = evaluate_v003_strategy(
        adapter="live",
        symbol="XAUUSDm",
        decision_at=dec_at,
        side="bullish",
        entry_frame=frame_old,
        htf_bias="bullish",
        dxy_context=dict(payload["dxy_context"]),
        news_context=dict(payload["news_context"]),
        session_context=dict(payload["session_context"]),
        evidence=evidence,
        fvgs=[],
        config=config,
    )
    assert res.entry_eligible is True
    assert res.order_block in (BlockState.ELIGIBLE, BlockState.RETEST_ELIGIBLE)
    assert res.invalidation["v003_age_bars"] > 30
    assert res.invalidation["v003_temporal_fvg_evidence"] is True
