# Phase 8 V2 Diagnostic D003 — Final Corrected Result (R001)

**Diagnostic:** `phase8-v2-D003` — Canonical Gate-11 and Order-Block Lifecycle Decomposition
**Classification:** `DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE`
**Research identity:** `phase6-development-v2`
**Charter:** `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
**Primary hypothesis:** `phase8-v2-H002` → **`SUPPORTED_BY_D003`**
**Preregistration:** commit `8b3a8bd1169fcd5f8fb0a15a089451c68d3e04b6` (spec SHA-256 `2b5204925a700cc2faa817835e77d298d778138f811bdfb2ad06cfe9c007cc46`)

## Identity

- Diagnostic: `phase8-v2-D003`, `DIAGNOSTIC_INVESTIGATION`, preregistered before any Fold-01 read.
- Primary linked hypothesis: `phase8-v2-H002` (statement unchanged since registration; never rewritten after any observation).
- Contextual-only: `phase8-v2-H001` (remains `INCONCLUSIVE_D001`). Not tested: `phase8-v2-H003`. Not reopened: `phase8-v2-H005` (`SUPPORTED_BY_V001`).
- Empirical universe: `TIER_A_FOLD01` only, preserved store `fold-01-a8b406884ab3525a`.
- This document records the FIRST valid D003 result. Both earlier outputs are VOID (below).

## Full tooling lineage

| Stage | Commit |
| --- | --- |
| Preregistration | `8b3a8bd1169fcd5f8fb0a15a089451c68d3e04b6` |
| Original tooling freeze | `882b4c9468f032fb4ac30f0737afd0831e12206d` |
| TC001 — causal prior-state repair | `aa6bbc1cd3e4d84821cba6cf5e821b917444c198` |
| TC002 — canonical_git_blob_v1 fingerprint | `58bedf6c59c213cbaf3557c7dc03bac4e7896aed` |
| TC003 — D001 row-contract extraction repair | `b26ac6a88eb6276d8a0e0f5db3eb413d3732fe84` |
| TC004 — Surface-E direction semantics | `3e4514bbc257911d17a5f1f93acd2f86a275e2e9` (the ONLY tooling that produced R001) |

Governance records: `phase8-v2-D003-TC001`, `-TC002`, `-TC003`, `-TC004` (append-only; none rewritten).

## Original void attempt

- Exposure: `2026-09-24T21:52:07.081601+00:00` (budget permanently consumed: `2 / 12`).
- Output `phase8-v2-D003_result.json` SHA-256 `6637338401bd5133a53c4dbed455cff757b6459b85549088e17fe228a00488df` — **`VOID_ATTEMPT_OUTPUT — NOT R001`**: the observer read a nonexistent `row["gate_context"]`, degenerating interpretive surfaces B–H while accounting/funnel stayed faithful (internal contradiction: Gate-11 passed 1 with zero recorded component passes).
- Blockage artifact SHA-256 `764de0ea6fba632845b00da8f8c03950e8d0cbc69e5d6864821bafe0765b9a46`. Preserved, never overwritten.

## TC001 / TC002

- TC001: lifecycle observer receives the exact causal `prior_state_record` consumed by the reducer; consumed block IDs derive only from it; state advances only after observation. Unchanged through the final run.
- TC002: tooling fingerprint = SHA-256 of the committed Git blob of `backtests/phase8_v2_diagnostic_d003.py` at the active tooling commit under `canonical_git_blob_v1` — checkout-independent, fail-closed, no worktree fallback.

## TC003 repair and void rerun

- Repair: all surfaces extracted from the frozen flattened D001 row (`row["score"]`, `row["ob"]`, `row["fvg"]`, `row["overlap"]`, `row["direction"]`); fields flattened away by D001 (awarded points, raw FVG geometry, ATR) recovered read-only from the current decision's persisted render after full §9 reconciliation; Gate-11 self-consistency and fail-closed degeneracy invariants added.
- Corrected rerun `2026-09-25T00:07:38.631820+00:00` produced internally consistent accounting/funnel/B/C/D/F/G/H, but Surface E `direction_agreement` was mechanically wrong → **`VOID_CORRECTED_RERUN_OUTPUT — NOT R001`** (output SHA `5c8c2a8b84ce816f8c34e80a99e89cd03281fbc6c0b655562dc5b9136c215450`; blockage SHA `e28f976c356ae28b591fca594340faf5dea8491ba9ed2d80f36efb256dd0235a`). Preserved.

## TC004 direction repair

- `_semantic_direction`: case-insensitive `bullish`/`long` → `LONG`, `bearish`/`short` → `SHORT`; absent/empty/`FLAT` → `None` (`not_available`); unexpected tokens fail closed. Applied to Surface E only; Surface G untouched; four-cell eligibility contingency untouched; aggregation partition invariant enforced.

## Final corrected rerun

- Timestamps: started `2026-09-25T10:44:13.390741+00:00`, finished `2026-09-25T10:47:05.654904+00:00`.
- Tooling: TC004 commit only; `canonical_commit = tooling_commit = 3e4514bbc257911d17a5f1f93acd2f86a275e2e9`.
- `fingerprint_contract = canonical_git_blob_v1`; `tooling_fingerprint = c4a4d2f88fe01d991e48ca43cf2f281a73f3a790ac23d82b57c0735d4257797c` (independently verified against `git cat-file blob`).
- Store: identity `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4`, rows `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22` (row re-hashing verified), 13,269 snapshots, fold-01/full, plan fingerprint `adbab1bd…`. Prohibited store `fold-01-1d710826193a6767` never opened.

## Accounting

| Bucket | Count |
| --- | --- |
| scheduled | 13,269 |
| structural/reducer-classified | 7,316 |
| missing_history (`early_exit`) | 4,815 |
| unavailable_input (`dxy_blocked`) | 1,138 |
| evaluation_error | 0 |

`reconcile_accounting` passed: 13,269 = 7,316 + 4,815 + 1,138 + 0.

## Gate funnel

| Gate | Entered | Passed | Failed |
| --- | --- | --- | --- |
| Gate 8 (liquidity) | 7,316 | 3,607 | 3,709 |
| Gate 9 (displacement) | 3,607 | 1,489 | 2,118 |
| Gate 10 (internal structure) | 1,489 | 526 | 963 |
| Gate 11 (confluence 8/8) | 526 | 1 | 525 |
| Canonical strategy | 1 | 0 | 1 |

All counts derived naturally by the frozen tooling (no historical value forced).

## Frozen score components

For the 526 Gate-11 entrants (pass/fail):

- HTF bias aligns with trade direction: 526 / 0
- Price located in premium/discount zone: 526 / 0
- Valid order block present: 4 / 522
- FVG overlaps the order block zone: 1 / 525
- Liquidity sweep occurred before entry: 526 / 0

Awarded points: HTF 1,052 (2×526), PD 526 (1×526), valid OB 8 (2×4), FVG-in-OB 1 (1×1), sweep 1,052 (2×526). Score distribution: `{5: 522, 7: 3, 8: 1}`. Combination frequencies: `pd=True ob=False fvg=False: 522`, `pd=True ob=True fvg=False: 3`, `pd=True ob=True fvg=True: 1`. The single score-8 entrant is exactly the single Gate-11 pass — internally consistent with the funnel.

## Three-way frozen contingency

`pd=True ob=False fvg=False: 522` · `pd=True ob=True fvg=False: 3` · `pd=True ob=True fvg=True: 1` (sum 526). Descriptive only.

## Canonical OB lifecycle

States: `ELIGIBLE 87`, `EXPIRED 133`, `MITIGATED 28`, `INVALIDATED 3`, `UNAVAILABLE 275`. Sides: `LONG 149`, `SHORT 102`, `FLAT 275`. Eligible (`ELIGIBLE` + `RETEST_ELIGIBLE`) = 87; non-eligible = 439. State × direction: ELIGIBLE {LONG 50, SHORT 37}; EXPIRED {LONG 70, SHORT 63}; MITIGATED {LONG 26, SHORT 2}; INVALIDATED {LONG 3}; UNAVAILABLE {FLAT 275}.

## Canonical failure reasons

`no_confirmed_block 275` · `block_expired 133` · `block_already_mitigated 28` · `close_below_bullish_zone 3` · `confirmed_unmitigated_block 87` (the eligible reason). No post-hoc collapsing.

## Acquisition vs canonical agreement

Four-cell eligibility contingency: legacy false / canonical false 437; legacy false / canonical true **85**; legacy true / canonical false 2; legacy true / canonical true **2** (sum 526). The two legacy-valid canonical-eligible entrants are exactly the `pd=True ob=True fvg=True` combination.

## Corrected semantic direction agreement

**agree 251 · disagree 0 · not_available 275** (partition sums to 526). Semantic normalization (`bullish↔LONG`, `bearish↔SHORT`) repairs the voided rerun's artifact (`agree 0 / disagree 251`); cross-validated by Surface G's like-vocabulary agreement (`agree 60 / disagree 0`). The 251 agreements are exactly the decisions where a confirmed canonical block exists with the legacy-search direction.

## Canonical OB / FVG coexistence

canonical_eligible_and_final_fvg 60 · canonical_eligible_no_final_fvg 27 · canonical_not_eligible_with_final_fvg 116 · neither 323 (sum 526). Pairs with both: 60, direction agreement 60/0/0. Canonical overlap: true 39, false 21. Preregistered separation geometry only.

## Premium/discount context

`pd=True eligible_ob=False fvg=False 323` · `pd=True eligible_ob=False fvg=True 116` · `pd=True eligible_ob=True fvg=False 27` · `pd=True eligible_ob=True fvg=True 60` (sum 526). Descriptive only.

## H002 disposition

**`SUPPORTED_BY_D003`** — by the preregistered rule, applied to this result alone:

- Meaningful OB-like structure exists and enters later lifecycle states: 251/526 entrants (47.7%) carry a confirmed canonical block observable (`confirmed_unmitigated_block`), i.e. the canonical detector finds substantial OB structure in causal decision context.
- That structure concentrates in specific later lifecycle failure states/reasons: of the 251, 164 (65.3%) fail via `block_expired` (133, the dominant single failure reason) plus `block_already_mitigated` (28) and `close_below_bullish_zone` (3).
- Canonical eligibility is materially rarer because of the lifecycle conjunction: only 87/526 (16.5%) remain eligible; and only 2/526 remain legacy-valid while canonically eligible.
- The `NOT_SUPPORTED_BY_D003` arm requires `UNAVAILABLE/no_confirmed_block` domination **with little evidence of meaningful structure entering later lifecycle states** — the second condition demonstrably fails (251 later-state entries, 164 lifecycle-failure consumptions). `INCONCLUSIVE_D003` does not apply: counts are structurally interpretable, the surfaces reconcile exactly, and the legacy/canonical semantics are now measured on a common footing.

No numeric threshold was invented; no strategy change follows automatically from this disposition.

## H001 / H003 / H005 boundaries

- H001: `INCONCLUSIVE_D001` — unchanged; D003 recorded only contextual pair/overlap counts.
- H003: `NOT_TESTED_BY_D003` — no OB/FVG temporal association was computed.
- H005: `SUPPORTED_BY_V001` — unchanged, not reopened.

## What D003 establishes

A defensible, reconciled decomposition of the frozen Gate-11 conjunction on Fold 01: the score bottleneck is concentrated in the valid-OB requirement (522/526 lack a legacy-valid OB) and the FVG-in-OB requirement (525/526 fail overlap); the canonical lifecycle shows confirmed blocks are common at decision time (251) but rarely eligible (87), dominated by expiry (133). Legacy and canonical OB semantics agree directionally wherever both are meaningful (251 agree / 0 disagree) but agree on validity in only 2 of 526 cases — quantifying the acquisition/canonical semantic gap H002 anticipated. Where both a canonical-eligible OB and a final FVG exist (60), direction agreement is perfect and overlap is present in 39.

## What D003 does not establish

No candidate-count relief under any relaxed rule (all counterfactuals prohibited and none computed); no profitability or performance quantity of any kind; no evidence about Folds 02–04, holdout, or 2025+ data; no justification for a specific V002 parameter set; no claim that relaxing any single subcondition would produce adequate candidate density. No alternate threshold was tested; no strategy parameter was changed; no profitability metric was computed; no V002 has been created; Tier B remains sealed.

## Reserved evidence

Fold 02, Fold 03, Fold 04, holdout and 2025+ market data untouched (all `reserved_evidence` flags true in the sealed result).

---

**Prior-output status:** the attempt-1 output and the tc003-rerun1 output are both VOID and are NOT R001; only the sealed `tc004-rerun1` result below is the D003 result. All four historical artifacts remain preserved unchanged.

## Final external R001

- Path: `phase8_data::/v2_diagnostics/phase8-v2-D003/fold01/tc004-rerun1/phase8-v2-D003_result.json`
- SHA-256: `71f85982c3170c689678682184ccc2d3fe291bc74372a47e3dc8aed3a6d1b096`
- Bytes: 5,595 (read back and verified; never mutated after sealing)

## Budget

`2 / 12 diagnostics executed` · `1 / 8 strategy variants observed` · `0 / 4 numeric parameter trials` · upward-revision lock **ACTIVE**. The TC004 rerun completed the already-consumed D003 diagnostic; no additional diagnostic was consumed.
