"""
OpenAI-compatible API endpoints for integration with Open WebUI and other clients.
Implements the OpenAI Chat Completions API format.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.deps import get_copilot_client
from src.copilot.sdk_client import CopilotSDKClient
from src.core.logging import get_logger
from src.core.config import settings

logger = get_logger(__name__)

router = APIRouter()


# OpenAI-compatible request/response models
class ChatMessage(BaseModel):
    """OpenAI chat message format."""
    role: str = Field(..., description="Role: system, user, or assistant")
    content: str = Field(..., description="Message content")
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """OpenAI chat completion request format."""
    model: str = Field(default="codesense-ai", description="Model to use")
    messages: list[ChatMessage] = Field(..., description="Conversation messages")
    temperature: Optional[float] = Field(default=0.7, ge=0, le=2)
    top_p: Optional[float] = Field(default=1.0, ge=0, le=1)
    n: Optional[int] = Field(default=1, ge=1, le=10)
    stream: Optional[bool] = Field(default=False)
    stop: Optional[list[str] | str] = None
    max_tokens: Optional[int] = Field(default=4096, ge=1)
    presence_penalty: Optional[float] = Field(default=0, ge=-2, le=2)
    frequency_penalty: Optional[float] = Field(default=0, ge=-2, le=2)
    user: Optional[str] = None


class ChatCompletionChoice(BaseModel):
    """OpenAI chat completion choice."""
    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    """OpenAI token usage."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """OpenAI chat completion response format."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage


class ModelInfo(BaseModel):
    """OpenAI model info."""
    id: str
    object: str = "model"
    created: int
    owned_by: str = "codesense"


class ModelListResponse(BaseModel):
    """OpenAI model list response."""
    object: str = "list"
    data: list[ModelInfo]


@router.get("/models", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    """
    List available models (OpenAI-compatible endpoint).
    """
    return ModelListResponse(
        data=[
            ModelInfo(
                id="codesense-ai",
                created=int(time.time()),
                owned_by="codesense",
            ),
            ModelInfo(
                id="codesense-ai-fast",
                created=int(time.time()),
                owned_by="codesense",
            ),
        ]
    )


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    copilot_client: CopilotSDKClient = Depends(get_copilot_client),
) -> ChatCompletionResponse:
    """
    OpenAI-compatible chat completions endpoint.

    This endpoint allows Open WebUI and other OpenAI-compatible clients
    to interact with the CodeSense AI backend using the GitHub Copilot SDK.
    """
    request_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    logger.info(
        "OpenAI-compatible chat request",
        request_id=request_id,
        model=request.model,
        message_count=len(request.messages),
        stream=request.stream,
    )

    try:
        # Extract the last user message
        user_messages = [m for m in request.messages if m.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="No user message provided")

        last_message = user_messages[-1].content

        # Build system prompt from messages
        system_messages = [m for m in request.messages if m.role == "system"]
        system_prompt = (
            system_messages[0].content if system_messages
            else "You are CodeSense AI, an assistant that helps analyze legacy codebases and generate documentation."
        )

        # Create a conversation with the Copilot SDK
        conv_id = await copilot_client.create_conversation(
            system_prompt=system_prompt,
            skills=[],
            metadata={"request_id": request_id},
        )

        # Add context from previous messages (except system and last user message)
        for msg in request.messages:
            if msg.role == "assistant":
                copilot_client._conversations[conv_id].messages.append(
                    copilot_client._conversations[conv_id].messages[0].__class__(
                        role=copilot_client._conversations[conv_id].messages[0].role.__class__("assistant"),
                        content=msg.content,
                    )
                )
            elif msg.role == "user" and msg.content != last_message:
                copilot_client._conversations[conv_id].messages.append(
                    copilot_client._conversations[conv_id].messages[0].__class__(
                        role=copilot_client._conversations[conv_id].messages[0].role.__class__("user"),
                        content=msg.content,
                    )
                )

        # Send message through the SDK
        response = await copilot_client.send_message(
            message=last_message,
            conversation_id=conv_id,
            temperature=request.temperature,
        )

        response_content = response.content

        # Clean up conversation
        copilot_client.delete_conversation(conv_id)

        # Calculate approximate token counts
        prompt_tokens = sum(len(m.content.split()) * 4 // 3 for m in request.messages)
        completion_tokens = len(response_content.split()) * 4 // 3

        return ChatCompletionResponse(
            id=request_id,
            created=int(time.time()),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(
                        role="assistant",
                        content=response_content,
                    ),
                    finish_reason="stop",
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in OpenAI-compatible chat", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
