from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping

from filelock import FileLock

from .models import (
    SCHEMA_VERSION,
    ExecutionAction,
    ExecutionError,
    ExecutionReason,
    ExecutionStatus,
    RegistryRecord,
)


def record_to_payload(record: RegistryRecord) -> dict:
    payload = asdict(record)
    payload["action_type"] = record.action_type.value
    payload["state"] = record.state.value
    payload["reason"] = record.reason.value
    payload["created_at"] = record.created_at.isoformat()
    payload["updated_at"] = record.updated_at.isoformat()
    return payload


def record_from_payload(payload: Mapping[str, object]) -> RegistryRecord:
    if set(payload) != set(RegistryRecord.__dataclass_fields__):
        raise ExecutionError("execution registry record does not match schema")
    values = dict(payload)
    values["action_type"] = ExecutionAction(str(values["action_type"]))
    values["state"] = ExecutionStatus(str(values["state"]))
    values["reason"] = ExecutionReason(str(values["reason"]))
    values["created_at"] = datetime.fromisoformat(str(values["created_at"]))
    values["updated_at"] = datetime.fromisoformat(str(values["updated_at"]))
    return RegistryRecord(**values)


class ExecutionRegistryStore:
    def __init__(
        self,
        path: Path,
        *,
        before_replace: Callable[[Path, Path], None] | None = None,
    ) -> None:
        self.path = Path(path)
        self.backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        self.lock = FileLock(str(self.path.with_suffix(self.path.suffix + ".lock")))
        self.before_replace = before_replace

    def _decode(self, path: Path) -> dict[str, RegistryRecord]:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            raise ExecutionError("execution registry is empty")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "records"}:
            raise ExecutionError("execution registry envelope is invalid")
        if payload["schema_version"] != SCHEMA_VERSION or not isinstance(payload["records"], dict):
            raise ExecutionError("execution registry schema is unsupported")
        records = {
            str(action_id): record_from_payload(record_payload)
            for action_id, record_payload in payload["records"].items()
        }
        if any(action_id != record.action_id for action_id, record in records.items()):
            raise ExecutionError("execution registry key does not match action identity")
        return records

    def _encode(self, records: Mapping[str, RegistryRecord]) -> bytes:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "records": {
                action_id: record_to_payload(records[action_id])
                for action_id in sorted(records)
            },
        }
        return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")

    def _atomic_write(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, raw_temp = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temp_path = Path(raw_temp)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if self.before_replace is not None:
                self.before_replace(temp_path, path)
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _save_locked(self, records: Mapping[str, RegistryRecord]) -> None:
        encoded = self._encode(records)
        self._atomic_write(self.path, encoded)
        self._atomic_write(self.backup_path, encoded)

    def _load_locked(self) -> dict[str, RegistryRecord]:
        if not self.path.exists() and not self.backup_path.exists():
            return {}
        try:
            return self._decode(self.path)
        except (OSError, ValueError, json.JSONDecodeError, ExecutionError):
            try:
                recovered = self._decode(self.backup_path)
            except (OSError, ValueError, json.JSONDecodeError, ExecutionError) as exc:
                raise ExecutionError("execution registry is corrupt and cannot be recovered") from exc
            self._atomic_write(self.path, self._encode(recovered))
            return recovered

    def load(self) -> dict[str, RegistryRecord]:
        with self.lock:
            return self._load_locked()

    def mutate(
        self,
        mutator: Callable[[dict[str, RegistryRecord]], dict[str, RegistryRecord]],
    ) -> dict[str, RegistryRecord]:
        with self.lock:
            current = self._load_locked()
            updated = mutator(dict(current))
            self._save_locked(updated)
            return updated


class ExecutionRegistry:
    def __init__(self, store: ExecutionRegistryStore | None = None) -> None:
        self.store = store
        self._records: dict[str, RegistryRecord] = {}
        self._lock = threading.RLock()
        if store is not None:
            self._records = store.load()

    def snapshot(self) -> dict[str, RegistryRecord]:
        if self.store is not None:
            self._records = self.store.load()
        return dict(self._records)

    def get(self, action_id: str) -> RegistryRecord | None:
        return self.snapshot().get(action_id)

    def _mutate(
        self,
        mutator: Callable[[dict[str, RegistryRecord]], dict[str, RegistryRecord]],
    ) -> dict[str, RegistryRecord]:
        if self.store is not None:
            self._records = self.store.mutate(mutator)
            return self._records
        with self._lock:
            self._records = mutator(dict(self._records))
            return self._records

    def prepare(
        self,
        *,
        action_id: str,
        trade_id: str,
        symbol: str,
        action_type: ExecutionAction,
        now: datetime,
    ) -> RegistryRecord:
        created: RegistryRecord | None = None

        def operation(records: dict[str, RegistryRecord]) -> dict[str, RegistryRecord]:
            nonlocal created
            existing = records.get(action_id)
            if existing is not None:
                created = existing
                return records
            created = RegistryRecord(
                action_id=action_id,
                trade_id=trade_id,
                symbol=symbol,
                action_type=action_type,
                state=ExecutionStatus.PREPARED,
                created_at=now,
                updated_at=now,
            )
            records[action_id] = created
            return records

        self._mutate(operation)
        assert created is not None
        return created

    def transition(
        self,
        action_id: str,
        state: ExecutionStatus,
        now: datetime,
        *,
        reason: ExecutionReason,
        attempt_count: int | None = None,
        broker_retcode: int | None = None,
        order_ticket: int | None = None,
        deal_ticket: int | None = None,
        position_ticket: int | None = None,
        executed_volume: float | None = None,
        executed_price: float | None = None,
        last_attempt_id: str | None = None,
    ) -> RegistryRecord:
        updated_record: RegistryRecord | None = None

        def operation(records: dict[str, RegistryRecord]) -> dict[str, RegistryRecord]:
            nonlocal updated_record
            current = records.get(action_id)
            if current is None:
                raise ExecutionError("execution action must be prepared before transition")
            values = {
                "state": state,
                "updated_at": now,
                "reason": reason,
                "attempt_count": current.attempt_count if attempt_count is None else attempt_count,
                "broker_retcode": (
                    current.broker_retcode if broker_retcode is None else broker_retcode
                ),
                "order_ticket": current.order_ticket if order_ticket is None else order_ticket,
                "deal_ticket": current.deal_ticket if deal_ticket is None else deal_ticket,
                "position_ticket": current.position_ticket if position_ticket is None else position_ticket,
                "executed_volume": current.executed_volume if executed_volume is None else executed_volume,
                "executed_price": current.executed_price if executed_price is None else executed_price,
                "last_attempt_id": current.last_attempt_id if last_attempt_id is None else last_attempt_id,
            }
            updated_record = replace(current, **values)
            records[action_id] = updated_record
            return records

        self._mutate(operation)
        assert updated_record is not None
        return updated_record
