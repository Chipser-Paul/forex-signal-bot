from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


UTC = timezone.utc


def symbol(
    name: str,
    *,
    currency_base: str | None = None,
    currency_profit: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description=f"{name} test instrument",
        currency_base=currency_base or name[:3],
        currency_profit=currency_profit or name[3:6],
        currency_margin="USD",
        digits=2,
        point=0.01,
        trade_tick_size=0.01,
        trade_tick_value=1.0,
        trade_tick_value_profit=1.0,
        trade_tick_value_loss=1.0,
        trade_contract_size=100.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        trade_stops_level=10,
        trade_freeze_level=5,
        filling_mode=3,
        trade_exemode=2,
        swap_long=-1.0,
        swap_short=0.5,
        swap_mode=1,
        swap_rollover3days=3,
        visible=True,
    )


class FakeReadOnlyMT5:
    COPY_TICKS_ALL = 0
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440
    TIMEFRAME_W1 = 10080

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.initialized = True
        self.symbols = {
            "XAUUSDm": symbol("XAUUSDm", currency_base="XAU", currency_profit="USD"),
            **{base: symbol(base) for base in ("EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF")},
        }
        self.ticks = []
        self.rates = []
        self.last_error_value = (1, "Success")

    def _call(self, name: str, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def initialize(self, *args, **kwargs):
        self._call("initialize", *args, **kwargs)
        return self.initialized

    def shutdown(self):
        self._call("shutdown")
        return True

    def last_error(self):
        self._call("last_error")
        return self.last_error_value

    def version(self):
        return 5, 0, 1234, "unsafe extra"

    def symbol_info(self, name):
        self._call("symbol_info", name)
        return self.symbols.get(name)

    def symbol_select(self, name, enabled):
        self._call("symbol_select", name, enabled)
        return name in self.symbols and enabled

    def symbols_get(self, group=None):
        self._call("symbols_get", group=group)
        needle = str(group or "").strip("*")
        return tuple(value for name, value in self.symbols.items() if needle in name)

    def copy_ticks_range(self, *args):
        self._call("copy_ticks_range", *args)
        _symbol, start, end, _flags = args
        return [
            item for item in self.ticks
            if start.timestamp() * 1000 <= int(item["time_msc"]) < end.timestamp() * 1000
        ]

    def copy_rates_range(self, *args):
        self._call("copy_rates_range", *args)
        _symbol, _timeframe, start, end = args
        return [item for item in self.rates if start.timestamp() <= int(item["time"]) < end.timestamp()]

    def _forbidden(self, name):
        raise AssertionError(f"forbidden fake method called: {name}")

    def account_info(self):
        self._forbidden("account_info")

    def positions_get(self):
        self._forbidden("positions_get")

    def orders_get(self):
        self._forbidden("orders_get")

    def history_orders_get(self):
        self._forbidden("history_orders_get")

    def history_deals_get(self):
        self._forbidden("history_deals_get")

    def order_check(self, _request):
        self._forbidden("order_check")

    def order_send(self, _request):
        self._forbidden("order_send")


def tick(timestamp: datetime, bid: float = 2000.0, ask: float = 2000.2, *, flags: int = 6):
    milliseconds = int(timestamp.timestamp() * 1000)
    return {
        "time": milliseconds // 1000,
        "time_msc": milliseconds,
        "bid": bid,
        "ask": ask,
        "last": 0.0,
        "volume": 1,
        "volume_real": 0.0,
        "flags": flags,
    }
