"""
Location helpers for fallback distance calculations.
"""
from __future__ import annotations

import math


def calculate_haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate great-circle distance between two coordinates in kilometers.
    Uses Earth radius = 6371 km.
    """
    radius_km = 6371.0

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c
