"""
Structured JSON logging system for XAUUSDm trading bot.
Produces human-readable JSON logs for every scan cycle.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

from app_security.redaction import sanitize_mapping


class TradeLog:
    """
    Builds a structured JSON log entry for every scan cycle.
    Accumulates data through set_*() methods and writes to .jsonl and last_scan.json.
    """

    def __init__(self):
        """Initialize empty log structure."""
        self._log: dict[str, Any] = {}
        self._flags: list[dict[str, Any]] = []

    def set_meta(self, symbol: str, price: float, orchestrator_state: str) -> None:
        """
        Set metadata: timestamp, symbol, price, orchestrator state, log version.

        Args:
            symbol: Trading symbol (e.g., "XAUUSDm")
            price: Current bid price
            orchestrator_state: One of SCANNING_FOR_SETUP, 
                               TRADE_ACTIVE, NEWS_BLACKOUT, DAILY_LIMIT_HIT
        """
        self._log["meta"] = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "symbol": symbol,
            "price": float(price) if price is not None else None,
            "orchestrator_state": orchestrator_state,
            "log_version": "2.0",
        }

    def set_session(self, session_data: dict[str, Any]) -> None:
        """
        Set session information. Sessions are context only; they do not block trades.

        Args:
            session_data: dict with keys:
                - active_session: "london" | "new_york" | "asian" | "off_session"
                - session_allowed: bool
                - is_priority_session: bool
                - session_role: "primary_liquidity_window" | "secondary_liquidity_window" | "context" | "off"
                - london_open: str (time)
                - ny_open: str (time)
                - asian_high: float | None
                - asian_low: float | None
        """
        self._log["session"] = {
            "active_session": session_data.get("active_session", "off_session"),
            "session_allowed": bool(session_data.get("session_allowed", True)),
            "is_priority_session": bool(session_data.get("is_priority_session", False)),
            "session_role": session_data.get("session_role", "off"),
            "london_open": session_data.get("london_open", "07:00 UTC"),
            "ny_open": session_data.get("ny_open", "12:30 UTC"),
            "asian_high": session_data.get("asian_high"),
            "asian_low": session_data.get("asian_low"),
        }

    def set_news(self, news_data: dict[str, Any]) -> None:
        """
        Set news filter information.

        Args:
            news_data: dict with keys:
                - news_clear: bool
                - source: "live" | "fallback"
                - next_event_in_minutes: int | None
                - active_event: str | None
                - upcoming_events: list of dicts with name, minutes_away, impact
        """
        self._log["news"] = {
            "news_clear": bool(news_data.get("news_clear", True)),
            "source": news_data.get("source", "live"),
            "next_event_in_minutes": news_data.get("next_event_in_minutes"),
            "active_event": news_data.get("active_event"),
            "upcoming_events": news_data.get("upcoming_events", []),
            "block_window_minutes": {"before": 30, "after": 30},
        }

    def set_daily_state(
        self,
        daily_pnl: float,
        daily_pnl_pct: float,
        daily_limit_hit: bool,
        consecutive_losses: int,
        risk_scale_active: bool,
        current_risk_pct: float,
        open_trades: int,
        max_concurrent: int = 2,
    ) -> None:
        """Set daily P&L and risk state."""
        self._log["daily_state"] = {
            "daily_pnl": float(daily_pnl) if daily_pnl is not None else 0.0,
            "daily_pnl_pct": float(daily_pnl_pct) if daily_pnl_pct is not None else 0.0,
            "daily_limit_hit": bool(daily_limit_hit),
            "consecutive_losses": int(consecutive_losses) if consecutive_losses is not None else 0,
            "risk_scale_active": bool(risk_scale_active),
            "current_risk_pct": float(current_risk_pct) if current_risk_pct is not None else 0.5,
            "open_trades": int(open_trades) if open_trades is not None else 0,
            "max_concurrent": int(max_concurrent),
        }

    def set_structure(self, structure_data: dict[str, Any]) -> None:
        """
        Set market structure information.

        Args:
            structure_data: dict with keys:
                - htf_bias: "bullish" | "bearish" | "neutral" | "conflicting"
                - htf_score: int (range -3 to +3)
                - confidence: float (0.0-1.0)
                - condition: "trending" | "range" | "transitioning"
                - last_event: "BOS" | "CHoCH" | "none"
                - timeframes: dict mapping TF names to bias/last_event info
                - premium_zone: float | None
                - discount_zone: float | None
                - equilibrium: float | None
                - price_location: "premium" | "discount" | "equilibrium" | "unknown"
        """
        self._log["structure"] = {
            "htf_bias": structure_data.get("htf_bias", "neutral"),
            "htf_score": int(structure_data.get("htf_score", 0)),
            "confidence": float(structure_data.get("confidence", 0.0)),
            "condition": structure_data.get("condition", "transitioning"),
            "last_event": structure_data.get("last_event", "none"),
            "timeframes": structure_data.get("timeframes", {
                "W1": {"bias": "neutral", "last_event": "none"},
                "D1": {"bias": "neutral", "last_event": "none"},
                "H4": {"bias": "neutral", "last_event": "none"},
                "H1": {"bias": "neutral", "last_event": "none"},
            }),
            "premium_zone": structure_data.get("premium_zone"),
            "discount_zone": structure_data.get("discount_zone"),
            "equilibrium": structure_data.get("equilibrium"),
            "price_location": structure_data.get("price_location", "unknown"),
        }

    def set_dxy(self, dxy_data: dict[str, Any]) -> None:
        """
        Set DXY correlation information.

        Args:
            dxy_data: dict with keys:
                - available: bool
                - source: "live_symbol" | "synthetic_basket" | "unavailable"
                - dxy_bias: "bullish" | "bearish" | "neutral" | "unavailable"
                - gold_bias: "bullish" | "bearish" | "neutral"
                - relationship: "inverse_confirmed" | "divergence" | "conflict" | "unavailable"
                - confirms_bias: bool
                - reduce_size: bool
                - basket_pairs_used: int | None
                - note: str
        """
        self._log["dxy"] = {
            "available": bool(dxy_data.get("available", False)),
            "source": dxy_data.get("source", "unavailable"),
            "dxy_bias": dxy_data.get("dxy_bias", "unavailable"),
            "gold_bias": dxy_data.get("gold_bias", "neutral"),
            "relationship": dxy_data.get("relationship", "unavailable"),
            "confirms_bias": bool(dxy_data.get("confirms_bias", False)),
            "reduce_size": bool(dxy_data.get("reduce_size", False)),
            "basket_pairs_used": dxy_data.get("basket_pairs_used"),
            "note": dxy_data.get("note", ""),
        }

    def set_liquidity(self, liquidity_data: dict[str, Any]) -> None:
        """
        Set liquidity sweep information.

        Args:
            liquidity_data: dict with keys:
                - swept: bool
                - side: "buy" | "sell" | "none"
                - classification: "external" | "internal_continuation" | "none"
                - sweep_quality: "premium" | "standard" | "weak"
                - confidence: float (0.0-1.0)
                - swept_level: float | None
                - swept_level_type: pool type name
                - bars_ago: int | None
                - direction_hint: "buy" | "sell" | "none"
                - nearby_pools: list of dicts with type, price, distance_pips
        """
        self._log["liquidity"] = {
            "swept": bool(liquidity_data.get("swept", False)),
            "side": liquidity_data.get("side", "none"),
            "classification": liquidity_data.get("classification", "none"),
            "sweep_quality": liquidity_data.get("sweep_quality", "standard"),
            "confidence": float(liquidity_data.get("confidence", 0.0)),
            "swept_level": liquidity_data.get("swept_level"),
            "swept_level_type": liquidity_data.get("swept_level_type", "none"),
            "bars_ago": liquidity_data.get("bars_ago"),
            "direction_hint": liquidity_data.get("direction_hint", "none"),
            "nearby_pools": liquidity_data.get("nearby_pools", []),
        }

    def set_displacement(self, displacement_data: dict[str, Any]) -> None:
        """
        Set displacement and FVG information.

        Args:
            displacement_data: dict with keys:
                - valid: bool
                - type: "confirmation" | "rejection" | "none"
                - direction: "up" | "down" | "none"
                - strength: float (0.0-1.0) | None
                - impulse_range: float | None
                - atr: float | None
                - atr_ratio: float | None
                - fvg: dict with present, top, bottom, filled, timeframe
                - fvg_reason: str explaining FVG state
        """
        self._log["displacement"] = {
            "valid": bool(displacement_data.get("valid", False)),
            "type": displacement_data.get("type", "none"),
            "direction": displacement_data.get("direction", "none"),
            "strength": displacement_data.get("strength"),
            "impulse_range": displacement_data.get("impulse_range"),
            "atr": displacement_data.get("atr"),
            "atr_ratio": displacement_data.get("atr_ratio"),
            "fvg": {
                "present": bool(displacement_data.get("fvg", {}).get("present", False)),
                "top": displacement_data.get("fvg", {}).get("top"),
                "bottom": displacement_data.get("fvg", {}).get("bottom"),
                "filled": displacement_data.get("fvg", {}).get("filled"),
                "timeframe": displacement_data.get("fvg", {}).get("timeframe"),
            },
            "fvg_reason": displacement_data.get("fvg_reason", "null"),
        }

    def set_order_block(self, ob_data: dict[str, Any]) -> None:
        """
        Set order block detection information.

        Args:
            ob_data: dict with keys:
                - valid: bool
                - reason: "valid" | "ob_invalidated" | "mitigated" | "distance_too_far" | "none_found"
                - type: "bullish_ob" | "bearish_ob" | "none"
                - zone_high: float | None
                - zone_low: float | None
                - mitigated: bool | None
                - distance_atr: float | None
                - distance_pips: float | None
                - ob_age_bars: int | None
                - fvg_overlap: bool | None
                - rejected_obs_count: int (how many were filtered out)
        """
        self._log["order_block"] = {
            "valid": bool(ob_data.get("valid", False)),
            "reason": ob_data.get("reason", "none"),
            "type": ob_data.get("type", "none"),
            "zone_high": ob_data.get("zone_high"),
            "zone_low": ob_data.get("zone_low"),
            "mitigated": ob_data.get("mitigated"),
            "distance_atr": ob_data.get("distance_atr"),
            "distance_pips": ob_data.get("distance_pips"),
            "ob_age_bars": ob_data.get("ob_age_bars"),
            "fvg_overlap": ob_data.get("fvg_overlap"),
            "rejected_obs_count": int(ob_data.get("rejected_obs_count", 0)),
        }

    def set_m15_confirmation(self, m15_data: dict[str, Any]) -> None:
        """
        Set M15 internal structure confirmation.

        Args:
            m15_data: dict with keys:
                - choch_confirmed: bool
                - internal_bos: bool
                - m15_ob_present: bool
                - m15_sweep_done: bool
                - bars_since_choch: int | None
        """
        self._log["m15_confirmation"] = {
            "choch_confirmed": bool(m15_data.get("choch_confirmed", False)),
            "internal_bos": bool(m15_data.get("internal_bos", False)),
            "m15_ob_present": bool(m15_data.get("m15_ob_present", False)),
            "m15_sweep_done": bool(m15_data.get("m15_sweep_done", False)),
            "bars_since_choch": m15_data.get("bars_since_choch"),
        }

    def set_score(
        self,
        score: int | None,
        max_score: int | None,
        grade: str | None,
        risk_pct: float,
        passes_threshold: bool,
        min_score_to_trade: int = 8,
        checks: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Set confluence score and gate evaluations.

        Args:
            score: Final score (0-12) or None if not evaluated
            max_score: Maximum possible score
            grade: "A+" | "B" | "SKIP" | "BLOCKED" | None
            risk_pct: Risk percentage for this setup
            passes_threshold: Whether score >= min_score_to_trade
            min_score_to_trade: Minimum score to enter trade (default 8)
            checks: List of gate evaluation dicts
        """
        # Compute projected score
        projected_score = None
        if checks and score is not None:
            projected_score = self._compute_projected_score(checks, score)

        self._log["score"] = {
            "score": score,
            "max_score": max_score,
            "grade": grade,
            "risk_pct": float(risk_pct) if risk_pct is not None else 0.5,
            "passes_threshold": bool(passes_threshold),
            "min_score_to_trade": int(min_score_to_trade),
            "projected_score": projected_score,
            "checks": checks or [],
        }

    def _compute_projected_score(
        self, checks: list[dict[str, Any]], current_score: int
    ) -> int | None:
        """
        Compute projected score assuming remaining gates would pass.
        
        Args:
            checks: List of gate check dicts with points and max_points
            current_score: Current accumulated score
            
        Returns:
            Projected score if all remaining gates passed
        """
        if not checks:
            return current_score

        projected = current_score
        for check in checks:
            if not check.get("passed", False):
                # Assume remaining gates would contribute their max points
                max_pts = check.get("max_points", 0)
                projected += max_pts
        return min(projected, 12)  # Cap at 12

    def set_entry(self, entry_data: dict[str, Any]) -> None:
        """
        Set entry signal and execution parameters.

        Args:
            entry_data: dict with keys:
                - engine_action: "trade" | "skip" | "wait" | "blocked"
                - engine_reason: str explaining the action
                - engine_state: str (e.g., "READY_TO_TRADE", "WAITING")
                - entry_mode: "aggressive_limit" | "conservative_choch" | None
                - entry_price: float | None
                - sl_price: float | None
                - sl_pips: float | None
                - tp1_price: float | None
                - tp2_price: float | None
                - rr_ratio: float | None
                - lot_size: float | None
        """
        self._log["entry"] = {
            "engine_action": entry_data.get("engine_action", "skip"),
            "engine_reason": entry_data.get("engine_reason", ""),
            "engine_state": entry_data.get("engine_state", ""),
            "entry_mode": entry_data.get("entry_mode"),
            "entry_price": entry_data.get("entry_price"),
            "sl_price": entry_data.get("sl_price"),
            "sl_pips": entry_data.get("sl_pips"),
            "tp1_price": entry_data.get("tp1_price"),
            "tp2_price": entry_data.get("tp2_price"),
            "rr_ratio": entry_data.get("rr_ratio"),
            "lot_size": entry_data.get("lot_size"),
        }

    def set_risk(self, risk_data: dict[str, Any]) -> None:
        """
        Set risk management calculations.

        Args:
            risk_data: dict with keys:
                - account_balance: float
                - risk_amount_usd: float
                - risk_pct: float
                - pip_value: float | None
                - position_valid: bool
                - skip_reason: str | None
        """
        self._log["risk"] = {
            "account_balance": float(risk_data.get("account_balance", 0.0)),
            "risk_amount_usd": float(risk_data.get("risk_amount_usd", 0.0)),
            "risk_pct": float(risk_data.get("risk_pct", 0.5)),
            "pip_value": risk_data.get("pip_value"),
            "position_valid": bool(risk_data.get("position_valid", False)),
            "skip_reason": risk_data.get("skip_reason"),
        }

    def set_outcome(
        self,
        final_action: str,
        reason_code: str,
        reason_text: str,
        gate_failed: int | None = None,
    ) -> None:
        """
        Set final outcome of the scan cycle.

        Args:
            final_action: "trade" | "no_trade"
            reason_code: Machine-readable code
            reason_text: Human-readable explanation
            gate_failed: Which gate number blocked (if applicable)
        """
        self._log["outcome"] = {
            "final_action": final_action,
            "reason_code": reason_code,
            "reason_text": reason_text,
            "gate_failed": gate_failed,
            "flags": self._flags,
        }

    def add_flag(self, severity: str, code: str, message: str) -> None:
        """
        Add a flag to the flags array.

        Args:
            severity: "critical" | "warning" | "info"
            code: Machine-readable flag code
            message: Human-readable description
        """
        self._flags.append({
            "severity": severity,
            "code": code,
            "message": message,
        })

    def auto_detect_flags(self) -> None:
        """
        Auto-detect flags based on log state.
        Called after all set_*() methods to populate the flags array automatically.
        """
        # CRITICAL flags
        if self._log.get("dxy", {}).get("available") is False:
            self.add_flag(
                "critical",
                "DXY_UNAVAILABLE",
                "DXY data not available; inverse correlation cannot be confirmed",
            )

        if self._log.get("structure", {}).get("confidence") == 0:
            self.add_flag(
                "critical",
                "CONFIDENCE_ZERO",
                "HTF structure confidence is 0; setup may be questionable",
            )

        if self._log.get("order_block", {}).get("mitigated") is True:
            self.add_flag(
                "critical",
                "OB_MITIGATED",
                "Order block has been mitigated; entry zone compromised",
            )

        ob_distance_atr = self._log.get("order_block", {}).get("distance_atr")
        if ob_distance_atr is not None and ob_distance_atr > 1.5:
            self.add_flag(
                "critical",
                "OB_TOO_FAR",
                f"Order block distance ({ob_distance_atr:.2f} ATR) exceeds 1.5 ATR threshold",
            )

        score_grade = self._log.get("score", {}).get("grade")
        if score_grade == "BLOCKED":
            self.add_flag(
                "critical",
                "SCORER_BLOCKED",
                "Scorer was blocked and did not run; likely missing critical data",
            )

        # WARNING flags
        liquidity_class = self._log.get("liquidity", {}).get("classification")
        if liquidity_class == "internal_continuation":
            self.add_flag(
                "warning",
                "INTERNAL_SWEEP_ONLY",
                "Only internal continuation sweep detected; lower quality than external",
            )

        news_source = self._log.get("news", {}).get("source")
        if news_source == "fallback":
            self.add_flag(
                "warning",
                "NEWS_FALLBACK",
                "News filter using fallback mode; live source unavailable",
            )

        displacement_valid = self._log.get("displacement", {}).get("valid")
        fvg_present = self._log.get("displacement", {}).get("fvg", {}).get("present")
        if displacement_valid and not fvg_present:
            self.add_flag(
                "warning",
                "FVG_NULL_ON_VALID_DISPLACEMENT",
                "Displacement is valid but no FVG present; unusual market condition",
            )

        consecutive_losses = self._log.get("daily_state", {}).get("consecutive_losses", 0)
        if consecutive_losses >= 2:
            self.add_flag(
                "warning",
                "CONSECUTIVE_LOSSES",
                f"Account has {consecutive_losses} consecutive losses; risk scaling may be active",
            )

        # INFO flags
        if (
            self._log.get("structure", {}).get("confidence") == 0
            and self._log.get("score", {}).get("score") is not None
        ):
            self.add_flag(
                "info",
                "SCORE_INFLATED",
                "Score assigned despite zero confidence; relying on other factors",
            )

        dxy_relationship = self._log.get("dxy", {}).get("relationship")
        if dxy_relationship == "divergence":
            self.add_flag(
                "info",
                "DXY_DIVERGENCE",
                "DXY showing divergence from gold; watch for breakout",
            )

        basket_pairs = self._log.get("dxy", {}).get("basket_pairs_used")
        if basket_pairs is not None and basket_pairs < 6:
            self.add_flag(
                "info",
                "PARTIAL_BASKET",
                f"DXY basket using only {basket_pairs} of 6 pairs; may reduce confidence",
            )

    def build(self) -> dict[str, Any]:
        """
        Build and return the complete log dict.
        
        Returns:
            Complete structured log dict matching schema
        """
        return self._log

    def write(self, filepath: str) -> None:
        """
        Write log to .jsonl file (appends one JSON line).
        
        Args:
            filepath: Path to .jsonl file (e.g., logs/shadow_YYYYMMDD.jsonl)
        """
        # Ensure directory exists
        log_dir = os.path.dirname(filepath)
        if log_dir:
            Path(log_dir).mkdir(parents=True, exist_ok=True)

        # Append one line to .jsonl file
        with open(filepath, "a") as f:
            json.dump(sanitize_mapping(self._log), f, separators=(",", ":"))
            f.write("\n")

    def write_pretty(self, filepath: str) -> None:
        """
        Write prettified version to last_scan.json for real-time monitoring.
        
        Args:
            filepath: Path to last_scan.json file
        """
        # Ensure directory exists
        log_dir = os.path.dirname(filepath)
        if log_dir:
            Path(log_dir).mkdir(parents=True, exist_ok=True)

        # Overwrite with pretty-printed JSON
        with open(filepath, "w") as f:
            json.dump(sanitize_mapping(self._log), f, indent=2)


