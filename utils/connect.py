from __future__ import annotations

import MetaTrader5 as mt5

from app_security.environment import ChildCredentialContract, consume_child_credentials
from app_security.identity import verify_mt5_identity
from app_security.redaction import redact_text
from utils.log import log

def _normalized_server(value: object) -> str:
    return str(value or "").strip().casefold()


def connect_mt5(contract: ChildCredentialContract | None = None) -> bool:
    """Connect and enforce the dashboard-to-runtime MT5 identity contract."""
    runtime_contract = contract or consume_child_credentials()
    credentials = runtime_contract.credentials
    login = credentials.login
    password = credentials.password
    server = credentials.server
    expected_login = runtime_contract.expected_login
    expected_server = runtime_contract.expected_server

    if not login or not password or not server:
        log("[SECURITY] MT5 credentials are incomplete; startup aborted", "red")
        return False
    if login != expected_login or _normalized_server(server) != _normalized_server(expected_server):
        log("[SECURITY] MT5 child configuration does not match the authorized account", "red")
        return False

    try:
        numeric_login = int(login)
    except ValueError:
        log("[SECURITY] MT5 login identifier is invalid; startup aborted", "red")
        return False

    try:
        if not mt5.initialize(login=numeric_login, password=password, server=server):
            error = redact_text(mt5.last_error(), (password,))
            log(f"MT5 initialization failed: {error}", "red")
            try:
                mt5.shutdown()
            except Exception:
                pass
            return False

        account_info = mt5.account_info()
        if account_info is None:
            log("MT5 account information is unavailable; startup aborted", "red")
            mt5.shutdown()
            return False

        verification = verify_mt5_identity(
            account_info,
            expected_login=expected_login,
            expected_server=expected_server,
        )
        if not verification.ok:
            log(f"[SECURITY] {verification.reason}; startup aborted", "red")
            mt5.shutdown()
            return False

        server_status = "server verified" if verification.server_verified else "server not reported by MT5"
        log(f"[SECURITY] MT5 account identity verification passed ({server_status})", "green")
        return True
    except Exception as exc:
        log(
            f"MT5 connection failed safely: {redact_text(exc, (password,))}",
            "red",
            secrets=(password,),
        )
        try:
            mt5.shutdown()
        except Exception:
            pass
        return False
