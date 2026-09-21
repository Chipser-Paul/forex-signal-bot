from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backtests import empirical_data_control
from bot.acquisition.exporter import EmpiricalExporter
from bot.acquisition.models import AcquisitionError
from bot.acquisition.models import ExportConfig
from bot.acquisition.plan import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    PROPOSED_HOLDOUT_END,
    PROPOSED_HOLDOUT_START,
    DataInterval,
    append_access_record,
    calibration_blocks,
    chunk_ranges,
    classify_interval,
    require_development_access,
)


UTC = timezone.utc


@pytest.mark.unit
def test_weekly_chunks_are_closed_open_contiguous_and_cross_year_safely():
    start = datetime(2020, 12, 28, tzinfo=UTC)
    end = datetime(2021, 1, 12, tzinfo=UTC)
    chunks = chunk_ranges(start, end, days=7)
    assert [(item.start, item.end) for item in chunks] == [
        (start, datetime(2021, 1, 4, tzinfo=UTC)),
        (datetime(2021, 1, 4, tzinfo=UTC), datetime(2021, 1, 11, tzinfo=UTC)),
        (datetime(2021, 1, 11, tzinfo=UTC), end),
    ]
    assert all(left.end == right.start for left, right in zip(chunks, chunks[1:]))


@pytest.mark.unit
def test_utc_chunks_are_dst_independent_and_naive_values_fail_closed():
    start = datetime(2024, 3, 8, tzinfo=UTC)
    chunks = chunk_ranges(start, start + timedelta(days=14), days=7)
    assert all((item.end - item.start) == timedelta(days=7) for item in chunks)
    with pytest.raises(AcquisitionError, match="UTC"):
        chunk_ranges(start.replace(tzinfo=None), start + timedelta(days=1), days=7)


@pytest.mark.unit
def test_calibration_blocks_are_deterministic_calendar_only_development_weeks():
    first = calibration_blocks()
    assert first == calibration_blocks()
    assert len(first) == 24
    assert all(item.start.weekday() == 0 and item.end - item.start == timedelta(days=7) for item in first)
    assert all(DEVELOPMENT_START <= item.start < item.end <= DEVELOPMENT_END for item in first)
    assert {(item.start.year, item.start.month) for item in first} == {
        (year, month) for year in range(2019, 2025) for month in (1, 4, 7, 10)
    }


@pytest.mark.unit
def test_development_and_holdout_separation_fails_before_acquisition():
    dev = require_development_access(DEVELOPMENT_START, DEVELOPMENT_END, operation="test")
    assert classify_interval(dev) == "DEVELOPMENT"
    holdout = DataInterval(PROPOSED_HOLDOUT_START, PROPOSED_HOLDOUT_END)
    assert classify_interval(holdout) == "PROPOSED_UNTOUCHED_HOLDOUT"
    with pytest.raises(AcquisitionError, match="development"):
        require_development_access(holdout.start, holdout.end, operation="benchmark")


@pytest.mark.unit
def test_access_log_is_atomic_idempotent_and_prohibits_strategy_evaluation(tmp_path):
    path = tmp_path / "access.json"
    record = {
        "access_id": "bounded-dev-sample",
        "start": DEVELOPMENT_START,
        "end_exclusive": DEVELOPMENT_START + timedelta(hours=1),
        "classification": "DEVELOPMENT",
        "purpose": "storage-throughput-benchmark",
        "strategy_evaluated": False,
    }
    append_access_record(path, record)
    append_access_record(path, record)
    assert len(json.loads(path.read_text(encoding="utf-8"))) == 1
    with pytest.raises(AcquisitionError, match="strategy evaluation"):
        append_access_record(path, {**record, "access_id": "forbidden", "strategy_evaluated": True})
    assert not list(tmp_path.rglob("*.partial"))


@pytest.mark.unit
def test_machine_readable_plan_matches_frozen_intervals():
    raw = json.loads(
        (Path(__file__).resolve().parents[2] / "baseline" / "phase8b_hybrid_acquisition_plan.json")
        .read_text(encoding="utf-8")
    )
    assert raw["development"]["start"] == "2019-01-01T00:00:00Z"
    assert raw["proposed_untouched_tick_holdout"]["end_exclusive"] == "2026-08-01T00:00:00Z"
    assert raw["proposed_untouched_tick_holdout"]["performance_access_permitted"] is False
    assert raw["tick_calibration"]["continuous_coverage_claimed"] is False


@pytest.mark.unit
def test_calibration_export_requests_only_preregistered_blocks(tmp_path, monkeypatch):
    exporter = EmpiricalExporter(
        object(),
        ExportConfig(output_root=tmp_path, start=DEVELOPMENT_START, end=DEVELOPMENT_END,
                     tick_chunk_days=7, bulk_format="parquet-zstd", minimum_free_bytes=0),
    )
    requested = []
    monkeypatch.setattr(
        exporter,
        "_export_tick_interval",
        lambda start, end, *, resume: requested.append((start, end, resume)) or (),
    )
    assert exporter.export_calibration_ticks(resume=False) == ()
    assert [(start, end) for start, end, _resume in requested] == [
        (item.start, item.end) for item in calibration_blocks()
    ]
    assert all(end <= DEVELOPMENT_END for _start, end, _resume in requested)


@pytest.mark.unit
def test_show_plan_is_offline_and_never_imports_mt5(tmp_path, monkeypatch, capsys):
    imported = []
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    monkeypatch.setattr(empirical_data_control.importlib, "import_module", lambda name: imported.append(name))
    assert empirical_data_control.main(["show-plan", "--output-root", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "HYBRID_PLAN_PROPOSED"
    assert payload["plan"]["proposed_untouched_tick_holdout"]["performance_access_permitted"] is False
    assert imported == []
