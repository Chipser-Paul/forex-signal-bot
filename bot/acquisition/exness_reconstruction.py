from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from filelock import FileLock

from bot.validation.models import canonical_data

from .exness_archive import (
    MINIMUM_RESERVE_BYTES,
    _arrow,
    _canonical_from_parquet_values,
    exness_tick_schema,
    ingest_exness_archive,
    parse_archive_identity,
    verify_exness_package,
)
from .exness_monthly import plan_2024_monthly_reconstruction
from .models import AcquisitionError, EXECUTABLE_SYMBOL
from .storage import atomic_json, file_sha256, validate_output_root


UTC = timezone.utc
WORKFLOW_VERSION = "phase8b.exness-monthly-workflow.v1"
YEAR_MANIFEST_SCHEMA_VERSION = "phase8b.exness-development-year.v1"
YEAR_COMPLETION_SCHEMA_VERSION = "phase8b.exness-development-year-completion.v1"
EXPECTED_MONTHS = tuple(range(1, 13))
_PARTIAL_PACKAGE = re.compile(
    r"^\.exness-xauusdm-(?P<year>\d{4})-(?P<month>\d{2})-[a-f0-9]{16}\.partial$"
)
PARTIAL_QUARANTINE_SCHEMA_VERSION = "phase8b.partial-quarantine.v1"
_PARTIAL_QUARANTINE_MARKER = "partial.quarantine.json"


@dataclass(frozen=True)
class MonthlyReconstructionPlan:
    year: int = 2024
    symbol: str = EXECUTABLE_SYMBOL
    months: tuple[int, ...] = EXPECTED_MONTHS
    minimum_free_bytes: int = MINIMUM_RESERVE_BYTES

    def __post_init__(self) -> None:
        if (
            self.year != 2024
            or self.symbol != EXECUTABLE_SYMBOL
            or self.months != EXPECTED_MONTHS
            or self.minimum_free_bytes < MINIMUM_RESERVE_BYTES
        ):
            raise AcquisitionError("MONTHLY_RECONSTRUCTION_PLAN_UNSAFE")


def monthly_storage_projection(
    observations: Sequence[tuple[int, int]],
    *,
    remaining_months: int,
    current_free_bytes: int,
    reserve_bytes: int = MINIMUM_RESERVE_BYTES,
) -> dict[str, object]:
    if (
        len(observations) < 2
        or remaining_months < 0
        or current_free_bytes < 0
        or reserve_bytes < MINIMUM_RESERVE_BYTES
        or any(raw <= 0 or parquet <= 0 for raw, parquet in observations)
    ):
        raise AcquisitionError("MONTHLY_STORAGE_PROJECTION_INPUT_INVALID")
    totals = [raw + parquet for raw, parquet in observations]
    raw_sizes = [raw for raw, _parquet in observations]
    lower = min(totals) * remaining_months
    baseline = sum(totals) * remaining_months // len(totals)
    upper = max(totals) * 3 * remaining_months // 2
    largest_component = max(
        max(raw for raw, _ in observations),
        max(parquet for _, parquet in observations),
    )
    temporary = largest_component * 3 // 2
    raw_download_upper = max(raw_sizes) * 3 * remaining_months // 2
    return canonical_data({
        "basis": "OBSERVED_NOVEMBER_AND_DECEMBER_ARCHIVE_PLUS_PARQUET",
        "observed_month_count": len(observations),
        "remaining_month_count": remaining_months,
        "observed_raw_bytes": raw_sizes,
        "observed_parquet_bytes": [parquet for _raw, parquet in observations],
        "remaining_months_archive_and_parquet_bytes": {
            "lower": lower,
            "baseline": baseline,
            "upper": upper,
        },
        "remaining_raw_download_upper_bytes": raw_download_upper,
        "temporary_conversion_bytes": temporary,
        "current_free_bytes": current_free_bytes,
        "required_reserve_bytes": reserve_bytes,
        "upper_plus_temporary_and_reserve_bytes": upper + temporary + reserve_bytes,
        "remaining_months_fit_upper_scenario": (
            current_free_bytes > upper + temporary + reserve_bytes
        ),
        "projection_is_not_a_forecast": True,
    })


def _read_manifest(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError("MONTHLY_PACKAGE_MANIFEST_INVALID") from exc
    if not isinstance(value, dict):
        raise AcquisitionError("MONTHLY_PACKAGE_MANIFEST_INVALID")
    return value


def _quarantined_partial_marker(root: Path) -> Mapping[str, object] | None:
    marker_path = root / _PARTIAL_QUARANTINE_MARKER
    if not marker_path.is_file():
        return None
    marker = _read_manifest(marker_path)
    parquet_relative_path = marker.get("parquet_relative_path")
    parquet_sha256 = marker.get("parquet_sha256")
    if (
        marker.get("schema_version") != PARTIAL_QUARANTINE_SCHEMA_VERSION
        or marker.get("status") != "QUARANTINED"
        or marker.get("partial_package_id") != root.name
        or not isinstance(parquet_relative_path, str)
        or not isinstance(parquet_sha256, str)
    ):
        raise AcquisitionError("QUARANTINED_PARTIAL_MARKER_INVALID")
    parquet_path = root / parquet_relative_path
    if (
        not parquet_path.is_file()
        or root.resolve() not in parquet_path.resolve().parents
        or file_sha256(parquet_path) != parquet_sha256
    ):
        raise AcquisitionError("QUARANTINED_PARTIAL_ARTIFACT_CHANGED")
    return marker


def quarantine_interrupted_partial(
    partial_root: Path,
    *,
    forensic_record: Path,
    reason_code: str,
) -> dict[str, object]:
    """Preserve an interrupted package as non-selectable forensic evidence."""
    root = Path(partial_root).resolve(strict=True)
    if _PARTIAL_PACKAGE.fullmatch(root.name) is None:
        raise AcquisitionError("PARTIAL_QUARANTINE_IDENTITY_INVALID")
    parquet_paths = sorted(root.rglob("*.parquet"))
    if len(parquet_paths) != 1:
        raise AcquisitionError("PARTIAL_QUARANTINE_PARQUET_LAYOUT_INVALID")
    forensic = Path(forensic_record).resolve(strict=True)
    if not reason_code.strip():
        raise AcquisitionError("PARTIAL_QUARANTINE_REASON_REQUIRED")
    marker = canonical_data({
        "schema_version": PARTIAL_QUARANTINE_SCHEMA_VERSION,
        "status": "QUARANTINED",
        "partial_package_id": root.name,
        "parquet_relative_path": parquet_paths[0].relative_to(root).as_posix(),
        "parquet_sha256": file_sha256(parquet_paths[0]),
        "forensic_record_sha256": file_sha256(forensic),
        "reason_code": reason_code,
    })
    marker_path = root / _PARTIAL_QUARANTINE_MARKER
    if marker_path.exists():
        if _quarantined_partial_marker(root) != marker:
            raise AcquisitionError("PARTIAL_QUARANTINE_MARKER_CONFLICT")
        return marker
    atomic_json(marker_path, marker)
    return marker


def _discover_raw(
    raw_root: Path,
    plan: MonthlyReconstructionPlan,
) -> tuple[dict[int, list[Path]], list[str]]:
    by_month: dict[int, list[Path]] = defaultdict(list)
    unexpected: list[str] = []
    for path in sorted(raw_root.iterdir(), key=lambda value: value.name.casefold()):
        if not path.is_file() or path.suffix.lower() != ".zip":
            continue
        try:
            identity = parse_archive_identity(path.name)
        except AcquisitionError:
            unexpected.append(path.name)
            continue
        if (
            identity.symbol != plan.symbol
            or identity.year != plan.year
            or identity.month not in plan.months
        ):
            unexpected.append(path.name)
            continue
        by_month[int(identity.month)].append(path)
    return by_month, unexpected


def _discover_packages(
    output_root: Path,
    plan: MonthlyReconstructionPlan,
) -> tuple[dict[int, list[tuple[Path, Mapping[str, object]]]], list[str], list[str]]:
    by_month: dict[int, list[tuple[Path, Mapping[str, object]]]] = defaultdict(list)
    conflicts: list[str] = []
    quarantined_partials: list[str] = []
    packages_root = output_root / "packages"
    if not packages_root.exists():
        return by_month, conflicts, quarantined_partials
    for root in sorted(packages_root.iterdir(), key=lambda value: value.name.casefold()):
        partial = _PARTIAL_PACKAGE.fullmatch(root.name)
        if partial and int(partial.group("year")) == plan.year:
            try:
                marker = _quarantined_partial_marker(root)
            except AcquisitionError as exc:
                conflicts.append(str(exc))
                continue
            if marker is None:
                conflicts.append(f"INTERRUPTED_PARTIAL_MONTH_{int(partial.group('month')):02d}")
            else:
                quarantined_partials.append(root.name)
            continue
        manifest_path = root / "manifest.json"
        if root.name.startswith(".") or not root.is_dir() or not manifest_path.is_file():
            continue
        preview = _read_manifest(manifest_path)
        month = preview.get("claimed_month")
        if month is None:
            continue
        try:
            month_number = int(month)
        except (TypeError, ValueError) as exc:
            raise AcquisitionError("MONTHLY_PACKAGE_MONTH_INVALID") from exc
        if month_number not in plan.months:
            conflicts.append("MONTHLY_PACKAGE_PERIOD_OUTSIDE_PLAN")
            continue
        manifest = verify_exness_package(root)
        if (
            int(manifest.get("claimed_year", 0)) != plan.year
            or manifest.get("statistics", {}).get("symbol") != plan.symbol
        ):
            conflicts.append(f"PACKAGE_IDENTITY_CONFLICT_MONTH_{month_number:02d}")
            continue
        by_month[month_number].append((root, manifest))
    return by_month, conflicts, quarantined_partials


def monthly_reconstruction_readiness(
    raw_root: Path,
    output_root: Path,
    *,
    plan: MonthlyReconstructionPlan | None = None,
    forbidden_roots: Sequence[Path] = (),
    managed_registry_roots: Mapping[int, Path] | None = None,
) -> dict[str, object]:
    selected = plan or MonthlyReconstructionPlan()
    raw = Path(raw_root).resolve(strict=True)
    output = validate_output_root(Path(output_root), forbidden_roots=forbidden_roots)
    validate_output_root(raw, forbidden_roots=forbidden_roots)
    raw_by_month, unexpected = _discover_raw(raw, selected)
    package_by_month, package_conflicts, quarantined_partials = _discover_packages(output, selected)
    free_bytes = int(shutil.disk_usage(output if output.exists() else output.parent).free)
    matrix: list[dict[str, object]] = []
    verified_roots: list[str] = []
    next_month: int | None = None
    conflict_found = bool(unexpected or package_conflicts)

    for month in selected.months:
        raw_candidates = raw_by_month.get(month, [])
        packages = package_by_month.get(month, [])
        managed_month = bool(managed_registry_roots and month in managed_registry_roots)
        reason_codes: list[str] = []
        raw_record: dict[str, object] | None = None
        package_record: dict[str, object] | None = None
        if len(raw_candidates) > 1:
            reason_codes.append("DUPLICATE_RAW_MONTH_IDENTITY")
        # A registry-managed recovery period intentionally retains superseded
        # package directories. Its registry, not directory multiplicity,
        # supplies the one selectable package.
        if not managed_month and len(packages) > 1:
            reason_codes.append("DUPLICATE_PROCESSED_MONTH_IDENTITY")
        if len(raw_candidates) == 1:
            raw_path = raw_candidates[0]
            raw_record = {
                "filename": raw_path.name,
                "size_bytes": raw_path.stat().st_size,
                "sha256": file_sha256(raw_path),
                "modified_time_utc": datetime.fromtimestamp(
                    raw_path.stat().st_mtime, tz=UTC
                ),
            }
        # A recovery-managed period has a single external authority.  It never
        # falls back to directory ordering when the registry is missing or bad.
        if managed_month:
            from .package_registry import PackageRegistryStore
            try:
                if raw_record is None:
                    raise AcquisitionError("PACKAGE_REGISTRY_RAW_EVIDENCE_MISSING")
                registry = PackageRegistryStore(managed_registry_roots[month])
                root, _record = registry.active_package(
                    output / "packages",
                    expected_dataset_key=f"exness:{selected.symbol}:{selected.year:04d}-{month:02d}",
                    expected_raw_archive_sha256=str(raw_record["sha256"]),
                )
                packages = [(root, verify_exness_package(root))]
            except AcquisitionError as exc:
                packages = []
                reason_codes.append(str(exc))
        if len(packages) == 1:
            package_root, manifest = packages[0]
            package_record = {
                "package_id": manifest["package_id"],
                "archive_sha256": manifest["archive"]["sha256"],
                "canonical_normalized_sha256": manifest[
                    "canonical_normalized_sha256"
                ],
                "row_count": manifest["statistics"]["row_count"],
                "parquet_total_bytes": manifest["parquet_total_bytes"],
            }
            verified_roots.append(str(package_root))
        if raw_record is not None and package_record is not None:
            if (
                raw_record["sha256"] != package_record["archive_sha256"]
                or raw_record["filename"]
                != packages[0][1]["archive"]["filename"]
            ):
                reason_codes.append("RAW_PROCESSED_ARCHIVE_CONFLICT")
        elif package_record is not None:
            reason_codes.append("PROCESSED_PACKAGE_WITHOUT_RAW_EVIDENCE")

        if reason_codes:
            status = "CONFLICT"
            conflict_found = True
        elif package_record is not None:
            status = "VERIFIED_PACKAGE"
        elif raw_record is not None:
            status = "RAW_READY"
            if next_month is None:
                next_month = month
        else:
            status = "MISSING"
        matrix.append({
            "month": month,
            "period": f"{selected.year:04d}-{month:02d}",
            "status": status,
            "raw": raw_record,
            "package": package_record,
            "reason_codes": reason_codes,
        })

    all_verified = all(item["status"] == "VERIFIED_PACKAGE" for item in matrix)
    if conflict_found:
        status = "CONFLICT"
    elif all_verified:
        status = "READY_FOR_YEAR_RECONSTRUCTION"
    else:
        status = "INCOMPLETE_MONTHLY_SET"
    observations = [
        (int(item["raw"]["size_bytes"]), int(item["package"]["parquet_total_bytes"]))
        for item in matrix
        if item["status"] == "VERIFIED_PACKAGE"
    ]
    storage_projection = (
        monthly_storage_projection(
            observations,
            remaining_months=sum(item["status"] != "VERIFIED_PACKAGE" for item in matrix),
            current_free_bytes=free_bytes,
            reserve_bytes=selected.minimum_free_bytes,
        )
        if len(observations) >= 2
        else None
    )
    return canonical_data({
        "schema_version": WORKFLOW_VERSION,
        "status": status,
        "symbol": selected.symbol,
        "year": selected.year,
        "months": matrix,
        "next_ingestible_month": None if conflict_found else next_month,
        "verified_package_ids": [Path(value).name for value in verified_roots],
        "unexpected_archive_count": len(unexpected),
        "unexpected_archive_names": unexpected[:20],
        "package_conflict_count": len(package_conflicts),
        "package_conflicts": package_conflicts[:20],
        "quarantined_partial_packages": quarantined_partials,
        "free_bytes": free_bytes,
        "minimum_reserve_bytes": selected.minimum_free_bytes,
        "reserve_satisfied": free_bytes > selected.minimum_free_bytes,
        "one_archive_per_invocation": True,
        "downloads_performed": False,
        "raw_overwrite_permitted": False,
        "processed_overwrite_permitted": False,
        "reconstruction_authorized": all_verified and not conflict_found,
        "storage_projection": storage_projection,
        "reconstruction_requirements": [
            "EXACTLY_ONE_VERIFIED_PACKAGE_PER_MONTH",
            "MONTHLY_ARCHIVES_ONLY_NO_ANNUAL_MIXING",
            "NO_CROSS_MONTH_ROWS_OR_OVERLAP",
            "CHRONOLOGICAL_BOUNDARY_CHECKS",
            "YEAR_LEVEL_MANIFEST_AND_CANONICAL_HASH",
            "COMPLETE_YEAR_READBACK_RECONCILIATION",
            "MANAGED_RECOVERY_PERIODS_REQUIRE_EXTERNAL_ACTIVE_PACKAGE_REGISTRY",
        ],
    })


def ingest_next_monthly_archive(
    raw_root: Path,
    output_root: Path,
    *,
    plan: MonthlyReconstructionPlan | None = None,
    maximum_output_bytes: int = 2 * 1024**3,
    forbidden_roots: Sequence[Path] = (),
    managed_registry_roots: Mapping[int, Path] | None = None,
) -> dict[str, object]:
    selected = plan or MonthlyReconstructionPlan()
    before = monthly_reconstruction_readiness(
        raw_root,
        output_root,
        plan=selected,
        forbidden_roots=forbidden_roots,
        managed_registry_roots=managed_registry_roots,
    )
    if before["status"] == "CONFLICT":
        raise AcquisitionError("MONTHLY_RECONSTRUCTION_CONFLICT")
    month = before["next_ingestible_month"]
    if month is None:
        return canonical_data({"action": "NO_ARCHIVE_INGESTED", "readiness": before})
    if not before["reserve_satisfied"]:
        raise AcquisitionError("ARCHIVE_DISK_RESERVE_WOULD_BE_BREACHED")
    row = before["months"][int(month) - 1]
    archive = Path(raw_root) / row["raw"]["filename"]
    result = ingest_exness_archive(
        archive,
        output_root,
        claimed_year=selected.year,
        claimed_month=int(month),
        minimum_free_bytes=selected.minimum_free_bytes,
        maximum_output_bytes=maximum_output_bytes,
        forbidden_roots=tuple(forbidden_roots),
    )
    after = monthly_reconstruction_readiness(
        raw_root,
        output_root,
        plan=selected,
        forbidden_roots=forbidden_roots,
        managed_registry_roots=managed_registry_roots,
    )
    return canonical_data({
        "action": "ONE_ARCHIVE_INGESTED",
        "month": month,
        "package_id": result["package_id"],
        "idempotent_existing_package": result["idempotent_existing_package"],
        "readiness": after,
    })


def _selected_monthly_packages(
    package_roots: Sequence[Path],
) -> tuple[dict[int, tuple[Path, Mapping[str, object]]], dict[str, object]]:
    roots = tuple(Path(value).resolve(strict=True) for value in package_roots)
    plan = plan_2024_monthly_reconstruction(roots)
    if not plan["reconstruction_authorized"]:
        raise AcquisitionError("YEAR_RECONSTRUCTION_MONTHLY_SET_INCOMPLETE")
    selected: dict[int, tuple[Path, Mapping[str, object]]] = {}
    for root in roots:
        manifest = verify_exness_package(root)
        month = int(manifest["claimed_month"])
        if month in selected:
            raise AcquisitionError("YEAR_RECONSTRUCTION_MONTH_IDENTITY_DUPLICATE")
        selected[month] = (root, manifest)
    if tuple(sorted(selected)) != EXPECTED_MONTHS:
        raise AcquisitionError("YEAR_RECONSTRUCTION_MONTHLY_SET_INCOMPLETE")
    return selected, plan


def _stream_year_reference_statistics(
    selected: Mapping[int, tuple[Path, Mapping[str, object]]],
) -> dict[str, object]:
    _pa, pq = _arrow()
    digest = hashlib.sha256()
    total_rows = 0
    first: datetime | None = None
    last: datetime | None = None
    previous: datetime | None = None
    spread_total = Decimal("0")
    spread_min: Decimal | None = None
    spread_max: Decimal | None = None
    monthly_counts: dict[str, int] = {}
    monthly_references: list[dict[str, object]] = []

    for month in EXPECTED_MONTHS:
        root, manifest = selected[month]
        # Hash and completion checks happen before the deep, bounded scan.
        verify_exness_package(root)
        month_rows = 0
        for partition in manifest["partitions"]:
            parquet = pq.ParquetFile(root / str(partition["relative_path"]))
            if parquet.schema_arrow != exness_tick_schema():
                raise AcquisitionError("YEAR_RECONSTRUCTION_PARQUET_SCHEMA_MISMATCH")
            for batch in parquet.iter_batches(batch_size=100_000):
                columns = batch.to_pydict()
                for index in range(batch.num_rows):
                    timestamp = columns["timestamp"][index].astimezone(UTC)
                    if timestamp.year != 2024 or timestamp.month != month:
                        raise AcquisitionError("YEAR_RECONSTRUCTION_CROSS_MONTH_ROW")
                    if previous is not None and timestamp < previous:
                        raise AcquisitionError("YEAR_RECONSTRUCTION_ORDERING_MISMATCH")
                    bid = columns["bid"][index]
                    ask = columns["ask"][index]
                    if ask < bid:
                        raise AcquisitionError("YEAR_RECONSTRUCTION_CROSSED_QUOTE")
                    payload = _canonical_from_parquet_values(
                        symbol=str(columns["symbol"][index]),
                        time_msc=int(columns["time_msc"][index]),
                        bid=bid,
                        ask=ask,
                        sequence_id=int(columns["sequence_id"][index]),
                    )
                    digest.update(payload)
                    digest.update(b"\n")
                    spread = ask - bid
                    spread_total += spread
                    spread_min = spread if spread_min is None else min(spread_min, spread)
                    spread_max = spread if spread_max is None else max(spread_max, spread)
                    first = first or timestamp
                    last = timestamp
                    previous = timestamp
                    total_rows += 1
                    month_rows += 1
        if month_rows != int(manifest["statistics"]["row_count"]):
            raise AcquisitionError("YEAR_RECONSTRUCTION_MONTH_ROW_COUNT_MISMATCH")
        period = f"2024-{month:02d}"
        monthly_counts[period] = month_rows
        monthly_references.append({
            "period": period,
            "package_id": manifest["package_id"],
            "raw_archive_sha256": manifest["archive"]["sha256"],
            "manifest_sha256": file_sha256(root / "manifest.json"),
            "completion_sha256": file_sha256(root / "package.complete.json"),
            "parquet_partitions": [
                {"relative_path": item["relative_path"], "sha256": item["sha256"]}
                for item in manifest["partitions"]
            ],
            "logical_canonical_sha256": manifest["canonical_normalized_sha256"],
            "row_count": month_rows,
            "first_timestamp": manifest["statistics"]["first_timestamp"],
            "last_timestamp": manifest["statistics"]["last_timestamp"],
            "exact_duplicate_rows": manifest["statistics"]["exact_duplicate_rows"],
            "duplicate_timestamps_different_prices": manifest["statistics"][
                "duplicate_timestamps_different_prices"
            ],
            "gaps": manifest["statistics"]["gaps"],
        })

    if total_rows <= 0 or first is None or last is None or spread_min is None or spread_max is None:
        raise AcquisitionError("YEAR_RECONSTRUCTION_EMPTY")
    return canonical_data({
        "row_count": total_rows,
        "first_timestamp": first,
        "last_timestamp": last,
        "canonical_normalized_sha256": digest.hexdigest(),
        "monthly_row_counts": monthly_counts,
        "monthly_references": monthly_references,
        "aggregate_integrity": {
            "exact_duplicate_rows": sum(
                int(item["exact_duplicate_rows"]) for item in monthly_references
            ),
            "duplicate_timestamps_different_prices": sum(
                int(item["duplicate_timestamps_different_prices"])
                for item in monthly_references
            ),
            "long_gap_count": sum(
                int(item["gaps"]["long_gap_count"]) for item in monthly_references
            ),
        },
        "aggregate_spread_price": {
            "observation_count": total_rows,
            "minimum": format(spread_min, "f"),
            "maximum": format(spread_max, "f"),
            "mean": format(spread_total / Decimal(total_rows), "f"),
        },
    })


def build_2024_development_year_package(
    package_roots: Sequence[Path],
    output_root: Path,
    *,
    forbidden_roots: Sequence[Path] = (),
) -> dict[str, object]:
    """Create an immutable manifest over all monthly packages without copying ticks."""
    selected, plan = _selected_monthly_packages(package_roots)
    statistics = _stream_year_reference_statistics(selected)
    package_id = (
        "exness-xauusdm-2024-development-"
        f"{statistics['canonical_normalized_sha256'][:16]}"
    )
    output = validate_output_root(Path(output_root), forbidden_roots=forbidden_roots)
    final_root = output / "year-packages" / package_id
    if final_root.exists():
        manifest = verify_2024_development_year_package(final_root, package_roots)
        return canonical_data({"package_id": package_id, "manifest": manifest, "idempotent": True})

    manifest = canonical_data({
        "schema_version": YEAR_MANIFEST_SCHEMA_VERSION,
        "classification": "DEVELOPMENT_ONLY",
        "provider": "exness",
        "symbol": EXECUTABLE_SYMBOL,
        "period": {"start_inclusive": "2024-01-01T00:00:00Z", "end_exclusive": "2025-01-01T00:00:00Z"},
        "package_id": package_id,
        "monthly_packages": statistics["monthly_references"],
        "monthly_plan": plan,
        "statistics": {key: value for key, value in statistics.items() if key != "monthly_references"},
        "annual_archive_participation": "NONE",
        "limitations": ["DEVELOPMENT_ONLY", "NO_STRATEGY_OR_PROFITABILITY_EVALUATION"],
    })
    partial_root = final_root.parent / f".{package_id}.partial"
    with FileLock(str(final_root.parent / ".development-year.lock"), timeout=30):
        if final_root.exists():
            verified = verify_2024_development_year_package(final_root, package_roots)
            return canonical_data({"package_id": package_id, "manifest": verified, "idempotent": True})
        if partial_root.exists():
            raise AcquisitionError("YEAR_RECONSTRUCTION_PARTIAL_REQUIRES_REVIEW")
        partial_root.mkdir(parents=True)
        try:
            manifest_path = partial_root / "manifest.json"
            atomic_json(manifest_path, manifest)
            completion = canonical_data({
                "schema_version": YEAR_COMPLETION_SCHEMA_VERSION,
                "status": "COMPLETE",
                "package_id": package_id,
                "manifest_relative_path": "manifest.json",
                "manifest_sha256": file_sha256(manifest_path),
            })
            atomic_json(partial_root / "package.complete.json", completion)
            os.replace(partial_root, final_root)
        except Exception:
            raise
    verified = verify_2024_development_year_package(final_root, package_roots)
    return canonical_data({"package_id": package_id, "manifest": verified, "idempotent": False})


def verify_2024_development_year_package(
    package_root: Path,
    package_roots: Sequence[Path],
) -> dict[str, object]:
    root = Path(package_root).resolve(strict=True)
    try:
        completion = _read_manifest(root / "package.complete.json")
        manifest_path = root / str(completion["manifest_relative_path"])
        manifest = _read_manifest(manifest_path)
    except (KeyError, OSError, ValueError) as exc:
        raise AcquisitionError("YEAR_RECONSTRUCTION_COMPLETION_INVALID") from exc
    if (
        completion.get("schema_version") != YEAR_COMPLETION_SCHEMA_VERSION
        or completion.get("status") != "COMPLETE"
        or completion.get("package_id") != root.name
        or completion.get("manifest_sha256") != file_sha256(manifest_path)
        or manifest.get("schema_version") != YEAR_MANIFEST_SCHEMA_VERSION
        or manifest.get("package_id") != root.name
        or manifest.get("classification") != "DEVELOPMENT_ONLY"
    ):
        raise AcquisitionError("YEAR_RECONSTRUCTION_IDENTITY_MISMATCH")
    selected, _plan = _selected_monthly_packages(package_roots)
    statistics = _stream_year_reference_statistics(selected)
    stored = manifest.get("statistics", {})
    if (
        stored.get("row_count") != statistics["row_count"]
        or stored.get("first_timestamp") != statistics["first_timestamp"]
        or stored.get("last_timestamp") != statistics["last_timestamp"]
        or stored.get("canonical_normalized_sha256")
        != statistics["canonical_normalized_sha256"]
        or manifest.get("monthly_packages") != statistics["monthly_references"]
    ):
        raise AcquisitionError("YEAR_RECONSTRUCTION_DEEP_RECONCILIATION_FAILED")
    return manifest
