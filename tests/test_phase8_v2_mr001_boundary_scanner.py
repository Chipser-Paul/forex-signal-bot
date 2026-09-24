"""MR001 — V001 measurement-tooling boundary-scanner repair regressions.

Defect (frozen tooling ``d87b7149...``, discovered after empirical exposure):
``run_v001_evaluation`` stringified whole provenance mappings into
``reject_holdout_path``, a filesystem-path scanner, so hash-hex fragments of
real 64-hex SHA-256 digests (``4600``, ``8871`` ...) were misclassified as
future-year path components and every conforming store was deterministically
refused before any metric was emitted.

Repair principle (task §5): path scanners scan paths; structured provenance
validators validate structured provenance. Neither boundary is weakened.

Infrastructure verification only — no strategy, validation, fold, scenario,
cost or acceptance semantics are exercised. No empirical store is opened.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pytest

from backtests import phase8_v2_variant_v001_eval as v001


# ---------------------------------------------------------------------------
# Deterministic fixtures: real 64-hex digests with many 4-digit fragments >= 2025
# ---------------------------------------------------------------------------


def _digest_with_fragments(seed: str, minimum: int = 3) -> str:
    """Deterministic 64-hex digest containing >= `minimum` fragments >= 2025."""
    counter = 0
    while True:
        counter += 1
        digest = hashlib.sha256(f"mr001-fixture-{seed}-{counter}".encode()).hexdigest()
        fragments = [int(t) for t in re.findall(r"\d{4}", digest) if int(t) >= 2025]
        if len(fragments) >= minimum:
            return digest


def _digest_containing(literal: str) -> str:
    """Deterministic 64-hex digest containing an exact digit substring."""
    counter = 0
    while True:
        counter += 1
        digest = hashlib.sha256(f"mr001-literal-{literal}-{counter}".encode()).hexdigest()
        if literal in digest:
            return digest


# The exact replay-input index hash that deterministically failed in production
# (fragments 4600 / 8871 / 7882 / 5752 ...), as published in the blockage record.
REAL_FAILING_INDEX_SHA256 = (
    "e460066f4ebde8871eff44f874a6f7882a9a57524d5be358670c528e407846ba"
)


def _raw_source_identities() -> dict[str, Any]:
    """Conforming raw-source provenance shaped like the frozen store identity."""
    return {
        "input_index_sha256": REAL_FAILING_INDEX_SHA256,
        "source_identities": {
            "candle_partition_sha256s": {
                timeframe: _digest_with_fragments(f"candle-{timeframe}")
                for timeframe in ("M5", "M15", "H1", "H4", "D1", "W1")
            },
            "dxy_partition_sha256s": {
                symbol: _digest_with_fragments(f"dxy-{symbol}")
                for symbol in ("eurusd", "usdjpy", "gbpusd", "usdcad", "usdsek", "usdchf")
            },
            "evidence_package_sha256s": {
                "cost_policy": _digest_with_fragments("cost"),
                "metadata_bounds": _digest_with_fragments("bounds"),
                "official_news": _digest_with_fragments("news"),
            },
            "monthly_manifest_sha256s": {
                f"exness-xauusdm-2024-{month:02d}": _digest_with_fragments(f"m{month}")
                for month in range(1, 13)
            },
            "mode": "STRICT_ACCEPTED_PACKAGES",
            "year_package": {
                "package_id": "exness-xauusdm-2024-development-b2a0234a470dd397",
                "manifest_sha256": _digest_with_fragments("year"),
                "record_count": 39715935,
            },
        },
        "plan_fingerprint": _digest_with_fragments("plan"),
        "plan_package_id": "plan-package",
        "config_fingerprint": _digest_with_fragments("cfg"),
        "pipeline_fingerprint": _digest_with_fragments("pipe"),
    }


def _rebuilt_store_identity() -> dict[str, Any]:
    """Synthetic store identity reproducing the frozen store's schema shape."""
    return {
        "store_sha256": _digest_with_fragments("rows"),
        "store_name": "fold-01-" + _digest_with_fragments("store")[:16],
        "store_identity_sha256": _digest_with_fragments("sid"),
        "input_index_sha256": REAL_FAILING_INDEX_SHA256,
        "pipeline_fingerprint": _digest_with_fragments("pipe"),
    }


def _validate_provenance(
    raw: dict[str, Any], store: dict[str, Any]
) -> None:
    """The exact repaired boundary layer of run_v001_evaluation."""
    v001._assert_source_dates_within_development(raw)
    v001._reject_holdout_identity_paths(raw, "raw_source_identities")
    v001._reject_holdout_identity_paths(store, "rebuilt_store_identity")
    v001._assert_source_dates_within_development(store)


# ---------------------------------------------------------------------------
# §9 — the exact latent defect: digest fragments must not read as years
# ---------------------------------------------------------------------------


def test_structured_provenance_with_real_length_digests_passes():
    raw = _raw_source_identities()
    store = _rebuilt_store_identity()
    _validate_provenance(raw, store)


def test_real_production_failing_index_hash_passes_after_repair():
    raw = _raw_source_identities()
    assert raw["input_index_sha256"] == REAL_FAILING_INDEX_SHA256
    # Historical wiring: reject_holdout_path(str(raw)) refused exactly this
    # value (fragments 4600, 8871, ...). The path scanner itself is untouched
    # and would still refuse it as a literal argument — the repair is that the
    # structured layer no longer feeds digests into the path scanner.
    with pytest.raises(v001.BoundaryError):
        v001.reject_holdout_path(REAL_FAILING_INDEX_SHA256)


def test_digest_with_fragment_2029_passes():
    raw = {"plan_fingerprint": _digest_with_fragments("plan2029")}
    assert any(
        fragment >= 2025
        for fragment in (
            int(t)
            for t in re.findall(r"\d{4}", raw["plan_fingerprint"])
        )
    )
    _validate_provenance(raw, {"store_sha256": _digest_with_fragments("s")})


def test_digest_containing_literal_2025_substring_passes():
    raw = {"config_fingerprint": _digest_containing("2025")}
    assert "2025" in raw["config_fingerprint"]
    _validate_provenance(raw, {"store_sha256": _digest_with_fragments("s")})


def test_every_sha256_shaped_field_may_carry_2025_fragments():
    raw = _raw_source_identities()
    assert "2025" not in str(raw).lower().replace(_digest_containing("2025"), "")
    # Explicitly: incidental >=2025 fragments exist and must all be tolerated.
    fragments = [
        int(t)
        for part in re.findall(r"[0-9a-f]{64}", str(raw))
        for t in re.findall(r"\d{4}", part)
        if int(t) >= 2025
    ]
    assert fragments, "fixture must contain >=2025 digest fragments"
    _validate_provenance(raw, _rebuilt_store_identity())


# ---------------------------------------------------------------------------
# §10 — true positives: genuine holdout / 2025+ references still fail
# ---------------------------------------------------------------------------


def test_holdout_path_valued_field_fails():
    raw = _raw_source_identities()
    raw["tick_source_path"] = "C:/data/holdout/2024/ticks.parquet"
    with pytest.raises(v001.BoundaryError):
        _validate_provenance(raw, _rebuilt_store_identity())


def test_genuine_2025_path_valued_field_fails():
    raw = _raw_source_identities()
    raw["candle_root_path"] = "C:/evidence/year=2025/part.parquet"
    with pytest.raises(v001.BoundaryError):
        _validate_provenance(raw, _rebuilt_store_identity())


def test_genuine_2026_path_valued_field_fails():
    raw = _raw_source_identities()
    raw["export_dir"] = "C:/evidence/exports/2026-01/"
    with pytest.raises(v001.BoundaryError):
        _validate_provenance(raw, _rebuilt_store_identity())


def test_structured_year_2025_partition_marker_fails():
    raw = _raw_source_identities()
    raw["source_identities"]["candles"] = {"partition": "year=2025"}
    with pytest.raises(v001.BoundaryError):
        _validate_provenance(raw, _rebuilt_store_identity())


def test_structured_2025_iso_date_marker_fails():
    raw = _raw_source_identities()
    raw["source_identities"]["news"] = {"coverage_end": "2025-01-01T00:00:00Z"}
    with pytest.raises(v001.BoundaryError):
        _validate_provenance(raw, _rebuilt_store_identity())


def test_holdout_marker_in_nested_structured_value_fails():
    raw = _raw_source_identities()
    raw["source_identities"]["mystery"] = {"path": "holdout"}
    with pytest.raises(v001.BoundaryError):
        _validate_provenance(raw, _rebuilt_store_identity())


def test_store_identity_with_holdout_path_field_fails():
    store = _rebuilt_store_identity()
    store["evidence_path"] = "C:/evidence/holdout/fold-01"
    with pytest.raises(v001.BoundaryError):
        _validate_provenance(_raw_source_identities(), store)


def test_store_identity_with_2025_store_path_fails():
    store = _rebuilt_store_identity()
    store["store_path"] = "C:/data/market-feature-store/year=2025/fold-01"
    with pytest.raises(v001.BoundaryError):
        _validate_provenance(_raw_source_identities(), store)


def test_path_valued_field_must_be_a_string():
    raw = _raw_source_identities()
    raw["tick_source_path"] = {"path": "C:/ok/"}  # structured object, not a path
    with pytest.raises(v001.BoundaryError):
        _validate_provenance(raw, _rebuilt_store_identity())


# ---------------------------------------------------------------------------
# §11 — store-identity validation on synthetic fixtures only
# ---------------------------------------------------------------------------


def _store_boundary_identity(store_name: str = "fold-01-" + "a" * 16) -> dict[str, Any]:
    return {
        "fold_id": store_name.split("-")[0] + "-" + store_name.split("-")[1],
        "decision_timeframe": "M5",
        "coverage": "full",
        "evaluation_start_ms": v001.FOLD01_START_MS,
        "evaluation_end_ms": v001.FOLD01_END_MS,
    }


def test_legitimate_synthetic_store_identity_passes():
    identity = _store_boundary_identity()
    v001.check_store_boundary(identity)
    v001.assert_no_historical_store(identity)


def test_historical_prohibited_store_id_fails():
    identity = _store_boundary_identity()
    identity["fold_id"] = v001.HISTORICAL_STORE_ID
    with pytest.raises(v001.V001EvalError):
        v001.assert_no_historical_store(identity)


def test_wrong_fold_store_identity_fails():
    identity = _store_boundary_identity()
    identity["fold_id"] = "fold-02"
    with pytest.raises(v001.BoundaryError):
        v001.check_store_boundary(identity)


def test_partial_coverage_store_identity_fails():
    identity = _store_boundary_identity()
    identity["coverage"] = "partial:5-of-13269"
    with pytest.raises(v001.BoundaryError):
        v001.check_store_boundary(identity)


# ---------------------------------------------------------------------------
# Path-scanner invariance — the scanner itself is untouched (§5, §8)
# ---------------------------------------------------------------------------


def test_path_scanner_still_rejects_genuine_violations():
    with pytest.raises(v001.BoundaryError):
        v001.reject_holdout_path("C:/data/holdout/2025/results.parquet")
    with pytest.raises(v001.BoundaryError):
        v001.reject_holdout_path("evidence/final_validation/x.json")
    with pytest.raises(v001.BoundaryError):
        v001.reject_holdout_path("evidence/candles/year=2025/part.parquet")
    with pytest.raises(v001.BoundaryError):
        v001.reject_holdout_path("evidence/2026-01/ledger.jsonl")
    v001.reject_holdout_path("evidence/v2_variants/phase6-development-v2-V001/fold01/")


def test_structured_validator_rejects_year_marker_even_alongside_digests():
    raw = _raw_source_identities()
    raw["source_identities"]["year_package"]["partition_marker"] = "year=2025"
    with pytest.raises(v001.BoundaryError):
        v001._assert_source_dates_within_development(raw)


# ---------------------------------------------------------------------------
# Full boundary-layer regression through run_v001_evaluation
# (store + observer + aggregation stubbed; boundary wiring real)
# ---------------------------------------------------------------------------


class _StubStore:
    def __init__(self, identity: dict[str, Any]) -> None:
        self.identity = identity


class _StubSnapshot:
    gate_event_id = "stub-1"
    available_at_ms = 1711929600000
    # MR003: the loop now classifies snapshots (D001 contract) before
    # orchestration, so canonical stubs carry a reducer-path gate status.
    gate_status = "ok"
    gate_payload = "{}"
    check_passes = True


def test_run_v001_evaluation_accepts_conforming_digest_identities(monkeypatch):
    raw = _raw_source_identities()
    store_identity = dict(_store_boundary_identity())
    store_identity.update(_rebuilt_store_identity())
    store = _StubStore(store_identity)

    monkeypatch.setattr(v001, "_snapshot_rows", lambda _store: [_StubSnapshot()])
    monkeypatch.setattr(
        v001,
        "observe_decision",
        lambda _snapshot, _state: ({"decision_id": "stub-1"}, None),
    )

    canned_aggregate = {
        "decisions_total": 1,
        "candidate_ready": 0,
        "detector_eligible_decisions": 1,
        "attrition_stage_totals": {"atr_valid_windows": 1},
        "final_fvg": {"decisions_with_final_fvg": 1},
    }
    monkeypatch.setattr(v001, "aggregate_v001", lambda _rows: dict(canned_aggregate))

    material, rendered = v001.run_v001_evaluation(
        store,
        canonical_commit="d621aebcaae89b99d3727fb2fff02a3ada53b0ae",
        tooling_commit="d87b71491203249e6ab3dd95bca4b9ee89cf3e9e",
        raw_source_identities=raw,
        rebuilt_store_identity=_rebuilt_store_identity(),
    )
    assert material["outcome_classification"] == "FUNCTIONAL_REPAIR_NO_CANDIDATES"
    assert material["h005_disposition"] == "SUPPORTED_BY_V001"
    assert material["raw_source_identities"]["input_index_sha256"] == (
        REAL_FAILING_INDEX_SHA256
    )
    assert material["rebuilt_store_identity"]["store_sha256"] == (
        _rebuilt_store_identity()["store_sha256"]
    )
    # Deterministic output material contains the complete digests (§24 payload
    # must remain complete — no hash stripping).
    assert REAL_FAILING_INDEX_SHA256 in rendered.decode("utf-8")


def test_run_v001_evaluation_still_refuses_historical_store(monkeypatch):
    store_identity = dict(_store_boundary_identity())
    store_identity["fold_id"] = v001.HISTORICAL_STORE_ID
    store = _StubStore(store_identity)
    monkeypatch.setattr(v001, "_snapshot_rows", lambda _store: [])
    with pytest.raises(v001.V001EvalError):
        v001.run_v001_evaluation(
            store,
            canonical_commit="d621aebcaae89b99d3727fb2fff02a3ada53b0ae",
            tooling_commit="d87b71491203249e6ab3dd95bca4b9ee89cf3e9e",
            raw_source_identities=_raw_source_identities(),
            rebuilt_store_identity=_rebuilt_store_identity(),
        )


def test_run_v001_evaluation_still_refuses_2025_provenance(monkeypatch):
    raw = _raw_source_identities()
    raw["source_identities"]["candles"] = {"partition": "year=2025"}
    store = _StubStore(dict(_store_boundary_identity()))
    monkeypatch.setattr(v001, "_snapshot_rows", lambda _store: [])
    with pytest.raises(v001.BoundaryError):
        v001.run_v001_evaluation(
            store,
            canonical_commit="d621aebcaae89b99d3727fb2fff02a3ada53b0ae",
            tooling_commit="d87b71491203249e6ab3dd95bca4b9ee89cf3e9e",
            raw_source_identities=raw,
            rebuilt_store_identity=_rebuilt_store_identity(),
        )
