# PHASE 8 V2 — DIAGNOSTIC D005 SPECIFICATION (PREREGISTERED)

Status: PREREGISTERED — NOT EXECUTED. This document is written BEFORE any D005 empirical
access. Fold 01 is NOT opened during preregistration or tooling. The store is named for
boundary definition only.

Canonical baseline of this preregistration: result commit `6bb5c1ba63e21e66f66b5724011614253deda169`
(tree `1e4fa4a2df8e661ab44010a74ad4e8ee5d6921d1`, parent `cae8637adfbfae7338179d2e4d0888d81266e916`).

## 1. Scientific question

Among decisions whose frozen V002 structural-pair evaluator reports a structurally-active
canonical order block WITHOUT an associated same-direction final canonical FVG, what causal
temporal relationships exist between that block and canonical FVG structure in the causally
available frame, and why is the final FVG surface empty for those decisions?

This is the preregistered H003 question: OB and FVG evidence may be causally related across a
short temporal sequence rather than being required to appear as a strictly simultaneous state
at one decision timestamp. D005 measures the temporal structure explicitly; it is the
"later diagnostic" that H003's implementation boundary reserved. D005 is READ-ONLY: it
implements no strategy, creates no variant, and consumes no variant budget.

## 2. Empirical universe (future execution only — DO NOT execute in the preregistration or tooling task)

Authorized future data: Tier-A Fold 01 only, store `fold-01-a8b406884ab3525a`, identity
SHA-256 `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4`, rows content
SHA-256 `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22`, 13,269 decision
snapshots, coverage `fold-01/full`, re-hashed before any observation. The prohibited
historical store `fold-01-1d710826193a6767` is never opened. Folds 02–04, 2025+ and holdout
remain sealed. Tier B is NOT AUTHORIZED (candidate_ready 61 < 90).

## 3. Primary population (structural definition — no observed count may be encoded)

Future D005 population: V002 Gate-11 entrants (decisions in which
`"gate_11_confluence_score"` is present in the frozen D001 adapter row's gate results) for
which the frozen V002 structural-pair evaluator reports:

* `structurally_active == True`, AND
* `fvg_associated == False` under final-FVG semantics.

The population is derived naturally during execution. No expected count — including the
motivating V002 R001 values — may be encoded into tooling or tests.

## 4. Reference populations (structural context only)

For reconciliation and context only:

* R1: V002 structurally active + final same-direction FVG associated;
* R2: V002 structurally active + no final same-direction FVG associated (this is the
  primary population, reported separately for partition proof);
* R3: V002 non-active.

R1 + R2 + R3 must partition the V002 Gate-11 entrant universe exactly under frozen V002
semantics. OB state is never reinterpreted: the frozen V002 evaluator is the sole source of
`structurally_active` and `fvg_associated`.

## 5. Frozen configuration

Reuse the repaired canonical V001/V002 FVG implementation exactly:

* ATR period — unchanged;
* displacement multiplier — unchanged;
* gap definition — unchanged;
* direction definition — unchanged;
* fill semantics — unchanged.

No alternate detector, no numeric trial, no alternate ATR/displacement threshold. The
canonical detectors are imported, never reimplemented.

## 6. Causal FVG history rules

For every primary-population decision, D005 inspects ONLY the causally available M5 frame
through `decision_at`. A candle whose `available_at > decision_at` is never inspected. FVGs
are detected by the frozen canonical detector over that causal frame. No future FVG, no
retrospective reconstruction, no temporal aggregation across decisions.

## 7. Final-FVG reconciliation (fail closed)

Before any historical FVG observation is used, D005 recomputes the frozen final
same-direction unfilled FVG surface from the causal frame and requires EXACT reconciliation
with the persisted V002 input surface. If the persisted final FVG list and the canonical
recomputation disagree on any decision: FAIL CLOSED. No temporal aggregation is permitted to
mask a mismatch.

## 8. Temporal FVG universe (categories never collapsed)

For each primary-population decision, report all causally detected canonical FVGs relevant
to H003, distinguishing at minimum:

* FVG formed BEFORE canonical OB confirmation;
* FVG formed AT/AFTER canonical OB confirmation;
* same-direction;
* opposite-direction;
* still unfilled at decision;
* filled before decision.

## 9. Temporal association definition (exact H003 preregistered relationship)

H003's preregistered relationship is ORDERING-BASED: "OB and FVG evidence may be causally
related across a short temporal sequence rather than being required to appear as a strictly
simultaneous state at one decision timestamp." No numeric proximity, lag tolerance, or
temporal window is preregistered anywhere in H003, so D005 invents none.`h003_temporal_association_decisions` therefore counts primary-population decisions for which AT LEAST ONE same-direction canonical FVG exists in the causal frame that was formed AT OR AFTER canonical OB confirmation — the exact causal "temporal sequence" reading of H003 (the displacement imbalance follows its origin). FVGs formed before OB confirmation are reported descriptively (`SAME_DIRECTION_FVG_PRE_OB_ONLY`) but do NOT satisfy the H003 temporal-sequence relationship, because a strict temporal sequence requires the imbalance evidence to be causally produced by/after the structural origin.

The FVG fill state (§8) is a DESCRIPTIVE universe field only and is NOT part of the H003 ordering relationship: H003 preregisters ordering and nothing else. Importing the final-surface unfilled requirement into this rule would vacate the diagnostic, because the store's persisted final surface is `get_unfilled_fvgs(entry, "M5", direction=htf_bias)` over the whole causal frame (`bot/state/gate_inputs.py`), so a primary-population decision (empty final surface) by definition has no same-direction unfilled FVG anywhere in the frame; what CAN exist temporally after the OB in that population is a same-direction FVG that was formed and subsequently filled — exactly the temporal evidence H003 asks about.

No after-observation modification of this rule is permitted.

## 10. Temporal distance surface (descriptive only)

For qualifying same-direction temporal relationships report, descriptively:

* OB confirmation timestamp;
* FVG formation timestamp;
* signed bar distance;
* absolute bar distance;
* elapsed minutes;
* whether the FVG forms before or after OB confirmation;
* whether the FVG remains unfilled at decision;
* whether it was filled before decision.

Permitted summaries: count, min, max, median, exact integer histogram, p25 / p50 / p75.
No optimal lag. No lag cutoff search. No threshold derivation from any distribution.

## 11. Final-surface attrition categories (defined before execution)

For active-OB decisions lacking a final FVG, classify the exact causal reason:

* `NO_SAME_DIRECTION_FVG_EVER` — no same-direction canonical FVG exists in the causal frame;
* `SAME_DIRECTION_FVG_EXISTED_BUT_FILLED` — at least one same-direction FVG was formed
  AT/AFTER canonical OB confirmation (for primary-population decisions such an FVG is
  necessarily filled before the decision, because an unfilled one would be a member of
  the persisted final surface and contradict primary membership);
* `SAME_DIRECTION_FVG_PRE_OB_ONLY` — same-direction FVGs exist but ALL were formed
  BEFORE canonical OB confirmation (for primary-population decisions they are necessarily
  filled; no post-confirmation temporal sequence exists);
* `OPPOSITE_DIRECTION_ONLY` — only opposite-direction canonical FVGs exist in the causal frame.

The four categories are exhaustive and mutually exclusive under the frozen detector; any
decision that fits none is a FAIL-CLOSED accounting error, not an `other` bucket.

## 12. H003 temporal-association count

The count of primary-population decisions satisfying §9 is named ONLY
`h003_temporal_association_decisions`. It is a structural count. It must NEVER be named or
treated as `candidate_ready`, `rescued_candidates`, `candidate_if_temporal` or equivalent.

## 13. Necessary variant-headroom classification (pure arithmetic, NOT science)

Supervisory arithmetic recorded at preregistration (NOT empirical counterfactuals):

* canonical-strategy rejects at V002 R001: 22 → best case 61 + 22 = 83 < 90;
* Gate-12/13 rejects at V002 R001: 19 → best case 61 + 19 = 80 < 90.

Therefore a V003 that modifies ONLY canonical-strategy protections, or ONLY Gate-12/13
entry semantics, is mathematically unable to reach the 90-candidate Tier-A target. Neither
variant is created.

Temporal-only headroom rule: a temporal-association-only V003 can affect at most decisions
whose V002 structural-active OB lacks the required final same-direction FVG but possesses
valid causal temporal FVG structure under H003 — i.e. at most
`h003_temporal_association_decisions`. Required headroom is 90 − 61 = 29. Classification:

* `TEMPORAL_VARIANT_HEADROOM_POSSIBLE` if `h003_temporal_association_decisions >= 29`;
* `TEMPORAL_VARIANT_HEADROOM_INSUFFICIENT` if `h003_temporal_association_decisions < 29`.

This is a NECESSARY condition only. `>= 29` does NOT prove a variant would reach 90 (the
affected decisions must still survive V002 score, canonical strategy and Gate 12/13 under
whatever preregistered semantics a future variant defines). No automatic V003 follows from
either classification. The 29 figure is an arithmetic feasibility bound only — NOT an H003
support threshold, NOT a parameter, NOT a tuning objective, NOT a candidate prediction.

## 14. H003 disposition rule (copied verbatim from the preregistered record)

H003's existing preregistered criteria govern, exactly as registered before any D005
evidence existed:

* expected qualitative effect (verbatim): "If H003 is relevant, OB and FVG detections
  should exhibit short, structured temporal offsets rather than being restricted to
  same-bar co-occurrence; measurable only by a later dedicated diagnostic.";
* potential failure mode (verbatim): "If causal OB/FVG pairs are temporally diffuse or
  absent, temporal association is not economically meaningful for this strategy.";
* expected frequency effect (verbatim): "Qualitative only: a temporal-association rule
  would be expected to broaden admissible evidence relative to strict simultaneity; no
  number is predicted."

Application at execution: H003 is qualitatively SUPPORTED if the primary population is not
near-zero AND qualifying temporal associations exhibit structured (non-degenerate, non-
diffuse) offsets consistent with the expected qualitative effect; H003's failure mode holds
if causal OB/FVG pairs are temporally diffuse or absent. The 29-observation headroom rule
(§13) is NEVER the scientific support rule. Disposition values are drawn from the
register's existing vocabulary (`SUPPORTED_BY_D005` / `NOT_SUPPORTED_BY_D005`), applied
qualitatively. If at execution time the record were found to lack a usable
pre-observation interpretation rule, execution would STOP and return for supervisory
review; this document records that the rule above exists and is copied verbatim.

## 15. Boundaries — hypotheses D005 does NOT touch

* H001 — `SUPPORTED_BY_D003_D004_SYNTHESIS`: not reopened; final-FVG geometry appears only
  as frozen V002 input context.
* H002 — `SUPPORTED_BY_D003`: not reopened, not re-tested.
* H006 — `SUPPORTED_BY_D004`: not reopened, not re-tested.
* H007 — represented by V002 R001 (`OPPORTUNITY_INSUFFICIENT_TIER_A_FOLD01_OBSERVED`):
  not reopened; V002 semantics are consumed frozen.
* H005 — `SUPPORTED_BY_V001`: not reopened.

## 16. Prohibited counterfactuals and banned outputs

D005 does NOT calculate: candidate_ready if temporal association were accepted; Gate-11
pass if historical FVG were retained; candidate count if filled FVGs were reused; candidate
count without the final-FVG requirement; any alternate score threshold; any alternate age
cutoff. D005 reports structural temporal evidence only.

No downstream relaxation is tested: DXY, regime, bias, news, session, allowlist, Gate-12/13
liquidity alignment, entry readiness and the score threshold remain frozen descriptive V002
context.

Banned output concepts (fail closed): `candidate_if_temporal`, `rescued_candidate`,
`alternate_lag`, `optimal_lag`, `temporal_threshold`, `candidate_without_final_fvg`, `pnl`,
`profit`, `win_rate`, `expectancy`, `drawdown`, `sharpe`, `closed_trades`. No temporal
parameter search of any kind (1/2/3/5/10 bars, session windows, minute thresholds, ATR-based
temporal windows): no numeric trial, no optimizer.

## 17. Immutability of V002 artifacts

Read-only diagnostic. `bot/strategy/variant_v002.py`,
`backtests/phase8_v2_variant_v002_eval.py`, TC001 and TC002 are NOT modified. The V002
strategy module remains byte-identical (Git blob `8272c28552c05067b6dc3ba039ee8df2dbbfb8b4`).

## 18. Tooling reuse and two-phase discipline

Phase B tooling (`backtests/phase8_v2_diagnostic_d005.py`) reuses where possible: D001
snapshot classification, the V001 canonical FVG reconstruction/mirror, the V002
structural-pair evaluator, the V002 Gate-11 entrant definition, canonical Git-blob
provenance (`canonical_git_blob_v1`), Fold-01 boundary guards, and deterministic state
seed/carry. Detectors are never reimplemented. Phase A (this preregistration) precedes
tooling; Phase B synthetic-tested tooling is committed and pushed before any Fold-01
access; empirical execution only under separate supervisory authorization after the remote
resolves to the frozen tooling commit.

## 19. Budget

Registration and tooling freeze consume zero diagnostic budget: diagnostics remain `3 / 12`
at the tooling-freeze hard stop. Strategy variants remain `2 / 8`; numeric parameter trials
remain `0 / 4`; budget lock ACTIVE; V003 NOT CREATED. At the instant a future separately
authorized D005 execution first reads Fold 01, diagnostics become permanently `4 / 12`. No
strategy-variant budget is consumed by D005 under any outcome.

## 20. Required synthetic test coverage (Phase B, synthetic data only)

At minimum: (1) active OB + no FVG ever; (2) active OB + same-direction FVG after OB;
(3) active OB + same-direction FVG before OB only; (4) active OB + same-direction FVG
formed then filled before decision; (5) active OB + final unfilled same-direction FVG
reference case; (6) opposite-direction FVG only; (7) LONG block; (8) SHORT block;
(9) post-decision FVG excluded causally; (10) persisted final-FVG reconciliation;
(11) exact temporal-distance arithmetic; (12) malformed timestamp fail closed;
(13) block-identity mismatch fail closed; (14) historical final-FVG list mismatch fail
closed; (15) no counterfactual-candidate keys. Reconciliations: V002 entrant population,
V002 structural state, structurally-active population, final-FVG association status,
primary/reference partition, per-FVG causality, final-surface recomputation equality,
temporal-category accounting, H003 count subset-of-primary, reserved-evidence guards. No
empirical count is encoded anywhere.

## 21. TC001 — Causal Formation Clock Clarification

Registered as `phase8-v2-D005-TC001` in the hypothesis register
(`PRE_EMPIRICAL_MEASUREMENT_TOOLING_CORRECTION`, defect class
`D005_PRE_EMPIRICAL_TEMPORAL_CLOCK_MISMATCH`; defective tooling commit
`81c6a6f53a0e456a800f2fdddc957e34c1dc9064`).  This section is an append-only,
pre-empirical measurement-coordinate CLARIFICATION.  It does not rewrite sections 1-20,
the original D005 scientific registration, or H003.

What is clarified: sections 8-10's "FVG formation timestamp" and "formed" mean the
COMPLETION (third) candle's causal `available_at` — the instant the three-candle
pattern (c1, c2, c3) becomes observable.  The canonical detector attributes
`source_index = i - 1` (the middle displacement candle); the completion row remains
`source_index + 1` (section 8) and detector attribution is unchanged.  The OB clock is
the canonical `block.confirmed_at`, which is likewise the confirmation candle's
`available_at` (`bot.strategy.order_blocks.detect_order_blocks`).  Ordering and signed
bar distance therefore compare causal availability to causal availability:
`FVG formation available_at - OB confirmed_at`, negative = `BEFORE_OB_CONFIRMATION`,
zero = `AT_OB_CONFIRMATION`, positive = `AFTER_OB_CONFIRMATION`; the M5 bar-grid
invariant (`seconds_difference % 300 == 0` within tolerance) is unchanged and no
manual `-1`/`+1` compensation exists — the timestamps themselves are correct.

Why: the previously frozen tooling (81c6a6f) timestamped FVG formation with the
completion candle's `open_time`, which is a DIFFERENT causal clock from the OB's
`confirmed_at`; on the canonical contiguous M5 grid (`available_at(i) ==
open_time(i+1)`) this mislabels every FVG exactly one bar early (a true 0-bar
same-candle completion reported as -1; a true +1 reported as 0), shifting both the
ordering categories and the distance surface by one bar.

Output naming (section 17 restated): the formation field is
`fvg_formation_available_at`; the completion candle's `open_time` may be retained as
`fvg_completion_open_time` DESCRIPTIVE metadata only — it must never drive
BEFORE/AT/AFTER, signed bar distance, elapsed minutes or H003 decision membership.

Scope and integrity: this is a measurement-coordinate clarification only — the
ordering-only H003 relationship, the primary population, the 29-observation headroom
arithmetic, the final-surface reconciliation (`get_unfilled_fvgs(causal_frame, "M5",
direction=htf_bias)` unchanged) and the attrition categories are all unchanged.  The
correction occurred BEFORE any D005 empirical access: no Fold-01 store was opened and
no empirical data was observed when choosing the clock; all regression fixtures are
synthetic.  Because the former tooling mis-timestamped the temporal relationship, some
synthetic fixtures may legitimately move between
`SAME_DIRECTION_FVG_EXISTED_BUT_FILLED` and `SAME_DIRECTION_FVG_PRE_OB_ONLY`; the
category DEFINITIONS are unchanged and no old synthetic classification is forced.

Historical document hashes preserved (both verified from the committed Git blobs at
df19e89a8afd72deda2b58c79f38a798daaead76 and
c615c3e9ae15f6c47b1b9da27b835d46a431b05c): initial Phase-A preregistration
`bab242de848a79714828d958196b830d8ae975445f7183c8c6ac03874a747401`; ordering-only
correction `d7f39d31716b34308ad07afff4260312857653605a0df4d6b58d0f87f1e96941`.  The
full-document SHA after this append is recorded in the register TC001 record and the
corrected tooling's `SPEC_SHA256`.

---

## 22. TC002 — V002 Marginal/Intersection Partition and CLI Boundary Clarification

Status: POST_EXPOSURE_MEASUREMENT_TOOLING_CORRECTION (phase8-v2-D005-TC002).

This section appends to — and never rewrites — sections 1–21.  The scientific
surfaces of D005 are unchanged: the H003 statement and ordering-only rule, the
primary-population definition, the temporal FVG detector, the TC001 causal
availability clock, the attrition categories, the temporal-distance metrics,
the 29-observation headroom arithmetic and the H003 qualitative interpretation
rule all stand exactly as preregistered.  TC002 corrects two measurement
tooling defects exposed by D005 Attempt 1 and creates no new scientific
hypothesis.

### 22.1 Attempt-1 blockage identity (bound incident history)

D005 Attempt 1 completed the full 13,269-snapshot Fold-01 observation loop
over the preserved authorized store `fold-01-a8b406884ab3525a` (identity
`a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4`, rows
`96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22`), then
failed closed during aggregation with the exact frozen error
`ReconciliationError: primary population 42 != structurally-active without
final FVG R2=34`.  Exposure timestamp (first authorized store processing):
`2026-09-26T13:18:42.145570+00:00`; diagnostics are therefore permanently
4 / 12, strategy variants 2 / 8, numeric trials 0 / 4.  The external blockage
artifact `phase8-v2-D005_ATTEMPT1_BLOCKAGE.json`
(SHA-256 `168ea3b27eb5cf536cca338bd87de028e2da2abd055ed112e85c508e1886f6e2`,
3692 bytes) is preserved unmodified.  No successful D005 R001 exists; no H003
interpretation was made; V003 was not created.  A separate PRE-ACCESS
WRAPPER_REFUSAL at 2026-09-26T13:14:25Z (CLI path scan) consumed ZERO
empirical exposure and no budget.  The values 42, 34 and 8 are recorded here
ONLY as observed incident history; they are never test oracles and the
corrected logic is justified from set semantics alone.

### 22.2 Primary defect — D005_V002_MARGINAL_INTERSECTION_PARTITION_MISMATCH

The Attempt-1 tooling computed the reference partition from the frozen V002
aggregate MARGINALS as `R1 = associated`, `R2 = active − associated`.  This
subtraction is invalid: `v002_structurally_active_count` and
`v002_associated_same_direction_fvg_count` are independent marginals of two
different boolean attributes, and V002 can legitimately report
`fvg_associated == True` while `structurally_active == False` — for example a
canonical block in state `MITIGATED` (or `INVALIDATED`/`CONSUMED`) still
carries the same-direction persisted final FVG association attached by the
frozen evaluator.  Therefore `associated ⊄ active`, the subtraction
under-counts R2 and is prohibited.

### 22.3 Corrected four-cell contingency (the only partition rule)

The V002 population partition is constructed directly from individual frozen
per-decision V002 observations.  For every Gate-11 entrant exactly one cell:

* A `ACTIVE_ASSOCIATED` — `structurally_active == True` AND
  `fvg_associated == True`;
* B `ACTIVE_NOT_ASSOCIATED` — `structurally_active == True` AND
  `fvg_associated == False` — this is the D005 PRIMARY population;
* C `NONACTIVE_ASSOCIATED` — `structurally_active == False` AND
  `fvg_associated == True`;
* D `NONACTIVE_NOT_ASSOCIATED` — `structurally_active == False` AND
  `fvg_associated == False`.

Required: `A + B + C + D == Gate11 entrants` exactly.

### 22.4 Corrected reference populations

* R1 = `ACTIVE_ASSOCIATED`;
* R2 = `ACTIVE_NOT_ASSOCIATED` (primary D005 population);
* R3 = all non-active = `NONACTIVE_ASSOCIATED + NONACTIVE_NOT_ASSOCIATED`.

Required: `R1 + R2 + R3 == entrants` and `primary_count == R2` exactly.  R1
is NOT defined as the V002 associated marginal.

### 22.5 Marginals as reconciliation totals only

The frozen V002 aggregate marginals continue to be consumed, as
reconciliation totals only:

* `v002_structurally_active_count == A + B`;
* `v002_associated_same_direction_fvg_count == A + C`;
* `gate11_entrants_observed == A + B + C + D`.

These equalities explicitly prove why the two marginals cannot be directly
subtracted: their overlap is cell A, which is counted in both.

### 22.6 Primary decision-ID set reconciliation (no count-only check)

D005 aggregation now receives the actual per-decision frozen V002
observations.  Let `primary_ids` be the decision IDs of V002 observations
with `structurally_active == True` AND `fvg_associated == False`, and
`d005_ids` the decision IDs actually observed by D005.  Required:

* `primary_ids == d005_ids` as exact SETS (never count-only);
* no duplicate decision IDs anywhere;
* every D005 observation maps to exactly one V002 observation;
* every primary V002 observation receives exactly one D005 observation.

Any violation fails closed.

### 22.7 Secondary defect — D005_AUTHORIZED_STORE_HASH_PATH_YEAR_FALSE_POSITIVE

The inherited generic CLI path guard scanned arbitrary four-digit substrings
as calendar years, so numeric fragments embedded in the authorized store
directory name `fold-01-a8b406884ab3525a` (`4068`, `3525`) were misread as
`>= 2025` and refused BEFORE any store access.  This refusal consumed no
budget.  The D005 CLI now performs a D005-specific structured pre-open
boundary check instead of arbitrary substring-year scanning.  Reserved-
evidence protection is NOT weakened: the guard still refuses holdout /
final-validation tokens, standalone year directory components (`2025`,
`2026`, ...), structured `year=YYYY` markers with YYYY >= 2025, ISO-style
components beginning `2025-` / `2026-`, any different Fold store basename,
the prohibited historical store `fold-01-1d710826193a6767`, and Fold-02+
basenames.  Arbitrary four-digit substrings embedded inside SHA hashes,
fingerprints, store IDs and alphanumeric package IDs are never interpreted
as calendar years.  The post-open structured store-identity checks (Fold 01
ID, full coverage, M5, exact evaluation window, prohibited-historical-store
refusal, identity SHA) remain authoritative; pathname checks alone are never
sufficient.

### 22.8 Budget and scope integrity

TC002 consumes ZERO diagnostic budget: diagnostics remain 4 / 12, variants
2 / 8, numeric 0 / 4.  A later corrected D005 empirical rerun remains 4 / 12
because D005 has already consumed its diagnostic slot; it must NOT become
5 / 12.  No empirical access occurs during TC002: no Fold store of any kind
is opened, all regression fixtures are synthetic, and the V002 strategy
module (blob 8272c28552c05067b6dc3ba039ee8df2dbbfb8b4) and the frozen V002
measurement tooling are byte-identical before and after.

### 22.9 Historical specification hashes

All preserved and verified from the committed Git blobs: initial Phase-A
preregistration `bab242de848a79714828d958196b830d8ae975445f7183c8c6ac03874a747401`
(df19e89a8afd72deda2b58c79f38a798daaead76); ordering-only correction
`d7f39d31716b34308ad07afff4260312857653605a0df4d6b58d0f87f1e96941`
(c615c3e9ae15f6c47b1b9da27b835d46a431b05c); TC001 causal-clock correction
`2b820d608b1d881720369b045366e1986c9cf07f25ce44a2bba26ce837029ed8`
(7c9608d5b9871414a830e38395d1a67f7efacad2).  The new full-document SHA-256
after this append is recorded in the register TC002 record and the corrected
tooling's `SPEC_SHA256`.
