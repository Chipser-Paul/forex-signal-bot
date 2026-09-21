from __future__ import annotations

import pytest

from backtests.realistic_execution_replay import performance_sanity, run_replay


@pytest.mark.unit
def test_all_required_replay_scenarios_pass_without_profitability_claims():
    result = run_replay()
    assert result["scenario_count"] == 23
    assert all(item["status"] == "PASS" for item in result["scenarios"].values())
    assert result["result_label"] == "DIAGNOSTIC \u2014 NOT VALIDATED"
    assert result["profitability_evidence"] is False
    assert result["scenarios"]["aggregate_risk_rejection"]["reason_code"] == "AGGREGATE_RISK_LIMIT"
    assert result["scenarios"]["floating_equity_drawdown_pause"]["circuit"] == "DAILY_PAUSED"


@pytest.mark.unit
@pytest.mark.slow
def test_quote_normalization_performance_sanity():
    result = performance_sanity(10_000)
    assert result["record_count"] == 10_000
    assert result["diagnostic_count"] == 10_000
    assert result["ordered"] is True
    assert result["elapsed_seconds"] < 5.0
    assert result["local_observation_only"] is True
