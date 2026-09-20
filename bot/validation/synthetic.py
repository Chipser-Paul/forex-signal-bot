from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from bot.backtesting.models import FidelityClass

from .datasets import DXY_CONSTITUENTS, EXECUTABLE_SYMBOL, file_sha256
from .models import (
    DataStreamKind,
    DataStreamManifest,
    EmpiricalPackageManifest,
    StudyPeriod,
    TradeSample,
    ValidationError,
)


UTC = timezone.utc
START = datetime(2024, 1, 10, 0, 0, tzinfo=UTC)
END = datetime(2024, 1, 10, 0, 5, tzinfo=UTC)
TIMEFRAME_COUNTS = {"M5": 35, "M15": 2, "H1": 20, "H4": 20, "D1": 20, "W1": 2}
TIMEFRAME_SECONDS = {"M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400, "W1": 604800}


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")


def _stream(
    root: Path,
    *,
    name: str,
    kind: DataStreamKind,
    symbol: str,
    records: Sequence[Mapping[str, Any]],
    start: datetime,
    end: datetime,
    timeframe: str | None = None,
    maximum_gap: int | None = None,
) -> DataStreamManifest:
    relative = f"streams/{name}.jsonl" if kind is not DataStreamKind.BROKER_METADATA else f"streams/{name}.json"
    path = root / relative
    if kind is DataStreamKind.BROKER_METADATA:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(path)
        path.write_text(json.dumps(records[0], sort_keys=True, indent=2) + "\n", encoding="utf-8")
    else:
        _write_jsonl(path, records)
    return DataStreamManifest(
        name=name,
        kind=kind,
        relative_path=relative,
        sha256=file_sha256(path),
        symbol=symbol,
        start=start,
        end=end,
        record_count=len(records),
        provenance="SYNTHETIC_PHASE8A_FIXTURE",
        license_or_restrictions="TEST_USE_ONLY",
        timeframe=timeframe,
        maximum_expected_gap_seconds=maximum_gap,
    )


def build_synthetic_package(
    root: Path,
    *,
    package_id: str = "synthetic-phase8a",
    fidelity: FidelityClass = FidelityClass.TICK_BID_ASK,
    synthetic: bool = True,
) -> EmpiricalPackageManifest:
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise ValidationError("synthetic package directory must be empty")
    root.mkdir(parents=True, exist_ok=True)
    streams = []
    quote_records = [
        {"timestamp": START.isoformat(), "bid": 2030.0, "ask": 2030.2, "sequence": 1},
        {"timestamp": END.isoformat(), "bid": 2031.0, "ask": 2031.2, "sequence": 2},
    ]
    streams.append(_stream(
        root, name="xau_ticks", kind=DataStreamKind.EXECUTION_QUOTES,
        symbol=EXECUTABLE_SYMBOL, records=quote_records, start=START, end=END, maximum_gap=600,
    ))
    for timeframe, count in TIMEFRAME_COUNTS.items():
        duration = timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
        records = []
        for offset in range(count - 1, -1, -1):
            available = END - duration * offset
            open_time = available - duration
            records.append({
                "open_time": open_time.isoformat(),
                "available_at": available.isoformat(),
                "open": 2029.0,
                "high": 2032.0,
                "low": 2028.0,
                "close": 2030.0,
                "volume": 10,
                "timeframe": timeframe,
            })
        streams.append(_stream(
            root,
            name=f"xau_{timeframe.lower()}",
            kind=DataStreamKind.ANALYSIS_CANDLES,
            symbol=EXECUTABLE_SYMBOL,
            records=records,
            start=END - duration * (count - 1),
            end=END,
            timeframe=timeframe,
            maximum_gap=TIMEFRAME_SECONDS[timeframe] * 2,
        ))
    for constituent in sorted(DXY_CONSTITUENTS):
        records = [
            {"timestamp": START.isoformat(), "close": 1.0},
            {"timestamp": END.isoformat(), "close": 1.001},
        ]
        streams.append(_stream(
            root, name=f"dxy_{constituent.lower()}", kind=DataStreamKind.DXY_CONSTITUENT,
            symbol=constituent, records=records, start=START, end=END, maximum_gap=600,
        ))
    news = [
        {"timestamp": START.isoformat(), "event_id": "news-start", "currency": "USD", "impact": "LOW", "name": "fixture start", "provider": "synthetic", "retrieved_at": START.isoformat()},
        {"timestamp": END.isoformat(), "event_id": "news-end", "currency": "USD", "impact": "LOW", "name": "fixture end", "provider": "synthetic", "retrieved_at": END.isoformat()},
    ]
    streams.append(_stream(
        root, name="news", kind=DataStreamKind.NEWS_EVENTS, symbol="USD",
        records=news, start=START, end=END, maximum_gap=600,
    ))
    slippage = [
        {"timestamp": START.isoformat(), "slippage_price": 0.01},
        {"timestamp": END.isoformat(), "slippage_price": 0.02},
    ]
    streams.append(_stream(
        root, name="slippage", kind=DataStreamKind.SLIPPAGE_OBSERVATIONS,
        symbol=EXECUTABLE_SYMBOL, records=slippage, start=START, end=END, maximum_gap=600,
    ))
    metadata_start = START - timedelta(days=365)
    metadata_end = END + timedelta(days=365)
    metadata = {
        "effective_from": metadata_start.isoformat(),
        "effective_to": metadata_end.isoformat(),
        "symbol": EXECUTABLE_SYMBOL,
        "broker_source": "SYNTHETIC_PHASE8A_FIXTURE",
        "digits": 2,
        "point_size": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "contract_size": 100.0,
        "volume_min": 0.01,
        "volume_max": 10.0,
        "volume_step": 0.01,
        "margin_rate": 0.05,
        "account_currency": "USD",
        "profit_currency": "USD",
        "margin_currency": "USD",
        "commission": {"source": "OBSERVED", "kind": "PER_LOT_PER_SIDE", "value": 2.5},
        "swap": {"source": "OBSERVED", "long": -1.0, "short": 0.5, "rollover_timezone": "America/New_York", "triple_weekday": 2},
    }
    streams.append(_stream(
        root, name="broker_metadata", kind=DataStreamKind.BROKER_METADATA,
        symbol=EXECUTABLE_SYMBOL, records=[metadata], start=metadata_start, end=metadata_end,
    ))
    return EmpiricalPackageManifest(
        schema_version=1,
        package_id=package_id,
        broker_source="SYNTHETIC_PHASE8A_FIXTURE",
        fidelity=fidelity,
        evaluation_period=StudyPeriod(START, END, "synthetic-evaluation"),
        streams=tuple(streams),
        synthetic=synthetic,
        collection_method="deterministic generated test fixture",
        created_at=END,
    )


def synthetic_trades(count: int = 24) -> tuple[TradeSample, ...]:
    if count < 1:
        return ()
    trades = []
    for index in range(count):
        opened = START + timedelta(days=index)
        net_r = (0.8, -0.5, 1.2, -1.0, 0.4, -0.2)[index % 6]
        gross = net_r * 3.5 + 0.25
        trades.append(TradeSample(
            trade_id=f"synthetic-trade-{index + 1:03d}",
            opened_at=opened,
            closed_at=opened + timedelta(hours=2),
            side="LONG" if index % 2 == 0 else "SHORT",
            gross_pnl=gross,
            net_pnl=net_r * 3.5,
            net_r=net_r,
            costs=0.25,
            exposure_seconds=7200,
            turnover=200.0,
            regime=("TRENDING_UP", "TRENDING_DOWN", "RANGING")[index % 3],
            session=("LONDON", "NEW_YORK", "OVERLAP")[index % 3],
            spread_environment="ELEVATED" if index % 5 == 0 else "NORMAL",
        ))
    return tuple(trades)
