# Phase 8 V2 — Diagnostic D006 Preregistration: V003 Post-Confluence Entry-State Attrition Decomposition

DEVELOPMENT_DIAGNOSTIC_EVIDENCE — D006 — FOLD01 — NOT PROFITABILITY EVIDENCE

* Diagnostic: `phase8-v2-D006` — "V003 Post-Confluence Entry-State Attrition Decomposition"
* Linked hypothesis: `phase8-v2-H008` — "Post-Confluence Entry-State Alignment Bottleneck"
* Diagnostic class: `DIAGNOSTIC_INVESTIGATION`; evidence tier: `TIER_A_FOLD01`
* Diagnostic type: READ-ONLY decomposition of frozen entry-state rejection mechanisms. No profitability metric, no counterfactual candidate count, no parameter trial, no strategy variant.
* Motivating accepted result: `phase6-development-v2-V003-R001` (OPPORTUNITY_INSUFFICIENT; candidate_ready 81 vs frozen Tier-A adequacy target 90; V002 candidates 61 preserved + 20 V003 temporal-memory additions). V003 R001 is PRIOR RESULT GOVERNANCE EVIDENCE only: its sealed result file may be read during D006 execution for provenance/integrity reconciliation, and its observed counts are motivation recorded here — they are NEVER synthetic test oracles and NEVER encoded in diagnostic logic.

## 1. Hypothesis H008 (registered verbatim)

Statement (byte-exact, never rewritten by D006):

> After a setup satisfies V003 structural confluence and passes the unchanged canonical strategy protections, candidate attrition may be concentrated in a small number of frozen entry-state readiness or liquidity-alignment predicates rather than representing diffuse absence of executable setup context.

Economic rationale (verbatim):

> Structural confluence and execution readiness represent distinct stages. A setup may possess coherent OB/FVG structure and pass protected strategy filters while the persistent execution state has not yet encoded the matching structure/liquidity/displacement configuration. If the final entry-stage failures concentrate in one coherent state predicate, the bottleneck should be understood before any execution-semantic variant is proposed.

Hypothesis class: `HYPOTHESIS_NOT_CONCLUSION`.

### 1.1 What H008 does NOT claim

H008 does NOT claim that any existing entry rule should be removed or weakened. It does NOT claim: liquidity alignment is too strict; confirmed structure should be removed; displacement state should be ignored; daily-limit or news protections should be weakened; early-entry rules should be broadened; score threshold should change; RR should change; state expiry should change. D006 is decomposition only.

## 2. Empirical universe (future execution only — DO NOT execute in this preregistration or tooling task)

Existing authorized Fold-01 snapshot store `fold-01-a8b406884ab3525a` (identity SHA-256 `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4`, rows SHA-256 `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22`, 13,269 snapshots, fold-01/full), full `verify_rows=True` before any observation. The prohibited historical store `fold-01-1d710826193a6767` is refused. Folds 02–04, holdout, 2025+ and Tier B fail closed. All reconstructed state must be causally available at `decision_at`; no future candle, no future state.

## 3. Primary population (structural definition — no observed count may be encoded)

`P_ENTRY_REJECT` is defined naturally at execution time: every V003 observation satisfying

* `v003_gate11_passed == True` (V003's frozen 8/8 Gate-11 score), AND
* `v003_strategy_eligible == True` (unchanged canonical V003 strategy protections), AND
* `v003_entry_ready == False` (frozen Gate-12/13 `determine_entry` returns no entry).

The previously observed count `29` must NOT be encoded into diagnostic logic or synthetic tests. After the V003 surfaces are derived naturally at runtime, the tooling MAY load the sealed V003 R001 result and compare reproduced surfaces against it as provenance/integrity reconciliation (section 17). No count from the sealed file may flow into derivation logic.

## 4. Reference populations (reported separately; descriptive context)

* `R_READY` — V003 observations with `v003_strategy_eligible == True` AND `v003_entry_ready == True`.
* `R_STRATEGY_REJECT` — V003 Gate-11 passers with `v003_strategy_eligible == False`. PROTECTED-POLICY CONTEXT ONLY; never V004 recovery headroom; no "candidates if protection removed" computation.
* `R_GATE11_FAIL` — V003 Gate-11 entrants failing V003's 8/8 score. Descriptive count only.

Reconciliation: all V003 Gate-11 entrants must reconcile exactly across the appropriate stage partitions (every entrant is in exactly one of R_GATE11_FAIL / R_STRATEGY_REJECT / R_READY / P_ENTRY_REJECT; duplicates fail closed).

## 5. FVG-evidence source stratification

For all primary and entry-stage reference populations, stratify every surface by the V003 evidence source observed on the decision: `FINAL_SURFACE` versus `TEMPORAL_MEMORY` (frozen `v003_fvg_evidence_source`). The two strata are NEVER merged. This establishes whether the entry-stage bottleneck (i) already exists in the preserved V002/final branch, (ii) is disproportionately associated with V003 temporal-memory additions, or (iii) affects both similarly. No counterfactual candidate counts of any kind.

## 6. Sources of truth (frozen; never modified)

* Entry model: `strategies/smc_engine/entry_model.py::determine_entry` — D006 mirrors/decomposes its CURRENT predicates exactly; no alternative entry model.
* State: `strategies/smc_engine/strategy_state.py::StrategyState` — the same V002/V003 private persisted-state reconstruction path (`_v002_private_entry_state` → `bot.strategy.setup_state.state_from_record` over the decision's own next-record). The canonical state chain is never mutated; diagnostics use a separate reconstructed/deep-copied state instance (required because `ready_for_entry()` mutates `missing_conditions`).
* V003 semantics: `bot/strategy/variant_v003.py` and `backtests/phase8_v2_variant_v003_eval.py` reused verbatim where safe; no duplicated/inconsistent V003 semantics.

## 7. Score context

V003 candidate-relevant Gate-11 score remains exactly 8/8; therefore the entry mode under the current `determine_entry` contract is `conservative`, never aggressive. D006 MUST NOT evaluate score 10 or any alternate score. Early-entry's special `score >= 10` displacement relaxation (`allowed_missing.add("Displacement / FVG")`) is NOT available to V003 and is reported only as a frozen unreachable branch for this population.

## 8. Entry-rejection classifier (deterministic, read-only, ordered)

Every `P_ENTRY_REJECT` rejection maps to exactly one frozen category, evaluated in this order:

* **E1 — `STATE_EXPIRED`**: `state.is_expired() == True`. The canonical state is never `reset()` (a diagnostic copy absorbs the frozen reset path); state age is recorded descriptively.
* **E2 — `READINESS_INCOMPLETE`**: evaluate frozen `state.ready_for_entry()` on a diagnostic copy and record the exact `missing_conditions`; evaluate frozen early-entry eligibility exactly (frozen `_can_use_early_entry` at score 8). If `state_ready == False` AND `early_entry_ok == False` → `READINESS_INCOMPLETE`.
* **E3 — `STRUCTURE_DIRECTION_UNRESOLVED`**: if readiness/early-entry permits continuation but `state.structure_dir not in {"bullish", "bearish"}` → `STRUCTURE_DIRECTION_UNRESOLVED`.
* **E4 — `LIQUIDITY_ALIGNMENT_MISMATCH`**: for bullish structure the valid combinations are exactly (`liquidity_side == "sell"` AND `liquidity_type == "equal_lows"`) or (`liquidity_side == "buy"` AND `liquidity_type == "internal_continuation"`); for bearish structure exactly (`liquidity_side == "buy"` AND `liquidity_type == "equal_highs"`) or (`liquidity_side == "sell"` AND `liquidity_type == "internal_continuation"`). If neither valid combination holds → `LIQUIDITY_ALIGNMENT_MISMATCH`.
* **E5 — `UNMAPPED_ENTRY_REJECTION`**: frozen `determine_entry` returned None but the mirror maps none of E1–E4. Any nonzero E5 makes the D006 interpretation `INCONCLUSIVE_D006` and FAILS CLOSED for any future V004 justification.

## 9. `ready_for_entry` subpredicates

For every primary member report the frozen readiness booleans: `structure_state == "confirmed"`, `liquidity_swept == True`, `displacement_seen == True`, `daily_limits_hit == False`, `news_clear == True` (from `news_status`), plus the exact `missing_conditions` drawn only from `Confirmed structure`, `Liquidity sweep`, `Displacement / FVG`, `Daily limit clear`, `News clear`. Record single-condition and co-occurrence distributions. Do not invent an "other" condition; an unknown condition FAILS CLOSED.

## 10. Early-entry subpredicates (score 8)

At frozen V003 score 8 the allowed missing set is exactly `{"Confirmed structure"}` (displacement relaxability exists only at score >= 10 and is therefore unreachable). Record descriptively: missing set eligible for early entry yes/no; `structure_state` in transition/range/None yes/no; internal structure event BOS/CHOCH yes/no; sweep_rejected yes/no; OB zone context present yes/no; FVG zone context present yes/no; Asian priority context present yes/no; final `early_entry_ok`. No rule changes.

## 11. Liquidity-alignment surface

For all primary members report exact `structure_dir`, `liquidity_swept`, `liquidity_side`, `liquidity_type`; produce exact contingency counts `structure_dir × liquidity_side × liquidity_type` with raw cell counts preserved before any regrouping; and publish the semantic valid/invalid alignment count according to frozen `determine_entry`.

## 12. State-expiry surface

For every primary observation report `decision_at`, `state.last_update`, state age in minutes and `state.is_expired()`. Frozen expiry is `STATE_EXPIRY_MINUTES = 120`; no alternate expiry (60/90/180/no-expiry) is evaluated; the numeric budget remains untouched.

## 13. Strategy-rejection context (R_STRATEGY_REJECT)

Record the exact frozen `v003_strategy_reasons` distribution and explicitly label protected classes (regime; bias; DXY; session; news; symbol/allowlist; consumed/lifecycle safety) according to the actual emitted reason strings. Do NOT compute "candidates if protection removed"; do NOT use this population as V004 headroom.

## 14. No RR / pullback rejection claim (verified frozen-code contract)

At V003 score 8, once entry readiness/early-entry permits continuation, structure direction is bullish/bearish and frozen liquidity alignment is valid, `determine_entry` returns a conservative partial entry unconditionally (the frozen code contains no RR, pullback-distance, FVG-distance or limit-distance rejection gate on this path). Therefore no D006 category may be named `RR_TOO_LOW`, `PULLBACK_TOO_FAR`, `FVG_DISTANCE_FAIL` or `LIMIT_DISTANCE_FAIL` unless the frozen source actually changes before execution — in which case the task STOPs due to baseline mismatch.

## 15. Production-parity requirement (synthetic regressions)

Synthetic tests must prove the diagnostic rejection classifier agrees exactly with frozen `determine_entry(...)`: for each category construct an independent copied state, run the diagnostic classifier, separately run `determine_entry` on a second independent copy, and require (i) E1–E4 ⇒ `determine_entry` returns None; (ii) a valid ready/aligned case ⇒ a non-null entry; (iii) no production state mutation leaks into the diagnostic chain. Required coverage: E1 expired-state test (classifier `STATE_EXPIRED`, frozen model None, no reset of the authoritative test state); separate readiness tests for each of the five missing conditions plus relevant co-occurrences with exact missing-condition reporting; early-entry tests at score 8 (valid transition/range early entry succeeds; failure when liquidity sweep, displacement, daily limit, news, internal confirmation or zone/priority context is missing; one explicit guard that score 10 lies outside D006's V003 empirical surface and no score-10 evaluation exists); liquidity-alignment tests (exactly the four valid combinations accepted — bullish sell/equal_lows and buy/internal_continuation; bearish buy/equal_highs and sell/internal_continuation — mismatched combinations rejected); and an unmapped-guard test (a mocked production-entry rejection inconsistent with E1–E4 classifies `UNMAPPED_ENTRY_REJECTION` and the interpretation fails closed).

## 16. H008 disposition rule (applied only after separately authorized execution)

* `SUPPORTED_BY_D006` — only if entry-stage failures show clear concentration in one or a small number of coherent frozen state/readiness/liquidity mechanisms that plausibly represent a mismatch between structurally accepted setup context and execution-state representation. No arbitrary numerical percentage cutoff; the argument must use exact raw counts, concentration, economic/state-machine coherence and the final-vs-temporal source comparison.
* `NOT_SUPPORTED_BY_D006` — if failures are diffuse or predominantly represent economically valid absence of structure/liquidity/displacement context with no coherent state bottleneck.
* `INCONCLUSIVE_D006` — if unmapped rejections occur, the baseline does not reproduce, the tooling cannot distinguish predicates, or the population is too ambiguous for a defensible interpretation.

No V004 follows automatically from any disposition.

## 17. V003 baseline reproduction contract (future execution)

D006 execution must FIRST reproduce V003's frozen surface using the V003 strategy blob, corrected TC001 tooling semantics and the same authorized store. Runtime reconciliation MAY load the sealed V003 R001 result (`C:/Users/chips/forex-signal-bot-data/phase8/v2_variants/phase6-development-v2-V003/fold01/phase6-development-v2-V003_result.json`, governance-bound SHA-256 `50117c399481a2e31b8da6260da4e05c8719a522efb524f80bb2063319c41ff8`, 45,221 bytes — never modified) and require equality for the prior observed surfaces: Gate-11 entrant identity/count; V003 Gate-11 pass set/count; canonical-strategy pass set/count; candidate-ready set/count; setup IDs. No empirical numbers are hardcoded into diagnostic source or tests; they are read from the sealed prior result at runtime. Any mismatch: `D006 BASELINE REPRODUCTION FAILURE` — STOP, no D006 interpretation.

## 18. Exact primary-ID reconciliation

The primary D006 population IDs must equal `canonical_strategy_pass_set − candidate_ready_set` EXACTLY (set equality; count equality alone is insufficient; no duplicates; no missing primary member; no extra non-primary member).

## 19. Prohibited counterfactuals and banned outputs

D006 MUST NOT calculate candidate_ready under any removed/broadened/expanded condition: no `candidate_if` any state condition removed, liquidity alignment broadened, expiry removed, early-entry expanded, displacement copied from temporal evidence, or score 10 / alternate state. The only permitted candidate count is the already observed frozen V003 result used for provenance/reconciliation. Banned output keys/phrases (structurally rejected, semantic variants included): `candidate_if`, `rescued_candidates`, `would_pass`, `if_removed`, `alternate_expiry`, `alternate_state`, `alternate_score`, `score_10_candidate`, `relaxed_liquidity`, `pnl`, `profit`, `win_rate`, `expectancy`, `drawdown`, `sharpe`, `returns`, `closed_trades`. No protected-semantic weakening: DXY, news, session, regime, symbol allowlist, risk, daily limits, cascade controls, score threshold and score weights are not modified or proposed for removal during tooling. No numeric parameter trial: state expiry minutes, liquidity timeout bars, score values, OB expiry, FVG lag, RR and distance thresholds are never varied (numeric budget 0 / 4).

## 20. Boundaries — what D006 does NOT touch

No V004 is registered, implemented or motivated by D006; V003 is not modified. H008's statement is never rewritten by D006; H003, H001, H002, H004–H007, D001–D005 records and the V002/V003 registrations are untouched. Budget: diagnostics `4 / 12` until the first separately authorized real D006 Fold-01 observation makes them permanently `5 / 12`; variants remain `3 / 8`; numeric remains `0 / 4`; upward revision lock ACTIVE. D006 preregistration and tooling consume ZERO budget. Tier B remains SEALED (the V003 R001 outcome `81 < 90` does not meet the preregistered Tier-A adequacy target).

## 21. Required output surface (future result document)

Decision accounting; V003 baseline reproduction; entry-stage populations; primary population count/IDs; final-vs-temporal source stratification; state expiry distribution; `ready_for_entry` truth count; missing-condition distribution; missing-condition co-occurrence table; early-entry predicate decomposition; structure-state distribution; structure-direction distribution; liquidity-side distribution; liquidity-type distribution; structure × side × type contingency; frozen liquidity-alignment valid/invalid counts; exact entry-rejection category distribution; strategy-rejection protected-context reason distribution; H008 proposed disposition. No profitability metric anywhere.

## 22. Two-phase discipline

Phase A (this document + register records H008/D006) preregisters the hypothesis, diagnostic and tooling contract. Phase B implements and freeze-commits synthetic-tested tooling (`backtests/phase8_v2_diagnostic_d006.py`) with a HARD STOP before any real Fold-01 access. The tooling is NOT executed by the freeze task. Empirical execution requires separate supervisory authorization; at the instant the first real D006 Fold-01 observation occurs, diagnostics become permanently `5 / 12`.

## 23. Historical specification hashes

Phase-A registration hash for this document is computed on the committed bytes and bound in the register D006 record and the tooling constants. D005 spec lineage remains preserved: `bab242de848a79714828d958196b830d8ae975445f7183c8c6ac03874a747401` (df19e89a), `d7f39d31716b34308ad07afff4260312857653605a0df4d6b58d0f87f1e96941` (c615c3e9), `2b820d608b1d881720369b045366e1986c9cf07f25ce44a2bba26ce837029ed8` (7c9608d5), `b098e3bf55b199a1f34b3ccb87c1d9cc14d58821b30832e8aaf2e0bfb65f8f11` (05f4e6a9), TC003-corrected `7f754232731139816be5597aedadc4a069ead06d53c10423a7a88cd3d5f83d26`. The V003 variant specification identity is bound in `bot/strategy/variant_v003.py::SPEC_SHA256`.

## 24. TC001 — H008 Disposition and V003 Baseline-Reproduction Contract Correction

Pre-empirical tooling correction addressing two defects identified during supervisory review of the Phase-B tooling freeze commit `32a4186917b40fd60cd9a96197c9aae50dcb7782`, committed and pushed before any Fold-01 empirical execution:

### 24.1 Defect A: Removal of Unpreregistered 50% Concentration Cutoff

* **Defect**: The frozen Phase-B tooling mechanically branched `concentration_ratio >= 0.50` into `SUPPORTED_BY_D006` versus `NOT_SUPPORTED_BY_D006`. This violated Section 16 and Section 1.1, which strictly mandate that support or non-support must never be automatically assigned by an arbitrary numerical percentage threshold.
* **Correction**:
  1. The 50% mechanical threshold is completely removed from executable decision logic.
  2. When all primary rejections map to frozen categories ($E_5 = 0$) and the primary population is non-zero, the tooling outputs `proposed_disposition = "H008_SUPERVISORY_INTERPRETATION_REQUIRED"`.
  3. The tooling publishes descriptive concentration metrics: dominant category name, dominant count, dominant share (`round(dominant_count / primary_count, 4)`), top-two categories, top-two count, top-two share (`round(top_two_count / primary_count, 4)`), category distributions, and final-vs-temporal source breakdowns.
  4. Final determination of whether the observed concentration constitutes a coherent bottleneck versus diffuse absence of context is explicitly reserved for supervisory review.
  5. If $E_5 > 0$ (unmapped rejections exist), the tooling outputs `proposed_disposition = "INCONCLUSIVE_D006"` with rationale `UNMAPPED_ENTRY_REJECTION_PRESENT` and fails closed.
  6. If the primary population is zero, the tooling outputs `proposed_disposition = "INCONCLUSIVE_D006"`.

### 24.2 Defect B: Correction of Upstream Baseline-Reproduction Contract

* **Defect**: Section 17 originally required exact identity set reconciliation for upstream Gate-11 entrants, Gate-11 passers, and canonical-strategy passers against the sealed V003 R001 result artifact (`phase6-development-v2-V003_result.json`). However, the sealed V003 artifact only persists aggregate counts for upstream funnel stages (`V003_variant_funnel`: 526 entered, 138 passed Gate 11, 110 passed canonical strategy); it does NOT persist decision ID lists for upstream stages. Only the candidate stage (`candidate_ready`: 81) contains individual decision IDs and setup IDs.
* **Correction**:
  1. Upstream stage populations (Gate-11 entrants, Gate-11 passers, canonical-strategy passers) reconcile against the sealed V003 artifact by exact count (`len == count`). Count mismatches raise `D006BaselineReproductionError` and fail closed.
  2. The candidate stage reconciles by:
     - Exact count (`len(obs_ready) == prior_ready_count == 81`);
     - Exact decision ID set equality (`sorted(obs_ready) == sorted(prior_candidate_ids)`);
     - Exact setup ID reconciliation (`obs_setup_id == prior_setup_id` for every candidate, matching unique count `81` and duplicate count `0`).
  3. D006 reproduces the upstream decision ID sets and hashes them with SHA-256 (over newline-separated sorted decision IDs) for:
     - `gate11_entrants_sha256`
     - `gate11_passers_sha256`
     - `canonical_strategy_passers_sha256`
     - `candidate_ready_sha256`
     These digests are sealed in the D006 output under contract `FIRST_IDENTITY_SEALED_BY_D006`.
  4. Baseline reproduction status is reported truthfully as `SEALED_V003_BASELINE_RECONCILED`.
  5. Primary set identity within D006 remains strictly enforced: `P_ENTRY_REJECT IDs == canonical_strategy_pass_set - candidate_ready_set` as an exact set equality.

### 24.3 Governance and Budget Invariance

* **Budget**: Diagnostics remain `4 / 12`; strategy variants remain `3 / 8`; numeric trials remain `0 / 4`. Upward revision lock `ACTIVE`. TC001 consumes ZERO budget.
* **Zero Empirical Exposure**: The authorized Fold-01 snapshot store `fold-01-a8b406884ab3525a` is NOT accessed or opened during TC001. All test fixtures are synthetic.
* **Tier B & V004 Sealed**: Folds 02–04, holdout, and 2025+ remain sealed. V004 is NOT created.
* **Production Invariance**: Strategy modules and prior diagnostics remain byte-identical.
## 25. TC002 — Exact Frozen V003 Replay Plumbing and Strict Identity Reconciliation

Pre-empirical tooling and governance correction addressing four defects identified during supervisory review of TC001 commit `04dad93c5bedff1a4754a700e1f18d246b52aacc`, committed and pushed before any Fold-01 empirical execution:

### 25.1 Defect C: Exact Frozen V003 Replay Loop Discipline

* **Defect**: The D006 execution loop in `backtests/phase8_v2_diagnostic_d006.py` diverged from the canonical V003/D001 replay contract:
  1. Passed `store.table` instead of `store` to `_snapshot_rows`.
  2. Initialized state with `prior_state_record = None` rather than the canonical seed `StrategyState(event_time=datetime(2024, 1, 1, tzinfo=timezone.utc))`.
  3. Mismatched `classify_snapshot` return contract by treating its result as a row dictionary.
  4. Passed `row` instead of `snapshot` to `_reference_check_failed`.
  5. Called `evaluate_orchestration_decision` with defective signature and unpacked 3 return values instead of canonical `(row, next_record)`.
  6. Incorrectly invoked `assert_store_semantic_compatibility(store)` prior to the replay loop instead of verifying `snapshot` inside `gate11_entered`.
  7. Did not pass `next_record` as `decision_result_record` to `observe_v003_decision`.
  8. Failed to carry forward state sequentially via `state_record = next_record`.
* **Correction**:
  1. `run_d006` exactly mirrors `run_v003`: iterates `_snapshot_rows(store)`.
  2. Seeds state using `record_from_state(StrategyState(event_time=datetime(2024, 1, 1, tzinfo=timezone.utc)), event_at=seed_time)`.
  3. Handles `classify_snapshot(snapshot)` returning `None` for reducer path or `(name, reason)` for non-reducer buckets.
  4. Calls `_reference_check_failed(snapshot)`.
  5. Evaluates decision via `row, next_record = evaluate_orchestration_decision(snapshot, prior_state_record)`.
  6. Restricts `assert_store_semantic_compatibility(snapshot)` to Gate-11 entrants only (`gate_11_confluence_score` present in `row.get("gate_results")`).
  7. Passes `decision_result_record=next_record` to `observe_v003_decision`.
  8. Advances causal state sequentially via `state_record = next_record`.
  9. Structural pair reconstruction for primary rejection decomposition uses `_consumed_ids_from_record(prior_state_record)` and proves synthetic equivalence against observed V003 fields.

### 25.2 Defect D: Feature Store Loader Verification

* **Defect**: CLI entry point invoked `load_feature_store(args.store)` without `verify_rows=True`.
* **Correction**:
  1. Corrected to `load_feature_store(Path(args.store), verify_rows=True)`.
  2. Enforces strict CLI sequence: 1) parse args; 2) `validate_authorized_store_path`; 3) `load_feature_store(Path(args.store), verify_rows=True)`; 4) `run_d006`; 5) `write_result`.

### 25.3 Defect E: Strict Candidate Identity Reconciliation and Digests

* **Defect**: Candidate setup ID reconciliation checked setup IDs only when non-null (`sid is not None`), permitting missing identities to escape validation, and omitted sealing the `P_ENTRY_REJECT` decision ID digest.
* **Correction**:
  1. Strict prior candidate validation: every record in sealed V003 R001 candidate list must possess non-null `decision_id` and non-null `setup_id`; candidate count must equal `candidate_ready`; duplicate decision IDs fail closed.
  2. Strict observed candidate validation: every reproduced observation with `v003_entry_ready == True` must possess non-null `decision_id` and non-null `v003_setup_id`; missing either raises `D006BaselineReproductionError`.
  3. Strict multiset reconciliation: deterministic `(decision_id, setup_id)` pairs between sealed V003 R001 and reproduced observations must match under exact multiset equality (`sorted(obs_pairs) == sorted(prior_pairs)`).
  4. Independent validations: exact candidate decision ID set equality, exact candidate ready count, exact unique setup ID count, and exact duplicate setup ID occurrences.
  5. Sealed decision ID digests: SHA-256 over newline-separated sorted decision IDs are computed and sealed for:
     - `gate11_entrants_sha256` (`FIRST_IDENTITY_SEALED_BY_D006`)
     - `gate11_passers_sha256` (`FIRST_IDENTITY_SEALED_BY_D006`)
     - `canonical_strategy_passers_sha256` (`FIRST_IDENTITY_SEALED_BY_D006`)
     - `candidate_ready_sha256`
     - `p_entry_reject_sha256`
  6. Primary set identity: `P_ENTRY_REJECT IDs == canonical_strategy_pass_set - candidate_ready_set` enforced as exact set equality.

### 25.4 Defect F: Append-Only Governance Register Preservation

* **Defect**: TC001 modified `phase8-v2-D006` in-place within the `diagnostics` array of `baseline/phase8_v2_hypothesis_register.json`, violating the immutable historical preservation requirement.
* **Correction**:
  1. Historical register content at `32a4186917b40fd60cd9a96197c9aae50dcb7782` is restored for all pre-existing records, including `phase8-v2-H008` and the original `phase8-v2-D006` registration.
  2. TC001 and TC002 corrections are recorded strictly as separate append-only entries in `result_records`:
     - `phase8-v2-D006-TC001`: recording removal of 50% cutoff, supervisory interpretation contract, and upstream count vs candidate identity baseline contract.
     - `phase8-v2-D006-TC002`: recording replay loop parity, loader row verification, strict candidate identity multiset checks, P_ENTRY_REJECT digest, and governance register repair.

### 25.5 Governance and Budget Invariance

* **Budget**: Diagnostics remain `4 / 12`; strategy variants remain `3 / 8`; numeric trials remain `0 / 4`. Upward revision lock `ACTIVE`. TC002 consumes ZERO budget.
* **Zero Empirical Exposure**: The authorized Fold-01 snapshot store `fold-01-a8b406884ab3525a` is NOT accessed or opened during TC002. All test fixtures are synthetic.
* **Tier B & V004 Sealed**: Folds 02–04, holdout, and 2025+ remain sealed. V004 is NOT created.
* **Production Invariance**: Strategy modules, state, entry models, and prior diagnostics remain byte-identical.
