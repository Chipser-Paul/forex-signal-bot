# -*- coding: utf-8 -*-
"""Phase-B synthetic tests for the frozen V003 Fold-01 measurement tooling.

Synthetic fixtures only — no Fold-01 empirical data, no historical store,
no external evidence.  Proves, before any empirical access:

* store boundary + authorized-store validation + holdout/2025+ path rejection;
* store-compatibility assertion fails closed on payload gaps and accepts
  complete causal inputs;
* banned metric keys (P&L, win rate, drawdown, Sharpe, optimal lag) fail closed;
* aggregate + surface verification + funnel consistency + setup ID reconciliation;
* atomic result writing refuses overwrite;
* bound specification SHA-256 matches Phase-A preregistration.
"""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backtests import phase8_v2_variant_v003_eval as v003_eval
from bot.strategy.variant_v003 import SPEC_SHA256 as V003_SPEC_SHA256

UTC = timezone.utc


def _store_identity():
    return {
        "fold_id": "fold-01",
        "decision_timeframe": "M5",
        "evaluation_start_ms": v003_eval.FOLD01_START_MS,
        "evaluation_end_ms": v003_eval.FOLD01_END_MS,
        "coverage": "full",
    }


# ===========================================================================
# 1. Store Boundary and Path Validation Tests
# ===========================================================================


def test_store_boundary_refuses_wrong_fold_and_coverage():
    v003_eval.check_store_boundary(_store_identity())
    bad = dict(_store_identity(), fold_id="fold-02")
    with pytest.raises(Exception):
        v003_eval.check_store_boundary(bad)
    bad = dict(_store_identity(), coverage="partial")
    with pytest.raises(Exception):
        v003_eval.check_store_boundary(bad)
    bad = dict(_store_identity(), evaluation_start_ms=0)
    with pytest.raises(Exception):
        v003_eval.check_store_boundary(bad)


def test_historical_store_is_refused_as_v003_input():
    identity = dict(_store_identity(), fold_id="fold-01-1d710826193a6767")
    with pytest.raises(Exception):
        v003_eval.check_store_boundary(identity)


def test_validate_authorized_store_path_accepts_canonical_fold01():
    # Canonical authorized Fold-01 store basename
    v003_eval.validate_authorized_store_path("C:/data/stores/fold-01-a8b406884ab3525a")
    v003_eval.validate_authorized_store_path(Path("C:/data/stores/fold-01-a8b406884ab3525a"))


def test_validate_authorized_store_path_refuses_holdout():
    with pytest.raises(v003_eval.BoundaryError, match="holdout"):
        v003_eval.validate_authorized_store_path("C:/data/holdout/store")
    with pytest.raises(v003_eval.BoundaryError, match="holdout"):
        v003_eval.validate_authorized_store_path("C:/data/final_validation/store")


def test_validate_authorized_store_path_refuses_post_2024():
    with pytest.raises(v003_eval.BoundaryError, match="post-2024"):
        v003_eval.validate_authorized_store_path("C:/data/2025/store")
    with pytest.raises(v003_eval.BoundaryError, match="post-2024"):
        v003_eval.validate_authorized_store_path("C:/data/2025-01-01/store")
    with pytest.raises(v003_eval.BoundaryError, match="post-2024"):
        v003_eval.validate_authorized_store_path("C:/data/year=2026/store")


def test_validate_authorized_store_path_refuses_other_folds():
    with pytest.raises(v003_eval.BoundaryError, match="unauthorized fold store refused"):
        v003_eval.validate_authorized_store_path("C:/data/stores/fold-02-abc")
    with pytest.raises(v003_eval.BoundaryError, match="unauthorized fold store refused"):
        v003_eval.validate_authorized_store_path("C:/data/stores/fold-01-1d710826193a6767")


# ===========================================================================
# 2. Store Semantic Compatibility Tests
# ===========================================================================


def test_store_compatibility_fails_closed_on_missing_payload():
    class _EmptySnap:
        gate_payload = None

    with pytest.raises(v003_eval.StoreCompatibilityError, match="persisted gate payload"):
        v003_eval.assert_store_semantic_compatibility(_EmptySnap())


def test_store_compatibility_fails_closed_on_missing_causal_fields():
    class _Snap:
        gate_payload = json.dumps({"entry_rows": []})

    with pytest.raises(v003_eval.StoreCompatibilityError, match="lacks V003-required causal inputs"):
        v003_eval.assert_store_semantic_compatibility(_Snap())


def test_store_compatibility_accepts_complete_payload():
    class _Snap:
        gate_payload = json.dumps(
            {
                "entry_rows": [{"open_time": "2024-04-02T12:00:00+00:00"}],
                "fvgs": [],
                "htf_bias": "bullish",
                "atr": 1.0,
                "ob_result": {},
                "displacement": {},
                "session_context": {},
                "liquidity_context": {},
                "internal_structure": {},
                "liquidity_signal": {},
            }
        )

    v003_eval.assert_store_semantic_compatibility(_Snap())


# ===========================================================================
# 3. Banned Metric Rejection Tests
# ===========================================================================


def test_banned_metrics_rejected():
    banned_keys = ["pnl", "win_rate", "profit_factor", "drawdown", "sharpe", "expectancy", "optimal_lag"]
    for key in banned_keys:
        doc = {"decision_accounting": {}, key: 123.45}
        with pytest.raises(Exception):
            v003_eval._reject_banned_metrics(doc)


# ===========================================================================
# 4. Aggregation, Funnel, and Surface Invariant Tests
# ===========================================================================


def _mock_observation(decision_id: str, setup_id: str, state="ACTIVE", source="TEMPORAL_MEMORY", g11=True, strat=True, ready=True):
    return {
        "decision_id": decision_id,
        "available_at_ms": 1714557600000,
        "v003_pair_state": state,
        "v003_pair_reason": "structurally_active_block",
        "v003_side": "LONG",
        "v003_block_id": "blk_1",
        "v003_age_bars": 5,
        "v003_structurally_active": True,
        "v003_final_fvg_associated": source == "FINAL_SURFACE",
        "v003_temporal_fvg_evidence": source == "TEMPORAL_MEMORY",
        "v003_fvg_evidence": source in ("FINAL_SURFACE", "TEMPORAL_MEMORY"),
        "v003_fvg_evidence_source": source,
        "v003_exact_overlap_descriptive": None,
        "v003_temporal_fvg_offset_bars": 1 if source == "TEMPORAL_MEMORY" else None,
        "v003_temporal_fvg_count": 1 if source == "TEMPORAL_MEMORY" else 0,
        "v003_gate11_score": 8 if g11 else 7,
        "v003_gate11_passed": g11,
        "v003_strategy_eligible": strat,
        "v003_entry_ready": ready,
        "v003_setup_id": setup_id,
        "v003_entry": {"price": 2400.0} if ready else None,
        "legacy_score_passed": True,
    }


def test_aggregation_and_funnel_reconciliation():
    obs = [
        _mock_observation("d1", "s1", source="FINAL_SURFACE", g11=True, strat=True, ready=True),
        _mock_observation("d2", "s2", source="TEMPORAL_MEMORY", g11=True, strat=True, ready=True),
        _mock_observation("d3", "s2", source="TEMPORAL_MEMORY", g11=True, strat=True, ready=True),  # duplicate setup_id s2
        _mock_observation("d4", "s3", source="TEMPORAL_MEMORY", g11=True, strat=True, ready=False),  # fails entry
        _mock_observation("d5", "s4", source="TEMPORAL_MEMORY", g11=True, strat=False, ready=False),  # fails strat
        _mock_observation("d6", "s5", source="NONE", g11=False, strat=False, ready=False),  # fails g11
    ]

    agg = v003_eval.aggregate_v003(obs)

    # 1. Funnel chain counts
    funnel = agg["V003_variant_funnel"]
    assert funnel["gate_11_v003"]["entered"] == 6
    assert funnel["gate_11_v003"]["passed"] == 5
    assert funnel["canonical_strategy_v003"]["entered"] == 5
    assert funnel["canonical_strategy_v003"]["passed"] == 4
    assert funnel["gate_12_13_rr_entry_v003"]["entered"] == 4
    assert funnel["gate_12_13_rr_entry_v003"]["passed"] == 3

    # 2. Candidate counts & reconciliation
    candidate = agg["candidate_surface"]
    assert candidate["candidate_ready"] == 3
    assert candidate["unique_candidate_setup_ids"] == 2  # s1 and s2
    assert candidate["duplicate_candidate_setup_id_occurrences"] == 1  # s2 duplicated once
    assert candidate["setup_id_reconciliation"]["unique_plus_duplicates_equals_candidate_ready"] is True
    assert candidate["candidate_final_surface_count"] == 1
    assert candidate["candidate_temporal_memory_count"] == 2

    # 3. Success classification
    assert agg["success_classification"]["classification"] == "OPPORTUNITY_INSUFFICIENT"
    assert agg["success_classification"]["opportunity_target"] == 90
    assert agg["success_classification"]["headroom_upper_bound"] == 97


def test_surface_verification_asserts_all_required_surfaces():
    obs = [
        _mock_observation("d1", "s1", source="FINAL_SURFACE", g11=True, strat=True, ready=True),
    ]
    agg = v003_eval.aggregate_v003(obs)
    doc = {
        "decision_accounting": {
            "scheduled": 1,
            "reducer_classified": 1,
            "missing_history": 0,
            "unavailable_input": 0,
            "evaluation_error": 0,
        },
        "gate_funnel": {
            "gate_11_confluence_score": {"entered": 1, "passed": 1, "failed": 0},
        },
        "V003_structural_pair_surface": agg["V003_structural_pair_surface"],
        "V003_variant_funnel": agg["V003_variant_funnel"],
        "candidate_surface": agg["candidate_surface"],
        "success_classification": agg["success_classification"],
    }
    # Should pass without error
    v003_eval.assert_expected_surfaces(doc)

    # Missing surface fails closed
    bad_doc = copy.deepcopy(doc)
    del bad_doc["candidate_surface"]
    with pytest.raises(v003_eval.V003EvalError, match="surface missing"):
        v003_eval.assert_expected_surfaces(bad_doc)


def test_atomic_write_refuses_overwrite():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        content = b'{"test": 123}'
        target, digest = v003_eval.write_result({"test": 123}, content, out_dir)
        assert target.exists()
        assert digest == hashlib.sha256(content).hexdigest()

        # Refuse overwrite
        with pytest.raises(v003_eval.V003EvalError, match="already exists"):
            v003_eval.write_result({"test": 123}, content, out_dir)


def test_bound_specification_sha256():
    # Phase-A preregistration spec SHA-256 bound into tooling
    assert v003_eval.SPEC_SHA256 == "e6aa3e8a4f7b909f178a18112a43425ccfe61448c3c8643aea9c3f5d670e0d95"
    assert V003_SPEC_SHA256 == "e6aa3e8a4f7b909f178a18112a43425ccfe61448c3c8643aea9c3f5d670e0d95"
