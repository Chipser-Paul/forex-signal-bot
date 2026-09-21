from __future__ import annotations

import os
from collections.abc import MutableMapping
from dataclasses import dataclass

from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]

from app_security.models import MT5Credentials, mask_identifier


MT5_ENVIRONMENT_KEYS = (
    "MT5_LOGIN",
    "MT5_PASSWORD",
    "MT5_SERVER",
    "EXPECTED_MT5_LOGIN",
    "EXPECTED_MT5_SERVER",
)

_credentials_consumed = False


@dataclass(frozen=True, slots=True, repr=False)
class ChildCredentialContract:
    credentials: MT5Credentials
    expected_login: str
    expected_server: str

    def __repr__(self) -> str:
        return (
            "ChildCredentialContract("
            f"credentials={self.credentials!r}, "
            f"expected_login={mask_identifier(self.expected_login)!r}, "
            f"expected_server={self.expected_server!r})"
        )


def scrub_mt5_environment(
    environ: MutableMapping[str, str] | None = None,
) -> None:
    values = environ if environ is not None else os.environ
    for key in MT5_ENVIRONMENT_KEYS:
        values.pop(key, None)


def load_project_environment() -> None:
    """Load local configuration without restoring consumed child credentials."""
    load_dotenv()
    if _credentials_consumed:
        scrub_mt5_environment()


def consume_child_credentials(
    environ: MutableMapping[str, str] | None = None,
) -> ChildCredentialContract:
    """Read the one-shot MT5 child contract and erase its environment values."""
    global _credentials_consumed

    values = environ if environ is not None else os.environ
    if values is os.environ and not _credentials_consumed:
        load_dotenv()

    login = str(values.get("MT5_LOGIN", "")).strip()
    password = str(values.get("MT5_PASSWORD", ""))
    server = str(values.get("MT5_SERVER", "")).strip()
    expected_login = str(values.get("EXPECTED_MT5_LOGIN", login)).strip()
    expected_server = str(values.get("EXPECTED_MT5_SERVER", server)).strip()

    credentials = MT5Credentials(login=login, password=password, server=server)
    scrub_mt5_environment(values)
    if values is os.environ:
        _credentials_consumed = True

    return ChildCredentialContract(
        credentials=credentials,
        expected_login=expected_login,
        expected_server=expected_server,
    )
