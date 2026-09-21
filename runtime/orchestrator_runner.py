from __future__ import annotations

from typing import Any, Callable


def run_shadow_orchestrator(symbol: str, open_trades: dict[str, Any], impl: Callable[[str, dict[str, Any]], None]) -> None:
    impl(symbol, open_trades)


def execute_orchestrator_live(
    symbol: str,
    orchestrator_result: dict[str, Any],
    impl: Callable[[str, dict[str, Any]], Any],
) -> Any:
    return impl(symbol, orchestrator_result)
