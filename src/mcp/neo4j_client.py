"""
Neo4j MCP client for codebase graph queries.
Provides methods to query the code graph for structure and relationships.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from src.core.config import settings
from src.core.constants import (
    DEFAULT_GRAPH_DEPTH,
    MAX_GRAPH_DEPTH,
    NODE_LABELS,
    RELATIONSHIP_TYPES,
)
from src.core.logging import get_logger
from src.mcp.base_client import BaseMCPClient

logger = get_logger(__name__)


@dataclass
class Neo4jQueryResult:
    """Result from a Neo4j query."""

    query: str
    parameters: dict[str, Any]
    nodes: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    paths: list[list[dict[str, Any]]] = field(default_factory=list)
    execution_time_ms: float = 0.0

    @property
    def is_empty(self) -> bool:
        """Check if the result is empty."""
        return not self.nodes and not self.relationships and not self.paths


# Common Cypher query templates
QUERIES = {
    "get_entity": """
        MATCH (n:{label} {{name: $name}})
        RETURN n
    """,
    "get_class_dependencies": """
        MATCH (c:Class {{name: $class_name}})-[:DEPENDS_ON]->(dep:Class)
        RETURN dep.name as dependency, dep.file_path as path, dep.package as package
    """,
    "get_method_calls": """
        MATCH (m:Method {{name: $method_name, class_name: $class_name}})-[:CALLS]->(called:Method)
        RETURN called.name as method, called.class_name as class, called.file_path as file
    """,
    "find_entry_points": """
        MATCH (c:Class)-[:CONTAINS]->(m:Method)
        WHERE m.name IN ['main', 'init', 'setup', 'start', 'run']
        RETURN c.name as class, m.name as method, c.file_path as file
    """,
    "get_component_structure": """
        MATCH path = (comp:Component {{name: $component}})-[:CONTAINS*1..{depth}]->(element)
        RETURN path
    """,
    "trace_frontend_to_backend": """
        MATCH path = (fe:Frontend {{name: $frontend_component}})
                     -[:INTEGRATES_WITH*1..{depth}]->
                     (be:Backend)
        RETURN path
    """,
    "get_class_methods": """
        MATCH (c:Class {{name: $class_name}})-[:CONTAINS]->(m:Method)
        RETURN m.name as method, m.signature as signature, m.line_number as line
        ORDER BY m.line_number
    """,
    "get_class_hierarchy": """
        MATCH path = (c:Class {{name: $class_name}})-[:EXTENDS*0..{depth}]->(parent:Class)
        RETURN path
    """,
    "get_interface_implementations": """
        MATCH (c:Class)-[:IMPLEMENTS]->(i:Interface {{name: $interface_name}})
        RETURN c.name as class, c.file_path as file
    """,
    "search_by_pattern": """
        MATCH (n)
        WHERE n.name =~ $pattern
        RETURN labels(n) as labels, n.name as name, n.file_path as file
        LIMIT $limit
    """,
    "get_call_chain": """
        MATCH path = (m:Method {{name: $method_name, class_name: $class_name}})
                     -[:CALLS*1..{depth}]->(called:Method)
        RETURN path
    """,
    "get_reverse_dependencies": """
        MATCH (dependent:Class)-[:DEPENDS_ON]->(c:Class {{name: $class_name}})
        RETURN dependent.name as dependent, dependent.file_path as file
    """,
}


class Neo4jMCPClient(BaseMCPClient):
    """
    MCP client for Neo4j graph database.
    Provides methods to query codebase structure and relationships.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        """
        Initialize the Neo4j MCP client.

        Args:
            server_url: MCP server URL (defaults to settings)
            timeout: Request timeout in seconds
        """
        url = server_url or settings.neo4j.mcp_url
        super().__init__(server_url=url, timeout=timeout)

    @property
    def mcp_type(self) -> str:
        return "Neo4j"

    async def health_check(self) -> bool:
        """Check if Neo4j MCP server is healthy."""
        try:
            result = await self._get("/health")
            return result.get("status") == "healthy"
        except Exception as e:
            logger.warning("Neo4j health check failed", error=str(e))
            return False

    async def execute_query(
        self,
        query: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> Neo4jQueryResult:
        """
        Execute a raw Cypher query.

        Args:
            query: Cypher query string
            parameters: Query parameters

        Returns:
            Query result with nodes, relationships, and paths
        """
        params = parameters or {}

        logger.debug("Executing Neo4j query", query=query[:100], params=params)

        response = await self._post(
            "/query",
            data={"query": query, "parameters": params},
        )

        result = Neo4jQueryResult(
            query=query,
            parameters=params,
            nodes=response.get("nodes", []),
            relationships=response.get("relationships", []),
            paths=response.get("paths", []),
            execution_time_ms=response.get("execution_time_ms", 0.0),
        )

        logger.debug(
            "Query completed",
            nodes_count=len(result.nodes),
            relationships_count=len(result.relationships),
            execution_time_ms=result.execution_time_ms,
        )

        return result

    async def query_entity(
        self,
        entity_name: str,
        entity_type: str = "Class",
    ) -> Neo4jQueryResult:
        """
        Query for a specific entity by name and type.

        Args:
            entity_name: Name of the entity
            entity_type: Type/label of the entity (Class, Method, Interface, etc.)

        Returns:
            Query result containing the entity if found
        """
        # Validate entity type
        if entity_type not in NODE_LABELS.values():
            entity_type = NODE_LABELS.get(entity_type.upper(), "Class")

        query = QUERIES["get_entity"].format(label=entity_type)
        return await self.execute_query(query, {"name": entity_name})

    async def get_dependencies(
        self,
        class_name: str,
        depth: int = DEFAULT_GRAPH_DEPTH,
    ) -> Neo4jQueryResult:
        """
        Get dependencies for a class.

        Args:
            class_name: Name of the class
            depth: How deep to traverse (1-5)

        Returns:
            Query result with dependency information
        """
        depth = min(max(1, depth), MAX_GRAPH_DEPTH)
        return await self.execute_query(
            QUERIES["get_class_dependencies"],
            {"class_name": class_name},
        )

    async def get_call_chain(
        self,
        method_name: str,
        class_name: str,
        depth: int = DEFAULT_GRAPH_DEPTH,
    ) -> Neo4jQueryResult:
        """
        Get the call chain for a method.

        Args:
            method_name: Name of the method
            class_name: Name of the containing class
            depth: How deep to traverse

        Returns:
            Query result with call chain paths
        """
        depth = min(max(1, depth), MAX_GRAPH_DEPTH)
        query = QUERIES["get_call_chain"].format(depth=depth)
        return await self.execute_query(
            query,
            {"method_name": method_name, "class_name": class_name},
        )

    async def find_integration_points(
        self,
        component: str,
        depth: int = DEFAULT_GRAPH_DEPTH,
    ) -> Neo4jQueryResult:
        """
        Find integration points for a frontend component.

        Args:
            component: Name of the frontend component
            depth: How deep to traverse

        Returns:
            Query result with integration paths
        """
        depth = min(max(1, depth), MAX_GRAPH_DEPTH)
        query = QUERIES["trace_frontend_to_backend"].format(depth=depth)
        return await self.execute_query(query, {"frontend_component": component})

    async def get_component_structure(
        self,
        component_name: str,
        depth: int = DEFAULT_GRAPH_DEPTH,
    ) -> Neo4jQueryResult:
        """
        Get the internal structure of a component.

        Args:
            component_name: Name of the component
            depth: How deep to traverse

        Returns:
            Query result with component structure
        """
        depth = min(max(1, depth), MAX_GRAPH_DEPTH)
        query = QUERIES["get_component_structure"].format(depth=depth)
        return await self.execute_query(query, {"component": component_name})

    async def get_class_methods(self, class_name: str) -> Neo4jQueryResult:
        """
        Get all methods of a class.

        Args:
            class_name: Name of the class

        Returns:
            Query result with method information
        """
        return await self.execute_query(
            QUERIES["get_class_methods"],
            {"class_name": class_name},
        )

    async def get_class_hierarchy(
        self,
        class_name: str,
        depth: int = DEFAULT_GRAPH_DEPTH,
    ) -> Neo4jQueryResult:
        """
        Get the inheritance hierarchy for a class.

        Args:
            class_name: Name of the class
            depth: How deep to traverse

        Returns:
            Query result with hierarchy paths
        """
        depth = min(max(1, depth), MAX_GRAPH_DEPTH)
        query = QUERIES["get_class_hierarchy"].format(depth=depth)
        return await self.execute_query(query, {"class_name": class_name})

    async def get_interface_implementations(
        self,
        interface_name: str,
    ) -> Neo4jQueryResult:
        """
        Get all classes implementing an interface.

        Args:
            interface_name: Name of the interface

        Returns:
            Query result with implementing classes
        """
        return await self.execute_query(
            QUERIES["get_interface_implementations"],
            {"interface_name": interface_name},
        )

    async def search_by_pattern(
        self,
        pattern: str,
        limit: int = 50,
    ) -> Neo4jQueryResult:
        """
        Search for entities by name pattern (regex).

        Args:
            pattern: Regex pattern to match
            limit: Maximum results to return

        Returns:
            Query result with matching entities
        """
        return await self.execute_query(
            QUERIES["search_by_pattern"],
            {"pattern": pattern, "limit": limit},
        )

    async def get_reverse_dependencies(self, class_name: str) -> Neo4jQueryResult:
        """
        Get classes that depend on the specified class.

        Args:
            class_name: Name of the class

        Returns:
            Query result with dependent classes
        """
        return await self.execute_query(
            QUERIES["get_reverse_dependencies"],
            {"class_name": class_name},
        )

    async def find_entry_points(self) -> Neo4jQueryResult:
        """
        Find application entry points.

        Returns:
            Query result with entry point methods
        """
        return await self.execute_query(QUERIES["find_entry_points"], {})

    async def verify_entity_exists(
        self,
        entity_name: str,
        entity_type: str = "Class",
    ) -> bool:
        """
        Verify if an entity exists in the graph.

        Args:
            entity_name: Name of the entity
            entity_type: Type of the entity

        Returns:
            True if entity exists, False otherwise
        """
        result = await self.query_entity(entity_name, entity_type)
        return not result.is_empty

    async def verify_relationship_exists(
        self,
        source: str,
        target: str,
        relationship_type: str,
    ) -> bool:
        """
        Verify if a relationship exists between two entities.

        Args:
            source: Source entity name
            target: Target entity name
            relationship_type: Type of relationship (CALLS, DEPENDS_ON, etc.)

        Returns:
            True if relationship exists, False otherwise
        """
        # Validate relationship type
        if relationship_type.upper() not in RELATIONSHIP_TYPES.values():
            relationship_type = RELATIONSHIP_TYPES.get(
                relationship_type.upper(), "DEPENDS_ON"
            )

        query = f"""
            MATCH (a)-[:{relationship_type}]->(b)
            WHERE a.name = $source AND b.name = $target
            RETURN count(*) as count
        """
        result = await self.execute_query(
            query,
            {"source": source, "target": target},
        )

        if result.nodes:
            count = result.nodes[0].get("count", 0)
            return count > 0
        return False
