from copy import deepcopy

import pytest

from bot.validation import cost_policy
from bot.validation.development_metadata_bounds import SCENARIO_ORDER
from bot.validation.development_evaluation_plan import _fixed_folds
from bot.validation.development_scenario_matrix import (
    REQUIRED_BINDINGS, COMPLETION_PREREQUISITES, ScenarioMatrixError, compose_scenarios,
    build_cell_contract, verify_cell_contract, verify_cell_completion,
)
from bot.acquisition.evidence_contracts import canonical_hash


def _contract():
    matrix = compose_scenarios(cost_policy.SWAP_SCENARIO_ORDER,
        tuple(item["scenario_id"] for item in cost_policy.SLIPPAGE_SCENARIOS), SCENARIO_ORDER,
        tuple(f"fold-{index:02d}" for index in range(1, 5)))
    bindings = {key: canonical_hash({"synthetic": key}) for key in REQUIRED_BINDINGS}
    return matrix, _fixed_folds(), build_cell_contract(matrix, _fixed_folds(), bindings)


def test_all_64_cells_bind_exact_scenario_fold_costs_lifecycle_and_resume():
    matrix, folds, contract = _contract()
    verify_cell_contract(contract, matrix, folds)
    assert contract["cell_count"] == 64
    assert len({item["cell_id"] for item in contract["cells"]}) == 64
    assert len({item["scenario"]["scenario_id"] for item in contract["cells"]}) == 16
    for cell in contract["cells"]:
        assert cell["lifecycle_consumption_enabled"]
        assert cell["bindings"] == contract["bindings"]
        assert cell["metadata_overlay_id"] == cell["scenario"]["metadata_scenario_id"]
        assert cell["cost_overlay_ids"] == [cell["scenario"]["swap_scenario_id"], cell["scenario"]["slippage_scenario_id"]]
        checkpoint = {"cell_id": cell["cell_id"], "resume_identity": cell["resume_identity"],
                      "prerequisites": {name: True for name in COMPLETION_PREREQUISITES}}
        verify_cell_completion(cell, checkpoint)
        checkpoint["prerequisites"]["consumption_reconciled"] = False
        with pytest.raises(ScenarioMatrixError):
            verify_cell_completion(cell, checkpoint)
    assert build_cell_contract(matrix, folds, contract["bindings"]) == contract


@pytest.mark.parametrize("changed", ["scenario", "fold", "bindings", "resume_identity", "cell_id", "metadata_overlay_id", "lifecycle_consumption_enabled"])
def test_changed_cell_identity_rejects(changed):
    matrix, folds, contract = _contract()
    mutated = deepcopy(contract)
    mutated["cells"][0][changed] = "changed"
    with pytest.raises(ScenarioMatrixError):
        verify_cell_contract(mutated, matrix, folds)


@pytest.mark.parametrize("change", ["missing", "duplicate", "unexpected"])
def test_no_missing_duplicate_or_unexpected_cell(change):
    matrix, folds, contract = _contract()
    if change == "missing":
        contract["cells"].pop()
    elif change == "duplicate":
        contract["cells"][-1] = contract["cells"][0]
    else:
        contract["cells"][0]["cell_id"] = "unexpected"
    with pytest.raises(ScenarioMatrixError):
        verify_cell_contract(contract, matrix, folds)
