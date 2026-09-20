from __future__ import annotations

from datetime import datetime

from bot.utils.session_windows import ASIAN_SESSION
from strategies.smc_engine.market_structure import analyze_market_structure


def _pool_entry(price: float, pool_type: str, timeframe: str, **extra) -> dict[str, object]:
    return {
        "price": float(price),
        "type": pool_type,
        "timeframe": timeframe,
        **extra,
    }


def _row_timestamp(row) -> str | None:
    if hasattr(row, "get") and "time" in row:
        value = row["time"]
        return value.isoformat() if hasattr(value, "isoformat") else None
    index_value = getattr(row, "name", None)
    return index_value.isoformat() if hasattr(index_value, "isoformat") else None


def get_previous_day_levels(daily_df):
    if daily_df is None or len(daily_df) < 2:
        return None
    prev = daily_df.iloc[-2]
    return {
        "high": float(prev["high"]),
        "low": float(prev["low"]),
        "timestamp": _row_timestamp(prev),
    }


def get_previous_week_levels(weekly_df):
    if weekly_df is None or len(weekly_df) < 2:
        return None
    prev = weekly_df.iloc[-2]
    return {
        "high": float(prev["high"]),
        "low": float(prev["low"]),
        "timestamp": _row_timestamp(prev),
    }


def get_asian_session_range(intraday_df):
    if intraday_df is None or intraday_df.empty:
        return None

    df = intraday_df.copy()
    if "time" not in df.columns:
        df = df.reset_index().rename(columns={df.index.name or "index": "time"})

    latest_ts = df["time"].max()
    if latest_ts is None:
        return None

    current_day = latest_ts.date()
    session_mask = (
        (df["time"].dt.date == current_day)
        & (df["time"].dt.time >= ASIAN_SESSION.start)
        & (df["time"].dt.time < ASIAN_SESSION.end)
    )
    session_df = df.loc[session_mask]
    if session_df.empty:
        return None

    return {
        "high": float(session_df["high"].max()),
        "low": float(session_df["low"].min()),
        "start_utc": datetime.combine(current_day, ASIAN_SESSION.start).isoformat(),
        "end_utc": datetime.combine(current_day, ASIAN_SESSION.end).isoformat(),
    }


def build_liquidity_map_from_frames(symbol: str, frames, silent: bool = False) -> dict[str, object]:
    structure_df = frames.get("H1")
    intraday_df = frames.get("M15")
    daily_df = frames.get("D1")
    weekly_df = frames.get("W1")

    structure = analyze_market_structure(structure_df, silent=silent) if structure_df is not None and not structure_df.empty else None
    previous_day = get_previous_day_levels(daily_df)
    previous_week = get_previous_week_levels(weekly_df)
    asian_range = get_asian_session_range(intraday_df)

    liquidity_pools: list[dict[str, object]] = []

    if structure:
        for level in structure.get("equal_highs", []):
            liquidity_pools.append(
                _pool_entry(
                    level["price"], "equal_highs", "H1",
                    top=level["top"], bottom=level["bottom"], count=level["count"],
                )
            )
        for level in structure.get("equal_lows", []):
            liquidity_pools.append(
                _pool_entry(
                    level["price"], "equal_lows", "H1",
                    top=level["top"], bottom=level["bottom"], count=level["count"],
                )
            )

    if previous_day:
        liquidity_pools.append(_pool_entry(previous_day["high"], "pdh", "D1"))
        liquidity_pools.append(_pool_entry(previous_day["low"], "pdl", "D1"))

    if previous_week:
        liquidity_pools.append(_pool_entry(previous_week["high"], "pwh", "W1"))
        liquidity_pools.append(_pool_entry(previous_week["low"], "pwl", "W1"))

    if asian_range:
        liquidity_pools.append(_pool_entry(asian_range["high"], "asian_high", "session"))
        liquidity_pools.append(_pool_entry(asian_range["low"], "asian_low", "session"))

    return {
        "symbol": symbol,
        "structure_context": structure,
        "previous_day": previous_day,
        "previous_week": previous_week,
        "asian_range": asian_range,
        "liquidity_pools": liquidity_pools,
    }


def build_liquidity_map(symbol: str, silent: bool = False) -> dict[str, object]:
    from bot.data.market_data import fetch_batch, MarketDataRequest

    requests = [
        MarketDataRequest(symbol=symbol, timeframe="H1", bars=320),
        MarketDataRequest(symbol=symbol, timeframe="M15", bars=320),
        MarketDataRequest(symbol=symbol, timeframe="D1", bars=10),
        MarketDataRequest(symbol=symbol, timeframe="W1", bars=10),
    ]
    datasets = fetch_batch(requests)

    return build_liquidity_map_from_frames(
        symbol, {tf: datasets.get((symbol, tf)) for tf in ("H1", "M15", "D1", "W1")}, silent,
    )
