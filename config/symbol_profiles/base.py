DEFAULT_PROFILE = {
    "structure_tf": "H1",
    "structure_bars": 300,
    "entry_tf": "M15",
    "entry_bars": 150,
    "support_bias_tf": None,
    "support_bias_bars": 0,
    "pair_limit": 1,
    "risk_per_trade": 0.01,
    # min_rr: reward target used to place TP / validate setups.
    # min_execution_rr: floor the *filled* RR must clear or the trade is voided.
    # These are intentionally different: place TP at the target, but only reject
    # a fill when execution drift pushes RR below the (looser) execution floor.
    "min_rr": 3.0,
    "min_execution_rr": 1.2,
    "kill_switch_min_bars": 4,
    "kill_switch_atr_break_mult": 0.15,
    "market_structure": {
        "DISPLACEMENT_ATR_MULT": 1.2,
        "LOW_VOL_RATIO": 0.7,
        "HIGH_VOL_RATIO": 1.6,
        "MIN_SWING_ATR_MULT": 0.6,
        "PRESSURE_MIN_MOVE_ATR": 1.2,
        "PRESSURE_MIN_BAR_COUNT": 3,
    },
    "liquidity": {
        "lookback": 20,
        "SWEEP_STRENGTH_MIN": 0.20,
        "BODY_DOMINANCE_MIN": 0.30,
        "EQ_TOL_ATR_MULT": 0.15,
        "LOW_VOL_SKIP_RATIO": 0.60,
    },
    "displacement": {
        "impulse_atr_mult": 1.2,
        "lookback_candles": 3,
    },
    "ob_breaker": {
        "level_pad_atr_mult": 0.20,
        "lookback": 30,
        "search_back": 12,
    },
    "execution_levels": {
        "min_stop_atr_mult": 0.35,
        "min_stop_price": 0.0,
        "min_stop_points": 500,
        "anchor_buffer_atr_mult": 0.0,
        "anchor_buffer_price": 0.0,
    },
    # Phase 1: Structural shift variant configuration
    "structural_shift": {
        "variant": "variant_a",  # Options: "original", "variant_a", "variant_b"
        # Variant A: Weighted collapse - single strength input from all three signals
        "variant_a": {
            "enabled": True,
            "strength_scale": "continuous",  # "continuous" or "tiered"
            "displacement_tiers": [0.8, 1.0, 1.3, 1.8],  # ATR multiplier buckets
            "sweep_weight": 1.0,
            "displacement_weight": 1.5,
            "bos_weight": 1.0,
        },
        # Variant B: Sequential chain - each signal must follow the prior
        "variant_b": {
            "enabled": False,
            "require_sweep_first": True,
            "require_displacement_after_sweep": True,
            "require_bos_after_displacement": True,
        },
        # Freshness/decay window (applies to both variants)
        "freshness_window": {
            "enabled": True,
            "n1_max_bars": 5,  # Max bars from sweep to displacement
            "n2_max_bars": 8,  # Max bars from displacement to BOS/CHoCH
            "n3_max_bars": 13,  # Max bars from BOS/CHoCH to entry
        },
    },
    # Phase 2: Displacement tier system for position sizing
    "displacement_tiers": {
        "enabled": True,
        "tier_1": {
            "min_atr_mult": 0.8,
            "max_atr_mult": 1.0,
            "action": "log_only",  # No entry, just log
        },
        "tier_2": {
            "min_atr_mult": 1.0,
            "max_atr_mult": 1.3,
            "action": "partial_entry",
            "position_size_pct": 0.5,  # 50% of normal position size
        },
        "tier_3": {
            "min_atr_mult": 1.3,
            "max_atr_mult": float("inf"),
            "action": "full_entry",
            "position_size_pct": 1.0,  # 100% of normal position size
        },
    },
}
