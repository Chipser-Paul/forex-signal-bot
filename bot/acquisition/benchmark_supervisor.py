from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .journal import BenchmarkJournal, BoundedSanitizedLog
from .models import AcquisitionError


STEP_TIMEOUT_SECONDS = {
    "MT5_IMPORT": 60.0,
    "MT5_INITIALIZE": 180.0,
    "REQUEST": 600.0,
    "NORMALIZATION": 120.0,
    "GZIP_WRITE": 180.0,
    "PARQUET_WRITE": 180.0,
    "HASH_VERIFICATION": 180.0,
    "READBACK": 180.0,
}
STAGE_WALL_CLOCK_SECONDS = 20.0 * 60.0
POLL_SECONDS = 5.0
SUPERVISOR_HEARTBEAT_SECONDS = 15.0
GRACEFUL_SHUTDOWN_SECONDS = 10.0
FORCED_SHUTDOWN_SECONDS = 5.0
_OPERATION_EVENTS = {
    "MT5_IMPORT_STARTED": ("MT5_IMPORT", "MT5_IMPORT_COMPLETED"),
    "MT5_INITIALIZE_STARTED": ("MT5_INITIALIZE", "MT5_INITIALIZED"),
    "REQUEST_STARTED": ("REQUEST", "REQUEST_COMPLETED"),
    "PROBE_INTERVAL_STARTED": ("REQUEST", "PROBE_INTERVAL_COMPLETED"),
    "NORMALIZATION_STARTED": ("NORMALIZATION", "NORMALIZATION_COMPLETED"),
    "GZIP_WRITE_STARTED": ("GZIP_WRITE", "GZIP_WRITE_COMPLETED"),
    "PARQUET_WRITE_STARTED": ("PARQUET_WRITE", "PARQUET_WRITE_COMPLETED"),
    "HASH_VERIFICATION_STARTED": ("HASH_VERIFICATION", "HASH_VERIFICATION_COMPLETED"),
    "READBACK_STARTED": ("READBACK", "READBACK_COMPLETED"),
}


@dataclass(frozen=True)
class SupervisorResult:
    exit_code: int
    timed_out: bool
    final_event: str
    worker_exit_code: int | None = None
    supervisor_exit_code: int | None = None
    heartbeat_count: int = 0


def _drain(stream, sink: BoundedSanitizedLog) -> None:
    try:
        sink.consume(stream)
    finally:
        stream.close()


def _active_operation(records: Sequence[Mapping[str, object]]) -> tuple[str, float] | None:
    active: dict[str, tuple[str, float]] = {}
    for record in records:
        event = str(record.get("event", ""))
        if event in _OPERATION_EVENTS:
            operation, completed = _OPERATION_EVENTS[event]
            active[operation] = (completed, float(record["elapsed_monotonic_seconds"]))
            continue
        for operation, (completed, _started) in tuple(active.items()):
            if event == completed:
                active.pop(operation, None)
    if not active:
        return None
    operation, (_completed, started) = list(active.items())[-1]
    return operation, started


def _record_termination(journal: BenchmarkJournal, worker_pid: int, status: str, action: str) -> None:
    journal.append(
        "TERMINATION_DECISION",
        status=status,
        details={"worker_pid": worker_pid, "termination_action": action, "origin": "SUPERVISOR"},
    )


def _interrupt_child(process: subprocess.Popen[str], journal: BenchmarkJournal) -> None:
    worker_pid = int(getattr(process, "pid", 0) or 0)
    _record_termination(journal, worker_pid, "GRACEFUL_INTERRUPT", "INTERRUPT")
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGINT)
        process.wait(timeout=GRACEFUL_SHUTDOWN_SECONDS)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    _record_termination(journal, worker_pid, "TERMINATE_CHILD", "TERMINATE")
    try:
        process.terminate()
        process.wait(timeout=FORCED_SHUTDOWN_SECONDS)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    _record_termination(journal, worker_pid, "KILL_CHILD", "KILL")
    process.kill()
    process.wait(timeout=FORCED_SHUTDOWN_SECONDS)


def _record_supervisor_exit(journal: BenchmarkJournal, supervisor_pid: int, exit_code: int) -> None:
    journal.append(
        "SUPERVISOR_EXIT_RECORDED",
        status="RECORDED",
        exit_status=exit_code,
        details={"supervisor_pid": supervisor_pid, "supervisor_exit_status": exit_code},
    )


def supervise_benchmark_child(
    command: Sequence[str],
    journal: BenchmarkJournal,
    *,
    environment: Mapping[str, str],
    poll_seconds: float = POLL_SECONDS,
    heartbeat_seconds: float = SUPERVISOR_HEARTBEAT_SECONDS,
    stage_wall_clock_seconds: float = STAGE_WALL_CLOCK_SECONDS,
    step_timeouts: Mapping[str, float] = STEP_TIMEOUT_SECONDS,
) -> SupervisorResult:
    if poll_seconds <= 0 or poll_seconds > 30 or heartbeat_seconds <= 0 or heartbeat_seconds > 20:
        raise AcquisitionError("benchmark supervisor timing is invalid")
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    stdout_log = BoundedSanitizedLog(journal.run_dir / "stdout.log")
    stderr_log = BoundedSanitizedLog(journal.run_dir / "stderr.log")
    supervisor_pid = os.getpid()
    journal.append(
        "SUPERVISOR_STARTED",
        status="RUNNING",
        details={"supervisor_pid": supervisor_pid, "origin": "SUPERVISOR"},
    )
    try:
        process = subprocess.Popen(
            list(command),
            cwd=Path(__file__).resolve().parents[2],
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            creationflags=creation_flags,
        )
    except OSError:
        journal.append("RUN_FAILED", status="FAILED", error_category="CHILD_LAUNCH_FAILED", exit_status=-1)
        _record_supervisor_exit(journal, supervisor_pid, -1)
        return SupervisorResult(-1, False, "RUN_FAILED", None, -1, 0)
    if process.stdout is None or process.stderr is None:
        _interrupt_child(process, journal)
        journal.append("RUN_FAILED", status="FAILED", error_category="CHILD_CAPTURE_FAILED", exit_status=-1)
        _record_supervisor_exit(journal, supervisor_pid, -1)
        return SupervisorResult(-1, False, "RUN_FAILED", process.returncode, -1, 0)

    worker_pid = int(getattr(process, "pid", 0) or 0)
    journal.append(
        "WORKER_STARTED",
        status="RUNNING",
        details={"worker_pid": worker_pid, "origin": "SUPERVISOR"},
    )
    readers = (
        threading.Thread(target=_drain, args=(process.stdout, stdout_log), daemon=True),
        threading.Thread(target=_drain, args=(process.stderr, stderr_log), daemon=True),
    )
    for reader in readers:
        reader.start()

    last_sequence = 0
    timed_out = False
    timeout_category = ""
    started = time.monotonic()
    last_heartbeat = started
    heartbeat_count = 0
    interrupted = False
    try:
        while process.poll() is None:
            records = journal.records()
            for record in records[last_sequence:]:
                print(
                    json.dumps(
                        {
                            "status": "BENCHMARK_PROGRESS",
                            "run_id": journal.run_id,
                            "event": record["event"],
                            "elapsed_seconds": record["elapsed_monotonic_seconds"],
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    flush=True,
                )
            last_sequence = len(records)
            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_seconds:
                active = _active_operation(records)
                operation = active[0] if active is not None else "SUPERVISING"
                journal.append(
                    "HEARTBEAT",
                    status=operation,
                    details={"origin": "SUPERVISOR", "operation": operation, "worker_pid": worker_pid},
                )
                heartbeat_count += 1
                last_heartbeat = now
            if now - started > stage_wall_clock_seconds:
                timed_out = True
                timeout_category = "STAGE_WALL_CLOCK_TIMEOUT"
            active = _active_operation(records)
            if active is not None:
                operation, operation_started = active
                run_elapsed = max(time.monotonic() - journal.started_monotonic, 0.0)
                if run_elapsed - operation_started > float(step_timeouts[operation]):
                    timed_out = True
                    timeout_category = f"{operation}_TIMEOUT"
            if timed_out:
                _interrupt_child(process, journal)
                break
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        interrupted = True
        _interrupt_child(process, journal)

    if interrupted and not journal.state().get("terminal_event"):
        journal.append("RUN_INTERRUPTED", status="INTERRUPTED", error_category="RUN_INTERRUPTED")
    for reader in readers:
        reader.join(timeout=5)
    worker_exit = int(process.returncode if process.returncode is not None else -1)
    journal.append(
        "WORKER_EXIT_RECORDED",
        status="RECORDED",
        exit_status=worker_exit,
        details={"worker_pid": worker_pid, "worker_exit_status": worker_exit, "origin": "SUPERVISOR"},
    )
    journal.append("PROCESS_EXIT_RECORDED", status="RECORDED", exit_status=worker_exit)

    if interrupted:
        supervisor_exit = 130
        _record_supervisor_exit(journal, supervisor_pid, supervisor_exit)
        return SupervisorResult(supervisor_exit, False, "RUN_INTERRUPTED", worker_exit, supervisor_exit, heartbeat_count)
    if timed_out:
        journal.append(
            "RUN_TIMED_OUT", status="TIMED_OUT", error_category=timeout_category, exit_status=worker_exit
        )
        supervisor_exit = 124
        _record_supervisor_exit(journal, supervisor_pid, supervisor_exit)
        return SupervisorResult(supervisor_exit, True, "RUN_TIMED_OUT", worker_exit, supervisor_exit, heartbeat_count)

    terminal = str(journal.state().get("terminal_event") or "")
    if not terminal:
        journal.append(
            "RUN_FAILED",
            status="FAILED",
            error_category="CHILD_EXIT_WITHOUT_TERMINAL_STATE",
            exit_status=worker_exit,
        )
        terminal = "RUN_FAILED"
    supervisor_exit = 0 if terminal == "RUN_COMPLETED" and worker_exit == 0 else (worker_exit or 2)
    _record_supervisor_exit(journal, supervisor_pid, supervisor_exit)
    return SupervisorResult(supervisor_exit, False, terminal, worker_exit, supervisor_exit, heartbeat_count)
