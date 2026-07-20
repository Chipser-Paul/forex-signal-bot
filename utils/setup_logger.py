"""
Setup Logger - Logs all setup evaluations (taken and rejected)
Captures 13 gate values, timestamps, scores, and outcomes for analysis.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from utils.log import log
import pandas as pd


SETUP_LOG_DIR = Path("logs/setup_evaluations")
SETUP_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Daily log file
def _get_log_file() -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return SETUP_LOG_DIR / f"setups_{today}.jsonl"


def _serialize_value(value: Any) -> Any:
    """Convert non-JSON-serializable types to JSON-compatible types."""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    elif isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_serialize_value(v) for v in value]
    else:
        return value


def log_setup_evaluation(
    setup_id: str,
    symbol: str,
    action: str,  # "candidate_ready", "skip", "wait", "halt", "error"
    reason: str,
    gate_results: dict[str, Any],
    market_conditions: dict[str, Any],
    timing_info: dict[str, Any],
    trade_metrics: Optional[dict[str, Any]] = None,
    outcome: Optional[str] = None,  # "taken", "rejected"
    outcome_detail: Optional[str] = None,  # "won", "lost", or rejection reason
) -> None:
    """
    Log a complete setup evaluation with all gate results, market conditions, and timing.
    
    Args:
        setup_id: Unique identifier for this setup
        symbol: Trading symbol
        action: Orchestrator action (candidate_ready, skip, wait, halt, error)
        reason: Primary reason for the action
        gate_results: Dict with all 13 gate results (pass/fail + raw values)
        market_conditions: Dict with ATR, spread, session, volatility, etc.
        timing_info: Dict with timestamps for sweep, displacement, CHOCH, entry
        trade_metrics: Optional dict with entry, SL, TP, position size, RR (if trade taken)
        outcome: "taken" or "rejected"
        outcome_detail: "won", "lost" (if taken) or rejection reason (if rejected)
    """
    log_entry = {
        "setup_id": setup_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "action": action,
        "reason": reason,
        "outcome": outcome,
        "outcome_detail": outcome_detail,
        "gate_results": _serialize_value(gate_results),
        "market_conditions": _serialize_value(market_conditions),
        "timing_info": _serialize_value(timing_info),
        "trade_metrics": _serialize_value(trade_metrics) if trade_metrics else None,
    }
    
    # Write to JSONL file (append mode)
    log_file = _get_log_file()
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
        f.flush()  # Ensure immediate write
    
    # Log summary to console
    if action == "candidate_ready":
        log(f"[SETUP-LOG] {setup_id}: CANDIDATE READY - score={gate_results.get('score', 'N/A')}", "green")
    elif action == "skip":
        log(f"[SETUP-LOG] {setup_id}: SKIPPED - {reason}", "yellow")
    elif action == "wait":
        log(f"[SETUP-LOG] {setup_id}: WAITING - {reason}", "cyan")
    elif action == "halt":
        log(f"[SETUP-LOG] {setup_id}: HALTED - {reason}", "red")
    elif action == "error":
        log(f"[SETUP-LOG] {setup_id}: ERROR - {reason}", "red")


def generate_setup_id(symbol: str, timestamp: Optional[datetime] = None) -> str:
    """Generate a unique setup ID."""
    ts = timestamp or datetime.now(timezone.utc)
    ts_str = ts.strftime("%Y%m%d_%H%M%S")
    return f"{symbol}_{ts_str}"
