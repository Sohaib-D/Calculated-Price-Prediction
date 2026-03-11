"""
delivery.py - Delivery distance and fee calculation endpoint (FastAPI).
POST /delivery/calculate
"""
from __future__ import annotations

import logging
import math

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from services.delivery_service import calculate_delivery_fee
from services.routing_service import get_route_distance
from utils.location_utils import calculate_haversine_distance

router = APIRouter(prefix="/delivery", tags=["delivery"])
logger = logging.getLogger(__name__)


class DeliveryRequest(BaseModel):
    user_lat: float
    user_lon: float
    store_lat: float
    store_lon: float

    @field_validator("user_lat", "store_lat")
    @classmethod
    def validate_latitude(cls, value: float) -> float:
        if not (-90 <= value <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        return value

    @field_validator("user_lon", "store_lon")
    @classmethod
    def validate_longitude(cls, value: float) -> float:
        if not (-180 <= value <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        return value


class DeliveryResponse(BaseModel):
    distance_km: float
    duration_min: float
    delivery_fee: float


@router.post("/calculate", response_model=DeliveryResponse)
async def delivery_calculate(body: DeliveryRequest) -> DeliveryResponse:
    """
    Calculate delivery distance, travel time, and fee.
    Never returns 500 due to routing failure.
    """
    try:
        route = await get_route_distance(
            body.user_lat,
            body.user_lon,
            body.store_lat,
            body.store_lon,
        )
        distance_km = float(route.get("distance_km", 0.0))
        duration_min = float(route.get("duration_min", 0.0))
        if not math.isfinite(distance_km) or distance_km < 0:
            raise ValueError("Invalid distance from routing service")
        if not math.isfinite(duration_min) or duration_min < 0:
            raise ValueError("Invalid duration from routing service")
    except Exception as exc:
        logger.warning("Routing failed, using Haversine fallback: %s", exc)
        # Last-resort safety net if routing service ever raises unexpectedly.
        route = calculate_haversine_distance(
            body.user_lat,
            body.user_lon,
            body.store_lat,
            body.store_lon,
        )
        distance_km = float(route.get("distance_km", 0.0))
        duration_min = float(route.get("duration_min", 0.0))

    try:
        fee = calculate_delivery_fee(distance_km)
    except Exception as exc:
        logger.warning("Delivery fee calculation failed, using base fallback: %s", exc)
        fee = calculate_delivery_fee(0.0)

    return DeliveryResponse(
        distance_km=round(max(0.0, distance_km), 2),
        duration_min=round(max(0.0, duration_min), 2),
        delivery_fee=fee,
    )
