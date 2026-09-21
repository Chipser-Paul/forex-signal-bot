# utils/risk.py

import MetaTrader5 as mt5


def calculate_lot_size(
    symbol: str,
    capital: float,
    risk_per_trade: float = 0.01,
    stop_pips: float = 30,
):
    """
    Calculate lot size using REAL MT5 symbol properties.
    Works safely for FX, Gold, Crypto.
    """

    # Basic validation
    if capital <= 0 or stop_pips <= 0 or risk_per_trade <= 0:
        return None

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return None

    # Risk in account currency
    risk_amount = capital * risk_per_trade

    # Broker-specific values
    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size

    if tick_value <= 0 or tick_size <= 0:
        return None

    # Value per pip per lot
    pip_value_per_lot = tick_value / tick_size

    # Risk per 1 lot
    risk_per_lot = stop_pips * pip_value_per_lot

    if risk_per_lot <= 0:
        return None

    # Raw lot calculation
    lot = risk_amount / risk_per_lot

    # Enforce broker limits
    lot = max(lot, symbol_info.volume_min)
    lot = min(lot, symbol_info.volume_max)

    # Normalize to lot step
    lot = round(lot / symbol_info.volume_step) * symbol_info.volume_step

    return round(lot, 2)
