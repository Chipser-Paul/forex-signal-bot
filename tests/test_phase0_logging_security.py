from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.utils.logger import TradeLog
from utils import setup_logger, trade_journal


TEST_PASSWORD = "TEST_PASSWORD_DO_NOT_USE"  # pragma: allowlist secret
TEST_TOKEN = "TEST_TOKEN_DO_NOT_USE"  # pragma: allowlist secret


class StructuredLoggingSecurityTests(unittest.TestCase):
    def test_setup_jsonl_redacts_nested_credentials(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "setup.jsonl"
            with patch.object(setup_logger, "_get_log_file", return_value=log_file):
                setup_logger.log_setup_evaluation(
                    setup_id="TEST_SETUP",
                    symbol="TEST_SYMBOL",
                    action="wait",
                    reason="test",
                    gate_results={"password": TEST_PASSWORD},
                    market_conditions={"nested": {"access_token": TEST_TOKEN}},
                    timing_info={},
                )
            rendered = log_file.read_text(encoding="utf-8")

        self.assertNotIn(TEST_PASSWORD, rendered)
        self.assertNotIn(TEST_TOKEN, rendered)
        self.assertGreaterEqual(rendered.count("<REDACTED>"), 2)

    def test_trade_log_writers_redact_arbitrary_fields(self):
        trade_log = TradeLog()
        trade_log._log = {
            "password": TEST_PASSWORD,
            "nested": {"api_key": TEST_TOKEN},
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            compact_path = Path(temporary_directory) / "trade.jsonl"
            pretty_path = Path(temporary_directory) / "trade.json"
            trade_log.write(str(compact_path))
            trade_log.write_pretty(str(pretty_path))
            rendered = compact_path.read_text() + pretty_path.read_text()

        self.assertNotIn(TEST_PASSWORD, rendered)
        self.assertNotIn(TEST_TOKEN, rendered)

    def test_trade_journal_redacts_file_and_database_payloads(self):
        recorded = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            journal_path = Path(temporary_directory) / "journal.jsonl"
            with (
                patch.object(trade_journal, "LOG_DIR", journal_path.parent),
                patch.object(trade_journal, "JOURNAL_PATH", journal_path),
                patch.object(trade_journal, "record_trade_event", side_effect=recorded.append),
            ):
                trade_journal.log_trade_event(
                    ticket=1,
                    symbol="TEST_SYMBOL",
                    event_name="test",
                    details={"password": TEST_PASSWORD, "access_token": TEST_TOKEN},
                )
            rendered = journal_path.read_text(encoding="utf-8")

        self.assertNotIn(TEST_PASSWORD, rendered)
        self.assertNotIn(TEST_TOKEN, rendered)
        self.assertEqual(recorded[0]["details"]["password"], "<REDACTED>")
        self.assertEqual(recorded[0]["details"]["access_token"], "<REDACTED>")


if __name__ == "__main__":
    unittest.main()
