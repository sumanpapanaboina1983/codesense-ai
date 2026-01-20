"""
Base repository interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base class for repositories.
    """

    @abstractmethod
    async def get(self, id: str) -> Optional[T]:
        """Get an entity by ID."""
        ...

    @abstractmethod
    async def save(self, entity: T) -> T:
        """Save an entity."""
        ...

    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Delete an entity by ID."""
        ...

    @abstractmethod
    async def list(
        self,
        filters: Optional[dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[T]:
        """List entities with optional filters."""
        ...

    @abstractmethod
    async def exists(self, id: str) -> bool:
        """Check if an entity exists."""
        ...
