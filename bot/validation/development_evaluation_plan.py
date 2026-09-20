"""Phase 8M immutable, development-only evaluation-plan contract.

This module only verifies already-published offline artifacts and freezes their
identities into an append-only plan.  It deliberately cannot evaluate a
strategy, access a holdout, initialize MT5, or contact a network service.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from bot.acquisition.candle_attestation import verify_package_readonly as verify_candles
from bot.acquisition.dxy_package import verify_package_readonly as verify_dxy
from bot.acquisition.evidence_contracts import DEVELOPMENT_ONLY_CLASSIFICATION, canonical_hash
from bot.acquisition.evidence_store import build_evidence_package, load_evidence_package, publish_evidence_package
from bot.acquisition.exness_archive import verify_exness_package
from bot.acquisition.exness_reconstruction import (
    YEAR_COMPLETION_SCHEMA_VERSION,
    YEAR_MANIFEST_SCHEMA_VERSION,
    verify_2024_development_year_package,
)
from bot.acquisition.models import AcquisitionError
from bot.execution.risk.policy import RiskPolicy
from bot.strategy.config import StrategyConfig
from bot.validation import cost_policy
from bot.validation.development_metadata_bounds import verify_development_metadata_bounds
from bot.validation.study import ContaminationRegister


SCHEMA_VERSION = "phase8m.development-evaluation-plan.v1"
PLAN_KIND = "development_evaluation_plan"
SYMBOL = "XAUUSDm"
DEVELOPMENT_START = "2024-01-01T00:00:00Z"
DEVELOPMENT_END = "2025-01-01T00:00:00Z"
FROZEN_AT = "2026-09-15T00:00:00Z"
TIMEFRAMES = ("M5", "M15", "H1", "H4", "D1", "W1")
COST_POLICY_ID = "evidence-development_cost_policy-v1-6b1a986b1f8d7b81"
METADATA_POLICY_ID = "evidence-development_metadata_bounds-v1-8dad509e60c8014a"
OBSERVED_SPREAD_ID = "observed_spread-v1-e25bdb9bf028a5be"
OFFICIAL_NEWS_ID = "evidence-official_news-v1-78279c5e26c1c6d1"
UTC = timezone.utc
WARMUP_SECONDS = 2_419_200  # exactly 28 days, per the Phase 8A preregistration
PURGE_SECONDS = 86_400
EMBARGO_SECONDS = 86_400


class DevelopmentEvaluationPlanError(RuntimeError):
    """Raised when an input is missing, changes identity, or is unsafe."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _require_hash(value: object, label: str) -> str:
    result = str(value)
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise DevelopmentEvaluationPlanError(f"{label} lacks a valid SHA-256")
    return result


def _load_evidence(evidence_root: Path, package_id: str, expected_kind: str) -> dict[str, Any]:
    package = load_evidence_package(Path(evidence_root) / package_id)
    manifest = package.get("manifest", {})
    if manifest.get("package_id") != package_id or manifest.get("kind") != expected_kind:
        raise DevelopmentEvaluationPlanError(f"{package_id} identity or kind mismatch")
    _require_hash(manifest.get("content_canonical_sha256"), package_id)
    return package


def _broker_policy_fingerprint(worktree: Path) -> str:
    paths = (
        "bot/execution/broker/models.py",
        "bot/execution/broker/policy.py",
        "bot/execution/broker/validation.py",
        "bot/execution/broker/adapter.py",
    )
    payload = {relative: _sha256_file(Path(worktree) / relative) for relative in paths}
    return canonical_hash(payload)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _fixed_folds() -> tuple[dict[str, Any], ...]:
    # Four ANCHORED chronological folds per the Phase 8A preregistration
    # (config/validation_plan.example.json): anchored training from the
    # development start, an exact 28-day warm-up ending at each evaluation
    # start, an exact one-day purge gap between anchored training end and
    # evaluation start, and a one-day embargo between consecutive evaluation
    # windows.  The four equal evaluation windows tile 2024-04-01 to
    # 2025-01-01 with exactly three one-day embargo gaps; every boundary is
    # computed with datetime arithmetic -- never string slicing -- so each
    # derived date is valid by construction.
    region_start = datetime(2024, 4, 1, tzinfo=UTC)
    region_end = datetime(2025, 1, 1, tzinfo=UTC)
    total_days = (region_end - region_start).days
    gaps = 3
    if total_days <= gaps or (total_days - gaps) % 4 != 0:
        raise DevelopmentEvaluationPlanError("evaluation region does not tile into four equal windows")
    window = timedelta(days=(total_days - gaps) // 4)
    embargo_gap = timedelta(seconds=EMBARGO_SECONDS)
    development_start = datetime(2024, 1, 1, tzinfo=UTC)
    warmup = timedelta(seconds=WARMUP_SECONDS)
    purge_gap = timedelta(seconds=PURGE_SECONDS)
    folds: list[dict[str, Any]] = []
    evaluation_start = region_start
    for index in range(1, 5):
        evaluation_end = evaluation_start + window
        warmup_start = evaluation_start - warmup
        training_end = evaluation_start - purge_gap
        folds.append({
            "fold_id": f"fold-{index:02d}",
            "walk_forward_mode": "ANCHORED",
            "training": {"start": _iso(development_start), "end": _iso(training_end)},
            "warmup": {"start": _iso(warmup_start), "end": _iso(evaluation_start), "seconds": WARMUP_SECONDS},
            "evaluation": {"start": _iso(evaluation_start), "end": _iso(evaluation_end)},
            "purge_seconds": PURGE_SECONDS,
            "embargo_seconds": EMBARGO_SECONDS if index < 4 else 0,
        })
        evaluation_start = evaluation_end + embargo_gap
    if folds[-1]["evaluation"]["end"] != DEVELOPMENT_END:
        raise DevelopmentEvaluationPlanError("final fold must end exactly at the development boundary")
    return tuple(folds)


def _verify_folds(folds: tuple[Mapping[str, Any], ...]) -> None:
    if len(folds) != 4:
        raise DevelopmentEvaluationPlanError("exactly four chronological folds are required")
    if [str(fold.get("fold_id")) for fold in folds] != [f"fold-{index:02d}" for index in range(1, 5)]:
        raise DevelopmentEvaluationPlanError("fold identifiers must be fold-01..fold-04 in order")
    development_start = _parse_utc(DEVELOPMENT_START)
    development_end = _parse_utc(DEVELOPMENT_END)
    previous_end: datetime | None = None
    folds_so_far: list[Mapping[str, Any]] = []
    for fold in folds:
        if fold.get("walk_forward_mode") != "ANCHORED":
            raise DevelopmentEvaluationPlanError("folds must use the preregistered ANCHORED walk-forward mode")
        if fold.get("warmup", {}).get("seconds") != WARMUP_SECONDS:
            raise DevelopmentEvaluationPlanError("fold warm-up must remain exactly the preregistered 28 days")
        is_final = fold.get("fold_id") == "fold-04"
        required_embargo = 0 if is_final else EMBARGO_SECONDS
        if fold.get("purge_seconds") != PURGE_SECONDS or fold.get("embargo_seconds") != required_embargo:
            raise DevelopmentEvaluationPlanError("fold purge and embargo must remain one day")
        training_start = _parse_utc(str(fold["training"]["start"]))
        training_end = _parse_utc(str(fold["training"]["end"]))
        warmup_start = _parse_utc(str(fold["warmup"]["start"]))
        warmup_end = _parse_utc(str(fold["warmup"]["end"]))
        evaluation_start = _parse_utc(str(fold["evaluation"]["start"]))
        evaluation_end = _parse_utc(str(fold["evaluation"]["end"]))
        if training_start != development_start:
            raise DevelopmentEvaluationPlanError("anchored folds must train from the development start")
        if not (development_start <= warmup_start < evaluation_start < evaluation_end <= development_end):
            raise DevelopmentEvaluationPlanError("fold boundaries are outside the development period")
        if warmup_end != evaluation_start or warmup_start != evaluation_start - timedelta(seconds=WARMUP_SECONDS):
            raise DevelopmentEvaluationPlanError("fold warm-up must end exactly at evaluation start")
        if training_end != evaluation_start - timedelta(seconds=PURGE_SECONDS):
            raise DevelopmentEvaluationPlanError("fold purge boundary is violated")
        if previous_end is not None:
            expected_start = previous_end + timedelta(seconds=int(folds_so_far[-1]["embargo_seconds"]))
            if evaluation_start != expected_start:
                raise DevelopmentEvaluationPlanError("consecutive evaluation windows must be separated by exactly the embargo gap")
        previous_end = evaluation_end
        folds_so_far.append(fold)
    if previous_end is None or _iso(previous_end) != DEVELOPMENT_END:
        raise DevelopmentEvaluationPlanError("final evaluation window must end exactly at the development boundary")


def _evidence_binding(package: Mapping[str, Any]) -> dict[str, str]:
    manifest = package["manifest"]
    return {
        "package_id": str(manifest["package_id"]),
        "content_canonical_sha256": _require_hash(manifest["content_canonical_sha256"], str(manifest["package_id"])),
    }


def verify_year_package_identity_chain(
    year_root: Path,
    monthly_roots: Sequence[Path],
    *,
    deep: bool = False,
) -> dict[str, Any]:
    """Verify the 2024 tick year package without streaming tick rows.

    With deep=False this proves the full identity chain end to end: the
    completion/manifest binding of the year package, the year scope, every
    monthly package's completion/manifest/physical-partition-byte binding
    (SHA-256 over each stored parquet partition), exact agreement of the
    year manifest's per-month references with the freshly verified monthly
    manifests, and internal consistency of the stored year statistics.  The
    canonical normalized hash stays a build-time attestation under this
    mode.  deep=True delegates to the committed deep verifier, which
    additionally re-streams and re-canonicalizes every tick row.
    """
    if deep:
        return verify_2024_development_year_package(year_root, monthly_roots)
    year_root = Path(year_root)
    try:
        completion = json.loads((year_root / "package.complete.json").read_text(encoding="utf-8"))
        manifest_path = year_root / str(completion["manifest_relative_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DevelopmentEvaluationPlanError("TICK_IDENTITY_CHAIN_COMPLETION_INVALID") from exc
    if (
        completion.get("schema_version") != YEAR_COMPLETION_SCHEMA_VERSION
        or completion.get("status") != "COMPLETE"
        or completion.get("package_id") != year_root.name
        or completion.get("manifest_sha256") != _sha256_file(manifest_path)
        or manifest.get("schema_version") != YEAR_MANIFEST_SCHEMA_VERSION
        or manifest.get("package_id") != year_root.name
        or manifest.get("classification") != "DEVELOPMENT_ONLY"
    ):
        raise DevelopmentEvaluationPlanError("TICK_IDENTITY_CHAIN_IDENTITY_MISMATCH")
    if manifest.get("symbol") != SYMBOL or manifest.get("period") != {
        "start_inclusive": DEVELOPMENT_START,
        "end_exclusive": DEVELOPMENT_END,
    }:
        raise DevelopmentEvaluationPlanError("TICK_IDENTITY_CHAIN_SCOPE_INVALID")

    references = manifest.get("monthly_packages")
    if not isinstance(references, list) or len(references) != 12:
        raise DevelopmentEvaluationPlanError("TICK_IDENTITY_CHAIN_MONTHLY_SET_INVALID")
    expected_periods = [f"2024-{month:02d}" for month in range(1, 13)]
    if [str(item.get("period")) for item in references] != expected_periods:
        raise DevelopmentEvaluationPlanError("TICK_IDENTITY_CHAIN_MONTH_ORDER_INVALID")
    reference_ids = [str(item.get("package_id")) for item in references]
    if len(set(reference_ids)) != 12:
        raise DevelopmentEvaluationPlanError("TICK_IDENTITY_CHAIN_MONTH_IDENTITY_DUPLICATE")

    roots_by_id = {Path(root).name: Path(root) for root in monthly_roots}
    if set(roots_by_id) != set(reference_ids) or len(roots_by_id) != len(monthly_roots):
        raise DevelopmentEvaluationPlanError("TICK_IDENTITY_CHAIN_MONTHLY_ROOTS_MISMATCH")

    monthly_manifests: dict[str, Mapping[str, Any]] = {}
    for package_id, root in roots_by_id.items():
        try:
            monthly_manifests[package_id] = verify_exness_package(root)
        except AcquisitionError as exc:
            raise DevelopmentEvaluationPlanError(
                f"TICK_IDENTITY_CHAIN_MONTHLY_PACKAGE_INVALID: {package_id}"
            ) from exc

    total_rows = 0
    monthly_counts: dict[str, int] = {}
    aggregate = {
        "exact_duplicate_rows": 0,
        "duplicate_timestamps_different_prices": 0,
        "long_gap_count": 0,
    }
    for reference in references:
        package_id = str(reference["package_id"])
        monthly = monthly_manifests[package_id]
        try:
            expected_reference = {
                "period": str(reference["period"]),
                "package_id": package_id,
                "raw_archive_sha256": monthly["archive"]["sha256"],
                "manifest_sha256": _sha256_file(roots_by_id[package_id] / "manifest.json"),
                "completion_sha256": _sha256_file(roots_by_id[package_id] / "package.complete.json"),
                "parquet_partitions": [
                    {"relative_path": item["relative_path"], "sha256": item["sha256"]}
                    for item in monthly["partitions"]
                ],
                "logical_canonical_sha256": monthly["canonical_normalized_sha256"],
                "row_count": monthly["statistics"]["row_count"],
                "first_timestamp": monthly["statistics"]["first_timestamp"],
                "last_timestamp": monthly["statistics"]["last_timestamp"],
                "exact_duplicate_rows": monthly["statistics"]["exact_duplicate_rows"],
                "duplicate_timestamps_different_prices": monthly["statistics"][
                    "duplicate_timestamps_different_prices"
                ],
                "gaps": monthly["statistics"]["gaps"],
            }
        except (KeyError, TypeError) as exc:
            raise DevelopmentEvaluationPlanError(
                f"TICK_IDENTITY_CHAIN_MONTHLY_MANIFEST_MALFORMED: {package_id}"
            ) from exc
        if dict(reference) != expected_reference:
            raise DevelopmentEvaluationPlanError(
                f"TICK_IDENTITY_CHAIN_MONTHLY_REFERENCE_MISMATCH: {package_id}"
            )
        total_rows += int(expected_reference["row_count"])
        monthly_counts[expected_reference["period"]] = int(expected_reference["row_count"])
        aggregate["exact_duplicate_rows"] += int(expected_reference["exact_duplicate_rows"])
        aggregate["duplicate_timestamps_different_prices"] += int(
            expected_reference["duplicate_timestamps_different_prices"]
        )
        aggregate["long_gap_count"] += int(expected_reference["gaps"]["long_gap_count"])

    statistics = manifest.get("statistics", {})
    if (
        int(statistics.get("row_count", -1)) != total_rows
        or statistics.get("monthly_row_counts") != monthly_counts
        or statistics.get("aggregate_integrity") != aggregate
        or statistics.get("aggregate_spread_price", {}).get("observation_count") != total_rows
        or statistics.get("first_timestamp") != min(str(item["first_timestamp"]) for item in references)
        or statistics.get("last_timestamp") != max(str(item["last_timestamp"]) for item in references)
    ):
        raise DevelopmentEvaluationPlanError("TICK_IDENTITY_CHAIN_STATISTICS_MISMATCH")
    _require_hash(statistics.get("canonical_normalized_sha256"), "tick year canonical identity")
    return manifest


def verify_input_readiness(
    *,
    data_root: Path,
    worktree: Path,
    contamination_path: Path,
    tick_verification_depth: str = "identity-chain",
) -> dict[str, Any]:
    """Read and hash-verify every input required by the frozen 2024 plan."""
    if tick_verification_depth not in ("identity-chain", "deep-stream"):
        raise DevelopmentEvaluationPlanError("unknown tick verification depth")
    data_root = Path(data_root)
    evidence_root = data_root / "evidence"
    year_root = data_root / "exness-tick-history" / "processed" / "year-packages" / "exness-xauusdm-2024-development-b2a0234a470dd397"
    derived_root = data_root / "derived" / "derived-candles-2024-v1-20260911T195553Z"
    dxy_root = data_root / "dxy" / "dxy-development-2024-v1-20260912T091410.712364Z"
    if not all(path.is_dir() for path in (year_root, derived_root, dxy_root, evidence_root)):
        raise DevelopmentEvaluationPlanError("required empirical input root is missing")

    try:
        year_document = json.loads((year_root / "manifest.json").read_text(encoding="utf-8"))
        monthly_ids = [str(item["package_id"]) for item in year_document["monthly_packages"]]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DevelopmentEvaluationPlanError("year-package monthly identity list is unreadable") from exc
    if len(monthly_ids) != 12 or len(monthly_ids) != len(set(monthly_ids)):
        raise DevelopmentEvaluationPlanError("year package does not bind exactly one identity per month")
    packages_root = data_root / "exness-tick-history" / "processed" / "packages"
    monthly_roots = [packages_root / package_id for package_id in monthly_ids]
    if any(not root.is_dir() for root in monthly_roots):
        raise DevelopmentEvaluationPlanError("year package references a missing monthly package")
    ticks = verify_year_package_identity_chain(
        year_root,
        monthly_roots,
        deep=tick_verification_depth == "deep-stream",
    )
    if ticks.get("symbol") != SYMBOL or ticks.get("period", {}).get("start_inclusive") != DEVELOPMENT_START or ticks.get("period", {}).get("end_exclusive") != DEVELOPMENT_END:
        raise DevelopmentEvaluationPlanError("tick package scope is not exactly development-only XAUUSDm 2024")
    tick_hash = _require_hash(ticks.get("statistics", {}).get("canonical_normalized_sha256"), "tick package")

    candles = verify_candles(derived_root)
    candle_timeframes = tuple(item["timeframe"] for item in candles["partitions"])
    if candle_timeframes != TIMEFRAMES:
        raise DevelopmentEvaluationPlanError("derived candle timeframes are incomplete or reordered")
    if candles["source_canonical_sha256"] != tick_hash:
        raise DevelopmentEvaluationPlanError("derived candles are not bound to the accepted tick package")

    dxy = verify_dxy(dxy_root)
    required_dxy = {"EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF"}
    if set(dxy["constituents"]) != required_dxy or not dxy["causal_dxy"]["record_count"]:
        raise DevelopmentEvaluationPlanError("DXY coverage is incomplete")
    if dxy["source_year_canonical_sha256"] != tick_hash:
        raise DevelopmentEvaluationPlanError("DXY input is not bound to the accepted tick package")

    news = _load_evidence(evidence_root, OFFICIAL_NEWS_ID, "official_news")
    news_events = news["content"].get("events")
    if (
        news["content"].get("status") != "ACCEPTED_DEVELOPMENT_ONLY"
        or not isinstance(news_events, list)
        or len(news_events) < 1
        or news["content"].get("complete") is not True
    ):
        raise DevelopmentEvaluationPlanError("official USD news is not accepted for development")
    spread = _load_evidence(evidence_root, OBSERVED_SPREAD_ID, "observed_spread")
    if spread["content"].get("status") != "ACCEPTED_DEVELOPMENT_ONLY":
        raise DevelopmentEvaluationPlanError("observed spread is not accepted for development")
    cost = _load_evidence(evidence_root, COST_POLICY_ID, "development_cost_policy")
    cost_report = cost_policy.verify_cost_policy(cost["content"])
    metadata = _load_evidence(evidence_root, METADATA_POLICY_ID, "development_metadata_bounds")
    verify_development_metadata_bounds(metadata["content"])
    if metadata["content"].get("development_evaluation_sufficient") is not True:
        raise DevelopmentEvaluationPlanError("metadata policy does not allow development preparation")
    if any(metadata["content"].get(gate) is not False for gate in ("strategy_evaluation_authorized", "accepted_for_final_validation", "holdout_access_authorized", "phase9_authorized")):
        raise DevelopmentEvaluationPlanError("metadata policy improperly authorizes restricted activity")

    contamination = ContaminationRegister.from_path(Path(contamination_path))
    contamination_hash = _sha256_file(contamination_path)
    if not contamination.artifacts:
        raise DevelopmentEvaluationPlanError("contamination register is empty")
    phase8a_template = Path(worktree) / "config" / "validation_plan.example.json"
    if not phase8a_template.is_file():
        raise DevelopmentEvaluationPlanError("Phase 8A preregistration template is missing")
    bindings = cost["content"]["bindings"]
    expected_strategy = cost_policy.strategy_fingerprint(StrategyConfig())
    expected_execution = cost_policy.execution_model_fingerprint()
    expected_risk = cost_policy.risk_policy_fingerprint(RiskPolicy())
    if (bindings["strategy_fingerprint"], bindings["execution_model_fingerprint"], bindings["risk_policy_fingerprint"]) != (expected_strategy, expected_execution, expected_risk):
        raise DevelopmentEvaluationPlanError("strategy, execution, or risk fingerprint drifted from frozen cost policy")

    return {
        "schema_version": "phase8m.input-readiness.v1",
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "tick_verification_depth": tick_verification_depth,
        "ticks": {"package_id": ticks["package_id"], "canonical_sha256": tick_hash, "row_count": ticks["statistics"]["row_count"]},
        "candles": {"manifest_sha256": candles["original_manifest_sha256"], "attestation_id": "derived-candles-attestation-v1-6715e5c64d888215", "timeframes": list(candle_timeframes)},
        "dxy": {"package_id": dxy["package_id"], "canonical_sha256": dxy["causal_dxy"]["canonical_content_sha256"], "record_count": dxy["causal_dxy"]["record_count"], "constituents": sorted(required_dxy)},
        "official_news": _evidence_binding(news),
        "observed_spread": _evidence_binding(spread),
        "cost_policy": {**_evidence_binding(cost), "policy_fingerprint": cost_report["policy_fingerprint"]},
        "metadata_bounds": {
            **_evidence_binding(metadata),
            "policy_fingerprint": metadata["content"]["policy_fingerprint"],
            "mandatory_scenarios": [item["scenario_id"] for item in metadata["content"]["mandatory_scenarios"]],
        },
        "fingerprints": {"strategy": expected_strategy, "execution": expected_execution, "risk": expected_risk, "broker_policy": _broker_policy_fingerprint(worktree)},
        "session_time_rules": {"timezone": "UTC", "strategy_config_fingerprint": StrategyConfig().fingerprint(), "rollover": ["21:55", "22:10"]},
        "contamination_register": {"sha256": contamination_hash, "artifact_count": len(contamination.artifacts), "source": contamination.source},
        "phase8a_preregistration": {"path": "config/validation_plan.example.json", "sha256": _sha256_file(phase8a_template), "fold_count": 4, "purge_seconds": 86_400, "embargo_seconds": 86_400, "warmup_seconds": 2_419_200},
    }


def build_development_evaluation_plan(readiness: Mapping[str, Any]) -> dict[str, Any]:
    folds = _fixed_folds()
    _verify_folds(folds)
    content: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "plan_id": "phase8m.development-evaluation-plan.v1",
        "status": "FROZEN_AWAITING_AUTHORIZED_RUN",
        "frozen_at_utc": FROZEN_AT,
        "symbol": SYMBOL,
        "candidate": {"candidate_id": "phase6-frozen-v1", "strategy_configuration_mutation": "PROHIBITED", "strategy_fingerprint": readiness["fingerprints"]["strategy"]},
        "period": {"start": DEVELOPMENT_START, "end_exclusive": DEVELOPMENT_END, "holdout_accessed": False},
        "input_readiness": dict(readiness),
        "folds": list(folds),
        "cost_scenarios": {"required_all": True, "swap": list(cost_policy.SWAP_SCENARIO_ORDER), "slippage": [item["scenario_id"] for item in cost_policy.SLIPPAGE_SCENARIOS], "cheapest_selection": "PROHIBITED"},
        "metadata_scenarios": {"required_all": True, "scenario_ids": list(readiness["metadata_bounds"].get("mandatory_scenarios", [])), "cheapest_selection": "PROHIBITED"},
        "determinism": {"seeds": [8001], "ordering": "UTC_TIMESTAMP_THEN_STABLE_ROW_AND_ACTION_ID", "parallel_result_ordering": "CANONICAL_SCENARIO_FOLD_ORDER"},
        "metrics": {"minimum_closed_trades_per_fold": 30, "primary": ["net_expectancy", "net_profit_factor", "maximum_executable_equity_drawdown"], "secondary": ["win_rate", "expectancy_r", "cost_ratio", "regime_stability", "concentration"], "bootstrap": {"method": "moving_block_bootstrap", "replicates": 2000, "block_lengths": [5, 10, 20]}},
        "stress_and_sensitivity": {"strategy_parameter_variation": "PROHIBITED", "required": ["all_cost_scenarios", "all_metadata_scenarios", "observed_spread_rejections", "causal_data_gap_rejections", "risk_circuit_rejections"]},
        "reconciliation": {"ledger": "REQUIRED", "trade_lifecycle": "REQUIRED", "risk_circuit": "REQUIRED", "unexplained_difference_tolerance_account_currency": 0.01},
        "outputs": {"relative_root": "phase8/development-evaluations", "per_plan_directory": "plan_fingerprint", "non_overwrite": True, "label": "DEVELOPMENT_PROXY_NOT_HISTORICALLY_VALIDATED"},
        "resource_guards": {"maximum_runtime_seconds": 14_400, "maximum_output_bytes": 10_737_418_240, "checkpoint_interval_events": 100_000, "resume_requires_exact_plan_and_input_hashes": True},
        "prohibitions": {"automatic_tuning": True, "parameter_search": True, "cheapest_scenario_selection": True, "holdout_access": True, "final_validation_claim": True},
        "gates": {"empirical_strategy_evaluation_executed": False, "strategy_evaluation_authorized": False, "holdout_access_authorized": False, "accepted_for_final_validation": False, "phase9_authorized": False},
    }
    content["plan_fingerprint"] = canonical_hash(content)
    verify_development_evaluation_plan(content)
    return content


def verify_development_evaluation_plan(content: Mapping[str, Any]) -> dict[str, Any]:
    if content.get("schema_version") != SCHEMA_VERSION or content.get("symbol") != SYMBOL:
        raise DevelopmentEvaluationPlanError("plan schema or symbol mismatch")
    if content.get("status") != "FROZEN_AWAITING_AUTHORIZED_RUN":
        raise DevelopmentEvaluationPlanError("frozen plan status is not FROZEN_AWAITING_AUTHORIZED_RUN")
    payload = {key: value for key, value in content.items() if key != "plan_fingerprint"}
    if content.get("plan_fingerprint") != canonical_hash(payload):
        raise DevelopmentEvaluationPlanError("plan fingerprint mismatch")
    _verify_folds(tuple(content.get("folds", ())))
    if content["candidate"].get("candidate_id") != "phase6-frozen-v1" or content["candidate"].get("strategy_configuration_mutation") != "PROHIBITED":
        raise DevelopmentEvaluationPlanError("candidate is not frozen")
    if not content["cost_scenarios"].get("required_all") or not content["metadata_scenarios"].get("required_all"):
        raise DevelopmentEvaluationPlanError("all cost and metadata scenarios are mandatory")
    if content["cost_scenarios"].get("cheapest_selection") != "PROHIBITED" or content["metadata_scenarios"].get("cheapest_selection") != "PROHIBITED":
        raise DevelopmentEvaluationPlanError("cheapest scenario selection is prohibited")
    for gate in ("empirical_strategy_evaluation_executed", "strategy_evaluation_authorized", "holdout_access_authorized", "accepted_for_final_validation", "phase9_authorized"):
        if content["gates"].get(gate) is not False:
            raise DevelopmentEvaluationPlanError(f"restricted plan gate {gate} must remain false")
    return {"verified": True, "plan_fingerprint": str(content["plan_fingerprint"])}


def publish_plan(
    *,
    data_root: Path,
    worktree: Path,
    contamination_path: Path,
    tick_verification_depth: str = "identity-chain",
) -> dict[str, str]:
    readiness = verify_input_readiness(
        data_root=data_root,
        worktree=worktree,
        contamination_path=contamination_path,
        tick_verification_depth=tick_verification_depth,
    )
    plan = build_development_evaluation_plan(readiness)
    package, package_id = build_evidence_package(kind=PLAN_KIND, content=plan, source_path=None)
    root = Path(data_root) / "evidence"
    existing = sorted(root.glob("evidence-development_evaluation_plan-v1-*"))
    if any(path.name != package_id for path in existing):
        raise DevelopmentEvaluationPlanError("a conflicting development-evaluation plan is already frozen")
    publish_evidence_package(package, evidence_root=root)
    return {"package_id": package_id, "plan_fingerprint": str(plan["plan_fingerprint"])}


def synthetic_structure_dry_run() -> dict[str, Any]:
    """Pure structural proof; intentionally has no empirical data or metrics."""
    folds = _fixed_folds()
    _verify_folds(folds)
    return {"synthetic": True, "fold_count": len(folds), "performance_computed": False, "mt5_or_network_accessed": False, "gates_unchanged": True}
