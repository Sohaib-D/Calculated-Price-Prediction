"""
Delivery API router.

Endpoint:
POST /delivery/calculate
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from app.services.delivery_service import calculate_delivery_fee
from app.services.routing_service import get_route_distance
from app.utils.location_utils import calculate_haversine_distance

router = APIRouter(prefix="/delivery", tags=["delivery"])


class DeliveryRequest(BaseModel):
    user_lat: float
    user_lon: float
    store_lat: float
    store_lon: float

    @field_validator("user_lat", "store_lat")
    @classmethod
    def validate_latitude(cls, value: float) -> float:
        if not (-90.0 <= value <= 90.0):
            raise ValueError("Latitude must be between -90 and 90")
        return value

    @field_validator("user_lon", "store_lon")
    @classmethod
    def validate_longitude(cls, value: float) -> float:
        if not (-180.0 <= value <= 180.0):
            raise ValueError("Longitude must be between -180 and 180")
        return value


class DeliveryResponse(BaseModel):
    distance_km: float
    duration_min: float
    delivery_fee: float


@router.post("/calculate", response_model=DeliveryResponse)
async def calculate_delivery(body: DeliveryRequest) -> DeliveryResponse:
    """
    Calculate delivery distance, estimated travel time, and fee.

    Returns HTTP 200 for processing failures; invalid input is handled by model
    validation and returns a standard FastAPI validation response.
    """
    try:
        route = await get_route_distance(
            body.user_lat,
            body.user_lon,
            body.store_lat,
            body.store_lon,
        )
        fee = calculate_delivery_fee(route["distance_km"])
        return DeliveryResponse(
            distance_km=route["distance_km"],
            duration_min=route["duration_min"],
            delivery_fee=fee,
        )
    except Exception:
        fallback_distance = calculate_haversine_distance(
            body.user_lat,
            body.user_lon,
            body.store_lat,
            body.store_lon,
        )
        duration_min = (fallback_distance / 30.0) * 60.0
        fee = calculate_delivery_fee(fallback_distance)
        return DeliveryResponse(
            distance_km=round(fallback_distance, 2),
            duration_min=round(duration_min, 2),
            delivery_fee=fee,
        )
