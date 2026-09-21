"""Real canonical gates, Phase 3 management and Phase 7 confirmed synthetic fills."""

from dataclasses import replace
from datetime import timedelta
import json

import pytest

from backtests.realistic_execution_replay import _metadata, _policy
from bot.backtesting.engine import HistoricalExecutionEngine
from bot.backtesting.models import HistoricalQuote
from bot.backtesting.adapters import process_quote_entry, quote_event, manage_quote_position
from bot.backtesting.fill_journal import HistoricalFillJournal
from bot.execution.broker.models import ExecutionAction, ExecutionStatus, ExecutionReason
from bot.execution.broker.registry import ExecutionRegistry, ExecutionRegistryStore
from bot.execution.lifecycle.entry import create_entry_state, process_entry_event, record_fill
from bot.execution.lifecycle.management import manage_position
from bot.execution.lifecycle.models import FillKind, ManagementConfig, LifecycleStatus, stable_id
from bot.strategy.config import StrategyConfig
from bot.strategy.setup_intent import SetupSymbolMetadata
from bot.strategy.setup_recovery import SetupRecoveryCoordinator
from bot.strategy.setup_state import record_from_state, state_from_record
from bot.strategy.setup_store import SetupReplayStore
from bot.validation.empirical_strategy_adapter import evaluate_historical_orchestration, evaluate_setup_inputs, prepare_setup_inputs
from strategies.smc_engine.strategy_state import StrategyState
from tests.phase8.test_full_orchestration_parity import _install
from tests.phase8.test_gate_reducer import AT


def _quote(instant, bid, ask, identity):
    return HistoricalQuote("XAUUSDm", instant, bid, ask, "synthetic-only", "synthetic-lifecycle", identity)


def _normalized(position):
    return {
        "status": position.status.value, "signal": position.signal_id,
        "direction": position.direction.value,
        "quantity": position.initial_quantity, "remaining": position.remaining_quantity,
        "closed": position.closed_quantity, "gross": position.realized_gross_pnl,
        "stop": position.current_stop, "partial": position.partial_close_occurred,
        "exit": position.exit_reason,
        "transitions": [(item.from_status.value, item.to_status.value, item.reason) for item in position.transitions],
    }


@pytest.mark.parametrize("side", ["bullish", "bearish"])
@pytest.mark.parametrize("ending", ["target", "break_even"])
@pytest.mark.parametrize("partial_entry", [False, True])
def test_full_live_mock_and_historical_lifecycle_restart_parity(monkeypatch, tmp_path, side, ending, partial_entry):
    gold, constituents, news = _install(monkeypatch, side)
    initial = record_from_state(StrategyState(event_time=AT), event_at=AT)
    result, decision_record = evaluate_historical_orchestration(
        gold, constituent_frames=constituents, decision_at=AT, news_context=news,
        prior_state=initial, active_trade_count=0, max_concurrent_trades=2,
    )
    assert result.action == "candidate_ready"
    inputs = prepare_setup_inputs(
        gold, decision_at=AT, news_context=news, dxy_context=result.context["dxy"], config=StrategyConfig(),
    )
    metadata = SetupSymbolMetadata("XAUUSDm", .01, 10, 2, AT - timedelta(days=1), AT + timedelta(days=1), "synthetic")
    evaluated = evaluate_setup_inputs(initial, inputs, StrategyConfig(), metadata=metadata, min_rr=3, partial_close_fraction=.5)
    from bot.execution.lifecycle.serialization import entry_intent_from_payload
    intent = entry_intent_from_payload(json.loads(evaluated.intent_json))
    assert evaluated.transition.state_record == decision_record
    broker_metadata = replace(_metadata(), effective_from=AT - timedelta(days=1), contract_size=1, tick_value=.01)
    engine = HistoricalExecutionEngine(run_id="synthetic", metadata=broker_metadata, policy=_policy(), initial_balance=1000)
    quote = _quote(AT + timedelta(seconds=1), intent.requested_trigger, intent.requested_trigger, "entry")
    journal = HistoricalFillJournal(tmp_path / "fills")
    offline_store = SetupReplayStore(tmp_path / "offline.json", identity="synthetic")
    offline_store.initialize(decision_record)
    offline = SetupRecoveryCoordinator(offline_store, journal.snapshot)
    # The source event must never reach a fill or a consumption callback.
    source_event = replace(quote_event(quote, sequence=0), timestamp=AT, source_candle_id=intent.source_event_id)
    assert not process_entry_event(create_entry_state(intent), source_event).triggered
    assert not offline_store.load().data()["consumption"]["events"]
    entry_decision, historical = process_quote_entry(
        engine, create_entry_state(intent), quote, sequence=1, quantity=.08,
        available_volume=.04 if partial_entry else None,
        setup_recovery=offline, setup_record=decision_record, fill_journal=journal,
    )
    assert historical is not None
    assert len(offline_store.load().data()["consumption"]["events"]) == 1
    live_store = SetupReplayStore(tmp_path / "live.json", identity="synthetic")
    live_store.initialize(decision_record)
    registry = ExecutionRegistry(ExecutionRegistryStore(tmp_path / "live-registry.json"))
    live = SetupRecoveryCoordinator(live_store, registry.snapshot)
    event = quote_event(quote, sequence=1)
    live_trade_id = stable_id(intent.signal_id, event.event_id, FillKind.LIVE_MARKET.value)
    live_binding = live.prepare(decision_record, intent, action_id="live-entry", trade_id=live_trade_id, entry_event=event)
    registry.prepare(action_id=live_binding.action_id, trade_id=live_trade_id, symbol="XAUUSDm", action_type=ExecutionAction.ENTRY, now=AT)
    registry.transition(live_binding.action_id, ExecutionStatus.PARTIALLY_FILLED if partial_entry else ExecutionStatus.CONFIRMED, quote.timestamp,
        reason=ExecutionReason.CONFIRMED, deal_ticket=1, position_ticket=2,
        executed_volume=historical.initial_quantity, executed_price=historical.fill_price)
    live_position = record_fill(entry_decision.state, event, fill_price=historical.fill_price,
        quantity=historical.initial_quantity, fill_kind=FillKind.LIVE_MARKET)
    assert live.confirm(live_binding, position=live_position).outcome == "CONSUMED"
    assert historical.initial_quantity == (.04 if partial_entry else .08)
    assert _normalized(live_position) == _normalized(historical)
    config = ManagementConfig(pnl_per_price_unit=1, volume_min=.01, volume_step=.01)
    partial = historical.partial_target
    quotes = [_quote(AT + timedelta(seconds=2), partial, partial, "partial")]
    exit_price = historical.final_target if ending == "target" else historical.fill_price
    quotes.append(_quote(AT + timedelta(seconds=3), exit_price, exit_price, "exit"))
    for sequence, observed in enumerate(quotes, 2):
        atr = historical.initial_risk_price / config.trailing_atr_multiple
        live_position = manage_position(live_position, quote_event(observed, sequence=sequence, atr=atr), config).position
        historical = manage_quote_position(engine, historical, observed, sequence=sequence, config=config, atr=atr)
        assert _normalized(live_position) == _normalized(historical)
    assert historical.status is LifecycleStatus.CLOSED
    assert historical.partial_close_occurred
    assert sum(item.gross_pnl for item in historical.pnl_components) == pytest.approx(historical.realized_gross_pnl)
    for store, provider in ((live_store, registry.snapshot), (offline_store, journal.snapshot)):
        restarted = SetupRecoveryCoordinator(SetupReplayStore(store.path, identity=store.identity), provider)
        assert restarted.reconcile().outcome == "DUPLICATE_IGNORED"
        restored = store.load()
        assert len(restored.data()["consumption"]["events"]) == 1
        repeated, replay_state = evaluate_historical_orchestration(
            gold, constituent_frames=constituents, decision_at=AT, news_context=news,
            prior_state=restored, active_trade_count=0, max_concurrent_trades=2,
        )
        assert repeated.action == "skip"
        assert repeated.reason == "setup_already_consumed"


def test_historical_outbox_immutable_and_malformed_fail_closed(tmp_path):
    from bot.backtesting.models import SimulatedFill, Side, FidelityClass, HistoricalExecutionError
    fill = SimulatedFill("fill", "entry", "trade", "position", AT, "XAUUSDm", Side.BUY,
                         .01, 100, 100, 100, 0, 0, False, "ENTRY_FILL", FidelityClass.TICK_BID_ASK)
    journal = HistoricalFillJournal(tmp_path / "fills")
    journal.publish(fill)
    journal.publish(fill)
    assert journal.snapshot() == {"entry": fill}
    with pytest.raises(HistoricalExecutionError):
        journal.publish(replace(fill, volume=.02))
    path = next(journal.directory.glob("*.json"))
    path.write_text("truncated", encoding="utf-8")
    with pytest.raises(HistoricalExecutionError):
        journal.snapshot()
