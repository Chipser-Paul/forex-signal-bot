"""Immutable, offline package-selection registry for managed data periods.

This module deliberately has no gateway, MT5, archive-conversion, or strategy
imports.  It owns package *selection*, not market data processing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from filelock import FileLock

from bot.validation.models import canonical_data

from .models import AcquisitionError
from .storage import file_sha256


UTC = timezone.utc
REGISTRY_SCHEMA_VERSION = "phase8b.package-registry.v1"
JOURNAL_SCHEMA_VERSION = "phase8b.package-registry-journal.v1"
_HEX = re.compile(r"^[a-f0-9]{64}$")
_PACKAGE_ID = re.compile(r"^exness-xauusdm-\d{4}-\d{2}-[a-f0-9]{16}(?:-recovery-\d{4})?$")
_OPERATION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{7,95}$")
_LEGACY_RECOVERY_V1_ID = "exness-xauusdm-2024-12-a5cef8ab1fb1bce2-recovery-v1"
_LEGACY_RECOVERY_V1_DATASET_KEY = "exness:XAUUSDm:2024-12"
_LEGACY_RECOVERY_V1_RAW_SHA256 = "a5cef8ab1fb1bce26380113619c121da3062894b05b1c3d8de034c78bc8314fd"  # pragma: allowlist secret
_LEGACY_RECOVERY_V1_FORMAT = "phase8b.legacy-recovery-v1.literal"


class PackageStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    VERIFYING = "VERIFYING"
    VERIFIED_INACTIVE = "VERIFIED_INACTIVE"
    ACTIVE = "ACTIVE"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    INCOMPLETE = "INCOMPLETE"


_TRANSITIONS = {
    PackageStatus.CANDIDATE: {PackageStatus.VERIFYING, PackageStatus.QUARANTINED, PackageStatus.REJECTED, PackageStatus.INCOMPLETE},
    PackageStatus.VERIFYING: {PackageStatus.VERIFIED_INACTIVE, PackageStatus.QUARANTINED, PackageStatus.REJECTED, PackageStatus.INCOMPLETE},
    PackageStatus.VERIFIED_INACTIVE: {PackageStatus.ACTIVE, PackageStatus.QUARANTINED, PackageStatus.REJECTED},
    PackageStatus.ACTIVE: {PackageStatus.QUARANTINED},
    PackageStatus.QUARANTINED: set(),
    PackageStatus.REJECTED: set(),
    PackageStatus.INCOMPLETE: {PackageStatus.QUARANTINED, PackageStatus.REJECTED},
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_hash(value: object) -> str:
    payload = json.dumps(canonical_data(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _require_hash(value: object, name: str) -> str:
    text = str(value).lower()
    if not _HEX.fullmatch(text):
        raise AcquisitionError(f"PACKAGE_REGISTRY_{name}_INVALID")
    return text


def _safe_package_id(value: object) -> str:
    package_id = str(value)
    if not _PACKAGE_ID.fullmatch(package_id) or ".." in package_id or "/" in package_id or "\\" in package_id:
        raise AcquisitionError("PACKAGE_REGISTRY_PACKAGE_ID_INVALID")
    return package_id


def _safe_operation_id(value: object) -> str:
    operation_id = str(value)
    if not _OPERATION_ID.fullmatch(operation_id):
        raise AcquisitionError("PACKAGE_REGISTRY_OPERATION_ID_INVALID")
    return operation_id


def _validate_legacy_bootstrap_record(record: Mapping[str, object], registry: Mapping[str, object]) -> str:
    """Allow one historical literal only as quarantined bootstrap evidence."""
    package_id = str(record.get("package_id", ""))
    if (
        record.get("legacy_bootstrap") is not True
        or record.get("legacy_identity_format") != _LEGACY_RECOVERY_V1_FORMAT
        or package_id != _LEGACY_RECOVERY_V1_ID
        or registry.get("dataset_key") != _LEGACY_RECOVERY_V1_DATASET_KEY
        or registry.get("raw_archive_sha256") != _LEGACY_RECOVERY_V1_RAW_SHA256
        or record.get("base_dataset_key") != _LEGACY_RECOVERY_V1_DATASET_KEY
        or record.get("raw_archive_sha256") != _LEGACY_RECOVERY_V1_RAW_SHA256
        or record.get("package_path_identity") != _LEGACY_RECOVERY_V1_ID
        or int(record.get("generation", -1)) != 1
        or record.get("status") != PackageStatus.QUARANTINED.value
        or not str(record.get("status_reason", "")).strip()
    ):
        raise AcquisitionError("PACKAGE_REGISTRY_LEGACY_BOOTSTRAP_INVALID")
    return package_id


def _period(value: Mapping[str, object]) -> dict[str, str]:
    start, end = str(value.get("start_inclusive", "")), str(value.get("end_exclusive", ""))
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AcquisitionError("PACKAGE_REGISTRY_PERIOD_INVALID") from exc
    if start_dt.tzinfo is None or end_dt.tzinfo is None or start_dt.utcoffset() != timezone.utc.utcoffset(start_dt) or end_dt.utcoffset() != timezone.utc.utcoffset(end_dt) or start_dt >= end_dt:
        raise AcquisitionError("PACKAGE_REGISTRY_PERIOD_INVALID")
    return {"start_inclusive": start_dt.astimezone(UTC).isoformat().replace("+00:00", "Z"), "end_exclusive": end_dt.astimezone(UTC).isoformat().replace("+00:00", "Z")}


def _content_hash(registry: Mapping[str, object]) -> str:
    value = deepcopy(dict(registry))
    value.pop("last_transition_hash", None)
    return _json_hash(value)


def recovery_package_id(*, provider: str, symbol: str, period_slug: str, raw_archive_sha256: str, generation: int, writer_fingerprint: str) -> str:
    """Return the canonical non-overwriting identity for a recovery generation."""
    if provider != "exness" or symbol != "XAUUSDm" or not re.fullmatch(r"\d{4}-\d{2}", period_slug) or generation < 1 or not str(writer_fingerprint):
        raise AcquisitionError("PACKAGE_REGISTRY_RECOVERY_IDENTITY_INVALID")
    raw = _require_hash(raw_archive_sha256, "RAW_HASH")
    # The full identity is additionally bound in the registry record; the visible
    # prefix remains compatible with immutable normal monthly package names.
    _json_hash({"schema": REGISTRY_SCHEMA_VERSION, "writer": str(writer_fingerprint), "raw": raw, "generation": generation})
    return f"exness-xauusdm-{period_slug}-{raw[:16]}-recovery-{generation:04d}"


class PackageRegistryStore:
    """CAS-protected registry and hash-chained state-transition evidence."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.path = self.root / "package_registry.json"
        self.journal_path = self.root / "package_registry.journal.jsonl"
        self.lock_path = self.root / ".package_registry.lock"

    def create(self, *, dataset_key: str, provider: str, symbol: str, period: Mapping[str, object], raw_archive_sha256: str, code_fingerprint: str, generation_counter: int = 0) -> dict[str, object]:
        if not dataset_key or provider != "exness" or symbol != "XAUUSDm" or not str(code_fingerprint) or generation_counter < 0:
            raise AcquisitionError("PACKAGE_REGISTRY_IDENTITY_INVALID")
        registry = {
            "schema_version": REGISTRY_SCHEMA_VERSION, "dataset_key": str(dataset_key), "provider": provider, "symbol": symbol,
            "period": _period(period), "raw_archive_sha256": _require_hash(raw_archive_sha256, "RAW_HASH"),
            "revision": 0, "active_package_id": None, "generation_counter": int(generation_counter), "allocations": {}, "packages": [],
            "created_utc": _now(), "updated_utc": _now(), "last_transition_hash": None, "code_fingerprint": str(code_fingerprint),
        }
        with FileLock(str(self.lock_path), timeout=15):
            if self.path.exists() or self.journal_path.exists():
                raise AcquisitionError("PACKAGE_REGISTRY_ALREADY_EXISTS")
            self.root.mkdir(parents=True, exist_ok=True)
            self._write_atomic(self.path, registry, refuse_overwrite=True)
        return registry

    def bootstrap(self, spec: Mapping[str, object], *, reviewed_plan_hash: str, owner_confirmed: bool) -> dict[str, object]:
        """Install an explicit legacy description; it never discovers folders."""
        if not owner_confirmed:
            raise AcquisitionError("PACKAGE_REGISTRY_BOOTSTRAP_CONFIRMATION_REQUIRED")
        normalized = canonical_data(spec)
        if _json_hash(normalized) != _require_hash(reviewed_plan_hash, "BOOTSTRAP_PLAN_HASH"):
            raise AcquisitionError("PACKAGE_REGISTRY_BOOTSTRAP_PLAN_HASH_MISMATCH")
        required = {"dataset_key", "provider", "symbol", "period", "raw_archive_sha256", "code_fingerprint", "generation_counter", "packages", "active_package_id", "justification"}
        if not required.issubset(normalized) or not isinstance(normalized["packages"], list) or not str(normalized["justification"]).strip():
            raise AcquisitionError("PACKAGE_REGISTRY_BOOTSTRAP_SPEC_INVALID")
        self.create(dataset_key=str(normalized["dataset_key"]), provider=str(normalized["provider"]), symbol=str(normalized["symbol"]), period=normalized["period"], raw_archive_sha256=str(normalized["raw_archive_sha256"]), code_fingerprint=str(normalized["code_fingerprint"]), generation_counter=int(normalized["generation_counter"]))
        with FileLock(str(self.lock_path), timeout=15):
            before = self._load_locked()
            after = deepcopy(before)
            for source in normalized["packages"]:
                if not isinstance(source, dict):
                    raise AcquisitionError("PACKAGE_REGISTRY_BOOTSTRAP_RECORD_INVALID")
                record = deepcopy(source)
                if record.get("legacy_bootstrap") is True:
                    record["package_id"] = str(record.get("package_id", ""))
                else:
                    record["package_id"] = _safe_package_id(record.get("package_id"))
                record["base_dataset_key"] = before["dataset_key"]
                record["raw_archive_sha256"] = before["raw_archive_sha256"]
                record["package_path_identity"] = record["package_id"]
                PackageStatus(record.get("status"))
                for key, label in (("logical_canonical_sha256", "LOGICAL_HASH"), ("manifest_sha256", "MANIFEST_HASH"), ("completion_sha256", "COMPLETION_HASH")):
                    record[key] = _require_hash(record.get(key), label)
                record.setdefault("artifact_hashes", {"declared": record["logical_canonical_sha256"]})
                record.setdefault("recovery_reason", "LEGACY_BOOTSTRAP")
                record.setdefault("previous_package_id", None)
                record.setdefault("recovery_operation_id", "bootstrap-000")
                record.setdefault("creation_fingerprint", before["code_fingerprint"])
                record.setdefault("created_utc", _now()); record.setdefault("verified_utc", _now() if record["status"] in {"VERIFIED_INACTIVE", "ACTIVE"} else None); record.setdefault("transition_utc", _now()); record.setdefault("generation", 0)
                if record.get("legacy_bootstrap") is True:
                    _validate_legacy_bootstrap_record(record, after)
                after["packages"].append(record)
            active = [item["package_id"] for item in after["packages"] if item["status"] == PackageStatus.ACTIVE.value]
            if len(active) > 1: raise AcquisitionError("PACKAGE_REGISTRY_BOOTSTRAP_ACTIVE_AMBIGUOUS")
            declared_active = normalized["active_package_id"]
            if declared_active is not None: declared_active = _safe_package_id(declared_active)
            if (active[0] if active else None) != declared_active:
                raise AcquisitionError("PACKAGE_REGISTRY_BOOTSTRAP_ACTIVE_DECLARATION_MISMATCH")
            after["active_package_id"] = declared_active
            self._validate(after)
            self._commit_locked(before, after, package_id="BOOTSTRAP", old_status=None, new_status="BOOTSTRAPPED", reason="EXPLICIT_LEGACY_BOOTSTRAP", operation_id="bootstrap-000")
            return canonical_data(self._load_locked())

    def load(self) -> dict[str, object]:
        with FileLock(str(self.lock_path), timeout=15):
            return self._load_locked()

    def allocate_recovery(self, *, operation_id: str, reason: str, writer_fingerprint: str, package_root: Path | None = None, expected_revision: int | None = None) -> dict[str, object]:
        op = _safe_operation_id(operation_id)
        if not str(reason).strip() or not str(writer_fingerprint):
            raise AcquisitionError("PACKAGE_REGISTRY_RECOVERY_ALLOCATION_INVALID")
        with FileLock(str(self.lock_path), timeout=15):
            registry = self._load_locked()
            self._check_revision(registry, expected_revision)
            existing = registry["allocations"].get(op)
            if existing is not None:
                return canonical_data({"registry": registry, "allocation": existing, "idempotent": True})
            generation = int(registry["generation_counter"]) + 1
            period_slug = registry["period"]["start_inclusive"][:7]
            package_id = recovery_package_id(provider=str(registry["provider"]), symbol=str(registry["symbol"]), period_slug=period_slug, raw_archive_sha256=str(registry["raw_archive_sha256"]), generation=generation, writer_fingerprint=writer_fingerprint)
            if package_root is not None and (Path(package_root).resolve(strict=False) / package_id).exists():
                raise AcquisitionError("PACKAGE_REGISTRY_RECOVERY_DESTINATION_COLLISION")
            allocation = {"operation_id": op, "generation": generation, "package_id": package_id, "reason": str(reason), "writer_fingerprint": str(writer_fingerprint)}
            next_registry = deepcopy(registry)
            next_registry["generation_counter"] = generation
            next_registry["allocations"][op] = allocation
            self._commit_locked(registry, next_registry, package_id=package_id, old_status=None, new_status="ALLOCATED", reason="RECOVERY_GENERATION_ALLOCATED", operation_id=op)
            return canonical_data({"registry": self._load_locked(), "allocation": allocation, "idempotent": False})

    def allocated_destination(self, package_root: Path, *, operation_id: str) -> Path:
        """Return the only allowed unpublished destination for an allocation."""
        op = _safe_operation_id(operation_id)
        registry = self.load()
        allocation = registry["allocations"].get(op)
        if not allocation:
            raise AcquisitionError("PACKAGE_REGISTRY_ALLOCATION_NOT_FOUND")
        destination = Path(package_root).resolve(strict=False) / str(allocation["package_id"])
        if destination.exists():
            raise AcquisitionError("PACKAGE_REGISTRY_RECOVERY_DESTINATION_COLLISION")
        return destination

    def register_candidate(self, *, package_id: str, operation_id: str, recovery_reason: str, predecessor_package_id: str | None, artifact_hashes: Mapping[str, object], logical_canonical_sha256: str, manifest_sha256: str, completion_sha256: str, creation_fingerprint: str, expected_revision: int | None = None) -> dict[str, object]:
        package_id, op = _safe_package_id(package_id), _safe_operation_id(operation_id)
        with FileLock(str(self.lock_path), timeout=15):
            registry = self._load_locked(); self._check_revision(registry, expected_revision)
            allocation = registry["allocations"].get(op)
            if not allocation or allocation["package_id"] != package_id:
                raise AcquisitionError("PACKAGE_REGISTRY_UNALLOCATED_CANDIDATE")
            existing = self._package(registry, package_id, required=False)
            if existing:
                if existing.get("recovery_operation_id") == op:
                    return canonical_data(existing)
                raise AcquisitionError("PACKAGE_REGISTRY_PACKAGE_ID_COLLISION")
            safe_artifacts = {str(name): _require_hash(value, "ARTIFACT_HASH") for name, value in artifact_hashes.items()}
            if not safe_artifacts or not str(recovery_reason).strip() or not str(creation_fingerprint):
                raise AcquisitionError("PACKAGE_REGISTRY_CANDIDATE_INVALID")
            if predecessor_package_id is not None:
                try:
                    _safe_package_id(predecessor_package_id)
                except AcquisitionError:
                    predecessor = self._package(registry, str(predecessor_package_id), required=False)
                    if not predecessor or predecessor.get("legacy_bootstrap") is not True or predecessor.get("status") != PackageStatus.QUARANTINED.value:
                        raise
            record = {"package_id": package_id, "base_dataset_key": registry["dataset_key"], "generation": allocation["generation"], "recovery_reason": str(recovery_reason), "raw_archive_sha256": registry["raw_archive_sha256"], "artifact_hashes": safe_artifacts, "logical_canonical_sha256": _require_hash(logical_canonical_sha256, "LOGICAL_HASH"), "manifest_sha256": _require_hash(manifest_sha256, "MANIFEST_HASH"), "completion_sha256": _require_hash(completion_sha256, "COMPLETION_HASH"), "package_path_identity": package_id, "creation_fingerprint": str(creation_fingerprint), "status": PackageStatus.CANDIDATE.value, "status_reason": "RECOVERY_CANDIDATE_REGISTERED", "previous_package_id": predecessor_package_id, "recovery_operation_id": op, "created_utc": _now(), "verified_utc": None, "transition_utc": _now()}
            next_registry = deepcopy(registry); next_registry["packages"].append(record)
            self._commit_locked(registry, next_registry, package_id=package_id, old_status=None, new_status=record["status"], reason="CANDIDATE_REGISTERED", operation_id=op)
            return canonical_data(record)

    def transition(self, package_id: str, new_status: PackageStatus, *, reason: str, operation_id: str, expected_revision: int | None = None) -> dict[str, object]:
        package_id, op = _safe_package_id(package_id), _safe_operation_id(operation_id)
        if not str(reason).strip(): raise AcquisitionError("PACKAGE_REGISTRY_REASON_INVALID")
        with FileLock(str(self.lock_path), timeout=15):
            registry = self._load_locked(); self._check_revision(registry, expected_revision)
            current = self._package(registry, package_id)
            old = PackageStatus(current["status"])
            if new_status not in _TRANSITIONS[old]:
                raise AcquisitionError("PACKAGE_REGISTRY_ILLEGAL_TRANSITION")
            if new_status is PackageStatus.ACTIVE:
                raise AcquisitionError("PACKAGE_REGISTRY_USE_ACTIVATE")
            next_registry = deepcopy(registry); record = self._package(next_registry, package_id)
            record["status"], record["status_reason"], record["transition_utc"] = new_status.value, str(reason), _now()
            if new_status is PackageStatus.VERIFIED_INACTIVE: record["verified_utc"] = _now()
            self._commit_locked(registry, next_registry, package_id=package_id, old_status=old.value, new_status=new_status.value, reason=str(reason), operation_id=op)
            return canonical_data(self._package(self._load_locked(), package_id))

    def activate(self, package_id: str, *, operation_id: str, reason: str, expected_revision: int | None = None) -> dict[str, object]:
        package_id, op = _safe_package_id(package_id), _safe_operation_id(operation_id)
        with FileLock(str(self.lock_path), timeout=15):
            registry = self._load_locked(); self._check_revision(registry, expected_revision)
            target = self._package(registry, package_id)
            if target["status"] != PackageStatus.VERIFIED_INACTIVE.value:
                raise AcquisitionError("PACKAGE_REGISTRY_ACTIVATION_REQUIRES_VERIFIED_INACTIVE")
            next_registry = deepcopy(registry)
            prior = next_registry["active_package_id"]
            if prior:
                old_record = self._package(next_registry, prior)
                old_record.update({"status": PackageStatus.QUARANTINED.value, "status_reason": "SUPERSEDED_BY_ACTIVATION", "transition_utc": _now()})
            active = self._package(next_registry, package_id)
            active.update({"status": PackageStatus.ACTIVE.value, "status_reason": str(reason), "transition_utc": _now()})
            next_registry["active_package_id"] = package_id
            self._commit_locked(registry, next_registry, package_id=package_id, old_status=target["status"], new_status="ACTIVE", reason=str(reason), operation_id=op)
            return canonical_data(self._load_locked())

    def active_package(self, package_root: Path, *, expected_dataset_key: str, expected_raw_archive_sha256: str) -> tuple[Path, Mapping[str, object]]:
        registry = self.load()
        if registry["dataset_key"] != expected_dataset_key or registry["raw_archive_sha256"] != _require_hash(expected_raw_archive_sha256, "RAW_HASH"):
            raise AcquisitionError("PACKAGE_REGISTRY_DISCOVERY_IDENTITY_MISMATCH")
        active_id = registry["active_package_id"]
        if not active_id: raise AcquisitionError("PACKAGE_REGISTRY_NO_ACTIVE_PACKAGE")
        record = self._package(registry, active_id)
        if record["status"] != PackageStatus.ACTIVE.value: raise AcquisitionError("PACKAGE_REGISTRY_ACTIVE_STATE_CONTRADICTION")
        root = Path(package_root).resolve(strict=False) / active_id
        if not root.is_dir(): raise AcquisitionError("PACKAGE_REGISTRY_ACTIVE_PATH_MISSING")
        manifest, completion = root / "manifest.json", root / "package.complete.json"
        if not manifest.is_file() or not completion.is_file(): raise AcquisitionError("PACKAGE_REGISTRY_ACTIVE_MARKER_MISSING")
        if file_sha256(manifest) != record["manifest_sha256"] or file_sha256(completion) != record["completion_sha256"]:
            raise AcquisitionError("PACKAGE_REGISTRY_ACTIVE_IDENTITY_CHANGED")
        try:
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            completion_data = json.loads(completion.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AcquisitionError("PACKAGE_REGISTRY_ACTIVE_MARKER_INVALID") from exc
        if (
            manifest_data.get("package_id") != active_id
            or completion_data.get("package_id") != active_id
            or manifest_data.get("canonical_normalized_sha256") != record["logical_canonical_sha256"]
        ):
            raise AcquisitionError("PACKAGE_REGISTRY_ACTIVE_MANIFEST_IDENTITY_INVALID")
        for relative, expected_hash in record["artifact_hashes"].items():
            relative_path = Path(str(relative))
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise AcquisitionError("PACKAGE_REGISTRY_ARTIFACT_PATH_INVALID")
            artifact = (root / relative_path).resolve(strict=False)
            if root not in artifact.parents or not artifact.is_file() or file_sha256(artifact) != expected_hash:
                raise AcquisitionError("PACKAGE_REGISTRY_ACTIVE_ARTIFACT_IDENTITY_CHANGED")
        return root, canonical_data(record)

    def _load_locked(self) -> dict[str, object]:
        if not self.path.is_file(): raise AcquisitionError("PACKAGE_REGISTRY_MISSING")
        try: registry = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise AcquisitionError("PACKAGE_REGISTRY_CORRUPT") from exc
        self._validate(registry); self._validate_journal(registry)
        return registry

    def _validate(self, registry: Mapping[str, object]) -> None:
        if not isinstance(registry, dict) or registry.get("schema_version") != REGISTRY_SCHEMA_VERSION: raise AcquisitionError("PACKAGE_REGISTRY_SCHEMA_UNSUPPORTED")
        if registry.get("provider") != "exness" or registry.get("symbol") != "XAUUSDm" or not registry.get("dataset_key") or int(registry.get("revision", -1)) < 0: raise AcquisitionError("PACKAGE_REGISTRY_IDENTITY_INVALID")
        _period(registry.get("period", {})); _require_hash(registry.get("raw_archive_sha256"), "RAW_HASH")
        packages = registry.get("packages"); allocations = registry.get("allocations")
        if not isinstance(packages, list) or not isinstance(allocations, dict) or int(registry.get("generation_counter", -1)) < 0: raise AcquisitionError("PACKAGE_REGISTRY_STRUCTURE_INVALID")
        seen, active, generations = set(), [], set()
        for record in packages:
            if not isinstance(record, dict): raise AcquisitionError("PACKAGE_REGISTRY_RECORD_INVALID")
            package_id = (
                _validate_legacy_bootstrap_record(record, registry)
                if record.get("legacy_bootstrap") is True
                else _safe_package_id(record.get("package_id"))
            )
            if package_id in seen or record.get("base_dataset_key") != registry["dataset_key"] or record.get("raw_archive_sha256") != registry["raw_archive_sha256"]: raise AcquisitionError("PACKAGE_REGISTRY_RECORD_IDENTITY_INVALID")
            seen.add(package_id); status = PackageStatus(record.get("status"))
            if record.get("package_path_identity") != package_id: raise AcquisitionError("PACKAGE_REGISTRY_PATH_IDENTITY_INVALID")
            generation = int(record.get("generation", 0))
            if generation < 0 or (generation and generation in generations): raise AcquisitionError("PACKAGE_REGISTRY_DUPLICATE_GENERATION")
            if generation: generations.add(generation)
            _require_hash(record.get("logical_canonical_sha256"), "LOGICAL_HASH"); _require_hash(record.get("manifest_sha256"), "MANIFEST_HASH"); _require_hash(record.get("completion_sha256"), "COMPLETION_HASH")
            if status is PackageStatus.ACTIVE: active.append(package_id)
        if len(active) > 1 or (active and registry.get("active_package_id") != active[0]) or (not active and registry.get("active_package_id") is not None): raise AcquisitionError("PACKAGE_REGISTRY_ACTIVE_INVARIANT_VIOLATION")

    def _validate_journal(self, registry: Mapping[str, object]) -> None:
        if not self.journal_path.exists():
            if registry.get("revision") != 0 or registry.get("last_transition_hash") is not None: raise AcquisitionError("PACKAGE_REGISTRY_JOURNAL_MISSING")
            return
        previous, records = None, []
        try: lines = self.journal_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc: raise AcquisitionError("PACKAGE_REGISTRY_JOURNAL_CORRUPT") from exc
        for index, line in enumerate(lines, 1):
            try: record = json.loads(line); claimed = record.pop("record_sha256")
            except (TypeError, KeyError, json.JSONDecodeError): raise AcquisitionError("PACKAGE_REGISTRY_JOURNAL_CORRUPT") from None
            if record.get("schema_version") != JOURNAL_SCHEMA_VERSION or record.get("sequence") != index or record.get("previous_record_sha256") != previous or _json_hash(record) != claimed: raise AcquisitionError("PACKAGE_REGISTRY_JOURNAL_CORRUPT")
            record["record_sha256"] = claimed; previous = claimed; records.append(record)
        if int(registry["revision"]) != len(records) or registry.get("last_transition_hash") != previous or (records and records[-1].get("resulting_registry_hash") != _content_hash(registry)):
            raise AcquisitionError("PACKAGE_REGISTRY_JOURNAL_MISMATCH")

    def _commit_locked(self, before: Mapping[str, object], after: dict[str, object], *, package_id: str, old_status: str | None, new_status: str, reason: str, operation_id: str) -> None:
        after["revision"] = int(before["revision"]) + 1; after["updated_utc"] = _now(); after["last_transition_hash"] = None
        resulting_hash = _content_hash(after)
        records = 0 if not self.journal_path.exists() else len(self.journal_path.read_text(encoding="utf-8").splitlines())
        body = {"schema_version": JOURNAL_SCHEMA_VERSION, "sequence": records + 1, "previous_record_sha256": before.get("last_transition_hash"), "timestamp_utc": _now(), "registry_revision_before": before["revision"], "registry_revision_after": after["revision"], "dataset_key": before["dataset_key"], "package_id": package_id, "old_status": old_status, "new_status": new_status, "reason_code": reason, "operation_id": operation_id, "code_fingerprint": after["code_fingerprint"], "resulting_registry_hash": resulting_hash}
        body["record_sha256"] = _json_hash(body); line = json.dumps(canonical_data(body), sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        self.root.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(line); handle.flush(); os.fsync(handle.fileno())
        after["last_transition_hash"] = body["record_sha256"]
        self._write_atomic(self.path, after, refuse_overwrite=False)

    @staticmethod
    def _write_atomic(path: Path, value: object, *, refuse_overwrite: bool) -> None:
        if refuse_overwrite and path.exists(): raise FileExistsError(path.name)
        path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".partial")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                json.dump(canonical_data(value), handle, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally: Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def _check_revision(registry: Mapping[str, object], expected: int | None) -> None:
        if expected is not None and int(registry["revision"]) != int(expected): raise AcquisitionError("PACKAGE_REGISTRY_STALE_REVISION")

    @staticmethod
    def _package(registry: Mapping[str, object], package_id: str, *, required: bool = True) -> dict[str, object] | None:
        found = next((item for item in registry["packages"] if item["package_id"] == package_id), None)
        if found is None and required: raise AcquisitionError("PACKAGE_REGISTRY_PACKAGE_NOT_FOUND")
        return found
