# Phase 8 V2 — Strategy Variant V005 Fold-01 Result (R001, Observed)

**Variant:** `phase6-development-v2-V005` — Eligibility-Scoped Requested-Side Entry Direction Authority  
**Linked effective hypothesis:** `phase8-v2-H009-TC001` (*Entry Direction Authority Coherence*)  
**Historical hypothesis:** `phase8-v2-H009`  
**Supporting diagnostic:** `phase8-v2-D006` (R001 valid)  
**Predecessor scientific baseline:** `phase6-development-v2-V003` (R001 observed, 81 candidates)  
**Historical blocked implementation:** `phase6-development-v2-V004` (Attempt 1: `phase6-development-v2-V004-ATTEMPT1`, `IMPLEMENTATION_BLOCKED_POST_EXPOSURE`)  
**Record:** `phase6-development-v2-V005-R001` (`STRATEGY_VARIANT_RESULT`)  
**Result classification:** `DEVELOPMENT_VARIANT_EVIDENCE — V005 — FOLD01 — NOT PROFITABILITY EVIDENCE`  
**Opportunity classification:** **`OPPORTUNITY_SUFFICIENT`** — mechanical application of the preregistered rule `candidate_ready >= 90` with `candidate_ready = 102`

---

## 1. Identity and Lineage

| Element | Identity |
|---|---|
| D006 empirical baseline | `f45a22f24560a1605bac5b2658011769da0e5bdf` |
| V004 blockage governance | `3e5a71bd25c1d03d72595eecb5d7d0c052bf5e40` |
| V005 Phase-A preregistration | `252af6a9434e155e70ce37e07893f1a8a06a600a` |
| V005 Phase-B implementation & tooling freeze | `2fd3460b9010d8cca548f4fd6980b6b34fe594e2` (execution baseline) |
| Specification (Phase-A scientific contract) | `docs/PHASE8_V2_VARIANT_V005.md`, SHA-256 `7f4972f36bd99f550c142741c1c3065db6ca1fc6d1f041858cf141ebd9477e35` (12,301 bytes, Git blob `d127d3b45b54135038698b1cebe540a0f43a0c20`) |
| Strategy implementation | `bot/strategy/variant_v005.py`, Git blob `3820c6c66f96c91d98b47feda0e4f5f88aa5c70a`, `canonical_git_blob_v1` fingerprint `717dc07aff63d0150fbd47de036e81bd12e270c4a5de31f78f5fc48dc998fd2f` |
| Measurement tooling | `backtests/phase8_v2_variant_v005_eval.py`, Git blob `6291999b059facadf6ea40482f8413872cf4cd23`, `canonical_git_blob_v1` fingerprint `dd4d864e6caf3413447121bac9bc412c1db7a8df6243422840e0e5d59ca26683` |

Execution was performed strictly on the frozen commit `2fd3460b9010d8cca548f4fd6980b6b34fe594e2`. Zero source code or tooling modifications were made after pre-flight verification.

---

## 2. Relationship to Blocked V004

Strategy variant V005 is a **NEW** variant, authorized under Charter §11 and §38 to test the unresolved scientific mechanism of hypothesis H009. It is **NOT** a V004 Attempt 2, rerun, or patch:
- **Historical V004 Blockage:** V004 Attempt 1 failed closed on the very first Gate-11 entrant decision (`2026-10-13T12:22:49Z`) because an executable directional consistency check in `bot/strategy/variant_v004.py` was evaluated unconditionally across all Gate-11 entrants before checking baseline readiness or fallback eligibility. This caused `V004VariantError` on unformed structural pairs (`pair.side == StrategySide.FLAT`).
- **Permanent Closure of V004:** V004 is permanently closed as `IMPLEMENTATION_BLOCKED_POST_EXPOSURE`. Variant slot 4 was permanently consumed (`4 / 8` observed).
- **V005 Scoped Guard Architecture:** V005 introduced eligibility-scoped guard evaluation:
  - Step A: baseline preservation evaluated FIRST (`v003_entry_ready == True` returns immediately).
  - Step B: non-eligible decisions (`v003_gate11_passed == False` or `v003_strategy_eligible == False`) return `entry_ready = False, entry_source = "NONE"` cleanly without raising exceptions on FLAT pairs.
  - Step D: pair-side consistency is enforced strictly on decisions reaching the actual fallback surface.
- **Empirical Validation:** V005 processed all 526 Gate-11 entrants cleanly with zero runtime exceptions, confirming the validity of the scoped guard contract.

---

## 3. Research Classification

Development evidence on contaminated Tier-A Fold 01. This run answers only:  
*Does V005 create sufficient raw opportunity density on Tier-A Fold 01 (`candidate_ready >= 90`)?*  
It does NOT establish sample sufficiency, profitability, or production readiness. Tier B remains strictly sealed.

---

## 4. Empirical Exposure and Budget Transition

- **Exposure Timestamp:** `2026-10-13T14:35:22.294978+00:00` (instant first real Fold-01 decision entered `observe_v005_decision`).
- **Run Duration:** `2026-10-13T14:35:22.294978+00:00` → `2026-10-13T14:57:33+00:00` (~22 minutes, single valid run, no rerun).
- **Permanent Budget Transition:** Consumed variant slot 5 at the exposure instant.
  - Diagnostics executed: `5 / 12`
  - Strategy variants observed: **`5 / 8`** (`V001`, `V002`, `V003`, `V004` [consumed/blocked], `V005` [observed])
  - Numeric parameter trials: `0 / 4`
  - Upward revision lock: `ACTIVE`

---

## 5. Store Provenance and Pre-Observation Integrity

- **Store Path:** `C:/Users/chips/forex-signal-bot-data/phase8/evidence/market-feature-store/fold-01-a8b406884ab3525a`
- **Store Identity SHA-256:** `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4`
- **Rows Content SHA-256:** `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22`
- **Snapshots:** `13269`
- **Coverage:** `fold-01/full`, M5
- **Pre-Observation Verification:** `verify_rows=True` executed before observation, re-verifying row hashes and gate event IDs across all 13,269 rows. Prohibited store `fold-01-1d710826193a6767` was never opened.
- **Fail-Closed Assertions:** All required causal context fields asserted fail-closed throughout execution; zero violations raised.

---

## 6. Decision Accounting

The sequential causal replay loop processed all scheduled snapshots:

| Category | Count | Proportion | Reconciles |
|---|---|---|---|
| Scheduled Snapshots | 13,269 | 100.00% | Reference total |
| Reducer Classified | 7,316 | 55.14% | Matches D001/D003/D004/D005/D006/V002/V003 |
| Missing History | 4,815 | 36.29% | Identical reference count |
| Unavailable Input | 1,138 | 8.58% | Identical reference count |
| Evaluation Errors | 0 | 0.00% | Zero runtime errors |
| **Sum** | **13,269** | **100.00%** | `7316 + 4815 + 1138 + 0 == 13269` ✓ |

The upstream reference pipeline remained completely unaltered; V005 operated strictly read-only.

---

## 7. Sealed V003 Baseline Reproduction & Candidate Preservation

V005 was executed with `--v003-result` pointing to the sealed external V003 R001 artifact (`phase6-development-v2-V003_result.json`, SHA-256 `50117c399481a2e31b8da6260da4e05c8719a522efb524f80bb2063319c41ff8`, 45,221 bytes).

### 7.1 Upstream Count Reproduction
- **Gate-11 Entrants:** `526` (expected: 526, observed: 526) ✓
- **V003 Gate-11 Passes:** `138` (expected: 138, observed: 138) ✓
- **Canonical Strategy Passes:** `110` (expected: 110, observed: 110) ✓
- **V003 Baseline Candidates:** `81` (expected: 81, observed: 81) ✓

### 7.2 Candidate Identity Multiset Equality
- All 81 `(decision_id, setup_id)` candidate pairs from sealed V003 R001 matched identically (`multiset_identity_equal: true`).
- Unique setup IDs: `81`, duplicate occurrences: `0`.

### 7.3 Entry Object Deterministic Parity
- All 81 deterministic JSON entry objects matched byte-for-byte with sealed V003 R001 (`all_entry_objects_identical: true`).

### 7.4 Baseline Preservation Under V005
- All 81 baseline candidates were emitted under V005 with `entry_source = "V003_BASELINE"` (`all_v003_candidates_preserved: true`).
- Zero baseline candidates were dropped, altered, or re-routed.

---

## 8. V005 Structural Funnel

| Stage | Entered | Passed | Failed | Pass Rate |
|---|---|---|---|---|
| `gate_11_v005` (Confluence 8/8) | 526 | **138** | 388 | 26.24% |
| `canonical_strategy_v005` (Protections) | 138 | **110** | 28 | 79.71% |
| `gate_12_13_rr_entry_v005` (Entry Readiness) | 110 | **102** | 8 | 92.73% |

Funnel chain reconciliation holds fail-closed: `102 <= 110 <= 138 <= 526`. Each stage's entered count equals exactly the previous stage's passed count.

The 8 rejections at Gate 12/13 entry consist of:
- 7 D006 E2 readiness failures that lacked internal confirmation (`internal_bos_seen`, `choch_seen`, or `sweep_rejected`), correctly remaining rejected under frozen score-8 conservative early-entry rules.
- 1 setup failing frozen entry geometry / RR parameters.

---

## 9. Candidate Surface and Source Decomposition

- **Total `candidate_ready`:** **`102`**
- **Candidate Rate:** `0.193916` (102 / 526 Gate-11 entrants)
- **Candidate Breakdown by Source:**
  - `V003_BASELINE`: **`81`** (79.41%)
  - `V005_DIRECTIONAL_FALLBACK`: **`21`** (20.59%)
  - Reconciles: `81 + 21 == 102` ✓

The 21 fallback candidates represent the recovery of decisions identified in diagnostic D006 that passed Gate-11 confluence (8/8) and canonical strategy protections, but suffered from internal directional authority divergence between Gate-11 inputs (`htf_bias`) and Gate-12/13 entry routing (`state.structure_dir`).

---

## 10. Candidate Directional Distribution

| Population | LONG (BUY) | SHORT (SELL) | Total |
|---|---|---|---|
| Baseline Candidates (`V003_BASELINE`) | 48 | 33 | 81 |
| Fallback Candidates (`V005_DIRECTIONAL_FALLBACK`) | 7 | 14 | 21 |
| **Total Candidates (`candidate_ready`)** | **55** | **47** | **102** |

All 21 fallback entries show 100% agreement with `requested_side`:
- 7 BUY candidates derived from `requested_side = "bullish"`
- 14 SELL candidates derived from `requested_side = "bearish"`

---

## 11. Setup ID Uniqueness and Duplication Analysis

- **Unique Candidate Setup IDs:** `102`
- **Duplicate Setup ID Occurrences:** `0`
- **Reconciliation:** `unique (102) + duplicates (0) == candidate_ready (102)` ✓
- Every candidate setup ID (`s8n1_...`) maps 1-to-1 to a distinct causal decision event. Zero deduplication occurred.

---

## 12. Structural Invariance Assertions

1. **State Invariance:** Authoritative `StrategyState` was never mutated. Fallback execution operated strictly on private deep copies (`copied_state.structure_dir = req_side`).
2. **Liquidity Rules Invariance:** Frozen valid combinations (`SELL + equal_lows`, `BUY + internal_continuation` for bullish; `BUY + equal_highs`, `SELL + internal_continuation` for bearish) were evaluated without modification, broadening, or relaxation.
3. **No Counterfactuals:** Zero counterfactual simulations, alternative threshold explorations, or parameter scans were performed.
4. **No Profitability Metrics:** Zero P&L, win rate, Sharpe, drawdown, profit factor, or return distributions were computed.

---

## 13. Opportunity Classification

Under the preregistered decision rule of the Research Charter:
- Target: `raw candidate_ready >= 90`
- Observed: `candidate_ready = 102`
- **Outcome Classification:** **`OPPORTUNITY_SUFFICIENT`**

This result establishes raw opportunity density adequacy on contaminated Tier-A Fold 01.

---

## 14. Status of Hypothesis H009

Hypothesis `phase8-v2-H009-TC001` remains in status `REGISTERED` with disposition **`PENDING_SUPERVISORY_INTERPRETATION`**.  
The hypothesis statement is NOT automatically mutated to `SUPPORTED` or `REFUTED` in the governance register. Supervisory review must formally evaluate the empirical finding (102 candidates, 21 fallback recoveries, 81 baseline preservations, 0 duplicates) to establish the scientific disposition.

---

## 15. What V005 Establishes

1. **Density Adequacy on Tier-A Fold 01:** Unifying Gate-12/13 directional authority with requested trade side unlocks 21 high-confluence candidates previously blocked by internal authority divergence, raising raw opportunity count from 81 to 102 (`OPPORTUNITY_SUFFICIENT` >= 90).
2. **Perfect Baseline Preservation:** All 81 V003 baseline candidates are preserved identically with zero loss, zero alteration, and byte-level deterministic entry object parity.
3. **Sound Scoped Guard Architecture:** Scoping directional consistency checks to fallback-eligible decisions resolves the architectural failure mode of V004, maintaining fail-closed safety without premature aborts on pre-structural FLAT states.
4. **Strict Conservative Readiness Invariance:** Preserving the requirement for internal structural confirmation in early entry correctly holds the line on D006 E2 rejections (7 remaining rejected).

---

## 16. What V005 Does NOT Establish

1. **No Profitability Evidence:** V005 Fold-01 execution measures opportunity density only. It provides zero evidence regarding profitability, expectancy, win rate, Sharpe ratio, or drawdown.
2. **No Sample Sufficiency:** Density adequacy on contaminated Fold 01 does not demonstrate statistical sufficiency across out-of-sample periods or market regimes.
3. **No Execution Authorization:** V005 does NOT authorize opening Fold 02, unsealing Tier B, or deploying code to live/demo environments.
4. **No Automatic `phase6-frozen-v2` Creation:** Formal candidate freeze requires supervisory candidate selection (§14) and explicit freeze authorization (§17).

---

## 17. External Sealed Artifact

- **Path:** `C:/Users/chips/forex-signal-bot-data/phase8/v2_variants/phase6-development-v2-V005/fold01/phase6-development-v2-V005_result.json`
- **Byte Count:** `80,554` bytes
- **SHA-256:** `27b8849eb97074d55c36bf11645cae8821d517b1f9e52e0c9a37976c77abcbfe`
- **Verification:** Read back from disk, verified against committed schema and baseline integrity checks.

---

## 18. Budget and Reserved Evidence Summary

- **Diagnostic Budget:** `5 / 12` executed (7 remaining)
- **Strategy Variant Budget:** `5 / 8` observed (`V001`, `V002`, `V003`, `V004` [consumed/blocked], `V005` [observed]; 3 remaining)
- **Numeric Parameter Trials:** `0 / 4` consumed (4 remaining)
- **Upward Revision Lock:** `ACTIVE` (budgets cannot be expanded)
- **Reserved Evidence:** Folds 02–04, holdout dataset, and 2025+ calendar data remain strictly **SEALED** and untouched. Tier B remains **SEALED**.
