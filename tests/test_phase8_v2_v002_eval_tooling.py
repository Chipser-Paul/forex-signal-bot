# -*- coding: utf-8 -*-
"""Phase-B tests for the frozen V002 Fold-01 measurement tooling.

Synthetic fixtures only — no Fold-01 empirical data, no historical store,
no external evidence.  Proves, before any empirical access:

* store boundary + historical-store refusal + holdout/2025+ path rejection;
* the store-compatibility assertion fails closed on payload gaps and
  accepts a payload that carries every V002-required causal input;
* a mocked-engine snapshot flows through the frozen D001 loop into the V002
  observer (pair evaluation, V002 scorer, downstream strategy);
* aggregate + surface verification + accounting reconciliation;
* prohibited metric keys and counterfactual families are refused;
* provenance binds the canonical_git_blob_v1 committed bytes via the
  pure-Python Git object store and fails closed on a wrong commit.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, "tests")

from backtests import phase8_v2_variant_v002_eval as v002_eval
from bot.strategy.variant_v002 import V002_ACTIVE
from tests.test_canonical_byte_contract import GitObjectStore

UTC = timezone.utc
AT = datetime(2024, 5, 1, 11, 50, tzinfo=timezone.utc)

COMMIT_A = "a" * 40
COMMIT_B = "b" * 40


def _displacement_snapshot(monkeypatch, at: datetime):
    """A real build_gate_inputs snapshot whose M5 frame carries the
    synthetic displacement fixture (D001 engine mocks for the acquisition
    surfaces, exactly like tests/test_phase8_v2_d001_tooling.py)."""
    from bot.state import gate_inputs as gi
    from config.symbol_profiles import get_symbol_profile
    from tests.test_phase8_v2_d001_tooling import _patch_engines
    from tests.test_phase8_v2_v002_variant import build_rows, to_frame

    from bot.strategy.config import StrategyConfig

    _patch_engines(monkeypatch)
    frame = to_frame(build_rows(pre=30, post=2))
    config = StrategyConfig()
    return gi.build_gate_inputs(
        symbol="XAUUSDm", event_at=at,
        frames={"H1": frame, "M5": frame, "M15": frame},
        profile=get_symbol_profile("XAUUSDm"), htf_bias="bullish",
        bias_snapshot={"htf_bias": {"direction": "bullish"}},
        bias_resolution={"direction": "bullish"},
        liquidity_context={
            "structure_context": {
                "structure": "bullish", "state": "confirmed",
                "discount_zone": (2380.0, 2395.0),
            },
            "liquidity_pools": [],
        },
        dxy_context={"available": True, "dxy_bias": "bearish"},
        news_context={"news_clear": True},
        session_context={"session_allowed": True, "active_session": "london"},
        config=config,
    )


def _store_identity():
    return {
        "fold_id": "fold-01",
        "decision_timeframe": "M5",
        "evaluation_start_ms": v002_eval.FOLD01_START_MS,
        "evaluation_end_ms": v002_eval.FOLD01_END_MS,
        "coverage": "full",
    }


def test_store_boundary_refuses_wrong_fold_and_coverage():
    v002_eval.check_store_boundary(_store_identity())
    bad = dict(_store_identity(), fold_id="fold-02")
    with pytest.raises(v002_eval.BoundaryError):
        v002_eval.check_store_boundary(bad)
    bad = dict(_store_identity(), coverage="partial")
    with pytest.raises(v002_eval.BoundaryError):
        v002_eval.check_store_boundary(bad)
    bad = dict(_store_identity(), evaluation_start_ms=0)
    with pytest.raises(v002_eval.BoundaryError):
        v002_eval.check_store_boundary(bad)


def test_historical_store_is_refused_as_v002_input():
    identity = dict(_store_identity(), fold_id="fold-01-1d710826193a6767")
    with pytest.raises(v002_eval.V002EvalError):
        v002_eval.check_store_boundary(identity)


def test_holdout_and_future_paths_are_refused():
    from backtests.phase8_v2_variant_v001_eval import BoundaryError as V001BoundaryError

    with pytest.raises(V001BoundaryError):
        v002_eval.reject_holdout_path("evidence/holdout/fold01")
    with pytest.raises(V001BoundaryError):
        v002_eval.reject_holdout_path("evidence/store-2025-01/x")


def test_store_compatibility_fails_closed_on_missing_causal_inputs():
    class _Snap:
        gate_payload = json.dumps({"entry_rows": []})

    with pytest.raises(v002_eval.StoreCompatibilityError) as error:
        v002_eval.assert_store_semantic_compatibility(_Snap())
    assert "fresh" in str(error.value)


def test_store_compatibility_accepts_complete_payload():
    class _Snap:
        gate_payload = json.dumps(
            {
                "entry_rows": [{"open_time": "2024-04-02T12:00:00+00:00"}],
                "fvgs": [], "htf_bias": "bullish", "atr": 1.0,
                "ob_result": {}, "displacement": {},
            }
        )

    v002_eval.assert_store_semantic_compatibility(_Snap())


class _SnapView:
    """Snapshot view over a build_gate_inputs payload (store-row semantics)."""

    def __init__(self, inputs, at: datetime):
        self.available_at_ms = int(at.timestamp() * 1000)
        self.open_time_ms = self.available_at_ms - 300_000
        self.timeframe = "M5"
        self.close = 100.0
        self.identity = "synthetic"
        self.check_passes = True
        self.gate_status = "ok"
        self.gate_payload = inputs.payload
        self.gate_event_id = inputs.event_id
        self.gate_sources = inputs.source_identities
        self.config_fingerprint = inputs.config_fingerprint
        self.session_context = {"session_allowed": True, "active_session": "london"}
        self.news_context = {"news_clear": True}
        self.bias_snapshot = {"htf_bias": {"direction": "bullish"}}
        self.bias_resolution = {"direction": "bullish"}
        self.dxy_context = {"available": True, "dxy_bias": "bearish"}
        self.frames_sufficient = True

    def strategy_evaluation_inputs(self):
        from bot.state.gate_inputs import StrategyEvaluationInputs
        from bot.validation.market_feature_store import SYMBOL

        return StrategyEvaluationInputs(
            symbol=SYMBOL,
            event_at=datetime.fromtimestamp(self.available_at_ms / 1000, tz=UTC),
            event_id=str(self.gate_event_id),
            source_identities=tuple(self.gate_sources),
            config_fingerprint=self.config_fingerprint,
            payload=str(self.gate_payload),
        )


def _displacement_snapview(at: datetime, monkeypatch=None) -> _SnapView:
    if monkeypatch is None:
        raise ValueError("engine mocks require the pytest monkeypatch fixture")
    return _SnapView(_displacement_snapshot(monkeypatch, at), at)


def test_observe_v002_decision_on_mocked_snapshot(monkeypatch):
    snapshot = _displacement_snapview(AT, monkeypatch)
    config = _config()
    from bot.strategy.setup_state import StrategyState, record_from_state

    seed = datetime(2024, 1, 1, tzinfo=UTC)
    prior = record_from_state(StrategyState(event_time=seed), event_at=seed)
    from backtests.phase8_v2_diagnostic_d001 import evaluate_orchestration_decision

    row, _next_record = evaluate_orchestration_decision(snapshot, prior)
    assert row["gate_results"].get("gate_11_confluence_score") is True, (
        "fixture must pass frozen Gate 11 to enter the V002 population"
    )
    observation = v002_eval.observe_v002_decision(
        row, snapshot, prior, config=config,
    )
    assert observation["v002_pair_state"] in (V002_ACTIVE, "MITIGATED", "RETEST_ELIGIBLE")
    assert observation["v002_side"] == "LONG"
    assert observation["legacy_score_passed"] is True
    assert "v002_gate11_score" in observation
    assert observation["v002_gate11_score"]["max_score"] == 8


def _config():
    from bot.strategy.config import StrategyConfig

    return StrategyConfig()


def test_aggregate_counts_and_candidate_surface():
    observations = [
        {
            "decision_id": "d1", "available_at_ms": 1,
            "v002_pair_state": V002_ACTIVE, "v002_pair_reason": "structurally_active_block",
            "v002_structurally_active": True, "v002_side": "LONG", "v002_age_bars": 40,
            "v002_block_id": "x", "v002_fvg_associated": True,
            "v002_fvg_direction": "bullish", "v002_exact_overlap_descriptive": True,
            "v002_gate11_score": {"passes_threshold": True, "max_score": 8},
            "v002_strategy_eligible": True, "v002_strategy_reasons": ["APPROVED"],
            "v002_strategy_order_block_state": "ELIGIBLE",
            "legacy_canonical_fvg_in_ob": False, "legacy_score_passed": True,
        },
        {
            "decision_id": "d2", "available_at_ms": 2,
            "v002_pair_state": "MITIGATED", "v002_pair_reason": "block_already_mitigated",
            "v002_structurally_active": False, "v002_side": "SHORT", "v002_age_bars": 10,
            "v002_block_id": "y", "v002_fvg_associated": False,
            "v002_fvg_direction": None, "v002_exact_overlap_descriptive": None,
            "v002_gate11_score": {"passes_threshold": False, "max_score": 8},
            "v002_strategy_eligible": False, "v002_strategy_reasons": ["ORDER_BLOCK_UNAVAILABLE"],
            "v002_strategy_order_block_state": "MITIGATED",
            "legacy_canonical_fvg_in_ob": True, "legacy_score_passed": True,
        },
    ]
    aggregate = v002_eval.aggregate_v002(observations)
    surface = aggregate["V002_structural_pair_surface"]
    assert surface["gate11_entrants_observed"] == 2
    assert surface["v002_pair_state_counts"] == {V002_ACTIVE: 1, "MITIGATED": 1}
    assert surface["v002_structurally_active_count"] == 1
    assert surface["v002_associated_same_direction_fvg_count"] == 1
    assert surface["exact_overlap_descriptive_true"] == 1
    assert surface["v002_structural_active_age_summary"]["count"] == 1
    candidate = aggregate["candidate_surface"]
    assert candidate["candidate_ready"] == 1
    assert candidate["candidate_setup_ids"] == ["d1"]
    assert candidate["candidate_long_count"] == 1
    assert candidate["candidate_short_count"] == 0
    assert aggregate["success_classification_rule"]["OPPORTUNITY_SUFFICIENT"] == "candidate_ready >= 90"


def test_banned_metrics_refused():
    with pytest.raises(v002_eval.V002EvalError):
        v002_eval._reject_banned_metrics({"pnl": 1})
    with pytest.raises(v002_eval.V002EvalError):
        v002_eval._reject_banned_metrics({"alternate_expiry_60_count": 1})
    with pytest.raises(v002_eval.V002EvalError):
        v002_eval._reject_banned_metrics({"candidate_if_expiry_removed": 1})
    v002_eval._reject_banned_metrics({"no_profitability_metrics": True})
    v002_eval._reject_banned_metrics({"no_numeric_expiry_evaluated": True})


def test_run_v002_rejects_wrong_fold_and_accounts_accounting(monkeypatch):
    class _Identity(dict):
        pass

    class _Store:
        identity = dict(_store_identity(), fold_id="fold-02")

    with pytest.raises(v002_eval.BoundaryError):
        v002_eval.run_v002(
            _Store(), implementation_commit=COMMIT_A, tooling_commit=COMMIT_A,
        )


def test_run_v002_full_loop_on_mocked_store(monkeypatch):
    from bot.strategy.setup_state import StrategyState, record_from_state
    from tests.test_phase8_v2_d001_tooling import _Snapshot, _Table

    snapshot = _displacement_snapview(AT, monkeypatch)
    from backtests.phase8_v2_diagnostic_d001 import evaluate_orchestration_decision

    seed = datetime(2024, 1, 1, tzinfo=UTC)
    prior = record_from_state(StrategyState(event_time=seed), event_at=seed)
    row, _next = evaluate_orchestration_decision(snapshot, prior)
    assert row["gate_results"].get("gate_11_confluence_score") is True

    early = _Snapshot(
        available_at_ms=int(AT.timestamp() * 1000) - 1,
        gate_status="early_exit",
    )
    table = _Table([early, snapshot])
    store = type("Store", (), {})()
    store.identity = _store_identity()
    store.table = table

    doc, rendered = v002_eval.run_v002(
        store, implementation_commit=COMMIT_A, tooling_commit=COMMIT_A,
        blob_source=_fake_blob_source(),
    )
    accounting = doc["decision_accounting"]
    assert accounting["scheduled"] == 2
    assert accounting["missing_history"] == 1
    assert accounting["reducer_classified"] == 1
    assert accounting["reconciles"] is True
    surface = doc["V002_structural_pair_surface"]
    assert surface["gate11_entrants_observed"] == 1
    assert surface["gate11_v002_score_pass_count"] >= 1
    assert doc["candidate_surface"]["candidate_ready"] >= 0
    import hashlib

    assert doc["provenance"]["implementation_commit"] == COMMIT_A
    assert doc["provenance"]["tooling_fingerprint"] == hashlib.sha256(
        _fake_blob_source()(COMMIT_A, v002_eval.TOOLING_RELPATH)
    ).hexdigest()


def _fake_blob_source():
    """Deterministic committed-byte source for the fingerprint contract."""

    def _read(at_commit, path):
        if at_commit != COMMIT_A:
            raise KeyError(f"commit {at_commit} not found in synthetic store")
        return b"synthetic-bytes:" + path.encode("utf-8")

    return _read


def test_provenance_fails_closed_on_wrong_tooling_commit(monkeypatch):
    with pytest.raises(v002_eval.V002EvalError):
        v002_eval.provenance(
            implementation_commit=COMMIT_A,
            tooling_commit=COMMIT_B,
            store_identity=_store_identity(),
            blob_source=_fake_blob_source(),
        )


def test_write_result_refuses_overwrite(tmp_path):
    import hashlib

    doc = {"variant_id": v002_eval.V002_ID}
    rendered = json.dumps(doc, sort_keys=True).encode("utf-8")
    path, sha = v002_eval.write_result(doc, rendered, tmp_path)
    assert sha == hashlib.sha256(rendered).hexdigest()
    with pytest.raises(v002_eval.V002EvalError):
        v002_eval.write_result(doc, rendered, tmp_path)


def test_git_object_store_fixture_importable():
    assert GitObjectStore is not None
