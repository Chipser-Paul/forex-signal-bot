from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from bot.execution.lifecycle import (
    ActionType,
    Direction,
    LifecycleAction,
    ManagementConfig,
    MarketEvent,
    MarketEventKind,
    ReadinessStyle,
    new_entry_intent,
    stable_id,
)


def _tick_timestamp(tick: Any, observed_at: datetime | None = None) -> tuple[datetime, int]:
    time_msc = int(getattr(tick, "time_msc", 0) or 0)
    if time_msc > 0:
        return datetime.fromtimestamp(time_msc / 1000.0, tz=timezone.utc), time_msc
    seconds = int(getattr(tick, "time", 0) or 0)
    if seconds > 0:
        return datetime.fromtimestamp(seconds, tz=timezone.utc), seconds * 1000
    if observed_at is None or observed_at.tzinfo is None:
        raise ValueError("tick requires a broker timestamp or explicit aware observation time")
    timestamp = observed_at.astimezone(timezone.utc)
    return timestamp, int(timestamp.timestamp() * 1000)


def market_event_from_tick(
    symbol: str,
    tick: Any,
    *,
    observed_at: datetime | None = None,
    atr: float | None = None,
    emergency_reason: str | None = None,
    structure_trail_level: float | None = None,
) -> MarketEvent:
    timestamp, sequence = _tick_timestamp(tick, observed_at)
    bid = float(getattr(tick, "bid"))
    ask = float(getattr(tick, "ask"))
    return MarketEvent(
        event_id=stable_id(symbol, "tick", sequence, bid, ask),
        timestamp=timestamp,
        symbol=symbol,
        source="live_mt5",
        kind=MarketEventKind.TICK,
        sequence=sequence,
        bid=bid,
        ask=ask,
        close=(bid + ask) / 2.0,
        atr=atr,
        emergency_reason=emergency_reason,
        structure_trail_level=structure_trail_level,
    )


def intent_from_strategy_entry(
    *,
    symbol: str,
    source_timeframe: str,
    entry: Mapping[str, Any],
    entry_frame,
    stop_loss: float,
    final_target: float,
    partial_close_fraction: float,
    configuration_id: str,
    expiry_minutes: int = 120,
    strategy_metadata: Mapping[str, Any] | None = None,
):
    source = entry_frame.iloc[-1]
    source_open = source["open_time"]
    signal_available = source["available_at"]
    entry_type = str(entry.get("entry_type") or "market").lower()
    pullback = entry_type == "limit"
    trigger = (
        float(entry["limit_entry"])
        if pullback and entry.get("limit_entry") is not None
        else float(source["close"])
    )
    source_event_id = stable_id(symbol, source_timeframe, source_open.isoformat())
    return new_entry_intent(
        symbol=symbol,
        direction=Direction(str(entry["direction"]).lower()),
        source_timeframe=source_timeframe,
        source_candle_open_time=source_open,
        signal_available_at=signal_available,
        requested_trigger=trigger,
        stop_loss=stop_loss,
        final_target=final_target,
        readiness_style=ReadinessStyle.PULLBACK if pullback else ReadinessStyle.IMMEDIATE,
        partial_close_fraction=partial_close_fraction,
        expires_at=signal_available + timedelta(minutes=expiry_minutes),
        source_event_id=source_event_id,
        source_sequence=0,
        strategy_metadata=dict(strategy_metadata or {}),
        configuration_id=configuration_id,
    )


def management_config_from_live(
    *,
    profile: Mapping[str, Any],
    symbol_info: Any,
    partial_close_fraction: float,
) -> ManagementConfig:
    trailing = dict(profile.get("trailing") or {})
    point = float(getattr(symbol_info, "point", 0.0) or 0.0)
    return ManagementConfig(
        partial_close_fraction=partial_close_fraction,
        partial_target_r=1.0,
        volume_min=float(getattr(symbol_info, "volume_min", 0.01) or 0.01),
        volume_step=float(getattr(symbol_info, "volume_step", 0.01) or 0.01),
        pnl_per_price_unit=float(getattr(symbol_info, "trade_contract_size", 1.0) or 1.0),
        trailing_enabled=str(trailing.get("mode", "atr_3x")) == "atr_3x",
        trailing_atr_multiple=float(trailing.get("atr_mult", 3.0)),
        trailing_min_distance=float(trailing.get("min_distance_points", 100.0)) * point,
    )


def order_request_for_action(
    action: LifecycleAction,
    *,
    symbol: str,
    ticket: int,
    direction: Direction,
    current_tp: float,
    bid: float,
    ask: float,
    constants: Mapping[str, int],
    digits: int,
    deviation: int,
    magic: int,
) -> dict[str, Any] | None:
    if action.action_type is ActionType.PARTIAL_SKIPPED:
        return None
    if action.action_type is ActionType.MODIFY_STOP:
        return {
            "action": constants["TRADE_ACTION_SLTP"],
            "symbol": symbol,
            "position": ticket,
            "sl": round(float(action.new_stop), digits),
            "tp": float(current_tp),
        }
    if action.action_type in (ActionType.PARTIAL_CLOSE, ActionType.FINAL_CLOSE):
        return {
            "action": constants["TRADE_ACTION_DEAL"],
            "symbol": symbol,
            "position": ticket,
            "volume": float(action.quantity),
            "type": (
                constants["ORDER_TYPE_SELL"]
                if direction is Direction.BUY
                else constants["ORDER_TYPE_BUY"]
            ),
            "price": float(bid if direction is Direction.BUY else ask),
            "deviation": int(deviation),
            "magic": int(magic),
            "comment": (
                "Lifecycle partial"
                if action.action_type is ActionType.PARTIAL_CLOSE
                else f"Lifecycle {action.reason}"
            ),
        }
    raise ValueError(f"unsupported lifecycle action: {action.action_type.value}")


def dispatch_actions(
    actions: tuple[LifecycleAction, ...],
    *,
    request_builder: Callable[[LifecycleAction], dict[str, Any] | None],
    send_order: Callable[[dict[str, Any]], Any],
    success_retcode: int,
) -> tuple[tuple[LifecycleAction, Any], ...]:
    del actions, request_builder, send_order, success_retcode
    raise RuntimeError(
        "legacy lifecycle dispatcher is disabled; use SecureBrokerExecutor"
    )
