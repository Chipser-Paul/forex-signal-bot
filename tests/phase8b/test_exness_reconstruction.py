from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from backtests import exness_monthly_control
from bot.acquisition.exness_archive import ingest_exness_archive
from bot.acquisition.exness_reconstruction import (
    MonthlyReconstructionPlan,
    build_2024_development_year_package,
    ingest_next_monthly_archive,
    monthly_storage_projection,
    monthly_reconstruction_readiness,
    quarantine_interrupted_partial,
    verify_2024_development_year_package,
)
from bot.acquisition.models import AcquisitionError


HEADER = "Exness,Symbol,Timestamp,Bid,Ask"


def _archive(root: Path, month: int, *, price: int = 2000) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"Exness_XAUUSDm_2024_{month:02d}.zip"
    member = f"Exness_XAUUSDm_2024_{month:02d}.csv"
    row = f"Exness,XAUUSDm,2024-{month:02d}-01 00:00:00.000Z,{price}.000,{price}.200"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, f"{HEADER}\n{row}\n")
    return path


@pytest.mark.unit
def test_readiness_is_declared_bounded_and_refuses_incomplete_year(tmp_path):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    raw.mkdir()
    output.mkdir()
    _archive(raw, 11)

    result = monthly_reconstruction_readiness(raw, output)

    assert len(result["months"]) == 12
    assert result["months"][10]["status"] == "RAW_READY"
    assert result["next_ingestible_month"] == 11
    assert result["status"] == "INCOMPLETE_MONTHLY_SET"
    assert result["reconstruction_authorized"] is False
    assert result["downloads_performed"] is False


@pytest.mark.unit
def test_managed_recovery_month_never_falls_back_to_directory_discovery(tmp_path):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    _archive(raw, 12)
    # A package directory could exist, but a declared managed month needs its
    # independent registry and zero/one active selection evidence.
    result = monthly_reconstruction_readiness(
        raw,
        output,
        managed_registry_roots={12: tmp_path / "missing-registry"},
    )
    december = result["months"][11]
    assert december["status"] == "CONFLICT"
    assert "PACKAGE_REGISTRY_MISSING" in december["reason_codes"]


@pytest.mark.unit
def test_managed_recovery_month_uses_active_registry_despite_quarantined_directories(
    tmp_path,
    monkeypatch,
):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    archive = _archive(raw, 12)
    result = ingest_exness_archive(archive, output, claimed_month=12)
    active_root = output / "packages" / result["package_id"]
    # Simulate a retained quarantined predecessor. Both directories are valid
    # package artifacts, but only the registry-selected root is executable.
    predecessor = output / "packages" / "retained-quarantined-predecessor"
    shutil.copytree(active_root, predecessor)
    manifest_path = predecessor / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["package_id"] = predecessor.name
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    completion_path = predecessor / "package.complete.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["package_id"] = predecessor.name
    completion["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    completion_path.write_text(json.dumps(completion, sort_keys=True), encoding="utf-8")

    class Registry:
        def __init__(self, _root):
            pass

        def active_package(self, _packages_root, **_kwargs):
            return active_root, {"status": "ACTIVE"}

    monkeypatch.setattr(
        "bot.acquisition.package_registry.PackageRegistryStore", Registry
    )

    readiness = monthly_reconstruction_readiness(
        raw,
        output,
        managed_registry_roots={12: tmp_path / "registry"},
    )

    december = readiness["months"][11]
    assert december["status"] == "VERIFIED_PACKAGE"
    assert december["package"]["package_id"] == result["package_id"]
    assert "DUPLICATE_PROCESSED_MONTH_IDENTITY" not in december["reason_codes"]


@pytest.mark.unit
def test_batch_ingests_exactly_one_then_resumes_and_skips_verified(tmp_path):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    _archive(raw, 11)
    _archive(raw, 12)

    first = ingest_next_monthly_archive(raw, output)
    second = ingest_next_monthly_archive(raw, output)
    third = ingest_next_monthly_archive(raw, output)

    assert first["action"] == second["action"] == "ONE_ARCHIVE_INGESTED"
    assert (first["month"], second["month"]) == (11, 12)
    assert third["action"] == "NO_ARCHIVE_INGESTED"
    assert third["readiness"]["months"][10]["status"] == "VERIFIED_PACKAGE"
    assert third["readiness"]["months"][11]["status"] == "VERIFIED_PACKAGE"
    assert third["readiness"]["reconstruction_authorized"] is False


@pytest.mark.unit
def test_changed_raw_archive_conflicts_with_verified_package(tmp_path):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    archive = _archive(raw, 11, price=2000)
    ingest_exness_archive(archive, output, claimed_month=11)
    _archive(raw, 11, price=2100)

    result = monthly_reconstruction_readiness(raw, output)

    assert result["status"] == "CONFLICT"
    assert result["months"][10]["reason_codes"] == [
        "RAW_PROCESSED_ARCHIVE_CONFLICT"
    ]
    with pytest.raises(AcquisitionError, match="RECONSTRUCTION_CONFLICT"):
        ingest_next_monthly_archive(raw, output)


@pytest.mark.unit
def test_duplicate_processed_month_identity_fails_closed(tmp_path):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    archive = _archive(raw, 11, price=2000)
    ingest_exness_archive(archive, output, claimed_month=11)
    archive.unlink()
    archive = _archive(raw, 11, price=2100)
    ingest_exness_archive(archive, output, claimed_month=11)

    result = monthly_reconstruction_readiness(raw, output)

    assert result["status"] == "CONFLICT"
    assert "DUPLICATE_PROCESSED_MONTH_IDENTITY" in result["months"][10]["reason_codes"]


@pytest.mark.unit
def test_interrupted_partial_package_requires_review(tmp_path):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    raw.mkdir()
    partial = output / "packages" / ".exness-xauusdm-2024-11-0123456789abcdef.partial"
    partial.mkdir(parents=True)

    result = monthly_reconstruction_readiness(raw, output)

    assert result["status"] == "CONFLICT"
    assert result["package_conflicts"] == ["INTERRUPTED_PARTIAL_MONTH_11"]


@pytest.mark.unit
def test_quarantined_partial_is_preserved_but_cannot_block_a_clean_retry(tmp_path):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    raw.mkdir()
    partial = output / "packages" / ".exness-xauusdm-2024-11-0123456789abcdef.partial"
    parquet = partial / "ticks" / "year=2024" / "month=11" / "part-00000.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.write_bytes(b"retained forensic evidence")
    forensic = tmp_path / "forensic_record.json"
    forensic.write_text('{"status":"COMPLETE"}\n', encoding="utf-8")

    marker = quarantine_interrupted_partial(
        partial,
        forensic_record=forensic,
        reason_code="PARTIAL_ARTIFACT_CORRUPTION",
    )
    result = monthly_reconstruction_readiness(raw, output)

    assert marker["status"] == "QUARANTINED"
    assert result["status"] == "INCOMPLETE_MONTHLY_SET"
    assert result["package_conflicts"] == []
    assert result["quarantined_partial_packages"] == [partial.name]


@pytest.mark.unit
def test_plan_and_disk_reserve_cannot_be_weakened(tmp_path, monkeypatch):
    with pytest.raises(AcquisitionError, match="PLAN_UNSAFE"):
        MonthlyReconstructionPlan(minimum_free_bytes=1)
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    _archive(raw, 11)
    output.mkdir()
    monkeypatch.setattr(
        "bot.acquisition.exness_reconstruction.shutil.disk_usage",
        lambda _path: type("Usage", (), {"free": 1})(),
    )

    with pytest.raises(AcquisitionError, match="DISK_RESERVE"):
        ingest_next_monthly_archive(raw, output)


@pytest.mark.unit
def test_batch_cli_is_bounded_sanitized_and_does_not_import_mt5(tmp_path, capsys):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    raw.mkdir()
    output.mkdir()
    mt5_before = sys.modules.get("MetaTrader5")

    code = exness_monthly_control.main([
        "batch-status",
        "--raw-root",
        str(raw),
        "--output-root",
        str(output),
    ])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "INCOMPLETE_MONTHLY_SET"
    assert payload["downloads_performed"] is False
    assert "bid" not in payload and "ask" not in payload
    assert sys.modules.get("MetaTrader5") is mt5_before

    _archive(raw, 11)
    code = exness_monthly_control.main([
        "batch-next",
        "--raw-root",
        str(raw),
        "--output-root",
        str(output),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["action"] == "ONE_ARCHIVE_INGESTED"
    assert payload["month"] == 11
    assert payload["status"] == "INCOMPLETE_MONTHLY_SET"
    assert sys.modules.get("MetaTrader5") is mt5_before


@pytest.mark.unit
def test_storage_projection_uses_two_observed_months_and_preserves_reserve():
    result = monthly_storage_projection(
        ((40, 240), (30, 170)),
        remaining_months=10,
        current_free_bytes=20_000,
        reserve_bytes=16_106_127_360,
    )

    assert result["remaining_months_archive_and_parquet_bytes"] == {
        "lower": 2_000,
        "baseline": 2_400,
        "upper": 4_200,
    }
    assert result["temporary_conversion_bytes"] == 360
    assert result["remaining_months_fit_upper_scenario"] is False
    assert result["projection_is_not_a_forecast"] is True


@pytest.mark.unit
def test_unexpected_zip_and_orphaned_package_fail_closed(tmp_path):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    archive = _archive(raw, 11)
    ingest_exness_archive(archive, output, claimed_month=11)
    archive.unlink()

    orphaned = monthly_reconstruction_readiness(raw, output)
    assert orphaned["status"] == "CONFLICT"
    assert orphaned["months"][10]["reason_codes"] == [
        "PROCESSED_PACKAGE_WITHOUT_RAW_EVIDENCE"
    ]

    (raw / "Exness_XAUUSDm_2024_11 (1).zip").write_bytes(b"not an archive")
    unexpected = monthly_reconstruction_readiness(raw, output)
    assert unexpected["status"] == "CONFLICT"
    assert unexpected["unexpected_archive_count"] == 1
    assert unexpected["unexpected_archive_names"] == [
        "Exness_XAUUSDm_2024_11 (1).zip"
    ]


@pytest.mark.unit
def test_all_twelve_verified_months_authorize_only_reconstruction_step(tmp_path):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    for month in range(1, 13):
        archive = _archive(raw, month, price=2000 + month)
        ingest_exness_archive(archive, output, claimed_month=month)

    result = monthly_reconstruction_readiness(raw, output)

    assert result["status"] == "READY_FOR_YEAR_RECONSTRUCTION"
    assert result["reconstruction_authorized"] is True
    assert all(item["status"] == "VERIFIED_PACKAGE" for item in result["months"])
    assert "COMPLETE_YEAR_READBACK_RECONCILIATION" in result[
        "reconstruction_requirements"
    ]


@pytest.mark.unit
def test_development_year_package_references_months_without_copying_tick_data(tmp_path):
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    roots = []
    for month in range(1, 13):
        archive = _archive(raw, month, price=2000 + month)
        result = ingest_exness_archive(archive, output, claimed_month=month)
        roots.append(output / "packages" / result["package_id"])

    first = build_2024_development_year_package(roots, output)
    second = build_2024_development_year_package(roots, output)
    manifest = verify_2024_development_year_package(
        output / "year-packages" / first["package_id"], roots
    )

    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert manifest["classification"] == "DEVELOPMENT_ONLY"
    assert manifest["statistics"]["row_count"] == 12
    assert len(manifest["monthly_packages"]) == 12
    assert not any(
        path.suffix == ".parquet"
        for path in (output / "year-packages" / first["package_id"]).rglob("*")
    )
