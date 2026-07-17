# utils/bot_control.py
import json
import os

CONTROL_FILE = os.path.join(os.path.dirname(__file__), ".bot_state.json")

def set_bot_state(state: str):
    """Set the bot control state (start, pause, stop)."""
    data = {"state": state}
    with open(CONTROL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return state

def get_bot_state() -> str:
    """Get current bot state (default 'stopped')."""
    if not os.path.exists(CONTROL_FILE):
        return "stopped"
    try:
        with open(CONTROL_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("state", "stopped")
    except Exception:
        return "stopped"

def clear_bot_state():
    """Reset control file."""
    if os.path.exists(CONTROL_FILE):
        os.remove(CONTROL_FILE)