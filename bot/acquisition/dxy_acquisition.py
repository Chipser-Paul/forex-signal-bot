"""Phase 8D bounded read-only MT5 H1-bar acquisition (worker functions).

Implements the single authorized bounded read-only MT5 session for the six
verified constituent mappings over the 2024 development year only:

- credential-bearing environment variables are stripped before import;
- the canonical ``ReadOnlyMT5Gateway`` confines the module surface to the
  permitted read-only operations (no login, no account, no orders);
- the official bot-control state must be STOPPED and no ambiguous bot
  process may be running;
- exactly one ``initialize()`` without login arguments and exactly one
  ``shutdown()`` in ``finally``;
- deterministic monthly ``copy_rates_range`` chunks over the six symbols,
  2024 only, with sanitized distinct handling of empty and null responses;
- durable journal events with heartbeats for the existing supervisor
  protocol.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import importlib
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from bot.validation.models import canonical_data

from .dxy_contracts import (
    DXY_CONSTITUENT_ORDER,
    DXY_SYMBOL_MAP,
    normalize_rate_chunk,
)
from .dxy_package import resolve_symbol_mappings
from .models import AcquisitionError
from .safety import (
    assess_project_control_safety,
    scrub_current_environment,
    windows_process_snapshot,
)

UTC = timezone.utc


def _existing_storage_path(path: Path) -> Path:
    candidate = Path(path).resolve(strict=False)
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return candidate


def run_dxy_acquisition(
    output_root: Path,
    owner_worktree: Path,
    journal,
    *,
    minimum_free_gb: float = 15.0,
    timeframe_attribute: str = "TIMEFRAME_H1",
    confirm_read_only_demo_export: bool = False,
) -> dict:
    """Execute the bounded read-only acquisition; returns acquisition evidence.

    The caller owns journal lifecycle and terminal-event emission.
    """
    output_root = Path(output_root)
    if not confirm_read_only_demo_export:
        raise AcquisitionError("DXY_READ_ONLY_CONFIRMATION_REQUIRED")

    journal.append("SAFETY_CHECK_STARTED", status="RUNNING")
    project_safety = assess_project_control_safety(
        owner_worktree, windows_process_snapshot()
    )
    if not project_safety.safe:
        raise AcquisitionError(f"DXY_PROJECT_SAFETY_UNSAFE: {project_safety.reason_code}")
    free_bytes = shutil.disk_usage(_existing_storage_path(output_root)).free
    if free_bytes <= int(minimum_free_gb * 1024**3):
        raise AcquisitionError("DXY_DISK_RESERVE_BREACHED")
    journal.append("SAFETY_CHECK_PASSED", status="PASSED")

    scrubbed = scrub_current_environment()
    journal.append(
        "DEPENDENCY_CHECK_PASSED",
        status="PASSED",
        details={"operation": "ENV_SCRUBBED"},
    )

    journal.append("MT5_IMPORT_STARTED", status="RUNNING")
    mt5 = importlib.import_module("MetaTrader5")
    journal.append("MT5_IMPORT_COMPLETED", status="PASSED")

    from .gateway import ReadOnlyMT5Gateway

    gateway = None
    try:
        gateway = ReadOnlyMT5Gateway(mt5)
        journal.append("MT5_INITIALIZE_STARTED", status="RUNNING")
        initialization_started = time.perf_counter()
        gateway.initialize(confirmed_read_only_demo_export=True)
        initialization_seconds = max(time.perf_counter() - initialization_started, 1e-9)
        journal.append("MT5_INITIALIZED", status="PASSED")

        version = gateway.version()
        build_text = ".".join(str(item) for item in version) if version else None
        error_status = gateway.last_error_status()

        resolved = resolve_symbol_mappings(gateway)
        timeframe_value = gateway.timeframe_value(timeframe_attribute)

        from .dxy_contracts import iter_development_month_chunks, DEVELOPMENT_END

        chunks = iter_development_month_chunks()
        records_by_symbol: dict[str, dict[int, dict]] = {
            symbol: {} for symbol in DXY_CONSTITUENT_ORDER
        }
        diagnostics_by_symbol: dict[str, dict] = {}
        retrieved_utc = datetime.now(UTC)

        for canonical_symbol in DXY_CONSTITUENT_ORDER:
            broker_symbol = DXY_SYMBOL_MAP[canonical_symbol]
            if not gateway.symbol_select(broker_symbol):
                raise AcquisitionError(
                    f"DXY_SYMBOL_SELECT_FAILED: {broker_symbol}"
                )
            for chunk_start, chunk_end in chunks:
                journal.append("REQUEST_STARTED", status="RUNNING")
                request_started = time.perf_counter()
                rates = gateway.copy_rates_range(
                    broker_symbol, timeframe_value, chunk_start, chunk_end
                )
                records, diagnostics = normalize_rate_chunk(
                    canonical_symbol,
                    broker_symbol,
                    rates,
                    chunk_start,
                    chunk_end,
                    retrieved_utc=retrieved_utc,
                    terminal_build=build_text,
                )
                existing = records_by_symbol[canonical_symbol]
                from .dxy_contracts import deduplicate_chunk_records

                records_by_symbol[canonical_symbol] = deduplicate_chunk_records(
                    existing, records, canonical_symbol
                )
                diagnostics_by_symbol.setdefault(
                    canonical_symbol, {"ok_chunks": 0, "empty_chunks": 0, "null_chunks": 0}
                )
                if diagnostics["response_class"] == "OK":
                    diagnostics_by_symbol[canonical_symbol]["ok_chunks"] += 1
                elif diagnostics["response_class"] == "EMPTY_RESPONSE":
                    diagnostics_by_symbol[canonical_symbol]["empty_chunks"] += 1
                else:
                    diagnostics_by_symbol[canonical_symbol]["null_chunks"] += 1
                journal.append(
                    "REQUEST_COMPLETED",
                    status="PASSED",
                    details={"operation": f"{canonical_symbol}-{chunk_start:%Y%m}"},
                )
                del request_started

        terminal_build = build_text
        error_summary = {
            "code": error_status.code,
            "category": error_status.category,
            "description_sha256": error_status.description_sha256,
        }
        return {
            "resolved_mappings": {
                symbol: canonical_data(dict(info)) for symbol, info in resolved.items()
            },
            "records_by_symbol": {
                symbol: sorted(records.values(), key=lambda r: r["open_time_ms"])
                for symbol, records in records_by_symbol.items()
            },
            "diagnostics_by_symbol": diagnostics_by_symbol,
            "retrieved_utc": retrieved_utc,
            "terminal_build": terminal_build,
            "initialization_seconds": initialization_seconds,
            "error_summary": error_summary,
            "chunk_count": len(list(chunks)) * len(DXY_CONSTITUENT_ORDER),
        }
    finally:
        if gateway is not None and gateway.is_initialized:
            journal.append("MT5_SHUTDOWN_STARTED", status="RUNNING")
            gateway.shutdown()
            journal.append("MT5_SHUTDOWN_COMPLETED", status="PASSED")
