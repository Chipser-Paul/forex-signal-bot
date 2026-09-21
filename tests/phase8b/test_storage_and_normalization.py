from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from bot.acquisition.exporter import (
    EmpiricalExporter,
    compare_tick_derived_bars,
    normalize_rates,
    normalize_ticks,
)
from bot.acquisition.gateway import ReadOnlyMT5Gateway
from bot.acquisition.models import AcquisitionError, CoverageReport, ExportConfig
from bot.acquisition.storage import ChunkStore, validate_output_root

from .helpers import FakeReadOnlyMT5, tick


UTC = timezone.utc
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


@pytest.mark.unit
def test_repository_outputs_are_rejected(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    with pytest.raises(AcquisitionError, match="Git"):
        validate_output_root(repository / "data", forbidden_roots=(repository,))


@pytest.mark.unit
def test_chunk_write_is_atomic_non_overwriting_and_resumable(tmp_path):
    store = ChunkStore(tmp_path, maximum_output_bytes=1024 * 1024)
    records = ({"timestamp": "2026-01-01T00:00:00Z", "bid": 1.0, "ask": 1.1},)
    summary = store.write(
        "ticks/a.jsonl.gz",
        records,
        chunk_id="a",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
    )
    assert store.verify("ticks/a.jsonl.gz") == summary
    assert store.write(
        "ticks/a.jsonl.gz",
        records,
        chunk_id="a",
        start=summary.start,
        end=summary.end,
        resume=True,
    ) == summary
    with pytest.raises(FileExistsError):
        store.write("ticks/a.jsonl.gz", records, chunk_id="a", start=summary.start, end=summary.end)
    assert not list(tmp_path.rglob("*.partial"))


@pytest.mark.unit
def test_partial_or_tampered_chunk_is_never_complete(tmp_path):
    store = ChunkStore(tmp_path, maximum_output_bytes=1024 * 1024)
    partial = tmp_path / "ticks" / "a.jsonl.gz.partial"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"partial")
    with pytest.raises(AcquisitionError, match="incomplete"):
        store.verify("ticks/a.jsonl.gz")
    partial.unlink()
    store.write(
        "ticks/a.jsonl.gz",
        ({"a": 1},),
        chunk_id="a",
        start=NOW,
        end=NOW + timedelta(seconds=1),
    )
    with (tmp_path / "ticks" / "a.jsonl.gz").open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(AcquisitionError, match="hash"):
        store.verify("ticks/a.jsonl.gz")


@pytest.mark.unit
def test_disk_budget_stops_before_finalization(tmp_path):
    store = ChunkStore(tmp_path, maximum_output_bytes=1)
    with pytest.raises(AcquisitionError, match="budget"):
        store.write(
            "ticks/a.jsonl.gz",
            ({"payload": "x" * 100},),
            chunk_id="a",
            start=NOW,
            end=NOW + timedelta(seconds=1),
        )
    assert not list(tmp_path.rglob("*.jsonl.gz"))


@pytest.mark.unit
def test_ticks_are_utc_ordered_and_have_stable_distinct_identities():
    raw = [tick(NOW + timedelta(milliseconds=1), 2.0, 2.2), tick(NOW, 1.0, 1.2), tick(NOW, 1.0, 1.2)]
    records, diagnostics = normalize_ticks(raw, symbol="XAUUSDm", chunk_id="chunk")
    assert [record["time_msc"] for record in records] == sorted(record["time_msc"] for record in records)
    assert len({record["sequence_id"] for record in records}) == 3
    assert diagnostics["duplicate_count"] == 1
    assert records[0]["timestamp"].endswith("Z")


@pytest.mark.unit
def test_tick_validation_rejects_wrong_symbol_crossed_and_zero_quotes():
    with pytest.raises(AcquisitionError, match="exact XAUUSDm"):
        normalize_ticks([], symbol="XAUUSD", chunk_id="chunk")
    with pytest.raises(AcquisitionError, match="crossed or zero"):
        normalize_ticks([tick(NOW, 2.0, 1.0)], symbol="XAUUSDm", chunk_id="chunk")
    with pytest.raises(AcquisitionError, match="crossed or zero"):
        normalize_ticks([tick(NOW, 0.0, 1.0)], symbol="XAUUSDm", chunk_id="chunk")


@pytest.mark.unit
def test_native_bars_use_phase2_causal_availability():
    raw = [
        {"time": int(NOW.timestamp()), "open": 2000, "high": 2002, "low": 1999, "close": 2001},
        {"time": int((NOW + timedelta(minutes=5)).timestamp()), "open": 2001, "high": 2003, "low": 2000, "close": 2002},
    ]
    records = normalize_rates(raw, symbol="XAUUSDm", timeframe="M5", end_exclusive=NOW + timedelta(minutes=10))
    assert records[0]["available_at"] == (NOW + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    assert records[-1]["available_at"] == (NOW + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")


@pytest.mark.unit
def test_tick_derived_native_bar_comparison_reports_discrepancy():
    ticks, _ = normalize_ticks(
        [
            tick(NOW, 2000.0, 2000.2),
            tick(NOW + timedelta(minutes=4), 2002.0, 2002.2),
        ],
        symbol="XAUUSDm",
        chunk_id="sample",
    )
    native = ({
        "open_time": NOW.isoformat().replace("+00:00", "Z"),
        "open": 2000.0,
        "high": 2001.0,
        "low": 2000.0,
        "close": 2001.0,
    },)
    comparison = compare_tick_derived_bars(ticks, native, timeframe="M5", price_tolerance=0.0)
    assert comparison["compared_bars"] == 1
    assert comparison["discrepancy_count"] == 1


@pytest.mark.unit
def test_symbol_mapping_is_exact_and_ambiguity_fails_closed(tmp_path):
    mt5 = FakeReadOnlyMT5()
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    exporter = EmpiricalExporter(gateway, ExportConfig(output_root=tmp_path))
    assert exporter.inspect().status.value == "TOOL_VERIFIED"
    mt5.symbols["EURUSD.a"] = mt5.symbols.pop("EURUSD")
    mt5.symbols["EURUSD.b"] = type(mt5.symbols["EURUSD.a"])(**vars(mt5.symbols["EURUSD.a"]))
    mt5.symbols["EURUSD.a"].name = "EURUSD.a"
    mt5.symbols["EURUSD.b"].name = "EURUSD.b"
    inspection = exporter.inspect()
    assert inspection.status.value == "MAPPING_AMBIGUOUS"
    assert inspection.ambiguous_symbols == ("EURUSD",)


@pytest.mark.unit
def test_estimate_is_conservative_and_budget_aware(tmp_path, monkeypatch):
    mt5 = FakeReadOnlyMT5()
    mt5.ticks = [tick(NOW + timedelta(seconds=1))]
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    exporter = EmpiricalExporter(
        gateway,
        ExportConfig(
            output_root=tmp_path,
            start=NOW,
            end=NOW + timedelta(hours=1),
            maximum_output_bytes=1024,
        ),
    )
    monkeypatch.setattr(exporter.store, "free_bytes", lambda: 10 * 1024**3)
    sample = exporter.write_sample(NOW, NOW + timedelta(minutes=15))
    coverage = CoverageReport(
        requested_start=NOW,
        requested_end=NOW + timedelta(hours=1),
        earliest_available=NOW,
        latest_available=NOW,
        active_days=1,
        probe_count=1,
        empty_probe_count=0,
        maximum_probe_span_seconds=3600,
    )
    estimate = exporter.estimate(sample, coverage)
    assert estimate.estimated_bytes > estimate.sample_bytes
    assert not estimate.safe_to_continue
