from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest


@pytest.mark.known_defect
def test_risk_engine_caps_caller_risk_at_the_central_maximum(fake_mt5):
    from bot.execution.risk_engine import RiskEngine

    engine = RiskEngine()
    nominal = engine.calculate_position_size("XAUUSDm", 1000.0, 1.0, risk_pct=0.0035)
    oversized = engine.calculate_position_size("XAUUSDm", 1000.0, 1.0, risk_pct=0.02)
    assert nominal is not None
    assert oversized is None


@pytest.mark.known_defect
def test_regime_classifier_detects_recent_volatility_expansion():
    from strategies.smc_engine.market_structure import detect_market_condition

    rows = []
    price = 100.0
    for index in range(40):
        width = 0.2 if index < 25 else 3.0
        rows.append(
            {
                "open": price,
                "high": price + width,
                "low": price - width,
                "close": price + 0.01,
            }
        )
        price += 0.01
    frame = pd.DataFrame(rows)
    swings = [
        {"type": "high", "price": 101.0},
        {"type": "low", "price": 99.0},
        {"type": "high", "price": 101.1},
        {"type": "low", "price": 99.1},
    ]
    assert detect_market_condition(frame, swings) == "vol_expansion"


@pytest.mark.known_defect
def test_missing_news_source_fails_closed(monkeypatch):
    from bot.execution.news_filter import get_news_status

    monkeypatch.delenv("NEWS_EVENTS_PATH", raising=False)
    result = get_news_status("XAUUSDm", now="2026-01-15T12:00:00Z")
    assert result["news_clear"] is False


@pytest.mark.known_defect
def test_order_block_is_not_mitigated_without_a_zone_revisit():
    from strategies.smc_engine.ob_breaker_engine import _zone_mitigated

    frame = pd.DataFrame(
        [
            {"open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0},
            {"open": 12.0, "high": 13.0, "low": 12.0, "close": 12.5},
            {"open": 12.5, "high": 13.5, "low": 12.1, "close": 13.0},
        ]
    )
    assert _zone_mitigated(frame, 0, 9.0, 11.0) is False


@pytest.mark.known_defect
def test_invalid_stop_retry_converts_distances_to_absolute_prices(fake_mt5, tmp_path):
    from bot.execution.broker import ExecutionAction
    from bot.execution.broker.validation import corrected_absolute_levels
    from tests.phase5.helpers import entry_request, executor

    engine = executor(fake_mt5, tmp_path)
    request = entry_request(engine)
    snapshot = engine.snapshot("XAUUSDm", "buy", ExecutionAction.ENTRY)
    stop, target = corrected_absolute_levels(request, snapshot.symbol, snapshot.tick)

    assert stop == 99.9
    assert target == 102.0
    assert stop != snapshot.symbol.stops_level_points * snapshot.symbol.point
