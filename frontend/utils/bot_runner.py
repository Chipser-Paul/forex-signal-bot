from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from app_security.models import MT5Credentials
from app_security.redaction import redact_text


ROOT_DIR = Path(__file__).resolve().parents[2]
PROCESS_FILE = Path(__file__).resolve().parent / ".bot_process.json"
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "ui_bot.log"


def _load_process() -> dict[str, Any]:
    if not PROCESS_FILE.exists():
        return {}
    try:
        with open(PROCESS_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def _save_process(data: dict[str, Any]) -> None:
    with open(PROCESS_FILE, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def _clear_process() -> None:
    if PROCESS_FILE.exists():
        PROCESS_FILE.unlink()


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def get_bot_status() -> dict[str, Any]:
    data = _load_process()
    pid = int(data.get("pid", 0) or 0)
    running = _is_pid_running(pid)
    if not running:
        return {"running": False, "pid": None, "started_at": None, "cmd": None}
    return {
        "running": True,
        "pid": pid,
        "started_at": data.get("started_at"),
        "cmd": data.get("cmd"),
    }


def start_bot(capital: float, credentials: MT5Credentials) -> tuple[bool, str]:
    status = get_bot_status()
    if status["running"]:
        return False, "Bot is already running."
    if not credentials.login or not credentials.password or not credentials.server:
        return False, "Authenticated MT5 credentials are required."

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(ROOT_DIR / "main.py")]
    try:
        env = os.environ.copy()
        env.pop("APP_ACCESS_TOKEN", None)
        env.update(
            {
                "BOT_CAPITAL": str(capital),
                "MT5_LOGIN": credentials.login,
                "MT5_PASSWORD": credentials.password,
                "MT5_SERVER": credentials.server,
                "EXPECTED_MT5_LOGIN": credentials.login,
                "EXPECTED_MT5_SERVER": credentials.server,
            }
        )
        with open(LOG_FILE, "a", encoding="utf-8") as log_handle:
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=log_handle,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
    except Exception as exc:
        safe_error = redact_text(exc, (credentials.password,))
        return False, f"Failed to start bot safely: {safe_error}"

    _save_process(
        {
            "pid": proc.pid,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "cmd": " ".join(cmd),
        }
    )
    return True, "Bot started."


def stop_bot() -> tuple[bool, str]:
    data = _load_process()
    pid = int(data.get("pid", 0) or 0)
    if not pid:
        _clear_process()
        return False, "No bot process was recorded."

    if not _is_pid_running(pid):
        _clear_process()
        return False, "Bot is not running."

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            os.kill(pid, 15)
    except Exception as exc:
        return False, f"Failed to stop bot: {exc}"

    _clear_process()
    return True, "Bot stopped."
