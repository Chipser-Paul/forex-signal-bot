from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, TextIO

from filelock import FileLock

from app_security.redaction import redact_text
from bot.validation.models import canonical_data

from .models import AcquisitionError
from .storage import atomic_json


UTC = timezone.utc
JOURNAL_SCHEMA_VERSION = "phase8b.benchmark-journal.v1"
JOURNAL_EVENTS = frozenset({
    "RUN_PREPARED",
    "SAFETY_CHECK_STARTED",
    "SAFETY_CHECK_PASSED",
    "DEPENDENCY_CHECK_PASSED",
    "MT5_IMPORT_STARTED",
    "MT5_IMPORT_COMPLETED",
    "MT5_INITIALIZE_STARTED",
    "MT5_INITIALIZED",
    "REQUEST_STARTED",
    "REQUEST_COMPLETED",
    "NORMALIZATION_STARTED",
    "NORMALIZATION_COMPLETED",
    "GZIP_WRITE_STARTED",
    "GZIP_WRITE_COMPLETED",
    "PARQUET_WRITE_STARTED",
    "PARQUET_WRITE_COMPLETED",
    "HASH_VERIFICATION_STARTED",
    "HASH_VERIFICATION_COMPLETED",
    "READBACK_STARTED",
    "READBACK_COMPLETED",
    "MT5_SHUTDOWN_STARTED",
    "MT5_SHUTDOWN_COMPLETED",
    "PROCESS_EXIT_RECORDED",
    "SUPERVISOR_STARTED",
    "WORKER_STARTED",
    "WORKER_EXIT_RECORDED",
    "SUPERVISOR_EXIT_RECORDED",
    "TERMINATION_DECISION",
    "HEARTBEAT",
    "PROBE_INTERVAL_STARTED",
    "PROBE_INTERVAL_COMPLETED",
    "PROBE_COMPLETED",
    "BENCHMARK_CONDITION_EVALUATED",
    "REQUEST_RESULT_CLASSIFIED",
    "RUN_COMPLETED",
    "RUN_FAILED",
    "RUN_TIMED_OUT",
    "RUN_INTERRUPTED",
})
TERMINAL_EVENTS = frozenset({"RUN_COMPLETED", "RUN_FAILED", "RUN_TIMED_OUT", "RUN_INTERRUPTED"})
_SAFE_TOKEN = re.compile(r"^[A-Z0-9_.:-]{1,96}$")
_WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^\s,;\"']+")
_CREDENTIAL_VALUE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|mt5_login|mt5_server)\s*[:=]\s*\S+"
)
_LONG_NUMBER = re.compile(r"\b\d{6,}\b")
_DETAIL_KEYS = frozenset({
    "pid",
    "supervisor_pid",
    "worker_pid",
    "worker_exit_status",
    "supervisor_exit_status",
    "origin",
    "operation",
    "termination_action",
    "interval_id",
    "request_kind",
    "response_kind",
    "row_count",
    "mt5_error_code",
    "requested_start",
    "requested_end",
    "benchmark_authorized",
})


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _safe_token(value: str, name: str) -> str:
    token = str(value).strip().upper()
    if not _SAFE_TOKEN.fullmatch(token):
        raise AcquisitionError(f"benchmark {name} is invalid")
    return token


def _record_hash(record: dict[str, object]) -> str:
    payload = json.dumps(canonical_data(record), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def sanitize_diagnostic_text(value: object) -> str:
    text = redact_text(value or "")
    text = _CREDENTIAL_VALUE.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    text = _WINDOWS_PATH.sub("<redacted-path>", text)
    text = _LONG_NUMBER.sub("<redacted-number>", text)
    return text[:4096]


def stable_error_category(error: BaseException) -> str:
    if isinstance(error, (TimeoutError, subprocess_timeout_type())):
        return "STEP_TIMEOUT"
    if isinstance(error, KeyboardInterrupt):
        return "RUN_INTERRUPTED"
    if isinstance(error, AcquisitionError):
        message = str(error).lower()
        if "api error" in message:
            return "API_ERROR"
        if "disk" in message or "output budget" in message:
            return "DISK_SAFETY_BLOCK"
        if "empty" in message or "no quote" in message or "unavailable" in message:
            return "DATA_UNAVAILABLE"
        if "preceding" in message or "prerequisite" in message:
            return "STAGE_PREREQUISITE_MISSING"
        if "incomplete" in message or "completion" in message or "hash" in message:
            return "ARTIFACT_VERIFICATION_FAILED"
        if "initial" in message or "terminal" in message:
            return "MT5_INITIALIZATION_FAILED"
        return "ACQUISITION_VALIDATION_FAILED"
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return "DEPENDENCY_IMPORT_FAILED"
    if isinstance(error, OSError):
        return "SYSTEM_IO_FAILED"
    return "INTERNAL_ERROR"


def subprocess_timeout_type() -> type[BaseException]:
    # Avoid importing subprocess on the normal journal path.
    import subprocess

    return subprocess.TimeoutExpired


class BenchmarkJournal:
    def __init__(self, run_dir: Path, metadata: dict[str, object]) -> None:
        self.run_dir = Path(run_dir)
        self.metadata = metadata
        self.run_id = str(metadata["run_id"])
        self.benchmark_stage = str(metadata["benchmark_stage"])
        self.started_monotonic = float(metadata["started_monotonic"])
        self.journal_path = self.run_dir / "run_journal.jsonl"
        self.state_path = self.run_dir / "run_state.json"
        self._lock_path = str(self.journal_path) + ".lock"

    @classmethod
    def create(
        cls,
        output_root: Path,
        benchmark_stage: str,
        *,
        run_id: str | None = None,
        now: datetime | None = None,
    ) -> "BenchmarkJournal":
        stage = benchmark_stage.strip().lower()
        if stage not in {"hour", "day", "week", "coverage"}:
            raise AcquisitionError("benchmark stage is invalid")
        created = (now or _utc_now()).astimezone(UTC)
        identity = run_id or f"{stage}-{created:%Y%m%dt%H%M%S}z-{uuid.uuid4().hex[:10]}"
        if not re.fullmatch(r"[a-z0-9-]{8,80}", identity):
            raise AcquisitionError("benchmark run identity is invalid")
        family = "probes" if stage == "coverage" else "benchmarks"
        run_dir = Path(output_root) / family / "development-20240805-20240812" / "runs" / stage / identity
        run_dir.mkdir(parents=True, exist_ok=False)
        metadata = {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "run_id": identity,
            "benchmark_stage": stage,
            "created_at": created,
            "started_monotonic": time.monotonic(),
        }
        atomic_json(run_dir / "run_metadata.json", metadata)
        journal = cls(run_dir, canonical_data(metadata))
        journal.append("RUN_PREPARED", status="PREPARED")
        return journal

    @classmethod
    def open(cls, run_dir: Path) -> "BenchmarkJournal":
        path = Path(run_dir) / "run_metadata.json"
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise AcquisitionError("benchmark run metadata is unavailable") from exc
        if metadata.get("schema_version") != JOURNAL_SCHEMA_VERSION:
            raise AcquisitionError("benchmark run metadata schema is incompatible")
        return cls(Path(run_dir), metadata)

    def append(
        self,
        event: str,
        *,
        status: str,
        error_category: str | None = None,
        exit_status: int | None = None,
        details: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        event_name = _safe_token(event, "event")
        if event_name not in JOURNAL_EVENTS:
            raise AcquisitionError("benchmark journal event is unsupported")
        status_name = _safe_token(status, "status")
        category = None if error_category is None else _safe_token(error_category, "error category")
        safe_details: dict[str, object] = {}
        for key, value in (details or {}).items():
            if key not in _DETAIL_KEYS:
                raise AcquisitionError("benchmark journal detail is unsupported")
            if isinstance(value, str):
                safe_details[key] = sanitize_diagnostic_text(value)
            elif value is None or isinstance(value, (bool, int, float)):
                safe_details[key] = value
            else:
                raise AcquisitionError("benchmark journal detail is invalid")
        with FileLock(self._lock_path, timeout=15):
            records = self._read_locked(repair_tail=True)
            previous = None if not records else str(records[-1]["record_sha256"])
            body: dict[str, object] = {
                "schema_version": JOURNAL_SCHEMA_VERSION,
                "run_id": self.run_id,
                "benchmark_stage": self.benchmark_stage,
                "sequence": len(records) + 1,
                "event": event_name,
                "timestamp_utc": _utc_now(),
                "elapsed_monotonic_seconds": max(time.monotonic() - self.started_monotonic, 0.0),
                "status": status_name,
                "error_category": category,
                "exit_status": exit_status,
                "previous_record_sha256": previous,
                "details": safe_details,
            }
            body["record_sha256"] = _record_hash(body)
            line = json.dumps(canonical_data(body), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            with self.journal_path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            prior_terminal = next(
                (item["event"] for item in reversed(records) if item["event"] in TERMINAL_EVENTS),
                None,
            )
            prior_exit = next(
                (item["exit_status"] for item in reversed(records) if item.get("exit_status") is not None),
                None,
            )
            terminal = event_name if event_name in TERMINAL_EVENTS else prior_terminal
            state = {
                "schema_version": JOURNAL_SCHEMA_VERSION,
                "run_id": self.run_id,
                "benchmark_stage": self.benchmark_stage,
                "last_sequence": body["sequence"],
                "last_event": event_name,
                "last_record_sha256": body["record_sha256"],
                "terminal_event": terminal,
                "exit_status": exit_status if exit_status is not None else prior_exit,
            }
            if event_name == "WORKER_EXIT_RECORDED":
                state["worker_exit_status"] = exit_status
            elif records:
                previous_worker = next(
                    (item.get("exit_status") for item in reversed(records) if item["event"] == "WORKER_EXIT_RECORDED"),
                    None,
                )
                if previous_worker is not None:
                    state["worker_exit_status"] = previous_worker
            if event_name == "SUPERVISOR_EXIT_RECORDED":
                state["supervisor_exit_status"] = exit_status
            elif records:
                previous_supervisor = next(
                    (item.get("exit_status") for item in reversed(records) if item["event"] == "SUPERVISOR_EXIT_RECORDED"),
                    None,
                )
                if previous_supervisor is not None:
                    state["supervisor_exit_status"] = previous_supervisor
            atomic_json(self.state_path, state, refuse_overwrite=False)
            return body

    def records(self) -> tuple[dict[str, object], ...]:
        with FileLock(self._lock_path, timeout=15):
            return tuple(self._read_locked(repair_tail=False))

    def state(self) -> dict[str, object]:
        if not self.state_path.exists():
            return {}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise AcquisitionError("benchmark run state is malformed") from exc
        return value if isinstance(value, dict) else {}

    def _read_locked(self, *, repair_tail: bool) -> list[dict[str, object]]:
        if not self.journal_path.exists():
            return []
        raw = self.journal_path.read_bytes()
        lines = raw.splitlines(keepends=True)
        records: list[dict[str, object]] = []
        valid_bytes = 0
        previous = None
        for index, line in enumerate(lines):
            try:
                record = json.loads(line.decode("utf-8"))
                claimed_hash = str(record.pop("record_sha256"))
                if (
                    record.get("schema_version") != JOURNAL_SCHEMA_VERSION
                    or record.get("run_id") != self.run_id
                    or record.get("benchmark_stage") != self.benchmark_stage
                    or int(record.get("sequence", -1)) != index + 1
                    or record.get("previous_record_sha256") != previous
                    or _record_hash(record) != claimed_hash
                ):
                    raise ValueError("journal chain mismatch")
                record["record_sha256"] = claimed_hash
                records.append(record)
                previous = claimed_hash
                valid_bytes += len(line)
            except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
                if repair_tail and index == len(lines) - 1:
                    with self.journal_path.open("r+b") as handle:
                        handle.truncate(valid_bytes)
                        handle.flush()
                        os.fsync(handle.fileno())
                    break
                raise AcquisitionError("benchmark journal is malformed") from None
        return records


class JournalHeartbeat:
    def __init__(self, journal: BenchmarkJournal, operation: str, *, interval_seconds: float = 15.0) -> None:
        if interval_seconds <= 0 or interval_seconds > 30:
            raise AcquisitionError("heartbeat interval must be within 30 seconds")
        self.journal = journal
        self.operation = _safe_token(operation, "heartbeat operation")
        self.interval_seconds = float(interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "JournalHeartbeat":
        self._thread = threading.Thread(target=self._run, name="benchmark-heartbeat", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=min(self.interval_seconds + 1.0, 31.0))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.journal.append("HEARTBEAT", status=self.operation)
            except (AcquisitionError, OSError):
                return


class BoundedSanitizedLog:
    def __init__(self, path: Path, *, maximum_bytes: int = 256 * 1024) -> None:
        self.path = Path(path)
        self.maximum_bytes = int(maximum_bytes)
        if self.maximum_bytes < 1024:
            raise AcquisitionError("benchmark log limit is too small")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        self._lock = threading.Lock()

    def consume(self, stream: TextIO) -> None:
        for line in iter(stream.readline, ""):
            self.write(line)
        stream.close()

    def write(self, value: object) -> None:
        encoded = (sanitize_diagnostic_text(value).rstrip("\r\n") + "\n").encode("utf-8")
        with self._lock:
            if self.path.exists() and self.path.stat().st_size + len(encoded) > self.maximum_bytes:
                rotated = self.path.with_suffix(self.path.suffix + ".1")
                rotated.unlink(missing_ok=True)
                os.replace(self.path, rotated)
            with self.path.open("ab") as handle:
                handle.write(encoded[: self.maximum_bytes])
                handle.flush()
                os.fsync(handle.fileno())
