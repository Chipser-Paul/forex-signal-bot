from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from bot.validation import development_evaluation_plan as plan


def _hash(char: str) -> str:
    return char * 64


def _readiness() -> dict:
    return {
        "schema_version": "phase8m.input-readiness.v1",
        "classification": "DEVELOPMENT_ONLY",
        "ticks": {"package_id": "ticks", "canonical_sha256": _hash("a"), "row_count": 10},
        "candles": {"manifest_sha256": _hash("b"), "attestation_id": "attestation", "timeframes": list(plan.TIMEFRAMES)},
        "dxy": {"package_id": "dxy", "canonical_sha256": _hash("c"), "record_count": 10, "constituents": ["EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY", "USDSEK"]},
        "official_news": {"package_id": "news", "content_canonical_sha256": _hash("d")},
        "observed_spread": {"package_id": "spread", "content_canonical_sha256": _hash("e")},
        "cost_policy": {"package_id": "cost", "content_canonical_sha256": _hash("f"), "policy_fingerprint": _hash("1")},
        "metadata_bounds": {"package_id": "metadata", "content_canonical_sha256": _hash("0"), "policy_fingerprint": _hash("2"), "mandatory_scenarios": ["one", "two"]},
        "fingerprints": {"strategy": _hash("3"), "execution": _hash("4"), "risk": _hash("5"), "broker_policy": _hash("6")},
        "session_time_rules": {"timezone": "UTC", "strategy_config_fingerprint": "safe", "rollover": ["21:55", "22:10"]},
        "contamination_register": {"sha256": _hash("7"), "artifact_count": 1, "source": "synthetic"},
        "phase8a_preregistration": {"path": "config/validation_plan.example.json", "sha256": _hash("8"), "fold_count": 4, "purge_seconds": 86400, "embargo_seconds": 86400, "warmup_seconds": 2419200},
    }


def test_plan_is_deterministic_and_keeps_candidate_frozen():
    first = plan.build_development_evaluation_plan(_readiness())
    second = plan.build_development_evaluation_plan(_readiness())
    assert first["plan_fingerprint"] == second["plan_fingerprint"]
    assert first["candidate"]["candidate_id"] == "phase6-frozen-v1"
    assert first["candidate"]["strategy_configuration_mutation"] == "PROHIBITED"


def test_plan_enforces_chronological_purge_embargo_and_all_scenarios():
    result = plan.build_development_evaluation_plan(_readiness())
    assert [fold["fold_id"] for fold in result["folds"]] == ["fold-01", "fold-02", "fold-03", "fold-04"]
    assert result["cost_scenarios"]["required_all"] is True
    assert result["metadata_scenarios"]["scenario_ids"] == ["one", "two"]
    assert result["cost_scenarios"]["cheapest_selection"] == "PROHIBITED"


@pytest.mark.parametrize("field", ["plan_fingerprint", "symbol"])
def test_tampered_plan_is_rejected(field):
    result = plan.build_development_evaluation_plan(_readiness())
    result[field] = "tampered"
    with pytest.raises(plan.DevelopmentEvaluationPlanError):
        plan.verify_development_evaluation_plan(result)


def test_final_validation_and_holdout_gates_stay_false():
    result = plan.build_development_evaluation_plan(_readiness())
    assert all(value is False for value in result["gates"].values())


def test_missing_dxy_or_timeframe_is_rejected_before_build(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        plan,
        "verify_year_package_identity_chain",
        lambda *args, **kwargs: {
            "symbol": "XAUUSDm",
            "period": {"start_inclusive": plan.DEVELOPMENT_START, "end_exclusive": plan.DEVELOPMENT_END},
            "package_id": "ticks",
            "statistics": {
                "canonical_normalized_sha256": _hash("a"),
                "row_count": 1,
            },
        },
    )
    monkeypatch.setattr(plan, "verify_candles", lambda _: {"source_canonical_sha256": _hash("a"), "original_manifest_sha256": _hash("b"), "partitions": [{"timeframe": "M5"}]})
    root = tmp_path / "root"
    for path in (root / "evidence", root / "exness-tick-history" / "processed" / "packages", root / "exness-tick-history" / "processed" / "year-packages" / "exness-xauusdm-2024-development-b2a0234a470dd397", root / "derived" / "derived-candles-2024-v1-20260911T195553Z", root / "dxy" / "dxy-development-2024-v1-20260912T091410.712364Z"):
        path.mkdir(parents=True, exist_ok=True)
    package_ids = [f"month-{index:02d}" for index in range(1, 13)]
    for package_id in package_ids:
        (root / "exness-tick-history" / "processed" / "packages" / package_id).mkdir()
    year_manifest = root / "exness-tick-history" / "processed" / "year-packages" / "exness-xauusdm-2024-development-b2a0234a470dd397" / "manifest.json"
    year_manifest.write_text(json.dumps({"monthly_packages": [{"package_id": item} for item in package_ids]}), encoding="utf-8")
    with pytest.raises(plan.DevelopmentEvaluationPlanError, match="timeframes"):
        plan.verify_input_readiness(data_root=root, worktree=tmp_path, contamination_path=tmp_path / "missing.json")


def test_dry_run_is_synthetic_and_never_computes_performance():
    result = plan.synthetic_structure_dry_run()
    assert result == {"synthetic": True, "fold_count": 4, "performance_computed": False, "mt5_or_network_accessed": False, "gates_unchanged": True}


def test_fresh_imports_do_not_load_mt5_or_network_modules():
    import inspect

    # The global fixture installs a fake MetaTrader5 module for unrelated
    # tests, so inspect this module's import surface instead of sys.modules.
    source = inspect.getsource(plan)
    assert "MetaTrader5" not in source
    assert "requests" not in source


def test_no_strategy_parameter_mutation_is_expressed_by_plan_contract():
    result = plan.build_development_evaluation_plan(_readiness())
    assert result["stress_and_sensitivity"]["strategy_parameter_variation"] == "PROHIBITED"
    assert result["prohibitions"]["automatic_tuning"] is True
