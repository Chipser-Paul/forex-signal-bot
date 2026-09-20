# Phase 8B Package Registry

## Purpose

Directory discovery cannot decide which of several preserved packages is valid
for a recovery month. `package_registry.py` is the external, offline authority
for that decision. It does not acquire, parse, or expose market data.

## Schema and state

Each versioned JSON registry binds one exact Exness `XAUUSDm` closed-open period
to its raw SHA-256, provider, code fingerprint, monotonic revision, recovery
generation counter, package records, and a nullable active package ID. Package
records bind a package identity to its artifact, logical, manifest, and
completion hashes.

Legal transitions are `CANDIDATE -> VERIFYING -> VERIFIED_INACTIVE -> ACTIVE`.
Candidate and verification failures may become `INCOMPLETE`, `REJECTED`, or
`QUARANTINED`. An active predecessor is quarantined atomically during a new
activation. Quarantined and rejected records cannot reactivate. Zero active
packages is intentionally fail-closed; otherwise exactly one active record and
`active_package_id` must agree.

## Recovery identities

Normal monthly package identities are unchanged. A recovery allocation uses a
locked monotonic generation and an immutable operation ID, yielding for example
`exness-xauusdm-2024-12-a5cef8ab1fb1bce2-recovery-0002`. Repeating an operation
returns its original allocation; a different operation receives a new number.
No directory count, suffix, or path traversal input participates in allocation.

### Preserved legacy evidence

One deliberately narrow bootstrap-only exception preserves the already-existing
literal December 2024 package ID ending in `-recovery-v1`. It is accepted only
when an explicit legacy flag and identity-format declaration are supplied for
the exact Exness/XAUUSDm December dataset, its exact raw hash, generation one,
and a non-empty reason. It is permanently `QUARANTINED`, cannot be activated or
registered by normal paths, and is not a canonical recovery identity. All new
allocations remain zero-padded numeric identities; after that preserved legacy
generation, the next allocation is `-recovery-0002`. This exception accepts no
other suffix and never renames a real package.

## Durability and discovery

Registry mutations use a file lock, deterministic JSON, same-directory temporary
file, fsync, and atomic replacement. Every mutation is recorded in a flushed,
hash-chained journal before publication; the registry revision, final journal
hash, and normalized content hash must reconcile on load. Any missing,
corrupt, contradictory, stale, or mismatched state blocks selection.

For a managed recovery period, monthly reconstruction reads only this registry,
then validates the selected active package's marker hashes. It never chooses by
directory order or modification time. Normal months retain the established
immutable discovery path until a separately authorized bootstrap manages them.

## Bootstrap and recovery sequence

`python -m backtests.package_registry_control bootstrap-dry-run --registry-root
<temporary-registry-root> --spec <owner-reviewed-plan.json>` produces a stable
plan hash. Applying it additionally requires `--confirm --plan-hash <hash>`.
The plan explicitly lists every package, status, hash, active selection (or
none), generation start, justification, and owner approval; it never scans
directories to infer any of those facts.

The future real-data sequence is: explicitly bootstrap December with both
preserved packages quarantined and no active record; allocate recovery generation
two; publish only to its allocated path; register candidate; complete durable
offline verification; record verification; atomically activate it. None of
those operations were run for this code-only change. No real December package,
August--October package, or year package was accessed or changed.

The durable offline verifier establishes physical/logical evidence. The registry
establishes selection authority; both are required before reconstruction can use
a managed recovery package.
