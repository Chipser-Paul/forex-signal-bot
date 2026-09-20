"""Phase 8E atomic external storage for evidence packages.

Owner-supplied evidence is validated offline, hashed, and published under a
new non-overwriting directory beneath the external Phase 8 data root:

    C:\\Users\\chips\\forex-signal-bot-data\\phase8\\evidence\\

Publication is atomic (temporary dir + fsync + rename) and non-overwriting:
an identical re-run recognizes the existing package and returns it
(idempotency); conflicting content under the same content-derived package id
fails closed. Absolute local paths are never used as cryptographic
identities — package IDs derive from content hashes. Source files supplied
by the owner are read, never modified.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from .evidence_contracts import canonical_hash, sha256_file

EVIDENCE_SCHEMA_VERSION = "phase8e.evidence-package.v1"


class EvidenceStoreError(RuntimeError):
    """Raised for storage/publishing failures (conflicts, tampering, IO)."""


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_bytes_durable(path: Path, payload: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def build_evidence_package(
    *,
    kind: str,
    content: Mapping[str, Any],
    source_path: Path | None,
) -> tuple[dict[str, Any], str]:
    """Wrap validated contract output into a publishable package envelope.

    Returns (package, package_id). The package id is content-derived; the
    manifest binds source-file and content hashes. ``kind`` is one of the
    intake categories (news, broker_metadata, commission, swap, slippage).
    """

    if kind not in {
        "news",
        "broker_metadata",
        "commission",
        "swap",
        "slippage",
        "official_news",
        "broker_support",
        "development_cost_policy",
        "cost_policy_activation",
        "dataset_acceptance_review",
        "broker_metadata_gap_policy",
        "metadata_gap_readiness",
        "broker_metadata_recovery",
        "metadata_recovery_readiness",
        "broker_metadata_unavailability",
        "development_metadata_bounds",
        "development_metadata_bounds_readiness",
        "development_evaluation_plan",
        "development_plan_disposition",
        "runner_compatibility",
        "observed_spread",
    }:
        raise EvidenceStoreError(f"unknown evidence package kind {kind!r}")
    content_hash = canonical_hash(dict(content))
    package_id = f"evidence-{kind}-v1-{content_hash[:16]}"
    manifest: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "package_id": package_id,
        "kind": kind,
        "classification": content.get("classification"),
        "content_schema_version": content.get("schema_version"),
        "content_canonical_sha256": content_hash,
    }
    if source_path is not None:
        manifest["source_file_name"] = source_path.name
        manifest["source_file_sha256"] = sha256_file(source_path)
    package = {
        "manifest": manifest,
        "content": dict(content),
    }
    return package, package_id


def publish_evidence_package(
    package: Mapping[str, Any],
    *,
    evidence_root: Path,
) -> tuple[Path, str]:
    """Atomically publish (or recognize) an evidence package.

    Idempotent: re-publishing byte-identical content returns the existing
    directory. Conflicting content under the same package id fails closed.
    """

    manifest = dict(package["manifest"])
    package_id = str(manifest["package_id"])
    evidence_root = Path(evidence_root)
    evidence_root.mkdir(parents=True, exist_ok=True)

    target = evidence_root / package_id
    expected_content_hash = str(manifest["content_canonical_sha256"])
    if target.exists():
        existing_manifest_path = target / "manifest.json"
        if not existing_manifest_path.is_file():
            raise EvidenceStoreError(
                f"existing evidence directory {package_id} lacks a manifest; refusing to touch it"
            )
        existing = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
        existing_hash = str(existing.get("content_canonical_sha256"))
        if existing_hash == expected_content_hash:
            return target, package_id
        raise EvidenceStoreError(
            "conflicting evidence package: identical id with different content — fail closed"
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix=".evidence-tmp-", dir=evidence_root))
    try:
        payload = json.dumps(package, indent=2, sort_keys=True).encode("utf-8")
        _write_bytes_durable(tmp_dir / "package.json", payload)
        manifest_payload = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        _write_bytes_durable(tmp_dir / "manifest.json", manifest_payload)
        manifest_digest = hashlib.sha256(manifest_payload).hexdigest()
        _write_bytes_durable(
            tmp_dir / "manifest.sha256",
            f"{manifest_digest}  manifest.json\n".encode("utf-8"),
        )
        _write_bytes_durable(
            tmp_dir / "PUBLISHED",
            json.dumps(
                {
                    "package_id": package_id,
                    "content_canonical_sha256": expected_content_hash,
                    "classification": manifest.get("classification"),
                },
                sort_keys=True,
            ).encode("utf-8"),
        )
        _fsync_dir(tmp_dir)
        try:
            os.rename(tmp_dir, target)
        except OSError:
            # Another writer won the race; re-check for idempotency/conflict.
            if target.exists():
                existing = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
                if str(existing.get("content_canonical_sha256")) == expected_content_hash:
                    return target, package_id
                raise EvidenceStoreError(
                    "conflicting evidence package raced with identical id"
                ) from None
            raise
        _fsync_dir(evidence_root)
        return target, package_id
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


def load_evidence_package(package_dir: Path) -> dict[str, Any]:
    """Load and hash-verify a published evidence package (tamper check).

    Verifies the standalone manifest file against its sidecar, binds the
    envelope's embedded manifest to that file, and re-hashes the content.
    """

    package_dir = Path(package_dir)
    manifest_path = package_dir / "manifest.json"
    package_path = package_dir / "package.json"
    if not manifest_path.is_file() or not package_path.is_file():
        raise EvidenceStoreError(
            f"evidence package {package_dir.name} is missing manifest.json or package.json"
        )
    manifest_bytes = manifest_path.read_bytes()
    sidecar = package_dir / "manifest.sha256"
    if sidecar.is_file():
        recorded = sidecar.read_text(encoding="utf-8").split()[0]
        if recorded != hashlib.sha256(manifest_bytes).hexdigest():
            raise EvidenceStoreError("evidence package manifest hash mismatch (tampering detected)")
    package = json.loads(package_path.read_bytes().decode("utf-8"))
    embedded = package.get("manifest")
    on_disk = json.loads(manifest_bytes.decode("utf-8"))
    if embedded != on_disk:
        raise EvidenceStoreError("evidence package envelope disagrees with its manifest file")
    content = package.get("content")
    actual = canonical_hash(content)
    if actual != str(on_disk.get("content_canonical_sha256")):
        raise EvidenceStoreError("evidence package content hash mismatch (tampering detected)")
    return package


# ---------------------------------------------------------------------------
# Intake orchestration
# ---------------------------------------------------------------------------

INTAKE_KINDS = {
    "news": "build_news_package",
    "broker_metadata": "build_broker_metadata_package",
    "commission": "build_commission_package",
    "swap": "build_swap_package",
    "slippage": "build_slippage_package",
}


def run_intake(
    kind: str,
    payload: Mapping[str, Any],
    *,
    source_path: Path | None,
    evidence_root: Path,
) -> tuple[Path, str, dict[str, Any]]:
    """Validate + publish one intake kind. Fail-closed end to end."""

    builder_name = INTAKE_KINDS.get(kind)
    if builder_name is None:
        raise EvidenceStoreError(f"unknown intake kind {kind!r}")
    from . import evidence_contracts as contracts

    builder: Callable[..., Mapping[str, Any]] = getattr(contracts, builder_name)
    if source_path is not None and payload.get("source_file_sha256") not in (None, ""):
        declared = str(payload["source_file_sha256"]).lower()
        actual = sha256_file(source_path)
        if declared != actual:
            raise EvidenceStoreError(
                f"declared source hash mismatch: {declared} != {actual} — fail closed"
            )
    if kind == "news":
        content = builder(
            payload["records"],
            provider=payload["provider"],
            retrieval_utc=payload["retrieval_utc"],
            licensing_declaration=payload["licensing_declaration"],
            source_file_sha256=sha256_file(source_path) if source_path else payload["source_file_sha256"],
            declared_coverage_start=payload.get("declared_coverage_start"),
            declared_coverage_end=payload.get("declared_coverage_end"),
        )
    else:
        content = builder(payload["records"])
    package, package_id = build_evidence_package(kind=kind, content=content, source_path=source_path)
    target, published_id = publish_evidence_package(package, evidence_root=Path(evidence_root))
    return target, published_id, dict(content)
