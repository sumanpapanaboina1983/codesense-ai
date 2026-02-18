"""API Routes for Code Assistant Chat.

Provides endpoints for:
- Asking natural language questions about a codebase
- Getting AI-generated answers with code citations
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database.config import get_async_session
from ..database.models import RepositoryDB
from ..models.repository import AnalysisStatus
from .chat_models import ChatRequest, ChatResponse, ChatErrorResponse
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..services.code_assistant_service import CodeAssistantService

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/repositories", tags=["Code Assistant"])

# Global service instances
_neo4j_client: Optional[Neo4jMCPClient] = None
_code_assistant: Optional["CodeAssistantService"] = None


async def get_neo4j_client() -> Neo4jMCPClient:
    """Get Neo4j client instance."""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jMCPClient()
        await _neo4j_client.connect()
    return _neo4j_client


async def get_code_assistant() -> "CodeAssistantService":
    """Get code assistant service instance."""
    global _code_assistant
    if _code_assistant is None:
        # Lazy import to avoid circular dependency
        from ..services.code_assistant_service import CodeAssistantService

        neo4j_client = await get_neo4j_client()
        # Create a dummy filesystem client - will be configured per-repo
        filesystem_client = FilesystemMCPClient()
        await filesystem_client.connect()
        _code_assistant = CodeAssistantService(
            neo4j_client=neo4j_client,
            filesystem_client=filesystem_client,
        )
    return _code_assistant


async def get_db_session():
    """Database session dependency."""
    async with get_async_session() as session:
        yield session


# =============================================================================
# Response Models
# =============================================================================


class ChatResponseWrapper(BaseModel):
    """Wrapper for chat response."""
    success: bool = True
    data: ChatResponse


class RepositoryNotAnalyzedError(BaseModel):
    """Error when repository is not analyzed."""
    success: bool = False
    error: str = "Repository not analyzed"
    detail: str = Field(
        default="Please analyze the repository first before asking questions."
    )


# =============================================================================
# Chat Endpoints
# =============================================================================


@router.post(
    "/{repository_id}/chat",
    response_model=ChatResponseWrapper,
    responses={
        400: {"model": ChatErrorResponse},
        404: {"model": ChatErrorResponse},
        422: {"model": RepositoryNotAnalyzedError},
    },
    summary="Ask a question about the codebase",
    description="""
    Ask a natural language question about a repository's codebase.

    The repository must be analyzed before you can ask questions.

    The response includes:
    - **answer**: Natural language answer with inline citations like [1], [2]
    - **citations**: List of code snippets referenced in the answer
    - **related_entities**: Code entities related to the answer for further exploration
    - **follow_up_suggestions**: Suggested follow-up questions

    Example questions:
    - "What classes exist in this codebase?"
    - "Where is authentication handled?"
    - "What depends on the UserService class?"
    - "How does the API routing work?"
    """,
)
async def chat_with_codebase(
    repository_id: str,
    request: ChatRequest,
    code_assistant: "CodeAssistantService" = Depends(get_code_assistant),
    session: AsyncSession = Depends(get_db_session),
) -> ChatResponseWrapper:
    """Ask a question about a repository's codebase."""
    # Validate repository exists
    result = await session.execute(
        select(RepositoryDB).where(RepositoryDB.id == repository_id)
    )
    db_repo = result.scalar_one_or_none()

    if not db_repo:
        raise HTTPException(
            status_code=404,
            detail="Repository not found"
        )

    # Check if repository is analyzed
    if db_repo.analysis_status != AnalysisStatus.COMPLETED.value:
        raise HTTPException(
            status_code=422,
            detail="Repository is not analyzed. Please analyze the repository first before asking questions."
        )

    # Get workspace root
    workspace_root = db_repo.local_path
    if not workspace_root:
        raise HTTPException(
            status_code=400,
            detail="Repository has no local path configured"
        )

    try:
        # Answer the question
        response = await code_assistant.answer_question(
            repository_id=repository_id,
            request=request,
            workspace_root=workspace_root,
        )

        return ChatResponseWrapper(data=response)

    except Exception as e:
        logger.exception(f"Failed to answer question for repo {repository_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process question: {str(e)}"
        )
