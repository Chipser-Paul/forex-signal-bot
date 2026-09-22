"""Canonical scientific fingerprint infrastructure (Phase 8)."""

from bot.scientific.canonical_bytes import CONTRACT_ID, LEGACY_CONTRACT_ID
from bot.scientific.prospective_freeze import (
    PROSPECTIVE_CONTRACTS,
    ProspectiveFreezeIdentity,
    ProspectiveFreezeError,
    validate_prospective_contract,
)

__all__ = [
    "CONTRACT_ID",
    "LEGACY_CONTRACT_ID",
    "PROSPECTIVE_CONTRACTS",
    "ProspectiveFreezeIdentity",
    "ProspectiveFreezeError",
    "validate_prospective_contract",
]
