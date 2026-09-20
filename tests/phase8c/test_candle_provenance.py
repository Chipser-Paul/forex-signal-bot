"""Phase 8C provenance attestation and discovery tests.

All packages are synthetic fixtures built through the real committed
pipeline.  No real dataset, no MT5, no network, no strategy evaluation.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from bot.acquisition.candle_attestation import (
    EXPECTED_RECORD_COUNTS,
    build_attestation,
    load_attestation,
    publish_attestation,
)
from bot.acquisition.candle_discovery import (
    _canonical_hash,
    code_fingerprint,
    load_discovery_record,
    register_attested_package,
)
from bot.acquisition.candle_manifest import build_derived_candle_manifest
from bot.acquisition.candle_pipeline import SCHEMA_VERSION, stable_candle_identity
from bot.acquisition.candle_store import ParquetBidAskCandleStore
from bot.acquisition.models import AcquisitionError
from bot.acquisition.storage import atomic_json, file_sha256
from backtests.candle_derivation_readiness import build_readiness_report

GENERATION_BASE_COMMIT = "4f46eef139bd20df84d4db5911767baa273eeba2"
IMPLEMENTATION_COMMIT = "2817d5b82a452157a3662b57e1956fd878a733cf"
OTHER_COMMIT = "b" * 40
TIMEFRAMES = ("M5", "M15", "H1", "H4", "D1", "W1")
DURATIONS_MS = {
    "M5": 300_000, "M15": 900_000, "H1": 3_600_000,
    "H4": 14_400_000, "D1": 86_400_000, "W1": 604_800_000,
}
ONE_ROW_COUNTS = {tf: 1 for tf in TIMEFRAMES}


def _record_for(timeframe: str) -> dict:
    duration = DURATIONS_MS[timeframe]
    open_ms, close_ms = 1_000_000, 1_000_000 + duration
    return {
        "symbol": "XAUUSDm",
        "timeframe": timeframe,
        "open_time_ms": open_ms,
        "close_time_ms": close_ms,
        "available_at_ms": close_ms,
        "bid_open": "2000.00", "bid_high": "2001.00",
        "bid_low": "1999.00", "bid_close": "2000.50",
        "ask_open": "2000.10", "ask_high": "2001.10",
        "ask_low": "1999.10", "ask_close": "2000.60",
        "tick_count": 10,
        "spread_min": "0.10", "spread_max": "0.10",
        "spread_median": "0.10", "spread_close": "0.10",
        "first_tick_ms": open_ms + 50,
        "last_tick_ms": close_ms - 50,
        "source_package_ids": ["pkg1"],
        "schema_version": SCHEMA_VERSION,
        "candle_identity": stable_candle_identity(
            "XAUUSDm", timeframe, open_ms, close_ms
        ),
    }


def _build_package(tmp_path: Path, *, git_commit: str = GENERATION_BASE_COMMIT,
                   with_fingerprint: str | None = None) -> Path:
    derived = tmp_path / "package"
    store = ParquetBidAskCandleStore(
        derived / "candles", maximum_output_bytes=10 * 1024**2, minimum_free_bytes=0
    )
    summaries = []
    for timeframe in TIMEFRAMES:
        summary = store.write(
            f"XAUUSDm/{timeframe}/year=2024/part-00000.parquet",
            [_record_for(timeframe)],
            partition_id=f"p-{timeframe}",
            timeframe=timeframe,
        )
        summaries.append((summary, {
            "gap_count": 0, "missing_window_count": 0,
            "partial_initial_window": False, "partial_terminal_window": True,
        }))
    manifest = build_derived_candle_manifest(
        derived,
        year_package_id="year-pkg",
        source_canonical_sha256="a" * 64,
        source_row_count=10,
        git_commit=git_commit,
        timeframe_summaries=summaries,
        monthly_package_ids=["pkg1"],
    )
    if with_fingerprint is not None:
        # Simulate a manifest that stores a generation-time fingerprint.
        path = derived / "manifest.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["generation_source_fingerprint"] = with_fingerprint
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        completion = derived / "pipeline.complete.json"
        marker = json.loads(completion.read_text(encoding="utf-8"))
        marker["manifest_sha256"] = file_sha256(path)
        completion.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")
        manifest = json.loads(path.read_text(encoding="utf-8"))
    completion = json.loads((derived / "pipeline.complete.json").read_text())
    report = build_readiness_report(
        year_package_id="year-pkg",
        source_row_count=10,
        source_canonical_sha256="a" * 64,
        source_first_tick="2024-01-01T23:05:09.882000Z",
        source_last_tick="2024-12-31T21:57:57.766000Z",
        derived_timeframes=list(TIMEFRAMES),
        derived_row_counts={tf: 1 for tf in TIMEFRAMES},
        derived_gap_counts={tf: 0 for tf in TIMEFRAMES},
        derived_missing_window_counts={tf: 0 for tf in TIMEFRAMES},
        derived_output_dir="external://package",
        derived_manifest_sha256=completion["manifest_sha256"],
        monthly_package_ids=["pkg1"],
        git_commit=git_commit,
    )
    atomic_json(derived / "readiness_report.json", report)
    return derived


@pytest.fixture
def package(tmp_path: Path) -> Path:
    return _build_package(tmp_path)


def _publish(derived: Path, tmp_path: Path, *, implementation=IMPLEMENTATION_COMMIT,
             verification=IMPLEMENTATION_COMMIT, counts=ONE_ROW_COUNTS, **kwargs):
    return publish_attestation(
        derived,
        tmp_path / "attestations",
        implementation_commit=implementation,
        verification_commit=verification,
        verification_fingerprint="phase8c-verifier-v1:" + "0" * 64,
        expected_record_counts=counts,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Creation, immutability, honesty
# ---------------------------------------------------------------------------

def test_attestation_creation_and_content(package, tmp_path):
    document, identity = _publish(package, tmp_path)
    assert document["schema_version"] == "phase8c.provenance-attestation.v1"
    assert document["classification"] == "DEVELOPMENT_ONLY"
    assert "NOT PROFITABILITY EVIDENCE" in document["label"]
    provenance = document["provenance"]
    assert provenance["generation_base_commit"] == GENERATION_BASE_COMMIT
    assert provenance["implementation_commit"] == IMPLEMENTATION_COMMIT
    assert provenance["verification_commit"] == IMPLEMENTATION_COMMIT
    assert provenance["verified_compatible"] is True
    assert provenance["generation_commit_equivalence"] == "NOT_PROVEN"
    assert provenance["generation_source_fingerprint"] is None
    assert "no generation-time" in provenance["generation_equivalence_explanation"]
    assert document["package"]["manifest_schema_version"] == \
        "phase8c.derived-candles-manifest.v1"
    assert len(document["verified_partitions"]) == 6
    assert document["holdout_accessed"] is False
    assert document["mt5_or_trading_accessed"] is False
    assert "No strategy evaluation" in document["strategy_evaluation_statement"]
    # Sidecar + round trip
    directory = tmp_path / "attestations" / identity.attestation_id
    assert (directory / "attestation.json").is_file()
    assert (directory / "attestation.sha256").is_file()
    loaded = load_attestation(tmp_path / "attestations", identity.attestation_id)
    assert loaded["attestation_canonical_sha256"] == identity.attestation_sha256


def test_existing_package_immutability(package, tmp_path):
    relevant = [package / "manifest.json", package / "pipeline.complete.json",
                package / "readiness_report.json"]
    relevant += sorted((package / "candles").rglob("*"))
    before = {p: file_sha256(p) for p in relevant if p.is_file()}
    _publish(package, tmp_path)
    register_attested_package(
        tmp_path / "attestations", tmp_path / "discovery"
    )
    after = {p: file_sha256(p) for p in relevant if p.is_file()}
    assert before == after


def test_honest_not_proven_without_fingerprint(package, tmp_path):
    document, _ = _publish(package, tmp_path)
    provenance = document["provenance"]
    assert provenance["generation_commit_equivalence"] == "NOT_PROVEN"
    assert provenance["generation_source_fingerprint"] is None
    # The manifest's honest generation-time commit is preserved verbatim.
    assert provenance["generation_base_commit"] == GENERATION_BASE_COMMIT


def test_proven_fingerprint_matching(tmp_path):
    module_hashes = {f"bot/acquisition/m{i}.py": hashlib.sha256(f"m{i}".encode()).hexdigest()
                     for i in range(5)}
    fingerprint = code_fingerprint(IMPLEMENTATION_COMMIT, module_hashes=module_hashes)
    derived = _build_package(tmp_path / "a", with_fingerprint=fingerprint)
    document, _ = _publish(
        derived, tmp_path, implementation_module_hashes=module_hashes
    )
    assert document["provenance"]["generation_commit_equivalence"] == "PROVEN"


def test_disproven_fingerprint(tmp_path):
    module_hashes = {f"bot/acquisition/m{i}.py": hashlib.sha256(f"m{i}".encode()).hexdigest()
                     for i in range(5)}
    fingerprint = code_fingerprint(OTHER_COMMIT, module_hashes=module_hashes)
    derived = _build_package(tmp_path / "a", with_fingerprint=fingerprint)
    document, _ = _publish(
        derived, tmp_path, implementation_module_hashes=module_hashes
    )
    assert document["provenance"]["generation_commit_equivalence"] == "DISPROVEN"


# ---------------------------------------------------------------------------
# Tamper detection (fixture copies only)
# ---------------------------------------------------------------------------

def _expect_acquisition_error(callable_, match: str) -> None:
    with pytest.raises(AcquisitionError, match=match):
        callable_()


def test_manifest_hash_mismatch(tmp_path):
    derived = _build_package(tmp_path)
    path = derived / "manifest.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["source_row_count"] = 11
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    _expect_acquisition_error(lambda: _publish(derived, tmp_path),
                              "SHA-256 mismatch")


def test_completion_marker_mismatch(tmp_path):
    derived = _build_package(tmp_path)
    path = derived / "pipeline.complete.json"
    marker = json.loads(path.read_text(encoding="utf-8"))
    marker["manifest_sha256"] = "0" * 64
    path.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    _expect_acquisition_error(lambda: _publish(derived, tmp_path),
                              "SHA-256 mismatch")


def test_partition_physical_hash_mismatch(tmp_path):
    derived = _build_package(tmp_path)
    partition = next((derived / "candles").rglob("part-00000.parquet"))
    with partition.open("ab") as handle:
        handle.write(b"corruption")
    _expect_acquisition_error(lambda: _publish(derived, tmp_path),
                              "PHYSICAL_HASH_MISMATCH")


def test_canonical_hash_mismatch(tmp_path):
    derived = _build_package(tmp_path)
    marker_path = next(
        (derived / "candles").rglob("part-00000.parquet.complete.json")
    )
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["canonical_content_sha256"] = "f" * 64
    marker_path.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    _expect_acquisition_error(lambda: _publish(derived, tmp_path),
                              "canonical content hash mismatch")


def test_incorrect_row_count(tmp_path):
    derived = _build_package(tmp_path)
    manifest_path = derived / "manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["timeframe_entries"][0]["record_count"] = 2
    manifest_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    completion = derived / "pipeline.complete.json"
    marker = json.loads(completion.read_text(encoding="utf-8"))
    marker["manifest_sha256"] = file_sha256(manifest_path)
    completion.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    _expect_acquisition_error(lambda: _publish(derived, tmp_path),
                              "ROW_COUNT_MISMATCH")


def test_incorrect_implementation_commit_conflict(package, tmp_path):
    _publish(package, tmp_path)
    with pytest.raises(AcquisitionError, match="ATTESTATION_CONFLICT"):
        _publish(package, tmp_path, implementation=OTHER_COMMIT)


# ---------------------------------------------------------------------------
# Publication semantics
# ---------------------------------------------------------------------------

def test_atomic_publication_interruption_recovery(package, tmp_path):
    from bot.acquisition.candle_attestation import attestation_id_for

    attestation_id = attestation_id_for(
        file_sha256(package / "manifest.json")
    )
    directory = tmp_path / "attestations" / attestation_id
    directory.mkdir(parents=True)
    (directory / ".attestation.json.stale.partial").write_bytes(b"junk")
    document, identity = _publish(package, tmp_path)
    assert identity.attestation_id == attestation_id
    assert (directory / "attestation.json").is_file()
    assert (directory / "attestation.sha256").is_file()
    loaded = load_attestation(tmp_path / "attestations", attestation_id)
    assert loaded["attestation_canonical_sha256"] == \
        document["attestation_canonical_sha256"]


def test_idempotent_repeated_attestation(package, tmp_path):
    _, first = _publish(package, tmp_path)
    _, second = _publish(package, tmp_path)
    assert first.attestation_sha256 == second.attestation_sha256
    assert first.attestation_physical_sha256 == second.attestation_physical_sha256


def test_conflicting_repeated_attestation(package, tmp_path):
    _publish(package, tmp_path)
    with pytest.raises(AcquisitionError, match="ATTESTATION_CONFLICT"):
        _publish(package, tmp_path, verification=OTHER_COMMIT)


def test_attestation_tampering(package, tmp_path):
    _, identity = _publish(package, tmp_path)
    directory = tmp_path / "attestations" / identity.attestation_id
    document_path = directory / "attestation.json"
    sidecar = directory / "attestation.sha256"

    # Case 1: bytes changed, recorded hashes untouched -> physical mismatch.
    stored = json.loads(document_path.read_text(encoding="utf-8"))
    stored["package"]["source_row_count"] = 999
    document_path.write_text(json.dumps(stored, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    with pytest.raises(AcquisitionError, match="PHYSICAL_HASH_MISMATCH"):
        load_attestation(tmp_path / "attestations", identity.attestation_id)

    # Case 2: attacker rewrites the sidecar for the mutated bytes but leaves
    # the self-recorded canonical hash stale -> canonical mismatch.
    sidecar.write_text(file_sha256(document_path) + "\n", encoding="ascii")
    with pytest.raises(AcquisitionError, match="CANONICAL_HASH_MISMATCH"):
        load_attestation(tmp_path / "attestations", identity.attestation_id)


# ---------------------------------------------------------------------------
# Discovery / registration
# ---------------------------------------------------------------------------

def test_discovery_registration_and_readiness(package, tmp_path):
    _, identity = _publish(package, tmp_path)
    record, discovery = register_attested_package(
        tmp_path / "attestations", tmp_path / "discovery"
    )
    assert discovery.attestation_id == identity.attestation_id
    assert record["discovery"]["verification_status"] == "VERIFIED_AT_COMMIT"
    assert record["discovery"]["package_id"].startswith("derived-candles-2024-v1-")
    assert record["discovery"]["manifest_sha256"] == identity.manifest_sha256
    assert record["discovery"]["attestation_canonical_sha256"] == \
        identity.attestation_sha256
    assert record["discovery"]["row_counts_by_timeframe"] == ONE_ROW_COUNTS
    readiness = record["dataset_readiness"]
    assert readiness["accepted_for_final_validation"] is False
    assert readiness["available_components"] == [
        "verified_2024_xauusdm_ticks",
        "derived_causal_bid_ask_candles",
        "observed_spread_evidence",
    ]
    assert "untouched_holdout_data" in readiness["missing_components"]
    assert "DXY_history_or_all_six_causally_aligned_constituents" in \
        readiness["missing_components"]
    loaded = load_discovery_record(
        tmp_path / "discovery", identity.attestation_id
    )
    assert loaded["discovery_canonical_sha256"] == discovery.discovery_sha256


def test_duplicate_registration_idempotent(package, tmp_path):
    _publish(package, tmp_path)
    _, first = register_attested_package(
        tmp_path / "attestations", tmp_path / "discovery"
    )
    _, second = register_attested_package(
        tmp_path / "attestations", tmp_path / "discovery"
    )
    assert first.discovery_sha256 == second.discovery_sha256
    assert first.discovery_physical_sha256 == second.discovery_physical_sha256


def test_discovery_registration_conflict(package, tmp_path):
    _publish(package, tmp_path)
    _, identity = register_attested_package(
        tmp_path / "attestations", tmp_path / "discovery"
    )
    directory = tmp_path / "discovery" / identity.attestation_id
    record_path = directory / "discovery.json"
    sidecar = directory / "discovery.json.sha256"
    stored = json.loads(record_path.read_text(encoding="utf-8"))
    stored["discovery"]["source_row_count"] = 999
    body = {k: v for k, v in stored.items()
            if k not in ("discovery_canonical_sha256",)}
    stored["discovery_canonical_sha256"] = _canonical_hash(body)
    record_path.write_text(json.dumps(stored, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    sidecar.write_text(file_sha256(record_path) + "\n", encoding="ascii")
    with pytest.raises(AcquisitionError, match="DISCOVERY_REGISTRATION_CONFLICT"):
        register_attested_package(tmp_path / "attestations", tmp_path / "discovery")


def test_missing_attestation_fails(tmp_path):
    with pytest.raises(AcquisitionError, match="ATTESTATION_MISSING"):
        register_attested_package(tmp_path / "none", tmp_path / "discovery")
    with pytest.raises(AcquisitionError, match="ATTESTATION_MISSING"):
        load_attestation(tmp_path / "none", "derived-candles-attestation-v1-abc")


def test_ambiguous_attestation_selection(tmp_path):
    first = _build_package(tmp_path / "one")
    second = _build_package(tmp_path / "two")
    _publish(first, tmp_path)
    # Second package has a different manifest hash -> second attestation dir.
    manifest_path = second / "manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["source_row_count"] = 12
    manifest_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (second / "readiness_report.json").unlink()
    completion = second / "pipeline.complete.json"
    marker = json.loads(completion.read_text(encoding="utf-8"))
    marker["manifest_sha256"] = file_sha256(manifest_path)
    completion.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    from backtests.candle_derivation_readiness import build_readiness_report as brr
    report = brr(
        year_package_id="year-pkg", source_row_count=12,
        source_canonical_sha256="a" * 64,
        source_first_tick="2024-01-01T23:05:09.882000Z",
        source_last_tick="2024-12-31T21:57:57.766000Z",
        derived_timeframes=list(TIMEFRAMES),
        derived_row_counts={tf: 1 for tf in TIMEFRAMES},
        derived_gap_counts={tf: 0 for tf in TIMEFRAMES},
        derived_missing_window_counts={tf: 0 for tf in TIMEFRAMES},
        derived_output_dir="external://package",
        derived_manifest_sha256=marker["manifest_sha256"],
        monthly_package_ids=["pkg1"], git_commit=GENERATION_BASE_COMMIT,
    )
    atomic_json(second / "readiness_report.json", report)
    _publish(second, tmp_path)
    with pytest.raises(AcquisitionError, match="AMBIGUOUS"):
        register_attested_package(tmp_path / "attestations", tmp_path / "discovery")


# ---------------------------------------------------------------------------
# Safety imports
# ---------------------------------------------------------------------------

def test_mt5_free_imports():
    before = set(sys.modules)
    import backtests.candle_provenance_control  # noqa: F401
    import bot.acquisition.candle_attestation  # noqa: F401
    import bot.acquisition.candle_discovery  # noqa: F401
    added = set(sys.modules) - before
    assert "MetaTrader5" not in added
    assert not any("MetaTrader5" in name for name in added)
