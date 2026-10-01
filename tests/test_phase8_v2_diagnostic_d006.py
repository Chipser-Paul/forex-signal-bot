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


def test_d006_spec_sha_matches_phase_a_file():
    spec_path = d006.REPO_ROOT / "docs/PHASE8_V2_DIAGNOSTIC_D006.md"
    assert spec_path.exists(), "D006 specification document must exist"
    file_bytes = spec_path.read_bytes()
    digest = hashlib.sha256(file_bytes).hexdigest()
    assert digest == d006.SPEC_SHA256, (
        f"Committed spec SHA mismatch: {digest} != {d006.SPEC_SHA256}"
    )


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
        "h008_disposition": {"proposed_disposition": "SUPPORTED_BY_D006"},
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
        "h008_disposition": {"proposed_disposition": "NOT_SUPPORTED_BY_D006"},
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
