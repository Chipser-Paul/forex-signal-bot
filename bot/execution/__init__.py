"""Execution layer for the modular trading engine.

Package attributes load lazily (PEP 562): ``risk_engine`` imports
MetaTrader5 at module level, so eager re-exports would force a terminal
library import onto pure validation/strategy consumers (Phase 8H
import-safety requirement).  Names resolve on first attribute access,
exactly as before.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - static-analysis surface only
    from .confluence_scorer import score_setup
    from .news_filter import get_news_status
    from .risk_engine import RiskEngine

__all__ = [
    "RiskEngine",
    "get_news_status",
    "score_setup",
]


def __getattr__(name: str):  # noqa: ANN202 - PEP 562 hook
    if name == "RiskEngine":
        from .risk_engine import RiskEngine

        return RiskEngine
    if name == "get_news_status":
        from .news_filter import get_news_status

        return get_news_status
    if name == "score_setup":
        from .confluence_scorer import score_setup

        return score_setup
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
