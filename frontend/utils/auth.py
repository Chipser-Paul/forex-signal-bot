from __future__ import annotations

import hmac
import os
from collections.abc import Mapping, MutableMapping
from typing import Any

from app_security.models import MT5Credentials


AUTHENTICATED_KEY = "_mt5_authenticated"
CREDENTIALS_KEY = "_mt5_credentials"
REMOTE_AUTHORIZED_KEY = "_remote_access_authorized"
PASSWORD_WIDGET_KEY = "mt5_password_input"  # pragma: allowlist secret
REMOTE_TOKEN_WIDGET_KEY = "remote_access_token_input"  # pragma: allowlist secret
PROTECTED_PAGES = frozenset({"dashboard", "strategy", "analytics", "ai", "settings"})


def is_authenticated(state: Mapping[str, Any]) -> bool:
    return bool(state.get(AUTHENTICATED_KEY)) and isinstance(
        state.get(CREDENTIALS_KEY), MT5Credentials
    )


def establish_authenticated_session(
    state: MutableMapping[str, Any], credentials: MT5Credentials
) -> None:
    state[AUTHENTICATED_KEY] = True
    state[CREDENTIALS_KEY] = credentials


def get_authenticated_credentials(state: Mapping[str, Any]) -> MT5Credentials | None:
    if not is_authenticated(state):
        return None
    credentials = state.get(CREDENTIALS_KEY)
    return credentials if isinstance(credentials, MT5Credentials) else None


def clear_authenticated_session(state: MutableMapping[str, Any]) -> None:
    state.pop(AUTHENTICATED_KEY, None)
    state.pop(CREDENTIALS_KEY, None)
    state.pop(PASSWORD_WIDGET_KEY, None)
    state.pop(REMOTE_AUTHORIZED_KEY, None)
    state.pop(REMOTE_TOKEN_WIDGET_KEY, None)
    state["page"] = "login"


def resolve_page(requested_page: str, state: Mapping[str, Any]) -> str:
    page = str(requested_page or "login").strip().lower()
    if page in PROTECTED_PAGES and not is_authenticated(state):
        return "login"
    return page if page in PROTECTED_PAGES or page == "login" else "login"


def remote_access_required(
    environ: Mapping[str, str] | None = None,
    *,
    server_address: object | None = None,
) -> bool:
    values = environ if environ is not None else os.environ
    explicit_remote = str(values.get("FOREX_REMOTE_ACCESS", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if server_address is None:
        return explicit_remote
    address = str(server_address or "").strip().casefold()
    loopback = address in {"127.0.0.1", "localhost", "::1"}
    return explicit_remote or not loopback


def remote_access_is_configured(environ: Mapping[str, str] | None = None) -> bool:
    values = environ if environ is not None else os.environ
    return bool(str(values.get("APP_ACCESS_TOKEN", "")).strip())


def authorize_remote_access(
    state: MutableMapping[str, Any],
    candidate: str,
    environ: Mapping[str, str] | None = None,
) -> bool:
    values = environ if environ is not None else os.environ
    expected = str(values.get("APP_ACCESS_TOKEN", ""))
    accepted = bool(expected) and hmac.compare_digest(str(candidate), expected)
    if accepted:
        state[REMOTE_AUTHORIZED_KEY] = True
    return accepted


def remote_access_authorized(state: Mapping[str, Any]) -> bool:
    return bool(state.get(REMOTE_AUTHORIZED_KEY))
