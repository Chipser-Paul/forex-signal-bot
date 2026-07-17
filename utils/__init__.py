#utils/__init__.py
import importlib.util
import os
import sys
import joblib
import pandas as pd
from pathlib import Path

MODEL_PATH = "models/ai_model.pkl"
DATA_FOLDER = "data/offline"

def load_model():
    """Loads the AI model from disk."""
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}")
    return joblib.load(MODEL_PATH)

def load_price_data(symbol, timeframe='M5'):
    """Loads offline historical price data for a given symbol."""
    file_path = os.path.join(DATA_FOLDER, f"{symbol}_{timeframe}.csv")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Price data not found for {symbol} at {file_path}")
    df = pd.read_csv(file_path)
    df.columns = [col.lower() for col in df.columns]
    df['time'] = pd.to_datetime(df['time'], unit='s', errors='coerce')
    df.dropna(inplace=True)
    return df

def load_strategies(symbol: str) -> list:
    """
    Dynamically load strategy modules from strategy/<symbol>/ folder.
    Each file must have an evaluate(df) function.
    """
    strategy_dir = Path(f"strategy/{symbol}")
    if not strategy_dir.exists():
        raise FileNotFoundError(f"No strategy directory for symbol: {symbol}")
    
    strategies = []
    for file in strategy_dir.glob("*.py"):
        if file.name.startswith("_"):
            continue  # ignore init.py or _*.py
        module_name = f"{symbol}_{file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(file))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        strategies.append(mod)
    return strategies