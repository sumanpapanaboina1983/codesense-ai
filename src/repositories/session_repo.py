"""
Session repository for managing session data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from src.core.constants import SessionStatus
from src.core.logging import get_logger
from src.domain.session import Session
from src.repositories.base import BaseRepository

logger = get_logger(__name__)


class InMemorySessionRepository(BaseRepository[Session]):
    """
    In-memory session repository for development/testing.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def get(self, id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self._sessions.get(id)

    async def save(self, entity: Session) -> Session:
        """Save a session."""
        entity.updated_at = datetime.utcnow()
        self._sessions[entity.id] = entity
        logger.debug("Session saved", session_id=entity.id)
        return entity

    async def delete(self, id: str) -> bool:
        """Delete a session by ID."""
        if id in self._sessions:
            del self._sessions[id]
            logger.debug("Session deleted", session_id=id)
            return True
        return False

    async def list(
        self,
        filters: Optional[dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Session]:
        """List sessions with optional filters."""
        sessions = list(self._sessions.values())

        if filters:
            if "status" in filters:
                sessions = [s for s in sessions if s.status == filters["status"]]
            if "user_id" in filters:
                sessions = [s for s in sessions if s.user_id == filters["user_id"]]

        # Sort by created_at descending
        sessions.sort(key=lambda s: s.created_at, reverse=True)

        return sessions[offset : offset + limit]

    async def exists(self, id: str) -> bool:
        """Check if a session exists."""
        return id in self._sessions

    async def get_active_sessions(self, user_id: Optional[str] = None) -> list[Session]:
        """Get all active sessions."""
        sessions = [
            s for s in self._sessions.values()
            if s.status == SessionStatus.ACTIVE
        ]

        if user_id:
            sessions = [s for s in sessions if s.user_id == user_id]

        return sessions

    async def cleanup_expired(self, max_age_hours: int = 24) -> int:
        """Clean up expired sessions."""
        now = datetime.utcnow()
        expired_ids = []

        for session_id, session in self._sessions.items():
            age = (now - session.updated_at).total_seconds() / 3600
            if age > max_age_hours:
                expired_ids.append(session_id)

        for session_id in expired_ids:
            del self._sessions[session_id]

        if expired_ids:
            logger.info("Cleaned up expired sessions", count=len(expired_ids))

        return len(expired_ids)


class PostgresSessionRepository(BaseRepository[Session]):
    """
    PostgreSQL session repository for production.
    """

    def __init__(self, connection_pool: Any) -> None:
        """
        Initialize with a database connection pool.

        Args:
            connection_pool: AsyncPG connection pool
        """
        self.pool = connection_pool

    async def get(self, id: str) -> Optional[Session]:
        """Get a session by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, status, context, metadata, created_at, updated_at
                FROM sessions
                WHERE id = $1
                """,
                id,
            )

            if row:
                return Session(
                    id=row["id"],
                    user_id=row["user_id"],
                    status=SessionStatus(row["status"]),
                    context=row["context"] or {},
                    metadata=row["metadata"] or {},
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

            return None

    async def save(self, entity: Session) -> Session:
        """Save a session."""
        entity.updated_at = datetime.utcnow()

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (id, user_id, status, context, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    context = EXCLUDED.context,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                """,
                entity.id,
                entity.user_id,
                entity.status.value,
                entity.context,
                entity.metadata,
                entity.created_at,
                entity.updated_at,
            )

        return entity

    async def delete(self, id: str) -> bool:
        """Delete a session by ID."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM sessions WHERE id = $1",
                id,
            )
            return result == "DELETE 1"

    async def list(
        self,
        filters: Optional[dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Session]:
        """List sessions with optional filters."""
        query = "SELECT * FROM sessions WHERE 1=1"
        params: list[Any] = []

        if filters:
            if "status" in filters:
                query += f" AND status = ${len(params) + 1}"
                params.append(filters["status"].value if isinstance(filters["status"], SessionStatus) else filters["status"])
            if "user_id" in filters:
                query += f" AND user_id = ${len(params) + 1}"
                params.append(filters["user_id"])

        query += f" ORDER BY created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        params.extend([limit, offset])

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

            return [
                Session(
                    id=row["id"],
                    user_id=row["user_id"],
                    status=SessionStatus(row["status"]),
                    context=row["context"] or {},
                    metadata=row["metadata"] or {},
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    async def exists(self, id: str) -> bool:
        """Check if a session exists."""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM sessions WHERE id = $1)",
                id,
            )
            return result
