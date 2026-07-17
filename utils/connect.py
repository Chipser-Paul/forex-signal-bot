# utils/connect.py
import MetaTrader5 as mt5
import os
from dotenv import load_dotenv # pyright: ignore[reportMissingImports]
from utils.log import log

load_dotenv()

def connect_mt5():
    login = int(os.getenv("MT5_LOGIN"))
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")

    if not mt5.initialize(login=login, password=password, server=server):
        log(f"❌ MT5 init failed → {mt5.last_error()}", "red")
        return False

    account_info = mt5.account_info()
    if account_info:
        log("✅ MT5 connected")
        return True
    else:
        log("❌ Failed to get account info", "red")
        return False
