"""Supported-wrapper parity with synthetic acquisition, real canonical gates."""

from datetime import timedelta
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from bot.analysis import bias_engine, liquidity_map, dxy_filter
from bot.data.candles import TIMEFRAMES
from bot.state import gate_inputs, orchestrator
from bot.strategy.setup_state import record_from_state
from bot.strategy.config import StrategyConfig
from bot.strategy.setup_intent import SetupSymbolMetadata
from bot.execution.lifecycle.serialization import entry_intent_to_payload
from bot.execution.live_adapter import intent_from_strategy_entry
from bot.validation.empirical_strategy_adapter import evaluate_setup_inputs
from bot.validation.empirical_strategy_adapter import evaluate_historical_orchestration
from bot.validation import empirical_strategy_adapter
from strategies.smc_engine import market_structure
from strategies.smc_engine.strategy_state import StrategyState
from tests.phase8.test_gate_reducer import AT


def _gold_frames(side, lifecycle="eligible"):
    values = [(2000.0, 2004.0, 1996.0, 2000.0)] * 60
    values[35] = (2010.0, 2020.0, 1980.0, 1990.0)
    values[36] = (1990.0, 2070.0, 1988.0, 2060.0)
    for index in range(37, 60):
        values[index] = (2060.0, 2064.0, 2040.0, 2060.0)
    values[59] = (2060.0, 2064.0, 2000.0, 2060.0)
    if lifecycle == "mitigated":
        values[58] = values[59]
    elif lifecycle == "invalidated":
        values[59] = (2060.0, 2064.0, 1960.0, 1970.0)
    if side == "bearish":
        values = [(4000 - o, 4000 - low, 4000 - high, 4000 - c) for o, high, low, c in values]
    frames = {}
    for timeframe in ("M5", "M15", "H1", "H4", "D1", "W1"):
        spec = TIMEFRAMES[timeframe]
        frame = pd.DataFrame(values, columns=("open", "high", "low", "close"))
        frame["open_time"] = pd.date_range(end=AT - spec.duration, periods=60, freq=spec.pandas_frequency)
        frame["available_at"] = frame["open_time"] + spec.duration
        frame["time"] = frame["open_time"]
        frame["timeframe"] = timeframe
        frame["tick_volume"] = 1
        frame["spread"] = 0
        frame["real_volume"] = 0
        frames[timeframe] = frame
    return frames


def _dxy_frames(side, missing=False):
    frames = {}
    for symbol, _weight, _invert in dxy_filter.DXY_BASKET:
        close = [1.0] * 100
        if side == "bullish" and symbol == "EURUSDm":
            close = [1.0 + index * 0.003 for index in range(100)]
        if side == "bearish" and symbol == "USDJPYm":
            close = [1.0 + index * 0.003 for index in range(100)]
        dates = pd.date_range(end=AT - timedelta(hours=1), periods=100, freq="1h")
        frames[symbol] = pd.DataFrame({
            "open_time": dates, "available_at": dates + timedelta(hours=1),
            "open": close, "high": [v + 0.01 for v in close],
            "low": [v - 0.01 for v in close], "close": close,
            "time": dates, "timeframe": "H1", "tick_volume": 1,
            "spread": 0, "real_volume": 0,
        })
    if missing:
        frames.pop("EURUSDm")
    return frames


def _install(monkeypatch, side, failed=None, lifecycle="eligible"):
    from bot.data import market_data

    gold = _gold_frames(side, lifecycle)
    constituents = _dxy_frames(side, missing=failed == "dxy")
    combined = {("XAUUSDm", tf): frame for tf, frame in gold.items()}
    combined.update({(symbol, "H1"): frame for symbol, frame in constituents.items()})

    def fetch(symbol, timeframe, bars, **kwargs):
        frame = combined.get((symbol, timeframe))
        return frame.tail(bars).copy() if frame is not None else None

    monkeypatch.setattr(market_data, "fetch_ohlcv", fetch)
    monkeypatch.setattr(market_data, "fetch_batch", lambda requests: {
        (request.symbol, request.timeframe): fetch(request.symbol, request.timeframe, request.bars)
        for request in requests
    })

    def structure(frame, silent=False):
        return {
            "structure": side, "state": "confirmed", "confidence": 80,
            "event": None if failed == "internal" else "BOS", "equal_highs": [], "equal_lows": [],
            "discount_zone": (1960.0, 2040.0), "premium_zone": (1960.0, 2040.0),
            "last_bos_level": 2040.0 if side == "bullish" else 1960.0,
        }

    for module in (bias_engine, liquidity_map, market_structure, gate_inputs, empirical_strategy_adapter):
        monkeypatch.setattr(module, "analyze_market_structure", structure)
    monkeypatch.setattr(gate_inputs, "detect_liquidity_sweep", lambda *a, **kw: (
        {} if failed == "liquidity" else {"side": "sell" if side == "bullish" else "buy", "type": "equal_lows" if side == "bullish" else "equal_highs"}
    ))
    fvg = (2020.0, 2040.0) if side == "bullish" else (1960.0, 1980.0)
    zone = (2000.0, 2040.0) if side == "bullish" else (1960.0, 2000.0)
    monkeypatch.setattr(gate_inputs, "detect_displacement", lambda *a, **kw: {
        "valid": failed != "displacement", "fvg": fvg,
    })
    monkeypatch.setattr(gate_inputs, "get_unfilled_fvgs", lambda *a, **kw: [{"bottom": fvg[0], "top": fvg[1]}])
    monkeypatch.setattr(gate_inputs, "detect_ob_breaker", lambda *a, **kw: {"valid": failed != "score", "zone": zone})
    monkeypatch.setattr(gate_inputs, "calculate_atr", lambda *a, **kw: 4.0)
    news = {"news_clear": failed != "news", "state": "BLOCKED" if failed == "news" else "CLEAR", "source": "SYNTHETIC", "reason": "fixture_event_window"}
    monkeypatch.setattr(orchestrator, "get_news_status", lambda symbol, now: news.copy())
    monkeypatch.setattr(orchestrator, "log_setup_evaluation", lambda **kwargs: None)
    return gold, constituents, news


@pytest.mark.parametrize("side", ["bullish", "bearish"])
@pytest.mark.parametrize("failed,lifecycle,expected", [
    (None, "eligible", "setup_passed_all_gates"),
    ("liquidity", "eligible", "liquidity_sweep_missing"),
    ("displacement", "eligible", "displacement_missing"),
    ("internal", "eligible", "internal_structure_missing"),
    ("score", "eligible", "score_below_threshold"),
    ("dxy", "eligible", "dxy_unsafe_or_conflicting"),
    ("news", "eligible", "news_blackout"),
    (None, "mitigated", "order_block_unavailable"),
])
def test_supported_live_and_offline_full_gate_output(monkeypatch, side, failed, lifecycle, expected):
    gold, constituents, news = _install(monkeypatch, side, failed, lifecycle)
    acquired = []
    original_builder = orchestrator.build_gate_inputs

    def observed_builder(**kwargs):
        result = original_builder(**kwargs)
        acquired.append(result)
        return result

    monkeypatch.setattr(orchestrator, "build_gate_inputs", observed_builder)
    state = StrategyState(event_time=AT)
    prior = record_from_state(state, event_at=AT)
    live = orchestrator.StrategyOrchestrator().evaluate_symbol(
        "XAUUSDm", state, event_at=AT, account_balance=1000,
        daily_pnl=0, active_trade_count=0,
    )
    historical, record = evaluate_historical_orchestration(
        gold, constituent_frames=constituents, decision_at=AT,
        news_context=news, prior_state=prior,
        active_trade_count=0, max_concurrent_trades=2,
    )
    assert live.reason == expected, live.context
    for key in live.context:
        assert historical.context[key] == live.context[key], key
    assert historical == live
    assert record == getattr(state, "_gate_record", None)
    if acquired:
        assert acquired[0] == acquired[1]
        assert record.data()["last_result"] == state._gate_record.data()["last_result"]
    if failed is None and lifecycle == "eligible":
        decision = live.context["strategy_decision"]
        assert decision["entry_eligible"]
        assert decision["side"] == ("LONG" if side == "bullish" else "SHORT")
        import main

        monkeypatch.setattr(main, "calculate_atr", lambda *a, **kw: 4.0)
        metadata = SetupSymbolMetadata("XAUUSDm", 0.01, 10, 2, AT - timedelta(days=1), AT + timedelta(days=1), "SYNTHETIC_ONLY")
        offline_setup = evaluate_setup_inputs(
            prior, acquired[1], StrategyConfig(), metadata=metadata,
            min_rr=main.ACTIVE_RISK_ENGINE.min_rr, partial_close_fraction=0.5,
        )
        assert offline_setup.intent_json is not None, offline_setup.levels_json
        entry = dict(live.context["entry"])
        entry["ob_zone"] = live.context["ob"]["zone"]
        entry_frame = gold["M5"]
        trigger = entry["limit_entry"] if entry.get("entry_type") == "limit" else entry_frame["close"].iloc[-1]
        stop, target, reason = main._build_orchestrator_trade_levels(
            SimpleNamespace(name="XAUUSDm", point=0.01, stops_level=10, digits=2),
            entry["direction"], trigger, entry, entry_frame,
            live.context["internal_structure"], live.context["liquidity"]["structure_context"],
            live.context["liquidity"]["liquidity_pools"], min_rr_buffer=0.10,
        )
        assert json.loads(offline_setup.levels_json) == {"stop": stop, "target": target, "reason": reason}
        intent = intent_from_strategy_entry(
            symbol="XAUUSDm", source_timeframe="M5", entry=entry, entry_frame=entry_frame,
            stop_loss=stop, final_target=target, partial_close_fraction=0.5,
            configuration_id="XAUUSDm:M5:phase3",
            strategy_metadata={"strategy": "SMC_COURTROOM_ORCHESTRATOR", "setup_score": live.context["score"]["score"], "setup_grade": live.context["score"]["grade"]},
        )
        assert entry_intent_to_payload(intent) == json.loads(offline_setup.intent_json)
        repeated, restored = evaluate_historical_orchestration(
            gold, constituent_frames=constituents, decision_at=AT,
            news_context=news, prior_state=record,
            active_trade_count=0, max_concurrent_trades=2,
        )
        assert repeated == historical
        assert restored == record
