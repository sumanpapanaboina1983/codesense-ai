"""Context Explorer API Routes.

Provides endpoints for exploring and validating context retrieval
from the codebase graph. Useful for validating that the context
aggregation is working correctly before BRD generation.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ..core.aggregator import ContextAggregator
from ..core.enhanced_context import EnhancedContextRetriever, extract_compound_terms
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Global enhanced retriever instance
_enhanced_retriever: EnhancedContextRetriever | None = None


async def get_enhanced_retriever() -> EnhancedContextRetriever:
    """Get or create the enhanced context retriever."""
    global _enhanced_retriever
    if _enhanced_retriever is None:
        neo4j_client = await get_neo4j_client()
        _enhanced_retriever = EnhancedContextRetriever(neo4j_client)
    return _enhanced_retriever

router = APIRouter(prefix="/context", tags=["context"])

# Global MCP clients (initialized on startup)
_neo4j_client: Neo4jMCPClient | None = None
_filesystem_client: FilesystemMCPClient | None = None


async def get_neo4j_client() -> Neo4jMCPClient:
    """Get or create Neo4j MCP client."""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jMCPClient()
        await _neo4j_client.connect()
    return _neo4j_client


async def get_filesystem_client() -> FilesystemMCPClient:
    """Get or create Filesystem MCP client."""
    global _filesystem_client
    if _filesystem_client is None:
        _filesystem_client = FilesystemMCPClient()
        await _filesystem_client.connect()
    return _filesystem_client


# =============================================================================
# Request/Response Models
# =============================================================================

class ExploreContextRequest(BaseModel):
    """Request to explore context for a feature."""

    feature_description: str = Field(
        ...,
        description="Description of the feature to explore context for",
        min_length=3,
        max_length=2000,
    )
    repository_id: Optional[str] = Field(
        default=None,
        description="Optional repository ID to filter context",
    )
    affected_components: Optional[list[str]] = Field(
        default=None,
        description="Optional list of known affected components",
    )
    include_file_contents: bool = Field(
        default=False,
        description="Whether to include file contents in response",
    )


class FileInfo(BaseModel):
    """Information about a file in the context."""

    path: str
    name: str
    type: str  # 'java', 'jsp', 'xml', 'ts', 'py', etc.
    relevance: str = ""
    relevance_score: float = 0.0
    content_preview: Optional[str] = None


class MethodInfo(BaseModel):
    """Information about a method/function."""

    name: str
    file_path: str
    class_name: Optional[str] = None
    signature: Optional[str] = None
    description: Optional[str] = None


class ComponentInfo(BaseModel):
    """Information about a code component."""

    name: str
    type: str  # 'class', 'service', 'controller', 'repository', etc.
    path: str
    description: str = ""
    dependencies: list[str] = Field(default_factory=list)
    dependents: list[str] = Field(default_factory=list)


class APIEndpointInfo(BaseModel):
    """Information about an API endpoint."""

    endpoint: str
    method: str  # GET, POST, PUT, DELETE
    service: str
    handler_file: Optional[str] = None


class DatabaseEntityInfo(BaseModel):
    """Information about a database entity/table."""

    name: str
    type: str  # 'table', 'view', 'entity'
    fields: list[str] = Field(default_factory=list)
    file_path: Optional[str] = None


class WebFlowInfo(BaseModel):
    """Information about Spring WebFlow definitions."""

    flow_id: str
    file_path: str
    states: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class CategorizedContext(BaseModel):
    """Context categorized by type for easy validation."""

    # Frontend/UI files
    frontend_files: list[FileInfo] = Field(default_factory=list)
    jsp_files: list[FileInfo] = Field(default_factory=list)

    # Backend files
    backend_files: list[FileInfo] = Field(default_factory=list)
    controllers: list[ComponentInfo] = Field(default_factory=list)
    services: list[ComponentInfo] = Field(default_factory=list)
    repositories: list[ComponentInfo] = Field(default_factory=list)

    # API layer
    api_endpoints: list[APIEndpointInfo] = Field(default_factory=list)

    # Data layer
    database_entities: list[DatabaseEntityInfo] = Field(default_factory=list)
    data_models: list[ComponentInfo] = Field(default_factory=list)

    # Configuration/Flow
    webflow_definitions: list[WebFlowInfo] = Field(default_factory=list)
    config_files: list[FileInfo] = Field(default_factory=list)

    # Test files
    test_files: list[FileInfo] = Field(default_factory=list)

    # Other components
    other_components: list[ComponentInfo] = Field(default_factory=list)


class ExploreContextResponse(BaseModel):
    """Response containing categorized context for validation."""

    success: bool
    feature_description: str

    # Summary statistics
    total_components: int = 0
    total_files: int = 0
    total_api_endpoints: int = 0
    total_database_entities: int = 0

    # Categorized context
    context: CategorizedContext

    # Schema info discovered
    available_labels: list[str] = Field(default_factory=list)
    available_relationships: list[str] = Field(default_factory=list)

    # Keywords used for search
    search_keywords: list[str] = Field(default_factory=list)

    # Errors/warnings
    warnings: list[str] = Field(default_factory=list)


# =============================================================================
# Helper Functions
# =============================================================================

def categorize_file(path: str) -> str:
    """Categorize a file based on its path and extension."""
    path_lower = path.lower()

    # JSP files
    if path_lower.endswith('.jsp'):
        return 'jsp'

    # WebFlow
    if 'webflow' in path_lower or (path_lower.endswith('.xml') and 'flow' in path_lower):
        return 'webflow'

    # Frontend files
    if any(ext in path_lower for ext in ['.tsx', '.jsx', '.vue', '.html', '.css', '.scss']):
        return 'frontend'
    if '/frontend/' in path_lower or '/ui/' in path_lower or '/web/' in path_lower:
        if path_lower.endswith(('.ts', '.js')):
            return 'frontend'

    # Test files
    if 'test' in path_lower or 'spec' in path_lower:
        return 'test'

    # Config files
    if any(name in path_lower for name in ['config', 'application.', 'settings', 'properties']):
        return 'config'
    if path_lower.endswith(('.yaml', '.yml', '.properties', '.xml', '.json')):
        if 'src/main' not in path_lower:
            return 'config'

    # Backend files
    return 'backend'


def categorize_component(comp_type: str, comp_name: str, comp_path: str = "") -> str:
    """Categorize a component based on its type, name, and path."""
    type_lower = comp_type.lower()
    name_lower = comp_name.lower()
    path_lower = comp_path.lower() if comp_path else ""

    # JavaField and JavaMethod are internal class elements - categorize by context
    if type_lower == 'javafield':
        # Fields that look like service injections
        if any(term in name_lower for term in ['service', 'repository', 'dao', 'validator', 'builder']):
            return 'service'  # Represents injected dependency
        return 'other'  # Regular fields go to other

    if type_lower == 'javamethod':
        return 'other'  # Methods are internal implementation details

    # JSP - check type first (from Neo4j labels)
    if type_lower in ['jsppage', 'jspform', 'jspinclude', 'jsptaglib']:
        return 'jsp'
    if path_lower.endswith('.jsp'):
        return 'jsp'

    # WebFlow - check type labels
    if type_lower in ['webflowdefinition', 'flowdefinition', 'flowstate', 'flowtransition', 'flowaction']:
        return 'webflow'
    if 'webflow' in type_lower or 'flow' in type_lower:
        return 'webflow'

    # SQL/Database - check type labels
    if type_lower in ['sqltable', 'sqlview', 'sqlcolumn']:
        return 'database'

    # Controllers - check type labels and naming patterns
    if type_lower in ['springcontroller', 'restcontroller']:
        return 'controller'
    if 'controller' in type_lower or 'controller' in name_lower:
        return 'controller'
    # Struts/Spring MVC Actions are controllers
    if name_lower.endswith('action') and type_lower in ['class', 'javaclass', 'springservice']:
        return 'controller'
    # Check path for controller indicators
    if '/actions/' in path_lower or '/controller/' in path_lower:
        return 'controller'

    # Repositories/DAOs - check type labels and naming patterns
    if any(term in type_lower for term in ['repository', 'dao']):
        return 'repository'
    if any(term in name_lower for term in ['repository', 'dao', 'mapper']):
        return 'repository'
    # Check path for persistence indicators
    if '/persistence/' in path_lower or '/dao/' in path_lower or '/repository/' in path_lower:
        return 'repository'

    # Services - check type labels
    if type_lower == 'springservice' and not name_lower.endswith('action'):
        return 'service'
    if 'service' in type_lower:
        return 'service'
    if 'service' in name_lower and not name_lower.endswith('action'):
        return 'service'

    # Data models/Entities
    if any(term in type_lower for term in ['entity', 'model', 'dto']):
        return 'data_model'
    # Check path for model indicators
    if '/model/' in path_lower or '/dto/' in path_lower or '/entity/' in path_lower:
        return 'data_model'

    # Validators
    if 'validator' in name_lower:
        return 'service'

    # Builders
    if 'builder' in name_lower:
        return 'service'

    # API/REST Endpoints
    if type_lower in ['restendpoint', 'apiendpoint']:
        return 'api'
    if any(term in type_lower for term in ['endpoint', 'api', 'rest']):
        return 'api'

    # Test files
    if 'test' in name_lower or 'spec' in name_lower:
        return 'test'

    return 'other'


def get_file_extension(path: str) -> str:
    """Get the file type from extension."""
    if '.' in path:
        ext = path.rsplit('.', 1)[-1].lower()
        return ext
    return 'unknown'


# =============================================================================
# Graph-Based Relevance Functions
# =============================================================================

def extract_compound_terms(keywords: list[str]) -> tuple[str, list[str]]:
    """
    Extract compound terms from keywords.

    "Legal Entity Maintenance" → compound="legalentity", actions=["maintenance"]

    Logic: Consecutive words before common action words form the compound subject.
    """
    action_words = {'maintenance', 'search', 'create', 'update', 'delete', 'merge',
                    'wizard', 'inquiry', 'report', 'list', 'view', 'edit', 'add',
                    'replace', 'contact', 'history', 'status', 'detail', 'summary'}

    subject_parts = []
    action_parts = []

    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in action_words:
            action_parts.append(kw_lower)
        else:
            subject_parts.append(kw_lower)

    # Compound term is all subject parts joined
    compound_term = ''.join(subject_parts) if subject_parts else ''

    return compound_term, action_parts


async def find_entry_points(
    neo4j_client,
    keywords: list[str],
) -> list[dict]:
    """
    Find entry points using COMPOUND TERM DETECTION + TRAVERSAL-BASED UI DISCOVERY.

    Approach:
    1. Extract compound term from keywords (e.g., "Legal Entity" → "legalentity")
    2. Find Controller entry points that match the compound term
    3. Traverse from Controllers to find connected WebFlows and JSPs
    4. This eliminates false positives (e.g., pointMaintenance when searching legalEntityMaintenance)

    Returns entry points organized by layer.
    """
    if not keywords:
        return []

    all_entry_points = []
    seen_names = set()

    # Extract compound term and action words
    compound_term, action_words = extract_compound_terms(keywords)
    logger.info(f"[ENTRY-POINTS] Compound term: '{compound_term}', Actions: {action_words}")

    # =================================================================
    # Step 1: Find Controller Entry Points (using compound term)
    # Controllers are the most reliable - they define the feature
    # =================================================================

    # Build filter: must contain compound term, optionally action words
    if compound_term:
        # Primary filter: compound term (e.g., "legalentity")
        compound_filter = f"toLower(n.name) CONTAINS '{compound_term}'"

        # Secondary filter: action words boost relevance
        if action_words:
            action_filter = " OR ".join([f"toLower(n.name) CONTAINS '{aw}'" for aw in action_words])
            score_boost = " + ".join([f"CASE WHEN toLower(n.name) CONTAINS '{aw}' THEN 10 ELSE 0 END" for aw in action_words])
        else:
            action_filter = "true"
            score_boost = "0"
    else:
        # Fallback to OR logic if no compound term
        compound_filter = " OR ".join([f"toLower(n.name) CONTAINS '{kw}'" for kw in keywords])
        score_boost = "0"

    controller_query = f"""
        MATCH (n)
        WHERE (n:SpringService OR n:JavaClass OR n:SpringController)
          AND ({compound_filter})
          AND (
            toLower(n.name) ENDS WITH 'action'
            OR toLower(n.name) ENDS WITH 'controller'
          )
        WITH n,
             ({score_boost}) AS action_score,
             COALESCE(n.pageRank, 0.1) AS pagerank
        RETURN n.name AS name,
               labels(n)[0] AS type,
               n.filePath AS path,
               'controller' AS layer,
               80 AS layer_score,
               action_score + pagerank * 10 AS relevance_score
        ORDER BY relevance_score DESC
        LIMIT 500
    """

    try:
        result = await neo4j_client.query_code_structure(controller_query)
        controllers = result.get("nodes", [])
        logger.info(f"[ENTRY-POINTS-Controller] Found {len(controllers)} controllers with compound term '{compound_term}'")

        for node in controllers:
            name = node.get("name")
            if name and name not in seen_names:
                all_entry_points.append(node)
                seen_names.add(name)
    except Exception as e:
        logger.warning(f"[ENTRY-POINTS-Controller] Query failed: {e}")
        controllers = []

    # =================================================================
    # Step 2: Find WebFlows CONNECTED to the Controllers
    # Instead of keyword matching, traverse from controllers
    # =================================================================

    if controllers:
        controller_names = [c.get("name") for c in controllers[:5] if c.get("name")]
        # Extract base names for WebFlow matching (e.g., LegalEntityWizardAction → legalEntityWizard)
        webflow_patterns = []
        for cn in controller_names:
            # Remove "Action" suffix and convert to lowercase for matching
            base = cn.replace("Action", "").replace("Controller", "")
            webflow_patterns.append(f"toLower(w.name) CONTAINS toLower('{base}')")

        webflow_filter = " OR ".join(webflow_patterns) if webflow_patterns else "false"

        webflow_query = f"""
            MATCH (w:WebFlowDefinition)
            WHERE {webflow_filter}
            RETURN w.name AS name,
                   'WebFlowDefinition' AS type,
                   w.filePath AS path,
                   'flow' AS layer,
                   90 AS layer_score
            LIMIT 500
        """

        try:
            result = await neo4j_client.query_code_structure(webflow_query)
            webflows = result.get("nodes", [])
            logger.info(f"[ENTRY-POINTS-WebFlow] Found {len(webflows)} WebFlows connected to controllers")

            for node in webflows:
                name = node.get("name")
                if name and name not in seen_names:
                    all_entry_points.append(node)
                    seen_names.add(name)
        except Exception as e:
            logger.warning(f"[ENTRY-POINTS-WebFlow] Query failed: {e}")

    # =================================================================
    # Step 3: Find JSPs CONNECTED to the WebFlows/Controllers
    # Use graph traversal OR naming pattern from controllers
    # =================================================================

    if controllers:
        controller_names = [c.get("name") for c in controllers[:5] if c.get("name")]

        # Try to find JSPs via WebFlow relationships first
        jsp_via_traversal_query = f"""
            MATCH (w:WebFlowDefinition)-[:FLOW_RENDERS_VIEW|FLOW_DEFINES_STATE*1..2]->(related)
            WHERE {webflow_filter}
              AND (related:JSPPage OR related:FlowState)
            WITH related
            MATCH (j:JSPPage)
            WHERE toLower(j.name) CONTAINS toLower(related.name)
               OR toLower(related.name) CONTAINS replace(toLower(j.name), '.jsp', '')
            RETURN DISTINCT j.name AS name,
                   'JSPPage' AS type,
                   j.filePath AS path,
                   'ui' AS layer,
                   100 AS layer_score
            LIMIT 500
        """

        # Also find JSPs by naming pattern (e.g., LegalEntityWizardAction → legalEntityWizard*.jsp)
        jsp_patterns = []
        for cn in controller_names:
            base = cn.replace("Action", "").replace("Controller", "")
            # Match JSPs that start with the controller base name
            jsp_patterns.append(f"toLower(j.name) STARTS WITH toLower('{base}')")
            # Also match if compound term is in JSP name
            if compound_term:
                jsp_patterns.append(f"toLower(j.name) CONTAINS '{compound_term}'")

        jsp_filter = " OR ".join(list(set(jsp_patterns))) if jsp_patterns else "false"

        # Additional filter: if we have action words, require them OR at least compound term
        if action_words and compound_term:
            action_bonus = " OR ".join([f"toLower(j.name) CONTAINS '{aw}'" for aw in action_words])
            jsp_relevance_query = f"""
                MATCH (j:JSPPage)
                WHERE ({jsp_filter})
                WITH j,
                     CASE WHEN toLower(j.name) CONTAINS '{compound_term}' THEN 20 ELSE 0 END +
                     CASE WHEN {action_bonus} THEN 10 ELSE 0 END AS relevance
                WHERE relevance >= 20  // Must at least have compound term
                RETURN j.name AS name,
                       'JSPPage' AS type,
                       j.filePath AS path,
                       'ui' AS layer,
                       100 AS layer_score,
                       relevance
                ORDER BY relevance DESC
                LIMIT 500
            """
        else:
            jsp_relevance_query = f"""
                MATCH (j:JSPPage)
                WHERE {jsp_filter}
                RETURN j.name AS name,
                       'JSPPage' AS type,
                       j.filePath AS path,
                       'ui' AS layer,
                       100 AS layer_score
                LIMIT 500
            """

        try:
            result = await neo4j_client.query_code_structure(jsp_relevance_query)
            jsps = result.get("nodes", [])
            logger.info(f"[ENTRY-POINTS-JSP] Found {len(jsps)} JSPs connected to controllers")

            for node in jsps:
                name = node.get("name")
                if name and name not in seen_names:
                    all_entry_points.append(node)
                    seen_names.add(name)
        except Exception as e:
            logger.warning(f"[ENTRY-POINTS-JSP] Query failed: {e}")

    # Sort by layer_score (UI first, then flow, then controller)
    all_entry_points.sort(key=lambda x: x.get("layer_score", 0), reverse=True)

    logger.info(f"[ENTRY-POINTS] Total: {len(all_entry_points)} entry points across all layers")
    for ep in all_entry_points[:5]:
        logger.info(f"[ENTRY-POINTS]   - {ep.get('name')} ({ep.get('type')}) layer={ep.get('layer')}")

    return all_entry_points[:20]  # Limit total entry points


async def traverse_dependencies(
    neo4j_client,
    entry_points: list[str],
    keywords: list[str] = None,
    max_depth: int = 4,
) -> dict:
    """
    Traverse the dependency graph from entry points to find all related components.

    This follows actual code relationships:
    - Method calls (HAS_METHOD, CALLS)
    - Field access (HAS_FIELD, USES)
    - Inheritance (EXTENDS, IMPLEMENTS)
    - Imports (JAVA_IMPORTS)
    - WebFlow transitions (FLOW_TRANSITIONS_TO, FLOW_EXECUTES_ACTION)
    - DAOs/Repositories in persistence layer
    - Database tables/views
    """
    keywords = keywords or []
    if not entry_points:
        return {"nodes": [], "edges": []}

    # Build entry point filter - escape special characters
    safe_entry_points = [ep.replace("'", "\\'") for ep in entry_points[:5]]
    entry_filter = " OR ".join([f"start.name = '{name}'" for name in safe_entry_points])

    all_nodes = []

    # Use multiple simpler queries for better compatibility
    # Query 1: Direct relationships (depth 1)
    query_depth1 = f"""
        MATCH (start)-[r]->(related)
        WHERE ({entry_filter})
          AND type(r) IN [
            'HAS_METHOD', 'HAS_FIELD', 'CALLS', 'USES', 'DEPENDS_ON',
            'EXTENDS', 'IMPLEMENTS', 'JAVA_IMPORTS',
            'FLOW_TRANSITIONS_TO', 'FLOW_EXECUTES_ACTION', 'FLOW_RENDERS_VIEW',
            'CONTAINS_FORM', 'INCLUDES_JSP', 'USES_TAGLIB',
            'BELONGS_TO', 'DEFINED_IN_MODULE', 'INSTANTIATES'
          ]
        RETURN DISTINCT related.name AS name,
               labels(related)[0] AS type,
               related.filePath AS path,
               related.description AS description,
               1 AS distance,
               type(r) AS relationship
        LIMIT 500
    """

    # Query 2: Two-hop relationships (depth 2)
    query_depth2 = f"""
        MATCH (start)-[r1]->(mid)-[r2]->(related)
        WHERE ({entry_filter})
          AND type(r1) IN ['HAS_METHOD', 'HAS_FIELD', 'CALLS', 'USES', 'DEPENDS_ON', 'EXTENDS', 'IMPLEMENTS', 'JAVA_IMPORTS']
          AND type(r2) IN ['HAS_METHOD', 'HAS_FIELD', 'CALLS', 'USES', 'DEPENDS_ON', 'EXTENDS', 'IMPLEMENTS', 'JAVA_IMPORTS', 'INSTANTIATES']
        RETURN DISTINCT related.name AS name,
               labels(related)[0] AS type,
               related.filePath AS path,
               related.description AS description,
               2 AS distance,
               type(r2) AS relationship
        LIMIT 500
    """

    # Query 3: Find classes that the entry point imports/uses
    query_imports = f"""
        MATCH (start)-[:JAVA_IMPORTS|USES|INSTANTIATES]->(imported)
        WHERE ({entry_filter})
        RETURN DISTINCT imported.name AS name,
               labels(imported)[0] AS type,
               imported.filePath AS path,
               imported.description AS description,
               1 AS distance,
               'IMPORTS' AS relationship
        LIMIT 200
    """

    # Query 4: Find services/classes that match field names (dependency injection pattern)
    # This captures injected dependencies like `legalEntityService` -> `LegalEntityService`
    query_injected_services = f"""
        MATCH (start)-[:HAS_FIELD]->(field:JavaField)
        WHERE ({entry_filter})
        WITH field, toLower(field.name) AS field_name

        // Find SpringService or JavaClass whose name matches the field name
        MATCH (service)
        WHERE (service:SpringService OR service:JavaClass OR service:JavaInterface)
          AND toLower(service.name) = field_name

        RETURN DISTINCT service.name AS name,
               labels(service)[0] AS type,
               service.filePath AS path,
               service.description AS description,
               1 AS distance,
               'INJECTED_SERVICE' AS relationship
        LIMIT 150
    """

    # Query 5: Find Actions referenced by WebFlows
    # WebFlow → FlowAction (e.g., "legalEntitySearchAction.initState()") → SpringService
    query_webflow_actions = f"""
        MATCH (start:WebFlowDefinition)-[:FLOW_EXECUTES_ACTION]->(fa:FlowAction)
        WHERE ({entry_filter})
        WITH fa, toLower(fa.name) AS action_expr

        // Extract action bean name from expressions like "legalEntitySearchAction.initState()"
        WITH fa,
             CASE
               WHEN action_expr CONTAINS '.'
               THEN substring(action_expr, 0, apoc.text.indexOf(action_expr, '.'))
               ELSE action_expr
             END AS bean_name

        // Find SpringService that matches the bean name
        MATCH (action:SpringService)
        WHERE toLower(action.name) = bean_name

        RETURN DISTINCT action.name AS name,
               'SpringService' AS type,
               action.filePath AS path,
               'Referenced by WebFlow' AS description,
               1 AS distance,
               'WEBFLOW_EXECUTES' AS relationship
        LIMIT 500
    """

    # Query 6: Find related services by similar naming patterns
    # E.g., for LegalEntitySearchAction, find LegalEntityService, LegalEntityValidator, etc.
    entry_base_names = [ep.replace("Action", "").replace("Controller", "").lower() for ep in safe_entry_points]
    base_name_filter = " OR ".join([f"toLower(s.name) CONTAINS '{base}'" for base in entry_base_names[:3]])

    query_related_services = f"""
        MATCH (s)
        WHERE (s:SpringService OR s:JavaInterface)
          AND ({base_name_filter})
          AND NOT toLower(s.name) ENDS WITH 'action'
          AND NOT toLower(s.name) ENDS WITH 'test'
        WITH DISTINCT s, COALESCE(s.pageRank, 0.0) AS rank
        ORDER BY rank DESC
        RETURN s.name AS name,
               labels(s)[0] AS type,
               s.filePath AS path,
               s.description AS description,
               2 AS distance,
               'RELATED_BY_NAME' AS relationship
        LIMIT 500
    """

    # Query 7: Find DAOs/Repositories in the data layer
    # Use original keywords for better matching (e.g., "legal", "entity" matches LeslegalEntityDao)
    dao_keyword_filter = " OR ".join([f"toLower(d.name) CONTAINS '{kw}'" for kw in keywords[:3]]) if keywords else "1=0"

    query_daos = f"""
        MATCH (d)
        WHERE (d:SpringService OR d:JavaClass)
          AND ({dao_keyword_filter})
          AND (toLower(d.name) CONTAINS 'dao' OR toLower(d.name) CONTAINS 'repository' OR toLower(d.name) CONTAINS 'mapper')
          AND NOT toLower(d.name) ENDS WITH 'test'
        WITH DISTINCT d, COALESCE(d.pageRank, 0.0) AS rank
        ORDER BY rank DESC
        RETURN d.name AS name,
               labels(d)[0] AS type,
               d.filePath AS path,
               d.description AS description,
               3 AS distance,
               'DATA_LAYER' AS relationship
        LIMIT 500
    """

    # Query 8: Find database entities/tables related to the feature
    # SQL tables, views that match keywords
    query_database = None
    if keywords:
        keyword_filter_sql = " OR ".join([f"toLower(n.name) CONTAINS '{kw}'" for kw in keywords])
        query_database = f"""
            MATCH (n)
            WHERE (n:SQLTable OR n:SQLView)
              AND ({keyword_filter_sql})
            RETURN n.name AS name,
                   labels(n)[0] AS type,
                   n.filePath AS path,
                   n.description AS description,
                   4 AS distance,
                   'DATABASE' AS relationship
            LIMIT 500
        """

    try:
        # Execute all queries and combine results
        seen_names = set()

        queries_to_run = [
            (query_depth1, "depth1"),
            (query_depth2, "depth2"),
            (query_imports, "imports"),
            (query_injected_services, "injected"),
            (query_webflow_actions, "webflow_actions"),
            (query_related_services, "related_services"),
            (query_daos, "daos"),
        ]
        # Add database query only if we have keywords
        if query_database:
            queries_to_run.append((query_database, "database"))

        for query, label in queries_to_run:
            try:
                result = await neo4j_client.query_code_structure(query)
                nodes = result.get("nodes", [])
                logger.info(f"[TRAVERSE-{label}] Found {len(nodes)} nodes")

                for node in nodes:
                    name = node.get("name")
                    if name and name not in seen_names:
                        all_nodes.append(node)
                        seen_names.add(name)
            except Exception as e:
                logger.warning(f"[TRAVERSE-{label}] Query failed: {e}")

        logger.info(f"[TRAVERSE] Total: {len(all_nodes)} connected components from {len(entry_points)} entry points")
        return {"nodes": all_nodes, "entry_points": entry_points}

    except Exception as e:
        logger.warning(f"[TRAVERSE] Graph traversal failed: {e}")
        return {"nodes": [], "entry_points": entry_points}


async def get_relevant_context_graph_based(
    neo4j_client,
    feature_description: str,
) -> tuple[list[dict], list[str], list[str]]:
    """
    Get relevant context using graph-based traversal.

    This approach:
    1. Finds entry points (Actions/Controllers) matching the feature
    2. Traverses the dependency graph from those entry points
    3. Returns only components that are actually connected

    Returns:
        Tuple of (components, entry_point_names, warnings)
    """
    warnings = []

    # Extract keywords
    keywords = [w.lower() for w in feature_description.split() if len(w) > 3][:5]

    if not keywords:
        warnings.append("No keywords extracted from feature description")
        return [], [], warnings

    # Step 1: Find entry points
    entry_points = await find_entry_points(neo4j_client, keywords)

    if not entry_points:
        warnings.append(f"No entry points found for keywords: {keywords}. Falling back to keyword search.")
        return [], [], warnings

    # Group entry points by layer for targeted traversal
    ui_entry_points = [ep for ep in entry_points if ep.get("layer") == "ui"]
    flow_entry_points = [ep for ep in entry_points if ep.get("layer") == "flow"]
    controller_entry_points = [ep for ep in entry_points if ep.get("layer") == "controller"]

    # Use controller entry points for traversal (they have the richest relationships)
    # If no controllers found, fall back to flow entry points
    traversal_entry_names = [ep.get("name") for ep in controller_entry_points if ep.get("name")]
    if not traversal_entry_names:
        traversal_entry_names = [ep.get("name") for ep in flow_entry_points if ep.get("name")]

    entry_point_names = [ep.get("name") for ep in entry_points if ep.get("name")]
    logger.info(f"[GRAPH-CONTEXT] Found entry points: UI={len(ui_entry_points)}, Flow={len(flow_entry_points)}, Controller={len(controller_entry_points)}")

    # Step 2: Traverse from controller/flow entry points (they have the best relationships)
    traversal_result = await traverse_dependencies(neo4j_client, traversal_entry_names, keywords=keywords)

    # Step 3: Combine entry points with traversed nodes
    all_nodes = []
    seen_names = set()

    # Add entry points first (they're the most relevant)
    for ep in entry_points:
        name = ep.get("name")
        if name and name not in seen_names:
            all_nodes.append({
                "name": name,
                "type": ep.get("type", "unknown"),
                "path": ep.get("path", ""),
                "description": "Entry point for feature",
                "distance": 0,
                "is_entry_point": True,
            })
            seen_names.add(name)

    # Add traversed nodes
    for node in traversal_result.get("nodes", []):
        name = node.get("name")
        if name and name not in seen_names:
            all_nodes.append({
                "name": name,
                "type": node.get("type", "unknown"),
                "path": node.get("path", ""),
                "description": node.get("description", ""),
                "distance": node.get("distance", 1),
                "is_entry_point": False,
            })
            seen_names.add(name)

    logger.info(f"[GRAPH-CONTEXT] Total relevant components: {len(all_nodes)}")

    # Build entry point summary by layer
    entry_point_summary = []
    if ui_entry_points:
        entry_point_summary.append(f"UI: {len(ui_entry_points)} JSP pages")
    if flow_entry_points:
        entry_point_summary.append(f"Flow: {len(flow_entry_points)} WebFlows")
    if controller_entry_points:
        controller_names = [ep.get("name") for ep in controller_entry_points[:3]]
        entry_point_summary.append(f"Controllers: {', '.join(controller_names)}")

    if entry_point_summary:
        warnings.insert(0, f"Entry points by layer: {' | '.join(entry_point_summary)}")

    return all_nodes, entry_point_names, warnings


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/explore", response_model=ExploreContextResponse)
async def explore_context(
    request: ExploreContextRequest,
) -> ExploreContextResponse:
    """
    Explore and retrieve categorized context for a feature.

    This endpoint uses the ENHANCED context retrieval with:
    1. COMPOUND TERM DETECTION - extracts subject from feature description
    2. ENTRY POINT DISCOVERY - finds Controllers/Actions first
    3. GRAPH-BASED TRAVERSAL - only returns connected components
    4. FALSE POSITIVE ELIMINATION - no loose keyword matching
    """
    logger.info(f"[CONTEXT-EXPLORE] ========================================")
    logger.info(f"[CONTEXT-EXPLORE] Starting ENHANCED context exploration")
    logger.info(f"[CONTEXT-EXPLORE] Feature: {request.feature_description[:80]}...")
    logger.info(f"[CONTEXT-EXPLORE] ========================================")

    warnings: list[str] = []

    try:
        # Get enhanced retriever (uses shared EnhancedContextRetriever)
        enhanced_retriever = await get_enhanced_retriever()
        filesystem_client = await get_filesystem_client()

        # Use ENHANCED retrieval (compound terms + graph traversal)
        logger.info("[CONTEXT-EXPLORE] Using EnhancedContextRetriever")
        graph_components, entry_points, graph_warnings = await enhanced_retriever.get_relevant_context(
            request.feature_description
        )
        warnings.extend(graph_warnings)

        # Entry point summary is now included from get_relevant_context_graph_based

        # If graph-based found components, use them
        if graph_components:
            logger.info(f"[CONTEXT-EXPLORE] Using graph-based results: {len(graph_components)} components")

            # Categorize the graph-based components
            categorized = CategorizedContext()

            for comp in graph_components:
                category = categorize_component(comp["type"], comp["name"], comp.get("path", ""))
                desc = comp.get("description") or ""
                if comp.get("is_entry_point"):
                    desc = (desc + " [Entry Point]").strip()
                comp_info = ComponentInfo(
                    name=comp["name"],
                    type=comp["type"],
                    path=comp.get("path", ""),
                    description=desc,
                    dependencies=[],
                    dependents=[],
                )

                if category == 'controller':
                    categorized.controllers.append(comp_info)
                elif category == 'service':
                    categorized.services.append(comp_info)
                elif category == 'repository':
                    categorized.repositories.append(comp_info)
                elif category == 'data_model':
                    categorized.data_models.append(comp_info)
                elif category == 'database':
                    categorized.database_entities.append(DatabaseEntityInfo(
                        name=comp["name"],
                        type=comp["type"],
                        fields=[],
                        file_path=comp.get("path"),
                    ))
                elif category == 'webflow':
                    categorized.webflow_definitions.append(WebFlowInfo(
                        flow_id=comp["name"],
                        file_path=comp.get("path", ""),
                        description=comp.get("description") or "",
                    ))
                elif category == 'jsp':
                    categorized.jsp_files.append(FileInfo(
                        path=comp.get("path") or "",
                        name=comp["name"],
                        type='jsp',
                        relevance=comp.get("description") or "",
                    ))
                elif category == 'api':
                    categorized.api_endpoints.append(APIEndpointInfo(
                        endpoint=comp["name"],
                        method='GET',
                        service=comp.get("path", "").rsplit('/', 1)[-1] if comp.get("path") else 'unknown',
                        handler_file=comp.get("path"),
                    ))
                else:
                    categorized.other_components.append(comp_info)

            # Get schema info
            labels_result = await neo4j_client.query_code_structure("CALL db.labels() YIELD label RETURN label")
            available_labels = [r.get("label", "") for r in labels_result.get("nodes", []) if r.get("label")]

            rels_result = await neo4j_client.query_code_structure(
                "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
            )
            available_relationships = [r.get("relationshipType", "") for r in rels_result.get("nodes", []) if r.get("relationshipType")]

            # Calculate totals
            total_components = (
                len(categorized.controllers) +
                len(categorized.services) +
                len(categorized.repositories) +
                len(categorized.data_models) +
                len(categorized.other_components)
            )
            total_files = (
                len(categorized.frontend_files) +
                len(categorized.jsp_files) +
                len(categorized.backend_files) +
                len(categorized.test_files) +
                len(categorized.config_files)
            )

            # Extract keywords used
            search_keywords = [w.lower() for w in request.feature_description.split() if len(w) > 3][:5]

            return ExploreContextResponse(
                success=True,
                feature_description=request.feature_description,
                total_components=total_components,
                total_files=total_files,
                total_api_endpoints=len(categorized.api_endpoints),
                total_database_entities=len(categorized.database_entities),
                context=categorized,
                available_labels=available_labels,
                available_relationships=available_relationships,
                search_keywords=search_keywords,
                warnings=warnings,
            )

        # Fallback to aggregator-based approach if graph-based didn't find anything
        logger.info("[CONTEXT-EXPLORE] Falling back to keyword-based search")
        warnings.append("Graph traversal found no results, using keyword-based search")

        # Create context aggregator
        aggregator = ContextAggregator(
            neo4j_client=neo4j_client,
            filesystem_client=filesystem_client,
            copilot_session=None,  # Not needed for direct MCP
            max_tokens=100000,
        )

        # Build context using the same logic as BRD generation
        context = await aggregator.build_context(
            request=request.feature_description,
            affected_components=request.affected_components,
            include_similar=True,
            use_direct_mcp=True,
        )

        # Categorize the context
        categorized = CategorizedContext()

        # Process components
        for comp in context.architecture.components:
            category = categorize_component(comp.type, comp.name, comp.path)
            comp_info = ComponentInfo(
                name=comp.name,
                type=comp.type,
                path=comp.path,
                description=comp.description,
                dependencies=comp.dependencies,
                dependents=comp.dependents,
            )

            if category == 'controller':
                categorized.controllers.append(comp_info)
            elif category == 'service':
                categorized.services.append(comp_info)
            elif category == 'repository':
                categorized.repositories.append(comp_info)
            elif category == 'data_model':
                categorized.data_models.append(comp_info)
            elif category == 'database':
                # Add as database entity
                categorized.database_entities.append(DatabaseEntityInfo(
                    name=comp.name,
                    type=comp.type,
                    fields=[],
                    file_path=comp.path,
                ))
            elif category == 'webflow':
                categorized.webflow_definitions.append(WebFlowInfo(
                    flow_id=comp.name,
                    file_path=comp.path,
                    description=comp.description,
                ))
            elif category == 'jsp':
                categorized.jsp_files.append(FileInfo(
                    path=comp.path,
                    name=comp.name,
                    type='jsp',
                    relevance=comp.description,
                ))
            elif category == 'api':
                categorized.api_endpoints.append(APIEndpointInfo(
                    endpoint=comp.name,
                    method='GET',
                    service=comp.path.rsplit('/', 1)[-1] if comp.path else 'unknown',
                    handler_file=comp.path,
                ))
            else:
                categorized.other_components.append(comp_info)

        # Process files
        for file_ctx in context.implementation.key_files:
            file_category = categorize_file(file_ctx.path)
            file_info = FileInfo(
                path=file_ctx.path,
                name=file_ctx.path.rsplit('/', 1)[-1] if '/' in file_ctx.path else file_ctx.path,
                type=get_file_extension(file_ctx.path),
                relevance=file_ctx.relevance,
                relevance_score=file_ctx.relevance_score,
                content_preview=file_ctx.content[:500] if request.include_file_contents and file_ctx.content else None,
            )

            if file_category == 'jsp':
                categorized.jsp_files.append(file_info)
            elif file_category == 'frontend':
                categorized.frontend_files.append(file_info)
            elif file_category == 'webflow':
                categorized.webflow_definitions.append(WebFlowInfo(
                    flow_id=file_info.name.replace('.xml', ''),
                    file_path=file_info.path,
                ))
            elif file_category == 'test':
                categorized.test_files.append(file_info)
            elif file_category == 'config':
                categorized.config_files.append(file_info)
            else:
                categorized.backend_files.append(file_info)

        # Process API contracts
        for api in context.architecture.api_contracts:
            categorized.api_endpoints.append(APIEndpointInfo(
                endpoint=api.endpoint,
                method=api.method,
                service=api.service,
            ))

        # Process data models
        for model in context.architecture.data_models:
            categorized.database_entities.append(DatabaseEntityInfo(
                name=model.name,
                type='entity',
                fields=list(model.fields) if isinstance(model.fields, dict) else model.fields,
            ))

        # Get search keywords used
        search_keywords = aggregator._extract_keywords_simple(request.feature_description)

        # Get schema info
        available_labels = []
        available_relationships = []
        if context.schema:
            available_labels = context.schema.node_labels
            available_relationships = context.schema.relationship_types

        # Calculate totals
        total_components = (
            len(categorized.controllers) +
            len(categorized.services) +
            len(categorized.repositories) +
            len(categorized.data_models) +
            len(categorized.other_components)
        )
        total_files = (
            len(categorized.frontend_files) +
            len(categorized.jsp_files) +
            len(categorized.backend_files) +
            len(categorized.test_files) +
            len(categorized.config_files)
        )

        logger.info(
            f"[CONTEXT-EXPLORE] Found {total_components} components, "
            f"{total_files} files, {len(categorized.api_endpoints)} APIs"
        )

        return ExploreContextResponse(
            success=True,
            feature_description=request.feature_description,
            total_components=total_components,
            total_files=total_files,
            total_api_endpoints=len(categorized.api_endpoints),
            total_database_entities=len(categorized.database_entities),
            context=categorized,
            available_labels=available_labels,
            available_relationships=available_relationships,
            search_keywords=search_keywords,
            warnings=warnings,
        )

    except Exception as e:
        logger.error(f"[CONTEXT-EXPLORE] Error exploring context: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to explore context: {str(e)}",
        )


@router.post("/query-direct")
async def query_direct(
    query: str,
    params: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Execute a direct Neo4j query for debugging.

    This is a debug endpoint to help validate queries.
    """
    logger.info(f"[CONTEXT-QUERY] Executing direct query: {query[:100]}...")

    try:
        neo4j_client = await get_neo4j_client()
        result = await neo4j_client.query_code_structure(query, params or {})
        return {
            "success": True,
            "query": query,
            "result": result,
        }
    except Exception as e:
        logger.error(f"[CONTEXT-QUERY] Query failed: {e}")
        return {
            "success": False,
            "query": query,
            "error": str(e),
        }


@router.get("/labels")
async def get_labels() -> dict[str, Any]:
    """Get all available node labels from Neo4j."""
    try:
        neo4j_client = await get_neo4j_client()
        result = await neo4j_client.query_code_structure("CALL db.labels() YIELD label RETURN label")
        labels = [r.get("label", "") for r in result.get("nodes", []) if r.get("label")]
        return {
            "success": True,
            "labels": labels,
            "count": len(labels),
        }
    except Exception as e:
        logger.error(f"[CONTEXT-LABELS] Failed to get labels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/relationships")
async def get_relationships() -> dict[str, Any]:
    """Get all available relationship types from Neo4j."""
    try:
        neo4j_client = await get_neo4j_client()
        result = await neo4j_client.query_code_structure(
            "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
        )
        rel_types = [r.get("relationshipType", "") for r in result.get("nodes", []) if r.get("relationshipType")]
        return {
            "success": True,
            "relationship_types": rel_types,
            "count": len(rel_types),
        }
    except Exception as e:
        logger.error(f"[CONTEXT-RELS] Failed to get relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Flow Graph Endpoint
# =============================================================================

class FlowGraphNode(BaseModel):
    """Node in the flow graph."""
    id: str
    name: str
    type: str  # 'jsp', 'controller', 'service', 'repository', 'database', 'webflow'
    layer: str  # 'presentation', 'controller', 'service', 'data'
    path: Optional[str] = None


class FlowGraphEdge(BaseModel):
    """Edge in the flow graph."""
    source: str
    target: str
    relationship: str
    label: Optional[str] = None


class FlowGraphResponse(BaseModel):
    """Response containing the flow graph for visualization."""
    success: bool
    nodes: list[FlowGraphNode] = Field(default_factory=list)
    edges: list[FlowGraphEdge] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    exit_points: list[str] = Field(default_factory=list)


def get_node_layer(node_type: str, node_name: str) -> str:
    """Determine the architectural layer for a node."""
    type_lower = node_type.lower()
    name_lower = node_name.lower()

    # Presentation layer
    if any(t in type_lower for t in ['jsp', 'jsppage', 'jspform', 'html', 'view']):
        return 'presentation'
    if any(t in type_lower for t in ['webflow', 'flowdefinition', 'flowstate']):
        return 'presentation'

    # Controller layer
    if any(t in type_lower for t in ['controller', 'action', 'flowaction']):
        return 'controller'
    if 'action' in name_lower:
        return 'controller'

    # Service layer
    if 'service' in type_lower or 'service' in name_lower:
        return 'service'
    if 'validator' in name_lower or 'builder' in name_lower:
        return 'service'

    # Data layer
    if any(t in type_lower for t in ['dao', 'repository', 'mapper', 'sqltable', 'sqlview']):
        return 'data'
    if any(t in name_lower for t in ['dao', 'repository']):
        return 'data'
    if '/persistence/' in (node_name or '').lower():
        return 'data'

    return 'service'  # Default to service layer


@router.post("/flow-graph")
async def get_flow_graph(
    feature_description: str,
    repository_id: Optional[str] = None,
) -> FlowGraphResponse:
    """
    Get a flow graph showing how a feature flows through the codebase.

    Uses ENHANCED context retrieval with:
    1. COMPOUND TERM DETECTION for accurate entry point identification
    2. GRAPH-BASED TRAVERSAL from entry points
    3. Only shows nodes that are actually connected

    Returns nodes and edges for visualization, organized by architectural layers.
    """
    logger.info(f"[FLOW-GRAPH] ========================================")
    logger.info(f"[FLOW-GRAPH] Building ENHANCED flow graph")
    logger.info(f"[FLOW-GRAPH] Feature: {feature_description[:80]}...")
    logger.info(f"[FLOW-GRAPH] ========================================")

    try:
        # Use shared EnhancedContextRetriever
        enhanced_retriever = await get_enhanced_retriever()
        neo4j_client = await get_neo4j_client()

        # Extract keywords for search
        keywords = [w for w in feature_description.split() if len(w) > 2][:8]

        if not keywords:
            return FlowGraphResponse(success=True)

        # Step 1: Find entry points using ENHANCED retrieval
        logger.info(f"[FLOW-GRAPH] Using EnhancedContextRetriever for entry points")
        entry_point_results = await enhanced_retriever._find_entry_points(keywords, max_entry_points=10)
        entry_point_names = [ep.get("name") for ep in entry_point_results if ep.get("name")]

        if not entry_point_names:
            logger.warning(f"[FLOW-GRAPH] No entry points found for: {keywords}")
            return FlowGraphResponse(success=True)

        logger.info(f"[FLOW-GRAPH] Found {len(entry_point_names)} entry points via ENHANCED retrieval")

        # Step 2: Build graph by traversing from entry points
        entry_filter = " OR ".join([f"start.name = '{name}'" for name in entry_point_names[:3]])

        # Query for nodes AND their relationships (edges)
        query = f"""
            // Start from entry points
            MATCH (start)
            WHERE {entry_filter}

            // Traverse relationships to build the graph
            CALL {{
                WITH start
                MATCH path = (start)-[r*1..3]->(related)
                WHERE ALL(rel IN r WHERE type(rel) IN [
                    'HAS_METHOD', 'HAS_FIELD', 'CALLS', 'USES', 'DEPENDS_ON',
                    'EXTENDS', 'IMPLEMENTS', 'JAVA_IMPORTS',
                    'FLOW_TRANSITIONS_TO', 'FLOW_EXECUTES_ACTION', 'FLOW_RENDERS_VIEW',
                    'BELONGS_TO', 'DEFINED_IN_MODULE'
                ])
                UNWIND relationships(path) AS rel
                WITH start, related, rel, startNode(rel) AS from_node, endNode(rel) AS to_node
                RETURN DISTINCT
                    from_node.name AS source_name,
                    labels(from_node)[0] AS source_type,
                    from_node.filePath AS source_path,
                    to_node.name AS target_name,
                    labels(to_node)[0] AS target_type,
                    to_node.filePath AS target_path,
                    type(rel) AS relationship
            }}

            RETURN source_name, source_type, source_path,
                   target_name, target_type, target_path, relationship
            LIMIT 500
        """

        result = await neo4j_client.query_code_structure(query)

        # Build nodes and edges
        nodes_map: dict[str, FlowGraphNode] = {}
        edges: list[FlowGraphEdge] = []
        graph_entry_points: set[str] = set()
        exit_points: set[str] = set()

        # First, add the entry points we found
        for ep in entry_point_results:
            ep_name = ep.get("name")
            ep_type = ep.get("type", "unknown")
            ep_path = ep.get("path", "")
            if ep_name and ep_name not in nodes_map:
                layer = get_node_layer(ep_type, ep_name)
                node_id = f"{ep_type}_{ep_name}".replace(" ", "_")
                nodes_map[ep_name] = FlowGraphNode(
                    id=node_id,
                    name=ep_name,
                    type=ep_type.lower(),
                    layer='controller',  # Entry points are controllers
                    path=ep_path,
                )
                graph_entry_points.add(node_id)

        for record in result.get("nodes", []):
            source_name = record.get("source_name")
            source_type = record.get("source_type", "")
            source_path = record.get("source_path", "")

            if source_name and source_name not in nodes_map:
                layer = get_node_layer(source_type, source_name)
                node_id = f"{source_type}_{source_name}".replace(" ", "_")
                nodes_map[source_name] = FlowGraphNode(
                    id=node_id,
                    name=source_name,
                    type=source_type.lower(),
                    layer=layer,
                    path=source_path,
                )
                # Mark as entry point if it's one of our found entry points
                if source_name in entry_point_names:
                    graph_entry_points.add(node_id)
                # Data layer nodes are exit points
                elif layer == 'data':
                    exit_points.add(node_id)

            target_name = record.get("target_name")
            target_type = record.get("target_type", "")
            target_path = record.get("target_path", "")
            relationship = record.get("relationship")

            if target_name and target_name not in nodes_map:
                layer = get_node_layer(target_type, target_name)
                node_id = f"{target_type}_{target_name}".replace(" ", "_")
                nodes_map[target_name] = FlowGraphNode(
                    id=node_id,
                    name=target_name,
                    type=target_type.lower(),
                    layer=layer,
                    path=target_path,
                )
                if target_name in entry_point_names:
                    graph_entry_points.add(node_id)
                elif layer == 'data':
                    exit_points.add(node_id)

            # Add edge
            if source_name and target_name and relationship:
                source_id = f"{source_type}_{source_name}".replace(" ", "_")
                target_id = f"{target_type}_{target_name}".replace(" ", "_")
                edges.append(FlowGraphEdge(
                    source=source_id,
                    target=target_id,
                    relationship=relationship,
                    label=relationship.replace("_", " ").title(),
                ))

        logger.info(f"[FLOW-GRAPH] Built graph with {len(nodes_map)} nodes, {len(edges)} edges, {len(graph_entry_points)} entry points")

        return FlowGraphResponse(
            success=True,
            nodes=list(nodes_map.values()),
            edges=edges,
            entry_points=list(graph_entry_points),
            exit_points=list(exit_points),
        )

    except Exception as e:
        logger.error(f"[FLOW-GRAPH] Failed to build flow graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))
