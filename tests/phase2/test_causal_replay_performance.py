from __future__ import annotations

import pytest

from backtests.causal_replay import benchmark_selector, build_causal_replay


@pytest.mark.unit
def test_synthetic_causal_replay_matches_expected_timeline():
    replay = build_causal_replay()
    visibility = replay["visibility"]
    assert visibility[0]["latest_open_time"] == {
        "M5": "2026-01-01T12:00:00+00:00",
        "H1": "2026-01-01T11:00:00+00:00",
        "H4": "2026-01-01T08:00:00+00:00",
        "D1": "2025-12-31T00:00:00+00:00",
    }
    assert visibility[1]["latest_open_time"]["H1"] == "2026-01-01T12:00:00+00:00"
    assert visibility[2]["latest_open_time"]["H4"] == "2026-01-01T12:00:00+00:00"
    assert visibility[3]["latest_open_time"]["D1"] == "2026-01-01T00:00:00+00:00"
    assert replay["future_visibility_violations"] == 0


@pytest.mark.unit
@pytest.mark.slow
def test_vectorized_selector_performance_sanity():
    benchmark = benchmark_selector(candle_count=20_000, decision_count=2_000)
    assert benchmark["last_position"] == 20_000
    assert benchmark["vectorized_selection_seconds"] < 5.0
