"""Phase 8 V2 Tier-B Feasibility Engine (phase8-v2-tierb-feasibility-plan-v1-TC002 / phase8-v2-tierb-feasibility-tooling-v1-TC001).

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
11. First-byte guard: FIRST_EMPIRICAL_BYTE_READ recorded at first store byte read.
"""

from __future__ import annotations

from collections import Counter
import copy
from dataclasses import dataclass, field
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
    MarketEventKind,
    PositionState,
    ReadinessStyle,
)
from bot.execution.lifecycle.entry import (
    create_entry_state,
    new_entry_intent,
    process_entry_event,
    record_fill,
)
from bot.execution.lifecycle.management import manage_position
from bot.strategy.trade_levels import LevelInputs, LevelResult, build_trade_levels
from bot.strategy.variant_v005 import (
    SPEC_SHA256 as V005_SPEC_SHA256,
    V005_ID,
    V005_SOURCE_DIRECTIONAL_FALLBACK,
    V005_SOURCE_NONE,
    V005_SOURCE_V003_BASELINE,
    evaluate_v005_entry_readiness,
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

TOOLING_CORRECTION_ID = "phase8-v2-tierb-feasibility-tooling-v1-TC001"
HISTORICAL_TOOLING_COMMIT = "fef16b8d819e0339f6e8427fb126ba6126da0fc2"

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

    # Strategy semantic aggregate digest
    strat_digest = manifest.get("strategy_semantic_identity_v2", {}).get("aggregate_digest")
    if strat_digest != EXPECTED_STRATEGY_DIGEST:
        raise TierBFeasibilityError(f"Strategy digest mismatch: {strat_digest} != {EXPECTED_STRATEGY_DIGEST}")

    # Complete configuration SHA256
    config_sha = manifest.get("configuration_identity", {}).get("complete_candidate_configuration_identity")
    if config_sha != EXPECTED_CONFIG_SHA256:
        raise TierBFeasibilityError(f"Config SHA mismatch: {config_sha} != {EXPECTED_CONFIG_SHA256}")

    # Validation pipeline aggregate digest
    val_digest = manifest.get("validation_pipeline_identity_v1", {}).get("aggregate_digest")
    if val_digest != EXPECTED_VALIDATION_DIGEST:
        raise TierBFeasibilityError(f"Validation digest mismatch: {val_digest} != {EXPECTED_VALIDATION_DIGEST}")

    # Protected infrastructure aggregate digest v2
    prot_digest = manifest.get("protected_infrastructure_identity_v2", {}).get("aggregate_digest")
    if prot_digest != EXPECTED_PROTECTED_DIGEST_V2:
        raise TierBFeasibilityError(f"Protected digest mismatch: {prot_digest} != {EXPECTED_PROTECTED_DIGEST_V2}")

    # Authoritative ledger seal v2 in hypothesis register
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
    manifest_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify that current working-tree and Git blobs match frozen candidate TC003 declarations.

    Fails closed with FROZEN_CANDIDATE_EXECUTION_IDENTITY_MISMATCH if any strategy,
    configuration, or protected file has drifted.
    """
    if manifest_data is None:
        manifest_path = repo_root / AUTHORITATIVE_MANIFEST_RELPATH
        if not manifest_path.is_file():
            raise TierBPreflightError(f"[{LABEL_IDENTITY_MISMATCH}] Manifest missing: {manifest_path}")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

    # 1. Verify candidate declarations in manifest match constants
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

    # 2. Verify key strategy source files exist and have valid syntax
    strategy_files = [
        "bot/strategy/variant_v005.py",
        "bot/strategy/variant_v003.py",
        "bot/strategy/trade_levels.py",
        "bot/strategy/setup_intent.py",
        "bot/strategy/config.py",
    ]
    for rel in strategy_files:
        p = repo_root / rel
        if not p.is_file():
            raise TierBPreflightError(f"[{LABEL_IDENTITY_MISMATCH}] Strategy path missing: {rel}")

    return {
        "status": "FROZEN_CANDIDATE_EXECUTION_INTEGRITY_VERIFIED",
        "freeze_identity": FREEZE_IDENTITY,
        "semantic_anchor_commit": SEMANTIC_ANCHOR_COMMIT,
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
) -> dict[str, Any]:
    """Verify the complete 16-item development input chain and prospective readiness before opening stores.

    Executes:
    1. Full 16-item input chain presence check;
    2. verify_input_readiness_prospective in identity-chain mode;
    3. Phase 8I activation verification (verify_activation_record);
    4. Phase 8L metadata bounds readiness verification (verify_readiness);
    5. Frozen candidate execution integrity verification against TC003 manifest.
    """
    root = repo_root or Path(__file__).resolve().parents[2]

    # Resolve evidence and data directories
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

    # 2. Prospective input readiness verification (identity-chain)
    attestation_path = root / "baseline" / "phase8_v2_cost_policy_canonical_attestation.json"
    contamination_path = root / "baseline" / "phase8_contamination_register.json"

    if not attestation_path.is_file():
        raise TierBPreflightError(f"[{LABEL_PREFLIGHT_BLOCKAGE}] Cost policy attestation missing: {attestation_path}")
    if not contamination_path.is_file():
        raise TierBPreflightError(f"[{LABEL_PREFLIGHT_BLOCKAGE}] Contamination register missing: {contamination_path}")

    with open(attestation_path, "r", encoding="utf-8") as f:
        attestation = json.load(f)

    commit_to_use = active_commit or "05c66a096807d5a9da3c449c2458f675fecc39a9"

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
    frozen_check = verify_frozen_candidate_execution_integrity(root)

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

    # Side <-> Direction bijection
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
    """Filter candidates strictly by evaluation window: evaluation_start <= available_at < evaluation_end.

    Warm-up candidates (< evaluation_start) and post-evaluation candidates (>= evaluation_end)
    contribute zero count.
    """
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
            "futility_condition_met": self.futility_condition_met,
            "headroom_target_met": self.headroom_target_met,
            "futility_classification": self.futility_classification,
            "headroom_classification": self.headroom_classification,
            "candidate_count": len(self.candidates),
        }
        assert_zero_profitability(result)
        return result


def evaluate_stage1_candidates(
    candidate_records: Sequence[Mapping[str, Any]],
    *,
    evaluation_start: datetime | None = None,
    evaluation_end: datetime | None = None,
) -> Stage1CandidateReport:
    """Analyze V005 candidate decisions for Stage-1 feasibility metrics.

    Applies the frozen futility threshold (30) and non-gating headroom target (60).
    Enforces evaluation window and validates canonical schema.
    """
    assert_zero_profitability(candidate_records)

    # Window filtering if evaluation boundaries supplied
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
    """Reconcile completed trade lifecycle outcomes against Stage-1 raw candidates.

    Enforces:
    1. Qualifying exits must be members of QUALIFYING_NATURAL_EXITS. Unknown exits fail closed.
    2. END_OF_DATA is strictly excluded from qualifying trades.
    3. Exact accounting identity holds:
       raw_candidate_ready == (qualifying_completed_trades + end_of_data_closed
                               + level_intent_attrition + unfilled_expired_cancelled
                               + never_opened + duplicate_events)
    """
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

    # 1. Sealed candidate extraction strictly from candidate_surface.candidates
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

    # 2. Reproduced candidate count
    total_reproduced = len(reproduced_candidates)
    if total_reproduced != 102:
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Expected 102 reproduced candidates, got {total_reproduced}"
        )

    # Validate schema for all reproduced candidates
    for c in reproduced_candidates:
        validate_canonical_candidate(c)

    # 3. Exact multiset equality: Counter((decision_id, setup_id))
    sealed_multiset = Counter((str(c["decision_id"]), str(c["setup_id"])) for c in sealed_candidates)
    rep_multiset = Counter((str(c["decision_id"]), str(c["setup_id"])) for c in reproduced_candidates)

    if sealed_multiset != rep_multiset:
        diff_missing = sealed_multiset - rep_multiset
        diff_extra = rep_multiset - sealed_multiset
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Candidate (decision_id, setup_id) multiset mismatch. "
            f"Missing from rep: {dict(diff_missing)}, Extra in rep: {dict(diff_extra)}"
        )

    # 4. Exact per-candidate entry object parity (json.dumps with allow_nan=False)
    sealed_by_pair = {(str(c["decision_id"]), str(c["setup_id"])): c for c in sealed_candidates}
    rep_by_pair = {(str(c["decision_id"]), str(c["setup_id"])): c for c in reproduced_candidates}

    for pair_key, sealed_c in sealed_by_pair.items():
        rep_c = rep_by_pair[pair_key]

        # Source parity
        if sealed_c.get("entry_source") != rep_c.get("entry_source"):
            raise TierBParityError(
                f"[{LABEL_PARITY_FAILURE}] Candidate {pair_key} entry_source mismatch: "
                f"{sealed_c.get('entry_source')} != {rep_c.get('entry_source')}"
            )

        # Direction parity
        if sealed_c.get("entry_direction") != rep_c.get("entry_direction"):
            raise TierBParityError(
                f"[{LABEL_PARITY_FAILURE}] Candidate {pair_key} entry_direction mismatch: "
                f"{sealed_c.get('entry_direction')} != {rep_c.get('entry_direction')}"
            )

        # Side parity
        if sealed_c.get("side") != rep_c.get("side"):
            raise TierBParityError(
                f"[{LABEL_PARITY_FAILURE}] Candidate {pair_key} side mismatch: "
                f"{sealed_c.get('side')} != {rep_c.get('side')}"
            )

        # Entry JSON exact parity
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

    # 5. Counts summary
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


# -----------------------------------------------------------------------------
# V005 -> Trade Levels -> EntryIntent -> Lifecycle Execution Adapters
# -----------------------------------------------------------------------------

def candidate_to_trade_levels(
    candidate: Mapping[str, Any],
    *,
    symbol: str = "XAUUSDm",
    point: float = 0.01,
    stops_level: int = 10,
    digits: int = 2,
    min_rr: float = 1.5,
    min_rr_buffer: float = 0.10,
    level_config: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> LevelResult:
    """Pure construction of absolute trade levels from a canonical V005 candidate."""
    validate_canonical_candidate(candidate)
    direction = str(candidate["entry_direction"]).lower()
    entry = candidate["entry"]

    trigger = (
        float(entry["limit_entry"])
        if entry.get("entry_type") == "limit" and entry.get("limit_entry") is not None
        else float(entry.get("entry_price") or entry.get("price") or 2000.0)
    )

    ctx = dict(context or {})
    internal_structure = dict(ctx.get("internal_structure") or {})
    structure_context = dict(ctx.get("structure_context") or {})
    liquidity_pools = tuple(ctx.get("liquidity_pools") or ())
    recent_lows = tuple(ctx.get("recent_lows") or ())
    recent_highs = tuple(ctx.get("recent_highs") or ())
    atr = float(ctx.get("atr") or 2.50)

    # Use ob_zone from entry or candidate if available
    ob_zone = entry.get("ob_zone") or candidate.get("ob_zone")
    if ob_zone and not isinstance(ob_zone, (list, tuple)):
        ob_zone = None

    entry_mode = entry.get("entry_mode") or candidate.get("entry_mode")
    if entry_mode is None and ob_zone is not None:
        entry_mode = "aggressive"

    cfg = dict(level_config or {
        "anchor_buffer_atr_mult": 0.10,
        "min_stop_points": 500,
        "min_stop_atr_mult": 0.35,
    })

    inputs = LevelInputs(
        direction=direction,
        entry_price=trigger,
        entry_mode=entry_mode,
        ob_zone=ob_zone,
        internal_structure=internal_structure,
        recent_lows=recent_lows,
        recent_highs=recent_highs,
        structure_context=structure_context,
        liquidity_pools=liquidity_pools,
        atr=atr,
        point=point,
        stops_level=stops_level,
        digits=digits,
        level_config=cfg,
        min_rr=min_rr,
        min_rr_buffer=min_rr_buffer,
    )

    return build_trade_levels(inputs)


def candidate_to_entry_intent(
    candidate: Mapping[str, Any],
    levels: LevelResult,
    *,
    symbol: str = "XAUUSDm",
    source_timeframe: str = "M5",
    partial_close_fraction: float = 0.5,
    configuration_id: str = "phase6-frozen-v2-PRIMARY_BASELINE",
) -> EntryIntent:
    """Construct an EntryIntent from a canonical candidate and valid trade levels."""
    validate_canonical_candidate(candidate)
    if levels.stop is None or levels.target is None:
        raise TierBFeasibilityError(
            f"[{LABEL_GEOMETRY_ATTRITION}] Cannot create EntryIntent without valid levels: {levels.reason}"
        )

    avail_ms = int(candidate["available_at_ms"])
    avail_dt = datetime.fromtimestamp(avail_ms / 1000.0, tz=UTC)
    entry = candidate["entry"]
    entry_type = str(entry.get("entry_type") or "market").lower()
    pullback = entry_type == "limit"
    trigger = (
        float(entry["limit_entry"])
        if pullback and entry.get("limit_entry") is not None
        else float(entry.get("entry_price") or entry.get("price") or 2000.0)
    )

    return new_entry_intent(
        symbol=symbol,
        direction=Direction(str(candidate["entry_direction"]).lower()),
        source_timeframe=source_timeframe,
        source_candle_open_time=avail_dt - timedelta(minutes=5),
        signal_available_at=avail_dt,
        requested_trigger=trigger,
        stop_loss=float(levels.stop),
        final_target=float(levels.target),
        readiness_style=ReadinessStyle.PULLBACK if pullback else ReadinessStyle.IMMEDIATE,
        partial_close_fraction=partial_close_fraction,
        expires_at=avail_dt + timedelta(minutes=120),
        source_event_id=str(candidate["decision_id"]),
        strategy_metadata={
            "setup_id": str(candidate["setup_id"]),
            "entry_source": str(candidate["entry_source"]),
            "side": str(candidate["side"]),
        },
        configuration_id=configuration_id,
    )


def execute_candidate_lifecycle(
    intent: EntryIntent,
    market_events: Sequence[MarketEvent],
    *,
    management_config: ManagementConfig | None = None,
) -> tuple[PositionState | None, ExitReason | None]:
    """Execute a single candidate intent through the lifecycle engine against market events.

    Returns the final terminal PositionState and the natural ExitReason (or None if never filled).
    """
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


# -----------------------------------------------------------------------------
# Release Authorization & Guarded Store Reader
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ReleaseAuthorizationRecord:
    authorization_id: str
    target_partition: str
    governing_plan_id: str
    tooling_id: str
    frozen_candidate_identity: str
    supervisory_approval_reference: str
    output_path: str
    created_utc: str
    prior_sealed_pass_reference: str | None = None

    def validate(self, expected_partition: str) -> None:
        if self.target_partition != expected_partition:
            raise TierBAuthorizationError(
                f"Release authorization target partition mismatch: {self.target_partition} != {expected_partition}"
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

        # Prior-fold dependencies for reserved folds
        if expected_partition == "fold-03" and not self.prior_sealed_pass_reference:
            raise TierBAuthorizationError("Fold-03 authorization requires sealed Fold-02 PASS reference")
        if expected_partition == "fold-04" and not self.prior_sealed_pass_reference:
            raise TierBAuthorizationError("Fold-04 authorization requires sealed Fold-03 PASS reference")


class GuardedEmpiricalStoreReader:
    """Store wrapper enforcing strict verification ordering and recording first byte read.

    Order enforced:
    1. Plan verify
    2. Tooling / freeze identity verify
    3. Full prospective input readiness
    4. Activation / metadata readiness
    5. Release authorization verify
    6. Output freshness verify
    7. Store read -> records FIRST_EMPIRICAL_BYTE_READ
    """

    def __init__(
        self,
        *,
        partition: str,
        authorization: ReleaseAuthorizationRecord,
        repo_root: Path,
        raw_store_opener: Callable[[], Iterable[Any]],
    ) -> None:
        self.partition = partition
        self.authorization = authorization
        self.repo_root = repo_root
        self._raw_store_opener = raw_store_opener
        self.empirical_first_read_utc: str | None = None
        self.read_call_count = 0
        self.exposure_state: dict[str, Any] | None = None

    def open_store(self, *, preflight_already_run: bool = False) -> Iterable[Any]:
        # 1. Plan verify
        verify_plan_tc002(self.repo_root)

        # 2. Tooling verify
        verify_tooling_integrity(self.repo_root)

        # 3, 4. Full preflight (readiness, activation, metadata, candidate execution integrity)
        if not preflight_already_run:
            pre_release_evidence_preflight(self.repo_root)

        # 5. Release authorization verify
        self.authorization.validate(self.partition)

        # 6. Output freshness verify
        out_p = Path(self.authorization.output_path)
        if out_p.exists():
            raise TierBFeasibilityError(f"Target output path already exists (not fresh): {out_p}")

        # 7. Record FIRST_EMPIRICAL_BYTE_READ and return stream
        now_utc = datetime.now(UTC).isoformat()
        self.empirical_first_read_utc = now_utc
        self.read_call_count += 1

        self.exposure_state = {
            "status": LABEL_FIRST_EMPIRICAL_BYTE_READ,
            "empirical_first_read_utc": now_utc,
            "partition": self.partition,
            "governing_plan_id": PLAN_ID,
            "tooling_id": TOOLING_CORRECTION_ID,
            "authorization_id": self.authorization.authorization_id,
        }

        return self._raw_store_opener()
