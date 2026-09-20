from __future__ import annotations

import datetime as datetime_module
import sys
import types
from datetime import datetime, timedelta

import pandas as pd
import pytest

from bot.execution.risk_engine import RiskEngine
from runtime.context import RuntimeContext
from runtime import loop as runtime_loop
from strategies.smc_engine.strategy_state import StrategyState


@pytest.mark.unit
@pytest.mark.characterization
def test_risk_engine_is_deterministic_and_normalizes_to_volume_step(fake_mt5):
    fake_mt5.symbol.volume_step = 0.01
    engine = RiskEngine()

    first = engine.calculate_position_size("XAUUSDm", 1000.0, 1.0, risk_pct=0.0035)
    second = engine.calculate_position_size("XAUUSDm", 1000.0, 1.0, risk_pct=0.0035)

    assert first == second == 0.03


@pytest.mark.unit
@pytest.mark.parametrize(
    ("capital", "stop_distance", "risk_pct"),
    [(0.0, 1.0, 0.01), (-1.0, 1.0, 0.01), (1000.0, 0.0, 0.01), (1000.0, -1.0, 0.01), (1000.0, 1.0, 0.0)],
)
def test_risk_engine_rejects_invalid_inputs(fake_mt5, capital, stop_distance, risk_pct):
    result = RiskEngine().calculate_position_size(
        "XAUUSDm", capital, stop_distance, risk_pct=risk_pct
    )
    assert result is None


@pytest.mark.unit
@pytest.mark.characterization
def test_risk_engine_skips_below_minimum_volume(fake_mt5):
    fake_mt5.symbol.volume_min = 0.1
    result = RiskEngine().calculate_position_size(
        "XAUUSDm", 100.0, 100.0, risk_pct=0.001, enforce_min_volume=True
    )
    assert result is None


@pytest.mark.unit
@pytest.mark.characterization
def test_strategy_state_reset_rejection_and_expiry_are_explicit():
    state = StrategyState()
    assert state.state_name == "MAPPING_STRUCTURE"

    state.register_setup_candidate(trade_direction="buy", score=8, grade="B")
    assert state.state_name == "SETUP_FOUND_PENDING_CONFIRMATION"
    state.reject_setup("required_gate_rejected")
    assert state.state_name == "SCANNING_FOR_SETUP"
    assert state.last_rejection_reason == "required_gate_rejected"

    state.last_update = datetime.utcnow() - timedelta(minutes=121)
    assert state.is_expired() is True


@pytest.mark.unit
@pytest.mark.characterization
def test_runtime_loop_order_and_approved_signal_path(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(runtime_loop, "_get_bot_state", lambda: "running")

    ctx = RuntimeContext(
        symbols=["XAUUSDm"],
        loop_delay=60,
        is_symbol_enabled=lambda symbol: events.append(f"enabled:{symbol}") or True,
        refresh_runtime_settings=lambda: events.append("refresh"),
        show_profit_summary=lambda: events.append("profit"),
        monitor_trades=lambda trades: events.append("monitor") or trades,
        evaluate_symbol=lambda symbol, trades: events.append(f"evaluate:{symbol}"),
        manage_open_trades=lambda symbol, trades, lock_tiers: events.append(f"manage:{symbol}"),
        sleep_fn=lambda seconds: events.append(f"sleep:{seconds}"),
    )

    result = runtime_loop.main_loop_once(ctx, {})

    assert result == {}
    assert events[:5] == ["refresh", "profit", "monitor", "enabled:XAUUSDm", "evaluate:XAUUSDm"]
    assert events.count("manage:XAUUSDm") == 15
    assert events[-1] == "sleep:60"


@pytest.mark.unit
def test_required_symbol_gate_prevents_signal_evaluation(monkeypatch):
    evaluated: list[str] = []
    monkeypatch.setattr(runtime_loop, "_get_bot_state", lambda: "running")
    ctx = RuntimeContext(
        symbols=["XAUUSDm"],
        loop_delay=0,
        is_symbol_enabled=lambda symbol: False,
        refresh_runtime_settings=lambda: None,
        show_profit_summary=lambda: None,
        monitor_trades=lambda trades: trades,
        evaluate_symbol=lambda symbol, trades: evaluated.append(symbol),
        manage_open_trades=lambda symbol, trades, lock_tiers: None,
        sleep_fn=lambda seconds: None,
    )
    runtime_loop.main_loop_once(ctx, {})
    assert evaluated == []


@pytest.mark.unit
@pytest.mark.characterization
def test_orchestrator_delegates_daily_limit_to_phase4_authority(monkeypatch):
    from bot.state import orchestrator as orchestrator_module

    class FixedDateTime(datetime_module.datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 1, 15, 12, 0, 0)
            return value.replace(tzinfo=tz) if tz is not None else value

    fake_datetime = types.ModuleType("datetime")
    fake_datetime.datetime = FixedDateTime
    fake_datetime.timezone = datetime_module.timezone
    fake_datetime.timedelta = datetime_module.timedelta
    monkeypatch.setitem(sys.modules, "datetime", fake_datetime)
    monkeypatch.setattr(
        orchestrator_module,
        "fetch_ohlcv",
        lambda *args, **kwargs: pd.DataFrame({"close": [100.0]}),
    )
    monkeypatch.setattr(
        orchestrator_module,
        "get_session_context",
        lambda now: {"active_session": "new_york", "session_allowed": True},
    )
    monkeypatch.setattr(orchestrator_module, "get_news_status", lambda symbol, now: {"news_clear": True})
    logged: dict = {}
    monkeypatch.setattr(orchestrator_module, "log_setup_evaluation", lambda **kwargs: logged.update(kwargs))

    result = orchestrator_module.StrategyOrchestrator().evaluate_symbol(
        "XAUUSDm",
        StrategyState(),
        account_balance=1000.0,
        daily_pnl=-100.0,
        active_trade_count=0,
        event_at=datetime_module.datetime(2026, 1, 15, 12, tzinfo=datetime_module.timezone.utc),
    )

    assert result.action == "skip"
    assert result.reason == "htf_bias_unconfirmed"
    assert result.context["setup_id"].startswith("pre8n_")
    assert result.state_name != "DAILY_LIMIT_HIT"
    assert list(logged["gate_results"])[:3] == [
        "gate_1_session",
        "gate_2_news",
        "gate_4_daily_limit",
    ]
    assert logged["gate_results"]["gate_4_daily_limit"] == {
        "pass": True,
        "raw": {
            "authority": "phase4_account_risk",
            "legacy_inputs_ignored": True,
        },
    }
