"""Versioned, deterministic records for the supported SMC setup state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Mapping

from strategies.smc_engine.strategy_state import StrategyState


STATE_SCHEMA = "phase8n.setup-state.v2"
SETUP_ID_SCHEMA = "phase8n.setup-id.v1"
STATE_FIELDS = (
    "state_name", "structure_dir", "liquidity_swept", "liquidity_side",
    "liquidity_type", "liquidity_index", "liquidity_time",
    "displacement_seen", "fvg_zone", "entry_started", "remaining_entries",
    "setup_candidate", "setup_score", "setup_grade", "trade_direction",
    "entry_mode", "ob_zone", "asian_sweep_detected", "bias_snapshot",
    "session_context", "news_status", "daily_limits_hit",
    "last_rejection_reason", "last_update", "_consecutive_same_dir_losses",
    "_last_trade_direction", "_last_trade_result", "_direction_blocked_until",
    "missing_conditions", "structure_state",
)


class SetupStateError(ValueError):
    """Setup state cannot be replayed or migrated safely."""


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SetupStateError("setup event time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat(), "aware": value.tzinfo is not None}
    if isinstance(value, tuple):
        return {"__type__": "tuple", "items": [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise SetupStateError("setup state contains non-string keys")
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SetupStateError("setup state contains non-finite value")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise SetupStateError(f"unsupported setup state type: {type(value).__name__}")


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        marker = value.get("__type__")
        if marker == "datetime":
            result = datetime.fromisoformat(value["value"])
            if bool(result.tzinfo is not None) != value["aware"]:
                raise SetupStateError("setup timestamp awareness mismatch")
            return result
        if marker == "tuple":
            return tuple(_decode(item) for item in value["items"])
        if marker is not None:
            raise SetupStateError("unknown setup state type tag")
        return {key: _decode(item) for key, item in value.items()}
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class SetupStateRecord:
    payload: str

    def data(self) -> dict[str, Any]:
        try:
            value = json.loads(self.payload)
        except (TypeError, ValueError) as exc:
            raise SetupStateError("setup state record is malformed") from exc
        if not isinstance(value, dict) or not isinstance(value.get("fields"), dict):
            raise SetupStateError("setup state record must be an object")
        if value.get("schema") != STATE_SCHEMA or set(value["fields"]) != set(STATE_FIELDS):
            raise SetupStateError("setup state schema or fields mismatch")
        from bot.strategy.setup_consumption import validate_history
        validate_history(value.get("consumption"))
        if not isinstance(value.get("last_event_at"), str):
            raise SetupStateError("setup state event time is missing")
        if _canonical(value) != self.payload:
            raise SetupStateError("setup state serialization is non-canonical")
        try:
            _utc(datetime.fromisoformat(value["last_event_at"]))
            decoded = {key: _decode(item) for key, item in value["fields"].items()}
        except (KeyError, TypeError, ValueError) as exc:
            raise SetupStateError("setup state fields or timestamp are malformed") from exc
        for key in ("liquidity_swept", "displacement_seen", "entry_started", "asian_sweep_detected", "daily_limits_hit"):
            if not isinstance(decoded[key], bool):
                raise SetupStateError("setup state flag has an invalid type")
        if not isinstance(decoded["last_update"], datetime) or decoded["last_update"].tzinfo is not None:
            raise SetupStateError("legacy state update must be explicit naive UTC")
        if not isinstance(decoded["remaining_entries"], list) or not isinstance(decoded["missing_conditions"], list):
            raise SetupStateError("setup state list has an invalid type")
        return value


def record_from_state(
    state: StrategyState, *, event_at: datetime,
    last_event_id: str | None = None, last_result: str | None = None,
) -> SetupStateRecord:
    event = _utc(event_at)
    fields = {key: _encode(getattr(state, key)) for key in STATE_FIELDS}
    return SetupStateRecord(_canonical({
        "schema": STATE_SCHEMA,
        "last_event_at": event.isoformat(),
        "last_event_id": last_event_id,
        "last_result": last_result,
        "fields": fields,
        "consumption": getattr(state, "_setup_consumption", {
            "schema": "phase8n.setup-consumption-history.v1",
            "bindings": {}, "events": {}, "blocked": {},
        }),
    }))


def state_from_record(record: SetupStateRecord, event_at: datetime) -> StrategyState:
    event = _utc(event_at)
    data = record.data()
    prior = _utc(datetime.fromisoformat(data["last_event_at"]))
    if event < prior:
        raise SetupStateError("setup event time cannot move backward")
    state = StrategyState(event_time=event)
    state._setup_consumption = data["consumption"]
    for key in STATE_FIELDS:
        setattr(state, key, _decode(data["fields"][key]))
    if state.last_update > event.replace(tzinfo=None):
        raise SetupStateError("setup state update lies in the future")
    return state


def stable_setup_id(
    *, symbol: str, side: str, decision_at: datetime,
    source_identities: Mapping[str, str], structure_identity: str,
    ob_identity: str | None, fvg_identity: str | None,
    sweep_identity: str | None, config_fingerprint: str,
    evaluation_identity: str | None = None,
) -> str:
    if symbol != "XAUUSDm" or side not in ("bullish", "bearish") or not source_identities:
        raise SetupStateError("setup identity is incomplete or not executable")
    material = _canonical({
        "schema": SETUP_ID_SCHEMA, "symbol": symbol, "side": side,
        "decision_at": _utc(decision_at).isoformat(),
        "sources": dict(source_identities), "structure": structure_identity,
        "order_block": ob_identity, "fvg": fvg_identity,
        "sweep": sweep_identity, "config": config_fingerprint,
        "evaluation": evaluation_identity,
    })
    return "s8n1_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def restore_setup_for_evaluation(record: SetupStateRecord, event_at: datetime) -> StrategyState:
    """Use the existing 120-minute expiry rule without erasing consumed history."""
    state = state_from_record(record, event_at)
    if state.is_expired():
        history = state._setup_consumption
        state.reset()
        state._setup_consumption = history
    elif record.data()["last_result"] is not None or record.data()["consumption"]["bindings"]:
        state._gate_record = record
    return state


@dataclass(frozen=True)
class LegacySetupMigration:
    status: str
    original_payload: str
    reason: str


def inspect_legacy_snapshot(snapshot: Mapping[str, Any]) -> LegacySetupMigration:
    """Read legacy diagnostics without silently adopting an active setup."""
    if not isinstance(snapshot, Mapping) or "state_name" not in snapshot:
        raise SetupStateError("legacy setup snapshot is malformed")
    original = _canonical(_encode(snapshot))
    if snapshot["state_name"] in ("TRADE_ACTIVE", "SETUP_FOUND_PENDING_CONFIRMATION"):
        return LegacySetupMigration("RECONCILIATION_REQUIRED", original, "legacy_active_setup_missing_identity")
    return LegacySetupMigration("READ_ONLY_LEGACY", original, "legacy_snapshot_not_restart_complete")
