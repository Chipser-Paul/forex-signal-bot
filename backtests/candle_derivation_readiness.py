"""Phase 8C machine-readable dataset readiness report.

Produces a JSON report separating:
  AVAILABLE  — what has been verified and derived.
  STILL_MISSING — what remains required before final validation.

This report does not evaluate the strategy, assess profitability,
or authorise holdout access.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from bot.validation.models import canonical_data

from bot.acquisition.candle_pipeline import REQUIRED_TIMEFRAMES, SCHEMA_VERSION

UTC = timezone.utc
REPORT_SCHEMA_VERSION = "phase8c.readiness-report.v1"


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_readiness_report(
    *,
    year_package_id: str,
    source_row_count: int,
    source_canonical_sha256: str,
    source_first_tick: str,
    source_last_tick: str,
    derived_timeframes: Sequence[str],
    derived_row_counts: dict[str, int],
    derived_gap_counts: dict[str, int],
    derived_missing_window_counts: dict[str, int],
    derived_output_dir: str,
    derived_manifest_sha256: str,
    monthly_package_ids: Sequence[str],
    git_commit: str,
) -> dict:
    """Build a machine-readable readiness report.

    Returns a dict suitable for JSON serialisation.
    """
    available_tfs = list(derived_timeframes)
    missing_tfs = [tf for tf in REQUIRED_TIMEFRAMES if tf not in available_tfs]

    report = canonical_data({
        "schema_version": REPORT_SCHEMA_VERSION,
        "classification": "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE",
        "generated_at": _now_utc_iso(),
        "git_commit": git_commit,
        "pipeline_schema_version": SCHEMA_VERSION,

        "AVAILABLE": {
            "verified_tick_dataset": {
                "description": (
                    "Verified 2024 XAUUSDm bid/ask ticks — 12 independently "
                    "verified monthly packages, reconstructed from Exness archives."
                ),
                "year_package_id": year_package_id,
                "source_row_count": source_row_count,
                "source_canonical_sha256": source_canonical_sha256,
                "first_tick_utc": source_first_tick,
                "last_tick_utc": source_last_tick,
                "monthly_package_ids": list(monthly_package_ids),
                "status": "VERIFIED",
            },
            "derived_causal_candles": {
                "description": (
                    "Causal XAUUSDm bid/ask OHLC candles derived from verified ticks. "
                    "Windows are closed-open [open_time, close_time). "
                    "available_at = close_time (conservative causal availability). "
                    "No forward-filling. No synthetic candles."
                ),
                "output_directory": derived_output_dir,
                "manifest_sha256": derived_manifest_sha256,
                "completed_timeframes": available_tfs,
                "row_counts": {tf: derived_row_counts.get(tf, 0) for tf in available_tfs},
                "gap_counts": {tf: derived_gap_counts.get(tf, 0) for tf in available_tfs},
                "missing_window_counts": {
                    tf: derived_missing_window_counts.get(tf, 0) for tf in available_tfs
                },
                "missing_timeframes": missing_tfs,
                "status": "COMPLETE" if not missing_tfs else "PARTIAL",
            },
            "spread_evidence": {
                "description": (
                    "Observed spread statistics are embedded in each candle "
                    "(spread_min, spread_max, spread_median, spread_close). "
                    "Observed from verified bid/ask tick pairs."
                ),
                "status": "EMBEDDED_IN_CANDLES",
            },
        },

        "STILL_MISSING_OR_UNRESOLVED": {
            "DXY_history": {
                "description": (
                    "Direct DXY index history or all six causally aligned Phase 6 "
                    "constituent OHLC histories (EURUSD, USDJPY, GBPUSD, USDCAD, "
                    "USDSEK, USDCHF) with provenance and licensing."
                ),
                "status": "NOT_PROVIDED",
                "required_for": "STRATEGY_EVALUATION",
            },
            "USD_news_history": {
                "description": (
                    "Complete 2024 high-impact USD news events with UTC timestamps, "
                    "stable event identities, impact levels, provider identity, "
                    "and provenance/licensing documentation."
                ),
                "status": "NOT_PROVIDED",
                "required_for": "STRATEGY_EVALUATION",
            },
            "broker_metadata": {
                "description": (
                    "Historically-effective Exness XAUUSDm broker metadata: "
                    "commission schedule, swap/rollover rates, triple-swap weekday, "
                    "tick size/value, contract size, effective dates, and provenance."
                ),
                "status": "NOT_PROVIDED",
                "required_for": "STRATEGY_EVALUATION",
            },
            "slippage_fill_evidence": {
                "description": (
                    "Empirical bid/ask fill and slippage observations with "
                    "timestamps, quote and fill prices, provenance."
                ),
                "status": "NOT_PROVIDED",
                "required_for": "VALIDATED_EXECUTION_FIDELITY",
            },
            "final_holdout_dataset": {
                "description": (
                    "An untouched, never-viewed final holdout period. "
                    "The 2024 development dataset is NOT the holdout. "
                    "Previously-viewed periods include 2025-10-01 through 2026-07-18; "
                    "those cannot be a genuinely untouched holdout."
                ),
                "status": "NOT_AVAILABLE",
                "required_for": "FINAL_SCIENTIFIC_VALIDATION",
            },
            "complete_validation_dataset": {
                "description": (
                    "The dataset cannot be classified ACCEPTED_FOR_FINAL_VALIDATION "
                    "while DXY, news, broker metadata, slippage evidence, and holdout "
                    "are missing. Current achievable outcome: "
                    "ACCEPTED_FOR_DEVELOPMENT_ONLY at most."
                ),
                "status": "INCOMPLETE",
                "missing_components": [
                    "DXY_history",
                    "USD_news_history",
                    "broker_metadata",
                    "slippage_fill_evidence",
                    "final_holdout_dataset",
                ],
            },
        },

        "STRATEGY_EVALUATION_STATUS": {
            "performed": False,
            "authorized": False,
            "note": (
                "No strategy evaluation, profitability assessment, win rate, "
                "profit factor, or trading recommendation has been computed. "
                "This report covers data availability only."
            ),
        },

        "HOLDOUT_STATUS": {
            "accessed": False,
            "authorized": False,
        },

        "MT5_AND_TRADING_STATUS": {
            "mt5_initialized": False,
            "broker_api_called": False,
            "order_sent": False,
            "account_accessed": False,
        },
    })

    return report
