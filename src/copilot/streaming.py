"""
Streaming response handler for real-time Copilot responses.
Provides utilities for handling streaming responses and broadcasting to clients.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Optional

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StreamChunk:
    """A chunk of streaming response."""

    content: str
    chunk_type: str = "content"  # content, tool_use, reasoning, complete
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: datetime.utcnow().timestamp())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.chunk_type,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class StreamingSession:
    """A streaming session for a conversation."""

    session_id: str
    conversation_id: str
    is_active: bool = True
    total_chunks: int = 0
    total_content_length: int = 0
    subscribers: list[Callable[[StreamChunk], Any]] = field(default_factory=list)


class StreamingHandler:
    """
    Handles streaming responses from Copilot.
    Manages buffering, broadcasting, and session tracking.
    """

    def __init__(
        self,
        buffer_size: int = 10,
        chunk_delay_ms: int = 0,
    ) -> None:
        """
        Initialize the streaming handler.

        Args:
            buffer_size: Number of chunks to buffer
            chunk_delay_ms: Artificial delay between chunks (for rate limiting)
        """
        self.buffer_size = buffer_size
        self.chunk_delay_ms = chunk_delay_ms

        self._sessions: dict[str, StreamingSession] = {}
        self._buffers: dict[str, list[StreamChunk]] = {}

    def create_session(
        self,
        session_id: str,
        conversation_id: str,
    ) -> StreamingSession:
        """
        Create a new streaming session.

        Args:
            session_id: Session ID
            conversation_id: Conversation ID

        Returns:
            StreamingSession instance
        """
        session = StreamingSession(
            session_id=session_id,
            conversation_id=conversation_id,
        )
        self._sessions[session_id] = session
        self._buffers[session_id] = []

        logger.debug(
            "Created streaming session",
            session_id=session_id,
            conversation_id=conversation_id,
        )

        return session

    def subscribe(
        self,
        session_id: str,
        callback: Callable[[StreamChunk], Any],
    ) -> None:
        """
        Subscribe to streaming updates for a session.

        Args:
            session_id: Session ID
            callback: Callback function to receive chunks
        """
        if session_id in self._sessions:
            self._sessions[session_id].subscribers.append(callback)

    def unsubscribe(
        self,
        session_id: str,
        callback: Callable[[StreamChunk], Any],
    ) -> None:
        """Unsubscribe from streaming updates."""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            if callback in session.subscribers:
                session.subscribers.remove(callback)

    async def emit_chunk(
        self,
        session_id: str,
        chunk: StreamChunk,
    ) -> None:
        """
        Emit a chunk to all subscribers.

        Args:
            session_id: Session ID
            chunk: Chunk to emit
        """
        if session_id not in self._sessions:
            return

        session = self._sessions[session_id]
        session.total_chunks += 1
        session.total_content_length += len(chunk.content)

        # Buffer the chunk
        self._buffers[session_id].append(chunk)
        if len(self._buffers[session_id]) > self.buffer_size:
            self._buffers[session_id].pop(0)

        # Notify subscribers
        for callback in session.subscribers:
            try:
                result = callback(chunk)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    "Subscriber callback failed",
                    session_id=session_id,
                    error=str(e),
                )

        # Optional delay
        if self.chunk_delay_ms > 0:
            await asyncio.sleep(self.chunk_delay_ms / 1000)

    async def stream_response(
        self,
        session_id: str,
        response_iterator: AsyncIterator[str],
    ) -> str:
        """
        Stream a response and emit chunks to subscribers.

        Args:
            session_id: Session ID
            response_iterator: Async iterator yielding response chunks

        Returns:
            Complete response content
        """
        if session_id not in self._sessions:
            raise ValueError(f"Unknown session: {session_id}")

        full_content = ""

        async for content in response_iterator:
            full_content += content

            chunk = StreamChunk(
                content=content,
                chunk_type="content",
            )
            await self.emit_chunk(session_id, chunk)

        # Emit completion chunk
        completion_chunk = StreamChunk(
            content="",
            chunk_type="complete",
            metadata={"total_length": len(full_content)},
        )
        await self.emit_chunk(session_id, completion_chunk)

        return full_content

    async def emit_tool_use(
        self,
        session_id: str,
        tool_name: str,
        status: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Emit a tool usage notification.

        Args:
            session_id: Session ID
            tool_name: Name of the tool
            status: Status (e.g., "started", "completed", "failed")
            details: Optional details
        """
        chunk = StreamChunk(
            content=f"Using tool: {tool_name}",
            chunk_type="tool_use",
            metadata={
                "tool": tool_name,
                "status": status,
                **(details or {}),
            },
        )
        await self.emit_chunk(session_id, chunk)

    async def emit_reasoning(
        self,
        session_id: str,
        step: str,
        thought: str,
    ) -> None:
        """
        Emit a reasoning step notification.

        Args:
            session_id: Session ID
            step: Reasoning step name
            thought: The reasoning content
        """
        chunk = StreamChunk(
            content=thought,
            chunk_type="reasoning",
            metadata={"step": step},
        )
        await self.emit_chunk(session_id, chunk)

    def get_buffer(self, session_id: str) -> list[StreamChunk]:
        """Get the buffered chunks for a session."""
        return self._buffers.get(session_id, []).copy()

    def end_session(self, session_id: str) -> None:
        """
        End a streaming session.

        Args:
            session_id: Session ID
        """
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.is_active = False
            session.subscribers.clear()

            logger.debug(
                "Ended streaming session",
                session_id=session_id,
                total_chunks=session.total_chunks,
                total_content_length=session.total_content_length,
            )

            del self._sessions[session_id]
            del self._buffers[session_id]


class StreamingResponseBuilder:
    """
    Builder for constructing streaming responses.
    Useful for building responses incrementally.
    """

    def __init__(self) -> None:
        self._chunks: list[StreamChunk] = []
        self._content: str = ""
        self._metadata: dict[str, Any] = {}

    def add_content(self, content: str) -> "StreamingResponseBuilder":
        """Add content chunk."""
        self._content += content
        self._chunks.append(StreamChunk(content=content, chunk_type="content"))
        return self

    def add_tool_use(
        self,
        tool_name: str,
        result: Any,
    ) -> "StreamingResponseBuilder":
        """Add tool usage record."""
        self._chunks.append(
            StreamChunk(
                content=f"Tool: {tool_name}",
                chunk_type="tool_use",
                metadata={"tool": tool_name, "result": result},
            )
        )
        return self

    def add_reasoning(
        self,
        step: str,
        thought: str,
    ) -> "StreamingResponseBuilder":
        """Add reasoning step."""
        self._chunks.append(
            StreamChunk(
                content=thought,
                chunk_type="reasoning",
                metadata={"step": step},
            )
        )
        return self

    def set_metadata(self, key: str, value: Any) -> "StreamingResponseBuilder":
        """Set metadata."""
        self._metadata[key] = value
        return self

    def build(self) -> dict[str, Any]:
        """Build the final response."""
        return {
            "content": self._content,
            "chunks": [c.to_dict() for c in self._chunks],
            "metadata": self._metadata,
        }

    def get_chunks(self) -> list[StreamChunk]:
        """Get all chunks."""
        return self._chunks.copy()

    async def stream(self) -> AsyncIterator[StreamChunk]:
        """Stream the chunks asynchronously."""
        for chunk in self._chunks:
            yield chunk
