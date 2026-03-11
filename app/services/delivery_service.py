"""
Delivery pricing business logic.
"""
from __future__ import annotations

import math

BASE_FEE_PKR = 80.0
PER_KM_COST_PKR = 20.0


def calculate_delivery_fee(distance_km: float) -> float:
    """
    Calculate delivery fee in PKR.

    Formula:
        fee = 80 + (distance_km * 20)

    Input handling:
    - Validates numeric and finite input
    - Protects against negative distance by clamping to zero
    """
    if distance_km is None:
        raise ValueError("distance_km is required")

    try:
        distance = float(distance_km)
    except (TypeError, ValueError) as exc:
        raise ValueError("distance_km must be a number") from exc

    if not math.isfinite(distance):
        raise ValueError("distance_km must be a finite number")

    distance = max(0.0, distance)
    fee = BASE_FEE_PKR + (distance * PER_KM_COST_PKR)
    return round(fee, 2)
