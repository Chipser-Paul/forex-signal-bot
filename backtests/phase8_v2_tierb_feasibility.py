"""Phase 8 V2 Tier-B Feasibility Protocol CLI (phase8-v2-tierb-feasibility-tooling-v1-TC002).

Authoritative CLI entry point for Tier-B candidate and lifecycle sample feasibility.

Enforces:
1. Pure pre-empirical execution;
2. Machine-readable release authorization;
3. Output and temp freshness;
4. Derived active Git commit matching authorized tooling commit;
5. Real V005 candidate replay;
6. PRIMARY_BASELINE HistoricalExecutionEngine lifecycle execution;
7. Prohibited profitability firewall.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from bot.backtesting.models import HistoricalQuote
from bot.validation.tierb_feasibility import (
    PLAN_ID,
    TOOLING_CORRECTION_ID,
    LABEL_STAGE1_FUTILITY,
    TierBAuthorizationError,
    TierBFeasibilityError,
    TierBParityError,
    TierBPreflightError,
    GuardedEmpiricalStoreReader,
    ReleaseAuthorizationRecord,
    assert_zero_profitability,
    atomic_publish_json,
    evaluate_stage1_candidates,
    execute_stage2_primary_baseline,
    pre_release_evidence_preflight,
    replay_v005_candidates_from_store,
    resolve_canonical_git_head,
    verify_fold01_parity_against_sealed_v005,
    verify_plan_tc002,
    verify_tooling_integrity,
)
from bot.validation.market_feature_store import load_feature_store

UTC = timezone.utc


def cmd_verify_plan(args: argparse.Namespace) -> int:
    """Verify Plan TC002 schema and content hash."""
    repo_root = Path(__file__).resolve().parents[1]
    try:
        result = verify_plan_tc002(repo_root)
        print(f"[OK] Plan TC002 verified successfully: {result.get('plan_id')}")
        print(f"     Content SHA-256: {result.get('plan_content_sha256')}")
        return 0
    except TierBFeasibilityError as exc:
        print(f"[FAIL] Plan TC002 verification failed: {exc}", file=sys.stderr)
        return 1


def cmd_verify_tooling(args: argparse.Namespace) -> int:
    """Verify tooling against TC003 freeze manifest and authoritative ledger seal."""
    repo_root = Path(__file__).resolve().parents[1]
    try:
        result = verify_tooling_integrity(repo_root)
        print(f"[OK] Tooling verified successfully against {result.get('manifest_path')}")
        print(f"     Freeze identity:    {result.get('freeze_identity')}")
        print(f"     Strategy digest:    {result.get('strategy_digest')}")
        print(f"     Config SHA-256:     {result.get('config_sha256')}")
        print(f"     Validation digest:  {result.get('validation_digest')}")
        print(f"     Protected digest:   {result.get('protected_digest_v2')}")
        print(f"     Ledger seal:        {result.get('ledger_seal')}")
        return 0
    except TierBFeasibilityError as exc:
        print(f"[FAIL] Tooling verification failed: {exc}", file=sys.stderr)
        return 1


def cmd_preflight(args: argparse.Namespace) -> int:
    """Run full pre-release evidence preflight checks with derived active commit."""
    repo_root = Path(__file__).resolve().parents[1]
    try:
        active_commit = resolve_canonical_git_head(repo_root)
        ev_root = Path(args.evidence_root) if args.evidence_root else None
        dt_root = Path(args.data_root) if args.data_root else None
        result = pre_release_evidence_preflight(
            repo_root,
            evidence_root=ev_root,
            data_root=dt_root,
            active_commit=active_commit,
        )
        print(f"[OK] Pre-release evidence preflight passed ({result.get('package_count')} packages verified)")
        print(f"     Active commit:        {active_commit}")
        print(f"     Activation:           {result.get('activation_verification')}")
        print(f"     Metadata:             {result.get('metadata_readiness_verification')}")
        return 0
    except TierBPreflightError as exc:
        print(f"[BLOCK] Preflight failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[FAIL] Unexpected error during preflight: {exc}", file=sys.stderr)
        return 1


def _load_authorization(auth_path_str: str | None, partition: str, operation: str) -> ReleaseAuthorizationRecord:
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
        authorized_operation=data.get("authorized_operation", ""),
        governing_plan_id=data.get("governing_plan_id", ""),
        tooling_id=data.get("tooling_id", ""),
        frozen_candidate_identity=data.get("frozen_candidate_identity", ""),
        supervisory_approval_reference=data.get("supervisory_approval_reference", ""),
        output_path=data.get("output_path", ""),
        created_utc=data.get("created_utc", ""),
        prior_sealed_pass_reference=data.get("prior_sealed_pass_reference"),
        prior_sealed_parity_reference=data.get("prior_sealed_parity_reference"),
        prior_sealed_lifecycle_reference=data.get("prior_sealed_lifecycle_reference"),
    )
    rec.validate(partition, expected_operation=operation)
    return rec


def _extract_quotes_from_store(store: Any) -> list[HistoricalQuote]:
    """Extract historical quotes sequence from feature store snapshots."""
    from backtests.phase8_v2_diagnostic_d001 import _snapshot_rows
    quotes: list[HistoricalQuote] = []
    seq = 0
    for snap in _snapshot_rows(store):
        seq += 1
        ts = datetime.fromtimestamp(int(snap.available_at_ms) / 1000.0, tz=UTC)
        close = float(snap.close)
        spread = 0.15
        bid = close - (spread / 2.0)
        ask = close + (spread / 2.0)
        quotes.append(
            HistoricalQuote(
                symbol="XAUUSDm",
                timestamp=ts,
                bid=bid,
                ask=ask,
                source="store-causal-snapshot",
                dataset_id="store",
                sequence_id=seq,
            )
        )
    return quotes


def cmd_fold01_parity_rehearsal(args: argparse.Namespace) -> int:
    """Execute Fold 01 candidate parity rehearsal against sealed V005 R001 artifact."""
    partition = "fold-01-rehearsal"
    operation = "FOLD01_PARITY_REHEARSAL"
    repo_root = Path(__file__).resolve().parents[1]
    try:
        auth = _load_authorization(args.authorization, partition, operation)
        if auth.tooling_id != TOOLING_CORRECTION_ID:
            raise TierBAuthorizationError(
                f"Authorization tooling ID mismatch: {auth.tooling_id} != {TOOLING_CORRECTION_ID}"
            )

        if not args.sealed_v005_result:
            raise TierBParityError(
                "Explicit --sealed-v005-result <path> required. No default path allowed."
            )
        sealed_path = Path(args.sealed_v005_result)
        if not sealed_path.is_file():
            raise TierBParityError(f"Sealed V005 result file not found: {sealed_path}")

        if not args.feature_store:
            raise TierBFeasibilityError("Explicit --feature-store <path> required.")
        store_path = Path(args.feature_store)

        out_path = Path(args.output or auth.output_path)

        active_commit = resolve_canonical_git_head(repo_root)

        # Guarded reader enters empirical boundary and loads store
        reader = GuardedEmpiricalStoreReader(
            partition=partition,
            authorization=auth,
            repo_root=repo_root,
            raw_store_opener=lambda: load_feature_store(store_path, verify_rows=True),
            expected_operation=operation,
        )
        store = reader.open_store(preflight_already_run=False, active_commit=active_commit)

        plan_data = verify_plan_tc002(repo_root)
        f01_sched = plan_data["exact_fold_schedule"]["fold-01"]
        eval_start = datetime.fromisoformat(f01_sched["evaluation"]["start"].replace("Z", "+00:00"))
        eval_end = datetime.fromisoformat(f01_sched["evaluation"]["end"].replace("Z", "+00:00"))
        warmup_start = datetime.fromisoformat(f01_sched["warmup"]["start"].replace("Z", "+00:00"))

        candidates = replay_v005_candidates_from_store(
            store, eval_start, eval_end, warmup_start=warmup_start,
        )

        clean_cands = [{k: v for k, v in c.items() if not k.startswith("_")} for c in candidates]

        parity_result = verify_fold01_parity_against_sealed_v005(clean_cands, sealed_path)

        report = {
            "protocol": "FOLD01_PARITY_REHEARSAL",
            "plan_id": PLAN_ID,
            "tooling_id": TOOLING_CORRECTION_ID,
            "classification": "CONTAMINATED_FOLD01_EMPIRICAL_TOOLING_REHEARSAL — NOT_TIER_B_EVIDENCE",
            "exposure_record": reader.exposure_record,
            "parity_result": parity_result,
            "candidates_count": len(clean_cands),
            "verified_utc": datetime.now(UTC).isoformat(),
        }

        atomic_publish_json(out_path, report)
        print(f"[OK] Fold-01 candidate parity rehearsal successful: {out_path}")
        return 0
    except (TierBAuthorizationError, TierBParityError, TierBFeasibilityError, TierBPreflightError) as exc:
        print(f"[FAIL] Fold 01 parity rehearsal blocked: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"[FAIL] Unexpected error: {exc}", file=sys.stderr)
        return 1


def cmd_fold01_lifecycle_rehearsal(args: argparse.Namespace) -> int:
    """Execute Fold 01 lifecycle rehearsal under PRIMARY_BASELINE."""
    partition = "fold-01-rehearsal"
    operation = "FOLD01_LIFECYCLE_REHEARSAL"
    repo_root = Path(__file__).resolve().parents[1]
    try:
        auth = _load_authorization(args.authorization, partition, operation)
        if auth.tooling_id != TOOLING_CORRECTION_ID:
            raise TierBAuthorizationError(
                f"Authorization tooling ID mismatch: {auth.tooling_id} != {TOOLING_CORRECTION_ID}"
            )

        if not args.feature_store:
            raise TierBFeasibilityError("Explicit --feature-store <path> required.")
        store_path = Path(args.feature_store)

        out_path = Path(args.output or auth.output_path)

        active_commit = resolve_canonical_git_head(repo_root)

        reader = GuardedEmpiricalStoreReader(
            partition=partition,
            authorization=auth,
            repo_root=repo_root,
            raw_store_opener=lambda: load_feature_store(store_path, verify_rows=True),
            expected_operation=operation,
        )
        store = reader.open_store(preflight_already_run=False, active_commit=active_commit)

        plan_data = verify_plan_tc002(repo_root)
        f01_sched = plan_data["exact_fold_schedule"]["fold-01"]
        eval_start = datetime.fromisoformat(f01_sched["evaluation"]["start"].replace("Z", "+00:00"))
        eval_end = datetime.fromisoformat(f01_sched["evaluation"]["end"].replace("Z", "+00:00"))
        warmup_start = datetime.fromisoformat(f01_sched["warmup"]["start"].replace("Z", "+00:00"))

        candidates = replay_v005_candidates_from_store(
            store, eval_start, eval_end, warmup_start=warmup_start,
        )

        quotes = _extract_quotes_from_store(store)

        accounting = execute_stage2_primary_baseline(candidates, quotes)

        report = {
            "protocol": "FOLD01_LIFECYCLE_REHEARSAL",
            "plan_id": PLAN_ID,
            "tooling_id": TOOLING_CORRECTION_ID,
            "classification": "CONTAMINATED_FOLD01_EMPIRICAL_TOOLING_REHEARSAL — NOT_TIER_B_EVIDENCE",
            "exposure_record": reader.exposure_record,
            "accounting": accounting.to_dict(),
            "verified_utc": datetime.now(UTC).isoformat(),
        }

        atomic_publish_json(out_path, report)
        print(f"[OK] Fold-01 lifecycle rehearsal successful: {out_path}")
        return 0
    except (TierBAuthorizationError, TierBFeasibilityError, TierBPreflightError) as exc:
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

    operation = "RESERVED_FOLD_FEASIBILITY"
    repo_root = Path(__file__).resolve().parents[1]
    try:
        auth = _load_authorization(args.authorization, fold_id, operation)
        if auth.tooling_id != TOOLING_CORRECTION_ID:
            raise TierBAuthorizationError(
                f"Authorization tooling ID mismatch: {auth.tooling_id} != {TOOLING_CORRECTION_ID}"
            )

        if not args.feature_store:
            raise TierBFeasibilityError("Explicit --feature-store <path> required.")
        store_path = Path(args.feature_store)

        out_path = Path(args.output or auth.output_path)

        active_commit = resolve_canonical_git_head(repo_root)

        reader = GuardedEmpiricalStoreReader(
            partition=fold_id,
            authorization=auth,
            repo_root=repo_root,
            raw_store_opener=lambda: load_feature_store(store_path, verify_rows=True),
            expected_operation=operation,
        )
        store = reader.open_store(preflight_already_run=False, active_commit=active_commit)

        plan_data = verify_plan_tc002(repo_root)
        fold_sched = plan_data["exact_fold_schedule"][fold_id]
        eval_start = datetime.fromisoformat(fold_sched["evaluation"]["start"].replace("Z", "+00:00"))
        eval_end = datetime.fromisoformat(fold_sched["evaluation"]["end"].replace("Z", "+00:00"))
        warmup_start = datetime.fromisoformat(fold_sched["warmup"]["start"].replace("Z", "+00:00"))

        candidates = replay_v005_candidates_from_store(
            store, eval_start, eval_end, warmup_start=warmup_start,
        )

        s1_report = evaluate_stage1_candidates(
            candidates, evaluation_start=eval_start, evaluation_end=eval_end,
        )

        if s1_report.futility_condition_met:
            report = {
                "fold_id": fold_id,
                "plan_id": PLAN_ID,
                "tooling_id": TOOLING_CORRECTION_ID,
                "classification": "PROSPECTIVE_RESERVED_DEVELOPMENT_FEASIBILITY — NOT_PROFITABILITY_EVIDENCE",
                "exposure_record": reader.exposure_record,
                "stage1": s1_report.to_dict(),
                "verdict": LABEL_STAGE1_FUTILITY,
                "verified_utc": datetime.now(UTC).isoformat(),
            }
        else:
            quotes = _extract_quotes_from_store(store)
            accounting = execute_stage2_primary_baseline(candidates, quotes)
            report = {
                "fold_id": fold_id,
                "plan_id": PLAN_ID,
                "tooling_id": TOOLING_CORRECTION_ID,
                "classification": "PROSPECTIVE_RESERVED_DEVELOPMENT_FEASIBILITY — NOT_PROFITABILITY_EVIDENCE",
                "exposure_record": reader.exposure_record,
                "stage1": s1_report.to_dict(),
                "stage2": accounting.to_dict(),
                "verdict": accounting.feasibility_verdict,
                "verified_utc": datetime.now(UTC).isoformat(),
            }

        atomic_publish_json(out_path, report)
        print(f"[OK] Feasibility evaluation complete for {fold_id}: {out_path}")
        return 0
    except (TierBAuthorizationError, TierBFeasibilityError, TierBPreflightError) as exc:
        print(f"[BLOCK] Tier-B execution on {fold_id} blocked: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"[FAIL] Tier-B execution error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 8 V2 Tier-B Feasibility Protocol Tooling (TC002)"
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
