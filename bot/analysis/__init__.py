"""Analysis layer for the modular trading engine.

Package attributes load lazily (PEP 562): ``bias_engine`` pulls in the MT5
backend through ``bot.data.market_data``, so eager re-exports would force a
MetaTrader5 import onto every pure strategy consumer (Phase 8H import-safety
requirement).  Names resolve on first attribute access, exactly as before.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - static-analysis surface only
    from .bias_engine import (
        aggregate_htf_bias,
        get_bias_snapshot,
        get_timeframe_biases,
        resolve_trade_bias,
    )
    from .fvg_engine import detect_fvgs, get_unfilled_fvgs
    from .liquidity_map import build_liquidity_map

__all__ = [
    "aggregate_htf_bias",
    "build_liquidity_map",
    "detect_fvgs",
    "get_bias_snapshot",
    "get_timeframe_biases",
    "get_unfilled_fvgs",
    "resolve_trade_bias",
]


def __getattr__(name: str):  # noqa: ANN202 - PEP 562 hook
    if name in __all__:
        if name in {"detect_fvgs", "get_unfilled_fvgs"}:
            from .fvg_engine import get_unfilled_fvgs, detect_fvgs

            return {"detect_fvgs": detect_fvgs, "get_unfilled_fvgs": get_unfilled_fvgs}[
                name
            ]
        if name == "build_liquidity_map":
            from .liquidity_map import build_liquidity_map

            return build_liquidity_map
        from . import bias_engine

        return getattr(bias_engine, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
