# PHASE 8 V2 — DIAGNOSTIC D002 SPECIFICATION (PREREGISTERED)

**Diagnostic ID:** `phase8-v2-D002`
**Title:** Canonical FVG Attrition Decomposition
**Status:** `REGISTERED_NOT_EXECUTED`
**Budget classification:** `DIAGNOSTIC_INVESTIGATION`
**Budget consumption upon first empirical execution:** `2 / 12` (registration
consumes nothing)
**Linked hypothesis:** `phase8-v2-H004` (registered in
`baseline/phase8_v2_hypothesis_register.json`)
**Unresolved downstream motivation (NOT tested by D002):** `phase8-v2-H001`
**Charter:** `phase8-v2-research-charter-v1-8527e3a5eec98f53`
(charter SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
**Research identity:** `phase6-development-v2`
**Preregistration commit basis:** `0019ef30a1bd1a67bc23b204dfce47d22fa23d5b`
**Canonical fingerprint contract:** `canonical_git_blob_v1`

This document is a preregistration. It fixes the scientific question, the
diagnostic population, the exact attrition stages and the exact metric surface
**before** any execution. It does not execute D002 and creates no diagnostic
tooling in this task. D002 execution is not authorized by this document; it
requires a separate supervisory authorization task with the same two-phase
tooling-freeze / empirical-barrier discipline used for D001.

---

## 1. Scientific question

> Under unchanged frozen V1 semantics in Fold 01, at which canonical
> FVG-generation or retention stage does the final same-direction unfilled FVG
> list become empty?

D002 is an **explanatory decomposition** of the canonical FVG pipeline.
It is **not**:

* a strategy variant;
* a threshold trial or multiplier search;
* a candidate-generation counterfactual;
* an overlap-strictness test (H001 is downstream motivation only — D002 does
  NOT claim to test overlap tolerance);
* a profitability evaluation.

All output must be labelled:

`DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE`

## 2. Input boundary (execution-time)

D002 execution may inspect **only** Fold 01:
`[2024-04-01T00:00:00Z, 2024-06-08T00:00:00Z)`, plus the causal
warm-up/history that existing Fold-01 semantics already require.

* It must use the canonical production path
  `bot/state/gate_inputs.py::build_gate_inputs` →
  `get_unfilled_fvgs(entry, timeframe="M5", direction=htf_bias)` →
  `bot/analysis/fvg_engine.py::detect_fvgs` unchanged.
* It must **not** inspect Fold 02, Fold 03 or Fold 04 in any form.
* It must **not** access 2025+ market data or holdout.
* No new observation may influence any preregistered text.

## 3. Preregistered attrition stages (exactly these)

For each eligible decision, decompose the canonical path without changing it:

### Stage A — sufficient FVG detector input

Whether the causal M5 frame contains enough rows for the canonical detector.
Record pass/fail per decision.

### Stage B — ATR-valid three-candle opportunities

Number/presence of candidate windows for which canonical ATR exists and is
positive, per the frozen detector availability semantics (canonical
`calculate_atr` output availability as consumed by `detect_fvgs`).

### Stage C — displacement-body threshold

The frozen detector requires
`abs(c2.close - c2.open) >= ATR * displacement_mult`.
Record pass/fail using the **exact frozen detector parameter actually used by
`get_unfilled_fvgs`**. Do not try alternative values.

### Stage D — geometric FVG

Among canonical detector-eligible windows: bullish gap, bearish gap, or no
gap, per the frozen three-candle geometric definitions only.

### Stage E — direction filter

For detected FVGs: same direction as `htf_bias`, or opposite direction.

### Stage F — fill-status filter

For detected same-direction zones: unfilled at decision time, or filled at
decision time (canonical `get_unfilled_fvgs` fill semantics).

### Stage G — final canonical list

Decision-level: final canonical FVG count; any canonical FVG yes/no.

**Reconciliation requirement:** the Stage-G final canonical FVG presence must
reproduce the D001 observation exactly: **0**. Any mismatch is a stop
condition (`FAILURE TO REPRODUCE FINAL CANONICAL FVG PRESENCE`).

## 4. Population transitions

The primary population is decisions for which the canonical FVG acquisition
logic is eligible to execute under existing semantics. **All population
transitions must be reported explicitly** (eligible → Stage A → Stage B → ...
→ Stage G), reconciling exactly at every transition.

## 5. Unique-versus-repeated structure

Because each decision sees a causal history window, the same historical FVG
may appear in more than one decision. Preregister both where deterministically
identifiable:

* decision-level counts;
* unique FVG identities/counts.

The unique identity is defined **now**, before execution, deterministically
from existing canonical record attributes (source/time/zone fields of the
canonical FVG records, including entry-frame `open_time` availability on the
causal M5 frames). No identity choice may be made after seeing results. If a
scientifically unambiguous identity cannot be defined from canonical records,
unique-zone counts are omitted and the reason is documented **before**
execution.

## 6. Raw detector observations are NOT strategy candidates

D002 may count detector stages. It must **not** calculate:

* candidate counts under altered FVG logic;
* hypothetical confluence scores;
* hypothetical overlap passes;
* fills, trades, or any lifecycle counterfactual;
* profitability of any kind.

A raw geometric FVG count is a diagnostic property, not evidence that a trade
should occur.

## 7. No threshold search

Do not calculate: the result if the displacement multiplier were 1.4, 1.3 or
1.2; an optimal FVG multiplier; count-versus-threshold curves; fill-window
alternatives; proximity alternatives. Only the exact frozen detector semantics
may be decomposed. If a specific frozen stage proves dominant, any change to
it later requires a separately preregistered strategy hypothesis/variant.

## 8. Permitted output surface

* population counts by stage;
* pass/fail counts/rates;
* bullish/bearish gap counts;
* direction-match counts;
* filled/unfilled counts;
* final canonical list counts;
* deterministic descriptive summaries (count, min, max, median, quartiles) of
  already-preregistered detector variables: ATR, displacement body,
  displacement-body/ATR ratio, gap width, FVG width.

No outcome-based threshold recommendation.

## 9. Two-phase execution discipline

* **Phase A:** implement and test D002 tooling on synthetic/non-empirical
  fixtures only; commit and push the tooling **before** any Fold-01 access;
  mirror equivalence against the production `get_unfilled_fvgs`/`detect_fvgs`
  path must be proven before empirical execution.
* **Phase B:** execute only after the remote branch resolves to the frozen
  D002 tooling commit. No tooling edit is permitted after seeing D002
  empirical output. If a scientific/tooling defect is discovered after data
  exposure: STOP; do not silently patch and rerun under the same ID.

## 10. Stop conditions

Canonical identity mismatch; H004/D002 preregistration mismatch; fold boundary
mismatch; Fold 02–04 access; 2025+/holdout access; causal-history violation;
failure to reproduce final canonical FVG presence; detector mirror mismatch;
unregistered metric; threshold search; candidate counterfactual; performance
output.

## 11. H002 boundary

`phase8-v2-H002` remains OPEN and is not touched by D002: it requires a
separately preregistered canonical `evaluate_order_block` lifecycle diagnostic
(a potential later D003). D002 does not repair or approximate it.
