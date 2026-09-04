from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import time, timedelta
from types import MappingProxyType
from typing import Mapping

from .models import StrategyError


PRODUCTION_EXECUTABLE_SYMBOLS = frozenset({"XAUUSDm"})
DEFAULT_DXY_SYMBOLS = MappingProxyType(
    {
        "EURUSD": "EURUSDm",
        "USDJPY": "USDJPYm",
        "GBPUSD": "GBPUSDm",
        "USDCAD": "USDCADm",
        "USDSEK": "USDSEKm",
        "USDCHF": "USDCHFm",
    }
)


@dataclass(frozen=True)
class StrategyConfig:
    version: str = "phase6-strategy-v1"
    executable_symbols: frozenset[str] = PRODUCTION_EXECUTABLE_SYMBOLS
    dxy_symbol_map: Mapping[str, str] = field(default_factory=lambda: DEFAULT_DXY_SYMBOLS)
    dxy_lookback_bars: int = 20
    dxy_slope_threshold_fraction_per_bar: float = 0.0001
    dxy_max_staleness: timedelta = timedelta(hours=1)
    atr_period_bars: int = 14
    regime_baseline_bars: int = 20
    regime_trend_lookback_bars: int = 20
    high_volatility_ratio: float = 1.5
    trend_strength_atr: float = 0.9
    order_block_displacement_atr: float = 1.5
    order_block_expiry_bars: int = 30
    news_block_before: timedelta = timedelta(minutes=30)
    news_block_after: timedelta = timedelta(minutes=30)
    news_max_age: timedelta = timedelta(minutes=60)
    rollover_start_utc: time = time(21, 55)
    rollover_end_utc: time = time(22, 10)
    confluence_threshold: int = 8

    def __post_init__(self) -> None:
        if self.executable_symbols != PRODUCTION_EXECUTABLE_SYMBOLS:
            raise StrategyError("production executable symbols must be exactly XAUUSDm")
        if set(self.dxy_symbol_map) != set(DEFAULT_DXY_SYMBOLS):
            raise StrategyError("all six DXY constituent mappings are required")
        if any(not key or not value for key, value in self.dxy_symbol_map.items()):
            raise StrategyError("DXY symbol mappings cannot be empty")
        integer_fields = (
            self.dxy_lookback_bars,
            self.atr_period_bars,
            self.regime_baseline_bars,
            self.regime_trend_lookback_bars,
            self.order_block_expiry_bars,
            self.confluence_threshold,
        )
        if any(value <= 0 for value in integer_fields):
            raise StrategyError("strategy periods and thresholds must be positive")
        numeric_fields = (
            self.dxy_slope_threshold_fraction_per_bar,
            self.high_volatility_ratio,
            self.trend_strength_atr,
            self.order_block_displacement_atr,
        )
        if any(not math.isfinite(value) or value <= 0 for value in numeric_fields):
            raise StrategyError("strategy numeric thresholds must be positive and finite")
        durations = (
            self.dxy_max_staleness,
            self.news_block_before,
            self.news_block_after,
            self.news_max_age,
        )
        if any(value.total_seconds() <= 0 for value in durations):
            raise StrategyError("strategy durations must be positive")
        object.__setattr__(self, "dxy_symbol_map", MappingProxyType(dict(self.dxy_symbol_map)))

    def fingerprint(self) -> str:
        payload = {
            "version": self.version,
            "executable_symbols": sorted(self.executable_symbols),
            "dxy_symbol_map": dict(sorted(self.dxy_symbol_map.items())),
            "dxy_lookback_bars": self.dxy_lookback_bars,
            "dxy_slope_threshold_fraction_per_bar": self.dxy_slope_threshold_fraction_per_bar,
            "dxy_max_staleness_seconds": self.dxy_max_staleness.total_seconds(),
            "atr_period_bars": self.atr_period_bars,
            "regime_baseline_bars": self.regime_baseline_bars,
            "regime_trend_lookback_bars": self.regime_trend_lookback_bars,
            "high_volatility_ratio": self.high_volatility_ratio,
            "trend_strength_atr": self.trend_strength_atr,
            "order_block_displacement_atr": self.order_block_displacement_atr,
            "order_block_expiry_bars": self.order_block_expiry_bars,
            "news_block_before_seconds": self.news_block_before.total_seconds(),
            "news_block_after_seconds": self.news_block_after.total_seconds(),
            "news_max_age_seconds": self.news_max_age.total_seconds(),
            "rollover_start_utc": self.rollover_start_utc.isoformat(),
            "rollover_end_utc": self.rollover_end_utc.isoformat(),
            "confluence_threshold": self.confluence_threshold,
        }
        rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:24]
