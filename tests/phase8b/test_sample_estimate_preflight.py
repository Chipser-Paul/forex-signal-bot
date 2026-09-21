from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from backtests import empirical_data_control
from bot.acquisition.exporter import EmpiricalExporter
from bot.acquisition.preflight import COVERAGE_PROBE_DAYS
from bot.acquisition.gateway import PERMITTED_MT5_OPERATIONS, ReadOnlyMT5Gateway
from bot.acquisition.models import AcquisitionError, ExportConfig
from bot.acquisition.safety import assess_project_control_safety
from bot.acquisition.storage import file_sha256
from bot.acquisition.gateway import _safe_text

from .helpers import FakeReadOnlyMT5, tick


UTC = timezone.utc
START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 7, 1, tzinfo=UTC)
SAMPLE_START = END - timedelta(minutes=15)


def _exporter(tmp_path, *, maximum_output_bytes: int = 50 * 1024**3):
    mt5 = FakeReadOnlyMT5()
    mt5.ticks = [
        tick(SAMPLE_START + timedelta(seconds=1)),
        tick(SAMPLE_START + timedelta(seconds=2), 2000.1, 2000.3),
    ]
    mt5.rates = [
        {"time": int((START + timedelta(days=1)).timestamp())},
        {"time": int((START + timedelta(days=100)).timestamp())},
    ]
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    exporter = EmpiricalExporter(
        gateway,
        ExportConfig(
            output_root=tmp_path,
            start=START,
            end=END,
            maximum_output_bytes=maximum_output_bytes,
        ),
    )
    return mt5, gateway, exporter


@pytest.mark.unit
def test_sample_is_hashed_atomic_and_manifested(tmp_path):
    _mt5, gateway, exporter = _exporter(tmp_path)
    manifest = exporter.write_sample(SAMPLE_START, END)
    data = tmp_path / manifest.relative_path
    marker = tmp_path / manifest.completion_marker
    manifest_path = data.with_name(data.name.removesuffix(".jsonl.gz") + ".manifest.json")

    assert data.is_file() and marker.is_file() and manifest_path.is_file()
    assert manifest.sha256 == file_sha256(data)
    assert len(manifest.sha256) == 64
    assert manifest.row_count == 2
    assert manifest.completion_status == "COMPLETE"
    assert manifest.requested_start == SAMPLE_START
    assert manifest.requested_end == END
    assert manifest.returned_start >= SAMPLE_START
    assert manifest.returned_end < END
    assert not list(tmp_path.rglob("*.partial"))
    serialized = json.dumps(asdict(manifest), default=str).lower()
    assert all(token not in serialized for token in ("password", "api_key", "login", "balance", "equity"))
    gateway.shutdown()


@pytest.mark.unit
def test_missing_marker_hash_mismatch_and_partial_sample_are_rejected(tmp_path):
    _mt5, gateway, exporter = _exporter(tmp_path)
    manifest = exporter.write_sample(SAMPLE_START, END)
    data = tmp_path / manifest.relative_path
    marker = tmp_path / manifest.completion_marker

    marker.unlink()
    with pytest.raises(AcquisitionError, match="incomplete"):
        exporter.load_sample(SAMPLE_START, END)
    marker.write_text(json.dumps(asdict(manifest), default=str), encoding="utf-8")
    with pytest.raises(AcquisitionError):
        exporter.load_sample(SAMPLE_START, END)

    data.unlink()
    marker.unlink()
    manifest_path = data.with_name(data.name.removesuffix(".jsonl.gz") + ".manifest.json")
    manifest_path.unlink()
    partial = data.with_suffix(data.suffix + ".partial")
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.write_bytes(b"interrupted")
    with pytest.raises(FileExistsError, match="already exists"):
        exporter.write_sample(SAMPLE_START, END)
    with pytest.raises(AcquisitionError, match="manifest is missing"):
        exporter.load_sample(SAMPLE_START, END)
    gateway.shutdown()


@pytest.mark.unit
def test_tampered_completed_sample_and_overwrite_are_rejected(tmp_path):
    mt5, gateway, exporter = _exporter(tmp_path)
    manifest = exporter.write_sample(SAMPLE_START, END)
    calls_before = len(mt5.calls)
    with pytest.raises(FileExistsError, match="already exists"):
        exporter.write_sample(SAMPLE_START, END)
    assert len(mt5.calls) == calls_before

    with (tmp_path / manifest.relative_path).open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(AcquisitionError, match="hash"):
        exporter.load_sample(SAMPLE_START, END)
    gateway.shutdown()


@pytest.mark.unit
def test_interrupted_manifest_write_cannot_be_accepted(tmp_path, monkeypatch):
    _mt5, gateway, exporter = _exporter(tmp_path)
    monkeypatch.setattr(
        "bot.acquisition.preflight.atomic_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("simulated interruption")),
    )
    with pytest.raises(OSError, match="simulated interruption"):
        exporter.write_sample(SAMPLE_START, END)
    with pytest.raises(AcquisitionError, match="manifest is missing"):
        exporter.load_sample(SAMPLE_START, END)
    gateway.shutdown()


@pytest.mark.unit
def test_coverage_discovery_is_bounded_and_reports_empty_periods(tmp_path):
    mt5, gateway, exporter = _exporter(tmp_path)
    coverage = exporter.discover_coverage()
    rate_calls = [args for name, args, _kwargs in mt5.calls if name == "copy_rates_range"]

    assert coverage.probe_count == 3
    assert coverage.empty_probe_count == 1
    assert coverage.active_days == 2
    assert coverage.earliest_available == START + timedelta(days=1)
    assert coverage.latest_available == START + timedelta(days=100)
    assert all((args[3] - args[2]).days <= COVERAGE_PROBE_DAYS for args in rate_calls)
    assert {name for name, _args, _kwargs in mt5.calls} <= PERMITTED_MT5_OPERATIONS
    gateway.shutdown()


@pytest.mark.unit
def test_empty_coverage_is_explicit_and_never_safe(tmp_path, monkeypatch):
    mt5, gateway, exporter = _exporter(tmp_path)
    mt5.rates = []
    sample = exporter.write_sample(SAMPLE_START, END)
    coverage = exporter.discover_coverage()
    monkeypatch.setattr(exporter.store, "free_bytes", lambda: 100 * 1024**3)
    estimate = exporter.estimate(sample, coverage)

    assert coverage.earliest_available is None
    assert coverage.latest_available is None
    assert coverage.empty_probe_count == coverage.probe_count
    assert estimate.estimated_rows == 0
    assert estimate.estimated_bytes == 0
    assert not estimate.safe_to_continue
    gateway.shutdown()


@pytest.mark.unit
def test_estimate_is_complete_deterministic_and_enforces_disk_limits(tmp_path, monkeypatch):
    _mt5, gateway, exporter = _exporter(tmp_path)
    sample = exporter.write_sample(SAMPLE_START, END)
    coverage = exporter.discover_coverage()
    monkeypatch.setattr(exporter.store, "free_bytes", lambda: 100 * 1024**3)
    first = exporter.estimate(sample, coverage)
    second = exporter.estimate(sample, coverage)
    required = {
        "requested_start", "requested_end", "coverage_earliest", "coverage_latest",
        "coverage_basis", "coverage_probe_count", "coverage_empty_probe_count",
        "coverage_active_days", "calendar_days", "sample_rows", "sample_bytes",
        "sample_duration_seconds", "rows_per_active_hour", "rows_per_active_day",
        "rows_per_active_month", "compressed_bytes_per_row", "estimated_rows",
        "estimated_bytes", "estimated_bytes_low", "estimated_bytes_high",
        "sampling_throughput_rows_per_second", "export_throughput_bytes_per_second",
        "estimated_export_duration_seconds", "free_bytes", "budget_bytes",
        "existing_output_bytes", "required_safety_margin_bytes", "recommended_chunk",
        "uncertainty", "safe_to_continue",
    }
    assert set(asdict(first)) == required
    assert first == second
    assert first.estimated_export_duration_seconds > 0
    assert first.recommended_chunk in {"P1M", "P7D"}

    monkeypatch.setattr(exporter.store, "free_bytes", lambda: 1)
    constrained = exporter.estimate(sample, coverage)
    assert not constrained.safe_to_continue
    gateway.shutdown()


@pytest.mark.unit
def test_project_control_state_allows_unrelated_python_only_when_recorded_bot_is_inactive(tmp_path):
    state_dir = tmp_path / "frontend" / "utils"
    state_dir.mkdir(parents=True)
    (state_dir / ".bot_state.json").write_text('{"state":"stopped"}', encoding="utf-8")
    (state_dir / ".bot_process.json").write_text('{"pid":42,"cmd":"not inspected"}', encoding="utf-8")

    safe = assess_project_control_safety(tmp_path, ((99, "python.exe"),))
    active = assess_project_control_safety(tmp_path, ((42, "python.exe"), (99, "python.exe")))
    assert safe.safe and not safe.recorded_pid_active
    assert not active.safe and active.recorded_pid_active
    assert active.reason_code == "RECORDED_BOT_PID_ACTIVE"


@pytest.mark.unit
def test_cli_sample_then_estimate_uses_persisted_sample_and_bounded_calls(tmp_path, monkeypatch, capsys):
    mt5 = FakeReadOnlyMT5()
    mt5.ticks = [tick(SAMPLE_START + timedelta(seconds=1))]
    mt5.rates = [{"time": int((START + timedelta(days=1)).timestamp())}]
    owner = tmp_path / "owner"
    state_dir = owner / "frontend" / "utils"
    state_dir.mkdir(parents=True)
    (state_dir / ".bot_state.json").write_text('{"state":"stopped"}', encoding="utf-8")
    output = tmp_path / "external-data"
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    monkeypatch.setattr(empirical_data_control, "windows_process_snapshot", lambda: ((77, "python.exe"),))
    monkeypatch.setattr(empirical_data_control.importlib, "import_module", lambda name: mt5)
    common = [
        "--confirm-read-only-demo-export",
        "--owner-worktree", str(owner),
        "--output-root", str(output),
        "--start", START.isoformat(),
        "--end", END.isoformat(),
    ]

    assert empirical_data_control.main(["sample", *common]) == 0
    assert empirical_data_control.main(["estimate", *common]) == 0
    payloads = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert payloads[0]["status"] == "SAMPLE_VALID"
    assert payloads[1]["status"] == "ESTIMATE_COMPLETE"
    assert payloads[1]["coverage"]["basis"] == "BOUNDED_D1_OPEN_TIME_PROXY"
    tick_calls = [call for call in mt5.calls if call[0] == "copy_ticks_range"]
    assert len(tick_calls) == 1
    assert {name for name, _args, _kwargs in mt5.calls} <= PERMITTED_MT5_OPERATIONS


@pytest.mark.unit
@pytest.mark.parametrize("command", ("sample", "estimate"))
def test_sample_and_estimate_without_confirmation_make_zero_mt5_calls(command, tmp_path, monkeypatch):
    mt5 = FakeReadOnlyMT5()
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    monkeypatch.setattr(empirical_data_control.importlib, "import_module", lambda name: mt5)
    assert empirical_data_control.main([command, "--output-root", str(tmp_path)]) == 0
    assert mt5.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("payload", ('[]', 'null', '{"state":"running"}', '{"state":"token=fixture-value"}'))
def test_malformed_or_running_control_fails_closed_without_echoing_content(tmp_path, payload):
    folder = tmp_path / "frontend" / "utils"
    folder.mkdir(parents=True)
    (folder / ".bot_state.json").write_text(payload, encoding="utf-8")
    result = assess_project_control_safety(tmp_path, ())
    assert not result.safe
    assert "fixture-value" not in repr(result)


@pytest.mark.unit
def test_metadata_redacts_credential_shaped_text():
    value = "token=" + "fixture-value"
    assert "fixture-value" not in _safe_text(value)


@pytest.mark.unit
@pytest.mark.parametrize("field,value", (("acquisition_elapsed_seconds", 0), ("write_elapsed_seconds", float("nan")), ("returned_end", END.isoformat())))
def test_corrupt_sample_diagnostics_cannot_authorize_export(tmp_path, field, value):
    _mt5, _gateway, exporter = _exporter(tmp_path)
    sample = exporter.write_sample(SAMPLE_START, END)
    path = (tmp_path / sample.relative_path).with_name(sample.sample_id + ".manifest.json")
    payload = json.loads(path.read_text())
    payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AcquisitionError):
        exporter.load_sample(SAMPLE_START, END)


@pytest.mark.unit
def test_query_failure_is_not_empty_market_history(tmp_path, monkeypatch):
    mt5, _gateway, exporter = _exporter(tmp_path)
    monkeypatch.setattr(mt5, "copy_rates_range", lambda *_args: None)
    with pytest.raises(AcquisitionError, match="query failed"):
        exporter.discover_coverage()


@pytest.mark.unit
def test_sample_naive_or_unbounded_interval_never_queries(tmp_path):
    mt5, _gateway, exporter = _exporter(tmp_path)
    before = len(mt5.calls)
    with pytest.raises(AcquisitionError):
        exporter.write_sample(SAMPLE_START.replace(tzinfo=None), END)
    with pytest.raises(AcquisitionError):
        exporter.write_sample(START, END)
    assert len(mt5.calls) == before
