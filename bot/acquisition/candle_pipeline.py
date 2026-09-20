"""Phase 8C causal bid/ask candle aggregation pipeline.

Converts verified 2024 XAUUSDm tick packages into deterministic, causal,
closed-open OHLC candles for each required timeframe.

Causality invariants enforced here:
- Each window is [open_time, close_time) — deterministic and closed-open.
- available_at = close_time (first moment after the window closes).
- No tick from outside the closed-open window enters a candle.
- Missing intervals remain explicit gaps; no synthetic flat candles.
- No forward-filling of OHLC or spreads.
- Bid and ask remain separate throughout.
- Duplicate source ticks (same ms, same price) count as multiple observations.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Mapping, Sequence

from bot.data.candles import TIMEFRAMES
from bot.validation.models import canonical_data

from .exness_archive import exness_tick_schema
from .models import AcquisitionError, EXECUTABLE_SYMBOL


UTC = timezone.utc
SCHEMA_VERSION = "phase8c.bidask-candles.v1"
CLASSIFICATION_LABEL = "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE"
PROVENANCE_LABEL = "exness-tick-history-2024-monthly-reconstruction"

# Timeframes supported by this pipeline (Phase 2 canonical set minus M1/M30)
REQUIRED_TIMEFRAMES = ("M5", "M15", "H1", "H4", "D1", "W1")

# Maximum ticks to buffer per streaming batch (keeps memory bounded)
BATCH_SIZE = 100_000


# ---------------------------------------------------------------------------
# Window boundaries
# ---------------------------------------------------------------------------

def timeframe_duration(timeframe: str) -> timedelta:
    """Return the canonical duration for a supported timeframe."""
    spec = TIMEFRAMES[timeframe]
    return spec.duration


def window_open_time(tick_time: datetime, timeframe: str) -> datetime:
    """Return the canonical open_time for the closed-open window containing tick_time.

    All boundaries use UTC.  W1 uses Monday 00:00 UTC per Phase 2 contract.

    This is deterministic: the same tick_time and timeframe always yield the
    same open_time regardless of processing order.
    """
    t = tick_time.astimezone(UTC).replace(tzinfo=UTC)
    if timeframe == "M5":
        minute = (t.minute // 5) * 5
        return t.replace(minute=minute, second=0, microsecond=0)
    if timeframe == "M15":
        minute = (t.minute // 15) * 15
        return t.replace(minute=minute, second=0, microsecond=0)
    if timeframe == "H1":
        return t.replace(minute=0, second=0, microsecond=0)
    if timeframe == "H4":
        hour = (t.hour // 4) * 4
        return t.replace(hour=hour, minute=0, second=0, microsecond=0)
    if timeframe == "D1":
        return t.replace(hour=0, minute=0, second=0, microsecond=0)
    if timeframe == "W1":
        # Monday 00:00 UTC — weekday() == 0 is Monday
        days_since_monday = t.weekday()
        monday = t - timedelta(days=days_since_monday)
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    raise AcquisitionError(f"Unsupported timeframe for window boundary: {timeframe!r}")


def window_close_time(open_time: datetime, timeframe: str) -> datetime:
    """Return the exclusive close_time for the window starting at open_time."""
    return open_time + timeframe_duration(timeframe)


def stable_candle_identity(
    symbol: str, timeframe: str, open_time_ms: int, close_time_ms: int
) -> str:
    """Return a stable SHA-256 identity for a candle, independent of content.

    The identity is derived only from (symbol, timeframe, open_time_ms,
    close_time_ms).  It is deterministic across runs given the same inputs.
    """
    payload = json.dumps(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "open_time_ms": open_time_ms,
            "close_time_ms": close_time_ms,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Per-window accumulator
# ---------------------------------------------------------------------------

@dataclass
class _WindowAccumulator:
    """Mutable accumulator for one closed-open candle window."""

    open_time: datetime
    close_time: datetime
    timeframe: str
    source_package_ids: set = field(default_factory=set)

    # Bid OHLC
    bid_open: Decimal | None = None
    bid_high: Decimal | None = None
    bid_low: Decimal | None = None
    bid_close: Decimal | None = None

    # Ask OHLC
    ask_open: Decimal | None = None
    ask_high: Decimal | None = None
    ask_low: Decimal | None = None
    ask_close: Decimal | None = None

    # Spread stats
    spreads: list = field(default_factory=list)

    # Tick provenance
    tick_count: int = 0
    first_tick_time: datetime | None = None
    last_tick_time: datetime | None = None

    def add_tick(
        self,
        timestamp: datetime,
        bid: Decimal,
        ask: Decimal,
        package_id: str,
    ) -> None:
        """Add one tick to this accumulator.

        Invariants enforced by the caller before this is invoked:
        - open_time <= timestamp < close_time
        - ask >= bid
        - bid > 0, ask > 0
        """
        self.tick_count += 1
        self.source_package_ids.add(package_id)

        if self.bid_open is None:
            self.bid_open = bid
            self.ask_open = ask
            self.first_tick_time = timestamp

        # High/low
        self.bid_high = bid if self.bid_high is None else max(self.bid_high, bid)
        self.bid_low = bid if self.bid_low is None else min(self.bid_low, bid)
        self.ask_high = ask if self.ask_high is None else max(self.ask_high, ask)
        self.ask_low = ask if self.ask_low is None else min(self.ask_low, ask)

        # Close updates on every tick
        self.bid_close = bid
        self.ask_close = ask
        self.last_tick_time = timestamp

        # Spread
        self.spreads.append(ask - bid)

    def is_empty(self) -> bool:
        return self.tick_count == 0

    def to_record(self) -> dict:
        """Convert accumulated state to a candle record dict."""
        if self.is_empty():
            raise AcquisitionError("Cannot materialise an empty window accumulator")
        open_ms = int(self.open_time.timestamp() * 1000)
        close_ms = int(self.close_time.timestamp() * 1000)
        identity = stable_candle_identity(
            EXECUTABLE_SYMBOL, self.timeframe, open_ms, close_ms
        )
        sorted_spreads = sorted(self.spreads)
        n = len(sorted_spreads)
        if n % 2 == 1:
            median_spread = sorted_spreads[n // 2]
        else:
            median_spread = (sorted_spreads[n // 2 - 1] + sorted_spreads[n // 2]) / 2

        return {
            "symbol": EXECUTABLE_SYMBOL,
            "timeframe": self.timeframe,
            "open_time_ms": open_ms,
            "close_time_ms": close_ms,
            "available_at_ms": close_ms,  # available_at = close_time (causal)
            "bid_open": format(self.bid_open, ".8f"),
            "bid_high": format(self.bid_high, ".8f"),
            "bid_low": format(self.bid_low, ".8f"),
            "bid_close": format(self.bid_close, ".8f"),
            "ask_open": format(self.ask_open, ".8f"),
            "ask_high": format(self.ask_high, ".8f"),
            "ask_low": format(self.ask_low, ".8f"),
            "ask_close": format(self.ask_close, ".8f"),
            "tick_count": self.tick_count,
            "spread_min": format(min(self.spreads), ".8f"),
            "spread_max": format(max(self.spreads), ".8f"),
            "spread_median": format(median_spread, ".8f"),
            "spread_close": format(self.spreads[-1], ".8f"),
            "first_tick_ms": int(self.first_tick_time.timestamp() * 1000),
            "last_tick_ms": int(self.last_tick_time.timestamp() * 1000),
            "source_package_ids": sorted(self.source_package_ids),
            "candle_identity": identity,
            "schema_version": SCHEMA_VERSION,
            "classification": CLASSIFICATION_LABEL,
        }


# ---------------------------------------------------------------------------
# Gap tracking
# ---------------------------------------------------------------------------

@dataclass
class GapRecord:
    timeframe: str
    gap_open_ms: int    # first missing window open_time
    gap_close_ms: int   # last missing window close_time (exclusive)
    missing_window_count: int


def _detect_gaps(
    timeframe: str,
    emitted_open_times_ms: list[int],
    period_start: datetime,
    period_end: datetime,
) -> list[GapRecord]:
    """Find contiguous runs of missing windows between first and last observation."""
    if not emitted_open_times_ms:
        return []
    dur = timeframe_duration(timeframe)
    dur_ms = int(dur.total_seconds() * 1000)
    emitted = sorted(emitted_open_times_ms)
    gaps: list[GapRecord] = []
    prev_close_ms = emitted[0]  # first open — no gap before first window
    for open_ms in emitted:
        if open_ms > prev_close_ms:
            # Gap from prev_close_ms to open_ms
            missing = (open_ms - prev_close_ms) // dur_ms
            gaps.append(
                GapRecord(
                    timeframe=timeframe,
                    gap_open_ms=prev_close_ms,
                    gap_close_ms=open_ms,
                    missing_window_count=missing,
                )
            )
        prev_close_ms = open_ms + dur_ms
    return gaps


# ---------------------------------------------------------------------------
# Main aggregation function
# ---------------------------------------------------------------------------

def aggregate_ticks_to_candles(
    monthly_packages: Sequence[tuple[Path, Mapping]],
    timeframe: str,
    *,
    year_package_id: str,
) -> Iterator[dict]:
    """Stream all monthly packages and yield completed candle records.

    Processes ticks in chronological monthly order.  Each batch is
    BATCH_SIZE rows.  Only completed windows are emitted; the last
    partial window at end-of-data is discarded (not forward-filled).

    Yields one dict per completed candle, in open_time_ms order.

    Args:
        monthly_packages: Sequence of (package_root, manifest) in month order.
        timeframe: One of the REQUIRED_TIMEFRAMES.
        year_package_id: The year-level package ID for provenance.
    """
    if timeframe not in REQUIRED_TIMEFRAMES:
        raise AcquisitionError(f"Unsupported timeframe: {timeframe!r}")

    try:
        _arrow_imported = _arrow()
    except AcquisitionError:
        raise
    pa, pq = _arrow_imported

    expected_schema = exness_tick_schema()
    current_accumulator: _WindowAccumulator | None = None
    previous: datetime | None = None

    for package_root, manifest in monthly_packages:
        package_id = str(manifest["package_id"])
        partitions = manifest.get("partitions", [])

        for partition in partitions:
            relative_path = str(partition["relative_path"])
            parquet_path = package_root / relative_path

            try:
                pf = pq.ParquetFile(parquet_path)
            except Exception as exc:
                raise AcquisitionError(
                    f"Cannot open tick partition {parquet_path.name}: {exc}"
                ) from exc

            if pf.schema_arrow != expected_schema:
                raise AcquisitionError(
                    f"Tick partition schema mismatch: {parquet_path.name}"
                )

            for batch in pf.iter_batches(batch_size=BATCH_SIZE):
                columns = batch.to_pydict()
                if batch.num_rows and previous is not None:
                    first_of_batch = columns["timestamp"][0].astimezone(UTC)
                    if first_of_batch < previous:
                        raise AcquisitionError(
                            "Tick partition is not in chronological order: "
                            f"{parquet_path.name} batch starts at "
                            f"{first_of_batch.isoformat()} before {previous.isoformat()}"
                        )
                for i in range(batch.num_rows):
                    timestamp = columns["timestamp"][i].astimezone(UTC)
                    bid = columns["bid"][i]
                    ask = columns["ask"][i]
                    symbol = str(columns["symbol"][i])

                    if symbol != EXECUTABLE_SYMBOL:
                        raise AcquisitionError(
                            f"Non-executable symbol in tick partition: {symbol!r}"
                        )
                    if ask < bid:
                        raise AcquisitionError(
                            f"Crossed quote at {timestamp.isoformat()}: "
                            f"bid={bid} ask={ask}"
                        )
                    if bid <= 0 or ask <= 0:
                        raise AcquisitionError(
                            f"Non-positive quote at {timestamp.isoformat()}: "
                            f"bid={bid} ask={ask}"
                        )

                    previous = timestamp

                    # Determine which window this tick belongs to
                    tick_open = window_open_time(timestamp, timeframe)
                    tick_close = tick_open + timeframe_duration(timeframe)

                    # Strict boundary check: tick must be in [open_time, close_time)
                    if not (tick_open <= timestamp < tick_close):
                        raise AcquisitionError(
                            f"Tick {timestamp.isoformat()} falls outside its "
                            f"assigned window [{tick_open.isoformat()}, "
                            f"{tick_close.isoformat()})"
                        )

                    # If we moved to a new window, emit the previous one
                    if (
                        current_accumulator is not None
                        and tick_open != current_accumulator.open_time
                    ):
                        if not current_accumulator.is_empty():
                            yield current_accumulator.to_record()
                        current_accumulator = None

                    if current_accumulator is None:
                        current_accumulator = _WindowAccumulator(
                            open_time=tick_open,
                            close_time=tick_close,
                            timeframe=timeframe,
                        )

                    current_accumulator.add_tick(timestamp, bid, ask, package_id)

    # Do NOT emit the final partial window — it may be incomplete.
    # The caller records this as a partial terminal window in the manifest.


def _arrow():
    """Import PyArrow, raising AcquisitionError if unavailable."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise AcquisitionError(
            "Parquet support requires the pinned requirements-data.txt environment"
        ) from exc
    return pa, pq
