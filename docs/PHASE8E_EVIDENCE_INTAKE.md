# Phase 8E — Offline News and Trading-Cost Evidence Intake

Status: **intake framework verified; owner evidence required.**
All accepted artifacts remain `DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE`.

## What this checkpoint built

A versioned, fail-closed, fully offline intake pipeline for the five remaining evidence
categories — historical high-impact USD news, effective-dated XAUUSDm broker metadata,
commission schedules, swap/rollover/triple-swap rules, sanitized slippage/fill evidence —
plus registration of the already-verified observed XAUUSDm spread evidence.

- Contracts: `bot/acquisition/evidence_contracts.py`
  (schemas `phase8e.historical-news.v1`, `phase8e.broker-metadata.v1`,
  `phase8e.commission-schedule.v1`, `phase8e.swap-rollover.v1`,
  `phase8e.slippage-fill-evidence.v1`, `phase8e.evidence-matrix.v1`)
- Atomic external storage: `bot/acquisition/evidence_store.py`
  (schema `phase8e.evidence-package.v1`; temporary dir → fsync → rename; non-overwriting;
  idempotent on identical content; conflicting intake detected at collection and fails closed)
- CLI: `backtests/evidence_intake_control.py`
  (`init`, `validate-news`, `validate-metadata`, `validate-commission`, `validate-swap`,
  `validate-slippage`, `verify-source`, `register-spread`, `matrix`, `readiness`, `reverify`)
- Owner input kit: `docs/PHASE8E_OWNER_INPUT_KIT.md`
- Fictional tracked examples: `docs/examples/phase8e/` (every value `EXAMPLE_ONLY`,
  `DUMMY_PROVIDER`, `NOT_EMPIRICAL`; the contracts reject example-marked content as evidence)

## Evidence matrix (as of this checkpoint)

| Category | Status |
|---|---|
| HISTORICAL_USD_NEWS | MISSING — no owner-supplied provenance-bearing file exists |
| BROKER_METADATA | MISSING — current MT5 observations are `CURRENT_ONLY_NOT_HISTORICAL` by contract and were not registered as 2024 evidence |
| COMMISSION | MISSING — zero commission must never be assumed from missing data |
| SWAP_ROLLOVER | MISSING — zero current swap fields are not historical proof |
| SLIPPAGE_FILLS | MISSING — no sanitized fills exist; the deterministic adverse/neutral model remains ASSUMPTION_ONLY for stress testing |
| OBSERVED_SPREAD | ACCEPTED_DEVELOPMENT_ONLY — hash-bound to the verified tick year package and derived-candle manifest/attestation |

## Why the original Phase 8C manifest stays unchanged

The derived-candle package's manifest is generation-time evidence; rewriting it would destroy
its provenance value. The Phase 8E spread evidence binds to it read-only via recorded SHA-256
values (manifest, completion marker, attestation) and to the tick year package via the exact
`canonical_normalized_sha256` — never via filenames or absolute paths.

## What downstream validation must do

Discover evidence packages under `C:\Users\chips\forex-signal-bot-data\phase8\evidence\`
by `package_id` (content-derived) and `content_canonical_sha256`; run `reverify` before use;
treat any `MISSING`/`PRESENT_UNVERIFIED`/`CURRENT_ONLY_NOT_HISTORICAL` category as blocking.
The dataset-level readiness remains governed by the existing Phase 8 acceptance framework:
`accepted_for_final_validation = false`, `strategy_evaluation_authorized = false`,
`holdout_access_authorized = false` until every mandatory category is genuinely accepted.

## Recovery procedure

If an evidence package directory is missing or fails `reverify`, delete only that package
directory and re-run the same `validate-*` (or `register-spread`/`matrix`/`readiness`)
command with unchanged inputs; publication is content-addressed and recreates it atomically.
A `manifest.sha256` or content-hash mismatch after re-publication from unchanged sources
means deliberate tampering — stop and investigate; never hand-edit published packages.
