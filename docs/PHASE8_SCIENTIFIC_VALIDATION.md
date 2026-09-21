# Phase 8A Scientific Validation Framework

Guarded acquisition preparation is documented in
`docs/PHASE8B_STAGE1_ACQUISITION.md`. Stage 1 does not alter the preregistered
evaluation or holdout boundary defined here.

The completed 2024 monthly development reconstruction, including the preserved
August forensic recovery and immutable year-manifest identity, is documented in
`docs/PHASE8B_2024_RECONSTRUCTION.md`. Its `DEVELOPMENT_ONLY` classification
does not authorize the final holdout.

Parent commit: `930b3c9f3e69ba5827581c906d192e8acbc167a1`.

Phase 8A verifies the study framework and empirical-data acceptance boundary.
It does not open a real holdout, validate market performance, or authorize
deployment. Synthetic output is always labeled `SYNTHETIC TEST FIXTURE - NOT
MARKET EVIDENCE`.

## Audit and frozen candidate

The initial candidate is the unchanged Phase 6 strategy configuration with
fingerprint `6fce546fb4a3ad41c2fe6fb9`. The unchanged Phase 7 execution model
`phase7-execution-v1` has fingerprint
`52a0a62dbdef5e327e91c5022f0d6ff1fa9dd1bd99825a61559bc4fdd4ef5b5d`.
Phase 4 policy remains `phase4-validation-v1`, including 0.35% base risk, 0.50%
per-trade ceiling and 8% total hard stop. No strategy, execution, cost or risk
parameter was selected from legacy results.

The historical audit found 16 prior result sets and a Phase 1 declaration of 44
cache pickles. The current unchanged tree contains 48 tracked pickles. The
contamination register preserves the reported count, records the discrepancy,
and treats all 48 current files as contaminated. Previously viewed periods span
2025-10-01 through 2026-07-18; overlapping future data can be development or
secondary validation data, never a genuinely untouched final holdout.

## Import-order repair

`bot.utils.session_clock` imported `bot.strategy.config`, which initialized the
eager `bot.strategy` package. That imported DXY, which initialized
`bot.analysis`; its eager liquidity-map import requested `ASIAN_SESSION` from
the still-partially initialized session-clock module. Immutable window
definitions now live in `bot.utils.session_windows`, a neutral dependency used
by both modules. Session boundaries and strategy decisions are unchanged. A
fresh isolated Python interpreter regression protects the architecture.

## Empirical package

`config/empirical_data_package.schema.json` defines a versioned package whose
raw files remain outside Git. It requires exact `XAUUSDm` execution quotes,
causal analysis candles for M5, M15, H1, H4, D1 and W1, either direct DXY or all
six Phase 6 constituents, complete USD news history, dated broker metadata and
slippage evidence. Every stream records coverage, SHA-256, provenance,
licensing, record count and gap expectations.

Execution quotes are JSON Lines with UTC `timestamp`, positive finite `bid` and
`ask`, and optional sequence metadata. Analysis candles carry `open_time`,
`available_at`, OHLCV and timeframe. DXY rows carry UTC `timestamp` and positive
`close`. News rows carry stable event identity, UTC event/retrieval timestamps,
currency, impact, name and provider. Metadata records exact symbol economics,
commission, long/short swap, rollover timezone, triple-swap weekday, currencies
and effective dates. Missing news never means no events.

## Acceptance gate

`validate_dataset_package` independently recomputes file hashes and validates
paths, parsing, UTC, ordering, duplicates, bid/ask, OHLC, coverage, gaps,
warm-up, DXY, news, costs, metadata dates, fidelity and recorded licensing.
Stable outcomes are `ACCEPTED_FOR_FINAL_VALIDATION`,
`ACCEPTED_FOR_DEVELOPMENT_ONLY`, `DIAGNOSTIC_ONLY` and `REJECTED`. Synthetic
provenance can never be relabeled empirical. Only the first outcome can reach a
real final holdout.

Offline owner command after preparing data:

```powershell
$python = 'C:\Users\chips\forex-signal-bot\.venv\Scripts\python.exe'
& $python -m backtests.validation_control accept-dataset `
  --manifest C:\outside-git\phase8\package.json `
  --package-root C:\outside-git\phase8 `
  --report C:\outside-git\phase8\dataset_acceptance.json
```

The command performs local reads only, refuses report overwrite and contacts no
broker or provider.

## Preregistration and chronological splits

The validation plan schema freezes the hypothesis, fingerprints, `$1,000`
capital, risk policy, dataset, development/validation/holdout periods, metrics,
folds, purge, embargo, warm-up, stresses, sensitivity grid, seeds, candidates,
trial count and invalidation rules before holdout access. Anchored and rolling
walk-forward folds are chronological. Warm-up is historical and cannot emit
evaluation trades; purge separates fitted history from evaluation, and embargo
separates consecutive evaluation folds. Rows are never shuffled.

Every fold retains its own manifest and must retain ledger and causal checks.
Aggregate reporting cannot discard weak folds. The frozen candidate is evaluated
before alternatives.

## Trial governance

The locked append-only candidate registry records candidate parentage, exact
differences, rationale, periods and metrics viewed, seed, outcome and holdout
access. It enforces the preregistered trial maximum and reports a Bonferroni
disclosure when multiple candidates exist. Losing and abandoned candidates stay
in the registry. Sensitivity output is diagnostic and cannot select a candidate.

## Metrics and uncertainty

Metrics include gross/net P&L, trade count, win rate, gross/net profit factor,
expectancy, R expectancy, median, balance and executable-equity drawdown,
drawdown duration, recovery, exposure, turnover, costs, rejection and circuit
counts, side/year/regime/session/spread slices, and best trade/day/week/month
concentration. No-trade, all-win and all-loss boundaries use explicit states
rather than infinity or division errors. Independent 90-day outcomes report
profitable, losing and flat windows without fitting toward `$1,800`.

Moving-block bootstrap preserves local serial structure and uses deterministic
seeds. Every resample rebuilds percentage-risk equity from the current balance,
then reports expectancy, win-rate and profit-factor intervals, drawdown
distribution, loss probability by horizon and probabilities of crossing the 2%,
4% and 8% Phase 4 limits. Block-length sensitivity is mandatory. Statistical
uncertainty is not a future-performance guarantee.

## Stress, sensitivity and stability

Preregistered stresses cover observed costs and 1.25x/1.5x/2x costs, wider
spreads, adverse slippage, entry latency, missed trades, gaps, loss clusters,
adverse order, reduced liquidity, minimum lots, partial-fill limits,
swap-sensitive holds, starting equity and dated metadata changes. Only base
observations are empirical; other scenarios are labeled hypothetical.

Sensitivity accepts small declared perturbations for confluence threshold,
regime boundaries, stops/targets, cost levels and delay. It reports cliff edges
but never promotes the best perturbation. Regime, session, spread, time-block and
long/short slices always carry trade counts; inadequate samples prohibit claims.

## Acceptance policy

Policy `phase8a-acceptance-v1` requires positive final net expectancy, net profit
factor above 1, executable-equity drawdown below 8%, reconciled ledgers, passing
causal/data invariants, acceptable concentration and cost stress, adequate
sample size, more than one successful walk-forward fold, uncertainty disclosure
and intact holdout rules. Thresholds cannot be loosened after holdout access.

Win rate 60%, net profit factor 2.0 and `$1,000` becoming `$1,800` are reported
outcomes only. They are never fitting targets and cannot override robustness or
risk requirements.

## Holdout lock

The lock binds dataset hash, UTC boundaries, strategy and execution fingerprints,
plan hash and candidate ID. Synthetic or non-accepted packages are denied.
Access requires the explicit `authorize-holdout` command flag and written
justification. First, denied and repeated attempts are append-only records;
repeats require a separate explicit authorization. Candidate changes after
opening invalidate untouched status. Phase 8A did not execute this command on a
real dataset.

## Outputs and limitations

The framework writes the 13 required deterministic artifacts atomically into a
unique directory and refuses overwrite. Empirical output from a dirty tree is
rejected. Raw/proprietary data and generated empirical outputs remain ignored.

Phase 8B still requires accepted owner-supplied broker data, a defensible
uncontaminated holdout, a finalized plan hash, and deliberate owner authorization.
Phase 9 is not authorized. Nothing here is evidence of profitability or
readiness for live trading.

The proposed Phase 8B hybrid acquisition/storage plan and its still-locked
holdout are documented in `PHASE8B_HYBRID_ACQUISITION.md`. It does not relax
this framework's fail-closed dataset acceptance gate.
