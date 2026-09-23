# Phase 8 Progress

## Current Phase 8N-F correction: implementation/publication complete

Parent: `e3e9ac4f8bb99ece9c3364097cdfaf82af3e2fd7`; branch:
`phase/8-scientific-validation`. Retained material: only the progress blocker
warning below; no unrelated dirty paths. Original four modified and six
untracked owner paths and clean Phase 1-7 checkpoints were verified unchanged.

Completed: reproduced rejected-entry cleanup on the exact committed code:
matching ENTRY/REJECTED registry evidence with zero executed volume removes
the pending block, creates zero events, incorrectly returns CONSUMED instead
of UNRELATED_FILL_IGNORED. The new regression failed before production edits.
Corrected reducer summary now tracks consumption, matched replay and release
independently from state mutation, with a versioned serializable outcome.

Caller audit: main startup blocks only unsafe outcomes; main confirmation and
historical entry confirmation use the existing fill-authoritative reducer.
Coordinator acknowledgement follows locked store mutation; no consumption
counter is inferred from record inequality. No caller logic change required.

Current changes: setup_consumption.py; new recovery_plan_correction.py;
one evidence-store kind; new recovery-outcome/publication tests; safe-import
extension; four directly related documentation/progress files.
Reviewed path inventory (11):

- bot/strategy/setup_consumption.py: corrected typed outcomes and summary.
- bot/validation/recovery_plan_correction.py: pure correction contract and
  append-only metadata publication; no empirical worker.
- bot/acquisition/evidence_store.py: accepts one disposition evidence kind.
- tests/phase8/test_recovery_outcomes.py: 23 synthetic recovery regressions.
- tests/phase8/test_recovery_plan_correction.py: 11 publication/tamper tests.
- tests/phase8/test_gate_offline_imports.py: MT5/network-prohibited import.
- baseline/phase8n_production_mapping.json: historical/current dispositions,
  source/plan fingerprints, test proof and predecessor hashes.
- docs/PHASE8N_CAUSAL_STRATEGY_ORCHESTRATION.md: contract/caller audit.
- docs/PHASE8N_DEVELOPMENT_EVALUATION.md: invalidation and blocked execution.
- docs/PHASE8N_EVALUATION_PLAN_AMENDMENT.md: revision identities/semantics.
- docs/PHASE8_PROGRESS.md: preserves discovered blocker and new handoff.

All changes are recovery contract, metadata disposition, tests or related
documentation. Strategy, risk limits, lifecycle, costs, broker mutation
policy and stored results remain unchanged. No owner/earlier-worktree file
is staged or edited. Changed-content scan: zero actual secrets; 26 exact
public commit/code/plan/file-hash entropy alerts individually bound to the
reviewed manifest and freshly recomputed source fingerprints.
Focused recovery tests: 23 passed. Complete consumption/restart/lifecycle/
64-cell/revision/import selection: 113 passed. Synthetic append-only
publication includes timestamp-independent disposition identity and old
package immutability. No current focused failures or incomplete functions.
358 Python files compile; 39 JSON/YAML files parse; pip check passed.
Changed-content scan: zero actual secrets, one audited public commit hash.
Full suite: 1,222 passed, one pre-existing opt-in skip, ten passing subtests;
zero failures/xfails/xpasses. Separate Phase 2-8/known-defect suite: 1,165
passed. Metadata-only disposition and successor published and checked twice;
all four files of each predecessor retain their exact original hashes.
Disposition: `evidence-development_plan_disposition-v1-dac472a23118c880`.
Successor: `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81`.
Fingerprint: `adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09`.
The machine-readable mapping is also updated, retaining historical findings.
Next exact action: reviewed changed/staged scans and explicit staging;
one separate commit `fix: correct setup recovery outcome classification`;
then exact detached snapshot full/focused/phase/import/schema verification.
Commit identity and detached verification are reported outside this snapshot,
not guessed or embedded before commit. No code functions remain incomplete.
Faulty plan must never execute. An approved streaming empirical runner and
fresh exact-fingerprint authorization are still missing; no valid empirical
command exists. Do not use the legacy plan-control or shadow diagnostic as
an execution substitute. After the detached checks, the next task is a
separate owner authorization and approved streaming runner, not evaluation.
Last safe state: verified synthetic tests and
append-only metadata publication only, zero empirical cells.
All empirical/holdout/final-validation/Phase 9 authorization remains false.
Last safe state: synthetic regression only; no real datasets, broker,
account, credentials, network, bot or Streamlit accessed.

## Post-commit Phase 8N-E blocker (historical owner-direction request)

Preserved local Stage 2 checkpoint:
`e3e9ac4f8bb99ece9c3364097cdfaf82af3e2fd7`, parent
`a2b358542cfa2f68e6e1b3660e1df2b21a18ac4a`.
Do not amend/reset/discard this checkpoint or execute its successor plan.

A fresh-process, MT5/network-prohibited synthetic review found that
`reconcile_setup_consumption` returns CONSUMED when a definitive REJECTED
entry merely clears its pending block. The persisted consumption-event count
correctly remains zero. The reducer itself does not create a false fill, but
the startup/recovery summary outcome violates the positive-fill-only semantic
contract and must be corrected before final readiness.

Current failure: rejected-entry recovery outcome is CONSUMED, expected
UNRELATED_FILL_IGNORED (no new consumption event). Root cause: reconciliation
selects CONSUMED for any changed record, rather than an actual consumption
transition. Existing passing tests did not assert this aggregate outcome.

Next exact action: obtain owner authorization for one separate, narrowly
scoped follow-up commit; track actual reducer outcomes in reconciliation;
add rejected-entry startup/restart regression coverage; rerun acceptance;
publish a new append-only plan revision bound to the corrected fingerprint.
The already published successor must remain unused. All authorization gates
remain false. No code correction, amendment or extra commit is authorized yet.

This progress-only warning is intentionally uncommitted after discovery so
the verified checkpoint is not rewritten. Commit identity and detached
verification results are reported in the final owner-facing closeout.
Detached verification at the exact checkpoint: full existing suite 1,188
passed, one pre-existing opt-in skip, ten subtests passed; focused contract
selection 79 passed. Zero existing pytest failures/xfails/xpasses. The additional
guarded rejected-entry recovery assertion failed as described above, so
overall Phase 8N-E acceptance remains blocked despite those passing suites.
355 Python files compiled, 39 JSON/YAML files parsed, implementation hashes
matched the published plan, `pip check`/diff checks passed and the committed
37-file secret scan found zero actual secrets (eleven audited public hashes).
Only the temporary detached verification worktree is removed after checks;
the permanent Phase 8 worktree and this warning are retained for safe resumption.
Original owner and Phase 1-7 work remain untouched. No empirical data or
broker/account/network/trading operation occurred.

## Pre-discovery Phase 8N-E handoff (historical)

Stage 2 implementation, consumption/restart/lifecycle parity and plan
supersession are complete. Historical partial/incomplete records below are
preserved as checkpoint history, not current blockers.

- Parent: `a2b358542cfa2f68e6e1b3660e1df2b21a18ac4a`;
  branch `phase/8-scientific-validation`; all retained work preserved.
- Verified: 79 focused tests; 1,131 selected Phase 2-8/known-defect tests;
  full suite 1,188 passed, one pre-existing opt-in skip, ten subtests passed,
  zero failures/xfails/xpasses. 355 compilations and 39 JSON/YAML parses pass.
- Consumption requires the first durably confirmed positive ENTRY fill.
  Live uses the secured Phase 5 registry; offline uses the immutable Phase 7
  fill outbox. Trigger/check/submission/zero/close/manual evidence cannot consume.
- Atomic snapshots, backups, marker, strict binding/schema checks and shared
  replay handle crashes and suppress consumed source/block reuse across restart.
  Receipt time never affects semantic identity; existing readiness tolerance
  and expiry are preserved.
- Successor: `evidence-development_evaluation_plan-v1-ba2745f96fda3939`;
  fingerprint `d69bbed4542d9517dc46d043d12324f6a921a846bca39c30e57fdc3774779c72`.
  Original parent bytes unchanged; publication idempotent twice; all 64 cells
  verified. All evaluation/holdout/final-validation/Phase 9 gates remain false.
- No incomplete function remains in the approved Stage 2 contract. An approved
  streaming empirical runner is a separate future prerequisite, not a command
  this operation may execute.
- Commit protocol: one local `fix: make orchestrator setup transitions deterministic`
  commit contains this record; its SHA and post-commit detached verification
  results belong in the final report, not a self-referential/amended manifest.
  No completion/readiness claim is valid until that exact snapshot passes.
- Next exact task after verified closeout: obtain new owner authorization for
  the exact successor fingerprint and separately approve a streaming runner.
  Do not run empirical data, access holdout, deploy or start any runtime.
- Last safe state: 37 reviewed Stage 2 paths only; original owner work and
  Phase 1-7 checkpoints unchanged; no real data/account/network/trading access.
  The file inventory and contract documentation below are the resumable source.
- Final changed-content scan: zero actual secrets. Eleven entropy alerts in
  the manifest were individually bound to public checkpoint, plan/cell and
  verified implementation hashes; no filter or earlier test was weakened.

## Phase 8N-B — partial production-input extraction, amendment still blocked

- Starting branch `phase/8-scientific-validation`, HEAD
  `63d6b7e7c41a6fd9a2276fafc77503d368e0881d`; all five retained
  Phase 8N/N-A uncommitted paths were reviewed and preserved. No unrelated
  path, strategy parameter, risk limit or result change was present.
- Completed: shared frame-based W1/D1/H4/H1/M15 bias and H1/M15/D1/W1
  liquidity-map computations now serve both injected and live-fetched frames.
  A partial adapter selects causal M5/M15/H1/H4/D1/W1 snapshots and derives
  side through the unchanged production bias resolver. Fresh-process imports
  do not load MetaTrader5. A machine-readable production-field audit exists.
- Current changes: retained Phase 8N/N-A paths plus
  `bot/analysis/bias_engine.py`, `bot/analysis/liquidity_map.py`,
  `utils/indicators.py`, `bot/validation/empirical_strategy_adapter.py`,
  `tests/phase8/test_empirical_strategy_adapter.py`,
  `baseline/phase8n_production_mapping.json`, and
  `docs/PHASE8N_EMPIRICAL_STRATEGY_ADAPTER.md`.
- Tests: 121 combined Phase 2/6/adapter/matrix tests passed; 253 Phase 8A,
  Phase 8B and known-defect tests passed. Full suite: 1,028 passed, one opt-in
  skipped, ten subtests passed, zero failures/xfails/xpasses. Parent Phase 8M
  plan still verifies at its unchanged fingerprint.
- Verification: read-only identity-chain input readiness passed; compilation,
  fresh-process safe imports (MetaTrader5 absent), 39 JSON/YAML parses,
  `pip check`, diff validation and changed-file secret scan passed. Nothing
  staged, so no staged content or detached commit snapshot exists.
- Current blocker: `SetupEvidence`/setup ID remains inside stateful gates;
  Phase 6 news requires a fresh *as-of-decision* provider retrieval timestamp
  not supplied by the retrospectively collected 2024 news package;
  `determine_entry` uses wall-clock `StrategyState` expiry/update timestamps;
  and the live absolute stop/target builder is not injected for offline use.
  The partial adapter cannot emit a canonical decision or Phase 3 intent.
- Next exact task: extract the existing gate/state/level construction with
  causal snapshots and injected event time, resolve news as-of provenance
  without fabricating a historical retrieval, prove full golden decision and
  intent parity, then publish a parent-bound append-only amendment.
- Last safe state: no empirical evaluation, new plan, new fingerprint, commit
  or run. Parent package unchanged; holdout/final-validation/Phase 9 gates
  remain false. Do not treat prepared bias as a trading approval.

## Phase 8N-A — authorized amendment blocked before publication

- Starting branch `phase/8-scientific-validation`, HEAD
  `63d6b7e7c41a6fd9a2276fafc77503d368e0881d`; only the preceding Phase
  8N documentation paths were dirty and were preserved after full review.
- Parent Phase 8M package and fingerprint verified. Read-only identity-chain
  input readiness passed for the frozen 2024 development-only bindings. No
  evaluation, MT5 or bot worker was running apart from the agent's own
  completed offline status verifier.
- Owner's factorized matrix is encoded and tested: 16 unique scenarios, 64
  required cells, canonical order and exact-component deduplication.
- Files changed: `bot/validation/development_scenario_matrix.py`,
  `tests/phase8/test_development_scenario_matrix.py`,
  `docs/PHASE8N_EVALUATION_PLAN_AMENDMENT.md`, this progress file, and the
  retained `docs/PHASE8N_DEVELOPMENT_EVALUATION.md`.
- Tests: six focused matrix tests, 59 Phase 8A tests, 189 Phase 8B and
  known-defect tests passed. Full suite: 1,023 passed, one opt-in skipped,
  ten subtests passed, zero failures/xfails/xpasses. Compilation, safe imports,
  38 JSON/YAML parses, `pip check`, diff check and changed-file secret scan
  passed. No staged content or detached committed snapshot exists.
- No scenario or empirical strategy run.
- Current failure/blocker: no deterministic offline production mapping for
  bias/requested side, setup evidence, or entry/SL/TP from a causal snapshot.
  No amended evidence package, fingerprint, commit or run exists.
- Next exact task: inject causal frames into the existing bias/setup/entry
  construction without changing its rules, prove synthetic live/replay
  decision and intent parity, then publish a parent-bound append-only plan.
- Last safe state: parent plan unchanged; holdout, final validation and Phase
  9 gates false. Do not label a package frozen-awaiting-run before parity.

## Phase 8N — preflight blocked before empirical execution

- Starting HEAD: `63d6b7e7c41a6fd9a2276fafc77503d368e0881d`, clean,
  branch `phase/8-scientific-validation`.
- Owner authorized one frozen development-only run at plan fingerprint
  `ae9b4e2a17562146f0ade44f758ca015f6ab9b017eaeaf665f7745278b131c79`.
- Plan package verifies. Read-only input/status audit and process/disk checks
  completed. No active acquisition/evaluation/MT5/bot worker; 45.93 GiB free;
  no preexisting development-evaluation output directory.
- Runner audit found no empirical Phase 6→3→4→7 orchestrator. The synthetic
  Phase 8A replay and legacy shadow backtest are unsuitable for the frozen
  empirical cost-aware plan.
- Blocking protocol ambiguity: Phase 8M binds four swap, three slippage and
  ten metadata scenarios but does not define their exact composition. Phase
  8N forbids interpreting or reducing it after preregistration.
- Files modified: `docs/PHASE8N_DEVELOPMENT_EVALUATION.md`, this progress file.
  No production code, dataset, evidence package, result or Git commit changed.
- Tests run: no Phase 8N runner tests because no runner can be safely selected
  under the current immutable contract. Phase 8M plan verification passed.
  Full repository suite: 1,017 passed, 1 opt-in skipped, 10 subtests passed;
  0 failures, 0 xfails, 0 xpasses. Compilation, safe imports, 38 JSON/YAML
  parses, `pip check`, `git diff --check`, and changed-file secret scan passed.
- Current failures: none; blocker is missing frozen orchestration/composition
  specification. Incomplete functions: empirical strategy adapter, streaming
  runner, scenario/fold checkpoint and statistical execution are absent.
- Next exact task: owner reviews an append-only, hash-bound protocol amendment
  defining the matrix and candidate data-to-intent mapping, then authorizes
  implementation and run against the new exact plan identity.
- Last safe state: no empirical evaluation began; holdout/final-validation/
  Phase 9 gates remain false. Do not amend or overwrite Phase 8M.

## Phase 8J — historical broker metadata gap policy

- Starting HEAD: `3c91707886a97bbf51b331b69df20751e597c08e`; Phase 8
  worktree clean. The owner decided to assess a development-only,
  assumption-only policy while official effective-dated 2024 metadata remains
  pending, without asserting that Exness cannot provide it later.
- In progress: an append-only, hash-bound policy plus readiness overlay binds
  Phase 8I acceptance, the Phase 8H fingerprint, active swap activation,
  broker-support revisions, current metadata evidence, and the accepted 2024
  tick/candle/spread/news/DXY chains. No existing acceptance review is edited.
- Expected safe outcome unless every material field can be bounded: retain all
  gates false, including development sufficiency and strategy evaluation.
- Published the policy `evidence-broker_metadata_gap_policy-v1-c1aea67b764d323f`
  and readiness overlay `evidence-metadata_gap_readiness-v1-1c4504f33bed24ea`.
  Both re-publish idempotently and verify hash bindings; eleven material fields
  remain unbounded, so every evaluation/authorization gate remains false.
- Next exact task: run focused 8J and affected 8E–8I tests, full verification,
  then commit only the code, tests, and documentation (external evidence stays
  outside Git).

## Phase 8I — swap-policy activation and dataset-acceptance review

- Starting HEAD: `0e3f924d45c02145275f6c915a50f33740d2dd65` on
  `phase/8-scientific-validation`; worktree clean; no workers; 45 GiB free.
- Owner decision recorded: activate the preregistered assumption-only
  conservative swap stress policy for development validation only.
  Implementation: new `bot/validation/cost_policy_activation.py` (activation
  record + dataset-acceptance review, fail-closed), `activate` subcommand on
  the Phase 8H cost-policy CLI, additive store/matrix/readiness wiring.
- The frozen Phase 8H policy package stayed byte-identical; the activation
  record binds its exact fingerprint
  (`aa0ccc9368c0cf55b4775b4295f0424d4bdb0e5fd6cbfaf27137763be58e9404`),
  preserves the frozen scenario ladder (×0 diagnostic, ×1 email reference,
  ×2, ×3 required adverse boundary, Wednesday ×3, no positive credit,
  cheapest-scenario selection prohibited, no parameter tuning from scenario
  results) and carries `HISTORICAL_SWAP_UNCERTAIN` on every scenario.
- Published `evidence-cost_policy_activation-v1-802914181c0ca505` and
  `evidence-dataset_acceptance_review-v1-4d47816f5f336fe2` under
  `phase8/evidence/`; idempotent re-publication; a conflicting second
  decision fails closed.
- Acceptance review (identities re-verified on disk first): ticks, candles
  and observed spread `ACCEPTED_EMPIRICAL`; official news, commission
  (Standard NONE), swap/rollover and slippage `ACCEPTED_DEVELOPMENT_ONLY`
  (swap/slippage at `ASSUMPTION_ONLY` strength); broker metadata
  `INSUFFICIENT` (current-only, no 2024-effective dates); holdout `BLOCKED`.
  `development_evaluation_sufficient=false` — effective-dated broker
  metadata remains the single blocking gap per the committed owner kit.
- Readiness after checkpoint: all gates false
  (`accepted_for_final_validation`, `strategy_evaluation_authorized`,
  `holdout_access_authorized`); the raw 8E commission/swap/slippage
  categories stay MISSING by design — their development-strength acceptance
  is represented by the broker-support + cost-policy + activation records.
- Tests: 27 focused Phase 8I tests, 174 Phase 8A–8H focused tests, and the
  complete suite (987 passed, 1 opt-in skip, 10 subtests) pass.
  Compilation, safe MT5-free imports, pip check, `git diff --check`, and
  secret scans clean; `order_send` remains confined to the approved broker
  adapter.
- Safety: no strategy run, backtest, optimization or profitability
  computation; no holdout or 2025+ access; no MT5, bot, Streamlit, account,
  network or trading operation; all prior external artifacts re-verified
  byte-identical; nothing pushed, merged or amended.
- Next exact task: supply effective-dated 2024 broker metadata (or an owner
  decision on the metadata gap), then dataset-acceptance re-review; final
  validation additionally requires empirical fill evidence and
  final-validation-strength commission/swap support.

## Phase 8H — conservative development transaction-cost policy preregistered

- Starting HEAD: `e1ebc7ab4ddace2bee86a2fab09280115e2ba3a0` on
  `phase/8-scientific-validation`; worktree clean; no workers; ~49 GiB free.
- Preregistered `phase8h.development-cost-policy.v1` (state
  `PREREGISTERED_INACTIVE`; activation unauthorized): frozen spread
  (observed bid/ask only), commission `NONE` (evidence-bound, development
  strength, final-validation eligibility false), swap unresolved (units
  conflict preserved verbatim; conversion/averaging/selection prohibited;
  historical 2024 values unavailable), slippage assumption-only (silent
  zero prohibited).
- Frozen swap ladder: diagnostic ×0, email reference (−3.85/−0.25 USD per
  lot/day), ×2 adverse (−7.70/−0.50), ×3 adverse (−11.55/−0.75) as the
  required adverse boundary; Wednesday ×3 retained everywhere; no positive
  swap credit.  Frozen slippage ladder (points, assumption-only): 0 / 1 /
  3 (0.10 USD per point per lot), anchored to the Phase 7
  `FIXED_ADVERSE_POINTS=1` execution-model boundary.
- Acceptance restrictions frozen: all scenarios disclosed,
  cheapest-scenario pass prohibited, per-scenario expectancy/PF/drawdown/
  circuit disclosure, automatic parameter selection prohibited,
  `HISTORICAL_SWAP_UNCERTAIN` labelling required; evaluation, final
  validation and holdout gates all false.
- Binding set (SHA-256, content identity, no absolute paths): strategy
  fingerprint, execution-model fingerprint (recomputed on verify), risk
  policy fingerprint, 2024 tick year package, derived candles +
  attestation, broker-support revision, observed-spread evidence, DXY
  input.
- Published `evidence-development_cost_policy-v1-6b1a986b1f8d7b81`
  (content canonical `6b1a986b1f8d7b81ff10616fd848cb93d6dd0b19d4a96f1a512d629716b42b42`,
  policy fingerprint
  `aa0ccc9368c0cf55b4775b4295f0424d4bdb0e5fd6cbfaf27137763be58e9404`)
  beneath `phase8/evidence/`; idempotent publication; conflicting content
  under the same id fails closed; matrix/readiness regenerated through the
  existing 8E tooling with `DEVELOPMENT_COST_POLICY:
  PREREGISTERED_INACTIVE` (informational, never flips
  `all_categories_accepted`).
- Import-safety correction (behaviour-preserving): `bot/analysis/__init__`
  and `bot/execution/__init__` converted to PEP 562 lazy re-exports and
  `bot/analysis/dxy_filter.py` now imports `fetch_ohlcv` inside its three
  live-fetch helpers, so pure strategy/validation imports no longer pull
  MetaTrader5 transitively; full suite identical before/after (960 passed,
  1 opt-in skip, 10 subtests).
- Tests: 28 focused Phase 8H tests; 245 tests across 8H/8E/8F/8G/Phase 2;
  complete suite 960 passed / 1 skipped / 10 subtests.  Compilation,
  MT5-free imports, pip check, git diff --check and secret scans clean;
  `order_send` remains confined to the approved broker adapter.
- Safety: no strategy evaluation, backtest, optimization or profitability
  computation; no holdout or 2025+ access; no MT5/bot/Streamlit start;
  no account/credential/network/order/trading operation; prior external
  artifacts re-hashed byte-identical; nothing amended or pushed.
- Next exact task: owner swap-route decision, then remaining owner-kit
  inputs (effective-dated broker metadata, commission/swap final-validation
  evidence, slippage) before dataset acceptance review.

## Phase 8G addendum — official support email ingested; swap-unit conflict recorded

- Starting HEAD: `dad6efbda76ff7a96b7338f0155ea8d545f6324b` on
  `phase/8-scientific-validation`; worktree clean; no workers; ~48.9 GiB free.
- Ingested the promised official Exness support email
  (`Support/Private/Exness_XAUUSDm_Standard_Conditions_2026-09-14.eml`, 14,737 B,
  SHA-256 `45574111e8c07f6eb3cf57f4907ae5da119b8622cdd46eaf303412ee5095fcaa`,
  sent 2026-09-14T14:29:42Z) plus its hash-bound PDF rendition
  (`72f43d4d…b8acb`, 166,468 B). Raw files read-only, never committed; owner
  greeting name, email addresses and thread id deterministically redacted from
  all derived payloads (raw files untouched).
- 9 email claims classified: commission-free Standard / XAUUSDm zero commission /
  costs-in-spread / market execution / triple-Wednesday / statements-show-
  existing-trades = `BROKER_SUPPORT_ASSERTED` (corroborating the chat); swap
  long −3.85 USD and short −0.25 USD per lot/day = `CURRENT_SUPPORT_REFERENCE`
  (not historical); "cannot provide a dated record … throughout 2024" =
  `HISTORICAL_VALUE_UNAVAILABLE`. Scope note: the email does not restate
  contract size (remains transcript/screenshot-bound).
- Swap-unit conflict recorded verbatim and unresolved: screenshot −534.9
  points/lot (2026-09-13, `084e9441…`) vs email −3.85 USD/lot (2026-09-14,
  `45574111…`); units, dates, hashes, calculation modes and possible
  account/server/date differences kept; conversion/averaging/selection
  prohibited; `equivalence_established=false`.
- Swap stress policy remains INACTIVE, now additionally conflict-gated
  (`PROPOSED_INACTIVE_CONFLICT_GATED`, gate `swap.units_points_vs_usd_per_lot`);
  email-derived scenarios (−3.85 ×1/×2/×3 USD per lot/day) are `ASSUMPTION_ONLY`,
  adverse-only, Wednesday triple preserved, no strategy-performance selection.
- Published revision: `evidence-broker_support-v1-3b68b4203a9109b9` (27 claims);
  chat-only revision retained; both verify; matrix/readiness regenerated
  (`BROKER_SUPPORT` = `ACCEPTED_DEVELOPMENT_ONLY`; metadata/commission/swap/
  slippage still `MISSING`; final validation, strategy evaluation and holdout
  access all remain unauthorized).
- Tests: 55 Phase 8G focused (18 new email/conflict tests; fixtures fully
  fictional), 145 across 8E+8F+8G, full suite 926 passed / 1 opt-in skip /
  10 subtests; compileall, safe imports (no MT5), pip check, git diff --check,
  secret scans clean.
- No MT5/bot/Streamlit/account/network/order/trading operation; no strategy
  evaluation, optimization or holdout access; no tick/candle reprocessing;
  prior external artifacts unchanged.
- Next owner decision: review the swap-unit conflict (request an official
  points↔USD conversion rule or dated swap history from Exness, or authorize
  a preregistration checkpoint for the assumption-only stress policy).

## Phase 8G completion — Exness broker-conditions evidence ingested and classified

- Starting HEAD: `49c7b002aa461add9bcb8080ec4b4636d848a918` on
  `phase/8-scientific-validation`; worktree clean; no workers; ~47.6 GiB free
  (15 GiB reserve intact).
- Ingested the sanitized Exness support transcript (7,342 B,
  `f7dd8d15…04af5`, complete two-session chat) and two sanitized MT5 XAUUSDm
  Specification screenshots (`6c2d7304…0f4cb`, `084e9441…7a3e3`); owner files
  read-only, never committed; fail-closed sensitive scan passed (no
  credentials/PINs/account numbers/emails; URL help-article IDs excluded;
  agent display name redacted from derived quotes only).
- 18 claims classified individually: 14 `BROKER_SUPPORT_ASSERTED` (incl.
  Standard zero commission, cost-in-spread, contract 100 oz, pip 0.01,
  volumes 0.01/200-day/20-night, margin 1:200/0%, market execution, triple
  swap Wednesday, no ticket created), 3 `HISTORICAL_VALUE_UNAVAILABLE`
  (historical swap values, rollover time — asked and never answered, no
  archived-specification mechanism), 1 `REJECTED_CONFLICTING` (Zero/Raw
  commission figures out of Standard scope).
- Screenshot values are `CURRENT_ONLY_NOT_HISTORICAL` (digits 3, 100 XAU,
  floating spread, stops 0, XAU/USD, Forex, bid chart, Market/GTC/FOK+IOC,
  0.01/200/0.01, swap points, swap long −534.9, weekday multipliers 1/1/3/1/1).
  Swap-short and margin-display context not OCR-readable → recorded as
  truncated, never guessed. Margin display 1.0000000 vs support 1:200
  documented as unresolved conflict.
- Unit normalization verified and tested: point 0.001 ≠ pip 0.01; one pip =
  10 points; 1 pip/lot = 1 USD; 1 point/lot = 0.10 USD; contract 100 XAU.
- Commission represented as mode `NONE` (0/0/0 USD) bound to the transcript
  hash with `established: false` effective interval; non-zero stress cases
  (3.5/5.5 USD) exist only as `ASSUMPTION_ONLY` proposals.
- Published immutable package (external, atomic, idempotent):
  `evidence-broker_support-v1-5ddf97d85fccc633`; verify re-reads hashes,
  recomputes canonical content, asserts stress template `PROPOSED_INACTIVE`
  (adverse-only, no positive swap credit, Wednesday triple preserved,
  conversion `usd = points × 0.001 × 100`).
- Matrix: `BROKER_SUPPORT` = `ACCEPTED_DEVELOPMENT_ONLY`; standalone
  `BROKER_METADATA`/`COMMISSION`/`SWAP_ROLLOVER`/`SLIPPAGE_FILLS` remain
  `MISSING`; `accepted_for_final_validation=false`,
  `strategy_evaluation_authorized=false`, `holdout_access_authorized=false`.
- Tests: 36 new focused Phase 8G tests; 127 across 8E+8F+8G; full suite
  908 passed, 1 opt-in skip, 10 subtests. compileall, safe imports (no
  MT5/order/credential references), pip check, git diff --check, secret
  scan clean; `order_send` confined to the approved adapter/gateway blocklist.
- No MT5, bot, Streamlit, account, network, order or trading operation; no
  strategy evaluation, optimization or holdout access; no tick reprocessing
  or candle re-derivation; all prior external artifacts byte-identical
  (derived-candle manifest and official-news packages re-hashed).
- Next owner decision: activate the proposed swap stress policy via a
  separate preregistration checkpoint, supply dated 2024 swap evidence, or
  proceed to remaining owner-kit evidence (slippage/fill logs, commission
  beyond Standard) before dataset acceptance review.

## Phase 8F completion — manual BLS ingestion, official 2024 calendar complete

- Starting HEAD: `d428700d9151a7f57fd3f2c410df31b2d38a3eff` on
  `phase/8-scientific-validation`; worktree clean; no workers; bot state
  `STOPPED`; ~48.6 GiB free (15 GiB reserve intact).
- Ingested the owner's manual browser download of the official BLS 2024
  schedule (`BUREAU_OF_LABOR_STATISTICS.html`, 101,431 bytes, SHA-256
  `989023c3…7f878`) with honest `MANUAL_BROWSER_DOWNLOAD` provenance,
  content-addressed non-overwriting storage, byte-for-byte preservation of
  the owner file, and fail-closed authenticity gates (schedule identity,
  Eastern-Time declaration, frozen categories, denial/CAPTCHA rejection).
  The prior programmatic `RETRIEVAL_BLOCKED` record is retained in the
  package as historical evidence.
- Extended the BLS parser to the real 2024 calendar-table layout
  (date/time/desc cells, `08:30 AM`, page-wide Eastern Time declaration,
  year-scoped rows) and excluded the "Employment Situation of Veterans"
  look-alike by title pattern; DST-aware conversion verified (12 EST /
  25 EDT for BLS 2024 events).
- Final package:
  `…/phase8/evidence/evidence-official_news-v1-78279c5e26c1c6d1` — **80
  events** (FOMC 8, NFP 12, CPI 12, PPI 12, GDP 12, PCE 12, Retail 12),
  all 12 months, all four agencies ACCEPTED, unique stable IDs,
  `coverage_gaps: []`, status `ACCEPTED_DEVELOPMENT_ONLY`. Rebuild is
  idempotent; all five published revisions verify; matrix/snapshot
  succession picks coverage → accepted status → id (subset tolerated,
  partial overlap fails closed).
- News-filter snapshot now serves the complete package with
  `successful: true` (provider `OFFICIAL_US_GOVERNMENT`, 80 UTC events);
  ±30-minute inclusive blackout semantics unchanged; fail-closed behavior
  for missing/stale/corrupt packages preserved.
- Readiness: `OFFICIAL_USD_NEWS` and `HISTORICAL_USD_NEWS` =
  `ACCEPTED_DEVELOPMENT_ONLY`; broker metadata, commission, swap/rollover
  and slippage remain `MISSING` and continue to block;
  `accepted_for_final_validation = false`,
  `strategy_evaluation_authorized = false`,
  `holdout_access_authorized = false`.
- 36 focused Phase 8F tests; full suite 877 passed, 1 skipped, 10
  subtests; compileall, safe imports, `pip check`, `git diff --check`,
  secret scan clean; `order_send` still confined to the approved adapter.
- Safety: no strategy evaluation, backtest, optimization or profitability
  computation; no holdout access; no 2025+ timestamp processed; no MT5,
  bot, Streamlit, account, order or trading API; owner file untouched; no
  prior commit amended.
- Next exact task: owner supplies broker metadata, commission, swap and
  slippage evidence per `docs/PHASE8E_OWNER_INPUT_KIT.md`; dataset
  acceptance review follows once every mandatory category is accepted.

## Phase 8F — official 2024 USD news calendar (zero-cost)

- Starting HEAD: `e8c9071f36927040c7a62d52b9dc1c1c2b7842cb` on
  `phase/8-scientific-validation`; worktree clean; no workers; bot state
  `STOPPED`; ~48.7 GiB free (15 GiB reserve intact).
- Built the fail-closed, zero-cost official-government news pipeline
  (`bot/acquisition/official_news.py`,
  `backtests/official_news_control.py`) for the frozen seven-category
  high-impact USD allowlist (FOMC, Employment Situation, CPI, PPI, GDP,
  Personal Income/Core PCE, Advance Retail Sales) using only Fed, BEA,
  Census and BLS official pages — no commercial/aggregator calendar.
- Real acquisition: Fed (8/8 FOMC decisions, statement pages used as
  corroboration of calendar instants), BEA (12/12 GDP + 12/12 Personal
  Income and Outlays via per-page `EST`/`EDT` embargo lines), Census
  (12/12 Advance Monthly Retail Sales from the year-specific 2024 archive
  page) — 44 events across all 12 months. BLS is hard-blocked for
  programmatic access (Akamai 403, also via native curl): NFP/CPI/PPI
  recorded honestly as `RETRIEVAL_BLOCKED` with 0/12 each; nothing
  fabricated.
- Published package:
  `…/phase8/evidence/evidence-official_news-v1-c2d385594d26e44b`, status
  `DEVELOPMENT_INCOMPLETE — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE`;
  raw snapshots content-addressed, non-overwriting, with retrieval
  sidecars; DST-aware America/New_York conversion with gap/ambiguity
  rejection; deterministic canonical event hash; news-filter snapshot
  emitted with `successful: false` so the filter stays fail-closed.
- Evidence matrix/readiness republished honestly
  (`OFFICIAL_USD_NEWS = DEVELOPMENT_INCOMPLETE`; ticks, candles, DXY,
  observed spread available; news/broker/commission/swap/slippage still
  unresolved; `accepted_for_final_validation = false`,
  `strategy_evaluation_authorized = false`,
  `holdout_access_authorized = false`). Official-news packages coalesce
  as retrieval revisions by stable event-ID set; divergent event sets
  fail closed.
- 28 focused Phase 8F tests; full suite 869 passed, 1 skipped, 10
  subtests; compileall, JSON parsing, `pip check`, `git diff --check`,
  secret scan clean; no MT5 import in new modules; `order_send` still
  confined to the approved broker adapter.
- Safety: no strategy evaluation, optimization or profitability
  computation; no holdout access; no 2025+ timestamp processed; no MT5,
  bot, Streamlit, account, order or trading API; no prior commit amended.
- Next exact task: owner manually downloads the official BLS 2024 schedule
  page into `…/phase8/official-news/raw/` (exact checklist in
  `docs/PHASE8F_OFFICIAL_NEWS.md`); rebuild + verify promotes the package
  to `DEVELOPMENT_ONLY`; separately, broker/commission/swap/slippage
  evidence per the Phase 8E owner-input kit remains outstanding.

## Phase 8E — historical news and trading-cost evidence intake

- Starting HEAD: `ab4276533b02b0e20c6a04ea3eb447fe46e34aab` on
  `phase/8-scientific-validation`; worktree clean; no workers; bot state
  `STOPPED`; ~49 GiB free (15 GiB reserve intact).
- Built the versioned, fail-closed, fully offline intake pipeline for the
  five missing evidence categories (news, broker metadata, commission,
  swap/rollover, sanitized slippage) plus evidence-matrix and readiness
  publication: `bot/acquisition/evidence_contracts.py`,
  `bot/acquisition/evidence_store.py`,
  `backtests/evidence_intake_control.py`, owner input kit
  (`docs/PHASE8E_OWNER_INPUT_KIT.md`), fictional tracked examples
  (`docs/examples/phase8e/`, rejected as evidence by construction), and
  `docs/PHASE8E_EVIDENCE_INTAKE.md`.
- Registered observed XAUUSDm spread evidence
  (`ACCEPTED_DEVELOPMENT_ONLY`) hash-bound to the verified tick year
  package (`exness-xauusdm-2024-development-b2a0234a470dd397`, matched by
  exact `canonical_normalized_sha256`), the derived-candle manifest,
  completion marker and attestation — tick-level year aggregates plus M5
  candle-level statistics, with explicit not-a-tick-path limitations.
- Evidence matrix after this checkpoint: OBSERVED_SPREAD accepted;
  HISTORICAL_USD_NEWS, BROKER_METADATA, COMMISSION, SWAP_ROLLOVER,
  SLIPPAGE_FILLS all honestly `MISSING` (current MT5 observations are
  `CURRENT_ONLY_NOT_HISTORICAL` by contract; zero commission/swap must
  never be assumed). External packages under
  `…/phase8/evidence/` (matrix `evidence_matrix-v1-b165e496070b3b7e`,
  readiness `evidence_readiness-v1-f81287cf686db344`, spread
  `observed_spread-v1-e25bdb9bf028a5be`); publication atomic,
  non-overwriting, idempotent; conflicting intake fails closed.
- 55 focused Phase 8E tests; full suite 841 passed, 1 skipped, 10
  subtests; compileall, safe imports, JSON/schema parsing, `pip check`,
  `git diff --check`, secret scan clean; no MT5 import in evidence
  modules; `order_send` still confined to the approved broker adapter.
- Safety: no provider/broker/network/MT5 call; no account, order or
  trading API; no holdout access; no 2025+ timestamp processed; no
  strategy evaluation or profitability computation; no prior commit
  amended.
- Next exact task: owner supplies evidence per the input kit; validate
  and register each category; only then dataset acceptance and baseline
  strategy evaluation become permissible.

## Phase 8D — causal 2024 DXY development input

- Starting HEAD: `fd1ed51ee613a68028cb5ed1effcf192377e9fdc` on
  `phase/8-scientific-validation`; worktree clean; no workers; bot state
  `STOPPED`; 49 GiB free (15 GiB reserve intact).
- Consumer audit proved the committed strategy consumes only six H1 close
  series (backward alignment on `available_at`, <= 1 h staleness, 20-bar
  warm-up); ticks are not required. Formula, exponents, mappings,
  alignment and staleness policies unchanged.
- Code commit `ebb2b62e1ea25397ba918caedaedc35ee6b8119d`
  (`feat: add causal DXY input pipeline`) carries the contracts, atomic
  package publisher/verifier, bounded read-only acquisition worker,
  discovery registration and supervised CLI; 26 focused Phase 8D tests,
  223 related Phase 2/6/7/8 tests, and the full suite (786 passed,
  1 skipped, 10 subtests) pass; hygiene battery clean; MT5 imports stay
  lazy and `order_send` remains confined to the broker adapter blocklist.
- Single bounded read-only MT5 session from that exact clean commit:
  initialize/version 500.6182/last_error SUCCESS/symbol_info/
  symbol_select/copy_rates_range (72 monthly requests, 2024 only,
  six currency-verified `*USDm` mappings)/shutdown in `finally`;
  environment scrubbed before import; no account, order or trading API.
- Package `dxy-development-2024-v1-20260912T091410.712364Z` (outside Git):
  six H1 constituent partitions (6,240 rows each; USDSEK 6,216; missing
  windows never forward-filled) and a 6,216-row causal DXY partition
  (2024-01-01T23:00Z → 2024-12-31T22:00Z; 25 honest
  `STALE_CONSTITUENT:USDSEK` anchor rejections; all six source identities
  and ages recorded per row). DXY sha256
  `00c2bae585b317582fd46488698a9a3b11dd2fbc13f86efe73b827cda5f2addf`,
  canonical `b6a180756b42ba65c4fd050c6cd10ad35347e4804223fe1cca60f29da44bb531`.
  The 23:00Z bar completing at the holdout boundary was excluded.
- Independent fresh-process verification reproduced the entire DXY series
  from stored constituents (formula reproduction) and re-checked hashes,
  readback, ordering, boundaries and gap reports. Discovery registration is
  idempotent (schema `phase8d.dxy-discovery.v1`, canonical
  `dfd06a17716c1d567770d7bd8f945e826e6af82aa92cf8f0449f4f10b9f6747d`) and
  records `accepted_for_final_validation = false`,
  `strategy_evaluation_authorized = false`,
  `holdout_access_authorized = false`.
- XAUUSDm tick package, derived candles, attestation and discovery records
  re-hashed byte-identical after the checkpoint.
- Still missing: USD news with provenance/licensing, broker metadata,
  commission schedule, swap/rollover/triple-swap rules, slippage/fill
  evidence, untouched holdout.
- Next exact task: Phase 8E — acquire and verify historical high-impact USD
  news with provenance and licensing through the existing fail-closed
  acquisition contracts, without touching the holdout.

## Phase 8B November monthly-reconstruction checkpoint

- Starting HEAD: `3bef7ec7b6d38dd9ecbb76ec27b0d3522be4c96c` on
  `phase/8-scientific-validation`; the worktree was clean.
- Objective: validate the owner-supplied November 2024 `XAUUSDm` monthly
  archive against the complete annual November interval and, if that evidence
  is sound, establish a guarded one-month-at-a-time reconstruction workflow.
- Immutable November evidence: `Exness_XAUUSDm_2024_11.zip`, 40,736,279
  bytes, SHA-256
  `edd4ead5f47b45f72d933735f9f52c8dc37b685bebfa03ade6a02db3e976c1a0`.
- Annual and December evidence re-hashed unchanged at
  `e20f29457ede7b107ade6feca2f64ca33eb7e118171497300a89bccee3c94047`
  and
  `a5cef8ab1fb1bce26380113619c121da3062894b05b1c3d8de034c78bc8314fd`.
- Safe central-directory inspection found one matching CSV member of
  282,998,017 uncompressed bytes at compression ratio 6.947. The archive has
  no structural safety finding and 57,342,169,088 bytes were free before
  content processing, above the 15 GiB reserve.
- Isolation: the owner worktree remains at `55f7dd3488eec695fa1b7c1810177e5d40c6932a`
  with the same four modified and six untracked paths; Phase 1-7 worktrees are
  clean; no bot process is running; existing owner Streamlit processes are
  untouched.
- Full source and read-back: 4,437,063 rows from
  `2024-11-01T00:00:00.618Z` through `2024-11-29T18:29:58.997Z`; no malformed,
  crossed, duplicate, non-monotonic, or missing-weekday finding. Package
  `exness-xauusdm-2024-11-edd4ead5f47b45f7` has a 236,558,969-byte Parquet
  partition and canonical SHA-256
  `74cc3b55a4264a7329d8ba3bfbb65f9bc98bbabaa1fa12c77add0fe2d82349ed`.
- Complete November comparison: all 2,210,717 annual rows match exactly, with
  zero annual-only ticks or price conflicts. The monthly source contributes
  2,226,346 additional ticks on November 14 and 18-29. Classification is
  `MATERIAL_FEED_DIFFERENCES`, caused by annual omissions. The annual's two
  source-order inversions are absent from the monotonic monthly archive.
- Reconstruction decision: monthly archives are canonical; the annual archive
  remains quarantined. January-October are `MISSING`, November and December
  are `VERIFIED_PACKAGE`, and year reconstruction remains unauthorized.
- Current files modified: declared-month CLI, full-month comparator, guarded
  reconstruction workflow, focused tests, monthly evidence documentation,
  earlier-document links, and this progress record.
- Tests run: repository/worktree/process checks, archive identity and hash
  revalidation, safe ZIP inspection, full scan, deterministic conversion,
  deep read-back, idempotent repeat ingest, full-month comparison, real
  readiness matrix, and 27 focused monthly/workflow tests. Phase 8B has 142
  passes, Phase 8A has 53, and all nine known-defect tests pass. The full suite
  has 679 passes, one intentional keyring skip, 10 passing subtests, zero
  failures, zero xfails, and zero xpasses.
- Static verification: 259 Python files compile; 30 JSON, three YAML files,
  and three schemas parse; the acquisition checkpoint scanner covers 39 files
  with zero secret findings; five new-module imports and the established six
  acquisition imports remain MT5-free; `pip check` and `git diff --check`
  pass; `order_send` remains confined to the Phase 5 adapter; raw data is
  outside every worktree and absent from Git.
- Current failures: none.
- Incomplete work: local commit and detached clean-snapshot verification.
- Decision: use an explicit declared month, never infer a permissive month,
  download data, or combine annual and monthly packages. The batch command
  processes at most one owner-supplied local archive per invocation and blocks
  on duplicates, changed hashes, crash residue, or reserve failure.
- Storage: the ten-month lower/baseline/upper converted scenarios are
  2,053,681,750 / 2,413,317,115 / 4,159,428,720 bytes. With 57,475,375,104
  bytes free, the upper scenario, 354,838,453-byte temporary allowance, and
  15 GiB reserve fit.
- Next exact task: create the requested local commit from the nine explicitly
  reviewed paths and reproduce it from a detached worktree.
- Commit status: the nine reviewed files are staged; staged compilation,
  imports, diff validation, and secret scan pass. No new commit exists yet.
- Last safe state: raw archives are unchanged and outside Git; no MT5, account,
  order, network, strategy, holdout, or performance operation has occurred.

## Phase 8B December monthly-archive continuity checkpoint

- Starting HEAD: `a673761cfe58ca95dcbca0d8dd7f229c940063e6` on
  `phase/8-scientific-validation`; the worktree was clean.
- Objective: validate the owner-supplied December 2024 `XAUUSDm` archive,
  compare its exact overlap with the incomplete annual archive, and determine
  a provenance-safe reconstruction policy without strategy or performance
  evaluation.
- Immutable monthly evidence: `Exness_XAUUSDm_2024_12.zip`, 30,255,246 bytes,
  SHA-256 `a5cef8ab1fb1bce26380113619c121da3062894b05b1c3d8de034c78bc8314fd`.
- Annual evidence was re-hashed unchanged at
  `e20f29457ede7b107ade6feca2f64ca33eb7e118171497300a89bccee3c94047`.
- Safe inspection found one CSV member, 208,589,370 uncompressed bytes, with
  no traversal, absolute path, link, encryption, collision, executable, or
  expansion-limit finding. More than 15 GiB remains free.
- Source scan: 3,270,432 valid rows from
  `2024-12-01T23:05:00.178Z` through `2024-12-31T21:57:57.766Z`; exact
  `XAUUSDm`, UTC millisecond timestamps, zero malformed/crossed/duplicate/
  non-monotonic rows, and zero missing weekdays inside observed coverage.
- External package: `exness-xauusdm-2024-12-a5cef8ab1fb1bce2`, one
  175,112,929-byte Parquet partition, 3,270,432-row read-back reconciled,
  canonical SHA-256
  `062ca48aa0e740c91290c8bba9434f564c7f826616fa8e0745bd3822564b5ebc`.
- Exact overlap: all 1,931 annual rows from
  `2024-12-15T23:05:14.949Z` through `2024-12-15T23:59:58.946Z` match
  monthly timestamp/bid/ask values and order; zero source-only rows, price
  conflicts, or daily-count differences. The monthly source then contributes
  1,602,952 rows dated December 16-31.
- Truncation hypothesis: `STRONGLY_SUPPORTED_BY_DATA`, not officially
  documented. The annual member is 96,813 bytes below signed 2 GiB, its exact
  overlap matches, and the independent monthly archive continues through the
  final December trading day.
- Current files modified: period-aware archive importer, monthly control and
  overlap domain, focused tests, annual/monthly documentation, and this
  progress record.
- Tests run: source safety inspection, complete source scan, full conversion
  and read-back, idempotent repeat ingestion, exact real overlap comparison,
  32 focused archive tests, 127 Phase 8B tests, 53 Phase 8A tests, 9
  known-defect marker tests, and the complete suite. The full result is 664
  passed, one intentional skip, 10 subtests passed, zero failures, zero
  xfails, and zero xpasses.
- Static checkpoint: 256 Python files compiled, 30 JSON and three YAML files
  parsed, three schemas validated, six safe imports passed without importing
  MetaTrader5, `pip check` passed, `order_send` remains confined to the Phase
  5 adapter, and no secret finding was reported. Current failures: none.
- Decision: extend the importer with explicit annual/monthly period identity,
  deterministic monthly package identity, exact zero-tolerance overlap
  comparison, and fail-closed reconstruction planning. Any non-zero source-only
  row or price conflict is material; no permissive mismatch threshold is used.
- Reconstruction decision: use all twelve monthly archives exclusively;
  mixing annual January-November with monthly December is not authorized.
  Exactly one package per month is required and every overlap or conflict
  fails closed. The next single archive recommendation is November 2024.
- Next exact task: review and explicitly stage the seven checkpoint files,
  rerun staged scans, create the requested local commit, then reproduce it in
  a detached clean worktree.
- Commit status: no new commit exists.
- Last safe state: raw archives and all earlier worktrees are untouched; the
  bot is stopped, the existing owner Streamlit process is untouched, and no
  MT5, account, order, network, strategy, holdout, or performance action has
  occurred.

## Phase 8B benchmark observability repair

- Checkpoint: `18e788501c9e97a5305b8127e6c155f79bc52146` on
  `phase/8-scientific-validation`.
- Objective: make the bounded empirical benchmark observable, stage-specific,
  resumable, and durable before one newly authorized one-hour MT5 session.
- Verified starting state: the Phase 8 worktree is clean at the checkpoint; the
  owner worktree remains at `55f7dd3488eec695fa1b7c1810177e5d40c6932a`
  with the same four modified and six untracked owner paths; official bot state
  is `stopped` with no recorded process file; more than 15 GiB is free.
- Diagnosis: the former CLI did not create the benchmark store until after MT5
  import, initialization, and broad symbol inspection. Any failure in argument
  validation, safety checks, dependency import, initialization, or inspection
  could therefore leave no artifact. Failure statuses were printed only to
  buffered stdout and returned exit code zero. The exact prior runtime cause is
  unknown because no durable record exists.
- Test diagnosis: the fixed 30-second subprocess test combined interpreter
  startup, eager acquisition imports, Git worktree discovery, and process
  inspection. The observed child steps completed without deadlock, but their
  combined duration is sensitive to machine load.
- Completed implementation: stage-specific benchmark runs, exact hour interval,
  hash-chained journal, atomic current state, bounded redacted child logs,
  heartbeats, per-step and wall-clock watchdogs, child-only interruption,
  verified resume, cross-format read-back identity, and day/week prerequisites.
- Current files modified: benchmark CLI/domain/supervisor/journal, focused tests,
  Stage 1 and hybrid documentation, and this progress document.
- Tests run at this milestone: 81 Phase 8B tests passed; 21 focused benchmark
  and observability tests passed; 53 Phase 8A tests passed; the full suite has
  618 passes, one intentional skip, zero xfails/xpasses, and 10 subtests. The
  formerly brittle subprocess test now
  passes in 9.39 seconds after lazy-import and early-confirmation changes. No
  real MT5 module was imported during code verification.
- Current failures: none in the focused Phase 8B suite.
- Decisions: use one external run directory per stage and attempt, a durable
  hash-chained journal, bounded sanitized logs, a supervised unbuffered child,
  explicit per-operation and total deadlines, and fail-closed predecessor
  verification for day/week stages.
- Static verification: 249 Python files compiled; six safe imports, 30 JSON
  files, three YAML files, and three schemas passed; `pip check` and
  `git diff --check` passed; the changed-content scan found no secrets;
  `order_send` remains confined to the Phase 5 adapter; dry-run did not import
  MetaTrader5.
- Next exact task: create the requested local checkpoint from the reviewed
  staged paths, reproduce it in a detached worktree, and only then run the
  authorized hour stage.
- Commit status: implementation and pre-commit verification are complete; this
  document is included in the requested local checkpoint, whose resulting SHA
  is recorded in the final report.
- Last safe state: no MT5 retry, acquisition, process control, account access,
  news access, or trading operation has occurred during this repair.

## Current Exness 2024 archive checkpoint

- Starting HEAD: `e0d75243b59d84f16efa3325a87f9c1da65cd62d`
- Branch/worktree: `phase/8-scientific-validation` at
  `C:\Users\chips\forex-signal-bot-phase8`
- Objective: inspect and ingest the owner-supplied Exness 2024 tick archive
  without MT5, network, strategy, holdout, or profitability access.
- Raw evidence: exactly one immutable archive,
  `Exness_XAUUSDm_2024.zip`, 313,203,271 bytes, SHA-256
  `e20f29457ede7b107ade6feca2f64ca33eb7e118171497300a89bccee3c94047`.
- Archive location is outside every registered Git worktree. No write has been
  made beneath its `raw` directory.
- Central-directory inspection: one CSV member, 2,147,386,835 declared bytes,
  6.856 compression ratio, with no traversal, absolute path, link, encryption,
  duplicate/case-colliding name, or executable member finding.
- Observed contract: UTF-8, comma-delimited, exact header
  `Exness,Symbol,Timestamp,Bid,Ask`, exact row symbol `XAUUSDm`, and explicit
  millisecond `Z` timestamps.
- Disk before processing: 62,672,580,608 bytes free; the 15 GiB reserve is met.
- First complete scan failed closed because the archive's source label differs
  from the header only by ASCII case. The parser now accepts that narrow Exness
  identity variation while still rejecting unrelated providers.
- Second complete scan identified two adjacent timestamp inversions among
  33,669,558 rows: the source places 2024-11-01 after 2024-11-03 and
  2024-11-04 after 2024-11-05. No package was published from either rejected
  attempt.
- Decision: preserve and report source-order defects, then normalize accepted
  rows deterministically by UTC timestamp and original source sequence within
  bounded monthly partitions. Invalid rows, timezone ambiguity, symbol
  mismatches, and crossed quotes remain fatal.
- Focused tests: 20 archive/import tests pass, including deterministic
  normalization of non-monotonic source rows and source-identity handling.
- Real ingest result: `EXNESS_ARCHIVE_INGESTED`; external package
  `exness-xauusdm-2024-e20f29457ede7b10` was atomically published after full
  source validation and two complete read-back passes.
- Reconciled data: 33,669,558 rows, 12 monthly Parquet partitions totaling
  1,806,797,414 bytes, canonical SHA-256
  `93c3eea8a5317c2c009fbb9bde72b774081b76d10c121f6e15fa6c19d3429185`.
- Actual coverage is `2024-01-01T23:05:09.882Z` through
  `2024-12-15T23:59:58.946Z`, not a complete calendar year. The near-2-GiB
  member size, missing late-year dates, 25 missing weekdays, and 184
  weekday/holiday-unverified long gaps are recorded as material limitations.
- Classification: `DEVELOPMENT_ONLY`, never holdout or final-validation
  evidence. Specific server identity, licensing, complete-year coverage,
  historical costs, and broker metadata remain unresolved.
- Current failures: none in fixture tests or real package reconciliation.
- Verification complete: idempotent ingest returned the same package ID, row
  count, and canonical hash in 10.5 seconds without overwrite. Phase 8B has
  115 passes, Phase 8A has 53 passes, known-defect regressions have 9 passes,
  and the full suite has 652 passes, one intentional skip, zero
  xfails/xpasses, and 10 subtests.
- Static and security verification: 253 Python files compile; 30 JSON files,
  three YAML files, and three schemas parse; six safe imports remain MT5-free;
  `pip check` and diff checks pass; current and staged scans have zero secret
  findings; `order_send` remains confined to the Phase 5 secured adapter.
- Next exact task: create the one reviewed local archive-ingestion commit,
  reproduce it from a detached clean worktree, then remove only that temporary
  verification worktree.
- Commit status: pre-commit verification is complete. This document is part of
  the requested local commit; its resulting SHA belongs in the final report.
- Last safe state: original owner work and Phase 1-7 worktrees are unchanged;
  no MT5, account, order, browser, network, news, bot, or Streamlit action was
  initiated.

## Current Phase 8B checkpoint

- Parent: `fc5d3d554f19924e93d86313962fc3059178ebfd`
- Branch: `phase/8-scientific-validation`
- Worktree: `C:\Users\chips\forex-signal-bot-phase8`
- Objective: harden independent benchmark supervision and determine bounded
  tick-history coverage without exporting bulk data or opening the holdout.

### Completed in this checkpoint

- Preserved the failed hour attempt
  `hour-20260908t171640z-0b371d7d67` as non-benchmark evidence: its request
  returned zero rows after approximately 112 seconds, but the old path did not
  capture an immediate MT5 status and could not establish the cause.
- Moved benchmark heartbeats to the independent supervisor process and added
  separate supervisor/worker lifecycle and exit records.
- Made stdout and stderr artifacts exist before worker launch and kept child-only
  interrupt, terminate, and kill escalation explicit in the hash-chained journal.
- Corrected gateway shutdown so it runs even after an earlier worker failure and
  records `ALREADY_DISCONNECTED`, `SUCCEEDED`, or `FAILED` independently.
- Added immediate, sanitized MT5 result classification that distinguishes
  `None`, empty arrays, invalid responses, and returned rows without retaining
  raw terminal descriptions.
- Added the deterministic counts-only `probe-tick-coverage` command with fixed
  recent, target, quarterly, and monthly intervals; request/time caps; atomic
  results; and a same-session conditional hour benchmark gate.
- Added focused fake-MT5 coverage for retention bracketing, complete-hour gating,
  empty/error classification, monotonicity, caps, shutdown, and supervisor
  behavior. No real MT5 or news provider was contacted by these tests.

### Current files changed

- `backtests/empirical_data_control.py`
- `bot/acquisition/benchmark.py`
- `bot/acquisition/benchmark_supervisor.py`
- `bot/acquisition/coverage_probe.py`
- `bot/acquisition/gateway.py`
- `bot/acquisition/journal.py`
- `docs/PHASE8B_STAGE1_ACQUISITION.md`
- `docs/PHASE8B_HYBRID_ACQUISITION.md`
- `docs/PHASE8_PROGRESS.md`
- Focused files under `tests/phase8b/`

### Tests and safe state

- Latest focused supervisor, benchmark, gateway, and coverage-probe subset:
  40 passed.
- Complete Phase 8B suite: 95 passed. Phase 8A suite: 53 passed.
- Full repository suite: 632 passed, 1 skipped, 10 subtests passed, with no
  xfails or xpasses.
- All 249 tracked Python files compiled. Six changed acquisition modules imported
  without loading `MetaTrader5`; 30 JSON and 3 YAML files parsed; `pip check`
  passed.
- `git diff --check`, changed-content secret scanning, acquisition forbidden-call
  scanning, secured `order_send` confinement, and the no-MT5 command dry run
  passed.
- Current failures: none in the focused checkpoint suite.
- No implementation function is knowingly incomplete; staged,
  committed-snapshot, and authorized runtime verification remain.
- The original owner work and Phase 1-7 worktrees remain untouched. An existing
  owner Streamlit dashboard was observed and deliberately left running and
  unmodified. The official bot state remains `STOPPED`.
- No bot was started, no process was stopped, and no MT5 session, account request,
  quote request, order API, trade, or external news request has occurred in this
  continuation.

### Decisions and next exact task

- Coverage probing is counts-only and cannot export raw holdout or development
  ticks. No day, week, bulk, or holdout acquisition is reachable from it.
- A benchmark is authorized only in the same single gateway session when four
  consecutive complete 15-minute windows establish a pre-2025 hour.
- Next: stage only the reviewed checkpoint files, scan staged content, create the
  single local commit, reproduce it in a detached worktree, then perform exactly
  one bounded read-only coverage session. No retry is authorized.
- Commit status: no new commit yet.
- Last verified safe state: all local suites and static gates pass, the source
  compiles, and no external data source has been touched.

## Phase 8A repository state

- Parent: `930b3c9f3e69ba5827581c906d192e8acbc167a1`
- Branch: `phase/8-scientific-validation`
- Worktree: `C:\Users\chips\forex-signal-bot-phase8`
- Objective: verify a scientific-validation framework and empirical-data
  acceptance boundary without opening a real holdout or making performance
  claims.

## Completed

- Verified the Phase 7 parent, clean worktree, branch isolation, and unchanged
  original owner state.
- Reproduced the isolated `tests/test_session_clock.py` import cycle at the
  exact Phase 7 checkpoint.
- Removed the cycle by moving immutable session definitions to the neutral
  `bot.utils.session_windows` module; isolated collection and fresh-interpreter
  regression now pass without changing session behavior.
- Added typed empirical-package acceptance with content, provenance, coverage,
  hash, warm-up, cost, news and DXY validation.
- Registered all 16 legacy results and all 48 currently tracked cache pickles;
  preserved the Phase 1 reported count of 44 as an explicit discrepancy.
- Added frozen preregistration, chronological folds, purge/embargo, append-only
  candidate governance and an explicit holdout lock.
- Added metrics, path-dependent `$1,000` reconstruction, moving-block bootstrap,
  drawdown probabilities, stress, sensitivity, stability and acceptance policy.
- Added deterministic 13-file outputs, offline control command, schemas,
  22-scenario replay, focused tests and Phase 8A documentation.

## Current changes

- `docs/PHASE8_PROGRESS.md`: resumable Phase 8A checkpoint.
- `bot/validation/`: scientific-validation domain and adapters.
- `backtests/scientific_validation_replay.py`: synthetic framework replay.
- `backtests/validation_control.py`: local-only dataset and holdout control.
- `tests/phase8/`: focused framework and import-order regressions.
- `config/`: empirical-package and validation-plan schemas/examples.
- `baseline/phase8_contamination_register.json`: contamination map.
- Session import-boundary repair, `.gitignore`, and phase documentation.

## Tests executed

- `tests/test_session_clock.py`: collection fails at the parent because
  `session_clock -> strategy.__init__ -> dxy -> analysis.__init__ ->
  liquidity_map -> session_clock` requests `ASIAN_SESSION` from a partially
  initialized module.
- Isolated session-clock plus import regression after repair: 5 passed.
- Phase 8 focused suite: 53 passed.
- Synthetic replay: 22/22 scenarios passed; no real holdout accessed.
- Full suite: 537 passed, 1 skipped, 0 xfailed, 0 xpassed, 10 subtests.
- Phase 0: 27 passed, 1 skipped, 10 subtests; Phase 1-7:
  26/71/82/74/96/39/60 passed; known defects: 5 passed.
- Compilation and nine safe imports passed; 29 JSON and 3 YAML files parsed.
- `pip check`, `git diff --check`, offline-boundary and secured
  `order_send` confinement checks passed.
- Changed-content secret scan: 28 reviewed files, zero findings.

## Current failures

- None recorded at this milestone.

## Incomplete work

- No Phase 8A framework implementation is incomplete.
- The local commit and exact committed-snapshot reproduction necessarily occur
  after this progress file is frozen; their evidence belongs in the final
  report.

## Decisions

- Phase 6 strategy and Phase 7 execution semantics remain frozen.
- Raw empirical data will remain outside Git.
- Synthetic fixtures will be labeled `SYNTHETIC TEST FIXTURE - NOT MARKET
  EVIDENCE` and cannot unlock a real holdout.

## Next exact task

- Create the local `test: add scientific validation framework` checkpoint and
  verify it from a detached clean worktree.

## Commit status

- Implementation is complete and explicitly staged for the single requested
  local checkpoint. The resulting SHA is recorded in the final report.

## Last verified safe state

- Phase 8A has 53 focused tests and 537 full-suite tests passing; staged diff
  and secret checks are clean. No bot, MT5, account, network provider, order
  API, empirical holdout, or owner process has been touched.

## Phase 8B Offline Verifier Checkpoint

- Objective: add a separate durable, read-only Parquet verifier without
  changing the MT5 benchmark supervisor or accessing real Phase 8 artifacts.
- Current files: `bot/acquisition/offline_verifier.py`,
  `backtests/offline_dataset_control.py`, focused synthetic tests, and
  `docs/PHASE8B_OFFLINE_VERIFIER.md`.
- Decisions: use distinct worker and supervisor hash-chained journals;
  `VERIFIED` reuse requires the same request and valid terminal marker;
  interrupted scans are not cryptographically resumable.
- Tests: 17 focused synthetic verifier tests, 158 Phase 8B tests, 53 Phase 8A
  tests, 9 known-defect tests, and the full 695-pass/1-skip suite pass. No test
  points at the external Phase 8 data root.
- Commit: this checkpoint is the requested local
  `feat: add durable offline dataset verifier` commit; its SHA is intentionally
  reported by the completing agent rather than embedded into this file.
- Next exact task: separately authorize a December `recovery-v2` run using the
  documented CLI and a new non-overwriting run directory.

## Phase 8B Heartbeat Follow-Up

- Root cause: the original polling loop could observe an immediate child exit
  before its first scheduled heartbeat.
- Correction: record and fsync `HEARTBEAT(initial=true)` immediately after the
  durable `CHILD_STARTED` event. A failed launch records
  `CHILD_LAUNCH_FAILED` and has no child heartbeat.
- Tests: immediate crashes repeat three times; event ordering, periodic
  heartbeats, launch failure, missing-result handling, and one final outcome
  are covered with synthetic children only.
- Commit: this checkpoint is the local
  `fix: make verifier heartbeat deterministic` follow-up commit; its SHA is
  reported by the completing agent rather than embedded into this file.
- Next exact task: separately authorize a December `recovery-v2` run using the
  documented CLI and a new non-overwriting run directory.

## Phase 8B Package-Registry Checkpoint

- Objective: replace ambiguous recovery-package directory selection with a
  versioned, hash-journaled, externally persisted selection authority.
- Current files: `bot/acquisition/package_registry.py`, the narrow
  `backtests/package_registry_control.py` offline CLI, reconstruction readiness
  integration, synthetic registry tests, and `PHASE8B_PACKAGE_REGISTRY.md`.
- Decisions: recovery IDs use locked monotonic generations and immutable
  operation IDs; zero active packages blocks managed recovery; bootstrap is an
  explicitly supplied, reviewed plan and never directory discovery.
- Current scope: code and temporary synthetic directories only. No real Phase 8
  data directory, package, verifier run, recovery, or year reconstruction has
  been accessed.
- Tests: 20 focused registry/readiness tests, 173 Phase 8B tests across safe
  bounded runs, 53 Phase 8A tests, 5 known-defect tests, and the full suite
  (710 passed, 1 skipped, 10 subtests) pass using temporary synthetic paths.
- Next exact task: stage only the reviewed registry contract files, create the
  requested local immutable-registry checkpoint, and reproduce it from a clean
  detached worktree.

## Phase 8B Legacy Bootstrap Compatibility

- Objective: preserve the literal existing December `recovery-v1` name as
  historical evidence without weakening canonical recovery allocation.
- Rule: it is accepted only by explicit legacy bootstrap for the exact December
  dataset/raw identity, only as `QUARANTINED`, and only at generation one.
  Normal registration and activation reject it; the next allocation remains
  zero-padded `recovery-0002`.
- Next exact task: verify the compatibility checkpoint from a clean snapshot,
  then generate the separately authorized, read-only December bootstrap plan.

## Phase 8C Derived-Candle Provenance Attestation

- Parent checkpoint: `2817d5b82a452157a3662b57e1956fd878a733cf` on
  `phase/8-scientific-validation`.
- Objective: close the Phase 8C provenance gap truthfully without
  regenerating the 39,715,935 source ticks or rederiving any candle dataset.
- Completed: read-only committed-snapshot verification of the existing
  derived package (manifest/completion binding, all six partition physical
  and canonical hashes, complete readback, boundaries, causality, W1 Monday
  alignment, row counts 70,562/23,550/5,904/1,600/311/52) and publication of
  an immutable post-commit attestation plus an external discovery record.
- Provenance honesty: the manifest truthfully stores the generation-time
  HEAD `4f46eef…` (`generation_base_commit`); no generation-time code
  fingerprint exists, so `generation_commit_equivalence` is recorded as
  `NOT_PROVEN`, never claimed as generated-from-`2817d5b…`. The verifier at
  `2817d5b…` accepts the package unchanged (`verified_compatible=true`).
- Current files: `bot/acquisition/candle_attestation.py`,
  `bot/acquisition/candle_discovery.py`,
  `backtests/candle_provenance_control.py`,
  `tests/phase8c/test_candle_provenance.py`, and
  `docs/PHASE8C_PROVENANCE_ATTESTATION.md`. Attestation and discovery
  records live outside Git and are never committed.
- Tests: 21 focused attestation/discovery tests, 39 Phase 8C tests, 184
  Phase 2/7/8 tests, and the full suite (760 passed, 1 skipped, 10
  subtests) pass. Compilation, safe MT5-free imports, JSON/YAML/schema
  parsing, pip check, git diff --check, and secret scanning are clean;
  `order_send` remains confined to the approved broker adapter gateway.
- Safety: no MT5, bot, Streamlit, account, network, order or trading
  action; no strategy evaluation, optimization or holdout access; the
  original package and all reconstruction/quarantine/forensic evidence are
  byte-identical before and after this checkpoint.
- Next exact task: begin Phase 8D input completion (DXY history, USD news
  history, broker metadata, slippage/fill evidence) without touching the
  holdout.

## Phase 8B 2024 Reconstruction Completion

- Parent checkpoint: `ff82bae3b20c778f3fa753a08ed88ad7be61cbba` on
  `phase/8-scientific-validation`.
- Completed: forensic classification and quarantine of the retained August
  partial artifact; clean August retry; September and October reconstruction;
  registry-governed 2024 monthly selection; and a reference-only 2024
  development-year manifest with a full canonical-stream verification.
- Current files: archive identity validation, reconstruction/quarantine and
  year-package support, registry compatibility, focused tests, and Phase 8B
  reconstruction documentation. External datasets remain outside Git.
- Safety: no MT5, broker, account, strategy, news, or profitability operation
  was invoked. Reconstruction used only the authorized external archive inputs.
- Next exact task: run final repository verification, stage the reviewed files,
  commit the reconstruction contract, and reproduce it from a detached clean
  worktree without altering external artifacts.

## Phase 8K Historical Broker Metadata Recovery

- Parent checkpoint: `bdc9a2858785f20971ef280c07cb7f8a1e2843c1`.
- Objective: examine local historical artifacts for independently supportable
  2024 XAUUSDm broker metadata, without changing Phase 8J or running a
  strategy evaluation.
- Completed: an append-only, hash-bound recovery/readiness protocol with
  synthetic idempotency, tamper, conflict, and MT5/network-free import tests.
  The local audit found only quote-only 2024 archives and current-only support
  evidence; no historical order, fill, account, terminal, or specification
  record was found. Quote serialization is retained as an empirical parsing
  observation only; it does not establish order normalization or economics.
- Current files: `bot/validation/metadata_recovery.py`,
  `backtests/metadata_recovery_control.py`, Phase 8K tests, and
  `docs/PHASE8K_METADATA_RECOVERY.md`.
- Published overlays: `evidence-broker_metadata_recovery-v1-712deee4c757709f`
  and `evidence-metadata_recovery_readiness-v1-f3301b9715937ad0`; repeated
  publication returned those same identities.
- Next exact task: obtain effective-dated 2024 broker metadata or independently
  verifiable historical execution records, then create a new immutable review.
  Strategy evaluation remains separately unauthorized.

## Phase 8L Owner-Authorized Conservative Metadata Bounds

- Parent checkpoint: `55c8d6fa301195172f368328e308398f22553d62`.
- Objective: bind the new official negative evidence to a preregistered,
  development-only metadata proxy without claiming it represents 2024 terms.
- Current files: `bot/validation/development_metadata_bounds.py`,
  `backtests/development_metadata_bounds_control.py`, Phase 8L tests, and
  `docs/PHASE8L_DEVELOPMENT_METADATA_BOUNDS.md`.
- Published overlays: `evidence-broker_metadata_unavailability-v1-f1be088c17a391c4`,
  `evidence-development_metadata_bounds-v1-8dad509e60c8014a`, and
  `evidence-development_metadata_bounds_readiness-v1-6fa811a3200c6042`.
  Re-publication returned the same identities.
- Next exact task: seek a separate explicit owner authorization before any
  development-only, all-scenario evaluation preparation. This checkpoint does
  not authorize strategy execution, final validation, holdout access, or Phase 9.

## Phase 8M Development Evaluation Plan Frozen

- Parent checkpoint: `9018042d489a17410da13e05a029404cf9fea9fb`.
- Objective: read-only readiness audit of every mandatory development input,
  then freeze the immutable `phase8m.development-evaluation-plan.v1` contract
  binding all dataset/evidence/policy/code fingerprints.
- Current files: `bot/validation/development_evaluation_plan.py`,
  `backtests/development_evaluation_plan_control.py`, Phase 8M tests, and
  `docs/PHASE8M_DEVELOPMENT_EVALUATION_PLAN.md`; additive matrix wiring in
  `backtests/evidence_intake_control.py` and `bot/acquisition/evidence_store.py`.
- Readiness audit: ticks 39,715,935 rows (identity-chain verified),
  M5/M15/H1/H4/D1/W1 candles, 80-event official news, six-constituent DXY
  (6,216 rows), observed spread, 8H cost policy, 8L metadata bounds,
  fingerprints, contamination register, and 8A preregistration all verified.
- Published plan: `evidence-development_evaluation_plan-v1-82ef6fcab5c13547`,
  fingerprint `ae9b4e2a17562146f0ade44f758ca015f6ab9b017eaeaf665f7745278b131c79`;
  idempotent re-publication returned identical identities. Matrix/readiness
  list it as `FROZEN_AWAITING_AUTHORIZED_RUN` (informational only).
- Gates unchanged and false: evaluation, final validation, holdout, Phase 9.
- Next exact task: separate owner-authorized checkpoint to execute the frozen
  plan deterministically (all scenarios x all folds, no tuning).

## Phase 8N-C Causal Orchestration Checkpoint

- Branch/parent: `phase/8-scientific-validation` at
  `63d6b7e7c41a6fd9a2276fafc77503d368e0881d`; legitimate uncommitted
  Phase 8N/N-A/N-B work was preserved.
- Completed: 16 unique/64-cell factorized matrix and partial causal bias/
  liquidity adapter retained; injected event time through `StrategyState`;
  extracted live-delegated pure absolute stop/target builder; added verified
  development-only official historical-news veto with distinct actual
  retrospective retrieval and evaluation times. Synthetic focused tests pass.
- Current changed files: bias/liquidity/indicator extraction, strategy news
  event-time helper, state event clock, live level wrapper and pure builder,
  partial empirical and news adapters, matrix/mapping documents and tests.
- Tests: 31 focused passed; full suite 1048 passed, one opt-in skipped, ten
  subtests, zero xfail/xpass. Compilation of 334 Python sources, four
  MT5-free fresh-process imports, 39 JSON/YAML parses, `pip check`, diff
  validation, and changed-path scan (21 paths, zero findings) passed. No
  staged paths exist. The legacy cascade test characterized the pre-existing
  third-loss block; no Phase 4 policy was changed.
- Incomplete: supported orchestrator gates 8–13 remain inline/stateful;
  `generate_setup_id` still uses process time; complete immutable restart
  state, stable setup identity, DXY/session/canonical/final-gate wiring and
  full decision/intent parity are absent. No plan amendment or commit exists.
- Decision: no empirical run, no holdout/final validation and no superseding
  Phase 8M plan until complete parity is proven. Historical news stays
  `RETROSPECTIVE_OFFICIAL_SCHEDULE`, never forged live freshness.
- Last verified safe state: focused 31 passed, full suite 1048 passed;
  no MT5/account/network/
  order/trade or empirical-performance operation occurred.
- Next exact task: extract gates 8–13 and `determine_entry` into one immutable,
  explicitly timed, idempotent setup reducer with stable source-candle IDs;
  wire both live and offline, then prove complete serialized decision and
  intent parity before any amendment or local commit.

## Phase 8N-D Retained-Work Checkpoint

- Starting HEAD `63d6b7e7c41a6fd9a2276fafc77503d368e0881d` on
  `phase/8-scientific-validation`; 21 retained Phase 8N/N-A/N-B/N-C paths
  reviewed. Original owner paths and earlier phase worktrees are untouched.
- The local `refactor: prepare causal strategy replay` checkpoint captures
  **partial infrastructure only**: factorized 16-scenario/64-cell matrix,
  causal bias/liquidity preparation, event-time state, shared live levels,
  retrospective development-only news, mapping audit, tests and blocked-run
  documentation. The supported setup reducer and full parity do not yet
  exist. No empirical run, holdout, final validation or plan supersession is
  authorized by the checkpoint.
- Current verification target: retained focused tests, complete suite,
  compilation, MT5-free imports, structured parsing, dependency check,
  diff validation and changed/staged secret scans, then detached verification
  of the exact checkpoint commit.
- Next exact task after checkpoint: characterize gates 8–13 against the
  supported live wrapper, separate acquisition from strategy, implement a
  pure explicitly timed/idempotent setup transition with stable source-based
  IDs, and wire the same transition into the empirical adapter.

- Stage 1 verified commit: `a2b358542cfa2f68e6e1b3660e1df2b21a18ac4a`
  (`refactor: prepare causal strategy replay`), 21 reviewed files. Detached
  clean snapshot: 1048 passed, one opt-in skipped, ten subtests; 334 Python
  files compiled, four MT5-free imports, 39 JSON/YAML parses, `pip check`,
  diff validation and committed-path secret scan (zero findings) passed.
  The temporary verification worktree was removed. This commit is local only
  and incomplete; no evaluation is authorized.

## Phase 8N-D Stage 2 Retained Implementation

- Branch: `phase/8-scientific-validation`; verified checkpoint parent
  `a2b358542cfa2f68e6e1b3660e1df2b21a18ac4a`. Stage 2 has no commit.
- Implemented: frozen causal gate-input aggregate, gate 8–13 reducer,
  complete tagged legacy-state record, stable setup/event ID schemas,
  explicit-time live delegation, staged analyzer short-circuit, shared DXY
  correlation interpretation, offline setup/level/Phase 3 intent mapping.
- Necessary integration correction: calculate unchanged M5 ATR(14) before
  enabled structural variant A reads it. No threshold/formula changed.
- Focused integration selection: 93 passed, including 16 symmetric supported
  wrapper comparisons with real canonical decisions and approved-case full
  level/intent equality. Earlier intermediate full suite: 1068 passed, one
  opt-in skipped, ten subtests. Final current-tree suite: **1110 passed, one
  opt-in skipped, ten subtests passed, zero failed/xfail/xpass**. Separate
  Phase 2–7 plus known-defect selection: 427 passed.
- Current files: `bot/state/{orchestrator,gate_inputs,gate_reducer}.py`,
  `bot/strategy/{setup_state,setup_intent}.py`, DXY filter extraction,
  empirical adapter, intent serialization, entry logging injection,
  Phase 8 tests and the earlier risk test's retired logger-ID expectation,
  orchestration/progress documentation. All edits remain in Phase 8.
- Incomplete: versioned confirmed-fill consumption event and full setup event
  history are not integrated into the live final boundary; durable consumed
  suppression and complete lifecycle/early-filter/per-cell parity remain
  unproven. No superseding plan exists. Current targeted tests have no failure;
  failing fixture attempts were corrected without weakening validators.
- Next exact task: implement explicit lifecycle event/restart integration and
  complete required parity; then bind and publish append-only supersession
  before reviewing/staging Stage 2 paths. Never rerun an empirical evaluation
  from this partial state.
- Last safe state: Stage 1 detached snapshot verified; synthetic-only Stage 2
  checks. No external empirical data, holdout, provider, account or MT5 call.
  Empirical evaluation, final validation, holdout and Phase 9 remain blocked.

### Current-tree verification and resumable safe state

- 345 tracked/new Python files compiled; 39 JSON/YAML files parsed.
- Fresh-process gate/orchestrator/empirical imports passed with a finder that
  prohibits MetaTrader5 and guards against network connections.
- `pip check`: no broken requirements. `git diff --check`: passed; Git's
  existing Windows line-ending notices are not whitespace defects.
- Changed/new scan: 23 paths, zero unexpected secret findings. Default scanner
  reported one Hex High Entropy String at mapping-manifest line 9: the public
  checkpoint Git SHA-1. Its type, path, line and hashed value were independently
  matched against expected HEAD and manifest metadata; no secret value printed.
  No broad filter/baseline exception was added. Staged content is empty.
- Broker-mutation search found only the secured Phase 5 adapter's
  `self.broker.order_send(final_payload)`. No production execution was invoked.
- Original main HEAD remains `55f7dd3488eec695fa1b7c1810177e5d40c6932a`
  with the same four modified and six untracked owner paths. Phases 1–7 are
  clean at recorded checkpoints. No process was started/stopped/restarted.
- No Stage 2 commit exists, so no Stage 2 exact committed-snapshot verification
  can be claimed. Stage 1 detached verification remains valid. No temporary
  verification worktree remains registered.
- Current objective is **incomplete, not approved for execution**. Last safe
  state is the passing current-tree suite above plus the verified Stage 1
  checkpoint. Preserve all partial files; do not reset/recreate this worktree.
- Next exact task remains confirmed-fill setup lifecycle/restart integration
  and complete required parity. Only after that may a superseding plan and the
  second local commit be created; a new empirical run still requires separate
  authorization.

### Stage 2 path inventory

| Path | Retained purpose |
| --- | --- |
| `bot/state/gate_inputs.py` | Frozen causal inputs, staged acquisition, shared tier/variant interpretation, verified event identity |
| `bot/state/gate_reducer.py` | Pure ordered gates, private state transition and deterministic result |
| `bot/state/orchestrator.py` | Supported live delegation, injected acquisition/event clock and offline diagnostic suppression |
| `bot/strategy/setup_state.py` | Versioned complete state serialization, setup IDs and conservative legacy inspection |
| `bot/strategy/setup_intent.py` | Explicit metadata and shared level/intent boundary mapping |
| `bot/analysis/dxy_filter.py` | Extract unchanged correlation interpretation; one injected decision time |
| `bot/validation/empirical_strategy_adapter.py` | Read-only causal acquisition and same supported wrapper/reducer/level/intent calls |
| `bot/execution/lifecycle/serialization.py` | JSON-compatible existing intent representation |
| `strategies/smc_engine/entry_model.py` | Injectable logging; formulas and thresholds unchanged |
| `tests/phase1/test_risk_state_runtime_baseline.py` | Preserve risk assertions; replace retired logger-ID/time mocks only |
| `tests/phase8/test_orchestrator_characterization.py` | Seven characterized gate/first-failure paths |
| `tests/phase8/test_gate_reducer.py` | Gate sequence, immutable inputs and duplicate/configuration checks |
| `tests/phase8/test_gate_input_contract.py` | Causality, identity integrity, restart and I/O/short-circuit guards |
| `tests/phase8/test_setup_state_record.py` | Complete roundtrip, stable IDs and fail-closed legacy/malformed records |
| `tests/phase8/test_setup_intent_parity.py` | Level/intent mapping, metadata and source-candle barrier |
| `tests/phase8/test_full_orchestration_parity.py` | 16 symmetric synthetic wrapper cases with real canonical gates and full approved-case intents |
| `tests/phase8/test_gate_offline_imports.py` | Fresh-process MT5/network-free imports |
| `baseline/phase8n_production_mapping.json` | Additive retained Stage 2 mapping and explicit acceptance blockers |
| `docs/PHASE8N_CAUSAL_STRATEGY_ORCHESTRATION.md` | Gate audit, contract and unresolved consumption/restart gap |
| `docs/PHASE8N_EMPIRICAL_STRATEGY_ADAPTER.md` | Preserve checkpoint history; describe current synthetic-only wiring |
| `docs/PHASE8N_EVALUATION_PLAN_AMENDMENT.md` | Explicitly prohibit premature supersession/publication |
| `docs/PHASE8N_DEVELOPMENT_EVALUATION.md` | Preserve blocked-run history and no-execution status |
| `docs/PHASE8_PROGRESS.md` | Exact verification, files, acceptance gap and resumable next task |
# Phase 8N-E retained-work continuation

Parent: `a2b358542cfa2f68e6e1b3660e1df2b21a18ac4a` on
`phase/8-scientific-validation`. The 23 retained Stage 2 paths match the
documented inventory; original owner status remains four modified/six untracked.
No retained edits were discarded. No Stage 2 commit exists.

Current objective: bind setup decisions and entry intents to authoritative
confirmed entry fills, persist consumption, and prove crash/restart suppression.
Next task: implement and test the pure consumption reducer and atomic replay
store, then integrate supported live/historical callers. Plan publication and
empirical execution remain blocked until every acceptance requirement passes.
No empirical data, broker/account/network service or runtime process accessed.

## Phase 8N-E implementation milestone

- Retained 23 paths preserved; checkpoint HEAD still `a2b358542cfa2f68e6e1b3660e1df2b21a18ac4a`.
- Implemented pure typed entry binding/consumption, strict approval relationship,
  atomic locked setup store, shared recovery coordinator and durable Phase 7
  fill outbox. Supported live and historical entry callers use the same
  classifier/reducer/reconciliation ordering; no trigger-only consumption.
- Added 16 consumption scenario pairs, eight complete symmetric lifecycle
  pairs, crash/backup/concurrency/restart tests, exact 64-cell contract and
  append-only superseding-plan publisher. Source reuse is blocked; new causal
  sources may form distinct setups. No thresholds, risk or cost overlays tuned.
- Latest focused selection: 76 passed. Full suite and final checks are running.
- Current failures: none in the latest focused selection. Earlier synthetic
  short fixture was corrected to its existing equal-highs liquidity semantics;
  no production entry rule changed or test assertion weakened.
- Next exact action: finish acceptance verification, publish successor twice
  only if all tests pass, update publication identity, explicitly stage reviewed
  Stage 2 paths, commit locally, verify the exact detached committed snapshot.
- Commit status: Stage 2 uncommitted. Empirical execution remains prohibited.
- Last safe state: original owner four modified/six untracked paths unchanged;
  Phase 1-7 clean at recorded checkpoints. No runtime operation occurred.

### Additional Phase 8N-E reviewed paths

Together with the retained 23-path table above, these 14 paths are the entire
37-path Stage 2 diff. No dataset, environment, credential, runtime state,
historical result or earlier phase-worktree file belongs to the commit.

| File | Responsibility |
| --- | --- |
| `bot/strategy/setup_consumption.py` | Pure typed approved binding, authoritative entry classifier, semantic event, reducer and replay |
| `bot/strategy/setup_store.py` | Atomic locked versioned setup snapshots, checksum, backup and disappearance guard |
| `bot/strategy/setup_recovery.py` | Shared durable prepare/consume/reconcile coordinator and decision compare-and-swap |
| `bot/backtesting/fill_journal.py` | Immutable original Phase 7 fill outbox and definitive unfilled rejection evidence |
| `bot/backtesting/adapters.py` | Optional bind/fill-publish/consume integration preserving existing Phase 7 execution |
| `main.py` | Supported live startup reconciliation, pre-send binding and secured-registry consumption |
| `bot/strategy/legacy_adapter.py` | Pass consumed canonical block IDs; expose block identity for binding |
| `bot/validation/development_scenario_matrix.py` | Exact frozen 64-cell component/completion/resume identities |
| `bot/validation/development_plan_revision.py` | Pure successor construction/verification and append-only evidence publication |
| `tests/phase8/test_setup_consumption.py` | Positive-fill boundary, relationship integrity, expiry, source reuse, crashes/backups/concurrency |
| `tests/phase8/test_consumption_scenario_parity.py` | 16 normalized Phase 5 versus Phase 7 consumption/restart scenario pairs |
| `tests/phase8/test_setup_lifecycle_restart_parity.py` | Eight real canonical-gate/Phase 3/Phase 7 lifecycle pairs and outbox integrity |
| `tests/phase8/test_scenario_cell_contract.py` | All 64 exact cells and invalid/missing/partial completion rejection |
| `tests/phase8/test_development_plan_revision.py` | Frozen-policy preservation, idempotent append-only publication and LF/CRLF equivalence |

### Phase 8N-E final code acceptance

- Final code suite: 1,188 passed, one pre-existing opt-in Windows keyring skip,
  ten subtests passed; zero failures, xfails or xpasses. Focused consumption,
  restart/lifecycle/cell/revision/import selection: 79 passed. Six selected
  safe-import/persistence tests passed, including isolated fresh-process
  imports that reject MetaTrader5 and network access.
- 355 reviewed Python files compile; 39 JSON/YAML files parse. Versioned state,
  consumption, cell and plan schemas are exercised by focused tests.
- `pip check` and `git diff --check` passed. Changed 37-file secret scan found
  zero actual secrets; one entropy alert was audited as the public parent
  checkpoint SHA at manifest line 9, not a credential.
- Production `order_send` remains solely in the Phase 5 secured adapter.
  No broker policy, strategy profile, risk limit, cost assumption or stored
  result changed. MT5 benchmark/offline-verifier journaling is unchanged.
- Separately selected Phase 2-8 and known-defect suites are running. Next:
  append-only successor publication after that pass, then explicit staging,
  staged scan, one local Stage 2 commit and detached snapshot verification.
- Main retains its four modified and six untracked paths; earlier phase
  worktrees are clean. Cached `main...origin/main` relationship is 24 ahead / 4
  behind, recorded only; no fetch or divergence resolution occurred.

### Phase 8N-G streaming development-evaluation runner

- Built `bot/validation/development_evaluation_runner.py` and the read-only
  control CLI `backtests/development_evaluation_control.py` (inspect,
  verify-inputs, estimate, status, verify-results, synthetic-rehearsal,
  dry-run-structure; run/resume require the explicit confirmation flag plus
  exact corrected-plan package id, fingerprint and candidate identity).
- Bound the corrected plan `evidence-development_evaluation_plan-v1-
  4a6ab94c3e303c81` (fingerprint `adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09`)
  and hard-rejected the invalidated plan `...ba2745f96fda3939` as runnable.
- Input firewall re-verifies all frozen inputs via the Phase 8M readiness
  verifier and binds them into the plan; documented rejections include
  changed hash, missing completion marker, wrong candidate, invalidated plan,
  legacy result input, unregistered scenario, out-of-plan interval, holdout
  timestamp/path and live-broker substitution.
- Bounded-memory JSONL streaming with chronology and duplicate detection
  spanning batch boundaries, corruption/naive/holdout timestamp rejection and
  sequence continuity; append-only fsync'd hash-chained journal with entry
  hash recomputation; atomic checkpoints and identity-checked resume; one
  terminal state per cell with silent-rerun/overwrite refusal; atomic
  non-overwriting 17-file result contract verified by `verify_results`.
- Synthetic 64-cell rehearsal (16 scenarios × 4 folds) passed with
  determinism, interruption/resume equivalence, duplicate suppression and
  full readback; results labelled `SYNTHETIC TEST FIXTURE — NOT MARKET
  EVIDENCE`; no empirical result was produced.
- Tests: 39 focused 8N-G; 738 across Phase 8A–8M; full suite 1,261 passed /
  1 opt-in keyring skip / 10 subtests. Compile, safe-import (no MT5, no
  network modules), `pip check`, `git diff --check` and secret scan clean.
- The exact empirical-run command was produced but NOT executed; strategy
  evaluation, optimization, profitability computation, holdout access and
  MT5/account/network/order operations remain unauthorized.

### Phase 8N-I plan-bound empirical input pipeline

- **Defect corrected:** the 8N-G `run`/`resume` commands required
  `--synthetic-stream`, so the runner could not consume the plan-bound
  empirical 2024 datasets and the 8N-G production-readiness claim was
  invalid. No empirical cell had run; no output root or result existed.
- **Fingerprint audit:** the plan's `CODE_COMPONENTS` binds only the shared
  replay contracts (adapter, reducer, levels, consumption, restart, state
  migration, parity); the runner module/CLI are not plan-authorized
  fingerprints. Disposition **branch B**: plan preserved byte-for-byte; a
  versioned append-only `runner_compatibility` record binds plan identity to
  the corrected runner fingerprint, empirical-source contract, tests and code
  commit (published after the commit, with the real commit SHA).
- **CLI:** empirical `run`/`resume` no longer accept or require
  `--synthetic-stream`; all empirical inputs resolve through
  `EmpiricalInputBindings` from the verified plan/evidence registry (no
  caller-selected data paths, no strategy parameter overrides). The exact
  previously authorized command passes parser regression and is still not
  executed.
- **Pipeline:** `bot/validation/empirical_input_pipeline.py` streams the
  accepted tick year and six causal candle frames chronologically, joins DXY
  by authoritative broker-symbol keys, replays official news through the
  development-only adapter, applies Phase 8H cost and Phase 8L metadata
  scenarios through existing execution/risk contracts, and follows the
  parity-proven orchestration contract (`(result, record)`; prior state into
  `evaluate_setup_inputs`); thin/insufficient frames fail closed. Decision
  reuse across scenarios is rejected; each scenario replays independently.
- **Resume:** full source cursors, strategy/lifecycle/risk/account state,
  pending intents and engine in-memory state serialize and restore; journal
  entries precede snapshots; empty state payloads fail closed (no zero-fill,
  no duplicate fills); rehearsal proves interrupted/resumed equivalence.
- **Rehearsal:** all 64 cells run through the same event-pipeline interface
  on labelled synthetic fixture bindings with a determinism pass,
  interruption/resume equivalence, rerun suppression and full verification.
- Gates unchanged and false; no strategy evaluation, optimization,
  profitability computation, holdout access or MT5/account/network/order
  operation occurred.

## 8N-J — Empirical replay performance (engineering acceleration; gate NOT met)

Branch phase/8-scientific-validation, base d90e467875ed3082dccaab9505d6c03ddbb2f87d.
Built the fold-scoped causal input index + `OptimizedCellDriver`
(`bot/validation/replay_input_index.py`): decision timestamps, tick
partition/row-group min/max, source identities; identity binds plan, fold,
all source hashes, pipeline fingerprint, schema, code version; published
atomically outside Git with completion marker + canonical hash + readback
verification (all four folds published and verified). Optimized driver does
exact state-dependent processing: full tick processing while an intent is
pending or a position is open, idle-span skipping with zero state effect,
decision-before-quote merge order, bounded batches, exact optimized resume
(cursor state + index identity + batch size bound into checkpoints). Runner
wired with a fold-cached index provider and fail-closed path detection;
empirical `run`/`resume` commands unchanged. Two shared-pipeline crash
defects found and repaired (END_OF_DATA close on fully-closed positions;
stale in-memory setup record after fill-time store mutation).

Real-data engineering benchmark (labelled NOT STRATEGY EVIDENCE; fold 1
first 6 evaluation hours, pre-declared): equivalence exact (decision
identities + semantic quote state with injected intents, 2 fills both
paths), 83 % of quotes skipped, 1/403 row groups decoded, 556 MB peak,
4.15× over the reference on the window. Profile: decision-bound strategy
evaluation ~0.95 s/decision dominates (skip overhead ~0.04 ms; active
quotes ~7.4 ms). Honest projection: **6.81 h/cell, ~436 h single-worker,
~218 h two-worker — one order of magnitude above the 24 h authorization
gate**. Per the phase contract: performance gate NOT met; no run
authorization; the remaining cost is the frozen candidate's gate stack and
cannot be reduced without changing strategy semantics. Proposed
semantics-preserving next architecture in
`PHASE8N_EMPIRICAL_REPLAY_PERFORMANCE.md` (fold-level memoization of
scenario-invariant orchestrator inputs; candidate-path indexed inputs;
then bounded 2-worker scheduling), which requires a new
runner-compatibility record, not a new plan.

Gates unchanged and false; no strategy evaluation, optimization,
profitability computation, holdout access or MT5/account/network/order
operation occurred.

## 8N-K — Checkpoint indexed replay and memoize causal market features

Stage 1: verified the uncommitted 8N-J dirty state path-by-path (all 8N-J
exclusive, semantics-preserving), sanitized probes (raw artifacts moved
outside Git; `probes/PROBES.md` documents them), re-ran the full
verification battery (1,268 passed) and created the authorized checkpoint
commit `perf: add indexed empirical replay groundwork` =
`7f3e3edad6b27254325a6463d421bfb95248d2db`; detached clean-snapshot
verification passed (27/27 focused tests on a fresh worktree at the
checkpoint).

Stage 2: per-function decision-path profile (cProfile over 10 real fold-1
decisions, `probes/_k_profile_cell/decision_callgraph.json`): of the
~1.74 s/decision (inflated), `analyze_market_structure` (8 calls/decision)
+ `build_gate_inputs` + bias + liquidity + DXY ≈ 86 % is **scenario-
invariant feature construction**; the pure shared reducer
`evaluate_strategy_gates` is ~21 ms/decision. Built
`bot/validation/market_feature_store.py`: one immutable row per decision
(bias snapshot + resolution, session, news, DXY context, gate inputs
payload, gate status/payload/event id, source identities), identity bound
to plan/fold/input-index/sources/fingerprints/schema/builder with row
digest + `coverage` field (`full` vs `partial:N-of-M` — the production
loader refuses partial stores), atomic non-overwrite publication with
completion marker + readback verification. Runner-attached
`FoldFeatureProvider` serves per-cell snapshots; the handler fast path
(opt-in `--market-features fast`, default `off`) replicates the reference
gate sequence and feeds the untouched shared reducer with cell-local
state; candidate decisions fall back to the reference input path by
design. Focused suite `tests/phase8n_k/test_market_feature_store.py`:
12 tests (classification A/B/C, store determinism, tamper rejection,
non-overwrite, partial-coverage refusal, 3-way equivalence
reference/indexed/snapshot, no cell-local state leakage, restart,
batch independence, holdout firewall, no MT5/network imports) — all
green, plus 8N-J suite re-verified.

Mechanically sampled fast-path benchmark across all four folds (≥ 1,000
decisions, first-N-per-fold window rule pre-declared, labelled EMPIRICAL
ENGINEERING BENCHMARK — NOT STRATEGY EVIDENCE) and the updated
`estimate-optimized` projection: measured results recorded in
`docs/PHASE8N_EMPIRICAL_REPLAY_PERFORMANCE.md` §8 and the benchmark
report. Stage 2 commit only if the ≤ 24 h gate passes; no empirical
run authorized either way.

Phase 8N-K (2026-09-20): Stage-1 checkpoint `7f3e3ed` (indexed replay
groundwork, authorized) and Stage-2 commit `92b2be1` (causal market feature
memoization) landed on `phase/8-scientific-validation`. Reference/indexed/
snapshot paths proven exactly equivalent; 1,000-decision sampled benchmark
plus fold-01 full-fold density probe and full-cell end-to-end measurement
(18.4 min/cell, 0 candidates) give a measured 23.18 h single-worker /
13.35 h two-worker projection (≤ 24 h gate met on the measured basis; the
≤ 12 h preferred target is met only with two workers). Runner-compatibility
record `evidence-runner_compatibility-v1-a81ef827217a69c6` published
(plan preserved); detached clean-snapshot verification green. A transient
frozen-data read anomaly and a ~3× thermal slowdown were diagnosed and are
documented in
`docs/PHASE8N_EMPIRICAL_REPLAY_PERFORMANCE.md` §8.9–§8.10; hardware
diagnostics and fold-03/04 density confirmation are required before any run
authorization. No empirical evaluation was executed.

## 2026-09-21 — V1 sample-size feasibility disposition (sealed)

The preregistered feasibility gate was executed read-only from the canonical
checkpoint `c38f9dc8` and returned `FEASIBILITY INSUFFICIENT — NO RUN
AUTHORIZED`: fold-01 produced zero raw strategy candidates across 13,269
scheduled decisions (7,273 skip + 5,827 wait + 169 news-blocked; exactly
reconciled), so the >=30-closed-trades-per-fold requirement is mathematically
unreachable under `phase6-frozen-v1`. Folds 02-04:
NOT_ATTEMPTED_DUE_TO_EARLY_FUTILITY. The zero-candidate outcome was
investigated and classified LEGITIMATE_FROZEN_STRATEGY_BEHAVIOR (526
decisions reached frozen confluence scoring; best score 7/8 against the
frozen 8/8 threshold). Disposition: `REJECTED_FOR_SAMPLE_SIZE_FUTILITY`; the
V1 64-cell plan is retained but `PROHIBITED_DUE_TO_SAMPLE_SIZE_FUTILITY`.
Evidence: `docs/PHASE8_FEASIBILITY_DISPOSITION_V1.md`; artifact manifest:
`baseline/feasibility_audit_v1_artifact_manifest.json`; contamination record:
`phase8n_feasibility_audit_v1_fold01` in
`baseline/phase8_contamination_register.json`. No profitability metric was
computed; Phase 0-7 remain complete; Phase 8 infrastructure functioned as
intended; holdout untouched; the fingerprint/canonical-byte engineering
debt is now `REPRODUCIBILITY_ENGINEERING_DEBT — RESOLVED FOR PROSPECTIVE
SCIENTIFIC FREEZES` via the verified `canonical_git_blob_v1` contract
(`docs/PHASE8N_CANONICAL_BYTE_CONTRACT.md`; historical V1 identities
unchanged, legacy contracts compatibility-only, prospective freezes must
explicitly declare an approved prospective contract). This does not
authorize a V2 scientific freeze; V2 research charter is now approved
and preregistered: `phase8-v2-research-charter-v1-8527e3a5eec98f53`
(final SHA-256
`8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`,
`docs/PHASE8_V2_RESEARCH_CHARTER.md`, status `APPROVED / PREREGISTERED`).
Active research identity: `phase6-development-v2`; `phase6-frozen-v2`
does not exist and charter publication does not freeze a strategy. No
strategy experiments have yet occurred; research budgets are sealed
(diagnostic investigations <= 12, strategy variants <= 8, numeric
parameter trials <= 4; upward revision prohibited after the first
strategy-variant result). Fold 01 is initially the sole permitted
design evidence; Folds 02-04 remain reserved and are released
sequentially and fail-fast; holdout remains untouched. Next
authorized task: the V2 semantic diagnostic stage on Fold 01 only
(read-only structural diagnostics under the charter's hypothesis
register; no profitability metrics). No demo/live trading is
authorized.

V2 preregistration (2026-09-21): hypotheses `phase8-v2-H001`
(exact-overlap possibly stricter than the economic concept),
`phase8-v2-H002` (conjunctively restrictive valid-OB predicate) and
`phase8-v2-H003` (temporal association, later diagnostic) registered
in the append-only `baseline/phase8_v2_hypothesis_register.json`;
diagnostic `phase8-v2-D001` (Frozen OB/FVG Structural Attrition
Decomposition) preregistered in `docs/PHASE8_V2_DIAGNOSTIC_D001.md`
as `REGISTERED_NOT_EXECUTED`. Diagnostic budget remains `0 / 12
executed`; no new Fold-01 observation occurred during
preregistration; no strategy variant has been observed so the
8-variant/4-parameter budget lock is not yet triggered. Folds 02-04
remain reserved; holdout untouched. Next authorized task:
implement and execute D001 exactly as preregistered.

Provenance correction `phase8-v2-PC001` (2026-09-22): the D001 /
H001-H003 preregistration was actually published in commit
`8985fb2f8396a999dbddcc8b51342788823dc2c2` at
`2026-09-22T22:20:51Z` (Git author/committer timestamp, verified
against the GitHub authoritative publication timestamp); the
`2026-09-21` date above was erroneous placeholder metadata and is
superseded for chronology only. No empirical observation occurred
before the correction; the diagnostic budget remains `0 / 12
executed`; D001 remains `REGISTERED_NOT_EXECUTED`.

V2 diagnostic D001 execution record (2026-09-23): executed on Fold 01
with frozen tooling '1f2f997c1763f7a6e50f7d02e35d88bcdd568ebf'
(Phase-A: 32/32 tooling tests + 25/25 regression; hard barrier: remote
resolved to the tooling commit; store 'fold-01-1d710826193a6767'
integrity verified over all 13,269 rows). Budget now '1 / 12'
diagnostics; variants '0 / 8'; parameter trials '0 / 4' (result-lock
not triggered). Result record 'phase8-v2-D001-R001' appended to the
register; raw output external under
'evidence/v2_diagnostics/phase8-v2-D001-R001/' (SHA-256
'af03bfbe688b010deb70261eabe2240336e16bbff07d519ea20a8ccbc3b99c10',
4,901 bytes, read-back verified); compact report
'docs/PHASE8_V2_DIAGNOSTIC_D001_RESULT.md'. Dispositions: H001
'SUPPORTED_BY_D001' (FVG present 0/7,316 - overlap never evaluable),
H002 'SUPPORTED_BY_D001' (valid-OB failure concentrated: mitigation
307/526 = 58.4%, outside-PD 79, invalidated 75, no-displacement 61,
aligned 4), H003 'NOT_TESTED_BY_D001'. Decision accounting reconciles
exactly (13,269 = 7,316 + 4,815 + 1,138) and reproduces the known V1
evidence (wait 5,827; skip 7,273 incl. 169 news-blocked; scores
522x5/8 + 4x7/8). No strategy variant selected; no profitability
metric emitted; Folds 02-04 remain reserved; holdout untouched. Next
step: supervisory review before D002 or Variant 1.
