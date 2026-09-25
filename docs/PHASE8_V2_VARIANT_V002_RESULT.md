# PHASE 8 V2 — STRATEGY VARIANT V002 FOLD-01 RESULT (R001, OBSERVED)

**Variant:** `phase6-development-v2-V002` — Canonical Structural OB/FVG Pair
**Primary hypothesis:** `phase8-v2-H007` (statement unchanged, not rewritten)
**Record:** `phase6-development-v2-V002-R001` (`STRATEGY_VARIANT_RESULT`)
**Result classification:** `DEVELOPMENT_VARIANT_EVIDENCE — V002 — FOLD01 — NOT PROFITABILITY EVIDENCE`
**Opportunity classification:** **`OPPORTUNITY_INSUFFICIENT`** — mechanical application of the
preregistered rule `0 < candidate_ready < 90` with `candidate_ready = 61`

---

## Identity and lineage

| Element | Identity |
|---|---|
| D004 result baseline | `cd7526260ac224facb5dbf993f6e98be25cb650d` |
| Phase-A preregistration | `3d910becf95ea3f0e9888241ec6f34af35fcfd42` |
| Implementation/tooling freeze | `4890dcbce8579f159224b653d94f634cc9017549` |
| TC001 — Gate-11 entrant population | `c2e74090e2ac29d54b2a5ed87c2ad28cac045bdb` |
| TC002 — candidate readiness through Gates 12–13 | `cae8637adfbfae7338179d2e4d0888d81266e916` (execution baseline) |
| Specification (Phase-A scientific content) | SHA-256 `f53f27c4e7700adf63194392e05f4c523d65312ecde7081dc427ec7347aa8703` (byte-identical pre-freeze; the frozen document adds only the append-only Phase-B §25 freeze record, committed blob `5c07fbe4…`) |
| Strategy implementation | `bot/strategy/variant_v002.py`, Git blob `8272c28552c05067b6dc3ba039ee8df2dbbfb8b4` at BOTH the freeze commit and the execution baseline (verified equal before access) |
| Measurement tooling | `backtests/phase8_v2_variant_v002_eval.py`, `canonical_git_blob_v1` fingerprint `2151c2171c0c43d02bbfdd8f25208c0fd304e7406101eec2581093303786c6d7`, **recomputed from the committed Git blob before execution**, not copied |

Only the TC002 tooling was executed. No V002 code and no tooling was modified for this run.

## Research classification

Development evidence on contaminated Tier-A Fold 01. This run answers only:
*Does V002 create sufficient raw opportunity density on Tier-A Fold 01?*
It does not establish sample sufficiency, profitability, or production readiness.

## Empirical exposure

* Exposure timestamp (first authorized store processing): **`2026-09-25T21:44:00.712191+00:00`**
* Valid run window: 21:44:00.712191Z → 21:48:00.258693Z (**239.5 s**), single run, no rerun
* Budget permanently consumed by this first observation: strategy variants **`2 / 8` observed**
  (diagnostics `3 / 12`; numeric trials `0 / 4`; upward-revision lock ACTIVE)

## Store provenance

* Store: `fold-01-a8b406884ab3525a` — the preserved immutable V001 store (decision B, unchanged)
* Store identity SHA-256 `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4`;
  rows-content SHA-256 `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22`
* `verify_rows=True` full row re-hash + gate-event-id re-derivation over all **13,269** rows passed
  before any observation; `fold-01/full`, M5; the prohibited historical store
  `fold-01-1d710826193a6767` was never opened
* Per-snapshot required causal fields (entry_rows, fvgs, htf_bias, atr, ob_result, displacement,
  session_context, liquidity_context, internal_structure, liquidity_signal) asserted fail-closed —
  zero violations raised during the run

## TC001 population correction

V002 population = **all decisions that legitimately entered frozen Gate 11**:
`gate11_entrants_observed = 526`, exactly equal to the frozen funnel's
`gate_11_confluence_score.entered = 526` (hard reconciliation passed). The historical Gate-11
boolean was descriptive only: `legacy_score_passed_count = 1`, `legacy_score_failed_count = 525`
— both included, neither gating V002.

## TC002 candidate-ready correction

`candidate_ready` is `count(v002_entry_ready)` through the frozen Gate-12/13 entry model —
**not** canonical-strategy eligibility. In this result the two differ materially: 80 setups passed
the V002 canonical strategy but only 61 passed `determine_entry`; honoring TC002, **61** is the
candidate count.

## Historical Gate funnel (unchanged reference pipeline)

`13,269 scheduled = 7,316 reducer-classified + 4,815 missing_history + 1,138 unavailable_input + 0 errors`
— identical to D003/D004; Gates 8–11: `7,316 → 3,607 → 1,489 → 526 → 1`.
This confirms the upstream pipeline was unchanged; V002 observed it read-only.

## V002 structural-pair surface

* Pair states: `ACTIVE 144` · `MITIGATED 92` · `INVALIDATED 15` · `UNAVAILABLE 275`
* H007 reason distribution: `structurally_active_block 144`, `block_already_mitigated 92`,
  `close_below_bullish_zone 9`, `close_above_bearish_zone 6`, `no_confirmed_block 275`
* Sides: LONG 149 / SHORT 102 / FLAT 275
* Structurally-active count: **144** (age > 30 did not, by itself, reject any untouched block)
* Associated same-direction final canonical FVG count: **110** of 144 active pairs (76.4%)
* Structural-active age summary: min 0 / p25 5.8 / median 13.5 / p75 41.2 / max 113 bars

## V002 variant funnel

| Stage | Entered | Passed | Failed |
|---|---|---|---|
| `gate_11_v002` (TC001 entrants; V002 8/8) | 526 | **102** | 424 |
| `canonical_strategy_v002` (entry_eligible) | 102 | **80** | 22 |
| `gate_12_13_rr_entry_v002` (frozen `determine_entry`) | 80 | **61** | 19 |

Chain reconciliation passed fail-closed: `61 ≤ 80 ≤ 102 ≤ 526`, and each stage's entered equals
the previous stage's passed.

## Gate-11 V002 score outcome

102 of 526 entrants (19.4%) pass the V002 8/8 score with the frozen weights 2/1/2/1/2 —
versus exactly **1** historical passer. The 101 additional passes are decisions the frozen
legacy-OB + exact-overlap conjunction rejected; that is the semantic effect H007 predicted
qualitatively and V002 was built to measure.

## Canonical-strategy outcome

80 of the 102 V002 Gate-11 passers are entry-eligible downstream (22 rejected by unchanged
protections — regime/bias/DXY/news/session/allowlist paths inside the untouched engine).

## Gate-12/13 entry outcome

61 of the 80 canonical-strategy passers produce a real frozen `determine_entry` object
(19 `entry_not_ready` for unchanged entry-model reasons — liquidity alignment / pullback
conditions). These 19 are correctly NOT candidates under TC002.

## Candidate-ready surface

* **`candidate_ready = 61`** — candidate rate 61/526 = **0.11597**
* Long 41 / Short 20
* Candidate ages: min 0, max 113 bars (includes >30-bar candidates the frozen evaluator
  would have expired)
* Descriptive exact overlap among candidates: true 25 / false 36 — membership never required it

## Candidate setup-ID reconciliation

* 61 persisted stable setup IDs (`s8n1_…`), event-id-reconciled fail-closed per candidate
* `unique_candidate_setup_ids = 61`, `duplicate_candidate_setup_id_occurrences = 0`
* `unique + duplicates == candidate_ready` → `61 + 0 == 61` ✓ (no silent deduplication)
* Decision IDs reported separately as `candidate_decision_ids` (61 distinct)
* Full ID lists sealed verbatim in the external result JSON; counts restated here

## Long/short distribution

Candidates: **LONG 41 (67.2%) / SHORT 20 (32.8%)**. Observed V002 structural pairs:
LONG 149 / SHORT 102.

## Age distribution

Structural-active blocks: min 0 / p25 5.8 / median 13.5 / p75 41.2 / max 113 — the upper
quartile extends past the frozen 30-bar expiry, empirically confirming H006's
expiry-preemption structure inside the V002-eligible surface. Candidate ages reach 113 bars.

## Exact-overlap descriptive outcome

Among the 110 associated same-direction FVG observations: exact overlap **true 67 / false 43**
(39.1% fail exact overlap) — descriptively consistent with the H001 synthesis; the overlap
boolean never gated V002 membership. Among the 61 candidates: true 25 / false 36.

## Opportunity classification

`candidate_ready = 61`, therefore **`OPPORTUNITY_INSUFFICIENT`** (`0 < 61 < 90`), mechanically
determined. Per the preregistered rule this means the variant does not yet merit Tier-B
progression; no ranking above 90 was computed and nothing was tuned toward 90.

## What V002 establishes

* The TC001/TC002-corrected harness measures V002's own semantic effect end-to-end on real data.
* One coherent structural-pair concept admits a materially larger Gate-11 surface than the
  frozen legacy-OB + exact-overlap conjunction (102 vs 1 passes) while every upstream gate,
  DXY authority, and the frozen entry model remain unchanged.
* The frozen Gate-12/13 model and downstream protections still bind: only 61 of 526 entrants
  become raw candidates.
* On contaminated Tier-A Fold 01 the variant's raw opportunity density (61, rate 0.116)
  is below the 90-candidate research target — an honest negative density result.

## What V002 does NOT establish

No profitability of any kind; no win rate, expectancy, drawdown, Sharpe, or trade outcomes;
no sample sufficiency; no production readiness; no Tier-B acceptance; no claim that 61 is a
final ceiling (no alternative score, threshold, expiry, DXY, or Gate-12/13 configuration was
tested); no V003 created.

## Budget

Diagnostics `3 / 12`; strategy variants **`2 / 8` observed** (V002 consumed at first
observation); numeric trials `0 / 4`; `UPWARD STRATEGY-VARIANT / PARAMETER-TRIAL BUDGET
REVISION PROHIBITED = ACTIVE`. Zero diagnostic budget was consumed by this variant run.

## Reserved evidence

Folds 02–04, holdout and 2025+ remain sealed and untouched. **Tier B remains sealed**; even
had `candidate_ready ≥ 90` been observed, Tier-B release would require separate supervisory
authorization after R001 review. With `OPPORTUNITY_INSUFFICIENT` recorded, the preregistered
Tier-B precondition (`candidate_ready ≥ 90` on Fold 01) is not met.
