"""Synthetic boundary mapping tests; not full empirical orchestration proof."""

from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace

import pytest

from bot.execution.lifecycle import create_entry_state, process_entry_event
from bot.execution.lifecycle.models import MarketEvent, MarketEventKind
from bot.execution.lifecycle.serialization import entry_intent_to_payload
from bot.execution.live_adapter import intent_from_strategy_entry
from bot.strategy.setup_intent import SetupSymbolMetadata, intent_from_setup_levels
from bot.strategy.setup_state import SetupStateRecord, record_from_state
from bot.strategy.trade_levels import LevelResult
from bot.state.gate_inputs import gate_event_id
from bot.validation.empirical_strategy_adapter import evaluate_setup_inputs
from strategies.smc_engine.strategy_state import StrategyState
from tests.phase8.test_gate_reducer import AT, _inputs


def _metadata():
    return SetupSymbolMetadata(
        "XAUUSDm", 0.01, 10, 2, AT - timedelta(days=1),
        AT + timedelta(days=1), "SYNTHETIC_TEST_ONLY",
    )


@pytest.mark.parametrize("failed", ["liquidity", "displacement", "internal", "score", "canonical", "entry"])
def test_rejected_setup_cannot_create_levels_or_intent(monkeypatch, failed):
    inputs, config, _ = _inputs(monkeypatch, failed)
    prior = record_from_state(StrategyState(event_time=AT), event_at=AT)
    result = evaluate_setup_inputs(prior, inputs, config, metadata=_metadata(), min_rr=3.0, partial_close_fraction=0.5)
    assert result.levels_json is None
    assert result.intent_json is None


def test_level_failure_has_no_intent_and_does_not_invent_anchor(monkeypatch):
    inputs, config, _ = _inputs(monkeypatch)
    prior = record_from_state(StrategyState(event_time=AT), event_at=AT)
    result = evaluate_setup_inputs(prior, inputs, config, metadata=_metadata(), min_rr=3.0, partial_close_fraction=0.5)
    assert json.loads(result.levels_json)["reason"].startswith("smc_stop_too_tight")
    assert result.intent_json is None


def test_same_live_level_mapping_and_phase3_intent(monkeypatch):
    import main

    inputs, config, frame = _inputs(monkeypatch)
    data = json.loads(inputs.payload)
    # Only this unit fixture uses explicit small-price synthetic level settings.
    data["profile"]["execution_levels"] = {"min_stop_points": 10}
    inputs = replace(inputs, payload=json.dumps(data, sort_keys=True, separators=(",", ":")))
    inputs = replace(inputs, event_id=gate_event_id(
        symbol=inputs.symbol, event_at=inputs.event_at, sources=inputs.source_identities,
        side=data["htf_bias"], payload=inputs.payload, config_fingerprint=inputs.config_fingerprint,
    ))
    prior = record_from_state(StrategyState(event_time=AT), event_at=AT)
    result = evaluate_setup_inputs(prior, inputs, config, metadata=_metadata(), min_rr=main.ACTIVE_RISK_ENGINE.min_rr, partial_close_fraction=0.5)
    context = result.transition.result()["context"]
    entry = dict(context["entry"])
    entry["ob_zone"] = context["ob"]["zone"]
    monkeypatch.setattr(main, "calculate_atr", lambda *a, **kw: 1.0)
    monkeypatch.setattr(main, "get_symbol_profile", lambda symbol: inputs.decoded()["profile"])
    trigger = entry["limit_entry"] if entry.get("entry_type") == "limit" else frame["close"].iloc[-1]
    stop, target, reason = main._build_orchestrator_trade_levels(
        SimpleNamespace(name="XAUUSDm", point=0.01, stops_level=10, digits=2),
        entry["direction"], trigger, entry, frame, context["internal_structure"],
        context["liquidity"]["structure_context"], context["liquidity"]["liquidity_pools"], min_rr_buffer=0.10,
    )
    assert json.loads(result.levels_json) == {"stop": stop, "target": target, "reason": reason}
    live = intent_from_strategy_entry(
        symbol="XAUUSDm", source_timeframe="M5", entry=entry, entry_frame=frame,
        stop_loss=stop, final_target=target, partial_close_fraction=0.5,
        configuration_id="XAUUSDm:M5:phase3",
        strategy_metadata={"strategy": "SMC_COURTROOM_ORCHESTRATOR", "setup_score": 8, "setup_grade": context["score"]["grade"]},
    )
    assert json.loads(result.intent_json) == entry_intent_to_payload(live)
    duplicate = evaluate_setup_inputs(SetupStateRecord(result.transition.state_record.payload), inputs, config, metadata=_metadata(), min_rr=main.ACTIVE_RISK_ENGINE.min_rr, partial_close_fraction=0.5)
    assert duplicate == result
    same_source = MarketEvent(
        event_id="source", timestamp=AT, symbol="XAUUSDm", source="synthetic",
        kind=MarketEventKind.BAR, sequence=0, open=100, high=102, low=98, close=100,
        bar_open_time=live.source_candle_open_time, source_candle_id=live.source_event_id,
    )
    prohibited = process_entry_event(create_entry_state(live), same_source)
    assert not prohibited.triggered
    assert prohibited.reason == "source_candle_barrier"
    later = replace(same_source, event_id="later", timestamp=AT + timedelta(minutes=5), bar_open_time=AT, source_candle_id="distinct-later-candle", sequence=1, open=trigger)
    assert process_entry_event(prohibited.state, later).triggered


def test_missing_effective_metadata_cannot_be_substituted():
    with pytest.raises(ValueError, match="effective"):
        _metadata().validate_at(AT + timedelta(days=1))


def test_rejected_levels_cannot_become_intent():
    with pytest.raises(ValueError, match="valid entry levels"):
        intent_from_setup_levels(
            symbol="XAUUSDm", source_timeframe="M5", context={}, entry_frame=None,
            levels=LevelResult(None, None, "missing"), partial_close_fraction=0.5,
            configuration_id="synthetic",
        )
