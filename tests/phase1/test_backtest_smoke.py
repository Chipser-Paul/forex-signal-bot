from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest


def _synthetic_frame() -> pd.DataFrame:
    index = pd.date_range(
        "2026-09-06T08:00:00Z",
        periods=36,
        freq="5min",
    )
    values = [100.0 + index * 0.01 for index in range(len(index))]
    return pd.DataFrame(
        {
            "open": values,
            "high": [value + 0.2 for value in values],
            "low": [value - 0.2 for value in values],
            "close": values,
            "tick_volume": [100] * len(index),
        },
        index=index,
    )


@pytest.mark.characterization
@pytest.mark.slow
def test_synthetic_backtest_completes_deterministically_without_live_mt5(
    monkeypatch, tmp_path, fake_mt5
):
    from backtests import shadow_mode_backtest as backtest

    frame = _synthetic_frame()
    monkeypatch.setattr(backtest, "_fetch_range", lambda *args, **kwargs: frame.copy())
    monkeypatch.setattr(backtest, "_mute_logs", lambda: None)

    start = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=175)
    first = backtest.run_backtest(
        "XAUUSDm", start, end, 1000.0, tmp_path / "first"
    )
    second = backtest.run_backtest(
        "XAUUSDm", start, end, 1000.0, tmp_path / "second"
    )

    stable_keys = (
        "closed_trades",
        "wins",
        "losses",
        "net_pnl",
        "ending_balance",
        "max_drawdown",
        "shadow_action_counts",
        "no_trade_counts",
    )
    assert {key: first[key] for key in stable_keys} == {
        key: second[key] for key in stable_keys
    }
    for key in ("net_pnl", "ending_balance", "max_drawdown"):
        assert math.isfinite(float(first[key]))
    assert not [call for call in fake_mt5.calls if call[0] == "copy_rates_range"]
    assert not [call for call in fake_mt5.calls if call[0] == "order_send"]
