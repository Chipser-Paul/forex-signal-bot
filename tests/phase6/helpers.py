from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bot.strategy import (
    BlockState,
    DirectionResult,
    DirectionState,
    MarketRegime,
    OrderBlockResult,
    RegimeResult,
    SafetyResult,
    SafetyState,
    SessionResult,
    SetupEvidence,
    SourceCandle,
    StrategyInput,
    StrategySide,
)


UTC = timezone.utc
DECISION_AT = datetime(2026, 1, 15, 12, 5, tzinfo=UTC)


def strategy_input(
    *,
    symbol: str = "XAUUSDm",
    side: StrategySide = StrategySide.LONG,
    decision_at: datetime = DECISION_AT,
    regime: MarketRegime = MarketRegime.RANGING,
    bias: DirectionState | None = None,
    dxy: DirectionState | None = None,
    news: SafetyState = SafetyState.CLEAR,
    session: SafetyState = SafetyState.CLEAR,
    block_state: BlockState = BlockState.RETEST_ELIGIBLE,
) -> StrategyInput:
    expected = DirectionState.BULLISH if side is StrategySide.LONG else DirectionState.BEARISH
    inverse = DirectionState.BEARISH if side is StrategySide.LONG else DirectionState.BULLISH
    return StrategyInput(
        symbol=symbol,
        decision_at=decision_at,
        requested_side=side,
        regime=RegimeResult(regime, 0.001, 1.0, 0.0, "test"),
        bias=DirectionResult(bias or expected, "test"),
        dxy=DirectionResult(dxy or inverse, "test"),
        news=SafetyResult(news, "test", provenance="fixture"),
        session=SessionResult(session, "test", "fixture", True),
        order_block=OrderBlockResult(
            block_state,
            side,
            "block-1",
            1990.0,
            2000.0,
            decision_at - timedelta(minutes=5),
            "test",
        ),
        evidence=SetupEvidence(True, True, True, True),
        source_candles=(
            SourceCandle(
                "m5-1",
                "M5",
                decision_at - timedelta(minutes=5),
                decision_at,
            ),
        ),
        invalidation={"price": 1989.0},
    )
