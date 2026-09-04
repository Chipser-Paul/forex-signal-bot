from __future__ import annotations

from datetime import datetime, time, timezone

import pytest

from bot.backtesting import CommissionKind, Side, SlippageKind
from bot.backtesting.costs import (
    commission_for_fill,
    deterministic_slippage_points,
    rollover_instants,
    swap_for_rollover,
)
from tests.phase7.helpers import metadata, policy


UTC = timezone.utc


@pytest.mark.unit
def test_deterministic_slippage_depends_on_stable_identity_not_call_order():
    model = policy(slippage_points=3, slippage_kind=SlippageKind.UNIFORM_ADVERSE_POINTS).slippage
    first = deterministic_slippage_points(model, seed=11, action_id="a")
    _ = deterministic_slippage_points(model, seed=11, action_id="other")
    second = deterministic_slippage_points(model, seed=11, action_id="a")
    assert first == second
    assert 0 <= first <= 3


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "amount", "volume", "expected"),
    [
        (CommissionKind.PER_LOT_PER_SIDE, 4, 0.5, 2.0),
        (CommissionKind.PER_LOT_ROUND_TURN, 8, 0.5, 2.0),
        (CommissionKind.FIXED_PER_ORDER, 3, 0.5, 3.0),
        (CommissionKind.PERCENT_NOTIONAL, 0.001, 0.5, 100.0),
    ],
)
def test_commission_schedules_are_explicit_per_fill(kind, amount, volume, expected):
    item = metadata(commission_kind=kind, commission_amount=amount)
    assert commission_for_fill(item, volume=volume, fill_price=2000) == pytest.approx(expected)


@pytest.mark.unit
def test_rollover_uses_named_timezone_across_dst():
    item = metadata(rollover_timezone="America/New_York", rollover_time=time(17, 0))
    winter = rollover_instants(
        datetime(2026, 1, 5, 20, tzinfo=UTC),
        datetime(2026, 1, 6, 23, tzinfo=UTC),
        item,
    )
    summer = rollover_instants(
        datetime(2026, 7, 5, 20, tzinfo=UTC),
        datetime(2026, 7, 6, 23, tzinfo=UTC),
        item,
    )
    assert winter[0].hour == 22
    assert summer[0].hour == 21


@pytest.mark.unit
def test_triple_swap_and_long_short_rates():
    item = metadata(long_swap=-1, short_swap=2, triple_weekday=2)
    wednesday_rollover = datetime(2026, 1, 7, 22, tzinfo=UTC)
    long_amount, multiplier = swap_for_rollover(
        item, direction=Side.BUY, volume=0.5, rollover=wednesday_rollover
    )
    short_amount, _ = swap_for_rollover(
        item, direction=Side.SELL, volume=0.5, rollover=wednesday_rollover
    )
    assert multiplier == 3
    assert long_amount == pytest.approx(-1.5)
    assert short_amount == pytest.approx(3.0)
