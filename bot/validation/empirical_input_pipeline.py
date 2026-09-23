"""Phase 8N-I — plan-bound empirical input pipeline for development cells.

Resolves every empirical input exclusively from the frozen corrected plan and
the identity-verified Phase 8 evidence packages (never from directory
scanning or caller-supplied paths), then streams deterministic typed events
for one fold-scenario cell:

    M5 completion -> strategy decision (shared Phase 8N adapter)
    -> eligible intent -> Phase 3 lifecycle entry/management on later
    executable quotes (parity-tested `bot.backtesting.adapters` glue)
    -> Phase 7 `HistoricalExecutionEngine` ledger with Phase 8H cost and
    8L metadata overlays.

Classifications are frozen in code and mirror the 8H/8L contracts:
spread OBSERVED_EMPIRICAL, commission BROKER_SUPPORT_ASSERTED (NONE),
swap ASSUMPTION_ONLY scenario ladder, slippage ASSUMPTION_ONLY ladder,
current metadata CURRENT_ONLY_NOT_HISTORICAL.

This module imports no broker terminal SDK, no network providers, no
account/order APIs and no credentials.  It publishes no performance numbers;
the structural canary stops before any strategy metric is produced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

import pandas as pd

from bot.backtesting import (
    BrokerSymbolMetadata,
    CommissionKind,
    CommissionSchedule,
    CostSource,
    HistoricalExecutionEngine,
    HistoricalExecutionPolicy,
    HistoricalQuote,
    LedgerEventType,
    LedgerEntry,
    FidelityClass,
    RunMode,
    Side,
    SimulatedFill,
    SlippageKind,
    SlippageModel,
    SwapCalculation,
    SwapSchedule,
)
from bot.backtesting.adapters import (
    lifecycle_stable_id,
    manage_quote_position,
    process_quote_entry,
)
from bot.execution.lifecycle.entry import create_entry_state, EntryState
from bot.backtesting.fill_journal import HistoricalFillJournal
from bot.execution.lifecycle.entry import create_entry_state
from bot.execution.lifecycle.management import ManagementConfig
from bot.execution.lifecycle.models import (
    Direction,
    EntryIntent,
    LifecycleStatus,
    MarketEventKind,
    PositionState,
    TERMINAL_STATUSES as _TERMINAL_LIFECYCLE_STATUSES,
)
from bot.execution.lifecycle.serialization import (
    entry_intent_from_payload,
    position_from_payload,
    position_to_payload,
)
from bot.validation.models import canonical_data, canonical_hash
from bot.execution.risk.models import RiskPolicy
from bot.strategy.config import StrategyConfig
from bot.strategy.setup_intent import SetupSymbolMetadata
from bot.strategy.setup_recovery import SetupRecoveryCoordinator
from bot.strategy.setup_state import (
    SetupStateRecord,
    record_from_state,
    state_from_record,
)
from bot.strategy.setup_store import SetupReplayStore
from bot.utils.session_clock import get_session_context
from bot.validation import historical_news_replay
from bot.validation.empirical_strategy_adapter import (
    evaluate_historical_orchestration,
    evaluate_setup_inputs,
)
from bot.data.candles import TIMEFRAMES
from strategies.smc_engine.strategy_state import StrategyState

UTC = timezone.utc

PIPELINE_SCHEMA = "phase8n.empirical-input-pipeline.v1"
PIPELINE_LABEL = "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE"
CANARY_LABEL = "EMPIRICAL PIPELINE STRUCTURAL CANARY — NOT STRATEGY EVIDENCE"

DECISION_TIMEFRAME = "M5"
"""Frozen base decision timeframe of the candidate (entry_tf = M5)."""

EXECUTION_LOT_CAP = 0.01
"""Development proxy volume: the smallest executable step of the account.

Deterministic, outcome-independent, and maximally conservative: no
position-sizing model is preregistered, so every development fill uses the
minimum volume (0.01 lots) rather than an invented sizing curve.
"""

ROLLOVER_TIME_UTC = dt_time(22, 0)
"""Exness server midnight rollover expressed in UTC (GMT+2 server time).

The support transcript established market execution and the triple-Wednesday
rule but not the rollover instant; the platform convention for Exness server
time (midnight server = 22:00 UTC during 2024) is a documented proxy, and the
Wednesday-triple behaviour is invariant to the exact hour within the server
day.  Classified CURRENT_ONLY_NOT_HISTORICAL (platform convention).
"""

TRIPLE_SWAP_WEEKDAY = 2  # Wednesday (Monday=0); broker-support asserted.

SYMBOL_SESSIONS_UTC = ((0, 24),)
"""XAUUSD trades the full UTC day in 2024 (weekday market sessions only).

The support transcript did not supply an official daytime/nighttime session
table; the 24h quoted-session convention is platform-observed (screenshot:
visible current trading sessions) and the daytime/nighttime volume split is
recorded as a limitation, not encoded as a hard gate.
"""

FROZEN_MIN_RR = 3.0
"""From the frozen RiskPolicy min_rr boundary (no tuning)."""


class EmpiricalPipelineError(RuntimeError):
    """Raised when an empirical input or event stream violates the plan."""


# ---------------------------------------------------------------------------
# Frozen broker metadata (one builder, bound to evidence)
# ---------------------------------------------------------------------------


def broker_symbol_metadata(
    cost_policy_content: Mapping[str, Any], *, swap_scenario: Mapping[str, Any]
) -> BrokerSymbolMetadata:
    """Build the frozen XAUUSDm development metadata for one swap scenario.

    Every numeric constant is bound to evidence or a documented proxy:
    digits/point/tick from the Phase 8G metadata contract (0.001 point,
    0.01 pip, one 0.001 point on one lot = 0.10 USD), contract size 100 oz
    broker-support asserted, volumes/margin from the 8L baseline, commission
    NONE from the support evidence, swap rates from the requested 8H
    scenario (ASSUMPTION_ONLY).
    """
    swap = cost_policy_content["cost_components"]["swap"]
    commission = cost_policy_content["cost_components"]["commission"]
    if commission["mode"] != "NONE":
        raise EmpiricalPipelineError("cost policy commission must be NONE")
    if swap_scenario["scenario_id"] not in {
        item["scenario_id"] for item in cost_policy_content["swap_scenarios"]
    }:
        raise EmpiricalPipelineError("swap scenario is not part of the frozen policy")
    return BrokerSymbolMetadata(
        symbol="XAUUSDm",
        version="phase8n-development-proxy-v1",
        broker_source="exness-standard-mt5-support-evidence",
        effective_from=datetime(2024, 1, 1, tzinfo=UTC),
        effective_to=None,
        digits=3,
        point_size=0.001,
        tick_size=0.001,
        tick_value=0.10,
        contract_size=100.0,
        volume_min=0.01,
        volume_max=200.0,
        volume_step=0.01,
        account_currency="USD",
        profit_currency="USD",
        margin_currency="USD",
        margin_rate=0.005,
        commission=CommissionSchedule(
            kind=CommissionKind.PER_LOT_PER_SIDE,
            amount=0.0,
            currency="USD",
            source=CostSource.ASSUMED,
        ),
        swap=SwapSchedule(
            calculation=SwapCalculation.ACCOUNT_CURRENCY_PER_LOT,
            long_rate=float(swap_scenario["long_usd_per_lot_per_day"]),
            short_rate=float(swap_scenario["short_usd_per_lot_per_day"]),
            rollover_time=ROLLOVER_TIME_UTC,
            rollover_timezone="UTC",
            triple_swap_weekday=TRIPLE_SWAP_WEEKDAY,
            source=CostSource.ASSUMED,
        ),
        provenance=f"8G contract + support evidence; swap basis {swap['basis']}",
    )


def slippage_model_for(
    policy_content: Mapping[str, Any], *, slippage_scenario_id: str
) -> SlippageModel:
    scenario = next(
        (item for item in policy_content["slippage_scenarios"]
         if item["scenario_id"] == slippage_scenario_id),
        None,
    )
    if scenario is None:
        raise EmpiricalPipelineError("unregistered slippage scenario")
    if scenario["kind"] == "FIXED_ADVERSE_POINTS":
        return SlippageModel(
            kind=SlippageKind.FIXED_ADVERSE_POINTS,
            points=float(scenario["points"]),
            source=CostSource.ASSUMED,
        )
    raise EmpiricalPipelineError("unsupported slippage kind")


# ---------------------------------------------------------------------------
# Typed immutable resolver (plan/evidence-registry driven only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmpiricalInputBindings:
    """Immutable resolution of every empirical input for the corrected plan.

    Resolution starts from the plan's own input-readiness block (already
    hash-verified by the Phase 8M firewall); this resolver then binds the
    exact filesystem locations that the plan's identities select and re-reads
    manifests/completions before first use.  No input is inferred from
    directory scanning, and no caller path can substitute a bound input.
    """

    plan: Mapping[str, Any]
    evidence_root: Path
    tick_year_root: Path
    monthly_roots: tuple[Path, ...]
    candle_root: Path
    dxy_root: Path
    news_package: Mapping[str, Any]
    news_snapshot: historical_news_replay.HistoricalNewsReplaySnapshot
    spread_binding: Mapping[str, Any]
    cost_policy_package_id: str
    cost_policy_content: Mapping[str, Any]
    metadata_bounds_package_id: str
    metadata_bounds_content: Mapping[str, Any]
    readiness: Mapping[str, Any]
    contingency: str = field(default="REFUSE_SYNTHETIC_SUBSTITUTION")

    @property
    def swap_scenarios(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.cost_policy_content["swap_scenarios"])


def resolve_input_bindings(
    *,
    evidence_root: Path,
    worktree: Path,
    contamination_path: Path,
    plan: Mapping[str, Any],
    tick_verification_depth: str = "identity-chain",
    fingerprint_contract: str = "legacy_worktree_bytes_v0",
    research_identity: str | None = None,
    variant_id: str | None = None,
    canonical_commit: str | None = None,
    cost_policy_attestation: Mapping[str, Any] | None = None,
) -> EmpiricalInputBindings:
    """Resolve and verify every empirical input through the frozen registry.

    The default binding contract is the historical
    ``legacy_worktree_bytes_v0`` execution-model verification.  V2 callers
    must explicitly pass ``fingerprint_contract="canonical_git_blob_v1"``
    together with the V2 research context and a compatibility attestation;
    there is no automatic fallback, and unknown contracts fail closed.
    """
    # Imported lazily to keep the import graph acyclic for tests.
    from bot.validation.development_evaluation_plan import (  # noqa: PLC0415
        METADATA_POLICY_ID,
        OFFICIAL_NEWS_ID,
        OBSERVED_SPREAD_ID,
        _load_evidence,
        verify_input_readiness,
        verify_input_readiness_prospective,
    )

    if fingerprint_contract == "canonical_git_blob_v1":
        readiness = verify_input_readiness_prospective(
            data_root=Path(evidence_root).parent,
            worktree=Path(worktree),
            contamination_path=Path(contamination_path),
            tick_verification_depth=tick_verification_depth,
            research_identity=str(research_identity),
            variant_id=str(variant_id),
            fingerprint_contract=fingerprint_contract,
            canonical_commit=str(canonical_commit),
            attestation=dict(cost_policy_attestation or {}),
        )
    elif fingerprint_contract == "legacy_worktree_bytes_v0":
        if any((research_identity, variant_id, canonical_commit, cost_policy_attestation)):
            raise EmpiricalPipelineError(
                "legacy binding contract must not carry prospective V2 context"
        )
        readiness = verify_input_readiness(
            data_root=Path(evidence_root).parent,
            worktree=Path(worktree),
            contamination_path=Path(contamination_path),
            tick_verification_depth=tick_verification_depth,
        )
    else:
        raise EmpiricalPipelineError(
            f"unknown fingerprint contract: {fingerprint_contract!r}"
        )
    bound_readiness = plan.get("input_readiness", {})
    if bound_readiness.get("ticks", {}).get("canonical_sha256") != readiness["ticks"]["canonical_sha256"]:
        raise EmpiricalPipelineError("plan tick identity does not match the verified registry")
    if bound_readiness.get("cost_policy", {}).get("policy_fingerprint") != readiness["cost_policy"]["policy_fingerprint"]:
        raise EmpiricalPipelineError("plan cost policy is not the frozen 8H policy")

    data_root = Path(evidence_root).parent
    year_root = data_root / "exness-tick-history" / "processed" / "year-packages" / "exness-xauusdm-2024-development-b2a0234a470dd397"
    completion = json.loads((year_root / "package.complete.json").read_text(encoding="utf-8"))
    year_manifest = json.loads((year_root / str(completion["manifest_relative_path"])).read_text(encoding="utf-8"))
    monthly_ids = [str(item["package_id"]) for item in year_manifest["monthly_packages"]]
    packages_root = data_root / "exness-tick-history" / "processed" / "packages"
    monthly_roots = tuple(packages_root / package_id for package_id in monthly_ids)

    candle_root = data_root / "derived" / "derived-candles-2024-v1-20260911T195553Z"
    dxy_root = data_root / "dxy" / "dxy-development-2024-v1-20260912T091410.712364Z"
    for path in (year_root, candle_root, dxy_root, *monthly_roots):
        if not path.is_dir():
            raise EmpiricalPipelineError(f"bound empirical input is missing on disk: {path.name}")

    news = _load_evidence(Path(evidence_root), OFFICIAL_NEWS_ID, "official_news")
    spread = _load_evidence(Path(evidence_root), OBSERVED_SPREAD_ID, "observed_spread")
    cost = _load_evidence(Path(evidence_root), readiness["cost_policy"]["package_id"], "development_cost_policy")
    metadata = _load_evidence(Path(evidence_root), METADATA_POLICY_ID, "development_metadata_bounds")

    news_snapshot = historical_news_replay.build_historical_news_snapshot(
        news["content"],
        package_id=OFFICIAL_NEWS_ID,
        expected_content_sha256=str(news["manifest"]["content_canonical_sha256"]),
    )

    return EmpiricalInputBindings(
        plan=plan,
        evidence_root=Path(evidence_root),
        tick_year_root=year_root,
        monthly_roots=monthly_roots,
        candle_root=candle_root,
        dxy_root=dxy_root,
        news_package=news,
        news_snapshot=news_snapshot,
        spread_binding=spread["manifest"],
        cost_policy_package_id=str(readiness["cost_policy"]["package_id"]),
        cost_policy_content=cost["content"],
        metadata_bounds_package_id=str(readiness["metadata_bounds"]["package_id"]),
        metadata_bounds_content=metadata["content"],
        readiness=readiness,
    )


# ---------------------------------------------------------------------------
# Bounded candle/DXY materialization
# ---------------------------------------------------------------------------


def _normalize_candle_frame(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Convert one derived-candle partition slice into adapter normal form."""
    normalized = pd.DataFrame({
        "open_time": pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True),
        "available_at": pd.to_datetime(frame["available_at_ms"], unit="ms", utc=True),
        "time": pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True),
        "open": frame["bid_open"].astype(float),
        "high": frame["bid_high"].astype(float),
        "low": frame["bid_low"].astype(float),
        "close": frame["bid_close"].astype(float),
        "tick_volume": frame["tick_count"].astype(float),
        "spread": frame["spread_median"].astype(float) / 10.0,
        "real_volume": 0.0,
        "timeframe": timeframe,
    })
    normalized.attrs["causal_normalized"] = True
    return normalized


def _normalize_constituent_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = pd.DataFrame({
        "open_time": pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True),
        "available_at": pd.to_datetime(frame["available_at_ms"], unit="ms", utc=True),
        "time": pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True),
        "open": frame["open"].astype(float),
        "high": frame["high"].astype(float),
        "low": frame["low"].astype(float),
        "close": frame["close"].astype(float),
        "tick_volume": frame["tick_volume"].astype(float),
        "spread": frame["spread"].astype(float),
        "real_volume": frame["real_volume"].astype(float),
        "timeframe": "H1",
    })
    normalized.attrs["causal_normalized"] = True
    return normalized


def _load_timeframe_slice(
    candle_root: Path, timeframe: str, start_ms: int, end_ms: int
) -> pd.DataFrame:
    """Read only yearly-partition rows overlapping [start, end) — bounded."""
    partition = candle_root / "candles" / "XAUUSDm" / timeframe / "year=2024" / "part-00000.parquet"
    if not partition.is_file():
        raise EmpiricalPipelineError(f"derived candle partition missing for {timeframe}")
    frame = pd.read_parquet(
        partition,
        columns=[
            "open_time_ms", "close_time_ms", "available_at_ms",
            "bid_open", "bid_high", "bid_low", "bid_close",
            "tick_count", "spread_median",
        ],
    )
    # Availability-window selection: keep candles whose availability window
    # intersects [start, end).  OHLC is never forward-filled across gaps —
    # missing windows simply stay missing (insufficient history raises).
    selected = frame[(frame["available_at_ms"] >= start_ms) & (frame["open_time_ms"] < end_ms)]
    del frame
    return _normalize_candle_frame(selected, timeframe)


def materialize_candle_frames(
    bindings: EmpiricalInputBindings, *, start_ms: int, end_ms: int
) -> dict[str, pd.DataFrame]:
    """Load the decision-required candle frames for one bounded interval."""
    frames = {
        timeframe: _load_timeframe_slice(bindings.candle_root, timeframe, start_ms, end_ms)
        for timeframe in ("M5", "M15", "H1", "H4", "D1", "W1")
    }
    for timeframe, frame in frames.items():
        opens = frame["open_time"].tolist()
        if opens != sorted(opens) or len(set(opens)) != len(opens):
            raise EmpiricalPipelineError(f"candle ordering violation for {timeframe}")
        if (frame["available_at"] <= frame["open_time"]).any():
            raise EmpiricalPipelineError(f"candle availability violation for {timeframe}")
    return frames


def materialize_constituent_frames(
    bindings: EmpiricalInputBindings, *, start_ms: int, end_ms: int
) -> dict[str, pd.DataFrame]:
    """Load the six causally aligned DXY constituent frames."""
    constituents = ("EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF")
    frames: dict[str, pd.DataFrame] = {}
    for symbol in constituents:
        partition = bindings.dxy_root / "constituents" / f"{symbol.lower()}-h1-2024.parquet"
        if not partition.is_file():
            raise EmpiricalPipelineError(f"DXY constituent partition missing: {symbol}")
        frame = pd.read_parquet(
            partition,
            columns=[
                "open_time_ms", "available_at_ms", "open", "high", "low", "close",
                "tick_volume", "spread", "real_volume",
            ],
        )
        selected = frame[(frame["available_at_ms"] >= start_ms) & (frame["open_time_ms"] < end_ms)]
        # The live DXY basket addresses constituents by their broker symbol
        # (EURUSDm, USDJPYm, ...); the derived packages record that mapping
        # authoritatively, so frames are keyed exactly as production expects.
        broker = pd.read_parquet(partition, columns=["broker_symbol"])
        broker_values = broker["broker_symbol"].astype(str).unique()
        if len(broker_values) != 1:
            raise EmpiricalPipelineError(f"ambiguous broker symbol in {partition.name}")
        frames[str(broker_values[0])] = _normalize_constituent_frame(selected)
    return frames


def news_context_for(
    bindings: EmpiricalInputBindings, decision_at: datetime, config: StrategyConfig
) -> dict[str, Any]:
    """Development-only historical news translation through the shared veto."""
    decision = historical_news_replay.evaluate_historical_news_decision(
        bindings.news_snapshot, decision_at, config,
    )
    safety = decision.safety
    return {
        "symbol": "XAUUSDm",
        "news_clear": safety.state.value == "CLEAR",
        "state": safety.state.value,
        "reason": safety.reason,
        "source": decision.package_id,
        "active_event_ids": list(safety.event_ids),
        "provenance": "DEVELOPMENT_EVENT_TIME_VETO_ONLY",
    }


# ---------------------------------------------------------------------------
# Deterministic event stream (bounded, chronological, causal)
# ---------------------------------------------------------------------------

DEVELOPMENT_START_MS = 1704067200000
"""2024-01-01T00:00:00Z in epoch milliseconds (leap year)."""

DEVELOPMENT_END_MS = 1735689600000
"""Exclusive 2025-01-01T00:00:00Z in epoch milliseconds."""


def _monthly_tick_partitions(monthly_root: Path) -> list[Path]:
    packages = (
        sorted(monthly_root.glob("ticks/**/*.parquet"))
        or sorted(monthly_root.glob("partitions/*.parquet"))
        or sorted(monthly_root.glob("*.parquet"))
    )
    if not packages:
        raise EmpiricalPipelineError(f"no tick partitions found under {monthly_root.name}")
    return packages


def iter_month_ticks(
    monthly_root: Path, *, start_ms: int, end_ms: int
) -> Iterator[dict[str, Any]]:
    """Stream one monthly tick partition in row-group batches (bounded memory)."""
    import pyarrow.parquet as pq  # noqa: PLC0415

    # `source_member` is the real monthly-package column naming the source
    # chunk/member; `row_identity` is the per-row hash identity. Both are read
    # when present so synthetic rehearsal fixtures and real packages share the
    # streaming path.
    columns = ["time_msc", "bid", "ask", "sequence_id", "provenance_id", "source_member", "row_identity"]
    for package in _monthly_tick_partitions(monthly_root):
        parquet = pq.ParquetFile(package)
        for batch_index in range(parquet.num_row_groups):
            table = parquet.read_row_group(batch_index, columns=columns)
            data = table.to_pydict()
            bids = data["bid"]
            asks = data["ask"]
            for offset, time_msc in enumerate(data["time_msc"]):
                moment = int(time_msc)
                if moment < start_ms:
                    continue
                if moment >= end_ms:
                    return
                yield {
                    "timestamp_ms": moment,
                    "bid": float(bids[offset]),
                    "ask": float(asks[offset]),
                    "sequence_id": str(data["sequence_id"][offset]),
                    "provenance_id": str(data["provenance_id"][offset]),
                    "source_chunk_id": str(data["source_member"][offset]),
                    "row_identity": str(data["row_identity"][offset]),
                    "month_package": monthly_root.name,
                }


def _candle_completion_events(
    candle_root: Path, *, decision_timeframe: str, start_ms: int, end_ms: int
) -> list[tuple[int, int, str, float, str]]:
    """M5 completions in [start, end): (available_at, open_time, tf, close, id)."""
    frame = pd.read_parquet(
        candle_root / "candles" / "XAUUSDm" / decision_timeframe / "year=2024" / "part-00000.parquet",
        columns=["open_time_ms", "available_at_ms", "bid_close", "candle_identity"],
    )
    selected = frame[
        (frame["available_at_ms"] >= start_ms) & (frame["available_at_ms"] < end_ms)
    ]
    events = [
        (
            int(row.available_at_ms), int(row.open_time_ms), decision_timeframe,
            float(row.bid_close), str(row.candle_identity),
        )
        for row in selected.itertuples(index=False)
    ]
    events.sort()
    return events


def empirical_event_stream(
    bindings: EmpiricalInputBindings,
    fold: Mapping[str, Any],
    *,
    canary: bool = False,
    canary_tick_limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Merge M5 completion decisions and executable quotes chronologically.

    Deterministic merge order: (timestamp_ms, decision-before-quote, stable
    id).  Decision events fire exactly when the M5 candle becomes available
    (`available_at` == decision time — never on the signal candle's own
    ticks); quotes are the later executable bid/ask ticks.  The interval is
    the fold's evaluation window; warm-up history is materialized separately.
    No timestamp at or after 2025-01-01 can be produced: the window filter
    clamps to the development period and the datasets are development-only.
    """
    eval_start = int(pd.Timestamp(fold["evaluation"]["start"]).value // 1_000_000)
    eval_end = min(
        int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000),
        DEVELOPMENT_END_MS,
    )
    if eval_start < DEVELOPMENT_START_MS:
        raise EmpiricalPipelineError("fold evaluation interval precedes the development period")
    if eval_start >= eval_end:
        raise EmpiricalPipelineError("fold evaluation interval is empty")

    decisions = iter(
        _candle_completion_events(
            bindings.candle_root, decision_timeframe=DECISION_TIMEFRAME,
            start_ms=eval_start, end_ms=eval_end,
        )
    )

    def quote_iterator() -> Iterator[dict[str, Any]]:
        emitted = 0
        for monthly_root in bindings.monthly_roots:
            for tick in iter_month_ticks(monthly_root, start_ms=eval_start, end_ms=eval_end):
                yield tick
                emitted += 1
                if canary and canary_tick_limit is not None and emitted >= canary_tick_limit:
                    return

    quotes = quote_iterator()
    pending_decision = next(decisions, None)
    pending_quote = next(quotes, None)
    while pending_decision is not None or pending_quote is not None:
        decision_key = (pending_decision[0], 0, "") if pending_decision else None
        quote_key = (pending_quote["timestamp_ms"], 1, pending_quote["sequence_id"]) if pending_quote else None
        if decision_key is not None and (quote_key is None or decision_key <= quote_key):
            available_at_ms, open_time_ms, timeframe, close, identity = pending_decision
            yield {
                "event_kind": "DECISION",
                "timestamp_ms": available_at_ms,
                "decision_for_open_ms": open_time_ms,
                "timeframe": timeframe,
                "source_close": close,
                "candle_identity": identity,
                "event_id": f"decision:{identity}",
            }
            pending_decision = next(decisions, None)
        else:
            yield {**pending_quote, "event_kind": "QUOTE", "event_id": f"quote:{pending_quote['sequence_id']}"}
            pending_quote = next(quotes, None)


# ---------------------------------------------------------------------------
# Cell execution (shared production contracts only)
# ---------------------------------------------------------------------------


class CellExecutionContext:
    """Per-cell state: engine, setup store, decision history, cursors."""

    def __init__(
        self, *, cell: Mapping[str, Any], fold: Mapping[str, Any],
        scenario: Mapping[str, Any], bindings: EmpiricalInputBindings,
        cell_dir: Path,
    ) -> None:
        self.cell = dict(cell)
        self.fold = dict(fold)
        self.scenario = dict(scenario)
        self.bindings = bindings
        self.cell_dir = Path(cell_dir)
        cost = bindings.cost_policy_content
        swap_scenario = next(
            item for item in cost["swap_scenarios"]
            if item["scenario_id"] == cell["cost_overlay_ids"][0]
        )
        self.swap_scenario = dict(swap_scenario)
        self.slippage_scenario_id = str(cell["cost_overlay_ids"][1])
        metadata_scenario = next(
            item for item in bindings.metadata_bounds_content["mandatory_scenarios"]
            if item["scenario_id"] == cell["metadata_overlay_id"]
        )
        self.metadata_scenario = dict(metadata_scenario)
        self.metadata = broker_symbol_metadata(cost, swap_scenario=swap_scenario)
        self.engine = HistoricalExecutionEngine(
            run_id=str(cell["cell_id"]),
            metadata=self.metadata,
            policy=HistoricalExecutionPolicy(
                mode=RunMode.DIAGNOSTIC,
                fidelity=FidelityClass.TICK_BID_ASK,
                maximum_spread_points=1_000_000_000.0,
                slippage=slippage_model_for(cost, slippage_scenario_id=self.slippage_scenario_id),
            ),
            initial_balance=10_000.0,
        )
        self.strategy_config = StrategyConfig()
        self.risk_policy = RiskPolicy()
        self.max_concurrent_trades = 2
        self.decisions: list[dict[str, Any]] = []
        self.rejections: list[dict[str, Any]] = []
        self.equity_points: list[dict[str, Any]] = []
        self.last_session_hour: int | None = None
        self.pending_intents: list[dict[str, Any]] = []
        self.lifecycle_positions: dict[str, PositionState] = {}
        self.consumed_event_keys: set[str] = set()
        self.state_record: SetupStateRecord = record_from_state(
            StrategyState(event_time=datetime(2024, 1, 1, tzinfo=UTC)),
            event_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        # Durable, parity-tested shared stores (file-backed under cell_dir).
        self.fill_journal = HistoricalFillJournal(self.cell_dir / "fill-journal")
        self.setup_store = SetupReplayStore(
            self.cell_dir / "setup-state.json", identity=str(cell["resume_identity"])
        )
        self.recovery = SetupRecoveryCoordinator(self.setup_store, self.fill_journal.snapshot)
        self.setup_store_initialized = False
        # Deterministic quote-event sequence counter (checkpointed).
        self.quote_sequence = 0


def serialize_cell_state(context: CellExecutionContext) -> dict[str, Any]:
    """Checkpoint payload: engine, ledger, strategy record, cursors.

    The engine, setup store and fill journal are durably file-backed and are
    re-loaded (not serialized) on resume; only derived counters, the pending
    (unfilled) entry intents and cursor identities are checkpointed.
    """
    from bot.execution.lifecycle.serialization import entry_intent_to_payload  # noqa: PLC0415

    engine = context.engine
    return {
        "schema": PIPELINE_SCHEMA,
        "cell_id": context.cell["cell_id"],
        "resume_identity": context.cell["resume_identity"],
        "decisions_count": len(context.decisions),
        "rejections_count": len(context.rejections),
        "equity_points_count": len(context.equity_points),
        "last_session_hour": context.last_session_hour,
        "consumed_event_keys": sorted(context.consumed_event_keys),
        "pending_intents": [
            {
                "intent": entry_intent_to_payload(pending["intent"]),
                "state_status": pending["state"].status.value,
                "decision_id": pending["decision_id"],
            }
            for pending in context.pending_intents
        ],
        "setup_store_initialized": context.setup_store_initialized,
        "engine_balance": engine.account.balance,
        "ledger_length": len(engine.ledger),
        "fills_length": len(engine.fills),
        "processed_action_id_count": len(engine.processed_action_ids),
        # Exact engine/lifecycle state so a resumed cell produces the same
        # normalized output as an uninterrupted run (no duplicated fills,
        # P&L, commission, swap or outcomes).  canonical_data serializes the
        # frozen dataclasses; identity is re-validated on restore.
        "engine_account": {
            key: getattr(engine.account, key) for key in (
                "initial_balance", "balance", "equity", "used_margin",
                "free_margin", "realized_gross_pnl", "commission", "swap",
                "unrealized_pnl", "high_water_equity",
            )
        },
        "engine_open_positions": [
            canonical_data(position) for position in engine.positions.values()
        ],
        # Fills and ledger are rebuilt on resume (lengths alone cannot rebuild
        # a fresh context).  canonical_data round-trips the frozen dataclasses
        # exactly; restore re-validates identity before appending.
        "engine_fills": [canonical_data(fill) for fill in engine.fills],
        "engine_ledger": [canonical_data(entry) for entry in engine.ledger],
        "processed_action_ids": sorted(engine.processed_action_ids),
        "last_event_time": (
            engine.last_event_time.isoformat() if engine.last_event_time else None
        ),
        "lifecycle_positions": {
            trade_id: position_to_payload(position)
            for trade_id, position in context.lifecycle_positions.items()
        },
        "handler_sequence": context.quote_sequence,
    }


def restore_cell_state(context: CellExecutionContext, snapshot: Mapping[str, Any]) -> None:
    """Verify and restore a snapshot produced by serialize_cell_state."""
    if snapshot.get("schema") != PIPELINE_SCHEMA:
        raise EmpiricalPipelineError("checkpoint state schema mismatch")
    if snapshot.get("cell_id") != context.cell["cell_id"] or snapshot.get("resume_identity") != context.cell["resume_identity"]:
        raise EmpiricalPipelineError("checkpoint belongs to a different cell")
    if snapshot.get("setup_store_initialized"):
        loaded = context.setup_store.load()
        context.setup_store_initialized = True
        record = loaded
    else:
        record = record_from_state(
            StrategyState(event_time=datetime(2024, 1, 1, tzinfo=UTC)),
            event_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
    context.state_record = record
    context.decisions = [None] * int(snapshot["decisions_count"])
    context.rejections = [None] * int(snapshot["rejections_count"])
    context.equity_points = [None] * int(snapshot["equity_points_count"])
    context.last_session_hour = snapshot["last_session_hour"]
    context.consumed_event_keys = set(snapshot.get("consumed_event_keys", ()))
    context.pending_intents = [
        {
            "intent": entry_intent_from_payload(pending["intent"]),
            "state": create_entry_state(entry_intent_from_payload(pending["intent"])),
            "decision_id": pending["decision_id"],
        }
        for pending in snapshot.get("pending_intents", ())
    ]
    engine = context.engine
    account = snapshot.get("engine_account")
    if account is not None:
        from bot.backtesting.models import HistoricalAccountState  # noqa: PLC0415

        restored = HistoricalAccountState(
            initial_balance=float(account["initial_balance"]),
            balance=float(account["balance"]),
            equity=float(account["equity"]),
            used_margin=float(account["used_margin"]),
            free_margin=float(account["free_margin"]),
            realized_gross_pnl=float(account["realized_gross_pnl"]),
            commission=float(account["commission"]),
            swap=float(account["swap"]),
            unrealized_pnl=float(account["unrealized_pnl"]),
            high_water_equity=float(account["high_water_equity"]),
        )
        engine.account = restored
    restored_positions = {}
    for position_payload in snapshot.get("engine_open_positions", ()):
        position = _position_from_serialized(position_payload)
        restored_positions[position.position_id] = position
    engine.positions = restored_positions
    engine.fills = [
        _fill_from_serialized(fill_payload)
        for fill_payload in snapshot.get("engine_fills", ())
    ]
    engine.ledger = [
        _ledger_entry_from_serialized(entry_payload)
        for entry_payload in snapshot.get("engine_ledger", ())
    ]
    engine.processed_action_ids = {
        str(action_id) for action_id in snapshot.get("processed_action_ids", ())
    }
    last_event_time = snapshot.get("last_event_time")
    engine.last_event_time = (
        datetime.fromisoformat(last_event_time) if last_event_time else None
    )
    context.lifecycle_positions = {
        trade_id: position_from_payload(payload)
        for trade_id, payload in snapshot.get("lifecycle_positions", {}).items()
    }
    context.quote_sequence = int(snapshot.get("handler_sequence", 0))


def _fill_from_serialized(payload: Mapping[str, Any]) -> "SimulatedFill":
    """Rebuild one engine fill from its canonical snapshot payload."""
    from bot.backtesting.models import FidelityClass, Side  # noqa: PLC0415

    return SimulatedFill(
        fill_id=str(payload["fill_id"]),
        action_id=str(payload["action_id"]),
        trade_id=str(payload["trade_id"]),
        position_id=str(payload["position_id"]),
        timestamp=datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00")),
        symbol=str(payload["symbol"]),
        side=Side(str(payload["side"])),
        volume=float(payload["volume"]),
        reference_price=float(payload["reference_price"]),
        executable_quote=float(payload["executable_quote"]),
        fill_price=float(payload["fill_price"]),
        slippage_price=float(payload["slippage_price"]),
        spread_price=float(payload["spread_price"]),
        partial=bool(payload["partial"]),
        reason_code=str(payload["reason_code"]),
        fidelity=FidelityClass(str(payload["fidelity"])),
    )


def _ledger_entry_from_serialized(payload: Mapping[str, Any]) -> "LedgerEntry":
    """Rebuild one ledger entry from its canonical snapshot payload."""
    from bot.backtesting.models import FidelityClass, Side  # noqa: PLC0415

    side = payload.get("side")
    return LedgerEntry(
        ledger_id=str(payload["ledger_id"]),
        run_id=str(payload["run_id"]),
        trade_id=(str(payload["trade_id"]) if payload.get("trade_id") is not None else None),
        position_id=(str(payload["position_id"]) if payload.get("position_id") is not None else None),
        action_id=str(payload["action_id"]),
        timestamp=datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00")),
        event_type=LedgerEventType(str(payload["event_type"])),
        symbol=str(payload["symbol"]),
        side=(Side(str(side)) if side is not None else None),
        volume=float(payload["volume"]),
        reference_price=(
            float(payload["reference_price"]) if payload.get("reference_price") is not None else None
        ),
        executable_quote=(
            float(payload["executable_quote"]) if payload.get("executable_quote") is not None else None
        ),
        fill_price=(float(payload["fill_price"]) if payload.get("fill_price") is not None else None),
        gross_price_pnl=float(payload["gross_price_pnl"]),
        spread_attribution=float(payload["spread_attribution"]),
        slippage_attribution=float(payload["slippage_attribution"]),
        commission=float(payload["commission"]),
        swap=float(payload["swap"]),
        net_cash_change=float(payload["net_cash_change"]),
        balance_after=float(payload["balance_after"]),
        equity_after=float(payload["equity_after"]),
        provenance=str(payload["provenance"]),
        fidelity=FidelityClass(str(payload["fidelity"])),
    )


def _position_from_serialized(payload: Mapping[str, Any]) -> "HistoricalPosition":
    """Rebuild one engine position from its canonical snapshot payload."""
    from bot.backtesting.models import HistoricalPosition, Side  # noqa: PLC0415

    return HistoricalPosition(
        position_id=str(payload["position_id"]),
        trade_id=str(payload["trade_id"]),
        symbol=str(payload["symbol"]),
        direction=Side(str(payload["direction"])),
        opened_at=datetime.fromisoformat(str(payload["opened_at"]).replace("Z", "+00:00")),
        entry_price=float(payload["entry_price"]),
        initial_volume=float(payload["initial_volume"]),
        remaining_volume=float(payload["remaining_volume"]),
        stop_price=float(payload["stop_price"]),
        target_price=float(payload["target_price"]),
        last_swap_at=datetime.fromisoformat(str(payload["last_swap_at"]).replace("Z", "+00:00")),
        closed_at=(
            datetime.fromisoformat(str(payload["closed_at"]).replace("Z", "+00:00"))
            if payload.get("closed_at") is not None else None
        ),
    )


class CellEventHandler:
    """Dispatches DECISION/QUOTE events for one cell through shared contracts."""

    def __init__(
        self, context: CellExecutionContext, *,
        candle_frames: Mapping[str, pd.DataFrame],
        constituent_frames: Mapping[str, pd.DataFrame],
        quantity: float = EXECUTION_LOT_CAP,
    ) -> None:
        self.context = context
        self.candle_frames = dict(candle_frames)
        self.constituent_frames = dict(constituent_frames)
        self.quantity = float(quantity)
        # Deterministic sequence counter lives on the (checkpointed) context.
        self.sequence = 0

    # -- decision path -----------------------------------------------------
    def on_signal(self, event: Mapping[str, Any]) -> None:
        from bot.data.candles import causal_snapshot  # noqa: PLC0415
        from bot.analysis.bias_engine import (  # noqa: PLC0415
            DEFAULT_BARS, bias_snapshot_from_frames, resolve_trade_bias,
        )
        from bot.analysis.liquidity_map import build_liquidity_map_from_frames  # noqa: PLC0415
        from bot.state.gate_inputs import build_gate_inputs  # noqa: PLC0415
        from bot.validation.empirical_strategy_adapter import prepare_dxy_context  # noqa: PLC0415
        from config.symbol_profiles import get_symbol_profile  # noqa: PLC0415

        context = self.context
        decision_at = datetime.fromtimestamp(event["timestamp_ms"] / 1000, tz=UTC)
        frame = causal_snapshot(
            self.candle_frames[event["timeframe"]], decision_at, max_bars=1
        )
        if frame.empty or frame["open_time"].iloc[-1] != pd.Timestamp(event["decision_for_open_ms"], unit="ms", tz="UTC"):
            return  # decision already consumed or superseded (single pass)
        provider = getattr(self, "feature_provider", None)
        if provider is not None:
            # Phase 8N-K fast path: identical semantics over memoized,
            # scenario-invariant features.  Every branch below mirrors the
            # reference path exactly (see the reference code following this
            # block); only feature *construction* is replaced by the store.
            from bot.validation.market_feature_store import (  # noqa: PLC0415
                evaluate_orchestration_from_features,
            )

            features = provider.features_for(
                int(event["timestamp_ms"]), str(event["candle_identity"])
            )
            if not features.check_passes:
                return  # reference single-pass check (scenario-invariant)
            if not features.news_context["news_clear"]:
                context.rejections.append({
                    "reason_code": "NEWS_BLOCKED", "decision_id": event["event_id"],
                    "timestamp": decision_at.isoformat(),
                })
                return
            prior_state = context.state_record
            decision, record = evaluate_orchestration_from_features(
                features, decision_at=decision_at, prior_state=prior_state,
                active_trade_count=len(context.engine.positions),
                max_concurrent_trades=context.max_concurrent_trades,
            )
            result = dict(decision.context)
            context.decisions.append({
                "decision_id": event["event_id"], "timestamp": decision_at.isoformat(),
                "action": decision.action, "reason": decision.reason,
                "setup_id": result.get("setup_id"), "entry_eligible": bool(
                    (result.get("strategy_decision") or {}).get("entry_eligible")
                ),
            })
            if record is not None:
                context.state_record = _publish_decision(context, record)
            if decision.action != "candidate_ready":
                return
            inputs = _inputs_for(self, decision_at)
            evaluated = evaluate_setup_inputs(
                prior_state, inputs, context.strategy_config,
                metadata=_setup_metadata(context, decision_at),
                min_rr=FROZEN_MIN_RR, partial_close_fraction=0.5,
            )
            if evaluated.intent_json is None:
                return
            intent = entry_intent_from_payload(json.loads(evaluated.intent_json))
            context.pending_intents.append({
                "intent": intent,
                "state": create_entry_state(intent),
                "decision_id": event["event_id"],
            })
            return
        news = news_context_for(context.bindings, decision_at, context.strategy_config)
        if not news["news_clear"]:
            context.rejections.append({
                "reason_code": "NEWS_BLOCKED", "decision_id": event["event_id"],
                "timestamp": decision_at.isoformat(),
            })
            return
        prior_state = context.state_record
        decision, record = evaluate_historical_orchestration(
            self.candle_frames,
            constituent_frames=self.constituent_frames,
            decision_at=decision_at,
            news_context=news,
            prior_state=prior_state,
            active_trade_count=len(context.engine.positions),
            max_concurrent_trades=context.max_concurrent_trades,
        )
        result = dict(decision.context)
        context.decisions.append({
            "decision_id": event["event_id"], "timestamp": decision_at.isoformat(),
            "action": decision.action, "reason": decision.reason,
            "setup_id": result.get("setup_id"), "entry_eligible": bool(
                (result.get("strategy_decision") or {}).get("entry_eligible")
            ),
        })
        # Fill-authoritative persistence: the orchestrator's reducer record
        # is the authoritative next state.  Early orchestrator outcomes
        # (insufficient data / unsafe inputs) produce no reducer record —
        # the prior state stays authoritative, exactly as production.
        if record is not None:
            context.state_record = _publish_decision(context, record)
        # Levels/intent construction is required only for candidates; the
        # reducer inputs are then guaranteed sufficient by the gates
        # themselves.  Non-candidate decisions never touch this path, so
        # thin early-fold history fails closed as waits, never as crashes.
        if decision.action != "candidate_ready":
            return
        inputs = _inputs_for(self, decision_at)
        evaluated = evaluate_setup_inputs(
            prior_state, inputs, context.strategy_config,
            metadata=_setup_metadata(context, decision_at),
            min_rr=FROZEN_MIN_RR, partial_close_fraction=0.5,
        )
        if evaluated.intent_json is None:
            return
        intent = entry_intent_from_payload(json.loads(evaluated.intent_json))
        context.pending_intents.append({
            "intent": intent,
            "state": create_entry_state(intent),
            "decision_id": event["event_id"],
        })

    # -- execution path ----------------------------------------------------
    def on_quote(self, event: Mapping[str, Any]) -> None:
        context = self.context
        quote = HistoricalQuote(
            symbol="XAUUSDm",
            timestamp=datetime.fromtimestamp(event["timestamp_ms"] / 1000, tz=UTC),
            bid=event["bid"], ask=event["ask"], source=event["provenance_id"],
            dataset_id=event["source_chunk_id"], sequence_id=event["sequence_id"],
        )
        self.sequence = context.quote_sequence + 1
        context.quote_sequence = self.sequence
        sequence = self.sequence
        engine = context.engine
        # (1) pending entries may fill on this later executable quote
        remaining = []
        for pending in context.pending_intents:
            decision, position = process_quote_entry(
                engine, pending["state"], quote, sequence=sequence,
                quantity=self.quantity,
                setup_recovery=context.recovery if context.setup_store_initialized else None,
                setup_record=context.state_record if context.setup_store_initialized else None,
                fill_journal=context.fill_journal,
            )
            if position is not None:
                context.lifecycle_positions[position.trade_id] = position
            elif decision.state.status not in _TERMINAL_LIFECYCLE_STATUSES:
                pending["state"] = decision.state
                remaining.append(pending)
        context.pending_intents = remaining
        # Fill-authoritative repair: fills mutate the durable setup store
        # (register_binding / consumption) outside publish_decision's CAS, so
        # the in-memory record must be refreshed from the authoritative
        # durable state before the next decision evaluation.  Without this
        # refresh the next publish_decision CAS correctly rejects a stale
        # expected record (setup state changed during evaluation).
        if context.setup_store_initialized:
            context.state_record = context.setup_store.load()
        # (2) open positions are managed against the quote through the
        # parity-tested historical/lifecycle glue
        for trade_id, position in list(context.lifecycle_positions.items()):
            managed = manage_quote_position(
                engine, position, quote, sequence=sequence, config=self._management_config(),
            )
            if managed.status in _TERMINAL_LIFECYCLE_STATUSES:
                del context.lifecycle_positions[trade_id]
            else:
                context.lifecycle_positions[trade_id] = managed
        # (3) equity tracking
        engine.mark_to_market(quote)
        context.equity_points.append({
            "timestamp": quote.timestamp.isoformat(),
            "balance": engine.account.balance, "equity": engine.account.equity,
        })

    # -- periodic ----------------------------------------------------------
    def on_session_boundary(self, timestamp: datetime) -> None:
        context = self.context
        hour = int(timestamp.timestamp() // 3600)
        if context.last_session_hour == hour:
            return
        context.last_session_hour = hour
        engine = context.engine
        for position_id in list(engine.positions):
            entries = engine.apply_swap_until(position_id, timestamp)
            if entries:
                context.equity_points.append({
                    "timestamp": timestamp.isoformat(), "swap_event": True,
                    "balance": engine.account.balance,
                })

    def finish_fold(self, last_quote: Mapping[str, Any] | None) -> None:
        context = self.context
        engine = context.engine
        if last_quote is not None:
            quote = HistoricalQuote(
                symbol="XAUUSDm",
                timestamp=datetime.fromtimestamp(last_quote["timestamp_ms"] / 1000, tz=UTC),
                bid=last_quote["bid"], ask=last_quote["ask"],
                source=last_quote["provenance_id"], dataset_id=last_quote["source_chunk_id"],
                sequence_id=last_quote["sequence_id"],
            )
            for position_id in list(engine.positions):
                # The engine retains fully-closed positions for ledger history;
                # only positions with open volume require the END_OF_DATA close.
                if engine.positions[position_id].remaining_volume <= 1e-12:
                    continue
                engine.close_market(
                    action_id=lifecycle_stable_id("close", position_id, "END_OF_DATA"),
                    position_id=position_id, quote=quote, reason_code="END_OF_DATA",
                )
        if any(
            position.remaining_volume > 1e-12
            for position in engine.positions.values()
        ):
            raise EmpiricalPipelineError("open positions remain without a final quote")

    # -- helpers -----------------------------------------------------------
    def _management_config(self) -> ManagementConfig:
        return ManagementConfig(
            volume_min=self.context.metadata.volume_min,
            volume_step=self.context.metadata.volume_step,
        )


def _publish_decision(context: CellExecutionContext, next_state: SetupStateRecord) -> SetupStateRecord:
    """Fill-authoritative decision persistence through the shared store."""
    if not context.setup_store_initialized:
        context.setup_store.initialize(next_state)
        context.setup_store_initialized = True
        return next_state
    return context.recovery.publish_decision(context.state_record, next_state)


def _inputs_for(handler: CellEventHandler, decision_at: datetime):
    from bot.analysis.bias_engine import (  # noqa: PLC0415
        DEFAULT_BARS, bias_snapshot_from_frames, resolve_trade_bias,
    )
    from bot.analysis.liquidity_map import build_liquidity_map_from_frames  # noqa: PLC0415
    from bot.data.candles import causal_snapshot  # noqa: PLC0415
    from bot.state.gate_inputs import build_gate_inputs  # noqa: PLC0415
    from bot.validation.empirical_strategy_adapter import prepare_dxy_context  # noqa: PLC0415
    from config.symbol_profiles import get_symbol_profile  # noqa: PLC0415

    context = handler.context
    config = context.strategy_config
    frames = {
        timeframe: causal_snapshot(frame, decision_at, max_bars=DEFAULT_BARS.get(timeframe, 320))
        for timeframe, frame in handler.candle_frames.items()
    }
    for timeframe, frame in frames.items():
        if (frame["available_at"] > pd.Timestamp(decision_at)).any():
            raise EmpiricalPipelineError(f"future candle selected for {timeframe}")
    # Thin higher-timeframe history is not a crash here: the orchestrator's
    # own bias/liquidity acquisition treats short frames as neutral (silent
    # fail-closed) and only empty H1/M5/M15 blocks evaluation upstream, so
    # this reconstruction must apply exactly the same semantics.
    bias = bias_snapshot_from_frames("XAUUSDm", frames, silent=True)
    resolution = resolve_trade_bias(bias)
    profile = get_symbol_profile("XAUUSDm")
    liquidity = build_liquidity_map_from_frames("XAUUSDm", {
        "H1": frames["H1"].tail(320), "M15": frames["M15"].tail(320),
        "D1": frames["D1"].tail(10), "W1": frames["W1"].tail(10),
    }, silent=True)
    dxy_context = prepare_dxy_context(
        handler.constituent_frames,
        {"structure": "neutral", "state": "range"},
        decision_at,
    )
    return build_gate_inputs(
        symbol="XAUUSDm", event_at=decision_at,
        frames={"H1": frames["H1"].tail(int(profile["structure_bars"])),
                "M5": frames["M5"].tail(int(profile["entry_bars"])),
                "M15": frames["M15"].tail(220)},
        profile=profile, htf_bias=str(resolution["direction"]),
        bias_snapshot=bias, bias_resolution=resolution,
        liquidity_context=liquidity, dxy_context=dxy_context,
        news_context=news_context_for(context.bindings, decision_at, config),
        session_context=get_session_context(decision_at),
        config=config,
    )


def run_cell_events(
    context: CellExecutionContext, handler: CellEventHandler, *,
    events: Iterator[dict[str, Any]],
    checkpoint_every: int = 100_000,
    on_checkpoint: Callable[[str | None, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Drive one cell to completion over the merged empirical stream.

    Resume semantics: the caller re-derives the identical deterministic
    stream; events already consumed before the checkpoint cursor are skipped
    by event identity, and all durable state (engine, setup store, fill
    journal) was written as it happened, so resumed output equals
    uninterrupted output without duplicate fills, P&L, costs or outcomes.
    """
    processed = 0
    last_event_key: str | None = None
    last_quote: dict[str, Any] | None = None
    consumed_keys: set[str] = getattr(context, "consumed_event_keys", set())
    since_checkpoint = 0
    for event in events:
        key = str(event["event_id"])
        if key in consumed_keys:
            continue
        if event["event_kind"] == "DECISION":
            handler.on_signal(event)
        elif event["event_kind"] == "QUOTE":
            handler.on_quote(event)
            last_quote = event
        else:
            raise EmpiricalPipelineError(f"unknown event kind: {event['event_kind']}")
        stamp = datetime.fromtimestamp((event["timestamp_ms"] // 3_600_000) * 3600, tz=UTC)
        handler.on_session_boundary(stamp)
        consumed_keys.add(key)
        last_event_key = key
        processed += 1
        since_checkpoint += 1
        # Periodic durable checkpoint: serialize the exact engine/lifecycle
        # state so a resumed cell continues without duplicate fills, P&L,
        # costs or outcomes (deterministic stream + consumed-key skip).
        if on_checkpoint is not None and since_checkpoint >= max(1, int(checkpoint_every)):
            on_checkpoint(last_event_key, serialize_cell_state(context))
            since_checkpoint = 0
    context.consumed_event_keys = consumed_keys
    if on_checkpoint is not None:
        on_checkpoint(last_event_key, serialize_cell_state(context))
    handler.finish_fold(last_quote)
    return {
        "events_processed": processed,
        "last_event_key": last_event_key,
        "decisions": len(context.decisions),
        "fills": len(context.engine.fills),
        "rejections": len(context.engine.rejections),
        "final_balance": context.engine.account.balance,
        "final_equity": context.engine.account.equity,
    }


def _setup_metadata(context: CellExecutionContext, decision_at: datetime) -> SetupSymbolMetadata:
    """Symbol metadata window for setup construction (synthetic-free bounds).

    The window bounds only level construction lookups; it is not an effective
    date claim about historical broker conditions.
    """
    return SetupSymbolMetadata(
        "XAUUSDm", 0.001, 10, 3,
        datetime(2024, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC),
        "phase8n-development-proxy",
    )


# ---------------------------------------------------------------------------
# Structural canary (no strategy metrics)
# ---------------------------------------------------------------------------


def empirical_structural_canary(
    bindings: EmpiricalInputBindings, *, fold: Mapping[str, Any],
    tick_limit: int = 50_000,
) -> dict[str, Any]:
    """Read-only structural canary over real datasets — stops before metrics.

    Streams bounded batches of the merged stream, validates chronology and
    schema, counts decision/quote events, measures read throughput, and never
    constructs a strategy evaluation or any performance figure.
    """
    started = datetime.now(UTC)
    previous_key: tuple[int, int, str] | None = None
    decisions = 0
    quotes = 0
    schema_errors: list[str] = []
    for event in empirical_event_stream(
        bindings, fold, canary=True, canary_tick_limit=tick_limit,
    ):
        key = (
            int(event["timestamp_ms"]),
            0 if event["event_kind"] == "DECISION" else 1,
            str(event.get("sequence_id", event.get("candle_identity", ""))),
        )
        if previous_key is not None and key < previous_key:
            schema_errors.append("CHRONOLOGY_INVERSION")
            break
        previous_key = key
        if event["event_kind"] == "DECISION":
            decisions += 1
            required = {"timestamp_ms", "decision_for_open_ms", "candle_identity", "event_id"}
        else:
            quotes += 1
            required = {"timestamp_ms", "bid", "ask", "sequence_id", "event_id"}
        missing = required - set(event)
        if missing:
            schema_errors.append(f"MISSING_FIELDS:{sorted(missing)}")
            break
        if quotes >= tick_limit:
            break
    elapsed = (datetime.now(UTC) - started).total_seconds()
    if schema_errors:
        raise EmpiricalPipelineError(f"canary failed: {schema_errors}")
    return {
        "schema": PIPELINE_SCHEMA,
        "label": CANARY_LABEL,
        "events_observed": decisions + quotes,
        "decision_events": decisions,
        "quote_events_observed": quotes,
        "elapsed_seconds": round(elapsed, 3),
        "quote_throughput_per_second": round(quotes / elapsed, 1) if elapsed > 0 else None,
        "fold_id": str(fold.get("fold_id", "")),
        "strategy_metrics_produced": False,
    }


# ---------------------------------------------------------------------------
# Synthetic rehearsal bindings (fixture-backed, NOT market evidence)
# ---------------------------------------------------------------------------

SYNTHETIC_REHEARSAL_LABEL = "SYNTHETIC TEST FIXTURE — NOT MARKET EVIDENCE"


SYNTHETIC_REHEARSAL_LABEL = "SYNTHETIC TEST FIXTURE — NOT MARKET EVIDENCE"


def build_synthetic_rehearsal_bindings(
    *, plan: Mapping[str, Any], worktree: Path,
) -> EmpiricalInputBindings:
    """Build plan-shaped synthetic bindings for the 64-cell rehearsal.

    The fixture mirrors the real dataset contracts (candle normal form,
    broker-symbol-keyed constituents, official-news snapshot, 8H/8L
    scenario structures) but every identity is derived inside the test
    root and clearly labelled synthetic.  No network, no MT5, no owner
    evidence, no empirical dataset is touched.
    """
    import tempfile  # noqa: PLC0415

    from bot.validation import cost_policy as cost_module
    from bot.validation import development_metadata_bounds as metadata_module

    fixture_root = Path(tempfile.mkdtemp(prefix="phase8n-rehearsal-"))
    from bot.validation import cost_policy as _cost

    cost_content = {
        "schema_version": _cost.POLICY_SCHEMA_VERSION,
        "classification": "SYNTHETIC_REHEARSAL_FIXTURE",
        "label": SYNTHETIC_REHEARSAL_LABEL,
        "cost_components": {
            "commission": cost_module.commission_treatment_record(),
            "swap": cost_module.swap_treatment_record(),
        },
        "swap_scenarios": list(cost_module.build_swap_scenarios()),
        "slippage_scenarios": list(cost_module.SLIPPAGE_SCENARIOS),
    }

    # -- candles ------------------------------------------------------------
    # Calendar-year frames in the exact normal form of the accepted empirical
    # candle packages (ordering, availability window, candle_identity).
    # Intraday timeframes are restricted to four deterministic 2-hour windows
    # per month so the 64-cell rehearsal completes in bounded time while every
    # fold evaluation window still contains real decisions and executable
    #    quotes.  All values are SYNTHETIC TEST FIXTURE — NOT MARKET EVIDENCE.
    candle_root = fixture_root / "candles"
    base = pd.Timestamp("2024-01-01", tz="UTC")
    year_end = pd.Timestamp("2025-01-01", tz="UTC")
    window_days = (1, 8, 15, 22)
    frequencies = {
        "M5": ("5min", 5 * 60_000, True),
        "M15": ("15min", 15 * 60_000, True),
        # H1/H4 also restricted to the deterministic windows: keeps the
        # rehearsal bounded while still providing causal HTF history inside
        # every fold (thin frames exercise the fail-closed neutral-bias
        # semantics deliberately).
        "H1": ("1h", 3_600_000, True),
        "H4": ("4h", 4 * 3_600_000, True),
        "D1": ("1D", 24 * 3_600_000, False),
        "W1": ("7D", 7 * 24 * 3_600_000, False),
    }
    for timeframe, (freq, step_ms, intraday) in frequencies.items():
        opens = pd.date_range(base, year_end, freq=freq, inclusive="left", tz="UTC")
        if intraday:
            opens = opens[opens.day.isin(window_days) & (opens.hour < 2)]
        open_ms = [int(value.value) // 1_000_000 for value in opens]
        # Deterministic triangle-wave prices: swings for the bias/liquidity
        # engine, no randomness, no strategy outcome relevance.
        closes = []
        for index in range(len(open_ms)):
            cycle = index % 48
            amplitude = cycle if cycle < 24 else 48 - cycle
            closes.append(round(2000.0 + amplitude * 0.75 + 0.005 * index, 3))
        frame = pd.DataFrame({
            "open_time_ms": open_ms,
            "close_time_ms": [value + step_ms for value in open_ms],
            "available_at_ms": [value + step_ms for value in open_ms],
            "bid_open": closes,
            "bid_high": [value + 1.7 for value in closes],
            "bid_low": [value - 1.7 for value in closes],
            "bid_close": [round(value + 0.4, 3) for value in closes],
            "tick_count": [10] * len(open_ms),
            "spread_median": [1.3] * len(open_ms),
            "candle_identity": [
                f"SYN-{timeframe}-{value}" for value in open_ms
            ],
        })
        partition = candle_root / "candles" / "XAUUSDm" / timeframe / "year=2024"
        partition.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(partition / "part-00000.parquet", index=False)

    # -- constituents (broker-symbol keyed, real basket members) ------------
    dxy_root = fixture_root / "dxy"
    for symbol in ("EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF"):
        opens = pd.date_range(base, year_end, freq="1h", inclusive="left", tz="UTC")
        open_ms = [int(value.value) // 1_000_000 for value in opens]
        closes = [
            round(1.0 + 0.01 * ((index % 24) / 24.0), 5)
            for index in range(len(open_ms))
        ]
        frame = pd.DataFrame({
            "open_time_ms": open_ms,
            "available_at_ms": [value + 3_600_000 for value in open_ms],
            "open": closes, "high": [value + 0.005 for value in closes],
            "low": [value - 0.005 for value in closes], "close": closes,
            "tick_volume": [1] * len(open_ms), "spread": [0] * len(open_ms),
            "real_volume": [0] * len(open_ms),
            "broker_symbol": [f"{symbol}m"] * len(open_ms),
        })
        constituents = dxy_root / "constituents"
        constituents.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(constituents / f"{symbol.lower()}-h1-2024.parquet", index=False)

    # -- monthly tick partitions (same layout as the accepted year package) -
    # Quotes at 30-second spacing inside the deterministic windows; fills and
    # management therefore always have later executable quotes after a
    # decision.  Streaming consumes these through iter_month_ticks exactly as
    # the empirical path does.
    (fixture_root / "ticks").mkdir(parents=True, exist_ok=True)
    monthly_roots = []
    total_ticks = 0
    for month in range(1, 13):
        month_root = fixture_root / f"ticks-month-{month:02d}"
        # Same relative layout as the accepted empirical monthly packages
        # (ticks/year=YYYY/month=NN/*.parquet).
        partition_dir = month_root / "ticks" / "year=2024" / f"month={month:02d}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        month_start = pd.Timestamp(f"2024-{month:02d}-01", tz="UTC")
        stamps: list[pd.Timestamp] = []
        for day in window_days:
            day_start = month_start + pd.Timedelta(days=day - 1)
            stamps.extend(pd.date_range(
                day_start, day_start + pd.Timedelta(hours=2),
                freq="30s", inclusive="left", tz="UTC",
            ))
        time_msc = [int(value.value) // 1_000_000 for value in stamps]
        bids = []
        for index in range(len(time_msc)):
            wave = index % 240
            amplitude = wave if wave < 120 else 240 - wave
            bids.append(round(2000.0 + amplitude * 0.05 + 0.002 * index, 3))
        tick_frame = pd.DataFrame({
            "time_msc": time_msc,
            "bid": bids,
            "ask": [value + 0.25 for value in bids],
            "sequence_id": [f"SYNT-{month:02d}-{index:06d}" for index in range(len(time_msc))],
            "provenance_id": ["SYNTHETIC-REHEARSAL"] * len(time_msc),
            "source_member": [f"syn-{month:02d}" for _ in time_msc],
            "row_identity": [f"SYNR-{month:02d}-{index:06d}" for index in range(len(time_msc))],
        })
        tick_frame.to_parquet(partition_dir / "part-00000.parquet", index=False)
        monthly_roots.append(month_root)
        total_ticks += len(time_msc)

    # -- official news snapshot --------------------------------------------
    from bot.validation import historical_news_replay as news_module

    events = []
    for index in range(4):
        event_at = base + pd.Timedelta(days=30 * (index + 1)) + pd.Timedelta(hours=14)
        events.append({
            "event_id": f"SYNTHETIC-EV-{index}",
            "event_at_utc": event_at.isoformat(),
            "currency": "USD",
            "impact": "HIGH",
            "original_title": "Synthetic rehearsal fixture event",
            "retrieved_at": (event_at + pd.Timedelta(minutes=1)).isoformat(),
            "source_agency": "SYNTHETIC_REHEARSAL_FIXTURE",
            "raw_source_sha256": "a" * 64,
        })
    news_content = {
        "status": "ACCEPTED_DEVELOPMENT_ONLY",
        "complete": True,
        "year": 2024,
        "retrieval_utc": (base + pd.Timedelta(days=200)).isoformat(),
        "events": events,
    }
    news_snapshot = news_module.build_historical_news_snapshot(
        news_content,
        package_id=news_module.PACKAGE_ID,
        expected_content_sha256=canonical_hash(news_content),
    )

    # -- 8L mandatory scenarios (frozen order) ------------------------------
    metadata_content = {
        "schema_version": metadata_module.POLICY_SCHEMA_VERSION,
        "classification": "SYNTHETIC_REHEARSAL_FIXTURE",
        "label": SYNTHETIC_REHEARSAL_LABEL,
        "mandatory_scenarios": metadata_module._scenarios(),
    }

    return EmpiricalInputBindings(
        plan=plan,
        evidence_root=fixture_root,
        tick_year_root=fixture_root / "ticks",
        monthly_roots=tuple(monthly_roots),
        candle_root=candle_root,
        dxy_root=dxy_root,
        news_package={"package_id": news_module.PACKAGE_ID, "synthetic": True},
        news_snapshot=news_snapshot,
        spread_binding={"synthetic": True, "label": SYNTHETIC_REHEARSAL_LABEL},
        cost_policy_package_id="synthetic-rehearsal-cost-policy",
        cost_policy_content=cost_content,
        metadata_bounds_package_id="synthetic-rehearsal-metadata-bounds",
        metadata_bounds_content=metadata_content,
        readiness={
            "ticks": {"row_count": total_ticks, "canonical_sha256": "synthetic"},
            "label": SYNTHETIC_REHEARSAL_LABEL,
        },
    )


def estimate_cell_runtime(bindings: EmpiricalInputBindings, *, canary: Mapping[str, Any]) -> dict[str, Any]:
    """Labelled projection (estimate, not guarantee) from measured throughput."""
    throughput = canary.get("quote_throughput_per_second") or 0.0
    fold = bindings.plan["folds"][0]
    fold_seconds = (
        int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000)
        - int(pd.Timestamp(fold["evaluation"]["start"]).value // 1_000_000)
    ) / 1000
    year_seconds = (DEVELOPMENT_END_MS - DEVELOPMENT_START_MS) / 1000
    ticks_per_cell = int(bindings.readiness["ticks"]["row_count"] * (fold_seconds / year_seconds))
    per_cell_seconds = ticks_per_cell / throughput if throughput > 0 else None
    return {
        "schema": PIPELINE_SCHEMA,
        "label": "ESTIMATE_NOT_GUARANTEE",
        "measured_quote_throughput_per_second": throughput,
        "projected_ticks_per_cell": ticks_per_cell,
        "projected_seconds_per_cell": None if per_cell_seconds is None else round(per_cell_seconds, 1),
        "projected_total_hours_64_cells": None if per_cell_seconds is None else round(per_cell_seconds * 64 / 3600, 2),
        "basis": "measured structural read throughput; strategy-decision and management time excluded",
    }
