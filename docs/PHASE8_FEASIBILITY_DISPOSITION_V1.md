# Phase 8 Feasibility Disposition — V1 (2026-09-21)

Candidate: `phase6-frozen-v1`

Disposition: `REJECTED_FOR_SAMPLE_SIZE_FUTILITY`

Scientific feasibility verdict: `FEASIBILITY INSUFFICIENT — NO RUN AUTHORIZED`

Classification: immutable scientific governance record. This document is
sealed at publication; it is not a research document, a tuning record or a
profitability analysis. The V1 evaluation plan remains retained as a frozen
historical preregistration and is now additionally governed as
`PROHIBITED_DUE_TO_SAMPLE_SIZE_FUTILITY` (see §6 below); the separately
invalidated plan identity keeps its own distinct invalidation status.

---

## 1. Canonical basis of this disposition

- Repository: `https://github.com/Chipser-Paul/forex-signal-bot.git`
- Branch: `integration/phase8-checkpoint-20260921`
- Audit baseline commit: `c38f9dc8a0c75e7d3a563f98ef927102f37fa9bc`
  (tree `4f8c46852765949bbb8610af205cd42de53347be`, parent
  `1c593f5e14597b6b25a8abe702457e71a10e545c`, sanitized parentless root)
- The audit operated from a fresh clone of that exact commit and produced the
  counts reproduced below from the published fold-01 feature store through
  the untouched frozen shared gate reducer.

## 2. Frozen identities referenced (unchanged by this publication)

| Identity | Value |
| --- | --- |
| Frozen candidate | `phase6-frozen-v1` (strategy_configuration_mutation `PROHIBITED`; strategy fingerprint `c764cef0993665470dec939789c02bebbaef6c052977a059edb176dc95053605`, bound inside the plan packages; no standalone candidate package exists) |
| Valid frozen development evaluation plan | `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81` (package.json SHA-256 `5a8bdf165bd1a61a9408a119443d573ee7f72260e57e484ac01dcb8350c1cd40` at disposition time) |
| Evaluation-plan fingerprint | `adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09` |
| Runner compatibility record | `evidence-runner_compatibility-v1-a81ef827217a69c6` (package.json SHA-256 `024677aca9c9719cd8d41505030be50216eadf26db669bf37edd7c87d96ee151`) |
| Invalidated plan (separate status, unchanged) | `evidence-development_evaluation_plan-v1-ba2745f96fda3939` / `d69bbed4542d9517dc46d043d12324f6a921a846bca39c30e57fdc3774779c72` — `INVALIDATED_BEFORE_EXECUTION` (package.json SHA-256 `72e73ab66fe60e54c88ce860377cd85c6bf03d823f7b5b4f6692675ad854f50f`) |
| Plan disposition package | `evidence-development_plan_disposition-v1-dac472a23118c880` (package.json SHA-256 `110a330e74cc9a54a9f19755030c986f3a6a0443c7dca0346c38b434b2be0717`) |
| Fold-01 feature store | `fold-01-1d710826193a6767` (store SHA-256 `1d710826193a67671e99f968160b2f8d586444f749a7f39e94c3ce6c04b0255e`; 13,269 decision rows; coverage `full`) |
| Evaluation design | 16 scenarios x 4 folds = 64 mandatory cells (never executed) |

None of these artifacts was modified by this publication; byte-level hashes
were recorded before and after (see §8).

## 3. Fold 01 evidence (complete accounting)

Scheduled decisions: **13,269** (every M5 decision of fold-01 served from the
published full-coverage feature store `fold-01-1d710826193a6767` and
evaluated exactly once through the frozen shared gate reducer with chained
setup state).

Mutually exclusive canonical terminal outcomes:

| Outcome | Count |
| --- | --- |
| `skip` | 7,273 |
| `wait` | 5,827 |
| `news-blocked` | 169 |
| `candidate_ready` | 0 |

Reconciliation: **7,273 + 5,827 + 169 + 0 = 13,269** (exact; mutually
exclusive and exhaustive; zero error outcomes; zero insufficient-history
outcomes).

Raw frozen-strategy candidate decisions: **0**
(`raw_strategy_candidate_decisions = 0`).

Scientific upper-bound argument (recorded explicitly):

> closed trades <= authoritative fills <= entry intents <= raw strategy
> candidates

With `raw strategy candidates = 0` it follows that **closed trades <= 0**.

The preregistered minimum requirement is **>= 30 closed trades per fold**
(`docs/PHASE8M_DEVELOPMENT_EVALUATION_PLAN.md`, metrics line:
`minimum_closed_trades_per_fold = 30`). Fold 01 therefore cannot satisfy the
minimum-sample requirement under the frozen candidate, and sample-size
futility is established **before** any profitability evaluation.

This upper bound is scenario-independent: candidates were counted at zero
open positions, the most permissive cell state, so no execution scenario can
increase the count. Every closed trade requires a confirmed entry fill; the
committed pipeline appends a pending entry intent only after a
`candidate_ready` decision; therefore the chain above is sound.

## 4. Fold 01 gate-distribution evidence (DEVELOPMENT_DIAGNOSTIC_EVIDENCE)

Read-only diagnostic findings from the same audit (engineering evidence
only, not profitability evidence, and not a basis for changing any strategy
rule):

- 526 decisions reached the confluence-scoring stage (gate 11).
- Raw score distribution: **522 decisions scored 5/8; 4 decisions scored
  7/8; 0 decisions scored 8/8.**
- The frozen candidate threshold was **8/8** (`confluence_threshold = 8` in
  the frozen `StrategyConfig`; the frozen scorer's maximum attainable score
  is 8, so a pass requires perfect confluence).
- Failure profile at gate 11: the FVG/order-block overlap requirement failed
  for **all 526** scored decisions; the valid-order-block requirement failed
  for **522 of 526**; the liquidity-sweep and premium/discount requirements
  passed in ~99% of scored decisions.
- Earlier frozen-gate funnel (first-failure reasons, mutually exclusive):
  `htf_bias_unconfirmed` 4,447; `liquidity_sweep_missing` 3,709 (wait);
  `dxy_unsafe_or_conflicting` 1,138; `displacement_missing` 2,118 (wait);
  `internal_structure_missing` 963; `score_below_threshold` 526;
  `session_closed` 199; `news_blackout` 169.

Classification: `DEVELOPMENT_DIAGNOSTIC_EVIDENCE`. These observations are
recorded to make the rejection auditable and reproducible. They are not
profitability evidence and were not used to modify any strategy rule.

## 5. Folds 02–04

| Fold | Status |
| --- | --- |
| Fold 02 | `NOT_ATTEMPTED_DUE_TO_EARLY_FUTILITY` |
| Fold 03 | `NOT_ATTEMPTED_DUE_TO_EARLY_FUTILITY` |
| Fold 04 | `NOT_ATTEMPTED_DUE_TO_EARLY_FUTILITY` |

The fail-fast feasibility protocol establishes that Fold 01 alone is
sufficient to reject the candidate for minimum-sample futility; later folds
were neither verified nor built beyond their pre-existing state (folds 03/04
feature stores were never built; the fold-02 store was not additionally
verified in the audit).

## 6. 64-cell plan disposition

The existing 64-cell evaluation package
`evidence-development_evaluation_plan-v1-4a6ab94c3e303c81` remains
**byte-for-byte unchanged** on disk. It is retained as a historical
preregistered artifact. This disposition adds the governance determination
that execution of that plan for `phase6-frozen-v1` is:

`PROHIBITED_DUE_TO_SAMPLE_SIZE_FUTILITY`

The plan is **not** deleted, rewritten or replaced, and it is **not**
authorized for execution. The already-invalidated plan
`evidence-development_evaluation_plan-v1-ba2745f96fda3939`
(`INVALIDATED_BEFORE_EXECUTION`) keeps its own separate status; the two
dispositions are distinct and must not be conflated.

Consequence recorded for future operators: the frozen V1 plan embeds the
contamination register hash as frozen at plan-freeze time; the §7 register
append legitimately changes the register's live hash, so the V1 plan's
input-firewall re-verification will (by the frozen fail-closed design) report
readiness drift for that plan. This is the expected behavior for a plan that
is no longer authorized for execution and is not a corruption signal.

## 7. Contamination register update

The canonical Phase 8 contamination register
(`baseline/phase8_contamination_register.json`) has been appended (not
rewritten) with one explicit record covering exactly the Fold 01 information
now known to the development process:

- the total scheduled decision count (13,269);
- the decision-state distribution (7,273 skip / 5,827 wait / 169
  news-blocked / 0 candidate_ready);
- the zero raw-candidate count;
- the confluence-score distribution (522 x 5/8, 4 x 7/8, 0 x 8/8);
- the FVG/order-block interaction failure distribution (526/526 FVG overlap
  failures; 522/526 valid-order-block failures);
- the resulting sample-size-futility determination.

The record states that Fold 01 has now been inspected and may influence
subsequent strategy research, and that Fold 01 must **not** later be
represented as untouched validation or holdout evidence for any V2 strategy
candidate whose design is influenced by this result. Classification:
`DEVELOPMENT_EVIDENCE — CONTAMINATED_FOR_FUTURE_STRATEGY_DESIGN`.

The untouched holdout remains separate and was not accessed. No holdout or
2025+ market data was read during the audit or during this publication.

## 8. Audit-evidence identity and frozen-artifact integrity

The compact manifest of accepted feasibility-audit artifacts (logical name,
role, size, SHA-256, timestamps, classification, storage location) is
published as `baseline/feasibility_audit_v1_artifact_manifest.json`. Raw
audit outputs remain **outside Git**; no Parquet, archive, raw market data,
owner evidence, feature store or log file was committed.

Frozen artifacts were hashed immediately before and immediately after the
governance edits of this publication; all hashes were identical
pre/post (no frozen artifact changed). The only file whose hash intentionally
changed is the contamination register, by explicit append, as required by the
publication contract and documented in §6–§7.

## 9. What this result does and does not mean

This result does **not** establish that `phase6-frozen-v1` is profitable or
unprofitable. No profitability conclusion was reached.

The result establishes only that the frozen candidate cannot generate enough
observations in Fold 01 to satisfy the preregistered minimum sample-size
requirement (>= 30 closed trades per fold).

No scientific conclusion was produced for any of the following, and none of
them was calculated during the audit or this publication:

- profitability;
- P&L;
- profit factor;
- win rate;
- expectancy;
- maximum drawdown;
- bootstrap confidence intervals;
- risk-adjusted performance;
- robustness across the 64-cell matrix.

## 10. Reproducibility engineering debt (recorded, not fixed)

`REPRODUCIBILITY_ENGINEERING_DEBT — MUST BE RESOLVED BEFORE V2 SCIENTIFIC FREEZE`

The audit discovered a newline-dependent reproducibility problem: several
published identity bindings (the 8N-K pipeline fingerprint and the cost
policy's execution-model fingerprint) hash raw working-tree bytes, so their
reproduction depends on the checkout's CRLF/LF representation
(`core.autocrlf`). Per the publication boundary, this was **not** fixed here:
no hashing helper, fingerprint implementation or repository byte
representation was changed.

The issue did **not** invalidate the V1 sample-size-futility result: the
zero-candidate conclusion arises from frozen strategy semantics (gate funnel
and confluence scoring over the published fold-01 feature store), upstream of
any profitability or execution-cost evaluation, and was independently
reproduced from the canonical checkpoint and matched the prior engineering
probe exactly.

Future scientific fingerprints must use a versioned canonical-byte contract
(explicit newline normalization inside the fingerprint computation, or
byte-exact checkout guarantees recorded as identity preconditions) before any
V2 candidate can be frozen. Implementing that contract belongs to a separate
task.

## 11. Consequences recorded in governance

Recorded in `docs/PROJECT_CONTINUATION_HANDOFF.md` (and summarized in
`docs/PHASE8_PROGRESS.md`):

- Phase 0–7 remain complete; Phase 8 feasibility infrastructure functioned
  as intended (it measured, reconciled and fail-closed exactly as designed).
- `phase6-frozen-v1` is rejected for sample-size futility; Fold 01 generated
  zero raw strategy candidates; folds 02–04 were not attempted due to early
  futility.
- The 64-cell V1 plan is retained but not authorized for execution
  (`PROHIBITED_DUE_TO_SAMPLE_SIZE_FUTILITY`).
- No profitability conclusion was reached; no demo or live trading is
  authorized.
- The fingerprint/canonical-byte engineering debt must be repaired before a
  V2 scientific freeze.
- Any future research candidate must use a new identity; when work eventually
  begins, the next research identity should be development-scoped rather than
  frozen (e.g. `phase6-development-v2`).
- Fold 01 is development evidence and is contaminated for future
  strategy-design purposes (`DEVELOPMENT_EVIDENCE —
  CONTAMINATED_FOR_FUTURE_STRATEGY_DESIGN`).
- The untouched holdout remains untouched and inaccessible.

V2 development has **not** begun.
