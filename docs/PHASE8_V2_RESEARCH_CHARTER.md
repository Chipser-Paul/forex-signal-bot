# PHASE 8 — `phase6-development-v2` RESEARCH CHARTER (APPROVED / PREREGISTERED)

**Status:** `APPROVED / PREREGISTERED` — this is the governing preregistration for the `phase6-development-v2` research cycle; no V2 strategy research may begin except under these rules.
**Charter identity:** `phase6-development-v2-research-charter-r2` (r1 drafted; r2 amended per supervisory review: sequential fold release, raw-candidate target semantics, trial-budget lock). The authoritative deterministic charter identity and final SHA-256 are recorded in `docs/PROJECT_CONTINUATION_HANDOFF.md` and `docs/PHASE8_PROGRESS.md`.
**Amendment log:** r1→r2 — (1) §3/§18: reserved folds released sequentially (Fold 02 → 03 → 04) under fail-fast contamination minimization; (2) §13: raw-candidate counts clarified as an upstream opportunity-density screen (90/60 reworded as research/headroom targets, two-stage post-freeze feasibility protocol); (3) §11: trial budget locked — no upward revision after the first strategy-variant result.
**Research identity governed by this charter:** `phase6-development-v2` (development-scoped; deliberately **not** `phase6-frozen-v2`)
**Canonical basis:** branch `integration/phase8-checkpoint-20260921`, commit `94b278a81fcdadac295054833bf79e9dc75140b4`, tree `15b748e6f666041dfde37f37c979bdab1a1c3fec`
**Fingerprint contract in force:** `canonical_git_blob_v1` (`bot/scientific/canonical_bytes.py`, `docs/PHASE8N_CANONICAL_BYTE_CONTRACT.md`)

This document is a **preregistration proposal**. Until supervisory approval it
binds nothing and changes nothing: no strategy code, no validation semantics,
no fold definitions, no plan identities. It was drafted by reading canonical
source and governance records only — no strategy replay, no new Fold-01
counts, no Fold 02–04 inspection, no holdout access, no profitability
computation, and no trading-platform contact.

---

## 1. Historical context: V1 is closed

`phase6-frozen-v1` is immutable historical evidence.

* Disposition (sealed): `REJECTED_FOR_SAMPLE_SIZE_FUTILITY`
  (`docs/PHASE8_FEASIBILITY_DISPOSITION_V1.md`).
* Its 64-cell evaluation plan
  `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81` remains
  `PROHIBITED_DUE_TO_SAMPLE_SIZE_FUTILITY` — retained as a preregistered
  artifact, never to be executed.
* V1 proved exactly one scientific fact: the required sample size
  (≥ 30 closed trades per fold) was **mathematically unreachable in Fold 01**
  under the frozen semantics (0 raw candidates ⇒ 0 closed trades). It
  established no profitability conclusion in either direction.

V1 will not be modified, reopened, re-thresholded, republished, given
retroactive variants, or reinterpreted.

## 2. Known V1 diagnostic evidence (already-contaminated; may inform hypotheses)

From the V1 feasibility audit, Fold 01 (2024-04-01 → 2024-06-08):

* 13,269 scheduled decisions: 7,273 `skip` + 5,827 `wait` + 169
  `news-blocked` + **0** `candidate_ready` (exact reconciliation).
* Of 526 decisions reaching frozen confluence scoring: 522 scored **5/8**,
  4 scored **7/8**, 0 scored **8/8** (frozen threshold 8/8).
* FVG/order-block overlap failed **526/526**; valid-order-block failed
  **522/526**.

This is `DEVELOPMENT_DIAGNOSTIC_EVIDENCE`. It may motivate the hypotheses in
§7–§8. It may never be used to justify a bare threshold change (§9) or to
tune any numeric parameter (§12).

## 3. Evidence tiers (preregistered data hierarchy)

### Tier A — V2 research/design evidence: Fold 01

`[2024-04-01T00:00:00Z, 2024-06-08T00:00:00Z)`

Already classified in the canonical contamination register
(`baseline/phase8_contamination_register.json`, artifact
`phase8n_feasibility_audit_v1_fold01`):
`DEVELOPMENT_EVIDENCE — CONTAMINATED_FOR_FUTURE_STRATEGY_DESIGN`.

Fold 01 is the **only** fold V2 research may observe strategy behavior on.
It may never again be represented as untouched evidence for V2.

### Tier B — development-confirmation evidence: Folds 02–04 (reserved, uninspected)

* Fold 02 `[2024-06-09 → 2024-08-16)`, Fold 03 `[2024-08-17 → 2024-10-24)`,
  Fold 04 `[2024-10-25 → 2025-01-01)` — three equal 68-day evaluation
  windows separated by the canonical one-day embargo gaps
  (`bot/validation/development_evaluation_plan.py`).
* **Reservation during the entire V2 design/research cycle:** do not inspect
  their gate distributions, candidate counts, candidate rates, trade counts,
  pass/fail outcomes, P&L, or parameter-response behavior. Do not build
  Fold 03/04 feature stores out of research curiosity. (Fold 02's store
  already exists from Phase 8N-K; it may remain on disk but remains
  uninspected for strategy behavior.)
* **Purpose:** after exactly one V2 candidate is selected, the reserved
  folds provide a genuine development-level confirmation test
  (candidate-frequency feasibility) before any new evaluation plan is
  written.
* **Sequential release rule (fail-fast contamination minimization).** The
  reserved folds are **not** exposed together. The confirmation sequence is
  strictly: Fold 02 → (only if Fold 02 passes its preregistered feasibility
  stage) Fold 03 → (only if Fold 03 passes) Fold 04.
  * If the frozen V2 candidate fails on Fold 02: reject the candidate, mark
    Fold 02 as inspected/contaminated for subsequent strategy design, and
    leave Fold 03 and Fold 04 untouched.
  * If it passes Fold 02 but fails Fold 03: reject the candidate; Fold 02
    and Fold 03 become inspected development evidence; Fold 04 remains
    untouched.
  * Only a candidate surviving Fold 02 and Fold 03 may inspect Fold 04.
  * No later strategy candidate may represent an already inspected fold as
    untouched.
  * The contamination register must record each fold release as a separate
    append-only artifact when it occurs (§16).

**Architectural compatibility assessment.** The reservation is compatible
with the canonical fold design:

1. The four evaluation windows are disjoint and equal, separated by embargo
   gaps — no temporal overlap of evidence.
2. Walk-forward mode is `ANCHORED`: every fold's training window ends at its
   own purge gap, and the training data (from `2024-01-01`) precedes each
   evaluation window. Training inputs are shared market facts, not
   strategy-behavior observations; the reservation governs **strategy
   outputs** (gates, candidates, fills, trades), which are produced only
   when a fold's cells are actually run.
3. Warm-up windows reach back to `2024-01-01` for market/factor history
   (candles, DXY, news, sessions). These are causal inputs defined by the
   frozen plan and are not fold-specific strategy evidence; observing them
   is not Tier-B inspection.
4. Feature stores are per-fold and immutable; no Fold 02–04 store needs to
   be built or read for Tier-A research.

No conflict exists between the Tier-B reservation and the fold architecture.
The reservation therefore stands **without weakening**; if a future technical
requirement ever forces Fold 02–04 inspection during design, that is a
charter violation to be recorded under §16, not silently absorbed.

### Tier C — untouched holdout (2025+)

Inaccessible. No V2 development decision may depend on it. It is the
eventual external judge and is not discussed further in this charter except
as a boundary.

## 4. Research objective

The first V2 objective is **not profitability optimization**. It is:

> Develop economically defensible strategy semantics capable of producing a
> scientifically measurable number of candidate opportunities without
> weakening existing causal, execution, risk or broker-safety protections.

The cycle must answer:

1. Why did V1's structural setup semantics suppress **every** candidate?
2. Are the OB and FVG detectors individually behaving according to their
   intended market definitions?
3. Is the required simultaneous geometric relationship between OB and FVG
   economically justified?
4. Is their temporal relationship overly restrictive?
5. Are mitigation/invalidation rules correct?
6. Is the confluence architecture treating independent evidence sensibly?
7. Can a revised structure generate sufficient opportunities without simply
   lowering standards?

Profitability must not be optimized while answering these (§10 metrics).

## 5. Protected infrastructure (not weakenable for frequency)

V2 research may not weaken any of the following merely to raise trade
frequency. Any proposal touching one requires separate architectural
justification and is **not** ordinary strategy tuning:

causal candle availability; active-bar exclusion; no future leakage; HTF
availability semantics; execution lifecycle legality; entry idempotency;
setup-consumption invariants; risk authority; equity-based drawdown
protection; circuit protection; volume precision; broker tick freshness;
spread protections; projected-margin safeguards; order retry/revalidation
rules; production symbol allowlist (`XAUUSDm` only); news fail-closed
behavior; validation fidelity requirements.

## 6. Research identity and the path to freeze

`phase6-development-v2` is a research-stage identity. A frozen V2 identity
may only be created later, after: (1) charter approval; (2) permitted
research trials; (3) candidate selection; (4) implementation review;
(5) explicit freeze authorization; (6) canonical fingerprint creation under
`canonical_git_blob_v1`. Until then nothing may be named `phase6-frozen-v2`
(§17).

## 7. Primary research areas (hypothesis themes, not implementations)

### 7.1 Order-block semantics

How an OB is identified; required displacement; candle/body/wick
definitions; swing context; mitigation; invalidation; expiry/age;
directional consistency; and whether V1 required properties that rarely
coexist in real XAUUSDm structure.

### 7.2 Fair-value-gap semantics

Exact FVG definition; minimum displacement/gap criteria; direction;
freshness; mitigation; expiry; HTF/LTF relationship.

### 7.3 OB/FVG interaction (primary suspect from V1 evidence)

Whether the frozen implementation requires an unnecessarily exact
**simultaneous geometric overlap**. Conceptual alternatives that may be
studied later (hypotheses only — none implemented by this charter):
containment; partial overlap; proximity; sequential confirmation;
same-impulse relationship; FVG generated by displacement from an OB;
temporal association rather than exact overlap.

## 8. Confluence architecture (open scientific question)

> Should all eight V1 conditions be mandatory simultaneously?

The answer is neither assumed yes nor assumed no. Potential research
directions: mandatory safety/structure gates plus scored confirmations;
groups of equivalent confirmations; hierarchical gates; necessary versus
supporting conditions.

**Prohibited justification:** changing `8/8 → 7/8` because four historical
Fold-01 decisions scored 7/8 is direct outcome-driven threshold tuning
against contaminated evidence. Any scoring change must arise from an
independently stated market hypothesis (economic rationale for *why* the
evidences are or are not independent, and *why* the proposed combination is
the economically meaningful one).

## 9. Research-hypothesis register (append-only)

All hypotheses must be recorded, with an ID assigned **before** testing, in
an append-only register (`baseline/phase8_v2_hypothesis_register.json`,
created only after charter approval; existing records are never rewritten).

Record schema per hypothesis:

| Field | Content |
|---|---|
| `hypothesis_id` | e.g. `phase8n-v2-H001` (monotonic, never reused) |
| `statement` | the hypothesis |
| `economic_rationale` | why the market should behave this way (independent of outcomes) |
| `code_components` | affected modules/symbols |
| `expected_qualitative_effect` | predicted structural change |
| `expected_frequency_effect` | predicted effect on candidate frequency |
| `potential_failure_mode` | what evidence would refute it |
| `data_permitted` | tiers allowed (must be ⊆ {A}) |
| `metrics_permitted` | subset of §10 structural metrics |
| `implementation_required` | yes/no (read-only diagnostic vs variant) |
| `result` | filled after the trial, once |
| `disposition` | e.g. `SUPPORTED` / `REFUTED` / `INCONCLUSIVE` / `ABANDONED` |

## 10. Permitted early metrics (structural only)

Permitted before any profitability authorization: number of scheduled
decisions; gate reach counts; rejection counts and reason-code
distribution; candidate count; candidate rate; candidate setup IDs; time
distribution; session distribution; long/short distribution; setup
duplication.

Additional permitted non-performance diagnostics (proposed): per-gate
failure co-occurrence matrices; OB/FVG candidate-count marginals (how many
blocks, how many gaps, how many near-misses by each relaxed criterion);
temporal distance distributions between OB and FVG events; score
distributions among reached decisions; session/hour histograms.

**Prohibited during initial semantic research:** profit; loss; P&L;
expectancy; profit factor; win rate; Sharpe; drawdown; trade-return
distributions; any outcome-based parameter selection.

A candidate must first prove it can produce measurable opportunities.

## 11. Trial budget (finite, proposed)

| Class | Proposed maximum | Justification |
|---|---|---|
| Diagnostic investigations (read-only, no candidate output change) | **12** | Enough to decompose OB semantics, FVG semantics, their interaction and the confluence marginals on Tier-A data (≈ 3–4 per research area). Diagnostics create no candidate strategy, so the risk of dredging is bounded by the metrics whitelist (§10). |
| Strategy variants (rule/semantic variants that can change candidate output) | **8** | One-change trials across three areas (OB, FVG, interaction) ≈ 5–6 single-hypothesis variants, ≤ 2 theory-driven confluence-architecture variants, 1 reserve. Eight is small enough that final selection remains scientifically interpretable and large enough to cover the hypothesis space §7–§8 actually motivates. |
| Numeric parameter trials | **4** | Only permitted inside a variant family **after** its qualitative hypothesis is supported, each with a pre-stated directional economic rationale. Explicitly prohibited: brute-force, grid, genetic, Bayesian or any automated hyperparameter search; thousands of variants. |

**Budget lock.** Before the first strategy-variant result is observed, the
charter may still be corrected during supervisory review. **After the first
strategy-variant result has been observed, upward budget revision is
prohibited.** The budget may be **reduced**; it may never be increased. If
the strategy-variant or numeric-trial budget is exhausted without an
acceptable development candidate, `phase6-development-v2` research
terminates unsuccessfully. Further strategy research then requires: a new
research-charter version, explicit supervisory approval, complete
carry-forward of contamination records, and complete carry-forward of the
previous hypothesis/trial ledger. No informal extension is created because
previous trials looked "promising".

## 12. One-change principle

Each strategy trial alters **one** conceptual hypothesis at a time. Bundles
(lower threshold + wider FVG + looser OB + longer sessions + changed ATR)
are prohibited. If multiple changes are structurally inseparable, the
hypothesis record must say exactly why. This preserves causal
interpretability of every observed structural difference.

## 13. Candidate sufficiency target (raw ≠ closed)

The preregistered scientific requirement remains **≥ 30 closed trades per
fold**. Raw candidates are only a necessary feasibility condition: closed
trades ≤ fills ≤ entry intents ≤ raw candidates.

Raw→closed attrition sources: intent rejection; entry expiry;
broker/risk rejection; unfilled entries; duplicate/setup consumption; open
positions at fold end.

**Proposed V2 design targets (buffered, not exactly 30):**

* During Tier-A research: a variant is opportunity-sufficient only if it
  produces **≥ 90 raw candidates in Fold 01** (3× the closed-trade minimum).
* Post-freeze feasibility on each reserved fold: **≥ 60 raw candidates**
  (2× minimum) before a new evaluation plan may even be drafted.

Buffer reasoning: intent/expiry/broker/consumption attrition classes can
each consume a material fraction of candidates; 2–3× is the smallest
defensible engineering margin that still expects ≥ 30 closed trades without
invoking any Fold 02–04 observation. These factors are set from attrition
structure, not from any reserved-fold measurement.

**What a raw-candidate count does and does not establish.** Raw-candidate
counts provide an **upstream opportunity-density screen only**. They do
**not** establish closed-trade sample sufficiency. Precisely:

* `raw ≥ 90` (Fold 01 research target) means the variant merits continued
  research. `90` is a deliberately conservative engineering/research
  buffer — 3× headroom over the historical 30-closed-trade requirement —
  **not** a statistically derived proof, and it does **not** imply that 90
  raw candidates will produce 30 closed trades.
* Variants must **not** be ranked by maximizing raw candidate count once
  adequate density has been achieved: producing more candidates is not
  inherently better, and no variant may be tuned to land just above 90.
  Economic coherence and simplicity remain selection criteria (§14).

**Post-freeze reserved-fold feasibility protocol (two conceptual stages).**

* **Stage 1 — raw-candidate futility screen.** If raw candidates in the
  fold are `< 30`, the candidate is rejected immediately for sample-size
  futility, because `closed ≤ raw < 30`. (`raw ≥ 30` alone proves nothing:
  it does not establish sample sufficiency and does not by itself authorize
  empirical evaluation.)
* **Stage 2 — lifecycle/sample feasibility.** If the screen passes, a
  separately preregistered, non-profitability lifecycle feasibility method
  determines whether the frozen candidate can produce the required number
  of **completed** trades under the evaluation semantics (no P&L metric is
  needed merely to count completed trades). **That method is deliberately
  not designed or executed in this charter** — the future V2
  evaluation/feasibility plan must define it before execution, under the
  new plan identity.
* The `≥ 60 raw candidates` figure for a reserved fold is therefore
  classified `RESERVED_FOLD_RAW_HEADROOM_TARGET`: a conservative screen
  level that permits further feasibility examination — it is **not** a
  scientific feasibility pass and cannot itself authorize empirical
  evaluation.

## 14. Candidate selection rule (preregistered)

Exactly one development candidate will eventually be selected. Selection is
**never** "whichever made the most money" (profitability is not even
measurable under §10). Preregistered criteria, applied to the hypothesis
ledger and Tier-A structural evidence:

1. economic coherence (each surviving change maps to a stated market
   hypothesis);
2. causal correctness (no leakage; all protected invariants §5 intact);
3. code simplicity (smallest semantic diff that answers the hypothesis);
4. opportunity sufficiency (§13 targets met on Tier A);
5. stability across time within permitted research data (no pathological
   clustering of candidates; reasonable dispersion across weeks/sessions);
6. long/short balance of opportunities;
7. limited complexity increase;
8. no weakening of protected safety architecture.

Ties resolve toward the simpler, more coherent candidate. Selection happens
**before** any reserved-fold run; the reserved folds are then used only for
the §13 feasibility confirmation of that single candidate.

**Frequency is not the objective.** Once a variant demonstrates adequate
opportunity density, a greater raw candidate count is **not** automatically
preferred: selection must not become `argmax(candidate_count)`. Opportunity
density is a feasibility property, not the optimization objective. Selection
remains the preregistered combination above — economic coherence, causal
correctness, simplicity, adequate opportunity density, temporal
distribution, long/short balance, absence of pathological clustering,
complexity discipline, and preservation of protected safeguards.

## 15. Stopping rules (failure is acceptable)

V2 research stops — and does not force V2 into existence — when any of:

* the trial budget (§11) is exhausted without an opportunity-sufficient
  candidate;
* no economically defensible variant reaches §13 frequency;
* reaching frequency would require weakening a protected §5 safeguard;
* hypotheses become outcome-driven rather than theory-driven;
* implementation semantics cannot be made causal;
* the contamination boundary (§16) is violated;
* reserved folds or holdout are exposed unexpectedly;
* scientific identity/provenance fails (fingerprint, contract guard, or
  register integrity).

A stop is recorded with its rule number and evidence; the identity remains
development-scoped and unspent budget does not roll into a future cycle
without a new charter.

## 16. Contamination accounting (immediate, never hidden)

* Fold 01: already `CONTAMINATED_FOR_FUTURE_STRATEGY_DESIGN` (register
  artifact `phase8n_feasibility_audit_v1_fold01`); all V2 research reads of
  Fold 01 inherit that status and need no new record per read, only the
  hypothesis-ledger linkage (§9) for each *use*.
* Folds 02–04: reserved. Any inspection — even accidental — of their
  strategy behavior during design must be recorded **immediately** as a new
  append-only register artifact
  (`artifact_id: phase8n_v2_unreserved_fold0N_inspection`, category
  `DEVELOPMENT_EVIDENCE — CONTAMINATED_FOR_FUTURE_STRATEGY_DESIGN`, with
  what/when/why and the affected hypothesis IDs), and the charter's
  Tier-B assumptions must be re-evaluated in a written addendum.
* Holdout/2025+: any exposure is a §15 stopping event, recorded the same
  way (`phase8n_v2_holdout_exposure`) — never hidden, never absorbed.
* **Reserved-fold inspection consequence.** Any reserved fold (Fold 02–04)
  inspected during post-freeze feasibility — passed or failed — becomes
  development evidence for **all later strategy research**; an uninspected
  later fold remains reserved. This status change is append-only and is
  recorded in the register immediately when the fold is released (one
  artifact per fold, per §3). Accidental reserved-fold inspection is not
  erased, ignored, or retroactively reclassified.
* The register (schema v1, append-only) remains the single canonical
  contamination ledger; V2 adds records, never edits or removes them.

## 17. Freeze criteria (all required before `phase6-frozen-v2` exists)

1. Research budget completed or a §15 stopping rule reached cleanly.
2. Exactly one candidate selected under the preregistered §14 rule.
3. Implementation reviewed (code review recorded).
4. Strategy semantics documented.
5. Complete configuration frozen.
6. All tests pass (focused + relevant suites; no new failures).
7. No unresolved semantic ambiguity.
8. Exact Git commit recorded on the canonical branch.
9. Fingerprints generated under `canonical_git_blob_v1` (source/config
   surfaces: strategy, validation pipeline, cost policy as applicable).
10. Prospective contract guard passes (`validate_prospective_contract`;
    legacy/missing/unknown rejected).
11. Trial/hypothesis ledger sealed (append-only, disposition filled for
    every opened hypothesis).
12. Contamination ledger updated (all research reads accounted for).
13. No holdout exposure at any point.
14. Explicit supervisory freeze authorization.

Until all fourteen hold, the identity remains `phase6-development-v2`.

## 18. Post-freeze path (no V1 reuse)

After one candidate becomes `phase6-frozen-v2`:

1. no more strategy tuning, of any kind;
2. run candidate-frequency/sample-size feasibility on the reserved
   development folds (Tier B) **sequentially — Fold 02, then Fold 03 only
   if Fold 02 passes, then Fold 04 only if Fold 03 passes** (§3 sequential
   release rule) — under the §13 two-stage protocol (raw-candidate futility
   screen, then preregistered lifecycle/sample feasibility), structural
   metrics only;
3. if feasibility fails at any fold, reject that candidate and stop
   releasing further folds (a new research cycle would require a new
   charter; the folds actually released are recorded as inspected
   development evidence, the rest stay reserved);
4. before any new evaluation plan is written, it must explicitly
   preregister its sample-size contract — minimum closed-trade requirement,
   the exact unit it applies to (per fold / per scenario / primary scenario /
   other), treatment of trades crossing a fold boundary, treatment of open
   positions at evaluation end, and whether scenario-dependent fills can
   change sample-size qualification — rather than silently inheriting V1's
   `≥ 30 closed trades per fold` semantics; retaining 30 is permitted only
   if scientifically justified and stated under the new plan identity;
4. if it passes, create a **new** scientific evaluation plan (new identity,
   new fingerprint under the canonical-byte contract) — the V1 plan identity
   `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81` is never
   reused;
5. only then consider the full empirical Phase 8 matrix under that plan;
6. holdout remains inaccessible until its own separate authorization point.

## 19. Safety record of this charter task

This charter is planning/documentation only. During its drafting there were:
no strategy edits; no experiments or replays; no new Fold-01 counts; no
Fold 02–04 inspection (their behavior remains unobserved); no holdout or
2025+ access; no profitability computation; no MT5/Streamlit launch; no
trading-API call; no commit; no push. Read-only inspections were limited to
canonical source, canonical documentation, the V1 disposition and the
contamination register (metadata), plus the canonical fold-window
definitions already published in the plan source. The canonical handoff is
deliberately **not** updated in this task.

---

*End of charter r2. Supervisory approval received: this document is the
binding preregistration for the `phase6-development-v2` research cycle. The
sealed research budgets, evidence tiers and stopping rules may not be
relaxed except through a new charter version under §11.
