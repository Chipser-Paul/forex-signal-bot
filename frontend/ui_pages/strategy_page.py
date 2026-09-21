from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as st_components

from utils.analytics_db import fetch_recent_loop_snapshots


LOG_PATH = Path("logs/ui_bot.log")
SYMBOLS = ("XAUUSDm", "BTCUSDm")
MAX_LOOP_FEED = 6


def _read_log_lines(limit: int = 3000) -> list[str]:
    if not LOG_PATH.exists():
        return []
    try:
        return LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
    except OSError:
        return []


def _split_loop_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if " Loop " in line and current:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return [block for block in blocks if any("Loop" in line for line in block)]


def _match(pattern: str, text: str, flags: int = 0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _symbol_segments(loop_block: list[str]) -> list[dict]:
    first_symbol_index = None
    for idx, line in enumerate(loop_block):
        if any(f"[{symbol}]" in line for symbol in SYMBOLS):
            first_symbol_index = idx
            break
    if first_symbol_index is None:
        return []

    common = loop_block[:first_symbol_index]
    body = loop_block[first_symbol_index:]

    starts: list[tuple[int, str]] = []
    for idx, line in enumerate(body):
        for symbol in SYMBOLS:
            if f"[{symbol}]" in line:
                starts.append((idx, symbol))
                break

    segments: list[dict] = []
    for pos, (start_idx, symbol) in enumerate(starts):
        end_idx = starts[pos + 1][0] if pos + 1 < len(starts) else len(body)
        segments.append({"symbol": symbol, "lines": common + body[start_idx:end_idx]})
    return segments


def _parse_segment(symbol: str, lines: list[str]) -> dict:
    text = "\n".join(lines)
    timestamp = _match(r"\[(\d{2}:\d{2}:\d{2})\]", text) or "--:--:--"
    bias = (
        _match(rf"{re.escape(symbol)}: Market Bias:\s*([A-Z_]+)", text)
        or _match(r"Market Structure\s*:\s*([A-Z_]+)", text)
        or "-"
    )
    state = (
        _match(rf"{re.escape(symbol)}: Market Bias:.*?State:\s*([A-Z_]+)", text, re.DOTALL)
        or _match(r"Market Structure\s*:\s*[A-Z_]+\s+([A-Z_]+)", text)
        or _match(r"State:\s*([A-Z_]+)", text)
        or "-"
    )
    confidence = (
        _match(rf"{re.escape(symbol)}: Market Bias:.*?Confidence:\s*(\d+)%", text, re.DOTALL)
        or _match(r"Confidence:\s*(\d+)%", text)
        or _match(r"Confidence\s*(\d+)%", text)
        or "0"
    )
    price = _match(rf"{re.escape(symbol)}: Latest price \([A-Z0-9]+\)\s*=\s*([0-9.]+)", text) or "-"
    condition = _match(r"Cond=([a-z_]+)", text) or _match(r"Condition:\s*([A-Z_]+)", text) or "-"
    latest_no_trade = _match(r"\[NO_TRADE\].*?reason=(.+)", text, re.DOTALL) or "-"
    ai_comment = (
        _match(rf"{re.escape(symbol)}: AI Analyst:\s*(.+)", text)
        or _match(r"AI Analyst:\s*(.+)", text)
        or "-"
    )
    liquidity = _match(r"Liquidity Sweep\s*:\s*(.+)", text) or "-"
    entry = _match(r"Entry Model\s*:\s*(.+)", text) or "-"

    action = "TRADE"
    if "[NO_TRADE]" in text:
        action = "NO_TRADE"
    elif "Entry: BLOCKED" in text or "Trades opened: 0" in text:
        action = "BLOCKED"

    return {
        "loop_id": hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:12],
        "symbol": symbol,
        "timestamp": timestamp,
        "bias": bias,
        "state": state,
        "confidence": confidence,
        "price": price,
        "condition": condition.upper(),
        "latest_no_trade": latest_no_trade,
        "ai_comment": ai_comment,
        "liquidity": liquidity,
        "entry": entry,
        "action": action,
        "raw": text,
    }


def _load_symbol_blocks() -> dict[str, list[dict]]:
    grouped = {symbol: [] for symbol in SYMBOLS}
    loaded_from_db = False
    for symbol in SYMBOLS:
        try:
            rows = fetch_recent_loop_snapshots(symbol=symbol, limit=MAX_LOOP_FEED)
        except Exception:
            rows = []
        if rows:
            grouped[symbol] = [_parse_db_snapshot(row) for row in rows]
            loaded_from_db = True

    if loaded_from_db:
        return grouped

    for loop_block in reversed(_split_loop_blocks(_read_log_lines())):
        for segment in _symbol_segments(loop_block):
            grouped[segment["symbol"]].append(_parse_segment(segment["symbol"], segment["lines"]))
    return grouped


def _short_time(ts: str | None) -> str:
    if not ts:
        return "--:--:--"
    match = re.search(r"T(\d{2}:\d{2}:\d{2})", str(ts))
    return match.group(1) if match else str(ts)[-8:]


def _parse_db_snapshot(row: dict) -> dict:
    payload = row.get("payload") or {}
    structure = payload.get("structure") or {}
    session = dict(structure.get("session") or {})
    if "in_killzone" in session:
        session.pop("in_killzone", None)
        session.setdefault("session_allowed", True)
        session.setdefault("is_priority_session", False)
    if "session_priority" in session:
        session["session_role"] = session.pop("session_priority")
    if session:
        structure["session"] = session
    liquidity = payload.get("liquidity") or {}
    entry = payload.get("entry") or {}
    displacement = payload.get("displacement") or {}
    ob_breaker = payload.get("ob_breaker") or {}
    score = structure.get("score") or {}

    reason_code = row.get("reason_code") or "-"
    reason_text = row.get("reason_text") or "-"
    action = str(row.get("final_action") or "-").upper()
    bias = row.get("structure") or structure.get("structure") or "-"
    state = row.get("structure_state") or structure.get("state") or entry.get("engine_state") or "-"
    condition = row.get("condition") or structure.get("condition") or "-"
    raw_conf = row.get("confidence")
    if raw_conf is None:
        raw_conf = structure.get("confidence")
    confidence = raw_conf if raw_conf is not None else 0
    liquidity_text = (
        f"{row.get('liquidity_side') or liquidity.get('side') or '-'} / "
        f"{row.get('liquidity_type') or liquidity.get('type') or '-'}"
    )
    entry_text = (
        f"{entry.get('direction') or row.get('entry_direction') or '-'} "
        f"{entry.get('entry_type') or row.get('entry_type') or '-'}"
    ).strip()
    ai_comment = "-"
    raw = {
        "timestamp": row.get("timestamp"),
        "symbol": row.get("symbol"),
        "price": row.get("price"),
        "structure": structure,
        "liquidity": liquidity,
        "displacement": displacement,
        "ob_breaker": ob_breaker,
        "entry": entry,
        "final_action": row.get("final_action"),
        "reason_code": reason_code,
        "reason_text": reason_text,
    }

    return {
        "loop_id": f"db-{row.get('id')}",
        "symbol": row.get("symbol"),
        "timestamp": _short_time(row.get("timestamp")),
        "bias": str(bias).upper(),
        "state": str(state).upper(),
        "confidence": str(confidence or 0),
        "price": f"{float(row.get('price')):.4f}" if row.get("price") is not None else "-",
        "condition": str(condition).upper(),
        "latest_no_trade": f"{reason_code}: {reason_text}",
        "ai_comment": ai_comment,
        "liquidity": liquidity_text,
        "entry": entry_text,
        "action": action,
        "raw": json.dumps(raw, ensure_ascii=False, indent=2),
    }


def _symbol_title(symbol: str) -> str:
    return "Gold Desk" if symbol == "XAUUSDm" else "Bitcoin Desk"


def _desk_theme(symbol: str) -> dict[str, str]:
    if symbol == "XAUUSDm":
        return {
            "accent": "#D4A63D",
            "accent_soft": "rgba(212, 166, 61, 0.18)",
            "border": "rgba(212, 166, 61, 0.45)",
            "glow": "rgba(212, 166, 61, 0.28)",
            "title": "Gold Desk",
            "subtitle": "SMC flow for XAUUSDm with a warm bullion accent.",
        }
    return {
        "accent": "#F7931A",
        "accent_soft": "rgba(247, 147, 26, 0.18)",
        "border": "rgba(247, 147, 26, 0.45)",
        "glow": "rgba(247, 147, 26, 0.28)",
        "title": "Bitcoin Desk",
        "subtitle": "Crypto-tuned BTCUSDm feed with a sharper momentum accent.",
    }


def _feed_state_key(symbol: str) -> str:
    return f"strategy_loop_feed::{symbol}"


def _merge_loop_feed(symbol: str, incoming: list[dict]) -> list[dict]:
    key = _feed_state_key(symbol)
    cached = st.session_state.get(key, [])
    seen = {item.get("loop_id") for item in cached}
    new_items = [item for item in incoming if item.get("loop_id") not in seen]
    merged = new_items + cached
    deduped: list[dict] = []
    seen_merged: set[str] = set()
    for item in merged:
        loop_id = item.get("loop_id")
        if loop_id in seen_merged:
            continue
        seen_merged.add(loop_id)
        deduped.append(item)
    deduped = deduped[:MAX_LOOP_FEED]
    st.session_state[key] = deduped
    return deduped


def _resolve_refresh_seconds() -> int:
    for key in ("refresh_interval", "refresh_interval_sec", "refresh_seconds"):
        value = st.session_state.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return 3


def _render_react_loop_feed(blocks: list[dict]) -> None:
    """Render the full loop feed as a single React-animated card list.

    Each card combines the header (loop #, timestamp, action, bias, price)
    with the detail card (reason, orchestrator, session, news) into one
    animated component.  Entrance stagger, hover lift, and a live-indicator
    pulse are done via CSS keyframes.
    """
    # ── Serialise every block into a JSON-safe list ───────────────────
    feed: list[dict] = []
    for idx, block in enumerate(blocks, start=1):
        raw_data: dict | None = None
        rt = block.get("raw", "")
        if rt:
            try:
                raw_data = json.loads(rt)
            except (json.JSONDecodeError, TypeError):
                raw_data = None

        card = {
            "idx": idx,
            "timestamp": block.get("timestamp", ""),
            "action": block.get("action", ""),
            "bias": block.get("bias", ""),
            "state": block.get("state", ""),
            "confidence": block.get("confidence", 0),
            "condition": block.get("condition", ""),
            "price": block.get("price", ""),
            "liquidity": block.get("liquidity", ""),
            "entry": block.get("entry", ""),
            # parsed raw payload (may be None)
            "final_action": "",
            "reason_code": "",
            "reason_text": "",
            "orchestrator_state": "",
            "engine_action": "",
            "active_session": None,
            "is_priority": False,
            "session_role": "",
            "session_allowed": None,
            "news_clear": None,
            # additional context
            "displacement_valid": None,
            "ob_valid": None,
            "entry_direction": "",
            "entry_type_label": "",
            "score_value": None,
            "score_max": 12,
            "tickets_opened": 0,
            "ai_comment": "",
            "latest_no_trade": "",
        }
        if raw_data:
            struct = raw_data.get("structure") or {}
            en = raw_data.get("entry") or {}
            sess = struct.get("session") or {}
            displ = raw_data.get("displacement") or {}
            ob = raw_data.get("ob_breaker") or {}
            score_data = struct.get("score") or {}

            score_val = None
            score_max = 12
            if isinstance(score_data, dict):
                score_val = score_data.get("value") or score_data.get("score")
                score_max = score_data.get("max", 12)
            elif isinstance(score_data, (int, float)):
                score_val = int(score_data)

            displ_valid = displ.get("valid")
            if displ_valid is None:
                displ_valid = bool(displ.get("type") or displ.get("impulse_detected"))

            ob_valid = ob.get("valid")
            if ob_valid is None:
                ob_valid = bool(ob.get("zone") or ob.get("direction"))

            card.update(
                final_action=str(raw_data.get("final_action", "")).upper(),
                reason_code=str(raw_data.get("reason_code", "")),
                reason_text=str(raw_data.get("reason_text", "")),
                orchestrator_state=str(struct.get("orchestrator_state", "")),
                engine_action=str(en.get("engine_action", "")),
                active_session=sess.get("active_session"),
                is_priority=sess.get("is_priority_session", False),
                session_role=str(sess.get("session_role", "")),
                session_allowed=sess.get("session_allowed"),
                news_clear=news.get("news_clear") if (news := struct.get("news")) else None,
                displacement_valid=displ_valid,
                ob_valid=ob_valid,
                entry_direction=str(en.get("direction", "")),
                entry_type_label=str(en.get("entry_type", "")),
                score_value=score_val,
                score_max=score_max,
                tickets_opened=int(raw_data.get("tickets_opened", 0)),
            )
        feed.append(card)

    data_json = json.dumps(feed).replace("</", "<\\/")

    react_html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    background:transparent; font-family:system-ui,-apple-system,sans-serif;
    color:#e2e8f0; padding:0 2px;
  }
  .feed-header {
    display:flex; align-items:center; gap:8px; margin-bottom:12px;
  }
  .feed-header h3 { font-size:15px; font-weight:700; color:#f1f5f9; }
  .live-dot {
    width:8px; height:8px; border-radius:50%; background:#22c55e;
    animation: pulse-dot 1.8s ease-in-out infinite;
  }
  @keyframes pulse-dot {
    0%,100% { opacity:1; transform:scale(1); }
    50% { opacity:0.4; transform:scale(0.85); }
  }

  .loop-card {
    background:rgba(15,23,42,0.65); border:1px solid rgba(148,163,184,0.1);
    border-radius:12px; padding:0.7rem 0.9rem; margin-bottom:10px;
    opacity:0; transform:translateY(14px);
    transition:opacity 0.45s cubic-bezier(0.16,1,0.3,1),
               transform 0.45s cubic-bezier(0.16,1,0.3,1),
               box-shadow 0.25s ease, border-color 0.25s ease;
  }
  .loop-card.visible { opacity:1; transform:translateY(0); }
  .loop-card:hover {
    transform:translateY(-2px);
    box-shadow:0 6px 24px rgba(0,0,0,0.35);
    border-color:rgba(148,163,184,0.25);
  }

  .top-row {
    display:flex; align-items:center; gap:8px; margin-bottom:5px;
  }
  .loop-num {
    font-size:10px; font-weight:700; color:rgba(255,255,255,0.3);
    letter-spacing:0.06em;
  }
  .ts { font-size:11px; color:rgba(255,255,255,0.45); }
  .action-pill {
    font-size:10px; font-weight:800; padding:2px 10px; border-radius:20px;
    letter-spacing:0.06em; color:#0a0e22; margin-left:auto;
  }

  .reason-row {
    display:flex; align-items:center; gap:6px; margin-bottom:6px;
    flex-wrap:wrap;
  }
  .rc { font-weight:700; font-size:12px; }
  .rt { color:rgba(255,255,255,0.4); font-size:11px; }

  .info-bar {
    display:flex; align-items:center; gap:6px; flex-wrap:wrap;
    font-size:11px; color:rgba(255,255,255,0.55); margin-bottom:7px;
  }
  .info-sep { color:rgba(255,255,255,0.15); }

  .cols {
    display:grid; grid-template-columns:1fr 1fr 1fr; gap:5px;
  }
  .col {
    background:rgba(0,0,0,0.25); border-radius:6px; padding:0.3rem 0.5rem;
  }
  .col-label {
    font-size:8px; color:rgba(255,255,255,0.3); text-transform:uppercase;
    letter-spacing:0.08em; margin-bottom:2px;
  }
  .col-val { font-weight:600; font-size:12px; color:#e2e8f0; }
  .col-sub { font-size:10px; color:rgba(255,255,255,0.4); }

  .info-sep-dots { color:rgba(255,255,255,0.12); font-size:9px; margin:0 1px; }

  .ai-row {
    margin-top:8px; padding:0.4rem 0.55rem;
    background:rgba(59,130,246,0.06); border-radius:8px;
    font-size:11px; color:rgba(255,255,255,0.55);
    border-left:2px solid rgba(59,130,246,0.25);
    line-height:1.5;
  }
  .ai-icon { color:rgba(59,130,246,0.7); margin-right:4px; }

  .no-trade-row {
    margin-top:6px; font-size:10px; color:rgba(239,68,68,0.7);
    background:rgba(239,68,68,0.06); border-radius:6px; padding:0.25rem 0.5rem;
    word-break:break-word;
  }
</style>
</head>
<body>
<div id="root"></div>
<script>
window.__DATA__ = __DATA_JSON__;
</script>
<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script>
(function(){
'use strict';
var h = React.createElement;

function getColors(action, finalAction) {
  var fa = (finalAction || action || '').toUpperCase();
  if (fa === 'TRADE') return {accent:'#22c55e', pill:'#22c55e', bg:'rgba(34,197,94,0.1)'};
  if (fa === 'NO_TRADE' || fa === 'SKIP') return {accent:'#818cf8', pill:'#818cf8', bg:'rgba(99,102,241,0.08)'};
  if (fa === 'HALT' || fa === 'PAUSE' || fa === 'BLOCKED' || fa === 'ERROR')
    return {accent:'#ef4444', pill:'#ef4444', bg:'rgba(239,68,68,0.1)'};
  return {accent:'rgba(255,255,255,0.4)', pill:'rgba(148,163,184,0.3)', bg:'transparent'};
}

function Card({block, index}) {
  var colors = getColors(block.action, block.final_action);
  var delay = (index * 80) + 'ms';

  var entryDetails = [];
  if (block.entry_direction) entryDetails.push(block.entry_direction);
  if (block.entry_type_label) entryDetails.push(block.entry_type_label);
  var entryStr = entryDetails.length ? entryDetails.join(' ') : null;

  var displStr = block.displacement_valid === true ? '\u2713 Valid' :
                 block.displacement_valid === false ? '\u2717 None' : null;
  var obStr = block.ob_valid === true ? '\u2713 Valid' :
              block.ob_valid === false ? '\u2717 None' : null;

  var scoreStr = null;
  if (block.score_value !== null && block.score_value !== undefined) {
    scoreStr = block.score_value + '/' + (block.score_max || 12);
  }

  return h('div', {
    className: 'loop-card visible',
    style: { transitionDelay: delay, animationDelay: delay, borderLeft: '3px solid ' + colors.accent }
  },
    h('div', {className:'top-row'},
      h('span', {className:'loop-num'}, '#' + block.idx),
      h('span', {className:'ts'}, block.timestamp),
      h('span', {className:'action-pill', style:{background:colors.pill}},
        block.final_action || block.action || '\u2014')
    ),
    (block.latest_no_trade && block.latest_no_trade !== '-' && block.latest_no_trade !== ': -')
      ? h('div', {className:'no-trade-row'}, block.latest_no_trade)
      : null,
    (block.reason_code || block.reason_text) ? h('div', {className:'reason-row'},
      block.reason_code ? h('span', {className:'rc', style:{color:colors.accent}}, block.reason_code) : null,
      block.reason_text ? h('span', {className:'rt'}, block.reason_text) : null
    ) : null,
    h('div', {className:'info-bar'},
      h('span', null, block.bias + ' ' + block.state + ' (' + block.confidence + '%)'),
      h('span', {className:'info-sep'}, '|'),
      h('span', null, block.condition || '\u2014'),
      h('span', {className:'info-sep'}, '|'),
      h('span', null, block.price),
      block.tickets_opened ? h('span', {className:'info-sep'}, '|') : null,
      block.tickets_opened ? h('span', {style:{color:'#22c55e',fontWeight:700}}, '\u2726x' + block.tickets_opened) : null
    ),
    h('div', {className:'cols'},
      h('div', {className:'col'},
        h('div', {className:'col-label'}, 'Orchestrator'),
        h('div', {className:'col-val'}, block.orchestrator_state || '\u2014'),
        block.engine_action ? h('div', {className:'col-sub'}, '\u2192 ' + block.engine_action) : null
      ),
      h('div', {className:'col'},
        h('div', {className:'col-label'}, 'Session'),
        h('div', {className:'col-val'},
          block.active_session ? block.active_session + (block.is_priority ? ' \u2605' : '') : '\u2014'
        ),
        block.session_allowed === true ? h('div', {className:'col-sub'}, '\u2713 OK') :
        block.session_allowed === false ? h('div', {className:'col-sub'}, '\u2717 Blocked') : null
      ),
      h('div', {className:'col'},
        h('div', {className:'col-label'}, 'News'),
        h('div', {className:'col-val'},
          block.news_clear === true ? '\u2713 Clear' : block.news_clear === false ? '\u26a0 Near' : '\u2014'
        )
      )
    ),
    h('div', {className:'cols', style:{marginTop:'5px'}},
      h('div', {className:'col'},
        h('div', {className:'col-label'}, 'Entry'),
        h('div', {className:'col-val'}, entryStr || '\u2014'),
        block.liquidity ? h('div', {className:'col-sub'}, block.liquidity) : null
      ),
      h('div', {className:'col'},
        h('div', {className:'col-label'}, 'Displacement / OB'),
        h('div', {className:'col-val'}, displStr || '\u2014'),
        obStr ? h('div', {className:'col-sub'}, 'OB: ' + obStr) : null
      ),
      h('div', {className:'col'},
        h('div', {className:'col-label'}, 'Score'),
        h('div', {className:'col-val', style: block.score_value >= 10 ? {color:'#22c55e'} :
          block.score_value >= 8 ? {color:'#facc15'} : {}},
          scoreStr || '\u2014'
        )
      )
    ),
    block.ai_comment && block.ai_comment !== '-'
      ? h('div', {className:'ai-row'},
      h('span', {className:'ai-icon'}, '\u25b6'),
      block.ai_comment
    ) : null
  );
}

function App() {
  var blocks = window.__DATA__ || [];
  return h('div', null,
    h('div', {className:'feed-header'},
      h('h3', null, 'Live Loop Feed'),
      h('div', {className:'live-dot'})
    ),
    blocks.map(function(b, i) { return h(Card, {key:i, block:b, index:i}); })
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(h(App));
})();
</script>
</body>
</html>""".replace("__DATA_JSON__", data_json)

    st_components.html(react_html, height=min(180 + len(blocks) * 175, 1200), scrolling=True)


def _render_symbol_desk(symbol: str, blocks: list[dict]) -> None:
    theme = _desk_theme(symbol)
    st.markdown(
        f"""
        <style>
        .desk-hero {{
            border: 1px solid {theme['border']};
            background:
                radial-gradient(circle at top right, {theme['glow']}, transparent 42%),
                linear-gradient(145deg, rgba(8, 12, 28, 0.95), rgba(11, 20, 42, 0.92));
            border-radius: 22px;
            padding: 1.15rem 1.25rem;
            box-shadow: 0 18px 45px rgba(0,0,0,0.28);
            margin: 0.25rem 0 1rem 0;
        }}
        .desk-hero .eyebrow {{
            color: {theme['accent']};
            font-size: 0.8rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
            font-weight: 700;
        }}
        .desk-hero h2 {{
            margin: 0;
            font-size: 2.1rem;
        }}
        .desk-hero p {{
            margin: 0.45rem 0 0 0;
            color: rgba(255,255,255,0.78);
        }}
        .desk-state {{
            border-left: 4px solid {theme['accent']};
            background: linear-gradient(160deg, {theme['accent_soft']}, rgba(10, 16, 32, 0.85));
            border-radius: 18px;
            padding: 1rem 1.1rem;
            margin: 0.65rem 0 1rem 0;
        }}
        .desk-state .eyebrow {{
            color: {theme['accent']};
            letter-spacing: 0.16em;
            text-transform: uppercase;
            font-size: 0.76rem;
            font-weight: 700;
        }}
        </style>
        <div class="desk-hero">
            <div class="eyebrow">{symbol}</div>
            <h2>{theme['title']}</h2>
            <p>{theme['subtitle']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not blocks:
        st.markdown(
            f"""
            <div class="card-shell" style="text-align:center;padding:2rem;">
                <div class="panel-title" style="margin-bottom:8px;">No Data Yet</div>
                <div class="panel-subtitle">The bot hasn't processed a loop for <strong>{symbol}</strong> yet.</div>
                <div class="panel-subtitle">Let the bot run for another cycle or check logs/ui_bot.log.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    live_feed = _merge_loop_feed(symbol, blocks[:MAX_LOOP_FEED])
    latest = live_feed[0]
    top = st.columns(4)
    bias = latest["bias"]
    bias_color = "var(--success)" if "BULL" in bias else "var(--danger)" if "BEAR" in bias else "var(--text-2)"
    top[0].markdown(
        f'<div class="metric-card"><div class="metric-label">Last Loop</div>'
        f'<div class="metric-value">{latest["timestamp"]}</div></div>',
        unsafe_allow_html=True,
    )
    top[1].markdown(
        f'<div class="metric-card"><div class="metric-label">Market Bias</div>'
        f'<div class="metric-value" style="color:{bias_color}">{bias}</div></div>',
        unsafe_allow_html=True,
    )
    confidence_val = int(float(latest["confidence"]))
    conf_color = "var(--success)" if confidence_val >= 80 else "var(--warn)" if confidence_val >= 50 else "var(--danger)"
    top[2].markdown(
        f'<div class="metric-card"><div class="metric-label">Confidence</div>'
        f'<div class="metric-value" style="color:{conf_color}">{latest["confidence"]}%</div></div>',
        unsafe_allow_html=True,
    )
    condition = latest["condition"]
    cond_color = "var(--success)" if "TREND" in condition else "var(--accent)" if "VOL" in condition else "var(--text-2)"
    top[3].markdown(
        f'<div class="metric-card"><div class="metric-label">Condition</div>'
        f'<div class="metric-value" style="font-size:18px;color:{cond_color}">{condition}</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="desk-state">
            <div class="eyebrow">Current State</div>
            <h3 style="margin:0 0 .5rem 0;">{latest['state']}</h3>
            <p style="margin:0;">Price: {latest['price']} | Action: {latest['action']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    info_cols = st.columns([1.15, 1, 1.25])
    with info_cols[0]:
        st.markdown("**Latest no-trade / block reason**")
        st.write(latest["latest_no_trade"])
    with info_cols[1]:
        st.markdown("**Liquidity / Entry**")
        st.write(f"{latest['liquidity']}\n\n{latest['entry']}")
    with info_cols[2]:
        st.markdown("**AI Analyst**")
        st.write(latest["ai_comment"])

    _render_react_loop_feed(live_feed)


STATE_KEY = "strategy_page_feed_cache"
SELECTED_SYMBOL_KEY = "strategy_page_selected_symbol"

# Module-level fragment so Streamlit can isolate reruns properly.
# Streamlit fragments support internal scheduling; we keep it simple by using a fixed ~30s cadence.
@st.fragment(run_every="30s")
def _live_feed_fragment() -> None:
    selected_symbol = st.session_state.get(SELECTED_SYMBOL_KEY, SYMBOLS[0])
    refresh_seconds = max(30, _resolve_refresh_seconds())

    # cache + refresh gating
    cache = st.session_state.get(STATE_KEY, {})
    last_ts = float(cache.get("last_ts", 0.0))
    refresh_due = (time.time() - last_ts) >= float(refresh_seconds)

    if refresh_due or not cache.get("grouped"):
        cache["grouped"] = _load_symbol_blocks()
        cache["last_ts"] = time.time()
        st.session_state[STATE_KEY] = cache

    grouped = cache.get("grouped", {symbol: [] for symbol in SYMBOLS})

    # Render ONLY the live feed portion
    _render_symbol_desk(selected_symbol, grouped.get(selected_symbol, []))


def strategy_page() -> None:
    st.markdown(
        """
        <div class="hero-panel">
            <div class="eyebrow">Strategy Feed</div>
            <h1>Symbol Desk</h1>
            <p>Pick one symbol and inspect its live structure, conditions, AI commentary, and recent loops without the split-screen clutter.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Professional symbol selector bar styled like a trading terminal
    st.markdown(
        """
        <style>
        div[data-testid="stHorizontalBlock"]:has(div.stSegmentedControl) {
            background: linear-gradient(145deg, rgba(8, 12, 28, 0.95), rgba(11, 20, 42, 0.92));
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-radius: 16px;
            padding: 0.5rem 0.75rem;
            margin-bottom: 1rem;
        }
        div.stSegmentedControl {
            width: 100%;
        }
        div.stSegmentedControl div[role="radiogroup"] {
            display: flex;
            gap: 0;
            background: rgba(2, 6, 23, 0.5);
            border-radius: 12px;
            padding: 3px;
            border: 1px solid rgba(148, 163, 184, 0.08);
        }
        div.stSegmentedControl label {
            flex: 1;
            text-align: center;
            padding: 10px 20px !important;
            border-radius: 10px !important;
            cursor: pointer;
            transition: all 0.25s ease !important;
            font-weight: 600 !important;
            font-size: 14px !important;
            letter-spacing: 0.04em;
            color: var(--text-2) !important;
            background: transparent !important;
            border: none !important;
            margin: 0 !important;
        }
        div.stSegmentedControl label:hover {
            color: var(--text-0) !important;
            background: rgba(248, 211, 79, 0.06) !important;
        }
        div.stSegmentedControl label[aria-checked="true"] {
            background: rgba(248, 211, 79, 0.14) !important;
            color: var(--accent) !important;
            box-shadow: 0 2px 12px rgba(248, 211, 79, 0.1);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    selected_symbol = st.segmented_control(
        "Symbol",
        options=SYMBOLS,
        default=SYMBOLS[0],
        format_func=lambda s: f"  {_symbol_title(s)}  ({s})",
        label_visibility="collapsed",
    )

    # Make selected_symbol accessible to the fragment on its own reruns.
    st.session_state[SELECTED_SYMBOL_KEY] = selected_symbol

    refresh_seconds = max(30, _resolve_refresh_seconds())
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">'
        f'<span class="status-dot"></span>'
        f'<span style="color:var(--text-2);font-size:13px;">Live feed auto-updates every ~{refresh_seconds}s</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Render fragment (the rest of the page stays visually stable).
    _live_feed_fragment()
