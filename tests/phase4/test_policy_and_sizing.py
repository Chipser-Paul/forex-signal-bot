from __future__ import annotations

from dataclasses import replace

import pytest

from bot.execution.confluence_scorer import score_setup
from bot.execution.risk import (
    OpenRiskItem,
    RISK_GATE_ORDER,
    RiskError,
    RiskReason,
    assess_trade_risk,
    human_percent_to_fraction,
    normalize_volume_down,
    validation_policy,
)
from tests.phase4.helpers import NOW, policy, snapshot, specification, state


def decide(**overrides):
    values = {
        "policy": policy(),
        "state": state(),
        "snapshot": snapshot(),
        "specification": specification(),
        "direction": "buy",
        "entry": 100.0,
        "stop": 99.0,
        "open_risk_items": (),
        "now": NOW,
    }
    values.update(overrides)
    return assess_trade_risk(**values)


@pytest.mark.parametrize(
    ("human", "fraction"),
    [("0.35", 0.0035), (0.5, 0.005), ("2.00", 0.02)],
)
def test_human_percentage_conversion_is_unambiguous(human, fraction):
    assert human_percent_to_fraction(human, field_name="RISK_PER_TRADE_PCT") == fraction


def test_environment_percentage_cannot_turn_point_35_into_35_percent():
    configured = validation_policy({"RISK_PER_TRADE_PCT": "0.35"})
    assert configured.base_risk_fraction == 0.0035
    with pytest.raises(RiskError, match="base risk"):
        validation_policy({"RISK_PER_TRADE_PCT": "35"})


def test_validation_defaults_are_canonical_fractions():
    configured = policy()
    assert configured.base_risk_fraction == 0.0035
    assert configured.absolute_risk_ceiling == 0.005
    assert configured.aggregate_open_risk_ceiling == 0.01
    assert configured.daily_drawdown_limit == 0.02
    assert configured.weekly_drawdown_limit == 0.04
    assert configured.total_drawdown_limit == 0.08
    assert configured.consecutive_loss_limit == 3
    assert configured.max_strategy_ideas_per_symbol == 1


def test_risk_gate_order_is_explicit_and_stable():
    assert RISK_GATE_ORDER == (
        "policy_configuration",
        "account_identity",
        "fresh_account_snapshot",
        "risk_state_integrity",
        "circuit_status",
        "equity_drawdown",
        "consecutive_losses",
        "same_symbol_idea_limit",
        "aggregate_open_risk",
        "proposed_stop",
        "raw_volume",
        "downward_volume_normalization",
        "post_normalization_risk",
        "final_risk_approval",
        "entry_intent_eligibility",
    )


@pytest.mark.parametrize("requested", [0.015, 0.02])
def test_risk_requests_above_hard_ceiling_are_rejected(requested):
    result = decide(requested_risk_fraction=requested)
    assert result.approved is False
    assert result.reason is RiskReason.RISK_ABOVE_HARD_CEILING
    assert result.diagnostics["ceiling"] == 0.005


def test_one_thousand_account_base_budget_and_downward_size():
    result = decide()
    assert result.approved
    assert result.equity_basis == 1000.0
    assert result.monetary_risk_budget == 3.5
    assert result.raw_volume == pytest.approx(0.35)
    assert result.normalized_volume == 0.35
    assert result.estimated_normalized_loss == pytest.approx(3.5)


def test_one_thousand_account_exact_hard_ceiling_is_five_dollars():
    result = decide(requested_risk_fraction=0.005)
    assert result.approved
    assert result.monetary_risk_budget == pytest.approx(5.0)
    assert result.estimated_normalized_loss <= 5.0


def test_conservative_equity_basis_uses_lower_of_balance_and_equity():
    account = snapshot(equity=900.0, balance=1000.0)
    result = decide(snapshot=account, state=state(account), now=NOW)
    assert result.equity_basis == 900.0
    assert result.monetary_risk_budget == pytest.approx(3.15)


@pytest.mark.parametrize(
    ("step", "raw", "expected"),
    [(0.01, 0.349999999999, 0.34), (0.1, 0.39, 0.3), (0.25, 0.74, 0.5)],
)
def test_volume_normalization_always_moves_down(step, raw, expected):
    normalized = normalize_volume_down(raw, specification(volume_step=step))
    assert normalized == expected
    assert normalized <= raw


def test_minimum_volume_is_rejected_when_its_loss_exceeds_budget():
    result = decide(specification=specification(volume_min=0.5, volume_step=0.1))
    assert result.reason is RiskReason.MINIMUM_VOLUME_EXCEEDS_RISK
    assert result.normalized_volume is None


def test_invalid_and_missing_side_stops_reject():
    assert decide(stop=100.0).reason is RiskReason.INVALID_STOP
    assert decide(stop=101.0).reason is RiskReason.INVALID_STOP
    assert decide(direction="sell", stop=99.0).reason is RiskReason.INVALID_STOP


def test_sell_risk_uses_the_same_budget_and_downward_normalization():
    result = decide(direction="sell", stop=101.0)
    assert result.approved
    assert result.monetary_risk_budget == pytest.approx(3.5)
    assert result.estimated_normalized_loss <= result.monetary_risk_budget


@pytest.mark.parametrize(
    "calculator",
    [lambda *_args: float("nan"), lambda *_args: (_ for _ in ()).throw(RuntimeError("offline"))],
)
def test_invalid_broker_loss_result_fails_closed(calculator):
    result = decide(profit_calculator=calculator)
    assert not result.approved
    assert result.reason is RiskReason.LOSS_CALCULATION_FAILED


def test_approved_values_are_finite_and_within_budget():
    result = decide()
    assert result.normalized_volume <= result.raw_volume
    assert result.estimated_normalized_loss <= result.monetary_risk_budget
    assert result.permitted_risk_fraction <= 0.005


def test_broker_loss_calculation_is_rechecked_after_normalization():
    calls = []

    def calculator(_direction, _symbol, volume, entry, stop):
        calls.append(volume)
        return -abs(entry - stop) * volume * 100.0

    result = decide(profit_calculator=calculator)
    assert result.approved
    assert result.calculation_method == "broker_order_calc_profit"
    assert calls == [1.0, result.normalized_volume]


def test_volume_maximum_is_respected_without_rounding_up():
    result = decide(specification=specification(tick_value=0.001, volume_max=1.0))
    assert result.approved
    assert result.normalized_volume == 1.0
    assert result.normalized_volume <= result.raw_volume


def test_score_grade_has_no_monetary_risk_field_or_authority():
    weak = score_setup({"min_score_to_trade": 8})
    strong = score_setup(
        {
            "htf_bias": "bullish",
            "trade_direction": "bullish",
            "price_in_discount_or_premium": True,
            "valid_ob_present": True,
            "fvg_in_ob_zone": True,
            "liquidity_swept_before_entry": True,
            "session_allowed": True,
            "dxy_confirms_bias": True,
            "no_news_in_30min": True,
            "min_score_to_trade": 8,
        }
    )
    assert weak["grade"] == "SKIP" and strong["grade"] == "A+"
    assert "risk_pct" not in weak and "risk_pct" not in strong
    assert strong["risk_authority"] == "central_phase4_policy"


def open_item(*, trade_id="open", symbol="OTHER", loss=6.5, stop=90.0, ownership="strategy"):
    return OpenRiskItem(
        trade_id=trade_id,
        symbol=symbol,
        direction="buy",
        remaining_volume=0.1,
        current_reference_price=100.0,
        current_stop=stop,
        estimated_loss=loss,
        ownership=ownership,
        calculation_method="test",
    )


def test_aggregate_risk_allows_exact_cap_and_rejects_one_unit_over():
    exact = decide(open_risk_items=(open_item(loss=6.5),))
    over = decide(open_risk_items=(open_item(loss=7.5),))
    assert exact.approved and exact.aggregate_open_risk_after == pytest.approx(10.0)
    assert over.reason is RiskReason.AGGREGATE_RISK_LIMIT


def test_unbounded_manual_or_unknown_position_blocks_new_trade():
    result = decide(open_risk_items=(open_item(stop=None, loss=None, ownership="manual_or_unknown"),))
    assert result.reason is RiskReason.UNBOUNDED_OPEN_RISK


def test_opposing_positions_are_added_not_assumed_to_hedge():
    buy = open_item(trade_id="buy", loss=4.0)
    sell = replace(open_item(trade_id="sell", loss=4.0), direction="sell")
    result = decide(open_risk_items=(buy, sell))
    assert result.reason is RiskReason.AGGREGATE_RISK_LIMIT


def test_existing_same_symbol_idea_blocks_second_idea():
    result = decide(open_risk_items=(open_item(symbol="TEST", loss=1.0),))
    assert result.reason is RiskReason.SYMBOL_IDEA_LIMIT
