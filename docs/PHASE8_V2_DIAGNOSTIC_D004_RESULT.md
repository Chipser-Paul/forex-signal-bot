# PHASE 8 V2 — DIAGNOSTIC D004 RESULT (R001)

## Identity

* **Diagnostic:** `phase8-v2-D004` — Expired Order-Block Structural Fate Decomposition
* **Diagnostic type:** `DIAGNOSTIC_INVESTIGATION`
* **Primary hypothesis:** `phase8-v2-H006` — Fixed Order-Block Expiry May Preempt Structural Lifecycle Evidence (`HYPOTHESIS_NOT_CONCLUSION`; statement unchanged since preregistration)
* **Classification of this evidence:** `DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE`
* **Research identity:** `phase6-development-v2` · Charter `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
* **Preregistration commit:** `e37b522238ad1b7b2548da75055080832f4099b6` (spec `docs/PHASE8_V2_DIAGNOSTIC_D004.md`, SHA-256 `cededb5f495d142d5713f691eec8c9b7efb604082ca4b722f6cfb72881a86392`)
* **Frozen tooling commit (the only authorized identity):** `b68d4e84e0ce475a311355f50748671feda53ba6` (parent `e37b5222…`, tree `9b991c10d656a81248bed92e39d79b17b8e25f37`)
* **Tooling fingerprint:** `canonical_git_blob_v1` = `b71c2440c4bd8e7763e7c419d3210852ad473fe3c88d6ec2f65af12c38f82dae` (recomputed from committed blob bytes during preflight; worktree byte-identical)
* **Result record:** `phase8-v2-D004-R001` (appended to `baseline/phase8_v2_hypothesis_register.json`)

## Motivation and V002 deferral

D003 R001 (`phase8-v2-D003-R001`, H002 `SUPPORTED_BY_D003`) observed canonical lifecycle EXPIRED as the dominant later lifecycle state among Gate-11 entrants, and the canonical `evaluate_order_block` short-circuits to `EXPIRED` (`block_expired`) when causally available post-confirmation bars exceed `order_block_expiry_bars` — BEFORE its mitigation/invalidation loop — potentially collapsing several distinct structural fates into one label. Motivation only: no D003 count was used as a target, expectation or oracle, and H002 is not reopened or reinterpreted. The supervisory V002 decision (`DEFERRED — DO NOT CREATE V002 YET`, because a canonical-OB substitution variant is mathematically incapable of reaching `candidate_ready >= 90` when canonical eligible = 87 < 90) made measuring the dominant lifecycle restriction the correct next step.

## Execution / budget

* **Budget-exposure instant (first store load attempt):** `2026-09-25T13:51:26.755772+00:00` — from this instant diagnostics are permanently **`3 / 12` executed** (never refunded, including the attempt-1 blockage below).
* **Attempt 1 (VOID — driver preflight, no observation):** at 13:51:26Z the untracked execution driver fail-closed in its own preflight identity assertion (it required the store identity SHA as a value inside the identity JSON; the canonical identity SHA is the digest OF that JSON). Zero snapshots were classified, evaluated or observed; the frozen tooling never began; nothing was written. Sealed as `phase8-v2-D004_ATTEMPT1_BLOCKAGE.json` (SHA-256 `ad789aea9ca06ef8d6beb80dadbf3ca6c5246bee07daa85a3e4405ece4a8dcdd`, 2,523 bytes), preserved intact. The frozen tooling module was NOT modified; only the driver's preflight check was corrected.
* **Valid run (R001):** started `2026-09-25T13:53:24.235052+00:00`, finished `2026-09-25T13:56:20.480636+00:00` (176.2 s), store identity and rows verified immediately before observation.
* **Budget after result:** diagnostics `3 / 12`; strategy variants `1 / 8`; numeric parameter trials `0 / 4`; upward-revision lock `ACTIVE`. No strategy variant and no numeric trial consumed.

## Store and tooling provenance

* Store `fold-01-a8b406884ab3525a`, coverage `fold-01/full`, 13,269 decision snapshots.
* Store identity SHA-256 `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4` — **recomputed from the loaded identity JSON** (SHA-256 of the canonical sorted/compact identity document) and matched exactly before observation.
* Rows-content SHA-256 `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22` — verified via `verify_rows=True` load.
* `plan_fingerprint` `adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09`; `pipeline_fingerprint` `b5a7ca17fd29aa593a5dce32e581cb4ff343b3a068142aace59a79da65d2065f`; `input_index_sha256` `e460066f4ebde8871eff44f874a6f7882a9a57524d5be358670c528e407846ba`.
* `canonical_commit == tooling_commit == b68d4e8…`; the tooling's own provenance block re-verified the committed-blob fingerprint inside the run.
* Prohibited historical store `fold-01-1d710826193a6767` never opened. Tier B never touched.

## Accounting

`13,269 = 7,316 + 4,815 + 1,138 + 0` — scheduled snapshots = reducer-classified (7,316) + missing_history (4,815; all `early_exit`) + unavailable_input (1,138; all `dxy_blocked`) + evaluation_error (0). Reconciles exactly, and reproduces the D001/D003 classification contract byte-for-byte at the accounting level.

## Gate funnel

| Gate | Entered | Passed | Failed |
|---|---|---|---|
| gate_8_liquidity | 7,316 | 3,607 | 3,709 |
| gate_9_displacement | 3,607 | 1,489 | 2,118 |
| gate_10_internal_structure | 1,489 | 526 | 963 |
| gate_11_confluence_score | 526 | 1 | 525 |
| canonical_strategy | 1 | 0 | 1 |

Identical to D003 R001's funnel — the pipeline is unchanged; D004 is a read-only observer on the same decisions.

## EXPIRED population

**133 blocks** — every Gate-11 entrant whose frozen canonical evaluation returned `BlockState.EXPIRED` with a confirmed same-side block (reason `block_expired`), derived naturally at execution time. Partition of all 526 entrants: EXPIRED 133 + ELIGIBLE 87 + MITIGATED 28 + INVALIDATED 3 + RETEST_ELIGIBLE 0 + UNAVAILABLE (count-only) 275 = 526.

## Raw fate predicates

Over the 133 EXPIRED blocks (raw, independent; overlap allowed):

| Predicate | Count |
|---|---|
| zone_overlap_before_decision | 76 |
| no_zone_overlap | 57 |
| invalidating_close | 49 |
| untouched_through_decision | 57 |
| first_retest_on_final_candle | 0 |

Every block's identity reconciled to the frozen canonical evaluation (block ID, side, zone, confirmed-at) before decomposition; zero reconciliation failures. The consumption invariant held with **zero violations** (the frozen evaluator checks consumed IDs before its expiry short-circuit, so a returned-EXPIRED block cannot be consumed; enforced fail-closed per observation).

## Fate categories

| Category | Count |
|---|---|
| `EXPIRED_UNTOUCHED` | 57 |
| `EXPIRED_TOUCHED` | 76 |
| `EXPIRED_INVALIDATED` | 49 |
| `EXPIRED_FIRST_RETEST_AT_DECISION` | 0 |

Categories may overlap where preregistered (UNTOUCHED excludes TOUCHED/INVALIDATED by construction; here TOUCHED and INVALIDATED overlap on 49 blocks). Raw predicate counts remain authoritative. No category is eligible and no category is a candidate.

## Age distribution

Post-confirmation bar age of the 133 EXPIRED blocks: **min 31, max 135, median 68**; p25 = 41, p50 = 68, p75 = 90. The exact integer-frequency histogram (78 distinct ages, e.g. 31×3, 32×3, 35×7, 36×6, 86×4, 90×1 … 135×1) is recorded verbatim in the sealed result JSON and sums to exactly 133. Age describes the population only: **no result at any alternative expiry was calculated** (no 31/40/45/60/90, no no-expiry, no session/day/ATR/dynamic expiry), and no "would pass at expiry = X" statement exists anywhere in the output.

## Final FVG context

Persisted final canonical FVG surface only (no redetection), frozen D001 mirror geometry, persisted ATR:

* final FVG present: **55** of 133 EXPIRED blocks; absent: 78;
* semantic direction agreement (FVG vs block side): **55 agree / 0 disagree / 78 not_available** — zero disagreements anywhere;
* canonical geometric overlap (among the 55 with FVG): **22 true / 33 false**;
* per-cell detail in the contingency below. Notably, 22 of the 57 untouched blocks retain a same-direction final FVG that also canonically overlaps the block zone (the `fvg_agreement=agree/overlap=true` cell).

## Fate × FVG contingency

Observed cells (each `untouched/touched/invalidated/first_retest_final` × `fvg_present` × `fvg_agreement` × `overlap`), summing exactly to 133:

* `untouched=True/…/fvg_present=True/agree/overlap=true` — **22**
* `untouched=True/…/fvg_present=True/agree/overlap=false` — **20**
* `untouched=True/…/fvg_present=False/not_available` — **15**
* `untouched=False/touched=True/invalidated=False/fvg_present=False/not_available` — 24
* `untouched=False/touched=True/invalidated=False/fvg_present=True/agree/overlap=false` — 3
* `untouched=False/touched=True/invalidated=True/fvg_present=False/not_available` — 39
* `untouched=False/touched=True/invalidated=True/fvg_present=True/agree/overlap=false` — 10

## Reference populations

Same descriptive predicates under each canonical state; never merged:

* **ELIGIBLE (87):** all 87 untouched (0 overlaps, 0 invalidating closes); age min 0, max 30, median 6, p75 = 11. Canonical eligibility is therefore young-and-untouched by construction — the frozen evaluator's own lifecycle semantics.
* **RETEST_ELIGIBLE (0):** empty.
* **MITIGATED (28):** all 28 zone-overlapped; 7 also show an invalidating close after the mitigating touch; age min 3, max 30, median 18.5.
* **INVALIDATED (3):** all 3 invalidated by close; age 18/21/24, median 21.

Context only; no alternate classification rule is created from these surfaces.

## H006 disposition

**`SUPPORTED_BY_D004`** — by the preregistered rule, with no numeric cutoff invented:

* A **meaningful concentration** — 57 of 133 (42.9%), the modal single fate — of frozen EXPIRED blocks remain **structurally untouched AND uninvalidated through the causal decision timestamp**. For these blocks, fixed age is the *only* lifecycle evidence acting against them at the decision; every other lifecycle condition the evaluator tests is satisfied.
* **FVG coexistence strengthens the interpretation exactly as H006 preregistered:** 42 of the 57 untouched blocks (73.7%) retain a same-direction final FVG, 22 of them with canonical geometric overlap true; direction disagreement is zero across the entire population (55 agree / 0 disagree / 78 not_available). H006's core claim — "a material subset … may remain unmitigated and uninvalidated through the causal decision timestamp and may continue to coexist directionally with final canonical FVG evidence" — is observed literally.
* **The NOT_SUPPORTED arm does not hold as registered:** while a slim aggregate majority of EXPIRED blocks show zone interaction (76 = 57.1%: 49 invalidation-like, 27 mitigation-like touches), that aggregate is heterogeneous (36.8% invalidation-like + 20.3% mitigation-like) and does not establish that EXPIRED blocks are "predominantly" stale in a single captured sense; the modal single fate is untouched+uninvalidated, not stale.
* **Honest counterweights (recorded, tempering any stronger claim):** 76 of 133 blocks did interact with price causally before the decision; 78 of 133 lack final FVG context; `EXPIRED_FIRST_RETEST_AT_DECISION` = 0 (no block's first touch arrived exactly on the decision candle).
* **Economic reading (no strategy change follows automatically):** the frozen 30-bar cutoff frequently preempts structural lifecycle evidence — 42.9% of age-expired blocks had seen no price interaction whatsoever at the decision — and the EXPIRED label collapses at least three distinct fates (untouched ≈ 43%, invalidation-like ≈ 37%, mitigation-like ≈ 20%). Any consequent strategy question belongs to a separately authorized, separately preregistered V002 decision.

## Existing hypothesis boundaries

* **H001 `INCONCLUSIVE_D001`** — unchanged; FVG geometry here is context only, not an H001 test.
* **H002 `SUPPORTED_BY_D003`** — unchanged; not reopened or reinterpreted.
* **H003 `NOT_TESTED_BY_D003`** — unchanged; no temporal lag or OB→FVG association was computed (banned output).
* **H005 `SUPPORTED_BY_V001`** — unchanged; not reopened.
* Only H006 received a D004 disposition.

## What D004 establishes

1. The frozen `EXPIRED` state on Fold 01 is structurally heterogeneous: at the causal decision, 57/133 blocks (42.9%, modal fate) had zero zone overlap and zero invalidating closes; 49 (36.8%) had causally invalidation-like closes; 27 (20.3%) had mitigation-like touches without invalidation; 0 had their first retest on the decision candle.
2. For the untouched subset, age is demonstrably the only adverse lifecycle evidence at the decision — the fixed 30-bar cutoff preempts all other lifecycle evaluation for 42.9% of the EXPIRED population.
3. Same-direction final-FVG coexistence is common among untouched expired blocks (42/57, with 22 canonically overlapping), consistent with H006's registered mechanism.
4. The EXPIRED population's age is broadly distributed (31–135 bars, median 68), not concentrated just beyond the boundary.
5. The frozen pipeline reproduces exactly (accounting, funnel, populations) on an unchanged code path — the observer is read-only.

## What D004 does NOT establish

* That removing, lengthening or parameterizing expiry would create any candidates — no candidate counterfactual, alternate candidate_ready, alternate Gate-11 pass count or alternate eligibility surface was computed.
* That any expiry value other than 30 is preferable — **no alternate expiry was tested** (no 31/40/45/60/90, no no-expiry, no session/day/ATR/dynamic expiry), and no "would pass at expiry = X" statement exists.
* Anything about profitability — **no profitability metric exists** in this evidence (no P&L, fills, trades, win rate, expectancy, drawdown, Sharpe, returns).
* Any change to H001/H002/H003/H005, and no V002 authorization — **no V002 was created**.
* Anything outside Fold 01 — **Tier B (Folds 02–04), 2025+ data and holdout remain sealed** and untouched.

## V002 status

`V002 = NOT CREATED`. **V002 DECISION REQUIRES SUPERVISORY INTERPRETATION OF D004 R001.** No implementation hypothesis may be registered automatically from this record.

## Reserved evidence

Untouched and sealed: Fold 02, Fold 03, Fold 04, 2025+ data, holdout. The historical store `fold-01-1d710826193a6767` was never opened. Folds 02–04 remain reserved sequential confirmation evidence.

---

### External result (sealed)

* Path: `phase8_data::/v2_diagnostics/phase8-v2-D004/fold01/phase8-v2-D004_result.json`
* SHA-256: `6563a93d426045df5ab48d0554d96deff1b9b82132071192be815e46cd723c9d`
* Bytes: 6,984 · read back verified · never mutated after sealing
* Void-attempt artifact: `phase8-v2-D004_ATTEMPT1_BLOCKAGE.json` (SHA-256 `ad789aea9ca06ef8d6beb80dadbf3ca6c5246bee07daa85a3e4405ece4a8dcdd`) — preserved intact.
