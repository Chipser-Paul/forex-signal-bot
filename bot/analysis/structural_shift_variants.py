"""
Structural Shift Variants for Phase 1
Implements Variant A (Weighted collapse) and Variant B (Sequential chain)
with freshness/decay window support.
"""

from typing import Any, Optional
from utils.log import log


def calculate_variant_a_strength(
    liquidity_signal: dict[str, Any],
    displacement: dict[str, Any],
    internal_structure: dict[str, Any],
    atr: float,
    config: dict[str, Any],
) -> dict[str, Any]:
    """
    Variant A: Weighted collapse - single strength input from all three signals.
    
    Combines liquidity sweep, displacement, and BOS/CHoCH into a continuous
    strength value (0-3 scale or continuous ATR multiplier).
    
    Returns:
        dict with:
        - strength: float (continuous strength value)
        - tier: int (0-3 tier based on displacement ATR multiplier)
        - components: dict with individual component values
    """
    variant_config = config.get("variant_a", {})
    displacement_tiers = variant_config.get("displacement_tiers", [0.8, 1.0, 1.3, 1.8])
    sweep_weight = variant_config.get("sweep_weight", 1.0)
    displacement_weight = variant_config.get("displacement_weight", 1.5)
    bos_weight = variant_config.get("bos_weight", 1.0)
    
    # Extract component values
    sweep_strength = float(liquidity_signal.get("strength", 0.0)) if liquidity_signal else 0.0
    displacement_atr_mult = float(displacement.get("atr_multiplier", 0.0)) if displacement else 0.0
    bos_present = bool(
        (internal_structure.get("event") in ("BOS", "CHOCH")) or
        (internal_structure.get("early_event", {}).get("event") in ("BOS", "CHOCH"))
    ) if internal_structure else False
    
    # Determine displacement tier
    tier = 0
    for i, threshold in enumerate(displacement_tiers):
        if displacement_atr_mult >= threshold:
            tier = i + 1
    
    # Calculate weighted strength
    # Normalize sweep strength (typically 0-1 range)
    normalized_sweep = min(sweep_strength, 1.0)
    
    # Normalize displacement tier to 0-1 range
    normalized_displacement = tier / len(displacement_tiers) if displacement_tiers else 0.0
    
    # BOS is binary (0 or 1)
    bos_value = 1.0 if bos_present else 0.0
    
    # Weighted sum
    total_weight = sweep_weight + displacement_weight + bos_weight
    if total_weight > 0:
        strength = (
            (normalized_sweep * sweep_weight) +
            (normalized_displacement * displacement_weight) +
            (bos_value * bos_weight)
        ) / total_weight
    else:
        strength = 0.0
    
    return {
        "strength": strength,
        "tier": tier,
        "displacement_atr_mult": displacement_atr_mult,
        "components": {
            "sweep_strength": sweep_strength,
            "displacement_tier": tier,
            "bos_present": bos_present,
        },
    }


def check_variant_b_sequence(
    liquidity_signal: dict[str, Any],
    displacement: dict[str, Any],
    internal_structure: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """
    Variant B: Sequential chain - each signal must follow the prior.
    
    Requires:
    1. Sweep must precede displacement
    2. Displacement must precede BOS/CHoCH
    3. All three must be present in sequence
    
    Returns:
        dict with:
        - pass: bool (whether sequence is valid)
        - missing_stage: str (which stage failed, if any)
        - sequence_order: dict with bar indices for each stage
    """
    variant_config = config.get("variant_b", {})
    require_sweep = variant_config.get("require_sweep_first", True)
    require_displacement = variant_config.get("require_displacement_after_sweep", True)
    require_bos = variant_config.get("require_bos_after_displacement", True)
    
    # Extract bar indices (if available from the signals)
    # Note: This requires the signal engines to return bar indices
    sweep_index = liquidity_signal.get("bar_index") if liquidity_signal else None
    displacement_index = displacement.get("bar_index") if displacement else None
    bos_index = internal_structure.get("bar_index") if internal_structure else None
    
    # Check presence
    has_sweep = bool(liquidity_signal)
    has_displacement = bool(displacement and displacement.get("valid"))
    has_bos = bool(
        internal_structure and
        (internal_structure.get("event") in ("BOS", "CHOCH") or
         internal_structure.get("early_event", {}).get("event") in ("BOS", "CHOCH"))
    )
    
    missing_stage = None
    
    if require_sweep and not has_sweep:
        missing_stage = "sweep"
    elif require_displacement and not has_displacement:
        missing_stage = "displacement"
    elif require_bos and not has_bos:
        missing_stage = "bos"
    
    # Check sequence order if all present and indices available
    sequence_valid = True
    if all(x is not None for x in [sweep_index, displacement_index, bos_index]):
        if require_sweep and require_displacement:
            if displacement_index <= sweep_index:
                sequence_valid = False
                missing_stage = "displacement_after_sweep"
        if require_displacement and require_bos and sequence_valid:
            if bos_index <= displacement_index:
                sequence_valid = False
                missing_stage = "bos_after_displacement"
    
    return {
        "pass": missing_stage is None and sequence_valid,
        "missing_stage": missing_stage,
        "sequence_order": {
            "sweep_index": sweep_index,
            "displacement_index": displacement_index,
            "bos_index": bos_index,
        },
        "components": {
            "has_sweep": has_sweep,
            "has_displacement": has_displacement,
            "has_bos": has_bos,
        },
    }


def check_freshness_window(
    timing_info: dict[str, str],
    config: dict[str, Any],
    entry_tf_bars: int = 1,  # Bars per candle in entry timeframe
) -> dict[str, Any]:
    """
    Check freshness/decay window for structural shift signals.
    
    Rejects setup if:
    - Displacement doesn't follow sweep within N1 bars
    - BOS/CHoCH doesn't follow displacement within N2 bars
    - Entry doesn't occur within N3 bars of last confirmation
    
    Args:
        timing_info: dict with timestamps for sweep, displacement, bos, entry
        config: freshness_window config with n1_max_bars, n2_max_bars, n3_max_bars
        entry_tf_bars: number of data points per candle in entry timeframe
    
    Returns:
        dict with:
        - pass: bool (whether freshness window is valid)
        - failed_stage: str (which freshness check failed, if any)
        - delays: dict with bar counts between stages
    """
    freshness_config = config.get("freshness_window", {})
    if not freshness_config.get("enabled", False):
        return {"pass": True, "failed_stage": None, "delays": {}}
    
    n1_max = freshness_config.get("n1_max_bars", 5)
    n2_max = freshness_config.get("n2_max_bars", 8)
    n3_max = freshness_config.get("n3_max_bars", 13)
    
    from datetime import datetime
    
    def parse_ts(ts_str: Optional[str]) -> Optional[datetime]:
        if not ts_str:
            return None
        try:
            return datetime.fromisoformat(ts_str)
        except Exception:
            return None
    
    sweep_ts = parse_ts(timing_info.get("sweep_detected"))
    displacement_ts = parse_ts(timing_info.get("displacement_detected"))
    bos_ts = parse_ts(timing_info.get("internal_structure_detected"))
    entry_ts = parse_ts(timing_info.get("entry_ready"))
    
    failed_stage = None
    delays = {}
    
    # Check N1: Sweep -> Displacement
    if sweep_ts and displacement_ts:
        delay_seconds = (displacement_ts - sweep_ts).total_seconds()
        # Approximate bar count (assuming 15-min bars for M15 timeframe)
        delay_bars = int(delay_seconds / (15 * 60)) if delay_seconds > 0 else 0
        delays["sweep_to_displacement_bars"] = delay_bars
        if delay_bars > n1_max:
            failed_stage = "sweep_to_displacement_exceeded"
    
    # Check N2: Displacement -> BOS
    if displacement_ts and bos_ts and failed_stage is None:
        delay_seconds = (bos_ts - displacement_ts).total_seconds()
        delay_bars = int(delay_seconds / (15 * 60)) if delay_seconds > 0 else 0
        delays["displacement_to_bos_bars"] = delay_bars
        if delay_bars > n2_max:
            failed_stage = "displacement_to_bos_exceeded"
    
    # Check N3: BOS -> Entry
    if bos_ts and entry_ts and failed_stage is None:
        delay_seconds = (entry_ts - bos_ts).total_seconds()
        delay_bars = int(delay_seconds / (15 * 60)) if delay_seconds > 0 else 0
        delays["bos_to_entry_bars"] = delay_bars
        if delay_bars > n3_max:
            failed_stage = "bos_to_entry_exceeded"
    
    return {
        "pass": failed_stage is None,
        "failed_stage": failed_stage,
        "delays": delays,
    }
