from __future__ import annotations

import json
import os
import queue
import threading
import urllib.error
import urllib.request
from typing import Any

from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]

from utils.analytics_db import record_ai_review
from utils.log import log


load_dotenv()

_QUEUE: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=32)
_WORKER: threading.Thread | None = None
_WORKER_LOCK = threading.Lock()

_ERROR_DEBUG = os.getenv("AI_LOOP_ANALYST_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
_GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
_SYSTEM_PROMPT = (
    "You are the loop analyst for a deterministic SMC trading bot. "
    "The bot decides trades using market structure, liquidity, displacement, OB/Breaker validation, "
    "and defensive risk rules. You do not make decisions for the bot. "
    "Review only the loop snapshot provided. Respond in 1 or 2 short sentences, max 45 words total. "
    "Say whether the current bot decision looks healthy, debatable, or risky, and name the main reason. "
    "Do not give generic filler. Do not suggest autonomous execution overrides."
)


def _env_flag(name: str, default: str = "1") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _compact(value: Any, max_len: int = 180) -> Any:
    if isinstance(value, str):
        text = value.strip().replace("\n", " ")
        return text if len(text) <= max_len else text[: max_len - 3] + "..."
    return value


def _build_prompt(payload: dict[str, Any]) -> str:
    compact_payload = {
        "symbol": payload.get("symbol"),
        "price": payload.get("price"),
        "timeframes": payload.get("timeframes"),
        "final_action": payload.get("final_action"),
        "reason_code": payload.get("reason_code"),
        "reason_text": _compact(payload.get("reason_text"), max_len=140),
        "tickets_opened": payload.get("tickets_opened"),
        "structure": payload.get("structure") or {},
        "liquidity": payload.get("liquidity") or {},
        "displacement": payload.get("displacement") or {},
        "ob_breaker": payload.get("ob_breaker") or {},
        "entry": payload.get("entry") or {},
    }
    return json.dumps(compact_payload, indent=2)


def _request_groq(prompt: str) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return ""

    payload = {
        "model": os.getenv("AI_LOOP_ANALYST_MODEL", "llama-3.1-8b-instant").strip() or "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": max(1e-8, float(os.getenv("AI_LOOP_ANALYST_TEMPERATURE", "0.2"))),
        "max_tokens": int(os.getenv("AI_LOOP_ANALYST_MAX_TOKENS", "90")),
    }

    req = urllib.request.Request(
        _GROQ_BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "forex-signal-bot/1.0 (+loop-analyst)",
        },
        method="POST",
    )

    timeout = int(os.getenv("AI_LOOP_ANALYST_TIMEOUT", "8"))
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    data = json.loads(body)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def _generate_commentary(payload: dict[str, Any]) -> str:
    return _request_groq(_build_prompt(payload))


def _log_error(symbol: str, exc: Exception) -> None:
    if _ERROR_DEBUG:
        log(f"[] {symbol}: AI Analyst unavailable ({exc})", "yellow")


def _worker_loop() -> None:
    while True:
        payload = _QUEUE.get()
        try:
            symbol = str(payload.get("symbol") or "?")
            commentary = _generate_commentary(payload)
            if commentary:
                record_ai_review(
                    review_type="loop_analysis",
                    symbol=symbol,
                    provider="groq",
                    model=os.getenv("AI_LOOP_ANALYST_MODEL", "llama-3.1-8b-instant").strip() or "llama-3.1-8b-instant",
                    input_payload=payload,
                    output_text=commentary,
                )
                log(f"[] {symbol}: AI Analyst: {commentary}", "blue")
        except Exception as exc:
            _log_error(str(payload.get("symbol") or "?"), exc)
        finally:
            _QUEUE.task_done()


def _ensure_worker() -> None:
    global _WORKER
    if _WORKER and _WORKER.is_alive():
        return
    with _WORKER_LOCK:
        if _WORKER and _WORKER.is_alive():
            return
        _WORKER = threading.Thread(target=_worker_loop, name="loop-ai-analyst", daemon=True)
        _WORKER.start()


def queue_loop_analysis(payload: dict[str, Any]) -> bool:
    if not _env_flag("AI_LOOP_ANALYST_ENABLED", "1"):
        return False
    if not os.getenv("GROQ_API_KEY", "").strip():
        return False

    _ensure_worker()
    try:
        _QUEUE.put_nowait(payload)
        return True
    except queue.Full:
        return False
