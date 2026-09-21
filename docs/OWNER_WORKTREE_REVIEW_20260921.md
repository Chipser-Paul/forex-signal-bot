# Owner Worktree Review — 2026-09-21

**Scope:** read-only audit of the dirty state in the original owner worktree
`C:/Users/chips/forex-signal-bot` (branch `main`, HEAD `55f7dd3`).
Machine-readable companion: `baseline/owner_worktree_disposition_20260921.json`.

**Nothing was modified, copied, staged, deleted, renamed, stashed or overwritten.**
No secret value was read or printed; scans were count-only pattern matches.
Nothing is migrated by this checkpoint — dispositions are proposals for a
separately authorized follow-up.

## Dirty state (4 modified + 6 untracked = 10 paths)

| # | Path | Status | Category | Disposition | One-line rationale |
|---|------|--------|----------|-------------|--------------------|
| 1 | backtests/shadow_mode_backtest.py | modified (tracked) | legacy shadow backtest harness | SUPERSEDED | Owner variant experiments on the pre-phase-split harness; the Phase 8 frozen evaluation pipeline replaces this workflow. |
| 2 | bot/execution/risk_engine.py | modified (tracked) | production risk module | REQUIRES_OWNER_DECISION | Additive read-only `max_trades` property alias (no behavior change) touching a production module outside any authorized phase scope. |
| 3 | bot/state/orchestrator.py | modified (tracked) | production orchestrator | SUPERSEDED | Behavior-preserving move of an `atr_val` computation; canonical evolved code computes the identical value. |
| 4 | utils/setup_logger.py | modified (tracked) | evaluation logging utility | KEEP_AND_MIGRATE | Optional `timestamp` parameter for deterministic event time — small, additive, aligned with Phase 8 determinism; migration needs separate authorization. |
| 5 | backtests/_trade_period_summary.py | untracked | one-off analysis script | SUPERSEDED | Hard-codes a Phase-0-era shadow CSV path that no longer exists; one-off July 2026 helper. |
| 6 | backtests/diagnostic_compare.py | untracked | one-off diagnostic | SUPERSEDED | Legacy-window (Apr–Jul) comparison of runs on the old engine. |
| 7 | backtests/diagnostic_report.md | untracked | historical report | SUPERSEDED | Dated 2026-07-30 against pre-phase-split commit `6af59c7`; simulated shadow results only, no account data. |
| 8 | backtests/strategy_state_audit.md | untracked | historical audit | SUPERSEDED | Its questions were resolved by verified Phase 8 checkpoint/resume guarantees. |
| 9 | htf_bias_diagnostic.py | untracked | diagnostic tool | REQUIRES_OWNER_DECISION | Potentially useful, but targets the old module layout and sits at repo root; compatibility unverified. |
| 10 | mt5_data_diagnostic.py | untracked | live MT5 diagnostic | PRIVATE_LOCAL_ONLY | Direct MetaTrader5 tool belongs on the broker machine; the validation tree's tested no-MT5/no-network firewall forbids it. |

## Verification evidence

- SHA-256 and byte sizes recorded for every path in the JSON companion.
- Secret-pattern scan (`password|passwd|secret|api[_-]?key|token|BEGIN ... PRIVATE KEY|session_key|.env`, case-insensitive): **0 hits in all 10 files**.
- Tracked-file diffs were read against the owner HEAD; untracked files were header-inspected only.
- For `utils/setup_logger.py`, the owner HEAD blob equals the canonical-tree blob — only the local modification differs.

## Recommended follow-up (requires separate authorization)

1. Migrate the `setup_logger` timestamp parameter (item 4) as a small maintenance commit on the canonical branch, with a regression test.
2. Owner decides items 2 and 9; the rest stay in the owner folder until the folder-consolidation step.

## Disposition vocabulary

KEEP_AND_MIGRATE / ALREADY_INTEGRATED / SUPERSEDED / GENERATED_OR_CACHE /
PRIVATE_LOCAL_ONLY / REQUIRES_OWNER_DECISION — as defined in the task brief;
uncertain cases were deliberately classified REQUIRES_OWNER_DECISION.
