from __future__ import annotations

import json
from collections import namedtuple
from datetime import timedelta

import pytest

from backtests import empirical_data_control
from bot.acquisition.benchmark import (
    AcquisitionBenchmark,
    BENCHMARK_INTERVALS,
    verify_stage_run,
)
from bot.acquisition.gateway import PERMITTED_MT5_OPERATIONS, ReadOnlyMT5Gateway
from bot.acquisition.journal import BenchmarkJournal
from bot.acquisition.models import AcquisitionError

from .helpers import FakeReadOnlyMT5, tick


def _run_hour(tmp_path, mt5: FakeReadOnlyMT5) -> tuple[dict[str, object], BenchmarkJournal]:
    start, _end = BENCHMARK_INTERVALS["hour"]
    mt5.ticks = [tick(start + timedelta(minutes=1))]
    journal = BenchmarkJournal.create(tmp_path, "hour")
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    result = AcquisitionBenchmark(
        gateway,
        tmp_path,
        stage="hour",
        journal=journal,
        symbol_point=0.01,
        minimum_free_bytes=0,
        heartbeat_seconds=0.01,
    ).run(initialization_seconds=0.25)
    journal.append("MT5_SHUTDOWN_STARTED", status="RUNNING")
    gateway.shutdown()
    journal.append("MT5_SHUTDOWN_COMPLETED", status="PASSED")
    journal.append("RUN_COMPLETED", status="PASSED", exit_status=0)
    return result, journal


@pytest.mark.unit
def test_hour_stage_is_exact_durable_and_uses_one_session(tmp_path):
    mt5 = FakeReadOnlyMT5()
    result, journal = _run_hour(tmp_path, mt5)

    assert result["initialization_seconds"] == 0.25
    assert result["sample"]["requested_start"] == "2024-08-05T12:00:00Z"
    assert result["sample"]["requested_end"] == "2024-08-05T13:00:00Z"
    assert result["sample"]["readback_equal"] is True
    assert result["mt5_session_count"] == 1
    assert result["holdout_accessed"] is False and result["strategy_evaluated"] is False
    assert [name for name, _args, _kwargs in mt5.calls].count("initialize") == 1
    assert [name for name, _args, _kwargs in mt5.calls].count("shutdown") == 1
    assert {name for name, _args, _kwargs in mt5.calls} <= PERMITTED_MT5_OPERATIONS
    verified = verify_stage_run(journal.run_dir)
    assert verified["canonical_content_sha256"] == result["canonical_content_sha256"]
    access = json.loads((tmp_path / "manifests" / "data_access_log.json").read_text(encoding="utf-8"))
    assert len(access) == 1 and access[0]["classification"] == "DEVELOPMENT"


@pytest.mark.unit
def test_benchmark_disk_reserve_blocks_before_history_request(tmp_path, monkeypatch):
    mt5 = FakeReadOnlyMT5()
    journal = BenchmarkJournal.create(tmp_path, "hour")
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    monkeypatch.setattr("bot.acquisition.benchmark.shutil.disk_usage", lambda _path: (100, 100, 0))
    with pytest.raises(AcquisitionError, match="reserve"):
        AcquisitionBenchmark(
            gateway,
            tmp_path,
            stage="hour",
            journal=journal,
            symbol_point=0.01,
            minimum_free_bytes=1,
        ).run(initialization_seconds=0.1)
    assert not any(name == "copy_ticks_range" for name, _args, _kwargs in mt5.calls)
    gateway.shutdown()


@pytest.mark.unit
def test_empty_success_response_is_classified_before_normalization(tmp_path):
    mt5 = FakeReadOnlyMT5()
    journal = BenchmarkJournal.create(tmp_path, "hour")
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    with pytest.raises(AcquisitionError, match="no quotes"):
        AcquisitionBenchmark(
            gateway,
            tmp_path,
            stage="hour",
            journal=journal,
            symbol_point=0.01,
            minimum_free_bytes=0,
        ).run(initialization_seconds=0.1)
    records = journal.records()
    classified = next(item for item in records if item["event"] == "REQUEST_RESULT_CLASSIFIED")
    assert classified["status"] == "EMPTY_SUCCESS_RESPONSE"
    assert classified["details"]["response_kind"] == "EMPTY_ARRAY"
    assert classified["details"]["row_count"] == 0
    assert "NORMALIZATION_STARTED" not in {item["event"] for item in records}
    history_index = [name for name, _args, _kwargs in mt5.calls].index("copy_ticks_range")
    assert mt5.calls[history_index + 1][0] == "last_error"
    gateway.shutdown()


@pytest.mark.unit
def test_worker_guarantees_shutdown_and_records_failure(tmp_path, monkeypatch):
    mt5 = FakeReadOnlyMT5()
    owner = tmp_path / "owner"
    state = owner / "frontend" / "utils"
    state.mkdir(parents=True)
    (state / ".bot_state.json").write_text('{"state":"stopped"}', encoding="utf-8")
    journal = BenchmarkJournal.create(tmp_path / "output", "hour")
    monkeypatch.setattr(empirical_data_control, "windows_process_snapshot", lambda: ())
    monkeypatch.setattr(empirical_data_control.importlib, "import_module", lambda _name: mt5)
    monkeypatch.setattr(
        AcquisitionBenchmark,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AcquisitionError("fixture failure")),
    )
    result = empirical_data_control.main([
        "benchmark", "--_benchmark-worker", "--_benchmark-run-id", journal.run_id,
        "--stage", "hour", "--confirm-read-only-demo-export",
        "--owner-worktree", str(owner), "--output-root", str(tmp_path / "output"),
        "--minimum-free-gb", "0", "--maximum-output-gb", "1",
    ])
    assert result == 2
    assert [name for name, _args, _kwargs in mt5.calls].count("initialize") == 1
    assert [name for name, _args, _kwargs in mt5.calls].count("shutdown") == 1
    reopened = BenchmarkJournal.open(journal.run_dir)
    assert reopened.state()["terminal_event"] == "RUN_FAILED"
    assert not (journal.run_dir / "stage.complete.json").exists()


@pytest.mark.unit
def test_cli_disk_preflight_journals_failure_before_mt5_import(tmp_path, monkeypatch):
    owner = tmp_path / "owner"
    state = owner / "frontend" / "utils"
    state.mkdir(parents=True)
    (state / ".bot_state.json").write_text('{"state":"stopped"}', encoding="utf-8")
    imported: list[str] = []
    disk = namedtuple("usage", "total used free")
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    monkeypatch.setattr(empirical_data_control, "windows_process_snapshot", lambda: ())
    monkeypatch.setattr(empirical_data_control.shutil, "disk_usage", lambda _path: disk(100, 100, 0))
    monkeypatch.setattr(empirical_data_control.importlib, "import_module", lambda name: imported.append(name))
    result = empirical_data_control.main([
        "benchmark", "--stage", "hour", "--confirm-read-only-demo-export",
        "--owner-worktree", str(owner), "--output-root", str(tmp_path / "output"),
        "--minimum-free-gb", "1", "--maximum-output-gb", "1",
    ])
    assert result == 2 and imported == []
    runs = tuple((tmp_path / "output" / "benchmarks" / "development-20240805-20240812" / "runs" / "hour").iterdir())
    journal = BenchmarkJournal.open(runs[0])
    assert journal.state()["terminal_event"] == "RUN_FAILED"


@pytest.mark.unit
def test_hybrid_estimate_has_separate_non_statistical_scenarios(tmp_path):
    result, _journal = _run_hour(tmp_path, FakeReadOnlyMT5())
    assert result["estimates"]["scenario_ranges_are_not_confidence_intervals"] is True
    assert result["estimates"]["combined_bytes"]["lower"] < result["estimates"]["combined_bytes"]["upper"]


@pytest.mark.unit
def test_completed_stage_resume_verifies_without_another_mt5_request(tmp_path, monkeypatch, capsys):
    result, journal = _run_hour(tmp_path, FakeReadOnlyMT5())
    imported: list[str] = []
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    monkeypatch.setattr(empirical_data_control.importlib, "import_module", lambda name: imported.append(name))
    exit_code = empirical_data_control.main([
        "benchmark", "--stage", "hour", "--resume-run-id", journal.run_id,
        "--confirm-read-only-demo-export", "--output-root", str(tmp_path),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0 and imported == []
    assert payload["status"] == "BENCHMARK_STAGE_ALREADY_VERIFIED"
    assert payload["record_count"] == result["sample"]["rows"]


@pytest.mark.unit
def test_offline_verify_understands_stage_specific_artifact_roots(tmp_path, monkeypatch):
    _run_hour(tmp_path, FakeReadOnlyMT5())
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    assert empirical_data_control.main(["verify", "--output-root", str(tmp_path)]) == 0


@pytest.mark.unit
@pytest.mark.parametrize("stage", ["day", "week"])
def test_later_stage_requires_verified_predecessor(tmp_path, stage):
    mt5 = FakeReadOnlyMT5()
    journal = BenchmarkJournal.create(tmp_path, stage)
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    with pytest.raises(AcquisitionError, match="preceding"):
        AcquisitionBenchmark(
            gateway,
            tmp_path,
            stage=stage,
            journal=journal,
            symbol_point=0.01,
            minimum_free_bytes=0,
        ).run(initialization_seconds=0.1)
    assert not any(name == "copy_ticks_range" for name, _args, _kwargs in mt5.calls)
    gateway.shutdown()
