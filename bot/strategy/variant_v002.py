"""V002 Canonical Structural OB/FVG Pair — isolated variant evaluator (H007).

DEVELOPMENT_VARIANT_IMPLEMENTATION — phase6-development-v2-V002 — H007

Frozen variant boundary (``docs/PHASE8_V2_VARIANT_V002.md``; register
``phase6-development-v2-V002``):

* ONE conceptual hypothesis: canonical OB/FVG structural-pair semantics.
* The historical canonical evaluator
  (``bot.strategy.order_blocks.evaluate_order_block``) is NOT modified;
  V1/V001 behavior is unchanged and global
  ``StrategyConfig.order_block_expiry_bars = 30`` is unchanged.
* V002 structural-active OB semantics: a confirmed same-side canonical
  block whose confirmation is causally available, that is not consumed,
  that has suffered no invalidating close by the decision time, that has
  had no prior zone interaction (not mitigated), and whose first-retest
  behavior stays consistent with canonical semantics.  Elapsed age greater
  than 30 bars ALONE never rejects an otherwise untouched/uninvalidated
  block; age is recorded as metadata only (``age_bars``).
* The associated FVG is the frozen final canonical FVG surface, causally
  available (the store's final list is already causally filtered at build
  time), in the same direction as the structural OB / requested side.
  Exact geometric overlap is computed and recorded as a DESCRIPTIVE field
  only and never gates V002 pair membership.  No proximity threshold, no
  partial-overlap threshold, no temporal lag, no H003 rule.
* Gate 11 keeps the frozen architecture: components 2/1/2/1/2, maximum 8,
  threshold 8/8.  In this V002 path the 2-point OB component is
  ``canonical structurally-active OB present`` and the 1-point FVG
  component is ``same-direction final canonical FVG associated with that
  OB``; neither is labeled exact geometric overlap.
* The downstream strategy evaluation below mirrors
  ``bot.strategy.legacy_adapter.evaluate_legacy_context`` but consumes the
  SAME V002 structural-pair semantics used at Gate 11, so a decision that
  passes Gate 11 cannot be rejected afterwards by the historical age-only
  EXPIRED short-circuit.  All other protected semantics (regime, bias,
  DXY, news, session, risk, symbol allowlist, consumption, lifecycle) run
  through the untouched canonical engine.
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

#: States the V002 evaluator reports.  ``ACTIVE`` is the V002
#: eligible-equivalent (canonical ``ELIGIBLE`` / ``RETEST_ELIGIBLE``
#: meaning) and never collapses to ``EXPIRED`` on age alone.
V002_ACTIVE = "ACTIVE"
V002_RETEST_ELIGIBLE = "RETEST_ELIGIBLE"
V002_MITIGATED = "MITIGATED"
V002_INVALIDATED = "INVALIDATED"
V002_CONSUMED = "CONSUMED"
V002_PREMATURE = "PREMATURE"
V002_UNAVAILABLE = "UNAVAILABLE"
V002_DATA_UNSAFE = "DATA_UNSAFE"

#: V002 structural-active states mapped onto canonical ``BlockState`` so the
#: untouched downstream engine sees its own vocabulary.
_V002_TO_BLOCK_STATE = {
    V002_ACTIVE: BlockState.ELIGIBLE,
    V002_RETEST_ELIGIBLE: BlockState.RETEST_ELIGIBLE,
    V002_MITIGATED: BlockState.MITIGATED,
    V002_INVALIDATED: BlockState.INVALIDATED,
    V002_CONSUMED: BlockState.CONSUMED,
    V002_PREMATURE: BlockState.PREMATURE,
    V002_UNAVAILABLE: BlockState.UNAVAILABLE,
    V002_DATA_UNSAFE: BlockState.DATA_UNSAFE,
}

#: V002 Gate-11 component labels (replacing the exact-overlap label ONLY in
#: this V002 scoring path; weights and threshold are unchanged).
V002_OB_LABEL = "Canonical structurally-active OB present"
V002_FVG_LABEL = "Same-direction final canonical FVG associated with the structural OB"

_SIDE_TO_FVG_DIRECTION = {
    StrategySide.LONG: "bullish",
    StrategySide.SHORT: "bearish",
}

# Canonical descriptive-overlap mirror of the frozen gate-11 geometry
# (tolerance atr * 0.30).  DESCRIPTIVE ONLY: its boolean never gates V002.
OVERLAP_TOLERANCE_ATR = 0.30


class V002VariantError(ValueError):
    """Fail closed on V002 contract violations (never guess a semantic)."""


@dataclass(frozen=True)
class V002PairResult:
    """One V002 canonical structural-pair evaluation at a causal decision."""

    state: str
    reason: str
    side: StrategySide
    block_id: str | None
    zone_low: float | None
    zone_high: float | None
    confirmed_at: datetime | None
    age_bars: int
    fvg_associated: bool
    fvg_direction: str | None
    exact_overlap: bool | None
    fvg_top: float | None = None
    fvg_bottom: float | None = None

    @property
    def structurally_active(self) -> bool:
        """V002 eligible-equivalent: age alone has not rejected the pair."""
        return self.state in (V002_ACTIVE, V002_RETEST_ELIGIBLE)


def _final_fvg_for_side(fvgs: Iterable[Any] | None, side: StrategySide) -> dict[str, Any] | None:
    """Same-direction final canonical FVG from the frozen persisted surface.

    The frozen ``get_unfilled_fvgs`` list is already causally available and
    same-direction filtered at acquisition time; V002 performs the explicit
    same-direction membership check here against the requested side.  The
    FIRST such zone (the reducer's ``fvgs[0]`` convention) is the associated
    zone.  No proximity, partial-overlap or temporal-lag rule exists.
    """
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
    """Frozen canonical overlap geometry, recorded descriptively only.

    Exact production expression (``bot/state/gate_reducer.py`` gate 11):
    ``tolerance = atr * 0.30``; ``gap`` is the signed separation of the two
    regions; ``fvg_in_ob = gap <= tolerance``.  The returned boolean is
    metadata and never feeds V002 eligibility.
    """
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


def evaluate_v002_structural_pair(
    frame: pd.DataFrame,
    side: StrategySide,
    decision_at: datetime,
    config: StrategyConfig,
    *,
    fvgs: Iterable[Any] | None = None,
    consumed_ids: frozenset[str] = frozenset(),
) -> V002PairResult:
    """Evaluate the V002 canonical structural pair for one causal decision.

    Detection, selection ordering, causality, consumed/premature handling,
    invalidation and zone-interaction semantics are the frozen canonical
    ones (``bot.strategy.order_blocks``); the ONLY semantic difference is
    that the age-only ``EXPIRED`` short-circuit does not reject the pair —
    age is carried as metadata instead.
    """
    if not isinstance(decision_at, datetime) or decision_at.tzinfo is None:
        return V002PairResult(
            V002_DATA_UNSAFE, "invalid_decision_time", StrategySide.FLAT,
            None, None, None, None, 0, False, None, None,
        )
    if not _valid_frame(frame):
        return V002PairResult(
            V002_DATA_UNSAFE, "malformed_or_naive_candle_frame", StrategySide.FLAT,
            None, None, None, None, 0, False, None, None,
        )
    blocks = [block for block in detect_order_blocks(frame, config) if block.side is side]
    if not blocks:
        return V002PairResult(
            V002_UNAVAILABLE, "no_confirmed_block", StrategySide.FLAT,
            None, None, None, None, 0, False, None, None,
        )
    block = sorted(
        blocks, key=lambda item: (item.confirmed_at, -item.zone_high + item.zone_low, item.block_id)
    )[-1]
    if block.confirmed_at > decision_at:
        return V002PairResult(
            V002_PREMATURE, "confirmation_not_available", block.side,
            block.block_id, block.zone_low, block.zone_high, block.confirmed_at,
            0, False, None, None,
        )
    if block.block_id in consumed_ids:
        return V002PairResult(
            V002_CONSUMED, "block_already_consumed", block.side,
            block.block_id, block.zone_low, block.zone_high, block.confirmed_at,
            0, False, None, None,
        )

    ordered = frame.sort_values("open_time", kind="mergesort").reset_index(drop=True)
    later = ordered.iloc[block.confirmation_index + 1 :]
    later = later[pd.to_datetime(later["available_at"], utc=True) <= pd.Timestamp(decision_at)]
    age_bars = int(len(later))
    for _position, (_index, candle) in enumerate(later.iterrows()):
        close = float(candle["close"])
        if side is StrategySide.LONG and close < block.zone_low:
            return V002PairResult(
                V002_INVALIDATED, "close_below_bullish_zone", block.side,
                block.block_id, block.zone_low, block.zone_high, block.confirmed_at,
                age_bars, False, None, None,
            )
        if side is StrategySide.SHORT and close > block.zone_high:
            return V002PairResult(
                V002_INVALIDATED, "close_above_bearish_zone", block.side,
                block.block_id, block.zone_low, block.zone_high, block.confirmed_at,
                age_bars, False, None, None,
            )
        overlaps = float(candle["low"]) <= block.zone_high and float(candle["high"]) >= block.zone_low
        if overlaps:
            # First zone interaction: the canonical RETEST_ELIGIBLE state on
            # the final available candle, MITIGATED on any earlier candle.
            # Age has NOT short-circuited the pair before this point.
            state = V002_RETEST_ELIGIBLE if _position == len(later) - 1 else V002_MITIGATED
            reason = (
                "first_post_confirmation_retest"
                if state == V002_RETEST_ELIGIBLE
                else "block_already_mitigated"
            )
            return _with_fvg(
                block, side, age_bars, state, reason, frame, config, fvgs
            )
    return _with_fvg(
        block, side, age_bars, V002_ACTIVE, "structurally_active_block", frame, config, fvgs
    )


def _with_fvg(
    block: Any,
    side: StrategySide,
    age_bars: int,
    state: str,
    reason: str,
    frame: pd.DataFrame,
    config: StrategyConfig,
    fvgs: Iterable[Any] | None,
) -> V002PairResult:
    """Attach the same-direction final FVG association + descriptive overlap."""
    fvg = _final_fvg_for_side(fvgs, side)
    if fvg is None:
        return V002PairResult(
            state, reason, block.side, block.block_id, block.zone_low, block.zone_high,
            block.confirmed_at, age_bars, False, None, None, None, None,
        )
    atr = 0.0
    prices = frame[["open", "high", "low", "close"]].astype(float)
    try:
        series = atr_series(prices, config.atr_period_bars)
        value = float(series.iloc[-1])
        if value == value and value > 0:  # finite and positive only
            atr = value
    except (IndexError, ValueError, TypeError):
        atr = 0.0
    exact_overlap = _descriptive_overlap(fvg, block.zone_low, block.zone_high, atr)
    return V002PairResult(
        state, reason, block.side, block.block_id, block.zone_low, block.zone_high,
        block.confirmed_at, age_bars, True,
        str(fvg.get("direction")), exact_overlap,
        float(fvg["top"]), float(fvg["bottom"]),
    )


def score_v002_setup(
    *,
    pair: V002PairResult,
    htf_bias: str,
    price_in_discount_or_premium: bool,
    liquidity_swept: bool,
    min_score_to_trade: int = 8,
) -> dict[str, object]:
    """V002 Gate-11 score: frozen 2/1/2/1/2 architecture, threshold 8/8.

    The 2-point OB component is ``canonical structurally-active OB present``
    and the 1-point FVG component is ``same-direction final canonical FVG
    associated with that OB``.  Exact overlap is NOT a scored component and
    is not labeled here; it remains a separately reported descriptive field
    on the pair result.
    """
    bias = str(htf_bias or "").lower()
    if bias not in ("bullish", "bearish"):
        raise V002VariantError(f"V002 scoring requires a resolved HTF bias, got {htf_bias!r}")
    expected_side = _SIDE_TO_FVG_DIRECTION[pair.side] if pair.side is not StrategySide.FLAT else None
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
    add(bool(pair.structurally_active), 2, V002_OB_LABEL)
    add(bool(pair.fvg_associated), 1, V002_FVG_LABEL)
    add(bool(liquidity_swept), 2, "Liquidity sweep occurred before entry")

    maximum = sum(int(check["max_points"]) for check in checks)
    threshold = int(min_score_to_trade or 8)
    if score == maximum and score >= threshold:
        grade = "A+"
    elif score >= threshold:
        grade = "B"
    else:
        grade = "SKIP"
    assert maximum == 8, "V002 must preserve the frozen 8-point maximum"
    assert tuple((name, weight) for name, weight in COMPONENTS) == (
        ("bias_alignment", 2),
        ("premium_discount_location", 1),
        ("order_block", 2),
        ("fvg_overlap", 1),
        ("liquidity_sweep", 2),
    ), "V002 must preserve the frozen component weights 2/1/2/1/2"
    return {
        "score": score,
        "max_score": maximum,
        "grade": grade,
        "risk_authority": "central_phase4_policy",
        "passes_threshold": score >= threshold,
        "min_score_to_trade": threshold,
        "checks": checks,
    }


def evaluate_v002_strategy(
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
    """Downstream V002 strategy decision over the SAME structural-pair semantics.

    Mirrors ``bot.strategy.legacy_adapter.evaluate_legacy_context`` but
    feeds the untouched canonical engine a V002-mapped ``OrderBlockResult``
    plus V002-meaning evidence, so Gate 11 and the downstream decision share
    one OB semantic definition and one structural-pair evidence set.  All
    protected semantics (regime, bias, DXY, news, session, symbol allowlist)
    run through the untouched engine.
    """
    from .adapters import evaluate_live_strategy, evaluate_replay_strategy
    from .legacy_adapter import _direction, _safety
    from .models import SourceCandle, StrategyInput
    from .regime import classify_regime

    policy = config or StrategyConfig()
    requested = {"bullish": StrategySide.LONG, "bearish": StrategySide.SHORT}.get(
        str(side).lower(), StrategySide.FLAT
    )
    if requested is StrategySide.FLAT:
        raise V002VariantError("V002 requires a resolved bullish/bearish side")
    decision = decision_at.astimezone(timezone.utc)
    pair = evaluate_v002_structural_pair(
        entry_frame, requested, decision, policy,
        fvgs=fvgs, consumed_ids=consumed_block_ids,
    )
    block = OrderBlockResult(
        state=_V002_TO_BLOCK_STATE[pair.state],
        side=pair.side,
        block_id=pair.block_id,
        zone_low=pair.zone_low,
        zone_high=pair.zone_high,
        confirmed_at=pair.confirmed_at,
        reason=pair.reason,
    )
    # V002 component meanings for the untouched engine's confluence check:
    # order_block_present = canonical structurally-active OB present;
    # fvg_overlaps_order_block = same-direction final canonical FVG
    # associated with that OB (NOT exact geometric overlap).
    evidence_v002 = SetupEvidence(
        price_in_discount_or_premium=bool(evidence.price_in_discount_or_premium),
        order_block_present=bool(pair.structurally_active),
        fvg_overlaps_order_block=bool(pair.fvg_associated),
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
        evidence=evidence_v002,
        source_candles=source_candles,
        invalidation={
            "order_block_id": pair.block_id,
            "v002_age_bars": pair.age_bars,
            "v002_exact_overlap": pair.exact_overlap,
            "v002_fvg_associated": pair.fvg_associated,
        },
    )
    evaluator = evaluate_live_strategy if adapter == "live" else evaluate_replay_strategy
    return evaluator(data, policy)


# Import aliases kept at the bottom so the V002 module reads top-down.
from .models import DirectionResult as _DirectionResult  # noqa: E402
from .models import SafetyResult as _SafetyResult  # noqa: E402
from .models import SessionResult as _SessionResult  # noqa: E402
