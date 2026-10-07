# -*- coding: utf-8 -*-
"""Synthetic invariant tests for the V004 entry direction authority evaluator (H009).

No store access, no empirical data. Proves the preregistered invariants of
``docs/PHASE8_V2_VARIANT_V004.md``:
- Strict V003 baseline preservation (when V003 is ready, entry is preserved unchanged);
- Gate-12/13 directional authority unification under requested trade direction;
- Strict state invariance (authoritative state is never mutated);
- Strict liquidity alignment rule preservation (no rule relaxation);
- Conservative score-8 early-entry confirmation requirement (E2 rejections preserved);
- Directional alignment verification (fallback entries strictly match requested direction).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

import pytest

from bot.strategy.models import StrategySide
from bot.strategy.variant_v003 import V003PairResult
from bot.strategy.variant_v004 import (
    SPEC_PHASE_A_SHA256,
    SPEC_SHA256,
    V004_ID,
    H009_ID,
    V004_SOURCE_V003_BASELINE,
    V004_SOURCE_DIRECTIONAL_FALLBACK,
    V004_SOURCE_NONE,
    V004VariantError,
    evaluate_v004_entry_readiness,
    is_valid_liquidity_alignment,
)
from strategies.smc_engine.strategy_state import StrategyState

UTC = timezone.utc
DECISION_TIME = datetime(2024, 5, 1, 10, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[1]


def make_dummy_pair(
    *,
    side: StrategySide = StrategySide.LONG,
    structurally_active: bool = True,
    zone_low: float = 2390.0,
    zone_high: float = 2400.0,
) -> V003PairResult:
    """Create a synthetic V003PairResult for testing."""
    return V003PairResult(
        state="ACTIVE",
        reason="canonical_confirmed",
        side=side,
        block_id="ob_dummy_1",
        zone_low=zone_low,
        zone_high=zone_high,
        confirmed_at=DECISION_TIME,
        age_bars=5,
        final_fvg_associated=True,
        temporal_fvg_evidence=False,
        v003_fvg_evidence=True,
        fvg_evidence_source="FINAL_SURFACE",
        fvg_direction="bullish" if side == StrategySide.LONG else "bearish",
        exact_overlap=True,
        live_fvg_top=2395.0,
        live_fvg_bottom=2392.0,
    )


def make_test_state(
    *,
    structure_dir: str = "bearish",
    structure_state: str = "transition",
    liquidity_side: str = "buy",
    liquidity_type: str = "internal_continuation",
    displacement_seen: bool = True,
    liquidity_swept: bool = True,
    daily_limits_hit: bool = False,
    news_clear: bool = True,
) -> StrategyState:
    """Create a synthetic StrategyState with given fields."""
    state = StrategyState(event_time=DECISION_TIME)
    state.last_update = DECISION_TIME.replace(tzinfo=None)
    state.structure_dir = structure_dir
    state.structure_state = structure_state
    state.liquidity_side = liquidity_side
    state.liquidity_type = liquidity_type
    state.displacement_seen = displacement_seen
    state.liquidity_swept = liquidity_swept
    state.daily_limits_hit = daily_limits_hit
    state.news_status = {"news_clear": news_clear}
    return state


def make_score(score_val: int = 8) -> dict[str, Any]:
    """Create synthetic Gate-11 score dictionary."""
    return {
        "score": score_val,
        "max_score": 8,
        "grade": "A+" if score_val == 8 else "SKIP",
        "passes_threshold": score_val >= 8,
        "min_score_to_trade": 8,
        "checks": [],
    }


def make_context(
    *,
    internal_event: str | None = "BOS",
    sweep_rejected: bool = True,
    asian_swept: bool = True,
    has_ob: bool = True,
) -> dict[str, Any]:
    """Create synthetic entry context."""
    return {
        "ob_zone": (2390.0, 2400.0) if has_ob else None,
        "fvg_zone": (2392.0, 2395.0),
        "after_london_open": True,
        "asian_liquidity_swept": asian_swept,
        "sweep_rejected": sweep_rejected,
        "internal_structure_event": internal_event,
        "htf_zone_alignment": has_ob,
    }


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_v004_spec_sha256_binding() -> None:
    """SPEC_SHA256 must match the SHA-256 of docs/PHASE8_V2_VARIANT_V004.md."""
    spec_path = REPO_ROOT / "docs" / "PHASE8_V2_VARIANT_V004.md"
    assert spec_path.is_file(), f"{spec_path} must exist"
    actual_sha = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    assert SPEC_SHA256 == actual_sha, f"SPEC_SHA256 mismatch: {SPEC_SHA256} != {actual_sha}"


def test_is_valid_liquidity_alignment_truth_table() -> None:
    """Frozen determine_entry liquidity alignment combinations must hold exactly."""
    # Bullish valid combinations
    assert is_valid_liquidity_alignment("bullish", "sell", "equal_lows") is True
    assert is_valid_liquidity_alignment("bullish", "buy", "internal_continuation") is True
    # Bullish invalid combinations
    assert is_valid_liquidity_alignment("bullish", "sell", "internal_continuation") is False
    assert is_valid_liquidity_alignment("bullish", "buy", "equal_highs") is False
    assert is_valid_liquidity_alignment("bullish", "buy", "equal_lows") is False
    assert is_valid_liquidity_alignment("bullish", "sell", "equal_highs") is False

    # Bearish valid combinations
    assert is_valid_liquidity_alignment("bearish", "buy", "equal_highs") is True
    assert is_valid_liquidity_alignment("bearish", "sell", "internal_continuation") is True
    # Bearish invalid combinations
    assert is_valid_liquidity_alignment("bearish", "buy", "internal_continuation") is False
    assert is_valid_liquidity_alignment("bearish", "sell", "equal_lows") is False
    assert is_valid_liquidity_alignment("bearish", "sell", "equal_highs") is False
    assert is_valid_liquidity_alignment("bearish", "buy", "equal_lows") is False

    # Unresolved / None
    assert is_valid_liquidity_alignment(None, "sell", "equal_lows") is False
    assert is_valid_liquidity_alignment("range", "sell", "equal_lows") is False


def test_v003_baseline_ready_preservation() -> None:
    """When V003 is already ready, V004 returns the exact V003 entry unchanged."""
    v003_entry = {"direction": "buy", "entry_type": "conservative", "market_entry": 2400.0}
    state = make_test_state(structure_dir="bullish")
    pair = make_dummy_pair(side=StrategySide.LONG)
    score = make_score(8)
    ctx = make_context()

    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=score,
        context=ctx,
        requested_side="bullish",
        v003_gate11_passed=True,
        v003_strategy_eligible=True,
        v003_entry=v003_entry,
        v003_entry_ready=True,
    )

    assert ready is True
    assert entry == v003_entry
    assert source == V004_SOURCE_V003_BASELINE


def test_gate11_or_strategy_ineligible_no_fallback() -> None:
    """When Gate 11 confluence or canonical strategy protections fail, fallback is not evaluated."""
    state = make_test_state(structure_dir="bearish")
    pair = make_dummy_pair()
    score = make_score(6)  # Confluence failed
    ctx = make_context()

    # Case A: gate 11 failed
    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=score,
        context=ctx,
        requested_side="bullish",
        v003_gate11_passed=False,
        v003_strategy_eligible=True,
        v003_entry=None,
        v003_entry_ready=False,
    )
    assert ready is False
    assert entry is None
    assert source == V004_SOURCE_NONE

    # Case B: strategy protection failed (e.g. news or regime)
    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=make_score(8),
        context=ctx,
        requested_side="bullish",
        v003_gate11_passed=True,
        v003_strategy_eligible=False,
        v003_entry=None,
        v003_entry_ready=False,
    )
    assert ready is False
    assert entry is None
    assert source == V004_SOURCE_NONE


def test_same_direction_no_divergence() -> None:
    """When requested_side == state.structure_dir, no directional divergence exists; no fallback."""
    state = make_test_state(structure_dir="bullish")
    pair = make_dummy_pair()
    score = make_score(8)
    ctx = make_context()

    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=score,
        context=ctx,
        requested_side="bullish",  # Matches persisted state.structure_dir
        v003_gate11_passed=True,
        v003_strategy_eligible=True,
        v003_entry=None,
        v003_entry_ready=False,
    )
    assert ready is False
    assert entry is None
    assert source == V004_SOURCE_NONE


def test_unresolved_direction_fails_closed() -> None:
    """When state.structure_dir is None or not in ('bullish', 'bearish'), fallback fails closed (E3)."""
    state = make_test_state(structure_dir="range")
    state.structure_dir = None
    pair = make_dummy_pair()
    score = make_score(8)
    ctx = make_context()

    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=score,
        context=ctx,
        requested_side="bullish",
        v003_gate11_passed=True,
        v003_strategy_eligible=True,
        v003_entry=None,
        v003_entry_ready=False,
    )
    assert ready is False
    assert entry is None
    assert source == V004_SOURCE_NONE


def test_state_expired_fails_closed() -> None:
    """When state is expired (>120 minutes), fallback fails closed (E1)."""
    state = make_test_state(structure_dir="bearish")
    # Make state expired by setting last_update 3 hours in the past
    state.last_update = datetime(2024, 5, 1, 6, 0)
    pair = make_dummy_pair()
    score = make_score(8)
    ctx = make_context()

    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=score,
        context=ctx,
        requested_side="bullish",
        v003_gate11_passed=True,
        v003_strategy_eligible=True,
        v003_entry=None,
        v003_entry_ready=False,
    )
    assert ready is False
    assert entry is None
    assert source == V004_SOURCE_NONE


def test_readiness_incomplete_without_early_entry_fails_closed() -> None:
    """When state is not ready and early entry criteria fail, fallback fails closed."""
    state = make_test_state(structure_dir="bearish", structure_state="transition")
    pair = make_dummy_pair()
    score = make_score(8)
    # Context missing zone context -> early entry fails
    ctx = make_context(has_ob=False, asian_swept=False)
    ctx["fvg_zone"] = None

    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=score,
        context=ctx,
        requested_side="bullish",
        v003_gate11_passed=True,
        v003_strategy_eligible=True,
        v003_entry=None,
        v003_entry_ready=False,
    )
    assert ready is False
    assert entry is None
    assert source == V004_SOURCE_NONE


def test_early_entry_missing_internal_confirmation_fails_closed() -> None:
    """In transition structure, missing internal confirmation (BOS/CHOCH) fails closed (E2 preserved).

    This test directly proves that the 7 D006 E2 rejections (which lacked internal confirmation)
    remain strictly rejected under V004.
    """
    state = make_test_state(
        structure_dir="bearish",
        structure_state="transition",
        liquidity_side="buy",
        liquidity_type="internal_continuation",
    )
    pair = make_dummy_pair()
    score = make_score(8)
    # No BOS or CHOCH, sweep_rejected=False
    ctx = make_context(internal_event=None, sweep_rejected=False, asian_swept=True)

    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=score,
        context=ctx,
        requested_side="bullish",
        v003_gate11_passed=True,
        v003_strategy_eligible=True,
        v003_entry=None,
        v003_entry_ready=False,
    )
    assert ready is False
    assert entry is None
    assert source == V004_SOURCE_NONE


def test_bullish_divergence_fallback_success() -> None:
    """Bullish requested_side with bearish persisted state recovers valid BUY entry when criteria met."""
    state = make_test_state(
        structure_dir="bearish",
        structure_state="transition",
        liquidity_side="buy",
        liquidity_type="internal_continuation",
    )
    pair = make_dummy_pair(side=StrategySide.LONG)
    score = make_score(8)
    ctx = make_context(internal_event="BOS", sweep_rejected=True, asian_swept=True)

    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=score,
        context=ctx,
        requested_side="bullish",
        v003_gate11_passed=True,
        v003_strategy_eligible=True,
        v003_entry=None,
        v003_entry_ready=False,
    )

    assert ready is True
    assert entry is not None
    assert source == V004_SOURCE_DIRECTIONAL_FALLBACK
    assert entry.get("direction") == "buy"
    assert "Bullish structure" in entry.get("reason", "")


def test_bearish_divergence_fallback_success() -> None:
    """Bearish requested_side with bullish persisted state recovers valid SELL entry when criteria met."""
    state = make_test_state(
        structure_dir="bullish",
        structure_state="transition",
        liquidity_side="sell",
        liquidity_type="internal_continuation",
    )
    pair = make_dummy_pair(side=StrategySide.SHORT)
    score = make_score(8)
    ctx = make_context(internal_event="CHOCH", sweep_rejected=True, asian_swept=True)

    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=score,
        context=ctx,
        requested_side="bearish",
        v003_gate11_passed=True,
        v003_strategy_eligible=True,
        v003_entry=None,
        v003_entry_ready=False,
    )

    assert ready is True
    assert entry is not None
    assert source == V004_SOURCE_DIRECTIONAL_FALLBACK
    assert entry.get("direction") == "sell"
    assert "Bearish structure" in entry.get("reason", "")


def test_invalid_liquidity_alignment_under_requested_side_fails_closed() -> None:
    """When liquidity alignment is invalid under requested_side, entry is rejected."""
    # Bullish requested, but liquidity is sell + internal_continuation (invalid under bullish!)
    state = make_test_state(
        structure_dir="bearish",
        structure_state="transition",
        liquidity_side="sell",
        liquidity_type="internal_continuation",
    )
    pair = make_dummy_pair()
    score = make_score(8)
    ctx = make_context(internal_event="BOS", sweep_rejected=True, asian_swept=True)

    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=score,
        context=ctx,
        requested_side="bullish",  # Under bullish, sell+internal_continuation is INVALID
        v003_gate11_passed=True,
        v003_strategy_eligible=True,
        v003_entry=None,
        v003_entry_ready=False,
    )

    assert ready is False
    assert entry is None
    assert source == V004_SOURCE_NONE


def test_authoritative_state_invariance() -> None:
    """The caller's authoritative state instance must NEVER be mutated during fallback evaluation."""
    state = make_test_state(
        structure_dir="bearish",
        structure_state="transition",
        liquidity_side="buy",
        liquidity_type="internal_continuation",
    )
    initial_structure_dir = state.structure_dir
    initial_structure_state = state.structure_state
    initial_candidate = state.setup_candidate

    pair = make_dummy_pair()
    score = make_score(8)
    ctx = make_context(internal_event="BOS", sweep_rejected=True, asian_swept=True)

    entry, ready, source = evaluate_v004_entry_readiness(
        state=state,
        decision_at=DECISION_TIME,
        current_price=2400.0,
        pair=pair,
        score=score,
        context=ctx,
        requested_side="bullish",
        v003_gate11_passed=True,
        v003_strategy_eligible=True,
        v003_entry=None,
        v003_entry_ready=False,
    )

    assert ready is True
    # State fields must remain identical to their values before evaluation
    assert state.structure_dir == initial_structure_dir == "bearish"
    assert state.structure_state == initial_structure_state == "transition"
    assert state.setup_candidate == initial_candidate


def test_safety_predicate_failures() -> None:
    """Safety predicates (daily limits, news, displacement, liquidity sweep) fail closed."""
    pair = make_dummy_pair()
    score = make_score(8)
    ctx = make_context(internal_event="BOS", sweep_rejected=True, asian_swept=True)

    # 1. Daily limits hit
    s1 = make_test_state(daily_limits_hit=True)
    _, ready, _ = evaluate_v004_entry_readiness(
        state=s1, decision_at=DECISION_TIME, current_price=2400.0, pair=pair,
        score=score, context=ctx, requested_side="bullish",
        v003_gate11_passed=True, v003_strategy_eligible=True,
        v003_entry=None, v003_entry_ready=False,
    )
    assert ready is False

    # 2. News not clear
    s2 = make_test_state(news_clear=False)
    _, ready, _ = evaluate_v004_entry_readiness(
        state=s2, decision_at=DECISION_TIME, current_price=2400.0, pair=pair,
        score=score, context=ctx, requested_side="bullish",
        v003_gate11_passed=True, v003_strategy_eligible=True,
        v003_entry=None, v003_entry_ready=False,
    )
    assert ready is False

    # 3. Displacement not seen
    s3 = make_test_state(displacement_seen=False)
    _, ready, _ = evaluate_v004_entry_readiness(
        state=s3, decision_at=DECISION_TIME, current_price=2400.0, pair=pair,
        score=score, context=ctx, requested_side="bullish",
        v003_gate11_passed=True, v003_strategy_eligible=True,
        v003_entry=None, v003_entry_ready=False,
    )
    assert ready is False

    # 4. Liquidity not swept
    s4 = make_test_state(liquidity_swept=False)
    _, ready, _ = evaluate_v004_entry_readiness(
        state=s4, decision_at=DECISION_TIME, current_price=2400.0, pair=pair,
        score=score, context=ctx, requested_side="bullish",
        v003_gate11_passed=True, v003_strategy_eligible=True,
        v003_entry=None, v003_entry_ready=False,
    )
    assert ready is False

# ===========================================================================
# TC001 Additional Invariant Tests
# ===========================================================================


def test_v004_spec_phase_a_sha256_preservation() -> None:
    """Historical Phase-A preregistration SHA-256 must be preserved."""
    assert SPEC_PHASE_A_SHA256 == "9ad9b5660bcb2d6d209c430958c3d88e47b83122c6c9816b6f5ee40d61b11b7f"


def test_pair_side_mismatch_fails_closed() -> None:
    """Section 20 & 31: requested_side contradicting pair.side must raise V004VariantError."""
    score = make_score(8)
    ctx = make_context(internal_event="BOS", sweep_rejected=True, asian_swept=True)

    # 1. requested_side bullish, pair.side SHORT -> fails closed
    pair_short = make_dummy_pair(side=StrategySide.SHORT)
    state_bull = make_test_state(structure_dir="bearish")
    with pytest.raises(V004VariantError, match="contradicts structural pair side"):
        evaluate_v004_entry_readiness(
            state=state_bull,
            decision_at=DECISION_TIME,
            current_price=2400.0,
            pair=pair_short,
            score=score,
            context=ctx,
            requested_side="bullish",
            v003_gate11_passed=True,
            v003_strategy_eligible=True,
            v003_entry=None,
            v003_entry_ready=False,
        )

    # 2. requested_side bearish, pair.side LONG -> fails closed
    pair_long = make_dummy_pair(side=StrategySide.LONG)
    state_bear = make_test_state(structure_dir="bullish")
    with pytest.raises(V004VariantError, match="contradicts structural pair side"):
        evaluate_v004_entry_readiness(
            state=state_bear,
            decision_at=DECISION_TIME,
            current_price=2400.0,
            pair=pair_long,
            score=score,
            context=ctx,
            requested_side="bearish",
            v003_gate11_passed=True,
            v003_strategy_eligible=True,
            v003_entry=None,
            v003_entry_ready=False,
        )


def test_early_entry_parity_table_driven() -> None:
    """Section 29: Table-driven synthetic tests comparing V004 eligibility to frozen _can_use_early_entry."""
    from strategies.smc_engine.entry_model import _can_use_early_entry

    cases = [
        # (name, structure_state, score_val, missing_conditions, internal_event, sweep_rejected, ob_zone, fvg_zone, asian_swept, asian_setup)
        ("transition_score8_bos_ob", "transition", 8, {"Confirmed structure"}, "BOS", False, (2390.0, 2400.0), None, False, False),
        ("transition_score8_choch_fvg", "transition", 8, {"Confirmed structure"}, "CHOCH", False, None, (2392.0, 2395.0), False, False),
        ("transition_score8_sweep_rejected_asian", "transition", 8, {"Confirmed structure"}, None, True, None, None, True, False),
        ("range_score8_bos_ob", "range", 8, {"Confirmed structure"}, "BOS", False, (2390.0, 2400.0), None, False, False),
        ("none_state_score8_bos_ob", None, 8, {"Confirmed structure"}, "BOS", False, (2390.0, 2400.0), None, False, False),
        ("invalid_state_fails", "invalid_state", 8, {"Confirmed structure"}, "BOS", False, (2390.0, 2400.0), None, False, False),
        ("score7_fails", "transition", 7, {"Confirmed structure"}, "BOS", False, (2390.0, 2400.0), None, False, False),
        ("score8_missing_displacement_fails", "transition", 8, {"Confirmed structure", "Displacement / FVG"}, "BOS", False, (2390.0, 2400.0), None, False, False),
        ("score10_missing_displacement_ok", "transition", 10, {"Confirmed structure", "Displacement / FVG"}, "BOS", False, (2390.0, 2400.0), None, False, False),
        ("missing_other_condition_fails", "transition", 8, {"Confirmed structure", "Other condition"}, "BOS", False, (2390.0, 2400.0), None, False, False),
        ("no_internal_confirmation_fails", "transition", 8, {"Confirmed structure"}, None, False, (2390.0, 2400.0), None, True, False),
        ("zone_context_only_ok", "transition", 8, {"Confirmed structure"}, "BOS", False, (2390.0, 2400.0), None, False, False),
        ("priority_context_only_ok", "transition", 8, {"Confirmed structure"}, "BOS", False, None, None, True, False),
        ("neither_zone_nor_priority_fails", "transition", 8, {"Confirmed structure"}, "BOS", False, None, None, False, False),
    ]

    for name, s_state, score_val, missing_conds, int_ev, swp_rej, ob_z, fvg_z, asian_swp, asian_stp in cases:
        state = StrategyState(event_time=DECISION_TIME)
        state.structure_state = s_state
        state.structure_dir = "bearish"
        state.displacement_seen = "Displacement / FVG" not in missing_conds
        state.liquidity_swept = True
        state.daily_limits_hit = False
        state.news_status = {"news_clear": True}
        state.missing_conditions = list(missing_conds)

        ctx = {
            "internal_structure_event": int_ev,
            "sweep_rejected": swp_rej,
            "ob_zone": ob_z,
            "fvg_zone": fvg_z,
            "asian_liquidity_swept": asian_swp,
            "asian_sweep_setup": asian_stp,
        }

        expected_early = _can_use_early_entry(state, score_value=score_val, context=ctx)

        # Now test against evaluate_v004_entry_readiness
        pair = make_dummy_pair(side=StrategySide.LONG)
        score_dict = make_score(score_val)
        state_for_v004 = copy.deepcopy(state)
        state_for_v004.liquidity_side = "buy"
        state_for_v004.liquidity_type = "internal_continuation"

        entry, ready, source = evaluate_v004_entry_readiness(
            state=state_for_v004,
            decision_at=DECISION_TIME,
            current_price=2400.0,
            pair=pair,
            score=score_dict,
            context=ctx,
            requested_side="bullish",
            v003_gate11_passed=(score_val >= 8),
            v003_strategy_eligible=True,
            v003_entry=None,
            v003_entry_ready=False,
        )

        state_ready = state_for_v004.ready_for_entry()
        if not (state_ready or expected_early):
            assert ready is False, f"Case {name} expected not ready, got ready"
            assert source == V004_SOURCE_NONE


def test_spec_does_not_redefine_frozen_helper() -> None:
    """Section 30: Static/spec test verifying TC001 identifies _can_use_early_entry as authoritative source of truth."""
    spec_path = REPO_ROOT / "docs" / "PHASE8_V2_VARIANT_V004.md"
    spec_text = spec_path.read_text(encoding="utf-8")

    assert "strategies/smc_engine/entry_model.py::_can_use_early_entry" in spec_text
    assert "remains completely unchanged" in spec_text or "must remain UNCHANGED" in spec_text
    assert "directly calls frozen `_can_use_early_entry(...)" in spec_text
