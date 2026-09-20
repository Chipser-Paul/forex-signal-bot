"""Phase 8C discovery/registration for attested derived candle packages.

Registers an existing, verified attestation in a minimal external discovery
record so downstream validation can discover the attested package by stable
content identity, manifest hash, attestation hash, source year-package
identity, schema version, classification and verification status.

This is a discovery mechanism only.  It never classifies the complete
empirical dataset as accepted: DXY history, USD news history, broker
metadata, slippage/fill evidence and an untouched holdout remain missing.

The record lives outside Git, is written locked, atomically and
non-overwriting, is idempotent for identical inputs, and fails closed on
tampering, missing attestations, hash mismatches or ambiguous selection.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from filelock import FileLock

from bot.validation.models import canonical_data

from .candle_attestation import (
    ATTESTATION_SCHEMA_VERSION,
    CLASSIFICATION,
    LABEL,
    VERIFIED_TIMEFRAMES,
    load_attestation,
)
from .models import AcquisitionError
from .storage import file_sha256

UTC = timezone.utc
DISCOVERY_SCHEMA_VERSION = "phase8c.derived-candle-discovery.v1"
DISCOVERY_RECORD_NAME = "discovery.json"
DISCOVERY_SIDECAR_SUFFIX = ".sha256"
DISCOVERY_LOCK_NAME = ".discovery.lock"

MISSING_DATASET_COMPONENTS: tuple[str, ...] = (
    "DXY_history_or_all_six_causally_aligned_constituents",
    "complete_historical_high_impact_USD_news_with_provenance_and_licensing",
    "historically_effective_broker_metadata",
    "commission_schedule",
    "swap_rollover_timezone_and_triple_swap_rules",
    "empirical_slippage_fill_evidence",
    "untouched_holdout_data",
)

# Modules whose committed content constitutes the package verifier at the
# verification commit.  The attestation/discovery modules themselves are
# meta-infrastructure introduced by this checkpoint; they record results and
# do not define package validity, so they are not required to exist at
# earlier verification commits.
VERIFIER_MODULES: tuple[str, ...] = (
    "bot/acquisition/candle_pipeline.py",
    "bot/acquisition/candle_store.py",
    "bot/acquisition/candle_manifest.py",
)
FINGERPRINT_PREFIX = "phase8c-verifier-v1:"


@dataclass(frozen=True)
class DiscoveryIdentity:
    attestation_id: str
    package_id: str
    discovery_sha256: str
    discovery_physical_sha256: str


def code_fingerprint(
    commit: str,
    *,
    worktree_root: Path | None = None,
    module_hashes: Mapping[str, str] | None = None,
) -> str:
    """Fingerprint the verifier modules at an exact commit.

    Prefers committed content via ``git show <commit>:<path>``.  For synthetic
    test contexts, an explicit ``module_hashes`` mapping may be supplied; it
    is hashed exactly like committed content.
    """
    if module_hashes is None:
        if worktree_root is None:
            raise AcquisitionError("DISCOVERY_FINGERPRINT_SOURCE_INVALID")
        module_hashes = {}
        for relative in VERIFIER_MODULES:
            try:
                blob = subprocess.check_output(
                    ["git", "show", f"{commit}:{relative}"],
                    cwd=str(worktree_root),
                    stderr=subprocess.DEVNULL,
                )
            except (OSError, subprocess.CalledProcessError) as exc:
                raise AcquisitionError(
                    f"DISCOVERY_FINGERPRINT_MODULE_UNAVAILABLE: {relative}"
                ) from exc
            module_hashes[relative] = hashlib.sha256(blob).hexdigest()
    payload = json.dumps(
        {
            "commit": str(commit),
            "modules": {str(k): str(v) for k, v in sorted(module_hashes.items())},
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return FINGERPRINT_PREFIX + hashlib.sha256(payload.encode("ascii")).hexdigest()


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        canonical_data(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _paths(discovery_root: Path, attestation_id: str) -> tuple[Path, Path, Path]:
    directory = Path(discovery_root) / str(attestation_id)
    return (
        directory,
        directory / DISCOVERY_RECORD_NAME,
        directory / (DISCOVERY_RECORD_NAME + DISCOVERY_SIDECAR_SUFFIX),
    )


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


def _select_unique_attestation(attestations_root: Path, attestation_id: str | None) -> dict:
    """Fail closed unless exactly one attestation is selected deterministically."""
    if attestation_id is not None:
        return load_attestation(attestations_root, attestation_id)
    root = Path(attestations_root)
    if not root.is_dir():
        raise AcquisitionError("ATTESTATION_MISSING")
    candidates = sorted(
        item.name
        for item in root.iterdir()
        if (item / "attestation.json").is_file()
    )
    if not candidates:
        raise AcquisitionError("ATTESTATION_MISSING")
    if len(candidates) > 1:
        raise AcquisitionError("DISCOVERY_ATTESTATION_SELECTION_AMBIGUOUS")
    return load_attestation(root, candidates[0])


def _load_record_file(record_path: Path, sidecar_path: Path) -> dict:
    try:
        stored = json.loads(record_path.read_text(encoding="utf-8"))
        recorded_physical = sidecar_path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError("DISCOVERY_RECORD_UNREADABLE") from exc
    if not isinstance(stored, dict):
        raise AcquisitionError("DISCOVERY_RECORD_UNREADABLE")
    if stored.get("schema_version") != DISCOVERY_SCHEMA_VERSION:
        raise AcquisitionError("DISCOVERY_RECORD_SCHEMA_UNSUPPORTED")
    if file_sha256(record_path) != recorded_physical:
        raise AcquisitionError("DISCOVERY_RECORD_PHYSICAL_HASH_MISMATCH")
    body = {
        key: value
        for key, value in stored.items()
        if key != "discovery_canonical_sha256"
    }
    if _canonical_hash(body) != stored.get("discovery_canonical_sha256"):
        raise AcquisitionError("DISCOVERY_RECORD_CANONICAL_HASH_MISMATCH")
    return stored


def build_discovery_record(attestation: Mapping[str, object]) -> dict:
    """Build the discovery record body from a verified attestation."""
    if attestation.get("schema_version") != ATTESTATION_SCHEMA_VERSION:
        raise AcquisitionError("DISCOVERY_ATTESTATION_SCHEMA_UNSUPPORTED")
    package = attestation["package"]
    provenance = attestation["provenance"]
    coverage = attestation["coverage"]
    rows = {
        str(item["timeframe"]): int(item["record_count"])
        for item in attestation["verified_partitions"]
    }
    hashes = {
        str(item["timeframe"]): str(item["sha256"])
        for item in attestation["verified_partitions"]
    }
    if tuple(sorted(rows)) != tuple(sorted(VERIFIED_TIMEFRAMES)):
        raise AcquisitionError("DISCOVERY_ATTESTATION_TIMEFRAMES_INCOMPLETE")

    record = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "discovery_id": str(attestation["attestation_id"]),
        "created_utc": _now_utc_iso(),
        "classification": CLASSIFICATION,
        "label": LABEL,
        "discovery": {
            "package_id": str(package["package_id"]),
            "identity_basis": str(package["identity_basis"]),
            "package_schema_version": str(package["package_schema_version"]),
            "manifest_schema_version": str(package["manifest_schema_version"]),
            "manifest_sha256": str(package["manifest_sha256"]),
            "completion_marker_sha256": str(package["completion_marker_sha256"]),
            "source_year_package_id": str(package["source_year_package_id"]),
            "source_canonical_sha256": str(package["source_canonical_sha256"]),
            "source_row_count": int(package["source_row_count"]),
            "attestation_id": str(attestation["attestation_id"]),
            "attestation_canonical_sha256": str(
                attestation["attestation_canonical_sha256"]
            ),
            "implementation_commit": str(provenance["implementation_commit"]),
            "verification_commit": str(provenance["verification_commit"]),
            "verification_fingerprint": str(provenance["verification_fingerprint"]),
            "generation_base_commit": provenance.get("generation_base_commit"),
            "generation_commit_equivalence": str(
                provenance["generation_commit_equivalence"]
            ),
            "verification_status": "VERIFIED_AT_COMMIT",
            "timeframes": list(coverage["timeframe_order"]),
            "row_counts_by_timeframe": rows,
            "partition_sha256_by_timeframe": hashes,
        },
        "dataset_readiness": {
            "accepted_for_final_validation": False,
            "available_components": [
                "verified_2024_xauusdm_ticks",
                "derived_causal_bid_ask_candles",
                "observed_spread_evidence",
            ],
            "missing_components": list(MISSING_DATASET_COMPONENTS),
            "note": (
                "Registration is discovery only and does not classify the "
                "complete empirical dataset as accepted. Only the 2024 "
                "XAUUSDm ticks, the derived causal candles and observed "
                "spread evidence are available."
            ),
        },
        "strategy_evaluation_statement": str(
            attestation["strategy_evaluation_statement"]
        ),
        "holdout_accessed": False,
        "mt5_or_trading_accessed": False,
    }
    return canonical_data(record)


def register_attested_package(
    attestations_root: Path,
    discovery_root: Path,
    *,
    attestation_id: str | None = None,
) -> tuple[dict, DiscoveryIdentity]:
    """Register an attested package; idempotent, locked, atomic, fail-closed.

    With ``attestation_id=None`` exactly one attestation must exist beneath
    ``attestations_root``; any other count fails closed.
    """
    attestation = _select_unique_attestation(attestations_root, attestation_id)
    record_id = str(attestation["attestation_id"])
    record = build_discovery_record(attestation)
    record["created_utc"] = _now_utc_iso()
    record["discovery_canonical_sha256"] = _canonical_hash(
        {k: v for k, v in record.items() if k != "discovery_canonical_sha256"}
    )
    payload = json.dumps(
        canonical_data(record),
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"

    discovery_root = Path(discovery_root)
    with FileLock(str(discovery_root / DISCOVERY_LOCK_NAME), timeout=15):
        discovery_root.mkdir(parents=True, exist_ok=True)
        directory, record_path, sidecar_path = _paths(discovery_root, record_id)
        if record_path.exists():
            existing = _load_record_file(record_path, sidecar_path)
            # created_utc records the first registration wall clock only; it is
            # excluded from the immutability comparison so that repeated
            # execution with identical immutable inputs stays idempotent.
            immutable_keys = ("discovery_canonical_sha256", "created_utc")
            if _canonical_hash(
                {k: v for k, v in existing.items() if k not in immutable_keys}
            ) != _canonical_hash(
                {k: v for k, v in record.items() if k not in immutable_keys}
            ):
                raise AcquisitionError(
                    "DISCOVERY_REGISTRATION_CONFLICT: existing record differs"
                )
            return canonical_data(existing), DiscoveryIdentity(
                attestation_id=record_id,
                package_id=str(existing["discovery"]["package_id"]),
                discovery_sha256=str(existing["discovery_canonical_sha256"]),
                discovery_physical_sha256=sidecar_path.read_text(encoding="ascii").strip(),
            )
        directory.mkdir(parents=True, exist_ok=False)
        _atomic_write_bytes(record_path, payload.encode("utf-8"))
        physical_sha256 = file_sha256(record_path)
        _atomic_write_bytes(
            sidecar_path, (physical_sha256 + "\n").encode("ascii")
        )
    return canonical_data(record), DiscoveryIdentity(
        attestation_id=record_id,
        package_id=str(record["discovery"]["package_id"]),
        discovery_sha256=str(record["discovery_canonical_sha256"]),
        discovery_physical_sha256=physical_sha256,
    )


def load_discovery_record(
    discovery_root: Path, attestation_id: str
) -> dict:
    """Load and verify a discovery record; fail closed on any tampering."""
    _, record_path, sidecar_path = _paths(discovery_root, attestation_id)
    if not record_path.is_file() or not sidecar_path.is_file():
        raise AcquisitionError("DISCOVERY_RECORD_MISSING")
    return _load_record_file(record_path, sidecar_path)
