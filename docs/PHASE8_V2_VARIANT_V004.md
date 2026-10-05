# Phase 8 V2 Strategy Variant V004: Unified Requested-Side Entry Direction Authority

## 1. Specification Lineage & Research Scope

* **Variant Identifier**: `phase6-development-v2-V004`
* **Title**: Unified Requested-Side Entry Direction Authority
* **Classification**: `DEVELOPMENT_VARIANT_IMPLEMENTATION — V004 — NOT PROFITABILITY EVIDENCE`
* **Governing Research Charter**: `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
* **Linked Hypothesis**: `phase8-v2-H009` (*Entry Direction Authority Coherence*)
* **Predecessor Variant**: `phase6-development-v2-V003` (*Causal Temporal FVG Evidence Memory*)
* **Supporting Predecessor Evidence**:
  * `phase8-v2-D006-R001` (V003 Post-Confluence Entry-State Attrition Decomposition)
  * `phase8-v2-H008-R001` (`SUPPORTED_BY_D006`)
* **Status**: `REGISTERED_NOT_OBSERVED`
* **Target Domain**: Tier-A Fold 01 (`fold-01-a8b406884ab3525a`, `2024-04-01T00:00:00Z` to `2024-06-08T00:00:00Z`)
* **Reserved Evidence**: Folds 02–04, 2025+ data, and holdout remain strictly sealed and inaccessible.

---

## 2. Scientific Motivation & Empirical Basis

In V003 empirical evaluation (`phase6-development-v2-V003-R001`), Gate-11 confluence passes expanded from 102 to 138, and canonical strategy passes expanded from 80 to 110, yielding 81 candidate-ready decisions (against the Tier-A adequacy target of 90, classifying V003 as `OPPORTUNITY_INSUFFICIENT`).

Diagnostic `phase8-v2-D006` investigated the remaining 29 decisions that passed Gate-11 confluence and canonical strategy protections but were rejected at Gate-12/13 entry execution (`P_ENTRY_REJECT`). The empirical observation revealed:
1. **Zero Unmapped Failures**: $E_5 = 0$. All 29 primary rejections mapped to known frozen categories.
2. **Zero State Expirations**: $E_1 = 0$. All 29 states were completely active (age = 0.0 minutes).
3. **Zero Unresolved Directions**: $E_3 = 0$.
4. **Dominant Rejection Category**: **E4 (`LIQUIDITY_ALIGNMENT_MISMATCH`)** accounted for **22 / 29 (75.86%)** of all rejections.
5. **Secondary Category**: **E2 (`READINESS_INCOMPLETE`)** accounted for **7 / 29 (24.14%)** of rejections (where early-entry internal BOS/CHOCH confirmation was absent in transition structure).
6. **Dual Directional Authorities**: Code analysis and contingency decomposition revealed that `build_gate_inputs` calls `detect_liquidity_sweep(structure, structure_dir=htf_bias)`, emitting internal continuation liquidity relative to the selected higher-timeframe / requested trade direction. Concurrently, the gate reducer assigns `state.structure_dir` from `liquidity_context.structure_context.structure` (a separate local authority). When execution reaches `determine_entry`, the entry engine routes trade direction and validates liquidity alignment using `state.structure_dir` rather than the requested trade side, causing 21 decisions to fail due to conflicting directional authorities.

---

## 3. The One-Concept Rule: Unified Directional Authority

V004 introduces exactly **ONE** conceptual change relative to frozen V003:

> **Gate-12/13 Directional Authority Unification**:
> For setups that have passed V003 Gate-11 confluence scoring (8/8) and canonical strategy protections, the authoritative trade direction for Gate-12/13 entry routing and liquidity alignment interpretation is the already-selected V003 / HTF requested trade side (`requested_side`), rather than a diverging persisted `state.structure_dir`.

All other pipeline stages, order block definitions, temporal FVG evidence memory, Gate-11 confluence weights, readiness predicates, liquidity alignment rules, risk controls, and broker protections remain completely frozen and unmodified.

---

## 4. Definition of Requested Trade Side

The authoritative trade direction is derived from the frozen V003 decision context:
* **Source**: The higher-timeframe bias (`htf_bias`) and structural pair side evaluated at Gate 11.
* **Mapping**:
  * `"bullish"` $\rightarrow$ `requested_side = "bullish"` (Trade Direction = `BUY`)
  * `"bearish"` $\rightarrow$ `requested_side = "bearish"` (Trade Direction = `SELL`)
* **Fail-Closed Contract**: If `htf_bias` is missing, empty, or not in `{"bullish", "bearish"}`, evaluation fails closed; no fallback entry is possible.
* **Directional Consistency**: `requested_side` must match the V003 structural-pair side (`pair.side`) and the canonical strategy side. Any internal contradiction fails closed.

---

## 5. Strict V003 Baseline Preservation

V004 is a strict fallback over V003:
1. **Primary Path**: V004 first evaluates frozen V003 execution exactly as implemented.
2. **Unchanged Candidates**: If V003 produces `v003_entry_ready == True`, V004 returns the **exact V003 entry unchanged**.
   * Exact entry order object preserved.
   * Exact setup ID preserved (`s8n1_...`).
   * Exact entry trade direction preserved.
   * Exact entry limit price, stop loss, and take profit geometry preserved.
   * `v004_entry_source = "V003_BASELINE"`.
3. **Candidate Invariance Guarantee**: All **81** candidate-ready decisions observed in V003 R001 are guaranteed to remain candidate-ready decisions under V004 with zero semantic drift.

---

## 6. Execution Conditions for Directional-Authority Fallback

The V004 directional-authority fallback may be evaluated **only** when all of the following conditions are simultaneously met:
1. `v003_gate11_passed == True` (8/8 confluence score satisfied).
2. `v003_strategy_eligible == True` (all canonical strategy protections satisfied: DXY clear, regime clear, session clear, news clear).
3. `v003_entry_ready == False` (the decision is a member of `P_ENTRY_REJECT`).
4. `requested_side in {"bullish", "bearish"}`.
5. Persisted `state.structure_dir in {"bullish", "bearish"}`.
6. Persisted `state.structure_dir != requested_side` (directional authority divergence is present).

If persisted `state.structure_dir` is `None` or unresolved, V004 preserves the V003 rejection without fallback (ruling out E3-type conversions). If persisted `state.structure_dir == requested_side`, directional divergence is absent; V004 preserves the V003 outcome without fallback.

---

## 7. State Readiness & Early-Entry Invariance (E2 Untouched)

Before directional fallback may proceed, the setup must satisfy all existing frozen readiness criteria:
1. **No Relaxation of Confirmed Structure**: If `state.structure_state` is `"confirmed"`, `ready_for_entry()` is evaluated normally.
2. **No Relaxation of Transition Structure**: If `state.structure_state` is `"transition"` or `"choch"`:
   * Score must be $\ge 8$ (`score_eligible_early`).
   * Missing conditions must be strictly `{"Confirmed structure"}` (`missing_set_eligible_early`).
   * Live zone context must be present (`has_zone_context`).
   * Session priority context must be present (`has_priority_context`).
   * **Mandatory Internal Confirmation**: `has_internal_confirmation` (`internal_bos_seen == True` or `choch_seen == True`) is **strictly required**.
3. **E2 Rejections Preserved**: If original state readiness fails and early entry is not authorized (e.g. missing internal confirmation), V004 **fails closed** (`v004_entry_ready = False`, `v004_entry_source = "NONE"`). The 7 D006 E2 observations remain rejected under V004.
4. **Frozen Safety Predicates**:
   * `daily_limits_hit` must remain `False`.
   * `news_status["news_clear"]` must remain `True`.
   * `displacement_seen` must remain `True`.
   * `liquidity_swept` must remain `True`.

---

## 8. Private State Copying & Canonical State Invariance

Canonical strategy state is **never mutated**:
1. An authoritative `StrategyState` instance is never modified during V004 evaluation.
2. For V004 fallback, the evaluator reconstructs the private Gate-12/13 state exactly as in V003.
3. The private state is verified for readiness / early-entry eligibility.
4. A **deep copy** of the private state is created (`copied_state = copy.deepcopy(private_state)`).
5. Only the copied state receives the unified direction: `copied_state.structure_dir = requested_side`.
6. No other field on `copied_state` is modified.
7. Frozen `determine_entry(copied_state, entry_context)` is invoked on the deep copy.
8. The authoritative state chain continues forward unchanged.

---

## 9. Liquidity Rules Invariance (Not a Liquidity Relaxation)

V004 does **not** broaden or relax the accepted liquidity alignment combinations. The combinations evaluated by `determine_entry` remain byte-for-byte identical to the production contract:

* **Bullish Alignment Valid Combinations**:
  * `SELL + equal_lows` (external sell-side liquidity sweep), OR
  * `BUY + internal_continuation` (internal buy-side liquidity continuation)
* **Bearish Alignment Valid Combinations**:
  * `BUY + equal_highs` (external buy-side liquidity sweep), OR
  * `SELL + internal_continuation` (internal sell-side liquidity continuation)

Any other combination (e.g. `bullish + sell + internal_continuation`, `bearish + buy + internal_continuation`, `bearish + sell + equal_lows`) remains **strictly invalid and rejected**.

V004 solely resolves which directional authority is used to interpret the existing rules: when a bullish trade is requested, the entry engine validates whether liquidity satisfies the bullish rule; when a bearish trade is requested, it validates whether liquidity satisfies the bearish rule.

---

## 10. Fallback Entry Trade Direction

Any trade entry emitted via V004 fallback is strictly routed to the requested trade direction:
* If `requested_side == "bullish"`: Entry signal direction is **`BUY`** (`trade_dir = "buy"`).
* If `requested_side == "bearish"`: Entry signal direction is **`SELL`** (`trade_dir = "sell"`).
* Under no circumstances may an entry be executed in the direction of the opposing or stale persisted structure direction.

---

## 11. Protected Policy & Upstream Architecture Invariance

The following components remain completely identical to V003 and production:
1. **V003 Causal Temporal FVG Evidence Memory**: $F_{\text{v003}} = F_{\text{final}} \lor F_{\text{temporal}}$ unchanged.
2. **Order Block Detection & Lifecycle**: Canonical OB detection, causal confirmation, age $>30$ acceptance, unmitigated / uninvalidated checks unchanged.
3. **Confluence Scorer**: Confluence weights (2 / 1 / 2 / 1 / 2), max 8, threshold 8/8 unchanged.
4. **Canonical Strategy Protections**: Regime volatility filters, regime direction filters, DXY authority, session filters, news guards unchanged.
5. **Live-Zone Separation**: Historical temporal FVGs never populate live limit or entry zones.
6. **Risk & Execution Logic**: Broker safeguards, lot sizing, stop loss, take profit, risk-reward ratios unchanged.

---

## 12. Zero Numeric Parameters

V004 introduces **zero** numeric parameters:
* No numerical threshold.
* No timer or timeout parameter.
* No proximity or distance parameter.
* No score alteration.
* **Numeric Parameter Budget**: Remains permanently **`0 / 4`**.

---

## 13. Tier-A Research Target & Classification

During subsequent empirical evaluation on Tier-A Fold 01:
* **Target Metric**: `candidate_ready >= 90` (Density adequacy target).
* **Preregistered Classifications**:
  * `OPPORTUNITY_SUFFICIENT`: `candidate_ready >= 90` (Qualifies variant for supervisory consideration of Tier-B sequential verification; does NOT establish profitability).
  * `OPPORTUNITY_INSUFFICIENT`: `0 < candidate_ready < 90`.
  * `NO_CANDIDATES`: `candidate_ready == 0`.
  * `IMPLEMENTATION_FAILED`: Tooling or contract verification failure.

### Prohibition on Candidate Arithmetic Encoding
D006 identified a coherent mechanism; it did not simulate candidate creation. No specific candidate number (e.g. 90, 102, 103, $81 + 22$, etc.) may be predicted or encoded as an expected oracle in tests. The empirical candidate count must derive naturally during authorized observation.

---

## 14. Governance Boundaries

* **No Empirical Execution in Phase A or B**: Fold-01 snapshot store (`fold-01-a8b406884ab3525a`) must NOT be opened or replayed during preregistration or tooling implementation.
* **Tier B Sealed**: Folds 02–04 remain strictly sealed.
* **Holdout & 2025+ Data**: Inaccessible.
* **Budget Tracking**:
  * Phase-A and Phase-B freeze consume **zero** strategy variant budget.
  * Strategy variants observed remain **`3 / 8`**.
  * Variants become permanently **`4 / 8`** only upon the first real Fold-01 observation under separate supervisory authorization.
