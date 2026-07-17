from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.analytics_db import (
    fetch_analytics_details,
    fetch_analytics_overview,
    fetch_recent_no_trade_snapshots,
    fetch_recent_trade_reviews as fetch_db_trade_reviews,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
JOURNAL_PATH = ROOT_DIR / "logs" / "trade_journal.jsonl"
UI_LOG_PATH = ROOT_DIR / "logs" / "ui_bot.log"


ANALYST_SYSTEM_PROMPT = (
    "You are an expert review assistant for a deterministic SMC trading bot. "
    "This bot uses market structure, liquidity, displacement, OB/Breaker alignment, and defensive trade management. "
    "Analyze only the provided context. Be evidence-based, practical, concise, and honest. "
    "Do not invent candles, indicators, broker behavior, or missing facts. "
    "Do not speak like a generic AI assistant. Speak like a sharp trading analyst reviewing this specific bot. "
    "Do not propose autonomous execution changes. Focus on setup quality, execution quality, exit quality, risk discipline, "
    "and what the trader can learn next. "
    "Important judgment rules: a stop-loss hit is usually a normal full-risk loss unless the provided context shows the stop placement itself was poor. "
    "Do not call an SL hit 'too defensive' unless there is clear evidence the bot tightened or altered the stop prematurely. "
    "Use 'too defensive' mainly for early profit-lock exits, kill-switch exits, or premature non-TP exits. "
    "If the setup was valid and the trade simply lost at the planned stop, say it was a valid setup that failed, not a defensive mistake."
)

CHAT_AGENT_SYSTEM_PROMPT = (
    "You are the trading copilot for this SMC bot project. "
    "You help the user understand performance, skipped trades, setup quality, risk discipline, "
    "and what patterns are emerging from the journal and recent logs. "
    "Do not invent facts outside the provided context. "
    "Do not tell the bot to place trades automatically. "
    "If the user asks about today, prioritize the today_utc section in the provided context. "
    "If today_utc contains relevant trades or PnL, answer directly from it instead of saying the timeframe is unclear. "
    "Answer clearly, practically, and in a collaborative tone."
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except Exception:
            continue
    return rows


def _priority_source(source: str | None) -> int:
    if source == "manage_open_trades":
        return 2
    if source == "monitor_trades":
        return 1
    return 0


def _compact_trade_context(open_event: dict[str, Any] | None) -> dict[str, Any]:
    if not open_event:
        return {}

    context = open_event.get("context") or {}
    structure_signal = context.get("structure_signal") or {}
    liquidity_signal = context.get("liquidity_signal") or {}
    displacement_signal = context.get("displacement_signal") or {}
    ob_breaker_signal = context.get("ob_breaker_signal") or {}
    entry_signal = context.get("entry_signal") or {}
    risk_plan = context.get("risk_plan") or {}
    levels = context.get("levels") or {}
    bot_context = context.get("bot_context") or {}
    return {
        "market_bias": context.get("market_bias") or {},
        "structure_signal": {
            "structure": structure_signal.get("structure"),
            "state": structure_signal.get("state"),
            "event": structure_signal.get("event"),
            "confidence": structure_signal.get("confidence"),
            "condition": structure_signal.get("condition"),
            "displacement": structure_signal.get("displacement"),
        },
        "liquidity_signal": {
            "type": liquidity_signal.get("type"),
            "classification": liquidity_signal.get("classification"),
            "side": liquidity_signal.get("side"),
            "confidence": liquidity_signal.get("confidence"),
        },
        "displacement_signal": {
            "valid": displacement_signal.get("valid"),
            "type": displacement_signal.get("type"),
            "direction": displacement_signal.get("direction"),
            "strength": displacement_signal.get("strength"),
            "atr": displacement_signal.get("atr"),
        },
        "ob_breaker_signal": {
            "valid": ob_breaker_signal.get("valid"),
            "reason": ob_breaker_signal.get("reason"),
            "type": ob_breaker_signal.get("type"),
            "distance_atr": ob_breaker_signal.get("distance_atr"),
        },
        "entry_signal": {
            "direction": entry_signal.get("direction"),
            "entry_type": entry_signal.get("entry_type"),
            "reason": entry_signal.get("reason"),
        },
        "risk_plan": {
            "risk_per_trade": risk_plan.get("risk_per_trade"),
            "rr_target": risk_plan.get("rr_target"),
            "risk_distance": risk_plan.get("risk_distance"),
            "executed_lot": risk_plan.get("executed_lot"),
        },
        "levels": {
            "price": levels.get("price"),
            "sl": levels.get("sl"),
            "tp": levels.get("tp"),
        },
        "bot_context": {
            "capital": bot_context.get("capital"),
            "daily_target": bot_context.get("daily_target"),
            "symbol_profit_today": bot_context.get("symbol_profit_today"),
        },
    }


def _event_brief(event: dict[str, Any]) -> dict[str, Any]:
    brief = {
        "ts_utc": event.get("ts_utc"),
        "event": event.get("event"),
    }
    if "pnl" in event:
        brief["pnl"] = event.get("pnl")
    if event.get("reason"):
        brief["reason"] = event.get("reason")
    details = event.get("details") or {}
    if details:
        allowed = {
            "locked_profit",
            "peak_profit",
            "lock_pct",
            "close_volume",
            "remaining_volume",
            "price",
            "trigger",
            "new_sl",
            "tf",
            "deal_id",
            "rr",
            "min_rr",
            "invalid_fill",
        }
        compact_details = {k: details[k] for k in details if k in allowed}
        if compact_details:
            brief["details"] = compact_details
    return brief


def _compact_text(value: Any, max_len: int = 180) -> Any:
    if isinstance(value, str):
        text = value.strip().replace("\n", " ")
        return text if len(text) <= max_len else text[: max_len - 3] + "..."
    return value


def load_recent_trade_reviews(limit: int = 30) -> list[dict[str, Any]]:
    db_reviews = fetch_db_trade_reviews(limit=limit)

    rows = _load_jsonl(JOURNAL_PATH)
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ticket = row.get("ticket")
        if isinstance(ticket, int):
            grouped[ticket].append(row)

    reviews: list[dict[str, Any]] = []
    for ticket, events in grouped.items():
        open_event = next((e for e in events if e.get("event") == "trade_opened"), None)
        close_events = [e for e in events if e.get("event") == "trade_closed"]
        if not open_event or not close_events:
            continue

        chosen_close = sorted(
            close_events,
            key=lambda e: (_priority_source(e.get("source")), e.get("ts_utc") or ""),
        )[-1]
        timeline = [_event_brief(e) for e in sorted(events, key=lambda e: e.get("ts_utc") or "")]
        pnl_value = chosen_close.get("pnl")
        pnl_text = f"{float(pnl_value):.2f}" if isinstance(pnl_value, (int, float)) else str(pnl_value)
        label = (
            f"{chosen_close.get('ts_utc', '--')} | {open_event.get('symbol', '-')}"
            f" | {str(open_event.get('direction', '-')).upper()}"
            f" | {chosen_close.get('result', '?')} {pnl_text}"
        )
        reviews.append(
            {
                "ticket": ticket,
                "label": label,
                "opened_at": open_event.get("ts_utc"),
                "closed_at": chosen_close.get("ts_utc"),
                "symbol": open_event.get("symbol"),
                "direction": open_event.get("direction"),
                "lot": open_event.get("lot"),
                "entry_price": open_event.get("entry_price"),
                "sl": open_event.get("sl"),
                "tp": open_event.get("tp"),
                "rr": open_event.get("rr"),
                "close_result": chosen_close.get("result"),
                "close_pnl": chosen_close.get("pnl"),
                "close_reason": chosen_close.get("reason"),
                "close_source": chosen_close.get("source"),
                "context": _compact_trade_context(open_event),
                "timeline": timeline[-12:],
            }
        )

    reviews.sort(key=lambda item: item["closed_at"] or "", reverse=True)
    combined: list[dict[str, Any]] = []
    seen_tickets: set[int] = set()
    for item in db_reviews + reviews:
        ticket = item.get("ticket")
        if isinstance(ticket, int) and ticket in seen_tickets:
            continue
        if isinstance(ticket, int):
            seen_tickets.add(ticket)
        combined.append(item)
    combined.sort(key=lambda item: item.get("closed_at") or "", reverse=True)
    return combined[:limit]


def build_trade_prompt(trade: dict[str, Any]) -> str:
    compact_trade = {
        "ticket": trade.get("ticket"),
        "symbol": trade.get("symbol"),
        "direction": trade.get("direction"),
        "lot": trade.get("lot"),
        "entry_price": trade.get("entry_price"),
        "sl": trade.get("sl"),
        "tp": trade.get("tp"),
        "rr": trade.get("rr"),
        "close_result": trade.get("close_result"),
        "close_pnl": trade.get("close_pnl"),
        "close_reason": trade.get("close_reason"),
        "market_bias": (trade.get("context") or {}).get("market_bias"),
        "structure_signal": (trade.get("context") or {}).get("structure_signal"),
        "liquidity_signal": (trade.get("context") or {}).get("liquidity_signal"),
        "displacement_signal": (trade.get("context") or {}).get("displacement_signal"),
        "ob_breaker_signal": (trade.get("context") or {}).get("ob_breaker_signal"),
        "entry_signal": {
            **(((trade.get("context") or {}).get("entry_signal")) or {}),
            "reason": _compact_text((((trade.get("context") or {}).get("entry_signal")) or {}).get("reason")),
        },
        "risk_plan": (trade.get("context") or {}).get("risk_plan"),
        "timeline": trade.get("timeline", [])[-6:],
    }
    payload = {
        "task": "Review this closed trade from our SMC bot.",
        "trade": compact_trade,
        "review_focus": [
            "Was the setup aligned with the bot's logic?",
            "Was the exit quality good, acceptable, too defensive, or just a normal stop-out?",
            "If the trade won, did the management leave too much on the table?",
            "If the trade lost, distinguish clearly between a normal planned SL loss and an avoidable management mistake.",
        ],
        "output_format": {
            "style": "markdown",
            "max_sections": 5,
            "max_bullets_per_section": 3,
            "sections": [
                "### Verdict",
                "### Setup Quality",
                "### Exit Quality",
                "### What Went Well",
                "### Main Weakness / Next Lesson",
            ],
            "rules": [
                "Use short paragraphs or bullets.",
                "Be specific to the given trade.",
                "Avoid generic filler.",
                "Do not label a planned SL hit as too defensive unless the context proves premature stop tightening or early forced exit.",
                "Complete all requested sections, but keep each section concise.",
            ],
        },
    }
    return json.dumps(payload, indent=2)


def build_daily_summary_payload(day: str) -> dict[str, Any]:
    trades = load_recent_trade_reviews(limit=500)
    same_day = [t for t in trades if str(t.get("closed_at", "")).startswith(day)]
    total_pnl = round(sum(float(t.get("close_pnl") or 0.0) for t in same_day), 2)
    wins = sum(1 for t in same_day if float(t.get("close_pnl") or 0.0) > 0)
    losses = sum(1 for t in same_day if float(t.get("close_pnl") or 0.0) < 0)
    return {
        "day": day,
        "total_pnl": total_pnl,
        "wins": wins,
        "losses": losses,
        "trades": [
            {
                "ticket": t.get("ticket"),
                "direction": t.get("direction"),
                "close_pnl": t.get("close_pnl"),
                "close_reason": t.get("close_reason"),
                "rr": t.get("rr"),
                "market_bias": (t.get("context") or {}).get("market_bias"),
                "liquidity_signal": (t.get("context") or {}).get("liquidity_signal"),
            }
            for t in same_day[:8]
        ],
    }


def build_daily_summary_prompt(day: str) -> str:
    payload = {
        "task": "Summarize this trading day for our SMC bot.",
        "daily_summary": build_daily_summary_payload(day),
        "review_focus": [
            "What setup type did best today?",
            "Were losses normal or avoidable?",
            "Did exits look too defensive or well managed?",
            "What should the trader watch next session?",
        ],
        "output_format": {
            "style": "markdown",
            "max_sections": 4,
            "sections": [
                "### Day Overview",
                "### Best Pattern",
                "### Weak Spot",
                "### Lessons For Next Session",
            ],
        },
    }
    return json.dumps(payload, indent=2)


def _group_loops(raw_lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in raw_lines:
        if "Loop" in raw:
            if current:
                blocks.append(current)
            current = [raw]
        elif current:
            current.append(raw)
    if current:
        blocks.append(current)
    return [block for block in blocks if block and "Loop" in block[0]]


def load_recent_no_trade_blocks(limit: int = 20) -> list[dict[str, Any]]:
    db_blocks = fetch_recent_no_trade_snapshots(limit=limit)

    if not UI_LOG_PATH.exists():
        return db_blocks[:limit]

    lines = UI_LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    blocks = _group_loops(lines[-1000:])
    results: list[dict[str, Any]] = []
    for block in blocks:
        text = "\n".join(block)
        if "[NO_TRADE]" not in text:
            continue
        ts_match = re.search(r"\[(\d{2}:\d{2}:\d{2})\]", text)
        no_trade_match = re.findall(r"\[NO_TRADE\]\s+code=([a-z_]+)\s+reason=(.+)", text)
        reason = f"{no_trade_match[-1][0]}: {no_trade_match[-1][1]}" if no_trade_match else "-"
        results.append(
            {
                "label": f"{ts_match.group(1) if ts_match else '--:--:--'} | {reason}",
                "timestamp": ts_match.group(1) if ts_match else "--:--:--",
                "reason": reason,
                "raw_block": text,
            }
        )

    merged: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for item in db_blocks + results[-limit:][::-1]:
        label = str(item.get("label") or "")
        if label in seen_labels:
            continue
        seen_labels.add(label)
        merged.append(item)
    return merged[:limit]


def build_chat_context(limit_trades: int = 6, limit_no_trades: int = 4) -> dict[str, Any]:
    trades = load_recent_trade_reviews(limit=limit_trades)
    no_trades = load_recent_no_trade_blocks(limit=limit_no_trades)
    overview = fetch_analytics_overview(limit_days=30)
    details = fetch_analytics_details(limit_days=30)
    today_utc = datetime.utcnow().strftime("%Y-%m-%d")
    today_trades = [
        {
            "ticket": t.get("ticket"),
            "symbol": t.get("symbol"),
            "direction": t.get("direction"),
            "closed_at": t.get("closed_at"),
            "pnl": t.get("close_pnl"),
            "reason": t.get("close_reason"),
            "market_bias": (t.get("context") or {}).get("market_bias"),
            "liquidity_signal": (t.get("context") or {}).get("liquidity_signal"),
        }
        for t in trades
        if str(t.get("closed_at", "")).startswith(today_utc)
    ]
    today_pnl = round(sum(float(t.get("pnl") or 0.0) for t in today_trades), 2)
    today_wins = sum(1 for t in today_trades if float(t.get("pnl") or 0.0) > 0)
    today_losses = sum(1 for t in today_trades if float(t.get("pnl") or 0.0) < 0)
    return {
        "today_utc": {
            "date": today_utc,
            "closed_trades": len(today_trades),
            "wins": today_wins,
            "losses": today_losses,
            "net_pnl": today_pnl,
            "trades": today_trades[:6],
        },
        "analytics_overview_30d": overview,
        "analytics_details_30d": {
            "top_no_trade_reasons": details.get("no_trade_reasons", [])[:5],
            "top_exit_reasons": details.get("exit_reasons", [])[:5],
            "condition_performance": details.get("condition_performance", [])[:5],
            "setup_performance": details.get("setup_performance", [])[:5],
        },
        "recent_trades": [
            {
                "ticket": t.get("ticket"),
                "symbol": t.get("symbol"),
                "direction": t.get("direction"),
                "pnl": t.get("close_pnl"),
                "reason": t.get("close_reason"),
                "market_bias": (t.get("context") or {}).get("market_bias"),
                "liquidity_signal": (t.get("context") or {}).get("liquidity_signal"),
            }
            for t in trades
        ],
        "recent_no_trade_blocks": [
            {
                "timestamp": b.get("timestamp"),
                "reason": b.get("reason"),
            }
            for b in no_trades
        ],
    }


def load_analytics_overview(limit_days: int = 30) -> dict[str, Any]:
    return fetch_analytics_overview(limit_days=limit_days)


def load_analytics_details(limit_days: int = 30) -> dict[str, Any]:
    return fetch_analytics_details(limit_days=limit_days)


def build_no_trade_prompt(block: dict[str, Any]) -> str:
    payload = {
        "task": "Explain why the SMC bot skipped this trade.",
        "no_trade_block": {
            "timestamp": block.get("timestamp"),
            "reason": block.get("reason"),
            "raw_block": _compact_text(block.get("raw_block"), max_len=900),
        },
        "review_focus": [
            "Identify the actual blocking rule.",
            "Say whether the skip looks healthy, debatable, or suspicious.",
            "Mention what would have needed to change for a valid entry.",
        ],
        "output_format": {
            "style": "markdown",
            "max_sections": 3,
            "sections": [
                "### What Blocked The Trade",
                "### Was The Skip Reasonable?",
                "### What Needed To Change",
            ],
        },
    }
    return json.dumps(payload, indent=2)
