#utils\indicators.py

import pandas as pd

def calculate_atr(df, period=14):
    if df is None or df.empty or len(df) < period:
        return 0.0
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr = (
        (high - low)
        .combine((high - close.shift()).abs(), max)
        .combine((low - close.shift()).abs(), max)
    )
    atr_series = tr.rolling(period).mean()
    if atr_series.empty:
        return 0.0
    return float(atr_series.iloc[-1])
