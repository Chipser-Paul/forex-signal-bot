import MetaTrader5 as mt5
import time
from datetime import datetime, timezone

from app_security.identity import verify_mt5_identity
from app_security.models import mask_identifier
from app_security.redaction import redact_text


def connect_mt5(login: int, password: str, server: str):
    """Initialize and connect to MT5 using provided credentials."""
    try:
        # Clean up any previous session
        mt5.shutdown()
        time.sleep(0.5)

        # Ensure correct formats
        login = int(str(login).strip())
        password = str(password)
        server = str(server).strip()

        # Attempt connection
        if not mt5.initialize(login=login, password=password, server=server):
            error = redact_text(mt5.last_error(), (password,))
            print(f"[MT5 ERROR] Connection failed: {error}")
            return None, error

        account_info = mt5.account_info()
        if account_info is None:
            error = redact_text(mt5.last_error(), (password,))
            print(f"[MT5 WARN] Account info unavailable: {error}")
            mt5.shutdown()
            return None, error

        verification = verify_mt5_identity(
            account_info,
            expected_login=login,
            expected_server=server,
        )
        if not verification.ok:
            print(f"[MT5 SECURITY] {verification.reason}")
            mt5.shutdown()
            return None, verification.reason

        connected_server = str(getattr(account_info, "server", "") or server)

        account_data = {
            "login": account_info.login,
            "name": account_info.name,
            "balance": account_info.balance,
            "equity": account_info.equity,
            "profit": account_info.profit,
            "margin": account_info.margin,
            "currency": account_info.currency,
            "server": connected_server,
        }

        print(
            "[MT5 SECURITY] Account identity verified: "
            f"{mask_identifier(account_data['login'])}"
        )
        return account_data, None

    except Exception as e:
        safe_error = redact_text(e, (password,))
        print(f"[MT5 ERROR] Exception during connection: {safe_error}")
        return None, safe_error


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
        print(f"[MT5 ERROR] Error fetching account info: {redact_text(e)}")
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
        print(f"[MT5 ERROR] Error fetching open trades: {redact_text(e)}")
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
        print(f"[MT5 ERROR] Error closing connection: {redact_text(e)}")


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
        print(f"[MT5 ERROR] Error fetching today's closed profit: {redact_text(e)}")
        return 0.0
