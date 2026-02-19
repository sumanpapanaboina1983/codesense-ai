"""API routes for feature flow extraction.

This module provides endpoints for:
- Tracing complete feature flows from UI to database
- Extracting method call chains
- Mapping data flow between layers
- Generating sequence diagrams
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.feature_flow import FeatureFlowService
from ..models.flow_context import (
    CallChainRequest,
    CallChainResponse,
    DataMapping,
    FeatureFlow,
    FeatureFlowRequest,
    FeatureFlowResponse,
    ImplementationMapping,
    SQLOperation,
    TechnicalArchitectureView,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/flow", tags=["Feature Flow"])

# Global service instance (will be set during app startup)
_flow_service: Optional[FeatureFlowService] = None


def get_flow_service() -> FeatureFlowService:
    """Get the feature flow service instance."""
    if _flow_service is None:
        raise HTTPException(
            status_code=503,
            detail="Feature flow service not initialized",
        )
    return _flow_service


def set_flow_service(service: FeatureFlowService) -> None:
    """Set the feature flow service instance."""
    global _flow_service
    _flow_service = service
    logger.info("Feature flow service registered with API routes")


# Request/Response models


class TraceRequest(BaseModel):
    """Request for tracing a feature flow."""

    entry_point: str = Field(..., description="File path, name, or entity ID of entry point")
    entry_point_type: str = Field(
        default="auto",
        description="Type hint: jsp, webflow, controller, or auto",
    )
    include_sql: bool = Field(default=True, description="Include SQL operations")
    include_data_mappings: bool = Field(default=True, description="Include data mappings")
    max_depth: int = Field(default=10, ge=1, le=20, description="Maximum traversal depth")


class CallChainApiRequest(BaseModel):
    """Request for call chain extraction."""

    method_id: str = Field(..., description="Entity ID of the method")
    direction: str = Field(
        default="downstream",
        description="Direction: downstream (who this calls) or upstream (who calls this)",
    )
    max_depth: int = Field(default=10, ge=1, le=20, description="Maximum depth")


class DataMappingRequest(BaseModel):
    """Request for data flow mapping."""

    field_name: str = Field(..., description="Field name or path to trace")
    jsp_file: Optional[str] = Field(default=None, description="Optional JSP file to scope search")


class ImplementationMappingRequest(BaseModel):
    """Request for generating implementation mapping."""

    entry_points: list[str] = Field(
        ...,
        description="List of entry point IDs or paths",
        min_length=1,
    )


class DiagramResponse(BaseModel):
    """Response containing a diagram."""

    diagram: str = Field(..., description="Mermaid diagram markdown")
    format: str = Field(default="mermaid", description="Diagram format")


# API Endpoints


@router.post("/trace", response_model=FeatureFlowResponse)
async def trace_feature_flow(
    request: TraceRequest,
    service: FeatureFlowService = Depends(get_flow_service),
) -> FeatureFlowResponse:
    """Trace complete feature flow from entry point to database.

    This endpoint extracts the full flow through all architectural layers:
    - UI (JSP, HTML)
    - Flow (WebFlow, Spring MVC)
    - Controller (Actions, Controllers)
    - Service (Business logic, Builders)
    - DAO (Data access, Repositories)
    - Database (SQL statements)

    Returns flow steps with line numbers and signatures.
    """
    logger.info(f"Tracing feature flow from: {request.entry_point}")

    return await service.extract_feature_flow(
        entry_point=request.entry_point,
        entry_point_type=request.entry_point_type,
        include_sql=request.include_sql,
        include_data_mappings=request.include_data_mappings,
        max_depth=request.max_depth,
    )


@router.get("/trace/{entry_point}", response_model=FeatureFlowResponse)
async def trace_feature_flow_get(
    entry_point: str,
    entry_point_type: str = Query(default="auto"),
    include_sql: bool = Query(default=True),
    include_data_mappings: bool = Query(default=True),
    max_depth: int = Query(default=10, ge=1, le=20),
    service: FeatureFlowService = Depends(get_flow_service),
) -> FeatureFlowResponse:
    """GET version of trace endpoint for simpler access."""
    logger.info(f"Tracing feature flow (GET) from: {entry_point}")

    return await service.extract_feature_flow(
        entry_point=entry_point,
        entry_point_type=entry_point_type,
        include_sql=include_sql,
        include_data_mappings=include_data_mappings,
        max_depth=max_depth,
    )


@router.post("/call-chain", response_model=CallChainResponse)
async def get_call_chain(
    request: CallChainApiRequest,
    service: FeatureFlowService = Depends(get_flow_service),
) -> CallChainResponse:
    """Extract method call chain.

    Returns the chain of method calls either:
    - downstream: methods that this method calls
    - upstream: methods that call this method

    Each step includes line numbers and method signatures.
    """
    logger.info(f"Getting call chain for: {request.method_id}")

    return await service.get_call_chain(
        method_id=request.method_id,
        direction=request.direction,
        max_depth=request.max_depth,
    )


@router.post("/data-mapping", response_model=list[DataMapping])
async def get_data_mapping(
    request: DataMappingRequest,
    service: FeatureFlowService = Depends(get_flow_service),
) -> list[DataMapping]:
    """Map data flow from UI field to entity field.

    Traces how a form field maps through:
    - UI field binding (JSP path attribute)
    - Entity/model field
    - Database column

    Returns validation rules and data types.
    """
    logger.info(f"Mapping data flow for: {request.field_name}")

    return await service.map_data_flow(
        form_field=request.field_name,
        jsp_file=request.jsp_file,
    )


@router.get("/sql-operations/{dao_class}", response_model=list[SQLOperation])
async def get_sql_operations(
    dao_class: str,
    service: FeatureFlowService = Depends(get_flow_service),
) -> list[SQLOperation]:
    """Get SQL operations in a DAO class.

    Returns all SQL statements (SELECT, INSERT, UPDATE, DELETE, etc.)
    detected in the specified DAO class, including:
    - Statement type
    - Table name
    - Columns involved
    - Raw SQL (if available)
    - Source method and line number
    """
    logger.info(f"Getting SQL operations for: {dao_class}")

    return await service.find_sql_operations(dao_class)


@router.get("/entry-points", response_model=list[dict])
async def find_entry_points(
    keyword: str = Query(..., min_length=2, description="Keyword to search for"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
    service: FeatureFlowService = Depends(get_flow_service),
) -> list[dict]:
    """Find entry points matching a keyword.

    Searches for:
    - JSP pages
    - WebFlow definitions
    - Controller classes

    Returns entry points ranked by relevance.
    """
    logger.info(f"Finding entry points for: {keyword}")

    return await service.find_entry_points(keyword, limit)


@router.post("/implementation-mapping", response_model=ImplementationMapping)
async def generate_implementation_mapping(
    request: ImplementationMappingRequest,
    service: FeatureFlowService = Depends(get_flow_service),
) -> ImplementationMapping:
    """Generate implementation mapping table.

    Creates a tabular mapping suitable for BRD Section 9:
    | Operation | UI | Controller | Service | DAO | Database |

    Each row shows the component at each layer for an operation.
    """
    logger.info(f"Generating implementation mapping for {len(request.entry_points)} entry points")

    return await service.generate_implementation_mapping(request.entry_points)


@router.get("/implementation-mapping/markdown")
async def get_implementation_mapping_markdown(
    entry_points: str = Query(
        ...,
        description="Comma-separated entry point IDs or paths",
    ),
    service: FeatureFlowService = Depends(get_flow_service),
) -> dict:
    """Get implementation mapping as markdown table.

    Returns markdown-formatted table for direct inclusion in BRD.
    """
    entry_point_list = [ep.strip() for ep in entry_points.split(",")]
    logger.info(f"Generating markdown implementation mapping for {len(entry_point_list)} entry points")

    mapping = await service.generate_implementation_mapping(entry_point_list)
    return {"markdown": mapping.to_markdown_table()}


@router.get("/technical-architecture/{entry_point}", response_model=TechnicalArchitectureView)
async def get_technical_architecture(
    entry_point: str,
    service: FeatureFlowService = Depends(get_flow_service),
) -> TechnicalArchitectureView:
    """Get technical architecture view.

    Returns a layered view of components for BRD Section 7,
    showing how the feature is implemented across layers.
    """
    logger.info(f"Getting technical architecture for: {entry_point}")

    return await service.generate_technical_architecture(entry_point)


@router.get("/technical-architecture/{entry_point}/markdown")
async def get_technical_architecture_markdown(
    entry_point: str,
    service: FeatureFlowService = Depends(get_flow_service),
) -> dict:
    """Get technical architecture as markdown.

    Returns markdown-formatted architecture view for direct inclusion in BRD.
    """
    logger.info(f"Generating markdown technical architecture for: {entry_point}")

    view = await service.generate_technical_architecture(entry_point)
    return {"markdown": view.to_markdown()}


@router.get("/diagram/{entry_point}", response_model=DiagramResponse)
async def get_sequence_diagram(
    entry_point: str,
    service: FeatureFlowService = Depends(get_flow_service),
) -> DiagramResponse:
    """Generate Mermaid sequence diagram.

    Creates a sequence diagram showing the flow of calls
    from UI through to database for a feature.
    """
    logger.info(f"Generating sequence diagram for: {entry_point}")

    diagram = await service.generate_sequence_diagram(entry_point)
    return DiagramResponse(diagram=diagram, format="mermaid")


@router.get("/brd-sections/{entry_point}")
async def get_brd_sections(
    entry_point: str,
    format: str = Query(default="comprehensive", description="Output format: comprehensive or compact"),
    service: FeatureFlowService = Depends(get_flow_service),
) -> dict:
    """Get both Technical Architecture and Implementation Mapping for BRD.

    Returns pre-formatted markdown sections ready for inclusion in BRD:
    - Section 7: Technical Architecture (layered view with file paths)
    - Section 9: Implementation Mapping (tabular operation-to-code mapping)

    Use format=comprehensive for detailed output or format=compact for brief output.
    """
    logger.info(f"Generating BRD sections for: {entry_point}")

    # Get the feature flow
    response = await service.extract_feature_flow(
        entry_point=entry_point,
        entry_point_type="auto",
        include_sql=True,
        include_data_mappings=True,
        max_depth=10,
    )

    if not response.success or not response.feature_flow:
        return {
            "success": False,
            "error": response.error or "Failed to extract feature flow",
            "technical_architecture": "",
            "implementation_mapping": "",
        }

    flow = response.feature_flow

    # Generate technical architecture view
    from ..models.flow_context import TechnicalArchitectureView, ImplementationMapping

    tech_arch_view = TechnicalArchitectureView.from_feature_flow(flow)
    impl_mapping = ImplementationMapping.from_feature_flows([flow])

    if format == "compact":
        tech_arch_md = tech_arch_view.to_compact_markdown()
        impl_mapping_md = impl_mapping.to_compact_table()
    else:
        tech_arch_md = tech_arch_view.to_markdown()
        impl_mapping_md = impl_mapping.to_markdown_table()

    return {
        "success": True,
        "entry_point": entry_point,
        "feature_name": flow.feature_name,
        "technical_architecture": tech_arch_md,
        "implementation_mapping": impl_mapping_md,
        "flow_steps_count": len(flow.flow_steps),
        "sql_operations_count": len(flow.sql_operations),
        "data_mappings_count": len(flow.data_mappings),
    }


@router.post("/brd-sections/batch")
async def get_brd_sections_batch(
    request: ImplementationMappingRequest,
    format: str = Query(default="comprehensive", description="Output format: comprehensive or compact"),
    service: FeatureFlowService = Depends(get_flow_service),
) -> dict:
    """Get BRD sections for multiple entry points.

    Combines flows from multiple entry points into unified BRD sections.
    Useful for features that span multiple entry points.
    """
    logger.info(f"Generating batch BRD sections for {len(request.entry_points)} entry points")

    from ..models.flow_context import TechnicalArchitectureView, ImplementationMapping, FeatureFlow

    all_flows: list[FeatureFlow] = []
    errors = []

    for entry_point in request.entry_points:
        response = await service.extract_feature_flow(
            entry_point=entry_point,
            entry_point_type="auto",
            include_sql=True,
            include_data_mappings=True,
            max_depth=10,
        )

        if response.success and response.feature_flow:
            all_flows.append(response.feature_flow)
        else:
            errors.append({"entry_point": entry_point, "error": response.error})

    if not all_flows:
        return {
            "success": False,
            "error": "No flows could be extracted",
            "errors": errors,
        }

    # Generate combined technical architecture
    tech_arch_sections = []
    for flow in all_flows:
        view = TechnicalArchitectureView.from_feature_flow(flow)
        if format == "compact":
            tech_arch_sections.append(view.to_compact_markdown())
        else:
            tech_arch_sections.append(view.to_markdown())

    # Generate combined implementation mapping
    impl_mapping = ImplementationMapping.from_feature_flows(all_flows)
    if format == "compact":
        impl_mapping_md = impl_mapping.to_compact_table()
    else:
        impl_mapping_md = impl_mapping.to_markdown_table()

    return {
        "success": True,
        "entry_points_processed": len(all_flows),
        "entry_points_failed": len(errors),
        "technical_architecture": "\n\n---\n\n".join(tech_arch_sections),
        "implementation_mapping": impl_mapping_md,
        "errors": errors if errors else None,
    }


# Health check endpoint


@router.get("/health")
async def health_check() -> dict:
    """Check flow service health."""
    return {
        "status": "healthy" if _flow_service is not None else "not initialized",
        "service": "FeatureFlowService",
    }
