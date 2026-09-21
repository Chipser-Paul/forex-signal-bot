from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from bot.analysis.dxy_filter import build_synthetic_dxy_from_frames
from bot.data.candles import align_causal_observations, normalize_candles
from tests.phase2.helpers import normalized_candles, raw_candles


@pytest.mark.unit
def test_equal_availability_timestamps_join_exactly():
    frames = {
        "A": normalized_candles("2026-01-01T10:00:00Z", 2, "1h", "H1"),
        "B": normalized_candles("2026-01-01T10:00:00Z", 2, "1h", "H1", base=200),
    }
    result = align_causal_observations(frames, "2026-01-01T12:00:00Z")
    assert list(result.frame.index) == [
        pd.Timestamp("2026-01-01T11:00:00Z"),
        pd.Timestamp("2026-01-01T12:00:00Z"),
    ]


@pytest.mark.unit
def test_unequal_history_lengths_align_by_timestamp_not_tail_position():
    frames = {
        "A": normalized_candles("2026-01-01T09:00:00Z", 3, "1h", "H1"),
        "B": normalized_candles("2026-01-01T10:00:00Z", 2, "1h", "H1", base=200),
    }
    result = align_causal_observations(frames, "2026-01-01T12:00:00Z")
    assert list(result.frame.index) == [
        pd.Timestamp("2026-01-01T11:00:00Z"),
        pd.Timestamp("2026-01-01T12:00:00Z"),
    ]
    assert result.frame.loc[pd.Timestamp("2026-01-01T11:00:00Z"), "A"] == 101.0


@pytest.mark.unit
def test_unsorted_constituent_input_is_normalized_before_alignment():
    unsorted = raw_candles("2026-01-01T10:00:00Z", 3, "1h").iloc[::-1]
    frames = {
        "A": normalize_candles(unsorted, "H1", final_candle_complete=True),
        "B": normalized_candles("2026-01-01T10:00:00Z", 3, "1h", "H1", base=200),
    }
    result = align_causal_observations(frames, "2026-01-01T13:00:00Z")
    assert result.frame.index.is_monotonic_increasing
    assert len(result.frame) == 3


@pytest.mark.unit
def test_missing_observation_uses_only_bounded_backward_value():
    frames = {
        "A": normalized_candles("2026-01-01T11:00:00Z", 2, "1h", "H1"),
        "B": normalized_candles("2026-01-01T11:00:00Z", 1, "1h", "H1", base=200),
    }
    result = align_causal_observations(
        frames,
        "2026-01-01T13:00:00Z",
        max_staleness=timedelta(hours=1),
    )
    assert result.frame.loc[pd.Timestamp("2026-01-01T13:00:00Z"), "B"] == 200.0


@pytest.mark.unit
def test_stale_observation_is_rejected_and_reported():
    a_raw = raw_candles("2026-01-01T12:00:01Z", 1, "1h")
    a = normalize_candles(a_raw, "H1", final_available_at="2026-01-01T13:00:01Z")
    b = normalized_candles("2026-01-01T11:00:00Z", 1, "1h", "H1", base=200)
    result = align_causal_observations(
        {"A": a, "B": b},
        "2026-01-01T13:00:01Z",
        max_staleness=timedelta(hours=1),
    )
    assert result.frame.empty
    assert result.diagnostics["B"]["stale_rejections"] == 1


@pytest.mark.unit
def test_future_observation_is_never_backfilled():
    a = normalized_candles("2026-01-01T12:00:00Z", 1, "1h", "H1")
    future = normalized_candles("2026-01-01T13:00:00Z", 1, "1h", "H1", base=200)
    result = align_causal_observations(
        {"A": a, "B": future},
        "2026-01-01T13:00:00Z",
        max_staleness=timedelta(hours=1),
    )
    assert result.frame.empty


@pytest.mark.unit
def test_maximum_staleness_boundary_is_inclusive():
    a = normalized_candles("2026-01-01T12:00:00Z", 1, "1h", "H1")
    b = normalized_candles("2026-01-01T11:00:00Z", 1, "1h", "H1", base=200)
    result = align_causal_observations(
        {"A": a, "B": b},
        "2026-01-01T13:00:00Z",
        max_staleness=timedelta(hours=1),
    )
    assert result.frame.loc[pd.Timestamp("2026-01-01T13:00:00Z"), "B"] == 200.0


@pytest.mark.unit
def test_synthetic_dxy_preserves_formula_after_timestamp_alignment():
    eur = normalized_candles("2026-01-01T09:00:00Z", 3, "1h", "H1", base=2.0)
    jpy = normalized_candles("2026-01-01T10:00:00Z", 2, "1h", "H1", base=100.0)
    gbp = normalized_candles("2026-01-01T10:00:00Z", 2, "1h", "H1", base=1.2)
    cad = normalized_candles("2026-01-01T10:00:00Z", 2, "1h", "H1", base=1.3)
    sek = normalized_candles("2026-01-01T10:00:00Z", 2, "1h", "H1", base=10.0)
    chf = normalized_candles("2026-01-01T10:00:00Z", 2, "1h", "H1", base=0.9)
    values, count, diagnostics = build_synthetic_dxy_from_frames(
        {
            "EURUSDm": eur,
            "USDJPYm": jpy,
            "GBPUSDm": gbp,
            "USDCADm": cad,
            "USDSEKm": sek,
            "USDCHFm": chf,
        },
        "H1",
        3,
        "2026-01-01T12:00:00Z",
    )
    expected_latest = (
        50.14348112
        * 4.0 ** -0.576
        * 101.0 ** 0.136
        * 2.2 ** -0.119
        * 2.3 ** 0.091
        * 11.0 ** 0.042
        * 1.9 ** 0.036
    )
    assert count == 6
    assert values is not None
    assert np.isclose(values[-1], expected_latest)
    assert diagnostics["latest_available_at"] == "2026-01-01T12:00:00+00:00"


@pytest.mark.unit
def test_live_gold_and_dxy_use_one_decision_timestamp(monkeypatch):
    from bot.analysis import dxy_filter

    captured: list[object] = []

    def fake_gold(_symbol, silent=False, decision_timestamp=None):
        captured.append(decision_timestamp)
        return {"direction": "neutral", "state": "range", "lead_bias": None}

    def fake_dxy(_timeframe, _bars, decision_timestamp=None):
        captured.append(decision_timestamp)
        return np.arange(20, dtype=float), 6

    monkeypatch.setattr(dxy_filter, "_gold_direction_snapshot", fake_gold)
    monkeypatch.setattr(dxy_filter, "get_synthetic_dxy", fake_dxy)
    dxy_filter.analyze_dxy_correlation()
    assert len(captured) == 2
    assert captured[0] == captured[1]
    assert captured[0].tzinfo is not None
