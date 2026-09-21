from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

import pytest

from bot.execution.lifecycle import (
    Direction,
    LifecycleError,
    LifecycleStatus,
    ManagementConfig,
    MarketEvent,
    MarketEventKind,
    ReadinessStyle,
    normalized_trace,
    run_historical_lifecycle,
    run_live_mock_lifecycle,
)
from tests.phase3.helpers import SOURCE_OPEN, bar, config, intent, tick


@dataclass(frozen=True)
class ParityScenario:
    name: str
    entry_intent: object
    historical_events: tuple[MarketEvent, ...]
    live_events: tuple[MarketEvent, ...]
    management: ManagementConfig


def _fill_pair(direction: Direction = Direction.BUY, *, event_id: str = "fill"):
    if direction is Direction.BUY:
        return (
            bar(f"h-{event_id}", 10, 100, 105, 95, 101, open_minute=5),
            tick(f"l-{event_id}", 10, 100),
        )
    return (
        bar(f"h-{event_id}", 10, 100, 105, 95, 99, open_minute=5),
        tick(f"l-{event_id}", 10, 100),
    )


def _scenario_data() -> list[ParityScenario]:
    scenarios: list[ParityScenario] = []
    base_cfg = config()

    scenarios.append(
        ParityScenario(
            "signal_never_triggers_and_expires",
            intent(),
            (
                bar("h-wait", 10, 110, 112, 105, 108),
                bar("h-expire", 125, 110, 112, 105, 108),
            ),
            (tick("l-wait", 10, 110), tick("l-expire", 125, 110)),
            base_cfg,
        )
    )

    immediate = intent(readiness=ReadinessStyle.IMMEDIATE)
    h_fill, l_fill = _fill_pair()
    scenarios.append(ParityScenario("immediate_next_event_trigger", immediate, (h_fill,), (l_fill,), base_cfg))
    scenarios.append(
        ParityScenario(
            "trigger_several_events_later",
            intent(),
            (
                bar("h-wait-1", 10, 110, 112, 105, 108),
                bar("h-wait-2", 15, 107, 109, 103, 105),
                bar("h-trigger", 20, 102, 104, 99, 101),
            ),
            (tick("l-wait-1", 10, 110), tick("l-wait-2", 15, 105), tick("l-trigger", 20, 100)),
            base_cfg,
        )
    )

    source_intent = intent()
    h_source = bar(
        "h-source",
        5,
        100,
        110,
        95,
        100,
        open_minute=0,
        source_candle_id=source_intent.source_event_id,
    )
    l_source = replace(
        tick("l-source", 5, 95),
        sequence=0,
        source_candle_id=source_intent.source_event_id,
    )
    scenarios.append(
        ParityScenario(
            "forbidden_same_source_event_touch",
            source_intent,
            (h_source, bar("h-after-source", 10, 102, 103, 99, 101)),
            (l_source, tick("l-after-source", 10, 100)),
            base_cfg,
        )
    )

    for name, direction, h_exit, l_exit in (
        ("long_full_stop", Direction.BUY, bar("h-ls", 15, 100, 105, 89, 92), tick("l-ls", 15, 90)),
        ("short_full_stop", Direction.SELL, bar("h-ss", 15, 100, 111, 95, 108), tick("l-ss", 15, 110)),
        ("long_final_target", Direction.BUY, bar("h-lt", 15, 120, 121, 119, 120), tick("l-lt", 15, 120)),
        ("short_final_target", Direction.SELL, bar("h-st", 15, 80, 81, 79, 80), tick("l-st", 15, 80)),
    ):
        h_entry, l_entry = _fill_pair(direction, event_id=name)
        scenarios.append(
            ParityScenario(name, intent(direction), (h_entry, h_exit), (l_entry, l_exit), base_cfg)
        )

    be_cfg = config(trailing_enabled=True, trailing_atr_multiple=3.0)
    h_entry, l_entry = _fill_pair()
    scenarios.append(
        ParityScenario(
            "partial_then_break_even_stop",
            intent(),
            (
                h_entry,
                bar("h-be-arm", 15, 110, 110, 101, 109, atr=10 / 3),
                bar("h-be-stop", 20, 100, 101, 99, 100),
            ),
            (l_entry, tick("l-be-arm", 15, 110, atr=10 / 3), tick("l-be-stop", 20, 100)),
            be_cfg,
        )
    )

    trailing_intent = replace(intent(), final_target=140.0)
    h_entry, l_entry = _fill_pair()
    scenarios.append(
        ParityScenario(
            "partial_then_trailing_stop",
            trailing_intent,
            (
                h_entry,
                bar("h-partial", 15, 110, 110, 101, 109),
                bar("h-trail", 20, 125, 130, 109, 125, atr=5),
                bar("h-trail-stop", 25, 115, 116, 114, 115),
            ),
            (
                l_entry,
                tick("l-partial", 15, 110),
                tick("l-trail", 20, 130, atr=5),
                tick("l-trail-stop", 25, 115),
            ),
            be_cfg,
        )
    )

    h_entry, l_entry = _fill_pair()
    scenarios.append(
        ParityScenario(
            "partial_then_final_target",
            intent(),
            (h_entry, bar("h-p", 15, 110, 111, 109, 110), bar("h-t", 20, 120, 121, 119, 120)),
            (l_entry, tick("l-p", 15, 110), tick("l-t", 20, 120)),
            base_cfg,
        )
    )

    h_entry, l_entry = _fill_pair()
    scenarios.append(
        ParityScenario(
            "stop_and_target_in_one_bar",
            intent(),
            (h_entry, bar("h-ambiguous", 15, 100, 125, 85, 100)),
            (l_entry, tick("l-conservative-stop", 15, 90)),
            base_cfg,
        )
    )
    scenarios.append(
        ParityScenario(
            "entry_stop_and_target_in_first_eligible_bar",
            intent(),
            (bar("h-entry-ambiguous", 10, 100, 125, 85, 100),),
            (tick("l-entry", 10, 100), tick("l-adverse", 11, 90)),
            base_cfg,
        )
    )
    scenarios.append(
        ParityScenario(
            "gap_across_entry_trigger",
            intent(),
            (bar("h-entry-gap", 10, 95, 99, 94, 98),),
            (tick("l-entry-gap", 10, 95),),
            base_cfg,
        )
    )

    h_entry, l_entry = _fill_pair()
    scenarios.append(
        ParityScenario(
            "gap_across_stop",
            intent(),
            (h_entry, bar("h-stop-gap", 15, 85, 88, 84, 86)),
            (l_entry, tick("l-stop-gap", 15, 85)),
            base_cfg,
        )
    )

    h_entry, l_entry = _fill_pair()
    h_duplicate = bar("h-duplicate", 15, 105, 106, 104, 105)
    l_duplicate = tick("l-duplicate", 15, 105)
    scenarios.append(
        ParityScenario(
            "repeated_identical_market_event",
            intent(),
            (h_entry, h_duplicate, h_duplicate),
            (l_entry, l_duplicate, l_duplicate),
            base_cfg,
        )
    )

    h_entry, l_entry = _fill_pair()
    h_partial = bar("h-partial-repeat", 15, 110, 111, 109, 110)
    l_partial = tick("l-partial-repeat", 15, 110)
    scenarios.append(
        ParityScenario(
            "repeated_partial_event",
            intent(),
            (h_entry, h_partial, h_partial),
            (l_entry, l_partial, l_partial),
            base_cfg,
        )
    )

    h_entry, l_entry = _fill_pair()
    h_exit = bar("h-exit-repeat", 15, 90, 91, 89, 90)
    l_exit = tick("l-exit-repeat", 15, 90)
    scenarios.append(
        ParityScenario(
            "repeated_exit_event",
            intent(),
            (h_entry, h_exit, h_exit),
            (l_entry, l_exit, l_exit),
            base_cfg,
        )
    )

    scenarios.append(
        ParityScenario(
            "expired_signal_receiving_later_trigger",
            intent(),
            (
                bar("h-expiry", 125, 110, 111, 105, 108),
                bar("h-late-trigger", 130, 100, 101, 99, 100),
            ),
            (tick("l-expiry", 125, 110), tick("l-late-trigger", 130, 100)),
            base_cfg,
        )
    )
    return scenarios


def _signature(run):
    position = run.position
    return {
        "entry_status": run.entry_state.status.value,
        "position_status": None if position is None else position.status.value,
        "partial": None if position is None else position.partial_close_occurred,
        "remaining": None if position is None else round(position.remaining_quantity, 8),
        "gross_pnl": None if position is None else round(position.realized_gross_pnl, 8),
        "exit_reason": (
            None
            if position is None or position.exit_reason is None
            else position.exit_reason.value if hasattr(position.exit_reason, "value") else position.exit_reason
        ),
        "trace": normalized_trace(run),
    }


@pytest.mark.parametrize("scenario", _scenario_data(), ids=lambda scenario: scenario.name)
def test_live_mock_and_historical_business_lifecycle_match(scenario):
    historical = run_historical_lifecycle(
        scenario.entry_intent,
        scenario.historical_events,
        quantity=1.0,
        config=scenario.management,
    )
    live = run_live_mock_lifecycle(
        scenario.entry_intent,
        scenario.live_events,
        quantity=1.0,
        config=scenario.management,
    )
    assert _signature(live) == _signature(historical)


def test_invalid_non_finite_market_event_is_rejected_by_both_adapter_inputs():
    builders: tuple[Callable[[], MarketEvent], ...] = (
        lambda: tick("bad-live", 10, float("nan")),
        lambda: bar("bad-history", 10, 100, float("inf"), 99, 100),
    )
    for build in builders:
        with pytest.raises(LifecycleError, match="finite"):
            build()


def test_scenario_register_contains_all_twenty_required_cases():
    names = {scenario.name for scenario in _scenario_data()}
    assert len(names) == 19
    assert "signal_never_triggers_and_expires" in names
    assert "expired_signal_receiving_later_trigger" in names
    # Invalid/non-finite input is the twentieth scenario and is tested separately.
