from __future__ import annotations

from typing import Any, Callable


def evaluate_symbol(symbol: str, open_trades: dict[str, Any], impl: Callable[[str, dict[str, Any]], Any]) -> Any:
    return impl(symbol, open_trades)
