"""
AI deal detection based on historical price averages.
"""
from __future__ import annotations

from typing import Any

from services.price_history_service import get_trend

_DEAL_THRESHOLD = 0.90
_DEFAULT_MESSAGE = "\u26a1 AI Deal Alert: Price dropped {discount}% below normal market price."


def detect_deal(query: str, current_price: float | int | None) -> dict[str, Any]:
    """
    Detect whether current price is an unusually strong deal.

    Logic:
      if current_price < historical_average * 0.9 => AI Deal
    """
    base = {
        "deal_detected": False,
        "discount_percent": 0,
        "ai_message": None,
    }

    if not query or current_price is None:
        return base

    try:
        price_now = float(current_price)
    except (TypeError, ValueError):
        return base

    if price_now <= 0:
        return base

    trend = get_trend(query)
    avg_price = trend.get("avg_price")
    if avg_price is None:
        return base

    try:
        historical_avg = float(avg_price)
    except (TypeError, ValueError):
        return base

    if historical_avg <= 0:
        return base

    if price_now < historical_avg * _DEAL_THRESHOLD:
        discount = int(round((1 - (price_now / historical_avg)) * 100))
        discount = max(1, discount)
        return {
            "deal_detected": True,
            "discount_percent": discount,
            "ai_message": _DEFAULT_MESSAGE.format(discount=discount),
        }

    return base

