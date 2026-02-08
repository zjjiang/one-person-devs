"""Tests for API health check endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    """Test health check endpoint returns correct status."""
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["service"] == "OPD API"


def test_root_endpoint(client: TestClient) -> None:
    """Test root API endpoint returns basic information."""
    response = client.get("/api/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "OPD - One Person Devs API"
    assert data["version"] == "0.1.0"
    assert "description" in data


@pytest.mark.asyncio
async def test_health_check_async(async_client) -> None:
    """Test health check endpoint with async client."""
    response = await async_client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
