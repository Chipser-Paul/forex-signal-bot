"""Phase 8A scientific-validation contracts and deterministic tooling."""

from .models import (
    AcceptanceOutcome,
    AcceptanceReport,
    CandidateRecord,
    DataStreamKind,
    DataStreamManifest,
    EmpiricalPackageManifest,
    FoldManifest,
    HoldoutIdentity,
    StudyPeriod,
    TradeSample,
    ValidationError,
    ValidationPlan,
    canonical_hash,
)

__all__ = [
    "AcceptanceOutcome",
    "AcceptanceReport",
    "CandidateRecord",
    "DataStreamKind",
    "DataStreamManifest",
    "EmpiricalPackageManifest",
    "FoldManifest",
    "HoldoutIdentity",
    "StudyPeriod",
    "TradeSample",
    "ValidationError",
    "ValidationPlan",
    "canonical_hash",
]
