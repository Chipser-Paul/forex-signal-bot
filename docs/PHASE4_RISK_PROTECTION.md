# Phase 4 - Risk and Capital Protection

Parent commit: `40521066e67c58b00c0b874a4bf9c260ad3113fa`

## Risk audit

| Setting/calculation | Phase 3 source | Live behavior | Backtest behavior | Bypass/failure | Phase 4 resolution | Deferred dependency |
| --- | --- | --- | --- | --- | --- | --- |
| Per-trade risk | Confluence `risk_pct`, profile, caller | A+/B requested 2%/1.5% | Same score-derived value | `max_risk_per_trade` was not enforced | Central 0.35% policy; requests above 0.50% reject | None |
| Capital basis | Dashboard/session `CAPITAL` | `CAPITAL + realized profit` | Starting capital plus realized P&L | Floating loss and account equity absent | Fresh snapshot and conservative `min(balance,equity)` | None |
| Monetary loss | Tick value/size | Direct MT5 metadata | Same approximate formula | No broker calculation or post-check | Injected broker calculation preferred; validated fallback | Costs remain Phase 7 |
| Volume | `round(raw/step)` and forced minimum | Could round up or oversize minimum | Same | Monetary budget could be exceeded | Decimal floor, minimum rejection, loss recalculation | Margin checks remain Phase 5 |
| Aggregate risk | Pair count only | No account-wide stop exposure | Pair count only | Multiple positions could exceed capital envelope | Sum stop loss; unbounded positions block; 1% cap | Gap risk remains Phase 7 |
| Drawdown | Realized daily deals | 3% realized-only gate | Realized simulation P&L | Floating, weekly and total loss absent | Equity/high-water daily 2%, weekly 4%, total 8% | Safe liquidation Phase 5 |
| Loss streak | In-memory `StrategyState` | Directional two-loss timer | Backtest-only outcome calls | Live outcomes absent; restart reset | Shared three-loss persistent circuit and final-outcome hook | None |
| Outcome idempotency | No durable outcome IDs | Journal only | Local state update | Replay could duplicate counters | Persisted stable outcome IDs | Atomic journal coordination remains separate |
| Risk persistence | None | Restart created fresh state | New state each run | Drawdown protection reset | Versioned atomic store, backup, lock, strict recovery | Account reconciliation Phase 5 |
| Runtime JSON | Direct overwrite | `open_trades.json` non-atomic | Result writes at end | Risk state could truncate/reset | Risk state alone is atomic in Phase 4 | Broader persistence remains later |

## 1. Policy version

`phase4-validation-v1` is the only executable policy in this phase. Risk
configuration is validated before account access and all live/backtest decisions
carry the policy version and a stable decision ID.

## 2. Percentage units

The domain stores fractions. `0.0035` is 0.35% and `0.0050` is 0.50%.
Environment names ending in `_PCT` use human percentages, so
`RISK_PER_TRADE_PCT=0.35` converts to `0.0035`. A value of `35` converts to
`0.35`, fails policy validation, and blocks the entry. There is no magnitude
guessing.

## 3. Validation defaults

| Control | Canonical value |
| --- | ---: |
| Base risk per trade | `0.0035` |
| Absolute per-trade ceiling | `0.0050` |
| Aggregate open-risk ceiling | `0.0100` |
| Daily equity drawdown | `0.0200` |
| Weekly equity drawdown | `0.0400` |
| Total validation drawdown | `0.0800` |
| Consecutive losing trades | `3` |
| Strategy ideas per symbol | `1` |
| Snapshot freshness | `60` seconds |
| Automatic increase/martingale | disabled/prohibited |

## 4. Hard ceiling

The central authority rejects, rather than clamps, requested risk above 0.50%.
Confluence grade, displacement tier, symbol profile, dashboard capital, backtest
arguments and `.env` cannot increase the ceiling. Grades remain available as
strategy metadata only. The compatibility `RiskEngine` also rejects a constructor
ceiling above `0.005` and rejects oversized callers.

## 5. Equity basis

Live snapshots are obtained at decision time through the injected MT5 adapter.
The account identity is checked against the Phase 0 child contract when present.
Sizing uses `min(balance, equity)`, which is at least as conservative as equity
when floating losses have reduced it. Missing, stale, non-finite or non-positive
account data fails closed. Dashboard/session capital is display and backtest
configuration only.

## 6. Monetary loss calculation

The preferred live calculation calls injected `order_calc_profit` for one lot
from proposed executable entry to stop. The fallback uses the symbol's validated
tick size and tick value. Buy stops must be below entry; sell stops must be above
entry. The normalized volume is priced again through the same method before
approval. Broker calculation failure returns `LOSS_CALCULATION_FAILED`.

## 7. Volume normalization

Volume uses decimal-safe floor arithmetic from zero and is bounded by the broker
maximum. It never exceeds raw volume. Steps such as `0.01`, `0.1`, and `0.25`,
including binary floating-point edge values, are covered by regressions. The
post-normalization loss must remain inside the monetary budget.

## 8. Minimum-volume rejection

If raw volume is below the broker minimum, or flooring cannot produce a valid
minimum/step quantity, the trade is rejected. The authority never promotes a
small request to minimum lot and never converts an invalid partial quantity into
a full position.

## 9. Aggregate open risk

Each open item contributes its remaining stop loss in account currency. Strategy,
manual and unknown broker positions are included; opposite positions are not
treated as perfect hedges. A missing/invalid stop is unbounded exposure and blocks
new entries. A locked-profit stop can contribute zero capital-at-risk, while gap
risk remains explicitly unmodelled. Projected risk may equal, but not exceed,
1.00% of the conservative equity basis. One existing same-symbol idea blocks a
second.

## 10. Drawdown definitions

Drawdown uses current equity, so floating P&L is included immediately at the
adapter's observation granularity. Daily and weekly checks use both starting
equity and the period high-water mark. Total checks use validation starting
equity and overall high-water equity. A threshold is breached at equality.

## 11. Period boundaries

Daily periods are UTC calendar days. Weekly periods begin Monday 00:00 UTC.
A daily pause remains sticky inside its day and may clear only on a valid new
day. A weekly pause remains sticky inside its week and may clear only on a valid
new week. Neither reset clears a total hard stop.

## 12. Circuit states

The states are `ACTIVE`, `DAILY_PAUSED`, `WEEKLY_PAUSED`,
`LOSS_STREAK_PAUSED`, `HARD_STOPPED`, `DATA_UNSAFE`, and `STATE_CORRUPT`.
Fresh valid observations may recover `DATA_UNSAFE`; valid period boundaries may
reset their matching pauses. `HARD_STOPPED` is durable and has no automatic
transition back to active.

The executable gate order is: policy, account identity, fresh snapshot, state
integrity, circuit, drawdown, loss streak, symbol idea limit, aggregate risk,
stop validation, raw sizing, downward normalization, normalized-loss check,
final approval, then Phase 3 entry eligibility.

## 13. Loss streak

Only a normalized final Phase 3 trade outcome changes the streak. Three completed
losses pause entries. Break-even preserves the existing count, a winner resets
it, and partial closes do not count as completed trades. The legacy two-loss
directional cascade is disabled in executable live/backtest paths.

## 14. Outcome idempotency

Final outcomes use stable IDs derived from trade identity and final exit time.
Processed IDs are persisted. Replaying a journal outcome, including after a
restart, does not change realized strategy P&L or the streak twice.

## 15. Persistence format

Risk state is deterministic, versioned JSON containing a hashed account
reference, policy version, period IDs, high-water marks, circuit state, completed
outcome IDs and trustworthy timestamps. It contains no login, password, token or
other credential. A `filelock` lock coordinates processes on Windows. Writes use
a temporary file in the same directory, flush, `fsync`, and `os.replace`; the
latest validated state is also written to a last-known-good backup.

## 16. Recovery behavior

First initialization is explicit through `RISK_STATE_INITIALIZE=1`, requires a
fresh account snapshot, and is refused when any tracked or broker position exists.
An empty store without that request is uninitialized and blocks entries. A corrupt
primary recovers from a valid backup. A missing primary after initialization, two
corrupt copies, schema mismatch, account mismatch, or policy mismatch fails closed
and requires controlled recovery. No path silently creates a new high-water mark.

## 17. Live integration

Both supported orchestrator and legacy analysis paths call the shared authority
after stop construction and before Phase 3 eligibility. The approved downward-
normalized volume is the only lot passed to execution. Broker/account calls do
not occur at import. Normal lifecycle final outcomes are consumed by the same
persistent circuit and produce sanitized diagnostics.

## 18. Backtest integration

The shadow backtester initializes the same policy from simulated starting equity,
marks open positions to each completed bar close, computes remaining stop risk,
uses the same decision engine and consumes the same final outcome model. Score
grades do not size positions. Completed-bar mark-to-market is deterministic but
is not tick-path reconstruction.

## 19. Reason codes

Key approvals/rejections are `APPROVED`, `INVALID_POLICY`,
`ACCOUNT_IDENTITY_MISMATCH`, `POLICY_IDENTITY_MISMATCH`,
`ACCOUNT_DATA_MISSING`, `ACCOUNT_DATA_STALE`, `INVALID_EQUITY`,
`RISK_STATE_UNINITIALIZED`, `RISK_STATE_CORRUPT`,
`DAILY_DRAWDOWN_LIMIT`, `WEEKLY_DRAWDOWN_LIMIT`,
`TOTAL_DRAWDOWN_LIMIT`, `LOSS_STREAK_LIMIT`, `INVALID_RISK_FRACTION`,
`RISK_ABOVE_HARD_CEILING`, `SYMBOL_IDEA_LIMIT`, `UNBOUNDED_OPEN_RISK`,
`AGGREGATE_RISK_LIMIT`, `INVALID_STOP`, `INVALID_SYMBOL_SPEC`,
`LOSS_CALCULATION_FAILED`, `MINIMUM_VOLUME_EXCEEDS_RISK`,
`VOLUME_NORMALIZATION_FAILED`, and `POST_NORMALIZATION_RISK_EXCEEDED`.

## 20. Remaining limitations

Phase 5 completes margin/order checks, spread-entry protection, filling modes,
invalid-stop retry, magic-number ownership, startup broker reconciliation and
ownership-safe liquidation; see `PHASE5_BROKER_SAFETY.md`. Phase 6 owns DXY arithmetic, regime/ATR, order-block
and news policy. Phase 7 owns slippage, complete spread/commission/swap treatment,
gap risk, tick reconstruction and performance validation. Other runtime JSON
stores are not represented as risk state and remain non-atomic where previously
documented.

## 21. Manual re-arm

There is deliberately no automatic hard-stop re-arm operation. A future
controlled operation must verify account identity, reconcile broker positions,
preserve audit history and explicitly authorize a new validation baseline. Phase
4 only blocks new entries and emits state; it does not claim to liquidate open or
unknown positions.

## 22. Profitability warning

These controls constrain capital exposure and make risk decisions reproducible.
They do not validate the strategy, backtest assumptions, expected return, or
profitability. Phase 4 results are not profitability evidence.
