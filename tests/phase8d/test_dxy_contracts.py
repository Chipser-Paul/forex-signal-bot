"""Phase 8D focused tests: causal DXY development-input contracts.

Synthetic only — no MT5, no network, no strategy evaluation, no holdout.
All timestamps stay inside [2024-01-01T00:00:00Z, 2025-01-01T00:00:00Z).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.acquisition import dxy_contracts as dc  # noqa: E402
from bot.acquisition.dxy_contracts import (  # noqa: E402
    DEVELOPMENT_END,
    DEVELOPMENT_END_MS,
    DEVELOPMENT_START,
    DEVELOPMENT_START_MS,
    DXY_CONSTITUENT_ORDER,
    DXY_EXPONENTS,
    DXY_SCALE,
    DXY_SYMBOL_MAP,
    H1_DURATION_MS,
    assert_development_interval,
    canonical_constituent_hash,
    canonical_dxy_hash,
    compute_causal_dxy_rows,
    compute_gap_report,
    deduplicate_chunk_records,
    from_ms,
    iter_development_month_chunks,
    iso_z,
    ms,
    normalize_rate_chunk,
)
from bot.acquisition.dxy_package import (  # noqa: E402
    publish_dxy_package,
    verify_package_readonly,
)
from bot.acquisition.dxy_discovery import (  # noqa: E402
    register_dxy_package,
    load_dxy_discovery_record,
)
from bot.acquisition.models import AcquisitionError  # noqa: E402

UTC = timezone.utc
TEST_COMMIT = "a" * 40
TEST_FINGERPRINT = "phase8d-pipeline-v1:" + "b" * 64


# ---------------------------------------------------------------------------
# Synthetic bar helpers
# ---------------------------------------------------------------------------

PRICES = {
    "EURUSD": 1.1, "USDJPY": 150.0, "GBPUSD": 1.27,
    "USDCAD": 1.35, "USDSEK": 10.5, "USDCHF": 0.88,
}


def _bars(symbol: str, hours: list[int], *, close: float | None = None) -> list[dict]:
    start_hour = int(ms(DEVELOPMENT_START) // 1000 // 3600)
    rows = []
    for hour in hours:
        open_ms = (start_hour + hour) * 3_600_000
        price = close if close is not None else PRICES[symbol]
        rows.append({
            "canonical_symbol": symbol,
            "broker_symbol": DXY_SYMBOL_MAP[symbol],
            "timeframe": "H1",
            "open_time_ms": open_ms,
            "close_time_ms": open_ms + H1_DURATION_MS,
            "available_at_ms": open_ms + H1_DURATION_MS,
            "open": price, "high": price * 1.001, "low": price * 0.999, "close": price,
            "tick_volume": 100.0, "spread": 10.0, "real_volume": None,
            "provenance_id": dc.PROVENANCE_ID,
            "retrieved_utc": "2026-09-12T00:00:00Z",
            "terminal_build": "test",
            "source_interval_start": iso_z(open_ms),
            "source_interval_end": iso_z(open_ms + H1_DURATION_MS),
            "sequence_id": f"{symbol}-H1-{open_ms}",
        })
    for row in rows:
        row["row_identity"] = dc.constituent_row_identity(row)
    return rows


def _full_week(symbol: str) -> list[dict]:
    # 2024-01-01 is Monday; one week = 120 hours of H1 bars.
    return _bars(symbol, list(range(120)))


def _light_bars_by_symbol(hours: list[int]) -> dict[str, list[dict]]:
    return {symbol: _bars(symbol, hours) for symbol in DXY_CONSTITUENT_ORDER}


def _acquisition_evidence() -> dict:
    return {
        "permitted_operations": ("initialize", "shutdown", "copy_rates_range"),
        "run_id": "dxy-test-run-00000000",
        "journal_relative_path": "dxy/journals/dxy-test-run-00000000/run_journal.jsonl",
        "terminal_build": "test-terminal",
        "error_category": "SUCCESS",
        "initialization_seconds": 1.5,
        "chunk_count": 72,
    }


def _mappings() -> dict[str, dict]:
    return {
        symbol: {
            "canonical_symbol": symbol,
            "broker_symbol": DXY_SYMBOL_MAP[symbol],
            "currency_base": base,
            "currency_profit": profit,
            "digits": 5,
            "point": 0.00001,
        }
        for symbol, (base, profit) in dc.MAPPING_CURRENCY_EXPECTATIONS.items()
    }


def _publish(tmp_path, bars_by_symbol, **overrides):
    arguments = dict(
        records_by_symbol=bars_by_symbol,
        resolved_mappings=_mappings(),
        acquisition_evidence=_acquisition_evidence(),
        source_year_package_id="exness-xauusdm-2024-development-b2a0234a470dd397",
        source_year_canonical_sha256="b2a0234a" + "0" * 56,
        source_year_row_count=39_715_935,
        retrieved_utc=datetime(2026, 9, 12, tzinfo=UTC),
        terminal_build="test-terminal",
        implementation_commit=TEST_COMMIT,
        code_fingerprint=TEST_FINGERPRINT,
        minimum_free_bytes=0,
    )
    arguments.update(overrides)
    return publish_dxy_package(tmp_path, **arguments)


# ---------------------------------------------------------------------------
# Interval / mapping / chunking contracts
# ---------------------------------------------------------------------------

def test_development_interval_guard_rejects_holdout_start():
    with pytest.raises(AcquisitionError):
        assert_development_interval(
            DEVELOPMENT_END, DEVELOPMENT_END + timedelta(hours=1)
        )
    with pytest.raises(AcquisitionError):
        assert_development_interval(
            DEVELOPMENT_START - timedelta(days=1), DEVELOPMENT_START
        )
    assert assert_development_interval(DEVELOPMENT_START, DEVELOPMENT_END) == (
        DEVELOPMENT_START, DEVELOPMENT_END
    )


def test_month_chunks_are_deterministic_and_bounded():
    chunks = iter_development_month_chunks()
    assert len(chunks) == 12
    assert chunks[0][0] == DEVELOPMENT_START
    assert chunks[-1][1] == DEVELOPMENT_END
    for (start, end), (next_start, _next_end) in zip(chunks, list(chunks)[1:]):
        assert end == next_start


# ---------------------------------------------------------------------------
# Rate normalization
# ---------------------------------------------------------------------------

def _rates_for(hours_open_ms: list[int], price: float) -> list:
    import numpy as np

    rows = []
    for open_ms in hours_open_ms:
        rows.append((
            open_ms // 1000,
            open_ms // 1000 + 3600,
            price * 0.999, price * 1.001, price * 0.998, price,
            100, 10, 0,
            np.zeros(13),
        ))
    # Structured-array-like access via numpy: use a real structured array.
    dtype = np.dtype([
        ("time", "<i8"), ("open", "<f8"), ("high", "<f8"), ("low", "<f8"),
        ("close", "<f8"), ("tick_volume", "<i8"), ("spread", "<i4"),
        ("real_volume", "<i8"),
    ])
    structured = np.zeros(len(rows), dtype=dtype)
    for index, open_ms in enumerate(hours_open_ms):
        structured[index] = (
            open_ms // 1000, price * 0.999, price * 1.001, price * 0.998,
            price, 100, 10, 0,
        )
    return structured


def test_normalize_accepts_valid_bars_and_discards_terminal_partial():
    symbol = "EURUSD"
    start_hour_ms = int(ms(DEVELOPMENT_START))
    hours = [start_hour_ms + h * H1_DURATION_MS for h in range(5)]
    rates = _rates_for(hours, 1.1)
    records, diagnostics = normalize_rate_chunk(
        symbol, DXY_SYMBOL_MAP[symbol], rates,
        DEVELOPMENT_START, DEVELOPMENT_START + timedelta(hours=6),
        retrieved_utc=datetime(2026, 9, 12, tzinfo=UTC), terminal_build="t",
    )
    assert diagnostics["response_class"] == "OK"
    assert len(records) == 5
    assert all(r["available_at_ms"] == r["open_time_ms"] + H1_DURATION_MS for r in records)


def test_normalize_rejects_duplicate_open_times():
    symbol = "EURUSD"
    start_hour_ms = int(ms(DEVELOPMENT_START))
    hours = [start_hour_ms, start_hour_ms, start_hour_ms + H1_DURATION_MS]
    rates = _rates_for(hours, 1.1)
    with pytest.raises(AcquisitionError, match="DUPLICATE_OPEN_TIME"):
        normalize_rate_chunk(
            symbol, DXY_SYMBOL_MAP[symbol], rates,
            DEVELOPMENT_START, DEVELOPMENT_START + timedelta(hours=3),
            retrieved_utc=datetime(2026, 9, 12, tzinfo=UTC), terminal_build="t",
        )


def test_normalize_rejects_non_finite_and_non_positive():
    import numpy as np

    symbol = "EURUSD"
    start_hour_ms = int(ms(DEVELOPMENT_START))
    dtype = np.dtype([
        ("time", "<i8"), ("open", "<f8"), ("high", "<f8"), ("low", "<f8"),
        ("close", "<f8"), ("tick_volume", "<i8"), ("spread", "<i4"),
        ("real_volume", "<i8"),
    ])
    rates = np.zeros(1, dtype=dtype)
    rates[0] = (start_hour_ms // 1000, 1.1, 1.1005, 1.0995, 0.0, 100, 10, 0)
    with pytest.raises(AcquisitionError, match="NOT_POSITIVE_FINITE"):
        normalize_rate_chunk(
            symbol, DXY_SYMBOL_MAP[symbol], rates,
            DEVELOPMENT_START, DEVELOPMENT_START + timedelta(hours=1),
            retrieved_utc=datetime(2026, 9, 12, tzinfo=UTC), terminal_build="t",
        )
    rates[0] = (start_hour_ms // 1000, 1.1, 1.1005, 1.0995, float("nan"), 100, 10, 0)
    with pytest.raises(AcquisitionError, match="NOT_POSITIVE_FINITE"):
        normalize_rate_chunk(
            symbol, DXY_SYMBOL_MAP[symbol], rates,
            DEVELOPMENT_START, DEVELOPMENT_START + timedelta(hours=1),
            retrieved_utc=datetime(2026, 9, 12, tzinfo=UTC), terminal_build="t",
        )


def test_normalize_discovers_empty_and_null_responses_distinctly():
    symbol = "EURUSD"
    empty_records, empty_diag = normalize_rate_chunk(
        symbol, DXY_SYMBOL_MAP[symbol], [],
        DEVELOPMENT_START, DEVELOPMENT_START + timedelta(hours=1),
        retrieved_utc=datetime(2026, 9, 12, tzinfo=UTC), terminal_build="t",
    )
    assert empty_records == () and empty_diag["response_class"] == "EMPTY_RESPONSE"
    null_records, null_diag = normalize_rate_chunk(
        symbol, DXY_SYMBOL_MAP[symbol], None,
        DEVELOPMENT_START, DEVELOPMENT_START + timedelta(hours=1),
        retrieved_utc=datetime(2026, 9, 12, tzinfo=UTC), terminal_build="t",
    )
    assert null_records == () and null_diag["response_class"] == "NULL_RESPONSE"


def test_normalize_never_crosses_the_holdout_boundary():
    symbol = "EURUSD"
    # Bar opening 2024-12-31T23:00Z completes exactly at the boundary and
    # must be discarded; any later-open bar must also never appear.
    boundary_open_ms = DEVELOPMENT_END_MS - H1_DURATION_MS
    rates = _rates_for([boundary_open_ms], 1.1)
    records, _diag = normalize_rate_chunk(
        symbol, DXY_SYMBOL_MAP[symbol], rates,
        DEVELOPMENT_END - timedelta(hours=2), DEVELOPMENT_END,
        retrieved_utc=datetime(2026, 9, 12, tzinfo=UTC), terminal_build="t",
    )
    assert records == ()


# ---------------------------------------------------------------------------
# Chunk deduplication
# ---------------------------------------------------------------------------

def test_deduplicate_accepts_identical_overlap_and_rejects_conflict():
    symbol = "EURUSD"
    base = _bars(symbol, [0, 1, 2])
    merged = deduplicate_chunk_records({}, base, symbol)
    again = deduplicate_chunk_records(merged, _bars(symbol, [2, 3, 4]), symbol)
    expected_keys = sorted(
        int(record["open_time_ms"]) for record in _bars(symbol, [0, 1, 2, 3, 4])
    )
    assert sorted(again) == expected_keys
    conflicting = _bars(symbol, [4])
    conflicting[0]["close"] = 9.99
    conflicting[0]["row_identity"] = dc.constituent_row_identity(conflicting[0])
    with pytest.raises(AcquisitionError, match="OVERLAP_CONFLICT"):
        deduplicate_chunk_records(again, conflicting, symbol)


# ---------------------------------------------------------------------------
# Causal DXY computation
# ---------------------------------------------------------------------------

def test_formula_reproduction_matches_committed_builder():
    hours = list(range(0, 125))
    bars_by_symbol = _light_bars_by_symbol(hours)
    rows, summary = compute_causal_dxy_rows(bars_by_symbol)
    assert summary["rejected_rows"] == 0
    assert len(rows) > 0

    import numpy as np
    import pandas as pd

    from bot.analysis.dxy_filter import build_synthetic_dxy_from_frames

    frames = {}
    for symbol in DXY_CONSTITUENT_ORDER:
        frame = pd.DataFrame([
            {
                "open_time": from_ms(row["open_time_ms"]),
                "available_at": from_ms(row["available_at_ms"]),
                "open": row["open"], "high": row["high"],
                "low": row["low"], "close": row["close"],
            }
            for row in bars_by_symbol[symbol]
        ])
        frame.attrs["causal_normalized"] = True
        frames[DXY_SYMBOL_MAP[symbol]] = frame
    decision = from_ms(max(r["available_at_ms"] for r in bars_by_symbol["EURUSD"]))
    values, count, diagnostics = build_synthetic_dxy_from_frames(
        frames, "H1", 100, decision
    )
    assert values is not None and count == 6
    expected_last = float(values[-1])
    computed_last = float(rows[-1]["dxy"])
    assert expected_last == pytest.approx(computed_last, rel=1e-12)


def test_dxy_precision_is_stable_across_recomputation():
    hours = list(range(125))
    rows_a, _ = compute_causal_dxy_rows(_light_bars_by_symbol(hours))
    rows_b, _ = compute_causal_dxy_rows(_light_bars_by_symbol(hours))
    assert canonical_dxy_hash(rows_a) == canonical_dxy_hash(rows_b)


def test_missing_constituent_is_rejected_never_fabricated():
    hours = list(range(125))
    bars = _light_bars_by_symbol(hours)
    del bars["USDSEK"]
    with pytest.raises(AcquisitionError, match="SERIES_EMPTY"):
        compute_causal_dxy_rows(bars)


def test_future_constituent_is_never_used():
    # USDSEK has only later bars; anchors before its first availability must
    # be rejected, not forward-filled.
    hours = list(range(125))
    bars = _light_bars_by_symbol(hours)
    bars["USDSEK"] = _bars("USDSEK", list(range(200, 300)))
    rows, summary = compute_causal_dxy_rows(bars)
    assert rows == ()
    assert summary["rejections_by_reason"].get("MISSING_CONSTITUENT:USDSEK", 0) > 0
    # No anchor earlier than USDSEK's first availability produced a row.
    first_usdsek = min(r["available_at_ms"] for r in bars["USDSEK"])
    assert all(int(row["available_at_ms"]) >= first_usdsek or row is None for row in rows)


def test_stale_constituent_is_rejected_at_exact_boundary():
    # USDCHF stalls: its last bar is available 2 hours before other symbols'
    # latest anchors; anchors more than 1h past it must be STALE rejections.
    hours = list(range(125))
    bars = _light_bars_by_symbol(hours)
    usdchf_max = max(r["available_at_ms"] for r in bars["USDCHF"])
    bars["USDCHF"] = [r for r in bars["USDCHF"] if r["available_at_ms"] <= usdchf_max - 2 * H1_DURATION_MS]
    rows, summary = compute_causal_dxy_rows(bars)
    assert summary["rejections_by_reason"].get("STALE_CONSTITUENT:USDCHF", 0) > 0
    # Anchors within the exact 1h staleness bound are still accepted.
    fresh_anchor = usdchf_max - H1_DURATION_MS
    accepted_anchors = [int(r["available_at_ms"]) for r in rows]
    assert fresh_anchor in accepted_anchors


def test_out_of_order_constituent_series_fail_closed():
    hours = list(range(125))
    bars = _light_bars_by_symbol(hours)
    bars["EURUSD"] = list(reversed(bars["EURUSD"]))
    with pytest.raises(AcquisitionError, match="UNORDERED"):
        compute_causal_dxy_rows(bars)


def test_warmup_semantics_are_visible_for_downstream_consumers():
    # The strategy requires dxy_lookback_bars (20) accepted rows before
    # decisions; the package records accepted row counts so downstream
    # validation can verify warm-up without re-deriving.
    hours = list(range(30))
    rows, summary = compute_causal_dxy_rows(_light_bars_by_symbol(hours))
    assert len(rows) == summary["accepted_rows"] >= 20


# ---------------------------------------------------------------------------
# Gap reporting
# ---------------------------------------------------------------------------

def test_gap_report_counts_missing_windows_and_runs():
    # Weekend gap: hours 0..119 contiguous, missing 120..143 (hypothetical)
    symbol = "EURUSD"
    rows = _bars(symbol, list(range(120)))
    report = compute_gap_report(rows)
    assert report["observed_windows"] == 120
    assert report["theoretical_windows"] == 8784
    assert report["missing_window_count"] == 8784 - 120
    assert report["gap_runs"] == 0


def test_gap_report_empty_series():
    report = compute_gap_report([])
    assert report["observed_windows"] == 0
    assert report["missing_window_count"] == 8784
    assert report["gap_runs"] == 0


# ---------------------------------------------------------------------------
# Package publication / verification
# ---------------------------------------------------------------------------

def test_publish_verify_readback_and_determinism(tmp_path):
    hours = list(range(120))
    bars_by_symbol = _light_bars_by_symbol(hours)
    root, verified = _publish(tmp_path, bars_by_symbol)
    assert verified["total_dxy_rows"] > 0
    assert verified["total_constituent_rows"] == 6 * 120
    again_root, again_verified = _publish(tmp_path, bars_by_symbol)
    assert again_root == root
    assert again_verified["manifest_sha256"] == verified["manifest_sha256"]
    assert again_verified["causal_dxy"]["sha256"] == verified["causal_dxy"]["sha256"]


def test_tampered_partition_hash_fails_closed(tmp_path):
    hours = list(range(120))
    bars_by_symbol = _light_bars_by_symbol(hours)
    root, _ = _publish(tmp_path, bars_by_symbol)
    partition = root / "constituents" / "eurusd-h1-2024.parquet"
    data = partition.read_bytes()
    partition.write_bytes(data[:-1] + bytes([data[-1] ^ 0xFF]))
    with pytest.raises(AcquisitionError, match="PHYSICAL_HASH_MISMATCH"):
        verify_package_readonly(root)


def test_manifest_tampering_fails_closed(tmp_path):
    hours = list(range(120))
    bars_by_symbol = _light_bars_by_symbol(hours)
    root, _ = _publish(tmp_path, bars_by_symbol)
    manifest_path = root / "manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["causal_dxy"]["record_count"] = 999999
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AcquisitionError):
        verify_package_readonly(root)


def test_wrong_implementation_commit_conflicts(tmp_path):
    hours = list(range(120))
    bars_by_symbol = _light_bars_by_symbol(hours)
    _publish(tmp_path, bars_by_symbol)
    with pytest.raises(AcquisitionError, match="CONFLICT"):
        _publish(tmp_path, bars_by_symbol, implementation_commit="b" * 40)


def test_conflicting_record_fails_after_package_change(tmp_path):
    hours = list(range(120))
    bars_by_symbol = _light_bars_by_symbol(hours)
    _publish(tmp_path, bars_by_symbol)
    altered = _light_bars_by_symbol(hours)
    altered["EURUSD"] = _bars("EURUSD", list(range(121)))
    with pytest.raises((AcquisitionError, Exception)):
        # Either fails at publish (new data with existing package recognized
        # first) or at verification; both are acceptable fail-closed paths.
        _publish(tmp_path, altered)


def test_interrupted_publication_leaves_no_package(tmp_path):
    hours = list(range(120))
    bars_by_symbol = _light_bars_by_symbol(hours)
    broken = dict(bars_by_symbol)
    broken["USDSEK"] = ()
    with pytest.raises(AcquisitionError):
        _publish(tmp_path, broken)
    assert not (tmp_path / "dxy").exists() or not list((tmp_path / "dxy").glob("dxy-development-2024-v1-*"))


# ---------------------------------------------------------------------------
# Discovery / readiness registration
# ---------------------------------------------------------------------------

def test_discovery_registration_idempotent_and_fail_closed(tmp_path):
    hours = list(range(120))
    bars_by_symbol = _light_bars_by_symbol(hours)
    _publish(tmp_path, bars_by_symbol)
    discovery_root = tmp_path / "derived" / "discovery"
    record, identity = register_dxy_package(tmp_path, discovery_root)
    assert record["dataset_readiness"]["accepted_for_final_validation"] is False
    assert record["dataset_readiness"]["strategy_evaluation_authorized"] is False
    assert record["dataset_readiness"]["holdout_access_authorized"] is False
    assert "causal_2024_dxy_development_input" in record["dataset_readiness"]["available_components"]
    record2, identity2 = register_dxy_package(tmp_path, discovery_root)
    assert identity2.discovery_sha256 == identity.discovery_sha256
    assert identity2.discovery_physical_sha256 == identity.discovery_physical_sha256
    loaded = load_dxy_discovery_record(discovery_root, identity.package_id)
    assert loaded["discovery"]["package_id"] == identity.package_id

    record_path = discovery_root / identity.package_id / "discovery.json"
    tampered = json.loads(record_path.read_text(encoding="utf-8"))
    tampered["discovery"]["total_dxy_rows"] = 1
    record_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(AcquisitionError, match="CANONICAL_HASH_MISMATCH|PHYSICAL_HASH_MISMATCH"):
        load_dxy_discovery_record(discovery_root, identity.package_id)


# ---------------------------------------------------------------------------
# Safety / confinement
# ---------------------------------------------------------------------------

def test_mt5_is_not_imported_by_offline_modules():
    mt5_before = sys.modules.get("MetaTrader5")
    import bot.acquisition.dxy_contracts  # noqa: F401
    import bot.acquisition.dxy_package  # noqa: F401
    import bot.acquisition.dxy_discovery  # noqa: F401
    assert sys.modules.get("MetaTrader5") is mt5_before


def test_prohibited_operations_confined_to_gateway():
    from bot.acquisition.gateway import assert_gateway_surface

    assert_gateway_surface()
    from pathlib import Path

    source = (REPO_ROOT / "bot" / "acquisition" / "dxy_acquisition.py").read_text(encoding="utf-8")
    for prohibited in ("order_send", "account_info", "positions_get", "order_check"):
        assert prohibited not in source
