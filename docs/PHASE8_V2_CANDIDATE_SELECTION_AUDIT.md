# Phase 8 V2 — Tier-A Candidate Selection Audit

**Document Identity:** `phase8-v2-candidate-selection-audit-v1`
**Classification:** `POST_RESULT_GOVERNANCE_AUDIT — SEALED_TIER_A_RESULT_ONLY — NOT_NEW_STRATEGY_TRIAL`
**Governing Charter:** `phase8-v2-research-charter-v1-8527e3a5eec98f53` (Charter §14 Candidate Selection & Charter §17 Freeze Criteria)
**Primary Evaluated Variant:** `phase6-development-v2-V005` (*Eligibility-Scoped Requested-Side Entry Direction Authority*)
**Primary Evaluated Result:** `phase6-development-v2-V005-R001` (External JSON: `phase6-development-v2-V005_result.json`, SHA-256 `27b8849eb97074d55c36bf11645cae8821d517b1f9e52e0c9a37976c77abcbfe`, 80,554 bytes)
**Audit Purpose:** Comprehensive Charter §14 evaluation of candidate density, temporal stability, causal integrity, economic coherence, and architectural safety on contaminated Tier-A Fold 01, culminating in a provisional candidate-selection recommendation prior to Charter §17 freeze authorization.

---

## A. Evidence Boundary

This audit operates strictly as a read-only post-result governance inspection under the following strict boundaries:
1. **Primary Empirical Source:** The audit analyzes the already-sealed, immutable `phase6-development-v2-V005-R001` external result JSON artifact.
2. **Permitted Governance Inputs:** Committed V005 specification (`docs/PHASE8_V2_VARIANT_V005.md`), committed V005 implementation (`bot/strategy/variant_v005.py`), committed evaluator tooling (`backtests/phase8_v2_variant_v005_eval.py`), Research Charter (`docs/PHASE8_V2_RESEARCH_CHARTER.md`), hypothesis register (`baseline/phase8_v2_hypothesis_register.json`), V004 blockage records, and V003 sealed baseline evidence.
3. **Prohibited Actions:**
   - ZERO strategy replay or re-execution.
   - ZERO opening or re-reading of the Fold-01 feature store (`fold-01-a8b406884ab3525a`).
   - ZERO access to out-of-sample Tier-A folds (Fold 02, Fold 03, Fold 04).
   - ZERO access to Tier-B holdout or post-2024 calendar data.
   - ZERO profitability, win-rate, Sharpe, drawdown, or trade outcome calculations.
   - ZERO budget consumption (diagnostics remain `5 / 12`, variants remain `5 / 8`, numeric trials remain `0 / 4`).

---

## B. V005 R001 Accepted Evidence Identity

The empirical findings of `phase6-development-v2-V005-R001` are accepted under supervisory review:
- **Variant ID:** `phase6-development-v2-V005`
- **Specification SHA-256:** `7f4972f36bd99f550c142741c1c3065db6ca1fc6d1f041858cf141ebd9477e35` (Git blob `d127d3b45b54135038698b1cebe540a0f43a0c20`)
- **Implementation Blob SHA:** `3820c6c66f96c91d98b47feda0e4f5f88aa5c70a` (fingerprint `717dc07aff63d0150fbd47de036e81bd12e270c4a5de31f78f5fc48dc998fd2f`)
- **Evaluator Tooling Blob SHA:** `6291999b059facadf6ea40482f8413872cf4cd23` (fingerprint `dd4d864e6caf3413447121bac9bc412c1db7a8df6243422840e0e5d59ca26683`)
- **External Result File:** `C:/Users/chips/forex-signal-bot-data/phase8/v2_variants/phase6-development-v2-V005/fold01/phase6-development-v2-V005_result.json`
- **Artifact SHA-256:** `27b8849eb97074d55c36bf11645cae8821d517b1f9e52e0c9a37976c77abcbfe` (80,554 bytes)
- **Accepted Empirical Surface:**
  - Scheduled snapshots: `13,269`
  - Reducer classified: `7,316` (missing history: 4,815; unavailable input: 1,138; errors: 0)
  - Gate-11 entrants: `526`
  - Gate-11 passes (8/8): `138` (26.24%)
  - Canonical strategy passes: `110` (79.71%)
  - Gate 12/13 entry readiness: `102` (92.73%)
  - Raw `candidate_ready`: **`102`** (Candidate rate: `0.193916`)
  - Candidate sources: `81` `V003_BASELINE` + `21` `V005_DIRECTIONAL_FALLBACK` = `102`
  - Unique setup IDs: `102` (0 duplicate setup ID occurrences; `102 + 0 == 102`)
  - Directional distribution: `55` LONG / `47` SHORT (Fallback: 7 BUY / 14 SELL, 100% agreement with `requested_side`)
  - Sealed V003 baseline reproduction: 100% (81/81 candidates preserved with exact multiset identity and deterministic entry JSON equality)
  - Formal outcome classification: **`OPPORTUNITY_SUFFICIENT`** (102 >= 90 target)

---

## C. V005 RC001 Narration Correction

Governance record `phase6-development-v2-V005-RC001` formally corrects Section 8 of `docs/PHASE8_V2_VARIANT_V005_RESULT.md`:
1. The Gate 12/13 non-passing count remains exactly **`8`** (`110 entered - 102 passed = 8 failed`).
2. Exactly **`7`** rejections are established by sealed evidence as preserved D006 E2 readiness failures lacking internal confirmation under frozen score-8 conservative early entry.
3. The historical description of the eighth rejection as "entry geometry / RR parameters" is formally **WITHDRAWN** because frozen score-8 `determine_entry` contains no post-readiness RR/geometry rejection gate, and V005 R001 did not seal reason-level predicates for non-candidates.
4. The eighth rejection mechanism is formally classified as **`NOT_ESTABLISHED_BY_V005_R001`**. Store re-inspection or replay is prohibited.

---

## D. H009 Supervisory Disposition

Governance record `phase8-v2-H009-R001` records the formal supervisory resolution of hypothesis `phase8-v2-H009-TC001`:
* **Disposition:** **`SUPPORTED_BY_V005`**
* **Formal Qualification:** `SUPPORTED_STRUCTURALLY_ON_CONTAMINATED_TIER_A — RESERVED_FOLD_CONFIRMATION_PENDING — NOT_PROFITABILITY_EVIDENCE`
* **Scientific Support Basis:**
  1. *Complete Baseline Preservation:* All 81 V003 baseline candidates reproduced with bit-for-bit entry object parity.
  2. *Empirical Opportunity Recovery:* Unifying Gate-12/13 direction authority with requested trade side unlocks 21 incremental candidate setups.
  3. *Density Target Exceeded:* Total raw candidate count reaches 102, exceeding the governing charter target of 90.
  4. *Directional Coherence:* 21 / 21 fallback entries exhibit 100% directional agreement with `requested_side`.
  5. *Zero Structural Weakening:* No liquidity combinations broadened, no readiness rules relaxed, zero numeric parameter trials consumed, and zero risk protections bypassed.

---

## E. Strategy Variant Candidate Pool Review

Charter §14 dictates that candidate selection must evaluate holistic structural, causal, and safety criteria, explicitly rejecting naive `argmax(candidate_count)` optimization:

| Variant | Conceptual Mechanism | Raw Candidates | Opportunity Classification | Candidate Selection Disposition |
|---|---|---|---|---|
| **V001** | First-FVG Geometry | 12 | `OPPORTUNITY_INSUFFICIENT` | **DISCONTINUED** — Insufficient opportunity density. |
| **V002** | Final-Surface FVG Association | 61 | `OPPORTUNITY_INSUFFICIENT` | **DISCONTINUED** — Substantial progress (+49), but falls short of 90 target. |
| **V003** | Temporal FVG Evidence Memory | 81 | `OPPORTUNITY_INSUFFICIENT` | **DISCONTINUED** — Rescued 20 setups (+20), but 81 < 90 target. |
| **V004** | Unified Direction Authority | 0 (Blocked) | `IMPLEMENTATION_BLOCKED` | **CLOSED** — Premature fail-closed guard defect on pre-structural FLAT pairs; zero observations completed. |
| **V005** | Scoped Direction Authority | 102 | `OPPORTUNITY_SUFFICIENT` | **CANDIDATE UNDER AUDIT** — Minimal sound extension of V003 achieving density adequacy (102 >= 90). |

---

## F. Temporal Candidate Distribution

Descriptive metrics derived strictly from the sealed candidate records (`available_at_ms`) in `phase6-development-v2-V005_result.json`:

* **Temporal Coverage Boundaries:**
  - Earliest Candidate: `2024-04-01T00:10:00+00:00`
  - Latest Candidate: `2024-06-07T14:35:00+00:00`
  - Fold-01 Start: `2024-04-01T00:00:00+00:00`
  - Fold-01 Midpoint: `2024-05-05T00:00:00+00:00`
  - Fold-01 End: `2024-06-08T00:00:00+00:00`
* **Partition Across Fold Halves:**
  - First Half (`2024-04-01` to `< 2024-05-05`): **`68`** candidates (66.7%)
  - Second Half (`2024-05-05` to `2024-06-08`): **`34`** candidates (33.3%)
* **Calendar Day Distribution:**
  - Occupied Calendar Days: `15` days
  - Maximum Candidates in One Day: `26` (2024-04-01, opening day volatility)
  - Median Candidates per Occupied Day: `5.0`
  - Mean Candidates per Occupied Day: `6.80`
  - Longest Gap Between Occupied Days: `11` days (`2024-04-12` to `2024-04-23`)
  - Longest Elapsed Time Gap Between Consecutive Setups: `11.58` days (`2024-05-24T00:10:00Z` to `2024-06-04T14:00:00Z`)
* **7-Day Bin Distribution (Anchored at `2024-04-01T00:00:00Z`):**
  - Bin 00 (`2024-04-01` to `2024-04-08`): `35`
  - Bin 01 (`2024-04-08` to `2024-04-15`): `2`
  - Bin 02 (`2024-04-15` to `2024-04-22`): `0`
  - Bin 03 (`2024-04-22` to `2024-04-29`): `11`
  - Bin 04 (`2024-04-29` to `2024-05-06`): `20`
  - Bin 05 (`2024-05-06` to `2024-05-13`): `1`
  - Bin 06 (`2024-05-13` to `2024-05-20`): `6`
  - Bin 07 (`2024-05-20` to `2024-05-27`): `24`
  - Bin 08 (`2024-05-27` to `2024-06-03`): `0`
  - Bin 09 (`2024-06-03` to `2024-06-08`): `3`
  - Maximum Candidates in One 7-Day Bin: `35`
  - Longest Consecutive Empty 7-Day Bin Streak: `1` bin (Bin 02 and Bin 08 are isolated empty intervals)

---

## G. Source-Stratified Temporal Distribution

To verify that the 21 V005 directional fallback recoveries are not concentrated in a single anomalous day, the candidate population is stratified across time:

### G.1 Calendar Day Stratification

| Date (UTC) | Total Candidates | V003 Baseline | V005 Fallback | LONG Setups | SHORT Setups |
|---|---|---|---|---|---|
| `2024-04-01` | 26 | 26 | 0 | 26 | 0 |
| `2024-04-02` | 6 | 6 | 0 | 6 | 0 |
| `2024-04-04` | 3 | 3 | 0 | 3 | 0 |
| `2024-04-12` | 2 | 2 | 0 | 2 | 0 |
| `2024-04-23` | 1 | 0 | **1** | 1 | 0 |
| `2024-04-24` | 10 | 0 | **10** | 0 | 10 |
| `2024-04-29` | 6 | 0 | **6** | 6 | 0 |
| `2024-04-30` | 14 | 11 | **3** | 0 | 14 |
| `2024-05-07` | 1 | 0 | **1** | 0 | 1 |
| `2024-05-17` | 6 | 6 | 0 | 6 | 0 |
| `2024-05-20` | 5 | 5 | 0 | 5 | 0 |
| `2024-05-23` | 16 | 16 | 0 | 0 | 16 |
| `2024-05-24` | 3 | 3 | 0 | 0 | 3 |
| `2024-06-04` | 1 | 1 | 0 | 0 | 1 |
| `2024-06-07` | 2 | 2 | 0 | 0 | 2 |
| **Total** | **102** | **81** | **21** | **55** | **47** |

### G.2 ISO Week Stratification

| ISO Week | Total Candidates | V003 Baseline | V005 Fallback | LONG Setups | SHORT Setups |
|---|---|---|---|---|---|
| `2024-W14` | 35 | 35 | 0 | 35 | 0 |
| `2024-W15` | 2 | 2 | 0 | 2 | 0 |
| `2024-W17` | 11 | 0 | **11** | 1 | 10 |
| `2024-W18` | 20 | 11 | **9** | 6 | 14 |
| `2024-W19` | 1 | 0 | **1** | 0 | 1 |
| `2024-W20` | 6 | 6 | 0 | 6 | 0 |
| `2024-W21` | 24 | 24 | 0 | 5 | 19 |
| `2024-W23` | 3 | 3 | 0 | 0 | 3 |
| **Total** | **102** | **81** | **21** | **55** | **47** |

### G.3 Findings on Fallback Dispersion
- Fallback candidates are distributed across **5 separate calendar days** (`2024-04-23`, `2024-04-24`, `2024-04-29`, `2024-04-30`, `2024-05-07`) in **3 distinct ISO weeks** (`W17`, `W18`, `W19`).
- Fallback recoveries activate during periods where HTF directional momentum diverged from persisted structure state, capturing both bullish continuation (7 BUY) and bearish continuation (14 SELL).
- Fallback additions seamlessly interleave with baseline candidates, confirming that V005 acts as a general structural authority correction rather than an isolated micro-burst anomaly.

---

## H. Session Distribution

Canonical session classifications were derived directly from candidate timestamps (`available_at_ms`) and frozen static configurations (`bot.strategy.config.StrategyConfig`), completely avoiding any feature-store access.

### H.1 Strategy Engine Session Classification (`bot.strategy.sessions.evaluate_session`)

| Session Category | Total Candidates | V003 Baseline | V005 Fallback | LONG Setups | SHORT Setups |
|---|---|---|---|---|---|
| `london` | **29** | 13 | **16** | 8 | 21 |
| `new_york` | **15** | 14 | **1** | 12 | 3 |
| `off_priority` | **58** | 54 | **4** | 35 | 23 |
| **Total** | **102** | **81** | **21** | **55** | **47** |

### H.2 Production Clock Session Classification (`bot.utils.session_clock.get_active_session`)

| Window Name | Total Candidates | V003 Baseline | V005 Fallback | LONG Setups | SHORT Setups |
|---|---|---|---|---|---|
| `london` (07:00–10:00 UTC) | **29** | 13 | **16** | 8 | 21 |
| `new_york` (12:30–15:00 UTC) | **15** | 14 | **1** | 12 | 3 |
| `asian` (00:00–06:00 UTC) | **35** | 31 | **4** | 28 | 7 |
| `off_session` (Other UTC) | **23** | 23 | **0** | 7 | 16 |
| **Total** | **102** | **81** | **21** | **55** | **47** |

### H.3 Session Dispersion Assessment
- Candidates are well-dispersed across sessions: Priority liquidity sessions (London + New York) account for `44` candidates (43.1%), Asian session accounts for `35` candidates (34.3%), and off-session hours account for `23` candidates (22.5%).
- V005 directional fallback recoveries show pronounced concentration in the London session (`16 / 21` = 76.2%), reflecting the high frequency of London breakout continuations where higher-timeframe order flow overrides stale Asian structure.

---

## I. LONG / SHORT Balance

* **Candidate Direction Breakdown:**
  - LONG Setups: `55` (53.92%)
  - SHORT Setups: `47` (46.08%)
* **Source Stratification:**
  - V003 Baseline: `48` LONG / `33` SHORT (59.3% / 40.7%)
  - V005 Fallback: `7` BUY / `14` SELL (33.3% / 66.7%)
* **Balance Evaluation:** The 55/47 distribution is remarkably balanced for a 68-day market regime in XAUUSDm, showing no degenerate single-direction bias. The fallback mechanism provided complementary short opportunities, improving overall portfolio equilibrium.

---

## J. Charter §14 Criterion-by-Criterion Assessment

### 1. Economic Coherence: **PASS**
* **Rationale:** V005 directly addresses the structural mismatch identified in diagnostic D006: when Gate-11 confluence achieves 8/8 confirmation under higher-timeframe bias (`htf_bias`), evaluating Gate 12/13 entry alignment against a stale, un-updated `state.structure_dir` creates an artificial internal conflict. Gating Gate-12/13 alignment to the authoritative requested trade direction aligns entry logic with upstream market structure.

### 2. Causal Correctness: **PASS**
* **Rationale:** Evaluated strictly over frozen historical market feature stores using indexed causal replay (`verify_rows=True`). No forward-looking data or future leakage is introduced. Authoritative `StrategyState` remains completely immutable; directional authority is applied exclusively on a private copy (`copied_state.structure_dir = req_side`). Sealed V003 baseline is 100% reproduced bit-for-bit.

### 3. Code Simplicity: **PASS**
* **Rationale:** Relative to frozen V003, V005 introduces exactly one conceptual change: eligibility-scoped directional authority. V005 avoids the unconditional over-reach of blocked V004 by evaluating pair consistency only on fallback-eligible decisions. It represents the minimal sufficient semantic delta required to achieve opportunity adequacy.

### 4. Opportunity Sufficiency: **PASS**
* **Rationale:** Mechanical evaluation against the Research Charter adequacy threshold: raw `candidate_ready = 102 >= 90`. Opportunity density is sufficient for Tier-A Fold 01.

### 5. Temporal Stability: **PASS**
* **Rationale:** As documented in Sections F and G, candidates occur across 15 distinct calendar days spanning April, May, and June 2024. Fallback recoveries occur across 5 days in 3 separate weeks. No single 7-day bin contains more than 35 candidates, and empty intervals are isolated to 1 bin. Candidates exhibit realistic clustering around market volatility regimes without pathological single-day collapse.

### 6. Long/Short Balance: **PASS**
* **Rationale:** Total candidate distribution is 55 LONG and 47 SHORT (53.9% / 46.1%), representing an exceptional directional equilibrium without artificial parameter forcing.

### 7. Limited Complexity Increase: **PASS**
* **Rationale:** V005 adds zero numeric parameters (0 / 4 numeric parameter trials consumed). It introduces no new indicators, no new machine learning models, no new filter rules, and relaxes no existing liquidity constraints.

### 8. Protected Safety Architecture: **PASS**
* **Rationale:** All Charter §5 protected infrastructure remains fully active and unbypassed:
  - Causal candle construction is intact.
  - Lifecycle state machine and setup consumption tracking are unaltered.
  - Account-level risk limits, broker safety controls, and drawdown protection are untouched.
  - Exness broker spread, commission, and rollover guards are maintained.
  - News fail-closed filters and high-volatility regime gates remain in full effect.

---

## K. Candidate Selection Recommendation

Because all eight Charter §14 criteria are evaluated as **PASS**, the provisional candidate selection recommendation is:

> **`SELECT_PHASE6_DEVELOPMENT_V2_V005_AS_SINGLE_FREEZE_CANDIDATE`**

* **Selected Implementation Identity:**
  - Canonical Freeze Commit: `2fd3460b9010d8cca548f4fd6980b6b34fe594e2`
  - Strategy Module: `bot/strategy/variant_v005.py`
  - Committed Git Blob SHA: `3820c6c66f96c91d98b47feda0e4f5f88aa5c70a`
  - Canonical Fingerprint SHA-256 (`canonical_git_blob_v1`): `717dc07aff63d0150fbd47de036e81bd12e270c4a5de31f78f5fc48dc998fd2f`

---

## L. Charter §17 Pre-Freeze Readiness Checklist

Charter §17 sets out 14 mandatory conditions that must be verified before executing a formal candidate freeze (`phase6-frozen-v2`). Current readiness status for each item:

| Item | Charter §17 Requirement | Current Status | Notes / Preconditions |
|---|---|---|---|
| **1** | Research budget & stopping condition | **READY** | 5/12 diagnostics, 5/8 variants, 0/4 numeric trials; stopping condition met (`candidate_ready >= 90`). |
| **2** | Single candidate selected under §14 | **READY** | V005 selected under §14 audit with 8/8 PASS. |
| **3** | Implementation review complete | **READY** | `bot/strategy/variant_v005.py` verified; clean fail-closed scoped guard. |
| **4** | Strategy semantics documented | **READY** | Fully documented in `docs/PHASE8_V2_VARIANT_V005.md` and result doc. |
| **5** | Complete configuration frozen | **REQUIRES_NEXT_TASK** | Strategy configuration and entry parameters must be formally locked for production freeze. |
| **6** | Test suite status | **READY** | 18 variant tests + 20 tooling tests passed; historical regression battery clean. |
| **7** | Semantic ambiguity resolved | **READY** | V005-RC001 resolved the Gate 12/13 eighth rejection narration ambiguity. |
| **8** | Exact Git commit identified | **READY** | Committed at `2fd3460b9010d8cca548f4fd6980b6b34fe594e2`. |
| **9** | Canonical fingerprints verified | **READY** | Git blob SHA `3820c6c6` and SHA-256 `717dc07a` verified against committed bytes. |
| **10** | Prospective contract guard in place | **REQUIRES_NEXT_TASK** | Freeze governance document must assert prospective freeze invariants. |
| **11** | Hypothesis/trial ledger up to date | **READY** | H009-R001, V005-RC001, and selection audit appended to ledger. |
| **12** | Contamination ledger explicit | **READY** | Fold 01 explicitly recorded as contaminated development set. |
| **13** | Holdout exposure status verified | **READY** | Holdout and 2025+ data verified untouched and strictly sealed. |
| **14** | Explicit supervisory authorization | **REQUIRES_NEXT_TASK** | Awaits supervisory review and explicit authorization to create `phase6-frozen-v2`. |

---

## M. What Remains Before `phase6-frozen-v2`

Under Charter §17 and Section 23 of the task instructions, **NO FREEZE IS EXECUTED IN THIS TASK**.
Before `phase6-frozen-v2` can be created, the following actions must occur in a separately authorized task:
1. Supervisory review and formal acceptance of this Candidate Selection Audit.
2. Formal supervisory authorization to transition `phase6-development-v2-V005` into `phase6-frozen-v2`.
3. Publication of the canonical freeze manifest and configuration lock.
4. Preregistration of the prospective Tier-B evaluation plan before unsealing any reserved folds.

---

## N. Reserved Evidence Status

* **Tier-A Folds 02–04:** Strictly **SEALED** and unopened.
* **Tier-B Holdout Dataset:** Strictly **SEALED** and unopened.
* **Post-2024 Data (2025+):** Strictly **SEALED** and unopened.
* **Integrity Guarantee:** Zero empirical observations have occurred outside of authorized Tier-A Fold 01.

---

## O. Audit RC001 Clarification — Fallback Concentration Nuance & Risk Flag

**Governance Reference:** `phase8-v2-candidate-selection-audit-v1-RC001`
**Classification:** POST-RESULT GOVERNANCE QUALIFICATION — NO EMPIRICAL RETEST

### O.1 Criterion 5 Status
Charter §14 Criterion 5 (Temporal Stability) remains **PASS** for the **COMPLETE** V005 candidate surface.

* **Rationale:** The full 102-candidate surface spans both halves of Fold 01, covers April, May, and June 2024, spans multiple trading sessions (London, New York, Asian, off-session), and populates eight occupied ISO-week bins without single-day collapse.

### O.2 Fallback Concentration Nuance & Mandatory Risk Flag
While the overall candidate surface satisfies Criterion 5, fine-grained stratification of the 21 incremental V005 fallback recoveries reveals temporal and session clustering:

* **Fallback Candidate Count:** `21`
* **Fallback Active Days:** `5` distinct trading days
* **Weekly Distribution:**
  - W17: `11`
  - W18: `9`
  - W19: `1`
  - **Temporal Concentration:** `20 / 21` (95.2%) fallbacks occur within W17–W18; `20 / 21` occur in the first half of Fold 01.
* **Session Concentration:** `16 / 21` (76.2%) fallbacks occur during the London session.

Accordingly, the mandatory prospective risk flag is formally recorded:
> **`TIER_B_REGIME_CONCENTRATION_RISK`**

### O.3 Clarification of Interpretation
Supervisory review noted that interpreting the fallback distribution as confirming a general structural correction or proving the complete absence of regime concentration is too strong. Prospectively, the interpretation is clarified as:

> *V005 demonstrates the H009 mechanism on contaminated Tier-A Fold 01, but its incremental fallback contribution is temporally and session concentrated. This does not invalidate candidate-level §14 temporal stability, but persistence of the incremental mechanism across reserved periods is unestablished and must be treated as a Tier-B confirmation risk.*
