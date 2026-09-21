# Phase 5 Broker Execution Safety

Parent commit: `242d2532479842b44b1fe83a87603f72400c7318`

Phase 5 secures the live mutation boundary. It does not change Phase 3 strategy
or lifecycle policy, Phase 4 risk limits, historical cost assumptions, or stored
results.

## 1. Execution policy

`bot.execution.broker.ExecutionPolicy` is the single live broker policy. Typed
requests retain Phase 3 signal/trade/action identities, the Phase 4 risk decision,
requested and executable prices, approved and requested volumes, stop/target
prices, expiry, magic, filling mode, and a sanitized broker comment.

## 2. Required live configuration

Live execution requires all of the following:

- `BOT_MAGIC_NUMBER`: stable non-zero integer selected and retained by the owner.
- `BOT_MAX_SPREAD_POINTS_XAUUSDM`: observed broker-specific XAU spread ceiling.
- `BOT_MAX_DEVIATION_POINTS_XAUUSDM`: observed broker-specific XAU deviation.

Phase 6 locks production execution to `XAUUSDm`; BTC execution settings are not
mandatory production configuration.

The repository deliberately supplies empty placeholders, not invented production
values. The owner should collect representative broker ticks under intended
sessions and volatility conditions, choose conservative operational limits, and
change them only through a reviewed policy update. Missing or invalid values stop
startup or reject execution.

## 3. Tick freshness

The default maximum age is 10 seconds with a one-second future-clock tolerance.
MT5 seconds/milliseconds are interpreted explicitly as UTC. Missing timestamps,
stale/future ticks, non-finite or non-positive bid/ask, and crossed markets fail
closed. A fresh tick is obtained again after preflight and before submission.

## 4. Spread gates

Spread is `ask - bid` and points are calculated with validated symbol `point`.
Both the required per-symbol absolute limit and the 10% spread-to-stop limit must
pass. The final pre-send observation is checked again; widening cannot bypass the
gate.

## 5. Symbol and trade-mode checks

The terminal must report connected and trade-enabled, and the account must permit
trading. The symbol must exist, be visible or become visible through a successful
selection, expose valid point/digits/volume/stop/freeze metadata, and permit the
requested long, short, or close operation. Disabled, close-only, and directional
modes are enforced.

## 6. Margin safeguards

Entries use the Phase 4-approved volume and broker `order_calc_margin`; leverage
is never guessed. Required margin must be finite and non-negative. Projected free
margin must remain positive, projected margin level must be at least 500%, and a
single new order may require at most 10% of current equity. Price or volume change
causes margin recalculation.

## 7. Filling-mode selection

Filling mode is derived from MT5 symbol capability flags and execution mode. The
documented preference is FOK, then IOC, then RETURN. RETURN is unavailable for
market-execution symbols. No mode is assumed and there is no silent IOC fallback.
The chosen mode is retained in the normalized execution result.

## 8. Stop and target price semantics

Stop/target distances and absolute prices are separate concepts. Broker requests
accept only direction-valid, finite, digit-normalized absolute prices. Entries
enforce broker stop distance; modifications also enforce freeze distance. Buy
stops/targets surround entry below/above; sell levels use the reverse ordering.

## 9. Invalid-stop retry

`KD-STOPS-001` is repaired. A definite invalid-stop rejection obtains fresh
symbol/tick metadata, derives direction-aware absolute levels, and returns to an
injected Phase 4 risk recheck. Volume can remain equal or decrease, never increase.
The retry repeats spread, stop, margin, filling and `order_check` validation. A
below-minimum resized volume is rejected. Only one retry is allowed.

## 10. Order-check requirements

Every supported entry, close, partial close, stop modification, and liquidation
request passes `order_check`. A missing/ambiguous check, rejected retcode, or a
check proposing increased volume blocks `order_send`. If final executable price
changes, Phase 4 reapproval and a second complete check are required.

## 11. Retcode classification

Broker results are classified as success, partial success, retryable price
rejection, permanent rejection, invalid request, invalid stops, trading
unavailable, insufficient margin, connection failure, or uncertain. Every result
has a stable reason code; unknown retcodes are permanent rejection rather than
implicitly retryable.

## 12. Retry policy

One automatic retry is permitted only for definite invalid-stop or price/requote
rejections. It uses the same action root and a distinct deterministic attempt ID.
Fresh validation and risk reapproval are mandatory. Market closed, insufficient
margin, invalid request, permanent rejection, and uncertainty do not retry.

## 13. Uncertain-result handling

The registry is persisted as `SUBMITTING` before `order_send`. A timeout,
exception, connection result, missing response, or incomplete apparent fill moves
the action to `UNCERTAIN`. It cannot be submitted again until broker orders,
positions, and deals establish confirmation or absence.

## 14. Magic-number ownership

Ownership requires matching non-zero magic, symbol, ticket, and stored trade
identity where available. Comments use the bounded form
`p5:<trade-id-8>:<action-id-8>`. Same-symbol manual and foreign-EA positions count
toward Phase 4 exposure but are never adopted, modified, closed, or liquidated.

## 15. Idempotency registry

The registry stores `PREPARED`, `CHECKED`, `SUBMITTING`, `CONFIRMED`,
`PARTIALLY_FILLED`, `REJECTED`, `UNCERTAIN`, and
`RECONCILIATION_REQUIRED`. It uses versioned deterministic JSON, a Windows-safe
file lock, same-directory temporary write, flush/`fsync`, atomic replacement, and
a latest-state backup. Confirmed actions cannot resend; uncertain actions require
reconciliation. No credentials or account snapshots are stored.

## 16. Partial fills

Requested and executed quantities remain distinct. Partial broker volume updates
the Phase 3 position and P&L component using actual quantity; unfilled volume is
restored to remaining exposure. The default policy does not retry the remainder.
Duplicate broker reports cannot produce another action submission.

## 17. Close and modify rules

Every management action resolves the exact broker ticket and proves ownership.
Close quantity cannot exceed broker remaining volume and is normalized downward.
Stop changes must improve protection, obey stop/freeze levels, and cannot widen
approved risk without Phase 4 re-evaluation. Successful broker price and volume,
not requested values, reconcile the lifecycle.

## 18. Startup reconciliation

The startup gate compares local lifecycle state, execution registry, broker
positions/orders, and recent deals:

| State | Resolution |
| --- | --- |
| Local and broker match | resume management |
| Broker-only owned with adequate history | reconstruct entry/volume/SL/TP as `RECOVERED`; partial history remains unknown |
| Broker-only owned without adequate history | block startup for review |
| Local-only with proven close deal | journal and consume one idempotent risk outcome |
| Local-only without close evidence | block startup |
| Uncertain action found at broker | confirm registry |
| Uncertain action with no conclusive evidence | retain reconciliation requirement; do not resend |
| Manual/foreign position | leave untouched; exposure remains conservative |
| Matching magic but ambiguous identity | fail closed and alert without account detail |

Repeated reconciliation is deterministic and action/outcome IDs prevent duplicate
effects.

## 19. Ownership-safe liquidation

Phase 4 risk breaches block new entries independently. Liquidation requests are
created only for positions with proven strategy magic and Phase 5 identity. Each
has a stable action ID and follows fresh tick, spread, filling, preflight,
submission, result, and reconciliation rules. Unknown/manual/foreign positions
are skipped; the system never claims they were closed.

## 20. Live-only versus shared protections

MT5 connection, tick age, spread, symbol modes, margin, filling flags,
`order_check`, magic ownership, retcodes, and broker reconciliation are live-only
adapter concerns. Stable action IDs, no volume increase, absolute stop semantics,
idempotency, actual partial-fill accounting, and no stop loosening are shared
invariants. The historical engine remains broker-independent and Phase 3/4 tests
remain authoritative for lifecycle/risk parity.

## 21. Remaining Phase 6 and 7 limitations

Phase 6 repairs DXY arithmetic/weights, ATR regime behavior, order-block
mitigation, news fail-closed policy, and any strategy interpretation redesign.
Phase 7 retains historical spread/slippage, commission, swap, gap/tick-path
reconstruction, transaction-cost parity, and performance validation.

## 22. Profitability warning

Broker safety prevents known unsafe mutations and makes fake-broker execution
deterministic. It does not establish strategy quality, expected return, or
profitability. Phase 5 results are not profitability evidence.

## Execution audit matrix

| File/function | Action | Previous validation/ownership/retry | Phase 5 resolution |
| --- | --- | --- | --- |
| `trade_executor.execute_trade` | entry | tick plus positive levels; fixed magic/IOC; blind stop retry | secured adapter only; legacy call fails closed |
| `main.close_position_immediately` | emergency close | ticket only; fixed magic/deviation; direct send | ownership, fresh snapshot, preflight, registry and classified result |
| `main.monitor_trades` | partial/final close and SL | Phase 3 action ID only; direct callback to MT5 | exact ownership and secured request per lifecycle action |
| `trade_manager.close_position` | legacy close | direct fixed-magic send | mutation disabled |
| `trade_executor.save_open_trades` | local state | adopted tickets by approximate entry price | no broker adoption; deterministic atomic write |
| `main` startup | recovery | missing-position deal lookup during monitoring | mandatory ownership-aware startup reconciliation |
| `bot.execution.risk.adapters` | account/exposure reads | read-only injected MT5 | unchanged; still feeds Phase 4 aggregate exposure |
| `frontend.utils.mt5_connector` | status/history reads | read-only | unchanged; no mutation authority |
| `backtests.shadow_mode_backtest` | historical simulation | no order send | remains isolated from Phase 5 broker policy |

The only production `order_send` call is inside `SecureBrokerExecutor` after the
recorded preflight and `SUBMITTING` transition.
