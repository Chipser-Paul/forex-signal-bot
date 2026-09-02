from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frontend.utils import credential_store, session_manager


RUN_INTEGRATION = os.getenv("RUN_WINDOWS_KEYRING_INTEGRATION") == "1"


@unittest.skipUnless(os.name == "nt", "Windows Credential Manager test")
@unittest.skipUnless(RUN_INTEGRATION, "opt-in Windows keyring integration test")
class WindowsKeyringIntegrationTests(unittest.TestCase):
    def test_save_retrieve_and_logout_delete_use_windows_backend(self):
        import keyring

        login = "PHASE0_DUMMY_LOGIN_20260902"
        server = "PHASE0_DUMMY_SERVER"
        password = "PHASE0_DUMMY_PASSWORD_DO_NOT_USE"  # pragma: allowlist secret
        backend = keyring.get_keyring()
        backend_identity = f"{type(backend).__module__}.{type(backend).__name__}"
        self.assertIn("keyring.backends.Windows", backend_identity)
        self.assertGreater(float(getattr(backend, "priority", 0)), 0)

        try:
            self.assertTrue(credential_store.store_password(login, server, password))
            self.assertEqual(credential_store.get_password(login, server), password)

            with tempfile.TemporaryDirectory() as temporary_directory:
                session_file = Path(temporary_directory) / ".session.json"
                with patch.object(session_manager, "SESSION_FILE", str(session_file)):
                    session_manager.clear_session(login=login, server=server)

            self.assertIsNone(credential_store.get_password(login, server))
        finally:
            credential_store.delete_password(login, server)


if __name__ == "__main__":
    unittest.main()
