# Phase 8 V2 Reserved-Fold Candidate and Lifecycle Sample Feasibility Plan

**Document ID:** `phase8-v2-tierb-feasibility-plan-v1`  
**Classification:** `PROSPECTIVE_RESERVED_DEVELOPMENT_FEASIBILITY — STRUCTURAL/LIFECYCLE ONLY — NOT_PROFITABILITY_EVIDENCE`  
**Created UTC:** `2026-10-15T01:30:00Z`  
**Research Charter Reference:** `phase8-v2-research-charter-v1-8527e3a5eec98f53` (§13, §14, §16, §17)  
**Superseded Historical Plan:** `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81` (`REPLACED_AND_EXECUTION_PROHIBITED`)  
**Plan Content SHA-256:** `d42d7392cc124b3d8ab09a6212aa29038317fd93ae5d486b24d72904eddea1c9`  

---

## 1. Executive Summary & Purpose

This plan establishes the prospective, two-stage scientific feasibility protocol governing the evaluation of frozen development candidate `phase6-frozen-v2` across reserved Tier-B development folds (`Fold 02`, `Fold 03`, `Fold 04`).

The purpose of Tier-B feasibility is narrow and specific:
> **Core Feasibility Question:**  
> *Does the frozen candidate create enough executable, naturally completed trades across reserved development market conditions to justify building and executing the full 16-scenario scientific evaluation matrix?*

Feasibility answers sample sufficiency and execution lifecycle viability only. It is **NOT** a profitability test, **NOT** an optimization study, and **NOT** a trading performance evaluation.

---

## 2. Frozen Candidate Binding & Authoritative Identities

This feasibility plan is cryptographically and canonically bound to the frozen strategy candidate and authoritative governance records established under Charter §17:

- **Frozen Candidate Identity:** `phase6-frozen-v2`
- **Development Predecessor:** `phase6-development-v2-V005` (Charter §14 Single Candidate Selection)
- **Authoritative Freeze Manifest:** `baseline/phase8_v2_frozen_candidate_manifest_tc003.json` (`phase8v2.frozen-candidate-manifest.v4`)
- **Immutable Semantic Anchor Commit:** `2fd3460b9010d8cca548f4fd6980b6b34fe594e2` (`feat: freeze V005 scoped direction authority`)
- **Strategy Semantic Runtime Dependency Closure:** 83 paths, aggregate digest `ec4b5e6e6ded4797fce2d4d841d1b746e15f7435ac50569c62d6daa38953064f` under `canonical_git_blob_v1`
- **Complete Candidate Configuration SHA-256:** `1aa8b73fb207e10abfe9725bc2979e14692815a5ffe91502cef892b8bae6e806` (StrategyConfig fingerprint `6fce546fb4a3ad41c2fe6fb9` + XAUUSDm profile `7178799c23f85d5cfb867d73f1d9bcb74ae597beb88227ea9a217602770a879a`)
- **Canonical Validation Pipeline Identity:** 147 paths, aggregate digest `957dba56e2244b8cae773ddc17c716da629732d3f492e77578978ef9e091da3f`
- **Protected Infrastructure Identity V2:** 18 Charter §5 controls, 11 unique enforcing paths, aggregate digest `666be323da1f5634e00d5a3285089d9318c99b300696d1f621db4d2cf07f9d7d`
- **Canonical Cost Policy Attestation:** `baseline/phase8_v2_cost_policy_canonical_attestation.json` (fingerprint `054c02ddc07dff2e61a45ed27200eaaf8ec93cc4308db38649395443b6b09108`)
- **Authoritative Scientific Ledger Seal:** `phase8-v2-ledger-seal-v2` (0 unresolved entities)

---

## 3. Known Tier-B Risk Flag Carried Forward

In accordance with candidate selection qualification `phase8-v2-candidate-selection-audit-v1-RC001`, the following risk flag is formally registered and carried into Tier B:

- **Risk Flag:** `TIER_B_REGIME_CONCENTRATION_RISK`
- **Empirical Rationale:** V005's incremental fallback recoveries on contaminated Fold 01 (21 candidates) were structurally concentrated:
  - 20 of 21 candidates occurred in ISO weeks `W17` (11) and `W18` (9), with only 1 in `W19`;
  - 20 of 21 candidates occurred in the first calendar half of Fold 01;
  - 16 of 21 candidates occurred during the London session;
  - Fallbacks spanned only 5 distinct active calendar days (`2024-04-23`, `2024-04-24`, `2024-04-29`, `2024-04-30`, `2024-05-07`).
- **Feasibility Policy:** This risk is monitored **descriptively only**. It does **NOT** impose an additional rejection threshold, and it **MUST NOT** be used to alter, tune, or filter candidate behavior in response.

---

## 4. Sequential Evidence Release Protocol

Reserved Tier-B evidence is protected by strict progressive disclosure rules:

1. **Strictly Sequential Partition Release:**
   - Reserved development folds are ordered: `Fold 02` $\rightarrow$ `Fold 03` $\rightarrow$ `Fold 04`.
   - `Fold 03` cannot be released or inspected unless `Fold 02` has fully passed this feasibility protocol and supervisory approval is granted.
   - `Fold 04` cannot be released or inspected unless `Fold 03` has fully passed.
2. **Supervisory Stop Between Folds:**
   - When a fold execution finishes (whether pass, fail, or blockage), execution **MUST STOP IMMEDIATELY**.
   - The result record must be published, sealed in the hypothesis register, and submitted for independent supervisory review.
   - Automated progression or daisy-chain execution into the next fold is strictly prohibited.
3. **Irreversible Contamination Transition:**
   - Immediately prior to the first empirical read of any reserved fold, a formal release record (e.g. `phase8-v2-tierb-fold02-release-R001`) must be appended to the scientific register.
   - Classification: `DEVELOPMENT_EVIDENCE — CONTAMINATED_FOR_FUTURE_STRATEGY_DESIGN`.
   - This marks the partition as contaminated for future strategy generation.
4. **Accidental Exposure Protocol:**
   - Any accidental or unauthorized access to an unreleased partition must be immediately recorded under Charter §16.
   - Any exposure of Tier-B Holdout or 2025+ data constitutes an immediate, permanent project stopping event.

---

## 5. Stage 1 — Raw-Candidate Futility Protocol

For each released reserved fold, evaluation begins with Stage 1:

1. **Execution Nature:**
   - Scenario-independent structural candidate replay using exact frozen `bot/strategy/variant_v005.py` logic.
   - No trade levels, no execution fills, no slippage, no transaction costs, and no P&L.
   - Counts the metric: `raw_candidate_ready`.
2. **Hard Futility Threshold (< 30):**
   - If `raw_candidate_ready < 30`:
     - Classification: `SAMPLE_SIZE_FUTILITY`.
     - Outcome: `phase6-frozen-v2` is **REJECTED**.
     - Execution stops immediately. Stage 2 lifecycle replay is **NOT** executed. Subsequent folds remain unopened.
3. **Headroom Target (>= 60):**
   - If `raw_candidate_ready >= 60`:
     - Classification: `RESERVED_FOLD_RAW_HEADROOM_TARGET_MET`.
   - If `30 <= raw_candidate_ready < 60`:
     - Classification: `RESERVED_FOLD_RAW_HEADROOM_TARGET_NOT_MET`.
   - **Non-Gating Status:** The 60-candidate target represents descriptive engineering headroom (2× over the 30-trade threshold). A fold with 30–59 raw candidates is **NOT** rejected at Stage 1 and proceeds to Stage 2 lifecycle feasibility.
4. **Stage-1 Reporting Surface:**
   - `raw_candidate_ready` count
   - `unique_setup_ids` count
   - duplicate setup count (must be 0)
   - LONG and SHORT counts
   - Source breakdown: `V003_BASELINE` vs `V005_DIRECTIONAL_FALLBACK`
   - Fallback direction: BUY vs SELL
   - Temporal distributions: weekly, session (London, NY, Asian, Off-hours), first-half vs second-half.
   - **Prohibited:** Any profitability calculation.

---

## 6. Stage 2 — Lifecycle / Completed-Trade Sample Feasibility Protocol

Folds passing Stage 1 ($\ge 30$ raw candidates) undergo Stage 2 lifecycle execution:

1. **Historical 30-Trade Threshold Retained Prospectively:**
   - Preregistered threshold: `MIN_COMPLETED_TRADES_PER_RESERVED_FOLD = 30`.
   - **Scientific Rationale:** Research Charter §13 explicitly specifies the historical 30-closed-trade requirement. The Tier-A raw target of 90 was engineered as 3× headroom over 30; the reserved headroom target of 60 was engineered as 2× headroom over 30. Retaining 30 prospectively preserves the pre-existing engineering sample feasibility requirement without post-observation manipulation.
2. **Exact Unit of Application:**
   - The 30-trade threshold applies strictly:
     $$\text{Qualifying Completed Trades} \ge 30 \quad \text{per reserved fold} \quad (\text{PRIMARY\_BASELINE scenario only})$$
   - It does **NOT** apply aggregated across folds.
   - It does **NOT** apply aggregated across multiple execution scenarios.
   - It does **NOT** apply per session or per direction.
3. **Single Canonical Scenario (PRIMARY_BASELINE):**
   - Only the single canonical `PRIMARY_BASELINE` execution scenario is executed during feasibility:
     - **Swap Component:** `SWAP_EMAIL_REFERENCE`
     - **Slippage Component:** `SLIPPAGE_MODERATE_ADVERSE`
     - **Metadata Component:** `BASELINE_CURRENT_REFERENCE_PROXY`
     - **Scenario ID:** Formed deterministically from these exact three registered components.
4. **Exclusion of the 16-Scenario Matrix During Feasibility:**
   - The full 16-scenario factorized matrix belongs to subsequent scientific evaluation.
   - Feasibility tests only whether sufficient completed trades occur under baseline conditions.
   - No sensitivity sweeps, worst-case stress tests, or diagnostic ladders are permitted during feasibility.
5. **Scenario-Dependent Qualification Rule:**
   - Only `PRIMARY_BASELINE` determines feasibility pass/fail. Other hypothetical scenarios are unobserved during feasibility and cannot influence candidate qualification.

---

## 7. Qualifying Completed-Trade Definition

A qualifying completed trade is strictly defined as one **UNIQUE** lifecycle position satisfying all 7 contractual conditions:

1. **Frozen Candidate Origin:** Originates from a verified `raw_candidate_ready` produced by frozen V005 in the released fold.
2. **Valid Trade Geometry:** Constructs a valid `EntryIntent` under existing frozen level infrastructure (`bot/strategy/trade_levels.py`, `bot/strategy/setup_intent.py`, profile `min_rr = 1.5`).
3. **Confirmed Entry Fill:** Receives a durable, validated entry fill event from the execution engine.
4. **Active State Attainment:** Successfully transitions to `LifecycleStatus.OPEN` or `LifecycleStatus.PARTIALLY_CLOSED`.
5. **Natural Lifecycle Closure:** Transitions to `LifecycleStatus.CLOSED` via normal frozen lifecycle logic driven by executable historical quotes.
6. **Legitimate Natural Exit Reason:** Closes via a permitted natural exit reason:
   - `STOP_LOSS`
   - `BREAK_EVEN`
   - `TRAILING_STOP`
   - `TAKE_PROFIT`
   - Legitimate frozen risk/circuit/emergency closure occurring after confirmed entry.
7. **Exclusion of Boundary Closes:** The trade was **NOT** closed solely due to the termination of the fold data window (`END_OF_DATA`).

### Explicitly Excluded States (Do NOT count toward 30):
- `CANCELLED` orders
- `EXPIRED` orders
- `REJECTED` orders
- Unfilled intents
- Untriggered pending limit/stop orders
- Positions never opened
- Partial closes without a final natural close
- Duplicate lifecycle events for the same setup
- Forced fold-boundary closures (`END_OF_DATA_FORCED_CLOSE_EXCLUDED_FROM_SAMPLE`)

---

## 8. Fold-Boundary & Open-Position Contract

To preserve partition independence and prevent lookahead bias:

1. **No Cross-Fold Empirical Lookahead:**
   - A feasibility run for Fold $N$ **MUST NOT** read any quote, bar, or tick from Fold $N+1$ to allow an open position to close naturally.
   - Strictly no next-fold market data may be accessed.
2. **Mandatory Exclusion of Fold-End Forced Closes:**
   - Any position remaining open at the fold boundary that is closed by engine shutdown or end-of-series accounting **MUST** be recorded as:
     `END_OF_DATA_FORCED_CLOSE_EXCLUDED_FROM_SAMPLE`
   - Such positions are strictly excluded from the count of qualifying completed trades.
   - Reporting must include: count, setup IDs, position IDs, directions, and entry timestamps (zero P&L).
3. **Pending Intents at Fold End:**
   - Untriggered pending orders at fold end are cancelled and accounted for under fold-boundary attrition.
4. **Zero Position Carryover:**
   - Each reserved fold is an isolated, independent feasibility trial.
   - No open position, pending order, or strategy state carries over from Fold 02 into Fold 03, or from Fold 03 into Fold 04.
   - Earlier released data may only be used as causal historical warmup where the frozen data input contract explicitly requires lookback bars.

---

## 9. V005 → Lifecycle Adapter Contract

A validation adapter will bridge frozen V005 candidates to the existing lifecycle engine:

1. **Authoritative V005 Readiness:**
   - The adapter must evaluate candidate readiness directly using `bot/strategy/variant_v005.py`.
   - Production pre-V005 gate-reducer candidate readiness cannot be substituted where V005 fallback differs.
2. **Zero Strategy Semantic Modification:**
   - The adapter is validation-only tooling. It translates frozen candidate outputs into `EntryIntent` structures; it **MUST NOT** alter candidate logic.
3. **Frozen Trade Geometry:**
   - V005 `determine_entry()` provides directional readiness.
   - Trade levels (entry price, stop loss, take profit) must be derived using existing frozen modules:
     - `bot/strategy/trade_levels.py`
     - `bot/strategy/setup_intent.py`
     - Effective frozen XAUUSDm profile (`min_rr = 1.5`, `structure_tf = H1`, `entry_tf = M5`).
   - No new level formulas, no modified stop distances, and no alternate risk-reward ratios may be introduced.
4. **Level / Intent Attrition:**
   - If a raw V005 candidate cannot construct a valid level geometry or EntryIntent under frozen constraints, it remains counted in Stage 1 raw candidates and is recorded as:
     `LEVEL_OR_INTENT_CONSTRUCTION_ATTRITION`
   - It does not proceed to lifecycle execution and is not removed retroactively from Stage 1.
5. **Direction Invariant:**
   - The generated lifecycle `EntryIntent` direction must exactly match the frozen V005 candidate direction (`BUY` $\rightarrow$ `BUY`, `SELL` $\rightarrow$ `SELL`). Any mismatch must fail closed.
6. **Setup Identity Invariant:**
   - The unique `setup_id` must be preserved immutably from raw candidate $\rightarrow$ EntryIntent $\rightarrow$ broker order $\rightarrow$ position $\rightarrow$ trade closure.
   - Re-use or duplicate consumption of a setup is strictly prohibited by existing setup consumption barriers.

---

## 10. Stage-2 Pass / Fail Classifications

For each released reserved fold:

1. **Pass Condition:**
   - Stage 1 raw candidate count $\ge 30$; **AND**
   - Stage 2 `PRIMARY_BASELINE` qualifying natural completed trades $\ge 30$; **AND**
   - All reconciliation checks (consumption idempotency, risk authority, fill journal, ledger balance) pass 100%.
   - **Classification:** `RESERVED_FOLD_SAMPLE_FEASIBILITY_PASS`.
2. **Lifecycle Sample Failure:**
   - Qualifying natural completed trades $< 30$.
   - **Classification:** `LIFECYCLE_SAMPLE_INSUFFICIENT`.
   - **Outcome:** `phase6-frozen-v2` is **REJECTED**. Execution stops. Subsequent folds remain sealed.
3. **Infrastructure / Reconciliation Failure:**
   - Unhandled exception, data corruption, or deterministic reconciliation failure occurs during replay.
   - **Classification:** `FEASIBILITY_IMPLEMENTATION_OR_DATA_BLOCKAGE`.
   - **Outcome:** Execution halts immediately without declaring strategy sample feasibility. Return for supervisory audit.

---

## 11. Complete Attrition Funnel & Monitoring Surface

Feasibility reports must output the complete structural attrition funnel:

1. `raw_candidates_ready`
2. `valid_level_geometry`
3. `valid_entry_intents`
4. `eligible_intents`
5. `triggered_intents`
6. `durable_entry_fills`
7. `opened_positions`
8. `partially_closed_positions`
9. `naturally_completed_trades` (Threshold $\ge 30$)
10. `end_of_data_excluded_positions`
11. Attrition categories: `cancelled`, `expired`, `rejected`, `unfilled`, `intent_construction_attrition`

### Stratifications:
- **By Source:** Report attrition and completed trades separately for `V003_BASELINE` vs `V005_DIRECTIONAL_FALLBACK`.
- **Regime-Concentration Monitoring:** Report fallback candidates by ISO week, session, direction, and calendar half to evaluate `TIER_B_REGIME_CONCENTRATION_RISK`.

---

## 12. Strict Prohibition on Profitability Metrics

In accordance with Research Charter §14 and Phase 8 governance:

> [!CAUTION]
> **STRICT BAN ON PROFITABILITY METRICS**  
> Feasibility tooling, logs, and artifacts **MUST NOT** compute, summarize, rank, or display:
> - Net Profit / Gross Profit / Gross Loss
> - Win Rate / Loss Rate
> - Profit Factor / Expectancy
> - Sharpe Ratio / Sortino Ratio / Calmar Ratio
> - Return on Investment (ROI) / Percentage Returns
> - Equity Curves / Balance Curves
> - Monetary or Percentage Drawdowns
> - Average Winner / Average Loser
> - R-Multiple profitability or payoff ratios
> 
> Even if internal execution mechanisms require price math, all output summaries are strictly restricted to structural lifecycle event counts.

Counting structural exit reasons (`STOP_LOSS`, `TAKE_PROFIT`, `BREAK_EVEN`, `TRAILING_STOP`) is permitted **only** as categorical event tallies; transforming them into financial win rates is strictly prohibited.

---

## 13. Tooling Implementation Roadmap & Mandatory Rehearsals

This document preregisters the feasibility plan only; it authorizes **zero** empirical execution.

Before any reserved fold is opened, the future implementation task must build the tooling and undergo two mandatory non-tuning rehearsals on contaminated Fold 01:

1. **Mandatory Fold-01 Candidate Parity Rehearsal:**
   - Prove the new V005 feasibility adapter exactly reproduces the sealed `phase6-development-v2-V005-R001` candidate surface on Fold 01:
     - Exactly 102 raw candidates (81 `V003_BASELINE`, 21 `V005_DIRECTIONAL_FALLBACK`);
     - Exactly 102 unique setup IDs, 0 duplicates;
     - Exact candidate `(decision_id, setup_id)` multiset agreement;
     - Exact deterministic entry objects.
2. **Mandatory Fold-01 Lifecycle Mechanics Rehearsal:**
   - Prove the `PRIMARY_BASELINE` lifecycle runner completes end-to-end, enforces `END_OF_DATA` exclusions, and reconciles all accounting without error on Fold 01.
   - Fold-01 lifecycle trade counts do **NOT** count toward Tier B and **MUST NOT** be used to alter the 30-trade threshold.
   - Zero strategy tuning is permitted during rehearsal.

---

## 14. Plan Content Fingerprint & Canonical Invariants

- **Canonical Plan JSON:** `baseline/phase8_v2_tierb_feasibility_plan.json`
- **Schema:** `phase8v2.tierb-feasibility-plan.v1`
- **Plan Content SHA-256:** `d42d7392cc124b3d8ab09a6212aa29038317fd93ae5d486b24d72904eddea1c9`
- **Prospective Contract:** `canonical_git_blob_v1`
- **Research Budget Impact:** 0 (allowances remain retired).
- **Empirical Access:** 0 (Tier-B partitions remain strictly sealed).

---

## 15. Plan-TC001 Provenance Corrections & Evidence Contracts

Under supervisory review, four machine-contract corrections and provenance hardenings were formally applied append-only in `phase8-v2-tierb-feasibility-plan-v1-TC001`:

- **Correction Record ID:** `phase8-v2-tierb-feasibility-plan-v1-TC001`
- **Plan Manifest:** `baseline/phase8_v2_tierb_feasibility_plan_tc001.json`
- **Schema:** `phase8v2.tierb-feasibility-plan.v2`
- **Parent Plan:** `phase8-v2-tierb-feasibility-plan-v1` (content SHA `d42d7392cc124b3d8ab09a6212aa29038317fd93ae5d486b24d72904eddea1c9` preserved immutably)
- **TC001 Plan Content SHA-256:** `5c2d5e4f29d2dfb3720dc264c8b28d240c0cf1cb8a62ccd40923ed5d8b2cfddf`

### 15.1 Cost-Policy & Provenance Disambiguation
- **Canonical Execution Model Fingerprint:** `054c02ddc07dff2e61a45ed27200eaaf8ec93cc4308db38649395443b6b09108` (derived from `bot/backtesting/costs.py`, `bot/backtesting/models.py`, `bot/backtesting/engine.py` at anchor `d87b71491203249e6ab3dd95bca4b9ee89cf3e9e`).
- **Cost-Policy Canonical Attestation Fingerprint:** `10e9a42e501b24b3cff3459a955cfef37c67d542dc76ef8300bcff596321ff42` (`baseline/phase8_v2_cost_policy_canonical_attestation.json`).
- **Phase 8H Policy Package:** `evidence-development_cost_policy-v1-6b1a986b1f8d7b81` (policy fingerprint `aa0ccc9368c0cf55b4775b4295f0424d4bdb0e5fd6cbfaf27137763be58e9404`, content SHA `6b1a986b1f8d7b81ff10616fd848cb93d6dd0b19d4a96f1a512d629716b42b42`, state `PREREGISTERED_INACTIVE`).
- **Phase 8I Activation Package:** `evidence-cost_policy_activation-v1-802914181c0ca505` (state `ACTIVE_FOR_DEVELOPMENT_VALIDATION`, authorizes development accounting only).
- **Phase 8I Dataset Review:** `evidence-dataset_acceptance_review-v1-4d47816f5f336fe2`.
- **Phase 8L Development Metadata Bounds:**
  - Unavailability: `evidence-broker_metadata_unavailability-v1-f1be088c17a391c4`
  - Bounds: `evidence-development_metadata_bounds-v1-8dad509e60c8014a`
  - Readiness: `evidence-development_metadata_bounds_readiness-v1-6fa811a3200c6042`
  - Policy Fingerprint: `54f9a9817613bf3115039dd43b66c476a72627880663d4fb6c3f59cbbde1be1f`
- **Development-Proxy Qualifications:** All Stage-2 results carry mandatory qualifications: `DEVELOPMENT_PROXY_NOT_HISTORICALLY_VALIDATED` and `HISTORICAL_SWAP_UNCERTAIN`.

### 15.2 Factorized 16-Scenario Matrix Fingerprint
- **Matrix Schema:** `phase8n.factorized-scenario-matrix.v1`
- **Unique Scenarios:** 16 (64 required cells across 4 folds).
- **Matrix Canonical Fingerprint:** `3c59adbc16c2e2780041c1021e44066c5c43d980c5991af7fe32dcaaa36c3401`
- **PRIMARY_BASELINE Scenario Object:** `SWAP_EMAIL_REFERENCE|SLIPPAGE_MODERATE_ADVERSE|BASELINE_CURRENT_REFERENCE_PROXY` (role: `PRIMARY`).

### 15.3 Exact Reserved-Fold Schedule & Windows
- **Fold 01:** Evaluation `[2024-04-01T00:00:00Z, 2024-06-08T00:00:00Z)`; warmup begins `2024-03-04T00:00:00Z`; purge `86400`s; embargo `86400`s.
- **Fold 02:** Evaluation `[2024-06-09T00:00:00Z, 2024-08-16T00:00:00Z)`; warmup begins `2024-05-12T00:00:00Z`; purge `86400`s; embargo `86400`s.
- **Fold 03:** Evaluation `[2024-08-17T00:00:00Z, 2024-10-24T00:00:00Z)`; warmup begins `2024-07-20T00:00:00Z`; purge `86400`s; embargo `86400`s.
- **Fold 04:** Evaluation `[2024-10-25T00:00:00Z, 2025-01-01T00:00:00Z)`; warmup begins `2024-09-27T00:00:00Z`; purge `86400`s; embargo `0`s.
- Warm-up duration is exactly 28 days (2,419,200 seconds) terminating at evaluation start.

### 15.4 Lifecycle Exit Enum Parity
- Qualifying natural exit reasons correspond verbatim to frozen `ExitReason` enum: `STOP_LOSS`, `BREAK_EVEN`, `TRAILING_STOP`, `TAKE_PROFIT`, `EMERGENCY`.
- Fold-end forced closure uses frozen `ExitReason.END_OF_DATA`, classified as `END_OF_DATA_FORCED_CLOSE_EXCLUDED_FROM_SAMPLE` and strictly excluded from the 30-trade minimum quota.

### 15.5 Strengthened Fold-01 Empirical Rehearsal
- Formally classified as `CONTAMINATED_FOLD01_EMPIRICAL_TOOLING_REHEARSAL — NOT_TIER_B_EVIDENCE`.
- Bound to sealed `phase6-development-v2-V005-R001` (SHA-256 `27b8849eb97074d55c36bf11645cae8821d517b1f9e52e0c9a37976c77abcbfe`, 80,554 bytes).
- Rehearsal asserts:
  - Exact counts: 102 raw candidates, 81 baseline, 21 fallback, 102 unique setups, 0 duplicates;
  - Exact `(decision_id, setup_id)` multiset equality;
  - Exact deterministic JSON entry object equality: `json.dumps(entry, sort_keys=True, separators=(',', ':'), allow_nan=False)`. Mismatch halts fail-closed with `FOLD01_V005_ENTRY_PARITY_FAILURE`.

---

## 16. Plan-TC002 Pre-Release Evidence Contract & Execution Integrity Hardening

Under supervisory review of tooling commit `fef16b8d819e0339f6e8427fb126ba6126da0fc2` (dispositioned as `IMPLEMENTATION_INCOMPLETE_PRE_EMPIRICAL` in record `phase8-v2-tierb-feasibility-tooling-v1-R001` with 0 budget impact and 0 empirical exposure), `phase8-v2-tierb-feasibility-plan-v1-TC002` was created to complete the pre-release evidence contract and mandate commit-bound execution integrity:

- **Correction Record ID:** `phase8-v2-tierb-feasibility-plan-v1-TC002`
- **Plan Manifest:** `baseline/phase8_v2_tierb_feasibility_plan_tc002.json`
- **Schema:** `phase8v2.tierb-feasibility-plan.v3`
- **Parent Plan:** `phase8-v2-tierb-feasibility-plan-v1-TC001` (content SHA `5c2d5e4f29d2dfb3720dc264c8b28d240c0cf1cb8a62ccd40923ed5d8b2cfddf` preserved immutably)
- **TC002 Plan Content SHA-256:** `033ea8a04ef6ee991001774abff034f6e4e0ea11445e30b030665c5aa413d943`
- **Classification:** `PROSPECTIVE_RESERVED_DEVELOPMENT_FEASIBILITY — STRUCTURAL/LIFECYCLE ONLY — NOT_PROFITABILITY_EVIDENCE`

### 16.1 Complete 16-Item Pre-Release Input Chain
Before any empirical partition (Fold 01 rehearsal or reserved folds) can be accessed, the runner must verify the presence and cryptographic integrity of the complete 16-item development input chain:
1. **2024 Tick-Year Package:** `exness-xauusdm-2024-development-b2a0234a470dd397`
2. **Derived Candles:** `derived-candles-2024-v1-20260911T195553Z`
3. **Candle Attestation:** `derived-candles-attestation-v1-6715e5c64d888215`
4. **DXY Index:** `dxy-development-2024-v1-20260912T091410.712364Z`
5. **Observed Spread:** `observed_spread-v1-e25bdb9bf028a5be`
6. **Official USD News:** `evidence-official_news-v1-78279c5e26c1c6d1`
7. **Phase 8H Cost Policy:** `evidence-development_cost_policy-v1-6b1a986b1f8d7b81`
8. **Phase 8I Activation Package:** `evidence-cost_policy_activation-v1-802914181c0ca505`
9. **Phase 8I Dataset Acceptance Review:** `evidence-dataset_acceptance_review-v1-4d47816f5f336fe2`
10. **Historical Broker Metadata Unavailability:** `evidence-broker_metadata_unavailability-v1-f1be088c17a391c4`
11. **Phase 8L Development Metadata Bounds:** `evidence-development_metadata_bounds-v1-8dad509e60c8014a`
12. **Phase 8L Metadata Bounds Readiness:** `evidence-development_metadata_bounds_readiness-v1-6fa811a3200c6042`
13. **Contamination Register:** `baseline/phase8_contamination_register.json`
14. **Candidate Freeze Manifest:** `baseline/phase8_v2_frozen_candidate_manifest_tc003.json`
15. **Feasibility Plan TC002:** `baseline/phase8_v2_tierb_feasibility_plan_tc002.json`
16. **Authoritative Ledger Seal:** `phase8-v2-ledger-seal-v2`

### 16.2 Prospective Readiness & Governance Verification
Rather than relying on ad-hoc file checks:
- The runner executes `bot.validation.development_evaluation_plan.verify_input_readiness_prospective` with `tick_verification_depth="identity-chain"`, `research_identity="phase6-development-v2"`, `variant_id="phase6-development-v2-V005"`, and `fingerprint_contract="canonical_git_blob_v1"`.
- Phase 8I activation is verified via `bot.validation.cost_policy_activation.verify_activation_record`, requiring state `ACTIVE_FOR_DEVELOPMENT_VALIDATION` and exact binding to policy `evidence-development_cost_policy-v1-6b1a986b1f8d7b81`.
- Phase 8L metadata readiness is verified via `bot.validation.development_metadata_bounds.verify_readiness`, asserting exact bounds policy and fingerprint `54f9a9817613bf3115039dd43b66c476a72627880663d4fb6c3f59cbbde1be1f`.

### 16.3 Commit-Bound Frozen Candidate Execution Integrity
- Strategy research is permanently closed. The candidate remains `phase6-frozen-v2` at semantic anchor commit `2fd3460b9010d8cca548f4fd6980b6b34fe594e2`.
- Execution integrity requires that the current active commit's Git blobs for all strategy, configuration, validation, and protected runtime paths match verbatim the digests recorded in `phase8_v2_frozen_candidate_manifest_tc003.json`:
  - Strategy Semantic Digest: `ec4b5e6e6ded4797fce2d4d841d1b746e15f7435ac50569c62d6daa38953064f`
  - Candidate Configuration SHA-256: `1aa8b73fb207e10abfe9725bc2979e14692815a5ffe91502cef892b8bae6e806`
  - Validation Pipeline Digest: `957dba56e2244b8cae773ddc17c716da629732d3f492e77578978ef9e091da3f`
  - Protected Infrastructure Digest V2: `666be323da1f5634e00d5a3285089d9318c99b300696d1f621db4d2cf07f9d7d`
- Any worktree drift or blob mismatch halts execution immediately prior to opening any feature store with classification `FROZEN_CANDIDATE_EXECUTION_IDENTITY_MISMATCH`.
