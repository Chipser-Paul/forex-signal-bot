"""Phase 8C derived-candle manifest builder and verifier.

Creates a versioned, non-overwriting, atomically-published manifest
that records complete provenance for derived XAUUSDm candle artifacts.

Every manifest is explicitly labelled:
  DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from filelock import FileLock

from bot.validation.models import canonical_data

from .candle_pipeline import REQUIRED_TIMEFRAMES, SCHEMA_VERSION, CLASSIFICATION_LABEL
from .candle_store import (
    CandlePartitionSummary,
    canonical_candle_hash,
    read_candle_records,
    ParquetBidAskCandleStore,
)
from .models import AcquisitionError, EXECUTABLE_SYMBOL
from .storage import atomic_json, file_sha256, validate_output_root


UTC = timezone.utc
MANIFEST_SCHEMA_VERSION = "phase8c.derived-candles-manifest.v1"
COMPLETION_SCHEMA_VERSION = "phase8c.derived-candles-completion.v1"
CLASSIFICATION = "DEVELOPMENT_ONLY"
LABEL = CLASSIFICATION_LABEL

_PROVENANCE_NOTE = (
    "Derived from Exness XAUUSDm 2024 monthly tick packages. "
    "Tick data is proprietary Exness broker history. "
    "Candle derivation code is under the project MIT licence. "
    "No licensing status beyond data-provider terms of service is claimed."
)


@dataclass(frozen=True)
class TimeframeManifestEntry:
    timeframe: str
    partition_relative_path: str
    sha256: str
    canonical_content_sha256: str
    record_count: int
    size_bytes: int
    first_open_ms: int
    last_open_ms: int
    gap_count: int
    partial_initial_window: bool
    partial_terminal_window: bool
    schema_version: str


@dataclass(frozen=True)
class DerivedCandleManifest:
    schema_version: str
    classification: str
    label: str
    symbol: str
    year_package_id: str
    source_canonical_sha256: str
    source_row_count: int
    git_commit: str
    derived_at: str
    timeframe_entries: tuple[TimeframeManifestEntry, ...]
    monthly_package_ids: tuple[str, ...]
    provenance: str
    pipeline_schema_version: str


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_derived_candle_manifest(
    output_root: Path,
    *,
    year_package_id: str,
    source_canonical_sha256: str,
    source_row_count: int,
    git_commit: str,
    timeframe_summaries: Sequence[tuple[CandlePartitionSummary, dict]],
    monthly_package_ids: Sequence[str],
) -> dict:
    """Build and atomically publish the derived-candle manifest.

    Args:
        output_root:              Root of the derived-candles output directory.
        year_package_id:          ID of the source year package.
        source_canonical_sha256:  Canonical hash of the source tick year package.
        source_row_count:         Total source tick rows.
        git_commit:               Git commit SHA at derivation time.
        timeframe_summaries:      Sequence of (CandlePartitionSummary, gap_info_dict).
        monthly_package_ids:      Ordered list of monthly source package IDs.

    Returns the manifest dict.  Raises AcquisitionError if the manifest
    already exists (non-overwriting) or any invariant is violated.
    """
    root = validate_output_root(Path(output_root), forbidden_roots=())
    manifest_path = root / "manifest.json"
    completion_path = root / "pipeline.complete.json"
    partial_marker = root / ".manifest.partial.json"

    if manifest_path.exists() or completion_path.exists():
        # Idempotent: return the existing manifest if it matches
        return _verify_and_return_existing(
            root,
            year_package_id=year_package_id,
            source_canonical_sha256=source_canonical_sha256,
        )

    entries: list[TimeframeManifestEntry] = []
    for summary, gap_info in timeframe_summaries:
        entries.append(
            TimeframeManifestEntry(
                timeframe=summary.timeframe,
                partition_relative_path=summary.relative_path,
                sha256=summary.sha256,
                canonical_content_sha256=summary.canonical_content_sha256,
                record_count=summary.record_count,
                size_bytes=summary.size_bytes,
                first_open_ms=summary.first_open_ms,
                last_open_ms=summary.last_open_ms,
                gap_count=int(gap_info.get("gap_count", 0)),
                partial_initial_window=bool(gap_info.get("partial_initial_window", False)),
                partial_terminal_window=bool(gap_info.get("partial_terminal_window", True)),
                schema_version=summary.schema_version,
            )
        )

    manifest_obj = DerivedCandleManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        classification=CLASSIFICATION,
        label=LABEL,
        symbol=EXECUTABLE_SYMBOL,
        year_package_id=year_package_id,
        source_canonical_sha256=source_canonical_sha256,
        source_row_count=source_row_count,
        git_commit=git_commit,
        derived_at=_now_utc_iso(),
        timeframe_entries=tuple(entries),
        monthly_package_ids=tuple(monthly_package_ids),
        provenance=_PROVENANCE_NOTE,
        pipeline_schema_version=SCHEMA_VERSION,
    )

    manifest_dict = canonical_data(asdict(manifest_obj))

    with FileLock(str(root / ".manifest.lock"), timeout=30):
        if manifest_path.exists() or completion_path.exists():
            return _verify_and_return_existing(
                root,
                year_package_id=year_package_id,
                source_canonical_sha256=source_canonical_sha256,
            )

        # Write manifest atomically
        atomic_json(manifest_path, manifest_dict)

        # Write completion marker
        completion = canonical_data({
            "schema_version": COMPLETION_SCHEMA_VERSION,
            "status": "COMPLETE",
            "classification": CLASSIFICATION,
            "label": LABEL,
            "year_package_id": year_package_id,
            "manifest_relative_path": "manifest.json",
            "manifest_sha256": file_sha256(manifest_path),
        })
        atomic_json(completion_path, completion)

    return manifest_dict


def verify_derived_candle_manifest(output_root: Path) -> dict:
    """Verify that an existing derived-candle manifest is internally consistent."""
    root = Path(output_root).resolve(strict=True)
    manifest_path = root / "manifest.json"
    completion_path = root / "pipeline.complete.json"

    if not manifest_path.is_file():
        raise AcquisitionError("Derived-candle manifest.json is missing")
    if not completion_path.is_file():
        raise AcquisitionError("Derived-candle pipeline.complete.json is missing")

    try:
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AcquisitionError("Derived-candle manifest or completion is unreadable") from exc

    if completion.get("schema_version") != COMPLETION_SCHEMA_VERSION:
        raise AcquisitionError("Derived-candle completion schema_version mismatch")
    if completion.get("status") != "COMPLETE":
        raise AcquisitionError("Derived-candle completion status is not COMPLETE")
    if file_sha256(manifest_path) != completion.get("manifest_sha256"):
        raise AcquisitionError("Derived-candle manifest SHA-256 mismatch vs completion marker")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise AcquisitionError("Derived-candle manifest schema_version mismatch")
    if manifest.get("classification") != CLASSIFICATION:
        raise AcquisitionError("Derived-candle manifest classification must be DEVELOPMENT_ONLY")

    return manifest


def _verify_and_return_existing(
    root: Path,
    *,
    year_package_id: str,
    source_canonical_sha256: str,
) -> dict:
    manifest = verify_derived_candle_manifest(root)
    if manifest.get("year_package_id") != year_package_id:
        raise AcquisitionError(
            "Existing derived-candle manifest year_package_id does not match request"
        )
    if manifest.get("source_canonical_sha256") != source_canonical_sha256:
        raise AcquisitionError(
            "Existing derived-candle manifest source_canonical_sha256 does not match"
        )
    return manifest
