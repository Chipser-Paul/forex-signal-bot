from __future__ import annotations

from dataclasses import replace

import pytest

from bot.validation.analytics import (
    AcceptancePolicy,
    adverse_ordering_stress,
    bootstrap_block_sensitivity,
    calculate_metrics,
    missed_trade_stress,
    moving_block_bootstrap,
    regime_stability,
    run_cost_stress,
    run_preregistered_stress_suite,
    run_sensitivity,
    simulate_account_path,
    three_month_outcomes,
)
from bot.validation.models import ValidationError
from bot.validation.synthetic import synthetic_trades


def test_metrics_cover_required_slices_and_concentration():
    trades = synthetic_trades(24)
    metrics = calculate_metrics(trades, initial_capital=1000.0)
    assert metrics["trade_count"] == 24
    assert metrics["gross_pnl"] != metrics["net_pnl"]
    assert metrics["cost_total"] == pytest.approx(6.0)
    assert set(metrics["long_short"]) == {"LONG", "SHORT"}
    assert set(metrics["by_regime"]) == {"RANGING", "TRENDING_DOWN", "TRENDING_UP"}
    assert metrics["profit_concentration"]["best_trade"] is not None


def test_metrics_report_rejections_circuits_and_three_month_distribution():
    trades = synthetic_trades(24)
    metrics = calculate_metrics(
        trades,
        initial_capital=1000.0,
        rejections=(
            {"reason_code": "MINIMUM_VOLUME_EXCEEDS_RISK"},
            {"reason_code": "INSUFFICIENT_MARGIN"},
        ),
        circuit_events=("DAILY_PAUSED", "DAILY_PAUSED"),
    )
    assert metrics["minimum_lot_rejections"] == 1
    assert metrics["insufficient_margin_rejections"] == 1
    assert metrics["risk_circuit_activations"] == {"DAILY_PAUSED": 2}
    windows = three_month_outcomes(
        trades, start=trades[0].opened_at, end=trades[-1].closed_at
    )
    assert len(windows["windows"]) == 1
    assert windows["target_fitted"] is False


def test_no_trade_and_profit_factor_boundaries_are_explicit():
    empty = calculate_metrics((), initial_capital=1000.0)
    assert empty["status"] == "NO_TRADES"
    assert empty["win_rate"] is None
    winners = tuple(replace(item, net_pnl=1.0, gross_pnl=1.25, net_r=1.0) for item in synthetic_trades(3))
    winner_metrics = calculate_metrics(winners, initial_capital=1000.0)
    assert winner_metrics["profit_factor_net"] is None
    assert winner_metrics["profit_factor_net_boundary"] == "NO_LOSING_TRADES"
    losers = tuple(replace(item, net_pnl=-1.0, gross_pnl=-0.75, net_r=-1.0) for item in synthetic_trades(3))
    loser_metrics = calculate_metrics(losers, initial_capital=1000.0)
    assert loser_metrics["win_rate"] == 0.0
    assert loser_metrics["profit_factor_net"] == 0.0


def test_one_thousand_account_path_resizes_each_trade_and_tracks_drawdown():
    trades = synthetic_trades(2)
    result = simulate_account_path(trades, initial_capital=1000.0)
    expected_first = 1000.0 + 1000.0 * 0.0035 * trades[0].net_r
    expected_second = expected_first + expected_first * 0.0035 * trades[1].net_r
    assert result.path[1] == pytest.approx(expected_first)
    assert result.ending_equity == pytest.approx(expected_second)
    assert len(result.path) == 3


def test_path_dependent_hard_stop_probability_uses_phase4_limit():
    catastrophic = tuple(replace(item, net_r=-30.0) for item in synthetic_trades(4))
    account = simulate_account_path(catastrophic)
    assert account.hard_stop_breached
    assert len(account.path) == 2
    bootstrap = moving_block_bootstrap(catastrophic, replicates=20, block_length=2, seed=7)
    assert bootstrap["probability_of_phase4_hard_stop"] == 1.0


def test_path_reconstructs_daily_weekly_and_loss_streak_circuits():
    base = synthetic_trades(4)
    same_day = tuple(replace(item, opened_at=base[0].opened_at, closed_at=base[0].closed_at, net_r=-2.0) for item in base)
    account = simulate_account_path(same_day)
    assert account.daily_pause_activated
    assert account.skipped_trades > 0

    three_losses = tuple(replace(item, net_r=-1.0) for item in synthetic_trades(4))
    streak = simulate_account_path(three_losses)
    assert streak.loss_streak_pause_activated
    assert streak.processed_trades == 3


def test_moving_block_bootstrap_is_deterministic_and_reports_uncertainty():
    trades = synthetic_trades(24)
    first = moving_block_bootstrap(trades, replicates=100, block_length=4, seed=8001)
    second = moving_block_bootstrap(trades, replicates=100, block_length=4, seed=8001)
    assert first == second
    assert first["method"] == "MOVING_BLOCK_BOOTSTRAP"
    assert len(first["mean_expectancy_r_interval_95"]) == 2
    assert len(first["win_rate_interval_95"]) == 2
    assert len(first["maximum_drawdown_interval_95"]) == 2


def test_bootstrap_block_length_sensitivity_is_visible():
    results = bootstrap_block_sensitivity(
        synthetic_trades(24), block_lengths=(2, 4, 6), replicates=25, seed=9
    )
    assert set(results) == {"2", "4", "6"}
    assert all(item["replicates"] == 25 for item in results.values())


def test_cost_stress_is_monotonic_and_labeled_empirical_vs_hypothetical():
    results = run_cost_stress(synthetic_trades(24))
    equities = [results[key]["ending_equity"] for key in ("cost_x_1.00", "cost_x_1.25", "cost_x_1.50", "cost_x_2.00")]
    assert equities == sorted(equities, reverse=True)
    assert results["cost_x_1.00"]["empirical"] is True
    assert results["cost_x_1.25"]["empirical"] is False


def test_complete_preregistered_stress_matrix_is_reported():
    report = run_preregistered_stress_suite(synthetic_trades(24))
    expected = {
        "base_and_cost_multipliers", "wider_spread_periods", "increased_adverse_slippage",
        "entry_latency", "missed_trades", "data_gaps", "consecutive_losing_clusters",
        "adverse_trade_ordering", "reduced_liquidity", "minimum_lot_constraints",
        "partial_fill_limitations", "swap_sensitive_holding", "starting_equity_sensitivity",
        "broker_metadata_change", "strategy_parameters_changed",
    }
    assert set(report) == expected
    assert report["strategy_parameters_changed"] is False


def test_missed_trade_and_adverse_ordering_stresses_do_not_change_signals():
    trades = synthetic_trades(12)
    missed = missed_trade_stress(trades, every_nth=3)
    adverse = adverse_ordering_stress(trades)
    assert len(missed) == 8
    assert {item.trade_id for item in missed} < {item.trade_id for item in trades}
    assert [item.net_r for item in adverse] == sorted(item.net_r for item in trades)


def test_sensitivity_reports_cliffs_but_never_selects_candidate():
    report = run_sensitivity(
        {"threshold": 1.0},
        {"threshold": (0.9, 0.95, 1.05, 1.1)},
        lambda values: 1.0 if values["threshold"] <= 1.0 else -1.0,
    )
    assert report["selection_permitted"] is False
    assert any(row["cliff_edge"] for row in report["parameters"]["threshold"])
    with pytest.raises(ValidationError, match="final holdout"):
        run_sensitivity({"x": 1.0}, {"x": (0.9,)}, lambda _: 1.0, final_holdout_accessed=True)


def test_regime_analysis_reports_sample_size_with_each_slice():
    results = regime_stability(synthetic_trades(12), minimum_sample_size=5)
    assert all(item["trade_count"] == 4 for item in results.values())
    assert not any(item["claim_permitted"] for item in results.values())


def test_acceptance_policy_cannot_be_overridden_by_ambitious_targets():
    trades = synthetic_trades(36)
    metrics = calculate_metrics(trades, initial_capital=1000.0)
    policy = AcceptancePolicy(minimum_trades=30)
    result = policy.evaluate(
        metrics,
        ledger_reconciled=True,
        invariants_passed=True,
        folds_profitable=(True, True, False, True),
        modest_cost_net_pnl=1.0,
        uncertainty_reported=True,
        holdout_rules_observed=True,
    )
    assert "win_rate_60" not in result["checks"]
    assert "ending_balance_1800" not in result["checks"]
    assert result["policy_version"] == "phase8a-acceptance-v1"


def test_invalid_bootstrap_and_account_parameters_fail_closed():
    with pytest.raises(ValidationError):
        moving_block_bootstrap(synthetic_trades(3), replicates=0, block_length=1, seed=1)
    with pytest.raises(ValidationError):
        simulate_account_path(synthetic_trades(1), risk_fraction=0.02)
