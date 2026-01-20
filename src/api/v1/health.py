"""
Health check endpoints.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Basic health check endpoint.
    Returns application status.
    """
    return {
        "status": "healthy",
        "app": settings.app_name,
        "environment": settings.app_env,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/ready")
async def readiness_check() -> dict[str, Any]:
    """
    Readiness check endpoint.
    Verifies all dependencies are available.
    """
    checks = {
        "app": True,
        # Add more checks as services are implemented
        # "database": await check_database(),
        # "redis": await check_redis(),
        # "neo4j": await check_neo4j(),
    }

    all_healthy = all(checks.values())

    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """
    Liveness check endpoint.
    Simple check that the application is running.
    """
    return {"status": "alive"}
