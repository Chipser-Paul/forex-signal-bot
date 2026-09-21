# Phase 8B 2024 Reconstruction

## Status

The canonical 2024 `XAUUSDm` development package is complete. It references
twelve immutable monthly packages without copying their tick data. It is
classified `DEVELOPMENT_ONLY`; it is not a holdout, profitability result, or
deployment authorization.

## December selection

The December registry has exactly one active package:
`exness-xauusdm-2024-12-a5cef8ab1fb1bce2-recovery-0002`. The original December
package and `recovery-v1` remain quarantined and are not selectable.

## August forensic recovery

The first August conversion left a preserved partial artifact after one stored
row identity differed from the deterministic identity reconstructed from the
raw source. The full forensic scan found exactly one mismatch in 3,958,550
rows, no duplicate stored identities, and no raw structural, timestamp,
decimal, duplicate-ordinal, or verifier discrepancy. The stored digest was not
the identity of another raw row.

The cause is classified `PARTIAL_ARTIFACT_CORRUPTION`. The retained partial is
bound to its physical SHA-256 and forensic record by a quarantine marker. It is
non-selectable, remains preserved outside Git, and fails closed if its Parquet
artifact changes. A new non-overwriting recovery package was built directly
from the unchanged raw ZIP. It contains all 3,958,550 rows and preserves 6,702
exact duplicate source rows.

## Year package

| Field | Value |
| --- | --- |
| Package ID | `exness-xauusdm-2024-development-b2a0234a470dd397` |
| Period | `[2024-01-01T00:00:00Z, 2025-01-01T00:00:00Z)` |
| Rows | 39,715,935 |
| First tick | `2024-01-01T23:05:09.882Z` |
| Last tick | `2024-12-31T21:57:57.766Z` |
| Canonical SHA-256 | `b2a0234a470dd397a9bd1d2df210a417620a7a5f60dbf18488938db512f47e73` |
| Manifest SHA-256 | `239d3cffccdf268eefd532c0b844bb440eee0e948ec2e56249b9550c5b213a78` |
| Completion SHA-256 | `1ec0b2605ae6bc938482ed4ca69a75bb8b93166c0319b4f0dfdde6b04b8502df` |

The year manifest references only monthly packages. The incomplete annual
archive contributes zero rows. The deep verifier recomputed the full-year row
count, chronology, month membership, package hashes, and canonical hash twice
after publication.

## Aggregate diagnostics

- Exact duplicate source rows: 24,648; duplicates remain part of the source
  contract.
- Conflicting timestamp prices: 0.
- Long gaps: 260; gaps are reported, not filled.
- Observed spread price range: `0.06400000` to `9.02600000`; mean
  `0.1831070536045544439530379934`.
- Every adjacent monthly boundary is strictly chronological. This validates
  package ordering, not continuous market availability.

## Limits and next work

The data remains outside Git and was processed without MT5, account, network,
strategy, holdout, backtest, optimization, or trading operations. Broker
metadata, cost evidence, causal analysis-candle inputs, complete news history,
and the Phase 8 scientific-validation protocol remain required before any
final validation or holdout work.
