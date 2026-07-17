"""
utils/volatility.py
Adaptive SL/TP calculation using ATR and market bias
"""
import MetaTrader5 as mt5
import pandas as pd
from utils.fetch import fetch_ohlcv
from trend_filter import detect_trend

def adapt_tp_sl(symbol: str, df: pd.DataFrame, base_tp: float = 3.0, direction: str = "buy", atr_period: int = 14, atr_mult: float = 1.5):
    """
    Adjust SL/TP using ATR and trend alignment.
    - direction: 'buy' or 'sell'
    - Returns (sl_points, tp_points)
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return base_tp / 1.5, base_tp  # fallback basic SL/TP

    try:
        # Calculate ATR
        atr = (df["high"] - df["low"]).rolling(atr_period).mean().iloc[-1]
        entry = df["close"].iloc[-1]
        if atr is None or pd.isna(atr):
            return base_tp / 1.5, base_tp

        # Symbol info for precision
        info = mt5.symbol_info(symbol)
        point = info.point if info else 0.01
        digits = info.digits if info else 2

        # Default buffers
        sl_buffer = atr * atr_mult
        tp_buffer = atr * atr_mult * 1.2

        # Trend bias
        trend_result = detect_trend(df)
        trend_dir = trend_result[0] if trend_result and isinstance(trend_result, tuple) else None

        # Adjust based on trend
        if direction == "buy":
            sl = entry - sl_buffer
            tp = entry + tp_buffer
            if trend_dir == "up":
                tp += atr * 0.5
                sl += atr * 0.2
            elif trend_dir == "down":
                tp -= atr * 0.4
        elif direction == "sell":
            sl = entry + sl_buffer
            tp = entry - tp_buffer
            if trend_dir == "down":
                tp -= atr * 0.5
                sl -= atr * 0.2
            elif trend_dir == "up":
                tp += atr * 0.4
        else:
            return base_tp / 1.5, base_tp  # fallback

        sl_points = abs(sl - entry)
        tp_points = abs(tp - entry)
        return round(sl_points, digits), round(tp_points, digits)

    except Exception as e:
        print(f"[❌] adapt_tp_sl error: {e}")
        return base_tp / 1.5, base_tp  # safe fallback