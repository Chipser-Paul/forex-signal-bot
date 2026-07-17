import MetaTrader5 as mt5
import time
from datetime import datetime, timezone


def connect_mt5(login: int, password: str, server: str):
    """Initialize and connect to MT5 using provided credentials."""
    try:
        # Clean up any previous session
        mt5.shutdown()
        time.sleep(0.5)

        # Ensure correct formats
        login = int(str(login).strip())
        password = str(password).strip()
        server = str(server).strip()

        # Attempt connection
        if not mt5.initialize(login=login, password=password, server=server):
            error = mt5.last_error()
            print(f"[MT5 ERROR] Connection failed: {error}")
            return None, error

        account_info = mt5.account_info()
        if account_info is None:
            error = mt5.last_error()
            print(f"[MT5 WARN] Account info unavailable: {error}")
            mt5.shutdown()
            return None, error

        account_data = {
            "login": account_info.login,
            "name": account_info.name,
            "balance": account_info.balance,
            "equity": account_info.equity,
            "profit": account_info.profit,
            "margin": account_info.margin,
            "currency": account_info.currency,
            "server": server,
        }

        print(f"[MT5 OK] Connected successfully: {account_data['login']} ({account_data['server']})")
        return account_data, None

    except Exception as e:
        print(f"[MT5 ERROR] Exception during connection: {e}")
        return None, str(e)


def get_account_info():
    """Return current account information if connected."""
    try:
        info = mt5.account_info()
        if info:
            return {
                "balance": info.balance,
                "equity": info.equity,
                "profit": info.profit,
                "margin": info.margin,
                "currency": info.currency,
            }
        print("[MT5 WARN] No account info returned.")
        return None
    except Exception as e:
        print(f"[MT5 ERROR] Error fetching account info: {e}")
        return None


def get_open_trades():
    """Fetch and group open trades by symbol (for dashboard stats)."""
    try:
        positions = mt5.positions_get()
        if not positions:
            return {}

        trades = {}
        for pos in positions:
            symbol = pos.symbol
            profit = pos.profit
            if symbol not in trades:
                trades[symbol] = {"count": 0, "total_profit": 0.0}
            trades[symbol]["count"] += 1
            trades[symbol]["total_profit"] += profit

        return trades

    except Exception as e:
        print(f"[MT5 ERROR] Error fetching open trades: {e}")
        return {}


def is_connected() -> bool:
    """Check if MT5 is currently connected and functional."""
    try:
        info = mt5.terminal_info()
        return info is not None and info.connected
    except Exception:
        return False


def shutdown_mt5():
    """Cleanly close the MT5 connection."""
    try:
        mt5.shutdown()
        print("[MT5 INFO] Connection closed.")
    except Exception as e:
        print(f"[MT5 ERROR] Error closing connection: {e}")


def get_closed_profit_today():
    """Return realized closed P/L for today (UTC)."""
    try:
        now = datetime.now(timezone.utc)
        utc_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = mt5.history_deals_get(utc_midnight, now)
        if not deals:
            return 0.0
        total = 0.0
        for d in deals:
            total += float(getattr(d, "profit", 0.0))
        return total
    except Exception as e:
        print(f"[MT5 ERROR] Error fetching today's closed profit: {e}")
        return 0.0
