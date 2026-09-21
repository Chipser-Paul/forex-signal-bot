"""Durable, read-only verification for a single normalized Exness Parquet file.

This module is deliberately independent from the MT5 benchmark supervisor.  It
does not load terminal, broker, network, strategy, or credential code.  A
supervisor launches this module in a child process so a failed logical scan has
an auditable terminal result rather than being inferred from process output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from filelock import FileLock, Timeout

from bot.validation.models import canonical_data

from .exness_archive import (
    PARQUET_SCHEMA_VERSION,
    PRICE_QUANTUM,
    _canonical_from_parquet_values,
    exness_tick_schema,
)
from .models import AcquisitionError, EXECUTABLE_SYMBOL
from .storage import atomic_json, file_sha256


PROTOCOL_VERSION = "phase8b.offline-parquet-verifier.v1"
MAX_BATCH_SIZE = 250_000
DEFAULT_BATCH_SIZE = 100_000
DEFAULT_STAGE_TIMEOUT_SECONDS = 30 * 60
DEFAULT_OVERALL_TIMEOUT_SECONDS = 60 * 60
DEFAULT_HEARTBEAT_SECONDS = 15.0
MAX_LOG_BYTES = 64 * 1024
_HEX = re.compile(r"^[0-9a-f]{64}$")
_PERIOD = re.compile(r"^(?P<year>20\d{2})-(?P<month>0[1-9]|1[0-2])$")
_FORBIDDEN_SUFFIXES = {".zip", ".csv", ".gz", ".jsonl"}
_TERMINAL_STATUSES = frozenset({
    "VERIFIED", "PHYSICAL_HASH_MISMATCH", "PHYSICAL_FILE_CHANGED_DURING_SCAN",
    "LOGICAL_HASH_MISMATCH", "SCHEMA_MISMATCH", "SYMBOL_MISMATCH",
    "ROW_COUNT_MISMATCH", "PERIOD_MISMATCH", "ORDERING_INVALID",
    "MALFORMED_ROW", "CHILD_CRASHED", "TIMED_OUT", "RESULT_MISSING",
    "RESULT_INVALID", "CANCELLED",
})
_JOURNAL_EVENTS = frozenset({
    "RUN_PREPARED", "REQUEST_VALIDATED", "CHILD_STARTED", "HEARTBEAT",
    "PHYSICAL_HASH_STARTED", "PHYSICAL_HASH_COMPLETED", "PARQUET_SCAN_STARTED",
    "PARQUET_BATCH_COMPLETED", "PARQUET_SCAN_COMPLETED", "POST_SCAN_HASH_STARTED",
    "POST_SCAN_HASH_COMPLETED", "TERMINAL_RESULT_PUBLISHED",
    "CHILD_LAUNCH_FAILED", "CHILD_EXITED", "RUN_VERIFIED", "RUN_FAILED",
    "RUN_TIMED_OUT",
})


class VerificationError(AcquisitionError):
    """Raised for a malformed offline-verification protocol artifact."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime | None = None) -> str:
    return (value or _utc_now()).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _absolute(path: Path | str, field: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise VerificationError(f"{field} must be an absolute path")
    return candidate.resolve(strict=False)


def _inside(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _sha(value: object) -> str:
    encoded = json.dumps(canonical_data(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _file_identity(path: Path) -> dict[str, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return {"device": int(stat.st_dev), "inode": int(stat.st_ino), "size_bytes": int(stat.st_size)}


def _safe_error(exc: BaseException) -> str:
    """Return a bounded diagnostic without copying potentially sensitive text."""
    name = type(exc).__name__
    message = str(exc).replace("\r", " ").replace("\n", " ")[:160]
    message = re.sub(r"(?i)(password|token|secret|api[_-]?key)\s*[:=]\s*\S+", r"\1=<redacted>", message)
    return f"{name}:{message}" if message else name


@dataclass(frozen=True)
class VerificationRequest:
    protocol_version: str
    run_id: str
    parquet_path: str
    expected_physical_sha256: str
    expected_logical_sha256: str
    expected_schema_identity: str
    expected_symbol: str
    expected_period: str
    expected_row_count: int
    batch_size: int
    stage_timeout_seconds: float
    overall_timeout_seconds: float
    output_directory: str
    code_fingerprint: str

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise VerificationError("REQUEST_PROTOCOL_VERSION_UNSUPPORTED")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", self.run_id):
            raise VerificationError("REQUEST_RUN_ID_INVALID")
        input_path = _absolute(self.parquet_path, "parquet path")
        output_path = _absolute(self.output_directory, "output directory")
        if input_path.suffix.lower() in _FORBIDDEN_SUFFIXES or input_path.suffix.lower() != ".parquet":
            raise VerificationError("REQUEST_INPUT_MUST_BE_PARQUET")
        if _inside(input_path, output_path) or _inside(output_path, input_path):
            raise VerificationError("REQUEST_INPUT_OUTPUT_OVERLAP")
        for field, value in (("physical", self.expected_physical_sha256), ("logical", self.expected_logical_sha256)):
            if not _HEX.fullmatch(value):
                raise VerificationError(f"REQUEST_{field.upper()}_HASH_INVALID")
        if self.expected_schema_identity != PARQUET_SCHEMA_VERSION:
            raise VerificationError("REQUEST_SCHEMA_IDENTITY_UNSUPPORTED")
        if self.expected_symbol != EXECUTABLE_SYMBOL:
            raise VerificationError("REQUEST_SYMBOL_UNSUPPORTED")
        if not _PERIOD.fullmatch(self.expected_period):
            raise VerificationError("REQUEST_PERIOD_INVALID")
        if self.expected_row_count < 0:
            raise VerificationError("REQUEST_ROW_COUNT_INVALID")
        if not 1 <= self.batch_size <= MAX_BATCH_SIZE:
            raise VerificationError("REQUEST_BATCH_SIZE_UNSAFE")
        if not all(math.isfinite(float(value)) and float(value) > 0 for value in (self.stage_timeout_seconds, self.overall_timeout_seconds)):
            raise VerificationError("REQUEST_TIMEOUT_INVALID")
        if float(self.overall_timeout_seconds) < float(self.stage_timeout_seconds):
            raise VerificationError("REQUEST_TIMEOUT_ORDER_INVALID")
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,160}", self.code_fingerprint):
            raise VerificationError("REQUEST_CODE_FINGERPRINT_INVALID")
        object.__setattr__(self, "parquet_path", str(input_path))
        object.__setattr__(self, "output_directory", str(output_path))

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "VerificationRequest":
        expected = {item.name for item in fields(cls)}
        if set(value) != expected:
            raise VerificationError("REQUEST_SCHEMA_FIELDS_INVALID")
        return cls(**value)  # type: ignore[arg-type]

    def request_hash(self) -> str:
        return _sha(asdict(self))


class HashJournal:
    """A small, append-only, hash-chained journal for one verifier run."""

    def __init__(self, path: Path, run_id: str) -> None:
        self.path = Path(path)
        self.run_id = run_id

    def append(self, event: str, payload: Mapping[str, object] | None = None) -> str:
        if event not in _JOURNAL_EVENTS:
            raise VerificationError("JOURNAL_EVENT_UNSUPPORTED")
        safe_payload = canonical_data(dict(payload or {}))
        encoded = json.dumps(safe_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        if len(encoded.encode("utf-8")) > 8192:
            raise VerificationError("JOURNAL_PAYLOAD_TOO_LARGE")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock", timeout=10):
            entries = self.entries()
            sequence = len(entries) + 1
            previous_hash = entries[-1]["entry_hash"] if entries else "0" * 64
            entry = {
                "protocol_version": PROTOCOL_VERSION,
                "run_id": self.run_id,
                "sequence": sequence,
                "event": event,
                "utc_timestamp": _utc_text(),
                "monotonic_seconds": time.monotonic(),
                "payload": safe_payload,
                "previous_hash": previous_hash,
            }
            entry["entry_hash"] = _sha(entry)
            with self.path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return str(entry["entry_hash"])

    def entries(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        entries: list[dict[str, object]] = []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        raise VerificationError("JOURNAL_BLANK_RECORD")
                    entries.append(json.loads(line))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise VerificationError("JOURNAL_INVALID") from exc
        previous = "0" * 64
        for number, entry in enumerate(entries, start=1):
            if (
                entry.get("protocol_version") != PROTOCOL_VERSION
                or entry.get("run_id") != self.run_id
                or entry.get("sequence") != number
                or entry.get("event") not in _JOURNAL_EVENTS
                or entry.get("previous_hash") != previous
            ):
                raise VerificationError("JOURNAL_CHAIN_INVALID")
            supplied = entry.get("entry_hash")
            without_hash = dict(entry)
            without_hash.pop("entry_hash", None)
            if not isinstance(supplied, str) or supplied != _sha(without_hash):
                raise VerificationError("JOURNAL_CHAIN_INVALID")
            previous = supplied
        return entries

    def terminal_hash(self) -> str:
        entries = self.entries()
        return str(entries[-1]["entry_hash"]) if entries else "0" * 64


def _arrow():
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise VerificationError("PARQUET_RUNTIME_UNAVAILABLE") from exc
    return pq


def _period_match(timestamp: datetime, period: str) -> bool:
    match = _PERIOD.fullmatch(period)
    assert match is not None
    return timestamp.year == int(match.group("year")) and timestamp.month == int(match.group("month"))


def _scan(request: VerificationRequest, journal: HashJournal) -> dict[str, object]:
    """Read a Parquet file in bounded batches and return non-sensitive facts."""
    path = Path(request.parquet_path)
    journal.append("PHYSICAL_HASH_STARTED", {"phase": "before_scan"})
    identity_before = _file_identity(path)
    physical_before = file_sha256(path) if path.is_file() else None
    size_before = path.stat().st_size if path.is_file() else None
    journal.append("PHYSICAL_HASH_COMPLETED", {"phase": "before_scan", "sha256": physical_before, "size_bytes": size_before})
    if physical_before != request.expected_physical_sha256:
        return {"status": "PHYSICAL_HASH_MISMATCH", "reason_code": "PHYSICAL_HASH_MISMATCH", "physical_before": physical_before, "size_before": size_before, "identity_before": identity_before}

    pq = _arrow()
    journal.append("PARQUET_SCAN_STARTED", {"batch_size": request.batch_size})
    parquet = pq.ParquetFile(path)
    metadata = parquet.schema_arrow.metadata or {}
    schema_identity = metadata.get(b"schema_version", b"").decode("ascii", errors="replace")
    if parquet.schema_arrow != exness_tick_schema() or schema_identity != request.expected_schema_identity:
        return {"status": "SCHEMA_MISMATCH", "reason_code": "SCHEMA_MISMATCH", "physical_before": physical_before, "size_before": size_before, "identity_before": identity_before, "schema_identity": schema_identity}

    digest = hashlib.sha256()
    row_count = exact_duplicates = conflicting_timestamps = ordering_violations = malformed_rows = crossed_quotes = 0
    batches = peak_batch_bytes = 0
    first: datetime | None = None
    last: datetime | None = None
    previous: datetime | None = None
    timestamp_quotes: set[tuple[Decimal, Decimal]] = set()
    current_timestamp: datetime | None = None
    failure: str | None = None

    for batch in parquet.iter_batches(batch_size=request.batch_size):
        batches += 1
        peak_batch_bytes = max(peak_batch_bytes, int(getattr(batch, "nbytes", 0)))
        columns = batch.to_pydict()
        for index in range(batch.num_rows):
            try:
                symbol = columns["symbol"][index]
                timestamp = columns["timestamp"][index]
                bid = columns["bid"][index]
                ask = columns["ask"][index]
                time_msc = int(columns["time_msc"][index])
                sequence_id = int(columns["sequence_id"][index])
                if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
                    raise ValueError("timestamp")
                timestamp = timestamp.astimezone(timezone.utc)
                bid = Decimal(bid).quantize(PRICE_QUANTUM)
                ask = Decimal(ask).quantize(PRICE_QUANTUM)
                if not bid.is_finite() or not ask.is_finite() or bid <= 0 or ask <= 0:
                    raise ValueError("quote")
                if int(timestamp.timestamp() * 1000) != time_msc:
                    raise ValueError("timestamp")
            except (ArithmeticError, TypeError, ValueError):
                malformed_rows += 1
                failure = "MALFORMED_ROW"
                continue
            if symbol != request.expected_symbol:
                failure = "SYMBOL_MISMATCH"
            if not _period_match(timestamp, request.expected_period):
                failure = "PERIOD_MISMATCH"
            if previous is not None and timestamp < previous:
                ordering_violations += 1
                failure = "ORDERING_INVALID"
            if ask < bid:
                crossed_quotes += 1
                failure = "MALFORMED_ROW"
            if timestamp != current_timestamp:
                current_timestamp = timestamp
                timestamp_quotes.clear()
            quote = (bid, ask)
            if quote in timestamp_quotes:
                exact_duplicates += 1
            elif timestamp_quotes:
                conflicting_timestamps += 1
            timestamp_quotes.add(quote)
            payload = _canonical_from_parquet_values(symbol=symbol, time_msc=time_msc, bid=bid, ask=ask, sequence_id=sequence_id)
            digest.update(payload)
            digest.update(b"\n")
            row_count += 1
            previous = timestamp
            first = first or timestamp
            last = timestamp
        journal.append("PARQUET_BATCH_COMPLETED", {"batch": batches, "rows_scanned": row_count, "peak_batch_bytes": peak_batch_bytes})

    journal.append("PARQUET_SCAN_COMPLETED", {"batches": batches, "rows_scanned": row_count})
    journal.append("POST_SCAN_HASH_STARTED", {})
    identity_after = _file_identity(path)
    physical_after = file_sha256(path) if path.is_file() else None
    size_after = path.stat().st_size if path.is_file() else None
    journal.append("POST_SCAN_HASH_COMPLETED", {"sha256": physical_after, "size_bytes": size_after})
    if physical_after != physical_before or size_after != size_before or identity_after != identity_before:
        status = "PHYSICAL_FILE_CHANGED_DURING_SCAN"
    elif failure is not None:
        status = failure
    elif row_count != request.expected_row_count:
        status = "ROW_COUNT_MISMATCH"
    elif digest.hexdigest() != request.expected_logical_sha256:
        status = "LOGICAL_HASH_MISMATCH"
    else:
        status = "VERIFIED"
    return {
        "status": status,
        "reason_code": status,
        "physical_before": physical_before,
        "physical_after": physical_after,
        "size_before": size_before,
        "size_after": size_after,
        "identity_before": identity_before,
        "identity_after": identity_after,
        "schema_identity": schema_identity,
        "symbol": request.expected_symbol,
        "record_count": row_count,
        "first_timestamp": _utc_text(first) if first else None,
        "last_timestamp": _utc_text(last) if last else None,
        "logical_canonical_sha256": digest.hexdigest(),
        "ordering_violations": ordering_violations,
        "exact_duplicates": exact_duplicates,
        "conflicting_timestamps": conflicting_timestamps,
        "malformed_rows": malformed_rows,
        "crossed_quotes": crossed_quotes,
        "batch_count": batches,
        "peak_batch_bytes": peak_batch_bytes,
    }


def _terminal_paths(output: Path) -> tuple[Path, Path]:
    return output / "terminal-result.json", output / "terminal-result.complete.json"


def _publish_terminal(output: Path, request: VerificationRequest, journal: HashJournal, scan: Mapping[str, object], *, start_utc: str, start_monotonic: float, child_exit_status: int) -> dict[str, object]:
    status = str(scan.get("status", "RESULT_INVALID"))
    if status not in _TERMINAL_STATUSES:
        status = "RESULT_INVALID"
    journal_hash = journal.append("TERMINAL_RESULT_PUBLISHED", {"status": status})
    result = canonical_data({
        "protocol_version": PROTOCOL_VERSION,
        "run_id": request.run_id,
        "status": status,
        "reason_code": str(scan.get("reason_code", status)),
        "request_hash": request.request_hash(),
        "input_file": Path(request.parquet_path).name,
        "expected_physical_sha256": request.expected_physical_sha256,
        "expected_logical_sha256": request.expected_logical_sha256,
        "expected_schema_identity": request.expected_schema_identity,
        "expected_period": request.expected_period,
        "expected_row_count": request.expected_row_count,
        "physical_hash_before": scan.get("physical_before"),
        "physical_hash_after": scan.get("physical_after"),
        "size_before": scan.get("size_before"),
        "size_after": scan.get("size_after"),
        "file_identity_before": scan.get("identity_before"),
        "file_identity_after": scan.get("identity_after"),
        "schema_identity": scan.get("schema_identity"),
        "symbol": scan.get("symbol", request.expected_symbol),
        "row_count": scan.get("record_count", 0),
        "first_timestamp": scan.get("first_timestamp"),
        "last_timestamp": scan.get("last_timestamp"),
        "logical_canonical_sha256": scan.get("logical_canonical_sha256"),
        "ordering_statistics": {"violations": scan.get("ordering_violations", 0)},
        "duplicate_statistics": {"exact": scan.get("exact_duplicates", 0), "conflicting_timestamps": scan.get("conflicting_timestamps", 0)},
        "malformed_statistics": {"rows": scan.get("malformed_rows", 0), "crossed_quotes": scan.get("crossed_quotes", 0)},
        "batch_count": scan.get("batch_count", 0),
        "peak_batch_bytes": scan.get("peak_batch_bytes", 0),
        "start_utc": start_utc,
        "end_utc": _utc_text(),
        "start_monotonic_seconds": start_monotonic,
        "end_monotonic_seconds": time.monotonic(),
        "duration_seconds": time.monotonic() - start_monotonic,
        "child_exit_status": child_exit_status,
        "journal_chain_terminal_hash": journal_hash,
    })
    result_path, completion_path = _terminal_paths(output)
    atomic_json(result_path, result)
    atomic_json(completion_path, {"protocol_version": PROTOCOL_VERSION, "run_id": request.run_id, "result_sha256": file_sha256(result_path), "journal_chain_terminal_hash": journal_hash})
    return result


def child_verify(request_path: Path) -> int:
    """Child entry point. It always tries to leave one durable terminal result."""
    request_raw = json.loads(Path(request_path).read_text(encoding="utf-8"))
    request = VerificationRequest.from_mapping(request_raw)
    output = Path(request.output_directory)
    output.mkdir(parents=True, exist_ok=True)
    journal = HashJournal(output / "worker.journal.jsonl", request.run_id)
    start_utc, start_monotonic = _utc_text(), time.monotonic()
    journal.append("RUN_PREPARED", {"request_hash": request.request_hash()})
    journal.append("REQUEST_VALIDATED", {})
    try:
        scan = _scan(request, journal)
    except BaseException as exc:
        scan = {"status": "CHILD_CRASHED", "reason_code": "CHILD_SCAN_EXCEPTION", "exception": _safe_error(exc)}
    exit_status = 0 if scan.get("status") == "VERIFIED" else 2
    _publish_terminal(output, request, journal, scan, start_utc=start_utc, start_monotonic=start_monotonic, child_exit_status=exit_status)
    return exit_status


def _load_valid_terminal(request: VerificationRequest) -> dict[str, object] | None:
    output = Path(request.output_directory)
    result_path, completion_path = _terminal_paths(output)
    if not result_path.exists() and not completion_path.exists():
        return None
    if not result_path.is_file() or not completion_path.is_file():
        raise VerificationError("RESULT_PARTIAL")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise VerificationError("RESULT_INVALID") from exc
    if (
        result.get("protocol_version") != PROTOCOL_VERSION
        or result.get("run_id") != request.run_id
        or result.get("request_hash") != request.request_hash()
        or completion.get("run_id") != request.run_id
        or completion.get("result_sha256") != file_sha256(result_path)
        or result.get("status") != "VERIFIED"
    ):
        raise VerificationError("RESULT_REUSE_IDENTITY_MISMATCH")
    journal = HashJournal(output / "worker.journal.jsonl", request.run_id)
    entries = journal.entries()
    terminal_events = [entry for entry in entries if entry.get("event") == "TERMINAL_RESULT_PUBLISHED"]
    if len(terminal_events) != 1 or journal.terminal_hash() != result.get("journal_chain_terminal_hash"):
        raise VerificationError("RESULT_JOURNAL_LINK_INVALID")
    return result


class _BoundedDrain(threading.Thread):
    def __init__(self, stream: Any, destination: Path) -> None:
        super().__init__(daemon=True)
        self.stream = stream
        self.destination = destination
        self.total_bytes = 0

    def run(self) -> None:
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        with self.destination.open("wb") as handle:
            while True:
                block = self.stream.read(4096)
                if not block:
                    break
                remaining = max(0, MAX_LOG_BYTES - self.total_bytes)
                if remaining:
                    handle.write(block[:remaining])
                    self.total_bytes += min(len(block), remaining)
            handle.flush()
            os.fsync(handle.fileno())


def _termination(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _child_environment() -> dict[str, str]:
    """Pass only OS/runtime plumbing, never the caller's application secrets."""
    blocked_fragments = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "PRIVATE_KEY")
    blocked_prefixes = ("MT5_", "BOT_", "GROQ_", "TELEGRAM_", "FCM_", "FIREBASE_")
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(blocked_prefixes)
        and not any(fragment in key.upper() for fragment in blocked_fragments)
    }


def supervise_verification(request: VerificationRequest, *, heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_SECONDS, command: list[str] | None = None) -> dict[str, object]:
    """Supervise one child scan; zero exit status never substitutes for a result."""
    if not 10 <= heartbeat_interval_seconds <= 20 and command is None:
        raise VerificationError("HEARTBEAT_INTERVAL_INVALID")
    existing = _load_valid_terminal(request)
    if existing is not None:
        return {"status": "VERIFIED", "reason_code": "IDEMPOTENT_COMPLETED_RUN", "result": existing, "idempotent": True}
    output = Path(request.output_directory)
    output.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(output / "run.lock"), timeout=0)
    try:
        lock.acquire()
    except Timeout as exc:
        raise VerificationError("RUN_CONCURRENT_LOCKED") from exc
    try:
        if [path for path in output.iterdir() if path.name != "run.lock"]:
            raise VerificationError("RUN_DIRECTORY_NONEMPTY")
        request_path = output / "request.json"
        atomic_json(request_path, asdict(request))
        journal = HashJournal(output / "supervisor.journal.jsonl", request.run_id)
        journal.append("RUN_PREPARED", {"request_hash": request.request_hash()})
        journal.append("REQUEST_VALIDATED", {})
        child_command = command or [sys.executable, "-m", "bot.acquisition.offline_verifier", "--child", str(request_path)]
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                child_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                cwd=str(Path(__file__).resolve().parents[2]),
                env=_child_environment(),
            )
        except OSError as exc:
            journal.append("CHILD_LAUNCH_FAILED", {"error": _safe_error(exc)})
            journal.append("RUN_FAILED", {"status": "RESULT_INVALID", "reason_code": "CHILD_LAUNCH_FAILED"})
            summary = {
                "protocol_version": PROTOCOL_VERSION,
                "run_id": request.run_id,
                "status": "RESULT_INVALID",
                "reason_code": "CHILD_LAUNCH_FAILED",
                "child_exit_code": None,
                "result": None,
                "supervisor_journal_hash": journal.terminal_hash(),
                "idempotent": False,
            }
            atomic_json(output / "supervisor-summary.json", summary)
            atomic_json(
                output / "supervisor-summary.complete.json",
                {"run_id": request.run_id, "summary_sha256": file_sha256(output / "supervisor-summary.json")},
            )
            return summary
        assert process.stdout is not None and process.stderr is not None
        stdout = _BoundedDrain(process.stdout, output / "child.stdout.log")
        stderr = _BoundedDrain(process.stderr, output / "child.stderr.log")
        stdout.start(); stderr.start()
        journal.append("CHILD_STARTED", {"pid": process.pid})
        # This is deliberately synchronous: an immediate child crash still has
        # durable liveness evidence independent of child progress or output.
        initial_heartbeat_at = time.monotonic()
        journal.append(
            "HEARTBEAT",
            {"elapsed_seconds": initial_heartbeat_at - started, "child_pid": process.pid, "initial": True},
        )
        deadline = started + request.overall_timeout_seconds
        stage_deadline = started + request.stage_timeout_seconds
        next_heartbeat = initial_heartbeat_at + heartbeat_interval_seconds
        worker_journal = output / "worker.journal.jsonl"
        observed_worker_mtime: int | None = None
        timed_out = False
        while process.poll() is None:
            now = time.monotonic()
            try:
                worker_mtime = worker_journal.stat().st_mtime_ns
            except OSError:
                worker_mtime = None
            if worker_mtime is not None and worker_mtime != observed_worker_mtime:
                observed_worker_mtime = worker_mtime
                stage_deadline = now + request.stage_timeout_seconds
            if now >= deadline or now >= stage_deadline:
                timed_out = True
                journal.append("RUN_TIMED_OUT", {"elapsed_seconds": now - started})
                _termination(process)
                break
            if now >= next_heartbeat:
                journal.append("HEARTBEAT", {"elapsed_seconds": now - started, "child_pid": process.pid})
                next_heartbeat = now + heartbeat_interval_seconds
            time.sleep(0.05)
        exit_code = process.wait(timeout=5)
        stdout.join(timeout=5); stderr.join(timeout=5)
        process.stdout.close()
        process.stderr.close()
        journal.append("CHILD_EXITED", {"exit_code": exit_code, "stdout_bytes": stdout.total_bytes, "stderr_bytes": stderr.total_bytes})
        try:
            result = _load_terminal_any(request)
        except VerificationError as exc:
            result = None
            invalid_reason = str(exc)
        else:
            invalid_reason = None
        if timed_out:
            outcome, reason = "TIMED_OUT", "OVERALL_OR_STAGE_TIMEOUT"
        elif result is None:
            outcome, reason = "RESULT_INVALID", invalid_reason or "RESULT_MISSING"
        elif exit_code != 0 and result.get("status") == "VERIFIED":
            outcome, reason = "RESULT_INVALID", "CHILD_EXIT_CONTRADICTS_RESULT"
        else:
            outcome, reason = str(result.get("status")), str(result.get("reason_code"))
        journal.append("RUN_VERIFIED" if outcome == "VERIFIED" else "RUN_FAILED", {"status": outcome, "reason_code": reason})
        summary = {"protocol_version": PROTOCOL_VERSION, "run_id": request.run_id, "status": outcome, "reason_code": reason, "child_exit_code": exit_code, "result": result, "supervisor_journal_hash": journal.terminal_hash(), "idempotent": False}
        atomic_json(output / "supervisor-summary.json", summary)
        atomic_json(output / "supervisor-summary.complete.json", {"run_id": request.run_id, "summary_sha256": file_sha256(output / "supervisor-summary.json")})
        return summary
    finally:
        lock.release()


def _load_terminal_any(request: VerificationRequest) -> dict[str, object]:
    output = Path(request.output_directory)
    result_path, completion_path = _terminal_paths(output)
    if not result_path.is_file() or not completion_path.is_file():
        raise VerificationError("RESULT_MISSING")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise VerificationError("RESULT_INVALID") from exc
    if (
        result.get("protocol_version") != PROTOCOL_VERSION
        or result.get("run_id") != request.run_id
        or result.get("request_hash") != request.request_hash()
        or completion.get("result_sha256") != file_sha256(result_path)
        or completion.get("run_id") != request.run_id
        or result.get("status") not in _TERMINAL_STATUSES
    ):
        raise VerificationError("RESULT_INVALID")
    journal = HashJournal(output / "worker.journal.jsonl", request.run_id)
    entries = journal.entries()
    terminal_events = [entry for entry in entries if entry.get("event") == "TERMINAL_RESULT_PUBLISHED"]
    if len(terminal_events) != 1 or journal.terminal_hash() != result.get("journal_chain_terminal_hash"):
        raise VerificationError("RESULT_JOURNAL_LINK_INVALID")
    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="offline-parquet-verifier")
    parser.add_argument("--child", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.child is None:
        print("offline verifier requires --child REQUEST.json", file=sys.stderr)
        return 64
    try:
        return child_verify(args.child)
    except BaseException as exc:
        print(_safe_error(exc), file=sys.stderr)
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
