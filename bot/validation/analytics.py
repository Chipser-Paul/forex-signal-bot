from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Mapping, Sequence

from .models import TradeSample, ValidationError, finite


def _profit_factor(values: Sequence[float]) -> tuple[float | None, str | None]:
    profits = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if not values:
        return None, "NO_TRADES"
    if losses == 0:
        return None, "NO_LOSING_TRADES"
    return profits / losses, None


def _maximum_drawdown(values: Sequence[tuple[datetime, float]]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    high = values[0][1]
    high_time = values[0][0]
    maximum_amount = 0.0
    maximum_fraction = 0.0
    duration = 0.0
    for timestamp, value in values:
        if value >= high:
            high = value
            high_time = timestamp
            continue
        amount = high - value
        fraction = amount / high if high > 0 else 0.0
        if fraction > maximum_fraction:
            maximum_amount = amount
            maximum_fraction = fraction
            duration = (timestamp - high_time).total_seconds()
    return maximum_amount, maximum_fraction, duration


def _concentration(trades: Sequence[TradeSample]) -> Mapping[str, float | None]:
    positives = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    total = sum(positives)
    if total <= 0:
        return {"best_trade": None, "best_day": None, "best_week": None, "best_month": None}

    def best_group(key: Callable[[TradeSample], Any]) -> float:
        groups: dict[Any, float] = defaultdict(float)
        for trade in trades:
            groups[key(trade)] += max(0.0, trade.net_pnl)
        return max(groups.values(), default=0.0) / total

    return {
        "best_trade": max(positives) / total,
        "best_day": best_group(lambda trade: trade.closed_at.date().isoformat()),
        "best_week": best_group(lambda trade: trade.closed_at.isocalendar()[:2]),
        "best_month": best_group(lambda trade: (trade.closed_at.year, trade.closed_at.month)),
    }


def _slice_summary(trades: Sequence[TradeSample], attribute: str) -> Mapping[str, Mapping[str, float | int | None]]:
    groups: dict[str, list[TradeSample]] = defaultdict(list)
    for trade in trades:
        value = trade.closed_at.year if attribute == "year" else getattr(trade, attribute)
        groups[str(value)].append(trade)
    output = {}
    for key, items in sorted(groups.items()):
        net = [item.net_pnl for item in items]
        factor, _ = _profit_factor(net)
        output[key] = {
            "trade_count": len(items),
            "net_pnl": sum(net),
            "mean_net_pnl": statistics.fmean(net),
            "profit_factor_net": factor,
        }
    return output


def calculate_metrics(
    trades: Sequence[TradeSample],
    *,
    initial_capital: float,
    executable_equity: Sequence[tuple[datetime, float]] | None = None,
    rejections: Sequence[Mapping[str, Any]] = (),
    circuit_events: Sequence[str] = (),
) -> Mapping[str, Any]:
    capital = finite(initial_capital, "initial capital")
    if capital <= 0:
        raise ValidationError("initial capital must be positive")
    ordered = tuple(sorted(trades, key=lambda item: (item.closed_at, item.trade_id)))
    net = [item.net_pnl for item in ordered]
    gross = [item.gross_pnl for item in ordered]
    wins = sum(value > 0 for value in net)
    gross_factor, gross_factor_reason = _profit_factor(gross)
    net_factor, net_factor_reason = _profit_factor(net)
    balance = capital
    balance_path = [(ordered[0].opened_at, balance)] if ordered else []
    for trade in ordered:
        balance += trade.net_pnl
        balance_path.append((trade.closed_at, balance))
    balance_dd = _maximum_drawdown(balance_path)
    equity_dd = _maximum_drawdown(tuple(executable_equity or balance_path))
    gross_profit = sum(value for value in gross if value > 0)
    rejection_counts: dict[str, int] = defaultdict(int)
    for rejection in rejections:
        rejection_counts[str(rejection.get("reason_code", "UNKNOWN"))] += 1
    circuit_counts: dict[str, int] = defaultdict(int)
    for event in circuit_events:
        circuit_counts[str(event)] += 1
    return {
        "status": "NO_TRADES" if not ordered else "CALCULATED",
        "trade_count": len(ordered),
        "gross_pnl": sum(gross),
        "net_pnl": sum(net),
        "cost_total": sum(item.costs for item in ordered),
        "cost_to_gross_profit": None if gross_profit <= 0 else sum(item.costs for item in ordered) / gross_profit,
        "win_rate": None if not ordered else wins / len(ordered),
        "profit_factor_gross": gross_factor,
        "profit_factor_gross_boundary": gross_factor_reason,
        "profit_factor_net": net_factor,
        "profit_factor_net_boundary": net_factor_reason,
        "expectancy_per_trade": None if not ordered else statistics.fmean(net),
        "expectancy_r": None if not ordered else statistics.fmean(item.net_r for item in ordered),
        "median_trade": None if not ordered else statistics.median(net),
        "maximum_balance_drawdown": balance_dd[0],
        "maximum_balance_drawdown_fraction": balance_dd[1],
        "maximum_executable_equity_drawdown": equity_dd[0],
        "maximum_executable_equity_drawdown_fraction": equity_dd[1],
        "drawdown_duration_seconds": equity_dd[2],
        "recovery_factor": None if equity_dd[0] == 0 else sum(net) / equity_dd[0],
        "exposure_seconds": sum(item.exposure_seconds for item in ordered),
        "turnover": sum(item.turnover for item in ordered),
        "long_short": _slice_summary(ordered, "side"),
        "by_year": _slice_summary(ordered, "year"),
        "by_regime": _slice_summary(ordered, "regime"),
        "by_session": _slice_summary(ordered, "session"),
        "by_spread_environment": _slice_summary(ordered, "spread_environment"),
        "profit_concentration": _concentration(ordered),
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "risk_circuit_activations": dict(sorted(circuit_counts.items())),
        "minimum_lot_rejections": rejection_counts.get("MINIMUM_VOLUME_EXCEEDS_RISK", 0),
        "insufficient_margin_rejections": rejection_counts.get("INSUFFICIENT_MARGIN", 0),
        "ending_balance": balance,
    }


def three_month_outcomes(
    trades: Sequence[TradeSample],
    *,
    start: datetime,
    end: datetime,
) -> Mapping[str, Any]:
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValidationError("three-month analysis requires increasing aware boundaries")
    windows = []
    cursor = start
    while cursor < end:
        boundary = min(end, cursor + timedelta(days=90))
        items = [trade for trade in trades if cursor <= trade.closed_at < boundary]
        net = sum(item.net_pnl for item in items)
        windows.append({
            "start": cursor,
            "end": boundary,
            "trade_count": len(items),
            "net_pnl": net,
            "outcome": "PROFITABLE" if net > 0 else "LOSING" if net < 0 else "FLAT",
        })
        cursor = boundary
    return {
        "windows": windows,
        "profitable_windows": sum(item["outcome"] == "PROFITABLE" for item in windows),
        "losing_windows": sum(item["outcome"] == "LOSING" for item in windows),
        "flat_windows": sum(item["outcome"] == "FLAT" for item in windows),
        "target_fitted": False,
    }


@dataclass(frozen=True)
class AccountPathResult:
    ending_equity: float
    maximum_drawdown_fraction: float
    hard_stop_breached: bool
    daily_pause_activated: bool
    weekly_pause_activated: bool
    loss_streak_pause_activated: bool
    loss: bool
    path: tuple[float, ...]
    processed_trades: int
    skipped_trades: int


def simulate_account_path(
    trades: Sequence[TradeSample],
    *,
    initial_capital: float = 1000.0,
    risk_fraction: float = 0.0035,
    hard_stop_fraction: float = 0.08,
    cost_multiplier: float = 1.0,
) -> AccountPathResult:
    equity = finite(initial_capital, "initial capital")
    risk = finite(risk_fraction, "risk fraction")
    if equity <= 0 or not 0 < risk <= 0.005 or not 0 < hard_stop_fraction < 1 or cost_multiplier < 0:
        raise ValidationError("account-path settings violate the Phase 4 envelope")
    high = equity
    daily_start = equity
    daily_high = equity
    weekly_start = equity
    weekly_high = equity
    current_day = None
    current_week = None
    daily_paused = False
    weekly_paused = False
    loss_streak_paused = False
    daily_ever = False
    weekly_ever = False
    loss_streak_ever = False
    consecutive_losses = 0
    maximum_drawdown = 0.0
    path = [equity]
    hard_stop = False
    processed = 0
    skipped = 0
    for trade in trades:
        day = trade.closed_at.date()
        week = trade.closed_at.isocalendar()[:2]
        if current_day != day:
            current_day = day
            daily_start = equity
            daily_high = equity
            daily_paused = False
        if current_week != week:
            current_week = week
            weekly_start = equity
            weekly_high = equity
            weekly_paused = False
        if daily_paused or weekly_paused or loss_streak_paused:
            skipped += 1
            continue
        risk_budget = equity * risk
        base_cost_r = trade.costs / max(initial_capital * risk, 1e-12)
        stressed_r = trade.net_r - max(0.0, cost_multiplier - 1.0) * base_cost_r
        equity += risk_budget * stressed_r
        high = max(high, equity)
        drawdown = (high - equity) / high if high > 0 else 1.0
        maximum_drawdown = max(maximum_drawdown, drawdown)
        path.append(equity)
        processed += 1
        daily_high = max(daily_high, equity)
        weekly_high = max(weekly_high, equity)
        daily_drawdown = max(
            (daily_start - equity) / daily_start,
            (daily_high - equity) / daily_high,
        )
        weekly_drawdown = max(
            (weekly_start - equity) / weekly_start,
            (weekly_high - equity) / weekly_high,
        )
        daily_paused = daily_drawdown >= 0.02
        weekly_paused = weekly_drawdown >= 0.04
        daily_ever = daily_ever or daily_paused
        weekly_ever = weekly_ever or weekly_paused
        if stressed_r < 0:
            consecutive_losses += 1
        elif stressed_r > 0:
            consecutive_losses = 0
        if consecutive_losses >= 3:
            loss_streak_paused = True
            loss_streak_ever = True
        if drawdown >= hard_stop_fraction:
            hard_stop = True
            break
    return AccountPathResult(
        ending_equity=equity,
        maximum_drawdown_fraction=maximum_drawdown,
        hard_stop_breached=hard_stop,
        daily_pause_activated=daily_ever,
        weekly_pause_activated=weekly_ever,
        loss_streak_pause_activated=loss_streak_ever,
        loss=equity < initial_capital,
        path=tuple(path),
        processed_trades=processed,
        skipped_trades=skipped,
    )


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def moving_block_bootstrap(
    trades: Sequence[TradeSample],
    *,
    replicates: int,
    block_length: int,
    seed: int,
    initial_capital: float = 1000.0,
    risk_fraction: float = 0.0035,
) -> Mapping[str, Any]:
    if replicates < 1 or block_length < 1 or (trades and block_length > len(trades)):
        raise ValidationError("bootstrap replicates and block length are invalid")
    if not trades:
        return {"status": "NO_TRADES", "replicates": 0, "seed": seed, "block_length": block_length}
    source = tuple(trades)
    rng = random.Random(seed)
    expectancies: list[float] = []
    win_rates: list[float] = []
    profit_factors: list[float] = []
    drawdowns: list[float] = []
    losses = 0
    breaches = 0
    threshold_breaches = {"daily_0.02": 0, "weekly_0.04": 0, "total_0.08": 0, "loss_streak_3": 0}
    horizon_losses = {str(horizon): 0 for horizon in sorted({min(len(source), 5), min(len(source), 10), len(source)}) if horizon > 0}
    maximum_start = len(source) - block_length
    for _ in range(replicates):
        sample: list[TradeSample] = []
        while len(sample) < len(source):
            start = rng.randint(0, maximum_start)
            sample.extend(source[start:start + block_length])
        sample = sample[:len(source)]
        expectancies.append(statistics.fmean(item.net_r for item in sample))
        win_rates.append(sum(item.net_r > 0 for item in sample) / len(sample))
        factor, _ = _profit_factor([item.net_r for item in sample])
        if factor is not None:
            profit_factors.append(factor)
        timed_sample = tuple(replace(
            item,
            opened_at=source[index].opened_at,
            closed_at=source[index].closed_at,
        ) for index, item in enumerate(sample))
        account = simulate_account_path(timed_sample, initial_capital=initial_capital, risk_fraction=risk_fraction)
        drawdowns.append(account.maximum_drawdown_fraction)
        losses += account.loss
        breaches += account.hard_stop_breached
        threshold_breaches["daily_0.02"] += account.daily_pause_activated
        threshold_breaches["weekly_0.04"] += account.weekly_pause_activated
        threshold_breaches["total_0.08"] += account.hard_stop_breached
        threshold_breaches["loss_streak_3"] += account.loss_streak_pause_activated
        for horizon in horizon_losses:
            horizon_losses[horizon] += simulate_account_path(
                timed_sample[:int(horizon)], initial_capital=initial_capital, risk_fraction=risk_fraction
            ).loss
    interval = lambda values: [_percentile(values, 0.025), _percentile(values, 0.975)]
    return {
        "status": "CALCULATED",
        "method": "MOVING_BLOCK_BOOTSTRAP",
        "replicates": replicates,
        "block_length": block_length,
        "seed": seed,
        "mean_expectancy_r_interval_95": interval(expectancies),
        "win_rate_interval_95": interval(win_rates),
        "profit_factor_interval_95": interval(profit_factors),
        "maximum_drawdown_interval_95": interval(drawdowns),
        "probability_of_loss": losses / replicates,
        "probability_of_phase4_hard_stop": breaches / replicates,
        "probability_of_phase4_drawdown_breach": {
            key: value / replicates for key, value in threshold_breaches.items()
        },
        "probability_of_loss_by_trade_horizon": {
            key: value / replicates for key, value in horizon_losses.items()
        },
    }


def bootstrap_block_sensitivity(
    trades: Sequence[TradeSample],
    *,
    block_lengths: Sequence[int],
    replicates: int,
    seed: int,
) -> Mapping[str, Any]:
    return {
        str(length): moving_block_bootstrap(
            trades, replicates=replicates, block_length=length, seed=seed
        )
        for length in block_lengths
    }


def run_cost_stress(
    trades: Sequence[TradeSample],
    *,
    multipliers: Sequence[float] = (1.0, 1.25, 1.5, 2.0),
    initial_capital: float = 1000.0,
) -> Mapping[str, Any]:
    output = {}
    for multiplier in multipliers:
        if multiplier < 1:
            raise ValidationError("cost stress cannot improve costs")
        account = simulate_account_path(trades, initial_capital=initial_capital, cost_multiplier=multiplier)
        output[f"cost_x_{multiplier:.2f}"] = {
            "ending_equity": account.ending_equity,
            "maximum_drawdown_fraction": account.maximum_drawdown_fraction,
            "hard_stop_breached": account.hard_stop_breached,
            "empirical": multiplier == 1.0,
        }
    return output


def run_preregistered_stress_suite(
    trades: Sequence[TradeSample],
    *,
    initial_capital: float = 1000.0,
) -> Mapping[str, Any]:
    ordered = tuple(trades)
    cost = run_cost_stress(ordered, initial_capital=initial_capital)
    adverse = simulate_account_path(adverse_ordering_stress(ordered), initial_capital=initial_capital)
    missed = simulate_account_path(missed_trade_stress(ordered, every_nth=5), initial_capital=initial_capital)
    gap_subset = tuple(item for index, item in enumerate(ordered) if index % 7 not in {5, 6})
    reduced_liquidity = simulate_account_path(
        tuple(replace_trade_r(item, item.net_r * 0.75) for item in ordered), initial_capital=initial_capital
    )
    return {
        "base_and_cost_multipliers": cost,
        "wider_spread_periods": {"model": "HYPOTHETICAL", "cost_multiplier": 1.5},
        "increased_adverse_slippage": {"model": "HYPOTHETICAL", "cost_multiplier": 2.0},
        "entry_latency": {"model": "HYPOTHETICAL", "delayed_events": 1},
        "missed_trades": {"model": "HYPOTHETICAL", "remaining": len(missed.path) - 1, "ending_equity": missed.ending_equity},
        "data_gaps": {"model": "HYPOTHETICAL", "remaining_trades": len(gap_subset)},
        "consecutive_losing_clusters": {"model": "HYPOTHETICAL", "maximum_drawdown_fraction": adverse.maximum_drawdown_fraction},
        "adverse_trade_ordering": {"model": "HYPOTHETICAL", "ending_equity": adverse.ending_equity},
        "reduced_liquidity": {"model": "HYPOTHETICAL", "ending_equity": reduced_liquidity.ending_equity},
        "minimum_lot_constraints": {"model": "BROKER_METADATA_DEPENDENT", "recalculate_phase4_risk": True},
        "partial_fill_limitations": {"model": "DATASET_DEPENDENT", "invent_partial_fills": False},
        "swap_sensitive_holding": {"model": "BROKER_METADATA_DEPENDENT", "rerun_rollover_ledger": True},
        "starting_equity_sensitivity": {
            str(equity): simulate_account_path(ordered, initial_capital=equity).ending_equity
            for equity in (500.0, 1000.0, 2000.0)
        },
        "broker_metadata_change": {"model": "DATED_METADATA_SEGMENT", "requires_observed_metadata": True},
        "strategy_parameters_changed": False,
    }


def replace_trade_r(trade: TradeSample, net_r: float) -> TradeSample:
    return replace(trade, net_r=net_r)


def adverse_ordering_stress(trades: Sequence[TradeSample]) -> tuple[TradeSample, ...]:
    return tuple(sorted(trades, key=lambda item: (item.net_r, item.trade_id)))


def missed_trade_stress(trades: Sequence[TradeSample], *, every_nth: int) -> tuple[TradeSample, ...]:
    if every_nth < 2:
        raise ValidationError("missed-trade interval must be at least two")
    return tuple(item for index, item in enumerate(trades, start=1) if index % every_nth)


def run_sensitivity(
    base_parameters: Mapping[str, float],
    perturbations: Mapping[str, Sequence[float]],
    evaluator: Callable[[Mapping[str, float]], float],
    *,
    final_holdout_accessed: bool = False,
) -> Mapping[str, Any]:
    if final_holdout_accessed:
        raise ValidationError("sensitivity analysis cannot access the final holdout")
    base_score = finite(evaluator(dict(base_parameters)), "base sensitivity score")
    results: dict[str, Any] = {}
    for name, factors in sorted(perturbations.items()):
        if name not in base_parameters:
            raise ValidationError(f"unknown sensitivity parameter: {name}")
        rows = []
        for factor in factors:
            if not math.isfinite(factor) or factor <= 0:
                raise ValidationError("sensitivity factors must be positive and finite")
            candidate = dict(base_parameters)
            candidate[name] = base_parameters[name] * factor
            score = finite(evaluator(candidate), "sensitivity score")
            collapse = (base_score > 0 >= score) or (
                abs(base_score) > 1e-12 and abs(score - base_score) / abs(base_score) > 0.50
            )
            rows.append({"factor": factor, "value": candidate[name], "score": score, "cliff_edge": collapse})
        results[name] = rows
    return {"base_score": base_score, "parameters": results, "selection_permitted": False}


def regime_stability(trades: Sequence[TradeSample], *, minimum_sample_size: int) -> Mapping[str, Any]:
    if minimum_sample_size < 1:
        raise ValidationError("minimum sample size must be positive")
    slices = _slice_summary(trades, "regime")
    return {
        name: {**values, "claim_permitted": values["trade_count"] >= minimum_sample_size}
        for name, values in slices.items()
    }


@dataclass(frozen=True)
class AcceptancePolicy:
    version: str = "phase8a-acceptance-v1"
    minimum_trades: int = 30
    minimum_profit_factor: float = 1.0
    maximum_equity_drawdown_fraction: float = 0.08
    maximum_best_trade_concentration: float = 0.50
    maximum_modest_cost_collapse_fraction: float = 0.0

    def evaluate(
        self,
        metrics: Mapping[str, Any],
        *,
        ledger_reconciled: bool,
        invariants_passed: bool,
        folds_profitable: Sequence[bool],
        modest_cost_net_pnl: float,
        uncertainty_reported: bool,
        holdout_rules_observed: bool,
    ) -> Mapping[str, Any]:
        checks = {
            "positive_net_expectancy": (metrics.get("expectancy_per_trade") or 0) > 0,
            "net_profit_factor_above_one": (metrics.get("profit_factor_net") or 0) > self.minimum_profit_factor,
            "drawdown_below_phase4_hard_stop": metrics.get("maximum_executable_equity_drawdown_fraction", 1) < self.maximum_equity_drawdown_fraction,
            "ledger_reconciled": ledger_reconciled,
            "causal_and_dataset_invariants": invariants_passed,
            "profit_not_concentrated": (metrics.get("profit_concentration", {}).get("best_trade") or 1) <= self.maximum_best_trade_concentration,
            "modest_cost_stress_survives": modest_cost_net_pnl > self.maximum_modest_cost_collapse_fraction,
            "adequate_sample": metrics.get("trade_count", 0) >= self.minimum_trades,
            "more_than_one_successful_fold": sum(folds_profitable) > 1,
            "uncertainty_reported": uncertainty_reported,
            "holdout_rules_observed": holdout_rules_observed,
        }
        return {"policy_version": self.version, "accepted": all(checks.values()), "checks": checks}
