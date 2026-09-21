# Phase 8B Stage 1 Progress

- Parent commit: `0a5388f9e926029c83737b3956a58e9a36d4602c`
- Branch: `phase/8-scientific-validation`
- Objective: verify a storage-efficient hybrid acquisition plan without running the 2019-2026 export or opening the proposed holdout.
- Completed: added the proposed development/calibration/holdout contract; deterministic quarterly calibration weeks; UTC day chunking; optional Parquet/Zstandard tick and bar schemas; canonical content hashes; atomic partition publication; resume verification; explicit empty partitions; bounded fallback splitting; Phase 7/8 readers; one-session benchmark orchestration; access logging; disk/output guards; and separate cold/warm/storage timings.
- Current changes: acquisition models, planning, exporter, columnar stores, benchmark orchestration, CLI, package/validation readers, optional data dependency, tests, and documentation.
- Tests executed: hybrid-focused tests `65 passed`; Phase 8/known-defect tests `123 passed`; full suite `602 passed, 1 expected skip, 10 subtests passed`; `pip check` clean; checkpoint compilation/import/parsing/confinement checks clean.
- Current failures: none.
- Incomplete work: stage explicitly; run staged checks; commit locally; verify the detached exact snapshot.
- Decisions: gzip JSONL remains diagnostic/interchange only; Parquet/Zstandard is preferred bulk storage; monthly gzip remains the default until explicit `--chunk-days 7 --bulk-format parquet-zstd`; calibration blocks are the first Monday-starting week of January/April/July/October in each development year; the proposed 2025-01-01 to 2026-08-01 tick holdout remains locked and provisional.
- Timing audit: the prior sample recorded 66.748665 seconds acquisition versus 0.326779 seconds normalization/compression/write. The cold MT5/server-history request dominates; the 177-day projection is not accepted as a warm-throughput estimate.
- Last verified safe state: official state `STOPPED`, recorded PID inactive; C: free space `14,046,367,744` bytes is below the `16,106,127,360`-byte reserve, so the guarded benchmark returned `INSUFFICIENT_DISK` before MT5 import. Code tests used fake MT5 and no network; the prior sample remains outside the proposed holdout; no full export or strategy evaluation occurred.
- Next exact action: explicit staging, staged scan/test, local commit, detached verification.
- Commit status: no new commit yet; intended local subject is `perf: optimize empirical export storage and scope`.
