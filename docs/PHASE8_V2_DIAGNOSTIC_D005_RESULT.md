# PHASE 8 V2 — DIAGNOSTIC D005 RESULT (R001)

## Identity

* **Diagnostic:** `phase8-v2-D005` — Temporal Order-Block and Fair-Value-Gap Association Diagnostic
* **Diagnostic type:** `DIAGNOSTIC_INVESTIGATION`
* **Primary hypothesis:** `phase8-v2-H003` — Order-Block and Fair-Value-Gap Temporal Association (`HYPOTHESIS_NOT_CONCLUSION`; statement unchanged since preregistration)
* **Classification of this evidence:** `DEVELOPMENT_DIAGNOSTIC_EVIDENCE — D005 — FOLD01 — NOT PROFITABILITY EVIDENCE`
* **Research identity:** `phase6-development-v2` — Charter `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
* **Preregistration commit:** `df19e89a8afd72deda2b58c79f38a798daaead76` (ordering-only correction `c615c3e9ae15f6c47b1b9da27b835d46a431b05c`)
* **Frozen tooling commit (the only authorized identity):** `519902bc5db895f690568170909f82213be79545` (parent `05f4e6a9d0f5c4465d82e48a50a559c07ceed7b6`, tree `eb5f59695adde843bf28aa3d4ce4de73b9b414fc`)
* **Tooling fingerprint:** `canonical_git_blob_v1` = `bf13cd30037d97c57ef0e478db4a436503da7edb4db1ea8b441c88f9b87cdb52` (recomputed from committed Git blob; worktree byte-identical)
* **V002 implementation commit:** `4890dcbce8579f159224b653d94f634cc9017549` (`bot/strategy/variant_v002.py` canonical Git blob `8272c28552c05067b6dc3ba039ee8df2dbbfb8b4`)
* **Specification document:** `docs/PHASE8_V2_DIAGNOSTIC_D005.md` (SHA-256 `7f754232731139816be5597aedadc4a069ead06d53c10423a7a88cd3d5f83d26`)
* **Result record:** `phase8-v2-D005-R001` (appended to `baseline/phase8_v2_hypothesis_register.json`)

## Motivation and Lineage

D005 was preregistered to investigate hypothesis `phase8-v2-H003`: that order-block (OB) and fair-value-gap (FVG) structural evidence may be causally related across a short temporal sequence rather than being required to appear simultaneously on the final completed candle.

In V002 R001 (`phase6-development-v2-V002-R001`), the canonical structural pair implementation yielded 61 `candidate_ready` setups on Fold 01 (`OPPORTUNITY_INSUFFICIENT`, below the Tier-A target of 90). V002 required that a same-direction final canonical FVG coexist with a structurally active OB. Among the 526 Gate-11 entrants, 144 had structurally active OBs, but 42 of those lacked an associated final same-direction FVG under final-surface semantics. D005 measures whether those 42 decisions were accompanied by causally detected canonical FVGs forming across an ordered sequence at or after OB confirmation, and measures the temporal distance distribution of those associations.

## Execution and Budget History

* **Diagnostic budget exposure instant:** `2026-09-26T13:18:42.145570+00:00` (Attempt 1 first authorized store processing). From this instant, diagnostics are permanently **`4 / 12` executed** (never refunded; subsequent attempts complete the already-consumed slot).
* **Attempt 1 (VOID — aggregation fail-closed):** Executed `2026-09-26T13:18:42.145570+00:00`. Completed the 13,269-snapshot loop but failed closed in `aggregate_d005` due to an invalid partition assertion (`ReconciliationError: primary population 42 != structurally-active without final FVG R2=34`) caused by assuming FVG association was a subset of structurally active blocks. Sealed as `phase8-v2-D005_ATTEMPT1_BLOCKAGE.json` (SHA-256 `168ea3b27eb5cf536cca338bd87de028e2da2abd055ed112e85c508e1886f6e2`, 3,692 bytes). Tooling corrected via `phase8-v2-D005-TC002` (commit `05f4e6a9d0f5c4465d82e48a50a559c07ceed7b6`).
* **Attempt 2 (VOID — pre-observation CLI error):** Executed `2026-09-28T20:56:32.229086Z` to `2026-09-28T20:56:45.660600Z`. The committed CLI called `FoldFeatureStore.open(args.store)`, but the canonical infrastructure exposes only the module function `load_feature_store`. Failed closed before store opening (empirical exposure ZERO). Sealed as `phase8-v2-D005_ATTEMPT2_BLOCKAGE.json` (SHA-256 `5a1c9482c569d0e614ef08f6e3fe9d8323381222de31487d4f608b2d8644f1cf`, 6,690 bytes) and log `phase8/logs/d005_rerun.log` (SHA-256 `5ed6b39041fc86b2907e463bc4a0644b2e83b91a57b8e7b4465981f8da610b66`, 407 bytes). Tooling corrected via `phase8-v2-D005-TC003` (commit `519902bc5db895f690568170909f82213be79545`).
* **Attempt 3 (VOID — transient row decompression anomaly):** Executed `2026-09-29T15:18:33.354671+00:00` to `2026-09-29T15:18:51.011401+00:00`. The committed CLI executed `load_feature_store(verify_rows=True)` and failed at row position 1572 decompressing `gate_payload_z` with `zlib.error: Error -3 while decompressing data: invalid distance too far back`. Failed closed before `run_d005` began (empirical exposure ZERO). Sealed as `phase8-v2-D005_ATTEMPT3_BLOCKAGE.json` (SHA-256 `20a4dbe152821af1a2c09f42094473351b52399d94e8bd7b661f6a12897be449`, 6,657 bytes) and log `phase8/logs/d005_attempt3.log` (SHA-256 `a2a6582366c044c891ae59ac795e3b070868c38d8d57a547736f3961acb484ce`, 785 bytes). Triggered mandatory forensic audit S002.
* **Attempt 4 (SUCCESSFUL EMPIRICAL COMPLETION — R001):** Executed `2026-09-29T15:46:22.1605167Z` to `2026-09-29T15:53:15.1822061Z`. Full verification passed, all 13,269 snapshots evaluated, all reconciliation checks passed, and `phase8-v2-D005_result.json` was sealed.
* **Budget after result:** Diagnostics `4 / 12` executed; strategy variants `2 / 8` observed; numeric parameter trials `0 / 4`. Upward budget revision prohibited (`ACTIVE`).

## Dedicated S002 Forensic Audit Clearance

Following the Attempt 3 blockage, forensic audit `phase8-v2-S002` (*Fold-01 Feature-Store Byte and Codec Provenance Audit*) was conducted and sealed:
* **Audit JSON Report:** `phase8/forensics/S002/phase8-v2-S002_report.json` (12,997 bytes, SHA-256 `8c73ae26eb691a7299d8a8ebcff217cf715d4872142bc4ff3da38bb0f8cee7ac`)
* **Audit Markdown Report:** `phase8/forensics/S002/phase8-v2-S002_report.md` (3,130 bytes, SHA-256 `940df4c3c1824303f0444129cf5060a399d7d6f5d4becdd357c047e4b22c2ee2`)
* **Supervisory root-cause classification:** `PROVENANCE_INSUFFICIENT_TO_DISTINGUISH`
* **Operational store status:** `CURRENT_CANONICAL_STORE_VERIFIED_INTACT`
* **V002 impact:** `V002_R001_NOT_IMPLICATED`

The audit established that:
1. Physical store files (`features.parquet`, `manifest.json`, `index.json`, `completion.marker`) have mtimes dated 2026-09-23T17:30:20Z and have remained untouched since publication.
2. The physical SHA-256 of `features.parquet` (`508bd4186caaacbb0c19bca1d545ce5454aacf751754b4adf0222987790bfc60`) exactly matches the published completion marker.
3. Logical row digest across all 13,269 rows recomputed to `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22` (matching V002 R001 sealed identity).
4. Codec scan across all 13,269 rows: 5,953 empty payloads, 7,316 non-empty payloads; all 7,316 non-empty payloads start with standard `789c` zlib header and decompressed cleanly with **zero decompression errors**.
5. Row 1572 static inspection: 7,400 compressed bytes, SHA-256 `366a00854e5a7c74...`, decompressed to 47,751 valid JSON bytes containing `htf_bias: "bullish"`. Four independent read modes returned identical bytes.
6. The Attempt 3 failure was classified as a non-reproducible transient background execution / PyArrow C++ ChunkedArray indexing anomaly under Windows AMD64 process execution. The store was formally cleared for Attempt 4 without modification.

## Store and Tooling Provenance

* **Store:** `fold-01-a8b406884ab3525a`, coverage `fold-01/full`, 13,269 decision snapshots.
* **Store identity SHA-256:** `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4` (verified before observation).
* **Rows content SHA-256:** `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22` (verified via `load_feature_store(verify_rows=True)`).
* **Fold 01 boundary:** `["2024-04-01T00:00:00+00:00", "2024-06-08T00:00:00+00:00"]`.
* **Prohibited historical store:** `fold-01-1d710826193a6767` never opened.
* **Reserved evidence untouched:** Fold 02, Fold 03, Fold 04, 2025+ data, and holdout remain sealed. Tier B remains sealed.

## Decision Accounting

```
13,269 scheduled = 7,316 reducer_classified + 4,815 missing_history + 1,138 unavailable_input + 0 evaluation_error
```
Reconciles exactly, reproducing the canonical decision accounting contract.

## Gate Funnel

| Gate | Entered | Passed | Failed |
|---|---|---|---|
| `gate_8_liquidity` | 7,316 | 3,607 | 3,709 |
| `gate_9_displacement` | 3,607 | 1,489 | 2,118 |
| `gate_10_internal_structure` | 1,489 | 526 | 963 |
| `gate_11_confluence_score` | 526 | 1 | 525 |
| `canonical_strategy` | 1 | 0 | 1 |

Identical to D003, D004, and V002 upstream funnels — D005 is a strictly read-only observer.

## D005 Population and Four-Cell Contingency

Gate-11 entrants: **526 decisions**.

### Reference Populations Partition
* **R1 (`ACTIVE_ASSOCIATED`):** 102 decisions (structurally active OB with final same-direction FVG).
* **R2 (`ACTIVE_NOT_ASSOCIATED` — D005 Primary Population):** **42 decisions** (structurally active OB without final same-direction FVG).
* **R3 (Non-active decisions):** 382 decisions (UNAVAILABLE 275, MITIGATED 92, INVALIDATED 15).
* Partition equation: `102 + 42 + 382 = 526` (exact partition of Gate-11 entrants).

### Four-Cell Contingency Table
| | Associated Final Same-Direction FVG = True | Associated Final Same-Direction FVG = False | Total |
|---|---|---|---|
| **Structurally Active OB = True** | 102 (`ACTIVE_ASSOCIATED`) | **42** (`ACTIVE_NOT_ASSOCIATED`, Primary) | **144** |
| **Structurally Active OB = False** | 8 (`NONACTIVE_ASSOCIATED`) | 374 (`NONACTIVE_NOT_ASSOCIATED`) | **382** |
| **Total Entrants** | **110** | **416** | **526** |

* Active marginal reconciles: `102 + 42 = 144`.
* Associated marginal reconciles: `102 + 8 = 110`.
* Primary decision-ID set reconciles exactly with `R2`.
* Side distribution of Primary Population (42 decisions): **LONG = 17, SHORT = 25**.

## H003 Temporal Association Observations

The preregistered H003 temporal association rule tests whether for a primary-population decision, at least one same-direction canonical FVG formed **at or after** canonical OB confirmation in the causal frame.

* **Primary Population Decisions:** 42
* **H003 Temporal Association Decisions:** **36**
* **Temporal Association Rate:** **85.7%** (36 / 42)

In 36 of the 42 decisions where V002 rejected a structurally active OB due to the absence of a final same-direction FVG, at least one same-direction canonical FVG formed in ordered sequence following the confirmation of that OB.

## Temporal Distance Surface

Over the qualifying temporal associations (43 total qualifying FVG associations across the 36 decisions):

| Metric | Signed Distance (Bars) | Absolute Distance (Bars) | Elapsed Time (Minutes) |
|---|---|---|---|
| Min | 1 | 1 | 5.0 |
| Max | 87 | 87 | 435.0 |
| Median | **1.0** | **1.0** | **5.0** |
| P25 | 1.0 | 1.0 | 5.0 |
| P50 | 1.0 | 1.0 | 5.0 |
| P75 | 1.0 | 1.0 | 5.0 |

### Exact Integer Histogram of Signed Distance (Bars)
* **+1 bar:** **36 associations** (83.7% of all qualifying associations)
* **+2 bars:** 1 association
* **+6 bars:** 3 associations
* **+87 bars:** 3 associations

The empirical temporal offset is **extraordinarily compact and structured**: the modal and median offset is exactly **1 bar (5.0 minutes)**. The FVG forms on the immediate next candle completing the displacement that confirms the order block. It is not temporally diffuse.

## Final Surface Attrition Decomposition

The 42 decisions in the primary population decompose exhaustively and mutually exclusively across the preregistered attrition categories:

| Attrition Category | Count | Percentage | Description |
|---|---|---|---|
| `SAME_DIRECTION_FVG_EXISTED_BUT_FILLED` | **36** | 85.7% | Same-direction FVG formed at/after OB confirmation, but filled before the decision timestamp |
| `SAME_DIRECTION_FVG_PRE_OB_ONLY` | 4 | 9.5% | Same-direction FVG formed prior to OB confirmation only (no temporal post-OB sequence) |
| `NO_SAME_DIRECTION_FVG_EVER` | 1 | 2.4% | No same-direction FVG detected anywhere in the causal frame |
| `OPPOSITE_DIRECTION_ONLY` | 1 | 2.4% | Only opposite-direction FVG detected in the causal frame |
| **Total** | **42** | **100.0%** | Reconciles exactly to Primary Population |

## Temporal FVG Universe Surface

Across the causal history of the primary-population decisions:
* **Total Causal FVGs detected:** 113
* **Direction:** Same-direction = 93; Opposite-direction = 20.
* **Formation Order relative to OB:**
  * `BEFORE_OB_CONFIRMATION`: 69
  * `AT_OB_CONFIRMATION`: 0
  * `AFTER_OB_CONFIRMATION`: 44 (43 same-direction + 1 opposite-direction)
* **Fill States at Decision:**
  * `filled_before_decision`: 113 (100%)
  * `unfilled_at_decision`: 0 (0%)

Every causal FVG observed in these 42 decisions had been filled before the causal decision timestamp. Under V002's final-surface semantics (`get_unfilled_fvgs`), filled FVGs are excluded. Under a temporal-association sequence, the existence of the displacement imbalance following the OB is preserved even if subsequently mitigated/filled prior to entry.

## Headroom Feasibility Evaluation

* **Tier-A Research Target:** 90 candidate observations.
* **V002 R001 Baseline Candidates:** 61 candidate observations.
* **Arithmetic Headroom Deficit:** `90 - 61 = 29` observations.
* **D005 Temporal Associations Observed:** **36 decisions**.
* **Feasibility Condition:** `36 >= 29`.
* **Classification:** **`TEMPORAL_VARIANT_HEADROOM_POSSIBLE`**

> [!NOTE]
> Headroom feasibility is an **arithmetic necessary condition only**. It establishes that the pool of qualifying temporal decisions (36) is mathematically large enough that, if combined with the baseline (61), a variant could theoretically reach 90. It is NOT a candidate prediction, NOT an H003 support threshold, and NOT a guarantee that any future variant will reach 90.

## H003 Scientific Disposition

**`SUPPORTED_BY_D005`**

### Scientific Basis
1. **Material Population:** The primary population is substantial (42 decisions; 29.2% of all 144 structurally active OB decisions), disproving the failure mode that active OBs without final FVGs are negligible or near-zero.
2. **Dominant Temporal Association:** 36 of the 42 decisions (85.7%) exhibit an ordered temporal sequence where a same-direction canonical FVG formed at or after OB confirmation.
3. **Structured, Non-Diffuse Offsets:** The qualifying temporal offsets are highly structured, with a median signed distance of exactly **1 bar (5.0 minutes)** and 83.7% of associations occurring at bar +1. This directly satisfies the preregistered economic rationale: price displacement produces the imbalance immediately following the structural origin zone.
4. **Refutation of Failure Mode:** H003's preregistered failure mode ("If causal OB/FVG pairs are temporally diffuse or absent, temporal association is not economically meaningful") is **refuted on Fold 01**.

### Honest Counterweights
* **Fill State Precedence:** All 113 causal FVGs in these decisions had filled before the decision timestamp. A strategy variant leveraging temporal association must address whether filled FVGs retain structural validity or whether additional mitigation constraints are required.
* **Downstream Funnel Attrition:** D005 measures structural association at Gate 11. It does not evaluate whether these 36 decisions would survive downstream risk-reward, entry readiness, or trade filters.

## What D005 Does NOT Establish

* **No Candidate Prediction:** D005 does NOT claim that 36 (or any number of) candidates would be generated. No counterfactual candidate arithmetic was performed.
* **No Optimal Lag Cutoff:** D005 tested NO lag windows, tolerance bands, or parameter sweeps (no 1-bar, 2-bar, 5-bar, or ATR cutoffs).
* **No Profitability Evidence:** D005 contains ZERO financial or performance metrics (no P&L, win rate, Sharpe ratio, drawdown, or trade outcomes).
* **No Automatic V003 Authorization:** D005 is a diagnostic investigation only. V003 is NOT created or authorized by this result.
* **Tier-B Invariance:** Tier B (Folds 02–04), 2025+ data, and holdout remain completely untouched and sealed.

## V003 Status

**`V003 = NOT CREATED`**

Tier B remains sealed. Any subsequent strategy variant (e.g. V003) requires separate supervisory preregistration and authorization.

---

### External Sealed Result Binding

* **Result Path:** `phase8_data::/v2_diagnostics/phase8-v2-D005/fold01/phase8-v2-D005_result.json`
* **Result SHA-256:** `fc852ed282ffe06036ba27b098086444d6eba37c3d7cf275b8f30ebd2d7efebc`
* **Result Bytes:** 23,699 bytes
* **Attempt 1 Blockage:** `phase8-v2-D005_ATTEMPT1_BLOCKAGE.json` (SHA-256 `168ea3b27eb5cf536cca338bd87de028e2da2abd055ed112e85c508e1886f6e2`, 3,692 bytes)
* **Attempt 2 Blockage:** `phase8-v2-D005_ATTEMPT2_BLOCKAGE.json` (SHA-256 `5a1c9482c569d0e614ef08f6e3fe9d8323381222de31487d4f608b2d8644f1cf`, 6,690 bytes)
* **Attempt 3 Blockage:** `phase8-v2-D005_ATTEMPT3_BLOCKAGE.json` (SHA-256 `20a4dbe152821af1a2c09f42094473351b52399d94e8bd7b661f6a12897be449`, 6,657 bytes)
* **S002 Forensic Audit Report:** `phase8-v2-S002_report.json` (SHA-256 `8c73ae26eb691a7299d8a8ebcff217cf715d4872142bc4ff3da38bb0f8cee7ac`, 12,997 bytes)
