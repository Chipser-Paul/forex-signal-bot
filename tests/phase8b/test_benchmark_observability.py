from __future__ import annotations

import io
import json
import time

import pytest

from backtests import empirical_data_control
from bot.acquisition import benchmark_supervisor
from bot.acquisition.benchmark_supervisor import SupervisorResult, supervise_benchmark_child
from bot.acquisition.journal import (
    BenchmarkJournal,
    BoundedSanitizedLog,
    JournalHeartbeat,
)
from bot.acquisition.models import AcquisitionError


class _FakeProcess:
    def __init__(self, returncode=None):
        self.returncode = returncode
        self.pid = 4242
        self.stdout = io.StringIO("password=should-not-survive\n")
        self.stderr = io.StringIO("")

    def poll(self):
        return self.returncode

    def send_signal(self, _signal):
        return None

    def wait(self, timeout=None):
        del timeout
        if self.returncode is None:
            raise benchmark_supervisor.subprocess.TimeoutExpired("fake", 0)
        return self.returncode

    def terminate(self):
        self.returncode = 130

    def kill(self):
        self.returncode = 137


@pytest.mark.unit
def test_journal_is_hash_chained_durable_and_tail_recoverable(tmp_path):
    journal = BenchmarkJournal.create(tmp_path, "hour", run_id="hour-test-journal")
    journal.append("SAFETY_CHECK_STARTED", status="RUNNING")
    journal.append("SAFETY_CHECK_PASSED", status="PASSED")
    records = journal.records()
    assert [record["sequence"] for record in records] == [1, 2, 3]
    assert records[1]["previous_record_sha256"] == records[0]["record_sha256"]
    with journal.journal_path.open("ab") as handle:
        handle.write(b'{"partial":')
    journal.append("DEPENDENCY_CHECK_PASSED", status="PASSED")
    assert len(journal.records()) == 4


@pytest.mark.unit
def test_journal_rejects_non_tail_tampering(tmp_path):
    journal = BenchmarkJournal.create(tmp_path, "hour", run_id="hour-test-tamper")
    journal.append("SAFETY_CHECK_STARTED", status="RUNNING")
    text = journal.journal_path.read_text(encoding="utf-8").replace('"status":"PREPARED"', '"status":"CHANGED"')
    journal.journal_path.write_text(text, encoding="utf-8")
    with pytest.raises(AcquisitionError, match="malformed"):
        journal.records()


@pytest.mark.unit
def test_slow_operation_emits_heartbeats_within_bound(tmp_path):
    journal = BenchmarkJournal.create(tmp_path, "hour", run_id="hour-test-heartbeat")
    with JournalHeartbeat(journal, "REQUEST", interval_seconds=0.01):
        deadline = time.monotonic() + 5.0
        while not [item for item in journal.records() if item["event"] == "HEARTBEAT"]:
            assert time.monotonic() < deadline
            time.sleep(0.01)
    heartbeats = [item for item in journal.records() if item["event"] == "HEARTBEAT"]
    assert heartbeats
    assert all(item["status"] == "REQUEST" for item in heartbeats)


@pytest.mark.unit
def test_timeout_is_durable_and_shutdown_is_attempted(tmp_path, monkeypatch):
    journal = BenchmarkJournal.create(tmp_path, "hour", run_id="hour-test-timeout")
    journal.append("REQUEST_STARTED", status="RUNNING")
    process = _FakeProcess()
    monkeypatch.setattr(benchmark_supervisor.subprocess, "Popen", lambda *_args, **_kwargs: process)

    def interrupt(child, _journal):
        journal.append("MT5_SHUTDOWN_STARTED", status="RUNNING")
        journal.append("MT5_SHUTDOWN_COMPLETED", status="SUCCEEDED")
        child.returncode = 130

    monkeypatch.setattr(benchmark_supervisor, "_interrupt_child", interrupt)
    result = supervise_benchmark_child(
        ["fake-child"],
        journal,
        environment={},
        poll_seconds=0.01,
        stage_wall_clock_seconds=1,
        step_timeouts={**benchmark_supervisor.STEP_TIMEOUT_SECONDS, "REQUEST": 0.02},
    )
    assert result.exit_code == 124 and result.timed_out
    events = [item["event"] for item in journal.records()]
    assert "MT5_SHUTDOWN_STARTED" in events
    assert "RUN_TIMED_OUT" in events
    assert events[-1] == "SUPERVISOR_EXIT_RECORDED"
    assert journal.state()["worker_exit_status"] == 130
    assert journal.state()["supervisor_exit_status"] == 124


@pytest.mark.unit
def test_bounded_logs_cannot_replace_authoritative_journal(tmp_path):
    journal = BenchmarkJournal.create(tmp_path, "hour", run_id="hour-test-log")
    sink = BoundedSanitizedLog(journal.run_dir / "stdout.log", maximum_bytes=1024)
    sink.write("password=secret C:\\private\\terminal.exe " + ("x" * 3000))
    sink.write("second-line")
    combined = b"".join(
        path.read_bytes() for path in (journal.run_dir / "stdout.log.1", journal.run_dir / "stdout.log") if path.exists()
    ).decode("ascii")
    assert "secret" not in combined and "terminal.exe" not in combined
    assert len(journal.records()) == 1
    assert all(path.stat().st_size <= 1024 for path in journal.run_dir.glob("stdout.log*"))


@pytest.mark.unit
def test_supervisor_persists_success_exit_code(tmp_path, monkeypatch):
    journal = BenchmarkJournal.create(tmp_path, "hour", run_id="hour-test-exit")
    journal.append("RUN_COMPLETED", status="PASSED", exit_status=0)
    process = _FakeProcess(returncode=0)
    monkeypatch.setattr(benchmark_supervisor.subprocess, "Popen", lambda *_args, **_kwargs: process)
    result = supervise_benchmark_child(["fake-child"], journal, environment={}, poll_seconds=0.01)
    assert result.exit_code == 0
    assert journal.records()[-1]["event"] == "SUPERVISOR_EXIT_RECORDED"
    assert result.worker_exit_code == 0 and result.supervisor_exit_code == 0
    assert journal.state()["exit_status"] == 0


@pytest.mark.unit
def test_supervisor_heartbeats_continue_for_silent_worker_longer_than_thirty_seconds(
    tmp_path, monkeypatch
):
    journal = BenchmarkJournal.create(tmp_path, "hour", run_id="hour-test-supervisor-heartbeat")
    journal.append("REQUEST_STARTED", status="RUNNING")

    class Clock:
        value = 0.0

        def monotonic(self):
            return self.value

        def sleep(self, seconds):
            self.value += max(seconds, 5.0)

    clock = Clock()
    process = _FakeProcess()

    def poll():
        if clock.value >= 35 and process.returncode is None:
            journal.append("REQUEST_COMPLETED", status="PASSED")
            journal.append("RUN_COMPLETED", status="PASSED", exit_status=0)
            process.returncode = 0
        return process.returncode

    process.poll = poll
    process.stdout = io.StringIO("")
    monkeypatch.setattr(benchmark_supervisor.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(benchmark_supervisor.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(benchmark_supervisor.time, "sleep", clock.sleep)
    result = supervise_benchmark_child(
        ["silent-child"], journal, environment={}, poll_seconds=5, heartbeat_seconds=15
    )
    heartbeats = [item for item in journal.records() if item["event"] == "HEARTBEAT"]
    assert result.exit_code == 0 and len(heartbeats) >= 2
    assert all(item["details"]["origin"] == "SUPERVISOR" for item in heartbeats)
    assert (journal.run_dir / "stdout.log").exists()
    assert (journal.run_dir / "stderr.log").exists()


@pytest.mark.unit
def test_failed_run_identity_is_never_overwritten(tmp_path):
    first = BenchmarkJournal.create(tmp_path, "hour", run_id="hour-test-repeat")
    first.append("RUN_FAILED", status="FAILED", error_category="DATA_UNAVAILABLE", exit_status=2)
    with pytest.raises(FileExistsError):
        BenchmarkJournal.create(tmp_path, "hour", run_id="hour-test-repeat")
    second = BenchmarkJournal.create(tmp_path, "hour")
    assert second.run_id != first.run_id and second.run_dir != first.run_dir


@pytest.mark.unit
def test_resume_rejects_incomplete_run_without_importing_mt5(tmp_path, monkeypatch, capsys):
    journal = BenchmarkJournal.create(tmp_path, "hour", run_id="hour-test-incomplete")
    imported: list[str] = []
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    monkeypatch.setattr(empirical_data_control.importlib, "import_module", lambda name: imported.append(name))
    result = empirical_data_control.main([
        "benchmark", "--stage", "hour", "--resume-run-id", journal.run_id,
        "--confirm-read-only-demo-export", "--output-root", str(tmp_path),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert result == 2 and imported == []
    assert payload["reason_code"] == "INCOMPLETE_BENCHMARK_CANNOT_RESUME"


@pytest.mark.unit
@pytest.mark.parametrize("stage", ["day", "week"])
def test_later_cli_stages_fail_before_child_launch(tmp_path, monkeypatch, stage, capsys):
    owner = tmp_path / "owner"
    control = owner / "frontend" / "utils"
    control.mkdir(parents=True)
    (control / ".bot_state.json").write_text('{"state":"stopped"}', encoding="utf-8")
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    monkeypatch.setattr(empirical_data_control, "windows_process_snapshot", lambda: ())
    monkeypatch.setattr(empirical_data_control.importlib.metadata, "version", lambda _name: "25.0.1")
    result = empirical_data_control.main([
        "benchmark", "--stage", stage, "--confirm-read-only-demo-export",
        "--owner-worktree", str(owner), "--output-root", str(tmp_path / "output"),
        "--minimum-free-gb", "0", "--maximum-output-gb", "1",
    ])
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert result == 2
    assert lines[0]["status"] == "BENCHMARK_RUN_PREPARED"
    assert lines[-1]["reason_code"] == "STAGE_PREREQUISITE_MISSING"


@pytest.mark.unit
def test_no_confirmation_returns_before_git_or_process_work(monkeypatch):
    monkeypatch.setattr(
        empirical_data_control,
        "_worktree_roots",
        lambda: (_ for _ in ()).throw(AssertionError("git must not run")),
    )
    monkeypatch.setattr(
        empirical_data_control,
        "windows_process_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("process scan must not run")),
    )
    assert empirical_data_control.main(["estimate"]) == 0


@pytest.mark.unit
def test_cli_prints_durable_identity_before_child_launch(tmp_path, monkeypatch, capsys):
    owner = tmp_path / "owner"
    state = owner / "frontend" / "utils"
    state.mkdir(parents=True)
    (state / ".bot_state.json").write_text('{"state":"stopped"}', encoding="utf-8")
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    monkeypatch.setattr(empirical_data_control, "windows_process_snapshot", lambda: ())
    monkeypatch.setattr(empirical_data_control.importlib.metadata, "version", lambda _name: "25.0.1")

    def supervise(_command, journal, **_kwargs):
        payload = json.loads(capsys.readouterr().out)
        assert payload["run_id"] == journal.run_id
        assert payload["journal_path"] == str(journal.journal_path)
        journal.append("RUN_FAILED", status="FAILED", error_category="TEST_STOP", exit_status=2)
        return SupervisorResult(2, False, "RUN_FAILED")

    monkeypatch.setattr(benchmark_supervisor, "supervise_benchmark_child", supervise)
    result = empirical_data_control.main([
        "benchmark", "--stage", "hour", "--confirm-read-only-demo-export",
        "--owner-worktree", str(owner), "--output-root", str(tmp_path / "output"),
        "--minimum-free-gb", "0", "--maximum-output-gb", "1",
    ])
    assert result == 2
