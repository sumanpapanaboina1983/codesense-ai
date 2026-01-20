"""
Cache repository for managing cached data.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from src.core.logging import get_logger

logger = get_logger(__name__)


class InMemoryCacheRepository:
    """
    In-memory cache repository for development/testing.
    """

    def __init__(self, default_ttl_seconds: int = 3600) -> None:
        """
        Initialize the cache.

        Args:
            default_ttl_seconds: Default TTL for cache entries
        """
        self._cache: dict[str, dict[str, Any]] = {}
        self.default_ttl = default_ttl_seconds

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        if key not in self._cache:
            return None

        entry = self._cache[key]
        if entry["expires_at"] < datetime.utcnow():
            del self._cache[key]
            return None

        return entry["value"]

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None
    ) -> None:
        """Set a value in cache."""
        ttl = ttl_seconds or self.default_ttl
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)

        self._cache[key] = {
            "value": value,
            "expires_at": expires_at,
            "created_at": datetime.utcnow(),
        }

        logger.debug("Cache set", key=key, ttl=ttl)

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        return await self.get(key) is not None

    async def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        logger.info("Cache cleared")

    async def clear_expired(self) -> int:
        """Clear expired cache entries."""
        now = datetime.utcnow()
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry["expires_at"] < now
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug("Cleared expired cache entries", count=len(expired_keys))

        return len(expired_keys)

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        now = datetime.utcnow()
        active = sum(1 for e in self._cache.values() if e["expires_at"] >= now)
        expired = len(self._cache) - active

        return {
            "total_entries": len(self._cache),
            "active_entries": active,
            "expired_entries": expired,
        }


class RedisCacheRepository:
    """
    Redis cache repository for production.
    """

    def __init__(
        self,
        redis_client: Any,
        default_ttl_seconds: int = 3600,
        key_prefix: str = "ai_accelerator:",
    ) -> None:
        """
        Initialize with a Redis client.

        Args:
            redis_client: Redis async client
            default_ttl_seconds: Default TTL for cache entries
            key_prefix: Prefix for all cache keys
        """
        self.redis = redis_client
        self.default_ttl = default_ttl_seconds
        self.key_prefix = key_prefix

    def _make_key(self, key: str) -> str:
        """Create a prefixed key."""
        return f"{self.key_prefix}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        full_key = self._make_key(key)
        value = await self.redis.get(full_key)

        if value is None:
            return None

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value.decode() if isinstance(value, bytes) else value

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None
    ) -> None:
        """Set a value in cache."""
        full_key = self._make_key(key)
        ttl = ttl_seconds or self.default_ttl

        # Serialize value
        if isinstance(value, (dict, list)):
            serialized = json.dumps(value)
        else:
            serialized = str(value)

        await self.redis.setex(full_key, ttl, serialized)
        logger.debug("Cache set", key=key, ttl=ttl)

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        full_key = self._make_key(key)
        result = await self.redis.delete(full_key)
        return result > 0

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        full_key = self._make_key(key)
        return await self.redis.exists(full_key) > 0

    async def clear(self, pattern: str = "*") -> None:
        """Clear cache entries matching a pattern."""
        full_pattern = self._make_key(pattern)
        keys = []

        async for key in self.redis.scan_iter(match=full_pattern):
            keys.append(key)

        if keys:
            await self.redis.delete(*keys)
            logger.info("Cache cleared", pattern=pattern, count=len(keys))

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        info = await self.redis.info("memory")

        return {
            "used_memory": info.get("used_memory_human", "unknown"),
            "used_memory_peak": info.get("used_memory_peak_human", "unknown"),
        }

    # Additional helper methods for common patterns

    async def get_or_set(
        self,
        key: str,
        factory: callable,
        ttl_seconds: Optional[int] = None
    ) -> Any:
        """Get value from cache or set it using factory function."""
        value = await self.get(key)
        if value is not None:
            return value

        value = await factory()
        await self.set(key, value, ttl_seconds)
        return value

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment a counter."""
        full_key = self._make_key(key)
        return await self.redis.incrby(full_key, amount)

    async def set_hash(self, key: str, mapping: dict[str, Any]) -> None:
        """Set a hash value."""
        full_key = self._make_key(key)
        serialized = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in mapping.items()}
        await self.redis.hset(full_key, mapping=serialized)

    async def get_hash(self, key: str) -> Optional[dict[str, Any]]:
        """Get a hash value."""
        full_key = self._make_key(key)
        result = await self.redis.hgetall(full_key)

        if not result:
            return None

        parsed = {}
        for k, v in result.items():
            key_str = k.decode() if isinstance(k, bytes) else k
            val_str = v.decode() if isinstance(v, bytes) else v
            try:
                parsed[key_str] = json.loads(val_str)
            except json.JSONDecodeError:
                parsed[key_str] = val_str

        return parsed
