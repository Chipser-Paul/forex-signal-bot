"""Pure setup consumption over existing broker/lifecycle fill evidence.

Bindings are prepared before execution. No trigger or broker submission is a
fill. Stores and adapters supply evidence; this module performs no I/O.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import math
from typing import Any, Mapping

from bot.execution.broker.models import ExecutionAction, ExecutionStatus, RegistryRecord
from bot.execution.lifecycle.models import EntryIntent, MarketEvent, PositionState
from bot.strategy.setup_state import SetupStateError, SetupStateRecord, _utc


CONSUMPTION_SCHEMA = "phase8n.setup-consumption-event.v1"
HISTORY_SCHEMA = "phase8n.setup-consumption-history.v1"
RESTART_CONTRACT = "phase8n.authoritative-fill-replay.v1"
RECOVERY_OUTCOME_SCHEMA = "phase8n.recovery-outcome.v1"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def semantic_id(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SetupEntryBinding:
    setup_id: str
    decision_id: str
    decision_payload: str
    intent_id: str
    intent_payload: str
    action_id: str
    trade_id: str
    symbol: str
    side: str
    available_at: str
    entry_event_id: str
    entry_event_at: str
    entry_tolerance: float
    source_identities: tuple[tuple[str, str], ...]
    config_fingerprint: str
    evidence_id: str
    block_id: str | None

    def __post_init__(self) -> None:
        for name in ("setup_id", "decision_id", "intent_id", "action_id", "trade_id",
                     "config_fingerprint", "evidence_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise SetupStateError("setup binding identity is incomplete")
        if self.symbol != "XAUUSDm" or self.side not in ("buy", "sell"):
            raise SetupStateError("setup binding is not executable")
        _utc(datetime.fromisoformat(self.available_at))
        if not math.isfinite(self.entry_tolerance) or self.entry_tolerance < 0:
            raise SetupStateError("entry tolerance is invalid")
        from bot.execution.lifecycle.serialization import entry_intent_from_payload
        intent = entry_intent_from_payload(json.loads(self.intent_payload))
        if (intent.signal_id, intent.symbol, intent.direction.value, intent.signal_available_at.isoformat()) != (
                self.intent_id, self.symbol, self.side, self.available_at):
            raise SetupStateError("setup binding intent does not match")
        approved = json.loads(self.decision_payload)
        expected = {
            "setup_id": self.setup_id, "decision_id": self.decision_id, "symbol": self.symbol,
            "side": self.side, "sources": dict(self.source_identities), "available_at": self.available_at,
            "requested_trigger": intent.requested_trigger, "config": self.config_fingerprint,
            "evidence": self.evidence_id, "action": "candidate_ready",
        }
        if canonical(approved) != canonical(expected):
            raise SetupStateError("setup binding approval relationship mismatch")
        if not self.entry_event_id or _utc(datetime.fromisoformat(self.entry_event_at)) < _utc(datetime.fromisoformat(self.available_at)):
            raise SetupStateError("entry event identity or chronology is invalid")
        if (not self.source_identities or tuple(sorted(self.source_identities)) != self.source_identities
                or len(dict(self.source_identities)) != len(self.source_identities)):
            raise SetupStateError("setup binding sources are missing or ambiguous")


def binding_from_decision(
    record: SetupStateRecord, intent: EntryIntent, *, action_id: str, trade_id: str,
    entry_event: MarketEvent, tolerance: float = 0.0,
) -> SetupEntryBinding:
    from bot.execution.lifecycle.entry import create_entry_state, process_entry_event
    from bot.execution.lifecycle.serialization import entry_intent_to_payload
    if not process_entry_event(create_entry_state(intent), entry_event, tolerance=tolerance).triggered:
        raise SetupStateError("entry event is not eligible under the lifecycle contract")
    data = record.data()
    result = json.loads(data["last_result"] or "null")
    if not isinstance(result, dict) or result.get("action") != "candidate_ready":
        raise SetupStateError("only an approved decision can bind an entry")
    context = result["context"]
    source = f"{intent.source_timeframe}:{intent.source_candle_open_time.isoformat()}:{intent.signal_available_at.isoformat()}"
    entry = context["entry"]
    trigger = entry.get("limit_entry") if entry.get("entry_type") == "limit" else context["source_close"]
    if (context["symbol"] != intent.symbol or context["entry"]["direction"] != intent.direction.value
            or data["last_event_id"] != result["event_id"]
            or intent.signal_available_at.isoformat() != context["signal_available_at"]
            or source != context["source_identities"].get(intent.source_timeframe)
            or trigger is None or not math.isclose(intent.requested_trigger, float(trigger), abs_tol=1e-9)):
        raise SetupStateError("decision and intent identities mismatch")
    return SetupEntryBinding(
        setup_id=result["setup_id"], decision_id=result["event_id"], intent_id=intent.signal_id,
        decision_payload=canonical({
            "setup_id": result["setup_id"], "decision_id": result["event_id"], "symbol": intent.symbol,
            "side": entry["direction"], "sources": context["source_identities"],
            "available_at": context["signal_available_at"], "requested_trigger": intent.requested_trigger,
            "config": context["config_fingerprint"], "evidence": context["evidence_id"],
            "action": result["action"],
        }),
        intent_payload=canonical(entry_intent_to_payload(intent)),
        action_id=action_id, trade_id=trade_id, symbol=intent.symbol, side=intent.direction.value,
        available_at=intent.signal_available_at.isoformat(),
        entry_event_id=entry_event.event_id, entry_event_at=entry_event.timestamp.isoformat(),
        entry_tolerance=tolerance,
        source_identities=tuple(sorted(context["source_identities"].items())),
        config_fingerprint=context["config_fingerprint"], evidence_id=context["evidence_id"],
        block_id=(context.get("strategy_decision", {}).get("invalidation") or {}).get("order_block_id"),
    )


def _binding(value: Mapping[str, Any]) -> SetupEntryBinding:
    value = dict(value)
    value["source_identities"] = tuple(tuple(pair) for pair in value["source_identities"])
    return SetupEntryBinding(**value)


def validate_history(value: Any) -> None:
    try:
        if (not isinstance(value, dict) or set(value) != {"schema", "bindings", "events", "blocked"}
                or value["schema"] != HISTORY_SCHEMA):
            raise ValueError("history schema mismatch")
        for field in ("bindings", "events", "blocked"):
            if not isinstance(value[field], dict):
                raise ValueError("history collection is malformed")
        for key, item in value["bindings"].items():
            if _binding(item).setup_id != key:
                raise ValueError("binding key mismatch")
        for key, item in value["events"].items():
            binding = _binding(value["bindings"][key])
            expected_fields = {*asdict(binding), "schema", "fill_id", "executed_volume", "timestamp", "reason", "event_id"}
            if set(item) != expected_fields:
                raise ValueError("consumption event fields mismatch")
            if (item["schema"] != CONSUMPTION_SCHEMA or item["setup_id"] != key
                    or item["reason"] != "CONFIRMED_ENTRY_FILL"
                    or not math.isfinite(item["executed_volume"]) or item["executed_volume"] <= 0):
                raise ValueError("consumption event malformed")
            if canonical({name: item[name] for name in asdict(binding)}) != canonical(asdict(binding)):
                raise ValueError("consumption binding mismatch")
            material = {name: item[name] for name in item if name != "event_id"}
            if item["event_id"] != semantic_id("consume_", material):
                raise ValueError("consumption event hash mismatch")
            rebuilt = SetupConsumptionEvent(binding, item["fill_id"], item["executed_volume"], item["timestamp"]).to_dict()
            if canonical(rebuilt) != canonical(item):
                raise ValueError("consumption event validation mismatch")
        if any(key not in value["bindings"] or not isinstance(reason, str) or not reason
               for key, reason in value["blocked"].items()):
            raise ValueError("blocked setup identity missing")
        canonical(value)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise SetupStateError("setup consumption history is corrupt") from exc


def _with_history(record: SetupStateRecord, history: dict[str, Any]) -> SetupStateRecord:
    validate_history(history)
    data = record.data()
    data["consumption"] = history
    return SetupStateRecord(canonical(data))


def register_binding(record: SetupStateRecord, binding: SetupEntryBinding) -> SetupStateRecord:
    history = record.data()["consumption"]
    existing = history["bindings"].get(binding.setup_id)
    if existing is not None and canonical(existing) != canonical(asdict(binding)):
        raise SetupStateError("setup is already bound to another entry")
    if setup_reuse_reason(record, binding.setup_id, binding.evidence_id):
        raise SetupStateError("setup reuse requires reconciliation or is consumed")
    if any(item["intent_id"] == binding.intent_id and key != binding.setup_id
           for key, item in history["bindings"].items()):
        raise SetupStateError("duplicate intent identity")
    history["bindings"][binding.setup_id] = json.loads(canonical(asdict(binding)))
    history["blocked"][binding.setup_id] = "entry_pending_confirmation"
    return _with_history(record, history)


def setup_reuse_reason(record: SetupStateRecord, setup_id: str, evidence_id: str) -> str | None:
    history = record.data()["consumption"]
    for key, binding in history["bindings"].items():
        if key == setup_id or binding["evidence_id"] == evidence_id:
            if key in history["blocked"]:
                return history["blocked"][key]
            if key in history["events"]:
                return "setup_already_consumed"
    return None


@dataclass(frozen=True)
class ClassifiedEntryFill:
    outcome: str
    binding: SetupEntryBinding
    fill_id: str | None = None
    executed_volume: float = 0.0
    timestamp: str | None = None


def classify_confirmed_entry_fill(
    binding: SetupEntryBinding, evidence: RegistryRecord | Any | None,
    *, position: PositionState | None = None,
) -> ClassifiedEntryFill:
    """Use Phase 5 confirmed registry or Phase 7 entry-fill classifications.

    No broker object is accepted as an owned position just because its symbol
    matches. Live callers use the secured registry; offline callers use its
    simulated entry ledger. Durable evidence must precede reducer persistence.
    """
    from bot.backtesting.models import SimulatedFill

    if evidence is None:
        return ClassifiedEntryFill("UNCERTAIN_BLOCKED", binding)
    if isinstance(evidence, RegistryRecord):
        if evidence.action_type is not ExecutionAction.ENTRY:
            return ClassifiedEntryFill("UNRELATED_FILL_IGNORED", binding)
        if (evidence.action_id, evidence.trade_id, evidence.symbol) != (
                binding.action_id, binding.trade_id, binding.symbol):
            return ClassifiedEntryFill("IDENTITY_MISMATCH_BLOCKED", binding)
        if evidence.state in (ExecutionStatus.SUBMITTING, ExecutionStatus.UNCERTAIN,
                              ExecutionStatus.RECONCILIATION_REQUIRED):
            return ClassifiedEntryFill("UNCERTAIN_BLOCKED", binding)
        if evidence.state not in (ExecutionStatus.CONFIRMED, ExecutionStatus.PARTIALLY_FILLED):
            return ClassifiedEntryFill("REJECTED_UNFILLED" if evidence.state is ExecutionStatus.REJECTED else "UNCERTAIN_BLOCKED", binding)
        volume, price = evidence.executed_volume, evidence.executed_price
        # Phase 3 records the confirmed position at its ordered entry event.
        # Registry updated_at is receipt telemetry, not semantic fill identity.
        timestamp = _utc(datetime.fromisoformat(binding.entry_event_at))
        if evidence.deal_ticket is None or evidence.position_ticket is None:
            return ClassifiedEntryFill("UNCERTAIN_BLOCKED", binding)
        fill_id = str(evidence.deal_ticket)
    elif isinstance(evidence, SimulatedFill):
        if evidence.reason_code not in ("ENTRY_FILL", "PARTIAL_ENTRY_FILL"):
            return ClassifiedEntryFill("UNRELATED_FILL_IGNORED", binding)
        if (evidence.action_id, evidence.trade_id, evidence.symbol, evidence.side.value.lower()) != (
                binding.action_id, binding.trade_id, binding.symbol, binding.side):
            return ClassifiedEntryFill("IDENTITY_MISMATCH_BLOCKED", binding)
        volume, price, timestamp = evidence.volume, evidence.fill_price, evidence.timestamp
        fill_id = evidence.fill_id
    else:
        return ClassifiedEntryFill("UNRELATED_FILL_IGNORED", binding)
    if volume <= 0:
        return ClassifiedEntryFill("UNRELATED_FILL_IGNORED", binding)
    if (not math.isfinite(volume) or price is None or not math.isfinite(price) or price <= 0
            or timestamp < _utc(datetime.fromisoformat(binding.available_at))):
        return ClassifiedEntryFill("IDENTITY_MISMATCH_BLOCKED", binding)
    if position is not None and (
            (position.signal_id, position.trade_id, position.symbol, position.direction.value) !=
            (binding.intent_id, binding.trade_id, binding.symbol, binding.side)
            or position.initial_quantity > volume + 1e-9):
        return ClassifiedEntryFill("IDENTITY_MISMATCH_BLOCKED", binding)
    return ClassifiedEntryFill("CONSUMED", binding, fill_id, volume, timestamp.isoformat())


@dataclass(frozen=True)
class ConsumptionTransition:
    outcome: str
    state_record: SetupStateRecord
    event_json: str | None = None
    state_changed: bool = False
    consumption_applied: bool = False
    consumption_already_present: bool = False
    binding_released: bool = False
    reconciliation_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RECOVERY_OUTCOME_SCHEMA, "outcome": self.outcome,
            "state_record": self.state_record.data(), "event_json": self.event_json,
            "state_changed": self.state_changed, "consumption_applied": self.consumption_applied,
            "consumption_already_present": self.consumption_already_present,
            "binding_released": self.binding_released,
            "reconciliation_required": self.reconciliation_required,
        }


def _transition(before: SetupStateRecord, after: SetupStateRecord, outcome: str,
                event_json: str | None = None, *, applied: bool = False,
                already_present: bool = False, released: bool = False,
                required: bool = False) -> ConsumptionTransition:
    return ConsumptionTransition(outcome, after, event_json, after != before,
                                 applied, already_present, released, required)


@dataclass(frozen=True)
class SetupConsumptionEvent:
    """Immutable semantic event, including the full pre-execution binding."""
    binding: SetupEntryBinding
    fill_id: str
    executed_volume: float
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        if (not self.fill_id or isinstance(self.executed_volume, bool)
                or not math.isfinite(self.executed_volume) or self.executed_volume <= 0
                or _utc(datetime.fromisoformat(self.timestamp)) < _utc(datetime.fromisoformat(self.binding.available_at))):
            raise SetupStateError("consumption requires a causal positive confirmed fill")
        material = {
            **asdict(self.binding), "schema": CONSUMPTION_SCHEMA,
            "fill_id": self.fill_id, "executed_volume": self.executed_volume,
            "timestamp": self.timestamp, "reason": "CONFIRMED_ENTRY_FILL",
        }
        return {**material, "event_id": semantic_id("consume_", material)}


def apply_setup_consumption(record: SetupStateRecord, fill: ClassifiedEntryFill) -> ConsumptionTransition:
    try:
        data = record.data()
        history = data["consumption"]
        key = fill.binding.setup_id
        registered = history["bindings"].get(key)
        if registered is None or canonical(registered) != canonical(asdict(fill.binding)):
            return _transition(record, record, "IDENTITY_MISMATCH_BLOCKED", required=True)
        if fill.outcome in ("UNCERTAIN_BLOCKED", "IDENTITY_MISMATCH_BLOCKED"):
            history["blocked"][key] = fill.outcome.lower()
            return _transition(record, _with_history(record, history), fill.outcome, required=True)
        if fill.outcome == "REJECTED_UNFILLED" and key not in history["events"]:
            released = key in history["blocked"]
            history["blocked"].pop(key, None)
            return _transition(record, _with_history(record, history), "UNRELATED_FILL_IGNORED",
                               released=released, required=bool(history["blocked"]))
        if fill.outcome != "CONSUMED":
            return _transition(record, record, "UNRELATED_FILL_IGNORED", required=bool(history["blocked"]))
        if key in history["events"]:
            history["blocked"].pop(key, None)
            return _transition(record, _with_history(record, history), "DUPLICATE_IGNORED",
                               canonical(history["events"][key]), already_present=True,
                               required=bool(history["blocked"]))
        event = SetupConsumptionEvent(fill.binding, fill.fill_id, fill.executed_volume, fill.timestamp).to_dict()
        history["events"][key] = json.loads(canonical(event))
        history["blocked"].pop(key, None)
        return _transition(record, _with_history(record, history), "CONSUMED", canonical(event),
                           applied=True, required=bool(history["blocked"]))
    except (SetupStateError, TypeError, ValueError, KeyError):
        return _transition(record, record, "STATE_CORRUPT", required=True)


def reconcile_setup_consumption(
    record: SetupStateRecord, authoritative: Mapping[str, Any],
) -> ConsumptionTransition:
    """Replay the fill-before-consumption crash boundary, without cross-file atomicity."""
    try:
        history = record.data()["consumption"]
        current = record
        applied = already_present = released = unrelated = False

        def summary(outcome: str, *, required: bool = False) -> ConsumptionTransition:
            return _transition(record, current, outcome, applied=applied,
                               already_present=already_present, released=released, required=required)

        for key, raw in sorted(history["bindings"].items()):
            binding = _binding(raw)
            classified = classify_confirmed_entry_fill(binding, authoritative.get(binding.action_id))
            if key in history["events"]:
                event = history["events"][key]
                if (classified.outcome != "CONSUMED"
                        or classified.executed_volume < event["executed_volume"]):
                    current_history = current.data()["consumption"]
                    current_history["blocked"][key] = "consumption_missing_authoritative_fill"
                    current = _with_history(current, current_history)
                    continue
            transition = apply_setup_consumption(current, classified)
            current = transition.state_record
            applied |= transition.consumption_applied
            already_present |= transition.consumption_already_present
            released |= transition.binding_released
            unrelated |= transition.outcome == "UNRELATED_FILL_IGNORED"
            if transition.outcome in ("STATE_CORRUPT", "IDENTITY_MISMATCH_BLOCKED"):
                return summary(transition.outcome, required=True)
        if current.data()["consumption"]["blocked"]:
            return summary("UNCERTAIN_BLOCKED", required=True)
        # Cleanup and matched replay can both mutate state without a new fill.
        return summary("CONSUMED" if applied else
                       "UNRELATED_FILL_IGNORED" if unrelated else "DUPLICATE_IGNORED")
    except (SetupStateError, TypeError, ValueError, KeyError):
        return _transition(record, record, "STATE_CORRUPT", required=True)
