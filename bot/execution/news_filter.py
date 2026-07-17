from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


UTC = timezone.utc
BLOCK_BEFORE_MINUTES = 30
BLOCK_AFTER_MINUTES = 30
HIGH_IMPACT_KEYWORDS = ("nfp", "cpi", "fomc", "powell", "gdp")
TARGET_CURRENCIES = ("USD", "XAU", "GOLD")


def _coerce_utc(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except Exception:
        return None


def _load_local_news_events() -> list[dict]:
    path = os.getenv("NEWS_EVENTS_PATH", "").strip()
    if not path:
        return []
    file_path = Path(path)
    if not file_path.exists():
        return []
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def _event_matches(event: dict, symbol: str) -> bool:
    title = str(event.get("title", "") or "").lower()
    impact = str(event.get("impact", "") or "").lower()
    currency = str(event.get("currency", "") or "").upper()

    if impact not in ("high", "red", "3", "3.0"):
        return False

    title_match = any(keyword in title for keyword in HIGH_IMPACT_KEYWORDS)
    currency_match = currency in TARGET_CURRENCIES or (
        symbol.startswith("XAU") and currency == "USD"
    )
    return title_match or currency_match


def get_news_status(symbol: str, now: datetime | None = None) -> dict[str, object]:
    """
    Safe first implementation:
    - reads optional local JSON event feed from NEWS_EVENTS_PATH
    - if unavailable, returns news_clear=True with source='fallback'
    """
    now_utc = _coerce_utc(now) or datetime.now(UTC)
    events = _load_local_news_events()
    matching = []

    for event in events:
        event_time = _coerce_utc(event.get("time"))
        if event_time is None or not _event_matches(event, symbol):
            continue
        matching.append(
            {
                **event,
                "time_utc": event_time,
            }
        )

    matching.sort(key=lambda item: item["time_utc"])
    active_event = None
    next_event_minutes = None
    news_clear = True

    for event in matching:
        event_time = event["time_utc"]
        delta_minutes = int((event_time - now_utc).total_seconds() // 60)
        if next_event_minutes is None and delta_minutes >= 0:
            next_event_minutes = delta_minutes

        blackout_start = event_time - timedelta(minutes=BLOCK_BEFORE_MINUTES)
        blackout_end = event_time + timedelta(minutes=BLOCK_AFTER_MINUTES)
        if blackout_start <= now_utc <= blackout_end:
            active_event = event
            news_clear = False
            break

    return {
        "news_clear": news_clear,
        "source": "local_json" if events else "fallback",
        "next_event_in_minutes": next_event_minutes,
        "active_event": {
            "title": active_event.get("title"),
            "currency": active_event.get("currency"),
            "impact": active_event.get("impact"),
            "time_utc": active_event["time_utc"].isoformat(),
        }
        if active_event
        else None,
        "block_window_minutes": {
            "before": BLOCK_BEFORE_MINUTES,
            "after": BLOCK_AFTER_MINUTES,
        },
    }

