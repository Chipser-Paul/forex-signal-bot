from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from bot.execution.risk import RiskReason, RiskStateStore, account_identity_ref
from tests.phase4.helpers import NOW


def configure_account(fake_mt5, *, equity=1000.0, balance=1000.0):
    fake_mt5.account = SimpleNamespace(
        login=12345678,
        server="Phase4-Test",
        balance=balance,
        equity=equity,
        profit=equity - balance,
        margin=0.0,
        margin_free=equity,
        currency="USD",
    )
    fake_mt5.order_calc_profit_response = (
        lambda _order_type, _symbol, volume, entry, close: -abs(entry - close)
        * volume
        * 100.0
    )


@pytest.mark.unit
def test_live_risk_uses_account_equity_and_ignores_dashboard_capital(
    fake_mt5,
    monkeypatch,
    tmp_path,
):
    import main

    configure_account(fake_mt5)
    monkeypatch.setattr(main, "RISK_STATE_DIR", tmp_path)
    monkeypatch.setattr(main, "CAPITAL", 1_000_000.0)
    monkeypatch.setenv("RISK_STATE_INITIALIZE", "1")

    decision = main._approve_live_risk(
        "XAUUSDm",
        "buy",
        100.0,
        99.0,
        {},
        now=NOW,
    )

    assert decision.approved
    assert decision.equity_basis == 1000.0
    assert decision.monetary_risk_budget == pytest.approx(3.5)
    assert decision.normalized_volume == 0.03
    assert all(name != "order_send" for name, _args, _kwargs in fake_mt5.calls)


@pytest.mark.unit
def test_live_risk_missing_state_fails_closed(fake_mt5, monkeypatch, tmp_path):
    import main

    configure_account(fake_mt5)
    monkeypatch.setattr(main, "RISK_STATE_DIR", tmp_path)
    monkeypatch.delenv("RISK_STATE_INITIALIZE", raising=False)

    decision = main._approve_live_risk(
        "XAUUSDm",
        "buy",
        100.0,
        99.0,
        {},
        now=NOW,
    )

    assert not decision.approved
    assert decision.reason is RiskReason.RISK_STATE_UNINITIALIZED


@pytest.mark.parametrize(
    ("account", "environment", "reason"),
    [
        (None, {}, RiskReason.ACCOUNT_DATA_MISSING),
        (
            SimpleNamespace(
                login=12345678,
                server="Phase4-Test",
                balance=1000.0,
                equity=0.0,
                profit=-1000.0,
                margin=0.0,
                margin_free=0.0,
                currency="USD",
            ),
            {},
            RiskReason.INVALID_EQUITY,
        ),
        (None, {"RISK_PER_TRADE_PCT": "2"}, RiskReason.INVALID_POLICY),
    ],
)
def test_live_risk_boundary_failures_return_stable_reason_codes(
    fake_mt5,
    monkeypatch,
    tmp_path,
    account,
    environment,
    reason,
):
    import main

    fake_mt5.account = account
    monkeypatch.setattr(main, "RISK_STATE_DIR", tmp_path)
    monkeypatch.delenv("RISK_PER_TRADE_PCT", raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    decision = main._approve_live_risk(
        "XAUUSDm", "buy", 100.0, 99.0, {}, now=NOW
    )
    assert not decision.approved
    assert decision.reason is reason


@pytest.mark.unit
def test_live_unknown_position_without_stop_blocks_new_entry(
    fake_mt5,
    monkeypatch,
    tmp_path,
):
    import main

    configure_account(fake_mt5)
    monkeypatch.setattr(main, "RISK_STATE_DIR", tmp_path)
    monkeypatch.setenv("RISK_STATE_INITIALIZE", "1")
    first = main._approve_live_risk(
        "XAUUSDm", "buy", 100.0, 99.0, {}, now=NOW
    )
    assert first.approved

    monkeypatch.delenv("RISK_STATE_INITIALIZE")
    fake_mt5.positions = [
        SimpleNamespace(
            ticket=91,
            symbol="EURUSDm",
            type=fake_mt5.ORDER_TYPE_BUY,
            volume=0.1,
            sl=0.0,
        )
    ]
    blocked = main._approve_live_risk(
        "XAUUSDm", "buy", 100.0, 99.0, {}, now=NOW + timedelta(seconds=1)
    )

    assert not blocked.approved
    assert blocked.reason is RiskReason.UNBOUNDED_OPEN_RISK


@pytest.mark.unit
def test_live_completed_outcome_is_consumed_once_across_store_reload(
    fake_mt5,
    monkeypatch,
    tmp_path,
):
    import main

    configure_account(fake_mt5)
    monkeypatch.setattr(main, "RISK_STATE_DIR", tmp_path)
    monkeypatch.setenv("RISK_STATE_INITIALIZE", "1")
    assert main._approve_live_risk(
        "XAUUSDm", "buy", 100.0, 99.0, {}, now=NOW
    ).approved
    monkeypatch.delenv("RISK_STATE_INITIALIZE")

    closed = SimpleNamespace(
        trade_id="trade-live-1",
        exit_time=NOW + timedelta(minutes=1),
        realized_gross_pnl=-3.0,
    )
    first = main._consume_live_risk_outcome(closed, now=closed.exit_time)
    second = main._consume_live_risk_outcome(closed, now=closed.exit_time)

    ref = account_identity_ref(fake_mt5.account.login, fake_mt5.account.server)
    loaded = RiskStateStore(tmp_path / f"{ref}.json").load().state
    assert first is True and second is False
    assert loaded is not None
    assert loaded.consecutive_losses == 1
    assert len(loaded.processed_outcome_ids) == 1
