"""Locked, atomic setup replay snapshots; fill stores remain authoritative."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable

from filelock import FileLock

from bot.strategy.setup_consumption import canonical
from bot.strategy.setup_state import SetupStateError, SetupStateRecord


STORE_SCHEMA = "phase8n.setup-replay-store.v1"


class SetupReplayStore:
    def __init__(self, path: Path, *, identity: str) -> None:
        if not identity:
            raise SetupStateError("setup store identity required")
        self.path = Path(path)
        self.backup = self.path.with_suffix(self.path.suffix + ".bak")
        self.marker = self.path.with_suffix(self.path.suffix + ".initialized")
        self.identity = identity
        self.lock = FileLock(str(self.path) + ".lock")

    def _encode(self, record: SetupStateRecord) -> str:
        record.data()
        content = {"schema": STORE_SCHEMA, "identity": self.identity, "record": record.payload}
        return canonical({**content, "sha256": hashlib.sha256(canonical(content).encode()).hexdigest()})

    def _decode(self, path: Path) -> SetupStateRecord:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            content = {key: value[key] for key in ("schema", "identity", "record")}
            if (set(value) != {*content, "sha256"} or value["schema"] != STORE_SCHEMA
                    or value["identity"] != self.identity
                    or value["sha256"] != hashlib.sha256(canonical(content).encode()).hexdigest()):
                raise ValueError("setup store identity or checksum mismatch")
            record = SetupStateRecord(value["record"])
            record.data()
            return record
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise SetupStateError("setup replay store is corrupt or incompatible") from exc

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _load_locked(self) -> SetupStateRecord:
        try:
            return self._decode(self.path)
        except SetupStateError:
            recovered = self._decode(self.backup)
            self._atomic_write(self.path, self._encode(recovered))
            return recovered

    def load(self) -> SetupStateRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            return self._load_locked()

    def initialize(self, initial: SetupStateRecord) -> SetupStateRecord:
        """Explicit first initialization only; missing prior state never resets protection."""
        initial.data()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            if self.path.exists() or self.backup.exists():
                return self._load_locked()
            if self.marker.exists():
                raise SetupStateError("previously initialized setup replay state disappeared")
            self._atomic_write(self.marker, STORE_SCHEMA)
            self._atomic_write(self.path, self._encode(initial))
            self._atomic_write(self.backup, self._encode(initial))
            return initial

    def mutate(self, operation: Callable[[SetupStateRecord], SetupStateRecord]) -> SetupStateRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            current = self._load_locked()
            updated = operation(current)
            updated.data()
            self._atomic_write(self.path, self._encode(updated))
            self._atomic_write(self.backup, self._encode(updated))
            return updated
