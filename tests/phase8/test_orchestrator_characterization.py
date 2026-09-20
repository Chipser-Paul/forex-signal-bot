from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from bot.state import orchestrator as module
from bot.state import gate_inputs, gate_reducer
from strategies.smc_engine.strategy_state import StrategyState


def _frame():
    at = datetime(2024, 3, 4, 12, 5, tzinfo=timezone.utc)
    opened = [at - timedelta(minutes=5 * (60 - n)) for n in range(60)]
    return pd.DataFrame({
        "open_time": opened,
        "available_at": [item + timedelta(minutes=5) for item in opened],
        "open": [100.0] * 60, "high": [102.0] * 60,
        "low": [98.0] * 60, "close": [100.0] * 60,
    })


def _install(monkeypatch, *, failed=None):
    calls = []
    frame = _frame()
    monkeypatch.setattr(module, "log_setup_evaluation", lambda **kw: calls.append(kw))
    monkeypatch.setattr(module, "get_session_context", lambda now: {"session_allowed": True, "active_session": "london"})
    monkeypatch.setattr(module, "get_news_status", lambda symbol, now: {"news_clear": True})
    monkeypatch.setattr(module, "get_bias_snapshot", lambda symbol, silent: {"htf_bias": {"direction": "bullish"}})
    monkeypatch.setattr(module, "resolve_trade_bias", lambda snapshot: {"direction": "bullish"})
    monkeypatch.setattr(module, "analyze_dxy_correlation", lambda symbol, silent, decision_timestamp: {
        "available": True, "reduce_size": False, "dxy_bias": "bullish",
    })
    monkeypatch.setattr(module, "fetch_ohlcv", lambda symbol, timeframe, bars: frame.copy())
    monkeypatch.setattr(module, "build_liquidity_map", lambda symbol, silent: {
        "structure_context": {"structure": "bullish", "state": "confirmed", "discount_zone": (95.0, 99.0)},
        "liquidity_pools": [],
    })
    monkeypatch.setattr(gate_inputs, "detect_liquidity_sweep", lambda *args, **kw: (
        {} if failed == "liquidity" else {"side": "sell", "type": "equal_lows"}
    ))
    monkeypatch.setattr(gate_inputs, "detect_displacement", lambda *args, **kw: (
        {} if failed == "displacement" else {"valid": True, "fvg": (98.0, 99.0)}
    ))
    monkeypatch.setattr(gate_inputs, "get_unfilled_fvgs", lambda *args, **kw: [{"bottom": 98.0, "top": 99.0}])
    monkeypatch.setattr(gate_inputs, "analyze_market_structure", lambda *args, **kw: (
        {} if failed == "internal" else {"event": "BOS"}
    ))
    monkeypatch.setattr(gate_inputs, "detect_ob_breaker", lambda *args, **kw: (
        {} if failed == "score" else {"valid": True, "zone": (97.0, 99.0)}
    ))
    monkeypatch.setattr(gate_inputs, "calculate_atr", lambda *args, **kw: 1.0)
    monkeypatch.setattr(gate_reducer, "evaluate_legacy_context", lambda **kw: SimpleNamespace(
        entry_eligible=failed != "canonical",
        to_dict=lambda: {"eligible": failed != "canonical"},
        reasons=(SimpleNamespace(value="DATA_UNSAFE"),),
    ))
    if failed == "entry":
        monkeypatch.setattr(gate_reducer, "determine_entry", lambda *args, **kw: None)
    return calls


@pytest.mark.parametrize("failed,action,reason,last_gate", [
    ("liquidity", "wait", "liquidity_sweep_missing", "gate_8_liquidity"),
    ("displacement", "wait", "displacement_missing", "gate_9_displacement"),
    ("internal", "skip", "internal_structure_missing", "gate_10_internal_structure"),
    ("score", "skip", "score_below_threshold", "gate_11_confluence_score"),
    ("canonical", "skip", "data_unsafe", "canonical_strategy"),
    ("entry", "wait", "entry_not_ready", "gate_12_13_rr_entry"),
    (None, "candidate_ready", "setup_passed_all_gates", "gate_12_13_rr_entry"),
])
def test_supported_live_gate_order_and_first_failure(monkeypatch, failed, action, reason, last_gate):
    logs = _install(monkeypatch, failed=failed)
    state = StrategyState()
    result = module.StrategyOrchestrator().evaluate_symbol(
        "XAUUSDm", state, account_balance=1000.0, daily_pnl=0.0,
        active_trade_count=0,
        event_at=datetime(2024, 3, 4, 12, 5, tzinfo=timezone.utc),
    )
    assert (result.action, result.reason) == (action, reason)
    assert result.context["setup_id"].startswith("s8n1_")
    if logs:
        assert last_gate in logs[-1]["gate_results"]
    if failed is None:
        assert state.structure_dir == "bullish"
        assert state.liquidity_side == "sell"
        assert state.displacement_seen
        assert result.context["score"]["score"] == 8
        assert result.context["entry"]["direction"] == "buy"
