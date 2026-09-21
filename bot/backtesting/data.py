from __future__ import annotations

from bisect import bisect_right
from datetime import timedelta
from statistics import mean, median
from typing import Iterable, Iterator

from .models import (
    BidAskBar,
    CostSource,
    DatasetDiagnostics,
    FidelityClass,
    HistoricalExecutionError,
    HistoricalQuote,
    MidBar,
    SpreadObservation,
)


def classify_fidelity(
    *,
    has_bid_ask: bool,
    granularity: str,
    spread_source: CostSource,
    metadata_complete: bool,
    timestamps_unambiguous: bool,
) -> FidelityClass:
    if not metadata_complete or not timestamps_unambiguous:
        return FidelityClass.INSUFFICIENT_FOR_VALIDATION
    normalized = granularity.strip().upper()
    if has_bid_ask and normalized == "TICK":
        return FidelityClass.TICK_BID_ASK
    if has_bid_ask and normalized == "BAR":
        return FidelityClass.BAR_BID_ASK
    if not has_bid_ask and normalized == "BAR":
        if spread_source is CostSource.OBSERVED:
            return FidelityClass.MID_BAR_WITH_OBSERVED_COSTS
        if spread_source is CostSource.ASSUMED:
            return FidelityClass.MID_BAR_WITH_ASSUMED_COSTS
    return FidelityClass.INSUFFICIENT_FOR_VALIDATION


def _gap_is_market_closure(previous, current) -> bool:
    return previous.weekday() == 4 and current.weekday() in (6, 0)


def normalize_quotes(
    records: Iterable[HistoricalQuote],
    *,
    expected_interval: timedelta | None = None,
) -> tuple[tuple[HistoricalQuote, ...], DatasetDiagnostics]:
    original = tuple(records)
    ordered = tuple(sorted(original, key=lambda item: (item.timestamp, item.sequence_id)))
    identities: set[tuple[object, str]] = set()
    timestamps: set[object] = set()
    for quote in ordered:
        identity = (quote.timestamp, quote.sequence_id)
        if identity in identities:
            raise HistoricalExecutionError("duplicate quote timestamp and sequence identity")
        identities.add(identity)
        if quote.timestamp in timestamps and not quote.sequence_id:
            raise HistoricalExecutionError("same-timestamp quotes require sequence identity")
        timestamps.add(quote.timestamp)

    unexplained: list[tuple[str, str]] = []
    closures: list[tuple[str, str]] = []
    if expected_interval is not None:
        if expected_interval.total_seconds() <= 0:
            raise HistoricalExecutionError("expected quote interval must be positive")
        for previous, current in zip(ordered, ordered[1:]):
            if current.timestamp - previous.timestamp <= expected_interval:
                continue
            pair = (previous.timestamp.isoformat(), current.timestamp.isoformat())
            (closures if _gap_is_market_closure(previous.timestamp, current.timestamp) else unexplained).append(pair)
    return ordered, DatasetDiagnostics(
        record_count=len(ordered),
        expected_interval_seconds=None if expected_interval is None else expected_interval.total_seconds(),
        unexplained_gaps=tuple(unexplained),
        market_closure_gaps=tuple(closures),
    )


def normalize_bid_ask_bars(records: Iterable[BidAskBar]) -> tuple[BidAskBar, ...]:
    ordered = tuple(sorted(tuple(records), key=lambda item: (item.open_time, item.sequence_id)))
    identities: set[tuple[object, str]] = set()
    for bar in ordered:
        identity = (bar.open_time, bar.sequence_id)
        if identity in identities:
            raise HistoricalExecutionError("duplicate bid/ask bar identity")
        identities.add(identity)
    return ordered


def causal_quotes(
    quotes: Iterable[HistoricalQuote],
    decision_timestamp,
) -> tuple[HistoricalQuote, ...]:
    from .models import utc_datetime

    decision = utc_datetime(decision_timestamp, "decision timestamp")
    ordered, _ = normalize_quotes(quotes)
    return tuple(quote for quote in ordered if quote.timestamp <= decision)


def iter_normalized_quote_chunks(
    chunks: Iterable[Iterable[HistoricalQuote]],
) -> Iterator[HistoricalQuote]:
    """Normalize bounded chunks while preserving global causal ordering."""
    previous_identity: tuple[object, str] | None = None
    for chunk in chunks:
        ordered, _ = normalize_quotes(chunk)
        for quote in ordered:
            identity = (quote.timestamp, quote.sequence_id)
            if previous_identity is not None and identity <= previous_identity:
                raise HistoricalExecutionError("quote chunks overlap or move backward")
            previous_identity = identity
            yield quote


def spread_statistics(
    quotes: Iterable[HistoricalQuote],
    *,
    point_size: float,
) -> dict[str, float | int]:
    if point_size <= 0:
        raise HistoricalExecutionError("point size must be positive")
    values = sorted(quote.spread_price for quote in quotes)
    if not values:
        raise HistoricalExecutionError("spread statistics require observed quotes")
    p95_index = min(len(values) - 1, max(0, int((len(values) - 1) * 0.95)))
    return {
        "count": len(values),
        "minimum_price": values[0],
        "median_price": median(values),
        "mean_price": mean(values),
        "p95_price": values[p95_index],
        "maximum_price": values[-1],
        "minimum_points": values[0] / point_size,
        "median_points": median(values) / point_size,
        "p95_points": values[p95_index] / point_size,
        "maximum_points": values[-1] / point_size,
    }


def align_observed_spread_to_mid_bars(
    bars: Iterable[MidBar],
    observations: Iterable[SpreadObservation],
    *,
    maximum_staleness: timedelta,
) -> tuple[BidAskBar, ...]:
    if maximum_staleness.total_seconds() < 0:
        raise HistoricalExecutionError("maximum spread staleness cannot be negative")
    ordered_observations = sorted(
        tuple(observations), key=lambda item: (item.timestamp, item.sequence_id)
    )
    timestamps = [item.timestamp for item in ordered_observations]
    result: list[BidAskBar] = []
    for bar in sorted(tuple(bars), key=lambda item: (item.open_time, item.sequence_id)):
        index = bisect_right(timestamps, bar.available_at) - 1
        if index < 0:
            raise HistoricalExecutionError("observed spread is unavailable at bar decision time")
        observation = ordered_observations[index]
        if bar.available_at - observation.timestamp > maximum_staleness:
            raise HistoricalExecutionError("observed spread is stale at bar decision time")
        spread = observation.spread_price
        bid_offset = spread / 2.0 if bar.feed_side == "MID" else 0.0
        ask_offset = spread / 2.0 if bar.feed_side == "MID" else spread
        result.append(BidAskBar(
            symbol=bar.symbol,
            open_time=bar.open_time,
            available_at=bar.available_at,
            bid_open=bar.open - bid_offset,
            bid_high=bar.high - bid_offset,
            bid_low=bar.low - bid_offset,
            bid_close=bar.close - bid_offset,
            ask_open=bar.open + ask_offset,
            ask_high=bar.high + ask_offset,
            ask_low=bar.low + ask_offset,
            ask_close=bar.close + ask_offset,
            source=f"{bar.source}+{observation.source}",
            dataset_id=f"{bar.dataset_id}+{observation.dataset_id}",
            sequence_id=f"{bar.sequence_id}:{observation.sequence_id}",
        ))
    return tuple(result)
