from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any, Iterable

from .models import (
    ExecutionAction,
    ExecutionReason,
    ExecutionStatus,
    ReconciliationResult,
    ReconciliationState,
    stable_execution_id,
)
from .registry import ExecutionRegistry


@dataclass(frozen=True)
class LocalPosition:
    trade_id: str
    symbol: str
    ticket: int
    direction: str
    remaining_volume: float
    stop: float | None
    target: float | None

    def __post_init__(self) -> None:
        if not self.trade_id or not self.symbol or self.ticket <= 0:
            raise ValueError("local position identity is invalid")
        if (
            self.direction not in ("buy", "sell")
            or not math.isfinite(self.remaining_volume)
            or self.remaining_volume <= 0
        ):
            raise ValueError("local position direction or volume is invalid")
        for name, value in (("stop", self.stop), ("target", self.target)):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"local position {name} is invalid")


def _comment(value: Any) -> str:
    return str(getattr(value, "comment", "") or "")


def _magic(value: Any) -> int:
    return int(getattr(value, "magic", 0) or 0)


def _ticket(value: Any) -> int:
    return int(getattr(value, "ticket", 0) or getattr(value, "position_id", 0) or 0)


def _position_ticket(value: Any) -> int:
    return int(getattr(value, "position_id", 0) or getattr(value, "position", 0) or _ticket(value))


def is_owned_position(
    position: Any,
    *,
    magic_number: int,
    symbol: str,
    ticket: int,
    trade_id: str | None = None,
) -> bool:
    if magic_number <= 0 or _magic(position) != magic_number:
        return False
    if str(getattr(position, "symbol", "")) != symbol or _ticket(position) != int(ticket):
        return False
    if trade_id is not None and f":{trade_id[:8]}:" not in _comment(position):
        return False
    return True


def broker_identity_matches(value: Any, *, magic_number: int, action_id: str) -> bool:
    return _magic(value) == magic_number and _comment(value).endswith(f":{action_id[:8]}")


class StartupReconciler:
    def __init__(self, registry: ExecutionRegistry, magic_number: int) -> None:
        self.registry = registry
        self.magic_number = magic_number

    def reconcile_action(
        self,
        action_id: str,
        *,
        orders: Iterable[Any],
        positions: Iterable[Any],
        deals: Iterable[Any],
        now: datetime,
        absence_proven: bool = False,
    ) -> ReconciliationResult:
        record = self.registry.get(action_id)
        reconciliation_id = stable_execution_id("reconcile", action_id)
        if record is None:
            return ReconciliationResult(
                reconciliation_id,
                ReconciliationState.REQUIRED,
                ExecutionReason.RECONCILIATION_REQUIRED,
                now,
                action_id=action_id,
                block_new_entries=True,
            )
        matches = [
            item
            for item in (*tuple(orders), *tuple(positions), *tuple(deals))
            if broker_identity_matches(item, magic_number=self.magic_number, action_id=action_id)
        ]
        if matches:
            match = matches[0]
            position_ticket = _position_ticket(match) or record.position_ticket
            self.registry.transition(
                action_id,
                ExecutionStatus.CONFIRMED,
                now,
                reason=ExecutionReason.RECONCILED_CONFIRMED,
                order_ticket=int(getattr(match, "order", 0) or record.order_ticket or 0) or None,
                deal_ticket=int(getattr(match, "deal", 0) or _ticket(match) or 0) or None,
                position_ticket=position_ticket,
                executed_volume=float(getattr(match, "volume", 0.0) or record.executed_volume),
                executed_price=(
                    float(getattr(match, "price", 0.0) or record.executed_price or 0.0)
                    or None
                ),
            )
            return ReconciliationResult(
                reconciliation_id,
                ReconciliationState.MATCHED,
                ExecutionReason.RECONCILED_CONFIRMED,
                now,
                trade_id=record.trade_id,
                action_id=action_id,
                position_ticket=position_ticket,
            )
        if absence_proven:
            self.registry.transition(
                action_id,
                ExecutionStatus.REJECTED,
                now,
                reason=ExecutionReason.RECONCILED_ABSENT,
            )
            return ReconciliationResult(
                reconciliation_id,
                ReconciliationState.ABSENT_CONFIRMED,
                ExecutionReason.RECONCILED_ABSENT,
                now,
                trade_id=record.trade_id,
                action_id=action_id,
            )
        self.registry.transition(
            action_id,
            ExecutionStatus.RECONCILIATION_REQUIRED,
            now,
            reason=ExecutionReason.RECONCILIATION_REQUIRED,
        )
        return ReconciliationResult(
            reconciliation_id,
            ReconciliationState.REQUIRED,
            ExecutionReason.RECONCILIATION_REQUIRED,
            now,
            trade_id=record.trade_id,
            action_id=action_id,
            block_new_entries=True,
        )

    def reconcile_startup(
        self,
        local_positions: Iterable[LocalPosition],
        *,
        broker_positions: Iterable[Any],
        broker_orders: Iterable[Any],
        recent_deals: Iterable[Any],
        now: datetime,
    ) -> tuple[ReconciliationResult, ...]:
        local = {position.ticket: position for position in local_positions}
        broker = {_ticket(position): position for position in broker_positions}
        results: list[ReconciliationResult] = []

        for ticket, local_position in sorted(local.items()):
            broker_position = broker.get(ticket)
            rid = stable_execution_id("startup", local_position.trade_id, ticket)
            if broker_position is not None:
                if is_owned_position(
                    broker_position,
                    magic_number=self.magic_number,
                    symbol=local_position.symbol,
                    ticket=ticket,
                    trade_id=local_position.trade_id,
                ):
                    results.append(
                        ReconciliationResult(
                            rid,
                            ReconciliationState.MATCHED,
                            ExecutionReason.RECONCILED_CONFIRMED,
                            now,
                            trade_id=local_position.trade_id,
                            position_ticket=ticket,
                        )
                    )
                else:
                    results.append(
                        ReconciliationResult(
                            rid,
                            ReconciliationState.REQUIRED,
                            ExecutionReason.OWNERSHIP_UNPROVEN,
                            now,
                            trade_id=local_position.trade_id,
                            position_ticket=ticket,
                            block_new_entries=True,
                        )
                    )
                continue
            close_deals = [deal for deal in recent_deals if _position_ticket(deal) == ticket]
            confirmed = any(_magic(deal) == self.magic_number for deal in close_deals)
            results.append(
                ReconciliationResult(
                    rid,
                    ReconciliationState.CLOSED_CONFIRMED if confirmed else ReconciliationState.REQUIRED,
                    ExecutionReason.RECONCILED_CONFIRMED if confirmed else ExecutionReason.RECONCILIATION_REQUIRED,
                    now,
                    trade_id=local_position.trade_id,
                    position_ticket=ticket,
                    block_new_entries=not confirmed,
                )
            )

        for ticket, broker_position in sorted(broker.items()):
            if ticket in local:
                continue
            rid = stable_execution_id("startup-broker", ticket)
            magic = _magic(broker_position)
            comment = _comment(broker_position)
            if magic != self.magic_number:
                results.append(
                    ReconciliationResult(
                        rid,
                        ReconciliationState.FOREIGN_IGNORED,
                        ExecutionReason.OWNERSHIP_UNPROVEN,
                        now,
                        position_ticket=ticket,
                    )
                )
                continue
            related = [deal for deal in recent_deals if _position_ticket(deal) == ticket]
            recoverable = all(
                float(getattr(broker_position, name, 0.0) or 0.0) > 0
                for name in ("price_open", "volume", "sl", "tp")
            )
            if comment.startswith("p5:") and related and recoverable:
                comment_parts = comment.split(":")
                results.append(
                    ReconciliationResult(
                        rid,
                        ReconciliationState.RECOVERED,
                        ExecutionReason.RECOVERED_POSITION,
                        now,
                        position_ticket=ticket,
                        recovered={
                            "trade_id_fragment": comment_parts[1],
                            "symbol": str(getattr(broker_position, "symbol", "")),
                            "direction": (
                                "buy" if int(getattr(broker_position, "type", 0) or 0) == 0 else "sell"
                            ),
                            "entry_price": float(getattr(broker_position, "price_open", 0.0) or 0.0),
                            "remaining_volume": float(getattr(broker_position, "volume", 0.0) or 0.0),
                            "stop": float(getattr(broker_position, "sl", 0.0) or 0.0),
                            "target": float(getattr(broker_position, "tp", 0.0) or 0.0),
                            "partial_history": "UNKNOWN",
                        },
                    )
                )
            else:
                results.append(
                    ReconciliationResult(
                        rid,
                        ReconciliationState.REQUIRED,
                        ExecutionReason.OWNERSHIP_UNPROVEN,
                        now,
                        position_ticket=ticket,
                        block_new_entries=True,
                    )
                )

        for action_id, record in sorted(self.registry.snapshot().items()):
            if record.state not in (
                ExecutionStatus.SUBMITTING,
                ExecutionStatus.UNCERTAIN,
                ExecutionStatus.RECONCILIATION_REQUIRED,
            ):
                continue
            results.append(
                self.reconcile_action(
                    action_id,
                    orders=broker_orders,
                    positions=broker_positions,
                    deals=recent_deals,
                    now=now,
                )
            )
        return tuple(results)
