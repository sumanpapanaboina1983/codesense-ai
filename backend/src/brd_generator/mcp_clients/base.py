"""Base MCP client abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx

from ..utils.logger import get_logger

logger = get_logger(__name__)


class MCPToolError(Exception):
    """Raised when MCP tool call fails."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class MCPClient(ABC):
    """Abstract base class for MCP clients."""

    def __init__(
        self,
        server_name: str,
        server_url: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize MCP client.

        Args:
            server_name: Name of the MCP server
            server_url: URL of the MCP server (for HTTP-based communication)
            timeout: Request timeout in seconds
        """
        self.server_name = server_name
        self.server_url = server_url.rstrip("/") if server_url else None
        self.timeout = timeout
        self._connected = False
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self.server_url,
                timeout=httpx.Timeout(self.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._http_client

    async def _http_get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Make HTTP GET request."""
        if not self.server_url:
            raise MCPToolError("Server URL not configured")

        client = await self._get_http_client()
        try:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise MCPToolError(
                f"HTTP {e.response.status_code}: {e.response.text}",
                {"endpoint": endpoint, "status_code": e.response.status_code},
            ) from e
        except httpx.RequestError as e:
            raise MCPToolError(f"Request failed: {str(e)}") from e

    async def _http_post(
        self,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Make HTTP POST request."""
        if not self.server_url:
            raise MCPToolError("Server URL not configured")

        client = await self._get_http_client()
        try:
            response = await client.post(endpoint, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise MCPToolError(
                f"HTTP {e.response.status_code}: {e.response.text}",
                {"endpoint": endpoint, "status_code": e.response.status_code},
            ) from e
        except httpx.RequestError as e:
            raise MCPToolError(f"Request failed: {str(e)}") from e

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to MCP server."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to MCP server."""
        pass

    @abstractmethod
    async def call_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> Any:
        """Call a tool provided by the MCP server."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if MCP server is healthy."""
        pass

    async def __aenter__(self) -> "MCPClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
