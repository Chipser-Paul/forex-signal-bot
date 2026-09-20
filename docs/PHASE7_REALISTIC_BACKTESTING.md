# Phase 7 Realistic, Cost-Aware Historical Execution

Parent commit: `3c8a9ae39f6c98571f95f2a6657dcf138b4bf272`

Phase 7 defines execution and accounting mechanics. It does not select strategy
parameters and it does not provide evidence that the strategy has an edge.

## 1. Backtesting Audit

| Path | Previous behavior | Fidelity or accounting risk | Phase 7 disposition |
| --- | --- | --- | --- |
| `backtests/shadow_mode_backtest.py:main` | Connected to MT5, read caches or broker bars, then ran the shadow loop | No offline quote/metadata contract | Retained as a legacy diagnostic entry point; `--diagnostic` acknowledgement is required |
| `_fetch_range` | Pickle cache with MT5 fallback | Cache has no bid/ask or complete provenance | Existing artifacts remain read-only and non-validated |
| `run_backtest` | Neutral OHLC bars and one aggregate round-trip cost | Quote side, rollover, per-fill costs and intrabar path absent | Explicit `DIAGNOSTIC — NOT VALIDATED` and fidelity label added |
| `CostModel.round_trip` | Spread once, slippage twice, commission once after final close | Partial-close timing and financing were not represented | Clearly identified as the legacy approximation; new engine uses fill-level ledgers |
| `_backtest_account_snapshot` | Marked every position against one neutral close | Did not use executable bid/ask | New engine marks long positions at bid and short positions at ask |
| Phase 3 entry lifecycle | Causal source-candle barrier and deterministic market-on-trigger | Gross neutral price unless adapter supplies actual fill | Phase 7 adapter supplies the costed executable fill and actual volume |
| Phase 3 management | Stop-first ambiguity, partial and trailing chronology | Historical event needs the correct closing quote side | Quote and bid/ask bar adapters preserve the lifecycle ordering |
| Phase 4 risk authority | Equity, floating drawdown, exposure and circuits | Historical account needs executable marks and costs | New account snapshot contains bid/ask floating P/L, margin and cost-adjusted balance |
| Phase 5 policy | Spread, deviation and projected margin safeguards | Historically representable checks were missing | Absolute/relative spread, deviation and projected margin checks are enforced |
| Legacy output | Three files could be overwritten | No immutable manifest or cost provenance | Legacy overwrite is rejected; Phase 7 emits a unique nine-file result bundle |
| Existing result directories | 16 XAUUSDm result sets | Missing full costs, intrabar path and reproducible manifests | `INSUFFICIENT_FOR_VALIDATION`; preserved unchanged |
| Existing cache | 44 tracked pickle files | Bar-side/provenance and cost metadata incomplete | `INSUFFICIENT_FOR_VALIDATION`; preserved unchanged |

No previous result was used to choose a spread, slippage, commission, swap or
metadata value.

## 2. Strategy Freeze

The Phase 6 strategy is frozen. Phase 7 does not change bias, confluence, ATR,
regime, order blocks, DXY, news, sessions, entries, stops, targets, partial-close
fractions, trailing rules, or Phase 4 limits. The legacy `min_rr` override now
fails because it is a parameter-selection surface, not an execution input.

## 3. Fidelity Classification

Every run has exactly one `FidelityClass`:

| Class | Contract | Validation status |
| --- | --- | --- |
| `TICK_BID_ASK` | Sequenced historical UTC bid/ask quotes | Eligible only with complete observed metadata and costs |
| `BAR_BID_ASK` | Separate causal bid and ask OHLC bars | Eligible with conservative bar ambiguity and complete metadata |
| `MID_BAR_WITH_OBSERVED_COSTS` | Mid/bid bars plus timestamp-aligned observed broker costs | Lower precision, potentially eligible when provenance is complete |
| `MID_BAR_WITH_ASSUMED_COSTS` | Bars plus explicit hypothetical costs | Diagnostic only |
| `INSUFFICIENT_FOR_VALIDATION` | Missing cost, metadata, timestamp or provenance facts | Diagnostic only |

`RunMode.VALIDATION` rejects assumed/missing slippage and non-eligible fidelity.
The engine additionally requires observed commission and swap provenance.
Validation output from a dirty Git tree is rejected. Diagnostic output always
uses the prominent label `DIAGNOSTIC — NOT VALIDATED`.

## 4. Quote and Bar Contracts

`HistoricalQuote` contains exact `XAUUSDm`, UTC timestamp, positive finite bid
and ask, provenance, dataset identity, stable sequence identity, optional side
volumes and market flags. Crossed quotes are rejected. Quotes sort by timestamp
and sequence. An identical timestamp and sequence is rejected; multiple quotes
at one timestamp require distinct sequence identities.

`BidAskBar` keeps separate bid and ask OHLC values, `open_time`, causal
`available_at`, provenance and identity. It is not represented as a tick. Each
side must be valid OHLC and no corresponding quote side may cross.

Input objects are immutable. Normalization does not forward-fill quotes.
Expected-interval diagnostics distinguish ordinary Friday-to-weekend closures
from otherwise unexplained gaps. `iter_normalized_quote_chunks` supports bounded
streaming and rejects overlapping or backward chunks.

For `MID_BAR_WITH_OBSERVED_COSTS`, `SpreadObservation` values are joined
backward at each bar's availability time with an explicit maximum staleness.
Future, missing and stale spread observations reject the conversion. The
resulting bid/ask bar records the identities of both source datasets. Observed
spread reports include count, minimum, median, mean, p95 and maximum in both
price and metadata-derived point units.

## 5. Broker Metadata

`BrokerSymbolMetadata` is an offline, dated, versioned contract for exactly
`XAUUSDm`. It includes digits, point, tick size/value, contract size, volume
limits/step, currencies, margin rate, commission, swap, rollover zone, triple
swap weekday and provenance. `BrokerMetadataCatalog` permits non-overlapping
dated segments and requires one unambiguous segment at an event timestamp.

The JSON shape is published in
`config/historical_broker_metadata.schema.json`. It intentionally contains no
broker values. The owner must supply values and provenance offline. The current
implementation fails closed when profit-currency or commission-currency
conversion would be required because no causal conversion-rate contract exists.

## 6. Bid/Ask Execution

| Action | Long | Short |
| --- | --- | --- |
| Market entry | Buy at ask | Sell at bid |
| Mark to market | Bid | Ask |
| Market/stop close | Sell at bid | Buy at ask |
| Partial close | Sell at bid | Buy at ask |
| Take-profit limit | Closing-side target, with no favorable gap improvement | Closing-side target, with no favorable gap improvement |

Technical trigger, executable quote and final simulated fill are separate
fields. Spread is embodied in bid/ask fills and is never debited again. The
ledger records spread attribution relative to quote mid only for audit.

## 7. Spread and Slippage

Observed bid/ask spread varies by timestamp. It is stored as both price and
metadata-derived points. The Phase 5 absolute per-symbol limit and 10 percent
spread-to-stop limit both apply. A widened spread can reject an action.

Slippage is a typed boundary: none, fixed adverse points, or bounded uniform
adverse points. Buys move upward and sells move downward. Uniform values derive
from SHA-256 of run seed and stable action identity, so scheduling and evaluation
order cannot alter results. Expected quote, slippage and fill are stored
separately. Assumed slippage can run only as diagnostic evidence.

## 8. Gap and Bar Ambiguity

A Phase 3 signal cannot fill from its source event. A later quote that has
already crossed a market trigger fills at the first executable side, not at the
old trigger. A gapped stop fills at the first executable closing side plus any
adverse slippage. A take-profit limit receives the target, never an unjustified
better price.

For bid/ask bars, an existing stop is tested before target and favorable
management. If both are present, `AMBIGUOUS_BAR_STOP_FIRST` is emitted. The
engine does not invent a tick path. Phase 3 stop modifications remain effective
for the next event.

## 9. Commission

Supported schedules are per-lot per-side, per-lot round-turn, fixed per order,
and percentage of notional. Round-turn values are divided across entry and exit
fills, including unequal partial exits, so they are not double charged. Each
commission is a separate ledger debit. A non-account commission currency fails
closed until causal conversion support exists.

## 10. Swap

Long and short swap rates are separate. Supported units are account currency per
lot and points per lot. Broker-local rollover uses a named IANA timezone, which
handles daylight-saving changes. The configured local weekday receives the
triple multiplier. Swap applies to volume still open at each rollover, so a
prior partial close reduces later financing. Every swap is a separate ledger
entry with a stable id and duplicate suppression.

## 11. Lifecycle and Partial Fills

The adapter calls the Phase 3 entry reducer, then records Phase 7's actual fill
price and actual filled volume back into `PositionState`. Management remains in
the Phase 3 reducer. Its close actions are executed on the correct quote side and
reconciled through `ActionConfirmation`. Stop changes retain absolute-price and
never-loosen guarantees.

Partial fills occur only when an explicit available volume is supplied. No
random partial liquidity is invented. Later partial-close quantities use actual
open volume. Stable action ids prevent duplicate fill, volume, cost and P/L.

## 12. Account, Risk, and Margin

The account tracks balance, gross realized P/L, commission, swap, executable
unrealized P/L, equity, used margin, free margin and high water. Position size is
still approved by Phase 4 before execution. Phase 7 exposes `AccountSnapshot`
and `OpenRiskItem` values to the unchanged risk authority.

Margin uses dated metadata. New-order margin must be no more than 10 percent of
equity, projected free margin must remain positive, and projected margin level
must be at least 500 percent. Floating quote-side loss affects equity and can
activate the Phase 4 daily, weekly or total circuit immediately. Risk outcomes
remain idempotent through the Phase 4 authority.

## 13. Ledger

The append-only ledger records run, trade, position and action ids; UTC time;
event type; side; volume; reference, quote and fill prices; gross P/L; spread and
slippage attribution; commission; swap; net cash; and post-event balance/equity.

CFD notional is not debited from cash. Entry commission, closing gross P/L,
closing commission and rollover swap are distinct cash events. The invariant is:

`final balance = initial balance + sum(net_cash_change)`

Gross P/L, commission and swap totals are reconciled independently. Differences
above `1e-8` fail. Raw values remain available for audit; presentation code may
round to account-currency digits.

## 14. Result Bundle

Each run id creates a new directory and refuses overwrite. Files are written via
same-directory temporary files, flush, `fsync` and `os.replace`:

- `run_manifest.json`
- `configuration.json`
- `dataset_manifest.json`
- `fills.jsonl`
- `ledger.jsonl`
- `trades.jsonl`
- `equity.csv`
- `rejections.jsonl`
- `summary.json`

The manifest includes Git state, strategy version, safe configuration hash,
dataset hashes/provenance, fidelity, cost-source classes, seed, period, capital,
symbol, timeframes, model version and run mode. Generated Phase 7 result folders
are ignored. Identical immutable inputs produce identical normalized bundle
hashes.

Summary metrics are mechanical accounting outputs only. Gross, commission, swap
and net values are separate. Division by zero yields `null`, not an invented
ratio. Every summary sets `profitability_evidence` to false.

## 15. Legacy Evidence

`baseline/phase7_legacy_inventory.json` references the immutable Phase 1 hash
inventory and records 16 result sets and 44 cached pickles. They are not
rewritten. They remain
`INSUFFICIENT_FOR_VALIDATION` because bid/ask provenance, slippage, commission,
swap, intrabar path and complete immutable manifests are missing.

Old and Phase 7 outputs can differ because Phase 7 uses executable quote sides,
per-fill costs, rollover financing, gap prices, actual partial volume, floating
equity and Phase 4/5 gates. That difference is not evidence for or against the
strategy.

## 16. Replay and Performance

`backtests/realistic_execution_replay.py` contains 23 deterministic synthetic
scenarios for quote sides, spread, slippage, gaps, targets, partials, trailing
chronology, commission, swap, drawdown, aggregate risk, partial fills,
idempotency, ambiguity, metadata failure, diagnostic labeling, reconciliation
and repeatability. It makes no MT5 or network call and calculates no strategy
performance conclusion.

The performance sanity function sorted 100,000 reverse-ordered synthetic quotes
in approximately 0.184 seconds on this local verification run. This is a local
observation only. Large real datasets should be fed through bounded normalized
chunks.

## 17. Safety and Limitations

- Only exact `XAUUSDm` can enter the historical execution engine.
- No production broker metadata has been committed or inferred.
- No historical broker dataset was downloaded.
- Bar fidelity cannot establish an observed intrabar path.
- Assumed costs are diagnostic only.
- Currency conversion is not yet supported without a causal conversion series.
- True exchange queue position and partial liquidity require appropriate data.
- The legacy shadow runner remains lower fidelity even with non-zero assumptions.
- Phase 8 requires owner-supplied historical bid/ask data and dated metadata.
- Phase 8 performs scientific validation; Phase 9 controls deployment.

Phase 8A's acceptance, preregistration and holdout controls are defined in
`docs/PHASE8_SCIENTIFIC_VALIDATION.md`; they preserve this execution model.

Phase 7 engine verification is not profitability evidence and is not a live
trading recommendation.
