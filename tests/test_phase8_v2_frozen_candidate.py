"""Tests for Phase 8 V2 prospective strategy freeze (phase6-frozen-v2).

Covers Research Charter §17 and Task requirements:
- Approved prospective contract (canonical_git_blob_v1) accepted
- Legacy contract (legacy_worktree_bytes_v0) rejected
- Missing and unknown contracts rejected (fail-closed)
- Semantic path ordering and deduplication enforced
- Freeze manifest parsing and schema validation
- Configuration lock determinism and StrategyConfig fingerprint parity
- Blob identities and dependency locks match frozen declarations
- Prospective contract record format (zero local path leakage)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

from bot.strategy.config import StrategyConfig
from bot.scientific.prospective_freeze import (
    CONTRACT_ID,
    LEGACY_CONTRACT_ID,
    ProspectiveFreezeError,
    ProspectiveFreezeIdentity,
    contract_record,
    validate_prospective_contract,
    freeze_prospective_identity,
)
from bot.scientific.canonical_bytes import canonical_framed_digest


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "baseline" / "phase8_v2_frozen_candidate_manifest.json"

ANCHOR_COMMIT = "2fd3460b9010d8cca548f4fd6980b6b34fe594e2"

EXPECTED_PATHS = (
    "bot/state/gate_inputs.py",
    "bot/state/gate_reducer.py",
    "bot/strategy/config.py",
    "bot/strategy/variant_v003.py",
    "bot/strategy/variant_v005.py",
    "strategies/smc_engine/entry_model.py",
    "strategies/smc_engine/strategy_state.py",
)

EXPECTED_BLOBS = {
    "bot/state/gate_inputs.py": "a4bdc19a949f75ea7fa7cc52c516b6626590fe6c",
    "bot/state/gate_reducer.py": "e1841fc276401146e38a69b9555a0e4437a30290",
    "bot/strategy/config.py": "fc992fb091bc5c04363552467e99807c83387386",
    "bot/strategy/variant_v003.py": "c25f110c15c60bc5b32cffc0b3870de6d5d5144c",
    "bot/strategy/variant_v005.py": "3820c6c66f96c91d98b47feda0e4f5f88aa5c70a",
    "strategies/smc_engine/entry_model.py": "0dff4ccb47513ccd56cd955d9f618e69d9ec3c02",
    "strategies/smc_engine/strategy_state.py": "b7500160ebfb084703c6fe02c16946c1185d21b2",
}

EXPECTED_AGGREGATE_DIGEST = (
    "22880f7acfb762b938997ef070fef13580679f37058f1853b8c8438fc9defc25"
)
EXPECTED_CONFIG_FINGERPRINT = "6fce546fb4a3ad41c2fe6fb9"
EXPECTED_CONFIG_SHA256 = (
    "6fce546fb4a3ad41c2fe6fb98231ceb7840d15e60f234746d7c78c87d3791e19"
)


# ---------------------------------------------------------------------------
# Contract Boundary Tests
# ---------------------------------------------------------------------------


def test_approved_prospective_contract_accepted() -> None:
    assert validate_prospective_contract("canonical_git_blob_v1") == "canonical_git_blob_v1"
    assert validate_prospective_contract(CONTRACT_ID) == CONTRACT_ID


def test_legacy_contract_rejected() -> None:
    with pytest.raises(ProspectiveFreezeError, match="PROSPECTIVE_CONTRACT_REJECTED"):
        validate_prospective_contract("legacy_worktree_bytes_v0")
    with pytest.raises(ProspectiveFreezeError, match="PROSPECTIVE_CONTRACT_REJECTED"):
        validate_prospective_contract(LEGACY_CONTRACT_ID)


def test_missing_and_empty_contract_rejected() -> None:
    with pytest.raises(ProspectiveFreezeError, match="PROSPECTIVE_CONTRACT_UNDECLARED"):
        validate_prospective_contract(None)
    with pytest.raises(ProspectiveFreezeError, match="PROSPECTIVE_CONTRACT_ID_INVALID"):
        validate_prospective_contract("")


def test_unknown_contract_rejected() -> None:
    with pytest.raises(ProspectiveFreezeError, match="PROSPECTIVE_CONTRACT_UNKNOWN"):
        validate_prospective_contract("canonical_git_blob_v999")


def test_semantic_path_order_and_uniqueness_enforced(tmp_path: Path) -> None:
    # Unordered paths must raise ProspectiveFreezeError
    with pytest.raises(ProspectiveFreezeError, match="PROSPECTIVE_PATHS_MUST_BE_ORDERED_AND_UNIQUE"):
        ProspectiveFreezeIdentity(
            contract_id=CONTRACT_ID,
            digest_algorithm="sha256",
            commit=ANCHOR_COMMIT,
            paths=("bot/strategy/variant_v005.py", "bot/strategy/config.py"),
            digest="a" * 64,
        )

    # Duplicate paths must raise ProspectiveFreezeError
    with pytest.raises(ProspectiveFreezeError, match="PROSPECTIVE_PATHS_MUST_BE_ORDERED_AND_UNIQUE"):
        ProspectiveFreezeIdentity(
            contract_id=CONTRACT_ID,
            digest_algorithm="sha256",
            commit=ANCHOR_COMMIT,
            paths=("bot/strategy/config.py", "bot/strategy/config.py"),
            digest="a" * 64,
        )


# ---------------------------------------------------------------------------
# Manifest & Invariants Tests
# ---------------------------------------------------------------------------


def test_freeze_manifest_parses_and_validates_schema() -> None:
    assert MANIFEST_PATH.exists(), f"Manifest missing at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["schema_version"] == "phase8v2.frozen-candidate-manifest.v1"
    assert manifest["freeze_identity"] == "phase6-frozen-v2"
    assert manifest["development_predecessor"] == "phase6-development-v2-V005"
    assert manifest["semantic_anchor_commit"] == ANCHOR_COMMIT
    assert manifest["strategy_semantic_aggregate_digest"] == EXPECTED_AGGREGATE_DIGEST
    assert manifest["configuration_fingerprint"] == EXPECTED_CONFIG_FINGERPRINT
    assert manifest["full_configuration_sha256"] == EXPECTED_CONFIG_SHA256


def test_freeze_manifest_ordered_paths_and_blobs() -> None:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    ordered_paths = manifest["ordered_semantic_paths"]
    assert tuple(ordered_paths) == EXPECTED_PATHS
    assert ordered_paths == sorted(ordered_paths)
    assert len(set(ordered_paths)) == len(ordered_paths)

    path_blobs = manifest["path_git_blob_ids"]
    assert path_blobs == EXPECTED_BLOBS


def test_freeze_manifest_contract_record_shape() -> None:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    record = manifest["prospective_contract_record"]
    assert record["contract_id"] == "canonical_git_blob_v1"
    assert record["digest_algorithm"] == "sha256"
    assert record["commit"] == ANCHOR_COMMIT
    assert record["paths"] == list(EXPECTED_PATHS)
    assert record["digest"] == EXPECTED_AGGREGATE_DIGEST
    assert record["legacy_compatible"] is False

    # Zero absolute path or Windows backslash leakage in path lists
    for p in record["paths"]:
        assert "\\" not in p
        assert not Path(p).is_absolute()
        assert not p.startswith("/")

    dumped = json.dumps(manifest)
    assert "C:" not in dumped
    assert "/Users/" not in dumped
    assert "\\Users\\" not in dumped


def test_configuration_lock_and_fingerprint_determinism() -> None:
    cfg = StrategyConfig()
    fp = cfg.fingerprint()
    assert fp == EXPECTED_CONFIG_FINGERPRINT

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    lock = manifest["configuration_lock"]
    assert lock["version"] == cfg.version
    assert set(lock["executable_symbols"]) == cfg.executable_symbols
    assert lock["dxy_lookback_bars"] == cfg.dxy_lookback_bars
    assert lock["dxy_slope_threshold_fraction_per_bar"] == cfg.dxy_slope_threshold_fraction_per_bar
    assert lock["dxy_max_staleness_seconds"] == cfg.dxy_max_staleness.total_seconds()
    assert lock["atr_period_bars"] == cfg.atr_period_bars
    assert lock["regime_baseline_bars"] == cfg.regime_baseline_bars
    assert lock["regime_trend_lookback_bars"] == cfg.regime_trend_lookback_bars
    assert lock["high_volatility_ratio"] == cfg.high_volatility_ratio
    assert lock["trend_strength_atr"] == cfg.trend_strength_atr
    assert lock["order_block_displacement_atr"] == cfg.order_block_displacement_atr
    assert lock["order_block_expiry_bars"] == cfg.order_block_expiry_bars
    assert lock["news_block_before_seconds"] == cfg.news_block_before.total_seconds()
    assert lock["news_block_after_seconds"] == cfg.news_block_after.total_seconds()
    assert lock["news_max_age_seconds"] == cfg.news_max_age.total_seconds()
    assert lock["rollover_start_utc"] == cfg.rollover_start_utc.isoformat()
    assert lock["rollover_end_utc"] == cfg.rollover_end_utc.isoformat()
    assert lock["confluence_threshold"] == cfg.confluence_threshold

    # Deterministic compact serialization matches full SHA-256
    payload = {
        "version": cfg.version,
        "executable_symbols": sorted(list(cfg.executable_symbols)),
        "dxy_symbol_map": dict(sorted(cfg.dxy_symbol_map.items())),
        "dxy_lookback_bars": cfg.dxy_lookback_bars,
        "dxy_slope_threshold_fraction_per_bar": cfg.dxy_slope_threshold_fraction_per_bar,
        "dxy_max_staleness_seconds": cfg.dxy_max_staleness.total_seconds(),
        "atr_period_bars": cfg.atr_period_bars,
        "regime_baseline_bars": cfg.regime_baseline_bars,
        "regime_trend_lookback_bars": cfg.regime_trend_lookback_bars,
        "high_volatility_ratio": cfg.high_volatility_ratio,
        "trend_strength_atr": cfg.trend_strength_atr,
        "order_block_displacement_atr": cfg.order_block_displacement_atr,
        "order_block_expiry_bars": cfg.order_block_expiry_bars,
        "news_block_before_seconds": cfg.news_block_before.total_seconds(),
        "news_block_after_seconds": cfg.news_block_after.total_seconds(),
        "news_max_age_seconds": cfg.news_max_age.total_seconds(),
        "rollover_start_utc": cfg.rollover_start_utc.isoformat(),
        "rollover_end_utc": cfg.rollover_end_utc.isoformat(),
        "confluence_threshold": cfg.confluence_threshold,
    }
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    sha = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    assert sha == EXPECTED_CONFIG_SHA256
    assert sha[:24] == fp


def test_dependency_locks_match_manifest() -> None:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    v003_lock = manifest["v003_dependency_lock"]
    assert v003_lock["git_blob_id"] == "c25f110c15c60bc5b32cffc0b3870de6d5d5144c"
    assert v003_lock["specification_sha256"] == "e6aa3e8a4f7b909f178a18112a43425ccfe61448c3c8643aea9c3f5d670e0d95"

    entry_state_lock = manifest["entry_and_state_dependency_lock"]
    assert entry_state_lock["entry_model_git_blob_id"] == "0dff4ccb47513ccd56cd955d9f618e69d9ec3c02"
    assert entry_state_lock["strategy_state_git_blob_id"] == "b7500160ebfb084703c6fe02c16946c1185d21b2"

    eval_prov = manifest["development_evaluator_provenance"]
    assert eval_prov["git_blob_id"] == "6291999b059facadf6ea40482f8413872cf4cd23"
    assert eval_prov["canonical_file_digest"] == "dd4d864e6caf3413447121bac9bc412c1db7a8df6243422840e0e5d59ca26683"
    assert eval_prov["classification"] == "DEVELOPMENT_MEASUREMENT_PROVENANCE"

    cost_ref = manifest["cost_policy_attestation_reference"]
    assert cost_ref["git_blob_id"] == "1e08dc4a0bc2f82c8318e8aa57c71e90b0980b1e"
    assert cost_ref["canonical_execution_model_fingerprint"] == "054c02ddc07dff2e61a45ed27200eaaf8ec93cc4308db38649395443b6b09108"
