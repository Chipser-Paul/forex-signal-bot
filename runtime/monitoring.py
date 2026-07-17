from __future__ import annotations

from typing import Any, Callable


def monitor_trades(open_trades: dict[str, Any], impl: Callable[[dict[str, Any]], dict[str, Any] | None]) -> dict[str, Any]:
    updated = impl(open_trades)
    return updated or {}
