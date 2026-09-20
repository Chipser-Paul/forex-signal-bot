"""Tests for streaming tick-to-candle aggregation, gap semantics,
manifest publication and determinism across package groupings.

All ticks are synthetic.  No real dataset, no MT5, no network.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from bot.acquisition.candle_manifest import (
    build_derived_candle_manifest,
    verify_derived_candle_manifest,
)
from bot.acquisition.candle_pipeline import (
    _detect_gaps,
    aggregate_ticks_to_candles,
    stable_candle_identity,
)
from bot.acquisition.candle_store import (
    ParquetBidAskCandleStore,
    canonical_candle_hash,
)
from bot.acquisition.exness_archive import exness_tick_schema
from bot.acquisition.models import AcquisitionError

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Synthetic tick fixtures
# ---------------------------------------------------------------------------

def _tick_rows(rows):
    """rows: sequence of (datetime, bid Decimal, ask Decimal)."""
    out = []
    for index, (timestamp, bid, ask) in enumerate(rows):
        out.append({
            "source": "EXNESS_TEST",
            "symbol": "XAUUSDm",
            "timestamp_raw": timestamp.isoformat(),
            "timestamp": timestamp,
            "time_msc": int(timestamp.timestamp() * 1000),
            "bid_raw": str(bid),
            "ask_raw": str(ask),
            "bid": bid,
            "ask": ask,
            "sequence_id": index,
            "row_identity": f"test-row-{index}",
            "source_member": "test.csv.gz",
            "member_sha256": "0" * 64,
            "archive_sha256": "1" * 64,
            "provenance_id": "test-provenance",
        })
    return out


def _write_tick_package(root: Path, package_id: str, partitions) -> Path:
    """partitions: sequence of (relative_path, rows)."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    package_root = root / package_id
    schema = exness_tick_schema()
    for relative_path, rows in partitions:
        target = package_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pydict(
            {field.name: [row[field.name] for row in rows] for field in schema},
            schema=schema,
        )
        pq.write_table(table, target)
    manifest = {
        "package_id": package_id,
        "claimed_month": package_id[-2:],
        "partitions": [
            {"relative_path": relative_path} for relative_path, _ in partitions
        ],
    }
    (package_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return package_root


def _valid_record(open_ms: int, close_ms: int) -> dict:
    return {
        "symbol": "XAUUSDm",
        "timeframe": "M5",
        "open_time_ms": open_ms,
        "close_time_ms": close_ms,
        "available_at_ms": close_ms,
        "bid_open": "2000.00",
        "bid_high": "2001.00",
        "bid_low": "1999.00",
        "bid_close": "2000.50",
        "ask_open": "2000.10",
        "ask_high": "2001.10",
        "ask_low": "1999.10",
        "ask_close": "2000.60",
        "tick_count": 10,
        "spread_min": "0.10",
        "spread_max": "0.10",
        "spread_median": "0.10",
        "spread_close": "0.10",
        "first_tick_ms": open_ms + 50,
        "last_tick_ms": close_ms - 50,
        "source_package_ids": ["pkg1"],
        "schema_version": "phase8c.bidask-candles.v1",
        "candle_identity": stable_candle_identity("XAUUSDm", "M5", open_ms, close_ms),
    }


# ---------------------------------------------------------------------------
# Streaming aggregation and causality
# ---------------------------------------------------------------------------

def test_streaming_aggregation_emits_only_completed_windows(tmp_path):
    tick = datetime(2024, 1, 1, 10, 1, tzinfo=UTC)
    rows = _tick_rows([
        (tick, Decimal("2000.10"), Decimal("2000.20")),
        (tick, Decimal("2000.10"), Decimal("2000.20")),  # exact duplicate tick
        (datetime(2024, 1, 1, 10, 2, tzinfo=UTC), Decimal("2000.50"), Decimal("2000.60")),
        (datetime(2024, 1, 1, 10, 21, tzinfo=UTC), Decimal("2010.00"), Decimal("2010.10")),
    ])
    package = _write_tick_package(
        tmp_path, "exness-test-2024-01",
        [("ticks/year=2024/month=01/part-00000.parquet", rows)],
    )
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))

    records = list(aggregate_ticks_to_candles(
        [(package, manifest)], "M5", year_package_id="year-pkg"
    ))

    # The 10:00-10:05 window is completed by the 10:20 tick crossing the
    # boundary and is emitted; the final 10:20 window is the terminal partial
    # window and MUST be discarded (never forward-filled, never synthesized).
    assert len(records) == 1
    first = records[0]
    assert first["open_time_ms"] == int(datetime(2024, 1, 1, 10, 0, tzinfo=UTC).timestamp() * 1000)
    assert first["close_time_ms"] == int(datetime(2024, 1, 1, 10, 5, tzinfo=UTC).timestamp() * 1000)
    # available_at == close_time (conservative causal availability)
    assert first["available_at_ms"] == first["close_time_ms"]
    # Duplicates count as multiple observations; bid/ask stay separate.
    assert first["tick_count"] == 3
    assert first["bid_open"] == "2000.10000000"
    assert first["ask_open"] == "2000.20000000"
    assert first["bid_close"] == "2000.50000000"
    assert Decimal(first["ask_close"]) > Decimal(first["bid_close"])
    # Provenance is recorded.
    assert first["source_package_ids"] == ["exness-test-2024-01"]


def test_streaming_rejects_out_of_order_partitions(tmp_path):
    early = _tick_rows([
        (datetime(2024, 1, 1, 10, 2, tzinfo=UTC), Decimal("2000.00"), Decimal("2000.10")),
    ])
    late = _tick_rows([
        (datetime(2024, 1, 1, 10, 1, tzinfo=UTC), Decimal("2000.00"), Decimal("2000.10")),
    ])
    package = _write_tick_package(
        tmp_path, "exness-test-2024-01",
        [
            ("ticks/year=2024/month=01/part-00000.parquet", early),
            ("ticks/year=2024/month=01/part-00001.parquet", late),
        ],
    )
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))

    with pytest.raises(AcquisitionError, match="chronological order"):
        list(aggregate_ticks_to_candles(
            [(package, manifest)], "M5", year_package_id="year-pkg"
        ))


def test_gap_detection_between_emitted_windows():
    dur_ms = 5 * 60 * 1000
    base = int(datetime(2024, 1, 1, 10, 0, tzinfo=UTC).timestamp() * 1000)
    emitted = [base, base + 4 * dur_ms]
    gaps = _detect_gaps("M5", emitted, datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                        datetime(2024, 1, 1, 11, 0, tzinfo=UTC))
    assert len(gaps) == 1
    assert gaps[0].gap_open_ms == base + dur_ms
    assert gaps[0].missing_window_count == 3


# ---------------------------------------------------------------------------
# Determinism across package groupings
# ---------------------------------------------------------------------------

def test_aggregation_independent_of_package_grouping(tmp_path):
    rows = _tick_rows([
        (datetime(2024, 1, 1, 10, 1, tzinfo=UTC), Decimal("2000.10"), Decimal("2000.20")),
        (datetime(2024, 1, 1, 10, 3, tzinfo=UTC), Decimal("2000.40"), Decimal("2000.50")),
    ])
    package_a = _write_tick_package(
        tmp_path, "exness-test-2024-01",
        [("ticks/year=2024/month=01/part-00000.parquet", rows)],
    )
    package_b = _write_tick_package(
        tmp_path, "exness-test-2024-01-recovery-0002",
        [("ticks/year=2024/month=01/part-00000.parquet", rows)],
    )
    manifest_a = json.loads((package_a / "manifest.json").read_text(encoding="utf-8"))
    manifest_b = json.loads((package_b / "manifest.json").read_text(encoding="utf-8"))

    records_a = list(aggregate_ticks_to_candles(
        [(package_a, manifest_a)], "M5", year_package_id="year-pkg"
    ))
    records_b = list(aggregate_ticks_to_candles(
        [(package_b, manifest_b)], "M5", year_package_id="year-pkg"
    ))
    assert [r["candle_identity"] for r in records_a] == [
        r["candle_identity"] for r in records_b
    ]
    assert canonical_candle_hash(records_a) == canonical_candle_hash(records_b)


# ---------------------------------------------------------------------------
# Manifest publication (atomic, non-overwriting, verifiable)
# ---------------------------------------------------------------------------

def test_manifest_publication_and_tamper_detection(tmp_path):
    store = ParquetBidAskCandleStore(
        tmp_path / "candles", maximum_output_bytes=10 * 1024**2, minimum_free_bytes=0
    )
    record = _valid_record(1000000, 1300000)
    summary = store.write(
        "XAUUSDm/M5/year=2024/part-00000.parquet",
        [record], partition_id="xauusdm-m5-2024", timeframe="M5",
    )
    gap_info = {"gap_count": 0, "missing_window_count": 0,
                "partial_initial_window": False, "partial_terminal_window": True}

    manifest = build_derived_candle_manifest(
        tmp_path,
        year_package_id="year-pkg",
        source_canonical_sha256="a" * 64,
        source_row_count=10,
        git_commit="0" * 40,
        timeframe_summaries=[(summary, gap_info)],
        monthly_package_ids=["pkg1"],
    )
    assert manifest["classification"] == "DEVELOPMENT_ONLY"
    assert "NOT PROFITABILITY EVIDENCE" in manifest["label"]
    assert (tmp_path / "manifest.json").is_file()
    assert (tmp_path / "pipeline.complete.json").is_file()

    # Idempotent re-invocation returns the existing manifest.
    again = build_derived_candle_manifest(
        tmp_path,
        year_package_id="year-pkg",
        source_canonical_sha256="a" * 64,
        source_row_count=10,
        git_commit="0" * 40,
        timeframe_summaries=[(summary, gap_info)],
        monthly_package_ids=["pkg1"],
    )
    assert again == manifest

    # Round-trip verification succeeds.
    assert verify_derived_candle_manifest(tmp_path) == manifest

    # Any tampering with the manifest must fail verification.
    manifest_path = tmp_path / "manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["source_row_count"] = 11
    manifest_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    with pytest.raises(AcquisitionError, match="SHA-256 mismatch"):
        verify_derived_candle_manifest(tmp_path)
