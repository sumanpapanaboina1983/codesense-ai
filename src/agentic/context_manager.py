"""
Context window management for the Agentic Harness.
Implements sliding window with importance scoring.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import tiktoken

from src.core.config import settings
from src.core.constants import MessageRole
from src.core.logging import get_logger
from src.copilot.sdk_client import Message

logger = get_logger(__name__)


@dataclass
class ScoredMessage:
    """A message with an importance score."""

    message: Message
    score: float
    timestamp: float = field(default_factory=lambda: datetime.utcnow().timestamp())


class ImportanceScorer:
    """
    Scores message importance for context retention.
    """

    def __init__(self) -> None:
        # Keywords that indicate important content
        self.important_keywords = {
            "error", "exception", "failed", "critical", "important",
            "requirement", "must", "shall", "should", "class", "method",
            "function", "service", "component", "verified", "confirmed",
        }

        # Role importance weights
        self.role_weights = {
            MessageRole.SYSTEM: 1.0,  # System messages are always important
            MessageRole.USER: 0.8,  # User messages are important
            MessageRole.TOOL: 0.9,  # Tool results are very important
            MessageRole.ASSISTANT: 0.6,  # Assistant messages vary
        }

    def score(
        self,
        message: Message,
        current_task: Optional[str] = None,
    ) -> float:
        """
        Calculate importance score for a message.

        Args:
            message: The message to score
            current_task: Optional current task for relevance

        Returns:
            Score from 0.0 to 1.0
        """
        score = 0.0

        # Base score from role
        role_weight = self.role_weights.get(message.role, 0.5)
        score += role_weight * 0.3

        # Keyword overlap with current task
        if current_task:
            task_keywords = set(current_task.lower().split())
            msg_keywords = set(message.content.lower().split())
            overlap = len(task_keywords & msg_keywords)
            if task_keywords:
                score += (overlap / len(task_keywords)) * 0.3

        # Important keyword presence
        content_lower = message.content.lower()
        keyword_count = sum(1 for kw in self.important_keywords if kw in content_lower)
        score += min(keyword_count * 0.05, 0.2)

        # Code/technical content indicators
        if any(indicator in message.content for indicator in
               ['```', 'class ', 'def ', 'function ', '{', '}']):
            score += 0.1

        # Tool results are always important
        if message.role == MessageRole.TOOL:
            score += 0.2

        return min(score, 1.0)


class ContextManager:
    """
    Manages context window to prevent token overflow.
    Implements sliding window with importance scoring.
    """

    def __init__(
        self,
        max_tokens: Optional[int] = None,
        window_size: Optional[int] = None,
        importance_threshold: Optional[float] = None,
    ) -> None:
        """
        Initialize the context manager.

        Args:
            max_tokens: Maximum tokens in context
            window_size: Number of recent messages to always keep
            importance_threshold: Minimum importance for historical messages
        """
        self.max_tokens = max_tokens or settings.context.max_tokens
        self.window_size = window_size or settings.context.window_size
        self.importance_threshold = (
            importance_threshold or settings.context.importance_threshold
        )

        self.scorer = ImportanceScorer()

        # Try to get tokenizer (use cl100k_base for GPT-4)
        try:
            self._tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._tokenizer = None
            logger.warning("Tiktoken not available, using character estimation")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self._tokenizer:
            return len(self._tokenizer.encode(text))
        # Fallback: estimate ~4 characters per token
        return len(text) // 4

    def count_message_tokens(self, message: Message) -> int:
        """Count tokens in a message."""
        # Account for message structure overhead
        overhead = 4  # role, content markers
        return self.count_tokens(message.content) + overhead

    def optimize_context(
        self,
        messages: list[Message],
        current_task: Optional[str] = None,
        reserved_tokens: int = 1000,
    ) -> list[Message]:
        """
        Optimize context to fit within token limit.

        Keeps:
        1. System message (always)
        2. Recent messages (window_size)
        3. Important historical messages (by score)

        Args:
            messages: All conversation messages
            current_task: Current task for relevance scoring
            reserved_tokens: Tokens to reserve for response

        Returns:
            Optimized list of messages
        """
        if not messages:
            return []

        available_tokens = self.max_tokens - reserved_tokens

        # Always keep system message
        system_msg = None
        if messages and messages[0].role == MessageRole.SYSTEM:
            system_msg = messages[0]
            messages = messages[1:]

        # Split into recent and historical
        recent_messages = messages[-self.window_size:] if len(messages) > self.window_size else messages
        historical_messages = messages[:-self.window_size] if len(messages) > self.window_size else []

        # Start with system message
        selected = []
        token_count = 0

        if system_msg:
            tokens = self.count_message_tokens(system_msg)
            if tokens < available_tokens:
                selected.append(system_msg)
                token_count += tokens

        # Score historical messages
        scored_historical = []
        for msg in historical_messages:
            score = self.scorer.score(msg, current_task)
            if score >= self.importance_threshold:
                scored_historical.append(ScoredMessage(message=msg, score=score))

        # Sort by score (highest first)
        scored_historical.sort(key=lambda x: x.score, reverse=True)

        # Add historical messages by importance
        for scored_msg in scored_historical:
            msg_tokens = self.count_message_tokens(scored_msg.message)
            # Reserve space for recent messages
            recent_estimate = sum(
                self.count_message_tokens(m) for m in recent_messages
            )

            if token_count + msg_tokens + recent_estimate < available_tokens:
                selected.append(scored_msg.message)
                token_count += msg_tokens

        # Add recent messages (always keep if possible)
        for msg in recent_messages:
            msg_tokens = self.count_message_tokens(msg)
            if token_count + msg_tokens < available_tokens:
                selected.append(msg)
                token_count += msg_tokens
            else:
                logger.warning(
                    "Dropping recent message due to token limit",
                    tokens=msg_tokens,
                    current_total=token_count,
                )

        logger.debug(
            "Optimized context",
            original_count=len(messages) + (1 if system_msg else 0),
            optimized_count=len(selected),
            token_count=token_count,
            max_tokens=available_tokens,
        )

        return selected

    def summarize_context(
        self,
        messages: list[Message],
        max_summary_tokens: int = 500,
    ) -> str:
        """
        Create a summary of the conversation context.

        Args:
            messages: Messages to summarize
            max_summary_tokens: Maximum tokens for summary

        Returns:
            Summary string
        """
        if not messages:
            return ""

        summary_parts = []

        # Collect key information
        user_queries = []
        assistant_responses = []
        tool_results = []

        for msg in messages:
            if msg.role == MessageRole.USER:
                user_queries.append(msg.content[:200])
            elif msg.role == MessageRole.ASSISTANT:
                assistant_responses.append(msg.content[:200])
            elif msg.role == MessageRole.TOOL:
                tool_results.append(msg.content[:100])

        if user_queries:
            summary_parts.append(f"User asked about: {'; '.join(user_queries[:3])}")

        if tool_results:
            summary_parts.append(f"Tools returned: {'; '.join(tool_results[:3])}")

        if assistant_responses:
            summary_parts.append(f"Key findings: {assistant_responses[-1][:200]}")

        summary = "\n".join(summary_parts)

        # Truncate if needed
        if self.count_tokens(summary) > max_summary_tokens:
            # Simple truncation
            while self.count_tokens(summary) > max_summary_tokens and len(summary) > 100:
                summary = summary[:int(len(summary) * 0.9)]
            summary += "..."

        return summary

    def get_context_stats(self, messages: list[Message]) -> dict[str, Any]:
        """
        Get statistics about the current context.

        Args:
            messages: Current messages

        Returns:
            Dictionary with context statistics
        """
        total_tokens = sum(self.count_message_tokens(m) for m in messages)

        role_counts = {}
        for msg in messages:
            role = msg.role.value
            role_counts[role] = role_counts.get(role, 0) + 1

        return {
            "message_count": len(messages),
            "total_tokens": total_tokens,
            "max_tokens": self.max_tokens,
            "utilization": total_tokens / self.max_tokens if self.max_tokens else 0,
            "role_distribution": role_counts,
        }


class ConversationContext:
    """
    Manages context for a specific conversation.
    """

    def __init__(
        self,
        conversation_id: str,
        context_manager: Optional[ContextManager] = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.manager = context_manager or ContextManager()
        self.messages: list[Message] = []
        self.current_task: Optional[str] = None
        self.metadata: dict[str, Any] = {}

    def add_message(self, message: Message) -> None:
        """Add a message to the context."""
        self.messages.append(message)

    def set_task(self, task: str) -> None:
        """Set the current task for relevance scoring."""
        self.current_task = task

    def get_optimized_messages(self) -> list[Message]:
        """Get optimized message list for the conversation."""
        return self.manager.optimize_context(
            self.messages,
            current_task=self.current_task,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get context statistics."""
        return self.manager.get_context_stats(self.messages)

    def clear(self) -> None:
        """Clear the context."""
        self.messages.clear()
        self.current_task = None
