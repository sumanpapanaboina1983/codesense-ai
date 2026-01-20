"""
Unit tests for health endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient) -> None:
    """Test basic health check endpoint."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_check(async_client: AsyncClient) -> None:
    """Test readiness check endpoint."""
    response = await async_client.get("/api/v1/health/ready")
    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "checks" in data


@pytest.mark.asyncio
async def test_liveness_check(async_client: AsyncClient) -> None:
    """Test liveness check endpoint."""
    response = await async_client.get("/api/v1/health/live")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "alive"


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient) -> None:
    """Test root endpoint."""
    response = await async_client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert "name" in data
    assert "version" in data
