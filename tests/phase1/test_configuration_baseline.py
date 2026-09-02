from __future__ import annotations

import importlib
import json
import sys

import pytest

from app_security.environment import consume_child_credentials
from config.symbol_profiles import DEFAULT_PROFILE, SYMBOL_PROFILES, get_symbol_profile


REQUIRED_PROFILE_KEYS = {
    "structure_tf",
    "structure_bars",
    "entry_tf",
    "entry_bars",
    "pair_limit",
    "risk_per_trade",
    "min_rr",
    "min_execution_rr",
    "market_structure",
    "liquidity",
    "displacement",
    "ob_breaker",
    "execution_levels",
}


@pytest.mark.unit
@pytest.mark.characterization
def test_symbol_profiles_have_required_schema_and_are_independent():
    for symbol in SYMBOL_PROFILES:
        profile = get_symbol_profile(symbol)
        assert REQUIRED_PROFILE_KEYS <= profile.keys()
        assert profile["structure_tf"]
        assert profile["entry_tf"]
        assert profile["risk_per_trade"] > 0

    first = get_symbol_profile("XAUUSDm")
    first["market_structure"]["DISPLACEMENT_ATR_MULT"] = -1
    assert get_symbol_profile("XAUUSDm")["market_structure"]["DISPLACEMENT_ATR_MULT"] > 0


@pytest.mark.unit
@pytest.mark.characterization
def test_unsupported_symbol_uses_a_deep_copy_of_the_default_profile():
    profile = get_symbol_profile("UNSUPPORTED_PHASE1_SYMBOL")
    assert profile == DEFAULT_PROFILE
    assert profile is not DEFAULT_PROFILE
    profile["liquidity"]["lookback"] = -1
    assert DEFAULT_PROFILE["liquidity"]["lookback"] > 0


@pytest.mark.unit
def test_child_credential_contract_prefers_expected_identity_and_scrubs_source():
    environment = {
        "MT5_LOGIN": "PHASE1_LOGIN",
        "MT5_PASSWORD": "PHASE1_DUMMY_PASSWORD_DO_NOT_USE",  # pragma: allowlist secret
        "MT5_SERVER": "PHASE1_SERVER",
        "EXPECTED_MT5_LOGIN": "EXPECTED_LOGIN",
        "EXPECTED_MT5_SERVER": "EXPECTED_SERVER",
    }

    contract = consume_child_credentials(environment)

    assert contract.credentials.login == "PHASE1_LOGIN"
    assert contract.expected_login == "EXPECTED_LOGIN"
    assert contract.expected_server == "EXPECTED_SERVER"
    assert environment == {}
    assert "PHASE1_DUMMY_PASSWORD_DO_NOT_USE" not in repr(contract)


@pytest.mark.unit
@pytest.mark.characterization
def test_session_preferences_override_startup_capital(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_CAPITAL", "2500")
    previous = sys.modules.pop("main", None)
    try:
        main = importlib.import_module("main")
        assert main.CAPITAL == 2500.0

        session_file = tmp_path / "session.json"
        session_file.write_text(
            json.dumps({"capital": 1250.0, "daily_target_pct": 2.0, "btc_enabled": False}),
            encoding="utf-8",
        )
        monkeypatch.setattr(main, "SESSION_JSON", session_file)
        main._last_session_mtime = None

        main.refresh_runtime_capital()

        assert main.CAPITAL == 1250.0
        assert main.DAILY_TARGET_PCT == 2.0
        assert main.BTC_TRADING_ENABLED is False
    finally:
        sys.modules.pop("main", None)
        if previous is not None:
            sys.modules["main"] = previous
