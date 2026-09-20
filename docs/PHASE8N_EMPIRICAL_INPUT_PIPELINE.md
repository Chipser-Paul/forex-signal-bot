# Phase 8N-I — Plan-Bound Empirical Input Pipeline

Status: **runner connected to the frozen plan's empirical inputs; corrected and
verified; NO empirical run executed.** Every artifact remains
`DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE`.

## Corrected defect

The Phase 8N-G production-readiness claim was **invalid**: `run` and `resume`
required `--synthetic-stream`, so the runner accepted synthetic fixture streams
only and could not consume the plan-bound empirical 2024 datasets. The
authorized empirical command failed at argument parsing before any cell ran; no
output root, run identity, journal or result existed. This checkpoint corrects
the runner and supersedes that claim.

## Fingerprint audit (decisive)

`CODE_COMPONENTS` in `development_plan_revision.py` binds only the shared
replay contracts: `empirical_adapter`, `gate_reducer`, `levels_builder`,
`consumption`, `restart`, `state_migration`, `lifecycle_parity`. The runner
module and its CLI are **not** plan-authorized fingerprints.

**Disposition branch B** applies (execution-compatibility bound, not
plan-bound): the corrected plan remains byte-for-byte; a versioned append-only
compatibility record (`bot/validation/runner_compatibility.py`, evidence kind
`runner_compatibility`) binds plan identity ↔ corrected runner fingerprint ↔
empirical-source contract (`phase8n.plan-bound-empirical-inputs.v1`) ↔ tests ↔
code commit. The record refuses publication against the invalidated plan. It
is published after the commit with the real commit SHA (per-file SHA-256
hashes fully pin content).

## CLI correction

- `synthetic-rehearsal` keeps its fixture stream (internally built).
- Empirical `run`/`resume` no longer accept or require `--synthetic-stream`;
  a caller-supplied synthetic stream to an empirical command is structural
  misuse and fails closed before the confirmation gate.
- No caller-selected market-data path exists. All empirical inputs resolve
  through `EmpiricalInputBindings` from the verified plan/evidence registry.
- The exact previously authorized command passes argument parsing (regression
  tested) and is still NOT executed.

## Empirical input resolver

`bot/validation/empirical_input_pipeline.py`:

- **XAUUSDm ticks** — accepted 2024 year package + 12 monthly partitions,
  completion markers and canonical hashes verified; chronological streaming.
- **Derived candles** — M5/M15/H1/H4/D1/W1 bound to the source tick hash with
  manifest/completion identity; causal `available_at_ms` selection.
- **DXY** — six constituents keyed by the authoritative parquet
  `broker_symbol` (`EURUSDm`-style), causal timestamps, staleness enforced.
- **USD news** — official-event package through the development-only
  historical-news replay adapter.
- **Costs/metadata** — observed bid/ask spread, Phase 8H cost policy (real
  `cost_components` key), Phase 8L bounds with 10 mandatory scenarios applied
  through the existing execution/risk contracts.
- **Code identities** — strategy, empirical adapter, setup reducer,
  consumption/recovery, lifecycle, risk, broker execution, runner
  compatibility. No input is inferred from directory scanning alone.

Never: forward-filled OHLC, future DXY/news/price, signal-candle fills,
bar-close substitution for later executable quotes, fabricated ticks, full
year in memory, or 2025+ data.

## Streaming event pipeline

Per cell: verified ticks stream chronologically → decisions fire only when a
completed decision candle becomes available → higher timeframes are selected
causally (`available_at <= decision timestamp`) → DXY joins causally with
frozen staleness → intents enter the Phase 3 lifecycle → triggers, fills,
management and exits consume later executable bid/ask ticks → Phase 8H/8L
overlays apply through existing contracts. `on_signal` follows the
parity-proven contract: `evaluate_historical_orchestration` returns
`(result, record)` where `record` is the authoritative next state, and
`evaluate_setup_inputs` receives the prior state. Insufficient/thin frames
fail closed exactly like the shared orchestrator (no crash, no fabrication);
empty H1/M5/M15 or unsafe causal inputs produce wait/rejections. Deterministic
batch boundaries and sequence continuity are preserved; decision-stream reuse
across scenarios is **rejected** (execution outcomes can alter later
decisions) — each scenario replays independently.

## Resume contract

Source cursors (tick partition/member/row, candle/DXY/news cursors, fold,
scenario/cell), strategy setup state, consumed setup identities, lifecycle
positions, risk/circuit state, account ledger, engine in-memory state
(account, open positions, processed action ids, quote sequence), pending
intents and accumulated metrics/rejections are serialized via
`serialize_cell_state` and rebuilt by `restore_cell_state`. Journal entries
are appended **before** the matching snapshot so resume's head check is
consistent. An empty state payload fails closed (never restores zeros, never
duplicates fills). Resume requires the same plan/candidate/code/inputs/output
root and produces the same normalized result as uninterrupted execution
(rehearsal-tested).

## Structural canary and throughput (estimate, not guarantee)

Permitted read-only canaries against real datasets resolve manifests, stream
bounded batches, validate schemas/chronology/causal joins and count events —
stopping before any strategy metric. Measured structural read throughput and
`estimate_cell_runtime` projections are labelled
`ESTIMATE_NOT_GUARANTEE`; strategy-decision and management time is excluded.

## Synthetic 64-cell rehearsal

`synthetic-rehearsal` now drives all 64 cells through the **same**
`empirical_event_stream → CellEventHandler → run_cell_events` interface with
fixture-backed `EmpiricalInputBindings` (same dataset shapes, clearly labelled
`SYNTHETIC TEST FIXTURE — NOT MARKET EVIDENCE`), including full determinism
pass, interruption/checkpoint/resume equivalence, rerun suppression and
full result verification. No empirical dataset is read; no performance is
computed.

## Gates (unchanged, all false)

`empirical_strategy_evaluation_executed`, `holdout_access_authorized`,
`accepted_for_final_validation`, `phase9_authorized` remain **false**. No
strategy evaluation, optimization, profitability calculation, holdout access,
MT5/account/network/order or trading operation occurred in this correction.

## Phase 8N-J addendum — event-driven optimized path (engineering)

Phase 8N-J adds `bot/validation/replay_input_index.py` (fold-scoped causal
input index + `OptimizedCellDriver`), documented in
`PHASE8N_EMPIRICAL_REPLAY_PERFORMANCE.md`. Pipeline-semantics changes were
limited to two crash repairs found by the optimized path's equivalence
harness, both semantics-preserving:

1. `finish_fold` END_OF_DATA close now applies only to positions with open
   volume (the engine retains fully-closed positions for ledger history).
2. After quote processing mutates the durable setup store
   (fill binding/consumption), the in-memory `state_record` is refreshed
   from the authoritative durable record, so the next decision's
   `publish_decision` CAS does not reject a stale expected record.

Checkpoint payloads additionally bind `quote_cursor_state`,
`input_index_sha256` and `batch_rows` (optimized resume binds the exact
cursor; missing cursor state on an optimized checkpoint fails closed).
Slow/reference path and event semantics are unchanged; equivalence is
proven on synthetic fixtures and on real fold-1 data (see the performance
doc). No strategy, cost, scenario or gate semantics changed.
