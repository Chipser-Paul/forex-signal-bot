# PHASE 8 V2 — STRATEGY VARIANT V002 PREREGISTRATION + H001 EVIDENCE SYNTHESIS (GOVERNANCE ONLY)

**Variant:** `phase6-development-v2-V002`
**Title:** Canonical Structural OB/FVG Pair
**Status:** `REGISTERED_NOT_OBSERVED`
**Budget classification:** `STRATEGY_VARIANT` (registration and implementation consume nothing)
**Budget consumption upon first empirical observation:** strategy variants becomes
permanently `2 / 8 observed` at the instant first Fold-01 V002 strategy behavior is
empirically observed; numeric parameter trials remain `0 / 4` (V002 introduces no
numeric expiry value and consumes no numeric trial).
**Linked hypothesis:** `phase8-v2-H007` — Canonical OB/FVG Structural-Pair Semantics
(registered in this preregistration commit)
**Supporting evidence:** `phase8-v2-H002 = SUPPORTED_BY_D003`,
`phase8-v2-H006 = SUPPORTED_BY_D004`,
`phase8-v2-H001 = SUPPORTED_BY_D003_D004_SYNTHESIS` (evidence synthesis, this commit)
**Research identity:** `phase6-development-v2`
**Charter:** `phase8-v2-research-charter-v1-8527e3a5eec98f53`
(charter SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
**Canonical baseline:** `cd7526260ac224facb5dbf993f6e98be25cb650d`
(tree `3c873168c7094a43260b5b147110a2fabcfbc23e`, parent `b68d4e84e0ce475a311355f50748671feda53ba6` —
the D004 result commit; D004 R001 has passed supervisory review)
**Canonical fingerprint contract:** `canonical_git_blob_v1`
**Registration:** `baseline/phase8_v2_hypothesis_register.json` (this commit:
`phase8-v2-H001-R001` evidence-synthesis record, H001 disposition flip, H007, V002)

This document is a **governance-only preregistration**. It publishes the H001
evidence synthesis from sealed D003+D004 R001 evidence, fixes the V002 conceptual
boundary, its structural semantics, its success classification, and its exact
empirical metric surface **before** any implementation or execution. It creates no
strategy code in this commit. V002 empirical execution is NOT authorized by this
document; it requires a separate supervisory authorization after the frozen
implementation/tooling commit is verified on the remote. No Fold-01 store is
opened in this task. Folds 02–04, holdout and 2025+ data remain untouched.

---

## 1. H001 evidence synthesis — inputs and discipline

Record: `phase8-v2-H001-R001`, type `EVIDENCE_SYNTHESIS`, classification
`DEVELOPMENT_EVIDENCE_SYNTHESIS — D003+D004 R001 — NO NEW EMPIRICAL EXECUTION`.

Inputs ONLY:

* `phase8-v2-D003-R001` (sealed; register record)
* `phase8-v2-D004-R001` (sealed; output SHA-256
  `6563a93d426045df5ab48d0554d96deff1b9b82132071192be815e46cd723c9d`, 6,984 bytes)

No Fold-01 store read (store `fold-01-a8b406884ab3525a` NOT opened; the prohibited
historical store `fold-01-1d710826193a6767` NOT opened). No new replay. No new
empirical observation of any kind. Diagnostic budget consumed: **zero** — budget
remains `3 / 12`; no D005 is created. H001's preregistered statement, expected
qualitative effect and potential failure mode are the governing criteria; H001 was
registered before D003/D004 were observed and its text is NOT rewritten.

## 2. Synthesis arithmetic (structural pair observations, NOT candidates)

D003 valid sealed evidence (Surface G, canonical eligible OB + final FVG):
60 same-direction pairs; direction agreement 60 agree / 0 disagree; canonical
overlap 39 true / 21 false.

D004 valid sealed evidence for `EXPIRED_UNTOUCHED` with same-direction final FVG:
42 blocks; canonical overlap among those 22 true / 20 false.

The ELIGIBLE and EXPIRED_UNTOUCHED populations are lifecycle-disjoint (ELIGIBLE
blocks are untouched through decision with age <= 30 by construction; EXPIRED
blocks have age > 30 by the frozen short-circuit), so addition composes one
coherent structural surface without double counting:

* same-direction structurally-intact OB/FVG pairs: `60 + 42 = 102`
* exact canonical overlaps: `39 + 22 = 61`
* same-direction non-overlapping pairs: `21 + 20 = 41`

Recorded explicitly: **`102` is NOT a candidate count. `61` is NOT a candidate
count. `41` is NOT a candidate count.** They are structural pair observation
counts only. They are not eligibility counts, not strategy outputs, not
predictions, and must not be encoded as expected test outputs (tests use
synthetic fixtures only; §16).

## 3. H001 disposition — `SUPPORTED_BY_D003_D004_SYNTHESIS`

The already-preregistered H001 expected qualitative effect is observed:

* OB/FVG pair availability is not near-zero (60 + 42 structurally-intact
  same-direction pairs across the two sealed surfaces);
* same-direction OB/FVG coexistence materially exceeds exact-overlap coexistence
  (102 vs 61);
* 41 of 102 structurally coherent same-direction pairs fail exact geometric
  overlap, so exact overlap removes a substantial part of the observed pair
  surface rather than merely tracking structure absence.

The registered H001 failure condition (OB and FVG availability themselves
near-zero, or the overlap conjunction not a material attrition point) does not
hold. This is a qualitative application of the criteria registered before
D003/D004; no new numeric acceptance threshold is introduced.

## 4. Why expiry-only V002 is prohibited (mathematical futility)

Under H006 alone, structurally active canonical OBs would consist at most of:

* the existing canonical eligible structure (D003: 87 ELIGIBLE blocks, 60 of them
  with a same-direction final FVG); plus
* age-only `EXPIRED_UNTOUCHED` structure (D004: 57 blocks, 42 of them with a
  same-direction final FVG).

But preserving exact overlap gives only `61` observed exact-overlap structural
pairs. Therefore for an expiry-only / OB-only variant that preserves exact
overlap:

`candidate_ready <= Gate-11 passes <= 61 < 90`

The charter's Tier-A research target is `>= 90 raw candidates`. An expiry-only
variant is therefore mathematically futile: V002 is NOT spent on it.

## 5. Why overlap-only V002 is prohibited (structural futility)

Frozen legacy Gate-11 OB validity passes only `4 / 526` Gate-11 entrants
(D001-R001 `score_check_pass_counts`: "Valid order block present" passed 4 /
failed 522). Changing overlap while retaining the legacy OB predicate therefore
remains structurally futile. No overlap-only variant is created.

## 6. H007 — Canonical OB/FVG Structural-Pair Semantics

`phase8-v2-H007`, status `REGISTERED`, registered in this commit. Statement:
Gate-11 structure should be represented by one coherent canonical OB/FVG pair
concept rather than the conjunction of the legacy/acquisition `ob_result.valid`
predicate and mandatory exact contemporaneous geometric overlap. A canonical
structural pair consists of:

1. a confirmed same-side canonical order block that is structurally active at
   the causal decision timestamp; and
2. a final canonical FVG in the same market direction.

Exact geometric overlap remains observable evidence but is not mandatory
membership in the structural pair.

Economic rationale: H002 established a large mismatch between legacy OB validity
and canonical lifecycle structure (legacy Gate-11 OB validity passes only 4 of
526); H006 established that fixed 30-bar age alone rejects a meaningful subset of
otherwise untouched/uninvalidated blocks (57 of 133 frozen EXPIRED blocks remain
untouched AND uninvalidated at the causal decision); the H001 synthesis (§2)
establishes that same-direction canonical OB/FVG coexistence materially exceeds
exact geometric overlap (102 vs 61). The economic concept being tested is the
coherent structural relationship between the origin zone and its displacement
imbalance, not exact legacy-detector agreement plus literal price-interval
overlap.

H007 is registered after D003/D004 evidence was observed; the register records
`registered_after_evidence_was_observed: true` with the exact input records, so
the epistemic ordering is disclosed rather than hidden.

## 7. V002 identity and one-change principle

`phase6-development-v2-V002` — Canonical Structural OB/FVG Pair — is ONE
conceptual hypothesis: canonical OB/FVG structural-pair semantics. Although
implementation may touch multiple code locations, those edits are structurally
inseparable because:

* Gate 11 must evaluate one OB semantic definition;
* the FVG association must reference that same canonical block concept;
* downstream canonical strategy evaluation must use the same OB semantic
  definition — using different OB definitions before and after Gate 11 would
  create a contradictory strategy.

These consistency edits are ONE hypothesis, not separate strategy hypotheses. No
unrelated rule may change. Specifically prohibited variant shapes: expiry-only
(§4), overlap-only (§5), numeric expiry 45/60/90 or any numeric extension, any
replacement age threshold derived from the D004 age histogram, any weakening of
DXY authority.

## 8. Structural-active OB semantics (V002 evaluator)

V002 uses a VARIANT-SPECIFIC evaluator. Historical canonical V1/V001 behavior is
NOT altered. A V002 structural-active OB must satisfy:

* canonical same-side confirmed block exists;
* confirmation is causally available (`available_at <= decision_at`);
* block is not consumed;
* no invalidating close has occurred by decision time;
* no prior zone interaction has already mitigated the block;
* first-retest behavior remains consistent with existing canonical semantics.

Crucially: elapsed age greater than 30 bars ALONE must NOT reject an otherwise
untouched/uninvalidated block under V002. Age remains recorded as metadata. The
canonical 30-bar rule is NOT deleted from historical V1/V001 semantics, and
global `StrategyConfig.order_block_expiry_bars` remains 30.

## 9. No new numeric expiry value

V002 is NOT expiry 45, 60, 90, or any numeric extension. It consumes no numeric
trial and derives no threshold from D004's age histogram. Numeric trials remain
`0 / 4`.

## 10. FVG association semantics

The associated FVG must be: the frozen final canonical FVG surface; causally
available; same direction as the structural-active OB / requested trade side.
Exact geometric overlap is NOT mandatory for V002 structural-pair membership,
but is still computed and recorded descriptively. No proximity threshold; no
partial-overlap threshold; no temporal lag; no H003 rule.

## 11. Exact-overlap descriptive observer (unchanged)

The frozen canonical overlap calculation is retained verbatim as a DESCRIPTIVE
observer with its frozen tolerance. Its boolean is never fed into V002
eligibility. This preserves comparability with D001/D003/D004 surfaces.

## 12. Confluence weights and threshold preserved

The existing architecture is preserved: bias alignment 2; premium/discount 1;
OB structure 2; FVG structural relationship 1; liquidity sweep 2; maximum 8;
threshold `8/8` unchanged. For V002 only, the 2-point OB component represents
`canonical structurally-active OB present` and the 1-point FVG component
represents `same-direction final canonical FVG associated with that OB`. The
second component is NOT labeled exact geometric overlap in V002 outputs; exact
overlap remains a separately reported descriptive field.

## 13. Protected semantics unchanged

No changes to: causal candle availability; active-bar exclusion; HTF bias;
liquidity sweep; displacement detector; FVG detector thresholds; internal
structure Gate 10; premium/discount; session; news; DXY; regime; risk; broker
safeguards; entry idempotency; consumption invariants; execution lifecycle;
symbol allowlist; global `StrategyConfig.order_block_expiry_bars`; the
historical canonical evaluator (including its EXPIRED short-circuit) for
V1/V001.

## 14. Downstream consistency

The downstream canonical-strategy decision used by V002 must consume the SAME
V002 structural-active OB semantics and SAME V002 structural-pair evidence used
at Gate 11. It is prohibited to pass Gate 11 under V002 semantics and then reject
the exact same block merely because the historical canonical evaluator applies
the old age-only EXPIRED short-circuit — that would not test H007. An isolated
V002 adapter/evaluator path is allowed. The historical canonical evaluator
remains unchanged.

## 15. DXY remains authoritative

The final DXY-direction conflict behavior remains unchanged. V002 may still
produce Gate-11 passes that fail canonical strategy due to DXY. DXY is not
weakened to increase candidate count.

## 16. No candidate target encoding

The structural synthesis (102 pair observations) is motivation showing V002 is
not mathematically futile; it is NOT a predicted candidate count. `102`, `61`,
`41`, `90` must NOT be encoded as test expected strategy outputs. Tests use
synthetic fixtures only. The empirical result must derive naturally.

## 17. Success classification (preregistered BEFORE empirical observation)

* `OPPORTUNITY_SUFFICIENT` — Fold-01 `candidate_ready >= 90`. This means the
  variant merits continued research only; it does NOT establish sample
  sufficiency or profitability.
* `OPPORTUNITY_INSUFFICIENT` — `0 < candidate_ready < 90`.
* `NO_CANDIDATES` — `candidate_ready == 0`.
* `IMPLEMENTATION_FAILED` — only if H007 semantics are not functioning as
  specified.

No ranking above 90; no optimization toward 90.

## 18. Preregistered structural result metrics and prohibitions

Allowed on a future Fold-01 V002 measurement: scheduled decisions; accounting
buckets; Gate 8–13 funnel; `candidate_ready` count; candidate rate; candidate
setup IDs; long/short distribution; weekly/time distribution; session
distribution; duplicate/setup-consumption counts; V002 structural-active OB
count; associated same-direction FVG count; exact-overlap descriptive
true/false; age distribution of structural-active OBs; H007 pair-state reason
distribution. No performance metrics: no P&L, wins/losses, profit factor,
expectancy, drawdown, Sharpe, trade-return distribution, or account
balance/equity outcome. No Fold 02–04; no 2025+; no holdout.

## 19. Phase A — this governance commit

This commit is governance only: register records (`phase8-v2-H001-R001` + H001
disposition flip + H007 + V002), this specification, and narrow progress/handoff
updates. No strategy code. Parent `cd7526260ac224facb5dbf993f6e98be25cb650d`.
Pushed and remote-verified before any Phase B implementation work.

## 20. Phase B — implementation boundary (future freeze)

Implement the smallest V002-specific semantic path: an isolated V002
helper/module/evaluator that reuses canonical detectors; no duplication of
unrelated reducer logic; historical V1/V001 behavior untouched; no broad
refactors; no empirical data. Synthetic tests (§21) must pass, plus the full
repository suite (strategy semantics change). Then the Fold-01 structural
measurement tooling freezes, binds the exact V002 implementation commit, uses
`canonical_git_blob_v1`, emits structural metrics only, fails closed on
boundary/provenance mismatch, refuses Tier B and holdout, and writes
non-overwriting output. The tooling is NOT executed in the freeze task.

## 21. Required synthetic invariant coverage (Phase B tests, synthetic data only)

At least: young untouched canonical block remains structurally active;
>30-bar untouched/uninvalidated block remains structurally active under V002;
>30-bar touched block is not structurally active; >30-bar invalidated block is
not structurally active; consumed block rejected; premature block rejected;
LONG and SHORT behavior; same-direction FVG associates; opposite-direction FVG
does not associate; exact-overlap-true pair accepted; exact-overlap-false
same-direction pair accepted; no FVG rejected; Gate 11 still requires 8/8; DXY
behavior unchanged; news/session/risk unaffected; historical canonical evaluator
still produces original EXPIRED behavior. None of `102`, `61`, `41`, `90`
appears as an expected strategy output.

## 22. Store compatibility decision (documented before empirical execution)

Before any empirical execution, the V002 task must explicitly document whether
V002 requires (A) a fresh Fold-01 feature-store rebuild or (B) reuse of the
existing immutable V001 store, determined from INPUT SEMANTICS, not convenience:
reuse is allowed only if V002 strategy outputs are not stored as immutable
inputs and every V002-required causal input is reconstructable causally from the
existing snapshots; if any V002-required causal input is absent, a fresh rebuild
is required. The decision is recorded in the implementation/tooling freeze
material. Do not guess.

## 23. Fold / holdout boundary and hard stop

V002 research remains Fold 01 only:
`[2024-04-01T00:00:00Z, 2024-06-08T00:00:00Z)` plus the causal warm-up that
existing Fold-01 semantics already require, against the preserved V001 store
`fold-01-a8b406884ab3525a` unless §22 mandates a fresh rebuild. Folds 02–04,
2025+ data and holdout must not be inspected; Tier B remains sealed until V002
demonstrates `candidate_ready >= 90` on contaminated Tier-A Fold 01. After the
implementation/tooling-freeze commit is pushed and remote-verified, this task
STOPS — V002 is NOT executed — and returns for supervisory review.

## 24. Budget

Registration and implementation consume zero budget. At the tooling freeze:
diagnostics `3 / 12`; strategy variants `1 / 8` observed; numeric parameter
trials `0 / 4`; `UPWARD STRATEGY-VARIANT / PARAMETER-TRIAL BUDGET REVISION
PROHIBITED = ACTIVE`. The H001 evidence synthesis consumed zero diagnostic
budget and created no D005. At the instant first Fold-01 V002 strategy behavior
is empirically observed, strategy variants becomes permanently `2 / 8`.
