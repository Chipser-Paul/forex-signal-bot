"""Preregistered V001 Fold-01 measurement tooling (phase6-development-v2-V001).

DEVELOPMENT_VARIANT_EVIDENCE — V001 — FOLD01 — NOT PROFITABILITY EVIDENCE

Governance
----------
* Variant:            phase6-development-v2-V001 (Canonical FVG ATR-Series Compatibility Repair)
* Primary hypothesis: phase8-v2-H005 (FVG ATR-Series Interface Repair)
* Static audit:       phase8-v2-S001 (Frozen FVG ATR Interface Incompatibility)
* Specification:      docs/PHASE8_V2_VARIANT_V001.md (SHA-256 recorded below)
* Implementation:     b4a1b0e6ab353f513a0df554840344f322e0964c
* Charter:            phase8-v2-research-charter-v1-8527e3a5eec98f53

Frozen measurement contract (preregistered before empirical access):

* The historical pre-V001 store ``fold-01-1d710826193a6767`` is REFUSED as a
  V001 input: its persisted gate payloads were built under the broken FVG
  semantics and may only serve as historical V1/D001 evidence.
* Strategy behaviour is observed through the canonical orchestrator path
  (``evaluate_orchestration_from_features`` via the frozen D001 decision
  evaluator) against a FRESH V001 causal rebuild — never through the old
  payloads.
* The detector-attrition observer is a read-only explanatory mirror that
  calls the production ``bot.analysis.fvg_engine`` functions directly and
  must reproduce ``get_unfilled_fvgs`` exactly for every decision
  (``V001 EXECUTION BLOCKED — FVG OBSERVER NOT EQUIVALENT`` otherwise).
* Unique-FVG identity is fixed here, before data, from timeframe +
  direction + canonical UTC open_time of the displacement candle named by
  ``source_index`` + canonical top/bottom, framed as canonical JSON and
  SHA-256 hashed. Frame-relative indices are never the identity.
* Only the preregistered structural metrics and descriptive summaries are
  emitted; profitability/counterfactual metric names are structurally
  rejected.  Fold 02-04, 2025+ and holdout boundaries fail closed.
* Raw output is written atomically outside Git and content-hashed;
  identity binds ``canonical_git_blob_v1`` committed bytes (the historical
  V1 ``legacy_worktree_bytes_v0`` environment is neither reproduced nor
  used).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backtests.phase8_v2_diagnostic_d001 import (  # noqa: E402
    FOLD01_END,
    FOLD01_START,
    evaluate_orchestration_decision,
)
from bot.analysis.fvg_engine import detect_fvgs, get_unfilled_fvgs  # noqa: E402
from bot.state.gate_inputs import displacement_tier_result  # noqa: E402
from bot.strategy.regime import atr_series  # noqa: E402

V001_ID = "phase6-development-v2-V001"
H005_ID = "phase8-v2-H005"
S001_ID = "phase8-v2-S001"
CHARTER_ID = "phase8-v2-research-charter-v1-8527e3a5eec98f53"
CHARTER_SHA256 = "8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc"
SPEC_SHA256 = "0b1d5ec57c68746f7c346c4b576220460d0dad54d218a2add34dbe6e2adbf8fb"
IMPLEMENTATION_COMMIT = "b4a1b0e6ab353f513a0df554840344f322e0964c"
FINGERPRINT_CONTRACT = "canonical_git_blob_v1"
CLASSIFICATION = "DEVELOPMENT_VARIANT_EVIDENCE — V001 — FOLD01 — NOT PROFITABILITY EVIDENCE"
RESEARCH_DENSITY_TARGET = 90
FROZEN_ATR_PERIOD = 14
FROZEN_DISPLACEMENT_MULT = 1.5
HISTORICAL_STORE_ID = "fold-01-1d710826193a6767"
FOLD01_START_MS = int(datetime.fromisoformat(FOLD01_START).timestamp() * 1000)
FOLD01_END_MS = int(datetime.fromisoformat(FOLD01_END).timestamp() * 1000)

# §21/§28: metric names that must never appear in emitted output.  Exact
# keys are matched exactly; substrings target counterfactual families.
BANNED_METRIC_KEYS = frozenset(
    {
        "pnl", "profit", "profit_factor", "win_rate", "expectancy",
        "drawdown", "sharpe", "returns", "return", "closed_trades", "trades",
        "fills", "fill_count",
    }
)
BANNED_METRIC_SUBSTRINGS = (
    "candidate_count_at_", "threshold_curve", "temporal_lag",
    "lag_distribution", "alternative_", "seven_of_eight", "partial_overlap",
    "optimal_", "sweep_for_",
)

# Development-evidence boundary: sources are all strictly pre-2025.
DEVELOPMENT_END_DATE = date(2024, 12, 31)
HOLDOUT_TOKENS = ("holdout", "hold_out", "final_validation", "validation_fold")
FOLD_PREFIX_ALLOWED = ("fold-01",)


class V001EvalError(RuntimeError):
    """Frozen V001 measurement contract violation."""


class BoundaryError(V001EvalError):
    """Fold/holdout/temporal boundary violation."""


class ReconciliationError(V001EvalError):
    """Observer/production or accounting disagreement."""


# ---------------------------------------------------------------------------
# §3/§12/§28 — identity and boundary guards
# ---------------------------------------------------------------------------


def assert_no_historical_store(identity: Mapping[str, Any]) -> None:
    """Refuse the pre-V001 historical store as a V001 evaluation input."""
    fold_id = str(identity.get("fold_id", ""))
    if fold_id == HISTORICAL_STORE_ID or HISTORICAL_STORE_ID in json.dumps(
        dict(identity), sort_keys=True
    ):
        raise V001EvalError(
            "the historical pre-V001 store fold-01-1d710826193a6767 contains "
            "broken-FVG gate payloads and must not drive V001 evaluation"
        )


def check_store_boundary(identity: Mapping[str, Any]) -> None:
    """Fail closed unless the store is a full-coverage Fold-01 M5 store."""
    fold_id = str(identity.get("fold_id", ""))
    if not fold_id.startswith(FOLD_PREFIX_ALLOWED):
        raise BoundaryError(f"reserved fold store refused for V001: {fold_id!r}")
    if str(identity.get("decision_timeframe")) != "M5":
        raise BoundaryError(
            f"store decision timeframe is not M5: {identity.get('decision_timeframe')!r}"
        )
    start = int(identity.get("evaluation_start_ms", -1))
    end = int(identity.get("evaluation_end_ms", -1))
    if (start, end) != (FOLD01_START_MS, FOLD01_END_MS):
        raise BoundaryError(
            "store evaluation window is not Fold 01: "
            f"[{start}, {end}) expected [{FOLD01_START_MS}, {FOLD01_END_MS})"
        )
    if str(identity.get("coverage")) != "full":
        raise BoundaryError(
            f"store coverage is not full: {identity.get('coverage')!r}"
        )


def check_fold_boundary(start_ms: int, end_ms: int) -> None:
    if (int(start_ms), int(end_ms)) != (FOLD01_START_MS, FOLD01_END_MS):
        raise BoundaryError(
            f"requested window is not the preregistered Fold-01 boundary: "
            f"[{start_ms}, {end_ms})"
        )
    if datetime.fromtimestamp(int(end_ms) / 1000, tz=timezone.utc).year > 2024:
        raise BoundaryError("2025+ data is outside the V001 development boundary")


def reject_holdout_path(path: str | Path) -> None:
    """Refuse holdout/final-validation/2025+ paths by name and by year."""
    import re  # noqa: PLC0415

    text = str(path).lower()
    if any(token in text for token in HOLDOUT_TOKENS):
        raise BoundaryError(f"holdout evidence path refused: {path!r}")
    for part in Path(str(path)).parts:
        for token in re.findall(r"\d{4}", part):
            if int(token) >= 2025:
                raise BoundaryError(f"2025+ evidence path refused: {path!r}")


def _assert_source_dates_within_development(source_identities: Mapping[str, Any]) -> None:
    """Recorded source identities must stay inside the development period.

    Checks structural date markers only (year partitions, ISO date prefixes,
    holdout naming) — never hash digests, whose hex can coincidentally
    contain digit substrings.
    """
    for name, value in sorted(source_identities.items()):
        text = json.dumps(value, sort_keys=True, default=str)
        if "holdout" in text.lower():
            raise BoundaryError(
                f"source identity {name!r} references holdout evidence"
            )
        for marker in ("year=2025", "year=2026", "year=58041"):
            if marker in text:
                raise BoundaryError(
                    f"source identity {name!r} references a 2025+ partition"
                )
        for date_marker in ("2025-", "2026-"):
            if date_marker in text:
                raise BoundaryError(
                    f"source identity {name!r} references a 2025+ date"
                )


# ---------------------------------------------------------------------------
# §8 — unique FVG identity (frozen before empirical access)
# ---------------------------------------------------------------------------


def _canonical_material(material: Mapping[str, Any]) -> str:
    return json.dumps(material, sort_keys=True, separators=(",", ":"), allow_nan=False)


def utc_date(value: datetime) -> date:
    """Canonical UTC calendar date of a decision (naive values read as UTC)."""
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(timezone.utc).date()


def unique_fvg_identity(
    fvg: Mapping[str, Any], decision_at: datetime, entry_rows: Iterable[Mapping[str, Any]]
) -> str:
    """Deterministic cross-frame identity of one historical FVG zone.

    Derived only from: timeframe; direction; the canonical UTC ``open_time``
    of the displacement candle named by ``source_index`` (resolved against
    the decision's own entry rows — never the frame-relative index alone);
    and the canonical top/bottom levels.  Canonical JSON framing + SHA-256.
    """
    rows = list(entry_rows)
    source_index = int(fvg["source_index"])
    if not 0 <= source_index < len(rows):
        raise ReconciliationError(
            f"fvg source_index {source_index} outside the entry frame "
            f"({len(rows)} rows)"
        )
    open_time = rows[source_index].get("open_time")
    if open_time is None:
        raise ReconciliationError("entry row without open_time cannot anchor identity")
    if isinstance(open_time, datetime):
        stamp = open_time.isoformat()
    else:
        stamp = str(pd_open_time_iso(open_time))
    material = {
        "timeframe": str(fvg["timeframe"]),
        "direction": str(fvg["direction"]),
        "source_open_time_utc": stamp,
        "top": float(fvg["top"]),
        "bottom": float(fvg["bottom"]),
    }
    return hashlib.sha256(_canonical_material(material).encode("utf-8")).hexdigest()


def pd_open_time_iso(value: Any) -> str:
    """Canonical UTC ISO rendering of a payload open_time cell."""
    import pandas as pd  # noqa: PLC0415

    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC").isoformat()


# ---------------------------------------------------------------------------
# §7 — read-only detector-attrition observer (production-equivalent mirror)
# ---------------------------------------------------------------------------


def reconstruct_entry_frame(entry_rows: Iterable[Mapping[str, Any]]):
    """Rebuild the exact M5 frame the production detector consumed.

    Payload ``entry_rows`` is the frozen ``entry.to_dict("records")`` taken
    inside ``build_gate_inputs``; timestamps arrive ISO-rendered by
    ``_freeze``.  Reconstruction is the identity operation on that data —
    it re-executes the production functions on the very frame they saw.
    """
    import pandas as pd  # noqa: PLC0415

    rows = list(entry_rows)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    stamp = pd.to_datetime(frame["open_time"], utc=True)
    return pd.DataFrame(
        {
            "open_time": stamp,
            "open": frame["open"].astype(float),
            "high": frame["high"].astype(float),
            "low": frame["low"].astype(float),
            "close": frame["close"].astype(float),
        }
    )


def mirror_fvg_stages(entry_frame: Any, direction: str) -> dict[str, Any]:
    """Stage-level attrition observer over the production V001 detector.

    Calls the frozen production functions directly (``regime.atr_series`` and
    ``detect_fvgs`` with the frozen parameters); classifies each causal
    three-candle window through the identical gates, then asserts that the
    observer's final same-direction unfilled list equals
    ``get_unfilled_fvgs``.  Structural disagreement raises
    ``ReconciliationError`` (fail closed).
    """
    import pandas as pd  # noqa: PLC0415

    if FROZEN_ATR_PERIOD != 14 or FROZEN_DISPLACEMENT_MULT != 1.5:
        raise V001EvalError("frozen detector parameters changed")
    atr_period = 14
    displacement_mult = 1.5

    frame = entry_frame
    n = 0 if frame is None or frame.empty else len(frame)
    min_rows = atr_period + 3
    stage_a_pass = n >= min_rows

    windows_total = max(0, n - 2)
    atr_values = atr_series(frame, atr_period) if stage_a_pass else None
    atr_head_count = 0
    if atr_values is not None:
        for value in atr_values:
            if pd.isna(value) or float(value) <= 0:
                atr_head_count += 1
            else:
                break

    atr_valid_windows = 0
    displacement_passes = 0
    bullish = 0
    bearish = 0
    no_gap = 0
    ratios: list[float] = []
    # Production short-circuits to [] before any iteration when stage A
    # fails (atr_values None); the mirror must not iterate then either.
    for i in range(2, n if atr_values is not None else 0):
        # Guard order mirrors the production detector exactly:
        # len-guard, then NaN, then positivity.
        if i - 1 >= len(atr_values):
            continue
        atr_val = atr_values.iloc[i - 1]
        if pd.isna(atr_val):
            continue
        atr_val = float(atr_val)
        if atr_val <= 0:
            continue
        atr_valid_windows += 1
        c2 = frame.iloc[i - 1]
        body = abs(float(c2["close"]) - float(c2["open"]))
        if body >= atr_val * displacement_mult:
            displacement_passes += 1
            ratios.append(body / atr_val)
            c1 = frame.iloc[i - 2]
            c3 = frame.iloc[i]
            if float(c1["high"]) < float(c3["low"]):
                bullish += 1
            elif float(c1["low"]) > float(c3["high"]):
                bearish += 1
            else:
                no_gap += 1

    zones = get_unfilled_fvgs(frame, timeframe="M5", direction=direction)
    detected_all = detect_fvgs(frame, timeframe="M5")
    same_direction = [z for z in detected_all if z["direction"] == direction]
    opposite_direction = [z for z in detected_all if z["direction"] != direction]
    filled = [z for z in detected_all if z["filled"]]
    unfilled = [z for z in detected_all if not z["filled"]]

    return {
        "windows_total": windows_total,
        "stage_a_pass": stage_a_pass,
        "atr_valid_windows": atr_valid_windows,
        "atr_warmup_windows": windows_total - atr_valid_windows,
        "atr_series_head_unavailable": atr_head_count,
        "displacement_passes": displacement_passes,
        "gap_bullish": bullish,
        "gap_bearish": bearish,
        "gap_none": no_gap,
        "zones_same_direction_all": len(same_direction),
        "zones_opposite_direction": len(opposite_direction),
        "zones_filled": len(filled),
        "zones_unfilled": len(unfilled),
        "body_atr_ratios": ratios,
        "atr_at_entry_tail": (
            float(atr_values.iloc[-1])
            if atr_values is not None and not pd.isna(atr_values.iloc[-1])
            else None
        ),
        # §7 hard equality: observer final list == production function.
        "final_same_direction_unfilled": zones,
    }


def _final_list_signature(zones: Iterable[Mapping[str, Any]]) -> str:
    material = [
        {
            "type": str(zone.get("type")),
            "direction": str(zone.get("direction")),
            "top": float(zone["top"]),
            "bottom": float(zone["bottom"]),
            "filled": bool(zone.get("filled")),
            "timeframe": str(zone.get("timeframe")),
            "source_index": int(zone.get("source_index")),
            "displacement_body": float(zone.get("displacement_body", 0.0)),
        }
        for zone in zones
    ]
    return _canonical_material(material)


# ---------------------------------------------------------------------------
# Per-decision observation (canonical orchestrator path + payload mirror)
# ---------------------------------------------------------------------------


def observe_decision(
    snapshot: Any,
    prior_state_record: Any,
    *,
    max_concurrent_trades: int = 2,
) -> tuple[dict[str, Any], Any]:
    """One V001 decision: canonical evaluation + payload-derived observer.

    The top-level action/gate/funnel state comes verbatim from the frozen
    D001 decision evaluator (production orchestrator path).  The detector
    observer re-executes production FVG semantics on the decision's own
    payload entry rows and is reconciled against the payload's final
    ``fvgs`` list on every decision.
    """
    row, next_record = evaluate_orchestration_decision(
        snapshot, prior_state_record, max_concurrent_trades=max_concurrent_trades
    )
    row["available_at_iso"] = (
        datetime.fromtimestamp(int(snapshot.available_at_ms) / 1000, tz=timezone.utc)
        .isoformat()
    )
    if row.get("action") == "error":
        return row, next_record

    payload = json.loads(snapshot.gate_payload) if snapshot.gate_payload else {}
    htf_bias = str(payload.get("htf_bias") or "")
    displacement = payload.get("displacement") or {}
    payload_fvgs = payload.get("fvgs") or []
    entry_rows = payload.get("entry_rows") or []
    row["decision_at_ms"] = int(snapshot.available_at_ms)

    # Detector-eligible = the payload proves get_unfilled_fvgs executed.
    # The exact production cascade is re-derived with the production
    # classifier itself: displacement must be valid and must not be tier-1
    # log-only (build_gate_inputs short-circuits before the FVG call
    # otherwise).  Re-running ``displacement_tier_result`` on the payload's
    # own frozen profile/displacement reproduces the build-time decision by
    # construction.
    displacement_valid = bool(displacement.get("valid"))
    eligible = False
    eligibility_source = "no_displacement"
    if displacement_valid:
        tier = displacement_tier_result(payload.get("profile") or {}, displacement)
        tier_rejects = tier["tier"] == "tier_1" and tier["action"] == "log_only"
        if tier_rejects:
            eligibility_source = "tier1_log_only"
        else:
            eligibility_source = "displacement_valid_tier_ok"
            eligible = True

    row["detector_eligible"] = eligible
    row["eligibility_source"] = eligibility_source

    mirror: dict[str, Any] | None = None
    if eligible:
        frame = reconstruct_entry_frame(entry_rows)
        mirror = mirror_fvg_stages(frame, htf_bias)
        produced = _final_list_signature(payload_fvgs)
        expected = _final_list_signature(mirror["final_same_direction_unfilled"])
        if produced != expected:
            raise ReconciliationError(
                f"FVG observer not equivalent at {row['decision_id']}: "
                "payload fvgs != production get_unfilled_fvgs"
            )
        row["mirror"] = {
            key: value
            for key, value in mirror.items()
            if key != "final_same_direction_unfilled"
        }
        row["final_fvg_count"] = len(payload_fvgs)
        row["final_fvg_present"] = bool(payload_fvgs)
        row["fvg_direction_counts"] = _direction_counts(payload_fvgs)
        row["fvg_widths"] = [
            float(zone["top"]) - float(zone["bottom"]) for zone in payload_fvgs
        ]
        identities = []
        for zone in payload_fvgs:
            identities.append(unique_fvg_identity(zone, row["available_at_iso"], entry_rows))
        row["unique_fvg_identities"] = sorted(set(identities))
    else:
        row["final_fvg_count"] = 0
        row["final_fvg_present"] = False
        row["fvg_direction_counts"] = {}
        row["fvg_widths"] = []
        row["unique_fvg_identities"] = []
    row["reconciliation_available"] = eligible
    return row, next_record


def _direction_counts(zones: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for zone in zones:
        key = str(zone.get("direction"))
        counts[key] = counts.get(key, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Aggregation (preregistered structural surface only)
# ---------------------------------------------------------------------------


def _summary(values: Iterable[float]) -> dict[str, Any]:
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return {"count": 0}
    def quartile(q: float) -> float:
        position = q * (len(ordered) - 1)
        low = int(position)
        high = min(low + 1, len(ordered) - 1)
        weight = position - low
        return ordered[low] * (1.0 - weight) + ordered[high] * weight
    return {
        "count": len(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        "median": quartile(0.5),
        "q1": quartile(0.25),
        "q3": quartile(0.75),
    }


def aggregate_v001(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Reduce decision rows to the preregistered V001 metric surface."""
    rows = list(rows)
    actions: dict[str, int] = {}
    reasons: dict[str, int] = {}
    funnel: dict[str, dict[str, int]] = {}
    eligibility_counts: dict[str, int] = {}
    eligible = 0
    stage_a_fail_decisions = 0
    final_present = 0
    final_count_total = 0
    fvg_direction: dict[str, int] = {}
    stage_totals = {
        "windows_total": 0,
        "atr_warmup_windows": 0,
        "atr_valid_windows": 0,
        "displacement_passes": 0,
        "gap_bullish": 0,
        "gap_bearish": 0,
        "gap_none": 0,
        "zones_same_direction_all": 0,
        "zones_opposite_direction": 0,
        "zones_filled": 0,
        "zones_unfilled": 0,
    }
    ratios: list[float] = []
    atr_values: list[float] = []
    widths: list[float] = []
    unique_identities: set[str] = set()
    pair_decisions = 0
    zone_pair_total = 0
    overlap_true = 0
    overlap_false = 0
    candidate_ready = 0
    reconciled = 0

    for row in rows:
        actions[str(row["action"])] = actions.get(str(row["action"]), 0) + 1
        reasons[str(row["reason"])] = reasons.get(str(row["reason"]), 0) + 1
        if row["action"] == "candidate_ready":
            candidate_ready += 1
        for name, passed in row.get("gate_results", {}).items():
            slot = funnel.setdefault(name, {"entered": 0, "passed": 0, "failed": 0})
            slot["entered"] += 1
            slot["passed" if passed else "failed"] += 1
        if row.get("detector_eligible"):
            eligible += 1
            eligibility_counts[str(row.get("eligibility_source"))] = (
                eligibility_counts.get(str(row.get("eligibility_source")), 0) + 1
            )
            mirror = row.get("mirror") or {}
            if not mirror.get("stage_a_pass", True):
                stage_a_fail_decisions += 1
            for key in stage_totals:
                stage_totals[key] += int(mirror.get(key, 0))
            ratios.extend(mirror.get("body_atr_ratios") or [])
            if mirror.get("atr_at_entry_tail") is not None:
                atr_values.append(float(mirror["atr_at_entry_tail"]))
            widths.extend(row.get("fvg_widths") or [])
        if row.get("final_fvg_present"):
            final_present += 1
            final_count_total += int(row.get("final_fvg_count", 0))
            for direction, count in (row.get("fvg_direction_counts") or {}).items():
                fvg_direction[direction] = fvg_direction.get(direction, 0) + int(count)
        for identity in row.get("unique_fvg_identities") or []:
            unique_identities.add(identity)
        if row.get("reconciliation_available"):
            reconciled += 1
        ob = row.get("ob") or {}
        fvg_present = bool(row.get("final_fvg_present"))
        if bool(ob.get("valid")) and fvg_present:
            pair_decisions += 1
            zone_pair_total += max(1, int(row.get("final_fvg_count", 0)))
            overlap_value = (row.get("overlap") or {}).get("canonical_fvg_in_ob")
            if overlap_value is True:
                overlap_true += 1
            elif overlap_value is False:
                overlap_false += 1

    if len(rows) and reconciled == 0:
        raise ReconciliationError("no decision carried an FVG observer reconciliation")

    density = {
        "target": RESEARCH_DENSITY_TARGET,
        "candidate_ready": candidate_ready,
        "meets_target": candidate_ready >= RESEARCH_DENSITY_TARGET,
        "insufficient": 0 < candidate_ready < RESEARCH_DENSITY_TARGET,
        "zero": candidate_ready == 0,
    }
    return {
        "decisions_total": len(rows),
        "actions": dict(sorted(actions.items())),
        "reasons": dict(sorted(reasons.items())),
        "gate_funnel": {name: funnel[name] for name in sorted(funnel)},
        "detector_eligible_decisions": eligible,
        "eligibility_source_counts": dict(sorted(
            eligibility_counts.items()
        )),
        "stage_a_fail_decisions": stage_a_fail_decisions,
        "attrition_stage_totals": stage_totals,
        "final_fvg": {
            "decisions_with_final_fvg": final_present,
            "total_final_fvg_count": final_count_total,
            "direction_counts": dict(sorted(fvg_direction.items())),
            "unique_identities": len(unique_identities),
        },
        "descriptive_summaries": {
            "atr_at_entry_tail": _summary(atr_values),
            "body_atr_ratio": _summary(ratios),
            "fvg_width": _summary(widths),
        },
        "ob_fvg_coexistence": {
            "decisions_with_valid_ob_and_fvg": pair_decisions,
            "ob_fvg_zone_pairs": zone_pair_total,
            "canonical_overlap_true": overlap_true,
            "canonical_overlap_false": overlap_false,
        },
        "candidate_ready": candidate_ready,
        "research_density": density,
        "observer_reconciled_decisions": reconciled,
    }


# ---------------------------------------------------------------------------
# Evaluation run + deterministic external output
# ---------------------------------------------------------------------------


def _snapshot_rows(store: Any):
    """Iterate the store as verified snapshots (canonical machinery)."""
    from bot.validation.market_feature_store import (  # noqa: PLC0415
        _snapshot_from_row,
    )

    identity = dict(store.identity)
    assert_no_historical_store(identity)
    check_store_boundary(identity)
    for position in range(store.table.num_rows):
        raw = {
            name: store.table.column(name)[position].as_py()
            for name in store.table.column_names
        }
        yield _snapshot_from_row(raw)


def run_v001_evaluation(
    store: Any,
    *,
    canonical_commit: str,
    tooling_commit: str,
    raw_source_identities: Mapping[str, Any],
    rebuilt_store_identity: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes]:
    """Execute the preregistered V001 measurement over the fresh store."""
    identity = dict(store.identity)
    assert_no_historical_store(identity)
    check_store_boundary(identity)
    _assert_source_dates_within_development(raw_source_identities)
    reject_holdout_path(str(raw_source_identities))
    reject_holdout_path(str(rebuilt_store_identity))
    from bot.analysis.fvg_engine import detect_fvgs as _production  # noqa: F401, PLC0415

    rows = []
    state_record = None
    started = datetime.now(timezone.utc).isoformat()
    for snapshot in _snapshot_rows(store):
        row, state_record = observe_decision(snapshot, state_record)
        rows.append(row)
    finished = datetime.now(timezone.utc).isoformat()
    aggregate = aggregate_v001(rows)
    if aggregate["decisions_total"] == 0:
        raise V001EvalError("fresh V001 store yielded zero decisions")

    if aggregate["candidate_ready"] >= RESEARCH_DENSITY_TARGET:
        outcome = "FUNCTIONAL_REPAIR_WITH_ADEQUATE_DENSITY"
    elif aggregate["candidate_ready"] > 0:
        outcome = "FUNCTIONAL_REPAIR_WITH_INSUFFICIENT_DENSITY"
    elif aggregate["final_fvg"]["decisions_with_final_fvg"] > 0 or (
        aggregate["detector_eligible_decisions"] > 0
        and aggregate["attrition_stage_totals"]["atr_valid_windows"] > 0
    ):
        outcome = "FUNCTIONAL_REPAIR_NO_CANDIDATES"
    else:
        outcome = "IMPLEMENTATION_REPAIR_FAILED"

    h005_disposition = (
        "SUPPORTED_BY_V001"
        if outcome != "IMPLEMENTATION_REPAIR_FAILED"
        else "INCONCLUSIVE_V001"
    )

    material = {
        "schema": "phase8_v2_v001_result_v1",
        "variant_id": V001_ID,
        "research_identity": "phase6-development-v2",
        "hypothesis_id": H005_ID,
        "static_audit": S001_ID,
        "charter_id": CHARTER_ID,
        "charter_sha256": CHARTER_SHA256,
        "specification_sha256": SPEC_SHA256,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "measurement_tooling_commit": tooling_commit,
        "canonical_source_commit_used": canonical_commit,
        "fingerprint_contract": FINGERPRINT_CONTRACT,
        "fold_boundary": {"start": FOLD01_START, "end": FOLD01_END},
        "fold_boundary_ms": {"start": FOLD01_START_MS, "end": FOLD01_END_MS},
        "raw_source_identities": dict(sorted(raw_source_identities.items())),
        "rebuilt_store_identity": dict(sorted(rebuilt_store_identity.items())),
        "classification": CLASSIFICATION,
        "execution": {"started_utc": started, "finished_utc": finished},
        "budget": {
            "diagnostics_executed": "1 / 12",
            "strategy_variants_observed_after_this_run": "1 / 8",
            "numeric_parameter_trials": "0 / 4",
            "upward_budget_revision_lock": "ACTIVE",
        },
        "metrics": aggregate,
        "outcome_classification": outcome,
        "h005_disposition": h005_disposition,
        "no_profitability_metrics": True,
        "reserved_folds_untouched": True,
        "holdout_untouched": True,
    }
    _reject_banned_metrics(material)
    rendered = _canonical_material(material).encode("utf-8")
    return material, rendered


def _reject_banned_metrics(node: Any, path: str = "material") -> None:
    """Structurally refuse any prohibited metric key anywhere in the output.

    Exact-key bans and counterfactual-family substrings only, so honest
    negation/record keys (e.g. ``no_profitability_metrics``) pass while any
    real performance or counterfactual metric name is refused.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            key_text = str(key).lower()
            if key_text in BANNED_METRIC_KEYS or any(
                banned in key_text for banned in BANNED_METRIC_SUBSTRINGS
            ):
                raise V001EvalError(f"prohibited metric key {path}.{key}")
            _reject_banned_metrics(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_banned_metrics(value, f"{path}[{index}]")


def write_result(material: Mapping[str, Any], rendered: bytes, output_dir: Path) -> tuple[Path, str]:
    """Atomically write the deterministic result; refuse overwrite; return path+sha."""
    output_dir = Path(output_dir)
    reject_holdout_path(str(output_dir))
    target = output_dir / "phase6-development-v2-V001_result.json"
    if target.exists():
        raise V001EvalError(f"result already exists; refusing overwrite: {target}")
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = output_dir / f".staging-{uuid.uuid4().hex[:8]}"
    staging.write_bytes(rendered)
    os.replace(staging, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != hashlib.sha256(rendered).hexdigest():
        raise V001EvalError("result hash mismatch after write")
    return target, digest


def read_result_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="fresh V001 Fold-01 store parquet path")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--canonical-commit", default=IMPLEMENTATION_COMMIT)
    parser.add_argument("--tooling-commit", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    from bot.validation.market_feature_store import load_feature_store  # noqa: PLC0415

    store = load_feature_store(Path(args.store), verify_rows=True)
    identity = dict(store.identity)
    raw_sources = {
        "input_index_sha256": identity.get("input_index_sha256"),
        "source_identities": identity.get("source_identities", {}),
        "plan_fingerprint": identity.get("plan_fingerprint"),
        "plan_package_id": identity.get("plan_package_id"),
        "config_fingerprint": identity.get("config_fingerprint"),
        "pipeline_fingerprint": identity.get("pipeline_fingerprint"),
    }
    material, rendered = run_v001_evaluation(
        store,
        canonical_commit=args.canonical_commit,
        tooling_commit=args.tooling_commit,
        raw_source_identities=raw_sources,
        rebuilt_store_identity={
            "store_sha256": identity.get("rows_sha256"),
            "store_name": Path(args.store).name,
            "store_identity_sha256": identity.get("store_identity_sha256"),
        },
    )
    target, digest = write_result(material, rendered, Path(args.output_dir))
    print(
        json.dumps(
            {
                "result": str(target),
                "sha256": digest,
                "outcome": material["outcome_classification"],
                "h005": material["h005_disposition"],
                "candidate_ready": material["metrics"]["candidate_ready"],
                "decisions": material["metrics"]["decisions_total"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
