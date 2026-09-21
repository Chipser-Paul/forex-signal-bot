from __future__ import annotations

from dataclasses import replace

import pytest

from bot.execution.lifecycle import (
    ActionType,
    LifecycleStatus,
    create_entry_state,
    manage_position,
    process_entry_event,
)
from tests.phase3.helpers import bar, config, intent, open_position, tick


@pytest.mark.known_defect
def test_kd_backtest_001_source_candle_cannot_fill_its_own_signal():
    entry_intent = intent()
    source = bar(
        "source-touch",
        5,
        100.0,
        110.0,
        90.0,
        100.0,
        open_minute=0,
        source_candle_id=entry_intent.source_event_id,
    )
    blocked = process_entry_event(create_entry_state(entry_intent), source)
    assert blocked.triggered is False
    assert blocked.reason == "source_candle_barrier"
    later = process_entry_event(blocked.state, bar("later", 10, 101.0, 102.0, 99.0, 100.0))
    assert later.triggered is True


@pytest.mark.known_defect
def test_kd_exit_001_partial_close_is_shared_and_one_shot():
    position = open_position()
    event = tick("partial", 10, 110.0)
    first = manage_position(position, event, config())
    second = manage_position(first.position, event, config())
    assert [action.action_type for action in first.actions] == [ActionType.PARTIAL_CLOSE]
    assert first.position.status is LifecycleStatus.PARTIALLY_CLOSED
    assert second.duplicate_event is True
    assert second.actions == ()


@pytest.mark.known_defect
def test_kd_exit_002_trailing_rule_checks_old_stop_then_activates_next_event():
    position = replace(open_position(), partial_close_attempted=True, partial_close_occurred=True)
    management = config(trailing_enabled=True, trailing_atr_multiple=3.0)
    trail = manage_position(position, tick("trail", 10, 119.0, atr=5.0), management)
    assert [action.action_type for action in trail.actions] == [ActionType.MODIFY_STOP]
    assert trail.position.current_stop == 104.0
    stopped = manage_position(trail.position, tick("next", 15, 104.0), management)
    assert stopped.position.status is LifecycleStatus.CLOSED


@pytest.mark.known_defect
def test_kd_exit_003_partial_and_final_gross_pnl_reconcile():
    partial = manage_position(open_position(), tick("partial", 10, 110.0), config())
    final = manage_position(partial.position, tick("target", 15, 120.0), config())
    components = final.position.pnl_components
    assert len(components) == 2
    assert sum(component.gross_pnl for component in components) == final.position.realized_gross_pnl
    assert final.position.remaining_quantity == 0.0
