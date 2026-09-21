"""Deterministic Phase 3 lifecycle replay with no broker or MT5 access."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bot.execution.lifecycle import (
    Direction,
    ManagementConfig,
    MarketEvent,
    MarketEventKind,
    ReadinessStyle,
    new_entry_intent,
    normalized_trace,
    run_historical_lifecycle,
    run_live_mock_lifecycle,
)


UTC = timezone.utc
SOURCE_OPEN = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
SIGNAL_AT = SOURCE_OPEN + timedelta(minutes=5)


@dataclass(frozen=True)
class ReplayScenario:
    name: str
    direction: Direction
    historical_prices: tuple[tuple[float, float, float, float], ...]
    live_prices: tuple[float, ...]


SCENARIOS = (
    ReplayScenario(
        "long_partial_then_target",
        Direction.BUY,
        ((100.0, 101.0, 99.0, 100.0), (110.0, 111.0, 109.0, 110.0), (120.0, 121.0, 119.0, 120.0)),
        (100.0, 110.0, 120.0),
    ),
    ReplayScenario(
        "short_partial_then_break_even",
        Direction.SELL,
        ((100.0, 101.0, 99.0, 100.0), (90.0, 99.0, 90.0, 91.0), (100.0, 101.0, 99.0, 100.0)),
        (100.0, 90.0, 100.0),
    ),
)


def _intent(direction: Direction):
    stop = 90.0 if direction is Direction.BUY else 110.0
    target = 120.0 if direction is Direction.BUY else 80.0
    return new_entry_intent(
        symbol="SYNTH",
        direction=direction,
        source_timeframe="M5",
        source_candle_open_time=SOURCE_OPEN,
        signal_available_at=SIGNAL_AT,
        requested_trigger=100.0,
        stop_loss=stop,
        final_target=target,
        readiness_style=ReadinessStyle.IMMEDIATE,
        source_event_id="source-m5-1000",
        configuration_id="phase3-replay-v1",
    )


def _events(scenario: ReplayScenario):
    bars = []
    ticks = []
    for offset, (ohlc, tick_price) in enumerate(
        zip(scenario.historical_prices, scenario.live_prices, strict=True),
        start=1,
    ):
        timestamp = SIGNAL_AT + timedelta(minutes=5 * offset)
        open_price, high, low, close = ohlc
        atr = (10.0 / 3.0) if scenario.name.endswith("break_even") and offset == 2 else None
        bars.append(
            MarketEvent(
                event_id=f"{scenario.name}-bar-{offset}",
                timestamp=timestamp,
                symbol="SYNTH",
                source="historical",
                kind=MarketEventKind.BAR,
                sequence=offset,
                open=open_price,
                high=high,
                low=low,
                close=close,
                bar_open_time=timestamp - timedelta(minutes=5),
                atr=atr,
            )
        )
        ticks.append(
            MarketEvent(
                event_id=f"{scenario.name}-tick-{offset}",
                timestamp=timestamp,
                symbol="SYNTH",
                source="live_mock",
                kind=MarketEventKind.TICK,
                sequence=offset,
                bid=tick_price,
                ask=tick_price,
                close=tick_price,
                atr=atr,
            )
        )
    return tuple(bars), tuple(ticks)


def build_replay() -> dict[str, object]:
    config = ManagementConfig(
        partial_close_fraction=0.5,
        partial_target_r=1.0,
        volume_min=0.01,
        volume_step=0.01,
        pnl_per_price_unit=1.0,
        trailing_enabled=True,
        trailing_atr_multiple=3.0,
    )
    results = []
    for scenario in SCENARIOS:
        bars, ticks = _events(scenario)
        intent = _intent(scenario.direction)
        historical = run_historical_lifecycle(intent, bars, quantity=1.0, config=config)
        live = run_live_mock_lifecycle(intent, ticks, quantity=1.0, config=config)
        historical_trace = normalized_trace(historical)
        live_trace = normalized_trace(live)
        results.append(
            {
                "scenario": scenario.name,
                "historical": historical_trace,
                "live_mock": live_trace,
                "match": historical_trace == live_trace,
            }
        )
    return {"phase": 3, "all_match": all(item["match"] for item in results), "scenarios": results}


def main() -> None:
    print(json.dumps(build_replay(), indent=2))


if __name__ == "__main__":
    main()
