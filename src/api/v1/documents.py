"""
Document management endpoints.
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from src.api.deps import get_document_service
from src.core.constants import DocumentType, VerificationStatus
from src.core.exceptions import DocumentNotFoundError
from src.core.logging import get_logger
from src.services.document_service import DocumentService

logger = get_logger(__name__)

router = APIRouter()


# Response models
class VerificationInfo(BaseModel):
    """Verification information for a document."""

    status: str
    confidence: float
    verified_claims: int
    total_claims: int


class DocumentResponse(BaseModel):
    """Response model for document."""

    document_id: str
    type: str
    title: str
    content: str
    format: str = "markdown"
    metadata: dict[str, Any]
    verification_status: str
    confidence_score: float
    created_at: str
    updated_at: str


class DocumentListItem(BaseModel):
    """List item for document listing."""

    document_id: str
    type: str
    title: str
    verification_status: str
    confidence: float
    created_at: str


class DocumentListResponse(BaseModel):
    """Response for document listing."""

    documents: list[DocumentListItem]
    total: int
    page: int
    page_size: int


class GenerateBRDRequest(BaseModel):
    """Request to generate a BRD."""

    session_id: str
    component_name: str
    codebase_path: str = "/codebase"
    preferences: Optional[dict[str, Any]] = None


class GenerateEpicRequest(BaseModel):
    """Request to generate Epics from a BRD."""

    session_id: str
    brd_document_id: str
    codebase_path: str = "/codebase"
    preferences: Optional[dict[str, Any]] = None


class GenerateBacklogRequest(BaseModel):
    """Request to generate Backlog items from an Epic."""

    session_id: str
    epic_id: str
    codebase_path: str = "/codebase"
    preferences: Optional[dict[str, Any]] = None


class WorkflowResultResponse(BaseModel):
    """Response for workflow execution."""

    workflow_id: str
    workflow_type: str
    status: str
    document_id: Optional[str] = None
    artifacts: list[dict[str, Any]] = []
    error: Optional[str] = None
    duration_seconds: float


@router.post("/documents/generate/brd", response_model=WorkflowResultResponse)
async def generate_brd(
    request: GenerateBRDRequest,
    document_service: DocumentService = Depends(get_document_service),
) -> WorkflowResultResponse:
    """
    Generate a Business Requirements Document (BRD) for a component.
    """
    logger.info(
        "Generating BRD",
        session_id=request.session_id,
        component=request.component_name,
    )

    result = await document_service.generate_brd(
        session_id=request.session_id,
        component_name=request.component_name,
        codebase_path=request.codebase_path,
        preferences=request.preferences,
    )

    return WorkflowResultResponse(
        workflow_id=result.workflow_id,
        workflow_type=result.workflow_type,
        status=result.status.value,
        document_id=result.document.id if result.document else None,
        artifacts=result.artifacts,
        error=result.error,
        duration_seconds=result.duration_seconds,
    )


@router.post("/documents/generate/epics", response_model=WorkflowResultResponse)
async def generate_epics(
    request: GenerateEpicRequest,
    document_service: DocumentService = Depends(get_document_service),
) -> WorkflowResultResponse:
    """
    Generate Epics from a BRD document.
    """
    logger.info(
        "Generating Epics",
        session_id=request.session_id,
        brd_id=request.brd_document_id,
    )

    try:
        result = await document_service.generate_epics(
            session_id=request.session_id,
            brd_document_id=request.brd_document_id,
            codebase_path=request.codebase_path,
            preferences=request.preferences,
        )

        return WorkflowResultResponse(
            workflow_id=result.workflow_id,
            workflow_type=result.workflow_type,
            status=result.status.value,
            document_id=result.document.id if result.document else None,
            artifacts=result.artifacts,
            error=result.error,
            duration_seconds=result.duration_seconds,
        )
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/documents/generate/backlog", response_model=WorkflowResultResponse)
async def generate_backlog(
    request: GenerateBacklogRequest,
    document_service: DocumentService = Depends(get_document_service),
) -> WorkflowResultResponse:
    """
    Generate Backlog items from an Epic.
    """
    logger.info(
        "Generating Backlog",
        session_id=request.session_id,
        epic_id=request.epic_id,
    )

    try:
        result = await document_service.generate_backlog(
            session_id=request.session_id,
            epic_id=request.epic_id,
            codebase_path=request.codebase_path,
            preferences=request.preferences,
        )

        return WorkflowResultResponse(
            workflow_id=result.workflow_id,
            workflow_type=result.workflow_type,
            status=result.status.value,
            document_id=result.document.id if result.document else None,
            artifacts=result.artifacts,
            error=result.error,
            duration_seconds=result.duration_seconds,
        )
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """
    Retrieve a generated document by ID.
    """
    logger.info("Retrieving document", document_id=document_id)

    document = await document_service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    return DocumentResponse(
        document_id=document.id,
        type=document.type.value,
        title=document.title,
        content=document.content,
        format="markdown",
        metadata=document.metadata,
        verification_status=document.verification_status.value,
        confidence_score=document.confidence_score,
        created_at=document.created_at.isoformat(),
        updated_at=document.updated_at.isoformat(),
    )


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    format: str = Query(default="markdown", regex="^(markdown|json|html)$"),
    document_service: DocumentService = Depends(get_document_service),
) -> Response:
    """
    Download a document in the specified format.
    """
    logger.info("Downloading document", document_id=document_id, format=format)

    try:
        content = await document_service.export_document(document_id, format)

        # Determine content type and file extension
        if format == "markdown":
            content_type = "text/markdown"
            extension = "md"
        elif format == "json":
            content_type = "application/json"
            extension = "json"
        else:  # html
            content_type = "text/html"
            extension = "html"

        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={document_id}.{extension}"
            },
        )
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    session_id: Optional[str] = Query(default=None),
    doc_type: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    """
    List documents with optional filtering.
    """
    logger.info(
        "Listing documents",
        session_id=session_id,
        doc_type=doc_type,
        page=page,
    )

    # Convert doc_type string to enum if provided
    document_type = None
    if doc_type:
        try:
            document_type = DocumentType(doc_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid document type: {doc_type}")

    documents = await document_service.list_documents(
        session_id=session_id,
        document_type=document_type,
    )

    # Paginate
    total = len(documents)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = documents[start:end]

    return DocumentListResponse(
        documents=[
            DocumentListItem(
                document_id=d.id,
                type=d.type.value,
                title=d.title,
                verification_status=d.verification_status.value,
                confidence=d.confidence_score,
                created_at=d.created_at.isoformat(),
            )
            for d in paginated
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


class UpdateDocumentRequest(BaseModel):
    """Request to update a document."""

    title: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@router.patch("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    request: UpdateDocumentRequest,
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """
    Update a document.
    """
    logger.info("Updating document", document_id=document_id)

    try:
        document = await document_service.update_document(
            document_id=document_id,
            title=request.title,
            content=request.content,
            metadata=request.metadata,
        )

        return DocumentResponse(
            document_id=document.id,
            type=document.type.value,
            title=document.title,
            content=document.content,
            format="markdown",
            metadata=document.metadata,
            verification_status=document.verification_status.value,
            confidence_score=document.confidence_score,
            created_at=document.created_at.isoformat(),
            updated_at=document.updated_at.isoformat(),
        )
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> dict[str, str]:
    """
    Delete a document.
    """
    logger.info("Deleting document", document_id=document_id)

    deleted = await document_service.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    return {"status": "deleted", "document_id": document_id}


# Hierarchy endpoints
class DocumentHierarchyResponse(BaseModel):
    """Response for document hierarchy."""

    document: dict[str, Any]
    children: list[Any]


@router.get("/documents/{document_id}/hierarchy", response_model=DocumentHierarchyResponse)
async def get_document_hierarchy(
    document_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentHierarchyResponse:
    """
    Get the full document hierarchy starting from a document.
    """
    logger.info("Getting document hierarchy", document_id=document_id)

    try:
        hierarchy = await document_service.get_document_hierarchy(document_id)
        return DocumentHierarchyResponse(**hierarchy)
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")


# Epic endpoints
class EpicListResponse(BaseModel):
    """Response for epic listing."""

    epics: list[DocumentListItem]
    total: int


@router.get("/documents/{document_id}/epics", response_model=EpicListResponse)
async def list_epics_for_document(
    document_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> EpicListResponse:
    """
    List epics generated from a BRD document.
    """
    logger.info("Listing epics for document", document_id=document_id)

    epics = await document_service.list_documents(
        parent_document_id=document_id,
        document_type=DocumentType.EPIC,
    )

    return EpicListResponse(
        epics=[
            DocumentListItem(
                document_id=e.id,
                type=e.type.value,
                title=e.title,
                verification_status=e.verification_status.value,
                confidence=e.confidence_score,
                created_at=e.created_at.isoformat(),
            )
            for e in epics
        ],
        total=len(epics),
    )


# Backlog endpoints
class BacklogListResponse(BaseModel):
    """Response for backlog listing."""

    items: list[DocumentListItem]
    total: int


@router.get("/epics/{epic_id}/backlog", response_model=BacklogListResponse)
async def list_backlog_for_epic(
    epic_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> BacklogListResponse:
    """
    List backlog items for an epic.
    """
    logger.info("Listing backlog for epic", epic_id=epic_id)

    items = await document_service.list_documents(
        parent_document_id=epic_id,
        document_type=DocumentType.BACKLOG_ITEM,
    )

    return BacklogListResponse(
        items=[
            DocumentListItem(
                document_id=i.id,
                type=i.type.value,
                title=i.title,
                verification_status=i.verification_status.value,
                confidence=i.confidence_score,
                created_at=i.created_at.isoformat(),
            )
            for i in items
        ],
        total=len(items),
    )
