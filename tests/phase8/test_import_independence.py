from __future__ import annotations

import sys
from pathlib import Path

from tests.conftest import REAL_POPEN


ROOT = Path(__file__).resolve().parents[2]


def test_session_clock_imports_in_fresh_interpreter() -> None:
    process = REAL_POPEN(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(ROOT)!r}); "
                "from bot.utils.session_clock import get_session_context; "
                "assert callable(get_session_context)"
            ),
        ],
        cwd=ROOT,
        stdout=-1,
        stderr=-1,
        text=True,
    )
    stdout, stderr = process.communicate(timeout=30)
    assert process.returncode == 0, stderr or stdout
