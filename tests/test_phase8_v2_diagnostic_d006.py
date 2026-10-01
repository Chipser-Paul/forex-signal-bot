# -*- coding: utf-8 -*-
"""Phase-B synthetic tests for the frozen D006 diagnostic tooling (H008).

Synthetic fixtures only — no Fold-01 empirical data, no historical store,
no external evidence. Proves, before any empirical access:

* Production parity against frozen determine_entry contract;
* E1 (STATE_EXPIRED): expired state classified, determine_entry returns None,
  authoritative state NOT reset;
* E2 (READINESS_INCOMPLETE): separate tests for each of the 5 missing conditions,
  co-occurrences, exact missing-condition reporting;
* Early-entry at score 8: transition/range early entry succeeds with valid context;
  fails when sweep/displacement/daily-limit/news/confirmation/zone missing;
  explicit guard that score 10 displacement relaxation is unreachable;
* E3 (STRUCTURE_DIRECTION_UNRESOLVED): unclassified/non-bullish/non-bearish structure;
* E4 (LIQUIDITY_ALIGNMENT_MISMATCH): exact valid combinations accepted,
  mismatched combinations rejected;
* E5 (UNMAPPED_ENTRY_REJECTION): unmapped rejection classifier and fail-closed
  INCONCLUSIVE_D006 disposition;
* StrategyState non-mutation: diagnostic observer leaves authoritative state untouched;
* Stage partition and primary ID reconciliation;
* Prior V003 result baseline reproduction verification;
* Store boundary validation and holdout/2025+ rejection;
* Banned metric rejection (P&L, win rate, expectancy, counterfactual candidates);
* Bound specification SHA-256 matches Phase-A committed specification.
"""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from backtests import phase8_v2_diagnostic_d006 as d006
from backtests.phase8_v2_diagnostic_d006 import (
    CATEGORY_E1_STATE_EXPIRED,
    CATEGORY_E2_READINESS_INCOMPLETE,
    CATEGORY_E3_STRUCTURE_DIRECTION_UNRESOLVED,
    CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH,
    CATEGORY_E5_UNMAPPED_ENTRY_REJECTION,
    D006BaselineReproductionError,
    D006Error,
    classify_entry_rejection,
    decompose_v003_decision,
    is_valid_liquidity_alignment,
    reconcile_v003_prior_result,
    validate_authorized_store_path,
)
from strategies.smc_engine.entry_model import determine_entry
from strategies.smc_engine.strategy_state import StrategyState

UTC = timezone.utc
BASE_TIME = datetime(2024, 5, 15, 14, 0, tzinfo=UTC)


def _make_ready_bullish_state(event_time: datetime = BASE_TIME) -> StrategyState:
    """Create a fully ready bullish StrategyState."""
    s = StrategyState(event_time=event_time)
    s.structure_dir = "bullish"
    s.structure_state = "confirmed"
    s.liquidity_swept = True
    s.liquidity_side = "sell"
    s.liquidity_type = "equal_lows"
    s.displacement_seen = True
    s.daily_limits_hit = False
    s.news_status = {"news_clear": True}
    s.last_update = s._now()
    return s


def _make_ready_bearish_state(event_time: datetime = BASE_TIME) -> StrategyState:
    """Create a fully ready bearish StrategyState."""
    s = StrategyState(event_time=event_time)
    s.structure_dir = "bearish"
    s.structure_state = "confirmed"
    s.liquidity_swept = True
    s.liquidity_side = "buy"
    s.liquidity_type = "equal_highs"
    s.displacement_seen = True
    s.daily_limits_hit = False
    s.news_status = {"news_clear": True}
    s.last_update = s._now()
    return s


def _score_result(score: int = 8) -> dict:
    return {"score": score, "grade": "A+", "passes_threshold": score >= 8}


# ===========================================================================
# 1. Specification and Metadata Invariance Tests
# ===========================================================================


def test_d006_spec_sha_matches_committed_file_and_retains_phase_a():
    spec_path = d006.REPO_ROOT / "docs/PHASE8_V2_DIAGNOSTIC_D006.md"
    assert spec_path.exists(), "D006 specification document must exist"
    file_bytes = spec_path.read_bytes()
    digest = hashlib.sha256(file_bytes).hexdigest()
    assert digest == d006.SPEC_SHA256, (
        f"Committed spec SHA mismatch: {digest} != {d006.SPEC_SHA256}"
    )
    assert (
        d006.SPEC_PHASE_A_SHA256
        == "a50b2e0ddfd84ecfa087dc5c347473cad40c58eb4f04c57f4f52038c73aa1ba6"
    )
    assert (
        d006.SPEC_TC001_SHA256
        == "fe29aa848c489b8d3f7a5e937efca20ef93bde9625f88d32ddd8f3ca9ec1a5eb"
    )
    assert (
        d006.SPEC_TC002_SHA256
        == "4ebe97b997f530e2d60a8b1f3a25f62e5c2e22456c7ccfc375b28b727add42ad"
    )
    assert d006.SPEC_SHA256 == d006.SPEC_TC002_SHA256


def test_provenance_contains_expected_keys():
    prov = d006.provenance(
        tooling_commit="a" * 40,
        store_identity={"fold_id": "fold-01", "coverage": "full"},
        blob_source=lambda commit, rel_path: b"content",
    )
    assert prov["diagnostic_id"] == "phase8-v2-D006"
    assert prov["linked_hypothesis_id"] == "phase8-v2-H008"
    assert prov["specification_document"] == "docs/PHASE8_V2_DIAGNOSTIC_D006.md"
    assert prov["specification_sha256"] == d006.SPEC_SHA256
    assert len(prov["tooling_commit"]) == 40
    assert prov["tooling_fingerprint"] is not None


# ===========================================================================
# 2. Production Parity and E1 (State Expired) Tests
# ===========================================================================


def test_e1_expired_state_classification_and_parity():
    state = _make_ready_bullish_state()
    # Move last_update back 130 minutes (STATE_EXPIRY_MINUTES is 120)
    state.last_update = state._now() - timedelta(minutes=130)
    assert state.is_expired() is True

    original_last_update = state.last_update
    original_missing = list(state.missing_conditions)

    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    assert category == CATEGORY_E1_STATE_EXPIRED
    assert decomp["is_expired"] is True
    assert decomp["state_age_minutes"] >= 120.0

    # Diagnostic inspection must NOT reset the authoritative state
    assert state.last_update == original_last_update
    assert state.missing_conditions == original_missing
    assert state.is_expired() is True

    # Parity: frozen determine_entry returns None for expired state
    det_copy = copy.deepcopy(state)
    det_res = determine_entry(
        "XAUUSDm",
        det_copy,
        current_price=2000.0,
        score_result=_score_result(8),
        context={},
        emit_log=None,
    )
    assert det_res is None


# ===========================================================================
# 3. Production Parity and E2 (Readiness Incomplete) Tests
# ===========================================================================


def test_e2_missing_confirmed_structure():
    state = _make_ready_bullish_state()
    state.structure_state = "unconfirmed"
    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},  # no early entry confirmation
        current_price=2000.0,
    )
    assert category == CATEGORY_E2_READINESS_INCOMPLETE
    assert "Confirmed structure" in decomp["missing_conditions"]
    assert decomp["ready_for_entry"] is False

    det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context={}, emit_log=None)
    assert det_res is None


def test_e2_missing_liquidity_sweep():
    state = _make_ready_bullish_state()
    state.liquidity_swept = False
    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    assert category == CATEGORY_E2_READINESS_INCOMPLETE
    assert "Liquidity sweep" in decomp["missing_conditions"]

    det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context={}, emit_log=None)
    assert det_res is None


def test_e2_missing_displacement():
    state = _make_ready_bullish_state()
    state.displacement_seen = False
    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    assert category == CATEGORY_E2_READINESS_INCOMPLETE
    assert "Displacement / FVG" in decomp["missing_conditions"]

    det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context={}, emit_log=None)
    assert det_res is None


def test_e2_missing_daily_limit_clear():
    state = _make_ready_bullish_state()
    state.daily_limits_hit = True
    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    assert category == CATEGORY_E2_READINESS_INCOMPLETE
    assert "Daily limit clear" in decomp["missing_conditions"]

    det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context={}, emit_log=None)
    assert det_res is None


def test_e2_missing_news_clear():
    state = _make_ready_bullish_state()
    state.news_status = {"news_clear": False}
    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    assert category == CATEGORY_E2_READINESS_INCOMPLETE
    assert "News clear" in decomp["missing_conditions"]

    det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context={}, emit_log=None)
    assert det_res is None


def test_e2_cooccurring_missing_conditions():
    state = _make_ready_bullish_state()
    state.liquidity_swept = False
    state.displacement_seen = False
    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    assert category == CATEGORY_E2_READINESS_INCOMPLETE
    assert set(decomp["missing_conditions"]) == {"Liquidity sweep", "Displacement / FVG"}


# ===========================================================================
# 4. Early-Entry Subpredicates Tests (Score 8 Context)
# ===========================================================================


def test_early_entry_allowed_at_score_8_in_transition():
    state = _make_ready_bullish_state()
    # Missing only "Confirmed structure", but structure_state is "transition"
    state.structure_state = "transition"
    ctx = {
        "internal_structure_event": "CHOCH",
        "ob_zone": (1990.0, 1995.0),
    }
    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context=ctx,
        current_price=2000.0,
    )
    # Early entry is allowed, and liquidity alignment is valid -> should produce an entry!
    assert category is None
    assert decomp["early_entry_ok"] is True

    det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context=ctx, emit_log=None)
    assert det_res is not None
    assert det_res["direction"] == "buy"


def test_early_entry_fails_when_displacement_missing_at_score_8():
    state = _make_ready_bullish_state()
    state.structure_state = "transition"
    state.displacement_seen = False  # displacement cannot be relaxed at score 8!
    ctx = {
        "internal_structure_event": "BOS",
        "ob_zone": (1990.0, 1995.0),
    }
    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context=ctx,
        current_price=2000.0,
    )
    assert category == CATEGORY_E2_READINESS_INCOMPLETE
    assert decomp["early_entry_ok"] is False

    det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context=ctx, emit_log=None)
    assert det_res is None


def test_early_entry_score_10_unreachable_guard():
    state = _make_ready_bullish_state()
    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    sub = decomp["early_entry_subpredicates"]
    assert sub["displacement_relaxation_at_score_10_unreachable_for_v003"] is True


# ===========================================================================
# 5. Production Parity and E3 (Structure Direction Unresolved) Tests
# ===========================================================================


def test_e3_structure_direction_unresolved():
    state = _make_ready_bullish_state()
    state.structure_dir = None
    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    assert category == CATEGORY_E3_STRUCTURE_DIRECTION_UNRESOLVED
    assert decomp["structure_dir"] is None

    det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context={}, emit_log=None)
    assert det_res is None


def test_e3_structure_direction_flat_unresolved():
    state = _make_ready_bullish_state()
    state.structure_dir = "range"
    category, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    assert category == CATEGORY_E3_STRUCTURE_DIRECTION_UNRESOLVED

    det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context={}, emit_log=None)
    assert det_res is None


# ===========================================================================
# 6. Production Parity and E4 (Liquidity Alignment Mismatch) Tests
# ===========================================================================


def test_e4_bullish_valid_alignments():
    # 1. sell / equal_lows
    assert is_valid_liquidity_alignment("bullish", "sell", "equal_lows") is True
    # 2. buy / internal_continuation
    assert is_valid_liquidity_alignment("bullish", "buy", "internal_continuation") is True


def test_e4_bearish_valid_alignments():
    # 1. buy / equal_highs
    assert is_valid_liquidity_alignment("bearish", "buy", "equal_highs") is True
    # 2. sell / internal_continuation
    assert is_valid_liquidity_alignment("bearish", "sell", "internal_continuation") is True


def test_e4_bullish_mismatched_alignments():
    mismatches = [
        ("buy", "equal_highs"),
        ("sell", "internal_continuation"),
        ("buy", "equal_lows"),
        ("sell", "trend_continuation"),
        (None, "equal_lows"),
        ("sell", None),
    ]
    for side, l_type in mismatches:
        assert is_valid_liquidity_alignment("bullish", side, l_type) is False
        state = _make_ready_bullish_state()
        state.liquidity_side = side
        state.liquidity_type = l_type
        category, decomp = classify_entry_rejection(
            state=state,
            score_result=_score_result(8),
            context={},
            current_price=2000.0,
        )
        assert category == CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH
        det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context={}, emit_log=None)
        assert det_res is None


def test_e4_bearish_mismatched_alignments():
    mismatches = [
        ("sell", "equal_lows"),
        ("buy", "internal_continuation"),
        ("buy", "equal_lows"),
        ("sell", "trend_continuation"),
    ]
    for side, l_type in mismatches:
        assert is_valid_liquidity_alignment("bearish", side, l_type) is False
        state = _make_ready_bearish_state()
        state.liquidity_side = side
        state.liquidity_type = l_type
        category, decomp = classify_entry_rejection(
            state=state,
            score_result=_score_result(8),
            context={},
            current_price=2000.0,
        )
        assert category == CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH
        det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context={}, emit_log=None)
        assert det_res is None


def test_valid_ready_entry_returns_no_rejection_category():
    # Bullish valid ready
    state = _make_ready_bullish_state()
    cat, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    assert cat is None
    det_res = determine_entry("XAUUSDm", copy.deepcopy(state), 2000.0, _score_result(8), context={}, emit_log=None)
    assert det_res is not None
    assert det_res["direction"] == "buy"

    # Bearish valid ready
    state_bear = _make_ready_bearish_state()
    cat_bear, decomp_bear = classify_entry_rejection(
        state=state_bear,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    assert cat_bear is None
    det_bear = determine_entry("XAUUSDm", copy.deepcopy(state_bear), 2000.0, _score_result(8), context={}, emit_log=None)
    assert det_bear is not None
    assert det_bear["direction"] == "sell"


# ===========================================================================
# 7. Production Parity and E5 (Unmapped Rejection) Fail-Closed Guard
# ===========================================================================


def test_e5_unmapped_rejection_when_production_returns_none():
    state = _make_ready_bullish_state()
    with patch(
        "backtests.phase8_v2_diagnostic_d006.determine_entry",
        return_value=None,
    ):
        cat, decomp = classify_entry_rejection(
            state=state,
            score_result=_score_result(8),
            context={},
            current_price=2000.0,
        )
        assert cat == CATEGORY_E5_UNMAPPED_ENTRY_REJECTION


def test_e5_forces_inconclusive_h008_disposition():
    obs = [
        {
            "decision_id": "dec-1",
            "v003_gate11_passed": True,
            "v003_strategy_eligible": True,
            "v003_entry_ready": False,
            "v003_fvg_evidence_source": "FINAL_SURFACE",
        }
    ]
    decomps = [
        {
            "decision_id": "dec-1",
            "fvg_evidence_source": "FINAL_SURFACE",
            "decomposition": {
                "category": CATEGORY_E5_UNMAPPED_ENTRY_REJECTION,
                "is_expired": False,
                "state_age_minutes": 5.0,
                "ready_for_entry": True,
                "missing_conditions": [],
                "structure_state": "confirmed",
                "structure_dir": "bullish",
                "liquidity_side": "sell",
                "liquidity_type": "equal_lows",
                "liquidity_alignment_valid": True,
                "liquidity_contingency_cell": "bullish x sell x equal_lows",
                "early_entry_ok": False,
                "early_entry_subpredicates": {
                    "missing_set_eligible_early": True,
                    "structure_state_early_eligible": False,
                    "score_eligible_early": True,
                    "has_internal_confirmation": False,
                    "has_zone_context": False,
                    "has_priority_context": False,
                },
            },
        }
    ]
    agg = d006.aggregate_d006(obs, decomps)
    assert agg["h008_disposition"]["proposed_disposition"] == "INCONCLUSIVE_D006"


# ===========================================================================
# 8. State Non-Mutation and Invariance Tests
# ===========================================================================


def test_classify_entry_rejection_does_not_mutate_authoritative_state():
    state = _make_ready_bullish_state()
    state.structure_state = "unconfirmed"  # will make ready_for_entry False
    assert state.missing_conditions == []

    cat, decomp = classify_entry_rejection(
        state=state,
        score_result=_score_result(8),
        context={},
        current_price=2000.0,
    )
    # The authoritative state's missing_conditions must remain unmutated!
    assert state.missing_conditions == []
    assert decomp["missing_conditions"] == ["Confirmed structure"]


# ===========================================================================
# 9. Partition Reconciliation and Primary ID Reconciliation Tests
# ===========================================================================


def test_aggregate_d006_partitions_reconcile_and_ids_match():
    obs = [
        # 1. Gate 11 fail
        {
            "decision_id": "dec-1",
            "v003_gate11_passed": False,
            "v003_strategy_eligible": False,
            "v003_entry_ready": False,
            "v003_fvg_evidence_source": "FINAL_SURFACE",
        },
        # 2. Strategy reject
        {
            "decision_id": "dec-2",
            "v003_gate11_passed": True,
            "v003_strategy_eligible": False,
            "v003_entry_ready": False,
            "v003_strategy_reasons": ["regime_volatile_filter"],
            "v003_fvg_evidence_source": "TEMPORAL_MEMORY",
        },
        # 3. Ready candidate
        {
            "decision_id": "dec-3",
            "v003_gate11_passed": True,
            "v003_strategy_eligible": True,
            "v003_entry_ready": True,
            "v003_fvg_evidence_source": "FINAL_SURFACE",
        },
        # 4. Primary population entry reject
        {
            "decision_id": "dec-4",
            "v003_gate11_passed": True,
            "v003_strategy_eligible": True,
            "v003_entry_ready": False,
            "v003_fvg_evidence_source": "TEMPORAL_MEMORY",
        },
    ]

    decomps = [
        {
            "decision_id": "dec-4",
            "fvg_evidence_source": "TEMPORAL_MEMORY",
            "decomposition": {
                "category": CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH,
                "is_expired": False,
                "state_age_minutes": 10.0,
                "ready_for_entry": True,
                "missing_conditions": [],
                "structure_state": "confirmed",
                "structure_dir": "bullish",
                "liquidity_side": "buy",
                "liquidity_type": "equal_highs",
                "liquidity_alignment_valid": False,
                "liquidity_contingency_cell": "bullish x buy x equal_highs",
                "early_entry_ok": False,
                "early_entry_subpredicates": {
                    "missing_set_eligible_early": True,
                    "structure_state_early_eligible": False,
                    "score_eligible_early": True,
                    "has_internal_confirmation": False,
                    "has_zone_context": False,
                    "has_priority_context": False,
                },
            },
        }
    ]

    agg = d006.aggregate_d006(obs, decomps)
    pops = agg["entry_stage_populations"]
    assert pops["total_gate11_entrants"] == 4
    assert pops["R_GATE11_FAIL_count"] == 1
    assert pops["R_STRATEGY_REJECT_count"] == 1
    assert pops["R_READY_count"] == 1
    assert pops["P_ENTRY_REJECT_count"] == 1
    assert pops["partition_reconciles"] is True

    prim = agg["primary_population"]
    assert prim["count"] == 1
    assert prim["decision_ids"] == ["dec-4"]
    assert prim["id_reconciliation"]["equals_canonical_strategy_pass_minus_candidate_ready"] is True

    # Stratification check
    strat = agg["fvg_source_stratification"]
    assert strat["P_ENTRY_REJECT"]["TEMPORAL_MEMORY"] == 1
    assert strat["R_READY"]["FINAL_SURFACE"] == 1


# ===========================================================================
# 10. Banned Output Guard Tests
# ===========================================================================


def test_banned_output_guard_rejects_forbidden_keys():
    doc = {
        "candidate_if_relaxed": 95,
    }
    with pytest.raises(d006.D006Error, match="prohibited metric key"):
        d006._reject_banned_metrics(doc)


def test_banned_output_guard_rejects_profitability_metrics():
    for forbidden in ["pnl", "win_rate", "expectancy", "drawdown", "sharpe"]:
        doc = {forbidden: 1.5}
        with pytest.raises(d006.D006Error, match="prohibited metric key"):
            d006._reject_banned_metrics(doc)


# ===========================================================================
# 11. Store Boundary and Path Validation Tests
# ===========================================================================


def test_validate_authorized_store_path_accepts_canonical():
    validate_authorized_store_path("C:/data/stores/fold-01-a8b406884ab3525a")


def test_validate_authorized_store_path_rejects_holdout_and_other_folds():
    with pytest.raises(Exception, match="holdout"):
        validate_authorized_store_path("C:/data/holdout/store")
    with pytest.raises(Exception, match="unauthorized fold"):
        validate_authorized_store_path("C:/data/stores/fold-02-abc")
    with pytest.raises(Exception, match="unauthorized fold"):
        validate_authorized_store_path("C:/data/stores/fold-01-1d710826193a6767")


# ===========================================================================
# 12. Prior Result Reconciliation Tests
# ===========================================================================


def test_reconcile_v003_prior_result_skipped_synthetic():
    res = reconcile_v003_prior_result(None, [])
    assert res["status"] == "SKIPPED_SYNTHETIC"
    assert res["reconciles"] is True


def test_reconcile_v003_prior_result_missing_file_raises():
    with pytest.raises(D006BaselineReproductionError, match="not found"):
        reconcile_v003_prior_result("C:/nonexistent/result.json", [])


def test_reconcile_v003_prior_result_bytes_or_hash_mismatch():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tf:
        tf.write('{"small": true}')
        temp_path = tf.name
    try:
        with pytest.raises(D006BaselineReproductionError, match="bytes mismatch"):
            reconcile_v003_prior_result(temp_path, [])
    finally:
        Path(temp_path).unlink(missing_ok=True)


# ===========================================================================
# 13. Surface Assertions and Atomic Write Tests
# ===========================================================================


def test_assert_expected_surfaces_validates_accounting_and_categories():
    doc = {
        "decision_accounting": {
            "scheduled": 10,
            "reducer_classified": 5,
            "missing_history": 3,
            "unavailable_input": 2,
            "evaluation_error": 0,
            "reconciles": True,
        },
        "entry_stage_populations": {
            "partition_reconciles": True,
        },
        "primary_population": {"count": 2},
        "fvg_source_stratification": {},
        "entry_rejection_category_distribution": {
            d006.CATEGORY_E1_STATE_EXPIRED: 1,
            d006.CATEGORY_E2_READINESS_INCOMPLETE: 1,
            d006.CATEGORY_E3_STRUCTURE_DIRECTION_UNRESOLVED: 0,
            d006.CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH: 0,
            d006.CATEGORY_E5_UNMAPPED_ENTRY_REJECTION: 0,
        },
        "entry_rejection_by_source": {},
        "state_expiry_surface": {},
        "ready_for_entry_surface": {},
        "early_entry_surface": {},
        "structure_and_liquidity_surface": {},
        "strategy_rejection_context": {},
        "h008_disposition": {
            "proposed_disposition": "H008_SUPERVISORY_INTERPRETATION_REQUIRED"
        },
    }
    d006.assert_expected_surfaces(doc)


def test_assert_expected_surfaces_catches_accounting_mismatch():
    doc = {
        "decision_accounting": {
            "scheduled": 10,
            "reducer_classified": 5,
            "missing_history": 2,  # 5 + 2 + 2 = 9 != 10
            "unavailable_input": 2,
            "evaluation_error": 0,
        },
        "entry_stage_populations": {"partition_reconciles": True},
        "primary_population": {"count": 0},
        "fvg_source_stratification": {},
        "entry_rejection_category_distribution": {cat: 0 for cat in d006.REJECTION_CATEGORIES},
        "entry_rejection_by_source": {},
        "state_expiry_surface": {},
        "ready_for_entry_surface": {},
        "early_entry_surface": {},
        "structure_and_liquidity_surface": {},
        "strategy_rejection_context": {},
        "h008_disposition": {"proposed_disposition": "INCONCLUSIVE_D006"},
    }
    with pytest.raises(d006.D006AccountingError, match="accounting does not reconcile"):
        d006.assert_expected_surfaces(doc)


def test_write_result_refuses_overwrite(tmp_path):
    out_dir = tmp_path / "d006_out"
    doc = {"test": "data"}
    rendered = b'{"test": "data"}'
    target, digest = d006.write_result(doc, rendered, out_dir)
    assert target.exists()
    assert len(digest) == 64

    # Second write must refuse overwrite
    with pytest.raises(d006.D006Error, match="refusing overwrite"):
        d006.write_result(doc, rendered, out_dir)


# ===========================================================================
# 14. TC001 Regression Tests (Defect A and Defect B)
# ===========================================================================


def test_no_50_percent_threshold_in_code_static_scan():
    """Static assertion: executable D006 module contains no mechanical 50% cutoff."""
    code_path = d006.REPO_ROOT / "backtests/phase8_v2_diagnostic_d006.py"
    content = code_path.read_text(encoding="utf-8")
    import re
    assert not re.search(r"0\.50", content), "0.50 found in D006 module"
    assert not re.search(r"50%", content), "50% found in D006 module"
    assert not re.search(r"concentration_ratio", content), "concentration_ratio found in D006 module"


def test_h008_disposition_emits_supervisory_interpretation_required_across_all_concentrations():
    """When E5 = 0, all concentrations (<50%, 50%, >50%, 100%) emit H008_SUPERVISORY_INTERPRETATION_REQUIRED."""
    def _run_with_counts(cat_counts: dict[str, int]):
        obs = []
        decomps = []
        i = 0
        for cat, cnt in cat_counts.items():
            for _ in range(cnt):
                did = f"dec-{i}"
                i += 1
                obs.append({
                    "decision_id": did,
                    "v003_gate11_passed": True,
                    "v003_strategy_eligible": True,
                    "v003_entry_ready": False,
                    "v003_fvg_evidence_source": "FINAL_SURFACE",
                })
                decomps.append({
                    "decision_id": did,
                    "fvg_evidence_source": "FINAL_SURFACE",
                    "decomposition": {
                        "category": cat,
                        "is_expired": cat == CATEGORY_E1_STATE_EXPIRED,
                        "state_age_minutes": 10.0,
                        "ready_for_entry": cat != CATEGORY_E2_READINESS_INCOMPLETE,
                        "missing_conditions": ["Liquidity sweep"] if cat == CATEGORY_E2_READINESS_INCOMPLETE else [],
                        "structure_state": "confirmed",
                        "structure_dir": "bullish" if cat != CATEGORY_E3_STRUCTURE_DIRECTION_UNRESOLVED else "unresolved",
                        "liquidity_side": "sell",
                        "liquidity_type": "equal_lows",
                        "liquidity_alignment_valid": cat != CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH,
                        "liquidity_contingency_cell": "cell",
                        "early_entry_ok": False,
                        "early_entry_subpredicates": {
                            "missing_set_eligible_early": True,
                            "structure_state_early_eligible": False,
                            "score_eligible_early": True,
                            "has_internal_confirmation": False,
                            "has_zone_context": False,
                            "has_priority_context": False,
                        },
                    },
                })
        return d006.aggregate_d006(obs, decomps)

    # 1. < 50% concentration (4 / 12 = 33.3%)
    agg1 = _run_with_counts({
        CATEGORY_E1_STATE_EXPIRED: 4,
        CATEGORY_E2_READINESS_INCOMPLETE: 3,
        CATEGORY_E3_STRUCTURE_DIRECTION_UNRESOLVED: 3,
        CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH: 2,
    })
    disp1 = agg1["h008_disposition"]
    assert disp1["proposed_disposition"] == "H008_SUPERVISORY_INTERPRETATION_REQUIRED"
    assert disp1["concentration_metrics"]["dominant_category"] == CATEGORY_E1_STATE_EXPIRED
    assert disp1["concentration_metrics"]["dominant_count"] == 4
    assert disp1["concentration_metrics"]["dominant_share"] == round(4 / 12, 4)

    # 2. Exactly 50% concentration (5 / 10 = 50.0%)
    agg2 = _run_with_counts({
        CATEGORY_E2_READINESS_INCOMPLETE: 5,
        CATEGORY_E1_STATE_EXPIRED: 2,
        CATEGORY_E3_STRUCTURE_DIRECTION_UNRESOLVED: 2,
        CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH: 1,
    })
    disp2 = agg2["h008_disposition"]
    assert disp2["proposed_disposition"] == "H008_SUPERVISORY_INTERPRETATION_REQUIRED"
    assert disp2["concentration_metrics"]["dominant_category"] == CATEGORY_E2_READINESS_INCOMPLETE
    assert disp2["concentration_metrics"]["dominant_count"] == 5
    assert disp2["concentration_metrics"]["dominant_share"] == 0.5

    # 3. > 50% concentration (7 / 10 = 70.0%)
    agg3 = _run_with_counts({
        CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH: 7,
        CATEGORY_E1_STATE_EXPIRED: 1,
        CATEGORY_E2_READINESS_INCOMPLETE: 1,
        CATEGORY_E3_STRUCTURE_DIRECTION_UNRESOLVED: 1,
    })
    disp3 = agg3["h008_disposition"]
    assert disp3["proposed_disposition"] == "H008_SUPERVISORY_INTERPRETATION_REQUIRED"
    assert disp3["concentration_metrics"]["dominant_category"] == CATEGORY_E4_LIQUIDITY_ALIGNMENT_MISMATCH
    assert disp3["concentration_metrics"]["dominant_count"] == 7
    assert disp3["concentration_metrics"]["dominant_share"] == 0.7

    # 4. 100% concentration (10 / 10 = 100.0%)
    agg4 = _run_with_counts({
        CATEGORY_E1_STATE_EXPIRED: 10,
    })
    disp4 = agg4["h008_disposition"]
    assert disp4["proposed_disposition"] == "H008_SUPERVISORY_INTERPRETATION_REQUIRED"
    assert disp4["concentration_metrics"]["dominant_category"] == CATEGORY_E1_STATE_EXPIRED
    assert disp4["concentration_metrics"]["dominant_count"] == 10
    assert disp4["concentration_metrics"]["dominant_share"] == 1.0


def test_e5_nonzero_always_forces_inconclusive():
    """Even if a single category has 99% concentration, any E5 > 0 forces INCONCLUSIVE_D006."""
    obs = []
    decomps = []
    for i in range(99):
        did = f"dec-{i}"
        obs.append({
            "decision_id": did,
            "v003_gate11_passed": True,
            "v003_strategy_eligible": True,
            "v003_entry_ready": False,
            "v003_fvg_evidence_source": "FINAL_SURFACE",
        })
        decomps.append({
            "decision_id": did,
            "fvg_evidence_source": "FINAL_SURFACE",
            "decomposition": {
                "category": CATEGORY_E1_STATE_EXPIRED,
                "is_expired": True,
                "state_age_minutes": 130.0,
                "ready_for_entry": True,
                "missing_conditions": [],
                "structure_state": "confirmed",
                "structure_dir": "bullish",
                "liquidity_side": "sell",
                "liquidity_type": "equal_lows",
                "liquidity_alignment_valid": True,
                "liquidity_contingency_cell": "c",
                "early_entry_ok": False,
                "early_entry_subpredicates": {
                    "missing_set_eligible_early": True,
                    "structure_state_early_eligible": False,
                    "score_eligible_early": True,
                    "has_internal_confirmation": False,
                    "has_zone_context": False,
                    "has_priority_context": False,
                },
            },
        })
    did_e5 = "dec-99"
    obs.append({
        "decision_id": did_e5,
        "v003_gate11_passed": True,
        "v003_strategy_eligible": True,
        "v003_entry_ready": False,
        "v003_fvg_evidence_source": "FINAL_SURFACE",
    })
    decomps.append({
        "decision_id": did_e5,
        "fvg_evidence_source": "FINAL_SURFACE",
        "decomposition": {
            "category": CATEGORY_E5_UNMAPPED_ENTRY_REJECTION,
            "is_expired": False,
            "state_age_minutes": 10.0,
            "ready_for_entry": True,
            "missing_conditions": [],
            "structure_state": "confirmed",
            "structure_dir": "bullish",
            "liquidity_side": "sell",
            "liquidity_type": "equal_lows",
            "liquidity_alignment_valid": True,
            "liquidity_contingency_cell": "c",
            "early_entry_ok": False,
            "early_entry_subpredicates": {
                "missing_set_eligible_early": True,
                "structure_state_early_eligible": False,
                "score_eligible_early": True,
                "has_internal_confirmation": False,
                "has_zone_context": False,
                "has_priority_context": False,
            },
        },
    })
    agg = d006.aggregate_d006(obs, decomps)
    assert agg["h008_disposition"]["proposed_disposition"] == "INCONCLUSIVE_D006"


def _create_mock_v003_result_file(tmp_path: Path, candidate_ids: list[str], setup_ids: list[str]):
    """Helper to create a temporary sealed V003 result artifact with valid byte size and hash."""
    doc = {
        "V003_variant_funnel": {
            "gate_11_v003": {"entered": 526, "failed": 388, "passed": 138},
            "canonical_strategy_v003": {"entered": 138, "failed": 28, "passed": 110},
            "gate_12_13_rr_entry_v003": {"entered": 110, "failed": 29, "passed": len(candidate_ids)},
        },
        "candidate_surface": {
            "candidate_ready": len(candidate_ids),
            "candidates": [
                {"decision_id": did, "setup_id": sid}
                for did, sid in zip(candidate_ids, setup_ids)
            ],
            "unique_candidate_setup_ids": len(set(setup_ids)),
            "duplicate_candidate_setup_id_occurrences": len(setup_ids) - len(set(setup_ids)),
        },
    }
    raw = json.dumps(doc, indent=2).encode("utf-8")
    target = tmp_path / "mock_v003_result.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return target, len(raw), hashlib.sha256(raw).hexdigest()


def test_reconcile_v003_upstream_count_matching_and_mismatching(tmp_path, monkeypatch):
    """Test upstream count reconciliation accepts matching counts and rejects count mismatches."""
    cand_ids = [f"cand-{i}" for i in range(81)]
    setup_ids = [f"setup-{i}" for i in range(81)]
    path, raw_len, digest = _create_mock_v003_result_file(tmp_path, cand_ids, setup_ids)

    monkeypatch.setattr(d006, "V003_SEALED_RESULT_BYTES", raw_len)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_SHA256", digest)

    def _build_obs(n_entrants=526, n_g11_pass=138, n_strat_pass=110, n_ready=81):
        obs = []
        for i in range(n_entrants):
            did = cand_ids[i] if i < n_ready else f"other-{i}"
            g11_pass = i < n_g11_pass
            strat_pass = i < n_strat_pass
            ready = i < n_ready
            sid = setup_ids[i] if ready else None
            obs.append({
                "decision_id": did,
                "v003_gate11_passed": g11_pass,
                "v003_strategy_eligible": strat_pass,
                "v003_entry_ready": ready,
                "v003_setup_id": sid,
            })
        return obs

    # 1. Matching case
    matching_obs = _build_obs()
    res = reconcile_v003_prior_result(path, matching_obs)
    assert res["status"] == "SEALED_V003_BASELINE_RECONCILED"
    assert res["reconciles"] is True
    assert res["upstream_decision_id_digests"]["identity_sealing_note"] == "FIRST_IDENTITY_SEALED_BY_D006"
    assert "gate11_entrants_sha256" in res["upstream_decision_id_digests"]
    assert res["candidate_setup_id_reconciliation"]["matches_prior_v003"] is True

    # 2. Entrant count mismatch (525 != 526)
    obs_bad_entrants = _build_obs(n_entrants=525)
    with pytest.raises(D006BaselineReproductionError, match="Gate-11 entrant count mismatch"):
        reconcile_v003_prior_result(path, obs_bad_entrants)

    # 3. Gate 11 pass count mismatch (137 != 138)
    obs_bad_g11 = _build_obs(n_g11_pass=137)
    with pytest.raises(D006BaselineReproductionError, match="Gate-11 pass count mismatch"):
        reconcile_v003_prior_result(path, obs_bad_g11)

    # 4. Canonical strategy pass count mismatch (109 != 110)
    obs_bad_strat = _build_obs(n_strat_pass=109)
    with pytest.raises(D006BaselineReproductionError, match="Canonical-strategy pass count mismatch"):
        reconcile_v003_prior_result(path, obs_bad_strat)

    # 5. Candidate ready count mismatch (80 != 81)
    obs_bad_ready = _build_obs(n_ready=80)
    with pytest.raises(D006BaselineReproductionError, match="Candidate-ready count mismatch"):
        reconcile_v003_prior_result(path, obs_bad_ready)


def test_reconcile_v003_candidate_identity_tampering(tmp_path, monkeypatch):
    """Test candidate reconciliation fails on altered decision ID, setup ID, unique count, or duplicate count."""
    cand_ids = [f"cand-{i}" for i in range(81)]
    setup_ids = [f"setup-{i}" for i in range(81)]
    path, raw_len, digest = _create_mock_v003_result_file(tmp_path, cand_ids, setup_ids)

    monkeypatch.setattr(d006, "V003_SEALED_RESULT_BYTES", raw_len)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_SHA256", digest)

    def _build_obs():
        obs = []
        for i in range(526):
            ready = i < 81
            did = cand_ids[i] if ready else f"other-{i}"
            sid = setup_ids[i] if ready else None
            obs.append({
                "decision_id": did,
                "v003_gate11_passed": i < 138,
                "v003_strategy_eligible": i < 110,
                "v003_entry_ready": ready,
                "v003_setup_id": sid,
            })
        return obs

    # 1. Altered candidate decision ID
    obs1 = _build_obs()
    obs1[0]["decision_id"] = "tampered-decision-id"
    with pytest.raises(D006BaselineReproductionError, match="Candidate decision ID set does not reproduce"):
        reconcile_v003_prior_result(path, obs1)

    # 2. Altered candidate setup ID
    obs2 = _build_obs()
    obs2[0]["v003_setup_id"] = "tampered-setup-id"
    with pytest.raises(D006BaselineReproductionError, match="Candidate setup_id mismatch"):
        reconcile_v003_prior_result(path, obs2)

    # 3. Tampered unique setup ID count in prior result
    path_tampered_unique, raw_len_u, digest_u = _create_mock_v003_result_file(
        tmp_path / "u", cand_ids, setup_ids
    )
    # Modify unique_candidate_setup_ids in the file
    doc_u = json.loads(path_tampered_unique.read_text(encoding="utf-8"))
    doc_u["candidate_surface"]["unique_candidate_setup_ids"] = 99
    raw_u = json.dumps(doc_u, indent=2).encode("utf-8")
    path_tampered_unique.write_bytes(raw_u)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_BYTES", len(raw_u))
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_SHA256", hashlib.sha256(raw_u).hexdigest())
    with pytest.raises(D006BaselineReproductionError, match="Unique setup ID count mismatch"):
        reconcile_v003_prior_result(path_tampered_unique, _build_obs())

    # 4. Tampered duplicate occurrences count in prior result
    path_tampered_dup, raw_len_d, digest_d = _create_mock_v003_result_file(
        tmp_path / "d", cand_ids, setup_ids
    )
    doc_d = json.loads(path_tampered_dup.read_text(encoding="utf-8"))
    doc_d["candidate_surface"]["duplicate_candidate_setup_id_occurrences"] = 5
    raw_d = json.dumps(doc_d, indent=2).encode("utf-8")
    path_tampered_dup.write_bytes(raw_d)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_BYTES", len(raw_d))
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_SHA256", hashlib.sha256(raw_d).hexdigest())
    with pytest.raises(D006BaselineReproductionError, match="Duplicate setup ID occurrences mismatch"):
        reconcile_v003_prior_result(path_tampered_dup, _build_obs())


def test_aggregate_d006_primary_id_set_tampering_raises():
    """Primary set reconciliation fails if an ID is altered while preserving count."""
    # Here, dec-fail passed strategy but failed Gate 11: invalid upstream flow causing set mismatch
    obs = [
        {
            "decision_id": "dec-strat-1",
            "v003_gate11_passed": True,
            "v003_strategy_eligible": True,
            "v003_entry_ready": False,
            "v003_fvg_evidence_source": "FINAL_SURFACE",
        },
        {
            "decision_id": "dec-fail-g11",
            "v003_gate11_passed": False,
            "v003_strategy_eligible": True,
            "v003_entry_ready": False,
            "v003_fvg_evidence_source": "FINAL_SURFACE",
        },
    ]
    decomps = []
    with pytest.raises(d006.D006AccountingError, match="Primary population decision IDs do not equal"):
        d006.aggregate_d006(obs, decomps)
# ===========================================================================
# 11. TC002 Replay Loop Parity, Strict Candidate Identity & Governance Tests
# ===========================================================================


class _MockSnapshot:
    def __init__(self, decision_id: str, available_at_ms: int = 1704110400000, payload_dict: dict | None = None):
        self.decision_id = decision_id
        self.available_at_ms = available_at_ms
        self.gate_payload = json.dumps(payload_dict or {})


class _MockStore:
    def __init__(self, snapshots: list[_MockSnapshot]):
        self.identity = {
            "fold_id": "fold-01-a8b406884ab3525a",
            "coverage": "full",
        }
        self.snapshots = snapshots
        self.table = "MOCK_TABLE_OBJECT"


def test_run_d006_run_loop_contract(monkeypatch):
    """Section 27: Verify exact run_d006 contract parity with frozen V003."""
    calls = {
        "snapshot_rows_arg": None,
        "classify_snapshot_args": [],
        "reference_check_args": [],
        "evaluate_decision_args": [],
        "assert_compatibility_args": [],
        "observe_v003_args": [],
    }

    snap = _MockSnapshot("dec-1", payload_dict={"gate_payload_field": "val"})
    store = _MockStore([snap])

    def mock_snapshot_rows(s):
        calls["snapshot_rows_arg"] = s
        return s.snapshots

    def mock_classify(s):
        calls["classify_snapshot_args"].append(s)
        return None  # valid reducer path

    def mock_ref_check(s):
        calls["reference_check_args"].append(s)
        return False

    mock_next_record = ("NEXT_STATE", "EXTRA_CELL")

    def mock_eval_dec(s, prior_state):
        calls["evaluate_decision_args"].append((s, prior_state))
        row = {
            "decision_id": s.decision_id,
            "action": "hold",
            "gate_results": {"gate_11_confluence_score": True},
        }
        return row, mock_next_record

    def mock_assert_compat(s):
        calls["assert_compatibility_args"].append(s)

    def mock_observe_v003(row, s, prior_state, config, decision_result_record):
        calls["observe_v003_args"].append({
            "row": row,
            "snapshot": s,
            "prior_state": prior_state,
            "decision_result_record": decision_result_record,
        })
        return {
            "decision_id": row["decision_id"],
            "v003_gate11_passed": False,
            "v003_strategy_eligible": False,
            "v003_entry_ready": False,
            "v003_fvg_evidence_source": "FINAL_SURFACE",
        }

    monkeypatch.setattr(d006, "_snapshot_rows", mock_snapshot_rows)
    monkeypatch.setattr(d006, "classify_snapshot", mock_classify)
    monkeypatch.setattr(d006, "_reference_check_failed", mock_ref_check)
    monkeypatch.setattr(d006, "evaluate_orchestration_decision", mock_eval_dec)
    monkeypatch.setattr(d006, "assert_store_semantic_compatibility", mock_assert_compat)
    monkeypatch.setattr(d006, "observe_v003_decision", mock_observe_v003)

    doc, _ = d006.run_d006(store, tooling_commit="a" * 40, prior_v003_result_path=None, blob_source=lambda c, r: b"mock")

    # 1. _snapshot_rows receives the STORE object, not store.table
    assert calls["snapshot_rows_arg"] is store
    assert calls["snapshot_rows_arg"] is not store.table

    # 2. classify_snapshot receives the snapshot
    assert len(calls["classify_snapshot_args"]) == 1
    assert calls["classify_snapshot_args"][0] is snap

    # 3. _reference_check_failed receives the snapshot
    assert len(calls["reference_check_args"]) == 1
    assert calls["reference_check_args"][0] is snap

    # 4. evaluate_orchestration_decision receives (snapshot, prior_state_record)
    assert len(calls["evaluate_decision_args"]) == 1
    passed_snap, passed_prior = calls["evaluate_decision_args"][0]
    assert passed_snap is snap
    assert passed_prior is not None  # Canonical seed record

    # 5. assert_store_semantic_compatibility receives snapshot, not store
    assert len(calls["assert_compatibility_args"]) == 1
    assert calls["assert_compatibility_args"][0] is snap

    # 6. observe_v003_decision receives decision_result_record=next_record
    assert len(calls["observe_v003_args"]) == 1
    assert calls["observe_v003_args"][0]["decision_result_record"] is mock_next_record


def test_multi_snapshot_state_carry(monkeypatch):
    """Section 28: State carry advances sequentially across decisions without reset."""
    snap1 = _MockSnapshot("dec-1")
    snap2 = _MockSnapshot("dec-2")
    store = _MockStore([snap1, snap2])

    seen_prior_states = []
    record_1 = ("STATE_1",)
    record_2 = ("STATE_2",)
    records = [record_1, record_2]

    def mock_eval_dec(s, prior_state):
        seen_prior_states.append(prior_state)
        idx = 0 if s.decision_id == "dec-1" else 1
        row = {
            "decision_id": s.decision_id,
            "action": "hold",
            "gate_results": {},
        }
        return row, records[idx]

    monkeypatch.setattr(d006, "_snapshot_rows", lambda s: s.snapshots)
    monkeypatch.setattr(d006, "classify_snapshot", lambda s: None)
    monkeypatch.setattr(d006, "_reference_check_failed", lambda s: False)
    monkeypatch.setattr(d006, "evaluate_orchestration_decision", mock_eval_dec)

    d006.run_d006(store, tooling_commit="a" * 40, prior_v003_result_path=None, blob_source=lambda c, r: b"mock")

    assert len(seen_prior_states) == 2
    # First decision receives canonical seed
    assert seen_prior_states[0] is not None
    # Second decision receives exactly the first decision's next_record
    assert seen_prior_states[1] is record_1


def test_d006_bucket_accounting(monkeypatch):
    """Section 29: Synthetic snapshots for all non-reducer and evaluation buckets."""
    snap_mh = _MockSnapshot("snap-mh")
    snap_ui = _MockSnapshot("snap-ui")
    snap_ref_err = _MockSnapshot("snap-ref-err")
    snap_act_err = _MockSnapshot("snap-act-err")
    snap_ok = _MockSnapshot("snap-ok")
    store = _MockStore([snap_mh, snap_ui, snap_ref_err, snap_act_err, snap_ok])

    def mock_classify(s):
        if s.decision_id == "snap-mh":
            return ("missing_history", "historical window empty")
        if s.decision_id == "snap-ui":
            return ("unavailable_input", "feed gap")
        return None

    def mock_ref_check(s):
        return s.decision_id == "snap-ref-err"

    def mock_eval_dec(s, prior_state):
        if s.decision_id == "snap-act-err":
            return {"action": "error", "decision_id": s.decision_id}, prior_state
        return {"action": "hold", "decision_id": s.decision_id, "gate_results": {}}, prior_state

    monkeypatch.setattr(d006, "_snapshot_rows", lambda s: s.snapshots)
    monkeypatch.setattr(d006, "classify_snapshot", mock_classify)
    monkeypatch.setattr(d006, "_reference_check_failed", mock_ref_check)
    monkeypatch.setattr(d006, "evaluate_orchestration_decision", mock_eval_dec)

    doc, _ = d006.run_d006(store, tooling_commit="a" * 40, prior_v003_result_path=None, blob_source=lambda c, r: b"mock")
    acc = doc["decision_accounting"]

    assert acc["scheduled"] == 5
    assert acc["missing_history"] == 1
    assert acc["unavailable_input"] == 1
    assert acc["evaluation_error"] == 2  # ref check fail + action == "error"
    assert acc["reducer_classified"] == 1
    assert acc["reconciles"] is True


def test_gate11_semantic_compatibility_call_timing(monkeypatch):
    """Section 30: assert_store_semantic_compatibility called only on Gate-11 entrants with snapshot."""
    snap_non_g11 = _MockSnapshot("non-g11")
    snap_g11 = _MockSnapshot("g11")
    store = _MockStore([snap_non_g11, snap_g11])

    compat_calls = []

    def mock_eval_dec(s, prior_state):
        if s.decision_id == "non-g11":
            return {"decision_id": s.decision_id, "action": "hold", "gate_results": {}}, prior_state
        return {
            "decision_id": s.decision_id,
            "action": "hold",
            "gate_results": {"gate_11_confluence_score": True},
        }, prior_state

    def mock_observe_v003(row, s, prior_state, config, decision_result_record):
        return {
            "decision_id": row["decision_id"],
            "v003_gate11_passed": False,
            "v003_strategy_eligible": False,
            "v003_entry_ready": False,
            "v003_fvg_evidence_source": "NONE",
        }

    monkeypatch.setattr(d006, "_snapshot_rows", lambda s: s.snapshots)
    monkeypatch.setattr(d006, "classify_snapshot", lambda s: None)
    monkeypatch.setattr(d006, "_reference_check_failed", lambda s: False)
    monkeypatch.setattr(d006, "evaluate_orchestration_decision", mock_eval_dec)
    monkeypatch.setattr(d006, "assert_store_semantic_compatibility", lambda s: compat_calls.append(s))
    monkeypatch.setattr(d006, "observe_v003_decision", mock_observe_v003)

    d006.run_d006(store, tooling_commit="a" * 40, prior_v003_result_path=None, blob_source=lambda c, r: b"mock")

    assert len(compat_calls) == 1
    assert compat_calls[0] is snap_g11


def test_main_cli_loader_verification_and_order(monkeypatch, tmp_path):
    """Section 31: CLI execution order parse -> validate -> load(verify_rows=True) -> run -> write."""
    order = []

    def mock_validate(path):
        order.append("validate_path")

    def mock_load(path, verify_rows=False):
        assert isinstance(path, Path)
        assert verify_rows is True
        order.append("load_store")
        return "MOCK_STORE"

    def mock_run(store, tooling_commit, prior_v003_result_path):
        assert store == "MOCK_STORE"
        order.append("run_d006")
        return {"result": "ok"}, b"{}"

    def mock_write(doc, raw, out_dir):
        order.append("write_result")
        return out_dir / "out.json", "fake_digest"

    import bot.validation.market_feature_store as mfs
    monkeypatch.setattr(d006, "validate_authorized_store_path", mock_validate)
    monkeypatch.setattr(mfs, "load_feature_store", mock_load)
    monkeypatch.setattr(d006, "run_d006", mock_run)
    monkeypatch.setattr(d006, "write_result", mock_write)

    argv = [
        "--store", "C:/Users/chips/forex-signal-bot-data/phase8/feature_store/fold-01-a8b406884ab3525a",
        "--tooling-commit", "b" * 40,
        "--output-dir", str(tmp_path),
    ]
    exit_code = d006.main(argv)
    assert exit_code == 0
    assert order == ["validate_path", "load_store", "run_d006", "write_result"]


def test_candidate_null_id_fail_closed(tmp_path, monkeypatch):
    """Section 32: Missing candidate decision_id or setup_id in prior or observed fails closed."""
    cand_ids = [f"cand-{i}" for i in range(81)]
    setup_ids = [f"setup-{i}" for i in range(81)]

    def _build_obs():
        obs = []
        for i in range(526):
            ready = i < 81
            obs.append({
                "decision_id": cand_ids[i] if ready else f"other-{i}",
                "v003_gate11_passed": i < 138,
                "v003_strategy_eligible": i < 110,
                "v003_entry_ready": ready,
                "v003_setup_id": setup_ids[i] if ready else None,
            })
        return obs

    # 1. Prior candidate missing decision_id
    cand_ids_missing_did = list(cand_ids)
    cand_ids_missing_did[0] = None
    p1, rlen1, dig1 = _create_mock_v003_result_file(tmp_path / "p1", cand_ids_missing_did, setup_ids)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_BYTES", rlen1)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_SHA256", dig1)
    with pytest.raises(D006BaselineReproductionError, match="Prior candidate record missing non-null decision_id or setup_id"):
        reconcile_v003_prior_result(p1, _build_obs())

    # 2. Prior candidate missing setup_id
    setup_ids_missing_sid = list(setup_ids)
    setup_ids_missing_sid[0] = None
    p2, rlen2, dig2 = _create_mock_v003_result_file(tmp_path / "p2", cand_ids, setup_ids_missing_sid)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_BYTES", rlen2)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_SHA256", dig2)
    with pytest.raises(D006BaselineReproductionError, match="Prior candidate record missing non-null decision_id or setup_id"):
        reconcile_v003_prior_result(p2, _build_obs())

    # Good prior file for tests 3 and 4
    p_good, rlen_g, dig_g = _create_mock_v003_result_file(tmp_path / "good", cand_ids, setup_ids)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_BYTES", rlen_g)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_SHA256", dig_g)

    # 3. Observed candidate missing decision_id
    obs_missing_did = _build_obs()
    obs_missing_did[0]["decision_id"] = None
    with pytest.raises(D006BaselineReproductionError, match="Observed ready candidate missing non-null decision_id or v003_setup_id"):
        reconcile_v003_prior_result(p_good, obs_missing_did)

    # 4. Observed candidate missing v003_setup_id
    obs_missing_sid = _build_obs()
    obs_missing_sid[0]["v003_setup_id"] = None
    with pytest.raises(D006BaselineReproductionError, match="Observed ready candidate missing non-null decision_id or v003_setup_id"):
        reconcile_v003_prior_result(p_good, obs_missing_sid)


def test_candidate_pair_swap_fails_reconciliation(tmp_path, monkeypatch):
    """Section 33: Swapping two setup IDs between candidate decisions fails exact pair multiset equality."""
    cand_ids = [f"cand-{i}" for i in range(81)]
    setup_ids = [f"setup-{i}" for i in range(81)]
    path, raw_len, digest = _create_mock_v003_result_file(tmp_path, cand_ids, setup_ids)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_BYTES", raw_len)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_SHA256", digest)

    obs = []
    for i in range(526):
        ready = i < 81
        sid = setup_ids[i] if ready else None
        obs.append({
            "decision_id": cand_ids[i] if ready else f"other-{i}",
            "v003_gate11_passed": i < 138,
            "v003_strategy_eligible": i < 110,
            "v003_entry_ready": ready,
            "v003_setup_id": sid,
        })

    # Swap setup IDs between index 0 and 1
    obs[0]["v003_setup_id"], obs[1]["v003_setup_id"] = obs[1]["v003_setup_id"], obs[0]["v003_setup_id"]

    with pytest.raises(D006BaselineReproductionError, match=r"Candidate setup_id mismatch|Exact \(decision_id, setup_id\) pair multiset does not match"):
        reconcile_v003_prior_result(path, obs)


def test_candidate_duplicate_setup_ids_reconciliation(tmp_path, monkeypatch):
    """Section 34: Duplicate setup IDs are reconciled against prior metadata without deduplication."""
    cand_ids = [f"cand-{i}" for i in range(81)]
    # Duplicate setup-0 on index 1
    setup_ids = [f"setup-{i}" for i in range(81)]
    setup_ids[1] = setup_ids[0]  # Duplicate!

    path, raw_len, digest = _create_mock_v003_result_file(tmp_path, cand_ids, setup_ids)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_BYTES", raw_len)
    monkeypatch.setattr(d006, "V003_SEALED_RESULT_SHA256", digest)

    obs = []
    for i in range(526):
        ready = i < 81
        obs.append({
            "decision_id": cand_ids[i] if ready else f"other-{i}",
            "v003_gate11_passed": i < 138,
            "v003_strategy_eligible": i < 110,
            "v003_entry_ready": ready,
            "v003_setup_id": setup_ids[i] if ready else None,
        })

    res = reconcile_v003_prior_result(path, obs)
    assert res["reconciles"] is True
    assert res["candidate_setup_id_reconciliation"]["unique_setup_ids"] == 80
    assert res["candidate_setup_id_reconciliation"]["duplicate_setup_ids"] == 1


def test_set_digests_deterministic_and_tamper_detection():
    """Section 35: Deterministic decision ID SHA-256 digests and tamper detection."""
    obs = [
        {"decision_id": "d1", "v003_gate11_passed": True, "v003_strategy_eligible": True, "v003_entry_ready": True, "v003_setup_id": "s1"},
        {"decision_id": "d2", "v003_gate11_passed": True, "v003_strategy_eligible": True, "v003_entry_ready": False, "v003_fvg_evidence_source": "FINAL_SURFACE"},
        {"decision_id": "d3", "v003_gate11_passed": True, "v003_strategy_eligible": False, "v003_entry_ready": False, "v003_fvg_evidence_source": "TEMPORAL_MEMORY"},
        {"decision_id": "d4", "v003_gate11_passed": False, "v003_strategy_eligible": False, "v003_entry_ready": False, "v003_fvg_evidence_source": "NONE"},
    ]

    res = reconcile_v003_prior_result(None, obs)
    digests = res["upstream_decision_id_digests"]

    assert digests["gate11_entrants_sha256"] == hashlib.sha256(b"d1\nd2\nd3\nd4").hexdigest()
    assert digests["gate11_passers_sha256"] == hashlib.sha256(b"d1\nd2\nd3").hexdigest()
    assert digests["canonical_strategy_passers_sha256"] == hashlib.sha256(b"d1\nd2").hexdigest()
    assert digests["candidate_ready_sha256"] == hashlib.sha256(b"d1").hexdigest()
    assert digests["p_entry_reject_sha256"] == hashlib.sha256(b"d2").hexdigest()

    # Changing one ID alters digest
    obs_tampered = list(obs)
    obs_tampered[0] = dict(obs[0])
    obs_tampered[0]["decision_id"] = "d9"
    res_t = reconcile_v003_prior_result(None, obs_tampered)
    dig_t = res_t["upstream_decision_id_digests"]
    assert dig_t["gate11_entrants_sha256"] != digests["gate11_entrants_sha256"]
    assert dig_t["candidate_ready_sha256"] != digests["candidate_ready_sha256"]


def test_historical_register_immutability():
    """Section 36: Verify historical register content preserved unchanged from parent 32a41869."""
    import zlib
    blob_sha = "25321789d9bbdd5e73b6fe47f1335493dadde36f"
    obj_path = d006.REPO_ROOT / ".git" / "objects" / blob_sha[:2] / blob_sha[2:]
    if obj_path.exists():
        raw_obj = zlib.decompress(obj_path.read_bytes())
        _hdr, content_bytes = raw_obj.split(b"\x00", 1)
        data_base = json.loads(content_bytes.decode("utf-8"))
    else:
        from tests.conftest import REAL_POPEN
        import subprocess
        proc = REAL_POPEN(
            ["git", "show", "32a4186917b40fd60cd9a96197c9aae50dcb7782:baseline/phase8_v2_hypothesis_register.json"],
            cwd=str(d006.REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, _ = proc.communicate()
        data_base = json.loads(stdout.decode("utf-8"))

    reg_path = d006.REPO_ROOT / "baseline/phase8_v2_hypothesis_register.json"
    data_curr = json.loads(reg_path.read_text(encoding="utf-8"))

    # Top-level keys identical except result_records
    for k in data_base:
        if k != "result_records":
            assert data_base[k] == data_curr[k], f"Mismatch in top-level key {k}"

    # Historical result_records unchanged
    assert len(data_curr["result_records"]) == len(data_base["result_records"]) + 2
    for i, r in enumerate(data_base["result_records"]):
        assert r == data_curr["result_records"][i], f"Mismatch in historical result_records[{i}]"

    # Appended records
    assert data_curr["result_records"][-2]["correction_id"] == "phase8-v2-D006-TC001"
    assert data_curr["result_records"][-1]["correction_id"] == "phase8-v2-D006-TC002"

    # Specifically verify original H008 and D006 unchanged
    h008_base = [h for h in data_base["hypotheses"] if h["hypothesis_id"] == "phase8-v2-H008"][0]
    h008_curr = [h for h in data_curr["hypotheses"] if h["hypothesis_id"] == "phase8-v2-H008"][0]
    assert h008_base == h008_curr, "H008 registration changed!"

    d006_base = [d for d in data_base["diagnostics"] if d["diagnostic_id"] == "phase8-v2-D006"][0]
    d006_curr = [d for d in data_curr["diagnostics"] if d["diagnostic_id"] == "phase8-v2-D006"][0]
    assert d006_base == d006_curr, "D006 diagnostic registration changed!"
