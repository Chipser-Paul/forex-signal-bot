from __future__ import annotations

import pytest

from bot.validation import cost_policy
from bot.validation.development_metadata_bounds import SCENARIO_ORDER
from bot.validation.development_scenario_matrix import (
    ScenarioMatrixError, compose_scenarios, verify_completed_cells,
)


def matrix():
    return compose_scenarios(
        cost_policy.SWAP_SCENARIO_ORDER,
        [item["scenario_id"] for item in cost_policy.SLIPPAGE_SCENARIOS],
        SCENARIO_ORDER,
        [f"fold-{index:02d}" for index in range(1, 5)],
    )


def test_factorized_matrix_covers_every_registered_component():
    result = matrix()
    scenarios = result["scenarios"]
    assert result["unique_scenario_count"] == 16
    assert result["required_cell_count"] == 64
    assert {item["swap_scenario_id"] for item in scenarios} == set(cost_policy.SWAP_SCENARIO_ORDER)
    assert {item["slippage_scenario_id"] for item in scenarios} == {
        item["scenario_id"] for item in cost_policy.SLIPPAGE_SCENARIOS
    }
    assert {item["metadata_scenario_id"] for item in scenarios} == set(SCENARIO_ORDER)
    assert scenarios[0]["role"] == "PRIMARY"
    assert scenarios[-1]["groups"] == ["METADATA_STRESS", "COMBINED_WORST_CASE"]
    assert all(item["spread_source"] == "OBSERVED_HISTORICAL_BID_ASK" for item in scenarios)


def test_matrix_is_deterministic_and_completion_fails_closed():
    first = matrix()
    assert first == matrix()
    verify_completed_cells(first, first["required_fold_scenario_cells"])
    with pytest.raises(ScenarioMatrixError):
        verify_completed_cells(first, first["required_fold_scenario_cells"][:-1])
    with pytest.raises(ScenarioMatrixError):
        verify_completed_cells(first, first["required_fold_scenario_cells"] * 2)


@pytest.mark.parametrize("component", ["swap", "slippage", "metadata", "fold"])
def test_registered_component_drift_rejected(component):
    args = [
        list(cost_policy.SWAP_SCENARIO_ORDER),
        [item["scenario_id"] for item in cost_policy.SLIPPAGE_SCENARIOS],
        list(SCENARIO_ORDER),
        [f"fold-{index:02d}" for index in range(1, 5)],
    ]
    args[["swap", "slippage", "metadata", "fold"].index(component)].pop()
    with pytest.raises(ScenarioMatrixError):
        compose_scenarios(*args)
