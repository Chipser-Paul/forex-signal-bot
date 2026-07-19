# main.py  Elite 2025 (Top-Down) Version (cleaned & fixed)
from __future__ import annotations
import sys
import os

# Handle Windows console encoding issues
if sys.platform == "win32":
    try:
        import colorama
        colorama.just_fix_windows_console()
    except ImportError:
        # Fallback: set environment variable to force UTF-8
        os.environ["PYTHONIOENCODING"] = "utf-8"
        # Try to reconfigure stdout/stderr if possible
        try:
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8')
            if hasattr(sys.stderr, 'reconfigure'):
                sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

import time
import warnings
import traceback
import json
import pandas as pd # pyright: ignore[reportMissingModuleSource]
import numpy as np # pyright: ignore[reportMissingImports]
from pathlib import Path
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5  # pyright: ignore[reportMissingImports]
from trade_manager import manage_open_trades

# utils & existing modules
from utils.fetch import fetch_ohlcv
from utils.log import log
from utils.risk import calculate_lot_size
from trade_executor import execute_trade, load_open_trades, save_open_trades
from utils.connect import connect_mt5
from utils.indicators import calculate_atr
from utils.notifications import send_alert
from utils.trade_journal import log_trade_close, log_trade_event
from utils.analytics_db import record_loop_snapshot
from utils.loop_ai import queue_loop_analysis
#from trend import get_trend
from bot.execution.risk_engine import RiskEngine
from bot.state.orchestrator import StrategyOrchestrator

# 
# SMC STRATEGY ENGINE IMPORTS
# 

# Strategy state (memory between ticks)
from strategies.smc_engine.strategy_state import StrategyState

# Core SMC logic
from strategies.smc_engine.market_structure import analyze_market_structure
from strategies.smc_engine.liquidity_engine import detect_liquidity_sweep
from strategies.smc_engine.displacement_engine import detect_displacement
from strategies.smc_engine.ob_breaker_engine import detect_ob_breaker
from strategies.smc_engine.entry_model import determine_entry
import strategies.smc_engine.market_structure as market_structure_module
import strategies.smc_engine.liquidity_engine as liquidity_module
import strategies.smc_engine.displacement_engine as displacement_module
import strategies.smc_engine.ob_breaker_engine as ob_breaker_module
from utils.symbol_profiles import get_symbol_profile
from runtime.context import RuntimeContext
from runtime.loop import main_loop_once

#  CONFIG 
SYMBOLS = ["XAUUSDm", "BTCUSDm"]

TIMEFRAME = "H1"  # main timeframe for the bot loop (we fetch others as needed)
PAIR_LIMITS = {"XAUUSDm": 1, "BTCUSDm": 1}  # max open trades per symbol
LOOP_DELAY = 60
OPEN_JSON = Path("open_trades.json")
SESSION_JSON = Path("frontend") / "utils" / ".session.json"
STRATEGY_STATES = {}
SHADOW_STRATEGY_STATES = {}
SHADOW_ORCHESTRATOR = StrategyOrchestrator()
ACTIVE_ORCHESTRATOR = StrategyOrchestrator()
ACTIVE_RISK_ENGINE: RiskEngine = ACTIVE_ORCHESTRATOR.risk_engine
_last_session_mtime: float | None = None
BTC_TRADING_ENABLED = True
ACTIVE_ENGINE = os.environ.get("BOT_ACTIVE_ENGINE", "orchestrator").strip().lower()
USE_ORCHESTRATOR_LIVE = ACTIVE_ENGINE not in ("legacy", "old", "classic")

last_profit_check = datetime.now(timezone.utc).replace(
    hour=0, minute=0, second=0, microsecond=0
)


#  CAPITAL + DAILY TARGET SETTINGS 
try:
    env_capital = os.environ.get("BOT_CAPITAL")
    if env_capital is not None and str(env_capital).strip() != "":
        CAPITAL = float(env_capital)
    else:
        CAPITAL = 1_000.0
except Exception:
    log("Invalid capital -> default $1,000", "red")
    CAPITAL = 1_000.0

# Default keeps prior behavior unless dashboard session overrides it.
DAILY_TARGET_PCT = 20.0
TARGET_PROFIT = (DAILY_TARGET_PCT / 100.0) * CAPITAL
symbol_profits = {symbol: 0.0 for symbol in SYMBOLS}
previous_profits = {symbol: 0.0 for symbol in SYMBOLS}
RISK_PER_TRADE = 0.01
MIN_EXECUTION_RR = 1.2

last_profit_check = None
profit_initialized = False
daily_target_notified = set()
ACCOUNT_DAILY_TARGET_KEY = "__ACCOUNT__"

# safety lot cap derived from capital (conservative)
def max_lot_by_capital(capital: float) -> float:
    # Conservative default: 0.01 lot per $100 of capital (i.e. capital/10000)
    return max(0.01, round(capital / 10000.0, 2))


# track last tighten time per ticket to avoid spammy repeated SL changes
_last_tighten = {}  # ticket -> datetime


def close_position_immediately(symbol: str, ticket: int, direction: str, volume: float, reason: str) -> bool:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False

    close_req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "position": ticket,
        "volume": volume,
        "type": mt5.ORDER_TYPE_SELL if direction == "buy" else mt5.ORDER_TYPE_BUY,
        "price": tick.bid if direction == "buy" else tick.ask,
        "deviation": 20,
        "magic": 123456,
        "comment": reason,
    }
    res = mt5.order_send(close_req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        log_trade_close(
            ticket=ticket,
            symbol=symbol,
            exit_price=float(close_req["price"]),
            reason=reason,
            source="execution_guard",
        )
        return True
    return False


def refresh_runtime_capital() -> None:
    """Reload capital from frontend session file so runtime settings update without bot restart."""
    global CAPITAL, DAILY_TARGET_PCT, TARGET_PROFIT, _last_session_mtime, daily_target_notified, BTC_TRADING_ENABLED

    if not SESSION_JSON.exists():
        return

    try:
        mtime = SESSION_JSON.stat().st_mtime
        if _last_session_mtime is not None and mtime <= _last_session_mtime:
            return

        session = json.loads(SESSION_JSON.read_text(encoding="utf-8"))
        new_capital = float(session.get("capital", CAPITAL))
        new_daily_target_pct = float(session.get("daily_target_pct", DAILY_TARGET_PCT))
        new_btc_enabled = bool(session.get("btc_enabled", BTC_TRADING_ENABLED))

        if new_capital <= 0:
            new_capital = CAPITAL
        if new_daily_target_pct <= 0:
            new_daily_target_pct = DAILY_TARGET_PCT

        capital_changed = abs(new_capital - CAPITAL) > 1e-9
        target_pct_changed = abs(new_daily_target_pct - DAILY_TARGET_PCT) > 1e-9
        if capital_changed or target_pct_changed:
            CAPITAL = new_capital
            DAILY_TARGET_PCT = new_daily_target_pct
            TARGET_PROFIT = (DAILY_TARGET_PCT / 100.0) * CAPITAL
            daily_target_notified.clear()
            log(
                f" Runtime settings updated -> capital=${CAPITAL:.2f} "
                f"target={DAILY_TARGET_PCT:.2f}% (${TARGET_PROFIT:.2f})",
                "cyan",
            )

        if new_btc_enabled != BTC_TRADING_ENABLED:
            BTC_TRADING_ENABLED = new_btc_enabled
            log(
                " BTCUSDm trading enabled at runtime"
                if BTC_TRADING_ENABLED
                else " BTCUSDm trading disabled at runtime",
                "cyan" if BTC_TRADING_ENABLED else "yellow",
            )

        _last_session_mtime = mtime
    except Exception as exc:
        log(f"[WARN] Could not refresh runtime capital: {exc}", "yellow")


def is_symbol_trading_enabled(symbol: str) -> bool:
    if symbol == "BTCUSDm":
        return BTC_TRADING_ENABLED
    return True

def initialize_today_profit():
    global last_profit_check, profit_initialized

    utc_midnight = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    now = datetime.now(timezone.utc)

    deals = mt5.history_deals_get(utc_midnight, now)

    if deals:
        for d in deals:
            if d.symbol in symbol_profits:
                symbol_profits[d.symbol] += d.profit

    last_profit_check = now
    profit_initialized = True

#  HELPERS 
def dynamic_sl_tp(symbol, df, direction, score):
    """
    Dynamic SL/TP:
      - SL at nearest swing high/low  ATR buffer
      - TP based on SL distance  RRR (2:1 for medium, 3:1 for strong setups)
    """
    info = mt5.symbol_info(symbol)
    if info is None or df is None or df.empty:
        return None, None, False  # keep 3 values

    point = info.point
    digits = info.digits

    # ATR(14) calculation
    highs, lows, closes = df["high"].values, df["low"].values, df["close"].values
    tr = np.maximum(highs[1:], closes[:-1]) - np.minimum(lows[1:], closes[:-1])
    atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
    atr_buffer = atr * 0.5  # half ATR buffer

    recent = df.tail(20)
    swing_high = recent["high"].max()
    swing_low = recent["low"].min()
    last_close = closes[-1]

    # Risk-to-reward ratio based on score strength
    rrr = 2.0 if score <= 4 else 3.0

    if direction == "buy":
        sl = swing_low - atr_buffer
        tp = last_close + (last_close - sl) * rrr
    else:
        sl = swing_high + atr_buffer
        tp = last_close - (sl - last_close) * rrr

    return round(sl, digits), round(tp, digits), True  # always 3 values

def profit_today(update_symbol_totals=False) -> float:
    global last_profit_check, symbol_profits, previous_profits, daily_target_notified

    now = datetime.now(timezone.utc)
    utc_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Automatic day rollover reset (UTC): no bot restart needed.
    if last_profit_check is not None and last_profit_check < utc_midnight:
        symbol_profits = {symbol: 0.0 for symbol in SYMBOLS}
        previous_profits = {symbol: 0.0 for symbol in SYMBOLS}
        daily_target_notified.clear()
        last_profit_check = utc_midnight

    if last_profit_check is None:
        last_profit_check = utc_midnight

    deals = mt5.history_deals_get(last_profit_check, now)
    total = 0.0

    if deals:
        for d in deals:
            total += d.profit
            if update_symbol_totals and d.symbol in symbol_profits:
                symbol_profits[d.symbol] += d.profit

        #  CRITICAL: advance cursor
        last_profit_check = now

    return total

def show_profit_summary():
    profit_today(update_symbol_totals=True)

    log(" Daily Profit Summary", "cyan")
    for sym, current in symbol_profits.items():
        prev = previous_profits.get(sym, 0.0)
        delta = current - prev
        arrow = "" if delta > 0 else ("" if delta < 0 else "")
        color = "green" if current > 0 else ("red" if current < 0 else "yellow")

        log(f"  {sym}: ${current:.2f} ({arrow} ${abs(delta):.2f})", color)
        previous_profits[sym] = current

    total = sum(symbol_profits.values())
    log(f" Total P/L: ${total:.2f}", "cyan")


def total_profit_today() -> float:
    return float(sum(symbol_profits.values()))


def _find_recent_close_deal(ticket: int, symbol: str, lookback_days: int = 7) -> dict | None:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=lookback_days)
    deals = mt5.history_deals_get(start, now)
    if not deals:
        return None

    close_entries = {
        getattr(mt5, "DEAL_ENTRY_OUT", 1),
        getattr(mt5, "DEAL_ENTRY_OUT_BY", 3),
    }

    candidates = []
    for deal in deals:
        if getattr(deal, "symbol", None) != symbol:
            continue

        position_id = getattr(deal, "position_id", None)
        if position_id is None:
            position_id = getattr(deal, "position", None)
        if position_id is None:
            continue

        if int(position_id) != int(ticket):
            continue

        if getattr(deal, "entry", None) not in close_entries:
            continue

        candidates.append(deal)

    if not candidates:
        return None

    close_deal = max(
        candidates,
        key=lambda d: getattr(d, "time_msc", 0) or getattr(d, "time", 0),
    )

    close_ts = getattr(close_deal, "time", None)
    close_iso = None
    if close_ts:
        close_iso = datetime.fromtimestamp(close_ts, tz=timezone.utc).isoformat()

    return {
        "pnl": float(getattr(close_deal, "profit", 0.0)),
        "exit_price": float(getattr(close_deal, "price", 0.0)),
        "closed_at_utc": close_iso,
        "comment": str(getattr(close_deal, "comment", "") or ""),
        "deal_id": int(getattr(close_deal, "ticket", 0) or 0),
    }


def apply_symbol_profile(symbol: str) -> dict:
    profile = get_symbol_profile(symbol)

    global RISK_PER_TRADE, MIN_EXECUTION_RR, KILL_SWITCH_MIN_BARS_AFTER_ENTRY, KILL_SWITCH_ATR_BREAK_MULT
    RISK_PER_TRADE = float(profile.get("risk_per_trade", 0.01))
    MIN_EXECUTION_RR = float(profile.get("min_execution_rr", 1.2))
    # Reward target used to place TP and validate setups. Kept as the single
    # source of truth so the orchestrator-live path and the backtest agree.
    ACTIVE_RISK_ENGINE.min_rr = float(profile.get("min_rr", ACTIVE_RISK_ENGINE.min_rr))
    KILL_SWITCH_MIN_BARS_AFTER_ENTRY = int(profile.get("kill_switch_min_bars", 4))
    KILL_SWITCH_ATR_BREAK_MULT = float(profile.get("kill_switch_atr_break_mult", 0.15))
    PAIR_LIMITS[symbol] = int(profile.get("pair_limit", PAIR_LIMITS.get(symbol, 1)))

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


def run_shadow_orchestrator(symbol: str, open_trades) -> None:
    """
    Shadow mode:
    - runs the new orchestrator in parallel
    - keeps separate state
    - logs what it would do
    - never places or blocks live trades
    """
    shadow_state = SHADOW_STRATEGY_STATES.get(symbol)
    if shadow_state is None or shadow_state.is_expired():
        shadow_state = StrategyState()
        shadow_state.reset()
        SHADOW_STRATEGY_STATES[symbol] = shadow_state

    active_trade_count = len(open_trades.get(symbol, [])) if isinstance(open_trades.get(symbol, []), list) else 0
    try:
        result = SHADOW_ORCHESTRATOR.evaluate_symbol(
            symbol,
            shadow_state,
            account_balance=CAPITAL,
            daily_pnl=total_profit_today(),
            active_trade_count=active_trade_count,
        )
        score = (result.context.get("score") or {}).get("score")
        grade = (result.context.get("score") or {}).get("grade")
        bias = ((result.context.get("bias") or {}).get("htf_bias") or {}).get("direction")
        note = f"score={score} grade={grade}" if score is not None else "score=NA"
        log(
            f"[SHADOW] {symbol}: action={result.action} reason={result.reason} "
            f"state={result.state_name} bias={bias} {note}",
            "magenta" if result.action == "candidate_ready" else "cyan",
        )
    except Exception as exc:
        log(f"[SHADOW] {symbol}: orchestrator error -> {exc}", "yellow")


def _nearest_internal_anchor(
    direction: str,
    entry_price: float,
    internal_structure: dict | None,
    entry_df,
) -> float | None:
    candidates: list[float] = []
    internal_structure = internal_structure or {}

    for key in ("last_choch_level", "last_bos_level"):
        value = internal_structure.get(key)
        if value is not None:
            candidates.append(float(value))

    swing_lows = internal_structure.get("swing_lows") or []
    swing_highs = internal_structure.get("swing_highs") or []
    if direction == "buy":
        candidates.extend(float(s["price"]) for s in swing_lows[-6:] if "price" in s)
        if entry_df is not None and not entry_df.empty:
            candidates.append(float(entry_df["low"].tail(10).min()))
        below = [level for level in candidates if level < entry_price]
        return max(below) if below else None

    candidates.extend(float(s["price"]) for s in swing_highs[-6:] if "price" in s)
    if entry_df is not None and not entry_df.empty:
        candidates.append(float(entry_df["high"].tail(10).max()))
    above = [level for level in candidates if level > entry_price]
    return min(above) if above else None


def _pick_orchestrator_tp(
    direction: str,
    entry_price: float,
    sl: float,
    liquidity_pools: list[dict],
) -> float:
    risk_distance = abs(entry_price - sl)
    fallback = (
        entry_price + risk_distance * ACTIVE_RISK_ENGINE.min_rr
        if direction == "buy"
        else entry_price - risk_distance * ACTIVE_RISK_ENGINE.min_rr
    )
    targets = ACTIVE_RISK_ENGINE.build_tp_targets(direction, entry_price, liquidity_pools)
    if not targets:
        return fallback

    ordered_targets = [
        float(targets[key])
        for key in ("tp3", "tp2", "tp1")
        if key in targets and targets[key] is not None
    ]
    for target in ordered_targets:
        if ACTIVE_RISK_ENGINE.validate_rr(entry_price, sl, target):
            return target
    return fallback


def _execution_level_config(symbol_info) -> dict:
    symbol_name = str(getattr(symbol_info, "name", "") or "")
    profile = get_symbol_profile(symbol_name) if symbol_name else {}
    return profile.get("execution_levels", {}) if isinstance(profile, dict) else {}


def _build_orchestrator_trade_levels(
    symbol_info,
    direction: str,
    entry_price: float,
    entry: dict,
    entry_df,
    internal_structure: dict | None,
    structure_context: dict,
    liquidity_pools: list[dict],
    min_rr_buffer: float = 0.0,
) -> tuple[float | None, float | None, str]:
    sl: float | None = None
    reason = "unresolved"
    ob_zone = entry.get("ob_zone")
    level_cfg = _execution_level_config(symbol_info)
    atr_val = float(calculate_atr(entry_df, period=14) or 0.0)
    anchor_buffer = max(
        atr_val * float(level_cfg.get("anchor_buffer_atr_mult", 0.0) or 0.0),
        float(level_cfg.get("anchor_buffer_price", 0.0) or 0.0),
    )

    if entry.get("entry_mode") == "aggressive" and ob_zone:
        low, high = sorted([float(ob_zone[0]), float(ob_zone[1])])
        if direction == "buy":
            sl = low - anchor_buffer
        else:
            sl = high + anchor_buffer
        reason = "aggressive_ob_boundary"

    if sl is None:
        anchor = _nearest_internal_anchor(direction, entry_price, internal_structure, entry_df)
        if anchor is not None:
            sl = anchor - anchor_buffer if direction == "buy" else anchor + anchor_buffer
            reason = "internal_structure_anchor"

    if sl is None:
        if direction == "buy":
            discount_zone = structure_context.get("discount_zone")
            if discount_zone:
                sl = float(discount_zone[0]) - anchor_buffer
                reason = "discount_zone_floor"
        else:
            premium_zone = structure_context.get("premium_zone")
            if premium_zone:
                sl = float(premium_zone[1]) + anchor_buffer
                reason = "premium_zone_ceiling"

    if sl is None or sl <= 0:
        return None, None, "no_smc_stop_anchor"

    if direction == "buy" and sl >= entry_price:
        return None, None, f"invalid_buy_sl:{reason}"
    if direction == "sell" and sl <= entry_price:
        return None, None, f"invalid_sell_sl:{reason}"

    point = float(getattr(symbol_info, "point", 0.0) or 0.0)
    broker_min_stop = float(getattr(symbol_info, "stops_level", 0) or 10) * point
    atr_floor = atr_val * float(level_cfg.get("min_stop_atr_mult", 0.35) or 0.0) if atr_val > 0 else 0.0
    point_floor = point * float(level_cfg.get("min_stop_points", 500) or 0.0) if point > 0 else 0.0
    price_floor = float(level_cfg.get("min_stop_price", 0.0) or 0.0)
    min_stop_distance = max(broker_min_stop, atr_floor, point_floor, price_floor)
    stop_distance = abs(entry_price - sl)

    if min_stop_distance > 0 and stop_distance < min_stop_distance:
        return None, None, f"smc_stop_too_tight({stop_distance:.3f}<{min_stop_distance:.3f})"

    max_atr_ceil = atr_val * float(level_cfg.get("max_stop_atr_mult", 0.0) or 0.0) if atr_val > 0 else 0.0
    max_price_ceil = float(level_cfg.get("max_stop_price", 0.0) or 0.0)
    candidates = [v for v in (max_atr_ceil, max_price_ceil) if v > 0]
    max_stop_distance = min(candidates) if candidates else 0.0

    if max_stop_distance > 0 and stop_distance > max_stop_distance:
        return None, None, f"exceeds_max_stop({stop_distance:.1f}>{max_stop_distance:.1f})"

    if stop_distance <= 0:
        return None, None, "invalid_stop_distance"

    tp = _pick_orchestrator_tp(direction, entry_price, sl, liquidity_pools)
    if min_rr_buffer > 0:
        risk_distance = abs(entry_price - sl)
        buffered_rr = ACTIVE_RISK_ENGINE.min_rr + float(min_rr_buffer)
        if ACTIVE_RISK_ENGINE.rr_value(entry_price, sl, tp) < buffered_rr:
            tp = (
                entry_price + risk_distance * buffered_rr
                if direction == "buy"
                else entry_price - risk_distance * buffered_rr
            )
    if not ACTIVE_RISK_ENGINE.validate_rr(entry_price, sl, tp):
        return None, None, "rr_below_orchestrator_minimum"

    digits = int(getattr(symbol_info, "digits", 2) or 2)
    return round(float(sl), digits), round(float(tp), digits), reason


def _entry_price_ready_for_live_market(
    direction: str,
    entry: dict,
    current_price: float,
    entry_df,
    symbol_info,
) -> tuple[bool, str]:
    if entry.get("entry_type") != "limit":
        return True, "market_entry"

    limit_price = entry.get("limit_entry")
    if limit_price is None:
        return False, "missing_limit_price"

    limit_price = float(limit_price)
    atr_val = float(calculate_atr(entry_df, period=14) or 0.0)
    point = float(getattr(symbol_info, "point", 0.0) or 0.0)
    tolerance = max(point * 50, atr_val * 0.05)

    if direction == "buy" and current_price <= limit_price + tolerance:
        return True, "limit_price_reached"
    if direction == "sell" and current_price >= limit_price - tolerance:
        return True, "limit_price_reached"
    return False, f"waiting_for_limit:{limit_price:.5f}"


def _safe_dict(val, name=""):
    """Coerce a value to a dict. Logs a warning if the value has an unexpected type."""
    import json as _json
    from pathlib import Path as _Path
    _diag = _Path("logs/diagnostic.log")
    _diag.parent.mkdir(exist_ok=True)
    if isinstance(val, dict):
        return val
    if val is not None:
        msg = f"[SAFETY] Expected dict for '{name}', got {type(val).__name__}: {val!r}"
        log(msg, "yellow")
        with open(_diag, "a", encoding="utf-8") as _f:
            _f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")
    return {}


def execute_orchestrator_live(
    symbol: str,
    open_trades,
    *,
    trading_allowed: bool,
    account_profit_today: float,
    loop_context: dict,
    dbg,
    no_trade,
    save_loop_snapshot,
    emit_ai_commentary,
) -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    try:
        _execute_orchestrator_live_body(
            symbol, open_trades, trading_allowed=trading_allowed,
            account_profit_today=account_profit_today, loop_context=loop_context,
            dbg=dbg, no_trade=no_trade,
            save_loop_snapshot=save_loop_snapshot, emit_ai_commentary=emit_ai_commentary,
        )
    except Exception as exc:
        import traceback
        err_file = log_dir / f"orch_error_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(err_file, "w") as f:
            traceback.print_exc(file=f)
        log(f"[EXEC-ORCH] {symbol}: exception -> {exc}. Traceback saved to {err_file}", "red")
        no_trade("orchestrator_live_error", str(exc), "red")


def _execute_orchestrator_live_body(
    symbol: str,
    open_trades,
    *,
    trading_allowed: bool,
    account_profit_today: float,
    loop_context: dict,
    dbg,
    no_trade,
    save_loop_snapshot,
    emit_ai_commentary,
) -> None:
    cfg = apply_symbol_profile(symbol)
    entry_df_for_display = None
    loop_context["timeframes"] = {
        "structure_tf": cfg.get("structure_tf"),
        "entry_tf": cfg.get("entry_tf"),
        "active_engine": "orchestrator",
    }
    try:
        entry_df_for_display = fetch_ohlcv(symbol, cfg["entry_tf"], bars=cfg["entry_bars"])
        if entry_df_for_display is not None and not entry_df_for_display.empty:
            loop_context["price"] = float(entry_df_for_display["close"].iloc[-1])
    except Exception as exc:
        dbg(f"live heartbeat price fetch failed: {exc}", "", "yellow")

    pair_limit = int(PAIR_LIMITS.get(symbol, 1))
    positions = mt5.positions_get(symbol=symbol) or []
    tracked_count = len(open_trades.get(symbol, [])) if isinstance(open_trades.get(symbol, []), list) else 0
    active_trade_count = max(tracked_count, len(positions))

    if active_trade_count >= pair_limit:
        no_trade("pair_limit_reached", f"active={active_trade_count} limit={pair_limit}")
        return

    if not trading_allowed:
        no_trade(
            "daily_target_reached",
            f"account_pnl={account_profit_today:.2f} target={TARGET_PROFIT:.2f}",
            "yellow",
        )
        return

    state = STRATEGY_STATES.get(symbol)
    if state is None or state.is_expired():
        state = StrategyState()
        state.reset()
        STRATEGY_STATES[symbol] = state
        dbg("Strategy state initialized/reset", "")

    result = ACTIVE_ORCHESTRATOR.evaluate_symbol(
        symbol,
        state,
        account_balance=CAPITAL,
        daily_pnl=account_profit_today,
        active_trade_count=active_trade_count,
    )
    context = result.context or {}
    entry = _safe_dict(context.get("entry"), "entry")
    score = _safe_dict(context.get("score"), "score")
    liquidity_context = _safe_dict(context.get("liquidity"), "liquidity")
    structure_context = _safe_dict(liquidity_context.get("structure_context"), "structure_context")
    liquidity_pools = liquidity_context.get("liquidity_pools") or []
    ob_result = _safe_dict(context.get("ob"), "ob")
    liquidity_signal = _safe_dict(context.get("liquidity_signal"), "liquidity_signal")
    displacement = _safe_dict(context.get("displacement"), "displacement")
    bias_resolution = _safe_dict(context.get("bias_resolution"), "bias_resolution")

    current_price = float(entry.get("market_entry") or structure_context.get("current_price") or loop_context.get("price") or 0.0)
    loop_context["price"] = current_price or loop_context.get("price")
    loop_context["structure"] = {
        "structure": bias_resolution.get("direction") or structure_context.get("structure"),
        "state": structure_context.get("state"),
        "confidence": structure_context.get("confidence"),
        "condition": structure_context.get("condition"),
        "event": structure_context.get("event"),
        "orchestrator_state": result.state_name,
        "session": context.get("session"),
        "news": context.get("news"),
        "dxy": context.get("dxy"),
        "score": score,
    }
    loop_context["liquidity"] = liquidity_signal if isinstance(liquidity_signal, dict) else {}
    loop_context["displacement"] = displacement if isinstance(displacement, dict) else {"valid": bool(displacement)}
    loop_context["ob_breaker"] = ob_result if isinstance(ob_result, dict) else {}
    loop_context["entry"] = entry if isinstance(entry, dict) else {}
    loop_context["entry"].update(
        {
            "engine_action": result.action,
            "engine_reason": result.reason,
            "engine_state": result.state_name,
        }
    )

    log(
        f"[LIVE-ORCH] {symbol}: action={result.action} reason={result.reason} "
        f"state={result.state_name} score={score.get('score', 'NA')} grade={score.get('grade', 'NA')}",
        "green" if result.action == "candidate_ready" else "cyan",
    )

    if result.action != "candidate_ready":
        # Copy error details into loop_context so they survive into snapshots
        error_details = context.get("orchestrator_error_details")
        if error_details:
            loop_context["orchestrator_error_details"] = error_details
            log(f"[EXEC-ORCH] {symbol}: Error details saved to loop_context: {error_details}", "red")
        no_trade(result.reason, f"orchestrator action={result.action}")
        return

    direction = str(entry.get("direction", "")).lower()
    if direction not in ("buy", "sell"):
        no_trade("invalid_entry_direction", f"direction={direction}", "red")
        return

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        no_trade("symbol_info_missing", "symbol info not found", "red")
        return

    entry_df = entry_df_for_display
    if entry_df is None or entry_df.empty:
        entry_df = fetch_ohlcv(symbol, cfg["entry_tf"], bars=cfg["entry_bars"])
    if entry_df is None or entry_df.empty:
        no_trade("insufficient_entry_data", "cannot build live trade levels", "red")
        return

    signal_price = float(entry_df["close"].iloc[-1])
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        no_trade("tick_missing", "cannot price live market order", "red")
        return
    current_price = float(tick.ask if direction == "buy" else tick.bid)
    loop_context["price"] = current_price
    ready, ready_reason = _entry_price_ready_for_live_market(direction, entry, signal_price, entry_df, symbol_info)
    if not ready:
        no_trade("entry_wait", ready_reason)
        return

    entry_with_zone = dict(entry)
    if ob_result.get("valid") and ob_result.get("zone"):
        entry_with_zone["ob_zone"] = ob_result.get("zone")

    sl, tp, level_reason = _build_orchestrator_trade_levels(
        symbol_info,
        direction,
        current_price,
        entry_with_zone,
        entry_df,
        context.get("internal_structure"),
        structure_context,
        liquidity_pools,
        min_rr_buffer=0.10,
    )
    if sl is None or tp is None:
        no_trade("level_build_failed", level_reason, "red")
        return

    rr = ACTIVE_RISK_ENGINE.rr_value(current_price, sl, tp)
    if rr < ACTIVE_RISK_ENGINE.min_rr:
        no_trade("rr_below_orchestrator_minimum", f"rr={rr:.2f}", "red")
        return

    # Apply DXY-based risk reduction if needed
    dxy_context = context.get("dxy") or {}
    dxy_reduce_size = bool(dxy_context.get("reduce_size", False))
    base_risk_pct = float(score.get("risk_pct") or cfg.get("risk_per_trade", 0.01))
    risk_pct = base_risk_pct * 0.75 if dxy_reduce_size else base_risk_pct
    
    # Phase 2: Apply displacement tier position size adjustment
    displacement_tier_adjustment = context.get("displacement_tier_adjustment") or {}
    position_size_pct = float(displacement_tier_adjustment.get("position_size_pct", 1.0))
    
    lot = ACTIVE_RISK_ENGINE.calculate_position_size(
        symbol=symbol,
        account_balance=max(1.0, CAPITAL + account_profit_today),
        stop_distance_price=abs(current_price - sl),
        risk_pct=risk_pct,
        enforce_min_volume=True,
        position_size_pct=position_size_pct,  # Phase 2: Displacement tier adjustment
    )
    if lot is None:
        no_trade(
            "risk_below_min_volume",
            f"capital={CAPITAL:.2f} risk_pct={risk_pct:.4f} stop={abs(current_price - sl):.5f}",
            "yellow",
        )
        return

    rr = ACTIVE_RISK_ENGINE.rr_value(current_price, sl, tp)
    if rr < ACTIVE_RISK_ENGINE.min_rr:
        no_trade("rr_below_orchestrator_minimum", f"rr={rr:.2f}", "red")
        return

    strategy_context = {
        "strategy": "SMC_COURTROOM_ORCHESTRATOR",
        "engine_mode": "live",
        "timeframes": loop_context["timeframes"],
        "orchestrator": {
            "action": result.action,
            "reason": result.reason,
            "state_name": result.state_name,
        },
        "score": score,
        "bias": context.get("bias"),
        "bias_resolution": bias_resolution,
        "session": context.get("session"),
        "news": context.get("news"),
        "dxy": context.get("dxy"),
        "liquidity_map": liquidity_context,
        "liquidity_signal": liquidity_signal,
        "displacement_signal": displacement,
        "fvg_signal": context.get("fvgs"),
        "internal_structure": context.get("internal_structure"),
        "ob_breaker_signal": ob_result,
        "entry_signal": entry_with_zone,
        "risk_plan": {
            "risk_pct": risk_pct,
            "risk_distance": abs(current_price - sl),
            "rr_target": rr,
            "sl_reason": level_reason,
            "calculated_lot": lot,
            "executed_lot": lot,
            "min_rr": ACTIVE_RISK_ENGINE.min_rr,
        },
        "levels": {
            "price": current_price,
            "sl": sl,
            "tp": tp,
        },
        "bot_context": {
            "capital": CAPITAL,
            "daily_target_pct": DAILY_TARGET_PCT,
            "daily_target": TARGET_PROFIT,
            "account_profit_today": account_profit_today,
        },
    }

    log(
        f"[LIVE-ORCH] {symbol} MARKET {direction.upper()} | lot={lot:.2f} "
        f"SL={sl:.2f} TP={tp:.2f} RR={rr:.2f}",
        "green",
    )
    execution = execute_trade(
        symbol=symbol,
        direction=direction,
        lot=lot,
        sl=sl,
        tp=tp,
        comment="SMC-Orchestrator",
        context=strategy_context,
    )
    if not execution:
        no_trade("order_send_failed", "MT5 rejected or did not fill the order", "red")
        return

    ticket = int(execution["ticket"])
    actual_entry = float(execution["entry_price"])
    actual_sl = float(execution["sl"])
    actual_tp = float(execution["tp"])
    actual_rr = ACTIVE_RISK_ENGINE.rr_value(actual_entry, actual_sl, actual_tp)

    invalid_fill = (
        (direction == "buy" and (actual_tp <= actual_entry or actual_sl >= actual_entry))
        or (direction == "sell" and (actual_tp >= actual_entry or actual_sl <= actual_entry))
    )
    if invalid_fill or actual_rr < MIN_EXECUTION_RR:
        log(
            f" {symbol}: orchestrator execution guard closed trade "
            f"(fill={actual_entry:.3f} rr={actual_rr:.3f} min_rr={MIN_EXECUTION_RR:.2f})",
            "yellow",
        )
        log_trade_event(
            ticket=ticket,
            symbol=symbol,
            event_name="orchestrator_execution_guard_reject",
            details={
                "entry_price": actual_entry,
                "sl": actual_sl,
                "tp": actual_tp,
                "rr": actual_rr,
                "min_rr": MIN_EXECUTION_RR,
                "invalid_fill": invalid_fill,
            },
        )
        close_position_immediately(
            symbol=symbol,
            ticket=ticket,
            direction=direction,
            volume=float(execution["lot"]),
            reason="orchestrator_guard_low_rr",
        )
        no_trade("execution_guard_low_rr", f"fill_rr={actual_rr:.3f}", "yellow")
        return

    open_trades.setdefault(symbol, [])
    if not any(isinstance(t, dict) and str(t.get("ticket")) == str(ticket) for t in open_trades[symbol]):
        open_trades[symbol].append(
            {
                "ticket": ticket,
                "symbol": symbol,
                "direction": direction,
                "entry_price": actual_entry,
                "sl": actual_sl,
                "tp": actual_tp,
                "risk": abs(actual_entry - actual_sl),
                "lot": float(lot),
                "opened_at": datetime.now(timezone.utc).isoformat(),
                "confidence": structure_context.get("confidence"),
                "structure_dir": bias_resolution.get("direction"),
                "structure_state": structure_context.get("state"),
                "condition": structure_context.get("condition"),
                "liquidity_side": liquidity_signal.get("side") if isinstance(liquidity_signal, dict) else None,
                "liquidity_type": liquidity_signal.get("type") if isinstance(liquidity_signal, dict) else None,
                "ob_breaker_type": ob_result.get("type") if isinstance(ob_result, dict) else None,
                "ob_breaker_reason": ob_result.get("reason") if isinstance(ob_result, dict) else None,
                "engine": "orchestrator",
                "score": score.get("score"),
                "grade": score.get("grade"),
            }
        )
        save_open_trades(open_trades)

    save_loop_snapshot(
        "trade_opened",
        reason_code="orchestrator_executed",
        reason_text=f"opened=1 direction={direction} score={score.get('score')} rr={actual_rr}",
        tickets_opened=1,
    )
    emit_ai_commentary(
        "trade_opened",
        reason_code="orchestrator_executed",
        reason_text=f"opened=1 direction={direction} score={score.get('score')} rr={actual_rr}",
        tickets_opened=1,
    )
    log("[] ORCHESTRATOR EXECUTED SUCCESSFULLY", "green")

#  EVALUATE SYMBOL (SMC ENGINE) 
def evaluate_symbol(symbol, open_trades, debug=True):
    """Evaluate a single symbol with SMC strategy and generate a structured console report."""

    #  DAILY TARGET CHECK 
    account_profit_today = total_profit_today()
    if account_profit_today >= TARGET_PROFIT:
        log(
            f" Account daily target reached "
            f"(${account_profit_today:.2f} / ${TARGET_PROFIT:.2f})  Trading halted for all pairs",
            "yellow"
        )
        if ACCOUNT_DAILY_TARGET_KEY not in daily_target_notified:
            send_alert(
                f"Daily target reached\n"
                f"Scope: Account-wide halt\n"
                f"P/L: {account_profit_today:.2f}\n"
                f"Target: {TARGET_PROFIT:.2f}",
                title="Daily Target Reached",
            )
            daily_target_notified.add(ACCOUNT_DAILY_TARGET_KEY)
        trading_allowed = False
    else:
        trading_allowed = True

    def dbg(msg, emoji="", color="cyan"):
        if debug:
            log(f"[{emoji}] {symbol}: {msg}", color)

    loop_context = {
        "symbol": symbol,
        "price": None,
        "timeframes": {},
        "structure": {},
        "liquidity": {},
        "displacement": {},
        "ob_breaker": {},
        "entry": {},
    }
    ai_emitted = False
    snapshot_saved = False

    def save_loop_snapshot(
        final_action: str,
        reason_code: str | None = None,
        reason_text: str | None = None,
        tickets_opened: int = 0,
    ) -> None:
        nonlocal snapshot_saved
        if snapshot_saved:
            return
        snapshot_saved = True
        try:
            record_loop_snapshot(
                {
                    "symbol": symbol,
                    "price": loop_context.get("price"),
                    "timeframes": loop_context.get("timeframes"),
                    "final_action": final_action,
                    "reason_code": reason_code,
                    "reason_text": reason_text,
                    "tickets_opened": tickets_opened,
                    "structure": loop_context.get("structure"),
                    "liquidity": loop_context.get("liquidity"),
                    "displacement": loop_context.get("displacement"),
                    "ob_breaker": loop_context.get("ob_breaker"),
                    "entry": loop_context.get("entry"),
                    "orchestrator_error_details": loop_context.get("orchestrator_error_details"),
                }
            )
        except Exception:
            pass

    def emit_ai_commentary(
        final_action: str,
        reason_code: str | None = None,
        reason_text: str | None = None,
        tickets_opened: int = 0,
    ) -> None:
        nonlocal ai_emitted
        if ai_emitted:
            return
        ai_emitted = True
        queue_loop_analysis(
            {
                "symbol": symbol,
                "price": loop_context.get("price"),
                "timeframes": loop_context.get("timeframes"),
                "final_action": final_action,
                "reason_code": reason_code,
                "reason_text": reason_text,
                "tickets_opened": tickets_opened,
                "structure": loop_context.get("structure"),
                "liquidity": loop_context.get("liquidity"),
                "displacement": loop_context.get("displacement"),
                "ob_breaker": loop_context.get("ob_breaker"),
                "entry": loop_context.get("entry"),
                "orchestrator_error_details": loop_context.get("orchestrator_error_details"),
            }
        )

    def no_trade(code: str, reason: str, color: str = "yellow") -> None:
        dbg(f"[NO_TRADE] code={code} reason={reason}", "", color)
        save_loop_snapshot("no_trade", code, reason, tickets_opened=0)
        emit_ai_commentary("no_trade", code, reason, tickets_opened=0)

    if USE_ORCHESTRATOR_LIVE:
        try:
            execute_orchestrator_live(
                symbol,
                open_trades,
                trading_allowed=trading_allowed,
                account_profit_today=account_profit_today,
                loop_context=loop_context,
                dbg=dbg,
                no_trade=no_trade,
                save_loop_snapshot=save_loop_snapshot,
                emit_ai_commentary=emit_ai_commentary,
            )
        except Exception as exc:
            err_msg = str(exc)
            log(f"[LIVE-ORCH] {symbol}: orchestrator live error -> {err_msg}", "red")
            traceback.print_exc()
            no_trade("orchestrator_live_error", err_msg, "red")
        return

    # -------------------------------------------------
    # 1 Fetch data (PER STRATEGY TIMEFRAMES)
    # -------------------------------------------------
    cfg = apply_symbol_profile(symbol)

    df_structure = fetch_ohlcv(symbol, cfg["structure_tf"], bars=cfg["structure_bars"])
    df_entry = fetch_ohlcv(symbol, cfg["entry_tf"], bars=cfg["entry_bars"])
    support_tf = cfg.get("support_bias_tf")
    support_bars = int(cfg.get("support_bias_bars", 0) or 0)
    df_support = (
        fetch_ohlcv(symbol, support_tf, bars=support_bars)
        if support_tf and support_bars > 0
        else None
    )

    if df_structure is None or df_structure.empty or df_entry is None or df_entry.empty:
        no_trade("insufficient_data", "insufficient SMC data", "red")
        return

    price = float(df_entry["close"].iloc[-1])
    loop_context["price"] = float(price)
    loop_context["timeframes"] = {
        "structure_tf": cfg["structure_tf"],
        "entry_tf": cfg["entry_tf"],
    }

    print()
    log(f"[{symbol}] {''*20}", "cyan")
    dbg(f"Latest price ({cfg['entry_tf']}) = {price:.4f}", "")
    dbg(f"SMC TFs  Structure: {cfg['structure_tf']} | Entry: {cfg['entry_tf']}", "")

    # -------------------------------------------------
    # 2 Strategy state (persistent)
    # -------------------------------------------------
    state = STRATEGY_STATES.get(symbol)
    if state is None or state.is_expired():
        state = StrategyState()
        state.reset()
        STRATEGY_STATES[symbol] = state
        dbg("Strategy state initialized/reset", "")

    run_shadow_orchestrator(symbol, open_trades)

    # -------------------------------------------------
    # 3 Market Structure (HTF) + STATE + CONFIDENCE
    # -------------------------------------------------
    structure = analyze_market_structure(df_structure, state, support_df=df_support)

    if not structure:
        no_trade("no_structure", "no valid market structure")
        return

    structure_dir = structure.get("structure")
    structure_state = structure.get("state")
    confidence = structure.get("confidence", 0)
    condition = structure.get("condition", "unknown")
    structure_event = structure.get("event")
    loop_context["structure"] = {
        "structure": structure_dir,
        "state": structure_state,
        "confidence": confidence,
        "condition": condition,
        "event": structure_event,
    }

    dbg(
        f"Market Bias: {structure_dir.upper()} | State: {structure_state.upper()} | Confidence: {confidence}%",
        "",
        "green" if structure_state == "confirmed" else "yellow",
    )

    #  HARD FILTER
    if structure_state != "confirmed" or confidence < 65:
        no_trade(
            "structure_unconfirmed",
            f"state={structure_state} confidence={confidence}",
            "yellow",
        )
        return

    state.update_structure(structure_dir, structure_state)

    # -------------------------------------------------
    # 4 Liquidity Sweep (HTF)
    # -------------------------------------------------
    liquidity = detect_liquidity_sweep(
        df_structure,
        structure_dir=structure_dir,
        lookback=int(cfg.get("liquidity", {}).get("lookback", 20))
    )

    if not liquidity:
        no_trade("no_liquidity_sweep", "no liquidity sweep yet")
        return

    # Extract fields from liquidity dict
    liquidity_side = liquidity.get("side")       # 'buy' or 'sell'
    liquidity_type = liquidity.get("type")       # 'equal_highs', 'internal_continuation', etc.
    loop_context["liquidity"] = {
        "side": liquidity_side,
        "type": liquidity_type,
        "classification": liquidity.get("classification"),
        "confidence": liquidity.get("confidence"),
    }

    #  Safety: ensure liquidity side is valid
    if liquidity_side not in ("buy", "sell"):
        no_trade("invalid_liquidity_side", f"side={liquidity_side}", "red")
        return

    # -------------------------------------------------
    #  Condition-aware entry filters (optional)
    # -------------------------------------------------
    if condition == "low_vol":
        no_trade("condition_block", "condition=low_vol", "yellow")
        return

    if condition == "range" and liquidity_type not in ("equal_highs", "equal_lows"):
        no_trade("condition_block", f"condition=range type={liquidity_type}", "yellow")
        return

    if condition == "vol_expansion" and structure_event != "BOS":
        no_trade("condition_block", f"condition=vol_expansion event={structure_event}", "yellow")
        return

    # Optional professional filter:
    # Skip weak trend-continuation fallback trades if needed
    if liquidity_type == "trend_continuation":
        dbg(" Trend-continuation liquidity  can be filtered if desired", "blue")

    # Update state properly
    state.update_liquidity(
        side=liquidity_side,
        index=liquidity["index"],
        liquidity_type=liquidity_type
    )
    state.liquidity_time = df_structure.index[-1]

    # Debug log for verification
    #dbg(f"DEBUG  side={state.liquidity_side}, type={state.liquidity_type}", "cyan")

    # -------------------------------------------------
    # 5 Displacement (LTF, DIRECTIONAL)
    # -------------------------------------------------
    displacement = detect_displacement(
        df_entry,
        structure_dir,
        atr_period=14,
        impulse_atr_mult=float(cfg.get("displacement", {}).get("impulse_atr_mult", 1.2)),
        lookback_candles=int(cfg.get("displacement", {}).get("lookback_candles", 3)),
    )

    displacement_valid = False
    fvg = None
    if isinstance(displacement, dict):
        displacement_valid = bool(displacement.get("valid"))
        fvg = displacement.get("fvg")
    elif displacement:
        displacement_valid = True

    if displacement_valid:
        state.update_displacement(fvg)
        loop_context["displacement"] = {
            "valid": True,
            "direction": structure_dir,
            "fvg_present": bool(fvg),
            "strength": (
                displacement.get("strength")
                if isinstance(displacement, dict)
                else None
            ),
        }
        dbg(
            f"Displacement     :  {structure_dir.upper()} CONFIRMATION | FVG={'Yes' if fvg else 'No'}",
            "",
            "green",
        )
    else:
        no_trade("no_displacement", "no valid displacement yet")
        return

    # -------------------------------------------------
    # 6 OB/Breaker Validation (LTF)
    # -------------------------------------------------
    ob_breaker = detect_ob_breaker(
        df_entry,
        structure_dir=structure_dir,
        lookback=int(cfg.get("ob_breaker", {}).get("lookback", 30)),
        search_back=int(cfg.get("ob_breaker", {}).get("search_back", 12)),
    )
    if not isinstance(ob_breaker, dict):
        no_trade("ob_breaker_invalid", "invalid ob_breaker payload", "red")
        return

    if not ob_breaker.get("valid"):
        no_trade(
            "ob_breaker_invalid",
            f"type={ob_breaker.get('type')} reason={ob_breaker.get('reason')}",
        )
        return

    ob_type = str(ob_breaker.get("type", "unknown"))
    ob_reason = str(ob_breaker.get("reason", "aligned"))
    ob_zone = ob_breaker.get("zone")
    loop_context["ob_breaker"] = {
        "valid": True,
        "type": ob_type,
        "reason": ob_reason,
        "zone": ob_zone,
    }
    dbg(
        f"OB/Breaker       : {ob_type.upper()} | {ob_reason} | zone={ob_zone}",
        "",
        "green",
    )

    # -------------------------------------------------
    # 7 Entry Decision (SMC Engine)
    # -------------------------------------------------
    entry = determine_entry(symbol=symbol, state=state, current_price=price)

    if not entry:
        no_trade("entry_wait", "entry model says WAIT")
        return

    direction = entry["direction"]
    loop_context["entry"] = {
        "direction": direction,
        "entry_type": entry.get("entry_type"),
        "reason": entry.get("reason"),
    }

    # -------------------------------------------------
    # 8 Duplicate position check
    # -------------------------------------------------
    positions = mt5.positions_get(symbol=symbol) or []
    for pos in positions:
        if direction == "buy" and pos.type == mt5.ORDER_TYPE_BUY:
            no_trade("duplicate_position", "already have BUY position")
            return
        if direction == "sell" and pos.type == mt5.ORDER_TYPE_SELL:
            no_trade("duplicate_position", "already have SELL position")
            return
        
    # -------------------------------------------------
    # 9 Stop Loss & Take Profit (SMC + ATR HYBRID)
    # -------------------------------------------------
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        no_trade("symbol_info_missing", "symbol info not found", "red")
        return

    point = symbol_info.point

    # -------------------------------------------------
    #  STOP LOSS  STRUCTURE + ATR BUFFER (KEY FIX)
    # -------------------------------------------------
    atr_val = calculate_atr(df_entry, period=14)
    if atr_val <= 0:
        no_trade("invalid_atr", f"atr={atr_val}", "red")
        return

    # ATR buffer gives the trade room to breathe
    atr_buffer = atr_val * 0.8   #  GOLD SWEET SPOT (0.71.0)

    # 1 Structure anchor (SMC)
    if direction == "buy":
        structure_sl = df_entry["low"].iloc[-6:].min()
        sl = structure_sl - atr_buffer
    else:  # SELL
        structure_sl = df_entry["high"].iloc[-6:].max()
        sl = structure_sl + atr_buffer

    # -------------------------------------------------
    #  HARD SL VALIDATION
    # -------------------------------------------------
    if direction == "buy" and sl >= price:
        no_trade("invalid_sl", f"buy sl={sl:.5f} price={price:.5f}", "red")
        return

    if direction == "sell" and sl <= price:
        no_trade("invalid_sl", f"sell sl={sl:.5f} price={price:.5f}", "red")
        return

    # -------------------------------------------------
    #  Broker minimum stop distance (SAFE)
    # -------------------------------------------------
    try:
        min_stop_points = symbol_info.stops_level
    except AttributeError:
        min_stop_points = None

    if not min_stop_points or min_stop_points <= 0:
        min_stop_points = 10  # safe fallback

    min_stop_distance = min_stop_points * point
    stop_distance = abs(price - sl)

    if stop_distance <= min_stop_distance:
        no_trade(
            "sl_too_tight",
            f"stop_distance={stop_distance:.5f} min={min_stop_distance:.5f}",
            "red",
        )
        return

    # -------------------------------------------------
    #  TAKE PROFIT  RR FIRST (SMC-CORRECT)
    # -------------------------------------------------
    rr = 2.0  #  SAFE BASE RR (can scale later)
    tp = None

    if direction == "buy":
        tp = price + stop_distance * rr
    else:  # SELL
        tp = price - stop_distance * rr

    # -------------------------------------------------
    #  TP VALIDATION (NO ENTRY-LEVEL TP EVER)
    # -------------------------------------------------
    buffer = 2 * point

    if direction == "buy" and tp <= price + buffer:
        no_trade("invalid_tp", f"buy tp={tp:.5f} price={price:.5f}", "red")
        return

    if direction == "sell" and tp >= price - buffer:
        no_trade("invalid_tp", f"sell tp={tp:.5f} price={price:.5f}", "red")
        return

    # -------------------------------------------------
    # 10 Lot sizing (CONFIDENCE-ADAPTIVE + CAPITAL SAFE)
    # -------------------------------------------------
    risk = RISK_PER_TRADE

    # Raw lot from risk model
    stop_distance_price = abs(price - sl)
    calculated_lot = calculate_lot_size(
        symbol=symbol,
        capital=CAPITAL,
        risk_per_trade=risk,
        stop_pips=stop_distance_price,
    )
    if calculated_lot is None:
        no_trade("lot_calc_failed", "risk model returned no lot size", "red")
        return

    #  Capital-based hard cap
    capital_lot_cap = max_lot_by_capital(CAPITAL)

    #  Symbol broker constraints
    broker_lot_cap = min(symbol_info.volume_max, 0.10)

    #  Final enforced lot
    # Use capital-based sizing as primary execution model and keep risk-model lot as diagnostic.
    requested_lot = capital_lot_cap
    full_lot = round(
        min(requested_lot, broker_lot_cap),
        2
    )

    # Optional safety log (shows when risk model and capital model diverge)
    if abs(calculated_lot - full_lot) >= 0.01:
        log(
            f" Lot model: risk={calculated_lot:.2f} capital={capital_lot_cap:.2f} -> execute={full_lot:.2f}",
            "yellow"
        )

    # Final minimum-volume check
    if full_lot < symbol_info.volume_min:
        no_trade(
            "lot_too_small",
            f"lot={full_lot:.2f} min_lot={symbol_info.volume_min:.2f}",
            "red",
        )
        return

    # -------------------------------------------------
    #  Execute market entry
    # -------------------------------------------------
    tickets = []

    strategy_context = {
        "strategy": "SMC_ENGINE",
        "timeframes": {
            "structure_tf": cfg["structure_tf"],
            "entry_tf": cfg["entry_tf"],
        },
        "market_bias": {
            "structure": structure_dir,
            "state": structure_state,
            "confidence": confidence,
            "condition": condition,
        },
        "structure_signal": structure,
        "liquidity_signal": liquidity,
        "displacement_signal": (
            displacement if isinstance(displacement, dict) else {"valid": bool(displacement)}
        ),
        "ob_breaker_signal": ob_breaker,
        "entry_signal": entry,
        "risk_plan": {
            "risk_per_trade": risk,
            "rr_target": rr,
            "risk_distance": abs(price - sl),
            "atr_value": float(atr_val),
            "atr_buffer": float(atr_buffer),
            "calculated_lot": float(calculated_lot),
            "capital_lot_cap": float(capital_lot_cap),
            "broker_lot_cap": float(broker_lot_cap),
            "full_lot": float(full_lot),
            "executed_lot": float(full_lot),
        },
        "levels": {
            "price": float(price),
            "sl": float(sl),
            "tp": float(tp),
        },
        "state_snapshot": {
            "structure_dir": getattr(state, "structure_dir", None),
            "structure_state": getattr(state, "structure_state", None),
            "liquidity_side": getattr(state, "liquidity_side", None),
            "liquidity_type": getattr(state, "liquidity_type", None),
            "displacement_confirmed": bool(getattr(state, "displacement_confirmed", False)),
            "fvg_zone": getattr(state, "fvg_zone", None),
            "ob_breaker_type": ob_type,
            "ob_breaker_reason": ob_reason,
        },
        "bot_context": {
            "capital": CAPITAL,
            "daily_target_pct": DAILY_TARGET_PCT,
            "daily_target": TARGET_PROFIT,
            "symbol_profit_today": symbol_profits.get(symbol, 0.0),
        },
    }

    if trading_allowed:
        log(f"[] {symbol} MARKET {direction.upper()} | lot={full_lot}", "green")
        execution = execute_trade(
            symbol=symbol,
            direction=direction,
            lot=full_lot,
            sl=sl,
            tp=tp,
            comment="SMC-Market",
            context=strategy_context,
        )

        if execution:
            ticket = int(execution["ticket"])
            actual_entry = float(execution["entry_price"])
            actual_sl = float(execution["sl"])
            actual_tp = float(execution["tp"])
            actual_risk = abs(actual_entry - actual_sl)
            actual_reward = (
                (actual_tp - actual_entry)
                if direction == "buy"
                else (actual_entry - actual_tp)
            )
            actual_rr = (actual_reward / actual_risk) if actual_risk > 0 else 0.0

            invalid_fill = (
                (direction == "buy" and actual_tp <= actual_entry)
                or (direction == "sell" and actual_tp >= actual_entry)
                or (direction == "buy" and actual_sl >= actual_entry)
                or (direction == "sell" and actual_sl <= actual_entry)
            )
            if invalid_fill or actual_rr < MIN_EXECUTION_RR:
                log(
                    f" {symbol}: execution guard closed trade "
                    f"(fill={actual_entry:.3f} rr={actual_rr:.3f} min_rr={MIN_EXECUTION_RR:.2f})",
                    "yellow",
                )
                log_trade_event(
                    ticket=ticket,
                    symbol=symbol,
                    event_name="execution_guard_reject",
                    details={
                        "entry_price": actual_entry,
                        "sl": actual_sl,
                        "tp": actual_tp,
                        "rr": round(actual_rr, 4),
                        "min_rr": MIN_EXECUTION_RR,
                        "invalid_fill": invalid_fill,
                    },
                )
                close_position_immediately(
                    symbol=symbol,
                    ticket=ticket,
                    direction=direction,
                    volume=float(execution["lot"]),
                    reason="execution_guard_low_rr",
                )
                no_trade(
                    "execution_guard_low_rr",
                    f"fill_rr={actual_rr:.3f} min_rr={MIN_EXECUTION_RR:.2f}",
                    "yellow",
                )
                return

            tickets.append(ticket)
            open_trades.setdefault(symbol, [])
            if not any(
                isinstance(t, dict) and str(t.get("ticket")) == str(ticket)
                for t in open_trades[symbol]
            ):
                open_trades[symbol].append(
                    {
                        "ticket": int(ticket),
                        "symbol": symbol,
                        "direction": direction,
                        "entry_price": actual_entry,
                        "sl": actual_sl,
                        "tp": actual_tp,
                        "risk": actual_risk,
                        "lot": float(full_lot),
                        "opened_at": datetime.now(timezone.utc).isoformat(),
                        "confidence": confidence,
                        "structure_dir": structure_dir,
                        "structure_state": structure_state,
                        "condition": condition,
                        "liquidity_side": liquidity_side,
                        "liquidity_type": liquidity_type,
                        "ob_breaker_type": ob_type,
                        "ob_breaker_reason": ob_reason,
                    }
                )
                save_open_trades(open_trades)
    else:
        log(f" {symbol}: Trade blocked (account daily target reached)", "yellow")
        no_trade(
            "daily_target_reached",
            f"account_pnl={account_profit_today:.2f} target={TARGET_PROFIT:.2f}",
            "yellow",
        )

    # -------------------------------------------------
    #  Summary
    # -------------------------------------------------
    print()
    log(f"[{symbol}] {''*20}", "cyan")
    log(f" Bias: {structure_dir.upper()} | Confidence: {confidence}% | CONFIRMED", "yellow")
    entry_text = f"PARTIAL {direction.upper()}" if trading_allowed else "BLOCKED (Daily Target)"
    log(f" Entry: {entry_text}", "green" if trading_allowed else "yellow")
    log(f" Trades opened: {len(tickets)}", "cyan")
    save_loop_snapshot(
        "trade_opened" if tickets else "trade_ready_no_fill",
        reason_code="executed" if tickets else "no_fill",
        reason_text=(
            f"opened={len(tickets)} direction={direction}"
            if tickets
            else f"no ticket opened after valid setup direction={direction}"
        ),
        tickets_opened=len(tickets),
    )
    emit_ai_commentary(
        "trade_opened" if tickets else "trade_ready_no_fill",
        reason_code="executed" if tickets else "no_fill",
        reason_text=(
            f"opened={len(tickets)} direction={direction}"
            if tickets
            else f"no ticket opened after valid setup direction={direction}"
        ),
        tickets_opened=len(tickets),
    )
    log("[] EXECUTED SUCCESSFULLY", "green")
    print()

#  MONITOR TRADES (SMC Engine: Partial TP + BOS Trail + Kill-Switch) 

PARTIAL_CLOSE_RATIO = 0.5      # 50% at 1R
# BE_OFFSET_PIPS removed — ATR-3x trailing handles all SL management
HTF_TF = "H1"
KILL_SWITCH_MIN_BARS_AFTER_ENTRY = 4
KILL_SWITCH_ATR_BREAK_MULT = 0.15

def monitor_trades(open_trades):
    updated = {}
    positions = {p.ticket: p for p in (mt5.positions_get() or [])}

    for sym, trades in open_trades.items():
        apply_symbol_profile(sym)
        trades = trades if isinstance(trades, list) else [trades]
        keep = []

        for trade in trades:
            if not isinstance(trade, dict):
                continue

            ticket = trade.get("ticket")
            if ticket is None:
                continue
            ticket = int(ticket)
            if ticket not in positions:
                close_data = _find_recent_close_deal(ticket, sym)
                if close_data:
                    log_trade_close(
                        ticket=ticket,
                        symbol=sym,
                        pnl=close_data.get("pnl"),
                        exit_price=close_data.get("exit_price"),
                        reason=close_data.get("comment") or "position_closed",
                        source="monitor_trades_history",
                        closed_at_utc=close_data.get("closed_at_utc"),
                        details={"deal_id": close_data.get("deal_id")},
                    )
                else:
                    log_trade_close(
                        ticket=ticket,
                        symbol=sym,
                        reason="position_not_found",
                        source="monitor_trades",
                        details={"note": "position missing and no close deal found in lookback"},
                    )
                continue  # position already closed

            pos = positions[ticket]
            info = mt5.symbol_info(sym)
            tick = mt5.symbol_info_tick(sym)

            if not info or not tick:
                keep.append(trade)
                continue

            point = info.point
            digits = info.digits

            direction = trade.get("direction")
            entry = trade.get("entry_price")
            risk = trade.get("risk")

            if not direction or entry is None or risk is None:
                keep.append(trade)
                continue

            price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

            #
            # 1 PARTIAL TP AT 1R
            #
            if not trade.get("partial_taken"):
                reached_1r = (
                    price >= entry + risk
                    if direction == "buy"
                    else price <= entry - risk
                )

                if reached_1r:
                    close_volume = round(pos.volume * PARTIAL_CLOSE_RATIO, 2)

                    if close_volume >= pos.volume or close_volume < info.volume_min:
                        # Can't split — let ATR-3x trailing manage the full position
                        trade["partial_taken"] = True
                        log(f" 1R reached on min-lot {sym} — ATR trailing manages exit", "cyan")
                    elif close_volume >= info.volume_min:
                        close_req = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": sym,
                            "position": ticket,
                            "volume": close_volume,
                            "type": mt5.ORDER_TYPE_SELL if direction == "buy" else mt5.ORDER_TYPE_BUY,
                            "price": price,
                            "deviation": 20,
                            "magic": 123456,
                            "comment": "Partial TP 1R",
                        }

                        res = mt5.order_send(close_req)

                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            log(f" Partial TP hit (1R)  {sym}", "green")
                            trade["partial_taken"] = True
                            log_trade_event(
                                ticket=ticket,
                                symbol=sym,
                                event_name="partial_tp_hit",
                                details={
                                    "close_volume": close_volume,
                                    "remaining_volume": round(max(pos.volume - close_volume, 0.0), 2),
                                    "price": float(price),
                                    "trigger": "1R",
                                },
                            )
                            # SL management handled by ATR-3x trailing below

            # 
            # 2 STRUCTURE FAILURE KILL-SWITCH (FIXED)
            # 
            entry_df = fetch_ohlcv(sym, "M15", bars=10)

            structure_failed = False
            if entry_df is not None and len(entry_df) >= 7:
                # Exclude currently forming candle to avoid noisy intra-candle exits.
                closed_df = entry_df.iloc[:-1].copy()

                if len(closed_df) >= 4:
                    skip_kill_switch = False

                    # Ignore first few M15 bars after entry to let the trade breathe.
                    opened_at = trade.get("opened_at")
                    if opened_at:
                        try:
                            opened_dt = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
                            if opened_dt.tzinfo is None:
                                opened_dt = opened_dt.replace(tzinfo=timezone.utc)

                            last_closed_time = closed_df["time"].iloc[-1]
                            if hasattr(last_closed_time, "to_pydatetime"):
                                last_closed_time = last_closed_time.to_pydatetime()
                            if last_closed_time.tzinfo is None:
                                last_closed_time = last_closed_time.replace(tzinfo=timezone.utc)

                            bars_since_entry = int(
                                max(0, (last_closed_time - opened_dt).total_seconds()) // (15 * 60)
                            )
                            if bars_since_entry < KILL_SWITCH_MIN_BARS_AFTER_ENTRY:
                                skip_kill_switch = True
                        except Exception:
                            pass

                    if not skip_kill_switch:
                        # Require a meaningful break beyond structure level (ATR buffer).
                        atr_val = calculate_atr(closed_df, period=14)
                        break_buffer = atr_val * KILL_SWITCH_ATR_BREAK_MULT if atr_val > 0 else 0.0

                        c1 = closed_df.iloc[-4]
                        c2 = closed_df.iloc[-3]
                        c3 = closed_df.iloc[-2]
                        c4 = closed_df.iloc[-1]

                        if direction == "buy":
                            level1 = min(c1["low"], c2["low"])
                            level2 = min(c2["low"], c3["low"])
                            break1 = c3["close"] < (level1 - break_buffer)
                            break2 = c4["close"] < (level2 - break_buffer)
                            structure_failed = bool(break1 and break2)
                        else:
                            level1 = max(c1["high"], c2["high"])
                            level2 = max(c2["high"], c3["high"])
                            break1 = c3["close"] > (level1 + break_buffer)
                            break2 = c4["close"] > (level2 + break_buffer)
                            structure_failed = bool(break1 and break2)

                if structure_failed:
                    log(f" KILL-SWITCH  Structure failure {sym}", "red")

                    close_req = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": sym,
                        "position": ticket,
                        "volume": pos.volume,
                        "type": mt5.ORDER_TYPE_SELL if direction == "buy" else mt5.ORDER_TYPE_BUY,
                        "price": tick.bid if direction == "buy" else tick.ask,
                        "deviation": 20,
                        "magic": 123456,
                        "comment": "SMC Kill-switch",
                    }

                    close_res = mt5.order_send(close_req)
                    if close_res and close_res.retcode == mt5.TRADE_RETCODE_DONE:
                        log_trade_close(
                            ticket=ticket,
                            symbol=sym,
                            pnl=float(getattr(pos, "profit", 0.0)),
                            exit_price=float(close_req["price"]),
                            reason="kill_switch_structure_failure",
                            source="monitor_trades",
                        )
                        continue
                    keep.append(trade)
                    continue

            #
            # 3 ATR-3x TRAILING SL
            #
            trail_cfg = get_symbol_profile(sym).get("trailing", {})
            trail_mode = trail_cfg.get("mode", "htf_bos")

            if trail_mode == "atr_3x":
                trail_atr_mult = float(trail_cfg.get("atr_mult", 3.0))
                trail_min_pts = float(trail_cfg.get("min_distance_points", 100)) * point

                m5_df = fetch_ohlcv(sym, "M5", bars=20)
                if m5_df is not None and len(m5_df) >= 15:
                    m5_atr = calculate_atr(m5_df, period=14)
                    if m5_atr > 0:
                        trail_dist = max(m5_atr * trail_atr_mult, trail_min_pts)
                        mid = (tick.bid + tick.ask) / 2

                        if direction == "buy":
                            prev_peak = trade.get("peak_price")
                            if prev_peak is None or mid > prev_peak:
                                trade["peak_price"] = mid
                            new_sl = trade["peak_price"] - trail_dist
                            if (pos.sl is None or new_sl > pos.sl) and new_sl >= entry:
                                mt5.order_send({
                                    "action": mt5.TRADE_ACTION_SLTP,
                                    "symbol": sym,
                                    "position": ticket,
                                    "sl": round(new_sl, digits),
                                    "tp": pos.tp,
                                })
                                log_trade_event(
                                    ticket=ticket,
                                    symbol=sym,
                                    event_name="trail_sl_update",
                                    details={"new_sl": round(new_sl, digits), "mode": "atr_3x"},
                                )
                        else:  # sell
                            prev_peak = trade.get("peak_price")
                            if prev_peak is None or mid < prev_peak:
                                trade["peak_price"] = mid
                            new_sl = trade["peak_price"] + trail_dist
                            if (pos.sl is None or new_sl < pos.sl) and new_sl <= entry:
                                mt5.order_send({
                                    "action": mt5.TRADE_ACTION_SLTP,
                                    "symbol": sym,
                                    "position": ticket,
                                    "sl": round(new_sl, digits),
                                    "tp": pos.tp,
                                })
                                log_trade_event(
                                    ticket=ticket,
                                    symbol=sym,
                                    event_name="trail_sl_update",
                                    details={"new_sl": round(new_sl, digits), "mode": "atr_3x"},
                                )

            #
            # 4 HTF BOS CONFIRMATION
            #
            if trade.get("partial_taken") and not trade.get("htf_bos_confirmed"):
                htf_df = fetch_ohlcv(sym, HTF_TF, bars=3)
                if htf_df is not None and len(htf_df) >= 2:
                    if (
                        direction == "buy"
                        and htf_df["high"].iloc[-1] > htf_df["high"].iloc[-2]
                    ):
                        trade["htf_bos_confirmed"] = True
                        log(f" HTF BOS confirmed  {sym}", "blue")
                        log_trade_event(
                            ticket=ticket,
                            symbol=sym,
                            event_name="htf_bos_confirmed",
                            details={"direction": direction, "tf": HTF_TF},
                        )

                    if (
                        direction == "sell"
                        and htf_df["low"].iloc[-1] < htf_df["low"].iloc[-2]
                    ):
                        trade["htf_bos_confirmed"] = True
                        log(f" HTF BOS confirmed  {sym}", "blue")
                        log_trade_event(
                            ticket=ticket,
                            symbol=sym,
                            event_name="htf_bos_confirmed",
                            details={"direction": direction, "tf": HTF_TF},
                        )

            #
            # 5 HTF STRUCTURE TRAILING SL
            # 
            if trade.get("htf_bos_confirmed"):
                htf_df = fetch_ohlcv(sym, HTF_TF, bars=5)
                if htf_df is not None:
                    if direction == "buy":
                        new_sl = htf_df["low"].iloc[-2]
                        if pos.sl is None or new_sl > pos.sl:
                            mt5.order_send({
                                "action": mt5.TRADE_ACTION_SLTP,
                                "symbol": sym,
                                "position": ticket,
                                "sl": round(new_sl, digits),
                                "tp": pos.tp,
                            })
                            log_trade_event(
                                ticket=ticket,
                                symbol=sym,
                                event_name="trail_sl_update",
                                details={"new_sl": round(new_sl, digits), "tf": HTF_TF},
                            )
                    else:
                        new_sl = htf_df["high"].iloc[-2]
                        if pos.sl is None or new_sl < pos.sl:
                            mt5.order_send({
                                "action": mt5.TRADE_ACTION_SLTP,
                                "symbol": sym,
                                "position": ticket,
                                "sl": round(new_sl, digits),
                                "tp": pos.tp,
                            })
                            log_trade_event(
                                ticket=ticket,
                                symbol=sym,
                                event_name="trail_sl_update",
                                details={"new_sl": round(new_sl, digits), "tf": HTF_TF},
                            )

            keep.append(trade)

        if keep:
            updated[sym] = keep

    if updated != open_trades:
        save_open_trades(updated)

    return updated

#  ENTRYPOINT 
if __name__ == "__main__":
    if not connect_mt5():
        log(" MT5 connection failed. Exiting.", "red")
        raise SystemExit(1)

    open_trades = load_open_trades()
    # normalize format
    for k, v in list(open_trades.items()):
        if isinstance(v, int):
            open_trades[k] = [v]

    log(
        " Strategy Bot started "
        f"({'SMC_Courtroom_Orchestrator' if USE_ORCHESTRATOR_LIVE else 'Legacy_SMC_Engine'})",
        "cyan",
    )

    initialize_today_profit()

    def _evaluate_symbol_safe(sym: str, state_open_trades: dict) -> None:
        try:
            evaluate_symbol(sym, state_open_trades)
        except Exception as e:
            log(f"[] evaluate_symbol error for {sym}: {e}", "red")
            traceback.print_exc()

    def _manage_open_trades_safe(sym: str, state_open_trades: dict, *, lock_tiers) -> None:
        try:
            manage_open_trades(sym, state_open_trades, lock_tiers=lock_tiers)
        except Exception as e:
            log(f"[] manage_open_trades error for {sym}: {e}", "red")

    runtime_ctx = RuntimeContext(
        symbols=SYMBOLS,
        loop_delay=LOOP_DELAY,
        is_symbol_enabled=is_symbol_trading_enabled,
        refresh_runtime_settings=refresh_runtime_capital,
        show_profit_summary=lambda: (log(" Loop ", "blue"), show_profit_summary()),
        monitor_trades=monitor_trades,
        evaluate_symbol=_evaluate_symbol_safe,
        manage_open_trades=_manage_open_trades_safe,
        sleep_fn=time.sleep,
    )

    while True:
        # Check UI stop signal — frontend/utils/.bot_state.json written by Settings page
        _ui_state_path = os.path.join("frontend", "utils", ".bot_state.json")
        try:
            if os.path.exists(_ui_state_path):
                with open(_ui_state_path) as f:
                    if json.load(f).get("state") == "stopped":
                        log(" Bot stopped via UI — exiting", "red")
                        break
        except Exception:
            pass

        open_trades = main_loop_once(runtime_ctx, open_trades)
