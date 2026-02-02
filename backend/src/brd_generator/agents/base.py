"""Base agent class for multi-agent BRD architecture.

The Copilot SDK handles tool calling natively:
- MCP servers are configured via mcp_servers in session config
- Skills are loaded via skill_directories in session config
- SDK automatically executes tools when LLM requests them
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..utils.logger import get_logger

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

    MCP tools are available via the Copilot SDK session:
    - MCP servers configured via mcp_servers in session config
    - SDK handles tool execution automatically

    All agents communicate through messages and coordinate via the orchestrator.
    """

    def __init__(
        self,
        role: AgentRole,
        copilot_session: Any = None,
        config: dict[str, Any] = None,
    ):
        """
        Initialize the agent.

        Args:
            role: The role of this agent
            copilot_session: Copilot SDK session for LLM access (with MCP tools)
            config: Agent-specific configuration
        """
        self.role = role
        self.session = copilot_session
        self.config = config or {}

        # State
        self.state = AgentState(role=role)

        # Message queues
        self._inbox: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._outbox: asyncio.Queue[AgentMessage] = asyncio.Queue()

        # Control
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # SDK handles tool execution via mcp_servers in session config
        self.enable_agentic_tools = config.get("enable_agentic_tools", True) if config else True

        # Log initialization details
        session_status = "connected" if copilot_session else "not available (mock mode)"
        tools_status = "enabled" if self.enable_agentic_tools else "disabled"
        logger.info(f"Agent initialized: {role.value}")
        logger.debug(f"  Session: {session_status}")
        logger.debug(f"  Agentic tools: {tools_status}")
        logger.debug(f"  Config: {config}")

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

    async def send_to_llm(
        self,
        prompt: str,
        timeout: float = 300,
        use_tools: bool = True,
    ) -> str:
        """
        Send a prompt to the LLM via Copilot SDK.

        MCP tools are available via the SDK session's mcp_servers config.
        The SDK handles tool execution automatically.

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds
            use_tools: Whether to enable tool calling (SDK handles automatically)

        Returns:
            The LLM response (after any tool calls are resolved by SDK)
        """
        if not self.session:
            logger.warning(f"Agent {self.role.value}: No Copilot session, returning mock response")
            return self._generate_mock_response(prompt)

        try:
            return await self._send_to_sdk(prompt, timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Agent {self.role.value}: LLM timeout after {timeout}s")
            return self._generate_mock_response(prompt)
        except Exception as e:
            logger.error(f"Agent {self.role.value}: LLM error: {e}")
            return self._generate_mock_response(prompt)

    async def _send_to_sdk(self, prompt: str, timeout: float) -> str:
        """
        Send prompt to Copilot SDK.

        The SDK handles:
        - Tool calling when LLM requests it (via mcp_servers)
        - Executing the tool functions
        - Feeding results back to LLM
        - Iterating until final response
        """
        import time
        start_time = time.time()

        prompt_preview = prompt[:100] + "..." if len(prompt) > 100 else prompt
        logger.info(f"[{self.role.value.upper()}] Sending to LLM ({len(prompt)} chars)")
        logger.debug(f"[{self.role.value.upper()}] Prompt preview: {prompt_preview}")
        logger.debug(f"[{self.role.value.upper()}] Timeout: {timeout}s")

        message_options = {"prompt": prompt}

        if hasattr(self.session, 'send_and_wait'):
            logger.debug(f"[{self.role.value.upper()}] Using send_and_wait method")
            event = await asyncio.wait_for(
                self.session.send_and_wait(message_options, timeout=timeout),
                timeout=timeout
            )
            elapsed = time.time() - start_time
            if event:
                response = self._extract_from_event(event)
                response_preview = response[:100] + "..." if len(response) > 100 else response
                logger.info(f"[{self.role.value.upper()}] Response received ({len(response)} chars, {elapsed:.2f}s)")
                logger.debug(f"[{self.role.value.upper()}] Response preview: {response_preview}")
                return response
            else:
                logger.warning(f"[{self.role.value.upper()}] No event returned from SDK ({elapsed:.2f}s)")

        if hasattr(self.session, 'send'):
            logger.debug(f"[{self.role.value.upper()}] Using send method (polling for response)")
            await self.session.send(message_options)
            response = await self._wait_for_response(timeout)
            elapsed = time.time() - start_time
            logger.info(f"[{self.role.value.upper()}] Response received via polling ({len(response)} chars, {elapsed:.2f}s)")
            return response

        logger.warning(f"[{self.role.value.upper()}] Session has no send methods, using mock response")
        return self._generate_mock_response(prompt)

    def _extract_from_event(self, event: Any) -> str:
        """Extract text content from a Copilot event."""
        try:
            logger.debug(f"[{self.role.value.upper()}] Extracting from event type: {type(event).__name__}")

            if hasattr(event, 'data'):
                data = event.data
                logger.debug(f"[{self.role.value.upper()}] Event has data attribute, type: {type(data).__name__}")

                if hasattr(data, 'message') and hasattr(data.message, 'content'):
                    logger.debug(f"[{self.role.value.upper()}] Extracted from data.message.content")
                    return str(data.message.content)
                if hasattr(data, 'content'):
                    logger.debug(f"[{self.role.value.upper()}] Extracted from data.content")
                    return str(data.content)
                if hasattr(data, 'text'):
                    logger.debug(f"[{self.role.value.upper()}] Extracted from data.text")
                    return str(data.text)

            if hasattr(event, 'content'):
                logger.debug(f"[{self.role.value.upper()}] Extracted from event.content")
                return str(event.content)
            if hasattr(event, 'text'):
                logger.debug(f"[{self.role.value.upper()}] Extracted from event.text")
                return str(event.text)

            logger.debug(f"[{self.role.value.upper()}] Using str(event) as fallback")
            return str(event)
        except Exception as e:
            logger.error(f"[{self.role.value.upper()}] Error extracting from event: {e}", exc_info=True)
            return ""

    async def _wait_for_response(self, timeout: float) -> str:
        """Wait for LLM response by polling messages."""
        start_time = asyncio.get_event_loop().time()
        poll_interval = 1.0
        poll_count = 0

        logger.debug(f"[{self.role.value.upper()}] Waiting for response (timeout: {timeout}s)")

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                logger.warning(f"[{self.role.value.upper()}] Polling timeout after {elapsed:.1f}s ({poll_count} polls)")
                return ""

            try:
                poll_count += 1
                messages = self.session.get_messages()
                logger.debug(f"[{self.role.value.upper()}] Poll {poll_count}: {len(messages)} messages")

                for msg in reversed(messages):
                    if hasattr(msg, 'data'):
                        data = msg.data
                        if hasattr(data, 'role') and data.role == 'assistant':
                            logger.debug(f"[{self.role.value.upper()}] Found assistant response after {poll_count} polls")
                            return self._extract_from_event(msg)
            except Exception as e:
                logger.debug(f"[{self.role.value.upper()}] Poll error: {e}")

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
