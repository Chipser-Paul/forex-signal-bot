from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from app_security.redaction import sanitize_mapping
from utils.analytics_db import record_trade_event

LOG_DIR = Path("logs")
JOURNAL_PATH = LOG_DIR / "trade_journal.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


def _append_event(payload: dict[str, Any]) -> None:
    safe_payload = sanitize_mapping(payload)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with JOURNAL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(safe_payload, ensure_ascii=False) + "\n")
    try:
        record_trade_event(safe_payload)
    except Exception:
        pass


def _safe_rr(entry: float, sl: float, tp: float, direction: str) -> float | None:
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    if direction.lower() == "buy":
        reward = tp - entry
    else:
        reward = entry - tp
    return round(reward / risk, 4)


def log_trade_open(
    *,
    ticket: int,
    symbol: str,
    direction: str,
    lot: float,
    entry_price: float,
    sl: float,
    tp: float,
    context: dict[str, Any] | None = None,
) -> None:
    event = {
        "event": "trade_opened",
        "ts_utc": _utc_now_iso(),
        "ticket": int(ticket),
        "symbol": symbol,
        "direction": direction,
        "lot": float(lot),
        "entry_price": float(entry_price),
        "sl": float(sl),
        "tp": float(tp),
        "risk_distance": round(abs(float(entry_price) - float(sl)), 6),
        "rr": _safe_rr(float(entry_price), float(sl), float(tp), direction),
        "context": _json_safe(context or {}),
    }
    _append_event(event)


def log_trade_event(
    *,
    ticket: int,
    symbol: str,
    event_name: str,
    details: dict[str, Any] | None = None,
) -> None:
    event = {
        "event": event_name,
        "ts_utc": _utc_now_iso(),
        "ticket": int(ticket),
        "symbol": symbol,
        "details": _json_safe(details or {}),
    }
    _append_event(event)


def log_trade_close(
    *,
    ticket: int,
    symbol: str,
    pnl: float | None = None,
    exit_price: float | None = None,
    result: str | None = None,
    reason: str | None = None,
    source: str | None = None,
    closed_at_utc: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    normalized_result = result
    if normalized_result is None and pnl is not None:
        if pnl > 0:
            normalized_result = "win"
        elif pnl < 0:
            normalized_result = "loss"
        else:
            normalized_result = "breakeven"

    event = {
        "event": "trade_closed",
        "ts_utc": closed_at_utc or _utc_now_iso(),
        "ticket": int(ticket),
        "symbol": symbol,
        "pnl": None if pnl is None else float(pnl),
        "exit_price": None if exit_price is None else float(exit_price),
        "result": normalized_result or "unknown",
        "reason": reason or "unknown",
        "source": source or "unknown",
        "details": _json_safe(details or {}),
    }
    _append_event(event)
