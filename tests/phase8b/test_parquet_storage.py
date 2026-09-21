from __future__ import annotations

import builtins
import json
from datetime import datetime, timedelta, timezone

import pytest

from bot.acquisition.columnar import (
    BAR_SCHEMA_VERSION,
    TICK_SCHEMA_VERSION,
    ParquetBarStore,
    ParquetTickStore,
    _arrow,
    canonical_tick_hash,
    iter_historical_quotes,
    read_tick_records,
)
from bot.acquisition.exporter import EmpiricalExporter, normalize_ticks
from bot.acquisition.gateway import ReadOnlyMT5Gateway
from bot.acquisition.models import AcquisitionError, ExportConfig
from bot.validation.datasets import _load_records
from bot.validation.models import DataStreamKind, DataStreamManifest

from .helpers import FakeReadOnlyMT5, tick


UTC = timezone.utc
START = datetime(2024, 8, 5, tzinfo=UTC)


def _records(chunk_id="fixture"):
    return normalize_ticks(
        [tick(START, 2400.12345, 2400.22345), tick(START + timedelta(milliseconds=1), 2400.2, 2400.3)],
        symbol="XAUUSDm",
        chunk_id=chunk_id,
    )


@pytest.mark.unit
def test_parquet_zstd_schema_hash_atomic_publication_and_phase7_reader(tmp_path):
    records, diagnostics = _records()
    store = ParquetTickStore(tmp_path, maximum_output_bytes=1024**2)
    summary = store.write(
        "ticks/XAUUSDm/year=2024/month=08/iso_week=2024-W32/fixture.parquet",
        records,
        chunk_id="fixture",
        requested_start=START,
        requested_end=START + timedelta(hours=1),
        diagnostics=diagnostics,
    )
    verified = store.verify(summary.relative_path)
    marker = json.loads((tmp_path / (summary.relative_path + ".complete.json")).read_text(encoding="utf-8"))
    assert verified == summary
    assert summary.schema_version == TICK_SCHEMA_VERSION
    assert summary.compression == "zstd"
    assert marker["canonical_content_sha256"] == canonical_tick_hash(records)
    assert canonical_tick_hash(read_tick_records(tmp_path / summary.relative_path)) == summary.canonical_content_sha256
    quotes = tuple(iter_historical_quotes(tmp_path / summary.relative_path))
    assert len(quotes) == 2 and quotes[0].bid == pytest.approx(2400.12345)
    stream = DataStreamManifest(
        name="ticks", kind=DataStreamKind.EXECUTION_QUOTES, relative_path=summary.relative_path,
        sha256=summary.sha256, symbol="XAUUSDm", start=START,
        end=START + timedelta(hours=1), record_count=2, provenance="fixture",
        license_or_restrictions="TEST_ONLY",
    )
    assert len(_load_records(tmp_path / summary.relative_path, stream)) == 2
    assert not list(tmp_path.rglob("*.partial"))


@pytest.mark.unit
def test_parquet_resume_rejects_partial_and_hash_mismatch(tmp_path):
    records, diagnostics = _records()
    store = ParquetTickStore(tmp_path, maximum_output_bytes=1024**2)
    relative = "ticks/XAUUSDm/test.parquet"
    partial = tmp_path / (relative + ".partial")
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"interrupted")
    with pytest.raises(AcquisitionError, match="partial"):
        store.write(relative, records, chunk_id="fixture", requested_start=START,
                    requested_end=START + timedelta(hours=1), diagnostics=diagnostics, resume=True)
    partial.unlink()
    summary = store.write(relative, records, chunk_id="fixture", requested_start=START,
                          requested_end=START + timedelta(hours=1), diagnostics=diagnostics)
    assert store.write(relative, records, chunk_id="fixture", requested_start=START,
                       requested_end=START + timedelta(hours=1), diagnostics=diagnostics, resume=True) == summary
    with (tmp_path / relative).open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(AcquisitionError, match="hash"):
        store.verify(relative)


@pytest.mark.unit
def test_empty_tick_partition_is_explicit_and_verified(tmp_path):
    store = ParquetTickStore(tmp_path, maximum_output_bytes=1024**2)
    summary = store.write("empty.parquet", (), chunk_id="empty", requested_start=START,
                          requested_end=START + timedelta(days=7))
    assert summary.record_count == 0
    assert summary.start == START and summary.end == START + timedelta(days=7)
    assert store.verify("empty.parquet").record_count == 0


@pytest.mark.unit
def test_parquet_bar_schema_and_canonical_verification(tmp_path):
    records = ({
        "symbol": "XAUUSDm", "timeframe": "M5", "open_time": START.isoformat(),
        "available_at": (START + timedelta(minutes=5)).isoformat(), "open": 2400.1,
        "high": 2401.0, "low": 2399.5, "close": 2400.5, "tick_volume": 10,
        "spread": 20, "real_volume": 0, "sequence_id": "bar-1",
    },)
    store = ParquetBarStore(tmp_path, maximum_output_bytes=1024**2)
    summary = store.write("bars/XAUUSDm/M5/test.parquet", records, chunk_id="bar",
                          requested_start=START, requested_end=START + timedelta(minutes=5))
    assert summary.schema_version == BAR_SCHEMA_VERSION
    assert store.verify(summary.relative_path) == summary


@pytest.mark.unit
def test_optional_dependency_has_actionable_failure(monkeypatch):
    original = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "pyarrow" or name.startswith("pyarrow."):
            raise ImportError("fixture")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(AcquisitionError, match="requirements-data"):
        _arrow()


@pytest.mark.unit
def test_weekly_export_falls_back_to_smaller_verified_partitions(tmp_path):
    mt5 = FakeReadOnlyMT5()
    mt5.ticks = [tick(START + timedelta(hours=1)), tick(START + timedelta(days=1, hours=1))]
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    exporter = EmpiricalExporter(
        gateway,
        ExportConfig(output_root=tmp_path, start=START, end=START + timedelta(days=2),
                     tick_chunk_days=2, bulk_format="parquet-zstd", maximum_rows_per_tick_chunk=1,
                     maximum_output_bytes=1024**2, minimum_free_bytes=0),
    )
    summaries = exporter.export_ticks(resume=False)
    assert len(summaries) == 2
    assert summaries[0].requested_end == summaries[1].requested_start
    assert all(item.storage_format == "parquet" for item in summaries)
    gateway.shutdown()
