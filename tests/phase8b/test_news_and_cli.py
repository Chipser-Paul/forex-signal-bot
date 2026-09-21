from __future__ import annotations

import importlib
from datetime import datetime, timezone

import pytest

from backtests import empirical_data_control
from bot.acquisition.models import AcquisitionError
from bot.acquisition.news import normalize_historical_news


UTC = timezone.utc


@pytest.mark.unit
def test_trading_economics_news_normalizes_and_deduplicates_offline():
    record = {
        "CalendarId": "event-1",
        "Country": "United States",
        "Currency": "USD",
        "Event": "Employment report",
        "Importance": 3,
        "Date": "2026-01-02T13:30:00-05:00",
    }
    result = normalize_historical_news(
        (record, record, {**record, "CalendarId": "foreign", "Country": "Canada", "Currency": "CAD"}),
        provider="TRADING_ECONOMICS",
        retrieved_at=datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert len(result) == 1
    assert result[0]["timestamp"] == "2026-01-02T18:30:00Z"
    assert result[0]["impact"] == "HIGH"
    assert len(result[0]["raw_record_sha256"]) == 64


@pytest.mark.unit
def test_news_unknown_impact_or_naive_time_fails_closed():
    base = {
        "CalendarId": "event-1",
        "Country": "United States",
        "Event": "Event",
        "Importance": "unknown",
        "Date": "2026-01-02T13:30:00Z",
    }
    with pytest.raises(AcquisitionError, match="impact"):
        normalize_historical_news((base,), provider="TRADING_ECONOMICS", retrieved_at=datetime(2026, 1, 3, tzinfo=UTC))
    with pytest.raises(AcquisitionError, match="timezone"):
        normalize_historical_news(
            ({**base, "Importance": 3, "Date": "2026-01-02T13:30:00"},),
            provider="TRADING_ECONOMICS",
            retrieved_at=datetime(2026, 1, 3, tzinfo=UTC),
        )


@pytest.mark.unit
def test_dry_run_and_missing_confirmation_never_import_mt5(monkeypatch, capsys, tmp_path):
    imported: list[str] = []
    real_import = importlib.import_module

    def guarded_import(name, *args, **kwargs):
        if name == "MetaTrader5":
            imported.append(name)
            raise AssertionError("MT5 import is forbidden")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(empirical_data_control.importlib, "import_module", guarded_import)
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    assert empirical_data_control.main(["inspect", "--dry-run", "--output-root", str(tmp_path)]) == 0
    assert empirical_data_control.main(["inspect", "--output-root", str(tmp_path)]) == 0
    assert imported == []
    output = capsys.readouterr().out
    assert '"mt5_initialized":false' in output


@pytest.mark.unit
def test_active_process_blocks_before_mt5_import(monkeypatch, tmp_path):
    monkeypatch.setattr(empirical_data_control, "_worktree_roots", lambda: ())
    owner = tmp_path / "owner"
    state_dir = owner / "frontend" / "utils"
    state_dir.mkdir(parents=True)
    (state_dir / ".bot_state.json").write_text('{"state":"stopped"}', encoding="utf-8")
    (state_dir / ".bot_process.json").write_text('{"pid":999999}', encoding="utf-8")
    monkeypatch.setattr(
        empirical_data_control,
        "windows_process_snapshot",
        lambda: ((999999, "python.exe"),),
    )
    monkeypatch.setattr(
        empirical_data_control.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(AssertionError(f"unexpected import: {name}")),
    )
    result = empirical_data_control.main([
        "inspect",
        "--confirm-read-only-demo-export",
        "--output-root",
        str(tmp_path),
        "--owner-worktree",
        str(owner),
    ])
    assert result == 0
