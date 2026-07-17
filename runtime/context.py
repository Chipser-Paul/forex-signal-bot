from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class RuntimeContext:
    symbols: list[str]
    loop_delay: float
    is_symbol_enabled: Callable[[str], bool]
    refresh_runtime_settings: Callable[[], None]
    show_profit_summary: Callable[[], None]
    monitor_trades: Callable[[dict[str, Any]], dict[str, Any] | None]
    evaluate_symbol: Callable[[str, dict[str, Any]], Any]
    manage_open_trades: Callable[..., Any]
    sleep_fn: Callable[[float], None]
