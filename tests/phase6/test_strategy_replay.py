from __future__ import annotations

import pytest

from backtests.strategy_semantics_replay import run_replay


@pytest.mark.integration
def test_all_strategy_replay_scenarios_have_live_historical_parity():
    results = run_replay()
    assert len(results) == 18
    assert all(item["parity"] for item in results.values())
    assert results["valid_bullish_xau"]["entry_eligible"]
    assert results["valid_bearish_xau"]["entry_eligible"]
    assert not results["news_provider_unavailable"]["entry_eligible"]
    assert not results["non_allowlisted_symbol"]["entry_eligible"]
    assert not results["high_volatility_rejection"]["entry_eligible"]
