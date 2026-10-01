# Phase 8 V2 Diagnostic D006: V003 Post-Confluence Entry-State Attrition Decomposition Result

## 1. Identity & Lineage

* **Diagnostic Identity**: `phase8-v2-D006`
* **Title**: V003 Post-Confluence Entry-State Attrition Decomposition
* **Classification**: `DEVELOPMENT_DIAGNOSTIC_EVIDENCE — D006 — FOLD01 — NOT PROFITABILITY EVIDENCE`
* **Linked Hypothesis**: `phase8-v2-H008` (*Post-Confluence Entry-State Alignment Bottleneck*)
* **Governing Research Charter**: `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
* **Specification Document**: `docs/PHASE8_V2_DIAGNOSTIC_D006.md`
  * Phase-A Historical SHA-256: `a50b2e0ddfd84ecfa087dc5c347473cad40c58eb4f04c57f4f52038c73aa1ba6` (18,280 bytes)
  * TC001 Historical SHA-256: `fe29aa848c489b8d3f7a5e937efca20ef93bde9625f88d32ddd8f3ca9ec1a5eb` (22,552 bytes)
  * TC002 Frozen Specification SHA-256: `4ebe97b997f530e2d60a8b1f3a25f62e5c2e22456c7ccfc375b28b727add42ad` (28,558 bytes)
* **Tooling Implementation**: `backtests/phase8_v2_diagnostic_d006.py`
  * Tooling Commit: `0ea73bf2e46c5a9957be68af8fbf172e127a4b05`
  * Tooling Git Blob SHA: `eb206bf906243554beb135cfe7fa19b1707af983`
  * Tooling Canonical File Digest (`canonical_git_blob_v1`): `a61124b7ee2210800595d75bab55242bc03af080b0d31cf3b2c19d4bd23cfed6` (58,985 bytes)
* **Motivating Variant**: `phase6-development-v2-V003` (Result: `phase6-development-v2-V003-R001`)

---

## 2. V003 Sealed-Result Provenance & Integrity

The sealed prior V003 R001 artifact was read strictly as read-only prior governance evidence:
* **Path**: `C:/Users/chips/forex-signal-bot-data/phase8/v2_variants/phase6-development-v2-V003/fold01/phase6-development-v2-V003_result.json`
* **Expected & Verified SHA-256**: `50117c399481a2e31b8da6260da4e05c8719a522efb524f80bb2063319c41ff8`
* **Expected & Verified Bytes**: `45,221`
* **Status**: Intact, read-only, verified before and during execution.

---

## 3. D006 Exposure Window & Permanent Budget Transition

* **Target Market Feature Store**: `C:/Users/chips/forex-signal-bot-data/phase8/evidence/market-feature-store/fold-01-a8b406884ab3525a`
  * Store Canonical Identity SHA-256: `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4`
  * Parquet Rows Content SHA-256: `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22`
  * Total Scheduled Snapshots: `13,269`
  * Boundary: `2024-04-01T00:00:00+00:00` to `2024-06-08T00:00:00+00:00`
  * Coverage: `fold-01 / full`
* **Exposure Start Timestamp (UTC)**: `2026-10-01T18:29:24.670654+00:00`
* **Result Generation Timestamp (UTC)**: `2026-10-01T18:55:48.771710+00:00`
* **Execution Duration**: 26 minutes 24 seconds.
* **Permanent Budget Transition**:
  * At the instant the first real Fold-01 snapshot was processed, diagnostic slot 5 was permanently consumed.
  * **Diagnostics**: `5 / 12`
  * **Strategy Variants**: `3 / 8`
  * **Numeric Parameter Trials**: `0 / 4`
  * **Upward Revision Lock**: `ACTIVE`
  * **Tier B**: `SEALED`
  * **V004**: `NOT CREATED`

---

## 4. V003 Baseline Reproduction & First Identity Seals

The D006 execution harness reproduced the exact canonical V003 evaluation loop over all 13,269 scheduled snapshots with zero state reset or mutation.

* **Baseline Reproduction Status**: `SEALED_V003_BASELINE_RECONCILED`
* **Upstream Reconciliation Contract**: `EXACT_COUNT_RECONCILED_FIRST_IDENTITY_SEALED_BY_D006`
* **Candidate Reconciliation Contract**: `EXACT_DECISION_ID_AND_SETUP_ID_SET_EQUALITY`

### Upstream Stage Counts Reconciled
* **Gate-11 Entrants**: `526` (prior: 526, match: `True`)
* **V003 Gate-11 Passers**: `138` (prior: 138, match: `True`)
* **Canonical-Strategy Passers**: `110` (prior: 110, match: `True`)
* **Candidate Ready Decisions**: `81` (prior: 81, match: `True`)

### Candidate Identity Reconciliation
* **Candidate Count**: `81`
* **Unique Setup IDs**: `81`
* **Duplicate Setup IDs**: `0`
* **Multiset Pair Equality**: `sorted([(d_id, setup_id)])` matches prior sealed V003 R001 candidate list identically (`matches_prior_v003 = True`).

### First-Sealed Identity Digests (SHA-256 over newline-separated sorted decision IDs)
* `gate11_entrants_sha256`: `8612bad49dc18c7a41307c14a5c2ae349e3836f27b6bc31b3737dc7f43c78abc` (`FIRST_IDENTITY_SEALED_BY_D006`)
* `gate11_passers_sha256`: `84f5e6a5e1e38eec686aed9a6121d414ee48125297c0330781d2a57b49b3e1b0` (`FIRST_IDENTITY_SEALED_BY_D006`)
* `canonical_strategy_passers_sha256`: `21d64d470c34f29595c9026df188a8a03f373fd29727225a633e50c69c9b98e8` (`FIRST_IDENTITY_SEALED_BY_D006`)
* `candidate_ready_sha256`: `a4f4e885fe0c6be51a4a708c5a8b9b44cf1ed9da2d5aedbd31f13044d1e990d5`
* `p_entry_reject_sha256`: `c52009ac64813c009cff1f09917b921d20767d9dfebc5d16b50bc0f0fe541eb1`

---

## 5. Decision Accounting & Entry-Stage Population Partition

### Decision Accounting
* **Scheduled Snapshots**: `13,269`
* **Reducer Classified**: `7,316`
* **Missing History**: `4,815`
* **Unavailable Input**: `1,138`
* **Evaluation Error**: `0`
* **Reconciles**: `7316 + 4815 + 1138 + 0 == 13269` (`True`)

### Gate-11 Entrant Partition
The 526 decisions that reached frozen Gate 11 partition pairwise disjointly:
* **`R_GATE11_FAIL`**: `388` (Gate-11 entrants failing V003 8/8 confluence score)
* **`R_STRATEGY_REJECT`**: `28` (Gate-11 passers failing unchanged canonical strategy protections: 23 high volatility, 2 regime direction conflict, 3 DXY conflict)
* **`R_READY`**: `81` (Canonical-strategy passers with frozen `determine_entry` returning valid entry)
* **`P_ENTRY_REJECT`**: `29` (Canonical-strategy passers with frozen `determine_entry` returning None)
* **Partition Sum**: `388 + 28 + 81 + 29 = 526` (`partition_reconciles = True`)

---

## 6. Primary Population `P_ENTRY_REJECT` Identity

The primary diagnostic population `P_ENTRY_REJECT` was derived naturally through live replay without hardcoding:
* **Definition**: `v003_gate11_passed == True and v003_strategy_eligible == True and not v003_entry_ready`
* **Observed Count**: `29`
* **Unique Decision IDs**: `29`
* **Duplicates**: `0`
* **Exact Set Identity**: `P_ENTRY_REJECT IDs == canonical_strategy_pass_set - candidate_ready_set` (`True`)
* **Digest (`p_entry_reject_sha256`)**: `c52009ac64813c009cff1f09917b921d20767d9dfebc5d16b50bc0f0fe541eb1`

---

## 7. FVG Source Stratification

Every stage population is stratified by FVG evidence source (`FINAL_SURFACE` vs `TEMPORAL_MEMORY` vs `NONE`):

| Population Stage | FINAL_SURFACE | TEMPORAL_MEMORY | NONE | Total |
| :--- | :---: | :---: | :---: | :---: |
| **`R_GATE11_FAIL`** | 8 | 61 | 319 | 388 |
| **`R_STRATEGY_REJECT`** | 22 | 6 | 0 | 28 |
| **`R_READY`** | 61 | 20 | 0 | 81 |
| **`P_ENTRY_REJECT`** (Primary) | 19 | 10 | 0 | 29 |
| **Total Gate-11 Entrants** | 110 | 97 | 319 | 526 |

### Observations on Stratification
* In `P_ENTRY_REJECT` (29 decisions), 19 originate from `FINAL_SURFACE` and 10 from `TEMPORAL_MEMORY`.
* Both final-surface and temporal-memory FVG evidence suffer post-confluence entry-state attrition in roughly proportional measure to their presence among canonical-strategy passers (`19/80 = 23.8%` of final-surface strategy passers vs `10/30 = 33.3%` of temporal-memory strategy passers are rejected at `determine_entry`).

---

## 8. E1–E5 Rejection Taxonomy & Distribution

Every decision in `P_ENTRY_REJECT` was classified using the frozen, ordered deterministic classifier matching production `determine_entry`:

| Category | Description | Primary Count | Share | FINAL_SURFACE | TEMPORAL_MEMORY |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **E1** | `STATE_EXPIRED` (`state.is_expired()`) | 0 | 0.0% | 0 | 0 |
| **E2** | `READINESS_INCOMPLETE` (`ready_for_entry() == False` & `not early_entry_ok`) | 7 | 24.1% | 7 | 0 |
| **E3** | `STRUCTURE_DIRECTION_UNRESOLVED` (direction not in bullish/bearish) | 0 | 0.0% | 0 | 0 |
| **E4** | `LIQUIDITY_ALIGNMENT_MISMATCH` (direction/side/type invalid) | 22 | 75.9% | 12 | 10 |
| **E5** | `UNMAPPED_ENTRY_REJECTION` (unmapped failure) | 0 | 0.0% | 0 | 0 |
| **Total** | | **29** | **100.0%** | **19** | **10** |

* **Zero Unmapped Rejections**: $E_5 = 0$. All 29 primary rejections map completely to preregistered frozen categories.
* **Zero State Expirations**: $E_1 = 0$. All 29 decisions occurred with fresh strategy state (age = 0.0 min).
* **Zero Unresolved Directions**: $E_3 = 0$. All decisions had resolved market structure direction (15 bullish, 14 bearish).

---

## 9. State Expiry Surface

* **Frozen Expiry Threshold**: `120 minutes`
* **Active States**: `29` (100.0%)
* **Expired States**: `0` (0.0%)
* **Age Distribution**: min = 0.0 min, median = 0.0 min, max = 0.0 min, P25 = 0.0, P50 = 0.0, P75 = 0.0.
* State expiry is completely ruled out as a source of entry attrition in Fold 01.

---

## 10. Ready-for-Entry State Surface & Missing Conditions

Evaluation of `ready_for_entry()` across all 29 primary decisions:
* **`ready_for_entry() == True`**: 1 decision
* **`ready_for_entry() == False`**: 28 decisions

### Missing Conditions Distribution
* **`Confirmed structure`**: `28` / 29 (96.6%)
* **`Daily limit clear`**: `0` / 29
* **`Displacement / FVG`**: `0` / 29
* **`Liquidity sweep`**: `0` / 29
* **`News clear`**: `0` / 29

### Missing Condition Co-occurrences
* **`Confirmed structure` alone**: `28`
* **`None` (all conditions met)**: `1`

The sole condition missing in `ready_for_entry()` is `Confirmed structure`: in 28 decisions, the structure state is in `transition` rather than `confirmed`.

---

## 11. Early-Entry Surface Decomposition

Because score is 8 and `ready_for_entry()` failed on 28 decisions, `determine_entry` evaluated the frozen score-8 conservative early-entry pathway:
* **Score Context**: 8
* **Entry Mode**: conservative
* **`score_eligible_early` (score >= 8)**: 29 / 29
* **`missing_set_eligible_early` (missing == {"Confirmed structure"})**: 29 / 29
* **`structure_state_early_eligible` (structure_state in {"choch", "transition"})**: 28 / 29
* **`has_zone_context` (`live_ob_zone` or `live_fvg_zone`)**: 29 / 29
* **`has_priority_context` (within London/NY priority windows)**: 29 / 29
* **`has_internal_confirmation` (`internal_bos_seen` or `choch_seen`)**: 22 / 29
* **Final `early_entry_ok`**: `21` / 29

### Early-Entry Outcome
* In **21 of the 28** decisions lacking confirmed structure, conservative early entry was **authorized** (`early_entry_ok == True`).
* In the remaining **7 decisions**, early entry failed because internal confirmation was missing (`has_internal_confirmation == False`), resulting in rejection category **E2 (`READINESS_INCOMPLETE`)**.
* For the 21 decisions where early entry succeeded (plus the 1 decision where `ready_for_entry()` was True, total 22), execution proceeded to liquidity alignment evaluation.

---

## 12. Structure & Liquidity Alignment Surface

All 22 decisions that passed readiness evaluation (21 via early entry + 1 via full readiness) reached liquidity alignment evaluation:
* **Structure Direction Distribution**:
  * `bullish`: 15
  * `bearish`: 14
* **Liquidity Side Distribution**:
  * `sell`: 21
  * `buy`: 8
* **Liquidity Type Distribution**:
  * `internal_continuation`: 28
  * `equal_lows`: 1

### Complete Contingency Table (`structure_dir × liquidity_side × liquidity_type`)

| Direction | Liquidity Side | Liquidity Type | Count | Alignment Status | Subsequent Outcome |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `bullish` | `sell` | `internal_continuation` | 14 | **INVALID** | **E4 Rejection** |
| `bearish` | `buy` | `internal_continuation` | 7 | **VALID** | Failed readiness (E2: 7) |
| `bearish` | `sell` | `internal_continuation` | 6 | **INVALID** | **E4 Rejection** |
| `bearish` | `sell` | `equal_lows` | 1 | **INVALID** | **E4 Rejection** |
| `bullish` | `buy` | `internal_continuation` | 1 | **VALID** | Full ready, passed E4 |

### Liquidity Alignment Summary
* **Valid Alignment**: 7 decisions (all 7 failed readiness under E2).
* **Invalid Alignment**: **22 decisions** (all 22 rejected under category **E4 (`LIQUIDITY_ALIGNMENT_MISMATCH`)**).
* The 22 invalid alignment decisions break down into:
  1. `bullish x sell x internal_continuation`: **14** (63.6% of E4; bullish direction with sell-side internal continuation, whereas bullish requires buy-side internal continuation or sell-side external equal lows).
  2. `bearish x sell x internal_continuation`: **6** (27.3% of E4; bearish direction with sell-side internal continuation, whereas bearish requires sell-side internal continuation or buy-side external equal highs).
  3. `bearish x sell x equal_lows`: **1** (4.5% of E4; bearish direction with sell-side equal lows, whereas bearish requires buy-side sweep).
  4. (Plus 1 internal continuation mismatch).

---

## 13. Protected Strategy-Rejection Context

* **`R_STRATEGY_REJECT` Count**: `28`
* **Distribution**:
  * `StrategyReason.REGIME_HIGH_VOLATILITY`: 23
  * `StrategyReason.DXY_DIRECTION_CONFLICT`: 3
  * `StrategyReason.REGIME_DIRECTION_CONFLICT`: 2
* **Governance Note**: PROTECTED-POLICY CONTEXT ONLY. These 28 decisions passed V003 Gate 11 but failed canonical risk protections. They are never treated as V004 candidate headroom.

---

## 14. Descriptive Concentration Metrics

* **Dominant Rejection Category**: `LIQUIDITY_ALIGNMENT_MISMATCH` (E4)
* **Dominant Category Count**: `22` / 29
* **Dominant Category Share**: `75.86%`
* **Top-Two Rejection Categories**: `LIQUIDITY_ALIGNMENT_MISMATCH` (22) + `READINESS_INCOMPLETE` (7)
* **Top-Two Count**: `29` / 29
* **Top-Two Share**: `100.0%`
* **Category × FVG-Source Breakdown**:
  * E4 (`LIQUIDITY_ALIGNMENT_MISMATCH`): 12 FINAL_SURFACE + 10 TEMPORAL_MEMORY = 22
  * E2 (`READINESS_INCOMPLETE`): 7 FINAL_SURFACE + 0 TEMPORAL_MEMORY = 7

---

## 15. H008 Pending Supervisory Interpretation

Under the preregistered TC001/TC002 contract, because $E_5 = 0$ and primary count > 0:
* **Tooling Output Disposition**:
  `proposed_disposition = "H008_SUPERVISORY_INTERPRETATION_REQUIRED"`
* **Decision Rule Applied**:
  "When E5 = 0 and primary_count > 0, proposed_disposition is H008_SUPERVISORY_INTERPRETATION_REQUIRED with descriptive concentration metrics; support or non-support must never be automatically assigned by a numerical percentage. INCONCLUSIVE_D006 if unmapped rejections (E5 > 0) occur, primary population is zero, or baseline fails."
* **Status in Register**:
  `phase8-v2-H008` remains **OPEN** with result `phase8-v2-D006-R001` attached. Final scientific disposition (`SUPPORTED_BY_D006` vs `NOT_SUPPORTED_BY_D006`) awaits independent supervisory review.

---

## 16. What D006 Establishes

1. **Rejection Concentration**: Post-confluence entry-state attrition in V003 on Fold 01 is not diffuse; it is concentrated in two categories (E4 accounting for 75.9%, E2 accounting for 24.1%, totaling 100.0%).
2. **Liquidity Alignment Bottleneck**: The predominant obstacle to trade entry after confluence is liquidity alignment mismatch (22 decisions), predominantly `bullish x sell x internal_continuation` (14 decisions).
3. **Internal Confirmation Bottleneck**: State readiness failure (7 decisions) is driven exclusively by lack of internal BOS/CHOCH confirmation when market structure is in transition.
4. **Total State Freshness**: State expiry ($E_1$) is completely non-contributory (0 decisions).
5. **Exact Production Agreement**: Every rejection maps to frozen production behavior ($E_5 = 0$).

---

## 17. What D006 Does NOT Establish

1. **No Rule Relaxation Justified**: D006 does not establish that relaxing liquidity alignment or structure confirmation rules is desirable, safe, or economically sound.
2. **No Counterfactual Claim**: D006 does not simulate what trades would have executed or what performance would have resulted had rules been different.
3. **No Profitability Evidence**: D006 produces zero P&L, Sharpe, win rate, or return metrics.
4. **No V004 Authorization**: D006 does not authorize, design, or implement V004.
5. **Tier B Remains Sealed**: D006 does not evaluate or touch Folds 02–04, 2025+ data, or holdout.

---

## 18. Budget & Governance Status

* **Diagnostics Executed**: `5 / 12` (Slot 5 permanently consumed by this empirical execution).
* **Strategy Variants Observed**: `3 / 8` (Unchanged; V001, V002, V003).
* **Numeric Parameter Trials**: `0 / 4` (Unchanged).
* **Upward Revision Lock**: `ACTIVE`.
* **Tier B**: `SEALED`.
* **V004 Status**: `NOT_CREATED` — Tier B remains sealed. Supervisory H008/D006 interpretation required before any subsequent variant proposal.
