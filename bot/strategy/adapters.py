from __future__ import annotations

from .config import StrategyConfig
from .engine import evaluate_strategy
from .models import StrategyDecision, StrategyInput


def evaluate_live_strategy(data: StrategyInput, config: StrategyConfig) -> StrategyDecision:
    return evaluate_strategy(data, config)


def evaluate_replay_strategy(data: StrategyInput, config: StrategyConfig) -> StrategyDecision:
    return evaluate_strategy(data, config)
