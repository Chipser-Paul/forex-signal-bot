from datetime import datetime, timedelta, timezone

import pytest

from strategies.smc_engine.strategy_state import STATE_EXPIRY_MINUTES, StrategyState


def test_injected_event_time_controls_state_and_candidate_identity():
    at = datetime(2024, 1, 2, 12, 5, tzinfo=timezone.utc)
    first = StrategyState(event_time=at)
    second = StrategyState(event_time=at)
    for state in (first, second):
        state.update_liquidity("sell", 4)
        state.register_setup_candidate(trade_direction="buy", score=8)
    assert first.snapshot() == second.snapshot()
    assert first.liquidity_time == at.replace(tzinfo=None)
    assert first.setup_candidate["created_at"] == at.replace(tzinfo=None).isoformat()


def test_expiry_is_event_time_based_with_strict_boundary():
    at = datetime(2024, 1, 2, 12, tzinfo=timezone.utc)
    state = StrategyState(event_time=at)
    state.set_event_time(at + timedelta(minutes=STATE_EXPIRY_MINUTES))
    assert not state.is_expired()
    state.set_event_time(at + timedelta(minutes=STATE_EXPIRY_MINUTES, microseconds=1))
    assert state.is_expired()


def test_event_time_rejects_naive_and_backward_values():
    at = datetime(2024, 1, 2, 12, tzinfo=timezone.utc)
    state = StrategyState(event_time=at)
    with pytest.raises(ValueError, match="timezone-aware"):
        state.set_event_time(at.replace(tzinfo=None))
    with pytest.raises(ValueError, match="backward"):
        state.set_event_time(at - timedelta(microseconds=1))


def test_cascade_clock_uses_injected_event_time():
    at = datetime(2024, 1, 2, 12, tzinfo=timezone.utc)
    state = StrategyState(event_time=at)
    state.record_trade_result("bullish", "loss")
    state.record_trade_result("bullish", "loss")
    state.record_trade_result("bullish", "loss")
    assert state.is_direction_blocked("bullish")
    state.set_event_time(at + timedelta(hours=12))
    assert not state.is_direction_blocked("bullish")


def test_injected_transitions_never_call_wall_clock(monkeypatch):
    import strategies.smc_engine.strategy_state as state_module

    at = datetime(2024, 1, 2, 12, tzinfo=timezone.utc)
    state = StrategyState(event_time=at)

    class ClockTrap(datetime):
        @classmethod
        def utcnow(cls):
            raise AssertionError("hidden wall-clock dependency")

    monkeypatch.setattr(state_module, "datetime", ClockTrap)
    state.reset()
    state.update_structure("bullish", "confirmed")
    state.update_liquidity("sell", 4)
    state.update_displacement((98.0, 99.0))
    state.register_setup_candidate(trade_direction="buy")
    state.record_trade_result("bullish", "loss")
    assert not state.is_expired()
