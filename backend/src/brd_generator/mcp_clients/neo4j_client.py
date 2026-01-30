"""Neo4j MCP client for code graph queries."""

from __future__ import annotations

import os
from typing import Any, Optional

from .base import MCPClient, MCPToolError
from ..utils.logger import get_logger

logger = get_logger(__name__)


class Neo4jMCPClient(MCPClient):
    """
    Client for Neo4j MCP server.

    Supports two modes:
    1. HTTP mode: Direct REST API calls to Neo4j MCP server
    2. SDK mode: Tool calls through Copilot SDK session
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize Neo4j MCP client.

        Args:
            server_url: MCP server URL (defaults to env NEO4J_MCP_URL)
            timeout: Request timeout in seconds
        """
        url = server_url or os.getenv("NEO4J_MCP_URL", "http://localhost:3006")
        super().__init__(
            server_name="neo4j-code-graph",
            server_url=url,
            timeout=timeout,
        )

    async def connect(self) -> None:
        """Initialize connection."""
        logger.info(f"Neo4j MCP client connecting to: {self.server_url}")

        # Verify connection with health check
        if self.server_url:
            try:
                healthy = await self.health_check()
                if healthy:
                    logger.info("Neo4j MCP server connection verified")
                else:
                    logger.warning("Neo4j MCP server unhealthy, continuing anyway")
            except Exception as e:
                logger.warning(f"Neo4j MCP health check failed: {e}")

        self._connected = True

    async def disconnect(self) -> None:
        """Close connection."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._connected = False
        logger.info("Neo4j MCP client disconnected")

    async def health_check(self) -> bool:
        """Check if Neo4j MCP server is healthy."""
        try:
            result = await self._http_get("/health")
            return result.get("status") == "healthy"
        except Exception as e:
            logger.warning(f"Neo4j health check failed: {e}")
            return False

    async def call_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> Any:
        """
        Call Neo4j MCP tool.

        Args:
            tool_name: Name of the tool
            parameters: Tool parameters

        Returns:
            Tool result
        """
        if not self._connected:
            raise MCPToolError("Neo4j MCP client not connected")

        # Map tool names to HTTP endpoints
        tool_handlers = {
            "query_code_structure": self._query_code_structure,
            "get_component_dependencies": self._get_component_dependencies,
            "get_api_contracts": self._get_api_contracts,
            "search_similar_features": self._search_similar_features,
        }

        handler = tool_handlers.get(tool_name)
        if not handler:
            raise MCPToolError(f"Unknown tool: {tool_name}")

        return await handler(**parameters)

    async def _query_code_structure(self, cypher_query: str) -> dict[str, Any]:
        """Execute Cypher query against code graph."""
        return await self._http_post("/query", {
            "query": cypher_query,
            "parameters": {},
        })

    async def _get_component_dependencies(
        self,
        component_name: str,
    ) -> dict[str, list[str]]:
        """Get upstream and downstream dependencies for a component."""
        # Query for upstream dependencies
        upstream_query = """
            MATCH (comp)-[:DEPENDS_ON]->(dep)
            WHERE comp.name = $name
            RETURN dep.name as dependency
        """
        upstream_result = await self._http_post("/query", {
            "query": upstream_query,
            "parameters": {"name": component_name},
        })

        # Query for downstream (dependents)
        downstream_query = """
            MATCH (dep)-[:DEPENDS_ON]->(comp)
            WHERE comp.name = $name
            RETURN dep.name as dependent
        """
        downstream_result = await self._http_post("/query", {
            "query": downstream_query,
            "parameters": {"name": component_name},
        })

        return {
            "upstream": [n.get("dependency") for n in upstream_result.get("nodes", [])],
            "downstream": [n.get("dependent") for n in downstream_result.get("nodes", [])],
        }

    async def _get_api_contracts(self, service_name: str) -> list[dict[str, Any]]:
        """Get API contracts for a service."""
        query = """
            MATCH (s:Service {name: $name})-[:EXPOSES]->(api:API)
            RETURN api.endpoint as endpoint, api.method as method,
                   api.parameters as parameters
        """
        result = await self._http_post("/query", {
            "query": query,
            "parameters": {"name": service_name},
        })
        return result.get("nodes", [])

    async def _search_similar_features(
        self,
        description: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for similar features using text matching."""
        # Simple text search - could be enhanced with vector similarity
        query = """
            MATCH (f:Feature)
            WHERE f.description CONTAINS $keyword
            RETURN f.name as name, f.description as description
            LIMIT $limit
        """
        # Extract keywords from description
        keywords = description.split()[:3]
        results = []

        for keyword in keywords:
            if len(keyword) > 3:  # Skip short words
                result = await self._http_post("/query", {
                    "query": query,
                    "parameters": {"keyword": keyword, "limit": limit},
                })
                results.extend(result.get("nodes", []))

        # Deduplicate
        seen = set()
        unique_results = []
        for r in results:
            name = r.get("name", "")
            if name and name not in seen:
                seen.add(name)
                unique_results.append(r)

        return unique_results[:limit]

    # Convenience methods that map to tool calls

    async def query_code_structure(self, cypher_query: str) -> dict[str, Any]:
        """Execute Cypher query against code graph."""
        return await self.call_tool("query_code_structure", {
            "cypher_query": cypher_query,
        })

    async def get_component_dependencies(
        self,
        component_name: str,
    ) -> dict[str, list[str]]:
        """Get dependencies for a component."""
        return await self.call_tool("get_component_dependencies", {
            "component_name": component_name,
        })

    async def get_api_contracts(self, service_name: str) -> list[dict[str, Any]]:
        """Get API contracts for a service."""
        return await self.call_tool("get_api_contracts", {
            "service_name": service_name,
        })

    async def search_similar_features(
        self,
        description: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for similar existing features."""
        return await self.call_tool("search_similar_features", {
            "description": description,
            "limit": limit,
        })
