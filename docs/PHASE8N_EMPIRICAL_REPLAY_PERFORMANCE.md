# Phase 8N-J/K — Empirical Replay Performance (Engineering Acceleration)

Status: **8N-J COMPLETED (checkpointed at `7f3e3ed`); 8N-K in progress —
performance gate pending measured benchmark**

Classification: `DEVELOPMENT_ENGINEERING_ONLY`. Every artifact produced under
this phase is labelled `EMPIRICAL ENGINEERING BENCHMARK — NOT STRATEGY
EVIDENCE`. No strategy outcome, profitability number, aggregate metric or
candidate acceptance is derived here.

## 1. Purpose and authorization boundary

The frozen 64-cell development evaluation was measured at ~258 merged
events/second — ~11.4 h/cell before strategy cost, >30 days for 64 cells.
Phase 8N-J optimizes representation, indexing and scheduling mechanics only.
Strategy, execution, risk, scenario, fold, metric and acceptance semantics
are frozen; no plan-bound component changed. The empirical `run` command and
plan remain byte-for-byte unchanged.

## 2. Profile findings (measured, not guessed)

Measured on real accepted 2024 fold-1 data (`engineering/phase8n-j/`):

| component | measured cost | evidence |
| --- | --- | --- |
| decision evaluation (strategy gates) | **~0.95 s/decision** (steady 0.47–1.1 s; `StrategyOrchestrator.evaluate_symbol` ≈ 0.50 s) | `probes/decision_timings.json`, `probes/orchestrator_cost_breakdown.json` |
| candidate-path input assembly (only for real candidates) | ~10.9 s/decision (bias/liquidity 8.1 s, gate-input build 2.0 s, DXY 0.7 s, causal snapshots 0.09 s) | `probes/decision_cost_breakdown.json` |
| active-quote processing (fill/management) | ~7.4 ms/quote | benchmark report |
| idle-quote skip | ~0.04 ms/skip (negligible) | benchmark report |
| tick row-group decode | negligible (row-group pruning works) | benchmark: 1 of 403 row groups decoded |
| fold input-index build | 4.3 s (12,269–13,445 decisions/fold; 12 partitions; 39.7 M source rows) | benchmark report |

Conclusion: the pipeline bottleneck is **plan-bound strategy evaluation per
decision**, not input mechanics. Skip/decode costs are already negligible.

## 3. What was built

### Columnar input index (`bot/validation/replay_input_index.py`)

- Fold-scoped immutable index of scenario-invariant facts only: decision
  timestamps (available-at, source open, timeframe, close, candle identity),
  tick partition/row-group boundaries with min/max `time_msc`, and source
  identities (tick packages, monthly manifests, candle/DXY partition SHA-256s,
  evidence package SHA-256s). No strategy/decision/execution state.
- Identity binds plan package + fingerprint, fold, all source hashes,
  pipeline fingerprint (`pipeline_fingerprint(worktree)`), index schema,
  builder version and code version. Published atomically outside Git under
  `evidence/replay-input-index/fold-XX-<sha12>/` with completion marker,
  canonical SHA-256 and readback verification; incompatible indices are never
  reused. Tolerant of both synthetic-fixture and real evidence package
  schemas (identity cross-checked against the year manifest).
- Deterministic per fold (no wall-clock in identity): one published index
  serves all 16 cells of a fold.

### Event-driven optimized driver (`OptimizedCellDriver`)

- Persistent row-group-aware quote cursor over Parquet metadata statistics;
  only row groups overlapping the required span are decoded (benchmark:
  1 of 403).
- Exact state-dependent processing: full tick processing only while an entry
  intent is pending or a position is open (trigger/fill, cancellation,
  expiry, stop/target/partial/break-even/trailing, session/swap, END_OF_DATA
  close); idle spans skip intermediate quotes with zero state effect
  (skipped ticks cannot change state: no pending intent can trigger and no
  open position can be managed). Decision-before-quote merge order is
  preserved (deferred decisions fire before the quote at their availability
  instant), matching the reference stream exactly.
- Bounded columnar batches (`batch_rows`), configurable; deterministic
  regardless of batch size; duplicate/inversion detection at boundaries.
- Checkpoints bind input-index SHA-256, quote-cursor state, batch size and
  the full cell state; optimized resume restores the cursor exactly
  (interrupted == uninterrupted, proven by test).

### Runner wiring (`bot/validation/development_evaluation_runner.py`)

- Fold-cached index provider (no per-cell re-hashing); optimized run/resume
  path auto-detected from checkpoint payload, fail-closed when an optimized
  checkpoint lacks cursor state.
- Reference path retained untouched for equivalence comparison.

### Shared-pipeline defect repairs (found by the benchmark, semantics-preserving)

1. `finish_fold` attempted END_OF_DATA close on fully-closed positions →
   `POSITION_ALREADY_CLOSED` crash at fold end for any cell that closed a
   trade early (8N-I rehearsal never opened a position). Now closes only
   positions with open volume.
2. Fill-time `register_binding`/consumption mutates the durable setup store
   outside `publish_decision`'s CAS; the in-memory `state_record` was never
   refreshed, so the next decision would crash with "setup state changed
   during evaluation" at the first real fill. The authoritative durable
   record is now reloaded after quote processing.

### CLI (`backtests/replay_performance_control.py`)

`build-input-index`, `verify-input-index`, `benchmark-pipeline`,
`estimate-optimized` (plus `profile-pipeline` and `synthetic-rehearsal`
entry points). The empirical `run`/`resume` commands are unchanged.

## 4. Real-data engineering benchmark

- Interval (pre-declared, mechanical): fold 1's first 6 evaluation hours
  (2024-04-01 00:00–06:00 UTC), ~30,000 source rows.
- Optimized pass: 13 decisions, 1,216 active quotes, 5,915 skipped quotes
  (83 %), 1 of 403 row groups decoded, 556 MB peak working set.
- Reference pass over the identical horizon: 13 decisions, 7,131 quotes.
- Equivalence: decision identities exactly equal; semantic quote state
  (balance, equity, commission, swap, realized P&L, fills, ledger,
  rejections, pending, positions) exactly equal with identical synthetic
  injected intents on both paths (2 fills each).
- Throughput on the window: optimized 21.4 s vs reference 88.9 s (4.15×).

## 5. Revised runtime estimate (honest)

From measured per-decision and per-active-quote costs:

- Per cell: **6.81 h** (13,269 decisions × 0.95 s ≈ 3.5 h strategy
  evaluation + active-quote work at the benchmark's 4.05 % active fraction).
- Single worker, 64 cells: **≈ 436 h** (18.2 days).
- Two workers (verified determinism model, not yet scheduled end-to-end):
  **≈ 218 h** (9.1 days).

Reference-path projection for comparison: ~8,800 h.

## 6. Performance-gate decision

The task's authorization gate requires ≤ 24 h (preferred ≤ 12 h). Even with
event-driven skipping eliminating 83 % of quotes and row-group pruning
eliminating 99.75 % of decode work, **decision-bound strategy evaluation
(≈ 0.95 s/decision × ~13,300 decisions/fold × 16 cells/fold) keeps the
projected runtime one order of magnitude above the gate.** That cost is the
frozen candidate's own gate stack — reducing it would change strategy
semantics, which this phase forbids.

**EMPIRICAL REPLAY PERFORMANCE INSUFFICIENT — NO RUN AUTHORIZED.**

### Required next architecture (semantics-preserving proposal)

- **Decision-level memoization of scenario-invariant context**: the
  orchestrator's bias/liquidity/DXY/session inputs are scenario-invariant
  facts (identical across all 16 cells of a fold) and may be precomputed
  once per fold into the input index — this alone recovers a large share of
  the 0.5 s `evaluate_symbol` cost that is acquisition, not gate math.
- **Candidate-path cost isolation**: the ~10.9 s candidate path only runs
  for real `candidate_ready` decisions; precomputing its indexed inputs
  (candle row ranges, DXY rows, news windows) is already contract-legal.
- **Process-level parallelism** (2 workers) after single-worker
  determinism scheduling is proven end-to-end: brings the remaining
  strategy-bound floor down by at most 2×.
- These are representation/indexing optimizations and require a new
  runner-compatibility record, not a new plan.

## 7. Artifacts

- `engineering/phase8n-j/benchmark/benchmark_report.json` (labelled
  engineering benchmark, not strategy evidence)
- `evidence/replay-input-index/fold-01..04-*/` (published, verified)
- `probes/decision_timings.json`, `probes/orchestrator_cost_breakdown.json`,
  `probes/decision_cost_breakdown.json` (engineering measurements)
- Tests: `tests/phase8n_j/test_replay_input_index.py` (9 tests: index
  determinism, tamper rejection, skip proof, pending-intent full processing,
  open-position full processing, batch independence, cross-batch
  duplicates/inversions, slow/optimized equivalence, resume equivalence,
  cache incompatibility)

## 8. Phase 8N-K — Causal market feature memoization (in progress)

### 8.1 Measured decision-path decomposition (cProfile, 10 real fold-1 decisions)

`probes/phase8n_k_profile_callgraph.py` → `probes/_k_profile_cell/decision_callgraph.json`:

| component | cumulative share of decision cost | classification |
|---|---|---|
| `analyze_market_structure` (8 calls/decision: bias×5, liquidity, DXY, internal) | ≈ 70 % | **A** — scenario-invariant market fact |
| `build_gate_inputs` (bias/liquidity/DXY → gate frame) | ≈ 16 % | **A** |
| `evaluate_strategy_gates` (pure shared reducer) | ≈ 1 % | shared reducer — runs per cell |
| publish/persist/checkpoint | ≈ 2 % | cell-local |

The dominant decision cost is **feature construction from frozen inputs** —
identical across all 16 scenario cells of a fold and therefore exactly what
the phase authorizes memoizing. The gate reducer itself is nearly free.

### 8.2 Feature classification

- **A (scenario-invariant)**: decision timestamp/identity, candle/DXY row
  indices, news window facts, session context, bias snapshot + resolution,
  gate inputs (`StrategyEvaluationInputs`), gate status/payload/event id —
  all derived only from frozen fold inputs; identical for every cell.
- **B (cell-local)**: trade count, pending intent, open position, risk/circuit
  state, fills, equity, consumed event keys, gate *record* (mutation buffer
  restored from prior cell state).
- **C (mixed → split)**: gate 1–7 outcome = memoized (A) inputs + cell-local
  reducer. Store never caches B or C outputs.

### 8.3 Store contract

`bot/validation/market_feature_store.py`: one immutable row per decision
(Parquet + JSON identity). Identity binds plan package/fingerprint, fold id,
input-index sha256, source identities, pipeline fingerprint, config
fingerprint, schema, builder version, row count, row digest, and a `coverage`
field (`full` or `partial:N-of-M`). Published atomically outside Git with a
completion marker, file-hash readback and non-overwrite publication; the
production loader refuses partial-coverage stores, so engineering sample
stores can never serve a real run.

### 8.4 Fast cell evaluation

Runner-attached `FoldFeatureProvider` serves per-decision snapshots; the
handler's fast path replicates the reference gate 1–7 sequence over memoized
features and feeds the identical `StrategyEvaluationInputs` object to the
untouched shared reducer. Candidate decisions deliberately fall back to the
reference input path (the reference's candidate branch uses a distinct
construction). Opt-in via `--market-features fast`; `off` is the default, so
the empirical `run` command's behavior is unchanged.

### 8.5 Benchmark and estimate

- `benchmark-features`: mechanically sampled (first N evaluation decisions
  per fold, pre-declared, outcome-blind; pooled ≥ 1,000 decisions across all
  four folds) → `feature_benchmark_report.json`: per-fold construction, cold
  vs warm serve, reducer throughput.
- `estimate-optimized`: consumes the measured basis (construction amortized
  once per fold; serve + reducer per cell; active-quote cost at the measured
  8N-J rate) and projects 1/2-worker runtimes against the 24 h gate.

### 8.6 Measured sampled-benchmark results (1,000 decisions, all four folds)

`EMPIRICAL ENGINEERING BENCHMARK — NOT STRATEGY EVIDENCE`
(`feature_benchmark_report.json`):

| measure | pooled value |
|---|---|
| feature construction (reference path, memoized into store) | **523.2 ms/decision** (once per fold) |
| warm serve from store | **0.348 ms/decision** (≈ 1,500× faster) |
| shared reducer (cell-local gates) | **13.6 ms/decision** |
| fold store build (250 decisions each) | 120–142 s per fold sample |

Candidate-density probe (`probes/candidate_density.json`): over the 1,000
sampled decisions at zero open trades, orchestrator actions are 320 `skip` /
680 `wait` — **0 `candidate_ready`** — so the expensive candidate input path
(`~10.9 s`) was never exercised by the sample; fold-wide candidate density
remains the one open variable.

Projection (`estimate-optimized`, measured basis, construction amortized once
per fold, serve+reducer per cell):

- **Headline (conservative)**: 222.8 h single-worker / 111.4 h two-worker —
  carries the equivalence harness's *injected* active-quote density (4.05 %
  of rows, a harness artifact: the intent injector holds positions open; the
  frozen strategy produced no candidates in the measured windows) at full
  fold scale.
- **Measured low bound (zero-candidate sample)**: **11.0 h single-worker /
  5.5 h two-worker** — inside the ≤ 24 h gate and the ≤ 12 h preference.
- The true runtime lies between the bounds; the decisive missing fact is
  fold-wide candidate density, measurable in minutes from the full-coverage
  fold store (`build-feature-stores`, ~2.1 h compute per fold, engineering
  only) and required for the production fast path regardless.

### 8.7 Full-coverage fold stores (engineering build)

`build-feature-stores` publishes the production full-coverage store per fold
atomically and non-overwriting (resumable: already-published folds are
skipped). Fold-01 published as `fold-01-1d710826193a6767` (13,269 rows,
verified readback). Its construction-rate curve was flat (~1.2–2.2 dec/s
under test-suite contention; ~4.2 dec/s uncontended) — the long wall time
was contention and machine sleep, not superlinear cost; uncontended
construction is ~53 min per fold.

### 8.8 Full-fold density probe and full-cell measurement (decisive)

**Fold-01 full-fold real-strategy density probe**
(`probes/real_activity_density_fold01.json`): all 13,269 decisions served
from the published store through the shared reducer with chained setup
state and frozen level construction, in decision order. Result: **0
candidate_ready fold-wide** (7,273 skip / 5,827 wait; 169 news-blocked).
The frozen strategy opens no positions on fold-1 data.

**Fold-01 full-cell end-to-end measurement**
(`engineering_benchmark_8nk/full_cell_run_fold01.json`): the optimized
driver over the complete fold-01 quote stream (~16.4 M quotes) with the
memoized provider, no injection:

| metric | measured |
|---|---|
| wall time | **1,106.6 s (18.4 min) per cell** |
| CPU time | 621.9 s (0.56 CPU/wall — quote I/O-bound) |
| decisions processed | 13,269 (13100 recorded; 169 news-blocked) |
| fills | **0** — matches the density probe |
| idle quotes skipped | 16,436,775 (cost now measured, not bounded) |
| row groups decoded | 84 / 403 |
| memory peak | 557 MB — within the frozen ceiling |

**Projection from measured values** (`estimate-optimized`, full-fold basis):
64 cells × 18.4 min ≈ 19.7 h + ~3.5 h fold construction ≈ **23.2 h
single-worker** (inside the ≤ 24 h gate) and ≈ 13 h with two workers.
Condition still open: fold-02..04 candidate densities (their stores build
unattended; each fold is probed the same way once published).

### 8.9 Frozen-data integrity event and storage stability probe (2026-09-20)

During fold-store construction under heavy concurrent I/O the identity chain
detected two transient anomalies; both were diagnosed and closed the same day:

1. **December 2024 recovery-0002 partition** returned a digest differing from
   its manifest under concurrent build + test load; minutes later it
   re-verified OK and has remained stable since.
2. **April 2024 partition** returned a *stable but wrong* digest
   (`ebc8756e…`) for several minutes, then restored to the manifest digest.
   A fresh file copy re-hashed twice matched the manifest through an
   independent read path while the anomaly was still observable via the
   original path.

Additionally, **two file writes were silently lost** during the same window
(a probe script written through the editor layer never appeared on the OS
filesystem; both were re-created via shell and verified).

Diagnostics run (all labelled EMPIRICAL ENGINEERING BENCHMARK — NOT STRATEGY
EVIDENCE):

- RAM pattern test (200 × 8 MiB fill/verify rounds): **0 failures**.
- `probes/phase8n_k_storage_stability.py`: all 26 frozen partitions read in
  3 chunked passes; only the April partition flagged, and only while its
  poisoned cache state persisted.
- Sequential full re-verification of all 26 partitions: **0 mismatches**.
- SMART / `Get-PhysicalDisk`: single SSD, **Healthy**; System event log: no
  disk/NTFS error events; C: free space 46.9 GB (not a capacity issue).

Conclusion: the frozen source data is **intact**; the anomalies were
cache/controller-level read faults (and write loss) occurring only under
heavy concurrent I/O. The binding-verification identity chain caught every
fault before any artifact was published. Consequences for the evaluation:

- Fold-store construction is **suspended with folds 03/04 unbuilt**; fold-01
  and fold-02 stores were published *before* the anomaly window and their
  readback verification passed.
- Any future evaluation run must execute on an otherwise idle machine, with
  a pre-run full-manifest verification gate, and hardware diagnostics
  (vendor SSD tool, `chkdsk`, memory test) are recommended before authorizing
  the ~20-hour run.
- The runner's binding verification is the effective safety net; per-row
  tick reads are not individually hashed, so a mid-run transient read fault
  on an unverified row would be silent — this risk is accepted only for the
  engineering probes run so far, and is flagged for the run-authorization
  decision.

### 8.10 Stage-2 commit, compatibility record and detached verification (2026-09-20)

- Stage-1 checkpoint: `7f3e3ed` (perf: add indexed empirical replay groundwork).
- Stage-2 commit: `92b2be188ba2860613bc925291ff5b56a4eda7f3`
  (perf: memoize causal market feature snapshots) — code, 12 focused tests,
  docs and sanitized probes only; process helpers and raw logs remain
  untracked.
- Runner-compatibility record published append-only:
  `evidence-runner_compatibility-v1-a81ef827217a69c6`, binding runner
  fingerprint `c847398bb075e2ef…` to commit `92b2be1…` with the accepted plan
  `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81` preserved
  byte-for-byte (`preserved: true, republished: false`) and the invalidated
  plan still recorded as never-accepted. Readback-verified.
- Detached clean-snapshot verification: a temporary detached worktree at
  `92b2be1` (0 local modifications) passed the full battery —
  tests/phase8n_k + phase8n_j: 21 passed; tests/phase8n_g + phase8n_i:
  56 passed (plus the heavy full-reference-rehearsal test passed separately
  in 12:45 after the two-stage run measured it at 766 s on a cool machine);
  compileall, safe imports and `pip check` clean. Worktree removed after
  verification.
- Full-suite totals (two-stage run on the working tree): stage 1
  1,299 passed / 1 skipped / 10 subtests in 33:29; stage 2 heavy test passed.

Machine-health finding affecting the projection: the laptop currently runs
~3× slower than its cool baseline (10^7-iteration Python loop 2.49 s vs
~0.6–1.0 s healthy) when heated under sustained load; the 23.18 h
single-worker projection was measured on the earlier cool-machine basis.
Run-authorization preconditions: (1) hardware diagnostics per §8.9;
(2) fold-03/04 feature stores built and their candidate densities measured;
(3) run executed on an idle machine with the pre-run full-manifest
verification gate.
