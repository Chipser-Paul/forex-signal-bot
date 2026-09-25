# PHASE 8 V2 — DIAGNOSTIC D004 SPECIFICATION (PREREGISTERED)

**Diagnostic:** `phase8-v2-D004`
**Title:** Expired Order-Block Structural Fate Decomposition
**Diagnostic type:** `DIAGNOSTIC_INVESTIGATION`
**Classification (future evidence):** `DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE`
**Research identity:** `phase6-development-v2`
**Charter:** `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
**Primary linked hypothesis:** `phase8-v2-H006` (registered in this preregistration commit)
**Contextual prior:** `phase8-v2-H002 = SUPPORTED_BY_D003` (contextual prior only; D004 must NOT reopen H002)
**Registration:** `baseline/phase8_v2_hypothesis_register.json` (this preregistration commit)

## 1. Scientific question

D003 R001 (`SUPPORTED_BY_D003`, canonical lifecycle ELIGIBLE 87 / EXPIRED 133 / MITIGATED 28 / INVALIDATED 3 / UNAVAILABLE 275 among Gate-11 entrants) motivates but does not establish anything about the internal structure of the dominant later lifecycle state. D003's observed EXPIRED count is motivation only; no observed count may be hard-coded into D004 tooling or synthetic tests.

The frozen canonical lifecycle (`bot/strategy/order_blocks.py::evaluate_order_block`) returns `BlockState.EXPIRED` immediately when the count of causally available post-confirmation bars exceeds `order_block_expiry_bars`, BEFORE its mitigation and invalidation loop. A fixed-age cutoff may therefore collapse several distinct structural fates (untouched, touched, invalidated, first-retest-on-final-candle) into a single `EXPIRED` label.

The registered scientific question (H006 context):

> Among decisions whose frozen canonical evaluation is `BlockState.EXPIRED` with a confirmed same-side block, what structural fate do those blocks actually exhibit at the causal decision timestamp — untouched, touched, invalidated, or first-retested exactly at the decision candle — and with what final canonical FVG context?

D004 is decomposition of observed structure. It is NOT an alternate lifecycle classification, NOT a parameter study, and NOT a V002 justification by itself.

## 2. Empirical universe (future execution only — DO NOT execute in the preregistration or tooling task)

* `TIER_A_FOLD01` only, and only against the preserved V001 store `fold-01-a8b406884ab3525a`
  (store identity SHA-256 `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4`;
  rows-content SHA-256 `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22`;
  13,269 decision snapshots; fold-01/full).
* The historical store `fold-01-1d710826193a6767` is prohibited as input.
* No store may be opened in the preregistration or tooling-freeze tasks. No diagnostic budget is consumed by registration or tooling; execution, if separately authorized, consumes `3 / 12` diagnostics upon first empirical execution.
* No Fold 02–04, no 2025+ data, no holdout. Reserved evidence remains untouched.

## 3. Primary population (structural definition — no observed count may be encoded)

Decisions that, at future execution time and derived naturally from the preserved store:

1. legitimately reach the same canonical OB lifecycle population used by D003 (D001 `classify_snapshot`, reference check, successful orchestration evaluation, Gate-10 pass, Gate-11 entry — the D003 observer loop reused verbatim);
2. have a confirmed same-side canonical block (the frozen `evaluate_order_block` returns a non-null block identity); and
3. are classified by that frozen canonical evaluation as `BlockState.EXPIRED` (reason `block_expired`).

The population is derived at execution time. The D003 result is never a test oracle.

## 4. Reference populations (structural context only)

D004 may report the same descriptive fate predicates for decisions classified `ELIGIBLE`, `RETEST_ELIGIBLE`, `MITIGATED`, or `INVALIDATED`. `UNAVAILABLE` may be counted but has no block geometry. States are never merged; every reference surface is labeled by its canonical `BlockState`.

## 5. Frozen configuration

`order_block_expiry_bars = 30` in the exact frozen `StrategyConfig`. D004 does not change it, does not test another value, and does not compute any result at 31, 40, 45, 60, 90, no-expiry, session-expiry, day-expiry, or dynamic-ATR-expiry. No grid, no numeric parameter trial.

## 6. Read-only expired-block decomposition predicates

For each population block, using its already-detected canonical block identity and only the causal candles available at `decision_at` (candles with `available_at <= decision_at`; the exact `evaluate_order_block` causality filter):

* `block_confirmed_at` — the canonical block's confirmation timestamp;
* `block_candidate_open_time` — the canonical block's candidate-candle open timestamp;
* `decision_at` — the decision timestamp;
* `post_confirmation_bars` — exact count of causally available post-confirmation candles;
* `bars_beyond_expiry_boundary` — `post_confirmation_bars - order_block_expiry_bars` for EXPIRED blocks (strictly positive by construction);
* `zone_overlap_before_decision` — whether any post-confirmation candle overlaps the block zone (`candle.low <= zone_high and candle.high >= zone_low`, the frozen evaluator's own overlap expression);
* `first_zone_overlap_index` — ordinal (0-based, among causally available post-confirmation candles) of the first zone overlap when present, else null;
* `invalidating_close` — whether an invalidating close occurs causally before the decision (close below a LONG block's `zone_low` / above a SHORT block's `zone_high`);
* `first_invalidating_close_index` — ordinal of the first invalidating close when present, else null;
* `untouched_through_decision` — no zone overlap and no invalidating close through decision time;
* `first_retest_on_final_candle` — the first causal zone overlap occurs on the final available candle;
* `block_side` — canonical `StrategySide` of the block;
* `block_zone` — canonical `(zone_low, zone_high)` of the block.

These are independent descriptive predicates measured over the frozen structure; no predicate is reinterpreted as eligibility and no state is reassigned.

## 7. Preregistered fate categories (descriptive; raw predicate counts are authoritative)

* `EXPIRED_UNTOUCHED` — no zone overlap and no invalidating close through decision time.
* `EXPIRED_TOUCHED` — at least one block-zone overlap occurred before decision time.
* `EXPIRED_INVALIDATED` — an invalidating close occurred before decision time.
* `EXPIRED_FIRST_RETEST_AT_DECISION` — the first causal zone overlap occurs on the final available candle at the decision.

Categories may overlap where mathematically unavoidable, except where definitions make them exclusive (`EXPIRED_UNTOUCHED` is exclusive of `EXPIRED_TOUCHED` and `EXPIRED_INVALIDATED` by construction). Raw predicate counts are authoritative rather than a forced single exclusive bucket, so overlap never discards information. No category may be called "eligible"; no eligibility semantics attach to any category.

## 8. Age surface

The exact observed age in post-confirmation bars is reported for every population block. Permitted summaries only: count, minimum, maximum, median, the exact integer-frequency histogram of post-confirmation bar counts, and preregistered deterministic quantiles (p25/p50/p75, linear interpolation on the sorted integer sample). The histogram describes age only. Prohibited: any evaluation at an alternative expiry threshold, and any statement of the form "would pass at expiry = X".

## 9. Final FVG context (no FVG redetection)

For each expired block, using the already-persisted final canonical FVG surface exactly as D003 extracts it (the frozen flattened D001 row `fvg` surface, plus the persisted raw first-FVG geometry recovered through the D003 render reconciliation) — and the SAME frozen geometry observer (`backtests.phase8_v2_diagnostic_d001.mirror_fvg_in_ob` with the persisted ATR and the expired block's canonical zone):

* final FVG present yes/no;
* direction agreement between the final FVG and the block side (semantic LONG/SHORT comparison, `not_available` when either side is absent/FLAT);
* raw canonical FVG count (the persisted row FVG count);
* canonical geometric overlap true/false via the frozen mirror geometry (`gap <= 0.30 * ATR` semantics, unchanged);
* the exact descriptive separation geometry the mirror returns (intersection, containment, signed/absolute separation, widths).

No FVG redetection, no alternate overlap tolerance, no tolerance sensitivity report.

## 10. Expired fate x FVG contingency (descriptive)

Preregistered contingency over the expired population: expired structural predicate (untouched / touched / invalidated / first-retest-at-decision, predicate-level not exclusive-bucket) x final FVG present true/false x direction agreement (agree/disagree/not_available) x canonical overlap true/false. Permitted summaries are observed-cell counts such as "untouched expired block + FVG present" or "touched expired block + FVG present + overlap true". No candidate counts of any kind.

## 11. Consumption invariant (asserted; fail closed)

`consumed_ids` derive causally from the prior setup-state record exactly as in D003 (`consumed_ids_from_record`). D004 reports whether the canonical block ID is already consumed; however, because `evaluate_order_block` checks consumed IDs before its expiry short-circuit, a block actually returned as `EXPIRED` cannot have been in the causal consumed set under frozen semantics. D004 asserts this invariant for every EXPIRED observation: if a returned-EXPIRED block ID appears in the derived consumed ids, execution fails closed (`D004Error`). The assertion is recorded as `consumed_invariant_holds: true` on each observation.

## 12. Causality

Only candles with `available_at <= decision_at` may be inspected — the exact causality filter frozen inside `evaluate_order_block`. No later candle, no future mitigation, no "what happened next". D004 answers structural state AT THE DECISION only. The decision timestamp is the snapshot's causal `available_at_ms`, and the setup-state chain follows the D003/TC001 discipline exactly: the observer receives the causal PRIOR state record; the current decision's `next_record` is used read-only for render reconciliation only and never drives lifecycle or consumed-id semantics.

## 13. No reimplementation of detection (block-identity reconciliation; fail closed)

D004 reuses `detect_order_blocks(...)`, `StrategyConfig`, `StrategySide`, and the same canonical block-selection ordering used by `evaluate_order_block(...)`. It creates no parallel OB detector. For every observed decision, the block identity D004 analyzes (same selection ordering over the same causal frame) must match the block returned by frozen canonical evaluation — `block_id`, side, zone, and `confirmed_at` all agree. Any reconciliation failure is a stop condition (`D004Error`, fail closed).

## 14. D003-semantics reconciliation

For every observed decision, the canonical state from frozen `evaluate_order_block`, side, block ID, zone, and reason must agree with the corresponding D004 selected block/context. D004 measures the same canonical objects D003 measured; a disagreement (including any reason/state pair the frozen evaluator cannot produce) fails closed.

## 15. H006 preregistered decision rule (fixed BEFORE any empirical access)

* `SUPPORTED_BY_D004` — when a meaningful proportion of frozen EXPIRED blocks remain structurally untouched and uninvalidated through decision time, demonstrating that fixed age frequently preempts other structural lifecycle evidence. Support is strengthened if those blocks also retain same-direction final FVG structure, but FVG coexistence is NOT required for the basic disposition. "Meaningful proportion" is argued from concentration and structural interpretation, never from an invented after-the-fact percentage cutoff.
* `NOT_SUPPORTED_BY_D004` — when frozen EXPIRED blocks are predominantly already touched, mitigated-like, invalidated, directionally inconsistent, or otherwise structurally stale by decision time.
* `INCONCLUSIVE_D004` — if counts are too sparse, or causal decomposition cannot distinguish the structural fate safely.

No strategy change follows automatically from any disposition. A high EXPIRED count alone does NOT support H006 (H006 failure condition, register §4).

## 16. Boundaries — hypotheses that D004 does NOT touch

* H002 remains `SUPPORTED_BY_D003`; D004 must not reopen, re-test, or re-classify it.
* H001 remains `INCONCLUSIVE_D001`; FVG geometry appears here as context only, never as an H001 test.
* H003 remains `NOT_TESTED_BY_D003`; absolutely no OB→FVG lag, FVG→OB lag, temporal windows, or preceding/following-bar association is computed. The temporal_fvg_lag concept is banned output.
* H005 remains `SUPPORTED_BY_V001`; not reopened.

## 17. Prohibited counterfactuals and banned outputs

D004 does NOT test "would removing expiry create >= 90 candidates" and does NOT compute alternate candidate_ready, alternate Gate-11 passes, alternate canonical eligibility, or alternate closed-trade feasibility; those are strategy-variant outcomes and remain prohibited. No V002 is created by D004.

The tooling fails closed if the emitted document contains, as keys or semantic concepts: `candidate_if_expiry_removed`, `eligible_without_expiry`, `alternate_expiry`, `expiry_31`, `expiry_40`, `expiry_45`, `expiry_60`, `expiry_90`, `counterfactual_candidate`, `pnl`, `profit`, `profit_factor`, `win_rate`, `expectancy`, `drawdown`, `sharpe`, `returns`, `fills`, `closed_trades`, `temporal_fvg_lag`, or any temporal-lag key — enforced by exact-key bans plus robust semantic substring families, with honest negation keys (e.g. `no_profitability_metrics`, `no_alternate_expiry_evaluated`) still passing. No profitability, fills, closed trades or account quantities of any kind.

## 18. Tooling reuse and two-phase discipline

Tooling reuses existing validated infrastructure wherever possible: D001 snapshot classification, reference check and accounting; the D001 orchestration adapter; the D003 canonical lifecycle observer patterns (`canonical_ob_lifecycle`, `consumed_ids_from_record`, render reconciliation, `_semantic_direction`), the canonical setup-state seed/carry, TC001-style prior-state handling, canonical Git-blob provenance (`canonical_git_blob_v1` via `bot.scientific.canonical_bytes`), and the canonical order-block detector/evaluator. No frozen semantics are duplicated or altered. Tooling is deterministic and fails closed on any accounting, reconciliation, provenance or structural violation.

* Phase A (this document + register records H006/D004) precedes any tooling freeze.
* Phase B (synthetic-tested tooling + focused tests) is committed and pushed before any Fold-01 access.
* Empirical execution only under separate supervisory authorization after the remote resolves to the frozen tooling commit; that future execution consumes `3 / 12` diagnostics upon first store read.

## 19. Budget

Registration and tooling freeze consume zero diagnostic budget. Budget at this preregistration: diagnostics `2 / 12` executed; strategy variants `1 / 8` observed; numeric parameter trials `0 / 4`; `UPWARD STRATEGY-VARIANT / PARAMETER-TRIAL BUDGET REVISION PROHIBITED = ACTIVE`. A future separately authorized D004 empirical execution consumes `3 / 12` diagnostics upon first empirical store access. No strategy variant and no numeric trial is consumed by D004.

## 20. Required synthetic test coverage (Phase B, synthetic data only)

At least: expired + untouched through decision; expired + zone touched before decision; expired + invalidating close; expired + first retest on the final decision candle; expired + final same-direction overlapping FVG; expired + final FVG non-overlapping; LONG block; SHORT block; causal exclusion of post-decision candles; the consumed-ID invariant (including its fail-closed violation path); block-identity reconciliation (including a tampered mismatch failing closed); malformed/data-unsafe inputs failing closed. Age tests: exact post-confirmation age; the frozen expiry threshold remains 30 in reported provenance; age reporting does not alter canonical state; and no alternate-expiry output key exists (banned-guard proof).
