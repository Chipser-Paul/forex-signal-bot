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

## 7. Correct evaluation plan (the only one authorized for future execution)

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

## 11. Current blocker: pre-run sample-size feasibility audit

Before any 64-cell run is authorized, a **sample-size feasibility audit** must
answer: does the frozen strategy produce enough eligible candidates on the
frozen data to yield at least 30 closed trades per fold (section 14)? The
audit counts candidates and rejection reasons only — it must not compute
profitability.

## 12. Why fold-1's zero-candidate observation requires investigation

A full-fold, real-strategy probe over all 13,269 fold-1 decisions measured
**zero candidates** (7,273 skip / 5,827 wait decisions, 169 news-blocked) and
therefore zero fills. Before the 64-cell run, this must be investigated
without changing strategy semantics: it may be legitimate market behavior for
the frozen window, but an unnoticed configuration/orchestration regression
would silently invalidate 64 cells of work. The investigation is a read-only
analysis task and must be completed and documented first.

## 13. Exact safe next task (no profitability computation)

1. Build and publish fold-03 and fold-04 feature stores (resumable build:
   already-published folds are skipped; run on an idle, cool machine,
   sequential I/O).
2. Then count eligible candidates and rejection reasons across all four
   folds using the published stores and the shared reducer (gate/reason
   accounting only).
3. Aggregate the counts into the feasibility verdict.

## 14. Acceptance requirement

The evaluation plan requires **at least 30 closed trades per fold**
(`docs/PHASE8M_DEVELOPMENT_EVALUATION_PLAN.md`, metrics line). This is why
feasibility must pass before the 64-cell run is authorized.

## 15. Empirical execution prohibition

**Do not execute any empirical evaluation until (a) the feasibility audit
passes, and (b) the owner issues a new explicit run authorization.** No
scenario, fold or fidelity reduction is permitted to force a pass. The
runner's verification chain refuses invalidated plans, unregistered packages
and legacy inputs.

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
