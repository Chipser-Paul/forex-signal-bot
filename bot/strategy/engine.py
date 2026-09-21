from __future__ import annotations

from .config import StrategyConfig
from .confluence import score_evidence
from .models import (
    BlockState,
    DirectionState,
    MarketRegime,
    SafetyState,
    StrategyDecision,
    StrategyInput,
    StrategyReason,
    StrategySide,
)


def _expected_direction(side: StrategySide) -> DirectionState:
    return DirectionState.BULLISH if side is StrategySide.LONG else DirectionState.BEARISH


def evaluate_strategy(data: StrategyInput, config: StrategyConfig) -> StrategyDecision:
    confluence = score_evidence(data.evidence, config.confluence_threshold)
    reasons: list[StrategyReason] = []

    if data.symbol not in config.executable_symbols:
        reasons.append(StrategyReason.SYMBOL_NOT_EXECUTABLE)
    if data.requested_side is StrategySide.FLAT:
        reasons.append(StrategyReason.SIDE_FLAT)
    if not data.source_candles:
        reasons.append(StrategyReason.SOURCE_DATA_UNSAFE)
    elif any(candle.available_at > data.decision_at for candle in data.source_candles):
        reasons.append(StrategyReason.SOURCE_CANDLE_IN_FUTURE)

    if data.regime.state is MarketRegime.DATA_UNSAFE:
        reasons.append(StrategyReason.REGIME_DATA_UNSAFE)
    elif data.regime.state is MarketRegime.HIGH_VOLATILITY:
        reasons.append(StrategyReason.REGIME_HIGH_VOLATILITY)

    expected = (
        _expected_direction(data.requested_side)
        if data.requested_side is not StrategySide.FLAT
        else DirectionState.NEUTRAL
    )
    if data.bias.state is DirectionState.DATA_UNSAFE:
        reasons.append(StrategyReason.BIAS_DATA_UNSAFE)
    elif data.bias.state is DirectionState.NEUTRAL:
        reasons.append(StrategyReason.BIAS_NEUTRAL)
    elif data.bias.state is not expected:
        reasons.append(StrategyReason.BIAS_DIRECTION_CONFLICT)

    if data.regime.state in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN):
        regime_direction = (
            DirectionState.BULLISH
            if data.regime.state is MarketRegime.TRENDING_UP
            else DirectionState.BEARISH
        )
        if regime_direction is not expected:
            reasons.append(StrategyReason.REGIME_DIRECTION_CONFLICT)

    if data.dxy.state is DirectionState.DATA_UNSAFE:
        reasons.append(StrategyReason.DXY_DATA_UNSAFE)
    elif data.dxy.state is expected:
        reasons.append(StrategyReason.DXY_DIRECTION_CONFLICT)

    if data.news.state is SafetyState.DATA_UNSAFE:
        reasons.append(StrategyReason.NEWS_DATA_UNSAFE)
    elif data.news.state is SafetyState.BLOCKED:
        reasons.append(StrategyReason.NEWS_BLOCKED)
    if data.session.state is SafetyState.DATA_UNSAFE:
        reasons.append(StrategyReason.SESSION_DATA_UNSAFE)
    elif data.session.state is SafetyState.BLOCKED:
        reasons.append(StrategyReason.SESSION_CLOSED)

    if not data.order_block.eligible:
        reasons.append(StrategyReason.ORDER_BLOCK_UNAVAILABLE)
    elif data.order_block.side is not data.requested_side:
        reasons.append(StrategyReason.ORDER_BLOCK_DIRECTION_CONFLICT)
    if not confluence.passed:
        reasons.append(StrategyReason.CONFLUENCE_BELOW_THRESHOLD)

    eligible = not reasons
    return StrategyDecision(
        symbol=data.symbol,
        decision_at=data.decision_at,
        side=data.requested_side if eligible else StrategySide.FLAT,
        entry_eligible=eligible,
        regime=data.regime.state,
        bias=data.bias.state,
        dxy=data.dxy.state,
        news=data.news.state,
        session=data.session.state,
        order_block=data.order_block.state,
        confluence=confluence,
        source_candles=data.source_candles,
        reasons=(StrategyReason.APPROVED,) if eligible else tuple(dict.fromkeys(reasons)),
        configuration_fingerprint=config.fingerprint(),
        strategy_version=config.version,
        invalidation=dict(data.invalidation),
    )
