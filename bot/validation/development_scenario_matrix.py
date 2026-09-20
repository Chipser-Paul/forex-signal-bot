"""Factorized Phase 8N-A scenario composition; no evaluation side effects."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from bot.validation import cost_policy
from bot.validation.development_metadata_bounds import SCENARIO_ORDER
from bot.acquisition.evidence_contracts import canonical_hash


class ScenarioMatrixError(ValueError):
    """A required frozen scenario or fold is missing or inconsistent."""


BASE_SWAP = "SWAP_EMAIL_REFERENCE"
BASE_SLIPPAGE = "SLIPPAGE_MODERATE_ADVERSE"
ADVERSE_SWAP = cost_policy.REQUIRED_ADVERSE_BOUNDARY
ADVERSE_SLIPPAGE = "SLIPPAGE_SEVERE_ADVERSE"
BASE_METADATA = "BASELINE_CURRENT_REFERENCE_PROXY"
WORST_METADATA = "COMBINED_ADVERSE_BROKER_CONDITIONS"


def compose_scenarios(
    swap_ids: Sequence[str], slippage_ids: Sequence[str],
    metadata_ids: Sequence[str], fold_ids: Sequence[str],
) -> dict[str, Any]:
    """Deduplicate by component identity, retaining every group membership."""
    if tuple(swap_ids) != cost_policy.SWAP_SCENARIO_ORDER:
        raise ScenarioMatrixError("frozen swap ladder changed")
    expected_slippage = tuple(item["scenario_id"] for item in cost_policy.SLIPPAGE_SCENARIOS)
    if tuple(slippage_ids) != expected_slippage:
        raise ScenarioMatrixError("frozen slippage ladder changed")
    if tuple(metadata_ids) != SCENARIO_ORDER:
        raise ScenarioMatrixError("frozen metadata ladder changed")
    if tuple(fold_ids) != tuple(f"fold-{index:02d}" for index in range(1, 5)):
        raise ScenarioMatrixError("four frozen chronological folds are required")

    groups = (
        ("PRIMARY_BASELINE", ((BASE_SWAP, BASE_SLIPPAGE, BASE_METADATA),)),
        ("SWAP_SENSITIVITY", tuple((swap, BASE_SLIPPAGE, BASE_METADATA) for swap in swap_ids)),
        ("SLIPPAGE_SENSITIVITY", tuple((BASE_SWAP, slip, BASE_METADATA) for slip in slippage_ids)),
        ("METADATA_STRESS", tuple((ADVERSE_SWAP, ADVERSE_SLIPPAGE, meta) for meta in metadata_ids)),
        ("COMBINED_WORST_CASE", ((ADVERSE_SWAP, ADVERSE_SLIPPAGE, WORST_METADATA),)),
    )
    memberships: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for group, combinations in groups:
        for combination in combinations:
            if group not in memberships[combination]:
                memberships[combination].append(group)

    scenarios = []
    for (swap, slip, metadata), membership in memberships.items():
        scenario_id = "|".join((swap, slip, metadata))
        if "PRIMARY_BASELINE" in membership:
            role = "PRIMARY"
        elif swap == "SWAP_NO_OVERNIGHT_EXPOSURE_DIAGNOSTIC" or slip == "SLIPPAGE_NEUTRAL_DIAGNOSTIC":
            role = "DIAGNOSTIC"
        else:
            role = "MANDATORY_ADVERSE"
        scenarios.append({
            "scenario_id": scenario_id,
            "swap_scenario_id": swap,
            "slippage_scenario_id": slip,
            "metadata_scenario_id": metadata,
            "groups": membership,
            "role": role,
            "spread_source": "OBSERVED_HISTORICAL_BID_ASK",
            "commission_source": "STANDARD_ACCOUNT_NONE_DEVELOPMENT_ONLY",
        })
    cells = [
        {"scenario_id": scenario["scenario_id"], "fold_id": fold}
        for scenario in scenarios for fold in fold_ids
    ]
    return {
        "schema_version": "phase8n.factorized-scenario-matrix.v1",
        "group_order": [name for name, _ in groups],
        "canonical_order": "FIRST_OCCURRENCE_IN_GROUP_ORDER_THEN_REGISTERED_COMPONENT_ORDER",
        "deduplication": "EXACT_SWAP_SLIPPAGE_METADATA_IDENTITY",
        "scenarios": scenarios,
        "unique_scenario_count": len(scenarios),
        "fold_ids": list(fold_ids),
        "required_fold_scenario_cells": cells,
        "required_cell_count": len(cells),
        "all_cells_required": True,
        "cheapest_scenario_selection": "PROHIBITED",
    }


def verify_completed_cells(matrix: Mapping[str, Any], completed: Sequence[Mapping[str, str]]) -> None:
    required = {
        (cell["scenario_id"], cell["fold_id"])
        for cell in matrix["required_fold_scenario_cells"]
    }
    actual = [(cell["scenario_id"], cell["fold_id"]) for cell in completed]
    if len(actual) != len(set(actual)) or set(actual) != required:
        raise ScenarioMatrixError("missing, duplicate, or unexpected fold-scenario cell")


CELL_SCHEMA = "phase8n.scenario-cell-contract.v1"
REQUIRED_BINDINGS = (
    "parent_plan", "candidate", "empirical_adapter", "gate_reducer", "levels_builder",
    "consumption", "restart", "state_migration", "lifecycle_parity", "inputs",
)
COMPLETION_PREREQUISITES = (
    "exact_inputs_verified", "all_events_processed", "consumption_reconciled",
    "lifecycle_reconciled", "risk_reconciled", "ledger_reconciled", "outputs_durable",
)


def build_cell_contract(matrix: Mapping[str, Any], folds: Sequence[Mapping[str, Any]], bindings: Mapping[str, str]) -> dict[str, Any]:
    """Bind the unchanged 16 scenarios/four folds to exact resumable contracts."""
    expected = compose_scenarios(
        cost_policy.SWAP_SCENARIO_ORDER,
        tuple(item["scenario_id"] for item in cost_policy.SLIPPAGE_SCENARIOS),
        SCENARIO_ORDER, tuple(f"fold-{index:02d}" for index in range(1, 5)),
    )
    if dict(matrix) != expected or len(folds) != 4 or tuple(item["fold_id"] for item in folds) != tuple(expected["fold_ids"]):
        raise ScenarioMatrixError("scenario matrix or fold identity changed")
    if set(bindings) != set(REQUIRED_BINDINGS) or any(
            not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            for value in bindings.values()):
        raise ScenarioMatrixError("every frozen component requires a SHA-256 binding")
    cells = []
    for scenario in expected["scenarios"]:
        for fold in folds:
            identity = {
                "schema": CELL_SCHEMA, "scenario": scenario, "fold": dict(fold),
                "bindings": dict(bindings), "lifecycle_consumption_enabled": True,
                "cost_overlay_ids": [scenario["swap_scenario_id"], scenario["slippage_scenario_id"]],
                "metadata_overlay_id": scenario["metadata_scenario_id"],
                "completion_prerequisites": list(COMPLETION_PREREQUISITES),
            }
            fingerprint = canonical_hash(identity)
            cells.append({**identity, "cell_id": "cell_" + fingerprint, "resume_identity": fingerprint})
    return {
        "schema": CELL_SCHEMA, "bindings": dict(bindings), "cells": cells,
        "scenario_count": 16, "fold_count": 4, "cell_count": 64,
        "fingerprint": canonical_hash(cells), "empirical_execution_authorized": False,
    }


def verify_cell_contract(contract: Mapping[str, Any], matrix: Mapping[str, Any], folds: Sequence[Mapping[str, Any]]) -> None:
    expected = build_cell_contract(matrix, folds, contract["bindings"])
    if dict(contract) != expected:
        raise ScenarioMatrixError("cell or resume contract identity mismatch")


def verify_cell_completion(cell: Mapping[str, Any], checkpoint: Mapping[str, Any]) -> None:
    if (checkpoint.get("cell_id") != cell["cell_id"]
            or checkpoint.get("resume_identity") != cell["resume_identity"]
            or set(checkpoint.get("prerequisites", {})) != set(COMPLETION_PREREQUISITES)
            or any(value is not True for value in checkpoint["prerequisites"].values())):
        raise ScenarioMatrixError("cell completion or resume prerequisites are not satisfied")
