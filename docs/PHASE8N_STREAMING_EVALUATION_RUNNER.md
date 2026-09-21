# Phase 8N-G — Streaming Development Evaluation Runner

Status: **runner built and tested; NO empirical run authorized or executed.**
Every artifact remains `DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE`.

> **CORRECTION (Phase 8N-I):** the original production-readiness claim below
> was invalid — `run`/`resume` accepted synthetic fixture streams only and
> could not consume the plan-bound empirical datasets. See
> `PHASE8N_EMPIRICAL_INPUT_PIPELINE.md`; the pipeline is now connected and
> verified. This section is retained as the historical record.

## What this checkpoint built

A plan-driven, bounded-memory streaming runner for the corrected frozen
development plan, plus a control CLI. The runner consumes the shared Phase 8N
production/replay contracts (empirical adapter, scenario matrix, cell
contract, completion prerequisites) and refuses any path lacking them. No
shadow backtester, legacy backtest CLI, diagnostic runner or older plan-control
command is involved.

## Frozen plan identity

- Accepted plan package: `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81`
- Accepted plan fingerprint:
  `adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09`
- Invalidated plan (NEVER ACCEPT):
  `evidence-development_evaluation_plan-v1-ba2745f96fda3939`,
  fingerprint
  `d69bbed4542d9517dc46d043d12324f6a921a846bca39c30e57fdc3774779c72`
  Its disposition record legitimately remains on disk as published evidence
  of the invalidation; presenting the invalidated package as runnable fails
  closed (`INVALIDATED_PLAN_REJECTED`), and its fingerprint is still checked
  for on-disk mutation.

## Runner architecture

- `bot/validation/development_evaluation_runner.py` — pure orchestration
  module: plan firewall, input firewall, bounded JSONL streaming, cell state
  machine, hash-chained journal, atomic checkpoints, result publication,
  resource guards, synthetic rehearsal and result verification.
- `backtests/development_evaluation_control.py` — read-only CLI:
  `inspect`, `verify-inputs`, `estimate`, `status`, `verify-results`,
  `synthetic-rehearsal`, `dry-run-structure`, plus `run`/`resume`.
- The runner is strictly plan-driven: no strategy threshold or candidate
  parameter can be supplied from the command line. `run`/`resume` require an
  explicit confirmation flag, the exact plan package id, the exact plan
  fingerprint and the exact candidate identity (`phase6-frozen-v1`); without
  them they fail closed. No default command can start an empirical run.

## Input firewall

`verify_input_firewall` re-verifies every frozen input through the committed
Phase 8M readiness verifier (ticks 39,715,935 rows via the identity chain,
derived candles M5/M15/H1/H4/D1/W1, DXY 6,216 records over six constituents,
official 80-event news, observed spread, Phase 8H cost policy, Phase 8L
metadata bounds with 10 mandatory scenarios, code fingerprints, contamination
register, Phase 8A preregistration) and binds the result into the plan.
Documented rejection categories: changed hash, missing completion marker,
wrong candidate, invalidated plan, legacy result input, unregistered
scenario, interval outside plan, holdout timestamp (`>= 2025-01-01T00:00:00Z`,
rejected per streamed event), holdout path and live-broker substitution.

## Streaming, journal and checkpoints

- `BoundedJsonlStream` reads JSONL in bounded batches (default 5,000),
  preserving chronology; timestamp ordering and record-id duplicate detection
  span batch boundaries; malformed lines raise `CORRUPT_RECORD`; naive and
  holdout timestamps are rejected per event; sequence continuity is checked.
- `HashChainedJournal` is append-only with fsync-before-acknowledge; replay
  verifies both the chain linkage and each entry's own hash
  (`JOURNAL_CHAIN_BROKEN` / `JOURNAL_ENTRY_TAMPERED`).
- `CellRunner` states: PREPARED → RUNNING → CHECKPOINTED → COMPLETE (plus
  FAILED/INTERRUPTED/INVALID/RECONCILIATION_REQUIRED categories); only one
  terminal state is published; a completed cell refuses silent rerun or
  overwrite. Checkpoints persist cell/resume identity, cursor, deterministic
  random-generator state, and completion prerequisites; resume verifies
  journal head/count and cell identity before continuing, refusing foreign
  or corrupted state.

## Result contract

Atomic, non-overwriting publication (staging directory + `os.replace`) of
exactly 17 files: `run_manifest.json`, `cells.jsonl`, `cell_manifests.jsonl`,
`decision_ledger.jsonl`, `fills.jsonl`, `trade_ledger.jsonl`,
`equity_curve.jsonl`, `costs.jsonl`, `circuits.jsonl`, `fold_metrics.json`,
`scenario_metrics.json`, `aggregate_metrics.json`, `bootstrap_results.json`,
`acceptance_table.json`, `reconciliation_report.json`, `run_summary.json`,
`RUN_COMPLETE`. Incomplete contracts abort without publishing; `verify_results`
re-checks the full contract, cell count (64), completion states and
manifest/summary agreement.

## Synthetic 64-cell rehearsal

`synthetic-rehearsal` executes all 16 scenarios × 4 folds = 64 cells
structurally on clearly labelled
`SYNTHETIC TEST FIXTURE — NOT MARKET EVIDENCE` fixtures: deterministic cell
identity, interruption/resume equivalence, rerun suppression (duplicate
suppression), atomic non-overwrite publication and full result verification.
No market data is read and no strategy result is computed.

## Resource safety

`estimate` reports cell count, projected output upper bound (64 × 50 MiB),
temporary bound, 15 GiB minimum free reserve, available space, memory ceiling
(2 GiB) and timeout policy (per cell 1,800 s, overall 14,400 s). `enforce_resource_guards`
fails closed on low disk or output-limit projection before any run.

## Verification totals

- Focused Phase 8N-G tests: 39 passed.
- Phase 8A–8M suites: 738 passed.
- Full repository suite: 1,261 passed, 1 skipped (opt-in Windows keyring
  integration test), 10 subtests passed.
- Compile, MT5/network-free safe import, `pip check`, `git diff --check` and
  changed-file secret scan: all clean.

## Remaining before an empirical run

A separately authorized checkpoint must issue the exact run command printed
by the CLI (plan package, fingerprint, candidate, external output root, disk
reserve, output limit, confirmation flag). This checkpoint performed no
strategy evaluation, no optimization, no profitability calculation, no
holdout access and no MT5/account/network/order operation.

## Phase 8N-J addendum — optimized empirical cell path (engineering)

The runner gains an optimized empirical cell path behind the same
`run_cell_events` interface: fold-cached input-index provider
(`bot/validation/replay_input_index.py`), `OptimizedCellDriver` execution
with event-driven tick skipping, and optimized resume that auto-detects the
path from the checkpoint payload (fail-closed on missing cursor state).
Cell outputs and the empirical `run`/`resume` commands are unchanged. The
reference (slow) path is retained for equivalence. Measured result and the
performance-gate decision: see `PHASE8N_EMPIRICAL_REPLAY_PERFORMANCE.md`
(performance gate NOT met; no run authorization). No plan-bound component
changed.

## Phase 8N-K fast path (feature snapshots)

When a published `CausalMarketFeatureSnapshot` store matches the fold's input
index (plan, fold, source hashes, schema, implementation fingerprints), the
optimized cell executor can serve decision features from the immutable store
instead of recomputing them per cell. The mode is opt-in via the empirical
CLI (`--feature-mode fast|off`, default `off` — the `run` command is
unchanged). The shared pure gate reducer, all cell-local state, lifecycle,
risk and execution semantics are untouched; only feature *construction* is
memoized per fold. Partial-coverage (windowed) stores are labelled in their
identity and are refused by the production loader.
