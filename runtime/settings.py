from __future__ import annotations

from typing import Callable


def refresh_runtime_settings(impl: Callable[[], None]) -> None:
    impl()


def is_symbol_enabled(symbol: str, impl: Callable[[str], bool]) -> bool:
    return bool(impl(symbol))
