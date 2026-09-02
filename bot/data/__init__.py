"""Data access and causal candle contracts for the trading engine."""

from .candles import (
    CandleDataError,
    CausalAlignment,
    TimeframeSpec,
    align_causal_observations,
    causal_end_positions,
    causal_snapshot,
    get_timeframe_spec,
    normalize_candles,
)

__all__ = [
    "CandleDataError",
    "CausalAlignment",
    "TimeframeSpec",
    "align_causal_observations",
    "causal_end_positions",
    "causal_snapshot",
    "get_timeframe_spec",
    "normalize_candles",
]

