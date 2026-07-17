from __future__ import annotations

import json
import os

from runtime.context import RuntimeContext
from runtime.legacy_runner import evaluate_symbol as evaluate_symbol_via_runtime
from runtime.monitoring import monitor_trades as monitor_trades_via_runtime
from runtime.profit import show_profit_summary as show_profit_summary_via_runtime
from runtime.settings import is_symbol_enabled as is_symbol_enabled_via_runtime
from runtime.settings import refresh_runtime_settings as refresh_runtime_settings_via_runtime

# UI bot state file (written by frontend/utils/bot_control.py)
_BOT_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),  # project root
    "frontend", "utils", ".bot_state.json",
)


def _get_bot_state() -> str | None:
    """Read UI bot state. Returns 'running', 'paused', 'stopped', or None on error/missing."""
    try:
        if os.path.exists(_BOT_STATE_FILE):
            with open(_BOT_STATE_FILE) as f:
                return json.load(f).get("state")
    except Exception:
        pass
    return None


def main_loop_once(ctx: RuntimeContext, open_trades: dict) -> dict:
    refresh_runtime_settings_via_runtime(ctx.refresh_runtime_settings)
    show_profit_summary_via_runtime(ctx.show_profit_summary)
    open_trades = monitor_trades_via_runtime(open_trades, ctx.monitor_trades)

    # Check UI pause state — skip new trade evaluation when paused,
    # but still monitor/manage existing trades (SL/TP, trailing, kill-switch)
    bot_state = _get_bot_state()
    is_paused = bot_state == "paused"

    if not is_paused:
        for sym in ctx.symbols:
            if not is_symbol_enabled_via_runtime(sym, ctx.is_symbol_enabled):
                continue
            evaluate_symbol_via_runtime(sym, open_trades, ctx.evaluate_symbol)

    for _ in range(15):
        for sym in ctx.symbols:
            ctx.manage_open_trades(
                sym,
                open_trades,
                lock_tiers=[
                    (8.0, 0.40),
                    (12.0, 0.55),
                    (16.0, 0.70),
                    (20.0, 0.80),
                ],
            )
        ctx.sleep_fn(1.5)

    ctx.sleep_fn(ctx.loop_delay)
    return open_trades
