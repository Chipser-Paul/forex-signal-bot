# Phase 8C Provenance Attestation and Discovery

This checkpoint closes the Phase 8C provenance gap without regenerating the
39,715,935 source ticks or rederiving any candle dataset.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE

## Why the original manifest remains unchanged

The derived package
`derived-candles-2024-v1-20260911T195553Z` was generated while the Phase 8C
implementation existed only as uncommitted working-tree files and the
repository HEAD was `4f46eef139bd20df84d4db5911767baa273eeba2`. Its manifest
therefore truthfully records `"git_commit": "4f46eef…"`. Rewriting that field
now — after the implementation was committed as `2817d5b…` — would falsify
generation evidence. The package, its manifest, its completion marker and its
readiness report are immutable inputs; this checkpoint only reads them and
records hashes of them.

## Generation commit versus verification commit

These are distinct concepts and are never collapsed:

| Field | Value | Meaning |
|---|---|---|
| `generation_base_commit` | `4f46eef139bd20df84d4db5911767baa273eeba2` | Repository HEAD during generation, as recorded by the manifest itself. |
| `generation_source_fingerprint` | `null` (absent) | The manifest stores no generation-time code fingerprint. |
| `implementation_commit` | `2817d5b82a452157a3662b57e1956fd878a733cf` | The commit that introduced the Phase 8C implementation. |
| `verification_commit` | `2817d5b82a452157a3662b57e1956fd878a733cf` | The exact clean commit whose committed verifier executed the attestation verification. |
| `verification_fingerprint` | `phase8c-verifier-v1:<sha256>` | SHA-256 over committed blob hashes of `candle_pipeline.py`, `candle_store.py`, `candle_manifest.py` at the verification commit (via `git show <commit>:<path>`). |
| `verified_compatible` | `true` | The package passes the committed verifier unchanged. |
| `generation_commit_equivalence` | `NOT_PROVEN` | No immutable evidence binds the generation-time working tree to `2817d5b…`. |

The CLI-only `monthly_dirs` correction (resolving the twelve monthly package
directories referenced by the year manifest) affected only source discovery
and predates the successful generation run; the deep year reconciliation
passed with it. It changed no aggregation logic and no derived content.

## What the attestation proves

- The package manifest and completion marker are mutually hash-bound and
  unchanged since publication.
- All six partitions match their recorded physical SHA-256 and canonical
  content hashes; complete readback validates schema versions, stable candle
  identities, UTC ordering, closed-open boundaries, exact timeframe
  durations, `available_at >= close_time`, bid/ask validity, OHLC invariants
  and first/last source-tick containment.
- Row counts match the Phase 8C checkpoint report independently
  (M5 70,562; M15 23,550; H1 5,904; H4 1,600; D1 311; W1 52) and reconcile
  with the package's own readiness report.
- The verifier at exact commit `2817d5b…` accepts the package unchanged
  (`verified_compatible = true`).
- No strategy evaluation occurred; the holdout was not accessed.

## What it cannot prove

- That commit `2817d5b…` generated the package. The generation-time working
  tree was uncommitted, and no generation-time code fingerprint was recorded
  in the manifest, so `generation_commit_equivalence = NOT_PROVEN`.
  The mechanism supports `PROVEN` and `DISPROVEN` classifications if a
  fingerprint is present and is reproduced (or fails to reproduce) from
  committed verifier content; it never guesses.

## How downstream validation discovers the package

`bot/acquisition/candle_discovery.py` registers the attested package in an
external discovery record keyed by attestation id. The record carries the
stable package identity (content-derived, never an absolute path), original
manifest and completion-marker hashes, attestation canonical hash, source
year-package identity and canonical hash, schema versions, classification,
row counts and partition hashes, verification status, and the dataset
readiness block. Registration is locked, atomic, non-overwriting, idempotent
and fails closed on tampering, missing attestations, hash mismatches or
ambiguous attestation selection. It does not classify the complete empirical
dataset as accepted.

## Development-only restriction and remaining inputs

Only the 2024 XAUUSDm ticks, the derived causal bid/ask candles and observed
spread evidence are available. The following remain missing or unresolved:
direct DXY history or all six causally aligned constituent histories;
complete historical high-impact USD news with provenance and licensing;
historically effective broker metadata; commission schedule; swap, rollover
timezone and triple-swap rules; empirical slippage/fill evidence; and an
untouched holdout. Registration and attestation never authorize holdout
access or strategy evaluation.

## Exact external locations

- Attested package: `C:\Users\chips\forex-signal-bot-data\phase8\derived\derived-candles-2024-v1-20260911T195553Z` (unchanged)
- Attestation: `C:\Users\chips\forex-signal-bot-data\phase8\derived\attestations\derived-candles-attestation-v1-6715e5c64d888215\attestation.json` (+ `.sha256` sidecar)
- Discovery record: `C:\Users\chips\forex-signal-bot-data\phase8\derived\discovery\derived-candles-attestation-v1-6715e5c64d888215\discovery.json` (+ `.sha256` sidecar)

Owner commands:

```powershell
$python = 'C:\Users\chips\forex-signal-bot\.venv\Scripts\python.exe'
& $python -m backtests.candle_provenance_control attest `
  --derived-root  C:\Users\chips\forex-signal-bot-data\phase8\derived\derived-candles-2024-v1-20260911T195553Z `
  --attestations-root C:\Users\chips\forex-signal-bot-data\phase8\derived\attestations `
  --implementation-commit 2817d5b82a452157a3662b57e1956fd878a733cf `
  --verification-commit 2817d5b82a452157a3662b57e1956fd878a733cf
& $python -m backtests.candle_provenance_control register `
  --attestations-root C:\Users\chips\forex-signal-bot-data\phase8\derived\attestations `
  --discovery-root C:\Users\chips\forex-signal-bot-data\phase8\derived\discovery
```

## Recovery procedure for missing or corrupted records

If the attestation or discovery record is missing, corrupted, or fails its
hash checks, delete only the affected record directory (never the attested
package) and re-run `attest` followed by `register`. Because the attested
package is immutable and its identity derives from content hashes, a
re-created record must reproduce byte-identical hashes for the same
immutable inputs; any difference indicates package tampering or a verifier
change and fails closed. A conflicting re-attestation (different commits)
refuses to overwrite and requires explicit investigation.

## Current files

`bot/acquisition/candle_attestation.py`,
`bot/acquisition/candle_discovery.py`,
`backtests/candle_provenance_control.py`,
focused tests in `tests/phase8c/test_candle_provenance.py`, and this
document. No generated market-data artifact, attestation or discovery record
is committed to Git.
