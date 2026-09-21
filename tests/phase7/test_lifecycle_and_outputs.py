from __future__ import annotations

import json
from datetime import timedelta

import pytest

from bot.backtesting import (
    BidAskBar,
    CostSource,
    FidelityClass,
    HistoricalExecutionEngine,
    HistoricalExecutionError,
    RunDescriptor,
    RunMode,
    Side,
    SlippageKind,
    classify_phase1_legacy_inventory,
    normalized_bundle_hash,
    write_result_bundle,
)
from bot.backtesting.adapters import manage_quote_position, process_bar_entry, process_quote_entry
from bot.execution.lifecycle.entry import create_entry_state, new_entry_intent
from bot.execution.lifecycle.models import Direction, LifecycleStatus, ManagementConfig, ReadinessStyle
from tests.phase7.helpers import T0, metadata, policy, quote


def intent(direction: Direction = Direction.BUY):
    if direction is Direction.BUY:
        trigger, stop, target = 100.0, 99.0, 102.0
    else:
        trigger, stop, target = 100.0, 101.0, 98.0
    return new_entry_intent(
        symbol="XAUUSDm",
        direction=direction,
        source_timeframe="M5",
        source_candle_open_time=T0 - timedelta(minutes=5),
        signal_available_at=T0,
        requested_trigger=trigger,
        stop_loss=stop,
        final_target=target,
        readiness_style=ReadinessStyle.IMMEDIATE,
        source_event_id="source-candle",
        source_sequence=0,
        configuration_id="phase7-test",
    )


def descriptor() -> RunDescriptor:
    return RunDescriptor(
        git_commit="abc123",
        git_dirty=False,
        strategy_version="phase6-strategy-v1",
        configuration={"symbol": "XAUUSDm", "risk_fraction": 0.0035},
        dataset_manifest={
            "dataset_id": "fixture",
            "provenance": "synthetic",
            "hashes": {"quotes": "deadbeef"},
            "spread_source": "OBSERVED",
        },
        start_timestamp=T0.isoformat(),
        end_timestamp=(T0 + timedelta(minutes=5)).isoformat(),
        initial_capital=1000,
        timeframes=("TICK", "M5"),
    )


@pytest.mark.unit
def test_phase3_entry_uses_actual_phase7_fill_and_identity():
    engine = HistoricalExecutionEngine(
        run_id="adapter",
        metadata=metadata(),
        policy=policy(slippage_points=1),
        initial_balance=1000,
    )
    decision, position = process_quote_entry(
        engine,
        create_entry_state(intent()),
        quote(1, 99.9, 100),
        sequence=1,
        quantity=0.1,
    )
    assert decision.triggered
    assert position is not None
    assert position.fill_kind.value == "SIMULATED_TRIGGER"
    assert position.fill_price == 100.01
    assert position.adapter_metadata["fidelity"] == "TICK_BID_ASK"


@pytest.mark.unit
def test_phase3_source_barrier_remains_authoritative():
    engine = HistoricalExecutionEngine(
        run_id="barrier", metadata=metadata(), policy=policy(), initial_balance=1000
    )
    item = intent()
    source_quote = quote(0, 99.9, 100, sequence="source")
    decision, position = process_quote_entry(
        engine,
        create_entry_state(item),
        source_quote,
        sequence=0,
        quantity=0.1,
    )
    assert not decision.triggered
    assert position is None
    assert engine.fills == []


@pytest.mark.unit
def test_phase3_partial_and_final_actions_use_phase7_costed_fills():
    engine = HistoricalExecutionEngine(
        run_id="manage", metadata=metadata(), policy=policy(), initial_balance=1000
    )
    _, position = process_quote_entry(
        engine,
        create_entry_state(intent()),
        quote(1, 99.9, 100),
        sequence=1,
        quantity=0.1,
    )
    assert position is not None
    config = ManagementConfig(
        partial_close_fraction=0.5,
        partial_target_r=1,
        volume_min=0.01,
        volume_step=0.01,
        pnl_per_price_unit=100,
        trailing_enabled=False,
    )
    position = manage_quote_position(
        engine, position, quote(2, 101, 101.1), sequence=2, config=config
    )
    assert position.status is LifecycleStatus.PARTIALLY_CLOSED
    assert position.remaining_quantity == pytest.approx(0.05)
    position = manage_quote_position(
        engine, position, quote(3, 102, 102.1), sequence=3, config=config
    )
    assert position.status is LifecycleStatus.CLOSED
    assert engine.reconcile()["difference"] == pytest.approx(0)
    assert engine.account.commission == pytest.approx(0.5)


@pytest.mark.unit
def test_bid_ask_bar_entry_uses_later_ask_open_for_long_gap():
    engine = HistoricalExecutionEngine(
        run_id="bar-entry",
        metadata=metadata(),
        policy=policy(fidelity=FidelityClass.BAR_BID_ASK),
        initial_balance=1000,
    )
    bar = BidAskBar(
        symbol="XAUUSDm",
        open_time=T0,
        available_at=T0 + timedelta(minutes=5),
        bid_open=99.75,
        bid_high=100.25,
        bid_low=99.55,
        bid_close=100.05,
        ask_open=99.8,
        ask_high=100.3,
        ask_low=99.6,
        ask_close=100.1,
        source="bid-ask-bars",
        dataset_id="bars",
        sequence_id="next-bar",
    )
    decision, position = process_bar_entry(
        engine, create_entry_state(intent()), bar, sequence=1, quantity=0.1
    )
    assert decision.triggered
    assert position is not None
    assert position.fill_price == 99.8
    assert position.adapter_metadata["intrabar_path"] == "unknown_conservative"


@pytest.mark.unit
def test_result_bundle_contains_all_required_files_and_labels(tmp_path):
    engine = HistoricalExecutionEngine(
        run_id="bundle", metadata=metadata(), policy=policy(), initial_balance=1000
    )
    engine.open_market(
        action_id="entry", trade_id="trade", direction=Side.BUY,
        requested_volume=0.1, stop_price=99, target_price=102,
        quote=quote(1, 99.9, 100), signal_available_at=T0,
        source_event_id="signal", market_event_id="quote",
    )
    result = write_result_bundle(tmp_path / "results", engine, descriptor())
    assert {path.name for path in result.iterdir()} == {
        "run_manifest.json", "configuration.json", "dataset_manifest.json",
        "fills.jsonl", "ledger.jsonl", "trades.jsonl", "equity.csv",
        "rejections.jsonl", "summary.json",
    }
    summary = json.loads((result / "summary.json").read_text(encoding="utf-8"))
    assert summary["result_label"] == "DIAGNOSTIC \u2014 NOT VALIDATED"
    assert summary["profitability_evidence"] is False
    manifest = json.loads((result / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["cost_sources"] == {
        "commission": "OBSERVED",
        "slippage": "NOT_AVAILABLE",
        "spread": "OBSERVED",
        "swap": "OBSERVED",
    }


@pytest.mark.unit
def test_closed_trade_output_reconciles_gross_and_costs(tmp_path):
    engine = HistoricalExecutionEngine(
        run_id="closed-bundle", metadata=metadata(), policy=policy(), initial_balance=1000
    )
    position, _ = engine.open_market(
        action_id="entry", trade_id="trade", direction=Side.BUY,
        requested_volume=0.1, stop_price=99, target_price=102,
        quote=quote(1, 99.9, 100), signal_available_at=T0,
        source_event_id="signal", market_event_id="quote",
    )
    engine.close_market(
        action_id="exit", position_id=position.position_id,
        quote=quote(2, 101.9, 102), reason_code="EXIT",
    )
    result = write_result_bundle(tmp_path, engine, descriptor())
    trade = json.loads((result / "trades.jsonl").read_text(encoding="utf-8").strip())
    assert trade["gross_price_pnl"] == pytest.approx(19)
    assert trade["commission"] == pytest.approx(0.5)
    assert trade["net_pnl"] == pytest.approx(18.5)


@pytest.mark.unit
def test_bundle_is_reproducible_for_identical_inputs(tmp_path):
    def build(run_id: str):
        item = HistoricalExecutionEngine(
            run_id=run_id, metadata=metadata(), policy=policy(), initial_balance=1000
        )
        return item

    first = write_result_bundle(tmp_path / "a", build("same"), descriptor())
    second = write_result_bundle(tmp_path / "b", build("same"), descriptor())
    assert normalized_bundle_hash(first) == normalized_bundle_hash(second)


@pytest.mark.unit
def test_result_directory_is_never_overwritten(tmp_path):
    engine = HistoricalExecutionEngine(
        run_id="same", metadata=metadata(), policy=policy(), initial_balance=1000
    )
    write_result_bundle(tmp_path, engine, descriptor())
    with pytest.raises(FileExistsError):
        write_result_bundle(tmp_path, engine, descriptor())


@pytest.mark.unit
def test_result_configuration_rejects_credential_like_fields(tmp_path):
    engine = HistoricalExecutionEngine(
        run_id="secret", metadata=metadata(), policy=policy(), initial_balance=1000
    )
    sensitive_key = "api" + "_key"
    unsafe = RunDescriptor(
        **{**descriptor().__dict__, "configuration": {sensitive_key: "must-not-serialize"}}
    )
    with pytest.raises(HistoricalExecutionError, match="sensitive field"):
        write_result_bundle(tmp_path, engine, unsafe)
    assert not (tmp_path / "secret" / "configuration.json").exists()


@pytest.mark.unit
def test_validation_bundle_rejects_dirty_tree(tmp_path):
    validation_policy = policy(
        mode=RunMode.VALIDATION,
        slippage_points=1,
        slippage_kind=SlippageKind.FIXED_ADVERSE_POINTS,
        slippage_source=CostSource.OBSERVED,
    )
    engine = HistoricalExecutionEngine(
        run_id="validation", metadata=metadata(), policy=validation_policy, initial_balance=1000
    )
    dirty = RunDescriptor(**{**descriptor().__dict__, "git_dirty": True})
    with pytest.raises(HistoricalExecutionError, match="dirty tree"):
        write_result_bundle(tmp_path, engine, dirty)


@pytest.mark.unit
def test_phase1_legacy_results_and_pickles_remain_non_validated(repo_root):
    inventory = classify_phase1_legacy_inventory(repo_root / "baseline" / "phase1_manifest.json")
    assert inventory["result_set_count"] == 16
    assert inventory["cache_pickle_count"] == 44
    assert inventory["fidelity_class"] == "INSUFFICIENT_FOR_VALIDATION"
    assert inventory["preserved_read_only"] is True
