from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

from .models import RiskError, RiskPolicy


def human_percent_to_fraction(value: str | float | int, *, field_name: str) -> float:
    try:
        percentage = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise RiskError(f"{field_name} must be a finite human percentage") from exc
    if not percentage.is_finite() or percentage <= 0:
        raise RiskError(f"{field_name} must be a positive human percentage")
    return float(percentage / Decimal("100"))


def validation_policy(environ: Mapping[str, str] | None = None) -> RiskPolicy:
    environ = environ or {}
    base = 0.0035
    if "RISK_PER_TRADE_PCT" in environ:
        base = human_percent_to_fraction(
            environ["RISK_PER_TRADE_PCT"],
            field_name="RISK_PER_TRADE_PCT",
        )
    return RiskPolicy(base_risk_fraction=base)
