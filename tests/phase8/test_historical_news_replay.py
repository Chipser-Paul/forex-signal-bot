from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from bot.acquisition.evidence_contracts import canonical_hash
from bot.strategy.config import StrategyConfig
from bot.strategy.models import SafetyState
from bot.strategy.news import NewsSnapshot, evaluate_news
from bot.validation.historical_news_replay import (
    CLASSIFICATION, PACKAGE_ID, HistoricalNewsError,
    build_historical_news_snapshot, evaluate_historical_news,
    evaluate_historical_news_decision,
)


EVENT_AT = datetime(2024, 6, 3, 12, tzinfo=timezone.utc)
RETRIEVED_AT = datetime(2026, 9, 15, tzinfo=timezone.utc)


def _content():
    return {
        "status": "ACCEPTED_DEVELOPMENT_ONLY",
        "complete": True,
        "year": 2024,
        "retrieval_utc": RETRIEVED_AT.isoformat(),
        "events": [{
            "event_id": "synthetic-usd-01",
            "event_at_utc": EVENT_AT.isoformat(),
            "retrieved_at": RETRIEVED_AT.isoformat(),
            "currency": "USD",
            "impact": "HIGH",
            "original_title": "Synthetic release",
            "source_agency": "synthetic-official",
            "raw_source_sha256": "a" * 64,
        }],
    }


def _snapshot(content=None):
    source = _content() if content is None else content
    return build_historical_news_snapshot(
        source, package_id=PACKAGE_ID, expected_content_sha256=canonical_hash(source),
    )


def test_retrospective_replay_reuses_frozen_inclusive_event_window():
    snapshot = _snapshot()
    assert snapshot.classification == CLASSIFICATION
    assert snapshot.actual_retrieval_at == RETRIEVED_AT
    assert snapshot.records[0].event.retrieved_at == RETRIEVED_AT
    config = StrategyConfig()
    for offset, expected in (
        (-timedelta(minutes=30, microseconds=1), SafetyState.CLEAR),
        (-timedelta(minutes=30), SafetyState.BLOCKED),
        (timedelta(minutes=30), SafetyState.BLOCKED),
        (timedelta(minutes=30, microseconds=1), SafetyState.CLEAR),
    ):
        result = evaluate_historical_news(snapshot, EVENT_AT + offset, config)
        assert result.state is expected
        assert result.provenance == CLASSIFICATION


def test_live_freshness_is_not_forged_by_retrospective_adapter():
    snapshot = _snapshot()
    event = snapshot.records[0].event
    live = NewsSnapshot(event.provider, RETRIEVED_AT, True, (event,))
    assert evaluate_news(live, EVENT_AT, StrategyConfig()).state is SafetyState.DATA_UNSAFE
    assert evaluate_historical_news(snapshot, EVENT_AT, StrategyConfig()).state is SafetyState.BLOCKED


def test_replay_decision_retains_distinct_decision_and_actual_retrieval_times():
    snapshot = _snapshot()
    decision = evaluate_historical_news_decision(snapshot, EVENT_AT, StrategyConfig())
    assert decision.decision_at == EVENT_AT
    assert decision.actual_retrieval_at == RETRIEVED_AT
    assert decision.safety.state is SafetyState.BLOCKED
    assert decision.classification == CLASSIFICATION
    assert not decision.final_validation_authorized
    assert not decision.holdout_access_authorized


def test_identical_duplicates_deduplicate_but_conflicts_reject():
    source = _content()
    source["events"].append(dict(source["events"][0]))
    assert len(_snapshot(source).records) == 1
    source["events"][1]["impact"] = "LOW"
    with pytest.raises(HistoricalNewsError, match="conflicting duplicate"):
        _snapshot(source)


@pytest.mark.parametrize("field,value", [
    ("impact", "UNKNOWN"),
    ("currency", "???"),
    ("event_at_utc", "2024-06-03T12:00:00"),
    ("event_at_utc", "2025-06-03T12:00:00Z"),
    ("raw_source_sha256", "not-a-hash"),
])
def test_malformed_or_unknown_event_fails_closed(field, value):
    source = _content()
    source["events"][0][field] = value
    with pytest.raises(HistoricalNewsError):
        _snapshot(source)


def test_missing_or_tampered_package_fails_closed():
    source = _content()
    with pytest.raises(HistoricalNewsError):
        build_historical_news_snapshot(None, package_id=PACKAGE_ID, expected_content_sha256=canonical_hash(source))
    with pytest.raises(HistoricalNewsError):
        build_historical_news_snapshot(source, package_id=PACKAGE_ID, expected_content_sha256="0" * 64)
    with pytest.raises(HistoricalNewsError):
        build_historical_news_snapshot(source, package_id="foreign", expected_content_sha256=canonical_hash(source))
    assert evaluate_historical_news(None, EVENT_AT, StrategyConfig()).state is SafetyState.DATA_UNSAFE
