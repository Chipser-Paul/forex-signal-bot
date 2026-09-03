from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from bot.execution.broker import (
    BrokerSymbol,
    ExecutionAction,
    ExecutionReason,
    FillingMode,
)
from bot.execution.broker.validation import (
    corrected_absolute_levels,
    normalize_volume_down,
    select_filling_mode,
    stop_improves,
    validate_directional_levels,
    validate_margin,
)
from tests.phase5.helpers import NOW, configure_broker, entry_request, executor, policy


def test_invisible_symbol_is_selected(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    fake_mt5.symbol.visible = False

    original_select = fake_mt5.symbol_select

    def select(symbol, enabled):
        fake_mt5.symbol.visible = True
        return original_select(symbol, enabled)

    fake_mt5.symbol_select = select
    snapshot = engine.snapshot("XAUUSDm", "buy", ExecutionAction.ENTRY)
    assert snapshot.symbol.visible
    assert any(call[0] == "symbol_select" for call in fake_mt5.calls)


@pytest.mark.parametrize(
    ("attribute", "value", "reason"),
    [
        ("trade_mode", 0, ExecutionReason.SYMBOL_TRADE_MODE_REJECTED),
        ("point", 0, ExecutionReason.SYMBOL_METADATA_INVALID),
        ("digits", -1, ExecutionReason.SYMBOL_METADATA_INVALID),
    ],
)
def test_invalid_symbol_metadata_fails_closed(fake_mt5, tmp_path, attribute, value, reason):
    engine = executor(fake_mt5, tmp_path)
    setattr(fake_mt5.symbol, attribute, value)
    result = engine.execute(entry_request(engine))
    assert result.reason is reason
    assert not [call for call in fake_mt5.calls if call[0] == "order_send"]


def test_missing_symbol_and_failed_selection(fake_mt5, tmp_path, monkeypatch):
    engine = executor(fake_mt5, tmp_path)
    monkeypatch.setattr(fake_mt5, "symbol_info", lambda _symbol: None)
    assert engine.execute(entry_request(engine)).reason is ExecutionReason.SYMBOL_MISSING

    engine = executor(fake_mt5, tmp_path / "selection")
    fake_mt5.symbol.visible = False
    monkeypatch.setattr(fake_mt5, "symbol_info", lambda _symbol: fake_mt5.symbol)
    monkeypatch.setattr(fake_mt5, "symbol_select", lambda *_args: False)
    assert engine.execute(entry_request(engine)).reason is ExecutionReason.SYMBOL_SELECTION_FAILED


@pytest.mark.parametrize(
    ("margin", "account_changes", "reason"),
    [
        (101.0, {}, ExecutionReason.NEW_ORDER_MARGIN_LIMIT),
        (20.0, {"margin": 190.0}, ExecutionReason.MARGIN_LEVEL_TOO_LOW),
        (901.0, {"margin_free": 900.0, "equity": 10000.0}, ExecutionReason.FREE_MARGIN_INSUFFICIENT),
        (None, {}, ExecutionReason.MARGIN_CALCULATION_FAILED),
        (-1.0, {}, ExecutionReason.MARGIN_CALCULATION_FAILED),
    ],
)
def test_margin_failures(fake_mt5, tmp_path, margin, account_changes, reason):
    engine = executor(fake_mt5, tmp_path)
    for key, value in account_changes.items():
        setattr(fake_mt5.account, key, value)
    fake_mt5.order_calc_margin_response = margin
    result = engine.execute(entry_request(engine))
    assert result.reason is reason
    assert not [call for call in fake_mt5.calls if call[0] == "order_send"]


def test_valid_margin_reports_conservative_projection(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    snapshot = engine.snapshot("XAUUSDm", "buy", ExecutionAction.ENTRY)
    required, free, level = validate_margin(
        required_margin=20.0,
        snapshot=snapshot,
        policy=engine.policy,
    )
    assert (required, free) == (20.0, 880.0)
    assert level > 500.0


@pytest.mark.parametrize(
    ("flags", "execution_mode", "expected"),
    [
        (1, 2, FillingMode.FOK),
        (2, 2, FillingMode.IOC),
        (3, 2, FillingMode.FOK),
        (0, 3, FillingMode.RETURN),
    ],
)
def test_dynamic_filling_selection(fake_mt5, tmp_path, flags, execution_mode, expected):
    engine = executor(fake_mt5, tmp_path)
    fake_mt5.symbol.filling_mode = flags
    fake_mt5.symbol.trade_exemode = execution_mode
    snapshot = engine.snapshot("XAUUSDm", "buy", ExecutionAction.ENTRY)
    assert select_filling_mode(fake_mt5, snapshot.symbol, engine.policy) is expected


def test_market_execution_without_fok_or_ioc_is_rejected(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    fake_mt5.symbol.filling_mode = 0
    result = engine.execute(entry_request(engine))
    assert result.reason is ExecutionReason.FILLING_MODE_UNSUPPORTED


@pytest.mark.parametrize(
    ("direction", "entry", "stop", "target"),
    [("buy", 100.01, 99.0, 102.0), ("sell", 100.0, 101.0, 98.0)],
)
def test_valid_absolute_stops_and_targets(fake_mt5, tmp_path, direction, entry, stop, target):
    engine = executor(fake_mt5, tmp_path)
    snapshot = engine.snapshot("XAUUSDm", direction, ExecutionAction.ENTRY)
    assert validate_directional_levels(
        direction,
        entry,
        stop,
        target,
        snapshot.symbol,
        snapshot.tick,
    ) == (stop, target)


@pytest.mark.parametrize(
    ("direction", "stop", "target", "reason"),
    [
        ("buy", 101.0, 102.0, ExecutionReason.STOP_INVALID),
        ("buy", 99.0, 99.5, ExecutionReason.TARGET_INVALID),
        ("sell", 99.0, 98.0, ExecutionReason.STOP_INVALID),
        ("sell", 101.0, 101.5, ExecutionReason.TARGET_INVALID),
    ],
)
def test_wrong_side_levels_are_rejected(fake_mt5, tmp_path, direction, stop, target, reason):
    engine = executor(fake_mt5, tmp_path)
    snapshot = engine.snapshot("XAUUSDm", direction, ExecutionAction.ENTRY)
    with pytest.raises(Exception) as captured:
        validate_directional_levels(
            direction,
            100.0,
            stop,
            target,
            snapshot.symbol,
            snapshot.tick,
        )
    assert captured.value.reason is reason


def test_stop_and_freeze_distance_are_enforced(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    fake_mt5.symbol.trade_stops_level = 20
    snapshot = engine.snapshot("XAUUSDm", "buy", ExecutionAction.ENTRY)
    with pytest.raises(Exception) as captured:
        validate_directional_levels(
            "buy", 100.01, 99.9, 102.0, snapshot.symbol, snapshot.tick
        )
    assert captured.value.reason is ExecutionReason.STOP_DISTANCE_VIOLATION

    fake_mt5.symbol.trade_stops_level = 0
    fake_mt5.symbol.trade_freeze_level = 20
    snapshot = engine.snapshot("XAUUSDm", "buy", ExecutionAction.MODIFY_STOP)
    with pytest.raises(Exception) as captured:
        validate_directional_levels(
            "buy", 100.01, 99.9, 102.0, snapshot.symbol, snapshot.tick, modification=True
        )
    assert captured.value.reason is ExecutionReason.FREEZE_LEVEL_VIOLATION


def test_invalid_stop_correction_returns_absolute_prices(fake_mt5, tmp_path):
    engine = executor(fake_mt5, tmp_path)
    request = entry_request(engine)
    snapshot = engine.snapshot("XAUUSDm", "buy", ExecutionAction.ENTRY)
    stop, target = corrected_absolute_levels(request, snapshot.symbol, snapshot.tick)
    assert stop == 99.9
    assert target == 102.0
    assert stop != snapshot.symbol.stops_level_points * snapshot.symbol.point


@pytest.mark.parametrize("volume", [0.199999999999, 0.24, 0.26])
def test_volume_normalization_never_increases(fake_mt5, tmp_path, volume):
    engine = executor(fake_mt5, tmp_path)
    fake_mt5.symbol.volume_step = 0.05
    snapshot = engine.snapshot("XAUUSDm", "buy", ExecutionAction.ENTRY)
    assert normalize_volume_down(volume, snapshot.symbol) <= volume


def test_stop_protection_improvement_is_directional():
    assert stop_improves("buy", 99.0, 99.5)
    assert not stop_improves("buy", 99.5, 99.0)
    assert stop_improves("sell", 101.0, 100.5)
    assert not stop_improves("sell", 100.5, 101.0)
