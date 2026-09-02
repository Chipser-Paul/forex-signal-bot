from __future__ import annotations

import importlib
import io
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app_security.models import MT5Credentials
from frontend.utils import bot_runner


TEST_LOGIN = "900000000000"
TEST_PASSWORD = "TEST_PASSWORD_DO_NOT_USE"  # pragma: allowlist secret
TEST_SERVER = "TEST_SERVER"


class FakeAccountInfo:
    def __init__(self, login: int, server: str):
        self.login = login
        self.server = server


def _fake_mt5(account_login: int, account_server: str):
    module = types.ModuleType("MetaTrader5")
    module.initialize_calls = []
    module.shutdown_calls = 0
    module.order_send_calls = 0

    def initialize(**kwargs):
        module.initialize_calls.append(kwargs)
        return True

    def account_info():
        return FakeAccountInfo(account_login, account_server)

    def shutdown():
        module.shutdown_calls += 1

    def order_send(*args, **kwargs):
        module.order_send_calls += 1
        raise AssertionError("Tests must never call the MT5 order API")

    module.initialize = initialize
    module.account_info = account_info
    module.shutdown = shutdown
    module.order_send = order_send
    module.last_error = lambda: (0, "TEST_ERROR")
    return module


class BotIdentityTests(unittest.TestCase):
    def tearDown(self) -> None:
        sys.modules.pop("utils.connect", None)

    @staticmethod
    def _environment() -> dict[str, str]:
        return {
            "MT5_LOGIN": TEST_LOGIN,
            "MT5_PASSWORD": TEST_PASSWORD,
            "MT5_SERVER": TEST_SERVER,
            "EXPECTED_MT5_LOGIN": TEST_LOGIN,
            "EXPECTED_MT5_SERVER": TEST_SERVER,
        }

    def _run_connection(self, fake_mt5):
        sys.modules.pop("utils.connect", None)
        with patch.dict(sys.modules, {"MetaTrader5": fake_mt5}):
            with patch.dict(os.environ, self._environment(), clear=False):
                connect = importlib.import_module("utils.connect")
                output = io.StringIO()
                with redirect_stdout(output):
                    result = connect.connect_mt5()
        return result, output.getvalue()

    def test_bot_connection_accepts_expected_mocked_identity(self):
        fake_mt5 = _fake_mt5(int(TEST_LOGIN), TEST_SERVER)

        result, output = self._run_connection(fake_mt5)

        self.assertTrue(result)
        self.assertEqual(len(fake_mt5.initialize_calls), 1)
        self.assertEqual(fake_mt5.order_send_calls, 0)
        self.assertNotIn(TEST_PASSWORD, output)

    def test_bot_connection_rejects_unexpected_mocked_identity(self):
        fake_mt5 = _fake_mt5(int(TEST_LOGIN) + 1, TEST_SERVER)

        result, output = self._run_connection(fake_mt5)

        self.assertFalse(result)
        self.assertEqual(fake_mt5.shutdown_calls, 1)
        self.assertEqual(fake_mt5.order_send_calls, 0)
        self.assertNotIn(TEST_PASSWORD, output)

    def test_bot_connection_rejects_unexpected_mocked_server(self):
        fake_mt5 = _fake_mt5(int(TEST_LOGIN), "UNEXPECTED_TEST_SERVER")

        result, output = self._run_connection(fake_mt5)

        self.assertFalse(result)
        self.assertEqual(fake_mt5.shutdown_calls, 1)
        self.assertEqual(fake_mt5.order_send_calls, 0)
        self.assertNotIn(TEST_PASSWORD, output)

    def test_bot_credentials_use_child_environment_not_command_arguments(self):
        captured = {}

        class Process:
            pid = 4321

        def fake_popen(command, **kwargs):
            captured["command"] = command
            captured["environment"] = kwargs["env"]
            return Process()

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with (
                patch.object(bot_runner, "LOG_DIR", root / "logs"),
                patch.object(bot_runner, "LOG_FILE", root / "logs" / "bot.log"),
                patch.object(bot_runner, "PROCESS_FILE", root / ".bot_process.json"),
                patch.object(bot_runner, "get_bot_status", return_value={"running": False}),
                patch.object(bot_runner.subprocess, "Popen", side_effect=fake_popen),
            ):
                credentials = MT5Credentials(TEST_LOGIN, TEST_PASSWORD, TEST_SERVER)
                with patch.dict(os.environ, {"APP_ACCESS_TOKEN": "TEST_APP_TOKEN"}):
                    parent_environment = dict(os.environ)
                    ok, _ = bot_runner.start_bot(1000.0, credentials)
                    self.assertEqual(dict(os.environ), parent_environment)

        self.assertTrue(ok)
        self.assertNotIn(TEST_PASSWORD, " ".join(captured["command"]))
        self.assertNotIn(TEST_LOGIN, " ".join(captured["command"]))
        self.assertEqual(captured["environment"]["MT5_PASSWORD"], TEST_PASSWORD)
        self.assertEqual(captured["environment"]["EXPECTED_MT5_LOGIN"], TEST_LOGIN)
        self.assertNotIn("APP_ACCESS_TOKEN", captured["environment"])

    def test_subprocess_failure_diagnostics_redact_credentials(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with (
                patch.object(bot_runner, "LOG_DIR", root / "logs"),
                patch.object(bot_runner, "LOG_FILE", root / "logs" / "bot.log"),
                patch.object(bot_runner, "PROCESS_FILE", root / ".bot_process.json"),
                patch.object(bot_runner, "get_bot_status", return_value={"running": False}),
                patch.object(
                    bot_runner.subprocess,
                    "Popen",
                    side_effect=RuntimeError(
                        f"password={TEST_PASSWORD} token=TEST_TOKEN_DO_NOT_USE"
                    ),
                ),
            ):
                ok, message = bot_runner.start_bot(
                    1000.0,
                    MT5Credentials(TEST_LOGIN, TEST_PASSWORD, TEST_SERVER),
                )

        self.assertFalse(ok)
        self.assertNotIn(TEST_PASSWORD, message)
        self.assertNotIn("TEST_TOKEN_DO_NOT_USE", message)
        self.assertIn("<REDACTED>", message)


if __name__ == "__main__":
    unittest.main()
