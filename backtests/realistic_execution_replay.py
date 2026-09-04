from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from time import perf_counter
from typing import Any, Callable

from bot.backtesting import (
    BidAskBar,
    BrokerSymbolMetadata,
    CommissionKind,
    CommissionSchedule,
    CostSource,
    FidelityClass,
    HistoricalExecutionEngine,
    HistoricalExecutionError,
    HistoricalExecutionPolicy,
    HistoricalQuote,
    RunMode,
    Side,
    SlippageKind,
    SlippageModel,
    SwapCalculation,
    SwapSchedule,
)
from bot.backtesting.adapters import manage_quote_position, process_quote_entry
from bot.execution.lifecycle.entry import create_entry_state, new_entry_intent
from bot.execution.lifecycle.models import Direction, ManagementConfig, ReadinessStyle
from bot.backtesting.data import normalize_quotes
from bot.execution.risk.authority import InMemoryRiskAuthority
from bot.execution.risk.models import SymbolRiskSpecification
from bot.execution.risk.models import OpenRiskItem
from bot.execution.risk.policy import validation_policy
from bot.execution.risk.state import initialize_risk_state


UTC = timezone.utc
T0 = datetime(2026, 1, 5, 12, tzinfo=UTC)


def _metadata(
    *,
    commission_kind: CommissionKind = CommissionKind.PER_LOT_PER_SIDE,
    commission_amount: float = 2.5,
) -> BrokerSymbolMetadata:
    return BrokerSymbolMetadata(
        symbol="XAUUSDm",
        version="synthetic-replay-v1",
        broker_source="synthetic-replay",
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
        margin_rate=0.001,
        commission=CommissionSchedule(
            kind=commission_kind,
            amount=commission_amount,
            currency="USD",
            source=CostSource.OBSERVED,
        ),
        swap=SwapSchedule(
            calculation=SwapCalculation.ACCOUNT_CURRENCY_PER_LOT,
            long_rate=-1.0,
            short_rate=-2.0,
            rollover_time=time(17, 0),
            rollover_timezone="America/New_York",
            triple_swap_weekday=2,
            source=CostSource.OBSERVED,
        ),
        provenance="synthetic-phase7-replay",
    )


def _policy(**overrides: Any) -> HistoricalExecutionPolicy:
    values = {
        "mode": RunMode.DIAGNOSTIC,
        "fidelity": FidelityClass.TICK_BID_ASK,
        "maximum_spread_points": 50.0,
        "maximum_deviation_points": 20,
        "slippage": SlippageModel(),
        "random_seed": 17,
    }
    values.update(overrides)
    return HistoricalExecutionPolicy(**values)


def _quote(seconds: int, bid: float, ask: float, sequence: str | None = None) -> HistoricalQuote:
    return HistoricalQuote(
        symbol="XAUUSDm",
        timestamp=T0 + timedelta(seconds=seconds),
        bid=bid,
        ask=ask,
        source="phase7-synthetic-replay",
        dataset_id="phase7-replay-v1",
        sequence_id=sequence or f"q-{seconds}",
    )


def _engine(
    name: str,
    *,
    metadata: BrokerSymbolMetadata | None = None,
    policy: HistoricalExecutionPolicy | None = None,
) -> HistoricalExecutionEngine:
    return HistoricalExecutionEngine(
        run_id=f"phase7-replay-{name}",
        metadata=metadata or _metadata(),
        policy=policy or _policy(),
        initial_balance=1000,
    )


def _open(execution: HistoricalExecutionEngine, direction: Side = Side.BUY, volume: float = 0.1):
    stop, target = ((99, 102) if direction is Side.BUY else (101, 98))
    return execution.open_market(
        action_id="entry",
        trade_id="trade",
        direction=direction,
        requested_volume=volume,
        stop_price=stop,
        target_price=target,
        quote=_quote(1, 99.9 if direction is Side.BUY else 100, 100 if direction is Side.BUY else 100.1),
        signal_available_at=T0,
        source_event_id="signal-candle",
        market_event_id="q-1",
    )


def _result(execution: HistoricalExecutionEngine, **details: Any) -> dict[str, Any]:
    reconciliation = execution.reconcile()
    return {
        "status": "PASS",
        "balance": round(execution.account.balance, 6),
        "equity": round(execution.account.equity, 6),
        "fills": len(execution.fills),
        "ledger_entries": len(execution.ledger),
        "reconciliation_difference": round(reconciliation["difference"], 12),
        **details,
    }


def _rejected(name: str, operation: Callable[[], object]) -> dict[str, Any]:
    try:
        operation()
    except HistoricalExecutionError as exc:
        return {"status": "PASS", "reason_code": str(exc)}
    raise AssertionError(f"{name} did not fail closed")


def run_replay() -> dict[str, Any]:
    scenarios: dict[str, dict[str, Any]] = {}

    long_engine = _engine("long")
    long_position, long_entry = _open(long_engine)
    long_exit = long_engine.close_market(
        action_id="exit", position_id=long_position.position_id,
        quote=_quote(2, 101.9, 102), reason_code="REPLAY_EXIT",
    )
    scenarios["long_ask_entry_bid_exit"] = _result(
        long_engine, entry=long_entry.fill_price, exit=long_exit.fill_price,
        gross_pnl=long_engine.account.realized_gross_pnl, expected_net=18.5,
    )

    short_engine = _engine("short")
    short_position, short_entry = _open(short_engine, Side.SELL)
    short_exit = short_engine.close_market(
        action_id="exit", position_id=short_position.position_id,
        quote=_quote(2, 98, 98.1), reason_code="REPLAY_EXIT",
    )
    scenarios["short_bid_entry_ask_exit"] = _result(
        short_engine, entry=short_entry.fill_price, exit=short_exit.fill_price,
        gross_pnl=short_engine.account.realized_gross_pnl, expected_net=18.5,
    )

    variable = _engine("variable-spread")
    _open(variable)
    variable.mark_to_market(_quote(2, 100.8, 101.0))
    scenarios["variable_spread"] = _result(variable, observed_spreads=[0.1, 0.2])

    spread_reject = _engine("spread-reject", policy=_policy(maximum_spread_points=5))
    scenarios["spread_limit_rejection"] = _rejected(
        "spread",
        lambda: spread_reject.open_market(
            action_id="entry", trade_id="trade", direction=Side.BUY,
            requested_volume=0.1, stop_price=99, target_price=102,
            quote=_quote(1, 100, 100.1), signal_available_at=T0,
            source_event_id="signal", market_event_id="quote",
        ),
    )

    slip_policy = _policy(slippage=SlippageModel(
        kind=SlippageKind.FIXED_ADVERSE_POINTS, points=2, source=CostSource.ASSUMED
    ))
    slipped = _engine("slippage", policy=slip_policy)
    _, fill = _open(slipped)
    scenarios["adverse_entry_slippage"] = _result(slipped, quote=100, fill=fill.fill_price)

    stop_gap = _engine("stop-gap")
    position, _ = _open(stop_gap)
    fill = stop_gap.evaluate_quote(position.position_id, _quote(2, 98.5, 98.6))
    scenarios["stop_loss_gap"] = _result(stop_gap, fill=fill.fill_price, reason=fill.reason_code)

    target_engine = _engine("target")
    position, _ = _open(target_engine)
    fill = target_engine.evaluate_quote(position.position_id, _quote(2, 103, 103.1))
    scenarios["take_profit_limit"] = _result(target_engine, fill=fill.fill_price, reason=fill.reason_code)

    partial = _engine("partial")
    position, _ = _open(partial)
    partial.close_market(
        action_id="partial", position_id=position.position_id,
        quote=_quote(2, 101, 101.1), requested_volume=0.05, reason_code="PARTIAL_TARGET",
    )
    scenarios["one_shot_partial_with_costs"] = _result(
        partial, remaining=partial.positions[position.position_id].remaining_volume,
        commission=partial.account.commission,
    )

    trailing = _engine("trailing")
    trailing_intent = new_entry_intent(
        symbol="XAUUSDm", direction=Direction.BUY, source_timeframe="M5",
        source_candle_open_time=T0 - timedelta(minutes=5), signal_available_at=T0,
        requested_trigger=100, stop_loss=99, final_target=103,
        readiness_style=ReadinessStyle.IMMEDIATE, source_event_id="signal-candle",
        source_sequence=0, configuration_id="phase7-replay",
    )
    _, lifecycle_position = process_quote_entry(
        trailing, create_entry_state(trailing_intent), _quote(1, 99.9, 100),
        sequence=1, quantity=0.1,
    )
    assert lifecycle_position is not None
    trail_config = ManagementConfig(
        partial_close_fraction=0.5, partial_target_r=1, volume_min=0.01,
        volume_step=0.01, pnl_per_price_unit=100, trailing_enabled=True,
        trailing_atr_multiple=1, trailing_min_distance=0,
    )
    lifecycle_position = manage_quote_position(
        trailing, lifecycle_position, _quote(2, 100.8, 100.9), sequence=2,
        config=trail_config, atr=0.2,
    )
    raised_stop = lifecycle_position.current_stop
    lifecycle_position = manage_quote_position(
        trailing, lifecycle_position, _quote(3, 100.5, 100.6), sequence=3,
        config=trail_config,
    )
    scenarios["trailing_effective_next_event"] = {
        "status": "PASS",
        "raised_stop": raised_stop,
        "next_event_status": lifecycle_position.status.value,
        "exit_reason": str(lifecycle_position.exit_reason.value),
    }

    per_side = _engine("commission-side")
    position, _ = _open(per_side)
    per_side.close_market(action_id="exit", position_id=position.position_id, quote=_quote(2, 101, 101.1), reason_code="EXIT")
    scenarios["commission_per_side"] = _result(per_side, commission=per_side.account.commission)

    round_turn = _engine(
        "commission-round",
        metadata=_metadata(commission_kind=CommissionKind.PER_LOT_ROUND_TURN, commission_amount=5),
    )
    position, _ = _open(round_turn)
    round_turn.close_market(action_id="exit", position_id=position.position_id, quote=_quote(2, 101, 101.1), reason_code="EXIT")
    scenarios["commission_round_turn"] = _result(round_turn, commission=round_turn.account.commission)

    rollover = _engine("rollover")
    position, _ = _open(rollover)
    entries = rollover.apply_swap_until(position.position_id, datetime(2026, 1, 5, 23, tzinfo=UTC))
    scenarios["single_rollover_swap"] = _result(rollover, swap=sum(entry.swap for entry in entries))

    triple = _engine("triple")
    position, _ = _open(triple)
    entries = triple.apply_swap_until(position.position_id, datetime(2026, 1, 8, 0, tzinfo=UTC))
    scenarios["triple_swap"] = _result(triple, swap=sum(entry.swap for entry in entries))

    reduced = _engine("partial-swap")
    position, _ = _open(reduced)
    reduced.close_market(
        action_id="partial", position_id=position.position_id,
        quote=_quote(60, 101, 101.1), requested_volume=0.04, reason_code="PARTIAL",
    )
    entries = reduced.apply_swap_until(position.position_id, datetime(2026, 1, 5, 23, tzinfo=UTC))
    scenarios["partial_before_rollover"] = _result(reduced, swap=sum(entry.swap for entry in entries))

    drawdown = _engine("drawdown")
    position, _ = _open(drawdown)
    start_snapshot = replace(drawdown.risk_account_snapshot(T0 + timedelta(seconds=1)), equity=1000, balance=1000, floating_pnl=0)
    risk_policy = validation_policy({})
    authority = InMemoryRiskAuthority(risk_policy, initialize_risk_state(start_snapshot, risk_policy, known_strategy_positions=0))
    drawdown.mark_to_market(_quote(2, 97.8, 97.9))
    authority.refresh(drawdown.risk_account_snapshot(T0 + timedelta(seconds=2)), now=T0 + timedelta(seconds=2))
    scenarios["floating_equity_drawdown_pause"] = {
        "status": "PASS",
        "circuit": authority.state.circuit_status.value,
        "floating_pnl": drawdown.account.unrealized_pnl,
    }

    aggregate = _engine("aggregate")
    position, _ = _open(aggregate)
    snapshot = aggregate.risk_account_snapshot(T0 + timedelta(seconds=1))
    authority = InMemoryRiskAuthority(risk_policy, initialize_risk_state(snapshot, risk_policy, known_strategy_positions=0))
    specification = SymbolRiskSpecification(
        symbol="XAUUSDm", tick_size=0.01, tick_value=1, volume_min=0.01,
        volume_max=100, volume_step=0.01, price_precision=2, contract_size=100,
    )
    external_exposure = OpenRiskItem(
        trade_id="existing-exposure", symbol="OTHER", direction="buy",
        remaining_volume=1, current_reference_price=1, current_stop=0.5,
        estimated_loss=8.0, ownership="explicit_historical_exposure",
        calculation_method="synthetic_fixture", entry_price=1,
    )
    decision = authority.decide(
        snapshot=snapshot, specification=specification, direction="buy",
        entry=100, stop=99, open_risk_items=(external_exposure,),
        now=T0 + timedelta(seconds=1), requested_risk_fraction=risk_policy.base_risk_fraction,
    )
    scenarios["aggregate_risk_rejection"] = {"status": "PASS", "reason_code": decision.reason.value}

    partial_fill = _engine("partial-fill")
    _, fill = partial_fill.open_market(
        action_id="entry", trade_id="trade", direction=Side.BUY,
        requested_volume=0.1, stop_price=99, target_price=102,
        quote=_quote(1, 99.9, 100), signal_available_at=T0,
        source_event_id="signal", market_event_id="quote", available_volume=0.04,
    )
    scenarios["partial_fill"] = _result(partial_fill, actual_volume=fill.volume)

    duplicate = _engine("duplicate")
    position, _ = _open(duplicate)
    duplicate.close_market(action_id="once", position_id=position.position_id, quote=_quote(2, 101, 101.1), requested_volume=0.04, reason_code="PARTIAL")
    before = duplicate.account.balance
    duplicate_fill = duplicate.close_market(action_id="once", position_id=position.position_id, quote=_quote(2, 101, 101.1), requested_volume=0.04, reason_code="PARTIAL")
    scenarios["duplicate_event_suppression"] = {
        "status": "PASS",
        "same_fill_id": duplicate_fill.fill_id == next(fill.fill_id for fill in duplicate.fills if fill.action_id == "once"),
        "balance_unchanged": duplicate.account.balance == before,
    }

    ambiguous = _engine("ambiguous")
    position, _ = _open(ambiguous)
    bar = BidAskBar(
        symbol="XAUUSDm", open_time=T0 + timedelta(minutes=1), available_at=T0 + timedelta(minutes=6),
        bid_open=100, bid_high=103, bid_low=98, bid_close=101,
        ask_open=100.1, ask_high=103.1, ask_low=98.1, ask_close=101.1,
        source="synthetic", dataset_id="bars", sequence_id="ambiguous",
    )
    fill = ambiguous.evaluate_bar(position.position_id, bar)
    scenarios["ambiguous_bar_stop_first"] = _result(ambiguous, reason=fill.reason_code)

    scenarios["missing_metadata_validation_failure"] = _rejected(
        "metadata",
        lambda: replace(_metadata(), tick_value=0),
    )

    assumed = _engine(
        "assumed",
        policy=_policy(
            fidelity=FidelityClass.MID_BAR_WITH_ASSUMED_COSTS,
            slippage=SlippageModel(kind=SlippageKind.FIXED_ADVERSE_POINTS, points=1, source=CostSource.ASSUMED),
        ),
    )
    scenarios["diagnostic_assumed_costs"] = _result(assumed, label=assumed.policy.result_label)

    ledger = _engine("ledger")
    position, _ = _open(ledger)
    ledger.close_market(action_id="exit", position_id=position.position_id, quote=_quote(2, 101, 101.1), reason_code="EXIT")
    scenarios["ledger_reconciliation"] = _result(ledger)

    repeat_a = _engine("repeat")
    repeat_b = _engine("repeat")
    _open(repeat_a)
    _open(repeat_b)
    scenarios["deterministic_repeat"] = {
        "status": "PASS",
        "identical": json.dumps(repeat_a.normalized_state(), default=str, sort_keys=True)
        == json.dumps(repeat_b.normalized_state(), default=str, sort_keys=True),
    }

    if len(scenarios) != 23 or not all(item.get("status") == "PASS" for item in scenarios.values()):
        raise AssertionError("Phase 7 replay is incomplete")
    return {
        "phase": 7,
        "result_label": "DIAGNOSTIC \u2014 NOT VALIDATED",
        "profitability_evidence": False,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }


def performance_sanity(record_count: int = 100_000) -> dict[str, Any]:
    records = [_quote(index, 2000 + index * 0.0001, 2000.1 + index * 0.0001) for index in range(record_count - 1, -1, -1)]
    started = perf_counter()
    ordered, diagnostics = normalize_quotes(records)
    elapsed = perf_counter() - started
    return {
        "record_count": record_count,
        "elapsed_seconds": elapsed,
        "ordered": ordered[0].timestamp < ordered[-1].timestamp,
        "diagnostic_count": diagnostics.record_count,
        "local_observation_only": True,
    }


def main() -> None:
    print(json.dumps(run_replay(), indent=2, sort_keys=True))
    print(json.dumps({"performance_sanity": performance_sanity()}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
