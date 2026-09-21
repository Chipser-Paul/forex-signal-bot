# Phase 8D — Causal 2024 DXY Development Input

Status: **VERIFIED (development-only)** — the causal 2024 DXY development
input is derived, published, independently verified and registered for
discovery. The complete empirical dataset remains **unaccepted**.

Label: `DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE`

## Why the original derived-candle package was not touched

Phase 8C produced the XAUUSDm candle package at commit `2817d5b` and
attested it at `fd1ed51`. Phase 8D adds a new, separate input package; the
XAUUSDm tick package, derived candles, attestation and discovery records are
immutable evidence and were re-verified byte-identical after this
checkpoint:

- `derived-candles-2024-v1-20260911T195553Z/manifest.json`
  `6715e5c64d888215ea9c88a6ab77e5340046f367ed6250813158f6b1f096d316`
- `derived-candles-2024-v1-20260911T195553Z/pipeline.complete.json`
  `1342bdb19c4c473243085d41d10cedea8d25b30729473c02d4d63bead6e31d43`
- `attestations/.../attestation.json`
  `8a5ee16c118efbf7f738d671741d9c5f3b45f139e81a8d565e3a2340436ca75e`

## DXY consumer audit (why H1 closes are sufficient)

The committed consumers of DXY are:

- `bot/strategy/dxy.py::evaluate_dxy` — builds the basket from six
  constituent close frames via `build_synthetic_dxy_from_frames`,
  `timeframe="H1"`, warm-up `dxy_lookback_bars = 20`, staleness
  `dxy_max_staleness = 1 hour`, alignment backward on `available_at`.
- `bot/analysis/dxy_filter.py::get_synthetic_dxy` /
  `analyze_dxy_correlation` — same builder, `"H1"`, 100-bar fetch, 20-bar
  bias lookback; `causal_snapshot`/`align_causal_observations` align on
  `available_at` with `max_staleness = H1 duration`.

Therefore the minimum causally sufficient input is **six constituent H1
close series**. Bid/ask bars, mid bars and ticks are not required by any
committed consumer; no tick request was made. The formula, constant,
exponents, inverse-gold directional interpretation, alignment policy and
staleness policy are unchanged; this checkpoint only supplies the data.

## Source selection and authorization

No accepted offline constituent-bar package existed, so the single
authorized bounded read-only MT5 session was executed from the clean
committed snapshot `ebb2b62e1ea25397ba918caedaedc35ee6b8119d`
(`feat: add causal DXY input pipeline`) under the existing guards:

- Official bot-control state verified `STOPPED`; no ambiguous process.
- Credential-bearing environment variables stripped before import
  (`scrub_current_environment`); the supervisor passed a scrubbed
  environment to the worker child.
- Canonical `ReadOnlyMT5Gateway` only: `initialize()` (no login arguments),
  `version()` → build 500.6182, sanitized `last_error()` (SUCCESS),
  `symbol_info()`/`symbol_select()` per mapping,
  `copy_rates_range()` for the six verified mappings, monthly chunks,
  2024 only, and one `shutdown()` in `finally`.
- No account, order, position, deal, margin or profit API exists on the
  gateway surface; `order_send` remains confined to the approved broker
  adapter blocklist.

## Six resolved symbol mappings (currency-verified)

| Canonical | Broker | Base/Profit | Digits |
|---|---|---|---|
| EURUSD | EURUSDm | EUR/USD | 5 |
| USDJPY | USDJPYm | USD/JPY | 3 |
| GBPUSD | GBPUSDm | GBP/USD | 5 |
| USDCAD | USDCADm | USD/CAD | 5 |
| USDSEK | USDSEKm | USD/SEK | 5 |
| USDCHF | USDCHFm | USD/CHF | 5 |

These are analytical inputs only; the production allowlist remains exactly
`XAUUSDm`.

## Package

`C:\Users\chips\forex-signal-bot-data\phase8\dxy\dxy-development-2024-v1-20260912T091410.712364Z`

- 6 constituent H1 partitions (24/7 FX reality: 6,240 observed windows each;
  USDSEK 6,216), missing windows remain missing — never forward-filled.
- Causal DXY partition: 6,216 rows, available
  2024-01-01T23:00:00Z → 2024-12-31T22:00:00Z; every row records all six
  source row identities and alignment ages; 25 anchors rejected
  (`STALE_CONSTITUENT:USDSEK`) instead of fabricated.
- `manifest.json` (schema `phase8d.dxy-manifest.v1`), `pipeline.complete.json`
  (binds the manifest hash), coverage + gap/staleness reports, provenance
  (commit, code fingerprint, retrieval time, terminal build, acquisition
  evidence, journal path).
- The final 2024-12-31T23:00Z H1 bar completes exactly at the holdout
  boundary and was excluded; no record is available at or after
  2025-01-01T00:00:00Z.

Key identities:

- DXY partition `sha256` `00c2bae585b317582fd46488698a9a3b11dd2fbc13f86efe73b827cda5f2addf`,
  canonical `b6a180756b42ba65c4fd050c6cd10ad35347e4804223fe1cca60f29da44bb531`
- Implementation commit `ebb2b62e1ea25397ba918caedaedc35ee6b8119d`,
  fingerprint `phase8d-pipeline-v1:a5cdca8ba832357e7b37c5b740cda02b1b2ce55238b14dbe4b64b62b606af435`

## Verification performed

Independent fresh-process `verify` re-hashes and re-reads every partition,
re-derives the whole causal DXY series from the stored constituents and
compares canonical hashes (formula reproduction), checks ordering,
closed-open H1 boundaries, availability causality, development-interval
containment, mapping consistency and gap-report reconciliation. The
discovery registration was executed twice and is idempotent; tampering,
row-count and manifest-mutation tests fail closed in
`tests/phase8d/test_dxy_contracts.py`.

## Discovery / readiness

`C:\Users\chips\forex-signal-bot-data\phase8\derived\discovery\dxy-development-2024-v1-20260912T091410.712364Z\discovery.json`
(schema `phase8d.dxy-discovery.v1`, canonical
`dfd06a17716c1d567770d7bd8f945e826e6af82aa92cf8f0449f4f10b9f6747d`, physical
`0402bd162238d1ba03cbdb37efef35eafe5d128cad86c98238ae39849971c0dc`)
records: package identity, manifest/completion hashes, source year-package
identity, per-symbol hashes and gap statistics, DXY hashes, alignment and
staleness summaries, verification status, and the readiness flags
`accepted_for_final_validation = false`,
`strategy_evaluation_authorized = false`,
`holdout_access_authorized = false`.

Recovery: if the discovery record is missing or corrupt, re-run
`python backtests/dxy_input_control.py register` — it rebuilds the record
from the immutable package and refuses to overwrite a conflicting record.
If the package itself is damaged, it must be quarantined; do not repair in
place. Re-acquisition requires a new non-overwriting package directory.

## Still missing (dataset remains unaccepted)

Historical high-impact USD news with provenance/licensing; historically
effective broker metadata; commission schedule; swap, rollover timezone and
triple-swap rules; empirical slippage/fill evidence; untouched holdout.
