"""Phase 8 V2 Tier-B Feasibility Engine (phase8-v2-tierb-feasibility-plan-v1-TC002 / phase8-v2-tierb-feasibility-tooling-v1-TC002).

Implements the prospective two-stage candidate and lifecycle sample feasibility
protocol governing the evaluation of frozen development candidate `phase6-frozen-v2`
across reserved Tier-B development folds (`fold-02`, `fold-03`, `fold-04`).

Strict constraints enforced by this module:
1. Zero empirical store access without explicit preflight evidence checks and
   machine-readable release authorization;
2. Candidate evaluation uses the frozen V005 entry authority adapter without
   fills or broker costs;
3. Levels and intent geometry enforce symbol XAUUSDm, min_rr = 1.5, and direction
   invariance;
4. Stage 2 lifecycle evaluation accepts strictly PRIMARY_BASELINE scenario;
5. Completed-trade accounting strictly requires qualifying natural exits
   (STOP_LOSS, BREAK_EVEN, TRAILING_STOP, TAKE_PROFIT, EMERGENCY) reaching terminal
   CLOSED state;
6. END_OF_DATA_FORCED_CLOSE_EXCLUDED_FROM_SAMPLE is strictly excluded from the
   completed-trade count;
7. All non-completed states (CANCELLED, EXPIRED, REJECTED, unfilled, untriggered)
   are excluded;
8. Exact 1-to-1 setup-to-position barrier: each setup_id may produce at most one position;
9. Full accounting reconciliation holds:
   raw_candidate_ready == (qualifying_completed_trades + end_of_data_closed
                           + level_intent_attrition + unfilled_expired_cancelled
                           + never_opened + duplicate_events);
10. Absolute zero profitability metrics (P&L, win rate, Sharpe, drawdown, expectancy,
    profit factor, equity curves strictly prohibited and firewalled);
11. First-byte guard: EMPIRICAL_READ_BOUNDARY_ENTERED recorded immediately prior to
    first empirical store read.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from bot.execution.lifecycle.models import (
    Direction,
    EntryIntent,
    ExitReason,
    LifecycleStatus,
    ManagementConfig,
    MarketEvent,
    PositionState,
)
from bot.execution.lifecycle.entry import (
    create_entry_state,
    process_entry_event,
    record_fill,
)
from bot.execution.lifecycle.management import manage_position
from bot.scientific.canonical_bytes import (
    BlobSource,
    canonical_blob_bytes,
    working_tree_canonical_agreement,
)
from bot.strategy.setup_intent import (
    SetupSymbolMetadata,
    intent_from_setup_levels,
    level_inputs_from_setup,
)
from bot.strategy.trade_levels import LevelResult, build_trade_levels
from bot.strategy.variant_v005 import (
    V005_SOURCE_DIRECTIONAL_FALLBACK,
    V005_SOURCE_V003_BASELINE,
)

UTC = timezone.utc

PLAN_ID = "phase8-v2-tierb-feasibility-plan-v1-TC002"
PLAN_SCHEMA = "phase8v2.tierb-feasibility-plan.v3"
PLAN_CONTENT_SHA256 = (
    "033ea8a04ef6ee991001774abff034f6e4e0ea11445e30b030665c5aa413d943"
)

PARENT_PLAN_ID = "phase8-v2-tierb-feasibility-plan-v1-TC001"
PARENT_PLAN_CONTENT_SHA256 = (
    "5c2d5e4f29d2dfb3720dc264c8b28d240c0cf1cb8a62ccd40923ed5d8b2cfddf"
)

TOOLING_CORRECTION_ID = "phase8-v2-tierb-feasibility-tooling-v1-TC002"
HISTORICAL_TOOLING_COMMIT = "132343a0b1de527f6ecdb1776b7a90132068dbea"

FREEZE_IDENTITY = "phase6-frozen-v2"
DEVELOPMENT_PREDECESSOR = "phase6-development-v2-V005"
SEMANTIC_ANCHOR_COMMIT = "2fd3460b9010d8cca548f4fd6980b6b34fe594e2"
AUTHORITATIVE_MANIFEST_RELPATH = "baseline/phase8_v2_frozen_candidate_manifest_tc003.json"

EXPECTED_STRATEGY_DIGEST = (
    "ec4b5e6e6ded4797fce2d4d841d1b746e15f7435ac50569c62d6daa38953064f"
)
EXPECTED_CONFIG_SHA256 = (
    "1aa8b73fb207e10abfe9725bc2979e14692815a5ffe91502cef892b8bae6e806"
)
EXPECTED_VALIDATION_DIGEST = (
    "957dba56e2244b8cae773ddc17c716da629732d3f492e77578978ef9e091da3f"
)
EXPECTED_PROTECTED_DIGEST_V2 = (
    "666be323da1f5634e00d5a3285089d9318c99b300696d1f621db4d2cf07f9d7d"
)
EXPECTED_LEDGER_SEAL = "phase8-v2-ledger-seal-v2"

# Cost-policy & Provenance bindings
COST_POLICY_PACKAGE_ID = "evidence-development_cost_policy-v1-6b1a986b1f8d7b81"
COST_POLICY_FINGERPRINT = (
    "aa0ccc9368c0cf55b4775b4295f0424d4bdb0e5fd6cbfaf27137763be58e9404"
)
CANONICAL_EXECUTION_MODEL_FINGERPRINT = (
    "054c02ddc07dff2e61a45ed27200eaaf8ec93cc4308db38649395443b6b09108"
)
COST_ATTESTATION_FINGERPRINT = (
    "10e9a42e501b24b3cff3459a955cfef37c67d542dc76ef8300bcff596321ff42"
)
COST_ACTIVATION_PACKAGE_ID = "evidence-cost_policy_activation-v1-802914181c0ca505"
METADATA_BOUNDS_PACKAGE_ID = "evidence-development_metadata_bounds-v1-8dad509e60c8014a"
METADATA_POLICY_FINGERPRINT = (
    "54f9a9817613bf3115039dd43b66c476a72627880663d4fb6c3f59cbbde1be1f"
)
METADATA_READINESS_PACKAGE_ID = "evidence-development_metadata_bounds_readiness-v1-6fa811a3200c6042"

# Scenario Matrix bindings
SCENARIO_MATRIX_FINGERPRINT = (
    "3c59adbc16c2e2780041c1021e44066c5c43d980c5991af7fe32dcaaa36c3401"
)
PRIMARY_BASELINE_SCENARIO_ID = (
    "SWAP_EMAIL_REFERENCE|SLIPPAGE_MODERATE_ADVERSE|BASELINE_CURRENT_REFERENCE_PROXY"
)

# Sealed V005 R001 Rehearsal Artifact
SEALED_V005_R001_SHA256 = (
    "27b8849eb97074d55c36bf11645cae8821d517b1f9e52e0c9a37976c77abcbfe"
)
SEALED_V005_R001_BYTES = 80554

# Complete 16-item Pre-release Input Chain
COMPLETE_PRE_RELEASE_INPUT_CHAIN = {
    "tick_year_package_id": "exness-xauusdm-2024-development-b2a0234a470dd397",
    "derived_candles_package_id": "derived-candles-2024-v1-20260911T195553Z",
    "candle_attestation_package_id": "derived-candles-attestation-v1-6715e5c64d888215",
    "dxy_package_id": "dxy-development-2024-v1-20260912T091410.712364Z",
    "observed_spread_package_id": "observed_spread-v1-e25bdb9bf028a5be",
    "official_usd_news_package_id": "evidence-official_news-v1-78279c5e26c1c6d1",
    "phase8h_cost_policy_package_id": COST_POLICY_PACKAGE_ID,
    "phase8i_activation_package_id": COST_ACTIVATION_PACKAGE_ID,
    "phase8i_dataset_acceptance_review_package_id": "evidence-dataset_acceptance_review-v1-4d47816f5f336fe2",
    "historical_metadata_unavailability_package_id": "evidence-broker_metadata_unavailability-v1-f1be088c17a391c4",
    "phase8l_metadata_bounds_package_id": METADATA_BOUNDS_PACKAGE_ID,
    "phase8l_metadata_readiness_package_id": METADATA_READINESS_PACKAGE_ID,
    "contamination_register_path": "baseline/phase8_contamination_register.json",
    "candidate_freeze_manifest_path": AUTHORITATIVE_MANIFEST_RELPATH,
    "plan_tc002_path": "baseline/phase8_v2_tierb_feasibility_plan_tc002.json",
    "authoritative_ledger_seal_id": EXPECTED_LEDGER_SEAL,
}

REQUIRED_PREFLIGHT_PACKAGES = (
    "exness-xauusdm-2024-development-b2a0234a470dd397",
    "derived-candles-2024-v1-20260911T195553Z",
    "derived-candles-attestation-v1-6715e5c64d888215",
    "dxy-development-2024-v1-20260912T091410.712364Z",
    "observed_spread-v1-e25bdb9bf028a5be",
    "evidence-official_news-v1-78279c5e26c1c6d1",
    "evidence-development_cost_policy-v1-6b1a986b1f8d7b81",
    "evidence-cost_policy_activation-v1-802914181c0ca505",
    "evidence-dataset_acceptance_review-v1-4d47816f5f336fe2",
    "evidence-broker_metadata_unavailability-v1-f1be088c17a391c4",
    "evidence-development_metadata_bounds-v1-8dad509e60c8014a",
    "evidence-development_metadata_bounds_readiness-v1-6fa811a3200c6042",
)

# Thresholds & Quotas
STAGE1_FUTILITY_THRESHOLD = 30
STAGE1_HEADROOM_TARGET = 60
STAGE2_MIN_COMPLETED_TRADES = 30

# Classifications
LABEL_STAGE1_FUTILITY = "SAMPLE_SIZE_FUTILITY"
LABEL_STAGE1_HEADROOM_MET = "RESERVED_FOLD_RAW_HEADROOM_TARGET_MET"
LABEL_STAGE1_HEADROOM_NOT_MET = "RESERVED_FOLD_RAW_HEADROOM_TARGET_NOT_MET"
LABEL_STAGE2_FEASIBILITY_PASS = "RESERVED_FOLD_SAMPLE_FEASIBILITY_PASS"
LABEL_STAGE2_SAMPLE_INSUFFICIENT = "LIFECYCLE_SAMPLE_INSUFFICIENT"
LABEL_END_OF_DATA_EXCLUDED = "END_OF_DATA_FORCED_CLOSE_EXCLUDED_FROM_SAMPLE"
LABEL_GEOMETRY_ATTRITION = "LEVEL_OR_INTENT_CONSTRUCTION_ATTRITION"
LABEL_PREFLIGHT_BLOCKAGE = "TIER_B_PRE_RELEASE_EVIDENCE_BLOCKAGE"
LABEL_PARITY_FAILURE = "FOLD01_V005_ENTRY_PARITY_FAILURE"
LABEL_IDENTITY_MISMATCH = "FROZEN_CANDIDATE_EXECUTION_IDENTITY_MISMATCH"
LABEL_FIRST_EMPIRICAL_BYTE_READ = "FIRST_EMPIRICAL_BYTE_READ"
LABEL_EMPIRICAL_BOUNDARY_ENTERED = "EMPIRICAL_READ_BOUNDARY_ENTERED"

AUTHORIZED_OPERATIONS = (
    "FOLD01_PARITY_REHEARSAL",
    "FOLD01_LIFECYCLE_REHEARSAL",
    "RESERVED_FOLD_FEASIBILITY",
)

MANDATORY_STAGE2_QUALIFICATIONS = (
    "DEVELOPMENT_PROXY_NOT_HISTORICALLY_VALIDATED",
    "HISTORICAL_SWAP_UNCERTAIN",
)

PROHIBITED_METRICS = (
    "profit_and_loss",
    "net_profit",
    "gross_profit",
    "gross_loss",
    "win_rate",
    "profit_factor",
    "expectancy",
    "sharpe_ratio",
    "sortino_ratio",
    "returns_pct",
    "equity_curve",
    "drawdown_monetary",
    "drawdown_pct",
    "avg_winner",
    "avg_loser",
    "r_multiple_profitability",
)

QUALIFYING_NATURAL_EXITS = {
    ExitReason.STOP_LOSS,
    ExitReason.BREAK_EVEN,
    ExitReason.TRAILING_STOP,
    ExitReason.TAKE_PROFIT,
    ExitReason.EMERGENCY,
}

QUALIFYING_NATURAL_EXIT_NAMES = {e.name for e in QUALIFYING_NATURAL_EXITS}

NON_COMPLETED_EXCLUDED_STATES = {
    "CANCELLED",
    "EXPIRED",
    "REJECTED",
    "UNFILLED_INTENT",
    "UNTRIGGERED_INTENT",
    "NEVER_OPENED",
    "PARTIALLY_CLOSED_WITHOUT_FINAL_CLOSE",
    "DUPLICATE_LIFECYCLE_EVENT",
    LABEL_END_OF_DATA_EXCLUDED,
}

CANONICAL_SOURCES = {V005_SOURCE_V003_BASELINE, V005_SOURCE_DIRECTIONAL_FALLBACK}
CANONICAL_DIRECTIONS = {"buy", "sell"}
CANONICAL_SIDES = {"LONG", "SHORT"}

RELEASE_AUTHORIZATION_SCHEMA = "phase8v2.tierb-release-authorization.v1"


class TierBFeasibilityError(RuntimeError):
    """Base error for Tier-B feasibility contract violations."""


class TierBPreflightError(TierBFeasibilityError):
    """Raised when pre-release evidence packages are missing, invalid, or drifted."""


class TierBContaminationError(TierBFeasibilityError):
    """Raised when empirical store access is attempted without authorization."""


class TierBParityError(TierBFeasibilityError):
    """Raised when Fold-01 rehearsal parity checks fail."""


class TierBProfitabilityViolation(TierBFeasibilityError):
    """Raised when prohibited profitability metrics are detected."""


class TierBAuthorizationError(TierBFeasibilityError):
    """Raised when release authorization is missing, invalid, or prerequisites unfulfilled."""


DEFAULT_EVIDENCE_ROOT = Path("C:/Users/chips/forex-signal-bot-data/phase8/evidence")
DEFAULT_DATA_ROOT = Path("C:/Users/chips/forex-signal-bot-data/phase8")


def resolve_canonical_git_head(repo_root: Path) -> str:
    """Resolve canonical Git HEAD commit hash without stale fallbacks."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
        if len(out) == 40 and all(c in "0123456789abcdef" for c in out.lower()):
            return out.lower()
    except Exception:
        pass

    git_dir = repo_root / ".git"
    if git_dir.is_file():
        content = git_dir.read_text(encoding="utf-8").strip()
        if content.startswith("gitdir:"):
            git_dir = (repo_root / content[7:].strip()).resolve()
    head_file = git_dir / "HEAD"
    if head_file.is_file():
        ref = head_file.read_text(encoding="utf-8").strip()
        if ref.startswith("ref:"):
            ref_path = git_dir / ref[4:].strip()
            if ref_path.is_file():
                return ref_path.read_text(encoding="utf-8").strip().lower()
        elif len(ref) == 40 and all(c in "0123456789abcdef" for c in ref.lower()):
            return ref.lower()

    raise TierBPreflightError("Cannot resolve canonical Git HEAD commit")


def assert_zero_profitability(data: Any, path: str = "") -> None:
    """Recursively verify that no prohibited profitability metrics are present."""
    if isinstance(data, dict):
        for k, v in data.items():
            k_lower = str(k).lower()
            if k_lower in ("take_profit", "takeprofit"):
                assert_zero_profitability(v, f"{path}.{k}")
                continue
            if k in (
                "prohibited_metrics", "description", "classification",
                "banned_output_guard", "prohibitions", "notes",
                "valid_natural_exit_reasons"
            ):
                assert_zero_profitability(v, f"{path}.{k}")
                continue
            for token in (
                "sharpe", "sortino", "pnl", "profit_and_loss", "net_profit",
                "gross_profit", "gross_loss", "profit_factor", "win_rate",
                "expectancy", "drawdown", "equity_curve", "r_multiple",
                "returns_pct", "avg_winner", "avg_loser",
            ):
                if token in k_lower:
                    raise TierBProfitabilityViolation(
                        f"Prohibited profitability metric token '{token}' in key: {path}.{k}"
                    )
            if k_lower == "profit" or k_lower.startswith("profit_") or k_lower.endswith("_profit"):
                raise TierBProfitabilityViolation(
                    f"Prohibited profitability metric in key: {path}.{k}"
                )
            assert_zero_profitability(v, f"{path}.{k}")
    elif isinstance(data, (list, tuple)):
        for idx, item in enumerate(data):
            assert_zero_profitability(item, f"{path}[{idx}]")


def compute_plan_content_sha256(plan_data: Mapping[str, Any]) -> str:
    """Compute canonical content SHA-256 for plan JSON excluding plan_content_sha256."""
    content_copy = {k: v for k, v in plan_data.items() if k != "plan_content_sha256"}
    rendered = json.dumps(content_copy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def verify_plan_tc002(repo_root: Path) -> dict[str, Any]:
    """Verify Plan-TC002 schema, content SHA, and prospective contract."""
    plan_path = repo_root / "baseline" / "phase8_v2_tierb_feasibility_plan_tc002.json"
    if not plan_path.is_file():
        raise TierBFeasibilityError(f"Plan TC002 file missing: {plan_path}")
    with open(plan_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("plan_id") != PLAN_ID:
        raise TierBFeasibilityError(f"Unexpected plan_id: {data.get('plan_id')}")
    if data.get("schema_version") != PLAN_SCHEMA:
        raise TierBFeasibilityError(f"Unexpected schema_version: {data.get('schema_version')}")

    computed_sha = compute_plan_content_sha256(data)
    if computed_sha != PLAN_CONTENT_SHA256:
        raise TierBFeasibilityError(
            f"Plan TC002 content SHA mismatch: computed {computed_sha} != {PLAN_CONTENT_SHA256}"
        )
    if data.get("plan_content_sha256") != PLAN_CONTENT_SHA256:
        raise TierBFeasibilityError("Plan TC002 embedded content SHA mismatch")

    assert_zero_profitability(data)
    return data


def verify_tooling_integrity(repo_root: Path) -> dict[str, Any]:
    """Verify frozen candidate manifest TC003, all four digests, and ledger seal v2."""
    manifest_path = repo_root / AUTHORITATIVE_MANIFEST_RELPATH
    if not manifest_path.is_file():
        raise TierBFeasibilityError(f"Manifest missing: {manifest_path}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    strat_digest = manifest.get("strategy_semantic_identity_v2", {}).get("aggregate_digest")
    if strat_digest != EXPECTED_STRATEGY_DIGEST:
        raise TierBFeasibilityError(f"Strategy digest mismatch: {strat_digest} != {EXPECTED_STRATEGY_DIGEST}")

    config_sha = manifest.get("configuration_identity", {}).get("complete_candidate_configuration_identity")
    if config_sha != EXPECTED_CONFIG_SHA256:
        raise TierBFeasibilityError(f"Config SHA mismatch: {config_sha} != {EXPECTED_CONFIG_SHA256}")

    val_digest = manifest.get("validation_pipeline_identity_v1", {}).get("aggregate_digest")
    if val_digest != EXPECTED_VALIDATION_DIGEST:
        raise TierBFeasibilityError(f"Validation digest mismatch: {val_digest} != {EXPECTED_VALIDATION_DIGEST}")

    prot_digest = manifest.get("protected_infrastructure_identity_v2", {}).get("aggregate_digest")
    if prot_digest != EXPECTED_PROTECTED_DIGEST_V2:
        raise TierBFeasibilityError(f"Protected digest mismatch: {prot_digest} != {EXPECTED_PROTECTED_DIGEST_V2}")

    reg_path = repo_root / "baseline" / "phase8_v2_hypothesis_register.json"
    if not reg_path.is_file():
        raise TierBFeasibilityError(f"Hypothesis register missing: {reg_path}")
    with open(reg_path, "r", encoding="utf-8") as f:
        reg = json.load(f)

    ledger_seals = [
        r for r in reg.get("result_records", [])
        if r.get("record_id") == EXPECTED_LEDGER_SEAL
    ]
    if len(ledger_seals) != 1:
        raise TierBFeasibilityError(f"Expected 1 ledger seal for {EXPECTED_LEDGER_SEAL}, found {len(ledger_seals)}")
    seal = ledger_seals[0]
    if seal.get("unresolved_entities_count") != 0:
        raise TierBFeasibilityError("Ledger seal contains unresolved entities")

    return {
        "manifest_path": str(manifest_path),
        "freeze_identity": FREEZE_IDENTITY,
        "development_predecessor": DEVELOPMENT_PREDECESSOR,
        "semantic_anchor_commit": SEMANTIC_ANCHOR_COMMIT,
        "strategy_digest": strat_digest,
        "config_sha256": config_sha,
        "validation_digest": val_digest,
        "protected_digest_v2": prot_digest,
        "ledger_seal": EXPECTED_LEDGER_SEAL,
        "unresolved_entities_count": 0,
        "verified": True,
    }


def verify_frozen_candidate_execution_integrity(
    repo_root: Path,
    *,
    active_commit: str | None = None,
    blob_source: BlobSource | None = None,
    manifest_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify that current Git blobs match frozen candidate TC003 declarations.

    Fails closed with FROZEN_CANDIDATE_EXECUTION_IDENTITY_MISMATCH if any strategy,
    configuration, or protected file has drifted at the active execution commit.
    """
    commit_to_verify = active_commit or resolve_canonical_git_head(repo_root)

    if blob_source is None:
        try:
            from tests.test_phase8_v2_frozen_candidate import GitObjectStore
            _store = GitObjectStore(repo_root)
            _t_cache: dict[str, dict[str, tuple[str, str]]] = {}
            _orig_rt = _store._read_tree
            def _c_rt(sha: str):
                if sha not in _t_cache:
                    _t_cache[sha] = _orig_rt(sha)
                return _t_cache[sha]
            _store._read_tree = _c_rt
            def _auto_source(c: str, p: str) -> bytes:
                try:
                    return canonical_blob_bytes(p, commit=c, repo=repo_root)
                except Exception:
                    return _store.blob_bytes(c, p)
            blob_source = _auto_source
        except Exception:
            pass

    if manifest_data is None:
        manifest_path = repo_root / AUTHORITATIVE_MANIFEST_RELPATH
        if not manifest_path.is_file():
            raise TierBPreflightError(f"[{LABEL_IDENTITY_MISMATCH}] Manifest missing: {manifest_path}")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

    # 1. Manifest digests validation
    strat = manifest_data.get("strategy_semantic_identity_v2", {})
    if strat.get("aggregate_digest") != EXPECTED_STRATEGY_DIGEST:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Strategy aggregate digest drifted in manifest: "
            f"{strat.get('aggregate_digest')} != {EXPECTED_STRATEGY_DIGEST}"
        )

    cfg = manifest_data.get("configuration_identity", {})
    if cfg.get("complete_candidate_configuration_identity") != EXPECTED_CONFIG_SHA256:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Configuration SHA drifted: "
            f"{cfg.get('complete_candidate_configuration_identity')} != {EXPECTED_CONFIG_SHA256}"
        )

    val = manifest_data.get("validation_pipeline_identity_v1", {})
    if val.get("aggregate_digest") != EXPECTED_VALIDATION_DIGEST:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Validation pipeline digest drifted: "
            f"{val.get('aggregate_digest')} != {EXPECTED_VALIDATION_DIGEST}"
        )

    prot = manifest_data.get("protected_infrastructure_identity_v2", {})
    if prot.get("aggregate_digest") != EXPECTED_PROTECTED_DIGEST_V2:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Protected infrastructure digest drifted: "
            f"{prot.get('aggregate_digest')} != {EXPECTED_PROTECTED_DIGEST_V2}"
        )

    # 2. Recompute and verify all paths between anchor and active commit byte-for-byte
    strat_paths = list(strat.get("ordered_semantic_paths") or [])
    if len(strat_paths) != 83:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Expected 83 strategy semantic paths, found {len(strat_paths)}"
        )

    profile_info = cfg.get("effective_xauusdm_profile") or {}
    config_paths = list((profile_info.get("source_blob_ids") or {}).keys())
    protected_paths = list(prot.get("enforcing_paths") or [])

    all_paths = list(dict.fromkeys(strat_paths + config_paths + protected_paths))

    for path in all_paths:
        try:
            b_anchor = canonical_blob_bytes(path, commit=SEMANTIC_ANCHOR_COMMIT, repo=repo_root, blob_source=blob_source)
            b_active = canonical_blob_bytes(path, commit=commit_to_verify, repo=repo_root, blob_source=blob_source)
        except Exception as exc:
            raise TierBPreflightError(
                f"[{LABEL_IDENTITY_MISMATCH}] Failed reading Git blob for {path}: {exc}"
            ) from exc

        if b_anchor != b_active:
            raise TierBPreflightError(
                f"[{LABEL_IDENTITY_MISMATCH}] Git blob mismatch for {path} at active commit {commit_to_verify} vs anchor {SEMANTIC_ANCHOR_COMMIT}"
            )

        if not working_tree_canonical_agreement(path, commit=commit_to_verify, repo=repo_root, blob_source=blob_source):
            raise TierBPreflightError(
                f"[{LABEL_IDENTITY_MISMATCH}] Working tree path not clean: {path}"
            )

    # 3. Check effective XAUUSDm profile lock in code
    from config.symbol_profiles import get_symbol_profile
    profile = get_symbol_profile("XAUUSDm")
    exec_lvls = profile.get("execution_levels") or {}
    if exec_lvls.get("min_stop_atr_mult") != 2.0:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Effective XAUUSDm profile min_stop_atr_mult must be 2.0, got {exec_lvls.get('min_stop_atr_mult')}"
        )
    if exec_lvls.get("min_stop_price") != 10.0:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Effective XAUUSDm profile min_stop_price must be 10.0, got {exec_lvls.get('min_stop_price')}"
        )
    if exec_lvls.get("min_stop_points") != 500:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Effective XAUUSDm profile min_stop_points must be 500, got {exec_lvls.get('min_stop_points')}"
        )
    if exec_lvls.get("max_stop_atr_mult") != 8.0:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Effective XAUUSDm profile max_stop_atr_mult must be 8.0, got {exec_lvls.get('max_stop_atr_mult')}"
        )
    if exec_lvls.get("max_stop_price") != 40.0:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Effective XAUUSDm profile max_stop_price must be 40.0, got {exec_lvls.get('max_stop_price')}"
        )
    if exec_lvls.get("anchor_buffer_atr_mult") != 0.10:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Effective XAUUSDm profile anchor_buffer_atr_mult must be 0.10, got {exec_lvls.get('anchor_buffer_atr_mult')}"
        )
    if exec_lvls.get("anchor_buffer_price") != 0.75:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Effective XAUUSDm profile anchor_buffer_price must be 0.75, got {exec_lvls.get('anchor_buffer_price')}"
        )
    if profile.get("min_rr") != 1.5:
        raise TierBPreflightError(
            f"[{LABEL_IDENTITY_MISMATCH}] Effective XAUUSDm profile min_rr must be 1.5, got {profile.get('min_rr')}"
        )

    return {
        "status": "FROZEN_CANDIDATE_EXECUTION_INTEGRITY_VERIFIED",
        "freeze_identity": FREEZE_IDENTITY,
        "semantic_anchor_commit": SEMANTIC_ANCHOR_COMMIT,
        "active_commit": commit_to_verify,
        "strategy_paths_verified": len(strat_paths),
        "config_paths_verified": len(config_paths),
        "protected_paths_verified": len(protected_paths),
        "total_paths_verified": len(all_paths),
        "strategy_digest": EXPECTED_STRATEGY_DIGEST,
        "config_sha256": EXPECTED_CONFIG_SHA256,
        "validation_digest": EXPECTED_VALIDATION_DIGEST,
        "protected_digest_v2": EXPECTED_PROTECTED_DIGEST_V2,
    }


def pre_release_evidence_preflight(
    repo_root: Path | None = None,
    *,
    evidence_root: Path | None = None,
    data_root: Path | None = None,
    active_commit: str | None = None,
    blob_source: BlobSource | None = None,
) -> dict[str, Any]:
    """Verify the complete 16-item development input chain and prospective readiness before opening stores."""
    root = repo_root or Path(__file__).resolve().parents[2]

    if evidence_root is not None:
        target_evidence = Path(evidence_root)
    elif DEFAULT_EVIDENCE_ROOT.is_dir():
        target_evidence = DEFAULT_EVIDENCE_ROOT
    elif (root / "evidence").is_dir():
        target_evidence = root / "evidence"
    else:
        target_evidence = DEFAULT_EVIDENCE_ROOT

    if data_root is not None:
        target_data = Path(data_root)
    elif DEFAULT_DATA_ROOT.is_dir():
        target_data = DEFAULT_DATA_ROOT
    elif target_evidence.parent.is_dir():
        target_data = target_evidence.parent
    else:
        target_data = DEFAULT_DATA_ROOT

    def _resolve_pkg(pkg: str) -> Path | None:
        if pkg.startswith("exness-"):
            p = target_data / "exness-tick-history" / "processed" / "year-packages" / pkg / "manifest.json"
            if p.is_file():
                return p
        elif pkg.startswith("derived-candles-attestation"):
            p = target_data / "derived" / "attestations" / pkg / "attestation.json"
            if p.is_file():
                return p
            p = target_data / "derived" / "discovery" / pkg / "discovery.json"
            if p.is_file():
                return p
        elif pkg.startswith("derived-"):
            p = target_data / "derived" / pkg / "manifest.json"
            if p.is_file():
                return p
        elif pkg.startswith("dxy-"):
            p = target_data / "dxy" / pkg / "manifest.json"
            if p.is_file():
                return p
        else:
            p = target_evidence / pkg / "manifest.json"
            if p.is_file():
                return p
            p = target_evidence / pkg / "package.json"
            if p.is_file():
                return p
        return None

    # 1. Package existence check for required packages
    missing_packages = []
    found_packages = []
    for pkg_id in REQUIRED_PREFLIGHT_PACKAGES:
        pkg_manifest = _resolve_pkg(pkg_id)
        if pkg_manifest is None:
            missing_packages.append(pkg_id)
        else:
            found_packages.append(pkg_id)

    if missing_packages:
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Missing required preflight packages: {missing_packages}. "
            "Execution halted fail-closed before any empirical byte read."
        )

    # 2. Prospective input readiness verification
    contamination_path = root / "baseline" / "phase8_contamination_register.json"
    if not contamination_path.is_file():
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Contamination register missing: {contamination_path}"
        )

    attestation_path = root / "baseline" / "phase8_v2_cost_policy_canonical_attestation.json"
    if not attestation_path.is_file():
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Cost policy canonical attestation missing: {attestation_path}"
        )

    with open(attestation_path, "r", encoding="utf-8") as f:
        attestation = json.load(f)

    commit_to_use = active_commit or resolve_canonical_git_head(root)

    from bot.validation.development_evaluation_plan import verify_input_readiness_prospective

    try:
        readiness_report = verify_input_readiness_prospective(
            data_root=target_data,
            worktree=root,
            contamination_path=contamination_path,
            tick_verification_depth="identity-chain",
            research_identity="phase6-development-v2",
            variant_id="phase6-development-v2-V005",
            fingerprint_contract="canonical_git_blob_v1",
            active_commit=commit_to_use,
            attestation=attestation,
        )
    except Exception as exc:
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Prospective input readiness verification failed: {exc}"
        ) from exc

    # 3. Phase 8I activation verification
    activation_pkg_json = target_evidence / COST_ACTIVATION_PACKAGE_ID / "package.json"
    if not activation_pkg_json.is_file():
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Phase 8I activation package.json missing: {activation_pkg_json}"
        )

    with open(activation_pkg_json, "r", encoding="utf-8") as f:
        act_pkg = json.load(f)
    act_content = act_pkg.get("content", act_pkg)

    from bot.validation.cost_policy_activation import verify_activation_record

    try:
        verify_activation_record(act_content)
    except Exception as exc:
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Phase 8I activation record verification failed: {exc}"
        ) from exc

    if act_content.get("activation_state") != "ACTIVE_FOR_DEVELOPMENT_VALIDATION":
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Invalid activation state: {act_content.get('activation_state')}"
        )

    activated_policy_pkg = act_content.get("activated_policy", {}).get("package_id")
    if activated_policy_pkg != COST_POLICY_PACKAGE_ID:
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Phase 8I activation bound to wrong policy: {activated_policy_pkg}"
        )

    # 4. Phase 8L metadata readiness verification
    meta_readiness_pkg_json = target_evidence / METADATA_READINESS_PACKAGE_ID / "package.json"
    if not meta_readiness_pkg_json.is_file():
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Phase 8L metadata readiness package.json missing: {meta_readiness_pkg_json}"
        )

    with open(meta_readiness_pkg_json, "r", encoding="utf-8") as f:
        meta_pkg = json.load(f)
    meta_content = meta_pkg.get("content", meta_pkg)

    from bot.validation.development_metadata_bounds import verify_readiness

    try:
        verify_readiness(meta_content)
    except Exception as exc:
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Phase 8L metadata readiness verification failed: {exc}"
        ) from exc

    meta_policy = meta_content.get("policy", {})
    if meta_policy.get("package_id") != METADATA_BOUNDS_PACKAGE_ID:
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Phase 8L readiness bound to wrong bounds package: {meta_policy.get('package_id')}"
        )
    if meta_policy.get("policy_fingerprint") != METADATA_POLICY_FINGERPRINT:
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Phase 8L readiness bound to wrong policy fingerprint: {meta_policy.get('policy_fingerprint')}"
        )

    # 5. Commit-bound frozen candidate execution integrity
    frozen_check = verify_frozen_candidate_execution_integrity(
        root,
        active_commit=commit_to_use,
        blob_source=blob_source,
    )

    return {
        "status": "PREFLIGHT_PASSED",
        "verified_packages": found_packages,
        "package_count": len(found_packages),
        "prospective_readiness": readiness_report.get("prospective_binding"),
        "activation_verification": "ACTIVE_FOR_DEVELOPMENT_VALIDATION",
        "metadata_readiness_verification": "METADATA_READINESS_VERIFIED",
        "frozen_candidate_integrity": frozen_check,
    }


def validate_canonical_candidate(candidate: Mapping[str, Any]) -> None:
    """Validate that candidate conforms strictly to the canonical V005 candidate schema."""
    decision_id = candidate.get("decision_id")
    if not decision_id or not isinstance(decision_id, str):
        raise TierBFeasibilityError("Candidate missing valid non-empty decision_id")

    setup_id = candidate.get("setup_id")
    if not setup_id or not isinstance(setup_id, str):
        raise TierBFeasibilityError("Candidate missing valid non-empty setup_id")

    available_at_ms = candidate.get("available_at_ms")
    if available_at_ms is None or not isinstance(available_at_ms, (int, float)) or not math.isfinite(available_at_ms):
        raise TierBFeasibilityError(f"Candidate {decision_id} missing valid finite available_at_ms")

    side = candidate.get("side")
    if side not in CANONICAL_SIDES:
        raise TierBFeasibilityError(f"Candidate {decision_id} has invalid side: {side}")

    entry_direction = candidate.get("entry_direction")
    if entry_direction not in CANONICAL_DIRECTIONS:
        raise TierBFeasibilityError(f"Candidate {decision_id} has invalid entry_direction: {entry_direction}")

    entry_source = candidate.get("entry_source")
    if entry_source not in CANONICAL_SOURCES:
        raise TierBFeasibilityError(f"Candidate {decision_id} has invalid entry_source: {entry_source}")

    if side == "LONG" and entry_direction != "buy":
        raise TierBFeasibilityError(f"Candidate {decision_id} side/direction contradiction: LONG but direction is {entry_direction}")
    if side == "SHORT" and entry_direction != "sell":
        raise TierBFeasibilityError(f"Candidate {decision_id} side/direction contradiction: SHORT but direction is {entry_direction}")

    entry = candidate.get("entry")
    if not isinstance(entry, Mapping):
        raise TierBFeasibilityError(f"Candidate {decision_id} missing valid entry dict")

    if entry.get("direction") != entry_direction:
        raise TierBFeasibilityError(
            f"Candidate {decision_id} entry.direction ({entry.get('direction')}) != candidate entry_direction ({entry_direction})"
        )


def filter_candidates_by_window(
    candidates: Sequence[Mapping[str, Any]],
    evaluation_start: datetime,
    evaluation_end: datetime,
) -> tuple[Mapping[str, Any], ...]:
    """Filter candidates strictly by evaluation window: evaluation_start <= available_at < evaluation_end."""
    start_ms = int(evaluation_start.timestamp() * 1000)
    end_ms = int(evaluation_end.timestamp() * 1000)

    filtered = []
    for c in candidates:
        validate_canonical_candidate(c)
        avail = int(c["available_at_ms"])
        if start_ms <= avail < end_ms:
            filtered.append(c)

    return tuple(filtered)


@dataclass(frozen=True)
class Stage1CandidateReport:
    raw_candidate_ready: int
    unique_setup_ids: int
    duplicate_count: int
    long_count: int
    short_count: int
    v003_baseline_count: int
    v005_directional_fallback_count: int
    fallback_buy_count: int
    fallback_sell_count: int
    week_distribution: Mapping[str, int]
    session_distribution: Mapping[str, int]
    half_distribution: Mapping[str, int]
    futility_condition_met: bool
    headroom_target_met: bool
    futility_classification: str | None
    headroom_classification: str
    candidates: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        result = {
            "raw_candidate_ready": self.raw_candidate_ready,
            "unique_setup_ids": self.unique_setup_ids,
            "duplicate_count": self.duplicate_count,
            "long_count": self.long_count,
            "short_count": self.short_count,
            "v003_baseline_count": self.v003_baseline_count,
            "v005_directional_fallback_count": self.v005_directional_fallback_count,
            "fallback_buy_count": self.fallback_buy_count,
            "fallback_sell_count": self.fallback_sell_count,
            "week_distribution": dict(self.week_distribution),
            "session_distribution": dict(self.session_distribution),
            "half_distribution": dict(self.half_distribution),
            "futility_threshold": STAGE1_FUTILITY_THRESHOLD,
            "futility_condition_met": self.futility_condition_met,
            "futility_classification": self.futility_classification,
            "headroom_target": STAGE1_HEADROOM_TARGET,
            "headroom_target_met": self.headroom_target_met,
            "headroom_classification": self.headroom_classification,
        }
        assert_zero_profitability(result)
        return result


def evaluate_stage1_candidates(
    candidate_records: Sequence[Mapping[str, Any]],
    *,
    evaluation_start: datetime | None = None,
    evaluation_end: datetime | None = None,
) -> Stage1CandidateReport:
    """Analyze V005 candidate decisions for Stage-1 feasibility metrics."""
    assert_zero_profitability(candidate_records)

    if evaluation_start is not None and evaluation_end is not None:
        eligible_candidates = filter_candidates_by_window(
            candidate_records, evaluation_start, evaluation_end
        )
    else:
        for c in candidate_records:
            validate_canonical_candidate(c)
        eligible_candidates = tuple(candidate_records)

    total_raw = len(eligible_candidates)
    setup_ids: list[str] = []
    long_count = 0
    short_count = 0
    v003_baseline = 0
    v005_fallback = 0
    fallback_buy = 0
    fallback_sell = 0
    week_dist: dict[str, int] = {}
    session_dist: dict[str, int] = {}
    half_dist: dict[str, int] = {"first_half": 0, "second_half": 0}

    midpoint_ts: float | None = None
    if evaluation_start and evaluation_end:
        midpoint_ts = evaluation_start.timestamp() + (evaluation_end.timestamp() - evaluation_start.timestamp()) / 2.0

    for cand in eligible_candidates:
        sid = str(cand["setup_id"])
        setup_ids.append(sid)

        direction = str(cand["entry_direction"]).lower()
        if direction == "buy":
            long_count += 1
        elif direction == "sell":
            short_count += 1

        source = str(cand["entry_source"])
        if source == V005_SOURCE_V003_BASELINE:
            v003_baseline += 1
        elif source == V005_SOURCE_DIRECTIONAL_FALLBACK:
            v005_fallback += 1
            if direction == "buy":
                fallback_buy += 1
            elif direction == "sell":
                fallback_sell += 1

        week = cand.get("week") or cand.get("iso_week")
        if week:
            week_key = str(week)
            week_dist[week_key] = week_dist.get(week_key, 0) + 1

        sess = cand.get("session") or cand.get("active_session")
        if sess:
            sess_key = str(sess).lower()
            session_dist[sess_key] = session_dist.get(sess_key, 0) + 1

        avail_ms = cand.get("available_at_ms")
        if avail_ms and midpoint_ts is not None:
            ts_sec = avail_ms / 1000.0
            if ts_sec < midpoint_ts:
                half_dist["first_half"] += 1
            else:
                half_dist["second_half"] += 1

    unique_setups = len(set(setup_ids))
    duplicate_count = total_raw - unique_setups

    futility_met = total_raw < STAGE1_FUTILITY_THRESHOLD
    headroom_met = total_raw >= STAGE1_HEADROOM_TARGET

    return Stage1CandidateReport(
        raw_candidate_ready=total_raw,
        unique_setup_ids=unique_setups,
        duplicate_count=duplicate_count,
        long_count=long_count,
        short_count=short_count,
        v003_baseline_count=v003_baseline,
        v005_directional_fallback_count=v005_fallback,
        fallback_buy_count=fallback_buy,
        fallback_sell_count=fallback_sell,
        week_distribution=week_dist,
        session_distribution=session_dist,
        half_distribution=half_dist,
        futility_condition_met=futility_met,
        headroom_target_met=headroom_met,
        futility_classification=LABEL_STAGE1_FUTILITY if futility_met else None,
        headroom_classification=LABEL_STAGE1_HEADROOM_MET if headroom_met else LABEL_STAGE1_HEADROOM_NOT_MET,
        candidates=eligible_candidates,
    )


def replay_v005_candidates_from_store(
    store: Any,
    evaluation_start: datetime,
    evaluation_end: datetime,
    *,
    warmup_start: datetime | None = None,
    config: Any = None,
) -> list[dict[str, Any]]:
    """Replay frozen candidate V005 observation over a feature store.

    Reuses the exact frozen orchestration and observer mechanics from
    backtests.phase8_v2_variant_v005_eval:
    - classify_snapshot
    - evaluate_orchestration_decision
    - observe_v005_decision
    - StrategyState / state-record progression.

    Filters candidates strictly by evaluation window:
    evaluation_start <= available_at < evaluation_end.
    Returns canonical Stage-1 candidate records.
    """
    from backtests.phase8_v2_variant_v005_eval import (
        observe_v005_decision,
        assert_store_semantic_compatibility,
    )
    from backtests.phase8_v2_diagnostic_d001 import (
        _snapshot_rows,
        _reference_check_failed,
        classify_snapshot,
        evaluate_orchestration_decision,
    )
    from bot.strategy.config import StrategyConfig
    from bot.strategy.setup_state import StrategyState, record_from_state

    cfg = config or StrategyConfig()
    seed_time = warmup_start or evaluation_start
    state_record = record_from_state(
        StrategyState(event_time=seed_time), event_at=seed_time,
    )

    candidates: list[dict[str, Any]] = []

    for snapshot in _snapshot_rows(store):
        avail_ms = int(snapshot.available_at_ms)
        avail_dt = datetime.fromtimestamp(avail_ms / 1000.0, tz=UTC)

        if avail_dt >= evaluation_end:
            break

        bucket = classify_snapshot(snapshot)
        if bucket is not None:
            continue
        if _reference_check_failed(snapshot):
            continue

        prior_state_record = state_record
        row, next_record = evaluate_orchestration_decision(
            snapshot, prior_state_record,
        )
        if row["action"] == "error":
            continue

        gate11_entered = "gate_11_confluence_score" in (
            row.get("gate_results") or {}
        )
        if gate11_entered:
            assert_store_semantic_compatibility(snapshot)
            v005_obs = observe_v005_decision(
                row,
                snapshot,
                prior_state_record,
                config=cfg,
                decision_result_record=next_record,
            )
            if v005_obs.get("v005_entry_ready"):
                if evaluation_start <= avail_dt < evaluation_end:
                    cand = {
                        "decision_id": v005_obs["decision_id"],
                        "setup_id": v005_obs["v005_setup_id"],
                        "available_at_ms": v005_obs["available_at_ms"],
                        "side": v005_obs["v005_side"],
                        "entry_direction": v005_obs["v005_entry_direction"],
                        "entry_source": v005_obs["v005_entry_source"],
                        "fvg_evidence_source": v005_obs["v005_fvg_evidence_source"],
                        "entry": v005_obs["v005_entry"],
                        "_causal_snapshot": snapshot,
                        "_prior_state_record": prior_state_record,
                        "_decision_result_record": next_record,
                    }
                    candidates.append(cand)

        state_record = next_record

    return candidates


@dataclass(frozen=True)
class CompletedTradeAccounting:
    qualifying_completed_trades: int
    natural_exit_distribution: Mapping[str, int]
    end_of_data_closed: int
    level_or_intent_attrition: int
    unfilled_or_expired_or_cancelled: int
    never_opened: int
    duplicate_events_rejected: int
    total_reconciled_raw: int
    reconciliation_balanced: bool
    feasibility_verdict: str

    def to_dict(self) -> dict[str, Any]:
        result = {
            "qualifying_completed_trades": self.qualifying_completed_trades,
            "natural_exit_distribution": dict(self.natural_exit_distribution),
            "end_of_data_closed": self.end_of_data_closed,
            "level_or_intent_attrition": self.level_or_intent_attrition,
            "unfilled_or_expired_or_cancelled": self.unfilled_or_expired_or_cancelled,
            "never_opened": self.never_opened,
            "duplicate_events_rejected": self.duplicate_events_rejected,
            "total_reconciled_raw": self.total_reconciled_raw,
            "reconciliation_balanced": self.reconciliation_balanced,
            "feasibility_verdict": self.feasibility_verdict,
            "qualifications": list(MANDATORY_STAGE2_QUALIFICATIONS),
        }
        assert_zero_profitability(result)
        return result


def reconcile_completed_trades(
    *,
    raw_candidates_count: int,
    qualifying_exits: Sequence[ExitReason | str],
    end_of_data_count: int = 0,
    attrition_count: int = 0,
    unfilled_or_expired_count: int = 0,
    never_opened_count: int = 0,
    duplicates_count: int = 0,
) -> CompletedTradeAccounting:
    """Reconcile completed trade lifecycle outcomes against Stage-1 raw candidates."""
    exit_dist: dict[str, int] = {}
    qualifying_count = 0

    for item in qualifying_exits:
        reason_name = item.name if isinstance(item, ExitReason) else str(item)

        if reason_name == ExitReason.END_OF_DATA.name:
            raise TierBFeasibilityError(
                "END_OF_DATA passed to qualifying_exits; must be counted under end_of_data_count"
            )

        if reason_name not in QUALIFYING_NATURAL_EXIT_NAMES:
            raise TierBFeasibilityError(
                f"Invalid or non-qualifying exit reason in completed sample: {reason_name}. "
                f"Accepted natural exits: {sorted(QUALIFYING_NATURAL_EXIT_NAMES)}"
            )

        exit_dist[reason_name] = exit_dist.get(reason_name, 0) + 1
        qualifying_count += 1

    total_accounted = (
        qualifying_count
        + end_of_data_count
        + attrition_count
        + unfilled_or_expired_count
        + never_opened_count
        + duplicates_count
    )

    reconciled = total_accounted == raw_candidates_count
    if not reconciled:
        raise TierBFeasibilityError(
            f"Trade accounting reconciliation failed: raw {raw_candidates_count} != "
            f"accounted {total_accounted} (qualifying: {qualifying_count}, "
            f"end_of_data: {end_of_data_count}, attrition: {attrition_count}, "
            f"unfilled/expired: {unfilled_or_expired_count}, never_opened: {never_opened_count}, "
            f"duplicates: {duplicates_count})"
        )

    verdict = (
        LABEL_STAGE2_FEASIBILITY_PASS
        if qualifying_count >= STAGE2_MIN_COMPLETED_TRADES
        else LABEL_STAGE2_SAMPLE_INSUFFICIENT
    )

    return CompletedTradeAccounting(
        qualifying_completed_trades=qualifying_count,
        natural_exit_distribution=exit_dist,
        end_of_data_closed=end_of_data_count,
        level_or_intent_attrition=attrition_count,
        unfilled_or_expired_or_cancelled=unfilled_or_expired_count,
        never_opened=never_opened_count,
        duplicate_events_rejected=duplicates_count,
        total_reconciled_raw=total_accounted,
        reconciliation_balanced=reconciled,
        feasibility_verdict=verdict,
    )


def verify_fold01_parity_against_sealed_v005(
    reproduced_candidates: Sequence[Mapping[str, Any]],
    sealed_artifact_path: Path,
) -> dict[str, Any]:
    """Verify exact candidate multiset and entry parity against sealed V005 R001 external artifact."""
    sealed_path = Path(sealed_artifact_path)
    if not sealed_path.is_file():
        raise TierBParityError(f"[{LABEL_PARITY_FAILURE}] Sealed V005 R001 artifact missing: {sealed_path}")

    raw_bytes = sealed_path.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    byte_count = len(raw_bytes)

    if sha256 != SEALED_V005_R001_SHA256:
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] SHA-256 mismatch: {sha256} != {SEALED_V005_R001_SHA256}"
        )
    if byte_count != SEALED_V005_R001_BYTES:
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Byte count mismatch: {byte_count} != {SEALED_V005_R001_BYTES}"
        )

    try:
        sealed_data = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise TierBParityError(f"[{LABEL_PARITY_FAILURE}] Sealed artifact JSON unreadable: {exc}") from exc

    assert_zero_profitability(sealed_data)

    if "candidate_surface" not in sealed_data or not isinstance(sealed_data["candidate_surface"], Mapping):
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Missing 'candidate_surface' mapping in sealed artifact"
        )

    candidate_surface = sealed_data["candidate_surface"]
    if "candidates" not in candidate_surface or not isinstance(candidate_surface["candidates"], list):
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Missing 'candidates' list in sealed candidate_surface"
        )

    sealed_candidates = candidate_surface["candidates"]
    if len(sealed_candidates) != 102:
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Sealed candidates count {len(sealed_candidates)} != 102"
        )

    total_reproduced = len(reproduced_candidates)
    if total_reproduced != 102:
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Expected 102 reproduced candidates, got {total_reproduced}"
        )

    for c in reproduced_candidates:
        validate_canonical_candidate(c)

    sealed_multiset = Counter((str(c["decision_id"]), str(c["setup_id"])) for c in sealed_candidates)
    rep_multiset = Counter((str(c["decision_id"]), str(c["setup_id"])) for c in reproduced_candidates)

    if sealed_multiset != rep_multiset:
        diff_missing = sealed_multiset - rep_multiset
        diff_extra = rep_multiset - sealed_multiset
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Candidate (decision_id, setup_id) multiset mismatch. "
            f"Missing from rep: {dict(diff_missing)}, Extra in rep: {dict(diff_extra)}"
        )

    sealed_by_pair = {(str(c["decision_id"]), str(c["setup_id"])): c for c in sealed_candidates}
    rep_by_pair = {(str(c["decision_id"]), str(c["setup_id"])): c for c in reproduced_candidates}

    for pair_key, sealed_c in sealed_by_pair.items():
        rep_c = rep_by_pair[pair_key]

        if sealed_c.get("entry_source") != rep_c.get("entry_source"):
            raise TierBParityError(
                f"[{LABEL_PARITY_FAILURE}] Candidate {pair_key} entry_source mismatch: "
                f"{sealed_c.get('entry_source')} != {rep_c.get('entry_source')}"
            )

        if sealed_c.get("entry_direction") != rep_c.get("entry_direction"):
            raise TierBParityError(
                f"[{LABEL_PARITY_FAILURE}] Candidate {pair_key} entry_direction mismatch: "
                f"{sealed_c.get('entry_direction')} != {rep_c.get('entry_direction')}"
            )

        if sealed_c.get("side") != rep_c.get("side"):
            raise TierBParityError(
                f"[{LABEL_PARITY_FAILURE}] Candidate {pair_key} side mismatch: "
                f"{sealed_c.get('side')} != {rep_c.get('side')}"
            )

        s_entry = sealed_c.get("entry")
        r_entry = rep_c.get("entry")
        if not s_entry or not r_entry:
            raise TierBParityError(f"[{LABEL_PARITY_FAILURE}] Missing entry object in candidate {pair_key}")

        s_json = json.dumps(s_entry, sort_keys=True, separators=(",", ":"), allow_nan=False)
        r_json = json.dumps(r_entry, sort_keys=True, separators=(",", ":"), allow_nan=False)

        if s_json != r_json:
            raise TierBParityError(
                f"[{LABEL_PARITY_FAILURE}] Deterministic entry JSON mismatch for candidate {pair_key}:\n"
                f"Sealed:     {s_json}\n"
                f"Reproduced: {r_json}"
            )

    rep_baseline = sum(1 for c in reproduced_candidates if c["entry_source"] == V005_SOURCE_V003_BASELINE)
    rep_fallback = sum(1 for c in reproduced_candidates if c["entry_source"] == V005_SOURCE_DIRECTIONAL_FALLBACK)

    if rep_baseline != 81:
        raise TierBParityError(f"[{LABEL_PARITY_FAILURE}] Expected 81 baseline candidates, got {rep_baseline}")
    if rep_fallback != 21:
        raise TierBParityError(f"[{LABEL_PARITY_FAILURE}] Expected 21 fallback candidates, got {rep_fallback}")

    return {
        "status": "FOLD01_PARITY_VERIFIED",
        "sealed_artifact_sha256": sha256,
        "sealed_artifact_bytes": byte_count,
        "total_candidates": total_reproduced,
        "v003_baseline_count": rep_baseline,
        "v005_directional_fallback_count": rep_fallback,
        "unique_setup_ids": len(rep_multiset),
        "duplicates": 0,
        "multiset_equality": True,
        "exact_entry_parity": True,
        "verified": True,
    }


def _extract_causal_context_and_frame(candidate: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
    """Extract causal context mapping and entry DataFrame from candidate's causal snapshot."""
    snapshot = candidate.get("_causal_snapshot")
    if snapshot is None:
        raise TierBFeasibilityError(
            f"[{LABEL_GEOMETRY_ATTRITION}] Candidate {candidate.get('decision_id')} missing causal snapshot"
        )
    payload = json.loads(snapshot.gate_payload) if isinstance(snapshot.gate_payload, str) else snapshot.gate_payload
    rows = list(payload.get("entry_rows") or [])
    from backtests.phase8_v2_variant_v002_eval import _entry_frame
    frame = _entry_frame(rows)

    dxy_context = dict(payload.get("dxy_context") or {})
    news_context = dict(payload.get("news_context") or {})
    session_context = dict(payload.get("session_context") or {})
    liquidity_context = dict(payload.get("liquidity_context") or {})
    internal = dict(payload.get("internal_structure") or {})
    market_cond = dict(payload.get("market_conditions") or {})
    if "atr" not in market_cond and payload.get("atr") is not None:
        market_cond["atr"] = payload.get("atr")

    context = {
        "entry": candidate.get("entry") or {},
        "ob": payload.get("ob") or {},
        "internal_structure": internal,
        "liquidity": liquidity_context,
        "market_conditions": market_cond,
        "dxy": dxy_context,
        "news": news_context,
        "session": session_context,
        "score": candidate.get("score") or {},
    }
    return context, frame


def candidate_to_trade_levels(
    candidate: Mapping[str, Any],
    *,
    context: Mapping[str, Any] | None = None,
    entry_frame: Any = None,
    metadata: SetupSymbolMetadata | None = None,
    profile: Mapping[str, Any] | None = None,
    min_rr: float = 1.5,
    min_rr_buffer: float = 0.10,
) -> LevelResult:
    """Canonical conversion of approved V005 candidate into trade levels via shared adapter."""
    validate_canonical_candidate(candidate)

    # 1. Resolve and validate frozen profile
    from config.symbol_profiles import get_symbol_profile
    prof = profile or get_symbol_profile("XAUUSDm")
    exec_lvls = prof.get("execution_levels") or {}

    min_stop_atr = exec_lvls.get("min_stop_atr_mult")
    if min_stop_atr != 2.0:
        raise TierBFeasibilityError(
            f"[{LABEL_GEOMETRY_ATTRITION}] Effective XAUUSDm min_stop_atr_mult must be 2.0, got {min_stop_atr}"
        )

    # 2. Extract or validate causal context and entry_frame
    ctx = context
    frame = entry_frame
    if ctx is None or frame is None:
        try:
            extracted_ctx, extracted_frame = _extract_causal_context_and_frame(candidate)
            ctx = ctx or extracted_ctx
            frame = frame or extracted_frame
        except Exception as exc:
            raise TierBFeasibilityError(
                f"[{LABEL_GEOMETRY_ATTRITION}] Causal context or entry frame missing for candidate {candidate.get('decision_id')}: {exc}"
            ) from exc

    if ctx is None or frame is None:
        raise TierBFeasibilityError(
            f"[{LABEL_GEOMETRY_ATTRITION}] Causal context or entry frame is None for candidate {candidate.get('decision_id')}"
        )

    # 3. Decision timestamp & Metadata
    avail_ms = int(candidate["available_at_ms"])
    decision_at = datetime.fromtimestamp(avail_ms / 1000.0, tz=UTC)

    meta = metadata or SetupSymbolMetadata(
        symbol="XAUUSDm",
        point=0.001,
        stops_level=10,
        digits=3,
        effective_from=datetime(2024, 1, 1, tzinfo=UTC),
        effective_until=datetime(2025, 1, 1, tzinfo=UTC),
        provenance="phase8n-development-proxy",
    )
    meta.validate_at(decision_at)

    try:
        inputs = level_inputs_from_setup(
            context=ctx,
            entry_frame=frame,
            metadata=meta,
            decision_at=decision_at,
            profile=prof,
            min_rr=min_rr,
            min_rr_buffer=min_rr_buffer,
        )
    except Exception as exc:
        raise TierBFeasibilityError(
            f"[{LABEL_GEOMETRY_ATTRITION}] level_inputs_from_setup failed: {exc}"
        ) from exc

    return build_trade_levels(inputs)


def candidate_to_entry_intent(
    candidate: Mapping[str, Any],
    levels: LevelResult,
    *,
    context: Mapping[str, Any] | None = None,
    entry_frame: Any = None,
    symbol: str = "XAUUSDm",
    source_timeframe: str = "M5",
    partial_close_fraction: float = 0.5,
    configuration_id: str = "phase6-frozen-v2-PRIMARY_BASELINE",
) -> EntryIntent:
    """Canonical construction of EntryIntent via shared intent_from_setup_levels adapter."""
    validate_canonical_candidate(candidate)
    if levels.stop is None or levels.target is None:
        raise TierBFeasibilityError(
            f"[{LABEL_GEOMETRY_ATTRITION}] Cannot create EntryIntent without valid levels: {levels.reason}"
        )

    ctx = context
    frame = entry_frame
    if ctx is None or frame is None:
        try:
            extracted_ctx, extracted_frame = _extract_causal_context_and_frame(candidate)
            ctx = ctx or extracted_ctx
            frame = frame or extracted_frame
        except Exception as exc:
            raise TierBFeasibilityError(
                f"[{LABEL_GEOMETRY_ATTRITION}] Causal context or entry frame missing for intent: {exc}"
            ) from exc

    if ctx is None or frame is None:
        raise TierBFeasibilityError(
            f"[{LABEL_GEOMETRY_ATTRITION}] Causal context or entry frame is None for intent"
        )

    try:
        return intent_from_setup_levels(
            symbol=symbol,
            source_timeframe=source_timeframe,
            context=ctx,
            entry_frame=frame,
            levels=levels,
            partial_close_fraction=partial_close_fraction,
            configuration_id=configuration_id,
        )
    except Exception as exc:
        raise TierBFeasibilityError(
            f"[{LABEL_GEOMETRY_ATTRITION}] intent_from_setup_levels failed: {exc}"
        ) from exc


def execute_candidate_lifecycle(
    intent: EntryIntent,
    market_events: Sequence[MarketEvent],
    *,
    management_config: ManagementConfig | None = None,
) -> tuple[PositionState | None, ExitReason | None]:
    """Low-level single candidate lifecycle against market events."""
    cfg = management_config or ManagementConfig(
        partial_close_fraction=0.5,
        partial_target_r=1.0,
        volume_min=0.01,
        volume_step=0.01,
        pnl_per_price_unit=1.0,
        trailing_enabled=False,
    )

    entry_state = create_entry_state(intent)
    position: PositionState | None = None
    exit_reason: ExitReason | None = None

    for event in market_events:
        if position is None:
            decision = process_entry_event(entry_state, event)
            entry_state = decision.state
            if decision.triggered and decision.proposed_fill_price is not None and decision.fill_kind is not None:
                position = record_fill(
                    entry_state,
                    event,
                    fill_price=decision.proposed_fill_price,
                    quantity=cfg.volume_min,
                    fill_kind=decision.fill_kind,
                )
        else:
            if position.status in (LifecycleStatus.OPEN, LifecycleStatus.PARTIALLY_CLOSED):
                res = manage_position(position, event, cfg)
                position = res.position
                if position.status == LifecycleStatus.CLOSED:
                    raw_exit = position.exit_reason
                    if isinstance(raw_exit, ExitReason):
                        exit_reason = raw_exit
                    elif raw_exit:
                        exit_reason = ExitReason(str(raw_exit))
                    break

    return position, exit_reason


def execute_stage2_primary_baseline(
    candidates: Sequence[Mapping[str, Any]],
    quotes: Iterable[Any],
    *,
    cost_policy_content: Mapping[str, Any] | None = None,
    initial_balance: float = 100_000.0,
    volume: float = 0.01,
) -> CompletedTradeAccounting:
    """Execute Stage-2 candidate sample evaluation under PRIMARY_BASELINE.

    Runs through canonical HistoricalExecutionEngine under:
    SWAP_EMAIL_REFERENCE | SLIPPAGE_MODERATE_ADVERSE | BASELINE_CURRENT_REFERENCE_PROXY.
    Enforces exact 1-to-1 setup-to-position idempotency.
    Reconciles all candidates against completed trades, attrition, and exclusions.
    Suppresses all profitability metrics.
    """
    assert_zero_profitability(candidates)

    if cost_policy_content is None:
        evidence_pkg = DEFAULT_EVIDENCE_ROOT / COST_POLICY_PACKAGE_ID / "package.json"
        if not evidence_pkg.is_file():
            alt_p = Path("evidence") / COST_POLICY_PACKAGE_ID / "package.json"
            if alt_p.is_file():
                evidence_pkg = alt_p
        if evidence_pkg.is_file():
            with open(evidence_pkg, "r", encoding="utf-8") as f:
                doc = json.load(f)
            cost_policy_content = doc.get("content", doc)
        else:
            cost_policy_content = {
                "cost_components": {
                    "commission": {"mode": "NONE"},
                    "swap": {"mode": "SCENARIO_LADDER"},
                },
                "swap_scenarios": [
                    {
                        "scenario_id": "SWAP_EMAIL_REFERENCE",
                        "long_usd_per_lot_per_day": -3.85,
                        "short_usd_per_lot_per_day": -0.25,
                        "triple_swap_weekday": "WEDNESDAY",
                        "triple_swap_multiplier": 3,
                    }
                ],
                "slippage_scenarios": [
                    {
                        "scenario_id": "SLIPPAGE_MODERATE_ADVERSE",
                        "kind": "FIXED_ADVERSE_POINTS",
                        "points": 1.0,
                    }
                ],
            }

    swap_scenario = next(
        s for s in cost_policy_content["swap_scenarios"]
        if s["scenario_id"] == "SWAP_EMAIL_REFERENCE"
    )

    from bot.validation.empirical_input_pipeline import (
        broker_symbol_metadata,
        slippage_model_for,
    )
    from bot.backtesting.engine import (
        HistoricalExecutionEngine,
        HistoricalExecutionPolicy,
    )
    from bot.backtesting.models import FidelityClass, RunMode
    from bot.backtesting.adapters import (
        process_quote_entry,
        manage_quote_position,
    )

    broker_metadata = broker_symbol_metadata(cost_policy_content, swap_scenario=swap_scenario)
    slippage_model = slippage_model_for(cost_policy_content, slippage_scenario_id="SLIPPAGE_MODERATE_ADVERSE")

    engine = HistoricalExecutionEngine(
        run_id="tierb-feasibility-stage2",
        metadata=broker_metadata,
        policy=HistoricalExecutionPolicy(
            mode=RunMode.DIAGNOSTIC,
            fidelity=FidelityClass.TICK_BID_ASK,
            maximum_spread_points=1_000_000_000.0,
            slippage=slippage_model,
        ),
        initial_balance=initial_balance,
    )

    mgmt_cfg = ManagementConfig(
        partial_close_fraction=0.5,
        partial_target_r=1.0,
        volume_min=volume,
        volume_step=0.01,
        pnl_per_price_unit=broker_metadata.tick_value / broker_metadata.tick_size,
        trailing_enabled=False,
    )

    attrition_count = 0
    duplicate_count = 0
    seen_setup_ids: set[str] = set()
    consumed_setup_ids: set[str] = set()

    pending_entries: list[dict[str, Any]] = []

    for c in candidates:
        sid = str(c["setup_id"])
        if sid in seen_setup_ids:
            duplicate_count += 1
            continue
        seen_setup_ids.add(sid)

        try:
            levels = candidate_to_trade_levels(c)
            intent = candidate_to_entry_intent(c, levels)
            entry_state = create_entry_state(intent)
            pending_entries.append({
                "candidate": c,
                "intent": intent,
                "state": entry_state,
                "setup_id": sid,
            })
        except TierBFeasibilityError:
            attrition_count += 1

    open_positions: dict[str, PositionState] = {}
    qualifying_exits: list[ExitReason] = []
    end_of_data_count = 0
    never_opened_count = 0
    unfilled_or_expired_count = 0

    quote_seq = 0
    for quote in quotes:
        quote_seq += 1

        rem_entries = []
        for item in pending_entries:
            intent = item["intent"]
            state = item["state"]
            sid = item["setup_id"]

            if quote.timestamp < intent.signal_available_at:
                rem_entries.append(item)
                continue

            if sid in consumed_setup_ids:
                duplicate_count += 1
                continue

            decision, position = process_quote_entry(
                engine,
                state,
                quote,
                sequence=quote_seq,
                quantity=volume,
            )

            if position is not None:
                consumed_setup_ids.add(sid)
                open_positions[position.trade_id] = position
            elif decision.state.status in (LifecycleStatus.CANCELLED, LifecycleStatus.EXPIRED, LifecycleStatus.REJECTED):
                unfilled_or_expired_count += 1
            else:
                item["state"] = decision.state
                rem_entries.append(item)
        pending_entries = rem_entries

        for trade_id, position in list(open_positions.items()):
            managed = manage_quote_position(
                engine,
                position,
                quote,
                sequence=quote_seq,
                config=mgmt_cfg,
            )
            if managed.status == LifecycleStatus.CLOSED:
                del open_positions[trade_id]
                exit_reason = managed.exit_reason
                if exit_reason in QUALIFYING_NATURAL_EXITS:
                    qualifying_exits.append(exit_reason)
                elif exit_reason == ExitReason.END_OF_DATA:
                    end_of_data_count += 1
                else:
                    unfilled_or_expired_count += 1
            else:
                open_positions[trade_id] = managed

    end_of_data_count += len(open_positions)
    open_positions.clear()

    unfilled_or_expired_count += len(pending_entries)
    pending_entries.clear()

    accounting = reconcile_completed_trades(
        raw_candidates_count=len(candidates),
        qualifying_exits=qualifying_exits,
        end_of_data_count=end_of_data_count,
        attrition_count=attrition_count,
        unfilled_or_expired_count=unfilled_or_expired_count,
        never_opened_count=never_opened_count,
        duplicates_count=duplicate_count,
    )

    assert_zero_profitability(accounting.to_dict())
    return accounting


@dataclass(frozen=True)
class ReleaseAuthorizationRecord:
    authorization_id: str
    target_partition: str
    authorized_operation: str
    governing_plan_id: str
    tooling_id: str
    frozen_candidate_identity: str
    supervisory_approval_reference: str
    output_path: str
    created_utc: str
    prior_sealed_pass_reference: str | None = None
    prior_sealed_parity_reference: str | None = None
    prior_sealed_lifecycle_reference: str | None = None

    def validate(self, expected_partition: str, expected_operation: str | None = None) -> None:
        if self.target_partition != expected_partition:
            raise TierBAuthorizationError(
                f"Release authorization target partition mismatch: {self.target_partition} != {expected_partition}"
            )
        if self.authorized_operation not in AUTHORIZED_OPERATIONS:
            raise TierBAuthorizationError(
                f"Release authorization operation invalid: {self.authorized_operation}. Allowed: {AUTHORIZED_OPERATIONS}"
            )
        if expected_operation and self.authorized_operation != expected_operation:
            raise TierBAuthorizationError(
                f"Release authorization operation mismatch: {self.authorized_operation} != {expected_operation}"
            )
        if self.governing_plan_id != PLAN_ID:
            raise TierBAuthorizationError(
                f"Release authorization governing plan mismatch: {self.governing_plan_id} != {PLAN_ID}"
            )
        if self.tooling_id != TOOLING_CORRECTION_ID:
            raise TierBAuthorizationError(
                f"Release authorization tooling id mismatch: {self.tooling_id} != {TOOLING_CORRECTION_ID}"
            )
        if self.frozen_candidate_identity != FREEZE_IDENTITY:
            raise TierBAuthorizationError(
                f"Release authorization candidate mismatch: {self.frozen_candidate_identity} != {FREEZE_IDENTITY}"
            )
        if not self.supervisory_approval_reference:
            raise TierBAuthorizationError("Release authorization missing supervisory_approval_reference")

        if expected_partition == "fold-01-rehearsal":
            if self.authorized_operation not in ("FOLD01_PARITY_REHEARSAL", "FOLD01_LIFECYCLE_REHEARSAL"):
                raise TierBAuthorizationError(
                    f"Invalid operation {self.authorized_operation} for fold-01-rehearsal"
                )
        elif expected_partition in ("fold-02", "fold-03", "fold-04"):
            if self.authorized_operation != "RESERVED_FOLD_FEASIBILITY":
                raise TierBAuthorizationError(
                    f"Reserved fold execution requires RESERVED_FOLD_FEASIBILITY, got {self.authorized_operation}"
                )

        if expected_partition == "fold-02":
            if not self.prior_sealed_parity_reference or not self.prior_sealed_lifecycle_reference:
                raise TierBAuthorizationError(
                    "Fold-02 authorization requires prior sealed Fold-01 parity and lifecycle references"
                )
        elif expected_partition == "fold-03":
            if not self.prior_sealed_pass_reference:
                raise TierBAuthorizationError(
                    "Fold-03 authorization requires sealed Fold-02 PASS reference"
                )
        elif expected_partition == "fold-04":
            if not self.prior_sealed_pass_reference:
                raise TierBAuthorizationError(
                    "Fold-04 authorization requires sealed Fold-03 PASS reference"
                )


class GuardedEmpiricalStoreReader:
    """Store wrapper enforcing strict verification ordering and recording exposure boundary."""

    def __init__(
        self,
        *,
        partition: str,
        authorization: ReleaseAuthorizationRecord,
        repo_root: Path,
        raw_store_opener: Callable[[], Any],
        expected_operation: str | None = None,
    ) -> None:
        self.partition = partition
        self.authorization = authorization
        self.repo_root = repo_root
        self._raw_store_opener = raw_store_opener
        self.expected_operation = expected_operation
        self.empirical_boundary_utc: str | None = None
        self.empirical_first_read_utc: str | None = None
        self.exposure_record: dict[str, Any] | None = None

    def open_store(self, *, preflight_already_run: bool = False, active_commit: str | None = None) -> Any:
        verify_plan_tc002(self.repo_root)
        verify_tooling_integrity(self.repo_root)

        if not preflight_already_run:
            pre_release_evidence_preflight(self.repo_root, active_commit=active_commit)

        self.authorization.validate(self.partition, expected_operation=self.expected_operation)

        out_p = Path(self.authorization.output_path)
        tmp_p = Path(str(out_p) + ".tmp")
        if out_p.exists():
            raise TierBFeasibilityError(f"Target output path already exists (not fresh): {out_p}")
        if tmp_p.exists():
            raise TierBFeasibilityError(f"Target temporary output path already exists (not fresh): {tmp_p}")

        boundary_utc = datetime.now(UTC).isoformat()
        self.empirical_boundary_utc = boundary_utc
        self.empirical_first_read_utc = boundary_utc

        self.exposure_record = {
            "status": LABEL_EMPIRICAL_BOUNDARY_ENTERED,
            "conservative_exposure_timestamp": boundary_utc,
            "empirical_first_read_utc": boundary_utc,
            "partition": self.partition,
            "governing_plan_id": PLAN_ID,
            "tooling_id": TOOLING_CORRECTION_ID,
            "authorization_id": self.authorization.authorization_id,
            "candidate_freeze_identity": FREEZE_IDENTITY,
            "result_path": str(out_p),
        }

        store = self._raw_store_opener()

        if hasattr(store, "identity") and isinstance(store.identity, Mapping):
            self.exposure_record["feature_store_identity"] = dict(store.identity)
            self.exposure_record["feature_store_sha256"] = store.identity.get("store_sha256")

            store_fold = store.identity.get("fold_id")
            if store_fold and store_fold != self.partition and self.partition != "fold-01-rehearsal":
                raise TierBFeasibilityError(
                    f"Store fold_id mismatch: {store_fold} != {self.partition}"
                )

        return store


def atomic_publish_json(target_path: Path | str, data: Mapping[str, Any]) -> None:
    """Atomically publish a JSON artifact. Fails if target or temp file exists."""
    p = Path(target_path)
    tmp_p = Path(str(p) + ".tmp")
    if p.exists():
        raise TierBFeasibilityError(f"Target output path already exists: {p}")
    if tmp_p.exists():
        raise TierBFeasibilityError(f"Temporary output path already exists: {tmp_p}")

    assert_zero_profitability(data)
    rendered = json.dumps(data, indent=2, sort_keys=True, allow_nan=False)

    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_p.write_text(rendered, encoding="utf-8")
    tmp_p.rename(p)
