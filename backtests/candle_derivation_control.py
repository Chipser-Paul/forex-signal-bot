"""Phase 8C offline CLI control for deriving causal development candles.

Streams the verified 2024 XAUUSDm monthly tick packages (39,715,935 rows)
and derives M5/M15/H1/H4/D1/W1 bid/ask candles without ever holding the
complete year in memory.

The run performs, in order:
  1. Deep verification of the year package manifest and every monthly package.
  2. Preflight: free-space reserve (>= 15 GiB) and non-existent output target.
  3. Streaming aggregation per timeframe (closed-open UTC windows,
     Monday-based W1, no forward-filling, duplicates preserved, bid/ask
     separate, terminal partial window discarded).
  4. Atomic, non-overwriting Parquet publication.
  5. Full readback verification of every partition.
  6. Determinism verification: a second aggregation pass must reproduce
     the identical canonical content hash.
  7. Atomic manifest + completion marker + readiness report publication.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from bot.acquisition.models import AcquisitionError
from bot.acquisition.storage import atomic_json, validate_output_root
from bot.acquisition.exness_reconstruction import verify_2024_development_year_package
from bot.acquisition.candle_pipeline import (
    REQUIRED_TIMEFRAMES,
    _detect_gaps,
    aggregate_ticks_to_candles,
)
from bot.acquisition.candle_store import ParquetBidAskCandleStore
from bot.acquisition.candle_manifest import (
    build_derived_candle_manifest,
    verify_derived_candle_manifest,
)
from backtests.candle_derivation_readiness import build_readiness_report

logger = logging.getLogger(__name__)

MINIMUM_FREE_BYTES = 15 * 1024**3  # 15 GiB reserve
CANDLE_OUTPUT_BUDGET_BYTES = 5 * 1024**3  # 5 GiB budget for candle partitions
SYMBOL = "XAUUSDm"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "UNKNOWN"


def _select_monthly_packages(
    year_manifest: Mapping, package_root: Path
) -> list[tuple[Path, Mapping]]:
    """Resolve the monthly package directories referenced by the year manifest.

    The ordering and set of packages is taken exclusively from the verified
    year manifest (which already lists monthly packages in chronological
    month order, including the recovery-variant package identities).
    """
    from bot.acquisition.exness_archive import verify_exness_package

    ordered: list[tuple[Path, Mapping]] = []
    previous_period: str | None = None
    for reference in year_manifest["monthly_packages"]:
        period = str(reference["period"])
        if previous_period is not None and period <= previous_period:
            raise AcquisitionError(
                f"YEAR_REFERENCE_ORDER_INVALID: {period} after {previous_period}"
            )
        previous_period = period
        package_id = str(reference["package_id"])
        package_dir = package_root / package_id
        if not package_dir.is_dir():
            raise AcquisitionError(
                f"YEAR_REFERENCE_MISSING: monthly package {package_id} is absent"
            )
        try:
            manifest = verify_exness_package(package_dir)
        except AcquisitionError as exc:
            raise AcquisitionError(
                f"YEAR_REFERENCE_INVALID: monthly package {package_id} failed "
                f"verification: {exc}"
            ) from exc
        if str(manifest.get("package_id")) != package_id:
            raise AcquisitionError(
                f"YEAR_REFERENCE_IDENTITY_MISMATCH: {package_id}"
            )
        ordered.append((package_dir, manifest))
    if not ordered:
        raise AcquisitionError("YEAR_REFERENCE_EMPTY")
    return ordered


def derive_candles(
    year_manifest_path: Path,
    package_root: Path,
    output_root: Path,
    timeframes: Sequence[str],
) -> Path:
    """Run the offline candle derivation pipeline. Returns the output dir."""
    unsupported = [tf for tf in timeframes if tf not in REQUIRED_TIMEFRAMES]
    if unsupported:
        raise AcquisitionError(f"Unsupported timeframes requested: {unsupported}")
    if len(set(timeframes)) != len(timeframes):
        raise AcquisitionError("Duplicate timeframes requested")

    # 1. Verify year package (deep reconciliation against monthly packages).
    #    The verifier expects the individual monthly package directories
    #    referenced by the year manifest, in manifest (chronological) order.
    logger.info("Verifying year package manifest and all monthly source packages...")
    year_root = year_manifest_path.resolve(strict=True).parent
    raw_manifest = json.loads(year_manifest_path.read_text(encoding="utf-8"))
    monthly_dirs = [
        package_root / str(reference["package_id"])
        for reference in raw_manifest.get("monthly_packages", [])
    ]
    if not monthly_dirs:
        raise AcquisitionError("YEAR_MANIFEST_HAS_NO_MONTHLY_PACKAGES")
    year_manifest = verify_2024_development_year_package(year_root, monthly_dirs)

    year_package_id = str(year_manifest["package_id"])
    stats = year_manifest["statistics"]
    source_canonical_sha256 = str(stats["canonical_normalized_sha256"])
    source_row_count = int(stats["row_count"])
    source_first_tick = str(stats["first_timestamp"])
    source_last_tick = str(stats["last_timestamp"])
    logger.info(
        "Year package %s verified: %d ticks, %s .. %s",
        year_package_id,
        source_row_count,
        source_first_tick,
        source_last_tick,
    )

    monthly_packages = _select_monthly_packages(year_manifest, package_root)
    monthly_package_ids = [
        str(manifest["package_id"]) for _, manifest in monthly_packages
    ]

    # 2. Output directory preparation (atomic, non-overwriting).
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    derived_output_dir = output_root / f"derived-candles-2024-v1-{timestamp}"
    derived_output_dir = validate_output_root(derived_output_dir, forbidden_roots=())
    derived_output_dir.mkdir(parents=True, exist_ok=False)
    logger.info("Derived output directory: %s", derived_output_dir)

    # 3. Storage with 15 GiB disk reserve.
    store = ParquetBidAskCandleStore(
        derived_output_dir / "candles",
        maximum_output_bytes=CANDLE_OUTPUT_BUDGET_BYTES,
        minimum_free_bytes=MINIMUM_FREE_BYTES,
    )

    start_dt = datetime.fromisoformat(source_first_tick.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(source_last_tick.replace("Z", "+00:00"))
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    timeframe_summaries = []
    derived_row_counts: dict[str, int] = {}
    derived_gap_counts: dict[str, int] = {}
    derived_missing_windows: dict[str, int] = {}

    # 4. Derivation loop.
    for tf in timeframes:
        logger.info("Aggregating %s candles (streaming pass 1)...", tf)
        records = aggregate_ticks_to_candles(
            monthly_packages, tf, year_package_id=year_package_id
        )
        summary = store.write(
            f"{SYMBOL}/{tf}/year=2024/part-00000.parquet",
            records,
            partition_id=f"xauusdm-{tf.lower()}-2024",
            timeframe=tf,
        )

        # 5. Full readback verification.
        logger.info("Verifying readback for %s (%d candles)...", tf, summary.record_count)
        verified = store.verify(summary.relative_path)
        if verified.sha256 != summary.sha256:
            raise AcquisitionError(f"{tf}: physical SHA-256 changed after write")
        if verified.canonical_content_sha256 != summary.canonical_content_sha256:
            raise AcquisitionError(f"{tf}: canonical content hash changed after write")

        # 6. Determinism: second streaming pass must reproduce the same content.
        logger.info("Determinism pass for %s (streaming pass 2)...", tf)
        deterministic_digest = ParquetBidAskCandleStore.canonical_digest_of_stream(
            aggregate_ticks_to_candles(
                monthly_packages, tf, year_package_id=year_package_id
            )
        )
        if deterministic_digest != summary.canonical_content_sha256:
            raise AcquisitionError(
                f"{tf}: deterministic re-derivation produced a different "
                f"canonical content hash"
            )

        # Gap accounting: re-derive open times from the verified readback
        # (rows are already validated and ordered) instead of a third pass.
        from bot.acquisition.candle_store import read_candle_records

        open_times_ms = [
            int(row["open_time_ms"])
            for row in read_candle_records(store._safe_path(summary.relative_path))
        ]
        gaps = _detect_gaps(tf, open_times_ms, start_dt, end_dt)
        missing_windows = sum(gap.missing_window_count for gap in gaps)

        gap_info = {
            "gap_count": len(gaps),
            "missing_window_count": missing_windows,
            "partial_initial_window": False,
            "partial_terminal_window": True,
        }
        timeframe_summaries.append((summary, gap_info))
        derived_row_counts[tf] = summary.record_count
        derived_gap_counts[tf] = gap_info["gap_count"]
        derived_missing_windows[tf] = missing_windows
        logger.info(
            "Completed %s: %d candles, %d gap runs, %d missing windows.",
            tf,
            summary.record_count,
            gap_info["gap_count"],
            missing_windows,
        )

    # 7. Manifest + completion marker (atomic, non-overwriting).
    logger.info("Building derived-data manifest...")
    manifest_dict = build_derived_candle_manifest(
        derived_output_dir,
        year_package_id=year_package_id,
        source_canonical_sha256=source_canonical_sha256,
        source_row_count=source_row_count,
        git_commit=_git_commit(),
        timeframe_summaries=timeframe_summaries,
        monthly_package_ids=monthly_package_ids,
    )
    verified_manifest = verify_derived_candle_manifest(derived_output_dir)
    if verified_manifest != manifest_dict:
        raise AcquisitionError("Derived-candle manifest failed round-trip verification")
    derived_manifest_sha256 = str(
        json.loads((derived_output_dir / "pipeline.complete.json").read_text("utf-8"))[
            "manifest_sha256"
        ]
    )

    # 8. Readiness report (atomic, non-overwriting).
    report_dict = build_readiness_report(
        year_package_id=year_package_id,
        source_row_count=source_row_count,
        source_canonical_sha256=source_canonical_sha256,
        source_first_tick=source_first_tick,
        source_last_tick=source_last_tick,
        derived_timeframes=list(timeframes),
        derived_row_counts=derived_row_counts,
        derived_gap_counts=derived_gap_counts,
        derived_missing_window_counts=derived_missing_windows,
        derived_output_dir=derived_output_dir.resolve().as_posix(),
        derived_manifest_sha256=derived_manifest_sha256,
        monthly_package_ids=monthly_package_ids,
        git_commit=manifest_dict["git_commit"],
    )
    report_path = derived_output_dir / "readiness_report.json"
    atomic_json(report_path, report_dict)

    logger.info("Success. Derived dataset written to: %s", derived_output_dir)
    logger.info("Readiness report written to: %s", report_path)
    return derived_output_dir


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    logging.Formatter.converter = time.gmtime

    parser = argparse.ArgumentParser(
        description="Derive causal 2024 development candles from verified ticks."
    )
    parser.add_argument("command", choices=["derive"])
    parser.add_argument("--year-manifest", required=True, type=Path,
                        help="Path to the year package manifest.json")
    parser.add_argument("--package-root", required=True, type=Path,
                        help="Directory containing the monthly package folders")
    parser.add_argument("--output-root", required=True, type=Path,
                        help="Directory outside Git for derived candle output")
    parser.add_argument("--timeframe", required=True, type=str,
                        help="Comma-separated timeframes (M5,M15,H1,H4,D1,W1)")

    args = parser.parse_args()
    timeframes = [tf.strip().upper() for tf in args.timeframe.split(",") if tf.strip()]

    try:
        derive_candles(
            args.year_manifest,
            args.package_root,
            args.output_root,
            timeframes,
        )
    except AcquisitionError as exc:
        logger.error("Derivation failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
