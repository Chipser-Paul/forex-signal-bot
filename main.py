# main.py  Elite 2025 (Top-Down) Version (cleaned & fixed)
from __future__ import annotations
import sys
import os

from app_security.environment import consume_child_credentials


_RUNTIME_MT5_CONTRACT = consume_child_credentials() if __name__ == "__main__" else None

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
from typing import Callable
import MetaTrader5 as mt5  # pyright: ignore[reportMissingImports]
from trade_manager import manage_open_trades

# utils & existing modules
from utils.fetch import fetch_ohlcv
from utils.log import log
from trade_executor import execute_trade, load_open_trades, save_open_trades
from utils.connect import connect_mt5
from utils.indicators import calculate_atr
from utils.notifications import send_alert
from utils.trade_journal import log_trade_close, log_trade_event
from utils.analytics_db import record_loop_snapshot
from utils.loop_ai import queue_loop_analysis
#from trend import get_trend
from bot.execution.risk_engine import RiskEngine
from bot.execution.risk import (
    ClosedTradeOutcome,
    CircuitStatus,
    PersistentRiskAuthority,
    RiskDecision,
    RiskError,
    RiskReason,
    RiskStateStore,
    StoreStatus,
    account_snapshot_from_mt5,
    mt5_profit_calculator,
    open_risk_items_from_mt5,
    stable_ref as risk_stable_ref,
    symbol_specification_from_mt5,
    validation_policy,
)
from bot.execution.broker import (
    ExecutionAction,
    ExecutionError as BrokerExecutionError,
    ExecutionRegistry,
    ExecutionRegistryStore,
    ExecutionStatus as BrokerExecutionStatus,
    LocalPosition,
    SecureBrokerExecutor,
    execution_policy_from_environment,
    stable_execution_id,
)
from bot.execution.lifecycle import (
    ActionConfirmation,
    ActionType,
    FillKind,
    ReadinessStyle,
    create_entry_state,
    is_price_ready,
    process_entry_event,
    manage_position,
    reconcile_confirmed_actions,
    record_fill,
    stable_id as lifecycle_stable_id,
)
from bot.execution.live_adapter import (
    intent_from_strategy_entry,
    management_config_from_live,
    market_event_from_tick,
)
from bot.execution.lifecycle.serialization import (
    outcome_to_event,
    position_from_trade_record,
    update_trade_record,
)
from bot.state.orchestrator import StrategyOrchestrator
from bot.strategy.config import PRODUCTION_EXECUTABLE_SYMBOLS
from bot.strategy.trade_levels import LevelInputs, build_trade_levels

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
SYMBOLS = ["XAUUSDm"]

TIMEFRAME = "H1"  # main timeframe for the bot loop (we fetch others as needed)
PAIR_LIMITS = {"XAUUSDm": 1}  # production execution is intentionally XAUUSDm-only
LOOP_DELAY = 60
OPEN_JSON = Path("open_trades.json")
SESSION_JSON = Path("frontend") / "utils" / ".session.json"
RISK_STATE_DIR = Path("runtime") / "risk_state"
EXECUTION_STATE_DIR = Path("runtime") / "execution_state"
STRATEGY_STATES = {}
PENDING_ENTRY_STATES = {}
SHADOW_STRATEGY_STATES = {}
SHADOW_ORCHESTRATOR = StrategyOrchestrator()
ACTIVE_ORCHESTRATOR = StrategyOrchestrator()
ACTIVE_RISK_ENGINE: RiskEngine = ACTIVE_ORCHESTRATOR.risk_engine
_last_session_mtime: float | None = None
# Retained for session-file compatibility only; it cannot expand SYMBOLS or the
# immutable production execution allowlist.
BTC_TRADING_ENABLED = False
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
MIN_EXECUTION_RR = 1.2

last_profit_check = None
profit_initialized = False
daily_target_notified = set()
ACCOUNT_DAILY_TARGET_KEY = "__ACCOUNT__"

def _tracked_trades_by_ticket(open_trades: dict) -> dict[int, dict]:
    tracked: dict[int, dict] = {}
    for records in open_trades.values():
        values = records if isinstance(records, list) else [records]
        for record in values:
            if not isinstance(record, dict) or record.get("ticket") is None:
                continue
            tracked[int(record["ticket"])] = record
    return tracked


def _risk_decision_context(decision) -> dict:
    return {
        "approved": bool(decision.approved),
        "reason": decision.reason.value,
        "decision_id": decision.decision_id,
        "policy_version": decision.policy_version,
        "circuit_status": (
            None if decision.circuit_status is None else decision.circuit_status.value
        ),
        "equity_basis": decision.equity_basis,
        "requested_risk_fraction": decision.requested_risk_fraction,
        "permitted_risk_fraction": decision.permitted_risk_fraction,
        "monetary_risk_budget": decision.monetary_risk_budget,
        "raw_volume": decision.raw_volume,
        "normalized_volume": decision.normalized_volume,
        "estimated_normalized_loss": decision.estimated_normalized_loss,
        "aggregate_open_risk_before": decision.aggregate_open_risk_before,
        "aggregate_open_risk_after": decision.aggregate_open_risk_after,
        "calculation_method": decision.calculation_method,
        "diagnostics": dict(decision.diagnostics),
    }


def _live_risk_authority(*, now: datetime):
    policy = validation_policy(os.environ)
    expected_login = None
    expected_server = None
    if _RUNTIME_MT5_CONTRACT is not None:
        expected_login = _RUNTIME_MT5_CONTRACT.expected_login or None
        expected_server = _RUNTIME_MT5_CONTRACT.expected_server or None
    snapshot = account_snapshot_from_mt5(
        mt5,
        now=now,
        expected_login=expected_login,
        expected_server=expected_server,
    )
    store = RiskStateStore(RISK_STATE_DIR / f"{snapshot.account_ref}.json")
    authority = PersistentRiskAuthority(policy, store)
    return policy, snapshot, authority


def _live_risk_components(open_trades: dict, *, now: datetime):
    policy, snapshot, authority = _live_risk_authority(now=now)
    positions = tuple(mt5.positions_get() or ())
    tracked = _tracked_trades_by_ticket(open_trades)
    loaded = authority.store.load()
    initialize_requested = os.environ.get("RISK_STATE_INITIALIZE", "").strip() == "1"
    if loaded.status is StoreStatus.UNINITIALIZED and initialize_requested:
        if positions or tracked:
            raise RiskError("risk state initialization requires zero open positions")
        authority.initialize(snapshot, known_strategy_positions=0)
    open_risk = open_risk_items_from_mt5(
        mt5,
        positions=positions,
        tracked_trades=tracked,
    )
    return policy, snapshot, authority, open_risk


def _approve_live_risk(
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    open_trades: dict,
    *,
    now: datetime,
):
    try:
        policy, snapshot, authority, open_risk = _live_risk_components(
            open_trades,
            now=now,
        )
        specification = symbol_specification_from_mt5(mt5, symbol)
        return authority.decide(
            snapshot=snapshot,
            specification=specification,
            direction=direction,
            entry=entry,
            stop=stop,
            open_risk_items=open_risk,
            now=now,
            requested_risk_fraction=policy.base_risk_fraction,
            profit_calculator=mt5_profit_calculator(mt5),
        )
    except (RiskError, OSError, ValueError) as exc:
        message = str(exc).lower()
        if "policy" in message or "base risk" in message:
            reason = RiskReason.INVALID_POLICY
        elif "identity" in message:
            reason = RiskReason.ACCOUNT_IDENTITY_MISMATCH
        elif "equity" in message or "balance" in message:
            reason = RiskReason.INVALID_EQUITY
        elif "account snapshot" in message:
            reason = RiskReason.ACCOUNT_DATA_MISSING
        elif "symbol" in message:
            reason = RiskReason.INVALID_SYMBOL_SPEC
        else:
            reason = RiskReason.RISK_STATE_CORRUPT
        fallback_policy = validation_policy({})
        return RiskDecision(
            approved=False,
            reason=reason,
            decision_id=risk_stable_ref(
                fallback_policy.policy_version,
                reason.value,
                now.isoformat(),
            ),
            timestamp=now,
            policy_version=fallback_policy.policy_version,
            circuit_status=CircuitStatus.DATA_UNSAFE,
            diagnostics={"boundary": "live_risk_adapter"},
        )


def _consume_live_risk_outcome(position, *, now: datetime) -> bool:
    try:
        if position.exit_time is None:
            raise RiskError("completed lifecycle outcome is missing an exit timestamp")
        _policy, snapshot, authority = _live_risk_authority(now=now)
        outcome = ClosedTradeOutcome(
            outcome_id=risk_stable_ref(
                position.trade_id,
                "final",
                position.exit_time.isoformat(),
            ),
            trade_id=position.trade_id,
            timestamp=position.exit_time,
            gross_realized_pnl=position.realized_gross_pnl,
            metadata={"cost_basis": "gross_before_costs", "source": "phase3_lifecycle"},
        )
        _state, consumed = authority.consume_outcome(snapshot, outcome, now=now)
        return consumed
    except (RiskError, OSError, ValueError) as exc:
        log(f"[RISK] completed outcome not consumed: {exc}", "red")
        return False


# track last tighten time per ticket to avoid spammy repeated SL changes
_last_tighten = {}  # ticket -> datetime


def _live_broker_executor(symbols: tuple[str, ...]) -> SecureBrokerExecutor:
    policy = execution_policy_from_environment(os.environ, symbols)
    registry_path = EXECUTION_STATE_DIR / f"strategy-{policy.magic_number}.json"
    return SecureBrokerExecutor(
        mt5,
        policy,
        ExecutionRegistry(ExecutionRegistryStore(registry_path)),
    )


def _execution_risk_recheck(
    symbol: str,
    direction: str,
    open_trades: dict,
) -> Callable[[float, float, float], float | None]:
    def recheck(entry: float, stop: float, maximum_volume: float) -> float | None:
        now = datetime.now(timezone.utc)
        decision = _approve_live_risk(
            symbol,
            direction,
            entry,
            stop,
            open_trades,
            now=now,
        )
        if not decision.approved or decision.normalized_volume is None:
            return None
        approved = float(decision.normalized_volume)
        return approved if approved <= maximum_volume + 1e-12 else maximum_volume

    return recheck


def _submit_live_entry(
    *,
    symbol: str,
    direction: str,
    lot: float,
    stop: float,
    target: float,
    intent,
    tick_event,
    risk_decision: RiskDecision,
    open_trades: dict,
    comment: str,
    context: dict,
) -> tuple[dict | None, str]:
    trade_id = lifecycle_stable_id(
        intent.signal_id,
        tick_event.event_id,
        FillKind.LIVE_MARKET.value,
    )
    if symbol not in PRODUCTION_EXECUTABLE_SYMBOLS:
        log(f"[EXECUTION] {symbol} rejected: symbol is not executable", "red")
        return None, trade_id
    try:
        executor = _live_broker_executor((symbol,))
        execution = execute_trade(
            symbol=symbol,
            direction=direction,
            lot=lot,
            sl=stop,
            tp=target,
            comment=comment,
            context=context,
            executor=executor,
            action_id=stable_execution_id(trade_id, "entry"),
            signal_id=intent.signal_id,
            trade_id=trade_id,
            risk_decision_id=risk_decision.decision_id,
            approved_volume=float(risk_decision.normalized_volume),
            approved_stop=stop,
            requested_trigger=intent.requested_trigger,
            created_at=tick_event.timestamp,
            expires_at=intent.expires_at,
            risk_recheck=_execution_risk_recheck(symbol, direction, open_trades),
        )
    except (BrokerExecutionError, OSError, ValueError) as exc:
        log(f"[EXECUTION] {symbol} broker safety rejected submission: {exc}", "red")
        execution = None
    return execution, trade_id


def close_position_immediately(
    symbol: str,
    ticket: int,
    direction: str,
    volume: float,
    reason: str,
    *,
    signal_id: str,
    trade_id: str,
    risk_decision_id: str,
) -> bool:
    """Close only a proven Phase 5-owned position through the secured adapter."""
    try:
        executor = _live_broker_executor((symbol,))
        action_id = stable_execution_id(trade_id, "emergency-close", reason)
        request = executor.position_request(
            action_id=action_id,
            signal_id=signal_id,
            trade_id=trade_id,
            symbol=symbol,
            direction=direction,
            action_type=ExecutionAction.FULL_CLOSE,
            volume=volume,
            executable_price=1.0,
            position_ticket=ticket,
            risk_decision_id=risk_decision_id,
            approved_volume=volume,
            created_at=datetime.now(timezone.utc),
        )
        result = executor.execute(request)
    except (BrokerExecutionError, OSError, ValueError) as exc:
        log(f"[EXECUTION] Emergency close blocked: {exc}", "red")
        return False
    if (
        result.status is BrokerExecutionStatus.CONFIRMED
        and result.executed_volume + 1e-12 >= volume
    ):
        log_trade_close(
            ticket=ticket,
            symbol=symbol,
            exit_price=result.executed_price,
            reason=reason,
            source="phase5_secured_execution_guard",
            details={"action_id": action_id, "execution_reason": result.reason.value},
        )
        return True
    return False


def refresh_runtime_capital() -> None:
    """Reload capital from frontend session file so runtime settings update without bot restart."""
    global CAPITAL, DAILY_TARGET_PCT, TARGET_PROFIT, _last_session_mtime, daily_target_notified

    if not SESSION_JSON.exists():
        return

    try:
        mtime = SESSION_JSON.stat().st_mtime
        if _last_session_mtime is not None and mtime <= _last_session_mtime:
            return

        session = json.loads(SESSION_JSON.read_text(encoding="utf-8"))
        new_capital = float(session.get("capital", CAPITAL))
        new_daily_target_pct = float(session.get("daily_target_pct", DAILY_TARGET_PCT))

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

        _last_session_mtime = mtime
    except Exception as exc:
        log(f"[WARN] Could not refresh runtime capital: {exc}", "yellow")


def is_symbol_trading_enabled(symbol: str) -> bool:
    return symbol in PRODUCTION_EXECUTABLE_SYMBOLS

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

    global MIN_EXECUTION_RR, KILL_SWITCH_MIN_BARS_AFTER_ENTRY, KILL_SWITCH_ATR_BREAK_MULT
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
    result = build_trade_levels(LevelInputs(
        direction=direction,
        entry_price=entry_price,
        entry_mode=entry.get("entry_mode"),
        ob_zone=entry.get("ob_zone"),
        internal_structure=internal_structure or {},
        recent_lows=tuple(float(value) for value in entry_df["low"].tail(10)) if entry_df is not None and not entry_df.empty else (),
        recent_highs=tuple(float(value) for value in entry_df["high"].tail(10)) if entry_df is not None and not entry_df.empty else (),
        structure_context=structure_context,
        liquidity_pools=tuple(liquidity_pools),
        atr=float(calculate_atr(entry_df, period=14) or 0.0),
        point=float(getattr(symbol_info, "point", 0.0) or 0.0),
        stops_level=int(getattr(symbol_info, "stops_level", 0) or 0),
        digits=int(getattr(symbol_info, "digits", 2) or 2),
        level_config=_execution_level_config(symbol_info),
        min_rr=ACTIVE_RISK_ENGINE.min_rr,
        min_rr_buffer=min_rr_buffer,
    ))
    return result.stop, result.target, result.reason


def _entry_price_ready_for_live_market(
    direction: str,
    entry: dict,
    current_price: float,
    entry_df,
    symbol_info,
) -> tuple[bool, str]:
    if entry.get("entry_type") != "limit":
        return is_price_ready(
            direction,
            ReadinessStyle.IMMEDIATE,
            current_price,
            current_price,
        ), "market_on_trigger_immediate"

    limit_price = entry.get("limit_entry")
    if limit_price is None:
        return False, "missing_limit_price"

    limit_price = float(limit_price)
    atr_val = float(calculate_atr(entry_df, period=14) or 0.0)
    point = float(getattr(symbol_info, "point", 0.0) or 0.0)
    tolerance = max(point * 50, atr_val * 0.05)

    if is_price_ready(
        direction,
        ReadinessStyle.PULLBACK,
        limit_price,
        current_price,
        tolerance,
    ):
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

    from bot.strategy.setup_recovery import SetupRecoveryCoordinator
    from bot.strategy.setup_state import SetupStateError, record_from_state, restore_setup_for_evaluation
    from bot.strategy.setup_store import SetupReplayStore

    decision_at = datetime.now(timezone.utc)
    try:
        setup_executor = _live_broker_executor((symbol,))
        setup_store = SetupReplayStore(
            EXECUTION_STATE_DIR / f"setup-{setup_executor.policy.magic_number}-{symbol}.json",
            identity=f"{symbol}:{setup_executor.policy.magic_number}:phase8n",
        )
        prior_runtime_state = STRATEGY_STATES.get(symbol)
        if not setup_store.path.exists() and not setup_store.backup.exists():
            if (open_trades.get(symbol) or setup_executor.registry.snapshot()
                    or (prior_runtime_state is not None and prior_runtime_state.state_name in
                        ("TRADE_ACTIVE", "SETUP_FOUND_PENDING_CONFIRMATION"))):
                raise SetupStateError("legacy active state requires setup reconciliation")
            setup_store.initialize(record_from_state(StrategyState(event_time=decision_at), event_at=decision_at))
        setup_recovery = SetupRecoveryCoordinator(setup_store, setup_executor.registry.snapshot)
        restored = setup_recovery.reconcile()
        if restored.outcome in ("UNCERTAIN_BLOCKED", "IDENTITY_MISMATCH_BLOCKED", "STATE_CORRUPT"):
            no_trade("setup_reconciliation_required", restored.outcome, "red")
            return
        durable_prior = restored.state_record
        state = restore_setup_for_evaluation(durable_prior, decision_at)
        STRATEGY_STATES[symbol] = state
    except (SetupStateError, BrokerExecutionError, OSError, ValueError):
        no_trade("setup_state_unsafe", "setup state cannot be safely recovered", "red")
        return

    result = ACTIVE_ORCHESTRATOR.evaluate_symbol(
        symbol,
        state,
        event_at=decision_at,
        account_balance=CAPITAL,
        daily_pnl=account_profit_today,
        active_trade_count=active_trade_count,
    )
    try:
        evaluated_record = getattr(state, "_gate_record", None)
        if evaluated_record is not None:
            setup_recovery.publish_decision(durable_prior, evaluated_record)
    except (SetupStateError, OSError, ValueError):
        no_trade("setup_checkpoint_failed", "decision state was not durably checkpointed", "red")
        return
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

    entry_with_zone = dict(entry)
    if ob_result.get("valid") and ob_result.get("zone"):
        entry_with_zone["ob_zone"] = ob_result.get("zone")

    requested_trigger = (
        float(entry["limit_entry"])
        if entry.get("entry_type") == "limit" and entry.get("limit_entry") is not None
        else signal_price
    )

    sl, tp, level_reason = _build_orchestrator_trade_levels(
        symbol_info,
        direction,
        requested_trigger,
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

    intent = intent_from_strategy_entry(
        symbol=symbol,
        source_timeframe=cfg["entry_tf"],
        entry=entry_with_zone,
        entry_frame=entry_df,
        stop_loss=sl,
        final_target=tp,
        partial_close_fraction=PARTIAL_CLOSE_RATIO,
        configuration_id=f"{symbol}:{cfg['entry_tf']}:phase3",
        strategy_metadata={
            "strategy": "SMC_COURTROOM_ORCHESTRATOR",
            "setup_score": score.get("score"),
            "setup_grade": score.get("grade"),
        },
    )
    pending_state = PENDING_ENTRY_STATES.get(symbol)
    if pending_state is None or pending_state.intent.signal_id != intent.signal_id:
        pending_state = create_entry_state(intent)
    tick_event = market_event_from_tick(
        symbol,
        tick,
        observed_at=datetime.now(timezone.utc),
    )
    atr_val = float(calculate_atr(entry_df, period=14) or 0.0)
    point = float(getattr(symbol_info, "point", 0.0) or 0.0)
    tolerance = (
        max(point * 50, atr_val * 0.05)
        if intent.readiness_style is ReadinessStyle.PULLBACK
        else 0.0
    )
    try:
        risk_decision = _approve_live_risk(
            symbol,
            direction,
            current_price,
            sl,
            open_trades,
            now=tick_event.timestamp,
        )
    except (RiskError, OSError, ValueError) as exc:
        no_trade("risk_data_unsafe", str(exc), "red")
        return
    loop_context["risk"] = _risk_decision_context(risk_decision)
    if not risk_decision.approved or risk_decision.normalized_volume is None:
        no_trade(
            f"risk_{risk_decision.reason.value.lower()}",
            json.dumps(_risk_decision_context(risk_decision), sort_keys=True),
            "yellow",
        )
        return
    lot = float(risk_decision.normalized_volume)

    entry_decision = process_entry_event(pending_state, tick_event, tolerance=tolerance)
    if not entry_decision.triggered:
        if entry_decision.state.status.value in ("EXPIRED", "CANCELLED", "REJECTED"):
            PENDING_ENTRY_STATES.pop(symbol, None)
        else:
            PENDING_ENTRY_STATES[symbol] = entry_decision.state
        no_trade("entry_wait", entry_decision.reason)
        return
    PENDING_ENTRY_STATES.pop(symbol, None)
    current_price = float(entry_decision.proposed_fill_price)

    rr = ACTIVE_RISK_ENGINE.rr_value(current_price, sl, tp)
    if rr < ACTIVE_RISK_ENGINE.min_rr:
        no_trade("rr_below_orchestrator_minimum", f"rr={rr:.2f}", "red")
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
            "policy_version": risk_decision.policy_version,
            "requested_risk_fraction": risk_decision.requested_risk_fraction,
            "permitted_risk_fraction": risk_decision.permitted_risk_fraction,
            "monetary_risk_budget": risk_decision.monetary_risk_budget,
            "estimated_normalized_loss": risk_decision.estimated_normalized_loss,
            "aggregate_open_risk_before": risk_decision.aggregate_open_risk_before,
            "aggregate_open_risk_after": risk_decision.aggregate_open_risk_after,
            "calculation_method": risk_decision.calculation_method,
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
    expected_trade_id = lifecycle_stable_id(intent.signal_id, tick_event.event_id, FillKind.LIVE_MARKET.value)
    try:
        setup_binding = setup_recovery.prepare(
            evaluated_record, intent,
            action_id=stable_execution_id(expected_trade_id, "entry"), trade_id=expected_trade_id,
            entry_event=tick_event,
            tolerance=tolerance,
        )
    except (SetupStateError, OSError, ValueError):
        no_trade("setup_binding_unsafe", "entry identity was not durably bound", "red")
        return
    execution, broker_trade_id = _submit_live_entry(
        symbol=symbol,
        direction=direction,
        lot=lot,
        stop=sl,
        target=tp,
        intent=intent,
        tick_event=tick_event,
        risk_decision=risk_decision,
        open_trades=open_trades,
        comment="SMC-Orchestrator",
        context=strategy_context,
    )
    # The secured executor fsyncs registry confirmation before this replay.
    # Positive partial fills consume once even if a later execution guard closes.
    try:
        consumed = setup_recovery.confirm(setup_binding)
        state._setup_consumption = consumed.state_record.data()["consumption"]
        state._gate_record = consumed.state_record
        if consumed.outcome in ("UNCERTAIN_BLOCKED", "IDENTITY_MISMATCH_BLOCKED", "STATE_CORRUPT"):
            no_trade("setup_reconciliation_required", consumed.outcome, "red")
            return
    except (SetupStateError, OSError, ValueError):
        no_trade("setup_consumption_checkpoint_failed", "durable fill will be replayed on recovery", "red")
        return
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
            signal_id=intent.signal_id,
            trade_id=broker_trade_id,
            risk_decision_id=risk_decision.decision_id,
        )
        no_trade("execution_guard_low_rr", f"fill_rr={actual_rr:.3f}", "yellow")
        return

    lifecycle_position = record_fill(
        entry_decision.state,
        tick_event,
        fill_price=actual_entry,
        quantity=float(execution["lot"]),
        fill_kind=FillKind.LIVE_MARKET,
        executed_stop=actual_sl,
        executed_target=actual_tp,
        adapter_metadata={
            "source": "live_mt5",
            "configuration_id": intent.configuration_id,
            "ticket": ticket,
            "execution_action_id": execution["execution_action_id"],
            "risk_decision_id": risk_decision.decision_id,
        },
    )

    open_trades.setdefault(symbol, [])
    if not any(isinstance(t, dict) and str(t.get("ticket")) == str(ticket) for t in open_trades[symbol]):
        trade_record = update_trade_record(
            {
                "ticket": ticket,
                "symbol": symbol,
                "direction": direction,
                "opened_at": tick_event.timestamp.isoformat(),
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
            },
            lifecycle_position,
        )
        open_trades[symbol].append(trade_record)
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

    if symbol not in PRODUCTION_EXECUTABLE_SYMBOLS:
        log(f"[STRATEGY] {symbol}: rejected non-executable symbol", "yellow")
        return

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
            "rr_target": rr,
            "risk_distance": abs(price - sl),
            "atr_value": float(atr_val),
            "atr_buffer": float(atr_buffer),
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
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            no_trade("tick_missing", "cannot evaluate post-signal entry readiness", "red")
            return
        intent = intent_from_strategy_entry(
            symbol=symbol,
            source_timeframe=cfg["entry_tf"],
            entry=entry,
            entry_frame=df_entry,
            stop_loss=sl,
            final_target=tp,
            partial_close_fraction=PARTIAL_CLOSE_RATIO,
            configuration_id=f"{symbol}:{cfg['entry_tf']}:phase3-legacy",
            strategy_metadata={
                "strategy": "SMC_ENGINE",
                "legacy_analysis_path": True,
            },
        )
        pending_state = PENDING_ENTRY_STATES.get(symbol)
        if pending_state is None or pending_state.intent.signal_id != intent.signal_id:
            pending_state = create_entry_state(intent)
        tick_event = market_event_from_tick(
            symbol,
            tick,
            observed_at=datetime.now(timezone.utc),
        )
        executable_price = float(tick.ask if direction == "buy" else tick.bid)
        try:
            risk_decision = _approve_live_risk(
                symbol,
                direction,
                executable_price,
                sl,
                open_trades,
                now=tick_event.timestamp,
            )
        except (RiskError, OSError, ValueError) as exc:
            no_trade("risk_data_unsafe", str(exc), "red")
            return
        if not risk_decision.approved or risk_decision.normalized_volume is None:
            no_trade(
                f"risk_{risk_decision.reason.value.lower()}",
                json.dumps(_risk_decision_context(risk_decision), sort_keys=True),
                "yellow",
            )
            return
        full_lot = float(risk_decision.normalized_volume)
        strategy_context["risk_plan"].update(_risk_decision_context(risk_decision))
        strategy_context["risk_plan"]["executed_lot"] = full_lot
        tolerance = (
            max(float(point) * 50.0, float(atr_val) * 0.05)
            if intent.readiness_style is ReadinessStyle.PULLBACK
            else 0.0
        )
        entry_decision = process_entry_event(
            pending_state,
            tick_event,
            tolerance=tolerance,
        )
        if not entry_decision.triggered:
            if entry_decision.state.status.value in ("EXPIRED", "CANCELLED", "REJECTED"):
                PENDING_ENTRY_STATES.pop(symbol, None)
            else:
                PENDING_ENTRY_STATES[symbol] = entry_decision.state
            no_trade("entry_wait", entry_decision.reason)
            return
        PENDING_ENTRY_STATES.pop(symbol, None)

        log(f"[] {symbol} MARKET {direction.upper()} | lot={full_lot}", "green")
        execution, broker_trade_id = _submit_live_entry(
            symbol=symbol,
            direction=direction,
            lot=full_lot,
            stop=sl,
            target=tp,
            intent=intent,
            tick_event=tick_event,
            risk_decision=risk_decision,
            open_trades=open_trades,
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
                    signal_id=intent.signal_id,
                    trade_id=broker_trade_id,
                    risk_decision_id=risk_decision.decision_id,
                )
                no_trade(
                    "execution_guard_low_rr",
                    f"fill_rr={actual_rr:.3f} min_rr={MIN_EXECUTION_RR:.2f}",
                    "yellow",
                )
                return

            tickets.append(ticket)
            lifecycle_position = record_fill(
                entry_decision.state,
                tick_event,
                fill_price=actual_entry,
                quantity=float(execution["lot"]),
                fill_kind=FillKind.LIVE_MARKET,
                executed_stop=actual_sl,
                executed_target=actual_tp,
                adapter_metadata={
                    "source": "live_mt5",
                    "configuration_id": intent.configuration_id,
                    "ticket": ticket,
                    "legacy_analysis_path": True,
                    "execution_action_id": execution["execution_action_id"],
                    "risk_decision_id": risk_decision.decision_id,
                },
            )
            open_trades.setdefault(symbol, [])
            if not any(
                isinstance(t, dict) and str(t.get("ticket")) == str(ticket)
                for t in open_trades[symbol]
            ):
                open_trades[symbol].append(
                    update_trade_record({
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
                        "engine": "legacy_analysis",
                    }, lifecycle_position)
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

def _live_structure_failed(trade, direction, entry_df) -> bool:
    if entry_df is None or len(entry_df) < 7:
        return False
    # Preserve the Phase 2 runtime sampling convention. The causal fetch already
    # excludes the active MT5 candle; this extra exclusion remains a conservative
    # management delay and is not an execution-ordering decision.
    closed_df = entry_df.iloc[:-1].copy()
    if len(closed_df) < 4:
        return False
    opened_at = trade.get("opened_at")
    if opened_at:
        try:
            opened_dt = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
            last_closed_time = closed_df["open_time"].iloc[-1]
            if hasattr(last_closed_time, "to_pydatetime"):
                last_closed_time = last_closed_time.to_pydatetime()
            if last_closed_time.tzinfo is None:
                last_closed_time = last_closed_time.replace(tzinfo=timezone.utc)
            bars_since_entry = int(
                max(0, (last_closed_time - opened_dt).total_seconds()) // (15 * 60)
            )
            if bars_since_entry < KILL_SWITCH_MIN_BARS_AFTER_ENTRY:
                return False
        except (TypeError, ValueError, KeyError):
            return False

    atr_val = calculate_atr(closed_df, period=14)
    break_buffer = atr_val * KILL_SWITCH_ATR_BREAK_MULT if atr_val > 0 else 0.0
    c1, c2, c3, c4 = (closed_df.iloc[-4], closed_df.iloc[-3], closed_df.iloc[-2], closed_df.iloc[-1])
    if direction == "buy":
        level1 = min(c1["low"], c2["low"])
        level2 = min(c2["low"], c3["low"])
        return bool(
            c3["close"] < level1 - break_buffer
            and c4["close"] < level2 - break_buffer
        )
    level1 = max(c1["high"], c2["high"])
    level2 = max(c2["high"], c3["high"])
    return bool(
        c3["close"] > level1 + break_buffer
        and c4["close"] > level2 + break_buffer
    )


def _live_structure_trail_level(sym, trade, direction, partial_taken):
    if not partial_taken:
        return None
    htf_df = fetch_ohlcv(sym, HTF_TF, bars=5)
    if htf_df is None or len(htf_df) < 3:
        return None
    confirmed = bool(trade.get("htf_bos_confirmed"))
    if not confirmed:
        if direction == "buy":
            confirmed = bool(htf_df["high"].iloc[-1] > htf_df["high"].iloc[-2])
        else:
            confirmed = bool(htf_df["low"].iloc[-1] < htf_df["low"].iloc[-2])
        if confirmed:
            trade["htf_bos_confirmed"] = True
    if not confirmed:
        return None
    return float(
        htf_df["low"].iloc[-2]
        if direction == "buy"
        else htf_df["high"].iloc[-2]
    )


def monitor_trades(open_trades):
    """Manage live positions through the shared Phase 3 lifecycle reducer."""
    updated = {}
    positions = {int(position.ticket): position for position in (mt5.positions_get() or [])}
    for sym, records in open_trades.items():
        profile = apply_symbol_profile(sym)
        keep = []
        try:
            broker_executor = _live_broker_executor((sym,))
        except (BrokerExecutionError, OSError, ValueError) as exc:
            log(f"[EXECUTION] {sym} management blocked: {exc}", "red")
            updated[sym] = list(records) if isinstance(records, list) else [records]
            continue
        for raw_trade in records if isinstance(records, list) else [records]:
            if not isinstance(raw_trade, dict) or raw_trade.get("ticket") is None:
                continue
            trade = dict(raw_trade)
            ticket = int(trade["ticket"])
            broker_position = positions.get(ticket)
            if broker_position is None:
                close_data = _find_recent_close_deal(ticket, sym)
                log_trade_close(
                    ticket=ticket,
                    symbol=sym,
                    pnl=None if close_data is None else close_data.get("pnl"),
                    exit_price=None if close_data is None else close_data.get("exit_price"),
                    reason=(
                        "position_not_found"
                        if close_data is None
                        else close_data.get("comment") or "broker_position_closed"
                    ),
                    source="phase3_broker_reconciliation",
                    closed_at_utc=None if close_data is None else close_data.get("closed_at_utc"),
                    details={"signal_id": trade.get("signal_id"), "trade_id": trade.get("trade_id")},
                )
                continue

            info = mt5.symbol_info(sym)
            tick_data = mt5.symbol_info_tick(sym)
            if info is None or tick_data is None:
                keep.append(trade)
                continue
            direction = str(trade.get("direction") or "").lower()
            if direction not in ("buy", "sell"):
                keep.append(trade)
                continue

            observed_at = datetime.now(timezone.utc)
            initial_stop = float(getattr(broker_position, "sl", 0.0) or trade.get("sl") or 0.0)
            final_target = float(getattr(broker_position, "tp", 0.0) or trade.get("tp") or 0.0)
            if initial_stop <= 0 or final_target <= 0:
                keep.append(trade)
                continue
            trade.setdefault("symbol", sym)
            position = position_from_trade_record(
                trade,
                remaining_quantity=float(broker_position.volume),
                current_stop=initial_stop,
                final_target=final_target,
                observed_at=observed_at,
            )

            identity_event = market_event_from_tick(
                sym,
                tick_data,
                observed_at=observed_at,
            )
            if identity_event.event_id in position.processed_event_ids:
                keep.append(trade)
                continue

            m15_df = fetch_ohlcv(sym, "M15", bars=10)
            emergency = (
                "kill_switch_structure_failure"
                if _live_structure_failed(trade, direction, m15_df)
                else None
            )
            m5_df = fetch_ohlcv(sym, "M5", bars=20)
            m5_atr = (
                float(calculate_atr(m5_df, period=14) or 0.0)
                if m5_df is not None and len(m5_df) >= 15
                else None
            )
            structure_trail = _live_structure_trail_level(
                sym,
                trade,
                direction,
                position.partial_close_occurred,
            )
            market_event = market_event_from_tick(
                sym,
                tick_data,
                observed_at=observed_at,
                atr=m5_atr,
                emergency_reason=emergency,
                structure_trail_level=structure_trail,
            )
            management_config = management_config_from_live(
                profile=profile,
                symbol_info=info,
                partial_close_fraction=position.partial_close_fraction,
            )
            lifecycle_result = manage_position(position, market_event, management_config)

            executed = []
            dispatch_error = None
            try:
                for action in lifecycle_result.actions:
                    if action.action_type is ActionType.PARTIAL_SKIPPED:
                        executed.append((action, None))
                        continue
                    action_mapping = {
                        ActionType.PARTIAL_CLOSE: ExecutionAction.PARTIAL_CLOSE,
                        ActionType.FINAL_CLOSE: ExecutionAction.FULL_CLOSE,
                        ActionType.MODIFY_STOP: ExecutionAction.MODIFY_STOP,
                    }
                    broker_action = action_mapping[action.action_type]
                    requested_quantity = (
                        float(action.quantity)
                        if action.action_type in (
                            ActionType.PARTIAL_CLOSE,
                            ActionType.FINAL_CLOSE,
                        )
                        and action.quantity is not None
                        else float(broker_position.volume)
                    )
                    execution_request = broker_executor.position_request(
                        action_id=action.action_id,
                        signal_id=position.signal_id,
                        trade_id=position.trade_id,
                        symbol=sym,
                        direction=direction,
                        action_type=broker_action,
                        volume=requested_quantity,
                        executable_price=float(
                            tick_data.bid if direction == "buy" else tick_data.ask
                        ),
                        position_ticket=ticket,
                        risk_decision_id=str(
                            position.adapter_metadata.get(
                                "risk_decision_id",
                                "phase4-existing-position",
                            )
                        ),
                        approved_volume=float(broker_position.volume),
                        created_at=market_event.timestamp,
                        stop_price=(
                            float(action.new_stop)
                            if action.action_type is ActionType.MODIFY_STOP
                            else None
                        ),
                        target_price=(
                            final_target
                            if action.action_type is ActionType.MODIFY_STOP
                            else None
                        ),
                        approved_stop=(
                            position.current_stop
                            if action.action_type is ActionType.MODIFY_STOP
                            else None
                        ),
                    )
                    broker_result = broker_executor.execute(execution_request)
                    if broker_result.status not in (
                        BrokerExecutionStatus.CONFIRMED,
                        BrokerExecutionStatus.PARTIALLY_FILLED,
                    ):
                        raise RuntimeError(
                            f"{action.action_id}:{broker_result.reason.value}"
                        )
                    executed.append((action, broker_result))
            except (BrokerExecutionError, RuntimeError, ValueError) as exc:
                log(f"[LIFECYCLE] {sym} action dispatch failed: {exc}", "red")
                dispatch_error = exc

            confirmations = []
            for action, broker_result in executed:
                if (
                    broker_result is not None
                    and action.action_type in (ActionType.PARTIAL_CLOSE, ActionType.FINAL_CLOSE)
                    and broker_result.executed_price is not None
                    and broker_result.executed_volume > 0
                ):
                    confirmations.append(
                        ActionConfirmation(
                            action_id=action.action_id,
                            executed_quantity=float(broker_result.executed_volume),
                            executed_price=float(broker_result.executed_price),
                        )
                    )
                elif broker_result is not None:
                    confirmations.append(ActionConfirmation(action_id=action.action_id))
                log_trade_event(
                    ticket=ticket,
                    symbol=sym,
                    event_name=f"lifecycle_{action.action_type.value.lower()}",
                    details={
                        "signal_id": position.signal_id,
                        "trade_id": position.trade_id,
                        "event_id": action.event_id,
                        "action_id": action.action_id,
                        "quantity": action.quantity,
                        "requested_price": action.requested_price,
                        "new_stop": action.new_stop,
                        "reason": action.reason.value if hasattr(action.reason, "value") else action.reason,
                        "execution_reason": (
                            None if broker_result is None else broker_result.reason.value
                        ),
                        "executed_quantity": (
                            None if broker_result is None else broker_result.executed_volume
                        ),
                    },
                )

            managed = reconcile_confirmed_actions(
                position,
                lifecycle_result,
                confirmations,
                management_config,
            )
            if dispatch_error is not None and not executed:
                keep.append(trade)
                continue

            if managed.status.value == "CLOSED":
                closed_event = outcome_to_event(managed)
                log_trade_close(
                    ticket=ticket,
                    symbol=sym,
                    pnl=managed.realized_gross_pnl,
                    exit_price=managed.exit_price,
                    reason=str(closed_event["reason"]),
                    source="phase3_lifecycle",
                    closed_at_utc=str(closed_event["ts_utc"]),
                    details=closed_event,
                )
                consumed = _consume_live_risk_outcome(
                    managed,
                    now=managed.exit_time or observed_at,
                )
                log_trade_event(
                    ticket=ticket,
                    symbol=sym,
                    event_name="risk_outcome_consumed",
                    details={
                        "trade_id": managed.trade_id,
                        "consumed": consumed,
                        "policy": "phase4-validation-v1",
                    },
                )
                continue
            keep.append(update_trade_record(trade, managed))

        if keep:
            updated[sym] = keep

    if updated != open_trades:
        save_open_trades(updated)
    return updated


def _consume_reconciled_close(trade: dict, close_data: dict, *, now: datetime) -> bool:
    """Consume one broker-confirmed complete close without replaying partials."""
    try:
        _policy, snapshot, authority = _live_risk_authority(now=now)
        trade_id = str(trade["trade_id"])
        outcome = ClosedTradeOutcome(
            outcome_id=risk_stable_ref(
                trade_id,
                "broker-reconciled-close",
                close_data.get("deal_id"),
            ),
            trade_id=trade_id,
            timestamp=now,
            gross_realized_pnl=(
                float(trade.get("realized_gross_pnl", 0.0))
                + float(close_data.get("pnl", 0.0))
            ),
            metadata={
                "cost_basis": "broker_reported_gross_before_complete_cost_model",
                "source": "phase5_startup_reconciliation",
            },
        )
        _state, consumed = authority.consume_outcome(snapshot, outcome, now=now)
        return consumed
    except (KeyError, RiskError, OSError, ValueError) as exc:
        log(f"[RECONCILIATION] Close outcome was not consumed: {exc}", "red")
        return False


def reconcile_broker_startup(open_trades: dict) -> bool:
    """Fail closed unless persisted lifecycle and broker ownership reconcile."""
    now = datetime.now(timezone.utc)
    try:
        executor = _live_broker_executor(tuple(SYMBOLS))
        broker_positions = tuple(mt5.positions_get() or ())
        broker_orders = tuple(mt5.orders_get() or ())
        recent_deals = tuple(mt5.history_deals_get(now - timedelta(days=7), now) or ())
    except (BrokerExecutionError, OSError, ValueError, AttributeError) as exc:
        log(f"[RECONCILIATION] Startup blocked: {exc}", "red")
        return False

    local_positions: list[LocalPosition] = []
    local_by_ticket: dict[int, dict] = {}
    for symbol, records in open_trades.items():
        for trade in records if isinstance(records, list) else [records]:
            if not isinstance(trade, dict) or trade.get("ticket") is None:
                continue
            ticket = int(trade["ticket"])
            local_by_ticket[ticket] = trade
            local_positions.append(
                LocalPosition(
                    trade_id=str(trade.get("trade_id") or f"legacy-{ticket}"),
                    symbol=symbol,
                    ticket=ticket,
                    direction=str(trade.get("direction") or "unknown"),
                    remaining_volume=float(
                        trade.get("remaining_quantity") or trade.get("lot") or 0.0
                    ),
                    stop=(float(trade["sl"]) if trade.get("sl") else None),
                    target=(float(trade["tp"]) if trade.get("tp") else None),
                )
            )

    results = executor.reconciler.reconcile_startup(
        local_positions,
        broker_positions=broker_positions,
        broker_orders=broker_orders,
        recent_deals=recent_deals,
        now=now,
    )
    for result in results:
        if result.state.value == "CLOSED_CONFIRMED" and result.position_ticket in local_by_ticket:
            trade = local_by_ticket[result.position_ticket]
            close_data = _find_recent_close_deal(
                int(result.position_ticket),
                str(trade.get("symbol") or ""),
            )
            if close_data is None:
                return False
            _consume_reconciled_close(trade, close_data, now=now)
            for symbol in list(open_trades):
                records = open_trades[symbol]
                values = records if isinstance(records, list) else [records]
                filtered = [
                    item
                    for item in values
                    if not isinstance(item, dict)
                    or int(item.get("ticket", -1)) != int(result.position_ticket)
                ]
                if filtered:
                    open_trades[symbol] = filtered
                else:
                    open_trades.pop(symbol, None)
        elif result.state.value == "RECOVERED":
            recovered = dict(result.recovered)
            symbol = str(recovered["symbol"])
            open_trades.setdefault(symbol, []).append(
                {
                    "ticket": int(result.position_ticket),
                    "symbol": symbol,
                    "trade_id": str(recovered["trade_id_fragment"]),
                    "signal_id": str(recovered["trade_id_fragment"]),
                    "direction": str(recovered["direction"]),
                    "entry_price": float(recovered["entry_price"]),
                    "lot": float(recovered["remaining_volume"]),
                    "remaining_quantity": float(recovered["remaining_volume"]),
                    "sl": float(recovered["stop"]),
                    "tp": float(recovered["target"]),
                    "reconciliation_state": "RECOVERED",
                    "partial_history": "UNKNOWN",
                }
            )
    if any(result.block_new_entries for result in results):
        blocked = [result.reason.value for result in results if result.block_new_entries]
        log(f"[RECONCILIATION] Startup requires owner review: {sorted(set(blocked))}", "red")
        return False
    save_open_trades(open_trades)
    return True

#  ENTRYPOINT 
if __name__ == "__main__":
    if not connect_mt5(_RUNTIME_MT5_CONTRACT):
        log(" MT5 connection failed. Exiting.", "red")
        raise SystemExit(1)

    open_trades = load_open_trades(strict=True)
    # normalize format
    for k, v in list(open_trades.items()):
        if isinstance(v, int):
            open_trades[k] = [v]
    if not reconcile_broker_startup(open_trades):
        log(" Broker reconciliation failed closed. Exiting.", "red")
        raise SystemExit(1)

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
