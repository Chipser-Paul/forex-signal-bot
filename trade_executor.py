"""Trade persistence and secured live-entry compatibility facade."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from bot.execution.broker import ExecutionError, ExecutionStatus, SecureBrokerExecutor
from utils.logger import log
from utils.notifications import send_alert
from utils.trade_journal import log_trade_open
from utils.trade_logger import log_trade


OPEN_JSON = Path("open_trades.json")


def load_open_trades(*, strict: bool = False) -> dict:
    if not OPEN_JSON.exists():
        return {}
    raw = OPEN_JSON.read_text(encoding="utf-8").strip()
    if not raw:
        if strict:
            raise ExecutionError("open-trade state exists but is empty")
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log("[WARN] open_trades.json is invalid; broker reconciliation is required", "yellow")
        if strict:
            raise ExecutionError("open-trade state is corrupt")
        return {}
    if not isinstance(data, dict):
        if strict:
            raise ExecutionError("open-trade state must be a JSON object")
        return {}
    return data


def save_open_trades(data: dict) -> None:
    """Persist identifiable local records without adopting broker positions."""
    cleaned: dict[str, list[dict]] = {}
    for symbol, records in data.items():
        normalized: list[dict] = []
        for raw in records if isinstance(records, list) else [records]:
            if isinstance(raw, int):
                trade = {"ticket": raw, "symbol": symbol}
            elif isinstance(raw, dict):
                trade = dict(raw)
            else:
                continue
            if "ticket" not in trade:
                log(f"[WARN] Ignoring unidentifiable local trade for {symbol}", "yellow")
                continue
            normalized.append(trade)
        if normalized:
            cleaned[symbol] = normalized

    OPEN_JSON.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(
        dir=str(OPEN_JSON.parent),
        prefix=f".{OPEN_JSON.name}.",
        suffix=".tmp",
    )
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(cleaned, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, OPEN_JSON)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def execute_trade(
    symbol: str,
    direction: str,
    lot: float,
    sl: float,
    tp: float,
    comment: str = "",
    context: dict | None = None,
    *,
    executor: SecureBrokerExecutor | None = None,
    action_id: str | None = None,
    signal_id: str | None = None,
    trade_id: str | None = None,
    risk_decision_id: str | None = None,
    approved_volume: float | None = None,
    approved_stop: float | None = None,
    requested_trigger: float | None = None,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    risk_recheck: Callable[[float, float, float], float | None] | None = None,
) -> dict | None:
    """Submit through Phase 5 or fail closed when no secured adapter is supplied."""
    required = (executor, action_id, signal_id, trade_id, risk_decision_id)
    if any(value is None for value in required) or requested_trigger is None:
        log("[EXECUTION] Legacy direct submission is disabled", "red")
        return None

    request = executor.entry_request(
        action_id=str(action_id),
        signal_id=str(signal_id),
        trade_id=str(trade_id),
        symbol=symbol,
        direction=direction,
        volume=lot,
        requested_trigger=requested_trigger,
        executable_price=requested_trigger,
        stop_price=sl,
        target_price=tp,
        risk_decision_id=str(risk_decision_id),
        approved_volume=float(approved_volume if approved_volume is not None else lot),
        approved_stop=float(approved_stop if approved_stop is not None else sl),
        created_at=created_at or datetime.now(timezone.utc),
        expires_at=expires_at,
    )
    result = executor.execute(request, risk_recheck=risk_recheck)
    if result.status not in (ExecutionStatus.CONFIRMED, ExecutionStatus.PARTIALLY_FILLED):
        log(
            f"[EXECUTION] Order not confirmed for {symbol}: "
            f"status={result.status.value} reason={result.reason.value}",
            "red",
        )
        return None
    if not result.position_ticket or not result.executed_price or result.executed_volume <= 0:
        log(f"[EXECUTION] {symbol} result requires broker reconciliation", "red")
        return None

    actual_entry = float(result.executed_price)
    actual_lot = float(result.executed_volume)
    log(
        f"[OK] ORDER PLACED: {symbol} {direction.upper()} "
        f"lot={actual_lot} SL={sl} TP={tp} fill={actual_entry}",
        "green",
    )
    send_alert(
        f"Trade placed\nSymbol: {symbol}\nSide: {direction.upper()}\n"
        f"Lot: {actual_lot}\nEntry: {actual_entry}\nSL: {sl}\nTP: {tp}\n"
        f"Ticket: {result.position_ticket}",
        title="Trade Placed",
    )
    log_trade(symbol, direction, actual_lot, sl, tp, actual_entry, comment)
    execution_context = {
        "action_id": result.action_id,
        "attempt_id": result.attempt_id,
        "status": result.status.value,
        "reason": result.reason.value,
        "requested_volume": result.requested_volume,
        "executed_volume": result.executed_volume,
        "filling_mode": None if result.filling_mode is None else result.filling_mode.value,
    }
    try:
        log_trade_open(
            ticket=int(result.position_ticket),
            symbol=symbol,
            direction=direction,
            lot=actual_lot,
            entry_price=actual_entry,
            sl=sl,
            tp=tp,
            context={**(context or {}), "execution": execution_context},
        )
    except Exception as exc:
        log(f"[WARN] trade journal open log failed for {symbol}: {exc}", "yellow")

    if symbol == "BTCUSDm":
        log_btc_trade(symbol, direction, actual_lot, sl, tp, actual_entry)
    return {
        "ticket": int(result.position_ticket),
        "entry_price": actual_entry,
        "sl": float(sl),
        "tp": float(tp),
        "lot": actual_lot,
        "requested_lot": float(lot),
        "execution_action_id": result.action_id,
        "execution_attempt_id": result.attempt_id,
        "execution_status": result.status.value,
    }


def log_btc_trade(symbol, direction, lot, sl, tp, price):
    os.makedirs("logs", exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("logs/btc_trades.log", "a", encoding="utf-8") as handle:
        handle.write(
            f"{now} | {symbol} | {direction.upper()} | Price: {price:.2f} | "
            f"Lot: {lot} | SL: {sl:.2f} | TP: {tp:.2f}\n"
        )


def backtest_trade(df, direction, entry_price, lot_size, sl_pips=50, tp_pips=30):
    """Legacy offline helper retained without any broker dependency."""
    pip_value = 0.10
    equity_change = 0
    result = None
    sl_price = entry_price - sl_pips * 0.01 if direction == "buy" else entry_price + sl_pips * 0.01
    tp_price = entry_price + tp_pips * 0.01 if direction == "buy" else entry_price - tp_pips * 0.01
    for index in range(len(df)):
        high = df.iloc[index]["high"]
        low = df.iloc[index]["low"]
        if direction == "buy":
            if low <= sl_price:
                result = "loss"
                equity_change = -sl_pips * pip_value * (lot_size / 0.01)
                break
            if high >= tp_price:
                result = "win"
                equity_change = tp_pips * pip_value * (lot_size / 0.01)
                break
        else:
            if high >= sl_price:
                result = "loss"
                equity_change = -sl_pips * pip_value * (lot_size / 0.01)
                break
            if low <= tp_price:
                result = "win"
                equity_change = tp_pips * pip_value * (lot_size / 0.01)
                break
    return (result or "timeout"), equity_change
