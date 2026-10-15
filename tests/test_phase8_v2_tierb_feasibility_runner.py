"""Phase-B synthetic unit and contract tests for the Tier-B Feasibility Tooling.

All tests operate strictly on synthetic fixtures and canonical manifests.
ZERO empirical data access, zero historical store reads, zero profitability metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from bot.execution.lifecycle.models import Direction, ExitReason, LifecycleStatus
from bot.validation.tierb_feasibility import (
    PLAN_ID,
    PLAN_SCHEMA,
    PLAN_CONTENT_SHA256,
    FREEZE_IDENTITY,
    DEVELOPMENT_PREDECESSOR,
    SEMANTIC_ANCHOR_COMMIT,
    EXPECTED_STRATEGY_DIGEST,
    EXPECTED_CONFIG_SHA256,
    EXPECTED_VALIDATION_DIGEST,
    EXPECTED_PROTECTED_DIGEST_V2,
    EXPECTED_LEDGER_SEAL,
    STAGE1_FUTILITY_THRESHOLD,
    STAGE1_HEADROOM_TARGET,
    STAGE2_MIN_COMPLETED_TRADES,
    PRIMARY_BASELINE_SCENARIO_ID,
    LABEL_STAGE1_FUTILITY,
    LABEL_STAGE1_HEADROOM_MET,
    LABEL_STAGE1_HEADROOM_NOT_MET,
    LABEL_STAGE2_FEASIBILITY_PASS,
    LABEL_STAGE2_SAMPLE_INSUFFICIENT,
    LABEL_END_OF_DATA_EXCLUDED,
    LABEL_GEOMETRY_ATTRITION,
    LABEL_PREFLIGHT_BLOCKAGE,
    LABEL_PARITY_FAILURE,
    MANDATORY_STAGE2_QUALIFICATIONS,
    PROHIBITED_METRICS,
    QUALIFYING_NATURAL_EXITS,
    NON_COMPLETED_EXCLUDED_STATES,
    V005_SOURCE_V003_BASELINE,
    V005_SOURCE_DIRECTIONAL_FALLBACK,
    V005_SOURCE_NONE,
    TierBFeasibilityError,
    TierBPreflightError,
    TierBParityError,
    TierBProfitabilityViolation,
    assert_zero_profitability,
    evaluate_stage1_candidates,
    pre_release_evidence_preflight,
    reconcile_completed_trades,
    verify_fold01_parity_against_sealed_v005,
    verify_plan_tc001,
    verify_tooling_integrity,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


# -----------------------------------------------------------------------------
# 1. Plan and Tooling Integrity Verification
# -----------------------------------------------------------------------------

def test_plan_tc001_verification_success() -> None:
    """Plan TC001 parses and passes schema and content SHA-256 verification."""
    plan = verify_plan_tc001(REPO_ROOT)
    assert plan["plan_id"] == PLAN_ID
    assert plan["schema_version"] == PLAN_SCHEMA
    assert plan["plan_content_sha256"] == PLAN_CONTENT_SHA256
    assert plan["zero_empirical_access"] is True
    assert plan["budget_impact"] == 0


def test_tooling_integrity_verification_success() -> None:
    """Tooling integrity binds to phase6-frozen-v2 with all four invariant digests."""
    tooling = verify_tooling_integrity(REPO_ROOT)
    assert tooling["freeze_identity"] == FREEZE_IDENTITY
    assert tooling["development_predecessor"] == DEVELOPMENT_PREDECESSOR
    assert tooling["semantic_anchor_commit"] == SEMANTIC_ANCHOR_COMMIT
    assert tooling["strategy_digest"] == EXPECTED_STRATEGY_DIGEST
    assert tooling["config_sha256"] == EXPECTED_CONFIG_SHA256
    assert tooling["validation_digest"] == EXPECTED_VALIDATION_DIGEST
    assert tooling["protected_digest_v2"] == EXPECTED_PROTECTED_DIGEST_V2
    assert tooling["ledger_seal"] == EXPECTED_LEDGER_SEAL
    assert tooling["unresolved_entities_count"] == 0
    assert tooling["verified"] is True


def test_preflight_evidence_verification(tmp_path: Path) -> None:
    """Preflight check passes with all required packages and fails if any missing."""
    # When all packages exist in repo
    res = pre_release_evidence_preflight(REPO_ROOT)
    assert res["status"] == "PREFLIGHT_PASSED"
    assert res["package_count"] >= 5

    # Mock directory missing packages
    mock_evidence = tmp_path / "evidence"
    mock_evidence.mkdir(parents=True)
    with pytest.raises(TierBPreflightError) as exc_info:
        pre_release_evidence_preflight(evidence_root=mock_evidence)
    assert LABEL_PREFLIGHT_BLOCKAGE in str(exc_info.value)


# -----------------------------------------------------------------------------
# 2. Stage 1 Candidate Evaluation & Futility/Headroom Thresholds
# -----------------------------------------------------------------------------

def _make_candidate(
    decision_id: str,
    setup_id: str,
    direction: str,
    source: str,
    ts: datetime,
    session: str = "london",
    week: str = "2024-W15",
) -> dict:
    return {
        "decision_id": decision_id,
        "setup_id": setup_id,
        "v005_setup_id": setup_id,
        "direction": direction,
        "v005_entry_direction": direction,
        "source": source,
        "v005_entry_source": source,
        "timestamp": ts.isoformat(),
        "decision_at": ts.isoformat(),
        "session": session,
        "week": week,
    }


def test_stage1_futility_stopping_condition() -> None:
    """Stage 1 raw candidate count < 30 halts with SAMPLE_SIZE_FUTILITY."""
    candidates = [
        _make_candidate(f"dec_{i}", f"setup_{i}", "buy", V005_SOURCE_V003_BASELINE, datetime(2024, 4, 15, 8, 0, tzinfo=UTC))
        for i in range(25)  # 25 < 30
    ]
    report = evaluate_stage1_candidates(candidates)
    assert report.raw_candidate_ready == 25
    assert report.futility_condition_met is True
    assert report.futility_classification == LABEL_STAGE1_FUTILITY
    assert report.headroom_target_met is False
    assert report.headroom_classification == LABEL_STAGE1_HEADROOM_NOT_MET


def test_stage1_headroom_target_evaluation() -> None:
    """Stage 1 raw candidate count >= 60 meets headroom target, 30-59 does not (non-gating)."""
    # Case A: 40 candidates (>= 30 futility pass, but < 60 headroom not met)
    candidates_40 = [
        _make_candidate(f"dec_{i}", f"setup_{i}", "buy", V005_SOURCE_V003_BASELINE, datetime(2024, 4, 15, 8, 0, tzinfo=UTC))
        for i in range(40)
    ]
    rep_40 = evaluate_stage1_candidates(candidates_40)
    assert rep_40.futility_condition_met is False
    assert rep_40.futility_classification is None
    assert rep_40.headroom_target_met is False
    assert rep_40.headroom_classification == LABEL_STAGE1_HEADROOM_NOT_MET

    # Case B: 75 candidates (>= 60 headroom met)
    candidates_75 = [
        _make_candidate(f"dec_{i}", f"setup_{i}", "sell", V005_SOURCE_DIRECTIONAL_FALLBACK, datetime(2024, 4, 15, 8, 0, tzinfo=UTC))
        for i in range(75)
    ]
    rep_75 = evaluate_stage1_candidates(candidates_75)
    assert rep_75.futility_condition_met is False
    assert rep_75.headroom_target_met is True
    assert rep_75.headroom_classification == LABEL_STAGE1_HEADROOM_MET


def test_stage1_candidate_source_and_distribution_breakdown() -> None:
    """Stage 1 produces correct baseline vs fallback, direction, and session breakdowns."""
    candidates = []
    # 50 baseline buy
    for i in range(50):
        candidates.append(_make_candidate(f"dec_{i}", f"setup_{i}", "buy", V005_SOURCE_V003_BASELINE, datetime(2024, 4, 10, 8, 0, tzinfo=UTC), session="london", week="2024-W15"))
    # 20 fallback sell
    for i in range(50, 70):
        candidates.append(_make_candidate(f"dec_{i}", f"setup_{i}", "sell", V005_SOURCE_DIRECTIONAL_FALLBACK, datetime(2024, 4, 18, 14, 0, tzinfo=UTC), session="new_york", week="2024-W16"))

    report = evaluate_stage1_candidates(
        candidates,
        evaluation_start=datetime(2024, 4, 1, tzinfo=UTC),
        evaluation_end=datetime(2024, 6, 8, tzinfo=UTC),
    )
    assert report.raw_candidate_ready == 70
    assert report.unique_setup_ids == 70
    assert report.duplicate_count == 0
    assert report.v003_baseline_count == 50
    assert report.v005_directional_fallback_count == 20
    assert report.long_count == 50
    assert report.short_count == 20
    assert report.fallback_buy_count == 0
    assert report.fallback_sell_count == 20
    assert report.session_distribution["london"] == 50
    assert report.session_distribution["new_york"] == 20
    assert report.week_distribution["2024-W15"] == 50
    assert report.week_distribution["2024-W16"] == 20


# -----------------------------------------------------------------------------
# 3. Stage 2 Completed-Trade Accounting & Reconciliation
# -----------------------------------------------------------------------------

def test_stage2_qualifying_completed_trade_pass() -> None:
    """Stage 2 passes when qualifying completed trades >= 30 under PRIMARY_BASELINE."""
    # 35 qualifying exits
    qualifying_exits = (
        [ExitReason.TAKE_PROFIT] * 15
        + [ExitReason.STOP_LOSS] * 10
        + [ExitReason.BREAK_EVEN] * 5
        + [ExitReason.TRAILING_STOP] * 3
        + [ExitReason.EMERGENCY] * 2
    )
    # Accounting components
    end_of_data = 5
    attrition = 10
    unfilled = 15
    never_opened = 5
    duplicates = 0
    raw_candidates = 35 + 5 + 10 + 15 + 5 + 0  # 70 total

    result = reconcile_completed_trades(
        raw_candidates_count=raw_candidates,
        qualifying_exits=qualifying_exits,
        end_of_data_count=end_of_data,
        attrition_count=attrition,
        unfilled_or_expired_count=unfilled,
        never_opened_count=never_opened,
        duplicates_count=duplicates,
    )

    assert result.qualifying_completed_trades == 35
    assert result.end_of_data_closed == 5
    assert result.level_or_intent_attrition == 10
    assert result.unfilled_or_expired_or_cancelled == 15
    assert result.never_opened == 5
    assert result.reconciliation_balanced is True
    assert result.feasibility_verdict == LABEL_STAGE2_FEASIBILITY_PASS
    assert result.natural_exit_distribution["TAKE_PROFIT"] == 15
    assert result.natural_exit_distribution["STOP_LOSS"] == 10
    assert result.natural_exit_distribution["BREAK_EVEN"] == 5
    assert result.natural_exit_distribution["TRAILING_STOP"] == 3
    assert result.natural_exit_distribution["EMERGENCY"] == 2


def test_stage2_insufficient_sample_verdict() -> None:
    """Stage 2 classifies LIFECYCLE_SAMPLE_INSUFFICIENT when qualifying trades < 30."""
    # Only 22 qualifying exits
    qualifying_exits = [ExitReason.STOP_LOSS] * 12 + [ExitReason.TAKE_PROFIT] * 10
    end_of_data = 8
    attrition = 20
    unfilled = 10
    raw_candidates = 22 + 8 + 20 + 10  # 60 total

    result = reconcile_completed_trades(
        raw_candidates_count=raw_candidates,
        qualifying_exits=qualifying_exits,
        end_of_data_count=end_of_data,
        attrition_count=attrition,
        unfilled_or_expired_count=unfilled,
    )

    assert result.qualifying_completed_trades == 22
    assert result.feasibility_verdict == LABEL_STAGE2_SAMPLE_INSUFFICIENT


def test_stage2_end_of_data_excluded_from_qualifying_quota() -> None:
    """END_OF_DATA positions must NOT count toward the 30-trade minimum quota."""
    # 25 qualifying exits + 10 END_OF_DATA = 35 total closed positions
    # But qualifying count must be strictly 25 (< 30) -> INSUFFICIENT
    qualifying_exits = [ExitReason.STOP_LOSS] * 15 + [ExitReason.TAKE_PROFIT] * 10
    end_of_data = 10
    raw_candidates = 25 + 10

    result = reconcile_completed_trades(
        raw_candidates_count=raw_candidates,
        qualifying_exits=qualifying_exits,
        end_of_data_count=end_of_data,
    )

    assert result.qualifying_completed_trades == 25
    assert result.end_of_data_closed == 10
    assert result.feasibility_verdict == LABEL_STAGE2_SAMPLE_INSUFFICIENT


def test_stage2_accounting_reconciliation_mismatch_fails_closed() -> None:
    """Reconciliation mismatch between raw candidates and accounted lifecycle outcomes raises error."""
    with pytest.raises(TierBFeasibilityError) as exc_info:
        reconcile_completed_trades(
            raw_candidates_count=50,
            qualifying_exits=[ExitReason.STOP_LOSS] * 30,
            end_of_data_count=5,  # 30 + 5 = 35 != 50
        )
    assert "Trade accounting reconciliation failed" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 4. Prohibited Metrics Firewall
# -----------------------------------------------------------------------------

def test_profitability_firewall_rejection() -> None:
    """Feasibility runner rejects any data structure containing prohibited profitability metrics."""
    clean_dict = {
        "candidate_count": 100,
        "completed_trades": 35,
        "exit_reasons": {"STOP_LOSS": 15, "TAKE_PROFIT": 20},
    }
    assert_zero_profitability(clean_dict)  # passes cleanly

    for bad_key in (
        "pnl", "net_profit", "gross_profit", "win_rate", "profit_factor",
        "expectancy", "sharpe_ratio", "sortino_ratio", "drawdown_monetary",
        "equity_curve", "r_multiple_profitability"
    ):
        dirty_dict = {**clean_dict, bad_key: 123.45}
        with pytest.raises(TierBProfitabilityViolation):
            assert_zero_profitability(dirty_dict)


# -----------------------------------------------------------------------------
# 5. Mandatory Stage-2 Qualifications & Plan Constants
# -----------------------------------------------------------------------------

def test_mandatory_qualifications_present_in_trade_accounting() -> None:
    """Completed trade accounting dict always attaches mandatory development proxy qualifications."""
    result = reconcile_completed_trades(
        raw_candidates_count=35,
        qualifying_exits=[ExitReason.TAKE_PROFIT] * 35,
    )
    d = result.to_dict()
    assert "DEVELOPMENT_PROXY_NOT_HISTORICALLY_VALIDATED" in d["qualifications"]
    assert "HISTORICAL_SWAP_UNCERTAIN" in d["qualifications"]
