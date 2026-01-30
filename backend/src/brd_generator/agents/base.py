"""Base agent class for multi-agent BRD architecture.

Supports AGENTIC TOOL CALLING:
- Agents can use MCP tools (Neo4j, Filesystem) dynamically
- The Copilot SDK's agentic loop handles tool calls
- No hardcoded orchestration - LLM decides what tools to use
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..core.tool_registry import ToolRegistry

logger = get_logger(__name__)


class AgentRole(str, Enum):
    """Agent roles in the multi-agent system."""

    GENERATOR = "generator"  # Generates BRD content
    VERIFIER = "verifier"  # Verifies and validates BRD content
    ORCHESTRATOR = "orchestrator"  # Coordinates agents


class MessageType(str, Enum):
    """Types of messages exchanged between agents."""

    # Generator -> Verifier
    BRD_SECTION = "brd_section"  # A BRD section to verify
    BRD_COMPLETE = "brd_complete"  # Full BRD for final verification

    # Verifier -> Generator
    VERIFICATION_RESULT = "verification_result"  # Verification outcome
    FEEDBACK = "feedback"  # Feedback for regeneration
    APPROVED = "approved"  # Section/BRD approved

    # Control messages
    START = "start"  # Start processing
    STOP = "stop"  # Stop processing
    ERROR = "error"  # Error occurred


class AgentMessage(BaseModel):
    """Message exchanged between agents."""

    id: str = Field(default_factory=lambda: f"MSG-{datetime.now().strftime('%H%M%S%f')}")
    timestamp: datetime = Field(default_factory=datetime.now)
    message_type: MessageType
    sender: AgentRole
    recipient: AgentRole

    # Content
    content: Any = None
    section_name: Optional[str] = None
    iteration: int = 1

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentState(BaseModel):
    """State of an agent."""

    role: AgentRole
    is_active: bool = False
    current_task: Optional[str] = None
    iteration: int = 0
    messages_processed: int = 0
    last_message_at: Optional[datetime] = None

    # Performance tracking
    total_processing_time_ms: int = 0
    errors: list[str] = Field(default_factory=list)


class BaseAgent(ABC):
    """
    Base class for agents in the multi-agent BRD system.

    Supports AGENTIC TOOL CALLING:
    - Agents can use MCP tools (Neo4j, Filesystem) via tool_registry
    - The agentic loop handles tool calls automatically
    - LLM decides what tools to use based on the task

    All agents communicate through messages and coordinate via the orchestrator.
    """

    def __init__(
        self,
        role: AgentRole,
        copilot_session: Any = None,
        tool_registry: Optional["ToolRegistry"] = None,
        config: dict[str, Any] = None,
    ):
        """
        Initialize the agent.

        Args:
            role: The role of this agent
            copilot_session: Copilot SDK session for LLM access
            tool_registry: Registry of MCP tools for agentic calling
            config: Agent-specific configuration
        """
        self.role = role
        self.session = copilot_session
        self.tool_registry = tool_registry
        self.config = config or {}

        # State
        self.state = AgentState(role=role)

        # Message queues
        self._inbox: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._outbox: asyncio.Queue[AgentMessage] = asyncio.Queue()

        # Control
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Agentic loop settings
        self.max_tool_iterations = config.get("max_tool_iterations", 10) if config else 10
        self.enable_agentic_tools = config.get("enable_agentic_tools", True) if config else True

        # Skill instructions (from skill YAML)
        self.skill_instructions = config.get("skill_instructions", "") if config else ""

        tools_status = "enabled" if (tool_registry and self.enable_agentic_tools) else "disabled"
        skill_status = "with skill" if self.skill_instructions else "no skill"
        logger.info(f"Agent initialized: {role.value} (agentic tools: {tools_status}, {skill_status})")

    @property
    def is_running(self) -> bool:
        """Check if agent is running."""
        return self._running

    async def start(self) -> None:
        """Start the agent's processing loop."""
        if self._running:
            logger.warning(f"Agent {self.role.value} already running")
            return

        self._running = True
        self.state.is_active = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info(f"Agent {self.role.value} started")

    async def stop(self) -> None:
        """Stop the agent's processing loop."""
        self._running = False
        self.state.is_active = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info(f"Agent {self.role.value} stopped")

    async def send(self, message: AgentMessage) -> None:
        """
        Send a message to the outbox for delivery.

        Args:
            message: The message to send
        """
        message.sender = self.role
        await self._outbox.put(message)
        logger.debug(f"Agent {self.role.value} sent message: {message.message_type.value}")

    async def receive(self, timeout: float = None) -> Optional[AgentMessage]:
        """
        Receive a message from the inbox.

        Args:
            timeout: Optional timeout in seconds

        Returns:
            The received message, or None if timeout
        """
        try:
            if timeout:
                message = await asyncio.wait_for(
                    self._inbox.get(),
                    timeout=timeout
                )
            else:
                message = await self._inbox.get()

            self.state.messages_processed += 1
            self.state.last_message_at = datetime.now()
            return message

        except asyncio.TimeoutError:
            return None

    async def deliver(self, message: AgentMessage) -> None:
        """
        Deliver a message to this agent's inbox.

        Args:
            message: The message to deliver
        """
        await self._inbox.put(message)

    async def get_outgoing(self) -> Optional[AgentMessage]:
        """
        Get an outgoing message from the outbox (non-blocking).

        Returns:
            The outgoing message, or None if no messages
        """
        try:
            return self._outbox.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _process_loop(self) -> None:
        """Main processing loop for the agent."""
        while self._running:
            try:
                message = await self.receive(timeout=1.0)
                if message:
                    start_time = datetime.now()
                    await self._handle_message(message)
                    elapsed = (datetime.now() - start_time).total_seconds() * 1000
                    self.state.total_processing_time_ms += int(elapsed)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent {self.role.value} error: {e}")
                self.state.errors.append(str(e))

    async def _handle_message(self, message: AgentMessage) -> None:
        """
        Handle an incoming message.

        Args:
            message: The message to handle
        """
        logger.debug(
            f"Agent {self.role.value} handling message: {message.message_type.value}"
        )

        # Update state
        self.state.current_task = f"Processing {message.message_type.value}"
        self.state.iteration = message.iteration

        # Route to appropriate handler
        if message.message_type == MessageType.START:
            await self.on_start(message)
        elif message.message_type == MessageType.STOP:
            await self.on_stop(message)
        elif message.message_type == MessageType.ERROR:
            await self.on_error(message)
        else:
            await self.process(message)

        self.state.current_task = None

    @abstractmethod
    async def process(self, message: AgentMessage) -> None:
        """
        Process a message. Must be implemented by subclasses.

        Args:
            message: The message to process
        """
        pass

    async def on_start(self, message: AgentMessage) -> None:
        """Handle start message. Override in subclasses if needed."""
        logger.info(f"Agent {self.role.value} received start signal")

    async def on_stop(self, message: AgentMessage) -> None:
        """Handle stop message. Override in subclasses if needed."""
        logger.info(f"Agent {self.role.value} received stop signal")
        await self.stop()

    async def on_error(self, message: AgentMessage) -> None:
        """Handle error message. Override in subclasses if needed."""
        logger.error(f"Agent {self.role.value} received error: {message.content}")
        self.state.errors.append(str(message.content))

    async def send_to_llm(self, prompt: str, timeout: float = 300, use_tools: bool = True) -> str:
        """
        Send a prompt to the LLM via Copilot SDK with AGENTIC TOOL CALLING.

        When tools are enabled:
        - Tools (Neo4j, Filesystem) are passed to the LLM
        - LLM can decide to call tools to gather information
        - Agentic loop handles tool calls and feeds results back
        - Loop continues until LLM provides final response

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds
            use_tools: Whether to enable agentic tool calling

        Returns:
            The LLM response (after any tool calls are resolved)
        """
        if not self.session:
            logger.warning(f"Agent {self.role.value}: No Copilot session, returning mock response")
            return self._generate_mock_response(prompt)

        # Check if we should use agentic tools
        should_use_tools = (
            use_tools and
            self.enable_agentic_tools and
            self.tool_registry is not None
        )

        try:
            if should_use_tools:
                return await self._send_with_agentic_loop(prompt, timeout)
            else:
                return await self._send_simple(prompt, timeout)

        except asyncio.TimeoutError:
            logger.warning(f"Agent {self.role.value}: LLM timeout after {timeout}s")
            return self._generate_mock_response(prompt)
        except Exception as e:
            logger.error(f"Agent {self.role.value}: LLM error: {e}")
            return self._generate_mock_response(prompt)

    async def _send_simple(self, prompt: str, timeout: float) -> str:
        """Send prompt without tool calling (simple mode)."""
        message_options = {"prompt": prompt}
        logger.info(f"Agent {self.role.value}: Sending to LLM (simple mode, {len(prompt)} chars)")

        if hasattr(self.session, 'send_and_wait'):
            event = await asyncio.wait_for(
                self.session.send_and_wait(message_options, timeout=timeout),
                timeout=timeout
            )
            if event:
                return self._extract_from_event(event)

        if hasattr(self.session, 'send'):
            await self.session.send(message_options)
            return await self._wait_for_response(timeout)

        return self._generate_mock_response(prompt)

    async def _send_with_agentic_loop(self, prompt: str, timeout: float) -> str:
        """
        Send prompt with AGENTIC TOOL CALLING loop.

        This is the core of the agentic architecture:
        1. Send prompt with available tools and skill instructions
        2. If LLM wants to call a tool, execute it and feed result back
        3. Repeat until LLM provides final response
        """
        logger.info(f"Agent {self.role.value}: Starting agentic loop with tools")

        # Get tool definitions
        tools = self.tool_registry.get_tool_definitions()
        logger.info(f"Agent {self.role.value}: {len(tools)} tools available")

        # Include skill instructions if available
        full_prompt = prompt
        if self.skill_instructions:
            full_prompt = f"""## Skill Instructions
{self.skill_instructions}

## Task
{prompt}"""
            logger.info(f"Agent {self.role.value}: Using skill instructions")

        # Build initial message with tools
        message_options = {
            "prompt": full_prompt,
            "tools": tools,
        }

        iteration = 0
        start_time = asyncio.get_event_loop().time()

        while iteration < self.max_tool_iterations:
            iteration += 1
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining_timeout = timeout - elapsed

            if remaining_timeout <= 0:
                logger.warning(f"Agent {self.role.value}: Agentic loop timeout")
                break

            logger.info(f"Agent {self.role.value}: Agentic iteration {iteration}")

            # Send to LLM
            event = await asyncio.wait_for(
                self.session.send_and_wait(message_options, timeout=remaining_timeout),
                timeout=remaining_timeout
            )

            if not event:
                logger.warning(f"Agent {self.role.value}: No event from LLM")
                break

            # Check if LLM wants to call tools
            tool_calls = self._extract_tool_calls(event)

            if tool_calls:
                # Execute tool calls and prepare results
                logger.info(f"Agent {self.role.value}: LLM requested {len(tool_calls)} tool calls")
                tool_results = await self._execute_tool_calls(tool_calls)

                # Build next message with tool results
                message_options = {
                    "tool_results": tool_results,
                }
            else:
                # No tool calls - LLM has final response
                response = self._extract_from_event(event)
                logger.info(f"Agent {self.role.value}: Agentic loop complete after {iteration} iterations")
                return response

        # Max iterations reached
        logger.warning(f"Agent {self.role.value}: Max tool iterations ({self.max_tool_iterations}) reached")
        return self._extract_from_event(event) if event else ""

    def _extract_tool_calls(self, event: Any) -> list[dict[str, Any]]:
        """Extract tool calls from LLM response event."""
        tool_calls = []

        try:
            # Check various possible locations for tool calls
            if hasattr(event, 'data'):
                data = event.data

                # Check for tool_calls in message
                if hasattr(data, 'message'):
                    msg = data.message
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        for tc in msg.tool_calls:
                            tool_calls.append({
                                "id": getattr(tc, 'id', f"tc_{len(tool_calls)}"),
                                "name": getattr(tc, 'name', None) or getattr(tc.function, 'name', None),
                                "arguments": self._parse_tool_arguments(tc),
                            })

                # Check for tool_calls directly on data
                if hasattr(data, 'tool_calls') and data.tool_calls:
                    for tc in data.tool_calls:
                        tool_calls.append({
                            "id": getattr(tc, 'id', f"tc_{len(tool_calls)}"),
                            "name": getattr(tc, 'name', None) or getattr(tc.function, 'name', None),
                            "arguments": self._parse_tool_arguments(tc),
                        })

            # Check for tool_calls directly on event
            if hasattr(event, 'tool_calls') and event.tool_calls:
                for tc in event.tool_calls:
                    tool_calls.append({
                        "id": getattr(tc, 'id', f"tc_{len(tool_calls)}"),
                        "name": getattr(tc, 'name', None),
                        "arguments": self._parse_tool_arguments(tc),
                    })

        except Exception as e:
            logger.error(f"Error extracting tool calls: {e}")

        return tool_calls

    def _parse_tool_arguments(self, tool_call: Any) -> dict[str, Any]:
        """Parse tool call arguments from various formats."""
        try:
            # Try function.arguments (OpenAI format)
            if hasattr(tool_call, 'function') and hasattr(tool_call.function, 'arguments'):
                args = tool_call.function.arguments
                if isinstance(args, str):
                    return json.loads(args)
                return args

            # Try arguments directly
            if hasattr(tool_call, 'arguments'):
                args = tool_call.arguments
                if isinstance(args, str):
                    return json.loads(args)
                return args

            # Try input (Anthropic format)
            if hasattr(tool_call, 'input'):
                return tool_call.input

            return {}
        except Exception as e:
            logger.error(f"Error parsing tool arguments: {e}")
            return {}

    async def _execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute tool calls and return results."""
        results = []

        for tc in tool_calls:
            tool_name = tc.get("name")
            tool_args = tc.get("arguments", {})
            tool_id = tc.get("id", "unknown")

            logger.info(f"Agent {self.role.value}: Executing tool '{tool_name}'")

            try:
                # Execute via tool registry
                result = await self.tool_registry.execute_tool(tool_name, tool_args)

                results.append({
                    "tool_call_id": tool_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": result,
                })

                logger.info(f"Agent {self.role.value}: Tool '{tool_name}' executed successfully")

            except Exception as e:
                logger.error(f"Agent {self.role.value}: Tool '{tool_name}' failed: {e}")
                results.append({
                    "tool_call_id": tool_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps({"error": str(e)}),
                })

        return results

    def _extract_from_event(self, event: Any) -> str:
        """Extract text content from a Copilot event."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                if hasattr(data, 'message') and hasattr(data.message, 'content'):
                    return str(data.message.content)
                if hasattr(data, 'content'):
                    return str(data.content)
                if hasattr(data, 'text'):
                    return str(data.text)

            if hasattr(event, 'content'):
                return str(event.content)
            if hasattr(event, 'text'):
                return str(event.text)

            return str(event)
        except Exception as e:
            logger.error(f"Error extracting from event: {e}")
            return ""

    async def _wait_for_response(self, timeout: float) -> str:
        """Wait for LLM response by polling messages."""
        start_time = asyncio.get_event_loop().time()
        poll_interval = 1.0

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return ""

            try:
                messages = self.session.get_messages()
                for msg in reversed(messages):
                    if hasattr(msg, 'data'):
                        data = msg.data
                        if hasattr(data, 'role') and data.role == 'assistant':
                            return self._extract_from_event(msg)
            except Exception:
                pass

            await asyncio.sleep(poll_interval)

    def _generate_mock_response(self, prompt: str) -> str:
        """Generate a mock response for testing without LLM."""
        # Subclasses can override for role-specific mock responses
        return "Mock response - Copilot session not available"

    def get_status(self) -> dict[str, Any]:
        """Get agent status summary."""
        return {
            "role": self.role.value,
            "is_active": self.state.is_active,
            "current_task": self.state.current_task,
            "iteration": self.state.iteration,
            "messages_processed": self.state.messages_processed,
            "total_processing_time_ms": self.state.total_processing_time_ms,
            "errors": self.state.errors[-5:],  # Last 5 errors
        }
