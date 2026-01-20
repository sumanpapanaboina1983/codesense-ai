"""
Chat endpoints for conversational AI interactions.
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel, Field

from src.api.deps import get_session_manager
from src.api.v1.websocket import StreamingHandler, connection_manager, websocket_endpoint
from src.core.exceptions import SessionNotFoundError
from src.core.logging import get_logger
from src.core.security import generate_request_id
from src.services.session_manager import SessionManager

logger = get_logger(__name__)

router = APIRouter()


# Request/Response models
class ChatContext(BaseModel):
    """Context for chat requests."""

    codebase_path: Optional[str] = Field(
        default=None, description="Path to the codebase"
    )
    preferences: Optional[dict[str, Any]] = Field(
        default=None, description="User preferences"
    )


class ChatMessageRequest(BaseModel):
    """Request model for chat messages."""

    session_id: Optional[str] = Field(
        default=None, description="Session ID (creates new if not provided)"
    )
    message: str = Field(..., description="User message", min_length=1)
    skill_name: Optional[str] = Field(
        default=None, description="Specific skill to use"
    )
    context: Optional[ChatContext] = Field(default=None)


class Artifact(BaseModel):
    """Generated artifact (document)."""

    type: str
    document_id: str
    download_url: str


class ChatResponseData(BaseModel):
    """Response data from chat."""

    type: str = Field(default="text", description="Response type")
    content: str = Field(..., description="Response content")
    artifacts: list[Artifact] = Field(default_factory=list)


class ChatMetadata(BaseModel):
    """Metadata for chat response."""

    tokens_used: int = Field(default=0)
    reasoning_traces: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    """Response model for chat messages."""

    session_id: str
    message_id: str
    response: ChatResponseData
    metadata: ChatMetadata
    timestamp: str


@router.post("/chat/message", response_model=ChatMessageResponse)
async def send_message(
    request: ChatMessageRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> ChatMessageResponse:
    """
    Send a message to the AI accelerator.

    This endpoint handles:
    - Creating new sessions
    - Processing user messages
    - Generating responses with optional document artifacts
    """
    request_id = generate_request_id()

    logger.info(
        "Processing chat message",
        request_id=request_id,
        session_id=request.session_id,
        message_length=len(request.message),
    )

    try:
        # Create or get session
        if request.session_id:
            try:
                session = await session_manager.get_session(request.session_id)
                session_id = session.id
            except SessionNotFoundError:
                # Create new session if not found
                session = await session_manager.create_session(
                    codebase_path=request.context.codebase_path if request.context else None,
                    metadata={"request_id": request_id},
                )
                session_id = session.id
        else:
            session = await session_manager.create_session(
                codebase_path=request.context.codebase_path if request.context else None,
                metadata={"request_id": request_id},
            )
            session_id = session.id

        # Build context
        context: dict[str, Any] = {}
        if request.context:
            if request.context.codebase_path:
                context["codebase_path"] = request.context.codebase_path
            if request.context.preferences:
                context["preferences"] = request.context.preferences

        # Send message through session manager
        response = await session_manager.send_message(
            session_id=session_id,
            message=request.message,
            skill_name=request.skill_name,
            context=context,
        )

        # Build artifacts from tool calls if any documents were generated
        artifacts: list[Artifact] = []
        for tool_call in response.tool_calls:
            if tool_call.name in ["generate_brd", "generate_epic", "generate_backlog"]:
                if tool_call.result and isinstance(tool_call.result, dict):
                    doc_id = tool_call.result.get("document_id")
                    if doc_id:
                        artifacts.append(Artifact(
                            type=tool_call.name.replace("generate_", ""),
                            document_id=doc_id,
                            download_url=f"/api/v1/documents/{doc_id}/download",
                        ))

        return ChatMessageResponse(
            session_id=session_id,
            message_id=request_id,
            response=ChatResponseData(
                type="text",
                content=response.content,
                artifacts=artifacts,
            ),
            metadata=ChatMetadata(
                tokens_used=response.usage.get("total_tokens", 0) if response.usage else 0,
                reasoning_traces=[],
                confidence=0.9,  # Would come from verification in production
                tool_calls=[t.dict() for t in response.tool_calls],
            ),
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.exception("Error processing chat message", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""

    user_id: Optional[str] = None
    codebase_path: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class SessionResponse(BaseModel):
    """Response with session info."""

    session_id: str
    status: str
    created_at: str


@router.post("/chat/session", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    """
    Create a new chat session.
    """
    session = await session_manager.create_session(
        user_id=request.user_id,
        codebase_path=request.codebase_path,
        metadata=request.metadata,
    )

    return SessionResponse(
        session_id=session.id,
        status=session.status.value,
        created_at=session.created_at.isoformat(),
    )


class StreamRequest(BaseModel):
    """Request for streaming chat."""

    session_id: str
    message: str


@router.post("/chat/stream")
async def stream_message(request: StreamRequest) -> dict[str, str]:
    """
    Initiate a streaming chat response.

    Returns WebSocket connection details for streaming.
    Actual streaming is handled via WebSocket endpoint.
    """
    return {
        "websocket_url": f"/api/v1/ws/chat/{request.session_id}",
        "session_id": request.session_id,
    }


class ConversationHistoryResponse(BaseModel):
    """Response with conversation history."""

    session_id: str
    messages: list[dict[str, Any]]
    total_messages: int


@router.get("/chat/history/{session_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    session_id: str,
    limit: int = 50,
    session_manager: SessionManager = Depends(get_session_manager),
) -> ConversationHistoryResponse:
    """
    Get conversation history for a session.
    """
    logger.info("Retrieving conversation history", session_id=session_id)

    try:
        messages = await session_manager.get_conversation_history(session_id, limit)

        return ConversationHistoryResponse(
            session_id=session_id,
            messages=[m.dict() for m in messages],
            total_messages=len(messages),
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


@router.delete("/chat/session/{session_id}")
async def end_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    """
    End a chat session and clean up resources.
    """
    logger.info("Ending session", session_id=session_id)

    try:
        await session_manager.end_session(session_id)
        return {"status": "ended", "session_id": session_id}
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


@router.delete("/chat/session/{session_id}/history")
async def clear_conversation(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    """
    Clear conversation history for a session.
    """
    logger.info("Clearing conversation", session_id=session_id)

    try:
        await session_manager.clear_conversation(session_id)
        return {"status": "cleared", "session_id": session_id}
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


# WebSocket endpoint for streaming
@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(
    websocket: WebSocket,
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
) -> None:
    """
    WebSocket endpoint for streaming chat responses.
    """

    async def handle_message(sid: str, data: dict[str, Any]) -> None:
        """Handle incoming chat messages over WebSocket."""
        message = data.get("message", "")
        skill_name = data.get("skill_name")
        context = data.get("context", {})

        streaming_handler = StreamingHandler(sid)

        try:
            await streaming_handler.send_status("processing", "Processing your message...")

            # Send message through session manager
            response = await session_manager.send_message(
                session_id=sid,
                message=message,
                skill_name=skill_name,
                context=context,
            )

            # Stream the response content
            await streaming_handler.stream_tokens(response.content)

            # Send tool call results if any
            for tool_call in response.tool_calls:
                await streaming_handler.send_tool_result(tool_call.name, tool_call.result)

            await streaming_handler.send_complete()

        except Exception as e:
            logger.exception("WebSocket message error", error=str(e))
            await streaming_handler.send_error(str(e))

    await websocket_endpoint(websocket, session_id, handle_message)
