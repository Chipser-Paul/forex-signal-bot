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


# ===========================================================================
# 5. TC001 Observer Drift Regressions (Sections 16-23)
# ===========================================================================


class _MockSnapshot:
    def __init__(self, payload: dict[str, Any], available_at_ms: int | None = None):
        if available_at_ms is None:
            entry_rows = payload.get("entry_rows") or []
            if entry_rows and "available_at" in entry_rows[-1]:
                available_at_ms = int(
                    datetime.fromisoformat(entry_rows[-1]["available_at"]).timestamp() * 1000
                )
            else:
                available_at_ms = 1714557600000
        self.available_at_ms = available_at_ms
        self.gate_payload = json.dumps(payload)


def _make_mock_decision_record(
    decision_id: str = "d001",
    setup_id: str = "setup_001",
    event_at: datetime | None = None,
):
    from bot.strategy.setup_state import StrategyState, record_from_state
    at = event_at or datetime(2024, 5, 1, 9, 0, tzinfo=UTC)
    state = StrategyState(event_time=at)
    return record_from_state(
        state,
        event_at=at,
        last_event_id=decision_id,
        last_result=json.dumps({"setup_id": setup_id}),
    )


def _make_bullish_candles(fill_fvg: bool = False):
    from datetime import timedelta
    bar = timedelta(minutes=5)
    base = datetime(2024, 5, 1, 9, 0, tzinfo=UTC)
    rows = []
    # 50 warmup candles (2400.0 flat)
    for i in range(50):
        t = base + bar * i
        rows.append({
            "open_time": t.isoformat(),
            "available_at": (t + bar).isoformat(),
            "open": 2400.0, "high": 2402.0, "low": 2398.0, "close": 2400.0,
        })
    # Candle 50: candidate zone [2390.0, 2401.0]
    t50 = base + bar * 50
    rows.append({
        "open_time": t50.isoformat(),
        "available_at": (t50 + bar).isoformat(),
        "open": 2400.0, "high": 2401.0, "low": 2390.0, "close": 2391.0,
    })
    # Candle 51: confirmation
    t51 = base + bar * 51
    rows.append({
        "open_time": t51.isoformat(),
        "available_at": (t51 + bar).isoformat(),
        "open": 2391.0, "high": 2413.0, "low": 2389.0, "close": 2412.0,
    })
    # Candle 52: FVG completion candle (low = 2410.0 > 2401.0)
    t52 = base + bar * 52
    rows.append({
        "open_time": t52.isoformat(),
        "available_at": (t52 + bar).isoformat(),
        "open": 2412.0, "high": 2415.0, "low": 2410.0, "close": 2414.0,
    })
    if fill_fvg:
        t53 = base + bar * 53
        rows.append({
            "open_time": t53.isoformat(),
            "available_at": (t53 + bar).isoformat(),
            "open": 2414.0, "high": 2415.0, "low": 2405.0, "close": 2412.0,
        })
        start_post = 54
    else:
        start_post = 53
    # Add post candles to exceed minimum warmup (64 bars total)
    for i in range(start_post, start_post + 20):
        t = base + bar * i
        rows.append({
            "open_time": t.isoformat(),
            "available_at": (t + bar).isoformat(),
            "open": 2412.0, "high": 2415.0, "low": 2408.0, "close": 2412.0,
        })
    return rows


def test_regression_unresolved_bias_fails_closed():
    """Section 16: Gate-11 entrant with missing/unresolved htf_bias must raise V003EvalError."""
    from bot.strategy.config import StrategyConfig
    config = StrategyConfig()
    row = {"decision_id": "dec_bias_test"}
    candles = _make_bullish_candles()

    for unres_bias in ("", None, "FLAT", "neutral", "invalid"):
        payload = {
            "entry_rows": candles,
            "fvgs": [],
            "htf_bias": unres_bias,
            "atr": 1.0,
            "liquidity_context": {"structure_context": {"discount_zone": True}},
            "liquidity_signal": True,
        }
        snap = _MockSnapshot(payload)
        with pytest.raises(v003_eval.V003EvalError, match="lacks a resolved htf_bias"):
            v003_eval.observe_v003_decision(row, snap, None, config=config)

        # Prove the defective 82cf09b... logic would have mapped it to 'bullish'
        raw_bias = str(payload.get("htf_bias") or "").lower()
        defective_bias = raw_bias if raw_bias in ("bullish", "bearish") else "bullish"
        assert defective_bias == "bullish"


def test_regression_premium_discount_source():
    """Section 17: V003 must consume liquidity_context.structure_context, NOT ob_result."""
    from bot.strategy.config import StrategyConfig
    config = StrategyConfig()
    row = {"decision_id": "dec_pd_test"}
    rec = _make_mock_decision_record("dec_pd_test", "setup_pd_test")
    candles = _make_bullish_candles()

    # Case A: ob_result says True, but structure_context says False -> pd_flag must be False
    payload_a = {
        "entry_rows": candles,
        "fvgs": [],
        "htf_bias": "bullish",
        "atr": 1.0,
        "ob_result": {"in_discount_or_premium": True},
        "liquidity_context": {"structure_context": {"discount_zone": False}},
        "liquidity_signal": True,
    }
    obs_a = v003_eval.observe_v003_decision(
        row, _MockSnapshot(payload_a), None, config=config, decision_result_record=rec
    )
    checks_a = {c["label"]: c["passed"] for c in obs_a["v003_gate11_score"]["checks"]}
    assert checks_a["Price located in premium/discount zone"] is False

    # Case B: ob_result says False, but structure_context says True -> pd_flag must be True
    payload_b = {
        "entry_rows": candles,
        "fvgs": [],
        "htf_bias": "bullish",
        "atr": 1.0,
        "ob_result": {"in_discount_or_premium": False},
        "liquidity_context": {"structure_context": {"discount_zone": True}},
        "liquidity_signal": True,
    }
    obs_b = v003_eval.observe_v003_decision(
        row, _MockSnapshot(payload_b), None, config=config, decision_result_record=rec
    )
    checks_b = {c["label"]: c["passed"] for c in obs_b["v003_gate11_score"]["checks"]}
    assert checks_b["Price located in premium/discount zone"] is True

    # Case C (Bearish): structure_context has premium_zone True
    payload_c = {
        "entry_rows": candles,
        "fvgs": [],
        "htf_bias": "bearish",
        "atr": 1.0,
        "ob_result": {"in_discount_or_premium": False},
        "liquidity_context": {"structure_context": {"premium_zone": True}},
        "liquidity_signal": True,
    }
    obs_c = v003_eval.observe_v003_decision(
        row, _MockSnapshot(payload_c), None, config=config, decision_result_record=rec
    )
    checks_c = {c["label"]: c["passed"] for c in obs_c["v003_gate11_score"]["checks"]}
    assert checks_c["Price located in premium/discount zone"] is True


def test_regression_no_true_default_for_premium_discount():
    """Section 18: Missing structure_context flag must be False, not defaulted to True."""
    from bot.strategy.config import StrategyConfig
    config = StrategyConfig()
    row = {"decision_id": "dec_pd_default_test"}
    rec = _make_mock_decision_record("dec_pd_default_test", "setup_pd_default_test")
    candles = _make_bullish_candles()

    payload = {
        "entry_rows": candles,
        "fvgs": [],
        "htf_bias": "bullish",
        "atr": 1.0,
        "ob_result": {},
        "liquidity_context": {},
        "liquidity_signal": True,
    }
    obs = v003_eval.observe_v003_decision(
        row, _MockSnapshot(payload), None, config=config, decision_result_record=rec
    )
    checks = {c["label"]: c["passed"] for c in obs["v003_gate11_score"]["checks"]}
    assert checks["Price located in premium/discount zone"] is False


def test_regression_sweep_source_no_or_fallback():
    """Section 19: Sweep must come from liquidity_signal only, with no OR fallback."""
    from bot.strategy.config import StrategyConfig
    config = StrategyConfig()
    row = {"decision_id": "dec_sweep_test"}
    rec = _make_mock_decision_record("dec_sweep_test", "setup_sweep_test")
    candles = _make_bullish_candles()

    # Case A: liquidity_signal is False, liquidity_swept is True -> sweep_flag must be False
    payload_a = {
        "entry_rows": candles,
        "fvgs": [],
        "htf_bias": "bullish",
        "atr": 1.0,
        "liquidity_context": {"structure_context": {"discount_zone": True}, "liquidity_swept": True},
        "liquidity_signal": False,
    }
    obs_a = v003_eval.observe_v003_decision(
        row, _MockSnapshot(payload_a), None, config=config, decision_result_record=rec
    )
    checks_a = {c["label"]: c["passed"] for c in obs_a["v003_gate11_score"]["checks"]}
    assert checks_a["Liquidity sweep occurred before entry"] is False

    # Case B: liquidity_signal is True, liquidity_swept is False -> sweep_flag must be True
    payload_b = {
        "entry_rows": candles,
        "fvgs": [],
        "htf_bias": "bullish",
        "atr": 1.0,
        "liquidity_context": {"structure_context": {"discount_zone": True}, "liquidity_swept": False},
        "liquidity_signal": True,
    }
    obs_b = v003_eval.observe_v003_decision(
        row, _MockSnapshot(payload_b), None, config=config, decision_result_record=rec
    )
    checks_b = {c["label"]: c["passed"] for c in obs_b["v003_gate11_score"]["checks"]}
    assert checks_b["Liquidity sweep occurred before entry"] is True


def test_regression_adapter_and_symbol_passed_to_strategy(monkeypatch):
    """Section 20: evaluate_v003_strategy must be called with adapter='live' and symbol='XAUUSDm'."""
    from bot.strategy.config import StrategyConfig
    from bot.strategy.variant_v003 import evaluate_v003_strategy as real_eval_strategy
    config = StrategyConfig()
    row = {"decision_id": "dec_adapter_test"}
    rec = _make_mock_decision_record("dec_adapter_test", "setup_adapter_test")
    candles = _make_bullish_candles()

    payload = {
        "symbol": "EURUSD",  # Payload specifies alternate symbol
        "entry_rows": candles,
        "fvgs": [],
        "htf_bias": "bullish",
        "atr": 1.0,
        "liquidity_context": {"structure_context": {"discount_zone": True}},
        "liquidity_signal": True,
    }

    called_kwargs = {}

    def mock_eval_strategy(**kwargs):
        nonlocal called_kwargs
        called_kwargs = dict(kwargs)
        return real_eval_strategy(**kwargs)

    monkeypatch.setattr("backtests.phase8_v2_variant_v003_eval.evaluate_v003_strategy", mock_eval_strategy)

    v003_eval.observe_v003_decision(
        row, _MockSnapshot(payload), None, config=config, decision_result_record=rec
    )

    assert called_kwargs.get("adapter") == "live", f"Expected adapter='live', got {called_kwargs.get('adapter')}"
    assert called_kwargs.get("symbol") == "XAUUSDm", f"Expected symbol='XAUUSDm', got {called_kwargs.get('symbol')}"


def test_v002_v003_non_fvg_input_equivalence():
    """Section 21: Exact equivalence between V002 and V003 observers when F_final is True."""
    from backtests.phase8_v2_variant_v002_eval import observe_v002_decision
    from bot.strategy.config import StrategyConfig
    config = StrategyConfig()
    row = {
        "decision_id": "dec_equiv_001",
        "score": {"passes_threshold": True},
        "gate_results": {"gate_11_confluence_score": True},
        "overlap": {"canonical_fvg_in_ob": True},
    }
    candles = _make_bullish_candles(fill_fvg=False)
    dec_at = datetime.fromisoformat(candles[-1]["available_at"])
    rec = _make_mock_decision_record("dec_equiv_001", "setup_equiv_001", event_at=dec_at)
    final_fvg = {"bottom": 2401.0, "top": 2410.0, "direction": "bullish"}
    payload = {
        "symbol": "XAUUSDm",
        "entry_rows": candles,
        "fvgs": [final_fvg],
        "htf_bias": "bullish",
        "atr": 1.0,
        "dxy_context": {"dxy_bias": "bearish", "available": True},
        "news_context": {"news_clear": True, "state": "CLEAR", "source": "test"},
        "session_context": {
            "session_allowed": True,
            "state": "CLEAR",
            "active_session": "london",
            "is_priority_session": True,
        },
        "liquidity_context": {
            "structure_context": {"discount_zone": True},
            "liquidity_swept": True,
            "liquidity_pools": [],
        },
        "internal_structure": {"event": "CHOCH"},
        "liquidity_signal": True,
    }
    snap = _MockSnapshot(payload)

    obs_v002 = observe_v002_decision(row, snap, None, config=config, decision_result_record=rec)
    obs_v003 = v003_eval.observe_v003_decision(row, snap, None, config=config, decision_result_record=rec)

    # 1. side
    assert obs_v002["v002_side"] == obs_v003["v003_side"] == "LONG"
    # 2. structurally_active
    assert obs_v002["v002_structurally_active"] == obs_v003["v003_structurally_active"] is True
    # 3. age_bars
    assert obs_v002["v002_age_bars"] == obs_v003["v003_age_bars"]
    # 4. block_id
    assert obs_v002["v002_block_id"] == obs_v003["v003_block_id"]
    # 5. Gate-11 score points and threshold pass
    assert obs_v002["v002_gate11_score"]["score"] == obs_v003["v003_gate11_score"]["score"] == 8
    assert obs_v002["v002_gate11_passed"] == obs_v003["v003_gate11_passed"] is True
    # 6. strategy eligibility and reasons
    assert obs_v002["v002_strategy_eligible"] == obs_v003["v003_strategy_eligible"] is True
    assert obs_v002["v002_strategy_reasons"] == obs_v003["v003_strategy_reasons"]
    assert obs_v002["v002_strategy_order_block_state"] == obs_v003["v003_strategy_order_block_state"]
    # 7. entry readiness, setup_id, entry
    assert obs_v002["v002_entry_ready"] == obs_v003["v003_entry_ready"]
    assert obs_v002["v002_setup_id"] == obs_v003["v003_setup_id"] == "setup_equiv_001"
    assert obs_v002["v002_entry"] == obs_v003["v003_entry"]


def test_temporal_only_difference_from_v002():
    """Section 22: When F_final is False and F_temporal is True, only the FVG component differs."""
    from backtests.phase8_v2_variant_v002_eval import observe_v002_decision
    from bot.strategy.config import StrategyConfig
    config = StrategyConfig()
    row = {
        "decision_id": "dec_temp_diff_001",
        "score": {"passes_threshold": False},
        "gate_results": {"gate_11_confluence_score": True},
        "overlap": {"canonical_fvg_in_ob": False},
    }
    candles = _make_bullish_candles(fill_fvg=True)
    dec_at = datetime.fromisoformat(candles[-1]["available_at"])
    rec = _make_mock_decision_record("dec_temp_diff_001", "setup_temp_001", event_at=dec_at)
    payload = {
        "symbol": "XAUUSDm",
        "entry_rows": candles,
        "fvgs": [],  # F_final is FALSE
        "htf_bias": "bullish",
        "atr": 1.0,
        "dxy_context": {"dxy_bias": "bearish", "available": True},
        "news_context": {"news_clear": True, "state": "CLEAR", "source": "test"},
        "session_context": {
            "session_allowed": True,
            "state": "CLEAR",
            "active_session": "london",
            "is_priority_session": True,
        },
        "liquidity_context": {
            "structure_context": {"discount_zone": True},
            "liquidity_swept": True,
            "liquidity_pools": [],
        },
        "internal_structure": {"event": "CHOCH"},
        "liquidity_signal": True,
    }
    snap = _MockSnapshot(payload)

    obs_v002 = observe_v002_decision(row, snap, None, config=config, decision_result_record=rec)
    obs_v003 = v003_eval.observe_v003_decision(row, snap, None, config=config, decision_result_record=rec)

    # In V002: FVG component is False -> score 7/8 -> fails threshold
    assert obs_v002["v002_fvg_associated"] is False
    assert obs_v002["v002_gate11_score"]["score"] == 7
    assert obs_v002["v002_gate11_passed"] is False
    assert obs_v002["v002_strategy_eligible"] is False
    assert obs_v002["v002_entry_ready"] is False

    # In V003: Temporal memory FVG evidence qualifies -> score 8/8 -> passes threshold
    assert obs_v003["v003_temporal_fvg_evidence"] is True
    assert obs_v003["v003_final_fvg_associated"] is False
    assert obs_v003["v003_fvg_evidence"] is True
    assert obs_v003["v003_gate11_score"]["score"] == 8
    assert obs_v003["v003_gate11_passed"] is True
    assert obs_v003["v003_strategy_eligible"] is True

    # Non-FVG inputs are strictly identical
    assert obs_v002["v002_side"] == obs_v003["v003_side"] == "LONG"
    assert obs_v002["v002_structurally_active"] == obs_v003["v003_structurally_active"] is True
    assert obs_v002["v002_block_id"] == obs_v003["v003_block_id"]
    assert obs_v002["v002_setup_id"] == obs_v003["v003_setup_id"] == "setup_temp_001"


def test_regression_score_contamination_prevented():
    """Section 23: Legacy/alternate truthy surfaces must NOT manufacture Gate-11 score points."""
    from datetime import timedelta
    from bot.strategy.config import StrategyConfig
    config = StrategyConfig()
    row = {"decision_id": "dec_contam_test"}
    rec = _make_mock_decision_record("dec_contam_test", "setup_contam_test")
    bar = timedelta(minutes=5)
    base = datetime(2024, 5, 1, 9, 0, tzinfo=UTC)
    rows = []
    for i in range(65):
        t = base + bar * i
        rows.append({
            "open_time": t.isoformat(),
            "available_at": (t + bar).isoformat(),
            "open": 2400.0, "high": 2401.0, "low": 2399.0, "close": 2400.0,
        })
    payload = {
        "symbol": "XAUUSDm",
        "entry_rows": rows,
        "fvgs": [],
        "htf_bias": "bullish",
        "atr": 1.0,
        "ob_result": {"in_discount_or_premium": True},  # alternate truthy
        "liquidity_context": {
            "structure_context": {"discount_zone": False},  # V002 flag FALSE
            "liquidity_swept": True,  # alternate truthy
        },
        "liquidity_signal": False,  # V002 flag FALSE
    }
    snap = _MockSnapshot(payload)
    obs = v003_eval.observe_v003_decision(
        row, snap, None, config=config, decision_result_record=rec
    )

    checks = {c["label"]: (c["passed"], c["points"]) for c in obs["v003_gate11_score"]["checks"]}
    assert checks["Price located in premium/discount zone"] == (False, 0)
    assert checks["Liquidity sweep occurred before entry"] == (False, 0)
    assert obs["v003_gate11_score"]["score"] == 0  # HTF bias aligns only when active block side matches
    assert obs["v003_gate11_passed"] is False
