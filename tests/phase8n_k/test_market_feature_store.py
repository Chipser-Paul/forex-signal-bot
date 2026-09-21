"""Phase 8N-K focused tests: causal market-feature memoization equivalence.

Synthetic fixtures only.  No network, no MT5, no strategy evaluation on the
empirical datasets, no holdout access, no profitability computation.

The feature-snapshot path (memoized scenario-invariant features + shared
reducer) must produce exactly the same observable state as the reference
path and the Phase 8N-J indexed path.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.validation import empirical_input_pipeline as pipeline  # noqa: E402
from bot.validation import market_feature_store as features  # noqa: E402
from bot.validation import replay_input_index as replay  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "tests" / "phase8n_j"))
from test_replay_input_index import (  # noqa: E402
    _attach_intent_injector,
    _fixture_cell,
    _run_optimized_with_index,
    _run_reference,
    _trading_fixture,
)


def _build_store(bindings, index, candle_frames, constituent_frames, evidence_root):
    records = features.build_feature_records(
        bindings, index,
        candle_frames=candle_frames,
        constituent_frames=constituent_frames,
    )
    path, sha = features.publish_feature_store(
        records, evidence_root=evidence_root, bindings=bindings, index=index,
    )
    return path, sha


def _run_snapshot(
    bindings, index, store_path, cell, out, *,
    batch_rows=None, feature_provider=None,
):
    fold = bindings.plan["folds"][0]
    scenario = {"scenario_id": cell["scenario"]["scenario_id"]}
    context = pipeline.CellExecutionContext(
        cell=cell, fold=fold, scenario=scenario, bindings=bindings, cell_dir=out,
    )
    warmup = int(pd.Timestamp(fold["warmup"]["start"]).value // 1_000_000)
    end = min(int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000), pipeline.DEVELOPMENT_END_MS)
    candle_frames = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
    constituent_frames = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
    handler = pipeline.CellEventHandler(context, candle_frames=candle_frames, constituent_frames=constituent_frames)
    _attach_intent_injector(handler, context)
    store = features.load_feature_store(store_path)
    handler.feature_provider = features.FoldFeatureProvider(store, index=index)
    driver = replay.OptimizedCellDriver(context, handler, index=index)
    outcome = driver.run(**({} if batch_rows is None else {"batch_rows": batch_rows}))
    return {
        "outcome": outcome,
        "decisions": context.decisions,
        "rejections": context.rejections,
        "fills": [dict(vars(fill)) for fill in context.engine.fills],
        "ledger": [dict(vars(entry)) for entry in context.engine.ledger],
        "balance": context.engine.account.balance,
        "swap": context.engine.account.swap,
        "consumed": sorted(context.consumed_event_keys),
        "pending": len(context.pending_intents),
        "lifecycle": {key: position.status.value for key, position in context.lifecycle_positions.items()},
    }


# ---------------------------------------------------------------------------
# Classification contract
# ---------------------------------------------------------------------------


def test_feature_classification_contract() -> None:
    """Every classified input is exactly A, B or C; B entries never stored."""
    assert features.FEATURE_CLASSIFICATION, "classification table must not be empty"
    for name, category in features.FEATURE_CLASSIFICATION.items():
        assert category in ("A", "B", "C"), (name, category)
    # Every scenario-invariant semantic field the snapshot serves is
    # classified A (memoizable); B entries are never served.
    semantic_fields = {
        "session_context", "news_context", "bias_snapshot", "bias_resolution",
        "dxy_context", "frames_sufficient", "gate_payload", "gate_event_id",
        "gate_sources", "config_fingerprint",
    }
    memoized = {
        name for name, category in features.FEATURE_CLASSIFICATION.items()
        if category == "A"
    }
    assert semantic_fields <= memoized
    # Cell-local state must never be memoized.
    for name in (
        "setup_lifecycle_consumption", "pending_intent", "open_position",
        "risk_circuit_state", "account_equity_state", "pnl_costs",
    ):
        assert features.FEATURE_CLASSIFICATION.get(name) == "B", name


def test_snapshot_holds_no_cell_local_state() -> None:
    """The snapshot dataclass exposes scenario-invariant facts only."""
    stored_fields = {f.name for f in features.CausalMarketFeatureSnapshot.__dataclass_fields__.values()}
    prohibited = {
        "intent", "fill", "position", "risk", "circuit", "pnl", "balance",
        "equity", "consumption", "action", "candidate",
        "entry_eligible", "trade", "order", "cost", "commission", "swap_",
    }
    for field in stored_fields:
        for word in prohibited:
            assert not field.startswith(word), (field, word)


# ---------------------------------------------------------------------------
# Store contract
# ---------------------------------------------------------------------------


def test_feature_store_publish_readback_and_nonoverwrite() -> None:
    with tempfile.TemporaryDirectory(prefix="phase8n-k-pub-") as tmp:
        root = Path(tmp)
        bindings = _trading_fixture(root / "data")
        index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
        warmup = int(pd.Timestamp(bindings.plan["folds"][0]["warmup"]["start"]).value // 1_000_000)
        end = int(pd.Timestamp(bindings.plan["folds"][0]["evaluation"]["end"]).value // 1_000_000)
        cf = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
        cons = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
        path, sha = _build_store(bindings, index, cf, cons, root / "evidence")
        assert (path / "feature-store.complete.json").is_file()
        loaded = features.load_feature_store(path)
        assert features.canonical_hash(loaded.identity) == sha
        assert len(loaded) == len(index.decisions)
        with pytest.raises(RuntimeError):
            records = features.build_feature_records(
                bindings, index, candle_frames=cf, constituent_frames=cons,
            )
            features.publish_feature_store(
                records, evidence_root=root / "evidence", bindings=bindings, index=index,
            )


def test_feature_store_determinism() -> None:
    """Two builds of the same fold produce the same store identity hash."""
    with tempfile.TemporaryDirectory(prefix="phase8n-k-det-") as tmp:
        root = Path(tmp)
        bindings = _trading_fixture(root / "data")
        index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
        warmup = int(pd.Timestamp(bindings.plan["folds"][0]["warmup"]["start"]).value // 1_000_000)
        end = int(pd.Timestamp(bindings.plan["folds"][0]["evaluation"]["end"]).value // 1_000_000)
        cf = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
        cons = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
        _p1, sha1 = _build_store(bindings, index, cf, cons, root / "ev1")
        _p2, sha2 = _build_store(bindings, index, cf, cons, root / "ev2")
        assert sha1 == sha2


def test_feature_store_tampering_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="phase8n-k-tam-") as tmp:
        root = Path(tmp)
        bindings = _trading_fixture(root / "data")
        index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
        warmup = int(pd.Timestamp(bindings.plan["folds"][0]["warmup"]["start"]).value // 1_000_000)
        end = int(pd.Timestamp(bindings.plan["folds"][0]["evaluation"]["end"]).value // 1_000_000)
        cf = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
        cons = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
        path, _sha = _build_store(bindings, index, cf, cons, root / "evidence")
        # Flip a byte inside the parquet payload.
        features_file = path / "features.parquet"
        raw = bytearray(features_file.read_bytes())
        raw[-64] ^= 0xFF
        features_file.write_bytes(bytes(raw))
        with pytest.raises(RuntimeError):
            features.load_feature_store(path, verify_rows=True)


def test_feature_store_missing_decision_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="phase8n-k-mis-") as tmp:
        root = Path(tmp)
        bindings = _trading_fixture(root / "data")
        index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
        warmup = int(pd.Timestamp(bindings.plan["folds"][0]["warmup"]["start"]).value // 1_000_000)
        end = int(pd.Timestamp(bindings.plan["folds"][0]["evaluation"]["end"]).value // 1_000_000)
        cf = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
        cons = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
        path, _sha = _build_store(bindings, index, cf, cons, root / "evidence")
        store = features.load_feature_store(path)
        with pytest.raises(KeyError):
            store.row(1, "not-a-real-identity")


# ---------------------------------------------------------------------------
# 3-way equivalence: reference / indexed / feature-snapshot
# ---------------------------------------------------------------------------


def test_three_way_equivalence_with_trades() -> None:
    """Reference == indexed == feature-snapshot, skipping idle ticks only."""
    with tempfile.TemporaryDirectory(prefix="phase8n-k-eq-") as tmp:
        root = Path(tmp)
        bindings = _trading_fixture(root / "data")
        cell = _fixture_cell()
        index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)

        reference = _run_reference(bindings, cell, root / "ref")
        indexed = _run_optimized_with_index(index, bindings, cell, root / "idx")
        warmup = int(pd.Timestamp(bindings.plan["folds"][0]["warmup"]["start"]).value // 1_000_000)
        end = int(pd.Timestamp(bindings.plan["folds"][0]["evaluation"]["end"]).value // 1_000_000)
        cf = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
        cons = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
        store_path, _sha = _build_store(bindings, index, cf, cons, root / "evidence")
        snap = _run_snapshot(bindings, index, store_path, cell, root / "snap")

        from test_replay_input_index import _assert_equivalent

        _assert_equivalent(reference, indexed)
        _assert_equivalent(reference, snap)
        assert snap["decisions"] == indexed["decisions"]
        assert snap["balance"] == indexed["balance"]
        assert snap["fills"] == indexed["fills"]


def test_snapshot_batch_size_independence() -> None:
    with tempfile.TemporaryDirectory(prefix="phase8n-k-bat-") as tmp:
        root = Path(tmp)
        bindings = _trading_fixture(root / "data")
        cell = _fixture_cell()
        index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
        warmup = int(pd.Timestamp(bindings.plan["folds"][0]["warmup"]["start"]).value // 1_000_000)
        end = int(pd.Timestamp(bindings.plan["folds"][0]["evaluation"]["end"]).value // 1_000_000)
        cf = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
        cons = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
        store_path, _sha = _build_store(bindings, index, cf, cons, root / "evidence")
        baseline = _run_snapshot(bindings, index, store_path, cell, root / "a")
        for batch in (1, 7, 1000):
            outcome = _run_snapshot(
                bindings, index, store_path, cell, root / f"b{batch}", batch_rows=batch,
            )
            assert outcome["outcome"]["driver_stats"]["decisions_processed"] == baseline["outcome"]["driver_stats"]["decisions_processed"]
            assert outcome["outcome"]["driver_stats"]["active_quotes_processed"] == baseline["outcome"]["driver_stats"]["active_quotes_processed"]
            assert outcome["fills"] == baseline["fills"]
            assert outcome["decisions"] == baseline["decisions"]
            assert outcome["balance"] == baseline["balance"]


def test_no_cell_state_leakage_across_cells() -> None:
    """Two cells sharing one store keep fully independent outcomes."""
    with tempfile.TemporaryDirectory(prefix="phase8n-k-iso-") as tmp:
        root = Path(tmp)
        bindings = _trading_fixture(root / "data")
        index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
        warmup = int(pd.Timestamp(bindings.plan["folds"][0]["warmup"]["start"]).value // 1_000_000)
        end = int(pd.Timestamp(bindings.plan["folds"][0]["evaluation"]["end"]).value // 1_000_000)
        cf = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
        cons = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
        store_path, _sha = _build_store(bindings, index, cf, cons, root / "evidence")
        cell_a = _fixture_cell()
        cell_b = dict(cell_a)
        cell_b["cell_id"] = "cell_fixturebbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        cell_b["resume_identity"] = "resume_fixturebbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        run_a = _run_snapshot(bindings, index, store_path, cell_a, root / "cellA")
        run_b = _run_snapshot(bindings, index, store_path, cell_b, root / "cellB")
        run_a2 = _run_snapshot(bindings, index, store_path, cell_a, root / "cellA2")
        # Same store, same inputs => identical outcomes; a rerun reproduces A.
        assert run_a["outcome"]["final_balance"] == run_a2["outcome"]["final_balance"]
        assert run_b["outcome"]["decisions"] == run_a["outcome"]["decisions"]
        # No durable state crossed cells: every cell replays the same inputs
        # to identical outcomes from the one shared immutable store.  Fill
        # identity fields embed the cell id by design; semantic content must
        # be identical across cells and identical across reruns.
        def _semantic(fill: dict) -> dict:
            return {k: v for k, v in fill.items() if k not in (
                "fill_id", "action_id", "trade_id", "position_id",
            )}
        assert run_a["fills"] == run_a2["fills"]
        assert [_semantic(f) for f in run_a["fills"]] == [_semantic(f) for f in run_b["fills"]]
        assert run_a["consumed"] == run_b["consumed"] == run_a2["consumed"]
        assert run_a["lifecycle"] == run_b["lifecycle"] == run_a2["lifecycle"]
        assert run_a["balance"] == run_b["balance"] == run_a2["balance"]


def test_feature_store_cold_warm_serve_equivalence() -> None:
    """Serving the same decision twice returns equal immutable snapshots."""
    with tempfile.TemporaryDirectory(prefix="phase8n-k-cache-") as tmp:
        root = Path(tmp)
        bindings = _trading_fixture(root / "data")
        index = replay.build_replay_input_index(bindings, fold=bindings.plan["folds"][0], relaxed_identity=True)
        warmup = int(pd.Timestamp(bindings.plan["folds"][0]["warmup"]["start"]).value // 1_000_000)
        end = int(pd.Timestamp(bindings.plan["folds"][0]["evaluation"]["end"]).value // 1_000_000)
        cf = pipeline.materialize_candle_frames(bindings, start_ms=warmup, end_ms=end)
        cons = pipeline.materialize_constituent_frames(bindings, start_ms=warmup, end_ms=end)
        path, _sha = _build_store(bindings, index, cf, cons, root / "evidence")
        store = features.load_feature_store(path)
        provider = features.FoldFeatureProvider(store, index=index)
        if not len(index.decisions):
            pytest.skip("fixture produced no decisions")
        available_ms, open_ms, timeframe, close, identity = index.decisions[0]
        first = provider.features_for(available_ms, identity)
        second = provider.features_for(available_ms, identity)
        assert first.gate_payload == second.gate_payload
        assert first.bias_snapshot == second.bias_snapshot
        assert first.dxy_context == second.dxy_context
        assert first.news_context == second.news_context


def test_holdout_timestamps_never_reach_feature_store() -> None:
    """A plan whose evaluation crosses 2025 can never index or memoize."""
    assert replay.DEVELOPMENT_END_MS == pipeline.DEVELOPMENT_END_MS
    bindings_plan = {
        "plan_fingerprint": "holdout",
        "folds": [{
            "fold_id": "holdout-fold",
            "warmup": {"start": "2024-12-01T00:00:00Z", "end": "2025-01-01T00:00:00Z"},
            "evaluation": {"start": "2025-01-01T00:00:00Z", "end": "2025-02-01T00:00:00Z"},
        }],
        "scenario_matrix": {"scenarios": []},
    }
    with tempfile.TemporaryDirectory(prefix="phase8n-k-hold-") as tmp:
        root = Path(tmp)
        bindings = _trading_fixture(root / "data")
        object.__setattr__(bindings, "plan", bindings_plan)
        with pytest.raises(replay.EmpiricalPipelineError):
            replay.build_replay_input_index(
                bindings, fold=bindings_plan["folds"][0], relaxed_identity=True,
            )


def test_no_mt5_or_network_imports_in_feature_store_module() -> None:
    """The feature-store layer must not reference MT5, network or keyring."""
    text = (REPO_ROOT / "bot" / "validation" / "market_feature_store.py").read_text(encoding="utf-8")
    for prohibited in ("MetaTrader5", "import mt5", "requests", "urllib", "keyring", "socket"):
        assert prohibited not in text, prohibited
