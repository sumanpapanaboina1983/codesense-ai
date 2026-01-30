"""Context aggregation from multiple sources."""

from __future__ import annotations

from typing import Any, Callable, Optional, Awaitable

from ..models.context import (
    AggregatedContext,
    ArchitectureContext,
    ImplementationContext,
    ComponentInfo,
    FileContext,
    APIContract,
    DataModel,
)
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from ..utils.logger import get_logger
from ..utils.token_counter import estimate_tokens

logger = get_logger(__name__)

# Type for progress callback: async function that takes (step: str, detail: str)
ProgressCallback = Callable[[str, str], Awaitable[None]]


class ContextAggregator:
    """Aggregates context from Neo4j and Filesystem MCPs."""

    def __init__(
        self,
        neo4j_client: Neo4jMCPClient,
        filesystem_client: FilesystemMCPClient,
        max_tokens: int = 100000,
    ):
        """
        Initialize the context aggregator.

        Args:
            neo4j_client: Neo4j MCP client
            filesystem_client: Filesystem MCP client
            max_tokens: Maximum tokens for context
        """
        self.neo4j = neo4j_client
        self.filesystem = filesystem_client
        self.max_tokens = max_tokens

    async def build_context(
        self,
        request: str,
        affected_components: Optional[list[str]] = None,
        include_similar: bool = True,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AggregatedContext:
        """
        Build aggregated context from all sources.

        Args:
            request: User's feature request
            affected_components: Known affected components
            include_similar: Search for similar features
            progress_callback: Optional callback for progress updates

        Returns:
            Aggregated context ready for LLM
        """
        logger.info("Building aggregated context...")

        # Helper to report progress
        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        await report("context", "Starting context aggregation...")

        # Phase 1: Get architecture from Neo4j
        await report("neo4j", "Querying code graph for architecture context...")
        architecture = await self._get_architecture_context(
            request,
            affected_components,
            progress_callback,
        )
        await report("neo4j", f"Found {len(architecture.components)} components")

        # Phase 2: Get implementation details from filesystem
        await report("filesystem", "Reading source files for implementation context...")
        implementation = await self._get_implementation_context(architecture, progress_callback)
        await report("filesystem", f"Analyzed {len(implementation.key_files)} key files")

        # Phase 3: Find similar features
        similar_features = []
        if include_similar:
            await report("neo4j", "Searching for similar features in codebase...")
            similar_features = await self._find_similar_features(request)
            if similar_features:
                await report("neo4j", f"Found {len(similar_features)} similar features")

        # Build complete context
        context = AggregatedContext(
            request=request,
            architecture=architecture,
            implementation=implementation,
            similar_features=similar_features,
        )

        # Check token budget
        if context.estimated_tokens > self.max_tokens:
            logger.warning(
                f"Context exceeds token limit ({context.estimated_tokens} > {self.max_tokens})"
            )
            context = await self._compress_context(context)

        logger.info(f"Context built: ~{context.estimated_tokens} tokens")
        return context

    async def _get_architecture_context(
        self,
        request: str,
        affected_components: Optional[list[str]],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ArchitectureContext:
        """Extract architecture info from Neo4j."""
        components = []
        dependencies: dict[str, list[str]] = {}
        api_contracts: list[APIContract] = []
        data_models: list[DataModel] = []

        # Helper to report progress
        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        # If specific components are provided, query their details
        if affected_components:
            for comp_name in affected_components:
                try:
                    await report("neo4j", f"Querying dependencies for component: {comp_name}")
                    # Get component info
                    deps = await self.neo4j.get_component_dependencies(comp_name)

                    component = ComponentInfo(
                        name=comp_name,
                        type="service",  # Could be determined from graph
                        path=f"/services/{comp_name}",
                        dependencies=deps.get("upstream", []),
                        dependents=deps.get("downstream", []),
                    )
                    components.append(component)
                    dependencies[comp_name] = deps.get("upstream", [])

                    # Get API contracts for this component
                    try:
                        await report("neo4j", f"Fetching API contracts for: {comp_name}")
                        apis = await self.neo4j.get_api_contracts(comp_name)
                        for api in apis:
                            api_contracts.append(APIContract(
                                endpoint=api.get("endpoint", ""),
                                method=api.get("method", "GET"),
                                parameters=api.get("parameters", {}),
                                service=comp_name,
                            ))
                    except Exception as e:
                        logger.debug(f"Could not get API contracts for {comp_name}: {e}")

                except Exception as e:
                    logger.warning(f"Could not get dependencies for {comp_name}: {e}")
                    # Still add the component with basic info
                    components.append(ComponentInfo(
                        name=comp_name,
                        type="service",
                        path=f"/services/{comp_name}",
                        dependencies=[],
                        dependents=[],
                    ))

        # If no components specified, try to identify from request
        if not affected_components:
            await report("neo4j", "Discovering services from code graph...")
            try:
                # Query for all services/components in the graph
                result = await self.neo4j.query_code_structure("""
                    MATCH (c:Service)
                    RETURN c.name as name, c.type as type, c.path as path
                    LIMIT 20
                """)
                for node in result.get("nodes", []):
                    components.append(ComponentInfo(
                        name=node.get("name", "unknown"),
                        type=node.get("type", "service"),
                        path=node.get("path", ""),
                        dependencies=[],
                        dependents=[],
                    ))
            except Exception as e:
                logger.debug(f"Could not query components: {e}")

        return ArchitectureContext(
            components=components,
            dependencies=dependencies,
            api_contracts=api_contracts,
            data_models=data_models,
        )

    async def _get_implementation_context(
        self,
        architecture: ArchitectureContext,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ImplementationContext:
        """Extract implementation details from filesystem."""
        key_files: list[FileContext] = []
        patterns: list[str] = []
        configs: dict[str, Any] = {}

        # Helper to report progress
        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        # Read key files for each component
        for component in architecture.components[:5]:  # Limit to avoid too many files
            try:
                await report("filesystem", f"Searching files for component: {component.name}")
                # Try common file patterns
                file_patterns = [
                    f"**/{component.name}/**/*.py",
                    f"**/{component.name}/**/*.java",
                    f"**/{component.name}/**/*.ts",
                    f"**/services/{component.name}/**/*",
                ]

                for pattern in file_patterns:
                    try:
                        files = await self.filesystem.search_files(pattern)
                        if isinstance(files, list):
                            for file_info in files[:3]:  # Limit files per component
                                file_path = file_info if isinstance(file_info, str) else file_info.get("path", "")
                                if file_path:
                                    try:
                                        await report("filesystem", f"Reading: {file_path.split('/')[-1]}")
                                        content = await self.filesystem.read_file(file_path)
                                        key_files.append(FileContext(
                                            path=file_path,
                                            content=content[:5000],  # Truncate large files
                                            relevance_score=0.8,
                                        ))
                                    except Exception:
                                        pass
                    except Exception:
                        continue

            except Exception as e:
                logger.debug(f"Could not get files for {component.name}: {e}")

        # Try to read config files
        config_patterns = [
            "**/config/*.yaml",
            "**/config/*.json",
            "**/.env.example",
        ]
        for pattern in config_patterns:
            try:
                config_files = await self.filesystem.search_files(pattern)
                if isinstance(config_files, list) and config_files:
                    for cf in config_files[:2]:
                        file_path = cf if isinstance(cf, str) else cf.get("path", "")
                        if file_path:
                            configs[file_path] = "present"
            except Exception:
                pass

        return ImplementationContext(
            key_files=key_files,
            patterns=patterns,
            configs=configs,
        )

    async def _find_similar_features(self, request: str) -> list[str]:
        """Search for similar existing features."""
        try:
            results = await self.neo4j.search_similar_features(request, limit=5)
            return [r.get("name", "") for r in results if r.get("name")]
        except Exception as e:
            logger.debug(f"Could not search similar features: {e}")
            return []

    async def _compress_context(
        self,
        context: AggregatedContext,
    ) -> AggregatedContext:
        """Compress context to fit token budget."""
        logger.info("Compressing context to fit token budget...")

        # Strategy 1: Summarize file contents
        for file_ctx in context.implementation.key_files:
            if len(file_ctx.content) > 1000:
                # Truncate large files, keep first/last portions
                file_ctx.summary = (
                    file_ctx.content[:500] + "\n... [truncated] ...\n" + file_ctx.content[-500:]
                )
                file_ctx.content = file_ctx.summary

        # Strategy 2: Reduce number of components
        if len(context.architecture.components) > 10:
            # Keep only top 10 most relevant
            context.architecture.components = context.architecture.components[:10]

        # Strategy 3: Reduce number of files
        if len(context.implementation.key_files) > 10:
            # Keep only highest relevance files
            sorted_files = sorted(
                context.implementation.key_files,
                key=lambda f: f.relevance_score,
                reverse=True,
            )
            context.implementation.key_files = sorted_files[:10]

        # Strategy 4: Remove similar features if still over budget
        if context.estimated_tokens > self.max_tokens:
            context.similar_features = context.similar_features[:3]

        return context
