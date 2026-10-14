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


import ast
import hashlib
import math
from utils.symbol_profiles import get_symbol_profile


MANIFEST_TC001_PATH = (
    REPO_ROOT / "baseline" / "phase8_v2_frozen_candidate_manifest_tc001.json"
)
REGISTER_PATH = REPO_ROOT / "baseline" / "phase8_v2_hypothesis_register.json"

STRATEGY_ROOTS = (
    "bot/state/gate_inputs.py",
    "bot/state/gate_reducer.py",
    "bot/strategy/config.py",
    "bot/strategy/variant_v003.py",
    "bot/strategy/variant_v005.py",
    "strategies/smc_engine/entry_model.py",
    "strategies/smc_engine/strategy_state.py",
    "config/symbol_profiles/__init__.py",
    "config/symbol_profiles/base.py",
    "config/symbol_profiles/xauusdm.py",
    "utils/symbol_profiles.py",
    "bot/state/orchestrator.py",
)

VAL_ROOTS = (
    "bot/validation/empirical_strategy_adapter.py",
    "bot/state/orchestrator.py",
    "main.py",
    "bot/backtesting/adapters.py",
    "bot/state/gate_reducer.py",
    "bot/state/gate_inputs.py",
    "bot/strategy/legacy_adapter.py",
    "bot/strategy/trade_levels.py",
    "bot/strategy/setup_intent.py",
    "strategies/smc_engine/entry_model.py",
    "bot/strategy/setup_consumption.py",
    "bot/execution/lifecycle/serialization.py",
    "bot/strategy/setup_recovery.py",
    "bot/strategy/setup_store.py",
    "bot/backtesting/fill_journal.py",
    "bot/validation/development_scenario_matrix.py",
    "bot/strategy/setup_state.py",
    "bot/validation/empirical_input_pipeline.py",
    "bot/validation/replay_input_index.py",
    "bot/validation/market_feature_store.py",
    "bot/validation/historical_news_replay.py",
    "bot/validation/runner_compatibility.py",
    "bot/validation/development_plan_revision.py",
)


def pure_git_blob_bytes(relative_path: str, repo_root: Path = REPO_ROOT) -> bytes:
    p = repo_root / relative_path
    content = p.read_bytes()
    return content.replace(b"\r\n", b"\n")


def pure_git_blob_id(relative_path: str, repo_root: Path = REPO_ROOT) -> str:
    content_lf = pure_git_blob_bytes(relative_path, repo_root)
    header = f"blob {len(content_lf)}".encode("ascii") + b"\x00"
    return hashlib.sha1(header + content_lf).hexdigest()


def compute_local_ast_closure(
    roots: tuple[str, ...],
    repo_root: Path = REPO_ROOT,
    exclude_prefixes: tuple[str, ...] = ("tests/", "docs/", "probes/", "scripts/"),
) -> list[str]:
    def is_repo_py_file(rel_path: str) -> bool:
        p = repo_root / rel_path
        return p.is_file() and rel_path.endswith(".py")

    def get_source_text(rel_path: str) -> str:
        return pure_git_blob_bytes(rel_path, repo_root).decode("utf-8", errors="replace")

    def resolve_import(source_file: str, node: ast.AST) -> list[str]:
        resolved: list[str] = []
        source_dir = Path(source_file).parent
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                cur = ""
                for p in parts:
                    cur = f"{cur}/{p}" if cur else p
                    init_p = f"{cur}/__init__.py"
                    if is_repo_py_file(init_p):
                        resolved.append(init_p)
                mod_p = f"{cur}.py"
                if is_repo_py_file(mod_p):
                    resolved.append(mod_p)
        elif isinstance(node, ast.ImportFrom):
            level = node.level
            module = node.module or ""
            if level > 0:
                base = source_dir
                for _ in range(level - 1):
                    base = base.parent
                base_str = base.as_posix()
                if base_str == ".":
                    base_str = ""
                if module:
                    mod_rel = module.replace(".", "/")
                    target_base = f"{base_str}/{mod_rel}" if base_str else mod_rel
                else:
                    target_base = base_str
                if is_repo_py_file(f"{target_base}.py"):
                    resolved.append(f"{target_base}.py")
                if is_repo_py_file(f"{target_base}/__init__.py"):
                    resolved.append(f"{target_base}/__init__.py")
                for alias in node.names:
                    sub_mod = (
                        f"{target_base}/{alias.name}.py"
                        if target_base
                        else f"{alias.name}.py"
                    )
                    sub_pkg = (
                        f"{target_base}/{alias.name}/__init__.py"
                        if target_base
                        else f"{alias.name}/__init__.py"
                    )
                    if is_repo_py_file(sub_mod):
                        resolved.append(sub_mod)
                    if is_repo_py_file(sub_pkg):
                        resolved.append(sub_pkg)
            else:
                parts = module.split(".")
                cur = ""
                for p in parts:
                    cur = f"{cur}/{p}" if cur else p
                    init_p = f"{cur}/__init__.py"
                    if is_repo_py_file(init_p):
                        resolved.append(init_p)
                mod_p = f"{cur}.py"
                if is_repo_py_file(mod_p):
                    resolved.append(mod_p)
                for alias in node.names:
                    sub_mod = f"{cur}/{alias.name}.py" if cur else f"{alias.name}.py"
                    sub_pkg = (
                        f"{cur}/{alias.name}/__init__.py"
                        if cur
                        else f"{alias.name}/__init__.py"
                    )
                    if is_repo_py_file(sub_mod):
                        resolved.append(sub_mod)
                    if is_repo_py_file(sub_pkg):
                        resolved.append(sub_pkg)
        return resolved

    visited = set(roots)
    for r in list(visited):
        parts = Path(r).parts[:-1]
        cur = ""
        for p in parts:
            cur = f"{cur}/{p}" if cur else p
            init_p = f"{cur}/__init__.py"
            if is_repo_py_file(init_p):
                visited.add(init_p)

    queue = list(visited)
    while queue:
        curr = queue.pop(0)
        if any(curr.startswith(pfx) for pfx in exclude_prefixes):
            continue
        content = get_source_text(curr)
        try:
            tree = ast.parse(content, filename=curr)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                res_files = resolve_import(curr, node)
                for rf in res_files:
                    if any(rf.startswith(pfx) for pfx in exclude_prefixes):
                        continue
                    parts = Path(rf).parts[:-1]
                    cur = ""
                    for p in parts:
                        cur = f"{cur}/{p}" if cur else p
                        init_p = f"{cur}/__init__.py"
                        if is_repo_py_file(init_p) and init_p not in visited:
                            visited.add(init_p)
                            queue.append(init_p)
                    if rf not in visited:
                        visited.add(rf)
                        queue.append(rf)
    return sorted(visited)


# ---------------------------------------------------------------------------
# TC001 Repaired Prospective Freeze Tests
# ---------------------------------------------------------------------------


def test_freeze_manifest_tc001_parses_and_validates_schema() -> None:
    assert MANIFEST_TC001_PATH.exists(), f"TC001 Manifest missing at {MANIFEST_TC001_PATH}"
    with open(MANIFEST_TC001_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["schema_version"] == "phase8v2.frozen-candidate-manifest.v2"
    assert manifest["record_type"] == "PROSPECTIVE_STRATEGY_FREEZE_MANIFEST_TC001"
    assert manifest["freeze_identity"] == "phase6-frozen-v2"
    assert manifest["development_predecessor"] == "phase6-development-v2-V005"
    assert manifest["semantic_anchor_commit"] == ANCHOR_COMMIT

    # References historical F001 as superseded
    hist = manifest["historical_f001_reference"]
    assert hist["freeze_record_id"] == "phase6-frozen-v2-F001"
    assert hist["historical_7_path_digest"] == EXPECTED_AGGREGATE_DIGEST
    assert hist["disposition"] == "SUPERSEDED_FOR_PROSPECTIVE_TIER_B_USE"

    # Zero path leakage
    dumped = json.dumps(manifest)
    assert "C:" not in dumped
    assert "/Users/" not in dumped
    assert "\\Users\\" not in dumped


def test_computed_runtime_closure_matches_tc001_manifest() -> None:
    with open(MANIFEST_TC001_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    strategy_sec = manifest["strategy_semantic_identity_v2"]
    manifest_paths = strategy_sec["ordered_semantic_paths"]
    manifest_digest = strategy_sec["aggregate_digest"]

    # Recompute runtime closure dynamically from roots
    computed_closure = compute_local_ast_closure(STRATEGY_ROOTS)
    assert computed_closure == manifest_paths
    assert len(computed_closure) == 83

    # Recompute prospective identity digest
    identity = freeze_prospective_identity(
        computed_closure,
        contract_id=CONTRACT_ID,
        commit=ANCHOR_COMMIT,
        repo=REPO_ROOT,
        blob_source=lambda commit, path: pure_git_blob_bytes(path, REPO_ROOT),
    )
    assert identity.digest == manifest_digest
    assert identity.digest == "ec4b5e6e6ded4797fce2d4d841d1b746e15f7435ac50569c62d6daa38953064f"

    # Omitting any single member must fail equality
    truncated = computed_closure[:-1]
    assert truncated != manifest_paths


def test_effective_xauusdm_profile_lock() -> None:
    with open(MANIFEST_TC001_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    cfg_sec = manifest["configuration_identity"]
    prof_sec = cfg_sec["effective_xauusdm_profile"]
    manifest_prof = prof_sec["canonical_profile_payload"]
    manifest_sha = prof_sec["profile_sha256"]

    # Derive effective profile from source code
    prof = get_symbol_profile("XAUUSDm")

    # Required field assertions
    assert prof["structure_tf"] == "H1"
    assert prof["entry_tf"] == "M5"
    assert prof["min_rr"] == 1.5
    assert prof["structure_bars"] == 300
    assert prof["entry_bars"] == 150
    assert prof["pair_limit"] == 1
    assert prof["risk_per_trade"] == 0.01

    def canonicalize_for_json(obj):
        if isinstance(obj, float) and math.isinf(obj):
            return {"__unbounded_profile_max__": True}
        if isinstance(obj, dict):
            return {k: canonicalize_for_json(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            return [canonicalize_for_json(x) for x in obj]
        return obj

    canon = canonicalize_for_json(prof)
    assert canon == manifest_prof

    rendered = json.dumps(canon, sort_keys=True, separators=(",", ":"), allow_nan=False)
    prof_sha = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    assert prof_sha == manifest_sha
    assert prof_sha == "7178799c23f85d5cfb867d73f1d9bcb74ae597beb88227ea9a217602770a879a"

    # Modifying one nested field must change profile SHA
    mutated = dict(canon)
    mutated_displacement = dict(mutated["displacement"])
    mutated_displacement["lookback_candles"] = 999
    mutated["displacement"] = mutated_displacement
    mutated_rendered = json.dumps(mutated, sort_keys=True, separators=(",", ":"), allow_nan=False)
    mutated_sha = hashlib.sha256(mutated_rendered.encode("utf-8")).hexdigest()
    assert mutated_sha != prof_sha


def test_complete_candidate_configuration_identity() -> None:
    with open(MANIFEST_TC001_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    cfg_sec = manifest["configuration_identity"]
    manifest_combined_sha = cfg_sec["complete_candidate_configuration_identity"]

    cfg = StrategyConfig()
    cfg_payload = {
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

    prof = get_symbol_profile("XAUUSDm")
    def canonicalize_for_json(obj):
        if isinstance(obj, float) and math.isinf(obj):
            return {"__unbounded_profile_max__": True}
        if isinstance(obj, dict):
            return {k: canonicalize_for_json(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            return [canonicalize_for_json(x) for x in obj]
        return obj

    canon_prof = canonicalize_for_json(prof)

    combined_envelope = {
        "strategy_config": cfg_payload,
        "xauusdm_profile": canon_prof,
    }
    rendered = json.dumps(combined_envelope, sort_keys=True, separators=(",", ":"), allow_nan=False)
    combined_sha = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    assert combined_sha == manifest_combined_sha
    assert combined_sha == "1aa8b73fb207e10abfe9725bc2979e14692815a5ffe91502cef892b8bae6e806"

    # Modifying either component must alter combined SHA
    mutated_cfg = dict(cfg_payload, confluence_threshold=9)
    mutated_envelope1 = {"strategy_config": mutated_cfg, "xauusdm_profile": canon_prof}
    assert (
        hashlib.sha256(
            json.dumps(mutated_envelope1, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        != combined_sha
    )


def test_validation_pipeline_identity() -> None:
    with open(MANIFEST_TC001_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    val_sec = manifest["validation_pipeline_identity_v1"]
    manifest_paths = val_sec["ordered_paths"]
    manifest_digest = val_sec["aggregate_digest"]

    # Recompute validation closure dynamically
    computed_val_closure = compute_local_ast_closure(VAL_ROOTS)
    assert computed_val_closure == manifest_paths
    assert len(computed_val_closure) == 147

    # Recompute prospective identity digest
    identity = freeze_prospective_identity(
        computed_val_closure,
        contract_id=CONTRACT_ID,
        commit=ANCHOR_COMMIT,
        repo=REPO_ROOT,
        blob_source=lambda commit, path: pure_git_blob_bytes(path, REPO_ROOT),
    )
    assert identity.digest == manifest_digest
    assert identity.digest == "957dba56e2244b8cae773ddc17c716da629732d3f492e77578978ef9e091da3f"


def test_protected_infrastructure_mapping() -> None:
    with open(MANIFEST_TC001_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    prot_sec = manifest["protected_infrastructure_identity_v1"]
    enforcing_paths = prot_sec["enforcing_paths"]
    manifest_digest = prot_sec["aggregate_digest"]
    control_map = prot_sec["control_mapping"]

    # Require minimum 17 controls
    assert len(control_map) >= 17

    # Verify each control has an enforcing source and resolves at anchor
    for ctrl_name, mapping in control_map.items():
        path = mapping["enforcing_path"]
        computed_blob = pure_git_blob_id(path, REPO_ROOT)
        assert mapping["git_blob_id"] == computed_blob, f"Blob mismatch for {path}"
        assert "symbol_or_function" in mapping and mapping["symbol_or_function"]

    # Recompute aggregate digest over unique enforcing paths
    identity = freeze_prospective_identity(
        enforcing_paths,
        contract_id=CONTRACT_ID,
        commit=ANCHOR_COMMIT,
        repo=REPO_ROOT,
        blob_source=lambda commit, path: pure_git_blob_bytes(path, REPO_ROOT),
    )
    assert identity.digest == manifest_digest
    assert identity.digest == "666be323da1f5634e00d5a3285089d9318c99b300696d1f621db4d2cf07f9d7d"


def test_scientific_ledger_terminality() -> None:
    with open(REGISTER_PATH, "r", encoding="utf-8") as f:
        reg = json.load(f)

    # Find ledger seal record
    seal = None
    h007_disp = None
    for r in reg["result_records"]:
        rid = r.get("record_id") or r.get("result_id")
        if rid == "phase8-v2-ledger-seal-v1":
            seal = r
        if rid == "phase8-v2-H007-R001":
            h007_disp = r

    assert seal is not None, "phase8-v2-ledger-seal-v1 missing from register"
    assert h007_disp is not None, "phase8-v2-H007-R001 missing from register"

    # H007 terminal resolution verification
    assert h007_disp["disposition"] == "SUPPORTED_BY_V002_STRUCTURAL_EVIDENCE"
    assert "SUPPORTED_STRUCTURALLY_ON_CONTAMINATED_TIER_A" in h007_disp["qualification"]
    assert h007_disp["evidence"]["candidate_ready"] == 61
    assert h007_disp["evidence"]["final_opportunity_classification"] == "OPPORTUNITY_INSUFFICIENT"

    # Verify ledger seal map covers all entities
    h_map = seal["hypotheses_terminality_map"]
    for h in reg["hypotheses"]:
        hid = h.get("id") or h.get("hypothesis_id")
        assert hid in h_map, f"Hypothesis {hid} not accounted for in ledger seal"

    d_map = seal["diagnostics_terminality_map"]
    for d in reg["diagnostics"]:
        did = d.get("id") or d.get("diagnostic_id")
        assert did in d_map, f"Diagnostic {did} not accounted for in ledger seal"

    v_map = seal["variants_terminality_map"]
    for v in reg["strategy_variants"]:
        vid = v.get("id") or v.get("variant_id")
        assert vid in v_map, f"Variant {vid} not accounted for in ledger seal"

    assert seal["unresolved_entities_count"] == 0
