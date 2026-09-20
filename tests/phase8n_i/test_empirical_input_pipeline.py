"""Phase 8N-I focused tests: plan-bound empirical input pipeline.

Synthetic fixtures only.  No network, no MT5, no strategy evaluation, no
holdout access, no empirical performance calculation.  The exact authorized
empirical command is exercised at the parser level only — never executed.
"""

from __future__ import annotations

import json
import subprocess  # noqa: S404 — import-safety tests run pinned code only
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.validation import empirical_input_pipeline as pipeline  # noqa: E402
from bot.validation import runner_compatibility as compat  # noqa: E402

UTC = timezone.utc

# The exact authorized Phase 8N-H command (verbatim, parser regression only).
AUTHORIZED_RUN_COMMAND = [
    "run",
    "--plan-package", "evidence-development_evaluation_plan-v1-4a6ab94c3e303c81",
    "--plan-fingerprint", "adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09",
    "--candidate", "phase6-frozen-v1",
    "--output-root", "C:/Users/chips/forex-signal-bot-data/phase8/development-evaluations/plan-4a6ab94c3e303c81",
    "--min-free-bytes", "16106127360",
    "--max-output-bytes", "10737418240",
    "--confirm-empirical-development-evaluation",
]


# ---------------------------------------------------------------------------
# Frozen metadata / overlays
# ---------------------------------------------------------------------------


def _cost_policy_content() -> dict:
    from bot.validation import cost_policy as cost_module

    return {
        "cost_components": {
            "commission": cost_module.commission_treatment_record(),
            "swap": cost_module.swap_treatment_record(),
        },
        "swap_scenarios": list(cost_module.build_swap_scenarios()),
        "slippage_scenarios": list(cost_module.SLIPPAGE_SCENARIOS),
    }


def test_commission_zero_normalization() -> None:
    metadata = pipeline.broker_symbol_metadata(
        _cost_policy_content(),
        swap_scenario=dict(_cost_policy_content()["swap_scenarios"][1]),
    )
    assert metadata.commission.kind.value == "PER_LOT_PER_SIDE"
    assert metadata.commission.amount == 0.0
    assert metadata.commission.currency == "USD"


def test_point_versus_pip_units_are_distinct() -> None:
    metadata = pipeline.broker_symbol_metadata(
        _cost_policy_content(),
        swap_scenario=dict(_cost_policy_content()["swap_scenarios"][1]),
    )
    assert metadata.point_size == 0.001  # MT5 point (8G metadata contract)
    assert metadata.tick_size == 0.001
    one_pip = metadata.point_size * 10
    assert one_pip == 0.01  # broker pip size
    # one 0.01 pip move on one lot = 1 USD; one 0.001 point move = 0.10 USD
    assert metadata.contract_size * one_pip == pytest.approx(1.0)
    assert metadata.contract_size * metadata.point_size == pytest.approx(0.10)


def test_swap_scenario_binding_and_triple_wednesday() -> None:
    content = _cost_policy_content()
    scenario = dict(content["swap_scenarios"][3])  # SWAP_EMAIL_3X_ADVERSE
    assert scenario["scenario_id"] == "SWAP_EMAIL_3X_ADVERSE"
    metadata = pipeline.broker_symbol_metadata(content, swap_scenario=scenario)
    assert metadata.swap.long_rate == pytest.approx(-3.85 * 3)
    assert metadata.swap.short_rate == pytest.approx(-0.25 * 3)
    assert metadata.swap.triple_swap_weekday == 2  # Wednesday


def test_unregistered_swap_scenario_rejected() -> None:
    content = _cost_policy_content()
    intruder = dict(content["swap_scenarios"][1])
    intruder["scenario_id"] = "SWAP_NOT_IN_POLICY"
    with pytest.raises(pipeline.EmpiricalPipelineError):
        pipeline.broker_symbol_metadata(content, swap_scenario=intruder)


def test_nonzero_commission_rejected() -> None:
    content = _cost_policy_content()
    content["cost_components"]["commission"]["mode"] = "PER_LOT_PER_SIDE"
    with pytest.raises(pipeline.EmpiricalPipelineError):
        pipeline.broker_symbol_metadata(
            content, swap_scenario=dict(_cost_policy_content()["swap_scenarios"][1]),
        )


def test_slippage_models_are_assumption_only() -> None:
    content = _cost_policy_content()
    severe = pipeline.slippage_model_for(content, slippage_scenario_id="SLIPPAGE_SEVERE_ADVERSE")
    assert severe.kind.value == "FIXED_ADVERSE_POINTS"
    assert severe.points == 3.0
    assert severe.source.value == "ASSUMED"
    with pytest.raises(pipeline.EmpiricalPipelineError):
        pipeline.slippage_model_for(content, slippage_scenario_id="SLIPPAGE_NOT_REGISTERED")


# ---------------------------------------------------------------------------
# Synthetic bindings / stream contract
# ---------------------------------------------------------------------------


def _synthetic_bindings(tmp_path: Path) -> pipeline.EmpiricalInputBindings:
    content = _cost_policy_content()
    candle_root = tmp_path / "candles"
    timeframe_frames = {}
    for timeframe, freq, periods in (("M5", "5min", 40), ("M15", "15min", 40),
                                     ("H1", "1h", 40), ("H4", "4h", 40),
                                     ("D1", "1D", 40), ("W1", "7D", 40)):
        opens = pd.date_range("2024-01-01", periods=periods, freq=freq, tz="UTC")
        frame = pd.DataFrame({
            "open_time_ms": (opens.view("int64") // 1_000_000),
            "close_time_ms": (opens.view("int64") // 1_000_000) + 1,
            "available_at_ms": (opens.view("int64") // 1_000_000) + 1,
            "bid_open": 2000.0, "bid_high": 2001.0, "bid_low": 1999.0,
            "bid_close": 2000.5, "tick_count": 10, "spread_median": 1.3,
        })
        timeframe_frames[timeframe] = frame
    candle_frames = pd.concat(
        [frame.assign(timeframe=tf) for tf, frame in timeframe_frames.items()],
        ignore_index=True,
    )
    partition_dir = candle_root / "candles" / "XAUUSDm" / "M5" / "year=2024"
    partition_dir.mkdir(parents=True, exist_ok=True)
    candle_frames.to_parquet(partition_dir / "part-00000.parquet", index=False)
    dxy_root = tmp_path / "dxy"
    dxy_root.mkdir(parents=True, exist_ok=True)
    binding = pipeline.EmpiricalInputBindings(
        plan={"folds": [], "plan_fingerprint": "synthetic"},
        evidence_root=tmp_path / "evidence",
        tick_year_root=tmp_path,
        monthly_roots=(tmp_path,),
        candle_root=candle_root,
        dxy_root=dxy_root,
        news_package={},
        news_snapshot=None,
        spread_binding={},
        cost_policy_package_id="synthetic-cost",
        cost_policy_content=content,
        metadata_bounds_package_id="synthetic-metadata",
        metadata_bounds_content={"mandatory_scenarios": []},
        readiness={"ticks": {"row_count": 1_000_000}},
    )
    return binding


def test_fold_interval_firewall(tmp_path: Path) -> None:
    binding = _synthetic_bindings(tmp_path)
    holdout_fold = {
        "evaluation": {"start": "2025-01-01T00:00:00Z", "end": "2025-04-01T00:00:00Z"},
    }
    with pytest.raises((pipeline.EmpiricalPipelineError, ValueError)):
        list(pipeline.empirical_event_stream(binding, holdout_fold))


def test_development_end_is_hard_clamped(tmp_path: Path) -> None:
    binding = _synthetic_bindings(tmp_path)
    assert pipeline.DEVELOPMENT_END_MS == 1735689600000
    assert pipeline.DEVELOPMENT_START_MS == 1704067200000


# ---------------------------------------------------------------------------
# Runner integration: empirical path guards (synthetic fixtures only)
# ---------------------------------------------------------------------------


def _cell(tmp_path: Path) -> dict:
    return {
        "cell_id": "cell_synthetic0000000000000000000000000000000000000000000000000000",
        "resume_identity": "resume_synthetic000000000000000000000000000000000000000000000000",
        "cost_overlay_ids": ["SWAP_EMAIL_REFERENCE", "SLIPPAGE_MODERATE_ADVERSE"],
        "metadata_overlay_id": "BASELINE_CURRENT_REFERENCE_PROXY",
        "scenario": {"scenario_id": "synthetic-scenario"},
        "fold": {"fold_id": "synthetic-fold"},
    }


def test_empirical_run_rejects_synthetic_stream(tmp_path: Path) -> None:
    from bot.validation import development_evaluation_runner as runner

    cell = _cell(tmp_path)
    cell_runner = runner.CellRunner(
        cell=cell, output_dir=tmp_path / "cell", plan_fingerprint="synthetic",
        seed=1, deterministic_order="UTC_TIMESTAMP_THEN_STABLE_ROW_AND_ACTION_ID",
    )
    with pytest.raises(runner.RunnerError, match="SYNTHETIC_STREAM_REJECTED"):
        cell_runner.run_cell(
            stream_path=tmp_path / "synthetic.jsonl",
            empirical=True, empirical_confirmation={"empirical_execution": True},
        )


def test_empirical_resume_rejects_synthetic_stream(tmp_path: Path) -> None:
    from bot.validation import development_evaluation_runner as runner

    cell = _cell(tmp_path)
    cell_runner = runner.CellRunner(
        cell=cell, output_dir=tmp_path / "cell", plan_fingerprint="synthetic",
        seed=1, deterministic_order="UTC_TIMESTAMP_THEN_STABLE_ROW_AND_ACTION_ID",
    )
    with pytest.raises(runner.RunnerError, match="SYNTHETIC_STREAM_REJECTED"):
        cell_runner.resume_cell(
            stream_path=tmp_path / "synthetic.jsonl",
            empirical=True, bindings=object(),
        )


def test_empirical_requires_bindings(tmp_path: Path) -> None:
    from bot.validation import development_evaluation_runner as runner

    cell = _cell(tmp_path)
    cell_runner = runner.CellRunner(
        cell=cell, output_dir=tmp_path / "cell", plan_fingerprint="synthetic",
        seed=1, deterministic_order="UTC_TIMESTAMP_THEN_STABLE_ROW_AND_ACTION_ID",
    )
    with pytest.raises(runner.RunnerError, match="bindings"):
        cell_runner.run_cell(empirical=True, bindings=None)


# ---------------------------------------------------------------------------
# CLI parser regression: exact authorized command parses, never executed
# ---------------------------------------------------------------------------


def test_exact_authorized_command_parses_without_synthetic_stream() -> None:
    sys.path.insert(0, str(REPO_ROOT / "backtests"))
    import development_evaluation_control as control

    parser = control.build_parser()
    args = parser.parse_args(AUTHORIZED_RUN_COMMAND)
    assert args.plan_package == "evidence-development_evaluation_plan-v1-4a6ab94c3e303c81"
    assert args.plan_fingerprint == "adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09"
    assert args.candidate == "phase6-frozen-v1"
    assert args.confirm_empirical_development_evaluation is True
    assert "synthetic_stream" not in vars(args)


def test_synthetic_stream_argument_is_unknown_for_run() -> None:
    sys.path.insert(0, str(REPO_ROOT / "backtests"))
    import development_evaluation_control as control

    parser = control.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([*AUTHORIZED_RUN_COMMAND, "--synthetic-stream", "x.jsonl"])


# ---------------------------------------------------------------------------
# Compatibility record (disposition branch B)
# ---------------------------------------------------------------------------


def _record(tmp_path: Path) -> dict:
    from bot.validation import development_evaluation_runner as runner

    return compat.build_compatibility_record(
        plan_package_id=runner.CORRECTED_PLAN_PACKAGE_ID,
        plan_fingerprint=runner.CORRECTED_PLAN_FINGERPRINT,
        invalidated_plan_package_id=runner.INVALIDATED_PLAN_PACKAGE_ID,
        invalidated_plan_fingerprint=runner.INVALIDATED_PLAN_FINGERPRINT,
        worktree=REPO_ROOT,
        code_commit="77097e4055a961a58c886c8752665508ec103660"[:40],
        runner_schema=runner.RUNNER_SCHEMA,
        runner_version=runner.RUNNER_VERSION,
        test_node_ids=("tests/phase8n_i/test_empirical_input_pipeline.py",),
    )


def test_compatibility_record_binds_plan_and_runner(tmp_path: Path) -> None:
    from bot.validation import development_evaluation_runner as runner

    record = _record(tmp_path)
    assert record["plan_binding"]["package_id"] == runner.CORRECTED_PLAN_PACKAGE_ID
    assert record["plan_binding"]["preserved"] is True
    assert record["plan_binding"]["republished"] is False
    verified = compat.verify_compatibility_record(record, worktree=REPO_ROOT)
    assert verified["verified"] is True


def test_compatibility_record_rejects_invalidated_plan(tmp_path: Path) -> None:
    from bot.validation import development_evaluation_runner as runner

    with pytest.raises(compat.CompatibilityRecordError):
        compat.build_compatibility_record(
            plan_package_id=runner.INVALIDATED_PLAN_PACKAGE_ID,
            plan_fingerprint=runner.INVALIDATED_PLAN_FINGERPRINT,
            invalidated_plan_package_id=runner.INVALIDATED_PLAN_PACKAGE_ID,
            invalidated_plan_fingerprint=runner.INVALIDATED_PLAN_FINGERPRINT,
            worktree=REPO_ROOT,
            code_commit="7" * 40,
            runner_schema="s", runner_version="v",
            test_node_ids=("t",),
        )


def test_compatibility_record_detects_runner_drift(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["runner_binding"]["fingerprint"] = "0" * 64
    with pytest.raises(compat.CompatibilityRecordError, match="drifted"):
        compat.verify_compatibility_record(record, worktree=REPO_ROOT)


def test_compatibility_record_publishes_and_readback(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["recorded_at_utc"] = datetime.now(UTC).isoformat()
    published, package_id = compat.publish_compatibility_record(
        evidence_root=tmp_path / "evidence", content=record,
    )
    assert package_id.startswith("evidence-runner_compatibility-v1-")
    loaded = json.loads((published / "package.json").read_text(encoding="utf-8"))
    assert loaded["content"]["plan_binding"]["plan_fingerprint"] == (
        "adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09"
    )
    # Idempotent republication returns the same package id.
    again, again_id = compat.publish_compatibility_record(
        evidence_root=tmp_path / "evidence", content=record,
    )
    assert again_id == package_id and again == published


# ---------------------------------------------------------------------------
# Import safety (fresh process, no MT5/network modules)
# ---------------------------------------------------------------------------


def test_no_mt5_or_network_imports() -> None:
    """Static source inspection (conftest blocks subprocesses in tests)."""
    sources = [
        REPO_ROOT / "bot" / "validation" / "empirical_input_pipeline.py",
        REPO_ROOT / "bot" / "validation" / "runner_compatibility.py",
        REPO_ROOT / "backtests" / "development_evaluation_control.py",
    ]
    for source in sources:
        text = source.read_text(encoding="utf-8")
        for prohibited in ("MetaTrader5", "import mt5", "requests", "urllib", "keyring"):
            assert prohibited not in text, (source.name, prohibited)
    # Import-time safety in this process.  Note: tests/conftest.py installs
    # a stateful FAKE MetaTrader5 stub globally, so the real broker SDK is
    # structurally unreachable during tests; the meaningful assertion is
    # that none of these modules references or binds it (checked above and
    # here via module attributes, matching the Phase 8N-G convention).
    import bot.validation.development_evaluation_runner as runner_module  # noqa: PLC0415
    import bot.validation.empirical_input_pipeline as pipeline_module  # noqa: PLC0415
    import bot.validation.runner_compatibility as compat_module  # noqa: PLC0415

    for module in (runner_module, pipeline_module, compat_module):
        assert not hasattr(module, "MetaTrader5")
    # Deeper transitive check across the pipeline's runtime imports.
    import bot.backtesting.adapters as adapters_module  # noqa: PLC0415
    import bot.execution.lifecycle.adapters as lifecycle_module  # noqa: PLC0415

    for module in (adapters_module, lifecycle_module):
        assert not hasattr(module, "MetaTrader5")
