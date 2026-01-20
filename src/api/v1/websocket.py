"""
WebSocket handler for real-time streaming responses.
"""

import asyncio
import json
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.core.logging import get_logger

logger = get_logger(__name__)


class WSMessageType(str, Enum):
    """WebSocket message types."""

    # Client messages
    CHAT = "chat"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PING = "ping"

    # Server messages
    TOKEN = "token"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    REASONING = "reasoning"
    VERIFICATION = "verification"
    DOCUMENT = "document"
    STATUS = "status"
    ERROR = "error"
    PONG = "pong"
    COMPLETE = "complete"


class WSMessage(BaseModel):
    """WebSocket message format."""

    type: WSMessageType
    session_id: Optional[str] = None
    data: dict[str, Any] = {}
    timestamp: datetime = None

    def __init__(self, **data):
        if "timestamp" not in data or data["timestamp"] is None:
            data["timestamp"] = datetime.utcnow()
        super().__init__(**data)


class ConnectionManager:
    """
    Manages WebSocket connections.
    """

    def __init__(self) -> None:
        # Active connections by session_id
        self._connections: dict[str, list[WebSocket]] = {}
        # Connection metadata
        self._metadata: dict[WebSocket, dict[str, Any]] = {}
        # Subscriptions (session_id -> set of topics)
        self._subscriptions: dict[str, set[str]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
        metadata: Optional[dict[str, Any]] = None
    ) -> None:
        """Accept and register a new connection."""
        await websocket.accept()

        if session_id not in self._connections:
            self._connections[session_id] = []

        self._connections[session_id].append(websocket)
        self._metadata[websocket] = {
            "session_id": session_id,
            "connected_at": datetime.utcnow(),
            **(metadata or {}),
        }
        self._subscriptions[session_id] = set()

        logger.info(
            "WebSocket connected",
            session_id=session_id,
            total_connections=len(self._connections[session_id]),
        )

    async def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """Remove a connection."""
        if session_id in self._connections:
            if websocket in self._connections[session_id]:
                self._connections[session_id].remove(websocket)

            if not self._connections[session_id]:
                del self._connections[session_id]
                if session_id in self._subscriptions:
                    del self._subscriptions[session_id]

        if websocket in self._metadata:
            del self._metadata[websocket]

        logger.info("WebSocket disconnected", session_id=session_id)

    async def send_message(
        self,
        session_id: str,
        message: WSMessage
    ) -> None:
        """Send a message to all connections in a session."""
        if session_id not in self._connections:
            return

        message_json = message.model_dump_json()

        for websocket in self._connections[session_id]:
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.warning(
                    "Failed to send WebSocket message",
                    session_id=session_id,
                    error=str(e),
                )

    async def broadcast(
        self,
        message: WSMessage,
        topic: Optional[str] = None
    ) -> None:
        """Broadcast a message to all connections or to subscribers of a topic."""
        message_json = message.model_dump_json()

        for session_id, connections in self._connections.items():
            # If topic is specified, only send to subscribers
            if topic and topic not in self._subscriptions.get(session_id, set()):
                continue

            for websocket in connections:
                try:
                    await websocket.send_text(message_json)
                except Exception as e:
                    logger.warning("Failed to broadcast", error=str(e))

    def subscribe(self, session_id: str, topic: str) -> None:
        """Subscribe a session to a topic."""
        if session_id not in self._subscriptions:
            self._subscriptions[session_id] = set()
        self._subscriptions[session_id].add(topic)

    def unsubscribe(self, session_id: str, topic: str) -> None:
        """Unsubscribe a session from a topic."""
        if session_id in self._subscriptions:
            self._subscriptions[session_id].discard(topic)

    def get_connection_count(self, session_id: Optional[str] = None) -> int:
        """Get the number of active connections."""
        if session_id:
            return len(self._connections.get(session_id, []))
        return sum(len(conns) for conns in self._connections.values())

    def is_connected(self, session_id: str) -> bool:
        """Check if a session has active connections."""
        return session_id in self._connections and len(self._connections[session_id]) > 0


# Global connection manager instance
connection_manager = ConnectionManager()


class StreamingHandler:
    """
    Handler for streaming responses to WebSocket clients.
    """

    def __init__(
        self,
        session_id: str,
        manager: ConnectionManager = connection_manager,
    ) -> None:
        self.session_id = session_id
        self.manager = manager
        self._message_count = 0

    async def stream_token(self, token: str) -> None:
        """Stream a single token."""
        await self.manager.send_message(
            self.session_id,
            WSMessage(
                type=WSMessageType.TOKEN,
                session_id=self.session_id,
                data={"token": token, "index": self._message_count},
            ),
        )
        self._message_count += 1

    async def stream_tokens(self, content: str, chunk_size: int = 10) -> None:
        """Stream content as tokens."""
        for i in range(0, len(content), chunk_size):
            chunk = content[i : i + chunk_size]
            await self.stream_token(chunk)
            await asyncio.sleep(0.01)  # Small delay for natural streaming

    async def send_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any]
    ) -> None:
        """Send a tool call notification."""
        await self.manager.send_message(
            self.session_id,
            WSMessage(
                type=WSMessageType.TOOL_CALL,
                session_id=self.session_id,
                data={
                    "tool": tool_name,
                    "arguments": arguments,
                },
            ),
        )

    async def send_tool_result(
        self,
        tool_name: str,
        result: Any
    ) -> None:
        """Send a tool result."""
        await self.manager.send_message(
            self.session_id,
            WSMessage(
                type=WSMessageType.TOOL_RESULT,
                session_id=self.session_id,
                data={
                    "tool": tool_name,
                    "result": result,
                },
            ),
        )

    async def send_reasoning_step(
        self,
        step: str,
        output: str,
        confidence: float
    ) -> None:
        """Send a reasoning step update."""
        await self.manager.send_message(
            self.session_id,
            WSMessage(
                type=WSMessageType.REASONING,
                session_id=self.session_id,
                data={
                    "step": step,
                    "output": output,
                    "confidence": confidence,
                },
            ),
        )

    async def send_verification_update(
        self,
        status: str,
        facts_verified: int,
        issues_found: int
    ) -> None:
        """Send a verification status update."""
        await self.manager.send_message(
            self.session_id,
            WSMessage(
                type=WSMessageType.VERIFICATION,
                session_id=self.session_id,
                data={
                    "status": status,
                    "facts_verified": facts_verified,
                    "issues_found": issues_found,
                },
            ),
        )

    async def send_document(
        self,
        document_id: str,
        document_type: str,
        title: str,
        preview: str
    ) -> None:
        """Send a document notification."""
        await self.manager.send_message(
            self.session_id,
            WSMessage(
                type=WSMessageType.DOCUMENT,
                session_id=self.session_id,
                data={
                    "document_id": document_id,
                    "type": document_type,
                    "title": title,
                    "preview": preview[:500],
                },
            ),
        )

    async def send_status(self, status: str, message: str) -> None:
        """Send a status update."""
        await self.manager.send_message(
            self.session_id,
            WSMessage(
                type=WSMessageType.STATUS,
                session_id=self.session_id,
                data={
                    "status": status,
                    "message": message,
                },
            ),
        )

    async def send_error(self, error: str, code: Optional[str] = None) -> None:
        """Send an error message."""
        await self.manager.send_message(
            self.session_id,
            WSMessage(
                type=WSMessageType.ERROR,
                session_id=self.session_id,
                data={
                    "error": error,
                    "code": code,
                },
            ),
        )

    async def send_complete(self, summary: Optional[str] = None) -> None:
        """Send completion message."""
        await self.manager.send_message(
            self.session_id,
            WSMessage(
                type=WSMessageType.COMPLETE,
                session_id=self.session_id,
                data={
                    "total_tokens": self._message_count,
                    "summary": summary,
                },
            ),
        )


async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    message_handler: Callable[[str, dict[str, Any]], Any]
) -> None:
    """
    WebSocket endpoint handler.

    Args:
        websocket: WebSocket connection
        session_id: Session ID
        message_handler: Callback function to handle incoming messages
    """
    await connection_manager.connect(websocket, session_id)

    try:
        while True:
            # Receive message
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                msg_type = message.get("type", "")

                if msg_type == WSMessageType.PING:
                    # Respond to ping
                    await connection_manager.send_message(
                        session_id,
                        WSMessage(
                            type=WSMessageType.PONG,
                            session_id=session_id,
                        ),
                    )

                elif msg_type == WSMessageType.SUBSCRIBE:
                    # Subscribe to topic
                    topic = message.get("data", {}).get("topic")
                    if topic:
                        connection_manager.subscribe(session_id, topic)
                        await connection_manager.send_message(
                            session_id,
                            WSMessage(
                                type=WSMessageType.STATUS,
                                session_id=session_id,
                                data={"status": "subscribed", "topic": topic},
                            ),
                        )

                elif msg_type == WSMessageType.UNSUBSCRIBE:
                    # Unsubscribe from topic
                    topic = message.get("data", {}).get("topic")
                    if topic:
                        connection_manager.unsubscribe(session_id, topic)

                elif msg_type == WSMessageType.CHAT:
                    # Handle chat message
                    await message_handler(session_id, message.get("data", {}))

                else:
                    logger.warning("Unknown message type", type=msg_type)

            except json.JSONDecodeError:
                await connection_manager.send_message(
                    session_id,
                    WSMessage(
                        type=WSMessageType.ERROR,
                        session_id=session_id,
                        data={"error": "Invalid JSON"},
                    ),
                )

    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket, session_id)
    except Exception as e:
        logger.exception("WebSocket error", error=str(e))
        await connection_manager.disconnect(websocket, session_id)
