"""
Session manager for handling user sessions and conversations.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from src.agentic.context_manager import ContextManager
from src.copilot.conversation_handler import ConversationHandler
from src.copilot.sdk_client import CopilotResponse, CopilotSDKClient

# Alias for backwards compatibility
ConversationResponse = CopilotResponse
from src.core.constants import MessageRole, SessionStatus
from src.core.exceptions import SessionNotFoundError
from src.core.logging import get_logger
from src.domain.session import ConversationMessage, Session
from src.mcp.tool_registry import MCPToolRegistry
from src.repositories.session_repo import InMemorySessionRepository

logger = get_logger(__name__)


class SessionManager:
    """
    Manages user sessions and conversation state.
    """

    def __init__(
        self,
        copilot_client: CopilotSDKClient,
        tool_registry: MCPToolRegistry,
        session_repository: Optional[InMemorySessionRepository] = None,
        max_context_tokens: int = 100000,
    ) -> None:
        """
        Initialize the session manager.

        Args:
            copilot_client: Copilot SDK client
            tool_registry: MCP tool registry
            session_repository: Session repository
            max_context_tokens: Maximum tokens for context window
        """
        self.copilot_client = copilot_client
        self.tool_registry = tool_registry
        self.session_repository = session_repository or InMemorySessionRepository()
        self.max_context_tokens = max_context_tokens

        # Conversation handlers by session
        self._handlers: dict[str, ConversationHandler] = {}
        # Context managers by session
        self._context_managers: dict[str, ContextManager] = {}

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        return f"sess_{uuid.uuid4().hex[:16]}"

    async def create_session(
        self,
        user_id: Optional[str] = None,
        codebase_path: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Session:
        """
        Create a new session.

        Args:
            user_id: Optional user ID
            codebase_path: Path to codebase being analyzed
            metadata: Additional session metadata

        Returns:
            Created session
        """
        session_id = self._generate_session_id()

        session = Session(
            id=session_id,
            user_id=user_id,
            status=SessionStatus.ACTIVE,
            context={
                "codebase_path": codebase_path,
            },
            metadata=metadata or {},
        )

        await self.session_repository.save(session)

        # Initialize handlers for this session
        self._handlers[session_id] = ConversationHandler(
            self.copilot_client,
            self.tool_registry,
        )
        self._context_managers[session_id] = ContextManager(
            max_tokens=self.max_context_tokens
        )

        logger.info(
            "Session created",
            session_id=session_id,
            user_id=user_id,
            codebase_path=codebase_path,
        )

        return session

    async def get_session(self, session_id: str) -> Session:
        """
        Get a session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session

        Raises:
            SessionNotFoundError: If session not found
        """
        session = await self.session_repository.get(session_id)
        if not session:
            raise SessionNotFoundError(
                session_id=session_id,
                message=f"Session not found: {session_id}",
            )
        return session

    async def send_message(
        self,
        session_id: str,
        message: str,
        skill_name: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> ConversationResponse:
        """
        Send a message in a session.

        Args:
            session_id: Session ID
            message: User message
            skill_name: Optional skill to use
            context: Additional context

        Returns:
            Conversation response
        """
        session = await self.get_session(session_id)

        if session.status != SessionStatus.ACTIVE:
            raise ValueError(f"Session is not active: {session.status}")

        # Get or create handler
        if session_id not in self._handlers:
            self._handlers[session_id] = ConversationHandler(
                self.copilot_client,
                self.tool_registry,
            )

        handler = self._handlers[session_id]

        # Add message to session history
        user_message = ConversationMessage(
            role=MessageRole.USER,
            content=message,
        )
        session.add_message(user_message)

        # Get context from context manager
        if session_id in self._context_managers:
            context_manager = self._context_managers[session_id]
            managed_context = context_manager.get_context()
            if context:
                managed_context.update(context)
            context = managed_context

        # Send message through handler
        response = await handler.send_message(
            session_id=session_id,
            message=message,
            skill_name=skill_name,
            context=context,
        )

        # Add assistant response to session history
        assistant_message = ConversationMessage(
            role=MessageRole.ASSISTANT,
            content=response.content,
            metadata={
                "skill_used": skill_name,
                "tool_calls": [t.dict() for t in response.tool_calls],
                "stop_reason": response.stop_reason,
            },
        )
        session.add_message(assistant_message)

        # Update context manager with new information
        if session_id in self._context_managers:
            self._context_managers[session_id].add_context(
                "last_message",
                message[:500],
                importance=0.7,
            )
            self._context_managers[session_id].add_context(
                "last_response",
                response.content[:500],
                importance=0.6,
            )

        # Save session
        await self.session_repository.save(session)

        logger.info(
            "Message processed",
            session_id=session_id,
            message_length=len(message),
            response_length=len(response.content),
        )

        return response

    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[ConversationMessage]:
        """
        Get conversation history for a session.

        Args:
            session_id: Session ID
            limit: Maximum messages to return

        Returns:
            List of conversation messages
        """
        session = await self.get_session(session_id)
        return session.get_recent_messages(limit)

    async def clear_conversation(self, session_id: str) -> None:
        """
        Clear conversation history for a session.

        Args:
            session_id: Session ID
        """
        session = await self.get_session(session_id)
        session.conversation_history = []
        await self.session_repository.save(session)

        # Reset context manager
        if session_id in self._context_managers:
            self._context_managers[session_id] = ContextManager(
                max_tokens=self.max_context_tokens
            )

        logger.info("Conversation cleared", session_id=session_id)

    async def end_session(self, session_id: str) -> None:
        """
        End a session.

        Args:
            session_id: Session ID
        """
        session = await self.get_session(session_id)
        session.status = SessionStatus.COMPLETED
        session.updated_at = datetime.utcnow()
        await self.session_repository.save(session)

        # Clean up handlers
        if session_id in self._handlers:
            del self._handlers[session_id]
        if session_id in self._context_managers:
            del self._context_managers[session_id]

        logger.info("Session ended", session_id=session_id)

    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        status: Optional[SessionStatus] = None,
        limit: int = 100,
    ) -> list[Session]:
        """
        List sessions with optional filters.

        Args:
            user_id: Filter by user ID
            status: Filter by status
            limit: Maximum sessions to return

        Returns:
            List of sessions
        """
        filters: dict[str, Any] = {}
        if user_id:
            filters["user_id"] = user_id
        if status:
            filters["status"] = status

        return await self.session_repository.list(filters=filters, limit=limit)

    async def update_session_context(
        self,
        session_id: str,
        key: str,
        value: Any,
        importance: float = 0.5,
    ) -> None:
        """
        Update session context.

        Args:
            session_id: Session ID
            key: Context key
            value: Context value
            importance: Importance score (0-1)
        """
        session = await self.get_session(session_id)
        session.context[key] = value
        await self.session_repository.save(session)

        # Update context manager
        if session_id in self._context_managers:
            self._context_managers[session_id].add_context(key, value, importance)

    async def get_session_context(self, session_id: str) -> dict[str, Any]:
        """
        Get the current context for a session.

        Args:
            session_id: Session ID

        Returns:
            Session context
        """
        session = await self.get_session(session_id)

        if session_id in self._context_managers:
            return self._context_managers[session_id].get_context()

        return session.context

    async def cleanup_inactive_sessions(
        self,
        inactive_hours: int = 24
    ) -> int:
        """
        Clean up inactive sessions.

        Args:
            inactive_hours: Hours of inactivity before cleanup

        Returns:
            Number of sessions cleaned up
        """
        count = await self.session_repository.cleanup_expired(inactive_hours)

        # Clean up handlers for expired sessions
        active_session_ids = set(
            s.id for s in await self.session_repository.list()
        )

        handlers_to_remove = [
            sid for sid in self._handlers.keys()
            if sid not in active_session_ids
        ]

        for sid in handlers_to_remove:
            del self._handlers[sid]
            if sid in self._context_managers:
                del self._context_managers[sid]

        logger.info("Cleaned up inactive sessions", count=count)
        return count
