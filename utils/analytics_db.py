from __future__ import annotations

import json
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path("data") / "analytics.db"
JOURNAL_PATH = Path("logs") / "trade_journal.jsonl"
_WRITE_LOCK = threading.Lock()


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


def _json_dumps(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _WRITE_LOCK:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS trade_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_utc TEXT NOT NULL,
                    ticket INTEGER,
                    symbol TEXT,
                    event TEXT NOT NULL,
                    direction TEXT,
                    lot REAL,
                    entry_price REAL,
                    sl REAL,
                    tp REAL,
                    risk_distance REAL,
                    rr REAL,
                    pnl REAL,
                    exit_price REAL,
                    result TEXT,
                    reason TEXT,
                    source TEXT,
                    details_json TEXT,
                    context_json TEXT,
                    raw_event_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_trade_events_ticket
                    ON trade_events(ticket, ts_utc);
                CREATE INDEX IF NOT EXISTS idx_trade_events_symbol
                    ON trade_events(symbol, ts_utc);
                CREATE INDEX IF NOT EXISTS idx_trade_events_event
                    ON trade_events(event, ts_utc);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_events_unique
                    ON trade_events(ts_utc, ticket, event, source);

                CREATE TABLE IF NOT EXISTS loop_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_utc TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL,
                    structure TEXT,
                    structure_state TEXT,
                    confidence REAL,
                    condition TEXT,
                    structure_event TEXT,
                    liquidity_side TEXT,
                    liquidity_type TEXT,
                    displacement_valid INTEGER,
                    ob_valid INTEGER,
                    entry_direction TEXT,
                    entry_type TEXT,
                    final_action TEXT NOT NULL,
                    reason_code TEXT,
                    reason_text TEXT,
                    tickets_opened INTEGER DEFAULT 0,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_loop_snapshots_symbol_ts
                    ON loop_snapshots(symbol, ts_utc);
                CREATE INDEX IF NOT EXISTS idx_loop_snapshots_action
                    ON loop_snapshots(final_action, ts_utc);

                CREATE TABLE IF NOT EXISTS ai_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_utc TEXT NOT NULL,
                    review_type TEXT NOT NULL,
                    symbol TEXT,
                    ref_ticket INTEGER,
                    provider TEXT,
                    model TEXT,
                    input_json TEXT,
                    output_text TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ai_reviews_type_ts
                    ON ai_reviews(review_type, ts_utc);
                CREATE INDEX IF NOT EXISTS idx_ai_reviews_ticket
                    ON ai_reviews(ref_ticket, ts_utc);
                """
            )
            conn.commit()
        finally:
            conn.close()


def record_trade_event(event: dict[str, Any]) -> None:
    payload = _json_safe(event)
    with _WRITE_LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO trade_events (
                    ts_utc, ticket, symbol, event, direction, lot, entry_price, sl, tp,
                    risk_distance, rr, pnl, exit_price, result, reason, source,
                    details_json, context_json, raw_event_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("ts_utc") or _utc_now_iso(),
                    payload.get("ticket"),
                    payload.get("symbol"),
                    payload.get("event"),
                    payload.get("direction"),
                    payload.get("lot"),
                    payload.get("entry_price"),
                    payload.get("sl"),
                    payload.get("tp"),
                    payload.get("risk_distance"),
                    payload.get("rr"),
                    payload.get("pnl"),
                    payload.get("exit_price"),
                    payload.get("result"),
                    payload.get("reason"),
                    payload.get("source"),
                    _json_dumps(payload.get("details")),
                    _json_dumps(payload.get("context")),
                    _json_dumps(payload),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def record_loop_snapshot(payload: dict[str, Any]) -> None:
    safe_payload = _json_safe(payload)
    structure = safe_payload.get("structure") or {}
    liquidity = safe_payload.get("liquidity") or {}
    displacement = safe_payload.get("displacement") or {}
    ob_breaker = safe_payload.get("ob_breaker") or {}
    entry = safe_payload.get("entry") or {}

    with _WRITE_LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO loop_snapshots (
                    ts_utc, symbol, price, structure, structure_state, confidence, condition,
                    structure_event, liquidity_side, liquidity_type, displacement_valid, ob_valid,
                    entry_direction, entry_type, final_action, reason_code, reason_text,
                    tickets_opened, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_payload.get("ts_utc") or _utc_now_iso(),
                    safe_payload.get("symbol"),
                    safe_payload.get("price"),
                    structure.get("structure"),
                    structure.get("state"),
                    structure.get("confidence"),
                    structure.get("condition"),
                    structure.get("event"),
                    liquidity.get("side"),
                    liquidity.get("type"),
                    1 if displacement.get("valid") else 0,
                    1 if ob_breaker.get("valid") else 0,
                    entry.get("direction"),
                    entry.get("entry_type"),
                    safe_payload.get("final_action"),
                    safe_payload.get("reason_code"),
                    safe_payload.get("reason_text"),
                    int(safe_payload.get("tickets_opened") or 0),
                    _json_dumps(safe_payload),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def record_ai_review(
    *,
    review_type: str,
    output_text: str,
    symbol: str | None = None,
    ref_ticket: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    input_payload: dict[str, Any] | None = None,
) -> None:
    with _WRITE_LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO ai_reviews (
                    ts_utc, review_type, symbol, ref_ticket, provider, model, input_json, output_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now_iso(),
                    review_type,
                    symbol,
                    ref_ticket,
                    provider,
                    model,
                    _json_dumps(input_payload or {}),
                    output_text,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def _load_json(text: str | None) -> Any:
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {}


def _priority_source(source: str | None) -> int:
    if source == "manage_open_trades":
        return 2
    if source == "monitor_trades":
        return 1
    return 0


def fetch_recent_trade_reviews(limit: int = 30) -> list[dict[str, Any]]:
    ensure_trade_journal_backfill()
    conn = _connect()
    try:
        close_rows = conn.execute(
            """
            SELECT raw_event_json
            FROM trade_events
            WHERE event = 'trade_closed' AND ticket IS NOT NULL
            ORDER BY ts_utc DESC
            LIMIT 500
            """
        ).fetchall()
        if not close_rows:
            return []

        chosen_close_by_ticket: dict[int, dict[str, Any]] = {}
        for row in close_rows:
            event = _load_json(row["raw_event_json"])
            ticket = event.get("ticket")
            if not isinstance(ticket, int):
                continue
            current = chosen_close_by_ticket.get(ticket)
            if current is None:
                chosen_close_by_ticket[ticket] = event
                continue
            current_key = (_priority_source(current.get("source")), current.get("ts_utc") or "")
            new_key = (_priority_source(event.get("source")), event.get("ts_utc") or "")
            if new_key >= current_key:
                chosen_close_by_ticket[ticket] = event

        ordered_tickets = sorted(
            chosen_close_by_ticket.items(),
            key=lambda item: item[1].get("ts_utc") or "",
            reverse=True,
        )[:limit]
        if not ordered_tickets:
            return []

        ticket_ids = [ticket for ticket, _ in ordered_tickets]
        placeholders = ",".join("?" for _ in ticket_ids)
        event_rows = conn.execute(
            f"""
            SELECT raw_event_json
            FROM trade_events
            WHERE ticket IN ({placeholders})
            ORDER BY ts_utc ASC, id ASC
            """,
            ticket_ids,
        ).fetchall()

        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in event_rows:
            event = _load_json(row["raw_event_json"])
            ticket = event.get("ticket")
            if isinstance(ticket, int):
                grouped[ticket].append(event)

        reviews: list[dict[str, Any]] = []
        for ticket, chosen_close in ordered_tickets:
            events = grouped.get(ticket, [])
            open_event = next((e for e in events if e.get("event") == "trade_opened"), None)
            if not open_event:
                continue
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
                    "context": open_event.get("context") or {},
                    "timeline": events[-12:],
                }
            )
        return reviews
    finally:
        conn.close()


def fetch_recent_no_trade_snapshots(limit: int = 20) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT ts_utc, symbol, reason_code, reason_text, payload_json
            FROM loop_snapshots
            WHERE final_action = 'no_trade'
            ORDER BY ts_utc DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            payload = _load_json(row["payload_json"])
            ts = str(row["ts_utc"] or "")
            label = f"{ts} | {row['symbol']} | {row['reason_code']}: {row['reason_text']}"
            raw_block = json.dumps(payload, ensure_ascii=False, indent=2)
            results.append(
                {
                    "label": label,
                    "timestamp": ts,
                    "reason": f"{row['reason_code']}: {row['reason_text']}",
                    "raw_block": raw_block,
                    "symbol": row["symbol"],
                }
            )
        return results
    finally:
        conn.close()


def fetch_recent_loop_snapshots(symbol: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        params: tuple[Any, ...]
        where = ""
        if symbol:
            where = "WHERE symbol = ?"
            params = (symbol, int(limit))
        else:
            params = (int(limit),)

        rows = conn.execute(
            f"""
            SELECT
                id, ts_utc, symbol, price, structure, structure_state, confidence,
                condition, structure_event, liquidity_side, liquidity_type,
                displacement_valid, ob_valid, entry_direction, entry_type,
                final_action, reason_code, reason_text, tickets_opened, payload_json
            FROM loop_snapshots
            {where}
            ORDER BY ts_utc DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            payload = _load_json(row["payload_json"])
            results.append(
                {
                    "id": row["id"],
                    "timestamp": row["ts_utc"],
                    "symbol": row["symbol"],
                    "price": row["price"],
                    "structure": row["structure"],
                    "structure_state": row["structure_state"],
                    "confidence": row["confidence"],
                    "condition": row["condition"],
                    "structure_event": row["structure_event"],
                    "liquidity_side": row["liquidity_side"],
                    "liquidity_type": row["liquidity_type"],
                    "displacement_valid": bool(row["displacement_valid"]),
                    "ob_valid": bool(row["ob_valid"]),
                    "entry_direction": row["entry_direction"],
                    "entry_type": row["entry_type"],
                    "final_action": row["final_action"],
                    "reason_code": row["reason_code"],
                    "reason_text": row["reason_text"],
                    "tickets_opened": row["tickets_opened"],
                    "payload": payload,
                }
            )
        return results
    finally:
        conn.close()


def fetch_analytics_overview(limit_days: int = 30) -> dict[str, Any]:
    ensure_trade_journal_backfill()
    conn = _connect()
    try:
        close_rows = conn.execute(
            """
            SELECT raw_event_json
            FROM trade_events
            WHERE event = 'trade_closed'
              AND ts_utc >= datetime('now', ?)
            ORDER BY ts_utc DESC
            """,
            (f"-{int(limit_days)} days",),
        ).fetchall()
        loop_rows = conn.execute(
            """
            SELECT reason_code, COUNT(*) AS total
            FROM loop_snapshots
            WHERE ts_utc >= datetime('now', ?)
              AND final_action = 'no_trade'
            GROUP BY reason_code
            ORDER BY total DESC
            LIMIT 5
            """,
            (f"-{int(limit_days)} days",),
        ).fetchall()

        chosen_close_by_ticket: dict[int, dict[str, Any]] = {}
        for row in close_rows:
            event = _load_json(row["raw_event_json"])
            ticket = event.get("ticket")
            if not isinstance(ticket, int):
                continue
            current = chosen_close_by_ticket.get(ticket)
            if current is None:
                chosen_close_by_ticket[ticket] = event
                continue
            current_key = (_priority_source(current.get("source")), current.get("ts_utc") or "")
            new_key = (_priority_source(event.get("source")), event.get("ts_utc") or "")
            if new_key >= current_key:
                chosen_close_by_ticket[ticket] = event

        trade_rows = list(chosen_close_by_ticket.values())
        closed = len(trade_rows)
        wins = sum(1 for row in trade_rows if row.get("result") == "win")
        pnl_total = round(sum(float(row.get("pnl") or 0.0) for row in trade_rows), 2)
        exit_reason_counts: dict[str, int] = defaultdict(int)
        for row in trade_rows:
            exit_reason_counts[str(row.get("reason") or "unknown")] += 1
        top_exit_reason = max(exit_reason_counts.items(), key=lambda item: item[1])[0] if exit_reason_counts else "-"

        top_no_trade = loop_rows[0]["reason_code"] if loop_rows else "-"
        return {
            "closed_trades": closed,
            "wins": wins,
            "win_rate": round((wins / closed) * 100.0, 2) if closed else 0.0,
            "net_pnl": pnl_total,
            "top_exit_reason": top_exit_reason,
            "top_no_trade_reason": top_no_trade,
            "no_trade_breakdown": [{row["reason_code"]: row["total"]} for row in loop_rows],
        }
    finally:
        conn.close()


def fetch_analytics_details(limit_days: int = 30) -> dict[str, Any]:
    ensure_trade_journal_backfill()
    conn = _connect()
    try:
        trade_rows = conn.execute(
            """
            SELECT ticket, event, result, pnl, reason, ts_utc, context_json, raw_event_json
            FROM trade_events
            WHERE ts_utc >= datetime('now', ?)
              AND event IN ('trade_opened', 'trade_closed')
            ORDER BY ts_utc ASC, id ASC
            """,
            (f"-{int(limit_days)} days",),
        ).fetchall()
        loop_rows = conn.execute(
            """
            SELECT reason_code, condition, structure, structure_state, final_action
            FROM loop_snapshots
            WHERE ts_utc >= datetime('now', ?)
            ORDER BY ts_utc DESC
            """,
            (f"-{int(limit_days)} days",),
        ).fetchall()

        trade_groups: dict[int, dict[str, Any]] = {}
        for row in trade_rows:
            ticket = row["ticket"]
            if not isinstance(ticket, int):
                continue
            slot = trade_groups.setdefault(ticket, {"open": None, "close": None})
            payload = _load_json(row["raw_event_json"])
            if row["event"] == "trade_opened":
                slot["open"] = payload
            elif row["event"] == "trade_closed":
                current = slot.get("close")
                if current is None:
                    slot["close"] = payload
                else:
                    current_key = (_priority_source(current.get("source")), current.get("ts_utc") or "")
                    new_key = (_priority_source(payload.get("source")), payload.get("ts_utc") or "")
                    if new_key >= current_key:
                        slot["close"] = payload

        condition_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"trades": 0, "wins": 0, "net_pnl": 0.0})
        setup_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"trades": 0, "wins": 0, "net_pnl": 0.0})
        exit_reason_counts: dict[str, int] = defaultdict(int)
        for slot in trade_groups.values():
            open_event = slot.get("open")
            close_event = slot.get("close")
            if not open_event or not close_event:
                continue
            context = open_event.get("context") or {}
            market_bias = context.get("market_bias") or {}
            liquidity_signal = context.get("liquidity_signal") or {}
            condition = str(market_bias.get("condition") or "unknown")
            setup = str(liquidity_signal.get("type") or "unknown")
            pnl = float(close_event.get("pnl") or 0.0)
            win = pnl > 0

            condition_stats[condition]["trades"] += 1
            condition_stats[condition]["wins"] += 1 if win else 0
            condition_stats[condition]["net_pnl"] += pnl

            setup_stats[setup]["trades"] += 1
            setup_stats[setup]["wins"] += 1 if win else 0
            setup_stats[setup]["net_pnl"] += pnl

            exit_reason_counts[str(close_event.get("reason") or "unknown")] += 1

        def _finalize_stats(stats: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for name, item in stats.items():
                trades = int(item["trades"])
                wins = int(item["wins"])
                rows.append(
                    {
                        "name": name,
                        "trades": trades,
                        "wins": wins,
                        "win_rate": round((wins / trades) * 100.0, 2) if trades else 0.0,
                        "net_pnl": round(float(item["net_pnl"]), 2),
                    }
                )
            rows.sort(key=lambda row: row["trades"], reverse=True)
            return rows

        no_trade_counts: dict[str, int] = defaultdict(int)
        condition_counts: dict[str, int] = defaultdict(int)
        for row in loop_rows:
            if row["final_action"] == "no_trade":
                no_trade_counts[str(row["reason_code"] or "unknown")] += 1
            condition_counts[str(row["condition"] or "unknown")] += 1

        no_trade_rows = [
            {"reason_code": key, "count": value}
            for key, value in sorted(no_trade_counts.items(), key=lambda item: item[1], reverse=True)[:8]
        ]
        exit_reason_rows = [
            {"reason": key, "count": value}
            for key, value in sorted(exit_reason_counts.items(), key=lambda item: item[1], reverse=True)[:8]
        ]
        condition_rows = [
            {"condition": key, "loops": value}
            for key, value in sorted(condition_counts.items(), key=lambda item: item[1], reverse=True)[:8]
        ]

        return {
            "no_trade_reasons": no_trade_rows,
            "exit_reasons": exit_reason_rows,
            "condition_performance": _finalize_stats(condition_stats),
            "setup_performance": _finalize_stats(setup_stats),
            "condition_loop_counts": condition_rows,
        }
    finally:
        conn.close()


init_db()


def ensure_trade_journal_backfill() -> None:
    if not JOURNAL_PATH.exists():
        return

    with _WRITE_LOCK:
        conn = _connect()
        try:
            existing = conn.execute("SELECT COUNT(*) FROM trade_events").fetchone()[0]
            if int(existing or 0) > 0:
                return

            rows: list[dict[str, Any]] = []
            for raw in JOURNAL_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue

            for payload in rows:
                safe = _json_safe(payload)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO trade_events (
                        ts_utc, ticket, symbol, event, direction, lot, entry_price, sl, tp,
                        risk_distance, rr, pnl, exit_price, result, reason, source,
                        details_json, context_json, raw_event_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        safe.get("ts_utc") or _utc_now_iso(),
                        safe.get("ticket"),
                        safe.get("symbol"),
                        safe.get("event"),
                        safe.get("direction"),
                        safe.get("lot"),
                        safe.get("entry_price"),
                        safe.get("sl"),
                        safe.get("tp"),
                        safe.get("risk_distance"),
                        safe.get("rr"),
                        safe.get("pnl"),
                        safe.get("exit_price"),
                        safe.get("result"),
                        safe.get("reason"),
                        safe.get("source"),
                        _json_dumps(safe.get("details")),
                        _json_dumps(safe.get("context")),
                        _json_dumps(safe),
                    ),
                )
            conn.commit()
        finally:
            conn.close()
