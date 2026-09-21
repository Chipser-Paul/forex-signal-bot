"""Development-only retrospective official schedule; never a live snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from bot.acquisition.evidence_contracts import canonical_hash
from bot.strategy.config import StrategyConfig
from bot.strategy.models import SafetyResult, SafetyState, utc_datetime
from bot.strategy.news import (
    NewsEvent, NewsImpact, active_high_impact_usd_event_ids,
)


CLASSIFICATION = "RETROSPECTIVE_OFFICIAL_SCHEDULE"
PACKAGE_ID = "evidence-official_news-v1-78279c5e26c1c6d1"


class HistoricalNewsError(ValueError):
    """The schedule or provenance cannot support development replay."""


@dataclass(frozen=True)
class HistoricalNewsRecord:
    event: NewsEvent
    source_record_sha256: str


@dataclass(frozen=True)
class HistoricalNewsReplaySnapshot:
    package_id: str
    content_sha256: str
    actual_retrieval_at: datetime
    records: tuple[HistoricalNewsRecord, ...]
    classification: str = CLASSIFICATION
    final_validation_authorized: bool = False
    holdout_access_authorized: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "actual_retrieval_at",
            utc_datetime(self.actual_retrieval_at, "actual news retrieval"),
        )
        if self.package_id != PACKAGE_ID or self.classification != CLASSIFICATION:
            raise HistoricalNewsError("retrospective news package identity mismatch")
        if self.final_validation_authorized or self.holdout_access_authorized:
            raise HistoricalNewsError("historical news cannot authorize validation or holdout")


@dataclass(frozen=True)
class HistoricalNewsReplayDecision:
    decision_at: datetime
    safety: SafetyResult
    package_id: str
    content_sha256: str
    actual_retrieval_at: datetime
    classification: str = CLASSIFICATION
    final_validation_authorized: bool = False
    holdout_access_authorized: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_at", utc_datetime(self.decision_at, "historical decision time"))
        object.__setattr__(self, "actual_retrieval_at", utc_datetime(self.actual_retrieval_at, "actual news retrieval"))
        if self.classification != CLASSIFICATION or self.final_validation_authorized or self.holdout_access_authorized:
            raise HistoricalNewsError("historical news decision cannot authorize validation or holdout")


def _parse_aware(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return utc_datetime(parsed, field)
    except (TypeError, ValueError) as exc:
        raise HistoricalNewsError(f"invalid {field}") from exc


def build_historical_news_snapshot(
    content: Mapping[str, Any] | None, *, package_id: str,
    expected_content_sha256: str,
) -> HistoricalNewsReplaySnapshot:
    """Validate a loaded evidence content object without filesystem access."""
    if content is None or package_id != PACKAGE_ID:
        raise HistoricalNewsError("official schedule missing or package mismatch")
    if canonical_hash(content) != expected_content_sha256:
        raise HistoricalNewsError("official schedule content hash mismatch")
    if (content.get("status") != "ACCEPTED_DEVELOPMENT_ONLY"
            or content.get("complete") is not True
            or content.get("year") != 2024):
        raise HistoricalNewsError("official schedule is incomplete or out of scope")
    raw_events = content.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise HistoricalNewsError("official event coverage is unavailable")

    actual_retrieval = _parse_aware(content.get("retrieval_utc"), "actual retrieval")
    records: dict[str, HistoricalNewsRecord] = {}
    for item in raw_events:
        if not isinstance(item, Mapping):
            raise HistoricalNewsError("malformed official event")
        try:
            event_at = _parse_aware(item.get("event_at_utc"), "event time")
            retrieved_at = _parse_aware(item.get("retrieved_at"), "event retrieval")
            impact = NewsImpact(str(item.get("impact", "")).upper())
            event = NewsEvent(
                event_id=str(item["event_id"]), event_at=event_at,
                currency=str(item["currency"]), impact=impact,
                name=str(item["original_title"]), retrieved_at=retrieved_at,
                provider=str(item["source_agency"]),
            )
            record_hash = str(item["raw_source_sha256"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HistoricalNewsError("malformed official event or unknown impact") from exc
        if len(record_hash) != 64 or any(char not in "0123456789abcdef" for char in record_hash):
            raise HistoricalNewsError("official event source hash invalid")
        if event.currency != "USD" or not (
            datetime(2024, 1, 1, tzinfo=timezone.utc)
            <= event.event_at
            < datetime(2025, 1, 1, tzinfo=timezone.utc)
        ):
            raise HistoricalNewsError("official event currency or year invalid")
        record = HistoricalNewsRecord(event, record_hash)
        if event.event_id in records and records[event.event_id] != record:
            raise HistoricalNewsError("conflicting duplicate official event")
        records[event.event_id] = record
    return HistoricalNewsReplaySnapshot(
        package_id=package_id,
        content_sha256=expected_content_sha256,
        actual_retrieval_at=actual_retrieval,
        records=tuple(sorted(records.values(), key=lambda item: (item.event.event_at, item.event.event_id))),
    )


def evaluate_historical_news(
    snapshot: HistoricalNewsReplaySnapshot | None,
    decision_at: datetime, config: StrategyConfig,
) -> SafetyResult:
    """Reuse the live event-time veto, not its as-of provider freshness claim."""
    if snapshot is None:
        return SafetyResult(SafetyState.DATA_UNSAFE, "historical_official_schedule_missing", provenance=CLASSIFICATION)
    try:
        decision = utc_datetime(decision_at, "historical decision time")
    except (TypeError, ValueError):
        return SafetyResult(SafetyState.DATA_UNSAFE, "invalid_decision_time", provenance=CLASSIFICATION)
    active = active_high_impact_usd_event_ids(
        (record.event for record in snapshot.records), decision, config,
    )
    if active:
        return SafetyResult(SafetyState.BLOCKED, "high_impact_usd_window", active, CLASSIFICATION)
    return SafetyResult(SafetyState.CLEAR, "retrospective_official_no_active_event", (), CLASSIFICATION)


def evaluate_historical_news_decision(
    snapshot: HistoricalNewsReplaySnapshot, decision_at: datetime, config: StrategyConfig,
) -> HistoricalNewsReplayDecision:
    """Retain distinct evaluation and retrospective retrieval times for audit."""
    decision = utc_datetime(decision_at, "historical decision time")
    return HistoricalNewsReplayDecision(
        decision_at=decision,
        safety=evaluate_historical_news(snapshot, decision, config),
        package_id=snapshot.package_id,
        content_sha256=snapshot.content_sha256,
        actual_retrieval_at=snapshot.actual_retrieval_at,
    )
