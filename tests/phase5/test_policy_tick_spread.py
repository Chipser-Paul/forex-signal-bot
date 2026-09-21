from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from bot.execution.broker import ExecutionAction, ExecutionError, ExecutionReason
from bot.execution.broker.policy import execution_policy_from_environment, symbol_environment_key
from bot.execution.broker.validation import tick_from_mt5, validate_spread, validate_tick
from tests.phase5.helpers import NOW, configure_broker, entry_request, executor, policy


def test_environment_requires_magic_and_per_symbol_limits():
    with pytest.raises(ExecutionError, match="BOT_MAGIC_NUMBER"):
        execution_policy_from_environment({}, ("XAUUSDm",))
    with pytest.raises(ExecutionError, match="required"):
        execution_policy_from_environment({"BOT_MAGIC_NUMBER": "7"}, ("XAUUSDm",))


def test_environment_loads_explicit_limits_without_inventing_values():
    loaded = execution_policy_from_environment(
        {
            "BOT_MAGIC_NUMBER": "771234",
            "BOT_MAX_SPREAD_POINTS_XAUUSDM": "25.5",
            "BOT_MAX_DEVIATION_POINTS_XAUUSDM": "7",
        },
        ("XAUUSDm",),
    )
    assert loaded.magic_number == 771234
    assert loaded.spread_limit("XAUUSDm") == 25.5
    assert loaded.deviation_limit("XAUUSDm") == 7
    assert symbol_environment_key("BOT_MAX_SPREAD_POINTS", "XAU/USD.m") == "BOT_MAX_SPREAD_POINTS_XAUUSDM"


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_environment_rejects_invalid_magic(value):
    env = {
        "BOT_MAGIC_NUMBER": value,
        "BOT_MAX_SPREAD_POINTS_XAUUSDM": "25",
        "BOT_MAX_DEVIATION_POINTS_XAUUSDM": "5",
    }
    with pytest.raises(ExecutionError):
        execution_policy_from_environment(env, ("XAUUSDm",))


def test_tick_timestamp_is_explicit_utc(fake_mt5):
    configure_broker(fake_mt5)
    tick = tick_from_mt5(fake_mt5.tick)
    assert tick.timestamp == NOW
    assert tick.timestamp.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    ("offset", "reason"),
    [(-11, ExecutionReason.TICK_STALE), (2, ExecutionReason.TICK_FUTURE)],
)
def test_stale_and_future_ticks_are_rejected(fake_mt5, offset, reason):
    configure_broker(fake_mt5)
    raw = replace_time(fake_mt5.tick, NOW + timedelta(seconds=offset))
    tick = tick_from_mt5(raw)
    with pytest.raises(Exception) as captured:
        validate_tick(tick, NOW, policy())
    assert captured.value.reason is reason


def replace_time(tick, value):
    return SimpleNamespace(
        bid=tick.bid,
        ask=tick.ask,
        time=int(value.timestamp()),
        time_msc=int(value.timestamp() * 1000),
    )


@pytest.mark.parametrize(
    ("bid", "ask"),
    [(0, 1), (-1, 1), (1, 0), (2, 1), (float("nan"), 1)],
)
def test_invalid_bid_ask_is_rejected(bid, ask):
    raw = SimpleNamespace(bid=bid, ask=ask, time_msc=int(NOW.timestamp() * 1000))
    with pytest.raises(Exception) as captured:
        tick_from_mt5(raw)
    assert captured.value.reason is ExecutionReason.TICK_INVALID


def test_absolute_spread_limit_is_enforced(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path, custom_policy=policy(maximum_spread_points={"XAUUSDm": 0.5}))
    snapshot = engine.snapshot("XAUUSDm", "buy", ExecutionAction.ENTRY)
    with pytest.raises(Exception) as captured:
        validate_spread(snapshot.symbol, snapshot.tick, 99.0, engine.policy)
    assert captured.value.reason is ExecutionReason.SPREAD_ABSOLUTE_LIMIT


def test_relative_spread_limit_is_enforced(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path, custom_policy=policy(maximum_spread_to_stop_fraction=0.05))
    snapshot = engine.snapshot("XAUUSDm", "buy", ExecutionAction.ENTRY)
    with pytest.raises(Exception) as captured:
        validate_spread(snapshot.symbol, snapshot.tick, 99.9, engine.policy)
    assert captured.value.reason is ExecutionReason.SPREAD_RELATIVE_LIMIT


def test_missing_spread_configuration_fails_closed(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path, custom_policy=policy(maximum_spread_points={}))
    result = engine.execute(entry_request(engine))
    assert result.reason is ExecutionReason.SPREAD_CONFIGURATION_MISSING
    assert not [call for call in fake_mt5.calls if call[0] == "order_send"]
