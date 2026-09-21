from __future__ import annotations

from typing import Any

try:
    import keyring as _keyring  # pyright: ignore[reportMissingImports]
    from keyring.errors import KeyringError, PasswordDeleteError  # pyright: ignore[reportMissingImports]
except ImportError:  # Safe fallback: password persistence stays disabled.
    _keyring = None

    class KeyringError(Exception):
        pass

    class PasswordDeleteError(KeyringError):
        pass


SERVICE_NAME = "forex-signal-bot.mt5"


def _credential_name(login: object, server: object) -> str:
    return f"{str(login or '').strip()}@{str(server or '').strip().casefold()}"


def keyring_available() -> bool:
    if _keyring is None:
        return False
    try:
        backend: Any = _keyring.get_keyring()
        return float(getattr(backend, "priority", 0)) > 0
    except Exception:
        return False


def store_password(login: object, server: object, password: str) -> bool:
    """Persist a password only when an OS-backed keyring backend is usable."""
    if not password or not keyring_available():
        return False
    try:
        _keyring.set_password(SERVICE_NAME, _credential_name(login, server), password)
        return True
    except Exception:
        return False


def get_password(login: object, server: object) -> str | None:
    if not keyring_available():
        return None
    try:
        return _keyring.get_password(SERVICE_NAME, _credential_name(login, server))
    except Exception:
        return None


def delete_password(login: object, server: object) -> bool:
    if not keyring_available():
        return False
    try:
        _keyring.delete_password(SERVICE_NAME, _credential_name(login, server))
        return True
    except PasswordDeleteError:
        return True
    except Exception:
        return False
