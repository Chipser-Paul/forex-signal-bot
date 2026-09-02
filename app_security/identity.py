from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _normalize_server(value: object) -> str:
    return str(value or "").strip().casefold()


@dataclass(frozen=True, slots=True)
class IdentityVerification:
    ok: bool
    login_verified: bool
    server_verified: bool
    server_check_available: bool
    reason: str


def verify_mt5_identity(
    account_info: Any,
    *,
    expected_login: object,
    expected_server: object,
) -> IdentityVerification:
    """Verify the connected account without placing identifiers in result messages."""
    actual_login = str(getattr(account_info, "login", "") or "").strip()
    expected_login_text = str(expected_login or "").strip()
    if not actual_login or actual_login != expected_login_text:
        return IdentityVerification(False, False, False, False, "MT5 account identity mismatch")

    expected_server_text = _normalize_server(expected_server)
    actual_server_text = _normalize_server(getattr(account_info, "server", ""))
    server_check_available = bool(actual_server_text)
    if server_check_available and actual_server_text != expected_server_text:
        return IdentityVerification(False, True, False, True, "MT5 broker server mismatch")

    return IdentityVerification(
        True,
        True,
        server_check_available,
        server_check_available,
        "MT5 account identity verified",
    )
