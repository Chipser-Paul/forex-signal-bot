from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from bot.state import gate_inputs, gate_reducer
from bot.strategy.config import StrategyConfig
from bot.strategy.setup_state import record_from_state
from config.symbol_profiles import get_symbol_profile
from strategies.smc_engine.strategy_state import StrategyState


AT = datetime(2024, 3, 4, 12, 5, tzinfo=timezone.utc)


def _frame():
    opened = [AT - timedelta(minutes=5 * (60 - n)) for n in range(60)]
    return pd.DataFrame({
        "open_time": opened,
        "available_at": [item + timedelta(minutes=5) for item in opened],
        "open": [100.0] * 60, "high": [102.0] * 60,
        "low": [98.0] * 60, "close": [100.0] * 60,
    })


def _inputs(monkeypatch, failed=None):
    monkeypatch.setattr(gate_inputs, "detect_liquidity_sweep", lambda *a, **kw: (
        {} if failed == "liquidity" else {"side": "sell", "type": "equal_lows"}
    ))
    monkeypatch.setattr(gate_inputs, "detect_displacement", lambda *a, **kw: (
        {} if failed == "displacement" else {"valid": True, "fvg": (98.0, 99.0)}
    ))
    monkeypatch.setattr(gate_inputs, "get_unfilled_fvgs", lambda *a, **kw: [{"bottom": 98.0, "top": 99.0}])
    monkeypatch.setattr(gate_inputs, "analyze_market_structure", lambda *a, **kw: (
        {} if failed == "internal" else {"event": "BOS"}
    ))
    monkeypatch.setattr(gate_inputs, "detect_ob_breaker", lambda *a, **kw: (
        {} if failed == "score" else {"valid": True, "zone": (97.0, 99.0)}
    ))
    monkeypatch.setattr(gate_inputs, "calculate_atr", lambda *a, **kw: 1.0)
    monkeypatch.setattr(gate_reducer, "evaluate_legacy_context", lambda **kw: SimpleNamespace(
        entry_eligible=failed != "canonical",
        to_dict=lambda: {"eligible": failed != "canonical"},
        reasons=(SimpleNamespace(value="DATA_UNSAFE"),),
    ))
    if failed == "entry":
        monkeypatch.setattr(gate_reducer, "determine_entry", lambda *a, **kw: None)
    frame = _frame()
    config = StrategyConfig()
    inputs = gate_inputs.build_gate_inputs(
        symbol="XAUUSDm", event_at=AT,
        frames={"H1": frame, "M5": frame, "M15": frame},
        profile=get_symbol_profile("XAUUSDm"), htf_bias="bullish",
        bias_snapshot={"htf_bias": {"direction": "bullish"}},
        bias_resolution={"direction": "bullish"},
        liquidity_context={
            "structure_context": {"structure": "bullish", "state": "confirmed", "discount_zone": (95.0, 99.0)},
            "liquidity_pools": [],
        },
        dxy_context={"available": True, "dxy_bias": "bullish"},
        news_context={"news_clear": True},
        session_context={"session_allowed": True, "active_session": "london"},
        config=config,
    )
    return inputs, config, frame


@pytest.mark.parametrize("failed,action,reason", [
    ("liquidity", "wait", "liquidity_sweep_missing"),
    ("displacement", "wait", "displacement_missing"),
    ("internal", "skip", "internal_structure_missing"),
    ("score", "skip", "score_below_threshold"),
    ("canonical", "skip", "data_unsafe"),
    ("entry", "wait", "entry_not_ready"),
    (None, "candidate_ready", "setup_passed_all_gates"),
])
def test_gate_sequence_matches_live_characterization(monkeypatch, failed, action, reason):
    inputs, config, _ = _inputs(monkeypatch, failed)
    prior = record_from_state(StrategyState(event_time=AT), event_at=AT)
    transition = gate_reducer.evaluate_strategy_gates(prior, inputs, AT, config)
    result = transition.result()
    assert (result["action"], result["reason"]) == (action, reason)
    assert result["setup_id"].startswith("s8n1_")
    assert prior.data()["last_event_id"] is None
    assert transition.state_record.data()["last_event_id"] == inputs.event_id
    if failed is None:
        assert result["context"]["score"]["score"] == 8
        assert result["context"]["entry"]["direction"] == "buy"


def test_duplicate_event_and_input_mutation_are_idempotent(monkeypatch):
    inputs, config, frame = _inputs(monkeypatch)
    prior = record_from_state(StrategyState(event_time=AT), event_at=AT)
    first = gate_reducer.evaluate_strategy_gates(prior, inputs, AT, config)
    frame.loc[0, "close"] = 999.0
    second = gate_reducer.evaluate_strategy_gates(first.state_record, inputs, AT, config)
    assert second.result_json == first.result_json
    assert second.state_record == first.state_record
    assert inputs.decoded()["entry_rows"][0]["close"] == 100.0


def test_event_time_and_configuration_mismatch_reject(monkeypatch):
    inputs, config, _ = _inputs(monkeypatch)
    prior = record_from_state(StrategyState(event_time=AT), event_at=AT)
    with pytest.raises(ValueError, match="mismatch"):
        gate_reducer.evaluate_strategy_gates(prior, inputs, AT + timedelta(seconds=1), config)
