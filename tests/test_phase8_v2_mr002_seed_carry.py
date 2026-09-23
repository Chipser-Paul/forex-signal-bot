"""MR002 — V001 measurement decision-loop setup-state seed/carry regressions.

Second post-exposure tooling defect: the frozen V001 measurement loop
initialized its sequential setup-state chain with ``None`` while both
production (``empirical_input_pipeline``) and the successful frozen D001
diagnostic initialize a valid ``SetupStateRecord`` via
``record_from_state(StrategyState(event_time=2024-01-01Z), event_at=seed)``.
``None`` reached ``state_from_record(None)`` (``AttributeError``) and the
canonical adapter classified every ok-path row as ``action=error /
orchestrator_input_unsafe`` before any observation.

Repair principle (task §5): repair the caller; use the established seed;
match D001 carry semantics exactly. No strategy semantics, no measurement
surface, and no D001 adapter changes.

Synthetic fixtures only — no empirical store is opened.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtests import phase8_v2_variant_v001_eval as v001  # noqa: E402
from backtests import phase8_v2_diagnostic_d001 as d001  # noqa: E402
from tests.test_phase8_v2_d001_tooling import (  # noqa: E402
    AT,
    FOLD01_START_MS,
    _ok_snapshot,
    _mocked_ok_snapshot,
    _seed_record,
    _Table,
)

FOLD01_END_MS = int(datetime(2024, 6, 8, tzinfo=timezone.utc).timestamp() * 1000)


def _store_stub(rows, identity=None):
    class _Store:
        pass

    store = _Store()
    store.table = _Table(rows)
    store.identity = identity or {
        "fold_id": "fold-01",
        "coverage": "full",
        "decision_timeframe": "M5",
        "evaluation_start_ms": FOLD01_START_MS,
        "evaluation_end_ms": FOLD01_END_MS,
    }
    return store


# ---------------------------------------------------------------------------
# §11 — exact defect: None seed fails, canonical seed succeeds
# ---------------------------------------------------------------------------


def test_none_seed_fails_in_orchestrator_restoration():
    """Historical defect: prior_state=None reaches state_from_record(None).

    Proven at two layers: the production orchestrator raises directly, and
    the canonical adapter converts that into action=error rows.
    """
    import bot.validation.market_feature_store as mfs
    from datetime import datetime as _dt, timezone as _tz

    snapshot = _ok_snapshot()  # real build_gate_inputs fixture (no mocks)
    decision_at = _dt.fromtimestamp(snapshot.available_at_ms / 1000, tz=_tz.utc)
    with pytest.raises(AttributeError):
        mfs.evaluate_orchestration_from_features(
            snapshot, decision_at=decision_at, prior_state=None,
            active_trade_count=0, max_concurrent_trades=2,
        )
    row, record = d001.evaluate_orchestration_decision(snapshot, None)
    assert row["action"] == "error"
    assert row["reason"] == "orchestrator_input_unsafe"
    assert row["error_type"] == "AttributeError"
    assert record is None  # nothing valid existed to carry


def test_canonical_seed_reaches_normal_orchestration(monkeypatch):
    """MR002: the canonical seed lets the same snapshot evaluate normally."""
    snapshot = _mocked_ok_snapshot(monkeypatch)
    row, record = d001.evaluate_orchestration_decision(snapshot, _seed_record())
    assert row["action"] in {"wait", "skip", "candidate_ready"}
    assert row["reason"] != "orchestrator_input_unsafe"
    assert record.data()["last_event_id"] == snapshot.gate_event_id


def test_seed_state_record_matches_d001_contract():
    """The V001 seed must be the exact production/D001 pattern (§14)."""
    record = v001._seed_state_record()
    reference = _seed_record()
    assert record.data() == reference.data()
    seed = datetime(2024, 1, 1, tzinfo=timezone.utc)
    from bot.strategy.setup_state import record_from_state, StrategyState

    assert record.data() == record_from_state(
        StrategyState(event_time=seed), event_at=seed
    ).data()


# ---------------------------------------------------------------------------
# §12 — sequential carry: no reset between snapshots
# ---------------------------------------------------------------------------


def test_sequential_carry_content_across_snapshots():
    first = _ok_snapshot()
    second = _ok_snapshot(AT + timedelta(minutes=5))
    third = _ok_snapshot(AT + timedelta(minutes=10))

    row1, rec1 = v001.observe_decision(first, _seed_record())
    assert rec1.data()["last_event_id"] == first.gate_event_id

    row2, rec2 = v001.observe_decision(second, rec1)
    assert rec2.data()["last_event_id"] == second.gate_event_id
    # carried content, not merely call order
    assert rec2.data()["last_event_at"] >= rec1.data()["last_event_at"]

    row3, rec3 = v001.observe_decision(third, rec2)
    assert rec3.data()["last_event_id"] == third.gate_event_id


def test_run_loop_seed_exists_before_first_snapshot(monkeypatch):
    """§11/§12: the loop seeds before snapshot 1 and carries between rows.

    observe_decision is stubbed at loop level (established synthetic
    pattern); the loop's seed/carry/error logic is the unit under test.
    """
    from bot.strategy.setup_state import StrategyState, record_from_state

    snaps = [_ok_snapshot(), _ok_snapshot(AT + timedelta(minutes=5))]
    seen_records = []

    def stub_observe(snapshot, state_record, **kwargs):
        seen_records.append(state_record)
        next_record = record_from_state(
            StrategyState(event_time=datetime.fromtimestamp(
                snapshot.available_at_ms / 1000, tz=timezone.utc)),
            event_at=datetime.fromtimestamp(
                snapshot.available_at_ms / 1000, tz=timezone.utc),
            last_event_id=snapshot.gate_event_id,
            last_result="{}",
        )
        return {
            "decision_id": snapshot.gate_event_id,
            "available_at_ms": snapshot.available_at_ms,
            "action": "wait",
            "reason": "stub",
            "reconciliation_available": True,
        }, next_record

    monkeypatch.setattr(v001, "observe_decision", stub_observe)

    material, _rendered = v001.run_v001_evaluation(
        _store_stub(snaps),
        canonical_commit="d621aebcaae89b99d3727fb2fff02a3ada53b0ae",
        tooling_commit="a193702c4d26cbae7e5121950fa66574b860a69d",
        raw_source_identities={
            "plan_fingerprint": "a" * 64,
            "pipeline_fingerprint": "b" * 64,
            "source_identities": {"y": {"partition": "year=2024"}},
        },
        rebuilt_store_identity={"store_sha256": "c" * 64, "store_name": "fold-01-x"},
    )
    assert seen_records, "loop never observed a decision"
    assert seen_records[0] is not None, "first snapshot received None seed"
    seed = datetime(2024, 1, 1, tzinfo=timezone.utc)
    from bot.strategy.setup_state import record_from_state, StrategyState

    assert seen_records[0].data() == record_from_state(
        StrategyState(event_time=seed), event_at=seed
    ).data()
    assert seen_records[1].data()["last_event_id"] == snaps[0].gate_event_id
    assert material["metrics"]["decisions_total"] == 2


# ---------------------------------------------------------------------------
# §13 — error carry: error must not poison the chain
# ---------------------------------------------------------------------------


def test_error_carry_matches_d001():
    """success -> error -> success; the third snapshot gets the last
    successful state and the error does not poison the chain."""
    import bot.validation.market_feature_store as mfs

    real = mfs.evaluate_orchestration_from_features

    def boom(*args, **kwargs):
        raise ValueError("synthetic orchestrator failure")

    s1 = _ok_snapshot()
    row1, rec1 = v001.observe_decision(s1, _seed_record())
    assert row1["action"] != "error"

    mfs.evaluate_orchestration_from_features = boom
    try:
        s2 = _ok_snapshot(AT + timedelta(minutes=5))
        row2, next_from_error = v001.observe_decision(s2, rec1)
        assert row2["action"] == "error"
        assert row2["reason"] == "orchestrator_input_unsafe"
        assert next_from_error is rec1, "adapter must return prior record on error"
        # D001 reference behavior on the identical failure (same patched layer)
        d001_row2, d001_next = d001.evaluate_orchestration_decision(
            _ok_snapshot(AT + timedelta(minutes=5)), rec1
        )
    finally:
        mfs.evaluate_orchestration_from_features = real
    assert d001_row2["action"] == "error" and d001_next is rec1

    s3 = _ok_snapshot(AT + timedelta(minutes=10))
    row3, rec3 = v001.observe_decision(s3, rec1)
    assert rec3.data()["last_event_id"] == s3.gate_event_id


def test_run_loop_preserves_state_on_error_row(monkeypatch):
    """Loop-level: an error row must not replace the carried record."""
    from bot.strategy.setup_state import StrategyState, record_from_state

    s1 = _ok_snapshot()
    s2 = _ok_snapshot(AT + timedelta(minutes=5))
    s3 = _ok_snapshot(AT + timedelta(minutes=10))

    received = []

    def stub_observe(snapshot, state_record, **kwargs):
        received.append((snapshot.gate_event_id, state_record))
        if snapshot.available_at_ms == s2.available_at_ms:
            return {
                "decision_id": snapshot.gate_event_id,
                "available_at_ms": snapshot.available_at_ms,
                "action": "error",
                "reason": "orchestrator_input_unsafe",
                "error_type": "ValueError",
            }, state_record
        next_record = record_from_state(
            StrategyState(event_time=datetime.fromtimestamp(
                snapshot.available_at_ms / 1000, tz=timezone.utc)),
            event_at=datetime.fromtimestamp(
                snapshot.available_at_ms / 1000, tz=timezone.utc),
            last_event_id=snapshot.gate_event_id,
            last_result="{}",
        )
        return {
            "decision_id": snapshot.gate_event_id,
            "available_at_ms": snapshot.available_at_ms,
            "action": "wait",
            "reason": "stub",
            "reconciliation_available": True,
        }, next_record

    monkeypatch.setattr(v001, "observe_decision", stub_observe)

    material, _rendered = v001.run_v001_evaluation(
        _store_stub([s1, s2, s3]),
        canonical_commit="d621aebcaae89b99d3727fb2fff02a3ada53b0ae",
        tooling_commit="a193702c4d26cbae7e5121950fa66574b860a69d",
        raw_source_identities={
            "plan_fingerprint": "a" * 64,
            "pipeline_fingerprint": "b" * 64,
            "source_identities": {"y": {"partition": "year=2024"}},
        },
        rebuilt_store_identity={"store_sha256": "c" * 64, "store_name": "fold-01-x"},
    )
    # snapshot 3 received exactly the record produced by snapshot 1
    assert received[0][1].data() == _seed_record().data()  # seeded start
    assert received[2][1].data()["last_event_id"] == s1.gate_event_id
    assert material["metrics"]["decisions_total"] == 2  # error row excluded
    assert material["metrics"]["actions"].get("error") is None
    assert material["metrics"]["observer_reconciled_decisions"] == 2


# ---------------------------------------------------------------------------
# §10 — measurement surface invariance (aggregation unchanged)
# ---------------------------------------------------------------------------


def test_aggregation_reconciliation_invariant_unchanged():
    from tests.test_phase8_v2_v001_eval_tooling import _material_with

    error_row = {**_material_with(0)["metrics"], "action": "error",
                 "reason": "orchestrator_input_unsafe",
                 "reconciliation_available": False}
    with pytest.raises(v001.ReconciliationError):
        v001.aggregate_v001([error_row])
    ok_row = {**_material_with(0)["metrics"], "action": "skip",
              "reason": "synthetic",
              "reconciliation_available": True}
    assert v001.aggregate_v001([ok_row])["decisions_total"] == 1


def test_seed_helper_does_not_touch_strategy_or_d001_modules():
    import backtests.phase8_v2_diagnostic_d001 as d001_mod
    import bot.analysis.fvg_engine as fvg

    before_d001 = Path(d001_mod.__file__).read_bytes()
    before_fvg = Path(fvg.__file__).read_bytes()
    v001._seed_state_record()
    assert Path(d001_mod.__file__).read_bytes() == before_d001
    assert Path(fvg.__file__).read_bytes() == before_fvg
