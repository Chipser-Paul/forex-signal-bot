from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .engine import HistoricalExecutionEngine
from .models import EXECUTION_MODEL_VERSION, HistoricalExecutionError, RunMode, enum_json
from .models import positive, utc_datetime


REQUIRED_RESULT_FILES = (
    "run_manifest.json",
    "configuration.json",
    "dataset_manifest.json",
    "fills.jsonl",
    "ledger.jsonl",
    "trades.jsonl",
    "equity.csv",
    "rejections.jsonl",
    "summary.json",
)
SENSITIVE_KEY_PARTS = ("PASSWORD", "SECRET", "TOKEN", "CREDENTIAL", "API_KEY", "MT5_LOGIN")


def canonical_json(value: Any) -> str:
    return json.dumps(enum_json(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def configuration_fingerprint(configuration: Mapping[str, Any]) -> str:
    _reject_sensitive_configuration(configuration)
    return hashlib.sha256(canonical_json(configuration).encode("utf-8")).hexdigest()


def _reject_sensitive_configuration(value: Any, path: str = "configuration") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).upper()
            if any(part in normalized for part in SENSITIVE_KEY_PARTS):
                raise HistoricalExecutionError(f"sensitive field is prohibited in {path}")
            _reject_sensitive_configuration(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_sensitive_configuration(item, f"{path}[{index}]")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _json_lines(items: Iterable[Any]) -> str:
    values = [canonical_json(item) for item in items]
    return "" if not values else "\n".join(values) + "\n"


@dataclass(frozen=True)
class RunDescriptor:
    git_commit: str
    git_dirty: bool
    strategy_version: str
    configuration: Mapping[str, Any]
    dataset_manifest: Mapping[str, Any]
    start_timestamp: str
    end_timestamp: str
    initial_capital: float
    timeframes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.git_commit or not self.strategy_version or not self.timeframes:
            raise HistoricalExecutionError("run commit, strategy version and timeframes are required")
        start = _parse_utc(self.start_timestamp, "run start")
        end = _parse_utc(self.end_timestamp, "run end")
        if end < start:
            raise HistoricalExecutionError("run end precedes run start")
        positive(self.initial_capital, "initial capital")


def _parse_utc(value: str, field_name: str):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise HistoricalExecutionError(f"{field_name} must be an ISO timestamp") from exc
    normalized = utc_datetime(parsed, field_name)
    if parsed.utcoffset() != normalized.utcoffset():
        raise HistoricalExecutionError(f"{field_name} must be expressed in UTC")
    return normalized


def build_summary(engine: HistoricalExecutionEngine) -> dict[str, Any]:
    closed = [position for position in engine.positions.values() if position.remaining_volume <= 1e-12]
    gross = sum(entry.gross_price_pnl for entry in engine.ledger)
    commission = sum(entry.commission for entry in engine.ledger)
    swap = sum(entry.swap for entry in engine.ledger)
    net = gross - commission + swap
    trade_net: dict[str, float] = {}
    for entry in engine.ledger:
        if entry.trade_id:
            trade_net[entry.trade_id] = trade_net.get(entry.trade_id, 0.0) + entry.net_cash_change
    wins = sum(1 for value in trade_net.values() if value > 0)
    losses = sum(1 for value in trade_net.values() if value < 0)
    gross_profit = sum(value for value in trade_net.values() if value > 0)
    gross_loss = sum(value for value in trade_net.values() if value < 0)
    return {
        "result_label": engine.policy.result_label,
        "fidelity_class": engine.policy.fidelity.value,
        "execution_model_version": EXECUTION_MODEL_VERSION,
        "symbol": engine.metadata.symbol,
        "closed_trades": len(closed),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": None if not trade_net else wins / len(trade_net) * 100.0,
        "gross_price_pnl": gross,
        "commission": commission,
        "swap": swap,
        "net_pnl": net,
        "ending_balance": engine.account.balance,
        "profit_factor_net": None if gross_loss == 0 else gross_profit / abs(gross_loss),
        "maximum_equity_drawdown": _maximum_equity_drawdown(engine),
        "maximum_balance_drawdown": _maximum_balance_drawdown(engine),
        "rejection_counts": _reason_counts(engine.rejections),
        "profitability_evidence": False,
}


def _maximum_equity_drawdown(engine: HistoricalExecutionEngine) -> float:
    high_water = engine.account.initial_balance
    maximum = 0.0
    for row in engine.equity_curve:
        equity = float(row["equity"])
        high_water = max(high_water, equity)
        maximum = max(maximum, high_water - equity)
    return maximum


def _maximum_balance_drawdown(engine: HistoricalExecutionEngine) -> float:
    high_water = engine.account.initial_balance
    maximum = 0.0
    for entry in engine.ledger:
        high_water = max(high_water, entry.balance_after)
        maximum = max(maximum, high_water - entry.balance_after)
    return maximum


def _reason_counts(rejections: Iterable[Mapping[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rejection in rejections:
        reason = str(rejection.get("reason_code", "UNKNOWN"))
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def write_result_bundle(
    root: Path,
    engine: HistoricalExecutionEngine,
    descriptor: RunDescriptor,
) -> Path:
    if engine.policy.mode is RunMode.VALIDATION and descriptor.git_dirty:
        raise HistoricalExecutionError("validation output cannot be produced from a dirty tree")
    config = enum_json(dict(descriptor.configuration))
    fingerprint = configuration_fingerprint(config)
    _reject_sensitive_configuration(descriptor.dataset_manifest, "dataset_manifest")
    result_dir = Path(root) / engine.run_id
    if result_dir.exists():
        raise FileExistsError(f"result directory already exists: {result_dir}")
    result_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(
        dir=str(result_dir.parent), prefix=f".{engine.run_id}.", suffix=".tmp"
    ))
    manifest = {
        "run_id": engine.run_id,
        "git_commit": descriptor.git_commit,
        "git_dirty": descriptor.git_dirty,
        "strategy_version": descriptor.strategy_version,
        "configuration_fingerprint": fingerprint,
        "dataset_hashes": descriptor.dataset_manifest.get("hashes", {}),
        "dataset_provenance": descriptor.dataset_manifest.get("provenance"),
        "fidelity_class": engine.policy.fidelity.value,
        "cost_sources": {
            "spread": "OBSERVED" if engine.policy.fidelity.value in {"TICK_BID_ASK", "BAR_BID_ASK"} else descriptor.dataset_manifest.get("spread_source", "UNKNOWN"),
            "slippage": engine.policy.slippage.source.value,
            "commission": engine.metadata.commission.source.value,
            "swap": engine.metadata.swap.source.value,
        },
        "random_seed": engine.policy.random_seed,
        "start_timestamp": descriptor.start_timestamp,
        "end_timestamp": descriptor.end_timestamp,
        "initial_capital": descriptor.initial_capital,
        "symbol": engine.metadata.symbol,
        "timeframes": list(descriptor.timeframes),
        "execution_model_version": EXECUTION_MODEL_VERSION,
        "run_mode": engine.policy.mode.value,
        "result_label": engine.policy.result_label,
        "profitability_evidence": False,
    }
    trades = []
    for position in sorted(engine.positions.values(), key=lambda item: item.position_id):
        entries = [entry for entry in engine.ledger if entry.trade_id == position.trade_id]
        gross = sum(entry.gross_price_pnl for entry in entries)
        commission = sum(entry.commission for entry in entries)
        swap = sum(entry.swap for entry in entries)
        trades.append({
            "trade_id": position.trade_id,
            "position_id": position.position_id,
            "symbol": position.symbol,
            "direction": position.direction.value,
            "opened_at": position.opened_at,
            "closed_at": position.closed_at,
            "entry_price": position.entry_price,
            "initial_volume": position.initial_volume,
            "remaining_volume": position.remaining_volume,
            "gross_price_pnl": gross,
            "commission": commission,
            "swap": swap,
            "net_pnl": gross - commission + swap,
        })
    try:
        _atomic_write(staging_dir / "run_manifest.json", json.dumps(enum_json(manifest), sort_keys=True, indent=2) + "\n")
        _atomic_write(staging_dir / "configuration.json", json.dumps(config, sort_keys=True, indent=2) + "\n")
        _atomic_write(staging_dir / "dataset_manifest.json", json.dumps(enum_json(descriptor.dataset_manifest), sort_keys=True, indent=2) + "\n")
        _atomic_write(staging_dir / "fills.jsonl", _json_lines(engine.fills))
        _atomic_write(staging_dir / "ledger.jsonl", _json_lines(engine.ledger))
        _atomic_write(staging_dir / "trades.jsonl", _json_lines(trades))
        _atomic_write(staging_dir / "rejections.jsonl", _json_lines(engine.rejections))
        summary = build_summary(engine)
        _atomic_write(staging_dir / "summary.json", json.dumps(enum_json(summary), sort_keys=True, indent=2) + "\n")
        equity_rows = getattr(engine, "equity_curve", [])
        columns = ("timestamp", "balance", "equity", "used_margin", "free_margin", "unrealized_pnl")
        csv_lines = [",".join(columns)]
        for row in equity_rows:
            csv_lines.append(",".join(str(row.get(column, "")) for column in columns))
        _atomic_write(staging_dir / "equity.csv", "\n".join(csv_lines) + "\n")
        missing = [name for name in REQUIRED_RESULT_FILES if not (staging_dir / name).exists()]
        if missing:
            raise HistoricalExecutionError(f"result bundle is incomplete: {missing}")
        os.replace(staging_dir, result_dir)
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
    return result_dir


def normalized_bundle_hash(result_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in REQUIRED_RESULT_FILES:
        digest.update(name.encode("utf-8"))
        digest.update((Path(result_dir) / name).read_bytes())
    return digest.hexdigest()
