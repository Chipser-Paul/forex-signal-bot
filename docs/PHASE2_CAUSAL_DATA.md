# Phase 2 Causal Market-Data Contract

## 1. Scope and provenance

- Parent commit: `ef52f54b1c33fab45e83410d937eef11f3495cbc`
- Branch: `phase/2-causal-data`
- Platform verified: Windows, CPython 3.10.9, 64-bit
- Contract implementation: `bot/data/candles.py`
- Live adapter: `bot/data/market_data.py`

Phase 2 changes data visibility and alignment only. It does not change the DXY
formula or weights, entry/fill modeling, strategy thresholds, risk, exits, costs,
broker execution, or stored backtest results. No result in this repository is
profitability evidence.

## 2. Market-data audit

| File / function | Input meaning | Output meaning / zone | Prior alignment and risk | Phase 2 action |
| --- | --- | --- | --- | --- |
| `bot/data/market_data.py:fetch_ohlcv` | MT5 Unix `time` is candle open | Canonical UTC rows | `start_pos=1` avoided the active bar, but availability was implicit | Preserved offset; normalize and filter by `available_at` |
| `utils/fetch.py` | Alias of live fetch | Same as live fetch | Inherited live ambiguity | Inherits canonical adapter |
| `bot/analysis/bias_engine.py` | Live W1/D1/H4/H1/M15 frames | Completed canonical frames | Relied on fetch contract | No policy change; receives explicit closed rows |
| `bot/analysis/liquidity_map.py` | Live H1/M15/D1/W1 frames | Strategy structures/levels | Relied on fetch contract | No policy change; receives UTC rows |
| `bot/state/orchestrator.py` | Live fetched frames | Gate inputs | Relied on implicit closure | No gate changes; canonical live boundary applies |
| `main.py`, `trade_executor.py`, `trade_manager.py` | Live fetched frames | Signal/display/management inputs | Used positional row access after fetch | No strategy changes; canonical live boundary applies |
| `utils/__init__.py:load_price_data` | Offline CSV Unix timestamps | Historical canonical frame | Produced naive local-time values and dropped invalid rows | Uses strict UTC normalizer; uncertain final row is excluded |
| `backtests/shadow_mode_backtest.py:_fetch_range` | MT5 range or cached pickle | Historical canonical frame | Separate permissive converter, silent sort/dedup, uncertain final row | Shared strict normalization; duplicates/invalid data reject |
| `run_backtest` entry timeline | Entry candle opening index | Decision at entry candle availability | Treated full M5 row as visible at its opening timestamp | Decisions use M5 `available_at` |
| `run_backtest` HTF lookup | M5 opening timestamps | W1/D1/H4/H1/M15 views | Opening-time `get_indexer(..., method='ffill')` plus `pos + 1` exposed unfinished HTF OHLC | Vectorized availability `searchsorted`; exclusive causal slices |
| `_synthetic_dxy_context` | Historical H1 constituent frames | Synthetic index array | Filtered by open index then paired arrays by tail length | Shared availability snapshots and timestamp joins |
| `bot/analysis/dxy_filter.py:get_synthetic_dxy` | Live H1 constituent frames | Synthetic index array | Paired unequal arrays by tail length | Shared bounded backward availability join |
| `_dxy_cache_key` | Historical DXY frames and decision | Stable cache key | Opening-time `ffill` lookup | Latest causally available timestamp |
| `backtests/causal_replay.py` | Synthetic M5/H1/H4/D1 and cross-symbol rows | JSON diagnostics | Not previously present | Reproducible replay and selector benchmark |

The committed setup/trade analysis scripts read result or journal records rather
than candle series. The six diagnostic files in the dirty owner worktree were not
read or modified and are outside this branch.

## 3. Canonical candle schema

Every non-empty normalized frame has these deterministic columns:

`open_time`, `available_at`, `time`, `open`, `high`, `low`, `close`,
`tick_volume`, `spread`, `real_volume`, `timeframe`.

`time` is a compatibility alias of `open_time`. `open_time` is also the ordered
DataFrame index. Optional MT5 volume/spread fields are retained as numeric values
or missing values; OHLC fields are mandatory.

## 4. Timestamp and availability semantics

- All canonical timestamps are timezone-aware UTC.
- Numeric MT5 timestamps are interpreted explicitly as Unix seconds in UTC.
- Naive values and naive decision timestamps are rejected, not localized by
  machine settings.
- MT5 `time` means candle opening time, never close time.
- A row is visible exactly when `available_at <= decision_timestamp`; equality is
  inclusive. One microsecond before that boundary is not visible.
- For every historical row except the final row, `available_at` is the next
  observed candle opening. Only the next timestamp is used, never future OHLC.
- This next-observed-open rule intentionally treats session/weekend gaps
  conservatively.

## 5. Final-candle policy

An uncertain final historical or offline row is excluded. A caller may retain it
only by explicitly asserting that it is complete, optionally with an explicit UTC
availability boundary. When completion is explicit but no boundary is supplied,
the validated timeframe duration supplies the nominal boundary.

Live `start_pos=1` retrieval is explicit completion context. Even then, the result
is filtered against one captured decision timestamp, so an unexpectedly returned
active row whose nominal close is later than the decision is excluded.

## 6. Timeframe metadata

| Name | MT5 attribute | Nominal duration | Pandas representation | Rank |
| --- | --- | ---: | --- | ---: |
| M1 | `TIMEFRAME_M1` | 1 minute | `1min` | 1 |
| M5 | `TIMEFRAME_M5` | 5 minutes | `5min` | 2 |
| M15 | `TIMEFRAME_M15` | 15 minutes | `15min` | 3 |
| M30 | `TIMEFRAME_M30` | 30 minutes | `30min` | 4 |
| H1 | `TIMEFRAME_H1` | 1 hour | `1h` | 5 |
| H4 | `TIMEFRAME_H4` | 4 hours | `4h` | 6 |
| D1 | `TIMEFRAME_D1` | 1 day | `1D` | 7 |
| W1 | `TIMEFRAME_W1` | 7 days | `1W-MON` | 8 |

Rank is deterministic ordering metadata, not a conversion rule. Next observed
open is preferred over nominal duration because daily and weekly market sessions
are not continuous.

## 7. Validation and data-quality policy

Normalization copies caller data, sorts stably by opening time, and rejects
duplicate opens. It rejects missing OHLC fields, non-numeric or non-finite prices,
negative tick/real volume, and invalid high/low relationships. Materially invalid
OHLC is never repaired. Missing candles are not synthesized, forward-filled, or
backfilled. Empty input returns an empty frame with the canonical schema.

Unsupported timeframe names fail with a sanitized `CandleDataError`. Historical
cache validation errors are propagated rather than silently replaced by a live
download.

## 8. Causal snapshots and historical HTF views

`causal_snapshot` performs an inclusive `searchsorted` over sorted
`available_at`. It returns an ordered copy, optionally limited to the newest N
bars, and asserts that no returned row is from the future. The shadow backtester
precomputes exclusive causal end positions for every M5 decision using vectorized
`numpy.searchsorted`, then slices W1/D1/H4/H1/M15 frames by those positions.

At `12:05 UTC`, the M5 candle opened at `12:00` is available, the H1 candle opened
at `12:00` is not, and the H1 candle opened at `11:00` is the latest visible H1.
At `13:00 UTC`, the H1 candle opened at `12:00` becomes visible. The equivalent H4
boundary is `16:00`; a D1 candle opened at midnight becomes visible at the next
observed daily opening. Empty required HTF views produce a deterministic
`insufficient_completed_htf_history:<timeframes>` reason.

## 9. Cross-symbol alignment and staleness

Constituent observations are keyed by `available_at`, not position or tail length.
The shared join uses the newest observation at or before each anchor timestamp and
never a future value. DXY allows backward observations no more than one validated
timeframe duration old; the exact maximum-staleness boundary is inclusive.

Rows missing any participating constituent after that tolerance are rejected.
Per-symbol diagnostics report missing rows, stale rejections, and the latest
source timestamp. Entirely unavailable basket symbols retain the existing
missing-weight redistribution behavior. The formula, weights, minimum-history
ratio, bias interpretation, and confluence impact are unchanged.

## 10. Synthetic causal replay

| Decision UTC | Latest M5 open | Latest H1 open | Latest H4 open | Latest D1 open |
| --- | --- | --- | --- | --- |
| 2026-01-01 12:05 | 12:00 | 11:00 | 08:00 | 2025-12-31 00:00 |
| 2026-01-01 13:00 | 12:25* | 12:00 | 08:00 | 2025-12-31 00:00 |
| 2026-01-01 16:00 | 12:25* | 14:00* | 12:00 | 2025-12-31 00:00 |
| 2026-01-02 00:00 | 12:25* | 14:00* | 16:00 | 2026-01-01 00:00 |

`*` marks the end of that deliberately short synthetic series, not a filled row.
The replay includes unequal cross-symbol timelines and reports zero future-data
violations. It records visibility only and emits no profitability metrics.

## 11. Performance considerations

Normalization is linear and performed once per loaded dataset. Repeated backtest
selection uses sorted integer timestamp arrays and vectorized binary search rather
than scanning every HTF frame for every M5 decision. On the verification machine,
100,000 synthetic M5 candles normalized in about 1.55 seconds and 10,000 decision
positions were selected in about 0.73 seconds. These are approximate local sanity
measurements, not absolute or cross-platform performance claims.

No mutable snapshot cache was added; cache invalidation errors could reintroduce
stale or future visibility.

## 12. Runtime defenses

The shared boundary rejects naive, duplicate, malformed, unsupported, or
non-finite input. Snapshot selection rejects naive decisions and checks the causal
invariant. The backtester asserts that each generated HTF view has no
`available_at` later than the decision. Cross-symbol alignment rejects stale rows
and exposes structured diagnostics without account information.

## 13. Known limitations

- Same-candle signal/fill sequencing and market-on-trigger chronology were
  repaired in Phase 3; see `docs/PHASE3_EXECUTION_PARITY.md`.
- Shared partial-close, trailing and gross exit accounting were repaired in
  Phase 3. Tick reconstruction and transaction-cost realism remain Phase 7.
- Risk caps, floating drawdown, circuit-breaker outcomes, and atomic risk state
  were repaired in Phase 4; see `docs/PHASE4_RISK_PROTECTION.md`. Broader runtime
  persistence remains deferred.
- Broker invalid-stop retries remain Phase 5.
- ATR/regime, order-block mitigation, DXY semantics, and news policy were repaired
  in Phase 6 without weakening this causal data contract.
- Nominal final boundaries cannot model exchange-specific early closes; uncertain
  historical finals therefore remain excluded by default.
- Phase 6 retained this alignment and replaced the permissive linear proxy with
  the required six-constituent geometric DXY basket.

## 14. Reproduction

```powershell
$python = 'C:\Users\chips\forex-signal-bot\.venv\Scripts\python.exe'
& $python -m pytest tests\phase2
& $python backtests\causal_replay.py
& $python backtests\causal_replay.py --benchmark
```

These commands use synthetic or mocked data. They must not initialize MT5, start
the bot or Streamlit, access an account, place an order, run optimization, or
rewrite historical result files.
