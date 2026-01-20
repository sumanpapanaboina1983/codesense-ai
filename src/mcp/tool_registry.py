"""
MCP Tool Registry - discovers and manages MCP tools for AI integration.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.core.logging import get_logger
from src.mcp.filesystem_client import FilesystemMCPClient
from src.mcp.neo4j_client import Neo4jMCPClient

logger = get_logger(__name__)


@dataclass
class ToolDefinition:
    """Definition of an MCP tool for AI consumption."""

    name: str
    description: str
    parameters: dict[str, Any]
    required_params: list[str] = field(default_factory=list)
    category: str = "general"

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required_params,
                },
            },
        }


# Tool definitions for Neo4j operations
NEO4J_TOOLS = [
    ToolDefinition(
        name="neo4j_query_entity",
        description="Query the code graph for a specific entity (class, method, interface, component)",
        parameters={
            "entity_name": {
                "type": "string",
                "description": "Name of the entity to find",
            },
            "entity_type": {
                "type": "string",
                "enum": ["Class", "Method", "Interface", "Component", "Module"],
                "description": "Type of the entity",
            },
        },
        required_params=["entity_name", "entity_type"],
        category="neo4j",
    ),
    ToolDefinition(
        name="neo4j_get_dependencies",
        description="Get all dependencies of a class",
        parameters={
            "class_name": {
                "type": "string",
                "description": "Name of the class",
            },
            "depth": {
                "type": "integer",
                "description": "Depth of dependency traversal (1-5)",
                "default": 2,
            },
        },
        required_params=["class_name"],
        category="neo4j",
    ),
    ToolDefinition(
        name="neo4j_get_call_chain",
        description="Get the call chain for a method",
        parameters={
            "method_name": {
                "type": "string",
                "description": "Name of the method",
            },
            "class_name": {
                "type": "string",
                "description": "Name of the containing class",
            },
            "depth": {
                "type": "integer",
                "description": "Depth of call chain traversal",
                "default": 2,
            },
        },
        required_params=["method_name", "class_name"],
        category="neo4j",
    ),
    ToolDefinition(
        name="neo4j_get_component_structure",
        description="Get the internal structure of a component",
        parameters={
            "component_name": {
                "type": "string",
                "description": "Name of the component",
            },
            "depth": {
                "type": "integer",
                "description": "Depth of traversal",
                "default": 2,
            },
        },
        required_params=["component_name"],
        category="neo4j",
    ),
    ToolDefinition(
        name="neo4j_verify_entity",
        description="Verify if an entity exists in the codebase graph",
        parameters={
            "entity_name": {
                "type": "string",
                "description": "Name of the entity",
            },
            "entity_type": {
                "type": "string",
                "description": "Type of entity",
                "default": "Class",
            },
        },
        required_params=["entity_name"],
        category="neo4j",
    ),
    ToolDefinition(
        name="neo4j_verify_relationship",
        description="Verify if a relationship exists between two entities",
        parameters={
            "source": {
                "type": "string",
                "description": "Source entity name",
            },
            "target": {
                "type": "string",
                "description": "Target entity name",
            },
            "relationship_type": {
                "type": "string",
                "enum": ["CALLS", "DEPENDS_ON", "EXTENDS", "IMPLEMENTS", "CONTAINS"],
                "description": "Type of relationship",
            },
        },
        required_params=["source", "target", "relationship_type"],
        category="neo4j",
    ),
]

# Tool definitions for Filesystem operations
FILESYSTEM_TOOLS = [
    ToolDefinition(
        name="filesystem_read_file",
        description="Read the contents of a source file",
        parameters={
            "path": {
                "type": "string",
                "description": "Path to the file (relative to codebase root)",
            },
        },
        required_params=["path"],
        category="filesystem",
    ),
    ToolDefinition(
        name="filesystem_read_file_range",
        description="Read specific lines from a source file",
        parameters={
            "path": {
                "type": "string",
                "description": "Path to the file",
            },
            "start_line": {
                "type": "integer",
                "description": "Starting line number (1-based)",
            },
            "end_line": {
                "type": "integer",
                "description": "Ending line number (inclusive)",
            },
        },
        required_params=["path", "start_line", "end_line"],
        category="filesystem",
    ),
    ToolDefinition(
        name="filesystem_find_files",
        description="Find files matching a glob pattern",
        parameters={
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g., '**/*.java', '*Service.py')",
            },
            "root": {
                "type": "string",
                "description": "Starting directory",
                "default": "",
            },
        },
        required_params=["pattern"],
        category="filesystem",
    ),
    ToolDefinition(
        name="filesystem_search_in_file",
        description="Search for a pattern within a file",
        parameters={
            "path": {
                "type": "string",
                "description": "Path to the file",
            },
            "pattern": {
                "type": "string",
                "description": "Search pattern (regex supported)",
            },
        },
        required_params=["path", "pattern"],
        category="filesystem",
    ),
    ToolDefinition(
        name="filesystem_verify_content",
        description="Verify if specific content exists in a file",
        parameters={
            "path": {
                "type": "string",
                "description": "Path to the file",
            },
            "content": {
                "type": "string",
                "description": "Content to search for",
            },
        },
        required_params=["path", "content"],
        category="filesystem",
    ),
]


class MCPToolRegistry:
    """
    Registry for MCP tools.
    Manages tool definitions and executes tool calls.
    """

    def __init__(
        self,
        neo4j_client: Optional[Neo4jMCPClient] = None,
        filesystem_client: Optional[FilesystemMCPClient] = None,
    ) -> None:
        """
        Initialize the tool registry.

        Args:
            neo4j_client: Neo4j MCP client instance
            filesystem_client: Filesystem MCP client instance
        """
        self.neo4j_client = neo4j_client
        self.filesystem_client = filesystem_client

        # Build tool mapping
        self._tools: dict[str, ToolDefinition] = {}
        self._executors: dict[str, Callable] = {}

        self._register_tools()

    def _register_tools(self) -> None:
        """Register all available tools."""
        # Register Neo4j tools
        if self.neo4j_client:
            for tool in NEO4J_TOOLS:
                self._tools[tool.name] = tool
            self._register_neo4j_executors()

        # Register Filesystem tools
        if self.filesystem_client:
            for tool in FILESYSTEM_TOOLS:
                self._tools[tool.name] = tool
            self._register_filesystem_executors()

        logger.info(f"Registered {len(self._tools)} MCP tools")

    def _register_neo4j_executors(self) -> None:
        """Register Neo4j tool executors."""
        self._executors["neo4j_query_entity"] = self._exec_neo4j_query_entity
        self._executors["neo4j_get_dependencies"] = self._exec_neo4j_get_dependencies
        self._executors["neo4j_get_call_chain"] = self._exec_neo4j_get_call_chain
        self._executors["neo4j_get_component_structure"] = self._exec_neo4j_get_component_structure
        self._executors["neo4j_verify_entity"] = self._exec_neo4j_verify_entity
        self._executors["neo4j_verify_relationship"] = self._exec_neo4j_verify_relationship

    def _register_filesystem_executors(self) -> None:
        """Register Filesystem tool executors."""
        self._executors["filesystem_read_file"] = self._exec_filesystem_read_file
        self._executors["filesystem_read_file_range"] = self._exec_filesystem_read_file_range
        self._executors["filesystem_find_files"] = self._exec_filesystem_find_files
        self._executors["filesystem_search_in_file"] = self._exec_filesystem_search_in_file
        self._executors["filesystem_verify_content"] = self._exec_filesystem_verify_content

    def get_tool_definitions(
        self,
        categories: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """
        Get tool definitions in OpenAI function calling format.

        Args:
            categories: Optional filter by categories

        Returns:
            List of tool definitions
        """
        tools = self._tools.values()

        if categories:
            tools = [t for t in tools if t.category in categories]

        return [tool.to_openai_format() for tool in tools]

    def get_available_tools(self) -> list[str]:
        """Get list of available tool names."""
        return list(self._tools.keys())

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a tool call.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        if tool_name not in self._executors:
            return {"error": f"Unknown tool: {tool_name}"}

        logger.debug("Executing tool", tool=tool_name, args=arguments)

        try:
            result = await self._executors[tool_name](**arguments)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error("Tool execution failed", tool=tool_name, error=str(e))
            return {"success": False, "error": str(e)}

    # Neo4j executors
    async def _exec_neo4j_query_entity(
        self,
        entity_name: str,
        entity_type: str,
    ) -> dict[str, Any]:
        result = await self.neo4j_client.query_entity(entity_name, entity_type)
        return {
            "found": not result.is_empty,
            "nodes": result.nodes,
            "query": result.query,
        }

    async def _exec_neo4j_get_dependencies(
        self,
        class_name: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        result = await self.neo4j_client.get_dependencies(class_name, depth)
        return {
            "class": class_name,
            "dependencies": result.nodes,
        }

    async def _exec_neo4j_get_call_chain(
        self,
        method_name: str,
        class_name: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        result = await self.neo4j_client.get_call_chain(method_name, class_name, depth)
        return {
            "method": f"{class_name}.{method_name}",
            "call_chain": result.paths,
        }

    async def _exec_neo4j_get_component_structure(
        self,
        component_name: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        result = await self.neo4j_client.get_component_structure(component_name, depth)
        return {
            "component": component_name,
            "structure": result.paths,
        }

    async def _exec_neo4j_verify_entity(
        self,
        entity_name: str,
        entity_type: str = "Class",
    ) -> dict[str, Any]:
        exists = await self.neo4j_client.verify_entity_exists(entity_name, entity_type)
        return {
            "entity": entity_name,
            "type": entity_type,
            "exists": exists,
        }

    async def _exec_neo4j_verify_relationship(
        self,
        source: str,
        target: str,
        relationship_type: str,
    ) -> dict[str, Any]:
        exists = await self.neo4j_client.verify_relationship_exists(
            source, target, relationship_type
        )
        return {
            "source": source,
            "target": target,
            "relationship": relationship_type,
            "exists": exists,
        }

    # Filesystem executors
    async def _exec_filesystem_read_file(self, path: str) -> dict[str, Any]:
        result = await self.filesystem_client.read_file(path)
        return {
            "path": result.path,
            "content": result.content,
            "lines": result.total_lines,
            "truncated": result.truncated,
        }

    async def _exec_filesystem_read_file_range(
        self,
        path: str,
        start_line: int,
        end_line: int,
    ) -> dict[str, Any]:
        result = await self.filesystem_client.read_file_range(path, start_line, end_line)
        return {
            "path": result.path,
            "content": result.content,
            "start_line": result.start_line,
            "end_line": result.end_line,
        }

    async def _exec_filesystem_find_files(
        self,
        pattern: str,
        root: str = "",
    ) -> dict[str, Any]:
        files = await self.filesystem_client.find_files(pattern, root)
        return {
            "pattern": pattern,
            "files": files,
            "count": len(files),
        }

    async def _exec_filesystem_search_in_file(
        self,
        path: str,
        pattern: str,
    ) -> dict[str, Any]:
        matches = await self.filesystem_client.search_in_file(path, pattern)
        return {
            "path": path,
            "pattern": pattern,
            "matches": matches,
        }

    async def _exec_filesystem_verify_content(
        self,
        path: str,
        content: str,
    ) -> dict[str, Any]:
        exists = await self.filesystem_client.verify_content_exists(path, content)
        return {
            "path": path,
            "content_exists": exists,
        }

    async def close(self) -> None:
        """Close all MCP clients."""
        if self.neo4j_client:
            await self.neo4j_client.close()
        if self.filesystem_client:
            await self.filesystem_client.close()
