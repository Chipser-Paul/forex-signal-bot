import MetaTrader5 as mt5  # pyright: ignore[reportMissingImports]

from utils.logger import log
from utils.notifications import send_alert
from utils.trade_journal import log_trade_close, log_trade_event
from trade_executor import save_open_trades


def manage_open_trades(
    symbol: str,
    open_trades: dict,
    lock_trigger: float = 2.0,
    lock_pct: float = 0.3,
    lock_tiers: list[tuple[float, float]] | None = None,
):
    """
    Monitors and manages open trades:
    - Locks a percentage of profit once floating P/L exceeds lock_trigger.
    - Closes trade early if price reverses below locked profit.
    """
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or len(positions) == 0:
        return

    if symbol not in open_trades or not isinstance(open_trades[symbol], list):
        open_trades[symbol] = []

    trades = open_trades[symbol]

    if lock_tiers:
        # Ensure tiers are sorted by trigger ascending
        lock_tiers = sorted(lock_tiers, key=lambda x: x[0])
        lock_trigger = min(t[0] for t in lock_tiers)

    for pos in positions:
        ticket = int(pos.ticket)
        profit = pos.profit
        entry_price = pos.price_open
        direction = "buy" if pos.type == 0 else "sell"

        trade_meta = next((t for t in trades if t.get("ticket") == ticket), None)

        if profit >= lock_trigger:
            prev_peak = trade_meta.get("peak_profit", 0) if trade_meta else 0
            peak_profit = max(prev_peak, profit)

            # Determine lock percentage (tiered if provided)
            active_pct = lock_pct
            if lock_tiers:
                for trigger, pct in lock_tiers:
                    if peak_profit >= trigger:
                        active_pct = pct
            locked_profit = round(peak_profit * active_pct, 2)

            if not trade_meta:
                trade_meta = {
                    "symbol": symbol,
                    "ticket": ticket,
                    "direction": direction,
                    "entry_price": entry_price,
                    "locked_profit": locked_profit,
                    "peak_profit": peak_profit,
                    "lock_pct": active_pct,
                }
                trades.append(trade_meta)
                log(f"[LOCK] Locking profit {locked_profit:.2f} on {symbol} (ticket {ticket})", "yellow")
                log_trade_event(
                    ticket=ticket,
                    symbol=symbol,
                    event_name="profit_lock_armed",
                    details={
                        "locked_profit": locked_profit,
                        "peak_profit": peak_profit,
                        "lock_pct": active_pct,
                    },
                )
            else:
                prev_locked = trade_meta.get("locked_profit", 0)
                if locked_profit > prev_locked:
                    trade_meta["locked_profit"] = locked_profit
                    trade_meta["peak_profit"] = peak_profit
                    trade_meta["lock_pct"] = active_pct
                    log(f"[LOCK] Updated lock {locked_profit:.2f} on {symbol} (ticket {ticket})", "yellow")
                    log_trade_event(
                        ticket=ticket,
                        symbol=symbol,
                        event_name="profit_lock_updated",
                        details={
                            "locked_profit": locked_profit,
                            "peak_profit": peak_profit,
                            "lock_pct": active_pct,
                        },
                    )

        if trade_meta:
            locked_profit = trade_meta.get("locked_profit", 0)
            if locked_profit > 0 and profit <= locked_profit:
                # Tracking only — ATR-3x trailing handles exit management
                log(f"[LOCK] Profit dropped below locked level (${profit:.2f} < ${locked_profit:.2f}) on {symbol} (ticket {ticket}) — letting ATR trailing manage exit", "cyan")
                log_trade_event(
                    ticket=ticket,
                    symbol=symbol,
                    event_name="profit_lock_breach",
                    details={
                        "profit": round(profit, 2),
                        "locked_profit": locked_profit,
                        "action": "monitor_only_atr_trailing",
                    },
                )

    open_trades[symbol] = trades
    save_open_trades(open_trades)


def close_position(ticket, symbol, lot, order_type):
    """Close a position safely."""
    if order_type == mt5.ORDER_TYPE_BUY:
        result = mt5.order_send(
            {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": mt5.ORDER_TYPE_SELL,
                "position": ticket,
                "deviation": 20,
                "magic": 234000,
                "comment": "profit_lock_exit",
            }
        )
    else:
        result = mt5.order_send(
            {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": mt5.ORDER_TYPE_BUY,
                "position": ticket,
                "deviation": 20,
                "magic": 234000,
                "comment": "profit_lock_exit",
            }
        )

    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"[OK] Closed {symbol} ticket={ticket}", "green")
        send_alert(
            f"Trade exited\n"
            f"Symbol: {symbol}\n"
            f"Ticket: {ticket}\n"
            f"Reason: close_position()",
            title="Trade Exited",
        )
        log_trade_close(
            ticket=int(ticket),
            symbol=symbol,
            reason="close_position",
            source="close_position_helper",
            details={"lot": lot, "order_type": int(order_type)},
        )
    else:
        retcode = result.retcode if result else "no_response"
        log(f"[ERROR] Failed to close {symbol} ticket={ticket}, retcode={retcode}", "red")
