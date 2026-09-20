from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from bot.acquisition.models import AcquisitionError, ExportConfig, ExportStatus
from bot.acquisition.safety import (
    assess_project_control_safety,
    scrub_current_environment,
    strip_sensitive_environment,
    windows_process_snapshot,
)
from bot.acquisition.storage import validate_output_root
from bot.validation.models import canonical_data


UTC = timezone.utc
REPO_ROOT = Path(__file__).resolve().parents[1]
MT5_COMMANDS = frozenset({
    "inspect", "sample", "estimate", "benchmark", "export-bars",
    "export-calibration", "export", "resume", "probe-tick-coverage",
})
BENCHMARK_MAXIMUM_BYTES = 1024**3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guarded read-only Phase 8B empirical-data acquisition")
    parser.add_argument(
        "command",
        choices=(
            "inspect", "sample", "estimate", "benchmark", "export-bars",
            "export-calibration", "export", "resume", "verify", "show-plan",
            "build-package", "accept-dataset", "probe-tick-coverage",
        ),
    )
    parser.add_argument("--output-root", type=Path, default=Path(r"C:\Users\chips\forex-signal-bot-data\phase8"))
    parser.add_argument("--owner-worktree", type=Path, default=Path(r"C:\Users\chips\forex-signal-bot"))
    parser.add_argument("--start", default="2019-01-01T00:00:00Z")
    parser.add_argument("--end", default="2026-09-01T00:00:00Z")
    parser.add_argument("--sample-start", help="UTC start of a bounded sample, at most one hour")
    parser.add_argument("--sample-end", help="UTC end (exclusive) of the same sample")
    parser.add_argument("--maximum-output-gb", type=float, default=50.0)
    parser.add_argument("--minimum-free-gb", type=float, default=15.0)
    parser.add_argument("--chunk-days", type=int)
    parser.add_argument("--bulk-format", choices=("gzip-jsonl", "parquet-zstd"), default="gzip-jsonl")
    parser.add_argument("--maximum-rows-per-tick-chunk", type=int, default=5_000_000)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--license-or-restrictions", default="OWNER_REVIEW_REQUIRED")
    parser.add_argument("--confirm-read-only-demo-export", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stage", choices=("hour", "day", "week"))
    parser.add_argument("--resume-run-id")
    parser.add_argument("--_benchmark-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_coverage-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_benchmark-run-id", help=argparse.SUPPRESS)
    return parser


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise AcquisitionError("CLI timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def _git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
        env=strip_sensitive_environment(),
    )
    return completed.stdout.strip()


def _worktree_roots() -> tuple[Path, ...]:
    return tuple(
        Path(line.removeprefix("worktree ").strip())
        for line in _git_output("worktree", "list", "--porcelain").splitlines()
        if line.startswith("worktree ")
    )


def _existing_storage_path(path: Path) -> Path:
    candidate = Path(path).resolve(strict=False)
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return candidate


def _safe_result(status: str, *, exit_code: int = 0, **details: object) -> int:
    payload = {"status": status, **details}
    print(
        json.dumps(canonical_data(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        flush=True,
    )
    return int(exit_code)


def _config(args: argparse.Namespace) -> ExportConfig:
    root = validate_output_root(args.output_root, forbidden_roots=_worktree_roots())
    return ExportConfig(
        output_root=root,
        start=_utc(args.start),
        end=_utc(args.end),
        maximum_output_bytes=int(args.maximum_output_gb * 1024**3),
        minimum_free_bytes=int(args.minimum_free_gb * 1024**3),
        tick_chunk_days=args.chunk_days,
        bulk_format=args.bulk_format,
        maximum_rows_per_tick_chunk=args.maximum_rows_per_tick_chunk,
    )


def _offline_command(args: argparse.Namespace, config: ExportConfig) -> int:
    if args.command == "show-plan":
        from bot.acquisition.plan import plan_payload

        return _safe_result("HYBRID_PLAN_PROPOSED", plan=plan_payload())
    if args.command == "verify":
        from bot.acquisition.columnar import ParquetBarStore, ParquetTickStore
        from bot.acquisition.storage import ChunkStore

        markers = sorted(config.output_root.rglob("*.complete.json"))
        verified = []
        for marker in markers:
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
            if marker.name == "probe.complete.json":
                from bot.acquisition.coverage_probe import verify_coverage_probe

                verified.append(verify_coverage_probe(marker.parent))
                continue
            if marker.name == "stage.complete.json":
                from bot.acquisition.benchmark import verify_stage_run

                verified.append(verify_stage_run(marker.parent))
                continue
            relative = str(marker_payload["relative_path"])
            final_path = Path(str(marker).removesuffix(".complete.json"))
            relative_parts = Path(relative).parts
            if not relative_parts or final_path.name != relative_parts[-1]:
                raise AcquisitionError("completion marker path is incompatible")
            store_root = final_path.parents[len(relative_parts) - 1]
            if relative.endswith(".parquet"):
                store = (
                    ParquetTickStore(store_root, maximum_output_bytes=config.maximum_output_bytes)
                    if marker_payload.get("schema_version") == "phase8b.tick.v1"
                    else ParquetBarStore(store_root, maximum_output_bytes=config.maximum_output_bytes)
                )
            else:
                store = ChunkStore(store_root, maximum_output_bytes=config.maximum_output_bytes)
            verified.append(store.verify(relative))
        return _safe_result("EXPORT_VERIFIED", chunk_count=len(verified))
    if args.command == "build-package":
        from bot.acquisition.package import build_partial_package

        path = build_partial_package(
            config,
            created_at=datetime.now(UTC),
            license_or_restrictions=args.license_or_restrictions,
        )
        return _safe_result("PARTIAL_EMPIRICAL_PACKAGE_CREATED", manifest_name=path.name)
    if args.command == "accept-dataset":
        from bot.validation.datasets import (
            load_empirical_package_manifest,
            validate_dataset_package,
            write_acceptance_report,
        )

        manifest_path = args.manifest or config.output_root / "package" / "empirical_data_package.json"
        report_path = args.report or config.output_root / "package" / "dataset_acceptance.json"
        manifest = load_empirical_package_manifest(manifest_path)
        report = validate_dataset_package(manifest, config.output_root, checked_at=datetime.now(UTC))
        write_acceptance_report(report_path, report)
        return _safe_result(report.outcome.value, issue_count=len(report.issues))
    raise AcquisitionError("unsupported offline command")


def _benchmark_run_dir(output_root: Path, stage: str, run_id: str) -> Path:
    family = "probes" if stage == "coverage" else "benchmarks"
    return (
        Path(output_root)
        / family
        / "development-20240805-20240812"
        / "runs"
        / stage
        / run_id
    )


def _shutdown_gateway(journal, gateway) -> BaseException | None:
    journal.append("MT5_SHUTDOWN_STARTED", status="RUNNING")
    if gateway is None or not gateway.is_initialized:
        journal.append("MT5_SHUTDOWN_COMPLETED", status="ALREADY_DISCONNECTED")
        return None
    try:
        gateway.shutdown()
    except Exception as exc:
        journal.append(
            "MT5_SHUTDOWN_COMPLETED",
            status="FAILED",
            error_category="MT5_SHUTDOWN_FAILED",
        )
        return exc
    journal.append("MT5_SHUTDOWN_COMPLETED", status="SUCCEEDED")
    return None


def _benchmark_worker(args: argparse.Namespace) -> int:
    from bot.acquisition.benchmark import AcquisitionBenchmark, BENCHMARK_MAX_BYTES
    from bot.acquisition.gateway import ReadOnlyMT5Gateway
    from bot.acquisition.journal import BenchmarkJournal, stable_error_category

    if not args.stage or not args._benchmark_run_id:
        return 2
    output_root = validate_output_root(args.output_root, forbidden_roots=())
    run_dir = _benchmark_run_dir(output_root, args.stage, args._benchmark_run_id)
    journal = BenchmarkJournal.open(run_dir)
    gateway: ReadOnlyMT5Gateway | None = None
    result: dict[str, object] | None = None
    failure: BaseException | None = None
    interrupted = False
    try:
        project_safety = assess_project_control_safety(args.owner_worktree, windows_process_snapshot())
        if not project_safety.safe:
            raise AcquisitionError("project safety changed before MT5 import")
        if shutil.disk_usage(_existing_storage_path(output_root)).free <= int(args.minimum_free_gb * 1024**3):
            raise AcquisitionError("benchmark blocked by the disk safety reserve")
        journal.append("MT5_IMPORT_STARTED", status="RUNNING")
        mt5 = importlib.import_module("MetaTrader5")
        journal.append("MT5_IMPORT_COMPLETED", status="PASSED")
        gateway = ReadOnlyMT5Gateway(mt5)
        journal.append("MT5_INITIALIZE_STARTED", status="RUNNING")
        initialization_started = time.perf_counter()
        gateway.initialize(confirmed_read_only_demo_export=True)
        initialization_seconds = max(time.perf_counter() - initialization_started, 1e-9)
        journal.append("MT5_INITIALIZED", status="PASSED")
        metadata = gateway.symbol_info("XAUUSDm")
        if metadata is None or metadata.get("name") != "XAUUSDm":
            raise AcquisitionError("exact benchmark symbol is unavailable")
        result = AcquisitionBenchmark(
            gateway,
            output_root,
            stage=args.stage,
            journal=journal,
            symbol_point=float(metadata.get("point", 0)),
            minimum_free_bytes=int(args.minimum_free_gb * 1024**3),
            maximum_output_bytes=min(int(args.maximum_output_gb * 1024**3), BENCHMARK_MAX_BYTES),
        ).run(initialization_seconds=initialization_seconds)
    except KeyboardInterrupt as exc:
        interrupted = True
        failure = exc
    except Exception as exc:
        failure = exc
    finally:
        shutdown_failure = _shutdown_gateway(journal, gateway)
        if failure is None:
            failure = shutdown_failure
    if failure is not None:
        event = "RUN_INTERRUPTED" if interrupted else "RUN_FAILED"
        journal.append(
            event,
            status="INTERRUPTED" if interrupted else "FAILED",
            error_category=stable_error_category(failure),
            exit_status=130 if interrupted else 2,
        )
        return 130 if interrupted else 2
    journal.append("RUN_COMPLETED", status="PASSED", exit_status=0)
    return _safe_result(
        "BOUNDED_BENCHMARK_STAGE_COMPLETE",
        run_id=journal.run_id,
        journal_path=str(journal.journal_path),
        benchmark=result,
    )


def _coverage_worker(args: argparse.Namespace) -> int:
    from bot.acquisition.benchmark import AcquisitionBenchmark, BENCHMARK_MAX_BYTES
    from bot.acquisition.coverage_probe import TickCoverageProbe
    from bot.acquisition.gateway import ReadOnlyMT5Gateway
    from bot.acquisition.journal import BenchmarkJournal, stable_error_category

    if not args._benchmark_run_id:
        return 2
    output_root = validate_output_root(args.output_root, forbidden_roots=())
    run_dir = _benchmark_run_dir(output_root, "coverage", args._benchmark_run_id)
    journal = BenchmarkJournal.open(run_dir)
    gateway: ReadOnlyMT5Gateway | None = None
    probe_result: dict[str, object] | None = None
    benchmark_result: dict[str, object] | None = None
    failure: BaseException | None = None
    interrupted = False
    try:
        project_safety = assess_project_control_safety(args.owner_worktree, windows_process_snapshot())
        if not project_safety.safe:
            raise AcquisitionError("project safety changed before MT5 import")
        if shutil.disk_usage(_existing_storage_path(output_root)).free <= int(args.minimum_free_gb * 1024**3):
            raise AcquisitionError("coverage probe blocked by the disk safety reserve")
        journal.append("MT5_IMPORT_STARTED", status="RUNNING")
        mt5 = importlib.import_module("MetaTrader5")
        journal.append("MT5_IMPORT_COMPLETED", status="PASSED")
        gateway = ReadOnlyMT5Gateway(mt5)
        journal.append("MT5_INITIALIZE_STARTED", status="RUNNING")
        initialization_started = time.perf_counter()
        gateway.initialize(confirmed_read_only_demo_export=True)
        initialization_seconds = max(time.perf_counter() - initialization_started, 1e-9)
        journal.append("MT5_INITIALIZED", status="PASSED")
        metadata = gateway.symbol_info("XAUUSDm")
        if metadata is None or metadata.get("name") != "XAUUSDm":
            raise AcquisitionError("exact coverage symbol is unavailable")
        probe_result = TickCoverageProbe(
            gateway,
            output_root,
            journal,
            m5_timeframe=gateway.timeframe_value("TIMEFRAME_M5"),
        ).run()
        benchmark_authorized = bool(probe_result["conditional_benchmark_authorized"])
        journal.append(
            "BENCHMARK_CONDITION_EVALUATED",
            status="AUTHORIZED" if benchmark_authorized else "BLOCKED",
            details={"benchmark_authorized": benchmark_authorized},
        )
        if benchmark_authorized:
            interval_start = _utc(str(probe_result["complete_development_hour_start"]))
            benchmark_result = AcquisitionBenchmark(
                gateway,
                output_root,
                stage="hour",
                journal=journal,
                symbol_point=float(metadata.get("point", 0)),
                minimum_free_bytes=int(args.minimum_free_gb * 1024**3),
                maximum_output_bytes=min(int(args.maximum_output_gb * 1024**3), BENCHMARK_MAX_BYTES),
                interval=(interval_start, interval_start + timedelta(hours=1)),
                mt5_session_count=1,
            ).run(initialization_seconds=initialization_seconds)
    except KeyboardInterrupt as exc:
        interrupted = True
        failure = exc
    except Exception as exc:
        failure = exc
    finally:
        shutdown_failure = _shutdown_gateway(journal, gateway)
        if failure is None:
            failure = shutdown_failure
    if failure is not None:
        event = "RUN_INTERRUPTED" if interrupted else "RUN_FAILED"
        journal.append(
            event,
            status="INTERRUPTED" if interrupted else "FAILED",
            error_category=stable_error_category(failure),
            exit_status=130 if interrupted else 2,
        )
        return 130 if interrupted else 2
    journal.append("RUN_COMPLETED", status="PASSED", exit_status=0)
    return _safe_result(
        "TICK_COVERAGE_PROBE_COMPLETE",
        run_id=journal.run_id,
        journal_path=str(journal.journal_path),
        probe=probe_result,
        benchmark=benchmark_result,
        mt5_session_count=1,
    )


def _benchmark_command(args: argparse.Namespace, config: ExportConfig) -> int:
    from bot.acquisition.benchmark import verified_stage_runs, verify_stage_run
    from bot.acquisition.benchmark_supervisor import supervise_benchmark_child
    from bot.acquisition.journal import BenchmarkJournal

    if not args.stage:
        return _safe_result(
            "ACQUISITION_BLOCKED", exit_code=2, reason_code="BENCHMARK_STAGE_REQUIRED", mt5_initialized=False
        )
    if args.resume_run_id:
        run_dir = _benchmark_run_dir(config.output_root, args.stage, args.resume_run_id)
        try:
            manifest = verify_stage_run(run_dir)
        except (AcquisitionError, OSError, ValueError, json.JSONDecodeError):
            return _safe_result(
                "ACQUISITION_BLOCKED",
                exit_code=2,
                reason_code="INCOMPLETE_BENCHMARK_CANNOT_RESUME",
                run_id=args.resume_run_id,
                mt5_initialized=False,
            )
        return _safe_result(
            "BENCHMARK_STAGE_ALREADY_VERIFIED",
            run_id=args.resume_run_id,
            stage=args.stage,
            record_count=manifest["sample"]["rows"],
            mt5_initialized=False,
        )

    journal = BenchmarkJournal.create(config.output_root, args.stage)
    _safe_result(
        "BENCHMARK_RUN_PREPARED",
        run_id=journal.run_id,
        journal_path=str(journal.journal_path),
        mt5_initialized=False,
    )
    journal.append("SAFETY_CHECK_STARTED", status="RUNNING")
    try:
        project_safety = assess_project_control_safety(args.owner_worktree, windows_process_snapshot())
    except (OSError, subprocess.SubprocessError):
        journal.append("RUN_FAILED", status="FAILED", error_category="PROCESS_SAFETY_CHECK_FAILED", exit_status=2)
        return _safe_result(
            "ACQUISITION_BLOCKED", exit_code=2, run_id=journal.run_id,
            journal_path=str(journal.journal_path), reason_code="PROCESS_SAFETY_CHECK_FAILED", mt5_initialized=False,
        )
    if not project_safety.safe:
        journal.append("RUN_FAILED", status="FAILED", error_category=project_safety.reason_code, exit_status=2)
        return _safe_result(
            "ACQUISITION_BLOCKED", exit_code=2, run_id=journal.run_id,
            journal_path=str(journal.journal_path), reason_code=project_safety.reason_code, mt5_initialized=False,
        )
    if shutil.disk_usage(_existing_storage_path(config.output_root)).free <= config.minimum_free_bytes:
        journal.append("RUN_FAILED", status="FAILED", error_category="DISK_SAFETY_RESERVE_NOT_MET", exit_status=2)
        return _safe_result(
            "ACQUISITION_BLOCKED", exit_code=2, run_id=journal.run_id,
            journal_path=str(journal.journal_path), reason_code="DISK_SAFETY_RESERVE_NOT_MET", mt5_initialized=False,
        )
    journal.append("SAFETY_CHECK_PASSED", status="PASSED")
    try:
        pyarrow_version = importlib.metadata.version("pyarrow")
    except importlib.metadata.PackageNotFoundError:
        pyarrow_version = ""
    if pyarrow_version != "25.0.1":
        journal.append("RUN_FAILED", status="FAILED", error_category="DATA_DEPENDENCY_MISMATCH", exit_status=2)
        return _safe_result(
            "ACQUISITION_BLOCKED", exit_code=2, run_id=journal.run_id,
            journal_path=str(journal.journal_path), reason_code="DATA_DEPENDENCY_MISMATCH", mt5_initialized=False,
        )
    journal.append("DEPENDENCY_CHECK_PASSED", status="PASSED")
    predecessor = {"hour": None, "day": "hour", "week": "day"}[args.stage]
    if predecessor and not verified_stage_runs(config.output_root, predecessor):
        journal.append("RUN_FAILED", status="FAILED", error_category="STAGE_PREREQUISITE_MISSING", exit_status=2)
        return _safe_result(
            "ACQUISITION_BLOCKED", exit_code=2, run_id=journal.run_id,
            journal_path=str(journal.journal_path), reason_code="STAGE_PREREQUISITE_MISSING", mt5_initialized=False,
        )

    command = [
        sys.executable, "-u", "-m", "backtests.empirical_data_control", "benchmark",
        "--_benchmark-worker", "--_benchmark-run-id", journal.run_id,
        "--stage", args.stage, "--confirm-read-only-demo-export",
        "--owner-worktree", str(args.owner_worktree), "--output-root", str(config.output_root),
        "--minimum-free-gb", str(args.minimum_free_gb),
        "--maximum-output-gb", str(min(args.maximum_output_gb, 1.0)),
    ]
    environment = strip_sensitive_environment()
    environment["PYTHONUNBUFFERED"] = "1"
    supervised = supervise_benchmark_child(command, journal, environment=environment)
    return _safe_result(
        "BOUNDED_BENCHMARK_STAGE_COMPLETE" if supervised.exit_code == 0 else "ACQUISITION_BLOCKED",
        exit_code=supervised.exit_code,
        run_id=journal.run_id,
        journal_path=str(journal.journal_path),
        stage=args.stage,
        terminal_event=supervised.final_event,
        worker_exit_code=supervised.worker_exit_code,
        supervisor_exit_code=supervised.supervisor_exit_code,
        heartbeat_count=supervised.heartbeat_count,
        mt5_initialized=any(item["event"] == "MT5_INITIALIZED" for item in journal.records()),
    )


def _coverage_command(args: argparse.Namespace, config: ExportConfig) -> int:
    from bot.acquisition.benchmark_supervisor import supervise_benchmark_child
    from bot.acquisition.benchmark import verify_stage_run
    from bot.acquisition.coverage_probe import verify_coverage_probe
    from bot.acquisition.journal import BenchmarkJournal

    journal = BenchmarkJournal.create(config.output_root, "coverage")
    _safe_result(
        "COVERAGE_PROBE_RUN_PREPARED",
        run_id=journal.run_id,
        journal_path=str(journal.journal_path),
        mt5_initialized=False,
    )
    journal.append("SAFETY_CHECK_STARTED", status="RUNNING")
    try:
        project_safety = assess_project_control_safety(args.owner_worktree, windows_process_snapshot())
    except (OSError, subprocess.SubprocessError):
        journal.append("RUN_FAILED", status="FAILED", error_category="PROCESS_SAFETY_CHECK_FAILED", exit_status=2)
        return _safe_result(
            "ACQUISITION_BLOCKED", exit_code=2, run_id=journal.run_id,
            journal_path=str(journal.journal_path), reason_code="PROCESS_SAFETY_CHECK_FAILED",
            mt5_initialized=False,
        )
    if not project_safety.safe:
        journal.append("RUN_FAILED", status="FAILED", error_category=project_safety.reason_code, exit_status=2)
        return _safe_result(
            "ACQUISITION_BLOCKED", exit_code=2, run_id=journal.run_id,
            journal_path=str(journal.journal_path), reason_code=project_safety.reason_code,
            mt5_initialized=False,
        )
    if shutil.disk_usage(_existing_storage_path(config.output_root)).free <= config.minimum_free_bytes:
        journal.append("RUN_FAILED", status="FAILED", error_category="DISK_SAFETY_RESERVE_NOT_MET", exit_status=2)
        return _safe_result(
            "ACQUISITION_BLOCKED", exit_code=2, run_id=journal.run_id,
            journal_path=str(journal.journal_path), reason_code="DISK_SAFETY_RESERVE_NOT_MET",
            mt5_initialized=False,
        )
    journal.append("SAFETY_CHECK_PASSED", status="PASSED")
    try:
        pyarrow_version = importlib.metadata.version("pyarrow")
    except importlib.metadata.PackageNotFoundError:
        pyarrow_version = ""
    if pyarrow_version != "25.0.1":
        journal.append("RUN_FAILED", status="FAILED", error_category="DATA_DEPENDENCY_MISMATCH", exit_status=2)
        return _safe_result(
            "ACQUISITION_BLOCKED", exit_code=2, run_id=journal.run_id,
            journal_path=str(journal.journal_path), reason_code="DATA_DEPENDENCY_MISMATCH",
            mt5_initialized=False,
        )
    journal.append("DEPENDENCY_CHECK_PASSED", status="PASSED")

    command = [
        sys.executable, "-u", "-m", "backtests.empirical_data_control", "probe-tick-coverage",
        "--_coverage-worker", "--_benchmark-run-id", journal.run_id,
        "--confirm-read-only-demo-export", "--owner-worktree", str(args.owner_worktree),
        "--output-root", str(config.output_root), "--minimum-free-gb", str(args.minimum_free_gb),
        "--maximum-output-gb", str(min(args.maximum_output_gb, 1.0)),
    ]
    environment = strip_sensitive_environment()
    environment["PYTHONUNBUFFERED"] = "1"
    supervised = supervise_benchmark_child(command, journal, environment=environment)
    probe: dict[str, object] | None = None
    if supervised.exit_code == 0:
        try:
            probe = verify_coverage_probe(journal.run_dir)
            if probe.get("conditional_benchmark_authorized"):
                verify_stage_run(journal.run_dir)
        except (AcquisitionError, OSError, ValueError, json.JSONDecodeError):
            return _safe_result(
                "ACQUISITION_BLOCKED", exit_code=2, run_id=journal.run_id,
                journal_path=str(journal.journal_path), reason_code="PROBE_VERIFICATION_FAILED",
                mt5_initialized=True,
            )
    return _safe_result(
        "TICK_COVERAGE_PROBE_COMPLETE" if supervised.exit_code == 0 else "ACQUISITION_BLOCKED",
        exit_code=supervised.exit_code,
        run_id=journal.run_id,
        journal_path=str(journal.journal_path),
        terminal_event=supervised.final_event,
        worker_exit_code=supervised.worker_exit_code,
        supervisor_exit_code=supervised.supervisor_exit_code,
        heartbeat_count=supervised.heartbeat_count,
        probe=probe,
        mt5_initialized=any(item["event"] == "MT5_INITIALIZED" for item in journal.records()),
    )


def _mt5_command(args: argparse.Namespace, config: ExportConfig) -> int:
    from bot.acquisition.exporter import EmpiricalExporter, compare_tick_derived_bars, normalize_rates
    from bot.acquisition.gateway import ReadOnlyMT5Gateway
    from bot.data.candles import TIMEFRAMES

    project_safety = assess_project_control_safety(args.owner_worktree, windows_process_snapshot())
    if not project_safety.safe:
        return _safe_result(
            ExportStatus.ACTIVE_BOT_DETECTED.value,
            mt5_initialized=False,
            reason_code=project_safety.reason_code,
            project_control_state=project_safety.control_state,
            recorded_pid_active=project_safety.recorded_pid_active,
        )
    if args.command in {"export-bars", "export-calibration"} and shutil.disk_usage(
        _existing_storage_path(config.output_root)
    ).free <= config.minimum_free_bytes:
        return _safe_result(
            ExportStatus.INSUFFICIENT_DISK.value,
            mt5_initialized=False,
            reason_code="DISK_SAFETY_RESERVE_NOT_MET",
            required_free_bytes=config.minimum_free_bytes,
        )

    mt5 = importlib.import_module("MetaTrader5")
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    try:
        exporter = EmpiricalExporter(gateway, config)
        inspection = exporter.inspect()
        if inspection.status is not ExportStatus.TOOL_VERIFIED:
            return _safe_result(
                inspection.status.value,
                mt5_initialized=True,
                missing_symbols=inspection.missing_symbols,
                ambiguous_symbols=inspection.ambiguous_symbols,
            )
        if args.command == "inspect":
            metadata = gateway.safe_metadata("XAUUSDm", datetime.now(UTC))
            return _safe_result(
                inspection.status.value,
                mt5_initialized=True,
                mt5_version=gateway.version(),
                mappings={key: value.broker_symbol for key, value in inspection.mappings.items()},
                xau_metadata=metadata,
            )
        sample_end = _utc(args.sample_end) if args.sample_end else config.end
        sample_start = _utc(args.sample_start) if args.sample_start else sample_end - timedelta(minutes=config.sample_minutes)
        if args.command == "sample":
            return _safe_result("SAMPLE_VALID", sample=exporter.write_sample(sample_start, sample_end))
        if args.command in {"export-bars", "export-calibration"}:
            from bot.acquisition.plan import DEVELOPMENT_END, DEVELOPMENT_START

            if config.start != DEVELOPMENT_START or config.end != DEVELOPMENT_END:
                raise AcquisitionError("hybrid development exports require the exact development interval")
            chunks = (
                exporter.export_bars(inspection.mappings, resume=False)
                if args.command == "export-bars"
                else exporter.export_calibration_ticks(resume=False)
            )
            return _safe_result(
                "BOUNDED_HYBRID_EXPORT_COMPLETE",
                dataset_scope="DEVELOPMENT_BARS" if args.command == "export-bars" else "PREREGISTERED_TICK_CALIBRATION",
                chunk_count=len(chunks),
                strategy_evaluated=False,
            )
        sample_manifest, sample_records = exporter.load_sample(sample_start, sample_end)
        coverage = exporter.discover_coverage()
        estimate = exporter.estimate(sample_manifest, coverage)
        if args.command == "estimate":
            return _safe_result("ESTIMATE_COMPLETE", coverage=coverage, estimate=estimate)
        if not estimate.safe_to_continue:
            return _safe_result(ExportStatus.INSUFFICIENT_DISK.value, estimate=estimate)
        native_sample = normalize_rates(
            gateway.copy_rates_range(
                "XAUUSDm", gateway.timeframe_value(TIMEFRAMES["M5"].mt5_attribute), sample_start, sample_end
            ),
            symbol="XAUUSDm", timeframe="M5", end_exclusive=sample_end,
        )
        cross_check = compare_tick_derived_bars(sample_records, native_sample, timeframe="M5", price_tolerance=0.0)
        resume = args.command == "resume"
        tick_chunks = exporter.export_ticks(resume=resume)
        bar_chunks = exporter.export_bars(inspection.mappings, resume=resume)
        metadata = exporter.export_safe_metadata(exported_at=datetime.now(UTC), resume=resume)
        chunks = tick_chunks + bar_chunks
        status = ExportStatus.EXPORT_COMPLETE if tick_chunks and bar_chunks else ExportStatus.PARTIAL_EXPORT
        exporter.write_export_manifest(
            inspection=inspection,
            chunks=chunks,
            metadata_path=metadata,
            status=status,
            git_commit=_git_output("rev-parse", "HEAD"),
            cross_checks={"bounded_xau_m5_sample": cross_check},
        )
        return _safe_result(status.value, chunk_count=len(chunks))
    finally:
        gateway.shutdown()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    scrub_current_environment()
    try:
        if args._benchmark_worker:
            return _benchmark_worker(args)
        if args._coverage_worker:
            return _coverage_worker(args)
        if args.dry_run:
            return _safe_result(
                ExportStatus.TOOL_VERIFIED.value,
                dry_run=True,
                mt5_initialized=False,
                command=args.command,
            )
        if args.command in MT5_COMMANDS and not args.confirm_read_only_demo_export:
            return _safe_result(
                "ACQUISITION_BLOCKED",
                exit_code=2 if args.command in {"benchmark", "probe-tick-coverage"} else 0,
                reason_code="CONFIRMATION_REQUIRED",
                mt5_initialized=False,
            )
        config = _config(args)
        if bool(args.sample_start) != bool(args.sample_end):
            raise AcquisitionError("both bounded sample timestamps are required")
        if args.sample_start:
            sample_start = _utc(args.sample_start)
            sample_end = _utc(args.sample_end)
            if not config.start <= sample_start < sample_end <= config.end or sample_end - sample_start > timedelta(hours=1):
                raise AcquisitionError("sample must lie within requested history and span at most one hour")
        if args.command not in MT5_COMMANDS:
            return _offline_command(args, config)
        if args.command == "benchmark":
            return _benchmark_command(args, config)
        if args.command == "probe-tick-coverage":
            return _coverage_command(args, config)
        return _mt5_command(args, config)
    except (AcquisitionError, FileExistsError, OSError, TypeError, ValueError, subprocess.SubprocessError):
        return _safe_result("ACQUISITION_BLOCKED", reason="sanitized safety or validation failure")


if __name__ == "__main__":
    raise SystemExit(main())
