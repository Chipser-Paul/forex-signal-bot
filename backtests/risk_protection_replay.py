from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bot.execution.risk import (
    AccountSnapshot,
    ClosedTradeOutcome,
    InMemoryRiskAuthority,
    OpenRiskItem,
    RiskStateStore,
    SymbolRiskSpecification,
    initialize_risk_state,
    validation_policy,
)


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _snapshot(source: str, equity: float = 1000.0, *, timestamp: datetime = NOW):
    return AccountSnapshot(
        account_ref="synthetic-account",
        balance=1000.0,
        equity=equity,
        floating_pnl=equity - 1000.0,
        margin=0.0,
        free_margin=equity,
        currency="USD",
        timestamp=timestamp,
        source=source,
    )


def _spec(*, tick_value: float = 1.0) -> SymbolRiskSpecification:
    return SymbolRiskSpecification(
        symbol="XAUUSDm",
        tick_size=0.01,
        tick_value=tick_value,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        price_precision=2,
        contract_size=100.0,
    )


def _normalized_decision(decision) -> dict:
    return {
        "approved": decision.approved,
        "reason": decision.reason.value,
        "equity_basis": decision.equity_basis,
        "budget": decision.monetary_risk_budget,
        "volume": decision.normalized_volume,
        "loss": decision.estimated_normalized_loss,
        "aggregate_before": decision.aggregate_open_risk_before,
        "aggregate_after": decision.aggregate_open_risk_after,
        "circuit": None if decision.circuit_status is None else decision.circuit_status.value,
    }


def _adapter_replay(source: str) -> dict:
    policy = validation_policy({})
    initial = _snapshot(source)
    authority = InMemoryRiskAuthority(
        policy,
        initialize_risk_state(initial, policy, known_strategy_positions=0),
    )

    def decide(*, requested=None, spec=None, open_items=(), now=NOW):
        account = _snapshot(source, timestamp=now)
        return authority.decide(
            snapshot=account,
            specification=spec or _spec(),
            direction="buy",
            entry=100.0,
            stop=99.0,
            open_risk_items=open_items,
            now=now,
            requested_risk_fraction=requested,
        )

    existing = OpenRiskItem(
        trade_id="other-risk",
        symbol="EURUSDm",
        direction="buy",
        remaining_volume=0.1,
        current_reference_price=1.1,
        current_stop=1.0,
        estimated_loss=8.0,
        ownership="strategy",
        calculation_method="synthetic",
        entry_price=1.1,
    )
    scenarios = {
        "normal_approval": _normalized_decision(decide()),
        "oversized_request": _normalized_decision(decide(requested=0.02)),
        "minimum_lot": _normalized_decision(decide(spec=_spec(tick_value=10.0))),
        "aggregate_limit": _normalized_decision(decide(open_items=(existing,))),
    }

    daily = _snapshot(source, 980.0, timestamp=NOW + timedelta(minutes=1))
    authority.refresh(daily, now=daily.timestamp)
    scenarios["floating_daily_drawdown"] = authority.state.circuit_status.value
    for name, equity in (("weekly_drawdown", 960.0), ("total_hard_stop", 920.0)):
        guard = InMemoryRiskAuthority(
            policy,
            initialize_risk_state(initial, policy, known_strategy_positions=0),
        )
        breached = _snapshot(source, equity, timestamp=NOW + timedelta(minutes=1))
        guard.refresh(breached, now=breached.timestamp)
        scenarios[name] = guard.state.circuit_status.value

    loss_authority = InMemoryRiskAuthority(
        policy,
        initialize_risk_state(initial, policy, known_strategy_positions=0),
    )
    for index in range(3):
        loss_authority.consume_outcome(
            ClosedTradeOutcome(
                outcome_id=f"loss-{index}",
                trade_id=f"trade-{index}",
                timestamp=NOW + timedelta(minutes=index + 1),
                gross_realized_pnl=-1.0,
            )
        )
    before_duplicate = loss_authority.state.realized_strategy_pnl
    duplicate_consumed = loss_authority.consume_outcome(
        ClosedTradeOutcome(
            outcome_id="loss-2",
            trade_id="trade-2",
            timestamp=NOW + timedelta(minutes=3),
            gross_realized_pnl=-1.0,
        )
    )
    scenarios["three_losses"] = loss_authority.state.circuit_status.value
    scenarios["duplicate_outcome"] = {
        "consumed": duplicate_consumed,
        "pnl_unchanged": loss_authority.state.realized_strategy_pnl == before_duplicate,
    }
    return scenarios


def _persistence_replay() -> dict:
    policy = validation_policy({})
    initial = _snapshot("persistence_replay")
    state = initialize_risk_state(initial, policy, known_strategy_positions=0)
    with tempfile.TemporaryDirectory(prefix="phase4-risk-replay-") as directory:
        path = Path(directory) / "risk.json"
        store = RiskStateStore(path)
        store.initialize(state)
        reloaded = RiskStateStore(path).load()
        path.write_text("{truncated", encoding="utf-8")
        recovered = RiskStateStore(path).load()
        return {
            "restart": reloaded.status.value,
            "corrupt_primary": recovered.status.value,
            "state_preserved": recovered.state == state,
        }


def run_risk_replay() -> dict:
    live = _adapter_replay("mock_live")
    backtest = _adapter_replay("simulated_backtest")
    return {
        "policy": "phase4-validation-v1",
        "live_mock": live,
        "simulated_backtest": backtest,
        "normalized_match": live == backtest,
        "persistence": _persistence_replay(),
    }


def main() -> None:
    print(json.dumps(run_risk_replay(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
