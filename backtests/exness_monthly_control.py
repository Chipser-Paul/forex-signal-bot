from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from bot.acquisition.exness_archive import (
    MINIMUM_RESERVE_BYTES,
    ingest_exness_archive,
    inspect_exness_archive,
    parse_archive_identity,
)
from bot.acquisition.exness_monthly import (
    compare_annual_monthly_full_month,
    compare_annual_monthly_overlap,
    plan_2024_monthly_reconstruction,
)
from bot.acquisition.exness_reconstruction import (
    ingest_next_monthly_archive,
    monthly_reconstruction_readiness,
)
from bot.acquisition.models import AcquisitionError, EXECUTABLE_SYMBOL
from bot.validation.models import canonical_data


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = Path(
    r"C:\Users\chips\forex-signal-bot-data\phase8\exness-tick-history\raw\monthly\2024"
)
DEFAULT_OUTPUT_ROOT = Path(
    r"C:\Users\chips\forex-signal-bot-data\phase8\exness-tick-history\processed"
)


def discover_monthly_archive(
    raw_root: Path,
    *,
    year: int,
    month: int,
    explicit: Path | None = None,
) -> Path:
    if year != 2024 or month not in range(1, 13):
        raise AcquisitionError("MONTHLY_ARCHIVE_DECLARED_PERIOD_UNSUPPORTED")
    root = Path(raw_root).resolve(strict=True)
    if explicit is not None:
        candidate = Path(explicit).resolve(strict=True)
        if candidate.parent != root or not candidate.is_file():
            raise AcquisitionError("explicit monthly archive must be an immediate raw-directory file")
        candidates = (candidate,)
    else:
        candidates = []
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.suffix.lower() != ".zip":
                continue
            try:
                identity = parse_archive_identity(path.name)
            except AcquisitionError:
                continue
            if identity.symbol == EXECUTABLE_SYMBOL and identity.year == year and identity.month == month:
                candidates.append(path)
        candidates = tuple(candidates)
    if len(candidates) != 1:
        raise AcquisitionError("EXACTLY_ONE_DECLARED_MONTHLY_ARCHIVE_REQUIRED")
    identity = parse_archive_identity(candidates[0].name)
    if identity.symbol != EXECUTABLE_SYMBOL or identity.year != year or identity.month != month:
        raise AcquisitionError("MONTHLY_ARCHIVE_IDENTITY_MISMATCH")
    return candidates[0]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline Exness monthly archive continuity control")
    parser.add_argument(
        "command",
        choices=(
            "inspect",
            "ingest",
            "compare",
            "compare-month",
            "plan",
            "batch-status",
            "batch-next",
        ),
    )
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--month", type=int)
    parser.add_argument("--annual-package", type=Path)
    parser.add_argument("--monthly-package", type=Path)
    parser.add_argument("--package", action="append", type=Path, default=[])
    parser.add_argument("--minimum-free-gb", type=float, default=15.0)
    parser.add_argument("--maximum-output-gb", type=float, default=2.0)
    return parser


def _print(status: str, **details: object) -> int:
    print(json.dumps(canonical_data({"status": status, **details}), sort_keys=True, separators=(",", ":")))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command in {"batch-status", "batch-next"}:
            if args.minimum_free_gb < 15:
                raise AcquisitionError("minimum free-space reserve cannot be below 15 GiB")
            if args.command == "batch-status":
                result = monthly_reconstruction_readiness(
                    args.raw_root,
                    args.output_root,
                    forbidden_roots=(REPO_ROOT,),
                )
            else:
                result = ingest_next_monthly_archive(
                    args.raw_root,
                    args.output_root,
                    maximum_output_bytes=int(args.maximum_output_gb * 1024**3),
                    forbidden_roots=(REPO_ROOT,),
                )
            workflow_status = str(
                result.get("status", result.get("readiness", {}).get("status"))
            )
            if workflow_status == "None":
                raise AcquisitionError("MONTHLY_BATCH_STATUS_MISSING")
            details = {key: value for key, value in result.items() if key != "status"}
            return _print(
                workflow_status,
                command_status="EXNESS_MONTHLY_BATCH_REVIEWED",
                **details,
            )
        if args.command in {"compare", "compare-month"}:
            if args.annual_package is None or args.monthly_package is None:
                raise AcquisitionError("compare requires annual and monthly package roots")
            comparator = (
                compare_annual_monthly_full_month
                if args.command == "compare-month"
                else compare_annual_monthly_overlap
            )
            result = comparator(args.annual_package, args.monthly_package)
            return _print("EXNESS_MONTHLY_OVERLAP_COMPARED", **result)
        if args.command == "plan":
            result = plan_2024_monthly_reconstruction(args.package)
            return _print("EXNESS_MONTHLY_RECONSTRUCTION_PLANNED", **result)

        if args.month is None:
            raise AcquisitionError("DECLARED_MONTH_REQUIRED")
        archive = discover_monthly_archive(
            args.raw_root,
            year=args.year,
            month=args.month,
            explicit=args.archive,
        )
        if args.command == "inspect":
            inspection = inspect_exness_archive(archive)
            return _print(
                "EXNESS_MONTHLY_ARCHIVE_SAFE",
                filename=inspection.filename,
                size_bytes=inspection.size_bytes,
                sha256=inspection.sha256,
                member_count=len(inspection.members),
                total_uncompressed_bytes=inspection.total_uncompressed_bytes,
                maximum_compression_ratio=inspection.maximum_compression_ratio,
            )
        if args.minimum_free_gb < 15:
            raise AcquisitionError("minimum free-space reserve cannot be below 15 GiB")
        result = ingest_exness_archive(
            archive,
            args.output_root,
            claimed_year=args.year,
            claimed_month=args.month,
            minimum_free_bytes=max(int(args.minimum_free_gb * 1024**3), MINIMUM_RESERVE_BYTES),
            maximum_output_bytes=int(args.maximum_output_gb * 1024**3),
            forbidden_roots=(REPO_ROOT,),
        )
        return _print(
            "EXNESS_MONTHLY_ARCHIVE_INGESTED",
            package_id=result["package_id"],
            classification=result["classification"],
            row_count=result["statistics"]["row_count"],
            first_timestamp=result["statistics"]["first_timestamp"],
            last_timestamp=result["statistics"]["last_timestamp"],
            canonical_normalized_sha256=result["canonical_normalized_sha256"],
            parquet_total_bytes=result["parquet_total_bytes"],
            idempotent_existing_package=result["idempotent_existing_package"],
            holdout_accessed=False,
            strategy_evaluated=False,
            profitability_evaluated=False,
            mt5_imported=False,
        )
    except AcquisitionError as exc:
        _print("EXNESS_MONTHLY_ARCHIVE_BLOCKED", reason_code=str(exc))
        return 2
    except (FileNotFoundError, NotADirectoryError, OSError, ValueError):
        _print("EXNESS_MONTHLY_ARCHIVE_BLOCKED", reason_code="SANITIZED_VALIDATION_FAILURE")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
