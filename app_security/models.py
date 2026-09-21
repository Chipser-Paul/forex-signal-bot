from __future__ import annotations

from dataclasses import dataclass


def mask_identifier(value: object) -> str:
    """Return a recognizable account identifier without displaying it in full."""
    text = str(value or "").strip()
    if not text:
        return "<unknown>"
    if len(text) <= 4:
        return "*" * len(text)
    return f"{'*' * (len(text) - 4)}{text[-4:]}"


@dataclass(frozen=True, slots=True, repr=False)
class MT5Credentials:
    """In-memory MT5 credentials with a deliberately sanitized representation."""

    login: str
    password: str
    server: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "login", str(self.login).strip())
        object.__setattr__(self, "password", str(self.password))
        object.__setattr__(self, "server", str(self.server).strip())

    def __repr__(self) -> str:
        return (
            "MT5Credentials("
            f"login={mask_identifier(self.login)!r}, "
            "password='<REDACTED>', "
            f"server={self.server!r})"
        )

    __str__ = __repr__
