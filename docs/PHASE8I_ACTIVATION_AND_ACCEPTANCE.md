# Phase 8I — Swap-Policy Activation and Dataset-Acceptance Review

Status: **activation recorded; per-category review published; evaluation
remains unauthorized.**  All artifacts stay
`DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE`.

## Owner decision

Activate the already-preregistered, frozen Phase 8H assumption-only
conservative swap stress policy **for development validation only**.
The decision is recorded in its own content-derived evidence package; the
frozen Phase 8H policy package was **not** modified (verified byte-identical
after activation).

## What was built

- `bot/validation/cost_policy_activation.py` — activation-record and
  dataset-acceptance-review contracts.  Fail-closed on: missing or
  unverified policy, drifted frozen ladder (order, multipliers, Wednesday
  ×3, no positive credit), missing evidence packages, hash mismatches,
  attested-manifest drift, ambiguous tick packages, row-count disagreement,
  missing/incomplete official news, and any gate that is not exactly `false`.
- `backtests/cost_policy_control.py` — new `activate` subcommand.  It
  re-verifies the published policy, builds + verifies the activation record
  (bound to the exact policy fingerprint `aa0ccc9368c0cf55b4775b4295f0424d4bdb0e5fd6cbfaf27137763be58e9404`),
  refuses a conflicting second decision (a different activation content
  identity already existing fails closed), publishes the dataset-acceptance
  review, and regenerates the readiness report.  Idempotent for identical
  decisions.
- Evidence-store kind allowlist extended additively
  (`cost_policy_activation`, `dataset_acceptance_review`, `observed_spread`);
  matrix/readiness gained the two new honest categories following the 8F/8G/8H
  pattern.  They never flip `all_categories_accepted` and never authorize
  anything.

## Activation record

- Package: `evidence-cost_policy_activation-v1-802914181c0ca505`
- State: `ACTIVE_FOR_DEVELOPMENT_VALIDATION` (development validation only)
- Underlying policy remains `PREREGISTERED_INACTIVE` with
  `activation_authorized: false` — activation lives entirely in this record.
- Frozen ladder preserved verbatim: diagnostic ×0 (never the primary
  acceptance result when trades cross rollover), email reference ×1
  (−3.85/−0.25 USD per lot/day), ×2 adverse, **×3 adverse as the required
  conservative boundary**; Wednesday triple swap; no positive swap credit;
  no cheapest-scenario selection; no parameter optimization from scenario
  results; `HISTORICAL_SWAP_UNCERTAIN` label carried on every scenario.
- Historical 2024 swap values remain `HISTORICAL_VALUE_UNAVAILABLE`; the
  points-vs-USD conflict stays preserved with conversion/averaging/selection
  prohibited.  Nothing was reinterpreted.

## Dataset-acceptance review

- Package: `evidence-dataset_acceptance_review-v1-4d47816f5f336fe2`
- Per-category result (all identities re-verified on disk before review):

| Category | Status | Strength |
|---|---|---|
| XAUUSDM_TICKS_2024 (39,715,935 rows) | ACCEPTED_EMPIRICAL | EMPIRICAL |
| XAUUSDM_CAUSAL_CANDLES (attested) | ACCEPTED_EMPIRICAL | EMPIRICAL |
| OBSERVED_SPREAD | ACCEPTED_EMPIRICAL | EMPIRICAL |
| OFFICIAL_USD_NEWS (80 events, 12 months) | ACCEPTED_DEVELOPMENT_ONLY | DEVELOPMENT_ONLY |
| COMMISSION (Standard, NONE) | ACCEPTED_DEVELOPMENT_ONLY | DEVELOPMENT_ONLY |
| SWAP_ROLLOVER (scenario ladder) | ACCEPTED_DEVELOPMENT_ONLY | ASSUMPTION_ONLY |
| SLIPPAGE_FILLS (0/1/3 points) | ACCEPTED_DEVELOPMENT_ONLY | ASSUMPTION_ONLY |
| BROKER_METADATA (current-only) | INSUFFICIENT | CURRENT_ONLY_NOT_HISTORICAL |
| DXY_DEVELOPMENT_INPUT (6,216 values) | ACCEPTED_DEVELOPMENT_ONLY | EMPIRICAL_CONSTITUENTS |
| HOLDOUT | BLOCKED | NONE |

- Verified chains recorded in the review: derived manifest bytes match the
  attested manifest hash; attested source canonical hash matches the derived
  manifest; exactly one tick year package carries that hash with matching
  row count; DXY identity present; the active official-news revision is
  accepted, complete, 12-months covered.
- `development_evaluation_sufficient = false` — the committed Phase 8E owner
  kit requires **effective-dated** broker metadata for development
  evaluation, and only current-only observations exist.  This is the single
  blocking gap; it is recorded, not waived.

## Readiness after the checkpoint

- Ticks / candles / spread / DXY / official news / broker-support conditions:
  available or accepted at their stated strength.
- `cost_policy_activation`: `ACTIVE_FOR_DEVELOPMENT_VALIDATION`;
  `dataset_acceptance_review`: `ACCEPTED_DEVELOPMENT_ONLY`.
- `broker_metadata`: MISSING (effective-dated evidence required);
  `commission` / `swap_rollover` / `slippage_fills` raw 8E categories remain
  MISSING by design — their acceptance is represented by the broker-support
  + cost-policy + activation records at development strength only.
- `accepted_for_final_validation = false`,
  `strategy_evaluation_authorized = false`,
  `holdout_access_authorized = false`.

## Verification

- 27 focused Phase 8I tests (deterministic fingerprints, frozen-ladder
  guards, tamper re-signing, idempotency, conflicting-decision refusal,
  market-chain and news fail-closed paths, readiness gates, MT5-free
  imports); 174 Phase 8A–8H focused tests; complete suite 987 passed,
  1 opt-in skip, 10 subtests.
- Compilation, safe MT5-free imports, pip check, `git diff --check`, and
  secret scans clean; `order_send` confined to the approved broker adapter.

## Safety

No strategy run, backtest, optimization, or profitability computation; no
holdout or 2025+ access; no MT5, bot, Streamlit, account, credential,
network, or trading operation; owner worktree and Phase 1–7 worktrees
untouched; every prior external artifact re-verified byte-identical; the
frozen Phase 8H policy package unchanged; nothing pushed or amended.
