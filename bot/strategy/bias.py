from __future__ import annotations

from .models import DirectionResult, DirectionState


BIAS_WEIGHTS = {"W1": 0.40, "D1": 0.35, "H4": 0.25}


def aggregate_bias(timeframes: dict[str, DirectionState]) -> DirectionResult:
    if any(timeframe not in timeframes for timeframe in BIAS_WEIGHTS):
        return DirectionResult(DirectionState.DATA_UNSAFE, "missing_required_htf")
    if any(timeframes[timeframe] is DirectionState.DATA_UNSAFE for timeframe in BIAS_WEIGHTS):
        return DirectionResult(DirectionState.DATA_UNSAFE, "unsafe_htf")
    score = sum(
        BIAS_WEIGHTS[timeframe]
        * (
            1
            if timeframes[timeframe] is DirectionState.BULLISH
            else -1
            if timeframes[timeframe] is DirectionState.BEARISH
            else 0
        )
        for timeframe in BIAS_WEIGHTS
    )
    if score > 0:
        return DirectionResult(DirectionState.BULLISH, "weighted_htf_majority", abs(score))
    if score < 0:
        return DirectionResult(DirectionState.BEARISH, "weighted_htf_majority", abs(score))
    return DirectionResult(DirectionState.NEUTRAL, "htf_conflict_or_neutral", 0.0)
