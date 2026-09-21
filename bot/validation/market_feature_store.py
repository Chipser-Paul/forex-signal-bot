"""Phase 8N-K causal market-feature memoization for the empirical replay.

Engineering acceleration only — no strategy, risk, cost, scenario, fold,
metric or acceptance semantic is changed.

Measured profile (``probes/phase8n_k_callgraph.json`` — labelled
`EMPIRICAL ENGINEERING BENCHMARK — NOT STRATEGY EVIDENCE`): of the ~0.95 s
per decision, ≈86 % is scenario-invariant feature construction (bias
snapshot, liquidity map, DXY alignment, gate-input assembly) that is
identical for every scenario cell of a fold.  The pure shared reducer
(``bot.state.gate_reducer.evaluate_strategy_gates``) and the durable
decision publication are cell-local and are reused untouched.

Feature classification implemented here (see ``FEATURE_CLASSIFICATION``):

- A. SCENARIO-INVARIANT MARKET FACT — memoized once per fold per decision:
  session context, news context, HTF bias snapshot + resolution, DXY
  context (real gold structure variant), causal frame sufficiency, the
  full orchestrator ``StrategyEvaluationInputs`` payload (which embeds the
  liquidity sweep, displacement, FVGs, internal structure, order-block
  result, ATR and entry rows) and its event id / source identities.
- B. CELL-LOCAL STATE — never memoized: setup lifecycle and consumption,
  pending intents, positions, risk/circuit state, fills, account state,
  P&L/costs.  These live only in ``CellExecutionContext``.
- C. MIXED — split: the raw market facts above are memoized; every
  cell-local interpretation (gate transitions, consumption, execution)
  runs per cell through the shared reducer.

The candidate path (``_inputs_for`` in the input pipeline) is rare and
keeps the exact reference implementation; only the per-decision
orchestration path (the dominant cost) is memoized.

Store contract: immutable, published atomically outside Git, bound to the
plan, fold, input index, news package, frozen configuration, feature
schema and implementation fingerprint.  No strategy outcomes, fills,
positions, risk decisions or performance are stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import uuid
import zlib
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

import pandas as pd

from bot.acquisition.evidence_contracts import canonical_hash
from bot.analysis.bias_engine import BIAS_TIMEFRAMES, DEFAULT_BARS, bias_snapshot_from_frames, resolve_trade_bias
from bot.data.candles import causal_snapshot
from bot.state.gate_inputs import GateInputError, StrategyEvaluationInputs, build_gate_inputs
from bot.strategy.config import StrategyConfig
from bot.strategy.setup_state import (
    STATE_FIELDS, record_from_state, restore_setup_for_evaluation, state_from_record,
)
from bot.utils.session_clock import get_session_context
from utils.symbol_profiles import get_symbol_profile

FEATURE_SCHEMA = "phase8n.causal-market-features.v1"
FEATURE_STORE_DIR_NAME = "market-feature-store"
COMPLETE_MARKER = "feature-store.complete.json"
BUILDER_VERSION = "phase8n-k.feature-store.v1"

SYMBOL = "XAUUSDm"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decision_datetime(available_at_ms: int) -> datetime:
    """Exactly the reference construction (``CellEventHandler.on_signal``)."""
    return datetime.fromtimestamp(available_at_ms / 1000, tz=timezone.utc)


def preflight_setup_id(decision_at: datetime) -> str:
    """The orchestrator's pre-reducer setup id (observable on early returns)."""
    material = f"phase8n.preflight.v1|{SYMBOL}|{decision_at.isoformat()}"
    return "pre8n_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _ensure_dict(value: Any, default: dict | None = None) -> dict:
    """Mirror ``StrategyOrchestrator._ensure_dict`` (warnings disabled here)."""
    if isinstance(value, dict):
        return value
    return default if default is not None else {}


def _ensure_dict_list(value: Any) -> list[dict]:
    if value is None or not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


# ---------------------------------------------------------------------------
# Feature classification (documentation contract enforced by tests)
# ---------------------------------------------------------------------------

FEATURE_CLASSIFICATION: dict[str, str] = {
    # A — scenario-invariant market facts (memoized here)
    "session_context": "A",
    "news_context": "A",
    "bias_snapshot": "A",
    "bias_resolution": "A",
    "dxy_context": "A",
    "frame_sufficiency": "A",
    "gate_inputs_payload": "A",
    "gate_event_id": "A",
    "gate_source_identities": "A",
    # Served snapshot-field views of the same A facts above:
    "gate_payload": "A",
    "gate_sources": "A",
    "frames_sufficient": "A",
    "config_fingerprint": "A",
    "liquidity_context_raw": "A",  # build-time only; embedded in the payload
    # B — cell-local state (never memoized)
    "setup_lifecycle_consumption": "B",
    "pending_intent": "B",
    "open_position": "B",
    "risk_circuit_state": "B",
    "broker_rejections": "B",
    "fill_execution_outcomes": "B",
    "account_equity_state": "B",
    "consumed_setup_identities": "B",
    "pnl_costs": "B",
    "active_trade_count": "B",
    # C — mixed, split into raw fact + cell-local reducer step
    "order_block_candidates": "C",  # raw facts inside the memoized payload
    "order_block_consumption": "B",  # cell-local via the shared reducer/store
    "liquidity_pools": "C",  # raw pools shared; sweep-driven lifecycle local
}


# ---------------------------------------------------------------------------
# Snapshot (in-memory serving shape)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CausalMarketFeatureSnapshot:
    """Immutable scenario-invariant facts for one frozen decision event.

    Contains no strategy outcome, fill, position, risk decision or
    performance figure — verified structurally by tests and by the
    publication schema below.
    """

    available_at_ms: int
    open_time_ms: int
    timeframe: str
    close: float
    identity: str
    check_passes: bool
    session_context: Mapping[str, Any]
    news_context: Mapping[str, Any]
    bias_snapshot: Mapping[str, Any]
    bias_resolution: Mapping[str, Any]
    dxy_context: Mapping[str, Any]
    frames_sufficient: bool
    gate_status: str  # ok | early_exit | dxy_blocked | insufficient_data | causal_input_unsafe
    gate_payload: str | None
    gate_event_id: str | None
    gate_sources: tuple[tuple[str, str], ...]
    config_fingerprint: str

    def strategy_evaluation_inputs(self) -> StrategyEvaluationInputs:
        """Rebuild the exact frozen inputs object for the shared reducer."""
        if self.gate_status != "ok" or self.gate_payload is None:
            raise GateInputError(f"decision {self.identity} has no executable gate inputs")
        return StrategyEvaluationInputs(
            symbol=SYMBOL,
            event_at=_decision_datetime(self.available_at_ms),
            event_id=str(self.gate_event_id),
            source_identities=tuple(self.gate_sources),
            config_fingerprint=self.config_fingerprint,
            payload=str(self.gate_payload),
        )


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def _liquidity_coerced(liquidity: Mapping[str, Any]) -> dict[str, Any]:
    """Exactly the orchestrator's coercion of the raw liquidity map."""
    coerced = dict(liquidity)
    coerced["structure_context"] = _ensure_dict(coerced.get("structure_context"))
    coerced["liquidity_pools"] = _ensure_dict_list(coerced.get("liquidity_pools"))
    return coerced


def build_feature_records(
    bindings: Any, index: Any, *, candle_frames: Mapping[str, pd.DataFrame],
    constituent_frames: Mapping[str, pd.DataFrame],
    decision_stride: int | None = None,
    available_at_range: tuple[int, int] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one feature record per decision event of the input index.

    Reproduces the reference decision path's feature construction in the
    orchestrator's exact gate order, using only frozen inputs.  Every
    reference call is invoked with identical arguments; the memo is a
    byte-level cache of the reference computation, not a reimplementation.

    ``decision_stride`` restricts the yield to every k-th decision
    (mechanical stride sampling) — engineering-benchmark builds only;
    production stores must be published with the full coverage (stride
    omitted or 1) that the serving contract requires.

    ``available_at_range`` (inclusive start, exclusive end, ms) is the
    second mechanical sampling dimension (engineering benchmarks only):
    decisions outside the half-open window are skipped *before* any
    expensive feature work.  Both parameters are honestly encoded in the
    published identity's ``coverage`` field, which the serving loader
    refuses for anything but full coverage.
    """
    from bot.analysis.liquidity_map import build_liquidity_map_from_frames  # noqa: PLC0415
    from bot.validation.empirical_input_pipeline import news_context_for  # noqa: PLC0415
    from bot.validation.empirical_strategy_adapter import prepare_dxy_context  # noqa: PLC0415
    from strategies.smc_engine.market_structure import analyze_market_structure  # noqa: PLC0415

    stride = int(decision_stride) if decision_stride else 1
    if stride < 1:
        raise ValueError("decision_stride must be >= 1")
    if available_at_range is not None:
        range_start_ms, range_end_ms = (int(v) for v in available_at_range)
        if range_end_ms <= range_start_ms:
            raise ValueError("available_at_range end must exceed start")
    else:
        range_start_ms, range_end_ms = None, None

    profile = get_symbol_profile(SYMBOL)
    config = StrategyConfig()
    config_fingerprint = config.fingerprint()
    structure_bars = int(profile.get("structure_bars", 320))
    entry_bars = int(profile.get("entry_bars", 220))

    def candles(frame: pd.DataFrame, decision_at: datetime, bars: int) -> pd.DataFrame:
        return causal_snapshot(frame, decision_at, max_bars=bars)

    total = len(index.decisions)
    for position, decision in enumerate(index.decisions):
        if position % stride:
            continue
        available_at_ms, open_time_ms, timeframe, close, identity = decision
        if (
            range_start_ms is not None
            and not (range_start_ms <= available_at_ms < range_end_ms)
        ):
            continue
        decision_at = _decision_datetime(available_at_ms)

        # on_signal's single-pass completion check (scenario-invariant).
        sample = candles(candle_frames[timeframe], decision_at, 1)
        check_passes = bool(
            not sample.empty
            and sample["open_time"].iloc[-1]
            == pd.Timestamp(open_time_ms, unit="ms", tz="UTC")
        )

        session = get_session_context(decision_at)
        news = news_context_for(bindings, decision_at, config)

        bias_snapshot: dict[str, Any] = {}
        bias_resolution: dict[str, Any] = {}
        dxy_context: dict[str, Any] = {}
        liquidity: dict[str, Any] = {}
        gate_status = "early_exit"
        gate_payload: str | None = None
        gate_event_id: str | None = None
        gate_sources: tuple[tuple[str, str], ...] = ()

        session_allowed = bool(session.get("session_allowed", False))
        news_clear = bool(news.get("news_clear", False))
        if session_allowed and news_clear:
            bias_frames = {
                tf: candles(candle_frames[tf], decision_at, DEFAULT_BARS.get(tf, 320))
                for tf in BIAS_TIMEFRAMES
            }
            bias_snapshot = bias_snapshot_from_frames(SYMBOL, bias_frames, silent=True)
            bias_resolution = resolve_trade_bias(bias_snapshot)
            htf_bias = str(bias_resolution.get("direction", "neutral"))
            if htf_bias in ("bullish", "bearish"):
                liquidity = _liquidity_coerced(build_liquidity_map_from_frames(
                    SYMBOL,
                    {
                        "H1": candles(candle_frames["H1"], decision_at, 320),
                        "M15": candles(candle_frames["M15"], decision_at, 320),
                        "D1": candles(candle_frames["D1"], decision_at, 10),
                        "W1": candles(candle_frames["W1"], decision_at, 10),
                    },
                    silent=True,
                ))
                gold_frame = candles(candle_frames["H1"], decision_at, 220)
                gold_structure = (
                    analyze_market_structure(gold_frame, silent=True)
                    if gold_frame is not None and not gold_frame.empty else {}
                )
                dxy_context = prepare_dxy_context(
                    constituent_frames, gold_structure or {}, decision_at,
                )
                gate7_pass = bool(dxy_context.get("available")) and not bool(
                    dxy_context.get("reduce_size")
                )
                if gate7_pass:
                    structure_df = candles(candle_frames["H1"], decision_at, structure_bars)
                    entry_df = candles(candle_frames["M5"], decision_at, entry_bars)
                    internal_df = candles(candle_frames["M15"], decision_at, 220)
                    if (
                        structure_df is None or structure_df.empty
                        or entry_df is None or entry_df.empty
                    ):
                        gate_status = "insufficient_data"
                    else:
                        try:
                            inputs = build_gate_inputs(
                                symbol=SYMBOL, event_at=decision_at,
                                frames={"H1": structure_df, "M5": entry_df, "M15": internal_df},
                                profile=profile, htf_bias=htf_bias,
                                bias_snapshot=bias_snapshot, bias_resolution=bias_resolution,
                                liquidity_context=liquidity, dxy_context=dxy_context,
                                news_context=news, session_context=session, config=config,
                            )
                        except GateInputError:
                            gate_status = "causal_input_unsafe"
                        else:
                            gate_status = "ok"
                            gate_payload = inputs.payload
                            gate_event_id = inputs.event_id
                            gate_sources = tuple(inputs.source_identities)
                else:
                    gate_status = "dxy_blocked"

        yield {
            "available_at_ms": int(available_at_ms),
            "open_time_ms": int(open_time_ms),
            "timeframe": str(timeframe),
            "close": float(close),
            "identity": str(identity),
            "check_passes": check_passes,
            "session_json": json.dumps(session, sort_keys=True, separators=(",", ":"), allow_nan=False),
            "news_json": json.dumps(news, sort_keys=True, separators=(",", ":"), allow_nan=False),
            "bias_json": json.dumps(bias_snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False),
            "bias_resolution_json": json.dumps(bias_resolution, sort_keys=True, separators=(",", ":"), allow_nan=False),
            "dxy_json": json.dumps(dxy_context, sort_keys=True, separators=(",", ":"), allow_nan=False),
            "gate_status": gate_status,
            "gate_payload_z": zlib.compress(gate_payload.encode("utf-8"), 6) if gate_payload is not None else b"",
            "gate_event_id": gate_event_id or "",
            "gate_sources_json": json.dumps([list(pair) for pair in gate_sources], separators=(",", ":")),
            "config_fingerprint": config_fingerprint,
        }
        if on_progress is not None:
            on_progress(position + 1, total)


def _frames_sufficient_from(record: Mapping[str, Any]) -> bool:
    return record["gate_status"] in ("ok", "causal_input_unsafe")


# ---------------------------------------------------------------------------
# Store identity + publication
# ---------------------------------------------------------------------------


def store_identity_payload(
    bindings: Any, index: Any, *, row_digest: str, row_count: int,
) -> dict[str, Any]:
    """Identity binding for the fold feature store (no wall-clock inside)."""
    news = bindings.news_snapshot
    return {
        "schema": FEATURE_SCHEMA,
        "builder_version": BUILDER_VERSION,
        "plan_package_id": bindings.plan.get("package_id", "plan-package"),
        "plan_fingerprint": bindings.plan.get("plan_fingerprint", ""),
        "fold_id": index.fold_id,
        "input_index_sha256": index.index_sha256,
        "decision_timeframe": index.decision_timeframe,
        "evaluation_start_ms": index.evaluation_start_ms,
        "evaluation_end_ms": index.evaluation_end_ms,
        "row_count": int(row_count),
        "coverage": (
            "full" if int(row_count) == len(index.decisions)
            else f"partial:{int(row_count)}-of-{len(index.decisions)}"
        ),
        "rows_sha256": row_digest,
        "source_identities": dict(index.source_identities),
        "news_package_id": getattr(news, "package_id", None),
        "news_content_sha256": getattr(news, "content_sha256", None),
        "config_fingerprint": StrategyConfig().fingerprint(),
        "pipeline_fingerprint": index.pipeline_fingerprint,
    }


def _record_digest(record: Mapping[str, Any]) -> str:
    material = {
        key: (value.hex() if isinstance(value, (bytes, bytearray)) else value)
        for key, value in record.items()
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class FoldFeatureStore:
    """Loaded, read-only feature store for one fold."""

    def __init__(self, identity: Mapping[str, Any], table: Any, path: Path) -> None:
        self.identity = dict(identity)
        self.table = table
        self.path = Path(path)
        self._positions: dict[tuple[int, str], int] = {}
        available = table.column("available_at_ms").to_pylist()
        identities = table.column("identity").to_pylist()
        for position, (available_at_ms, identity) in enumerate(zip(available, identities)):
            self._positions[(int(available_at_ms), str(identity))] = position

    def __len__(self) -> int:
        return self.table.num_rows

    def row(self, available_at_ms: int, identity: str) -> Mapping[str, Any]:
        position = self._positions.get((int(available_at_ms), str(identity)))
        if position is None:
            raise KeyError(f"decision not covered by the feature store: {identity}")
        return {
            name: self.table.column(name)[position].as_py()
            for name in self.table.column_names
        }


def _snapshot_from_row(row: Mapping[str, Any]) -> CausalMarketFeatureSnapshot:
    payload = (
        zlib.decompress(bytes(row["gate_payload_z"])).decode("utf-8")
        if row["gate_payload_z"] else None
    )
    return CausalMarketFeatureSnapshot(
        available_at_ms=int(row["available_at_ms"]),
        open_time_ms=int(row["open_time_ms"]),
        timeframe=str(row["timeframe"]),
        close=float(row["close"]),
        identity=str(row["identity"]),
        check_passes=bool(row["check_passes"]),
        session_context=json.loads(row["session_json"]),
        news_context=json.loads(row["news_json"]),
        bias_snapshot=json.loads(row["bias_json"]),
        bias_resolution=json.loads(row["bias_resolution_json"]),
        dxy_context=json.loads(row["dxy_json"]),
        frames_sufficient=_frames_sufficient_from(row),
        gate_status=str(row["gate_status"]),
        gate_payload=payload,
        gate_event_id=row["gate_event_id"] or None,
        gate_sources=tuple(
            (str(pair[0]), str(pair[1])) for pair in json.loads(row["gate_sources_json"])
        ),
        config_fingerprint=str(row["config_fingerprint"]),
    )


def publish_feature_store(
    records: Iterator[dict[str, Any]] | list[dict[str, Any]], *, evidence_root: Path,
    bindings: Any, index: Any,
) -> tuple[Path, str]:
    """Atomically publish the fold feature store; refuses overwrite."""
    import pyarrow as pa  # noqa: PLC0415
    import pyarrow.parquet as pq  # noqa: PLC0415

    materialized = list(records)
    row_digest = hashlib.sha256()
    for record in materialized:
        row_digest.update(_record_digest(record).encode("utf-8"))
    identity = store_identity_payload(
        bindings, index, row_digest=row_digest.hexdigest(), row_count=len(materialized),
    )
    identity_sha = canonical_hash(identity)

    root = Path(evidence_root) / FEATURE_STORE_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    name = f"{index.fold_id}-{identity_sha[:16]}"
    target = root / name
    if target.exists():
        raise RuntimeError(f"feature store already published: {name}")
    staging = root / f".staging-{name}-{uuid.uuid4().hex[:8]}"
    if staging.exists():
        for stale in sorted(staging.rglob("*"), reverse=True):
            if stale.is_file():
                stale.unlink()
        staging.rmdir()
    staging.mkdir(parents=True)

    def column(name: str, arrow_type: Any) -> pa.Array:
        return pa.array([record[name] for record in materialized], arrow_type)

    table = pa.table({
        "available_at_ms": column("available_at_ms", pa.int64()),
        "open_time_ms": column("open_time_ms", pa.int64()),
        "timeframe": column("timeframe", pa.string()),
        "close": column("close", pa.float64()),
        "identity": column("identity", pa.string()),
        "check_passes": column("check_passes", pa.bool_()),
        "session_json": column("session_json", pa.string()),
        "news_json": column("news_json", pa.string()),
        "bias_json": column("bias_json", pa.string()),
        "bias_resolution_json": column("bias_resolution_json", pa.string()),
        "dxy_json": column("dxy_json", pa.string()),
        "gate_status": column("gate_status", pa.string()),
        "gate_payload_z": column("gate_payload_z", pa.binary()),
        "gate_event_id": column("gate_event_id", pa.string()),
        "gate_sources_json": column("gate_sources_json", pa.string()),
        "config_fingerprint": column("config_fingerprint", pa.string()),
    })
    features_path = staging / "features.parquet"
    pq.write_table(table, features_path)

    identity_file = staging / "feature-store.json"
    identity_file.write_text(
        json.dumps({
            "label": "SCENARIO-INVARIANT CAUSAL MARKET FEATURE STORE — NOT STRATEGY EVIDENCE",
            "built_at_utc": _utc_now(),
            "store_sha256": identity_sha,
            "identity": identity,
        }, sort_keys=True, indent=1),
        encoding="utf-8",
    )
    marker = {
        "status": "COMPLETE",
        "store_sha256": identity_sha,
        "features_file_sha256": _file_sha256(features_path),
        "row_count": len(materialized),
        "fold_id": index.fold_id,
    }
    (staging / COMPLETE_MARKER).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")
    if target.exists():
        raise RuntimeError(f"feature store already published: {name}")
    staging.replace(target)
    loaded = load_feature_store(target)
    if canonical_hash(loaded.identity) != identity_sha:
        raise RuntimeError("feature store readback hash mismatch")
    return target, identity_sha


def load_feature_store(path: Path, *, verify_rows: bool = False) -> FoldFeatureStore:
    """Load and verify a published feature store.

    ``verify_rows`` recomputes every row's digest and re-derives the gate
    event id from its payload (slow; used by the verify CLI command).
    """
    import pyarrow.parquet as pq  # noqa: PLC0415

    path = Path(path)
    payload = json.loads((path / "feature-store.json").read_text(encoding="utf-8"))
    marker = json.loads((path / COMPLETE_MARKER).read_text(encoding="utf-8"))
    if marker.get("status") != "COMPLETE" or marker.get("store_sha256") != payload.get("store_sha256"):
        raise RuntimeError(f"feature store completion marker invalid: {path.name}")
    if marker.get("features_file_sha256") != _file_sha256(path / "features.parquet"):
        raise RuntimeError(f"feature store file bytes changed after publication: {path.name}")
    identity = payload["identity"]
    if identity["schema"] != FEATURE_SCHEMA:
        raise RuntimeError("feature store schema mismatch")
    table = pq.read_table(path / "features.parquet")
    store = FoldFeatureStore(identity, table, path)
    if store.table.num_rows != int(identity["row_count"]):
        raise RuntimeError("feature store row count mismatch")
    if verify_rows:
        digest = hashlib.sha256()
        from bot.state.gate_inputs import gate_event_id  # noqa: PLC0415

        for position in range(store.table.num_rows):
            row = {
                name: store.table.column(name)[position].as_py()
                for name in store.table.column_names
            }
            digest.update(_record_digest(row).encode("utf-8"))
            snapshot = _snapshot_from_row(row)
            if snapshot.gate_status == "ok":
                inputs = snapshot.strategy_evaluation_inputs()
                expected = gate_event_id(
                    symbol=SYMBOL, event_at=inputs.event_at, sources=inputs.source_identities,
                    side=json.loads(inputs.payload)["htf_bias"], payload=inputs.payload,
                    config_fingerprint=inputs.config_fingerprint,
                )
                if expected != snapshot.gate_event_id:
                    raise RuntimeError(f"feature row event id mismatch at position {position}")
        if digest.hexdigest() != identity["rows_sha256"]:
            raise RuntimeError("feature store row digest mismatch (tampered or stale)")
    return store


def find_published_feature_store(evidence_root: Path, *, fold_id: str, store_sha256: str) -> Path:
    target = Path(evidence_root) / FEATURE_STORE_DIR_NAME / f"{fold_id}-{store_sha256[:16]}"
    if not target.is_dir():
        raise RuntimeError(f"published feature store missing: {target.name}")
    return target


def load_published_feature_store_for_index(
    bindings: Any, index: Any, *, evidence_root: Path,
) -> tuple[Path, str] | None:
    """Locate the already-published full-coverage store bound to this index.

    Matches on the identity fields that pin the store to exactly this
    (plan, fold, sources, fingerprints, schema, builder) tuple, and to full
    decision coverage.  Ambiguous publications fail closed.  Read-only.
    """
    root = Path(evidence_root) / FEATURE_STORE_DIR_NAME
    if not root.is_dir():
        return None
    expected_config = StrategyConfig().fingerprint()
    matches: list[tuple[Path, str]] = []
    for directory in sorted(root.iterdir()):
        payload_path = directory / "feature-store.json"
        if not payload_path.is_file():
            continue
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        identity = payload.get("identity")
        if not isinstance(identity, Mapping):
            continue
        if identity.get("schema") != FEATURE_SCHEMA:
            continue
        if identity.get("builder_version") != BUILDER_VERSION:
            continue
        if identity.get("fold_id") != index.fold_id:
            continue
        if identity.get("input_index_sha256") != index.index_sha256:
            continue
        if identity.get("pipeline_fingerprint") != index.pipeline_fingerprint:
            continue
        if identity.get("config_fingerprint") != expected_config:
            continue
        if identity.get("coverage") != "full":
            continue
        if identity.get("decision_timeframe") != index.decision_timeframe:
            continue
        if identity.get("evaluation_start_ms") != index.evaluation_start_ms:
            continue
        if identity.get("evaluation_end_ms") != index.evaluation_end_ms:
            continue
        if identity.get("source_identities") != dict(index.source_identities):
            continue
        sha = str(payload.get("store_sha256"))
        if directory.name != f"{index.fold_id}-{sha[:16]}":
            raise RuntimeError(f"feature store directory name inconsistent with its hash: {directory.name}")
        matches.append((directory, sha))
    if not matches:
        return None
    if len(matches) > 1:
        raise RuntimeError(
            f"ambiguous published feature stores for index {index.index_sha256[:12]}"
        )
    path, sha = matches[0]
    load_feature_store(path)  # completion marker + file-hash readback
    return path, sha


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------


class FoldFeatureProvider:
    """Serves per-decision feature snapshots to any number of cells.

    The store is immutable and read-only; every serve returns freshly
    decoded objects so no cell can mutate another cell's view.  Shared
    across all scenario cells of a fold — the exact scenario-invariant
    reuse the phase authorizes.
    """

    def __init__(self, store: FoldFeatureStore, *, index: Any | None = None) -> None:
        self.store = store
        self.index = index
        self.serve_count = 0

    def features_for(self, available_at_ms: int, identity: str) -> CausalMarketFeatureSnapshot:
        self.serve_count += 1
        return _snapshot_from_row(self.store.row(int(available_at_ms), str(identity)))


# ---------------------------------------------------------------------------
# Fast cell evaluation (shared reducer, cell-local state)
# ---------------------------------------------------------------------------


def evaluate_orchestration_from_features(
    features: CausalMarketFeatureSnapshot, *, decision_at: datetime,
    prior_state: Any, active_trade_count: int, max_concurrent_trades: int,
) -> tuple[Any, Any]:
    """Run the frozen orchestration over memoized features.

    Replicates ``StrategyOrchestrator.evaluate_symbol``'s decision tree
    exactly, with every acquisition-backed value served from the immutable
    feature snapshot.  Gates 8–13 run through the untouched shared reducer
    (``evaluate_strategy_gates``); all state mutation stays in the
    cell-local ``state`` object.  Returns ``(OrchestratorResult,
    gate_record | None)`` exactly like the reference adapter.
    """
    from bot.state.orchestrator import OrchestratorResult  # noqa: PLC0415
    from bot.state.gate_reducer import evaluate_strategy_gates  # noqa: PLC0415
    from bot.validation.empirical_strategy_adapter import HistoricalConcurrencyGate  # noqa: PLC0415
    from strategies.smc_engine.strategy_state import StrategyState  # noqa: PLC0415

    state = restore_setup_for_evaluation(prior_state, decision_at)
    profile = get_symbol_profile(SYMBOL)
    context: dict[str, Any] = {"symbol": SYMBOL, "setup_id": preflight_setup_id(decision_at)}
    try:
        if profile and "min_rr" in profile:
            context["profile_min_rr"] = float(profile["min_rr"])

        # Gate 1: session.
        state.set_event_time(decision_at)
        session = features.session_context
        state.update_session(session)
        context["session"] = session
        if not session.get("session_allowed", False):
            return (
                OrchestratorResult("skip", state.state_name, "session_closed", context),
                getattr(state, "_gate_record", None),
            )

        # Gate 2: news blackout.
        news = features.news_context
        state.update_news(news)
        context["news"] = news
        if not news.get("news_clear", False):
            return (
                OrchestratorResult("pause", state.state_name, "news_blackout", context),
                getattr(state, "_gate_record", None),
            )

        # Gate 4 placeholder (authority stays with the Phase 4 risk authority).
        state.set_daily_limit_hit(False)

        # Gate 5: max concurrent trades (cell-local).
        gate = HistoricalConcurrencyGate(max_concurrent_trades)
        if not gate.can_open_more_trades(active_trade_count):
            return (
                OrchestratorResult("skip", state.state_name, "max_concurrent_trades_hit", context),
                getattr(state, "_gate_record", None),
            )

        # Gate 6: HTF bias confirmation.
        bias = features.bias_snapshot
        state.update_bias(bias)
        context["bias"] = bias
        resolution = features.bias_resolution
        context["bias_resolution"] = resolution
        htf_bias = str(resolution.get("direction", "neutral"))
        if htf_bias not in ("bullish", "bearish"):
            state.reject_setup("htf_bias_unconfirmed")
            return (
                OrchestratorResult("skip", state.state_name, "htf_bias_unconfirmed", context),
                getattr(state, "_gate_record", None),
            )

        # Gate 7: DXY correlation.
        dxy = features.dxy_context
        context["dxy"] = dxy
        if not (bool(dxy.get("available")) and not bool(dxy.get("reduce_size"))):
            return (
                OrchestratorResult("skip", state.state_name, "dxy_unsafe_or_conflicting", context),
                getattr(state, "_gate_record", None),
            )

        # Gates 8–13 through the shared reducer over memoized inputs.
        if not features.frames_sufficient:
            return (
                OrchestratorResult("wait", state.state_name, "insufficient_market_data", context),
                getattr(state, "_gate_record", None),
            )
        if features.gate_status == "causal_input_unsafe":
            return (
                OrchestratorResult("wait", state.state_name, "causal_input_unsafe", context),
                getattr(state, "_gate_record", None),
            )
        inputs = features.strategy_evaluation_inputs()

        policy = StrategyConfig()
        cached = getattr(state, "_gate_record", None)
        if cached is not None and cached.data()["last_event_id"] == inputs.event_id:
            prior = cached
        else:
            previous = cached.data() if cached is not None else {}
            prior = record_from_state(
                state, event_at=decision_at,
                last_event_id=previous.get("last_event_id"),
                last_result=previous.get("last_result"),
            )
        transition = evaluate_strategy_gates(prior, inputs, decision_at, policy)
        next_state = state_from_record(transition.state_record, decision_at)
        for field in STATE_FIELDS:
            setattr(state, field, getattr(next_state, field))
        state._setup_consumption = next_state._setup_consumption
        state._gate_record = transition.state_record

        gate_result = transition.result()
        context.update(gate_result["context"])
        return (
            OrchestratorResult(
                gate_result["action"], state.state_name, gate_result["reason"], context,
            ),
            getattr(state, "_gate_record", None),
        )
    except Exception as error:  # noqa: BLE001 — mirrors the reference wrapper
        context["error_type"] = type(error).__name__
        return (
            OrchestratorResult("error", state.state_name, "orchestrator_input_unsafe", context),
            None,
        )
