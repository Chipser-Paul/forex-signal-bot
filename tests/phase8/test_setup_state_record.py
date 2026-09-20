from datetime import datetime, timedelta, timezone

import pytest

from bot.strategy.setup_state import (
    SetupStateError, SetupStateRecord, inspect_legacy_snapshot,
    record_from_state, stable_setup_id, state_from_record,
)
from strategies.smc_engine.strategy_state import StrategyState


AT = datetime(2024, 3, 4, 12, 5, tzinfo=timezone.utc)


def _identity(side="bullish", ob="ob-1"):
    return stable_setup_id(
        symbol="XAUUSDm", side=side, decision_at=AT,
        source_identities={"M5": "2024-03-04T12:00Z", "H1": "2024-03-04T11:00Z"},
        structure_identity="structure-1", ob_identity=ob,
        fvg_identity="fvg-1", sweep_identity="sweep-1",
        config_fingerprint="phase6-frozen-v1",
    )


def test_complete_setup_state_roundtrip_is_deterministic():
    state = StrategyState(event_time=AT)
    state.update_structure("bullish", "confirmed")
    state.update_liquidity("sell", 5, "equal_lows")
    state.update_displacement((98.0, 99.0))
    state.register_setup_candidate(trade_direction="buy", ob_zone=(96.0, 100.0))
    record = record_from_state(state, event_at=AT, last_event_id="event-1")
    restored = state_from_record(record, AT + timedelta(minutes=5))
    assert restored.snapshot() == state.snapshot()
    assert restored.setup_candidate == state.setup_candidate
    assert restored.ob_zone == (96.0, 100.0)
    assert record_from_state(restored, event_at=AT, last_event_id="event-1") == record


def test_setup_id_is_order_independent_and_evidence_sensitive():
    assert _identity() == _identity()
    assert _identity("bullish") != _identity("bearish")
    assert _identity(ob="ob-1") != _identity(ob="ob-2")
    with pytest.raises(SetupStateError):
        stable_setup_id(
            symbol="XAUUSD", side="bullish", decision_at=AT,
            source_identities={}, structure_identity="", ob_identity=None,
            fvg_identity=None, sweep_identity=None, config_fingerprint="",
        )


def test_backward_or_malformed_state_fails_closed():
    record = record_from_state(StrategyState(event_time=AT), event_at=AT)
    with pytest.raises(SetupStateError, match="backward"):
        state_from_record(record, AT - timedelta(microseconds=1))
    with pytest.raises(SetupStateError):
        SetupStateRecord("not-json").data()


def test_legacy_active_setup_requires_reconciliation():
    active = inspect_legacy_snapshot({"state_name": "TRADE_ACTIVE", "last_update": AT.isoformat()})
    assert active.status == "RECONCILIATION_REQUIRED"
    assert "missing_identity" in active.reason
    inactive = inspect_legacy_snapshot({"state_name": "MAPPING_STRUCTURE"})
    assert inactive.status == "READ_ONLY_LEGACY"


@pytest.mark.parametrize("payload", ["[]", "null", "1", '"text"', '{}'])
def test_nonobject_or_incomplete_state_rejects_with_domain_error(payload):
    with pytest.raises(SetupStateError):
        SetupStateRecord(payload).data()
