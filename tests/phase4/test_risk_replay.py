from __future__ import annotations

import pytest

from backtests.risk_protection_replay import run_risk_replay


@pytest.mark.integration
def test_live_mock_and_backtest_risk_replay_match():
    replay = run_risk_replay()
    assert replay["normalized_match"] is True
    assert replay["live_mock"]["normal_approval"]["approved"] is True
    assert replay["live_mock"]["oversized_request"]["reason"] == "RISK_ABOVE_HARD_CEILING"
    assert replay["live_mock"]["minimum_lot"]["reason"] == "MINIMUM_VOLUME_EXCEEDS_RISK"
    assert replay["live_mock"]["aggregate_limit"]["reason"] == "AGGREGATE_RISK_LIMIT"
    assert replay["live_mock"]["floating_daily_drawdown"] == "DAILY_PAUSED"
    assert replay["live_mock"]["weekly_drawdown"] == "WEEKLY_PAUSED"
    assert replay["live_mock"]["total_hard_stop"] == "HARD_STOPPED"
    assert replay["live_mock"]["three_losses"] == "LOSS_STREAK_PAUSED"
    assert replay["live_mock"]["duplicate_outcome"] == {
        "consumed": False,
        "pnl_unchanged": True,
    }
    assert replay["persistence"] == {
        "restart": "LOADED",
        "corrupt_primary": "RECOVERED_BACKUP",
        "state_preserved": True,
    }
