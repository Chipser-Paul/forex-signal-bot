"""Phase 8N-J — immutable fold-scoped causal input index + optimized replay.

Performance layer for the plan-bound empirical replay.  It changes execution
mechanics only; strategy, execution, risk, scenario, fold, metric and
acceptance semantics are untouched, and the reference (slow) path in
:mod:`bot.validation.empirical_input_pipeline` is retained for equivalence
testing.

Profile findings (see docs/PHASE8N_EMPIRICAL_REPLAY_PERFORMANCE.md): 88% of
structural replay time is the per-tick Python loop in ``iter_month_ticks``
(dict building, ``str()`` conversions and boundary checks for every one of
3.3M rows per month), 11% is Parquet decode, everything else is noise.

Three mechanisms:

1. **Immutable input index** — per fold: decision events (M5 completions with
   causal availability and close), row-group timestamp boundaries for every
   tick partition (Parquet footer statistics — no data read), and exact source
   identities (partition SHA-256s, manifests, pipeline fingerprint, plan
   fingerprint, worktree head).  Published atomically outside Git with a
   completion marker, canonical hash and readback verification.  Only
   scenario-invariant facts are precomputed — never strategy eligibility,
   setup state, decisions, intents, fills, risk or P&L.

2. **Event-driven tick processing** — while the cell is IDLE (no pending
   intent, no open position) intermediate quote events are skipped with a
   persistent cursor; when an entry intent is pending or a position is open,
   every tick is processed in exact chronological order until the cell is
   idle again.  Idleness is a state-function proof: with no pending intent and
   no open position the handler's ``on_quote`` performs no lifecycle
   transition, no ledger entry and no durable change — its outputs are a
   strictly increasing quote-sequence counter and an equity snapshot the next
   processed quote overwrites.  A skipped quote therefore cannot change any
   state, decision, fill, cost or outcome (verified by equivalence tests).
   Fill semantics are frozen: an intent still triggers on the *next*
   executable quote after its decision, exactly like the reference.

3. **Vectorized causal lookup** — Arrow row-group reads with NumPy masks and
   ``searchsorted`` boundaries replace per-tick Python loops; row groups that
   cannot intersect the current need are never decoded (footer statistics).

No MT5, no network, no holdout or 2025+ data.  The index refuses any decision
at or after 2025-01-01.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

import numpy as np

from bot.acquisition.evidence_contracts import canonical_hash
from bot.validation.empirical_input_pipeline import (
    DECISION_TIMEFRAME,
    DEVELOPMENT_END_MS,
    DEVELOPMENT_START_MS,
    EmpiricalPipelineError,
    _candle_completion_events,
    _monthly_tick_partitions,
)

UTC = timezone.utc


def _repo_root() -> Path:
    """Repository root from this module's location (pytest-safe, no cwd use)."""
    return Path(__file__).resolve().parents[2]


INDEX_SCHEMA = "phase8n.replay-input-index.v1"
#: Bounded batch size for row-group decoding (memory ceiling honored; output
#: is deterministic regardless of batch size because order never depends on it).
DEFAULT_BATCH_ROWS = 50_000
INDEX_DIR_NAME = "replay-input-index"
INDEX_BUILDER_VERSION = "phase8n-j-1"
COMPLETE_MARKER = "index.complete.json"

#: Files whose content defines the replay-mechanics fingerprint.  Mirrors the
#: branch-B runner compatibility surface (runner_compatibility.py) plus this
#: module: any change requires a new index and a new compatibility record.
PIPELINE_FINGERPRINT_FILES = (
    "bot/validation/empirical_input_pipeline.py",
    "bot/validation/replay_input_index.py",
    "bot/validation/development_evaluation_runner.py",
    "backtests/development_evaluation_control.py",
)


def pipeline_fingerprint(worktree: Path) -> str:
    """SHA-256 over the replay-mechanics source files (sorted, length-prefixed)."""
    digest = hashlib.sha256()
    for relative in PIPELINE_FINGERPRINT_FILES:
        data = (Path(worktree) / relative).read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(relative.encode("utf-8"))
        digest.update(data)
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Index model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TickPartitionIndex:
    """Row-group timestamp boundaries for one monthly tick partition.

    ``row_groups`` holds ``(min_time_msc, max_time_msc, start_row, num_rows)``
    per row group, taken from Parquet footer statistics (no data read).
    """

    package_id: str
    path: str
    partition_sha256: str
    row_count: int
    row_groups: tuple[tuple[int, int, int, int], ...]


@dataclass(frozen=True)
class ReplayInputIndex:
    """Immutable, scenario-invariant causal input facts for one fold.

    ``decisions`` are the M5 completion tuples
    ``(available_at_ms, open_time_ms, timeframe, close, identity)`` in
    chronological order — exactly the facts the reference stream merges;
    nothing strategy-derived is precomputed.
    """

    schema: str
    plan_package_id: str
    plan_fingerprint: str
    fold_id: str
    decision_timeframe: str
    evaluation_start_ms: int
    evaluation_end_ms: int
    decisions: tuple[tuple[int, int, str, float, str], ...]
    partitions: tuple[TickPartitionIndex, ...]
    source_identities: Mapping[str, Any]
    pipeline_fingerprint: str
    builder_version: str
    index_sha256: str
    built_at_utc: str

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "plan_package_id": self.plan_package_id,
            "plan_fingerprint": self.plan_fingerprint,
            "fold_id": self.fold_id,
            "decision_timeframe": self.decision_timeframe,
            "evaluation_start_ms": self.evaluation_start_ms,
            "evaluation_end_ms": self.evaluation_end_ms,
            "decisions": [list(item) for item in self.decisions],
            "partitions": [
                {
                    "package_id": part.package_id,
                    "path": part.path,
                    "partition_sha256": part.partition_sha256,
                    "row_count": part.row_count,
                    "row_groups": [list(rg) for rg in part.row_groups],
                }
                for part in self.partitions
            ],
            "source_identities": self.source_identities,
            "pipeline_fingerprint": self.pipeline_fingerprint,
            "builder_version": self.builder_version,
        }


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def _partition_boundaries(parquet_path: Path) -> tuple[tuple[int, int, int, int], ...]:
    import pyarrow.parquet as pq  # noqa: PLC0415

    parquet_file = pq.ParquetFile(parquet_path)
    metadata = parquet_file.metadata
    column_index = parquet_file.schema_arrow.get_field_index("time_msc")
    bounded: list[tuple[int, int, int, int]] = []
    previous_max: int | None = None
    start_row = 0
    for group in range(metadata.num_row_groups):
        statistics = metadata.row_group(group).column(column_index).statistics
        if statistics is None or not statistics.has_min_max:
            raise EmpiricalPipelineError(
                f"tick partition lacks time_msc statistics: {parquet_path.name}"
            )
        low, high = int(statistics.min), int(statistics.max)
        if previous_max is not None and low < previous_max:
            raise EmpiricalPipelineError(
                f"row-group timestamps are not chronological: {parquet_path.name}"
            )
        previous_max = high
        num_rows = int(metadata.row_group(group).num_rows)
        bounded.append((low, high, start_row, num_rows))
        start_row += num_rows
    if start_row != int(metadata.num_rows):
        raise EmpiricalPipelineError(f"row-group row counts do not sum to total: {parquet_path.name}")
    return tuple(bounded)


def _partition_index(
    monthly_root: Path, package_id: str, declared_sha256: str | None
) -> TickPartitionIndex:
    partitions = _monthly_tick_partitions(monthly_root)
    if len(partitions) != 1:
        raise EmpiricalPipelineError(
            f"expected exactly one tick partition per monthly package: {monthly_root.name}"
        )
    parquet_path = partitions[0]
    observed_sha256 = _file_sha256(parquet_path)
    if declared_sha256 is not None and observed_sha256 != declared_sha256:
        raise EmpiricalPipelineError(
            f"tick partition bytes changed since acceptance: {parquet_path.name}"
        )
    import pyarrow.parquet as pq  # noqa: PLC0415

    row_count = int(pq.ParquetFile(parquet_path).metadata.num_rows)
    return TickPartitionIndex(
        package_id=str(package_id),
        path=str(parquet_path),
        partition_sha256=observed_sha256,
        row_count=row_count,
        row_groups=_partition_boundaries(parquet_path),
    )


def _package_dir(root: Path, package_id: str) -> Path:
    directory = Path(root) / package_id
    if not directory.is_dir():
        raise EmpiricalPipelineError(f"bound evidence package missing: {package_id}")
    return directory


def build_replay_input_index(
    bindings: Any,
    *,
    fold: Mapping[str, Any],
    worktree: Path | None = None,
    relaxed_identity: bool = False,
) -> ReplayInputIndex:
    """Build the immutable fold-scoped index from verified bindings.

    ``relaxed_identity`` is for SYNTHETIC FIXTURE bindings only (tests and the
    structural rehearsal): fixture packages carry no acceptance manifests, so
    identities fall back to direct file hashes.  Real builds keep the default
    strict mode and refuse on any missing manifest or changed hash.
    """
    import pandas as pd  # noqa: PLC0415

    plan = bindings.plan
    eval_start = int(pd.Timestamp(fold["evaluation"]["start"]).value // 1_000_000)
    eval_end = min(int(pd.Timestamp(fold["evaluation"]["end"]).value // 1_000_000), DEVELOPMENT_END_MS)
    if eval_start < DEVELOPMENT_START_MS or eval_start >= eval_end:
        raise EmpiricalPipelineError("fold evaluation interval outside the development period")

    decisions = [
        (int(available_at_ms), int(open_time_ms), str(timeframe), float(close), str(identity))
        for available_at_ms, open_time_ms, timeframe, close, identity in _candle_completion_events(
            bindings.candle_root,
            decision_timeframe=DECISION_TIMEFRAME,
            start_ms=eval_start,
            end_ms=eval_end,
        )
    ]
    if not decisions:
        raise EmpiricalPipelineError("fold contains no decision candles; index refuses to build")
    if decisions[-1][0] >= DEVELOPMENT_END_MS:
        raise EmpiricalPipelineError("decision at or after 2025-01-01 refused")

    year_root = Path(bindings.tick_year_root)
    source_identities: dict[str, Any] = {}
    if relaxed_identity:
        source_identities["mode"] = "SYNTHETIC_FIXTURE_RELAXED_IDENTITY"
        source_identities["year_package"] = {"package_id": year_root.name}
        monthly_manifest_sha256s: dict[str, str] = {}
        partitions = [
            _partition_index(Path(root), package_id, None)
            for root, package_id in zip(bindings.monthly_roots, [f"synthetic-{index}" for index in range(len(bindings.monthly_roots))])
        ]
    else:
        completion = json.loads((year_root / "package.complete.json").read_text(encoding="utf-8"))
        manifest_path = year_root / str(completion["manifest_relative_path"])
        manifest_sha256 = _file_sha256(manifest_path)
        completion_sha256 = _file_sha256(year_root / "package.complete.json")
        declared_manifest_sha256 = completion.get("manifest_sha256")
        if declared_manifest_sha256 is not None and declared_manifest_sha256 != manifest_sha256:
            raise EmpiricalPipelineError(
                "year completion manifest hash does not match manifest file; refusing to bind index"
            )
        source_identities["mode"] = "STRICT_ACCEPTED_PACKAGES"
        year_identity: dict[str, Any] = {
            "package_id": str(year_root.name),
            "manifest_sha256": manifest_sha256,
            "completion_sha256": completion_sha256,
        }
        # Content identity: prefer an explicit canonical normalized hash when the
        # package schema exposes one; otherwise the manifest's own SHA-256 is the
        # content identity (the completion marker is itself hash-bound above).
        if "canonical_normalized_sha256" in completion:
            year_identity["canonical_normalized_sha256"] = str(completion["canonical_normalized_sha256"])
            year_identity["canonical_hash_source"] = "completion"
        else:
            year_identity["canonical_normalized_sha256"] = manifest_sha256
            year_identity["canonical_hash_source"] = "manifest_file_sha256"
        year_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if "record_count" in completion:
            year_identity["record_count"] = int(completion["record_count"])
            year_identity["record_count_source"] = "completion"
        else:
            year_identity["record_count"] = int(
                sum(int(item["row_count"]) for item in year_manifest.get("monthly_packages", []))
            )
            year_identity["record_count_source"] = "year_manifest_monthly_row_counts"
        source_identities["year_package"] = year_identity
        monthly_manifest_sha256s = {}
        partitions = []
        # Package identity: monthly roots are the accepted package directories
        # (package_id == directory name).  Cross-check each against the year
        # manifest's monthly_packages so an unaccepted/renamed root fails here.
        manifest_by_id = {
            str(item.get("package_id")): item
            for item in year_manifest.get("monthly_packages", [])
        }
        package_ids: list[str] = []
        for monthly_root in bindings.monthly_roots:
            package_id = Path(monthly_root).name
            if package_id not in manifest_by_id:
                raise EmpiricalPipelineError(
                    f"monthly root is not an accepted package per year manifest: {package_id}"
                )
            package_ids.append(package_id)
        if len(package_ids) != len(manifest_by_id):
            raise EmpiricalPipelineError(
                "monthly root set does not cover the year manifest packages"
            )
        for monthly_root, package_id in zip(bindings.monthly_roots, package_ids):
            manifest_file = Path(monthly_root) / "manifest.json"
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            monthly_manifest_sha256s[str(package_id)] = _file_sha256(manifest_file)
            partitions.append(
                _partition_index(Path(monthly_root), str(package_id), str(manifest["partitions"][0]["sha256"]))
            )
        source_identities["monthly_manifest_sha256s"] = monthly_manifest_sha256s

    candle_sha256s = {
        timeframe: _file_sha256(
            Path(bindings.candle_root) / "candles" / "XAUUSDm" / timeframe / "year=2024" / "part-00000.parquet"
        )
        for timeframe in ("M5", "M15", "H1", "H4", "D1", "W1")
    }
    dxy_sha256s = {
        parquet_file.name: _file_sha256(parquet_file)
        for parquet_file in sorted((Path(bindings.dxy_root) / "constituents").glob("*.parquet"))
    }
    source_identities["candle_partition_sha256s"] = candle_sha256s
    source_identities["dxy_partition_sha256s"] = dxy_sha256s

    if not relaxed_identity:
        evidence_root = Path(bindings.evidence_root)
        news_pkg = bindings.news_package
        news_package_id = news_pkg.get(
            "package_id",
            news_pkg.get("manifest", {}).get("package_id"),
        )
        if not news_package_id:
            raise ValueError(
                "news package identity missing from bindings "
                f"(keys={sorted(news_pkg.keys())})"
            )
        evidence_identities = {}
        for label, package_id in (
            ("official_news", str(news_package_id)),
            ("cost_policy", str(bindings.cost_policy_package_id)),
            ("metadata_bounds", str(bindings.metadata_bounds_package_id)),
        ):
            evidence_identities[label] = _file_sha256(_package_dir(evidence_root, package_id) / "package.json")
        source_identities["evidence_package_sha256s"] = evidence_identities
    else:
        source_identities["evidence_package_sha256s"] = {"mode": "SYNTHETIC_FIXTURE"}

    worktree_path = Path(worktree) if worktree is not None else _repo_root()
    index = ReplayInputIndex(
        schema=INDEX_SCHEMA,
        plan_package_id=str(plan.get("plan_id", plan.get("plan_fingerprint", "synthetic"))),
        plan_fingerprint=str(plan["plan_fingerprint"]),
        fold_id=str(fold["fold_id"]),
        decision_timeframe=DECISION_TIMEFRAME,
        evaluation_start_ms=eval_start,
        evaluation_end_ms=eval_end,
        decisions=tuple(decisions),
        partitions=tuple(partitions),
        source_identities=source_identities,
        pipeline_fingerprint=pipeline_fingerprint(worktree_path),
        builder_version=INDEX_BUILDER_VERSION,
        index_sha256="",
        built_at_utc=datetime.now(UTC).isoformat(),
    )
    return _with_sha256(index, canonical_hash(index.canonical_payload()))


def _with_sha256(index: ReplayInputIndex, digest: str) -> ReplayInputIndex:
    return ReplayInputIndex(
        schema=index.schema,
        plan_package_id=index.plan_package_id,
        plan_fingerprint=index.plan_fingerprint,
        fold_id=index.fold_id,
        decision_timeframe=index.decision_timeframe,
        evaluation_start_ms=index.evaluation_start_ms,
        evaluation_end_ms=index.evaluation_end_ms,
        decisions=index.decisions,
        partitions=index.partitions,
        source_identities=index.source_identities,
        pipeline_fingerprint=index.pipeline_fingerprint,
        builder_version=index.builder_version,
        index_sha256=digest,
        built_at_utc=index.built_at_utc,
    )


# ---------------------------------------------------------------------------
# Publish / load / verify (atomic, non-overwriting, readback)
# ---------------------------------------------------------------------------


def publish_input_index(index: ReplayInputIndex, *, evidence_root: Path) -> tuple[Path, str]:
    """Atomically publish the index; refuses overwrite; verifies readback."""
    root = Path(evidence_root) / INDEX_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    name = f"{index.fold_id}-{index.index_sha256[:16]}"
    target = root / name
    if target.exists():
        raise EmpiricalPipelineError(f"index already published: {name}")
    staging = root / f".staging-{name}"
    if staging.exists():
        # Leftover from a failed previous publication of the SAME content;
        # remove only the stale staging directory, never any published index.
        for stale in sorted(staging.rglob("*"), reverse=True):
            if stale.is_file():
                stale.unlink()
        staging.rmdir()
    staging.mkdir(parents=True)
    payload = {
        "schema": INDEX_SCHEMA,
        "label": "SCENARIO-INVARIANT CAUSAL INPUT INDEX — NOT STRATEGY EVIDENCE",
        "built_at_utc": index.built_at_utc,
        "index_sha256": index.index_sha256,
        "index": index.canonical_payload(),
    }
    index_file = staging / "index.json"
    index_file.write_text(json.dumps(payload, sort_keys=True, indent=1), encoding="utf-8")
    file_sha256 = _file_sha256(index_file)
    marker = {
        "status": "COMPLETE",
        "index_sha256": index.index_sha256,
        "file_sha256": file_sha256,
        "fold_id": index.fold_id,
    }
    (staging / COMPLETE_MARKER).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")
    if target.exists():
        raise EmpiricalPipelineError(f"index already published: {name}")
    staging.replace(target)
    loaded = load_input_index(target)
    if loaded.index_sha256 != index.index_sha256:
        raise EmpiricalPipelineError("index readback hash mismatch")
    return target, index.index_sha256


def load_input_index(path: Path, *, worktree: Path | None = None) -> ReplayInputIndex:
    """Load and structurally verify a published index."""
    path = Path(path)
    payload = json.loads((path / "index.json").read_text(encoding="utf-8"))
    marker = json.loads((path / COMPLETE_MARKER).read_text(encoding="utf-8"))
    if marker.get("status") != "COMPLETE" or marker.get("index_sha256") != payload.get("index_sha256"):
        raise EmpiricalPipelineError(f"index completion marker invalid: {path.name}")
    if marker.get("file_sha256") != _file_sha256(path / "index.json"):
        raise EmpiricalPipelineError(f"index file bytes changed after publication: {path.name}")
    raw = payload["index"]
    if raw["schema"] != INDEX_SCHEMA:
        raise EmpiricalPipelineError("index schema mismatch")
    index = ReplayInputIndex(
        schema=raw["schema"],
        plan_package_id=raw["plan_package_id"],
        plan_fingerprint=raw["plan_fingerprint"],
        fold_id=raw["fold_id"],
        decision_timeframe=raw["decision_timeframe"],
        evaluation_start_ms=int(raw["evaluation_start_ms"]),
        evaluation_end_ms=int(raw["evaluation_end_ms"]),
        decisions=tuple(
            (int(item[0]), int(item[1]), str(item[2]), float(item[3]), str(item[4]))
            for item in raw["decisions"]
        ),
        partitions=tuple(
            TickPartitionIndex(
                package_id=part["package_id"],
                path=part["path"],
                partition_sha256=part["partition_sha256"],
                row_count=int(part["row_count"]),
                row_groups=tuple(
                    (int(group[0]), int(group[1]), int(group[2]), int(group[3]))
                    for group in part["row_groups"]
                ),
            )
            for part in raw["partitions"]
        ),
        source_identities=raw["source_identities"],
        pipeline_fingerprint=raw["pipeline_fingerprint"],
        builder_version=raw["builder_version"],
        index_sha256=payload["index_sha256"],
        built_at_utc=payload.get("built_at_utc", ""),
    )
    if canonical_hash(index.canonical_payload()) != index.index_sha256:
        raise EmpiricalPipelineError("index canonical hash mismatch (tampered or stale)")
    if worktree is not None and pipeline_fingerprint(worktree) != index.pipeline_fingerprint:
        raise EmpiricalPipelineError(
            "index pipeline fingerprint drifted from current code; rebuild required"
        )
    return index


def find_published_index(evidence_root: Path, *, fold_id: str, index_sha256: str) -> Path:
    target = Path(evidence_root) / INDEX_DIR_NAME / f"{fold_id}-{index_sha256[:16]}"
    if not target.is_dir():
        raise EmpiricalPipelineError(f"published index missing: {target.name}")
    return target


def verify_index_matches_bindings(index: ReplayInputIndex, bindings: Any) -> dict[str, Any]:
    """Re-check the index's source identities against live bindings (read-only)."""
    if index.source_identities.get("mode") == "SYNTHETIC_FIXTURE_RELAXED_IDENTITY":
        if len(index.partitions) != len(tuple(bindings.monthly_roots)):
            raise EmpiricalPipelineError("index partition count mismatch")
    else:
        year_root = Path(bindings.tick_year_root)
        completion = json.loads((year_root / "package.complete.json").read_text(encoding="utf-8"))
        expected_year = index.source_identities["year_package"]
        if expected_year["package_id"] != year_root.name:
            raise EmpiricalPipelineError("index year package mismatch")
        current_manifest_sha256 = _file_sha256(
            year_root / str(completion["manifest_relative_path"])
        )
        if expected_year.get("manifest_sha256") != current_manifest_sha256:
            raise EmpiricalPipelineError("year package manifest changed since index build")
        current_canonical = str(
            completion.get(
                "canonical_normalized_sha256",
                current_manifest_sha256,
            )
        )
        if expected_year["canonical_normalized_sha256"] != current_canonical:
            raise EmpiricalPipelineError("year package content changed since index build")
        if len(index.partitions) != len(tuple(bindings.monthly_roots)):
            raise EmpiricalPipelineError("index partition count mismatch")
    for part, monthly_root in zip(index.partitions, bindings.monthly_roots):
        discovered = _monthly_tick_partitions(Path(monthly_root))
        if len(discovered) != 1 or _file_sha256(discovered[0]) != part.partition_sha256:
            raise EmpiricalPipelineError(f"tick partition changed since index build: {part.package_id}")
    worktree_for_fingerprint = Path(bindings.worktree) if getattr(bindings, "worktree", None) else _repo_root()
    current_fingerprint = pipeline_fingerprint(worktree_for_fingerprint)
    if current_fingerprint != index.pipeline_fingerprint:
        raise EmpiricalPipelineError("pipeline fingerprint drifted from index; rebuild required")
    if index.decisions and index.decisions[-1][0] >= DEVELOPMENT_END_MS:
        raise EmpiricalPipelineError("index contains a holdout timestamp")
    return {
        "verified": True,
        "fold_id": index.fold_id,
        "decisions": len(index.decisions),
        "partitions": len(index.partitions),
        "pipeline_fingerprint": current_fingerprint,
    }


# ---------------------------------------------------------------------------
# Persistent vectorized quote cursor
# ---------------------------------------------------------------------------

COLUMNS = ["time_msc", "bid", "ask", "sequence_id", "provenance_id", "source_member", "row_identity"]


class QuoteCursor:
    """Persistent, forward-only quote cursor over the indexed partitions.

    Walks row groups in chronological order, decoding each at most once and
    only when its window can intersect the fold.  All skipping is explicit and
    counted; chronology across row-group and partition boundaries is verified.
    """

    def __init__(
        self, index: ReplayInputIndex, *, start_ms: int, end_ms: int,
        batch_rows: int = DEFAULT_BATCH_ROWS,
    ) -> None:
        if not (DEVELOPMENT_START_MS <= start_ms < end_ms <= DEVELOPMENT_END_MS):
            raise EmpiricalPipelineError("quote window outside the development period")
        if int(batch_rows) < 1:
            raise EmpiricalPipelineError("cursor batch_rows must be at least 1")
        self.index = index
        self.start_ms = int(start_ms)
        self.end_ms = int(end_ms)
        self.batch_rows = int(batch_rows)
        self.part_pos = 0
        self.rg_pos = 0
        self.row_pos = 0
        self._times: np.ndarray | None = None
        self._columns: dict[str, list[Any]] | None = None
        self._rg_low = 0
        self._rg_high = 0
        self.exhausted = False
        self.last_timestamp: int | None = None
        self.row_groups_decoded = 0
        self.rows_emitted = 0
        self.rows_skipped = 0
        self._decoded_rgs: set[tuple[str, int]] = set()
        self._restored = False

    def _open(self, part_index: int) -> Any:
        import pyarrow.parquet as pq  # noqa: PLC0415

        part = self.index.partitions[part_index]
        path = Path(part.path)
        if not path.is_file():
            raise EmpiricalPipelineError(f"indexed tick partition missing: {part.path}")
        return pq.ParquetFile(path)

    def _decode(self) -> None:
        part = self.index.partitions[self.part_pos]
        group = self.rg_pos
        if (part.package_id, group) in self._decoded_rgs:
            raise EmpiricalPipelineError("row group decoded twice (cursor invariant violated)")
        self._decoded_rgs.add((part.package_id, group))
        parquet_file = self._open(self.part_pos)
        table = parquet_file.read_row_group(group, columns=COLUMNS)
        self.row_groups_decoded += 1
        data = table.to_pydict()
        times = np.asarray(data.pop("time_msc"), dtype=np.int64)
        if times.size and bool(np.any(np.diff(times) < 0)):
            raise EmpiricalPipelineError(f"tick inversion inside row group: {part.package_id}#{group}")
        self._times = times
        self._columns = data
        self._rg_low, self._rg_high = times[0], times[-1] if times.size else (0, 0)
        boundary = int(np.searchsorted(times, self.start_ms, side="left"))
        if self._restored:
            # Restored mid-row-group: keep the checkpointed position (never
            # re-process consumed rows, never skip unconsumed rows).
            self.row_pos = max(boundary, min(self.row_pos, times.size))
            self._restored = False
        else:
            self.row_pos = boundary

    def _advance(self) -> None:
        part = self.index.partitions[self.part_pos]
        if self.rg_pos + 1 < len(part.row_groups):
            self.rg_pos += 1
            self._times = None
            self._columns = None
            return
        if self.part_pos + 1 < len(self.index.partitions):
            self.part_pos += 1
            self.rg_pos = 0
            self._times = None
            self._columns = None
            return
        self.exhausted = True

    def peek_timestamp(self) -> int | None:
        """Timestamp of the next quote without consuming it (None if exhausted).

        Decodes the current row group when necessary; never advances position.
        Enables exact decision-before-quote merge semantics.
        """
        while not self.exhausted:
            part = self.index.partitions[self.part_pos]
            low, high, _, _ = part.row_groups[self.rg_pos]
            if high < self.start_ms or low >= self.end_ms:
                self._advance()
                continue
            if self._times is None:
                self._decode()
            times = self._times
            assert times is not None
            if self.row_pos >= times.size:
                self._advance()
                continue
            stamp = int(times[self.row_pos])
            if stamp >= self.end_ms:
                self.exhausted = True
                break
            if stamp < self.start_ms:
                self.row_pos += 1
                continue
            return stamp
        return None

    def next_quote(self) -> dict[str, Any] | None:
        """Next executable quote in [start, end), or None when exhausted."""
        while not self.exhausted:
            part = self.index.partitions[self.part_pos]
            low, high, _, _ = part.row_groups[self.rg_pos]
            if high < self.start_ms or low >= self.end_ms:
                self._advance()
                continue
            if self._times is None:
                self._decode()
            times = self._times
            assert times is not None and self._columns is not None
            if self.row_pos >= times.size:
                self._advance()
                continue
            stamp = int(times[self.row_pos])
            if stamp >= self.end_ms:
                self.exhausted = True
                break
            if stamp < self.start_ms:
                self.row_pos += 1
                self.rows_skipped += 1
                continue
            offset = self.row_pos
            self.row_pos += 1
            self.last_timestamp = stamp
            self.rows_emitted += 1
            return {
                "timestamp_ms": stamp,
                "bid": float(self._columns["bid"][offset]),
                "ask": float(self._columns["ask"][offset]),
                "sequence_id": str(self._columns["sequence_id"][offset]),
                "provenance_id": str(self._columns["provenance_id"][offset]),
                "source_chunk_id": str(self._columns["source_member"][offset]),
                "row_identity": str(self._columns["row_identity"][offset]),
            }
        return None

    def next_unconsumed(self, consumed: set[str]) -> dict[str, Any] | None:
        """Next quote whose identity is not already consumed (resume path)."""
        while True:
            quote = self.next_quote()
            if quote is None:
                return None
            if f"quote:{quote['sequence_id']}" in consumed:
                continue
            return quote

    def cursor_state(self) -> dict[str, Any]:
        """Serializable cursor position for exact optimized-resume checkpoints."""
        return {
            "part_pos": self.part_pos,
            "rg_pos": self.rg_pos,
            "row_pos": self.row_pos,
            "exhausted": self.exhausted,
            "last_timestamp": self.last_timestamp,
            "row_groups_decoded": self.row_groups_decoded,
            "rows_emitted": self.rows_emitted,
            "rows_skipped": self.rows_skipped,
        }

    def restore_cursor_state(self, state: Mapping[str, Any]) -> None:
        """Restore an exact cursor position (same index required)."""
        if self._times is not None or self._columns is not None:
            raise EmpiricalPipelineError("cursor restore requires an undecoded cursor")
        part_pos = int(state["part_pos"])
        rg_pos = int(state["rg_pos"])
        row_pos = int(state["row_pos"])
        if not (0 <= part_pos < len(self.index.partitions)):
            raise EmpiricalPipelineError("cursor restore: partition position out of range")
        part = self.index.partitions[part_pos]
        if not (0 <= rg_pos < len(part.row_groups)):
            raise EmpiricalPipelineError("cursor restore: row-group position out of range")
        _, _, _start_row, num_rows = part.row_groups[rg_pos]
        # row_pos is row-group-relative.
        if not (0 <= row_pos <= num_rows):
            raise EmpiricalPipelineError("cursor restore: row position outside row group")
        self.part_pos = part_pos
        self.rg_pos = rg_pos
        self.row_pos = row_pos
        self.exhausted = bool(state["exhausted"])
        last = state.get("last_timestamp")
        self.last_timestamp = None if last is None else int(last)
        self.row_groups_decoded = int(state["row_groups_decoded"])
        self.rows_emitted = int(state["rows_emitted"])
        self.rows_skipped = int(state["rows_skipped"])
        self._restored = not self.exhausted

    def skip_through(self, through_ms: int) -> int:
        """Advance past every quote with timestamp <= through_ms without emitting.

        Returns the number of skipped quotes.  Used only in the IDLE state;
        skipped quotes are the state-function-proven irrelevant ticks.
        """
        skipped = 0
        while not self.exhausted:
            part = self.index.partitions[self.part_pos]
            low, high, _, _ = part.row_groups[self.rg_pos]
            if high < self.start_ms or low >= self.end_ms:
                self._advance()
                continue
            if high <= through_ms:
                # Whole row group is skippable without decoding.
                size = part.row_groups[self.rg_pos][3]
                skipped += size
                self.rows_skipped += size
                self.last_timestamp = high
                self._times = None
                self._columns = None
                self._advance()
                continue
            if self._times is None:
                self._decode()
            times = self._times
            assert times is not None
            target = int(np.searchsorted(times, through_ms, side="right"))
            if target > self.row_pos:
                skipped += target - self.row_pos
                self.rows_skipped += target - self.row_pos
                self.row_pos = target
            if self.row_pos < times.size and int(times[self.row_pos]) < self.end_ms:
                self.last_timestamp = int(times[self.row_pos - 1]) if self.row_pos > 0 else self.last_timestamp
                return skipped
            self._advance()
        return skipped


def latest_quote_at_or_before(
    index: ReplayInputIndex, *, at_ms: int
) -> dict[str, Any] | None:
    """Latest executable quote with timestamp <= at_ms (deterministic search).

    Utility for benchmark statistics and verification.  The frozen fill
    semantics remain: intents trigger on the next executable quote after the
    decision — this function never feeds fills.
    """
    import pyarrow.parquet as pq  # noqa: PLC0415

    if at_ms < index.evaluation_start_ms:
        return None
    ceiling = min(int(at_ms), index.evaluation_end_ms - 1)
    best: dict[str, Any] | None = None
    for part in index.partitions:
        path = Path(part.path)
        if not path.is_file():
            raise EmpiricalPipelineError(f"indexed tick partition missing: {part.path}")
        parquet_file = pq.ParquetFile(path)
        for group, (low, high, _, _) in enumerate(part.row_groups):
            if low > ceiling:
                break
            if high < index.evaluation_start_ms:
                continue
            table = parquet_file.read_row_group(group, columns=COLUMNS)
            times = np.asarray(table.column("time_msc").to_pylist(), dtype=np.int64)
            position = int(np.searchsorted(times, ceiling, side="right")) - 1
            if position < 0:
                continue
            stamp = int(times[position])
            if best is not None and stamp <= int(best["timestamp_ms"]):
                continue
            best = {
                "timestamp_ms": stamp,
                "bid": float(table.column("bid")[position].as_py()),
                "ask": float(table.column("ask")[position].as_py()),
                "sequence_id": str(table.column("sequence_id")[position].as_py()),
                "provenance_id": str(table.column("provenance_id")[position].as_py()),
                "source_chunk_id": str(table.column("source_member")[position].as_py()),
                "row_identity": str(table.column("row_identity")[position].as_py()),
            }
    return best


# ---------------------------------------------------------------------------
# Optimized cell driver (event-driven tick processing)
# ---------------------------------------------------------------------------


class OptimizedCellDriver:
    """State-machine driver over the indexed stream (semantics preserved).

    Replaces always-every-event iteration with state-dependent processing:

    - IDLE (no pending intent, no open position): intermediate quotes are
      skipped by the persistent cursor; the driver processes the next decision
      event directly.
    - ACTIVE (entry intent pending or position open): every quote is processed
      in exact chronological order until the cell is idle again — covering
      trigger/fill, cancellation, invalidation, expiry, stop, target, partial
      close, break-even, trailing, emergency/circuit action, swap/rollover.

    The cursor is always positioned at the first unprocessed quote, so a
    decision that creates an intent sees exactly the same trigger quote the
    reference stream would deliver next.  Idleness proof: with no pending
    intent and no open position, ``on_quote`` performs no lifecycle
    transition, no ledger entry and no durable change — only the quote
    sequence counter advances and an equity snapshot is appended that the
    next processed quote overwrites.  Skipped quotes cannot change any state,
    decision, fill, cost or outcome (equivalence-tested).
    """

    def __init__(
        self, context: Any, handler: Any, *, index: ReplayInputIndex,
        quote_cursor: QuoteCursor | None = None,
    ) -> None:
        self.context = context
        self.handler = handler
        self.index = index
        if quote_cursor is None:
            quote_cursor = QuoteCursor(
                index, start_ms=index.evaluation_start_ms, end_ms=index.evaluation_end_ms
            )
        self.cursor = quote_cursor

    def cursor_state(self) -> dict[str, Any]:
        """Durable cursor position for exact optimized-cell checkpoints."""
        return self.cursor.cursor_state()

    def restore_cursor(self, state: Mapping[str, Any]) -> None:
        """Restore the exact cursor position captured at a checkpoint."""
        self.cursor.restore_cursor_state(state)

    def _active(self) -> bool:
        context = self.context
        return bool(context.pending_intents) or bool(context.lifecycle_positions)

    def _emit_quote(self, quote: Mapping[str, Any]) -> None:
        from datetime import datetime, timezone as _tz  # noqa: PLC0415

        context = self.context
        full_event = {**quote, "event_kind": "QUOTE", "event_id": f"quote:{quote['sequence_id']}"}
        self.handler.on_quote(full_event)
        stamp = datetime.fromtimestamp((quote["timestamp_ms"] // 3_600_000) * 3600, tz=_tz.utc)
        self.handler.on_session_boundary(stamp)
        context.consumed_event_keys.add(full_event["event_id"])

    def run(
        self, *,
        checkpoint_every: int = 100_000,
        on_checkpoint: Any = None,
        counters: dict[str, int] | None = None,
        batch_rows: int | None = None,
        max_processed: int | None = None,
        finish: bool = True,
    ) -> dict[str, Any]:
        from datetime import datetime, timezone as _tz  # noqa: PLC0415

        from bot.validation.empirical_input_pipeline import serialize_cell_state  # noqa: PLC0415

        context = self.context
        index = self.index
        if batch_rows is not None:
            if int(batch_rows) < 1:
                raise EmpiricalPipelineError("batch_rows must be at least 1")
            self.cursor.batch_rows = int(batch_rows)
        stats = counters if counters is not None else {}
        stats.setdefault("decisions_processed", 0)
        stats.setdefault("active_quotes_processed", 0)
        stats.setdefault("idle_quotes_skipped", 0)
        stats.setdefault("idle_spans", 0)
        stats.setdefault("row_groups_decoded", 0)
        stats.setdefault("row_groups_total", sum(len(part.row_groups) for part in index.partitions))
        stats.setdefault("last_event_ts_ms", 0)

        processed = 0
        since_checkpoint = 0
        last_event_key: str | None = None
        last_quote: dict[str, Any] | None = None
        last_quote_ts: int | None = None
        consumed = context.consumed_event_keys

        max_processed = (
            int(max_processed) if max_processed is not None else None
        )

        def maybe_checkpoint() -> None:
            nonlocal since_checkpoint
            if on_checkpoint is not None and since_checkpoint >= max(1, int(checkpoint_every)):
                payload = dict(serialize_cell_state(context))
                payload["quote_cursor_state"] = self.cursor_state()
                payload["input_index_sha256"] = index.index_sha256
                payload["batch_rows"] = int(self.cursor.batch_rows)
                on_checkpoint(last_event_key, payload)
                since_checkpoint = 0

        decision_index = 0
        while True:
            # Skip already-consumed decisions (resume).
            while (
                decision_index < len(index.decisions)
                and f"decision:{index.decisions[decision_index][4]}" in consumed
            ):
                decision_index += 1
            has_decision = decision_index < len(index.decisions)
            active = self._active()
            peek_ts = self.cursor.peek_timestamp()
            if not has_decision and peek_ts is None and not active:
                break
            if max_processed is not None and processed >= max_processed and not active:
                break

            def process_decision() -> None:
                nonlocal decision_index, processed, last_event_key
                available_at_ms, open_time_ms, timeframe, close, identity = index.decisions[decision_index]
                decision_id = f"decision:{identity}"
                event = {
                    "event_kind": "DECISION",
                    "timestamp_ms": available_at_ms,
                    "decision_for_open_ms": open_time_ms,
                    "timeframe": timeframe,
                    "source_close": close,
                    "candle_identity": identity,
                    "event_id": decision_id,
                }
                self.handler.on_signal(event)
                stamp = datetime.fromtimestamp((available_at_ms // 3_600_000) * 3600, tz=_tz.utc)
                self.handler.on_session_boundary(stamp)
                consumed.add(decision_id)
                last_event_key = decision_id
                decision_index += 1
                processed += 1
                stats["decisions_processed"] += 1
                stats["last_event_ts_ms"] = available_at_ms

            if has_decision and (peek_ts is None or index.decisions[decision_index][0] <= peek_ts):
                # Decision fires before the next unprocessed quote (or no quote
                # follows) — exactly the reference merge order.
                process_decision()
                continue

            if active:
                # -- full tick processing until idle --------------------------
                while self._active():
                    quote = self.cursor.next_unconsumed(consumed)
                    if quote is None:
                        break
                    self._emit_quote(quote)
                    last_quote = quote
                    last_quote_ts = int(quote["timestamp_ms"])
                    last_event_key = f"quote:{quote['sequence_id']}"
                    processed += 1
                    stats["active_quotes_processed"] += 1
                    stats["last_event_ts_ms"] = last_quote_ts
                    since_checkpoint += 1
                    maybe_checkpoint()
                    if self._active():
                        # Deferred decision due before the next quote fires
                        # first (decision-before-quote, reference merge).
                        while (
                            decision_index < len(index.decisions)
                            and f"decision:{index.decisions[decision_index][4]}" in consumed
                        ):
                            decision_index += 1
                        if (
                            decision_index < len(index.decisions)
                            and index.decisions[decision_index][0] <= self.cursor.peek_timestamp()
                            if self.cursor.peek_timestamp() is not None
                            else decision_index < len(index.decisions)
                        ):
                            available_at_ms = index.decisions[decision_index][0]
                            identity = index.decisions[decision_index][4]
                            decision_id = f"decision:{identity}"
                            event = {
                                "event_kind": "DECISION",
                                "timestamp_ms": available_at_ms,
                                "decision_for_open_ms": index.decisions[decision_index][1],
                                "timeframe": index.decisions[decision_index][2],
                                "source_close": index.decisions[decision_index][3],
                                "candle_identity": identity,
                                "event_id": decision_id,
                            }
                            self.handler.on_signal(event)
                            stamp = datetime.fromtimestamp((available_at_ms // 3_600_000) * 3600, tz=_tz.utc)
                            self.handler.on_session_boundary(stamp)
                            consumed.add(decision_id)
                            last_event_key = decision_id
                            decision_index += 1
                            processed += 1
                            stats["decisions_processed"] += 1
                if self._active():
                    # Quote stream exhausted while still active: end of fold.
                    break
                stats["idle_spans"] += 1
                continue

            # -- idle span: skip irrelevant quotes up to the next decision ----
            stats["idle_spans"] += 1
            next_available = int(index.decisions[decision_index][0])
            skipped = self.cursor.skip_through(next_available - 1)
            stats["idle_quotes_skipped"] += skipped
            stats["row_groups_decoded"] = self.cursor.row_groups_decoded
            maybe_checkpoint()

        stats["row_groups_decoded"] = self.cursor.row_groups_decoded
        if on_checkpoint is not None:
            payload = dict(serialize_cell_state(context))
            payload["quote_cursor_state"] = self.cursor_state()
            payload["input_index_sha256"] = index.index_sha256
            payload["batch_rows"] = int(self.cursor.batch_rows)
            on_checkpoint(last_event_key, payload)
        if finish:
            self.handler.finish_fold(last_quote)
        return {
            "events_processed": processed,
            "last_event_key": last_event_key,
            "decisions": len(context.decisions),
            "fills": len(context.engine.fills),
            "rejections": len(context.engine.rejections),
            "final_balance": context.engine.account.balance,
            "final_equity": context.engine.account.equity,
            "driver_stats": dict(stats),
        }
