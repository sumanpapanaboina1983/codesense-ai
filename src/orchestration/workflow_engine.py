"""
Workflow execution engine for document generation.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Type

from src.agentic.context_manager import ContextManager
from src.agentic.reasoning_engine import ReasoningEngine, ReasoningResult
from src.agentic.verification_engine import VerificationEngine, VerificationResult
from src.copilot.conversation_handler import ConversationHandler
from src.copilot.sdk_client import CopilotSDKClient
from src.core.constants import DocumentType, VerificationStatus, WorkflowStatus
from src.core.exceptions import WorkflowError
from src.core.logging import get_logger
from src.domain.document import Document, VerificationResult as DocVerificationResult
from src.mcp.tool_registry import MCPToolRegistry
from src.orchestration.state_machine import StateMachine, WorkflowState
from src.skills.registry import SkillRegistry

logger = get_logger(__name__)


@dataclass
class WorkflowContext:
    """Context for workflow execution."""

    session_id: str
    codebase_path: str
    component_name: Optional[str] = None
    parent_document_id: Optional[str] = None
    preferences: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """Result of workflow execution."""

    workflow_id: str
    workflow_type: str
    status: WorkflowStatus
    document: Optional[Document] = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    reasoning_traces: list[dict[str, Any]] = field(default_factory=list)
    verification: Optional[VerificationResult] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0


class BaseWorkflow(ABC):
    """
    Abstract base class for workflows.
    """

    def __init__(
        self,
        copilot_client: CopilotSDKClient,
        tool_registry: MCPToolRegistry,
        skill_registry: SkillRegistry,
        reasoning_engine: ReasoningEngine,
        verification_engine: VerificationEngine,
    ) -> None:
        self.copilot_client = copilot_client
        self.tool_registry = tool_registry
        self.skill_registry = skill_registry
        self.reasoning_engine = reasoning_engine
        self.verification_engine = verification_engine
        self.conversation_handler = ConversationHandler(copilot_client, tool_registry)

    @property
    @abstractmethod
    def workflow_type(self) -> str:
        """Return workflow type identifier."""
        ...

    @property
    @abstractmethod
    def state_machine(self) -> StateMachine:
        """Return the state machine for this workflow."""
        ...

    @abstractmethod
    async def execute(self, context: WorkflowContext) -> WorkflowResult:
        """Execute the workflow."""
        ...

    def _generate_workflow_id(self) -> str:
        """Generate a unique workflow ID."""
        return f"wf_{self.workflow_type}_{uuid.uuid4().hex[:12]}"

    def _generate_document_id(self) -> str:
        """Generate a unique document ID."""
        return f"doc_{uuid.uuid4().hex[:16]}"


class WorkflowEngine:
    """
    Main workflow orchestration engine.
    Manages workflow lifecycle and execution.
    """

    def __init__(
        self,
        copilot_client: CopilotSDKClient,
        tool_registry: MCPToolRegistry,
        skill_registry: Optional[SkillRegistry] = None,
        reasoning_engine: Optional[ReasoningEngine] = None,
        verification_engine: Optional[VerificationEngine] = None,
    ) -> None:
        """
        Initialize the workflow engine.

        Args:
            copilot_client: Copilot SDK client
            tool_registry: MCP tool registry
            skill_registry: Skill registry
            reasoning_engine: Reasoning engine
            verification_engine: Verification engine
        """
        self.copilot_client = copilot_client
        self.tool_registry = tool_registry
        self.skill_registry = skill_registry or SkillRegistry()
        self.reasoning_engine = reasoning_engine or ReasoningEngine(
            copilot_client, tool_registry
        )
        self.verification_engine = verification_engine

        self._workflows: dict[str, BaseWorkflow] = {}
        self._active_workflows: dict[str, WorkflowState] = {}

    def register_workflow(self, workflow_class: Type[BaseWorkflow]) -> None:
        """
        Register a workflow type.

        Args:
            workflow_class: Workflow class to register
        """
        workflow = workflow_class(
            copilot_client=self.copilot_client,
            tool_registry=self.tool_registry,
            skill_registry=self.skill_registry,
            reasoning_engine=self.reasoning_engine,
            verification_engine=self.verification_engine,
        )
        self._workflows[workflow.workflow_type] = workflow
        logger.info(f"Registered workflow: {workflow.workflow_type}")

    async def execute_workflow(
        self,
        workflow_type: str,
        context: WorkflowContext,
    ) -> WorkflowResult:
        """
        Execute a workflow.

        Args:
            workflow_type: Type of workflow to execute
            context: Workflow context

        Returns:
            Workflow execution result
        """
        if workflow_type not in self._workflows:
            raise WorkflowError(
                workflow_name=workflow_type,
                message=f"Unknown workflow type: {workflow_type}",
            )

        workflow = self._workflows[workflow_type]
        start_time = datetime.utcnow()

        logger.info(
            "Starting workflow",
            workflow_type=workflow_type,
            session_id=context.session_id,
            component=context.component_name,
        )

        try:
            result = await workflow.execute(context)
            result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()

            logger.info(
                "Workflow completed",
                workflow_id=result.workflow_id,
                status=result.status.value,
                duration=result.duration_seconds,
            )

            return result

        except Exception as e:
            logger.exception(
                "Workflow failed",
                workflow_type=workflow_type,
                error=str(e),
            )
            return WorkflowResult(
                workflow_id=workflow._generate_workflow_id(),
                workflow_type=workflow_type,
                status=WorkflowStatus.FAILED,
                error=str(e),
                duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
            )

    async def execute_brd_workflow(
        self,
        session_id: str,
        component_name: str,
        codebase_path: str = "/codebase",
    ) -> WorkflowResult:
        """
        Convenience method to execute BRD workflow.

        Args:
            session_id: Session ID
            component_name: Component to analyze
            codebase_path: Path to codebase

        Returns:
            Workflow result with BRD document
        """
        context = WorkflowContext(
            session_id=session_id,
            codebase_path=codebase_path,
            component_name=component_name,
        )
        return await self.execute_workflow("brd", context)

    async def execute_epic_workflow(
        self,
        session_id: str,
        brd_document_id: str,
        codebase_path: str = "/codebase",
    ) -> WorkflowResult:
        """
        Convenience method to execute Epic workflow.

        Args:
            session_id: Session ID
            brd_document_id: Parent BRD document ID
            codebase_path: Path to codebase

        Returns:
            Workflow result with Epic documents
        """
        context = WorkflowContext(
            session_id=session_id,
            codebase_path=codebase_path,
            parent_document_id=brd_document_id,
        )
        return await self.execute_workflow("epic", context)

    async def execute_backlog_workflow(
        self,
        session_id: str,
        epic_id: str,
        codebase_path: str = "/codebase",
    ) -> WorkflowResult:
        """
        Convenience method to execute Backlog workflow.

        Args:
            session_id: Session ID
            epic_id: Parent Epic ID
            codebase_path: Path to codebase

        Returns:
            Workflow result with Backlog items
        """
        context = WorkflowContext(
            session_id=session_id,
            codebase_path=codebase_path,
            parent_document_id=epic_id,
        )
        return await self.execute_workflow("backlog", context)

    def get_workflow_status(self, workflow_id: str) -> Optional[WorkflowState]:
        """Get the status of a workflow."""
        return self._active_workflows.get(workflow_id)

    def list_registered_workflows(self) -> list[str]:
        """List all registered workflow types."""
        return list(self._workflows.keys())
