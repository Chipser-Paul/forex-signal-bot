"""Tests for Phase 8 V2 Tier-B Feasibility Plan preregistration (phase8-v2-tierb-feasibility-plan-v1).

Covers Research Charter §15, §17 and Section 53 requirements:
1. plan JSON parses and validates against declared schema phase8v2.tierb-feasibility-plan.v1;
2. candidate binding matches phase6-frozen-v2 at 2fd3460b9010d8cca548f4fd6980b6b34fe594e2 with TC003 manifest and all four invariant digests;
3. authoritative ledger seal is phase8-v2-ledger-seal-v2 and contains 0 unresolved entities;
4. reserved folds sequence is strictly ['fold-02', 'fold-03', 'fold-04'] with supervisory stop;
5. Stage 1 futility threshold is exactly 30; headroom target is exactly 60 and non-gating;
6. Stage 2 completed-trade minimum is exactly 30; unit of application is strictly per-fold / PRIMARY_BASELINE only;
7. PRIMARY_BASELINE scenario components match registered IDs: swap SWAP_EMAIL_REFERENCE, slippage SLIPPAGE_MODERATE_ADVERSE, metadata BASELINE_CURRENT_REFERENCE_PROXY;
8. END_OF_DATA_FORCED_CLOSE_EXCLUDED_FROM_SAMPLE is excluded from the completed-trade count;
9. non-completed states (CANCELLED, EXPIRED, REJECTED, unfilled, untriggered) excluded;
10. cross-fold empirical lookahead and position carryover into next fold are strictly prohibited;
11. profitability fields and summary metrics are strictly prohibited;
12. mandatory Fold-01 rehearsals (candidate parity 102/81/21 and lifecycle mechanics) are registered;
13. plan content SHA-256 matches canonical computation;
14. register record phase8-v2-tierb-feasibility-plan-v1 exists and is consistent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = REPO_ROOT / "baseline" / "phase8_v2_tierb_feasibility_plan.json"
DOC_PATH = REPO_ROOT / "docs" / "PHASE8_V2_TIERB_FEASIBILITY_PLAN.md"
REGISTER_PATH = REPO_ROOT / "baseline" / "phase8_v2_hypothesis_register.json"
MANIFEST_TC003_PATH = REPO_ROOT / "baseline" / "phase8_v2_frozen_candidate_manifest_tc003.json"

EXPECTED_PLAN_ID = "phase8-v2-tierb-feasibility-plan-v1"
EXPECTED_SCHEMA_VERSION = "phase8v2.tierb-feasibility-plan.v1"
EXPECTED_PLAN_CONTENT_SHA256 = (
    "d42d7392cc124b3d8ab09a6212aa29038317fd93ae5d486b24d72904eddea1c9"
)
EXPECTED_ANCHOR_COMMIT = "2fd3460b9010d8cca548f4fd6980b6b34fe594e2"
EXPECTED_STRATEGY_DIGEST = (
    "ec4b5e6e6ded4797fce2d4d841d1b746e15f7435ac50569c62d6daa38953064f"
)
EXPECTED_CONFIG_SHA256 = (
    "1aa8b73fb207e10abfe9725bc2979e14692815a5ffe91502cef892b8bae6e806"
)
EXPECTED_VALIDATION_DIGEST = (
    "957dba56e2244b8cae773ddc17c716da629732d3f492e77578978ef9e091da3f"
)
EXPECTED_PROTECTED_DIGEST_V2 = (
    "666be323da1f5634e00d5a3285089d9318c99b300696d1f621db4d2cf07f9d7d"
)
EXPECTED_LEDGER_SEAL = "phase8-v2-ledger-seal-v2"

PROHIBITED_METRICS_LIST = [
    "profit_and_loss",
    "net_profit",
    "gross_profit",
    "gross_loss",
    "win_rate",
    "profit_factor",
    "expectancy",
    "sharpe_ratio",
    "sortino_ratio",
    "returns_pct",
    "equity_curve",
    "drawdown_monetary",
    "drawdown_pct",
    "avg_winner",
    "avg_loser",
    "r_multiple_profitability",
]


@pytest.fixture(scope="module")
def plan_data() -> dict:
    assert PLAN_PATH.is_file(), f"Feasibility plan missing: {PLAN_PATH}"
    with open(PLAN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def register_data() -> dict:
    assert REGISTER_PATH.is_file(), f"Hypothesis register missing: {REGISTER_PATH}"
    with open(REGISTER_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def manifest_tc003_data() -> dict:
    assert MANIFEST_TC003_PATH.is_file(), f"TC003 manifest missing: {MANIFEST_TC003_PATH}"
    with open(MANIFEST_TC003_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_plan_json_parses_and_validates_schema(plan_data: dict) -> None:
    """1. Plan JSON parses and validates against declared schema phase8v2.tierb-feasibility-plan.v1."""
    assert plan_data["plan_id"] == EXPECTED_PLAN_ID
    assert plan_data["schema_version"] == EXPECTED_SCHEMA_VERSION
    assert "PROSPECTIVE_RESERVED_DEVELOPMENT_FEASIBILITY" in plan_data["classification"]
    assert "NOT_PROFITABILITY_EVIDENCE" in plan_data["classification"]
    assert plan_data["zero_empirical_access"] is True
    assert plan_data["budget_impact"] == 0
    assert plan_data["prospective_contract"] == "canonical_git_blob_v1"


def test_plan_canonical_content_sha256(plan_data: dict) -> None:
    """Plan canonical content SHA-256 matches exact hash computation."""
    content_copy = {k: v for k, v in plan_data.items() if k != "plan_content_sha256"}
    rendered_core = json.dumps(content_copy, sort_keys=True, separators=(",", ":"))
    computed_sha = hashlib.sha256(rendered_core.encode("utf-8")).hexdigest()
    assert computed_sha == EXPECTED_PLAN_CONTENT_SHA256
    assert plan_data["plan_content_sha256"] == EXPECTED_PLAN_CONTENT_SHA256


def test_candidate_binding_matches_frozen_v2(plan_data: dict, manifest_tc003_data: dict) -> None:
    """2. Candidate binding matches phase6-frozen-v2 at anchor commit with TC003 manifest and 4 digests."""
    binding = plan_data["frozen_candidate_binding"]
    assert binding["freeze_identity"] == "phase6-frozen-v2"
    assert binding["development_predecessor"] == "phase6-development-v2-V005"
    assert binding["semantic_anchor_commit"] == EXPECTED_ANCHOR_COMMIT
    assert binding["authoritative_freeze_manifest"] == "baseline/phase8_v2_frozen_candidate_manifest_tc003.json"
    assert binding["strategy_semantic_aggregate_digest"] == EXPECTED_STRATEGY_DIGEST
    assert binding["complete_candidate_configuration_sha256"] == EXPECTED_CONFIG_SHA256
    assert binding["validation_pipeline_aggregate_digest"] == EXPECTED_VALIDATION_DIGEST
    assert binding["protected_infrastructure_aggregate_digest_v2"] == EXPECTED_PROTECTED_DIGEST_V2
    assert binding["charter_section_5_controls_count"] == 18

    # Parity with TC003 manifest itself
    tc003_semantic = manifest_tc003_data["strategy_semantic_identity_v2"]
    assert tc003_semantic["commit"] == EXPECTED_ANCHOR_COMMIT
    assert tc003_semantic["aggregate_digest"] == EXPECTED_STRATEGY_DIGEST
    assert manifest_tc003_data["validation_pipeline_identity_v1"]["aggregate_digest"] == EXPECTED_VALIDATION_DIGEST
    assert manifest_tc003_data["protected_infrastructure_identity_v2"]["aggregate_digest"] == EXPECTED_PROTECTED_DIGEST_V2
    assert manifest_tc003_data["configuration_identity"]["complete_candidate_configuration_identity"] == EXPECTED_CONFIG_SHA256
    assert manifest_tc003_data["historical_tc001_reference"]["strategy_digest"] == EXPECTED_STRATEGY_DIGEST


def test_authoritative_ledger_seal_binding(plan_data: dict, register_data: dict) -> None:
    """3. Authoritative ledger seal is phase8-v2-ledger-seal-v2 and contains 0 unresolved entities."""
    binding = plan_data["frozen_candidate_binding"]
    assert binding["authoritative_ledger_seal"] == EXPECTED_LEDGER_SEAL
    assert binding["unresolved_entities_count"] == 0

    # Verify against actual ledger seal record in register
    ledger_seals = [
        r for r in register_data.get("result_records", [])
        if r.get("record_id") == EXPECTED_LEDGER_SEAL
    ]
    assert len(ledger_seals) == 1
    seal = ledger_seals[0]
    assert seal["unresolved_entities_count"] == 0
    assert seal["attestation"] == "ALL_OPENED_SCIENTIFIC_ENTITIES_TERMINALLY_RESOLVED"


def test_reserved_folds_sequence_and_release_protocol(plan_data: dict) -> None:
    """4. Reserved folds sequence is strictly ['fold-02', 'fold-03', 'fold-04'] with supervisory stop."""
    protocol = plan_data["evidence_release_protocol"]
    assert protocol["reserved_folds_sequence"] == ["fold-02", "fold-03", "fold-04"]
    assert protocol["release_order"] == "STRICT_SEQUENTIAL"
    assert protocol["supervisory_stop_between_folds"] is True
    assert protocol["contamination_record_required_before_read"] is True


def test_stage_1_raw_candidate_protocol_thresholds(plan_data: dict) -> None:
    """5. Stage 1 futility threshold is exactly 30; headroom target is exactly 60 and non-gating."""
    stage1 = plan_data["stage_1_raw_candidate_protocol"]
    assert stage1["replay_type"] == "SCENARIO_INDEPENDENT_STRUCTURAL_ONLY"
    assert stage1["fills_or_costs_evaluated"] is False
    assert stage1["futility_threshold"] == 30
    assert stage1["futility_classification"] == "SAMPLE_SIZE_FUTILITY"
    assert stage1["headroom_target"] == 60
    assert stage1["headroom_gating"] is False
    assert stage1["headroom_target_met_label"] == "RESERVED_FOLD_RAW_HEADROOM_TARGET_MET"
    assert stage1["headroom_target_not_met_label"] == "RESERVED_FOLD_RAW_HEADROOM_TARGET_NOT_MET"


def test_stage_2_lifecycle_completed_trade_threshold(plan_data: dict) -> None:
    """6. Stage 2 completed-trade minimum is exactly 30; unit of application is per-fold / PRIMARY_BASELINE only."""
    stage2 = plan_data["stage_2_lifecycle_sample_protocol"]
    assert stage2["min_completed_trades_per_reserved_fold"] == 30
    assert stage2["unit_of_application"] == "PER_RESERVED_FOLD_PRIMARY_BASELINE_ONLY"
    assert stage2["cross_fold_aggregation_permitted"] is False
    assert stage2["cross_scenario_aggregation_permitted"] is False
    assert stage2["sensitivity_or_worst_case_matrix_in_feasibility"] is False
    assert stage2["pass_classification"] == "RESERVED_FOLD_SAMPLE_FEASIBILITY_PASS"
    assert stage2["failure_classification"] == "LIFECYCLE_SAMPLE_INSUFFICIENT"


def test_primary_baseline_scenario_components(plan_data: dict) -> None:
    """7. PRIMARY_BASELINE scenario components match registered IDs."""
    primary = plan_data["stage_2_lifecycle_sample_protocol"]["primary_baseline_scenario"]
    assert primary["scenario_name"] == "PRIMARY_BASELINE"
    assert primary["swap_component"] == "SWAP_EMAIL_REFERENCE"
    assert primary["slippage_component"] == "SLIPPAGE_MODERATE_ADVERSE"
    assert primary["metadata_component"] == "BASELINE_CURRENT_REFERENCE_PROXY"


def test_end_of_data_excluded_from_qualifying_sample(plan_data: dict) -> None:
    """8. END_OF_DATA_FORCED_CLOSE_EXCLUDED_FROM_SAMPLE is excluded from the completed-trade count."""
    boundary = plan_data["fold_boundary_contract"]
    assert boundary["end_of_data_position_classification"] == "END_OF_DATA_FORCED_CLOSE_EXCLUDED_FROM_SAMPLE"
    assert boundary["end_of_data_counts_toward_threshold"] is False
    assert boundary["pending_intents_at_fold_end_counted"] is False

    completed_def = plan_data["completed_trade_definition"]
    assert "END_OF_DATA_FORCED_CLOSE_EXCLUDED_FROM_SAMPLE" in completed_def["non_completed_states_excluded"]


def test_non_completed_states_excluded(plan_data: dict) -> None:
    """9. Non-completed states (CANCELLED, EXPIRED, REJECTED, unfilled, untriggered) excluded."""
    excluded = set(plan_data["completed_trade_definition"]["non_completed_states_excluded"])
    mandatory_excluded = {
        "CANCELLED",
        "EXPIRED",
        "REJECTED",
        "UNFILLED_INTENT",
        "UNTRIGGERED_INTENT",
        "NEVER_OPENED",
        "PARTIALLY_CLOSED_WITHOUT_FINAL_CLOSE",
        "DUPLICATE_LIFECYCLE_EVENT",
        "END_OF_DATA_FORCED_CLOSE_EXCLUDED_FROM_SAMPLE",
    }
    for state in mandatory_excluded:
        assert state in excluded, f"State {state} must be excluded from completed-trade count"


def test_cross_fold_lookahead_and_carryover_prohibited(plan_data: dict) -> None:
    """10. Cross-fold empirical lookahead and position carryover into next fold are strictly prohibited."""
    boundary = plan_data["fold_boundary_contract"]
    assert boundary["cross_fold_empirical_lookahead_permitted"] is False
    assert boundary["position_carry_into_next_fold_permitted"] is False
    assert boundary["prior_fold_historical_causal_warmup_permitted"] is True


def test_profitability_metrics_strictly_prohibited(plan_data: dict) -> None:
    """11. Profitability fields and summary metrics are strictly prohibited."""
    prohibited = plan_data.get("prohibited_metrics", [])
    for metric in PROHIBITED_METRICS_LIST:
        assert metric in prohibited, f"Metric {metric} must be explicitly prohibited"

    # Scan entire JSON for any unauthorized profitability keys
    banned_substrings = [
        "sharpe", "sortino", "pnl", "profit", "win_rate",
        "expectancy", "drawdown", "equity_curve", "r_multiple"
    ]
    def _scan(obj: object, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k not in ("prohibited_metrics", "description", "classification", "banned_output_guard", "prohibitions"):
                    for b in banned_substrings:
                        assert b not in k.lower(), f"Banned metric token '{b}' found in plan key: {path}.{k}"
                _scan(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                _scan(item, f"{path}[{idx}]")

    _scan(plan_data)


def test_mandatory_fold01_rehearsals_registered(plan_data: dict) -> None:
    """12. Mandatory Fold-01 rehearsals (candidate parity 102/81/21 and lifecycle mechanics) registered."""
    rehearsals = plan_data["rehearsal_requirements"]
    assert rehearsals["fold01_parity_rehearsal_required"] is True
    assert rehearsals["required_fold01_candidate_count"] == 102
    assert rehearsals["required_fold01_v003_baseline_count"] == 81
    assert rehearsals["required_fold01_v005_fallback_count"] == 21
    assert rehearsals["required_fold01_unique_setups"] == 102
    assert rehearsals["required_fold01_duplicates"] == 0
    assert rehearsals["fold01_lifecycle_mechanics_rehearsal_required"] is True
    assert rehearsals["fold01_rehearsal_counts_toward_tier_b"] is False
    assert rehearsals["tuning_during_rehearsal_permitted"] is False


def test_hypothesis_register_plan_record(register_data: dict) -> None:
    """14. Register record phase8-v2-tierb-feasibility-plan-v1 exists and is consistent."""
    records = [
        r for r in register_data.get("result_records", [])
        if r.get("plan_id") == EXPECTED_PLAN_ID
    ]
    assert len(records) == 1, f"Expected 1 plan record for {EXPECTED_PLAN_ID}, found {len(records)}"
    record = records[0]
    assert record["record_type"] == "PROSPECTIVE_RESERVED_DEVELOPMENT_FEASIBILITY_PLAN_PREREGISTRATION"
    assert record["plan_content_sha256"] == EXPECTED_PLAN_CONTENT_SHA256
    assert record["plan_file"] == "baseline/phase8_v2_tierb_feasibility_plan.json"
    assert record["plan_doc"] == "docs/PHASE8_V2_TIERB_FEASIBILITY_PLAN.md"
    assert record["stage_1_raw_futility_threshold"] == 30
    assert record["stage_1_raw_headroom_target"] == 60
    assert record["stage_2_min_completed_trades_per_fold"] == 30
    assert record["stage_2_primary_scenario"] == "PRIMARY_BASELINE"
    assert record["end_of_data_excluded_from_sample"] is True
    assert record["mandatory_fold01_parity_rehearsal_required"] is True
    assert record["zero_empirical_access"] is True
    assert record["budget_impact"] == 0
    assert "TIER_B_PLAN_PREREGISTERED" in record["tier_b_status"]
    assert "EMPIRICAL_RELEASE_NOT_AUTHORIZED" in record["tier_b_status"]


def test_feasibility_plan_documentation_exists_and_binds_sha() -> None:
    """Plan documentation docs/PHASE8_V2_TIERB_FEASIBILITY_PLAN.md exists and contains SHA."""
    assert DOC_PATH.is_file(), f"Document missing: {DOC_PATH}"
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    assert EXPECTED_PLAN_ID in doc_text
    assert EXPECTED_PLAN_CONTENT_SHA256 in doc_text
    assert EXPECTED_ANCHOR_COMMIT in doc_text
    assert EXPECTED_STRATEGY_DIGEST in doc_text
    assert EXPECTED_CONFIG_SHA256 in doc_text
    assert EXPECTED_VALIDATION_DIGEST in doc_text
    assert EXPECTED_PROTECTED_DIGEST_V2 in doc_text
    assert "SAMPLE_SIZE_FUTILITY" in doc_text
    assert "LIFECYCLE_SAMPLE_INSUFFICIENT" in doc_text
    assert "END_OF_DATA_FORCED_CLOSE_EXCLUDED_FROM_SAMPLE" in doc_text
