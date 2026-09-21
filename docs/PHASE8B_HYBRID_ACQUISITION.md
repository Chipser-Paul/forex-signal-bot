# Phase 8B Hybrid Acquisition And Storage

## Status And Scope

This checkpoint defines and verifies a hybrid acquisition plan. It does not
finalize the Phase 8 scientific plan, unlock the proposed holdout, run strategy
performance, or authorize Phase 9. The full 2019-2026 tick export is prohibited.

Development is `[2019-01-01, 2025-01-01)` UTC. Tick calibration consists of the
first Monday-starting UTC week in January, April, July, and October for each
year 2019-2024: 24 blocks selected solely by calendar. The proposed untouched
tick holdout is `[2025-01-01, 2026-08-01)` UTC and remains provisional. The
2026-08-31 sample is outside it and is recorded as prior integrity access.

## Acquisition Audit

The original acquisition path stored monthly gzip JSON Lines and estimated all
history from one 15-minute request. One CLI invocation already reused its MT5
session, but timings did not separate initialization, cold retrieval, warm
retrieval, validation, encoding, write, read, and hash work. Resume trusted a
gzip marker only after byte hash and row verification; there was no portable
content hash or columnar schema. Bars and ticks had no distinct hybrid scopes.

The existing sample manifest resolves most of the 66.75-second ambiguity:

| Stage | Local observation |
| --- | ---: |
| MT5 bounded history retrieval plus normalization | 66.748665 s |
| gzip write and verification | 0.326779 s |

Normalization was included in the first number, so terminal initialization,
server download, cache fill, transfer, and normalization cannot be split after
the fact. Local gzip work was under 0.5% of elapsed time. The old 177-day
projection is therefore rejected as an extrapolation of one cold request.

## Storage Contract

`requirements-data.txt` pins PyArrow for the optional acquisition environment.
The live bot runtime requirements remain unchanged. Tick schema
`phase8b.tick.v1` stores symbol, UTC timestamp, source milliseconds, decimal
prices and volume, flags, sequence identity, row identity, source chunk, and
provenance. Bar schema `phase8b.bar.v1` stores causal UTC times and decimal
OHLCV/spread. Zstandard and dictionary encoding are used.

Partitions are deterministic by symbol, year, month, ISO week, and closed-open
chunk identity. Publication uses a same-directory partial file, durability
flush, atomic replace, and completion marker. Resume verifies schema, format,
compression, row count, first/last/requested timestamps, byte SHA-256, and a
canonical normalized-content SHA-256. Parquet byte identity may change across
library versions; canonical content identity must not.

Weekly chunks are exact UTC intervals with no gaps or overlaps. An inclusive
MT5 endpoint is reduced by one millisecond to preserve the exclusive boundary.
Oversized responses split deterministically until one day; a still-oversized
day fails closed. Empty responses publish zero-row Parquet partitions. A partial
file can never satisfy resume verification.

## Bounded Benchmark Gate

The benchmark plan is one hour, one day, then conditionally one week inside
`[2024-08-05, 2024-08-12)`. The repaired implementation gives each stage an
independent run identity and restricted gateway session, with verified
predecessor requirements for day and week. Each command caps combined output at
1 GiB and requires 15 GiB free before MT5 import, every request, and
serialization.

At the runtime gate, the bot state was `STOPPED`, its recorded PID was inactive,
and C: had 14,046,367,744 bytes free. The 16,106,127,360-byte reserve was not
met. Consequently the one-hour/day/week benchmark made no MT5 request and no
benchmark file. This is a safety result, not a missing-data workaround.

The existing 3,136-row sample was compared in memory only. Its logical JSON was
1,253,750 bytes, gzip was 190,285 bytes, and Parquet/Zstandard was 157,460
bytes. Parquet was 32,825 bytes (17.25%) smaller than gzip. Local Parquet write,
read, and canonical-hash observations were 0.2653 s, 0.1062 s, and 0.4365 s;
peak traced Python allocation was 1,947,833 bytes. These are local observations,
not universal benchmarks.

The later all-in-one benchmark attempt produced no verifiable artifact. Static
diagnosis established that its output directory was created only after MT5
initialization and broad symbol inspection, while failures depended on buffered
console output and returned exit code zero. No evidence remains to identify the
specific runtime failure. The repaired benchmark uses independent hour, day,
and week runs with an external hash-chained journal created before MT5 import,
bounded redacted logs, heartbeats, stage prerequisites, and persisted process
exit status. Only the hour stage is authorized at this checkpoint.

A subsequent supervised hour attempt, run ID
`hour-20260908t171640z-0b371d7d67`, returned zero rows for the requested
development interval after approximately 112 seconds. Its journal proves that
the request completed with an empty response, but the earlier implementation
did not preserve the immediate MT5 numeric status needed to distinguish a
successful empty history response from a gateway or terminal error. It also
allowed worker-side blocking to delay heartbeat evidence. The attempt therefore
does not establish a retention boundary and is not a valid benchmark result.

The hardened `probe-tick-coverage` command now performs counts-only fixed-window
checks under one read-only session, records immediate sanitized MT5 status, and
distinguishes `None`, an empty array, invalid data, and rows. It uses fixed
calendar intervals rather than market outcomes, persists no quotes, and can
authorize one one-hour benchmark in the same session only after four consecutive
15-minute windows establish complete pre-2025 coverage. Probe evidence may
support a later acquisition-plan revision, but this document is not changed
automatically from a runtime result.

## Provisional Capacity Scenarios

The following planning scenarios scale the old 15-minute density and Parquet
ratio. Lower and upper are 0.75x and 1.5x scenarios, not confidence intervals.
They must be replaced by the development-period benchmark after storage exists.

| Dataset | Lower | Baseline | Upper |
| --- | ---: | ---: | ---: |
| XAU development bars | 44.63 MiB | 59.51 MiB | 89.26 MiB |
| Six-constituent DXY bars | 201.26 MiB | 268.34 MiB | 402.51 MiB |
| 24 tick-calibration weeks | 1.27 GiB | 1.69 GiB | 2.53 GiB |
| Continuous proposed holdout ticks | 4.35 GiB | 5.80 GiB | 8.70 GiB |
| Combined | 5.86 GiB | 7.81 GiB | 11.72 GiB |

Temporary working space is provisionally 112.14 MiB per bounded chunk. Adding
the 15 GiB reserve to the upper package requires about 26.83 GiB free before
allowing for licensed news, dated metadata, retries, and filesystem overhead.
Current free space is about 13.08 GiB, a shortfall of at least 13.75 GiB. Modest
C-drive cleanup is not a reliable plan; an external SSD remains recommended.
The original continuous 2019-2026 tick export remains unjustified.

No revised export duration is issued. The only retrieval observation is cold,
and calling it warm throughput would be misleading. A revised duration requires
the blocked one-hour/day/week sequence and must separately include cold cost,
warm throughput, chunk count, compression, verification, and retry allowance.

## Fidelity And Remaining Inputs

Long-term bars assess signal and regime stability but are not tick accurate.
Sampled development ticks characterize execution and cost behavior but do not
replace continuous ticks. Final performance evidence should rely most heavily
on the continuous bid/ask holdout. Reports must keep fidelity strata separate,
and dataset acceptance remains fail closed.

Licensed historical USD high-impact news, commission, historical or
preregistered slippage, rollover timezone, historically effective metadata,
and licensing declarations remain required. No current symbol snapshot is
promoted into historical evidence.

## Next Command

After an external path has at least the reserve plus reviewed estimates, the
next bounded operation is development bars only:

```powershell
python -m backtests.empirical_data_control export-bars --confirm-read-only-demo-export --start 2019-01-01T00:00:00Z --end 2025-01-01T00:00:00Z --chunk-days 7 --bulk-format parquet-zstd --output-root <external-path> --minimum-free-gb 15
```

It was not run. `export-calibration` is a separate later command for only the
24 calendar blocks. No implemented command unlocks holdout strategy evaluation.
