"""API routes for health checks and common endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Dict

from fastapi import APIRouter, status

router = APIRouter(prefix="/api", tags=["health"])


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    response_model=Dict[str, str],
    summary="Health check endpoint",
    description="Returns the health status of the API service",
)
async def health_check() -> Dict[str, str]:
    """Health check endpoint to verify the API is running.

    Returns:
        Dict containing status and timestamp
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "OPD API",
    }


@router.get(
    "/",
    status_code=status.HTTP_200_OK,
    summary="API root endpoint",
    description="Returns basic API information",
)
async def root() -> Dict[str, str]:
    """Root endpoint providing basic API information.

    Returns:
        Dict containing API name and version
    """
    return {
        "name": "OPD - One Person Devs API",
        "version": "0.1.0",
        "description": "AI-powered engineering workflow orchestration platform",
    }
