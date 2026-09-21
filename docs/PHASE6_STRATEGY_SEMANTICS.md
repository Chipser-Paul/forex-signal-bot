# Phase 6 Strategy Semantics

Phase 7 preserves this strategy contract unchanged and adds the historical
execution/data-fidelity contract in `docs/PHASE7_REALISTIC_BACKTESTING.md`.

Parent commit: `657a377cb239e533ccd15436ba91d28a9cfe4c85`

Phase 6 defines a deterministic, causal strategy interpretation. It does not tune
parameters, model transaction costs, or provide evidence of profitability.

## Strategy audit

| Path | Baseline finding | Phase 6 decision |
| --- | --- | --- |
| `bot/state/orchestrator.py` | Live gates mixed wall clock, mutable profile state, permissive news, informational DXY, and scored safety checks | Exact-symbol guard, fail-closed safety gates, immutable profile use, and final canonical decision gate |
| `backtests/shadow_mode_backtest.py` | Duplicated gates, forced session allow, and opening-time-era strategy conventions | Phase 2 snapshots retained; session/news fail closed and canonical replay gate added |
| `bot/analysis/dxy_filter.py` | Linear weighted proxy tolerated missing pairs | Six-pair geometric basket; all components required and causally aligned |
| `market_structure.detect_market_condition` | Scalar ATR baseline made volatility ratio effectively constant | Completed-frame ATR series normalized by close with trailing baseline |
| `ob_breaker_engine` | A close outside the zone was treated as mitigation | Mitigation requires post-confirmation zone overlap; typed lifecycle controls reuse |
| `news_filter.py` | Missing/invalid source became an empty clear calendar | Fresh successful provenance-bearing snapshot required |
| `session_clock.py` | Naive times were silently UTC and session was always allowed | Aware UTC required; weekend, rollover, and broker availability fail closed |
| `confluence_scorer.py` | Session, news, and DXY could compensate as score points | Setup evidence only; safety gates are vetoes |
| `main.py` | XAUUSDm and BTCUSDm were executable | Production allowlist is exactly `XAUUSDm`, checked again before broker submission |

Phase 2 `open_time`/`available_at` is mandatory. Regime needs 34 bars with the
default ATR/baseline settings; DXY needs 20 aligned H1 observations; order blocks
need ATR warm-up plus candidate and confirmation candles. Missing warm-up is an
unsafe, non-trading state.

## Decision contract

`StrategyInput` and `StrategyDecision` are frozen typed records. A decision
records exact symbol, UTC decision time, `LONG`/`SHORT`/`FLAT`, regime, HTF bias,
DXY/news/session/order-block states, setup evidence, causal source identities,
invalidation metadata, stable reasons, strategy version, and a credential-free
configuration fingerprint. Serialization is deterministic JSON.

Live and replay adapters invoke the same pure reducer. Any failed gate produces
`FLAT` and `entry_eligible=false`; downstream code cannot turn that decision into
an entry. A compatibility translator makes the established orchestrator and
shadow replay pass through this final canonical gate.

## Executable universe

The production execution allowlist is exactly `XAUUSDm`. `XAUUSD`, `BTCUSDm`,
direct DXY symbols, and basket constituents are rejected without suffix rewriting.
DXY mappings are read-only and cannot expand the allowlist. Existing owned
`XAUUSDm` positions remain manageable through Phase 5; manual and foreign
positions retain Phase 5 ownership protection.

## DXY and bias

The fallback formula is:

`50.14348112 * EURUSD^-0.576 * USDJPY^0.136 * GBPUSD^-0.119 * USDCAD^0.091 * USDSEK^0.042 * USDCHF^0.036`

All six positive finite closes are required. Phase 2 bounded backward joins use
availability timestamps, never future observations. The default maximum age is
one hour. A configured direct DXY frame may take priority under identical causal
and freshness rules. Direction is normalized trailing slope over 20 observations.

Gold/DXY inverse agreement supports a setup, neutral DXY is non-vetoing, and a
same-direction reading rejects it. This relationship is probabilistic and is not
counted again in confluence. W1/D1/H4 bias uses fixed 0.40/0.35/0.25 weights and
fails closed on missing or unsafe inputs.

## ATR and regime

ATR is a 14-bar simple moving average of true range from completed candles.
Volatility is `ATR / close`; the current value is divided by the preceding 20-bar
mean, excluding the current observation. A ratio at or above 1.5 is
`HIGH_VOLATILITY`. Otherwise, 20-bar close displacement divided by current ATR at
or above 0.9 is `TRENDING_UP`; at or below -0.9 is `TRENDING_DOWN`; otherwise it is
`RANGING`. Invalid OHLC, non-finite/non-positive values, or insufficient warm-up
produce `DATA_UNSAFE`. These are unvalidated semantics, not optimized settings.

High volatility blocks new entries. A directional trend blocks the opposite side.
Regime changes do not alter management of existing owned positions.

## Order blocks

A candidate is the opposite-color candle immediately before a displacement close
through its extreme. Displacement body must be at least 1.5 current ATR. The zone
is the candidate high/low and becomes available only when confirmation closes.
The confirmation candle cannot retest its own block.

An untouched confirmed block is `ELIGIBLE`; its first later overlapping candle is
`RETEST_ELIGIBLE`. A subsequent evaluation is `MITIGATED`. A close through the
adverse edge invalidates it, consumed IDs cannot recur, and more than 30 later bars
expires it. Long/short rules mirror each other. Most recent confirmation and a
stable zone/ID ordering resolve multiple blocks.

## News policy

New entries require a successful fresh typed calendar snapshot. Events record a
stable ID, aware UTC time, currency, impact, name, retrieval time, and provider.
High-impact USD events block `XAUUSDm` inclusively from 30 minutes before through
30 minutes after.

Missing configuration, provider/file failure, malformed payload, unknown impact,
ambiguous timezone, stale/future cache, or provenance mismatch is `DATA_UNSAFE`.
A clear calendar is valid only when a fresh successful response explicitly has no
active events. Tests inject snapshots; no network provider is called. Existing
positions are not liquidated by this filter.

## Session policy

All internal times are aware UTC. Weekends, broker-unavailable state, and the
half-open rollover interval 21:55 through 22:10 UTC block new entries. Named
`Europe/London` and `America/New_York` zones provide DST-correct priority labels;
priority is context, not an extra gate. Missing timezone data or a naive clock is
unsafe. Existing position management remains active.

## Confluence

| Feature | Frame | Long / short / neutral | Weight | Warm-up/failure | Role |
| --- | --- | --- | --- | --- | --- |
| HTF bias alignment | W1/D1/H4 | Match / mirrored / reject | 2 | All HTFs required | Setup evidence |
| Premium/discount | Structure | Discount / premium / absent | 1 | Structure required | Setup evidence |
| Order block | Entry | Bullish / bearish / unavailable | 2 | ATR plus confirmation | Setup evidence |
| FVG overlap | Entry | Directional / mirrored / absent | 1 | Valid zones required | Setup evidence |
| Liquidity sweep | Structure | Sell-side / buy-side / absent | 2 | Causal sweep required | Setup evidence |
| DXY | H1 | Inverse support / same-direction veto / neutral | Veto | 20 aligned bars | Mandatory gate |
| News | Calendar | Clear / blocked / unsafe | Veto | Fresh snapshot | Mandatory gate |
| Session | Clock | Open / closed / unsafe | Veto | Aware clock | Mandatory gate |
| Symbol | Request | Exact XAUUSDm / reject | Veto | None | Mandatory gate |

The setup maximum and default threshold are both 8; equality passes. Safety gates
cannot be offset by points. No component changes Phase 4 monetary risk, and no
score is described as accuracy or calibrated probability.

## Parity and deferred work

`backtests/strategy_semantics_replay.py` covers 18 causal scenarios and compares
normalized live/replay decisions. Strategy code exposes no broker mutation API.
Phase 4 remains the risk authority and Phase 5 remains the secured live mutation
boundary.

Phase 7 owns historical bid/ask, spread, slippage, commission, swap, and tick-path
realism. Phase 8 owns scientific validation and parameter selection. Phase 6
outputs are not profitability evidence.
