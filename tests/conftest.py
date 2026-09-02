from __future__ import annotations

import os
import subprocess
import sys
import types
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_POPEN = subprocess.Popen


class UnsafeExternalCall(RuntimeError):
    """Raised whenever a test reaches a prohibited external boundary."""


class FakeMT5(types.ModuleType):
    """Stateful, fail-closed substitute for the MetaTrader5 package."""

    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440
    TIMEFRAME_W1 = 10080

    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_INVALID_STOPS = 10016
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_OUT_BY = 3

    def __init__(self) -> None:
        super().__init__("MetaTrader5")
        self.reset()

    def reset(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.rates: Any = []
        self.range_rates: Any | None = None
        self.positions: list[Any] = []
        self.deals: list[Any] = []
        self.account: Any | None = None
        self.tick = SimpleNamespace(bid=99.9, ask=100.1)
        self.symbol = SimpleNamespace(
            name="XAUUSDm",
            point=0.01,
            digits=2,
            stops_level=10,
            trade_tick_value=1.0,
            trade_tick_size=0.01,
            trade_contract_size=100.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
        )
        self.allow_order_send = False
        self.allow_order_check = False
        self.order_response: Any | None = None
        self.order_check_response: Any | None = None

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    def initialize(self, *args: Any, **kwargs: Any) -> bool:
        self._record("initialize", *args, **kwargs)
        raise UnsafeExternalCall("Tests must never initialize an MT5 session")

    def shutdown(self) -> bool:
        self._record("shutdown")
        return True

    def last_error(self) -> tuple[int, str]:
        return (0, "fake MT5 has no terminal error")

    def account_info(self) -> Any | None:
        self._record("account_info")
        return self.account

    def terminal_info(self) -> Any | None:
        self._record("terminal_info")
        return None

    def symbol_info(self, symbol: str) -> Any:
        self._record("symbol_info", symbol)
        return self.symbol

    def symbol_info_tick(self, symbol: str) -> Any:
        self._record("symbol_info_tick", symbol)
        return self.tick

    def symbol_select(self, symbol: str, enabled: bool) -> bool:
        self._record("symbol_select", symbol, enabled)
        return True

    def copy_rates_from_pos(
        self, symbol: str, timeframe: int, start_pos: int, bars: int
    ) -> Any:
        self._record("copy_rates_from_pos", symbol, timeframe, start_pos, bars)
        return self.rates

    def copy_rates_range(self, *args: Any, **kwargs: Any) -> Any:
        self._record("copy_rates_range", *args, **kwargs)
        if self.range_rates is None:
            raise UnsafeExternalCall("Unconfigured MT5 range retrieval is prohibited")
        return self.range_rates

    def positions_get(self, *args: Any, **kwargs: Any) -> list[Any]:
        self._record("positions_get", *args, **kwargs)
        return list(self.positions)

    def history_deals_get(self, *args: Any, **kwargs: Any) -> list[Any]:
        self._record("history_deals_get", *args, **kwargs)
        return list(self.deals)

    def order_check(self, request: dict[str, Any]) -> Any:
        self._record("order_check", request)
        if not self.allow_order_check:
            raise UnsafeExternalCall("order_check requires explicit fake enablement")
        return self.order_check_response

    def order_send(self, request: dict[str, Any]) -> Any:
        self._record("order_send", request)
        if not self.allow_order_send:
            raise UnsafeExternalCall("order_send requires explicit fake enablement")
        return self.order_response


FAKE_MT5 = FakeMT5()
sys.modules["MetaTrader5"] = FAKE_MT5


@dataclass(frozen=True)
class FrozenClock:
    value: datetime = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.value


@pytest.fixture(scope="session", autouse=True)
def session_working_directory(tmp_path_factory: pytest.TempPathFactory):
    original_cwd = Path.cwd()
    sandbox = tmp_path_factory.mktemp("session-cwd")
    os.chdir(sandbox)
    try:
        yield sandbox
    finally:
        os.chdir(original_cwd)


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def fake_mt5() -> FakeMT5:
    return FAKE_MT5


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def isolated_paths(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        root=tmp_path,
        state=tmp_path / "state.json",
        journal=tmp_path / "trade_journal.jsonl",
        database=tmp_path / "analytics.db",
        cache=tmp_path / "cache",
    )


@pytest.fixture
def allow_fake_order(fake_mt5: FakeMT5):
    def enable(response: Any) -> FakeMT5:
        fake_mt5.allow_order_send = True
        fake_mt5.order_response = response
        return fake_mt5

    return enable


@pytest.fixture(autouse=True)
def isolate_external_boundaries(monkeypatch: pytest.MonkeyPatch):
    FAKE_MT5.reset()
    sys.modules["MetaTrader5"] = FAKE_MT5

    for name in (
        "MT5_LOGIN",
        "MT5_PASSWORD",
        "MT5_SERVER",
        "EXPECTED_MT5_LOGIN",
        "EXPECTED_MT5_SERVER",
        "APP_ACCESS_TOKEN",
        "GROQ_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "FCM_DEVICE_TOKEN",
        "FCM_DEVICE_TOKENS",
        "FIREBASE_SERVICE_ACCOUNT_PATH",
        "NEWS_EVENTS_PATH",
        "BOT_CAPITAL",
        "BOT_ACTIVE_ENGINE",
    ):
        monkeypatch.delenv(name, raising=False)

    launch_calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def blocked_launch(*args: Any, **kwargs: Any):
        launch_calls.append(("subprocess", args, kwargs))
        raise UnsafeExternalCall("Process launch is prohibited during tests")

    for name in ("Popen", "run", "call", "check_call"):
        monkeypatch.setattr(subprocess, name, blocked_launch)

    def guarded_check_output(*args: Any, **kwargs: Any):
        if args == ("ver",) and kwargs.get("shell") is True:
            process = REAL_POPEN(*args, stdout=subprocess.PIPE, **kwargs)
            stdout, _ = process.communicate()
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, args[0])
            return stdout
        return blocked_launch(*args, **kwargs)

    monkeypatch.setattr(subprocess, "check_output", guarded_check_output)
    monkeypatch.setattr(os, "system", blocked_launch)
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", blocked_launch)
    monkeypatch.setattr(webbrowser, "open", blocked_launch)

    def blocked_network(*args: Any, **kwargs: Any):
        raise UnsafeExternalCall("Network access is prohibited during tests")

    monkeypatch.setattr(urllib.request, "urlopen", blocked_network)

    yield launch_calls

    assert sys.modules.get("MetaTrader5") is FAKE_MT5
    FAKE_MT5.reset()
