from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.execution.broker import (
    ExecutionReason,
    ExecutionStatus,
    FillingMode,
    ResultClass,
)
from bot.execution.broker.adapter import classify_retcode
from tests.phase5.helpers import entry_request, executor


def calls(fake_mt5, name):
    return [call for call in fake_mt5.calls if call[0] == name]


def test_success_requires_preflight_before_send(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    request = entry_request(engine)
    result = engine.execute(request, risk_recheck=lambda _entry, _stop, volume: volume)
    names = [name for name, _args, _kwargs in fake_mt5.calls]
    assert result.status is ExecutionStatus.CONFIRMED
    assert result.reason is ExecutionReason.CONFIRMED
    assert names.index("order_check") < names.index("order_send")
    assert result.filling_mode is FillingMode.FOK
    assert result.executed_volume == 0.1


@pytest.mark.parametrize("response", [None, SimpleNamespace(comment="missing retcode")])
def test_missing_preflight_blocks_send(fake_mt5, tmp_path, response):
    engine = executor(fake_mt5, tmp_path)
    fake_mt5.order_check_response = response
    result = engine.execute(entry_request(engine))
    assert result.reason is ExecutionReason.PREFLIGHT_MISSING
    assert calls(fake_mt5, "order_send") == []


def test_preflight_cannot_increase_volume(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    fake_mt5.order_check_response = SimpleNamespace(retcode=0, volume=0.2)
    result = engine.execute(entry_request(engine))
    assert result.reason is ExecutionReason.PREFLIGHT_VOLUME_INCREASE
    assert calls(fake_mt5, "order_send") == []


@pytest.mark.parametrize(
    ("retcode_name", "category", "reason", "retryable"),
    [
        ("TRADE_RETCODE_DONE", ResultClass.SUCCESS, ExecutionReason.CONFIRMED, False),
        ("TRADE_RETCODE_DONE_PARTIAL", ResultClass.PARTIAL_SUCCESS, ExecutionReason.PARTIAL_FILL, False),
        ("TRADE_RETCODE_INVALID_STOPS", ResultClass.INVALID_STOPS, ExecutionReason.BROKER_INVALID_STOPS, True),
        ("TRADE_RETCODE_REQUOTE", ResultClass.PRICE_CHANGED, ExecutionReason.BROKER_PRICE_CHANGED, True),
        ("TRADE_RETCODE_NO_MONEY", ResultClass.INSUFFICIENT_MARGIN, ExecutionReason.BROKER_INSUFFICIENT_MARGIN, False),
        ("TRADE_RETCODE_MARKET_CLOSED", ResultClass.TRADING_UNAVAILABLE, ExecutionReason.BROKER_TRADING_UNAVAILABLE, False),
        ("TRADE_RETCODE_INVALID_VOLUME", ResultClass.INVALID_REQUEST, ExecutionReason.BROKER_INVALID_REQUEST, False),
        ("TRADE_RETCODE_TIMEOUT", ResultClass.UNCERTAIN, ExecutionReason.BROKER_OUTCOME_UNCERTAIN, False),
    ],
)
def test_retcode_classification(fake_mt5, retcode_name, category, reason, retryable):
    assert classify_retcode(fake_mt5, getattr(fake_mt5, retcode_name)) == (
        category,
        reason,
        retryable,
    )


def test_partial_fill_uses_actual_volume_and_does_not_retry_remainder(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    fake_mt5.order_response = SimpleNamespace(
        retcode=fake_mt5.TRADE_RETCODE_DONE_PARTIAL,
        order=101,
        deal=201,
        position=301,
        volume=0.04,
        price=100.01,
    )
    result = engine.execute(entry_request(engine))
    assert result.status is ExecutionStatus.PARTIALLY_FILLED
    assert result.executed_volume == 0.04
    assert result.remaining_unfilled_volume == pytest.approx(0.06)
    assert result.reconciliation_required
    assert len(calls(fake_mt5, "order_send")) == 1


def test_invalid_stop_retry_uses_absolute_prices_and_lower_volume(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    responses = iter(
        [
            SimpleNamespace(retcode=fake_mt5.TRADE_RETCODE_INVALID_STOPS, volume=0.0),
            SimpleNamespace(
                retcode=fake_mt5.TRADE_RETCODE_DONE,
                order=102,
                deal=202,
                position=302,
                volume=0.05,
                price=100.01,
            ),
        ]
    )
    fake_mt5.order_response = lambda _request: next(responses)
    fake_mt5.order_check_response = lambda request: SimpleNamespace(
        retcode=0,
        volume=request.get("volume", 0.0),
    )
    result = engine.execute(
        entry_request(engine),
        risk_recheck=lambda _entry, stop, _volume: 0.05 if stop == 99.9 else None,
    )
    sends = calls(fake_mt5, "order_send")
    assert result.status is ExecutionStatus.CONFIRMED
    assert result.executed_volume == 0.05
    assert len(sends) == 2
    retry_request = sends[1][1][0]
    assert retry_request["sl"] == 99.9
    assert retry_request["sl"] != 0.1
    assert retry_request["volume"] == 0.05


def test_invalid_stop_retry_below_minimum_is_rejected(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    fake_mt5.order_response = SimpleNamespace(
        retcode=fake_mt5.TRADE_RETCODE_INVALID_STOPS,
        volume=0.0,
    )
    result = engine.execute(
        entry_request(engine),
        risk_recheck=lambda _entry, _stop, _volume: 0.001,
    )
    assert result.status is ExecutionStatus.REJECTED
    assert result.reason is ExecutionReason.VOLUME_INVALID
    assert len(calls(fake_mt5, "order_send")) == 1


def test_second_invalid_stop_rejection_ends_retry(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    fake_mt5.order_response = SimpleNamespace(
        retcode=fake_mt5.TRADE_RETCODE_INVALID_STOPS,
        volume=0.0,
    )
    fake_mt5.order_check_response = lambda request: SimpleNamespace(
        retcode=0,
        volume=request.get("volume", 0.0),
    )
    result = engine.execute(
        entry_request(engine),
        risk_recheck=lambda _entry, _stop, volume: volume,
    )
    assert result.reason is ExecutionReason.BROKER_INVALID_STOPS
    assert not result.retry_eligible
    assert len(calls(fake_mt5, "order_send")) == 2


def test_requote_permits_one_fully_checked_retry(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    responses = iter(
        [
            SimpleNamespace(retcode=fake_mt5.TRADE_RETCODE_REQUOTE, volume=0.0),
            SimpleNamespace(
                retcode=fake_mt5.TRADE_RETCODE_DONE,
                order=102,
                deal=202,
                position=302,
                volume=0.1,
                price=100.01,
            ),
        ]
    )
    fake_mt5.order_response = lambda _request: next(responses)
    result = engine.execute(
        entry_request(engine),
        risk_recheck=lambda _entry, _stop, volume: volume,
    )
    assert result.status is ExecutionStatus.CONFIRMED
    assert len(calls(fake_mt5, "order_send")) == 2
    assert len(calls(fake_mt5, "order_check")) == 4


def test_timeout_is_uncertain_and_never_blindly_retried(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    fake_mt5.order_response = None
    request = entry_request(engine)
    first = engine.execute(request, risk_recheck=lambda _entry, _stop, volume: volume)
    second = engine.execute(request, risk_recheck=lambda _entry, _stop, volume: volume)
    assert first.status is ExecutionStatus.UNCERTAIN
    assert first.reconciliation_required
    assert second.reason is ExecutionReason.ACTION_UNCERTAIN
    assert len(calls(fake_mt5, "order_send")) == 1


def test_confirmed_action_cannot_be_sent_again(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    request = entry_request(engine)
    first = engine.execute(request, risk_recheck=lambda _entry, _stop, volume: volume)
    second = engine.execute(request, risk_recheck=lambda _entry, _stop, volume: volume)
    assert first.status is ExecutionStatus.CONFIRMED
    assert second.reason is ExecutionReason.DUPLICATE_ACTION
    assert len(calls(fake_mt5, "order_send")) == 1


def test_spread_widening_before_send_is_rejected(fake_mt5, tmp_path, monkeypatch):
    engine = executor(fake_mt5, tmp_path)
    narrow = fake_mt5.tick
    wide = SimpleNamespace(
        bid=100.0,
        ask=100.5,
        time=narrow.time,
        time_msc=narrow.time_msc,
    )
    ticks = iter([narrow, wide])

    def next_tick(_symbol):
        fake_mt5._record("symbol_info_tick", _symbol)
        return next(ticks)

    monkeypatch.setattr(fake_mt5, "symbol_info_tick", next_tick)
    result = engine.execute(entry_request(engine))
    assert result.reason is ExecutionReason.SPREAD_ABSOLUTE_LIMIT
    assert calls(fake_mt5, "order_send") == []
