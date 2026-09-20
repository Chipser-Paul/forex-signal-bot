from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backtests import empirical_data_control
from bot.acquisition.exporter import EmpiricalExporter
from bot.acquisition.gateway import PERMITTED_MT5_OPERATIONS, ReadOnlyMT5Gateway
from bot.acquisition.models import ExportConfig, ExportStatus
from bot.acquisition.safety import ProjectControlSafety
from bot.acquisition.package import build_partial_package
from bot.validation.datasets import load_empirical_package_manifest, validate_dataset_package

from .helpers import FakeReadOnlyMT5, tick


UTC = timezone.utc
START = datetime(2026, 8, 1, tzinfo=UTC)
END = datetime(2026, 8, 2, tzinfo=UTC)


def _exporter(tmp_path):
    mt5 = FakeReadOnlyMT5()
    mt5.ticks = [tick(START + timedelta(seconds=1)), tick(START + timedelta(seconds=2), 2000.1, 2000.3)]
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    exporter = EmpiricalExporter(
        gateway,
        ExportConfig(output_root=tmp_path, start=START, end=END, maximum_output_bytes=10 * 1024**2),
    )
    return mt5, gateway, exporter


@pytest.mark.unit
def test_tick_export_resumes_at_verified_chunk_boundary(tmp_path):
    mt5, gateway, exporter = _exporter(tmp_path)
    first = exporter.export_ticks(resume=False)
    second = exporter.export_ticks(resume=True)
    assert first == second
    assert len(first) == 1
    assert first[0].record_count == 2
    assert not list(tmp_path.rglob("*.partial"))
    called = {name for name, _args, _kwargs in mt5.calls}
    assert called <= PERMITTED_MT5_OPERATIONS
    gateway.shutdown()


@pytest.mark.unit
def test_safe_metadata_marks_unavailable_cost_evidence_missing(tmp_path):
    _mt5, gateway, exporter = _exporter(tmp_path)
    path = exporter.export_safe_metadata(exported_at=END, resume=False)
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["symbol"] == "XAUUSDm"
    assert value["commission"]["status"] == "MISSING"
    assert value["historical_slippage"]["status"] == "MISSING"
    assert value["rollover_timezone"]["status"] == "MISSING"
    forbidden = {"login", "account", "balance", "equity", "positions", "orders", "deals"}
    serialized = json.dumps(value).lower()
    assert all(word not in serialized for word in forbidden)
    gateway.shutdown()


@pytest.mark.unit
def test_partial_package_reads_compressed_chunks_and_fails_acceptance_honestly(tmp_path):
    _mt5, gateway, exporter = _exporter(tmp_path)
    inspection = exporter.inspect()
    chunks = exporter.export_ticks(resume=False)
    exporter.write_export_manifest(
        inspection=inspection,
        chunks=chunks,
        metadata_path=None,
        status=ExportStatus.PARTIAL_EXPORT,
        git_commit="a" * 40,
    )
    path = build_partial_package(
        exporter.config,
        created_at=END,
        license_or_restrictions="OWNER_REVIEW_REQUIRED",
    )
    manifest = load_empirical_package_manifest(path)
    report = validate_dataset_package(manifest, tmp_path, checked_at=END)
    reasons = {issue.reason_code for issue in report.issues}
    assert report.outcome.value == "REJECTED"
    assert "NEWS_HISTORY_MISSING" in reasons
    assert "SLIPPAGE_PROVENANCE_MISSING" in reasons
    assert "STREAM_CORRUPT" not in reasons
    gateway.shutdown()


@pytest.mark.unit
def test_cli_fake_inspection_uses_only_allowlisted_operations(monkeypatch, capsys, tmp_path):
    mt5 = FakeReadOnlyMT5()
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    monkeypatch.setattr(empirical_data_control, "windows_process_snapshot", lambda: ())
    monkeypatch.setattr(
        empirical_data_control,
        "assess_project_control_safety",
        lambda *_args: ProjectControlSafety(True, "PROJECT_RECORDED_STOPPED", "STOPPED", False),
    )
    monkeypatch.setattr(empirical_data_control.importlib, "import_module", lambda name: mt5)
    result = empirical_data_control.main([
        "inspect",
        "--confirm-read-only-demo-export",
        "--output-root",
        str(tmp_path),
    ])
    assert result == 0
    assert '"status":"TOOL_VERIFIED"' in capsys.readouterr().out
    called = {name for name, _args, _kwargs in mt5.calls}
    assert called <= PERMITTED_MT5_OPERATIONS
    assert "initialize" in called
    assert "shutdown" in called


@pytest.mark.unit
def test_non_xau_symbols_cannot_enter_tick_export(tmp_path):
    mt5, gateway, exporter = _exporter(tmp_path)
    inspection = exporter.inspect()
    assert set(inspection.mappings) == {
        "XAUUSDm", "EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF"
    }
    assert all(base != "XAUUSDm" for base in inspection.mappings if base != "XAUUSDm")
    assert exporter.config.output_root == tmp_path
    gateway.shutdown()
