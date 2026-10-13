# Phase 8 V2 Strategy Variant V005: Eligibility-Scoped Requested-Side Entry Direction Authority

## 1. Specification Lineage & Research Scope

* **Variant Identifier**: `phase6-development-v2-V005`
* **Title**: Eligibility-Scoped Requested-Side Entry Direction Authority
* **Classification**: `DEVELOPMENT_VARIANT_IMPLEMENTATION — V005 — NOT PROFITABILITY EVIDENCE`
* **Governing Research Charter**: `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
* **Linked Effective Hypothesis**: `phase8-v2-H009-TC001` (*Entry Direction Authority Coherence*)
* **Historical Hypothesis**: `phase8-v2-H009`
* **Predecessor Scientific Baseline**: `phase6-development-v2-V003` (*Causal Temporal FVG Evidence Memory*)
* **Historical Blocked Implementation**: `phase6-development-v2-V004` (Attempt 1: `phase6-development-v2-V004-ATTEMPT1`, `IMPLEMENTATION_BLOCKED_POST_EXPOSURE`)
* **Status**: `REGISTERED_NOT_OBSERVED`
* **Target Domain**: Tier-A Fold 01 (`fold-01-a8b406884ab3525a`, `2024-04-01T00:00:00Z` to `2024-06-08T00:00:00Z`)
* **Reserved Evidence**: Folds 02–04, 2025+ data, and holdout remain strictly sealed and inaccessible.
* **Relationship to Blocked V004**: V005 is a **NEW** strategy variant that tests the same unresolved scientific hypothesis H009 with correctly scoped implementation semantics. It is **NOT** a V004 Attempt 2. Variant slot 4 was permanently consumed by V004 Attempt 1; V005 will consume variant slot 5 only upon its first separately authorized real Fold-01 observation.

---

## 2. Scientific Motivation & Lineage

In V003 empirical evaluation (`phase6-development-v2-V003-R001`), Gate-11 confluence passes expanded from 102 to 138, and canonical strategy passes expanded from 80 to 110, yielding 81 candidate-ready decisions (against the Tier-A adequacy target of 90, classifying V003 as `OPPORTUNITY_INSUFFICIENT`).

Diagnostic `phase8-v2-D006` investigated the remaining 29 decisions that passed Gate-11 confluence and canonical strategy protections but were rejected at Gate-12/13 entry execution (`P_ENTRY_REJECT`). The empirical observation revealed that 22 / 29 (75.86%) concentrated in E4 (`LIQUIDITY_ALIGNMENT_MISMATCH`) due to an internal authority conflict between Gate 11 input liquidity detection (conditioned on `htf_bias`) and Gate 12/13 entry routing and alignment (conditioned on `state.structure_dir`).

Variant V004 attempted to resolve this divergence. However, V004 Attempt 1 failed closed on the very first Gate-11 entrant decision (`2026-10-13T12:22:49Z`) because an executable directional consistency guard evaluated `pair.side` unconditionally across all Gate-11 entrants before checking whether the decision was fallback-eligible or baseline-ready. Gate-11 entrants with unformed structural pairs (`pair.side == StrategySide.FLAT`) were treated as directional contradictions. V004 completed zero Gate-11 observations, baseline reconciliation was not reached, and no valid R001 was sealed (`IMPLEMENTATION_BLOCKED_POST_EXPOSURE`).

Hypothesis H009 / H009-TC001 therefore remains completely **UNRESOLVED**. V005 is authorized to test this exact unresolved mechanism with correctly scoped guard semantics.

---

## 3. The One-Concept Rule: Eligibility-Scoped Direction Authority

V005 introduces exactly **ONE** conceptual change relative to frozen V003:

> **Eligibility-Scoped Gate-12/13 Directional Authority**:
> For setups that have already passed V003 Gate-11 confluence scoring (8/8) and canonical strategy protections, but did not return a baseline entry, the authoritative trade direction for Gate-12/13 entry routing and liquidity alignment interpretation is the requested trade side (`requested_side` derived from `htf_bias`), rather than a diverging persisted `state.structure_dir`.

The single technical difference between V005 and blocked V004 is the **scope** of the directional consistency invariant:
* Blocked V004 asserted directional consistency across **every** Gate-11 entrant, prematurely failing on normal pre-structural `StrategySide.FLAT` decisions.
* V005 evaluates directional consistency **only** after establishing that a decision has reached the actual H009 fallback surface.

All other pipeline stages, order block definitions, temporal FVG evidence memory, Gate-11 confluence weights, readiness predicates, liquidity alignment rules, risk controls, and broker protections remain completely frozen and unmodified.

---

## 4. Definition of Requested Trade Side

The authoritative trade direction is derived from the frozen decision context:
* **Source**: The higher-timeframe bias (`htf_bias`) evaluated at Gate 11.
* **Mapping**:
  * `"bullish"` $\rightarrow$ `requested_side = "bullish"` (Trade Direction = `BUY`)
  * `"bearish"` $\rightarrow$ `requested_side = "bearish"` (Trade Direction = `SELL`)
* **Fail-Closed Contract**: If `htf_bias` is missing, empty, or not in `{"bullish", "bearish"}`, evaluation fails closed; no fallback entry is possible.

---

## 5. Exact V005 Control Flow

Evaluation in `evaluate_v005_entry_readiness` executes in the following strict sequential order:

### Step A: V003 Baseline Preservation FIRST
If `v003_entry_ready == True` AND `v003_entry is not None`:
* Return the exact V003 entry immediately:
  * `entry_ready = True`
  * `entry_source = "V003_BASELINE"`
* **Zero V005-specific guards** may run before this return. Existing V003 baseline candidates bypass all fallback checks.

### Step B: Fallback Eligibility Check
If NOT (`v003_gate11_passed == True` AND `v003_strategy_eligible == True`):
* Return immediately:
  * `entry_ready = False`
  * `entry_source = "NONE"`
* Decisions that failed Gate-11 or canonical strategy protections (including decisions where `pair.side == StrategySide.FLAT`) exit cleanly here without raising exceptions.

### Step C: Requested Side Resolution
Resolve `req_side = str(requested_side).lower()`. If `req_side` is not in `{"bullish", "bearish"}`:
* Return `(None, False, "NONE")`.

### Step D: Structural Pair Direction Invariant (Fallback-Eligible Only)
Only upon reaching this fallback-eligible stage is the structural pair validated:
1. `pair` must not be `None`.
2. `pair.structurally_active` must be `True`.
3. `pair.side` must be in `{StrategySide.LONG, StrategySide.SHORT}`.
4. Directional agreement:
   * If `req_side == "bullish"`, `pair.side` must be `StrategySide.LONG`.
   * If `req_side == "bearish"`, `pair.side` must be `StrategySide.SHORT`.
5. **Contract Violations at this Stage**:
   * If `pair.side == StrategySide.FLAT`, raise `V005VariantError` (a true 8/8 H009 fallback candidate must possess a formed directional structural pair).
   * If `pair.side` opposes `req_side`, raise `V005VariantError`.
   * If `pair.structurally_active` is `False`, raise `V005VariantError`.

### Step E: Persisted State Requirements
1. `state` must not be `None`.
2. Persisted structure direction `state.structure_dir` must be in `{"bullish", "bearish"}`. If unresolved, return `(None, False, "NONE")`.
3. Persisted direction must differ from requested side: `state.structure_dir != req_side`. If `state.structure_dir == req_side`, directional divergence is absent; preserve V003 rejection without fallback (`(None, False, "NONE")`).

### Step F: Frozen Readiness & Early-Entry Evaluation (E2 Untouched)
1. Evaluate frozen state readiness using `state.ready_for_entry()`.
2. If readiness fails, evaluate frozen `_can_use_early_entry(...)` from `strategies/smc_engine/entry_model.py`:
   * At score 8, allowed missing conditions are strictly `{'Confirmed structure'}`.
   * Eligible structure states are `{'transition', 'range'}` or `None`.
   * Internal confirmation (`internal_bos_seen`, `choch_seen`, or `sweep_rejected`) is strictly required.
   * Conjunction requires internal confirmation `AND` (`zone_context` `OR` `priority_context`).
3. If neither standard readiness nor early-entry permits continuation, return `(None, False, "NONE")`. All 7 D006 E2 rejections remain rejected.

### Step G: Private-Copy State Authority & Entry Determination
1. Deep-copy the authoritative state: `copied_state = copy.deepcopy(state)`.
2. Apply the single intentional modification: `copied_state.structure_dir = req_side`.
3. Invoke frozen `determine_entry(symbol, current_price, copied_state, context, score)`.
4. If an entry is returned:
   * Return `(entry, True, "V005_DIRECTIONAL_FALLBACK")`.
5. Otherwise, return `(None, False, "NONE")`.

---

## 6. Contrast with Blocked V004

| Aspect | Blocked V004 | Corrected V005 |
| :--- | :--- | :--- |
| **Guard Placement** | Pre-eligibility (runs on all 526 Gate-11 entrants) | Post-eligibility (runs only on 8/8 strategy-eligible candidates) |
| **Gate-11 Failed Entrant with FLAT Pair** | Crashed with `V004VariantError` | Returns `(None, False, "NONE")` cleanly |
| **Strategy-Ineligible with FLAT Pair** | Crashed with `V004VariantError` | Returns `(None, False, "NONE")` cleanly |
| **V003 Baseline Candidate with FLAT Pair** | Evaluated guard before returning baseline | Returns exact baseline entry immediately in Step A |
| **8/8 Fallback Candidate with FLAT Pair** | Crashed | Raises `V005VariantError` (fail-closed contract) |
| **8/8 Fallback Candidate with Opposing Pair** | Crashed | Raises `V005VariantError` (fail-closed contract) |

---

## 7. Strict V003 Baseline Preservation

* **Primary Path**: All 81 candidate-ready decisions from sealed V003 R001 are returned with zero modification.
* **Source Label**: `v005_entry_source = "V003_BASELINE"`.
* **Geometry Preservation**: Entry type, market/pullback entry, limit price, stop loss, take profit, and setup ID are byte-identical to sealed V003 R001.

---

## 8. Frozen Liquidity Rules Invariance

Valid combinations remain strictly:
* **Bullish**: `sell + equal_lows` OR `buy + internal_continuation`.
* **Bearish**: `buy + equal_highs` OR `sell + internal_continuation`.

No wildcard combinations, relaxation, or new liquidity classes are introduced.

---

## 9. Canonical State Invariance

* Authoritative `StrategyState` instances are never mutated.
* Fallback operates exclusively on private deep copies (`copy.deepcopy(state)`).
* The only intentional state mutation on the private copy is `copied_state.structure_dir = requested_side`.

---

## 10. Sealed V003 Baseline Reconciliation Contract

V005 measurement tooling requires the `--v003-result` CLI flag pointing to sealed V003 R001 (`phase6-development-v2-V003_result.json`, SHA-256 `50117c399481a2e31b8da6260da4e05c8719a522efb524f80bb2063319c41ff8`, 45,221 bytes).
Reconciliation verifies:
1. Exact upstream reproduction: Gate-11 entrants (526), Gate-11 passers (138), canonical-strategy passers (110), candidate-ready (81).
2. Exact `(decision_id, setup_id)` multiset equality.
3. 81 unique setup IDs, 0 duplicates.
4. Exact deterministic JSON entry-object matching via `json.dumps(entry, sort_keys=True, separators=(",", ":"), allow_nan=False)`.

---

## 11. Target Metric & Decision Rules

* **Target Domain**: Tier-A Fold 01 (`fold-01-a8b406884ab3525a`).
* **Primary Target**: Raw `candidate_ready >= 90`.
* **Classification Rules**:
  * `raw candidate_ready >= 90`: `OPPORTUNITY_SUFFICIENT` (merits continued research; does NOT authorize Tier B without supervisory candidate-freeze review).
  * `0 < raw candidate_ready < 90`: `OPPORTUNITY_INSUFFICIENT`.
  * `raw candidate_ready == 0`: `NO_CANDIDATES`.
* **Setup Duplication**: Reported as a separate stability criterion; does not alter raw candidate classification.
* **Candidate Source Accounting**: Exact accounting of `V003_BASELINE` + `V005_DIRECTIONAL_FALLBACK` == total raw `candidate_ready`.
* **No Predictive Arithmetic**: No rescue count or expected candidate number is encoded or predicted.

---

## 12. Prohibitions & Governance Safeguards

* **Zero Numeric Parameters**: 0 / 4 numeric parameter trials.
* **Zero Profitability Metrics**: P&L, win rate, profit factor, expectancy, drawdown, Sharpe, returns, and account balance are strictly prohibited.
* **Tier B Remains Sealed**: Folds 02–04, holdout, and 2025+ data remain inaccessible.
* **Zero Empirical Execution**: This specification and its implementation freeze authorize zero empirical store access. Real observation requires separate supervisory authorization.
