from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from app_security.environment import load_project_environment


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
load_project_environment()


def groq_status() -> tuple[bool, str]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return False, "Set GROQ_API_KEY to use Groq."
    return True, "Groq API key detected."


def generate_text(
    *,
    model: str,
    prompt: str,
    system: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 220,
    timeout: int = 60,
) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY.")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": max(1e-8, float(temperature)),
        "max_tokens": int(max_tokens),
    }

    req = urllib.request.Request(
        f"{GROQ_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "forex-signal-bot/1.0 (+local-streamlit-app)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = str(exc)
        raise RuntimeError(f"Groq request failed: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Groq network error: {exc}") from exc

    data = json.loads(body)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()


def generate_chat(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 260,
    timeout: int = 60,
) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY.")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": max(1e-8, float(temperature)),
        "max_tokens": int(max_tokens),
    }

    req = urllib.request.Request(
        f"{GROQ_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "forex-signal-bot/1.0 (+local-streamlit-app)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = str(exc)
        raise RuntimeError(f"Groq request failed: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Groq network error: {exc}") from exc

    data = json.loads(body)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()
