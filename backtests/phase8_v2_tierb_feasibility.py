"""Phase 8 V2 Tier-B Feasibility CLI Runner (phase8-v2-tierb-feasibility-plan-v1-TC001).

CLI interface for verifying feasibility contracts, running preflight evidence checks,
rehearsing on Fold 01 (when authorized), and executing reserved fold feasibility.

NO EMPIRICAL EXECUTION IS AUTHORIZED IN THIS TASK.
ANY ATTEMPT TO ACCESS RESERVED FOLDS (FOLD-02, FOLD-03, FOLD-04), HOLDOUT, OR 2025+
FAILS CLOSED WITH IMMEDIATE TERMINATION.
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
    FREEZE_IDENTITY,
    DEVELOPMENT_PREDECESSOR,
    SEMANTIC_ANCHOR_COMMIT,
    STAGE1_FUTILITY_THRESHOLD,
    STAGE1_HEADROOM_TARGET,
    STAGE2_MIN_COMPLETED_TRADES,
    PRIMARY_BASELINE_SCENARIO_ID,
    assert_zero_profitability,
    evaluate_stage1_candidates,
    pre_release_evidence_preflight,
    reconcile_completed_trades,
    verify_fold01_parity_against_sealed_v005,
    verify_plan_tc001,
    verify_tooling_integrity,
    TierBFeasibilityError,
    TierBPreflightError,
)

UTC = timezone.utc


def cmd_verify_plan(args: argparse.Namespace) -> int:
    """Verify Plan TC001 against schema and content SHA-256."""
    try:
        plan_data = verify_plan_tc001(REPO_ROOT)
        print(f"[PASS] Plan TC001 verified successfully.")
        print(f"       Plan ID: {plan_data['plan_id']}")
        print(f"       Schema:  {plan_data['schema_version']}")
        print(f"       SHA-256: {plan_data['plan_content_sha256']}")
        return 0
    except Exception as exc:
        print(f"[FAIL] Plan verification failed: {exc}", file=sys.stderr)
        return 1


def cmd_verify_tooling(args: argparse.Namespace) -> int:
    """Verify tooling against TC003 freeze manifest and 4 digests."""
    try:
        tooling = verify_tooling_integrity(REPO_ROOT)
        print(f"[PASS] Tooling integrity verified successfully.")
        print(f"       Candidate:         {tooling['freeze_identity']}")
        print(f"       Anchor Commit:     {tooling['semantic_anchor_commit']}")
        print(f"       Strategy Digest:   {tooling['strategy_digest']}")
        print(f"       Config SHA-256:    {tooling['config_sha256']}")
        print(f"       Validation Digest: {tooling['validation_digest']}")
        print(f"       Protected Digest:  {tooling['protected_digest_v2']}")
        print(f"       Ledger Seal:       {tooling['ledger_seal']}")
        return 0
    except Exception as exc:
        print(f"[FAIL] Tooling verification failed: {exc}", file=sys.stderr)
        return 1


def cmd_preflight(args: argparse.Namespace) -> int:
    """Run pre-release evidence preflight checks."""
    try:
        result = pre_release_evidence_preflight(REPO_ROOT)
        print(f"[PASS] Preflight passed ({result['package_count']} packages verified).")
        return 0
    except TierBPreflightError as exc:
        print(f"[BLOCK] Preflight failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[FAIL] Unexpected error during preflight: {exc}", file=sys.stderr)
        return 1


def cmd_fold01_parity_rehearsal(args: argparse.Namespace) -> int:
    """Rehearse Fold 01 candidate parity against sealed V005 R001 artifact."""
    sealed_path = REPO_ROOT / (
        args.sealed_artifact
        or "baseline/phase6_development_v2_v005_r001_sealed.json"
    )
    if not sealed_path.is_file():
        # Check standard location in baseline or results
        alt_path = REPO_ROOT / "results" / "phase6-development-v2-V005-R001.json"
        if alt_path.is_file():
            sealed_path = alt_path

    print(f"Executing Fold 01 parity rehearsal against: {sealed_path}")
    print("[HALT] Fold 01 rehearsal requires explicit supervisory execution command.")
    return 3


def cmd_run_fold(args: argparse.Namespace) -> int:
    """Execute feasibility on a reserved fold (requires supervisory authorization)."""
    fold_id = args.fold_id
    if fold_id not in ("fold-02", "fold-03", "fold-04"):
        print(f"[ERROR] Invalid fold_id: {fold_id}. Reserved folds are fold-02, fold-03, fold-04.", file=sys.stderr)
        return 1

    print(f"[BLOCK] Tier-B execution on {fold_id} is UNAUTHORIZED in this task.")
    print("        Zero empirical data access is permitted. Stopping fail-closed.")
    return 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 8 V2 Tier-B Feasibility Protocol Tooling"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # verify-plan
    p_plan = subparsers.add_parser("verify-plan", help="Verify Plan TC001 schema and hash")
    p_plan.set_defaults(func=cmd_verify_plan)

    # verify-tooling
    p_tooling = subparsers.add_parser("verify-tooling", help="Verify tooling against TC003 freeze manifest")
    p_tooling.set_defaults(func=cmd_verify_tooling)

    # preflight
    p_preflight = subparsers.add_parser("preflight", help="Run pre-release evidence preflight checks")
    p_preflight.set_defaults(func=cmd_preflight)

    # fold01-parity-rehearsal
    p_rehearsal = subparsers.add_parser("fold01-parity-rehearsal", help="Rehearse Fold 01 candidate parity")
    p_rehearsal.add_argument("--sealed-artifact", type=str, default=None, help="Path to sealed V005 R001 artifact")
    p_rehearsal.set_defaults(func=cmd_fold01_parity_rehearsal)

    # run-fold
    p_run = subparsers.add_parser("run-fold", help="Run feasibility evaluation on a reserved fold")
    p_run.add_argument("--fold-id", type=str, required=True, choices=["fold-02", "fold-03", "fold-04"])
    p_run.set_defaults(func=cmd_run_fold)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
