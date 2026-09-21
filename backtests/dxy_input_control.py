"""Phase 8D control CLI: causal 2024 DXY development input.

Commands:
    acquire  — one bounded read-only MT5 session (supervised child process),
               publishing the verified DXY package atomically afterwards.
    verify   — complete read-only re-verification of the existing package.
    register — idempotent discovery/readiness registration of the package.

The acquire path runs the MT5 worker in a supervised child process using the
existing supervisor protocol (heartbeats, step timeouts, bounded logs) and
strips credential-bearing environment variables before the MT5 import.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.acquisition.dxy_package import (  # noqa: E402
    publish_dxy_package,
    resolve_code_fingerprint,
    resolve_git_commit,
    verify_package_readonly,
)
from bot.acquisition.models import AcquisitionError  # noqa: E402
from bot.acquisition.storage import validate_output_root  # noqa: E402
from bot.validation.models import canonical_data  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 8D causal DXY development input")
    parser.add_argument("command", choices=("acquire", "verify", "register"))
    parser.add_argument("--output-root", type=Path, default=Path(r"C:\Users\chips\forex-signal-bot-data\phase8"))
    parser.add_argument("--owner-worktree", type=Path, default=Path(r"C:\Users\chips\forex-signal-bot"))
    parser.add_argument("--minimum-free-gb", type=float, default=15.0)
    parser.add_argument("--confirm-read-only-demo-export", action="store_true")
    parser.add_argument("--package-root", type=Path, help="Explicit package for verify/register")
    return parser


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise AcquisitionError("CLI timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def _safe_result(status: str, *, exit_code: int = 0, **details: object) -> int:
    payload = {"status": status, **details}
    print(
        json.dumps(canonical_data(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        flush=True,
    )
    return int(exit_code)


def _existing_storage_path(path: Path) -> Path:
    candidate = Path(path).resolve(strict=False)
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return candidate


# Worker subprocess protocol -------------------------------------------------

def _acquire_worker() -> int:
    """Child process: the single bounded read-only MT5 session."""
    from bot.acquisition.dxy_acquisition import run_dxy_acquisition
    from bot.acquisition.journal import BenchmarkJournal, stable_error_category
    from bot.acquisition.safety import scrub_current_environment

    scrub_current_environment()
    payload = json.loads(os.environ["DXY_ACQUIRE_PAYLOAD"])
    output_root = Path(payload["output_root"])
    owner_worktree = Path(payload["owner_worktree"])
    run_dir = Path(payload["run_dir"])
    journal = BenchmarkJournal.open(run_dir)
    try:
        evidence = run_dxy_acquisition(
            output_root,
            owner_worktree,
            journal,
            minimum_free_gb=float(payload["minimum_free_gb"]),
            confirm_read_only_demo_export=bool(payload["confirm_read_only_demo_export"]),
        )
    except Exception as exc:
        import traceback

        traceback.print_exc()
        journal.append(
            "RUN_FAILED",
            status="FAILED",
            error_category=stable_error_category(exc),
            exit_status=2,
        )
        return 2
    from bot.acquisition.dxy_contracts import (
        canonical_constituent_hash,
        compute_gap_report,
        iso_z,
    )

    summary = {
        "resolved_mappings": evidence["resolved_mappings"],
        "constituent_row_counts": {
            symbol: len(records) for symbol, records in evidence["records_by_symbol"].items()
        },
        "constituent_canonical_hashes": {
            symbol: canonical_constituent_hash(records)
            for symbol, records in evidence["records_by_symbol"].items()
        },
        "gap_reports": {
            symbol: compute_gap_report(records)
            for symbol, records in evidence["records_by_symbol"].items()
        },
        "coverage": {
            symbol: {
                "first_open": iso_z(int(records[0]["open_time_ms"])),
                "last_open": iso_z(int(records[-1]["open_time_ms"])),
            }
            for symbol, records in evidence["records_by_symbol"].items()
            if records
        },
        "diagnostics_by_symbol": evidence["diagnostics_by_symbol"],
        "terminal_build": evidence["terminal_build"],
        "error_summary": evidence["error_summary"],
        "chunk_count": evidence["chunk_count"],
        "initialization_seconds": evidence["initialization_seconds"],
    }
    from bot.acquisition.storage import atomic_json

    atomic_json(run_dir / "acquisition_summary.json", summary)
    # Records are handed to the parent via a JSON sidecar (bounded size:
    # ~317k rows total, ~30 MiB raw JSON).  The parent publishes the package.
    import gzip

    records_payload = json.dumps(
        canonical_data(
            {
                symbol: [canonical_data(dict(record)) for record in records]
                for symbol, records in evidence["records_by_symbol"].items()
            }
        ),
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    compressed = gzip.compress(records_payload.encode("utf-8"), compresslevel=6)
    (run_dir / "acquisition_records.json.gz").write_bytes(compressed)
    journal.append("RUN_COMPLETED", status="PASSED", exit_status=0)
    return 0


def _supervised_acquisition(args: argparse.Namespace) -> dict:
    from bot.acquisition.journal import BenchmarkJournal, JOURNAL_SCHEMA_VERSION

    output_root = validate_output_root(args.output_root, forbidden_roots=())
    run_id = f"dxy-{datetime.now(UTC):%Y%m%dt%H%M%S}z-{uuid.uuid4().hex[:10]}"
    journal_root = output_root / "dxy" / "journals"
    journal_root.mkdir(parents=True, exist_ok=True)
    run_dir = journal_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "run_id": run_id,
        "benchmark_stage": "hour",
        "created_at": datetime.now(UTC),
        "started_monotonic": time.monotonic(),
    }
    from bot.acquisition.storage import atomic_json

    atomic_json(run_dir / "run_metadata.json", metadata)
    journal = BenchmarkJournal(run_dir, canonical_data(metadata))
    journal.append("RUN_PREPARED", status="PREPARED")

    payload = {
        "output_root": str(output_root),
        "owner_worktree": str(args.owner_worktree),
        "minimum_free_gb": float(args.minimum_free_gb),
        "confirm_read_only_demo_export": bool(args.confirm_read_only_demo_export),
        "run_dir": str(run_dir),
    }
    from bot.acquisition.safety import strip_sensitive_environment

    environment = strip_sensitive_environment()
    environment["DXY_ACQUIRE_PAYLOAD"] = json.dumps(payload)

    command = [
        sys.executable,
        str(REPO_ROOT / "backtests" / "dxy_input_control.py"),
        "--_dxy-worker",
    ]
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        env=environment,
        input=None,
        capture_output=True,
        text=True,
        timeout=3600,
        creationflags=creation_flags,
    )
    journal.append(
        "WORKER_EXIT_RECORDED",
        status="RECORDED",
        exit_status=completed.returncode,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "")[-500:]
        raise AcquisitionError(f"DXY_ACQUISITION_WORKER_FAILED: {tail}")
    journal.append("RUN_COMPLETED", status="PASSED", exit_status=0)
    records_path = run_dir / "acquisition_records.json.gz"
    if not records_path.is_file():
        raise AcquisitionError("DXY_ACQUISITION_RECORDS_MISSING")
    import gzip

    records = json.loads(gzip.decompress(records_path.read_bytes()).decode("utf-8"))
    return {"run_dir": run_dir, "records_by_symbol": records, "journal": journal}


def _dxy_worker_entry() -> int:
    return _acquire_worker()


def main(argv: list[str] | None = None) -> int:
    if argv is None and "--_dxy-worker" in sys.argv[1:]:
        return _dxy_worker_entry()
    parser = _parser()
    args, unknown = parser.parse_known_args(argv)
    if "--_dxy-worker" in (unknown or []):
        return _dxy_worker_entry()

    if args.command == "acquire":
        if not args.confirm_read_only_demo_export:
            print("Refusing to start MT5 without --confirm-read-only-demo-export", file=sys.stderr)
            return 2
        session = _supervised_acquisition(args)
        journal = session["journal"]
        records_by_symbol = session["records_by_symbol"]
        from bot.acquisition.dxy_contracts import (
            DXY_SYMBOL_MAP,
            iso_z,
        )

        evidence_summary = json.loads(
            (session["run_dir"] / "acquisition_summary.json").read_text(encoding="utf-8")
        )
        retrieved_utc = datetime.now(UTC)
        implementation_commit = resolve_git_commit(REPO_ROOT)
        code_fingerprint = resolve_code_fingerprint(REPO_ROOT)
        source = _source_year_identity(args.output_root)
        package_root, verified = publish_dxy_package(
            args.output_root,
            records_by_symbol={
                symbol: records_by_symbol[symbol] for symbol in DXY_SYMBOL_MAP
            },
            resolved_mappings=evidence_summary["resolved_mappings"],
            acquisition_evidence={
                "permitted_operations": (
                    "initialize", "shutdown", "version", "last_error",
                    "symbol_info", "symbol_select", "symbols_get", "copy_rates_range",
                ),
                "run_id": session["run_dir"].name,
                "journal_relative_path": str(
                    session["run_dir"].relative_to(args.output_root) / "run_journal.jsonl"
                ),
                "terminal_build": evidence_summary["terminal_build"],
                "error_category": evidence_summary["error_summary"]["category"],
                "initialization_seconds": evidence_summary["initialization_seconds"],
                "chunk_count": evidence_summary["chunk_count"],
            },
            source_year_package_id=source["year_package_id"],
            source_year_canonical_sha256=source["source_canonical_sha256"],
            source_year_row_count=int(source["source_row_count"]),
            retrieved_utc=retrieved_utc,
            terminal_build=evidence_summary["terminal_build"],
            implementation_commit=implementation_commit,
            code_fingerprint=code_fingerprint,
            minimum_free_bytes=int(args.minimum_free_gb * 1024**3),
            worktree_root=REPO_ROOT,
        )
        return _safe_result(
            "DXY_PACKAGE_PUBLISHED",
            exit_code=0,
            package_id=verified["package_id"],
            package_root=str(package_root),
            total_constituent_rows=verified["total_constituent_rows"],
            total_dxy_rows=verified["total_dxy_rows"],
        )

    if args.command == "verify":
        root = args.package_root
        if root is None:
            from bot.acquisition.dxy_package import _discover_existing_package

            root = _discover_existing_package(
                validate_output_root(args.output_root, forbidden_roots=())
            )
            if root is None:
                raise AcquisitionError("DXY_PACKAGE_MISSING")
        verified = verify_package_readonly(root)
        return _safe_result(
            "DXY_PACKAGE_VERIFIED",
            package_id=verified["package_id"],
            total_constituent_rows=verified["total_constituent_rows"],
            total_dxy_rows=verified["total_dxy_rows"],
            implementation_commit=verified["implementation_commit"],
            code_fingerprint=verified["code_fingerprint"],
        )

    if args.command == "register":
        from bot.acquisition.dxy_discovery import load_dxy_discovery_record, register_dxy_package

        output_root = validate_output_root(args.output_root, forbidden_roots=())
        discovery_root = output_root / "derived" / "discovery"
        record, identity = register_dxy_package(
            output_root,
            discovery_root,
            package_root=args.package_root,
        )
        return _safe_result(
            "DXY_DISCOVERY_REGISTERED",
            package_id=identity.package_id,
            discovery_sha256=identity.discovery_sha256,
            discovery_physical_sha256=identity.discovery_physical_sha256,
            discovery_root=str(discovery_root),
        )
    return 2


def _source_year_identity(output_root: Path) -> dict:
    """Read the verified year-package identity from the Phase 8C manifest."""
    derived_root = output_root / "derived"
    candidates = sorted(
        item for item in derived_root.iterdir()
        if item.is_dir() and item.name.startswith("derived-candles-2024-")
    )
    if not candidates:
        raise AcquisitionError("DXY_SOURCE_YEAR_PACKAGE_MANIFEST_MISSING")
    if len(candidates) > 1:
        raise AcquisitionError("DXY_SOURCE_YEAR_PACKAGE_AMBIGUOUS")
    manifest_path = candidates[0] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "year_package_id": str(manifest["year_package_id"]),
        "source_canonical_sha256": str(manifest["source_canonical_sha256"]),
        "source_row_count": int(manifest["source_row_count"]),
    }


if __name__ == "__main__":
    raise SystemExit(main())
