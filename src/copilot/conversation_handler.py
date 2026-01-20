"""
Multi-turn conversation management for Copilot interactions.
Handles conversation lifecycle, context management, and tool calling loops.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from src.copilot.sdk_client import CopilotResponse, CopilotSDKClient, ToolCall
from src.core.logging import get_logger
from src.mcp.tool_registry import MCPToolRegistry

logger = get_logger(__name__)


@dataclass
class ConversationState:
    """State of a conversation."""

    conversation_id: str
    session_id: str
    active_skills: list[str] = field(default_factory=list)
    pending_tool_calls: list[ToolCall] = field(default_factory=list)
    total_turns: int = 0
    total_tokens: int = 0
    is_active: bool = True


class ConversationHandler:
    """
    Handles multi-turn conversations with tool calling support.
    Manages the interaction loop between user, Copilot, and MCP tools.
    """

    def __init__(
        self,
        copilot_client: CopilotSDKClient,
        tool_registry: MCPToolRegistry,
        max_tool_iterations: int = 10,
    ) -> None:
        """
        Initialize the conversation handler.

        Args:
            copilot_client: Copilot SDK client
            tool_registry: MCP tool registry
            max_tool_iterations: Max iterations for tool calling loop
        """
        self.copilot_client = copilot_client
        self.tool_registry = tool_registry
        self.max_tool_iterations = max_tool_iterations

        self._conversations: dict[str, ConversationState] = {}

    async def create_conversation(
        self,
        session_id: str,
        system_prompt: str,
        skills: Optional[list[str]] = None,
    ) -> str:
        """
        Create a new conversation.

        Args:
            session_id: Session ID for tracking
            system_prompt: System prompt
            skills: Skills to activate

        Returns:
            Conversation ID
        """
        conversation_id = await self.copilot_client.create_conversation(
            system_prompt=system_prompt,
            skills=skills,
        )

        self._conversations[conversation_id] = ConversationState(
            conversation_id=conversation_id,
            session_id=session_id,
            active_skills=skills or [],
        )

        logger.info(
            "Created managed conversation",
            conversation_id=conversation_id,
            session_id=session_id,
        )

        return conversation_id

    async def send_message(
        self,
        conversation_id: str,
        message: str,
        include_tools: bool = True,
    ) -> CopilotResponse:
        """
        Send a message and handle the full tool calling loop.

        Args:
            conversation_id: Conversation ID
            message: User message
            include_tools: Whether to include MCP tools

        Returns:
            Final Copilot response after all tool calls are resolved
        """
        if conversation_id not in self._conversations:
            raise ValueError(f"Unknown conversation: {conversation_id}")

        state = self._conversations[conversation_id]
        state.total_turns += 1

        # Get tools if needed
        tools = None
        if include_tools:
            tools = self.tool_registry.get_tool_definitions()

        # Send initial message
        response = await self.copilot_client.send_message(
            message=message,
            conversation_id=conversation_id,
            tools=tools,
        )

        state.total_tokens += response.tokens_used

        # Handle tool calling loop
        iterations = 0
        while response.tool_calls and iterations < self.max_tool_iterations:
            iterations += 1

            logger.debug(
                "Processing tool calls",
                conversation_id=conversation_id,
                iteration=iterations,
                tool_count=len(response.tool_calls),
            )

            # Execute all tool calls
            for tool_call in response.tool_calls:
                result = await self.tool_registry.execute(
                    tool_call.function_name,
                    tool_call.arguments,
                )

                await self.copilot_client.add_tool_result(
                    conversation_id=conversation_id,
                    tool_call_id=tool_call.id,
                    result=result,
                )

            # Continue conversation with tool results
            response = await self.copilot_client.send_message(
                message="",  # Empty message to continue with tool results
                conversation_id=conversation_id,
                tools=tools,
            )

            state.total_tokens += response.tokens_used

        if iterations >= self.max_tool_iterations:
            logger.warning(
                "Max tool iterations reached",
                conversation_id=conversation_id,
                iterations=iterations,
            )

        return response

    async def inject_skills(
        self,
        conversation_id: str,
        skills: list[str],
    ) -> None:
        """
        Inject additional skills into a conversation.

        Args:
            conversation_id: Conversation ID
            skills: Skills to inject
        """
        await self.copilot_client.inject_skills(conversation_id, skills)

        if conversation_id in self._conversations:
            state = self._conversations[conversation_id]
            state.active_skills.extend(skills)

    def get_conversation_state(
        self,
        conversation_id: str,
    ) -> Optional[ConversationState]:
        """Get the state of a conversation."""
        return self._conversations.get(conversation_id)

    def end_conversation(self, conversation_id: str) -> None:
        """
        End a conversation and clean up resources.

        Args:
            conversation_id: Conversation ID
        """
        if conversation_id in self._conversations:
            state = self._conversations[conversation_id]
            state.is_active = False

            logger.info(
                "Ended conversation",
                conversation_id=conversation_id,
                total_turns=state.total_turns,
                total_tokens=state.total_tokens,
            )

        self.copilot_client.delete_conversation(conversation_id)
        self._conversations.pop(conversation_id, None)

    async def execute_with_reasoning(
        self,
        conversation_id: str,
        task: str,
        reasoning_prompt: str,
    ) -> dict[str, Any]:
        """
        Execute a task with explicit reasoning steps.

        This method instructs Copilot to think through the task
        step by step before providing a final answer.

        Args:
            conversation_id: Conversation ID
            task: The task to perform
            reasoning_prompt: Template for reasoning

        Returns:
            Dictionary with reasoning trace and final answer
        """
        # Format the reasoning prompt
        full_prompt = reasoning_prompt.format(task=task)

        response = await self.send_message(
            conversation_id=conversation_id,
            message=full_prompt,
        )

        # Parse the response to extract reasoning and answer
        # This assumes a structured format in the response
        return {
            "task": task,
            "response": response.message,
            "tokens_used": response.tokens_used,
            "tools_used": [tc.function_name for tc in response.tool_calls],
        }
