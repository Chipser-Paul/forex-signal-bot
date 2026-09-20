"""Phase 8D causal DXY development-data package (atomic, non-overwriting).

Publishes and verifies a development-only package containing the six
constituent H1 bar partitions, the causal DXY partition, a versioned
manifest, a completion marker, coverage/gap/staleness reports and a
provenance record under a new non-overwriting directory beneath the external
Phase 8 data root.

Storage is atomic (temporary + fsync + rename), non-overwriting, and
idempotent: re-running with identical inputs recognizes the existing package
and returns its identity; any conflict fails closed.  Existing XAUUSDm
artifacts are never touched.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from bot.validation.models import canonical_data

from .dxy_contracts import (
    CLASSIFICATION,
    DEVELOPMENT_END_MS,
    DEVELOPMENT_START_MS,
    DXY_CONSTITUENT_ORDER,
    H1_DURATION_MS,
    TIMEFRAME,
    LABEL,
    MAPPING_CURRENCY_EXPECTATIONS,
    DXY_SYMBOL_MAP,
    canonical_constituent_hash,
    canonical_dxy_hash,
    compute_causal_dxy_rows,
    compute_gap_report,
    iso_z,
)
from .models import AcquisitionError
from .storage import file_sha256, validate_output_root

UTC = timezone.utc
PACKAGE_SCHEMA_VERSION = "phase8d.dxy-package.v1"
MANIFEST_SCHEMA_VERSION = "phase8d.dxy-manifest.v1"
COMPLETION_MARKER = "pipeline.complete.json"
MANIFEST_NAME = "manifest.json"
COVER_REPORT_NAME = "coverage_report.json"
GAP_REPORT_NAME = "gap_staleness_report.json"
PROVENANCE_NAME = "provenance.json"
DXY_PARTITION_PATH = "dxy/causal-dxy-2024.parquet"


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        canonical_data(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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


def _atomic_write_json(path: Path, value: object) -> None:
    payload = json.dumps(
        canonical_data(value),
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"
    _atomic_write_bytes(path, payload.encode("utf-8"))


def resolve_git_commit(worktree_root: Path | None = None) -> str:
    """Return the exact 40-char HEAD commit of the phase8 worktree."""
    root = Path(worktree_root) if worktree_root is not None else GIT_WORKTREE_FALLBACK
    try:
        blob = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(root), stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AcquisitionError("DXY_PROVENANCE_COMMIT_UNAVAILABLE") from exc
    commit = blob.decode("ascii").strip()
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise AcquisitionError("DXY_PROVENANCE_COMMIT_INVALID")
    return commit


def resolve_code_fingerprint(worktree_root: Path | None = None) -> str:
    """Fingerprint the Phase 8D implementation modules at HEAD."""
    root = Path(worktree_root) if worktree_root is not None else GIT_WORKTREE_FALLBACK
    commit = resolve_git_commit(root)
    module_hashes: dict[str, str] = {}
    for relative in IMPLEMENTATION_MODULES:
        try:
            blob = subprocess.check_output(
                ["git", "show", f"{commit}:{relative}"],
                cwd=str(root),
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise AcquisitionError(
                f"DXY_FINGERPRINT_MODULE_UNAVAILABLE: {relative}"
            ) from exc
        module_hashes[relative] = hashlib.sha256(blob).hexdigest()
    payload = json.dumps(
        {"commit": commit, "modules": dict(sorted(module_hashes.items()))},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "phase8d-pipeline-v1:" + hashlib.sha256(payload.encode("ascii")).hexdigest()


IMPLEMENTATION_MODULES: tuple[str, ...] = (
    "bot/acquisition/dxy_contracts.py",
    "bot/acquisition/dxy_package.py",
    "bot/acquisition/dxy_acquisition.py",
    "bot/acquisition/dxy_discovery.py",
)


def resolve_symbol_mappings(gateway: object) -> dict[str, dict[str, object]]:
    """Verify all six broker mappings by currency fields (fail closed)."""
    resolved: dict[str, dict[str, object]] = {}
    for canonical_symbol, broker_symbol in sorted(DXY_SYMBOL_MAP.items()):
        info = gateway.symbol_info(broker_symbol)
        if info is None:
            raise AcquisitionError(
                f"DXY_MAPPING_MISSING: {canonical_symbol}->{broker_symbol}"
            )
        base = str(info.get("currency_base", ""))
        profit = str(info.get("currency_profit", ""))
        expected_base, expected_profit = MAPPING_CURRENCY_EXPECTATIONS[canonical_symbol]
        if base != expected_base or profit != expected_profit:
            raise AcquisitionError(
                f"DXY_MAPPING_CURRENCY_MISMATCH: {canonical_symbol} "
                f"expected {expected_base}/{expected_profit}, got {base}/{profit}"
            )
        if not info.get("name") == broker_symbol:
            raise AcquisitionError(f"DXY_MAPPING_NAME_MISMATCH: {broker_symbol}")
        resolved[canonical_symbol] = {
            "canonical_symbol": canonical_symbol,
            "broker_symbol": broker_symbol,
            "currency_base": base,
            "currency_profit": profit,
            "digits": int(info.get("digits", 0)),
            "point": float(info.get("point", 0)),
        }
    return resolved


def verify_mapping_offline(records: Sequence[Mapping[str, object]]) -> dict[str, str]:
    """Re-verify mappings from persisted records without MT5."""
    observed: dict[str, str] = {}
    for record in records:
        canonical_symbol = str(record["canonical_symbol"])
        broker_symbol = str(record["broker_symbol"])
        expected = DXY_SYMBOL_MAP.get(canonical_symbol)
        if expected != broker_symbol:
            raise AcquisitionError(
                f"DXY_MAPPING_MISMATCH_IN_PACKAGE: {canonical_symbol}"
            )
        observed[canonical_symbol] = broker_symbol
    if set(observed) != set(DXY_SYMBOL_MAP):
        raise AcquisitionError("DXY_MAPPING_SET_INCOMPLETE")
    return observed


def _constituent_records_to_rows(
    records: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Full record shape for storage: canonical hashes recompute exactly."""
    rows: list[dict[str, object]] = []
    for record in records:
        rows.append({
            "canonical_symbol": str(record["canonical_symbol"]),
            "broker_symbol": str(record["broker_symbol"]),
            "timeframe": str(record["timeframe"]),
            "open_time_ms": int(record["open_time_ms"]),
            "close_time_ms": int(record["close_time_ms"]),
            "available_at_ms": int(record["available_at_ms"]),
            "open_time": iso_z(int(record["open_time_ms"])),
            "available_at": iso_z(int(record["available_at_ms"])),
            "open": str(record["open"]),
            "high": str(record["high"]),
            "low": str(record["low"]),
            "close": str(record["close"]),
            "tick_volume": (
                None if record.get("tick_volume") is None else str(record["tick_volume"])
            ),
            "spread": None if record.get("spread") is None else str(record["spread"]),
            "real_volume": (
                None if record.get("real_volume") is None else str(record["real_volume"])
            ),
            "sequence_id": str(record["sequence_id"]),
            "provenance_id": str(record["provenance_id"]),
            "retrieved_utc": str(record["retrieved_utc"]),
            "terminal_build": (
                None if record.get("terminal_build") is None else str(record["terminal_build"])
            ),
            "source_interval_start": str(record["source_interval_start"]),
            "source_interval_end": str(record["source_interval_end"]),
            "row_identity": str(record["row_identity"]),
        })
    return tuple(rows)


def _write_parquet_records(
    path: Path,
    records: Sequence[Mapping[str, object]],
    *,
    schema_kind: str,
) -> tuple[int, str]:
    """Write records as a zstd parquet file atomically; return (rows, sha)."""
    import pandas as pd

    partial = path.with_suffix(path.suffix + ".partial")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame = pd.DataFrame(list(records))
        frame.to_parquet(partial, compression="zstd", index=False)
        with partial.open("r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(partial, path)
        rows = len(records)
        sha256 = file_sha256(path)
        return rows, sha256
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _read_parquet_records(path: Path) -> tuple[dict[str, object], ...]:
    import pandas as pd

    frame = pd.read_parquet(path)
    rows: list[dict[str, object]] = []
    for item in frame.to_dict(orient="records"):
        record: dict[str, object] = {}
        for key, value in item.items():
            record[str(key)] = None if pd.isna(value) else value
        rows.append(record)
    return tuple(rows)


def verify_package_readonly(
    package_root: Path,
    *,
    expected: Mapping[str, object] | None = None,
) -> dict:
    """Complete read-only verification; raises AcquisitionError on any defect."""
    root = Path(package_root).resolve(strict=True)
    manifest_path = root / MANIFEST_NAME
    completion_path = root / COMPLETION_MARKER
    if not manifest_path.is_file() or not completion_path.is_file():
        raise AcquisitionError("DXY_PACKAGE_INCOMPLETE")

    manifest_sha256 = file_sha256(manifest_path)
    completion_sha256 = file_sha256(completion_path)
    completion = _load_json(completion_path)
    if str(completion.get("manifest_sha256")) != manifest_sha256:
        raise AcquisitionError("DXY_PACKAGE_COMPLETION_BINDING_INVALID")
    if completion.get("complete") is not True:
        raise AcquisitionError("DXY_PACKAGE_COMPLETION_FLAG_INVALID")

    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise AcquisitionError("DXY_PACKAGE_MANIFEST_SCHEMA_UNSUPPORTED")
    if manifest.get("classification") != CLASSIFICATION or LABEL not in str(manifest.get("label", "")):
        raise AcquisitionError("DXY_PACKAGE_CLASSIFICATION_INVALID")

    source_identity = manifest["source_year_package"]
    verify_mapping_offline(
        [{"canonical_symbol": item["canonical_symbol"], "broker_symbol": item["broker_symbol"]}
         for item in manifest["constituents"]]
    )

    constituent_part: dict[str, object] = {}
    bars_by_symbol: dict[str, list[dict[str, object]]] = {}
    total_constituent_rows = 0
    for entry in manifest["constituents"]:
        canonical_symbol = str(entry["canonical_symbol"])
        relative_path = str(entry["partition_relative_path"])
        final_path = root / relative_path
        if not final_path.is_file():
            raise AcquisitionError(f"DXY_PARTITION_MISSING: {canonical_symbol}")
        if file_sha256(final_path) != str(entry["sha256"]):
            raise AcquisitionError(f"DXY_PARTITION_PHYSICAL_HASH_MISMATCH: {canonical_symbol}")
        records = _read_parquet_records(final_path)
        if len(records) != int(entry["record_count"]):
            raise AcquisitionError(f"DXY_PARTITION_ROW_COUNT_MISMATCH: {canonical_symbol}")
        if canonical_constituent_hash(records) != str(entry["canonical_content_sha256"]):
            raise AcquisitionError(f"DXY_PARTITION_CANONICAL_HASH_MISMATCH: {canonical_symbol}")
        opens = [int(record["open_time_ms"]) for record in records]
        if opens != sorted(opens) or len(set(opens)) != len(opens):
            raise AcquisitionError(f"DXY_PARTITION_ORDERING_VIOLATION: {canonical_symbol}")
        available = [int(record["available_at_ms"]) for record in records]
        if any(available_at_ms < open_ms + H1_DURATION_MS for open_ms, available_at_ms in zip(opens, available)):
            raise AcquisitionError(f"DXY_PARTITION_AVAILABILITY_VIOLATION: {canonical_symbol}")
        if any(available_at_ms >= DEVELOPMENT_END_MS for available_at_ms in available):
            raise AcquisitionError(f"DXY_PARTITION_DEVELOPMENT_BOUNDARY_VIOLATION: {canonical_symbol}")
        if int(entry["first_open_ms"]) != opens[0] or int(entry["last_open_ms"]) != opens[-1]:
            raise AcquisitionError(f"DXY_PARTITION_COVERAGE_BOUNDARY_MISMATCH: {canonical_symbol}")
        gap_report = compute_gap_report(records)
        reported_gap = manifest.get("gap_reports", {}).get(canonical_symbol, {})
        if int(reported_gap.get("missing_window_count", -1)) != gap_report["missing_window_count"]:
            raise AcquisitionError(f"DXY_GAP_REPORT_MISMATCH: {canonical_symbol}")
        if int(reported_gap.get("gap_runs", -1)) != gap_report["gap_runs"]:
            raise AcquisitionError(f"DXY_GAP_REPORT_MISMATCH: {canonical_symbol}")
        for record in records:
            if str(record["broker_symbol"]) != str(entry["broker_symbol"]):
                raise AcquisitionError(f"DXY_PARTITION_SYMBOL_MISMATCH: {canonical_symbol}")
            if float(record["close"]) <= 0 or float(record["open"]) <= 0:
                raise AcquisitionError(f"DXY_PARTITION_NON_POSITIVE_PRICE: {canonical_symbol}")
        constituent_part[canonical_symbol] = {
            "partition_relative_path": relative_path,
            "sha256": str(entry["sha256"]),
            "canonical_content_sha256": str(entry["canonical_content_sha256"]),
            "record_count": len(records),
            "first_open": iso_z(opens[0]),
            "last_open": iso_z(opens[-1]),
            "missing_window_count": gap_report["missing_window_count"],
            "gap_runs": gap_report["gap_runs"],
        }
        bars_by_symbol[canonical_symbol] = [
            {
                "available_at_ms": int(record["available_at_ms"]),
                "close": float(record["close"]),
                "row_identity": str(record["row_identity"]),
                "open_time_ms": int(record["open_time_ms"]),
            }
            for record in records
        ]
        total_constituent_rows += len(records)

    recomputed_rows, recompute_summary = compute_causal_dxy_rows(
        {symbol: bars for symbol, bars in bars_by_symbol.items()},
        interval_start_ms=DEVELOPMENT_START_MS,
        interval_end_ms=DEVELOPMENT_END_MS,
    )
    dxy_entry = manifest["causal_dxy"]
    dxy_path = root / str(dxy_entry["partition_relative_path"])
    if not dxy_path.is_file():
        raise AcquisitionError("DXY_PARTITION_MISSING: causal_dxy")
    if file_sha256(dxy_path) != str(dxy_entry["sha256"]):
        raise AcquisitionError("DXY_PARTITION_PHYSICAL_HASH_MISMATCH: causal_dxy")
    dxy_readback = _read_parquet_records(dxy_path)
    if len(dxy_readback) != int(dxy_entry["record_count"]):
        raise AcquisitionError("DXY_PARTITION_ROW_COUNT_MISMATCH: causal_dxy")
    if canonical_dxy_hash(dxy_readback) != str(dxy_entry["canonical_content_sha256"]):
        raise AcquisitionError("DXY_PARTITION_CANONICAL_HASH_MISMATCH: causal_dxy")
    recomputed_hashes = canonical_dxy_hash(recomputed_rows)
    if recomputed_hashes != canonical_dxy_hash(dxy_readback):
        raise AcquisitionError("DXY_FORMULA_REPRODUCTION_MISMATCH")
    if len(recomputed_rows) != len(dxy_readback):
        raise AcquisitionError("DXY_FORMULA_REPRODUCTION_ROW_COUNT_MISMATCH")

    dxy_available = [int(row["available_at_ms"]) for row in dxy_readback]
    if dxy_available != sorted(dxy_available) or len(set(dxy_available)) != len(dxy_available):
        raise AcquisitionError("DXY_SERIES_ORDERING_VIOLATION")
    if any(ts >= DEVELOPMENT_END_MS for ts in dxy_available):
        raise AcquisitionError("DXY_SERIES_DEVELOPMENT_BOUNDARY_VIOLATION")
    for row in dxy_readback:
        value = float(row["dxy"])
        if value != value or value in (float("inf"), float("-inf")) or value <= 0:
            raise AcquisitionError("DXY_SERIES_VALUE_INVALID")
        for symbol in DXY_CONSTITUENT_ORDER:
            if symbol not in row["sources"]:
                raise AcquisitionError("DXY_SERIES_SOURCE_IDENTITY_MISSING")
    latest_available = dxy_available[-1] if dxy_available else None
    staleness_report = {
        "accepted_rows": len(dxy_readback),
        "rejected_rows": int(recompute_summary["rejected_rows"]),
        "rejections_by_reason": dict(recompute_summary["rejections_by_reason"]),
        "last_accepted_available_at": iso_z(latest_available) if latest_available is not None else None,
    }

    return canonical_data({
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_sha256": manifest_sha256,
        "completion_marker_sha256": completion_sha256,
        "package_id": str(manifest["package_id"]),
        "identity_basis": str(manifest["identity_basis"]),
        "source_year_package_id": str(source_identity["year_package_id"]),
        "source_year_canonical_sha256": str(source_identity["source_canonical_sha256"]),
        "source_year_row_count": int(source_identity["source_row_count"]),
        "implementation_commit": str(manifest["provenance"]["implementation_commit"]),
        "code_fingerprint": str(manifest["provenance"]["code_fingerprint"]),
        "retrieved_utc": str(manifest["provenance"]["retrieved_utc"]),
        "terminal_build": manifest["provenance"].get("terminal_build"),
        "constituents": constituent_part,
        "causal_dxy": {
            "partition_relative_path": str(dxy_entry["partition_relative_path"]),
            "sha256": str(dxy_entry["sha256"]),
            "canonical_content_sha256": str(dxy_entry["canonical_content_sha256"]),
            "record_count": len(dxy_readback),
            "first_available": iso_z(dxy_available[0]),
            "last_available": iso_z(dxy_available[-1]),
        },
        "gap_reports": {
            symbol: dict(manifest["gap_reports"][symbol]) for symbol in sorted(manifest["gap_reports"])
        },
        "staleness_report": staleness_report,
        "total_constituent_rows": total_constituent_rows,
        "total_dxy_rows": len(dxy_readback),
    })


def _load_json(path: Path) -> dict:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError(f"DXY_JSON_UNREADABLE: {Path(path).name}") from exc
    if not isinstance(document, dict):
        raise AcquisitionError(f"DXY_JSON_INVALID: {Path(path).name}")
    return document


def publish_dxy_package(
    data_root: Path,
    *,
    records_by_symbol: Mapping[str, Sequence[Mapping[str, object]]],
    resolved_mappings: Mapping[str, Mapping[str, object]],
    acquisition_evidence: Mapping[str, object],
    source_year_package_id: str,
    source_year_canonical_sha256: str,
    source_year_row_count: int,
    retrieved_utc: datetime,
    terminal_build: str | None,
    implementation_commit: str,
    code_fingerprint: str,
    minimum_free_bytes: int = 15 * 1024**3,
    worktree_root: Path | None = None,
) -> tuple[dict, dict]:
    """Publish the package; idempotent, atomic, non-overwriting, fail-closed."""
    data_root = validate_output_root(data_root, forbidden_roots=())
    free_bytes = shutil.disk_usage(data_root).free
    if free_bytes < minimum_free_bytes:
        raise AcquisitionError("DXY_DISK_RESERVE_BREACHED")

    records_by_symbol = {
        symbol: tuple(records_by_symbol[symbol]) for symbol in DXY_CONSTITUENT_ORDER
    }
    missing = [s for s in DXY_CONSTITUENT_ORDER if not records_by_symbol[s]]
    if missing:
        raise AcquisitionError(f"DXY_CONSTITUENT_DATA_MISSING: {','.join(missing)}")

    # Idempotency: recognize an identical existing package.
    existing = _discover_existing_package(data_root)
    if existing is not None:
        verified = verify_package_readonly(existing)
        if (
            verified["source_year_canonical_sha256"] != source_year_canonical_sha256
            or verified["implementation_commit"] != implementation_commit
            or verified["code_fingerprint"] != code_fingerprint
        ):
            raise AcquisitionError("DXY_PACKAGE_CONFLICT: existing package differs")
        for symbol in DXY_CONSTITUENT_ORDER:
            offered_hash = canonical_constituent_hash(records_by_symbol[symbol])
            stored_hash = str(
                verified["constituents"][symbol]["canonical_content_sha256"]
            )
            if offered_hash != stored_hash:
                raise AcquisitionError(
                    f"DXY_PACKAGE_CONFLICT: offered records differ for {symbol}"
                )
        return existing, verified

    all_records: list[Mapping[str, object]] = []
    for symbol in DXY_CONSTITUENT_ORDER:
        all_records.extend(records_by_symbol[symbol])
    verify_mapping_offline(all_records)

    dxy_rows, alignment_summary = compute_causal_dxy_rows(
        {
            symbol: [
                {
                    "available_at_ms": int(r["available_at_ms"]),
                    "close": float(r["close"]),
                    "row_identity": str(r["row_identity"]),
                    "open_time_ms": int(r["open_time_ms"]),
                }
                for r in records_by_symbol[symbol]
            ]
            for symbol in DXY_CONSTITUENT_ORDER
        },
        interval_start_ms=DEVELOPMENT_START_MS,
        interval_end_ms=DEVELOPMENT_END_MS,
    )
    if not dxy_rows:
        raise AcquisitionError("DXY_SERIES_EMPTY")

    timestamp = _now_utc_iso().replace(":", "").replace("-", "").replace("+00:00", "Z")
    package_id = f"dxy-development-2024-v1-{timestamp}"
    package_root = data_root / "dxy" / package_id
    try:
        package_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise AcquisitionError("DXY_PACKAGE_DIRECTORY_EXISTS") from exc

    try:
        constituent_parts = []
        for symbol in DXY_CONSTITUENT_ORDER:
            relative_path = f"constituents/{symbol.lower()}-h1-2024.parquet"
            rows = _constituent_records_to_rows(records_by_symbol[symbol])
            final_path = package_root / relative_path
            _write_parquet_records(final_path, rows, schema_kind="constituent")
            sha256 = file_sha256(final_path)
            opens = [int(r["open_time_ms"]) for r in records_by_symbol[symbol]]
            gap_report = compute_gap_report(records_by_symbol[symbol])
            constituent_parts.append({
                "canonical_symbol": symbol,
                "broker_symbol": str(DXY_SYMBOL_MAP[symbol]),
                "partition_relative_path": relative_path,
                "sha256": sha256,
                "canonical_content_sha256": canonical_constituent_hash(records_by_symbol[symbol]),
                "record_count": len(records_by_symbol[symbol]),
                "first_open_ms": opens[0],
                "last_open_ms": opens[-1],
                "missing_window_count": gap_report["missing_window_count"],
                "gap_runs": gap_report["gap_runs"],
            })

        dxy_parquet_rows = tuple(
            {
                "available_at_ms": int(row["available_at_ms"]),
                "available_at": iso_z(int(row["available_at_ms"])),
                "dxy": float(row["dxy"]),
                "sources": {
                    symbol: {
                        "row_identity": str(row["sources"][symbol]["row_identity"]),
                        "open_time_ms": int(row["sources"][symbol]["open_time_ms"]),
                        "open_time": iso_z(int(row["sources"][symbol]["open_time_ms"])),
                        "age_ms": int(row["sources"][symbol]["age_ms"]),
                    }
                    for symbol in DXY_CONSTITUENT_ORDER
                },
                "provenance_id": str(row["provenance_id"]),
                "row_identity": str(row["row_identity"]),
            }
            for row in dxy_rows
        )
        dxy_rows_written, dxy_sha256 = _write_parquet_records(
            package_root / DXY_PARTITION_PATH, dxy_parquet_rows, schema_kind="dxy"
        )
        if dxy_rows_written != len(dxy_parquet_rows):
            raise AcquisitionError("DXY_PARQUET_ROW_COUNT_MISMATCH")

        manifest = canonical_data({
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "package_id": package_id,
            "identity_basis": (
                "content identity: source year canonical hash + constituent "
                "and DXY canonical content hashes; no absolute local path is "
                "part of the identity"
            ),
            "classification": CLASSIFICATION,
            "label": LABEL,
            "timeframe": TIMEFRAME,
            "created_utc": _now_utc_iso(),
            "source_year_package": {
                "year_package_id": str(source_year_package_id),
                "source_canonical_sha256": str(source_year_canonical_sha256),
                "source_row_count": int(source_year_row_count),
            },
            "constituents": constituent_parts,
            "gap_reports": {
                part["canonical_symbol"]: {
                    "missing_window_count": int(part["missing_window_count"]),
                    "gap_runs": int(part["gap_runs"]),
                }
                for part in constituent_parts
            },
            "causal_dxy": {
                "partition_relative_path": DXY_PARTITION_PATH,
                "record_count": len(dxy_parquet_rows),
                "sha256": dxy_sha256,
                "canonical_content_sha256": canonical_dxy_hash(dxy_rows),
                "first_available_ms": int(dxy_rows[0]["available_at_ms"]),
                "last_available_ms": int(dxy_rows[-1]["available_at_ms"]),
            },
            "alignment_summary": alignment_summary,
            "symbol_mappings": {
                symbol: dict(resolved_mappings[symbol]) for symbol in sorted(resolved_mappings)
            },
            "provenance": {
                "implementation_commit": str(implementation_commit),
                "code_fingerprint": str(code_fingerprint),
                "retrieved_utc": retrieved_utc.isoformat().replace("+00:00", "Z"),
                "terminal_build": terminal_build,
                "acquisition_evidence": dict(acquisition_evidence),
            },
            "development_interval": {
                "start": iso_z(DEVELOPMENT_START_MS),
                "end_exclusive": iso_z(DEVELOPMENT_END_MS),
            },
            "strategy_evaluation_statement": (
                "No strategy evaluation, backtest, optimization, tuning, "
                "profitability metric, win rate, profit factor or capital "
                "projection was computed for this package."
            ),
            "holdout_accessed": False,
            "mt5_or_trading_operations": acquisition_evidence.get(
                "permitted_operations", ()
            ),
        })
        _atomic_write_json(package_root / MANIFEST_NAME, manifest)

        completion = canonical_data({
            "schema_version": "phase8d.dxy-completion.v1",
            "package_id": package_id,
            "complete": True,
            "manifest_sha256": file_sha256(package_root / MANIFEST_NAME),
            "created_utc": _now_utc_iso(),
        })
        _atomic_write_json(package_root / COMPLETION_MARKER, completion)

        _atomic_write_json(package_root / COVER_REPORT_NAME, {
            "schema_version": "phase8d.coverage-report.v1",
            "package_id": package_id,
            "constituents": [
                {
                    "canonical_symbol": part["canonical_symbol"],
                    "observed_windows": part["record_count"],
                    "theoretical_windows": 8784,
                    "first_open": iso_z(part["first_open_ms"]),
                    "last_open": iso_z(part["last_open_ms"]),
                }
                for part in constituent_parts
            ],
            "causal_dxy": {
                "accepted_rows": len(dxy_parquet_rows),
                "first_available": iso_z(int(dxy_rows[0]["available_at_ms"])),
                "last_available": iso_z(int(dxy_rows[-1]["available_at_ms"])),
            },
        })
        _atomic_write_json(package_root / GAP_REPORT_NAME, {
            "schema_version": "phase8d.gap-staleness-report.v1",
            "package_id": package_id,
            "gap_reports": manifest["gap_reports"],
            "alignment_summary": alignment_summary,
            "policy": "MISSING_WINDOWS_REMAIN_MISSING_NO_FORWARD_FILL",
        })
    except Exception:
        shutil.rmtree(package_root, ignore_errors=True)
        raise

    verified = verify_package_readonly(package_root)
    return package_root, verified


def _discover_existing_package(data_root: Path) -> Path | None:
    dxy_root = data_root / "dxy"
    if not dxy_root.is_dir():
        return None
    candidates = sorted(
        item for item in dxy_root.iterdir()
        if item.is_dir() and (item / COMPLETION_MARKER).is_file()
        and (item / MANIFEST_NAME).is_file()
    )
    if not candidates:
        return None
    if len(candidates) > 1:
        raise AcquisitionError("DXY_PACKAGE_SELECTION_AMBIGUOUS")
    return candidates[0]

