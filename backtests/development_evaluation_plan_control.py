"""Offline control for the Phase 8M plan; no strategy runner is exposed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bot.acquisition.evidence_store import load_evidence_package  # noqa: E402
from bot.validation.development_evaluation_plan import (  # noqa: E402
    DevelopmentEvaluationPlanError,
    build_development_evaluation_plan,
    publish_plan,
    synthetic_structure_dry_run,
    verify_development_evaluation_plan,
    verify_input_readiness,
)


def _default_data_root() -> Path:
    return Path(r"C:\Users\chips\forex-signal-bot-data\phase8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Phase 8M development-evaluation plan control")
    parser.add_argument("command", choices=("build-plan", "verify-plan", "status", "dry-run-structure"))
    parser.add_argument("--data-root", type=Path, default=_default_data_root())
    parser.add_argument("--worktree", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--contamination", type=Path, default=Path(__file__).resolve().parents[1] / "baseline" / "phase8_contamination_register.json")
    parser.add_argument("--package-id")
    parser.add_argument(
        "--tick-verification-depth",
        choices=("identity-chain", "deep-stream"),
        default="identity-chain",
        help=(
            "identity-chain: completion/manifest/partition-hash binding "
            "without streaming tick rows; deep-stream: full row-level "
            "re-canonicalization (tens of minutes)"
        ),
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "dry-run-structure":
            result = synthetic_structure_dry_run()
        elif args.command == "build-plan":
            result = publish_plan(
                data_root=args.data_root,
                worktree=args.worktree,
                contamination_path=args.contamination,
                tick_verification_depth=args.tick_verification_depth,
            )
        elif args.command == "status":
            result = verify_input_readiness(
                data_root=args.data_root,
                worktree=args.worktree,
                contamination_path=args.contamination,
                tick_verification_depth=args.tick_verification_depth,
            )
        else:
            if not args.package_id:
                raise DevelopmentEvaluationPlanError("verify-plan requires --package-id")
            package = load_evidence_package(Path(args.data_root) / "evidence" / str(args.package_id))
            result = verify_development_evaluation_plan(package["content"])
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except DevelopmentEvaluationPlanError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
