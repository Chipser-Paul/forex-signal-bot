"""Shared live/offline orchestration of fill-authoritative setup replay."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from bot.execution.lifecycle.models import EntryIntent, MarketEvent, PositionState
from bot.strategy.setup_consumption import (
    ConsumptionTransition, SetupEntryBinding, apply_setup_consumption,
    binding_from_decision, classify_confirmed_entry_fill, reconcile_setup_consumption,
    register_binding,
)
from bot.strategy.setup_state import SetupStateError, SetupStateRecord
from bot.strategy.setup_store import SetupReplayStore


class SetupRecoveryCoordinator:
    """Evidence provider must read an already durable registry/fill journal.

    This coordinator never writes fill evidence or reaches a broker. Separate
    stores recover by replay, not by a fictitious cross-file transaction.
    """

    def __init__(self, store: SetupReplayStore, evidence: Callable[[], Mapping[str, Any]]) -> None:
        self.store = store
        self.evidence = evidence

    def reconcile(self) -> ConsumptionTransition:
        authoritative = self.evidence()
        result = None

        def replay(record):
            nonlocal result
            result = reconcile_setup_consumption(record, authoritative)
            if result.outcome == "STATE_CORRUPT":
                raise SetupStateError("setup reconciliation state corrupt")
            return result.state_record

        self.store.mutate(replay)
        return result

    def publish_decision(self, expected: SetupStateRecord, evaluated: SetupStateRecord) -> SetupStateRecord:
        def publish(current):
            if current != expected:
                raise SetupStateError("setup state changed during evaluation; reevaluation required")
            if current.data()["consumption"] != evaluated.data()["consumption"]:
                raise SetupStateError("gate evaluation changed fill-authoritative consumption")
            return evaluated
        return self.store.mutate(publish)

    def prepare(self, record: SetupStateRecord, intent: EntryIntent, *, action_id: str, trade_id: str,
                entry_event: MarketEvent, tolerance: float = 0.0) -> SetupEntryBinding:
        binding = binding_from_decision(record, intent, action_id=action_id, trade_id=trade_id, entry_event=entry_event, tolerance=tolerance)

        def prepare(current):
            if current != record:
                raise SetupStateError("setup state changed before entry binding")
            return register_binding(current, binding)
        self.store.mutate(prepare)
        return binding

    def confirm(self, binding: SetupEntryBinding, *, position: PositionState | None = None) -> ConsumptionTransition:
        authoritative = self.evidence().get(binding.action_id)
        classified = classify_confirmed_entry_fill(binding, authoritative, position=position)
        result = None

        def consume(current):
            nonlocal result
            result = apply_setup_consumption(current, classified)
            if result.outcome == "STATE_CORRUPT":
                raise SetupStateError("setup consumption state corrupt")
            return result.state_record
        self.store.mutate(consume)
        return result
