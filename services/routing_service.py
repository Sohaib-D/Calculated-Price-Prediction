"""
routing_service.py - OSRM-based road distance and duration calculator.
Primary: public OSRM API (no API key required).
Secondary: MapTiler routing API (key-based, optional).
Fallback: Haversine estimate via utils.location_utils.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from config import (
    MAPTILER_API_KEY,
    MAPTILER_BASE_URL,
    MAPTILER_CONNECT_TIMEOUT_SECONDS,
    MAPTILER_PROFILE,
    MAPTILER_READ_TIMEOUT_SECONDS,
    OSRM_BASE_URL,
)
from utils.location_utils import calculate_haversine_distance

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()
_request_timeout = httpx.Timeout(connect=1.0, read=1.5, write=1.0, pool=1.0)
_limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
_maptiler_client: httpx.AsyncClient | None = None
_maptiler_lock = asyncio.Lock()


async def _get_http_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for OSRM calls."""
    global _client
    if _client and not _client.is_closed:
        return _client

    async with _client_lock:
        if _client and not _client.is_closed:
            return _client
        _client = httpx.AsyncClient(
            base_url=OSRM_BASE_URL.rstrip("/"),
            timeout=_request_timeout,
            limits=_limits,
        )
        return _client


async def _get_maptiler_client() -> httpx.AsyncClient | None:
    """Return a shared async HTTP client for MapTiler calls."""
    if not (MAPTILER_API_KEY and MAPTILER_BASE_URL):
        return None

    global _maptiler_client
    if _maptiler_client and not _maptiler_client.is_closed:
        return _maptiler_client

    async with _maptiler_lock:
        if _maptiler_client and not _maptiler_client.is_closed:
            return _maptiler_client
        _maptiler_client = httpx.AsyncClient(
            base_url=MAPTILER_BASE_URL.rstrip("/"),
            timeout=httpx.Timeout(
                connect=MAPTILER_CONNECT_TIMEOUT_SECONDS,
                read=MAPTILER_READ_TIMEOUT_SECONDS,
                write=MAPTILER_READ_TIMEOUT_SECONDS,
                pool=MAPTILER_CONNECT_TIMEOUT_SECONDS,
            ),
            limits=_limits,
        )
        return _maptiler_client


async def close_routing_client() -> None:
    """Close the shared HTTP client during app shutdown."""
    global _client, _maptiler_client
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None
    if _maptiler_client and not _maptiler_client.is_closed:
        await _maptiler_client.aclose()
    _maptiler_client = None


def _fallback_distance(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> dict:
    fallback = calculate_haversine_distance(start_lat, start_lon, end_lat, end_lon)
    return {
        "distance_km": fallback["distance_km"],
        "duration_min": fallback["duration_min"],
    }


async def get_route_distance(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> dict:
    """
    Query OSRM for road distance and duration.

    Coordinate order for OSRM is longitude,latitude.
    Retries once on failure and always falls back to Haversine.
    """
    path = f"/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}"
    params = {"overview": "false"}
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            client = await _get_http_client()
            response = await client.get(path, params=params)
            response.raise_for_status()
            payload = response.json()
            routes = payload.get("routes") or []
            if not routes:
                raise ValueError("OSRM response missing routes")

            route = routes[0]
            distance_m = float(route.get("distance", 0.0))
            duration_s = float(route.get("duration", 0.0))
            if distance_m <= 0 or duration_s <= 0:
                raise ValueError("OSRM route distance/duration missing")

            return {
                "distance_km": round(distance_m / 1000, 2),
                "duration_min": round(duration_s / 60, 2),
            }
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            last_error = exc
            if attempt == 0:
                logger.warning("OSRM attempt 1 failed: %s. Retrying once.", exc)

    if MAPTILER_API_KEY and MAPTILER_BASE_URL:
        try:
            client = await _get_maptiler_client()
            if client:
                maptiler_path = f"/route/v1/{(MAPTILER_PROFILE or 'driving').strip().lower()}/{start_lon},{start_lat};{end_lon},{end_lat}"
                maptiler_params = {"overview": "false", "alternatives": "false", "steps": "false", "key": MAPTILER_API_KEY}
                response = await client.get(maptiler_path, params=maptiler_params)
                response.raise_for_status()
                payload = response.json()
                routes = payload.get("routes") or []
                if not routes:
                    raise ValueError("MapTiler response missing routes")

                route = routes[0]
                distance_m = float(route.get("distance", 0.0))
                duration_s = float(route.get("duration", 0.0))
                if distance_m <= 0 or duration_s <= 0:
                    raise ValueError("MapTiler route distance/duration missing")

                return {
                    "distance_km": round(distance_m / 1000, 2),
                    "duration_min": round(duration_s / 60, 2),
                }
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            logger.warning("MapTiler routing failed: %s", exc)

    logger.warning("OSRM unavailable (%s). Using Haversine fallback.", last_error)
    return _fallback_distance(start_lat, start_lon, end_lat, end_lon)
