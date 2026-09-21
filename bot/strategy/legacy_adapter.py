from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .adapters import evaluate_live_strategy, evaluate_replay_strategy
from .config import StrategyConfig
from .models import (
    DirectionResult,
    DirectionState,
    SafetyResult,
    SafetyState,
    SessionResult,
    SetupEvidence,
    SourceCandle,
    StrategyDecision,
    StrategyInput,
    StrategySide,
)
from .order_blocks import evaluate_order_block
from .regime import classify_regime


def _direction(value: object) -> DirectionState:
    text = str(value or "").upper()
    return {
        "BULLISH": DirectionState.BULLISH,
        "BEARISH": DirectionState.BEARISH,
        "NEUTRAL": DirectionState.NEUTRAL,
    }.get(text, DirectionState.DATA_UNSAFE)


def _safety(context: dict, clear_key: str) -> SafetyState:
    state = str(context.get("state", "")).upper()
    if state in SafetyState.__members__:
        return SafetyState[state]
    if clear_key not in context:
        return SafetyState.DATA_UNSAFE
    return SafetyState.CLEAR if context.get(clear_key) is True else SafetyState.BLOCKED


def evaluate_legacy_context(
    *,
    adapter: str,
    symbol: str,
    decision_at: datetime,
    side: str,
    entry_frame: pd.DataFrame,
    htf_bias: str,
    dxy_context: dict,
    news_context: dict,
    session_context: dict,
    evidence: SetupEvidence,
    config: StrategyConfig | None = None,
    consumed_block_ids: frozenset[str] = frozenset(),
) -> StrategyDecision:
    """Translate old dictionary analysis into the canonical fail-closed contract."""
    policy = config or StrategyConfig()
    requested = {"bullish": StrategySide.LONG, "bearish": StrategySide.SHORT}.get(
        str(side).lower(), StrategySide.FLAT
    )
    decision = decision_at.astimezone(timezone.utc)
    source_candles: tuple[SourceCandle, ...] = ()
    if entry_frame is not None and not entry_frame.empty and {"open_time", "available_at"}.issubset(entry_frame.columns):
        last = entry_frame.iloc[-1]
        opened = pd.Timestamp(last["open_time"]).to_pydatetime()
        available = pd.Timestamp(last["available_at"]).to_pydatetime()
        source_candles = (
            SourceCandle(
                f"{symbol}:{opened.astimezone(timezone.utc).isoformat()}",
                str(last.get("timeframe", "ENTRY")),
                opened,
                available,
            ),
        )
    block = evaluate_order_block(entry_frame, requested, decision, policy, consumed_ids=consumed_block_ids)
    data = StrategyInput(
        symbol=symbol,
        decision_at=decision,
        requested_side=requested,
        regime=classify_regime(entry_frame, policy),
        bias=DirectionResult(_direction(htf_bias), "legacy_htf_translation"),
        dxy=DirectionResult(_direction(dxy_context.get("dxy_bias")), "legacy_dxy_translation"),
        news=SafetyResult(
            _safety(news_context, "news_clear"),
            str(news_context.get("reason", "legacy_news_translation")),
            provenance=str(news_context.get("source", "unavailable")),
        ),
        session=SessionResult(
            _safety(session_context, "session_allowed"),
            str(session_context.get("reason", "legacy_session_translation")),
            str(session_context.get("active_session", "unknown")),
            bool(session_context.get("is_priority_session", False)),
        ),
        order_block=block,
        evidence=evidence,
        source_candles=source_candles,
        invalidation={"order_block_id": block.block_id},
    )
    evaluator = evaluate_live_strategy if adapter == "live" else evaluate_replay_strategy
    return evaluator(data, policy)
