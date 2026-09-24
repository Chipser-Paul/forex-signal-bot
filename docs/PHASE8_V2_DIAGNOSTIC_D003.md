# PHASE 8 V2 — DIAGNOSTIC D003 SPECIFICATION (PREREGISTERED)

**Diagnostic:** `phase8-v2-D003`
**Title:** Canonical Gate-11 and Order-Block Lifecycle Decomposition
**Diagnostic type:** `DIAGNOSTIC_INVESTIGATION`
**Classification (future evidence):** `DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE`
**Research identity:** `phase6-development-v2`
**Charter:** `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
**Primary linked hypothesis:** `phase8-v2-H002` (registered statement remains unchanged; not rewritten after V001)
**Secondary contextual hypothesis:** `phase8-v2-H001` (contextual OB/FVG overlap context only)
**Registration:** `baseline/phase8_v2_hypothesis_register.json` (this preregistration commit)

## 1. Scientific question

V001 R001 (`FUNCTIONAL_REPAIR_NO_CANDIDATES`, H005 `SUPPORTED_BY_V001`) motivates but does not establish:

* which canonical order-block lifecycle state dominates the surviving Gate-11 population;
* that the frozen `8/8` threshold should change;
* that valid-OB, premium/discount or FVG-overlap semantics should be relaxed.

D003 exists to measure before anything is changed. The registered scientific question:

> Among decisions that legitimately reach Gate 11, what is the exact frozen-score component composition, and how does the canonical order-block lifecycle (`evaluate_order_block`) classify the same decisions compared with the persisted legacy/acquisition `ob_result.valid` surface?

## 2. Empirical universe (future execution only — DO NOT execute in the preregistration or tooling task)

* `TIER_A_FOLD01` only, and only against the preserved V001 store `fold-01-a8b406884ab3525a`
  (store identity SHA-256 `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4`;
  rows-content SHA-256 `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22`;
  13,269 decision snapshots; fold-01/full).
* The historical store `fold-01-1d710826193a6767` is prohibited as input.
* No store may be opened in the preregistration or tooling-freeze tasks. No diagnostic budget is consumed by registration or tooling; execution, if separately authorized, consumes `2 / 12`.

## 3. Primary population (structural definition — no observed count may be encoded)

Decisions that, at future execution time and derived naturally from the preserved store:

1. pass canonical snapshot classification (D001 `classify_snapshot`);
2. pass the reference check (`_reference_check_failed` false);
3. evaluate successfully through the canonical orchestration path (action != `error`);
4. pass Gate 10 (`gate_10_internal_structure`);
5. enter Gate 11 (Gate-11 scored; entrant regardless of Gate-11 outcome).

This is the scientifically relevant Gate-11 conjunction population. The previously observed V001 values are motivation only and must not appear as expected outputs in tooling or tests.

## 4. Frozen Gate-11 score contract (source fact — never a change proposal)

`bot/execution/confluence_scorer.py::score_setup` awards:
HTF bias alignment 2, premium/discount placement 1, valid OB 2, FVG-overlaps-OB 1, liquidity sweep 2; maximum 8; frozen default threshold 8.

For decisions that legitimately reach Gate 11, HTF bias/trade-direction alignment and the liquidity sweep are already established by construction (Gate 8 passed). Gate 11's remaining discriminating conjunction is structurally `premium_or_discount AND valid_ob AND fvg_in_ob`. D003 records this source fact; it does not alter any threshold.

## 5. Acquisition OB versus canonical OB — two distinct surfaces

* Persisted gate input `ob_result` is populated by the legacy/acquisition `detect_ob_breaker(...)` path (`bot/state/gate_inputs.py`).
* H002 concerns the canonical lifecycle model `bot/strategy/order_blocks.py::evaluate_order_block(...)`.
* D003 measures both separately and never treats `ob_result.valid` as equivalent to canonical `OrderBlockResult.eligible`. Neither surface is replaced or modified.

## 6. Canonical OB lifecycle contract

* `evaluate_order_block(frame, side, decision_at, config, consumed_ids=...)` with the exact frozen `StrategyConfig` and canonical `StrategySide`.
* `BlockState` outcomes: `ELIGIBLE`, `RETEST_ELIGIBLE`, `MITIGATED`, `INVALIDATED`, `EXPIRED`, `CONSUMED`, `PREMATURE`, `UNAVAILABLE`, `DATA_UNSAFE`.
* Canonical lifecycle eligibility is ONLY `ELIGIBLE` or `RETEST_ELIGIBLE`. Not redefined.
* Canonical inputs are reconstructed ONLY from already-persisted causal V001 snapshot data: persisted M5 `entry_rows`, persisted `htf_bias`, the decision timestamp, the exact frozen `StrategyConfig`, and causal prior setup-state consumption information where required. No external candles, no later bars, no rebuilt market inputs, no information unavailable at the decision timestamp.
* `consumed_ids` are derived only from the canonical prior setup-state record at that decision, matching the frozen reducer's causal consumption semantics (`previous["consumption"]["bindings"]` intersected with `previous["consumption"]["events"]`). The empty set is never assumed; synthetic tests must cover at least one non-empty consumed-id example.
* The canonical lifecycle observer is READ-ONLY relative to strategy evaluation: it must not alter reducer state, the setup-state chain, or any persisted row.

## 7. Exact preregistered metric surface

### A. Accounting (must reconcile; D001 `reconcile_accounting` reused)

Scheduled snapshots; pre-evaluation bucket counts (missing_history / unavailable_input / evaluation_error); successful structural decisions; Gate-8 entered/pass/fail; Gate-9 entered/pass/fail; Gate-10 entered/pass/fail; Gate-11 entered/pass/fail.

### B. Frozen score components (exactly as scored)

For every Gate-11 entrant, the five frozen checks (`HTF bias aligns with trade direction`, `Price located in premium/discount zone`, `Valid order block present`, `FVG overlaps the order block zone`, `Liquidity sweep occurred before entry`): pass count, fail count, awarded points, exact frozen score distribution, and exact five-boolean co-occurrence frequencies. No score is recalculated under any changed rule.

### C. Discriminating-component contingency (descriptive only)

Over Gate-11 entrants: premium/discount true/false x persisted legacy/acquisition `ob_result.valid` true/false x persisted FVG-in-OB overlap true/false — all observed boolean combinations reported. Explicitly NOT computed: "candidate count if one condition removed", alternate scores, alternate thresholds.

### D. Canonical OB lifecycle

For the same causal decisions: complete `BlockState` distribution; complete canonical reason distribution; side/direction distribution; eligible count (`ELIGIBLE + RETEST_ELIGIBLE`); non-eligible count; state x reason table where nonredundant; state x direction table. No alternative configuration.

### E. Acquisition/canonical agreement

Per Gate-11 entrant contingency of persisted `ob_result.valid` versus canonical `OrderBlockResult.eligible` — four cells (false/false, false/true, true/false, true/true) — plus direction agreement where both surfaces expose a meaningful side. Diagnostic agreement evidence only; neither surface replaces the other.

### F. Canonical failure reasons

Counts for canonical reasons where observed, never grouped away: `no_confirmed_block`, `confirmation_not_available`, `block_already_consumed`, `block_expired`, `close_below_bullish_zone`, `close_above_bearish_zone`, `first_post_confirmation_retest`, `block_already_mitigated`, `confirmed_unmitigated_block`, and data-unsafe reasons (`invalid_decision_time`, `malformed_or_naive_candle_frame`).

### G. Contextual FVG coexistence (H001-context only)

Canonical-OB-lifecycle-eligible true/false x final canonical FVG present true/false. Where BOTH exist: pair count, direction agreement, canonical geometric overlap true/false, and preregistered separation geometry only (the D001 mirror geometry: `fvg_low - ob_high` / `ob_low - fvg_high` / else `0.0`, pass when `gap <= 0.30 * ATR`). No counterfactual score is created using canonical OB eligibility.

### H. Premium/discount context

Premium/discount pass/fail among Gate-11 entrants (it carries one frozen point), plus the descriptive contingency premium/discount x canonical-lifecycle-eligible OB x final FVG present. Diagnostic decomposition only; no new rule is proposed in D003.

## 8. H002 preregistered decision rule (fixed BEFORE execution)

* `SUPPORTED_BY_D003` — only if canonical lifecycle results show that OB-like blocks exist with substantial concentration in one or more specific lifecycle failure states/reasons, while canonical eligible OB availability is much rarer because of the current lifecycle conjunction. "Substantial" is NOT defined by an arbitrary post-hoc percentage; it is argued from structural evidence and concentration description. No parameter change follows automatically.
* `NOT_SUPPORTED_BY_D003` — if canonical evaluation is dominated by `UNAVAILABLE / no_confirmed_block` with little evidence of otherwise meaningful detected OB structure entering later lifecycle states.
* `INCONCLUSIVE_D003` — if data/tooling cannot distinguish the lifecycle, counts are too sparse for a meaningful structural interpretation, or acquisition/canonical semantic mismatch prevents a defensible lifecycle inference.

No strategy change automatically follows any disposition.

## 9. H001 boundary

D003 may reproduce contextual OB/FVG pair and overlap counts (section 7.G). H001 remains `INCONCLUSIVE_D001` unless a separately preregistered H001 decision rule exists before D003 execution. Default: unchanged.

## 10. H003 boundary

Absolutely no OB→FVG lag, FVG→OB lag, temporal windows, or preceding/following bar associations. `H003 = NOT_TESTED_BY_D003`; it requires its own later diagnostic.

## 11. Prohibited counterfactuals and banned outputs

No `7/8` or `6/8` scoring; no candidates-if-condition-removed; no alternate OB expiry bars or displacement ATR; no alternate premium/discount semantics, overlap tolerances, partial overlap or proximity rules; no temporal association; no optimizer or search. The tooling fails closed if output contains `pnl`, `profit`, `profit_factor`, `win_rate`, `expectancy`, `drawdown`, `sharpe`, `returns`, `fills`, `closed_trades`, alternate-threshold keys, counterfactual candidate counts, score-at-X keys or temporal-lag keys. No profitability, fills, closed trades or account quantities of any kind.

## 12. No V002

D003 must not create `phase6-development-v2-V002`. No strategy implementation change is yet justified; D003 must complete first.

## 13. Two-phase execution discipline and stop conditions

* Phase A (this document + register record) precedes any tooling freeze; Phase B (synthetic-tested tooling) is committed and pushed before any Fold-01 access; empirical execution only under a separate supervisory authorization after the remote resolves to the frozen tooling commit.
* Tooling reuses D001's classification, reference check, accounting, orchestration adapter and canonical setup-state carry verbatim; it must not duplicate frozen semantics, must be deterministic, and must fail closed.
* The sequential setup-state chain is preserved exactly (canonical preclassification -> reference check -> canonical orchestration -> prior-state preservation on error -> state advance on success).
* Any reconciliation, accounting or provenance mismatch is a stop condition. Folds 02–04, holdout and 2025+ data remain untouched; holdout is never read.

## 14. Budget

Registration and tooling freeze consume zero diagnostic budget. Budget before any D003 execution: diagnostics `1 / 12` executed; strategy variants `1 / 8` observed; numeric parameter trials `0 / 4`; `UPWARD STRATEGY-VARIANT / PARAMETER-TRIAL BUDGET REVISION PROHIBITED = ACTIVE`. A future authorized D003 execution consumes `2 / 12` diagnostics upon first empirical execution.
