from __future__ import annotations

import json

import pytest

from backtests.realistic_execution_replay import run_replay


@pytest.mark.unit
def test_phase7_replay_never_reaches_mt5_or_network(fake_mt5):
    run_replay()
    prohibited = {"initialize", "account_info", "copy_rates_range", "order_check", "order_send"}
    assert not [call for call in fake_mt5.calls if call[0] in prohibited]


@pytest.mark.unit
def test_historical_domain_has_no_mt5_or_network_import(repo_root):
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (repo_root / "bot" / "backtesting").glob("*.py")
    )
    assert "MetaTrader5" not in sources
    assert "requests" not in sources
    assert "urlopen" not in sources


@pytest.mark.unit
def test_production_order_send_remains_confined_to_phase5_adapter(repo_root):
    occurrences = []
    for path in (repo_root / "bot").rglob("*.py"):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "order_send(" in line:
                occurrences.append((path.relative_to(repo_root).as_posix(), line_number))
    assert occurrences == [("bot/execution/broker/adapter.py", 747)]


@pytest.mark.unit
def test_offline_metadata_schema_and_legacy_manifest_are_non_sensitive(repo_root):
    schema = json.loads(
        (repo_root / "config" / "historical_broker_metadata.schema.json").read_text(encoding="utf-8")
    )
    inventory = json.loads(
        (repo_root / "baseline" / "phase7_legacy_inventory.json").read_text(encoding="utf-8")
    )
    assert schema["properties"]["symbol"]["const"] == "XAUUSDm"
    assert inventory["profitability_evidence"] is False
    serialized = json.dumps({"schema": schema, "inventory": inventory}).lower()
    assert "password" not in serialized
    assert "api_key" not in serialized
