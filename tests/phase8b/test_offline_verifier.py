from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from bot.acquisition.exness_archive import _canonical_from_parquet_values, exness_tick_schema
from bot.acquisition import offline_verifier
from bot.acquisition.offline_verifier import (
    DEFAULT_HEARTBEAT_SECONDS,
    PROTOCOL_VERSION,
    HashJournal,
    VerificationError,
    VerificationRequest,
    child_verify,
    _load_terminal_any,
    supervise_verification,
)
from bot.acquisition.storage import file_sha256


UTC = timezone.utc


def _rows(*, count: int = 8, symbol: str = "XAUUSDm", reverse: bool = False, crossed: bool = False):
    rows = []
    for index in range(count):
        timestamp = datetime(2024, 1, 2, 12, 0, tzinfo=UTC).replace(microsecond=index * 1000)
        bid = Decimal("2000.00000000") + Decimal(index) / Decimal(100)
        ask = bid + Decimal("0.20000000")
        if crossed and index == 2:
            ask = bid - Decimal("0.10000000")
        rows.append((timestamp, bid, ask, index, symbol))
    return list(reversed(rows)) if reverse else rows


def _logical(rows) -> str:
    import hashlib

    digest = hashlib.sha256()
    for timestamp, bid, ask, sequence_id, symbol in rows:
        digest.update(_canonical_from_parquet_values(
            symbol=symbol,
            time_msc=int(timestamp.timestamp() * 1000),
            bid=bid,
            ask=ask,
            sequence_id=sequence_id,
        ))
        digest.update(b"\n")
    return digest.hexdigest()


def _parquet(tmp_path: Path, rows=None, *, row_groups: int = 1) -> tuple[Path, list]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = list(rows or _rows())
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "input.parquet"
    schema = exness_tick_schema()
    payload = []
    for timestamp, bid, ask, sequence_id, symbol in rows:
        payload.append({
            "source": "Exness",
            "symbol": symbol,
            "timestamp_raw": timestamp.isoformat().replace("+00:00", "Z"),
            "timestamp": timestamp,
            "time_msc": int(timestamp.timestamp() * 1000),
            "bid_raw": str(bid),
            "ask_raw": str(ask),
            "bid": bid,
            "ask": ask,
            "sequence_id": sequence_id,
            "row_identity": "synthetic",
            "source_member": "synthetic.csv",
            "member_sha256": "0" * 64,
            "archive_sha256": "1" * 64,
            "provenance_id": "synthetic",
        })
    table = pa.Table.from_pylist(payload, schema=schema)
    with pq.ParquetWriter(path, schema) as writer:
        width = max(1, len(rows) // row_groups)
        for start in range(0, len(rows), width):
            writer.write_table(table.slice(start, width))
    return path, rows


def _request(tmp_path: Path, path: Path, rows, **overrides) -> VerificationRequest:
    values = {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": "synthetic-run-001",
        "parquet_path": str(path.resolve()),
        "expected_physical_sha256": file_sha256(path),
        "expected_logical_sha256": _logical(rows),
        "expected_schema_identity": "phase8b.exness-tick.v1",
        "expected_symbol": "XAUUSDm",
        "expected_period": "2024-01",
        "expected_row_count": len(rows),
        "batch_size": 2,
        "stage_timeout_seconds": 30,
        "overall_timeout_seconds": 60,
        "output_directory": str((tmp_path / "run").resolve()),
        "code_fingerprint": "synthetic-tests-v1",
    }
    values.update(overrides)
    return VerificationRequest(**values)


def _direct_child(request: VerificationRequest):
    output = Path(request.output_directory)
    output.mkdir(parents=True, exist_ok=True)
    (output / "request.json").write_text(json.dumps(request.__dict__), encoding="utf-8")
    child_verify(output / "request.json")
    return _load_terminal_any(request)


@pytest.fixture
def allow_offline_child(monkeypatch):
    """Narrow opt-in for the verifier's own synthetic child process."""
    from tests.conftest import REAL_POPEN

    monkeypatch.setattr(offline_verifier.subprocess, "Popen", REAL_POPEN)


@pytest.mark.unit
def test_successful_multi_batch_scan_is_idempotent_and_does_not_mutate_input(tmp_path, allow_offline_child):
    path, rows = _parquet(tmp_path, row_groups=4)
    before_hash, before_stat = file_sha256(path), path.stat().st_mtime_ns
    request = _request(tmp_path, path, rows)

    first = supervise_verification(request)
    second = supervise_verification(request)

    assert first["status"] == "VERIFIED"
    assert first["result"]["batch_count"] >= 4
    assert first["result"]["logical_canonical_sha256"] == _logical(rows)
    assert second["idempotent"] is True
    assert file_sha256(path) == before_hash and path.stat().st_mtime_ns == before_stat


@pytest.mark.unit
@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"expected_physical_sha256": "0" * 64}, "PHYSICAL_HASH_MISMATCH"),
        ({"expected_logical_sha256": "0" * 64}, "LOGICAL_HASH_MISMATCH"),
        ({"expected_row_count": 99}, "ROW_COUNT_MISMATCH"),
        ({"expected_symbol": "XAUUSD"}, "REQUEST_SYMBOL_UNSUPPORTED"),
    ],
)
def test_request_and_identity_rejections_are_explicit(tmp_path, override, expected, allow_offline_child):
    path, rows = _parquet(tmp_path)
    if expected.startswith("REQUEST_"):
        with pytest.raises(VerificationError, match=expected):
            _request(tmp_path, path, rows, **override)
    else:
        result = supervise_verification(_request(tmp_path, path, rows, **override))
        assert result["status"] == expected


@pytest.mark.unit
def test_ordering_conflicts_and_malformed_quotes_are_detected(tmp_path, allow_offline_child):
    path, rows = _parquet(tmp_path / "ordering", _rows(reverse=True))
    result = supervise_verification(_request(tmp_path / "ordering", path, rows))
    assert result["status"] == "ORDERING_INVALID"

    path, rows = _parquet(tmp_path / "crossed", _rows(crossed=True))
    result = supervise_verification(_request(tmp_path / "crossed", path, rows))
    assert result["status"] == "MALFORMED_ROW"


@pytest.mark.unit
def test_schema_symbol_period_duplicates_and_conflicts_have_stable_results(tmp_path):
    path, rows = _parquet(tmp_path / "symbol", _rows(symbol="XAUUSD"))
    request = _request(tmp_path / "symbol", path, rows)
    assert _direct_child(request)["status"] == "SYMBOL_MISMATCH"

    path, rows = _parquet(tmp_path / "period")
    request = _request(tmp_path / "period", path, rows, expected_period="2024-02")
    assert _direct_child(request)["status"] == "PERIOD_MISMATCH"

    duplicate_rows = _rows()[:2] + [_rows()[1]] + _rows()[2:]
    path, rows = _parquet(tmp_path / "duplicates", duplicate_rows)
    terminal = _direct_child(_request(tmp_path / "duplicates", path, rows))
    assert terminal["status"] == "VERIFIED"
    assert terminal["duplicate_statistics"]["exact"] == 1

    conflicting = _rows()[:1] + [( _rows()[0][0], Decimal("2001"), Decimal("2001.2"), 99, "XAUUSDm")] + _rows()[1:]
    path, rows = _parquet(tmp_path / "conflicts", conflicting)
    terminal = _direct_child(_request(tmp_path / "conflicts", path, rows))
    assert terminal["status"] == "VERIFIED"
    assert terminal["duplicate_statistics"]["conflicting_timestamps"] == 1


@pytest.mark.unit
def test_broken_journal_or_terminal_checksum_is_not_accepted(tmp_path, allow_offline_child):
    path, rows = _parquet(tmp_path)
    request = _request(tmp_path, path, rows)
    assert supervise_verification(request)["status"] == "VERIFIED"
    (Path(request.output_directory) / "terminal-result.complete.json").write_text("{}", encoding="utf-8")
    with pytest.raises(VerificationError, match="RESULT_REUSE_IDENTITY_MISMATCH"):
        supervise_verification(request)


@pytest.mark.unit
def test_journal_is_hash_chained_and_rejects_tampering(tmp_path):
    journal = HashJournal(tmp_path / "journal.jsonl", "journal-run-001")
    journal.append("RUN_PREPARED", {"safe": "value"})
    journal.append("HEARTBEAT", {"elapsed_seconds": 1})
    lines = (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    changed = json.loads(lines[0]); changed["payload"] = {"changed": True}
    lines[0] = json.dumps(changed)
    (tmp_path / "journal.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(VerificationError, match="JOURNAL_CHAIN_INVALID"):
        journal.entries()


@pytest.mark.unit
@pytest.mark.parametrize("attempt", range(3))
def test_supervisor_rejects_child_crash_missing_result_and_keeps_heartbeat(tmp_path, allow_offline_child, attempt):
    path, rows = _parquet(tmp_path)
    request = _request(tmp_path, path, rows, stage_timeout_seconds=2, overall_timeout_seconds=3)
    crash = [sys.executable, "-c", "import sys; sys.exit(9)"]
    result = supervise_verification(request, heartbeat_interval_seconds=0.05, command=crash)
    assert result["status"] == "RESULT_INVALID"
    events = HashJournal(Path(request.output_directory) / "supervisor.journal.jsonl", request.run_id).entries()
    names = [event["event"] for event in events]
    assert names.index("CHILD_STARTED") < names.index("HEARTBEAT") < names.index("CHILD_EXITED")
    assert events[names.index("HEARTBEAT")]["payload"]["initial"] is True
    assert names.count("RUN_FAILED") == 1
    assert result["reason_code"] == "RESULT_MISSING"


@pytest.mark.unit
def test_launch_failure_records_no_misleading_heartbeat(tmp_path, monkeypatch):
    path, rows = _parquet(tmp_path)
    request = _request(tmp_path, path, rows)

    def fail_launch(*_args, **_kwargs):
        raise OSError("synthetic launch failure")

    monkeypatch.setattr(offline_verifier.subprocess, "Popen", fail_launch)
    result = supervise_verification(request)
    events = HashJournal(Path(request.output_directory) / "supervisor.journal.jsonl", request.run_id).entries()
    names = [event["event"] for event in events]
    assert result["status"] == "RESULT_INVALID"
    assert result["reason_code"] == "CHILD_LAUNCH_FAILED"
    assert "CHILD_LAUNCH_FAILED" in names
    assert "CHILD_STARTED" not in names and "HEARTBEAT" not in names
    assert names.count("RUN_FAILED") == 1


@pytest.mark.unit
def test_long_running_child_gets_initial_and_periodic_heartbeats(tmp_path, allow_offline_child):
    path, rows = _parquet(tmp_path)
    request = _request(tmp_path, path, rows, stage_timeout_seconds=2, overall_timeout_seconds=3)
    sleeper = [sys.executable, "-c", "import time; time.sleep(0.25)"]
    result = supervise_verification(request, heartbeat_interval_seconds=0.05, command=sleeper)
    events = HashJournal(Path(request.output_directory) / "supervisor.journal.jsonl", request.run_id).entries()
    heartbeats = [event for event in events if event["event"] == "HEARTBEAT"]
    assert result["reason_code"] == "RESULT_MISSING"
    assert len(heartbeats) >= 2
    assert heartbeats[0]["payload"]["initial"] is True
    assert all(not item["payload"].get("initial", False) for item in heartbeats[1:])


@pytest.mark.unit
def test_supervisor_timeout_terminates_only_its_child(tmp_path, allow_offline_child):
    path, rows = _parquet(tmp_path)
    request = _request(tmp_path, path, rows, stage_timeout_seconds=0.2, overall_timeout_seconds=0.3)
    sleeper = [sys.executable, "-c", "import time; time.sleep(10)"]
    result = supervise_verification(request, heartbeat_interval_seconds=0.05, command=sleeper)
    assert result["status"] == "TIMED_OUT"


@pytest.mark.unit
def test_request_path_and_timeout_validation_fails_closed(tmp_path):
    path, rows = _parquet(tmp_path)
    with pytest.raises(VerificationError, match="REQUEST_INPUT_OUTPUT_OVERLAP"):
        _request(tmp_path, path, rows, output_directory=str(path.parent.resolve()))
    with pytest.raises(VerificationError, match="REQUEST_TIMEOUT_INVALID"):
        _request(tmp_path, path, rows, stage_timeout_seconds=0)


@pytest.mark.unit
def test_input_replacement_and_non_overwrite_are_rejected(tmp_path, allow_offline_child):
    path, rows = _parquet(tmp_path)
    request = _request(tmp_path, path, rows)
    Path(request.output_directory).mkdir()
    (Path(request.output_directory) / "evidence.txt").write_text("existing", encoding="utf-8")
    with pytest.raises(VerificationError, match="RUN_DIRECTORY_NONEMPTY"):
        supervise_verification(request)


@pytest.mark.unit
def test_post_scan_physical_change_is_a_terminal_failure(tmp_path, monkeypatch):
    path, rows = _parquet(tmp_path)
    request = _request(tmp_path, path, rows)
    actual_hash = file_sha256(path)
    calls = 0

    def changing_hash(candidate):
        nonlocal calls
        calls += 1
        if calls == 2:
            return "f" * 64
        return actual_hash if Path(candidate) == path else file_sha256(candidate)

    monkeypatch.setattr(offline_verifier, "file_sha256", changing_hash)
    terminal = _direct_child(request)
    assert terminal["status"] == "PHYSICAL_FILE_CHANGED_DURING_SCAN"


@pytest.mark.unit
def test_cli_contract_uses_only_explicit_arguments(tmp_path, allow_offline_child):
    path, rows = _parquet(tmp_path)
    output = tmp_path / "cli-run"
    command = [
        sys.executable, "-m", "backtests.offline_dataset_control", "verify-parquet",
        "--run-id", "cli-synthetic-001", "--parquet", str(path.resolve()),
        "--expected-physical-sha256", file_sha256(path), "--expected-logical-sha256", _logical(rows),
        "--period", "2024-01", "--expected-row-count", str(len(rows)),
        "--output-directory", str(output.resolve()), "--code-fingerprint", "synthetic-cli-v1",
    ]
    from tests.conftest import REAL_POPEN

    process = REAL_POPEN(command, cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate(timeout=30)
    assert process.returncode == 0, stderr
    assert json.loads(stdout)["status"] == "VERIFIED"


@pytest.mark.unit
def test_fresh_process_import_does_not_load_mt5_or_gateway(tmp_path, allow_offline_child):
    script = (
        "import sys; import bot.acquisition.offline_verifier; "
        "assert 'MetaTrader5' not in sys.modules; "
        "assert 'bot.acquisition.gateway' not in sys.modules"
    )
    from tests.conftest import REAL_POPEN

    process = REAL_POPEN([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _stdout, stderr = process.communicate(timeout=30)
    assert process.returncode == 0, stderr


@pytest.mark.unit
def test_default_heartbeat_contract_is_fifteen_seconds():
    assert 10 <= DEFAULT_HEARTBEAT_SECONDS <= 20
