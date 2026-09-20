from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from .models import (
    Direction,
    ExitReason,
    FillKind,
    LifecycleStatus,
    LifecycleTransition,
    PnlComponent,
    PositionState,
    EntryIntent,
    EntryMode,
    ReadinessStyle,
    as_utc,
    stable_id,
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def position_to_payload(position: PositionState) -> dict[str, Any]:
    return _json_value(asdict(position))


def entry_intent_to_payload(intent) -> dict[str, Any]:
    """Canonical JSON-compatible representation without adapter-specific IDs."""
    return _json_value(asdict(intent))


def entry_intent_from_payload(payload: Mapping[str, Any]) -> EntryIntent:
    if set(payload) != set(EntryIntent.__dataclass_fields__):
        raise ValueError("entry intent schema mismatch")
    values = dict(payload)
    values["direction"] = Direction(values["direction"])
    values["entry_mode"] = EntryMode(values["entry_mode"])
    values["readiness_style"] = ReadinessStyle(values["readiness_style"])
    for name in ("source_candle_open_time", "signal_available_at", "expires_at"):
        if values[name] is not None:
            values[name] = datetime.fromisoformat(values[name].replace("Z", "+00:00"))
    return EntryIntent(**values)


def _parse_reason(value: str | None) -> ExitReason | str | None:
    if value is None:
        return None
    try:
        return ExitReason(value)
    except ValueError:
        return value


def position_from_payload(payload: Mapping[str, Any]) -> PositionState:
    transitions = tuple(
        LifecycleTransition(
            transition_id=str(item["transition_id"]),
            event_id=str(item["event_id"]),
            timestamp=datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00")),
            from_status=LifecycleStatus(item["from_status"]),
            to_status=LifecycleStatus(item["to_status"]),
            reason=str(item["reason"]),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in payload.get("transitions", [])
    )
    components = tuple(
        PnlComponent(
            action_id=str(item["action_id"]),
            timestamp=datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00")),
            quantity=float(item["quantity"]),
            entry_price=float(item["entry_price"]),
            exit_price=float(item["exit_price"]),
            gross_pnl=float(item["gross_pnl"]),
            reason=_parse_reason(str(item["reason"])) or "unknown",
        )
        for item in payload.get("pnl_components", [])
    )
    return PositionState(
        trade_id=str(payload["trade_id"]),
        signal_id=str(payload["signal_id"]),
        symbol=str(payload["symbol"]),
        direction=Direction(payload["direction"]),
        status=LifecycleStatus(payload["status"]),
        requested_entry=float(payload["requested_entry"]),
        fill_price=float(payload["fill_price"]),
        fill_timestamp=datetime.fromisoformat(str(payload["fill_timestamp"]).replace("Z", "+00:00")),
        fill_kind=FillKind(payload["fill_kind"]),
        initial_quantity=float(payload["initial_quantity"]),
        remaining_quantity=float(payload["remaining_quantity"]),
        closed_quantity=float(payload["closed_quantity"]),
        initial_stop=float(payload["initial_stop"]),
        current_stop=float(payload["current_stop"]),
        final_target=float(payload["final_target"]),
        initial_risk_price=float(payload["initial_risk_price"]),
        initial_risk_account_currency=(
            None
            if payload.get("initial_risk_account_currency") is None
            else float(payload["initial_risk_account_currency"])
        ),
        partial_target=float(payload["partial_target"]),
        partial_close_fraction=float(payload["partial_close_fraction"]),
        partial_close_attempted=bool(payload.get("partial_close_attempted", False)),
        partial_close_occurred=bool(payload.get("partial_close_occurred", False)),
        partial_close_skip_reason=payload.get("partial_close_skip_reason"),
        realized_gross_pnl=float(payload.get("realized_gross_pnl", 0.0)),
        current_r_multiple=float(payload.get("current_r_multiple", 0.0)),
        highest_favorable_price=payload.get("highest_favorable_price"),
        lowest_favorable_price=payload.get("lowest_favorable_price"),
        processed_event_ids=tuple(payload.get("processed_event_ids", [])),
        processed_action_ids=tuple(payload.get("processed_action_ids", [])),
        pnl_components=components,
        transitions=transitions,
        last_processed_event_id=payload.get("last_processed_event_id"),
        last_event_time=(
            None
            if payload.get("last_event_time") is None
            else datetime.fromisoformat(str(payload["last_event_time"]).replace("Z", "+00:00"))
        ),
        exit_time=(
            None
            if payload.get("exit_time") is None
            else datetime.fromisoformat(str(payload["exit_time"]).replace("Z", "+00:00"))
        ),
        exit_price=None if payload.get("exit_price") is None else float(payload["exit_price"]),
        exit_reason=_parse_reason(payload.get("exit_reason")),
        ambiguity_policy_used=bool(payload.get("ambiguity_policy_used", False)),
        adapter_metadata=dict(payload.get("adapter_metadata") or {}),
    )


def position_from_trade_record(
    trade: Mapping[str, Any],
    *,
    remaining_quantity: float,
    current_stop: float,
    final_target: float,
    observed_at: datetime,
    source: str = "live_legacy",
) -> PositionState:
    lifecycle = trade.get("lifecycle")
    if isinstance(lifecycle, Mapping):
        return position_from_payload(lifecycle)

    direction = Direction(str(trade["direction"]).lower())
    fill = float(trade["entry_price"])
    initial_quantity = float(trade.get("lot") or remaining_quantity)
    remaining_quantity = float(remaining_quantity)
    closed_quantity = max(0.0, initial_quantity - remaining_quantity)
    risk = abs(fill - float(trade.get("initial_sl", trade.get("sl", current_stop))))
    partial_fraction = float(trade.get("partial_close_fraction", 0.5))
    partial_target = fill + direction.sign * risk
    fill_time_raw = trade.get("opened_at")
    fill_time = observed_at
    if fill_time_raw:
        fill_time = datetime.fromisoformat(str(fill_time_raw).replace("Z", "+00:00"))
    partial_taken = bool(trade.get("partial_taken", False) or closed_quantity > 0)
    return PositionState(
        trade_id=str(trade.get("trade_id") or stable_id("legacy", trade.get("ticket"), fill_time)),
        signal_id=str(trade.get("signal_id") or stable_id("legacy-signal", trade.get("ticket"), fill_time)),
        symbol=str(trade.get("symbol")),
        direction=direction,
        status=LifecycleStatus.PARTIALLY_CLOSED if partial_taken else LifecycleStatus.OPEN,
        requested_entry=float(trade.get("requested_entry", fill)),
        fill_price=fill,
        fill_timestamp=as_utc(fill_time, "legacy fill timestamp"),
        fill_kind=FillKind.LIVE_MARKET,
        initial_quantity=initial_quantity,
        remaining_quantity=remaining_quantity,
        closed_quantity=closed_quantity,
        initial_stop=float(trade.get("initial_sl", trade.get("sl", current_stop))),
        current_stop=float(current_stop),
        final_target=float(final_target),
        initial_risk_price=risk,
        initial_risk_account_currency=None,
        partial_target=partial_target,
        partial_close_fraction=partial_fraction,
        partial_close_attempted=partial_taken,
        partial_close_occurred=partial_taken,
        highest_favorable_price=trade.get("peak_price", fill),
        lowest_favorable_price=trade.get("peak_price", fill),
        adapter_metadata={"source": source, "migrated_legacy_record": True},
    )


def update_trade_record(trade: Mapping[str, Any], position: PositionState) -> dict[str, Any]:
    updated = dict(trade)
    updated.update(
        {
            "trade_id": position.trade_id,
            "signal_id": position.signal_id,
            "requested_entry": position.requested_entry,
            "entry_price": position.fill_price,
            "initial_sl": position.initial_stop,
            "sl": position.current_stop,
            "tp": position.final_target,
            "risk": position.initial_risk_price,
            "lot": position.initial_quantity,
            "remaining_quantity": position.remaining_quantity,
            "partial_close_fraction": position.partial_close_fraction,
            "partial_taken": position.partial_close_occurred,
            "peak_price": (
                position.highest_favorable_price
                if position.direction is Direction.BUY
                else position.lowest_favorable_price
            ),
            "realized_gross_pnl": position.realized_gross_pnl,
            "lifecycle": position_to_payload(position),
        }
    )
    return updated


def outcome_to_event(position: PositionState) -> dict[str, Any]:
    if position.exit_time is None or position.exit_price is None or position.exit_reason is None:
        raise ValueError("closed lifecycle fields are required")
    return {
        "event": "trade_closed",
        "ts_utc": position.exit_time.isoformat(),
        "signal_id": position.signal_id,
        "trade_id": position.trade_id,
        "symbol": position.symbol,
        "direction": position.direction.value,
        "requested_entry": position.requested_entry,
        "entry_price": position.fill_price,
        "exit_price": position.exit_price,
        "reason": position.exit_reason.value if isinstance(position.exit_reason, ExitReason) else position.exit_reason,
        "gross_realized_pnl": position.realized_gross_pnl,
        "remaining_quantity": position.remaining_quantity,
        "partial_close_occurred": position.partial_close_occurred,
        "ambiguity_policy_used": position.ambiguity_policy_used,
        "adapter_source": position.adapter_metadata.get("source", "unknown"),
        "strategy_config_version": position.adapter_metadata.get("configuration_id"),
    }
