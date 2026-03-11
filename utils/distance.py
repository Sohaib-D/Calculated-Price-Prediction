"""
distance.py - distance and travel-cost calculations.

Primary:  OSRM routing API (no key required)
Secondary: MapTiler routing API (key-based, optional)
Fallback: Haversine estimate (local)
"""
from __future__ import annotations

import math
import os
import threading
import time

import requests

from config import (
    AVG_SPEED_KMH,
    FUEL_COST_PER_KM,
    MAPTILER_API_KEY,
    MAPTILER_BASE_URL,
    MAPTILER_CONNECT_TIMEOUT_SECONDS,
    MAPTILER_PROFILE,
    MAPTILER_READ_TIMEOUT_SECONDS,
    OSRM_BASE_URL,
    OSRM_CONNECT_TIMEOUT_SECONDS,
    OSRM_READ_TIMEOUT_SECONDS,
    ROUTING_PROVIDER,
    TIME_VALUE_PER_HOUR,
)
_DISTANCE_CACHE_TTL_SECONDS = int(os.environ.get("DISTANCE_CACHE_TTL_SECONDS", "600"))
_DISTANCE_CACHE_MAX_ENTRIES = int(os.environ.get("DISTANCE_CACHE_MAX_ENTRIES", "2048"))
_OSRM_FAILURE_THRESHOLD = int(os.environ.get("OSRM_FAILURE_THRESHOLD", "2"))
_OSRM_FAILURE_COOLDOWN_SECONDS = float(os.environ.get("OSRM_FAILURE_COOLDOWN_SECONDS", "180"))

_DISTANCE_CACHE: dict[str, tuple[float, dict]] = {}
_DISTANCE_CACHE_LOCK = threading.Lock()
_OSRM_STATE_LOCK = threading.Lock()
_OSRM_CONSECUTIVE_FAILURES = 0
_OSRM_DISABLED_UNTIL = 0.0


def _distance_cache_key(
    provider: str,
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> str:
    return (
        f"{provider}|"
        f"{round(origin_lat, 5)}|{round(origin_lon, 5)}|"
        f"{round(dest_lat, 5)}|{round(dest_lon, 5)}"
    )


def _cache_get(key: str) -> dict | None:
    now = time.time()
    with _DISTANCE_CACHE_LOCK:
        item = _DISTANCE_CACHE.get(key)
        if not item:
            return None
        expires_at, payload = item
        if expires_at <= now:
            _DISTANCE_CACHE.pop(key, None)
            return None
        return dict(payload)


def _cache_set(key: str, payload: dict) -> None:
    if _DISTANCE_CACHE_TTL_SECONDS <= 0 or _DISTANCE_CACHE_MAX_ENTRIES <= 0:
        return
    with _DISTANCE_CACHE_LOCK:
        now = time.time()
        if len(_DISTANCE_CACHE) >= _DISTANCE_CACHE_MAX_ENTRIES:
            expired_keys = [k for k, (expires_at, _) in _DISTANCE_CACHE.items() if expires_at <= now]
            for expired in expired_keys:
                _DISTANCE_CACHE.pop(expired, None)
            while len(_DISTANCE_CACHE) >= _DISTANCE_CACHE_MAX_ENTRIES:
                oldest_key = next(iter(_DISTANCE_CACHE))
                _DISTANCE_CACHE.pop(oldest_key, None)
        _DISTANCE_CACHE[key] = (now + _DISTANCE_CACHE_TTL_SECONDS, dict(payload))


def _osrm_is_temporarily_disabled() -> bool:
    with _OSRM_STATE_LOCK:
        return time.time() < _OSRM_DISABLED_UNTIL


def _record_osrm_success() -> None:
    global _OSRM_CONSECUTIVE_FAILURES, _OSRM_DISABLED_UNTIL
    with _OSRM_STATE_LOCK:
        _OSRM_CONSECUTIVE_FAILURES = 0
        _OSRM_DISABLED_UNTIL = 0.0


def _record_osrm_failure() -> None:
    global _OSRM_CONSECUTIVE_FAILURES, _OSRM_DISABLED_UNTIL
    with _OSRM_STATE_LOCK:
        _OSRM_CONSECUTIVE_FAILURES += 1
        if _OSRM_CONSECUTIVE_FAILURES >= max(1, _OSRM_FAILURE_THRESHOLD):
            _OSRM_DISABLED_UNTIL = time.time() + max(0.0, _OSRM_FAILURE_COOLDOWN_SECONDS)
            _OSRM_CONSECUTIVE_FAILURES = 0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in kilometres between two points."""
    radius_km = 6_371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius_km * 2 * math.asin(math.sqrt(a))


def _haversine_distance(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> dict:
    crow_km = haversine_km(origin_lat, origin_lon, dest_lat, dest_lon)
    road_km = crow_km * 1.3
    duration_min = (road_km / max(AVG_SPEED_KMH, 1e-6)) * 60
    return {
        "distance_km": round(road_km, 2),
        "duration_min": round(duration_min, 1),
        "via": "haversine_estimate",
    }


def format_duration(duration_min: float) -> str:
    """Format a duration in minutes into a compact, human-friendly label."""
    try:
        minutes = float(duration_min)
    except (TypeError, ValueError):
        return "0m"

    if minutes <= 0:
        return "0m"

    total_minutes = int(round(minutes))
    minute = 1
    hour = 60 * minute
    day = 24 * hour
    week = 7 * day
    month = 30 * day
    year = 365 * day

    def plural(value: int, singular: str, plural_label: str) -> str:
        return singular if value == 1 else plural_label

    if total_minutes >= year:
        years = total_minutes // year
        return f"{years} {plural(years, 'year', 'years')}"
    if total_minutes >= month:
        months = total_minutes // month
        return f"{months} {plural(months, 'month', 'months')}"
    if total_minutes >= week:
        weeks = total_minutes // week
        return f"{weeks} {plural(weeks, 'week', 'weeks')}"
    if total_minutes >= day:
        days = total_minutes // day
        return f"{days} {plural(days, 'day', 'days')}"
    if total_minutes >= hour:
        hours = total_minutes // hour
        mins = total_minutes % hour
        hour_label = "hr" if hours == 1 else "hrs"
        return f"{hours}{hour_label}" if mins == 0 else f"{hours}{hour_label} {mins}m"
    return f"{total_minutes}m"


def _osrm_distance(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> dict | None:
    if _osrm_is_temporarily_disabled():
        return None

    base_url = (OSRM_BASE_URL or "").strip().rstrip("/")
    if not base_url:
        return None

    url = f"{base_url}/route/v1/driving/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
    params = {
        "overview": "false",
        "alternatives": "false",
        "steps": "false",
    }
    timeout = (
        max(0.2, float(OSRM_CONNECT_TIMEOUT_SECONDS)),
        max(0.3, float(OSRM_READ_TIMEOUT_SECONDS)),
    )

    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json() or {}
        routes = payload.get("routes") or []
        if not routes:
            return None

        first = routes[0] or {}
        distance_km = float(first.get("distance", 0.0)) / 1000.0
        duration_min = float(first.get("duration", 0.0)) / 60.0
        if distance_km <= 0 or duration_min <= 0:
            return None

        _record_osrm_success()
        return {
            "distance_km": round(distance_km, 2),
            "duration_min": round(duration_min, 1),
            "via": "osrm",
        }
    except Exception as exc:
        _record_osrm_failure()
        print(f"[distance] OSRM error: {exc}")
        return None


def _maptiler_distance(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> dict | None:
    api_key = (MAPTILER_API_KEY or "").strip()
    base_url = (MAPTILER_BASE_URL or "").strip().rstrip("/")
    profile = (MAPTILER_PROFILE or "driving").strip().lower()
    if not api_key or not base_url:
        return None

    url = f"{base_url}/route/v1/{profile}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
    params = {
        "overview": "false",
        "alternatives": "false",
        "steps": "false",
        "key": api_key,
    }
    timeout = (
        max(0.2, float(MAPTILER_CONNECT_TIMEOUT_SECONDS)),
        max(0.3, float(MAPTILER_READ_TIMEOUT_SECONDS)),
    )

    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json() or {}
        routes = payload.get("routes") or []
        if not routes:
            return None

        first = routes[0] or {}
        distance_km = float(first.get("distance", 0.0)) / 1000.0
        duration_min = float(first.get("duration", 0.0)) / 60.0
        if distance_km <= 0 or duration_min <= 0:
            return None

        return {
            "distance_km": round(distance_km, 2),
            "duration_min": round(duration_min, 1),
            "via": "maptiler",
        }
    except Exception as exc:
        print(f"[distance] MapTiler error: {exc}")
        return None


def get_distance(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> dict:
    """
    Return distance info:
      distance_km, duration_min, via

    Uses ROUTING_PROVIDER order:
      - "osrm"     -> OSRM, then MapTiler, then Haversine
      - "maptiler" -> MapTiler, then OSRM, then Haversine
      - "auto"     -> OSRM, then MapTiler, then Haversine
    """
    provider = (ROUTING_PROVIDER or "auto").strip().lower()
    if provider not in {"osrm", "maptiler", "auto"}:
        provider = "auto"
    cache_key = _distance_cache_key(
        provider,
        origin_lat,
        origin_lon,
        dest_lat,
        dest_lon,
    )
    cached = _cache_get(cache_key)
    if cached:
        return cached

    result = None
    if provider in {"osrm", "auto"}:
        result = _osrm_distance(origin_lat, origin_lon, dest_lat, dest_lon)
        if not result:
            result = _maptiler_distance(origin_lat, origin_lon, dest_lat, dest_lon)
    elif provider == "maptiler":
        result = _maptiler_distance(origin_lat, origin_lon, dest_lat, dest_lon)
        if not result:
            result = _osrm_distance(origin_lat, origin_lon, dest_lat, dest_lon)

    if result:
        _cache_set(cache_key, result)
        return result

    fallback = _haversine_distance(origin_lat, origin_lon, dest_lat, dest_lon)
    _cache_set(cache_key, fallback)
    return fallback


def travel_cost(distance_km: float, duration_min: float) -> dict:
    """
    Estimate travel costs (one-way).
    Returns fuel_cost, time_cost, total_cost (fuel-only).
    """
    fuel_cost = round(distance_km * FUEL_COST_PER_KM, 2)
    time_cost = round((duration_min / 60.0) * TIME_VALUE_PER_HOUR, 2)
    return {
        "fuel_cost": fuel_cost,
        "time_cost": time_cost,
        "total_cost": round(fuel_cost, 2),
    }


def full_trip_analysis(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    product_price: float = 0.0,
) -> dict:
    """
    One-stop helper:
      distance + fuel cost + product price = grand_total
    """
    dist = get_distance(origin_lat, origin_lon, dest_lat, dest_lon)
    cost = travel_cost(dist["distance_km"], dist["duration_min"])
    return {
        **dist,
        **cost,
        "product_price": product_price,
        "grand_total": round(product_price + cost["total_cost"], 2),
    }
