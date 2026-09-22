"""Phase 8 canonical-byte fingerprint contract tests.

Infrastructure verification only — no strategy, validation, fold, scenario,
cost or acceptance semantics are exercised.

Test architecture note
----------------------
The repository test firewall (``tests/conftest.py``) prohibits subprocess
launches inside the suite, so these tests cannot shell out to ``git``.
Instead they exercise the contract against **genuine Git object databases**:
the :class:`GitObjectStore` helper below writes real zlib-compressed loose
objects (blobs, trees, commits) in the exact on-disk format ``git cat-file``
and ``git fsck`` consume — the standalone verification battery runs the
production ``git`` plumbing path and the full autocrlf clone matrix outside
the suite and records the results in the contract documentation.

Covers:

* ``canonical_git_blob_v1`` determinism across LF / CRLF working-tree
  materialisations (the checkout-independent property);
* the V1 regression: legacy ``legacy_worktree_bytes_v0`` diverges across
  checkout newline representations where the canonical contract stays stable;
* deterministic framing (ordering, ambiguity-free length prefixes) and every
  fail-closed case (missing/duplicate/invalid paths, empty manifest,
  directories, symlinks, invalid commit identity);
* working-tree integrity semantics (checkout-only newline transformation
  accepted; any real content change fails);
* the migration adapters' seam and framing (legacy framing over committed
  blob bytes);
* supervisory requirement A: commit identity is independent of dirty
  working-tree bytes (checkout representation, uncommitted edits, committed
  revisions);
* supervisory requirement B: prospective freezes fail closed on legacy or
  undeclared contracts while historical V1 verification is retained.
"""

from __future__ import annotations

import hashlib
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from bot.scientific.canonical_bytes import (
    CONTRACT_ID,
    CanonicalByteError,
    canonical_blob_bytes,
    canonical_file_digest,
    canonical_framed_digest,
    legacy_worktree_bytes_v0,
    working_tree_canonical_agreement,
)

# ---------------------------------------------------------------------------
# Genuine Git object database, built in pure Python (loose-object format)
# ---------------------------------------------------------------------------


class GitObjectStore:
    """Writes and reads real Git loose objects in a real ``.git`` layout.

    Objects are stored exactly as Git stores them:
    ``zlib.compress(b"<type> <byte-length>\\x00<content>)`` under
    ``.git/objects/<2-hex>/<38-hex>``.  The resulting directory is a valid
    Git repository (verifiable with ``git fsck`` outside the test suite).
    """

    def __init__(self, root: Path, *, author: str = "Scientific Verification") -> None:
        self.root = root
        self.objects_dir = root / ".git" / "objects"
        self.author = author
        (self.objects_dir).mkdir(parents=True, exist_ok=True)
        (root / ".git" / "refs" / "heads").mkdir(parents=True, exist_ok=True)
        (root / ".git" / "HEAD").write_bytes(b"ref: refs/heads/main\n")

    # -- object writing ----------------------------------------------------

    def _hash_object(self, obj_type: str, content: bytes) -> str:
        header = f"{obj_type} {len(content)}".encode("ascii") + b"\x00"
        store = header + content
        sha = hashlib.sha1(store).hexdigest()
        obj_dir = self.objects_dir / sha[:2]
        obj_dir.mkdir(exist_ok=True)
        obj_path = obj_dir / sha[2:]
        if not obj_path.exists():
            obj_path.write_bytes(zlib.compress(store))
        return sha

    def add_blob(self, data: bytes) -> str:
        return self._hash_object("blob", data)

    def write_tree(self, entries: dict[str, tuple[str, str]]) -> str:
        """``entries`` maps name -> (git-mode, object-sha).  Git-sorted."""
        def sort_key(name: str) -> bytes:
            mode = entries[name][0]
            # directories compare as if suffixed with '/'
            suffix = b"/" if mode == "40000" else b""
            return name.encode("utf-8") + suffix

        payload = b""
        for name in sorted(entries, key=sort_key):
            mode, sha = entries[name]
            payload += (
                mode.encode("ascii")
                + b" "
                + name.encode("utf-8")
                + b"\x00"
                + bytes.fromhex(sha)
            )
        return self._hash_object("tree", payload)

    def commit_tree(self, tree_sha: str, message: str, *, timestamp: int = 1700000000) -> str:
        ident = f"{self.author} <scientific@example.invalid> {timestamp} +0000"
        content = (
            f"tree {tree_sha}\n"
            f"author {ident}\n"
            f"committer {ident}\n\n"
            f"{message}\n"
        ).encode("utf-8")
        sha = self._hash_object("commit", content)
        (self.root / ".git" / "refs" / "heads" / "main").write_bytes(sha.encode("ascii") + b"\n")
        return sha

    def commit_files(self, files: dict[str, bytes], message: str) -> str:
        """Write a set of blobs, build the full nested tree, and commit it."""
        # Build nested trees recursively.
        files_all = set(files)
        blobs = {name: self.add_blob(data) for name, data in files.items()}

        def build_tree(prefix: str) -> str:
            if prefix:
                rest = prefix + "/"
                names = {
                    path[len(rest):].split("/", 1)[0]
                    for path in files_all
                    if path.startswith(rest)
                }
            else:
                names = {path.split("/", 1)[0] for path in files_all}
            entries: dict[str, tuple[str, str]] = {}
            for name in sorted(names):
                full = f"{prefix}/{name}" if prefix else name
                if any(other.startswith(full + "/") for other in files_all):
                    entries[name] = ("40000", build_tree(full))
                else:
                    entries[name] = ("100644", blobs[full])
            return self.write_tree(entries)

        tree_sha = build_tree("")
        return self.commit_tree(tree_sha, message)

    # -- object reading ----------------------------------------------------

    def _read_object(self, sha: str) -> tuple[str, bytes]:
        path = self.objects_dir / sha[:2] / sha[2:]
        raw = zlib.decompress(path.read_bytes())
        header, _, content = raw.partition(b"\x00")
        obj_type = header.split(b" ")[0].decode("ascii")
        return obj_type, content

    def _root_tree(self, commit: str) -> str:
        try:
            obj_type, content = self._read_object(commit)
        except FileNotFoundError as exc:
            raise CanonicalByteError(
                f"CANONICAL_COMMIT_IDENTITY_INVALID: {commit!r}"
            ) from exc
        if obj_type != "commit":
            raise CanonicalByteError(
                f"CANONICAL_COMMIT_IDENTITY_INVALID: {commit!r}"
            )
        for line in content.decode("ascii").splitlines():
            if line.startswith("tree "):
                return line.split()[1]
        raise CanonicalByteError(f"CANONICAL_COMMIT_IDENTITY_INVALID: {commit!r}")

    def _read_tree(self, sha: str) -> dict[str, tuple[str, str]]:
        obj_type, content = self._read_object(sha)
        if obj_type != "tree":
            raise CanonicalByteError("CANONICAL_BLOB_UNAVAILABLE: malformed tree")
        entries: dict[str, tuple[str, str]] = {}
        while content:
            mode_end = content.index(b" ")
            name_start = mode_end + 1
            name_end = content.index(b"\x00", name_start)
            mode = content[:mode_end].decode("ascii")
            name = content[name_start:name_end].decode("utf-8")
            entry_sha = content[name_end + 1 : name_end + 21].hex()
            entries[name] = (mode, entry_sha)
            content = content[name_end + 21 :]
        return entries

    def blob_bytes(self, commit: str, relative: str) -> bytes:
        """Production-mirroring resolver: fail closed on every non-blob entry."""
        if not isinstance(commit, str) or len(commit) != 40 or any(
            ch not in "0123456789abcdef" for ch in commit
        ):
            raise CanonicalByteError(f"CANONICAL_COMMIT_IDENTITY_INVALID: {commit!r}")
        if (
            not isinstance(relative, str)
            or not relative
            or relative.startswith("/")
            or "\\" in relative
            or ".." in relative.split("/")
        ):
            raise CanonicalByteError(f"CANONICAL_PATH_INVALID: {relative!r}")
        parts = relative.split("/")
        sha = self._root_tree(commit)
        mode = "40000"
        for depth, part in enumerate(parts):
            entries = self._read_tree(sha)
            if part not in entries:
                raise CanonicalByteError(
                    f"CANONICAL_BLOB_UNAVAILABLE: {relative} at {commit[:12]}"
                )
            mode, sha = entries[part]
            if depth < len(parts) - 1 and mode != "40000":
                raise CanonicalByteError(
                    f"CANONICAL_BLOB_UNAVAILABLE: {relative} at {commit[:12]}"
                )
        if mode == "40000":
            raise CanonicalByteError(f"CANONICAL_UNEXPECTED_FILE_TYPE: {relative} tree")
        if mode == "120000":
            raise CanonicalByteError(f"CANONICAL_UNEXPECTED_FILE_TYPE: {relative} symlink")
        if mode == "160000":
            raise CanonicalByteError(f"CANONICAL_UNEXPECTED_FILE_TYPE: {relative} gitlink")
        if mode not in ("100644", "100755"):
            raise CanonicalByteError(f"CANONICAL_UNEXPECTED_FILE_TYPE: {relative} mode {mode}")
        obj_type, content = self._read_object(sha)
        if obj_type != "blob":
            raise CanonicalByteError(f"CANONICAL_BLOB_UNAVAILABLE: {relative}")
        return content

    # -- working-tree materialisation ---------------------------------------

    def materialize_worktree(self, target: Path, files: dict[str, bytes], *, eol: str) -> Path:
        """Write a working tree whose text files use LF or CRLF endings.

        ``eol`` is "lf" or "crlf" — simulating exactly what Git's autocrlf
        policies materialise for LF-committed text.  Binary files are never
        transformed, matching Git's behaviour.
        """
        if eol not in ("lf", "crlf"):
            raise ValueError(eol)
        for name, data in files.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if b"\x00" in data or eol == "lf":
                path.write_bytes(data)
            else:
                path.write_bytes(data.replace(b"\n", b"\r\n"))
        return target


# ---------------------------------------------------------------------------
# Fixture content
# ---------------------------------------------------------------------------

TEXT_LF = b"alpha = 1\nbeta = 2\ngamma = 3\n"
TEXT_EXTENDED = b"alpha = 1\nbeta = 2\ngamma = 3\ndelta = 4\n"
TEXT_REMOVED = b"alpha = 1\ngamma = 3\n"
TEXT_TRAILING_SPACE = b"alpha = 1\nbeta = 2 \ngamma = 3\n"
BINARY = b"\x00\x01binary\x00\r\ndata\r\n\x00\xff"  # CRLF and NUL inside
UNICODE_TEXT = "café = 'naïve' — em-dash\n".encode("utf-8")

BASE_FILES = {
    "src/alpha.txt": TEXT_LF,
    "src/binary.bin": BINARY,
    "src/empty.txt": b"",
    "src/no_final_newline.txt": b"no trailing newline",
    "src/unicode.txt": UNICODE_TEXT,
}

PATHS = ["src/alpha.txt", "src/binary.bin", "src/empty.txt",
         "src/no_final_newline.txt", "src/unicode.txt"]


@dataclass
class FixtureRepo:
    root: Path
    commit: str
    store: GitObjectStore
    files: dict[str, bytes] = field(default_factory=dict)

    def worktree(self, tmp_path: Path, *, eol: str, name: str | None = None) -> Path:
        label = name or f"wt-{eol}"
        return self.store.materialize_worktree(
            tmp_path / label, self.files, eol=eol
        )

    def blob_source(self):
        return self.store.blob_bytes


@pytest.fixture()
def source_repo(tmp_path: Path) -> FixtureRepo:
    store = GitObjectStore(tmp_path / "source-repo")
    commit = store.commit_files(BASE_FILES, "frozen scientific fixture")
    return FixtureRepo(
        root=tmp_path / "source-repo", commit=commit, store=store, files=dict(BASE_FILES)
    )


def _recommit(store: GitObjectStore, files: dict[str, bytes], message: str) -> str:
    return store.commit_files(files, message)


# ---------------------------------------------------------------------------
# canonical_git_blob_v1 determinism across working-tree representations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("eol", ["lf", "crlf"])
def test_canonical_digest_identical_across_worktree_materialisation(
    source_repo: FixtureRepo, tmp_path: Path, eol: str
) -> None:
    expected = canonical_framed_digest(
        PATHS, commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    checkout = source_repo.worktree(tmp_path, eol=eol)
    assert canonical_framed_digest(
        PATHS, commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    ) == expected


def test_legacy_worktree_bytes_diverge_across_checkouts_v1_regression(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    """THE V1 defect, reproduced: same committed content, different legacy hashes."""
    canonical = canonical_framed_digest(
        ["src/alpha.txt"], commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    legacy_hashes = set()
    for eol in ("lf", "crlf"):
        checkout = source_repo.worktree(tmp_path, eol=eol)
        raw = legacy_worktree_bytes_v0(checkout / "src" / "alpha.txt")
        legacy_hashes.add(hashlib.sha256(raw).hexdigest())
        # the canonical contract stays stable in both environments
        assert canonical_framed_digest(
            ["src/alpha.txt"], commit=source_repo.commit, repo=checkout,
            blob_source=source_repo.blob_source(),
        ) == canonical
    assert len(legacy_hashes) == 2, "legacy raw worktree bytes must diverge"


def test_crlf_materialised_text_differs_but_canonical_matches(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    checkout = source_repo.worktree(tmp_path, eol="crlf")
    raw = (checkout / "src" / "alpha.txt").read_bytes()
    assert raw == TEXT_LF.replace(b"\n", b"\r\n")
    assert canonical_blob_bytes(
        "src/alpha.txt", commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    ) == TEXT_LF


# ---------------------------------------------------------------------------
# Content sensitivity
# ---------------------------------------------------------------------------


def test_added_line_changes_digest(source_repo: FixtureRepo) -> None:
    base = canonical_framed_digest(
        ["src/alpha.txt"], commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    files = dict(BASE_FILES)
    files["src/alpha.txt"] = TEXT_EXTENDED
    new_commit = _recommit(source_repo.store, files, "added line")
    after = canonical_framed_digest(
        ["src/alpha.txt"], commit=new_commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    assert after != base


def test_removed_line_changes_digest(source_repo: FixtureRepo) -> None:
    base = canonical_framed_digest(
        ["src/alpha.txt"], commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    files = dict(BASE_FILES)
    files["src/alpha.txt"] = TEXT_REMOVED
    new_commit = _recommit(source_repo.store, files, "removed line")
    after = canonical_framed_digest(
        ["src/alpha.txt"], commit=new_commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    assert after != base


def test_whitespace_change_not_silently_ignored(source_repo: FixtureRepo) -> None:
    base = canonical_framed_digest(
        ["src/alpha.txt"], commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    files = dict(BASE_FILES)
    files["src/alpha.txt"] = TEXT_TRAILING_SPACE
    new_commit = _recommit(source_repo.store, files, "trailing space")
    after = canonical_framed_digest(
        ["src/alpha.txt"], commit=new_commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    assert after != base


def test_path_change_changes_identity(source_repo: FixtureRepo) -> None:
    old = canonical_framed_digest(
        ["src/alpha.txt"], commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    files = dict(BASE_FILES)
    files["src/renamed.txt"] = files.pop("src/alpha.txt")
    new_commit = _recommit(source_repo.store, files, "rename")
    new = canonical_framed_digest(
        ["src/renamed.txt"], commit=new_commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    assert old != new


def test_argument_order_does_not_affect_digest(source_repo: FixtureRepo) -> None:
    forward = canonical_framed_digest(
        PATHS, commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    backward = canonical_framed_digest(
        list(reversed(PATHS)), commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    assert forward == backward


def test_single_file_digest_matches_raw_blob_sha256(source_repo: FixtureRepo) -> None:
    assert canonical_file_digest(
        "src/binary.bin", commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    ) == hashlib.sha256(BINARY).hexdigest()


def test_binary_blob_never_newline_normalised(source_repo: FixtureRepo) -> None:
    assert canonical_blob_bytes(
        "src/binary.bin", commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    ) == BINARY


def test_empty_file_deterministic(source_repo: FixtureRepo) -> None:
    first = canonical_file_digest(
        "src/empty.txt", commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    second = canonical_file_digest(
        "src/empty.txt", commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    assert first == second == hashlib.sha256(b"").hexdigest()


def test_no_final_newline_deterministic(source_repo: FixtureRepo) -> None:
    assert canonical_file_digest(
        "src/no_final_newline.txt", commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    ) == hashlib.sha256(b"no trailing newline").hexdigest()


def test_unicode_content_deterministic(source_repo: FixtureRepo) -> None:
    assert canonical_file_digest(
        "src/unicode.txt", commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    ) == hashlib.sha256(UNICODE_TEXT).hexdigest()


# ---------------------------------------------------------------------------
# Fail-closed cases
# ---------------------------------------------------------------------------


def test_missing_file_fails_closed(source_repo: FixtureRepo) -> None:
    with pytest.raises(CanonicalByteError):
        canonical_framed_digest(
            ["src/alpha.txt", "src/does_not_exist.txt"],
            commit=source_repo.commit, repo=source_repo.root,
            blob_source=source_repo.blob_source(),
        )


def test_duplicate_manifest_entry_fails_closed(source_repo: FixtureRepo) -> None:
    with pytest.raises(CanonicalByteError):
        canonical_framed_digest(
            ["src/alpha.txt", "src/alpha.txt"],
            commit=source_repo.commit, repo=source_repo.root,
            blob_source=source_repo.blob_source(),
        )


def test_empty_manifest_fails_closed(source_repo: FixtureRepo) -> None:
    with pytest.raises(CanonicalByteError):
        canonical_framed_digest(
            [], commit=source_repo.commit, repo=source_repo.root,
            blob_source=source_repo.blob_source(),
        )


def test_directory_path_fails_closed(source_repo: FixtureRepo) -> None:
    with pytest.raises(CanonicalByteError):
        canonical_framed_digest(
            ["src"], commit=source_repo.commit, repo=source_repo.root,
            blob_source=source_repo.blob_source(),
        )


def test_absolute_and_parent_paths_fail_closed(source_repo: FixtureRepo) -> None:
    for bad in ("/etc/passwd", "../outside.txt", "src\\alpha.txt"):
        with pytest.raises(CanonicalByteError):
            canonical_framed_digest(
                [bad], commit=source_repo.commit, repo=source_repo.root,
                blob_source=source_repo.blob_source(),
            )


def test_invalid_commit_identity_fails_closed(source_repo: FixtureRepo) -> None:
    with pytest.raises(CanonicalByteError):
        canonical_framed_digest(
            ["src/alpha.txt"], commit="not-a-commit", repo=source_repo.root,
            blob_source=source_repo.blob_source(),
        )


def test_unknown_commit_fails_closed(source_repo: FixtureRepo) -> None:
    unknown = "f" * 40
    with pytest.raises(CanonicalByteError):
        canonical_framed_digest(
            ["src/alpha.txt"], commit=unknown, repo=source_repo.root,
            blob_source=source_repo.blob_source(),
        )


def test_symlink_entry_fails_closed(tmp_path: Path) -> None:
    """A symlink tree entry must fail closed, never silently hash its target."""
    store = GitObjectStore(tmp_path / "symlink-repo")
    blob_sha = store.add_blob(TEXT_LF)
    link_blob_sha = store.add_blob(b"src/alpha.txt")  # symlink target as content
    tree = store.write_tree(
        {
            "alpha.txt": ("100644", blob_sha),
            "link.txt": ("120000", link_blob_sha),
        }
    )
    commit = store.commit_tree(tree, "symlink fixture")
    with pytest.raises(CanonicalByteError):
        store.blob_bytes(commit, "link.txt")


def test_gitlink_entry_fails_closed(tmp_path: Path) -> None:
    store = GitObjectStore(tmp_path / "gitlink-repo")
    blob_sha = store.add_blob(TEXT_LF)
    tree = store.write_tree(
        {
            "alpha.txt": ("100644", blob_sha),
            "vendor": ("160000", "0" * 40),
        }
    )
    commit = store.commit_tree(tree, "gitlink fixture")
    with pytest.raises(CanonicalByteError):
        store.blob_bytes(commit, "vendor")


# ---------------------------------------------------------------------------
# Working-tree integrity semantics
# ---------------------------------------------------------------------------


def test_working_tree_check_accepts_lf_checkout(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    checkout = source_repo.worktree(tmp_path, eol="lf")
    assert working_tree_canonical_agreement(
        "src/alpha.txt", commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    )


def test_working_tree_check_accepts_crlf_materialisation(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    checkout = source_repo.worktree(tmp_path, eol="crlf")
    assert working_tree_canonical_agreement(
        "src/alpha.txt", commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    )


def test_working_tree_check_rejects_real_edit(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    checkout = source_repo.worktree(tmp_path, eol="lf")
    with open(checkout / "src" / "alpha.txt", "ab") as handle:
        handle.write(b"epsilon = 5\n")
    assert not working_tree_canonical_agreement(
        "src/alpha.txt", commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    )


def test_working_tree_check_rejects_line_reordering(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    """Reordered lines are a real content change, not newline materialisation."""
    checkout = source_repo.worktree(tmp_path, eol="crlf")
    (checkout / "src" / "alpha.txt").write_bytes(b"beta = 2\nalpha = 1\ngamma = 3\n")
    assert not working_tree_canonical_agreement(
        "src/alpha.txt", commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    )


def test_working_tree_check_rejects_missing_file(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    checkout = source_repo.worktree(tmp_path, eol="lf")
    (checkout / "src" / "alpha.txt").unlink()
    with pytest.raises((CanonicalByteError, OSError)):
        working_tree_canonical_agreement(
            "src/alpha.txt", commit=source_repo.commit, repo=checkout,
            blob_source=source_repo.blob_source(),
        )


def test_working_tree_check_binary_exact_match_only(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    """Binary committed content containing CRLF requires exact agreement."""
    checkout = source_repo.worktree(tmp_path, eol="crlf")
    assert working_tree_canonical_agreement(
        "src/binary.bin", commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    )
    (checkout / "src" / "binary.bin").write_bytes(BINARY + b"x")
    assert not working_tree_canonical_agreement(
        "src/binary.bin", commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    )


# ---------------------------------------------------------------------------
# Migration adapters (§6, §11)
# ---------------------------------------------------------------------------


def test_pipeline_fingerprint_at_commit_fails_closed_without_surface(
    source_repo: FixtureRepo,
) -> None:
    """A repo lacking the pipeline surface files must fail closed."""
    from bot.validation.replay_input_index import pipeline_fingerprint_at_commit

    with pytest.raises(CanonicalByteError):
        pipeline_fingerprint_at_commit(
            source_repo.commit, source_repo.root, blob_source=source_repo.blob_source()
        )


def test_pipeline_fingerprint_at_commit_reproduces_fixture_binding(
    tmp_path: Path,
) -> None:
    """The historical-reproduction seam computes legacy framing over blobs."""
    from bot.validation.replay_input_index import (
        PIPELINE_FINGERPRINT_FILES,
        pipeline_fingerprint_at_commit,
    )

    store = GitObjectStore(tmp_path / "pipeline-repo")
    files = {name: f"# pipeline surface: {name}\n".encode("utf-8")
             for name in PIPELINE_FINGERPRINT_FILES}
    commit = store.commit_files(files, "pipeline surface fixture")
    value = pipeline_fingerprint_at_commit(
        commit, tmp_path / "pipeline-repo", blob_source=store.blob_bytes
    )
    digest = hashlib.sha256()
    for relative in PIPELINE_FINGERPRINT_FILES:
        data = files[relative]
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(relative.encode("utf-8"))
        digest.update(data)
    assert value == digest.hexdigest()


def _surface_repo(tmp_path: Path) -> tuple[GitObjectStore, str, dict[str, bytes]]:
    """A fixture repository containing both migration-adapter file surfaces."""
    from bot.validation.cost_policy import _EXECUTION_MODEL_MODULES
    from bot.validation.replay_input_index import PIPELINE_FINGERPRINT_FILES

    names = sorted(set(PIPELINE_FINGERPRINT_FILES) | set(_EXECUTION_MODEL_MODULES))
    files = {name: f"# scientific surface: {name}\n".encode("utf-8") for name in names}
    store = GitObjectStore(tmp_path / "surface-repo")
    commit = store.commit_files(files, "scientific surfaces fixture")
    return store, commit, files


def test_execution_model_fingerprint_canonical_deterministic(tmp_path: Path) -> None:
    from bot.validation.cost_policy import execution_model_fingerprint_canonical

    store, commit, _ = _surface_repo(tmp_path)
    first = execution_model_fingerprint_canonical(
        commit, tmp_path / "surface-repo", blob_source=store.blob_bytes
    )
    second = execution_model_fingerprint_canonical(
        commit, tmp_path / "surface-repo", blob_source=store.blob_bytes
    )
    assert first == second
    assert len(first) == 64


def test_canonical_and_legacy_are_distinct_contracts(tmp_path: Path) -> None:
    from bot.validation.cost_policy import execution_model_fingerprint_canonical
    from bot.validation.replay_input_index import pipeline_fingerprint_canonical

    store, commit, _ = _surface_repo(tmp_path)
    root = tmp_path / "surface-repo"
    canonical_pipeline = pipeline_fingerprint_canonical(
        commit, root, blob_source=store.blob_bytes
    )
    canonical_exec = execution_model_fingerprint_canonical(
        commit, root, blob_source=store.blob_bytes
    )
    assert len(canonical_pipeline) == len(canonical_exec) == 64
    assert CONTRACT_ID == "canonical_git_blob_v1"


def test_contract_module_imports_without_metatrader() -> None:
    import bot.scientific.canonical_bytes as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "MetaTrader5" not in source


# ---------------------------------------------------------------------------
# Supervisory requirement A — commit identity vs dirty working-tree bytes
# ---------------------------------------------------------------------------


#: autocrlf policy -> materialisation it produces for LF-committed text.
AUTOCRLF_MATERIALISATION = {"false": "lf", "input": "lf", "true": "crlf"}


@pytest.mark.parametrize("policy", ["false", "input", "true"])
def test_A1_same_commit_identical_under_every_autocrlf_policy(
    source_repo: FixtureRepo, tmp_path: Path, policy: str
) -> None:
    """A1: one fixed commit, one fingerprint under every checkout policy."""
    reference = canonical_framed_digest(
        PATHS, commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    checkout = source_repo.worktree(
        tmp_path, eol=AUTOCRLF_MATERIALISATION[policy], name=f"wt-autocrlf-{policy}"
    )
    # The canonical fingerprint comes from the object database: identical.
    assert canonical_framed_digest(
        PATHS, commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    ) == reference
    # Working-tree raw bytes differ between policies — expected and harmless.
    raw = (checkout / "src" / "alpha.txt").read_bytes()
    if AUTOCRLF_MATERIALISATION[policy] == "crlf":
        assert raw == TEXT_LF.replace(b"\n", b"\r\n") != TEXT_LF


def test_A1_all_policies_agree_on_one_fingerprint(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    """A1 (aggregate): LF, CRLF and all three autocrlf settings, one digest."""
    reference = canonical_framed_digest(
        PATHS, commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    digests = set()
    for policy, eol in [("false", "lf"), ("input", "lf"), ("true", "crlf")]:
        checkout = source_repo.worktree(
            tmp_path, eol=eol, name=f"wt-aggregate-{policy}"
        )
        digests.add(canonical_framed_digest(
            PATHS, commit=source_repo.commit, repo=checkout,
            blob_source=source_repo.blob_source(),
        ))
    assert digests == {reference}


def test_A2_uncommitted_edit_leaves_canonical_fingerprint_unchanged(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    """A2: a genuine uncommitted edit must not move the commit's identity."""
    reference = canonical_framed_digest(
        PATHS, commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    checkout = source_repo.worktree(tmp_path, eol="lf", name="wt-dirty")
    assert working_tree_canonical_agreement(
        "src/alpha.txt", commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    )
    # Genuine, uncommitted working-tree source edit (never committed).
    (checkout / "src" / "alpha.txt").write_bytes(
        TEXT_LF + b"# dirty uncommitted edit\n"
    )
    # Canonical fingerprint of the SAME commit: unchanged.
    assert canonical_framed_digest(
        PATHS, commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    ) == reference
    # ...while the legacy raw-worktree hash DID move (the old defect surface).
    assert hashlib.sha256(
        legacy_worktree_bytes_v0(checkout / "src" / "alpha.txt")
    ).hexdigest() != hashlib.sha256(TEXT_LF).hexdigest()
    # ...and working-tree agreement FAILS — the edit is detected.
    assert not working_tree_canonical_agreement(
        "src/alpha.txt", commit=source_repo.commit, repo=checkout,
        blob_source=source_repo.blob_source(),
    )


def test_A3_committed_edit_changes_fingerprint_consistently(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    """A3: fingerprint(A) != fingerprint(B); fingerprint(B) across checkouts."""
    fingerprint_a = canonical_framed_digest(
        PATHS, commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    # Genuine source edit, contained in a NEW fixture commit.
    edited = dict(BASE_FILES)
    edited["src/alpha.txt"] = TEXT_LF + b"delta = 4\n"
    commit_b = _recommit(source_repo.store, edited, "genuine revision B")
    assert commit_b != source_repo.commit
    fingerprint_b = canonical_framed_digest(
        PATHS, commit=commit_b, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    assert fingerprint_b != fingerprint_a
    # Every materialisation of commit B yields the single fingerprint of B.
    digests = set()
    for eol in ("lf", "crlf"):
        checkout_b = source_repo.store.materialize_worktree(
            tmp_path / f"wt-B-{eol}", edited, eol=eol
        )
        digests.add(canonical_framed_digest(
            PATHS, commit=commit_b, repo=checkout_b,
            blob_source=source_repo.blob_source(),
        ))
    assert digests == {fingerprint_b}


# ---------------------------------------------------------------------------
# Supervisory requirement B — prospective freezes fail closed on legacy
# ---------------------------------------------------------------------------


def test_B_canonical_contract_accepted_for_prospective_freeze(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    from bot.scientific.prospective_freeze import (
        contract_record,
        freeze_prospective_identity,
    )

    identity = freeze_prospective_identity(
        PATHS, contract_id=CONTRACT_ID, commit=source_repo.commit,
        repo=source_repo.root, blob_source=source_repo.blob_source(),
    )
    record = contract_record(identity)
    assert record["contract_id"] == "canonical_git_blob_v1"
    assert record["digest_algorithm"] == "sha256"
    assert record["commit"] == source_repo.commit
    assert record["paths"] == sorted(PATHS)
    assert record["digest"] == canonical_framed_digest(
        PATHS, commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )


def test_B_legacy_contract_rejected_prospective() -> None:
    from bot.scientific.prospective_freeze import (
        LEGACY_CONTRACT_ID,
        ProspectiveFreezeError,
        validate_prospective_contract,
    )

    assert LEGACY_CONTRACT_ID == "legacy_worktree_bytes_v0"
    with pytest.raises(ProspectiveFreezeError):
        validate_prospective_contract(LEGACY_CONTRACT_ID)


def test_B_missing_contract_rejected() -> None:
    from bot.scientific.prospective_freeze import (
        ProspectiveFreezeError,
        validate_prospective_contract,
    )

    with pytest.raises(ProspectiveFreezeError):
        validate_prospective_contract(None)
    with pytest.raises(ProspectiveFreezeError):
        validate_prospective_contract("")


def test_B_unknown_contract_rejected_until_registered() -> None:
    from bot.scientific.prospective_freeze import (
        ProspectiveFreezeError,
        register_prospective_contract,
        validate_prospective_contract,
    )

    with pytest.raises(ProspectiveFreezeError):
        validate_prospective_contract("canonical_git_blob_v2_draft")
    # Explicit approval makes it usable — the caller chooses, never defaults.
    register_prospective_contract("canonical_git_blob_v2_draft")
    assert validate_prospective_contract("canonical_git_blob_v2_draft") == (
        "canonical_git_blob_v2_draft"
    )
    # The legacy contract can never be registered, even explicitly.
    with pytest.raises(ProspectiveFreezeError):
        register_prospective_contract("legacy_worktree_bytes_v0")


def test_B_no_silent_default_contract(tmp_path: Path) -> None:
    """freeze_prospective_identity without an explicit contract must fail."""
    from bot.scientific.prospective_freeze import (
        ProspectiveFreezeError,
        freeze_prospective_identity,
    )

    with pytest.raises(ProspectiveFreezeError):
        freeze_prospective_identity(
            ["src/alpha.txt"],
            contract_id=None, commit="a" * 40,  # type: ignore[arg-type]
            repo=tmp_path, blob_source=None,
        )


def test_B_historical_v1_verification_retained(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    """V1-era semantics remain available for historical verification only."""
    from bot.scientific.prospective_freeze import PROSPECTIVE_CONTRACTS

    # Legacy bytes still readable under their original semantics...
    checkout = source_repo.worktree(tmp_path, eol="lf", name="wt-legacy-verify")
    raw = legacy_worktree_bytes_v0(checkout / "src" / "alpha.txt")
    assert hashlib.sha256(raw).hexdigest() == canonical_file_digest(
        "src/alpha.txt", commit=source_repo.commit, repo=source_repo.root,
        blob_source=source_repo.blob_source(),
    )
    # ...and the prospective registry does not quietly admit the legacy id.
    assert "legacy_worktree_bytes_v0" not in PROSPECTIVE_CONTRACTS
    assert PROSPECTIVE_CONTRACTS == ("canonical_git_blob_v1",)


def test_B_freeze_identity_record_shape_and_binding(
    source_repo: FixtureRepo, tmp_path: Path
) -> None:
    """Typed record: ordered paths, digest binding, no path/config leakage."""
    from bot.scientific.prospective_freeze import (
        ProspectiveFreezeError,
        ProspectiveFreezeIdentity,
        freeze_prospective_identity,
    )

    identity = freeze_prospective_identity(
        ["src/alpha.txt", "src/unicode.txt"],
        contract_id=CONTRACT_ID, commit=source_repo.commit,
        repo=source_repo.root, blob_source=source_repo.blob_source(),
    )
    assert isinstance(identity, ProspectiveFreezeIdentity)
    assert identity.paths == ("src/alpha.txt", "src/unicode.txt")
    # No absolute local paths or checkout configuration exist on the record.
    dumped = repr(identity)
    assert str(source_repo.root) not in dumped
    assert "autocrlf" not in dumped
    # Unordered manifest input is rejected (fail closed on record shape).
    with pytest.raises(ProspectiveFreezeError):
        ProspectiveFreezeIdentity(
            contract_id=CONTRACT_ID, digest_algorithm="sha256",
            commit=source_repo.commit,
            paths=("src/unicode.txt", "src/alpha.txt"),
            digest=identity.digest,
        )
    # A checkout cannot influence the identity: CRLF materialisation agrees.
    checkout = source_repo.worktree(tmp_path, eol="crlf", name="wt-freeze")
    assert freeze_prospective_identity(
        ["src/alpha.txt", "src/unicode.txt"],
        contract_id=CONTRACT_ID, commit=source_repo.commit,
        repo=checkout, blob_source=source_repo.blob_source(),
    ) == identity
