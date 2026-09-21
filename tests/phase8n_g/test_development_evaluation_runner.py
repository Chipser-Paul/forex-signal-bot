"""Phase 8N-G focused tests: streaming development-evaluation runner.

Synthetic fixtures only.  No network, no MT5, no strategy evaluation, no
holdout access, no empirical performance calculation.  The fixture plan is
built from the real frozen contracts (preregistered folds, 16-scenario
matrix, 64-cell contract); the runner's plan-identity constants are patched
to the fixture's derived identity so the production firewall logic is fully
exercised without touching live evidence.
"""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.validation import development_evaluation_runner as runner  # noqa: E402

UTC = timezone.utc
LIVE_PLAN_FP = runner.CORRECTED_PLAN_FINGERPRINT
LIVE_PLAN_PKG = runner.CORRECTED_PLAN_PACKAGE_ID
INVALIDATED_PKG = runner.INVALIDATED_PLAN_PACKAGE_ID


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def synthetic_plan() -> dict:
    """A real-shaped plan: preregistered folds, 16 scenarios, 64 cells."""
    from bot.validation import development_evaluation_plan as plan_module
    from bot.validation import development_scenario_matrix as matrix_module

    folds = [dict(fold) for fold in plan_module._fixed_folds()]
    matrix = matrix_module.compose_scenarios(
        matrix_module.cost_policy.SWAP_SCENARIO_ORDER,
        tuple(item["scenario_id"] for item in matrix_module.cost_policy.SLIPPAGE_SCENARIOS),
        matrix_module.SCENARIO_ORDER,
        tuple(fold["fold_id"] for fold in folds),
    )
    bindings = {name: f"{index:064x}" for index, name in enumerate(matrix_module.REQUIRED_BINDINGS)}
    contract = matrix_module.build_cell_contract(matrix, folds, bindings)
    return {
        "schema_version": "phase8n.synthetic-runner-fixture-plan.v1",
        "plan_fingerprint": "0" * 64,
        "symbol": "XAUUSDm",
        "period": {"start": "2024-01-01T00:00:00Z", "end_exclusive": "2025-01-01T00:00:00Z"},
        "status": "FROZEN_AWAITING_AUTHORIZED_RUN",
        "candidate": {"candidate_id": "phase6-frozen-v1", "strategy_configuration_mutation": "PROHIBITED"},
        "scenario_cell_contract": contract,
        "scenario_matrix": matrix,
        "folds": folds,
        "gates": {
            "empirical_strategy_evaluation_executed": False,
            "strategy_evaluation_authorized": False,
            "holdout_access_authorized": False,
            "accepted_for_final_validation": False,
            "phase9_authorized": False,
        },
        "cost_scenarios": {"required_all": True, "cheapest_selection": "PROHIBITED"},
        "metadata_scenarios": {"required_all": True, "cheapest_selection": "PROHIBITED"},
        "determinism": {"seeds": [8001], "ordering": "UTC_TIMESTAMP_THEN_STABLE_ROW_AND_ACTION_ID"},
        "resource_guards": {"maximum_output_bytes": 10 * 1024**3, "maximum_runtime_seconds": 14400},
        "input_readiness": {
            "schema_version": "phase8m.input-readiness.v1",
            "classification": "DEVELOPMENT_ONLY",
            "ticks": {"package_id": "synthetic-ticks", "canonical_sha256": "0" * 64, "row_count": 10},
            "candles": {"manifest_sha256": "1" * 64, "timeframes": ["M5"]},
        },
    }


@pytest.fixture()
def plan_root(tmp_path: Path, synthetic_plan: dict, monkeypatch) -> Path:
    """Evidence root carrying the fixture plan under its derived package id.

    The runner's identity constants are bound to the derived package so the
    production firewall (fingerprint recompute, invalidated-plan rejection,
    candidate binding) is exercised end to end.
    """
    from bot.acquisition.evidence_contracts import canonical_hash
    from bot.acquisition.evidence_store import build_evidence_package

    # The synthetic plan binds its own (synthetic) invalidated predecessor,
    # mirroring how the live corrected plan binds the real disposition.
    synthetic_invalidated_id = "evidence-development_evaluation_plan-v1-invalidatedfixture"
    synthetic_invalidated_fp = "d" * 64
    synthetic_plan["invalidates"] = {
        "package_id": synthetic_invalidated_id,
        "fingerprint": synthetic_invalidated_fp,
        "status": "INVALIDATED_BEFORE_EXECUTION",
    }
    monkeypatch.setattr(runner, "INVALIDATED_PLAN_PACKAGE_ID", synthetic_invalidated_id)
    monkeypatch.setattr(runner, "INVALIDATED_PLAN_FINGERPRINT", synthetic_invalidated_fp)
    synthetic_plan["plan_fingerprint"] = canonical_hash({
        key: value for key, value in synthetic_plan.items() if key != "plan_fingerprint"
    })
    package, package_id = build_evidence_package(
        kind="development_evaluation_plan", content=dict(synthetic_plan), source_path=None
    )
    root = tmp_path / "evidence"
    root.mkdir()
    package_dir = root / package_id
    package_dir.mkdir()
    (package_dir / "package.json").write_text(
        json.dumps(package, sort_keys=True, indent=2), encoding="utf-8"
    )
    (package_dir / "manifest.json").write_text(
        json.dumps(package["manifest"], sort_keys=True, indent=2), encoding="utf-8"
    )
    monkeypatch.setattr(runner, "CORRECTED_PLAN_PACKAGE_ID", package_id)
    monkeypatch.setattr(runner, "CORRECTED_PLAN_FINGERPRINT", synthetic_plan["plan_fingerprint"])
    return root


@pytest.fixture()
def runner_context(plan_root: Path, tmp_path: Path, monkeypatch, synthetic_plan: dict) -> runner.RunnerContext:
    readiness = synthetic_plan["input_readiness"]
    monkeypatch.setattr(
        runner.plan_module, "verify_input_readiness", lambda **kwargs: dict(readiness)
    )
    return runner.build_context(
        evidence_root=plan_root,
        worktree=REPO_ROOT,
        contamination_path=REPO_ROOT / "baseline" / "phase8_contamination_register.json",
        output_root=tmp_path / "out",
    )


@pytest.fixture()
def synthetic_stream(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic_stream.jsonl"
    base = datetime(2024, 1, 10, tzinfo=UTC)
    lines = []
    for index in range(12):
        moment = base + timedelta(seconds=30 * index)
        lines.append(json.dumps({
            "timestamp": moment.isoformat(),
            "record_id": f"synthetic-{index:03d}",
            "bid": 2030.0, "ask": 2030.2, "sequence": index + 1,
        }, sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Plan firewall
# ---------------------------------------------------------------------------


def test_corrected_plan_acceptance(plan_root: Path) -> None:
    plan = runner.load_corrected_plan(plan_root)
    assert plan["plan_fingerprint"] == runner.CORRECTED_PLAN_FINGERPRINT
    assert plan["scenario_cell_contract"]["cell_count"] == 64
    assert plan["scenario_matrix"]["unique_scenario_count"] == 16


def test_invalidated_plan_rejection(plan_root: Path, monkeypatch) -> None:
    with pytest.raises(runner.RunnerError, match="INVALIDATED_PLAN_REJECTED"):
        runner.reject_invalidated_plan(
            runner.INVALIDATED_PLAN_PACKAGE_ID, runner.INVALIDATED_PLAN_FINGERPRINT
        )


def test_fingerprint_mismatch_rejection(plan_root: Path) -> None:
    with pytest.raises(runner.RunnerError, match="PLAN_FINGERPRINT_MISMATCH"):
        runner.reject_invalidated_plan(runner.CORRECTED_PLAN_PACKAGE_ID, "b" * 64)


def test_candidate_mismatch_rejection() -> None:
    with pytest.raises(runner.RunnerError, match="candidate"):
        runner.empirical_run_confirmation(
            plan_package_id=runner.CORRECTED_PLAN_PACKAGE_ID,
            plan_fingerprint=runner.CORRECTED_PLAN_FINGERPRINT,
            candidate_id="some-other-candidate", output_root="C:/tmp",
            min_free_bytes=1, max_output_bytes=1, confirmed=True,
        )


def test_confirmation_requires_explicit_flag() -> None:
    with pytest.raises(runner.RunnerError, match="explicit development-evaluation confirmation"):
        runner.empirical_run_confirmation(
            plan_package_id=runner.CORRECTED_PLAN_PACKAGE_ID,
            plan_fingerprint=runner.CORRECTED_PLAN_FINGERPRINT,
            candidate_id="phase6-frozen-v1", output_root="C:/tmp",
            min_free_bytes=1, max_output_bytes=1, confirmed=False,
        )


def test_confirmation_binds_corrected_plan() -> None:
    with pytest.raises(runner.RunnerError, match="corrected plan identity"):
        runner.empirical_run_confirmation(
            plan_package_id="evidence-development_evaluation_plan-v1-wrong",
            plan_fingerprint=runner.CORRECTED_PLAN_FINGERPRINT, candidate_id="phase6-frozen-v1",
            output_root="C:/tmp", min_free_bytes=1, max_output_bytes=1, confirmed=True,
        )


def test_confirmation_fingerprint_mismatch() -> None:
    with pytest.raises(runner.RunnerError, match="corrected plan identity"):
        runner.empirical_run_confirmation(
            plan_package_id=runner.CORRECTED_PLAN_PACKAGE_ID,
            plan_fingerprint="f" * 64, candidate_id="phase6-frozen-v1",
            output_root="C:/tmp", min_free_bytes=1, max_output_bytes=1, confirmed=True,
        )


# ---------------------------------------------------------------------------
# Date/holdout firewall
# ---------------------------------------------------------------------------


def test_holdout_timestamp_rejection() -> None:
    with pytest.raises(runner.RunnerError, match="HOLDOUT_TIMESTAMP"):
        runner.enforce_date_firewall({"timestamp": "2025-01-01T00:00:00+00:00"})


def test_naive_timestamp_rejection() -> None:
    with pytest.raises(runner.RunnerError, match="naive timestamp"):
        runner.enforce_date_firewall({"timestamp": "2024-06-01T00:00:00"})


def test_out_of_interval_rejection() -> None:
    with pytest.raises(runner.RunnerError, match="INTERVAL_OUTSIDE_PLAN"):
        runner.enforce_date_firewall({"timestamp": "2023-12-31T23:59:59+00:00"})


def test_missing_timestamp_rejection() -> None:
    with pytest.raises(runner.RunnerError, match="lacks a timestamp"):
        runner.enforce_date_firewall({"price": 2030.0})


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def test_stream_chronology_inversion(tmp_path: Path) -> None:
    path = tmp_path / "inverted.jsonl"
    base = datetime(2024, 2, 1, tzinfo=UTC)
    records = []
    for index in (0, 2, 1):
        moment = base + timedelta(minutes=index)
        records.append({"timestamp": moment.isoformat(), "record_id": f"r-{index}", "sequence": index})
    path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n")
    stream = runner.BoundedJsonlStream(path, batch_size=2)
    with pytest.raises(runner.RunnerError, match="CHRONOLOGY_INVERSION"):
        list(stream.batches())


def test_stream_duplicate_rejection(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.jsonl"
    moment = datetime(2024, 2, 1, tzinfo=UTC)
    record = {"timestamp": moment.isoformat(), "record_id": "same", "sequence": 1}
    path.write_text(json.dumps(record) + "\n" + json.dumps(record) + "\n")
    stream = runner.BoundedJsonlStream(path, batch_size=10)
    with pytest.raises(runner.RunnerError, match="DUPLICATE_RECORD_ID"):
        list(stream.batches())


def test_stream_duplicate_across_batch_boundary(tmp_path: Path) -> None:
    path = tmp_path / "duplicate_span.jsonl"
    base = datetime(2024, 2, 1, tzinfo=UTC)
    lines = []
    for index in range(3):
        moment = base + timedelta(minutes=index)
        lines.append(json.dumps({"timestamp": moment.isoformat(), "record_id": f"r-{index}"}))
    lines.append(lines[2])  # duplicate of the last record of batch one
    path.write_text("\n".join(lines) + "\n")
    stream = runner.BoundedJsonlStream(path, batch_size=3)
    with pytest.raises(runner.RunnerError, match="DUPLICATE_RECORD_ID"):
        list(stream.batches())


def test_stream_corrupt_record(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.jsonl"
    path.write_text("{not json\n")
    stream = runner.BoundedJsonlStream(path, batch_size=10)
    with pytest.raises(runner.RunnerError, match="CORRUPT_RECORD"):
        list(stream.batches())


def test_stream_bounded_batches(tmp_path: Path, synthetic_stream: Path) -> None:
    stream = runner.BoundedJsonlStream(synthetic_stream, batch_size=5)
    batches = list(stream.batches())
    assert [len(records) for _, records in batches] == [5, 5, 2]
    assert batches[0][1][0]["record_id"] == "synthetic-000"
    assert batches[-1][0].offset == 12


def test_stream_missing_source(tmp_path: Path) -> None:
    with pytest.raises(runner.RunnerError, match="stream source missing"):
        runner.BoundedJsonlStream(tmp_path / "absent.jsonl")


# ---------------------------------------------------------------------------
# Cells / plan-driven preparation
# ---------------------------------------------------------------------------


def test_plan_defines_exactly_64_cells(runner_context: runner.RunnerContext) -> None:
    cells = runner.required_cells(runner_context.plan)
    assert len(cells) == 64
    assert len({cell["cell_id"] for cell in cells}) == 64


def test_scenario_for_cell_unknown(runner_context: runner.RunnerContext) -> None:
    cell = dict(runner_context.plan["scenario_cell_contract"]["cells"][0])
    cell["scenario"] = {"scenario_id": "unregistered"}
    with pytest.raises(runner.RunnerError, match="UNREGISTERED_SCENARIO"):
        runner.scenario_for_cell(runner_context.plan, cell)


# ---------------------------------------------------------------------------
# Cell execution, journal, checkpoint/resume
# ---------------------------------------------------------------------------


def _make_cell_runner(runner_context, cell, tmp_path: Path, name: str) -> runner.CellRunner:
    return runner.CellRunner(
        cell=cell, output_dir=tmp_path / "cells" / name / cell["cell_id"],
        plan_fingerprint=runner.CORRECTED_PLAN_FINGERPRINT,
        seed=8001, deterministic_order="UTC_TIMESTAMP_THEN_STABLE_ROW_AND_ACTION_ID",
    )


def test_cell_run_complete(
    runner_context: runner.RunnerContext, tmp_path: Path, synthetic_stream: Path,
) -> None:
    cell = runner_context.plan["scenario_cell_contract"]["cells"][0]
    cell_runner = _make_cell_runner(runner_context, cell, tmp_path, "a")
    result = cell_runner.run_cell(
        stream_path=synthetic_stream, setup_state=None,
        cost_overlay={}, metadata_overlay={}, empirical_confirmation=None,
    )
    assert result["state"] == "COMPLETE"
    snapshot = json.loads((Path(result_out(tmp_path, "a", cell)) / "checkpoint.json").read_text())
    assert snapshot["state"] == "COMPLETE"
    assert snapshot["checkpoint"]["prerequisites"] == {
        name: True for name in runner.matrix_module.COMPLETION_PREREQUISITES
    }


def result_out(tmp_path: Path, name: str, cell: dict) -> Path:
    return tmp_path / "cells" / name / cell["cell_id"]


def test_completed_cell_cannot_be_silently_rerun(
    runner_context: runner.RunnerContext, tmp_path: Path, synthetic_stream: Path,
) -> None:
    cell = runner_context.plan["scenario_cell_contract"]["cells"][0]
    cell_runner = _make_cell_runner(runner_context, cell, tmp_path, "a")
    cell_runner.run_cell(stream_path=synthetic_stream, setup_state=None,
                         cost_overlay={}, metadata_overlay={}, empirical_confirmation=None)
    with pytest.raises(runner.RunnerError, match="already terminal"):
        cell_runner.run_cell(stream_path=synthetic_stream, setup_state=None,
                             cost_overlay={}, metadata_overlay={}, empirical_confirmation=None)


def test_journal_chain_tamper_detection(
    runner_context: runner.RunnerContext, tmp_path: Path, synthetic_stream: Path,
) -> None:
    cell = runner_context.plan["scenario_cell_contract"]["cells"][0]
    cell_runner = _make_cell_runner(runner_context, cell, tmp_path, "a")
    cell_runner.run_cell(stream_path=synthetic_stream, setup_state=None,
                         cost_overlay={}, metadata_overlay={}, empirical_confirmation=None)
    journal_path = result_out(tmp_path, "a", cell) / "journal.jsonl"
    lines = journal_path.read_text().splitlines()
    entry = json.loads(lines[1])
    entry["payload"]["cursor"] = "TAMPERED"
    lines[1] = json.dumps(entry)
    journal_path.write_text("\n".join(lines) + "\n")
    with pytest.raises(runner.RunnerError, match="JOURNAL_(CHAIN_BROKEN|ENTRY_TAMPERED)"):
        runner.HashChainedJournal(journal_path)


def test_corrupt_checkpoint_rejected(
    runner_context: runner.RunnerContext, tmp_path: Path, synthetic_stream: Path,
) -> None:
    cell = runner_context.plan["scenario_cell_contract"]["cells"][0]
    cell_runner = _make_cell_runner(runner_context, cell, tmp_path, "a")
    cell_runner.run_cell(stream_path=synthetic_stream, setup_state=None,
                         cost_overlay={}, metadata_overlay={}, empirical_confirmation=None)
    (result_out(tmp_path, "a", cell) / "checkpoint.json").write_text("{corrupt")
    with pytest.raises(runner.RunnerError, match="CORRUPT_CHECKPOINT"):
        cell_runner.current_state()


def test_checkpoint_journal_mismatch_blocks_resume(
    runner_context: runner.RunnerContext, tmp_path: Path, synthetic_stream: Path,
) -> None:
    cell = runner_context.plan["scenario_cell_contract"]["cells"][0]
    cell_runner = _make_cell_runner(runner_context, cell, tmp_path, "a")
    cell_runner.run_cell(stream_path=synthetic_stream, setup_state=None,
                         cost_overlay={}, metadata_overlay={}, empirical_confirmation=None)
    forged = json.loads((result_out(tmp_path, "a", cell) / "checkpoint.json").read_text())
    forged["state"] = "CHECKPOINTED"
    (result_out(tmp_path, "a", cell) / "checkpoint.json").write_text(json.dumps(forged))
    with pytest.raises(runner.RunnerError, match="journal"):
        cell_runner.resume_cell(stream_path=synthetic_stream, cost_overlay={}, metadata_overlay={})


def test_wrong_cell_checkpoint_blocks_resume(
    runner_context: runner.RunnerContext, tmp_path: Path, synthetic_stream: Path,
) -> None:
    cell_a = runner_context.plan["scenario_cell_contract"]["cells"][0]
    cell_b = runner_context.plan["scenario_cell_contract"]["cells"][1]
    out = tmp_path / "cells" / "a" / cell_a["cell_id"]
    runner_a = runner.CellRunner(cell=cell_a, output_dir=out,
                                 plan_fingerprint=runner.CORRECTED_PLAN_FINGERPRINT,
                                 seed=8001, deterministic_order="UTC")
    runner_a.run_cell(stream_path=synthetic_stream, setup_state=None,
                      cost_overlay={}, metadata_overlay={}, empirical_confirmation=None)
    snapshot = json.loads((out / "checkpoint.json").read_text())
    snapshot["state"] = "CHECKPOINTED"
    snapshot["cell_id"] = cell_b["cell_id"]
    (out / "checkpoint.json").write_text(json.dumps(snapshot))
    with pytest.raises(runner.RunnerError, match="different cell"):
        runner_a.resume_cell(stream_path=synthetic_stream, cost_overlay={}, metadata_overlay={})


def test_cell_refuses_open_plan_gate(
    runner_context: runner.RunnerContext, tmp_path: Path, synthetic_plan: dict,
    synthetic_stream: Path,
) -> None:
    plan = dict(synthetic_plan)
    plan["gates"] = {**plan["gates"], "empirical_strategy_evaluation_executed": True}
    cell = plan["scenario_cell_contract"]["cells"][0]
    cell_runner = _make_cell_runner(runner_context, cell, tmp_path, "a")
    with pytest.raises(runner.RunnerError, match="gate"):
        cell_runner.verify_prerequisites(plan)


def test_empirical_confirmation_binds_plan_identity(
    runner_context: runner.RunnerContext, tmp_path: Path, synthetic_stream: Path,
) -> None:
    cell = runner_context.plan["scenario_cell_contract"]["cells"][0]
    cell_runner = _make_cell_runner(runner_context, cell, tmp_path, "a")
    with pytest.raises(runner.RunnerError, match="confirmation does not bind"):
        cell_runner.run_cell(
            stream_path=synthetic_stream, setup_state=None,
            cost_overlay={}, metadata_overlay={},
            empirical_confirmation={"empirical_execution": True, "plan_package_id": "wrong"},
        )


# ---------------------------------------------------------------------------
# Determinism / resume equivalence
# ---------------------------------------------------------------------------


def test_deterministic_cell_outputs(
    runner_context: runner.RunnerContext, tmp_path: Path, synthetic_stream: Path,
) -> None:
    from bot.acquisition.evidence_contracts import canonical_hash

    cell = runner_context.plan["scenario_cell_contract"]["cells"][0]
    digests = []
    for index in ("a", "b"):
        out = tmp_path / "cells" / index / cell["cell_id"]
        cell_runner = runner.CellRunner(cell=cell, output_dir=out,
                                        plan_fingerprint=runner.CORRECTED_PLAN_FINGERPRINT,
                                        seed=8001, deterministic_order="UTC")
        cell_runner.run_cell(stream_path=synthetic_stream, setup_state=None,
                             cost_overlay={}, metadata_overlay={}, empirical_confirmation=None)
        digests.append(canonical_hash(json.loads((out / "checkpoint.json").read_text())))
    assert digests[0] == digests[1]


# ---------------------------------------------------------------------------
# Result contract / publication
# ---------------------------------------------------------------------------


def _write_full_contract(publisher: runner.RunOutputPublisher, plan: dict) -> None:
    publisher.write("run_manifest.json", {"schema": runner.RUNNER_SCHEMA, "synthetic": True,
                                          "plan_fingerprint": plan["plan_fingerprint"]})
    for name in ("cells", "cell_manifests", "decision_ledger", "fills", "trade_ledger",
                 "equity_curve", "costs", "circuits"):
        publisher.write(name + ".jsonl", [])
    for name in ("fold_metrics", "scenario_metrics", "aggregate_metrics",
                 "bootstrap_results", "acceptance_table", "reconciliation_report", "run_summary"):
        publisher.write(name + ".json", {"synthetic": True})
    publisher.write("RUN_COMPLETE", "SYNTHETIC REHEARSAL COMPLETE\n")


def test_publisher_non_overwrite(tmp_path: Path, synthetic_plan: dict) -> None:
    root = tmp_path / "results"
    publisher = runner.RunOutputPublisher(root)
    publisher.begin()
    _write_full_contract(publisher, synthetic_plan)
    publisher.commit()
    with pytest.raises(runner.RunnerError, match="non-overwrite"):
        runner.RunOutputPublisher(root).begin()


def test_publisher_duplicate_write_rejected(tmp_path: Path) -> None:
    publisher = runner.RunOutputPublisher(tmp_path / "results")
    publisher.begin()
    publisher.write("run_manifest.json", {"synthetic": True})
    with pytest.raises(runner.RunnerError, match="duplicate output file"):
        publisher.write("run_manifest.json", {"synthetic": True})


def test_publisher_incomplete_contract_rejected(tmp_path: Path) -> None:
    publisher = runner.RunOutputPublisher(tmp_path / "results")
    publisher.begin()
    publisher.write("run_manifest.json", {"synthetic": True})
    with pytest.raises(runner.RunnerError, match="result contract incomplete"):
        publisher.commit()


def test_verify_results_requires_complete_contract(tmp_path: Path) -> None:
    with pytest.raises(runner.RunnerError, match="output directory missing"):
        runner.verify_results(tmp_path / "absent")


def test_verify_results_detects_cell_disagreement(
    runner_context: runner.RunnerContext, tmp_path: Path,
) -> None:
    outcome = runner.synthetic_rehearsal(runner_context, root=tmp_path / "rehearsal", batch_size=7)
    published = Path(outcome["published"])
    lines = (published / "cells.jsonl").read_text().splitlines()
    lines = lines[:-1]  # drop one cell: 63 of 64
    (published / "cells.jsonl").write_text("\n".join(lines) + "\n")
    with pytest.raises(runner.RunnerError, match="exactly 64 cells"):
        runner.verify_results(published)


def test_full_rehearsal_result_contract(
    runner_context: runner.RunnerContext, tmp_path: Path,
) -> None:
    outcome = runner.synthetic_rehearsal(runner_context, root=tmp_path / "rehearsal", batch_size=7)
    assert outcome["cells"] == 64
    assert outcome["interruption_resume_equivalence"] is True
    assert outcome["rerun_suppression"] is True
    published = Path(outcome["published"])
    result = runner.verify_results(published)
    assert result["verified"] is True and result["cells"] == 64
    assert result["synthetic"] is True
    manifest = json.loads((published / "run_manifest.json").read_text())
    assert manifest["empirical_strategy_evaluation_executed"] is False
    assert manifest["holdout_access_authorized"] is False
    assert manifest["accepted_for_final_validation"] is False


def test_run_summary_gates_false(runner_context: runner.RunnerContext, tmp_path: Path) -> None:
    outcome = runner.synthetic_rehearsal(runner_context, root=tmp_path / "rehearsal-2", batch_size=7)
    published = Path(outcome["published"])
    summary = json.loads((published / "run_summary.json").read_text())
    assert summary["empirical_execution"] is False
    assert summary["plan_fingerprint"] == runner.CORRECTED_PLAN_FINGERPRINT


# ---------------------------------------------------------------------------
# Resource guards
# ---------------------------------------------------------------------------


def test_low_disk_rejection(runner_context: runner.RunnerContext) -> None:
    estimate = runner.estimate_resources(runner_context)
    starved = dict(estimate)
    starved["available_free_bytes"] = runner.DEFAULT_MIN_FREE_BYTES - 1
    starved["sufficient"] = False
    with pytest.raises(runner.RunnerError, match="LOW_DISK"):
        runner.enforce_resource_guards(runner_context, starved)


def test_output_limit_rejection(runner_context: runner.RunnerContext) -> None:
    estimate = runner.estimate_resources(runner_context)
    oversized = dict(estimate)
    oversized["projected_output_bytes_upper_bound"] = runner.DEFAULT_MAX_OUTPUT_BYTES + 1
    with pytest.raises(runner.RunnerError, match="output limit"):
        runner.enforce_resource_guards(runner_context, oversized)


# ---------------------------------------------------------------------------
# Firewall registry / safety
# ---------------------------------------------------------------------------


def test_firewall_registry_documents_rejections() -> None:
    categories = dict(runner.firewall_rejections())
    for required in (
        "CHANGED_HASH", "MISSING_COMPLETION_MARKER", "WRONG_CANDIDATE",
        "INVALIDATED_PLAN", "LEGACY_RESULT_INPUT", "UNREGISTERED_SCENARIO",
        "INTERVAL_OUTSIDE_PLAN", "HOLDOUT_TIMESTAMP", "HOLDOUT_PATH",
        "LIVE_BROKER_SUBSTITUTION",
    ):
        assert required in categories


def test_no_mt5_or_network_imports() -> None:
    source = (REPO_ROOT / "bot" / "validation" / "development_evaluation_runner.py").read_text()
    for prohibited in ("MetaTrader5", "mt5", "requests", "urllib", "socket", "keyring"):
        assert prohibited not in source
    module = importlib.reload(runner)
    assert not hasattr(module, "MetaTrader5")
