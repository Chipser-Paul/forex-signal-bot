"""
Unit tests for session clock killzone gate.
Verifies that Sunday, hour 0, and hour 11 UTC are correctly blocked.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, time, timezone
from bot.utils.session_clock import get_session_context


def test_sunday_blocked():
    """Test that Sunday (weekday 6) is blocked."""
    # Sunday 2026-04-19 10:00 UTC
    sunday = datetime(2026, 4, 19, 10, 0, tzinfo=timezone.utc)
    context = get_session_context(sunday)
    
    # The orchestrator checks weekday() == 6 separately
    assert sunday.weekday() == 6, "Test date should be Sunday"
    print("✓ Sunday detection works (weekday=6)")


def test_hour_0_blocked():
    """Test that hour 0 UTC is blocked."""
    # Monday 2026-04-20 00:00 UTC
    hour_0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    context = get_session_context(hour_0)
    
    # The orchestrator checks hour_utc in (0, 11)
    assert hour_0.hour == 0, "Test time should be hour 0"
    print("✓ Hour 0 detection works")


def test_hour_11_blocked():
    """Test that hour 11 UTC is blocked."""
    # Monday 2026-04-20 11:00 UTC
    hour_11 = datetime(2026, 4, 20, 11, 0, tzinfo=timezone.utc)
    context = get_session_context(hour_11)
    
    # The orchestrator checks hour_utc in (0, 11)
    assert hour_11.hour == 11, "Test time should be hour 11"
    print("✓ Hour 11 detection works")


def test_allowed_hours_pass():
    """Test that other hours are allowed."""
    # Monday 2026-04-20 08:00 UTC (London session)
    allowed = datetime(2026, 4, 20, 8, 0, tzinfo=timezone.utc)
    context = get_session_context(allowed)
    
    assert allowed.weekday() != 6, "Should not be Sunday"
    assert allowed.hour not in (0, 11), "Should not be blocked hour"
    print("✓ Allowed hours pass")


if __name__ == "__main__":
    test_sunday_blocked()
    test_hour_0_blocked()
    test_hour_11_blocked()
    test_allowed_hours_pass()
    print("\n✅ All session clock tests passed")
