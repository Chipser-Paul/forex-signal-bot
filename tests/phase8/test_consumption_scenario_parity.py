"""Sixteen normalized consumption scenarios for both authoritative adapters."""

from dataclasses import replace
from datetime import datetime

import pytest

from bot.backtesting.models import SimulatedFill, Side, FidelityClass
from bot.execution.broker.models import ExecutionStatus
from bot.strategy.setup_consumption import (
    apply_setup_consumption, classify_confirmed_entry_fill, reconcile_setup_consumption, setup_reuse_reason,
)
from tests.phase8.test_setup_consumption import _fixture, _confirm


SCENARIOS = (
    "full_long", "full_short", "partial_entry", "later_remainder", "rejected",
    "cancelled", "expired", "uncertain", "crash_before_consumption", "crash_before_ack",
    "duplicate_fill", "matching_restart", "missing_fill", "foreign", "identity_mismatch", "source_reuse",
)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_all_consumption_scenarios_have_matching_normalized_live_offline_state(monkeypatch, tmp_path, scenario):
    _, _, binding, store, registry, _ = _fixture(monkeypatch, tmp_path, side="sell" if scenario == "full_short" else "buy")
    volume = .01 if scenario in ("partial_entry", "later_remainder") else .02
    live_evidence = _confirm(registry, binding, volume=volume,
        state=ExecutionStatus.PARTIALLY_FILLED if volume == .01 else ExecutionStatus.CONFIRMED)
    offline_evidence = SimulatedFill("2", binding.action_id, binding.trade_id, "synthetic-position",
        datetime.fromisoformat(binding.entry_event_at), binding.symbol, Side.SELL if scenario == "full_short" else Side.BUY,
        volume, 100, 100, 100, 0, 0, volume == .01,
        "PARTIAL_ENTRY_FILL" if volume == .01 else "ENTRY_FILL", FidelityClass.TICK_BID_ASK)
    initial = store.load()
    if scenario in ("rejected", "cancelled", "expired"):
        live_evidence = replace(live_evidence, state=ExecutionStatus.REJECTED, executed_volume=0)
        # The offline rejection outbox uses the existing registry schema too.
        offline_evidence = live_evidence
    elif scenario == "uncertain":
        live_evidence = replace(live_evidence, state=ExecutionStatus.UNCERTAIN, executed_volume=0)
        offline_evidence = None
    elif scenario == "foreign":
        live_evidence = offline_evidence = {"symbol": "XAUUSDm", "magic": 0}
    elif scenario == "identity_mismatch":
        live_evidence = replace(live_evidence, trade_id="foreign")
        offline_evidence = replace(offline_evidence, trade_id="foreign")
    live = apply_setup_consumption(initial, classify_confirmed_entry_fill(binding, live_evidence))
    offline = apply_setup_consumption(initial, classify_confirmed_entry_fill(binding, offline_evidence))
    assert live == offline
    if scenario in ("crash_before_consumption", "matching_restart", "crash_before_ack"):
        before = initial if scenario == "crash_before_consumption" else live.state_record
        assert reconcile_setup_consumption(before, {binding.action_id: live_evidence}) == reconcile_setup_consumption(before, {binding.action_id: offline_evidence})
    if scenario in ("duplicate_fill", "later_remainder"):
        if scenario == "later_remainder":
            live_evidence = replace(live_evidence, executed_volume=.02)
            offline_evidence = replace(offline_evidence, volume=.02, fill_id="later-fill")
        repeated_live = apply_setup_consumption(live.state_record, classify_confirmed_entry_fill(binding, live_evidence))
        repeated_offline = apply_setup_consumption(offline.state_record, classify_confirmed_entry_fill(binding, offline_evidence))
        assert repeated_live == repeated_offline
        assert repeated_live.outcome == "DUPLICATE_IGNORED"
    if scenario == "missing_fill":
        missing = reconcile_setup_consumption(live.state_record, {})
        assert missing == reconcile_setup_consumption(offline.state_record, {})
        assert missing.outcome == "UNCERTAIN_BLOCKED"
    if scenario == "source_reuse":
        assert setup_reuse_reason(live.state_record, "new-decision-id", binding.evidence_id) == "setup_already_consumed"
        assert setup_reuse_reason(live.state_record, "new-evidence-id", "materially-new-evidence") is None
