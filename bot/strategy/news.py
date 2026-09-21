from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

from .config import StrategyConfig
from .models import SafetyResult, SafetyState, StrategyError, utc_datetime


class NewsImpact(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class NewsEvent:
    event_id: str
    event_at: datetime
    currency: str
    impact: NewsImpact
    name: str
    retrieved_at: datetime
    provider: str

    def __post_init__(self) -> None:
        if not self.event_id or not self.currency or not self.name or not self.provider:
            raise StrategyError("news event identity and provenance are required")
        object.__setattr__(self, "event_at", utc_datetime(self.event_at, "news event time"))
        object.__setattr__(self, "retrieved_at", utc_datetime(self.retrieved_at, "news retrieval time"))
        object.__setattr__(self, "currency", self.currency.upper())


@dataclass(frozen=True)
class NewsSnapshot:
    provider: str
    retrieved_at: datetime
    successful: bool
    events: tuple[NewsEvent, ...]
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.provider:
            raise StrategyError("news provider identity is required")
        object.__setattr__(self, "retrieved_at", utc_datetime(self.retrieved_at, "news snapshot time"))


def stable_news_id(provider: str, event_at: datetime, currency: str, name: str) -> str:
    material = f"{provider}|{event_at.astimezone(timezone.utc).isoformat()}|{currency.upper()}|{name}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def active_high_impact_usd_event_ids(
    events: Iterable[NewsEvent], decision_at: datetime, config: StrategyConfig,
) -> tuple[str, ...]:
    """Apply the frozen inclusive event-time window after source validation."""
    now = decision_at.astimezone(timezone.utc)
    deduplicated = {event.event_id: event for event in events}
    return tuple(
        event.event_id
        for event in sorted(deduplicated.values(), key=lambda item: (item.event_at, item.event_id))
        if event.currency == "USD"
        and event.impact is NewsImpact.HIGH
        and event.event_at - config.news_block_before <= now <= event.event_at + config.news_block_after
    )


def evaluate_news(
    snapshot: NewsSnapshot | None,
    decision_at: datetime,
    config: StrategyConfig,
) -> SafetyResult:
    if not isinstance(decision_at, datetime) or decision_at.tzinfo is None:
        return SafetyResult(SafetyState.DATA_UNSAFE, "invalid_decision_time")
    now = decision_at.astimezone(timezone.utc)
    if snapshot is None:
        return SafetyResult(SafetyState.DATA_UNSAFE, "provider_not_configured")
    if not snapshot.successful:
        return SafetyResult(
            SafetyState.DATA_UNSAFE,
            snapshot.failure_reason or "provider_failed",
            provenance=snapshot.provider,
        )
    age = now - snapshot.retrieved_at
    if age.total_seconds() < 0 or age > config.news_max_age:
        return SafetyResult(SafetyState.DATA_UNSAFE, "stale_or_future_snapshot", provenance=snapshot.provider)

    for event in snapshot.events:
        if event.provider != snapshot.provider or event.retrieved_at != snapshot.retrieved_at:
            return SafetyResult(SafetyState.DATA_UNSAFE, "event_provenance_mismatch", provenance=snapshot.provider)
    active = active_high_impact_usd_event_ids(snapshot.events, now, config)
    if active:
        return SafetyResult(SafetyState.BLOCKED, "high_impact_usd_window", active, snapshot.provider)
    return SafetyResult(SafetyState.CLEAR, "fresh_provider_no_active_event", (), snapshot.provider)


def parse_news_events(
    payload: Iterable[dict],
    *,
    provider: str,
    retrieved_at: datetime,
) -> tuple[NewsEvent, ...]:
    events: dict[str, NewsEvent] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise StrategyError("news event must be an object")
        raw_time = item.get("event_at", item.get("time"))
        parsed = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise StrategyError("news event time must include a timezone")
        impact_text = str(item.get("impact", "")).upper()
        aliases = {"RED": "HIGH", "3": "HIGH", "3.0": "HIGH"}
        impact = NewsImpact(aliases.get(impact_text, impact_text))
        currency = str(item.get("currency", "")).upper()
        name = str(item.get("name", item.get("title", ""))).strip()
        event_id = str(item.get("event_id") or stable_news_id(provider, parsed, currency, name))
        event = NewsEvent(event_id, parsed, currency, impact, name, retrieved_at, provider)
        events[event.event_id] = event
    return tuple(sorted(events.values(), key=lambda event: (event.event_at, event.event_id)))
