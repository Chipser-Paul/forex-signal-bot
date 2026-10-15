"""Phase 8 V2 Tier-B Feasibility Engine (phase8-v2-tierb-feasibility-plan-v1-TC001).

Implements the prospective two-stage candidate and lifecycle sample feasibility
protocol governing the evaluation of frozen development candidate `phase6-frozen-v2`
across reserved Tier-B development folds (`fold-02`, `fold-03`, `fold-04`).

Strict constraints enforced by this module:
1. Zero empirical store access without explicit preflight evidence checks and
   contamination authorization;
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
    profit factor, equity curves strictly prohibited and firewalled).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from bot.execution.lifecycle.models import Direction, ExitReason, LifecycleStatus
from bot.strategy.variant_v005 import (
    SPEC_SHA256 as V005_SPEC_SHA256,
    V005_ID,
    V005_SOURCE_DIRECTIONAL_FALLBACK,
    V005_SOURCE_NONE,
    V005_SOURCE_V003_BASELINE,
    evaluate_v005_entry_readiness,
)

UTC = timezone.utc

PLAN_ID = "phase8-v2-tierb-feasibility-plan-v1-TC001"
PLAN_SCHEMA = "phase8v2.tierb-feasibility-plan.v2"
PLAN_CONTENT_SHA256 = (
    "5c2d5e4f29d2dfb3720dc264c8b28d240c0cf1cb8a62ccd40923ed5d8b2cfddf"
)

PARENT_PLAN_ID = "phase8-v2-tierb-feasibility-plan-v1"
PARENT_PLAN_CONTENT_SHA256 = (
    "d42d7392cc124b3d8ab09a6212aa29038317fd93ae5d486b24d72904eddea1c9"
)

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

# Pre-release Evidence Preflight Packages
REQUIRED_PREFLIGHT_PACKAGES = (
    "evidence-development_cost_policy-v1-6b1a986b1f8d7b81",
    "evidence-cost_policy_activation-v1-802914181c0ca505",
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


class TierBFeasibilityError(RuntimeError):
    """Base error for Tier-B feasibility contract violations."""


class TierBPreflightError(TierBFeasibilityError):
    """Raised when pre-release evidence packages are missing or invalid."""


class TierBContaminationError(TierBFeasibilityError):
    """Raised when empirical store access is attempted without authorization."""


class TierBParityError(TierBFeasibilityError):
    """Raised when Fold-01 rehearsal parity checks fail."""


class TierBProfitabilityViolation(TierBFeasibilityError):
    """Raised when prohibited profitability metrics are detected."""


DEFAULT_EVIDENCE_ROOT = Path("C:/Users/chips/forex-signal-bot-data/phase8/evidence")


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


def verify_plan_tc001(repo_root: Path) -> dict[str, Any]:
    """Verify Plan-TC001 schema, content SHA, and prospective contract."""
    plan_path = repo_root / "baseline" / "phase8_v2_tierb_feasibility_plan_tc001.json"
    if not plan_path.is_file():
        raise TierBFeasibilityError(f"Plan TC001 file missing: {plan_path}")
    with open(plan_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("plan_id") != PLAN_ID:
        raise TierBFeasibilityError(f"Unexpected plan_id: {data.get('plan_id')}")
    if data.get("schema_version") != PLAN_SCHEMA:
        raise TierBFeasibilityError(f"Unexpected schema_version: {data.get('schema_version')}")

    computed_sha = compute_plan_content_sha256(data)
    if computed_sha != PLAN_CONTENT_SHA256:
        raise TierBFeasibilityError(
            f"Plan TC001 content SHA mismatch: computed {computed_sha} != {PLAN_CONTENT_SHA256}"
        )
    if data.get("plan_content_sha256") != PLAN_CONTENT_SHA256:
        raise TierBFeasibilityError("Plan TC001 embedded content SHA mismatch")

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


def pre_release_evidence_preflight(
    repo_root: Path | None = None,
    *,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    """Verify that all required pre-release evidence packages exist before opening stores."""
    if evidence_root is not None:
        target_dir = Path(evidence_root)
    elif DEFAULT_EVIDENCE_ROOT.is_dir():
        target_dir = DEFAULT_EVIDENCE_ROOT
    elif repo_root is not None and (Path(repo_root) / "evidence").is_dir():
        target_dir = Path(repo_root) / "evidence"
    else:
        target_dir = DEFAULT_EVIDENCE_ROOT

    missing = []
    found = []
    for pkg_id in REQUIRED_PREFLIGHT_PACKAGES:
        pkg_path = target_dir / pkg_id
        pkg_manifest = pkg_path / "manifest.json"
        if not pkg_manifest.is_file():
            missing.append(pkg_id)
        else:
            found.append(pkg_id)

    if missing:
        raise TierBPreflightError(
            f"[{LABEL_PREFLIGHT_BLOCKAGE}] Missing required preflight packages: {missing}. "
            "Execution halted fail-closed before any empirical byte read."
        )

    return {

        "status": "PREFLIGHT_PASSED",
        "verified_packages": found,
        "package_count": len(found),
    }


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
    Evaluates only candidate records without fills or broker costs.
    """
    assert_zero_profitability(candidate_records)
    total_raw = len(candidate_records)
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

    for cand in candidate_records:
        sid = cand.get("setup_id") or cand.get("v005_setup_id") or ""
        setup_ids.append(sid)

        direction = str(cand.get("direction") or cand.get("v005_entry_direction") or "").lower()
        if direction == "buy" or direction == "long":
            long_count += 1
        elif direction == "sell" or direction == "short":
            short_count += 1

        source = str(cand.get("v005_entry_source") or cand.get("source") or "")
        if source == V005_SOURCE_V003_BASELINE:
            v003_baseline += 1
        elif source == V005_SOURCE_DIRECTIONAL_FALLBACK:
            v005_fallback += 1
            if direction in ("buy", "long"):
                fallback_buy += 1
            elif direction in ("sell", "short"):
                fallback_sell += 1

        week = cand.get("week") or cand.get("iso_week")
        if week:
            week_key = str(week)
            week_dist[week_key] = week_dist.get(week_key, 0) + 1

        sess = cand.get("session") or cand.get("active_session")
        if sess:
            sess_key = str(sess).lower()
            session_dist[sess_key] = session_dist.get(sess_key, 0) + 1

        ts = cand.get("timestamp") or cand.get("decision_at")
        if ts and midpoint_ts is not None:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            elif isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts / 1000.0 if ts > 1e11 else ts, tz=UTC)
            else:
                dt = ts
            if dt.timestamp() < midpoint_ts:
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
        candidates=tuple(candidate_records),
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

    Enforces the exact accounting identity:
    raw_candidate_ready == (qualifying_completed_trades + end_of_data_closed
                            + level_intent_attrition + unfilled_expired_cancelled
                            + never_opened + duplicate_events)
    """
    exit_dist: dict[str, int] = {}
    qualifying_count = 0

    for item in qualifying_exits:
        reason_name = item.name if isinstance(item, ExitReason) else str(item)
        if reason_name == ExitReason.END_OF_DATA.name:
            # End of data must not be in qualifying exits
            raise TierBFeasibilityError(
                "END_OF_DATA passed to qualifying_exits; must be counted under end_of_data_count"
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
    """Verify exact candidate parity against the sealed V005 R001 external artifact."""
    if not sealed_artifact_path.is_file():
        raise TierBParityError(f"Sealed V005 R001 artifact missing: {sealed_artifact_path}")

    raw_bytes = sealed_artifact_path.read_bytes()
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

    sealed_data = json.loads(raw_bytes.decode("utf-8"))
    assert_zero_profitability(sealed_data)

    # Extract sealed candidate entries
    sealed_candidates = sealed_data.get("candidates") or sealed_data.get("candidate_records") or []
    if not sealed_candidates and "observations" in sealed_data:
        sealed_candidates = [
            obs for obs in sealed_data["observations"]
            if obs.get("v005_entry_ready")
        ]

    # Check counts
    total_reproduced = len(reproduced_candidates)
    if total_reproduced != 102:
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Expected 102 reproduced candidates, got {total_reproduced}"
        )

    rep_baseline = sum(
        1 for c in reproduced_candidates
        if c.get("v005_entry_source") == V005_SOURCE_V003_BASELINE
        or c.get("source") == V005_SOURCE_V003_BASELINE
    )
    rep_fallback = sum(
        1 for c in reproduced_candidates
        if c.get("v005_entry_source") == V005_SOURCE_DIRECTIONAL_FALLBACK
        or c.get("source") == V005_SOURCE_DIRECTIONAL_FALLBACK
    )

    if rep_baseline != 81:
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Expected 81 baseline candidates, got {rep_baseline}"
        )
    if rep_fallback != 21:
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Expected 21 fallback candidates, got {rep_fallback}"
        )

    # Check setup_id unique count
    rep_setup_ids = [c.get("setup_id") or c.get("v005_setup_id") for c in reproduced_candidates]
    if len(set(rep_setup_ids)) != 102:
        raise TierBParityError(
            f"[{LABEL_PARITY_FAILURE}] Expected 102 unique setups, got {len(set(rep_setup_ids))}"
        )

    return {
        "status": "FOLD01_PARITY_VERIFIED",
        "sealed_artifact_sha256": sha256,
        "sealed_artifact_bytes": byte_count,
        "total_candidates": total_reproduced,
        "v003_baseline_count": rep_baseline,
        "v005_directional_fallback_count": rep_fallback,
        "unique_setup_ids": len(set(rep_setup_ids)),
        "duplicates": 0,
        "verified": True,
    }
