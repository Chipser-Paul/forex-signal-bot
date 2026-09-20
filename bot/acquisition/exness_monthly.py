from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from itertools import groupby, zip_longest
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

from bot.validation.models import canonical_data

from .exness_archive import _arrow, _parse_manifest_timestamp, verify_exness_package
from .models import AcquisitionError, EXECUTABLE_SYMBOL


UTC = timezone.utc
SIGNED_TWO_GIB_BYTES = 2 * 1024**3
NEAR_BOUNDARY_BYTES = 1024**2
MINIMUM_STRONG_OVERLAP_ROWS = 1_000
OVERLAP_POLICY_VERSION = "phase8b.exness-overlap.v1"
FULL_MONTH_POLICY_VERSION = "phase8b.exness-full-month-comparison.v1"


@dataclass(frozen=True, order=True)
class ComparableQuote:
    time_msc: int
    bid: Decimal
    ask: Decimal

    @property
    def timestamp(self) -> datetime:
        return datetime.fromtimestamp(self.time_msc / 1000, tz=UTC)


def _period_partition(manifest: Mapping[str, object], period: str) -> Mapping[str, object]:
    def item_period(item: Mapping[str, object]) -> object:
        for key in ("period", "partition", "month"):
            if key in item:
                return item[key]
        return None

    matches = [item for item in manifest["partitions"] if item_period(item) == period]
    if len(matches) != 1:
        raise AcquisitionError("EXNESS_PACKAGE_PERIOD_PARTITION_AMBIGUOUS")
    return matches[0]


def _iter_quotes(
    package_root: Path,
    partition: Mapping[str, object],
    *,
    start_msc: int,
    end_msc: int,
) -> Iterator[ComparableQuote]:
    _pa, pq = _arrow()
    path = Path(package_root) / str(partition["relative_path"])
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(columns=["time_msc", "bid", "ask"], batch_size=100_000):
        columns = batch.to_pydict()
        for index, time_msc in enumerate(columns["time_msc"]):
            value = int(time_msc)
            if value < start_msc:
                continue
            if value > end_msc:
                return
            yield ComparableQuote(value, columns["bid"][index], columns["ask"][index])


def _quote_payload(quote: ComparableQuote) -> bytes:
    return (
        f"{quote.time_msc},{format(quote.bid, 'f')},{format(quote.ask, 'f')}\n"
    ).encode("ascii")


def _hash_quotes(quotes: Iterable[ComparableQuote]) -> str:
    digest = hashlib.sha256()
    for quote in quotes:
        digest.update(_quote_payload(quote))
    return digest.hexdigest()


def _quote_record(value: ComparableQuote | None) -> dict[str, object] | None:
    if value is None:
        return None
    return canonical_data({
        "time_msc": value.time_msc,
        "timestamp": value.timestamp,
        "bid": format(value.bid, "f"),
        "ask": format(value.ask, "f"),
    })


def _timestamp_groups(
    quotes: Iterable[ComparableQuote],
) -> Iterator[tuple[int, tuple[ComparableQuote, ...]]]:
    for time_msc, rows in groupby(quotes, key=lambda quote: quote.time_msc):
        yield time_msc, tuple(rows)


def _stream_overlap_metrics(
    annual_quotes: Iterable[ComparableQuote],
    monthly_quotes: Iterable[ComparableQuote],
) -> dict[str, object]:
    sentinel = object()
    annual_groups = _timestamp_groups(annual_quotes)
    monthly_groups = _timestamp_groups(monthly_quotes)
    annual_item = next(annual_groups, sentinel)
    monthly_item = next(monthly_groups, sentinel)
    annual_count = monthly_count = exact_matches = common_timestamps = 0
    annual_only = monthly_only = conflict_timestamps = sequence_differences = 0
    shared_timestamp_sequence_differences = 0
    annual_duplicates = monthly_duplicates = 0
    annual_multi_price_timestamps = monthly_multi_price_timestamps = 0
    source_order_identical = same_multiset = True
    annual_days: Counter[str] = Counter()
    monthly_days: Counter[str] = Counter()
    annual_source_hash = hashlib.sha256()
    monthly_source_hash = hashlib.sha256()
    annual_normalized_hash = hashlib.sha256()
    monthly_normalized_hash = hashlib.sha256()
    first_divergence: dict[str, object] | None = None
    last_divergence: dict[str, object] | None = None

    def consume(
        annual_group: tuple[ComparableQuote, ...],
        monthly_group: tuple[ComparableQuote, ...],
    ) -> None:
        nonlocal annual_count, monthly_count, exact_matches, common_timestamps
        nonlocal annual_only, monthly_only, conflict_timestamps, sequence_differences
        nonlocal shared_timestamp_sequence_differences
        nonlocal annual_duplicates, monthly_duplicates
        nonlocal annual_multi_price_timestamps, monthly_multi_price_timestamps
        nonlocal source_order_identical, same_multiset, first_divergence, last_divergence

        annual_count += len(annual_group)
        monthly_count += len(monthly_group)
        for quote in annual_group:
            annual_days[quote.timestamp.date().isoformat()] += 1
            annual_source_hash.update(_quote_payload(quote))
        for quote in monthly_group:
            monthly_days[quote.timestamp.date().isoformat()] += 1
            monthly_source_hash.update(_quote_payload(quote))
        for quote in sorted(annual_group):
            annual_normalized_hash.update(_quote_payload(quote))
        for quote in sorted(monthly_group):
            monthly_normalized_hash.update(_quote_payload(quote))

        annual_counter = Counter(annual_group)
        monthly_counter = Counter(monthly_group)
        annual_duplicates += len(annual_group) - len(annual_counter)
        monthly_duplicates += len(monthly_group) - len(monthly_counter)
        annual_multi_price_timestamps += int(
            len({(quote.bid, quote.ask) for quote in annual_group}) > 1
        )
        monthly_multi_price_timestamps += int(
            len({(quote.bid, quote.ask) for quote in monthly_group}) > 1
        )
        exact_matches += sum((annual_counter & monthly_counter).values())
        annual_only += sum((annual_counter - monthly_counter).values())
        monthly_only += sum((monthly_counter - annual_counter).values())
        if annual_group and monthly_group:
            common_timestamps += 1
            annual_prices = {(quote.bid, quote.ask) for quote in annual_group}
            monthly_prices = {(quote.bid, quote.ask) for quote in monthly_group}
            conflict_timestamps += int(annual_prices != monthly_prices)
        if annual_counter != monthly_counter:
            same_multiset = False
        if annual_group != monthly_group:
            source_order_identical = False
            for position, (left, right) in enumerate(
                zip_longest(annual_group, monthly_group)
            ):
                if left == right:
                    continue
                sequence_differences += 1
                if annual_group and monthly_group:
                    shared_timestamp_sequence_differences += 1
                divergence = canonical_data({
                    "timestamp_position": position,
                    "annual": _quote_record(left),
                    "monthly": _quote_record(right),
                })
                first_divergence = first_divergence or divergence
                last_divergence = divergence

    while annual_item is not sentinel or monthly_item is not sentinel:
        if monthly_item is sentinel or (
            annual_item is not sentinel and annual_item[0] < monthly_item[0]
        ):
            consume(annual_item[1], ())
            annual_item = next(annual_groups, sentinel)
        elif annual_item is sentinel or monthly_item[0] < annual_item[0]:
            consume((), monthly_item[1])
            monthly_item = next(monthly_groups, sentinel)
        else:
            consume(annual_item[1], monthly_item[1])
            annual_item = next(annual_groups, sentinel)
            monthly_item = next(monthly_groups, sentinel)

    days = sorted(set(annual_days) | set(monthly_days))
    return {
        "annual_count": annual_count,
        "monthly_count": monthly_count,
        "exact_matches": exact_matches,
        "common_timestamps": common_timestamps,
        "annual_only": annual_only,
        "monthly_only": monthly_only,
        "conflict_timestamps": conflict_timestamps,
        "sequence_differences": sequence_differences,
        "shared_timestamp_sequence_differences": shared_timestamp_sequence_differences,
        "annual_exact_duplicate_rows": annual_duplicates,
        "monthly_exact_duplicate_rows": monthly_duplicates,
        "annual_duplicate_timestamps_different_prices": annual_multi_price_timestamps,
        "monthly_duplicate_timestamps_different_prices": monthly_multi_price_timestamps,
        "source_order_identical": source_order_identical,
        "same_multiset": same_multiset,
        "first_divergence": first_divergence,
        "last_divergence": last_divergence,
        "daily_differences": {
            day: {"annual": annual_days[day], "monthly": monthly_days[day]}
            for day in days
            if annual_days[day] != monthly_days[day]
        },
        "source_hashes": {
            "annual": annual_source_hash.hexdigest(),
            "monthly": monthly_source_hash.hexdigest(),
        },
        "normalized_hashes": {
            "annual": annual_normalized_hash.hexdigest(),
            "monthly": monthly_normalized_hash.hexdigest(),
        },
    }


def _manifest_month(manifest: Mapping[str, object]) -> int | None:
    value = manifest.get("claimed_month")
    return None if value is None else int(value)


def _source_order_inversions_in_period(
    manifest: Mapping[str, object],
    *,
    period: str,
) -> dict[str, object]:
    statistics = manifest.get("statistics", {})
    bounded = statistics.get("bounded_examples", {}).get("NON_MONOTONIC_TIMESTAMP", [])
    total = int(statistics.get("non_monotonic_rows", 0))
    examples = [
        item
        for item in bounded
        if str(item.get("timestamp", "")).startswith(period)
    ]
    all_examples_available = total == len(bounded)
    return canonical_data({
        "count": len(examples),
        "count_is_exact": all_examples_available,
        "global_count": total,
        "examples": examples,
    })


def _validated_annual_monthly_manifests(
    annual_package_root: Path,
    monthly_package_root: Path,
) -> tuple[Path, Path, Mapping[str, object], Mapping[str, object], int, int]:
    annual_root = Path(annual_package_root).resolve(strict=True)
    monthly_root = Path(monthly_package_root).resolve(strict=True)
    annual_manifest = verify_exness_package(annual_root)
    monthly_manifest = verify_exness_package(monthly_root)
    month = _manifest_month(monthly_manifest)
    if (
        _manifest_month(annual_manifest) is not None
        or month is None
        or annual_manifest.get("claimed_year") != monthly_manifest.get("claimed_year")
        or annual_manifest.get("statistics", {}).get("symbol") != EXECUTABLE_SYMBOL
        or monthly_manifest.get("statistics", {}).get("symbol") != EXECUTABLE_SYMBOL
    ):
        raise AcquisitionError("ANNUAL_MONTHLY_PACKAGE_IDENTITY_UNSAFE")
    return (
        annual_root,
        monthly_root,
        annual_manifest,
        monthly_manifest,
        int(monthly_manifest["claimed_year"]),
        month,
    )


def compare_annual_monthly_full_month(
    annual_package_root: Path,
    monthly_package_root: Path,
    *,
    minimum_matching_rows: int = MINIMUM_STRONG_OVERLAP_ROWS,
) -> dict[str, object]:
    if minimum_matching_rows < 1:
        raise AcquisitionError("OVERLAP_MINIMUM_ROWS_INVALID")
    (
        annual_root,
        monthly_root,
        annual_manifest,
        monthly_manifest,
        year,
        month,
    ) = _validated_annual_monthly_manifests(annual_package_root, monthly_package_root)
    period = f"{year:04d}-{month:02d}"
    annual_partition = _period_partition(annual_manifest, period)
    monthly_partition = _period_partition(monthly_manifest, period)
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year + int(month == 12), 1 if month == 12 else month + 1, 1, tzinfo=UTC)
    metrics = _stream_overlap_metrics(
        _iter_quotes(
            annual_root,
            annual_partition,
            start_msc=int(start.timestamp() * 1000),
            end_msc=int(end.timestamp() * 1000) - 1,
        ),
        _iter_quotes(
            monthly_root,
            monthly_partition,
            start_msc=int(start.timestamp() * 1000),
            end_msc=int(end.timestamp() * 1000) - 1,
        ),
    )
    annual_inversions = _source_order_inversions_in_period(
        annual_manifest, period=period
    )
    monthly_inversions = _source_order_inversions_in_period(
        monthly_manifest, period=period
    )
    enough = metrics["exact_matches"] >= minimum_matching_rows
    has_material_difference = bool(
        metrics["annual_only"]
        or metrics["monthly_only"]
        or metrics["conflict_timestamps"]
    )
    if not enough:
        classification = "INSUFFICIENT_OVERLAP"
    elif has_material_difference:
        classification = "MATERIAL_FEED_DIFFERENCES"
    elif (
        metrics["source_order_identical"]
        and annual_inversions["count"] == monthly_inversions["count"]
    ):
        classification = "IDENTICAL"
    elif metrics["same_multiset"]:
        classification = "EQUIVALENT_AFTER_ORDER_NORMALIZATION"
    else:
        classification = "MATERIAL_FEED_DIFFERENCES"

    annual_is_exact_subset = bool(
        metrics["annual_count"] > 0
        and metrics["annual_only"] == 0
        and metrics["conflict_timestamps"] == 0
        and metrics["exact_matches"] == metrics["annual_count"]
    )
    if annual_inversions["count"] and not monthly_inversions["count"]:
        ordering_conclusion = "ANNUAL_ONLY_SOURCE_ORDER_INVERSIONS; MONTHLY_SOURCE_MONOTONIC"
    elif annual_inversions["count"] == monthly_inversions["count"] == 0:
        ordering_conclusion = "NO_SOURCE_ORDER_INVERSIONS_RECORDED"
    else:
        ordering_conclusion = "SOURCE_ORDER_REQUIRES_REVIEW"

    return canonical_data({
        "schema_version": FULL_MONTH_POLICY_VERSION,
        "classification": classification,
        "period": period,
        "interval": {"start_inclusive": start, "end_exclusive": end},
        "minimum_matching_rows": minimum_matching_rows,
        "mismatch_policy": "ZERO_TOLERANCE_ANY_SOURCE_ONLY_OR_PRICE_CONFLICT_IS_MATERIAL",
        "annual_row_count": metrics["annual_count"],
        "monthly_row_count": metrics["monthly_count"],
        "matching_timestamp_bid_ask_multiplicities": metrics["exact_matches"],
        "exact_matches": metrics["exact_matches"],
        "annual_only_ticks": metrics["annual_only"],
        "monthly_only_ticks": metrics["monthly_only"],
        "conflicting_price_timestamps": metrics["conflict_timestamps"],
        "duplicate_differences": {
            "annual_exact_duplicate_rows": metrics["annual_exact_duplicate_rows"],
            "monthly_exact_duplicate_rows": metrics["monthly_exact_duplicate_rows"],
            "annual_duplicate_timestamps_different_prices": metrics[
                "annual_duplicate_timestamps_different_prices"
            ],
            "monthly_duplicate_timestamps_different_prices": metrics[
                "monthly_duplicate_timestamps_different_prices"
            ],
        },
        "daily_row_count_differences": metrics["daily_differences"],
        "record_differences": metrics["sequence_differences"],
        "shared_timestamp_order_differences": metrics[
            "shared_timestamp_sequence_differences"
        ],
        "first_divergence": metrics["first_divergence"],
        "last_divergence": metrics["last_divergence"],
        "canonical_multiset_hashes": metrics["normalized_hashes"],
        "normalized_order_hashes": metrics["source_hashes"],
        "annual_source_order_inversions": annual_inversions,
        "monthly_source_order_inversions": monthly_inversions,
        "ordering_conclusion": ordering_conclusion,
        "annual_is_exact_subset_of_monthly": annual_is_exact_subset,
        "common_records_compatible": annual_is_exact_subset,
        "monthly_archive_classification": monthly_manifest["classification"],
        "monthly_archive_validated": True,
        "annual_archive_quarantined": True,
    })


def classify_truncation_hypothesis(
    *,
    overlap_classification: str,
    matched_overlap_rows: int,
    continuation_rows: int,
    annual_member_distance_below_boundary_bytes: int,
) -> str:
    matching = overlap_classification in {"IDENTICAL", "EQUIVALENT_AFTER_ORDER_NORMALIZATION"}
    near_boundary = 0 <= annual_member_distance_below_boundary_bytes <= NEAR_BOUNDARY_BYTES
    if (
        matching
        and matched_overlap_rows >= MINIMUM_STRONG_OVERLAP_ROWS
        and continuation_rows > 0
        and near_boundary
    ):
        return "STRONGLY_SUPPORTED_BY_DATA"
    if overlap_classification == "MATERIAL_FEED_DIFFERENCES":
        return "NOT_SUPPORTED"
    return "POSSIBLE"


def compare_annual_monthly_overlap(
    annual_package_root: Path,
    monthly_package_root: Path,
    *,
    minimum_overlap_rows: int = MINIMUM_STRONG_OVERLAP_ROWS,
) -> dict[str, object]:
    if minimum_overlap_rows < 1:
        raise AcquisitionError("OVERLAP_MINIMUM_ROWS_INVALID")
    (
        annual_root,
        monthly_root,
        annual_manifest,
        monthly_manifest,
        year,
        month,
    ) = _validated_annual_monthly_manifests(annual_package_root, monthly_package_root)
    period = f"{year:04d}-{month:02d}"
    annual_partition = _period_partition(annual_manifest, period)
    monthly_partition = _period_partition(monthly_manifest, period)
    overlap_start = max(
        _parse_manifest_timestamp(annual_partition["first_timestamp"]),
        _parse_manifest_timestamp(monthly_partition["first_timestamp"]),
    )
    overlap_end = min(
        _parse_manifest_timestamp(annual_partition["last_timestamp"]),
        _parse_manifest_timestamp(monthly_partition["last_timestamp"]),
    )
    if overlap_start > overlap_end:
        return canonical_data({
            "schema_version": OVERLAP_POLICY_VERSION,
            "classification": "INSUFFICIENT_OVERLAP",
            "period": period,
            "overlap_start": None,
            "overlap_end": None,
            "minimum_overlap_rows": minimum_overlap_rows,
            "mismatch_policy": "ZERO_TOLERANCE",
        })

    start_msc = int(overlap_start.timestamp() * 1000)
    end_msc = int(overlap_end.timestamp() * 1000)
    metrics = _stream_overlap_metrics(
        _iter_quotes(
            annual_root,
            annual_partition,
            start_msc=start_msc,
            end_msc=end_msc,
        ),
        _iter_quotes(
            monthly_root,
            monthly_partition,
            start_msc=start_msc,
            end_msc=end_msc,
        ),
    )
    enough = min(metrics["annual_count"], metrics["monthly_count"]) >= minimum_overlap_rows
    if not enough:
        classification = "INSUFFICIENT_OVERLAP"
    elif metrics["source_order_identical"]:
        classification = "IDENTICAL"
    elif metrics["same_multiset"]:
        classification = "EQUIVALENT_AFTER_ORDER_NORMALIZATION"
    else:
        classification = "MATERIAL_FEED_DIFFERENCES"
    monthly_all_days = set(monthly_manifest["statistics"]["trading_day_counts"])
    annual_all_days = set(annual_manifest["statistics"]["trading_day_counts"])
    repaired_dates = sorted(monthly_all_days - annual_all_days)
    repaired_weekdays = [value for value in repaired_dates if date.fromisoformat(value).weekday() < 5]
    recorded_annual_missing = set(annual_manifest["statistics"]["completely_missing_weekdays"])
    repaired_recorded_missing = sorted(recorded_annual_missing & monthly_all_days)
    annual_last = _parse_manifest_timestamp(annual_partition["last_timestamp"])
    continuation_rows = sum(
        int(count)
        for day, count in monthly_manifest["statistics"]["trading_day_counts"].items()
        if date.fromisoformat(day) > annual_last.date()
    )
    annual_uncompressed = int(annual_manifest["archive"]["total_uncompressed_bytes"])
    boundary_distance = SIGNED_TWO_GIB_BYTES - annual_uncompressed
    truncation_hypothesis = classify_truncation_hypothesis(
        overlap_classification=classification,
        matched_overlap_rows=metrics["exact_matches"],
        continuation_rows=continuation_rows,
        annual_member_distance_below_boundary_bytes=boundary_distance,
    )

    return canonical_data({
        "schema_version": OVERLAP_POLICY_VERSION,
        "classification": classification,
        "period": period,
        "overlap_start": overlap_start,
        "overlap_end": overlap_end,
        "minimum_overlap_rows": minimum_overlap_rows,
        "mismatch_policy": "ZERO_TOLERANCE_ANY_SOURCE_ONLY_OR_PRICE_CONFLICT_IS_MATERIAL",
        "annual_rows_in_overlap": metrics["annual_count"],
        "monthly_rows_in_overlap": metrics["monthly_count"],
        "timestamps_appearing_in_both": metrics["common_timestamps"],
        "exact_timestamp_bid_ask_matches": metrics["exact_matches"],
        "ticks_only_in_annual": metrics["annual_only"],
        "ticks_only_in_monthly": metrics["monthly_only"],
        "identical_timestamps_with_different_prices": metrics["conflict_timestamps"],
        "sequence_differences": metrics["sequence_differences"],
        "daily_row_count_differences": metrics["daily_differences"],
        "first_divergence": metrics["first_divergence"],
        "last_divergence": metrics["last_divergence"],
        "source_order_hashes": metrics["source_hashes"],
        "normalized_common_bound_hashes": metrics["normalized_hashes"],
        "monthly_continuation_rows_after_annual_last_date": continuation_rows,
        "monthly_last_timestamp": monthly_manifest["statistics"]["last_timestamp"],
        "annual_last_timestamp": annual_manifest["statistics"]["last_timestamp"],
        "annual_absent_dates_present_monthly": repaired_dates,
        "annual_absent_weekdays_present_monthly": repaired_weekdays,
        "recorded_annual_missing_weekdays_repaired": repaired_recorded_missing,
        "signed_two_gib_boundary_bytes": SIGNED_TWO_GIB_BYTES,
        "annual_member_distance_below_boundary_bytes": boundary_distance,
        "truncation_hypothesis": truncation_hypothesis,
        "official_size_limit_documented": False,
    })


def plan_2024_monthly_reconstruction(
    package_roots: Sequence[Path],
) -> dict[str, object]:
    manifests: dict[int, tuple[Path, Mapping[str, object]]] = {}
    for root_value in package_roots:
        root = Path(root_value).resolve(strict=True)
        manifest = verify_exness_package(root)
        month = _manifest_month(manifest)
        if month is None:
            raise AcquisitionError("AMBIGUOUS_ARCHIVE_PRECEDENCE_ANNUAL_MONTHLY_MIX")
        if int(manifest.get("claimed_year", 0)) != 2024:
            raise AcquisitionError("RECONSTRUCTION_YEAR_UNSUPPORTED")
        if manifest.get("statistics", {}).get("symbol") != EXECUTABLE_SYMBOL:
            raise AcquisitionError("RECONSTRUCTION_SYMBOL_MISMATCH")
        if month in manifests:
            raise AcquisitionError("AMBIGUOUS_ARCHIVE_PRECEDENCE_DUPLICATE_MONTH")
        manifests[month] = (root, manifest)

    missing = sorted(set(range(1, 13)) - set(manifests))
    previous_last: datetime | None = None
    boundary_checks: list[dict[str, object]] = []
    for month in sorted(manifests):
        manifest = manifests[month][1]
        period = f"2024-{month:02d}"
        partition = _period_partition(manifest, period)
        first = _parse_manifest_timestamp(partition["first_timestamp"])
        last = _parse_manifest_timestamp(partition["last_timestamp"])
        if (
            first.strftime("%Y-%m") != period
            or last.strftime("%Y-%m") != period
            or first > last
        ):
            raise AcquisitionError("RECONSTRUCTION_PACKAGE_CROSS_MONTH_ROWS")
        if previous_last is not None and first <= previous_last:
            raise AcquisitionError("RECONSTRUCTION_MONTH_BOUNDARY_OVERLAP")
        boundary_checks.append({
            "period": period,
            "first_timestamp": first,
            "last_timestamp": last,
            "ordered_after_previous": previous_last is None or first > previous_last,
        })
        previous_last = last
    ordered = [manifests[month][1]["package_id"] for month in sorted(manifests)]
    return canonical_data({
        "schema_version": "phase8b.exness-reconstruction-plan.v1",
        "symbol": EXECUTABLE_SYMBOL,
        "year": 2024,
        "status": "READY" if not missing else "INCOMPLETE_MONTHLY_SET",
        "reconstruction_authorized": not missing,
        "available_months": sorted(manifests),
        "missing_months": missing,
        "ordered_package_ids": ordered,
        "chronological_boundary_checks": boundary_checks,
        "year_level_acceptance_pending": True,
        "year_level_manifest_required": True,
        "year_level_canonical_hash_required": True,
        "complete_year_readback_required": True,
        "archive_precedence": "MONTHLY_ARCHIVES_EXCLUSIVELY",
        "deduplication_policy": "NO_CROSS_MONTH_DEDUPLICATION_EXPECTED; REJECT_OVERLAP",
        "conflict_policy": "FAIL_CLOSED",
        "double_count_prevention": "ONE_UNAMBIGUOUS_PACKAGE_PER_CALENDAR_MONTH",
    })
