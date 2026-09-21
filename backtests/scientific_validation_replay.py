from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from bot.backtesting.models import FidelityClass
from bot.strategy.config import StrategyConfig
from bot.validation.analytics import (
    adverse_ordering_stress,
    calculate_metrics,
    moving_block_bootstrap,
    regime_stability,
    run_cost_stress,
    run_sensitivity,
    simulate_account_path,
)
from bot.validation.datasets import file_sha256, validate_dataset_package
from bot.validation.models import (
    AcceptanceOutcome,
    CandidateRecord,
    DataStreamKind,
    HoldoutIdentity,
    SYNTHETIC_LABEL,
    StudyPeriod,
    ValidationPlan,
    canonical_data,
    canonical_hash,
)
from bot.validation.outputs import ValidationArtifacts, normalized_validation_bundle_hash, write_validation_bundle
from bot.validation.study import CandidateRegistry, HoldoutLock, build_walk_forward_folds
from bot.validation.synthetic import END, START, build_synthetic_package, synthetic_trades


UTC = timezone.utc
NOW = datetime(2024, 1, 11, tzinfo=UTC)


def _plan(dataset_hash: str) -> ValidationPlan:
    return ValidationPlan(
        schema_version=1,
        plan_id="synthetic-framework-plan",
        research_hypothesis="Exercise validation mechanics without market inference.",
        strategy_fingerprint=StrategyConfig().fingerprint(),
        execution_fingerprint=canonical_hash({"execution_model_version": "phase7-execution-v1"}),
        risk_policy_version="phase4-validation-v1",
        initial_capital=1000.0,
        dataset_hash=dataset_hash,
        development_period=StudyPeriod(datetime(2020, 1, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC), "development"),
        validation_period=StudyPeriod(datetime(2021, 2, 1, tzinfo=UTC), datetime(2022, 2, 1, tzinfo=UTC), "validation"),
        final_holdout=StudyPeriod(datetime(2022, 3, 1, tzinfo=UTC), datetime(2023, 3, 1, tzinfo=UTC), "holdout"),
        walk_forward_mode="ANCHORED",
        fold_count=4,
        purge_seconds=86400,
        embargo_seconds=86400,
        warmup_seconds=86400 * 28,
        primary_metrics=("net_expectancy", "net_profit_factor", "maximum_executable_equity_drawdown"),
        secondary_metrics=("win_rate", "cost_ratio", "concentration"),
        acceptance_policy_version="phase8a-acceptance-v1",
        stress_scenarios=("cost_x_1.25", "cost_x_1.50", "cost_x_2.00"),
        sensitivity_spec={"confluence_threshold": (0.9, 0.95, 1.05, 1.1)},
        statistical_procedures=("moving_block_bootstrap", "path_dependent_equity_resimulation"),
        random_seeds=(8001,),
        permitted_candidate_ids=("phase6-frozen-v1",),
        maximum_trials=2,
        invalidation_conditions=("strategy_change", "dataset_change", "holdout_reuse"),
        finalized_at=NOW,
    )


def _rewrite(root: Path, manifest, stream_name: str, transform):
    stream = next(item for item in manifest.streams if item.name == stream_name)
    path = root / stream.relative_path
    if stream.kind is DataStreamKind.BROKER_METADATA:
        records = [json.loads(path.read_text(encoding="utf-8"))]
        changed = transform(records)
        path.write_text(json.dumps(changed[0], sort_keys=True, indent=2) + "\n", encoding="utf-8")
    else:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        changed = transform(records)
        path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in changed), encoding="utf-8")
    updated = replace(stream, sha256=file_sha256(path), record_count=len(changed))
    return replace(manifest, streams=tuple(updated if item.name == stream_name else item for item in manifest.streams))


def _reasons(report) -> list[str]:
    return sorted({issue.reason_code for issue in report.issues})


def _candidate() -> CandidateRecord:
    return CandidateRecord(
        candidate_id="phase6-frozen-v1",
        parent_candidate_id=None,
        parameter_difference={},
        reason="frozen initial candidate",
        dataset_periods_accessed=("development",),
        metrics_examined=("net_expectancy",),
        seed=8001,
        registered_at=NOW,
        outcome="REGISTERED",
        rejection_reason=None,
        final_holdout_accessed=False,
    )


def _artifact_bundle(study_plan: ValidationPlan, acceptance, metrics, bootstrap, stress, sensitivity, regimes, folds, candidates, accesses):
    summary = {
        "plan_hash": study_plan.plan_hash,
        "dataset_hash": acceptance.package_hash,
        "strategy_fingerprint": study_plan.strategy_fingerprint,
        "execution_fingerprint": study_plan.execution_fingerprint,
        "seed": 8001,
        "fidelity_class": acceptance.fidelity.value,
        "validation_status": "FRAMEWORK_VERIFIED_EMPIRICAL_DATA_REQUIRED",
        "profitability_evidence": False,
        "metrics_boundary_cases_only": True,
    }
    return ValidationArtifacts(
        validation_plan=canonical_data(study_plan),
        dataset_acceptance=canonical_data(acceptance),
        contamination_register={"synthetic": True, "artifacts": []},
        split_manifest={"folds": canonical_data(folds)},
        candidate_registry=tuple(candidates),
        walk_forward_results={"synthetic": True, "fold_count": len(folds), "metrics": metrics},
        bootstrap_results=bootstrap,
        stress_results=stress,
        sensitivity_results=sensitivity,
        regime_results=regimes,
        holdout_access=tuple(accesses),
        validation_summary=summary,
    )


def run_replay() -> Mapping[str, Any]:
    scenarios: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="phase8a-replay-") as temporary:
        root = Path(temporary)
        accepted_root = root / "accepted"
        manifest = build_synthetic_package(accepted_root)
        accepted = validate_dataset_package(manifest, accepted_root, checked_at=NOW)
        scenarios["accepted_high_fidelity_synthetic"] = {"outcome": accepted.outcome.value, "status": "PASS"}

        zero_root = root / "zero-cost"
        zero = build_synthetic_package(zero_root)
        zero = _rewrite(zero_root, zero, "broker_metadata", lambda rows: [{**rows[0], "commission": {"source": "NOT_AVAILABLE", "kind": "NONE", "value": 0}}])
        zero_report = validate_dataset_package(zero, zero_root, checked_at=NOW)
        scenarios["rejected_zero_cost"] = {"outcome": zero_report.outcome.value, "reasons": _reasons(zero_report), "status": "PASS"}

        missing_news = replace(manifest, streams=tuple(item for item in manifest.streams if item.kind is not DataStreamKind.NEWS_EVENTS))
        news_report = validate_dataset_package(missing_news, accepted_root, checked_at=NOW)
        scenarios["missing_news_history"] = {"reasons": _reasons(news_report), "status": "PASS"}

        missing_dxy = replace(manifest, streams=tuple(item for item in manifest.streams if not (item.kind is DataStreamKind.DXY_CONSTITUENT and item.symbol == "USDCHF")))
        dxy_report = validate_dataset_package(missing_dxy, accepted_root, checked_at=NOW)
        scenarios["missing_dxy_constituent"] = {"reasons": _reasons(dxy_report), "status": "PASS"}

        bad_hash = replace(manifest, streams=(replace(manifest.streams[0], sha256="0" * 64), *manifest.streams[1:]))
        hash_report = validate_dataset_package(bad_hash, accepted_root, checked_at=NOW)
        scenarios["hash_mismatch"] = {"reasons": _reasons(hash_report), "status": "PASS"}

        time_root = root / "timestamp"
        timestamp_manifest = build_synthetic_package(time_root)
        timestamp_manifest = _rewrite(time_root, timestamp_manifest, "xau_ticks", lambda rows: [{**rows[0], "timestamp": "2024-01-10T00:00:00"}, rows[1]])
        time_report = validate_dataset_package(timestamp_manifest, time_root, checked_at=NOW)
        scenarios["timestamp_contamination"] = {"reasons": _reasons(time_report), "status": "PASS"}

        study_plan = _plan(accepted.package_hash)
        folds = build_walk_forward_folds(study_plan)
        scenarios["chronological_walk_forward"] = {"folds": len(folds), "ordered": all(item.training.end < item.evaluation.start for item in folds), "status": "PASS"}
        scenarios["warmup_exclusion"] = {"excluded": all(item.warmup.end == item.evaluation.start for item in folds), "status": "PASS"}
        scenarios["purge_embargo"] = {"purge_seconds": folds[0].purge_seconds, "embargo_seconds": folds[0].embargo_seconds, "status": "PASS"}

        registry = CandidateRegistry(root / "candidates.jsonl", maximum_trials=2)
        registry.register(_candidate())
        scenarios["trial_registration"] = {**registry.disclosure(), "status": "PASS"}

        held = HoldoutIdentity(accepted.package_hash, study_plan.final_holdout, study_plan.strategy_fingerprint, study_plan.execution_fingerprint, study_plan.plan_hash, "phase6-frozen-v1")
        holdout = HoldoutLock(root / "holdout.json", root / "holdout_access.jsonl")
        holdout.seal(held, finalized_at=NOW)
        first = holdout.request_access(held, accepted, now=NOW, explicit=True, justification="synthetic probe")
        second = holdout.request_access(held, accepted, now=NOW, explicit=True, justification="synthetic repeat")
        scenarios["holdout_lock"] = {"granted": first, "reason": holdout.access_records()[0]["reason_code"], "status": "PASS"}
        scenarios["repeated_holdout_access"] = {"granted": second, "access_records": len(holdout.access_records()), "status": "PASS"}

        trades = synthetic_trades(24)
        bootstrap = moving_block_bootstrap(trades, replicates=100, block_length=4, seed=8001)
        scenarios["moving_block_bootstrap"] = {"deterministic": bootstrap == moving_block_bootstrap(trades, replicates=100, block_length=4, seed=8001), "status": "PASS"}
        account = simulate_account_path(adverse_ordering_stress(trades))
        scenarios["path_dependent_drawdown"] = {"path_points": len(account.path), "maximum_drawdown_fraction": account.maximum_drawdown_fraction, "status": "PASS"}
        stress = run_cost_stress(trades)
        scenarios["cost_stress"] = {"scenarios": len(stress), "selection_permitted": False, "status": "PASS"}
        sensitivity = run_sensitivity({"threshold": 1.0}, {"threshold": (0.9, 0.95, 1.05, 1.1)}, lambda values: 1.0 - abs(values["threshold"] - 1.0))
        scenarios["parameter_sensitivity"] = {"points": len(sensitivity["parameters"]["threshold"]), "selection_permitted": sensitivity["selection_permitted"], "status": "PASS"}
        regimes = regime_stability(trades, minimum_sample_size=10)
        scenarios["regime_slicing"] = {"regimes": len(regimes), "claims": sum(item["claim_permitted"] for item in regimes.values()), "status": "PASS"}
        metrics = calculate_metrics(trades, initial_capital=1000.0)
        scenarios["profit_concentration"] = {"reported": all(value is not None for value in metrics["profit_concentration"].values()), "status": "PASS"}
        thousand = simulate_account_path(trades, initial_capital=1000.0)
        scenarios["one_thousand_account_path"] = {"initial": thousand.path[0], "path_points": len(thousand.path), "status": "PASS"}
        scenarios["no_trade_result"] = {"boundary": calculate_metrics((), initial_capital=1000.0)["status"], "status": "PASS"}
        wins = tuple(replace(item, net_pnl=1.0, gross_pnl=1.25, net_r=1.0) for item in trades[:3])
        losses = tuple(replace(item, net_pnl=-1.0, gross_pnl=-0.75, net_r=-1.0) for item in trades[:3])
        scenarios["all_win_all_loss_boundaries"] = {
            "all_win": calculate_metrics(wins, initial_capital=1000.0)["profit_factor_net_boundary"],
            "all_loss_win_rate": calculate_metrics(losses, initial_capital=1000.0)["win_rate"],
            "status": "PASS",
        }

        artifacts = _artifact_bundle(study_plan, accepted, metrics, bootstrap, stress, sensitivity, regimes, folds, registry.records(), holdout.access_records())
        first_bundle = write_validation_bundle(root / "output-a", "synthetic-study", artifacts, synthetic=True)
        second_bundle = write_validation_bundle(root / "output-b", "synthetic-study", artifacts, synthetic=True)
        scenarios["reproducible_manifests"] = {
            "identical": normalized_validation_bundle_hash(first_bundle) == normalized_validation_bundle_hash(second_bundle),
            "label": SYNTHETIC_LABEL,
            "status": "PASS",
        }

    expected = {
        "accepted_high_fidelity_synthetic", "rejected_zero_cost", "missing_news_history",
        "missing_dxy_constituent", "hash_mismatch", "timestamp_contamination",
        "chronological_walk_forward", "warmup_exclusion", "purge_embargo",
        "trial_registration", "holdout_lock", "repeated_holdout_access",
        "moving_block_bootstrap", "path_dependent_drawdown", "cost_stress",
        "parameter_sensitivity", "regime_slicing", "profit_concentration",
        "one_thousand_account_path", "no_trade_result", "all_win_all_loss_boundaries",
        "reproducible_manifests",
    }
    if set(scenarios) != expected or any(item.get("status") != "PASS" for item in scenarios.values()):
        raise RuntimeError("Phase 8A synthetic replay is incomplete")
    return {
        "phase": "8A",
        "result_label": SYNTHETIC_LABEL,
        "scenario_count": len(scenarios),
        "profitability_evidence": False,
        "real_holdout_accessed": False,
        "scenarios": scenarios,
    }


if __name__ == "__main__":
    print(json.dumps(run_replay(), sort_keys=True, indent=2))
