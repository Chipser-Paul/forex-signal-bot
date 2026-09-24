"""MR003 — V001 snapshot classification before orchestration (post-exposure).

Third post-exposure tooling defect: ``run_v001_evaluation`` iterated every
persisted store snapshot directly into ``observe_decision`` while the frozen
D001 measurement contract first classifies non-evaluable snapshots
(``classify_snapshot`` + ``_reference_check_failed``) and never sends them to
the orchestrator. A canonical ``dxy_blocked`` row (empty ``gate_event_id``)
reached orchestration, produced a reducer decision whose persisted
``last_event_id`` mismatched the snapshot id, and the adapter's fail-closed
state-continuity invariant raised ``D001Error`` deterministically before any
observation.

Repair principle (task §6/§7): reuse the D001 implementations verbatim
(``classify_snapshot`` / ``_reference_check_failed`` /
``reconcile_accounting``); do NOT reimplement gate-status interpretation.

Synthetic fixtures only — the empirical store is never opened. No empirical
Fold-01 counts are used anywhere in this suite (§13).
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
    _seed_record,
)

FOLD01_END_MS = int(datetime(2024, 6, 8, tzinfo=timezone.utc).timestamp() * 1000)


class _BucketSnapshot:
    """Canonical D001 snapshot stub with configurable gate status."""

    def __init__(self, status, *, check_passes=True, payload="{}", at=None,
                 event_id="stub-ok-event"):
        self.gate_status = status
        self.check_passes = check_passes
        self.gate_payload = payload if status == "ok" else None
        self.gate_event_id = None if status != "ok" else event_id
        self.available_at_ms = int(
            (at or datetime(2024, 4, 2, tzinfo=timezone.utc)).timestamp() * 1000
        )


class _Record:
    """Sentinel setup-state record stub (identity, not content, matters here;
    real content carry is proven by the MR002 suite against the canonical
    setup-state implementation)."""

    def __init__(self, tag):
        self.tag = tag

    def data(self):
        return {"tag": self.tag}


def _canned_aggregate(structural_rows):
    """Minimal aggregate shape (established MR001-fixture pattern): the loop
    under test only reads decisions_total plus the outcome-classification
    keys; real reduction is covered by the frozen-tooling suite."""
    return {
        "decisions_total": len(structural_rows),
        "candidate_ready": 0,
        "detector_eligible_decisions": 0,
        "attrition_stage_totals": {"atr_valid_windows": 0},
        "final_fvg": {"decisions_with_final_fvg": 0},
    }


def _identity():
    return {
        "fold_id": "fold-01",
        "coverage": "full",
        "decision_timeframe": "M5",
        "evaluation_start_ms": FOLD01_START_MS,
        "evaluation_end_ms": FOLD01_END_MS,
    }


def _store_stub():
    class _Store:
        pass

    store = _Store()
    store.identity = _identity()
    return store


# ---------------------------------------------------------------------------
# §14 A–D — pre-evaluation buckets never reach the observer; state untouched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,bucket",
    [
        ("early_exit", "missing_history"),
        ("dxy_blocked", "unavailable_input"),
        ("insufficient_data", "unavailable_input"),
        ("causal_input_unsafe", "evaluation_error"),
    ],
)
def test_bucket_rows_classified_and_skipped(monkeypatch, status, bucket):
    """§14 A–D: classified rows are accounted, never observed, state kept."""
    assert d001.classify_snapshot(_BucketSnapshot(status)) == (bucket, status)

    calls = []

    def _must_not_be_called(*_args, **_kwargs):
        calls.append(1)
        raise AssertionError("observer invoked for a classified snapshot")

    monkeypatch.setattr(v001, "observe_decision", _must_not_be_called)
    monkeypatch.setattr(v001, "_snapshot_rows", lambda _store: [_BucketSnapshot(status)])

    with pytest.raises(v001.V001EvalError, match="zero decisions"):
        v001.run_v001_evaluation(
            _store_stub(),
            canonical_commit="d" * 40,
            tooling_commit="d" * 40,
            raw_source_identities={"source_identities": {}},
            rebuilt_store_identity={"store_sha256": "a" * 64, "store_name": "synthetic"},
        )
    assert calls == [], "observer must never be called for classified rows"


# ---------------------------------------------------------------------------
# §14 F/G — unknown status and payload-less ok rows fail closed
# ---------------------------------------------------------------------------


def test_unknown_gate_status_fails_closed():
    with pytest.raises(d001.D001Error, match="unknown canonical gate status"):
        d001.classify_snapshot(_BucketSnapshot("mystery_status"))
    monkey_calls = []

    def _must_not_be_called(*_args, **_kwargs):
        monkey_calls.append(1)
        raise AssertionError("observer invoked after classifier failure")

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(v001, "observe_decision", _must_not_be_called)
        monkey.setattr(
            v001, "_snapshot_rows", lambda _store: [_BucketSnapshot("mystery_status")]
        )
        with pytest.raises(d001.D001Error):
            v001.run_v001_evaluation(
                _store_stub(),
                canonical_commit="d" * 40,
                tooling_commit="d" * 40,
                raw_source_identities={"source_identities": {}},
                rebuilt_store_identity={"store_sha256": "a" * 64, "store_name": "s"},
            )
    finally:
        monkey.undo()
    assert monkey_calls == []


def test_ok_without_gate_payload_fails_closed():
    with pytest.raises(d001.D001Error, match="without a persisted gate payload"):
        d001.classify_snapshot(_BucketSnapshot("ok", payload=None))


# ---------------------------------------------------------------------------
# §14 E — ok rows reach the observer; success advances state
# ---------------------------------------------------------------------------


def test_ok_rows_reach_observer_and_advance_state(monkeypatch):
    ok1 = _BucketSnapshot("ok", at=AT, event_id="evt-1")
    ok2 = _BucketSnapshot("ok", at=AT + timedelta(minutes=5), event_id="evt-2")
    assert d001.classify_snapshot(ok1) is None
    assert d001._reference_check_failed(ok1) is False

    seed = _seed_record()
    n1 = _Record("after-evt-1")
    n2 = _Record("after-evt-2")
    received = []

    def _observe(snapshot, record):
        received.append(record)
        nxt = n1 if snapshot.gate_event_id == "evt-1" else n2
        return {
            "decision_id": snapshot.gate_event_id,
            "available_at_ms": snapshot.available_at_ms,
            "action": "wait",
            "reason": "entry_not_ready",
            "state_name": "monitoring",
        }, nxt

    captured = {}
    structural_rows = []

    def _aggregate_spy(rows):
        structural_rows.extend(rows)
        return _canned_aggregate(structural_rows)

    def _capture(**kw):
        captured.update(kw)

    monkeypatch.setattr(v001, "observe_decision", _observe)
    monkeypatch.setattr(v001, "_snapshot_rows", lambda _store: [ok1, ok2])
    monkeypatch.setattr(v001, "reconcile_accounting", _capture)
    monkeypatch.setattr(v001, "aggregate_v001", _aggregate_spy)

    material, _rendered = v001.run_v001_evaluation(
        _store_stub(),
        canonical_commit="d" * 40,
        tooling_commit="d" * 40,
        raw_source_identities={"source_identities": {}},
        rebuilt_store_identity={"store_sha256": "a" * 64, "store_name": "s"},
    )
    # Both ok rows were evaluated; the first received the canonical seed and
    # the second received the first row's next record (no reset).
    assert [row["decision_id"] for row in structural_rows] == ["evt-1", "evt-2"]
    assert material["metrics"]["decisions_total"] == 2
    assert received == [seed, n1]
    assert captured == {
        "scheduled": 2,
        "classified": 2,
        "missing_history": 0,
        "unavailable_input": 0,
        "evaluation_error": 0,
    }


# ---------------------------------------------------------------------------
# §15 — reference-check failure is accounted, never observed, state kept
# ---------------------------------------------------------------------------


def test_reference_check_failure_skips_orchestration(monkeypatch):
    bad = _BucketSnapshot("ok", check_passes=False)
    assert d001.classify_snapshot(bad) is None
    assert d001._reference_check_failed(bad) is True

    calls = []

    def _must_not_be_called(*_args, **_kwargs):
        calls.append(1)
        raise AssertionError("observer invoked despite failed reference check")

    captured = {}

    def _capture(**kw):
        captured.update(kw)

    monkeypatch.setattr(v001, "observe_decision", _must_not_be_called)
    monkeypatch.setattr(v001, "_snapshot_rows", lambda _store: [bad])
    monkeypatch.setattr(v001, "reconcile_accounting", _capture)
    with pytest.raises(v001.V001EvalError, match="zero decisions"):
        v001.run_v001_evaluation(
            _store_stub(),
            canonical_commit="d" * 40,
            tooling_commit="d" * 40,
            raw_source_identities={"source_identities": {}},
            rebuilt_store_identity={"store_sha256": "a" * 64, "store_name": "s"},
        )
    assert calls == []
    assert captured == {
        "scheduled": 1,
        "classified": 0,
        "missing_history": 0,
        "unavailable_input": 0,
        "evaluation_error": 1,
    }


# ---------------------------------------------------------------------------
# §16 — generic mixed sequence: eligibility, carry, rows, accounting
# ---------------------------------------------------------------------------


def test_mixed_sequence_generic_contract(monkeypatch):
    seed = _seed_record()
    n1 = _Record("after-first-success")
    n3 = _Record("after-third-success")
    seq = [
        _BucketSnapshot("early_exit", at=AT, event_id="e-bucket"),
        _BucketSnapshot("ok", at=AT + timedelta(minutes=5), event_id="e-ok1"),
        _BucketSnapshot("dxy_blocked", at=AT + timedelta(minutes=10)),
        _BucketSnapshot("ok", at=AT + timedelta(minutes=15), event_id="e-err",
                        check_passes=False),
        _BucketSnapshot("ok", at=AT + timedelta(minutes=20), event_id="e-err2"),
        _BucketSnapshot("ok", at=AT + timedelta(minutes=25), event_id="e-ok3"),
    ]
    ok1, ok_err2, ok_err3, ok3 = seq[1], seq[3], seq[4], seq[5]

    received = []

    def _observe(snapshot, record):
        received.append((snapshot.gate_event_id, record))
        if snapshot.gate_event_id == ok_err3.gate_event_id:
            return {
                "decision_id": snapshot.gate_event_id,
                "available_at_ms": snapshot.available_at_ms,
                "action": "error",
                "reason": "orchestrator_input_unsafe",
                "state_name": "unknown",
                "error_type": "ValueError",
            }, record
        nxt = n1 if snapshot.gate_event_id == ok1.gate_event_id else n3
        return {
            "decision_id": snapshot.gate_event_id,
            "available_at_ms": snapshot.available_at_ms,
            "action": "wait",
            "reason": "entry_not_ready",
            "state_name": "monitoring",
        }, nxt

    captured = {}
    structural_rows = []

    def _aggregate_spy(rows):
        structural_rows.extend(rows)
        return _canned_aggregate(structural_rows)

    def _capture(**kw):
        captured.update(kw)

    monkeypatch.setattr(v001, "observe_decision", _observe)
    monkeypatch.setattr(v001, "_snapshot_rows", lambda _store: seq)
    monkeypatch.setattr(v001, "reconcile_accounting", _capture)
    monkeypatch.setattr(v001, "aggregate_v001", _aggregate_spy)

    material, _rendered = v001.run_v001_evaluation(
        _store_stub(),
        canonical_commit="d" * 40,
        tooling_commit="d" * 40,
        raw_source_identities={"source_identities": {}},
        rebuilt_store_identity={"store_sha256": "a" * 64, "store_name": "s"},
    )
    # Only genuinely evaluable ok rows reached the observer — bucket rows and
    # the reference-check failure never did.
    assert [event for event, _record in received] == [
        ok1.gate_event_id, ok_err3.gate_event_id, ok3.gate_event_id,
    ]
    # State advanced only on success: ok1 got the seed, the reference-failed
    # row was skipped entirely, the error row received (and kept) the carried
    # n1 record, and ok3 received that same last-valid record.
    assert received == [
        (ok1.gate_event_id, seed),
        (ok_err3.gate_event_id, n1),
        (ok3.gate_event_id, n1),
    ]
    # Structural rows contain successful decisions only.
    assert [row["decision_id"] for row in structural_rows] == [
        ok1.gate_event_id, ok3.gate_event_id,
    ]
    assert material["metrics"]["decisions_total"] == 2
    assert captured == {
        "scheduled": 6,
        "classified": 2,
        "missing_history": 1,
        "unavailable_input": 1,
        "evaluation_error": 2,
    }


# ---------------------------------------------------------------------------
# §17 — D001 parity on the identical synthetic sequence
# ---------------------------------------------------------------------------


def test_d001_parity_on_identical_sequence(monkeypatch):
    """§17: the repaired V001 loop reproduces D001's control contract exactly.

    Strongest form first: the loop's decision points ARE the canonical
    functions (import identity, not reimplementation).  Then behavioral
    parity: the same synthetic sequence driven through the frozen D001
    control contract and through the repaired V001 loop produces identical
    bucket classifications, evaluation-error handling, state advancement
    and structural-row inclusion.
    """
    # Import identity — no gate-status interpretation exists outside D001.
    assert v001.classify_snapshot is d001.classify_snapshot
    assert v001._reference_check_failed is d001._reference_check_failed
    assert v001.reconcile_accounting is d001.reconcile_accounting

    seed = _seed_record()
    n1 = _Record("parity-after-success-1")
    n3 = _Record("parity-after-success-3")
    seq = [
        _BucketSnapshot("early_exit", at=AT, event_id="p-bucket"),
        _BucketSnapshot("ok", at=AT + timedelta(minutes=5), event_id="p-ok1"),
        _BucketSnapshot("dxy_blocked", at=AT + timedelta(minutes=10)),
        _BucketSnapshot("ok", at=AT + timedelta(minutes=15), event_id="p-err",
                        check_passes=False),
        _BucketSnapshot("ok", at=AT + timedelta(minutes=20), event_id="p-err2"),
        _BucketSnapshot("ok", at=AT + timedelta(minutes=25), event_id="p-ok3"),
    ]
    ok1, ok_err2, ok_err3, ok3 = seq[1], seq[3], seq[4], seq[5]

    def _shared_observe(record_log):
        """One orchestrator/observer behavior shared by both drivers."""
        def _observe(snapshot, record):
            record_log.append((snapshot.gate_event_id, record))
            if snapshot.gate_event_id == ok_err3.gate_event_id:
                return {
                    "decision_id": snapshot.gate_event_id,
                    "available_at_ms": snapshot.available_at_ms,
                    "action": "error",
                    "reason": "orchestrator_input_unsafe",
                    "state_name": "unknown",
                    "error_type": "ValueError",
                }, record
            nxt = n1 if snapshot.gate_event_id == ok1.gate_event_id else n3
            return {
                "decision_id": snapshot.gate_event_id,
                "available_at_ms": snapshot.available_at_ms,
                "action": "wait",
                "reason": "entry_not_ready",
                "state_name": "monitoring",
            }, nxt
        return _observe

    # --- driver 1: frozen D001 control contract ----------------------------
    d001_log = []
    d001_buckets = {"missing_history": 0, "unavailable_input": 0, "evaluation_error": 0}
    state = seed
    d001_structural = []
    for snapshot in seq:
        bucket = d001.classify_snapshot(snapshot)
        if bucket is not None:
            d001_buckets[bucket[0]] += 1
            continue
        if d001._reference_check_failed(snapshot):
            d001_buckets["evaluation_error"] += 1
            continue
        row, nxt = _shared_observe(d001_log)(snapshot, state)
        if row["action"] == "error":
            d001_buckets["evaluation_error"] += 1
            continue
        state = nxt
        d001_structural.append(row["decision_id"])

    # --- driver 2: repaired V001 loop --------------------------------------
    v001_log = []
    captured = {}
    structural_rows = []

    def _aggregate_spy(rows):
        structural_rows.extend(rows)
        return _canned_aggregate(structural_rows)

    def _capture(**kw):
        captured.update(kw)

    monkeypatch.setattr(v001, "observe_decision", _shared_observe(v001_log))
    monkeypatch.setattr(v001, "_snapshot_rows", lambda _store: seq)
    monkeypatch.setattr(v001, "reconcile_accounting", _capture)
    monkeypatch.setattr(v001, "aggregate_v001", _aggregate_spy)
    material, _rendered = v001.run_v001_evaluation(
        _store_stub(),
        canonical_commit="d" * 40,
        tooling_commit="d" * 40,
        raw_source_identities={"source_identities": {}},
        rebuilt_store_identity={"store_sha256": "a" * 64, "store_name": "s"},
    )
    v001_structural = [row["decision_id"] for row in structural_rows]

    # Identical classifications, error handling, structural inclusion and
    # state advancement on the identical sequence.
    assert captured == {
        "scheduled": 6,
        "classified": 2,
        "missing_history": 1,
        "unavailable_input": 1,
        "evaluation_error": 2,
    }
    assert sum(captured[k] for k in ("classified", "missing_history",
                                     "unavailable_input", "evaluation_error")) == captured["scheduled"]
    assert d001_buckets == {
        "missing_history": captured["missing_history"],
        "unavailable_input": captured["unavailable_input"],
        "evaluation_error": captured["evaluation_error"],
    }
    assert d001_log == v001_log == [
        (ok1.gate_event_id, seed),
        (ok_err3.gate_event_id, n1),
        (ok3.gate_event_id, n1),
    ]
    assert d001_structural == v001_structural
    assert material["metrics"]["decisions_total"] == 2
