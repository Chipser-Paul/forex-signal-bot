"""Phase 8 canonical scientific fingerprint contract.

Versioned, checkout-independent canonical-byte representation for
fingerprinting Git-tracked scientific source/configuration.

Why this exists
---------------
Historical fingerprints hashed **working-tree bytes**.  On Windows a checkout
performed with ``core.autocrlf=true`` materialises LF-in-repository text as
CRLF in the working tree, so semantically identical committed content produced
different fingerprints depending only on the user's Git configuration.  This
was recorded as
``REPRODUCIBILITY_ENGINEERING_DEBT — MUST BE RESOLVED BEFORE V2 SCIENTIFIC
FREEZE`` in ``docs/PHASE8_FEASIBILITY_DISPOSITION_V1.md``.  This module
implements the prospective contract that resolves that debt.

The authoritative byte representation is the **committed Git blob** — the
object actually stored in the repository at a given commit — never the bytes
that a particular checkout happens to materialise in the working tree.  Two
checkouts of the same commit therefore always agree, whatever their
``core.autocrlf`` setting or physical line endings are.

Contract identity
-----------------
``canonical_git_blob_v1``

Digest framing (unambiguous, order-independent, length-prefixed)::

    sha256(
        framed(b"canonical-git-blob-v1")
        || framed(str(len(paths)) as ASCII)
        || for each path in ascending lexicographic order:
               framed(path UTF-8) || framed(blob bytes)
    )

where ``framed(x) = 8-byte big-endian byte-length || x``.  Length framing
removes concatenation ambiguity; ascending path order removes enumeration
dependence; missing or malformed inputs fail closed.

Legacy fingerprints keep their original semantics and remain historical
evidence; they are classified ``legacy_worktree_bytes_v0`` and are verified
through the explicit compatibility adapter below, never reinterpreted as
produced by this contract.

Working-tree verification is a **separate concept** (see
:func:`working_tree_canonical_agreement`): the canonical identity is derived
from Git object storage, while a distinct check may ask whether a checkout
differs from its commit only by Git's newline-materialisation policy.

Blob sourcing
-------------
The production blob source resolves committed bytes with real Git plumbing
(``git ls-tree`` + ``git cat-file blob``), mirroring the repository's
established convention (``bot.acquisition.candle_discovery.code_fingerprint``).
The source is injectable so tests can exercise the full contract against a
genuine Git object database without launching processes (the repository's
test firewall prohibits subprocess launches inside the suite; the pure-Python
source reads and writes real zlib-compressed Git objects in the same on-disk
format that ``git cat-file`` and ``git fsck`` consume).

This module is infrastructure only.  It changes no strategy, validation,
execution, risk, fold, scenario or acceptance semantics.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Callable, Sequence

__all__ = [
    "CONTRACT_ID",
    "LEGACY_CONTRACT_ID",
    "CanonicalByteError",
    "BlobSource",
    "make_git_blob_source",
    "canonical_blob_bytes",
    "canonical_file_digest",
    "canonical_framed_digest",
    "legacy_worktree_bytes_v0",
    "working_tree_canonical_agreement",
]


CONTRACT_ID = "canonical_git_blob_v1"
CONTRACT_TAG = b"canonical-git-blob-v1"
LEGACY_CONTRACT_ID = "legacy_worktree_bytes_v0"

#: Permitted Git blob modes: regular executable and non-executable files.
#: Symlinks (120000), gitlinks/submodules (160000), directories (040000) and
#: any other mode fail closed — a scientific fingerprint is defined only for
#: regular tracked files.
_BLOB_MODES = {"100644", "100755"}


class CanonicalByteError(RuntimeError):
    """Raised on any canonical-byte contract violation.  Always fail-closed."""


#: Signature of a blob source: ``(commit, repository_relative_path) -> bytes``.
#: Implementations must fail closed (raise :class:`CanonicalByteError` or any
#: exception) for missing, non-blob or symlink entries.
BlobSource = Callable[[str, str], bytes]


# ---------------------------------------------------------------------------
# Framing primitives
# ---------------------------------------------------------------------------


def _framed(component: bytes) -> bytes:
    """8-byte big-endian length prefix plus the component bytes.

    Length framing makes the framed stream unambiguous: no two distinct
    component sequences can produce the same concatenation.
    """
    return len(component).to_bytes(8, "big") + component


def _validate_commit(commit: str) -> None:
    if not isinstance(commit, str) or len(commit) != 40 or any(
        char not in "0123456789abcdef" for char in commit
    ):
        raise CanonicalByteError(f"CANONICAL_COMMIT_IDENTITY_INVALID: {commit!r}")


def _validate_relative_path(relative: str) -> None:
    if (
        not isinstance(relative, str)
        or not relative
        or relative.startswith("/")
        or "\\" in relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise CanonicalByteError(f"CANONICAL_PATH_INVALID: {relative!r}")


def _ordered_unique(paths: Sequence[str]) -> tuple[str, ...]:
    ordered = tuple(sorted(paths))
    if len(set(ordered)) != len(ordered):
        raise CanonicalByteError("CANONICAL_DUPLICATE_PATH")
    if not ordered:
        raise CanonicalByteError("CANONICAL_INPUT_EMPTY")
    for relative in ordered:
        _validate_relative_path(relative)
    return ordered


# ---------------------------------------------------------------------------
# Production blob source — real Git plumbing (matches repo convention)
# ---------------------------------------------------------------------------


def make_git_blob_source(repo: Path) -> BlobSource:
    """Blob source resolving committed bytes via ``git ls-tree``/``cat-file``.

    Uses the object database, not the working tree, so results are independent
    of any checkout configuration.  Rejects missing paths, directories,
    symlinks, submodules and any other non-regular-file entry (fail closed).
    """
    repo_path = Path(repo)

    def source(commit: str, relative: str) -> bytes:
        _validate_commit(commit)
        _validate_relative_path(relative)
        try:
            listing = subprocess.check_output(
                ["git", "ls-tree", commit, "--", relative],
                cwd=str(repo_path),
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CanonicalByteError(
                f"CANONICAL_BLOB_UNAVAILABLE: {relative} at {commit[:12]}"
            ) from exc
        entries = [line for line in listing.decode("utf-8", "surrogateescape").split("\n") if line]
        if len(entries) != 1:
            raise CanonicalByteError(
                f"CANONICAL_BLOB_UNAVAILABLE: {relative} at {commit[:12]}"
            )
        mode, _obj_type, object_sha = entries[0].split()[:3]
        if mode not in _BLOB_MODES:
            raise CanonicalByteError(
                f"CANONICAL_UNEXPECTED_FILE_TYPE: {relative} mode {mode}"
            )
        try:
            return subprocess.check_output(
                ["git", "cat-file", "blob", object_sha],
                cwd=str(repo_path),
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CanonicalByteError(
                f"CANONICAL_BLOB_UNAVAILABLE: {relative} at {commit[:12]}"
            ) from exc

    return source


# ---------------------------------------------------------------------------
# canonical_git_blob_v1 — committed blob representation
# ---------------------------------------------------------------------------


def canonical_blob_bytes(
    relative_path: str,
    *,
    commit: str,
    repo: Path,
    blob_source: BlobSource | None = None,
) -> bytes:
    """Canonical byte representation of a tracked file under the v1 contract.

    The canonical representation of a committed file **is** its committed blob
    content — byte-for-byte as stored in the Git object database.  No newline
    transformation, encoding conversion or normalisation of any kind is
    applied.  Binary files therefore pass through unchanged and
    deterministically.  ``blob_source`` may inject an alternative committed-
    byte reader (tests use a pure-Python Git object-database reader); the
    default resolves through real Git plumbing.
    """
    _validate_commit(commit)
    _validate_relative_path(relative_path)
    source = blob_source if blob_source is not None else make_git_blob_source(Path(repo))
    return source(commit, relative_path)


def canonical_file_digest(
    relative_path: str,
    *,
    commit: str,
    repo: Path,
    blob_source: BlobSource | None = None,
) -> str:
    """SHA-256 of the canonical blob bytes of a single tracked file."""
    blob = canonical_blob_bytes(
        relative_path, commit=commit, repo=Path(repo), blob_source=blob_source
    )
    return hashlib.sha256(blob).hexdigest()


def canonical_framed_digest(
    paths: Sequence[str],
    *,
    commit: str,
    repo: Path,
    blob_source: BlobSource | None = None,
) -> str:
    """Deterministic framed digest over multiple tracked files.

    See the module docstring for the exact framing.  Determinism properties:
    ascending lexicographic path ordering removes filesystem and argument
    order dependence; per-component length framing removes concatenation
    ambiguity; missing or malformed inputs fail closed; an empty *file* is a
    valid zero-length blob and digests deterministically; files without a
    final newline and files with Unicode content are deterministic; binary
    content is never newline-normalised.
    """
    source = blob_source if blob_source is not None else make_git_blob_source(Path(repo))
    ordered = _ordered_unique(paths)
    digest = hashlib.sha256()
    digest.update(_framed(CONTRACT_TAG))
    digest.update(_framed(str(len(ordered)).encode("ascii")))
    for relative in ordered:
        blob = source(commit, relative)
        digest.update(_framed(relative.encode("utf-8")))
        digest.update(_framed(blob))
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# legacy_worktree_bytes_v0 — explicit compatibility adapter
# ---------------------------------------------------------------------------


def legacy_worktree_bytes_v0(path: Path, *, normalize_crlf: bool = False) -> bytes:
    """Historical byte representation, for legacy verification only.

    ``normalize_crlf=False`` reproduces the raw-working-tree semantics used by
    ``pipeline_fingerprint`` and ``execution_model_fingerprint`` (the exact
    behaviour that produced the V1 debt).  ``normalize_crlf=True`` reproduces
    the ``UTF8_TEXT_CANONICAL_LF_SHA256`` semantics used by the runner
    compatibility record and the plan-revision component fingerprints.

    Never use this representation for new scientific freeze identities.
    """
    data = Path(path).read_bytes()
    if normalize_crlf:
        data = data.replace(b"\r\n", b"\n")
    return data


# ---------------------------------------------------------------------------
# Working-tree verification (a distinct concept — see module docstring)
# ---------------------------------------------------------------------------


def working_tree_canonical_agreement(
    relative_path: str,
    *,
    commit: str,
    repo: Path,
    blob_source: BlobSource | None = None,
) -> bool:
    """Working-tree integrity check: does the checkout match the commit?

    Compares the working-tree file against the **committed blob** under
    explicit semantics:

    * if the committed blob contains CRLF sequences, the checkout must match
      byte-for-byte (checkout policy could only have produced CRLF there);
    * otherwise the working-tree bytes with CRLF sequences normalised to LF
      must equal the blob — an unchanged checkout whose text Git materialised
      with CRLF agrees, while any real content change (edited source, added or
      removed lines, whitespace beyond newline materialisation, a lone CR)
      fails closed.

    This is deliberately NOT the scientific fingerprint: the canonical
    identity always comes from Git object storage.  A missing working-tree
    file propagates the underlying read error (fail closed).
    """
    _validate_commit(commit)
    _validate_relative_path(relative_path)
    repo_path = Path(repo)
    committed = canonical_blob_bytes(
        relative_path, commit=commit, repo=repo_path, blob_source=blob_source
    )
    working = (repo_path / relative_path).read_bytes()
    if b"\r\n" in committed:
        return working == committed
    return working.replace(b"\r\n", b"\n") == committed
