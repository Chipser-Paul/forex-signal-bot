# Phase 8N — Development Evaluation Preflight

Status: **BLOCKED BEFORE EMPIRICAL EXECUTION**. No strategy evaluation or
result bundle has been produced.

## Verified authorization and inputs

- Starting branch `phase/8-scientific-validation`, clean HEAD
  `63d6b7e7c41a6fd9a2276fafc77503d368e0881d`.
- Frozen package `evidence-development_evaluation_plan-v1-82ef6fcab5c13547`
  verifies at fingerprint
  `ae9b4e2a17562146f0ade44f758ca015f6ab9b017eaeaf665f7745278b131c79`.
- Frozen candidate `phase6-frozen-v1`, exact symbol `XAUUSDm`, UTC development
  interval `[2024-01-01, 2025-01-01)`.
- Phase 8M recorded verified 2024 ticks, M5/M15/H1/H4/D1/W1 candles,
  six-constituent causal DXY, official USD news, observed bid/ask spread,
  Phase 8H cost policy, Phase 8L metadata bounds, strategy/execution/risk/
  broker fingerprints, session rules, contamination register, and Phase 8A
  preregistration. The Phase 8N read-only status verifier was rerun; it made
  no acquisition or strategy call.
- Approximately 45.93 GiB free on C: at preflight; no development-evaluation
  result directory existed. No matching worker was running.

## Runner audit

| Component | Existing implementation | Phase 8N gap |
| --- | --- | --- |
| Causal market inputs | Phase 8C candle partitions and Phase 8D DXY package | No empirical strategy-to-execution orchestrator loads both at each `available_at` decision. |
| Strategy | Pure Phase 6 `StrategyInput`/`StrategyDecision` | No frozen adapter creates the full input from the empirical candles, DXY and news timeline. |
| Lifecycle | Phase 3 entry/management reducers | Not wired to the empirical candidate run. |
| Risk | Phase 4 authority and circuits | Not wired to fold/scenario accounts and outcome checkpoints. |
| Broker semantics | Phase 5 guarded live adapter | Historical counterparts must be mapped explicitly to Phase 7. |
| Execution/costs | Phase 7 bid/ask engine and ledger | No streaming 2024 runner or scenario-specific metadata construction. |
| Studies | Phase 8A synthetic replay | Synthetic-only; cannot be promoted to empirical execution. |
| Legacy shadow | `backtests/shadow_mode_backtest.py` | Bar/gross diagnostic path; it is not the Phase 7 cost-aware empirical engine. |

The frozen Phase 8M plan lists four swap, three slippage, and ten metadata
scenarios, with all required. It does **not** define whether partitions are
the Cartesian product (120 combinations × four folds), one-at-a-time stress
paths, or another exact composition. The Phase 8N authorization expressly
requires the plan's *exact* composition and forbids reinterpretation or
scenario reduction. Creating a matrix now would change the frozen protocol.

An empirical runner would also need a precise, frozen mapping from accepted
market data into the Phase 6 `StrategyInput` fields and from approved decisions
into Phase 3 entry intents. The Phase 8M plan freezes `StrategyConfig` and
fingerprints but does not contain that orchestration contract. The legacy
shadow path cannot supply it without changing candidate semantics.

## Fail-closed outcome

No empirical source was evaluated. No fold, scenario, trade, ledger,
performance metric, bootstrap, acceptance decision, or result package exists.
The development decision is `INSUFFICIENT` because the run cannot be started
without adding meaning to the immutable plan. Holdout, final validation, and
Phase 9 gates remain false. No Phase 8N commit was created.

Repository verification after this documentation checkpoint: 1,017 tests
passed, one opt-in test skipped, ten subtests passed, zero failures/xfails/
xpasses. Compilation, safe import, 38 JSON/YAML parses, `pip check`, diff
validation and changed-file secret scan passed. Detached committed-snapshot
verification is inapplicable because no Phase 8N commit or runner exists.

Next checkpoint: preregister an **append-only plan amendment** that explicitly
defines scenario composition and the frozen empirical strategy-input/intent
mapping. Review and hash it before a separately authorized execution. The
existing Phase 8M package and commit must remain unchanged.

Phase 8N-A follow-up: the authorized factorized matrix has been encoded and
tested, but amendment publication remains blocked by the unmapped production
bias/setup/entry fields. See `docs/PHASE8N_EVALUATION_PLAN_AMENDMENT.md`.

Phase 8N-B follow-up: bias and liquidity maps now accept injected causal
frames through the same production functions. Full decision/entry parity is
still blocked; see `docs/PHASE8N_EMPIRICAL_STRATEGY_ADAPTER.md`. No empirical
evaluation occurred.

Phase 8N-C follow-up: synthetic event-time, stop/target and retrospective-news
boundaries were added without reading empirical performance or running a
strategy evaluation. The 2024 official news schedule is permitted only for
development event-time veto replay; actual retrospective retrieval remains
disclosed. Supported setup-state/identity parity is still absent, so the
evaluation and holdout gates remain false. See
`docs/PHASE8N_CAUSAL_STRATEGY_ORCHESTRATION.md`.

Phase 8N-D: local checkpoint `a2b358542cfa2f68e6e1b3660e1df2b21a18ac4a`
was verified in a detached clean worktree. Stage 2 remains uncommitted, with
shared gates and synthetic live/offline decision/level/intent comparisons.
No empirical input, result, holdout or private evidence was accessed for those
tests. The consumption/restart acceptance gap is still open; no evaluation
command or superseding plan is authorized.
# Phase 8N-E no-execution boundary

Successor publication verified twice:
`evidence-development_evaluation_plan-v1-ba2745f96fda3939`,
fingerprint `d69bbed4542d9517dc46d043d12324f6a921a846bca39c30e57fdc3774779c72`.
The original parent is preserved unchanged; its supersession is recorded only
by this revision. Stage 2 is mechanically verified, not an empirical result.
No separately authorized run command exists: owner approval of the exact new
fingerprint and an approved streaming empirical runner are still required.

The earlier blocked-run records below remain historical. Shared setup
consumption/restart is now synthetic-test covered, but neither implementation
nor plan publication grants run authorization. No empirical market file,
holdout or profitability evaluation was executed in this operation. The
superseding plan requires a new explicit owner authorization and an approved
streaming runner for the exact published fingerprint. The diagnostic shadow
backtester is not a substitute for that runner.
# Phase 8N-F: prior successor invalidated before execution

The Phase 8N-E plan `evidence-development_evaluation_plan-v1-ba2745f96fda3939`
was published before a post-commit recovery-outcome defect was discovered.
It is INVALIDATED_BEFORE_EXECUTION through append-only disposition evidence,
not by rewriting its immutable package. Zero empirical cells ran.
The original Phase 8M plan remains immutable and superseded.

The correction separates persisted state change from actual setup
consumption. Rejected-entry cleanup must never count as consumption.
See the causal orchestration contract and new recovery regression suite.
The corrected successor retains frozen candidate, inputs, scenario assumptions,
four folds and 16 scenarios/64 cells, binds the recovery schema/code/regression
fingerprints and explicitly invalidates the faulty predecessor.

Publication is metadata only and grants no execution authorization.
An approved streaming empirical runner and new owner authorization for the
exact corrected fingerprint remain required. There is no valid empirical
next command yet; the diagnostic shadow backtester is not a substitute.
No empirical, holdout, final-validation or Phase 9 work is permitted.
Publication identities are recorded in PHASE8N_EVALUATION_PLAN_AMENDMENT.md.
Current successor: `evidence-development_evaluation_plan-v1-4a6ab94c3e303c81`,
fingerprint `adbab1bd1faf844107f2bb4f1727ea832282964c37129f9447b7a20025359a09`.
Faulty-plan disposition: `evidence-development_plan_disposition-v1-dac472a23118c880`.
Both predecessors' bytes were verified unchanged; publication repeated
idempotently. No empirical cells have executed.
