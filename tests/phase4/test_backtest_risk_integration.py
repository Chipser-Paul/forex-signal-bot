from __future__ import annotations

from dataclasses import replace

import pytest

from backtests.shadow_mode_backtest import (
    _backtest_account_snapshot,
    _backtest_open_risk,
)
from tests.phase3.helpers import SIGNAL_AT, open_position


@pytest.mark.unit
def test_backtest_account_snapshot_includes_floating_loss():
    position = open_position(quantity=0.1, fill_price=100.0)
    snapshot = _backtest_account_snapshot(
        account_ref="test-account",
        capital=1000.0,
        realized_pnl=0.0,
        positions=[position],
        mark_price=95.0,
        contract_size=100.0,
        timestamp=SIGNAL_AT,
    )

    assert snapshot.balance == 1000.0
    assert snapshot.floating_pnl == -50.0
    assert snapshot.equity == 950.0


@pytest.mark.unit
def test_backtest_open_risk_uses_remaining_quantity_after_partial():
    original = open_position(quantity=0.1, fill_price=100.0)
    partial = replace(
        original,
        remaining_quantity=0.05,
        closed_quantity=0.05,
        partial_close_occurred=True,
    )
    item = _backtest_open_risk(
        [partial],
        mark_price=101.0,
        contract_size=100.0,
    )[0]

    assert item.remaining_volume == 0.05
    assert item.estimated_loss == pytest.approx(50.0)
    assert item.ownership == "strategy"


@pytest.mark.unit
def test_backtest_locked_profit_stop_has_zero_open_loss():
    original = open_position(quantity=0.1, fill_price=100.0)
    protected = replace(original, current_stop=100.5)
    item = _backtest_open_risk(
        [protected],
        mark_price=102.0,
        contract_size=100.0,
    )[0]
    assert item.estimated_loss == 0.0
    assert item.calculation_method == "locked_profit_floor"
