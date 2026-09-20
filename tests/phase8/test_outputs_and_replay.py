from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtests.scientific_validation_replay import run_replay
from bot.backtesting.models import EXECUTION_MODEL_VERSION
from bot.strategy.config import StrategyConfig
from backtests.validation_control import build_parser
from bot.validation.datasets import (
    load_acceptance_report,
    load_empirical_package_manifest,
    validate_dataset_package,
    write_acceptance_report,
)
from bot.validation.models import SYNTHETIC_LABEL, ValidationError, canonical_data, canonical_hash
from bot.validation.outputs import (
    REQUIRED_VALIDATION_OUTPUTS,
    ValidationArtifacts,
    normalized_validation_bundle_hash,
    write_validation_bundle,
)
from bot.validation.study import build_walk_forward_folds, load_validation_plan
from bot.validation.synthetic import END, build_synthetic_package, synthetic_trades

from .helpers import plan


ROOT = Path(__file__).resolve().parents[2]


def artifacts(study_plan, acceptance) -> ValidationArtifacts:
    summary = {
        "plan_hash": study_plan.plan_hash,
        "dataset_hash": acceptance.package_hash,
        "strategy_fingerprint": study_plan.strategy_fingerprint,
        "execution_fingerprint": study_plan.execution_fingerprint,
        "seed": 8001,
        "fidelity_class": acceptance.fidelity.value,
        "validation_status": "FRAMEWORK_VERIFIED_EMPIRICAL_DATA_REQUIRED",
        "profitability_evidence": False,
    }
    return ValidationArtifacts(
        validation_plan=canonical_data(study_plan),
        dataset_acceptance=canonical_data(acceptance),
        contamination_register={"source": "synthetic", "artifacts": []},
        split_manifest={"folds": canonical_data(build_walk_forward_folds(study_plan))},
        candidate_registry=({"candidate_id": "phase6-frozen-v1"},),
        walk_forward_results={"status": "SYNTHETIC_ONLY"},
        bootstrap_results={"status": "SYNTHETIC_ONLY"},
        stress_results={"status": "SYNTHETIC_ONLY"},
        sensitivity_results={"selection_permitted": False},
        regime_results={"status": "SYNTHETIC_ONLY"},
        holdout_access=(),
        validation_summary=summary,
    )


def test_manifest_and_plan_roundtrip_loaders(tmp_path):
    package_root = tmp_path / "package"
    manifest = build_synthetic_package(package_root)
    manifest_path = tmp_path / "package.json"
    manifest_path.write_text(json.dumps(canonical_data(manifest), sort_keys=True), encoding="utf-8")
    loaded_manifest = load_empirical_package_manifest(manifest_path)
    assert loaded_manifest.package_hash == manifest.package_hash

    study_plan = plan(dataset_hash=manifest.package_hash)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(canonical_data(study_plan), sort_keys=True), encoding="utf-8")
    loaded_plan = load_validation_plan(plan_path)
    assert loaded_plan.plan_hash == study_plan.plan_hash

    report = validate_dataset_package(manifest, package_root, checked_at=END)
    report_path = tmp_path / "acceptance.json"
    write_acceptance_report(report_path, report)
    assert load_acceptance_report(report_path) == report
    with pytest.raises(FileExistsError):
        write_acceptance_report(report_path, report)


def test_validation_bundle_contains_all_files_and_unmistakable_label(tmp_path):
    package_root = tmp_path / "package"
    manifest = build_synthetic_package(package_root)
    acceptance = validate_dataset_package(manifest, package_root, checked_at=END)
    study_plan = plan(dataset_hash=acceptance.package_hash)
    bundle = write_validation_bundle(
        tmp_path / "results", "study-1", artifacts(study_plan, acceptance), synthetic=True, git_dirty=True
    )
    assert {item.name for item in bundle.iterdir()} == set(REQUIRED_VALIDATION_OUTPUTS)
    summary = json.loads((bundle / "validation_summary.json").read_text(encoding="utf-8"))
    assert summary["result_label"] == SYNTHETIC_LABEL
    assert summary["profitability_evidence"] is False
    assert summary["git_dirty"] is True
    report = (bundle / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
    assert SYNTHETIC_LABEL in report
    assert "not a profitability claim" in report


def test_validation_bundle_is_reproducible_and_never_overwrites(tmp_path):
    package_root = tmp_path / "package"
    manifest = build_synthetic_package(package_root)
    acceptance = validate_dataset_package(manifest, package_root, checked_at=END)
    study_plan = plan(dataset_hash=acceptance.package_hash)
    content = artifacts(study_plan, acceptance)
    first = write_validation_bundle(tmp_path / "a", "same", content, synthetic=True)
    second = write_validation_bundle(tmp_path / "b", "same", content, synthetic=True)
    assert normalized_validation_bundle_hash(first) == normalized_validation_bundle_hash(second)
    with pytest.raises(FileExistsError):
        write_validation_bundle(tmp_path / "a", "same", content, synthetic=True)


def test_empirical_output_from_dirty_tree_fails_closed(tmp_path):
    package_root = tmp_path / "package"
    manifest = build_synthetic_package(package_root)
    acceptance = validate_dataset_package(manifest, package_root, checked_at=END)
    with pytest.raises(ValidationError, match="dirty tree"):
        write_validation_bundle(
            tmp_path / "results", "empirical", artifacts(plan(dataset_hash=acceptance.package_hash), acceptance),
            synthetic=False, git_dirty=True,
        )


def test_synthetic_output_cannot_claim_validation_pass(tmp_path):
    package_root = tmp_path / "package"
    manifest = build_synthetic_package(package_root)
    acceptance = validate_dataset_package(manifest, package_root, checked_at=END)
    content = artifacts(plan(dataset_hash=acceptance.package_hash), acceptance)
    content = ValidationArtifacts(**{**content.__dict__, "validation_summary": {**content.validation_summary, "validation_status": "PASS"}})
    with pytest.raises(ValidationError, match="cannot claim"):
        write_validation_bundle(tmp_path / "results", "unsafe", content, synthetic=True)


def test_replay_covers_all_framework_scenarios_without_market_claims():
    replay = run_replay()
    assert replay["scenario_count"] == 22
    assert replay["profitability_evidence"] is False
    assert replay["real_holdout_accessed"] is False
    assert replay["result_label"] == SYNTHETIC_LABEL
    assert all(item["status"] == "PASS" for item in replay["scenarios"].values())


def test_configuration_fingerprints_are_stable_and_frozen():
    first = plan()
    second = plan()
    assert first.plan_hash == second.plan_hash
    assert first.strategy_fingerprint == StrategyConfig().fingerprint()
    assert first.execution_fingerprint == canonical_hash({"execution_model_version": EXECUTION_MODEL_VERSION})
    assert canonical_hash(canonical_data(first)) == first.plan_hash


def test_validation_framework_has_no_broker_or_network_imports():
    paths = list((ROOT / "bot" / "validation").glob("*.py")) + [ROOT / "backtests" / "scientific_validation_replay.py"]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for prohibited in ("MetaTrader5", "order_send(", "order_check(", "requests.", "urlopen("):
        assert prohibited not in source


def test_holdout_control_requires_explicit_authorization_flag():
    parser = build_parser()
    args = parser.parse_args([
        "authorize-holdout", "--plan", "plan.json", "--acceptance-report", "acceptance.json",
        "--candidate-id", "phase6-frozen-v1", "--lock", "holdout.json",
        "--access-log", "access.jsonl", "--justification", "owner review",
    ])
    assert args.authorize_final_holdout is False
    explicitly_authorized = parser.parse_args([
        "authorize-holdout", "--plan", "plan.json", "--acceptance-report", "acceptance.json",
        "--candidate-id", "phase6-frozen-v1", "--lock", "holdout.json",
        "--access-log", "access.jsonl", "--justification", "owner review",
        "--authorize-final-holdout",
    ])
    assert explicitly_authorized.authorize_final_holdout is True


def test_raw_data_directories_are_not_part_of_framework_outputs(tmp_path):
    assert "raw" not in {name.lower() for name in REQUIRED_VALIDATION_OUTPUTS}
    assert synthetic_trades(0) == ()
    for schema in ("empirical_data_package.schema.json", "validation_plan.schema.json"):
        parsed = json.loads((ROOT / "config" / schema).read_text(encoding="utf-8"))
        assert parsed["$schema"].endswith("2020-12/schema")
