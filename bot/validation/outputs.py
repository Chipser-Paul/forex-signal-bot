from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import SYNTHETIC_LABEL, ValidationError, canonical_data, canonical_hash, canonical_json


REQUIRED_VALIDATION_OUTPUTS = (
    "validation_plan.json",
    "dataset_acceptance.json",
    "contamination_register.json",
    "split_manifest.json",
    "candidate_registry.jsonl",
    "walk_forward_results.json",
    "bootstrap_results.json",
    "stress_results.json",
    "sensitivity_results.json",
    "regime_results.json",
    "holdout_access.jsonl",
    "validation_summary.json",
    "VALIDATION_REPORT.md",
)


def _atomic_text(path: Path, content: str) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _json_lines(values: Sequence[Mapping[str, Any]]) -> str:
    return "".join(canonical_json(value) + "\n" for value in values)


@dataclass(frozen=True)
class ValidationArtifacts:
    validation_plan: Mapping[str, Any]
    dataset_acceptance: Mapping[str, Any]
    contamination_register: Mapping[str, Any]
    split_manifest: Mapping[str, Any]
    candidate_registry: tuple[Mapping[str, Any], ...]
    walk_forward_results: Mapping[str, Any]
    bootstrap_results: Mapping[str, Any]
    stress_results: Mapping[str, Any]
    sensitivity_results: Mapping[str, Any]
    regime_results: Mapping[str, Any]
    holdout_access: tuple[Mapping[str, Any], ...]
    validation_summary: Mapping[str, Any]


def write_validation_bundle(
    root: Path,
    study_id: str,
    artifacts: ValidationArtifacts,
    *,
    synthetic: bool,
    git_dirty: bool = False,
) -> Path:
    if not study_id or Path(study_id).name != study_id:
        raise ValidationError("study ID must be a safe directory name")
    destination = Path(root) / study_id
    if destination.exists():
        raise FileExistsError(f"validation result already exists: {destination}")
    if git_dirty and not synthetic:
        raise ValidationError("empirical validation output cannot be produced from a dirty tree")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=f".{study_id}.", suffix=".tmp"))
    summary = dict(artifacts.validation_summary)
    summary["synthetic"] = synthetic
    summary["result_label"] = SYNTHETIC_LABEL if synthetic else summary.get("result_label", "EMPIRICAL VALIDATION")
    summary["profitability_evidence"] = False if synthetic else bool(summary.get("profitability_evidence", False))
    summary["git_dirty"] = git_dirty
    required_summary = {
        "plan_hash", "dataset_hash", "strategy_fingerprint", "execution_fingerprint",
        "seed", "fidelity_class", "validation_status",
    }
    missing_summary = required_summary - set(summary)
    if missing_summary:
        raise ValidationError(f"validation summary is missing reproducibility fields: {sorted(missing_summary)}")
    if synthetic and summary.get("validation_status") == "PASS":
        raise ValidationError("synthetic output cannot claim validation PASS")
    payloads = {
        "validation_plan.json": artifacts.validation_plan,
        "dataset_acceptance.json": artifacts.dataset_acceptance,
        "contamination_register.json": artifacts.contamination_register,
        "split_manifest.json": artifacts.split_manifest,
        "walk_forward_results.json": artifacts.walk_forward_results,
        "bootstrap_results.json": artifacts.bootstrap_results,
        "stress_results.json": artifacts.stress_results,
        "sensitivity_results.json": artifacts.sensitivity_results,
        "regime_results.json": artifacts.regime_results,
        "validation_summary.json": summary,
    }
    try:
        for name, payload in payloads.items():
            _atomic_text(staging / name, json.dumps(canonical_data(payload), sort_keys=True, indent=2) + "\n")
        _atomic_text(staging / "candidate_registry.jsonl", _json_lines(artifacts.candidate_registry))
        _atomic_text(staging / "holdout_access.jsonl", _json_lines(artifacts.holdout_access))
        report = (
            "# Validation Report\n\n"
            f"**{summary['result_label']}**\n\n"
            "This artifact verifies framework mechanics only. It is not a profitability claim.\n"
        )
        _atomic_text(staging / "VALIDATION_REPORT.md", report)
        missing = [name for name in REQUIRED_VALIDATION_OUTPUTS if not (staging / name).is_file()]
        if missing:
            raise ValidationError(f"validation bundle is incomplete: {missing}")
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination


def normalized_validation_bundle_hash(path: Path) -> str:
    payload = {
        name: (Path(path) / name).read_text(encoding="utf-8")
        for name in REQUIRED_VALIDATION_OUTPUTS
    }
    return canonical_hash(payload)
