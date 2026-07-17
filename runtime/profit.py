from __future__ import annotations

from typing import Callable


def initialize_today_profit(impl: Callable[[], None]) -> None:
    impl()


def show_profit_summary(impl: Callable[[], None]) -> None:
    impl()
