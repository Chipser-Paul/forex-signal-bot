from __future__ import annotations

import importlib
import json
import sqlite3
import sys

import pytest

from frontend.utils import session_manager
from utils import analytics_db, trade_journal


@pytest.mark.unit
@pytest.mark.characterization
def test_trade_journal_and_sqlite_roundtrip_are_isolated(monkeypatch, isolated_paths):
    monkeypatch.setattr(analytics_db, "DB_PATH", isolated_paths.database)
    monkeypatch.setattr(analytics_db, "JOURNAL_PATH", isolated_paths.journal)
    monkeypatch.setattr(trade_journal, "LOG_DIR", isolated_paths.journal.parent)
    monkeypatch.setattr(trade_journal, "JOURNAL_PATH", isolated_paths.journal)

    analytics_db.init_db()
    trade_journal.log_trade_event(
        ticket=101,
        symbol="TEST_SYMBOL",
        event_name="phase1_roundtrip",
        details={"decision": "hold"},
    )

    event = json.loads(isolated_paths.journal.read_text(encoding="utf-8").strip())
    assert event["event"] == "phase1_roundtrip"
    assert event["details"] == {"decision": "hold"}

    with sqlite3.connect(isolated_paths.database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        stored = connection.execute(
            "SELECT event, symbol FROM trade_events WHERE ticket = ?", (101,)
        ).fetchone()

    assert {"trade_events", "loop_snapshots", "ai_reviews"} <= tables
    assert stored == ("phase1_roundtrip", "TEST_SYMBOL")


@pytest.mark.unit
@pytest.mark.characterization
def test_missing_and_corrupt_open_trade_state_fail_closed(monkeypatch, isolated_paths):
    import trade_executor

    monkeypatch.setattr(trade_executor, "OPEN_JSON", isolated_paths.state)
    assert trade_executor.load_open_trades() == {}

    isolated_paths.state.write_text('{"XAUUSDm": [{"ticket": 7}]}', encoding="utf-8")
    assert trade_executor.load_open_trades() == {"XAUUSDm": [{"ticket": 7}]}

    isolated_paths.state.write_text("not-json", encoding="utf-8")
    assert trade_executor.load_open_trades() == {}


@pytest.mark.unit
def test_session_preferences_never_persist_credentials(monkeypatch, isolated_paths):
    monkeypatch.setattr(session_manager, "SESSION_FILE", str(isolated_paths.state))
    password = "PHASE1_DUMMY_PASSWORD_DO_NOT_USE"  # pragma: allowlist secret
    token = "PHASE1_DUMMY_TOKEN_DO_NOT_USE"  # pragma: allowlist secret

    assert session_manager.save_session(
        login="TEST_LOGIN",
        password=password,
        server="TEST_SERVER",
        nested={"access_token": token},
        capital=1000,
    )

    rendered = isolated_paths.state.read_text(encoding="utf-8")
    persisted = json.loads(rendered)
    assert password not in rendered
    assert token not in rendered
    assert "password" not in persisted
    assert "access_token" not in persisted.get("nested", {})
    assert persisted["remember_password"] is False


@pytest.mark.unit
@pytest.mark.characterization
def test_key_module_imports_have_no_runtime_side_effects(fake_mt5, isolate_external_boundaries):
    module_names = (
        "bot.data.market_data",
        "bot.execution.risk_engine",
        "bot.state.orchestrator",
        "trade_executor",
        "trade_manager",
        "frontend.utils.mt5_connector",
        "frontend.utils.bot_runner",
        "utils.loop_ai",
        "main",
    )

    for name in module_names:
        module = importlib.import_module(name)
        importlib.reload(module)

    dangerous_mt5_calls = {"initialize", "order_send", "order_check"}
    assert not [call for call in fake_mt5.calls if call[0] in dangerous_mt5_calls]
    assert isolate_external_boundaries == []


@pytest.mark.unit
def test_streamlit_entry_is_guarded_from_import_based_test_execution(repo_root):
    source = (repo_root / "frontend" / "app.py").read_text(encoding="utf-8")
    assert "st.set_page_config" in source
    assert "subprocess.Popen" not in source
    assert "mt5.order_send" not in source
