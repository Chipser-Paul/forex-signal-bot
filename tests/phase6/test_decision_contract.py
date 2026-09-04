from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from bot.strategy import (
    DirectionState,
    SafetyState,
    StrategyConfig,
    StrategyReason,
    StrategySide,
    evaluate_live_strategy,
    evaluate_replay_strategy,
    aggregate_bias,
)
from bot.strategy.models import StrategyError
from tests.phase6.helpers import strategy_input


@pytest.mark.unit
@pytest.mark.parametrize("symbol", ["BTCUSDm", "XAUUSD", "EURUSDm", "DXY"])
def test_only_exact_xauusdm_is_executable(symbol):
    decision = evaluate_live_strategy(strategy_input(symbol=symbol), StrategyConfig())
    assert not decision.entry_eligible
    assert decision.side is StrategySide.FLAT
    assert StrategyReason.SYMBOL_NOT_EXECUTABLE in decision.reasons


@pytest.mark.unit
def test_live_and_replay_use_identical_pure_decision_engine():
    inputs = strategy_input()
    live = evaluate_live_strategy(inputs, StrategyConfig())
    replay = evaluate_replay_strategy(inputs, StrategyConfig())
    assert live.to_json() == replay.to_json()
    assert live.entry_eligible and live.side is StrategySide.LONG


@pytest.mark.unit
def test_mandatory_gate_cannot_be_overridden_by_full_confluence():
    decision = evaluate_live_strategy(
        strategy_input(news=SafetyState.DATA_UNSAFE), StrategyConfig()
    )
    assert decision.confluence.score == decision.confluence.maximum == 8
    assert not decision.entry_eligible
    assert decision.reasons == (StrategyReason.NEWS_DATA_UNSAFE,)


@pytest.mark.unit
def test_dxy_same_direction_is_a_conflict_for_gold():
    decision = evaluate_live_strategy(
        strategy_input(dxy=DirectionState.BULLISH), StrategyConfig()
    )
    assert StrategyReason.DXY_DIRECTION_CONFLICT in decision.reasons


@pytest.mark.unit
def test_htf_bias_is_weighted_deterministic_and_fail_closed():
    bullish = aggregate_bias(
        {"W1": DirectionState.BULLISH, "D1": DirectionState.BULLISH, "H4": DirectionState.BEARISH}
    )
    bearish = aggregate_bias(
        {"W1": DirectionState.BEARISH, "D1": DirectionState.BEARISH, "H4": DirectionState.BULLISH}
    )
    assert bullish.state is DirectionState.BULLISH
    assert bearish.state is DirectionState.BEARISH
    assert bullish.strength == pytest.approx(bearish.strength)
    assert aggregate_bias({"W1": DirectionState.BULLISH}).state is DirectionState.DATA_UNSAFE


@pytest.mark.unit
def test_decision_serialization_and_fingerprint_are_deterministic():
    first = evaluate_live_strategy(strategy_input(), StrategyConfig())
    second = evaluate_live_strategy(strategy_input(), StrategyConfig())
    assert first.to_json() == second.to_json()
    assert first.configuration_fingerprint == second.configuration_fingerprint
    assert "password" not in first.to_json().lower()


@pytest.mark.unit
def test_strategy_input_copies_mutable_invalidation():
    source = strategy_input()
    with pytest.raises(TypeError):
        source.invalidation["price"] = 0


@pytest.mark.unit
def test_invalid_production_allowlist_is_rejected():
    with pytest.raises(StrategyError, match="exactly XAUUSDm"):
        StrategyConfig(executable_symbols=frozenset({"XAUUSDm", "BTCUSDm"}))


@pytest.mark.unit
def test_main_and_broker_boundary_retain_symbol_guard(fake_mt5, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    import main

    assert main.SYMBOLS == ["XAUUSDm"]
    assert main.is_symbol_trading_enabled("XAUUSDm")
    assert not main.is_symbol_trading_enabled("BTCUSDm")
    source = inspect.getsource(main._submit_live_entry)
    assert "PRODUCTION_EXECUTABLE_SYMBOLS" in source
    assert "_live_broker_executor" in source

    monkeypatch.setattr(
        main,
        "_live_broker_executor",
        lambda _symbols: pytest.fail("non-allowlisted symbol reached broker construction"),
    )
    now = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)
    execution, _trade_id = main._submit_live_entry(
        symbol="BTCUSDm",
        direction="buy",
        lot=0.01,
        stop=99.0,
        target=102.0,
        intent=SimpleNamespace(signal_id="signal", requested_trigger=100.0, expires_at=None),
        tick_event=SimpleNamespace(event_id="tick", timestamp=now),
        risk_decision=SimpleNamespace(),
        open_trades={},
        comment="test",
        context={},
    )
    assert execution is None
