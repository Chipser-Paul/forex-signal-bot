from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from .models import (
    BrokerSnapshot,
    BrokerSymbol,
    ExecutionAction,
    ExecutionError,
    ExecutionPolicy,
    ExecutionReason,
    ExecutionRejected,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    FillingMode,
    ResultClass,
    sanitized_comment,
    stable_execution_id,
)
from .reconciliation import StartupReconciler, broker_identity_matches, is_owned_position
from .registry import ExecutionRegistry
from .validation import (
    broker_filling_constant,
    corrected_absolute_levels,
    normalize_price,
    normalize_volume_down,
    select_filling_mode,
    stop_improves,
    stop_widened,
    tick_from_mt5,
    validate_directional_levels,
    validate_margin,
    validate_spread,
    validate_tick,
    with_reapproved_stop,
)


RiskRecheck = Callable[[float, float, float], float | None]


def _integer(value: Any) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed or None


def _float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def classify_retcode(broker: Any, retcode: int | None) -> tuple[ResultClass, ExecutionReason, bool]:
    groups = {
        ResultClass.SUCCESS: (
            "TRADE_RETCODE_DONE",
            "TRADE_RETCODE_PLACED",
        ),
        ResultClass.PARTIAL_SUCCESS: ("TRADE_RETCODE_DONE_PARTIAL",),
        ResultClass.INVALID_STOPS: ("TRADE_RETCODE_INVALID_STOPS",),
        ResultClass.PRICE_CHANGED: (
            "TRADE_RETCODE_REQUOTE",
            "TRADE_RETCODE_PRICE_CHANGED",
            "TRADE_RETCODE_PRICE_OFF",
        ),
        ResultClass.INSUFFICIENT_MARGIN: ("TRADE_RETCODE_NO_MONEY",),
        ResultClass.TRADING_UNAVAILABLE: (
            "TRADE_RETCODE_MARKET_CLOSED",
            "TRADE_RETCODE_TRADE_DISABLED",
        ),
        ResultClass.INVALID_REQUEST: (
            "TRADE_RETCODE_INVALID",
            "TRADE_RETCODE_INVALID_VOLUME",
            "TRADE_RETCODE_INVALID_PRICE",
            "TRADE_RETCODE_INVALID_FILL",
        ),
        ResultClass.UNCERTAIN: ("TRADE_RETCODE_TIMEOUT",),
        ResultClass.CONNECTION_FAILURE: ("TRADE_RETCODE_CONNECTION",),
    }
    matched = next(
        (
            category
            for category, names in groups.items()
            if retcode is not None
            and any(hasattr(broker, name) and retcode == int(getattr(broker, name)) for name in names)
        ),
        ResultClass.PERMANENT_REJECTION,
    )
    mapping = {
        ResultClass.SUCCESS: (ExecutionReason.CONFIRMED, False),
        ResultClass.PARTIAL_SUCCESS: (ExecutionReason.PARTIAL_FILL, False),
        ResultClass.INVALID_STOPS: (ExecutionReason.BROKER_INVALID_STOPS, True),
        ResultClass.PRICE_CHANGED: (ExecutionReason.BROKER_PRICE_CHANGED, True),
        ResultClass.INSUFFICIENT_MARGIN: (ExecutionReason.BROKER_INSUFFICIENT_MARGIN, False),
        ResultClass.TRADING_UNAVAILABLE: (ExecutionReason.BROKER_TRADING_UNAVAILABLE, False),
        ResultClass.INVALID_REQUEST: (ExecutionReason.BROKER_INVALID_REQUEST, False),
        ResultClass.UNCERTAIN: (ExecutionReason.BROKER_OUTCOME_UNCERTAIN, False),
        ResultClass.CONNECTION_FAILURE: (ExecutionReason.BROKER_OUTCOME_UNCERTAIN, False),
        ResultClass.PERMANENT_REJECTION: (ExecutionReason.BROKER_REJECTED, False),
    }
    reason, retryable = mapping[matched]
    return matched, reason, retryable


class SecureBrokerExecutor:
    def __init__(
        self,
        broker: Any,
        policy: ExecutionPolicy,
        registry: ExecutionRegistry,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.broker = broker
        self.policy = policy
        self.registry = registry
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.reconciler = StartupReconciler(registry, policy.magic_number)

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None:
            raise ExecutionError("execution clock must be timezone-aware")
        return now.astimezone(timezone.utc)

    def _symbol(self, symbol: str, direction: str, action: ExecutionAction) -> BrokerSymbol:
        raw = self.broker.symbol_info(symbol)
        if raw is None:
            raise ExecutionRejected(ExecutionReason.SYMBOL_MISSING, "broker symbol does not exist")
        if not bool(getattr(raw, "visible", False)):
            if not bool(self.broker.symbol_select(symbol, True)):
                raise ExecutionRejected(
                    ExecutionReason.SYMBOL_SELECTION_FAILED,
                    "broker symbol selection failed",
                )
            raw = self.broker.symbol_info(symbol)
            if raw is None or not bool(getattr(raw, "visible", False)):
                raise ExecutionRejected(
                    ExecutionReason.SYMBOL_NOT_VISIBLE,
                    "broker symbol is not visible after selection",
                )
        try:
            model = BrokerSymbol(
                symbol=symbol,
                visible=bool(raw.visible),
                trade_mode=int(raw.trade_mode),
                execution_mode=int(raw.trade_exemode),
                filling_flags=int(raw.filling_mode),
                point=float(raw.point),
                digits=int(raw.digits),
                stops_level_points=int(getattr(raw, "trade_stops_level")),
                freeze_level_points=int(getattr(raw, "trade_freeze_level")),
                volume_min=float(raw.volume_min),
                volume_max=float(raw.volume_max),
                volume_step=float(raw.volume_step),
            )
        except (AttributeError, TypeError, ValueError, ExecutionError) as exc:
            raise ExecutionRejected(
                ExecutionReason.SYMBOL_METADATA_INVALID,
                "broker symbol metadata is incomplete or invalid",
            ) from exc

        disabled = int(getattr(self.broker, "SYMBOL_TRADE_MODE_DISABLED", 0))
        close_only = int(getattr(self.broker, "SYMBOL_TRADE_MODE_CLOSEONLY", 3))
        long_only = int(getattr(self.broker, "SYMBOL_TRADE_MODE_LONGONLY", 1))
        short_only = int(getattr(self.broker, "SYMBOL_TRADE_MODE_SHORTONLY", 2))
        if model.trade_mode == disabled:
            raise ExecutionRejected(
                ExecutionReason.SYMBOL_TRADE_MODE_REJECTED,
                "symbol trading is disabled",
            )
        if action is ExecutionAction.ENTRY:
            if model.trade_mode == close_only:
                raise ExecutionRejected(
                    ExecutionReason.SYMBOL_TRADE_MODE_REJECTED,
                    "symbol permits closes only",
                )
            if direction == "buy" and model.trade_mode == short_only:
                raise ExecutionRejected(
                    ExecutionReason.SYMBOL_TRADE_MODE_REJECTED,
                    "symbol does not permit long entries",
                )
            if direction == "sell" and model.trade_mode == long_only:
                raise ExecutionRejected(
                    ExecutionReason.SYMBOL_TRADE_MODE_REJECTED,
                    "symbol does not permit short entries",
                )
        return model

    def snapshot(
        self,
        symbol: str,
        direction: str,
        action: ExecutionAction,
        *,
        now: datetime | None = None,
    ) -> BrokerSnapshot:
        timestamp = self._now() if now is None else now.astimezone(timezone.utc)
        terminal = self.broker.terminal_info()
        account = self.broker.account_info()
        connected = bool(terminal is not None and getattr(terminal, "connected", False))
        trading = bool(
            terminal is not None
            and getattr(terminal, "trade_allowed", False)
            and account is not None
            and getattr(account, "trade_allowed", False)
        )
        if not connected:
            raise ExecutionRejected(
                ExecutionReason.CONNECTION_UNAVAILABLE,
                "broker terminal is not connected",
            )
        if not trading:
            raise ExecutionRejected(ExecutionReason.TRADING_DISABLED, "broker trading is unavailable")
        symbol_model = self._symbol(symbol, direction, action)
        tick = tick_from_mt5(self.broker.symbol_info_tick(symbol))
        validate_tick(tick, timestamp, self.policy)
        try:
            orders = tuple(self.broker.orders_get() or ())
            positions = tuple(self.broker.positions_get() or ())
            return BrokerSnapshot(
                timestamp=timestamp,
                connected=connected,
                trading_available=trading,
                equity=float(account.equity),
                margin=float(account.margin),
                free_margin=float(account.margin_free),
                symbol=symbol_model,
                tick=tick,
                orders=orders,
                positions=positions,
            )
        except (AttributeError, TypeError, ValueError, ExecutionError) as exc:
            raise ExecutionRejected(
                ExecutionReason.CONNECTION_UNAVAILABLE,
                "broker account snapshot is incomplete",
            ) from exc

    def entry_request(
        self,
        *,
        action_id: str,
        signal_id: str,
        trade_id: str,
        symbol: str,
        direction: str,
        volume: float,
        requested_trigger: float,
        executable_price: float,
        stop_price: float,
        target_price: float,
        risk_decision_id: str,
        approved_volume: float,
        approved_stop: float,
        created_at: datetime,
        expires_at: datetime | None = None,
    ) -> ExecutionRequest:
        return ExecutionRequest(
            action_id=action_id,
            signal_id=signal_id,
            trade_id=trade_id,
            symbol=symbol,
            direction=direction,
            action_type=ExecutionAction.ENTRY,
            volume=volume,
            requested_trigger=requested_trigger,
            executable_price=executable_price,
            stop_price=stop_price,
            target_price=target_price,
            deviation_points=self.policy.deviation_limit(symbol),
            filling_mode=None,
            magic_number=self.policy.magic_number,
            comment=sanitized_comment(trade_id, action_id),
            risk_decision_id=risk_decision_id,
            approved_volume=approved_volume,
            approved_stop=approved_stop,
            created_at=created_at,
            expires_at=expires_at,
        )

    def position_request(
        self,
        *,
        action_id: str,
        signal_id: str,
        trade_id: str,
        symbol: str,
        direction: str,
        action_type: ExecutionAction,
        volume: float,
        executable_price: float,
        position_ticket: int,
        risk_decision_id: str,
        approved_volume: float,
        created_at: datetime,
        stop_price: float | None = None,
        target_price: float | None = None,
        approved_stop: float | None = None,
    ) -> ExecutionRequest:
        return ExecutionRequest(
            action_id=action_id,
            signal_id=signal_id,
            trade_id=trade_id,
            symbol=symbol,
            direction=direction,
            action_type=action_type,
            volume=volume,
            requested_trigger=executable_price,
            executable_price=executable_price,
            stop_price=stop_price,
            target_price=target_price,
            deviation_points=self.policy.deviation_limit(symbol),
            filling_mode=None,
            magic_number=self.policy.magic_number,
            comment=sanitized_comment(trade_id, action_id),
            risk_decision_id=risk_decision_id,
            approved_volume=approved_volume,
            approved_stop=approved_stop,
            created_at=created_at,
            position_ticket=position_ticket,
        )

    def _result(
        self,
        request: ExecutionRequest,
        attempt_id: str,
        *,
        status: ExecutionStatus,
        reason: ExecutionReason,
        result_class: ResultClass,
        broker_result: Any = None,
        retry_eligible: bool = False,
        reconciliation_required: bool = False,
    ) -> ExecutionResult:
        executed = _float(getattr(broker_result, "volume", None)) or 0.0
        if result_class is ResultClass.SUCCESS and executed == 0:
            executed = request.volume
        return ExecutionResult(
            action_id=request.action_id,
            attempt_id=attempt_id,
            status=status,
            reason=reason,
            result_class=result_class,
            timestamp=self._now(),
            broker_retcode=_integer(getattr(broker_result, "retcode", None)),
            order_ticket=_integer(getattr(broker_result, "order", None)),
            deal_ticket=_integer(getattr(broker_result, "deal", None)),
            position_ticket=(
                _integer(getattr(broker_result, "position", None))
                or request.position_ticket
                or _integer(getattr(broker_result, "order", None))
            ),
            requested_volume=request.volume,
            executed_volume=executed,
            requested_price=request.executable_price,
            executed_price=_float(getattr(broker_result, "price", None)),
            remaining_unfilled_volume=max(0.0, request.volume - executed),
            retry_eligible=retry_eligible,
            reconciliation_required=reconciliation_required,
            filling_mode=request.filling_mode,
            diagnostics={"action_type": request.action_type.value},
        )

    def _rejected(
        self,
        request: ExecutionRequest,
        attempt_id: str,
        reason: ExecutionReason,
        *,
        result_class: ResultClass = ResultClass.INVALID_REQUEST,
    ) -> ExecutionResult:
        self.registry.transition(
            request.action_id,
            ExecutionStatus.REJECTED,
            self._now(),
            reason=reason,
            last_attempt_id=attempt_id,
        )
        return self._result(
            request,
            attempt_id,
            status=ExecutionStatus.REJECTED,
            reason=reason,
            result_class=result_class,
        )

    def _existing_broker_match(self, request: ExecutionRequest, snapshot: BrokerSnapshot) -> Any | None:
        return next(
            (
                value
                for value in (*snapshot.orders, *snapshot.positions)
                if broker_identity_matches(
                    value,
                    magic_number=self.policy.magic_number,
                    action_id=request.action_id,
                )
            ),
            None,
        )

    def _owned_position(self, request: ExecutionRequest, snapshot: BrokerSnapshot) -> Any:
        position = next(
            (
                value
                for value in snapshot.positions
                if int(getattr(value, "ticket", 0) or 0) == int(request.position_ticket or 0)
            ),
            None,
        )
        if position is None:
            raise ExecutionRejected(ExecutionReason.POSITION_NOT_FOUND, "broker position was not found")
        if not is_owned_position(
            position,
            magic_number=self.policy.magic_number,
            symbol=request.symbol,
            ticket=int(request.position_ticket),
            trade_id=request.trade_id,
        ):
            raise ExecutionRejected(
                ExecutionReason.OWNERSHIP_UNPROVEN,
                "broker position ownership could not be proven",
            )
        if request.action_type in (
            ExecutionAction.PARTIAL_CLOSE,
            ExecutionAction.FULL_CLOSE,
            ExecutionAction.LIQUIDATE,
        ) and request.volume > float(getattr(position, "volume", 0.0) or 0.0) + 1e-12:
            raise ExecutionRejected(
                ExecutionReason.CLOSE_VOLUME_EXCEEDS_POSITION,
                "close quantity exceeds broker remaining volume",
            )
        if request.action_type is ExecutionAction.MODIFY_STOP:
            current_stop = float(getattr(position, "sl", 0.0) or 0.0)
            if request.stop_price is None or current_stop <= 0 or not stop_improves(
                request.direction,
                current_stop,
                request.stop_price,
            ):
                raise ExecutionRejected(
                    ExecutionReason.STOP_NOT_IMPROVED,
                    "stop modification does not improve protection",
                )
        return position

    def _mt5_request(
        self,
        request: ExecutionRequest,
        snapshot: BrokerSnapshot,
    ) -> dict[str, Any]:
        if request.action_type is ExecutionAction.MODIFY_STOP:
            return {
                "action": int(self.broker.TRADE_ACTION_SLTP),
                "symbol": request.symbol,
                "position": int(request.position_ticket),
                "sl": float(request.stop_price),
                "tp": float(request.target_price or 0.0),
                "magic": request.magic_number,
                "comment": request.comment,
            }
        order_type = (
            int(self.broker.ORDER_TYPE_BUY)
            if request.direction == "buy"
            else int(self.broker.ORDER_TYPE_SELL)
        )
        if request.action_type is not ExecutionAction.ENTRY:
            order_type = (
                int(self.broker.ORDER_TYPE_SELL)
                if request.direction == "buy"
                else int(self.broker.ORDER_TYPE_BUY)
            )
        payload = {
            "action": int(self.broker.TRADE_ACTION_DEAL),
            "symbol": request.symbol,
            "volume": request.volume,
            "type": order_type,
            "price": request.executable_price,
            "deviation": request.deviation_points,
            "magic": request.magic_number,
            "comment": request.comment,
            "type_time": int(self.broker.ORDER_TIME_GTC),
            "type_filling": broker_filling_constant(self.broker, request.filling_mode),
        }
        if request.action_type is ExecutionAction.ENTRY:
            payload["sl"] = float(request.stop_price)
            payload["tp"] = float(request.target_price)
        else:
            payload["position"] = int(request.position_ticket)
        return payload

    def _validated_request(
        self,
        request: ExecutionRequest,
        snapshot: BrokerSnapshot,
        *,
        risk_recheck: RiskRecheck | None,
    ) -> tuple[ExecutionRequest, dict[str, Any], dict[str, float]]:
        validate_tick(snapshot.tick, snapshot.timestamp, self.policy)
        validate_spread(snapshot.symbol, snapshot.tick, request.stop_price, self.policy)
        volume = normalize_volume_down(request.volume, snapshot.symbol)
        if volume > request.approved_volume + 1e-12:
            raise ExecutionRejected(
                ExecutionReason.RISK_APPROVAL_INVALID,
                "normalized volume exceeds Phase 4 approval",
            )
        executable = snapshot.tick.ask if request.direction == "buy" else snapshot.tick.bid
        if request.action_type is not ExecutionAction.ENTRY:
            executable = snapshot.tick.bid if request.direction == "buy" else snapshot.tick.ask
            self._owned_position(request, snapshot)
        if request.action_type in (ExecutionAction.ENTRY, ExecutionAction.MODIFY_STOP):
            stop, target = validate_directional_levels(
                request.direction,
                executable,
                request.stop_price,
                request.target_price,
                snapshot.symbol,
                snapshot.tick,
                modification=request.action_type is ExecutionAction.MODIFY_STOP,
            )
        else:
            stop, target = request.stop_price, request.target_price
        candidate = replace(
            request,
            volume=volume,
            executable_price=normalize_price(executable, snapshot.symbol.digits),
            stop_price=stop,
            target_price=target,
            filling_mode=(
                None
                if request.action_type is ExecutionAction.MODIFY_STOP
                else select_filling_mode(self.broker, snapshot.symbol, self.policy)
            ),
        )
        if stop_widened(candidate.direction, candidate.approved_stop, candidate.stop_price):
            if risk_recheck is None:
                raise ExecutionRejected(
                    ExecutionReason.STOP_WIDENING_REQUIRES_RISK,
                    "a wider stop requires a new Phase 4 approval",
                )
            approved = risk_recheck(
                candidate.executable_price,
                float(candidate.stop_price),
                candidate.volume,
            )
            if approved is None or approved <= 0 or approved > candidate.approved_volume + 1e-12:
                raise ExecutionRejected(
                    ExecutionReason.RISK_APPROVAL_INVALID,
                    "Phase 4 rejected the wider stop",
                )
            candidate = replace(
                candidate,
                volume=min(candidate.volume, approved),
                approved_volume=approved,
                approved_stop=candidate.stop_price,
                risk_reapproved=True,
            )
        diagnostics: dict[str, float] = {}
        if candidate.action_type is ExecutionAction.ENTRY:
            try:
                required = self.broker.order_calc_margin(
                    int(
                        self.broker.ORDER_TYPE_BUY
                        if candidate.direction == "buy"
                        else self.broker.ORDER_TYPE_SELL
                    ),
                    candidate.symbol,
                    candidate.volume,
                    candidate.executable_price,
                )
            except Exception as exc:
                raise ExecutionRejected(
                    ExecutionReason.MARGIN_CALCULATION_FAILED,
                    "broker margin calculation is unavailable",
                ) from exc
            margin, projected_free, projected_level = validate_margin(
                required_margin=required,
                snapshot=snapshot,
                policy=self.policy,
            )
            diagnostics = {
                "required_margin": margin,
                "projected_free_margin": projected_free,
                "projected_margin_level": projected_level,
            }
        return candidate, self._mt5_request(candidate, snapshot), diagnostics

    def _check(self, request: ExecutionRequest, payload: dict[str, Any]) -> Any:
        try:
            checked = self.broker.order_check(payload)
        except Exception as exc:
            raise ExecutionRejected(ExecutionReason.PREFLIGHT_MISSING, "order_check failed") from exc
        if checked is None or getattr(checked, "retcode", None) is None:
            raise ExecutionRejected(ExecutionReason.PREFLIGHT_MISSING, "order_check returned no result")
        retcode = int(checked.retcode)
        accepted = {0}
        for name in ("TRADE_RETCODE_DONE", "TRADE_RETCODE_PLACED"):
            if hasattr(self.broker, name):
                accepted.add(int(getattr(self.broker, name)))
        if retcode not in accepted:
            category, reason, retryable = classify_retcode(self.broker, retcode)
            rejected = ExecutionRejected(reason, "broker preflight rejected the request")
            rejected.result_class = category
            rejected.retryable = retryable
            rejected.broker_result = checked
            raise rejected
        checked_volume = _float(getattr(checked, "volume", None))
        if checked_volume is not None and checked_volume > request.volume + 1e-12:
            raise ExecutionRejected(
                ExecutionReason.PREFLIGHT_VOLUME_INCREASE,
                "order_check suggested an unauthorized volume increase",
            )
        return checked

    def _attempt(
        self,
        request: ExecutionRequest,
        attempt_number: int,
        *,
        risk_recheck: RiskRecheck | None,
    ) -> tuple[ExecutionRequest, ExecutionResult]:
        attempt_id = stable_execution_id(request.action_id, "attempt", attempt_number)
        now = self._now()
        if request.expires_at is not None and now >= request.expires_at:
            return request, self._rejected(request, attempt_id, ExecutionReason.BROKER_REJECTED)
        try:
            snapshot = self.snapshot(request.symbol, request.direction, request.action_type, now=now)
            existing = self._existing_broker_match(request, snapshot)
            if existing is not None:
                self.registry.transition(
                    request.action_id,
                    ExecutionStatus.CONFIRMED,
                    now,
                    reason=ExecutionReason.RECONCILED_CONFIRMED,
                    position_ticket=_integer(getattr(existing, "ticket", None)),
                    executed_volume=_float(getattr(existing, "volume", None)) or 0.0,
                    last_attempt_id=attempt_id,
                )
                result = self._result(
                    request,
                    attempt_id,
                    status=ExecutionStatus.CONFIRMED,
                    reason=ExecutionReason.RECONCILED_CONFIRMED,
                    result_class=ResultClass.SUCCESS,
                    broker_result=existing,
                )
                return request, result

            candidate, payload, _diagnostics = self._validated_request(
                request,
                snapshot,
                risk_recheck=risk_recheck,
            )
            self._check(candidate, payload)

            # Rebuild and recheck at the final broker observation. This catches a
            # widened spread or changed executable price before any mutation.
            final_snapshot = self.snapshot(
                candidate.symbol,
                candidate.direction,
                candidate.action_type,
                now=self._now(),
            )
            final_candidate, final_payload, _final_diagnostics = self._validated_request(
                candidate,
                final_snapshot,
                risk_recheck=risk_recheck,
            )
            if final_candidate.executable_price != candidate.executable_price:
                if final_candidate.action_type is ExecutionAction.ENTRY:
                    if risk_recheck is None:
                        raise ExecutionRejected(
                            ExecutionReason.RISK_APPROVAL_INVALID,
                            "changed executable price requires Phase 4 reapproval",
                        )
                    approved = risk_recheck(
                        final_candidate.executable_price,
                        float(final_candidate.stop_price),
                        final_candidate.volume,
                    )
                    if approved is None or approved <= 0 or approved > candidate.approved_volume + 1e-12:
                        raise ExecutionRejected(
                            ExecutionReason.RISK_APPROVAL_INVALID,
                            "Phase 4 rejected the changed executable price",
                        )
                    final_candidate = replace(
                        final_candidate,
                        volume=min(final_candidate.volume, approved),
                        approved_volume=approved,
                        risk_reapproved=True,
                    )
                    final_candidate, final_payload, _final_diagnostics = self._validated_request(
                        final_candidate,
                        final_snapshot,
                        risk_recheck=risk_recheck,
                    )
                self._check(final_candidate, final_payload)
            else:
                self._check(final_candidate, final_payload)
        except ExecutionRejected as exc:
            result_class = getattr(exc, "result_class", ResultClass.INVALID_REQUEST)
            broker_result = getattr(exc, "broker_result", None)
            retryable = bool(getattr(exc, "retryable", False))
            self.registry.transition(
                request.action_id,
                ExecutionStatus.REJECTED,
                self._now(),
                reason=exc.reason,
                attempt_count=attempt_number,
                broker_retcode=_integer(getattr(broker_result, "retcode", None)),
                last_attempt_id=attempt_id,
            )
            return request, self._result(
                request,
                attempt_id,
                status=ExecutionStatus.REJECTED,
                reason=exc.reason,
                result_class=result_class,
                broker_result=broker_result,
                retry_eligible=retryable,
            )

        self.registry.transition(
            request.action_id,
            ExecutionStatus.CHECKED,
            self._now(),
            reason=ExecutionReason.APPROVED,
            attempt_count=attempt_number,
            last_attempt_id=attempt_id,
        )
        self.registry.transition(
            request.action_id,
            ExecutionStatus.SUBMITTING,
            self._now(),
            reason=ExecutionReason.APPROVED,
            attempt_count=attempt_number,
            last_attempt_id=attempt_id,
        )
        try:
            broker_result = self.broker.order_send(final_payload)
        except Exception:
            broker_result = None
        if broker_result is None or getattr(broker_result, "retcode", None) is None:
            self.registry.transition(
                request.action_id,
                ExecutionStatus.UNCERTAIN,
                self._now(),
                reason=ExecutionReason.BROKER_OUTCOME_UNCERTAIN,
                attempt_count=attempt_number,
                last_attempt_id=attempt_id,
            )
            return final_candidate, self._result(
                final_candidate,
                attempt_id,
                status=ExecutionStatus.UNCERTAIN,
                reason=ExecutionReason.BROKER_OUTCOME_UNCERTAIN,
                result_class=ResultClass.UNCERTAIN,
                reconciliation_required=True,
            )

        retcode = int(broker_result.retcode)
        category, reason, retryable = classify_retcode(self.broker, retcode)
        if category in (ResultClass.SUCCESS, ResultClass.PARTIAL_SUCCESS):
            has_ticket = any(
                _integer(getattr(broker_result, name, None)) is not None
                for name in ("order", "deal", "position")
            )
            has_price = _float(getattr(broker_result, "price", None)) is not None
            has_partial_volume = _float(getattr(broker_result, "volume", None)) is not None
            if request.action_type is ExecutionAction.ENTRY and (
                not has_ticket
                or not has_price
                or (category is ResultClass.PARTIAL_SUCCESS and not has_partial_volume)
            ):
                category = ResultClass.UNCERTAIN
                reason = ExecutionReason.BROKER_OUTCOME_UNCERTAIN
                retryable = False
        if category is ResultClass.SUCCESS:
            state = ExecutionStatus.CONFIRMED
        elif category is ResultClass.PARTIAL_SUCCESS:
            state = ExecutionStatus.PARTIALLY_FILLED
        elif category in (ResultClass.UNCERTAIN, ResultClass.CONNECTION_FAILURE):
            state = ExecutionStatus.UNCERTAIN
        else:
            state = ExecutionStatus.REJECTED
        result = self._result(
            final_candidate,
            attempt_id,
            status=state,
            reason=reason,
            result_class=category,
            broker_result=broker_result,
            retry_eligible=retryable,
            reconciliation_required=state in (
                ExecutionStatus.PARTIALLY_FILLED,
                ExecutionStatus.UNCERTAIN,
            ),
        )
        self.registry.transition(
            request.action_id,
            state,
            self._now(),
            reason=reason,
            attempt_count=attempt_number,
            broker_retcode=retcode,
            order_ticket=result.order_ticket,
            deal_ticket=result.deal_ticket,
            position_ticket=result.position_ticket,
            executed_volume=result.executed_volume,
            executed_price=result.executed_price,
            last_attempt_id=attempt_id,
        )
        return final_candidate, result

    def execute(
        self,
        request: ExecutionRequest,
        *,
        risk_recheck: RiskRecheck | None = None,
    ) -> ExecutionResult:
        existing = self.registry.get(request.action_id)
        if existing is not None:
            if existing.state in (
                ExecutionStatus.SUBMITTING,
                ExecutionStatus.UNCERTAIN,
                ExecutionStatus.RECONCILIATION_REQUIRED,
            ):
                return self._result(
                    request,
                    existing.last_attempt_id or stable_execution_id(request.action_id, "existing"),
                    status=ExecutionStatus.UNCERTAIN,
                    reason=ExecutionReason.ACTION_UNCERTAIN,
                    result_class=ResultClass.UNCERTAIN,
                    reconciliation_required=True,
                )
            broker_result = type(
                "PersistedExecution",
                (),
                {
                    "retcode": existing.broker_retcode,
                    "order": existing.order_ticket,
                    "deal": existing.deal_ticket,
                    "position": existing.position_ticket,
                    "volume": existing.executed_volume,
                    "price": existing.executed_price,
                },
            )()
            return self._result(
                request,
                existing.last_attempt_id or stable_execution_id(request.action_id, "existing"),
                status=existing.state,
                reason=ExecutionReason.DUPLICATE_ACTION,
                result_class=(
                    ResultClass.SUCCESS
                    if existing.state is ExecutionStatus.CONFIRMED
                    else ResultClass.PARTIAL_SUCCESS
                    if existing.state is ExecutionStatus.PARTIALLY_FILLED
                    else ResultClass.PERMANENT_REJECTION
                ),
                broker_result=broker_result,
            )
        self.registry.prepare(
            action_id=request.action_id,
            trade_id=request.trade_id,
            symbol=request.symbol,
            action_type=request.action_type,
            now=self._now(),
        )
        candidate = request
        candidate, result = self._attempt(candidate, 1, risk_recheck=risk_recheck)
        if not result.retry_eligible:
            return result

        if result.reason is ExecutionReason.BROKER_INVALID_STOPS:
            if risk_recheck is None:
                return replace(result, retry_eligible=False)
            try:
                snapshot = self.snapshot(candidate.symbol, candidate.direction, candidate.action_type)
                stop, target = corrected_absolute_levels(candidate, snapshot.symbol, snapshot.tick)
                approved = risk_recheck(
                    snapshot.tick.ask if candidate.direction == "buy" else snapshot.tick.bid,
                    stop,
                    candidate.volume,
                )
                if approved is None or approved <= 0:
                    return replace(result, retry_eligible=False)
                candidate = with_reapproved_stop(candidate, stop, target, approved)
            except (ExecutionError, ExecutionRejected):
                return replace(result, retry_eligible=False)
        elif result.reason is ExecutionReason.BROKER_PRICE_CHANGED:
            if risk_recheck is None or candidate.action_type is not ExecutionAction.ENTRY:
                return replace(result, retry_eligible=False)
            try:
                snapshot = self.snapshot(candidate.symbol, candidate.direction, candidate.action_type)
                new_price = snapshot.tick.ask if candidate.direction == "buy" else snapshot.tick.bid
                approved = risk_recheck(new_price, float(candidate.stop_price), candidate.volume)
                if approved is None or approved <= 0 or approved > candidate.approved_volume + 1e-12:
                    return replace(result, retry_eligible=False)
                candidate = replace(
                    candidate,
                    executable_price=new_price,
                    volume=min(candidate.volume, approved),
                    approved_volume=approved,
                    risk_reapproved=True,
                )
            except (ExecutionError, ExecutionRejected):
                return replace(result, retry_eligible=False)
        else:
            return replace(result, retry_eligible=False)

        self.registry.transition(
            candidate.action_id,
            ExecutionStatus.PREPARED,
            self._now(),
            reason=result.reason,
            attempt_count=1,
        )
        _candidate, retry_result = self._attempt(candidate, 2, risk_recheck=risk_recheck)
        return replace(retry_result, retry_eligible=False)

    def owned_positions(self, *, symbol: str | None = None) -> tuple[Any, ...]:
        positions = tuple(self.broker.positions_get(symbol=symbol) or ()) if symbol else tuple(self.broker.positions_get() or ())
        return tuple(position for position in positions if int(getattr(position, "magic", 0) or 0) == self.policy.magic_number)

    def liquidate_owned(
        self,
        positions: Iterable[Any],
        *,
        reason_root: str,
        now: datetime,
    ) -> tuple[ExecutionResult, ...]:
        results: list[ExecutionResult] = []
        for position in positions:
            if int(getattr(position, "magic", 0) or 0) != self.policy.magic_number:
                continue
            comment = str(getattr(position, "comment", "") or "")
            parts = comment.split(":")
            if len(parts) != 3 or parts[0] != "p5":
                continue
            trade_id = parts[1]
            ticket = int(position.ticket)
            action_id = stable_execution_id(reason_root, trade_id, ticket)
            direction = "buy" if int(position.type) == int(self.broker.ORDER_TYPE_BUY) else "sell"
            tick = tick_from_mt5(self.broker.symbol_info_tick(position.symbol))
            price = tick.bid if direction == "buy" else tick.ask
            request = self.position_request(
                action_id=action_id,
                signal_id=trade_id,
                trade_id=trade_id,
                symbol=str(position.symbol),
                direction=direction,
                action_type=ExecutionAction.LIQUIDATE,
                volume=float(position.volume),
                executable_price=price,
                position_ticket=ticket,
                risk_decision_id=reason_root,
                approved_volume=float(position.volume),
                created_at=now,
            )
            results.append(self.execute(request))
        return tuple(results)
