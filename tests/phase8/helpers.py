from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from bot.backtesting.models import FidelityClass
from bot.strategy.config import StrategyConfig
from bot.validation.datasets import file_sha256
from bot.validation.models import (
    AcceptanceOutcome,
    AcceptanceReport,
    DataStreamKind,
    EmpiricalPackageManifest,
    StudyPeriod,
    ValidationPlan,
    canonical_hash,
)
from bot.validation.synthetic import END, START, build_synthetic_package


UTC = timezone.utc


def package(tmp_path: Path, **kwargs) -> tuple[Path, EmpiricalPackageManifest]:
    root = tmp_path / "package"
    return root, build_synthetic_package(root, **kwargs)


def stream_by_kind(manifest: EmpiricalPackageManifest, kind: DataStreamKind, *, symbol: str | None = None):
    return next(
        item for item in manifest.streams
        if item.kind is kind and (symbol is None or item.symbol == symbol)
    )


def without_stream(
    manifest: EmpiricalPackageManifest,
    predicate: Callable[[object], bool],
) -> EmpiricalPackageManifest:
    return replace(manifest, streams=tuple(item for item in manifest.streams if not predicate(item)))


def rewrite_jsonl(
    root: Path,
    manifest: EmpiricalPackageManifest,
    stream_name: str,
    transform: Callable[[list[dict]], list[dict]],
) -> EmpiricalPackageManifest:
    stream = next(item for item in manifest.streams if item.name == stream_name)
    path = root / stream.relative_path
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    changed = transform(records)
    path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in changed), encoding="utf-8")
    updated = replace(stream, sha256=file_sha256(path), record_count=len(changed))
    return replace(manifest, streams=tuple(updated if item.name == stream_name else item for item in manifest.streams))


def plan(*, dataset_hash: str = "dataset-hash", mode: str = "ANCHORED", trials: int = 2) -> ValidationPlan:
    return ValidationPlan(
        schema_version=1,
        plan_id="synthetic-plan",
        research_hypothesis="Framework mechanics can be reproduced without market claims.",
        strategy_fingerprint=StrategyConfig().fingerprint(),
        execution_fingerprint=canonical_hash({"execution_model_version": "phase7-execution-v1"}),
        risk_policy_version="phase4-validation-v1",
        initial_capital=1000.0,
        dataset_hash=dataset_hash,
        development_period=StudyPeriod(datetime(2020, 1, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC), "development"),
        validation_period=StudyPeriod(datetime(2021, 2, 1, tzinfo=UTC), datetime(2022, 2, 1, tzinfo=UTC), "validation"),
        final_holdout=StudyPeriod(datetime(2022, 3, 1, tzinfo=UTC), datetime(2023, 3, 1, tzinfo=UTC), "holdout"),
        walk_forward_mode=mode,
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
        maximum_trials=trials,
        invalidation_conditions=("holdout_reuse", "strategy_change", "dataset_change"),
        finalized_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def accepted_report(*, package_hash: str, synthetic: bool) -> AcceptanceReport:
    return AcceptanceReport(
        package_id="fixture",
        package_hash=package_hash,
        outcome=(
            AcceptanceOutcome.ACCEPTED_FOR_DEVELOPMENT_ONLY
            if synthetic else AcceptanceOutcome.ACCEPTED_FOR_FINAL_VALIDATION
        ),
        checked_at=END,
        issues=(),
        accepted_stream_hashes={},
        fidelity=FidelityClass.TICK_BID_ASK,
        synthetic_label="SYNTHETIC TEST FIXTURE - NOT MARKET EVIDENCE" if synthetic else None,
    )
