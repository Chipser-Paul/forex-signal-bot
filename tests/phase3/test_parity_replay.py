from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backtests.execution_parity_replay import build_replay
from backtests.shadow_mode_backtest import run_backtest


def test_machine_readable_parity_replay_matches_both_adapters():
    replay = build_replay()
    assert replay["all_match"] is True
    assert len(replay["scenarios"]) == 2
    assert all(scenario["historical"] == scenario["live_mock"] for scenario in replay["scenarios"])


def test_shadow_backtest_rejects_retired_backtest_only_trailing_policy(tmp_path: Path):
    with pytest.raises(ValueError, match="shared live_atr_3x"):
        run_backtest(
            "TEST",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            1000.0,
            tmp_path,
            trail_mode="2stage",
        )
