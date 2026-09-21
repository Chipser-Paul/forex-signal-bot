# Phase 8B Exness Monthly Reconstruction

## Scope

This checkpoint validates the owner-supplied November 2024 Exness Tick
History archive, compares the complete November interval with the quarantined
annual archive, and establishes an offline one-month-at-a-time ingestion
workflow. It does not download data, access MT5 or an account, call a news or
order API, evaluate strategy behavior, open the empirical holdout, run a
backtest, or calculate performance.

Raw and processed evidence remains under
`C:\Users\chips\forex-signal-bot-data\phase8\exness-tick-history`, outside
Git. The source ZIPs were not extracted, renamed, modified, or committed.

## Immutable evidence

| Period | ZIP bytes | ZIP SHA-256 | Parquet bytes | Canonical SHA-256 |
| --- | ---: | --- | ---: | --- |
| 2024-11 | 40,736,279 | `edd4ead5f47b45f72d933735f9f52c8dc37b685bebfa03ade6a02db3e976c1a0` | 236,558,969 | `74cc3b55a4264a7329d8ba3bfbb65f9bc98bbabaa1fa12c77add0fe2d82349ed` |
| 2024-12 | 30,255,246 | `a5cef8ab1fb1bce26380113619c121da3062894b05b1c3d8de034c78bc8314fd` | 175,112,929 | `062ca48aa0e740c91290c8bba9434f564c7f826616fa8e0745bd3822564b5ebc` |
| Annual, quarantined | 313,203,271 | `e20f29457ede7b107ade6feca2f64ca33eb7e118171497300a89bccee3c94047` | 1,806,797,414 | `93c3eea8a5317c2c009fbb9bde72b774081b76d10c121f6e15fa6c19d3429185` |

November's single CSV member is 282,998,017 bytes uncompressed with SHA-256
`dca017e979dea5ca1ed043faa3a2335de6cd08602c6c9ccca5c62da5738bba68`.
Its compression ratio is 6.947 and the ZIP has one member. The package ID is
`exness-xauusdm-2024-11-edd4ead5f47b45f7`.

Filesystem creation and modification times were observed as
`2026-09-09T21:15:49Z` and `2026-09-09T21:15:32Z`. These are local
observations, not download provenance. The November Parquet SHA-256 is
`b01bce8a2696ddffa9a4eb945aa9cc9f9d68f0e1139cd5c45d32b4d9cbccc949`;
the package manifest SHA-256 is
`ee9d65f07c825c43a3ef6c0fc51306ef00cc7cebf476617057e036d6b380d7d0`.

## Archive and row contract

Central-directory inspection found one unencrypted CSV member and no path
traversal, absolute path, drive or UNC path, link, duplicate/case collision,
executable member, unsafe expansion, member-size, or compression-ratio
condition. The importer enforces the exact header
`Exness,Symbol,Timestamp,Bid,Ask`, exact row symbol `XAUUSDm`, explicit UTC
`Z` timestamps with millisecond precision, positive finite prices, and
`ask >= bid`. The source is streamed and no permanent CSV extraction occurs.

The 4,437,063 source records and complete Parquet read-back reconcile from
`2024-11-01T00:00:00.618Z` through `2024-11-29T18:29:58.997Z`. There are 25
observed UTC dates and no completely missing weekday in November.

Integrity findings:

- zero malformed, empty, invalid-time, wrong-symbol, non-finite,
  non-positive, crossed, locked, duplicate, or truncation-indicator rows;
- zero duplicate timestamps carrying different prices;
- zero source-order inversions in the monthly archive;
- 20 gaps longer than one hour: four weekend-associated and 16
  weekday-or-holiday-unverified;
- maximum gap 180,421.770 seconds, from November 1 to November 3.

Spread is observed `ask - bid` in price units, not broker points:

| Statistic | Price units |
| --- | ---: |
| Minimum | 0.15900000 |
| Median | 0.16000000 |
| P95 | 0.16000000 |
| P99 | 0.16000000 |
| Maximum | 0.24100000 |

There are six distinct spread values and zero observations above the bounded
diagnostic outlier rule `5 * p99 = 0.80000000`. These values do not establish
historically effective execution-cost calibration.

## Daily coverage

| UTC date | Rows | UTC date | Rows |
| --- | ---: | --- | ---: |
| 2024-11-01 | 186,618 | 2024-11-15 | 203,244 |
| 2024-11-03 | 5,461 | 2024-11-17 | 5,722 |
| 2024-11-04 | 162,217 | 2024-11-18 | 190,903 |
| 2024-11-05 | 157,486 | 2024-11-19 | 199,838 |
| 2024-11-06 | 373,343 | 2024-11-20 | 172,902 |
| 2024-11-07 | 239,724 | 2024-11-21 | 179,996 |
| 2024-11-08 | 201,052 | 2024-11-22 | 214,526 |
| 2024-11-10 | 3,702 | 2024-11-24 | 8,475 |
| 2024-11-11 | 210,987 | 2024-11-25 | 325,182 |
| 2024-11-12 | 234,176 | 2024-11-26 | 231,775 |
| 2024-11-13 | 226,985 | 2024-11-27 | 182,521 |
| 2024-11-14 | 243,426 | 2024-11-28 | 122,266 |
|  |  | 2024-11-29 | 154,536 |

## Complete November comparison

The comparison covers
`[2024-11-01T00:00:00Z, 2024-12-01T00:00:00Z)` and uses exact
timestamp/bid/ask multiplicities. Any source-only row or price conflict is
material.

| Measure | Result |
| --- | ---: |
| Annual November rows | 2,210,717 |
| Monthly November rows | 4,437,063 |
| Exact matching multiplicities | 2,210,717 |
| Annual-only ticks | 0 |
| Monthly-only ticks | 2,226,346 |
| Conflicting-price timestamps | 0 |
| Annual exact duplicate rows | 0 |
| Monthly exact duplicate rows | 0 |
| Duplicate timestamps with different prices | 0 in either source |

The annual archive omits every monthly tick on November 14 and November
18-29. Its first divergence is the missing monthly tick at
`2024-11-14T00:00:00.256Z`; its last is the missing monthly tick at
`2024-11-29T18:29:58.997Z`. Daily differences occur on November 14, 18-22,
and 24-29. All annual November records are an exact subset of the monthly
archive, including the annual November 15 and 17 records after its November
14 gap.

The complete-month canonical-multiset hashes are:

- annual: `f8687ffbc64c0e63a92c7af51cc767f2991f8ef5e6c001c01f97fb22dbd9eaa8`;
- monthly: `74cc3b55a4264a7329d8ba3bfbb65f9bc98bbabaa1fa12c77add0fe2d82349ed`.

The normalized-order hashes are the same respective values. The sources are
therefore not equal as complete months, despite exact agreement on every
annual record.

The annual manifest records exactly two whole-day source inversions:

- November 3 followed by November 1;
- November 5 followed by November 4.

The monthly source is monotonic and contains every annual record exactly
once. The inversions are annual-only source-order defects and are not
accompanied by November duplication or conflicting prices. Deterministic
normalization repairs ordering for comparison, but it cannot repair the
annual archive's missing November 14 and November 18-29 records.

The required complete-month classification is
`MATERIAL_FEED_DIFFERENCES`. The material differences are monthly-only rows
that expose annual omissions; they do not invalidate the internally sound
monthly archive. November itself is classified `DEVELOPMENT_ONLY`.

## Reconstruction authority

The two independent monthly archives establish monthly archives as the
canonical source granularity for a 2024 reconstruction. The annual archive
remains quarantined as `DEVELOPMENT_ONLY - INCOMPLETE`; it must never be mixed
with monthly packages.

A complete 2024 reconstruction is not yet authorized. It requires exactly one
verified package for each month January-December, no cross-month rows or
overlap, chronological boundary checks, a year-level immutable manifest and
canonical hash, and complete year read-back reconciliation. A duplicate raw
month, duplicate package month, changed raw/package hash, unexpected ZIP,
interrupted partial package, or annual/monthly mixture fails closed.

| Months | Status |
| --- | --- |
| January-October | `MISSING` |
| November | `VERIFIED_PACKAGE` |
| December | `VERIFIED_PACKAGE` |
| Complete 2024 | `INCOMPLETE_MONTHLY_SET` |

## Guarded batch workflow

`backtests/exness_monthly_control.py batch-status` validates the declared
twelve-month plan, re-hashes local raw archives, verifies immutable processed
packages, reports conflicts, and emits a bounded row-free readiness matrix.
`batch-next` ingests only the earliest locally available unverified month and
then stops. Repeating it resumes from verified packages and skips them
idempotently.

The workflow never downloads data. It only accepts owner-supplied immediate
ZIP children of the configured raw directory. The importer processes one ZIP,
maintains at least 15 GiB free, streams without permanent extraction, writes a
same-parent partial package, fully reconciles it, and atomically publishes a
new immutable package. Ordinary failures clean the partial. Crash residue is
not silently discarded; it blocks the workflow for explicit review.

```powershell
$env:PYTHONPATH = 'C:\Users\chips\forex-signal-bot-phase8'
& 'C:\Users\chips\forex-signal-bot\.venv\Scripts\python.exe' `
  'C:\Users\chips\forex-signal-bot-phase8\backtests\exness_monthly_control.py' `
  batch-status `
  --raw-root 'C:\Users\chips\forex-signal-bot-data\phase8\exness-tick-history\raw\monthly\2024' `
  --output-root 'C:\Users\chips\forex-signal-bot-data\phase8\exness-tick-history\processed'
```

Replace `batch-status` with `batch-next` to ingest one ready month. Inspect the
returned matrix after every invocation. The command does not import
MetaTrader5, read credentials, evaluate strategy logic, or access a network
provider.

## Storage model

November occupies 277,295,248 bytes as raw ZIP plus Parquet; December occupies
205,368,175 bytes. The remaining-ten-month scenarios use these two real
observations and are capacity calculations, not forecasts:

| Scenario | Remaining January-October ZIP plus Parquet |
| --- | ---: |
| Lower, ten times the smaller observed total | 2,053,681,750 bytes |
| Baseline, ten times the observed mean | 2,413,317,115 bytes |
| Upper, ten times 1.5 times the larger total | 4,159,428,720 bytes |

The upper raw-download-only scenario is 611,044,185 bytes. Temporary
conversion space is 354,838,453 bytes, based on 1.5 times the largest observed
raw or Parquet component. At the final readiness check, 57,475,375,104 bytes were
free. Upper converted storage, temporary space, and the 16,106,127,360-byte
reserve total 20,620,394,533 bytes, so January-October fit under this scenario.
Real month sizes can differ materially; the reserve remains authoritative.

## Owner download procedure

The owner may download all ten remaining raw archives sequentially before the
next ingestion run because the conservative raw-only scenario is small
relative to current free space. Downloads must not run concurrently.

1. In the Exness Tick History owner interface, choose exact symbol `XAUUSDm`.
2. Download each monthly period from January through October 2024, one at a
   time. Do not request an annual archive.
3. Keep each ZIP unextracted and unmodified. Do not rename it.
4. Place each file directly in the monthly raw directory. Expected identities
   are `Exness_XAUUSDm_2024_01.zip` through
   `Exness_XAUUSDm_2024_10.zip`.
5. Before starting the next download, confirm the prior download completed and
   that no browser-generated duplicate such as `(1)` exists.
6. Do not place `XAUUSD`, another symbol, another year, an annual archive, or a
   second ZIP for the same month in that directory.
7. After all ten downloads, leave the bot stopped and request the guarded
   ingestion. The workflow will hash and process one archive per invocation,
   stopping on the first ambiguity or integrity failure.

## Limitations

November and December are development evidence, not a holdout and not final
validation. Exness provenance remains indicative; exact server identity,
licensing, historically effective symbol metadata, commission, swap,
slippage/fill evidence, and historical USD news remain unresolved. No result
here is profitability, win-rate, profit-factor, strategy, or deployment
evidence. Phase 9 remains unauthorized.
