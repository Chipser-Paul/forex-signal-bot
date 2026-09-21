from dataclasses import replace
from datetime import timedelta
import json

import pytest

from bot.state import gate_inputs, gate_reducer, orchestrator
from bot.strategy.setup_state import SetupStateError, SetupStateRecord, record_from_state
from strategies.smc_engine.strategy_state import StrategyState
from tests.phase8.test_gate_reducer import AT, _inputs
from tests.phase8.test_orchestrator_characterization import _install


@pytest.mark.parametrize("failed,forbidden", [
    ("liquidity", "detect_displacement"),
    ("displacement", "get_unfilled_fvgs"),
    ("internal", "detect_ob_breaker"),
])
def test_live_acquisition_does_not_mask_first_failed_gate(monkeypatch, failed, forbidden):
    _install(monkeypatch, failed=failed)

    def prohibited(*args, **kwargs):
        pytest.fail(f"later analyzer ran after {failed} failed")

    monkeypatch.setattr(gate_inputs, forbidden, prohibited)
    result = orchestrator.StrategyOrchestrator().evaluate_symbol(
        "XAUUSDm", StrategyState(event_time=AT), event_at=AT,
        account_balance=1000, daily_pnl=0, active_trade_count=0,
    )
    assert result.reason == {
        "liquidity": "liquidity_sweep_missing", "displacement": "displacement_missing",
        "internal": "internal_structure_missing",
    }[failed]


def test_modified_evidence_cannot_reuse_an_event_id(monkeypatch):
    inputs, config, _ = _inputs(monkeypatch)
    data = json.loads(inputs.payload)
    data["atr"] += 1
    forged = replace(inputs, payload=json.dumps(data, sort_keys=True, separators=(",", ":")))
    with pytest.raises(gate_inputs.GateInputError, match="identity"):
        forged.decoded()
    prior = record_from_state(StrategyState(event_time=AT), event_at=AT)
    with pytest.raises(gate_inputs.GateInputError, match="identity"):
        gate_reducer.evaluate_strategy_gates(prior, forged, AT, config)


def test_restart_duplicate_preserves_every_state_field(monkeypatch):
    inputs, config, _ = _inputs(monkeypatch)
    prior = record_from_state(StrategyState(event_time=AT), event_at=AT)
    first = gate_reducer.evaluate_strategy_gates(prior, inputs, AT, config)
    restarted = SetupStateRecord(first.state_record.payload)
    second = gate_reducer.evaluate_strategy_gates(restarted, inputs, AT, config)
    assert second == first
    with pytest.raises(SetupStateError, match="backward"):
        gate_reducer.evaluate_strategy_gates(
            record_from_state(StrategyState(event_time=AT + timedelta(seconds=1)), event_at=AT + timedelta(seconds=1)),
            inputs, AT, config,
        )


@pytest.mark.parametrize("mode", ["future", "naive", "duplicate", "unsorted"])
def test_bad_causal_source_is_rejected_before_analysis(monkeypatch, mode):
    inputs, _, frame = _inputs(monkeypatch)
    if mode == "future":
        frame.loc[frame.index[-1], "available_at"] = AT + timedelta(seconds=1)
    elif mode == "naive":
        frame["open_time"] = frame["open_time"].dt.tz_localize(None)
    elif mode == "duplicate":
        frame.loc[frame.index[-1], "open_time"] = frame["open_time"].iloc[-2]
    else:
        frame = frame.iloc[::-1]
    with pytest.raises(gate_inputs.GateInputError):
        gate_inputs._source_identity("M5", frame, inputs.event_at)


def test_pure_reducer_does_not_use_log_files_fetchers_or_clock(monkeypatch):
    import builtins
    from bot.data import market_data
    import utils.log as logging_module

    inputs, config, _ = _inputs(monkeypatch)
    prior = record_from_state(StrategyState(event_time=AT), event_at=AT)

    def prohibited(*args, **kwargs):
        pytest.fail("pure gate reducer reached I/O")

    monkeypatch.setattr(builtins, "open", prohibited)
    monkeypatch.setattr(market_data, "fetch_ohlcv", prohibited)
    monkeypatch.setattr(logging_module, "log", prohibited)
    result = gate_reducer.evaluate_strategy_gates(prior, inputs, AT, config)
    assert result.result()["action"] == "candidate_ready"
