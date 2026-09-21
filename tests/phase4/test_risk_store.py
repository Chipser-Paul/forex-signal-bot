from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from bot.execution.risk import (
    AccountSnapshot,
    CircuitStatus,
    ClosedTradeOutcome,
    RiskError,
    RiskStateStore,
    StoreStatus,
    consume_closed_outcome,
    apply_account_snapshot,
)
from tests.phase4.helpers import NOW, policy, state


def test_initialization_requires_explicit_empty_store_and_zero_positions(tmp_path):
    store = RiskStateStore(tmp_path / "risk.json")
    with pytest.raises(RiskError, match="zero known"):
        from bot.execution.risk import initialize_risk_state
        from tests.phase4.helpers import snapshot

        initialize_risk_state(snapshot(), policy(), known_strategy_positions=1)
    store.initialize(state())
    with pytest.raises(RiskError, match="already exists"):
        store.initialize(state())


def test_atomic_roundtrip_and_deterministic_backup(tmp_path):
    store = RiskStateStore(tmp_path / "risk.json")
    store.initialize(state())
    updated = replace(state(), current_equity=990.0, circuit_status=CircuitStatus.DAILY_PAUSED)
    store.save(updated)
    assert store.load().state == updated
    assert store.backup_path.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_interruption_before_replace_preserves_primary_and_cleans_temp(tmp_path):
    base = RiskStateStore(tmp_path / "risk.json")
    base.initialize(state())

    def interrupt(_temp, target):
        if target.name == "risk.json":
            raise RuntimeError("simulated interruption")

    interrupted = RiskStateStore(tmp_path / "risk.json", before_replace=interrupt)
    with pytest.raises(RuntimeError, match="interruption"):
        interrupted.save(replace(state(), current_equity=999.0))
    assert base.load().state == state()
    assert not list(tmp_path.glob("*.tmp"))


def test_truncated_primary_recovers_valid_backup(tmp_path):
    store = RiskStateStore(tmp_path / "risk.json")
    original = state()
    store.initialize(original)
    store.save(replace(original, current_equity=990.0))
    store.path.write_text("{", encoding="utf-8")
    result = store.load()
    assert result.status is StoreStatus.RECOVERED_BACKUP
    assert result.state.current_equity == 990.0
    assert json.loads(store.path.read_text(encoding="utf-8"))["current_equity"] == 990.0


def test_both_files_corrupt_fail_closed(tmp_path):
    store = RiskStateStore(tmp_path / "risk.json")
    store.initialize(state())
    store.path.write_text("{", encoding="utf-8")
    store.backup_path.write_text("[]", encoding="utf-8")
    result = store.load()
    assert result.status is StoreStatus.STATE_CORRUPT
    assert result.state is None


def test_missing_primary_with_backup_is_not_silent_initialization(tmp_path):
    store = RiskStateStore(tmp_path / "risk.json")
    store.initialize(state())
    store.path.unlink()
    result = store.load()
    assert result.status is StoreStatus.MISSING_PRIMARY
    assert result.state is None


def test_concurrent_readers_and_writers_leave_valid_state(tmp_path):
    store = RiskStateStore(tmp_path / "risk.json")
    store.initialize(state())
    candidates = [replace(state(), current_equity=990.0 + index) for index in range(5)]

    def write(candidate):
        store.save(candidate)
        return store.load().state

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(write, candidates))
    final = store.load()
    assert final.status is StoreStatus.LOADED
    assert final.state.current_equity in {candidate.current_equity for candidate in candidates}
    assert all(result is not None for result in results)


def test_duplicate_outcome_remains_idempotent_across_restart(tmp_path):
    store = RiskStateStore(tmp_path / "risk.json")
    outcome = ClosedTradeOutcome("outcome", "trade", NOW, -1.0)
    updated, _ = consume_closed_outcome(state(), outcome, policy())
    store.initialize(updated)
    loaded = store.load().state
    replayed, consumed = consume_closed_outcome(loaded, outcome, policy())
    assert consumed is False
    assert replayed.consecutive_losses == 1


def test_schema_account_and_policy_mismatches_are_rejected(tmp_path):
    store = RiskStateStore(tmp_path / "risk.json")
    store.initialize(state())
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["schema_version"] = 999
    store.path.write_text(json.dumps(payload), encoding="utf-8")
    store.backup_path.write_text(json.dumps(payload), encoding="utf-8")
    assert store.load().status is StoreStatus.STATE_CORRUPT


def test_persisted_state_contains_no_credentials(tmp_path):
    store = RiskStateStore(tmp_path / "risk.json")
    store.initialize(state())
    text = store.path.read_text(encoding="utf-8").lower()
    assert "password" not in text
    assert "token" not in text
    assert "login" not in text


@pytest.mark.parametrize(
    ("equity", "expected"),
    [
        (980.0, CircuitStatus.DAILY_PAUSED),
        (960.0, CircuitStatus.WEEKLY_PAUSED),
        (920.0, CircuitStatus.HARD_STOPPED),
    ],
)
def test_drawdown_circuit_survives_restart(tmp_path, equity, expected):
    current = state()
    account = AccountSnapshot(
        account_ref=current.account_ref,
        balance=1000.0,
        equity=equity,
        floating_pnl=equity - 1000.0,
        margin=0.0,
        free_margin=equity,
        currency="USD",
        timestamp=NOW,
        source="test",
    )
    breached, _ = apply_account_snapshot(current, account, policy(), now=NOW)
    store = RiskStateStore(tmp_path / "risk.json")
    store.initialize(breached)
    assert RiskStateStore(store.path).load().state.circuit_status is expected
