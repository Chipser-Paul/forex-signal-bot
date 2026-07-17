from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
PROCESS_FILE = Path(__file__).resolve().parent / ".ui_process.json"
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "ui_frontend.log"


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


def get_ui_status() -> dict[str, Any]:
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


def start_ui(port: int = 8502) -> tuple[bool, str]:
    status = get_ui_status()
    if status["running"]:
        return False, "UI launcher is already running."

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ROOT_DIR / "frontend" / "app.py"),
        "--server.port",
        str(port),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=open(LOG_FILE, "a", encoding="utf-8"),
            stderr=open(LOG_FILE, "a", encoding="utf-8"),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    except Exception as exc:
        return False, f"Failed to start UI: {exc}"

    _save_process(
        {
            "pid": proc.pid,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "cmd": " ".join(cmd),
            "port": port,
        }
    )
    return True, f"UI started on port {port}."


def stop_ui() -> tuple[bool, str]:
    data = _load_process()
    pid = int(data.get("pid", 0) or 0)
    if not pid:
        _clear_process()
        return False, "No UI process was recorded."

    if not _is_pid_running(pid):
        _clear_process()
        return False, "UI is not running."

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
        return False, f"Failed to stop UI: {exc}"

    _clear_process()
    return True, "UI stopped."
