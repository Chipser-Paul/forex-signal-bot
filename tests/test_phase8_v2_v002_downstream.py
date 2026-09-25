# -*- coding: utf-8 -*-
"""V002 downstream-consistency tests (spec sections 14-15).

The downstream canonical-strategy decision used by V002 must consume the SAME
V002 structural-pair semantics as Gate 11: a decision that passes Gate 11
under V002 semantics must not afterwards be rejected by the historical
age-only EXPIRED short-circuit.  These tests also prove the protected
semantics (DXY, news, session, confluence threshold, symbol allowlist) run
through the untouched canonical engine.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

sys.path.insert(0, "tests")

from test_phase8_v2_v002_variant import (  # noqa: E402
    BASE,
    BAR,
    build_rows,
    fvgs,
    to_frame,
    zone_of,
)
from bot.strategy.config import StrategyConfig  # noqa: E402
from bot.strategy.legacy_adapter import evaluate_legacy_context  # noqa: E402
from bot.strategy.models import (  # noqa: E402
    BlockState,
    SetupEvidence,
    StrategyReason,
    StrategySide,
)
from bot.strategy.variant_v002 import evaluate_v002_strategy  # noqa: E402

UTC = timezone.utc


def _contexts():
    dxy = {"dxy_bias": "bearish", "available": True}
    news = {"news_clear": True, "state": "CLEAR", "source": "fixture"}
    session = {"session_allowed": True, "state": "CLEAR", "active_session": "london"}
    return dxy, news, session


def _evidence(active: bool, fvg: bool) -> SetupEvidence:
    return SetupEvidence(
        price_in_discount_or_premium=True,
        order_block_present=active,
        fvg_overlaps_order_block=fvg,
        liquidity_swept=True,
    )


def _evaluate(frame, config, decision_at, *, legacy: bool, fvgs_list=()):
    dxy, news, session = _contexts()
    evidence = _evidence(True, bool(fvgs_list))
    fn = evaluate_legacy_context if legacy else evaluate_v002_strategy
    kwargs = {}
    if not legacy:
        kwargs["fvgs"] = fvgs_list
    return fn(
        adapter="live",
        symbol="XAUUSDm",
        decision_at=decision_at,
        side="bullish",
        entry_frame=frame,
        htf_bias="bullish",
        dxy_context=dxy,
        news_context=news,
        session_context=session,
        evidence=evidence,
        config=config,
        **kwargs,
    )


def test_downstream_accepts_over_30_bar_pair_under_v002_semantics():
    frame, config, _block, decision_at = _fixture(pre=30, post=33)
    with_fvgs = fvgs(_block.zone_low - 2.0, _block.zone_low + 2.0)
    v002 = _evaluate(frame, config, decision_at, legacy=False, fvgs_list=with_fvgs)
    assert v002.entry_eligible is True
    assert v002.order_block is BlockState.ELIGIBLE
    assert v002.reasons == (StrategyReason.APPROVED,)
    assert v002.invalidation["v002_age_bars"] == 33
    assert v002.invalidation["v002_fvg_associated"] is True


def _fixture(pre: int, post: int):
    rows = build_rows(pre, post)
    frame = to_frame(rows)
    config = StrategyConfig()
    from bot.strategy.order_blocks import detect_order_blocks

    blocks = detect_order_blocks(frame, config)
    assert blocks and blocks[-1].side is StrategySide.LONG
    block = blocks[-1]
    decision_at = BASE + BAR * (pre + 2 + post)
    return frame, config, block, decision_at


def test_downstream_gate11_pass_is_not_rejected_by_age_short_circuit():
    """The §18 prohibition: Gate-11 pass then historical EXPIRED rejection."""
    frame, config, _block, decision_at = _fixture(pre=30, post=33)
    with_fvgs = fvgs(_block.zone_low - 2.0, _block.zone_low + 2.0)
    # V002: the same pair passes downstream (8/8 evidence set).
    v002 = _evaluate(frame, config, decision_at, legacy=False, fvgs_list=with_fvgs)
    assert v002.entry_eligible is True
    assert v002.order_block in (BlockState.ELIGIBLE, BlockState.RETEST_ELIGIBLE)
    # The untouched canonical path on the IDENTICAL frame rejects the exact
    # same block via the historical age-only EXPIRED short-circuit.
    canonical = _evaluate(frame, config, decision_at, legacy=True)
    assert canonical.entry_eligible is False
    assert canonical.order_block is BlockState.EXPIRED
    assert StrategyReason.ORDER_BLOCK_UNAVAILABLE in canonical.reasons
    assert canonical.invalidation.get("order_block_id") == v002.invalidation["order_block_id"]


def test_canonical_evaluator_original_expired_behavior_preserved():
    from bot.strategy.order_blocks import evaluate_order_block

    frame, config, _block, decision_at = _fixture(pre=30, post=33)
    result = evaluate_order_block(frame, StrategySide.LONG, decision_at, config)
    assert result.state is BlockState.EXPIRED
    assert result.reason == "block_expired"


def test_dxy_conflict_blocks_v002_candidate_unchanged():
    frame, config, _block, decision_at = _fixture(pre=30, post=3)
    dxy, news, session = _contexts()
    dxy_conflict = {"dxy_bias": "bullish", "available": True}
    decision = evaluate_v002_strategy(
        adapter="live",
        symbol="XAUUSDm",
        decision_at=decision_at,
        side="bullish",
        entry_frame=frame,
        htf_bias="bullish",
        dxy_context=dxy_conflict,
        news_context=news,
        session_context=session,
        evidence=_evidence(True, True),
        fvgs=fvgs(_block_zone_low(frame, config), _block_zone_low(frame, config) + 4.0),
        config=config,
    )
    assert decision.entry_eligible is False
    assert StrategyReason.DXY_DIRECTION_CONFLICT in decision.reasons
    assert decision.dxy.value == "BULLISH"


def _block_zone_low(frame, config):
    from bot.strategy.order_blocks import detect_order_blocks

    blocks = detect_order_blocks(frame, config)
    return blocks[-1].zone_low


def test_news_blocked_and_session_closed_unchanged_under_v002():
    frame, config, block, decision_at = _fixture(pre=30, post=3)
    fvg_list = fvgs(block.zone_low - 2.0, block.zone_low + 2.0)
    news_blocked = {"news_clear": False, "state": "BLOCKED", "source": "fixture"}
    decision = evaluate_v002_strategy(
        adapter="live", symbol="XAUUSDm", decision_at=decision_at, side="bullish",
        entry_frame=frame, htf_bias="bullish",
        dxy_context={"dxy_bias": "bearish", "available": True},
        news_context=news_blocked,
        session_context={"session_allowed": True, "state": "CLEAR", "active_session": "london"},
        evidence=_evidence(True, True), fvgs=fvg_list, config=config,
    )
    assert decision.entry_eligible is False
    assert StrategyReason.NEWS_BLOCKED in decision.reasons
    session_closed = {"session_allowed": False, "state": "BLOCKED", "active_session": "sydney"}
    decision = evaluate_v002_strategy(
        adapter="live", symbol="XAUUSDm", decision_at=decision_at, side="bullish",
        entry_frame=frame, htf_bias="bullish",
        dxy_context={"dxy_bias": "bearish", "available": True},
        news_context={"news_clear": True, "state": "CLEAR", "source": "fixture"},
        session_context=session_closed,
        evidence=_evidence(True, True), fvgs=fvg_list, config=config,
    )
    assert decision.entry_eligible is False
    assert StrategyReason.SESSION_CLOSED in decision.reasons


def test_young_pair_v002_matches_canonical_decision():
    frame, config, _block, decision_at = _fixture(pre=30, post=3)
    v002 = _evaluate(frame, config, decision_at, legacy=False)
    canonical = _evaluate(frame, config, decision_at, legacy=True)
    assert v002.entry_eligible == canonical.entry_eligible
    assert v002.order_block == canonical.order_block


def test_symbol_allowlist_unchanged():
    frame, config, _block, decision_at = _fixture(pre=30, post=3)
    dxy, news, session = _contexts()
    decision = evaluate_v002_strategy(
        adapter="live", symbol="EURUSD", decision_at=decision_at, side="bullish",
        entry_frame=frame, htf_bias="bullish",
        dxy_context=dxy, news_context=news, session_context=session,
        evidence=_evidence(True, True), fvgs=(), config=config,
    )
    assert decision.entry_eligible is False
    assert StrategyReason.SYMBOL_NOT_EXECUTABLE in decision.reasons


def test_v002_requires_resolved_side():
    frame, config, _block, decision_at = _fixture(pre=30, post=3)
    dxy, news, session = _contexts()
    with pytest.raises(Exception):
        evaluate_v002_strategy(
            adapter="live", symbol="XAUUSDm", decision_at=decision_at, side="flat",
            entry_frame=frame, htf_bias="bullish",
            dxy_context=dxy, news_context=news, session_context=session,
            evidence=_evidence(True, True), fvgs=(), config=config,
        )
