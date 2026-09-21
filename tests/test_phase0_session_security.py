from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app_security.models import MT5Credentials
from frontend.utils import auth, credential_store, session_manager
from utils.log import log


TEST_LOGIN = "TEST_LOGIN_0000"
TEST_PASSWORD = "TEST_PASSWORD_DO_NOT_USE"  # pragma: allowlist secret
TEST_TOKEN = "TEST_TOKEN_DO_NOT_USE"  # pragma: allowlist secret
TEST_SERVER = "TEST_SERVER"


class SessionSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.session_file = Path(self.temporary_directory.name) / ".session.json"
        self.session_path_patch = patch.object(
            session_manager,
            "SESSION_FILE",
            str(self.session_file),
        )
        self.session_path_patch.start()

    def tearDown(self) -> None:
        self.session_path_patch.stop()
        self.temporary_directory.cleanup()

    def test_saving_session_never_serializes_credentials(self):
        self.assertTrue(
            session_manager.save_session(
                login=TEST_LOGIN,
                password=TEST_PASSWORD,
                server=TEST_SERVER,
                nested={"access_token": TEST_TOKEN, "theme": "dark"},
            )
        )

        serialized = self.session_file.read_text(encoding="utf-8")
        loaded = json.loads(serialized)
        self.assertNotIn(TEST_PASSWORD, serialized)
        self.assertNotIn(TEST_TOKEN, serialized)
        self.assertNotIn("password", loaded)
        self.assertEqual(loaded["nested"], {"theme": "dark"})

    def test_remember_password_preference_is_not_mistaken_for_a_secret(self):
        self.assertTrue(
            session_manager.save_session(
                login=TEST_LOGIN,
                password=TEST_PASSWORD,
                server=TEST_SERVER,
                remember_password=True,
            )
        )

        loaded = json.loads(self.session_file.read_text(encoding="utf-8"))
        self.assertTrue(loaded["remember_password"])
        self.assertNotIn("password", loaded)

    def test_loading_legacy_session_removes_password(self):
        self.session_file.write_text(
            json.dumps(
                {
                    "login": TEST_LOGIN,
                    "password": TEST_PASSWORD,
                    "server": TEST_SERVER,
                    "capital": 1000.0,
                }
            ),
            encoding="utf-8",
        )

        loaded = session_manager.load_session()
        rewritten = self.session_file.read_text(encoding="utf-8")

        self.assertIsNotNone(loaded)
        self.assertNotIn("password", loaded)
        self.assertNotIn(TEST_PASSWORD, rewritten)

    def test_failed_legacy_rewrite_removes_credential_file(self):
        self.session_file.write_text(
            json.dumps({"login": TEST_LOGIN, "password": TEST_PASSWORD}),
            encoding="utf-8",
        )

        with patch.object(session_manager, "_write_preferences", return_value=False):
            loaded = session_manager.load_session()

        self.assertIsNotNone(loaded)
        self.assertFalse(self.session_file.exists())

    def test_credentials_have_sanitized_representations(self):
        credentials = MT5Credentials(TEST_LOGIN, TEST_PASSWORD, TEST_SERVER)

        self.assertNotIn(TEST_PASSWORD, repr(credentials))
        self.assertNotIn(TEST_PASSWORD, str(credentials))
        self.assertIn("<REDACTED>", repr(credentials))
        self.assertNotIn(TEST_LOGIN, repr(credentials))

    def test_passwords_and_tokens_are_redacted_from_logs(self):
        output = io.StringIO()
        with redirect_stdout(output):
            log(f"password={TEST_PASSWORD} token={TEST_TOKEN}")

        rendered = output.getvalue()
        self.assertNotIn(TEST_PASSWORD, rendered)
        self.assertNotIn(TEST_TOKEN, rendered)
        self.assertGreaterEqual(rendered.count("<REDACTED>"), 2)

    def test_quoted_mapping_credentials_are_redacted_from_logs(self):
        output = io.StringIO()
        with redirect_stdout(output):
            log({"password": TEST_PASSWORD, "access_token": TEST_TOKEN})

        rendered = output.getvalue()
        self.assertNotIn(TEST_PASSWORD, rendered)
        self.assertNotIn(TEST_TOKEN, rendered)

    def test_missing_keyring_backend_disables_password_persistence(self):
        with patch.object(credential_store, "_keyring", None):
            self.assertFalse(credential_store.keyring_available())
            self.assertFalse(
                credential_store.store_password(TEST_LOGIN, TEST_SERVER, TEST_PASSWORD)
            )
            self.assertIsNone(credential_store.get_password(TEST_LOGIN, TEST_SERVER))

    def test_available_keyring_backend_is_used(self):
        values = {}

        class Backend:
            priority = 1

        class FakeKeyring:
            @staticmethod
            def get_keyring():
                return Backend()

            @staticmethod
            def set_password(service, username, password):
                values[(service, username)] = password

            @staticmethod
            def get_password(service, username):
                return values.get((service, username))

            @staticmethod
            def delete_password(service, username):
                values.pop((service, username), None)

        with patch.object(credential_store, "_keyring", FakeKeyring()):
            self.assertTrue(
                credential_store.store_password(TEST_LOGIN, TEST_SERVER, TEST_PASSWORD)
            )
            self.assertEqual(
                credential_store.get_password(TEST_LOGIN, TEST_SERVER),
                TEST_PASSWORD,
            )
            self.assertTrue(credential_store.delete_password(TEST_LOGIN, TEST_SERVER))

    def test_keyring_exceptions_fail_closed_without_persistence(self):
        class Backend:
            priority = 1

        class FailingKeyring:
            @staticmethod
            def get_keyring():
                return Backend()

            @staticmethod
            def set_password(*args, **kwargs):
                raise RuntimeError(f"password={TEST_PASSWORD}")

            @staticmethod
            def get_password(*args, **kwargs):
                raise RuntimeError(f"password={TEST_PASSWORD}")

            @staticmethod
            def delete_password(*args, **kwargs):
                raise RuntimeError(f"password={TEST_PASSWORD}")

        with patch.object(credential_store, "_keyring", FailingKeyring()):
            self.assertFalse(
                credential_store.store_password(TEST_LOGIN, TEST_SERVER, TEST_PASSWORD)
            )
            self.assertIsNone(credential_store.get_password(TEST_LOGIN, TEST_SERVER))
            self.assertFalse(credential_store.delete_password(TEST_LOGIN, TEST_SERVER))
        self.assertFalse(self.session_file.exists())

    def test_clear_session_requests_keyring_deletion(self):
        with patch.object(session_manager, "delete_password", return_value=True) as delete:
            session_manager.clear_session(login=TEST_LOGIN, server=TEST_SERVER)

        delete.assert_called_once_with(TEST_LOGIN, TEST_SERVER)

    def test_protected_pages_require_in_memory_authentication(self):
        for page in auth.PROTECTED_PAGES:
            with self.subTest(page=page):
                self.assertEqual(auth.resolve_page(page, {"page": page}), "login")

        state = {"page": "settings"}
        auth.establish_authenticated_session(
            state,
            MT5Credentials(TEST_LOGIN, TEST_PASSWORD, TEST_SERVER),
        )
        for page in auth.PROTECTED_PAGES:
            with self.subTest(page=page):
                self.assertEqual(auth.resolve_page(page, state), page)

    def test_logout_clears_authentication_and_password_widget_state(self):
        state = {auth.PASSWORD_WIDGET_KEY: TEST_PASSWORD, "page": "dashboard"}
        auth.establish_authenticated_session(
            state,
            MT5Credentials(TEST_LOGIN, TEST_PASSWORD, TEST_SERVER),
        )

        auth.clear_authenticated_session(state)

        self.assertFalse(auth.is_authenticated(state))
        self.assertNotIn(auth.CREDENTIALS_KEY, state)
        self.assertNotIn(auth.PASSWORD_WIDGET_KEY, state)
        self.assertNotIn(auth.REMOTE_AUTHORIZED_KEY, state)
        self.assertEqual(state["page"], "login")

    def test_remote_access_requires_configured_token_and_safe_comparison(self):
        state = {}
        environ = {"FOREX_REMOTE_ACCESS": "1", "APP_ACCESS_TOKEN": TEST_TOKEN}

        self.assertTrue(auth.remote_access_required(environ))
        self.assertTrue(
            auth.remote_access_required(
                {"FOREX_REMOTE_ACCESS": "0"},
                server_address="0.0.0.0",
            )
        )
        self.assertFalse(
            auth.remote_access_required(
                {"FOREX_REMOTE_ACCESS": "0"},
                server_address="127.0.0.1",
            )
        )
        self.assertTrue(auth.remote_access_is_configured(environ))
        self.assertFalse(auth.authorize_remote_access(state, "WRONG_TEST_TOKEN", environ))
        self.assertTrue(auth.authorize_remote_access(state, TEST_TOKEN, environ))
        self.assertTrue(auth.remote_access_authorized(state))

    def test_remote_access_rejects_when_token_is_missing(self):
        state = {}
        self.assertFalse(auth.remote_access_is_configured({"FOREX_REMOTE_ACCESS": "1"}))
        self.assertFalse(auth.authorize_remote_access(state, "anything", {}))
        self.assertFalse(auth.remote_access_authorized(state))

    def test_frontend_does_not_accept_access_tokens_from_query_parameters(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "frontend" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("query_params", app_source)
        self.assertNotIn("experimental_get_query_params", app_source)


if __name__ == "__main__":
    unittest.main()
