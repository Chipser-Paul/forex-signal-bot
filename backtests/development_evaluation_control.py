"""Phase 8N-G control CLI for the streaming development-evaluation runner.

Read-only commands (`inspect`, `verify-inputs`, `estimate`, `status`,
`verify-results`, `dry-run-structure`) verify the frozen inputs and plan
without executing anything.  `run`/`resume` are guarded behind an explicit
development-evaluation confirmation flag and exact plan identity binding;
no default invocation can start an empirical evaluation.  The empirical
runner itself refuses to consume the 2024 datasets until the separately
authorized run publishes its confirmation contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.validation import development_evaluation_runner as runner  # noqa: E402
from bot.validation import development_scenario_matrix as matrix_module  # noqa: E402


def _evidence_root(args: argparse.Namespace) -> Path:
    return Path(args.evidence_root)


def cmd_inspect(args: argparse.Namespace) -> int:
    plan = runner.load_corrected_plan(_evidence_root(args))
    cells = runner.required_cells(plan)
    print(json.dumps({
        "schema": runner.RUNNER_SCHEMA,
        "plan_package_id": runner.CORRECTED_PLAN_PACKAGE_ID,
        "plan_fingerprint": runner.CORRECTED_PLAN_FINGERPRINT,
        "candidate_id": "phase6-frozen-v1",
        "symbol": plan.get("symbol"),
        "period": plan.get("period"),
        "folds": len(plan.get("folds", [])),
        "scenarios": len(plan.get("scenario_matrix", {}).get("scenarios", [])),
        "required_cells": len(cells),
        "invalidated_plan_rejected": True,
        "gates": plan.get("gates", {}),
    }, sort_keys=True, indent=2))
    return 0


def cmd_verify_inputs(args: argparse.Namespace) -> int:
    readiness = runner.verify_input_firewall(
        evidence_root=_evidence_root(args),
        worktree=Path(args.worktree),
        contamination_path=Path(args.contamination_path),
        plan=runner.load_corrected_plan(_evidence_root(args)),
        tick_verification_depth=args.tick_verification_depth,
    )
    print(json.dumps({
        "schema": runner.RUNNER_SCHEMA,
        "verified": True,
        "classification": readiness.get("classification"),
        "ticks_package_id": readiness["ticks"]["package_id"],
        "tick_rows": readiness["ticks"].get("row_count"),
        "candles": readiness["candles"]["timeframes"],
        "official_news": readiness["official_news"]["package_id"],
        "dxy_package_id": readiness["dxy"]["package_id"],
        "dxy_records": readiness["dxy"]["record_count"],
        "observed_spread": readiness["observed_spread"]["package_id"],
        "cost_policy": readiness["cost_policy"]["package_id"],
        "metadata_bounds": readiness["metadata_bounds"]["package_id"],
        "metadata_scenarios": len(readiness["metadata_bounds"].get("mandatory_scenarios", [])),
    }, sort_keys=True, indent=2))
    return 0


def cmd_estimate(args: argparse.Namespace) -> int:
    context = runner.build_context(
        evidence_root=_evidence_root(args), worktree=Path(args.worktree),
        contamination_path=Path(args.contamination_path),
        output_root=Path(args.output_root),
    )
    estimate = runner.estimate_resources(context)
    runner.enforce_resource_guards(context, estimate)
    print(json.dumps(estimate, sort_keys=True, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    output_root = Path(args.output_root)
    if not output_root.is_dir():
        print(json.dumps({"status": "NOT_STARTED", "output_root": str(output_root)}, indent=2))
        return 0
    try:
        result = runner.verify_results(output_root)
    except runner.RunnerError as exc:
        print(json.dumps({"status": "INVALID_OR_INCOMPLETE", "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"status": "COMPLETE", **result}, indent=2))
    return 0


def cmd_verify_results(args: argparse.Namespace) -> int:
    result = runner.verify_results(Path(args.output_root))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def cmd_synthetic_rehearsal(args: argparse.Namespace) -> int:
    context = runner.build_context(
        evidence_root=_evidence_root(args), worktree=Path(args.worktree),
        contamination_path=Path(args.contamination_path),
        output_root=Path(args.output_root),
    )
    outcome = runner.synthetic_rehearsal(context, root=Path(args.rehearsal_root))
    print(json.dumps(outcome, sort_keys=True, indent=2))
    return 0


def _resolve_bindings(args: argparse.Namespace):
    """Resolve every empirical input through the frozen plan/evidence registry.

    No caller-supplied market-data path exists: the resolver binds exactly
    the datasets the corrected plan's verified identities select.
    """
    from bot.validation.empirical_input_pipeline import resolve_input_bindings

    return resolve_input_bindings(
        evidence_root=_evidence_root(args),
        worktree=Path(args.worktree),
        contamination_path=Path(args.contamination_path),
        plan=runner.load_corrected_plan(_evidence_root(args)),
        tick_verification_depth=getattr(args, "tick_verification_depth", "identity-chain"),
    )


def cmd_run(args: argparse.Namespace) -> int:
    confirmation = runner.empirical_run_confirmation(
        plan_package_id=args.plan_package,
        plan_fingerprint=args.plan_fingerprint,
        candidate_id=args.candidate,
        output_root=args.output_root,
        min_free_bytes=args.min_free_bytes,
        max_output_bytes=args.max_output_bytes,
        confirmed=args.confirm_empirical_development_evaluation,
    )
    bindings = _resolve_bindings(args)
    context = runner.build_context(
        evidence_root=_evidence_root(args), worktree=Path(args.worktree),
        contamination_path=Path(args.contamination_path),
        output_root=Path(args.output_root),
    )
    runner.enforce_resource_guards(context, runner.estimate_resources(context))
    cells = runner.required_cells(context.plan)
    plan_fingerprint = context.plan["plan_fingerprint"]
    feature_mode = getattr(args, "market-features", "off")
    executed = []
    for cell in cells:
        out = Path(args.output_root) / plan_fingerprint / "cells" / cell["cell_id"]
        cell_runner = runner.CellRunner(
            cell=cell, output_dir=out, plan_fingerprint=plan_fingerprint,
            seed=context.seed, deterministic_order=context.deterministic_order,
            market_feature_mode=feature_mode,
        )
        executed.append(cell_runner.run_cell(
            empirical=True, bindings=bindings,
            empirical_confirmation=confirmation,
        ))
    print(json.dumps({
        "schema": runner.RUNNER_SCHEMA, "cells_executed": len(executed),
        "mode": "EMPIRICAL" if feature_mode == "off" else "EMPIRICAL_OPTIMIZED",
        "note": "empirical streaming execution over plan-bound datasets",
    }, indent=2))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    confirmation = runner.empirical_run_confirmation(
        plan_package_id=args.plan_package,
        plan_fingerprint=args.plan_fingerprint,
        candidate_id=args.candidate,
        output_root=args.output_root,
        min_free_bytes=args.min_free_bytes,
        max_output_bytes=args.max_output_bytes,
        confirmed=args.confirm_empirical_development_evaluation,
    )
    bindings = _resolve_bindings(args)
    plan = runner.load_corrected_plan(_evidence_root(args))
    cell = next(
        (candidate for candidate in runner.required_cells(plan)
         if candidate["cell_id"] == args.cell_id),
        None,
    )
    if cell is None:
        raise runner.RunnerError("UNREGISTERED_SCENARIO_CELL")
    out = Path(args.output_root) / plan["plan_fingerprint"] / "cells" / cell["cell_id"]
    cell_runner = runner.CellRunner(
        cell=cell, output_dir=out, plan_fingerprint=plan["plan_fingerprint"],
        seed=int(plan["determinism"]["seeds"][0]),
        deterministic_order=plan["determinism"]["ordering"],
        market_feature_mode=getattr(args, "market-features", "off"),
    )
    result = cell_runner.resume_cell(
        empirical=True, bindings=bindings,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_dry_run_structure(args: argparse.Namespace) -> int:
    plan = runner.load_corrected_plan(_evidence_root(args))
    cells = runner.required_cells(plan)
    matrix_module.verify_cell_contract(plan["scenario_cell_contract"], plan["scenario_matrix"], plan["folds"])
    structure = {
        "schema": runner.RUNNER_SCHEMA,
        "mode": "STRUCTURAL_DRY_RUN",
        "cells": [cell["cell_id"] for cell in cells],
        "folds": [fold["fold_id"] for fold in plan["folds"]],
        "scenarios": [scenario["scenario_id"] for scenario in plan["scenario_matrix"]["scenarios"]],
        "stages": ["inspect", "verify-inputs", "estimate", "prepare", "run", "resume", "verify-results"],
        "output_contract": list(runner.REQUIRED_OUTPUT_FILES),
        "empirical_execution": False,
    }
    print(json.dumps(structure, sort_keys=True, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 8N-G streaming development-evaluation runner control")
    parser.add_argument("--evidence-root", default="C:/Users/chips/forex-signal-bot-data/phase8/evidence")
    parser.add_argument("--worktree", default=str(REPO_ROOT))
    parser.add_argument("--contamination-path", default=str(REPO_ROOT / "baseline" / "phase8_contamination_register.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("inspect", "estimate", "dry-run-structure"):
        sub = subparsers.add_parser(name)
        if name == "estimate":
            sub.add_argument("--output-root", required=True)
        sub.set_defaults(handler={"inspect": cmd_inspect, "estimate": cmd_estimate,
                                  "dry-run-structure": cmd_dry_run_structure}[name])

    verify = subparsers.add_parser("verify-inputs")
    verify.add_argument("--tick-verification-depth", choices=("identity-chain", "deep"), default="identity-chain")
    verify.set_defaults(handler=cmd_verify_inputs)

    status = subparsers.add_parser("status")
    status.add_argument("--output-root", required=True)
    status.set_defaults(handler=cmd_status)

    results = subparsers.add_parser("verify-results")
    results.add_argument("--output-root", required=True)
    results.set_defaults(handler=cmd_verify_results)

    rehearsal = subparsers.add_parser("synthetic-rehearsal")
    rehearsal.add_argument("--rehearsal-root", required=True)
    rehearsal.add_argument("--output-root", default=str(REPO_ROOT))
    rehearsal.set_defaults(handler=cmd_synthetic_rehearsal)

    for name in ("run", "resume"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--plan-package", required=True)
        sub.add_argument("--plan-fingerprint", required=True)
        sub.add_argument("--candidate", required=True)
        sub.add_argument("--output-root", required=True)
        sub.add_argument("--min-free-bytes", type=int, default=runner.DEFAULT_MIN_FREE_BYTES)
        sub.add_argument("--max-output-bytes", type=int, default=runner.DEFAULT_MAX_OUTPUT_BYTES)
        sub.add_argument("--confirm-empirical-development-evaluation", action="store_true")
        sub.add_argument(
            "--market-features", choices=("off", "fast"), default="off",
            help="Phase 8N-K: memoize scenario-invariant causal market features "
                 "across the fold's cells (pure execution mechanics; default off)",
        )
        if name == "resume":
            sub.add_argument("--cell-id", required=True)
        sub.set_defaults(handler=cmd_run if name == "run" else cmd_resume)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except runner.RunnerError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
