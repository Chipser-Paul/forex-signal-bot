from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Iterable

from bot.execution.risk.models import AccountSnapshot, OpenRiskItem

from .costs import adverse_fill_price, commission_for_fill, rollover_instants, swap_for_rollover
from .models import (
    BidAskBar,
    BrokerSymbolMetadata,
    CostSource,
    HistoricalAccountState,
    HistoricalExecutionError,
    HistoricalExecutionPolicy,
    HistoricalPosition,
    HistoricalQuote,
    LedgerEntry,
    LedgerEventType,
    Side,
    SimulatedFill,
    stable_id,
    utc_datetime,
)


class HistoricalExecutionEngine:
    """Pure deterministic quote-side execution and account ledger for XAUUSDm."""

    def __init__(
        self,
        *,
        run_id: str,
        metadata: BrokerSymbolMetadata,
        policy: HistoricalExecutionPolicy,
        initial_balance: float,
    ) -> None:
        if not run_id:
            raise HistoricalExecutionError("run identity is required")
        self.run_id = run_id
        self.metadata = metadata
        self.policy = policy
        if policy.mode.value == "VALIDATION":
            if metadata.commission.source is not CostSource.OBSERVED:
                raise HistoricalExecutionError("validation requires observed commission provenance")
            if metadata.swap.source is not CostSource.OBSERVED:
                raise HistoricalExecutionError("validation requires observed swap provenance")
        self.account = HistoricalAccountState(
            initial_balance=float(initial_balance),
            balance=float(initial_balance),
            equity=float(initial_balance),
        )
        self.positions: dict[str, HistoricalPosition] = {}
        self.fills: list[SimulatedFill] = []
        self.ledger: list[LedgerEntry] = []
        self.rejections: list[dict[str, object]] = []
        self.diagnostics: list[dict[str, object]] = []
        self.equity_curve: list[dict[str, object]] = []
        self.processed_action_ids: set[str] = set()
        self.action_fingerprints: dict[str, str] = {}
        self.last_event_time: datetime | None = None

    def _reject(self, action_id: str, timestamp: datetime, reason: str) -> None:
        self.rejections.append(
            {
                "action_id": action_id,
                "timestamp": utc_datetime(timestamp, "rejection timestamp").isoformat(),
                "reason_code": reason,
            }
        )
        raise HistoricalExecutionError(reason)

    def _validate_event(self, timestamp: datetime, action_id: str) -> datetime:
        instant = utc_datetime(timestamp, "historical event timestamp")
        if self.last_event_time is not None and instant < self.last_event_time:
            self._reject(action_id, instant, "EVENT_TIME_MOVED_BACKWARD")
        if not self.metadata.applies_at(instant):
            self._reject(action_id, instant, "METADATA_NOT_EFFECTIVE")
        return instant

    def _normalize_volume(self, requested: float) -> float:
        value = Decimal(str(requested))
        step = Decimal(str(self.metadata.volume_step))
        units = (value / step).to_integral_value(rounding=ROUND_FLOOR)
        normalized = units * step
        minimum = Decimal(str(self.metadata.volume_min))
        maximum = Decimal(str(self.metadata.volume_max))
        if normalized < minimum:
            raise HistoricalExecutionError("VOLUME_BELOW_MINIMUM")
        if normalized > maximum:
            normalized = (maximum / step).to_integral_value(rounding=ROUND_FLOOR) * step
        if normalized <= 0 or normalized > value:
            raise HistoricalExecutionError("VOLUME_NORMALIZATION_FAILED")
        return float(normalized)

    def _normalize_price(self, price: float, transaction_side: Side) -> float:
        value = Decimal(str(price))
        tick = Decimal(str(self.metadata.tick_size))
        rounding = ROUND_CEILING if transaction_side is Side.BUY else ROUND_FLOOR
        units = (value / tick).to_integral_value(rounding=rounding)
        return float(units * tick)

    def _spread_check(self, quote: HistoricalQuote, stop_price: float, transaction_side: Side) -> None:
        spread_points = quote.spread_price / self.metadata.point_size
        if spread_points > self.policy.maximum_spread_points + 1e-9:
            self._reject(quote.sequence_id, quote.timestamp, "SPREAD_ABSOLUTE_LIMIT")
        executable = quote.ask if transaction_side is Side.BUY else quote.bid
        stop_distance = abs(executable - stop_price)
        if stop_distance <= 0:
            self._reject(quote.sequence_id, quote.timestamp, "INVALID_STOP_DISTANCE")
        if quote.spread_price / stop_distance > self.policy.maximum_spread_to_stop_fraction + 1e-12:
            self._reject(quote.sequence_id, quote.timestamp, "SPREAD_RELATIVE_LIMIT")

    def _validate_levels(self, direction: Side, entry: float, stop: float, target: float) -> None:
        values = (entry, stop, target)
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise HistoricalExecutionError("INVALID_PRICE_LEVEL")
        if direction is Side.BUY and not stop < entry < target:
            raise HistoricalExecutionError("INVALID_BUY_LEVELS")
        if direction is Side.SELL and not target < entry < stop:
            raise HistoricalExecutionError("INVALID_SELL_LEVELS")

    def _margin_required(self, price: float, volume: float) -> float:
        return price * self.metadata.contract_size * volume * self.metadata.margin_rate

    def _price_value(self, price_distance: float, volume: float) -> float:
        return (
            price_distance
            / self.metadata.tick_size
            * self.metadata.tick_value
            * volume
        )

    def _margin_check(self, required: float, action_id: str, timestamp: datetime) -> None:
        if not math.isfinite(required) or required < 0:
            self._reject(action_id, timestamp, "MARGIN_CALCULATION_INVALID")
        if required > self.account.equity * self.policy.maximum_new_order_margin_fraction + 1e-9:
            self._reject(action_id, timestamp, "NEW_ORDER_MARGIN_LIMIT")
        projected = self.account.used_margin + required
        projected_free = self.account.equity - projected
        level = math.inf if projected == 0 else self.account.equity / projected * 100.0
        if projected_free <= 0:
            self._reject(action_id, timestamp, "PROJECTED_FREE_MARGIN_NONPOSITIVE")
        if level < self.policy.minimum_projected_margin_level_percent - 1e-9:
            self._reject(action_id, timestamp, "PROJECTED_MARGIN_LEVEL_LOW")

    def _append_ledger(
        self,
        *,
        action_id: str,
        timestamp: datetime,
        event_type: LedgerEventType,
        trade_id: str | None,
        position_id: str | None,
        side: Side | None,
        volume: float,
        reference_price: float | None = None,
        executable_quote: float | None = None,
        fill_price: float | None = None,
        gross_price_pnl: float = 0.0,
        spread_attribution: float = 0.0,
        slippage_attribution: float = 0.0,
        commission: float = 0.0,
        swap: float = 0.0,
        net_cash_change: float = 0.0,
    ) -> LedgerEntry:
        self.account.balance += net_cash_change
        self.account.realized_gross_pnl += gross_price_pnl
        self.account.commission += commission
        self.account.swap += swap
        self.account.equity += net_cash_change
        self.account.free_margin = self.account.equity - self.account.used_margin
        self.account.high_water_equity = max(self.account.high_water_equity, self.account.equity)
        entry = LedgerEntry(
            ledger_id=stable_id(self.run_id, action_id, event_type.value, len(self.ledger)),
            run_id=self.run_id,
            trade_id=trade_id,
            position_id=position_id,
            action_id=action_id,
            timestamp=timestamp,
            event_type=event_type,
            symbol=self.metadata.symbol,
            side=side,
            volume=volume,
            reference_price=reference_price,
            executable_quote=executable_quote,
            fill_price=fill_price,
            gross_price_pnl=gross_price_pnl,
            spread_attribution=spread_attribution,
            slippage_attribution=slippage_attribution,
            commission=commission,
            swap=swap,
            net_cash_change=net_cash_change,
            balance_after=self.account.balance,
            equity_after=self.account.equity,
            provenance=self.metadata.provenance,
            fidelity=self.policy.fidelity,
        )
        self.ledger.append(entry)
        return entry

    def _commission_entry(
        self,
        *,
        action_id: str,
        timestamp: datetime,
        trade_id: str,
        position_id: str,
        side: Side,
        volume: float,
        fill_price: float,
    ) -> float:
        commission = commission_for_fill(self.metadata, volume=volume, fill_price=fill_price)
        if commission:
            self._append_ledger(
                action_id=f"{action_id}:commission",
                timestamp=timestamp,
                event_type=LedgerEventType.COMMISSION,
                trade_id=trade_id,
                position_id=position_id,
                side=side,
                volume=volume,
                fill_price=fill_price,
                commission=commission,
                net_cash_change=-commission,
            )
        return commission

    def open_market(
        self,
        *,
        action_id: str,
        trade_id: str,
        direction: Side,
        requested_volume: float,
        stop_price: float,
        target_price: float,
        quote: HistoricalQuote,
        signal_available_at: datetime,
        source_event_id: str,
        market_event_id: str,
        available_volume: float | None = None,
    ) -> tuple[HistoricalPosition, SimulatedFill]:
        fingerprint = stable_id(
            "open", trade_id, direction.value, requested_volume, stop_price,
            target_price, quote.timestamp.isoformat(), quote.sequence_id,
            signal_available_at, source_event_id, market_event_id, available_volume,
        )
        if action_id in self.processed_action_ids:
            if self.action_fingerprints.get(action_id) != fingerprint:
                self._reject(action_id, quote.timestamp, "ACTION_ID_CONFLICT")
            fill = next(item for item in self.fills if item.action_id == action_id)
            return self.positions[fill.position_id], fill
        instant = self._validate_event(quote.timestamp, action_id)
        signal_time = utc_datetime(signal_available_at, "signal availability")
        if instant < signal_time or source_event_id == market_event_id:
            self._reject(action_id, instant, "SOURCE_CANDLE_ENTRY_FORBIDDEN")
        transaction_side = direction
        reference = quote.ask if direction is Side.BUY else quote.bid
        self._validate_levels(direction, reference, stop_price, target_price)
        self._spread_check(quote, stop_price, transaction_side)
        volume = self._normalize_volume(requested_volume)
        partial = False
        if available_volume is not None and available_volume < volume:
            volume = self._normalize_volume(available_volume)
            partial = True
        raw_fill, slippage_price = adverse_fill_price(
            reference,
            transaction_side,
            self.policy.slippage,
            self.metadata,
            seed=self.policy.random_seed,
            action_id=action_id,
        )
        if slippage_price / self.metadata.point_size > self.policy.maximum_deviation_points + 1e-12:
            self._reject(action_id, instant, "DEVIATION_LIMIT")
        fill_price = self._normalize_price(raw_fill, transaction_side)
        self._validate_levels(direction, fill_price, stop_price, target_price)
        margin = self._margin_required(fill_price, volume)
        self._margin_check(margin, action_id, instant)
        position_id = stable_id(self.run_id, trade_id, action_id, "position")
        fill = SimulatedFill(
            fill_id=stable_id(self.run_id, action_id, "fill"),
            action_id=action_id,
            trade_id=trade_id,
            position_id=position_id,
            timestamp=instant,
            symbol=self.metadata.symbol,
            side=transaction_side,
            volume=volume,
            reference_price=reference,
            executable_quote=reference,
            fill_price=fill_price,
            slippage_price=abs(fill_price - reference),
            spread_price=quote.spread_price,
            partial=partial,
            reason_code="PARTIAL_ENTRY_FILL" if partial else "ENTRY_FILL",
            fidelity=self.policy.fidelity,
        )
        position = HistoricalPosition(
            position_id=position_id,
            trade_id=trade_id,
            symbol=self.metadata.symbol,
            direction=direction,
            opened_at=instant,
            entry_price=fill_price,
            initial_volume=volume,
            remaining_volume=volume,
            stop_price=stop_price,
            target_price=target_price,
            last_swap_at=instant,
        )
        self.positions[position_id] = position
        self.fills.append(fill)
        self.account.used_margin += margin
        spread_attribution = self._price_value(quote.spread_price, volume) / 2.0
        self._append_ledger(
            action_id=action_id,
            timestamp=instant,
            event_type=LedgerEventType.ENTRY_FILL,
            trade_id=trade_id,
            position_id=position_id,
            side=transaction_side,
            volume=volume,
            reference_price=(quote.bid + quote.ask) / 2.0,
            executable_quote=reference,
            fill_price=fill_price,
            spread_attribution=spread_attribution,
            slippage_attribution=self._price_value(abs(fill_price - reference), volume),
        )
        self._commission_entry(
            action_id=action_id,
            timestamp=instant,
            trade_id=trade_id,
            position_id=position_id,
            side=transaction_side,
            volume=volume,
            fill_price=fill_price,
        )
        self.processed_action_ids.add(action_id)
        self.action_fingerprints[action_id] = fingerprint
        self.last_event_time = instant
        self.mark_to_market(quote)
        return position, fill

    def apply_swap_until(self, position_id: str, timestamp: datetime) -> tuple[LedgerEntry, ...]:
        position = self.positions[position_id]
        instant = utc_datetime(timestamp, "swap target timestamp")
        if position.remaining_volume <= 0:
            self.positions[position_id] = replace(position, last_swap_at=instant)
            return ()
        entries: list[LedgerEntry] = []
        for rollover in rollover_instants(position.last_swap_at, instant, self.metadata):
            action_id = stable_id(position.position_id, rollover.isoformat(), "swap")
            if action_id in self.processed_action_ids:
                continue
            amount, multiplier = swap_for_rollover(
                self.metadata,
                direction=position.direction,
                volume=position.remaining_volume,
                rollover=rollover,
            )
            entry = self._append_ledger(
                action_id=action_id,
                timestamp=rollover,
                event_type=LedgerEventType.SWAP,
                trade_id=position.trade_id,
                position_id=position.position_id,
                side=position.direction,
                volume=position.remaining_volume,
                swap=amount,
                net_cash_change=amount,
            )
            entries.append(entry)
            self.processed_action_ids.add(action_id)
            self.diagnostics.append({
                "action_id": action_id,
                "timestamp": rollover.isoformat(),
                "reason_code": f"SWAP_MULTIPLIER_{multiplier}",
                "diagnostic_only": True,
            })
        self.positions[position_id] = replace(position, last_swap_at=instant)
        return tuple(entries)

    def close_market(
        self,
        *,
        action_id: str,
        position_id: str,
        quote: HistoricalQuote,
        requested_volume: float | None = None,
        reason_code: str,
        reference_override: float | None = None,
        limit_fill: bool = False,
    ) -> SimulatedFill:
        fingerprint = stable_id(
            "close", position_id, requested_volume, reason_code,
            reference_override, limit_fill, quote.timestamp.isoformat(), quote.sequence_id,
        )
        if action_id in self.processed_action_ids:
            if self.action_fingerprints.get(action_id) != fingerprint:
                self._reject(action_id, quote.timestamp, "ACTION_ID_CONFLICT")
            return next(item for item in self.fills if item.action_id == action_id)
        instant = self._validate_event(quote.timestamp, action_id)
        if position_id not in self.positions:
            self._reject(action_id, instant, "POSITION_NOT_FOUND")
        self.apply_swap_until(position_id, instant)
        position = self.positions[position_id]
        if position.remaining_volume <= 0:
            self._reject(action_id, instant, "POSITION_ALREADY_CLOSED")
        requested = position.remaining_volume if requested_volume is None else requested_volume
        if requested > position.remaining_volume + 1e-12:
            self._reject(action_id, instant, "CLOSE_EXCEEDS_REMAINING_VOLUME")
        volume = self._normalize_volume(requested)
        transaction_side = Side.SELL if position.direction is Side.BUY else Side.BUY
        quote_side = quote.bid if transaction_side is Side.SELL else quote.ask
        reference = quote_side if reference_override is None else float(reference_override)
        if limit_fill:
            fill_price, slippage_price = self._normalize_price(reference, transaction_side), 0.0
        else:
            raw_fill, slippage_price = adverse_fill_price(
                reference,
                transaction_side,
                self.policy.slippage,
                self.metadata,
                seed=self.policy.random_seed,
                action_id=action_id,
            )
            if slippage_price / self.metadata.point_size > self.policy.maximum_deviation_points + 1e-12:
                self._reject(action_id, instant, "DEVIATION_LIMIT")
            fill_price = self._normalize_price(raw_fill, transaction_side)
        gross = self._price_value(
            position.direction.sign * (fill_price - position.entry_price), volume
        )
        margin_release = self._margin_required(position.entry_price, volume)
        self.account.used_margin = max(0.0, self.account.used_margin - margin_release)
        self._append_ledger(
            action_id=action_id,
            timestamp=instant,
            event_type=LedgerEventType.EXIT_PNL,
            trade_id=position.trade_id,
            position_id=position.position_id,
            side=transaction_side,
            volume=volume,
            reference_price=reference,
            executable_quote=quote_side,
            fill_price=fill_price,
            gross_price_pnl=gross,
            spread_attribution=self._price_value(quote.spread_price, volume) / 2.0,
            slippage_attribution=self._price_value(abs(fill_price - reference), volume),
            net_cash_change=gross,
        )
        self._commission_entry(
            action_id=action_id,
            timestamp=instant,
            trade_id=position.trade_id,
            position_id=position.position_id,
            side=transaction_side,
            volume=volume,
            fill_price=fill_price,
        )
        remaining = max(0.0, position.remaining_volume - volume)
        self.positions[position_id] = replace(
            position,
            remaining_volume=remaining,
            closed_at=instant if remaining <= 1e-12 else None,
            last_swap_at=instant,
        )
        fill = SimulatedFill(
            fill_id=stable_id(self.run_id, action_id, "fill"),
            action_id=action_id,
            trade_id=position.trade_id,
            position_id=position.position_id,
            timestamp=instant,
            symbol=position.symbol,
            side=transaction_side,
            volume=volume,
            reference_price=reference,
            executable_quote=quote_side,
            fill_price=fill_price,
            slippage_price=abs(fill_price - reference),
            spread_price=quote.spread_price,
            partial=remaining > 1e-12,
            reason_code=reason_code,
            fidelity=self.policy.fidelity,
        )
        self.fills.append(fill)
        self.processed_action_ids.add(action_id)
        self.action_fingerprints[action_id] = fingerprint
        self.last_event_time = instant
        self.mark_to_market(quote)
        return fill

    def evaluate_quote(self, position_id: str, quote: HistoricalQuote) -> SimulatedFill | None:
        position = self.positions[position_id]
        closing_price = quote.bid if position.direction is Side.BUY else quote.ask
        if (position.direction is Side.BUY and closing_price <= position.stop_price) or (
            position.direction is Side.SELL and closing_price >= position.stop_price
        ):
            return self.close_market(
                action_id=stable_id(position_id, quote.sequence_id, "stop"),
                position_id=position_id,
                quote=quote,
                reason_code="STOP_TRIGGER",
            )
        if (position.direction is Side.BUY and closing_price >= position.target_price) or (
            position.direction is Side.SELL and closing_price <= position.target_price
        ):
            return self.close_market(
                action_id=stable_id(position_id, quote.sequence_id, "target"),
                position_id=position_id,
                quote=quote,
                reason_code="TAKE_PROFIT_LIMIT",
                reference_override=position.target_price,
                limit_fill=True,
            )
        self.apply_swap_until(position_id, quote.timestamp)
        self.mark_to_market(quote)
        self.last_event_time = quote.timestamp
        return None

    def evaluate_bar(self, position_id: str, bar: BidAskBar) -> SimulatedFill | None:
        position = self.positions[position_id]
        if position.direction is Side.BUY:
            open_price, high, low = bar.bid_open, bar.bid_high, bar.bid_low
            stop_hit, target_hit = low <= position.stop_price, high >= position.target_price
            gap_stop = open_price <= position.stop_price
        else:
            open_price, high, low = bar.ask_open, bar.ask_high, bar.ask_low
            stop_hit, target_hit = high >= position.stop_price, low <= position.target_price
            gap_stop = open_price >= position.stop_price
        quote = HistoricalQuote(
            symbol=bar.symbol,
            timestamp=bar.available_at,
            bid=bar.bid_close,
            ask=bar.ask_close,
            source=bar.source,
            dataset_id=bar.dataset_id,
            sequence_id=bar.sequence_id,
        )
        if stop_hit:
            reference = open_price if gap_stop else position.stop_price
            reason = "AMBIGUOUS_BAR_STOP_FIRST" if target_hit else ("STOP_GAP" if gap_stop else "STOP_TRIGGER")
            return self.close_market(
                action_id=stable_id(position_id, bar.sequence_id, "bar-stop"),
                position_id=position_id,
                quote=quote,
                reason_code=reason,
                reference_override=reference,
            )
        if target_hit:
            return self.close_market(
                action_id=stable_id(position_id, bar.sequence_id, "bar-target"),
                position_id=position_id,
                quote=quote,
                reason_code="TAKE_PROFIT_LIMIT",
                reference_override=position.target_price,
                limit_fill=True,
            )
        self.apply_swap_until(position_id, bar.available_at)
        self.mark_to_market(quote)
        self.last_event_time = bar.available_at
        return None

    def mark_to_market(self, quote: HistoricalQuote) -> float:
        self._validate_event(quote.timestamp, quote.sequence_id)
        unrealized = 0.0
        for position in self.positions.values():
            if position.remaining_volume <= 0:
                continue
            executable = quote.bid if position.direction is Side.BUY else quote.ask
            unrealized += self._price_value(
                position.direction.sign * (executable - position.entry_price),
                position.remaining_volume,
            )
        self.account.unrealized_pnl = unrealized
        self.account.equity = self.account.balance + unrealized
        self.account.free_margin = self.account.equity - self.account.used_margin
        self.account.high_water_equity = max(self.account.high_water_equity, self.account.equity)
        self.last_event_time = quote.timestamp
        self.equity_curve.append({
            "timestamp": quote.timestamp.isoformat(),
            "balance": self.account.balance,
            "equity": self.account.equity,
            "used_margin": self.account.used_margin,
            "free_margin": self.account.free_margin,
            "unrealized_pnl": self.account.unrealized_pnl,
        })
        return unrealized

    def risk_account_snapshot(self, timestamp: datetime) -> AccountSnapshot:
        instant = utc_datetime(timestamp, "risk snapshot timestamp")
        return AccountSnapshot(
            account_ref=stable_id(self.run_id, "historical-account"),
            balance=self.account.balance,
            equity=self.account.equity,
            floating_pnl=self.account.unrealized_pnl,
            margin=self.account.used_margin,
            free_margin=self.account.free_margin,
            currency=self.metadata.account_currency,
            timestamp=instant,
            source="phase7_historical_execution",
        )

    def open_risk_items(self, quote: HistoricalQuote) -> tuple[OpenRiskItem, ...]:
        items: list[OpenRiskItem] = []
        for position in self.positions.values():
            if position.remaining_volume <= 0:
                continue
            executable = quote.bid if position.direction is Side.BUY else quote.ask
            distance = max(0.0, position.direction.sign * (position.entry_price - position.stop_price))
            items.append(OpenRiskItem(
                trade_id=position.trade_id,
                symbol=position.symbol,
                direction=position.direction.value.lower(),
                remaining_volume=position.remaining_volume,
                current_reference_price=executable,
                current_stop=position.stop_price,
                estimated_loss=self._price_value(distance, position.remaining_volume),
                ownership="strategy",
                calculation_method="phase7_metadata_contract",
                entry_price=position.entry_price,
            ))
        return tuple(items)

    def reconcile(self, tolerance: float = 1e-8) -> dict[str, float]:
        cash_changes = sum(entry.net_cash_change for entry in self.ledger)
        expected_balance = self.account.initial_balance + cash_changes
        difference = self.account.balance - expected_balance
        if abs(difference) > tolerance:
            raise HistoricalExecutionError("ledger does not reconcile with account balance")
        gross = sum(entry.gross_price_pnl for entry in self.ledger)
        commissions = sum(entry.commission for entry in self.ledger)
        swaps = sum(entry.swap for entry in self.ledger)
        if abs(gross - self.account.realized_gross_pnl) > tolerance:
            raise HistoricalExecutionError("gross P&L does not reconcile")
        return {
            "cash_changes": cash_changes,
            "balance": self.account.balance,
            "difference": difference,
            "gross_pnl": gross,
            "commission": commissions,
            "swap": swaps,
        }

    def normalized_state(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "balance": round(self.account.balance, 10),
            "equity": round(self.account.equity, 10),
            "fills": [fill.__dict__ for fill in self.fills],
            "ledger": [entry.__dict__ for entry in self.ledger],
            "rejections": list(self.rejections),
        }

    def process_quotes(self, quotes: Iterable[HistoricalQuote]) -> None:
        for quote in quotes:
            for position_id, position in sorted(self.positions.items()):
                if position.remaining_volume > 0:
                    self.evaluate_quote(position_id, quote)
