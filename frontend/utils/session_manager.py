import json
import os
from datetime import datetime

# Ensure consistent session file path
SESSION_FILE = os.path.join(os.path.dirname(__file__), ".session.json")


def save_session(*args, **kwargs) -> None:
    """
    Save session data to disk
    Supports optional trading settings:
      - capital: float
      - daily_target_pct: float
      - lock_profit: float
      - lock_pct: float (automatically calculated if not provided)
      - refresh_interval: int
      - btc_enabled: bool
    """
    if args and isinstance(args[0], dict):
        data = args[0]
    else:
        login = kwargs.get("login") or (args[0] if len(args) > 0 else None)
        password = kwargs.get("password") or (args[1] if len(args) > 1 else None)
        server = kwargs.get("server") or (args[2] if len(args) > 2 else None)
        account = kwargs.get("account") or (args[3] if len(args) > 3 else None)
        broker = kwargs.get("broker") or (args[4] if len(args) > 4 else None)

        data = {
            "login": str(login),
            "password": str(password),
            "server": str(server),
            "account": account,
            "broker": broker,
        }

    # Optional trading settings
    capital = kwargs.get("capital", data.get("capital", 1000.0))
    lock_profit = kwargs.get("lock_profit", data.get("lock_profit", 5.0))
    lock_pct = kwargs.get("lock_pct") or (lock_profit / capital * 100.0)
    daily_target_pct = kwargs.get("daily_target_pct", data.get("daily_target_pct", 1.0))
    refresh_interval = int(kwargs.get("refresh_interval", data.get("refresh_interval", 5)))
    btc_enabled = bool(kwargs.get("btc_enabled", data.get("btc_enabled", True)))
    data.update({
        "capital": capital,
        "daily_target_pct": daily_target_pct,
        "lock_profit": lock_profit,
        "lock_pct": lock_pct,
        "refresh_interval": max(3, min(refresh_interval, 30)),
        "btc_enabled": btc_enabled,
    })

    data["saved_at"] = datetime.utcnow().isoformat()

    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def load_session() -> dict | None:
    """Load session data from disk"""
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def clear_session() -> None:
    """Remove session file"""
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    except Exception:
        pass
