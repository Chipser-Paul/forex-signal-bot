from __future__ import annotations

from dataclasses import dataclass
from datetime import time


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

SESSION_WINDOWS = (
    ASIAN_SESSION,
    LONDON_SESSION,
    NEW_YORK_SESSION,
)
