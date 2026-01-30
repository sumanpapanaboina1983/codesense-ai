"""
Tool Registry for Copilot SDK

Registers MCP tools (Neo4j, Filesystem) with the Copilot SDK session,
allowing the LLM to call them directly for an agentic workflow.

Uses the @define_tool decorator with Pydantic models as per SDK requirements.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Try to import the define_tool decorator from Copilot SDK
try:
    from copilot.tools import define_tool
    COPILOT_TOOLS_AVAILABLE = True
except ImportError:
    COPILOT_TOOLS_AVAILABLE = False
    define_tool = None
    logger.warning("copilot.tools not available - tools will use fallback format")


# Pydantic models for tool parameters
class QueryCodeStructureParams(BaseModel):
    """Parameters for querying code structure."""
    query: str = Field(description="Cypher query to execute. Example: MATCH (c:Component) RETURN c.name, c.type LIMIT 10")


class GetDependenciesParams(BaseModel):
    """Parameters for getting component dependencies."""
    component_name: str = Field(description="Name of the component to get dependencies for")


class SearchSimilarParams(BaseModel):
    """Parameters for searching similar features."""
    description: str = Field(description="Description of the feature to search for")
    limit: int = Field(default=5, description="Maximum number of results to return")


class ReadFileParams(BaseModel):
    """Parameters for reading a file."""
    path: str = Field(description="Path to the file relative to codebase root")


class ListDirectoryParams(BaseModel):
    """Parameters for listing a directory."""
    path: str = Field(description="Directory path relative to codebase root")


class SearchFilesParams(BaseModel):
    """Parameters for searching files."""
    pattern: str = Field(description="Glob pattern to search for. Example: **/*.py, src/**/*.ts")
    path: str = Field(default="", description="Directory to search in (optional)")


class GetFileInfoParams(BaseModel):
    """Parameters for getting file info."""
    path: str = Field(description="Path to the file")


class ToolRegistry:
    """
    Registers MCP tools with Copilot SDK for agentic tool calling.

    This allows the LLM to:
    1. Query Neo4j for code structure and dependencies
    2. Read files from the filesystem
    3. Search for similar features

    Uses @define_tool decorator for proper SDK integration.
    """

    def __init__(
        self,
        neo4j_client: Neo4jMCPClient,
        filesystem_client: FilesystemMCPClient,
    ):
        self.neo4j = neo4j_client
        self.filesystem = filesystem_client
        self._tools: list[Callable] = []
        self._tool_handlers: dict[str, Callable] = {}
        self._register_tools()

    def _register_tools(self) -> None:
        """Register all MCP tools using @define_tool decorator."""

        if not COPILOT_TOOLS_AVAILABLE:
            logger.warning("Copilot tools not available, using legacy format")
            self._register_legacy_tools()
            return

        # Create tool functions with @define_tool decorator
        @define_tool(description="Query the code graph database to find components, classes, functions, and their relationships. Use Cypher query language.", params_type=QueryCodeStructureParams)
        async def query_code_structure(params: QueryCodeStructureParams) -> dict:
            try:
                result = await self.neo4j.query_code_structure(params.query)
                return {"success": True, "data": result}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @define_tool(description="Get dependencies and dependents of a specific component in the codebase.", params_type=GetDependenciesParams)
        async def get_component_dependencies(params: GetDependenciesParams) -> dict:
            try:
                result = await self.neo4j.get_component_dependencies(params.component_name)
                return {"success": True, "data": result}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @define_tool(description="Search for similar existing features in the codebase based on a description.", params_type=SearchSimilarParams)
        async def search_similar_features(params: SearchSimilarParams) -> dict:
            try:
                result = await self.neo4j.search_similar_features(params.description, params.limit)
                return {"success": True, "data": result}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @define_tool(description="Read the contents of a source code file from the codebase.", params_type=ReadFileParams)
        async def read_file(params: ReadFileParams) -> dict:
            try:
                content = await self.filesystem.read_file(params.path)
                return {"success": True, "path": params.path, "content": content}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @define_tool(description="List files and subdirectories in a directory.", params_type=ListDirectoryParams)
        async def list_directory(params: ListDirectoryParams) -> dict:
            try:
                result = await self.filesystem.list_directory(params.path)
                return {"success": True, "path": params.path, "entries": result}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @define_tool(description="Search for files matching a pattern in the codebase.", params_type=SearchFilesParams)
        async def search_files(params: SearchFilesParams) -> dict:
            try:
                result = await self.filesystem.search_files(params.pattern, params.path)
                return {"success": True, "pattern": params.pattern, "files": result}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @define_tool(description="Get metadata about a file (size, type, last modified).", params_type=GetFileInfoParams)
        async def get_file_info(params: GetFileInfoParams) -> dict:
            try:
                result = await self.filesystem.get_file_info(params.path)
                return {"success": True, "data": result}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # Store the decorated tool functions
        self._tools = [
            query_code_structure,
            get_component_dependencies,
            search_similar_features,
            read_file,
            list_directory,
            search_files,
            get_file_info,
        ]

        # Store handlers for manual execution
        self._tool_handlers = {
            "query_code_structure": query_code_structure,
            "get_component_dependencies": get_component_dependencies,
            "search_similar_features": search_similar_features,
            "read_file": read_file,
            "list_directory": list_directory,
            "search_files": search_files,
            "get_file_info": get_file_info,
        }

        logger.info(f"Registered {len(self._tools)} MCP tools with @define_tool decorator")

    def _register_legacy_tools(self) -> None:
        """Register tools in legacy format when SDK is not available."""
        self._legacy_tools: dict[str, dict[str, Any]] = {}

        self._legacy_tools["query_code_structure"] = {
            "name": "query_code_structure",
            "description": "Query the code graph database to find components, classes, functions, and their relationships. Use Cypher query language.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Cypher query to execute. Example: MATCH (c:Component) RETURN c.name, c.type LIMIT 10"
                    }
                },
                "required": ["query"]
            },
        }

        self._legacy_tools["get_component_dependencies"] = {
            "name": "get_component_dependencies",
            "description": "Get dependencies and dependents of a specific component in the codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "component_name": {
                        "type": "string",
                        "description": "Name of the component to get dependencies for"
                    }
                },
                "required": ["component_name"]
            },
        }

        self._legacy_tools["search_similar_features"] = {
            "name": "search_similar_features",
            "description": "Search for similar existing features in the codebase based on a description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Description of the feature to search for"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 5
                    }
                },
                "required": ["description"]
            },
        }

        self._legacy_tools["read_file"] = {
            "name": "read_file",
            "description": "Read the contents of a source code file from the codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to codebase root"
                    }
                },
                "required": ["path"]
            },
        }

        self._legacy_tools["list_directory"] = {
            "name": "list_directory",
            "description": "List files and subdirectories in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to codebase root"
                    }
                },
                "required": ["path"]
            },
        }

        self._legacy_tools["search_files"] = {
            "name": "search_files",
            "description": "Search for files matching a pattern in the codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to search for. Example: **/*.py, src/**/*.ts"
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (optional)",
                        "default": ""
                    }
                },
                "required": ["pattern"]
            },
        }

        self._legacy_tools["get_file_info"] = {
            "name": "get_file_info",
            "description": "Get metadata about a file (size, type, last modified).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file"
                    }
                },
                "required": ["path"]
            },
        }

        logger.info(f"Registered {len(self._legacy_tools)} MCP tools in legacy format")

    def get_tool_definitions(self) -> list[Any]:
        """
        Get tool definitions for Copilot SDK session.

        Returns decorated tool functions when SDK is available,
        otherwise returns legacy format definitions.
        """
        if COPILOT_TOOLS_AVAILABLE and self._tools:
            # Return the decorated functions directly - SDK handles them
            return self._tools

        # Return legacy format for fallback
        if hasattr(self, '_legacy_tools'):
            return [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"],
                    }
                }
                for tool in self._legacy_tools.values()
            ]

        return []

    def get_tools(self) -> list[Any]:
        """
        Convenience alias for get_tool_definitions().

        Returns the list of tool functions for SDK session configuration.
        """
        return self.get_tool_definitions()

    def get_tool_handlers(self) -> dict[str, Callable]:
        """Get mapping of tool names to handlers."""
        return self._tool_handlers

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name with given arguments."""
        if tool_name not in self._tool_handlers:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        handler = self._tool_handlers[tool_name]
        try:
            # Create the appropriate params object
            params_class = self._get_params_class(tool_name)
            if params_class:
                params = params_class(**arguments)
                result = await handler(params)
            else:
                result = await handler(**arguments)
            return json.dumps(result, default=str)
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}", error=str(e))
            return json.dumps({"error": str(e)})

    def _get_params_class(self, tool_name: str) -> Optional[type[BaseModel]]:
        """Get the Pydantic params class for a tool."""
        params_map = {
            "query_code_structure": QueryCodeStructureParams,
            "get_component_dependencies": GetDependenciesParams,
            "search_similar_features": SearchSimilarParams,
            "read_file": ReadFileParams,
            "list_directory": ListDirectoryParams,
            "search_files": SearchFilesParams,
            "get_file_info": GetFileInfoParams,
        }
        return params_map.get(tool_name)
