from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from bot.acquisition.gateway import (
    PROHIBITED_MT5_OPERATIONS,
    ReadOnlyMT5Gateway,
    assert_gateway_surface,
)
from bot.acquisition.models import AcquisitionError
from bot.acquisition.safety import assess_process_safety, strip_sensitive_environment

from .helpers import FakeReadOnlyMT5


UTC = timezone.utc


@pytest.mark.unit
def test_gateway_requires_confirmation_and_initializes_without_credentials():
    mt5 = FakeReadOnlyMT5()
    gateway = ReadOnlyMT5Gateway(mt5)
    with pytest.raises(AcquisitionError, match="confirmation"):
        gateway.initialize(confirmed_read_only_demo_export=False)
    assert not mt5.calls

    gateway.initialize(confirmed_read_only_demo_export=True)
    assert mt5.calls[0] == ("initialize", (), {})
    gateway.shutdown()


@pytest.mark.unit
def test_forbidden_methods_are_not_reachable_or_referenced():
    assert_gateway_surface()
    public = {name for name in dir(ReadOnlyMT5Gateway) if not name.startswith("_")}
    assert not public.intersection(PROHIBITED_MT5_OPERATIONS)
    source = inspect.getsource(ReadOnlyMT5Gateway)
    for operation in PROHIBITED_MT5_OPERATIONS:
        assert f".{operation}(" not in source


@pytest.mark.unit
def test_gateway_redacts_errors_and_safe_metadata_excludes_account_fields():
    mt5 = FakeReadOnlyMT5()
    mt5.last_error_value = (500, r"failure C:\Users\private\terminal 12345678")
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    code, message = gateway.last_error()
    metadata = gateway.safe_metadata("XAUUSDm", datetime(2026, 1, 1, tzinfo=UTC))
    assert code == 500
    assert message == "MT5_READ_ONLY_ERROR_REDACTED"
    serialized = repr(metadata).lower()
    assert "login" not in serialized
    assert "balance" not in serialized
    assert "equity" not in serialized


@pytest.mark.unit
def test_credentials_are_stripped_from_child_environment():
    blocked_keys = ("MT5_" + "PASS" + "WORD", "NEWS_" + "API" + "_" + "KEY")
    environment = {
        "PATH": "safe",
        "MT5_LOGIN": "123",
        "UNRELATED": "value",
    }
    environment.update({key: "fixture-value" for key in blocked_keys})
    clean = strip_sensitive_environment(environment)
    assert clean == {"PATH": "safe", "UNRELATED": "value"}


@pytest.mark.unit
def test_process_safety_blocks_other_python_without_disclosing_details():
    blocked = assess_process_safety(((10, "python.exe"), (11, "explorer.exe")), current_pid=99)
    safe = assess_process_safety(((99, "python.exe"), (11, "explorer.exe")), current_pid=99)
    assert not blocked.safe
    assert blocked.reason_code == "ACTIVE_OR_AMBIGUOUS_BOT_PROCESS"
    assert blocked.ambiguous_process_count == 1
    assert safe.safe
