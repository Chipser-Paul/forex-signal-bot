# Phase 8N-C — Causal Strategy Orchestration Checkpoint

Status: **BLOCKED BEFORE PLAN AMENDMENT AND EMPIRICAL RUN**. This checkpoint
documents partial, synthetic-only extraction. It is not full production/offline
decision or entry-intent parity.

## Supported production flow and audit

`main.py` calls `StrategyOrchestrator.evaluate_symbol`. Gates 1–2 read live
session/news state; gate 5 reads active-trade count; gate 6 builds W1/D1/H4
bias; gate 7 reads DXY; gates 8–11 fetch H1/M5/M15 frames, build liquidity,
displacement, FVG, order-block and internal structure, mutate `StrategyState`,
score confluence and call the Phase 6 canonical compatibility reducer. Gates
12–13 call `determine_entry`. `main._build_orchestrator_trade_levels` then
constructs absolute stop/target, followed by the Phase 3 intent, Phase 4 risk
approval and Phase 5 broker boundary. The shadow backtester is diagnostic,
not a substitute for this supported path.

The production orchestrator generates a setup ID with
`utils.setup_logger.generate_setup_id(symbol)` before acquiring the decision
candle. That ID uses process time to the second, not candle/source identity.
Gates 8–13 contain inline fetches, mutable state transitions, tier/variant
checks and early returns. `StrategyState.snapshot()` is diagnostic and omits
several transition-driving fields (including candidate, OB zone, bias, news,
session and cascade state). Therefore it cannot yet be an immutable replay or
restart state. No empirical runner may interpret its current result as a
production-equivalent decision.

## Completed partial boundaries

- Phase 2 closed-candle selection and unchanged bias/liquidity frame
  calculations were retained from Phase 8N-B.
- `StrategyState` now accepts a timezone-aware event timestamp and uses it
  for update, expiry, candidate and legacy cascade timestamps. Without an
  injected event time, the existing production UTC fallback and naive-UTC
  stored format remain. Time injection alone does **not** make the supported
  orchestrator a pure reducer.
- `bot.strategy.trade_levels.build_trade_levels` contains the existing
  absolute SMC anchor/buffer/minimum/maximum stop and liquidity-target/R:R
  calculation. `main._build_orchestrator_trade_levels` now supplies the same
  ATR, recent closed-frame values, symbol point/digits/stops level, profile
  execution levels and `ACTIVE_RISK_ENGINE.min_rr`. Synthetic long/short
  tests pin the output. Live Phase 4 monetary risk is still evaluated after
  levels; the builder does not size or send an order.
- `bot.validation.historical_news_replay` verifies the accepted official
  schedule's identity and content hash, retains actual retrospective
  retrieval timestamps, and uses the frozen inclusive USD high-impact
  ±30-minute event-time veto. It emits
  `RETROSPECTIVE_OFFICIAL_SCHEDULE`, never a forged live `NewsSnapshot`.
  Its typed replay decision separates the 2024 evaluation time from the
  actual 2026 retrieval time. Final-validation and holdout flags stay false.
  The live provider freshness gate remains unchanged.

## Remaining exact blocker

The missing production field is the **causally stable setup transition and
identity** from gates 8–13: H1 sweep, M5 displacement/OB/FVG, M15 internal
confirmation, premium/discount, displacement tier, structural variant,
confluence evidence and `determine_entry` state. A semantics-preserving,
immutable, explicitly timed reducer must be called by both live and offline
wrappers. It must derive setup IDs from source-candle identities, enforce
duplicate-event idempotency and serialize the complete restart state. The
offline adapter currently prepares causal bias only and must not emit a
`StrategyDecision` or `EntryIntent`.

After that reducer is proven, bind Phase 6 DXY, the development-only
historical-news interpretation, session and canonical decision to the same
input, call the shared level builder and Phase 3 intent constructor, and
compare complete serialized live/offline outcomes. Broker metadata from
Phase 8L remains a **development proxy**, not 2024 historical terms.

The 16-unique-scenario/64-cell factorized matrix is retained. The original
Phase 8M plan is unchanged. No superseding plan, new fingerprint, empirical
evaluation, holdout access or final-validation claim exists. There is no
authorized run command at this checkpoint.

## Verification and safety

Synthetic event-time, levels and retrospective-news focused tests pass.
The full suite at this checkpoint passed with 1048 tests, one opt-in skip and
ten subtests; no xfail or xpass was reported. No real MT5, account, broker,
news network, order, trade, strategy-profitability or empirical-performance
operation was used. Phase 8N-D permits a reviewed local **incomplete
checkpoint** of this partial work. That checkpoint authorizes no empirical
evaluation. Full parity, amendment publication and a separate final commit
remain required.

## Phase 8N-D gate 8–13 audit

The supported production XAUUSDm profile uses H1 structure (300 bars), M5
entry (150 bars), and M15 internal structure (220 bars). The deep-merged base
profile enables displacement tiers, structural variant A and freshness checks;
omission from the XAU-specific overlay does not disable those settings. The
following order and first-failure reasons are the characterization contract:

| Gate | Source / inline acquisition | State read or mutation | First rejection | Pure input / output |
| --- | --- | --- | --- | --- |
| 8 liquidity | `build_liquidity_map` fetches H1/M15/D1/W1, then H1/M5/M15 fetched inline; `detect_liquidity_sweep(H1, htf_bias)` | structure update, sweep index/time; missing sweep calls `reject_setup` | `insufficient_market_data` (wait) then `liquidity_sweep_missing` (wait) | causal frames, structure context/map, bias, frozen liquidity config → structure/sweep transition |
| 9 displacement | `detect_displacement(M5, htf_bias)`; optional tier check | FVG/displacement update or rejection | `displacement_missing` (wait), optional `displacement_tier_1_log_only` (skip) | M5 displacement, profile tier config → FVG/tier transition |
| 10 internal structure | `get_unfilled_fvgs(M5)`, `analyze_market_structure(M15)`; optional variant/freshness checks; `detect_ob_breaker(M5)` follows | `reject_setup` on failed confirmation/variant | `internal_structure_missing` (skip), optional variant/freshness reason (skip) | M15 event/early event, FVG/OB, timing identities, variant config → confirmed structure/zone transition |
| 11 confluence | ATR(M5), OB/FVG proximity, `score_setup`; `evaluate_legacy_context` canonical reducer | score candidate or `reject_setup` | `score_below_threshold` (skip), then first canonical reason (skip) | evidence, bias/DXY/news/session, causal M5 frame → canonical decision |
| 12 R:R / level gate | orchestration only records entry readiness; actual absolute levels are built later in `main.py` by shared `build_trade_levels` | none in orchestrator | downstream `level_build_failed` or minimum-R:R risk gate | causal anchors, effective symbol/profile metadata → absolute levels or rejection |
| 13 entry model | `determine_entry` reads current M5 close and mutable `StrategyState` | expiry/reset, `ready_for_entry`, candidate creation and timestamp | `entry_not_ready` (wait) | full restartable state, explicit event time, score/context/current close → entry dictionary and candidate state |

Gate 8 short-circuits before gate 9; gate 9 before tier/internal analysis;
gate 10 before variant/OB/confluence; gate 11 before entry determination.
Gates 12–13 are named together in the code, while absolute stop/target and
Phase 4 risk approval actually occur in `main.py` after candidate readiness.
Before extraction, `generate_setup_id` was called at orchestration start using
process time. Stage 2 replaces it with an explicitly timed deterministic
preflight diagnostic ID; gate 8–13 candidate IDs bind causal source evidence.

Characterization found a pre-existing dataflow defect: the merged default
profile enables structural variant A, whose strength calculation read
`atr_val` before the later market-condition assignment. Reaching that branch
raised `UnboundLocalError` even for otherwise eligible input. Phase 8N-D
moves the **same** M5 ATR(14) calculation before variant A; no ATR method,
threshold or candidate parameter changes. Earlier gate rejection reasons
remain unchanged. This repair is necessary to characterize and replay gates
11–13 at all, not a profitability adjustment.

## Historical Phase 8N-D implementation and acceptance gap

`bot.state.gate_inputs.StrategyEvaluationInputs` freezes acquired analysis,
profile, filters and exact source `open_time`/`available_at` identities as
canonical JSON. Validation rejects naive/future, unsorted or duplicate candles.
Acquisition preserves sweep, displacement/tier, internal and structural-variant
short-circuit order. Tier and variant helpers share one interpretation.

`bot.state.gate_reducer.evaluate_strategy_gates` restores a private state copy,
uses explicit UTC event time, executes the original gates and unchanged
canonical compatibility decision/entry model, then returns frozen result/state
records. Entry logging is injectable and disabled inside this reducer. No
fetcher, filesystem, network, broker mutation or clock read belongs to it.
The supported live wrapper delegates to it. Injected acquisition allows that
same wrapper to run offline without diagnostics or a MetaTrader5 import.

`phase8n.setup-id.v1` binds symbol, side, UTC decision time, causal source
identities, structure/OB/FVG/sweep hashes, configuration fingerprint and frozen
evaluation hash (including merged profile). Event IDs are verified against
evidence before a cached result may be used. Preflight diagnostics use a
separate deterministic ID. Tagged `phase8n.setup-state.v1` records contain all
legacy state fields and the last event/result; duplicate replay after record
serialization is idempotent. Backward time/malformed types reject. Legacy
active diagnostics require reconciliation and are never silently adopted.

Synthetic tests prove seven characterized paths, first-failure isolation,
immutability, identity integrity, duplicate restart and 16 long/short
live-versus-offline wrapper cases. Those cases use synthetic acquired evidence
with real Phase 6 canonical regime/order-block/decision rules; approved cases
also compare full live/offline levels and Phase 3 intent payloads. Boundary
fixtures enforce source-bar fill exclusion and reject missing/ineffective
metadata. These are mechanical parity tests, not empirical results.

**Still incomplete:** no versioned final-fill consumption event is wired from
`main.py` into serialized setup state. `mark_entry_filled` remains a legacy
mutation; the record cache represents evaluation, not complete consumed,
invalidated and expired event history. Canonical block status diagnostics do
not prove durable consumed-setup suppression. The full lifecycle, early-filter,
availability-boundary and per-cell parity matrix is incomplete. No superseding
plan may be published and Stage 2 must remain uncommitted.

Next exact implementation: add stable explicit lifecycle events and immutable
reducer integration; wire confirmed Phase 5 fills only to consumption; prove
restart/duplicate suppression and every required parity scenario; then bind
the unchanged 16-scenario/64-cell plan and publish append-only supersession.

## Phase 8N-E consumption and recovery contract

The historical gap above is addressed by a fill-authoritative replay contract,
not by treating a gate result, entry intent, trigger, check or submission as a
fill. `SetupEntryBinding` durably captures the approved decision relationship
before execution: setup, decision, existing Phase 3 intent, entry event,
action/trade identity, exact symbol/side, source candles, frozen configuration,
source-evidence fingerprint and canonical order-block ID where available.
Binding reconstruction checks the compact approved-decision payload against
the intent and source relationship. Only an eligible Phase 3 entry event can
prepare a binding; source-candle exclusion and expiry remain authoritative.
The existing adapter readiness tolerance is injected and persisted in the
binding; revalidation never substitutes a different tolerance or formula.

`classify_confirmed_entry_fill` accepts the secured Phase 5 ENTRY registry
record in CONFIRMED/PARTIALLY_FILLED state with positive finite executed volume,
valid fill price and deal/position evidence, or the existing Phase 7
ENTRY_FILL/PARTIAL_ENTRY_FILL record. Raw/manual positions, close fills, stop
changes, zero quantity, rejection and uncertain responses are not entry fills.
No new broker-success interpretation or broker mutation is introduced.

`phase8n.setup-consumption-event.v1` binds the complete pre-execution binding,
original fill identity, first positive executed volume, causal UTC event time,
and `CONFIRMED_ENTRY_FILL`. Its ID is SHA-256 of canonical semantic JSON.
Registry receipt/update time is telemetry: the live semantic timestamp is the
persisted ordered Phase 3 entry event; historical fills retain their quote
event timestamp. Receipt timing, machine identity, random IDs and paths cannot
change consumption identity. Later entry fills preserve the original event.

The shared pure reducer returns CONSUMED, DUPLICATE_IGNORED,
UNRELATED_FILL_IGNORED, UNCERTAIN_BLOCKED, IDENTITY_MISMATCH_BLOCKED or
STATE_CORRUPT. A definitive unfilled rejection can release the pending block
without consumption; it does not authorize resubmission of a rejected Phase 5
action. Missing/uncertain evidence remains blocked until reconciliation.

### Durable order and crash recovery

1. Persist the approved setup/intent/action binding before execution.
2. Classify and durably record broker confirmation in the existing Phase 5
   registry, or publish the original Phase 7 fill to its immutable fill outbox.
3. Apply the shared consumption reducer against that authoritative evidence.
4. Persist the versioned setup record under an interprocess lock using a
   same-directory temporary file, flush/fsync and atomic replace.
5. Publish acknowledgement only after persistence succeeds.

`SetupReplayStore` checks identity, schema, canonical serialization and checksum;
it maintains a backup and initialization marker. Previously initialized state
disappearance never initializes a fresh history. Corrupt primary/valid backup
recovers; both corrupt or incompatible versions fail closed. This is not a
cross-file transaction: durable fill plus missing consumption replays once;
matching consumption replays as a no-op; consumption without authoritative
fill blocks. Tests inject failures before replace and after primary replace
but before backup/ack, and concurrent confirmations still emit one event.

### Shared integration and restart suppression

The supported `main.py` orchestration path restores/reconciles the setup store,
checkpoints the decision, binds the intent before secured entry submission,
and consumes from the already persisted secured registry. Positive partial
entry fills consume even when a later fill guard must reject/close a position.
Phase 5 remains the sole production `order_send` boundary.

The Phase 7 quote-entry adapter optionally takes the same recovery coordinator
and a `HistoricalFillJournal`. It binds before execution and publishes the
actual fill before consumption; a trigger alone cannot consume. Definitive
Phase 7 engine rejection is recorded as the existing rejected-entry registry
contract. Conflicting or malformed outbox evidence requires reconciliation.
The default Phase 7 API retains its existing execution/accounting behavior.

`phase8n.setup-state.v2` retains the complete legacy gate state plus immutable
bindings, consumption events and pending/reconciliation reasons. Both live and
offline restoration use the same existing 120-minute expiry rule without
erasing consumption history or refreshing expiry merely during recovery.
Legacy gate fields such as `entry_started` are evaluation diagnostics, not a
second fill authority: the Phase 3 position and authoritative fill are the
position lifecycle truth. Legacy active snapshots are never silently adopted.

Consumed source-evidence hashes suppress a newly clocked decision from the
same causal source. Canonical consumed order-block IDs also prevent later
bars from reusing a consumed block. Materially different completed source
evidence may form a distinct setup, subject to all unchanged safety gates.
Configuration/source changes are explicit identity changes, not resets of
the consumed history.

### Synthetic proof and plan binding

Tests cover 16 normalized consumption/restart scenarios, eight complete
long/short lifecycles (full/partial entry and final target/break-even endings),
the retained 16 full wrapper cases using real canonical strategy rules, and
all 64 unchanged scenario/fold cells. Partial and final gross P&L components
reconcile through the unchanged Phase 3 ledger. No empirical performance is
computed. Source-bar exclusion, new-source eligibility, receipt-time identity,
corrupt state, backups, lost acknowledgement and concurrent replay are tested.

`phase8n.scenario-cell-contract.v1` binds the parent plan, frozen candidate,
input readiness, empirical adapter, gate reducer, levels builder, consumption,
restart, migration and parity fingerprints. Each cell binds exact cost and
metadata overlays, fold, deterministic ID/resume identity and seven completion
prerequisites. A partial/incorrect completion record cannot pass verification.
Implementation fingerprints hash reviewed UTF-8 Python text with canonical LF
newlines; Windows CRLF checkouts produce identical bindings. This normalizes
only source-text serialization, not market input hashes or numerical data.

The append-only superseding plan retains every frozen parent policy/input,
including retrospective news limitations, and remains
FROZEN_AWAITING_AUTHORIZED_RUN. The original Phase 8M evidence package is never
edited; SUPERSEDED_BEFORE_EXECUTION is recorded by its successor. Publication
is permitted only after synthetic acceptance, verified twice for idempotency.
See the amendment document for the publication identity after verification.
No empirical run, holdout, final validation or Phase 9 authorization is granted.

### Verified closeout

The final code suite passed 1,188 tests, with one pre-existing opt-in skip,
ten passing subtests and zero failures/xfails/xpasses. The focused contract
selection passed 79 tests; selected Phase 2-8/known-defect suites passed 1,131.
355 Python files compile, 39 JSON/YAML files parse, safe imports, dependency
consistency and diff validation pass. The successor was published twice:
`evidence-development_evaluation_plan-v1-ba2745f96fda3939`, fingerprint
`d69bbed4542d9517dc46d043d12324f6a921a846bca39c30e57fdc3774779c72`.
The unchanged original parent and all false authorization gates were verified.
Final commit identity and exact detached-snapshot results are reported after
commit, outside the snapshot they verify; see the final owner-facing report.
The complete 37-path reviewed inventory is in `docs/PHASE8_PROGRESS.md`.
# Phase 8N-F recovery outcome correction

The Phase 8N-E closeout below is historical. A post-commit synthetic probe
on `e3e9ac4f8bb99ece9c3364097cdfaf82af3e2fd7` disproved its aggregate
rejected-entry recovery classification: matching ENTRY/REJECTED evidence
with zero volume cleared `entry_pending_confirmation`, produced zero
consumption events, but returned CONSUMED. The pure fill reducer and durable
event history were correct; record inequality in the replay summary was not.

`phase8n.recovery-outcome.v1` preserves the existing outcome strings and the
state/event payloads, adding independent booleans: state_changed,
consumption_applied, consumption_already_present, binding_released and
reconciliation_required. Canonical JSON serialization is deterministic.
Existing history/store/event schemas remain unchanged; older constructor
arguments retain their defaults. No persisted fill or intent is redefined.

CONSUMED requires a newly applied authoritative positive entry-fill
transition. Matching already-consumed replay is DUPLICATE_IGNORED, even when
it clears a recovery block. Definitively rejected unfilled cleanup is
UNRELATED_FILL_IGNORED, even when it changes state. It releases the pending
block but retains the binding audit history; repeated cleanup remains a
non-consumption outcome. The existing offline rejection journal maps
cancelled/expired unfilled terminal reasons through the same REJECTED schema.
Zero-volume/unrelated evidence never consumes or releases an unresolved
pending binding; the aggregate remains UNCERTAIN_BLOCKED until resolved.

Mixed-binding summary priority is corruption/identity mismatch, unresolved
blocks, new consumption, unrelated non-fill, then duplicate/no-op. The flags
retain actual successful transitions independently when another binding
blocks recovery. Generic state mutation is never treated as fill evidence.

Caller audit: main startup tests explicit unsafe outcomes, not record
inequality. Main confirmation still uses the same fill classifier/reducer;
the Phase 7 adapter accepts only CONSUMED or matching DUPLICATE_IGNORED after
durable positive fill publication. SetupRecoveryCoordinator returns only
after locked store mutation. It does not increment consumption counters or
refresh setup expiry during recovery. No caller behavior change is needed.

Regressions: `tests/phase8/test_recovery_outcomes.py` covers cleanup,
serialization/restart, duplicate rejection, long/short and partial positive
fills, live/offline evidence parity, uncertainty, mismatch, manual/nonentry
evidence, corruption, mixed bindings and crash after cleanup persistence.
The retained tests cover crash after fill persistence, source reuse,
concurrency, complete lifecycles and all 64 structural cells.

Faulty plan `evidence-development_evaluation_plan-v1-ba2745f96fda3939` must
never execute. Append-only disposition and corrected successor identities
are recorded in the amendment document after full verification/publication.
All execution, holdout, final-validation and Phase 9 gates remain false.
Verified successor: `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81`;
fingerprint `adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09`.
Disposition: `evidence-development_plan_disposition-v1-dac472a23118c880`.
Focused recovery: 23 passed; complete focused contracts: 113 passed.
Full suite: 1,222 passed, one existing opt-in skip, ten passing subtests;
zero failures/xfails/xpasses. Separate Phase 2-8/known-defect selection:
1,165 passed. The retained 64 cells are structural/synthetic, not executed.
