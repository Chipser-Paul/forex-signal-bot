# Phase 8B Offline Dataset Verifier

## Purpose and separation

`bot.acquisition.offline_verifier` is a read-only, Parquet-only verification
protocol. It deliberately does not reuse the MT5 benchmark supervisor or its
stage vocabulary: benchmark acquisition has terminal/session semantics while a
logical file scan needs a separate, inspectable evidence trail. The verifier
does not import MetaTrader5, the MT5 gateway, broker code, strategy code,
network providers, or credential loaders.

This implementation was built and tested only with temporary synthetic Parquet
fixtures. It did not read, rebuild, activate, quarantine, or otherwise access
December or any other Phase 8 market-data artifact. Recovery is a separately
authorized operation.

## Request contract

`VerificationRequest` uses protocol version
`phase8b.offline-parquet-verifier.v1`. It requires an absolute Parquet input
path, distinct absolute output directory, run ID, expected physical and
canonical logical SHA-256 values, schema identity, exact symbol, closed
`YYYY-MM` period, expected row count, bounded batch size, positive stage and
overall deadlines, and a non-secret code fingerprint. ZIP/CSV input, path
overlap, unsupported schema/symbol, invalid hashes, unsafe batch sizes, and
invalid timeouts are rejected before a child starts.

## Worker and evidence

The child hashes the input, reads it through bounded Parquet record batches,
checks the Phase 8B normalized schema, recomputes the existing canonical
logical hash, validates symbol/period/order/quotes, counts duplicates and
timestamp conflicts, then rehashes and re-identifies the input. It never
materializes the entire Parquet file or writes input data. It creates exactly
one atomic `terminal-result.json` and completion marker; a valid result links
to the terminal hash of `worker.journal.jsonl`.

Worker journal events are hash chained with stable sequence numbers, UTC and
monotonic timestamps, fsync-backed append, bounded payloads, and no market
rows. Its vocabulary is specific to the verifier: `RUN_PREPARED`,
`REQUEST_VALIDATED`, physical hash, scan/batch, post-scan hash, and terminal
publication events. The supervisor has its own hash-chained journal for child
start/exit, independent heartbeats, and final outcome.

## Supervision, resume, and outcomes

The parent starts only `python -m bot.acquisition.offline_verifier --child`.
It passes a credential-filtered environment, uses monotonic stage and overall
deadlines, records a durable initial heartbeat synchronously after
`CHILD_STARTED`, then emits supervisor heartbeats every 15 seconds in
production. The initial record is intentionally independent of child progress,
output, or lifetime; a launch failure records `CHILD_LAUNCH_FAILED` and does
not fabricate one. Stdout/stderr are bounded at 64 KiB and only the owned child
is terminated on timeout. A zero child exit code is insufficient: the parent
validates result schema, checksum, run ID, request hash, status, and
worker-journal linkage before publishing an atomic supervisor summary.

A completed `VERIFIED` run with the same immutable request is returned
idempotently. A changed expected file identity, malformed/partial result,
broken journal, or nonempty prior run directory is rejected; interrupted work
is evidence, not a resumable partial hash. A new full scan must use a new run
directory.

Stable terminal statuses include `VERIFIED`, physical/logical/schema/symbol/
period/row-count/order failures, `CHILD_CRASHED`, `TIMED_OUT`, and
result-integrity failures. The child emits no tick rows in logs.

## CLI

The local-only command is:

```powershell
python -m backtests.offline_dataset_control verify-parquet --run-id <new-run-id> --parquet <absolute-parquet-path> --expected-physical-sha256 <sha256> --expected-logical-sha256 <sha256> --period 2024-12 --expected-row-count <count> --output-directory <new-empty-absolute-run-directory> --code-fingerprint <approved-code-fingerprint>
```

It neither recovers nor activates a package, accesses `.env`, starts MT5, or
runs strategy code. The proposed command for the separately authorized
December `recovery-v2` task is the same command only after that task supplies
the approved *new* package path, run ID, physical identity, logical identity,
row count, and output directory. This task intentionally does not provide or
execute those values.
