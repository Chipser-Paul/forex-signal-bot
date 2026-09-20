# Phase 8B Stage 1: Guarded Empirical Data Acquisition

## Scope

Stage 1 prepares and, only under safe terminal conditions, runs a read-only
historical export from an already authenticated demo MT5 terminal. It does not
inspect account state, positions, orders, deals, or performance, and it does not
open the final holdout.

Requested coverage is the closed UTC interval
`[2019-01-01T00:00:00Z, 2026-09-01T00:00:00Z)`. Partial server coverage is
recorded as partial coverage and is never converted into a flat period.

## Read-Only Boundary

`bot.acquisition.gateway.ReadOnlyMT5Gateway` exposes only:

- `initialize()` with no arguments, `shutdown()`, redacted `last_error()`, and
  sanitized `version()`.
- `symbol_info()`, `symbol_select()`, and restricted `symbols_get()` discovery.
- `copy_ticks_range()` and `copy_rates_range()`.

The gateway does not expose login, account, position, order, deal-history,
preflight, margin/profit calculation, or mutation functions. The CLI imports
MetaTrader5 only after the explicit confirmation flag and process check pass.
Credential-like environment variables are removed before that import.

Initialization attaches without login, password, server, terminal path, or
account arguments. Failure to obtain the required symbols/history is treated as
terminal unavailable or unauthenticated; the tool does not attempt a login.

## Process Safety

The exporter reads the official dashboard control state and the recorded bot
PID from the original owner worktree. MT5 initialization is permitted only
when the control state is exactly `stopped` and the recorded PID is absent from
the process snapshot. Process command lines and environments are never logged.
An unrelated Python process does not block acquisition after those project
checks and explicit owner confirmation pass. The exporter never changes the
control state or stops or restarts a process.

## Storage

The default raw-data root is:

`C:\Users\chips\forex-signal-bot-data\phase8`

The path validator rejects Git repositories and every registered worktree.
Ticks and bars are deterministic gzip-compressed JSON Lines. Files are first
written as `.partial`, flushed and synchronized, moved into place, hashed, and
then paired with an atomic `.complete.json` marker. Resume trusts only a file
whose marker, size, path, and SHA-256 all match. Existing complete outputs are
never overwritten.

The `sample` command writes one deterministic 15-minute XAUUSDm sample under
`samples/XAUUSDm/`. Acceptance requires the gzip stream, its completion marker,
and a separate sanitized sample manifest to agree on path, row count, size,
hash, symbol, and requested interval. A partial file, missing marker, malformed
stream, hash mismatch, or missing manifest is incomplete. The command does not
overwrite or auto-delete any prior artifact; the owner must inspect and remove
an incomplete sample deliberately before retrying.

XAUUSDm ticks use monthly chunks by default. `estimate` reuses the verified
persisted sample and discovers available history with consecutive D1 probes no
longer than 90 days. Earliest/latest coverage is explicitly a D1 open-time
proxy, not an exact claim about tick-history boundaries. Empty probes increase
uncertainty and never become evidence of a flat market. The estimate reports
calendar duration, observed active D1 dates, sample density, compressed bytes
per row, projected rows and byte range, measured sample acquisition/write
throughput, estimated duration, disk space, 50 GiB budget, safety margin, and a
monthly-or-smaller chunk recommendation. A single 15-minute density sample is
labeled high uncertainty. No multi-year tick response is requested or loaded.

Density units are explicit capacity equivalents: one active hour is 3,600
seconds, one active day is 24 hours, and one active month is 30 active-day
equivalents. These are planning assumptions, not measured broker trading
hours. Projection multiplies the daily equivalent by the number of observed
D1 dates; missing probes remain unknown and block automatic authorization.
The 0.75x to 1.5x byte range is a scenario range, not a confidence interval.
The high estimate reserves room for auxiliary bar streams; free-space reserve
is a further 25% (minimum 1 GiB). Duration includes measured sample acquisition
and serialization throughput; server throttling, history downloads, and future
quote density can change it. D1 coverage never establishes complete tick coverage.

Use `--sample-start` and `--sample-end` to select an explicit UTC interval of
at most one hour within the requested history. For example, a 15-minute window
ending at `2026-08-31T12:15:00Z` avoids an implicit midnight sample. The same
sample arguments must be supplied to `estimate` and a later authorized export.
The raw response is bounded to that one window; writing and verification stream
JSON Lines. Interprocess file locks serialize atomic publication and refusal
to overwrite. `.lock` files contain no sample or account data.

## Symbols And Streams

The only execution quote symbol is exact `XAUUSDm`. Native M5, M15, H1, H4, D1,
and W1 bars are normalized using the Phase 2 candle contract.

Synthetic DXY inputs are read-only. EURUSD, USDJPY, GBPUSD, USDCAD, USDSEK, and
USDCHF mappings require either an exact symbol or one unique broker-suffix
candidate whose base/profit currencies agree. Missing or ambiguous mappings
block the package. M5 and H1 bars are exported for reconstruction and direct
Phase 6 use. Discovery cannot expand the production execution allowlist.

Same-time ticks are retained only with stable unique sequence identities.
Exact duplicate tick payloads are counted. Crossed or zero bid/ask records fail
the chunk. Unexplained gaps are counted; weekend gaps are identified
separately where possible. Empty server responses are recorded explicitly.

## Safe Metadata

The exporter records only XAUUSDm symbol fields needed by Phase 7: digits,
point/tick size and values, contract size, volume bounds/step, stops/freeze
levels, filling/execution modes, currencies, swap fields, and export time.
Login, name, balance, equity, positions, orders, deals, terminal paths, and
credentials are excluded.

Current symbol settings are not treated as historical metadata. Commission,
historical slippage, rollover timezone, and historical effective-date segments
remain `MISSING` until provenance-backed owner evidence is supplied.

## Historical News

`bot.acquisition.news` is an offline normalizer for licensed Trading Economics
exports and, where sufficient, EODHD exports. It retains USD events only,
requires a stable identity, timezone-aware timestamp, known impact, provenance,
retrieval time, and raw-record hash, and deduplicates deterministically.

No provider client or network operation exists in Stage 1. Provider credentials
must later be supplied through a separately authorized secure mechanism, never
through URLs, Git, logs, manifests, or process arguments.

## Corrective Verification

The original sample path only returned a row count; its estimator compressed
an in-memory sample and had no coverage or throughput evidence. Version 2 uses
the completed sample as evidence and separates bounded preflight code into
`bot/acquisition/preflight.py`. Review also found an indirect real MT5 import
through eager backtesting exports; lazy package exports preserve that public
API while ensuring imports, dry runs, and missing confirmation never load MT5.

Reproduce code-only checks with `python -m pytest` and
`python -m tests.phase8b.checkpoint_checks`. Add `--staged` to verify the exact
staged file contents. The latter compiles source, parses JSON/YAML/schemas,
scans changed text without printing candidate secrets, blocks network calls
and real MT5 imports, and checks production order-send confinement.

## Commands

Dry-run never imports or initializes MT5:

```powershell
python -m backtests.empirical_data_control inspect --dry-run
```

Terminal-reading commands require the exact confirmation:

```powershell
python -m backtests.empirical_data_control inspect --confirm-read-only-demo-export
python -m backtests.empirical_data_control sample --confirm-read-only-demo-export
python -m backtests.empirical_data_control estimate --confirm-read-only-demo-export
python -m backtests.empirical_data_control export --confirm-read-only-demo-export
python -m backtests.empirical_data_control resume --confirm-read-only-demo-export
```

Offline verification and packaging do not initialize MT5:

```powershell
python -m backtests.empirical_data_control verify
python -m backtests.empirical_data_control build-package
python -m backtests.empirical_data_control accept-dataset
```

Use `--output-root` and `--maximum-output-gb` to select an external destination
and stricter budget. A partial package remains rejected by Phase 8A until all
coverage, historical news, observed costs, metadata provenance, and licensing
requirements pass.

The guarded preflight sequence is `inspect`, `sample`, then `estimate`. The
`estimate` command never starts `export`; a full export requires a separate,
deliberate invocation after owner review.

## Stage Boundary

Stage 1 may end with a verified tool awaiting safe terminal conditions, a
partial empirical package, or an accepted package ready to finalize the
preregistered plan. It never runs strategy performance, opens the final
holdout, optimizes parameters, authorizes Phase 9, or proves profitability.

## Hybrid Storage Plan

The proposed, not-yet-finalized plan is machine readable at
`baseline/phase8b_hybrid_acquisition_plan.json`. Development evidence is
restricted to `[2019-01-01, 2025-01-01)` UTC. Tick calibration uses the first
Monday-starting seven-day UTC block in January, April, July, and October of
each development year. This yields 24 calendar-selected blocks and makes no
continuous tick-coverage claim.

The provisional untouched tick holdout is `[2025-01-01, 2026-08-01)` UTC.
Acquisition integrity is the only permitted access before the final validation
plan is finalized and hashed; strategy evaluation and performance summaries
remain prohibited. The prior 2026-08-31 sample lies outside that interval and
is retained in the access register. Access records are atomic, idempotent, and
must state `strategy_evaluated: false`.

Bulk data uses the optional dependency in `requirements-data.txt`. Tick schema
`phase8b.tick.v1` stores UTC millisecond timestamps, source milliseconds,
decimal bid/ask/last and volumes, flags, stable sequence/row identities, source
chunk, and provenance. Bar schema `phase8b.bar.v1` stores UTC opening and
availability timestamps, decimal OHLCV/spread, timeframe, sequence, and
provenance. Parquet files use Zstandard, dictionary encoding for repeated
identities, bounded row groups, and deterministic partition paths by symbol,
year, month, ISO week, and closed-open chunk identity.

Every partition is written beside its final destination as `.partial`, flushed,
atomically replaced, and paired with a completion marker. Resume accepts a
partition only after byte SHA-256, canonical normalized-content SHA-256, schema,
row count, timestamps, format, and compression verify. Canonical hashes are
portable across compatible readers; Parquet bytes are not promised identical
across PyArrow/library versions. Empty intervals are valid zero-row Parquet
partitions and therefore cannot disappear from the coverage record.

`--chunk-days 7 --bulk-format parquet-zstd` selects contiguous UTC weekly
chunks. The legacy monthly gzip default remains unchanged until explicit use.
Oversized responses split deterministically into smaller closed-open ranges,
stopping at one day rather than accepting an unbounded allocation. MT5 requests
subtract one millisecond from the exclusive boundary because the source
interface is inclusive; adjacent chunks cannot claim the same millisecond.

The guarded benchmark is stage-specific. `--stage hour` requests exactly
`[2024-08-05T12:00:00Z, 2024-08-05T13:00:00Z)`. The day stage requires a
verified hour run, and the week stage requires a verified day run. Each stage
uses a separate MT5 session and immutable run directory; a failure never grants
permission to a later stage.

Before MT5 import, the parent process creates
`benchmarks/development-20240805-20240812/runs/<stage>/<run-id>` and prints the
run ID and journal path. `run_journal.jsonl` is append-only, flushed and
`fsync`-synchronized, file-locked, sequence-numbered, and SHA-256 chained.
`run_state.json` is atomically replaced after each transition. Child stdout and
stderr are unbuffered and captured in separately bounded, redacted, rotating
logs. Console truncation therefore cannot remove the authoritative state.

The supervisor process emits and `fsync`s heartbeats every 15 seconds while it
polls the worker. Heartbeats therefore continue even when an MT5 C-extension
call prevents the worker interpreter from scheduling a thread. Reader threads
consume child stdout and stderr without blocking supervision, and both bounded
files are created before child launch, including when they remain empty. Worker
and supervisor identities and exit codes are recorded separately inside the
journal but are not printed with unrelated process information. Import,
initialization, request, processing, and verification have independent limits;
the complete stage has a 20-minute ceiling. Timeout first interrupts the
dedicated child process group so its `finally` block can shut down the gateway.
Only that child may then be terminated if it does not exit during the grace
period. Every escalation is journaled. MT5, Streamlit, Codex, owner processes,
and unrelated Python processes are never termination targets.

The former all-in-one command could exit before constructing its store because
store creation followed MT5 initialization and broad symbol inspection. Its
only diagnostic was buffered stdout, and blocked outcomes returned exit code
zero. Those are verified design causes of the missing evidence; the exact
runtime cause of the previous attempt remains unknown because no durable
journal existed. The new hour benchmark checks exact `XAUUSDm` only and records
every transition. It separately times initialization, retrieval, normalization,
gzip and Parquet writes, validation, hashes, and read-back. Python allocation
peak is labeled as such and is not a whole-process memory claim. The 1 GiB
combined cap and 15 GiB reserve remain mandatory.

The 2026-08-31 sample took 66.748665 seconds to acquire and 0.326779 seconds to
normalize, compress, write, and verify. That isolates a cold terminal,
server-history-download, or cache-fill cost but cannot divide those server-side
components further. Local gzip work was not the bottleneck. The earlier 177-day
extrapolation is retained only as a rejected single-cold-request projection.

Long-term bars remain bar-level evidence. Sampled development ticks characterize
execution costs but do not replace continuous ticks. Final empirical execution
evidence should rely most heavily on continuous bid/ask holdout ticks, while
bars assess signal/regime stability. Fidelity classes must remain separate and
no acceptance threshold may be loosened because less data was acquired.
Licensed historical USD news, commission, historical or preregistered slippage,
rollover timezone, effective metadata periods, and licensing remain fail-closed
owner inputs.

After storage and owner authorization, the recommended development-bar command
is:

```powershell
python -m backtests.empirical_data_control export-bars --confirm-read-only-demo-export --start 2019-01-01T00:00:00Z --end 2025-01-01T00:00:00Z --chunk-days 7 --bulk-format parquet-zstd --output-root <external-path> --minimum-free-gb 15
```

This command is documentation only and was not run. `export-calibration` uses
the same exact interval and storage flags but requests only the 24
preregistered blocks. No command unlocks or evaluates the proposed holdout.

## Observable Benchmark Commands

The only currently authorized empirical command is the hour stage:

```powershell
python -u -m backtests.empirical_data_control benchmark --stage hour --confirm-read-only-demo-export --owner-worktree C:\Users\chips\forex-signal-bot --output-root C:\Users\chips\forex-signal-bot-data\phase8 --minimum-free-gb 15 --maximum-output-gb 1
```

Review an existing completed run without reacquiring data by adding
`--resume-run-id <run-id>`. Resume verifies the journal, schemas, completion
markers, byte hashes, row counts, and cross-format canonical content. An
incomplete run is blocked for manual review and is never acquired again under
the old identity. A new attempt always receives a new run ID.

The day and week stages are implemented but are not authorized by the current
checkpoint. Their prerequisites are validated before MT5 import.

## Tick Coverage Probe

`probe-tick-coverage` is a counts-only diagnostic command. It initializes the
read-only gateway once, requests only exact `XAUUSDm` 15-minute windows, and
persists no raw quotes. It first requests the fixed 2026-08-31 positive control,
the fixed 2024-08-05 target control, and a corresponding M5 bar control. If the
recent control succeeds while the old tick control is empty, it probes a fixed
Tuesday-noon quarterly sequence and then first-Tuesday monthly boundaries. It
stops at 30 tick requests, 10 bar requests, or 30 minutes.

Every request records its closed-open UTC interval, response shape (`NONE`,
`EMPTY_ARRAY`, `ROWS`, or `INVALID`), count, elapsed time, MT5 numeric error
code, sanitized category, and a hash of the redacted description. `None` and a
successful empty array remain distinct. The result and completion marker are
atomically written under
`probes/development-20240805-20240812/runs/coverage/<run-id>` and verified by
SHA-256. Probe files contain counts and provenance only.

A conditional benchmark may run in the same initialized worker only when four
consecutive 15-minute windows establish a complete hour before 2025-01-01,
availability is monotonic, and every safety gate remains valid. The selected
hour is calendar-driven, never price-driven. No day or week action is reachable
from the probe command. Counts-only checks may characterize dates in the
provisional holdout, but they export no raw data and never evaluate strategy or
performance; the holdout lock remains closed.
