"""
location_utils.py — Standalone location helpers.
──────────────────────────────────────────────────
Provides a Haversine distance function that returns
the same dict format as the routing service, making
it a drop-in fallback.
"""
from __future__ import annotations

from config import AVG_SPEED_KMH
from utils.distance import haversine_km


def calculate_haversine_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> dict:
    """
    Haversine-based distance estimate with road-factor correction.

    Returns:
        {
            "distance_km": float,   # estimated road distance
            "duration_min": float,  # estimated travel time
            "via": "haversine_estimate"
        }
    """
    crow_km = haversine_km(lat1, lon1, lat2, lon2)
    road_km = round(crow_km * 1.3, 2)
    duration = round((road_km / AVG_SPEED_KMH) * 60, 2)
    return {
        "distance_km":  road_km,
        "duration_min": duration,
        "via":          "haversine_estimate",
    }
