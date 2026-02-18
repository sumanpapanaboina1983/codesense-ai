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

    async def query_code_structure(
        self,
        cypher_query: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Execute Cypher query against code graph.

        This is a public method that can be called directly without going
        through the MCP tool interface.

        Args:
            cypher_query: The Cypher query to execute
            parameters: Optional query parameters

        Returns:
            Dict with 'nodes' key containing query results
        """
        return await self._query_code_structure(cypher_query, parameters)

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
            # New agentic tools for iterative retrieval
            "get_callers_of": self._get_callers_of,
            "get_related_components": self._get_related_components,
            "search_by_relevance": self._search_by_relevance,
            "expand_from_seeds": self._expand_from_seeds,
        }

        handler = tool_handlers.get(tool_name)
        if not handler:
            raise MCPToolError(f"Unknown tool: {tool_name}")

        result = await handler(**parameters)
        logger.info(f"[MCP-TOOL] Result: {str(result)[:500]}...")
        return result

    async def _query_code_structure(
        self,
        cypher_query: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute Cypher query against code graph."""
        if not self._driver:
            raise MCPToolError("Neo4j not connected")

        # Log the Cypher query
        logger.info(f"[NEO4J-QUERY] Executing Cypher query:")
        logger.info(f"[NEO4J-QUERY] {cypher_query}")
        if parameters:
            logger.info(f"[NEO4J-QUERY] Parameters: {parameters}")

        try:
            async with self._driver.session(database=self.neo4j_database) as session:
                result = await session.run(cypher_query, parameters or {})
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
    # Note: query_code_structure is defined above with parameter support

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

    # ==========================================================================
    # New Agentic Tools for Iterative Retrieval
    # ==========================================================================

    async def _get_callers_of(
        self,
        component_name: str,
        max_depth: int = 2,
    ) -> dict[str, Any]:
        """
        Get all components that call/use the specified component.

        This enables agents to understand "who uses this component"
        for impact analysis and dependency understanding.

        Args:
            component_name: Name of the component to find callers for
            max_depth: Maximum depth of call chain to traverse (default 2)

        Returns:
            Dict with callers list and call chain paths
        """
        if not self._driver:
            raise MCPToolError("Neo4j not connected")

        async with self._driver.session(database=self.neo4j_database) as session:
            # Find direct and indirect callers with relevance scores
            query = """
                MATCH (caller)-[r:CALLS|IMPORTS|USES_COMPONENT|DEPENDS_ON*1..$maxDepth]->(target)
                WHERE target.name = $name
                WITH caller, min(length(r)) AS depth, COALESCE(caller.pageRank, 0.1) AS pageRank
                RETURN caller.name AS name,
                       labels(caller)[0] AS type,
                       caller.filePath AS path,
                       depth,
                       pageRank
                ORDER BY depth ASC, pageRank DESC
                LIMIT 30
            """
            result = await session.run(query, name=component_name, maxDepth=max_depth)
            records = await result.data()

        callers = [
            {
                "name": r.get("name"),
                "type": r.get("type"),
                "path": r.get("path"),
                "depth": r.get("depth"),
                "importance": r.get("pageRank"),
            }
            for r in records if r.get("name")
        ]

        logger.info(f"[MCP-TOOL] get_callers_of({component_name}): Found {len(callers)} callers")
        return {"component": component_name, "callers": callers}

    async def _get_related_components(
        self,
        component_name: str,
        relationship_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Get components related to the specified component via any relationship.

        This enables agents to explore the neighborhood of a component
        to understand its context and connections.

        Args:
            component_name: Name of the component
            relationship_types: Optional list of relationship types to filter

        Returns:
            Dict with related components grouped by relationship type
        """
        if not self._driver:
            raise MCPToolError("Neo4j not connected")

        rel_filter = ""
        if relationship_types:
            rel_types = "|".join(relationship_types)
            rel_filter = f":{rel_types}"

        async with self._driver.session(database=self.neo4j_database) as session:
            query = f"""
                MATCH (source)-[r{rel_filter}]-(related)
                WHERE source.name = $name
                WITH type(r) AS relType,
                     CASE WHEN startNode(r) = source THEN 'outgoing' ELSE 'incoming' END AS direction,
                     related,
                     COALESCE(related.pageRank, 0.1) AS pageRank
                RETURN relType,
                       direction,
                       related.name AS name,
                       labels(related)[0] AS type,
                       related.filePath AS path,
                       pageRank
                ORDER BY pageRank DESC
            """
            result = await session.run(query, name=component_name)
            records = await result.data()

        # Group by relationship type and direction
        grouped: dict[str, list[dict]] = {}
        for r in records:
            key = f"{r.get('direction')}_{r.get('relType')}"
            if key not in grouped:
                grouped[key] = []
            grouped[key].append({
                "name": r.get("name"),
                "type": r.get("type"),
                "path": r.get("path"),
                "importance": r.get("pageRank"),
            })

        logger.info(f"[MCP-TOOL] get_related_components({component_name}): Found {len(records)} related")
        return {"component": component_name, "relationships": grouped}

    async def _search_by_relevance(
        self,
        search_terms: str,
        min_score: float = 0.3,
        include_pagerank: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Search components using full-text search with relevance scoring.

        Returns components ranked by combined relevance (fulltext + pagerank).
        No hardcoded limit - returns all components above score threshold.

        Args:
            search_terms: Space-separated search terms (Lucene syntax supported)
            min_score: Minimum relevance score (0-1) to include
            include_pagerank: Whether to boost results by PageRank

        Returns:
            List of components with relevance scores
        """
        if not self._driver:
            raise MCPToolError("Neo4j not connected")

        async with self._driver.session(database=self.neo4j_database) as session:
            try:
                if include_pagerank:
                    query = """
                        CALL db.index.fulltext.queryNodes('component_fulltext_search', $terms)
                        YIELD node, score
                        WHERE score >= $minScore
                        WITH node, score AS fulltextScore, COALESCE(node.pageRank, 0.1) AS pageRank
                        WITH node, fulltextScore, pageRank,
                             (fulltextScore * 0.7 + pageRank * 0.3) AS combinedScore
                        RETURN node.name AS name,
                               labels(node)[0] AS type,
                               node.filePath AS path,
                               node.description AS description,
                               fulltextScore,
                               pageRank,
                               combinedScore
                        ORDER BY combinedScore DESC
                    """
                else:
                    query = """
                        CALL db.index.fulltext.queryNodes('component_fulltext_search', $terms)
                        YIELD node, score
                        WHERE score >= $minScore
                        RETURN node.name AS name,
                               labels(node)[0] AS type,
                               node.filePath AS path,
                               node.description AS description,
                               score AS combinedScore
                        ORDER BY combinedScore DESC
                    """

                result = await session.run(query, terms=search_terms, minScore=min_score)
                records = await result.data()

                logger.info(f"[MCP-TOOL] search_by_relevance('{search_terms}'): Found {len(records)} results")
                return records

            except Exception as e:
                # Fallback if fulltext index not available
                logger.warning(f"[MCP-TOOL] Fulltext search failed, using fallback: {e}")
                keywords = search_terms.lower().split()
                keyword_filter = " OR ".join([f"toLower(n.name) CONTAINS '{kw}'" for kw in keywords])

                fallback_query = f"""
                    MATCH (n)
                    WHERE (n:Class OR n:Function OR n:JavaClass OR n:SpringService)
                      AND ({keyword_filter})
                    WITH n, COALESCE(n.pageRank, 0.1) AS pageRank
                    RETURN n.name AS name,
                           labels(n)[0] AS type,
                           n.filePath AS path,
                           pageRank AS combinedScore
                    ORDER BY combinedScore DESC
                    LIMIT 50
                """
                result = await session.run(fallback_query)
                records = await result.data()
                return records

    async def _expand_from_seeds(
        self,
        seed_components: list[str],
        max_hops: int = 2,
        min_pagerank: float = 0.1,
    ) -> dict[str, Any]:
        """
        Expand context from seed components using graph traversal.

        This implements Personalized PageRank-like expansion:
        - Start from seed components
        - Traverse relationships up to max_hops
        - Include only components above pagerank threshold

        This replaces hardcoded hop limits with importance-based expansion.

        Args:
            seed_components: List of component names to expand from
            max_hops: Maximum relationship hops (default 2)
            min_pagerank: Minimum PageRank to include in expansion

        Returns:
            Dict with expanded context including components and paths
        """
        if not self._driver:
            raise MCPToolError("Neo4j not connected")

        if not seed_components:
            return {"seeds": [], "expanded": [], "paths": []}

        async with self._driver.session(database=self.neo4j_database) as session:
            # Build seed filter
            seed_filter = " OR ".join([f"seed.name = '{name}'" for name in seed_components])

            query = f"""
                MATCH (seed)
                WHERE {seed_filter}
                CALL {{
                    WITH seed
                    MATCH path = (seed)-[*1..{max_hops}]-(connected)
                    WHERE COALESCE(connected.pageRank, 0.1) >= $minPagerank
                      AND connected <> seed
                    WITH connected, length(path) AS distance, path
                    RETURN connected, distance, path
                    ORDER BY connected.pageRank DESC
                    LIMIT 20
                }}
                WITH seed, connected, distance,
                     [node IN nodes(path) | node.name] AS pathNodes
                RETURN seed.name AS seedName,
                       connected.name AS name,
                       labels(connected)[0] AS type,
                       connected.filePath AS path,
                       connected.pageRank AS pageRank,
                       distance,
                       pathNodes
                ORDER BY pageRank DESC
            """

            result = await session.run(query, minPagerank=min_pagerank)
            records = await result.data()

        # Deduplicate and organize results
        expanded = {}
        paths = []
        for r in records:
            name = r.get("name")
            if name and name not in expanded:
                expanded[name] = {
                    "name": name,
                    "type": r.get("type"),
                    "path": r.get("path"),
                    "pageRank": r.get("pageRank"),
                    "distance": r.get("distance"),
                    "reachedFrom": r.get("seedName"),
                }
            if r.get("pathNodes"):
                paths.append({
                    "from": r.get("seedName"),
                    "to": name,
                    "path": r.get("pathNodes"),
                })

        logger.info(f"[MCP-TOOL] expand_from_seeds({seed_components}): Expanded to {len(expanded)} components")
        return {
            "seeds": seed_components,
            "expanded": list(expanded.values()),
            "paths": paths[:20],  # Limit paths to avoid noise
        }

    # Convenience methods for new tools
    async def get_callers_of(self, component_name: str, max_depth: int = 2) -> dict[str, Any]:
        """Get components that call/use the specified component."""
        return await self.call_tool("get_callers_of", {
            "component_name": component_name,
            "max_depth": max_depth,
        })

    async def get_related_components(
        self,
        component_name: str,
        relationship_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Get components related to the specified component."""
        return await self.call_tool("get_related_components", {
            "component_name": component_name,
            "relationship_types": relationship_types,
        })

    async def search_by_relevance(
        self,
        search_terms: str,
        min_score: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Search components using relevance scoring."""
        return await self.call_tool("search_by_relevance", {
            "search_terms": search_terms,
            "min_score": min_score,
        })

    async def expand_from_seeds(
        self,
        seed_components: list[str],
        max_hops: int = 2,
    ) -> dict[str, Any]:
        """Expand context from seed components using graph traversal."""
        return await self.call_tool("expand_from_seeds", {
            "seed_components": seed_components,
            "max_hops": max_hops,
        })
