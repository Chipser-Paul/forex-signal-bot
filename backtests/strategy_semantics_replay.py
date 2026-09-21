from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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
    StrategyConfig,
    StrategyInput,
    StrategySide,
    evaluate_live_strategy,
    evaluate_replay_strategy,
)


UTC = timezone.utc
DECISION_AT = datetime(2026, 1, 15, 12, 5, tzinfo=UTC)


def _input(
    *,
    symbol="XAUUSDm",
    side=StrategySide.LONG,
    regime=MarketRegime.RANGING,
    bias=None,
    dxy=None,
    news=SafetyState.CLEAR,
    session=SafetyState.CLEAR,
    block=BlockState.RETEST_ELIGIBLE,
    sources=True,
    score=True,
):
    expected = DirectionState.BULLISH if side is StrategySide.LONG else DirectionState.BEARISH
    inverse = DirectionState.BEARISH if side is StrategySide.LONG else DirectionState.BULLISH
    source = (
        SourceCandle("m5-1", "M5", DECISION_AT - timedelta(minutes=5), DECISION_AT),
    ) if sources else ()
    evidence = SetupEvidence(score, score, score, score)
    return StrategyInput(
        symbol,
        DECISION_AT,
        side,
        RegimeResult(regime, 0.001 if regime is not MarketRegime.DATA_UNSAFE else None, 1.0, 0.0, "replay"),
        DirectionResult(bias or expected, "replay"),
        DirectionResult(dxy or inverse, "replay"),
        SafetyResult(news, "replay", provenance="synthetic"),
        SessionResult(session, "replay", "synthetic", True),
        OrderBlockResult(block, side, "ob-1", 1990.0, 2000.0, DECISION_AT - timedelta(minutes=5), "replay"),
        evidence,
        source,
    )


def scenario_inputs() -> dict[str, StrategyInput]:
    return {
        "valid_bullish_xau": _input(),
        "valid_bearish_xau": _input(side=StrategySide.SHORT),
        "neutral_conflicting_setup": _input(bias=DirectionState.NEUTRAL),
        "insufficient_history": _input(regime=MarketRegime.DATA_UNSAFE, sources=False),
        "stale_dxy_constituent": _input(dxy=DirectionState.DATA_UNSAFE),
        "dxy_disagreement": _input(dxy=DirectionState.BULLISH),
        "trending_regime": _input(regime=MarketRegime.TRENDING_UP),
        "ranging_regime": _input(regime=MarketRegime.RANGING),
        "high_volatility_rejection": _input(regime=MarketRegime.HIGH_VOLATILITY),
        "causally_confirmed_order_block": _input(block=BlockState.ELIGIBLE),
        "premature_order_block_retest": _input(block=BlockState.PREMATURE),
        "fully_mitigated_block": _input(block=BlockState.MITIGATED),
        "high_impact_news": _input(news=SafetyState.BLOCKED),
        "news_provider_unavailable": _input(news=SafetyState.DATA_UNSAFE),
        "session_closed": _input(session=SafetyState.BLOCKED),
        "non_allowlisted_symbol": _input(symbol="BTCUSDm"),
        "below_confluence": _input(score=False),
        "repeated_evaluation": _input(),
    }


def run_replay() -> dict[str, dict]:
    config = StrategyConfig()
    results = {}
    for name, data in scenario_inputs().items():
        live = evaluate_live_strategy(data, config).to_dict()
        replay = evaluate_replay_strategy(data, config).to_dict()
        if live != replay:
            raise AssertionError(f"strategy parity failed for {name}")
        results[name] = {
            "side": live["side"],
            "entry_eligible": live["entry_eligible"],
            "regime": live["regime"],
            "reasons": live["reasons"],
            "parity": True,
        }
    repeated = evaluate_live_strategy(scenario_inputs()["repeated_evaluation"], config).to_json()
    if repeated != evaluate_live_strategy(scenario_inputs()["repeated_evaluation"], config).to_json():
        raise AssertionError("repeated strategy evaluation was not deterministic")
    return results


if __name__ == "__main__":
    print(json.dumps(run_replay(), sort_keys=True, indent=2))
