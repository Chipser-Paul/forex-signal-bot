# strategies/smc_engine/entry_model.py

from typing import Optional, Dict
from strategies.smc_engine.strategy_state import StrategyState
from utils.log import log


def _zone_mid(zone):
    if isinstance(zone, dict):
        top = float(zone.get("top", 0.0))
        bottom = float(zone.get("bottom", 0.0))
        if top or bottom:
            return (top + bottom) / 2.0
    if isinstance(zone, (list, tuple)) and len(zone) == 2:
        return (float(zone[0]) + float(zone[1])) / 2.0
    return None


def _can_use_early_entry(state: StrategyState, score_value: int, context: dict | None = None) -> bool:
    context = context or {}
    state.ready_for_entry()
    missing = set(state.missing_conditions)

    # Which conditions can be missing for early entry.
    # "Confirmed structure" is always relaxable — we can enter in transition/range
    # if the setup is strong enough. "Displacement / FVG" is also relaxable when
    # the score is high enough (≥10) — a clean sweep + high score already provides
    # enough confidence to act before formal displacement fires.
    allowed_missing = {"Confirmed structure"}
    if score_value >= 10:
        allowed_missing.add("Displacement / FVG")

    if not missing.issubset(allowed_missing):
        return False

    # Structure state: accept transition, range, or pre-confirmation (None means
    # the structure engine hasn't classified yet, which is fine for early entry)
    if state.structure_state not in ("transition", "range") and state.structure_state is not None:
        return False
    if score_value < 8:
        return False

    internal_event = context.get("internal_structure_event")
    has_internal_confirmation = internal_event in ("BOS", "CHOCH") or bool(context.get("sweep_rejected"))
    has_zone_context = bool(context.get("ob_zone")) or bool(context.get("fvg_zone"))
    has_priority_context = bool(context.get("asian_liquidity_swept")) or bool(context.get("asian_sweep_setup"))

    return bool(has_internal_confirmation and (has_zone_context or has_priority_context))


def check_asian_sweep_setup(context: dict | None = None) -> bool:
    if not context:
        return False
    return bool(
        context.get("after_london_open")
        and context.get("asian_liquidity_swept")
        and context.get("sweep_rejected")
        and context.get("htf_zone_alignment")
    )


def determine_entry(
    symbol: str,
    state: StrategyState,
    current_price: float,
    score_result: dict | None = None,
    context: dict | None = None,
) -> Optional[Dict]:

    if state.is_expired():
        log("Entry Model : State expired -> reset", "yellow")
        state.reset()
        return None

    state_ready = state.ready_for_entry()
    early_entry_ok = _can_use_early_entry(state, score_value=int((score_result or {}).get("score", 0) or 0), context=context)
    if not state_ready and not early_entry_ok:
        log("Entry Model : WAIT (conditions incomplete)", "yellow")
        return None
    if not state_ready and early_entry_ok:
        log("Entry Model : EARLY ENTRY ALLOWED (strong transitional setup)", "cyan")

    structure = state.structure_dir
    liquidity_side = state.liquidity_side
    liquidity_type = state.liquidity_type
    fvg = state.fvg_zone
    ob_zone = context.get("ob_zone") if context else state.ob_zone
    score_value = int((score_result or {}).get("score", 0) or 0)
    score_grade = (score_result or {}).get("grade")
    entry_mode = "aggressive" if score_value >= 10 else "conservative" if score_value >= 8 else None

    log(f"DEBUG -> side={liquidity_side}, type={liquidity_type}", "cyan")

    pullback_price = None
    if fvg and isinstance(fvg, tuple):
        pullback_price = sum(fvg) / 2
    elif context and context.get("fvg_zone"):
        pullback_price = _zone_mid(context.get("fvg_zone"))

    ob_mid = _zone_mid(ob_zone)
    asian_sweep = check_asian_sweep_setup(context)

    # ==========================================================
    # BULLISH STRUCTURE
    # ==========================================================
    if structure == "bullish":

        valid_setup = False
        setup_label = ""

        # External reversal (premium)
        if liquidity_side == "sell" and liquidity_type == "equal_lows":
            valid_setup = True
            setup_label = "External SELL-side sweep"

        # Internal continuation (bullish trend continuation)
        elif liquidity_side == "buy" and liquidity_type == "internal_continuation":
            valid_setup = True
            setup_label = "Internal continuation (bullish)"

        if not valid_setup:
            log("Entry Model : No valid bullish liquidity alignment", "yellow")
            return None

        if entry_mode == "aggressive" and ob_mid is not None:
            state.register_setup_candidate(
                trade_direction="buy",
                score=score_value,
                grade=score_grade,
                entry_mode="aggressive",
                ob_zone=ob_zone,
                fvg_zone=fvg,
                asian_sweep=asian_sweep,
            )
            log(f"Entry Model : BUY -> AGGRESSIVE LIMIT | {setup_label}", "green")
            return {
                "direction": "buy",
                "entry_type": "limit",
                "entry_mode": "aggressive",
                "limit_entry": ob_mid,
                "market_entry": current_price,
                "pullback_entry": pullback_price,
                "reason": f"Bullish structure + {setup_label} + aggressive OB entry",
                "score": score_value,
                "grade": score_grade,
                "asian_sweep_setup": asian_sweep,
            }

        if entry_mode == "aggressive":
            # Score ≥10 but no valid OB zone — aggressive market entry instead of
            # falling back to conservative partial. The highest-conviction setups
            # should not be blocked waiting for a retrace that may never come.
            state.register_setup_candidate(
                trade_direction="buy",
                score=score_value,
                grade=score_grade,
                entry_mode="aggressive",
                ob_zone=ob_zone,
                fvg_zone=fvg,
                asian_sweep=asian_sweep,
            )
            log(f"Entry Model : BUY -> AGGRESSIVE MARKET | {setup_label}", "green")
            return {
                "direction": "buy",
                "entry_type": "market",
                "entry_mode": "aggressive",
                "market_entry": current_price,
                "pullback_entry": pullback_price,
                "reason": f"Bullish structure + {setup_label} + aggressive market entry (no OB zone)",
                "score": score_value,
                "grade": score_grade,
                "asian_sweep_setup": asian_sweep,
            }

        state.register_setup_candidate(
            trade_direction="buy",
            score=score_value,
            grade=score_grade,
            entry_mode="conservative" if entry_mode else "legacy_partial",
            ob_zone=ob_zone,
            fvg_zone=fvg,
            asian_sweep=asian_sweep,
        )
        log(f"Entry Model : BUY -> PARTIAL | {setup_label}", "green")

        return {
            "direction": "buy",
            "entry_type": "partial",
            "entry_mode": "conservative" if entry_mode else "legacy_partial",
            "market_entry": current_price,
            "pullback_entry": pullback_price,
            "reason": f"Bullish structure + {setup_label} + displacement",
            "score": score_value,
            "grade": score_grade,
            "asian_sweep_setup": asian_sweep,
        }

    # ==========================================================
    # BEARISH STRUCTURE
    # ==========================================================
    if structure == "bearish":

        valid_setup = False
        setup_label = ""

        # External reversal (premium)
        if liquidity_side == "buy" and liquidity_type == "equal_highs":
            valid_setup = True
            setup_label = "External BUY-side sweep"

        # Internal continuation (bearish trend continuation)
        elif liquidity_side == "sell" and liquidity_type == "internal_continuation":
            valid_setup = True
            setup_label = "Internal continuation (bearish)"

        if not valid_setup:
            log("Entry Model : No valid bearish liquidity alignment", "yellow")
            return None

        if entry_mode == "aggressive" and ob_mid is not None:
            state.register_setup_candidate(
                trade_direction="sell",
                score=score_value,
                grade=score_grade,
                entry_mode="aggressive",
                ob_zone=ob_zone,
                fvg_zone=fvg,
                asian_sweep=asian_sweep,
            )
            log(f"Entry Model : SELL -> AGGRESSIVE LIMIT | {setup_label}", "green")
            return {
                "direction": "sell",
                "entry_type": "limit",
                "entry_mode": "aggressive",
                "limit_entry": ob_mid,
                "market_entry": current_price,
                "pullback_entry": pullback_price,
                "reason": f"Bearish structure + {setup_label} + aggressive OB entry",
                "score": score_value,
                "grade": score_grade,
                "asian_sweep_setup": asian_sweep,
            }

        if entry_mode == "aggressive":
            # Score ≥10 but no valid OB zone — aggressive market entry
            state.register_setup_candidate(
                trade_direction="sell",
                score=score_value,
                grade=score_grade,
                entry_mode="aggressive",
                ob_zone=ob_zone,
                fvg_zone=fvg,
                asian_sweep=asian_sweep,
            )
            log(f"Entry Model : SELL -> AGGRESSIVE MARKET | {setup_label}", "green")
            return {
                "direction": "sell",
                "entry_type": "market",
                "entry_mode": "aggressive",
                "market_entry": current_price,
                "pullback_entry": pullback_price,
                "reason": f"Bearish structure + {setup_label} + aggressive market entry (no OB zone)",
                "score": score_value,
                "grade": score_grade,
                "asian_sweep_setup": asian_sweep,
            }

        state.register_setup_candidate(
            trade_direction="sell",
            score=score_value,
            grade=score_grade,
            entry_mode="conservative" if entry_mode else "legacy_partial",
            ob_zone=ob_zone,
            fvg_zone=fvg,
            asian_sweep=asian_sweep,
        )
        log(f"Entry Model : SELL -> PARTIAL | {setup_label}", "green")

        return {
            "direction": "sell",
            "entry_type": "partial",
            "entry_mode": "conservative" if entry_mode else "legacy_partial",
            "market_entry": current_price,
            "pullback_entry": pullback_price,
            "reason": f"Bearish structure + {setup_label} + displacement",
            "score": score_value,
            "grade": score_grade,
            "asian_sweep_setup": asian_sweep,
        }

    log("Entry Model : WAIT", "yellow")
    return None
