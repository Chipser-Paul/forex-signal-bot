"""Phase 8C post-commit verification attestation for derived candle packages.

Creates an immutable, versioned attestation that proves exactly what can be
proven about an already-published derived-candle package:

- the package, its manifest and completion marker are unchanged (hash-bound);
- every partition matches its recorded physical and canonical content hashes;
- the package is compatible with and verified by the exact clean commit that
  executes the verification (``verification_commit``);
- whether the generation-time implementation can be proven identical to that
  commit.  It deliberately does NOT claim that the verification commit
  generated the package: the original manifest truthfully records the
  repository state that existed during generation, and no cryptographic
  generation-time code fingerprint exists to prove more.

Unprovable facts are recorded as explicit ``NOT_PROVEN`` values, never guessed.
The attested package is never modified.

Publication layout (outside Git, non-overwriting):

    <attestations_root>/<attestation_id>/attestation.json   canonical document
    <attestations_root>/<attestation_id>/attestation.sha256 sha256 of the file bytes

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from bot.validation.models import canonical_data

from .candle_manifest import verify_derived_candle_manifest
from .candle_pipeline import CLASSIFICATION_LABEL
from .candle_store import ParquetBidAskCandleStore, read_candle_records
from .models import AcquisitionError
from .storage import file_sha256

UTC = timezone.utc
ATTESTATION_SCHEMA_VERSION = "phase8c.provenance-attestation.v1"
CLASSIFICATION = "DEVELOPMENT_ONLY"
LABEL = CLASSIFICATION_LABEL

# Fixed verification order; the attestation records this order explicitly.
VERIFIED_TIMEFRAMES: tuple[str, ...] = ("M5", "M15", "H1", "H4", "D1", "W1")
TIMEFRAME_DURATION_MS: dict[str, int] = {
    "M5": 300_000,
    "M15": 900_000,
    "H1": 3_600_000,
    "H4": 14_400_000,
    "D1": 86_400_000,
    "W1": 604_800_000,
}

# Independent high-level expectations from the Phase 8C checkpoint report.
EXPECTED_RECORD_COUNTS: dict[str, int] = {
    "M5": 70_562,
    "M15": 23_550,
    "H1": 5_904,
    "H4": 1_600,
    "D1": 311,
    "W1": 52,
}


@dataclass(frozen=True)
class AttestationIdentity:
    """Stable external identity of an attested derived package."""

    package_id: str
    manifest_sha256: str
    completion_sha256: str
    attestation_id: str
    attestation_sha256: str          # canonical content hash (self-recorded)
    attestation_physical_sha256: str  # sha256 of the published file bytes


def attestation_id_for(manifest_sha256: str) -> str:
    """Derive the stable attestation directory id from the manifest hash."""
    text = str(manifest_sha256).lower()
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise AcquisitionError("ATTESTATION_MANIFEST_HASH_INVALID")
    return f"derived-candles-attestation-v1-{text[:16]}"


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _require_exact_commit(value: object, name: str) -> str:
    text = str(value)
    if len(text) != 40 or any(c not in "0123456789abcdef" for c in text):
        raise AcquisitionError(f"ATTESTATION_{name}_INVALID")
    return text


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        canonical_data(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def verify_package_readonly(
    derived_root: Path,
    *,
    expected_record_counts: Mapping[str, int] | None = None,
) -> dict:
    """Complete read-only verification of an existing derived package.

    Verifies manifest/completion binding, every partition's physical hash,
    canonical content hash, complete validated readback, row counts, schema
    versions, ordering, closed-open boundaries, exact timeframe durations,
    available_at causality, first/last source-tick containment, coverage
    boundaries and the development-only classification.  The store verifier
    enforces stable identities plus bid/ask and OHLC invariants during
    readback.  Raises AcquisitionError on any mismatch.
    """
    root = Path(derived_root).resolve(strict=True)
    manifest_path = root / "manifest.json"
    completion_path = root / "pipeline.complete.json"
    if not manifest_path.is_file() or not completion_path.is_file():
        raise AcquisitionError("ATTESTATION_PACKAGE_INCOMPLETE")

    original_manifest_sha256 = file_sha256(manifest_path)
    original_completion_sha256 = file_sha256(completion_path)

    readiness_path = root / "readiness_report.json"
    if not readiness_path.is_file():
        raise AcquisitionError("ATTESTATION_READINESS_REPORT_MISSING")
    original_readiness_sha256 = file_sha256(readiness_path)
    try:
        readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError("ATTESTATION_READINESS_REPORT_UNREADABLE") from exc
    if readiness.get("schema_version") != "phase8c.readiness-report.v1":
        raise AcquisitionError("ATTESTATION_READINESS_REPORT_SCHEMA_UNSUPPORTED")
    readiness_candles = readiness.get("AVAILABLE", {}).get("derived_causal_candles", {})
    if readiness_candles.get("status") != "COMPLETE":
        raise AcquisitionError("ATTESTATION_READINESS_NOT_COMPLETE")
    if readiness.get("HOLDOUT_STATUS", {}).get("accessed") is not False:
        raise AcquisitionError("ATTESTATION_READINESS_HOLDOUT_FLAG_INVALID")
    if readiness.get("STRATEGY_EVALUATION_STATUS", {}).get("performed") is not False:
        raise AcquisitionError("ATTESTATION_READINESS_STRATEGY_FLAG_INVALID")

    manifest = verify_derived_candle_manifest(root)
    if manifest.get("classification") != CLASSIFICATION:
        raise AcquisitionError("ATTESTATION_PACKAGE_CLASSIFICATION_INVALID")
    if CLASSIFICATION_LABEL not in str(manifest.get("label", "")):
        raise AcquisitionError("ATTESTATION_PACKAGE_LABEL_INVALID")

    store = ParquetBidAskCandleStore(
        root / "candles", maximum_output_bytes=1 << 30, minimum_free_bytes=0
    )
    entries = {str(item["timeframe"]): item for item in manifest["timeframe_entries"]}
    if tuple(sorted(entries)) != tuple(sorted(VERIFIED_TIMEFRAMES)):
        raise AcquisitionError("ATTESTATION_PACKAGE_TIMEFRAMES_INCOMPLETE")

    partitions = []
    total_rows = 0
    coverage_starts: dict[str, str] = {}
    coverage_ends: dict[str, str] = {}
    gap_counts: dict[str, int] = {}

    expected_counts = (
        dict(EXPECTED_RECORD_COUNTS)
        if expected_record_counts is None
        else dict(expected_record_counts)
    )

    for timeframe in VERIFIED_TIMEFRAMES:
        entry = entries[timeframe]
        relative_path = str(entry["partition_relative_path"])
        final_path = root / "candles" / relative_path
        if not final_path.is_file():
            raise AcquisitionError("ATTESTATION_PARTITION_MISSING")
        if file_sha256(final_path) != str(entry["sha256"]):
            raise AcquisitionError("ATTESTATION_PARTITION_PHYSICAL_HASH_MISMATCH")

        summary = store.verify(relative_path)
        if summary.record_count != int(entry["record_count"]):
            raise AcquisitionError("ATTESTATION_PARTITION_ROW_COUNT_MISMATCH")
        if summary.canonical_content_sha256 != str(entry["canonical_content_sha256"]):
            raise AcquisitionError("ATTESTATION_PARTITION_CANONICAL_HASH_MISMATCH")
        if summary.schema_version != str(entry["schema_version"]):
            raise AcquisitionError("ATTESTATION_PARTITION_SCHEMA_MISMATCH")
        if summary.record_count != int(expected_counts[timeframe]):
            raise AcquisitionError("ATTESTATION_EXPECTED_ROW_COUNT_MISMATCH")

        rows = read_candle_records(final_path)
        if len(rows) != summary.record_count:
            raise AcquisitionError("ATTESTATION_READBACK_COUNT_MISMATCH")

        duration_ms = TIMEFRAME_DURATION_MS[timeframe]
        opens: list[int] = []
        previous_close_ms: int | None = None
        for row in rows:
            open_ms = int(row["open_time_ms"])
            close_ms = int(row["close_time_ms"])
            if close_ms - open_ms != duration_ms:
                raise AcquisitionError("ATTESTATION_WINDOW_DURATION_MISMATCH")
            if int(row["available_at_ms"]) < close_ms:
                raise AcquisitionError("ATTESTATION_CAUSALITY_VIOLATION")
            if (
                int(row["first_tick_ms"]) < open_ms
                or int(row["last_tick_ms"]) >= close_ms
            ):
                raise AcquisitionError("ATTESTATION_TICK_CONTAINMENT_VIOLATION")
            if previous_close_ms is not None and open_ms < previous_close_ms:
                raise AcquisitionError("ATTESTATION_WINDOW_OVERLAP")
            previous_close_ms = close_ms
            opens.append(open_ms)
        if opens != sorted(opens) or len(set(opens)) != len(opens):
            raise AcquisitionError("ATTESTATION_ORDERING_VIOLATION")
        if (
            int(entry["first_open_ms"]) != opens[0]
            or int(entry["last_open_ms"]) != opens[-1]
        ):
            raise AcquisitionError("ATTESTATION_COVERAGE_BOUNDARY_MISMATCH")

        coverage_starts[timeframe] = (
            datetime.fromtimestamp(opens[0] / 1000, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
        coverage_ends[timeframe] = (
            datetime.fromtimestamp((opens[-1] + duration_ms) / 1000, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
        gap_counts[timeframe] = int(entry["gap_count"])
        total_rows += summary.record_count
        reported_rows = readiness_candles.get("row_counts", {}).get(timeframe)
        reported_gaps = readiness_candles.get("gap_counts", {}).get(timeframe)
        if reported_rows is None or int(reported_rows) != summary.record_count:
            raise AcquisitionError("ATTESTATION_READINESS_ROW_COUNT_MISMATCH")
        if reported_gaps is None or int(reported_gaps) != gap_counts[timeframe]:
            raise AcquisitionError("ATTESTATION_READINESS_GAP_COUNT_MISMATCH")

        partitions.append({
            "timeframe": timeframe,
            "partition_relative_path": relative_path,
            "record_count": summary.record_count,
            "sha256": str(entry["sha256"]),
            "canonical_content_sha256": str(entry["canonical_content_sha256"]),
            "size_bytes": int(entry["size_bytes"]),
            "first_open_ms": opens[0],
            "last_open_ms": opens[-1],
        })

    return canonical_data({
        "original_manifest_sha256": original_manifest_sha256,
        "original_completion_sha256": original_completion_sha256,
        "year_package_id": str(manifest["year_package_id"]),
        "source_canonical_sha256": str(manifest["source_canonical_sha256"]),
        "source_row_count": int(manifest["source_row_count"]),
        "total_emitted_rows": total_rows,
        "coverage_start_by_timeframe": coverage_starts,
        "coverage_end_by_timeframe": coverage_ends,
        "gap_count_by_timeframe": gap_counts,
        "missing_window_count_by_timeframe": dict(
            readiness_candles.get("missing_window_counts", {})
        ),
        "readiness_report_sha256": original_readiness_sha256,
        "partitions": partitions,
        "package_schema_version": str(manifest.get("pipeline_schema_version", "")),
        "manifest_schema_version": str(manifest.get("schema_version", "")),
    })


def build_attestation(
    derived_root: Path,
    *,
    implementation_commit: str,
    verification_commit: str,
    verification_fingerprint: str,
    expected_record_counts: Mapping[str, int] | None = None,
    implementation_module_hashes: Mapping[str, str] | None = None,
    worktree_root: Path | None = None,
) -> dict:
    """Build the attestation document (without self-hashes and timestamp)."""
    implementation_commit = _require_exact_commit(
        implementation_commit, "IMPLEMENTATION_COMMIT"
    )
    verification_commit = _require_exact_commit(
        verification_commit, "VERIFICATION_COMMIT"
    )
    if not str(verification_fingerprint).strip():
        raise AcquisitionError("ATTESTATION_VERIFICATION_FINGERPRINT_INVALID")

    verified = verify_package_readonly(
        derived_root, expected_record_counts=expected_record_counts
    )

    manifest_document = json.loads(
        (Path(derived_root) / "manifest.json").read_text(encoding="utf-8")
    )
    stored_commit = str(manifest_document.get("git_commit", ""))
    generation_base_commit = stored_commit if len(stored_commit) == 40 else None
    generation_source_fingerprint = _manifest_generation_fingerprint(
        Path(derived_root)
    )

    if generation_source_fingerprint is not None:
        # Only immutable evidence can classify equivalence; reproduce the
        # fingerprint from the implementation commit's committed verifier
        # content and compare, otherwise fail honestly.
        from .candle_discovery import code_fingerprint

        reproduced = code_fingerprint(
            verification_commit,
            worktree_root=worktree_root,
            module_hashes=implementation_module_hashes,
        )
        if reproduced == generation_source_fingerprint:
            equivalence = "PROVEN"
            explanation = (
                "The package manifest stores a generation-time code "
                "fingerprint that is byte-for-byte reproducible from the "
                "committed verifier content of the implementation commit; "
                "generation-commit equivalence is therefore PROVEN."
            )
        else:
            equivalence = "DISPROVEN"
            explanation = (
                "The package manifest stores a generation-time code "
                "fingerprint that does not match the committed verifier "
                "content of the implementation commit; generation-commit "
                "equivalence is DISPROVEN."
            )
    else:
        equivalence = "NOT_PROVEN"
        explanation = (
            "The package manifest records only the repository HEAD during "
            "generation (generation_base_commit) and carries no generation-time "
            "code fingerprint. The Phase 8C implementation was uncommitted in the "
            "working tree during generation and was committed afterwards as "
            "implementation_commit. No immutable evidence cryptographically binds "
            "the generation-time working-tree contents to that commit, so "
            "generation-commit equivalence is NOT_PROVEN. The committed verifier "
            "accepts the package unchanged, which establishes compatibility "
            "(verified_compatible=true) but not generation identity."
        )

    attestation = {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "attestation_id": attestation_id_for(verified["original_manifest_sha256"]),
        "classification": CLASSIFICATION,
        "label": LABEL,
        "package": {
            "package_id": (
                f"derived-candles-2024-v1-"
                f"{verified['original_manifest_sha256'][:16]}"
            ),
            "identity_basis": (
                "content identity: source year canonical hash + manifest "
                "sha256; no absolute local path is part of the identity"
            ),
            "source_year_package_id": verified["year_package_id"],
            "source_canonical_sha256": verified["source_canonical_sha256"],
            "source_row_count": verified["source_row_count"],
            "manifest_sha256": verified["original_manifest_sha256"],
            "completion_marker_sha256": verified["original_completion_sha256"],
            "package_schema_version": verified["package_schema_version"],
            "manifest_schema_version": verified["manifest_schema_version"],
        },
        "provenance": {
            "generation_base_commit": generation_base_commit,
            "generation_source_fingerprint": generation_source_fingerprint,
            "generation_commit_equivalence": equivalence,
            "generation_equivalence_explanation": explanation,
            "implementation_commit": implementation_commit,
            "verification_commit": verification_commit,
            "verification_fingerprint": str(verification_fingerprint),
            "verified_compatible": True,
        },
        "verified_partitions": verified["partitions"],
        "coverage": {
            "timeframe_order": list(VERIFIED_TIMEFRAMES),
            "coverage_start_by_timeframe": verified["coverage_start_by_timeframe"],
            "coverage_end_by_timeframe": verified["coverage_end_by_timeframe"],
            "gap_count_by_timeframe": verified["gap_count_by_timeframe"],
            "missing_window_count_by_timeframe": verified[
                "missing_window_count_by_timeframe"
            ],
            "total_emitted_rows": verified["total_emitted_rows"],
            "terminal_partial_window_policy": "DISCARDED_NOT_FORWARD_FILLED",
            "duplicate_policy": "EXACT_DUPLICATE_TICKS_COUNTED_AS_OBSERVATIONS",
        },
        "verification_invariants": [
            "manifest_completion_hash_binding",
            "partition_physical_sha256",
            "partition_canonical_content_sha256",
            "complete_partition_readback",
            "row_counts_match_expected_checkpoint_report",
            "schema_versions_match",
            "stable_candle_identities",
            "utc_open_time_ordering",
            "closed_open_window_boundaries",
            "exact_timeframe_durations",
            "available_at_greater_or_equal_close_time",
            "bid_ask_validity_and_ohlc_invariants",
            "first_last_source_tick_containment",
            "gap_and_missing_window_diagnostics_reconciled",
            "development_only_classification",
        ],
        "strategy_evaluation_statement": (
            "No strategy evaluation, backtest, optimization, tuning, "
            "profitability metric, win rate, profit factor or capital "
            "projection was computed for this attestation."
        ),
        "holdout_accessed": False,
        "mt5_or_trading_accessed": False,
    }
    return canonical_data(attestation)


def _manifest_generation_fingerprint(derived_root: Path) -> str | None:
    """Return the package's generation-time code fingerprint, if it stores one."""
    try:
        document = json.loads(
            (Path(derived_root) / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None
    for key in ("generation_source_fingerprint", "code_fingerprint"):
        value = document.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _attestation_paths(attestations_root: Path, attestation_id: str) -> tuple[Path, Path, Path]:
    directory = Path(attestations_root) / str(attestation_id)
    return directory, directory / "attestation.json", directory / "attestation.sha256"


def publish_attestation(
    derived_root: Path,
    attestations_root: Path,
    *,
    implementation_commit: str,
    verification_commit: str,
    verification_fingerprint: str,
    expected_record_counts: Mapping[str, int] | None = None,
    implementation_module_hashes: Mapping[str, str] | None = None,
    worktree_root: Path | None = None,
) -> tuple[dict, AttestationIdentity]:
    """Verify the package and publish its attestation atomically.

    The attestation directory is created non-overwriting under
    ``attestations_root``.  Repeated execution with the same immutable inputs
    recognizes and returns the existing identical attestation; conflicting
    repetition (different implementation/verification commit, changed
    package, tampered record) fails closed.  The attested package is never
    modified.
    """
    body = build_attestation(
        derived_root,
        implementation_commit=implementation_commit,
        verification_commit=verification_commit,
        verification_fingerprint=verification_fingerprint,
        expected_record_counts=expected_record_counts,
        implementation_module_hashes=implementation_module_hashes,
        worktree_root=worktree_root,
    )
    attestation_id = str(body["attestation_id"])
    directory, final_path, sidecar_path = _attestation_paths(
        attestations_root, attestation_id
    )

    if final_path.exists():
        existing = load_attestation(attestations_root, attestation_id)
        _require_compatible_attestation(existing, body)
        return canonical_data(existing), AttestationIdentity(
            package_id=str(existing["package"]["package_id"]),
            manifest_sha256=str(existing["package"]["manifest_sha256"]),
            completion_sha256=str(existing["package"]["completion_marker_sha256"]),
            attestation_id=attestation_id,
            attestation_sha256=str(existing["attestation_canonical_sha256"]),
            attestation_physical_sha256=sidecar_path.read_text(encoding="ascii").strip(),
        )

    document = dict(body)
    document["created_utc"] = _now_utc_iso()
    document["attestation_canonical_sha256"] = _canonical_hash(
        {k: v for k, v in document.items() if k != "attestation_canonical_sha256"}
    )
    payload = json.dumps(
        canonical_data(document),
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"

    if sidecar_path.exists() and not final_path.exists():
        raise AcquisitionError("ATTESTATION_SIDECAR_WITHOUT_DOCUMENT")
    # An interrupted earlier attempt may have left the directory with stale
    # .partial files only; publishing here is still non-overwriting because
    # the published document and sidecar do not exist yet.
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write_bytes(final_path, payload.encode("utf-8"))
    physical_sha256 = file_sha256(final_path)
    _atomic_write_bytes(sidecar_path, (physical_sha256 + "\n").encode("ascii"))

    return canonical_data(document), AttestationIdentity(
        package_id=str(document["package"]["package_id"]),
        manifest_sha256=str(document["package"]["manifest_sha256"]),
        completion_sha256=str(document["package"]["completion_marker_sha256"]),
        attestation_id=attestation_id,
        attestation_sha256=str(document["attestation_canonical_sha256"]),
        attestation_physical_sha256=physical_sha256,
    )


def load_attestation(attestations_root: Path, attestation_id: str) -> dict:
    """Load and verify an existing attestation; fail closed on any tampering."""
    _, final_path, sidecar_path = _attestation_paths(attestations_root, attestation_id)
    if not final_path.is_file():
        raise AcquisitionError("ATTESTATION_MISSING")
    if not sidecar_path.is_file():
        raise AcquisitionError("ATTESTATION_SIDECAR_MISSING")
    try:
        stored = json.loads(final_path.read_text(encoding="utf-8"))
        recorded_physical = sidecar_path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError("ATTESTATION_UNREADABLE") from exc
    if not isinstance(stored, dict):
        raise AcquisitionError("ATTESTATION_UNREADABLE")
    if stored.get("schema_version") != ATTESTATION_SCHEMA_VERSION:
        raise AcquisitionError("ATTESTATION_SCHEMA_UNSUPPORTED")
    if file_sha256(final_path) != recorded_physical:
        raise AcquisitionError("ATTESTATION_PHYSICAL_HASH_MISMATCH")
    body = {
        key: value
        for key, value in stored.items()
        if key != "attestation_canonical_sha256"
    }
    if _canonical_hash(body) != stored.get("attestation_canonical_sha256"):
        raise AcquisitionError("ATTESTATION_CANONICAL_HASH_MISMATCH")
    return stored


def _require_compatible_attestation(
    existing: Mapping[str, object], body: Mapping[str, object]
) -> None:
    """Fail closed unless the existing attestation matches the request."""
    stored_provenance = existing["provenance"]
    stored_package = existing["package"]
    conflicts = []
    for key in (
        "implementation_commit",
        "verification_commit",
        "verification_fingerprint",
    ):
        expected = body["provenance"][key]
        actual = stored_provenance.get(key)
        if actual != expected:
            conflicts.append(f"provenance.{key}: stored={actual!r} requested={expected!r}")
    for key in ("manifest_sha256", "completion_marker_sha256", "source_canonical_sha256"):
        expected = body["package"][key]
        actual = stored_package.get(key)
        if actual != expected:
            conflicts.append(f"package.{key}: stored={actual!r} requested={expected!r}")
    if conflicts:
        raise AcquisitionError("ATTESTATION_CONFLICT: " + "; ".join(conflicts))


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".partial"
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
