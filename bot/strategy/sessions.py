from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import StrategyConfig
from .models import SafetyState, SessionResult


def _inside_clock_window(current, start, end) -> bool:
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def evaluate_session(
    decision_at: datetime,
    config: StrategyConfig,
    *,
    broker_available: bool = True,
) -> SessionResult:
    if not isinstance(decision_at, datetime) or decision_at.tzinfo is None:
        return SessionResult(SafetyState.DATA_UNSAFE, "naive_or_invalid_clock", "unknown", False)
    now = decision_at.astimezone(timezone.utc)
    if not broker_available:
        return SessionResult(SafetyState.BLOCKED, "broker_unavailable", "closed", False)
    if now.weekday() >= 5:
        return SessionResult(SafetyState.BLOCKED, "weekend", "closed", False)
    if _inside_clock_window(now.time(), config.rollover_start_utc, config.rollover_end_utc):
        return SessionResult(SafetyState.BLOCKED, "rollover_window", "rollover", False)

    try:
        london = now.astimezone(ZoneInfo("Europe/London"))
        new_york = now.astimezone(ZoneInfo("America/New_York"))
    except ZoneInfoNotFoundError:
        return SessionResult(SafetyState.DATA_UNSAFE, "timezone_database_unavailable", "unknown", False)
    in_london = 8 <= london.hour < 11
    in_new_york = (8, 30) <= (new_york.hour, new_york.minute) < (11, 0)
    if in_london and in_new_york:
        name = "london_new_york_overlap"
    elif in_london:
        name = "london"
    elif in_new_york:
        name = "new_york"
    else:
        name = "off_priority"
    return SessionResult(SafetyState.CLEAR, "weekday_market_window", name, in_london or in_new_york)
