# Phase 8N-J engineering probes — measurement summaries

Label: `EMPIRICAL ENGINEERING BENCHMARK — NOT STRATEGY EVIDENCE`

These probes measured where replay time goes on real accepted 2024 fold-1
data. Scripts resolve all inputs through the standard plan-bound bindings
resolver; no machine-specific paths are committed (raw JSON artifacts stay
outside Git; their summarized results are reproduced below).

## `phase8n_j_decision_cost.py`

Runs the optimized driver without the intent injector at two event caps and
derives per-decision cost from the delta (every quote is skipped, so the
measured cost is decision evaluation + skip overhead).

## `phase8n_j_profile_decisions.py`

cProfile over a small bounded optimized-driver run; writes
`decision_profile.json` (kept out of Git; summarized here).

## Measured summaries

### In-driver decision cost (`decision_timings.json`)

20 real fold-1 decisions, steady state: mean **952.7 ms/decision**,
min 472 ms, max 6,130 ms (outlier = first decision after warm-up);
20 decisions in 19.5 s wall with 10,972 idle quotes skipped.

### Orchestrator split (`orchestrator_cost_breakdown.json`)

6 decisions: `historical_acquisition` build ≈ 4.3 ms;
`StrategyOrchestrator.evaluate_symbol` ≈ **495.9 ms** (frozen gate stack +
analyzers over acquisition callbacks).

### Candidate-path input assembly (`decision_cost_breakdown.json`)

8 candidate-path evaluations (only reachable on real `candidate_ready`
decisions, which the frozen gates did not produce in the benchmark window):

| component | per decision |
| --- | --- |
| causal frame snapshots (6 timeframes) | 90.1 ms |
| news context | 2.6 ms |
| bias + liquidity maps | 8,142.7 ms |
| DXY context | 678.6 ms |
| gate-input build | 1,960.6 ms |

### Consequence

Decision-bound strategy evaluation dominates replay: ~0.95 s/decision ×
~13,269 decisions/fold ⇒ ~3.5 h/cell of irreducible (frozen) gate work plus
acquisition overhead that is the target of Phase 8N-K memoization.

# Phase 8N-K engineering probes — measurement summaries

Label: `EMPIRICAL ENGINEERING BENCHMARK — NOT STRATEGY EVIDENCE`

## `phase8n_k_profile_callgraph.py`

cProfile call-graph over ~10 real fold-1 decisions through the orchestrator
path; writes `decision_callgraph.json` (out of Git; summarized in
`docs/PHASE8N_EMPIRICAL_REPLAY_PERFORMANCE.md` §8.1). Finding: ≈ 86 % of the
decision cost is scenario-invariant feature construction
(`analyze_market_structure` 8 calls/decision + `build_gate_inputs` + bias +
liquidity + DXY); the shared reducer is ~21 ms/decision.

## `phase8n_k_candidate_density.py`

Runs the shared reducer over the sampled 1,000-decision stores (all four
folds): 320 skip / 680 wait — **0 candidate_ready** in the sample
(`candidate_density.json`, out of Git).

## `phase8n_k_real_activity_density.py`

Full-fold real-strategy activity probe: serves every decision of a fold from
the published full-coverage store, runs the shared reducer with chained
setup state and frozen level construction, resolves fills in certain
(decision-ordered) quote sequence and bounds exits by exact first-touch over
accepted tick rows. Fold-01 result (`real_activity_density_fold01.json`, out
of Git): **13,269 decisions, 0 candidates, 0 fills** in 359 s wall.

## `phase8n_k_full_cell.py`

Representative full-cell measurement: the optimized driver over the complete
fold-01 quote stream with the memoized provider, no injection
(`full_cell_run_fold01.json`, out of Git). Result: **1,106.6 s wall
(18.4 min) per cell**, 621.9 s CPU, 13,269 decisions, 0 fills,
16,436,775 idle quotes skipped, 84/403 row groups decoded, 557 MB peak.

### Consequence

64 cells × 18.4 min ≈ 19.7 h decision+skip work; uncontended fold
construction ≈ 53 min × 4 ≈ 3.5 h ⇒ **≈ 23.2 h single-worker** (inside the
24 h gate; two workers ≈ 13 h), conditional on fold-02..04 density
confirmation (stores build unattended; each fold probed identically once
published).

- `phase8n_k_storage_stability.py` — read-stability diagnosis after the
  2026-09-20 transient hash-mismatch events: 3 chunked read passes over every
  frozen tick partition with per-pass manifest comparison, plus a RAM pattern
  test. Writes `storage_stability_report.json` (gitignored). Result: frozen
  data intact; one partition transiently mis-served under heavy I/O, self-
  healed; see performance doc §8.9.
