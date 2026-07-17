from __future__ import annotations

from dataclasses import dataclass

from bot.data.market_data import MarketDataRequest, fetch_batch, fetch_ohlcv
from strategies.smc_engine.market_structure import analyze_market_structure


BIAS_TIMEFRAMES: tuple[str, ...] = ("W1", "D1", "H4", "H1", "M15")
HTF_AGGREGATION_TIMEFRAMES: tuple[str, ...] = ("W1", "D1", "H4")
TIMEFRAME_WEIGHTS: dict[str, float] = {
    "W1": 0.40,
    "D1": 0.35,
    "H4": 0.25,
}
DEFAULT_BARS: dict[str, int] = {
    "W1": 220,
    "D1": 320,
    "H4": 320,
    "H1": 320,
    "M15": 320,
}


@dataclass(frozen=True)
class TimeframeBias:
    timeframe: str
    direction: str
    score: int
    confidence: int
    state: str
    event: str | None
    condition: str | None
    lead_bias: str | None


def _normalize_direction(result: dict | None) -> str:
    if not result:
        return "neutral"

    structure = result.get("structure")
    state = result.get("state")
    event = result.get("event")
    lead_bias = (result.get("lead_bias") or {}).get("direction")

    if state == "confirmed" and structure in ("bullish", "bearish"):
        return structure
    if state == "transition" and structure in ("bullish", "bearish"):
        return structure
    # A clear BOS event signals directional conviction even when
    # confidence/state hasn't caught up (e.g. trend transition).
    if structure in ("bullish", "bearish") and event == "BOS":
        return structure
    if lead_bias in ("bullish", "bearish"):
        return lead_bias
    return "neutral"


def _direction_to_score(direction: str) -> int:
    if direction == "bullish":
        return 1
    if direction == "bearish":
        return -1
    return 0


def analyze_timeframe_bias(symbol: str, timeframe: str, bars: int | None = None, silent: bool = False) -> TimeframeBias:
    df = fetch_ohlcv(symbol, timeframe, bars=bars or DEFAULT_BARS.get(timeframe, 320))
    result = analyze_market_structure(df, silent=silent) if df is not None and not df.empty else None
    direction = _normalize_direction(result)
    return TimeframeBias(
        timeframe=timeframe,
        direction=direction,
        score=_direction_to_score(direction),
        confidence=int((result or {}).get("confidence", 0) or 0),
        state=str((result or {}).get("state", "range")),
        event=(result or {}).get("event"),
        condition=(result or {}).get("condition"),
        lead_bias=((result or {}).get("lead_bias") or {}).get("direction"),
    )


def get_timeframe_biases(symbol: str, timeframes: tuple[str, ...] = BIAS_TIMEFRAMES, silent: bool = False) -> dict[str, TimeframeBias]:
    requests = [
        MarketDataRequest(symbol=symbol, timeframe=tf, bars=DEFAULT_BARS.get(tf, 320))
        for tf in timeframes
    ]
    data = fetch_batch(requests)

    biases: dict[str, TimeframeBias] = {}
    for tf in timeframes:
        df = data.get((symbol, tf))
        result = analyze_market_structure(df, silent=silent) if df is not None and not df.empty else None
        direction = _normalize_direction(result)
        biases[tf] = TimeframeBias(
            timeframe=tf,
            direction=direction,
            score=_direction_to_score(direction),
            confidence=int((result or {}).get("confidence", 0) or 0),
            state=str((result or {}).get("state", "range")),
            event=(result or {}).get("event"),
            condition=(result or {}).get("condition"),
            lead_bias=((result or {}).get("lead_bias") or {}).get("direction"),
        )
    return biases


def aggregate_htf_bias(timeframe_biases: dict[str, TimeframeBias]) -> dict[str, object]:
    raw_sum = sum(timeframe_biases[tf].score for tf in HTF_AGGREGATION_TIMEFRAMES if tf in timeframe_biases)
    weighted_score = sum(
        timeframe_biases[tf].score * TIMEFRAME_WEIGHTS.get(tf, 0.0)
        for tf in HTF_AGGREGATION_TIMEFRAMES
        if tf in timeframe_biases
    )

    non_neutral_dirs = [
        timeframe_biases[tf].direction
        for tf in HTF_AGGREGATION_TIMEFRAMES
        if tf in timeframe_biases and timeframe_biases[tf].score != 0
    ]
    conflict = len(set(non_neutral_dirs)) > 1
    aligned = len(non_neutral_dirs) > 0 and not conflict

    if raw_sum > 0:
        direction = "bullish"
    elif raw_sum < 0:
        direction = "bearish"
    else:
        direction = "neutral"

    alignment_strength = round(abs(weighted_score), 4)
    return {
        "direction": direction,
        "raw_sum": int(raw_sum),
        "weighted_score": float(round(weighted_score, 4)),
        "alignment_strength": alignment_strength,
        "conflict": conflict,
        "aligned": aligned,
        "contributors": {
            tf: {
                "direction": timeframe_biases[tf].direction,
                "score": timeframe_biases[tf].score,
                "confidence": timeframe_biases[tf].confidence,
                "state": timeframe_biases[tf].state,
            }
            for tf in HTF_AGGREGATION_TIMEFRAMES
            if tf in timeframe_biases
        },
    }


def get_bias_snapshot(symbol: str, silent: bool = False) -> dict[str, object]:
    timeframe_biases = get_timeframe_biases(symbol, silent=silent)
    htf_bias = aggregate_htf_bias(timeframe_biases)
    return {
        "symbol": symbol,
        "timeframes": {
            tf: {
                "direction": bias.direction,
                "score": bias.score,
                "confidence": bias.confidence,
                "state": bias.state,
                "event": bias.event,
                "condition": bias.condition,
                "lead_bias": bias.lead_bias,
            }
            for tf, bias in timeframe_biases.items()
        },
        "htf_bias": htf_bias,
    }


def resolve_trade_bias(snapshot: dict[str, object] | None) -> dict[str, object]:
    snapshot = snapshot or {}
    timeframes = snapshot.get("timeframes") or {}
    htf_bias = snapshot.get("htf_bias") or {}

    def _tf(tf: str) -> dict[str, object]:
        return dict(timeframes.get(tf) or {})

    def _dir(tf: str) -> str:
        return str(_tf(tf).get("direction", "neutral"))

    def _state(tf: str) -> str:
        return str(_tf(tf).get("state", "range"))

    def _confidence(tf: str) -> int:
        return int(_tf(tf).get("confidence", 0) or 0)

    primary_direction = str(htf_bias.get("direction", "neutral"))
    if primary_direction in ("bullish", "bearish"):
        return {
            "direction": primary_direction,
            "confirmed": True,
            "mode": "primary_htf",
            "alignment_strength": float(htf_bias.get("alignment_strength", 0.0) or 0.0),
        }

    # Fallback 1: allow D1/H4 consensus to lead when H1 is not fighting it.
    for direction in ("bullish", "bearish"):
        if _dir("D1") == direction and _dir("H4") == direction and _dir("H1") in (direction, "neutral"):
            strength = round((_confidence("D1") + _confidence("H4") + max(_confidence("H1"), 25)) / 3, 2)
            if strength >= 35 or _state("H4") in ("confirmed", "transition"):
                return {
                    "direction": direction,
                    "confirmed": False,
                    "mode": "d1_h4_alignment",
                    "alignment_strength": float(strength),
                }

    # Fallback 2: allow H4/H1 agreement to act as a tactical bias when D1 is not opposing.
    for direction in ("bullish", "bearish"):
        if _dir("H4") == direction and _dir("H1") == direction and _dir("D1") in (direction, "neutral"):
            strength = round((_confidence("H4") + _confidence("H1")) / 2, 2)
            if strength >= 40 or _state("H1") in ("confirmed", "transition"):
                return {
                    "direction": direction,
                    "confirmed": False,
                    "mode": "h4_h1_alignment",
                    "alignment_strength": float(strength),
                }

    return {
        "direction": "neutral",
        "confirmed": False,
        "mode": "unconfirmed",
        "alignment_strength": 0.0,
    }
