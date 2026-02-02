"""Neo4j MCP client for code graph queries."""

from __future__ import annotations

import os
from typing import Any, Optional

from neo4j import AsyncGraphDatabase

from .base import MCPClient, MCPToolError
from ..utils.logger import get_logger

logger = get_logger(__name__)


class Neo4jMCPClient(MCPClient):
    """
    Client for Neo4j code graph queries.

    Uses direct bolt connection for reliable access to Neo4j.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize Neo4j client.

        Args:
            server_url: Neo4j bolt URI (defaults to env NEO4J_URI)
            timeout: Request timeout in seconds
        """
        self.neo4j_uri = server_url or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
        self.neo4j_database = os.getenv("NEO4J_DATABASE", "neo4j")

        super().__init__(
            server_name="neo4j-code-graph",
            server_url=self.neo4j_uri,
            timeout=timeout,
        )

        self._driver = None

    async def connect(self) -> None:
        """Initialize bolt connection."""
        logger.info(f"Neo4j client connecting to: {self.neo4j_uri}")
        logger.info(f"Database: {self.neo4j_database}")

        try:
            self._driver = AsyncGraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password),
            )
            # Verify connection
            async with self._driver.session(database=self.neo4j_database) as session:
                result = await session.run("RETURN 1 as test")
                await result.single()
            logger.info("Neo4j connection verified")
            self._connected = True
        except Exception as e:
            logger.warning(f"Neo4j connection failed: {e}")
            self._connected = False

    async def disconnect(self) -> None:
        """Close connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
        self._connected = False
        logger.info("Neo4j client disconnected")

    async def health_check(self) -> bool:
        """Check if Neo4j is healthy."""
        try:
            if not self._driver:
                return False
            async with self._driver.session(database=self.neo4j_database) as session:
                result = await session.run("RETURN 1 as test")
                await result.single()
            return True
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

        # Log MCP tool invocation
        logger.info(f"[MCP-TOOL] Neo4j tool invoked: {tool_name}")
        logger.info(f"[MCP-TOOL] Parameters: {parameters}")

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

        result = await handler(**parameters)
        logger.info(f"[MCP-TOOL] Result: {str(result)[:500]}...")
        return result

    async def _query_code_structure(self, cypher_query: str) -> dict[str, Any]:
        """Execute Cypher query against code graph."""
        if not self._driver:
            raise MCPToolError("Neo4j not connected")

        # Log the Cypher query
        logger.info(f"[NEO4J-QUERY] Executing Cypher query:")
        logger.info(f"[NEO4J-QUERY] {cypher_query}")

        try:
            async with self._driver.session(database=self.neo4j_database) as session:
                result = await session.run(cypher_query)
                records = await result.data()
                logger.info(f"[NEO4J-QUERY] Query returned {len(records)} records")
                if records:
                    logger.info(f"[NEO4J-QUERY] Sample result: {str(records[0])[:200]}...")
                return {"nodes": records}
        except Exception as e:
            logger.error(f"[NEO4J-QUERY] Cypher query failed: {e}")
            raise MCPToolError(f"Query failed: {e}")

    async def _get_component_dependencies(
        self,
        component_name: str,
    ) -> dict[str, list[str]]:
        """Get upstream and downstream dependencies for a component."""
        if not self._driver:
            raise MCPToolError("Neo4j not connected")

        async with self._driver.session(database=self.neo4j_database) as session:
            # Query for upstream dependencies
            upstream_query = """
                MATCH (comp)-[:DEPENDS_ON|:IMPORTS|:CALLS]->(dep)
                WHERE comp.name = $name
                RETURN dep.name as dependency
            """
            upstream_result = await session.run(upstream_query, name=component_name)
            upstream_records = await upstream_result.data()

            # Query for downstream (dependents)
            downstream_query = """
                MATCH (dep)-[:DEPENDS_ON|:IMPORTS|:CALLS]->(comp)
                WHERE comp.name = $name
                RETURN dep.name as dependent
            """
            downstream_result = await session.run(downstream_query, name=component_name)
            downstream_records = await downstream_result.data()

        return {
            "upstream": [n.get("dependency") for n in upstream_records if n.get("dependency")],
            "downstream": [n.get("dependent") for n in downstream_records if n.get("dependent")],
        }

    async def _get_api_contracts(self, service_name: str) -> list[dict[str, Any]]:
        """Get API contracts for a service."""
        if not self._driver:
            return []

        async with self._driver.session(database=self.neo4j_database) as session:
            # Try different relationship patterns for API exposure
            query = """
                MATCH (s)-[:EXPOSES|:HAS_ENDPOINT|:HAS_METHOD]->(api)
                WHERE s.name = $name
                RETURN api.endpoint as endpoint, api.method as method,
                       api.parameters as parameters
            """
            result = await session.run(query, name=service_name)
            records = await result.data()
        return records

    async def _search_similar_features(
        self,
        description: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for similar features using text matching."""
        if not self._driver:
            return []

        # Extract keywords from description
        keywords = [w.lower() for w in description.split() if len(w) > 3][:3]
        results = []

        async with self._driver.session(database=self.neo4j_database) as session:
            for keyword in keywords:
                # Search in class/service names and file paths
                query = """
                    MATCH (n)
                    WHERE (n:JavaClass OR n:SpringService OR n:SpringController)
                    AND (toLower(n.name) CONTAINS $keyword OR toLower(n.filePath) CONTAINS $keyword)
                    RETURN n.name as name, n.filePath as description
                    LIMIT $limit
                """
                result = await session.run(query, keyword=keyword, limit=limit)
                records = await result.data()
                results.extend(records)

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
