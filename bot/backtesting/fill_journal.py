"""Durable outbox of existing Phase 7 fills, replayed before setup acknowledgement."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from filelock import FileLock

from bot.backtesting.models import FidelityClass, HistoricalExecutionError, Side, SimulatedFill, enum_json
from bot.backtesting.outputs import _atomic_write
from bot.execution.broker.models import ExecutionAction, ExecutionReason, ExecutionStatus
from bot.execution.broker.registry import ExecutionRegistry, ExecutionRegistryStore


class HistoricalFillJournal:
    """Immutable per-fill records; no speculative trigger/submission records."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def publish_rejection(self, binding, rejection: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        if rejection.get("action_id") != binding.action_id or not rejection.get("reason_code"):
            raise HistoricalExecutionError("historical rejection lacks authoritative action evidence")
        timestamp = rejection["timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        registry = ExecutionRegistry(ExecutionRegistryStore(self.directory / "rejected-actions.json"))
        registry.prepare(action_id=binding.action_id, trade_id=binding.trade_id, symbol=binding.symbol,
            action_type=ExecutionAction.ENTRY, now=datetime.fromisoformat(binding.entry_event_at))
        registry.transition(binding.action_id, ExecutionStatus.REJECTED, timestamp, reason=ExecutionReason.BROKER_REJECTED)

    def publish(self, fill: SimulatedFill) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(fill.fill_id.encode()).hexdigest() + ".fill.json"
        path = self.directory / name
        serialized = json.dumps(enum_json(fill), sort_keys=True, separators=(",", ":"), allow_nan=False)
        with FileLock(str(self.directory / "outbox.lock")):
            if path.exists():
                if path.read_text(encoding="utf-8") != serialized:
                    raise HistoricalExecutionError("historical fill identity was reused with changed evidence")
                return
            _atomic_write(path, serialized)

    def snapshot(self) -> dict[str, SimulatedFill]:
        self.directory.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.directory / "outbox.lock")):
            result = ExecutionRegistry(ExecutionRegistryStore(self.directory / "rejected-actions.json")).snapshot()
            for path in sorted(self.directory.glob("*.fill.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    data["timestamp"] = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                    data["side"] = Side(data["side"])
                    data["fidelity"] = FidelityClass(data["fidelity"])
                    fill = SimulatedFill(**data)
                    if path.name != hashlib.sha256(fill.fill_id.encode()).hexdigest() + ".fill.json":
                        raise ValueError("fill filename identity mismatch")
                    existing = result.get(fill.action_id)
                    if existing is not None:
                        if not isinstance(existing, SimulatedFill):
                            raise ValueError("entry action has conflicting rejection and fill evidence")
                        if (existing.trade_id, existing.symbol, existing.side, existing.position_id) != (
                                fill.trade_id, fill.symbol, fill.side, fill.position_id):
                            raise ValueError("conflicting fills for one entry action")
                        # Consumption belongs to the first positive entry fill.
                        # Later fills stay auditable but never consume again.
                        fill = min((existing, fill), key=lambda item: (item.timestamp, item.fill_id))
                    result[fill.action_id] = fill
                except (TypeError, ValueError, KeyError, OSError) as exc:
                    raise HistoricalExecutionError("historical fill outbox is malformed") from exc
            return result
