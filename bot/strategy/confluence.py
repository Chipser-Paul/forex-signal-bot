from __future__ import annotations

from .models import ConfluenceResult, SetupEvidence


COMPONENTS = (
    ("bias_alignment", 2),
    ("premium_discount_location", 1),
    ("order_block", 2),
    ("fvg_overlap", 1),
    ("liquidity_sweep", 2),
)


def score_evidence(evidence: SetupEvidence, threshold: int = 8) -> ConfluenceResult:
    values = {
        "bias_alignment": True,
        "premium_discount_location": evidence.price_in_discount_or_premium,
        "order_block": evidence.order_block_present,
        "fvg_overlap": evidence.fvg_overlaps_order_block,
        "liquidity_sweep": evidence.liquidity_swept,
    }
    components = tuple(
        (name, weight, bool(values[name])) for name, weight in COMPONENTS
    )
    score = sum(weight for _name, weight, passed in components if passed)
    maximum = sum(weight for _name, weight in COMPONENTS)
    return ConfluenceResult(score, maximum, threshold, score >= threshold, components)
