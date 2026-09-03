# Phase 4 Progress - Risk and Capital Protection

## Repository state

- Branch: `phase/4-risk-protection`
- Parent commit: `40521066e67c58b00c0b874a4bf9c260ad3113fa`
- Worktree: `C:\Users\chips\forex-signal-bot-phase4`
- Objective: establish one fail-closed account-level risk authority shared by
  live and historical adapters.
- Completion status: Phase 4 implementation and pre-commit verification are
  complete.
- Commit status: this record is part of the single local Phase 4 commit; its SHA
  is recorded in the final report because a commit cannot contain its own ID.

## Completed work

- Verified the exact Phase 3 parent and clean Phase 3 worktree.
- Recorded the original worktree's four modified and six untracked owner paths.
- Confirmed Phase 1 and Phase 2 worktrees are clean.
- Created and verified the isolated Phase 4 branch and worktree.
- Audited scorer, profiles, runtime capital, live/backtest sizing, drawdown,
  circuit outcomes and persistence paths.
- Implemented the shared policy, models, sizing authority, drawdown/circuit
  reducer, MT5 adapters and atomic versioned risk-state store.
- Added focused policy, sizing, drawdown, outcome, persistence and concurrency
  tests.
- Integrated fresh-equity approval and normalized outcome consumption into both
  live execution paths without adding import-time broker access.
- Integrated mark-to-market equity, aggregate stop exposure, shared sizing and
  the shared circuit into the shadow backtester.
- Disabled the legacy realized-only daily gate, score sizing authority and
  two-loss directional cascade in executable paths.
- Added deterministic live-mock/backtest risk replay and integration tests.

## Current files changed

- `.gitignore`
- `requirements.txt`
- `requirements-baseline-win-py310.txt`
- `bot/execution/confluence_scorer.py`
- `bot/execution/risk_engine.py`
- `bot/execution/risk/*.py`
- `bot/execution/lifecycle/entry.py`
- `bot/execution/lifecycle/__init__.py`
- `bot/state/orchestrator.py`
- `main.py`
- `backtests/shadow_mode_backtest.py`
- `backtests/risk_protection_replay.py`
- `docs/PHASE4_PROGRESS.md`
- `docs/PHASE4_RISK_PROTECTION.md`
- `tests/phase1/test_risk_state_runtime_baseline.py`
- `tests/known_defects/test_phase1_known_defects.py`
- `tests/phase4/*.py`

## Tests and failures

- Tests run: `pytest tests/phase4 -q` -> 74 passed.
- Tests run: full `pytest -q` -> 285 passed, 1 skipped, 4 expected failures,
  10 subtests passed.
- Phase suites: Phase 0 `27 passed, 1 skipped, 10 subtests`; Phase 1 `26
  passed`; Phase 2 `71 passed`; Phase 3 `82 passed`; Phase 4 `74 passed`.
- Known-defect inventory: 1 repaired regression passed and 4 strict later-phase
  xfails; no xpasses.
- Dependency installation/satisfaction, `pip check`, compilation, safe imports,
  JSON/YAML parsing, synthetic replay, diff check and secret scans pass.
- Current failures: none.

## Design decisions

- Internal percentages will use fractions only.
- All broker/account access will remain behind injected adapters.
- Missing, stale or corrupt safety state will reject new entries.
- Live uses `min(balance, equity)` as its conservative capital basis.
- The maintained `filelock` package provides Windows interprocess locking.
- Locked-profit stops may contribute zero open capital-at-risk; unknown positions
  without valid stops block entries.

## Incomplete functions

None within the Phase 4 implementation. Exact committed-snapshot verification
is the remaining release procedure, not an incomplete production function.

## Next exact task

After the local commit, create a temporary detached worktree at that SHA and run
the complete verification matrix. Record the SHA and exact results in the final
Phase 4 report; do not begin Phase 5.

## Last verified safe state

The pre-commit tree passes the complete verification matrix. The changed-tree
all-plugin secret scan and full-tree credential-pattern scan report zero new
findings; existing entropy-only hash/build artifacts are unchanged. Original and
earlier phase worktrees remain unchanged.
