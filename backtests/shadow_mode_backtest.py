
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

CACHE_DIR = ROOT_DIR / "backtests" / "cached_data"

import MetaTrader5 as mt5  # pyright: ignore[reportMissingImports]
import pandas as pd  # pyright: ignore[reportMissingModuleSource]

from bot.analysis.bias_engine import TIMEFRAME_WEIGHTS, resolve_trade_bias
from bot.analysis.dxy_filter import get_dxy_bias_from_array
from bot.analysis.fvg_engine import get_unfilled_fvgs
from bot.analysis.liquidity_map import get_asian_session_range, get_previous_day_levels, get_previous_week_levels
from bot.execution.confluence_scorer import score_setup
from bot.execution.news_filter import get_news_status
from bot.execution.risk_engine import RiskEngine
from bot.utils.session_clock import get_session_context
from strategies.smc_engine.displacement_engine import detect_displacement
from strategies.smc_engine.entry_model import determine_entry
from strategies.smc_engine.liquidity_engine import detect_liquidity_sweep
from strategies.smc_engine.market_structure import analyze_market_structure
from strategies.smc_engine.ob_breaker_engine import detect_ob_breaker
from strategies.smc_engine.strategy_state import StrategyState
from utils.connect import connect_mt5
from utils.symbol_profiles import get_symbol_profile

import strategies.smc_engine.market_structure as market_structure_module
import strategies.smc_engine.liquidity_engine as liquidity_module
import strategies.smc_engine.displacement_engine as displacement_module
import strategies.smc_engine.ob_breaker_engine as ob_breaker_module
import strategies.smc_engine.entry_model as entry_model_module
import strategies.smc_engine.strategy_state as strategy_state_module
import utils.log as log_module
import main as main_module
from main import _build_orchestrator_trade_levels

TIMEFRAME_MAP = {
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
}

DXY_BASKET = [
    ("EURUSDm", 0.576, True),
    ("USDJPYm", 0.136, False),
    ("GBPUSDm", 0.119, True),
    ("USDCADm", 0.091, False),
    ("USDSEKm", 0.042, False),
    ("USDCHFm", 0.036, False),
]


def _mute_logs() -> None:
    def _noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    log_module.log = _noop
    market_structure_module.log = _noop
    liquidity_module.log = _noop
    displacement_module.log = _noop
    ob_breaker_module.log = _noop
    entry_model_module.log = _noop
    strategy_state_module.log = _noop


@dataclass
class Position:
    ticket: int
    symbol: str
    direction: str
    lot: float
    entry_price: float
    sl: float
    tp: float
    risk_price: float
    sl_reason: str
    opened_at: datetime
    score: int
    grade: str
    # Trailing / kill-switch state
    peak_price: float | None = None
    trail_activated: bool = False
    _partial_pct_closed: float = 0.0


@dataclass
class CostModel:
    """First-order live trading-cost model applied to every round trip."""
    spread_price: float = 0.0
    slippage_price: float = 0.0
    commission_per_lot: float = 0.0
    contract_size: float = 100.0

    def round_trip(self, lot: float) -> float:
        # Spread is paid once (enter at ask, exit at bid); slippage on both fills.
        price_cost = self.spread_price + 2.0 * self.slippage_price
        return price_cost * lot * self.contract_size + self.commission_per_lot * lot


def _update_trailing_sl_live(pos: Position, high: float, low: float, m5_atr: float, point: float, trail_cfg: dict) -> None:
    """Mirror the live main.py ATR-3x trail: trail behind the running peak by
    max(atr*mult, min_distance) and only ever move the stop to break-even or
    better (never into a loss). Keeps the backtest exit engine matched to live."""
    if m5_atr <= 0:
        return
    atr_mult = float(trail_cfg.get("atr_mult", 3.0))
    min_pts = float(trail_cfg.get("min_distance_points", 100)) * point
    trail_dist = max(m5_atr * atr_mult, min_pts)
    if pos.direction == "buy":
        pos.peak_price = high if pos.peak_price is None else max(pos.peak_price, high)
        new_sl = pos.peak_price - trail_dist
        if new_sl > pos.sl and new_sl >= pos.entry_price:
            pos.sl = new_sl
    else:
        pos.peak_price = low if pos.peak_price is None else min(pos.peak_price, low)
        new_sl = pos.peak_price + trail_dist
        if new_sl < pos.sl and new_sl <= pos.entry_price:
            pos.sl = new_sl


def _apply_trailing(pos: Position, high: float, low: float, trail_mode: str, m5_atr: float, point: float, trail_cfg: dict) -> None:
    if trail_mode == "live_atr_3x":
        _update_trailing_sl_live(pos, high, low, m5_atr, point, trail_cfg)
    else:
        _update_trailing_sl(pos, high, low, trail_mode, m5_atr)


def _get_trail_offset(pos: Position, trail_mode: str, m5_atr: float) -> float:
    """Determine trailing SL offset in price points based on mode."""
    if trail_mode == "1x":
        return pos.risk_price
    elif trail_mode == "1.5x":
        return pos.risk_price * 1.5
    elif trail_mode == "2x":
        return pos.risk_price * 2.0
    elif trail_mode == "2stage":
        # 1.5x room until trade extends 2x risk, then tighten to 1x
        peak_dist = abs(pos.peak_price - pos.entry_price) if pos.peak_price is not None else 0.0
        if peak_dist >= pos.risk_price * 2.0:
            return pos.risk_price
        return pos.risk_price * 1.5
    elif trail_mode == "atr-3x":
        return m5_atr * 3.0 if m5_atr > 0 else pos.risk_price
    return pos.risk_price


def _update_trailing_sl(pos: Position, high: float, low: float, trail_mode: str = "1x", m5_atr: float = 0.0) -> None:
    """Trail SL after trade has moved 1R in profit. Offset behind peak depends on trail_mode."""
    if pos.risk_price <= 0:
        return
    if pos.direction == "buy":
        if not pos.trail_activated:
            if high >= pos.entry_price + pos.risk_price:
                pos.trail_activated = True
                pos.peak_price = high
        if pos.trail_activated and pos.peak_price is not None:
            pos.peak_price = max(pos.peak_price, high)
            offset = _get_trail_offset(pos, trail_mode, m5_atr)
            new_sl = pos.peak_price - offset
            if new_sl > pos.sl:
                pos.sl = new_sl
    else:
        if not pos.trail_activated:
            if low <= pos.entry_price - pos.risk_price:
                pos.trail_activated = True
                pos.peak_price = low
        if pos.trail_activated and pos.peak_price is not None:
            pos.peak_price = min(pos.peak_price, low)
            offset = _get_trail_offset(pos, trail_mode, m5_atr)
            new_sl = pos.peak_price + offset
            if new_sl < pos.sl:
                pos.sl = new_sl


def _check_kill_switch(
    pos: Position,
    now_ts: datetime,
    m15_closed: pd.DataFrame,
    profile: dict,
) -> bool:
    """Check if M15 structure has invalidated the trade entry. Returns True if structure failed."""
    if m15_closed.empty or len(m15_closed) < 8:
        return False
    # Count closed M15 bars since position opened
    opened = pos.opened_at.replace(tzinfo=None) if pos.opened_at.tzinfo is not None else pos.opened_at
    bars_since_entry = sum(1 for ts in m15_closed.index if ts.tzinfo is not None and ts.replace(tzinfo=None) >= opened)
    kill_switch_min_bars = int(profile.get("kill_switch_min_bars", 4))
    if bars_since_entry < kill_switch_min_bars:
        return False

    c1 = m15_closed.iloc[-4]
    c2 = m15_closed.iloc[-3]
    c3 = m15_closed.iloc[-2]
    c4 = m15_closed.iloc[-1]

    # Simple ATR from closed M15 bars (using .values for speed)
    highs = m15_closed["high"].values
    lows = m15_closed["low"].values
    closes = m15_closed["close"].values
    tr_sum = 0.0
    tr_count = 0
    for i in range(1, len(highs)):
        tr_val = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        tr_sum += tr_val
        tr_count += 1
    atr_val = tr_sum / tr_count if tr_count > 0 else 0.0

    break_buffer = atr_val * float(profile.get("kill_switch_atr_break_mult", 0.15)) if atr_val > 0 else 0.0

    if pos.direction == "buy":
        level1 = min(c1["low"], c2["low"])
        level2 = min(c2["low"], c3["low"])
        break1 = c3["close"] < (level1 - break_buffer)
        break2 = c4["close"] < (level2 - break_buffer)
        return bool(break1 and break2)
    else:
        level1 = max(c1["high"], c2["high"])
        level2 = max(c2["high"], c3["high"])
        break1 = c3["close"] > (level1 + break_buffer)
        break2 = c4["close"] > (level2 + break_buffer)
        return bool(break1 and break2)


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _to_df(rates: Any) -> pd.DataFrame:
    df = pd.DataFrame(rates)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    return df


def _fetch_range(symbol: str, timeframe: str, start: datetime, end: datetime, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
    # File-based cache: reuse previously downloaded MT5 data
    cache_path = None
    if use_cache and not force_refresh:
        cache_key = f"{symbol}_{timeframe}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.pkl"
        cache_path = CACHE_DIR / cache_key
        if cache_path.exists():
            try:
                return pd.read_pickle(str(cache_path))
            except Exception:
                pass  # corrupted cache — re-fetch

    mt5.symbol_select(symbol, True)
    chunk_days = {
        "M5": 20,
        "M15": 45,
        "M30": 60,
        "H1": 120,
        "H4": 240,
        "D1": 730,
        "W1": 3650,
    }.get(timeframe, 60)
    frames: list[pd.DataFrame] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days), end)
        rates = mt5.copy_rates_range(symbol, TIMEFRAME_MAP[timeframe], cursor, chunk_end)
        df = _to_df(rates)
        if not df.empty:
            frames.append(df)
        cursor = chunk_end + timedelta(seconds=1)
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames).sort_index().loc[~pd.concat(frames).sort_index().index.duplicated(keep="last")]

    if use_cache:
        if cache_path is None:
            cache_key = f"{symbol}_{timeframe}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.pkl"
            cache_path = CACHE_DIR / cache_key
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            result.to_pickle(str(cache_path))
        except Exception:
            pass  # cache write failure is non-fatal
    return result


def _apply_symbol_profile(symbol: str) -> dict:
    profile = get_symbol_profile(symbol)
    ms_cfg = profile.get("market_structure", {})
    market_structure_module.DISPLACEMENT_ATR_MULT = float(ms_cfg.get("DISPLACEMENT_ATR_MULT", market_structure_module.DISPLACEMENT_ATR_MULT))
    market_structure_module.LOW_VOL_RATIO = float(ms_cfg.get("LOW_VOL_RATIO", market_structure_module.LOW_VOL_RATIO))
    market_structure_module.HIGH_VOL_RATIO = float(ms_cfg.get("HIGH_VOL_RATIO", market_structure_module.HIGH_VOL_RATIO))
    market_structure_module.MIN_SWING_ATR_MULT = float(ms_cfg.get("MIN_SWING_ATR_MULT", market_structure_module.MIN_SWING_ATR_MULT))
    market_structure_module.PRESSURE_MIN_MOVE_ATR = float(ms_cfg.get("PRESSURE_MIN_MOVE_ATR", market_structure_module.PRESSURE_MIN_MOVE_ATR))
    market_structure_module.PRESSURE_MIN_BAR_COUNT = int(ms_cfg.get("PRESSURE_MIN_BAR_COUNT", market_structure_module.PRESSURE_MIN_BAR_COUNT))

    liq_cfg = profile.get("liquidity", {})
    liquidity_module.SWEEP_STRENGTH_MIN = float(liq_cfg.get("SWEEP_STRENGTH_MIN", liquidity_module.SWEEP_STRENGTH_MIN))
    liquidity_module.BODY_DOMINANCE_MIN = float(liq_cfg.get("BODY_DOMINANCE_MIN", liquidity_module.BODY_DOMINANCE_MIN))
    liquidity_module.EQ_TOL_ATR_MULT = float(liq_cfg.get("EQ_TOL_ATR_MULT", liquidity_module.EQ_TOL_ATR_MULT))
    liquidity_module.LOW_VOL_SKIP_RATIO = float(liq_cfg.get("LOW_VOL_SKIP_RATIO", liquidity_module.LOW_VOL_SKIP_RATIO))

    disp_cfg = profile.get("displacement", {})
    displacement_module.IMPULSE_ATR_MULT_DEFAULT = float(disp_cfg.get("impulse_atr_mult", displacement_module.IMPULSE_ATR_MULT_DEFAULT))
    displacement_module.LOOKBACK_CANDLES_DEFAULT = int(disp_cfg.get("lookback_candles", displacement_module.LOOKBACK_CANDLES_DEFAULT))

    ob_cfg = profile.get("ob_breaker", {})
    ob_breaker_module.LEVEL_PAD_ATR_MULT = float(ob_cfg.get("level_pad_atr_mult", ob_breaker_module.LEVEL_PAD_ATR_MULT))
    return profile


def _normalize_direction(result: dict | None) -> str:
    if not result:
        return "neutral"
    structure = result.get("structure")
    state = result.get("state")
    lead_bias = (result.get("lead_bias") or {}).get("direction")
    if state in ("confirmed", "transition") and structure in ("bullish", "bearish"):
        return str(structure)
    if lead_bias in ("bullish", "bearish"):
        return str(lead_bias)
    return "neutral"


def _build_bias_snapshot(tf_frames: dict[str, pd.DataFrame]) -> dict[str, object]:
    timeframes: dict[str, dict[str, object]] = {}
    for tf in ("W1", "D1", "H4", "H1", "M15"):
        df = tf_frames.get(tf)
        result = analyze_market_structure(df, silent=True) if df is not None and not df.empty else None
        direction = _normalize_direction(result)
        timeframes[tf] = {
            "direction": direction,
            "score": 1 if direction == "bullish" else -1 if direction == "bearish" else 0,
            "confidence": int((result or {}).get("confidence", 0) or 0),
            "state": str((result or {}).get("state", "range")),
            "event": (result or {}).get("event"),
            "condition": (result or {}).get("condition"),
            "lead_bias": ((result or {}).get("lead_bias") or {}).get("direction"),
        }

    htf_tfs = ("W1", "D1", "H4")
    raw_sum = sum(int(timeframes[tf]["score"]) for tf in htf_tfs)
    weighted_score = sum(float(timeframes[tf]["score"]) * TIMEFRAME_WEIGHTS.get(tf, 0.0) for tf in htf_tfs)
    non_neutral = [timeframes[tf]["direction"] for tf in htf_tfs if timeframes[tf]["score"] != 0]
    direction = "bullish" if raw_sum > 0 else "bearish" if raw_sum < 0 else "neutral"
    return {
        "symbol": "XAUUSDm",
        "timeframes": timeframes,
        "htf_bias": {
            "direction": direction,
            "raw_sum": raw_sum,
            "weighted_score": round(weighted_score, 4),
            "alignment_strength": round(abs(weighted_score), 4),
            "conflict": len(set(non_neutral)) > 1,
            "aligned": bool(non_neutral and len(set(non_neutral)) == 1),
            "contributors": {tf: timeframes[tf] for tf in htf_tfs},
        },
    }


def _pool_entry(price: float, pool_type: str, timeframe: str, **extra) -> dict[str, object]:
    return {"price": float(price), "type": pool_type, "timeframe": timeframe, **extra}


def _build_liquidity_map(symbol: str, structure_context: dict | None, m15_slice: pd.DataFrame, d1_slice: pd.DataFrame, w1_slice: pd.DataFrame) -> dict[str, object]:
    previous_day = get_previous_day_levels(d1_slice)
    previous_week = get_previous_week_levels(w1_slice)
    asian_range = get_asian_session_range(m15_slice)
    liquidity_pools: list[dict[str, object]] = []
    structure_context = structure_context or {}
    for level in structure_context.get("equal_highs", []) or []:
        if isinstance(level, dict) and level.get("price") is not None:
            liquidity_pools.append(_pool_entry(level["price"], "equal_highs", "H1", top=level.get("top"), bottom=level.get("bottom"), count=level.get("count")))
    for level in structure_context.get("equal_lows", []) or []:
        if isinstance(level, dict) and level.get("price") is not None:
            liquidity_pools.append(_pool_entry(level["price"], "equal_lows", "H1", top=level.get("top"), bottom=level.get("bottom"), count=level.get("count")))
    if previous_day:
        liquidity_pools.append(_pool_entry(previous_day["high"], "pdh", "D1"))
        liquidity_pools.append(_pool_entry(previous_day["low"], "pdl", "D1"))
    if previous_week:
        liquidity_pools.append(_pool_entry(previous_week["high"], "pwh", "W1"))
        liquidity_pools.append(_pool_entry(previous_week["low"], "pwl", "W1"))
    if asian_range:
        liquidity_pools.append(_pool_entry(asian_range["high"], "asian_high", "session"))
        liquidity_pools.append(_pool_entry(asian_range["low"], "asian_low", "session"))
    return {
        "symbol": symbol,
        "structure_context": structure_context,
        "previous_day": previous_day,
        "previous_week": previous_week,
        "asian_range": asian_range,
        "liquidity_pools": [pool for pool in liquidity_pools if isinstance(pool, dict)],
    }


def _synthetic_dxy_context(symbol: str, gold_structure: dict | None, dxy_frames: dict[str, pd.DataFrame], now_ts) -> dict[str, object]:
    if not symbol.startswith("XAU"):
        return {"available": False, "relationship": "not_applicable", "confirms_bias": False, "reduce_size": False}
    components = []
    total_weight = 0.0
    for pair, weight, invert in DXY_BASKET:
        df = dxy_frames.get(pair)
        if df is None or df.empty:
            continue
        closes = df[df.index <= now_ts]["close"].tail(100).astype(float).to_numpy()
        if len(closes) < 80:
            continue
        if invert:
            closes = 1.0 / closes
        components.append((closes, weight))
        total_weight += weight
    if not components or total_weight <= 0:
        return {"available": False, "source": "synthetic_basket", "dxy_bias": "unavailable", "confirms_bias": False, "reduce_size": False, "basket_pairs_used": 0}
    min_len = min(len(c[0]) for c in components)
    dxy = None
    for closes, weight in components:
        part = closes[-min_len:] * (weight / total_weight)
        dxy = part if dxy is None else dxy + part
    dxy_dir = get_dxy_bias_from_array(dxy)
    gold_dir = str((gold_structure or {}).get("structure", "neutral"))
    gold_state = str((gold_structure or {}).get("state", "range"))
    gold_lead_bias = ((gold_structure or {}).get("lead_bias") or {}).get("direction")
    confirms = (gold_dir == "bullish" and dxy_dir == "bearish") or (gold_dir == "bearish" and dxy_dir == "bullish")
    divergence = (
        (dxy_dir == "bullish" and gold_state in ("range", "transition") and gold_lead_bias == "bullish")
        or (dxy_dir == "bearish" and gold_state in ("range", "transition") and gold_lead_bias == "bearish")
    )
    conflicts = gold_dir in ("bullish", "bearish") and dxy_dir in ("bullish", "bearish") and not confirms and not divergence
    return {
        "available": dxy_dir != "unavailable",
        "source": "synthetic_basket",
        "dxy_bias": dxy_dir,
        "gold_bias": gold_dir,
        "gold_state": gold_state,
        "gold_lead_bias": gold_lead_bias,
        "relationship": "inverse_confirmed" if confirms else "divergence" if divergence else "conflict" if conflicts else "neutral",
        "confirms_bias": bool(confirms),
        "reduce_size": bool(conflicts),
        "basket_pairs_used": len(components),
    }


def _last_index_key(df: pd.DataFrame | None) -> str | None:
    if df is None or df.empty:
        return None
    return str(df.index[-1])


def _dxy_cache_key(dxy_frames: dict[str, pd.DataFrame], now_ts) -> tuple:
    key = []
    for pair, _weight, _invert in DXY_BASKET:
        df = dxy_frames.get(pair)
        if df is None or df.empty:
            key.append((pair, None))
            continue
        try:
            pos = df.index.get_loc(now_ts, method='ffill')
            key.append((pair, str(df.index[pos])))
        except (KeyError, TypeError):
            key.append((pair, None))
    return tuple(key)


def _pnl(symbol: str, direction: str, lot: float, entry: float, exit_price: float, cost: CostModel | None = None) -> float:
    sign = 1 if direction == "buy" else -1
    contract = cost.contract_size if cost else 100.0
    gross = (exit_price - entry) * sign * lot * contract
    fees = cost.round_trip(lot) if cost else 0.0
    return float(gross - fees)


def run_backtest(
    symbol: str,
    start: datetime,
    end: datetime,
    capital: float,
    out_dir: Path,
    trail_mode: str = "live_atr_3x",
    *,
    spread_points: float = 0.0,
    slippage_points: float = 0.0,
    commission_per_lot: float = 0.0,
    min_rr: float | None = None,
) -> dict[str, Any]:
    profile = _apply_symbol_profile(symbol)
    risk_engine = RiskEngine()
    if min_rr is not None:
        # Single source of truth: drive both the local RR validation and the
        # TP placement inside main._build_orchestrator_trade_levels.
        risk_engine.min_rr = float(min_rr)
        main_module.ACTIVE_RISK_ENGINE.min_rr = float(min_rr)
    pair_limit = int(profile.get("pair_limit", 1))
    structure_tf = str(profile.get("structure_tf", "H1"))
    entry_tf = str(profile.get("entry_tf", "M5"))
    structure_bars = int(profile.get("structure_bars", 300))
    entry_bars = int(profile.get("entry_bars", 150))
    warmup_start = start - timedelta(days=370)

    data_frames = {tf: _fetch_range(symbol, tf, warmup_start, end) for tf in ("W1", "D1", "H4", "H1", "M15", entry_tf)}
    entry_df_all = data_frames[entry_tf]
    if entry_df_all is None or entry_df_all.empty:
        raise RuntimeError(f"No {entry_tf} data for {symbol}")
    dxy_frames = {pair: _fetch_range(pair, "H1", warmup_start, end) for pair, _w, _i in DXY_BASKET}

    state = StrategyState()
    open_positions: list[Position] = []
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    no_trade_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    realized_pnl = 0.0
    current_day = None
    day_start_realized_pnl = 0.0
    ticket_seq = 1
    bias_cache: dict[tuple, dict[str, object]] = {}
    structure_cache: dict[str | None, dict[str, object]] = {}
    internal_structure_cache: dict[str | None, dict[str, object]] = {}
    liquidity_cache: dict[tuple, dict[str, object]] = {}
    dxy_cache: dict[tuple, dict[str, object]] = {}

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        raise RuntimeError(f"MT5 symbol info unavailable for {symbol}")

    point = float(getattr(symbol_info, "point", 0.01) or 0.01)
    contract_size = float(getattr(symbol_info, "trade_contract_size", 100.0) or 100.0)
    trail_cfg = profile.get("trailing", {})
    cost = CostModel(
        spread_price=spread_points * point,
        slippage_price=slippage_points * point,
        commission_per_lot=commission_per_lot,
        contract_size=contract_size,
    )
    total_costs = 0.0

    test_rows = entry_df_all[(entry_df_all.index >= start) & (entry_df_all.index <= end)]
    total = len(test_rows)

    # Pre-compute M5 ATR for ATR-based trailing modes
    test_rows = test_rows.copy()
    prev_close = test_rows["close"].shift(1)
    tr_vals = pd.concat([
        (test_rows["high"] - test_rows["low"]).abs(),
        (test_rows["high"] - prev_close).abs(),
        (test_rows["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    test_rows["atr_14"] = tr_vals.rolling(window=14).mean().shift(1)

    # Pre-compute integer positions for O(log n) per-bar DataFrame slicing
    tf_positions: dict[str, Any] = {}
    for tf in ("W1", "D1", "H4", "H1", "M15"):
        df = data_frames.get(tf)
        if df is not None and not df.empty:
            tf_positions[tf] = df.index.get_indexer(test_rows.index, method='ffill')
    m5_positions = entry_df_all.index.get_indexer(test_rows.index)

    for idx, (now_ts, candle) in enumerate(test_rows.iterrows(), start=1):
        loop_day = now_ts.date()
        if loop_day != current_day:
            current_day = loop_day
            day_start_realized_pnl = realized_pnl

        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])

        # Build M15 view for kill-switch before position loop (only when positions exist)
        i = idx - 1
        current_m15_idx = int(tf_positions.get("M15", [0])[i]) if "M15" in tf_positions and i < len(tf_positions["M15"]) and tf_positions["M15"][i] >= 0 else -1
        m15_closed = pd.DataFrame()
        if open_positions and current_m15_idx > 0 and data_frames.get("M15") is not None:
            all_m15 = data_frames["M15"]
            m15_start = max(0, current_m15_idx - 20)
            m15_closed = all_m15.iloc[m15_start:current_m15_idx]

        survivors: list[Position] = []
        for pos in open_positions:
            exit_price = None
            reason = None

            m5_atr = float(candle.get("atr_14", 0.0)) if pd.notna(candle.get("atr_14", None)) else 0.0

            # 1. Check SL/TP against the levels carried from the PREVIOUS bar.
            #    Trailing is applied afterwards (step 3) so a stop moved using
            #    this bar's extreme cannot also be "hit" on the same bar — that
            #    look-ahead inflated backtest win rates vs live.
            if pos.direction == "buy":
                sl_hit = low <= pos.sl
                tp_hit = high >= pos.tp
                if sl_hit:
                    exit_price, reason = pos.sl, "sl_hit"
                elif tp_hit:
                    exit_price, reason = pos.tp, "tp_hit"
            else:
                sl_hit = high >= pos.sl
                tp_hit = low <= pos.tp
                if sl_hit:
                    exit_price, reason = pos.sl, "sl_hit"
                elif tp_hit:
                    exit_price, reason = pos.tp, "tp_hit"

            # 2. Check kill-switch (structure failure) if still alive
            if exit_price is None:
                if _check_kill_switch(pos, now_ts, m15_closed, profile):
                    exit_price, reason = close, "kill_switch"

            # 3. Survivor: trail the stop for FUTURE bars, then carry forward
            if exit_price is None:
                _apply_trailing(pos, high, low, trail_mode, m5_atr, point, trail_cfg)
                survivors.append(pos)
                continue

            pnl = _pnl(symbol, pos.direction, pos.lot, pos.entry_price, float(exit_price), cost)
            total_costs += cost.round_trip(pos.lot)
            realized_pnl += pnl
            # Cascade circuit breaker: track trade result
            trade_dir = "bullish" if pos.direction == "buy" else "bearish"
            trade_result = "win" if pnl > 0 else "loss"
            state.record_trade_result(trade_dir, trade_result, now=now_ts.to_pydatetime())
            trades.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "direction": pos.direction,
                "opened_at": pos.opened_at.isoformat(),
                "closed_at": now_ts.isoformat(),
                "entry_price": round(pos.entry_price, 5),
                "exit_price": round(float(exit_price), 5),
                "sl": round(pos.sl, 5),
                "tp": round(pos.tp, 5),
                "risk_price": round(pos.risk_price, 5),
                "sl_reason": pos.sl_reason,
                "lot": pos.lot,
                "score": pos.score,
                "grade": pos.grade,
                "reason": reason,
                "pnl": round(pnl, 4),
            })
        open_positions = survivors
        equity_rows.append({"timestamp": now_ts.isoformat(), "equity": round(capital + realized_pnl, 4), "open_positions": len(open_positions)})

        if idx % 500 == 0:
            print(f"[SHADOW PROGRESS] {idx}/{total} ({(idx / max(total, 1)) * 100:.1f}%)", flush=True)

        if len(open_positions) >= pair_limit:
            action_counts["skip"] += 1
            no_trade_counts["max_concurrent_trades_hit"] += 1
            continue

        tf_frames = {}
        for tf in ("W1", "D1", "H4", "H1", "M15"):
            df = data_frames.get(tf)
            pos_arr = tf_positions.get(tf)
            pos = int(pos_arr[i]) if pos_arr is not None and i < len(pos_arr) and pos_arr[i] >= 0 else -1
            if df is not None and pos >= 0:
                start_row = max(0, pos - 319)
                tf_frames[tf] = df.iloc[start_row:pos + 1].copy()
            else:
                tf_frames[tf] = pd.DataFrame()
        m5_pos = int(m5_positions[i]) if i < len(m5_positions) and m5_positions[i] >= 0 else -1
        entry_slice = entry_df_all.iloc[max(0, m5_pos - entry_bars + 1):m5_pos + 1].copy() if m5_pos >= 0 else pd.DataFrame()
        h1_slice = tf_frames["H1"].tail(structure_bars).copy()
        m15_slice = tf_frames["M15"].tail(220).copy()
        d1_slice = tf_frames["D1"].tail(10).copy()
        w1_slice = tf_frames["W1"].tail(10).copy()

        session_context = get_session_context(now_ts.to_pydatetime())
        session_context["session_allowed"] = True
        state.update_session(session_context)
        # Sunday filter: skip trading on Sunday (0% WR over baseline)
        if now_ts.weekday() == 6:  # Sunday = 6
            action_counts["skip"] += 1
            no_trade_counts["sunday_filter_skipped"] += 1
            continue
        # Bad hour filter: 00, 02, 11, 13 UTC (combined 7% WR over 15 trades)
        hour_utc = now_ts.hour
        if hour_utc in (0, 11):  # Match live orchestrator: block only hours 0 and 11
            action_counts["skip"] += 1
            no_trade_counts["bad_hour_filter_skipped"] += 1
            continue
        news_status = get_news_status(symbol, now_ts.to_pydatetime())
        state.update_news(news_status)
        if not news_status.get("news_clear", True):
            action_counts["pause"] += 1
            no_trade_counts["news_blackout"] += 1
            continue
        daily_realized_pnl = realized_pnl - day_start_realized_pnl
        if risk_engine.check_daily_drawdown(daily_realized_pnl, capital):
            action_counts["halt"] += 1
            no_trade_counts["daily_drawdown_limit_hit"] += 1
            continue

        bias_key = tuple(_last_index_key(tf_frames.get(tf)) for tf in ("W1", "D1", "H4", "H1", "M15"))
        bias_snapshot = bias_cache.get(bias_key)
        if bias_snapshot is None:
            bias_snapshot = _build_bias_snapshot(tf_frames)
            bias_cache[bias_key] = bias_snapshot
        state.update_bias(bias_snapshot)
        bias_resolution = resolve_trade_bias(bias_snapshot)
        htf_bias = str(bias_resolution.get("direction", "neutral"))
        if htf_bias not in ("bullish", "bearish"):
            state.reject_setup("htf_bias_unconfirmed")
            action_counts["skip"] += 1
            no_trade_counts["htf_bias_unconfirmed"] += 1
            continue

        # CASCADE CIRCUIT BREAKER: block direction after 2 same-direction losses
        if state.is_direction_blocked(htf_bias, now=now_ts.to_pydatetime()):
            state.reject_setup(f"cascade_breaker_blocked_{htf_bias}")
            action_counts["skip"] += 1
            no_trade_counts[f"cascade_breaker_blocked_{htf_bias}"] += 1
            continue

        structure_key = _last_index_key(h1_slice)
        structure_context = structure_cache.get(structure_key)
        if structure_context is None:
            analyzed_structure = analyze_market_structure(h1_slice, silent=True) if not h1_slice.empty else {}
            structure_context = analyzed_structure if isinstance(analyzed_structure, dict) else {}
            structure_cache[structure_key] = structure_context
        structure_context = structure_context if isinstance(structure_context, dict) else {}
        liquidity_key = (structure_key, _last_index_key(m15_slice), _last_index_key(d1_slice), _last_index_key(w1_slice))
        liquidity_context = liquidity_cache.get(liquidity_key)
        if liquidity_context is None:
            liquidity_context = _build_liquidity_map(symbol, structure_context, m15_slice, d1_slice, w1_slice)
            liquidity_cache[liquidity_key] = liquidity_context
        dxy_key = (structure_key, _dxy_cache_key(dxy_frames, now_ts))
        dxy_context = dxy_cache.get(dxy_key)
        if dxy_context is None:
            dxy_context = _synthetic_dxy_context(symbol, structure_context, dxy_frames, now_ts)
            dxy_cache[dxy_key] = dxy_context
        structure_dir = str(structure_context.get("structure", ""))
        structure_state = str(structure_context.get("state", ""))
        if structure_dir in ("bullish", "bearish") and structure_state in ("confirmed", "transition", "range"):
            state.update_structure(structure_dir, structure_state)

        liquidity_signal = detect_liquidity_sweep(
            h1_slice,
            structure_dir=htf_bias,
            lookback=int(profile.get("liquidity", {}).get("lookback", 20)),
            sweep_window=int(profile.get("liquidity", {}).get("sweep_window", 3)),
        )
        liquidity_signal = liquidity_signal if isinstance(liquidity_signal, dict) else {}
        if not liquidity_signal:
            state.reject_setup("liquidity_sweep_missing")
            action_counts["wait"] += 1
            no_trade_counts["liquidity_sweep_missing"] += 1
            continue
        if liquidity_signal.get("side") in ("buy", "sell"):
            state.update_liquidity(side=liquidity_signal["side"], index=int(idx), liquidity_type=liquidity_signal.get("type"))

        displacement = detect_displacement(
            entry_slice,
            htf_bias,
            atr_period=14,
            impulse_atr_mult=float(profile.get("displacement", {}).get("impulse_atr_mult", 1.2)),
            lookback_candles=int(profile.get("displacement", {}).get("lookback_candles", 3)),
        )
        displacement = displacement if isinstance(displacement, dict) else {}
        if not bool(displacement.get("valid")):
            state.reject_setup("displacement_missing")
            action_counts["wait"] += 1
            no_trade_counts["displacement_missing"] += 1
            continue
        state.update_displacement(displacement.get("fvg"))

        internal_structure_key = _last_index_key(m15_slice)
        internal_structure = internal_structure_cache.get(internal_structure_key)
        if internal_structure is None:
            analyzed_internal = analyze_market_structure(m15_slice, silent=True) if not m15_slice.empty else {}
            internal_structure = analyzed_internal if isinstance(analyzed_internal, dict) else {}
            internal_structure_cache[internal_structure_key] = internal_structure
        fvgs = [fvg for fvg in get_unfilled_fvgs(entry_slice, timeframe=entry_tf, direction=htf_bias) if isinstance(fvg, dict)]
        ob_result = detect_ob_breaker(
            entry_slice,
            htf_bias,
            lookback=int(profile.get("ob_breaker", {}).get("lookback", 30)),
            search_back=int(profile.get("ob_breaker", {}).get("search_back", 12)),
            premium_zone=structure_context.get("premium_zone"),
            discount_zone=structure_context.get("discount_zone"),
            equilibrium_level=structure_context.get("equilibrium_level"),
        )
        ob_result = ob_result if isinstance(ob_result, dict) else {}
        first_fvg = fvgs[0] if fvgs else None
        ob_zone = ob_result.get("zone") if ob_result.get("valid") else None
        fvg_in_ob_zone = bool(
            first_fvg and ob_zone and first_fvg.get("bottom") is not None and first_fvg.get("top") is not None
            and float(first_fvg.get("bottom")) <= float(ob_zone[1]) and float(first_fvg.get("top")) >= float(ob_zone[0])
        )
        score_result = score_setup({
            "htf_bias": htf_bias,
            "trade_direction": htf_bias,
            "price_in_discount_or_premium": bool(structure_context.get("discount_zone") if htf_bias == "bullish" else structure_context.get("premium_zone")),
            "valid_ob_present": bool(ob_result.get("valid")),
            "fvg_in_ob_zone": fvg_in_ob_zone,
            "liquidity_swept_before_entry": bool(liquidity_signal),
            "internal_bos_on_m15": bool(
                internal_structure.get("event") in ("BOS", "CHOCH") or
                internal_structure.get("early_event", {}).get("event") in ("BOS", "CHOCH")
            ),
            "session_allowed": True,
            "dxy_confirms_bias": bool(dxy_context.get("confirms_bias")),
            "no_news_in_30min": bool(news_status.get("news_clear")),
        })
        if not score_result.get("passes_threshold", False):
            state.reject_setup("score_below_threshold")
            action_counts["skip"] += 1
            no_trade_counts["score_below_threshold"] += 1
            continue

        # DIRECTION-BASED SCORE FILTER REMOVED — Match live orchestrator (line 365-368)
        # The old filter required bullish ≥10 vs bearish ≥8, creating an unjustified
        # anti-buy bias. Live removed this filter, so backtest must match.

        entry = determine_entry(symbol, state, close, score_result=score_result, context={
            "ob_zone": ob_zone,
            "fvg_zone": first_fvg,
            "after_london_open": session_context.get("active_session") == "london",
            "asian_liquidity_swept": any(pool.get("type") in ("asian_high", "asian_low") for pool in liquidity_context.get("liquidity_pools", [])),
            "sweep_rejected": bool(
                internal_structure.get("event") in ("CHOCH", "BOS") or
                internal_structure.get("early_event", {}).get("event") in ("CHOCH", "BOS")
            ),
            "internal_structure_event": internal_structure.get("event"),
            "htf_zone_alignment": bool(ob_result.get("valid")),
        })
        if not entry:
            action_counts["wait"] += 1
            no_trade_counts["entry_not_ready"] += 1
            continue

        direction = str(entry.get("direction", "")).lower()
        if direction not in ("buy", "sell"):
            action_counts["skip"] += 1
            no_trade_counts["invalid_entry_direction"] += 1
            continue
        if entry.get("entry_type") == "limit":
            limit_price = entry.get("limit_entry")
            if limit_price is None or not (low <= float(limit_price) <= high):
                action_counts["wait"] += 1
                no_trade_counts["limit_entry_wait"] += 1
                continue
            entry_price = float(limit_price)
        else:
            entry_price = close

        entry_with_zone = dict(entry)
        if ob_zone:
            entry_with_zone["ob_zone"] = ob_zone
        sl, tp, level_reason = _build_orchestrator_trade_levels(
            symbol_info,
            direction,
            entry_price,
            entry_with_zone,
            entry_slice,
            internal_structure,
            structure_context,
            liquidity_context.get("liquidity_pools", []),
        )
        if sl is None or tp is None:
            action_counts["skip"] += 1
            no_trade_counts[f"level_build_failed:{level_reason}"] += 1
            continue
        # Phase 2: Apply displacement tier position size adjustment (default to 1.0 for backtest)
        position_size_pct = 1.0  # Backtest doesn't use orchestrator displacement tier system
        
        lot = risk_engine.calculate_position_size(
            symbol=symbol,
            account_balance=max(1.0, capital + realized_pnl),
            stop_distance_price=abs(entry_price - sl),
            risk_pct=float(score_result.get("risk_pct") or profile.get("risk_per_trade", 0.01)),
            enforce_min_volume=True,
            position_size_pct=position_size_pct,
        )
        if lot is None:
            action_counts["skip"] += 1
            no_trade_counts["risk_below_min_volume"] += 1
            continue
        if not risk_engine.validate_rr(entry_price, sl, tp):
            action_counts["skip"] += 1
            no_trade_counts["rr_below_orchestrator_minimum"] += 1
            continue

        open_positions.append(Position(
            ticket=ticket_seq,
            symbol=symbol,
            direction=direction,
            lot=float(lot),
            entry_price=float(entry_price),
            sl=float(sl),
            tp=float(tp),
            risk_price=abs(entry_price - sl),
            sl_reason=str(level_reason),
            opened_at=now_ts.to_pydatetime(),
            score=int(score_result.get("score", 0) or 0),
            grade=str(score_result.get("grade", "")),
        ))
        ticket_seq += 1
        action_counts["candidate_ready"] += 1

    final_ts = end.isoformat()
    for pos in open_positions:
        last_close = float(test_rows["close"].iloc[-1]) if not test_rows.empty else pos.entry_price
        pnl = _pnl(symbol, pos.direction, pos.lot, pos.entry_price, last_close, cost)
        total_costs += cost.round_trip(pos.lot)
        realized_pnl += pnl
        trades.append({
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "direction": pos.direction,
            "opened_at": pos.opened_at.isoformat(),
            "closed_at": final_ts,
            "entry_price": round(pos.entry_price, 5),
            "exit_price": round(last_close, 5),
            "sl": round(pos.sl, 5),
            "tp": round(pos.tp, 5),
            "risk_price": round(pos.risk_price, 5),
            "sl_reason": pos.sl_reason,
            "lot": pos.lot,
            "score": pos.score,
            "grade": pos.grade,
            "reason": "end_of_backtest",
            "pnl": round(pnl, 4),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_rows)
    trades_path = out_dir / "shadow_mode_trades.csv"
    equity_path = out_dir / "shadow_mode_equity_curve.csv"
    summary_path = out_dir / "shadow_mode_summary.json"
    trades_df.to_csv(trades_path, index=False)
    equity_df.to_csv(equity_path, index=False)

    pnl_series = trades_df["pnl"].astype(float) if not trades_df.empty else pd.Series(dtype=float)
    wins = int((pnl_series > 0).sum())
    losses = int((pnl_series < 0).sum())
    reasons = trades_df["reason"] if ("reason" in trades_df.columns) else pd.Series(dtype=str)
    tp_hit_wins = int(((reasons == "tp_hit") & (pnl_series > 0)).sum()) if not trades_df.empty else 0
    trail_profit_exits = int(((reasons != "tp_hit") & (pnl_series > 0)).sum()) if not trades_df.empty else 0
    gross_profit = float(pnl_series[pnl_series > 0].sum()) if not pnl_series.empty else 0.0
    gross_loss = float(pnl_series[pnl_series < 0].sum()) if not pnl_series.empty else 0.0
    equity_series = capital + pnl_series.cumsum() if not pnl_series.empty else pd.Series([capital])
    max_dd = float((equity_series.cummax() - equity_series).max()) if not equity_series.empty else 0.0
    summary = {
        "symbol": symbol,
        "mode": "shadow_orchestrator_all_sessions_live_synced",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "capital": float(capital),
        "closed_trades": int(len(trades_df)),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round((wins / len(trades_df)) * 100.0, 2) if len(trades_df) else 0.0,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "gross_costs": round(total_costs, 2),
        "tp_hit_wins": tp_hit_wins,
        "trail_or_other_profit_exits": trail_profit_exits,
        "win_rate_tp_only_pct": round((tp_hit_wins / len(trades_df)) * 100.0, 2) if len(trades_df) else 0.0,
        "min_rr_target": float(risk_engine.min_rr),
        "cost_model": {
            "spread_points": spread_points,
            "slippage_points": slippage_points,
            "commission_per_lot": commission_per_lot,
            "contract_size": contract_size,
        },
        "net_pnl": round(float(pnl_series.sum()) if not pnl_series.empty else 0.0, 2),
        "ending_balance": round(float(capital + (pnl_series.sum() if not pnl_series.empty else 0.0)), 2),
        "profit_factor": round(gross_profit / abs(gross_loss), 4) if gross_loss < 0 else "inf",
        "max_drawdown": round(max_dd, 2),
        "shadow_action_counts": dict(action_counts),
        "no_trade_counts": dict(no_trade_counts),
        "assumptions": [
            "All-session trading is enabled; session is context only, not a trade gate.",
            "Synthetic DXY uses the repaired DataFrame-safe basket logic and contributes to confluence scoring.",
            "Liquidity/FVG/OB payloads are normalized defensively like the live orchestrator.",
            "Entries use current SMC entry model, current confluence scorer, and current modular RiskEngine.",
            "Exits are simulated with SL/TP and end-of-backtest closure; live trailing/profit-lock may differ.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Trades saved: {trades_path}")
    print(f"Equity saved: {equity_path}")
    print(f"Summary saved: {summary_path}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSDm")
    parser.add_argument("--start", default="2026-04-01")
    parser.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--capital", type=float, default=1000.0)
    parser.add_argument("--out", default="backtests/shadow_mode")
    parser.add_argument("--trail-mode", default="live_atr_3x",
                        choices=["live_atr_3x", "1x", "1.5x", "2x", "2stage", "atr-3x"],
                        help="live_atr_3x mirrors the live bot's trailing (default).")
    parser.add_argument("--min-rr", type=float, default=None,
                        help="Override the reward-target RR; sweep to find the best target.")
    parser.add_argument("--spread-points", type=float, default=0.0,
                        help="Round-trip spread in broker points (e.g. XAU 20 = $0.20).")
    parser.add_argument("--slippage-points", type=float, default=0.0,
                        help="Per-side slippage in broker points.")
    parser.add_argument("--commission-per-lot", type=float, default=0.0,
                        help="Round-turn commission per lot in account currency.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not connect_mt5():
        raise SystemExit(1)
    if not args.verbose:
        _mute_logs()
    start = _parse_date(args.start)
    end = _parse_date(args.end) + timedelta(days=1) - timedelta(seconds=1)
    run_backtest(
        args.symbol,
        start,
        end,
        float(args.capital),
        Path(args.out),
        trail_mode=args.trail_mode,
        spread_points=args.spread_points,
        slippage_points=args.slippage_points,
        commission_per_lot=args.commission_per_lot,
        min_rr=args.min_rr,
    )


if __name__ == "__main__":
    main()
