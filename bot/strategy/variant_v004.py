"""V004 Unified Requested-Side Entry Direction Authority — isolated variant evaluator (H009).

DEVELOPMENT_VARIANT_IMPLEMENTATION — phase6-development-v2-V004 — H009

Governing variant boundary (``docs/PHASE8_V2_VARIANT_V004.md``; register
``phase6-development-v2-V004``):

* ONE conceptual change: Gate-12/13 Directional Authority Unification.
  For setups that have passed V003 Gate-11 confluence scoring (8/8) and
  canonical strategy protections, the authoritative trade direction for
  Gate-12/13 entry routing and liquidity alignment interpretation is the
  already-selected V003 / HTF requested trade side (``requested_side``),
  rather than a diverging persisted ``state.structure_dir``.
* Strict V003 baseline preservation: when V003 produces ``v003_entry_ready == True``,
  V004 returns the exact V003 entry unchanged (source ``V003_BASELINE``).
  All 81 V003 candidates are guaranteed to remain candidates under V004.
* Canonical state invariance: authoritative ``StrategyState`` is never mutated;
  directional fallback evaluation operates strictly on a private deep copy
  (``copied_state.structure_dir = requested_side``).
* Strict liquidity rule invariance: evaluates the exact frozen ``determine_entry``
  logic without relaxation. Valid combinations remain:
  - Bullish: sell + equal_lows OR buy + internal_continuation
  - Bearish: buy + equal_highs OR sell + internal_continuation
  All other combinations remain strictly rejected.
* Readiness & early-entry invariance: score-8 conservative early entry strictly
  requires internal confirmation (BOS/CHOCH seen). The 7 D006 E2 rejections
  remain strictly rejected.
* Fallback entry trade direction: strictly matches ``requested_side`` (BUY for
  bullish, SELL for bearish).
* Zero numeric parameters: no new numeric thresholds, proximity parameters, or
  timer parameters; numeric parameter trials remain 0 / 4.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Mapping

from bot.strategy.variant_v003 import (
    SPEC_SHA256 as V003_SPEC_SHA256,
    V003_ACTIVE,
    V003_CONSUMED,
    V003_DATA_UNSAFE,
    V003_FVG_LABEL,
    V003_INVALIDATED,
    V003_MITIGATED,
    V003_OB_LABEL,
    V003_PREMATURE,
    V003_RETEST_ELIGIBLE,
    V003_UNAVAILABLE,
    V003PairResult,
    V003VariantError,
    evaluate_v003_strategy,
    evaluate_v003_structural_pair,
    score_v003_setup,
)
from strategies.smc_engine.entry_model import (
    _can_use_early_entry,
    determine_entry,
)
from strategies.smc_engine.strategy_state import StrategyState

#: Phase-A preregistration specification SHA-256 bound into tooling
SPEC_SHA256 = "9ad9b5660bcb2d6d209c430958c3d88e47b83122c6c9816b6f5ee40d61b11b7f"

V004_ID = "phase6-development-v2-V004"
H009_ID = "phase8-v2-H009"
V003_ID = "phase6-development-v2-V003"
D006_ID = "phase8-v2-D006"

V004_SOURCE_V003_BASELINE = "V003_BASELINE"
V004_SOURCE_DIRECTIONAL_FALLBACK = "V004_DIRECTIONAL_FALLBACK"
V004_SOURCE_NONE = "NONE"

#: Re-exported Gate-11 components and evaluators (identical to V003)
score_v004_setup = score_v003_setup
evaluate_v004_structural_pair = evaluate_v003_structural_pair
evaluate_v004_strategy = evaluate_v003_strategy


class V004VariantError(ValueError):
    """Fail closed on V004 contract violations (never guess a semantic)."""


def is_valid_liquidity_alignment(
    structure_dir: str | None,
    liquidity_side: str | None,
    liquidity_type: str | None,
) -> bool:
    """Exact frozen liquidity-alignment combinations from determine_entry.

    Bullish valid:
      - liquidity_side == 'sell' AND liquidity_type == 'equal_lows'
      - liquidity_side == 'buy' AND liquidity_type == 'internal_continuation'
    Bearish valid:
      - liquidity_side == 'buy' AND liquidity_type == 'equal_highs'
      - liquidity_side == 'sell' AND liquidity_type == 'internal_continuation'
    """
    if structure_dir == "bullish":
        if liquidity_side == "sell" and liquidity_type == "equal_lows":
            return True
        if liquidity_side == "buy" and liquidity_type == "internal_continuation":
            return True
        return False
    elif structure_dir == "bearish":
        if liquidity_side == "buy" and liquidity_type == "equal_highs":
            return True
        if liquidity_side == "sell" and liquidity_type == "internal_continuation":
            return True
        return False
    return False


def evaluate_v004_entry_readiness(
    *,
    state: Any,
    decision_at: datetime,
    current_price: float,
    pair: Any,
    score: Mapping[str, Any],
    context: Mapping[str, Any],
    requested_side: str,
    v003_gate11_passed: bool,
    v003_strategy_eligible: bool,
    v003_entry: dict[str, Any] | None,
    v003_entry_ready: bool,
    symbol: str = "XAUUSDm",
) -> tuple[dict[str, Any] | None, bool, str]:
    """Evaluate V004 entry readiness under unified requested-side directional authority.

    Args:
        state: Persisted strategy state (never mutated by this function).
        decision_at: Causal decision timestamp.
        current_price: Current market close price.
        pair: V003 structural-pair result.
        score: Gate-11 confluence score dict.
        context: Entry model context dictionary.
        requested_side: Requested trade side ('bullish' or 'bearish' derived from htf_bias).
        v003_gate11_passed: Whether V003 Gate-11 confluence score >= 8/8.
        v003_strategy_eligible: Whether canonical strategy passed all protections.
        v003_entry: Entry dict returned by frozen V003 (if any).
        v003_entry_ready: Whether frozen V003 produced an entry.
        symbol: Instrument symbol (default 'XAUUSDm').

    Returns:
        tuple (entry_result, entry_ready, entry_source)
        where entry_source is one of:
          - "V003_BASELINE"
          - "V004_DIRECTIONAL_FALLBACK"
          - "NONE"
    """
    # 1. Primary path: strict V003 baseline preservation
    if v003_entry_ready and v003_entry is not None:
        return v003_entry, True, V004_SOURCE_V003_BASELINE

    # 2. Preconditions for directional-authority fallback
    if not (v003_gate11_passed and v003_strategy_eligible):
        return None, False, V004_SOURCE_NONE

    req_side = str(requested_side).lower() if requested_side is not None else ""
    if req_side not in ("bullish", "bearish"):
        return None, False, V004_SOURCE_NONE

    if state is None:
        return None, False, V004_SOURCE_NONE

    persisted_dir = getattr(state, "structure_dir", None)
    if persisted_dir not in ("bullish", "bearish"):
        # Unresolved structure direction fails closed (E3 preservation)
        return None, False, V004_SOURCE_NONE

    if persisted_dir == req_side:
        # No directional divergence; rejection is not due to authority mismatch
        return None, False, V004_SOURCE_NONE

    # 3. State readiness and conservative early-entry validation
    # Operates strictly on a deep copy; authoritative state is NEVER mutated.
    copied_state = copy.deepcopy(state)

    if copied_state.is_expired():
        return None, False, V004_SOURCE_NONE

    score_val = int(score.get("score", 0) or 0)
    ctx_dict = dict(context)

    state_ready = bool(copied_state.ready_for_entry())
    early_entry_ok = bool(_can_use_early_entry(copied_state, score_value=score_val, context=ctx_dict))

    if (not state_ready) and (not early_entry_ok):
        # Readiness incomplete and early entry not authorized (E2 preservation: internal BOS/CHOCH missing)
        return None, False, V004_SOURCE_NONE

    # Safety predicates
    if bool(copied_state.daily_limits_hit):
        return None, False, V004_SOURCE_NONE

    news_clear = bool(
        copied_state.news_status.get("news_clear", True)
        if copied_state.news_status is not None
        else True
    )
    if not news_clear:
        return None, False, V004_SOURCE_NONE

    if not bool(copied_state.displacement_seen):
        return None, False, V004_SOURCE_NONE

    if not bool(copied_state.liquidity_swept):
        return None, False, V004_SOURCE_NONE

    # 4. Apply unified directional authority to copied state
    copied_state.structure_dir = req_side

    # 5. Invoke frozen determine_entry on copied state
    entry = determine_entry(
        symbol,
        copied_state,
        current_price,
        score_result=dict(score),
        context=ctx_dict,
        emit_log=None,
    )

    if entry is not None:
        expected_dir = "buy" if req_side == "bullish" else "sell"
        actual_dir = str(entry.get("direction", "")).lower()
        if actual_dir != expected_dir:
            raise V004VariantError(
                f"V004 directional fallback direction mismatch: "
                f"expected {expected_dir!r} for requested_side {req_side!r}, "
                f"got {actual_dir!r}"
            )
        return entry, True, V004_SOURCE_DIRECTIONAL_FALLBACK

    return None, False, V004_SOURCE_NONE
