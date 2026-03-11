"""
delivery_service.py — Delivery fee calculation.
─────────────────────────────────────────────────
Base fee + per-km charge model (Pakistan market).
"""
from __future__ import annotations

import math

from config import DELIVERY_BASE_FEE, DELIVERY_PER_KM


def calculate_delivery_fee(distance_km: float) -> float:
    """
    Calculate delivery fee in PKR.

    Formula:
        fee = base_fee + (distance_km × per_km_rate)

    Example (defaults):
        80 + (5.0 × 20) = 180.00 PKR
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
    fee = DELIVERY_BASE_FEE + (distance * DELIVERY_PER_KM)
    return round(fee, 2)
