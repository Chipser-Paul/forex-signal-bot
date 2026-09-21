from __future__ import annotations

from dataclasses import replace

import pytest

from bot.execution.lifecycle import Direction, LifecycleError, LifecycleStatus, manage_position
from bot.execution.lifecycle.serialization import (
    outcome_to_event,
    position_from_payload,
    position_to_payload,
    update_trade_record,
)
from tests.phase3.helpers import config, open_position, tick


def test_position_payload_roundtrip_preserves_lifecycle_and_ledger():
    partial = manage_position(open_position(), tick("partial", 10, 110), config()).position
    restored = position_from_payload(position_to_payload(partial))
    assert restored == partial


def test_trade_record_update_is_backward_compatible():
    position = manage_position(open_position(), tick("partial", 10, 110), config()).position
    record = update_trade_record({"ticket": 7, "comment": "kept"}, position)
    assert record["ticket"] == 7
    assert record["comment"] == "kept"
    assert record["partial_taken"] is True
    assert record["lifecycle"]["trade_id"] == position.trade_id


def test_normalized_closed_event_contains_execution_identity_and_gross_pnl():
    closed = manage_position(open_position(), tick("stop", 10, 90), config()).position
    event = outcome_to_event(closed)
    assert event["signal_id"] == closed.signal_id
    assert event["trade_id"] == closed.trade_id
    assert event["gross_realized_pnl"] == -10.0
    assert event["remaining_quantity"] == 0.0


def test_closed_quantity_cannot_exceed_initial_quantity():
    position = open_position()
    with pytest.raises(LifecycleError, match="exceeds"):
        replace(position, closed_quantity=1.1, remaining_quantity=0.0)


def test_open_position_requires_positive_remaining_quantity():
    position = open_position()
    with pytest.raises(LifecycleError, match="positive remaining"):
        replace(position, remaining_quantity=0.0, closed_quantity=1.0)


def test_direction_is_immutable_through_management():
    position = open_position(Direction.SELL)
    managed = manage_position(position, tick("safe", 10, 95), config()).position
    assert managed.direction is Direction.SELL


def test_every_emitted_action_has_a_unique_stable_id():
    result = manage_position(open_position(), tick("target", 10, 120), config())
    ids = [action.action_id for action in result.actions]
    assert len(ids) == len(set(ids))
    repeated_from_same_initial_state = manage_position(open_position(), tick("target", 10, 120), config())
    assert [action.action_id for action in repeated_from_same_initial_state.actions] == ids


def test_closed_position_has_single_final_transition():
    closed = manage_position(open_position(), tick("stop", 10, 90), config()).position
    final = [transition for transition in closed.transitions if transition.to_status is LifecycleStatus.CLOSED]
    assert len(final) == 1
