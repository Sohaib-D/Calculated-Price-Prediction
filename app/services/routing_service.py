"""
Async OSRM routing service for FastAPI delivery workflows.

Public OSRM endpoint format:
/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx
from app.utils.location_utils import calculate_haversine_distance
from config import (
    MAPTILER_API_KEY,
    MAPTILER_BASE_URL,
    MAPTILER_CONNECT_TIMEOUT_SECONDS,
    MAPTILER_PROFILE,
    MAPTILER_READ_TIMEOUT_SECONDS,
    OSRM_BASE_URL as CONFIG_OSRM_BASE_URL,
)

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None
_active_base_url: str | None = None
_client_lock = asyncio.Lock()
_limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
_max_timeout_seconds = min(5.0, max(0.1, float(os.getenv("OSRM_TIMEOUT_SECONDS", "5.0"))))
_soft_budget_seconds = min(5.0, max(0.1, float(os.getenv("OSRM_SOFT_BUDGET_SECONDS", "0.5"))))
_maptiler_client: httpx.AsyncClient | None = None
_maptiler_lock = asyncio.Lock()
_active_maptiler_base_url: str | None = None


def _resolve_osrm_base_url() -> str:
    """
    Resolve OSRM base URL from env with config fallback.
    This keeps URL selection in the project config/settings flow.
    """
    env_url = os.getenv("OSRM_BASE_URL")
    if env_url and env_url.strip():
        return env_url.strip().rstrip("/")
    return CONFIG_OSRM_BASE_URL.rstrip("/")


async def _get_client() -> httpx.AsyncClient:
    """Return a shared AsyncClient instance."""
    global _client, _active_base_url
    base_url = _resolve_osrm_base_url()
    if _client and not _client.is_closed and _active_base_url == base_url:
        return _client

    async with _client_lock:
        base_url = _resolve_osrm_base_url()
        if _client and not _client.is_closed and _active_base_url == base_url:
            return _client
        if _client and not _client.is_closed:
            await _client.aclose()
        _client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout=_max_timeout_seconds),
            limits=_limits,
        )
        _active_base_url = base_url
        return _client


async def _get_maptiler_client() -> httpx.AsyncClient | None:
    """Return a shared AsyncClient for MapTiler calls."""
    if not (MAPTILER_API_KEY and MAPTILER_BASE_URL):
        return None

    global _maptiler_client, _active_maptiler_base_url
    base_url = MAPTILER_BASE_URL.strip().rstrip("/")
    if _maptiler_client and not _maptiler_client.is_closed and _active_maptiler_base_url == base_url:
        return _maptiler_client

    async with _maptiler_lock:
        base_url = MAPTILER_BASE_URL.strip().rstrip("/")
        if _maptiler_client and not _maptiler_client.is_closed and _active_maptiler_base_url == base_url:
            return _maptiler_client
        if _maptiler_client and not _maptiler_client.is_closed:
            await _maptiler_client.aclose()
        _maptiler_client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(
                connect=MAPTILER_CONNECT_TIMEOUT_SECONDS,
                read=MAPTILER_READ_TIMEOUT_SECONDS,
                write=MAPTILER_READ_TIMEOUT_SECONDS,
                pool=MAPTILER_CONNECT_TIMEOUT_SECONDS,
            ),
            limits=_limits,
        )
        _active_maptiler_base_url = base_url
        return _maptiler_client


async def close_client() -> None:
    """Close the shared AsyncClient, useful on app shutdown."""
    global _client, _active_base_url, _maptiler_client, _active_maptiler_base_url
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None
    _active_base_url = None
    if _maptiler_client and not _maptiler_client.is_closed:
        await _maptiler_client.aclose()
    _maptiler_client = None
    _active_maptiler_base_url = None


def _safe_value(route: dict[str, Any], key: str) -> float:
    try:
        return float(route.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _remaining_soft_budget(started_at: float) -> float:
    elapsed = time.perf_counter() - started_at
    return _soft_budget_seconds - elapsed


async def get_route_distance(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> dict:
    """
    Calculate road distance and travel time using OSRM.

    Returns:
    {
        "distance_km": float,
        "duration_min": float
    }
    """
    path = f"/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}"
    params = {"overview": "false"}
    last_error: Exception | None = None
    started_at = time.perf_counter()

    for attempt in range(2):
        try:
            remaining_budget = _remaining_soft_budget(started_at)
            if remaining_budget <= 0 and attempt > 0:
                break

            client = await _get_client()
            # Prefer sub-500ms response when possible; never exceed 5s.
            per_request_timeout = min(
                _max_timeout_seconds,
                remaining_budget if remaining_budget > 0 else _max_timeout_seconds,
            )
            response = await client.get(path, params=params, timeout=per_request_timeout)
            response.raise_for_status()

            payload = response.json()
            routes = payload.get("routes") or []
            if not routes:
                raise ValueError("OSRM response does not contain routes")

            route = routes[0]
            distance_m = _safe_value(route, "distance")
            duration_s = _safe_value(route, "duration")
            if distance_m <= 0 or duration_s <= 0:
                raise ValueError("OSRM route distance/duration is invalid")

            return {
                "distance_km": round(distance_m / 1000.0, 2),
                "duration_min": round(duration_s / 60.0, 2),
            }
        except (httpx.TimeoutException, httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            last_error = exc
            logger.warning(
                "OSRM attempt %d failed (%s): %s",
                attempt + 1,
                type(exc).__name__,
                exc,
            )

    if MAPTILER_API_KEY and MAPTILER_BASE_URL:
        try:
            remaining_budget = _remaining_soft_budget(started_at)
            if remaining_budget > 0:
                client = await _get_maptiler_client()
                if client:
                    profile = (MAPTILER_PROFILE or "driving").strip().lower()
                    maptiler_path = f"/route/v1/{profile}/{start_lon},{start_lat};{end_lon},{end_lat}"
                    maptiler_params = {"overview": "false", "alternatives": "false", "steps": "false", "key": MAPTILER_API_KEY}
                    maptiler_timeout = min(
                        _max_timeout_seconds,
                        remaining_budget if remaining_budget > 0 else _max_timeout_seconds,
                    )
                    response = await client.get(maptiler_path, params=maptiler_params, timeout=maptiler_timeout)
                    response.raise_for_status()

                    payload = response.json()
                    routes = payload.get("routes") or []
                    if not routes:
                        raise ValueError("MapTiler response does not contain routes")

                    route = routes[0]
                    distance_m = _safe_value(route, "distance")
                    duration_s = _safe_value(route, "duration")
                    if distance_m <= 0 or duration_s <= 0:
                        raise ValueError("MapTiler route distance/duration is invalid")

                    return {
                        "distance_km": round(distance_m / 1000.0, 2),
                        "duration_min": round(duration_s / 60.0, 2),
                    }
        except (httpx.TimeoutException, httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            logger.warning("MapTiler routing failed (%s): %s", type(exc).__name__, exc)

    logger.error("OSRM unavailable after retry: %s", last_error)
    try:
        distance_km = calculate_haversine_distance(
            start_lat,
            start_lon,
            end_lat,
            end_lon,
        )
        duration_min = (distance_km / 30.0) * 60.0
        return {
            "distance_km": round(distance_km, 2),
            "duration_min": round(duration_min, 2),
        }
    except Exception as fallback_exc:
        logger.exception("Haversine fallback failed: %s", fallback_exc)
        return {
            "distance_km": 0.0,
            "duration_min": 0.0,
        }
