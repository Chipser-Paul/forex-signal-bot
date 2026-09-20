"""Narrow local-only command for read-only offline Parquet verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.acquisition.offline_verifier import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_OVERALL_TIMEOUT_SECONDS,
    DEFAULT_STAGE_TIMEOUT_SECONDS,
    PROTOCOL_VERSION,
    VerificationRequest,
    supervise_verification,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="offline-dataset-control")
    command = parser.add_subparsers(dest="command", required=True)
    verify = command.add_parser("verify-parquet")
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--parquet", required=True, type=Path)
    verify.add_argument("--expected-physical-sha256", required=True)
    verify.add_argument("--expected-logical-sha256", required=True)
    verify.add_argument("--schema", default="phase8b.exness-tick.v1")
    verify.add_argument("--symbol", default="XAUUSDm")
    verify.add_argument("--period", required=True)
    verify.add_argument("--expected-row-count", required=True, type=int)
    verify.add_argument("--output-directory", required=True, type=Path)
    verify.add_argument("--code-fingerprint", required=True)
    verify.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    verify.add_argument("--stage-timeout-seconds", type=float, default=DEFAULT_STAGE_TIMEOUT_SECONDS)
    verify.add_argument("--overall-timeout-seconds", type=float, default=DEFAULT_OVERALL_TIMEOUT_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    request = VerificationRequest(
        protocol_version=PROTOCOL_VERSION,
        run_id=args.run_id,
        parquet_path=str(args.parquet),
        expected_physical_sha256=args.expected_physical_sha256,
        expected_logical_sha256=args.expected_logical_sha256,
        expected_schema_identity=args.schema,
        expected_symbol=args.symbol,
        expected_period=args.period,
        expected_row_count=args.expected_row_count,
        batch_size=args.batch_size,
        stage_timeout_seconds=args.stage_timeout_seconds,
        overall_timeout_seconds=args.overall_timeout_seconds,
        output_directory=str(args.output_directory),
        code_fingerprint=args.code_fingerprint,
    )
    summary = supervise_verification(request)
    print(json.dumps({key: summary.get(key) for key in ("run_id", "status", "reason_code", "idempotent")}, sort_keys=True))
    return 0 if summary["status"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
