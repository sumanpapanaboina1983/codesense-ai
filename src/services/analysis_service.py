"""
Analysis service for codebase analysis operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from src.agentic.reasoning_engine import ReasoningEngine, ReasoningResult
from src.core.logging import get_logger
from src.mcp.neo4j_client import Neo4jMCPClient
from src.mcp.filesystem_client import FilesystemMCPClient
from src.mcp.tool_registry import MCPToolRegistry

logger = get_logger(__name__)


@dataclass
class ComponentInfo:
    """Information about a codebase component."""

    name: str
    type: str  # class, module, service, etc.
    path: str
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """Result of codebase analysis."""

    codebase_path: str
    analyzed_at: datetime
    components: list[ComponentInfo] = field(default_factory=list)
    architecture: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    insights: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)


class AnalysisService:
    """
    Service for analyzing codebases and extracting insights.
    """

    def __init__(
        self,
        tool_registry: MCPToolRegistry,
        reasoning_engine: Optional[ReasoningEngine] = None,
    ) -> None:
        """
        Initialize the analysis service.

        Args:
            tool_registry: MCP tool registry
            reasoning_engine: Reasoning engine for deeper analysis
        """
        self.tool_registry = tool_registry
        self.reasoning_engine = reasoning_engine

        # Analysis cache
        self._cache: dict[str, AnalysisResult] = {}

    async def analyze_codebase(
        self,
        codebase_path: str,
        depth: str = "standard",
        focus_areas: Optional[list[str]] = None,
    ) -> AnalysisResult:
        """
        Perform comprehensive codebase analysis.

        Args:
            codebase_path: Path to codebase
            depth: Analysis depth (quick, standard, deep)
            focus_areas: Specific areas to focus on

        Returns:
            Analysis result
        """
        logger.info(
            "Starting codebase analysis",
            path=codebase_path,
            depth=depth,
        )

        # Check cache
        cache_key = f"{codebase_path}:{depth}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            # Return cached if less than 1 hour old
            if (datetime.utcnow() - cached.analyzed_at).total_seconds() < 3600:
                logger.info("Returning cached analysis")
                return cached

        # Gather data from various sources
        components = await self._discover_components(codebase_path)
        architecture = await self._analyze_architecture(codebase_path, components)
        metrics = await self._calculate_metrics(codebase_path, components)
        insights = await self._generate_insights(codebase_path, components, architecture, metrics)

        result = AnalysisResult(
            codebase_path=codebase_path,
            analyzed_at=datetime.utcnow(),
            components=components,
            architecture=architecture,
            metrics=metrics,
            insights=insights,
        )

        # Cache result
        self._cache[cache_key] = result

        logger.info(
            "Codebase analysis complete",
            components_found=len(components),
            insights_generated=len(insights),
        )

        return result

    async def analyze_component(
        self,
        codebase_path: str,
        component_name: str,
    ) -> ComponentInfo:
        """
        Analyze a specific component.

        Args:
            codebase_path: Path to codebase
            component_name: Component name

        Returns:
            Component information
        """
        logger.info(
            "Analyzing component",
            component=component_name,
        )

        # Query Neo4j for component info
        try:
            graph_data = await self.tool_registry.execute_tool(
                "neo4j_query_entity",
                {"entity_type": "component", "name": component_name}
            )
        except Exception as e:
            logger.warning("Failed to query graph", error=str(e))
            graph_data = {}

        # Get dependencies
        try:
            dependencies = await self.tool_registry.execute_tool(
                "neo4j_get_dependencies",
                {"entity_name": component_name}
            )
        except Exception as e:
            logger.warning("Failed to get dependencies", error=str(e))
            dependencies = []

        # Get dependents
        try:
            dependents = await self.tool_registry.execute_tool(
                "neo4j_get_dependents",
                {"entity_name": component_name}
            )
        except Exception as e:
            logger.warning("Failed to get dependents", error=str(e))
            dependents = []

        # Generate description using reasoning
        description = ""
        if self.reasoning_engine:
            result = await self.reasoning_engine.reason(
                query=f"Describe the purpose and functionality of the {component_name} component.",
                context={"graph_data": graph_data, "codebase_path": codebase_path}
            )
            description = result.final_answer or ""

        return ComponentInfo(
            name=component_name,
            type=graph_data.get("type", "unknown"),
            path=graph_data.get("path", ""),
            description=description,
            dependencies=dependencies if isinstance(dependencies, list) else [],
            dependents=dependents if isinstance(dependents, list) else [],
            metrics=graph_data.get("metrics", {}),
        )

    async def get_dependency_graph(
        self,
        codebase_path: str,
        root_component: Optional[str] = None,
        max_depth: int = 3,
    ) -> dict[str, Any]:
        """
        Get the dependency graph for the codebase or a specific component.

        Args:
            codebase_path: Path to codebase
            root_component: Optional root component to start from
            max_depth: Maximum depth to traverse

        Returns:
            Dependency graph structure
        """
        logger.info(
            "Building dependency graph",
            root=root_component,
            max_depth=max_depth,
        )

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        visited: set[str] = set()

        async def traverse(component_name: str, depth: int) -> None:
            if depth > max_depth or component_name in visited:
                return

            visited.add(component_name)

            # Get component info
            try:
                info = await self.analyze_component(codebase_path, component_name)
                nodes.append({
                    "id": component_name,
                    "type": info.type,
                    "path": info.path,
                })

                # Add edges for dependencies
                for dep in info.dependencies:
                    edges.append({
                        "source": component_name,
                        "target": dep,
                        "type": "depends_on",
                    })
                    await traverse(dep, depth + 1)

            except Exception as e:
                logger.warning(f"Failed to traverse {component_name}", error=str(e))

        if root_component:
            await traverse(root_component, 0)
        else:
            # Get all top-level components
            components = await self._discover_components(codebase_path)
            for comp in components[:20]:  # Limit for performance
                await traverse(comp.name, 0)

        return {
            "nodes": nodes,
            "edges": edges,
            "root": root_component,
            "depth": max_depth,
        }

    async def find_entry_points(
        self,
        codebase_path: str,
    ) -> list[dict[str, Any]]:
        """
        Find entry points in the codebase (APIs, main functions, etc.).

        Args:
            codebase_path: Path to codebase

        Returns:
            List of entry points
        """
        logger.info("Finding entry points", path=codebase_path)

        entry_points: list[dict[str, Any]] = []

        # Query Neo4j for entry points
        try:
            # Look for API endpoints
            api_result = await self.tool_registry.execute_tool(
                "neo4j_execute_query",
                {
                    "query": """
                    MATCH (n)
                    WHERE n.type IN ['endpoint', 'api', 'route', 'handler']
                    OR n.name CONTAINS 'main'
                    OR n.name CONTAINS 'app'
                    RETURN n.name as name, n.type as type, n.path as path
                    LIMIT 50
                    """
                }
            )

            if isinstance(api_result, list):
                for item in api_result:
                    entry_points.append({
                        "name": item.get("name", ""),
                        "type": item.get("type", "unknown"),
                        "path": item.get("path", ""),
                    })
        except Exception as e:
            logger.warning("Failed to query entry points", error=str(e))

        # Search file system for common entry point patterns
        try:
            main_files = await self.tool_registry.execute_tool(
                "filesystem_find_files",
                {
                    "path": codebase_path,
                    "pattern": "*main*.py",
                }
            )

            if isinstance(main_files, list):
                for file_path in main_files:
                    entry_points.append({
                        "name": file_path.split("/")[-1],
                        "type": "main",
                        "path": file_path,
                    })
        except Exception as e:
            logger.warning("Failed to find main files", error=str(e))

        return entry_points

    async def search_codebase(
        self,
        codebase_path: str,
        query: str,
        search_type: str = "semantic",
    ) -> list[dict[str, Any]]:
        """
        Search the codebase for relevant code.

        Args:
            codebase_path: Path to codebase
            query: Search query
            search_type: Type of search (semantic, keyword, pattern)

        Returns:
            List of search results
        """
        logger.info(
            "Searching codebase",
            query=query,
            type=search_type,
        )

        results: list[dict[str, Any]] = []

        if search_type == "keyword":
            # Simple file search
            try:
                file_results = await self.tool_registry.execute_tool(
                    "filesystem_search_in_file",
                    {
                        "path": codebase_path,
                        "pattern": query,
                    }
                )

                if isinstance(file_results, list):
                    results.extend(file_results)
            except Exception as e:
                logger.warning("Keyword search failed", error=str(e))

        elif search_type == "semantic":
            # Use reasoning engine for semantic search
            if self.reasoning_engine:
                reasoning_result = await self.reasoning_engine.reason(
                    query=f"Find code related to: {query}",
                    context={"codebase_path": codebase_path}
                )

                if reasoning_result.final_answer:
                    results.append({
                        "type": "semantic",
                        "query": query,
                        "result": reasoning_result.final_answer,
                        "confidence": reasoning_result.confidence,
                    })

        return results

    async def _discover_components(
        self,
        codebase_path: str
    ) -> list[ComponentInfo]:
        """Discover components in the codebase."""
        components: list[ComponentInfo] = []

        try:
            # Query Neo4j for all components
            result = await self.tool_registry.execute_tool(
                "neo4j_execute_query",
                {
                    "query": """
                    MATCH (n)
                    WHERE n.type IN ['class', 'module', 'service', 'component']
                    RETURN n.name as name, n.type as type, n.path as path
                    LIMIT 100
                    """
                }
            )

            if isinstance(result, list):
                for item in result:
                    components.append(ComponentInfo(
                        name=item.get("name", ""),
                        type=item.get("type", "unknown"),
                        path=item.get("path", ""),
                    ))
        except Exception as e:
            logger.warning("Failed to discover components", error=str(e))

        return components

    async def _analyze_architecture(
        self,
        codebase_path: str,
        components: list[ComponentInfo]
    ) -> dict[str, Any]:
        """Analyze the architecture of the codebase."""
        architecture: dict[str, Any] = {
            "layers": [],
            "patterns": [],
            "structure": {},
        }

        # Group components by type
        by_type: dict[str, list[str]] = {}
        for comp in components:
            if comp.type not in by_type:
                by_type[comp.type] = []
            by_type[comp.type].append(comp.name)

        architecture["structure"] = by_type

        # Detect architectural patterns
        if self.reasoning_engine:
            result = await self.reasoning_engine.reason(
                query="Identify the architectural patterns used in this codebase.",
                context={
                    "component_types": by_type,
                    "codebase_path": codebase_path,
                }
            )
            if result.final_answer:
                architecture["patterns"] = [result.final_answer]

        return architecture

    async def _calculate_metrics(
        self,
        codebase_path: str,
        components: list[ComponentInfo]
    ) -> dict[str, Any]:
        """Calculate codebase metrics."""
        return {
            "total_components": len(components),
            "component_types": len(set(c.type for c in components)),
            "analyzed_at": datetime.utcnow().isoformat(),
        }

    async def _generate_insights(
        self,
        codebase_path: str,
        components: list[ComponentInfo],
        architecture: dict[str, Any],
        metrics: dict[str, Any]
    ) -> list[str]:
        """Generate insights from analysis."""
        insights: list[str] = []

        # Basic insights
        insights.append(f"Codebase contains {len(components)} components")

        if architecture.get("patterns"):
            insights.append(f"Detected patterns: {', '.join(architecture['patterns'])}")

        # Use reasoning for deeper insights
        if self.reasoning_engine:
            result = await self.reasoning_engine.reason(
                query="What are the key insights about this codebase's structure and quality?",
                context={
                    "components": [c.name for c in components[:20]],
                    "architecture": architecture,
                    "metrics": metrics,
                }
            )
            if result.final_answer:
                insights.append(result.final_answer)

        return insights
