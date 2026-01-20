"""
GitHub Copilot SDK client wrapper using the official SDK.
Provides conversation management, skill injection, and streaming support.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional

from src.core.config import settings
from src.core.constants import MessageRole
from src.core.exceptions import CopilotError
from src.core.logging import get_logger

logger = get_logger(__name__)

# Try to import the official SDK
try:
    from copilot import CopilotClient, define_tool
    COPILOT_SDK_AVAILABLE = True
except ImportError:
    COPILOT_SDK_AVAILABLE = False
    CopilotClient = None
    define_tool = None
    logger.warning(
        "GitHub Copilot SDK not installed. "
        "Install with: pip install github-copilot-sdk"
    )


@dataclass
class Message:
    """A message in the conversation."""

    role: MessageRole
    content: str
    metadata: Optional[dict[str, Any]] = None
    name: Optional[str] = None  # For tool messages
    tool_call_id: Optional[str] = None  # For tool responses

    def to_dict(self) -> dict[str, Any]:
        """Convert to API format."""
        msg = {"role": self.role.value, "content": self.content}
        if self.name:
            msg["name"] = self.name
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        return msg


@dataclass
class ToolCall:
    """A tool call requested by the model."""

    id: str
    function_name: str
    arguments: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolCall":
        """Create from API response."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            function_name=data.get("function", {}).get("name", data.get("name", "")),
            arguments=data.get("function", {}).get("arguments", data.get("arguments", {})),
        )

    def dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "function_name": self.function_name,
            "arguments": self.arguments,
        }


@dataclass
class CopilotResponse:
    """Response from Copilot."""

    content: str
    conversation_id: str
    tokens_used: int = 0
    model: str = ""
    skills_used: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    stop_reason: str = "stop"

    # Alias for backwards compatibility
    @property
    def message(self) -> str:
        return self.content

    @property
    def finish_reason(self) -> str:
        return self.stop_reason


@dataclass
class Conversation:
    """A conversation with Copilot."""

    id: str
    session: Any = None  # Copilot SDK session
    messages: list[Message] = field(default_factory=list)
    active_skills: list[str] = field(default_factory=list)
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class CopilotSDKClient:
    """
    Wrapper around the official GitHub Copilot SDK.
    Manages conversations, skill injection, and tool calling.

    Requires:
    - GitHub Copilot CLI installed and in PATH
    - github-copilot-sdk Python package installed
    - Valid GitHub authentication (GH_TOKEN or GITHUB_TOKEN environment variable)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        cli_path: Optional[str] = None,
        auto_start: bool = True,
    ) -> None:
        """
        Initialize the Copilot SDK client.

        Args:
            api_key: GitHub token (uses GH_TOKEN/GITHUB_TOKEN env var if not provided)
            model: Model to use (e.g., "claude-sonnet-4-5", "gpt-4")
            cli_path: Path to Copilot CLI executable
            auto_start: Whether to auto-start the CLI server
        """
        self.api_key = api_key or settings.copilot.api_key
        self.model = model or settings.copilot.model or "claude-sonnet-4-5"
        self.cli_path = cli_path or settings.copilot.cli_path
        self.auto_start = auto_start

        self._client: Optional[Any] = None
        self._conversations: dict[str, Conversation] = {}
        self._skill_prompts: dict[str, str] = {}
        self._tools: dict[str, Callable] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the Copilot SDK client."""
        if self._initialized:
            return

        if not COPILOT_SDK_AVAILABLE:
            logger.warning(
                "Copilot SDK not available, running in fallback mode"
            )
            self._initialized = True
            return

        try:
            config = {
                "auto_start": self.auto_start,
                "log_level": "info" if settings.debug else "warning",
            }

            if self.cli_path:
                config["cli_path"] = self.cli_path

            self._client = CopilotClient(config)
            await self._client.start()
            self._initialized = True

            logger.info(
                "Copilot SDK client initialized",
                model=self.model,
                cli_path=self.cli_path,
            )
        except Exception as e:
            logger.error("Failed to initialize Copilot SDK", error=str(e))
            self._initialized = True  # Mark as initialized to avoid retries

    async def close(self) -> None:
        """Close the Copilot SDK client."""
        if self._client is not None:
            try:
                # Clean up all sessions
                for conv_id, conv in list(self._conversations.items()):
                    if conv.session:
                        try:
                            await conv.session.destroy()
                        except Exception:
                            pass
                self._conversations.clear()

                # Stop the client
                if hasattr(self._client, 'stop'):
                    await self._client.stop()
            except Exception as e:
                logger.warning("Error closing Copilot client", error=str(e))
            finally:
                self._client = None
                self._initialized = False

    def register_skill_prompt(self, skill_name: str, prompt: str) -> None:
        """
        Register a skill's prompt for injection.

        Args:
            skill_name: Name of the skill
            prompt: The skill's prompt text
        """
        self._skill_prompts[skill_name] = prompt
        logger.debug("Registered skill prompt", skill=skill_name)

    def register_tool(
        self,
        name: str,
        handler: Callable,
        description: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Register a tool for function calling.

        Args:
            name: Tool name
            handler: Async function to handle tool calls
            description: Tool description
            parameters: JSON schema for parameters
        """
        self._tools[name] = {
            "handler": handler,
            "description": description,
            "parameters": parameters or {},
        }
        logger.debug("Registered tool", name=name)

    async def create_conversation(
        self,
        system_prompt: str,
        skills: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Create a new conversation.

        Args:
            system_prompt: Base system prompt
            skills: Skills to inject into system context
            metadata: Optional metadata

        Returns:
            Conversation ID
        """
        await self.initialize()

        conv_id = f"conv_{uuid.uuid4().hex[:16]}"

        # Build system message with injected skills
        full_system_prompt = self._build_system_prompt(system_prompt, skills or [])

        # Create SDK session if available
        session = None
        if self._client is not None and COPILOT_SDK_AVAILABLE:
            try:
                session_config = {
                    "model": self.model,
                    "system_prompt": full_system_prompt,
                }

                # Add tools if registered
                if self._tools:
                    session_config["tools"] = self._get_sdk_tools()

                session = await self._client.create_session(session_config)
            except Exception as e:
                logger.warning("Failed to create SDK session", error=str(e))

        conversation = Conversation(
            id=conv_id,
            session=session,
            messages=[
                Message(role=MessageRole.SYSTEM, content=full_system_prompt)
            ],
            active_skills=skills or [],
            metadata=metadata or {},
        )

        self._conversations[conv_id] = conversation

        logger.info(
            "Created conversation",
            conversation_id=conv_id,
            skills=skills,
            has_sdk_session=session is not None,
        )

        return conv_id

    def _build_system_prompt(
        self,
        base_prompt: str,
        skills: list[str],
    ) -> str:
        """
        Build system prompt with injected skills.

        Args:
            base_prompt: Base system prompt
            skills: Skills to inject

        Returns:
            Complete system prompt
        """
        prompt_parts = [base_prompt]

        for skill_name in skills:
            if skill_name in self._skill_prompts:
                skill_prompt = self._skill_prompts[skill_name]
                prompt_parts.append(f"\n\n## Skill: {skill_name}\n{skill_prompt}")
            else:
                logger.warning("Skill prompt not found", skill=skill_name)

        return "\n".join(prompt_parts)

    def _get_sdk_tools(self) -> list[Any]:
        """Get tools in SDK format."""
        sdk_tools = []
        for name, tool_info in self._tools.items():
            # Create tool definition for SDK
            sdk_tools.append({
                "name": name,
                "description": tool_info["description"],
                "parameters": tool_info["parameters"],
                "handler": tool_info["handler"],
            })
        return sdk_tools

    async def inject_skills(
        self,
        conversation_id: str,
        skill_names: list[str],
    ) -> None:
        """
        Dynamically inject additional skills into a conversation.

        Args:
            conversation_id: ID of the conversation
            skill_names: Skills to inject
        """
        if conversation_id not in self._conversations:
            raise CopilotError(f"Conversation not found: {conversation_id}")

        conversation = self._conversations[conversation_id]

        # Get the system message
        if not conversation.messages or conversation.messages[0].role != MessageRole.SYSTEM:
            raise CopilotError("Conversation has no system message")

        system_msg = conversation.messages[0]

        # Add new skills
        for skill_name in skill_names:
            if skill_name not in conversation.active_skills:
                if skill_name in self._skill_prompts:
                    skill_prompt = self._skill_prompts[skill_name]
                    system_msg.content += f"\n\n## Skill: {skill_name}\n{skill_prompt}"
                    conversation.active_skills.append(skill_name)

        logger.info(
            "Injected skills",
            conversation_id=conversation_id,
            skills=skill_names,
        )

    async def send_message(
        self,
        message: str,
        conversation_id: str,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
    ) -> CopilotResponse:
        """
        Send a message and get a response.

        Args:
            message: User message
            conversation_id: Conversation ID
            tools: Available tools for function calling
            temperature: Sampling temperature

        Returns:
            Copilot response
        """
        await self.initialize()

        if conversation_id not in self._conversations:
            raise CopilotError(f"Conversation not found: {conversation_id}")

        conversation = self._conversations[conversation_id]

        # Add user message to history
        if message:
            conversation.messages.append(
                Message(role=MessageRole.USER, content=message)
            )

        # Try to use SDK session
        if conversation.session is not None and COPILOT_SDK_AVAILABLE:
            try:
                return await self._send_via_sdk(
                    conversation, message, tools, temperature
                )
            except Exception as e:
                logger.warning(
                    "SDK message failed, using fallback",
                    error=str(e),
                )

        # Fallback response when SDK is not available
        return self._create_fallback_response(conversation_id, message)

    async def _send_via_sdk(
        self,
        conversation: Conversation,
        message: str,
        tools: Optional[list[dict[str, Any]]],
        temperature: Optional[float],
    ) -> CopilotResponse:
        """Send message through the official SDK."""
        response_content = ""
        tool_calls = []
        done_event = asyncio.Event()

        def on_event(event):
            nonlocal response_content, tool_calls

            event_type = event.type.value if hasattr(event.type, 'value') else str(event.type)

            if event_type == "assistant.message":
                response_content = event.data.content
            elif event_type == "assistant.message_delta":
                if hasattr(event.data, 'delta_content'):
                    response_content += event.data.delta_content
            elif event_type == "tool.call":
                tool_calls.append(ToolCall(
                    id=event.data.id,
                    function_name=event.data.name,
                    arguments=event.data.arguments,
                ))
            elif event_type == "session.idle":
                done_event.set()

        # Subscribe to events
        conversation.session.on(on_event)

        # Send the message
        await conversation.session.send({"prompt": message})

        # Wait for response with timeout
        try:
            await asyncio.wait_for(done_event.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            logger.warning("SDK response timed out")

        # Add assistant response to conversation history
        conversation.messages.append(
            Message(role=MessageRole.ASSISTANT, content=response_content)
        )

        return CopilotResponse(
            content=response_content,
            conversation_id=conversation.id,
            tokens_used=0,  # SDK doesn't provide token counts directly
            model=self.model,
            skills_used=conversation.active_skills,
            tool_calls=tool_calls,
            stop_reason="stop",
        )

    def _create_fallback_response(
        self,
        conversation_id: str,
        message: str,
    ) -> CopilotResponse:
        """Create a fallback response when SDK is not available."""
        fallback_content = (
            f"I received your message: '{message[:100]}...'\n\n"
            "**Note:** The GitHub Copilot SDK is not properly configured.\n\n"
            "To enable AI responses, please ensure:\n"
            "1. GitHub Copilot CLI is installed (`brew install copilot-cli` or `npm install -g @github/copilot`)\n"
            "2. GitHub Copilot SDK is installed (`pip install github-copilot-sdk`)\n"
            "3. You're authenticated (`GH_TOKEN` or `GITHUB_TOKEN` environment variable)\n"
            "4. You have an active GitHub Copilot subscription\n\n"
            "CodeSense AI can help you:\n"
            "- Analyze legacy codebases\n"
            "- Generate Business Requirements Documents (BRDs)\n"
            "- Create Epics and User Stories\n"
            "- Understand code dependencies and relationships"
        )

        return CopilotResponse(
            content=fallback_content,
            conversation_id=conversation_id,
            tokens_used=0,
            model="fallback",
            stop_reason="stop",
        )

    async def add_tool_result(
        self,
        conversation_id: str,
        tool_call_id: str,
        result: Any,
    ) -> None:
        """
        Add a tool execution result to the conversation.

        Args:
            conversation_id: Conversation ID
            tool_call_id: ID of the tool call
            result: Tool execution result
        """
        if conversation_id not in self._conversations:
            raise CopilotError(f"Conversation not found: {conversation_id}")

        conversation = self._conversations[conversation_id]

        # Add tool result as a message
        result_content = json.dumps(result) if not isinstance(result, str) else result

        conversation.messages.append(
            Message(
                role=MessageRole.TOOL,
                content=result_content,
                tool_call_id=tool_call_id,
            )
        )

        logger.debug(
            "Added tool result",
            conversation_id=conversation_id,
            tool_call_id=tool_call_id,
        )

    async def stream_message(
        self,
        message: str,
        conversation_id: str,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        """
        Stream a response chunk by chunk.

        Args:
            message: User message
            conversation_id: Conversation ID
            tools: Available tools

        Yields:
            Response chunks
        """
        await self.initialize()

        if conversation_id not in self._conversations:
            raise CopilotError(f"Conversation not found: {conversation_id}")

        conversation = self._conversations[conversation_id]

        # Add user message
        if message:
            conversation.messages.append(
                Message(role=MessageRole.USER, content=message)
            )

        # Try streaming via SDK
        if conversation.session is not None and COPILOT_SDK_AVAILABLE:
            try:
                async for chunk in self._stream_via_sdk(conversation, message):
                    yield chunk
                return
            except Exception as e:
                logger.warning("SDK streaming failed", error=str(e))

        # Fallback
        fallback = self._create_fallback_response(conversation_id, message)
        yield fallback.content

    async def _stream_via_sdk(
        self,
        conversation: Conversation,
        message: str,
    ) -> AsyncIterator[str]:
        """Stream response through the SDK."""
        response_queue: asyncio.Queue[str | None] = asyncio.Queue()
        full_response = ""

        def on_event(event):
            nonlocal full_response
            event_type = event.type.value if hasattr(event.type, 'value') else str(event.type)

            if event_type == "assistant.message_delta":
                if hasattr(event.data, 'delta_content'):
                    chunk = event.data.delta_content
                    full_response += chunk
                    response_queue.put_nowait(chunk)
            elif event_type == "assistant.message":
                # Final message
                response_queue.put_nowait(None)
            elif event_type == "session.idle":
                response_queue.put_nowait(None)

        conversation.session.on(on_event)
        await conversation.session.send({"prompt": message})

        # Yield chunks from queue
        while True:
            try:
                chunk = await asyncio.wait_for(response_queue.get(), timeout=60.0)
                if chunk is None:
                    break
                yield chunk
            except asyncio.TimeoutError:
                break

        # Add complete response to history
        conversation.messages.append(
            Message(role=MessageRole.ASSISTANT, content=full_response)
        )

    def get_conversation_history(
        self,
        conversation_id: str,
    ) -> list[Message]:
        """
        Get the full conversation history.

        Args:
            conversation_id: Conversation ID

        Returns:
            List of messages
        """
        if conversation_id not in self._conversations:
            raise CopilotError(f"Conversation not found: {conversation_id}")

        return self._conversations[conversation_id].messages.copy()

    def get_conversation_tokens(self, conversation_id: str) -> int:
        """Get total tokens used in a conversation."""
        if conversation_id not in self._conversations:
            return 0
        return self._conversations[conversation_id].total_tokens

    def delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation."""
        if conversation_id in self._conversations:
            conv = self._conversations[conversation_id]
            # Clean up SDK session
            if conv.session is not None:
                try:
                    asyncio.create_task(conv.session.destroy())
                except Exception:
                    pass
            del self._conversations[conversation_id]
            logger.info("Deleted conversation", conversation_id=conversation_id)

    async def __aenter__(self) -> "CopilotSDKClient":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
