# Phase 8M — Frozen Development Evaluation Plan and Input Readiness

Status: **plan frozen and hash-bound; evaluation itself remains unauthorized.**
Every artifact remains `DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE`.

## What this checkpoint did

1. Performed a read-only empirical-input readiness audit of every mandatory
   development input, verifying each through its own committed verifier.
2. Froze the immutable development-evaluation run plan
   `phase8m.development-evaluation-plan.v1` binding every dataset, evidence,
   policy and code fingerprint.

No strategy evaluation, optimization, parameter search, holdout analysis,
MT5 initialization/import, or network request occurred. The plan modules are
import-safe without MetaTrader5 (asserted by focused test and hygiene check).

## Verified input matrix (live audit result)

| Input | Identity | Result |
| --- | --- | --- |
| 2024 XAUUSDm ticks | `exness-xauusdm-2024-development-b2a0234a470dd397`, 39,715,935 rows, canonical `b2a0234a…f47e73` | identity-chain verified (completion ↔ manifest ↔ 12 monthly packages ↔ physical parquet hashes ↔ stored statistics); deep row-stream verification available via `--tick-verification-depth deep-stream` |
| Derived causal candles | `derived-candles-2024-v1-20260911T195553Z` + attestation `derived-candles-attestation-v1-6715e5c64d888215` | M5/M15/H1/H4/D1/W1 present and bound to the accepted tick canonical hash |
| 2024 USD official news | `evidence-official_news-v1-78279c5e26c1c6d1` (80 events) | `ACCEPTED_DEVELOPMENT_ONLY` |
| DXY (six constituents) | `dxy-development-2024-v1-20260912T091410.712364Z`, 6,216 causal rows | EURUSD/USDJPY/GBPUSD/USDCAD/USDSEK/USDCHF, bound to tick hash; no substitution allowed |
| Observed spread | `observed_spread-v1-e25bdb9bf028a5be` | `ACCEPTED_DEVELOPMENT_ONLY` |
| Phase 8H cost policy | `evidence-development_cost_policy-v1-6b1a986b1f8d7b81` | verified, all four swap scenarios + slippage scenarios mandatory |
| Phase 8L metadata bounds | `evidence-development_metadata_bounds-v1-8dad509e60c8014a` | verified; 10 mandatory metadata scenarios |
| Code fingerprints | strategy `c764cef0…`, execution `b1736e39…`, risk `763ccf15…`, broker policy `09845875…` | match frozen cost-policy bindings exactly |
| Session/time rules | UTC; rollover window 21:55–22:10 | frozen from strategy config |
| Contamination register | tracked baseline register | non-empty, hash-bound |
| Phase 8A preregistration | `config/validation_plan.example.json` (sha256 `24bb7812…`) | 4 folds, 28-day warm-up, 1-day purge/embargo |

Missing inputs: none for the development plan. (Raw owner-evidence categories
broker metadata / commission / swap / slippage remain `MISSING` in the
readiness matrix by prior honest classification; the 8H/8L development
policies cover them for development purposes only.)

## Frozen plan contract

- Candidate: `phase6-frozen-v1`, `strategy_configuration_mutation=PROHIBITED`,
  XAUUSDm-only, development period `[2024-01-01T00:00:00Z, 2025-01-01T00:00:00Z)`.
- Fold schedule (ANCHORED, from the Phase 8A preregistration): four equal
  evaluation windows tiling 2024-04-01 → 2025-01-01 with three one-day
  embargo gaps (68-day windows), each fold preceded by an exact 28-day
  warm-up ending at evaluation start and a one-day purge after anchored
  training from the development start. Final fold's embargo is 0 (development
  boundary). All boundaries computed with datetime arithmetic.
- Mandatory scenarios: all Phase 8H swap scenarios (×0 diagnostic → ×1 email
  reference → ×2 → ×3 required adverse boundary; Wednesday triple; no
  positive swap credit) and slippage scenarios, plus all ten Phase 8L
  metadata scenarios. `cheapest_selection=PROHIBITED` for both.
- Determinism: seed 8001, canonical ordering, scenario×fold result order.
- Metrics: min 30 closed trades/fold; primary expectancy / profit factor /
  max executable drawdown; secondary set; moving-block bootstrap
  (2,000 replicates, blocks 5/10/20).
- Stress suites: all cost + metadata scenarios, observed-spread rejections,
  causal-gap rejections, risk-circuit rejections; strategy parameter
  variation prohibited.
- Reconciliation: ledger, trade lifecycle, risk circuit; $0.01 tolerance.
- Outputs: `phase8/development-evaluations/<plan_fingerprint>/`,
  non-overwrite, labelled `DEVELOPMENT_PROXY_NOT_HISTORICALLY_VALIDATED`.
- Resource guards: 14,400 s runtime cap, 10 GiB output cap, checkpoint every
  100,000 events, resume requires exact plan+input hash match.
- Prohibitions: automatic tuning, parameter search, cheapest-scenario
  selection, holdout access, final-validation claims.

## CLI

`backtests/development_evaluation_plan_control.py`:

- `status` — read-only readiness audit (optionally `--tick-verification-depth deep-stream`);
- `build-plan` — verify + freeze + publish (idempotent; refuses to overwrite or conflict);
- `verify-plan --package-id …` — re-verify a published plan;
- `dry-run-structure` — synthetic structural proof only; never computes performance.

## Published artifact

`C:\Users\chips\forex-signal-bot-data\phase8\evidence\evidence-development_evaluation_plan-v1-82ef6fcab5c13547`

- plan fingerprint: `ae9b4e2a17562146f0ade44f758ca015f6ab9b017eaeaf665f7745278b131c79`
- idempotent re-publication returned the identical package id;
- evidence matrix `evidence_matrix-v1-4d2eab899e0f33c9` and readiness
  `evidence_readiness-v1-392d2097a1b6b3d8` list the plan as
  `FROZEN_AWAITING_AUTHORIZED_RUN` (informational only — it cannot flip
  `all_categories_accepted` and authorizes nothing).

## Gates (all unchanged, all false)

`empirical_strategy_evaluation_executed=false`,
`strategy_evaluation_authorized=false`,
`holdout_access_authorized=false`,
`accepted_for_final_validation=false`,
`phase9_authorized=false`.

## Next step

A separate owner-authorized checkpoint runs the frozen plan exactly as
published (all scenarios × all folds, no tuning). Nothing in this checkpoint
authorizes that run.
