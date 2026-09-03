from __future__ import annotations

from dataclasses import dataclass

import MetaTrader5 as mt5  # pyright: ignore[reportMissingImports]

from bot.execution.risk import RiskError, SymbolRiskSpecification, loss_for_volume, normalize_volume_down


VALIDATION_ABSOLUTE_RISK_CEILING = 0.005


@dataclass
class RiskEngine:
    """Compatibility facade; executable approvals belong to the Phase 4 authority."""

    max_risk_per_trade: float = 0.005
    base_risk_per_trade: float = 0.0035
    max_daily_drawdown: float = 0.02
    max_concurrent_trades: int = 2
    min_rr: float = 3.0

    def __post_init__(self) -> None:
        if not 0 < self.max_risk_per_trade <= VALIDATION_ABSOLUTE_RISK_CEILING:
            raise RiskError("compatibility risk ceiling cannot exceed 0.005")
        if not 0 < self.base_risk_per_trade <= self.max_risk_per_trade:
            raise RiskError("compatibility base risk must remain within the ceiling")

    def calculate_position_size(
        self,
        symbol: str,
        account_balance: float,
        stop_distance_price: float,
        risk_pct: float | None = None,
        enforce_min_volume: bool = True,
        position_size_pct: float = 1.0,
    ) -> float | None:
        requested = self.base_risk_per_trade if risk_pct is None else float(risk_pct)
        if (
            account_balance <= 0
            or stop_distance_price <= 0
            or requested <= 0
            or requested > self.max_risk_per_trade
            or position_size_pct <= 0
            or position_size_pct > 1
        ):
            return None
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        try:
            specification = SymbolRiskSpecification(
                symbol=symbol,
                tick_size=float(getattr(info, "trade_tick_size", 0.0) or 0.0),
                tick_value=float(getattr(info, "trade_tick_value", 0.0) or 0.0),
                volume_min=float(getattr(info, "volume_min", 0.0) or 0.0),
                volume_max=float(getattr(info, "volume_max", 0.0) or 0.0),
                volume_step=float(getattr(info, "volume_step", 0.0) or 0.0),
                price_precision=int(getattr(info, "digits", 0) or 0),
                contract_size=float(getattr(info, "trade_contract_size", 0.0) or 0.0) or None,
            )
            one_lot_loss, _ = loss_for_volume(
                "buy", specification, stop_distance_price, 0.0, 1.0
            )
            raw = account_balance * requested * position_size_pct / one_lot_loss
            if enforce_min_volume and raw < specification.volume_min:
                return None
            normalized = normalize_volume_down(raw, specification)
            if normalized < specification.volume_min or normalized <= 0:
                return None
            normalized_loss, _ = loss_for_volume(
                "buy", specification, stop_distance_price, 0.0, normalized
            )
            budget = account_balance * requested * position_size_pct
            return normalized if normalized_loss <= budget + 1e-9 else None
        except (TypeError, ValueError):
            return None

    def validate_rr(self, entry: float, sl: float, tp: float) -> bool:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        return risk > 0 and reward > 0 and (reward / risk) >= self.min_rr

    def rr_value(self, entry: float, sl: float, tp: float) -> float:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        return round(reward / risk, 4) if risk > 0 else 0.0

    def check_daily_drawdown(self, daily_pnl: float, account_balance: float) -> bool:
        if account_balance <= 0:
            return True
        return daily_pnl <= -(account_balance * self.max_daily_drawdown)

    def can_open_more_trades(self, active_trade_count: int) -> bool:
        return active_trade_count < self.max_concurrent_trades

    def build_tp_targets(self, direction: str, entry: float, liquidity_pools: list[dict]) -> dict[str, float] | None:
        if direction not in ("buy", "sell") or not liquidity_pools:
            return None
        ahead = []
        for pool in liquidity_pools:
            if not isinstance(pool, dict) or pool.get("price") is None:
                continue
            price = float(pool["price"])
            if (direction == "buy" and price > entry) or (direction == "sell" and price < entry):
                ahead.append(price)
        if not ahead:
            return None
        ordered = sorted(ahead, reverse=direction == "sell")
        return {f"tp{index + 1}": price for index, price in enumerate(ordered[:3])}

    def trail_reference_level(self, direction: str, last_h1_swing_high: float | None, last_h1_swing_low: float | None):
        if direction == "buy":
            return last_h1_swing_low
        if direction == "sell":
            return last_h1_swing_high
        return None
