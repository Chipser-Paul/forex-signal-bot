# Phase 8N-A — Evaluation-Plan Amendment Checkpoint

Status: **BLOCKED BEFORE PUBLICATION**. The Phase 8M plan remains the only
frozen plan; it has not been deleted, rewritten, superseded or executed.

## Verified parent and authorized matrix

- Parent package: `evidence-development_evaluation_plan-v1-82ef6fcab5c13547`.
- Parent fingerprint: `ae9b4e2a17562146f0ade44f758ca015f6ab9b017eaeaf665f7745278b131c79`.
- Candidate: `phase6-frozen-v1`, symbol exactly `XAUUSDm`.
- The parent plan and input-readiness verifier passed without using a strategy
  runner. The readiness record binds 2024 ticks (39,715,935 rows), six causal
  candle timeframes, six DXY constituents, official USD news, observed spread,
  the Phase 8H cost policy and ten Phase 8L development-proxy metadata cases.

The owner authorized a factorized matrix, not a 120-combination Cartesian
product. `bot.validation.development_scenario_matrix.compose_scenarios` uses
the existing registered IDs and the following canonical group order:

| Group | Fixed components | Varied component |
| --- | --- | --- |
| PRIMARY_BASELINE | email-reference swap, moderate adverse slippage, baseline metadata | none |
| SWAP_SENSITIVITY | moderate adverse slippage, baseline metadata | all four registered swaps |
| SLIPPAGE_SENSITIVITY | email-reference swap, baseline metadata | all three registered slippages |
| METADATA_STRESS | required 3x adverse swap, severe adverse slippage | all ten registered metadata scenarios |
| COMBINED_WORST_CASE | 3x adverse swap, severe adverse slippage, combined adverse metadata | none |

All combinations use observed historical XAUUSDm bid/ask spread and the
Standard-account development-only zero-commission record. An exact triple of
swap, slippage and metadata IDs is one scenario; duplicate group membership
does not produce a second run. First occurrence in group order, then frozen
registered component order, defines canonical ordering. The verified ladders
yield **16 unique scenarios × four frozen folds = 64 required cells**.
The baseline is `PRIMARY`; the zero-swap and neutral-slippage cases are
`DIAGNOSTIC`; other cases are `MANDATORY_ADVERSE`. The combined worst case is
the final metadata-stress scenario and also belongs to the worst-case group.
Every cell must finish; a missing, duplicate or unexpected cell fails closed.
The primary baseline alone cannot pass development review, and selecting the
cheapest scenario is prohibited.

Exact canonical `swap|slippage|metadata` identities, computed from the
verified registered ladders (every identity is required in folds 01–04):

| Order | Scenario identity | Role |
| --- | --- | --- |
| 01 | `SWAP_EMAIL_REFERENCE|SLIPPAGE_MODERATE_ADVERSE|BASELINE_CURRENT_REFERENCE_PROXY` | PRIMARY |
| 02 | `SWAP_NO_OVERNIGHT_EXPOSURE_DIAGNOSTIC|SLIPPAGE_MODERATE_ADVERSE|BASELINE_CURRENT_REFERENCE_PROXY` | DIAGNOSTIC |
| 03 | `SWAP_EMAIL_2X_ADVERSE|SLIPPAGE_MODERATE_ADVERSE|BASELINE_CURRENT_REFERENCE_PROXY` | MANDATORY_ADVERSE |
| 04 | `SWAP_EMAIL_3X_ADVERSE|SLIPPAGE_MODERATE_ADVERSE|BASELINE_CURRENT_REFERENCE_PROXY` | MANDATORY_ADVERSE |
| 05 | `SWAP_EMAIL_REFERENCE|SLIPPAGE_NEUTRAL_DIAGNOSTIC|BASELINE_CURRENT_REFERENCE_PROXY` | DIAGNOSTIC |
| 06 | `SWAP_EMAIL_REFERENCE|SLIPPAGE_SEVERE_ADVERSE|BASELINE_CURRENT_REFERENCE_PROXY` | MANDATORY_ADVERSE |
| 07 | `SWAP_EMAIL_3X_ADVERSE|SLIPPAGE_SEVERE_ADVERSE|BASELINE_CURRENT_REFERENCE_PROXY` | MANDATORY_ADVERSE |
| 08 | `SWAP_EMAIL_3X_ADVERSE|SLIPPAGE_SEVERE_ADVERSE|REDUCED_MAXIMUM_VOLUME` | MANDATORY_ADVERSE |
| 09 | `SWAP_EMAIL_3X_ADVERSE|SLIPPAGE_SEVERE_ADVERSE|STRICTER_MARGIN_REQUIREMENT` | MANDATORY_ADVERSE |
| 10 | `SWAP_EMAIL_3X_ADVERSE|SLIPPAGE_SEVERE_ADVERSE|CONSTRAINED_FREE_MARGIN` | MANDATORY_ADVERSE |
| 11 | `SWAP_EMAIL_3X_ADVERSE|SLIPPAGE_SEVERE_ADVERSE|FOK_MISSED_FILL_STRESS` | MANDATORY_ADVERSE |
| 12 | `SWAP_EMAIL_3X_ADVERSE|SLIPPAGE_SEVERE_ADVERSE|PARTIAL_FILL_REDUCED_LIQUIDITY` | MANDATORY_ADVERSE |
| 13 | `SWAP_EMAIL_3X_ADVERSE|SLIPPAGE_SEVERE_ADVERSE|STOP_FREEZE_RESTRICTION_GUARD` | MANDATORY_ADVERSE |
| 14 | `SWAP_EMAIL_3X_ADVERSE|SLIPPAGE_SEVERE_ADVERSE|MINIMUM_VOLUME_RISK_BUDGET_FAILURE` | MANDATORY_ADVERSE |
| 15 | `SWAP_EMAIL_3X_ADVERSE|SLIPPAGE_SEVERE_ADVERSE|STALE_METADATA_REJECTION` | MANDATORY_ADVERSE |
| 16 | `SWAP_EMAIL_3X_ADVERSE|SLIPPAGE_SEVERE_ADVERSE|COMBINED_ADVERSE_BROKER_CONDITIONS` | MANDATORY_ADVERSE |

## Empirical mapping gate

The proposed mapping version is `phase8n.empirical-decision-mapping.v1`.
The XAUUSDm profile's entry timeframe is M5. Phase 2 provides closed-candle
`available_at` selection, and Phase 6 provides the pure `StrategyInput` and
`StrategyDecision` reducers. The existing Phase 3 `new_entry_intent` and
`intent_from_strategy_entry` preserve source-candle chronology. These
interfaces are necessary but do not yet form an empirical adapter.

The exact fields that cannot currently be derived through a pure offline
production path from the accepted package are:

1. `requested_side` and `bias`: the live orchestrator obtains a bias snapshot
   through symbol-reading functions, not an injected set of causal W1/D1/H4
   frames. No frozen offline bias-snapshot construction is registered.
2. `SetupEvidence` flags: liquidity, discount/premium, FVG overlap and sweep
   are assembled by live market-data readers and mutable orchestrator state.
   The accepted frames do not by themselves define their production context.
3. Entry mapping (`entry_type`, trigger, stop and final target): the legacy
   orchestrator uses `determine_entry` and a separate level builder after
   confluence. `StrategyDecision` does not contain these fields; they cannot
   be invented or inferred from its eligibility flag.
4. Stateful compatibility gates: setup IDs, expiry and duplicate suppression
   require a deterministic fold/resume state contract before replay.

Therefore neither a golden empirical/live parity proof nor a safe entry-intent
translation can pass yet. Insufficient HTF history, stale DXY, uncertain news,
closed sessions, rejected confluence, duplicate decisions, symbol limits,
gaps, incomplete candles and repeated events must all reject or remain
idempotent in the eventual adapter; they must not be assigned permissive
fallbacks. No source candle may fill its own signal.

Publishing a `FROZEN_AWAITING_AUTHORIZED_RUN` superseding package now would
misrepresent readiness. The parent remains unchanged, not marked
`SUPERSEDED_BEFORE_EXECUTION`; no new canonical fingerprint exists. Holdout,
final validation and Phase 9 remain blocked. No strategy evaluation is
authorized by this checkpoint.

Next task: extract or inject the *existing* production bias, setup and entry
construction against Phase 2 causal snapshots, prove live/replay normalized
decision and intent parity on synthetic golden scenarios, then publish an
append-only amendment bound to the parent and all unchanged evidence/code
identities. Only after that may the old plan be described as superseded and a
new exact fingerprint be submitted for separate run authorization.

Phase 8N-B follow-up: frame-based production bias and liquidity calculations
have been extracted and tested against their live wrappers. Full decision and
intent mapping remains blocked by stateful setup/entry/final-level gates and
by unavailable as-of-2024 provider retrieval evidence for the frozen news
freshness rule. See `docs/PHASE8N_EMPIRICAL_STRATEGY_ADAPTER.md` and
`baseline/phase8n_production_mapping.json`. No amendment has been published.

Verification of this uncommitted checkpoint: six focused matrix tests, 59
Phase 8A tests, and 189 Phase 8B/known-defect tests passed. Full repository
suite: 1,023 passed, one opt-in skipped, ten subtests passed, zero failures,
xfails or xpasses. Compilation, safe imports without MetaTrader5, 38 JSON/YAML
parses, `pip check`, `git diff --check`, and changed-file secret scan passed.
There is no staged content, commit, or detached committed snapshot to verify.

Phase 8N-C follow-up: state event-time injection, a live-delegated pure
stop/target builder and a verified retrospective official-news event-time
adapter are now synthetic-test covered. News classification remains
`RETROSPECTIVE_OFFICIAL_SCHEDULE`, not fresh 2024 provider evidence. The
production setup evidence and stable setup identity still lack a shared pure
reducer; therefore no complete empirical decision/intent parity, append-only
superseding plan, new fingerprint or authorized run command exists. The
Phase 8M parent remains unchanged.

Phase 8N-D follow-up: verified local retained-work checkpoint
`a2b358542cfa2f68e6e1b3660e1df2b21a18ac4a` exists. The uncommitted Stage 2
shared gates and synthetic long/short level/intent parity are now implemented.
They do not yet cover final-fill consumption, complete lifecycle restart and
every required matrix case. The parent plan is **not superseded**; no new plan
ID/fingerprint or executable authorization was published. All evaluation,
holdout, final-validation and Phase 9 gates stay false. See the Stage 2 gap in
`docs/PHASE8N_CAUSAL_STRATEGY_ORCHESTRATION.md`.
# Phase 8N-E amendment contract

## Verified append-only publication

- Original Phase 8M package: `evidence-development_evaluation_plan-v1-82ef6fcab5c13547`.
- Original fingerprint: `ae9b4e2a17562146f0ade44f758ca015f6ab9b017eaeaf665f7745278b131c79`.
- Successor package: `evidence-development_evaluation_plan-v1-ba2745f96fda3939`.
- New plan fingerprint: `d69bbed4542d9517dc46d043d12324f6a921a846bca39c30e57fdc3774779c72`.
- Scenario-cell fingerprint: `474c7aec8d3f6d23b21d7417bf7b22e7fdcb173e8009392a192fe50415dd3d0d`.
- Status: FROZEN_AWAITING_AUTHORIZED_RUN; successor records the parent as
  SUPERSEDED_BEFORE_EXECUTION. All four original parent files retain identical
  SHA-256 hashes; original content/status were not edited.
- Two publications returned the same identity. Every frozen candidate,
  input-readiness, fold, cost/metadata scenario and parent policy is retained.
- Proof: 79 focused tests; 1,131 selected Phase 2-8/known-defect tests; full
  suite 1,188 passed, one pre-existing opt-in skip, ten subtests passed, zero
  failures/xfails/xpasses. All 64 cells are structural/synthetic only.
- All run/holdout/final-validation/Phase 9 gates remain false. No run command
  is authorized. An approved streaming runner for this exact successor does
  not yet exist; neither the shadow diagnostic nor the plan-control CLI may
  be used as an empirical execution substitute.

The prior blocked checkpoints below remain historical evidence. The successor
publisher binds the unchanged parent policies/inputs and exact 16-scenario,
four-fold matrix to versioned consumption, restart, state migration and tested
implementation fingerprints. It is append-only and cannot run the plan.
The original parent package stays byte-for-byte unchanged. Its successor
records SUPERSEDED_BEFORE_EXECUTION, while its own status is
FROZEN_AWAITING_AUTHORIZED_RUN. All empirical, holdout, final-validation and
Phase 9 gates remain false. Actual publication identity is recorded below only
after acceptance and two idempotent publication checks.
# Phase 8N-F append-only correction

The earlier Phase 8N-E publication record below is historical, not current
run readiness. Its package `evidence-development_evaluation_plan-v1-ba2745f96fda3939`
and fingerprint `d69bbed4542d9517dc46d043d12324f6a921a846bca39c30e57fdc3774779c72`
must never be executed. Disposition status: INVALIDATED_BEFORE_EXECUTION.
Original and faulty plan packages remain byte-for-byte immutable.

The disposition binds the faulty identity/fingerprint, defective code
checkpoint, exact reason, failed discovery-test identity and zero empirical
cells. UTC discovery/publication time belongs only to envelope provenance;
it cannot change the semantic disposition or successor identity.

The corrected `phase8n.superseding-development-plan.v2` binds
`phase8n.recovery-outcome.v1`, corrected source fingerprint, regression
fingerprint/proof, all prior implementation fingerprints and the invalidation
relationship. Frozen inputs, cost/metadata scenarios, candidate and four-fold
16-scenario/64-cell matrix are retained. Verification rebuilds the full
expected contract and rejects tampering even with a recomputed outer hash.
Publication uses the existing atomic non-overwriting evidence store,
recognizes a second identical publication, reloads both new packages and
checks all four files of both old packages before/after publication.

Only the corrected successor is current FROZEN_AWAITING_AUTHORIZED_RUN;
legacy on-disk status strings are not authoritative disposition evidence.
Every execution/holdout/final-validation/Phase 9 authorization flag is false.
No empirical runner or next execution command is authorized.
Verified publication identities:

- Disposition: `evidence-development_plan_disposition-v1-dac472a23118c880`.
- Corrected successor: `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81`.
- Plan fingerprint: `adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09`.
- Cell fingerprint: `dc624f125ce1e0014f27d0bc3a0489b03b1ea9b8be3c7088d51a45150aa6aaf6`.
- Corrected consumption component: `328d1254e8b76e90a7124e0687e64b25515def630451e4e84e2e7e400e32c3e7`.
- Regression source: `61de1e4e5379215b82b144158ace0804fc1a95428a6e39e3ba135e04ea05a7ca`.

Two idempotent checks passed; both predecessors' four-file hashes are
unchanged. No source datasets were opened. Full suite: 1,222 passed, one
pre-existing opt-in skip, ten passing subtests, zero failures/xfails/xpasses.
Selected Phase 2-8/known defects: 1,165 passed. Focused contracts: 113 passed.
The machine-readable baseline records both old identities, new identities,
source bindings and predecessor hashes. Commit and exact detached results
are reported outside the snapshot containing this record.
