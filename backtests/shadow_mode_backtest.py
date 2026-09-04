
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
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
from bot.analysis.dxy_filter import (
    DXY_BASKET,
    build_synthetic_dxy_from_frames,
    get_dxy_bias_from_array,
)
from bot.data.candles import (
    CandleDataError,
    as_utc_timestamp,
    causal_end_positions,
    causal_snapshot,
    get_timeframe_spec,
    normalize_candles,
)
from bot.data.market_data import get_mt5_timeframe
from bot.analysis.fvg_engine import get_unfilled_fvgs
from bot.analysis.liquidity_map import get_asian_session_range, get_previous_day_levels, get_previous_week_levels
from bot.execution.confluence_scorer import score_setup
from bot.execution.news_filter import get_news_status
from bot.strategy.legacy_adapter import evaluate_legacy_context
from bot.strategy.models import SetupEvidence
from bot.execution.risk_engine import RiskEngine
from bot.execution.risk import (
    AccountSnapshot,
    CircuitStatus,
    ClosedTradeOutcome,
    InMemoryRiskAuthority,
    OpenRiskItem,
    SymbolRiskSpecification,
    initialize_risk_state,
    stable_ref as risk_stable_ref,
    validation_policy,
)
from bot.execution.lifecycle import (
    Direction as LifecycleDirection,
    EntryState,
    FillKind,
    LifecycleStatus,
    ManagementConfig,
    MarketEvent,
    MarketEventKind,
    PositionState,
    ReadinessStyle,
    create_entry_state,
    force_close,
    manage_position,
    new_entry_intent,
    process_entry_event,
    prospective_bar_fill,
    record_fill,
    stable_id,
)
from bot.utils.session_clock import get_session_context
from utils.setup_logger import log_setup_evaluation, generate_setup_id
from strategies.smc_engine.displacement_engine import detect_displacement
from strategies.smc_engine.entry_model import determine_entry
from strategies.smc_engine.liquidity_engine import detect_liquidity_sweep
from strategies.smc_engine.market_structure import analyze_market_structure
from strategies.smc_engine.ob_breaker_engine import detect_ob_breaker
from strategies.smc_engine.strategy_state import STATE_EXPIRY_MINUTES, StrategyState
from utils.connect import connect_mt5
from utils.indicators import calculate_atr
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
class PendingEntry:
    entry_state: EntryState
    sl_reason: str
    score: int
    grade: str
    setup_id: str
    tolerance: float = 0.0


@dataclass
class CostModel:
    """Legacy diagnostic round-trip approximation; never validation evidence."""
    spread_price: float = 0.0
    slippage_price: float = 0.0
    commission_per_lot: float = 0.0
    contract_size: float = 100.0

    def round_trip(self, lot: float) -> float:
        # Spread is paid once (enter at ask, exit at bid); slippage on both fills.
        price_cost = self.spread_price + 2.0 * self.slippage_price
        return price_cost * lot * self.contract_size + self.commission_per_lot * lot


def _backtest_account_snapshot(
    *,
    account_ref: str,
    capital: float,
    realized_pnl: float,
    positions: list[PositionState],
    mark_price: float,
    contract_size: float,
    timestamp: datetime,
) -> AccountSnapshot:
    balance = capital + realized_pnl
    floating_pnl = sum(
        position.direction.sign
        * (mark_price - position.fill_price)
        * position.remaining_quantity
        * contract_size
        for position in positions
    )
    return AccountSnapshot(
        account_ref=account_ref,
        balance=balance,
        equity=balance + floating_pnl,
        floating_pnl=floating_pnl,
        margin=0.0,
        free_margin=balance + floating_pnl,
        currency="SIMULATED",
        timestamp=timestamp,
        source="shadow_backtest",
    )


def _backtest_open_risk(
    positions: list[PositionState],
    *,
    mark_price: float,
    contract_size: float,
) -> tuple[OpenRiskItem, ...]:
    items = []
    for position in positions:
        stop = position.current_stop
        wrong_side = (
            position.direction is LifecycleDirection.BUY and stop >= mark_price
        ) or (
            position.direction is LifecycleDirection.SELL and stop <= mark_price
        )
        locked_profit = (
            position.direction is LifecycleDirection.BUY and stop >= position.fill_price
        ) or (
            position.direction is LifecycleDirection.SELL and stop <= position.fill_price
        )
        estimated_loss = None
        method = "invalid_stop"
        if not wrong_side:
            estimated_loss = (
                0.0
                if locked_profit
                else abs(position.fill_price - stop)
                * position.remaining_quantity
                * contract_size
            )
            method = "locked_profit_floor" if locked_profit else "backtest_contract_size"
        items.append(
            OpenRiskItem(
                trade_id=position.trade_id,
                symbol=position.symbol,
                direction=position.direction.value,
                remaining_volume=position.remaining_quantity,
                current_reference_price=mark_price,
                current_stop=stop,
                estimated_loss=estimated_loss,
                ownership="strategy",
                calculation_method=method,
                entry_price=position.fill_price,
            )
        )
    return tuple(items)


def _refresh_backtest_risk(
    authority: InMemoryRiskAuthority,
    *,
    account_ref: str,
    capital: float,
    realized_pnl: float,
    positions: list[PositionState],
    mark_price: float,
    contract_size: float,
    timestamp: datetime,
) -> AccountSnapshot:
    snapshot = _backtest_account_snapshot(
        account_ref=account_ref,
        capital=capital,
        realized_pnl=realized_pnl,
        positions=positions,
        mark_price=mark_price,
        contract_size=contract_size,
        timestamp=timestamp,
    )
    authority.refresh(snapshot, now=timestamp)
    return snapshot


def _consume_backtest_outcome(
    authority: InMemoryRiskAuthority,
    position: PositionState,
) -> bool:
    if position.exit_time is None:
        raise RuntimeError("closed backtest position lacks an exit timestamp")
    return authority.consume_outcome(
        ClosedTradeOutcome(
            outcome_id=risk_stable_ref(
                position.trade_id,
                "final",
                position.exit_time.isoformat(),
            ),
            trade_id=position.trade_id,
            timestamp=position.exit_time,
            gross_realized_pnl=position.realized_gross_pnl,
            metadata={"cost_basis": "gross_before_costs", "source": "shadow_backtest"},
        )
    )


def _check_kill_switch(
    pos: PositionState,
    now_ts: datetime,
    m15_closed: pd.DataFrame,
    profile: dict,
) -> bool:
    """Check if M15 structure has invalidated the trade entry. Returns True if structure failed."""
    if m15_closed.empty or len(m15_closed) < 8:
        return False
    # Count closed M15 bars since position opened
    opened_at = getattr(pos, "fill_timestamp", getattr(pos, "opened_at", now_ts))
    opened = opened_at.replace(tzinfo=None) if opened_at.tzinfo is not None else opened_at
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


def _normalize_historical_frame(data: Any, timeframe: str) -> pd.DataFrame:
    frame = data.copy(deep=True) if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if frame.empty:
        return normalize_candles(frame, timeframe)
    if (
        frame.attrs.get("causal_normalized")
        and frame.attrs.get("timeframe") == get_timeframe_spec(timeframe).name
    ):
        return frame.copy(deep=True)
    return normalize_candles(frame, timeframe, final_candle_complete=False)


def _fetch_range(symbol: str, timeframe: str, start: datetime, end: datetime, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
    # File-based cache: reuse previously downloaded MT5 data
    cache_path = None
    if use_cache and not force_refresh:
        cache_key = f"{symbol}_{timeframe}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.pkl"
        cache_path = CACHE_DIR / cache_key
        if cache_path.exists():
            try:
                return _normalize_historical_frame(pd.read_pickle(str(cache_path)), timeframe)
            except CandleDataError:
                raise
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
        rates = mt5.copy_rates_range(symbol, get_mt5_timeframe(timeframe), cursor, chunk_end)
        df = pd.DataFrame(rates)
        if not df.empty:
            frames.append(df)
        cursor = chunk_end + timedelta(seconds=1)
    if not frames:
        return pd.DataFrame()
    result = _normalize_historical_frame(pd.concat(frames, ignore_index=True), timeframe)

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
    dxy, component_count, alignment = build_synthetic_dxy_from_frames(
        dxy_frames,
        "H1",
        100,
        now_ts,
    )
    if dxy is None:
        return {
            "available": False,
            "source": "synthetic_basket",
            "dxy_bias": "unavailable",
            "confirms_bias": False,
            "reduce_size": False,
            "basket_pairs_used": component_count,
            "alignment": alignment,
        }
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
        "basket_pairs_used": component_count,
        "alignment": alignment,
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
        snapshot = causal_snapshot(df, now_ts, max_bars=1)
        key.append(
            (pair, snapshot["available_at"].iloc[-1].isoformat())
            if not snapshot.empty
            else (pair, None)
        )
    return tuple(key)


def _causal_timeframe_views(
    data_frames: dict[str, pd.DataFrame],
    decision_timestamp: object,
    *,
    limits: dict[str, int] | None = None,
) -> tuple[dict[str, pd.DataFrame], str | None]:
    """Build deterministic completed-candle views for one backtest decision."""
    decision = as_utc_timestamp(decision_timestamp, field="decision_timestamp")
    views: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for timeframe in ("W1", "D1", "H4", "H1", "M15"):
        frame = data_frames.get(timeframe)
        view = (
            causal_snapshot(
                frame,
                decision,
                max_bars=(limits or {}).get(timeframe, 320),
            )
            if frame is not None and not frame.empty
            else pd.DataFrame()
        )
        views[timeframe] = view
        if view.empty:
            missing.append(timeframe)
    reason = f"insufficient_completed_htf_history:{','.join(missing)}" if missing else None
    return views, reason


def _pnl(symbol: str, direction: str, lot: float, entry: float, exit_price: float, cost: CostModel | None = None) -> float:
    sign = 1 if direction == "buy" else -1
    contract = cost.contract_size if cost else 100.0
    gross = (exit_price - entry) * sign * lot * contract
    fees = cost.round_trip(lot) if cost else 0.0
    return float(gross - fees)


def _lifecycle_trade_record(position, net_pnl: float, transaction_cost: float) -> dict[str, Any]:
    metadata = dict(position.adapter_metadata)
    reason = position.exit_reason.value if hasattr(position.exit_reason, "value") else position.exit_reason
    return {
        "ticket": int(metadata.get("ticket", 0)),
        "signal_id": position.signal_id,
        "trade_id": position.trade_id,
        "symbol": position.symbol,
        "direction": position.direction.value,
        "opened_at": position.fill_timestamp.isoformat(),
        "closed_at": position.exit_time.isoformat(),
        "requested_entry": round(position.requested_entry, 5),
        "entry_price": round(position.fill_price, 5),
        "exit_price": round(float(position.exit_price), 5),
        "initial_sl": round(position.initial_stop, 5),
        "sl": round(position.current_stop, 5),
        "tp": round(position.final_target, 5),
        "risk_price": round(position.initial_risk_price, 5),
        "sl_reason": metadata.get("sl_reason"),
        "lot": position.initial_quantity,
        "closed_quantity": position.closed_quantity,
        "score": metadata.get("score", 0),
        "grade": metadata.get("grade", ""),
        "setup_id": metadata.get("setup_id"),
        "reason": reason,
        "gross_pnl": round(position.realized_gross_pnl, 4),
        "transaction_cost": round(transaction_cost, 4),
        "pnl": round(net_pnl, 4),
        "partial_close_occurred": position.partial_close_occurred,
        "pnl_components": [
            {
                "action_id": component.action_id,
                "quantity": component.quantity,
                "exit_price": component.exit_price,
                "gross_pnl": component.gross_pnl,
                "reason": component.reason.value if hasattr(component.reason, "value") else component.reason,
            }
            for component in position.pnl_components
        ],
        "ambiguity_policy_used": position.ambiguity_policy_used,
        "lifecycle_transitions": [
            {
                "event_id": transition.event_id,
                "from": transition.from_status.value,
                "to": transition.to_status.value,
                "reason": transition.reason,
            }
            for transition in position.transitions
        ],
    }


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
    if trail_mode != "live_atr_3x":
        raise ValueError(
            "Phase 3 supports only the shared live_atr_3x management policy; "
            "legacy backtest-only trailing modes were retired"
        )
    if min_rr is not None:
        raise ValueError(
            "Phase 7 freezes Phase 6 strategy parameters; min_rr overrides are prohibited"
        )
    profile = _apply_symbol_profile(symbol)
    risk_engine = RiskEngine()
    pair_limit = int(profile.get("pair_limit", 1))
    structure_tf = str(profile.get("structure_tf", "H1"))
    entry_tf = str(profile.get("entry_tf", "M5"))
    structure_bars = int(profile.get("structure_bars", 300))
    entry_bars = int(profile.get("entry_bars", 150))
    warmup_start = start - timedelta(days=370)

    data_frames = {
        tf: _normalize_historical_frame(
            _fetch_range(symbol, tf, warmup_start, end),
            tf,
        )
        for tf in ("W1", "D1", "H4", "H1", "M15", entry_tf)
    }
    entry_df_all = data_frames[entry_tf]
    if entry_df_all is None or entry_df_all.empty:
        raise RuntimeError(f"No {entry_tf} data for {symbol}")
    dxy_frames = {
        pair: _normalize_historical_frame(
            _fetch_range(pair, "H1", warmup_start, end),
            "H1",
        )
        for pair, _w, _i in DXY_BASKET
    }

    state = StrategyState()
    open_positions: list[PositionState] = []
    pending_entry: PendingEntry | None = None
    booked_gross_by_trade: dict[str, float] = {}
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    no_trade_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    realized_pnl = 0.0
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
    lifecycle_config = ManagementConfig(
        partial_close_fraction=0.5,
        partial_target_r=1.0,
        volume_min=float(getattr(symbol_info, "volume_min", 0.01) or 0.01),
        volume_step=float(getattr(symbol_info, "volume_step", 0.01) or 0.01),
        pnl_per_price_unit=contract_size,
        trailing_enabled=str(trail_cfg.get("mode", "atr_3x")) == "atr_3x",
        trailing_atr_multiple=float(trail_cfg.get("atr_mult", 3.0)),
        trailing_min_distance=float(trail_cfg.get("min_distance_points", 100.0)) * point,
    )
    total_costs = 0.0

    start_timestamp = as_utc_timestamp(start, field="backtest start")
    end_timestamp = as_utc_timestamp(end, field="backtest end")
    risk_policy = validation_policy({})
    risk_specification = SymbolRiskSpecification(
        symbol=symbol,
        tick_size=float(getattr(symbol_info, "trade_tick_size", point) or point),
        tick_value=float(getattr(symbol_info, "trade_tick_value", 0.0) or 0.0),
        volume_min=float(getattr(symbol_info, "volume_min", 0.0) or 0.0),
        volume_max=float(getattr(symbol_info, "volume_max", 0.0) or 0.0),
        volume_step=float(getattr(symbol_info, "volume_step", 0.0) or 0.0),
        price_precision=int(getattr(symbol_info, "digits", 0) or 0),
        contract_size=contract_size,
    )
    risk_account_ref = risk_stable_ref(
        "shadow_backtest",
        symbol,
        start_timestamp.isoformat(),
        float(capital),
    )
    initial_snapshot = AccountSnapshot(
        account_ref=risk_account_ref,
        balance=float(capital),
        equity=float(capital),
        floating_pnl=0.0,
        margin=0.0,
        free_margin=float(capital),
        currency="SIMULATED",
        timestamp=start_timestamp.to_pydatetime(),
        source="shadow_backtest",
    )
    risk_authority = InMemoryRiskAuthority(
        risk_policy,
        initialize_risk_state(
            initial_snapshot,
            risk_policy,
            known_strategy_positions=0,
        ),
    )
    test_rows = entry_df_all[
        (entry_df_all["available_at"] >= start_timestamp)
        & (entry_df_all["available_at"] <= end_timestamp)
    ]
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
            tf_positions[tf] = causal_end_positions(df, test_rows["available_at"])
    m5_positions = causal_end_positions(entry_df_all, test_rows["available_at"])

    for idx, (_candle_open_time, candle) in enumerate(test_rows.iterrows(), start=1):
        now_ts = as_utc_timestamp(candle["available_at"], field="entry candle availability")
        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        candle_open_time = as_utc_timestamp(candle["open_time"], field="entry candle open")

        # Build M15 view for kill-switch before position loop (only when positions exist)
        i = idx - 1
        current_m15_idx = int(tf_positions.get("M15", [0])[i]) if "M15" in tf_positions and i < len(tf_positions["M15"]) and tf_positions["M15"][i] > 0 else 0
        m15_closed = pd.DataFrame()
        if open_positions and current_m15_idx > 0 and data_frames.get("M15") is not None:
            all_m15 = data_frames["M15"]
            m15_start = max(0, current_m15_idx - 20)
            m15_closed = all_m15.iloc[m15_start:current_m15_idx].copy()

        m5_atr = float(candle.get("atr_14", 0.0)) if pd.notna(candle.get("atr_14", None)) else 0.0
        event_id = stable_id(symbol, entry_tf, candle_open_time.isoformat(), now_ts.isoformat())
        base_event = MarketEvent(
            event_id=event_id,
            timestamp=now_ts.to_pydatetime(),
            symbol=symbol,
            source="shadow_backtest",
            kind=MarketEventKind.BAR,
            sequence=idx,
            open=open_price,
            high=high,
            low=low,
            close=close,
            bar_open_time=candle_open_time.to_pydatetime(),
            source_candle_id=stable_id(symbol, entry_tf, candle_open_time.isoformat()),
            atr=m5_atr,
        )

        survivors: list[PositionState] = []
        for pos in open_positions:
            emergency = "kill_switch_structure_failure" if _check_kill_switch(pos, now_ts, m15_closed, profile) else None
            event = replace(base_event, emergency_reason=emergency)
            previous_gross = booked_gross_by_trade.get(pos.trade_id, 0.0)
            management = manage_position(pos, event, lifecycle_config)
            managed = management.position
            gross_delta = managed.realized_gross_pnl - previous_gross
            realized_pnl += gross_delta
            booked_gross_by_trade[managed.trade_id] = managed.realized_gross_pnl
            for action in management.actions:
                action_counts[f"lifecycle_{action.action_type.value.lower()}"] += 1
            if managed.status is not LifecycleStatus.CLOSED:
                survivors.append(managed)
                continue

            trade_cost = cost.round_trip(managed.initial_quantity)
            total_costs += trade_cost
            realized_pnl -= trade_cost
            net_pnl = managed.realized_gross_pnl - trade_cost
            _consume_backtest_outcome(risk_authority, managed)
            trades.append(_lifecycle_trade_record(managed, net_pnl, trade_cost))
            booked_gross_by_trade.pop(managed.trade_id, None)
        open_positions = survivors

        try:
            account_snapshot = _refresh_backtest_risk(
                risk_authority,
                account_ref=risk_account_ref,
                capital=capital,
                realized_pnl=realized_pnl,
                positions=open_positions,
                mark_price=close,
                contract_size=contract_size,
                timestamp=now_ts.to_pydatetime(),
            )
        except (ValueError, TypeError):
            account_snapshot = None
            no_trade_counts["risk_invalid_simulated_equity"] += 1

        if pending_entry is not None:
            intent = pending_entry.entry_state.intent
            risk_decision = None
            if intent.expires_at is not None and base_event.timestamp >= intent.expires_at:
                entry_decision = process_entry_event(
                    pending_entry.entry_state,
                    base_event,
                    tolerance=pending_entry.tolerance,
                )
            else:
                prospective = prospective_bar_fill(
                    intent,
                    base_event,
                    pending_entry.tolerance,
                )
                prospective_entry = (
                    float(prospective[0])
                    if prospective is not None
                    else float(intent.requested_trigger)
                )
                if account_snapshot is not None:
                    risk_decision = risk_authority.decide(
                        snapshot=account_snapshot,
                        specification=risk_specification,
                        direction=intent.direction.value,
                        entry=prospective_entry,
                        stop=intent.stop_loss,
                        open_risk_items=_backtest_open_risk(
                            open_positions,
                            mark_price=close,
                            contract_size=contract_size,
                        ),
                        now=now_ts.to_pydatetime(),
                        requested_risk_fraction=risk_policy.base_risk_fraction,
                    )
                if risk_decision is None or not risk_decision.approved:
                    reason = (
                        "INVALID_SIMULATED_EQUITY"
                        if risk_decision is None
                        else risk_decision.reason.value
                    )
                    no_trade_counts[f"risk_{reason.lower()}"] += 1
                    entry_decision = None
                else:
                    entry_decision = process_entry_event(
                        pending_entry.entry_state,
                        base_event,
                        tolerance=pending_entry.tolerance,
                    )
            if entry_decision is None:
                pass
            else:
                pending_entry.entry_state = entry_decision.state
                if entry_decision.state.status in (
                    LifecycleStatus.EXPIRED,
                    LifecycleStatus.CANCELLED,
                    LifecycleStatus.REJECTED,
                ):
                    no_trade_counts[f"pending_{entry_decision.state.status.value.lower()}"] += 1
                    pending_entry = None
                elif entry_decision.triggered:
                    assert risk_decision is not None and risk_decision.normalized_volume is not None
                    fill_price = float(entry_decision.proposed_fill_price)
                    intent = entry_decision.state.intent
                    lot = float(risk_decision.normalized_volume)
                    if not risk_engine.validate_rr(fill_price, intent.stop_loss, intent.final_target):
                        no_trade_counts["filled_rr_below_orchestrator_minimum"] += 1
                    else:
                        filled = record_fill(
                            entry_decision.state,
                            base_event,
                            fill_price=fill_price,
                            quantity=lot,
                            fill_kind=entry_decision.fill_kind or FillKind.SIMULATED_TRIGGER,
                            initial_risk_account_currency=risk_decision.estimated_normalized_loss,
                            adapter_metadata={
                                "source": "shadow_backtest",
                                "configuration_id": intent.configuration_id,
                                "ticket": ticket_seq,
                                "sl_reason": pending_entry.sl_reason,
                                "score": pending_entry.score,
                                "grade": pending_entry.grade,
                                "setup_id": pending_entry.setup_id,
                                "risk_decision_id": risk_decision.decision_id,
                            },
                        )
                        ticket_seq += 1
                        state.mark_entry_filled()
                        first_management = manage_position(filled, base_event, lifecycle_config)
                        managed = first_management.position
                        realized_pnl += managed.realized_gross_pnl
                        booked_gross_by_trade[managed.trade_id] = managed.realized_gross_pnl
                        action_counts["entry_triggered"] += 1
                        for action in first_management.actions:
                            action_counts[f"lifecycle_{action.action_type.value.lower()}"] += 1
                        if managed.status is LifecycleStatus.CLOSED:
                            trade_cost = cost.round_trip(managed.initial_quantity)
                            total_costs += trade_cost
                            realized_pnl -= trade_cost
                            net_pnl = managed.realized_gross_pnl - trade_cost
                            _consume_backtest_outcome(risk_authority, managed)
                            trades.append(_lifecycle_trade_record(managed, net_pnl, trade_cost))
                            booked_gross_by_trade.pop(managed.trade_id, None)
                        else:
                            open_positions.append(managed)
                    pending_entry = None

        try:
            account_snapshot = _refresh_backtest_risk(
                risk_authority,
                account_ref=risk_account_ref,
                capital=capital,
                realized_pnl=realized_pnl,
                positions=open_positions,
                mark_price=close,
                contract_size=contract_size,
                timestamp=now_ts.to_pydatetime(),
            )
        except (ValueError, TypeError):
            account_snapshot = None

        equity_value = (
            account_snapshot.equity
            if account_snapshot is not None
            else capital + realized_pnl
        )
        equity_rows.append({"timestamp": now_ts.isoformat(), "equity": round(equity_value, 4), "open_positions": len(open_positions)})

        if idx % 500 == 0:
            print(f"[SHADOW PROGRESS] {idx}/{total} ({(idx / max(total, 1)) * 100:.1f}%)", flush=True)

        if pending_entry is not None:
            action_counts["wait"] += 1
            no_trade_counts["pending_entry_wait"] += 1
            continue

        if len(open_positions) >= pair_limit:
            action_counts["skip"] += 1
            no_trade_counts["max_concurrent_trades_hit"] += 1
            continue

        if account_snapshot is None:
            action_counts["halt"] += 1
            no_trade_counts["risk_invalid_simulated_equity"] += 1
            continue
        if risk_authority.state.circuit_status is not CircuitStatus.ACTIVE:
            action_counts["halt"] += 1
            no_trade_counts[
                f"risk_{risk_authority.state.circuit_status.value.lower()}"
            ] += 1
            continue

        tf_frames = {}
        for tf in ("W1", "D1", "H4", "H1", "M15"):
            df = data_frames.get(tf)
            pos_arr = tf_positions.get(tf)
            end_pos = int(pos_arr[i]) if pos_arr is not None and i < len(pos_arr) and pos_arr[i] > 0 else 0
            if df is not None and end_pos > 0:
                start_row = max(0, end_pos - 320)
                tf_frames[tf] = df.iloc[start_row:end_pos].copy()
            else:
                tf_frames[tf] = pd.DataFrame()
        m5_end_pos = int(m5_positions[i]) if i < len(m5_positions) and m5_positions[i] > 0 else 0
        entry_slice = entry_df_all.iloc[max(0, m5_end_pos - entry_bars):m5_end_pos].copy() if m5_end_pos > 0 else pd.DataFrame()
        h1_slice = tf_frames["H1"].tail(structure_bars).copy()
        m15_slice = tf_frames["M15"].tail(220).copy()
        d1_slice = tf_frames["D1"].tail(10).copy()
        w1_slice = tf_frames["W1"].tail(10).copy()

        missing_timeframes = [tf for tf, frame in tf_frames.items() if frame.empty]
        if entry_slice.empty or missing_timeframes:
            action_counts["skip"] += 1
            suffix = ",".join(missing_timeframes or [entry_tf])
            no_trade_counts[f"insufficient_completed_htf_history:{suffix}"] += 1
            continue
        if any((frame["available_at"] > now_ts).any() for frame in tf_frames.values()):
            raise RuntimeError("Causal HTF snapshot contains future candles")

        session_context = get_session_context(now_ts.to_pydatetime())
        state.update_session(session_context)
        if not session_context.get("session_allowed", False):
            action_counts["skip"] += 1
            no_trade_counts["session_closed"] += 1
            continue
        news_status = get_news_status(symbol, now_ts.to_pydatetime())
        state.update_news(news_status)
        if not news_status.get("news_clear", False):
            action_counts["pause"] += 1
            no_trade_counts["news_blackout"] += 1
            continue
        # Initialize setup logging for this iteration
        setup_id = generate_setup_id(symbol, timestamp=now_ts.to_pydatetime())
        gate_results = {}
        market_conditions = {}
        timing_info = {"evaluation_start": now_ts.to_pydatetime().isoformat()}
        
        # Gate 1: Session/killzone check
        session_context = get_session_context(now_ts.to_pydatetime())
        gate_results["gate_1_session"] = {
            "pass": session_context.get("session_allowed", False),
            "raw": session_context
        }
        if not session_context.get("session_allowed", False):
            action_counts["skip"] += 1
            no_trade_counts["bad_hour_filter_skipped"] += 1
            log_setup_evaluation(
                setup_id=setup_id,
                symbol=symbol,
                action="skip",
                reason="bad_hour_filter_skipped",
                gate_results=gate_results,
                market_conditions=market_conditions,
                timing_info=timing_info,
                outcome="rejected",
                outcome_detail="bad_hour_filter_skipped"
            )
            continue

        bias_key = tuple(_last_index_key(tf_frames.get(tf)) for tf in ("W1", "D1", "H4", "H1", "M15"))
        bias_snapshot = bias_cache.get(bias_key)
        if bias_snapshot is None:
            bias_snapshot = _build_bias_snapshot(tf_frames)
            bias_cache[bias_key] = bias_snapshot
        state.update_bias(bias_snapshot)
        bias_resolution = resolve_trade_bias(bias_snapshot)
        htf_bias = str(bias_resolution.get("direction", "neutral"))
        
        gate_results["gate_6_htf_bias"] = {
            "pass": htf_bias in ("bullish", "bearish"),
            "raw": {"bias": htf_bias, "resolution": bias_resolution}
        }
        
        if htf_bias not in ("bullish", "bearish"):
            state.reject_setup("htf_bias_unconfirmed")
            action_counts["skip"] += 1
            no_trade_counts["htf_bias_unconfirmed"] += 1
            log_setup_evaluation(
                setup_id=setup_id,
                symbol=symbol,
                action="skip",
                reason="htf_bias_unconfirmed",
                gate_results=gate_results,
                market_conditions=market_conditions,
                timing_info=timing_info,
                outcome="rejected",
                outcome_detail="htf_bias_unconfirmed"
            )
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
        
        gate_results["gate_8_liquidity"] = {
            "pass": bool(liquidity_signal),
            "raw": liquidity_signal
        }
        
        if not liquidity_signal:
            state.reject_setup("liquidity_sweep_missing")
            action_counts["wait"] += 1
            no_trade_counts["liquidity_sweep_missing"] += 1
            log_setup_evaluation(
                setup_id=setup_id,
                symbol=symbol,
                action="wait",
                reason="liquidity_sweep_missing",
                gate_results=gate_results,
                market_conditions=market_conditions,
                timing_info=timing_info,
                outcome="rejected",
                outcome_detail="liquidity_sweep_missing"
            )
            continue
        if liquidity_signal.get("side") in ("buy", "sell"):
            state.update_liquidity(side=liquidity_signal["side"], index=int(idx), liquidity_type=liquidity_signal.get("type"))
            timing_info["sweep_detected"] = now_ts.to_pydatetime().isoformat()

        displacement = detect_displacement(
            entry_slice,
            htf_bias,
            atr_period=14,
            impulse_atr_mult=float(profile.get("displacement", {}).get("impulse_atr_mult", 1.2)),
            lookback_candles=int(profile.get("displacement", {}).get("lookback_candles", 3)),
        )
        displacement = displacement if isinstance(displacement, dict) else {}
        
        gate_results["gate_9_displacement"] = {
            "pass": bool(displacement.get("valid")),
            "raw": displacement
        }
        
        if not bool(displacement.get("valid")):
            state.reject_setup("displacement_missing")
            action_counts["wait"] += 1
            no_trade_counts["displacement_missing"] += 1
            log_setup_evaluation(
                setup_id=setup_id,
                symbol=symbol,
                action="wait",
                reason="displacement_missing",
                gate_results=gate_results,
                market_conditions=market_conditions,
                timing_info=timing_info,
                outcome="rejected",
                outcome_detail="displacement_missing"
            )
            continue
        state.update_displacement(displacement.get("fvg"))
        timing_info["displacement_detected"] = now_ts.to_pydatetime().isoformat()

        internal_structure_key = _last_index_key(m15_slice)
        internal_structure = internal_structure_cache.get(internal_structure_key)
        if internal_structure is None:
            analyzed_internal = analyze_market_structure(m15_slice, silent=True) if not m15_slice.empty else {}
            internal_structure = analyzed_internal if isinstance(analyzed_internal, dict) else {}
            internal_structure_cache[internal_structure_key] = internal_structure
        
        # Gate 10: Internal M15 BOS/CHoCH
        internal_event = internal_structure.get("event") if internal_structure else None
        internal_early_event = (internal_structure.get("early_event") or {}).get("event") if internal_structure else None
        has_internal_confirmation = internal_event in ("BOS", "CHOCH") or internal_early_event in ("BOS", "CHOCH")
        
        gate_results["gate_10_internal_structure"] = {
            "pass": has_internal_confirmation,
            "raw": {
                "event": internal_event,
                "early_event": internal_early_event,
                "internal_structure": internal_structure
            }
        }
        
        if not has_internal_confirmation:
            state.reject_setup("internal_structure_missing")
            action_counts["skip"] += 1
            no_trade_counts["internal_structure_missing"] += 1
            log_setup_evaluation(
                setup_id=setup_id,
                symbol=symbol,
                action="skip",
                reason="internal_structure_missing",
                gate_results=gate_results,
                market_conditions=market_conditions,
                timing_info=timing_info,
                outcome="rejected",
                outcome_detail="internal_structure_missing"
            )
            continue
        
        timing_info["internal_structure_detected"] = now_ts.to_pydatetime().isoformat()
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
            "min_score_to_trade": 8,  # Explicitly set threshold
        })
        
        gate_results["gate_11_confluence_score"] = {
            "pass": score_result.get("passes_threshold", False),
            "raw": score_result
        }
        
        if not score_result.get("passes_threshold", False):
            state.reject_setup("score_below_threshold")
            action_counts["skip"] += 1
            no_trade_counts["score_below_threshold"] += 1
            log_setup_evaluation(
                setup_id=setup_id,
                symbol=symbol,
                action="skip",
                reason="score_below_threshold",
                gate_results=gate_results,
                market_conditions=market_conditions,
                timing_info=timing_info,
                outcome="rejected",
                outcome_detail="score_below_threshold"
            )
            continue

        canonical = evaluate_legacy_context(
            adapter="replay",
            symbol=symbol,
            decision_at=now_ts.to_pydatetime(),
            side=htf_bias,
            entry_frame=entry_slice,
            htf_bias=htf_bias,
            dxy_context=dxy_context,
            news_context=news_status,
            session_context=session_context,
            evidence=SetupEvidence(
                bool(structure_context.get("discount_zone") if htf_bias == "bullish" else structure_context.get("premium_zone")),
                bool(ob_result.get("valid")),
                fvg_in_ob_zone,
                bool(liquidity_signal),
            ),
        )
        gate_results["canonical_strategy"] = {
            "pass": canonical.entry_eligible,
            "raw": canonical.to_dict(),
        }
        if not canonical.entry_eligible:
            action_counts["skip"] += 1
            no_trade_counts[f"strategy:{canonical.reasons[0].value}"] += 1
            continue

        entry = determine_entry(symbol, state, close, score_result=score_result, context={
            "ob_zone": ob_zone,
            "fvg_zone": first_fvg,
            "after_london_open": session_context.get("active_session") == "london",
            "asian_liquidity_swept": any(
                pool.get("type") in ("asian_high", "asian_low")
                for pool in liquidity_context.get("liquidity_pools", [])
            ),
            "sweep_rejected": bool(internal_structure.get("event") in ("CHOCH", "BOS")),
            "internal_structure_event": internal_structure.get("event"),
            "htf_zone_alignment": bool(ob_result.get("valid")),
        })
        
        gate_results["gate_12_13_rr_entry"] = {
            "pass": bool(entry),
            "raw": {"entry": entry, "current_price": close}
        }
        
        if not entry:
            action_counts["wait"] += 1
            no_trade_counts["entry_not_ready"] += 1
            log_setup_evaluation(
                setup_id=setup_id,
                symbol=symbol,
                action="wait",
                reason="entry_not_ready",
                gate_results=gate_results,
                market_conditions=market_conditions,
                timing_info=timing_info,
                outcome="rejected",
                outcome_detail="entry_not_ready"
            )
            continue
        timing_info["entry_ready"] = now_ts.to_pydatetime().isoformat()
        
        # Log successful candidate
        log_setup_evaluation(
            setup_id=setup_id,
            symbol=symbol,
            action="candidate_ready",
            reason="setup_passed_all_gates",
            gate_results=gate_results,
            market_conditions=market_conditions,
            timing_info=timing_info,
            trade_metrics={
                "direction": entry.get("direction"),
                "entry_type": entry.get("entry_type"),
                "entry_mode": entry.get("entry_mode"),
                "score": score_result.get("score"),
                "grade": score_result.get("grade"),
            },
            outcome="taken",
            outcome_detail="candidate_ready"
        )
        
        direction = str(entry.get("direction", "")).lower()
        if direction not in ("buy", "sell"):
            action_counts["skip"] += 1
            no_trade_counts["invalid_entry_direction"] += 1
            continue
        readiness_style = (
            ReadinessStyle.PULLBACK
            if entry.get("entry_type") == "limit"
            else ReadinessStyle.IMMEDIATE
        )
        if readiness_style is ReadinessStyle.PULLBACK and entry.get("limit_entry") is None:
            action_counts["skip"] += 1
            no_trade_counts["missing_limit_price"] += 1
            continue
        requested_trigger = (
            float(entry["limit_entry"])
            if readiness_style is ReadinessStyle.PULLBACK
            else close
        )

        entry_with_zone = dict(entry)
        if ob_zone:
            entry_with_zone["ob_zone"] = ob_zone
        sl, tp, level_reason = _build_orchestrator_trade_levels(
            symbol_info,
            direction,
            requested_trigger,
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
        if not risk_engine.validate_rr(requested_trigger, sl, tp):
            action_counts["skip"] += 1
            no_trade_counts["rr_below_orchestrator_minimum"] += 1
            continue

        signal_intent = new_entry_intent(
            symbol=symbol,
            direction=LifecycleDirection(direction),
            source_timeframe=entry_tf,
            source_candle_open_time=candle_open_time.to_pydatetime(),
            signal_available_at=now_ts.to_pydatetime(),
            requested_trigger=requested_trigger,
            stop_loss=float(sl),
            final_target=float(tp),
            readiness_style=readiness_style,
            partial_close_fraction=lifecycle_config.partial_close_fraction,
            expires_at=(now_ts + pd.Timedelta(minutes=STATE_EXPIRY_MINUTES)).to_pydatetime(),
            source_event_id=base_event.source_candle_id,
            source_sequence=idx,
            strategy_metadata={"setup_id": setup_id, "score": score_result.get("score")},
            configuration_id=f"{symbol}:{entry_tf}:phase3",
        )
        signal_atr = float(calculate_atr(entry_slice, period=14) or 0.0)
        tolerance = (
            max(point * 50, signal_atr * 0.05)
            if readiness_style is ReadinessStyle.PULLBACK
            else 0.0
        )
        pending_entry = PendingEntry(
            entry_state=create_entry_state(signal_intent),
            sl_reason=str(level_reason),
            score=int(score_result.get("score", 0) or 0),
            grade=str(score_result.get("grade", "")),
            setup_id=setup_id,
            tolerance=tolerance,
        )
        action_counts["candidate_created"] += 1

    for pos in open_positions:
        last_close = float(test_rows["close"].iloc[-1]) if not test_rows.empty else pos.fill_price
        end_event = MarketEvent(
            event_id=stable_id(pos.trade_id, "end_of_backtest", end.isoformat()),
            timestamp=as_utc_timestamp(end, field="backtest end close").to_pydatetime(),
            symbol=symbol,
            source="shadow_backtest",
            kind=MarketEventKind.BAR,
            sequence=total + 1,
            open=last_close,
            high=last_close,
            low=last_close,
            close=last_close,
            bar_open_time=as_utc_timestamp(end, field="backtest end bar").to_pydatetime(),
        )
        closed = force_close(pos, end_event, lifecycle_config).position
        previous_gross = booked_gross_by_trade.get(pos.trade_id, 0.0)
        realized_pnl += closed.realized_gross_pnl - previous_gross
        trade_cost = cost.round_trip(closed.initial_quantity)
        total_costs += trade_cost
        realized_pnl -= trade_cost
        trades.append(
            _lifecycle_trade_record(
                closed,
                closed.realized_gross_pnl - trade_cost,
                trade_cost,
            )
        )
        _consume_backtest_outcome(risk_authority, closed)

    trades_path = out_dir / "shadow_mode_trades.csv"
    equity_path = out_dir / "shadow_mode_equity_curve.csv"
    summary_path = out_dir / "shadow_mode_summary.json"
    existing_outputs = [path for path in (trades_path, equity_path, summary_path) if path.exists()]
    if existing_outputs:
        raise FileExistsError(
            "legacy shadow results are immutable; choose a new output directory"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_rows)
    trades_df.to_csv(trades_path, index=False)
    equity_df.to_csv(equity_path, index=False)

    pnl_series = trades_df["pnl"].astype(float) if not trades_df.empty else pd.Series(dtype=float)
    wins = int((pnl_series > 0).sum())
    losses = int((pnl_series < 0).sum())
    reasons = trades_df["reason"] if ("reason" in trades_df.columns) else pd.Series(dtype=str)
    tp_hit_wins = int(((reasons == "TAKE_PROFIT") & (pnl_series > 0)).sum()) if not trades_df.empty else 0
    trail_profit_exits = int(((reasons != "TAKE_PROFIT") & (pnl_series > 0)).sum()) if not trades_df.empty else 0
    gross_profit = float(pnl_series[pnl_series > 0].sum()) if not pnl_series.empty else 0.0
    gross_loss = float(pnl_series[pnl_series < 0].sum()) if not pnl_series.empty else 0.0
    equity_series = capital + pnl_series.cumsum() if not pnl_series.empty else pd.Series([capital])
    max_dd = float((equity_series.cummax() - equity_series).max()) if not equity_series.empty else 0.0
    summary = {
        "result_label": "DIAGNOSTIC \u2014 NOT VALIDATED",
        "fidelity_class": (
            "MID_BAR_WITH_ASSUMED_COSTS"
            if any(value > 0 for value in (spread_points, slippage_points, commission_per_lot))
            else "INSUFFICIENT_FOR_VALIDATION"
        ),
        "validation_eligible": False,
        "profitability_evidence": False,
        "execution_model_version": "legacy-shadow-bar-v1",
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
        "risk_policy": {
            "version": risk_policy.policy_version,
            "base_risk_fraction": risk_policy.base_risk_fraction,
            "absolute_risk_ceiling": risk_policy.absolute_risk_ceiling,
            "aggregate_open_risk_ceiling": risk_policy.aggregate_open_risk_ceiling,
        },
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
            "This compatibility runner is diagnostic and cannot create Phase 7 validation evidence.",
            "Its neutral OHLC bars are not bid/ask quotes and have no observed intrabar path.",
            "All-session trading is enabled; session is context only, not a trade gate.",
            "Synthetic DXY uses the repaired DataFrame-safe basket logic and contributes to confluence scoring.",
            "Liquidity/FVG/OB payloads are normalized defensively like the live orchestrator.",
            "Confluence grades are strategy metadata and have no monetary-risk authority.",
            "Entries use the shared Phase 4 equity, exposure, sizing, and circuit policy.",
            "Floating equity is sampled at completed-bar close; tick-level path realism remains deferred.",
            "Configured costs are assumed and applied as a legacy round-trip aggregate after closure.",
            "Commission currency conversion and broker rollover swap are not represented here.",
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
    parser.add_argument(
        "--trail-mode",
        default="live_atr_3x",
        choices=["live_atr_3x"],
        help="Shared Phase 3 lifecycle trailing policy.",
    )
    parser.add_argument("--min-rr", type=float, default=None,
                        help="Retained for compatibility but rejected because Phase 6 strategy is frozen.")
    parser.add_argument("--spread-points", type=float, default=0.0,
                        help="Round-trip spread in broker points (e.g. XAU 20 = $0.20).")
    parser.add_argument("--slippage-points", type=float, default=0.0,
                        help="Per-side slippage in broker points.")
    parser.add_argument("--commission-per-lot", type=float, default=0.0,
                        help="Round-turn commission per lot in account currency.")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Acknowledge that this legacy mid-bar run is diagnostic and not validated.",
    )
    args = parser.parse_args()

    if not args.diagnostic:
        raise SystemExit(
            "Phase 7 requires --diagnostic for the legacy mid-bar runner; "
            "validation requires offline bid/ask data and broker metadata"
        )
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
