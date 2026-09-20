# Phase 8B Exness Archive Ingestion

## Scope and safety

This record covers offline inspection and conversion of one owner-supplied
Exness Tick History archive. No strategy, backtest, holdout, profitability,
MT5, account, order, browser, or network operation is part of this work.

The immutable source is outside every Git worktree:

`C:\Users\chips\forex-signal-bot-data\phase8\exness-tick-history\raw\Exness_XAUUSDm_2024.zip`

The importer never writes beneath `raw`. Derived packages are written under
the sibling `processed` directory and are excluded from Git.

## Source identity

| Item | Observed value |
| --- | --- |
| Archive size | 313,203,271 bytes |
| Archive SHA-256 | `e20f29457ede7b107ade6feca2f64ca33eb7e118171497300a89bccee3c94047` |
| Member | `Exness_XAUUSDm_2024.csv` |
| Member compressed size | 313,203,111 bytes |
| Member uncompressed size | 2,147,386,835 bytes |
| Member SHA-256 | `b9b6a99486bed4641306f2c7646bd1d229e0132a12fc7e85f1df18770ad2571a` |
| Compression ratio | approximately 6.856 |
| Claimed year | 2024 |
| Exact archive/member symbol | `XAUUSDm` |
| Acquisition | manual owner download through the Exness Personal Area |
| Source page | `https://www.exness.com/tick-history/` |

Filesystem creation and modification times are recorded in the external
inspection file, but they are observations only and are not authoritative
download provenance.

The data-row source label is an ASCII case variation of `Exness`. The importer
accepts only this case-insensitive Exness identity and preserves the raw
label. Unrelated provider names remain fatal.

## Archive safety

Central-directory inspection found one unencrypted CSV member. The archive has
no absolute path, traversal path, drive or UNC path, symbolic-link entry,
duplicate member, case-normalized name collision, executable/script member, or
unsafe expansion ratio. Declared expansion is below the configured 5 GiB
member and 10 GiB archive limits.

The conversion requires a 15 GiB free-space reserve and a 5 GiB maximum output
budget. It streams the ZIP member and never extracts a second CSV copy.

## Observed data contract

The member is UTF-8 without a BOM, comma-delimited, and has one header:

`Exness,Symbol,Timestamp,Bid,Ask`

Every accepted row has five fields. Timestamps carry an explicit `Z` suffix
and millisecond precision, so the canonical timestamp is timezone-aware UTC.
Bid and ask are positive finite decimal values. The exact row-level symbol is
`XAUUSDm`; no suffix translation is applied.

Canonical output preserves source strings and adds UTC timestamp, Unix
milliseconds, decimal bid/ask values, original source sequence, stable row
identity, archive/member hashes, and a non-sensitive provenance identifier.

## Coverage and integrity

The archive contains 33,669,558 accepted rows spanning:

- first: `2024-01-01T23:05:09.882Z`
- last: `2024-12-15T23:59:58.946Z`
- observed UTC dates: 271

Monthly row counts:

| Month | Rows |
| --- | ---: |
| 2024-01 | 2,346,574 |
| 2024-02 | 1,853,293 |
| 2024-03 | 2,285,761 |
| 2024-04 | 4,058,725 |
| 2024-05 | 3,429,450 |
| 2024-06 | 2,647,468 |
| 2024-07 | 3,236,688 |
| 2024-08 | 3,823,559 |
| 2024-09 | 3,511,082 |
| 2024-10 | 4,264,310 |
| 2024-11 | 2,210,717 |
| 2024-12 | 1,931 |

The source sequence has two adjacent timestamp inversions. It places November
1 after November 3 and November 4 after November 5. These defects are retained
in the manifest with bounded timestamp-only examples. Canonical Parquet is
ordered by `(timestamp UTC, original sequence_id)` so equal timestamps remain
stable and reproducible.

The canonical read-back found:

- 11,777 exact duplicate timestamp/bid/ask observations;
- zero duplicate timestamps carrying different prices;
- zero crossed quotes;
- zero locked quotes;
- 233 gaps longer than one hour;
- 49 weekend-associated long gaps;
- 184 weekday-or-holiday-unverified long gaps;
- maximum observed gap of 2,415,915.161 seconds;
- 25 completely missing weekdays.

No problematic row is discarded silently. Exact duplicates are retained and
counted because source sequence is part of record identity.

The final timestamp is mid-December and the CSV member is 96,813 bytes below
the signed 2 GiB boundary. The independently downloaded December archive now
matches all 1,931 overlapping ticks and continues through December 31. The
size-limit truncation hypothesis is therefore `STRONGLY_SUPPORTED_BY_DATA`,
but is not confirmed by official documentation. See
`docs/PHASE8B_EXNESS_MONTHLY_CONTINUITY.md`. The annual archive remains
`DEVELOPMENT_ONLY - INCOMPLETE` and must not be represented as complete
calendar-year 2024 evidence.

## Spread observations

Spread values are observed ask minus bid in price units, not points:

| Statistic | Price units |
| --- | ---: |
| Minimum | 0.15900000 |
| Median | 0.20000000 |
| 95th percentile | 0.20000000 |
| 99th percentile | 0.30000000 |
| Maximum | 9.02600000 |

There are 423 distinct spread values. The diagnostic outlier rule is
`spread > 5 * p99`, giving a threshold of 1.50000000 and 208 observations above
it. This is an integrity statistic only and is not a trading-cost calibration.

## Deterministic package

The package identifier is
`exness-xauusdm-2024-e20f29457ede7b10`. It contains 12 Zstandard Parquet
partitions, one per observed month. The total Parquet size is 1,806,797,414
bytes.

The canonical normalized-record SHA-256 is:

`93c3eea8a5317c2c009fbb9bde72b774081b76d10c121f6e15fa6c19d3429185`

The manifest SHA-256 is
`23d94fc21bdabbc281154c72f5e54e1f8e5f61ee705e306c0f33b4de2ed21d12`.
Partition hashes are:

| Month | Bytes | SHA-256 |
| --- | ---: | --- |
| 2024-01 | 126,653,785 | `e56375172f7e2bc51b12b93b5569c254d617426e1db9a97e2c725dc3be5ad245` |
| 2024-02 | 99,868,595 | `c857a1595b349c3efd40cfdd295db461188a6661b4addb63b71932b1d565823b` |
| 2024-03 | 123,564,866 | `1772611db261009bb4b9ac8c78bfe0337d8f60efa118d8e8dac46b92edb2b0a0` |
| 2024-04 | 217,830,513 | `a7bbb209c230770256d4239e28d83ca114a5b1b87f702391bb0748c8cf57a457` |
| 2024-05 | 184,625,721 | `a7cb6f29cf4d927c5221f8d7e81e9fa1cbc4ea0c9c9c6fbcb8847ccd70678e97` |
| 2024-06 | 142,820,292 | `62237791eb3a2c4db447714d08946f2e6c68dc6325958b959d9da4647a353e4e` |
| 2024-07 | 174,330,020 | `3e341678d644e0100ccf6e9b229d3262ff6b59d56d9c49f1d252a0963e33e826` |
| 2024-08 | 204,822,130 | `237ffaf55d48dae6adeb69e64bdd5a592b7f0c67d5e86be702cadcc8563c7d32` |
| 2024-09 | 186,921,703 | `45860f4d5b3de206c098ee2445d0d8e49ef8068a9ac93e1550169ea1349e23a2` |
| 2024-10 | 227,394,743 | `34c9b6d6ab1a0c9c0a81428290bbeaac31126c53592425255d6d65a9156f839d` |
| 2024-11 | 117,849,034 | `b7278fa56aed94e251a029bdd571e20c9519914dbb5f36f53d162f22cbd630ba` |
| 2024-12 | 116,012 | `46373a5c690542b66a148d936e1f40fc82eb61ecc502f6274391b6c0f1982fb9` |

Publication uses a same-parent partial directory, fsync, deterministic
manifest serialization, completion marker, and atomic directory replacement.
The completed data is read back and reconciled for row count, first/last UTC
timestamps, symbol, archive identity, record identities, ordering, duplicate
statistics, gap statistics, and canonical hash. A repeated ingest detects and
verifies the complete package instead of overwriting it.

## Classification

The highest assigned class is `DEVELOPMENT_ONLY` with Phase 7 fidelity
`TICK_BID_ASK`. This means the observations are usable for guarded engineering
and calibration work only. It does not mean that the archive is complete,
validation eligible, broker-server-specific, or licensed for redistribution.

Reasons preventing final-validation classification:

- 2024 is preregistered development data, not the locked holdout;
- Exness describes Tick History as indicative;
- the exact trading server and account type are not proven by the archive;
- redistribution and research-use rights are not proven;
- historical commission, swap, slippage, fills, rollover rules, and effective
  broker metadata remain separate inputs;
- the observed year is incomplete and has unexplained weekday gaps;
- possible 2 GiB export truncation remains unresolved.

The raw data itself is not committed. Only importer code, fixture tests, and
this row-free audit record belong in Git.

## Storage projection

The projection uses the observed 2024 compressed plus converted size as a
scenario, not a forecast for other years:

| Scenario for 2019-2023 | Bytes |
| --- | ---: |
| Conservative lower | 7,950,002,568 |
| Baseline | 10,600,003,425 |
| Upper | 15,900,005,137 |
| Temporary working space | 2,710,196,121 |
| Required reserve | 16,106,127,360 |
| Free space after conversion | 58,147,061,760 |

The upper scenario plus temporary space and reserve fits the observed disk,
but acquisition must still proceed one archive at a time because period size
and completeness can differ. The next candidate is the Exness `XAUUSDm`
November 2024 monthly archive. It must be hashed, inspected, coverage-checked,
and accepted before any other download is authorized.

## Deferred inputs

The November and December monthly archives are now accepted as development
evidence. Phase 8 still needs January-October for a provenance-safe 2024
reconstruction. See `docs/PHASE8B_EXNESS_MONTHLY_RECONSTRUCTION.md` for the
guarded workflow and complete November comparison.

Phase 8 also still needs
historically effective symbol metadata, commission, swap, slippage/fill
evidence, historical USD news with provenance, and the preregistered empirical
years. The holdout remains locked. Phase 9 remains unauthorized.

No result in this document is profitability, win-rate, profit-factor, or live
readiness evidence.
