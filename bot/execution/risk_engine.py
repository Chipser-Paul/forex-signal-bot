from __future__ import annotations

from dataclasses import dataclass

import MetaTrader5 as mt5  # pyright: ignore[reportMissingImports]


@dataclass
class RiskEngine:
    max_risk_per_trade: float = 0.01
    max_daily_drawdown: float = 0.03
    max_concurrent_trades: int = 2
    min_rr: float = 3.0

    def calculate_position_size(
        self,
        symbol: str,
        account_balance: float,
        stop_distance_price: float,
        risk_pct: float | None = None,
        enforce_min_volume: bool = True,
        position_size_pct: float = 1.0,  # Phase 2: Displacement tier adjustment
    ) -> float | None:
        if account_balance <= 0 or stop_distance_price <= 0:
            return None

        risk_pct = float(risk_pct if risk_pct is not None else self.max_risk_per_trade)
        if risk_pct <= 0:
            return None

        info = mt5.symbol_info(symbol)
        if info is None:
            return None

        tick_value = float(getattr(info, "trade_tick_value", 0.0) or 0.0)
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or 0.0)
        volume_min = float(getattr(info, "volume_min", 0.0) or 0.0)
        volume_max = float(getattr(info, "volume_max", 0.0) or 0.0)
        volume_step = float(getattr(info, "volume_step", 0.01) or 0.01)

        if tick_value <= 0 or tick_size <= 0 or volume_min <= 0:
            return None

        risk_amount = account_balance * risk_pct * position_size_pct  # Apply tier adjustment
        risk_per_lot = (stop_distance_price / tick_size) * tick_value
        if risk_per_lot <= 0:
            return None

        raw_lot = risk_amount / risk_per_lot
        if enforce_min_volume and raw_lot < volume_min:
            return None
        normalized = round(raw_lot / volume_step) * volume_step
        normalized = max(volume_min, normalized)
        normalized = min(volume_max, normalized)
        return round(normalized, 2)

    def validate_rr(self, entry: float, sl: float, tp: float) -> bool:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk <= 0 or reward <= 0:
            return False
        return (reward / risk) >= self.min_rr

    def rr_value(self, entry: float, sl: float, tp: float) -> float:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk <= 0:
            return 0.0
        return round(reward / risk, 4)

    def check_daily_drawdown(self, daily_pnl: float, account_balance: float) -> bool:
        if account_balance <= 0:
            return False
        return daily_pnl <= -(account_balance * self.max_daily_drawdown)

    def can_open_more_trades(self, active_trade_count: int) -> bool:
        return active_trade_count < self.max_concurrent_trades

    def build_tp_targets(self, direction: str, entry: float, liquidity_pools: list[dict]) -> dict[str, float] | None:
        if direction not in ("buy", "sell") or not liquidity_pools:
            return None

        ahead = []
        for pool in liquidity_pools:
            if not isinstance(pool, dict):
                continue
            if pool.get("price") is None:
                continue
            price = float(pool["price"])
            if direction == "buy" and price > entry:
                ahead.append(price)
            if direction == "sell" and price < entry:
                ahead.append(price)

        if not ahead:
            return None

        ordered = sorted(ahead) if direction == "buy" else sorted(ahead, reverse=True)
        targets = {"tp1": ordered[0]}
        if len(ordered) > 1:
            targets["tp2"] = ordered[1]
        if len(ordered) > 2:
            targets["tp3"] = ordered[2]
        return targets

    def trail_reference_level(self, direction: str, last_h1_swing_high: float | None, last_h1_swing_low: float | None):
        if direction == "buy":
            return last_h1_swing_low
        if direction == "sell":
            return last_h1_swing_high
        return None
