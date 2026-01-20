"""
Session domain model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.core.constants import MessageRole, SessionStatus


class ConversationMessage(BaseModel):
    """A message in a conversation."""

    role: MessageRole = Field(..., description="Role of the message sender")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class Session(BaseModel):
    """Chat session domain model."""

    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(default="anonymous", description="User identifier")
    codebase_path: str = Field(..., description="Path to the codebase being analyzed")
    status: SessionStatus = Field(default=SessionStatus.ACTIVE)

    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    metadata: dict[str, Any] = Field(default_factory=dict)

    copilot_conversation_id: Optional[str] = Field(
        default=None, description="Associated Copilot conversation ID"
    )
    active_workflow: Optional[str] = Field(
        default=None, description="Currently active workflow ID"
    )
    active_skills: list[str] = Field(
        default_factory=list, description="Currently active skills"
    )

    class Config:
        use_enum_values = True

    def add_message(self, message: ConversationMessage | str, content: str | None = None) -> None:
        """Add a message to conversation history.

        Can be called with either:
        - add_message(ConversationMessage(...))
        - add_message(role_str, content_str)
        """
        if isinstance(message, ConversationMessage):
            self.conversation_history.append(message.model_dump())
        else:
            # Legacy: role as first arg, content as second
            self.conversation_history.append({
                "role": message,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
            })
        self.updated_at = datetime.utcnow()

    def update_status(self, status: SessionStatus) -> None:
        """Update session status."""
        self.status = status
        self.updated_at = datetime.utcnow()

    def set_context(self, key: str, value: Any) -> None:
        """Set a context value."""
        self.context[key] = value
        self.updated_at = datetime.utcnow()

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get a context value."""
        return self.context.get(key, default)

    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        return self.status == SessionStatus.ACTIVE

    @property
    def message_count(self) -> int:
        """Get number of messages in conversation."""
        return len(self.conversation_history)
