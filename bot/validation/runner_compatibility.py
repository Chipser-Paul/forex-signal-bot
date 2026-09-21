"""Phase 8N-I — runner/plan compatibility record (disposition branch B).

The Phase 8N-G fingerprint audit proved the corrected plan binds only the
shared replay contracts (``CODE_COMPONENTS``: adapter, reducer, levels,
consumption, restart, state migration, parity tests).  The runner module and
its control CLI are *execution-compatibility* surface, not plan-authorized
fingerprints, so the corrected plan remains byte-for-byte and a versioned
compatibility record binds it to the corrected runner instead:

    plan identity  <-  compatibility record  ->  corrected runner fingerprint

Publication is append-only and content-addressed through the existing Phase
8E evidence store (``runner_compatibility`` kind).  The record refuses to
publish against the invalidated plan and pins the empirical-source contract,
tests and code commit so any later runner change requires a new record.

No strategy evaluation, MT5, network, account or trading operation occurs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from bot.acquisition.evidence_contracts import canonical_hash
from bot.acquisition.evidence_store import (
    build_evidence_package,
    publish_evidence_package,
)

UTC = timezone.utc

COMPAT_SCHEMA = "phase8n.runner-compatibility.v1"
COMPAT_CLASSIFICATION = "DEVELOPMENT_EXECUTION_COMPATIBILITY_NOT_PLAN_REVISION"
COMPAT_KIND = "runner_compatibility"

RUNNER_COMPATIBILITY_FILES = (
    "bot/validation/development_evaluation_runner.py",
    "backtests/development_evaluation_control.py",
    "bot/validation/empirical_input_pipeline.py",
)

EMPIRICAL_SOURCE_CONTRACT = "phase8n.plan-bound-empirical-inputs.v1"


class CompatibilityRecordError(RuntimeError):
    """Raised on any invalid or conflicting compatibility publication."""


def runner_fingerprint(worktree: Path) -> dict[str, str]:
    """UTF8-text canonical LF SHA-256 over the runner source files.

    Mirrors the ``implementation_hash_encoding`` of the plan's
    orchestration contract (``UTF8_TEXT_CANONICAL_LF_SHA256``).
    """
    files: dict[str, str] = {}
    for relative in RUNNER_COMPATIBILITY_FILES:
        path = Path(worktree) / relative
        if not path.is_file():
            raise CompatibilityRecordError(f"runner source file is missing: {relative}")
        files[relative] = hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
    return {
        "encoding": "UTF8_TEXT_CANONICAL_LF_SHA256",
        "fingerprint": canonical_hash(files),
        "files": files,
    }


def build_compatibility_record(
    *,
    plan_package_id: str,
    plan_fingerprint: str,
    invalidated_plan_package_id: str,
    invalidated_plan_fingerprint: str,
    worktree: Path,
    code_commit: str,
    runner_schema: str,
    runner_version: str,
    test_node_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Build the branch-B compatibility record content."""
    if plan_package_id == invalidated_plan_package_id:
        raise CompatibilityRecordError("the invalidated plan must never be accepted")
    if code_commit == "" or len(code_commit) != 40:
        raise CompatibilityRecordError("compatibility record requires the exact code commit")
    if not test_node_ids:
        raise CompatibilityRecordError("compatibility record requires its test node ids")
    identity = runner_fingerprint(worktree)
    return {
        "schema_version": COMPAT_SCHEMA,
        "classification": COMPAT_CLASSIFICATION,
        "label": "runner execution-compatibility binding; plan byte-for-byte preserved",
        "plan_binding": {
            "package_id": plan_package_id,
            "plan_fingerprint": plan_fingerprint,
            "preserved": True,
            "republished": False,
        },
        "invalidated_plan_never_accepted": {
            "package_id": invalidated_plan_package_id,
            "fingerprint": invalidated_plan_fingerprint,
        },
        "runner_binding": {
            **identity,
            "schema": runner_schema,
            "version": runner_version,
            "empirical_source_contract": EMPIRICAL_SOURCE_CONTRACT,
            "empirical_inputs": "PLAN_AND_EVIDENCE_REGISTRY_ONLY",
            "synthetic_stream_injection": "REJECTED_FOR_EMPIRICAL_COMMANDS",
            "synthetic_rehearsal": "FIXTURE_BACKED_BINDINGS_THROUGH_SAME_PIPELINE_INTERFACE",
        },
        "verification": {
            "code_commit": code_commit,
            "test_node_ids": list(test_node_ids),
            "structural_canary_label": (
                "EMPIRICAL PIPELINE STRUCTURAL CANARY — NOT STRATEGY EVIDENCE"
            ),
        },
        "gates": {
            "empirical_strategy_evaluation_executed": False,
            "holdout_access_authorized": False,
            "accepted_for_final_validation": False,
            "phase9_authorized": False,
        },
        "recorded_at_utc": datetime.now(UTC).isoformat(),
    }


def verify_compatibility_record(content: Mapping[str, Any], *, worktree: Path) -> dict[str, Any]:
    """Recompute every binding; raise on drift, tampering or invalidation."""
    if content.get("schema_version") != COMPAT_SCHEMA:
        raise CompatibilityRecordError("compatibility record schema mismatch")
    if content.get("classification") != COMPAT_CLASSIFICATION:
        raise CompatibilityRecordError("compatibility record classification invalid")
    plan = content.get("plan_binding", {})
    if plan.get("preserved") is not True or plan.get("republished") is not False:
        raise CompatibilityRecordError("compatibility record must preserve the plan byte-for-byte")
    invalidated = content.get("invalidated_plan_never_accepted", {})
    if invalidated.get("package_id") == plan.get("package_id"):
        raise CompatibilityRecordError("compatibility record binds the invalidated plan")
    runner = content.get("runner_binding", {})
    current = runner_fingerprint(worktree)
    if runner.get("fingerprint") != current["fingerprint"]:
        raise CompatibilityRecordError(
            "runner fingerprint drifted from the compatibility record; a new record is required"
        )
    if runner.get("files") != current["files"]:
        raise CompatibilityRecordError("runner source files drifted from the compatibility record")
    if runner.get("empirical_inputs") != "PLAN_AND_EVIDENCE_REGISTRY_ONLY":
        raise CompatibilityRecordError("empirical input contract missing from the record")
    if runner.get("synthetic_stream_injection") != "REJECTED_FOR_EMPIRICAL_COMMANDS":
        raise CompatibilityRecordError("synthetic-stream rejection is not recorded")
    gates = content.get("gates", {})
    for gate in ("empirical_strategy_evaluation_executed", "holdout_access_authorized",
                 "accepted_for_final_validation", "phase9_authorized"):
        if gates.get(gate) is not False:
            raise CompatibilityRecordError(f"gate {gate} must remain false")
    if not content.get("verification", {}).get("test_node_ids"):
        raise CompatibilityRecordError("record verification lacks its test node ids")
    return {"verified": True, "runner_fingerprint": current["fingerprint"]}


def publish_compatibility_record(
    *, evidence_root: Path, content: Mapping[str, Any]
) -> tuple[Path, str]:
    """Append-only, content-addressed publication through the Phase 8E store."""
    package, package_id = build_evidence_package(
        kind=COMPAT_KIND, content=dict(content), source_path=None
    )
    published, published_id = publish_evidence_package(package, evidence_root=Path(evidence_root))
    if published_id != package_id:
        raise CompatibilityRecordError("published package id does not match the built record")
    # Deterministic readback: re-load and re-verify against the worktree.
    loaded = json.loads((published / "package.json").read_text(encoding="utf-8"))
    if loaded.get("content", {}).get("schema_version") != COMPAT_SCHEMA:
        raise CompatibilityRecordError("compatibility readback schema mismatch")
    return published, published_id


def load_compatibility_record(evidence_root: Path) -> dict[str, Any]:
    """Load the latest published compatibility record (latest by recorded_at)."""
    root = Path(evidence_root)
    latest: dict[str, Any] | None = None
    latest_key: str = ""
    for package_dir in sorted(root.glob("evidence-runner_compatibility-v1-*")):
        package_path = package_dir / "package.json"
        if not package_path.is_file():
            continue
        content = json.loads(package_path.read_text(encoding="utf-8")).get("content", {})
        if content.get("schema_version") != COMPAT_SCHEMA:
            continue
        recorded = str(content.get("recorded_at_utc", ""))
        if recorded >= latest_key:
            latest_key = recorded
            latest = content
    if latest is None:
        raise CompatibilityRecordError("no compatibility record is published")
    return latest
