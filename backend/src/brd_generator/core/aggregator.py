"""Context aggregation from multiple sources using agentic LLM approach.

This module uses the Copilot SDK to let the LLM dynamically:
1. Discover the Neo4j schema (labels, relationships, properties)
2. Write appropriate Cypher queries based on the schema
3. Gather context from the codebase without hardcoded assumptions
"""

from __future__ import annotations

import json
import re
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
from ..models.flow_context import (
    FeatureFlow,
    ImplementationMapping,
    TechnicalArchitectureView,
)
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from ..utils.logger import get_logger, get_progress_logger
from .enhanced_context import EnhancedContextRetriever
from .feature_flow import FeatureFlowService

logger = get_logger(__name__)
progress = get_progress_logger(__name__, "ContextAggregator")

# Relevance thresholds for score-based filtering (no hardcoded LIMIT)
DEFAULT_FULLTEXT_SCORE_THRESHOLD = 0.5  # Minimum fulltext relevance score (0-1 normalized)
DEFAULT_PAGERANK_WEIGHT = 0.3  # Weight for PageRank in combined score
DEFAULT_FULLTEXT_WEIGHT = 0.7  # Weight for fulltext score in combined score
MIN_COMPONENTS_TO_RETURN = 5  # Minimum components even if scores are low
MAX_COMPONENTS_CAP = 100  # Safety cap to prevent runaway queries

# Type for progress callback: async function that takes (step: str, detail: str)
ProgressCallback = Callable[[str, str], Awaitable[None]]

# Prompt for schema discovery
SCHEMA_DISCOVERY_PROMPT = """You have access to a Neo4j code graph database via MCP tools.

Your task is to discover the schema of this code graph. Use the available Neo4j MCP tools to:

1. First, get the database schema to understand what node labels and relationship types exist
2. Identify which labels represent code components (classes, functions, services, modules, etc.)
3. Identify which relationships represent dependencies, calls, imports, etc.

Return your findings as a JSON object with this structure:
```json
{
    "node_labels": ["Label1", "Label2"],
    "component_labels": ["Label1"],
    "relationship_types": ["REL1", "REL2"],
    "dependency_relationships": ["DEPENDS_ON", "IMPORTS"],
    "call_relationships": ["CALLS", "INVOKES"],
    "key_properties": {
        "Label1": ["name", "filePath", "description"]
    }
}
```

Use the neo4j tools to query the schema. Common queries:
- CALL db.labels() - get all node labels
- CALL db.relationshipTypes() - get all relationship types
- CALL db.schema.visualization() - get schema visualization

Return ONLY the JSON object, no other text."""

# Prompt for component discovery
COMPONENT_DISCOVERY_PROMPT = """You have access to a Neo4j code graph database via MCP tools.

Based on the schema discovery, the database has these relevant labels and relationships:
{schema_summary}

Your task is to find components relevant to this feature request:
"{feature_request}"

User specified these components (if any): {affected_components}

Write and execute Cypher queries to:
1. Find components matching the feature request keywords
2. Get their dependencies and dependents
3. Find any API endpoints or contracts
4. Identify data models involved

Return your findings as a JSON object:
```json
{{
    "components": [
        {{
            "name": "ComponentName",
            "type": "class/service/module/function",
            "path": "/path/to/file",
            "description": "what it does",
            "dependencies": ["Dep1", "Dep2"],
            "dependents": ["Dependent1"]
        }}
    ],
    "api_contracts": [
        {{
            "endpoint": "/api/path",
            "method": "GET/POST",
            "service": "ServiceName"
        }}
    ],
    "data_models": [
        {{
            "name": "ModelName",
            "fields": ["field1", "field2"]
        }}
    ],
    "queries_executed": ["query1", "query2"]
}}
```

Use the neo4j MCP tools to execute your queries. Be adaptive - if a query returns no results, try alternative approaches based on the actual schema.

Return ONLY the JSON object, no other text."""

# Prompt for file discovery
FILE_DISCOVERY_PROMPT = """You have access to a filesystem via MCP tools.

Based on the components found:
{components_summary}

Your task is to find and read the most relevant source files for understanding these components.

Use the filesystem MCP tools to:
1. Search for files related to each component
2. Read the key implementation files
3. Find configuration files

Return your findings as a JSON object:
```json
{{
    "key_files": [
        {{
            "path": "/path/to/file",
            "relevance": "why this file is relevant",
            "content_summary": "brief summary of content"
        }}
    ],
    "config_files": ["/path/to/config1", "/path/to/config2"],
    "patterns_observed": ["pattern1", "pattern2"]
}}
```

Limit to the 10 most relevant files. Return ONLY the JSON object, no other text."""


class ContextAggregator:
    """Aggregates context from Neo4j and Filesystem using agentic LLM approach.

    This class uses the Copilot SDK to let the LLM dynamically discover the
    code graph schema and write appropriate queries, rather than using
    hardcoded technology-specific queries.

    IMPROVED: Uses relevance-based retrieval instead of hardcoded limits:
    - Full-text search with relevance scores
    - PageRank-boosted ranking for structural importance
    - LLM concept extraction for semantic understanding
    - Score-based thresholds instead of fixed LIMIT
    """

    def __init__(
        self,
        neo4j_client: Neo4jMCPClient,
        filesystem_client: FilesystemMCPClient,
        copilot_session: Any = None,
        max_tokens: int = 100000,
        fulltext_score_threshold: float = DEFAULT_FULLTEXT_SCORE_THRESHOLD,
        pagerank_weight: float = DEFAULT_PAGERANK_WEIGHT,
        use_enhanced_retrieval: bool = True,  # NEW: Enable enhanced context retrieval
    ):
        """
        Initialize the context aggregator.

        Args:
            neo4j_client: Neo4j MCP client
            filesystem_client: Filesystem MCP client
            copilot_session: Copilot SDK session for agentic queries
            max_tokens: Maximum tokens for context (used for dynamic limiting)
            fulltext_score_threshold: Minimum relevance score to include component
            pagerank_weight: Weight for PageRank in combined relevance score
            use_enhanced_retrieval: If True, use ENHANCED context retrieval with
                                   compound term detection and graph-based traversal.
                                   This eliminates false positives from keyword matching.
        """
        self.neo4j = neo4j_client
        self.filesystem = filesystem_client
        self.copilot_session = copilot_session
        self.max_tokens = max_tokens
        self.fulltext_score_threshold = fulltext_score_threshold
        self.pagerank_weight = pagerank_weight
        self.fulltext_weight = 1.0 - pagerank_weight
        self.use_enhanced_retrieval = use_enhanced_retrieval

        # Cache for discovered schema
        self._schema_cache: Optional[dict[str, Any]] = None
        # Cache for fulltext index availability
        self._fulltext_available: Optional[bool] = None

        # Initialize enhanced context retriever
        self._enhanced_retriever: Optional[EnhancedContextRetriever] = None
        if use_enhanced_retrieval:
            self._enhanced_retriever = EnhancedContextRetriever(neo4j_client)
            logger.info("[AGGREGATOR] ENHANCED context retrieval ENABLED - using compound term detection + graph traversal")

        # Initialize feature flow service for end-to-end traceability
        self._flow_service: Optional[FeatureFlowService] = None
        try:
            self._flow_service = FeatureFlowService(neo4j_client)
            logger.info("[AGGREGATOR] Feature Flow service ENABLED - auto-generation of BRD Sections 7 & 9")
        except Exception as e:
            logger.warning(f"[AGGREGATOR] Feature Flow service initialization failed: {e}")

    def _calculate_dynamic_limit(self, estimated_tokens_per_item: int = 100) -> int:
        """Calculate dynamic limit based on token budget.

        Args:
            estimated_tokens_per_item: Estimated tokens per result item

        Returns:
            Dynamic limit that fits within token budget
        """
        # Reserve 30% of tokens for other content (prompts, file contents, etc.)
        available_tokens = int(self.max_tokens * 0.7)
        # Calculate how many items we can fit
        dynamic_limit = max(10, available_tokens // estimated_tokens_per_item)
        return dynamic_limit

    async def build_context(
        self,
        request: str,
        affected_components: Optional[list[str]] = None,
        include_similar: bool = True,
        progress_callback: Optional[ProgressCallback] = None,
        use_direct_mcp: bool = True,
    ) -> AggregatedContext:
        """
        Build aggregated context from all sources.

        Args:
            request: User's feature request
            affected_components: Known affected components
            include_similar: Search for similar features
            progress_callback: Optional callback for progress updates
            use_direct_mcp: If True, use local MCP clients directly (more reliable).
                           If False, try agentic approach via Copilot SDK (may not work
                           if SDK doesn't expose MCP tools properly).

        Returns:
            Aggregated context ready for LLM
        """
        progress.start_operation("build_context", f"Request: {request[:50]}...")

        # Helper to report progress
        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        await report("context", "Starting context aggregation...")

        # CONTEXT_FIRST approach: Use local MCP clients directly for reliability
        # This bypasses the Copilot SDK's tool invocation which may not work properly
        if use_direct_mcp:
            logger.info("[CONTEXT_FIRST] Using direct MCP client calls for context gathering")
            return await self._build_context_direct(
                request, affected_components, include_similar, progress_callback
            )
        # Agentic approach: Try to use Copilot SDK for tool invocation (experimental)
        elif self.copilot_session is not None:
            logger.info("[AGENTIC] Trying Copilot SDK for MCP tool invocation")
            return await self._build_context_agentic(
                request, affected_components, include_similar, progress_callback
            )
        else:
            # Fallback to basic approach if no Copilot session
            logger.warning("No Copilot session available, using basic context aggregation")
            return await self._build_context_basic(
                request, affected_components, include_similar, progress_callback
            )

    async def _build_context_direct(
        self,
        request: str,
        affected_components: Optional[list[str]],
        include_similar: bool,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AggregatedContext:
        """
        Build context using direct MCP client calls.

        This is the reliable CONTEXT_FIRST approach that:
        1. Queries Neo4j directly via the local MCP client
        2. Reads files directly via the filesystem MCP client
        3. Does NOT rely on Copilot SDK tool invocation (which may not work)

        ENHANCED MODE (when use_enhanced_retrieval=True):
        - Uses compound term detection to eliminate false positives
        - Finds entry points (Controllers) first, then traverses dependencies
        - Only returns components that are actually connected to the feature

        The gathered context is then passed to the LLM for BRD generation.
        """

        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        # Phase 1: Discover Neo4j schema directly
        progress.step("build_context", "Querying Neo4j schema", current=1, total=5)
        await report("neo4j", "Querying code graph schema...")
        schema = await self._discover_schema_direct()
        progress.info(f"Schema discovered: {len(schema.component_labels)} component types, {len(schema.dependency_relationships)} relationships")

        # Phase 2: Find components
        # Use ENHANCED retrieval if enabled (compound term detection + graph traversal)
        progress.step("build_context", "Finding relevant components", current=2, total=5)

        if self.use_enhanced_retrieval and self._enhanced_retriever and not affected_components:
            # ================================================================
            # ENHANCED CONTEXT RETRIEVAL
            # Uses compound term detection + graph-based traversal
            # ================================================================
            logger.info("=" * 60)
            logger.info("[AGGREGATOR] Using ENHANCED context retrieval")
            logger.info("[AGGREGATOR] - Compound term detection: ENABLED")
            logger.info("[AGGREGATOR] - Graph-based traversal: ENABLED")
            logger.info("[AGGREGATOR] - False positive elimination: ENABLED")
            logger.info("=" * 60)

            await report("neo4j", "Using ENHANCED retrieval (compound terms + graph traversal)...")

            # Get components using enhanced retrieval
            enhanced_components, entry_points, warnings = await self._enhanced_retriever.get_relevant_context(
                request
            )

            # Convert to ComponentInfo objects
            components = []
            for comp in enhanced_components:
                # Ensure description is never None (Pydantic validation)
                desc = comp.get("description")
                if desc is None:
                    desc = ""
                components.append(ComponentInfo(
                    name=comp.get("name", ""),
                    type=comp.get("type", "unknown"),
                    path=comp.get("path", ""),
                    description=desc,
                    dependencies=[],
                    dependents=[],
                ))

            # Log summary
            logger.info(f"[AGGREGATOR] ENHANCED retrieval found {len(components)} components")
            logger.info(f"[AGGREGATOR] Entry points identified: {len(entry_points)}")
            for w in warnings:
                logger.info(f"[AGGREGATOR] {w}")

            # Build architecture context
            architecture = ArchitectureContext(
                components=components,
                dependencies={},
                api_contracts=[],
                data_models=[],
            )

            progress.info(
                f"Architecture context retrieved (ENHANCED MODE)",
                components=len(architecture.components),
                entry_points=len(entry_points)
            )
        else:
            # ================================================================
            # STANDARD RETRIEVAL (keyword-based with fulltext search)
            # ================================================================
            if affected_components:
                logger.info("[AGGREGATOR] Using STANDARD retrieval (user specified components)")
            else:
                logger.info("[AGGREGATOR] Using STANDARD retrieval (enhanced disabled)")

            await report("neo4j", "Searching for relevant components...")
            architecture = await self._get_architecture_direct(
                request, affected_components, schema
            )
            progress.info(
                f"Architecture context retrieved",
                components=len(architecture.components),
                apis=len(architecture.api_contracts)
            )

        # Phase 3: Read source files directly
        progress.step("build_context", "Reading source files", current=3, total=5)
        await report("filesystem", "Reading relevant source files...")
        implementation = await self._get_implementation_direct(architecture)
        progress.info(
            f"Implementation context retrieved",
            key_files=len(implementation.key_files),
            configs=len(implementation.configs)
        )

        # Phase 4: Find similar features
        similar_features = []
        if include_similar:
            progress.step("build_context", "Finding similar features", current=4, total=5)
            await report("neo4j", "Searching for similar features...")
            similar_features = await self._find_similar_direct(request, schema)
            if similar_features:
                progress.info(f"Found {len(similar_features)} similar features")

        # Phase 5: Extract feature flows for BRD Sections 7 & 9
        feature_flows_data = []
        impl_mapping_md = ""
        tech_arch_md = ""
        if self._flow_service:
            progress.step("build_context", "Extracting feature flows", current=5, total=5)
            await report("flow", "Extracting end-to-end feature flows...")
            try:
                feature_flows_data, impl_mapping_md, tech_arch_md = await self._extract_feature_flows(
                    architecture, request, progress_callback
                )
                if feature_flows_data:
                    progress.info(f"Extracted {len(feature_flows_data)} feature flows for BRD auto-generation")
            except Exception as e:
                logger.warning(f"[AGGREGATOR] Feature flow extraction failed: {e}")

        # Build complete context with schema info and feature flows
        from ..models.context import SchemaInfo
        context = AggregatedContext(
            request=request,
            architecture=architecture,
            implementation=implementation,
            similar_features=similar_features,
            schema=schema,
            # Feature flow data for auto-generating BRD sections
            feature_flows=[flow.model_dump() for flow in feature_flows_data] if feature_flows_data else None,
            implementation_mapping=impl_mapping_md if impl_mapping_md else None,
            technical_architecture=tech_arch_md if tech_arch_md else None,
        )

        # Check token budget
        if context.estimated_tokens > self.max_tokens:
            progress.warning(
                f"Context exceeds token limit ({context.estimated_tokens} > {self.max_tokens}), compressing..."
            )
            context = await self._compress_context(context)

        flow_summary = f", {len(feature_flows_data)} flows" if feature_flows_data else ""
        progress.end_operation(
            "build_context",
            success=True,
            details=f"{len(architecture.components)} components, {len(implementation.key_files)} files{flow_summary}, ~{context.estimated_tokens} tokens"
        )
        return context

    async def _discover_schema_direct(self) -> "SchemaInfo":
        """Discover Neo4j schema using direct MCP client calls."""
        from ..models.context import SchemaInfo

        node_labels = []
        relationship_types = []

        try:
            # Query for node labels
            labels_result = await self.neo4j.query_code_structure("CALL db.labels() YIELD label RETURN label")
            if labels_result and "nodes" in labels_result:
                node_labels = [r.get("label", "") for r in labels_result.get("nodes", []) if r.get("label")]

            # Query for relationship types
            rels_result = await self.neo4j.query_code_structure("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
            if rels_result and "nodes" in rels_result:
                relationship_types = [r.get("relationshipType", "") for r in rels_result.get("nodes", []) if r.get("relationshipType")]

            logger.info(f"[SCHEMA-DIRECT] Found {len(node_labels)} labels: {node_labels[:10]}")
            logger.info(f"[SCHEMA-DIRECT] Found {len(relationship_types)} relationships: {relationship_types[:10]}")

        except Exception as e:
            logger.warning(f"[SCHEMA-DIRECT] Schema discovery failed: {e}")

        # Identify component-like labels DYNAMICALLY
        # Instead of hardcoding what TO include, we exclude known non-component labels
        # This ensures we search across ALL code component types (WebFlowDefinition, FlowState, JSPPage, etc.)
        excluded_labels = {
            # Infrastructure/metadata labels (not code components)
            'File', 'Directory', 'Repository', 'Package', 'PackageDeclaration',
            'ImportDeclaration', 'Commit', 'Branch', 'Tag',
            # Generic labels that would return too many results
            'Node', 'Entity',
        }

        # Include ALL labels except excluded ones - this makes search truly dynamic
        component_labels = [l for l in node_labels if l not in excluded_labels]

        if not component_labels:
            # Fallback only if no labels found at all
            component_labels = node_labels[:10] if node_labels else ["Class", "Function", "Module"]

        logger.info(f"[SCHEMA-DIRECT] Component labels for search: {component_labels}")

        # Identify dependency relationships
        dep_keywords = ['depends', 'import', 'use', 'call', 'extend', 'implement', 'reference']
        dep_rels = [r for r in relationship_types if any(kw in r.lower() for kw in dep_keywords)]
        if not dep_rels:
            dep_rels = relationship_types[:5] if relationship_types else ["DEPENDS_ON", "CALLS"]

        return SchemaInfo(
            node_labels=node_labels,
            component_labels=component_labels,
            relationship_types=relationship_types,
            dependency_relationships=dep_rels,
        )

    async def _check_fulltext_index_available(self) -> bool:
        """Check if full-text search index is available in Neo4j."""
        if self._fulltext_available is not None:
            return self._fulltext_available

        try:
            result = await self.neo4j.query_code_structure(
                "SHOW INDEXES YIELD name WHERE name = 'component_fulltext_search' RETURN name"
            )
            self._fulltext_available = len(result.get("nodes", [])) > 0
            if self._fulltext_available:
                logger.info("[FULLTEXT] Full-text search index available")
            else:
                logger.info("[FULLTEXT] Full-text search index not found, using fallback")
            return self._fulltext_available
        except Exception as e:
            logger.warning(f"[FULLTEXT] Could not check index availability: {e}")
            self._fulltext_available = False
            return False

    async def _extract_concepts_with_llm(self, feature_request: str) -> list[str]:
        """
        Use LLM to extract semantic concepts from feature request.

        This goes beyond simple word splitting to understand:
        - Technical synonyms (login = authentication = auth)
        - Related concepts (payment → billing, checkout, order)
        - Domain-specific terms

        Returns:
            List of concept keywords for searching
        """
        if not self.copilot_session:
            # Fallback to simple extraction
            return self._extract_keywords_simple(feature_request)

        prompt = f"""Extract search keywords from this feature request for finding relevant code components.

Feature request: "{feature_request}"

Instructions:
1. Extract the main technical concepts (nouns, verbs related to functionality)
2. Add common synonyms and related terms (e.g., "login" → also search "auth", "authentication")
3. Include both business terms and technical terms
4. Return 5-15 keywords, prioritized by relevance

Return ONLY a JSON array of keywords, no explanation:
["keyword1", "keyword2", "keyword3"]"""

        try:
            response = await self._send_to_copilot(prompt)
            concepts = self._extract_json_from_response(response)
            if isinstance(concepts, list) and len(concepts) > 0:
                logger.info(f"[LLM-CONCEPTS] Extracted {len(concepts)} concepts: {concepts[:10]}")
                return concepts[:15]  # Cap at 15 concepts
        except Exception as e:
            logger.warning(f"[LLM-CONCEPTS] LLM concept extraction failed: {e}")

        # Fallback to simple extraction
        return self._extract_keywords_simple(feature_request)

    def _extract_keywords_simple(self, text: str) -> list[str]:
        """Simple keyword extraction fallback."""
        # Extract meaningful words (length > 3, not common stopwords)
        stopwords = {'with', 'from', 'that', 'this', 'have', 'will', 'should', 'would', 'could', 'need', 'want'}
        words = [w.lower() for w in text.split() if len(w) > 3 and w.lower() not in stopwords]
        return list(dict.fromkeys(words))[:10]  # Dedupe and limit

    async def _search_components_fulltext(
        self,
        keywords: list[str],
        schema: "SchemaInfo",
        min_score: float = 0.3,
    ) -> list[tuple[ComponentInfo, float]]:
        """
        Search components using Neo4j full-text search with relevance scores.

        Returns components with their relevance scores for threshold-based filtering.
        """
        if not keywords:
            return []

        # Build search query string (Lucene syntax)
        search_terms = " OR ".join(keywords)

        try:
            # Use full-text index with score
            query = f"""
                CALL db.index.fulltext.queryNodes('component_fulltext_search', $searchTerms)
                YIELD node, score
                WHERE score >= $minScore
                OPTIONAL MATCH (node)
                WHERE node.pageRank IS NOT NULL
                WITH node, score, COALESCE(node.pageRank, 0.1) AS pageRank
                WITH node,
                     score AS fulltextScore,
                     pageRank,
                     (score * $fulltextWeight + pageRank * $pagerankWeight) AS combinedScore
                RETURN node.name AS name,
                       labels(node)[0] AS type,
                       node.filePath AS path,
                       node.description AS description,
                       fulltextScore,
                       pageRank,
                       combinedScore
                ORDER BY combinedScore DESC
            """

            result = await self.neo4j.query_code_structure(query, {
                "searchTerms": search_terms,
                "minScore": min_score,
                "fulltextWeight": self.fulltext_weight,
                "pagerankWeight": self.pagerank_weight,
            })

            components = []
            for node in result.get("nodes", []):
                name = node.get("name", "")
                if name:
                    comp = ComponentInfo(
                        name=name,
                        type=node.get("type", "component"),
                        path=node.get("path") or "",
                        description=node.get("description") or "",
                        dependencies=[],
                        dependents=[],
                    )
                    score = node.get("combinedScore", 0.5)
                    components.append((comp, score))

            logger.info(f"[FULLTEXT-SEARCH] Found {len(components)} components with scores >= {min_score}")
            return components

        except Exception as e:
            logger.warning(f"[FULLTEXT-SEARCH] Full-text search failed: {e}")
            return []

    async def _search_components_fallback(
        self,
        keywords: list[str],
        schema: "SchemaInfo",
    ) -> list[tuple[ComponentInfo, float]]:
        """
        Fallback search using CONTAINS with PageRank boosting.

        Used when full-text index is not available.
        """
        if not keywords:
            return []

        # Build label filter
        label_filter = " OR ".join([f"n:{label}" for label in schema.component_labels])
        if not label_filter:
            label_filter = "n:Class OR n:Function OR n:Module"

        # Build keyword conditions
        keyword_conditions = " OR ".join([f"toLower(n.name) CONTAINS '{kw}'" for kw in keywords])

        query = f"""
            MATCH (n)
            WHERE ({label_filter}) AND ({keyword_conditions})
            WITH n, COALESCE(n.pageRank, 0.1) AS pageRank
            RETURN n.name AS name,
                   labels(n)[0] AS type,
                   n.filePath AS path,
                   n.description AS description,
                   pageRank
            ORDER BY pageRank DESC
            LIMIT {MAX_COMPONENTS_CAP}
        """

        try:
            result = await self.neo4j.query_code_structure(query)
            components = []
            for node in result.get("nodes", []):
                name = node.get("name", "")
                if name:
                    comp = ComponentInfo(
                        name=name,
                        type=node.get("type", "component"),
                        path=node.get("path") or "",
                        description=node.get("description") or "",
                        dependencies=[],
                        dependents=[],
                    )
                    # Use PageRank as score (normalized)
                    score = min(1.0, node.get("pageRank", 0.1) + 0.5)
                    components.append((comp, score))

            logger.info(f"[FALLBACK-SEARCH] Found {len(components)} components using CONTAINS")
            return components

        except Exception as e:
            logger.warning(f"[FALLBACK-SEARCH] Fallback search failed: {e}")
            return []

    def _apply_relevance_threshold(
        self,
        scored_components: list[tuple[ComponentInfo, float]],
        min_score: float = None,
    ) -> list[ComponentInfo]:
        """
        Apply relevance threshold to filter components.

        Uses score-based filtering instead of hardcoded LIMIT:
        - Components above threshold are included
        - Ensures minimum number of components
        - Caps at maximum to prevent token overflow
        """
        if min_score is None:
            min_score = self.fulltext_score_threshold

        # Sort by score descending
        sorted_components = sorted(scored_components, key=lambda x: x[1], reverse=True)

        # Find natural cutoff using elbow detection
        # or use threshold, whichever gives more components
        above_threshold = [(c, s) for c, s in sorted_components if s >= min_score]

        if len(above_threshold) >= MIN_COMPONENTS_TO_RETURN:
            # Enough components above threshold
            selected = above_threshold
        else:
            # Take at least MIN_COMPONENTS_TO_RETURN
            selected = sorted_components[:max(MIN_COMPONENTS_TO_RETURN, len(above_threshold))]

        # Apply maximum cap (for token budget safety)
        selected = selected[:MAX_COMPONENTS_CAP]

        # Log score distribution
        if selected:
            scores = [s for _, s in selected]
            logger.info(
                f"[RELEVANCE] Selected {len(selected)} components, "
                f"score range: {min(scores):.3f} - {max(scores):.3f}, "
                f"threshold: {min_score}"
            )

        return [comp for comp, _ in selected]

    async def _get_architecture_direct(
        self,
        request: str,
        affected_components: Optional[list[str]],
        schema: "SchemaInfo",
    ) -> ArchitectureContext:
        """Get architecture using direct Neo4j queries with relevance-based retrieval.

        IMPROVED: Uses full-text search + PageRank instead of hardcoded LIMIT:
        - Full-text search for semantic matching (when available)
        - PageRank for structural importance
        - Score-based thresholds instead of fixed limits
        - LLM concept extraction for better keyword discovery
        """
        components: list[ComponentInfo] = []
        dependencies: dict[str, list[str]] = {}
        api_contracts = []

        try:
            logger.info(f"[ARCH-DIRECT] Searching across {len(schema.component_labels)} label types")

            # Step 1: Extract concepts using LLM (or fallback to simple extraction)
            if affected_components:
                # User specified components - search for those directly
                keywords = affected_components
                logger.info(f"[ARCH-DIRECT] Using user-specified components: {keywords}")
            else:
                # Extract semantic concepts from request
                keywords = await self._extract_concepts_with_llm(request)
                logger.info(f"[ARCH-DIRECT] Extracted concepts: {keywords}")

            # Step 2: Search using full-text index (with fallback)
            fulltext_available = await self._check_fulltext_index_available()

            scored_components: list[tuple[ComponentInfo, float]] = []

            if fulltext_available and not affected_components:
                # Use full-text search with relevance scores
                scored_components = await self._search_components_fulltext(
                    keywords, schema, min_score=0.2
                )
            else:
                # Fallback to CONTAINS with PageRank boosting
                scored_components = await self._search_components_fallback(
                    keywords, schema
                )

            # Step 3: Apply relevance threshold (no hardcoded LIMIT)
            components = self._apply_relevance_threshold(scored_components)

            logger.info(f"[ARCH-DIRECT] Found {len(components)} relevant components (threshold-based)")

            # Get dependencies for found components using graph expansion
            # No hardcoded limit - include dependencies based on relevance
            if components and schema.dependency_relationships:
                rel_filter = " OR ".join([f"type(r) = '{rel}'" for rel in schema.dependency_relationships])
                comp_names = [c.name for c in components[:50]]  # Safety: limit source components
                name_filter = " OR ".join([f"c1.name = '{name}'" for name in comp_names])

                # Query dependencies with PageRank ordering (most important dependencies first)
                dep_query = f"""
                    MATCH (c1)-[r]->(c2)
                    WHERE ({name_filter}) AND ({rel_filter})
                    WITH c1.name AS source, type(r) AS rel, c2.name AS target,
                         COALESCE(c2.pageRank, 0.1) AS targetRank
                    RETURN source, rel, target, targetRank
                    ORDER BY targetRank DESC
                """

                dep_result = await self.neo4j.query_code_structure(dep_query)
                for dep in dep_result.get("nodes", []):
                    source = dep.get("source", "")
                    target = dep.get("target", "")
                    if source and target:
                        if source not in dependencies:
                            dependencies[source] = []
                        if target not in dependencies[source]:
                            dependencies[source].append(target)

                # Update component dependencies
                for comp in components:
                    comp.dependencies = dependencies.get(comp.name, [])

            # Try to find API endpoints
            api_labels = [l for l in schema.node_labels if any(kw in l.lower() for kw in ['endpoint', 'api', 'route', 'controller'])]
            if api_labels:
                api_limit = self._calculate_dynamic_limit(estimated_tokens_per_item=100)
                api_query = f"""
                    MATCH (n:{api_labels[0]})
                    RETURN n.path as endpoint, n.method as method, n.name as name
                    LIMIT {api_limit}
                """
                try:
                    api_result = await self.neo4j.query_code_structure(api_query)
                    for api in api_result.get("nodes", []):
                        if api.get("endpoint"):
                            api_contracts.append(APIContract(
                                endpoint=api.get("endpoint", ""),
                                method=api.get("method", "GET"),
                                parameters={},
                                service=api.get("name", ""),
                            ))
                except Exception as e:
                    logger.debug(f"[ARCH-DIRECT] API query failed: {e}")

        except Exception as e:
            logger.warning(f"[ARCH-DIRECT] Architecture query failed: {e}")

        return ArchitectureContext(
            components=components,
            dependencies=dependencies,
            api_contracts=api_contracts,
            data_models=[],
        )

    async def _get_implementation_direct(
        self,
        architecture: ArchitectureContext,
    ) -> ImplementationContext:
        """Get implementation using direct filesystem reads."""
        key_files: list[FileContext] = []
        configs: dict[str, Any] = {}
        patterns: list[str] = []

        # Read files for components with paths
        files_read = 0
        for component in architecture.components[:15]:
            if component.path and files_read < 10:
                try:
                    content = await self.filesystem.read_file(component.path)
                    if content:
                        key_files.append(FileContext(
                            path=component.path,
                            content=content[:8000] if len(content) > 8000 else content,
                            relevance=f"Source for {component.name}",
                            relevance_score=0.9,
                        ))
                        files_read += 1
                        logger.debug(f"[IMPL-DIRECT] Read: {component.path} ({len(content)} chars)")
                except Exception as e:
                    logger.debug(f"[IMPL-DIRECT] Could not read {component.path}: {e}")

        logger.info(f"[IMPL-DIRECT] Read {len(key_files)} source files")

        # Try to find and read config files
        config_patterns = ["application.yml", "application.yaml", "config.json", "settings.py", "package.json"]
        for pattern in config_patterns:
            try:
                files = await self.filesystem.search_files(f"**/{pattern}")
                if isinstance(files, list):
                    for f in files[:2]:
                        path = f if isinstance(f, str) else f.get("path", "")
                        if path:
                            configs[path] = "present"
            except Exception:
                pass

        return ImplementationContext(
            key_files=key_files,
            patterns=patterns,
            configs=configs,
        )

    async def _find_similar_direct(
        self,
        request: str,
        schema: "SchemaInfo",
    ) -> list[str]:
        """Find similar features using direct queries."""
        try:
            # Extract keywords - use all meaningful keywords (no artificial limit)
            keywords = [word.lower() for word in request.split() if len(word) > 3]
            if not keywords:
                return []

            # Build label filter - use ALL component labels for comprehensive search
            label_filter = " OR ".join([f"n:{label}" for label in schema.component_labels])
            if not label_filter:
                return []

            # Search for similar-named components with dynamic limit
            similar_limit = self._calculate_dynamic_limit(estimated_tokens_per_item=30)
            keyword_filter = " OR ".join([f"toLower(n.name) CONTAINS '{kw}'" for kw in keywords])
            query = f"""
                MATCH (n)
                WHERE ({label_filter}) AND ({keyword_filter})
                RETURN DISTINCT n.name as name
                LIMIT {similar_limit}
            """

            result = await self.neo4j.query_code_structure(query)
            similar = [r.get("name", "") for r in result.get("nodes", []) if r.get("name")]
            return similar

        except Exception as e:
            logger.debug(f"[SIMILAR-DIRECT] Search failed: {e}")
            return []

    async def _build_context_agentic(
        self,
        request: str,
        affected_components: Optional[list[str]],
        include_similar: bool,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AggregatedContext:
        """Build context using agentic LLM approach via Copilot SDK (experimental)."""

        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        # Phase 1: Discover Neo4j schema
        progress.step("build_context", "Discovering code graph schema", current=1, total=4)
        await report("neo4j", "LLM discovering code graph schema...")
        schema = await self._discover_schema_agentic(progress_callback)
        progress.info(f"Schema discovered: {len(schema.get('node_labels', []))} labels, {len(schema.get('relationship_types', []))} relationships")

        # Phase 2: Find components using agentic approach
        progress.step("build_context", "Finding relevant components", current=2, total=4)
        await report("neo4j", "LLM searching for relevant components...")
        architecture = await self._get_architecture_agentic(
            request, affected_components, schema, progress_callback
        )
        progress.info(
            f"Architecture context retrieved",
            components=len(architecture.components),
            apis=len(architecture.api_contracts)
        )

        # Phase 3: Get implementation details using agentic approach
        progress.step("build_context", "Reading source files", current=3, total=4)
        await report("filesystem", "LLM finding relevant source files...")
        implementation = await self._get_implementation_agentic(
            architecture, progress_callback
        )
        progress.info(
            f"Implementation context retrieved",
            key_files=len(implementation.key_files),
            configs=len(implementation.configs)
        )

        # Phase 4: Find similar features
        similar_features = []
        if include_similar:
            progress.step("build_context", "Finding similar features", current=4, total=4)
            await report("neo4j", "LLM searching for similar features...")
            similar_features = await self._find_similar_agentic(request, schema, progress_callback)
            if similar_features:
                progress.info(f"Found {len(similar_features)} similar features")

        # Build complete context
        context = AggregatedContext(
            request=request,
            architecture=architecture,
            implementation=implementation,
            similar_features=similar_features,
        )

        # Check token budget
        if context.estimated_tokens > self.max_tokens:
            progress.warning(
                f"Context exceeds token limit ({context.estimated_tokens} > {self.max_tokens}), compressing..."
            )
            context = await self._compress_context(context)

        progress.end_operation(
            "build_context",
            success=True,
            details=f"{len(architecture.components)} components, {len(implementation.key_files)} files, ~{context.estimated_tokens} tokens"
        )
        return context

    async def _discover_schema_agentic(
        self,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> dict[str, Any]:
        """Use LLM to discover Neo4j schema dynamically."""

        # Return cached schema if available
        if self._schema_cache is not None:
            return self._schema_cache

        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        try:
            await report("neo4j", "Querying database schema...")

            # Send prompt to Copilot SDK
            response = await self._send_to_copilot(SCHEMA_DISCOVERY_PROMPT)

            # Parse JSON response
            schema = self._extract_json_from_response(response)

            if schema:
                self._schema_cache = schema
                await report("neo4j", f"Found {len(schema.get('node_labels', []))} node labels")
                return schema
            else:
                logger.warning("Could not parse schema from LLM response, using fallback")
                return self._get_fallback_schema()

        except Exception as e:
            logger.warning(f"Schema discovery failed: {e}, using fallback")
            return self._get_fallback_schema()

    async def _get_architecture_agentic(
        self,
        request: str,
        affected_components: Optional[list[str]],
        schema: dict[str, Any],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ArchitectureContext:
        """Use LLM to find components and architecture dynamically."""

        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        try:
            # Build schema summary for the prompt
            schema_summary = self._format_schema_summary(schema)

            # Format the prompt
            prompt = COMPONENT_DISCOVERY_PROMPT.format(
                schema_summary=schema_summary,
                feature_request=request,
                affected_components=affected_components or "None specified",
            )

            await report("neo4j", "LLM writing and executing Cypher queries...")

            # Send to Copilot SDK
            response = await self._send_to_copilot(prompt)

            # Parse response
            result = self._extract_json_from_response(response)

            if result:
                return self._parse_architecture_result(result)
            else:
                logger.warning("Could not parse architecture from LLM response")
                return ArchitectureContext(
                    components=[],
                    dependencies={},
                    api_contracts=[],
                    data_models=[],
                )

        except Exception as e:
            logger.warning(f"Architecture discovery failed: {e}")
            return ArchitectureContext(
                components=[],
                dependencies={},
                api_contracts=[],
                data_models=[],
            )

    async def _get_implementation_agentic(
        self,
        architecture: ArchitectureContext,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ImplementationContext:
        """Use LLM to find relevant files dynamically."""

        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        try:
            # Build components summary
            components_summary = self._format_components_summary(architecture)

            # Format the prompt
            prompt = FILE_DISCOVERY_PROMPT.format(
                components_summary=components_summary,
            )

            await report("filesystem", "LLM searching for relevant files...")

            # Send to Copilot SDK
            response = await self._send_to_copilot(prompt)

            # Parse response
            result = self._extract_json_from_response(response)

            if result:
                return self._parse_implementation_result(result)
            else:
                logger.warning("Could not parse implementation from LLM response")
                return ImplementationContext(
                    key_files=[],
                    patterns=[],
                    configs={},
                )

        except Exception as e:
            logger.warning(f"Implementation discovery failed: {e}")
            return ImplementationContext(
                key_files=[],
                patterns=[],
                configs={},
            )

    async def _find_similar_agentic(
        self,
        request: str,
        schema: dict[str, Any],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> list[str]:
        """Use LLM to find similar features dynamically."""

        try:
            prompt = f"""You have access to a Neo4j code graph database.

Schema summary:
{self._format_schema_summary(schema)}

Find existing features or implementations similar to: "{request}"

Use the neo4j MCP tools to search for similar code patterns, features, or components.

Return a JSON array of similar feature names:
["feature1", "feature2", "feature3"]

Return ONLY the JSON array, no other text."""

            response = await self._send_to_copilot(prompt)
            result = self._extract_json_from_response(response)

            if isinstance(result, list):
                return result[:5]
            return []

        except Exception as e:
            logger.debug(f"Similar features search failed: {e}")
            return []

    async def _send_to_copilot(self, prompt: str) -> str:
        """Send a prompt to Copilot SDK and get response."""
        if self.copilot_session is None:
            raise ValueError("No Copilot session available")

        # Log the prompt being sent
        logger.info(f"[COPILOT-PROMPT] Sending prompt to Copilot SDK ({len(prompt)} chars)")
        logger.info(f"[COPILOT-PROMPT] Prompt preview: {prompt[:500]}...")

        try:
            # Build message options - SDK uses this format
            message_options = {"prompt": prompt}

            # Use send_and_wait method (correct SDK API)
            if hasattr(self.copilot_session, 'send_and_wait'):
                logger.info("[COPILOT-SDK] Using send_and_wait method")
                event = await self.copilot_session.send_and_wait(message_options, timeout=120)

                if event:
                    # Extract text content from event
                    response_text = self._extract_text_from_event(event)
                    logger.info(f"[COPILOT-RESPONSE] Received response ({len(response_text)} chars)")
                    logger.info(f"[COPILOT-RESPONSE] Response preview: {response_text[:500]}...")
                    return response_text
                else:
                    logger.warning("[COPILOT-SDK] send_and_wait returned None")
                    return ""

            elif hasattr(self.copilot_session, 'send'):
                logger.info("[COPILOT-SDK] Using send method (fallback)")
                message_id = await self.copilot_session.send(message_options)
                logger.info(f"[COPILOT-SDK] Message sent, ID: {message_id}")
                # Would need to poll for response
                return ""

            else:
                logger.error("[COPILOT-SDK] No suitable send method found on session")
                return ""

        except Exception as e:
            logger.error(f"[COPILOT-ERROR] Copilot SDK call failed: {e}")
            raise

    def _extract_text_from_event(self, event: Any) -> str:
        """Extract text content from a Copilot SDK event."""
        try:
            # Try various event formats
            if hasattr(event, 'data'):
                data = event.data
                if hasattr(data, 'message') and hasattr(data.message, 'content'):
                    return str(data.message.content)
                if hasattr(data, 'content'):
                    return str(data.content)
                if hasattr(data, 'text'):
                    return str(data.text)

            if hasattr(event, 'content'):
                return str(event.content)
            if hasattr(event, 'text'):
                return str(event.text)

            # Last resort
            return str(event)

        except Exception as e:
            logger.warning(f"[COPILOT-SDK] Error extracting text from event: {e}")
            return ""

    def _extract_json_from_response(self, response: str) -> Optional[Any]:
        """Extract JSON from LLM response, handling markdown code blocks."""
        if not response:
            return None

        # Try to find JSON in code blocks first
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'\{[\s\S]*\}',
            r'\[[\s\S]*\]',
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, response)
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue

        # Try parsing the entire response as JSON
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            return None

    def _format_schema_summary(self, schema: dict[str, Any]) -> str:
        """Format schema for prompt inclusion."""
        lines = []

        if schema.get("component_labels"):
            lines.append(f"Component labels: {', '.join(schema['component_labels'])}")
        elif schema.get("node_labels"):
            lines.append(f"Node labels: {', '.join(schema['node_labels'][:10])}")

        if schema.get("dependency_relationships"):
            lines.append(f"Dependency relationships: {', '.join(schema['dependency_relationships'])}")
        elif schema.get("relationship_types"):
            lines.append(f"Relationship types: {', '.join(schema['relationship_types'][:10])}")

        if schema.get("key_properties"):
            props = []
            for label, properties in list(schema["key_properties"].items())[:5]:
                props.append(f"{label}: {properties}")
            lines.append(f"Key properties: {'; '.join(props)}")

        return "\n".join(lines) if lines else "Schema information not available"

    def _format_components_summary(self, architecture: ArchitectureContext) -> str:
        """Format components for prompt inclusion."""
        if not architecture.components:
            return "No components identified yet"

        lines = []
        for comp in architecture.components[:10]:
            line = f"- {comp.name} ({comp.type})"
            if comp.path:
                line += f" at {comp.path}"
            lines.append(line)

        return "\n".join(lines)

    def _parse_architecture_result(self, result: dict[str, Any]) -> ArchitectureContext:
        """Parse LLM result into ArchitectureContext."""
        components = []
        dependencies = {}
        api_contracts = []
        data_models = []

        # Parse components
        for comp in result.get("components", []):
            component = ComponentInfo(
                name=comp.get("name", "unknown"),
                type=comp.get("type", "component"),
                path=comp.get("path", ""),
                description=comp.get("description", ""),
                dependencies=comp.get("dependencies", []),
                dependents=comp.get("dependents", []),
            )
            components.append(component)
            dependencies[component.name] = component.dependencies

        # Parse API contracts
        for api in result.get("api_contracts", []):
            api_contracts.append(APIContract(
                endpoint=api.get("endpoint", ""),
                method=api.get("method", "GET"),
                parameters=api.get("parameters", {}),
                service=api.get("service", ""),
            ))

        # Parse data models
        for model in result.get("data_models", []):
            data_models.append(DataModel(
                name=model.get("name", ""),
                fields=model.get("fields", []),
            ))

        return ArchitectureContext(
            components=components,
            dependencies=dependencies,
            api_contracts=api_contracts,
            data_models=data_models,
        )

    def _parse_implementation_result(self, result: dict[str, Any]) -> ImplementationContext:
        """Parse LLM result into ImplementationContext."""
        key_files = []
        configs = {}
        patterns = []

        # Parse key files
        for file_info in result.get("key_files", []):
            key_files.append(FileContext(
                path=file_info.get("path", ""),
                content=file_info.get("content_summary", ""),
                relevance_score=0.8,
            ))

        # Parse config files
        for config_path in result.get("config_files", []):
            configs[config_path] = "present"

        # Parse patterns
        patterns = result.get("patterns_observed", [])

        return ImplementationContext(
            key_files=key_files,
            patterns=patterns,
            configs=configs,
        )

    def _get_fallback_schema(self) -> dict[str, Any]:
        """Get a generic fallback schema when discovery fails."""
        return {
            "node_labels": ["Class", "Function", "Module", "File"],
            "component_labels": ["Class", "Function", "Module"],
            "relationship_types": ["CALLS", "IMPORTS", "CONTAINS", "DEPENDS_ON"],
            "dependency_relationships": ["DEPENDS_ON", "IMPORTS"],
            "call_relationships": ["CALLS"],
            "key_properties": {
                "Class": ["name", "filePath"],
                "Function": ["name", "filePath"],
                "Module": ["name", "path"],
            }
        }

    # =========================================================================
    # Basic (non-agentic) fallback methods
    # =========================================================================

    async def _build_context_basic(
        self,
        request: str,
        affected_components: Optional[list[str]],
        include_similar: bool,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AggregatedContext:
        """Build context using basic approach (fallback when no Copilot session)."""

        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        await report("context", "Using basic context aggregation (no LLM)...")

        # Phase 1: Try to get schema from Neo4j directly
        progress.step("build_context", "Querying Neo4j", current=1, total=3)
        await report("neo4j", "Querying code graph...")
        architecture = await self._get_architecture_basic(request, affected_components, progress_callback)

        # Phase 2: Get implementation details
        progress.step("build_context", "Reading source files", current=2, total=3)
        await report("filesystem", "Reading source files...")
        implementation = await self._get_implementation_basic(architecture, progress_callback)

        # Phase 3: Find similar (skip if no components found)
        similar_features: list[str] = []
        if include_similar and architecture.components:
            progress.step("build_context", "Finding similar features", current=3, total=3)
            similar_features = await self._find_similar_basic(request)

        context = AggregatedContext(
            request=request,
            architecture=architecture,
            implementation=implementation,
            similar_features=similar_features,
        )

        if context.estimated_tokens > self.max_tokens:
            context = await self._compress_context(context)

        progress.end_operation("build_context", success=True)
        return context

    async def _get_architecture_basic(
        self,
        request: str,
        affected_components: Optional[list[str]],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ArchitectureContext:
        """Get architecture using basic Neo4j queries (schema-agnostic)."""
        components = []
        dependencies: dict[str, list[str]] = {}

        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        try:
            # First, discover what labels exist
            await report("neo4j", "Discovering available labels...")
            labels_result = await self.neo4j.query_code_structure("CALL db.labels()")
            available_labels = [r.get("label", "") for r in labels_result.get("nodes", [])]

            if not available_labels:
                logger.warning("No labels found in Neo4j")
                return ArchitectureContext(components=[], dependencies={}, api_contracts=[], data_models=[])

            await report("neo4j", f"Found labels: {available_labels[:5]}...")

            # Build a dynamic query based on available labels
            # EXCLUDE known non-component labels instead of hardcoding what to include
            # This ensures WebFlowDefinition, FlowState, JSPPage, etc. are searched
            excluded_labels = {
                'File', 'Directory', 'Repository', 'Package', 'PackageDeclaration',
                'ImportDeclaration', 'Commit', 'Branch', 'Tag', 'Node', 'Entity',
            }
            component_labels = [l for l in available_labels if l not in excluded_labels]

            if not component_labels:
                component_labels = available_labels[:10]  # Fallback to first 10 labels

            # Query for components - use ALL component labels, not just first 5
            label_filter = " OR ".join([f"n:{label}" for label in component_labels])
            logger.info(f"[AGENTIC] Searching across {len(component_labels)} label types")

            # Calculate dynamic limit based on token budget
            component_limit = self._calculate_dynamic_limit(estimated_tokens_per_item=150)

            if affected_components:
                # Search for specific components
                name_filter = " OR ".join([f"toLower(n.name) CONTAINS toLower('{comp}')" for comp in affected_components])
                query = f"""
                    MATCH (n)
                    WHERE ({label_filter}) AND ({name_filter})
                    RETURN n.name as name, labels(n)[0] as type, n.filePath as path
                    LIMIT {component_limit}
                """
            else:
                # Extract keywords from request - use all meaningful keywords
                keywords = [word.lower() for word in request.split() if len(word) > 3]
                if keywords:
                    keyword_filter = " OR ".join([f"toLower(n.name) CONTAINS '{kw}'" for kw in keywords])
                    query = f"""
                        MATCH (n)
                        WHERE ({label_filter}) AND ({keyword_filter})
                        RETURN n.name as name, labels(n)[0] as type, n.filePath as path
                        LIMIT {component_limit}
                    """
                else:
                    query = f"""
                        MATCH (n)
                        WHERE {label_filter}
                        RETURN n.name as name, labels(n)[0] as type, n.filePath as path
                        LIMIT {component_limit}
                    """

            await report("neo4j", "Executing component query...")
            result = await self.neo4j.query_code_structure(query)

            for node in result.get("nodes", []):
                components.append(ComponentInfo(
                    name=node.get("name", "unknown"),
                    type=node.get("type", "component"),
                    path=node.get("path", ""),
                    dependencies=[],
                    dependents=[],
                ))

            progress.info(f"Found {len(components)} components")

        except Exception as e:
            logger.warning(f"Basic architecture query failed: {e}")

        return ArchitectureContext(
            components=components,
            dependencies=dependencies,
            api_contracts=[],
            data_models=[],
        )

    async def _get_implementation_basic(
        self,
        architecture: ArchitectureContext,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ImplementationContext:
        """Get implementation using basic filesystem queries."""
        key_files: list[FileContext] = []
        configs: dict[str, Any] = {}

        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        # Read files for components with paths - limit based on token budget
        max_files_to_read = self._calculate_dynamic_limit(estimated_tokens_per_item=1000)
        for component in architecture.components[:max_files_to_read]:
            if component.path:
                try:
                    await report("filesystem", f"Reading: {component.path.split('/')[-1]}")
                    content = await self.filesystem.read_file(component.path)
                    key_files.append(FileContext(
                        path=component.path,
                        content=content[:5000] if content else "",
                        relevance_score=0.8,
                    ))
                except Exception as e:
                    logger.debug(f"Could not read {component.path}: {e}")

        # Try to find config files
        config_patterns = ["**/config/*", "**/*.yaml", "**/*.json"]
        for pattern in config_patterns:
            try:
                files = await self.filesystem.search_files(pattern)
                if isinstance(files, list):
                    for f in files[:2]:
                        path = f if isinstance(f, str) else f.get("path", "")
                        if path:
                            configs[path] = "present"
            except Exception:
                pass

        return ImplementationContext(
            key_files=key_files,
            patterns=[],
            configs=configs,
        )

    async def _find_similar_basic(self, request: str) -> list[str]:
        """Find similar features using basic search."""
        try:
            results = await self.neo4j.search_similar_features(request, limit=5)
            return [r.get("name", "") for r in results if r.get("name")]
        except Exception as e:
            logger.debug(f"Similar features search failed: {e}")
            return []

    async def _extract_feature_flows(
        self,
        architecture: ArchitectureContext,
        request: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> tuple[list[FeatureFlow], str, str]:
        """
        Extract feature flows from entry points for BRD auto-generation.

        This method:
        1. Identifies entry points (JSPs, WebFlows, Controllers) from architecture
        2. Traces each entry point through to database
        3. Generates implementation mapping table (Section 9)
        4. Generates technical architecture markdown (Section 7)

        Args:
            architecture: Architecture context with components
            request: Original feature request for naming
            progress_callback: Optional progress callback

        Returns:
            Tuple of (feature_flows, implementation_mapping_markdown, technical_architecture_markdown)
        """
        if not self._flow_service:
            logger.info("[FLOW-EXTRACT] Flow service not available, skipping feature flow extraction")
            return [], "", ""

        async def report(step: str, detail: str) -> None:
            if progress_callback:
                await progress_callback(step, detail)

        feature_flows: list[FeatureFlow] = []
        entry_points_found: list[str] = []

        await report("flow", "Identifying entry points for feature flow extraction...")

        # Step 1: Identify entry points from architecture components
        # Entry points are JSPs, WebFlows, or Controller classes
        entry_point_types = {'JSPPage', 'WebFlowDefinition', 'SpringController', 'JavaClass'}
        entry_point_keywords = {'action', 'controller', 'flow', 'jsp', 'view'}

        for comp in architecture.components:
            comp_type = comp.type.lower() if comp.type else ""
            comp_name = comp.name.lower() if comp.name else ""

            is_entry_point = (
                comp.type in entry_point_types or
                any(kw in comp_type for kw in entry_point_keywords) or
                any(kw in comp_name for kw in entry_point_keywords) or
                comp.path.endswith('.jsp') if comp.path else False
            )

            if is_entry_point:
                entry_points_found.append(comp.name)

        # Also try to find entry points using flow service search
        if not entry_points_found:
            try:
                # Extract keywords from request for entry point search
                keywords = [w for w in request.split() if len(w) > 3]
                for keyword in keywords[:3]:  # Limit to first 3 keywords
                    found = await self._flow_service.find_entry_points(keyword, limit=5)
                    for ep in found:
                        if ep.get("name") and ep["name"] not in entry_points_found:
                            entry_points_found.append(ep["name"])
            except Exception as e:
                logger.debug(f"[FLOW-EXTRACT] Entry point search failed: {e}")

        logger.info(f"[FLOW-EXTRACT] Found {len(entry_points_found)} potential entry points: {entry_points_found[:10]}")

        if not entry_points_found:
            logger.info("[FLOW-EXTRACT] No entry points found, skipping flow extraction")
            return [], "", ""

        # Step 2: Trace each entry point (limit to avoid excessive queries)
        max_flows = 5
        await report("flow", f"Tracing {min(len(entry_points_found), max_flows)} feature flows...")

        for entry_point in entry_points_found[:max_flows]:
            try:
                logger.info(f"[FLOW-EXTRACT] Tracing flow for: {entry_point}")
                response = await self._flow_service.extract_feature_flow(
                    entry_point=entry_point,
                    entry_point_type="auto",
                    include_sql=True,
                    include_data_mappings=True,
                    max_depth=10,
                )

                if response.success and response.feature_flow:
                    feature_flows.append(response.feature_flow)
                    logger.info(
                        f"[FLOW-EXTRACT] Flow extracted: {len(response.feature_flow.flow_steps)} steps, "
                        f"{len(response.feature_flow.sql_operations)} SQL ops"
                    )
                else:
                    if response.error:
                        logger.debug(f"[FLOW-EXTRACT] Flow extraction failed for {entry_point}: {response.error}")

            except Exception as e:
                logger.debug(f"[FLOW-EXTRACT] Error tracing {entry_point}: {e}")

        logger.info(f"[FLOW-EXTRACT] Successfully extracted {len(feature_flows)} feature flows")

        if not feature_flows:
            return [], "", ""

        # Step 3: Generate BRD Section 9 - Implementation Mapping
        await report("flow", "Generating implementation mapping table...")
        implementation_mapping = ImplementationMapping.from_feature_flows(feature_flows)
        impl_mapping_md = implementation_mapping.to_markdown_table()
        logger.info(f"[FLOW-EXTRACT] Generated implementation mapping: {len(implementation_mapping.operations)} rows")

        # Step 4: Generate BRD Section 7 - Technical Architecture
        await report("flow", "Generating technical architecture view...")
        tech_arch_sections = []
        for flow in feature_flows:
            arch_view = TechnicalArchitectureView.from_feature_flow(flow)
            tech_arch_sections.append(arch_view.to_markdown())

        tech_arch_md = "\n\n".join(tech_arch_sections)
        logger.info(f"[FLOW-EXTRACT] Generated technical architecture for {len(feature_flows)} features")

        return feature_flows, impl_mapping_md, tech_arch_md

    async def _compress_context(
        self,
        context: AggregatedContext,
    ) -> AggregatedContext:
        """Compress context to fit token budget."""
        logger.info("Compressing context to fit token budget...")

        # Strategy 1: Summarize file contents
        for file_ctx in context.implementation.key_files:
            if len(file_ctx.content) > 1000:
                file_ctx.summary = (
                    file_ctx.content[:500] + "\n... [truncated] ...\n" + file_ctx.content[-500:]
                )
                file_ctx.content = file_ctx.summary

        # Strategy 2: Reduce number of components based on token budget
        max_components = self._calculate_dynamic_limit(estimated_tokens_per_item=150)
        if len(context.architecture.components) > max_components:
            context.architecture.components = context.architecture.components[:max_components]

        # Strategy 3: Reduce number of files based on token budget
        max_files = self._calculate_dynamic_limit(estimated_tokens_per_item=500)
        if len(context.implementation.key_files) > max_files:
            sorted_files = sorted(
                context.implementation.key_files,
                key=lambda f: f.relevance_score,
                reverse=True,
            )
            context.implementation.key_files = sorted_files[:max_files]

        # Strategy 4: Remove similar features if still over budget
        if context.estimated_tokens > self.max_tokens:
            max_similar = self._calculate_dynamic_limit(estimated_tokens_per_item=30)
            context.similar_features = context.similar_features[:max_similar]

        return context
