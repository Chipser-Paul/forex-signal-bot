from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.strategy.config import StrategyConfig
from bot.strategy.models import SafetyState
from bot.strategy.news import NewsSnapshot, evaluate_news, parse_news_events


UTC = timezone.utc


def _coerce_decision_time(value: datetime | str | None) -> datetime | None:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


def _load_snapshot(path: str) -> NewsSnapshot:
    payload: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("news snapshot must be an object")
    provider = str(payload.get("provider", "")).strip()
    retrieved = _coerce_decision_time(payload.get("retrieved_at"))
    if not provider or retrieved is None or not isinstance(payload.get("events"), list):
        raise ValueError("news snapshot requires provider, retrieved_at, and events")
    successful = payload.get("successful") is True
    events = parse_news_events(payload["events"], provider=provider, retrieved_at=retrieved)
    return NewsSnapshot(provider, retrieved, successful, events, payload.get("failure_reason"))


def get_news_status(
    symbol: str,
    now: datetime | str | None = None,
    *,
    snapshot: NewsSnapshot | None = None,
    config: StrategyConfig | None = None,
) -> dict[str, object]:
    """Return a fail-closed compatibility view of the typed news boundary."""
    decision_at = _coerce_decision_time(now)
    policy = config or StrategyConfig()
    load_reason = None
    if decision_at is None:
        decision_at = datetime.now(UTC)
        load_reason = "invalid_or_naive_decision_time"
    elif snapshot is None:
        path = os.getenv("NEWS_EVENTS_PATH", "").strip()
        if path:
            try:
                snapshot = _load_snapshot(path)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                load_reason = "malformed_or_unavailable_news_snapshot"
    result = evaluate_news(snapshot, decision_at, policy)
    return {
        "symbol": symbol,
        "news_clear": result.state is SafetyState.CLEAR,
        "state": result.state.value,
        "reason": load_reason or result.reason,
        "source": result.provenance or "unavailable",
        "active_event_ids": list(result.event_ids),
        "block_window_minutes": {
            "before": int(policy.news_block_before.total_seconds() // 60),
            "after": int(policy.news_block_after.total_seconds() // 60),
        },
    }
