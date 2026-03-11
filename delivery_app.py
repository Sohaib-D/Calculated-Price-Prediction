"""
delivery_app.py - FastAPI application for delivery services.

Run:
    uvicorn delivery_app:app --reload --port 8000

Production (Render):
    uvicorn delivery_app:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ALLOWED_ORIGINS
from api.routes.delivery import router as delivery_router
from services.routing_service import close_routing_client

app = FastAPI(
    title="Delivery Distance & Fee API",
    description="Real road distance and delivery fee calculation using OSRM",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CORS_ALLOWED_ORIGINS) if CORS_ALLOWED_ORIGINS else [],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(delivery_router)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Close shared HTTP resources gracefully."""
    await close_routing_client()


@app.get("/")
async def root() -> dict:
    return {
        "service": "Delivery Distance & Fee API",
        "version": "1.0.0",
        "endpoints": {
            "POST /delivery/calculate": "Calculate delivery distance, time and fee",
            "GET /health": "Health check",
            "GET /docs": "Interactive API documentation",
        },
    }


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "service": "delivery-api"}
