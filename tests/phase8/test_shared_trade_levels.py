from dataclasses import replace
from types import SimpleNamespace

import pandas as pd

from bot.strategy.trade_levels import LevelInputs, build_trade_levels


def _inputs(direction="buy") -> LevelInputs:
    return LevelInputs(
        direction=direction,
        entry_price=100.0,
        entry_mode="aggressive",
        ob_zone=(96.0, 104.0),
        internal_structure={},
        recent_lows=(),
        recent_highs=(),
        structure_context={},
        liquidity_pools=(),
        atr=1.0,
        point=0.01,
        stops_level=10,
        digits=2,
        level_config={"anchor_buffer_atr_mult": 0.5, "min_stop_points": 10},
        min_rr=3.0,
    )


def test_aggressive_ob_levels_are_absolute_and_mirrored():
    long = build_trade_levels(_inputs())
    short = build_trade_levels(_inputs("sell"))
    assert (long.stop, long.target, long.reason) == (95.5, 113.5, "aggressive_ob_boundary")
    assert (short.stop, short.target, short.reason) == (104.5, 86.5, "aggressive_ob_boundary")


def test_structure_anchor_precedes_zone_floor_and_pool_target():
    inputs = replace(
        _inputs(), entry_mode="standard", ob_zone=None,
        internal_structure={"last_bos_level": 98.0},
        recent_lows=(97.0,), structure_context={"discount_zone": (90.0, 93.0)},
        liquidity_pools=({"price": 110.0}, {"price": 107.0}, {"price": 108.0}),
    )
    result = build_trade_levels(inputs)
    assert (result.stop, result.target, result.reason) == (97.5, 110.0, "internal_structure_anchor")


def test_tight_stop_and_missing_anchor_reject_without_fallback():
    tight = replace(_inputs(), level_config={"min_stop_price": 5.0})
    assert build_trade_levels(tight).reason.startswith("smc_stop_too_tight")
    missing = replace(_inputs(), entry_mode="standard", ob_zone=None)
    assert build_trade_levels(missing).reason == "no_smc_stop_anchor"


def test_buffered_rr_uses_same_four_decimal_comparison():
    inputs = replace(_inputs(), min_rr_buffer=0.2, liquidity_pools=({"price": 113.5},))
    result = build_trade_levels(inputs)
    assert result.target == 114.4


def test_live_wrapper_delegates_frozen_inputs_to_pure_builder(monkeypatch):
    import main

    seen = []
    real_builder = build_trade_levels

    def spy(inputs):
        seen.append(inputs)
        return real_builder(inputs)

    monkeypatch.setattr(main, "build_trade_levels", spy)
    monkeypatch.setattr(main, "calculate_atr", lambda frame, period: 1.0)
    monkeypatch.setattr(main, "get_symbol_profile", lambda symbol: {
        "execution_levels": {"anchor_buffer_atr_mult": 0.5, "min_stop_points": 10},
    })
    info = SimpleNamespace(name="XAUUSDm", point=0.01, stops_level=10, digits=2)
    frame = pd.DataFrame({"low": [98.0], "high": [102.0]})
    result = main._build_orchestrator_trade_levels(
        info, "buy", 100.0, {"entry_mode": "aggressive", "ob_zone": (96.0, 104.0)},
        frame, {}, {}, [],
    )
    assert result == (95.5, 113.5, "aggressive_ob_boundary")
    assert len(seen) == 1
    assert seen[0].min_rr == main.ACTIVE_RISK_ENGINE.min_rr
    assert seen[0].recent_lows == (98.0,)
