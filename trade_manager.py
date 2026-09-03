"""Legacy profit-lock observation without broker mutation authority."""

from __future__ import annotations

import MetaTrader5 as mt5  # pyright: ignore[reportMissingImports]

from trade_executor import save_open_trades
from utils.logger import log
from utils.trade_journal import log_trade_event


def manage_open_trades(
    symbol: str,
    open_trades: dict,
    lock_trigger: float = 2.0,
    lock_pct: float = 0.3,
    lock_tiers: list[tuple[float, float]] | None = None,
):
    """Observe profit-lock telemetry; Phase 3 owns management decisions."""
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
    if symbol not in open_trades or not isinstance(open_trades[symbol], list):
        open_trades[symbol] = []
    trades = open_trades[symbol]
    tiers = sorted(lock_tiers or [], key=lambda item: item[0])
    if tiers:
        lock_trigger = min(trigger for trigger, _fraction in tiers)

    for position in positions:
        ticket = int(position.ticket)
        profit = float(position.profit)
        direction = "buy" if int(position.type) == int(mt5.ORDER_TYPE_BUY) else "sell"
        metadata = next(
            (item for item in trades if isinstance(item, dict) and item.get("ticket") == ticket),
            None,
        )
        if profit < lock_trigger:
            continue
        peak = max(float((metadata or {}).get("peak_profit", 0.0)), profit)
        active_fraction = lock_pct
        for trigger, fraction in tiers:
            if peak >= trigger:
                active_fraction = fraction
        locked = round(peak * active_fraction, 2)
        if metadata is None:
            metadata = {
                "symbol": symbol,
                "ticket": ticket,
                "direction": direction,
                "entry_price": float(position.price_open),
                "locked_profit": locked,
                "peak_profit": peak,
                "lock_pct": active_fraction,
            }
            trades.append(metadata)
            event_name = "profit_lock_armed"
        elif locked > float(metadata.get("locked_profit", 0.0)):
            metadata.update(
                locked_profit=locked,
                peak_profit=peak,
                lock_pct=active_fraction,
            )
            event_name = "profit_lock_updated"
        else:
            continue
        log(f"[LOCK] {event_name} for {symbol} ticket={ticket}", "yellow")
        log_trade_event(
            ticket=ticket,
            symbol=symbol,
            event_name=event_name,
            details={
                "locked_profit": locked,
                "peak_profit": peak,
                "lock_pct": active_fraction,
                "action": "observe_only_phase3_manages",
            },
        )
    open_trades[symbol] = trades
    save_open_trades(open_trades)


def close_position(*_args, **_kwargs) -> bool:
    """Legacy mutation helper is intentionally disabled by Phase 5."""
    log("[EXECUTION] Legacy close_position is disabled; use SecureBrokerExecutor", "red")
    return False
