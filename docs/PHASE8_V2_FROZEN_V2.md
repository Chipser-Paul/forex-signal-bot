# Phase 8 V2 Prospective Strategy Freeze — `phase6-frozen-v2`

**Document Classification:** PROSPECTIVE_STRATEGY_FREEZE_SPECIFICATION  
**Freeze Identity:** `phase6-frozen-v2`  
**Development Predecessor:** `phase6-development-v2-V005`  
**Charter Reference:** `phase8-v2-research-charter-v1-8527e3a5eec98f53` (§14, §17)  
**Semantic Anchor Commit:** `2fd3460b9010d8cca548f4fd6980b6b34fe594e2`  
**Prospective Contract ID:** `canonical_git_blob_v1`  
**Freeze Manifest:** `baseline/phase8_v2_frozen_candidate_manifest.json`  
**Freeze Governance Record:** `phase6-frozen-v2-F001`  
**Research Closure Record:** `phase6-development-v2-research-closure-v1`  
**Scientific Status:** `FROZEN_FOR_RESERVED_FOLD_FEASIBILITY` — **ZERO PROFITABILITY EVIDENCE** — **TIER-B REMAINS SEALED**  

---

## 1. Executive Summary & Selection Rationale

Under Research Charter §14 and §17, development variant `phase6-development-v2-V005` is formally accepted as the single development candidate and canonically frozen as `phase6-frozen-v2`.

### 1.1 Candidate Selection Audit Acceptance
In `docs/PHASE8_V2_CANDIDATE_SELECTION_AUDIT.md` (register record `phase8-v2-candidate-selection-audit-v1` and qualification `phase8-v2-candidate-selection-audit-v1-RC001`), V005 was audited against all eight mandatory Charter §14 criteria and evaluated as **8 / 8 PASS**:

1. **Economic Coherence (PASS):** Resolves the Gate-12/13 entry routing and liquidity alignment conflict identified in D006 by aligning entry directional authority with higher-timeframe market structure (`htf_bias`).
2. **Causal Correctness (PASS):** Evaluated strictly over causal historical feature stores with active-bar exclusion; authoritative `StrategyState` is unmutated; 81/81 V003 baseline entries reproduced identically.
3. **Code Simplicity (PASS):** Introduces exactly one conceptual change: eligibility-scoped directional authority. Avoids unconditional over-reach through scoped fallback gating.
4. **Opportunity Sufficiency (PASS):** Observed raw `candidate_ready = 102`, satisfying the Charter adequacy threshold (`>= 90`).
5. **Temporal Stability (PASS):** 102 candidates span 15 calendar days across April, May, and June 2024, populating 8 ISO-week bins without single-day collapse.
6. **Long/Short Balance (PASS):** 55 LONG / 47 SHORT (53.9% / 46.1%), demonstrating strong directional equilibrium.
7. **Limited Complexity Increase (PASS):** Zero numeric parameters added (0 / 4 numeric parameter trials consumed); no new indicators or ML models.
8. **Protected Safety Architecture (PASS):** All Charter §5 safety controls remain active, unbypassed, and uncompromised.

### 1.2 Selection Declaration
Formal selection decision:
> **`SELECT_PHASE6_DEVELOPMENT_V2_V005_AS_SINGLE_FREEZE_CANDIDATE`**

Supervisory authorization is executed to create:
> **`phase6-frozen-v2`**

---

## 2. Immutable Semantic Scope & Implementation Invariance

`phase6-frozen-v2` creates **NO** new strategy implementation files. It does **NOT** create `bot/strategy/frozen_v2.py`, does **NOT** copy V005 code, and does **NOT** modify existing source files.

The strategy semantic implementation is anchored to the exact committed bytes of `phase6-development-v2-V005` at semantic anchor commit `2fd3460b9010d8cca548f4fd6980b6b34fe594e2`.

### 2.1 The One-Concept Semantic Rule
* **Concept:** *Eligibility-Scoped Requested-Side Entry Direction Authority* (H009).
* **Baseline Preservation:** When `v003_entry_ready == True`, returns the exact V003 entry immediately (`source = V003_BASELINE`). All 81 V003 baseline candidates are preserved bit-for-bit.
* **Fallback Eligibility Boundary:** Directional fallback is evaluated **only** after:
  1. V003 Gate-11 confluence passes (8/8 score);
  2. Canonical strategy protections pass (`evaluate_v005_strategy`);
  3. `requested_side` agrees with `pair.side` (`BUY` for bullish, `SELL` for bearish);
  4. Directional divergence exists between `state.structure_dir` and `requested_side`.
* **State Machine Invariance:** The authoritative `StrategyState` is never mutated. Fallback entry routing operates exclusively on a private copy: `copied_state.structure_dir = requested_side`.
* **Liquidity Rule Invariance:** Strictly evaluates frozen `determine_entry` liquidity alignments:
  - Bullish: `sell` + `equal_lows` OR `buy` + `internal_continuation`.
  - Bearish: `buy` + `equal_highs` OR `sell` + `internal_continuation`.
  - All other combinations are rejected.
* **Readiness Invariance:** Score-8 conservative early entry requires internal confirmation (`BOS`, `CHOCH`, or `sweep_rejected`). The 7 D006 E2 rejections remain strictly rejected.
* **Direction Invariance:** Fallback trade direction strictly matches `requested_side`.

---

## 3. Prospective Contract & Semantic Digest

Under the repository prospective contract boundary (`bot/scientific/prospective_freeze.py`), prospective freezes must declare an approved contract (`canonical_git_blob_v1`) and compute framed digests over committed Git blobs only.

### 3.1 Contract Validation
* Contract ID: `canonical_git_blob_v1`
* Validation Status: `validate_prospective_contract("canonical_git_blob_v1")` returns **PASS**.
* Fail-Closed Invariants: Missing contract (`None`), empty string, legacy contract (`legacy_worktree_bytes_v0`), and unknown contract names fail closed.

### 3.2 Strategy Semantic Surface & Blob Hashes
The canonical semantic dependency surface is defined by the 7 minimal mandatory paths resolved at semantic anchor commit `2fd3460b9010d8cca548f4fd6980b6b34fe594e2`:

| Index | Canonical Repo-Relative Path | Git Blob SHA-1 | Mode | Size (bytes) | Role in Candidate Semantics |
|---|---|---|---|---|---|
| 1 | `bot/state/gate_inputs.py` | `a4bdc19a949f75ea7fa7cc52c516b6626590fe6c` | `100644` | 12,984 | Causal setup preparation & gate input mapping |
| 2 | `bot/state/gate_reducer.py` | `e1841fc276401146e38a69b9555a0e4437a30290` | `100644` | 13,388 | Gate sequencing 1–13 & candidate reduction |
| 3 | `bot/strategy/config.py` | `fc992fb091bc5c04363552467e99807c83387386` | `100644` | 4,703 | StrategyConfig configuration parameter definitions |
| 4 | `bot/strategy/variant_v003.py` | `c25f110c15c60bc5b32cffc0b3870de6d5d5144c` | `100644` | 22,768 | V003 baseline & temporal FVG evidence memory |
| 5 | `bot/strategy/variant_v005.py` | `3820c6c66f96c91d98b47feda0e4f5f88aa5c70a` | `100644` | 12,275 | V005 scoped directional authority candidate |
| 6 | `strategies/smc_engine/entry_model.py` | `0dff4ccb47513ccd56cd955d9f618e69d9ec3c02` | `100644` | 11,567 | Early entry readiness & determine_entry logic |
| 7 | `strategies/smc_engine/strategy_state.py` | `b7500160ebfb084703c6fe02c16946c1185d21b2` | `100644` | 5,618 | Authoritative state machine & condition tracker |

### 3.3 Aggregate Strategy-Semantic Digest
Computed via `freeze_prospective_identity` under `canonical_git_blob_v1`:
> **`22880f7acfb762b938997ef070fef13580679f37058f1853b8c8438fc9defc25`**

* Digest Algorithm: `sha256`
* Input Paths: 7 sorted repo-relative paths
* Local path leakage: **ZERO** (no absolute local paths enter the identity)

---

## 4. Complete Configuration Lock

The frozen candidate configuration is defined by `bot.strategy.config.StrategyConfig` defaults:

| Configuration Parameter | Locked Canonical Value | Units / Type |
|---|---|---|
| `version` | `"phase6-strategy-v1"` | string |
| `executable_symbols` | `["XAUUSDm"]` | frozenset / list |
| `dxy_symbol_map` | `{"EURUSD": "EURUSDm", "GBPUSD": "GBPUSDm", "USDCAD": "USDCADm", "USDCHF": "USDCHFm", "USDJPY": "USDJPYm", "USDSEK": "USDSEKm"}` | mapping |
| `dxy_lookback_bars` | `20` | bars (M5) |
| `dxy_slope_threshold_fraction_per_bar` | `0.0001` | fraction |
| `dxy_max_staleness_seconds` | `3600.0` | seconds (1 hour) |
| `atr_period_bars` | `14` | bars (M5) |
| `regime_baseline_bars` | `20` | bars (M5) |
| `regime_trend_lookback_bars` | `20` | bars (M5) |
| `high_volatility_ratio` | `1.5` | ratio |
| `trend_strength_atr` | `0.9` | ATR multiple |
| `order_block_displacement_atr` | `1.5` | ATR multiple |
| `order_block_expiry_bars` | `30` | bars (M5) |
| `news_block_before_seconds` | `1800.0` | seconds (30 mins) |
| `news_block_after_seconds` | `1800.0` | seconds (30 mins) |
| `news_max_age_seconds` | `3600.0` | seconds (60 mins) |
| `rollover_start_utc` | `"21:55:00"` | UTC time |
| `rollover_end_utc` | `"22:10:00"` | UTC time |
| `confluence_threshold` | `8` | points (max 8) |

### 4.1 Configuration Fingerprints
* **Historical/Config API Fingerprint:** `6fce546fb4a3ad41c2fe6fb9` (`StrategyConfig().fingerprint()`)
* **Full Deterministic Configuration SHA-256:** `6fce546fb4a3ad41c2fe6fb98231ceb7840d15e60f234746d7c78c87d3791e19`

---

## 5. Frozen Dependencies & Infrastructure Attestations

### 5.1 V003 Dependency Lock
* Implementation Git Blob: `c25f110c15c60bc5b32cffc0b3870de6d5d5144c`
* Preregistration Specification SHA-256: `e6aa3e8a4f7b909f178a18112a43425ccfe61448c3c8643aea9c3f5d670e0d95`
* Invariant: Temporal FVG evidence memory is formally retained as a frozen foundation.

### 5.2 Entry & State Model Dependency Lock
* `strategies/smc_engine/entry_model.py` Git Blob: `0dff4ccb47513ccd56cd955d9f618e69d9ec3c02`
* `strategies/smc_engine/strategy_state.py` Git Blob: `b7500160ebfb084703c6fe02c16946c1185d21b2`

### 5.3 Protected Safety Architecture Attestation (Charter §5)
Verified full preservation of all 15 core safety and execution guards:
1. Production executable symbol strictly `XAUUSDm`.
2. Causal candle availability (`available_at <= decision_at`).
3. Forming active bar strictly excluded.
4. HTF candle availability filtered causally.
5. News fail-closed window [t - 30m, t + 30m] with 60m max age.
6. Rollover lockout (21:55–22:10 UTC) strictly enforced.
7. DXY 6-pair basket and lookback rules active.
8. Setup consumption and setup ID idempotency guaranteed.
9. Risk engine retains exclusive lot sizing and SL/TP authority.
10. Account-level daily and max drawdown circuit breakers unbypassed.
11. Broker volume precision (0.01 step) enforced.
12. Tick freshness and staleness controls active.
13. Maximum spread threshold (30.0 points) enforced.
14. Projected margin pre-trade verification enforced.
15. Order retry and price revalidation active.

### 5.4 Cost Policy Attestation Reference
* Reference: `baseline/phase8_v2_cost_policy_canonical_attestation.json`
* Git Blob SHA-1: `1e08dc4a0bc2f82c8318e8aa57c71e90b0980b1e`
* Artifact SHA-256: `990109cc860a248663be758ca233e077acd96502d10cce91ad29726b760675f4`
* Canonical Execution Model Fingerprint: `054c02ddc07dff2e61a45ed27200eaaf8ec93cc4308db38649395443b6b09108`
* Invariant: Cost semantics are prospective validation infrastructure, not Tier-A profitability evidence.

### 5.5 Development Measurement Provenance
* Evaluator Module: `backtests/phase8_v2_variant_v005_eval.py`
* Git Blob SHA-1: `6291999b059facadf6ea40482f8413872cf4cd23`
* Canonical File Digest: `dd4d864e6caf3413447121bac9bc412c1db7a8df6243422840e0e5d59ca26683`
* Classification: `DEVELOPMENT_MEASUREMENT_PROVENANCE` (strictly separated from future Tier-B evaluation).

---

## 6. Research Cycle Closure & Retired Allowances

With the creation of `phase6-frozen-v2`, the Tier-A strategy development research cycle under `phase8-v2-research-charter-v1-8527e3a5eec98f53` is **PERMANENTLY CLOSED**:

* **Closure Record ID:** `phase6-development-v2-research-closure-v1`
* **Closure Reason:** `SINGLE_CANDIDATE_SELECTED_AND_FREEZE_AUTHORIZED`
* **Final Research Budget Ledger:**
  - Diagnostics: `5 / 12` executed (`7` unused and **RETIRED**)
  - Strategy Variants: `5 / 8` observed (`3` unused and **RETIRED**)
  - Numeric Parameter Trials: `0 / 4` executed (`4` unused and **RETIRED**)

### 6.1 Post-Freeze Research Prohibitions
1. No Variant 6 (`V006`) development or registration.
2. No new Tier-A strategy semantic modifications.
3. No numeric parameter tuning or optimization trials.
4. No diagnostic studies intended to modify candidate rules.
5. Any future strategy research requires a new charter identity.

---

## 7. Known Limitations, Contamination, and Risk Nuance

### 7.1 Tier-A Fold 01 Contamination
* Status: `CONTAMINATED_FOR_FUTURE_STRATEGY_DESIGN`
* Meaning: Fold 01 cannot be reused to develop, calibrate, or tune any future strategy.

### 7.2 Incremental Fallback Regime-Concentration Risk
Under audit qualification `phase8-v2-candidate-selection-audit-v1-RC001`:
* **Mandatory Risk Flag:** `TIER_B_REGIME_CONCENTRATION_RISK`
* **Scope:** Incremental V005 Directional Fallback Mechanism (21 candidates).
* **Evidence:**
  - `20 / 21` fallbacks occur in ISO weeks 17 and 18 (April 22 – May 3, 2024).
  - `20 / 21` fallbacks occur in the first half of Fold 01.
  - `16 / 21` fallbacks occur in the London session.
* **Prospective Warning:**
  > *V005 demonstrates the H009 mechanism on contaminated Tier-A Fold 01, but its incremental fallback contribution is temporally and session concentrated. This does not invalidate candidate-level §14 temporal stability, but persistence of the incremental mechanism across reserved periods is unestablished and must be treated as a Tier-B confirmation risk.*

### 7.3 Zero Profitability Evidence
This freeze establishes **opportunity adequacy and structural soundness only**.
It contains **zero** evidence of profitability, win rate, Sharpe ratio, or monetary edge. No trade execution simulation has been run.

---

## 8. Tier-B Status & Next Required Plan

* **Tier-A Folds 02–04:** Strictly **SEALED** and unopened.
* **Tier-B Holdout Dataset:** Strictly **SEALED** and unopened.
* **Post-2024 Data (2025+):** Strictly **SEALED** and unopened.

### 8.1 Next Scientific Action
The next task must create and preregister a prospective Tier-B Feasibility Plan before unsealing Fold 02. The plan must define:
1. Fold-02 release contract;
2. Raw-candidate futility screen;
3. Reserved-fold 60-candidate headroom reporting;
4. Completed-trade / lifecycle feasibility methodology;
5. Minimum completed-trade threshold;
6. Fold-boundary and open-position-at-end treatment;
7. Fill and slippage scenarios;
8. Fail-fast Fold 02 -> Fold 03 -> Fold 04 sequencing;
9. Progressive contamination transition for each unsealed fold;
10. Strict exclusion of profitability metrics during feasibility.

**NO TIER-B OBSERVATION IS PERMITTED IN THIS TASK.**

---

## 9. F001-TC001 — Complete Prospective Freeze Identity

- **Governance Record:** `phase6-frozen-v2-F001-TC001`
- **Record Classification:** `GOVERNANCE_AND_PROVENANCE_ONLY — ZERO_STRATEGY_SEMANTIC_CHANGE — ZERO_EMPIRICAL_ACCESS`
- **Manifest:** `baseline/phase8_v2_frozen_candidate_manifest_tc001.json` (schema `phase8v2.frozen-candidate-manifest.v2`)
- **Semantic Anchor Commit:** `2fd3460b9010d8cca548f4fd6980b6b34fe594e2`
- **Prospective Contract ID:** `canonical_git_blob_v1`
- **Historical F001 Status:** `PUBLISHED_PRE_TIER_B — SUPERVISORY_ACCEPTANCE_WITHHELD — INCOMPLETE_FREEZE_DEPENDENCY_SURFACE`
- **Scientific Status:** `CANONICALLY_SEALED_FOR_PROSPECTIVE_TIER_B_FEASIBILITY_PLAN_DESIGN`

### 9.1 Context and Preservation of Historical F001 Narrative
Under supervisory audit, historical freeze record `phase6-frozen-v2-F001` was identified as having four pre-Tier-B provenance and governance defects:
1. Incomplete strategy runtime dependency closure (the historical 7-path entrypoint identity was incomplete);
2. Incomplete configuration lock because the effective `XAUUSDm` symbol profile was not frozen;
3. Validation-pipeline and protected-infrastructure identities were asserted in prose but not cryptographically bound;
4. Hypothesis `phase8-v2-H007` lacked a terminal supervisory disposition record, leaving Charter §17 item 11 open.

**Crucial Governance Invariants:**
- **Candidate Selection Remains Valid:** `phase6-development-v2-V005` remains the single selected Charter §14 candidate (`SELECT_PHASE6_DEVELOPMENT_V2_V005_AS_SINGLE_FREEZE_CANDIDATE`).
- **Zero Strategy Code Modification:** The underlying strategy code at semantic anchor commit `2fd3460b9010d8cca548f4fd6980b6b34fe594e2` never changed and remains byte-identical.
- **Zero Empirical Access:** No empirical store (Fold 01, Fold 02–04, Holdout, or 2025+ data) was accessed during this correction.
- **Supersession for Prospective Use:** The historical 7-path aggregate digest (`22880f7acfb762b938997ef070fef13580679f37058f1853b8c8438fc9defc25`) is preserved historically as `HISTORICAL_PARTIAL_ENTRYPOINT_IDENTITY` and superseded for all future prospective Tier-B verification by `STRATEGY_SEMANTIC_IDENTITY_V2`.

### 9.2 Complete Strategy-Semantic Dependency Closure (`STRATEGY_SEMANTIC_IDENTITY_V2`)
Beginning from the 12 declared semantic roots:
- `bot/state/gate_inputs.py`
- `bot/state/gate_reducer.py`
- `bot/strategy/config.py`
- `bot/strategy/variant_v003.py`
- `bot/strategy/variant_v005.py`
- `strategies/smc_engine/entry_model.py`
- `strategies/smc_engine/strategy_state.py`
- `config/symbol_profiles/__init__.py`
- `config/symbol_profiles/base.py`
- `config/symbol_profiles/xauusdm.py`
- `utils/symbol_profiles.py`
- `bot/state/orchestrator.py`

A complete recursive AST dependency closure across repository-local Python modules was computed against committed Git bytes at the semantic anchor commit.
- **Path Count:** 83 unique paths (including `bot/analysis/*`, `bot/strategy/*`, `strategies/smc_engine/*`, `bot/execution/*`, `config/symbol_profiles/*`, `utils/*`).
- **Contract:** `canonical_git_blob_v1`
- **Aggregate SHA-256 Digest:** `ec4b5e6e6ded4797fce2d4d841d1b746e15f7435ac50569c62d6daa38953064f`

### 9.3 Effective XAUUSDm Configuration Lock & Complete Configuration Identity
- **Effective XAUUSDm Profile:** Derived deterministically from `config/symbol_profiles/base.py` + `xauusdm.py` via `utils/symbol_profiles.py`. Unbounded tier (`float("inf")`) canonicalized as `{"__unbounded_profile_max__": true}` with sorted keys and compact separators.
  - `effective_xauusdm_profile_sha256`: `7178799c23f85d5cfb867d73f1d9bcb74ae597beb88227ea9a217602770a879a`
- **Core StrategyConfig Identity:** Retained from F001:
  - Fingerprint: `6fce546fb4a3ad41c2fe6fb9`
  - Full SHA-256: `6fce546fb4a3ad41c2fe6fb98231ceb7840d15e60f234746d7c78c87d3791e19`
- **Complete Candidate Configuration Identity:** Deterministic JSON envelope `{"strategy_config": ..., "xauusdm_profile": ...}`:
  - `COMPLETE_CANDIDATE_CONFIGURATION_IDENTITY`: `1aa8b73fb207e10abfe9725bc2979e14692815a5ffe91502cef892b8bae6e806`

### 9.4 Prospective Validation Pipeline Identity (`VALIDATION_PIPELINE_IDENTITY_V1`)
Derived from the 23 validation roots (`bot/validation/development_plan_revision.py::CODE_COMPONENTS` non-test paths and empirical input pipeline sources) via recursive AST closure:
- **Path Count:** 147 unique paths.
- **Contract:** `canonical_git_blob_v1`
- **Aggregate SHA-256 Digest:** `957dba56e2244b8cae773ddc17c716da629732d3f492e77578978ef9e091da3f`

### 9.5 Protected Infrastructure Identity (`PROTECTED_INFRASTRUCTURE_IDENTITY_V1`)
All 17 Charter §5 protected safety controls are mapped to enforcing source modules, symbols, and committed Git blob IDs:
- **Enforcing Paths:** 11 unique modules (`bot/backtesting/models.py`, `bot/data/candles.py`, `bot/execution/broker/adapter.py`, `bot/execution/broker/validation.py`, `bot/execution/lifecycle/entry.py`, `bot/execution/news_filter.py`, `bot/execution/risk/authority.py`, `bot/execution/risk/sizing.py`, `bot/state/gate_inputs.py`, `bot/strategy/config.py`, `bot/strategy/setup_consumption.py`).
- **Contract:** `canonical_git_blob_v1`
- **Aggregate SHA-256 Digest:** `666be323da1f5634e00d5a3285089d9318c99b300696d1f621db4d2cf07f9d7d`

### 9.6 Terminal Scientific Ledger Seal & H007 Supervisory Disposition
- **`phase8-v2-H007-R001`:** Hypothesis `phase8-v2-H007` formally resolved as `SUPPORTED_BY_V002_STRUCTURAL_EVIDENCE` (qualified: `SUPPORTED_STRUCTURALLY_ON_CONTAMINATED_TIER_A — V002_OPPORTUNITY_INSUFFICIENT — NOT_SELECTED — NOT_PROFITABILITY_EVIDENCE`).
- **`phase8-v2-ledger-seal-v1`:** Authoritative terminality seal explicitly accounting for all hypotheses (H001..H009), all diagnostics (D001..D006), and all variants (V001..V005). Zero scientific entities remain unresolved.
- **Research Budgets:** Remain retired: diagnostics 5/12, variants 5/8, numeric trials 0/4.
