from __future__ import annotations

import hashlib
import json
import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bot.acquisition.models import AcquisitionError
from bot.acquisition.package_registry import PackageRegistryStore, PackageStatus, _json_hash
from backtests.package_registry_control import main


RAW = "a" * 64
HASH = "b" * 64
PERIOD = {"start_inclusive": "2024-12-01T00:00:00Z", "end_exclusive": "2025-01-01T00:00:00Z"}
LEGACY_RAW = "a5cef8ab1fb1bce26380113619c121da3062894b05b1c3d8de034c78bc8314fd"  # pragma: allowlist secret
LEGACY_ID = "exness-xauusdm-2024-12-a5cef8ab1fb1bce2-recovery-v1"
LEGACY_PERIOD = PERIOD


def store(tmp_path: Path) -> PackageRegistryStore:
    value = PackageRegistryStore(tmp_path / "registry")
    value.create(dataset_key="exness:XAUUSDm:2024-12", provider="exness", symbol="XAUUSDm", period=PERIOD, raw_archive_sha256=RAW, code_fingerprint="test-code")
    return value


def candidate(value: PackageRegistryStore, *, operation: str = "recovery-v2-0001") -> str:
    allocation = value.allocate_recovery(operation_id=operation, reason="DECEMBER_RECOVERY", writer_fingerprint="test-writer")["allocation"]
    package_id = allocation["package_id"]
    value.register_candidate(package_id=package_id, operation_id=operation, recovery_reason="DECEMBER_RECOVERY", predecessor_package_id=None, artifact_hashes={"quotes.parquet": HASH}, logical_canonical_sha256=HASH, manifest_sha256=HASH, completion_sha256=HASH, creation_fingerprint="test-writer")
    return package_id


def verified(value: PackageRegistryStore, package_id: str, operation: str = "recovery-v2-0001") -> None:
    value.transition(package_id, PackageStatus.VERIFYING, reason="START_VERIFICATION", operation_id=operation)
    value.transition(package_id, PackageStatus.VERIFIED_INACTIVE, reason="VERIFIED", operation_id=operation)


def test_empty_registry_is_fail_closed_and_deterministic(tmp_path: Path) -> None:
    value = store(tmp_path)
    loaded = value.load()
    assert loaded["active_package_id"] is None and loaded["revision"] == 0
    with pytest.raises(AcquisitionError, match="NO_ACTIVE"):
        value.active_package(tmp_path / "packages", expected_dataset_key="exness:XAUUSDm:2024-12", expected_raw_archive_sha256=RAW)


def test_recovery_identity_allocation_is_idempotent_and_monotonic(tmp_path: Path) -> None:
    value = store(tmp_path)
    first = value.allocate_recovery(operation_id="recovery-v2-0001", reason="RECOVERY", writer_fingerprint="writer")
    same = value.allocate_recovery(operation_id="recovery-v2-0001", reason="RECOVERY", writer_fingerprint="writer")
    second = value.allocate_recovery(operation_id="recovery-v3-0001", reason="RECOVERY", writer_fingerprint="writer")
    assert first["allocation"]["package_id"].endswith("-recovery-0001")
    assert same["idempotent"] is True and same["allocation"] == first["allocation"]
    assert second["allocation"]["package_id"].endswith("-recovery-0002")
    destination = value.allocated_destination(tmp_path / "packages", operation_id="recovery-v3-0001")
    assert destination.name == second["allocation"]["package_id"]
    destination.mkdir(parents=True)
    with pytest.raises(AcquisitionError, match="DESTINATION_COLLISION"):
        value.allocated_destination(tmp_path / "packages", operation_id="recovery-v3-0001")


def test_candidate_state_machine_and_exactly_one_active(tmp_path: Path) -> None:
    value = store(tmp_path); package_id = candidate(value); verified(value, package_id)
    active = value.activate(package_id, operation_id="recovery-v2-0001", reason="ACTIVATE")
    assert active["active_package_id"] == package_id
    with pytest.raises(AcquisitionError, match="ILLEGAL_TRANSITION"):
        value.transition(package_id, PackageStatus.VERIFIED_INACTIVE, reason="REVERSE", operation_id="recovery-v2-0001")
    second = candidate(value, operation="recovery-v3-0001"); verified(value, second, "recovery-v3-0001")
    active = value.activate(second, operation_id="recovery-v3-0001", reason="REPLACE")
    statuses = {item["package_id"]: item["status"] for item in active["packages"]}
    assert statuses == {package_id: "QUARANTINED", second: "ACTIVE"}
    with pytest.raises(AcquisitionError):
        value.activate(package_id, operation_id="recovery-v2-0001", reason="REACTIVATE")


def test_concurrent_allocations_are_unique_and_journal_reconciles(tmp_path: Path) -> None:
    value = store(tmp_path)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda index: value.allocate_recovery(operation_id=f"operation-{index:04d}", reason="RECOVERY", writer_fingerprint="writer"), range(6)))
    ids = {result["allocation"]["package_id"] for result in results}
    assert len(ids) == 6
    assert value.load()["revision"] == 6


def test_stale_revision_corruption_and_journal_mismatch_fail_closed(tmp_path: Path) -> None:
    value = store(tmp_path); revision = value.load()["revision"]
    value.allocate_recovery(operation_id="recovery-v2-0001", reason="RECOVERY", writer_fingerprint="writer")
    with pytest.raises(AcquisitionError, match="STALE"):
        value.allocate_recovery(operation_id="recovery-v3-0001", reason="RECOVERY", writer_fingerprint="writer", expected_revision=revision)
    value.journal_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(AcquisitionError, match="JOURNAL"):
        value.load()


def test_active_discovery_checks_only_selected_package_and_marker_hashes(tmp_path: Path) -> None:
    value = store(tmp_path); package_id = candidate(value); verified(value, package_id)
    root = tmp_path / "packages" / package_id; root.mkdir(parents=True)
    manifest = root / "manifest.json"; completion = root / "package.complete.json"
    manifest.write_text("manifest", encoding="utf-8"); completion.write_text("complete", encoding="utf-8")
    registry = value.load(); record = next(item for item in registry["packages"] if item["package_id"] == package_id)
    # Synthetic package markers are registered with their actual physical hashes.
    record["manifest_sha256"] = hashlib.sha256(b"manifest").hexdigest(); record["completion_sha256"] = hashlib.sha256(b"complete").hexdigest()
    # This direct synthetic adjustment is intentionally rejected by journal binding.
    with pytest.raises(AcquisitionError, match="JOURNAL"):
        PackageRegistryStore(value.root)._validate_journal(registry)
    # Register a second clean synthetic registry with predeclared marker hashes.
    clean = PackageRegistryStore(tmp_path / "clean")
    clean.create(dataset_key="exness:XAUUSDm:2024-12", provider="exness", symbol="XAUUSDm", period=PERIOD, raw_archive_sha256=RAW, code_fingerprint="test")
    alloc = clean.allocate_recovery(operation_id="recovery-v2-0001", reason="RECOVERY", writer_fingerprint="writer")["allocation"]
    package = alloc["package_id"]; target = tmp_path / "clean-packages" / package; target.mkdir(parents=True)
    artifact = target / "quotes.parquet"; artifact.write_bytes(b"synthetic-quotes")
    manifest_payload = {"package_id": package, "canonical_normalized_sha256": HASH}
    completion_payload = {"package_id": package}
    manifest_text = json.dumps(manifest_payload, sort_keys=True); completion_text = json.dumps(completion_payload, sort_keys=True)
    (target / "manifest.json").write_text(manifest_text, encoding="utf-8"); (target / "package.complete.json").write_text(completion_text, encoding="utf-8")
    clean.register_candidate(package_id=package, operation_id="recovery-v2-0001", recovery_reason="RECOVERY", predecessor_package_id=None, artifact_hashes={"quotes.parquet": hashlib.sha256(b"synthetic-quotes").hexdigest()}, logical_canonical_sha256=HASH, manifest_sha256=hashlib.sha256(manifest_text.encode()).hexdigest(), completion_sha256=hashlib.sha256(completion_text.encode()).hexdigest(), creation_fingerprint="writer")
    verified(clean, package); clean.activate(package, operation_id="recovery-v2-0001", reason="ACTIVATE")
    selected, record = clean.active_package(tmp_path / "clean-packages", expected_dataset_key="exness:XAUUSDm:2024-12", expected_raw_archive_sha256=RAW)
    assert selected.name == package and record["status"] == "ACTIVE"
    (selected / "manifest.json").write_text("changed", encoding="utf-8")
    with pytest.raises(AcquisitionError, match="IDENTITY_CHANGED"):
        clean.active_package(tmp_path / "clean-packages", expected_dataset_key="exness:XAUUSDm:2024-12", expected_raw_archive_sha256=RAW)


def test_interrupted_journal_publication_fails_closed_on_restart(tmp_path: Path, monkeypatch) -> None:
    value = store(tmp_path)
    original = value._write_atomic
    monkeypatch.setattr(value, "_write_atomic", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("simulated crash")))
    with pytest.raises(OSError):
        value.allocate_recovery(operation_id="recovery-v2-0001", reason="RECOVERY", writer_fingerprint="writer")
    monkeypatch.setattr(value, "_write_atomic", original)
    with pytest.raises(AcquisitionError, match="JOURNAL_MISMATCH"):
        value.load()


def test_bootstrap_dry_plan_and_apply_require_exact_hash(tmp_path: Path) -> None:
    spec = {"dataset_key": "exness:XAUUSDm:2024-12", "provider": "exness", "symbol": "XAUUSDm", "period": PERIOD, "raw_archive_sha256": RAW, "code_fingerprint": "bootstrap", "generation_counter": 1, "packages": [], "active_package_id": None, "justification": "owner-reviewed"}
    spec_path = tmp_path / "plan.json"; spec_path.write_text(json.dumps(spec), encoding="utf-8")
    root = tmp_path / "registry"
    assert main(["bootstrap-dry-run", "--registry-root", str(root), "--spec", str(spec_path)]) == 0
    assert main(["bootstrap-apply", "--registry-root", str(root), "--spec", str(spec_path), "--plan-hash", "0" * 64, "--confirm"]) == 2
    assert main(["bootstrap-apply", "--registry-root", str(root), "--spec", str(spec_path), "--plan-hash", _json_hash(spec), "--confirm"]) == 0


def test_exact_legacy_identity_is_bootstrap_only_and_next_generation_is_two(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    legacy = {
        "package_id": LEGACY_ID, "legacy_bootstrap": True,
        "legacy_identity_format": "phase8b.legacy-recovery-v1.literal",
        "generation": 1, "recovery_reason": "HISTORICAL_PHYSICAL_INTEGRITY_UNCERTAINTY",
        "status": "QUARANTINED", "status_reason": "HISTORICAL_PHYSICAL_INTEGRITY_UNCERTAINTY",
        "artifact_hashes": {"ticks/part.parquet": HASH}, "logical_canonical_sha256": HASH,
        "manifest_sha256": HASH, "completion_sha256": HASH,
    }
    spec = {"dataset_key": "exness:XAUUSDm:2024-12", "provider": "exness", "symbol": "XAUUSDm", "period": LEGACY_PERIOD, "raw_archive_sha256": LEGACY_RAW, "code_fingerprint": "bootstrap", "generation_counter": 1, "packages": [legacy], "active_package_id": None, "justification": "owner-reviewed"}
    store = PackageRegistryStore(root)
    registry = store.bootstrap(spec, reviewed_plan_hash=_json_hash(spec), owner_confirmed=True)
    record = registry["packages"][0]
    assert record["package_id"] == LEGACY_ID and record["status"] == "QUARANTINED" and registry["active_package_id"] is None
    with pytest.raises(AcquisitionError):
        store.activate(LEGACY_ID, operation_id="legacy-activate-0001", reason="NO")
    allocation = store.allocate_recovery(operation_id="recovery-v2-0001", reason="RECOVERY", writer_fingerprint="writer")
    assert allocation["allocation"]["package_id"].endswith("-recovery-0002")
    store.register_candidate(package_id=allocation["allocation"]["package_id"], operation_id="recovery-v2-0001", recovery_reason="SUCCESSOR", predecessor_package_id=LEGACY_ID, artifact_hashes={"x": HASH}, logical_canonical_sha256=HASH, manifest_sha256=HASH, completion_sha256=HASH, creation_fingerprint="writer")
    with pytest.raises(AcquisitionError):
        store.register_candidate(package_id=LEGACY_ID, operation_id="legacy-add-0001", recovery_reason="NO", predecessor_package_id=None, artifact_hashes={"x": HASH}, logical_canonical_sha256=HASH, manifest_sha256=HASH, completion_sha256=HASH, creation_fingerprint="writer")


@pytest.mark.parametrize("mutation", [
    {"legacy_bootstrap": False}, {"legacy_identity_format": "recovery-v1"},
    {"package_id": "exness-xauusdm-2024-12-a5cef8ab1fb1bce2-recovery-v2"},
    {"status": "ACTIVE"}, {"generation": 2},
])
def test_legacy_bootstrap_rejects_every_non_exact_shape(tmp_path: Path, mutation: dict[str, object]) -> None:
    legacy = {"package_id": LEGACY_ID, "legacy_bootstrap": True, "legacy_identity_format": "phase8b.legacy-recovery-v1.literal", "generation": 1, "recovery_reason": "UNCERTAIN", "status": "QUARANTINED", "status_reason": "UNCERTAIN", "artifact_hashes": {"x": HASH}, "logical_canonical_sha256": HASH, "manifest_sha256": HASH, "completion_sha256": HASH}
    legacy.update(mutation)
    spec = {"dataset_key": "exness:XAUUSDm:2024-12", "provider": "exness", "symbol": "XAUUSDm", "period": LEGACY_PERIOD, "raw_archive_sha256": LEGACY_RAW, "code_fingerprint": "bootstrap", "generation_counter": 1, "packages": [legacy], "active_package_id": None, "justification": "owner-reviewed"}
    with pytest.raises(AcquisitionError):
        PackageRegistryStore(tmp_path / "registry").bootstrap(spec, reviewed_plan_hash=_json_hash(spec), owner_confirmed=True)


def test_rejects_traversal_and_fresh_import_has_no_mt5(tmp_path: Path) -> None:
    value = store(tmp_path)
    with pytest.raises(AcquisitionError):
        value.allocate_recovery(operation_id="../bad", reason="RECOVERY", writer_fingerprint="writer")
    import bot.acquisition.package_registry as registry_module
    assert "MetaTrader5" not in inspect.getsource(registry_module)
