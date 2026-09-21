from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_security.redaction import is_sensitive_key

from .credential_store import delete_password


SESSION_FILE = os.path.join(os.path.dirname(__file__), ".session.json")


def _without_sensitive_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _without_sensitive_values(item)
            for key, item in value.items()
            if not is_sensitive_key(key)
        }
    if isinstance(value, list):
        return [_without_sensitive_values(item) for item in value]
    if isinstance(value, tuple):
        return [_without_sensitive_values(item) for item in value]
    return value


def _write_preferences(data: dict[str, Any]) -> bool:
    path = Path(SESSION_FILE)
    temporary_path = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(temporary_path, path)
        return True
    except (OSError, TypeError, ValueError):
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _build_session_data(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    if args and isinstance(args[0], dict):
        data = dict(args[0])
    else:
        positional_names = ("login", "password", "server", "account", "broker")
        data = dict(kwargs)
        for name, value in zip(positional_names, args):
            data.setdefault(name, value)
    return _without_sensitive_values(data)


def save_session(*args: Any, **kwargs: Any) -> bool:
    """Save non-sensitive dashboard preferences; credentials never enter JSON."""
    data = _build_session_data(args, kwargs)

    capital = float(data.get("capital", 1000.0))
    lock_profit = float(data.get("lock_profit", 5.0))
    supplied_lock_pct = data.get("lock_pct")
    lock_pct = (
        float(supplied_lock_pct)
        if supplied_lock_pct is not None
        else (lock_profit / max(capital, 1e-9)) * 100.0
    )
    refresh_interval = int(data.get("refresh_interval", 5))

    data.update(
        {
            "capital": capital,
            "daily_target_pct": float(data.get("daily_target_pct", 1.0)),
            "lock_profit": lock_profit,
            "lock_pct": lock_pct,
            "refresh_interval": max(3, min(refresh_interval, 30)),
            "btc_enabled": bool(data.get("btc_enabled", True)),
            "remember_password": bool(data.get("remember_password", False)),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return _write_preferences(data)


def load_session() -> dict[str, Any] | None:
    """Load preferences and migrate legacy credential-bearing sessions in place."""
    path = Path(SESSION_FILE)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(loaded, dict):
        return None

    sanitized = _without_sensitive_values(loaded)
    if sanitized != loaded:
        if not _write_preferences(sanitized):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    return sanitized


def clear_session(
    *,
    forget_credentials: bool = True,
    login: object | None = None,
    server: object | None = None,
) -> None:
    """Remove preferences and, by default, any remembered OS-keyring password."""
    session = load_session() or {}
    if forget_credentials:
        delete_password(login or session.get("login"), server or session.get("server"))
    try:
        Path(SESSION_FILE).unlink(missing_ok=True)
    except OSError:
        pass
