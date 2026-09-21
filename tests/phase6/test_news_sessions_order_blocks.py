from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from bot.strategy import BlockState, SafetyState, StrategyConfig, StrategySide
from bot.strategy.news import (
    NewsEvent,
    NewsImpact,
    NewsSnapshot,
    evaluate_news,
    parse_news_events,
)
from bot.strategy.order_blocks import detect_order_blocks, evaluate_order_block
from bot.strategy.sessions import evaluate_session
from bot.strategy.models import StrategyError


UTC = timezone.utc
NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def news_snapshot(event_at=None, *, retrieved_at=NOW, successful=True, impact=NewsImpact.HIGH):
    events = ()
    if event_at is not None:
        events = (NewsEvent("event-1", event_at, "USD", impact, "CPI", retrieved_at, "fixture"),)
    return NewsSnapshot("fixture", retrieved_at, successful, events)


@pytest.mark.unit
@pytest.mark.parametrize("offset,state", [(-31, SafetyState.CLEAR), (-30, SafetyState.BLOCKED), (0, SafetyState.BLOCKED), (30, SafetyState.BLOCKED), (31, SafetyState.CLEAR)])
def test_news_block_window_boundaries(offset, state):
    event_at = NOW - timedelta(minutes=offset)
    assert evaluate_news(news_snapshot(event_at), NOW, StrategyConfig()).state is state


@pytest.mark.unit
def test_news_missing_failed_stale_and_fresh_empty_behaviour():
    config = StrategyConfig()
    assert evaluate_news(None, NOW, config).state is SafetyState.DATA_UNSAFE
    assert evaluate_news(news_snapshot(successful=False), NOW, config).state is SafetyState.DATA_UNSAFE
    stale = news_snapshot(retrieved_at=NOW - timedelta(minutes=61))
    assert evaluate_news(stale, NOW, config).state is SafetyState.DATA_UNSAFE
    assert evaluate_news(news_snapshot(), NOW, config).state is SafetyState.CLEAR


@pytest.mark.unit
def test_news_parser_deduplicates_and_rejects_unknown_or_naive_data():
    payload = [{"event_id": "same", "time": "2026-01-15T12:30:00Z", "currency": "USD", "impact": "HIGH", "title": "CPI"}] * 2
    assert len(parse_news_events(payload, provider="fixture", retrieved_at=NOW)) == 1
    with pytest.raises((StrategyError, ValueError)):
        parse_news_events([{**payload[0], "impact": "UNKNOWN"}], provider="fixture", retrieved_at=NOW)
    with pytest.raises(StrategyError):
        parse_news_events([{**payload[0], "time": "2026-01-15T12:30:00"}], provider="fixture", retrieved_at=NOW)


@pytest.mark.unit
def test_news_timezone_conversion_is_canonical_utc():
    events = parse_news_events(
        [{"time": "2026-01-15T13:00:00+01:00", "currency": "USD", "impact": "HIGH", "title": "CPI"}],
        provider="fixture",
        retrieved_at=NOW,
    )
    assert events[0].event_at == NOW


@pytest.mark.unit
def test_session_weekend_rollover_and_boundaries():
    config = StrategyConfig()
    saturday = datetime(2026, 1, 17, 12, tzinfo=UTC)
    assert evaluate_session(saturday, config).state is SafetyState.BLOCKED
    assert evaluate_session(datetime(2026, 1, 16, 21, 54, 59, tzinfo=UTC), config).state is SafetyState.CLEAR
    assert evaluate_session(datetime(2026, 1, 16, 21, 55, tzinfo=UTC), config).state is SafetyState.BLOCKED
    assert evaluate_session(datetime(2026, 1, 16, 22, 9, 59, tzinfo=UTC), config).state is SafetyState.BLOCKED
    assert evaluate_session(datetime(2026, 1, 16, 22, 10, tzinfo=UTC), config).state is SafetyState.CLEAR
    assert evaluate_session(datetime(2026, 1, 16, 12), config).state is SafetyState.DATA_UNSAFE


def order_block_frame(include_retest=False, include_after=False, *, bearish=False):
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    rows = []
    for index in range(14):
        price = 100.0 + index * 0.01
        rows.append((price, price + 0.2, price - 0.2, price + 0.01))
    if not bearish:
        rows.extend([(100.5, 101.0, 99.0, 99.5), (99.5, 103.5, 99.4, 103.0)])
        if include_retest:
            rows.append((103.0, 103.2, 100.0, 102.0))
        if include_after:
            rows.append((102.0, 102.2, 101.5, 102.1))
    else:
        rows.extend([(100.0, 101.0, 99.0, 100.5), (100.5, 100.6, 96.5, 97.0)])
        if include_retest:
            rows.append((97.0, 100.0, 96.8, 98.0))
        if include_after:
            rows.append((98.0, 98.5, 97.5, 98.1))
    result = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    result["open_time"] = pd.date_range(start, periods=len(result), freq="5min")
    result["available_at"] = result["open_time"] + pd.Timedelta(minutes=5)
    return result


@pytest.mark.unit
@pytest.mark.parametrize(("side", "bearish"), [(StrategySide.LONG, False), (StrategySide.SHORT, True)])
def test_order_block_confirmation_retest_and_duplicate_suppression(side, bearish):
    config = StrategyConfig()
    confirmed = order_block_frame(bearish=bearish)
    blocks = detect_order_blocks(confirmed, config)
    assert blocks and blocks[-1].side is side
    at_confirmation = confirmed["available_at"].iloc[-1].to_pydatetime()
    assert evaluate_order_block(confirmed, side, at_confirmation, config).state is BlockState.ELIGIBLE

    retested = order_block_frame(include_retest=True, bearish=bearish)
    at_retest = retested["available_at"].iloc[-1].to_pydatetime()
    result = evaluate_order_block(retested, side, at_retest, config)
    assert result.state is BlockState.RETEST_ELIGIBLE
    assert evaluate_order_block(
        retested, side, at_retest, config, consumed_ids=frozenset({result.block_id})
    ).state is BlockState.CONSUMED

    after = order_block_frame(include_retest=True, include_after=True, bearish=bearish)
    assert evaluate_order_block(
        after, side, after["available_at"].iloc[-1].to_pydatetime(), config
    ).state is BlockState.MITIGATED


@pytest.mark.unit
def test_order_block_confirmation_cannot_be_used_early():
    frame = order_block_frame()
    decision = frame["available_at"].iloc[-1].to_pydatetime() - timedelta(microseconds=1)
    assert evaluate_order_block(frame, StrategySide.LONG, decision, StrategyConfig()).state is BlockState.PREMATURE


@pytest.mark.unit
def test_order_block_rejects_naive_or_invalid_candles():
    frame = order_block_frame()
    frame["open_time"] = frame["open_time"].dt.tz_localize(None)
    frame["available_at"] = frame["available_at"].dt.tz_localize(None)
    assert evaluate_order_block(frame, StrategySide.LONG, NOW, StrategyConfig()).state is BlockState.DATA_UNSAFE

    invalid = order_block_frame()
    invalid.loc[invalid.index[-1], "high"] = invalid.loc[invalid.index[-1], "low"] - 1
    assert evaluate_order_block(invalid, StrategySide.LONG, NOW, StrategyConfig()).state is BlockState.DATA_UNSAFE
