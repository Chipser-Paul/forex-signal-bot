from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Callable, TYPE_CHECKING

from bot.analysis import build_liquidity_map, get_bias_snapshot, resolve_trade_bias
from bot.analysis.dxy_filter import analyze_dxy_correlation
from bot.execution.news_filter import get_news_status
from bot.strategy.config import PRODUCTION_EXECUTABLE_SYMBOLS
from bot.strategy.config import StrategyConfig
from bot.strategy.setup_state import STATE_FIELDS, record_from_state, state_from_record
from bot.state.gate_inputs import GateInputError, build_gate_inputs
from bot.state.gate_reducer import evaluate_strategy_gates
from bot.utils.session_clock import get_session_context
from strategies.smc_engine.strategy_state import StrategyState
from utils.log import log
from utils.symbol_profiles import get_symbol_profile
from utils.setup_logger import log_setup_evaluation


if TYPE_CHECKING:
    from bot.execution.risk_engine import RiskEngine


def fetch_ohlcv(*args, **kwargs):
    """Live-only acquisition; offline imports never load the terminal module."""
    from bot.data.market_data import fetch_ohlcv as fetch

    return fetch(*args, **kwargs)


@dataclass(frozen=True)
class OrchestratorAcquisition:
    candles: Callable
    session: Callable
    news: Callable
    bias: Callable
    liquidity: Callable
    dxy: Callable


@dataclass
class OrchestratorResult:
    action: str
    state_name: str
    reason: str
    context: dict


class StrategyOrchestrator:
    def __init__(
        self, risk_engine: RiskEngine | None = None, *,
        acquisition: OrchestratorAcquisition | None = None,
        emit_diagnostics: bool = True,
    ):
        if risk_engine is None:
            from bot.execution.risk_engine import RiskEngine

            risk_engine = RiskEngine()
        self.risk_engine = risk_engine
        self.acquisition = acquisition
        self.emit_diagnostics = emit_diagnostics

    def _record_setup(self, **kwargs):
        if self.emit_diagnostics:
            log_setup_evaluation(**kwargs)

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
        event_at: datetime | None = None,
    ) -> OrchestratorResult:
        """
        Evaluate a symbol through all 13 gates and return orchestrator result.
        """
        # Initialize setup logging structures
        _now_utc = event_at or datetime.now(timezone.utc)
        if _now_utc.tzinfo is None or _now_utc.utcoffset() is None:
            raise ValueError("orchestrator event time must be timezone-aware")
        _now_utc = _now_utc.astimezone(timezone.utc)
        setup_id = "pre8n_" + hashlib.sha256(
            f"phase8n.preflight.v1|{symbol}|{_now_utc.isoformat()}".encode("utf-8")
        ).hexdigest()[:32]
        gate_results: dict[str, object] = {}
        market_conditions: dict[str, object] = {}
        timing_info: dict[str, object] = {}
        
        context: dict[str, object] = {"symbol": symbol, "setup_id": setup_id}
        current_price = 0.0
        acquisition = self.acquisition or OrchestratorAcquisition(
            fetch_ohlcv, get_session_context, get_news_status,
            get_bias_snapshot, build_liquidity_map, analyze_dxy_correlation,
        )

        if symbol not in PRODUCTION_EXECUTABLE_SYMBOLS:
            return OrchestratorResult("skip", state.state_name, "symbol_not_executable", context)

        try:
            # Profiles are evaluation inputs and must not mutate shared risk policy.
            profile = get_symbol_profile(symbol)
            if profile and "min_rr" in profile:
                context["profile_min_rr"] = float(profile["min_rr"])

            # Get current market price for metadata
            try:
                sample_df = acquisition.candles(symbol, "M5", bars=1)
                if sample_df is not None and not sample_df.empty:
                    current_price = float(sample_df["close"].iloc[-1])
            except Exception:
                current_price = 0.0

            # GATE 1: SESSION / KILLZONE CHECK
            state.set_event_time(_now_utc)
            
            gate_results["gate_1_session"] = {
                "pass": False,
                "raw": {"weekday": _now_utc.weekday(), "hour_utc": _now_utc.hour}
            }
            
            hour_utc = _now_utc.hour
            session_context = acquisition.session(_now_utc)
            gate_results["gate_1_session"]["pass"] = bool(session_context.get("session_allowed", False))
            gate_results["gate_1_session"]["raw"] = session_context
            state.update_session(session_context)
            context["session"] = session_context
            if not session_context.get("session_allowed", False):
                return OrchestratorResult("skip", state.state_name, "session_closed", context)

            # GATE 2: NEWS BLACKOUT CHECK
            news_status_raw = acquisition.news(symbol, now=_now_utc)
            news_status = self._ensure_dict(news_status_raw, "news_status", {"news_clear": False})
            state.update_news(news_status)
            context["news"] = news_status
            
            gate_results["gate_2_news"] = {
                "pass": news_status.get("news_clear", False),
                "raw": news_status
            }

            if not news_status.get("news_clear", False):
                self._record_setup(
                    setup_id=setup_id,
                    symbol=symbol,
                    action="pause",
                    reason="news_blackout",
                    gate_results=gate_results,
                    market_conditions=market_conditions,
                    timing_info=timing_info,
                    outcome="rejected",
                    outcome_detail="news_blackout"
                )
                return OrchestratorResult(
                    action="pause",
                    state_name=state.state_name,
                    reason="news_blackout",
                    context=context,
                )

            # Gate 4 is enforced by the Phase 4 account-level risk authority after
            # stop construction and before lifecycle entry eligibility.  Keeping a
            # diagnostic placeholder preserves the established gate ordering
            # without allowing configured capital or realized-only P&L to decide.
            gate_results["gate_4_daily_limit"] = {
                "pass": True,
                "raw": {
                    "authority": "phase4_account_risk",
                    "legacy_inputs_ignored": True,
                },
            }
            state.set_daily_limit_hit(False)

            # GATE 5: MAX CONCURRENT TRADES CHECK
            can_open_more = self.risk_engine.can_open_more_trades(active_trade_count)
            gate_results["gate_5_concurrent_trades"] = {
                "pass": can_open_more,
                "raw": {"active_trade_count": active_trade_count, "max_trades": self.risk_engine.max_concurrent_trades}
            }
            
            if not can_open_more:
                self._record_setup(
                    setup_id=setup_id,
                    symbol=symbol,
                    action="skip",
                    reason="max_concurrent_trades_hit",
                    gate_results=gate_results,
                    market_conditions=market_conditions,
                    timing_info=timing_info,
                    outcome="rejected",
                    outcome_detail="max_concurrent_trades_hit"
                )
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

            bias_snapshot = acquisition.bias(symbol, silent=True)
            bias_snapshot = self._ensure_dict(bias_snapshot, "bias_snapshot")
            state.update_bias(bias_snapshot)
            context["bias"] = bias_snapshot
            bias_resolution = resolve_trade_bias(bias_snapshot)
            bias_resolution = self._ensure_dict(bias_resolution, "bias_resolution")
            context["bias_resolution"] = bias_resolution
            htf_bias = str(bias_resolution.get("direction", "neutral"))
            
            gate_results["gate_6_htf_bias"] = {
                "pass": htf_bias in ("bullish", "bearish"),
                "raw": {"htf_bias": htf_bias, "bias_snapshot": bias_snapshot}
            }

            if htf_bias not in ("bullish", "bearish"):
                state.reject_setup("htf_bias_unconfirmed")
                self._record_setup(
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
                return OrchestratorResult(
                    action="skip",
                    state_name=state.state_name,
                    reason="htf_bias_unconfirmed",
                    context=context,
                )

            # Completed-trade loss streaks are enforced once by the Phase 4
            # account-level circuit.  The legacy directional cascade remains in
            # StrategyState only for backward-compatible record loading.
            gate_results["cascade_breaker"] = {
                "pass": True,
                "raw": {"authority": "phase4_account_risk", "legacy_disabled": True},
            }

            # GATE 7: DXY CORRELATION CHECK
            if symbol.startswith("XAU"):
                dxy_context_raw = acquisition.dxy(symbol, silent=True, decision_timestamp=_now_utc)
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
            
            gate_results["gate_7_dxy"] = {
                "pass": bool(dxy_context.get("available")) and not bool(dxy_context.get("reduce_size")),
                "raw": dxy_context
            }
            if not gate_results["gate_7_dxy"]["pass"]:
                return OrchestratorResult("skip", state.state_name, "dxy_unsafe_or_conflicting", context)

            # GATES 8–13: acquisition stays here; decisions use one shared reducer.
            liquidity_context_raw = acquisition.liquidity(symbol, silent=True)
            liquidity_context = self._ensure_dict(liquidity_context_raw, "liquidity_context")
            liquidity_context["structure_context"] = self._ensure_dict(
                liquidity_context.get("structure_context"), "liquidity_context.structure_context",
            )
            liquidity_context["liquidity_pools"] = self._ensure_dict_list(
                liquidity_context.get("liquidity_pools"), "liquidity_context.liquidity_pools",
            )
            structure_df = acquisition.candles(symbol, structure_tf, bars=structure_bars)
            entry_df = acquisition.candles(symbol, entry_tf, bars=entry_bars)
            internal_df = acquisition.candles(symbol, "M15", bars=220)
            if structure_df is None or structure_df.empty or entry_df is None or entry_df.empty:
                gate_results["gate_8_liquidity"] = {
                    "pass": False, "raw": {"reason": "insufficient_market_data"},
                }
                self._record_setup(
                    setup_id=setup_id, symbol=symbol, action="wait",
                    reason="insufficient_market_data", gate_results=gate_results,
                    market_conditions=market_conditions, timing_info=timing_info,
                    outcome="rejected", outcome_detail="insufficient_market_data",
                )
                return OrchestratorResult("wait", state.state_name, "insufficient_market_data", context)

            policy = StrategyConfig()
            try:
                inputs = build_gate_inputs(
                    symbol=symbol, event_at=_now_utc,
                    frames={"H1": structure_df, "M5": entry_df, "M15": internal_df},
                    profile=profile, htf_bias=htf_bias, bias_snapshot=bias_snapshot,
                    bias_resolution=bias_resolution,
                    liquidity_context=liquidity_context, dxy_context=dxy_context,
                    news_context=news_status, session_context=session_context,
                    config=policy,
                )
            except GateInputError:
                gate_results["gate_8_liquidity"] = {
                    "pass": False, "raw": {"reason": "causal_input_unsafe"},
                }
                self._record_setup(
                    setup_id=setup_id, symbol=symbol, action="wait",
                    reason="causal_input_unsafe", gate_results=gate_results,
                    market_conditions=market_conditions, timing_info=timing_info,
                    outcome="rejected", outcome_detail="causal_input_unsafe",
                )
                return OrchestratorResult("wait", state.state_name, "causal_input_unsafe", context)

            cached = getattr(state, "_gate_record", None)
            if cached is not None and cached.data()["last_event_id"] == inputs.event_id:
                prior = cached
            else:
                previous = cached.data() if cached is not None else {}
                prior = record_from_state(
                    state, event_at=_now_utc,
                    last_event_id=previous.get("last_event_id"),
                    last_result=previous.get("last_result"),
                )
            transition = evaluate_strategy_gates(prior, inputs, _now_utc, policy)
            next_state = state_from_record(transition.state_record, _now_utc)
            for field in STATE_FIELDS:
                setattr(state, field, getattr(next_state, field))
            state._setup_consumption = next_state._setup_consumption
            state._gate_record = transition.state_record

            gate_result = transition.result()
            setup_id = transition.setup_id
            context.update(gate_result["context"])
            gate_results.update(gate_result["gate_results"])
            timing_info.update(gate_result["timing_info"])
            market_conditions.update(gate_result["market_conditions"])
            action = gate_result["action"]
            reason = gate_result["reason"]
            self._record_setup(
                setup_id=setup_id, symbol=symbol, action=action, reason=reason,
                gate_results=gate_results, market_conditions=market_conditions,
                timing_info=timing_info,
                trade_metrics={
                    "direction": (context.get("entry") or {}).get("direction"),
                    "entry_type": (context.get("entry") or {}).get("entry_type"),
                    "entry_mode": (context.get("entry") or {}).get("entry_mode"),
                    "score": (context.get("score") or {}).get("score"),
                    "grade": (context.get("score") or {}).get("grade"),
                } if action == "candidate_ready" else None,
                outcome="taken" if action == "candidate_ready" else "rejected",
                outcome_detail="candidate_ready" if action == "candidate_ready" else reason,
            )
            return OrchestratorResult(action, state.state_name, reason, context)
        except Exception as e:
            if not self.emit_diagnostics:
                context["error_type"] = type(e).__name__
                return OrchestratorResult("error", state.state_name, "orchestrator_input_unsafe", context)
            import traceback
            err_msg = str(e)
            tb = traceback.format_exc()
            log(f"[ORCH-ERROR] {symbol}: {err_msg}", "red")
            log(f"[ORCH-TRACE] {symbol}:\n{tb}", "red")
            
            # Log the error to setup logger
            self._record_setup(
                setup_id=setup_id,
                symbol=symbol,
                action="error",
                reason=f"orchestrator_live_error: {err_msg}",
                gate_results=gate_results,
                market_conditions=market_conditions,
                timing_info=timing_info,
                outcome="rejected",
                outcome_detail=f"error: {type(e).__name__}"
            )
            
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
        finally:
            context["gate_results"] = gate_results
            context["timing_info"] = timing_info
            context["market_conditions"] = market_conditions
