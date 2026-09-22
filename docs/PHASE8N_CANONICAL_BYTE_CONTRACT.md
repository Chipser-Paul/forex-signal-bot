# Phase 8 Canonical-Byte Fingerprint Contract (`canonical_git_blob_v1`)

Status: **implemented, pending supervisory review — not committed**.

Scope: infrastructure only. This document and its implementation change no
strategy, validation, execution, risk, fold, scenario, cost or acceptance
semantics. No V2 research is conducted or implied.

---

## 1. Root cause of the V1 reproducibility debt

Several existing scientific fingerprints hash **raw working-tree bytes**:

* `pipeline_fingerprint` (`bot/validation/replay_input_index.py`) — bound into
  the published fold feature stores;
* `execution_model_fingerprint` (`bot/validation/cost_policy.py`) — bound into
  the published development cost policy.

On Windows, `git clone`/`git checkout` with `core.autocrlf=true` materialises
LF-in-repository text as CRLF in the working tree. The same committed content
therefore produced different fingerprints depending only on the user's Git
configuration:

* the published cost policy's execution-model fingerprint (`b1736e39…`)
  reproduces **only** from the historical build worktree's CRLF working-tree
  bytes, not from the committed LF blobs;
* the fold-01/02 feature-store pipeline fingerprint (`765b19d7…`) reproduces
  from the committed blobs only because that surface happened to be
  byte-identical between the historical worktree and the committed tree.

This was recorded as
`REPRODUCIBILITY_ENGINEERING_DEBT — MUST BE RESOLVED BEFORE V2 SCIENTIFIC FREEZE`
in `docs/PHASE8_FEASIBILITY_DISPOSITION_V1.md`. This contract resolves it
prospectively.

## 2. Contract identity and representation

* Contract ID: **`canonical_git_blob_v1`**
* Legacy classification: **`legacy_worktree_bytes_v0`** (explicit adapter,
  never reinterpreted)
* Digest algorithm: SHA-256
* Canonical byte source: **the committed Git blob** — the object stored in the
  Git object database at a given commit — never the bytes a checkout
  materialises. No newline transformation, encoding conversion or
  normalisation of any kind is applied; binary files pass through unchanged.

Production blob resolution uses real Git plumbing (`git ls-tree` +
`git cat-file blob`) via `make_git_blob_source`, mirroring the repository's
established convention (`bot.acquisition.candle_discovery.code_fingerprint`).
The source is injectable (`BlobSource`) so tests can exercise the contract
against a genuine Git object database without launching processes (the
repository test firewall prohibits subprocess launches inside the suite); the
fixture store writes real zlib loose objects in real `.git` layout and is
validated by `git fsck --strict` outside the suite.

## 3. Digest framing

For an input manifest of repository-relative paths:

```
sha256(
    framed(b"canonical-git-blob-v1")
 || framed(ASCII(len(paths)))
 || for each path in ascending lexicographic order:
        framed(path UTF-8) || framed(committed blob bytes)
)
```

with `framed(x) = 8-byte big-endian byte-length || x`.

Determinism properties:

* length framing removes concatenation ambiguity;
* ascending path order removes filesystem and argument-order dependence;
* per-path path framing binds the identity to the path itself.

## 4. Input classification

| Class | Contract | Rationale |
|---|---|---|
| Git-tracked scientific source/configuration | `canonical_git_blob_v1` | checkout-independent identity required |
| In-memory JSON/payload structures (`canonical_hash`) | existing JSON-canonical SHA-256 | already representation-independent; unchanged |
| Structured generated artifacts (evidence `package.json`, stores) | raw-byte SHA-256 (unchanged) | no proven reproducibility problem; historical evidence semantics preserved |
| Binary artifacts, empirical/raw data, external evidence | raw-byte SHA-256 (unchanged) | normalisation is never applied to data |

## 5. Working-tree verification (a separate concept)

`working_tree_canonical_agreement(relative, commit, repo)` asks whether a
checkout differs from its commit only by Git's newline-materialisation policy:

* if the committed blob contains CRLF, the working tree must match byte-for-byte;
* otherwise CRLF sequences in the working tree are normalised to LF before
  comparison — an unchanged checkout materialised with CRLF agrees, while any
  real content change (edited source, added/removed lines, reordered lines,
  whitespace edits, lone CR, missing file) fails.

This check is deliberately **not** the scientific fingerprint; canonical
identity always comes from Git object storage.

## 6. Fail-closed behaviour

`CanonicalByteError` is raised for: invalid commit identity (non-40-hex);
invalid paths (absolute, backslash, `..`, empty); empty manifests; duplicate
manifest entries; missing files; non-regular-file entries — directories,
symlinks (`120000`), gitlinks/submodules (`160000`) and any other mode; and
unresolvable blobs. Nothing is skipped, defaulted or repaired.

## 7. Legacy compatibility — historical V1 evidence is untouched

* **No historical fingerprint is rewritten or reinterpreted.** V1 identities
  remain verifiable under their original semantics:
  * fold-01/02 feature stores: `765b19d7…` — reproduced exactly by
    `pipeline_fingerprint_at_commit` (legacy framing applied to committed
    blobs; the committed blobs are byte-identical to the historical build
    worktree for this surface);
  * published cost policy: `b1736e39…` — reproduces from the historical CRLF
    working-tree bytes (`legacy_worktree_bytes_v0`, raw);
  * runner compatibility record: `c847398b…` under
    `UTF8_TEXT_CANONICAL_LF_SHA256` (CRLF→LF-normalised working-tree bytes).
* The legacy functions keep their exact behaviour and remain the only way to
  verify already-published artifacts.
* The canonical and legacy fingerprints are **different quantities under
  different contracts** and are never interchangeable.

## 8. Migration rules for future packages

* All future (post-V1) scientific freezes **must** use
  `canonical_git_blob_v1` for Git-tracked source/configuration fingerprints
  (`pipeline_fingerprint_canonical`,
  `execution_model_fingerprint_canonical`, or `canonical_framed_digest`
  directly), becoming mandatory upon supervisory approval of this change.
* Future scientific packages must record: fingerprint algorithm, canonical-byte
  contract ID, digest algorithm, commit identity, and the input manifest.
* V1's newline-sensitive semantics must not be extended to any new artifact.
* A future candidate freeze (e.g. `phase6-development-v2`) requires this
  contract to be in force — per the sealed V1 disposition, this debt must be
  resolved **before** a V2 scientific freeze.

## 9. `.gitattributes` disposition

The repository has **no** `.gitattributes`; checkout behaviour is purely
user-config-driven, which is why the contract is checkout-independent by
construction rather than by policy. No `.gitattributes` change is made or
required for scientific identity. Adding one (e.g. `* text=auto eol=lf` for
source) would be optional operational hygiene with its own review; it is not a
substitute for this contract.

## 10. Verification evidence (development-engineering, not strategy evidence)

* 47 focused contract tests (`tests/test_canonical_byte_contract.py`):
  LF/CRLF materialisation equivalence and the full autocrlf policy matrix
  (false/input/true) against one fixed commit, the V1 regression, added /
  removed / reordered lines, whitespace changes, path changes, argument-order
  independence, binary/no-final-newline/empty/Unicode determinism, all
  fail-closed cases (missing file, duplicate, empty manifest, directory,
  symlink, gitlink, invalid commit, unknown commit), working-tree agreement
  semantics, and the prospective-freeze guard.
* **Supervisory requirement A — commit identity vs dirty working-tree bytes**
  (tested in-suite and reproduced live with real `git` plumbing):
  * A1 — one fixed commit yields one canonical fingerprint under LF, CRLF,
    and `core.autocrlf=false/input/true` materialisations.
  * A2 — an uncommitted working-tree source edit leaves the canonical
    fingerprint of the same commit **unchanged** (live: canonical digest
    `f183d5c3…` before and after the dirty edit) while
    `working_tree_canonical_agreement` **fails** (dirty edit detected).
    The legacy raw-worktree hash moves under the same edit — the old defect
    surface.
  * A3 — a genuine committed revision produces a new fingerprint,
    identical across all materialisations and different from the previous
    commit's (`fingerprint(A) != fingerprint(B)`, `fingerprint(B, LF) =
    fingerprint(B, CRLF)`).
* **`61812831…` provenance (clarified).** The digest
  `618128317571888694b5d93bbaa380e86ed3cc208d7027c1b0ec9e1cda5d62fb` from the
  earlier demonstration came from a **committed fixture revision**: the demo
  edits the surface file, stages and commits it (`git add` + `git commit`),
  then recomputes against the new commit in three fresh checkouts. It was
  never an uncommitted working-tree artifact. (Pre-edit committed fixture:
  `f183d5c3…`; post-edit committed fixture: `61812831…`; both identical
  across all three autocrlf checkouts.)
* Live demonstration (outside the suite, production Git plumbing, real
  clones): legacy working-tree fingerprint produced **2 distinct digests**
  across `autocrlf=false` / `true` / `input` (the V1 debt, reproduced live),
  while the canonical fingerprint was **identical** in all three checkouts and
  moved identically after a real content edit; `git fsck --strict` validated
  the pure-Python fixture store; the production blob source agreed across
  repositories and checkout policies.
* Historical integrity: the fold-01 store binding reproduces from committed
  blobs, and all four frozen external evidence packages remain byte-identical.

## 11. Prospective-freeze contract guard (requirement B)

`bot/scientific/prospective_freeze.py` is the fail-closed validation
boundary separating historical verification from future freezes:

* `validate_prospective_contract(contract_id)` accepts only explicitly
  approved prospective contracts (currently `canonical_git_blob_v1`).
  Rejected, with no silent default: a missing/undeclared contract, the
  legacy contract `legacy_worktree_bytes_v0`, and any unknown contract name
  not registered via `register_prospective_contract` (an explicit,
  reviewed act; the legacy id can never be registered).
* `ProspectiveFreezeIdentity` is the typed record a future freeze must
  publish — `contract_id`, `digest_algorithm`, referenced Git `commit`,
  ordered unique input `paths`, resulting `digest`. It cannot carry an
  absolute local path or checkout configuration; unordered/duplicate path
  manifests are rejected.
* `freeze_prospective_identity(...)` requires the caller to name the
  contract explicitly; `contract_record(...)` renders the repository
  provenance shape.
* The invariant: **historical artifacts may verify under their declared
  legacy contract; new scientific freeze artifacts must explicitly declare
  and use an approved prospective canonical-byte contract.** V1 artifacts
  are untouched and remain verifiable under their original semantics.

Implementation surface: `bot/scientific/canonical_bytes.py` (new),
`bot/scientific/prospective_freeze.py` (new, supervisory requirement B),
`bot/scientific/__init__.py` (new), `bot/validation/replay_input_index.py`
(canonical + at-commit adapters added; legacy untouched),
`bot/validation/cost_policy.py` (canonical adapter added; legacy untouched),
`tests/test_canonical_byte_contract.py` (new). Left uncommitted for
supervisory review.
