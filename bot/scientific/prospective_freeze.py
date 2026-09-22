"""Prospective scientific-freeze contract boundary.

Historical artifacts may verify under their declared legacy contract.
**New** scientific freeze/package identities must explicitly declare and use
an approved prospective canonical-byte contract (``canonical_git_blob_v1``)
and fail closed otherwise.

This module is the validation boundary that makes that invariant
expressible and enforceable:

* :func:`validate_prospective_contract` rejects a missing contract, the
  legacy contract (``legacy_worktree_bytes_v0``) and any unknown contract
  unless it has been explicitly registered/approved;
* :class:`ProspectiveFreezeIdentity` is the typed record a future V2 freeze
  publishes — it can only be constructed for an approved prospective
  contract, and there is **no default contract**: the caller must state
  which identity contract it is using;
* :func:`contract_record` renders the identity in the repository's
  provenance-record shape (contract id, digest algorithm, referenced commit,
  ordered input paths, digest) without binding any absolute local path or
  checkout configuration into the scientific identity.

Historical V1 artifacts are untouched: they are verified through
``bot.scientific.canonical_bytes.legacy_worktree_bytes_v0`` and the
historical-binding seams (e.g. ``pipeline_fingerprint_at_commit``) under
their original semantics, never reinterpreted as produced by
``canonical_git_blob_v1``.

Infrastructure only — no strategy, validation, execution, risk, fold,
scenario or acceptance semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from bot.scientific.canonical_bytes import (
    CONTRACT_ID,
    LEGACY_CONTRACT_ID,
    BlobSource,
    CanonicalByteError,
    canonical_framed_digest,
)

__all__ = [
    "PROSPECTIVE_CONTRACTS",
    "register_prospective_contract",
    "validate_prospective_contract",
    "ProspectiveFreezeIdentity",
    "contract_record",
    "ProspectiveFreezeError",
]


#: Contracts approved for **prospective** scientific freeze identity.
#: The legacy contract is deliberately absent: it remains available for
#: historical verification only and is rejected here.
PROSPECTIVE_CONTRACTS: tuple[str, ...] = (CONTRACT_ID,)

_EXTRA_PROSPECTIVE_CONTRACTS: set[str] = set()

_DIGEST_ALGORITHM = "sha256"


class ProspectiveFreezeError(RuntimeError):
    """Raised when a prospective freeze violates the contract boundary."""


def register_prospective_contract(contract_id: str) -> None:
    """Explicitly approve an additional *future* contract for prospective use.

    Deliberately explicit (never implicit, never a default): a contract not
    on the approved list is rejected by :func:`validate_prospective_contract`
    until it is registered here by an authorised, reviewed change.
    """
    if not isinstance(contract_id, str) or not contract_id:
        raise ProspectiveFreezeError("PROSPECTIVE_CONTRACT_ID_INVALID")
    if contract_id == LEGACY_CONTRACT_ID:
        raise ProspectiveFreezeError(
            "PROSPECTIVE_CONTRACT_LEGACY_FORBIDDEN: "
            f"{LEGACY_CONTRACT_ID} is historical-verification only"
        )
    _EXTRA_PROSPECTIVE_CONTRACTS.add(contract_id)


def validate_prospective_contract(contract_id: str | None) -> str:
    """Fail closed unless ``contract_id`` is an approved prospective contract.

    Rejected: ``None``/missing, empty, the legacy contract, and any unknown
    contract name that has not been explicitly registered/approved.
    Returns the validated contract id.
    """
    if contract_id is None:
        raise ProspectiveFreezeError(
            "PROSPECTIVE_CONTRACT_UNDECLARED: "
            "a prospective freeze must explicitly declare its contract; "
            "no default is selected"
        )
    if not isinstance(contract_id, str) or not contract_id:
        raise ProspectiveFreezeError("PROSPECTIVE_CONTRACT_ID_INVALID")
    if contract_id == LEGACY_CONTRACT_ID:
        raise ProspectiveFreezeError(
            "PROSPECTIVE_CONTRACT_REJECTED: "
            f"{LEGACY_CONTRACT_ID} may not be used for a prospective "
            "scientific freeze (historical verification only)"
        )
    if contract_id in PROSPECTIVE_CONTRACTS or contract_id in _EXTRA_PROSPECTIVE_CONTRACTS:
        return contract_id
    raise ProspectiveFreezeError(
        f"PROSPECTIVE_CONTRACT_UNKNOWN: {contract_id!r} is not an approved "
        "prospective contract; approved: "
        f"{sorted(PROSPECTIVE_CONTRACTS) + sorted(_EXTRA_PROSPECTIVE_CONTRACTS)}"
    )


@dataclass(frozen=True)
class ProspectiveFreezeIdentity:
    """Typed prospective freeze record (see repository provenance conventions).

    Shape: ``contract_id`` + ``digest_algorithm`` + referenced Git ``commit``
    + ordered input ``paths`` + resulting ``digest``.  It cannot carry an
    absolute local path or any checkout configuration — the fields simply do
    not exist, so checkout representation cannot enter scientific identity.
    """

    contract_id: str
    digest_algorithm: str
    commit: str
    paths: tuple[str, ...]
    digest: str

    def __post_init__(self) -> None:
        validate_prospective_contract(self.contract_id)
        if self.digest_algorithm != _DIGEST_ALGORITHM:
            raise ProspectiveFreezeError(
                f"PROSPECTIVE_DIGEST_ALGORITHM_UNSUPPORTED: {self.digest_algorithm!r}"
            )
        if not isinstance(self.commit, str) or not self.commit:
            raise ProspectiveFreezeError("PROSPECTIVE_COMMIT_INVALID")
        if not self.paths:
            raise ProspectiveFreezeError("PROSPECTIVE_PATHS_EMPTY")
        ordered = tuple(sorted(self.paths))
        if ordered != self.paths or len(set(self.paths)) != len(self.paths):
            raise ProspectiveFreezeError(
                "PROSPECTIVE_PATHS_MUST_BE_ORDERED_AND_UNIQUE"
            )
        if not isinstance(self.digest, str) or len(self.digest) != 64:
            raise ProspectiveFreezeError("PROSPECTIVE_DIGEST_INVALID")


def freeze_prospective_identity(
    paths: Sequence[str],
    *,
    contract_id: str,
    commit: str,
    repo: Path,
    blob_source: BlobSource | None = None,
) -> ProspectiveFreezeIdentity:
    """Compute and return the prospective freeze identity for ``paths``.

    The caller must pass ``contract_id`` explicitly — there is no default.
    Only approved prospective contracts are accepted; the legacy contract and
    unknown names fail closed (see :func:`validate_prospective_contract`).
    """
    approved = validate_prospective_contract(contract_id)
    try:
        digest = canonical_framed_digest(
            paths, commit=commit, repo=Path(repo), blob_source=blob_source
        )
    except CanonicalByteError as exc:
        raise ProspectiveFreezeError(f"PROSPECTIVE_FREEZE_INPUT_REJECTED: {exc}") from exc
    return ProspectiveFreezeIdentity(
        contract_id=approved,
        digest_algorithm=_DIGEST_ALGORITHM,
        commit=commit,
        paths=tuple(sorted(paths)),
        digest=digest,
    )


def contract_record(identity: ProspectiveFreezeIdentity) -> dict[str, object]:
    """Provenance-record view of a prospective freeze identity."""
    return {
        "contract_id": identity.contract_id,
        "digest_algorithm": identity.digest_algorithm,
        "commit": identity.commit,
        "paths": list(identity.paths),
        "digest": identity.digest,
        "legacy_compatible": False,
    }
