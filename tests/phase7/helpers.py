from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from bot.backtesting import (
    BrokerSymbolMetadata,
    CommissionKind,
    CommissionSchedule,
    CostSource,
    FidelityClass,
    HistoricalExecutionEngine,
    HistoricalExecutionPolicy,
    HistoricalQuote,
    RunMode,
    SlippageKind,
    SlippageModel,
    SwapCalculation,
    SwapSchedule,
)


UTC = timezone.utc
T0 = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def metadata(
    *,
    commission_kind: CommissionKind = CommissionKind.PER_LOT_PER_SIDE,
    commission_amount: float = 2.5,
    commission_source: CostSource = CostSource.OBSERVED,
    swap_source: CostSource = CostSource.OBSERVED,
    long_swap: float = -1.0,
    short_swap: float = -2.0,
    rollover_timezone: str = "America/New_York",
    rollover_time: time = time(17, 0),
    triple_weekday: int = 2,
    margin_rate: float = 0.001,
) -> BrokerSymbolMetadata:
    return BrokerSymbolMetadata(
        symbol="XAUUSDm",
        version="synthetic-v1",
        broker_source="fixture-broker",
        effective_from=datetime(2025, 1, 1, tzinfo=UTC),
        effective_to=None,
        digits=2,
        point_size=0.01,
        tick_size=0.01,
        tick_value=1.0,
        contract_size=100.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        account_currency="USD",
        profit_currency="USD",
        margin_currency="USD",
        margin_rate=margin_rate,
        commission=CommissionSchedule(
            kind=commission_kind,
            amount=commission_amount,
            currency="USD",
            source=commission_source,
        ),
        swap=SwapSchedule(
            calculation=SwapCalculation.ACCOUNT_CURRENCY_PER_LOT,
            long_rate=long_swap,
            short_rate=short_swap,
            rollover_time=rollover_time,
            rollover_timezone=rollover_timezone,
            triple_swap_weekday=triple_weekday,
            source=swap_source,
        ),
        provenance="synthetic-test-fixture",
    )


def policy(
    *,
    mode: RunMode = RunMode.DIAGNOSTIC,
    fidelity: FidelityClass = FidelityClass.TICK_BID_ASK,
    max_spread_points: float = 50,
    slippage_points: float = 0,
    slippage_kind: SlippageKind | None = None,
    slippage_source: CostSource = CostSource.OBSERVED,
    seed: int = 7,
    deviation_points: int = 20,
) -> HistoricalExecutionPolicy:
    kind = slippage_kind or (
        SlippageKind.NONE if slippage_points == 0 else SlippageKind.FIXED_ADVERSE_POINTS
    )
    source = CostSource.NOT_AVAILABLE if kind is SlippageKind.NONE else slippage_source
    return HistoricalExecutionPolicy(
        mode=mode,
        fidelity=fidelity,
        maximum_spread_points=max_spread_points,
        maximum_deviation_points=deviation_points,
        slippage=SlippageModel(kind=kind, points=slippage_points, source=source),
        random_seed=seed,
    )


def quote(
    offset_seconds: int,
    bid: float,
    ask: float,
    *,
    sequence: str | None = None,
    bid_volume: float | None = None,
    ask_volume: float | None = None,
) -> HistoricalQuote:
    return HistoricalQuote(
        symbol="XAUUSDm",
        timestamp=T0 + timedelta(seconds=offset_seconds),
        bid=bid,
        ask=ask,
        source="synthetic",
        dataset_id="phase7-fixture",
        sequence_id=sequence or f"q-{offset_seconds}",
        bid_volume=bid_volume,
        ask_volume=ask_volume,
    )


def engine(**policy_overrides) -> HistoricalExecutionEngine:
    return HistoricalExecutionEngine(
        run_id="phase7-test-run",
        metadata=metadata(),
        policy=policy(**policy_overrides),
        initial_balance=1000.0,
    )


def open_long(target: float = 102.0, **policy_overrides):
    execution = engine(**policy_overrides)
    position, fill = execution.open_market(
        action_id="entry-long",
        trade_id="trade-long",
        direction=__import__("bot.backtesting", fromlist=["Side"]).Side.BUY,
        requested_volume=0.10,
        stop_price=99.0,
        target_price=target,
        quote=quote(1, 99.90, 100.00),
        signal_available_at=T0,
        source_event_id="signal-bar",
        market_event_id="q-1",
    )
    return execution, position, fill
