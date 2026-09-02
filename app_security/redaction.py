from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Iterable


REDACTED = "<REDACTED>"
_SENSITIVE_KEY = re.compile(
    r"(?:^|_)(?:password|passwd|pwd|token|secret|api_key|private_key|authorization)(?:$|_)",
    re.IGNORECASE,
)
_NON_SECRET_KEYS = frozenset({"remember_password"})
_QUOTED_KEY_VALUE = re.compile(
    r"(?i)([\"']?(?:password|passwd|pwd|token|secret|api[_-]?key|private[_-]?key|authorization)"
    r"[\"']?\s*[:=]\s*)([\"'])(.*?)(\2)"
)
_BARE_KEY_VALUE = re.compile(
    r"(?i)([\"']?(?:password|passwd|pwd|token|secret|api[_-]?key|private[_-]?key|authorization)"
    r"[\"']?\s*[:=]\s*)(?:bearer\s+)?([^\s,;}\]]+)"
)
_URL_CREDENTIAL = re.compile(r"(?i)(://[^:/\s]+:)([^@/\s]+)(@)")


def is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return normalized not in _NON_SECRET_KEYS and bool(_SENSITIVE_KEY.search(normalized))


def redact_text(value: object, secrets: Iterable[object] = ()) -> str:
    """Redact known values and common credential-shaped key/value text."""
    text = str(value)
    for secret in secrets:
        secret_text = str(secret or "")
        if secret_text:
            text = text.replace(secret_text, REDACTED)
    text = _URL_CREDENTIAL.sub(r"\1<REDACTED>\3", text)
    text = _QUOTED_KEY_VALUE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}{match.group(2)}",
        text,
    )
    return _BARE_KEY_VALUE.sub(r"\1<REDACTED>", text)


def sanitize_mapping(value: Any) -> Any:
    """Recursively remove credential values before serialization or logging."""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if is_sensitive_key(key) else sanitize_mapping(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_mapping(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_mapping(item) for item in value)
    return value
