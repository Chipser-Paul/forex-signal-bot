#trade_logger.py
import os
import csv
import json
from datetime import datetime

LOG_DIR = 'logs'
CSV_LOG = os.path.join(LOG_DIR, 'trade_log.csv')

def setup_logger():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    if not os.path.exists(CSV_LOG):
        with open(CSV_LOG, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Time', 'Symbol', 'Direction', 'Entry Price', 'SL', 'TP',
                'Exit Time', 'Result', 'PnL ($)', 'Lot Size'
            ])

def log_trade(symbol, direction, lot, sl, tp, entry_price, comment=""):
    setup_logger()
    with open(CSV_LOG, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            symbol,
            direction,
            round(entry_price, 2),
            round(sl, 2),
            round(tp, 2),
            '', '', '', lot
        ])

    # Also append to JSON for model training
    json_path = os.path.join(LOG_DIR, f"{symbol}_trades.json")
    trade = {
        "timestamp": datetime.utcnow().isoformat(),
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "sl": sl,
        "tp": tp,
        "result": "open",
        "profit": 0,
    }

    history = []
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            history = json.load(f)

    history.append(trade)
    with open(json_path, "w") as f:
        json.dump(history[-300:], f, indent=2)

def update_trade_log(symbol, direction, result, pnl):
    setup_logger()

    # Update CSV
    rows = []
    updated = False
    with open(CSV_LOG, 'r', newline='') as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            if (
                row[1] == symbol and
                row[2].lower() == direction.lower() and
                row[6] == ''
            ):
                row[6] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                row[7] = result
                row[8] = round(pnl, 2)
                updated = True
            rows.append(row)
    if updated:
        with open(CSV_LOG, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

    # Update JSON version
    json_path = os.path.join(LOG_DIR, f"{symbol}_trades.json")
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            history = json.load(f)

        for trade in reversed(history):
            if trade["result"] == "open":
                trade["result"] = result
                trade["profit"] = pnl
                break

        with open(json_path, "w") as f:
            json.dump(history[-300:], f, indent=2)

def load_trade_history(symbol):
    json_path = os.path.join(LOG_DIR, f"{symbol}_trades.json")
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            return json.load(f)
    return []

def get_recent_closed_trades(symbol, within_minutes=30):
    path = os.path.join(LOG_DIR, f"{symbol}_trades.json")
    if not os.path.exists(path): return []

    with open(path, "r") as f:
        trades = json.load(f)

    now = datetime.utcnow()
    recent = []

    for t in trades:
        if t["result"] in ("win", "loss") and "timestamp" in t:
            closed_time = datetime.fromisoformat(t["timestamp"])
            if (now - closed_time).total_seconds() <= within_minutes * 60:
                recent.append(t)

    return recent