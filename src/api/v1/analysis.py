"""
Codebase analysis endpoints.
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import get_analysis_service, get_tool_registry, get_cache
from src.core.logging import get_logger
from src.mcp.tool_registry import MCPToolRegistry
from src.repositories.cache_repo import InMemoryCacheRepository
from src.services.analysis_service import AnalysisService

logger = get_logger(__name__)

router = APIRouter()


# Request/Response models
class AnalysisRequest(BaseModel):
    """Request for codebase analysis."""

    component_name: str = Field(..., description="Name of the component to analyze")
    codebase_path: str = Field(default="/codebase", description="Path to the codebase")
    analysis_type: str = Field(
        default="standard",
        description="Type of analysis (quick, standard, deep)",
    )
    focus_areas: Optional[list[str]] = Field(
        default=None,
        description="Specific areas to focus on",
    )


class ComponentInfo(BaseModel):
    """Component information."""

    name: str
    type: str
    path: str
    description: str = ""
    dependencies: list[str] = []
    dependents: list[str] = []


class ArchitectureResult(BaseModel):
    """Architecture analysis result."""

    layers: list[str] = []
    patterns: list[str] = []
    structure: dict[str, Any] = {}


class VerificationInfo(BaseModel):
    """Verification information."""

    confidence: float
    evidence_count: int


class AnalysisResponse(BaseModel):
    """Response for codebase analysis."""

    analysis_id: str
    codebase_path: str
    components: list[ComponentInfo]
    architecture: ArchitectureResult
    metrics: dict[str, Any]
    insights: list[str]
    verification: VerificationInfo
    created_at: str


@router.post("/analysis/codebase", response_model=AnalysisResponse)
async def analyze_codebase(
    request: AnalysisRequest,
    analysis_service: AnalysisService = Depends(get_analysis_service),
    cache: InMemoryCacheRepository = Depends(get_cache),
) -> AnalysisResponse:
    """
    Analyze a codebase.

    Supports different analysis types:
    - quick: Fast overview of codebase structure
    - standard: Detailed analysis with component relationships
    - deep: Comprehensive analysis with architecture patterns
    """
    logger.info(
        "Analyzing codebase",
        path=request.codebase_path,
        type=request.analysis_type,
    )

    # Check cache
    cache_key = f"analysis:{request.codebase_path}:{request.analysis_type}"
    cached = await cache.get(cache_key)
    if cached:
        logger.info("Returning cached analysis")
        return AnalysisResponse(**cached)

    # Perform analysis
    result = await analysis_service.analyze_codebase(
        codebase_path=request.codebase_path,
        depth=request.analysis_type,
        focus_areas=request.focus_areas,
    )

    response = AnalysisResponse(
        analysis_id=f"analysis_{datetime.utcnow().timestamp()}",
        codebase_path=result.codebase_path,
        components=[
            ComponentInfo(
                name=c.name,
                type=c.type,
                path=c.path,
                description=c.description,
                dependencies=c.dependencies,
                dependents=c.dependents,
            )
            for c in result.components
        ],
        architecture=ArchitectureResult(
            layers=result.architecture.get("layers", []),
            patterns=result.architecture.get("patterns", []),
            structure=result.architecture.get("structure", {}),
        ),
        metrics=result.metrics,
        insights=result.insights,
        verification=VerificationInfo(
            confidence=0.85,
            evidence_count=len(result.components),
        ),
        created_at=result.analyzed_at.isoformat(),
    )

    # Cache result
    await cache.set(cache_key, response.dict(), ttl_seconds=3600)

    return response


class ComponentAnalysisResponse(BaseModel):
    """Response for component analysis."""

    component: ComponentInfo
    call_chain: list[dict[str, Any]] = []
    data_flows: list[dict[str, Any]] = []
    verification: VerificationInfo


@router.get("/analysis/component/{component_name}", response_model=ComponentAnalysisResponse)
async def analyze_component(
    component_name: str,
    codebase_path: str = Query(default="/codebase"),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> ComponentAnalysisResponse:
    """
    Analyze a specific component.
    """
    logger.info("Analyzing component", component=component_name)

    result = await analysis_service.analyze_component(
        codebase_path=codebase_path,
        component_name=component_name,
    )

    return ComponentAnalysisResponse(
        component=ComponentInfo(
            name=result.name,
            type=result.type,
            path=result.path,
            description=result.description,
            dependencies=result.dependencies,
            dependents=result.dependents,
        ),
        call_chain=[],  # Would be populated from actual analysis
        data_flows=[],  # Would be populated from actual analysis
        verification=VerificationInfo(
            confidence=0.8,
            evidence_count=1,
        ),
    )


class DependencyGraphResponse(BaseModel):
    """Response for dependency graph."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    root: Optional[str] = None
    depth: int


@router.get("/analysis/dependencies", response_model=DependencyGraphResponse)
async def get_dependency_graph(
    codebase_path: str = Query(default="/codebase"),
    root_component: Optional[str] = Query(default=None),
    max_depth: int = Query(default=3, ge=1, le=10),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> DependencyGraphResponse:
    """
    Get the dependency graph for the codebase or a specific component.
    """
    logger.info(
        "Getting dependency graph",
        root=root_component,
        depth=max_depth,
    )

    result = await analysis_service.get_dependency_graph(
        codebase_path=codebase_path,
        root_component=root_component,
        max_depth=max_depth,
    )

    return DependencyGraphResponse(**result)


class EntryPointsResponse(BaseModel):
    """Response for entry points."""

    entry_points: list[dict[str, Any]]
    total: int


@router.get("/analysis/entry-points", response_model=EntryPointsResponse)
async def find_entry_points(
    codebase_path: str = Query(default="/codebase"),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> EntryPointsResponse:
    """
    Find entry points in the codebase (APIs, main functions, etc.).
    """
    logger.info("Finding entry points", path=codebase_path)

    result = await analysis_service.find_entry_points(codebase_path)

    return EntryPointsResponse(
        entry_points=result,
        total=len(result),
    )


class SearchRequest(BaseModel):
    """Request for codebase search."""

    query: str = Field(..., description="Search query")
    search_type: str = Field(
        default="semantic",
        description="Type of search (semantic, keyword, pattern)",
    )
    codebase_path: str = Field(default="/codebase")


class SearchResponse(BaseModel):
    """Response for codebase search."""

    results: list[dict[str, Any]]
    total: int
    query: str
    search_type: str


@router.post("/analysis/search", response_model=SearchResponse)
async def search_codebase(
    request: SearchRequest,
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> SearchResponse:
    """
    Search the codebase.

    Supports different search types:
    - semantic: AI-powered semantic search
    - keyword: Simple text matching
    - pattern: Regex pattern matching
    """
    logger.info(
        "Searching codebase",
        query=request.query,
        type=request.search_type,
    )

    results = await analysis_service.search_codebase(
        codebase_path=request.codebase_path,
        query=request.query,
        search_type=request.search_type,
    )

    return SearchResponse(
        results=results,
        total=len(results),
        query=request.query,
        search_type=request.search_type,
    )


class ComponentListResponse(BaseModel):
    """Response for component listing."""

    components: list[ComponentInfo]
    total: int


@router.get("/analysis/components", response_model=ComponentListResponse)
async def list_components(
    codebase_path: str = Query(default="/codebase"),
    component_type: Optional[str] = Query(default=None),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> ComponentListResponse:
    """
    List discovered components in the codebase.
    """
    logger.info("Listing components", codebase_path=codebase_path)

    result = await analysis_service.analyze_codebase(
        codebase_path=codebase_path,
        depth="quick",
    )

    components = result.components
    if component_type:
        components = [c for c in components if c.type == component_type]

    return ComponentListResponse(
        components=[
            ComponentInfo(
                name=c.name,
                type=c.type,
                path=c.path,
                description=c.description,
                dependencies=c.dependencies,
                dependents=c.dependents,
            )
            for c in components
        ],
        total=len(components),
    )


class GraphQueryRequest(BaseModel):
    """Request for custom graph query."""

    query: str = Field(..., description="Cypher query")
    parameters: dict[str, Any] = Field(default_factory=dict)


class GraphQueryResponse(BaseModel):
    """Response for graph query."""

    nodes: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    execution_time_ms: float


@router.post("/analysis/graph/query", response_model=GraphQueryResponse)
async def execute_graph_query(
    request: GraphQueryRequest,
    tool_registry: MCPToolRegistry = Depends(get_tool_registry),
) -> GraphQueryResponse:
    """
    Execute a custom graph query.

    Note: This endpoint is for advanced users who understand Cypher.
    """
    logger.info("Executing graph query", query=request.query[:50])

    start_time = datetime.utcnow()

    try:
        result = await tool_registry.execute_tool(
            "neo4j_execute_query",
            {
                "query": request.query,
                "parameters": request.parameters,
            }
        )

        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Parse result into nodes and relationships
        nodes = []
        relationships = []

        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    if "source" in item and "target" in item:
                        relationships.append(item)
                    else:
                        nodes.append(item)

        return GraphQueryResponse(
            nodes=nodes,
            relationships=relationships,
            execution_time_ms=execution_time,
        )

    except Exception as e:
        logger.exception("Graph query failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Graph query failed: {str(e)}",
        )
