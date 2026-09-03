from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

from filelock import FileLock

from .models import CircuitStatus, RiskError, RiskState


class StoreStatus(str, Enum):
    LOADED = "LOADED"
    RECOVERED_BACKUP = "RECOVERED_BACKUP"
    UNINITIALIZED = "UNINITIALIZED"
    MISSING_PRIMARY = "MISSING_PRIMARY"
    STATE_CORRUPT = "STATE_CORRUPT"


@dataclass(frozen=True)
class StoreLoadResult:
    status: StoreStatus
    state: RiskState | None


def state_to_payload(state: RiskState) -> dict:
    payload = asdict(state)
    payload["circuit_status"] = state.circuit_status.value
    for key in ("initialized_at", "last_trade_at", "last_snapshot_at"):
        value = getattr(state, key)
        payload[key] = None if value is None else value.isoformat()
    payload["processed_outcome_ids"] = list(state.processed_outcome_ids)
    return payload


def state_from_payload(payload: dict) -> RiskState:
    if not isinstance(payload, dict):
        raise RiskError("risk state must be a JSON object")
    allowed = set(RiskState.__dataclass_fields__)
    if set(payload) != allowed:
        raise RiskError("risk-state fields do not match the versioned schema")
    values = dict(payload)
    values["circuit_status"] = CircuitStatus(values["circuit_status"])
    for key in ("initialized_at", "last_trade_at", "last_snapshot_at"):
        if values[key] is not None:
            values[key] = datetime.fromisoformat(values[key])
    values["processed_outcome_ids"] = tuple(values["processed_outcome_ids"])
    return RiskState(**values)


class RiskStateStore:
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

    def _read(self, path: Path) -> RiskState:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            raise RiskError("risk state is empty")
        return state_from_payload(json.loads(raw))

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

    def save(self, state: RiskState) -> None:
        encoded = (json.dumps(state_to_payload(state), sort_keys=True, indent=2) + "\n").encode("utf-8")
        with self.lock:
            self._save_locked(encoded)

    def _save_locked(self, encoded: bytes) -> None:
        self._atomic_write(self.path, encoded)
        self._atomic_write(self.backup_path, encoded)

    def load(self) -> StoreLoadResult:
        with self.lock:
            if not self.path.exists():
                status = StoreStatus.MISSING_PRIMARY if self.backup_path.exists() else StoreStatus.UNINITIALIZED
                return StoreLoadResult(status, None)
            try:
                return StoreLoadResult(StoreStatus.LOADED, self._read(self.path))
            except (OSError, ValueError, json.JSONDecodeError, RiskError):
                try:
                    recovered = self._read(self.backup_path)
                except (OSError, ValueError, json.JSONDecodeError, RiskError):
                    return StoreLoadResult(StoreStatus.STATE_CORRUPT, None)
                self._atomic_write(
                    self.path,
                    (json.dumps(state_to_payload(recovered), sort_keys=True, indent=2) + "\n").encode("utf-8"),
                )
                return StoreLoadResult(StoreStatus.RECOVERED_BACKUP, recovered)

    def initialize(self, state: RiskState) -> None:
        encoded = (json.dumps(state_to_payload(state), sort_keys=True, indent=2) + "\n").encode("utf-8")
        with self.lock:
            if self.path.exists() or self.backup_path.exists():
                raise RiskError("risk state already exists or requires explicit recovery")
            self._save_locked(encoded)
