"""
Base MCP (Model Context Protocol) client implementation.
Provides common functionality for all MCP clients.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.exceptions import MCPError
from src.core.logging import get_logger

logger = get_logger(__name__)


class BaseMCPClient(ABC):
    """
    Abstract base class for MCP clients.
    Provides common HTTP client functionality and error handling.
    """

    def __init__(
        self,
        server_url: str,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        """
        Initialize the MCP client.

        Args:
            server_url: Base URL of the MCP server
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.server_url,
                timeout=httpx.Timeout(self.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Make an HTTP request to the MCP server.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request body data
            params: Query parameters

        Returns:
            Response data as dictionary

        Raises:
            MCPError: If the request fails
        """
        client = await self._get_client()

        try:
            response = await client.request(
                method=method,
                url=endpoint,
                json=data,
                params=params,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(
                "MCP request failed",
                endpoint=endpoint,
                status_code=e.response.status_code,
                response_text=e.response.text,
            )
            raise MCPError(
                mcp_type=self.mcp_type,
                message=f"HTTP {e.response.status_code}: {e.response.text}",
                details={"endpoint": endpoint, "status_code": e.response.status_code},
            ) from e

        except httpx.RequestError as e:
            logger.error(
                "MCP request error",
                endpoint=endpoint,
                error=str(e),
            )
            raise MCPError(
                mcp_type=self.mcp_type,
                message=f"Request failed: {str(e)}",
                details={"endpoint": endpoint},
            ) from e

    async def _get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Make a GET request."""
        return await self._request("GET", endpoint, params=params)

    async def _post(
        self,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Make a POST request."""
        return await self._request("POST", endpoint, data=data)

    @property
    @abstractmethod
    def mcp_type(self) -> str:
        """Return the MCP type identifier."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the MCP server is healthy.

        Returns:
            True if healthy, False otherwise
        """
        ...

    async def __aenter__(self) -> "BaseMCPClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
