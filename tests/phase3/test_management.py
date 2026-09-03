from __future__ import annotations

import math
from dataclasses import replace

import pytest

from bot.execution.lifecycle import (
    ActionType,
    Direction,
    ExitReason,
    LifecycleError,
    LifecycleStatus,
    manage_position,
    normalized_outcome,
)
from tests.phase3.helpers import bar, config, open_position, tick


@pytest.mark.parametrize(
    ("direction", "event", "expected_reason"),
    [
        (Direction.BUY, bar("long-stop", 10, 100, 105, 89, 92), ExitReason.STOP_LOSS),
        (Direction.SELL, bar("short-stop", 10, 100, 111, 95, 108), ExitReason.STOP_LOSS),
    ],
)
def test_full_stop_is_symmetric(direction, event, expected_reason):
    result = manage_position(open_position(direction), event, config())
    assert result.position.status is LifecycleStatus.CLOSED
    assert result.position.exit_reason is expected_reason
    assert result.position.remaining_quantity == 0


@pytest.mark.parametrize("direction", [Direction.BUY, Direction.SELL])
def test_stop_first_resolves_ambiguous_stop_and_target_bar(direction):
    event = bar("ambiguous", 10, 100, 125, 75, 100)
    result = manage_position(open_position(direction), event, config())
    assert result.position.exit_reason is ExitReason.STOP_LOSS
    assert result.position.ambiguity_policy_used
    assert result.actions[0].metadata["intrabar_ambiguous"] is True


@pytest.mark.parametrize(
    ("direction", "partial_event", "exit_event", "exit_reason"),
    [
        (Direction.BUY, tick("lp", 10, 110), tick("lt", 11, 120), ExitReason.TAKE_PROFIT),
        (Direction.SELL, tick("sp", 10, 90), tick("st", 11, 80), ExitReason.TAKE_PROFIT),
    ],
)
def test_partial_then_final_reconciles_gross_pnl(direction, partial_event, exit_event, exit_reason):
    first = manage_position(open_position(direction), partial_event, config())
    assert first.position.partial_close_occurred
    assert first.position.remaining_quantity == 0.5
    second = manage_position(first.position, exit_event, config())
    assert second.position.exit_reason is exit_reason
    assert second.position.closed_quantity == 1.0
    component_sum = sum(item.gross_pnl for item in second.position.pnl_components)
    assert math.isclose(component_sum, second.position.realized_gross_pnl)
    assert math.isclose(second.position.realized_gross_pnl, 15.0)
    assert math.isclose(normalized_outcome(second.position).gross_r_multiple, 1.5)


def test_partial_happens_once_for_repeated_and_later_events():
    position = open_position()
    event = tick("partial", 10, 110)
    first = manage_position(position, event, config())
    duplicate = manage_position(first.position, event, config())
    later = manage_position(duplicate.position, tick("partial-later", 11, 111), config())
    assert duplicate.duplicate_event
    assert sum(action.action_type is ActionType.PARTIAL_CLOSE for action in first.actions + later.actions) == 1
    assert later.position.closed_quantity == 0.5


def test_partial_quantity_rounds_down_and_preserves_valid_remainder():
    result = manage_position(
        open_position(quantity=0.13),
        tick("partial", 10, 110),
        config(volume_step=0.02, volume_min=0.02),
    )
    assert result.actions[0].quantity == 0.06
    assert result.position.remaining_quantity == pytest.approx(0.07)


def test_invalid_partial_is_skipped_without_full_close():
    result = manage_position(
        open_position(quantity=0.01),
        tick("partial", 10, 110),
        config(volume_step=0.01, volume_min=0.01),
    )
    assert result.actions[0].action_type is ActionType.PARTIAL_SKIPPED
    assert result.position.status is LifecycleStatus.OPEN
    assert result.position.remaining_quantity == 0.01
    assert result.position.partial_close_skip_reason == "partial_below_minimum_volume"


def test_partial_and_final_target_in_same_bar_are_ordered_once():
    result = manage_position(open_position(), bar("targets", 10, 100, 121, 99, 120), config())
    assert [action.action_type for action in result.actions] == [
        ActionType.PARTIAL_CLOSE,
        ActionType.FINAL_CLOSE,
    ]
    assert result.position.status is LifecycleStatus.CLOSED
    assert result.position.realized_gross_pnl == 15.0


def test_partial_and_stop_in_same_bar_uses_stop_without_partial():
    result = manage_position(open_position(), bar("mixed", 10, 100, 111, 89, 100), config())
    assert [action.action_type for action in result.actions] == [ActionType.FINAL_CLOSE]
    assert result.position.exit_reason is ExitReason.STOP_LOSS


def test_existing_stop_is_checked_before_new_trailing_stop():
    position = open_position()
    event = bar("trail-and-stop", 10, 100, 130, 89, 125, atr=5)
    result = manage_position(
        position,
        event,
        config(trailing_enabled=True, trailing_atr_multiple=3.0),
    )
    assert result.position.exit_reason is ExitReason.STOP_LOSS
    assert not any(action.action_type is ActionType.MODIFY_STOP for action in result.actions)


@pytest.mark.parametrize(
    ("direction", "event", "expected_stop"),
    [
        (Direction.BUY, bar("buy-trail", 10, 100, 130, 99, 125, atr=5), 115.0),
        (Direction.SELL, bar("sell-trail", 10, 100, 101, 70, 75, atr=5), 85.0),
    ],
)
def test_trailing_formula_is_symmetric_and_monotonic(direction, event, expected_stop):
    position = open_position(direction)
    position = replace(
        position,
        final_target=140.0 if direction is Direction.BUY else 60.0,
    )
    first = manage_position(
        position,
        event,
        config(trailing_enabled=True, trailing_atr_multiple=3.0),
    )
    assert first.position.current_stop == expected_stop
    assert first.actions[-1].metadata["effective_from_next_event"] is True
    weaker = tick("weaker", 11, 105 if direction is Direction.BUY else 95, atr=5)
    second = manage_position(
        first.position,
        weaker,
        config(trailing_enabled=True, trailing_atr_multiple=3.0),
    )
    assert second.position.current_stop == expected_stop


@pytest.mark.parametrize(
    ("direction", "trail_event", "stop_event"),
    [
        (Direction.BUY, tick("be-up", 10, 115, atr=5), tick("be-stop", 11, 100)),
        (Direction.SELL, tick("be-down", 10, 85, atr=5), tick("be-stop-s", 11, 100)),
    ],
)
def test_break_even_stop_classification(direction, trail_event, stop_event):
    first = manage_position(
        open_position(direction),
        trail_event,
        config(trailing_enabled=True, trailing_atr_multiple=3.0),
    )
    assert first.position.current_stop == 100.0
    second = manage_position(first.position, stop_event, config(trailing_enabled=True))
    assert second.position.exit_reason is ExitReason.BREAK_EVEN


def test_duplicate_exit_does_not_duplicate_pnl():
    event = tick("exit", 10, 90)
    first = manage_position(open_position(), event, config())
    duplicate = manage_position(first.position, event, config())
    assert duplicate.position.realized_gross_pnl == first.position.realized_gross_pnl
    assert len(duplicate.position.pnl_components) == 1
    assert not duplicate.actions


def test_post_exit_event_emits_no_management_action():
    closed = manage_position(open_position(), tick("exit", 10, 90), config()).position
    result = manage_position(closed, tick("after", 11, 120), config())
    assert not result.actions
    assert result.position == closed


def test_management_timestamps_cannot_move_backward():
    first = manage_position(open_position(), tick("first", 10, 105), config()).position
    with pytest.raises(LifecycleError, match="backward"):
        manage_position(first, tick("older", 9, 105), config())


def test_structure_trail_beyond_final_target_is_ignored():
    position = replace(
        open_position(),
        partial_close_attempted=True,
        partial_close_occurred=True,
    )
    result = manage_position(
        position,
        tick("invalid-structure-trail", 10, 105.0, structure_trail_level=125.0),
        config(),
    )
    assert result.position.current_stop == position.current_stop
    assert result.actions == ()
