"""Preregistered D005 Fold-01 structural diagnostic tooling (H003).

DEVELOPMENT_DIAGNOSTIC_EVIDENCE — D005 — FOLD01 — NOT PROFITABILITY EVIDENCE

Governance
----------
* Diagnostic:        phase8-v2-D005 (Temporal OB/FVG Association and
                     Final-Surface Attrition)
* Primary hypothesis: phase8-v2-H003 (preregistered 2026-09-21; statement,
                     rationale, expected effects and failure mode preserved
                     EXACTLY — never rewritten by D005)
* Contextual prior:  H001 SUPPORTED_BY_D003_D004_SYNTHESIS; H002
                     SUPPORTED_BY_D003; H006 SUPPORTED_BY_D004; H007
                     represented by phase6-development-v2-V002-R001
* Specification:     docs/PHASE8_V2_DIAGNOSTIC_D005.md (SHA-256 below)
* Charter:           phase8-v2-research-charter-v1-8527e3a5eec98f53

READ-ONLY diagnostic (frozen preregistration):

* Population: V002 Gate-11 entrants whose frozen V002 structural-pair
  evaluation reports ``structurally_active == True`` AND
  ``fvg_associated == False`` under final-FVG semantics.  The population is
  derived naturally during execution; no expected count is encoded.
* Causal FVG history: ONLY candles whose ``available_at <= decision_at`` are
  inspected.  The frozen canonical detector (``bot.analysis.fvg_engine``) is
  reused exactly — no alternate detector, no threshold change, no numeric
  trial.  Non-causal trailing rows are excluded and their count recorded;
  they are never inspected.
* Final-surface reconciliation (fail closed): the frozen final
  same-direction unfilled FVG surface is recomputed from the causal frame
  (``get_unfilled_fvgs(entry, "M5", direction=htf_bias)`` — the exact
  production store expression) and must reconcile EXACTLY with the persisted
  V002 input surface on every observed decision.
* Temporal FVG universe: all causally detected canonical FVGs, categorized
  by formation relative to OB confirmation (BEFORE / AT / AFTER), direction
  (same / opposite) and fill state (unfilled at decision / filled before).
* Causal formation clock (D005-TC001): the FVG formation timestamp is the
  COMPLETION candle's ``available_at`` — the instant the three-candle
  pattern becomes observable (completion row ``source_index + 1``,
  unchanged).  The OB clock is the canonical ``block.confirmed_at``
  (confirmation-candle ``available_at``).  Ordering and signed bar distance
  compare availability to availability; the completion candle's
  ``open_time`` is recorded descriptively only (``fvg_completion_open_time``)
  and never drives ordering, distance or H003 membership.
* H003 temporal association (spec section 9): ORDERING ONLY — a
  primary-population decision satisfies H003 iff at least one same-direction
  canonical FVG in the causal frame was formed AT OR AFTER canonical OB
  confirmation.  No proximity, lag tolerance or temporal window exists
  anywhere in this tooling; the fill state is descriptive universe metadata
  and never part of the rule.
* ``h003_temporal_association_decisions`` is a structural count only — never
  ``candidate_ready``, ``rescued_candidates`` or ``candidate_if_temporal``.
  The headroom classification (29-observation arithmetic bound) is a
  NECESSARY feasibility condition only and is never an H003 support rule.
* No counterfactual candidates, no downstream relaxation, no temporal
  parameter search, no profitability metrics.  ``bot/strategy/variant_v002.py``
  and the frozen V002 measurement tooling are NOT modified by D005.
* Fold 01 ONLY; the historical store ``fold-01-1d710826193a6767`` is refused;
  Tier B (Folds 02-04), holdout and 2025+ fail closed.
* THIS TOOLING IS NOT EXECUTED BY THE FREEZE TASK.  Empirical execution
  requires separate supervisory authorization; at the instant first Fold-01
  D005 observation occurs, diagnostics become permanently 4 / 12.
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

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backtests.phase8_v2_diagnostic_d001 import (  # noqa: E402
    FOLD01_END,
    FOLD01_START,
    _reference_check_failed,
    _snapshot_rows,
    classify_snapshot,
    evaluate_orchestration_decision,
    reconcile_accounting,
)
from backtests.phase8_v2_variant_v001_eval import reject_holdout_path  # noqa: E402
from backtests.phase8_v2_variant_v002_eval import (  # noqa: E402
    _entry_frame,
    _gate_funnel,
    _reject_banned_metrics,
    assert_store_semantic_compatibility,
    check_store_boundary,
    observe_v002_decision,
)

D005_ID = "phase8-v2-D005"
H003_ID = "phase8-v2-H003"
V002_ID = "phase6-development-v2-V002"
CHARTER_ID = "phase8-v2-research-charter-v1-8527e3a5eec98f53"
CHARTER_SHA256 = "8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc"
SPEC_SHA256 = "2b820d608b1d881720369b045366e1986c9cf07f25ce44a2bba26ce837029ed8"
SPECIFICATION_DOCUMENT = "docs/PHASE8_V2_DIAGNOSTIC_D005.md"
CLASSIFICATION = (
    "DEVELOPMENT_DIAGNOSTIC_EVIDENCE — D005 — FOLD01 — NOT PROFITABILITY EVIDENCE"
)
TOOLING_RELPATH = "backtests/phase8_v2_diagnostic_d005.py"
V002_STRATEGY_MODULE = "bot/strategy/variant_v002.py"
V002_STRATEGY_GIT_BLOB_SHA = "8272c28552c05067b6dc3ba039ee8df2dbbfb8b4"
HISTORICAL_STORE_ID = "fold-01-1d710826193a6767"
FOLD01_START_MS = int(datetime.fromisoformat(FOLD01_START).timestamp() * 1000)
FOLD01_END_MS = int(datetime.fromisoformat(FOLD01_END).timestamp() * 1000)

#: Arithmetic feasibility bound ONLY (spec section 13): 90 - 61.  Never an
#: H003 support threshold, never a parameter, never a tuning objective.
TIER_A_ARITHMETIC_HEADROOM_OBSERVATIONS = 29

#: Preregistered attrition categories (spec section 11) — exhaustive and
#: mutually exclusive under the frozen detector; anything else fails closed.
ATTRITION_CATEGORIES = (
    "NO_SAME_DIRECTION_FVG_EVER",
    "SAME_DIRECTION_FVG_EXISTED_BUT_FILLED",
    "SAME_DIRECTION_FVG_PRE_OB_ONLY",
    "OPPOSITE_DIRECTION_ONLY",
)

#: D005-specific banned output concepts (spec section 16/20).  The V002
#: banned list is additionally applied to the whole document.
D005_BANNED_SUBSTRINGS = (
    "candidate_if_temporal",
    "rescued_candidate",
    "alternate_lag",
    "optimal_lag",
    "temporal_threshold",
    "candidate_without_final_fvg",
    "lag_cutoff",
    "lag_search",
    "lag_window",
    "pnl",
    "profit",
    "win_rate",
    "expectancy",
    "drawdown",
    "sharpe",
    "closed_trades",
)

BAR_MINUTES = 5


class D005Error(RuntimeError):
    """Frozen D005 diagnostic contract violation (fail closed)."""


class BoundaryError(D005Error):
    """Fold/holdout/temporal boundary violation."""


class ReconciliationError(D005Error):
    """Structural reconciliation failed (population/identity/accounting)."""


class FinalSurfaceMismatch(D005Error):
    """Persisted final-FVG surface does not reconcile with canonical recomputation."""


# ---------------------------------------------------------------------------
# Final-surface reconciliation (spec section 7/15 — fail closed)
# ---------------------------------------------------------------------------


def _reconcile_final_surface(
    decision_id: Any,
    persisted: Iterable[Mapping[str, Any]],
    recomputed: Iterable[Mapping[str, Any]],
) -> None:
    """Exact reconciliation of the persisted final same-direction FVG surface.

    Both lists must contain the same zones in the same order with the same
    fields (the recomputation is the exact production store expression over
    the causal frame).  Any disagreement fails closed; no temporal
    aggregation may mask a mismatch.
    """
    persisted_list = [dict(zone) for zone in persisted]
    recomputed_list = [dict(zone) for zone in recomputed]
    if persisted_list == recomputed_list:
        return
    raise FinalSurfaceMismatch(
        f"decision {decision_id!r}: persisted final-FVG surface does not "
        f"reconcile with canonical recomputation over the causal frame "
        f"(persisted {len(persisted_list)} zones vs recomputed "
        f"{len(recomputed_list)} zones); D005 refuses to use historical FVG "
        "observations that fail final-surface reconciliation"
    )


# ---------------------------------------------------------------------------
# Per-decision observation (read-only; frozen V002 observation is input)
# ---------------------------------------------------------------------------


def _parse_timestamp(decision_id: Any, field: str, value: Any) -> datetime:
    try:
        parsed = pd.Timestamp(value)
        if parsed is pd.NaT or pd.isna(parsed):
            raise ValueError("timestamp is NaT")
        return parsed.to_pydatetime().astimezone(timezone.utc)
    except (TypeError, ValueError) as error:
        raise D005Error(
            f"decision {decision_id!r}: malformed {field} timestamp "
            f"{value!r}: {error}"
        ) from error


def _bar_distance(decision_id: Any, start: datetime, end: datetime) -> int:
    """Signed 5-minute-bar distance (end - start); fails closed off-grid."""
    seconds = (end - start).total_seconds()
    bars, remainder = divmod(seconds, BAR_MINUTES * 60)
    if abs(remainder) > 1e-6:
        raise D005Error(
            f"decision {decision_id!r}: temporal distance is not on the "
            f"M5 bar grid ({seconds!r} seconds)"
        )
    return int(bars)


def _fvg_universe_record(
    *,
    decision_id: Any,
    zone: Mapping[str, Any],
    fvg_formation_available_at: datetime,
    fvg_completion_open_time: datetime | None,
    block_confirmed_at: datetime,
    decision_at: datetime,
) -> dict[str, Any]:
    """One temporal-universe record on the CAUSAL AVAILABILITY clock (TC001).

    ``fvg_formation_available_at`` is the completion (third) candle's causal
    ``available_at`` — the instant the three-candle FVG pattern becomes
    observable.  ``block_confirmed_at`` is the canonical OB clock, which is
    likewise the confirmation candle's ``available_at``
    (``bot.strategy.order_blocks.detect_order_blocks``).  Ordering and
    distance therefore compare causal availability to causal availability;
    no mixed-clock comparison and no manual +/-1 compensation exists.
    ``fvg_completion_open_time`` (when parseable) is DESCRIPTIVE metadata
    only and never drives ordering, distance or H003 membership.
    """
    signed = _bar_distance(decision_id, block_confirmed_at, fvg_formation_available_at)
    if signed > 0:
        order = "AFTER_OB_CONFIRMATION"
    elif signed < 0:
        order = "BEFORE_OB_CONFIRMATION"
    else:
        order = "AT_OB_CONFIRMATION"
    filled_before = bool(zone.get("filled"))
    return {
        "fvg_direction": str(zone.get("direction")),
        "formation_order_relative_to_ob": order,
        "signed_bar_distance": signed,
        "absolute_bar_distance": abs(signed),
        "elapsed_minutes": float(signed * BAR_MINUTES),
        "ob_confirmed_at": block_confirmed_at.astimezone(timezone.utc).isoformat(),
        "fvg_formation_available_at": (
            fvg_formation_available_at.astimezone(timezone.utc).isoformat()
        ),
        "fvg_completion_open_time": (
            fvg_completion_open_time.astimezone(timezone.utc).isoformat()
            if fvg_completion_open_time is not None else None
        ),
        "unfilled_at_decision": not filled_before,
        "filled_before_decision": filled_before,
        "source_index": zone.get("source_index"),
    }


def observe_d005_decision(
    v002_observation: Mapping[str, Any],
    snapshot: Any,
    *,
    config: Any,
) -> dict[str, Any]:
    """Read-only H003 temporal observation for ONE primary-population decision.

    The frozen V002 observation (from ``observe_v002_decision``) supplies the
    population membership and block identity; D005 re-derives the causal FVG
    evidence with the frozen canonical detector over the causal M5 frame and
    reconciles block identity and the persisted final surface.  Fails closed
    on any contract violation.  This function never mutates V002 state and
    never computes a candidate concept.
    """
    from bot.analysis import get_unfilled_fvgs  # noqa: PLC0415
    from bot.analysis.fvg_engine import detect_fvgs  # noqa: PLC0415
    from bot.strategy.order_blocks import detect_order_blocks  # noqa: PLC0415

    decision_id = v002_observation["decision_id"]
    if not v002_observation["v002_structurally_active"] or not v002_observation["v002_block_id"]:
        raise ReconciliationError(
            f"decision {decision_id!r}: D005 primary population requires a "
            "structurally-active V002 block with a block identity"
        )
    if v002_observation["v002_fvg_associated"]:
        raise ReconciliationError(
            f"decision {decision_id!r}: decision has an associated final "
            "same-direction FVG; it belongs to reference population R1, not "
            "the D005 primary population"
        )
    payload = json.loads(snapshot.gate_payload)
    if int(v002_observation["available_at_ms"]) != int(snapshot.available_at_ms):
        raise ReconciliationError(
            f"decision {decision_id!r}: observation/snapshot timestamp mismatch"
        )
    decision_at = datetime.fromtimestamp(
        int(snapshot.available_at_ms) / 1000, tz=timezone.utc
    )
    htf_bias = str(payload.get("htf_bias") or "")
    if htf_bias not in ("bullish", "bearish"):
        raise ReconciliationError(
            f"decision {decision_id!r}: unresolved htf_bias {htf_bias!r}"
        )
    side = {"bullish": "LONG", "bearish": "SHORT"}[htf_bias]
    if side != v002_observation["v002_side"]:
        raise ReconciliationError(
            f"decision {decision_id!r}: V002 side "
            f"{v002_observation['v002_side']!r} contradicts htf_bias "
            f"{htf_bias!r}"
        )

    rows = list(payload.get("entry_rows") or [])
    try:
        frame = _entry_frame(rows)
    except (TypeError, ValueError) as error:
        raise D005Error(
            f"decision {decision_id!r}: malformed candle rows: {error}"
        ) from error
    required = {"open_time", "available_at", "open", "high", "low", "close"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        raise D005Error(
            f"decision {decision_id!r}: causal M5 frame missing required columns"
        )
    # Causal boundary (spec section 6): exclude, record, never inspect.
    try:
        open_times = pd.to_datetime(frame["open_time"], utc=True)
        available_times = pd.to_datetime(frame["available_at"], utc=True)
    except (TypeError, ValueError) as error:
        raise D005Error(
            f"decision {decision_id!r}: malformed candle timestamps: {error}"
        ) from error
    if open_times.isna().any() or available_times.isna().any():
        raise D005Error(
            f"decision {decision_id!r}: malformed (NaT) candle timestamps in "
            "the causal frame"
        )
    causal_mask = available_times <= pd.Timestamp(decision_at)
    non_causal_excluded = int((~causal_mask).sum())
    causal_frame = frame.loc[causal_mask].reset_index(drop=True)
    if causal_frame.empty:
        raise D005Error(f"decision {decision_id!r}: empty causal frame")

    # Section 7/15: recompute the frozen final same-direction surface from
    # the causal frame and reconcile EXACTLY with the persisted input surface.
    persisted_fvgs = list(payload.get("fvgs") or [])
    recomputed_final = get_unfilled_fvgs(
        causal_frame, timeframe="M5", direction=htf_bias
    )
    _reconcile_final_surface(decision_id, persisted_fvgs, recomputed_final)

    # Section 16: temporal universe — the frozen detector, no direction
    # filter, causal frame only.
    universe_zones = detect_fvgs(causal_frame, timeframe="M5")

    # Block-identity reconciliation (fail closed): the canonical detector
    # over the same causal frame must reproduce the V002-selected block —
    # identity, zone and side.  The persisted LEGACY acquisition surface
    # (``ob_result``) is a DIFFERENT detector by design (H002); its zone
    # agreement is recorded descriptively only and never gates D005, and a
    # legacy surface that found no block (``ob_result == {}``) is expected
    # for most entrants and is not a failure.
    from bot.strategy.models import StrategySide  # noqa: PLC0415

    side_enum = {"LONG": StrategySide.LONG, "SHORT": StrategySide.SHORT}[side]
    blocks = [
        block for block in detect_order_blocks(causal_frame, config)
        if block.side is side_enum
    ]
    if not blocks:
        raise ReconciliationError(
            f"decision {decision_id!r}: canonical detector found no "
            f"{side} block; V002 block identity cannot be reconciled"
        )
    block = sorted(
        blocks,
        key=lambda item: (item.confirmed_at, -item.zone_high + item.zone_low, item.block_id),
    )[-1]
    if block.block_id != v002_observation["v002_block_id"]:
        raise ReconciliationError(
            f"decision {decision_id!r}: block-identity mismatch — V002 "
            f"reported {v002_observation['v002_block_id']!r}, canonical "
            f"recomputation selected {block.block_id!r}"
        )
    ob_context = payload.get("ob_result") or {}
    legacy_zone = ob_context.get("zone")
    if legacy_zone is not None:
        try:
            legacy_agreement = [
                float(legacy_zone[0]), float(legacy_zone[1]),
            ] == [float(block.zone_low), float(block.zone_high)]
        except (TypeError, ValueError, IndexError):
            legacy_agreement = None
    else:
        legacy_agreement = None

    universe: list[dict[str, Any]] = []
    same_direction_zones: list[Mapping[str, Any]] = []
    opposite_direction_count = 0
    for zone in universe_zones:
        completion_index = int(zone["source_index"]) + 1
        if completion_index >= len(causal_frame):
            raise ReconciliationError(
                f"decision {decision_id!r}: FVG completion index outside the "
                "causal frame"
            )
        # TC001 causal formation clock: the pattern completes only when the
        # THIRD candle is observable, so formation is the completion row's
        # ``available_at`` (the same clock as the canonical OB
        # ``confirmed_at``).  The completion row itself remains
        # ``source_index + 1`` — detector attribution is unchanged.
        fvg_formation_available_at = _parse_timestamp(
            decision_id,
            "fvg formation available_at",
            causal_frame.iloc[completion_index]["available_at"],
        )
        # Descriptive metadata only: the completion candle's open time.
        # Parsed tolerantly (it must never gate anything) and recorded for
        # clock-transparency; it cannot change ordering, distances or the
        # H003 decision because none of them consume it.
        try:
            fvg_completion_open_time = _parse_timestamp(
                decision_id,
                "fvg completion open_time",
                causal_frame.iloc[completion_index]["open_time"],
            )
        except D005Error:
            fvg_completion_open_time = None
        record = _fvg_universe_record(
            decision_id=decision_id,
            zone=zone,
            fvg_formation_available_at=fvg_formation_available_at,
            fvg_completion_open_time=fvg_completion_open_time,
            block_confirmed_at=block.confirmed_at.astimezone(timezone.utc),
            decision_at=decision_at,
        )
        universe.append(record)
        if record["fvg_direction"] == htf_bias:
            same_direction_zones.append((zone, record))
        else:
            opposite_direction_count += 1

    # Section 9: H003 ordering rule — same-direction FVG formed AT OR AFTER
    # OB confirmation.  Fill state is NOT part of the rule.
    qualifying = [item for item in same_direction_zones if item[1][
        "formation_order_relative_to_ob"
    ] in ("AFTER_OB_CONFIRMATION", "AT_OB_CONFIRMATION")]
    h003_temporal_association = bool(qualifying)

    # Section 11: exhaustive attrition categories (fail closed).
    pre_ob_same = [
        item for item in same_direction_zones
        if item[1]["formation_order_relative_to_ob"] == "BEFORE_OB_CONFIRMATION"
    ]
    if h003_temporal_association:
        category = "SAME_DIRECTION_FVG_EXISTED_BUT_FILLED"
    elif pre_ob_same:
        category = "SAME_DIRECTION_FVG_PRE_OB_ONLY"
    elif opposite_direction_count and not same_direction_zones:
        category = "OPPOSITE_DIRECTION_ONLY"
    elif not same_direction_zones and not opposite_direction_count:
        category = "NO_SAME_DIRECTION_FVG_EVER"
    else:
        raise ReconciliationError(
            f"decision {decision_id!r}: temporal universe does not map to a "
            "preregistered attrition category (accounting error)"
        )

    distances = [item[1]["signed_bar_distance"] for item in qualifying]
    observation = {
        "decision_id": decision_id,
        "available_at_ms": int(snapshot.available_at_ms),
        "h003_side": side,
        "v002_block_id": v002_observation["v002_block_id"],
        "block_confirmed_at": block.confirmed_at.astimezone(timezone.utc).isoformat(),
        "legacy_ob_zone_agreement_descriptive": legacy_agreement,
        "non_causal_rows_excluded": non_causal_excluded,
        "final_surface_reconciled": True,
        "causal_fvg_count_total": len(universe_zones),
        "causal_fvg_count_same_direction": len(same_direction_zones),
        "causal_fvg_count_opposite_direction": opposite_direction_count,
        "temporal_fvg_universe": universe,
        "attrition_category": category,
        "h003_temporal_association": h003_temporal_association,
        "h003_qualifying_fvg_count": len(qualifying),
        "temporal_distance_signed_bars": distances,
        "temporal_distance_records": [item[1] for item in qualifying],
    }
    _reject_banned_keys(observation)
    return observation


def _reject_banned_keys(node: Any, path: str = "observation") -> None:
    """Reject prohibited concept keys; declared-negative markers are exempt.

    Keys prefixed ``no_`` are governance negation markers (for example
    ``no_profitability_metrics``); they are exempt from the concept scan but
    their VALUES are still scanned recursively.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            key_text = str(key).lower()
            if not key_text.startswith("no_") and any(
                banned in key_text for banned in D005_BANNED_SUBSTRINGS
            ):
                raise D005Error(f"prohibited concept key {path}.{key}")
            _reject_banned_keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_banned_keys(value, f"{path}[{index}]")


# ---------------------------------------------------------------------------
# Aggregate (structural metrics only)
# ---------------------------------------------------------------------------


def _distance_summary(distances: list[int]) -> dict[str, Any]:
    if not distances:
        return {"count": 0}
    ordered = sorted(distances)
    absolute = sorted(abs(value) for value in distances)

    def _quantile(values: list[int], fraction: float) -> float:
        position = fraction * (len(values) - 1)
        low = int(position)
        high = min(low + 1, len(values) - 1)
        weight = position - low
        return round(values[low] * (1 - weight) + values[high] * weight, 1)

    histogram: dict[str, int] = {}
    for value in ordered:
        histogram[str(value)] = histogram.get(str(value), 0) + 1
    return {
        "count": len(ordered),
        "signed_min": ordered[0],
        "signed_max": ordered[-1],
        "absolute_min": absolute[0],
        "absolute_max": absolute[-1],
        "median_signed": _quantile(ordered, 0.5),
        "quantiles_signed": {
            "p25": _quantile(ordered, 0.25),
            "p50": _quantile(ordered, 0.5),
            "p75": _quantile(ordered, 0.75),
        },
        "exact_integer_histogram_signed": histogram,
    }


def aggregate_d005(
    observations: Iterable[Mapping[str, Any]],
    v002_pair_surface: Mapping[str, Any],
) -> dict[str, Any]:
    """Aggregate the D005 primary observations and reconcile the partition.

    The V002 structural-pair surface (frozen TC001/TC002 aggregate shape)
    supplies the entrant universe; the primary population is R2 and the three
    reference populations must partition it exactly.
    """
    observations = list(observations)
    entrants = int(v002_pair_surface["gate11_entrants_observed"])
    active = int(v002_pair_surface["v002_structurally_active_count"])
    associated = int(v002_pair_surface["v002_associated_same_direction_fvg_count"])
    primary_count = len(observations)
    r1 = associated
    r2 = active - associated
    r3 = entrants - active
    if primary_count != r2:
        raise ReconciliationError(
            f"primary population {primary_count} != structurally-active "
            f"without final FVG R2={r2}"
        )
    if r1 + r2 + r3 != entrants:
        raise ReconciliationError(
            f"reference partition {r1}+{r2}+{r3} != entrants {entrants}"
        )

    categories = {name: 0 for name in ATTRITION_CATEGORIES}
    h003_decisions = 0
    sides = {"LONG": 0, "SHORT": 0}
    universe_size_total = 0
    same_direction_total = 0
    opposite_direction_total = 0
    non_causal_excluded_total = 0
    distances: list[int] = []
    distance_records: list[dict[str, Any]] = []
    for observation in observations:
        category = observation["attrition_category"]
        if category not in categories:
            raise ReconciliationError(
                f"decision {observation['decision_id']!r}: attrition category "
                f"{category!r} is not preregistered"
            )
        categories[category] += 1
        sides[observation["h003_side"]] = sides.get(observation["h003_side"], 0) + 1
        if observation["h003_temporal_association"]:
            h003_decisions += 1
            if not (
                0 <= observation["h003_qualifying_fvg_count"]
                and observation["h003_qualifying_fvg_count"]
                == len(observation["temporal_distance_signed_bars"])
            ):
                raise ReconciliationError(
                    f"decision {observation['decision_id']!r}: qualifying "
                    "FVG count does not reconcile with distance records"
                )
            distances.extend(observation["temporal_distance_signed_bars"])
            distance_records.extend(observation["temporal_distance_records"])
        universe_size_total += int(observation["causal_fvg_count_total"])
        same_direction_total += int(observation["causal_fvg_count_same_direction"])
        opposite_direction_total += int(
            observation["causal_fvg_count_opposite_direction"]
        )
        non_causal_excluded_total += int(observation["non_causal_rows_excluded"])
    if sum(categories.values()) != primary_count:
        raise ReconciliationError("attrition categories do not reconcile")
    if h003_decisions > primary_count:
        raise ReconciliationError(
            "H003 temporal count exceeds the primary population"
        )

    if h003_decisions >= TIER_A_ARITHMETIC_HEADROOM_OBSERVATIONS:
        headroom = "TEMPORAL_VARIANT_HEADROOM_POSSIBLE"
    else:
        headroom = "TEMPORAL_VARIANT_HEADROOM_INSUFFICIENT"

    return {
        "D005_population": {
            "primary_population": primary_count,
            "population_rule": (
                "V002 Gate-11 entrants with frozen V002 structurally_active "
                "== True AND fvg_associated == False under final-FVG "
                "semantics; derived naturally during execution"
            ),
            "reference_populations_partition": {
                "R1_active_with_final_same_direction_fvg": r1,
                "R2_active_without_final_same_direction_fvg": r2,
                "R3_v002_non_active": r3,
                "partitions_entrants_exactly": r1 + r2 + r3 == entrants,
            },
            "h003_side_counts": {
                "LONG": sides.get("LONG", 0),
                "SHORT": sides.get("SHORT", 0),
            },
        },
        "temporal_fvg_universe_surface": {
            "causal_fvg_count_total": universe_size_total,
            "causal_fvg_count_same_direction": same_direction_total,
            "causal_fvg_count_opposite_direction": opposite_direction_total,
            "non_causal_rows_excluded_total": non_causal_excluded_total,
            "formation_orders": {
                "BEFORE_OB_CONFIRMATION": sum(
                    1
                    for observation in observations
                    for record in observation["temporal_fvg_universe"]
                    if record["formation_order_relative_to_ob"]
                    == "BEFORE_OB_CONFIRMATION"
                ),
                "AT_OB_CONFIRMATION": sum(
                    1
                    for observation in observations
                    for record in observation["temporal_fvg_universe"]
                    if record["formation_order_relative_to_ob"]
                    == "AT_OB_CONFIRMATION"
                ),
                "AFTER_OB_CONFIRMATION": sum(
                    1
                    for observation in observations
                    for record in observation["temporal_fvg_universe"]
                    if record["formation_order_relative_to_ob"]
                    == "AFTER_OB_CONFIRMATION"
                ),
            },
            "fill_states": {
                "unfilled_at_decision": sum(
                    1
                    for observation in observations
                    for record in observation["temporal_fvg_universe"]
                    if record["unfilled_at_decision"]
                ),
                "filled_before_decision": sum(
                    1
                    for observation in observations
                    for record in observation["temporal_fvg_universe"]
                    if record["filled_before_decision"]
                ),
            },
        },
        "final_surface_attrition": {
            "categories": dict(sorted(categories.items())),
            "category_definitions_preregistered": True,
            "reconciles_to_primary_population": (
                sum(categories.values()) == primary_count
            ),
        },
        "h003_temporal_association": {
            "rule": (
                "ordering only: at least one same-direction canonical FVG "
                "formed AT OR AFTER canonical OB confirmation in the causal "
                "frame; fill state is descriptive universe metadata and "
                "never part of the rule; no proximity, lag tolerance or "
                "temporal window exists in this tooling"
            ),
            "h003_temporal_association_decisions": h003_decisions,
            "structural_count_only": True,
            "never_a_candidate_count": True,
        },
        "temporal_distance_surface": {
            "summary": _distance_summary(distances),
            "records": distance_records,
            "permitted_summaries_only": (
                "count, min, max, median, exact integer histogram, p25/p50/p75"
            ),
            "no_lag_optimization_performed": True,
        },
        "headroom_feasibility": {
            "tier_a_arithmetic_headroom_observations": (
                TIER_A_ARITHMETIC_HEADROOM_OBSERVATIONS
            ),
            "classification": headroom,
            "necessary_condition_only": True,
            "note": (
                "arithmetic feasibility bound (90 - 61) only; NOT an H003 "
                "support threshold, NOT a parameter, NOT a tuning objective, "
                "NOT a candidate prediction; >= 29 does not prove any variant "
                "reaches 90 and no automatic V003 follows"
            ),
        },
    }


# ---------------------------------------------------------------------------
# Provenance and runner
# ---------------------------------------------------------------------------


def _canonical_blob_source():
    """Production committed-byte source: real Git plumbing on this repo."""
    from bot.scientific.canonical_bytes import make_git_blob_source  # noqa: PLC0415

    return make_git_blob_source(REPO_ROOT)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def provenance(
    *,
    v002_implementation_commit: str,
    tooling_commit: str,
    store_identity: Mapping[str, Any],
    generated_at: str | None = None,
    blob_source=None,
) -> dict[str, Any]:
    """Provenance bound to the frozen V002 implementation commit and this tooling."""
    from bot.scientific.canonical_bytes import canonical_file_digest  # noqa: PLC0415

    if not v002_implementation_commit or len(v002_implementation_commit) != 40:
        raise D005Error("V002 implementation commit identity invalid")
    if not tooling_commit or len(tooling_commit) != 40:
        raise D005Error("tooling commit identity invalid")
    source = blob_source if blob_source is not None else _canonical_blob_source()
    try:
        tooling_fingerprint = canonical_file_digest(
            TOOLING_RELPATH, commit=tooling_commit, repo=REPO_ROOT, blob_source=source,
        )
        v002_module_content_sha256 = hashlib.sha256(
            source(v002_implementation_commit, V002_STRATEGY_MODULE)
        ).hexdigest()
    except Exception as error:  # fail closed: no worktree/normalized fallback
        raise D005Error(f"D005 provenance unresolvable: {error}") from error
    blob = json.dumps(dict(store_identity), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "tooling": TOOLING_RELPATH,
        "diagnostic_id": D005_ID,
        "hypothesis_id": H003_ID,
        "variant_id_contextual": V002_ID,
        "charter_id": CHARTER_ID,
        "charter_sha256": CHARTER_SHA256,
        "specification_document": SPECIFICATION_DOCUMENT,
        "specification_sha256": SPEC_SHA256,
        "fingerprint_contract": "canonical_git_blob_v1",
        "classification": CLASSIFICATION,
        "research_identity": "phase8-v2",
        "fold01_boundary": [FOLD01_START, FOLD01_END],
        "v002_implementation_commit": v002_implementation_commit,
        "v002_strategy_module": V002_STRATEGY_MODULE,
        "v002_strategy_module_git_blob_sha_governance": V002_STRATEGY_GIT_BLOB_SHA,
        "v002_strategy_module_content_sha256": v002_module_content_sha256,
        "tooling_commit": tooling_commit,
        "tooling_fingerprint": tooling_fingerprint,
        "fold_store_identity_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "generated_at_utc": generated_at or _iso(datetime.now(timezone.utc)),
        "d005_is_read_only": True,
    }


def run_d005(
    store: Any,
    *,
    v002_implementation_commit: str,
    tooling_commit: str,
    blob_source=None,
) -> tuple[dict[str, Any], bytes]:
    """Execute the preregistered D005 read-only diagnostic over Fold 01.

    Loop discipline is the frozen D001/D003/V002 one.  The V002 observation
    path is reused verbatim (frozen TC001 population + TC002 candidate
    stages); D005 only additionally observes the primary population.  Fails
    closed on boundary, store-compatibility, accounting, identity or
    structural violations.  Returns ``(document, bytes)``.
    """
    from bot.strategy.config import StrategyConfig  # noqa: PLC0415
    from bot.strategy.setup_state import (  # noqa: PLC0415
        StrategyState,
        record_from_state,
    )

    identity = store.identity
    check_store_boundary(dict(identity))
    config = StrategyConfig()
    seed_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    state_record = record_from_state(
        StrategyState(event_time=seed_time), event_at=seed_time,
    )
    buckets = {"missing_history": 0, "unavailable_input": 0, "evaluation_error": 0}
    rows: list[dict[str, Any]] = []
    v002_observations: list[dict[str, Any]] = []
    d005_observations: list[dict[str, Any]] = []
    scheduled = 0
    for snapshot in _snapshot_rows(store):
        scheduled += 1
        bucket = classify_snapshot(snapshot)
        if bucket is not None:
            name, _status = bucket
            buckets[name] += 1
            continue
        if _reference_check_failed(snapshot):
            buckets["evaluation_error"] += 1
            continue
        prior_state_record = state_record
        row, next_record = evaluate_orchestration_decision(
            snapshot, prior_state_record,
        )
        if row["action"] == "error":
            buckets["evaluation_error"] += 1
            continue
        rows.append(row)
        gate11_entered = "gate_11_confluence_score" in (row.get("gate_results") or {})
        if gate11_entered:
            assert_store_semantic_compatibility(snapshot)
            v002_observation = observe_v002_decision(
                row, snapshot, prior_state_record, config=config,
                decision_result_record=next_record,
            )
            v002_observations.append(v002_observation)
            if v002_observation["v002_structurally_active"] and not v002_observation[
                "v002_fvg_associated"
            ]:
                d005_observations.append(
                    observe_d005_decision(v002_observation, snapshot, config=config)
                )
        state_record = next_record
    reconcile_accounting(
        scheduled=scheduled,
        classified=len(rows),
        missing_history=buckets["missing_history"],
        unavailable_input=buckets["unavailable_input"],
        evaluation_error=buckets["evaluation_error"],
    )
    from backtests.phase8_v2_variant_v002_eval import aggregate_v002  # noqa: PLC0415

    v002_aggregate = aggregate_v002(v002_observations)
    v002_surface = v002_aggregate["V002_structural_pair_surface"]
    doc: dict[str, Any] = {
        "diagnostic_id": D005_ID,
        "hypothesis_id": H003_ID,
        "classification": CLASSIFICATION,
        "specification_document": SPECIFICATION_DOCUMENT,
        "specification_sha256": SPEC_SHA256,
        "provenance": provenance(
            v002_implementation_commit=v002_implementation_commit,
            tooling_commit=tooling_commit,
            store_identity=dict(identity),
            blob_source=blob_source,
        ),
        "fold01_boundary": [FOLD01_START, FOLD01_END],
        "decision_accounting": {
            "scheduled": scheduled,
            "reducer_classified": len(rows),
            "missing_history": buckets["missing_history"],
            "unavailable_input": buckets["unavailable_input"],
            "evaluation_error": buckets["evaluation_error"],
            "reconciles": True,
        },
        "gate_funnel": _gate_funnel(rows),
        "v002_reference_surface": v002_surface,
        **aggregate_d005(d005_observations, v002_surface),
        "h003_disposition_rule": (
            "H003's existing preregistered expected qualitative effect and "
            "potential failure mode govern, applied qualitatively at "
            "execution review; the headroom arithmetic is never the "
            "scientific support rule; disposition values from the register "
            "vocabulary (SUPPORTED_BY_D005 / NOT_SUPPORTED_BY_D005)"
        ),
        "budget_consumption_note": (
            "diagnostics become permanently 4 / 12 at the instant first "
            "Fold-01 D005 observation; strategy variants remain 2 / 8; "
            "numeric trials remain 0 / 4"
        ),
        "reserved_evidence": {
            "fold_02_untouched": True,
            "fold_03_untouched": True,
            "fold_04_untouched": True,
            "holdout_untouched": True,
            "data_2025_plus_untouched": True,
        },
        "no_profitability_metrics": True,
        "counterfactual_arithmetic_performed": False,
        "no_lag_optimization_performed": True,
        "v002_strategy_module_unchanged": True,
        "d005_is_read_only": True,
    }
    _reject_banned_keys(doc)
    _reject_banned_metrics(doc)
    assert_expected_surfaces(doc)
    return doc, _canonical(doc).encode("utf-8")


def assert_expected_surfaces(document: Mapping[str, Any]) -> None:
    required = (
        "decision_accounting",
        "gate_funnel",
        "v002_reference_surface",
        "D005_population",
        "temporal_fvg_universe_surface",
        "final_surface_attrition",
        "h003_temporal_association",
        "temporal_distance_surface",
        "headroom_feasibility",
    )
    missing = [key for key in required if key not in document]
    if missing:
        raise D005Error(f"preregistered D005 surface missing: {missing}")
    accounting = document["decision_accounting"]
    if (
        accounting["reducer_classified"] + accounting["missing_history"]
        + accounting["unavailable_input"] + accounting["evaluation_error"]
        != accounting["scheduled"]
    ):
        raise D005Error("decision accounting does not reconcile")
    surface = document["v002_reference_surface"]
    entered = int(
        document.get("gate_funnel", {})
        .get("gate_11_confluence_score", {})
        .get("entered", -1)
    )
    if entered < 0:
        raise D005Error("gate funnel lacks a gate_11_confluence_score entry")
    if surface["gate11_entrants_observed"] != entered:
        raise D005Error(
            "V002 entrant population mismatch (TC001): "
            f"{surface['gate11_entrants_observed']} != {entered}"
        )
    population = document["D005_population"]
    partition = population["reference_populations_partition"]
    if not partition["partitions_entrants_exactly"]:
        raise D005Error("D005 reference populations do not partition the entrants")
    if population["primary_population"] != partition[
        "R2_active_without_final_same_direction_fvg"
    ]:
        raise D005Error(
            "primary population does not equal R2 (active without final FVG)"
        )
    attrition = document["final_surface_attrition"]
    if not attrition["reconciles_to_primary_population"]:
        raise D005Error("attrition categories do not reconcile to the primary population")
    if document["h003_temporal_association"][
        "h003_temporal_association_decisions"
    ] > population["primary_population"]:
        raise D005Error("H003 temporal count is not a subset of the primary population")
    headroom = document["headroom_feasibility"]
    if headroom["classification"] not in (
        "TEMPORAL_VARIANT_HEADROOM_POSSIBLE",
        "TEMPORAL_VARIANT_HEADROOM_INSUFFICIENT",
    ):
        raise D005Error("headroom classification is not a preregistered value")
    if headroom["tier_a_arithmetic_headroom_observations"] != 29:
        raise D005Error("headroom bound must remain the preregistered arithmetic value")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_result(material: Mapping[str, Any], rendered: bytes, output_dir: Path) -> tuple[Path, str]:
    """Atomically write the deterministic result; refuse overwrite."""
    output_dir = Path(output_dir)
    reject_holdout_path(str(output_dir))
    target = output_dir / "phase8-v2-D005_result.json"
    if target.exists():
        raise D005Error(f"result already exists; refusing overwrite: {target}")
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = output_dir / f".staging-{uuid.uuid4().hex[:8]}"
    staging.write_bytes(rendered)
    os.replace(staging, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != hashlib.sha256(rendered).hexdigest():
        raise D005Error("result hash mismatch after write")
    return target, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the Fold-01 feature store")
    parser.add_argument("--v002-implementation-commit", required=True)
    parser.add_argument("--tooling-commit", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    from bot.validation.market_feature_store import FoldFeatureStore  # noqa: PLC0415

    reject_holdout_path(args.store)
    store = FoldFeatureStore.open(args.store)
    document, rendered = run_d005(
        store,
        v002_implementation_commit=args.v002_implementation_commit,
        tooling_commit=args.tooling_commit,
    )
    path, sha = write_result(document, rendered, Path(args.output_dir))
    print(json.dumps({"path": str(path), "sha256": sha}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
