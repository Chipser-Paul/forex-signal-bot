from __future__ import annotations

import json
import stat
import sys
import zipfile
from pathlib import Path

import pytest

from backtests import exness_archive_control
from bot.acquisition import exness_archive
from bot.acquisition.exness_archive import (
    EXPECTED_HEADER,
    _arrow,
    _readback_partitions,
    exness_tick_schema,
    _unsafe_member_reason,
    ingest_exness_archive,
    inspect_exness_archive,
    scan_exness_archive,
    verify_exness_package,
)
from bot.acquisition.models import AcquisitionError
from bot.acquisition.storage import file_sha256


HEADER = ",".join(EXPECTED_HEADER)
ROWS = (
    "Exness,XAUUSDm,2024-01-02 12:00:00.000Z,2000.000,2000.200",
    "Exness,XAUUSDm,2024-01-02 12:00:00.500Z,2000.100,2000.300",
    "Exness,XAUUSDm,2024-02-01 12:00:00.000Z,2010.000,2010.250",
)


def _archive(tmp_path: Path, rows=ROWS, *, header=HEADER, member="Exness_XAUUSDm_2024.csv", final_newline=True):
    raw = tmp_path / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / "Exness_XAUUSDm_2024.zip"
    content = "\n".join((header, *rows)) + ("\n" if final_newline else "")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, content)
    return path


@pytest.mark.unit
def test_safe_archive_scan_and_deterministic_parquet_ingestion(tmp_path):
    archive = _archive(tmp_path)
    raw_hash = file_sha256(archive)
    raw_mtime = archive.stat().st_mtime_ns
    inspection = inspect_exness_archive(archive)
    stats = scan_exness_archive(archive, inspection)

    assert inspection.archive_type == "ZIP" and len(inspection.members) == 1
    assert stats["row_count"] == 3
    assert stats["symbol"] == "XAUUSDm"
    assert stats["timestamp_timezone"] == "UTC_EXPLICIT_Z"
    assert stats["crossed_quote_rows"] == 0

    first = ingest_exness_archive(archive, tmp_path / "processed-a", batch_size=2)
    second = ingest_exness_archive(archive, tmp_path / "processed-b", batch_size=2)
    first_hashes = [item["sha256"] for item in first["partitions"]]
    second_hashes = [item["sha256"] for item in second["partitions"]]
    assert first["classification"] == "DEVELOPMENT_ONLY"
    assert first["canonical_normalized_sha256"] == second["canonical_normalized_sha256"]
    assert first_hashes == second_hashes
    package = tmp_path / "processed-a" / "packages" / first["package_id"]
    assert verify_exness_package(package, deep=True)["statistics"]["row_count"] == 3
    repeated = ingest_exness_archive(archive, tmp_path / "processed-a", batch_size=2)
    assert repeated["idempotent_existing_package"] is True
    assert file_sha256(archive) == raw_hash and archive.stat().st_mtime_ns == raw_mtime
    assert not any(path.suffix == ".csv" for path in (tmp_path / "processed-a").rglob("*"))


@pytest.mark.unit
def test_recovery_package_override_is_canonical_and_never_accepts_legacy_identity(tmp_path):
    archive = _archive(
        tmp_path,
        rows=("Exness,XAUUSDm,2024-12-02 12:00:00.000Z,2000.000,2000.200",),
        member="Exness_XAUUSDm_2024_12.csv",
    )
    monthly_archive = archive.with_name("Exness_XAUUSDm_2024_12.zip")
    archive.rename(monthly_archive)
    expected_id = f"exness-xauusdm-2024-12-{file_sha256(monthly_archive)[:16]}-recovery-0002"

    result = ingest_exness_archive(
        monthly_archive,
        tmp_path / "processed",
        claimed_month=12,
        batch_size=2,
        package_id_override=expected_id,
    )

    assert result["package_id"] == expected_id
    with pytest.raises(AcquisitionError, match="ARCHIVE_RECOVERY_PACKAGE_ID_INVALID"):
        ingest_exness_archive(
            monthly_archive,
            tmp_path / "legacy",
            claimed_month=12,
            batch_size=2,
            package_id_override=expected_id.replace("recovery-0002", "recovery-v1"),
        )


@pytest.mark.unit
def test_readback_rejects_a_stored_row_identity_that_no_longer_matches_its_row(tmp_path):
    archive = _archive(tmp_path)
    result = ingest_exness_archive(archive, tmp_path / "processed", batch_size=2)
    package = tmp_path / "processed" / "packages" / result["package_id"]
    partition = package / result["partitions"][0]["relative_path"]
    _pa, pq = _arrow()
    table = pq.read_table(partition)
    row_identities = table["row_identity"].to_pylist()
    row_identities[1] = "0" * 64
    table = _pa.Table.from_arrays(
        [
            _pa.array(row_identities)
            if name == "row_identity"
            else table[name]
            for name in exness_tick_schema().names
        ],
        schema=exness_tick_schema(),
    )
    pq.write_table(table, partition)

    with pytest.raises(AcquisitionError, match="PARQUET_ROW_IDENTITY_MISMATCH"):
        _readback_partitions(package, result["partitions"], inspect_exness_archive(archive))


@pytest.mark.unit
def test_non_monotonic_source_rows_are_reported_and_normalized_deterministically(tmp_path):
    rows = (
        "Exness,XAUUSDm,2024-01-03 00:00:00.000Z,2002.000,2002.100",
        "Exness,XAUUSDm,2024-01-01 00:00:00.000Z,2000.000,2000.100",
        "Exness,XAUUSDm,2024-01-02 00:00:00.000Z,2001.000,2001.100",
    )
    archive = _archive(tmp_path, rows=rows)
    source_stats = scan_exness_archive(archive, inspect_exness_archive(archive))

    assert source_stats["non_monotonic_rows"] == 1
    assert source_stats["first_timestamp"] == "2024-01-01T00:00:00Z"
    assert source_stats["last_timestamp"] == "2024-01-03T00:00:00Z"

    result = ingest_exness_archive(archive, tmp_path / "processed", batch_size=2)

    assert result["statistics"]["non_monotonic_rows"] == 1
    assert result["readback"]["reconciled"] is True
    assert result["readback"]["first_timestamp"] == "2024-01-01T00:00:00Z"
    assert result["readback"]["last_timestamp"] == "2024-01-03T00:00:00Z"
    assert result["canonical_normalized_sha256"] != result["statistics"][
        "source_order_canonical_sha256"
    ]


@pytest.mark.unit
def test_exness_source_identity_accepts_case_only_not_another_provider(tmp_path):
    lower = _archive(
        tmp_path / "lower",
        rows=("exness,XAUUSDm,2024-01-02 00:00:00.000Z,2000.000,2000.100",),
    )
    inspection = inspect_exness_archive(lower)
    assert scan_exness_archive(lower, inspection)["row_count"] == 1

    foreign = _archive(
        tmp_path / "foreign",
        rows=("Another,XAUUSDm,2024-01-02 00:00:00.000Z,2000.000,2000.100",),
    )
    with pytest.raises(AcquisitionError, match="SOURCE_VALUE_MISMATCH"):
        scan_exness_archive(foreign, inspect_exness_archive(foreign))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("member", "reason"),
    [
        ("../escape.csv", "ARCHIVE_PATH_TRAVERSAL"),
        ("C:/escape.csv", "ARCHIVE_WINDOWS_PATH"),
        ("payload.exe", "ARCHIVE_EXECUTABLE_ENTRY"),
    ],
)
def test_archive_member_paths_and_types_fail_closed(tmp_path, member, reason):
    archive = _archive(tmp_path, member=member)
    with pytest.raises(AcquisitionError, match=reason):
        inspect_exness_archive(archive)


@pytest.mark.unit
def test_corrupt_zip_fails_closed(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    archive = raw / "Exness_XAUUSDm_2024.zip"
    archive.write_bytes(b"not-a-zip")
    with pytest.raises(AcquisitionError, match="CORRUPT"):
        inspect_exness_archive(archive)


@pytest.mark.unit
def test_case_colliding_members_fail_closed(tmp_path):
    archive = _archive(tmp_path)
    with zipfile.ZipFile(archive, "a") as value:
        value.writestr("exness_xauusdm_2024.CSV", HEADER + "\n")
    with pytest.raises(AcquisitionError, match="CASE_COLLISION"):
        inspect_exness_archive(archive)


@pytest.mark.unit
def test_link_and_encrypted_metadata_are_rejected():
    link = zipfile.ZipInfo("ticks.csv")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    assert _unsafe_member_reason(link) == "ARCHIVE_LINK_ENTRY"
    encrypted = zipfile.ZipInfo("ticks.csv")
    encrypted.flag_bits |= 0x1
    assert _unsafe_member_reason(encrypted) == "ARCHIVE_ENCRYPTED_ENTRY"


@pytest.mark.unit
def test_compression_bomb_ratio_is_rejected(tmp_path):
    archive = _archive(tmp_path, rows=("0" * 2_000_000,))
    with pytest.raises(AcquisitionError, match="COMPRESSION|MEMBER_EXPANSION"):
        inspect_exness_archive(archive, maximum_compression_ratio=10)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("header", "rows", "reason"),
    [
        ("bad,header", ROWS, "HEADER_MISMATCH"),
        (HEADER, ("Exness,XAUUSD,2024-01-02 12:00:00.000Z,1,2",), "SYMBOL_MISMATCH"),
        (HEADER, ("Exness,XAUUSDm,2024-01-02 12:00:00.000,1,2",), "TIMESTAMP_TIMEZONE_UNPROVEN"),
        (HEADER, ("Exness,XAUUSDm,2024-01-02 12:00:00.000Z,2,1",), "CROSSED_QUOTE"),
        (HEADER, ("too,few,fields",), "ROW_FIELD_COUNT_INVALID"),
    ],
)
def test_malformed_content_rejects_conversion(tmp_path, header, rows, reason):
    archive = _archive(tmp_path, rows=rows, header=header)
    inspection = inspect_exness_archive(archive)
    with pytest.raises(AcquisitionError, match=reason):
        scan_exness_archive(archive, inspection)


@pytest.mark.unit
def test_filename_symbol_mismatch_fails_before_content_conversion(tmp_path):
    archive = _archive(tmp_path, member="Exness_XAUUSD_2024.csv")
    with pytest.raises(AcquisitionError, match="FILENAME_SYMBOL_OR_YEAR_MISMATCH"):
        ingest_exness_archive(archive, tmp_path / "processed")


@pytest.mark.unit
def test_duplicates_and_truncation_are_counted_without_silent_discard(tmp_path):
    rows = (
        ROWS[0],
        ROWS[0],
        "Exness,XAUUSDm,2024-01-02 12:00:00.000Z,2000.050,2000.250",
    )
    archive = _archive(tmp_path, rows=rows, final_newline=False)
    stats = scan_exness_archive(archive, inspect_exness_archive(archive))
    assert stats["row_count"] == 3
    assert stats["exact_duplicate_rows"] == 1
    assert stats["duplicate_timestamps_different_prices"] == 1
    assert stats["truncation_indicators"] == 1


@pytest.mark.unit
def test_interrupted_conversion_leaves_no_published_or_partial_package(tmp_path, monkeypatch):
    archive = _archive(tmp_path)
    output = tmp_path / "processed"
    monkeypatch.setattr(
        exness_archive,
        "_write_partitions",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("simulated interruption")),
    )
    with pytest.raises(RuntimeError, match="interruption"):
        ingest_exness_archive(archive, output)
    assert not any(path.name.endswith(".partial") for path in output.rglob("*"))
    assert not any(path.name == "package.complete.json" for path in output.rglob("*"))


@pytest.mark.unit
def test_disk_reserve_rejection_occurs_before_content_scan(tmp_path, monkeypatch):
    archive = _archive(tmp_path)
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
        ingest_exness_archive(archive, tmp_path / "processed")


@pytest.mark.unit
def test_cli_is_offline_sanitized_and_does_not_import_mt5(tmp_path, capsys):
    archive = _archive(tmp_path)
    mt5_module_before = sys.modules.get("MetaTrader5")
    result = exness_archive_control.main([
        "inspect", "--raw-root", str(archive.parent), "--archive", str(archive)
    ])
    payload = json.loads(capsys.readouterr().out)
    assert result == 0 and payload["status"] == "EXNESS_ARCHIVE_SAFE"
    assert sys.modules.get("MetaTrader5") is mt5_module_before
    assert "bid" not in payload and "ask" not in payload

    blocked = exness_archive_control.main([
        "ingest", "--raw-root", str(archive.parent), "--archive", str(archive),
        "--output-root", str(tmp_path / "processed"), "--minimum-free-gb", "1",
    ])
    blocked_payload = json.loads(capsys.readouterr().out)
    assert blocked == 2
    assert blocked_payload["reason_code"] == "minimum free-space reserve cannot be below 15 GiB"
