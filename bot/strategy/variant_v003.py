"""V003 Causal Temporal FVG Evidence Memory — isolated variant evaluator (H003).

DEVELOPMENT_VARIANT_IMPLEMENTATION — phase6-development-v2-V003 — H003

Frozen variant boundary (``docs/PHASE8_V2_VARIANT_V003.md``; register
``phase6-development-v2-V003``):

* ONE conceptual hypothesis: causal temporal FVG evidence memory — broadening
  the Gate-11 FVG confluence component from "final unfilled FVG only" to
  (F_final OR F_temporal), where F_temporal requires a same-direction canonical
  FVG causally formed at or after the selected structural OB confirmation before
  the decision timestamp; historical fill status does not erase the occurrence
  of displacement imbalance evidence.
* Strict V002 baseline preservation: when F_final is True, V003 executes the
  V002 final-surface branch identically, preserving exact V002 evidence, exact
  overlap metadata, and live FVG geometry.  The temporal branch serves only as
  fallback when F_final is False.
* Critical live-zone separation: historical filled temporal FVGs satisfy the
  confluence evidence requirement that displacement occurred after the OB, but
  NEVER populate context['fvg_zone'], strategy_state.fvg_zone, limit/pullback
  zones, stop loss, take profit, or RR geometry.  Live fvg_zone is populated
  ONLY from the current unfilled final FVG surface (and is None for
  temporal-only evidence).
* Strategy state invariance: V003 evaluates evidence without mutating frozen
  strategy state: state.displacement_seen, state.fvg_zone,
  state.structure_state, state.liquidity_swept and all state fields remain
  completely unmutated by V003 historical evidence.
* Order-block semantics invariance: V003 order-block semantics are byte/behavior
  equivalent to V002: latest same-side canonical confirmed block, causal
  confirmation, consumed rejection, unmitigated/uninvalidated through decision,
  age > 30 bars alone does not reject.
* Causal FVG clock: preserves D005 TC001 causal clock: FVG formation timestamp
  = completion candle available_at (source_index + 1), available_at <= decision_at,
  ordering rule: fvg_formation_available_at >= block.confirmed_at.
* No lag threshold: no numeric proximity, lag cutoff, session window, or ATR
  temporal threshold; numeric parameter trials remain 0 / 4.
* Gate 11 keeps the frozen architecture: components 2/1/2/1/2, maximum 8,
  threshold 8/8.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

import pandas as pd

from .config import StrategyConfig
from .confluence import COMPONENTS
from .models import BlockState, OrderBlockResult, SetupEvidence, StrategySide
from .order_blocks import _valid_frame, detect_order_blocks
from .regime import atr_series

#: Phase-A preregistration specification SHA-256 bound into tooling
SPEC_SHA256 = "e6aa3e8a4f7b909f178a18112a43425ccfe61448c3c8643aea9c3f5d670e0d95"

#: States the V003 evaluator reports (identical to V002).
V003_ACTIVE = "ACTIVE"
V003_RETEST_ELIGIBLE = "RETEST_ELIGIBLE"
V003_MITIGATED = "MITIGATED"
V003_INVALIDATED = "INVALIDATED"
V003_CONSUMED = "CONSUMED"
V003_PREMATURE = "PREMATURE"
V003_UNAVAILABLE = "UNAVAILABLE"
V003_DATA_UNSAFE = "DATA_UNSAFE"

#: V003 structural-active states mapped onto canonical ``BlockState``.
_V003_TO_BLOCK_STATE = {
    V003_ACTIVE: BlockState.ELIGIBLE,
    V003_RETEST_ELIGIBLE: BlockState.RETEST_ELIGIBLE,
    V003_MITIGATED: BlockState.MITIGATED,
    V003_INVALIDATED: BlockState.INVALIDATED,
    V003_CONSUMED: BlockState.CONSUMED,
    V003_PREMATURE: BlockState.PREMATURE,
    V003_UNAVAILABLE: BlockState.UNAVAILABLE,
    V003_DATA_UNSAFE: BlockState.DATA_UNSAFE,
}

#: Gate-11 component labels for V003.
V003_OB_LABEL = "Canonical structurally-active OB present"
V003_FVG_LABEL = "V003 canonical FVG evidence associated with the structural OB"

_SIDE_TO_FVG_DIRECTION = {
    StrategySide.LONG: "bullish",
    StrategySide.SHORT: "bearish",
}

OVERLAP_TOLERANCE_ATR = 0.30
BAR_MINUTES = 5


class V003VariantError(ValueError):
    """Fail closed on V003 contract violations (never guess a semantic)."""


@dataclass(frozen=True)
class V003PairResult:
    """One V003 canonical structural-pair evaluation at a causal decision."""

    state: str
    reason: str
    side: StrategySide
    block_id: str | None
    zone_low: float | None
    zone_high: float | None
    confirmed_at: datetime | None
    age_bars: int
    final_fvg_associated: bool
    temporal_fvg_evidence: bool
    v003_fvg_evidence: bool
    fvg_evidence_source: str  # "FINAL_SURFACE" | "TEMPORAL_MEMORY" | "NONE"
    fvg_direction: str | None
    exact_overlap: bool | None
    live_fvg_top: float | None = None
    live_fvg_bottom: float | None = None
    temporal_fvg_offset_bars: int | None = None
    temporal_fvg_count: int = 0

    @property
    def structurally_active(self) -> bool:
        """V003 eligible-equivalent: age alone has not rejected the pair."""
        return self.state in (V003_ACTIVE, V003_RETEST_ELIGIBLE)

    @property
    def fvg_associated(self) -> bool:
        """Direct accessor for V003 FVG evidence satisfaction."""
        return self.v003_fvg_evidence


def _final_fvg_for_side(fvgs: Iterable[Any] | None, side: StrategySide) -> dict[str, Any] | None:
    """Same-direction final canonical FVG from the frozen persisted surface."""
    direction = _SIDE_TO_FVG_DIRECTION.get(side)
    if direction is None:
        return None
    for candidate in fvgs or ():
        if not isinstance(candidate, Mapping):
            continue
        if str(candidate.get("direction", "")).lower() != direction:
            continue
        try:
            float(candidate["bottom"])
            float(candidate["top"])
        except (TypeError, ValueError, KeyError):
            continue
        return dict(candidate)
    return None


def _descriptive_overlap(
    fvg: Mapping[str, Any] | None, zone_low: float | None, zone_high: float | None, atr: float
) -> bool | None:
    """Frozen canonical overlap geometry, recorded descriptively only."""
    if fvg is None or zone_low is None or zone_high is None:
        return None
    try:
        tolerance = atr * OVERLAP_TOLERANCE_ATR
        fvg_low, fvg_high = float(fvg["bottom"]), float(fvg["top"])
        gap = (
            fvg_low - zone_high
            if fvg_low > zone_high
            else zone_low - fvg_high
            if fvg_high < zone_low
            else 0.0
        )
    except (TypeError, ValueError, KeyError):
        return None
    return bool(gap <= tolerance)


def _temporal_fvg_for_side(
    frame: pd.DataFrame,
    side: StrategySide,
    block_confirmed_at: datetime,
    decision_at: datetime,
) -> tuple[bool, int, dict[str, Any] | None, int | None]:
    """Detect causal same-direction temporal FVG evidence formed AT or AFTER OB confirmation.

    Returns:
        (has_qualifying_temporal, qualifying_count, selected_fvg, signed_bar_distance)
    """
    from bot.analysis.fvg_engine import detect_fvgs

    direction = _SIDE_TO_FVG_DIRECTION.get(side)
    if direction is None or frame is None or frame.empty:
        return False, 0, None, None

    # Filter frame to causally available candles
    if "available_at" not in frame.columns:
        return False, 0, None, None

    available_times = pd.to_datetime(frame["available_at"], utc=True)
    causal_mask = available_times <= pd.Timestamp(decision_at)
    causal_frame = frame.loc[causal_mask].reset_index(drop=True)
    if causal_frame.empty:
        return False, 0, None, None

    all_fvgs = detect_fvgs(causal_frame, timeframe="M5")
    qualifying_zones: list[tuple[dict[str, Any], int, datetime]] = []

    for zone in all_fvgs:
        if str(zone.get("direction", "")).lower() != direction:
            continue
        source_idx = zone.get("source_index")
        if source_idx is None:
            continue
        completion_idx = int(source_idx) + 1
        if completion_idx >= len(causal_frame):
            continue

        # Causal clock: completion candle available_at
        avail_ts = pd.Timestamp(causal_frame.iloc[completion_idx]["available_at"])
        if avail_ts is pd.NaT or pd.isna(avail_ts):
            continue
        formation_at = avail_ts.to_pydatetime().astimezone(timezone.utc)

        # Causal check: formation available at or before decision
        if formation_at > decision_at:
            continue

        # Ordering check: formation at or after OB confirmation
        if formation_at >= block_confirmed_at:
            # Bar distance: (formation_at - block_confirmed_at)
            secs = (formation_at - block_confirmed_at).total_seconds()
            signed_bars = int(round(secs / (BAR_MINUTES * 60)))
            qualifying_zones.append((dict(zone), signed_bars, formation_at))

    if not qualifying_zones:
        return False, 0, None, None

    # Deterministic tie-breaker for descriptive selection:
    # 1) formation_at (earliest)
    # 2) source_index (lowest)
    # 3) bottom / top
    qualifying_zones.sort(
        key=lambda item: (
            item[2],
            int(item[0].get("source_index", 0)),
            float(item[0].get("bottom", 0.0)),
            float(item[0].get("top", 0.0)),
        )
    )

    selected_zone, selected_signed_bars, _ = qualifying_zones[0]
    return True, len(qualifying_zones), selected_zone, selected_signed_bars


def evaluate_v003_structural_pair(
    frame: pd.DataFrame,
    side: StrategySide,
    decision_at: datetime,
    config: StrategyConfig,
    *,
    fvgs: Iterable[Any] | None = None,
    consumed_ids: frozenset[str] = frozenset(),
) -> V003PairResult:
    """Evaluate the V003 canonical structural pair for one causal decision."""
    if not isinstance(decision_at, datetime) or decision_at.tzinfo is None:
        return V003PairResult(
            V003_DATA_UNSAFE, "invalid_decision_time", StrategySide.FLAT,
            None, None, None, None, 0, False, False, False, "NONE", None, None,
        )
    if not _valid_frame(frame):
        return V003PairResult(
            V003_DATA_UNSAFE, "malformed_or_naive_candle_frame", StrategySide.FLAT,
            None, None, None, None, 0, False, False, False, "NONE", None, None,
        )
    blocks = [block for block in detect_order_blocks(frame, config) if block.side is side]
    if not blocks:
        return V003PairResult(
            V003_UNAVAILABLE, "no_confirmed_block", StrategySide.FLAT,
            None, None, None, None, 0, False, False, False, "NONE", None, None,
        )
    block = sorted(
        blocks, key=lambda item: (item.confirmed_at, -item.zone_high + item.zone_low, item.block_id)
    )[-1]
    if block.confirmed_at > decision_at:
        return V003PairResult(
            V003_PREMATURE, "confirmation_not_available", block.side,
            block.block_id, block.zone_low, block.zone_high, block.confirmed_at,
            0, False, False, False, "NONE", None, None,
        )
    if block.block_id in consumed_ids:
        return V003PairResult(
            V003_CONSUMED, "block_already_consumed", block.side,
            block.block_id, block.zone_low, block.zone_high, block.confirmed_at,
            0, False, False, False, "NONE", None, None,
        )

    ordered = frame.sort_values("open_time", kind="mergesort").reset_index(drop=True)
    later = ordered.iloc[block.confirmation_index + 1 :]
    later = later[pd.to_datetime(later["available_at"], utc=True) <= pd.Timestamp(decision_at)]
    age_bars = int(len(later))
    for _position, (_index, candle) in enumerate(later.iterrows()):
        close = float(candle["close"])
        if side is StrategySide.LONG and close < block.zone_low:
            return V003PairResult(
                V003_INVALIDATED, "close_below_bullish_zone", block.side,
                block.block_id, block.zone_low, block.zone_high, block.confirmed_at,
                age_bars, False, False, False, "NONE", None, None,
            )
        if side is StrategySide.SHORT and close > block.zone_high:
            return V003PairResult(
                V003_INVALIDATED, "close_above_bearish_zone", block.side,
                block.block_id, block.zone_low, block.zone_high, block.confirmed_at,
                age_bars, False, False, False, "NONE", None, None,
            )
        overlaps = float(candle["low"]) <= block.zone_high and float(candle["high"]) >= block.zone_low
        if overlaps:
            state = V003_RETEST_ELIGIBLE if _position == len(later) - 1 else V003_MITIGATED
            reason = (
                "first_post_confirmation_retest"
                if state == V003_RETEST_ELIGIBLE
                else "block_already_mitigated"
            )
            return _with_v003_fvg(
                block, side, age_bars, state, reason, frame, config, fvgs, decision_at
            )
    return _with_v003_fvg(
        block, side, age_bars, V003_ACTIVE, "structurally_active_block", frame, config, fvgs, decision_at
    )


def _with_v003_fvg(
    block: Any,
    side: StrategySide,
    age_bars: int,
    state: str,
    reason: str,
    frame: pd.DataFrame,
    config: StrategyConfig,
    fvgs: Iterable[Any] | None,
    decision_at: datetime,
) -> V003PairResult:
    """Attach V003 FVG evidence (final-surface primary branch, temporal fallback)."""
    # 1. Branch A: Final canonical FVG surface (exact V002 preservation)
    final_fvg = _final_fvg_for_side(fvgs, side)
    if final_fvg is not None:
        atr = 0.0
        prices = frame[["open", "high", "low", "close"]].astype(float)
        try:
            series = atr_series(prices, config.atr_period_bars)
            value = float(series.iloc[-1])
            if value == value and value > 0:
                atr = value
        except (IndexError, ValueError, TypeError):
            atr = 0.0
        exact_overlap = _descriptive_overlap(final_fvg, block.zone_low, block.zone_high, atr)
        return V003PairResult(
            state=state,
            reason=reason,
            side=block.side,
            block_id=block.block_id,
            zone_low=block.zone_low,
            zone_high=block.zone_high,
            confirmed_at=block.confirmed_at,
            age_bars=age_bars,
            final_fvg_associated=True,
            temporal_fvg_evidence=False,
            v003_fvg_evidence=True,
            fvg_evidence_source="FINAL_SURFACE",
            fvg_direction=str(final_fvg.get("direction")),
            exact_overlap=exact_overlap,
            live_fvg_top=float(final_fvg["top"]),
            live_fvg_bottom=float(final_fvg["bottom"]),
            temporal_fvg_offset_bars=None,
            temporal_fvg_count=0,
        )

    # 2. Branch B: Temporal FVG Evidence Memory (fallback when final surface is absent)
    has_temp, temp_count, temp_fvg, temp_offset = _temporal_fvg_for_side(
        frame, side, block.confirmed_at, decision_at
    )
    if has_temp and temp_fvg is not None:
        return V003PairResult(
            state=state,
            reason=reason,
            side=block.side,
            block_id=block.block_id,
            zone_low=block.zone_low,
            zone_high=block.zone_high,
            confirmed_at=block.confirmed_at,
            age_bars=age_bars,
            final_fvg_associated=False,
            temporal_fvg_evidence=True,
            v003_fvg_evidence=True,
            fvg_evidence_source="TEMPORAL_MEMORY",
            fvg_direction=str(temp_fvg.get("direction")),
            exact_overlap=None,
            live_fvg_top=None,  # CRITICAL: historical filled FVG NEVER becomes live zone
            live_fvg_bottom=None,
            temporal_fvg_offset_bars=temp_offset,
            temporal_fvg_count=temp_count,
        )

    # 3. Branch C: No FVG evidence anywhere
    return V003PairResult(
        state=state,
        reason=reason,
        side=block.side,
        block_id=block.block_id,
        zone_low=block.zone_low,
        zone_high=block.zone_high,
        confirmed_at=block.confirmed_at,
        age_bars=age_bars,
        final_fvg_associated=False,
        temporal_fvg_evidence=False,
        v003_fvg_evidence=False,
        fvg_evidence_source="NONE",
        fvg_direction=None,
        exact_overlap=None,
        live_fvg_top=None,
        live_fvg_bottom=None,
        temporal_fvg_offset_bars=None,
        temporal_fvg_count=0,
    )


def score_v003_setup(
    *,
    pair: V003PairResult,
    htf_bias: str,
    price_in_discount_or_premium: bool,
    liquidity_swept: bool,
    min_score_to_trade: int = 8,
) -> dict[str, object]:
    """V003 Gate-11 score: frozen 2/1/2/1/2 architecture, threshold 8/8."""
    bias = str(htf_bias or "").lower()
    if bias not in ("bullish", "bearish"):
        raise V003VariantError(f"V003 scoring requires a resolved HTF bias, got {htf_bias!r}")
    expected_side = _SIDE_TO_FVG_DIRECTION.get(pair.side) if pair.side is not StrategySide.FLAT else None
    trade_direction_matches = expected_side == bias
    checks: list[dict[str, object]] = []
    score = 0

    def add(condition: bool, points: int, label: str) -> None:
        nonlocal score
        if condition:
            score += points
        checks.append(
            {
                "label": label,
                "passed": bool(condition),
                "points": points if condition else 0,
                "max_points": points,
            }
        )

    add(trade_direction_matches, 2, "HTF bias aligns with trade direction")
    add(bool(price_in_discount_or_premium), 1, "Price located in premium/discount zone")
    add(bool(pair.structurally_active), 2, V003_OB_LABEL)
    add(bool(pair.v003_fvg_evidence), 1, V003_FVG_LABEL)
    add(bool(liquidity_swept), 2, "Liquidity sweep occurred before entry")

    maximum = sum(int(check["max_points"]) for check in checks)
    threshold = int(min_score_to_trade or 8)
    if score == maximum and score >= threshold:
        grade = "A+"
    elif score >= threshold:
        grade = "B"
    else:
        grade = "SKIP"
    assert maximum == 8, "V003 must preserve the frozen 8-point maximum"
    assert tuple((name, weight) for name, weight in COMPONENTS) == (
        ("bias_alignment", 2),
        ("premium_discount_location", 1),
        ("order_block", 2),
        ("fvg_overlap", 1),
        ("liquidity_sweep", 2),
    ), "V003 must preserve the frozen component weights 2/1/2/1/2"
    return {
        "score": score,
        "max_score": maximum,
        "grade": grade,
        "risk_authority": "central_phase4_policy",
        "passes_threshold": score >= threshold,
        "min_score_to_trade": threshold,
        "checks": checks,
    }


def evaluate_v003_strategy(
    *,
    adapter: str,
    symbol: str,
    decision_at: datetime,
    side: str,
    entry_frame: pd.DataFrame,
    htf_bias: str,
    dxy_context: dict,
    news_context: dict,
    session_context: dict,
    evidence: SetupEvidence,
    fvgs: Iterable[Any] | None,
    config: StrategyConfig | None = None,
    consumed_block_ids: frozenset[str] = frozenset(),
):
    """Downstream V003 strategy decision over the SAME structural-pair semantics."""
    from .adapters import evaluate_live_strategy, evaluate_replay_strategy
    from .legacy_adapter import _direction, _safety
    from .models import SourceCandle, StrategyInput
    from .regime import classify_regime

    policy = config or StrategyConfig()
    requested = {"bullish": StrategySide.LONG, "bearish": StrategySide.SHORT}.get(
        str(side).lower(), StrategySide.FLAT
    )
    if requested is StrategySide.FLAT:
        raise V003VariantError("V003 requires a resolved bullish/bearish side")
    decision = decision_at.astimezone(timezone.utc)
    pair = evaluate_v003_structural_pair(
        entry_frame, requested, decision, policy,
        fvgs=fvgs, consumed_ids=consumed_block_ids,
    )
    block = OrderBlockResult(
        state=_V003_TO_BLOCK_STATE[pair.state],
        side=pair.side,
        block_id=pair.block_id,
        zone_low=pair.zone_low,
        zone_high=pair.zone_high,
        confirmed_at=pair.confirmed_at,
        reason=pair.reason,
    )
    evidence_v003 = SetupEvidence(
        price_in_discount_or_premium=bool(evidence.price_in_discount_or_premium),
        order_block_present=bool(pair.structurally_active),
        fvg_overlaps_order_block=bool(pair.v003_fvg_evidence),
        liquidity_swept=bool(evidence.liquidity_swept),
    )
    source_candles: tuple[SourceCandle, ...] = ()
    if entry_frame is not None and not entry_frame.empty and {"open_time", "available_at"}.issubset(entry_frame.columns):
        last = entry_frame.iloc[-1]
        opened = pd.Timestamp(last["open_time"]).to_pydatetime()
        available = pd.Timestamp(last["available_at"]).to_pydatetime()
        source_candles = (
            SourceCandle(
                f"{symbol}:{opened.astimezone(timezone.utc).isoformat()}",
                str(last.get("timeframe", "ENTRY")),
                opened,
                available,
            ),
        )
    data = StrategyInput(
        symbol=symbol,
        decision_at=decision,
        requested_side=requested,
        regime=classify_regime(entry_frame, policy),
        bias=_DirectionResult(_direction(htf_bias), "legacy_htf_translation"),
        dxy=_DirectionResult(_direction(dxy_context.get("dxy_bias")), "legacy_dxy_translation"),
        news=_SafetyResult(
            _safety(news_context, "news_clear"),
            str(news_context.get("reason", "legacy_news_translation")),
            provenance=str(news_context.get("source", "unavailable")),
        ),
        session=_SessionResult(
            _safety(session_context, "session_allowed"),
            str(session_context.get("reason", "legacy_session_translation")),
            str(session_context.get("active_session", "unknown")),
            bool(session_context.get("is_priority_session", False)),
        ),
        order_block=block,
        evidence=evidence_v003,
        source_candles=source_candles,
        invalidation={
            "order_block_id": pair.block_id,
            "v003_age_bars": pair.age_bars,
            "v003_final_fvg_associated": pair.final_fvg_associated,
            "v003_temporal_fvg_evidence": pair.temporal_fvg_evidence,
            "v003_fvg_evidence": pair.v003_fvg_evidence,
            "v003_fvg_evidence_source": pair.fvg_evidence_source,
            "v003_exact_overlap": pair.exact_overlap,
        },
    )
    evaluator = evaluate_live_strategy if adapter == "live" else evaluate_replay_strategy
    return evaluator(data, policy)


from .models import DirectionResult as _DirectionResult  # noqa: E402
from .models import SafetyResult as _SafetyResult  # noqa: E402
from .models import SessionResult as _SessionResult  # noqa: E402
