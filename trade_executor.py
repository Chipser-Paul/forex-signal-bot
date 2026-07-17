# trade_executor.py – persistent trade logger + smart retry + BTC logging

import json, os, MetaTrader5 as mt5 # pyright: ignore[reportMissingImports]
from pathlib import Path
from datetime import datetime
from utils.logger import log
from utils.notifications import send_alert
from utils.trade_logger import log_trade
from utils.trade_journal import log_trade_open
from utils.volatility import adapt_tp_sl
from utils.fetch import fetch_ohlcv

OPEN_JSON = Path("open_trades.json")

def load_open_trades() -> dict:
    if OPEN_JSON.exists():
        raw = OPEN_JSON.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            log("[WARN] open_trades.json is invalid. Resetting to empty object.", "yellow")
            return {}
    return {}

def save_open_trades(data: dict):
    cleaned = {}
    positions = {p.ticket: p for p in (mt5.positions_get() or [])}

    for sym, trades in data.items():
        fixed = []
        for t in (trades if isinstance(trades, list) else [trades]):
            trade = {}

            # Case 1: raw int ticket → normalize
            if isinstance(t, int):
                trade = {"ticket": t, "symbol": sym}

            # Case 2: dict trade
            elif isinstance(t, dict):
                trade = dict(t)  # copy to avoid mutation

                if "ticket" not in trade:
                    recovered = None

                    # Try recovery: match entry_price with open positions
                    if "entry_price" in trade:
                        ep = trade["entry_price"]
                        for p in positions.values():
                            if p.symbol == sym and abs(p.price_open - ep) < 0.05:
                                trade["ticket"] = p.ticket
                                recovered = p.ticket
                                log(f"[🛠️] Recovered ticket {p.ticket} for {sym}", "blue")
                                break

                    if not recovered:
                        log(f"[🗑️] Dropping stale trade for {sym} (no recoverable ticket)", "red")
                        continue  # ❌ skip adding this broken trade

            fixed.append(trade)

        if fixed:
            cleaned[sym] = fixed

    # 🔄 overwrite JSON with cleaned & normalized trades only
    OPEN_JSON.write_text(json.dumps(cleaned, indent=2))

def _send(req):
    return mt5.order_send(req)

def execute_trade(symbol: str,
                  direction: str,
                  lot: float,
                  sl: float,
                  tp: float,
                  comment: str = "",
                  context: dict | None = None) -> dict | None:

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        log(f"[❌] No tick data for {symbol}", "red")
        return None

    price = tick.ask if direction == "buy" else tick.bid

    if sl <= 0 or tp <= 0:
        log(f"[❌] Invalid SL or TP for {symbol} — SL={sl}, TP={tp}", "red")
        return None

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 123456,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    log(
        f"[ORDER] Sending order -> {symbol} {direction.upper()} "
        f"lot={lot} SL={sl:.2f} TP={tp:.2f} @ {price:.2f}",
        "yellow",
    )
    result = _send(req)

    if result and result.retcode == mt5.TRADE_RETCODE_INVALID_STOPS:
        log(f"[⚠️] {symbol} stops rejected → retrying with wider SL/TP", "yellow")
        df = fetch_ohlcv(symbol, "M5", bars=250)
        new_sl, new_tp = adapt_tp_sl(symbol, df, atr_mult=3.0)
        req["sl"], req["tp"] = new_sl, new_tp
        result = _send(req)

    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        actual_entry = float(result.price) if getattr(result, "price", 0) else float(price)
        log(
            f"[OK] ORDER PLACED: {symbol} {direction.upper()} "
            f"lot={lot} SL={req['sl']} TP={req['tp']} fill={actual_entry}",
            "green",
        )
        send_alert(
            f"Trade placed\n"
            f"Symbol: {symbol}\n"
            f"Side: {direction.upper()}\n"
            f"Lot: {lot}\n"
            f"Entry: {actual_entry}\n"
            f"SL: {req['sl']}\n"
            f"TP: {req['tp']}\n"
            f"Ticket: {result.order}",
            title="Trade Placed",
        )
        log_trade(symbol, direction, lot, req["sl"], req["tp"], actual_entry, comment)
        try:
            log_trade_open(
                ticket=int(result.order),
                symbol=symbol,
                direction=direction,
                lot=lot,
                entry_price=actual_entry,
                sl=req["sl"],
                tp=req["tp"],
                context=context or {},
            )
        except Exception as exc:
            log(f"[WARN] trade journal open log failed for {symbol}: {exc}", "yellow")

        if symbol == "BTCUSDm":
            log_btc_trade(symbol, direction, lot, sl, tp, price)

        return {
            "ticket": int(result.order),
            "entry_price": actual_entry,
            "sl": float(req["sl"]),
            "tp": float(req["tp"]),
            "lot": float(lot),
        }

    else:
        err_code = result.retcode if result else "no_response"
        err_msg = result.comment if result else "no MT5 response"
        log(f"[ERROR] Order failed {symbol} -> code: {err_code}, msg: {err_msg}", "red")
        return None

def log_btc_trade(symbol, direction, lot, sl, tp, price):
    os.makedirs("logs", exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("logs/btc_trades.log", "a") as f:
        f.write(f"{now} | {symbol} | {direction.upper()} | Price: {price:.2f} | Lot: {lot} | SL: {sl:.2f} | TP: {tp:.2f}\n")

# --------------------------
# ✅ Offline Backtest Version
# --------------------------
def backtest_trade(df, direction, entry_price, lot_size, sl_pips=50, tp_pips=30):
    """
    Simulates a trade based on fixed SL/TP and returns result and equity change.
    """
    pip_value = 0.10  # simplified default pip value for 0.01 lot
    equity_change = 0
    result = None

    sl_price = entry_price - sl_pips * 0.01 if direction == 'buy' else entry_price + sl_pips * 0.01
    tp_price = entry_price + tp_pips * 0.01 if direction == 'buy' else entry_price - tp_pips * 0.01

    for i in range(len(df)):
        high = df.iloc[i]['high']
        low = df.iloc[i]['low']
        if direction == 'buy':
            if low <= sl_price:
                result = 'loss'
                equity_change = -sl_pips * pip_value * (lot_size / 0.01)
                break
            elif high >= tp_price:
                result = 'win'
                equity_change = tp_pips * pip_value * (lot_size / 0.01)
                break
        else:
            if high >= sl_price:
                result = 'loss'
                equity_change = -sl_pips * pip_value * (lot_size / 0.01)
                break
            elif low <= tp_price:
                result = 'win'
                equity_change = tp_pips * pip_value * (lot_size / 0.01)
                break

    if result is None:
        result = 'timeout'
    return result, equity_change
