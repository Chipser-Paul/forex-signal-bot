from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from types import ModuleType
from typing import Any, Iterable

from app_security.redaction import redact_text

from .models import AcquisitionError, SafeSymbolMetadata, utc_datetime


PERMITTED_MT5_OPERATIONS = frozenset({
    "initialize",
    "shutdown",
    "last_error",
    "version",
    "symbol_info",
    "symbol_select",
    "symbols_get",
    "copy_ticks_range",
    "copy_rates_range",
})
PROHIBITED_MT5_OPERATIONS = frozenset({
    "login",
    "account_info",
    "positions_get",
    "orders_get",
    "history_orders_get",
    "history_deals_get",
    "order_calc_margin",
    "order_calc_profit",
    "order_check",
    "order_send",
})


@dataclass(frozen=True)
class SafeMT5Error:
    code: int | None
    category: str
    description_sha256: str


def _safe_text(value: object, *, fallback: str = "not-disclosed") -> str:
    text = redact_text(value or "").strip()
    if not text:
        return fallback
    text = re.sub(r"[A-Za-z]:\\[^\s,;]+", "<redacted-path>", text)
    text = re.sub(r"\b\d{6,}\b", "<redacted-number>", text)
    return text[:160]


class ReadOnlyMT5Gateway:
    """Narrow wrapper whose public surface cannot express a trading operation."""

    __slots__ = ("__mt5", "__initialized")

    def __init__(self, mt5_module: ModuleType | Any) -> None:
        missing = [name for name in PERMITTED_MT5_OPERATIONS if not callable(getattr(mt5_module, name, None))]
        if missing:
            raise AcquisitionError("MT5 read-only capability is incomplete")
        self.__mt5 = mt5_module
        self.__initialized = False

    @property
    def permitted_operations(self) -> tuple[str, ...]:
        return tuple(sorted(PERMITTED_MT5_OPERATIONS))

    @property
    def is_initialized(self) -> bool:
        return self.__initialized

    def initialize(self, *, confirmed_read_only_demo_export: bool) -> None:
        if not confirmed_read_only_demo_export:
            raise AcquisitionError("read-only demo export confirmation is required")
        try:
            initialized = self.__mt5.initialize()
        except Exception:
            raise AcquisitionError("MT5 terminal initialization failed") from None
        if not initialized:
            raise AcquisitionError("MT5 terminal is unavailable or not already authenticated")
        self.__initialized = True

    def shutdown(self) -> None:
        if self.__initialized:
            try:
                self.__mt5.shutdown()
            finally:
                self.__initialized = False

    def last_error(self) -> tuple[int | None, str]:
        status = self.last_error_status()
        return status.code, "MT5_READ_ONLY_ERROR_REDACTED"

    def last_error_status(self) -> SafeMT5Error:
        try:
            value = self.__mt5.last_error()
            code = int(value[0]) if isinstance(value, (tuple, list)) and value else None
            description = value[1] if isinstance(value, (tuple, list)) and len(value) > 1 else ""
        except Exception:
            code = None
            description = ""
        safe_description = _safe_text(description, fallback="not-disclosed")
        category = "SUCCESS" if code in {0, 1} else ("UNKNOWN" if code is None else "MT5_ERROR")
        return SafeMT5Error(
            code=code,
            category=category,
            description_sha256=hashlib.sha256(safe_description.encode("utf-8")).hexdigest(),
        )

    def version(self) -> tuple[int, ...] | None:
        self._require_initialized()
        try:
            value = self.__mt5.version()
            if not isinstance(value, (tuple, list)):
                return None
            return tuple(int(item) for item in value[:2])
        except Exception:
            return None

    def discover_symbols(self, base_symbol: str) -> tuple[dict[str, object], ...]:
        self._require_initialized()
        if not base_symbol.isalpha() or len(base_symbol) > 12:
            raise AcquisitionError("symbol discovery pattern is invalid")
        try:
            records = self.__mt5.symbols_get(group=f"*{base_symbol}*") or ()
        except Exception:
            raise AcquisitionError("restricted symbol discovery failed") from None
        return tuple(self._safe_symbol_identity(record) for record in records)

    def symbol_info(self, symbol: str) -> dict[str, object] | None:
        self._require_initialized()
        self._validate_symbol(symbol)
        try:
            record = self.__mt5.symbol_info(symbol)
        except Exception:
            raise AcquisitionError("symbol metadata lookup failed") from None
        return None if record is None else self._safe_symbol_identity(record, full=True)

    def symbol_select(self, symbol: str) -> bool:
        self._require_initialized()
        self._validate_symbol(symbol)
        try:
            return bool(self.__mt5.symbol_select(symbol, True))
        except Exception:
            raise AcquisitionError("symbol selection failed") from None

    def copy_ticks_range(self, symbol: str, start: datetime, end: datetime) -> Any:
        self._require_initialized()
        self._validate_symbol(symbol)
        start = utc_datetime(start, "tick start")
        end = utc_datetime(end, "tick end")
        if end <= start:
            raise AcquisitionError("tick range must be increasing")
        try:
            copy_all = int(getattr(self.__mt5, "COPY_TICKS_ALL"))
            return self.__mt5.copy_ticks_range(symbol, start, end, copy_all)
        except Exception:
            raise AcquisitionError("tick history retrieval failed") from None

    def copy_rates_range(self, symbol: str, timeframe: int, start: datetime, end: datetime) -> Any:
        self._require_initialized()
        self._validate_symbol(symbol)
        start = utc_datetime(start, "bar start")
        end = utc_datetime(end, "bar end")
        if not isinstance(timeframe, int) or end <= start:
            raise AcquisitionError("bar range arguments are invalid")
        try:
            return self.__mt5.copy_rates_range(symbol, timeframe, start, end)
        except Exception:
            raise AcquisitionError("bar history retrieval failed") from None

    def timeframe_value(self, attribute: str) -> int:
        self._require_initialized()
        if not attribute.startswith("TIMEFRAME_"):
            raise AcquisitionError("timeframe attribute is invalid")
        value = getattr(self.__mt5, attribute, None)
        if not isinstance(value, int):
            raise AcquisitionError("MT5 timeframe is unavailable")
        return value

    def safe_metadata(self, symbol: str, exported_at: datetime) -> SafeSymbolMetadata:
        raw = self.symbol_info(symbol)
        if raw is None:
            raise AcquisitionError("symbol is unavailable")
        required = {
            "point": raw.get("point"),
            "trade_tick_size": raw.get("trade_tick_size"),
            "trade_contract_size": raw.get("trade_contract_size"),
            "volume_min": raw.get("volume_min"),
            "volume_max": raw.get("volume_max"),
            "volume_step": raw.get("volume_step"),
        }
        if any(value is None for value in required.values()):
            raise AcquisitionError("required symbol metadata is unavailable")
        optional = ("trade_tick_value", "trade_tick_value_profit", "trade_tick_value_loss")
        return SafeSymbolMetadata(
            symbol=str(raw["name"]),
            description=_safe_text(raw.get("description")),
            currency_base=_safe_text(raw.get("currency_base")),
            currency_profit=_safe_text(raw.get("currency_profit")),
            currency_margin=_safe_text(raw.get("currency_margin")),
            digits=int(raw.get("digits", 0)),
            point=float(raw["point"]),
            trade_tick_size=float(raw["trade_tick_size"]),
            trade_tick_value=float(raw.get("trade_tick_value") or 0),
            trade_tick_value_profit=float(raw.get("trade_tick_value_profit") or 0),
            trade_tick_value_loss=float(raw.get("trade_tick_value_loss") or 0),
            trade_contract_size=float(raw["trade_contract_size"]),
            volume_min=float(raw["volume_min"]),
            volume_max=float(raw["volume_max"]),
            volume_step=float(raw["volume_step"]),
            trade_stops_level=int(raw.get("trade_stops_level") or raw.get("stops_level") or 0),
            trade_freeze_level=int(raw.get("trade_freeze_level") or 0),
            filling_mode=int(raw.get("filling_mode") or 0),
            trade_exemode=int(raw.get("trade_exemode") or 0),
            swap_long=float(raw.get("swap_long") or 0),
            swap_short=float(raw.get("swap_short") or 0),
            swap_mode=int(raw.get("swap_mode") or 0),
            swap_rollover3days=int(raw.get("swap_rollover3days") or 0),
            exported_at=exported_at,
            missing_fields=tuple(name for name in optional if raw.get(name) is None),
        )

    def _require_initialized(self) -> None:
        if not self.__initialized:
            raise AcquisitionError("MT5 gateway is not initialized")

    @staticmethod
    def _validate_symbol(symbol: str) -> None:
        if not symbol or len(symbol) > 32 or not re.fullmatch(r"[A-Za-z0-9._-]+", symbol):
            raise AcquisitionError("symbol identity is invalid")

    @staticmethod
    def _safe_symbol_identity(record: Any, *, full: bool = False) -> dict[str, object]:
        fields: Iterable[str] = (
            "name", "description", "currency_base", "currency_profit", "currency_margin", "digits", "point"
        )
        if full:
            fields = tuple(fields) + (
                "trade_tick_size", "trade_tick_value", "trade_tick_value_profit", "trade_tick_value_loss",
                "trade_contract_size", "volume_min", "volume_max", "volume_step", "trade_stops_level",
                "stops_level", "trade_freeze_level", "filling_mode", "trade_exemode", "swap_long",
                "swap_short", "swap_mode", "swap_rollover3days", "visible",
            )
        return {
            field: _safe_text(getattr(record, field, "")) if field in {
                "name", "description", "currency_base", "currency_profit", "currency_margin"
            } else getattr(record, field, None)
            for field in fields
        }


def assert_gateway_surface() -> None:
    public = {name for name in dir(ReadOnlyMT5Gateway) if not name.startswith("_")}
    reachable = public & PROHIBITED_MT5_OPERATIONS
    if reachable:
        raise AssertionError(f"forbidden MT5 operations are reachable: {sorted(reachable)}")


assert_gateway_surface()
