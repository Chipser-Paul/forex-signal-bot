# PHASE 8 V2 — STRATEGY VARIANT V003 PREREGISTRATION (GOVERNANCE ONLY)

## 1. Identity and Scope

* **Variant ID:** `phase6-development-v2-V003`
* **Title:** Causal Temporal FVG Evidence Memory
* **Variant Type:** `STRATEGY_VARIANT`
* **Classification:** `DEVELOPMENT_VARIANT_IMPLEMENTATION — V003 — NOT EMPIRICAL EVIDENCE`
* **Research Identity:** `phase6-development-v2` — Charter `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
* **Primary Hypothesis:** `phase8-v2-H003` — Order-Block and Fair-Value-Gap Temporal Association (`HYPOTHESIS_NOT_CONCLUSION`; status `SUPPORTED_BY_D005`)
* **Supporting Evidence:**
  * `phase8-v2-D005-R001` (D005 Fold-01 temporal diagnostic: H003 `SUPPORTED_BY_D005`, 36/42 temporal association decisions, median distance 1 bar / 5.0 minutes, headroom `TEMPORAL_VARIANT_HEADROOM_POSSIBLE`)
  * `phase6-development-v2-V002-R001` (V002 Fold-01 structural pair: 61 `candidate_ready`, `OPPORTUNITY_INSUFFICIENT` against target 90)
* **Forensic Status:** `phase8-v2-S002` clearance (`CURRENT_CANONICAL_STORE_VERIFIED_INTACT`, `V002_R001_NOT_IMPLICATED`)
* **Predecessor Variant:** `phase6-development-v2-V002`
* **Registration:** `baseline/phase8_v2_hypothesis_register.json` (appended in this commit)

## 2. Accepted Development Evidence Context

In V002 R001 (`phase6-development-v2-V002-R001`), the canonical structural pair implementation yielded 61 `candidate_ready` setups on Fold 01 (`OPPORTUNITY_INSUFFICIENT`, below the Tier-A engineering-density target of 90). V002 required that a same-direction final canonical FVG from the current unfilled surface coexist with a structurally active OB. Among the 526 Gate-11 entrants:
* 144 had structurally active OBs.
* 102 had both a structurally active OB and an associated final same-direction FVG (V002 Gate-11 passes).
* 42 had a structurally active OB but lacked an associated final same-direction FVG under final-surface semantics.

Diagnostic D005 R001 (`phase8-v2-D005-R001`) investigated those 42 decisions and established:
* **H003 Temporal Association:** 36 of the 42 decisions (85.7%) carry at least one same-direction canonical FVG that formed in ordered sequence **at or after** canonical OB confirmation.
* **Temporal Distance Offset:** The qualifying temporal offsets are highly structured and compact: median signed distance is exactly **1.0 bar (5.0 minutes)**, with 36 of 43 qualifying associations (83.7%) occurring at bar +1.
* **Headroom Feasibility:** The pool of qualifying temporal decisions (36) satisfies the arithmetic headroom bound ($90 - 61 = 29 \le 36$), resulting in classification `TEMPORAL_VARIANT_HEADROOM_POSSIBLE`.
* **Fill State Precedence:** All 113 causal FVGs detected across the primary-population decisions had been filled before the decision timestamp. Under V002's final-surface semantics (`get_unfilled_fvgs`), filled FVGs are excluded. Under an ordered temporal sequence, the displacement imbalance produced by the structural origin is preserved as historical evidence even if subsequently filled.

## 3. One Conceptual Change

V003 changes exactly **ONE** conceptual hypothesis relative to V002:

### V002 FVG Evidence
The Gate-11 FVG component is satisfied only by:
$$\text{same-direction FINAL canonical FVG present in the current unfilled surface } (F_{\text{final}})$$

### V003 FVG Evidence
The same component is satisfied by:
$$F_{\text{v003}} = F_{\text{final}} \lor F_{\text{temporal}}$$
where $F_{\text{temporal}}$ requires:
1. Canonical FVG detected by the frozen canonical detector (`bot.analysis.fvg_engine.detect_fvgs`) over the causal M5 frame through `decision_at`.
2. Same direction as the selected structural OB and requested trade side.
3. FVG formation is causally available (`fvg_formation_available_at <= decision_at`).
4. FVG formed at or after canonical OB confirmation (`fvg_formation_available_at >= block.confirmed_at`).

This second branch is **Causal Temporal FVG Evidence Memory**. Fill status does not erase the historical fact that a displacement imbalance occurred in ordered sequence following the order block.

## 4. Strict V002 Baseline Preservation

V003 is a strict semantic superset of V002 for all decisions possessing final-surface FVG evidence.
If $F_{\text{final}} == \text{True}$:
* V003 executes the V002 final-surface branch directly.
* V003 Gate-11 evidence equals V002.
* V003 exact-overlap descriptive metadata equals V002.
* V003 live FVG geometry equals V002.
* V003 entry context and Gate-12/13 result equal V002.
* No temporal-memory branch may alter or override the V002 result.

The temporal branch is an additional fallback activated **ONLY** when V002 lacks final-surface FVG evidence ($F_{\text{final}} == \text{False}$). This prevents any accidental regression of the 61-candidate V002 baseline.

## 5. Critical Evidence vs. Live-Zone Separation

A fundamental safety and scientific boundary governs V003: **historical filled temporal FVG evidence is NOT a live entry zone.**

When a decision qualifies via the temporal-only branch ($F_{\text{final}} == \text{False}$ and $F_{\text{temporal}} == \text{True}$):
* The historical filled FVG satisfies the confluence evidence check (proving that displacement imbalance accompanied the structural origin).
* The historical filled FVG **MUST NOT** populate:
  * `context["fvg_zone"]`
  * `strategy_state.fvg_zone`
  * pullback-entry geometry
  * limit-entry geometry
  * stop-loss geometry
  * take-profit geometry
  * risk-reward (RR) calculations.
* In such decisions, `live_fvg_zone` is explicitly set to `None`.
* The filled historical zone is never resurrected into live trading execution.

## 6. Strategy State Invariance

V003 evaluates evidence without mutating the canonical strategy state. For temporal-only decisions, V003 does **NOT** write, overwrite, or set:
* `state.displacement_seen`
* `state.fvg_zone`
* `state.structure_state`
* `state.liquidity_swept`
or any other state field.

Gate 12/13 consumes the exact canonical state reconstructed from the decision's own persisted `next_record`. V003 asks whether admitting historical displacement evidence into Gate 11 and canonical strategy unlocks valid trade setups under the already-existing frozen entry state; it does not manufacture artificial entry readiness.

## 7. Order-Block Semantics Invariance

V003 order-block semantics are byte- and behavior-identical to V002:
* Latest same-side canonical confirmed block selection.
* Causal confirmation requirement (`confirmed_at <= decision_at`).
* Rejection of consumed blocks.
* Rejection of invalidated blocks (invalidating close through the zone).
* First-interaction / mitigation tracking.
* Age $> 30$ bars alone does not reject an otherwise untouched and uninvalidated block.
* No order-block detection, scoring, or lifecycle rules are modified.

## 8. Causal FVG Clock and Ordering Rule

V003 preserves the exact causal clock semantics proven in D005 TC001:
* The canonical FVG detector records `source_index` for the middle displacement candle.
* FVG completion candle row: `source_index + 1`.
* FVG formation availability timestamp: completion candle's `available_at` (NOT `open_time`).
* Causal requirement: `fvg_formation_available_at <= decision_at`.
* Temporal ordering requirement: `fvg_formation_available_at >= block.confirmed_at`.
* Post-decision candles are never inspected; future leakage is strictly impossible.

## 9. Absence of Lag / Proximity Thresholds

In accordance with preregistered H003 semantics:
* **NO lag threshold** is introduced (no 1-bar, 2-bar, 6-bar, 10-bar, or 87-bar maximum).
* **NO minute or session window** is introduced.
* **NO ATR-scaled temporal threshold** is introduced.
* The empirical concentration at bar +1 observed in D005 R001 provides qualitative justification for H003 support, but is NOT converted into a tuned parameter.
* Numeric parameter trials remain strictly **`0 / 4`**.

## 10. Confluence Architecture and Weights

The Gate-11 confluence architecture remains strictly unchanged from canonical V1/V001/V002:
* **Weights:** `[2, 1, 2, 1, 2]`
  * HTF bias alignment: 2 points
  * Premium/discount location: 1 point
  * Canonical structurally active OB: 2 points
  * FVG structural evidence ($F_{\text{v003}}$): 1 point
  * Liquidity sweep: 2 points
* **Maximum Score:** 8 points.
* **Passing Threshold:** 8 / 8 points (unchanged; no 7/8 or 6/8 relaxation).

Only the internal interpretation of the existing 1-point FVG evidence component broadens from $F_{\text{final}}$ to $F_{\text{v003}}$.

## 11. Downstream Canonical Strategy and Gate 12/13

* **Canonical Strategy Adapter:** An isolated evaluator `evaluate_v003_strategy` mirrors V002's downstream adapter. For this isolated path, `SetupEvidence.fvg_overlaps_order_block` maps to `v003_fvg_evidence`.
* **Protected Engine Semantics:** Symbol allowlist, regime, bias, DXY, news, session, consumption, lifecycle, and risk authority remain completely untouched.
* **Gate 12/13 Entry Determination:** Uses the frozen `strategies.smc_engine.entry_model.determine_entry` unchanged.
  * `context["ob_zone"]` = live structurally active OB zone.
  * `context["fvg_zone"]` = `live_fvg_zone` (the final canonical unfilled FVG zone if present; `None` if temporal-only).
  * Frozen canonical state fields are consumed as reconstructed; no temporal geometry is injected.

## 12. Success Classification (Preregistered)

The Tier-A engineering-density target remains **`candidate_ready >= 90`** on Fold 01.

| Classification | Condition | Research Implication |
|---|---|---|
| `OPPORTUNITY_SUFFICIENT` | `candidate_ready >= 90` | Merits continued research only; establishes neither sample sufficiency nor profitability |
| `OPPORTUNITY_INSUFFICIENT` | `1 <= candidate_ready <= 89` | Insufficient opportunity density under Tier-A criteria |
| `NO_CANDIDATES` | `candidate_ready == 0` | Zero candidate yield |
| `IMPLEMENTATION_FAILED` | Defect or mismatch | Tooling or logic error |

### Headroom Upper Bound
$$\text{Upper Bound} = \text{V002 baseline } (61) + \text{D005 temporal associations } (36) = 97$$
This figure (97) represents an arithmetic upper bound assuming 100% downstream survival of temporal decisions. It is **NOT** an expected candidate count, and no tuning toward 90 is permitted.

## 13. Store Compatibility

The canonical Fold-01 store `fold-01-a8b406884ab3525a` (rows content SHA-256 `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22`) is semantically sufficient for V003 because:
1. It contains complete causal M5 `entry_rows` for every decision snapshot.
2. It contains the persisted final FVG surface.
3. D005 R001 already demonstrated deterministic reconstruction of historical causal FVGs from these identical store snapshots.
V003 measurement tooling will assert store compatibility fail-closed without modifying the store.

## 14. Prohibited Variant Shapes and Banned Outputs

* **Prohibited Modifications:**
  * Modifying `bot/strategy/variant_v002.py`
  * Modifying `strategies/smc_engine/entry_model.py` or `strategy_state.py`
  * Weakening DXY, news, session, or allowlist guards
  * Numeric lag parameters or cutoffs
  * Alternate score thresholds (no 7/8 or 6/8)
  * Resurrecting filled temporal FVG zones into live entry context
* **Banned Metric Outputs:**
  * Output containing P&L, win rate, profit factor, expectancy, drawdown, Sharpe, returns, optimal lag, or candidate counterfactuals fails closed.

## 15. Two-Phase Discipline & Budget

* **Phase A (This Commit):** Governance-only preregistration. Committed to `integration/phase8-checkpoint-20260921` and pushed to remote before any code implementation.
* **Phase B (Future Commit):** Isolated implementation (`bot/strategy/variant_v003.py`), measurement tooling (`backtests/phase8_v2_variant_v003_eval.py`), and comprehensive synthetic test suite.
* **Budget Status:**
  * Diagnostics executed: `4 / 12`
  * Strategy variants observed: `2 / 8`
  * Numeric parameter trials: `0 / 4`
  * Budget is **UNCHANGED** by Phase A preregistration and Phase B implementation/tooling.
  * Strategy variants will become `3 / 8` **ONLY** upon the first real empirical observation of Fold-01 data under separate supervisory authorization.
* **Reserved Evidence:** Tier B (Folds 02–04), 2025+ data, and holdout remain completely inaccessible and sealed.
