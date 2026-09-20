from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from bot.validation.datasets import (
    load_acceptance_report,
    load_empirical_package_manifest,
    validate_dataset_package,
    write_acceptance_report,
)
from bot.validation.models import HoldoutIdentity, canonical_data
from bot.validation.study import HoldoutLock, load_validation_plan


UTC = timezone.utc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline Phase 8 dataset and holdout control")
    subcommands = parser.add_subparsers(dest="command", required=True)
    acceptance = subcommands.add_parser("accept-dataset", help="validate a local empirical package")
    acceptance.add_argument("--manifest", type=Path, required=True)
    acceptance.add_argument("--package-root", type=Path, required=True)
    acceptance.add_argument("--report", type=Path, required=True)

    holdout = subcommands.add_parser("authorize-holdout", help="record an explicit final-holdout access decision")
    holdout.add_argument("--plan", type=Path, required=True)
    holdout.add_argument("--acceptance-report", type=Path, required=True)
    holdout.add_argument("--candidate-id", required=True)
    holdout.add_argument("--lock", type=Path, required=True)
    holdout.add_argument("--access-log", type=Path, required=True)
    holdout.add_argument("--justification", required=True)
    holdout.add_argument("--authorize-final-holdout", action="store_true")
    holdout.add_argument("--authorize-repeat", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now = datetime.now(UTC)
    if args.command == "accept-dataset":
        manifest = load_empirical_package_manifest(args.manifest)
        report = validate_dataset_package(manifest, args.package_root, checked_at=now)
        write_acceptance_report(args.report, report)
        print(json.dumps(canonical_data(report), sort_keys=True, indent=2))
        return 0 if not any(issue.fatal for issue in report.issues) else 2

    plan = load_validation_plan(args.plan)
    report = load_acceptance_report(args.acceptance_report)
    if args.candidate_id not in plan.permitted_candidate_ids:
        raise ValueError("candidate is not permitted by the finalized validation plan")
    identity = HoldoutIdentity(
        dataset_hash=plan.dataset_hash,
        period=plan.final_holdout,
        strategy_fingerprint=plan.strategy_fingerprint,
        execution_fingerprint=plan.execution_fingerprint,
        validation_plan_hash=plan.plan_hash,
        candidate_id=args.candidate_id,
    )
    lock = HoldoutLock(args.lock, args.access_log)
    lock.seal(identity, finalized_at=plan.finalized_at)
    granted = lock.request_access(
        identity,
        report,
        now=now,
        explicit=args.authorize_final_holdout,
        justification=args.justification,
        repeat_authorized=args.authorize_repeat,
    )
    print(json.dumps({"granted": granted, "access_records": len(lock.access_records())}, sort_keys=True))
    return 0 if granted else 3


if __name__ == "__main__":
    raise SystemExit(main())
