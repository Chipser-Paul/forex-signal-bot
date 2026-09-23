# Project Continuation Handoff — Phase 8 (2026-09-21)

This document equips a **new ordinary ChatGPT or coding agent with no access to
the current conversation** to resume the project safely. It is part of the
canonical continuation checkpoint `integration/phase8-checkpoint-20260921`.

> **Honest status:** Phase 8 is **in progress**. The scientific-validation
> infrastructure is built and verified through Phase 8N-K, but **no empirical
> evaluation has been executed**, feasibility has not passed, and the trading
> system is **not complete**. Do not claim otherwise.

---

## 1. Project purpose and scope

Build and scientifically validate a causal, cost-aware **XAUUSDm-only** SMC
trading system. Every evaluation runs on frozen historical data with strict
causality (no future data, no forward filling). All other symbols, live
trading and demo execution are out of scope for Phase 8.

## 2. Canonical repository, branch and commit

- Remote: `https://github.com/Chipser-Paul/forex-signal-bot.git`
- Canonical branch: `integration/phase8-checkpoint-20260921`
  (created 2026-09-21 from the sanitized snapshot)
- Sanitized root commit: `1c593f5e14597b6b25a8abe702457e71a10e545c`
  (parentless; tree `62e173d57c5bc624da16e6f21bbb655e11a532b7`)
- **V1 disposition (2026-09-21): `phase6-frozen-v1` is
  `REJECTED_FOR_SAMPLE_SIZE_FUTILITY` — the frozen candidate is not
  executable and the V1 64-cell plan is not authorized for execution. See
  `docs/PHASE8_FEASIBILITY_DISPOSITION_V1.md` and
  `baseline/feasibility_audit_v1_artifact_manifest.json`.**
- This checkpoint commit: see `git log -1` on the branch (message:
  `chore: publish sanitized Phase 8 continuation checkpoint`)
- Provenance manifest: `baseline/phase8_sanitized_snapshot_manifest.json`
  (canonical blob SHA-256 `a14a7205540924c67876d62a1dea7ab682557539c8632609efbc355d958a75e5`)
- The branch never descends from remote `main` or any credential-bearing
  historical branch. Owner dirty-state content is dispositioned in
  `baseline/owner_worktree_disposition_20260921.json`.

## 3. Python / venv setup and dependencies

- Python 3.10 on Windows; project venv historically at
  `C:/Users/chips/forex-signal-bot/.venv` (a fresh venv also works — see
  recovery instructions in section 20).
- Install:
  - `python -m venv .venv`
  - `.venv/Scripts/pip install -r requirements.txt`
  - `.venv/Scripts/pip install -r requirements-dev.txt`
  - (data-tooling extras, only if needed: `requirements-data.txt`;
    the win-py310 pin set: `requirements-baseline-win-py310.txt`)
- Verify: `.venv/Scripts/pip check`
- MetaTrader5 is a declared dependency (live-acquisition modules such as
  `bot/acquisition/`, `bot/data/market_data.py`, `bot/analysis/dxy_filter.py`
  import it), but the offline validation chain (orchestrator, gate reducer,
  strategy modules, validation adapters) is import-firewalled from it —
  enforced by `tests/phase8/test_gate_offline_imports.py` (a meta-path hook
  fails the import if MetaTrader5 is touched, and socket connections are
  forbidden). The validation work never requires MT5 or a terminal.

## 4. Phase 0–7 completion summary

| Phase | Purpose | Status | Evidence |
|---|---|---|---|
| 0 | Baseline harness, gate framework | complete | `docs/PHASE0_SECURITY.md`, owner `main` |
| 1 | Reproducible test baseline + CI | complete | `docs/PHASE1_BASELINE.md` |
| 2 | Causal market-data alignment | complete | `docs/PHASE2_CAUSAL_DATA.md` |
| 3 | Live/backtest execution parity | complete | `docs/PHASE3_EXECUTION_PARITY.md` |
| 4 | Account-level risk protection | complete | `docs/PHASE4_RISK_PROTECTION.md` |
| 5 | Broker safety + reconciliation | complete | `docs/PHASE5_BROKER_SAFETY.md` |
| 6 | Strategy semantics + market filters (frozen `phase6-frozen-v1`) | complete | `docs/PHASE6_STRATEGY_SEMANTICS.md` |
| 7 | Realistic cost-aware backtesting | complete | `docs/PHASE7_REALISTIC_BACKTESTING.md` |

Full lineage audit: `baseline/phase_lineage_20260921.json` (all phase tips
proven ancestors of the Phase 8 tip; zero production-path deletions).

## 5. Phase 8 status through 8N-K

Sub-phases 8A–8N-K are recorded in `docs/PHASE8_PROGRESS.md` and the
`docs/PHASE8*.md` documents. Key state:

- Frozen evaluation plan, scenario matrix (16 scenarios × 4 folds = 64 cells),
  streaming runner, causal strategy orchestration and empirical input pipeline
  are implemented and tested.
- 8N-J indexed replay: 4.15× structural acceleration, exact reference
  equivalence, deterministic interruption/resume.
- 8N-K causal market-feature memoization: `CausalMarketFeatureSnapshot`
  feature stores published atomically per fold; full-cell measured 18.4 min
  (vs 11.4 h baseline, 37×); 23.18 h single-worker / 13.35 h two-worker
  measured projection; two-worker determinism verified.
- **The 64-cell empirical evaluation has NOT been executed.** The current
  blocker is the pre-run sample-size feasibility audit (section 11).

## 6. Trusted dataset / evidence identities (no data embedded)

All frozen data lives **outside Git** under
`C:/Users/chips/forex-signal-bot-data/phase8/`:

| Location | Content |
|---|---|
| `exness-tick-history/` | frozen Exness tick year/month packages with manifest hashes |
| `evidence/` | immutable evidence packages (plan, candidate, cost policy, DXY, news, etc.) |
| `evidence/market-feature-store/` | fold feature stores: `fold-01-1d710826193a6767`, `fold-02-55c55daef9809b63` (published); folds 03/04 absent |
| `official-news/`, `dxy/`, `derived/`, `work/`, `samples/` | supporting frozen inputs |
| `engineering_benchmark_8nk/`, `benchmarks/`, `engineering/` | engineering benchmark artifacts (not strategy evidence) |

Every consumption path verifies package/partition manifest hashes before use.
Never place market data inside the repository.

## 7. Evaluation plan (retained historical preregistration — execution now prohibited)

> **Disposition (2026-09-21):** this plan is retained byte-for-byte as the
> historical V1 preregistration but its execution for `phase6-frozen-v1` is
> `PROHIBITED_DUE_TO_SAMPLE_SIZE_FUTILITY` (see section 11 and
> `docs/PHASE8_FEASIBILITY_DISPOSITION_V1.md`). It is listed here as the
> identity reference for the frozen artifacts only.

- Package: `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81`
- Fingerprint: `adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09`
- Candidate: `phase6-frozen-v1` (exact symbol `XAUUSDm`, UTC development window)
- Grid: **16 scenarios × 4 frozen folds = 64 cells**
- Runner-compatibility record:
  `evidence-runner_compatibility-v1-a81ef827217a69c6` (see section 9)

## 8. Invalidated plan identities that must never execute

- `evidence-development_evaluation_plan-v1-ba2745f96fda3939`
  (fingerprint `d69bbed4542d9517dc46d043d12324f6a921a846bca39c30e57fdc3774779c72`)
  — `INVALIDATED_BEFORE_EXECUTION` per
  `docs/PHASE8N_EVALUATION_PLAN_AMENDMENT.md`; the runner hard-rejects it.
- Any earlier plan package superseded by the append-only amendment chain
  (parent of the amendment: `evidence-development_evaluation_plan-v1-82ef6fcab5c13547`).
- Unregistered/unknown packages, wrong candidates, legacy result inputs —
  all refused by the streaming runner's verification chain.

## 9. Runner compatibility record

`evidence-runner_compatibility-v1-a81ef827217a69c6` — published append-only,
binding the runner checkpoint `92b2be1` to the plan above, preserving the
prior compatibility byte-for-byte and recording the invalidated identities.
Publishing mechanism: `probes/_publish_compat_8nk.py` in the Phase 8 worktree
calls `build_compatibility_record` from `bot/validation/runner_compatibility.py`.

## 10. Feature-store status and machine-health observations

- Built and published: fold-01 (`fold-01-1d710826193a6767`, 13,269 decision
  rows) and fold-02 (`fold-02-55c55daef9809b63`).
- Pending: **folds 03 and 04** (construction was suspended during the
  storage-anomaly window; see below).
- Measured machine observations (2026-09-21):
  - **Thermal:** the laptop decelerates ~3× under sustained load (simple loop
    2.49 s vs ~0.6–1.0 s healthy). Schedule heavy work in cool, idle-machine
    sessions; never stack CPU-heavy jobs.
  - **Storage:** two transient read-hash mismatches under heavy concurrent
    I/O were caught by the identity chain and re-read clean (frozen data
    intact; SMART healthy; no disk error events). One file-tool write was
    lost during the same window. Run pre-run full-manifest verification and
    keep heavy work sequential on this machine.
  - The identity chain caught every fault exactly as designed.

## 11. Current blocker: pre-run sample-size feasibility audit — **RESOLVED (V1 rejected)**

The sample-size feasibility audit was completed on 2026-09-21 from the
canonical checkpoint and concluded `FEASIBILITY INSUFFICIENT — NO RUN
AUTHORIZED`: fold-01 produced **zero raw strategy candidates** across all
13,269 scheduled decisions (7,273 skip + 5,827 wait + 169 news-blocked +
0 candidate_ready = 13,269, exactly reconciled), so
`closed trades <= 0 < 30` per fold and the preregistered minimum is
mathematically unreachable under the frozen candidate. Folds 02–04 were not
attempted due to early futility. `phase6-frozen-v1` is
`REJECTED_FOR_SAMPLE_SIZE_FUTILITY`; the V1 64-cell plan is retained but
`PROHIBITED_DUE_TO_SAMPLE_SIZE_FUTILITY`. Full evidence and interpretation:
`docs/PHASE8_FEASIBILITY_DISPOSITION_V1.md`. No profitability conclusion was
reached and none may be inferred from this result.

## 12. Why fold-1's zero-candidate observation requires investigation

The investigation is complete (2026-09-21, read-only, no semantics changed).
The zero-candidate outcome is classified **LEGITIMATE_FROZEN_STRATEGY_BEHAVIOR**:
the accounting reconciles exactly, the frozen gate funnel is internally
consistent, and among the 526 decisions that reached frozen confluence
scoring the best raw score was 7/8 against the frozen 8/8 threshold (522
scored 5/8; FVG/order-block overlap failed 526/526; valid order block failed
522/526). Full diagnostic detail:
`docs/PHASE8_FEASIBILITY_DISPOSITION_V1.md` §4. Fold-01 data is now
development-contaminated for future strategy design (see the
`phase8n_feasibility_audit_v1_fold01` record in
`baseline/phase8_contamination_register.json`) and must never be represented
as untouched validation or holdout evidence for a V2 candidate influenced by
this result.

## 13. Historical feasibility-audit task record (closed; no profitability computation)

The V1 feasibility audit has completed with a rejection, so the tasks below
are **closed**; they are retained as history.

1. ~~Build and publish fold-03 and fold-04 feature stores~~ — not attempted
   (early futility at fold-01; never built).
2. ~~Count eligible candidates and rejection reasons across all four
   folds~~ — fold-01 counted (zero candidates); folds 02–04 not attempted
   due to early futility.
3. ~~Aggregate the counts into the feasibility verdict~~ — verdict:
   `FEASIBILITY INSUFFICIENT — NO RUN AUTHORIZED` (sealed in
   `docs/PHASE8_FEASIBILITY_DISPOSITION_V1.md`).

Any future research must use a new candidate identity and should be
development-scoped rather than frozen (e.g. `phase6-development-v2`). V2
development has not begun. The former
`REPRODUCIBILITY_ENGINEERING_DEBT — MUST BE RESOLVED BEFORE V2 SCIENTIFIC
FREEZE` (newline-dependent fingerprint reproduction; see
`docs/PHASE8_FEASIBILITY_DISPOSITION_V1.md` §10) is now
`REPRODUCIBILITY_ENGINEERING_DEBT — RESOLVED FOR PROSPECTIVE SCIENTIFIC
FREEZES`: the versioned canonical-byte contract `canonical_git_blob_v1`
(`bot/scientific/canonical_bytes.py`,
`docs/PHASE8N_CANONICAL_BYTE_CONTRACT.md`) fingerprints committed Git
blobs and is checkout/newline-independent. Historical V1 identities are
unchanged and were not generated under the new contract; legacy
fingerprint semantics (`legacy_worktree_bytes_v0`) remain compatibility-only.
Prospective scientific freezes must explicitly declare an approved
prospective contract — legacy, missing and unknown/unapproved contracts
are rejected (`bot/scientific/prospective_freeze.py`). This resolution
does not by itself authorize a V2 scientific freeze; the V2 research charter is now approved and preregistered (sealing
record below). Holdout remains untouched; no
demo/live trading is authorized.

**V2 research charter sealing record.**

- Charter: `docs/PHASE8_V2_RESEARCH_CHARTER.md`, status
  `APPROVED / PREREGISTERED`; it is the governing preregistration for
  the V2 research cycle.
- Deterministic identity:
  `phase8-v2-research-charter-v1-8527e3a5eec98f53` (derived from the
  final charter SHA-256; the full hash is authoritative:
  `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`).
- Active research identity: `phase6-development-v2`;
  `phase6-frozen-v2` does not exist, and charter publication does not
  freeze a strategy.
- No strategy experiments have yet occurred. Research budgets are
  sealed: diagnostic investigations <= 12, strategy variants <= 8,
  numeric parameter trials <= 4; upward budget revision is prohibited
  after the first strategy-variant result (reduction only).
- Fold 01 is initially the sole permitted design evidence (already
  contaminated for V2 design); Folds 02-04 remain reserved and are
  released sequentially and fail-fast (Fold 02 -> Fold 03 -> Fold 04);
  holdout remains untouched.
- Next authorized task: the V2 semantic diagnostic stage on Fold 01
  only (read-only structural diagnostics under the charter's
  hypothesis register; no profitability metrics).
- No demo/live trading is authorized.

**V2 preregistration record (D001 stage).**

- Hypotheses `phase8-v2-H001` (OB/FVG exact-overlap may be stricter
  than the economic concept), `phase8-v2-H002` (valid-OB predicate
  may be conjunctively restrictive) and `phase8-v2-H003` (temporal
  association; later diagnostic) are registered in the append-only
  register `baseline/phase8_v2_hypothesis_register.json`, bound to the
  sealed charter identity and hash.
- Diagnostic `phase8-v2-D001` (Frozen OB/FVG Structural Attrition
  Decomposition) is preregistered in
  `docs/PHASE8_V2_DIAGNOSTIC_D001.md` with status
  `REGISTERED_NOT_EXECUTED`.
- Diagnostic budget remains `0 / 12 executed` (registration consumes
  nothing). No new Fold-01 observation occurred during
  preregistration.
- Next authorized task after publication: implement and execute D001
  exactly as preregistered (read-only tooling, Fold 01 only,
  structural metrics only, fail-closed stop conditions).
- Folds 02-04 remain reserved (sequential fail-fast release); holdout
  remains untouched. No strategy variant result has been observed,
  so the 8-variant/4-parameter budget lock has not yet been
  triggered.

**V2 D001 execution record (2026-09-23).**

- D001 was executed on Fold 01 using the frozen Phase-A tooling at
  commit `1f2f997c1763f7a6e50f7d02e35d88bcdd568ebf` (tooling tests
  32/32 plus 25/25 canonical-machinery regression tests passed before
  any data access; the remote resolved to the tooling commit at the
  hard barrier).
- Diagnostic budget is now `1 / 12 executed`; strategy variants
  remain `0 / 8 observed` and numeric parameter trials `0 / 4` —
  the budget result-lock has still not triggered.
- Result record `phase8-v2-D001-R001` is appended to
  `baseline/phase8_v2_hypothesis_register.json`; raw structured
  output lives outside Git under
  `evidence/v2_diagnostics/phase8-v2-D001-R001/` (SHA-256
  `af03bfbe688b010deb70261eabe2240336e16bbff07d519ea20a8ccbc3b99c10`,
  read-back verified). Compact report:
  `docs/PHASE8_V2_DIAGNOSTIC_D001_RESULT.md`.
- H001 `SUPPORTED_BY_D001`; H002 `SUPPORTED_BY_D001`; H003
  `NOT_TESTED_BY_D001`. Key structural facts: FVG present in 0 of
  7,316 reducer decisions; the exact-overlap condition was never
  evaluable (0/526); valid-OB failures concentrate in mitigation
  (307/526), premium/discount placement (79), invalidation (75) and
  displacement (61). The run exactly reproduces the known V1
  diagnostic evidence (13,269 scheduled; 5,827 wait; 7,273 skip).
- No strategy variant was selected; no profitability conclusion is
  drawn; D001 by itself supports no rule change.
- Next step requires supervisory review before D002 preregistration
  or Variant 1 authorization. Folds 02-04 remain reserved; holdout
  untouched.

## 14. Acceptance requirement

The evaluation plan requires **at least 30 closed trades per fold**
(`docs/PHASE8M_DEVELOPMENT_EVALUATION_PLAN.md`, metrics line). This is why
feasibility must pass before the 64-cell run is authorized.

## 15. Empirical execution prohibition

**The V1 64-cell plan `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81`
for `phase6-frozen-v1` is `PROHIBITED_DUE_TO_SAMPLE_SIZE_FUTILITY` and is not
authorized for execution.** The separately invalidated plan
(`evidence-development_evaluation_plan-v1-ba2745f96fda3939`) remains
`INVALIDATED_BEFORE_EXECUTION`; the two statuses are distinct and must not be
conflated. No demo or live trading is authorized. Any future evaluation would
require a new candidate identity, a passing feasibility audit for that
candidate, and a new explicit owner run authorization. No scenario, fold or
fidelity reduction is permitted to force a pass. Note: because the V1 plan
binds the contamination register as of its freeze, the 2026-09-21 register
append legitimately makes that plan's input-firewall re-verification report
readiness drift — the frozen fail-closed design working as intended for a
plan that is no longer authorized.

## 16. Phase 9 prerequisites

Phase 9 (deployment control, per `docs/PHASE7_REALISTIC_BACKTESTING.md`:
"Phase 8 performs scientific validation; Phase 9 controls deployment") may
only start after Phase 8 completes: feasibility passed, the 64-cell empirical
evaluation executed under authorization, acceptance gates evaluated, and the
empirical/holdout/final-validation gates recorded.

## 17. Demo execution

Deferred until **both** Phase 8 and Phase 9 are complete. No MT5 access,
demo or live execution belongs to the validation phase.

## 18. Owner-worktree disposition summary

Read-only audit of the owner folder's dirty state (4 modified + 6 untracked):
1 × KEEP_AND_MIGRATE (`utils/setup_logger.py` timestamp parameter),
6 × SUPERSEDED, 1 × PRIVATE_LOCAL_ONLY (`mt5_data_diagnostic.py` — the
validation firewall forbids MT5 imports), 2 × REQUIRES_OWNER_DECISION
(`bot/execution/risk_engine.py` property alias, `htf_bias_diagnostic.py`).
Details: `baseline/owner_worktree_disposition_20260921.json` and
`docs/OWNER_WORKTREE_REVIEW_20260921.md`. Nothing is migrated automatically;
the owner folder must be preserved until every disposition is approved by the
owner (folder-consolidation procedure in the 2026-09-21 consolidation report).

## 19. External market data must remain outside Git

Never commit tick data, candles, caches, feature stores, broker exports,
news archives, account statements or benchmark artifacts. The 48 legacy
market-cache pickles were excluded from the sanitized snapshot precisely for
this reason (`TRACKED_MARKET_CACHE_EXTERNAL_DATA`); the hygiene pass also
removed 100 Explorer `desktop.ini` files and 48 legacy shadow-mode output
files, with narrow `.gitignore` rules preventing recurrence.

## 20. Recovery instructions from a fresh clone

```bash
git clone --branch integration/phase8-checkpoint-20260921 \
  https://github.com/Chipser-Paul/forex-signal-bot.git phase8-canonical
cd phase8-canonical
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt
.venv/Scripts/pip check
.venv/Scripts/python -m compileall -q bot strategies runtime utils tests
.venv/Scripts/python -m pytest tests/phase8n_k tests/phase8n_j -q
```

The frozen datasets under `C:/Users/chips/forex-signal-bot-data/phase8/` are
machine-local and are **not** in Git; a fresh clone is sufficient for the test
suite (all tests run synthetic/offline), but empirical work additionally
requires those datasets with their manifest hashes intact.

## 21. Commands for compilation and tests

- Compilation: `.venv/Scripts/python -m compileall -q bot strategies runtime utils tests`
- Focused new-phase tests: `.venv/Scripts/python -m pytest tests/phase8n_k tests/phase8n_j -q`
- Broader 8N suites: `.venv/Scripts/python -m pytest tests/phase8n_g tests/phase8n_i -q`
  (8N-G includes a full 129-cell reference rehearsal test that takes 30–60+
  minutes on a cool machine — run it alone, e.g.
  `.venv/Scripts/python -m pytest "tests/phase8n_g/test_development_evaluation_runner.py::test_verify_results_detects_cell_disagreement" -q`)
- Full suite (fast, excludes the heavy rehearsal):
  `.venv/Scripts/python -m pytest -q --deselect "tests/phase8n_g/test_development_evaluation_runner.py::test_verify_results_detects_cell_disagreement"`
- The validation suites run fully offline; the import firewall keeps the validation chain free of MetaTrader5 even though the package is installed for live-acquisition modules.

## 22. Resume prompt for the feasibility audit

Copy-paste for a fresh agent session:

> Phase 8 feasibility audit (engineering only, no profitability). Work in the
> canonical clone of `integration/phase8-checkpoint-20260921`
> (https://github.com/Chipser-Paul/forex-signal-bot.git). Plan
> `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81`
> (fingerprint `adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09`),
> candidate `phase6-frozen-v1`. (1) Read
> `docs/PROJECT_CONTINUATION_HANDOFF.md` and follow it exactly. (2) Build and
> publish fold-03 and fold-04 causal market-feature stores (resumable; folds
> 01/02 already published) on an idle machine, sequential I/O, then verify
> their manifests. (3) Using the published stores and the shared pure gate
> reducer, count eligible candidates and rejection reasons per fold across
> all four folds — counts and reasons only, no PnL, no expectancy, no
> profitability. (4) Also investigate the fold-01 zero-candidate observation
> (read-only; confirm whether zero candidates on fold-1 data is legitimate
> frozen-market behavior rather than a regression) and document the finding.
> (5) Report per-fold candidate counts vs the at-least-30-closed-trades-per-fold
> acceptance requirement and end with exactly one verdict:
> FEASIBILITY PASSED — RUN AUTHORIZATION REQUEST READY, or
> FEASIBILITY INSUFFICIENT — NO RUN AUTHORIZED. Do not execute any empirical
> evaluation, do not modify strategy semantics, do not reduce scenarios or
> folds, and do not run anything on a heated machine or with stacked workloads.

## Update — 2026-09-23: D001 qualified; H004 registered; D002 preregistered (governance-only, no empirical read)

- **D001:** `EXECUTED_WITH_INTERPRETATION_QUALIFICATIONS` via append-only register record `phase8-v2-D001-Q001`. R001 immutable; original classifications preserved. Supervisory dispositions: **H001 → `INCONCLUSIVE_D001`** (upstream FVG-availability bottleneck identified; overlap strictness not testable with zero OB/FVG pairs), **H002 → `INCONCLUSIVE_D001`** (reducer `ob_result` acquisition decomposition, not the preregistered canonical `evaluate_order_block` lifecycle; observed counts retained as descriptive evidence only), **H003 → `NOT_TESTED_BY_D001`** (unchanged).
- **H004 registered (OPEN):** Canonical FVG Attrition Bottleneck — the D001 zero-FVG result should be attributable to one or more specific FVG-generation/retention stages (causal history → ATR validity → displacement threshold → geometric gap → direction filter → fill filter), not to the total absence of three-candle imbalance structure.
- **D002 preregistered (`REGISTERED_NOT_EXECUTED`):** Canonical FVG Attrition Decomposition; specification `docs/PHASE8_V2_DIAGNOSTIC_D002.md` (SHA-256 `ad271d85d4af95724c6f7081529c1bdb0017e21bdd034b88ce683ead1bddf2ea`); Fold 01 only `[2024-04-01T00:00:00Z, 2024-06-08T00:00:00Z)`; preregistered stages A–G; Stage G must reconcile exactly with the D001 observation (final canonical FVG presence = 0; mismatch is a stop condition); unique-FVG identity rule defined before execution; no threshold search, no candidate counterfactuals. H002 remains open (a potential later D003 on `evaluate_order_block`; D003 not registered).
- **Budget:** diagnostics `1 / 12` executed (D001; not refunded); D002 execution will consume `2 / 12`; strategy variants `0 / 8`; numeric parameter trials `0 / 4`; variant-budget result lock untriggered.
- **No new empirical read occurred** in this task. Folds 02–04 reserved and untouched; holdout untouched. D002 execution requires a separate authorization task with the D001 two-phase discipline (Phase A synthetic-only tooling committed and pushed before any Fold-01 access; Phase B only after the remote resolves to the frozen tooling commit).


## Update — 2026-09-23: S001 static FVG defect; D002 blocked; V001 preregistered (governance-only, no empirical read)

- **Static defect (authoritative source fact, `phase8-v2-S001`):** `utils/indicators.py::calculate_atr(df, period)` returns a **scalar** (`0.0` for invalid/insufficient input, otherwise `float(atr_series.iloc[-1])`). The frozen detector `bot/analysis/fvg_engine.py::detect_fvgs` computes `atr_series = atr if hasattr(atr, "iloc") else None` and skips every iteration when it is `None`. A scalar float has no `.iloc`, so `atr_series` is always `None`: **the frozen `detect_fvgs()` implementation cannot produce an FVG for any input through this path.** Classification: `STATIC_SOURCE_PROOF — NOT EMPIRICAL MARKET EVIDENCE` (deterministic implementation/interface defect; not an empirical Fold-01 inference). Proof bound to source commit `3d2cfd2496663118a4ffcacad4c7c1fe7b5bf814`, blobs `5324ae9e…` (indicators), `ceec93a7…` (fvg_engine), `4ffa993f…` (regime).
- **D002:** `BLOCKED_BEFORE_EXECUTION — DETERMINISTIC_FVG_ATR_INTERFACE_DEFECT`. Stage-B attrition is deterministically zero under the defect; execution would consume a diagnostic without informing Stages C–G. Execution count zero; no budget consumed; no result record; no raw output; specification retained unchanged with an append-only disposition section. Diagnostic budget remains `1 / 12 executed`.
- **H004:** `SUPPORTED_BY_STATIC_IMPLEMENTATION_AUDIT` (narrow meaning — pipeline causation of the canonical zero only). The D001 zero-FVG observation cannot be interpreted as absence of three-candle imbalance structure in Fold 01; nothing is established about real FVG counts, the 1.5× ATR rule, direction, fill status, OB overlap, candidate creation or profitability.
- **H005 registered (OPEN):** `FVG ATR-Series Interface Repair`. **V001 registered (`REGISTERED_NOT_IMPLEMENTED`):** `phase6-development-v2-V001` `Canonical FVG ATR-Series Compatibility Repair`; specification `docs/PHASE8_V2_VARIANT_V001.md` (SHA-256 `0b1d5ec57c68746f7c346c4b576220460d0dad54d218a2add34dbe6e2adbf8fb`).
- **V001 change boundary:** repair is local to the FVG detector path (preferred: reuse canonical `bot.strategy.regime.atr_series(frame, period)` or a proven mathematically equivalent local adapter). `utils.indicators.calculate_atr` remains unchanged globally (scalar public behavior preserved — other callers depend on it). Preserved: `atr_period=14`, `displacement_mult=1.5`, bullish/bearish geometric gap definitions, fill-status semantics, same-direction filtering, source-index semantics, timeframe semantics. No changes to Gate 8, Gate 9 displacement threshold, OB semantics, confluence score, overlap tolerance, `8/8`, session/news rules, DXY logic, risk, execution or broker safeguards. One-concept rule: no bundling.
- **V001 implementation barrier (future task, not yet authorized):** implement within boundary → synthetic/unit tests → ATR-series equivalence proof (`float(atr_series(frame, period).iloc[-1]) == calculate_atr(frame, period)` within explicit tolerance on multiple valid deterministic frames) → scalar-helper-unchanged proof → bullish/bearish FVG fixtures → filled-zone filtering identical → direction filtering identical → no other strategy source changed → commit and push → verify remote. Only then may Fold 01 be read.
- **V001 empirical surface (preregistered):** structural counts only (detector-eligible decisions, ATR-valid windows, displacement passes, bullish/bearish geometric FVG counts, same/opposite-direction counts, filled/unfilled counts, final canonical FVG presence/count, unique FVG identities where deterministically defined, Gate-11 reach/pass/fail, OB/FVG co-existing pairs, canonical overlap true/false, raw `candidate_ready`, existing gate/rejection reasons) plus descriptive statistics (ATR, body, body/ATR, FVG width, canonical overlap separation where a canonical pair exists). No performance metrics; no multiplier/period/overlap/threshold alternatives; no `7/8`; no H003 temporals.
- **Interpretation rule:** possible outcomes `FUNCTIONAL_REPAIR_WITH_ADEQUATE_DENSITY`, `FUNCTIONAL_REPAIR_WITH_INSUFFICIENT_DENSITY`, `FUNCTIONAL_REPAIR_NO_CANDIDATES`, `IMPLEMENTATION_REPAIR_FAILED`, `EMPIRICAL_EXECUTION_BLOCKED`. A functioning FVG detector is not automatically a good strategy; V001 must not be selected merely for producing more candidates.
- **Budget:** diagnostics `1 / 12 executed` (D001); strategy variants observed `0 / 8` (first empirical V001 result consumes `1 / 8` and from that point `UPWARD STRATEGY-VARIANT / PARAMETER-TRIAL BUDGET REVISION PROHIBITED`); numeric parameter trials `0 / 4` (V001 changes no numeric parameter). Variant-budget result lock **not yet triggered**. No new empirical data read in this task; Folds 02–04 reserved and untouched; holdout untouched. H002 remains OPEN (potential later D003 on `evaluate_order_block`; D003 not registered).
