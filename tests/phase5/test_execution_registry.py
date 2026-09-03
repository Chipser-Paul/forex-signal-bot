from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from bot.execution.broker import (
    ExecutionAction,
    ExecutionError,
    ExecutionReason,
    ExecutionRegistry,
    ExecutionRegistryStore,
    ExecutionStatus,
)
from tests.phase5.helpers import NOW


def prepare(registry, action_id="action-1"):
    return registry.prepare(
        action_id=action_id,
        trade_id="trade-1",
        symbol="XAUUSDm",
        action_type=ExecutionAction.ENTRY,
        now=NOW,
    )


def test_registry_roundtrip_and_restart_preserve_submitting(tmp_path):
    store = ExecutionRegistryStore(tmp_path / "execution.json")
    first = ExecutionRegistry(store)
    prepare(first)
    first.transition(
        "action-1",
        ExecutionStatus.SUBMITTING,
        NOW,
        reason=ExecutionReason.APPROVED,
        attempt_count=1,
        last_attempt_id="attempt-1",
    )
    restarted = ExecutionRegistry(store)
    assert restarted.get("action-1").state is ExecutionStatus.SUBMITTING
    assert restarted.get("action-1").attempt_count == 1


def test_registry_primary_corruption_recovers_latest_backup(tmp_path):
    store = ExecutionRegistryStore(tmp_path / "execution.json")
    registry = ExecutionRegistry(store)
    prepare(registry)
    store.path.write_text("{truncated", encoding="utf-8")
    recovered = ExecutionRegistry(store)
    assert recovered.get("action-1").state is ExecutionStatus.PREPARED
    json.loads(store.path.read_text(encoding="utf-8"))


def test_registry_dual_corruption_fails_closed(tmp_path):
    store = ExecutionRegistryStore(tmp_path / "execution.json")
    registry = ExecutionRegistry(store)
    prepare(registry)
    store.path.write_text("bad", encoding="utf-8")
    store.backup_path.write_text("bad", encoding="utf-8")
    with pytest.raises(ExecutionError, match="cannot be recovered"):
        ExecutionRegistry(store)


def test_interruption_before_replace_keeps_previous_state_and_cleans_temp(tmp_path):
    path = tmp_path / "execution.json"
    stable = ExecutionRegistryStore(path)
    registry = ExecutionRegistry(stable)
    prepare(registry)

    def interrupt(_temp, target):
        if target == path:
            raise OSError("simulated interruption")

    interrupted = ExecutionRegistryStore(path, before_replace=interrupt)
    with pytest.raises(OSError, match="simulated"):
        ExecutionRegistry(interrupted).transition(
            "action-1",
            ExecutionStatus.CHECKED,
            NOW,
            reason=ExecutionReason.APPROVED,
        )
    assert ExecutionRegistry(stable).get("action-1").state is ExecutionStatus.PREPARED
    assert not list(tmp_path.glob("*.tmp"))


def test_concurrent_writers_do_not_drop_records(tmp_path):
    path = tmp_path / "execution.json"

    def write(index):
        registry = ExecutionRegistry(ExecutionRegistryStore(path))
        prepare(registry, f"action-{index}")

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(12)))
    assert len(ExecutionRegistry(ExecutionRegistryStore(path)).snapshot()) == 12


def test_registry_payload_contains_no_credentials(tmp_path):
    path = tmp_path / "execution.json"
    registry = ExecutionRegistry(ExecutionRegistryStore(path))
    prepare(registry)
    raw = path.read_text(encoding="utf-8").lower()
    assert "password" not in raw
    assert "token" not in raw
    assert "mt5_login" not in raw
