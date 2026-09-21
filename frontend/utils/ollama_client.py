from __future__ import annotations

import json
import urllib.error
import urllib.request


OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def _request_json(path: str, payload: dict | None = None, timeout: int = 60) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(f"{OLLAMA_BASE_URL}{path}", data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def ollama_status() -> tuple[bool, str]:
    try:
        _request_json("/api/tags", timeout=5)
        return True, "Ollama is reachable."
    except urllib.error.URLError:
        return False, "Ollama is not running on http://127.0.0.1:11434."
    except Exception as exc:
        return False, f"Ollama check failed: {exc}"


def list_models() -> list[str]:
    try:
        payload = _request_json("/api/tags", timeout=10)
        models = payload.get("models", [])
        return [m.get("name") for m in models if m.get("name")]
    except Exception:
        return []


def generate_text(
    *,
    model: str,
    prompt: str,
    system: str | None = None,
    temperature: float = 0.2,
    timeout: int = 240,
    num_predict: int = 220,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }
    if system:
        payload["system"] = system

    data = _request_json("/api/generate", payload=payload, timeout=timeout)
    return (data.get("response") or "").strip()


def generate_chat(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    num_predict: int = 260,
    timeout: int = 240,
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }
    data = _request_json("/api/chat", payload=payload, timeout=timeout)
    message = data.get("message") or {}
    return (message.get("content") or "").strip()
