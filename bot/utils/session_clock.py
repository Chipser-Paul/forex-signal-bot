from __future__ import annotations

from datetime import datetime, timezone

from bot.strategy.config import StrategyConfig
from bot.strategy.models import SafetyState
from bot.strategy.sessions import evaluate_session
from bot.utils.session_windows import (
    ASIAN_SESSION,
    LONDON_SESSION,
    NEW_YORK_SESSION,
    SESSION_WINDOWS,
    SessionWindow,
)


UTC = timezone.utc

def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("session clock requires a timezone-aware datetime")
    return now.astimezone(UTC)


def _in_window(now_utc: datetime, window: SessionWindow) -> bool:
    current = now_utc.time()
    return window.start <= current < window.end


def get_active_session(now: datetime | None = None) -> str:
    now_utc = _utc_now(now)
    for window in SESSION_WINDOWS:
        if _in_window(now_utc, window):
            return window.name
    return "off_session"


def in_priority_session(now: datetime | None = None) -> bool:
    now_utc = _utc_now(now)
    return any(window.is_priority_session and _in_window(now_utc, window) for window in SESSION_WINDOWS)


def get_session_role(now: datetime | None = None) -> str:
    now_utc = _utc_now(now)
    for window in SESSION_WINDOWS:
        if _in_window(now_utc, window):
            return window.role
    return "off"


def get_session_context(now: datetime | None = None) -> dict[str, object]:
    try:
        now_utc = _utc_now(now)
    except (TypeError, ValueError):
        return {
            "active_session": "unknown",
            "session_allowed": False,
            "is_priority_session": False,
            "session_role": "unsafe",
            "reason": "naive_or_invalid_clock",
            "timestamp_utc": None,
        }
    result = evaluate_session(now_utc, StrategyConfig())
    return {
        "active_session": result.session_name,
        "session_allowed": result.state is SafetyState.CLEAR,
        "is_priority_session": result.priority,
        "session_role": get_session_role(now_utc),
        "reason": result.reason,
        "timestamp_utc": now_utc.isoformat(),
    }


# Backward-compatible aliases for older imports. The live strategy no longer
# uses these names as a trading gate.
def in_killzone(now: datetime | None = None) -> bool:
    return in_priority_session(now)


def get_session_priority(now: datetime | None = None) -> str:
    return get_session_role(now)
