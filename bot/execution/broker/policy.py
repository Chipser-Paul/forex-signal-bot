from __future__ import annotations

import re
from typing import Mapping

from .models import ExecutionError, ExecutionPolicy


def symbol_environment_key(prefix: str, symbol: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "", symbol).upper()
    if not normalized:
        raise ExecutionError("symbol cannot be converted to a configuration key")
    return f"{prefix}_{normalized}"


def execution_policy_from_environment(
    environment: Mapping[str, str],
    symbols: tuple[str, ...],
) -> ExecutionPolicy:
    raw_magic = str(environment.get("BOT_MAGIC_NUMBER", "")).strip()
    if not raw_magic:
        raise ExecutionError("BOT_MAGIC_NUMBER is required")
    try:
        magic = int(raw_magic)
    except ValueError as exc:
        raise ExecutionError("BOT_MAGIC_NUMBER must be a non-zero integer") from exc

    spreads: dict[str, float] = {}
    deviations: dict[str, int] = {}
    for symbol in symbols:
        spread_key = symbol_environment_key("BOT_MAX_SPREAD_POINTS", symbol)
        deviation_key = symbol_environment_key("BOT_MAX_DEVIATION_POINTS", symbol)
        raw_spread = str(environment.get(spread_key, "")).strip()
        raw_deviation = str(environment.get(deviation_key, "")).strip()
        if not raw_spread or not raw_deviation:
            raise ExecutionError(
                f"{spread_key} and {deviation_key} are required for live execution"
            )
        try:
            spreads[symbol] = float(raw_spread)
            deviations[symbol] = int(raw_deviation)
        except ValueError as exc:
            raise ExecutionError(f"broker limits are invalid for {symbol}") from exc

    return ExecutionPolicy(
        magic_number=magic,
        maximum_spread_points=spreads,
        maximum_deviation_points=deviations,
    )
