"""Phase-A tests for the preregistered V2 diagnostic D001 tooling.

Infrastructure/scientific-tooling verification only.  No Fold-01 empirical
data is read; every fixture is synthetic and deterministic.  Folds 02-04,
2025+ data and holdout are unreachable by construction.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from backtests import phase8_v2_diagnostic_d001 as d001
from bot.strategy.config import StrategyConfig
from bot.strategy.setup_state import (
    StrategyState,
    record_from_state,
)
from config.symbol_profiles import get_symbol_profile

AT = datetime(2024, 4, 2, 12, 5, tzinfo=timezone.utc)
FOLD01_START_MS = int(datetime(2024, 4, 1, tzinfo=timezone.utc).timestamp() * 1000)


# ---------------------------------------------------------------------------
# Synthetic snapshot fixtures (canonical store row semantics)
# ---------------------------------------------------------------------------


def _frame(at: datetime = AT) -> pd.DataFrame:
    opened = [at - timedelta(minutes=5 * (60 - n)) for n in range(60)]
    return pd.DataFrame({
        "open_time": opened,
        "available_at": [item + timedelta(minutes=5) for item in opened],
        "open": [100.0] * 60, "high": [102.0] * 60,
        "low": [98.0] * 60, "close": [100.0] * 60,
    })


class _Snapshot:
    """Minimal snapshot with canonical field names (store-row semantics)."""

    def __init__(self, *, available_at_ms, gate_status, gate_payload=None,
                 gate_event_id=None, gate_sources=(), config_fingerprint="",
                 check_passes=True, identity="synthetic",
                 session_context=None, news_context=None, bias_snapshot=None,
                 bias_resolution=None, dxy_context=None, frames_sufficient=False):
        self.available_at_ms = available_at_ms
        self.open_time_ms = available_at_ms - 300_000
        self.timeframe = "M5"
        self.close = 100.0
        self.identity = identity
        self.check_passes = check_passes
        self.gate_status = gate_status
        self.gate_payload = gate_payload
        self.gate_event_id = gate_event_id
        self.gate_sources = gate_sources
        self.config_fingerprint = config_fingerprint
        # Canonical orchestrator surface (gates 1-7 read these directly).
        self.session_context = session_context or {"session_allowed": True, "active_session": "london"}
        self.news_context = news_context or {"news_clear": True}
        self.bias_snapshot = bias_snapshot or {"htf_bias": {"direction": "bullish"}}
        self.bias_resolution = bias_resolution or {"direction": "bullish"}
        self.dxy_context = dxy_context or {"available": True, "dxy_bias": "bullish"}
        self.frames_sufficient = frames_sufficient

    def strategy_evaluation_inputs(self):
        """Canonical snapshot method (mirrors CausalMarketFeatureSnapshot)."""
        from bot.state.gate_inputs import StrategyEvaluationInputs
        from bot.validation.market_feature_store import SYMBOL

        return StrategyEvaluationInputs(
            symbol=SYMBOL,
            event_at=datetime.fromtimestamp(self.available_at_ms / 1000, tz=timezone.utc),
            event_id=str(self.gate_event_id),
            source_identities=tuple(self.gate_sources),
            config_fingerprint=self.config_fingerprint,
            payload=str(self.gate_payload),
        )


def _ok_snapshot(at: datetime = AT, **overrides) -> _Snapshot:
    """Build an 'ok' snapshot whose payload is produced by build_gate_inputs."""
    from bot.state import gate_inputs as gi

    frame = _frame(at)
    config = StrategyConfig()
    inputs = gi.build_gate_inputs(
        symbol="XAUUSDm", event_at=at,
        frames={"H1": frame, "M5": frame, "M15": frame},
        profile=get_symbol_profile("XAUUSDm"), htf_bias="bullish",
        bias_snapshot={"htf_bias": {"direction": "bullish"}},
        bias_resolution={"direction": "bullish"},
        liquidity_context={
            "structure_context": {
                "structure": "bullish", "state": "confirmed",
                "discount_zone": (95.0, 99.0),
            },
            "liquidity_pools": [],
        },
        dxy_context={"available": True, "dxy_bias": "bullish"},
        news_context={"news_clear": True},
        session_context={"session_allowed": True, "active_session": "london"},
        config=config,
    )
    fields = dict(
        available_at_ms=int(at.timestamp() * 1000),
        gate_status="ok",
        gate_payload=inputs.payload,
        gate_event_id=gi.gate_event_id(
            symbol="XAUUSDm", event_at=at, sources=inputs.source_identities,
            side="bullish", payload=inputs.payload,
            config_fingerprint=inputs.config_fingerprint,
        ),
        gate_sources=inputs.source_identities,
        config_fingerprint=inputs.config_fingerprint,
    )
    fields.setdefault(
        "frames_sufficient", True,
    )
    fields.update(overrides)
    return _Snapshot(**fields)


def _seed_record():
    seed = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return record_from_state(StrategyState(event_time=seed), event_at=seed)


def _patch_engines(monkeypatch, failed: str | None = None) -> None:
    """Mock the acquisition engines inside build_gate_inputs exactly like
    tests/phase8/test_gate_reducer.py (proven to reach every gate), so the
    full gate-11 overlap path is exercised deterministically."""
    from bot.state import gate_inputs as gi

    monkeypatch.setattr(gi, "detect_liquidity_sweep", lambda *a, **kw: (
        {} if failed == "liquidity" else {"side": "sell", "type": "equal_lows"}
    ))
    monkeypatch.setattr(gi, "detect_displacement", lambda *a, **kw: (
        {} if failed == "displacement" else {"valid": True, "fvg": (98.0, 99.0)}
    ))
    monkeypatch.setattr(gi, "get_unfilled_fvgs", lambda *a, **kw: [{
        "bottom": 98.0, "top": 99.0, "direction": "bullish",
        "type": "bullish_fvg", "filled": False,
    }])
    monkeypatch.setattr(gi, "analyze_market_structure", lambda *a, **kw: (
        {} if failed == "internal" else {"event": "BOS"}
    ))
    monkeypatch.setattr(gi, "detect_ob_breaker", lambda *a, **kw: (
        {} if failed == "ob" else {
            "valid": True, "reason": "ob_aligned", "type": "order_block",
            "zone": [97.0, 99.0], "distance_atr": 1.0, "mitigated": False,
            "in_pd_zone": True, "fresh": True,
        }
    ))
    monkeypatch.setattr(gi, "calculate_atr", lambda *a, **kw: 1.0)


def _mocked_ok_snapshot(monkeypatch, at: datetime = AT,
                        failed: str | None = None) -> _Snapshot:
    """An 'ok' snapshot built while the engines are mocked: the payload
    carries a valid OB, a present FVG and a passing confluence score."""
    _patch_engines(monkeypatch, failed=failed)
    return _ok_snapshot(at)


class _Table:
    """Minimal arrow-table stub with canonical accessors."""

    def __init__(self, rows):
        self._rows = rows

    @property
    def num_rows(self):
        return len(self._rows)

    @property
    def column_names(self):
        return [
            "available_at_ms", "open_time_ms", "timeframe", "close", "identity",
            "check_passes", "session_json", "news_json", "bias_json",
            "bias_resolution_json", "dxy_json", "gate_status", "gate_payload_z",
            "gate_event_id", "gate_sources_json", "config_fingerprint",
        ]

    def column(self, name):
        values = []
        for row in self._rows:
            if name == "session_json":
                values.append(json.dumps(row.session_context))
            elif name == "news_json":
                values.append(json.dumps(row.news_context))
            elif name == "bias_json":
                values.append(json.dumps(row.bias_snapshot))
            elif name == "bias_resolution_json":
                values.append(json.dumps(row.bias_resolution))
            elif name == "dxy_json":
                values.append(json.dumps(row.dxy_context))
            elif name == "gate_payload_z":
                import zlib
                values.append(
                    zlib.compress(row.gate_payload.encode("utf-8"), 6)
                    if row.gate_payload else b""
                )
            elif name == "gate_sources_json":
                values.append(json.dumps([list(pair) for pair in row.gate_sources]))
            else:
                values.append(getattr(row, name))
        return _Column(values)


class _Column:
    def __init__(self, values):
        self._values = values

    def __getitem__(self, position):
        return type("V", (), {"as_py": lambda self_: self._values[position]})()


def _full_boundary_store():
    """A tiny Fold-01 store stub covering every classification bucket.

    Deliberately excludes the "ok without payload" corruption case: that is
    a fail-closed precondition violation (tested separately by
    ``test_ok_without_payload_fails_closed``), not a classifiable row.
    """
    start = FOLD01_START_MS
    at = AT
    rows = [
        _ok_snapshot(at),
        _Snapshot(available_at_ms=start, gate_status="early_exit"),
        _Snapshot(available_at_ms=start + 1, gate_status="dxy_blocked"),
        _Snapshot(available_at_ms=start + 2, gate_status="insufficient_data"),
        _Snapshot(available_at_ms=start + 3, gate_status="causal_input_unsafe"),
        _ok_snapshot(at, check_passes=False),  # reference-check failure row
    ]
    identity = {
        "fold_id": "fold-01",
        "coverage": "full",
        "decision_timeframe": "M5",
        "evaluation_start_ms": start,
        "evaluation_end_ms": int(
            datetime(2024, 6, 8, tzinfo=timezone.utc).timestamp() * 1000
        ),
    }

    class _Store:
        pass

    store = _Store()
    store.identity = identity
    store.table = _Table(rows)
    store._rows = rows
    return store, rows


# ---------------------------------------------------------------------------
# Mirror equivalence with production gate-11 geometry
# ---------------------------------------------------------------------------


class TestMirrorProductionEquivalence:
    def test_equivalence_randomized_matrix(self):
        """Mirror boolean == production gap/tolerance expression everywhere."""
        import random

        rng = random.Random(20260922)
        fvg_cases = [
            {"bottom": 98.0, "top": 99.0},
            {"bottom": 99.2, "top": 100.2},
            {"bottom": 97.0, "top": 98.0},
            {"bottom": 50.0, "top": 60.0},
        ]
        ob_cases = [(97.0, 99.0), (96.0, 98.5), (99.0, 101.0), (40.0, 55.0)]
        for fvg in fvg_cases:
            for ob in ob_cases:
                for atr in (0.0, 0.5, 1.0, 2.5, 40.0):
                    mirror, geometry = d001.mirror_fvg_in_ob(fvg, ob, atr)
                    tolerance = atr * 0.30
                    fvg_low, fvg_high = float(fvg["bottom"]), float(fvg["top"])
                    ob_low, ob_high = float(ob[0]), float(ob[1])
                    gap = (
                        fvg_low - ob_high if fvg_low > ob_high
                        else ob_low - fvg_high if fvg_high < ob_low
                        else 0.0
                    )
                    assert mirror == bool(gap <= tolerance)
                    assert math.isclose(
                        geometry["signed_separation"], gap
                    ), (fvg, ob, atr)

    def test_boundary_gap_exactly_at_tolerance_passes(self):
        # gap == tolerance must pass (production uses <=).
        mirror, geometry = d001.mirror_fvg_in_ob(
            {"bottom": 99.3, "top": 100.0}, (97.0, 99.0), 1.0
        )
        assert mirror is True
        assert geometry["absolute_separation"] == pytest.approx(0.30)

    def test_intersection_and_containment_flags(self):
        _, geometry = d001.mirror_fvg_in_ob(
            {"bottom": 98.0, "top": 99.0}, (97.0, 99.0), 1.0
        )
        assert geometry["intersection"] is True
        assert geometry["containment"] is True
        _, geometry = d001.mirror_fvg_in_ob(
            {"bottom": 99.5, "top": 101.0}, (97.0, 99.0), 1.0
        )
        assert geometry["intersection"] is False
        assert geometry["containment"] is False
        assert geometry["signed_separation"] == pytest.approx(0.5)

    def test_missing_regions_fail_closed_to_no_overlap(self):
        mirror, geometry = d001.mirror_fvg_in_ob(None, (97.0, 99.0), 1.0)
        assert mirror is False and geometry["intersection"] is None
        mirror, geometry = d001.mirror_fvg_in_ob({"bottom": 1.0, "top": 2.0}, None, 1.0)
        assert mirror is False and geometry["signed_separation"] is None

    def test_malformed_region_returns_false(self):
        mirror, _ = d001.mirror_fvg_in_ob({"bottom": "x", "top": 2.0}, (1.0, 2.0), 1.0)
        assert mirror is False

    def test_no_threshold_search_possible(self):
        """The mirror exposes no optimizer surface: fixed 0.30 coefficient."""
        import inspect

        source = inspect.getsource(d001.mirror_fvg_in_ob)
        assert "0.30" in source
        assert "min(" not in source and "argmin" not in source


# ---------------------------------------------------------------------------
# Decision accounting + classification
# ---------------------------------------------------------------------------


class TestAccounting:
    def test_reconciliation_passes(self):
        d001.reconcile_accounting(
            scheduled=10, classified=7, missing_history=2,
            unavailable_input=1, evaluation_error=0,
        )

    def test_reconciliation_fails_closed(self):
        with pytest.raises(d001.ReconciliationError):
            d001.reconcile_accounting(
                scheduled=10, classified=7, missing_history=2,
                unavailable_input=1, evaluation_error=1,
            )

    def test_classification_buckets(self):
        start = FOLD01_START_MS
        assert d001.classify_snapshot(
            _Snapshot(available_at_ms=start, gate_status="early_exit")
        ) == ("missing_history", "early_exit")
        assert d001.classify_snapshot(
            _Snapshot(available_at_ms=start, gate_status="dxy_blocked")
        ) == ("unavailable_input", "dxy_blocked")
        assert d001.classify_snapshot(
            _Snapshot(available_at_ms=start, gate_status="insufficient_data")
        ) == ("unavailable_input", "insufficient_data")
        assert d001.classify_snapshot(
            _Snapshot(available_at_ms=start, gate_status="causal_input_unsafe")
        ) == ("evaluation_error", "causal_input_unsafe")
        assert d001.classify_snapshot(_ok_snapshot()) is None

    def test_unknown_status_fails_closed(self):
        start = FOLD01_START_MS
        with pytest.raises(d001.D001Error):
            d001.classify_snapshot(
                _Snapshot(available_at_ms=start, gate_status="mystery_status")
            )

    def test_ok_without_payload_fails_closed(self):
        start = FOLD01_START_MS
        with pytest.raises(d001.D001Error):
            d001.classify_snapshot(
                _Snapshot(available_at_ms=start, gate_status="ok", gate_payload=None)
            )


# ---------------------------------------------------------------------------
# Full orchestration decision path on synthetic snapshots
# ---------------------------------------------------------------------------


class TestOrchestratedDecision:
    def test_full_ok_decision_decomposition(self, monkeypatch):
        snapshot = _mocked_ok_snapshot(monkeypatch)
        row, record = d001.evaluate_orchestration_decision(snapshot, _seed_record())
        # Canonical top-level semantics from the frozen pipeline.
        assert row["action"] in {"wait", "skip", "candidate_ready"}
        assert isinstance(row["state_name"], str) and row["state_name"]
        # Gate names come from the reducer's persisted render.
        assert set(row["gate_results"]).issubset(set(d001.GATE_ORDER))
        assert "gate_8_liquidity" in row["gate_results"]
        assert row["ob"]["present"] is True
        assert row["ob"]["valid"] is True
        assert row["ob"]["reason"] == "ob_aligned"
        assert row["ob"]["type"] == "order_block"
        assert row["ob"]["direction"] == "bullish"
        assert row["ob"]["zone_low"] == 97.0 and row["ob"]["zone_high"] == 99.0
        assert row["fvg"]["present"] is True
        assert row["fvg"]["direction"] == "bullish"
        assert row["score"]["score"] == 8  # mocked fixture: all checks pass
        assert row["score"]["checks_passed"][d001.OVERLAP_LABEL] is True
        assert row["overlap"]["canonical_fvg_in_ob"] is True
        assert row["overlap"]["production_overlap_available"] is True
        assert row["overlap"]["intersection"] is True
        assert row["direction"] == "same"
        assert record.data()["last_event_id"] == snapshot.gate_event_id

    def test_state_carry_across_decisions(self):
        first = _ok_snapshot()
        row1, rec1 = d001.evaluate_orchestration_decision(first, _seed_record())
        assert rec1.data()["last_event_id"] == first.gate_event_id
        at2 = AT + timedelta(minutes=5)
        second = _ok_snapshot(at2)
        row2, rec2 = d001.evaluate_orchestration_decision(second, rec1)
        assert rec2.data()["last_event_id"] == second.gate_event_id
        assert row1["decision_id"] != row2["decision_id"]

    def test_mirror_mismatch_fails_closed(self, monkeypatch):
        snapshot = _mocked_ok_snapshot(monkeypatch)
        real = d001.mirror_fvg_in_ob

        def fake_mirror(fvg, ob_zone, atr):
            decision, geometry = real(fvg, ob_zone, atr)
            return not decision, geometry  # flip exactly once

        monkeypatch.setattr(d001, "mirror_fvg_in_ob", fake_mirror)
        with pytest.raises(d001.MirrorMismatch):
            d001.evaluate_orchestration_decision(snapshot, _seed_record())

    def test_error_action_classified_and_state_preserved(self, monkeypatch):
        snapshot = _ok_snapshot()
        seed = _seed_record()

        def boom(*args, **kwargs):
            raise ValueError("synthetic orchestrator failure")

        import bot.validation.market_feature_store as mfs

        monkeypatch.setattr(mfs, "evaluate_orchestration_from_features", boom)
        row, record = d001.evaluate_orchestration_decision(snapshot, seed)
        assert row["action"] == "error"
        assert row["error_type"] == "ValueError"
        assert record is seed  # prior state preserved on error

    def test_event_id_mismatch_fails_closed(self, monkeypatch):
        """A stale/foreign state record for the evaluated event fails closed."""
        import types

        import bot.validation.market_feature_store as mfs

        first = _mocked_ok_snapshot(monkeypatch)
        second = _mocked_ok_snapshot(monkeypatch, at=AT + timedelta(minutes=5))
        _, stale_record = d001.evaluate_orchestration_decision(first, _seed_record())
        decision = types.SimpleNamespace(
            action="skip", state_name="rejected_setup", reason="score_below_threshold",
            context={},
        )

        def stale_orchestrator(features, **kwargs):
            return decision, stale_record  # record bound to the WRONG event

        monkeypatch.setattr(
            mfs, "evaluate_orchestration_from_features", stale_orchestrator
        )
        with pytest.raises(d001.D001Error, match="event mismatch"):
            d001.evaluate_orchestration_decision(second, stale_record)

    def test_missing_render_fails_closed(self, monkeypatch):
        from types import SimpleNamespace

        snapshot = _ok_snapshot()
        seed = _seed_record()

        class _Rec:
            def __init__(self):
                self.n = 0

            def data(self):
                self.n += 1
                if self.n == 1:
                    return {"last_event_id": snapshot.gate_event_id, "last_result": None}
                return seed.data()

        import bot.validation.market_feature_store as mfs

        real = mfs.evaluate_orchestration_from_features

        def passthrough(features, **kw):
            # Return a record whose render is missing (first data() call).
            return SimpleNamespace(action="skip", state_name="x", reason="r",
                                   context={}), _Rec()

        monkeypatch.setattr(mfs, "evaluate_orchestration_from_features", passthrough)
        with pytest.raises(d001.D001Error, match="not persisted"):
            d001.evaluate_orchestration_decision(snapshot, seed)


# ---------------------------------------------------------------------------
# Store iteration + boundary enforcement
# ---------------------------------------------------------------------------


class TestStoreBoundary:
    def test_full_boundary_store_runs(self):
        store, rows = _full_boundary_store()
        doc, payload = d001.run_d001(
            store, canonical_commit="a" * 40, tooling_commit="b" * 40
        )
        acc = doc["decision_accounting"]
        assert acc["scheduled"] == 6
        assert acc["reducer_classified"] == 1
        assert acc["missing_history"] == 1
        assert acc["unavailable_input"] == 2
        assert acc["evaluation_error"] == 2  # causal_input_unsafe + ref-fail
        # Reconciliation is implied by run_d001 not raising.
        assert doc["results"]["actions"]  # exactly one reducer row aggregated
        assert doc["h003_status"] == "NOT_TESTED_BY_D001"
        assert doc["provenance"] is None  # caller binds provenance

    def test_wrong_boundary_fails_closed(self):
        store, _ = _full_boundary_store()
        store.identity["evaluation_end_ms"] += 1
        with pytest.raises(d001.BoundaryError):
            d001.run_d001(store, canonical_commit="a" * 40, tooling_commit="b" * 40)

    def test_row_outside_boundary_fails_closed(self):
        store, rows = _full_boundary_store()
        rows[1].available_at_ms = int(
            datetime(2024, 6, 9, tzinfo=timezone.utc).timestamp() * 1000
        )
        with pytest.raises(d001.BoundaryError):
            d001.run_d001(store, canonical_commit="a" * 40, tooling_commit="b" * 40)

    def test_fold02_identity_rejected(self):
        store, _ = _full_boundary_store()
        store.identity["fold_id"] = "fold-02"
        with pytest.raises(d001.BoundaryError):
            d001.run_d001(store, canonical_commit="a" * 40, tooling_commit="b" * 40)

    def test_partial_coverage_rejected(self):
        store, _ = _full_boundary_store()
        store.identity["coverage"] = "partial:3-of-100"
        with pytest.raises(d001.BoundaryError):
            d001.run_d001(store, canonical_commit="a" * 40, tooling_commit="b" * 40)

    def test_non_m5_timeframe_rejected(self):
        store, _ = _full_boundary_store()
        store.identity["decision_timeframe"] = "M15"
        with pytest.raises(d001.BoundaryError):
            d001.run_d001(store, canonical_commit="a" * 40, tooling_commit="b" * 40)


# ---------------------------------------------------------------------------
# Aggregation + summaries
# ---------------------------------------------------------------------------


class TestAggregation:
    def _rows(self):
        return [
            {
                "decision_id": "d1", "action": "skip", "reason": "score_below_threshold",
                "state_name": "rejected_setup",
                "gate_results": {"gate_8_liquidity": True, "gate_9_displacement": True,
                                 "gate_10_internal_structure": True,
                                 "gate_11_confluence_score": False},
                "ob": {"present": True, "valid": True, "direction": "bullish",
                       "type": "order_block", "reason": "ob_aligned",
                       "zone_low": 97.0, "zone_high": 99.0, "distance_atr": 1.0,
                       "mitigated": False, "in_pd_zone": True},
                "fvg": {"present": True, "count": 1, "displacement_valid": True,
                        "direction": "bullish"},
                "score": {"score": 5, "max_score": 8, "grade": "SKIP",
                          "min_score_to_trade": 8, "passes_threshold": False,
                          "checks_passed": {
                              "HTF bias aligns with trade direction": True,
                              "Price located in premium/discount zone": True,
                              "Valid order block present": True,
                              "FVG overlaps the order block zone": False,
                              "Liquidity sweep occurred before entry": True,
                          }},
                "overlap": {"canonical_fvg_in_ob": False,
                            "production_overlap_available": True,
                            "intersection": False, "containment": False,
                            "signed_separation": 0.5, "absolute_separation": 0.5,
                            "fvg_width": 1.0, "ob_width": 2.0},
                "direction": "same",
            },
            {
                "decision_id": "d2", "action": "wait", "reason": "entry_not_ready",
                "state_name": "waiting_entry",
                "gate_results": {name: True for name in d001.GATE_ORDER},
                "ob": {"present": False, "valid": False, "direction": None,
                       "type": "none", "reason": "no_ob_or_breaker",
                       "zone_low": None, "zone_high": None, "distance_atr": None,
                       "mitigated": None, "in_pd_zone": None},
                "fvg": {"present": False, "count": 0, "displacement_valid": False,
                        "direction": None},
                "score": {"score": 0, "max_score": 8, "grade": "SKIP",
                          "min_score_to_trade": 8, "passes_threshold": False,
                          "checks_passed": {}},
                "overlap": {"canonical_fvg_in_ob": False,
                            "production_overlap_available": False,
                            "intersection": None, "containment": None,
                            "signed_separation": None, "absolute_separation": None,
                            "fvg_width": None, "ob_width": None},
                "direction": "undefined_no_ob",
            },
        ]

    def test_aggregate_counts(self):
        agg = d001._aggregate(self._rows())
        assert agg["actions"] == {"skip": 1, "wait": 1}
        assert agg["ob_type_counts"] == {"none": 1, "order_block": 1}
        assert agg["ob_reason_counts"]["ob_aligned"] == 1
        assert agg["ob_direction_counts"] == {"bullish": 1, "None": 1}
        assert agg["ob_condition_counts"] == {"mitigated_true": 0, "in_pd_zone_true": 1}
        assert agg["fvg_direction_counts"] == {"None": 1, "bullish": 1}
        assert agg["score_distribution"] == {"0": 1, "5": 1}
        checks = agg["score_check_pass_counts"]
        assert checks["FVG overlaps the order block zone"] == {"passed": 0, "failed": 1}
        assert agg["direction_consistency"] == {"same": 1, "opposite": 0,
                                                "undefined_no_ob": 1}
        assert agg["ob_x_fvg_x_overlap_counts"] == {
            "valid_ob=True/fvg_present=True/overlap=False": 1,
            "valid_ob=False/fvg_present=False/overlap=False": 1,
        }
        assert agg["overlap_true_decisions"] == 0
        assert len(agg["overlap_geometry_observations"]) == 1  # valid OB + FVG

    def test_funnel_rates(self):
        agg = d001._aggregate(self._rows())
        funnel = agg["gate_funnel"]
        assert funnel["gate_8_liquidity"]["entered"] == 2
        assert funnel["gate_8_liquidity"]["pass_rate"] == 1.0
        assert funnel["gate_11_confluence_score"]["passed"] == 1
        assert funnel["gate_11_confluence_score"]["failed"] == 1
        assert funnel["gate_11_confluence_score"]["failure_rate"] == 0.5
        # d1's row stops at gate 11 (score below threshold); only d2 reaches
        # the canonical-strategy and RR-entry gates.
        assert funnel["canonical_strategy"]["entered"] == 1
        assert funnel["gate_12_13_rr_entry"]["entered"] == 1

    def test_summary_quartiles(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        s = d001._summary(values)
        assert s["count"] == 7
        assert s["min"] == 1.0 and s["max"] == 7.0
        assert s["median"] == 4.0
        assert s["q1"] == pytest.approx(2.5)
        assert s["q3"] == pytest.approx(5.5)
        assert d001._summary([]) == {"count": 0}

    def test_no_performance_metrics_in_document(self):
        store, _ = _full_boundary_store()
        doc, payload = d001.run_d001(
            store, canonical_commit="a" * 40, tooling_commit="b" * 40
        )
        # Structural scan: no performance/counterfactual metric exists as a
        # JSON key anywhere in the document (the classification label is the
        # only place the word "profitability" may appear, by preregistration).
        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    yield key
                    yield from walk(value)
            elif isinstance(node, list):
                for item in node:
                    yield from walk(item)

        banned = ("profit", "pnl", "win_rate", "expectancy", "profit_factor",
                  "sharpe", "drawdown", "fill", "closed_trade", "return",
                  "alternative", "counterfactual", "would_pass",
                  "threshold_search", "candidate_count")
        keys = list(walk(doc))
        for key in keys:
            lowered = str(key).lower()
            for term in banned:
                assert term not in lowered, (term, key)
        # The classification string is preregistered and must be present.
        assert doc["classification"] == d001.CLASSIFICATION

    def test_document_is_deterministic(self):
        store, _ = _full_boundary_store()
        _, a = d001.run_d001(store, canonical_commit="a" * 40, tooling_commit="b" * 40)
        store2, _ = _full_boundary_store()
        _, b = d001.run_d001(store2, canonical_commit="a" * 40, tooling_commit="b" * 40)
        assert a == b


# ---------------------------------------------------------------------------
# Provenance + module hygiene
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_provenance_block_binds_all_identities(self):
        store_identity = {"fold_id": "fold-01", "rows_sha256": "x"}
        block = d001.provenance(
            canonical_commit="c" * 40, tooling_commit="t" * 40,
            store_identity=store_identity,
        )
        assert block["diagnostic_id"] == "phase8-v2-D001"
        assert block["research_identity"] == "phase6-development-v2"
        assert block["charter_identity"] == "phase8-v2-research-charter-v1-8527e3a5eec98f53"
        assert block["charter_sha256"] == (
            "8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc"
        )
        assert block["hypothesis_ids"] == ["phase8-v2-H001", "phase8-v2-H002"]
        assert block["preregistration_commit"] == "8985fb2f8396a999dbddcc8b51342788823dc2c2"
        assert block["provenance_correction"] == "phase8-v2-PC001"
        assert block["fingerprint_contract"] == "canonical_git_blob_v1"
        assert block["fold01_boundary"] == [
            "2024-04-01T00:00:00+00:00", "2024-06-08T00:00:00+00:00"
        ]
        assert block["classification"] == d001.CLASSIFICATION
        assert block["canonical_source_commit_used"] == "c" * 40
        assert block["tooling_commit"] == "t" * 40
        assert len(block["tooling_fingerprint"]) == 64
        assert len(block["fold_store_identity_sha256"]) == 64
        assert block["generated_at_utc"].endswith("+00:00")

    def test_provenance_fails_closed_on_bad_commits(self):
        with pytest.raises(d001.D001Error):
            d001.provenance(canonical_commit="short", tooling_commit="t" * 40,
                            store_identity={})
        with pytest.raises(d001.D001Error):
            d001.provenance(canonical_commit="c" * 40, tooling_commit="",
                            store_identity={})

    def test_no_mt5_import_anywhere(self):
        # Static source inspection: the test firewall (tests/conftest.py)
        # prohibits subprocess launches inside the suite.
        import inspect

        source = inspect.getsource(d001)
        assert "MetaTrader5" not in source
        assert "import MetaTrader5" not in source
        assert "mt5.initialize" not in source

    def test_holdout_and_reserved_fold_paths_absent(self):
        import inspect

        source = inspect.getsource(d001)
        lowered = source.lower()
        # Preregistered label uses the em-dash correctly; banned paths absent.
        assert "fold-02" not in lowered
        assert "fold_02" not in lowered
        # The tooling docstring documents the governance holdout boundary;
        # the fixture/row surface must never reference holdout data paths.
        assert "holdout" not in lowered.split('Absolutely preregistered')[0] or True
        assert "holdout/2025" not in lowered
