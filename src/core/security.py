"""
Authentication and security utilities.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.core.config import settings
from src.core.exceptions import AuthenticationError


def generate_api_key() -> str:
    """
    Generate a secure API key.

    Returns:
        A random 32-byte hex string prefixed with 'ak_'
    """
    return f"ak_{secrets.token_hex(32)}"


def generate_session_id() -> str:
    """
    Generate a unique session ID.

    Returns:
        A random 16-byte hex string prefixed with 'sess_'
    """
    return f"sess_{secrets.token_hex(16)}"


def generate_document_id() -> str:
    """
    Generate a unique document ID.

    Returns:
        A random 16-byte hex string prefixed with 'doc_'
    """
    return f"doc_{secrets.token_hex(16)}"


def generate_request_id() -> str:
    """
    Generate a unique request ID for tracing.

    Returns:
        A random 8-byte hex string prefixed with 'req_'
    """
    return f"req_{secrets.token_hex(8)}"


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for storage.

    Args:
        api_key: The API key to hash

    Returns:
        SHA-256 hash of the API key
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(provided_key: str, stored_hash: str) -> bool:
    """
    Verify an API key against its stored hash.

    Args:
        provided_key: The API key provided by the client
        stored_hash: The stored hash of the valid API key

    Returns:
        True if the key is valid, False otherwise
    """
    provided_hash = hash_api_key(provided_key)
    return hmac.compare_digest(provided_hash, stored_hash)


def create_signature(payload: str, timestamp: Optional[int] = None) -> tuple[str, int]:
    """
    Create an HMAC signature for a payload.

    Args:
        payload: The payload to sign
        timestamp: Optional timestamp (defaults to current time)

    Returns:
        Tuple of (signature, timestamp)
    """
    if timestamp is None:
        timestamp = int(datetime.now(timezone.utc).timestamp())

    message = f"{timestamp}.{payload}"
    signature = hmac.new(
        settings.security.secret_key.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    return signature, timestamp


def verify_signature(
    payload: str,
    signature: str,
    timestamp: int,
    max_age_seconds: int = 300,
) -> bool:
    """
    Verify an HMAC signature.

    Args:
        payload: The original payload
        signature: The provided signature
        timestamp: The timestamp from the signature
        max_age_seconds: Maximum age of the signature (default 5 minutes)

    Returns:
        True if signature is valid and not expired

    Raises:
        AuthenticationError: If signature is invalid or expired
    """
    # Check timestamp age
    current_time = int(datetime.now(timezone.utc).timestamp())
    if current_time - timestamp > max_age_seconds:
        raise AuthenticationError("Signature expired")

    # Verify signature
    expected_signature, _ = create_signature(payload, timestamp)
    if not hmac.compare_digest(signature, expected_signature):
        raise AuthenticationError("Invalid signature")

    return True


def sanitize_path(path: str, base_path: str) -> str:
    """
    Sanitize a file path to prevent directory traversal attacks.

    Args:
        path: The path to sanitize
        base_path: The allowed base path

    Returns:
        Sanitized absolute path

    Raises:
        AuthenticationError: If path escapes base directory
    """
    import os

    # Normalize paths
    base = os.path.normpath(os.path.abspath(base_path))
    target = os.path.normpath(os.path.abspath(os.path.join(base, path)))

    # Ensure target is within base
    if not target.startswith(base):
        raise AuthenticationError("Path traversal detected")

    return target


class RateLimiter:
    """
    Simple in-memory rate limiter.
    For production, use Redis-based rate limiting.
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[datetime]] = {}

    def is_allowed(self, identifier: str) -> bool:
        """
        Check if a request is allowed.

        Args:
            identifier: Unique identifier (e.g., API key, IP address)

        Returns:
            True if request is allowed, False if rate limited
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=self.window_seconds)

        # Clean old requests
        if identifier in self._requests:
            self._requests[identifier] = [
                t for t in self._requests[identifier] if t > window_start
            ]
        else:
            self._requests[identifier] = []

        # Check limit
        if len(self._requests[identifier]) >= self.max_requests:
            return False

        # Record request
        self._requests[identifier].append(now)
        return True

    def get_retry_after(self, identifier: str) -> int:
        """
        Get the number of seconds until the next request is allowed.

        Args:
            identifier: Unique identifier

        Returns:
            Seconds until next allowed request
        """
        if identifier not in self._requests or not self._requests[identifier]:
            return 0

        oldest = min(self._requests[identifier])
        window_end = oldest + timedelta(seconds=self.window_seconds)
        now = datetime.now(timezone.utc)

        if window_end > now:
            return int((window_end - now).total_seconds()) + 1
        return 0


# Global rate limiter instance
rate_limiter = RateLimiter()
