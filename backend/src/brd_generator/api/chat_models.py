"""Request/Response models for Chat API."""

from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    question: str = Field(
        ...,
        description="Natural language question about the codebase",
        min_length=3,
        examples=["What classes exist in this codebase?", "How does authentication work?"],
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Optional conversation ID for maintaining context across messages",
    )


class Citation(BaseModel):
    """A code citation reference."""

    id: str = Field(..., description="Unique identifier for the citation (e.g., '1', '2')")
    file_path: str = Field(..., description="Path to the source file")
    line_start: int = Field(..., description="Starting line number")
    line_end: int = Field(..., description="Ending line number")
    snippet: str = Field(..., description="The actual code snippet")
    entity_name: Optional[str] = Field(None, description="Name of the code entity (class, function, etc.)")
    relevance_score: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="How relevant this citation is to the question",
    )


class RelatedEntity(BaseModel):
    """A related code entity for exploration."""

    name: str = Field(..., description="Entity name")
    type: str = Field(..., description="Entity type (class, function, module, etc.)")
    file_path: str = Field(..., description="File path where entity is defined")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    answer: str = Field(
        ...,
        description="Natural language answer with inline citations like [1], [2]",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="List of code citations referenced in the answer",
    )
    related_entities: list[RelatedEntity] = Field(
        default_factory=list,
        description="Related code entities for further exploration",
    )
    follow_up_suggestions: list[str] = Field(
        default_factory=list,
        description="Suggested follow-up questions",
    )
    conversation_id: str = Field(
        ...,
        description="Conversation ID for maintaining context",
    )


class ChatErrorResponse(BaseModel):
    """Error response for chat endpoint."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
