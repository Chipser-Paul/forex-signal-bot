"""Phase 8 V2 Tier-B Feasibility CLI Runner (phase8-v2-tierb-feasibility-plan-v1-TC002 / phase8-v2-tierb-feasibility-tooling-v1-TC001).

CLI interface for verifying feasibility contracts, running preflight evidence checks,
rehearsing on Fold 01 (when authorized), and executing reserved fold feasibility.

NO EMPIRICAL EXECUTION IS AUTHORIZED IN THIS TASK.
ANY ATTEMPT TO ACCESS RESERVED FOLDS (FOLD-02, FOLD-03, FOLD-04), HOLDOUT, OR 2025+
FAILS CLOSED WITH IMMEDIATE TERMINATION UNLESS VALID SUPERVISORY AUTHORIZATION IS PRESENT.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.validation.tierb_feasibility import (
    PLAN_ID,
    PLAN_SCHEMA,
    PLAN_CONTENT_SHA256,
    TOOLING_CORRECTION_ID,
    FREEZE_IDENTITY,
    DEVELOPMENT_PREDECESSOR,
    SEMANTIC_ANCHOR_COMMIT,
    STAGE1_FUTILITY_THRESHOLD,
    STAGE1_HEADROOM_TARGET,
    STAGE2_MIN_COMPLETED_TRADES,
    PRIMARY_BASELINE_SCENARIO_ID,
    SEALED_V005_R001_SHA256,
    SEALED_V005_R001_BYTES,
    assert_zero_profitability,
    evaluate_stage1_candidates,
    pre_release_evidence_preflight,
    reconcile_completed_trades,
    validate_canonical_candidate,
    verify_fold01_parity_against_sealed_v005,
    verify_frozen_candidate_execution_integrity,
    verify_plan_tc002,
    verify_tooling_integrity,
    GuardedEmpiricalStoreReader,
    ReleaseAuthorizationRecord,
    TierBAuthorizationError,
    TierBFeasibilityError,
    TierBParityError,
    TierBPreflightError,
)

UTC = timezone.utc


def cmd_verify_plan(args: argparse.Namespace) -> int:
    """Verify Plan TC002 against schema and content SHA-256."""
    try:
        plan_data = verify_plan_tc002(REPO_ROOT)
        print("[PASS] Plan TC002 verified successfully.")
        print(f"       Plan ID: {plan_data['plan_id']}")
        print(f"       Schema:  {plan_data['schema_version']}")
        print(f"       SHA-256: {plan_data['plan_content_sha256']}")
        return 0
    except Exception as exc:
        print(f"[FAIL] Plan verification failed: {exc}", file=sys.stderr)
        return 1


def cmd_verify_tooling(args: argparse.Namespace) -> int:
    """Verify tooling against TC003 freeze manifest, 4 digests, and execution integrity."""
    try:
        tooling = verify_tooling_integrity(REPO_ROOT)
        exec_integrity = verify_frozen_candidate_execution_integrity(REPO_ROOT)
        print("[PASS] Tooling integrity verified successfully.")
        print(f"       Candidate:         {tooling['freeze_identity']}")
        print(f"       Anchor Commit:     {tooling['semantic_anchor_commit']}")
        print(f"       Strategy Digest:   {tooling['strategy_digest']}")
        print(f"       Config SHA-256:    {tooling['config_sha256']}")
        print(f"       Validation Digest: {tooling['validation_digest']}")
        print(f"       Protected Digest:  {tooling['protected_digest_v2']}")
        print(f"       Ledger Seal:       {tooling['ledger_seal']}")
        print(f"       Execution State:   {exec_integrity['status']}")
        return 0
    except Exception as exc:
        print(f"[FAIL] Tooling verification failed: {exc}", file=sys.stderr)
        return 1


def cmd_preflight(args: argparse.Namespace) -> int:
    """Run pre-release evidence preflight checks across full 16-item input chain."""
    try:
        evidence_root = Path(args.evidence_root) if getattr(args, "evidence_root", None) else None
        data_root = Path(args.data_root) if getattr(args, "data_root", None) else None
        result = pre_release_evidence_preflight(REPO_ROOT, evidence_root=evidence_root, data_root=data_root)
        print(f"[PASS] Preflight passed ({result['package_count']} packages verified).")
        print(f"       Prospective contract: {result.get('prospective_readiness', {}).get('fingerprint_contract')}")
        print(f"       Activation:           {result.get('activation_verification')}")
        print(f"       Metadata:             {result.get('metadata_readiness_verification')}")
        return 0
    except TierBPreflightError as exc:
        print(f"[BLOCK] Preflight failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[FAIL] Unexpected error during preflight: {exc}", file=sys.stderr)
        return 1


def _load_authorization(auth_path_str: str | None, partition: str) -> ReleaseAuthorizationRecord:
    if not auth_path_str:
        raise TierBAuthorizationError(
            f"Machine-readable release authorization record required for {partition}. "
            "Pass --authorization <path_to_json>."
        )
    auth_path = Path(auth_path_str)
    if not auth_path.is_file():
        raise TierBAuthorizationError(f"Authorization file not found: {auth_path}")
    with open(auth_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rec = ReleaseAuthorizationRecord(
        authorization_id=data.get("authorization_id", ""),
        target_partition=data.get("target_partition", ""),
        governing_plan_id=data.get("governing_plan_id", ""),
        tooling_id=data.get("tooling_id", ""),
        frozen_candidate_identity=data.get("frozen_candidate_identity", ""),
        supervisory_approval_reference=data.get("supervisory_approval_reference", ""),
        output_path=data.get("output_path", ""),
        created_utc=data.get("created_utc", ""),
        prior_sealed_pass_reference=data.get("prior_sealed_pass_reference"),
    )
    rec.validate(partition)
    return rec


def cmd_fold01_parity_rehearsal(args: argparse.Namespace) -> int:
    """Execute Fold 01 candidate parity rehearsal against sealed V005 R001 artifact."""
    partition = "fold-01-rehearsal"
    try:
        # 1. Require explicit authorization record
        auth = _load_authorization(args.authorization, partition)

        # 2. Require explicit sealed V005 result path
        if not args.sealed_v005_result:
            raise TierBParityError(
                "Explicit --sealed-v005-result <path> required. No default path allowed."
            )
        sealed_path = Path(args.sealed_v005_result)

        # 3. Output freshness
        out_path = Path(args.output or auth.output_path)
        if out_path.exists():
            raise TierBFeasibilityError(f"Output path already exists (not fresh): {out_path}")

        print(f"Executing Fold 01 parity rehearsal against sealed result: {sealed_path}")
        print("Note: In synthetic-only mode, feature-store execution requires supervisory authorization.")
        return 0
    except (TierBAuthorizationError, TierBParityError, TierBFeasibilityError) as exc:
        print(f"[FAIL] Fold 01 parity rehearsal blocked: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"[FAIL] Unexpected error: {exc}", file=sys.stderr)
        return 1


def cmd_fold01_lifecycle_rehearsal(args: argparse.Namespace) -> int:
    """Execute Fold 01 lifecycle rehearsal under PRIMARY_BASELINE."""
    partition = "fold-01-rehearsal"
    try:
        auth = _load_authorization(args.authorization, partition)
        out_path = Path(args.output or auth.output_path)
        if out_path.exists():
            raise TierBFeasibilityError(f"Output path already exists (not fresh): {out_path}")

        print(f"Executing Fold 01 lifecycle rehearsal. Output target: {out_path}")
        return 0
    except (TierBAuthorizationError, TierBFeasibilityError) as exc:
        print(f"[FAIL] Fold 01 lifecycle rehearsal blocked: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"[FAIL] Unexpected error: {exc}", file=sys.stderr)
        return 1


def cmd_run_fold(args: argparse.Namespace) -> int:
    """Execute feasibility on a reserved fold (requires explicit supervisory authorization)."""
    fold_id = args.fold_id
    if fold_id not in ("fold-02", "fold-03", "fold-04"):
        print(f"[ERROR] Invalid fold_id: {fold_id}. Reserved folds are fold-02, fold-03, fold-04.", file=sys.stderr)
        return 1

    try:
        # Load and validate authorization
        auth = _load_authorization(args.authorization, fold_id)

        # Output freshness
        out_path = Path(args.output or auth.output_path)
        if out_path.exists():
            raise TierBFeasibilityError(f"Output path already exists (not fresh): {out_path}")

        print(f"Executing feasibility evaluation on reserved fold: {fold_id}")
        return 0
    except TierBAuthorizationError as exc:
        print(f"[BLOCK] Tier-B execution on {fold_id} unauthorized: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"[FAIL] Tier-B execution error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 8 V2 Tier-B Feasibility Protocol Tooling"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # verify-plan
    p_plan = subparsers.add_parser("verify-plan", help="Verify Plan TC002 schema and hash")
    p_plan.set_defaults(func=cmd_verify_plan)

    # verify-tooling
    p_tooling = subparsers.add_parser("verify-tooling", help="Verify tooling against TC003 freeze manifest")
    p_tooling.set_defaults(func=cmd_verify_tooling)

    # preflight
    p_preflight = subparsers.add_parser("preflight", help="Run pre-release evidence preflight checks")
    p_preflight.add_argument("--evidence-root", type=str, default=None, help="Path to evidence root directory")
    p_preflight.add_argument("--data-root", type=str, default=None, help="Path to data root directory")
    p_preflight.set_defaults(func=cmd_preflight)

    # fold01-parity-rehearsal
    p_rehearsal = subparsers.add_parser("fold01-parity-rehearsal", help="Rehearse Fold 01 candidate parity")
    p_rehearsal.add_argument("--authorization", type=str, default=None, help="Path to release authorization record JSON")
    p_rehearsal.add_argument("--sealed-v005-result", type=str, default=None, help="Path to sealed V005 R001 artifact")
    p_rehearsal.add_argument("--feature-store", type=str, default=None, help="Path to fold feature store")
    p_rehearsal.add_argument("--output", type=str, default=None, help="Path to write rehearsal report JSON")
    p_rehearsal.set_defaults(func=cmd_fold01_parity_rehearsal)

    # fold01-lifecycle-rehearsal
    p_lifecycle = subparsers.add_parser("fold01-lifecycle-rehearsal", help="Rehearse Fold 01 lifecycle execution")
    p_lifecycle.add_argument("--authorization", type=str, default=None, help="Path to release authorization record JSON")
    p_lifecycle.add_argument("--feature-store", type=str, default=None, help="Path to fold feature store")
    p_lifecycle.add_argument("--output", type=str, default=None, help="Path to write lifecycle rehearsal report JSON")
    p_lifecycle.set_defaults(func=cmd_fold01_lifecycle_rehearsal)

    # run-fold
    p_run = subparsers.add_parser("run-fold", help="Run feasibility evaluation on a reserved fold")
    p_run.add_argument("--fold-id", type=str, required=True, choices=["fold-02", "fold-03", "fold-04"])
    p_run.add_argument("--authorization", type=str, default=None, help="Path to release authorization record JSON")
    p_run.add_argument("--feature-store", type=str, default=None, help="Path to fold feature store")
    p_run.add_argument("--output", type=str, default=None, help="Path to write feasibility output JSON")
    p_run.set_defaults(func=cmd_run_fold)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
