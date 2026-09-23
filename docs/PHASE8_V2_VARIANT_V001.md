# PHASE 8 V2 — STRATEGY VARIANT V001 PREREGISTRATION (REGISTERED_NOT_IMPLEMENTED)

**Variant ID:** `phase6-development-v2-V001`
**Title:** Canonical FVG ATR-Series Compatibility Repair
**Status:** `REGISTERED_NOT_IMPLEMENTED`
**Budget classification:** `STRATEGY_VARIANT` (registration consumes nothing)
**Budget consumption upon first empirical result:** `1 / 8 strategy variants observed`,
which triggers the charter rule `UPWARD STRATEGY-VARIANT / PARAMETER-TRIAL BUDGET
REVISION PROHIBITED` from that point onward.
**Numeric parameter trial budget:** unchanged at `0 / 4` (V001 changes no numeric
parameter).
**Linked hypotheses:** `phase8-v2-H005` (primary), `phase8-v2-H004` (static
disposition `SUPPORTED_BY_STATIC_IMPLEMENTATION_AUDIT`), `phase8-v2-S001`
(`STATIC_IMPLEMENTATION_AUDIT`).
**Charter:** `phase8-v2-research-charter-v1-8527e3a5eec98f53`
(charter SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
**Research identity:** `phase6-development-v2`
**Preregistration commit basis:** `3d2cfd2496663118a4ffcacad4c7c1fe7b5bf814`
**Canonical fingerprint contract:** `canonical_git_blob_v1`

This document is a preregistration. It fixes the variant boundary, the
implementation barrier, and the exact empirical metric surface **before** any
implementation or execution. It does not implement V001 and creates no
strategy code in this task. V001 execution is not authorized by this document;
it requires a separate authorization task using the D001 two-phase discipline
(Phase A implementation/test freeze committed and pushed before any Fold-01
access; Phase B only after the remote resolves to the frozen implementation
commit).

---

## 1. Motivation (static source proof, not empirical inference)

`phase8-v2-S001` establishes at source level that the frozen canonical FVG
detector cannot produce an FVG for any input through its current path:

* `utils/indicators.py::calculate_atr(df, period)` returns `0.0` for
  invalid/insufficient input, otherwise `float(atr_series.iloc[-1])` — its
  public return surface is **scalar**.
* `bot/analysis/fvg_engine.py::detect_fvgs` computes
  `atr = calculate_atr(df, atr_period)` then
  `atr_series = atr if hasattr(atr, "iloc") else None`, and every detector
  iteration begins `if atr_series is None or i - 1 >= len(atr_series): continue`.
* A scalar float has no `.iloc`, so `atr_series` is always `None`; every
  candidate window is skipped and the detector returns `[]` for every frame
  long enough to enter the loop (and short frames also return `[]`).

This is a deterministic implementation/interface defect:
`STATIC_SOURCE_PROOF — NOT EMPIRICAL MARKET EVIDENCE`.

## 2. Scientific question

> Does supplying a mathematically equivalent rolling ATR series to the frozen
> FVG detector — while preserving every existing FVG threshold and downstream
> filtering semantic — restore the detector's ability to evaluate canonical
> FVG windows, without introducing any new trading threshold?

V001 is a **correctness repair**: it allows the already-declared FVG
definition to execute as written. It does **not** assert that relaxing the FVG
definition is profitable or desirable, and no numerical candidate prediction
is preregistered.

## 3. Exact change boundary

V001 may modify only what is necessary for the FVG detector to consume a valid
rolling ATR series.

* `utils.indicators.calculate_atr()` remains **unchanged** (scalar public
  behavior preserved — other callers may depend on it).
* Preferred design: use the existing canonical
  `bot.strategy.regime.atr_series(frame, period)` inside the FVG detector, or
  a proven mathematically equivalent local adapter.
* Preserved unchanged: `atr_period = 14`; `displacement_mult = 1.5`; bullish
  geometric gap definition; bearish geometric gap definition; fill-status
  semantics; same-direction filtering; source-index semantics; timeframe
  semantics.

No changes to: Gate 8; Gate 9 displacement threshold; OB semantics; confluence
score; overlap tolerance; `8/8`; session rules; news rules; DXY logic; risk;
execution; broker safeguards.

## 4. One-concept rule (no bundling)

The conceptual change is exactly: **make the existing FVG detector's intended
rolling ATR dependency executable.** Do not simultaneously reduce `1.5`, alter
the ATR period, modify fill logic, alter direction filtering, alter geometric
FVG conditions, add temporal persistence, modify overlap, change OB rules, or
change confluence. Any one of those requires a separate hypothesis/variant or
numeric trial.

## 5. ATR-series equivalence requirement

Before using the ATR-series helper in the variant, its mathematical
equivalence to the scalar helper's ATR definition must be proven by tests on
valid inputs. At minimum, for a valid frame where the rolling ATR is
available:

```
float(atr_series(frame, period).iloc[-1]) == calculate_atr(frame, period)
```

within an explicit numerical tolerance, established on **multiple valid
deterministic frames**, not a single example.

## 6. Phase A — implementation and test freeze (future task)

Before any Fold-01 empirical execution, the implementing task must:

1. implement V001 within the boundary of §3;
2. run synthetic/unit tests;
3. prove ATR-series equivalence (§5);
4. prove the frozen scalar helper remains unchanged;
5. prove detector behavior on hand-constructed bullish and bearish FVG
   fixtures;
6. prove filled zones remain filtered identically;
7. prove direction filtering remains identical;
8. prove no other strategy source changed;
9. commit and push the V001 implementation;
10. verify the remote commit.

Only afterward may Fold 01 be read.

## 7. Fold / holdout boundary

V001 research remains Fold 01 only:
`[2024-04-01T00:00:00Z, 2024-06-08T00:00:00Z)` plus the causal warm-up/history
that existing Fold-01 semantics already require. Fold 02, Fold 03, Fold 04,
2025+ data and holdout must not be inspected. Folds 02–04 remain reserved
sequential confirmation evidence.

## 8. Preregistered empirical metric surface

Allowed structural metrics on Fold 01:

* detector-eligible decisions;
* ATR-valid windows;
* displacement-body threshold passes;
* bullish geometric FVG count;
* bearish geometric FVG count;
* same-direction versus opposite-direction counts;
* filled versus unfilled counts;
* final canonical FVG decision presence/count;
* unique canonical FVG identities where deterministically defined;
* Gate-11 reach/pass/fail counts;
* OB/FVG co-existing pair count;
* canonical overlap true/false counts;
* raw `candidate_ready` count;
* existing gate/rejection reason counts.

Allowed descriptive statistics (count, min, max, median, quartiles): ATR;
candle body; body/ATR ratio; FVG width; canonical overlap separation where an
actual canonical OB/FVG pair exists.

**No performance metrics.**

## 9. Empirical prohibitions

Do not calculate: P&L; win rate; profit factor; expectancy; drawdown; Sharpe;
hypothetical alternative multipliers; candidate-count-versus-multiplier
curves; alternative ATR periods; altered overlap thresholds; `7/8` candidate
counts; H003 temporal alternatives. This first variant asks only whether the
exact existing FVG semantics function once their ATR interface is repaired.

## 10. Interpretation rule

V001 must not be selected merely because it produces more candidates.
Possible outcome classifications:

* `FUNCTIONAL_REPAIR_WITH_ADEQUATE_DENSITY`
* `FUNCTIONAL_REPAIR_WITH_INSUFFICIENT_DENSITY`
* `FUNCTIONAL_REPAIR_NO_CANDIDATES`
* `IMPLEMENTATION_REPAIR_FAILED`
* `EMPIRICAL_EXECUTION_BLOCKED`

A functioning FVG detector is not automatically a good strategy. After V001
results, supervisory review decides whether further diagnostics are needed,
whether the H002 lifecycle diagnostic should be preregistered, whether another
strategy variant is justified, and whether V001 remains a candidate for
eventual selection.

## 11. Stop conditions

Canonical identity mismatch; H005/V001 preregistration mismatch; fold boundary
mismatch; Fold 02–04 access; 2025+/holdout access; causal-history violation;
scalar `calculate_atr()` public behavior changed; any §3-preserved semantic
changed; bundled conceptual change; equivalence proof missing or failed;
detector mirror mismatch; unregistered metric; threshold search; candidate
counterfactual; performance output; raw output not deterministically hashed.

## 12. H002 boundary

`phase8-v2-H002` remains OPEN and is not touched by V001: it requires a
separately preregistered canonical `evaluate_order_block` lifecycle diagnostic
(a potential later D003). V001 does not repair or approximate it.
