# Phase 8B Exness Monthly Continuity

## November follow-up

The November monthly archive has now been independently accepted and compared
against the complete annual November partition. Every annual November record
matches, while the monthly archive exposes 2,226,346 annual omissions and has
none of the annual source-order inversions. The required full-month comparison
classification is `MATERIAL_FEED_DIFFERENCES`, attributable to the incomplete
annual export. Monthly archives are now the canonical source granularity for
2024 reconstruction; January-October remain missing. See
`docs/PHASE8B_EXNESS_MONTHLY_RECONSTRUCTION.md`.

The December-era recommendation below is retained as historical checkpoint
context and has been satisfied.

## Scope and isolation

This checkpoint validates one owner-downloaded December 2024 Exness Tick
History archive against the overlapping portion of the previously ingested
annual archive. It does not run a strategy, backtest, optimization, holdout,
performance calculation, MT5 operation, account request, news request, order,
or trade.

Both source ZIPs are immutable evidence outside Git. The importer streams ZIP
members and writes only atomic derived packages beneath the external
`processed` directory. It does not extract a permanent CSV.

## Source archives

| Item | Annual archive | December archive |
| --- | --- | --- |
| Filename | `Exness_XAUUSDm_2024.zip` | `Exness_XAUUSDm_2024_12.zip` |
| Bytes | 313,203,271 | 30,255,246 |
| SHA-256 | `e20f29457ede7b107ade6feca2f64ca33eb7e118171497300a89bccee3c94047` | `a5cef8ab1fb1bce26380113619c121da3062894b05b1c3d8de034c78bc8314fd` |
| Member | `Exness_XAUUSDm_2024.csv` | `Exness_XAUUSDm_2024_12.csv` |
| Member compressed bytes | 313,203,111 | 30,255,080 |
| Member uncompressed bytes | 2,147,386,835 | 208,589,370 |
| Member SHA-256 | `b9b6a99486bed4641306f2c7646bd1d229e0132a12fc7e85f1df18770ad2571a` | `e1af88a36eaa2d13dc5ac94d63d43f83882d3a0a9c4f9dcde228e54123fd3680` |
| Compression ratio | 6.856 | 6.894 |

The December ZIP filesystem creation time was observed as
`2026-09-09T16:39:27Z` and modification time as
`2026-09-09T16:38:58Z`. Filesystem times are observations, not authoritative
download provenance. The annual hash was recalculated before comparison and
matches the accepted value exactly.

## Archive and data contract

The December ZIP contains exactly one unencrypted CSV member. It has no path
traversal, absolute/drive/UNC path, link, duplicate member, case-normalized
collision, executable content, unsafe member size, unsafe aggregate expansion,
or dangerous compression-ratio finding. The 15 GiB reserve remained intact
during inspection and conversion.

The observed CSV contract is:

- UTF-8, comma-delimited, exact header `Exness,Symbol,Timestamp,Bid,Ask`;
- exact row symbol `XAUUSDm`, with no suffix translation;
- source identity restricted to case-insensitive exact `Exness`;
- explicit UTC `Z` timestamps with millisecond precision;
- positive finite decimal bid and ask values, with `ask >= bid`.

## December coverage

The source and complete Parquet read-back reconcile at 3,270,432 rows.
Coverage begins at `2024-12-01T23:05:00.178Z` and ends at
`2024-12-31T21:57:57.766Z`, spanning 27 observed UTC dates. All weekdays
inside December are represented. Saturday closure dates are absent as
expected from the observed schedule; weekend and holiday labels remain
observational rather than broker-calendar proof.

| UTC date | Rows | UTC date | Rows |
| --- | ---: | --- | ---: |
| 2024-12-01 | 5,626 | 2024-12-16 | 118,406 |
| 2024-12-02 | 226,655 | 2024-12-17 | 161,391 |
| 2024-12-03 | 183,306 | 2024-12-18 | 184,828 |
| 2024-12-04 | 188,363 | 2024-12-19 | 208,794 |
| 2024-12-05 | 173,671 | 2024-12-20 | 178,787 |
| 2024-12-06 | 205,102 | 2024-12-22 | 1,851 |
| 2024-12-08 | 5,500 | 2024-12-23 | 123,951 |
| 2024-12-09 | 166,996 | 2024-12-24 | 100,970 |
| 2024-12-10 | 180,904 | 2024-12-25 | 2,366 |
| 2024-12-11 | 185,368 | 2024-12-26 | 118,139 |
| 2024-12-12 | 73,748 | 2024-12-27 | 135,691 |
| 2024-12-13 | 70,310 | 2024-12-29 | 4,006 |
| 2024-12-15 | 1,931 | 2024-12-30 | 141,410 |
|  |  | 2024-12-31 | 122,362 |

Integrity statistics:

- zero malformed, empty, invalid-time, non-finite, non-positive, crossed,
  locked, wrong-symbol, non-monotonic, or truncation-indicator rows;
- zero exact duplicate rows and zero duplicate timestamps with different prices;
- 21 gaps longer than one hour: 5 weekend-associated and 16
  weekday-or-holiday-unverified;
- maximum gap 176,838.453 seconds, from Friday 13 December to Sunday 15
  December;
- the weekday/unverified group includes observed daily closure gaps of about
  63 minutes and longer observations around 8-9 and 24-25 December. These are
  reported, not silently accepted as proven broker closures.

Spread is `ask - bid` in price units:

| Statistic | Price units |
| --- | ---: |
| Minimum | 0.06400000 |
| Median | 0.16000000 |
| 95th percentile | 0.16000000 |
| 99th percentile | 0.16800000 |
| Maximum | 1.47200000 |

There are 85 distinct values. Twelve observations exceed the diagnostic
outlier rule `5 * p99 = 0.84000000`. These observations are not execution-cost
calibration.

## Deterministic package

The external package is
`exness-xauusdm-2024-12-a5cef8ab1fb1bce2`. It contains one Zstandard
Parquet partition of 175,112,929 bytes with SHA-256
`66407203016d7ddc95bc8fc760b0cf6a008f7dce6a5a701a1c90fbe09fb0fded`.

The normalized-record SHA-256 is
`062ca48aa0e740c91290c8bba9434f564c7f826616fa8e0745bd3822564b5ebc`.
The manifest SHA-256 is
`47ba68ffbe7de41965de78b96de475cbb1fdbc3e7a030adcba7f76f991f25fe3`.

Source and read-back row counts, first/last timestamps, symbol, archive hash,
row identities, duplicates, gaps, and canonical hash reconcile. A repeat
ingest returned the same package ID and canonical hash with
`idempotent_existing_package=true`; it did not rewrite the package or source.

## Exact overlap comparison

The exact common interval is
`2024-12-15T23:05:14.949Z` through
`2024-12-15T23:59:58.946Z`.

| Comparison | Result |
| --- | ---: |
| Annual rows in overlap | 1,931 |
| Monthly rows in overlap | 1,931 |
| Timestamps present in both | 1,931 |
| Exact timestamp/bid/ask matches | 1,931 |
| Annual-only ticks | 0 |
| Monthly-only ticks | 0 |
| Same timestamps with conflicting prices | 0 |
| Source-order differences | 0 |
| Daily-count differences | 0 |

Both source-order and normalized overlap SHA-256 values are
`9234bb8efb57bd1c026b931d4a8449a54ef345b179c121f6e15fa6c19d3429185`.
The overlap classification is `IDENTICAL`. There is no first or last
divergence.

The comparison uses zero tolerance: any source-only row, multiplicity
difference, or price conflict is material. The `MINOR_FEED_DIFFERENCES`
classification is reserved but is not emitted by this policy. Order-only
differences may be classified as `EQUIVALENT_AFTER_ORDER_NORMALIZATION` when
the exact timestamp/bid/ask multiset remains equal.

## Continuation and truncation evidence

The monthly archive's first post-cutoff tick is
`2024-12-16T00:00:00.026Z`. It supplies 1,602,952 rows dated December 16-31
and continues through `2024-12-31T21:57:57.766Z`. The annual member ends on
December 15 and is 96,813 bytes below the signed 2 GiB boundary.

Because at least 1,000 overlapping rows match exactly, the monthly file
continues beyond the annual cutoff, and the annual member is within 1 MiB of
that boundary, the hypothesis that the annual export hit a size-related limit
is `STRONGLY_SUPPORTED_BY_DATA`. This is not
`CONFIRMED_BY_DOCUMENTATION`: no official Exness statement establishing a
2 GiB export limit was used or found in this offline checkpoint.

The monthly archive repairs these ten December weekdays already listed as
missing by the annual manifest: December 2-6 and 9-13. It also supplies twelve
weekdays after the annual cutoff: December 16-20, 23-27, 30, and 31. In total,
26 UTC dates present in the monthly source are absent from the annual source;
the remaining four are Sunday session dates. December evidence does not prove
that January-November gaps are repaired.

## Reconstruction policy

The defensible reconstruction policy is all twelve independently accepted
monthly archives, exclusively. Annual January-November plus monthly December
is not recommended because it mixes source granularity and provenance while
retaining the annual archive's 25 missing weekdays, 184 weekday-or-holiday
gaps, 11,777 exact duplicates, and two ordering inversions without testing
whether monthly files repair them.

Reconstruction remains unauthorized until exactly one accepted package exists
for every month. Packages are ordered by calendar month. Duplicate month
packages, annual/monthly mixing, cross-month overlap, any price conflict, or
ambiguous precedence fail closed. This prevents silent double counting. All
twelve 2024 monthly archives are therefore required before a reconstructed
2024 package can be proposed.

## Classification and storage

The December archive is `DEVELOPMENT_ONLY`. The annual archive remains
`DEVELOPMENT_ONLY - INCOMPLETE`. Neither is final-validation or holdout data.
Even a complete monthly reconstruction would retain indicative Exness
provenance, unresolved exact-server identity and licensing, and missing
historically effective metadata, commission, swap, slippage/fill, and news
evidence.

The December ZIP plus Parquet package occupies 205,368,175 bytes. Scaling this
single month is a storage scenario, not a forecast; month-to-month and
year-to-year tick volume may be materially different.

| Scenario | 12 monthly archives plus Parquet | Five other development years |
| --- | ---: | ---: |
| Lower, 0.75 times December rate | 1,848,313,575 | 9,241,567,875 |
| Baseline, December rate | 2,464,418,100 | 12,322,090,500 |
| Upper, 1.5 times December rate | 3,696,627,150 | 18,483,135,750 |

Temporary working space is estimated at 262,669,393 bytes per conversion.
At the latest check, 57,341,202,432 bytes were free and the required reserve
was 16,106,127,360 bytes. Pure reserve arithmetic would accommodate the eleven
remaining 2024 monthly archives under the upper monthly scenario. The
disk-reserve-only concurrency bound is 72 December-sized upper-scenario units
when each unit includes its temporary conversion allowance; only 11 remain in
2024. This is not an acquisition recommendation. The authorized operational
maximum remains one new archive at a time because the December rate does not
establish other months' sizes or quality.

The next and only recommended download is `XAUUSDm`, November 2024. It tests
adjacency at the annual cutoff and whether the annual November partition and
its gaps agree with an independent monthly export. No other archive is
authorized by this recommendation.

## Implementation and deferred inputs

The importer now has explicit annual/monthly period identity, month-bounded
coverage validation, deterministic monthly package IDs, period-aware storage
projection, exact overlap comparison, and fail-closed twelve-month
reconstruction planning. The control command is offline and does not import
MetaTrader5.

Phase 8 still needs the other eleven 2024 monthly archives, historically
effective broker metadata, commission, swap, slippage/fill evidence,
historical USD news with provenance, licensing resolution, and the
preregistered development and holdout datasets. No holdout or performance
evaluation occurred. Phase 9 remains unauthorized.
