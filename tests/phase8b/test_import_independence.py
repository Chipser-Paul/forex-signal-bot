from __future__ import annotations

import sys
from pathlib import Path

from bot.acquisition.safety import strip_sensitive_environment
from tests.conftest import REAL_POPEN


def test_guarded_cli_import_and_dry_run_never_import_mt5():
    root = Path(__file__).resolve().parents[2]
    code = '''
import importlib.abc
import sys
class NoMT5(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "MetaTrader5":
            raise AssertionError("real MT5 import before authorization")
sys.meta_path.insert(0, NoMT5())
from backtests.empirical_data_control import main
assert "MetaTrader5" not in sys.modules
assert main(["sample", "--dry-run"]) == 0
assert main(["estimate"]) == 0
assert "MetaTrader5" not in sys.modules
'''
    process = REAL_POPEN(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(root)!r});\n" + code],
        cwd=root, env=strip_sensitive_environment(), stdout=-1, stderr=-1, text=True,
    )
    stdout, stderr = process.communicate(timeout=30)
    assert process.returncode == 0, stderr or stdout
