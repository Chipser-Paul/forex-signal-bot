# PHASE 8 V2 — STRATEGY VARIANT V003 FOLD-01 RESULT (R001, OBSERVED)

**Variant:** `phase6-development-v2-V003` — Causal Temporal FVG Evidence Memory  
**Primary hypothesis:** `phase8-v2-H003` (supported by D005 R001; statement unchanged, not rewritten)  
**Supporting diagnostic:** `phase8-v2-D005` (R001 valid)  
**Predecessor variant:** `phase6-development-v2-V002` (R001 observed, 61 candidates)  
**Record:** `phase6-development-v2-V003-R001` (`STRATEGY_VARIANT_RESULT`)  
**Result classification:** `DEVELOPMENT_VARIANT_EVIDENCE — V003 — FOLD01 — NOT PROFITABILITY EVIDENCE`  
**Opportunity classification:** **`OPPORTUNITY_INSUFFICIENT`** — mechanical application of the
preregistered rule `0 < candidate_ready < 90` with `candidate_ready = 81`

---

## Identity and lineage

| Element | Identity |
|---|---|
| D005 result baseline | `4d037f893c9f93dae32e5aa6af6b404fc3445b1f` |
| Phase-A preregistration | `18dc9889cf119623e56026d529e9546808125444` |
| Implementation/tooling freeze | `82cf09b92fdcd67af8b560f6d0e296dbc618ebd1` |
| TC001 — measurement-observer correction | `39817b3994a2d73e6c80eaf37579e8e3b3020b65` (execution baseline) |
| Specification (Phase-A scientific content) | SHA-256 `e6aa3e8a4f7b909f178a18112a43425ccfe61448c3c8643aea9c3f5d670e0d95` (12,390 bytes, byte-identical) |
| Strategy implementation | `bot/strategy/variant_v003.py`, Git blob `c25f110c15c60bc5b32cffc0b3870de6d5d5144c` at BOTH the freeze commit and the execution baseline (verified identical before access) |
| Measurement tooling | `backtests/phase8_v2_variant_v003_eval.py`, `canonical_git_blob_v1` fingerprint `40df72bd13902199504fb89cbd5d64184b923cffce1f211d041cffacc743c9b9`, **recomputed from the committed Git blob before execution**, not copied |

Only the TC001-corrected tooling was executed. No V003 code and no tooling was modified for this run.

## Research classification

Development evidence on contaminated Tier-A Fold 01. This run answers only:  
*Does V003 create sufficient raw opportunity density on Tier-A Fold 01?*  
It does not establish sample sufficiency, profitability, or production readiness.

## Empirical exposure

* Exposure timestamp (first authorized store processing): **`2026-09-29T18:27:20.872944+00:00`**
* Valid run window: 2026-09-29T18:27:33Z → 2026-09-29T19:10:27Z, single run, no rerun
* Budget permanently consumed by this first observation: strategy variants **`3 / 8` observed**
  (diagnostics `4 / 12`; numeric trials `0 / 4`; upward-revision lock ACTIVE)

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

## Gate-11 entrant population reconciliation

V003 population = **all decisions that legitimately entered frozen Gate 11**:  
`gate11_entrants_observed = 526`, exactly equal to the frozen funnel's
`gate_11_confluence_score.entered = 526` (hard reconciliation passed). The historical Gate-11
boolean was descriptive only: `legacy_score_passed_count = 1`, `legacy_score_failed_count = 525`
— both included, neither gating V003.

## Historical Gate funnel (unchanged reference pipeline)

`13,269 scheduled = 7,316 reducer-classified + 4,815 missing_history + 1,138 unavailable_input + 0 errors`  
— identical to D001/D003/D004/D005/V002; Gates 8–11: `7,316 → 3,607 → 1,489 → 526 → 1`.  
This confirms the upstream pipeline was unchanged; V003 observed it read-only.

## V003 structural-pair surface

* Pair states: `ACTIVE 144` · `MITIGATED 92` · `INVALIDATED 15` · `UNAVAILABLE 275`
* H007 reason distribution: `structurally_active_block 144`, `block_already_mitigated 92`,
  `close_below_bullish_zone 9`, `close_above_bearish_zone 6`, `no_confirmed_block 275`
* Sides: LONG 149 / SHORT 102 / FLAT 275
* Structurally-active count: **144** (identical to V002 baseline)
* Associated final-surface canonical FVG count: **110** of 144 active pairs
* Associated temporal-memory canonical FVG count: **97**
* Total V003 FVG evidence count: **207** (out of 526 entrants; 319 NONE)
* Descriptive exact overlap among final-surface pairs: true 67 / false 43 (identical to V002 baseline)
* Temporal FVG offset summary: count 97, min 1, max 7, median 1.0, p25 1.0, p50 1.0, p75 1.0 bars

## V003 variant funnel

| Stage | Entered | Passed | Failed |
|---|---|---|---|
| `gate_11_v003` (TC001 entrants; V003 8/8) | 526 | **138** | 388 |
| `canonical_strategy_v003` (entry_eligible) | 138 | **110** | 28 |
| `gate_12_13_rr_entry_v003` (frozen `determine_entry`) | 110 | **81** | 29 |

Chain reconciliation passed fail-closed: `81 ≤ 110 ≤ 138 ≤ 526`, and each stage's entered equals
the previous stage's passed.

## Gate-11 V003 score outcome

138 of 526 entrants (26.2%) pass the V003 8/8 score with the frozen weights 2/1/2/1/2 —
versus **102** passes in V002 and **1** historical passer.  
The 36 additional passes are decisions rescued specifically by temporal FVG evidence memory ($F_{\text{temporal}}$),
matching exactly the 36 temporal associations identified in D005 Attempt 4.

## Canonical-strategy outcome

110 of the 138 V003 Gate-11 passers are entry-eligible downstream (28 rejected by unchanged
protections — regime/bias/DXY/news/session/allowlist paths inside the untouched engine).

## Gate-12/13 entry outcome

81 of the 110 canonical-strategy passers produce a real frozen `determine_entry` object
(29 `entry_not_ready` for unchanged entry-model reasons — liquidity alignment / pullback
conditions / RR thresholds). These 29 are correctly NOT candidates under TC002/TC001 semantics.

## Candidate-ready surface

* **`candidate_ready = 81`** — candidate rate 81/526 = **0.153992**
* Long 48 / Short 33
* Candidate FVG evidence source decomposition:
  - **FINAL_SURFACE: 61** (exactly reproduces the 61 candidates observed in V002 R001)
  - **TEMPORAL_MEMORY: 20** (20 additional candidates generated by temporal FVG evidence memory)
  - `61 + 20 = 81`
* Descriptive exact overlap among candidates: true 34 / false 27 / null 20 (temporal-only memory has no final zone)
* Entry mode: conservative (81/81)
* Entry type: partial (81/81)

## Candidate setup-ID reconciliation

* 81 persisted stable setup IDs (`s8n1_…`), event-id-reconciled fail-closed per candidate
* `unique_candidate_setup_ids = 81`, `duplicate_candidate_setup_id_occurrences = 0`
* `unique + duplicates == candidate_ready` → `81 + 0 == 81` ✓ (no silent deduplication)
* Full ID lists sealed verbatim in the external result JSON; counts restated here

## Live-zone separation verification

When $F_{\text{temporal}}$ is the sole active evidence, `live_fvg_zone` was strictly `None`.
No historical filled FVG zone was resurrected into `context["fvg_zone"]`, `strategy_state.fvg_zone`,
pullback/limit zones, stop loss, take profit, or RR geometry.

## Strategy-state invariance verification

Neither V003 nor the evaluation observer mutated `StrategyState` fields
(`state.displacement_seen`, `state.fvg_zone`, `state.structure_state`, `state.liquidity_swept`).
The entry model executed over private deterministic copies reconstructed via `state_from_record`.

## Opportunity classification

`candidate_ready = 81`, therefore **`OPPORTUNITY_INSUFFICIENT`** (`0 < 81 < 90`), mechanically
determined. Per the preregistered rule this means the variant does not meet the 90-candidate
research threshold on Tier-A Fold 01. No ranking above 90 was computed and nothing was tuned toward 90.

## V002 structural comparison

| Metric | V002 (Final FVG only) | V003 (Final OR Temporal FVG) | Delta |
|---|---|---|---|
| Gate-11 entrants | 526 | 526 | 0 |
| Structurally active OBs | 144 | 144 | 0 |
| FVG evidence present | 110 | 207 | +97 |
| Gate-11 8/8 passes | 102 | 138 | +36 |
| Canonical strategy eligible | 80 | 110 | +30 |
| Gate-12/13 entry ready (`candidate_ready`) | 61 | **81** | **+20** |
| Long / Short candidates | 41 / 20 | 48 / 33 | +7 / +13 |
| Candidate rate | 0.11597 | 0.153992 | +0.038022 |

## What V003 establishes

* Temporal FVG evidence memory ($F_{\text{temporal}}$) is an effective structural mechanism: it safely rescues 36 Gate-11 entrants and converts 20 into valid, fully-formed candidates through the frozen Gate-12/13 entry engine.
* The V002 final-branch behavior is perfectly preserved: all 61 original V002 candidates are reproduced bit-for-bit without loss.
* Live-zone separation works cleanly: temporal memory provides structural evidence without distorting execution geometry.
* On contaminated Tier-A Fold 01, raw opportunity density increases from 61 to 81 (+32.8%), but falls short of the 90-candidate threshold (`81 < 90`) — an honest, rigorous negative result.

## What V003 does NOT establish

No profitability of any kind; no win rate, expectancy, drawdown, Sharpe, or trade outcomes;
no sample sufficiency; no production readiness; no Tier-B acceptance; no claim that 81 is a
final ceiling (no alternative score, threshold, expiry, lag window, DXY, or Gate-12/13 configuration was
tested); no V004 created.

## External sealed artifact

* Path: `C:/Users/chips/forex-signal-bot-data/phase8/v2_variants/phase6-development-v2-V003/fold01/phase6-development-v2-V003_result.json`
* SHA-256: `50117c399481a2e31b8da6260da4e05c8719a522efb524f80bb2063319c41ff8`
* Bytes: `45,221`
* Read-back verified from disk.

## Budget

Diagnostics `4 / 12`; strategy variants **`3 / 8` observed** (V003 consumed at first
observation); numeric trials `0 / 4`; `UPWARD STRATEGY-VARIANT / PARAMETER-TRIAL BUDGET
REVISION PROHIBITED = ACTIVE`.

## Reserved evidence

Folds 02–04, holdout and 2025+ remain sealed and untouched. **Tier B remains sealed**; even
had `candidate_ready ≥ 90` been observed, Tier-B release would require separate supervisory
authorization after R001 review. With `OPPORTUNITY_INSUFFICIENT` recorded (`81 < 90`), the preregistered
Tier-B precondition (`candidate_ready ≥ 90` on Fold 01) is not met.
