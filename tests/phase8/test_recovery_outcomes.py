"""Synthetic aggregate recovery outcomes, distinct from state mutation."""

from dataclasses import asdict, replace
from datetime import datetime
import json

import pytest

from bot.backtesting.models import SimulatedFill, Side, FidelityClass
from bot.execution.broker.models import ExecutionAction, ExecutionReason, ExecutionStatus
from bot.strategy.setup_consumption import (
    RECOVERY_OUTCOME_SCHEMA, canonical, reconcile_setup_consumption, setup_reuse_reason,
)
from bot.strategy.setup_recovery import SetupRecoveryCoordinator
from bot.strategy.setup_state import SetupStateRecord
from bot.strategy.setup_store import SetupReplayStore
from tests.phase8.test_setup_consumption import _fixture, _confirm


def test_rejected_entry_cleanup_is_not_consumption(monkeypatch, tmp_path):
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    before = store.load()
    _confirm(registry, binding, volume=0, state=ExecutionStatus.REJECTED)
    result = recovery.reconcile()
    assert result.state_record != before
    assert not result.state_record.data()["consumption"]["events"]
    assert not result.state_record.data()["consumption"]["blocked"]
    assert result.outcome == "UNRELATED_FILL_IGNORED"
    assert result.state_changed and result.binding_released
    assert not result.consumption_applied and not result.consumption_already_present
    assert not result.reconciliation_required


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("reason", ["rejected", "cancelled", "expired"])
def test_terminal_unfilled_recovery_survives_serialization_and_restart(monkeypatch, tmp_path, side, reason):
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path, side=side)
    # The existing outbox maps these terminal reasons to ENTRY/REJECTED,
    # never to a fabricated fill or a new execution status.
    from bot.backtesting.fill_journal import HistoricalFillJournal
    journal = HistoricalFillJournal(tmp_path / "synthetic-outbox")
    journal.publish_rejection(binding, {"action_id": binding.action_id,
        "reason_code": reason, "timestamp": binding.entry_event_at})
    evidence = replace(_confirm(registry, binding, volume=0, state=ExecutionStatus.REJECTED), reason=ExecutionReason.BROKER_REJECTED)
    assert reconcile_setup_consumption(store.load(), {binding.action_id: evidence}) == reconcile_setup_consumption(store.load(), journal.snapshot())
    recovery = SetupRecoveryCoordinator(store, journal.snapshot)
    first = recovery.reconcile()
    payload = json.loads(canonical(first.to_dict()))
    assert payload["schema"] == RECOVERY_OUTCOME_SCHEMA
    assert payload["outcome"] == "UNRELATED_FILL_IGNORED"
    assert payload["binding_released"] and not payload["consumption_applied"]
    assert SetupStateRecord(canonical(payload["state_record"])) == store.load()
    assert setup_reuse_reason(store.load(), binding.setup_id, binding.evidence_id) is None
    restarted = SetupRecoveryCoordinator(SetupReplayStore(store.path, identity=store.identity), recovery.evidence)
    repeated = restarted.reconcile()
    assert repeated.outcome == "UNRELATED_FILL_IGNORED"
    assert not repeated.state_changed and not repeated.binding_released
    assert not repeated.consumption_applied and not repeated.consumption_already_present
    assert not repeated.state_record.data()["consumption"]["events"]


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("volume", [.01, .02])
def test_positive_recovery_and_duplicate_flags_match_live_offline(monkeypatch, tmp_path, side, volume):
    _, _, binding, store, registry, _ = _fixture(monkeypatch, tmp_path, side=side)
    live = _confirm(registry, binding, volume=volume, state=ExecutionStatus.PARTIALLY_FILLED if volume == .01 else ExecutionStatus.CONFIRMED)
    offline = SimulatedFill("2", binding.action_id, binding.trade_id, "synthetic-position",
        datetime.fromisoformat(binding.entry_event_at), binding.symbol, Side(side.upper()),
        volume, 100, 100, 100, 0, 0, volume == .01,
        "PARTIAL_ENTRY_FILL" if volume == .01 else "ENTRY_FILL", FidelityClass.TICK_BID_ASK)
    initial = store.load()
    first = reconcile_setup_consumption(initial, {binding.action_id: live})
    assert first == reconcile_setup_consumption(initial, {binding.action_id: offline})
    assert first.outcome == "CONSUMED" and first.consumption_applied
    assert not first.consumption_already_present and not first.reconciliation_required
    repeated = reconcile_setup_consumption(first.state_record, {binding.action_id: live})
    assert repeated == reconcile_setup_consumption(first.state_record, {binding.action_id: offline})
    assert repeated.outcome == "DUPLICATE_IGNORED"
    assert repeated.consumption_already_present and not repeated.consumption_applied
    assert not repeated.state_changed
    assert len(repeated.state_record.data()["consumption"]["events"]) == 1


@pytest.mark.parametrize("case", ["zero", "uncertain", "mismatch", "manual", "close", "partial_close"])
def test_nonentry_or_unsafe_recovery_never_consumes(monkeypatch, tmp_path, case):
    _, _, binding, store, registry, _ = _fixture(monkeypatch, tmp_path)
    evidence = _confirm(registry, binding)
    if case == "zero":
        evidence = replace(evidence, executed_volume=0)
    elif case == "uncertain":
        evidence = replace(evidence, state=ExecutionStatus.UNCERTAIN)
    elif case == "mismatch":
        evidence = replace(evidence, trade_id="foreign")
    elif case == "manual":
        evidence = {"symbol": binding.symbol, "magic": 0}
    else:
        evidence = replace(evidence, action_type=ExecutionAction.FULL_CLOSE if case == "close" else ExecutionAction.PARTIAL_CLOSE)
    result = reconcile_setup_consumption(store.load(), {binding.action_id: evidence})
    assert result.outcome == ("IDENTITY_MISMATCH_BLOCKED" if case == "mismatch" else "UNCERTAIN_BLOCKED")
    assert result.reconciliation_required
    assert not result.consumption_applied and not result.consumption_already_present
    assert not result.state_record.data()["consumption"]["events"]


def test_cleanup_persisted_before_ack_crash_stays_unconsumed(monkeypatch, tmp_path):
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding, volume=0, state=ExecutionStatus.REJECTED)
    write = store._atomic_write
    def crash(path, content):
        if path == store.backup:
            raise OSError("synthetic cleanup persisted before acknowledgement")
        return write(path, content)
    with monkeypatch.context() as patch:
        patch.setattr(store, "_atomic_write", crash)
        with pytest.raises(OSError):
            recovery.reconcile()
    assert not store.load().data()["consumption"]["events"]
    result = recovery.reconcile()
    assert result.outcome == "UNRELATED_FILL_IGNORED"
    assert not result.state_changed and not result.consumption_applied


def test_corrupted_recovery_fails_closed(monkeypatch, tmp_path):
    _, _, _, store, _, _ = _fixture(monkeypatch, tmp_path)
    result = reconcile_setup_consumption(replace(store.load(), payload="null"), {})
    assert result.outcome == "STATE_CORRUPT" and result.reconciliation_required
    assert not result.consumption_applied and not result.state_changed


@pytest.mark.parametrize("second_kind", ["rejected", "confirmed", "uncertain", "mismatch"])
def test_mixed_binding_summary_preserves_independent_dimensions(monkeypatch, tmp_path, second_kind):
    _, _, first, store, registry, _ = _fixture(monkeypatch, tmp_path)
    payload = json.loads(first.decision_payload)
    payload.update(setup_id="z-second-setup", evidence="second-source-evidence")
    second = replace(first, setup_id=payload["setup_id"], evidence_id=payload["evidence"],
                     decision_payload=canonical(payload), action_id="second-entry", trade_id="second-trade")
    data = store.load().data()
    data["consumption"]["bindings"][second.setup_id] = json.loads(canonical(asdict(second)))
    data["consumption"]["blocked"][second.setup_id] = "entry_pending_confirmation"
    initial = SetupStateRecord(canonical(data))
    first_evidence = _confirm(registry, first)
    second_evidence = replace(first_evidence, action_id=second.action_id, trade_id=second.trade_id)
    if second_kind == "rejected":
        second_evidence = replace(second_evidence, state=ExecutionStatus.REJECTED, executed_volume=0)
    elif second_kind == "uncertain":
        second_evidence = replace(second_evidence, state=ExecutionStatus.UNCERTAIN)
    elif second_kind == "mismatch":
        second_evidence = replace(second_evidence, trade_id="foreign")
    result = reconcile_setup_consumption(initial, {first.action_id: first_evidence, second.action_id: second_evidence})
    assert result.consumption_applied and result.state_changed
    assert result.binding_released == (second_kind == "rejected")
    assert result.reconciliation_required == (second_kind in ("uncertain", "mismatch"))
    assert result.outcome == {"rejected": "CONSUMED", "confirmed": "CONSUMED",
        "uncertain": "UNCERTAIN_BLOCKED", "mismatch": "IDENTITY_MISMATCH_BLOCKED"}[second_kind]
    assert len(result.state_record.data()["consumption"]["events"]) == (2 if second_kind == "confirmed" else 1)
