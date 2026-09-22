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
