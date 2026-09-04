from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from bot.backtesting import (
    BrokerMetadataCatalog,
    CostSource,
    FidelityClass,
    HistoricalExecutionError,
    MidBar,
    RunMode,
    SlippageKind,
    SpreadObservation,
    align_observed_spread_to_mid_bars,
    classify_fidelity,
    normalize_quotes,
    iter_normalized_quote_chunks,
    spread_statistics,
)
from tests.phase7.helpers import T0, metadata, policy, quote


@pytest.mark.unit
@pytest.mark.parametrize(
    ("has_bid_ask", "granularity", "spread", "complete", "expected"),
    [
        (True, "tick", CostSource.OBSERVED, True, FidelityClass.TICK_BID_ASK),
        (True, "bar", CostSource.OBSERVED, True, FidelityClass.BAR_BID_ASK),
        (False, "bar", CostSource.OBSERVED, True, FidelityClass.MID_BAR_WITH_OBSERVED_COSTS),
        (False, "bar", CostSource.ASSUMED, True, FidelityClass.MID_BAR_WITH_ASSUMED_COSTS),
        (False, "bar", CostSource.NOT_AVAILABLE, True, FidelityClass.INSUFFICIENT_FOR_VALIDATION),
        (True, "tick", CostSource.OBSERVED, False, FidelityClass.INSUFFICIENT_FOR_VALIDATION),
    ],
)
def test_fidelity_classification(has_bid_ask, granularity, spread, complete, expected):
    assert classify_fidelity(
        has_bid_ask=has_bid_ask,
        granularity=granularity,
        spread_source=spread,
        metadata_complete=complete,
        timestamps_unambiguous=True,
    ) is expected


@pytest.mark.unit
def test_quote_requires_utc_aware_positive_uncrossed_prices():
    with pytest.raises(HistoricalExecutionError, match="timezone-aware"):
        replace(quote(1, 100, 101), timestamp=datetime(2026, 1, 1))
    with pytest.raises(HistoricalExecutionError, match="crossed"):
        replace(quote(1, 100, 101), bid=102)
    with pytest.raises(HistoricalExecutionError, match="positive"):
        replace(quote(1, 100, 101), ask=0)


@pytest.mark.unit
def test_quote_contract_rejects_non_executable_symbol():
    with pytest.raises(HistoricalExecutionError, match="XAUUSDm"):
        replace(quote(1, 100, 101), symbol="XAUUSD")


@pytest.mark.unit
def test_normalization_orders_without_mutating_input_and_reports_gaps():
    records = [quote(10, 100, 100.1), quote(1, 99, 99.1)]
    original = list(records)
    ordered, diagnostics = normalize_quotes(records, expected_interval=timedelta(seconds=2))
    assert [item.sequence_id for item in ordered] == ["q-1", "q-10"]
    assert records == original
    assert diagnostics.unexplained_gaps


@pytest.mark.unit
def test_duplicate_quote_identity_is_rejected():
    item = quote(1, 100, 100.1)
    with pytest.raises(HistoricalExecutionError, match="duplicate"):
        normalize_quotes([item, item])


@pytest.mark.unit
def test_metadata_has_dated_exact_xau_contract():
    item = metadata()
    assert item.applies_at(T0)
    assert item.symbol == "XAUUSDm"
    assert item.tick_size == 0.01
    with pytest.raises(HistoricalExecutionError, match="exactly XAUUSDm"):
        replace(item, symbol="XAUUSD")


@pytest.mark.unit
def test_dated_metadata_catalog_selects_one_non_overlapping_segment():
    first = replace(metadata(), effective_to=T0 + timedelta(days=1))
    second = replace(
        metadata(),
        version="synthetic-v2",
        effective_from=T0 + timedelta(days=1),
    )
    catalog = BrokerMetadataCatalog((second, first))
    assert catalog.at(T0).version == "synthetic-v1"
    assert catalog.at(T0 + timedelta(days=2)).version == "synthetic-v2"
    with pytest.raises(HistoricalExecutionError, match="overlap"):
        BrokerMetadataCatalog((metadata(), second))


@pytest.mark.unit
def test_chunked_quote_normalization_preserves_global_order():
    chunks = [[quote(2, 100, 100.1), quote(1, 99, 99.1)], [quote(3, 101, 101.1)]]
    assert [item.sequence_id for item in iter_normalized_quote_chunks(chunks)] == ["q-1", "q-2", "q-3"]
    with pytest.raises(HistoricalExecutionError, match="overlap"):
        tuple(iter_normalized_quote_chunks([[quote(2, 100, 100.1)], [quote(1, 99, 99.1)]]))


@pytest.mark.unit
def test_observed_spread_alignment_is_backward_causal_and_staleness_bounded():
    bar = MidBar(
        symbol="XAUUSDm", open_time=T0, available_at=T0 + timedelta(minutes=5),
        open=100, high=101, low=99, close=100.5, source="mid-bars",
        dataset_id="mid", sequence_id="bar-1",
    )
    observed = SpreadObservation(
        symbol="XAUUSDm", timestamp=T0 + timedelta(minutes=4), spread_price=0.2,
        source="broker-spread", dataset_id="spread", sequence_id="spread-1",
    )
    aligned = align_observed_spread_to_mid_bars(
        [bar], [observed], maximum_staleness=timedelta(minutes=2)
    )[0]
    assert aligned.ask_close - aligned.bid_close == pytest.approx(0.2)
    future = replace(observed, timestamp=T0 + timedelta(minutes=6))
    with pytest.raises(HistoricalExecutionError, match="unavailable"):
        align_observed_spread_to_mid_bars(
            [bar], [future], maximum_staleness=timedelta(minutes=2)
        )
    stale = replace(observed, timestamp=T0)
    with pytest.raises(HistoricalExecutionError, match="stale"):
        align_observed_spread_to_mid_bars(
            [bar], [stale], maximum_staleness=timedelta(minutes=2)
        )


@pytest.mark.unit
def test_observed_spread_statistics_report_price_and_point_units():
    stats = spread_statistics(
        [quote(1, 100, 100.1), quote(2, 100, 100.2)], point_size=0.01
    )
    assert stats["count"] == 2
    assert stats["minimum_points"] == pytest.approx(10)
    assert stats["maximum_points"] == pytest.approx(20)


@pytest.mark.unit
def test_validation_mode_rejects_assumed_or_missing_cost_provenance():
    with pytest.raises(HistoricalExecutionError, match="observed slippage"):
        policy(mode=RunMode.VALIDATION, slippage_points=1, slippage_source=CostSource.ASSUMED)
    with pytest.raises(HistoricalExecutionError, match="validation-eligible"):
        policy(mode=RunMode.VALIDATION, fidelity=FidelityClass.MID_BAR_WITH_ASSUMED_COSTS)


@pytest.mark.unit
def test_diagnostic_label_is_unmistakable():
    item = policy()
    assert item.result_label == "DIAGNOSTIC \u2014 NOT VALIDATED"
    assert "VALIDATED" in item.result_label
