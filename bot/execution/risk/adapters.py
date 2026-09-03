from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from .models import (
    AccountSnapshot,
    OpenRiskItem,
    RiskError,
    SymbolRiskSpecification,
    stable_ref,
    utc_datetime,
)
from .sizing import ProfitCalculator, loss_for_volume


def account_identity_ref(login: object, server: object) -> str:
    if login is None or not str(server or "").strip():
        raise RiskError("account identity is incomplete")
    return stable_ref("mt5-account", str(login), str(server).strip().lower())


def account_snapshot_from_mt5(
    mt5_module: Any,
    *,
    now: datetime,
    expected_login: object | None = None,
    expected_server: object | None = None,
) -> AccountSnapshot:
    account = mt5_module.account_info()
    if account is None:
        raise RiskError("account snapshot is unavailable")
    login = getattr(account, "login", None)
    server = getattr(account, "server", None)
    if expected_login is not None and str(login) != str(expected_login):
        raise RiskError("account identity verification failed")
    if expected_server is not None and str(server).strip().lower() != str(expected_server).strip().lower():
        raise RiskError("account identity verification failed")
    balance = float(getattr(account, "balance", 0.0) or 0.0)
    equity = float(getattr(account, "equity", 0.0) or 0.0)
    floating = getattr(account, "profit", None)
    if floating is None:
        floating = equity - balance
    return AccountSnapshot(
        account_ref=account_identity_ref(login, server),
        balance=balance,
        equity=equity,
        floating_pnl=float(floating),
        margin=float(getattr(account, "margin", 0.0) or 0.0),
        free_margin=float(getattr(account, "margin_free", getattr(account, "free_margin", 0.0)) or 0.0),
        currency=str(getattr(account, "currency", "") or "UNKNOWN"),
        timestamp=utc_datetime(now, "account observation time"),
        source="live_mt5",
    )


def symbol_specification_from_mt5(mt5_module: Any, symbol: str) -> SymbolRiskSpecification:
    info = mt5_module.symbol_info(symbol)
    if info is None:
        raise RiskError("symbol risk metadata is unavailable")
    return SymbolRiskSpecification(
        symbol=symbol,
        tick_size=float(getattr(info, "trade_tick_size", 0.0) or 0.0),
        tick_value=float(getattr(info, "trade_tick_value", 0.0) or 0.0),
        volume_min=float(getattr(info, "volume_min", 0.0) or 0.0),
        volume_max=float(getattr(info, "volume_max", 0.0) or 0.0),
        volume_step=float(getattr(info, "volume_step", 0.0) or 0.0),
        price_precision=int(getattr(info, "digits", 0) or 0),
        contract_size=float(getattr(info, "trade_contract_size", 0.0) or 0.0) or None,
    )


def mt5_profit_calculator(mt5_module: Any) -> ProfitCalculator:
    def calculate(direction: str, symbol: str, volume: float, entry: float, stop: float):
        method = getattr(mt5_module, "order_calc_profit", None)
        if method is None:
            return None
        order_type = mt5_module.ORDER_TYPE_BUY if direction == "buy" else mt5_module.ORDER_TYPE_SELL
        return method(order_type, symbol, volume, entry, stop)

    return calculate


def open_risk_items_from_mt5(
    mt5_module: Any,
    *,
    positions: Iterable[Any],
    tracked_trades: Mapping[int, Mapping[str, Any]],
) -> tuple[OpenRiskItem, ...]:
    items = []
    calculator = mt5_profit_calculator(mt5_module)
    for position in positions:
        ticket = int(getattr(position, "ticket"))
        symbol = str(getattr(position, "symbol"))
        direction = "buy" if int(getattr(position, "type")) == int(mt5_module.ORDER_TYPE_BUY) else "sell"
        volume = float(getattr(position, "volume", 0.0) or 0.0)
        stop = float(getattr(position, "sl", 0.0) or 0.0) or None
        tracked = tracked_trades.get(ticket)
        tick = mt5_module.symbol_info_tick(symbol)
        reference = float(
            getattr(tick, "bid" if direction == "buy" else "ask", 0.0) or 0.0
        )
        entry = None if tracked is None else float(tracked.get("entry_price", tracked.get("fill_price", 0.0)) or 0.0)
        basis = entry if entry and entry > 0 else reference
        estimated = None
        method = "missing_stop"
        if stop is not None and reference > 0 and basis > 0:
            locked_profit = (direction == "buy" and stop >= basis) or (direction == "sell" and stop <= basis)
            wrong_side_market = (direction == "buy" and stop >= reference) or (direction == "sell" and stop <= reference)
            if locked_profit and not wrong_side_market:
                estimated = 0.0
                method = "locked_profit_floor"
            elif not wrong_side_market:
                try:
                    specification = symbol_specification_from_mt5(mt5_module, symbol)
                    estimated, method = loss_for_volume(
                        direction,
                        specification,
                        basis,
                        stop,
                        volume,
                        profit_calculator=calculator,
                    )
                except (RiskError, ValueError, TypeError):
                    estimated = None
                    method = "loss_calculation_failed"
        items.append(
            OpenRiskItem(
                trade_id=str((tracked or {}).get("trade_id") or f"broker:{stable_ref(ticket)}"),
                symbol=symbol,
                direction=direction,
                remaining_volume=volume,
                current_reference_price=reference,
                current_stop=stop,
                estimated_loss=estimated,
                ownership="strategy" if tracked is not None else "manual_or_unknown",
                calculation_method=method,
                entry_price=entry,
            )
        )
    return tuple(items)
