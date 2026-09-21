# Phase 3 - Live/Backtest Execution Parity

Parent commit: `d15b386dcae810ee63ca572515a82abbb4d0ebe8`

## Execution audit

| Component | Live behavior at Phase 2 | Backtest behavior at Phase 2 | Difference | Phase 3 resolution | Deferred dependency |
| --- | --- | --- | --- | --- | --- |
| Signal identity | Candidate dictionary without a stable execution ID | Setup ID existed, but was not an execution identity | No common source-candle barrier or lifecycle key | Stable signal ID includes symbol, direction and source candle | Restart reconciliation remains Phase 4/5 |
| Signal time | Latest closed frame was read, then a current tick was evaluated | Decision used the completed M5 candle's availability | Live intent time was implicit | UTC `signal_available_at` and source open time are required | None |
| Entry readiness | Limit-style entries used current ask/bid plus ATR/point tolerance; other entries were immediately ready | Limit price had to lie inside the same decision candle; other entries filled at its close | Different event and fill rules; historical same-candle leakage | Shared `MARKET_ON_TRIGGER` readiness, with only later events eligible | Bid/ask history remains Phase 7 |
| Entry fill | Market order; actual broker fill retained | Exact limit or decision-candle close | Requested and simulated/actual fill semantics differed | Requested trigger and actual/simulated fill are separate fields | Slippage and full costs remain Phase 7 |
| Position model | Mutable dictionaries plus MT5 position objects | Local mutable `Position` dataclass | State and invariants differed | Shared typed position state and validated transitions | Startup broker reconciliation remains Phase 4/5 |
| Partial close | 50% at 1R, attempted from ticks | Not implemented | Quantity and realized P&L diverged | Shared one-shot partial rule and volume normalization | Risk/minimum-lot policy remains Phase 4 |
| Stop and target | Broker-side SL/TP; missing positions inferred from history | Bar OHLC with stop-first checks | Exit classification and gap handling differed | Shared ordered management reducer and normalized reasons | Tick reconstruction remains Phase 7 |
| Break-even/trailing | ATR-3x tick peak plus optional HTF structure trail | Multiple selectable formulas over bar extrema | Different formulas and event ordering | Shared monotonic ATR/structure stop policy; old stop is checked first | Tick/bar granularity remains Phase 7 |
| Kill switch | M15 structure check followed by market close | Similar local M15 calculation | Separate final-exit path and reason | Delivered to the shared reducer as an emergency event | Circuit consumption remains Phase 4 |
| P&L | Broker/account values and journal events | One full-position calculation at final exit | Partial components could not reconcile | Shared gross component ledger and normalized outcome | Commission, swap, spread and slippage remain Phase 7 |
| Idempotency | Boolean flags and broker position disappearance | Loop structure only | Replayed events could duplicate actions | Stable event/action IDs and processed-ID sets | Atomic persistence remains Phase 4 |
| Journaling | Open, management and close events used separate payload shapes | Result dictionaries used backtest-only fields | No common transition trace | Backward-compatible normalized lifecycle payload | Database migration is not required |

## Safety and scope

Phase 3 changes execution chronology and lifecycle parity only. It does not
change risk percentages, confluence, bias, symbol profiles, DXY arithmetic,
regime/order-block/news policy, broker filling mode or historical result files.
All historical fills remain gross and cost-neutral unless an existing explicit
backtest cost is supplied. Phase 3 results are not profitability evidence.

## 1. Shared lifecycle architecture

`bot.execution.lifecycle` is the pure execution domain. Strategy code creates an
`EntryIntent`; live ticks and historical bars become `MarketEvent` values; the
entry reducer creates a `PositionState`; and the management reducer emits typed
actions. `main.py` and `shadow_mode_backtest.py` are adapters and do not decide
partial, stop, target, break-even, trailing or gross P&L rules independently.

## 2. State transitions

The legal path is `CREATED -> WAITING/ELIGIBLE -> ENTRY_TRIGGERED -> OPEN ->
PARTIALLY_CLOSED -> CLOSED`. `CANCELLED`, `EXPIRED` and `REJECTED` are terminal.
Illegal transitions, non-positive risk/quantity, invalid directional levels,
backward event time and malformed prices raise `LifecycleError`.

## 3. Signal chronology

Every intent records its source candle open, UTC availability, stable source
event ID and sequence. Events before availability are rejected. The source bar
is permanently barred by identity/open time. A later bar may share the source
close timestamp only when it is a distinct event with a later sequence. No
adapter scans a pre-signal range retroactively.

## 4. MARKET_ON_TRIGGER semantics

This is the only active Phase 3 entry mode. `IMMEDIATE` becomes ready on the
first eligible event. A long `PULLBACK` becomes ready at or below trigger plus
tolerance; a short becomes ready at or above trigger minus tolerance. Missing,
non-finite or expired input cannot fill. Requested trigger and fill are distinct.

## 5. Historical fill policy

Only a later eligible bar is examined. If readiness is true at its open, the
simulated gross fill is that open. If readiness first becomes true intrabar, the
fill is the requested trigger. The fill kind records open versus intrabar trigger
and remains cost-neutral unless existing explicit backtest costs are supplied.

## 6. Live fill policy

Only a post-signal tick is eligible. Buy readiness uses ask and sell readiness
uses bid. Once ready, the adapter submits the existing market order and records
the returned broker fill separately. Tests inject a fake sender; the domain has
no MT5 import and cannot call an order API.

## 7. Expiry and invalidation

Expiry is evaluated before readiness and is inclusive at `expires_at`. Expired,
cancelled and rejected intents cannot reopen. Strategy-specific pre-entry
invalidation remains represented by terminal state but no new strategy rule was
invented in this phase.

## 8. Event ordering

The reducer validates the event, checks the stop already active before that
event, applies an explicit emergency exit, resolves target/partial observations,
applies at most one partial, then calculates a protective stop for the next
event. It emits at most one final close.

## 9. Conservative ambiguity policy

`STOP_FIRST` is the production and validation default. If one OHLC bar touches
both an existing stop and favorable target, the stop wins and the transition
records ambiguity metadata. If entry and exits share the first eligible bar,
the same adverse-valid ordering applies. Research may construct another policy
later, but no favorable policy is active.

## 10. Partial-close rules

The existing 1R target and configured fraction are shared. Quantity is rounded
down to the symbol step. A partial that is below minimum, equals a full close or
leaves a subminimum runner is skipped with a deterministic reason. A skipped or
executed partial is attempted once and never silently becomes a full close.

## 11. Break-even rules

Break-even is represented by a protective stop at the actual fill. It is applied
only after the current event's old stop and exit conditions are resolved and is
therefore active from the next event. A later hit is classified `BREAK_EVEN`.

## 12. Trailing-stop rules

Live and historical adapters use the same ATR multiple, minimum distance and
optional confirmed structure level. Favorable excursion is retained after a
partial. Buy stops only rise and sell stops only fall; proposals outside the
open stop/target interval are ignored. Each modification has a stable action ID.

## 13. Gross P&L accounting

Each close component records quantity, actual/simulated exit, gross P&L and
reason. Components sum to `realized_gross_pnl`; closed plus remaining quantity
equals initial quantity; final close leaves zero. Long P&L uses `(exit-fill)` and
short P&L reverses the sign. Requested entry is never substituted for fill.

## 14. Idempotency

Signals, trades, input events, transitions and actions have stable IDs. Processed
event/action IDs live in immutable state. Replaying a tick/bar cannot duplicate
an entry, partial, stop change, exit or P&L component. Event time cannot move
backward and closed positions emit no later action.

## 15. Live and backtest adapters

The live adapter translates pure actions to existing deal/SLTP requests and
reconciles confirmed execution prices. Both orchestrator and legacy analysis
paths pass through shared readiness and fill recording. The backtester uses the
Phase 2 causal timestamp, retains pending intents across bars and calls the same
management reducer. Retired backtest-only trailing modes now fail explicitly.

## 16. Remaining granularity differences

Live management observes broker ticks while historical management observes OHLC
bars. Shared formulas and conservative ordering are equal, but a bar cannot
reconstruct intrabar tick sequence. Full tick-path equivalence remains Phase 7.

## 17. Deferred transaction costs

The lifecycle ledger is gross before costs. Existing explicit shadow spread,
slippage and commission inputs remain outside the domain calculation. Complete
bid/ask history, commission, swap and execution-cost realism remain Phase 7.

## 18. Deferred broker protections

Risk caps, floating drawdown, normal lifecycle circuit consumption and atomic
risk state were repaired in Phase 4; see `docs/PHASE4_RISK_PROTECTION.md`. Filling
mode, invalid-stop retry, margin/spread protection, magic isolation and startup
broker reconciliation are completed in Phase 5. Risk-state persistence is complete;
broader runtime/journal atomicity remains deferred.

## 19. Known-defect transitions

`KD-BACKTEST-001` and `KD-EXIT-001` are repaired by passing Phase 3 regressions.
The latter includes shared partial, trailing and P&L tests. Strict xfails retained:
`KD-RISK-001` is repaired by Phase 4 regressions. Retained defects are
`KD-STOPS-001` (repaired by Phase 5), and `KD-REGIME-001`,
`KD-NEWS-001`, `KD-OB-001` (Phase 6). The Phase 4 document records the repaired
drawdown, circuit and risk-state persistence findings.

## 20. Testing and parity scenarios

The suite covers the twenty required live-mock/historical scenarios, symmetric
long/short management, volume edge cases, illegal transitions, serialization,
adapter translation, runtime integration and lifecycle invariants. Run the small
machine-readable replay with:

```powershell
python -m backtests.execution_parity_replay
```

The replay compares transitions and actions only. Phase 3 results are not
profitability evidence.
