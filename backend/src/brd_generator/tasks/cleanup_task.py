"""Cleanup task for expired audit history.

This task can be scheduled via cron or run on app startup to
clean up audit history records past their retention period.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from ..services.audit_service import AuditService
from ..utils.logger import get_logger

logger = get_logger(__name__)


async def run_audit_cleanup() -> int:
    """Background task to clean up expired audit history.

    Can be scheduled via cron or run on app startup.

    Returns:
        Number of records deleted
    """
    logger.info(f"Starting audit cleanup task at {datetime.utcnow().isoformat()}")

    try:
        audit_service = AuditService()
        deleted_count = await audit_service.cleanup_expired_history()

        if deleted_count > 0:
            logger.info(f"Audit cleanup completed: {deleted_count} expired records deleted")
        else:
            logger.info("Audit cleanup completed: no expired records to delete")

        return deleted_count

    except Exception as e:
        logger.error(f"Audit cleanup failed: {e}")
        raise


async def schedule_periodic_cleanup(interval_hours: int = 24) -> None:
    """Schedule periodic cleanup at specified interval.

    Args:
        interval_hours: Hours between cleanup runs (default: 24)
    """
    while True:
        try:
            await run_audit_cleanup()
        except Exception as e:
            logger.error(f"Periodic cleanup failed: {e}")

        # Wait for next run
        await asyncio.sleep(interval_hours * 3600)


def start_cleanup_background_task(interval_hours: int = 24) -> asyncio.Task:
    """Start the cleanup task as a background coroutine.

    Args:
        interval_hours: Hours between cleanup runs

    Returns:
        The asyncio Task object
    """
    return asyncio.create_task(schedule_periodic_cleanup(interval_hours))
