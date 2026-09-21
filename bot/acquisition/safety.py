from __future__ import annotations

import csv
import io
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


SENSITIVE_ENV_TOKENS = (
    "PASSWORD", "PASSWD", "SECRET", "TOKEN", "API_KEY", "APIKEY",
    "MT5_LOGIN", "MT5_SERVER", "ACCOUNT_LOGIN", "PRIVATE_KEY",
)
AMBIGUOUS_PROCESS_IMAGES = frozenset({
    "python.exe", "pythonw.exe", "streamlit.exe", "forex-signal-bot.exe", "bot.exe",
})


@dataclass(frozen=True)
class ProcessSafety:
    safe: bool
    reason_code: str
    ambiguous_process_count: int


@dataclass(frozen=True)
class ProjectControlSafety:
    safe: bool
    reason_code: str
    control_state: str
    recorded_pid_active: bool


def strip_sensitive_environment(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if environment is None else environment
    return {
        key: source[key]
        for key in source
        if not any(token in key.upper() for token in SENSITIVE_ENV_TOKENS)
    }


def scrub_current_environment() -> tuple[str, ...]:
    removed = tuple(
        key for key in tuple(os.environ)
        if any(token in key.upper() for token in SENSITIVE_ENV_TOKENS)
    )
    for key in removed:
        os.environ.pop(key, None)
    return tuple(sorted(removed))


def windows_process_snapshot() -> tuple[tuple[int, str], ...]:
    """Return only process identifiers and image names; never command lines."""
    completed = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
        env=strip_sensitive_environment(),
    )
    rows: list[tuple[int, str]] = []
    for row in csv.reader(io.StringIO(completed.stdout)):
        if len(row) < 2:
            continue
        try:
            rows.append((int(row[1]), row[0].strip().lower()))
        except ValueError:
            continue
    return tuple(rows)


def assess_process_safety(
    processes: Iterable[tuple[int, str]],
    *,
    current_pid: int | None = None,
) -> ProcessSafety:
    own_pid = os.getpid() if current_pid is None else current_pid
    ambiguous = sum(
        1
        for pid, image in processes
        if pid != own_pid and image.strip().lower() in AMBIGUOUS_PROCESS_IMAGES
    )
    if ambiguous:
        return ProcessSafety(False, "ACTIVE_OR_AMBIGUOUS_BOT_PROCESS", ambiguous)
    return ProcessSafety(True, "NO_AMBIGUOUS_BOT_PROCESS_DETECTED", 0)


def assess_project_control_safety(
    owner_worktree: Path,
    processes: Iterable[tuple[int, str]],
) -> ProjectControlSafety:
    """Validate official dashboard state without exposing process details."""
    frontend = Path(owner_worktree) / "frontend" / "utils"
    control_path = frontend / ".bot_state.json"
    process_path = frontend / ".bot_process.json"
    try:
        with control_path.open("r", encoding="utf-8") as handle:
            control_payload = json.load(handle)
        if not isinstance(control_payload, dict):
            raise ValueError("invalid control shape")
        state = str(control_payload.get("state", "")).strip().lower()
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return ProjectControlSafety(False, "PROJECT_CONTROL_STATE_UNAVAILABLE", "UNKNOWN", False)
    if state != "stopped":
        return ProjectControlSafety(False, "PROJECT_CONTROL_STATE_NOT_STOPPED", state.upper() if state in {"running", "paused"} else "UNKNOWN", False)

    recorded_pid = 0
    if process_path.exists():
        try:
            with process_path.open("r", encoding="utf-8") as handle:
                process_payload = json.load(handle)
            if not isinstance(process_payload, dict):
                raise ValueError("invalid process shape")
            recorded_pid = int(process_payload.get("pid", 0) or 0)
            if recorded_pid <= 0:
                raise ValueError("invalid recorded process identity")
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return ProjectControlSafety(False, "PROJECT_PROCESS_STATE_INVALID", "STOPPED", False)
    active_pids = {int(pid) for pid, _image in processes}
    recorded_active = recorded_pid > 0 and recorded_pid in active_pids
    if recorded_active:
        return ProjectControlSafety(False, "RECORDED_BOT_PID_ACTIVE", "STOPPED", True)
    return ProjectControlSafety(True, "PROJECT_RECORDED_STOPPED", "STOPPED", False)
