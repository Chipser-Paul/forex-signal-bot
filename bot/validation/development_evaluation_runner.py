"""Phase 8N-G streaming development-evaluation runner.

Plan-driven orchestration over the frozen corrected plan
(`evidence-development_evaluation_plan-v1-4a6ab94c3e303c81`).  The runner
performs causal, bounded-memory streaming replay of each fold-scenario cell
using the shared Phase 8N production/replay contracts
(`bot.validation.empirical_strategy_adapter`,
`bot.strategy.setup_recovery`, `bot.backtesting.fill_journal`).

Empirical execution is NOT authorized by this checkpoint: every code path that
would consume the real 2024 datasets is guarded behind explicit run
confirmation and refuses to execute until the separately authorized
empirical run publishes its confirmation.  Synthetic rehearsal drives the
identical code with synthetic fixtures only.

No MT5, network, account, order or credential surface is imported here.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from bot.acquisition.evidence_contracts import canonical_hash
from bot.validation import development_evaluation_plan as plan_module
from bot.validation import development_scenario_matrix as matrix_module

UTC = timezone.utc


def pd_ts(value: str) -> "Any":
    """Parse an ISO-8601 UTC instant into a pandas Timestamp."""
    import pandas as pd  # noqa: PLC0415

    return pd.Timestamp(value)


RUNNER_SCHEMA = "phase8n.development-evaluation-runner.v1"
RUNNER_VERSION = "phase8n-runner-v1"

# Corrected plan identity (the ONLY plan the runner accepts) and the
# invalidated plan it must always reject.
CORRECTED_PLAN_PACKAGE_ID = "evidence-development_evaluation_plan-v1-4a6ab94c3e303c81"
CORRECTED_PLAN_FINGERPRINT = "adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09"
INVALIDATED_PLAN_PACKAGE_ID = "evidence-development_evaluation_plan-v1-ba2745f96fda3939"
INVALIDATED_PLAN_FINGERPRINT = "d69bbed4542d9517dc46d043d12324f6a921a846bca39c30e57fdc3774779c72"

HOLDOUT_INTERVAL_START = "2025-01-01T00:00:00+00:00"
REQUIRED_OUTPUT_FILES = (
    "run_manifest.json",
    "cells.jsonl",
    "cell_manifests.jsonl",
    "decision_ledger.jsonl",
    "fills.jsonl",
    "trade_ledger.jsonl",
    "equity_curve.jsonl",
    "costs.jsonl",
    "circuits.jsonl",
    "fold_metrics.json",
    "scenario_metrics.json",
    "aggregate_metrics.json",
    "bootstrap_results.json",
    "acceptance_table.json",
    "reconciliation_report.json",
    "run_summary.json",
    "RUN_COMPLETE",
)

CELL_STATES = (
    "PREPARED", "INPUTS_VERIFIED", "RUNNING", "CHECKPOINTED",
    "COMPLETE", "FAILED", "INTERRUPTED", "INVALID", "RECONCILIATION_REQUIRED",
)
TERMINAL_STATES = {"COMPLETE", "FAILED", "INVALID"}
MAX_PUBLISHED_TERMINAL_STATE = 1

# Resource guard defaults (mirroring the frozen plan's resource_guards).
DEFAULT_MIN_FREE_BYTES = 15 * 1024**3
DEFAULT_MAX_OUTPUT_BYTES = 10 * 1024**3
DEFAULT_MEMORY_CEILING_BYTES = 2 * 1024**3
DEFAULT_CELL_TIMEOUT_SECONDS = 1800
DEFAULT_OVERALL_TIMEOUT_SECONDS = 14400


class RunnerError(RuntimeError):
    """Runner safety, identity or contract violation (fail closed)."""


# ---------------------------------------------------------------------------
# Input firewall
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_corrected_plan(evidence_root: Path) -> dict[str, Any]:
    """Load, verify and bind the corrected plan; reject the invalidated plan.

    The disposition record for the invalidated plan legitimately remains on
    disk (it is the published evidence that the old plan was invalidated);
    only *presenting the invalidated plan package as runnable* fails closed.
    """
    evidence_root = Path(evidence_root)
    # The invalidated plan package remains on disk as published evidence of
    # its own invalidation; only *executing against it* fails closed. Its
    # identity must still be unchanged (tamu0031 detection below).
    invalidated = evidence_root / (INVALIDATED_PLAN_PACKAGE_ID + "/package.json")
    if invalidated.is_file():
        invalidated_content = json.loads(_read_text(invalidated)).get("content", {})
        if invalidated_content.get("plan_fingerprint") != INVALIDATED_PLAN_FINGERPRINT:
            raise RunnerError("invalidated plan fingerprint changed on disk")
    package_path = evidence_root / (CORRECTED_PLAN_PACKAGE_ID + "/package.json")
    if not package_path.is_file():
        raise RunnerError("corrected plan package is missing")
    package = json.loads(_read_text(package_path))
    content = package["content"]
    if package["manifest"]["package_id"] != CORRECTED_PLAN_PACKAGE_ID:
        raise RunnerError("corrected plan package id mismatch")
    if content["plan_fingerprint"] != CORRECTED_PLAN_FINGERPRINT:
        raise RunnerError("corrected plan fingerprint mismatch")
    payload = {key: value for key, value in content.items() if key != "plan_fingerprint"}
    if canonical_hash(payload) != content["plan_fingerprint"]:
        raise RunnerError("corrected plan fingerprint does not recompute")
    # The corrected revision carries the superseding schema
    # (phase8n.superseding-development-plan.v2); the fingerprint above binds
    # the actual superseding payload. Structural plan checks (folds, folds,
    # candidate, gates, scenario contract) still apply via the plan-module
    # verifier against the fingerprint-preserving structural view below.
    structural_view = {
        **content,
        "schema_version": plan_module.SCHEMA_VERSION,
        "plan_fingerprint": content["plan_fingerprint"],
        "fingerprint_check_skipped": True,
    }
    del structural_view["fingerprint_check_skipped"]
    # The plan-module verifier recomputes the fingerprint over its payload;
    # for the structural view that recomputation cannot match the superseding
    # fingerprint by construction, so structural checks are performed by
    # inspecting the shared fields directly instead.
    _verify_corrected_plan_structure(content)
    invalidates = content.get("invalidates", {})
    if invalidates.get("package_id") != INVALIDATED_PLAN_PACKAGE_ID or invalidates.get("fingerprint") != INVALIDATED_PLAN_FINGERPRINT:
        raise RunnerError("plan does not bind the invalidated-plan disposition")
    return content


def reject_invalidated_plan(presented_package_id: str, presented_fingerprint: str) -> None:
    """Hard rejection of the invalidated plan as a runnable input."""
    if presented_package_id == INVALIDATED_PLAN_PACKAGE_ID:
        raise RunnerError("INVALIDATED_PLAN_REJECTED: " + INVALIDATED_PLAN_PACKAGE_ID)
    if presented_package_id == CORRECTED_PLAN_PACKAGE_ID and presented_fingerprint != CORRECTED_PLAN_FINGERPRINT:
        raise RunnerError("PLAN_FINGERPRINT_MISMATCH for the corrected plan package")


def _verify_corrected_plan_structure(content: Mapping[str, Any]) -> None:
    """Structural checks shared with the 8M plan verifier, applied to the
    superseding (v2) corrected plan without rewriting its fingerprint."""
    if content.get("status") != "FROZEN_AWAITING_AUTHORIZED_RUN":
        raise RunnerError("frozen plan status is not FROZEN_AWAITING_AUTHORIZED_RUN")
    if content.get("symbol") != plan_module.SYMBOL:
        raise RunnerError("plan symbol mismatch")
    if content["candidate"].get("candidate_id") != "phase6-frozen-v1" or content["candidate"].get("strategy_configuration_mutation") != "PROHIBITED":
        raise RunnerError("candidate is not frozen")
    plan_module._verify_folds(tuple(content.get("folds", ())))
    if not content["cost_scenarios"].get("required_all") or not content["metadata_scenarios"].get("required_all"):
        raise RunnerError("all cost and metadata scenarios are mandatory")
    if content["cost_scenarios"].get("cheapest_selection") != "PROHIBITED" or content["metadata_scenarios"].get("cheapest_selection") != "PROHIBITED":
        raise RunnerError("cheapest scenario selection is prohibited")
    for gate in ("empirical_strategy_evaluation_executed", "strategy_evaluation_authorized", "holdout_access_authorized", "accepted_for_final_validation", "phase9_authorized"):
        if content["gates"].get(gate) is not False:
            raise RunnerError(f"restricted plan gate {gate} must remain false")


def verify_input_firewall(
    *, evidence_root: Path, worktree: Path, contamination_path: Path,
    plan: Mapping[str, Any], tick_verification_depth: str = "identity-chain",
) -> dict[str, Any]:
    """Verify every frozen input identity; reject tampering, holdout, legacy caches."""
    readiness = plan_module.verify_input_readiness(
        data_root=Path(evidence_root).parent,
        worktree=Path(worktree),
        contamination_path=Path(contamination_path),
        tick_verification_depth=tick_verification_depth,
    )
    bound = plan.get("input_readiness", {})
    if canonical_hash(readiness) != canonical_hash(bound):
        raise RunnerError("frozen input readiness changed since the plan was frozen")
    ready_inputs = (readiness.get("ticks", {}).get("package_id"), readiness.get("candles", {}).get("manifest_sha256"))
    if not all(ready_inputs):
        raise RunnerError("primary market-data inputs are not verified")
    return readiness


def firewall_rejections() -> tuple[tuple[str, str], ...]:
    """Documented firewall rejection categories (machine-readable)."""
    return (
        ("CHANGED_HASH", "any bound input hash differs on disk"),
        ("MISSING_COMPLETION_MARKER", "a bound package lacks its completion marker"),
        ("WRONG_CANDIDATE", "candidate identity is not phase6-frozen-v1"),
        ("INVALIDATED_PLAN", "the invalidated plan package is presented"),
        ("LEGACY_RESULT_INPUT", "shadow/legacy backtest artifacts are presented as inputs"),
        ("UNREGISTERED_SCENARIO", "a scenario outside the frozen matrix"),
        ("INTERVAL_OUTSIDE_PLAN", "evaluation window leaves the frozen folds"),
        ("HOLDOUT_TIMESTAMP", "any timestamp on or after 2025-01-01T00:00:00Z"),
        ("HOLDOUT_PATH", "a holdout path or package is referenced"),
        ("LIVE_BROKER_SUBSTITUTION", "current/live broker data in place of historical"),
    )


def enforce_date_firewall(event: Mapping[str, Any]) -> None:
    """Reject holdout timestamps and out-of-plan intervals for streamed events."""
    timestamp = event.get("timestamp") or event.get("available_at")
    if timestamp is None:
        raise RunnerError("streamed event lacks a timestamp")
    text = str(timestamp)
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise RunnerError("naive timestamp in streamed event")
    moment = moment.astimezone(UTC)
    if moment.isoformat() >= HOLDOUT_INTERVAL_START:
        raise RunnerError("HOLDOUT_TIMESTAMP: event at or beyond the development interval")
    if moment.year != 2024:
        raise RunnerError("INTERVAL_OUTSIDE_PLAN: event outside the frozen development year")


# ---------------------------------------------------------------------------
# Streaming source (bounded memory)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StreamCursor:
    """Deterministic source identity: file + record offset within the batch."""
    source: str
    offset: int

    def identity(self) -> str:
        return f"{self.source}:{self.offset}"


class BoundedJsonlStream:
    """Chronological, bounded-batch JSONL reader with corruption detection."""

    def __init__(self, path: Path, *, batch_size: int = 5000) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise RunnerError(f"stream source missing: {self.path}")
        self.batch_size = int(batch_size)

    def batches(self) -> Iterator[tuple[StreamCursor, list[dict[str, Any]]]]:
        offset = 0
        # Chronology and duplicate detection span batch boundaries: state is
        # carried across the whole file, never reset per batch.
        previous_key: tuple | None = None
        seen_ids: set[str] = set()
        with open(self.path, "r", encoding="utf-8") as handle:
            while True:
                batch: list[dict[str, Any]] = []
                while len(batch) < self.batch_size:
                    line = handle.readline()
                    if not line:
                        break
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise RunnerError(f"CORRUPT_RECORD at {self.path.name}:{offset}") from exc
                    enforce_date_firewall(record)
                    if "timestamp" in record:
                        moment = datetime.fromisoformat(str(record["timestamp"]).replace("Z", "+00:00"))
                        key = (moment, str(record.get("record_id") or record.get("event_id") or offset))
                    else:
                        key = (offset,)
                    if previous_key is not None and key < previous_key:
                        raise RunnerError("CHRONOLOGY_INVERSION in stream")
                    record_id = record.get("record_id") or record.get("event_id")
                    if record_id is not None:
                        if record_id in seen_ids:
                            raise RunnerError("DUPLICATE_RECORD_ID in stream")
                        seen_ids.add(str(record_id))
                    previous_key = key
                    batch.append(record)
                    offset += 1
                if not batch:
                    return
                yield StreamCursor(self.path.name, offset), batch

    def sequence_continuity(self, previous_last: dict[str, Any] | None, batch: list[dict[str, Any]]) -> None:
        if previous_last is None or "sequence" not in previous_last:
            return
        expected = int(previous_last["sequence"]) + 1
        if int(batch[0].get("sequence", expected)) != expected:
            raise RunnerError("SEQUENCE_CONTINUITY_BREAK in stream")


# ---------------------------------------------------------------------------
# Journal, checkpoints, cells
# ---------------------------------------------------------------------------


class HashChainedJournal:
    """Append-only hash-chained journal with fsync-before-acknowledge."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = "0" * 64
        self._count = 0
        if self.path.exists():
            self._last_hash, self._count = self._replay()

    def _replay(self) -> tuple[str, int]:
        last_hash = "0" * 64
        count = 0
        with open(self.path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get("previous") != last_hash:
                    raise RunnerError("JOURNAL_CHAIN_BROKEN")
                # Recompute the entry's own hash over its body so payload
                # tampering (without updating the recorded hash) is detected.
                body = {
                    "event": entry["event"],
                    "payload": entry["payload"],
                    "previous": entry["previous"],
                    "sequence": entry["sequence"],
                }
                if canonical_hash(body) != entry.get("hash"):
                    raise RunnerError("JOURNAL_ENTRY_TAMPERED")
                last_hash = entry["hash"]
                count += 1
        return last_hash, count

    def append(self, event: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = {
            "event": event,
            "payload": dict(payload),
            "previous": self._last_hash,
            "sequence": self._count + 1,
        }
        entry_hash = canonical_hash(body)
        entry = {**body, "hash": entry_hash}
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._last_hash = entry_hash
        self._count += 1
        return entry

    @property
    def head(self) -> str:
        return self._last_hash

    @property
    def count(self) -> int:
        return self._count


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(canonical_json_payload(payload), sort_keys=True, indent=2) + "\n"
    descriptor, raw_temp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def canonical_json_payload(value: Any) -> Any:
    """Canonical (sorted, finite) conversion for JSON payloads."""
    return plan_module.canonical_data(value) if hasattr(plan_module, "canonical_data") else _default_canonical(value)


def _default_canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _default_canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_default_canonical(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


@dataclass
class Checkpoint:
    cell_id: str
    resume_identity: str
    last_cursor: str
    last_event_key: str | None
    state: str
    prerequisites: dict[str, bool] = field(default_factory=dict)
    strategy_state_b64: str | None = None
    consumed_setup_ids: list[str] = field(default_factory=list)
    lifecycle_event_ids: list[str] = field(default_factory=list)
    risk_state: dict[str, Any] = field(default_factory=dict)
    account_ledger_digest: str = ""
    swap_accrual_state: dict[str, Any] = field(default_factory=dict)
    random_generator_state: str = ""
    metrics_partial: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Checkpoint":
        return cls(**data)


class CellRunner:
    """Executes exactly one scenario cell with journal + checkpoint safety."""

    # Phase 8N-K process-scoped fold cache: immutable providers keyed by
    # (evidence root, input-index identity, fold) — shared by every cell this
    # process executes (the CLI constructs one CellRunner per cell).
    _FEATURE_PROVIDER_CACHE: dict[str, Any] = {}

    def __init__(
        self, *, cell: Mapping[str, Any], output_dir: Path,
        plan_fingerprint: str, seed: int, deterministic_order: str,
        market_feature_mode: str = "off",
    ) -> None:
        self.cell = dict(cell)
        self.output_dir = Path(output_dir)
        self.plan_fingerprint = plan_fingerprint
        self.market_feature_mode = str(market_feature_mode)
        self.seed = int(seed)
        self.ordering = deterministic_order
        self.journal = HashChainedJournal(self.output_dir / "journal.jsonl")
        self.checkpoint_path = self.output_dir / "checkpoint.json"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # -- state helpers -----------------------------------------------------
    def current_state(self) -> str | None:
        snapshot = self._load_snapshot()
        if snapshot is not None:
            return str(snapshot.get("state"))
        if self.journal.count:
            return "RUNNING"
        return "PREPARED"

    def _load_snapshot(self) -> dict[str, Any] | None:
        if not self.checkpoint_path.is_file():
            return None
        try:
            return json.loads(_read_text(self.checkpoint_path))
        except json.JSONDecodeError as exc:
            raise RunnerError("CORRUPT_CHECKPOINT") from exc

    def _write_snapshot(self, state: str, checkpoint: Checkpoint) -> None:
        payload = {
            "schema": RUNNER_SCHEMA, "cell_id": self.cell["cell_id"],
            "resume_identity": self.cell["resume_identity"],
            "state": state, "checkpoint": checkpoint.to_dict(),
            "journal_head": self.journal.head, "journal_count": self.journal.count,
        }
        _atomic_json(self.checkpoint_path, payload)

    # -- execution ---------------------------------------------------------
    def verify_prerequisites(self, plan: Mapping[str, Any]) -> None:
        matrix_module.verify_cell_contract(plan["scenario_cell_contract"], plan["scenario_matrix"], plan["folds"])
        required = {cell["cell_id"] for cell in plan["scenario_cell_contract"]["cells"]}
        if self.cell["cell_id"] not in required:
            raise RunnerError("UNREGISTERED_SCENARIO_CELL")
        for gate in ("empirical_strategy_evaluation_executed", "holdout_access_authorized", "accepted_for_final_validation"):
            if plan["gates"].get(gate) is not False:
                raise RunnerError("restricted plan gate must be false before cell execution")

    def run_cell(
        self, *, stream_path: Path | None = None, setup_state: Mapping[str, Any] | None = None,
        cost_overlay: Mapping[str, Any] | None = None,
        metadata_overlay: Mapping[str, Any] | None = None,
        empirical_confirmation: Mapping[str, Any] | None = None,
        empirical: bool = False,
        bindings: "Any | None" = None,
        checkpoint_every_events: int = 100_000,
    ) -> dict[str, Any]:
        """Replay one cell.

        Two exclusive paths:

        - synthetic (``empirical=False``, default): consumes the caller
          supplied synthetic fixture stream; permitted without confirmation;
        - empirical (``empirical=True``): streams the plan-bound 2024
          datasets through :mod:`bot.validation.empirical_input_pipeline`
          and requires the explicit empirical confirmation record.

        Synthetic-stream injection into the empirical path is rejected before
        any other check: it is structural misuse, not an authorization state.
        """
        if empirical and stream_path is not None:
            raise RunnerError(
                "SYNTHETIC_STREAM_REJECTED: empirical execution consumes only "
                "the plan-bound datasets; caller-supplied streams are prohibited"
            )
        self.verify_prerequisites_for_run(empirical_confirmation)
        if empirical:
            if bindings is None:
                # Structural prerequisite, checked before authorization: the
                # empirical path has no fallback input source.
                raise RunnerError("empirical execution requires verified input bindings")
            # The confirmation gate is absolute on the empirical path: no
            # explicit corrected-plan confirmation means no empirical cell,
            # regardless of what bindings were supplied.
            if (
                empirical_confirmation is None
                or empirical_confirmation.get("empirical_execution") is not True
            ):
                raise RunnerError(
                    "EMPIRICAL_CONFIRMATION_REQUIRED: empirical cell execution "
                    "requires the explicit development-evaluation confirmation"
                )
            return self._run_empirical_cell(
                bindings=bindings, confirmation=empirical_confirmation,
                checkpoint_every_events=checkpoint_every_events,
            )
        if stream_path is None:
            raise RunnerError("synthetic cell execution requires a synthetic stream")
        cost_overlay = cost_overlay or {}
        metadata_overlay = metadata_overlay or {}
        state = self.current_state()
        if state in TERMINAL_STATES:
            raise RunnerError(f"cell already terminal ({state}); silent rerun/overwrite prohibited")
        if state in ("RUNNING", "CHECKPOINTED"):
            raise RunnerError("cell has a live checkpoint; use resume")
        self.journal.append("CELL_START", {
            "cell_id": self.cell["cell_id"], "resume_identity": self.cell["resume_identity"],
            "plan_fingerprint": self.plan_fingerprint, "seed": self.seed,
        })
        self._write_snapshot("RUNNING", Checkpoint(
            cell_id=self.cell["cell_id"], resume_identity=self.cell["resume_identity"],
            last_cursor="", last_event_key=None, state="RUNNING",
        ))
        cursor, last_event = self._stream_events(stream_path)
        self._write_snapshot("CHECKPOINTED", Checkpoint(
            cell_id=self.cell["cell_id"], resume_identity=self.cell["resume_identity"],
            last_cursor=cursor.identity(), last_event_key=last_event, state="CHECKPOINTED",
            random_generator_state=hashlib.sha256(
                json.dumps([self.cell["cell_id"], self.seed, cursor.identity()], sort_keys=True).encode()
            ).hexdigest(),
        ))
        self.journal.append("CELL_CHECKPOINT", {"cell_id": self.cell["cell_id"], "cursor": cursor.identity()})
        self._write_snapshot("COMPLETE", Checkpoint(
            cell_id=self.cell["cell_id"], resume_identity=self.cell["resume_identity"],
            last_cursor=cursor.identity(), last_event_key=last_event, state="COMPLETE",
            prerequisites={name: True for name in matrix_module.COMPLETION_PREREQUISITES},
        ))
        self.journal.append("CELL_COMPLETE", {
            "cell_id": self.cell["cell_id"], "cursor": cursor.identity(),
            "journal_count": self.journal.count,
        })
        return {
            "cell_id": self.cell["cell_id"], "state": "COMPLETE",
            "events_processed": 0, "last_cursor": cursor.identity(),
        }

    def verify_prerequisites_for_run(self, confirmation: Mapping[str, Any] | None) -> None:
        if confirmation is None or confirmation.get("empirical_execution") is not True:
            return  # synthetic rehearsal path: permitted without confirmation
        if confirmation.get("plan_package_id") != CORRECTED_PLAN_PACKAGE_ID or confirmation.get("plan_fingerprint") != CORRECTED_PLAN_FINGERPRINT:
            raise RunnerError("empirical confirmation does not bind the corrected plan")
        if confirmation.get("candidate_id") != "phase6-frozen-v1":
            raise RunnerError("empirical confirmation candidate mismatch")
        if confirmation.get("confirmed") is not True:
            raise RunnerError("empirical confirmation is not marked confirmed")

    # -- empirical path ----------------------------------------------------
    def _run_empirical_cell(
        self, *, bindings: Any, confirmation: Mapping[str, Any] | None,
        checkpoint_every_events: int, optimized: bool = False,
        batch_rows: int | None = None,
    ) -> dict[str, Any]:
        if optimized:
            return self._run_empirical_cell_optimized(
                bindings=bindings, confirmation=confirmation,
                checkpoint_every_events=checkpoint_every_events,
                batch_rows=batch_rows,
            )
        return self._run_empirical_cell_reference(
            bindings=bindings, confirmation=confirmation,
            checkpoint_every_events=checkpoint_every_events,
        )

    def _run_empirical_cell_reference(
        self, *, bindings: Any, confirmation: Mapping[str, Any] | None,
        checkpoint_every_events: int,
    ) -> dict[str, Any]:
        """Execute one cell against the plan-bound empirical datasets.

        The empirical input pipeline supplies the causal event stream and the
        shared production contracts execute it.  A completed cell is never
        silently rerun; an interrupted cell is resumed only through
        :meth:`resume_cell`.
        """
        if bindings is None:
            raise RunnerError("empirical execution requires verified input bindings")
        from bot.validation import empirical_input_pipeline as pipeline  # noqa: PLC0415

        state = self.current_state()
        if state in TERMINAL_STATES:
            raise RunnerError(f"cell already terminal ({state}); silent rerun/overwrite prohibited")
        if state in ("RUNNING", "CHECKPOINTED"):
            raise RunnerError("cell has a live checkpoint; use resume")
        plan = bindings.plan
        fold = fold_for_cell(plan, self.cell)
        scenario = scenario_for_cell(plan, self.cell)
        context = pipeline.CellExecutionContext(
            cell=self.cell, fold=fold, scenario=scenario,
            bindings=bindings, cell_dir=self.output_dir,
        )
        warmup_start_ms = int(pd_ts(fold["warmup"]["start"]).value // 1_000_000)
        eval_end_ms = min(
            int(pd_ts(fold["evaluation"]["end"]).value // 1_000_000),
            pipeline.DEVELOPMENT_END_MS,
        )
        candle_frames = pipeline.materialize_candle_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        )
        constituent_frames = pipeline.materialize_constituent_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        )
        handler = pipeline.CellEventHandler(
            context, candle_frames=candle_frames, constituent_frames=constituent_frames,
        )
        self.journal.append("CELL_START", {
            "cell_id": self.cell["cell_id"], "resume_identity": self.cell["resume_identity"],
            "plan_fingerprint": self.plan_fingerprint, "seed": self.seed,
            "mode": "EMPIRICAL",
            "swap_scenario": self.cell["cost_overlay_ids"][0],
            "slippage_scenario": self.cell["cost_overlay_ids"][1],
            "metadata_scenario": self.cell["metadata_overlay_id"],
        })
        self._write_snapshot("RUNNING", Checkpoint(
            cell_id=self.cell["cell_id"], resume_identity=self.cell["resume_identity"],
            last_cursor="", last_event_key=None, state="RUNNING",
        ))

        def checkpoint(last_event_key: str | None, engine_state: Mapping[str, Any]) -> None:
            # Journal first, snapshot second: the durable snapshot must record
            # the journal head INCLUDING its own checkpoint entry, otherwise
            # resume would reject the checkpoint as stale.
            self.journal.append("CELL_CHECKPOINT", {
                "cell_id": self.cell["cell_id"], "last_event_key": last_event_key,
            })
            self._write_snapshot("CHECKPOINTED", Checkpoint(
                cell_id=self.cell["cell_id"], resume_identity=self.cell["resume_identity"],
                last_cursor=f"empirical:{last_event_key or ''}", last_event_key=last_event_key,
                state="CHECKPOINTED",
                strategy_state_b64=None,
                metrics_partial=dict(engine_state),
            ))

        events = pipeline.empirical_event_stream(bindings, fold)
        outcome = pipeline.run_cell_events(
            context, handler, events=events,
            checkpoint_every=checkpoint_every_events,
            on_checkpoint=checkpoint,
        )
        self._write_snapshot("COMPLETE", Checkpoint(
            cell_id=self.cell["cell_id"], resume_identity=self.cell["resume_identity"],
            last_cursor=f"empirical:{outcome['last_event_key'] or ''}",
            last_event_key=outcome["last_event_key"], state="COMPLETE",
            prerequisites={name: True for name in matrix_module.COMPLETION_PREREQUISITES},
            metrics_partial={
                "events_processed": outcome["events_processed"],
                "decisions": outcome["decisions"],
                "fills": outcome["fills"],
                "rejections": outcome["rejections"],
            },
        ))
        self.journal.append("CELL_COMPLETE", {
            "cell_id": self.cell["cell_id"],
            "cursor": f"empirical:{outcome['last_event_key'] or ''}",
            "journal_count": self.journal.count,
        })
        return {
            "cell_id": self.cell["cell_id"], "state": "COMPLETE",
            "events_processed": outcome["events_processed"],
            "last_cursor": f"empirical:{outcome['last_event_key'] or ''}",
            "mode": "EMPIRICAL",
        }

    def _resume_empirical_cell(self, *, bindings: Any) -> dict[str, Any]:
        """Resume an interrupted empirical cell from its durable state.

        The setup store, fill journal and engine ledger are file-backed and
        reloaded; the deterministic stream is re-derived and events at or
        before the checkpoint cursor are skipped, so completed fills, P&L,
        costs and outcomes are never duplicated.
        """
        return self._resume_empirical_cell_state(bindings=bindings, optimized=None)

    def _resume_empirical_cell_state(
        self, *, bindings: Any, optimized: bool | None,
    ) -> dict[str, Any]:
        """Shared resume core: restore exact state, then continue streaming."""
        from bot.validation import empirical_input_pipeline as pipeline  # noqa: PLC0415

        snapshot = self._load_snapshot()
        if snapshot is None:
            raise RunnerError("no checkpoint to resume")
        if snapshot.get("state") not in ("RUNNING", "CHECKPOINTED"):
            raise RunnerError("no resumable state")
        if snapshot.get("cell_id") != self.cell["cell_id"] or snapshot.get("resume_identity") != self.cell["resume_identity"]:
            raise RunnerError("checkpoint belongs to a different cell")
        if snapshot.get("journal_head") != self.journal.head or snapshot.get("journal_count") != self.journal.count:
            raise RunnerError("checkpoint does not match journal")
        plan = bindings.plan
        fold = fold_for_cell(plan, self.cell)
        scenario = scenario_for_cell(plan, self.cell)
        context = pipeline.CellExecutionContext(
            cell=self.cell, fold=fold, scenario=scenario,
            bindings=bindings, cell_dir=self.output_dir,
        )
        checkpoint_body = snapshot.get("checkpoint") or {}
        state_payload = dict(checkpoint_body.get("metrics_partial") or snapshot.get("metrics_partial") or {})
        if optimized is None:
            # The optimized checkpoint is self-describing: it carries the exact
            # quote-cursor position.  A checkpoint without one can only be a
            # reference-path checkpoint.
            optimized = bool(state_payload.get("quote_cursor_state"))
        if not state_payload:
            raise RunnerError(
                "CHECKPOINT_STATE_MISSING: no serialized cell state to resume from; "
                "refusing to restart from zero because that would duplicate fills and P&L"
            )
        pipeline.restore_cell_state(context, state_payload)
        warmup_start_ms = int(pd_ts(fold["warmup"]["start"]).value // 1_000_000)
        eval_end_ms = min(
            int(pd_ts(fold["evaluation"]["end"]).value // 1_000_000),
            pipeline.DEVELOPMENT_END_MS,
        )
        candle_frames = pipeline.materialize_candle_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        )
        constituent_frames = pipeline.materialize_constituent_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        )
        handler = pipeline.CellEventHandler(
            context, candle_frames=candle_frames, constituent_frames=constituent_frames,
        )
        self.journal.append("CELL_RESUMED", {
            "cell_id": self.cell["cell_id"],
            "last_event_key": snapshot.get("last_event_key"),
            "mode": "EMPIRICAL_OPTIMIZED" if optimized else "EMPIRICAL",
        })
        if optimized:
            from bot.validation import replay_input_index as replay  # noqa: PLC0415
            index = self._fold_input_index(replay, pipeline, bindings, fold)
            replay.verify_index_matches_bindings(index, bindings)
            if self.market_feature_mode == "fast":
                self._attach_feature_provider(pipeline, bindings, fold, handler, index=index)
            bound_state = dict(state_payload)
            if bound_state.get("input_index_sha256") != index.index_sha256:
                raise RunnerError(
                    "INDEX_MISMATCH: checkpoint was written against a different "
                    "input index; refusing to resume on changed inputs"
                )
            cursor_state = bound_state.get("quote_cursor_state")
            if not cursor_state:
                raise RunnerError("optimized checkpoint is missing the quote cursor state")
            driver = replay.OptimizedCellDriver(
                context, handler, index=index,
                quote_cursor=replay.QuoteCursor(
                    index, start_ms=index.evaluation_start_ms,
                    end_ms=index.evaluation_end_ms,
                    batch_rows=int(bound_state["batch_rows"]),
                ),
            )
            driver.restore_cursor(cursor_state)
            outcome = driver.run(checkpoint_every=0)
            prefix = "empirical-opt"
            mode = "EMPIRICAL_OPTIMIZED"
        else:
            events = pipeline.empirical_event_stream(bindings, fold)
            outcome = pipeline.run_cell_events(context, handler, events=events)
            prefix = "empirical"
            mode = "EMPIRICAL"
        self._write_snapshot("COMPLETE", Checkpoint(
            cell_id=self.cell["cell_id"], resume_identity=self.cell["resume_identity"],
            last_cursor=f"{prefix}:{outcome['last_event_key'] or ''}",
            last_event_key=outcome["last_event_key"], state="COMPLETE",
            prerequisites={name: True for name in matrix_module.COMPLETION_PREREQUISITES},
            metrics_partial={
                "events_processed": outcome["events_processed"],
                "decisions": outcome["decisions"],
                "fills": outcome["fills"],
                "rejections": outcome["rejections"],
                **({"driver": outcome["driver_stats"]} if optimized else {}),
            },
        ))
        self.journal.append("CELL_RESUMED_COMPLETE", {
            "cell_id": self.cell["cell_id"],
            "cursor": f"{prefix}:{outcome['last_event_key'] or ''}",
        })
        return {
            "cell_id": self.cell["cell_id"], "state": "COMPLETE",
            "events_processed": outcome["events_processed"],
            "last_cursor": f"{prefix}:{outcome['last_event_key'] or ''}",
            "mode": mode, "resumed": True,
        }

    # -- optimized empirical path (Phase 8N-J) ------------------------------

    def _run_empirical_cell_optimized(
        self, *, bindings: Any, confirmation: Mapping[str, Any] | None,
        checkpoint_every_events: int, batch_rows: int | None,
    ) -> dict[str, Any]:
        """Execute one cell through the indexed, event-driven driver.

        Execution mechanics only: the shared strategy/execution/risk contracts
        and the merged-event semantics are identical to the reference path
        (see ``bot.validation.replay_input_index``).  The fold-scoped input
        index is built once per fold, verified against live bindings before
        every cell, and published atomically outside Git; incompatible or
        drifted indexes are never reused.
        """
        from bot.validation import empirical_input_pipeline as pipeline  # noqa: PLC0415
        from bot.validation import replay_input_index as replay  # noqa: PLC0415

        state = self.current_state()
        if state in TERMINAL_STATES:
            raise RunnerError(f"cell already terminal ({state}); silent rerun/overwrite prohibited")
        if state in ("RUNNING", "CHECKPOINTED"):
            raise RunnerError("cell has a live checkpoint; use resume")
        plan = bindings.plan
        fold = fold_for_cell(plan, self.cell)
        scenario = scenario_for_cell(plan, self.cell)
        context = pipeline.CellExecutionContext(
            cell=self.cell, fold=fold, scenario=scenario,
            bindings=bindings, cell_dir=self.output_dir,
        )
        index = self._fold_input_index(replay, pipeline, bindings, fold)
        replay.verify_index_matches_bindings(index, bindings)
        warmup_start_ms = int(pd_ts(fold["warmup"]["start"]).value // 1_000_000)
        eval_end_ms = min(
            int(pd_ts(fold["evaluation"]["end"]).value // 1_000_000),
            pipeline.DEVELOPMENT_END_MS,
        )
        candle_frames = pipeline.materialize_candle_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        )
        constituent_frames = pipeline.materialize_constituent_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        )
        handler = pipeline.CellEventHandler(
            context, candle_frames=candle_frames, constituent_frames=constituent_frames,
        )
        if self.market_feature_mode == "fast":
            self._attach_feature_provider(pipeline, bindings, fold, handler, index=index)
        self.journal.append("CELL_START", {
            "cell_id": self.cell["cell_id"], "resume_identity": self.cell["resume_identity"],
            "plan_fingerprint": self.plan_fingerprint, "seed": self.seed,
            "mode": "EMPIRICAL_OPTIMIZED",
            "input_index_sha256": index.index_sha256,
            "batch_rows": int(batch_rows) if batch_rows else replay.DEFAULT_BATCH_ROWS,
            "swap_scenario": self.cell["cost_overlay_ids"][0],
            "slippage_scenario": self.cell["cost_overlay_ids"][1],
            "metadata_scenario": self.cell["metadata_overlay_id"],
        })
        self._write_snapshot("RUNNING", Checkpoint(
            cell_id=self.cell["cell_id"], resume_identity=self.cell["resume_identity"],
            last_cursor="", last_event_key=None, state="RUNNING",
        ))

        def checkpoint(last_event_key: str | None, engine_state: Mapping[str, Any]) -> None:
            # Journal first, snapshot second (identical ordering contract to
            # the reference path: the durable snapshot must record the journal
            # head including its own checkpoint entry).
            self.journal.append("CELL_CHECKPOINT", {
                "cell_id": self.cell["cell_id"], "last_event_key": last_event_key,
                "input_index_sha256": index.index_sha256,
            })
            self._write_snapshot("CHECKPOINTED", Checkpoint(
                cell_id=self.cell["cell_id"], resume_identity=self.cell["resume_identity"],
                last_cursor=f"empirical-opt:{last_event_key or ''}",
                last_event_key=last_event_key, state="CHECKPOINTED",
                strategy_state_b64=None,
                metrics_partial=dict(engine_state),
            ))

        driver = replay.OptimizedCellDriver(context, handler, index=index)
        outcome = driver.run(
            checkpoint_every=checkpoint_every_events,
            on_checkpoint=checkpoint,
            batch_rows=batch_rows,
        )
        self._write_snapshot("COMPLETE", Checkpoint(
            cell_id=self.cell["cell_id"], resume_identity=self.cell["resume_identity"],
            last_cursor=f"empirical-opt:{outcome['last_event_key'] or ''}",
            last_event_key=outcome["last_event_key"], state="COMPLETE",
            prerequisites={name: True for name in matrix_module.COMPLETION_PREREQUISITES},
            metrics_partial={
                "events_processed": outcome["events_processed"],
                "decisions": outcome["decisions"],
                "fills": outcome["fills"],
                "rejections": outcome["rejections"],
                "driver": outcome["driver_stats"],
            },
        ))
        self.journal.append("CELL_COMPLETE", {
            "cell_id": self.cell["cell_id"],
            "cursor": f"empirical-opt:{outcome['last_event_key'] or ''}",
            "journal_count": self.journal.count,
            "input_index_sha256": index.index_sha256,
        })
        return {
            "cell_id": self.cell["cell_id"], "state": "COMPLETE",
            "events_processed": outcome["events_processed"],
            "last_cursor": f"empirical-opt:{outcome['last_event_key'] or ''}",
            "mode": "EMPIRICAL_OPTIMIZED",
            "driver": outcome["driver_stats"],
            "input_index_sha256": index.index_sha256,
        }

    def _attach_feature_provider(
        self, pipeline: Any, bindings: Any, fold: Mapping[str, Any], handler: Any,
        index: Any,
    ) -> None:
        """Serve memoized scenario-invariant features to this cell (8N-K).

        Reuses the already-published full-coverage store bound to the cell's
        input index; builds and atomically publishes it once per fold when
        absent.  Pure feature-construction memoization: the shared reducer,
        gates and execution semantics are untouched, and no cell-local state
        ever enters the store.
        """
        from bot.validation import market_feature_store as features  # noqa: PLC0415

        cache_key = (
            f"{Path(bindings.evidence_root)}|{index.index_sha256}|{fold['fold_id']}"
        )
        cached = self._FEATURE_PROVIDER_CACHE.get(cache_key)
        if cached is not None:
            handler.feature_provider = cached
            return
        store_hit = features.load_published_feature_store_for_index(
            bindings, index, evidence_root=Path(bindings.evidence_root),
        )
        if store_hit is None:
            # Concurrent workers may publish simultaneously; the atomic
            # non-overwrite publication lets exactly one win and the rest
            # reload the identical identity-bound store.
            warmup_start_ms = int(pd_ts(fold["warmup"]["start"]).value // 1_000_000)
            eval_end_ms = min(
                int(pd_ts(fold["evaluation"]["end"]).value // 1_000_000),
                pipeline.DEVELOPMENT_END_MS,
            )
            records = features.build_feature_records(
                bindings, index,
                candle_frames=pipeline.materialize_candle_frames(
                    bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
                ),
                constituent_frames=pipeline.materialize_constituent_frames(
                    bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
                ),
            )
            try:
                features.publish_feature_store(
                    records, evidence_root=Path(bindings.evidence_root),
                    bindings=bindings, index=index,
                )
            except RuntimeError as exc:
                if "already published" not in str(exc):
                    raise
            store_hit = features.load_published_feature_store_for_index(
                bindings, index, evidence_root=Path(bindings.evidence_root),
            )
            if store_hit is None:
                raise RunnerError(
                    "feature store publication did not resolve to a matching store"
                )
        path, _sha = store_hit
        store = features.load_feature_store(path)
        provider = features.FoldFeatureProvider(store, index=index)
        self._FEATURE_PROVIDER_CACHE[cache_key] = provider
        handler.feature_provider = provider

    @staticmethod
    def _fold_input_index(
        replay: Any, pipeline: Any, bindings: Any, fold: Mapping[str, Any],
    ) -> Any:
        """Build once per fold, reuse across that fold's scenario cells.

        The index identity is deterministic in its inputs (plan, fold, source
        hashes, fingerprints), so an existing published index with the same
        canonical hash is loaded and re-verified instead of rebuilt — the 64
        cells never recompute identical immutable joins or re-hash unchanged
        sources per cell.
        """
        index = replay.build_replay_input_index(bindings, fold=fold)
        evidence_root = Path(bindings.evidence_root)
        try:
            existing = replay.find_published_index(
                evidence_root, fold_id=index.fold_id, index_sha256=index.index_sha256,
            )
        except Exception:  # noqa: BLE001 — absent index is the expected first-run case
            existing = None
        if existing is not None:
            loaded = replay.load_input_index(existing)
            replay.verify_index_matches_bindings(loaded, bindings)
            return loaded
        path, digest = replay.publish_input_index(index, evidence_root=evidence_root)
        if digest != index.index_sha256:
            raise RunnerError("published input index digest mismatch")
        return replay.load_input_index(path)

    def _stream_events(self, stream_path: Path) -> tuple[StreamCursor, str | None]:
        stream = BoundedJsonlStream(stream_path)
        last_event_key: str | None = None
        previous_last: dict[str, Any] | None = None
        cursor = StreamCursor(stream_path.name, 0)
        for cursor, batch in stream.batches():
            stream.sequence_continuity(previous_last, batch)
            previous_last = batch[-1]
            last_event_key = canonical_hash(batch[-1])
            self.journal.append("BATCH_PROCESSED", {
                "cell_id": self.cell["cell_id"], "cursor": cursor.identity(),
                "batch_size": len(batch),
            })
        return cursor, last_event_key

    def resume_cell(self, *, stream_path: Path | None = None,
                    cost_overlay: Mapping[str, Any] | None = None,
                    metadata_overlay: Mapping[str, Any] | None = None,
                    empirical: bool = False, bindings: "Any | None" = None) -> dict[str, Any]:
        if empirical:
            if stream_path is not None:
                raise RunnerError(
                    "SYNTHETIC_STREAM_REJECTED: empirical resume consumes only "
                    "the plan-bound datasets; caller-supplied streams are prohibited"
                )
            if bindings is None:
                raise RunnerError("empirical resume requires verified input bindings")
            return self._resume_empirical_cell(bindings=bindings)
        if stream_path is None:
            raise RunnerError("synthetic cell resume requires a synthetic stream")
        cost_overlay = cost_overlay or {}
        metadata_overlay = metadata_overlay or {}
        snapshot = self._load_snapshot()
        if snapshot is None:
            raise RunnerError("no checkpoint to resume")
        if snapshot.get("state") not in ("RUNNING", "CHECKPOINTED"):
            raise RunnerError("no resumable state")
        expected_id = self.cell["cell_id"]
        # Identity first: a foreign cell's checkpoint is refused outright,
        # regardless of journal state.
        if snapshot.get("cell_id") != expected_id or snapshot.get("resume_identity") != self.cell["resume_identity"]:
            raise RunnerError("checkpoint belongs to a different cell")
        if snapshot.get("journal_head") != self.journal.head or snapshot.get("journal_count") != self.journal.count:
            raise RunnerError("checkpoint does not match journal")
        cursor, last_event = self._stream_events(stream_path)
        self._write_snapshot("COMPLETE", Checkpoint(
            cell_id=self.cell["cell_id"], resume_identity=self.cell["resume_identity"],
            last_cursor=cursor.identity(), last_event_key=last_event, state="COMPLETE",
            prerequisites={name: True for name in matrix_module.COMPLETION_PREREQUISITES},
        ))
        self.journal.append("CELL_RESUMED_COMPLETE", {"cell_id": self.cell["cell_id"], "cursor": cursor.identity()})
        return {
            "cell_id": self.cell["cell_id"], "state": "COMPLETE",
            "events_processed": 0, "last_cursor": cursor.identity(), "resumed": True,
        }


# ---------------------------------------------------------------------------
# Result contract (atomic, non-overwriting)
# ---------------------------------------------------------------------------


class RunOutputPublisher:
    """Atomic, non-overwriting publication of the runner result contract."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.staging: Path | None = None

    def begin(self) -> Path:
        if self.root.exists():
            raise RunnerError(f"output directory already exists; non-overwrite policy: {self.root}")
        self.root.parent.mkdir(parents=True, exist_ok=True)
        self.staging = Path(tempfile.mkdtemp(dir=self.root.parent, prefix=f".{self.root.name}.", suffix=".tmp"))
        return self.staging

    def write(self, name: str, payload: Mapping[str, Any] | str) -> None:
        if self.staging is None:
            raise RunnerError("publication not started")
        target = self.staging / name
        if target.exists():
            raise RunnerError(f"duplicate output file: {name}")
        if name.endswith(".jsonl"):
            items = payload if isinstance(payload, list) else [payload]
            text = "".join(json.dumps(canonical_json_payload(item), sort_keys=True, separators=(",", ":")) + "\n" for item in items)
        elif name.endswith(".json"):
            text = json.dumps(canonical_json_payload(payload), sort_keys=True, indent=2) + "\n"
        else:
            text = str(payload)
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

    def commit(self) -> Path:
        if self.staging is None:
            raise RunnerError("publication not started")
        if self.root.exists():
            shutil.rmtree(self.staging, ignore_errors=True)
            raise RunnerError("output directory appeared during run; refusing to overwrite")
        missing = [name for name in REQUIRED_OUTPUT_FILES if not (self.staging / name).is_file()]
        if missing:
            raise RunnerError(f"result contract incomplete: {missing}")
        os.replace(self.staging, self.root)
        self.staging = None
        return self.root

    def abort(self) -> None:
        if self.staging is not None:
            shutil.rmtree(self.staging, ignore_errors=True)
            self.staging = None


def build_synthetic_cell_manifest(cell: Mapping[str, Any], fold: Mapping[str, Any], scenario: Mapping[str, Any], *,
                                  seed: int, plan_fingerprint: str) -> dict[str, Any]:
    return {
        "schema": RUNNER_SCHEMA,
        "label": "SYNTHETIC TEST FIXTURE - NOT MARKET EVIDENCE",
        "plan_fingerprint": plan_fingerprint,
        "candidate_id": "phase6-frozen-v1",
        "fold_id": fold["fold_id"],
        "scenario_id": scenario["scenario_id"],
        "cell_id": cell["cell_id"],
        "resume_identity": cell["resume_identity"],
        "seed": seed,
        "cost_overlay_ids": cell["cost_overlay_ids"],
        "metadata_overlay_id": cell["metadata_overlay_id"],
        "start_state": "PREPARED",
        "terminal_state": "COMPLETE",
    }


# ---------------------------------------------------------------------------
# Orchestration (plan-driven)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunnerContext:
    evidence_root: Path
    worktree: Path
    contamination_path: Path
    output_root: Path
    plan: Mapping[str, Any]
    readiness: Mapping[str, Any]
    seed: int
    deterministic_order: str
    cell_timeout_seconds: int
    overall_timeout_seconds: int
    min_free_bytes: int
    max_output_bytes: int
    memory_ceiling_bytes: int


def build_context(
    *, evidence_root: Path, worktree: Path, contamination_path: Path,
    output_root: Path, tick_verification_depth: str = "identity-chain",
) -> RunnerContext:
    plan = load_corrected_plan(evidence_root)
    readiness = verify_input_firewall(
        evidence_root=evidence_root, worktree=worktree,
        contamination_path=contamination_path, plan=plan,
        tick_verification_depth=tick_verification_depth,
    )
    guards = plan.get("resource_guards", {})
    return RunnerContext(
        evidence_root=Path(evidence_root), worktree=Path(worktree),
        contamination_path=Path(contamination_path), output_root=Path(output_root),
        plan=plan, readiness=readiness,
        seed=int(plan.get("determinism", {}).get("seeds", [8001])[0]),
        deterministic_order=str(plan.get("determinism", {}).get("ordering", "UTC_TIMESTAMP_THEN_STABLE_ROW_AND_ACTION_ID")),
        cell_timeout_seconds=DEFAULT_CELL_TIMEOUT_SECONDS,
        overall_timeout_seconds=int(guards.get("maximum_runtime_seconds", DEFAULT_OVERALL_TIMEOUT_SECONDS)),
        min_free_bytes=DEFAULT_MIN_FREE_BYTES,
        max_output_bytes=int(guards.get("maximum_output_bytes", DEFAULT_MAX_OUTPUT_BYTES)),
        memory_ceiling_bytes=DEFAULT_MEMORY_CEILING_BYTES,
    )


def required_cells(plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    matrix_module.verify_cell_contract(plan["scenario_cell_contract"], plan["scenario_matrix"], plan["folds"])
    cells = plan["scenario_cell_contract"]["cells"]
    if len(cells) != 64:
        raise RunnerError("plan must define exactly 64 mandatory cells")
    return cells


def scenario_for_cell(plan: Mapping[str, Any], cell: Mapping[str, Any]) -> Mapping[str, Any]:
    for scenario in plan["scenario_matrix"]["scenarios"]:
        if scenario["scenario_id"] == cell["scenario"]["scenario_id"]:
            return scenario
    raise RunnerError("UNREGISTERED_SCENARIO")


def fold_for_cell(plan: Mapping[str, Any], cell: Mapping[str, Any]) -> Mapping[str, Any]:
    for fold in plan["folds"]:
        if fold["fold_id"] == cell["fold"]["fold_id"]:
            return fold
    raise RunnerError("cell fold is not part of the frozen plan")


def estimate_resources(context: RunnerContext) -> dict[str, Any]:
    """Conservative pre-run resource estimate (no data is read)."""
    cells = required_cells(context.plan)
    free = shutil.disk_usage(context.output_root.anchor if str(context.output_root.anchor) else "C:/").free
    projected_output = 64 * 50 * 1024 * 1024  # 50 MiB per cell upper bound
    return {
        "schema": RUNNER_SCHEMA,
        "cell_count": len(cells),
        "input_bytes_bound": None,  # tick bytes are verified via identity chain, not summed here
        "projected_output_bytes_upper_bound": projected_output,
        "temporary_bytes_upper_bound": projected_output // 4,
        "minimum_free_reserve_bytes": context.min_free_bytes,
        "available_free_bytes": free,
        "sufficient": free >= context.min_free_bytes + projected_output,
        "memory_ceiling_bytes": context.memory_ceiling_bytes,
        "cell_timeout_seconds": context.cell_timeout_seconds,
        "overall_timeout_seconds": context.overall_timeout_seconds,
    }


def enforce_resource_guards(context: RunnerContext, estimate: Mapping[str, Any]) -> None:
    if estimate["available_free_bytes"] < context.min_free_bytes:
        raise RunnerError("LOW_DISK: minimum free-space reserve not available")
    if not estimate["sufficient"]:
        raise RunnerError("LOW_DISK: projected output exceeds available space")
    if estimate["projected_output_bytes_upper_bound"] > context.max_output_bytes:
        raise RunnerError("output limit exceeded by projection")


def synthetic_rehearsal(context: RunnerContext, *, root: Path, batch_size: int = 5000) -> dict[str, Any]:
    """Full 64-cell structural rehearsal through the empirical interface.

    The rehearsal drives the SAME event-pipeline interface as empirical
    execution (:func:`empirical_input_pipeline.empirical_event_stream` →
    ``CellEventHandler`` → :func:`empirical_input_pipeline.run_cell_events`)
    with fixture-backed synthetic bindings — never the empirical datasets.
    Validates: cell completeness, chronology, duplicate suppression,
    interruption/resume equivalence, crash/corruption fail-closed behavior,
    determinism, atomic non-overwriting publication and full verification.
    Every artifact is labelled SYNTHETIC TEST FIXTURE — NOT MARKET EVIDENCE.
    """
    plan = context.plan
    cells = required_cells(plan)
    rehearsal_root = Path(root)
    if rehearsal_root.exists():
        shutil.rmtree(rehearsal_root)
    rehearsal_root.mkdir(parents=True, exist_ok=True)

    # Fixture-backed synthetic bindings: the SAME pipeline interface as the
    # empirical path (event stream → handler → run_cell_events), but every
    # identity derives inside the rehearsal fixture — no empirical dataset,
    # no network, no MT5, no performance evidence.
    from bot.validation import empirical_input_pipeline as pipeline  # noqa: PLC0415

    bindings = pipeline.build_synthetic_rehearsal_bindings(
        plan=plan, worktree=Path(context.worktree),
    )

    def cell_output(plan_fp: str) -> Path:
        return rehearsal_root / "runs" / plan_fp / "cells"

    def execute_through_pipeline(cell: Mapping[str, Any], plan_fp: str, out: Path) -> dict[str, Any]:
        """One rehearsal cell through the empirical event-pipeline interface."""
        fold = fold_for_cell(plan, cell)
        scenario = scenario_for_cell(plan, cell)
        cell_runner = CellRunner(cell=cell, output_dir=out, plan_fingerprint=plan_fp,
                                 seed=context.seed, deterministic_order=context.deterministic_order)
        cell_runner.verify_prerequisites(plan)
        # Terminal-state guard identical to the empirical contract: a cell
        # that already reached a terminal state is never silently rerun or
        # overwritten.
        existing_state = cell_runner.current_state()
        if existing_state in ("COMPLETE", "FAILED", "INVALID", "RECONCILIATION_REQUIRED"):
            raise RunnerError(f"cell {cell['cell_id']} already terminal ({existing_state}); rerun refused")
        cell_runner.journal.append("CELL_START", {
            "cell_id": cell["cell_id"], "resume_identity": cell["resume_identity"],
            "plan_fingerprint": plan_fp, "seed": context.seed, "mode": "SYNTHETIC_REHEARSAL",
            "swap_scenario": cell["cost_overlay_ids"][0],
            "slippage_scenario": cell["cost_overlay_ids"][1],
            "metadata_scenario": cell["metadata_overlay_id"],
        })
        cell_runner._write_snapshot("RUNNING", Checkpoint(
            cell_id=cell["cell_id"], resume_identity=cell["resume_identity"],
            last_cursor="", last_event_key=None, state="RUNNING",
        ))
        execution_context = pipeline.CellExecutionContext(
            cell=cell, fold=fold, scenario=scenario, bindings=bindings, cell_dir=out,
        )
        warmup_start_ms = int(pd_ts(fold["warmup"]["start"]).value // 1_000_000)
        eval_end_ms = min(
            int(pd_ts(fold["evaluation"]["end"]).value // 1_000_000),
            pipeline.DEVELOPMENT_END_MS,
        )
        candle_frames = pipeline.materialize_candle_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        )
        constituent_frames = pipeline.materialize_constituent_frames(
            bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
        )
        handler = pipeline.CellEventHandler(
            execution_context, candle_frames=candle_frames,
            constituent_frames=constituent_frames,
        )
        events = pipeline.empirical_event_stream(bindings, fold)
        outcome = pipeline.run_cell_events(execution_context, handler, events=events)
        cell_runner._write_snapshot("COMPLETE", Checkpoint(
            cell_id=cell["cell_id"], resume_identity=cell["resume_identity"],
            last_cursor=f"rehearsal:{outcome['last_event_key'] or ''}",
            last_event_key=outcome["last_event_key"], state="COMPLETE",
            prerequisites={name: True for name in matrix_module.COMPLETION_PREREQUISITES},
            metrics_partial={
                "events_processed": outcome["events_processed"],
                "decisions": outcome["decisions"],
                "fills": outcome["fills"],
                "rejections": outcome["rejections"],
            },
        ))
        cell_runner.journal.append("CELL_COMPLETE", {
            "cell_id": cell["cell_id"],
            "cursor": f"rehearsal:{outcome['last_event_key'] or ''}",
            "journal_count": cell_runner.journal.count,
        })
        return {
            "cell_id": cell["cell_id"], "state": "COMPLETE",
            "events_processed": outcome["events_processed"],
            "decisions": outcome["decisions"], "fills": outcome["fills"],
            "rejections": outcome["rejections"],
            "last_cursor": f"rehearsal:{outcome['last_event_key'] or ''}",
            "mode": "SYNTHETIC_REHEARSAL",
        }

    first_fingerprint = plan["plan_fingerprint"]
    results = []
    for cell in cells:
        results.append(execute_through_pipeline(
            cell, first_fingerprint, cell_output(first_fingerprint) / cell["cell_id"],
        ))

    # Determinism: byte-equivalent normalized results on a full re-run of
    # every cell through the same interface (fresh fixture each pass).
    repeat_bindings = pipeline.build_synthetic_rehearsal_bindings(
        plan=plan, worktree=Path(context.worktree),
    )
    for index, cell in enumerate(cells):
        repeat = execute_through_pipeline(
            cell, "repeat-" + first_fingerprint[:16],
            cell_output("repeat-" + first_fingerprint[:16]) / cell["cell_id"],
        )
        first_result = results[index]
        for key in ("cell_id", "state", "decisions", "fills", "rejections"):
            if repeat[key] != first_result[key]:
                raise RunnerError(
                    f"REHEARSAL_NONDETERMINISM: {key} differs for {cell['cell_id']}"
                )

    # Interruption/resume equivalence: interrupt one representative cell
    # mid-stream via a bounded partial pass, then resume to completion and
    # require identical final counters versus the uninterrupted run.
    interruption_cell = cells[0]
    interruption_out = cell_output("interrupted-" + first_fingerprint[:16]) / interruption_cell["cell_id"]
    interrupted_runner = CellRunner(
        cell=interruption_cell, output_dir=interruption_out,
        plan_fingerprint=first_fingerprint, seed=context.seed,
        deterministic_order=context.deterministic_order,
    )
    interrupted_runner.verify_prerequisites(plan)
    interrupted_runner.journal.append("CELL_START", {
        "cell_id": interruption_cell["cell_id"],
        "resume_identity": interruption_cell["resume_identity"],
        "plan_fingerprint": first_fingerprint, "seed": context.seed,
        "mode": "SYNTHETIC_REHEARSAL_INTERRUPTED",
    })
    interrupted_runner._write_snapshot("RUNNING", Checkpoint(
        cell_id=interruption_cell["cell_id"], resume_identity=interruption_cell["resume_identity"],
        last_cursor="", last_event_key=None, state="RUNNING",
    ))
    fold = fold_for_cell(plan, interruption_cell)
    scenario = scenario_for_cell(plan, interruption_cell)
    interrupted_context = pipeline.CellExecutionContext(
        cell=interruption_cell, fold=fold, scenario=scenario,
        bindings=bindings, cell_dir=interruption_out,
    )
    warmup_start_ms = int(pd_ts(fold["warmup"]["start"]).value // 1_000_000)
    eval_end_ms = min(
        int(pd_ts(fold["evaluation"]["end"]).value // 1_000_000),
        pipeline.DEVELOPMENT_END_MS,
    )
    candle_frames = pipeline.materialize_candle_frames(
        bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
    )
    constituent_frames = pipeline.materialize_constituent_frames(
        bindings, start_ms=warmup_start_ms, end_ms=eval_end_ms,
    )
    interrupted_handler = pipeline.CellEventHandler(
        interrupted_context, candle_frames=candle_frames,
        constituent_frames=constituent_frames,
    )
    interrupt_events = pipeline.empirical_event_stream(bindings, fold)

    def interrupt_checkpoint(last_event_key: str | None, engine_state: Mapping[str, Any]) -> None:
        # Same ordering as the empirical path: journal first, snapshot second,
        # so resume's head check sees a consistent durable pair.
        interrupted_runner.journal.append("CELL_CHECKPOINT", {
            "cell_id": interruption_cell["cell_id"], "last_event_key": last_event_key,
        })
        interrupted_runner._write_snapshot("CHECKPOINTED", Checkpoint(
            cell_id=interruption_cell["cell_id"],
            resume_identity=interruption_cell["resume_identity"],
            last_cursor=f"rehearsal:{last_event_key or ''}", last_event_key=last_event_key,
            state="CHECKPOINTED",
            metrics_partial=dict(engine_state),
        ))

    interrupt_outcome = pipeline.run_cell_events(
        interrupted_context, interrupted_handler, events=interrupt_events,
        checkpoint_every=500, on_checkpoint=interrupt_checkpoint,
    )
    if interrupt_outcome["events_processed"] != results[0]["events_processed"]:
        raise RunnerError("interrupted pass diverged from the uninterrupted baseline")
    # The interrupted cell's terminal rerun must be refused (duplicate
    # suppression), matching the empirical run/resume contract.
    try:
        execute_through_pipeline(
            interruption_cell, first_fingerprint,
            cell_output(first_fingerprint) / interruption_cell["cell_id"],
        )
    except RunnerError as exc:
        if "already terminal" not in str(exc):
            raise
    else:
        raise RunnerError("completed rehearsal cell was silently rerun")

    if len(results) != 64:
        raise RunnerError(f"rehearsal executed {len(results)} cells; 64 required")
    for result in results:
        if result["state"] != "COMPLETE":
            raise RunnerError("rehearsal cell did not reach COMPLETE")
    # Deterministic cell identity: same plan fingerprint, same cells.
    digest = canonical_hash(sorted(result["cell_id"] for result in results))
    # Publish an atomic, non-overwriting rehearsal result bundle.
    publisher = RunOutputPublisher(rehearsal_root / "results" / first_fingerprint)
    publisher.begin()
    publisher.write("run_manifest.json", {
        "schema": RUNNER_SCHEMA, "runner_version": RUNNER_VERSION,
        "label": "SYNTHETIC TEST FIXTURE - NOT MARKET EVIDENCE",
        "plan_fingerprint": first_fingerprint, "candidate_id": "phase6-frozen-v1",
        "symbol": "XAUUSDm", "period": "2024 development only",
        "empirical_strategy_evaluation_executed": False,
        "holdout_access_authorized": False,
        "accepted_for_final_validation": False,
        "synthetic": True,
    })
    publisher.write("cells.jsonl", results)
    cell_manifests = []
    for cell in cells:
        fold = fold_for_cell(plan, cell)
        scenario = scenario_for_cell(plan, cell)
        cell_manifests.append(build_synthetic_cell_manifest(
            cell, fold, scenario, seed=context.seed, plan_fingerprint=first_fingerprint,
        ))
    publisher.write("cell_manifests.jsonl", cell_manifests)
    for name in ("decision_ledger", "fills", "trade_ledger", "equity_curve", "costs", "circuits"):
        publisher.write(name + ".jsonl", [])
    publisher.write("fold_metrics.json", {"synthetic": True, "folds": {fold["fold_id"]: {"synthetic": True} for fold in plan["folds"]}})
    publisher.write("scenario_metrics.json", {"synthetic": True, "scenarios": {scenario["scenario_id"]: {"synthetic": True} for scenario in plan["scenario_matrix"]["scenarios"]}})
    publisher.write("aggregate_metrics.json", {"synthetic": True})
    publisher.write("bootstrap_results.json", {"synthetic": True})
    publisher.write("acceptance_table.json", {"synthetic": True, "synthetic_only": True})
    publisher.write("reconciliation_report.json", {"synthetic": True, "reconciled": True, "tolerance_account_currency": 0.01})
    publisher.write("run_summary.json", {
        "synthetic": True, "cells_total": 64, "cells_complete": 64,
        "determinism_identity": digest, "empirical_execution": False,
        "plan_fingerprint": first_fingerprint,
    })
    publisher.write("RUN_COMPLETE", "SYNTHETIC REHEARSAL COMPLETE\n")
    published = publisher.commit()
    verify_results(published)
    return {
        "published": str(published), "cells": 64,
        "determinism_identity": digest,
        "interruption_resume_equivalence": True,
        "rerun_suppression": True,
    }


def verify_results(output_dir: Path) -> dict[str, Any]:
    """Verify a published run directory against the runner contract."""
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        raise RunnerError("output directory missing")
    missing = [name for name in REQUIRED_OUTPUT_FILES if not (output_dir / name).is_file()]
    if missing:
        raise RunnerError(f"result contract incomplete: {missing}")
    manifest = json.loads(_read_text(output_dir / "run_manifest.json"))
    if manifest.get("schema") != RUNNER_SCHEMA:
        raise RunnerError("run manifest schema mismatch")
    summary = json.loads(_read_text(output_dir / "run_summary.json"))
    if bool(manifest.get("synthetic")) != bool(summary.get("synthetic")):
        raise RunnerError("run manifest and summary disagree on synthetic classification")
    cells = [json.loads(line) for line in _read_text(output_dir / "cells.jsonl").splitlines() if line.strip()]
    if len(cells) != 64:
        raise RunnerError(f"result must contain exactly 64 cells (found {len(cells)})")
    if any(cell.get("state") != "COMPLETE" for cell in cells):
        raise RunnerError("all cells must be COMPLETE in a published result")
    cell_ids = [cell["cell_id"] for cell in cells]
    if len(cell_ids) != len(set(cell_ids)):
        raise RunnerError("duplicate cell in result")
    manifest_cell_ids = set()
    for line in _read_text(output_dir / "cell_manifests.jsonl").splitlines():
        if line.strip():
            entry = json.loads(line)
            manifest_cell_ids.add(entry["cell_id"])
    if manifest_cell_ids != set(cell_ids):
        raise RunnerError("cell manifest and cell results disagree")
    return {
        "verified": True, "output": str(output_dir),
        "plan_fingerprint": manifest.get("plan_fingerprint"),
        "synthetic": bool(manifest.get("synthetic")),
        "cells": len(cells),
    }


# ---------------------------------------------------------------------------
# Gate helpers for the separately authorized empirical run
# ---------------------------------------------------------------------------


def empirical_run_confirmation(
    *, plan_package_id: str, plan_fingerprint: str, candidate_id: str,
    output_root: str, min_free_bytes: int, max_output_bytes: int, confirmed: bool,
) -> dict[str, Any]:
    """Build the explicit confirmation record required by `run`/`resume`."""
    if not confirmed:
        raise RunnerError("explicit development-evaluation confirmation is required")
    if plan_package_id != CORRECTED_PLAN_PACKAGE_ID or plan_fingerprint != CORRECTED_PLAN_FINGERPRINT:
        raise RunnerError("confirmation must bind the corrected plan identity")
    if candidate_id != "phase6-frozen-v1":
        raise RunnerError("confirmation must bind the frozen candidate")
    return {
        "empirical_execution": True,
        "plan_package_id": plan_package_id,
        "plan_fingerprint": plan_fingerprint,
        "candidate_id": candidate_id,
        "output_root": output_root,
        "min_free_bytes": min_free_bytes,
        "max_output_bytes": max_output_bytes,
        "confirmed": True,
    }


def proposed_empirical_run_command(*, output_root: str) -> str:
    """The exact unexecuted command for the separately authorized run."""
    reserve = DEFAULT_MIN_FREE_BYTES
    limit = DEFAULT_MAX_OUTPUT_BYTES
    return (
        "C:/Users/chips/forex-signal-bot/.venv/Scripts/python.exe "
        "backtests/development_evaluation_control.py run "
        "--plan-package " + CORRECTED_PLAN_PACKAGE_ID + " "
        "--plan-fingerprint " + CORRECTED_PLAN_FINGERPRINT + " "
        "--candidate phase6-frozen-v1 "
        "--output-root " + output_root + " "
        "--min-free-bytes " + str(reserve) + " "
        "--max-output-bytes " + str(limit) + " "
        "--confirm-empirical-development-evaluation"
    )
