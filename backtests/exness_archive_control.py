from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from bot.acquisition.exness_archive import (
    MINIMUM_RESERVE_BYTES,
    ingest_exness_archive,
    inspect_exness_archive,
    verify_exness_package,
)
from bot.acquisition.models import AcquisitionError
from bot.validation.models import canonical_data


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = Path(r"C:\Users\chips\forex-signal-bot-data\phase8\exness-tick-history\raw")
DEFAULT_OUTPUT_ROOT = Path(r"C:\Users\chips\forex-signal-bot-data\phase8\exness-tick-history\processed")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline Exness archive ingestion control")
    parser.add_argument("command", choices=("inspect", "ingest", "verify"))
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--minimum-free-gb", type=float, default=15.0)
    parser.add_argument("--maximum-output-gb", type=float, default=5.0)
    return parser


def discover_archive(raw_root: Path, explicit: Path | None = None) -> Path:
    root = Path(raw_root).resolve(strict=True)
    if explicit is not None:
        candidate = Path(explicit).resolve(strict=True)
        if candidate.parent != root or not candidate.is_file():
            raise AcquisitionError("explicit archive must be an immediate raw-directory file")
        return candidate
    candidates = tuple(sorted(
        path for path in root.iterdir()
        if path.is_file() and path.suffix.lower() == ".zip" and "2024" in path.name
    ))
    if len(candidates) != 1:
        raise AcquisitionError("exactly one unclassified 2024 ZIP archive is required")
    return candidates[0]


def _print(status: str, **details: object) -> int:
    print(json.dumps(canonical_data({"status": status, **details}), sort_keys=True, separators=(",", ":")))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify":
            if args.package_root is None:
                raise AcquisitionError("verify requires --package-root")
            manifest = verify_exness_package(args.package_root, deep=True)
            return _print(
                "EXNESS_PACKAGE_VERIFIED",
                package_id=manifest["package_id"],
                classification=manifest["classification"],
                row_count=manifest["statistics"]["row_count"],
                canonical_normalized_sha256=manifest["canonical_normalized_sha256"],
            )
        archive = discover_archive(args.raw_root, args.archive)
        if args.command == "inspect":
            inspection = inspect_exness_archive(archive)
            return _print(
                "EXNESS_ARCHIVE_SAFE",
                filename=inspection.filename,
                size_bytes=inspection.size_bytes,
                sha256=inspection.sha256,
                archive_type=inspection.archive_type,
                member_count=len(inspection.members),
                total_uncompressed_bytes=inspection.total_uncompressed_bytes,
                maximum_compression_ratio=inspection.maximum_compression_ratio,
            )
        if args.minimum_free_gb < 15:
            raise AcquisitionError("minimum free-space reserve cannot be below 15 GiB")
        result = ingest_exness_archive(
            archive,
            args.output_root,
            claimed_year=2024,
            minimum_free_bytes=max(int(args.minimum_free_gb * 1024**3), MINIMUM_RESERVE_BYTES),
            maximum_output_bytes=int(args.maximum_output_gb * 1024**3),
            forbidden_roots=(REPO_ROOT,),
        )
        return _print(
            "EXNESS_ARCHIVE_INGESTED",
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
        _print("EXNESS_ARCHIVE_BLOCKED", reason_code=str(exc))
        return 2
    except (FileNotFoundError, NotADirectoryError, OSError, ValueError):
        _print("EXNESS_ARCHIVE_BLOCKED", reason_code="SANITIZED_VALIDATION_FAILURE")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
