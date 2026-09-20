"""Phase 8D discovery/readiness registration for the causal DXY package.

Registers the verified DXY development package in the external Phase 8
readiness/discovery area so downstream validation can discover it by stable
content identity.  Registration is discovery only: the complete empirical
dataset remains unaccepted, DXY news, broker metadata, commission, swap and
slippage evidence and the untouched holdout remain missing.

The record lives outside Git, is written locked, atomically and
non-overwriting, is idempotent for identical inputs, and fails closed on
tampering, missing packages, hash mismatches or ambiguous selection.

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

from filelock import FileLock

from bot.validation.models import canonical_data

from .dxy_contracts import CLASSIFICATION, LABEL, DXY_SYMBOL_MAP
from .dxy_package import (
    MANIFEST_NAME,
    COMPLETION_MARKER,
    _discover_existing_package,
    verify_package_readonly,
)
from .models import AcquisitionError
from .storage import file_sha256

UTC = timezone.utc
DISCOVERY_SCHEMA_VERSION = "phase8d.dxy-discovery.v1"
DISCOVERY_RECORD_NAME = "discovery.json"
DISCOVERY_SIDECAR_SUFFIX = ".sha256"
DISCOVERY_LOCK_NAME = ".discovery.lock"

REMAINING_MISSING_COMPONENTS: tuple[str, ...] = (
    "complete_historical_high_impact_USD_news_with_provenance_and_licensing",
    "historically_effective_broker_metadata",
    "commission_schedule",
    "swap_rollover_timezone_and_triple_swap_rules",
    "empirical_slippage_fill_evidence",
    "untouched_holdout_data",
)

AVAILABLE_COMPONENTS: tuple[str, ...] = (
    "verified_2024_xauusdm_ticks",
    "derived_causal_bid_ask_candles",
    "observed_spread_evidence",
    "causal_2024_dxy_development_input",
)


@dataclass(frozen=True)
class DxyDiscoveryIdentity:
    package_id: str
    discovery_sha256: str
    discovery_physical_sha256: str


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


def build_discovery_record(verified: Mapping[str, object]) -> dict:
    """Build the discovery record body from a verified package."""
    record = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "discovery_id": str(verified["package_id"]),
        "created_utc": _now_utc_iso(),
        "classification": CLASSIFICATION,
        "label": LABEL,
        "discovery": {
            "package_id": str(verified["package_id"]),
            "identity_basis": str(verified["identity_basis"]),
            "package_schema_version": str(verified["package_schema_version"]),
            "manifest_schema_version": str(verified["manifest_schema_version"]),
            "manifest_sha256": str(verified["manifest_sha256"]),
            "completion_marker_sha256": str(verified["completion_marker_sha256"]),
            "source_year_package_id": str(verified["source_year_package_id"]),
            "source_year_canonical_sha256": str(verified["source_year_canonical_sha256"]),
            "source_year_row_count": int(verified["source_year_row_count"]),
            "implementation_commit": str(verified["implementation_commit"]),
            "code_fingerprint": str(verified["code_fingerprint"]),
            "retrieved_utc": str(verified["retrieved_utc"]),
            "terminal_build": verified.get("terminal_build"),
            "verification_status": "VERIFIED_AT_COMMIT",
            "symbol_mappings": {
                symbol: str(DXY_SYMBOL_MAP[symbol]) for symbol in sorted(DXY_SYMBOL_MAP)
            },
            "constituents": {
                symbol: {
                    "sha256": str(part["sha256"]),
                    "canonical_content_sha256": str(part["canonical_content_sha256"]),
                    "record_count": int(part["record_count"]),
                    "missing_window_count": int(part["missing_window_count"]),
                    "gap_runs": int(part["gap_runs"]),
                }
                for symbol, part in sorted(verified["constituents"].items())
            },
            "causal_dxy": {
                "sha256": str(verified["causal_dxy"]["sha256"]),
                "canonical_content_sha256": str(
                    verified["causal_dxy"]["canonical_content_sha256"]
                ),
                "record_count": int(verified["causal_dxy"]["record_count"]),
                "first_available": str(verified["causal_dxy"]["first_available"]),
                "last_available": str(verified["causal_dxy"]["last_available"]),
            },
            "staleness_report": dict(verified["staleness_report"]),
            "total_constituent_rows": int(verified["total_constituent_rows"]),
            "total_dxy_rows": int(verified["total_dxy_rows"]),
        },
        "dataset_readiness": {
            "accepted_for_final_validation": False,
            "strategy_evaluation_authorized": False,
            "holdout_access_authorized": False,
            "available_components": list(AVAILABLE_COMPONENTS),
            "missing_components": list(REMAINING_MISSING_COMPONENTS),
            "note": (
                "Registration is discovery only and does not classify the "
                "complete empirical dataset as accepted. Available inputs are "
                "the 2024 XAUUSDm ticks, derived causal candles, observed "
                "spread evidence and the causal 2024 DXY development input."
            ),
        },
        "strategy_evaluation_statement": (
            "No strategy evaluation, backtest, optimization, tuning, "
            "profitability metric, win rate, profit factor or capital "
            "projection was computed for this registration."
        ),
        "holdout_accessed": False,
        "mt5_or_trading_accessed": False,
    }
    return canonical_data(record)


def register_dxy_package(
    data_root: Path,
    discovery_root: Path,
    *,
    package_root: Path | None = None,
) -> tuple[dict, DxyDiscoveryIdentity]:
    """Register the verified DXY package; idempotent, locked, atomic."""
    if package_root is None:
        selected = _discover_existing_package(data_root)
        if selected is None:
            raise AcquisitionError("DXY_PACKAGE_MISSING")
    else:
        selected = Path(package_root)
    verified = verify_package_readonly(selected)
    record = build_discovery_record(verified)
    record_id = str(record["discovery_id"])
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
        directory = discovery_root / record_id
        record_path = directory / DISCOVERY_RECORD_NAME
        sidecar_path = directory / (DISCOVERY_RECORD_NAME + DISCOVERY_SIDECAR_SUFFIX)
        if record_path.exists():
            existing = _load_record_file(record_path, sidecar_path)
            immutable_keys = ("discovery_canonical_sha256", "created_utc")
            if _canonical_hash(
                {k: v for k, v in existing.items() if k not in immutable_keys}
            ) != _canonical_hash(
                {k: v for k, v in record.items() if k not in immutable_keys}
            ):
                raise AcquisitionError(
                    "DXY_DISCOVERY_REGISTRATION_CONFLICT: existing record differs"
                )
            return canonical_data(existing), DxyDiscoveryIdentity(
                package_id=record_id,
                discovery_sha256=str(existing["discovery_canonical_sha256"]),
                discovery_physical_sha256=sidecar_path.read_text(encoding="ascii").strip(),
            )
        directory.mkdir(parents=True, exist_ok=False)
        _atomic_write_bytes(record_path, payload.encode("utf-8"))
        physical_sha256 = file_sha256(record_path)
        _atomic_write_bytes(sidecar_path, (physical_sha256 + "\n").encode("ascii"))
    return canonical_data(record), DxyDiscoveryIdentity(
        package_id=record_id,
        discovery_sha256=str(record["discovery_canonical_sha256"]),
        discovery_physical_sha256=physical_sha256,
    )


def load_dxy_discovery_record(discovery_root: Path, package_id: str) -> dict:
    """Load and verify a discovery record; fail closed on any tampering."""
    directory = Path(discovery_root) / str(package_id)
    record_path = directory / DISCOVERY_RECORD_NAME
    sidecar_path = directory / (DISCOVERY_RECORD_NAME + DISCOVERY_SIDECAR_SUFFIX)
    if not record_path.is_file() or not sidecar_path.is_file():
        raise AcquisitionError("DXY_DISCOVERY_RECORD_MISSING")
    return _load_record_file(record_path, sidecar_path)


def _load_record_file(record_path: Path, sidecar_path: Path) -> dict:
    try:
        stored = json.loads(record_path.read_text(encoding="utf-8"))
        recorded_physical = sidecar_path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError("DXY_DISCOVERY_RECORD_UNREADABLE") from exc
    if not isinstance(stored, dict):
        raise AcquisitionError("DXY_DISCOVERY_RECORD_UNREADABLE")
    if stored.get("schema_version") != DISCOVERY_SCHEMA_VERSION:
        raise AcquisitionError("DXY_DISCOVERY_RECORD_SCHEMA_UNSUPPORTED")
    if file_sha256(record_path) != recorded_physical:
        raise AcquisitionError("DXY_DISCOVERY_RECORD_PHYSICAL_HASH_MISMATCH")
    body = {
        key: value
        for key, value in stored.items()
        if key != "discovery_canonical_sha256"
    }
    if _canonical_hash(body) != stored.get("discovery_canonical_sha256"):
        raise AcquisitionError("DXY_DISCOVERY_RECORD_CANONICAL_HASH_MISMATCH")
    return stored
