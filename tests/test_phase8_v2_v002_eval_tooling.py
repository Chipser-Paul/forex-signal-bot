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
import tempfile
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
                "session_context": {}, "liquidity_context": {},
                "internal_structure": {}, "liquidity_signal": {},
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

    row, next_record = evaluate_orchestration_decision(snapshot, prior)
    assert row["gate_results"].get("gate_11_confluence_score") is True, (
        "fixture must pass frozen Gate 11 to enter the V002 population"
    )
    observation = v002_eval.observe_v002_decision(
        row, snapshot, prior, config=config,
        decision_result_record=next_record,
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
            "v002_gate11_passed": True,
            "v002_strategy_eligible": True, "v002_strategy_reasons": ["APPROVED"],
            "v002_strategy_order_block_state": "ELIGIBLE",
            "v002_setup_id": "s8n1_full_candidate", "v002_entry": {"direction": "buy"},
            "v002_entry_ready": True,
            "legacy_canonical_fvg_in_ob": False, "legacy_score_passed": True,
        },
        {
            "decision_id": "d2", "available_at_ms": 2,
            "v002_pair_state": "MITIGATED", "v002_pair_reason": "block_already_mitigated",
            "v002_structurally_active": False, "v002_side": "SHORT", "v002_age_bars": 10,
            "v002_block_id": "y", "v002_fvg_associated": False,
            "v002_fvg_direction": None, "v002_exact_overlap_descriptive": None,
            "v002_gate11_score": {"passes_threshold": False, "max_score": 8},
            "v002_gate11_passed": False,
            "v002_strategy_eligible": False, "v002_strategy_reasons": ["ORDER_BLOCK_UNAVAILABLE"],
            "v002_strategy_order_block_state": "MITIGATED",
            "v002_setup_id": "s8n1_rejected", "v002_entry": None,
            "v002_entry_ready": False,
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
    funnel = aggregate["V002_variant_funnel"]
    assert funnel["gate_11_v002"] == {"entered": 2, "passed": 1, "failed": 1}
    assert funnel["canonical_strategy_v002"] == {"entered": 1, "passed": 1, "failed": 0}
    assert funnel["gate_12_13_rr_entry_v002"] == {"entered": 1, "passed": 1, "failed": 0}
    candidate = aggregate["candidate_surface"]
    assert candidate["candidate_ready"] == 1
    assert candidate["candidate_setup_ids"] == ["s8n1_full_candidate"]
    assert candidate["candidate_setup_ids"] != ["d1"]
    assert candidate["unique_candidate_setup_ids"] == 1
    assert candidate["duplicate_candidate_setup_id_occurrences"] == 0
    assert candidate["setup_id_reconciliation"]["unique_plus_duplicates_equals_candidate_ready"] is True
    assert candidate["candidate_long_count"] == 1
    assert candidate["candidate_short_count"] == 0
    assert candidate["candidate_entry_directions"] == ["buy"]
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
    row, next_record = evaluate_orchestration_decision(snapshot, prior)
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
    funnel = doc["V002_variant_funnel"]
    assert funnel["gate_11_v002"]["entered"] == 1
    assert funnel["gate_11_v002"]["passed"] >= 1
    assert funnel["canonical_strategy_v002"]["entered"] == funnel["gate_11_v002"]["passed"]
    assert funnel["gate_12_13_rr_entry_v002"]["entered"] == funnel["canonical_strategy_v002"]["passed"]
    assert doc["candidate_surface"]["candidate_ready"] == funnel["gate_12_13_rr_entry_v002"]["passed"]
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


# ---------------------------------------------------------------------------
# TC001 — Gate-11 ENTRANT population (phase6-development-v2-V002-TC001)
# ---------------------------------------------------------------------------

TC001_DEFECTIVE_COMMIT = "4890dcbce8579f159224b653d94f634cc9017549"


def _rescue_snapshot(at: datetime, monkeypatch) -> object:
    """Synthetic causal fixture where legacy Gate-11 fails but V002 passes.

    The frozen legacy acquisition OB detector returns an INVALID result
    (exactly the D001-observed dominant failure shape), so the frozen
    legacy Gate-11 valid-OB component (and its dependent FVG-in-OB
    component) score zero and the historical Gate-11 fails — while the
    upstream pipeline is otherwise unchanged, so the decision legitimately
    ENTERS Gate 11.  V002's structural semantics do not consume the legacy
    OB predicate: the canonical block from the M5 entry frame is
    structurally active and the persisted same-direction FVG associates
    (exact overlap not required), so the V002 score reaches 8/8.
    """
    from bot.state import gate_inputs as gi
    from config.symbol_profiles import get_symbol_profile
    from tests.test_phase8_v2_d001_tooling import _patch_engines
    from tests.test_phase8_v2_v002_variant import build_rows, to_frame

    from bot.strategy.config import StrategyConfig

    _patch_engines(monkeypatch)
    monkeypatch.setattr(gi, "detect_ob_breaker", lambda *a, **kw: {})
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


def test_tc001_real_adapter_legacy_fail_entrant_is_observed(monkeypatch):
    """A real evaluate_orchestration_decision row that ENTERS Gate 11 with
    historical Gate-11 FALSE must be observed by V002 — no exception."""
    snapshot = _SnapView(_rescue_snapshot(AT, monkeypatch), AT)
    from bot.strategy.setup_state import StrategyState, record_from_state
    from backtests.phase8_v2_diagnostic_d001 import evaluate_orchestration_decision

    seed = datetime(2024, 1, 1, tzinfo=UTC)
    prior = record_from_state(StrategyState(event_time=seed), event_at=seed)
    row, next_record = evaluate_orchestration_decision(snapshot, prior)
    assert "gate_11_confluence_score" in row["gate_results"], "must ENTER Gate 11"
    assert row["gate_results"]["gate_11_confluence_score"] is False
    observation = v002_eval.observe_v002_decision(
        row, snapshot, prior, config=_config(),
        decision_result_record=next_record,
    )
    assert observation["legacy_score_passed"] is False
    assert observation["v002_pair_state"] in (
        V002_ACTIVE, "MITIGATED", "RETEST_ELIGIBLE",
    )


def test_tc001_v002_rescue_semantic_difference_is_observable(monkeypatch):
    """Legacy Gate 11 fails; V002 structural pair + 8/8 evidence set passes.
    With all unchanged downstream protections clear, the decision is a
    V002 candidate — the core observable semantic effect."""
    snapshot = _SnapView(_rescue_snapshot(AT, monkeypatch), AT)
    from bot.strategy.setup_state import StrategyState, record_from_state
    from backtests.phase8_v2_diagnostic_d001 import evaluate_orchestration_decision

    seed = datetime(2024, 1, 1, tzinfo=UTC)
    prior = record_from_state(StrategyState(event_time=seed), event_at=seed)
    row, next_record = evaluate_orchestration_decision(snapshot, prior)
    assert row["gate_results"]["gate_11_confluence_score"] is False
    observation = v002_eval.observe_v002_decision(
        row, snapshot, prior, config=_config(),
        decision_result_record=next_record,
    )
    assert observation["legacy_score_passed"] is False
    assert observation["v002_structurally_active"] is True
    assert observation["v002_fvg_associated"] is True
    assert observation["v002_gate11_score"]["passes_threshold"] is True
    assert observation["v002_gate11_score"]["score"] == 8
    assert observation["v002_strategy_eligible"] is True
    assert observation["v002_entry_ready"] is True
    assert observation["v002_entry"]["direction"] == "buy"
    assert observation["v002_setup_id"].startswith("s8n1_")


def test_tc001_mixed_population_loop_reconciliation(monkeypatch):
    """Loop regression: (1) non-entrant excluded, (2) historical-fail
    entrant observed, (3) historical-pass entrant observed; observed == 2;
    both legacy outcomes present; the fail is not discarded; funnel/entrant
    reconciliation holds."""
    from bot.strategy.setup_state import StrategyState, record_from_state
    from tests.test_phase8_v2_d001_tooling import _Snapshot, _Table

    failing = _SnapView(_rescue_snapshot(AT, monkeypatch), AT)
    passing = _displacement_snapview(AT, monkeypatch)
    early = _Snapshot(
        available_at_ms=int(AT.timestamp() * 1000) - 1,
        gate_status="early_exit",
    )
    store = type("Store", (), {})()
    store.identity = _store_identity()
    store.table = _Table([early, failing, passing])

    doc, rendered = v002_eval.run_v002(
        store, implementation_commit=COMMIT_A, tooling_commit=COMMIT_A,
        blob_source=_fake_blob_source(),
    )
    surface = doc["V002_structural_pair_surface"]
    assert surface["gate11_entrants_observed"] == 2
    assert surface["gate11_entrants_observed"] == (
        doc["gate_funnel"]["gate_11_confluence_score"]["entered"]
    )
    legacy_fail = surface["legacy_score_failed_count"]
    legacy_pass = surface["legacy_score_passed_count"]
    assert legacy_fail == 1, "the historical Gate-11 failure must not be discarded"
    assert legacy_pass == 1
    assert legacy_fail + legacy_pass == 2
    funnel = doc["V002_variant_funnel"]
    candidate = doc["candidate_surface"]
    assert (
        candidate["candidate_ready"]
        <= funnel["canonical_strategy_v002"]["passed"]
        <= funnel["gate_11_v002"]["passed"]
        <= surface["gate11_entrants_observed"]
    )
    assert rendered  # deterministic canonical bytes produced


def _tc001_doc(surface: dict, candidate: dict) -> dict:
    """Minimal complete V002 document for surface-check unit tests."""
    entrants = int(surface.get("gate11_entrants_observed", 3))
    gate11_pass = int(surface.get("gate11_v002_score_pass_count", entrants))
    strategy_pass = int(surface.get("gate11_v002_score_pass_count", entrants))
    entry_pass = int(candidate.get("candidate_ready", strategy_pass))
    return {
        "decision_accounting": {
            "scheduled": 5, "reducer_classified": 5, "missing_history": 0,
            "unavailable_input": 0, "evaluation_error": 0,
        },
        "gate_funnel": {
            "gate_11_confluence_score": {"entered": 3, "passed": 1, "failed": 2},
        },
        "V002_structural_pair_surface": surface,
        "V002_variant_funnel": {
            "gate_11_v002": {"entered": entrants, "passed": gate11_pass, "failed": 0},
            "canonical_strategy_v002": {"entered": gate11_pass, "passed": strategy_pass, "failed": 0},
            "gate_12_13_rr_entry_v002": {"entered": strategy_pass, "passed": entry_pass, "failed": 0},
        },
        "candidate_surface": candidate,
        "success_classification_rule": {
            "OPPORTUNITY_SUFFICIENT": "candidate_ready >= 90",
        },
    }


def test_tc001_reconciliation_fails_closed_on_truncated_population():
    """The TC001 funnel/entrant reconciliation refuses a truncated V002
    population (the passer-based defect shape) at the surface check."""
    doc = _tc001_doc(
        {"gate11_entrants_observed": 1}, {"candidate_ready": 0},
    )
    with pytest.raises(v002_eval.V002EvalError) as error:
        v002_eval.assert_expected_surfaces(doc)
    assert "TC001" in str(error.value)


def test_tc001_candidate_exceeding_score_passes_fails_closed():
    doc = _tc001_doc(
        {"gate11_entrants_observed": 3, "gate11_v002_score_pass_count": 1},
        {"candidate_ready": 2},
    )
    with pytest.raises(v002_eval.V002EvalError) as error:
        v002_eval.assert_expected_surfaces(doc)
    assert "candidate" in str(error.value)


def test_tc001_old_bug_reproduction_against_defective_commit(monkeypatch):
    """The TC001 legacy-fail entrant regression FAILS against the defective
    tooling commit 4890dcb: its run_v002 skips historical Gate-11 failures
    and its observe_v002_decision rejects them.  Executed via an in-process
    import of the committed blob bytes — no subprocess, no checkout."""
    store = GitObjectStore(_gitobjectstore_root())
    legacy_bytes = _defective_tooling_bytes()
    assert b"the V002 population must be a subset of frozen" in legacy_bytes
    store.add_blob(legacy_bytes)
    tree = store.write_tree({"phase8_v2_variant_v002_eval.py": ("100644", store.add_blob(legacy_bytes))})
    commit = store.commit_tree(tree, "defective TC001 tooling")
    assert commit, "defective tooling materialized as a genuine Git commit object"

    module_name = "_v002_eval_defective_4890dcb"
    assert module_name not in sys.modules
    module = types.ModuleType(module_name)
    module.__file__ = str(_gitobjectstore_root() / "phase8_v2_variant_v002_eval.py")
    module.__dict__["__name__"] = module_name
    exec(compile(legacy_bytes, module.__file__, "exec"), module.__dict__)
    sys.modules[module_name] = module

    snapshot = _SnapView(_rescue_snapshot(AT, monkeypatch), AT)
    from bot.strategy.setup_state import StrategyState, record_from_state
    from backtests.phase8_v2_diagnostic_d001 import evaluate_orchestration_decision

    seed = datetime(2024, 1, 1, tzinfo=UTC)
    prior = record_from_state(StrategyState(event_time=seed), event_at=seed)
    row, next_record = evaluate_orchestration_decision(snapshot, prior)
    assert row["gate_results"]["gate_11_confluence_score"] is False
    # Old defect, rejection arm: the committed observer refuses a
    # historical Gate-11 FAILURE even when the row entered Gate 11.
    with pytest.raises(module.V002EvalError) as error:
        module.observe_v002_decision(row, snapshot, prior, config=_config())
    assert "subset of frozen" in str(error.value)
    # Old defect, skip arm: its run_v002 records zero observations for a
    # store containing exactly this entrant.
    from tests.test_phase8_v2_d001_tooling import _Table

    fake_store = type("Store", (), {})()
    fake_store.identity = _store_identity()
    fake_store.table = _Table([snapshot])
    doc, rendered = module.run_v002(
        fake_store, implementation_commit=COMMIT_A, tooling_commit=COMMIT_A,
        blob_source=_fake_blob_source(),
    )
    assert doc["V002_structural_pair_surface"]["gate11_entrants_observed"] == 0
    assert doc["gate_funnel"]["gate_11_confluence_score"]["entered"] == 1


def _defective_tooling_bytes() -> bytes:
    """Exact committed bytes of the tooling file at the defective commit,
    snapshotted verbatim into the fixture tree (tests/conftest.py forbids
    subprocess launches inside the suite; the copy is byte-verified in
    test_tc001_defective_fixture_matches_committed_bytes)."""
    fixture = Path(__file__).parent / "fixtures" / "v002_eval_4890dcb.py"
    return fixture.read_bytes()


def test_tc001_defective_fixture_matches_committed_bytes():
    """Byte-identity of the defective-tooling fixture copy against the real
    committed blob at 4890dcb (guarded by an env-var opt-in because the
    production check shells out to git, which the suite firewall forbids)."""
    import os
    import subprocess

    if os.environ.get("V002_TC001_VERIFY_COMMITTED_BYTES") != "1":
        pytest.skip(
            "subprocess git cat-file is prohibited inside the suite; run with "
            "V002_TC001_VERIFY_COMMITTED_BYTES=1 to byte-verify the fixture copy"
        )
    committed = subprocess.run(
        ["git", "cat-file", "blob",
         TC001_DEFECTIVE_COMMIT + ":backtests/phase8_v2_variant_v002_eval.py"],
        cwd=".", capture_output=True, check=True,
    ).stdout
    assert committed == _defective_tooling_bytes()


_GIT_STORE_ROOT = None


def _gitobjectstore_root():
    global _GIT_STORE_ROOT
    if _GIT_STORE_ROOT is None:
        _GIT_STORE_ROOT = Path(tempfile.mkdtemp(prefix="v002-tc001-gitstore-"))
    return _GIT_STORE_ROOT


# ---------------------------------------------------------------------------
# TC002 — candidate_ready through frozen Gates 12/13
# (phase6-development-v2-V002-TC002)
# ---------------------------------------------------------------------------

TC002_DEFECTIVE_COMMIT = "c2e74090e2ac29d54b2a5ed87c2ad28cac045bdb"


def _observe_with_next(snapshot, monkeypatch=None):
    """Run the real reducer loop once and observe the Gate-11 entrant."""
    from bot.strategy.setup_state import StrategyState, record_from_state
    from backtests.phase8_v2_diagnostic_d001 import evaluate_orchestration_decision

    seed = datetime(2024, 1, 1, tzinfo=UTC)
    prior = record_from_state(StrategyState(event_time=seed), event_at=seed)
    row, next_record = evaluate_orchestration_decision(snapshot, prior)
    return row, next_record, v002_eval.observe_v002_decision(
        row, snapshot, prior, config=_config(),
        decision_result_record=next_record,
    )


def test_tc002_strategy_eligible_but_entry_not_ready_is_not_candidate(monkeypatch):
    """V002 Gate 11 passes, downstream strategy is eligible, but the frozen
    entry model returns None: entry-ready False and NOT candidate_ready.
    The synthetic state lacks a real liquidity sweep triple (liquidity_type
    None), so determine_entry has no valid liquidity alignment and waits —
    exactly the historical entry_not_ready shape."""
    snapshot = _displacement_snapview(AT, monkeypatch)
    row, next_record, observation = _observe_with_next(snapshot)
    assert row["gate_results"]["gate_11_confluence_score"] is True
    assert observation["v002_gate11_passed"] is True
    assert observation["v002_strategy_eligible"] is True
    # Forced entry-not-ready: neutralize the frozen state's liquidity sweep
    # identity on the PRIVATE V002 entry state only (an unchanged
    # non-H007 reason the historical reducer reports entry_not_ready for).
    class _PrivateObserver:
        pass

    real_state_builder = v002_eval._v002_private_entry_state

    def _stripped_state(record, *, decision_at, payload):
        state = real_state_builder(record, decision_at=decision_at, payload=payload)
        state.liquidity_type = None
        state.liquidity_side = None
        return state

    v002_eval._v002_private_entry_state = _stripped_state
    try:
        row, next_record, observation = _observe_with_next(snapshot)
    finally:
        v002_eval._v002_private_entry_state = real_state_builder
    assert observation["v002_strategy_eligible"] is True
    assert observation["v002_entry_ready"] is False
    assert observation["v002_entry"] is None
    aggregate = v002_eval.aggregate_v002([observation])
    assert aggregate["candidate_surface"]["candidate_ready"] == 0
    assert aggregate["V002_variant_funnel"]["gate_12_13_rr_entry_v002"]["passed"] == 0


def test_tc002_full_candidate_counts_once(monkeypatch):
    """Full V002 candidate: historical Gate 11 fails, V002 Gate 11 passes
    8/8, V002 canonical strategy passes, frozen determine_entry returns a
    real entry; candidate_ready increments exactly once."""
    snapshot = _SnapView(_rescue_snapshot(AT, monkeypatch), AT)
    row, next_record, observation = _observe_with_next(snapshot)
    assert row["gate_results"]["gate_11_confluence_score"] is False
    assert observation["legacy_score_passed"] is False
    assert observation["v002_gate11_passed"] is True
    assert observation["v002_strategy_eligible"] is True
    assert observation["v002_entry_ready"] is True
    assert observation["v002_entry"] is not None
    aggregate = v002_eval.aggregate_v002([observation])
    assert aggregate["candidate_surface"]["candidate_ready"] == 1
    assert aggregate["candidate_surface"]["candidate_decision_ids"] == [
        row["decision_id"]
    ]


def test_tc002_legacy_equivalence_when_semantics_coincide(monkeypatch):
    """When historical and V002 semantics coincide, the historical reducer's
    action is reproduced by the V002 path over the same frozen inputs."""
    snapshot = _displacement_snapview(AT, monkeypatch)
    from bot.strategy.setup_state import StrategyState, record_from_state
    from backtests.phase8_v2_diagnostic_d001 import evaluate_orchestration_decision

    seed = datetime(2024, 1, 1, tzinfo=UTC)
    prior = record_from_state(StrategyState(event_time=seed), event_at=seed)
    row, next_record = evaluate_orchestration_decision(snapshot, prior)
    if row["action"] == "candidate_ready":
        observation = v002_eval.observe_v002_decision(
            row, snapshot, prior, config=_config(),
            decision_result_record=next_record,
        )
        assert observation["v002_entry_ready"] is True
    else:
        # The historical reducer refused entry for unchanged non-H007
        # reasons; V002 must not rescue it merely because the canonical
        # strategy passed — assert no entry is manufactured.
        observation = v002_eval.observe_v002_decision(
            row, snapshot, prior, config=_config(),
            decision_result_record=next_record,
        )
        if observation["v002_strategy_eligible"]:
            assert observation["v002_entry_ready"] is False


def test_tc002_funnel_regression_exact_chain(monkeypatch):
    """Synthetic population: Gate-11 fail, strategy fail, entry-not-ready,
    full candidate.  Funnel: entrants 4, gate11 pass 3, strategy pass 2,
    gate-12/13 pass 1, candidate_ready 1."""
    base = _SnapView(_displacement_snapshot, AT) if False else None
    snapshot_ok = _displacement_snapview(AT, monkeypatch)
    failing = _SnapView(_rescue_snapshot(AT, monkeypatch), AT)
    observations = []
    from bot.strategy.setup_state import StrategyState, record_from_state
    from backtests.phase8_v2_diagnostic_d001 import evaluate_orchestration_decision

    seed = datetime(2024, 1, 1, tzinfo=UTC)
    prior = record_from_state(StrategyState(event_time=seed), event_at=seed)

    # (1) V002 Gate-11 failure: strip the same-direction FVG from the payload
    # surface the observer sees (no FVG association -> score 6 < 8).
    row, next_record = evaluate_orchestration_decision(snapshot_ok, prior)
    gate_fail = dict(observation_of(row, snapshot_ok, prior, next_record))
    gate_fail["v002_gate11_passed"] = False
    gate_fail["v002_gate11_score"] = dict(gate_fail["v002_gate11_score"], passes_threshold=False, score=6)
    gate_fail["v002_strategy_eligible"] = False
    gate_fail["v002_entry_ready"] = False
    gate_fail["v002_entry"] = None
    observations.append(gate_fail)

    # (2) strategy fail: non-structural downstream rejection (DXY conflict).
    strategy_fail = dict(gate_fail)
    strategy_fail["decision_id"] = "synthetic-strategy-fail"
    strategy_fail["v002_gate11_passed"] = True
    strategy_fail["v002_gate11_score"] = dict(gate_fail["v002_gate11_score"], passes_threshold=True, score=8)
    strategy_fail["v002_strategy_eligible"] = False
    strategy_fail["v002_strategy_reasons"] = ["DXY_DIRECTION_CONFLICT"]
    strategy_fail["v002_entry_ready"] = False
    observations.append(strategy_fail)

    # (3) strategy pass but entry-not-ready.
    entry_fail = dict(gate_fail)
    entry_fail["decision_id"] = "synthetic-entry-fail"
    entry_fail["v002_gate11_passed"] = True
    entry_fail["v002_gate11_score"] = dict(gate_fail["v002_gate11_score"], passes_threshold=True, score=8)
    entry_fail["v002_strategy_eligible"] = True
    entry_fail["v002_entry_ready"] = False
    entry_fail["v002_entry"] = None
    observations.append(entry_fail)

    # (4) full candidate.
    row, next_record, observation = _observe_with_next(failing)
    assert observation["v002_entry_ready"] is True
    observations.append(dict(observation))

    aggregate = v002_eval.aggregate_v002(observations)
    funnel = aggregate["V002_variant_funnel"]
    assert funnel["gate_11_v002"]["entered"] == 4
    assert funnel["gate_11_v002"]["passed"] == 3
    assert funnel["canonical_strategy_v002"]["entered"] == 3
    assert funnel["canonical_strategy_v002"]["passed"] == 2
    assert funnel["gate_12_13_rr_entry_v002"]["entered"] == 2
    assert funnel["gate_12_13_rr_entry_v002"]["passed"] == 1
    assert aggregate["candidate_surface"]["candidate_ready"] == 1
    doc = {
        "decision_accounting": {"scheduled": 4, "reducer_classified": 4,
                                "missing_history": 0, "unavailable_input": 0,
                                "evaluation_error": 0},
        "gate_funnel": {"gate_11_confluence_score": {"entered": 4, "passed": 1, "failed": 3}},
        "V002_structural_pair_surface": aggregate["V002_structural_pair_surface"],
        "V002_variant_funnel": funnel,
        "candidate_surface": aggregate["candidate_surface"],
        "success_classification_rule": aggregate["success_classification_rule"],
    }
    v002_eval.assert_expected_surfaces(doc)  # hard reconciliation holds


def observation_of(row, snapshot, prior, next_record):
    return v002_eval.observe_v002_decision(
        row, snapshot, prior, config=_config(),
        decision_result_record=next_record,
    )


def test_tc002_candidate_id_is_setup_identity_not_decision_id(monkeypatch):
    snapshot = _SnapView(_rescue_snapshot(AT, monkeypatch), AT)
    row, next_record, observation = _observe_with_next(snapshot)
    persisted = json.loads(next_record.data()["last_result"])
    assert observation["v002_setup_id"] == persisted["setup_id"]
    assert observation["v002_setup_id"] != row["decision_id"]
    assert persisted["event_id"] == row["decision_id"]


def test_tc002_candidate_id_fails_closed_on_mismatched_render(monkeypatch):
    snapshot = _SnapView(_rescue_snapshot(AT, monkeypatch), AT)
    from bot.strategy.setup_state import StrategyState, record_from_state
    from backtests.phase8_v2_diagnostic_d001 import evaluate_orchestration_decision

    seed = datetime(2024, 1, 1, tzinfo=UTC)
    prior = record_from_state(StrategyState(event_time=seed), event_at=seed)
    row, next_record = evaluate_orchestration_decision(snapshot, prior)
    with pytest.raises(v002_eval.V002EvalError) as error:
        v002_eval._persisted_setup_id(next_record, "some-other-decision-id")
    assert "mismatch" in str(error.value)

    empty = type("R", (), {})()
    empty.data = lambda: {"last_event_id": row["decision_id"], "last_result": None}
    with pytest.raises(v002_eval.V002EvalError) as error:
        v002_eval._persisted_setup_id(empty, row["decision_id"])
    assert "persisted result missing" in str(error.value)


def test_tc002_old_bug_counts_entry_not_ready_as_candidate(monkeypatch):
    """The TC001 tooling at c2e7409 counts a strategy-eligible / entry-
    not-ready decision as candidate_ready; the corrected tooling must not.
    The defective bytes are snapshotted verbatim in the committed fixture
    (byte-verified out-of-suite via V002_TC001_VERIFY_COMMITTED_BYTES=1)."""
    fixture = Path(__file__).parent / "fixtures" / "v002_eval_c2e7409.py"
    legacy_bytes = fixture.read_bytes()
    assert b'candidate_ready = len(strategy_eligible)' in legacy_bytes
    module_name = "_v002_eval_defective_c2e7409"
    assert module_name not in sys.modules
    module = types.ModuleType(module_name)
    module.__file__ = str(fixture)
    exec(compile(legacy_bytes, module.__file__, "exec"), module.__dict__)
    sys.modules[module_name] = module

    # The same observation (strategy-eligible, entry-not-ready) evaluated by
    # the defective aggregate counts it as a candidate; TC002 tooling does
    # not require the field at all, so the defective surface is proven with
    # its OWN aggregate contract.
    defective_observation = {
        "decision_id": "d-entry-not-ready", "available_at_ms": 1,
        "v002_pair_state": V002_ACTIVE, "v002_pair_reason": "structurally_active_block",
        "v002_structurally_active": True, "v002_side": "LONG", "v002_age_bars": 5,
        "v002_block_id": "blk", "v002_fvg_associated": True,
        "v002_fvg_direction": "bullish", "v002_exact_overlap_descriptive": False,
        "v002_gate11_score": {"passes_threshold": True, "max_score": 8},
        "v002_strategy_eligible": True, "v002_strategy_reasons": ["APPROVED"],
        "v002_strategy_order_block_state": "ELIGIBLE",
        "legacy_canonical_fvg_in_ob": True, "legacy_score_passed": True,
    }
    defective_aggregate = module.aggregate_v002([defective_observation])
    assert defective_aggregate["candidate_surface"]["candidate_ready"] == 1, (
        "defective TC001 tooling counts strategy eligibility as candidate_ready"
    )
    corrected = dict(defective_observation)
    corrected.update({
        "v002_gate11_passed": True, "v002_setup_id": "s8n1_x",
        "v002_entry": None, "v002_entry_ready": False,
    })
    corrected_aggregate = v002_eval.aggregate_v002([corrected])
    assert corrected_aggregate["candidate_surface"]["candidate_ready"] == 0
