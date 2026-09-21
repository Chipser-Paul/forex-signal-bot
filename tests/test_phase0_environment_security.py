from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app_security import environment


TEST_ENVIRONMENT = {
    "MT5_LOGIN": "900000000000",
    "MT5_PASSWORD": "TEST_PASSWORD_DO_NOT_USE",  # pragma: allowlist secret
    "MT5_SERVER": "TEST_SERVER",
    "EXPECTED_MT5_LOGIN": "900000000000",
    "EXPECTED_MT5_SERVER": "TEST_SERVER",
}


class ChildEnvironmentSecurityTests(unittest.TestCase):
    def test_consumption_builds_contract_and_removes_every_mt5_variable(self):
        child_environment = dict(TEST_ENVIRONMENT)

        contract = environment.consume_child_credentials(child_environment)

        self.assertEqual(contract.credentials.password, TEST_ENVIRONMENT["MT5_PASSWORD"])
        self.assertEqual(contract.expected_login, TEST_ENVIRONMENT["EXPECTED_MT5_LOGIN"])
        for key in environment.MT5_ENVIRONMENT_KEYS:
            self.assertNotIn(key, child_environment)
        self.assertNotIn(TEST_ENVIRONMENT["MT5_PASSWORD"], repr(contract))

    def test_later_subprocess_environment_cannot_inherit_consumed_credentials(self):
        with patch.dict(os.environ, TEST_ENVIRONMENT, clear=True):
            environment.consume_child_credentials()
            inherited_environment = os.environ.copy()

        for key in environment.MT5_ENVIRONMENT_KEYS:
            self.assertNotIn(key, inherited_environment)

    def test_later_dotenv_load_cannot_restore_consumed_credentials(self):
        def fake_load_dotenv() -> None:
            os.environ.update(TEST_ENVIRONMENT)

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(environment, "_credentials_consumed", True),
            patch.object(environment, "load_dotenv", side_effect=fake_load_dotenv),
        ):
            environment.load_project_environment()
            for key in environment.MT5_ENVIRONMENT_KEYS:
                self.assertNotIn(key, os.environ)


if __name__ == "__main__":
    unittest.main()
