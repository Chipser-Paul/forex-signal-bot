from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

from backtests import exness_monthly_control
from bot.acquisition import exness_archive, exness_monthly
from bot.acquisition.exness_archive import ingest_exness_archive
from bot.acquisition.exness_monthly import (
    classify_truncation_hypothesis,
    compare_annual_monthly_full_month,
    compare_annual_monthly_overlap,
    plan_2024_monthly_reconstruction,
)
from bot.acquisition.models import AcquisitionError
from bot.acquisition.storage import file_sha256


HEADER = "Exness,Symbol,Timestamp,Bid,Ask"


def _row(timestamp: str, bid: str = "2000.000", ask: str = "2000.200") -> str:
    return f"Exness,XAUUSDm,{timestamp},{bid},{ask}"


def _archive(root: Path, period: str, rows: tuple[str, ...]) -> Path:
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / f"Exness_XAUUSDm_{period}.zip"
    member = f"Exness_XAUUSDm_{period}.csv"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, "\n".join((HEADER, *rows)) + "\n")
    return path


def _packages(tmp_path: Path, annual_rows: tuple[str, ...], monthly_rows: tuple[str, ...]):
    annual_archive = _archive(tmp_path / "annual", "2024", annual_rows)
    monthly_archive = _archive(tmp_path / "monthly", "2024_12", monthly_rows)
    annual = ingest_exness_archive(annual_archive, tmp_path / "processed-annual", batch_size=2)
    monthly = ingest_exness_archive(
        monthly_archive,
        tmp_path / "processed-monthly",
        claimed_month=12,
        batch_size=2,
    )
    annual_root = tmp_path / "processed-annual" / "packages" / annual["package_id"]
    monthly_root = tmp_path / "processed-monthly" / "packages" / monthly["package_id"]
    return annual_root, monthly_root, monthly


@pytest.mark.unit
def test_monthly_archive_has_deterministic_identity_coverage_and_raw_immutability(tmp_path):
    rows = (
        _row("2024-12-01 23:05:00.000Z"),
        _row("2024-12-31 21:57:00.000Z", "2100.000", "2100.200"),
    )
    archive = _archive(tmp_path, "2024_12", rows)
    before = (file_sha256(archive), archive.stat().st_mtime_ns)

    first = ingest_exness_archive(archive, tmp_path / "processed-a", claimed_month=12)
    second = ingest_exness_archive(archive, tmp_path / "processed-b", claimed_month=12)
    repeated = ingest_exness_archive(archive, tmp_path / "processed-a", claimed_month=12)

    assert first["package_id"] == second["package_id"]
    assert first["package_id"].startswith("exness-xauusdm-2024-12-")
    assert first["claimed_month"] == 12 and first["claimed_period"] == "2024-12"
    assert first["statistics"]["month_counts"] == {"2024-12": 2}
    assert repeated["idempotent_existing_package"] is True
    assert (file_sha256(archive), archive.stat().st_mtime_ns) == before
    assert not any(path.suffix == ".csv" for path in (tmp_path / "processed-a").rglob("*"))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("period", "timestamp", "reason"),
    [
        ("2024_11", "2024-11-01 00:00:00.000Z", "FILENAME_SYMBOL_OR_YEAR_MISMATCH"),
        ("2024_12", "2024-11-30 23:59:00.000Z", "CLAIMED_MONTH_MISMATCH"),
    ],
)
def test_unexpected_month_or_out_of_period_content_fails_closed(tmp_path, period, timestamp, reason):
    archive = _archive(tmp_path, period, (_row(timestamp),))
    with pytest.raises(AcquisitionError, match=reason):
        ingest_exness_archive(archive, tmp_path / "processed", claimed_month=12)


@pytest.mark.unit
def test_identical_overlap_and_continuation_are_reported_exactly(tmp_path):
    common = tuple(
        _row(f"2024-12-15 23:05:{second:02d}.000Z", f"2000.{second:03d}", f"2000.{second + 200:03d}")
        for second in range(3)
    )
    continuation = _row("2024-12-16 00:00:00.000Z", "2001.000", "2001.200")
    annual_root, monthly_root, _manifest = _packages(tmp_path, common, (*common, continuation))

    result = compare_annual_monthly_overlap(annual_root, monthly_root, minimum_overlap_rows=1)

    assert result["classification"] == "IDENTICAL"
    assert result["exact_timestamp_bid_ask_matches"] == 3
    assert result["ticks_only_in_annual"] == result["ticks_only_in_monthly"] == 0
    assert result["first_divergence"] is None and result["last_divergence"] is None
    assert result["normalized_common_bound_hashes"]["annual"] == result["normalized_common_bound_hashes"]["monthly"]
    assert result["monthly_continuation_rows_after_annual_last_date"] == 1
    assert result["annual_absent_weekdays_present_monthly"] == ["2024-12-16"]


@pytest.mark.unit
def test_full_month_comparison_reports_exact_annual_subset_and_monthly_coverage(tmp_path):
    common = (
        _row("2024-12-01 00:00:00.000Z"),
        _row("2024-12-02 00:00:00.000Z", "2001.000", "2001.200"),
    )
    monthly_only = _row("2024-12-31 00:00:00.000Z", "2002.000", "2002.200")
    annual_root, monthly_root, _manifest = _packages(
        tmp_path, common, (*common, monthly_only)
    )

    result = compare_annual_monthly_full_month(
        annual_root, monthly_root, minimum_matching_rows=1
    )

    assert result["classification"] == "MATERIAL_FEED_DIFFERENCES"
    assert result["annual_row_count"] == result["exact_matches"] == 2
    assert result["annual_only_ticks"] == 0
    assert result["monthly_only_ticks"] == 1
    assert result["record_differences"] == 1
    assert result["shared_timestamp_order_differences"] == 0
    assert result["annual_is_exact_subset_of_monthly"] is True
    assert result["daily_row_count_differences"] == {
        "2024-12-31": {"annual": 0, "monthly": 1}
    }


@pytest.mark.unit
def test_full_month_comparison_reports_annual_only_source_inversion(tmp_path):
    annual_archive = _archive(
        tmp_path / "annual",
        "2024",
        (
            _row("2024-11-03 00:00:00.000Z", "2001.000", "2001.200"),
            _row("2024-11-01 00:00:00.000Z"),
        ),
    )
    monthly_archive = _archive(
        tmp_path / "monthly",
        "2024_11",
        (
            _row("2024-11-01 00:00:00.000Z"),
            _row("2024-11-03 00:00:00.000Z", "2001.000", "2001.200"),
        ),
    )
    annual = ingest_exness_archive(annual_archive, tmp_path / "processed-annual", batch_size=2)
    monthly = ingest_exness_archive(
        monthly_archive,
        tmp_path / "processed-monthly",
        claimed_month=11,
        batch_size=2,
    )

    result = compare_annual_monthly_full_month(
        tmp_path / "processed-annual" / "packages" / annual["package_id"],
        tmp_path / "processed-monthly" / "packages" / monthly["package_id"],
        minimum_matching_rows=1,
    )

    assert result["classification"] == "EQUIVALENT_AFTER_ORDER_NORMALIZATION"
    assert result["annual_source_order_inversions"]["count"] == 1
    assert result["monthly_source_order_inversions"]["count"] == 0
    assert result["ordering_conclusion"] == (
        "ANNUAL_ONLY_SOURCE_ORDER_INVERSIONS; MONTHLY_SOURCE_MONOTONIC"
    )


@pytest.mark.unit
def test_overlap_can_be_equivalent_after_normalizing_same_timestamp_order(tmp_path):
    first = _row("2024-12-15 23:05:00.000Z", "2000.000", "2000.200")
    second = _row("2024-12-15 23:05:00.000Z", "2000.100", "2000.300")
    last = _row("2024-12-15 23:05:01.000Z", "2000.200", "2000.400")
    annual_root, monthly_root, _manifest = _packages(
        tmp_path, (first, second, last), (second, first, last)
    )

    result = compare_annual_monthly_overlap(annual_root, monthly_root, minimum_overlap_rows=1)

    assert result["classification"] == "EQUIVALENT_AFTER_ORDER_NORMALIZATION"
    assert result["sequence_differences"] == 2
    assert result["normalized_common_bound_hashes"]["annual"] == result["normalized_common_bound_hashes"]["monthly"]


@pytest.mark.unit
@pytest.mark.parametrize("conflicting_price", [False, True])
def test_source_only_or_conflicting_overlap_is_material(tmp_path, conflicting_price):
    first = _row("2024-12-15 23:05:00.000Z")
    middle = _row("2024-12-15 23:05:01.000Z", "2000.100", "2000.300")
    changed = _row(
        "2024-12-15 23:05:01.000Z" if conflicting_price else "2024-12-15 23:05:01.500Z",
        "2000.150",
        "2000.350",
    )
    last = _row("2024-12-15 23:05:02.000Z", "2000.200", "2000.400")
    annual_root, monthly_root, _manifest = _packages(tmp_path, (first, middle, last), (first, changed, last))

    result = compare_annual_monthly_overlap(annual_root, monthly_root, minimum_overlap_rows=1)

    assert result["classification"] == "MATERIAL_FEED_DIFFERENCES"
    assert result["ticks_only_in_annual"] == result["ticks_only_in_monthly"] == 1
    assert result["first_divergence"] is not None
    assert result["identical_timestamps_with_different_prices"] == int(conflicting_price)


@pytest.mark.unit
def test_nonoverlapping_archives_are_insufficient(tmp_path):
    annual_root, monthly_root, _manifest = _packages(
        tmp_path,
        (_row("2024-12-01 00:00:00.000Z"),),
        (_row("2024-12-02 00:00:00.000Z"),),
    )
    result = compare_annual_monthly_overlap(annual_root, monthly_root, minimum_overlap_rows=1)
    assert result["classification"] == "INSUFFICIENT_OVERLAP"


@pytest.mark.unit
def test_truncation_evidence_requires_exact_large_overlap_continuation_and_near_boundary():
    assert classify_truncation_hypothesis(
        overlap_classification="IDENTICAL",
        matched_overlap_rows=1_000,
        continuation_rows=1,
        annual_member_distance_below_boundary_bytes=96_813,
    ) == "STRONGLY_SUPPORTED_BY_DATA"
    assert classify_truncation_hypothesis(
        overlap_classification="IDENTICAL",
        matched_overlap_rows=999,
        continuation_rows=1,
        annual_member_distance_below_boundary_bytes=96_813,
    ) == "POSSIBLE"
    assert classify_truncation_hypothesis(
        overlap_classification="MATERIAL_FEED_DIFFERENCES",
        matched_overlap_rows=10_000,
        continuation_rows=1,
        annual_member_distance_below_boundary_bytes=1,
    ) == "NOT_SUPPORTED"


def _manifest(month: int | None, package_id: str) -> dict[str, object]:
    partitions = [] if month is None else [{
        "period": f"2024-{month:02d}",
        "first_timestamp": f"2024-{month:02d}-01T00:00:00Z",
        "last_timestamp": f"2024-{month:02d}-01T00:00:01Z",
    }]
    return {
        "claimed_year": 2024,
        "claimed_month": month,
        "package_id": package_id,
        "statistics": {"symbol": "XAUUSDm"},
        "partitions": partitions,
    }


@pytest.mark.unit
def test_reconstruction_requires_one_unambiguous_package_for_each_month(tmp_path, monkeypatch):
    roots = []
    manifests = {}
    for month in range(1, 13):
        root = tmp_path / f"month-{month:02d}"
        root.mkdir()
        roots.append(root)
        manifests[root.resolve()] = _manifest(month, f"package-{month:02d}")
    monkeypatch.setattr(exness_monthly, "verify_exness_package", lambda root: manifests[Path(root).resolve()])

    complete = plan_2024_monthly_reconstruction(roots)
    incomplete = plan_2024_monthly_reconstruction(roots[:-1])

    assert complete["status"] == "READY" and complete["reconstruction_authorized"] is True
    assert complete["ordered_package_ids"] == [f"package-{month:02d}" for month in range(1, 13)]
    assert incomplete["status"] == "INCOMPLETE_MONTHLY_SET"
    assert incomplete["missing_months"] == [12]
    assert incomplete["reconstruction_authorized"] is False


@pytest.mark.unit
def test_reconstruction_rejects_annual_mixing_and_duplicate_month_precedence(tmp_path, monkeypatch):
    annual = tmp_path / "annual"
    december_a = tmp_path / "december-a"
    december_b = tmp_path / "december-b"
    for root in (annual, december_a, december_b):
        root.mkdir()
    manifests = {
        annual.resolve(): _manifest(None, "annual"),
        december_a.resolve(): _manifest(12, "december-a"),
        december_b.resolve(): _manifest(12, "december-b"),
    }
    monkeypatch.setattr(exness_monthly, "verify_exness_package", lambda root: manifests[Path(root).resolve()])

    with pytest.raises(AcquisitionError, match="ANNUAL_MONTHLY_MIX"):
        plan_2024_monthly_reconstruction((annual,))
    with pytest.raises(AcquisitionError, match="DUPLICATE_MONTH"):
        plan_2024_monthly_reconstruction((december_a, december_b))


@pytest.mark.unit
def test_reconstruction_rejects_cross_month_partition_identity(tmp_path, monkeypatch):
    november = tmp_path / "november"
    november.mkdir()
    manifest = _manifest(11, "november")
    manifest["partitions"][0]["last_timestamp"] = "2024-12-01T00:00:00Z"
    monkeypatch.setattr(exness_monthly, "verify_exness_package", lambda _root: manifest)

    with pytest.raises(AcquisitionError, match="CROSS_MONTH_ROWS"):
        plan_2024_monthly_reconstruction((november,))


@pytest.mark.unit
def test_monthly_disk_reserve_fails_before_scan_and_cli_stays_offline(tmp_path, monkeypatch, capsys):
    archive = _archive(tmp_path, "2024_12", (_row("2024-12-02 00:00:00.000Z"),))
    monkeypatch.setattr(
        exness_archive.shutil,
        "disk_usage",
        lambda _path: type("Usage", (), {"free": exness_archive.MINIMUM_RESERVE_BYTES})(),
    )
    monkeypatch.setattr(
        exness_archive,
        "scan_exness_archive",
        lambda *_args: (_ for _ in ()).throw(AssertionError("content must not be opened")),
    )
    with pytest.raises(AcquisitionError, match="DISK_RESERVE"):
        ingest_exness_archive(archive, tmp_path / "processed", claimed_month=12)

    mt5_before = sys.modules.get("MetaTrader5")
    result = exness_monthly_control.main([
        "inspect", "--raw-root", str(archive.parent), "--archive", str(archive),
        "--month", "12",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert result == 0 and payload["status"] == "EXNESS_MONTHLY_ARCHIVE_SAFE"
    assert sys.modules.get("MetaTrader5") is mt5_before
    assert "bid" not in payload and "ask" not in payload


@pytest.mark.unit
def test_monthly_discovery_selects_only_the_explicitly_declared_period(tmp_path):
    november = _archive(tmp_path / "monthly", "2024_11", (_row("2024-11-01 00:00:00.000Z"),))
    _archive(tmp_path / "monthly", "2024_12", (_row("2024-12-01 00:00:00.000Z"),))

    selected = exness_monthly_control.discover_monthly_archive(
        november.parent,
        year=2024,
        month=11,
    )

    assert selected == november.resolve()


@pytest.mark.unit
def test_monthly_control_requires_declared_period(tmp_path, capsys):
    archive = _archive(tmp_path, "2024_11", (_row("2024-11-01 00:00:00.000Z"),))

    result = exness_monthly_control.main([
        "inspect", "--raw-root", str(archive.parent), "--archive", str(archive)
    ])

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["reason_code"] == "DECLARED_MONTH_REQUIRED"
