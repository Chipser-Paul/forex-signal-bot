from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone


UTC = timezone.utc


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start: time
    end: time
    is_priority_session: bool
    role: str


ASIAN_SESSION = SessionWindow(
    name="asian",
    start=time(0, 0),
    end=time(6, 0),
    is_priority_session=False,
    role="context",
)

LONDON_SESSION = SessionWindow(
    name="london",
    start=time(7, 0),
    end=time(10, 0),
    is_priority_session=True,
    role="primary_liquidity_window",
)

NEW_YORK_SESSION = SessionWindow(
    name="new_york",
    start=time(12, 30),
    end=time(15, 0),
    is_priority_session=True,
    role="secondary_liquidity_window",
)

SESSION_WINDOWS = [
    ASIAN_SESSION,
    LONDON_SESSION,
    NEW_YORK_SESSION,
]


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
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
    now_utc = _utc_now(now)
    active = get_active_session(now_utc)
    return {
        "active_session": active,
        "session_allowed": True,
        "is_priority_session": in_priority_session(now_utc),
        "session_role": get_session_role(now_utc),
        "timestamp_utc": now_utc.isoformat(),
    }


# Backward-compatible aliases for older imports. The live strategy no longer
# uses these names as a trading gate.
def in_killzone(now: datetime | None = None) -> bool:
    return in_priority_session(now)


def get_session_priority(now: datetime | None = None) -> str:
    return get_session_role(now)
