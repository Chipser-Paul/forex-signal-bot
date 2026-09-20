"""Synthetic authoritative-fill and restart tests; no empirical inputs."""

from dataclasses import replace
from datetime import timedelta
import json

import pytest

from bot.execution.broker.models import ExecutionAction, ExecutionStatus, RegistryRecord
from bot.execution.broker.registry import ExecutionRegistry, ExecutionRegistryStore
from bot.execution.lifecycle.entry import new_entry_intent
from bot.execution.lifecycle.models import Direction, ReadinessStyle, MarketEvent, MarketEventKind
from bot.state.gate_reducer import evaluate_strategy_gates
from bot.strategy.setup_consumption import (
    ClassifiedEntryFill, SetupEntryBinding, apply_setup_consumption,
    binding_from_decision, classify_confirmed_entry_fill, reconcile_setup_consumption,
    register_binding, setup_reuse_reason,
)
from bot.strategy.setup_recovery import SetupRecoveryCoordinator
from bot.strategy.setup_state import SetupStateError, SetupStateRecord, record_from_state, state_from_record
from bot.strategy.setup_store import SetupReplayStore
from strategies.smc_engine.strategy_state import StrategyState
from tests.phase8.test_gate_reducer import AT, _inputs


def _fixture(monkeypatch, tmp_path, side="buy"):
    inputs, config, frame = _inputs(monkeypatch)
    if side == "sell":
        from bot.state.gate_inputs import gate_event_id
        data = json.loads(inputs.payload)
        data["htf_bias"] = "bearish"
        data["bias_snapshot"]["htf_bias"]["direction"] = "bearish"
        data["bias_resolution"]["direction"] = "bearish"
        data["liquidity_context"]["structure_context"]["structure"] = "bearish"
        data["liquidity_context"]["structure_context"]["premium_zone"] = [101, 105]
        data["liquidity_signal"]["side"] = "buy"
        data["liquidity_signal"]["type"] = "equal_highs"
        from bot.strategy.setup_consumption import canonical
        inputs = replace(inputs, payload=canonical(data))
        inputs = replace(inputs, event_id=gate_event_id(symbol=inputs.symbol, event_at=inputs.event_at,
            sources=inputs.source_identities, side="bearish", payload=inputs.payload, config_fingerprint=inputs.config_fingerprint))
    initial = record_from_state(StrategyState(event_time=AT), event_at=AT)
    transition = evaluate_strategy_gates(initial, inputs, AT, config)
    assert transition.result()["action"] == "candidate_ready", transition.result()
    intent = new_entry_intent(
        symbol="XAUUSDm", direction=Direction(side), source_timeframe="M5",
        source_candle_open_time=frame.open_time.iloc[-1].to_pydatetime(),
        signal_available_at=AT, requested_trigger=100, stop_loss=90 if side == "buy" else 110,
        final_target=130 if side == "buy" else 70,
        readiness_style=ReadinessStyle.IMMEDIATE,
    )
    event = MarketEvent("entry-event-1", AT + timedelta(seconds=1), "XAUUSDm", "synthetic", MarketEventKind.TICK, 1, bid=100, ask=100)
    binding = binding_from_decision(transition.state_record, intent, action_id="entry-action-1", trade_id="trade-1", entry_event=event)
    store = SetupReplayStore(tmp_path / "setup.json", identity="synthetic-account-policy")
    store.initialize(transition.state_record)
    registry = ExecutionRegistry(ExecutionRegistryStore(tmp_path / "registry.json"))
    registry.prepare(action_id=binding.action_id, trade_id=binding.trade_id,
                     symbol=binding.symbol, action_type=ExecutionAction.ENTRY, now=AT)
    coordinator = SetupRecoveryCoordinator(store, registry.snapshot)
    coordinator.prepare(transition.state_record, intent, action_id=binding.action_id, trade_id=binding.trade_id, entry_event=event)
    return inputs, config, binding, store, registry, coordinator


def _confirm(registry, binding, *, volume=0.02, state=ExecutionStatus.CONFIRMED):
    from bot.execution.broker.models import ExecutionReason
    return registry.transition(binding.action_id, state, AT + timedelta(seconds=1),
        reason=ExecutionReason.CONFIRMED, order_ticket=1, deal_ticket=2,
        position_ticket=3, executed_volume=volume, executed_price=100.0)


def test_confirmed_fill_is_consumed_durably_once(monkeypatch, tmp_path):
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding)
    transition = recovery.confirm(binding)
    assert transition.outcome == "CONSUMED"
    event = json.loads(transition.event_json)
    assert event["reason"] == "CONFIRMED_ENTRY_FILL"
    assert event["executed_volume"] == 0.02
    assert event["setup_id"] == binding.setup_id
    assert recovery.confirm(binding).outcome == "DUPLICATE_IGNORED"
    assert recovery.reconcile().outcome == "DUPLICATE_IGNORED"
    restarted = SetupReplayStore(store.path, identity=store.identity).load()
    assert restarted == store.load()
    assert len(restarted.data()["consumption"]["events"]) == 1


@pytest.mark.parametrize("state", [ExecutionStatus.PREPARED, ExecutionStatus.CHECKED,
    ExecutionStatus.SUBMITTING, ExecutionStatus.UNCERTAIN, ExecutionStatus.RECONCILIATION_REQUIRED,
    ExecutionStatus.REJECTED])
def test_nonfills_do_not_consume(monkeypatch, tmp_path, state):
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding, volume=0.0, state=state)
    result = recovery.confirm(binding)
    assert result.outcome != "CONSUMED"
    assert not store.load().data()["consumption"]["events"]
    if state in (ExecutionStatus.SUBMITTING, ExecutionStatus.UNCERTAIN, ExecutionStatus.RECONCILIATION_REQUIRED):
        assert result.outcome == "UNCERTAIN_BLOCKED"
        assert setup_reuse_reason(store.load(), binding.setup_id, binding.evidence_id)


def test_zero_confirmed_volume_does_not_consume(monkeypatch, tmp_path):
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding, volume=0)
    assert recovery.confirm(binding).outcome == "UNRELATED_FILL_IGNORED"
    assert not store.load().data()["consumption"]["events"]


def test_positive_partial_entry_and_later_remainder_consume_once(monkeypatch, tmp_path):
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding, volume=0.01, state=ExecutionStatus.PARTIALLY_FILLED)
    first = recovery.confirm(binding)
    assert first.outcome == "CONSUMED"
    _confirm(registry, binding, volume=0.02)
    assert recovery.confirm(binding).outcome == "DUPLICATE_IGNORED"
    assert recovery.reconcile().outcome == "DUPLICATE_IGNORED"
    assert list(store.load().data()["consumption"]["events"].values())[0]["executed_volume"] == 0.01


@pytest.mark.parametrize("action", [ExecutionAction.PARTIAL_CLOSE, ExecutionAction.FULL_CLOSE,
                                   ExecutionAction.MODIFY_STOP, ExecutionAction.LIQUIDATE])
def test_nonentry_fills_never_consume(monkeypatch, tmp_path, action):
    _, _, binding, store, registry, _ = _fixture(monkeypatch, tmp_path)
    evidence = replace(_confirm(registry, binding), action_type=action)
    classified = classify_confirmed_entry_fill(binding, evidence)
    assert classified.outcome == "UNRELATED_FILL_IGNORED"
    assert apply_setup_consumption(store.load(), classified).outcome == "UNRELATED_FILL_IGNORED"


def test_crash_after_durable_fill_replays_once(monkeypatch, tmp_path):
    _, _, binding, store, registry, _ = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding)
    restarted_registry = ExecutionRegistry(ExecutionRegistryStore(registry.store.path))
    restarted = SetupRecoveryCoordinator(SetupReplayStore(store.path, identity=store.identity), restarted_registry.snapshot)
    assert restarted.reconcile().outcome == "CONSUMED"
    assert restarted.reconcile().outcome == "DUPLICATE_IGNORED"


def test_crash_after_consumption_before_acknowledgement_is_noop(monkeypatch, tmp_path):
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding)
    recovery.confirm(binding)
    restarted = SetupRecoveryCoordinator(SetupReplayStore(store.path, identity=store.identity), registry.snapshot)
    assert restarted.reconcile().outcome == "DUPLICATE_IGNORED"


def test_consumption_without_authoritative_evidence_fails_closed(monkeypatch, tmp_path):
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding)
    recovery.confirm(binding)
    result = reconcile_setup_consumption(store.load(), {})
    assert result.outcome == "UNCERTAIN_BLOCKED"
    assert setup_reuse_reason(result.state_record, binding.setup_id, binding.evidence_id) == "consumption_missing_authoritative_fill"


def test_foreign_position_and_identity_mismatch_never_adopt(monkeypatch, tmp_path):
    _, _, binding, store, registry, _ = _fixture(monkeypatch, tmp_path)
    evidence = replace(_confirm(registry, binding), trade_id="foreign-trade")
    result = apply_setup_consumption(store.load(), classify_confirmed_entry_fill(binding, evidence))
    assert result.outcome == "IDENTITY_MISMATCH_BLOCKED"
    assert not result.state_record.data()["consumption"]["events"]
    assert classify_confirmed_entry_fill(binding, {"symbol": "XAUUSDm", "magic": 0}).outcome == "UNRELATED_FILL_IGNORED"


def test_same_source_evidence_cannot_regenerate_actionable_setup(monkeypatch, tmp_path):
    inputs, config, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding)
    recovery.confirm(binding)
    evaluated = evaluate_strategy_gates(store.load(), inputs, AT, config)
    assert evaluated.result()["action"] == "skip"
    assert evaluated.result()["reason"] == "setup_already_consumed"
    assert setup_reuse_reason(store.load(), "another-decision-setup-id", binding.evidence_id) == "setup_already_consumed"
    assert setup_reuse_reason(store.load(), "new-evidence", "materially-new-source") is None
    with pytest.raises(SetupStateError):
        register_binding(store.load(), binding)


def test_corrupt_history_and_binding_reject(monkeypatch, tmp_path):
    _, _, binding, store, registry, _ = _fixture(monkeypatch, tmp_path)
    corrupt = replace(store.load(), payload="null")
    result = apply_setup_consumption(corrupt, classify_confirmed_entry_fill(binding, _confirm(registry, binding)))
    assert result.outcome == "STATE_CORRUPT"
    with pytest.raises(SetupStateError):
        SetupEntryBinding(**{**binding.__dict__, "symbol": "XAUUSD"})


@pytest.mark.parametrize("field,value", [("decision_id", "different-decision"),
    ("config_fingerprint", "different-config"), ("evidence_id", "different-evidence")])
def test_binding_must_preserve_approved_decision_relationship(monkeypatch, tmp_path, field, value):
    _, _, binding, _, _, _ = _fixture(monkeypatch, tmp_path)
    with pytest.raises(SetupStateError, match="approval relationship"):
        replace(binding, **{field: value})


def test_new_completed_source_can_form_distinct_actionable_setup(monkeypatch, tmp_path):
    from bot.state.gate_inputs import build_gate_inputs
    inputs, config, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding)
    recovery.confirm(binding)
    data = inputs.decoded()
    from tests.phase8.test_gate_reducer import _frame
    frame = _frame()
    for column in ("open_time", "available_at"):
        frame[column] = frame[column] + timedelta(minutes=5)
    next_at = AT + timedelta(minutes=5)
    next_inputs = build_gate_inputs(
        symbol=inputs.symbol, event_at=next_at, frames={"H1": frame, "M5": frame, "M15": frame},
        profile=data["profile"], htf_bias=data["htf_bias"], bias_snapshot=data["bias_snapshot"],
        bias_resolution=data["bias_resolution"], liquidity_context=data["liquidity_context"],
        dxy_context=data["dxy_context"], news_context=data["news_context"],
        session_context=data["session_context"], config=config,
    )
    transition = evaluate_strategy_gates(store.load(), next_inputs, next_at, config)
    assert transition.result()["action"] == "candidate_ready"
    assert transition.setup_id != binding.setup_id
    assert transition.result()["context"]["evidence_id"] != binding.evidence_id
    assert transition.state_record.data()["consumption"] == store.load().data()["consumption"]


@pytest.mark.parametrize("side,price", [("buy", 100.25), ("sell", 99.75)])
def test_binding_preserves_existing_lifecycle_readiness_tolerance(monkeypatch, tmp_path, side, price):
    _, _, binding, store, _, _ = _fixture(monkeypatch, tmp_path, side=side)
    from bot.execution.lifecycle.serialization import entry_intent_from_payload
    intent = replace(entry_intent_from_payload(json.loads(binding.intent_payload)), readiness_style=ReadinessStyle.PULLBACK)
    decision = store.load()
    event = MarketEvent("tolerated-event", AT + timedelta(seconds=1), "XAUUSDm", "synthetic",
                        MarketEventKind.TICK, 1, bid=price, ask=price)
    with pytest.raises(SetupStateError, match="not eligible"):
        binding_from_decision(decision, intent, action_id="tolerated-entry", trade_id="tolerated-trade", entry_event=event)
    prepared = binding_from_decision(decision, intent, action_id="tolerated-entry", trade_id="tolerated-trade", entry_event=event, tolerance=.5)
    assert prepared.entry_tolerance == .5


def test_store_identity_checksum_and_missing_state_are_fail_closed(monkeypatch, tmp_path):
    _, _, _, store, _, _ = _fixture(monkeypatch, tmp_path)
    with pytest.raises(SetupStateError):
        SetupReplayStore(store.path, identity="another-account").load()
    initial = store.load()
    store.path.unlink()
    store.backup.unlink()
    with pytest.raises(SetupStateError, match="disappeared"):
        store.initialize(initial)


def test_interrupted_replace_preserves_prior_record(monkeypatch, tmp_path):
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    import bot.strategy.setup_store as module
    initial = store.load()
    _confirm(registry, binding)
    real_replace = module.os.replace
    def interrupted(source, target):
        if str(target) == str(store.path):
            raise OSError("synthetic crash before replace")
        return real_replace(source, target)
    with monkeypatch.context() as isolated:
        isolated.setattr(module.os, "replace", interrupted)
        with pytest.raises(OSError):
            recovery.confirm(binding)
    assert store.load() == initial
    assert not list(tmp_path.glob("*.tmp"))
    assert recovery.reconcile().outcome == "CONSUMED"


def test_corrupt_primary_recovers_valid_backup(monkeypatch, tmp_path):
    _, _, _, store, _, _ = _fixture(monkeypatch, tmp_path)
    expected = store.load()
    store.path.write_text("{truncated", encoding="utf-8")
    assert store.load() == expected
    store.path.write_text("{truncated", encoding="utf-8")
    store.backup.write_text("{truncated", encoding="utf-8")
    with pytest.raises(SetupStateError):
        store.load()


def test_receipt_telemetry_does_not_change_consumption_identity(monkeypatch, tmp_path):
    _, _, binding, store, registry, _ = _fixture(monkeypatch, tmp_path)
    evidence = _confirm(registry, binding)
    delayed = replace(evidence, updated_at=AT + timedelta(hours=1))
    first = apply_setup_consumption(store.load(), classify_confirmed_entry_fill(binding, evidence))
    second = apply_setup_consumption(store.load(), classify_confirmed_entry_fill(binding, delayed))
    assert first == second


def test_expiry_retains_history_and_does_not_refresh_without_events(monkeypatch, tmp_path):
    from bot.strategy.setup_state import restore_setup_for_evaluation
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding)
    recovery.confirm(binding)
    original = store.load()
    before = restore_setup_for_evaluation(original, AT + timedelta(minutes=120))
    assert before.last_update == state_from_record(original, AT).last_update
    expired = restore_setup_for_evaluation(original, AT + timedelta(minutes=120, microseconds=1))
    assert expired._setup_consumption == original.data()["consumption"]
    assert expired.is_expired() is False
    assert setup_reuse_reason(original, binding.setup_id, binding.evidence_id) == "setup_already_consumed"


def test_post_replace_pre_ack_failure_recovers_no_duplicate(monkeypatch, tmp_path):
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding)
    real_write = store._atomic_write
    def fail_backup(path, content):
        if path == store.backup:
            raise OSError("synthetic backup/ack interruption")
        return real_write(path, content)
    with monkeypatch.context() as patch:
        patch.setattr(store, "_atomic_write", fail_backup)
        with pytest.raises(OSError):
            recovery.confirm(binding)
    assert len(store.load().data()["consumption"]["events"]) == 1
    assert recovery.reconcile().outcome == "DUPLICATE_IGNORED"


def test_concurrent_confirmations_emit_one_consumption(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    _, _, binding, store, registry, recovery = _fixture(monkeypatch, tmp_path)
    _confirm(registry, binding)
    def consume(_):
        separate = SetupRecoveryCoordinator(SetupReplayStore(store.path, identity=store.identity), registry.snapshot)
        return separate.confirm(binding).outcome
    with ThreadPoolExecutor(max_workers=4) as workers:
        outcomes = list(workers.map(consume, range(8)))
    assert outcomes.count("CONSUMED") == 1
    assert outcomes.count("DUPLICATE_IGNORED") == 7
    assert len(store.load().data()["consumption"]["events"]) == 1
