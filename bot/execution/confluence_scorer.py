from __future__ import annotations


def score_setup(context) -> dict[str, object]:
    """
    Score a setup in a transparent way so we can log exactly why it passed or failed.
    Context can be any mapping-like object with the expected keys.
    """
    score = 0
    checks: list[dict[str, object]] = []

    def add(condition: bool, points: int, label: str):
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

    htf_bias = context.get("htf_bias")
    trade_direction = context.get("trade_direction")
    price_in_pd = bool(context.get("price_in_discount_or_premium"))
    valid_ob = bool(context.get("valid_ob_present"))
    fvg_in_ob = bool(context.get("fvg_in_ob_zone"))
    liquidity_swept = bool(context.get("liquidity_swept_before_entry"))
    # NOTE: internal_bos moved to Gate 10 (hard boolean gate), not scored here
    session_allowed = bool(context.get("session_allowed", True))
    dxy_confirms = bool(context.get("dxy_confirms_bias"))
    news_clear = bool(context.get("no_news_in_30min"))

    add(htf_bias == trade_direction, 2, "HTF bias aligns with trade direction")
    add(price_in_pd, 1, "Price located in premium/discount zone")
    add(valid_ob, 2, "Valid order block present")
    add(fvg_in_ob, 1, "FVG overlaps the order block zone")
    add(liquidity_swept, 2, "Liquidity sweep occurred before entry")
    # Internal M15 BOS/CHoCH removed from scoring - now Gate 10 hard check
    add(session_allowed, 1, "All-session trading enabled")
    add(dxy_confirms, 1, "DXY confirms or supports the setup")
    add(news_clear, 1, "No nearby high-impact news blackout")

    min_score_to_trade = int(context.get("min_score_to_trade", 8) or 8)

    if score >= 10:
        grade = "A+"
        risk_pct = 0.02
    elif score >= min_score_to_trade:
        grade = "B"
        risk_pct = 0.015
    else:
        grade = "SKIP"
        risk_pct = 0.0

    return {
        "score": score,
        "max_score": sum(int(check["max_points"]) for check in checks),
        "grade": grade,
        "risk_pct": risk_pct,
        "passes_threshold": score >= min_score_to_trade,
        "min_score_to_trade": min_score_to_trade,
        "checks": checks,
    }
