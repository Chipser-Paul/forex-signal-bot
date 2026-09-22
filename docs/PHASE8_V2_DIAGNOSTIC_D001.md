# PHASE 8 V2 — DIAGNOSTIC D001 SPECIFICATION (PREREGISTERED)

**Diagnostic ID:** `phase8-v2-D001`
**Title:** Frozen OB/FVG Structural Attrition Decomposition
**Status:** `REGISTERED_NOT_EXECUTED`
**Budget classification:** `DIAGNOSTIC_INVESTIGATION`
**Budget consumption upon first empirical execution:** `1 / 12` (registration consumes nothing)
**Linked hypotheses:** `phase8-v2-H001`, `phase8-v2-H002` (registered in
`baseline/phase8_v2_hypothesis_register.json`)
**Referenced later direction (not tested by D001):** `phase8-v2-H003`
**Charter:** `phase8-v2-research-charter-v1-8527e3a5eec98f53`
(charter SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
**Research identity:** `phase6-development-v2`
**Preregistration commit basis:** `a54d3fc6a5c802114278fcf67f6564af47a35b43`
**Canonical fingerprint contract:** `canonical_git_blob_v1`

This document is a preregistration. It fixes the scientific question, the
diagnostic population and the exact metric surface **before** any execution.
It does not execute D001 and creates no diagnostic tooling in this task
(specification first, implementation next).

---

## 1. Scientific question

> Within Fold 01 and under unchanged V1 structural semantics, where exactly
> does OB/FVG structural eligibility disappear before candidate creation?

D001 is an **attrition/explanation diagnostic**. It is **not**:

* a strategy variant;
* a threshold trial;
* a candidate-generation counterfactual;
* a profitability evaluation.

All output must be labelled:

`DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE`

## 2. Input boundary (execution-time)

D001 execution may inspect **only** Fold 01:
`[2024-04-01T00:00:00Z, 2024-06-08T00:00:00Z)`, plus the causal
warm-up/history that existing Fold-01 semantics already require (shared
market facts from the frozen plan; not fold-specific strategy evidence).

* It must use the existing causal/frozen strategy-semantic path (the frozen
  gate reducer and strategy modules) wherever possible.
* It must **not** inspect Fold 02, Fold 03 or Fold 04 in any form.
* It must **not** access 2025+ market data or holdout.
* No new observation may influence any preregistered text; results are
  reported against the questions fixed here.

## 3. Required structural outputs (exactly these, preregistered)

### A. Decision accounting

* scheduled decisions;
* canonical top-level action/state counts (`skip` / `wait` /
  `news-blocked` / `candidate_ready` per the canonical reducer's
  `action`/`reason`/`setup_status` semantics);
* missing-history count;
* unavailable-input count;
* evaluation-error count.

Accounting must reconcile exactly (every scheduled decision appears in
exactly one top-level class). Inability to reconcile is a stop condition
(§9).

### B. Gate reach funnel

For every frozen structural gate, in exact evaluation order, using the
canonical gate names from the frozen reducer
(`bot/state/gate_reducer.py`, `REDUCER_VERSION = phase8n.setup-gates.v1`):

1. `gate_8_liquidity` (fetched frame sufficiency, structure update,
   liquidity sweep);
2. `gate_9_displacement` (M5 displacement validity; `displacement_tier`
   recorded where the optional tier rule applies);
3. `gate_10_internal_structure` (M15 confirmation / internal BOS-CHOCH;
   `structural_shift_variant` recorded where evaluated);
4. `gate_11_confluence_score` (setup-only score incl. OB/FVG overlap
   geometry);
5. `canonical_strategy` (frozen Phase 6 reducer:
   symbol/side/source/regime/bias/DXY/news/session/`ORDER_BLOCK_*`/
   confluence reasons, canonical `StrategyReason` values);
6. `gate_12_13_rr_entry` (unchanged entry model).

For each gate: decisions entering, passing, failing, pass rate, failure
rate. Gate names are canonical implementation identifiers — they must not
be renamed. Gates are recorded as evaluated, including early exits
(e.g. `wait`/`insufficient_market_data` before gate 8 passes), so the
funnel reconciles with §3.A.

### C. OB state decomposition

Population: decisions reaching the structural stage where the canonical
`ob_result` is observable (gate-11 population).

* OB detected/present (`ob_result` non-empty);
* OB direction (`side`);
* `valid_order_block` true/false (`ob.get("valid")`);
* each canonical `BlockState` outcome from
  `bot/strategy/order_blocks.py::evaluate_order_block`:
  `DATA_UNSAFE`, `UNAVAILABLE`, `PREMATURE`, `CONSUMED`, `EXPIRED`,
  `INVALIDATED`, `RETEST_ELIGIBLE`, `MITIGATED`, `ELIGIBLE`;
* each canonical failure reason where observable:
  `invalid_decision_time`, `malformed_or_naive_candle_frame`,
  `no_confirmed_block`, `confirmation_not_available`,
  `block_already_consumed`, `block_expired`,
  `close_below_bullish_zone`, `close_above_bearish_zone`,
  `first_post_confirmation_retest`, `block_already_mitigated`,
  `confirmed_unmitigated_block`;
* failure-reason counts and failure-reason co-occurrence counts.

If the existing implementation does not expose a needed subpredicate
directly, D001 tooling may build a **read-only explanatory mirror** only,
and only if equivalence to the production predicate is proven by tests. The
production predicate is never altered. A mirror/production disagreement is
a stop condition (§9).

### D. FVG state decomposition

Same eligible diagnostic population:

* FVG detected/present (`displacement.fvg`; the canonical `fvgs` list);
* FVG direction (from the displacement/FVG record where defined);
* canonical FVG validity state (`displacement.get("valid")`,
  `gate_9_displacement`);
* existing subpredicate/failure reasons where observable:
  `displacement_missing`, `internal_structure_missing`,
  `structural_shift_variant` failures (including
  `freshness_window_failed_*`).

Again: explanatory tooling mirrors production semantics; it never alters
them.

### E. OB × FVG contingency table

Raw counts over the eligible population, at least:

| | FVG present/valid = false | FVG present/valid = true |
|---|---|---|
| **valid OB = false** | count | count |
| **valid OB = true** | count | count |

cross-tabulated with the exact canonical overlap outcome
(`fvg_in_ob` = false / true as computed by the frozen gate-11 geometry).
Raw counts only. **No alternative candidate decisions may be derived from
any combination.**

### F. Canonical overlap geometry

For observations where both relevant regions exist (canonical OB zone and
first FVG), report the **existing canonical geometric relationship only**,
as implemented at `gate_11_confluence_score`:

* intersection exists yes/no;
* interval containment relationship if mechanically definable without a
  new trading rule;
* signed price-region separation (the canonical gap quantity:
  `fvg_low − ob_high` when the FVG lies above the zone, `ob_low − fvg_high`
  when below, `0.0` when intersecting);
* absolute separation;
* region widths (FVG height, OB zone height).

Permitted descriptive statistics for these preregistered quantities only:
count, minimum, maximum, median, quartiles (§4).

**No alternative overlap threshold may be applied. No statement of the
form "would pass if distance ≤ X" is permitted. No candidate-count-versus-
distance curve may be constructed.**

### G. Direction consistency

Where meaningful:

* same-direction OB/FVG count (OB side vs canonical expected direction);
* opposite-direction count;
* unavailable/undefined count.

Directional acceptance is not changed.

## 4. Optional descriptive statistics

For the already-preregistered structural quantities of §3.F only: count,
minimum, maximum, median, quartiles. **Prohibited:** threshold
optimization; searching for the value that would produce approximately 90
candidates; constructing candidate-count-versus-distance curves. Those
cross from diagnosis into strategy-variant/parameter research and would
consume the wrong budget class.

## 5. Explicitly prohibited outputs

D001 must not calculate:

* hypothetical candidates under partial overlap;
* hypothetical candidates under proximity thresholds;
* hypothetical candidates under sequential OB/FVG logic;
* hypothetical candidates under 7/8 confluence;
* alternative strategy candidate counts;
* fills;
* closed trades;
* P&L;
* win rate;
* profit factor;
* expectancy;
* drawdown;
* Sharpe;
* return distributions.

D001 describes V1 structural semantics only. It does not alter them.
Registering a 7/8-threshold hypothesis or computing any 7/8 counterfactual
remains prohibited (charter §8; the four known historical 7/8 observations
are not a research justification).

## 6. Tooling design (to be implemented in a later authorized task)

The future diagnostic implementation must:

* be read-only;
* reuse canonical source semantics and avoid duplicating strategy logic
  where possible;
* fail closed on semantic mismatch;
* label all output
  `DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE`;
* emit deterministic structured output **outside Git** (external Phase 8
  data root);
* include provenance: canonical commit; charter identity/hash; diagnostic
  ID; linked hypothesis IDs; Fold 01 boundary; relevant code fingerprints
  (under `canonical_git_blob_v1`); input identities; output SHA-256.

No tooling is implemented by this preregistration task.

## 7. Budget accounting

* `REGISTERED` (this document) ≠ `EXECUTED`.
* Registration consumes no diagnostic budget.
* The **first empirical execution** of D001 consumes `1 / 12` of the
  diagnostic budget and the register's budget accounting must be updated
  by an append-only result record at that point.
* Re-running D001 solely to reproduce the exact same preregistered
  computation after a technical failure does **not** automatically become
  another scientific diagnostic, provided: no rule changes; no metric
  additions; no output-dependent modifications; and the reason for the
  rerun is recorded.
* Changing the diagnostic question, metrics or population after viewing
  results requires a **new diagnostic ID** and consumes additional budget.

## 8. Execution stop conditions (fail closed)

D001 execution must stop and report — never optimize around — if any of:

* canonical code identity mismatch;
* charter/hash mismatch;
* Fold boundary mismatch;
* any Fold 02–04 access;
* any holdout/2025+ access;
* inability to reconcile decision accounting (§3.A);
* explanatory mirror differs from the production predicate;
* unexpected strategy-source change;
* output contains performance metrics;
* empirical source provenance cannot be verified.

## 9. Relationship to the hypothesis register

D001 tests H001 and H002 qualitatively through the preregistered metric
surface above; results will be appended to
`baseline/phase8_v2_hypothesis_register.json` as separate linked
`result_records` (the hypothesis texts themselves are immutable). H003 is
explicitly **not** fully tested by D001: D001's metric surface contains no
OB-to-FVG temporal-distance distribution; that belongs to a later
diagnostic to be preregistered separately.

---

*End of D001 preregistration. Status remains `REGISTERED_NOT_EXECUTED`
until an authorized execution task runs it exactly as specified here.*

---

## 10. Provenance correction (phase8-v2-PC001)

* D001 was published in commit `8985fb2f8396a999dbddcc8b51342788823dc2c2`.
* Authoritative preregistration publication time: `2026-09-22T22:20:51Z`
  (Git commit author/committer timestamp, verified against the GitHub
  authoritative publication timestamp).
* The register's original `2026-09-21T00:00:00Z` timestamps (including
  this diagnostic's `registered_utc`) were erroneous placeholder
  metadata.
* Correction `phase8-v2-PC001` (see
  `baseline/phase8_v2_hypothesis_register.json`,
  `provenance_corrections`) supersedes that timestamp for chronology
  only.
* No empirical execution occurred before the correction; D001 remains
  `REGISTERED_NOT_EXECUTED`; its preregistered scientific question,
  metric surface, hypotheses, population and prohibited outputs are
  unchanged.
