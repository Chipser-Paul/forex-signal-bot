from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os

from bot.analysis import build_liquidity_map, get_bias_snapshot, get_unfilled_fvgs, resolve_trade_bias
from bot.analysis.dxy_filter import analyze_dxy_correlation
from bot.data.market_data import fetch_ohlcv
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
from utils.indicators import calculate_atr
from utils.log import log
from utils.symbol_profiles import get_symbol_profile


@dataclass
class OrchestratorResult:
    action: str
    state_name: str
    reason: str
    context: dict


class StrategyOrchestrator:
    def __init__(self, risk_engine: RiskEngine | None = None):
        self.risk_engine = risk_engine or RiskEngine()

    @staticmethod
    def _ensure_dict(val, name: str, default: dict | None = None) -> dict:
        """Coerce a value to a dict, logging a warning if the type is wrong."""
        if isinstance(val, dict):
            return val
        if val is not None:
            log(f"[ORCH] Expected dict for {name}, got {type(val).__name__}: {val!r}", "yellow")
        return default if default is not None else {}

    @staticmethod
    def _ensure_dict_list(val, name: str) -> list[dict]:
        """Return only dict items from a list-like payload and log dropped items."""
        if val is None:
            return []
        if not isinstance(val, list):
            log(f"[ORCH] Expected list for {name}, got {type(val).__name__}: {val!r}", "yellow")
            return []

        cleaned: list[dict] = []
        for idx, item in enumerate(val):
            if isinstance(item, dict):
                cleaned.append(item)
            else:
                log(
                    f"[ORCH] Dropping non-dict item from {name}[{idx}]: "
                    f"{type(item).__name__} {item!r}",
                    "yellow",
                )
        return cleaned

    def evaluate_symbol(
        self,
        symbol: str,
        state: StrategyState,
        *,
        account_balance: float,
        daily_pnl: float,
        active_trade_count: int,
    ) -> OrchestratorResult:
        """
        Evaluate a symbol through all 13 gates and return orchestrator result.
        """
        context: dict[str, object] = {"symbol": symbol}
        current_price = 0.0

        try:
            # Get current market price for metadata
            try:
                sample_df = fetch_ohlcv(symbol, "M5", bars=1)
                if sample_df is not None and not sample_df.empty:
                    current_price = float(sample_df["close"].iloc[-1])
            except Exception:
                current_price = 0.0

            # GATE 1: SESSION / KILLZONE CHECK
            from datetime import datetime as _dt, timezone as _tz
            _now_utc = _dt.now(_tz.utc)
            if _now_utc.weekday() == 6:  # Sunday = 6
                return OrchestratorResult(
                    action="skip",
                    state_name=state.state_name,
                    reason="sunday_filter",
                    context=context,
                )
            hour_utc = _now_utc.hour
            if hour_utc in (0, 11):  # Bad hours — 00:00 and 11:00 UTC historically unprofitable
                return OrchestratorResult(
                    action="skip",
                    state_name=state.state_name,
                    reason=f"bad_hour_{hour_utc}",
                    context=context,
                )
            session_context = get_session_context()
            state.update_session(session_context)
            context["session"] = session_context

            # GATE 2: NEWS BLACKOUT CHECK
            news_status_raw = get_news_status(symbol)
            news_status = self._ensure_dict(news_status_raw, "news_status", {"news_clear": True})
            state.update_news(news_status)
            context["news"] = news_status

            if not news_status.get("news_clear", True):
                return OrchestratorResult(
                    action="pause",
                    state_name=state.state_name,
                    reason="news_blackout",
                    context=context,
                )

            # GATE 4: DAILY LOSS LIMIT CHECK
            daily_pnl_pct = (daily_pnl / account_balance * 100) if account_balance > 0 else 0.0

            if self.risk_engine.check_daily_drawdown(daily_pnl, account_balance):
                state.set_daily_limit_hit(True, "daily_drawdown_limit_hit")
                return OrchestratorResult(
                    action="halt",
                    state_name=state.state_name,
                    reason="daily_drawdown_limit_hit",
                    context=context,
                )
            state.set_daily_limit_hit(False)

            # GATE 5: MAX CONCURRENT TRADES CHECK
            if not self.risk_engine.can_open_more_trades(active_trade_count):
                return OrchestratorResult(
                    action="skip",
                    state_name=state.state_name,
                    reason="max_concurrent_trades_hit",
                    context=context,
                )

            # GATE 6: HTF BIAS CONFIRMATION (Weekly + Daily + H4 structure)
            profile = get_symbol_profile(symbol)
            structure_tf = profile.get("structure_tf", "H1")
            entry_tf = profile.get("entry_tf", "M15")
            structure_bars = int(profile.get("structure_bars", 320))
            entry_bars = int(profile.get("entry_bars", 220))

            bias_snapshot = get_bias_snapshot(symbol, silent=True)
            bias_snapshot = self._ensure_dict(bias_snapshot, "bias_snapshot")
            state.update_bias(bias_snapshot)
            context["bias"] = bias_snapshot
            bias_resolution = resolve_trade_bias(bias_snapshot)
            bias_resolution = self._ensure_dict(bias_resolution, "bias_resolution")
            context["bias_resolution"] = bias_resolution
            htf_bias = str(bias_resolution.get("direction", "neutral"))

            if htf_bias not in ("bullish", "bearish"):
                state.reject_setup("htf_bias_unconfirmed")
                return OrchestratorResult(
                    action="skip",
                    state_name=state.state_name,
                    reason="htf_bias_unconfirmed",
                    context=context,
                )

            # CASCADE CIRCUIT BREAKER: block direction after 2 same-direction losses
            if state.is_direction_blocked(htf_bias):
                state.reject_setup(f"cascade_breaker_blocked_{htf_bias}")
                return OrchestratorResult(
                    action="skip",
                    state_name=state.state_name,
                    reason=f"cascade_breaker_blocked_{htf_bias}",
                    context=context,
                )

            # GATE 7: DXY CORRELATION CHECK
            if symbol.startswith("XAU"):
                dxy_context_raw = analyze_dxy_correlation(symbol, silent=True)
                dxy_context = self._ensure_dict(
                    dxy_context_raw, "dxy_context",
                    {"available": False, "confirms_bias": False, "reduce_size": False}
                )
            else:
                dxy_context = {
                    "available": False,
                    "relationship": "not_applicable",
                    "confirms_bias": False,
                    "reduce_size": False,
                    "note": "DXY filter not applied for this symbol.",
                }
            context["dxy"] = dxy_context

            # GATE 8: LIQUIDITY SWEEP CONFIRMATION
            liquidity_context_raw = build_liquidity_map(symbol, silent=True)
            liquidity_context = self._ensure_dict(liquidity_context_raw, "liquidity_context")
            liquidity_context["structure_context"] = self._ensure_dict(
                liquidity_context.get("structure_context"),
                "liquidity_context.structure_context",
            )
            liquidity_context["liquidity_pools"] = self._ensure_dict_list(
                liquidity_context.get("liquidity_pools"),
                "liquidity_context.liquidity_pools",
            )
            context["liquidity"] = liquidity_context

            structure_df = fetch_ohlcv(symbol, structure_tf, bars=structure_bars)
            entry_df = fetch_ohlcv(symbol, entry_tf, bars=entry_bars)
            internal_df = fetch_ohlcv(symbol, "M15", bars=220)
            structure_context = liquidity_context.get("structure_context") or {}
            structure_dir = str(structure_context.get("structure", ""))
            structure_state = str(structure_context.get("state", ""))

            if structure_df is None or structure_df.empty or entry_df is None or entry_df.empty:
                return OrchestratorResult(
                    action="wait",
                    state_name=state.state_name,
                    reason="insufficient_market_data",
                    context=context,
                )

            if structure_dir in ("bullish", "bearish") and structure_state in ("confirmed", "transition", "range"):
                state.update_structure(structure_dir, structure_state)

            liquidity_signal_raw = detect_liquidity_sweep(
                structure_df,
                structure_dir=htf_bias,
                lookback=int(profile.get("liquidity", {}).get("lookback", 20)),
                sweep_window=int(profile.get("liquidity", {}).get("sweep_window", 3)),
            )
            liquidity_signal = self._ensure_dict(liquidity_signal_raw, "liquidity_signal")
            context["liquidity_signal"] = liquidity_signal

            if not liquidity_signal:
                state.reject_setup("liquidity_sweep_missing")
                return OrchestratorResult(
                    action="wait",
                    state_name=state.state_name,
                    reason="liquidity_sweep_missing",
                    context=context,
                )

            side = liquidity_signal.get("side")
            liq_type = liquidity_signal.get("type")
            if side in ("buy", "sell"):
                state.update_liquidity(side=side, index=int(len(structure_df) - 1), liquidity_type=liq_type)

            # GATE 9: OB + FVG ZONE CHECK
            displacement_raw = detect_displacement(
                entry_df,
                htf_bias,
                atr_period=14,
                impulse_atr_mult=float(profile.get("displacement", {}).get("impulse_atr_mult", 1.2)),
                lookback_candles=int(profile.get("displacement", {}).get("lookback_candles", 3)),
            )
            displacement = self._ensure_dict(displacement_raw, "displacement") if displacement_raw else {}
            context["displacement"] = displacement
            displacement_valid = bool(displacement.get("valid"))

            if not displacement_valid:
                state.reject_setup("displacement_missing")
                return OrchestratorResult(
                    action="wait",
                    state_name=state.state_name,
                    reason="displacement_missing",
                    context=context,
                )

            state.update_displacement((displacement or {}).get("fvg") if isinstance(displacement, dict) else None)

            fvgs_raw = get_unfilled_fvgs(entry_df, timeframe=entry_tf, direction=htf_bias) if entry_df is not None else []
            fvgs = self._ensure_dict_list(fvgs_raw, "fvgs")
            context["fvgs"] = fvgs

            internal_structure_raw = analyze_market_structure(internal_df, silent=True) if internal_df is not None and not internal_df.empty else None
            internal_structure = self._ensure_dict(internal_structure_raw, "internal_structure")
            context["internal_structure"] = internal_structure
            
            ob_result_raw = detect_ob_breaker(
                entry_df if entry_df is not None else fetch_ohlcv(symbol, structure_tf, bars=int(profile.get("structure_bars", 220))),
                htf_bias,
                premium_zone=structure_context.get("premium_zone"),
                discount_zone=structure_context.get("discount_zone"),
                equilibrium_level=structure_context.get("equilibrium_level"),
            )
            ob_result = self._ensure_dict(ob_result_raw, "ob_result")
            context["ob"] = ob_result

            # GATE 10: INTERNAL M15 BOS/CHoCH CONFIRMATION
            # GATE 11: CONFLUENCE SCORE (min 8/12 to trade, 10+ = A+)
            first_fvg = fvgs[0] if fvgs else None
            ob_zone = ob_result.get("zone") if ob_result.get("valid") else None
            fvg_in_ob_zone = False
            if first_fvg and ob_zone:
                try:
                    atr_val_for_fvg = float(calculate_atr(entry_df, 14) or 0.0)
                    fvg_tol = atr_val_for_fvg * 0.30
                    fvg_low = float(first_fvg["bottom"])
                    fvg_high = float(first_fvg["top"])
                    ob_low = float(ob_zone[0])
                    ob_high = float(ob_zone[1])
                    # gap if FVG is entirely above or below OB zone
                    if fvg_low > ob_high:
                        gap = fvg_low - ob_high
                    elif fvg_high < ob_low:
                        gap = ob_low - fvg_high
                    else:
                        gap = 0.0
                    fvg_in_ob_zone = gap <= fvg_tol
                except Exception:
                    fvg_in_ob_zone = False

            score_result_raw = score_setup(
                {
                    "htf_bias": htf_bias,
                    "trade_direction": htf_bias,
                    "price_in_discount_or_premium": bool(
                        structure_context.get("discount_zone") if htf_bias == "bullish" else structure_context.get("premium_zone")
                    ),
                    "valid_ob_present": bool((ob_result or {}).get("valid")),
                    "fvg_in_ob_zone": fvg_in_ob_zone,
                    "liquidity_swept_before_entry": bool(liquidity_signal),
                    "internal_bos_on_m15": bool(
                        (internal_structure or {}).get("event") in ("BOS", "CHOCH") or
                        (internal_structure or {}).get("early_event", {}).get("event") in ("BOS", "CHOCH")
                    ),
                    "internal_bos_early": bool(
                        (internal_structure or {}).get("event") not in ("BOS", "CHOCH") and
                        (internal_structure or {}).get("early_event", {}).get("event") in ("BOS", "CHOCH")
                    ),
                    "session_allowed": True,
                    "dxy_confirms_bias": bool((dxy_context or {}).get("confirms_bias")),
                    "no_news_in_30min": bool((news_status or {}).get("news_clear")),
                }
            )
            score_result = self._ensure_dict(
                score_result_raw, "score_result", {"passes_threshold": False, "score": 0, "grade": "F"}
            )
            context["score"] = score_result

            if not score_result.get("passes_threshold", False):
                state.reject_setup("score_below_threshold")
                return OrchestratorResult(
                    action="skip",
                    state_name=state.state_name,
                    reason="score_below_threshold",
                    context=context,
                )

            # SCORE DIRECTION FILTER REMOVED — Gate 11 already enforces ≥8 for all directions.
            # The old filter required bullish ≥10 vs bearish ≥8, creating an unjustified
            # anti-buy bias. 58-trade analysis showed buys outperformed sells (25% WR, +$146.95
            # vs 21.1% WR, +$132.21), so there was no data basis for the higher bar.

            # GATE 12-13: RR VALIDATION (min 1:3), POSITION SIZE, and ENTRY DETERMINATION
            # Note: In the 13-gate system, gates 12-13 represent final RR/position/entry checks before trade signal
            current_price = float(entry_df["close"].iloc[-1]) if entry_df is not None and not entry_df.empty else 0.0
            entry = determine_entry(
                symbol,
                state,
                current_price,
                score_result=score_result,
                context={
                    "ob_zone": ob_zone,
                    "fvg_zone": first_fvg,
                    "after_london_open": session_context.get("active_session") == "london",
                    "asian_liquidity_swept": any(
                        pool.get("type") in ("asian_high", "asian_low")
                        for pool in liquidity_context.get("liquidity_pools", [])
                    ),
                    "sweep_rejected": bool((internal_structure or {}).get("event") in ("CHOCH", "BOS")),
                    "internal_structure_event": (internal_structure or {}).get("event"),
                    "htf_zone_alignment": bool(ob_result.get("valid")),
                },
            )
            context["entry"] = entry

            if entry:
                context["entry"] = entry
                return OrchestratorResult(
                    action="candidate_ready",
                    state_name=state.state_name,
                    reason="setup_passed_all_gates",
                    context=context,
                )
            else:
                context["entry"] = entry
                return OrchestratorResult(
                    action="wait",
                    state_name=state.state_name,
                    reason="entry_not_ready",
                    context=context,
                )

        except Exception as e:
            import traceback
            err_msg = str(e)
            tb = traceback.format_exc()
            log(f"[ORCH-ERROR] {symbol}: {err_msg}", "red")
            log(f"[ORCH-TRACE] {symbol}:\n{tb}", "red")
            # Save full traceback to a file for immediate debugging
            from pathlib import Path as _Path
            from datetime import timezone as _timezone
            err_path = _Path("logs/orchestrator_errors.log")
            err_path.parent.mkdir(exist_ok=True)
            with open(err_path, "a", encoding="utf-8") as _f:
                _f.write(f"{'='*60}\n")
                _f.write(f"time: {datetime.now(_timezone.utc).isoformat()}\n")
                _f.write(f"symbol: {symbol}\n")
                _f.write(f"state: {getattr(state, 'state_name', 'unknown')}\n")
                _f.write(f"{tb}\n")
            # Save to context so main.py can access it if needed
            context["orchestrator_error_details"] = {
                "error_message": err_msg,
                "traceback": tb,
                "error_type": type(e).__name__,
            }
            return OrchestratorResult(
                action="error",
                state_name=getattr(state, "state_name", "unknown"),
                reason=f"orchestrator_live_error: {err_msg}",
                context=context,
            )
