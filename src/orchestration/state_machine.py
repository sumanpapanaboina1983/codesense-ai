"""
State machine for workflow execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from src.core.constants import WorkflowStatus
from src.core.logging import get_logger

logger = get_logger(__name__)


class StateTransitionError(Exception):
    """Invalid state transition."""
    pass


@dataclass
class StateData:
    """Data associated with a state."""

    state: str
    entered_at: datetime = field(default_factory=datetime.utcnow)
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class WorkflowState:
    """Complete workflow state."""

    workflow_id: str
    workflow_type: str
    current_state: str
    status: WorkflowStatus = WorkflowStatus.PENDING

    history: list[StateData] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    result: Optional[dict[str, Any]] = None

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def add_to_history(self, state: str, data: Optional[dict] = None) -> None:
        """Add state to history."""
        self.history.append(StateData(state=state, data=data or {}))
        self.updated_at = datetime.utcnow()

    def set_error(self, error: str) -> None:
        """Set error state."""
        self.status = WorkflowStatus.FAILED
        if self.history:
            self.history[-1].error = error
        self.updated_at = datetime.utcnow()


class StateMachine:
    """
    Generic state machine for workflow orchestration.
    """

    def __init__(
        self,
        states: list[str],
        initial_state: str,
        final_states: list[str],
        transitions: dict[str, list[str]],
    ) -> None:
        """
        Initialize the state machine.

        Args:
            states: List of valid states
            initial_state: Starting state
            final_states: Terminal states
            transitions: Valid transitions {from_state: [to_states]}
        """
        self.states = set(states)
        self.initial_state = initial_state
        self.final_states = set(final_states)
        self.transitions = transitions

        # Validate
        if initial_state not in self.states:
            raise ValueError(f"Initial state '{initial_state}' not in states")
        for final in final_states:
            if final not in self.states:
                raise ValueError(f"Final state '{final}' not in states")

    def can_transition(self, from_state: str, to_state: str) -> bool:
        """Check if transition is valid."""
        if from_state not in self.transitions:
            return False
        return to_state in self.transitions[from_state]

    def get_next_states(self, current_state: str) -> list[str]:
        """Get valid next states from current state."""
        return self.transitions.get(current_state, [])

    def is_final(self, state: str) -> bool:
        """Check if state is a final state."""
        return state in self.final_states


# Predefined state machines for workflows

BRD_WORKFLOW_STATES = [
    "init",
    "analyzing",
    "generating_draft",
    "verifying",
    "refining",
    "finalizing",
    "completed",
    "failed",
]

BRD_WORKFLOW_TRANSITIONS = {
    "init": ["analyzing"],
    "analyzing": ["generating_draft", "failed"],
    "generating_draft": ["verifying", "failed"],
    "verifying": ["refining", "finalizing", "failed"],
    "refining": ["verifying", "failed"],
    "finalizing": ["completed", "failed"],
    "completed": [],
    "failed": [],
}

EPIC_WORKFLOW_STATES = [
    "init",
    "loading_brd",
    "analyzing_components",
    "generating_epics",
    "verifying",
    "refining",
    "finalizing",
    "completed",
    "failed",
]

EPIC_WORKFLOW_TRANSITIONS = {
    "init": ["loading_brd"],
    "loading_brd": ["analyzing_components", "failed"],
    "analyzing_components": ["generating_epics", "failed"],
    "generating_epics": ["verifying", "failed"],
    "verifying": ["refining", "finalizing", "failed"],
    "refining": ["verifying", "failed"],
    "finalizing": ["completed", "failed"],
    "completed": [],
    "failed": [],
}

BACKLOG_WORKFLOW_STATES = [
    "init",
    "loading_epic",
    "analyzing_scope",
    "generating_items",
    "verifying",
    "refining",
    "finalizing",
    "completed",
    "failed",
]

BACKLOG_WORKFLOW_TRANSITIONS = {
    "init": ["loading_epic"],
    "loading_epic": ["analyzing_scope", "failed"],
    "analyzing_scope": ["generating_items", "failed"],
    "generating_items": ["verifying", "failed"],
    "verifying": ["refining", "finalizing", "failed"],
    "refining": ["verifying", "failed"],
    "finalizing": ["completed", "failed"],
    "completed": [],
    "failed": [],
}


def create_brd_state_machine() -> StateMachine:
    """Create state machine for BRD workflow."""
    return StateMachine(
        states=BRD_WORKFLOW_STATES,
        initial_state="init",
        final_states=["completed", "failed"],
        transitions=BRD_WORKFLOW_TRANSITIONS,
    )


def create_epic_state_machine() -> StateMachine:
    """Create state machine for Epic workflow."""
    return StateMachine(
        states=EPIC_WORKFLOW_STATES,
        initial_state="init",
        final_states=["completed", "failed"],
        transitions=EPIC_WORKFLOW_TRANSITIONS,
    )


def create_backlog_state_machine() -> StateMachine:
    """Create state machine for Backlog workflow."""
    return StateMachine(
        states=BACKLOG_WORKFLOW_STATES,
        initial_state="init",
        final_states=["completed", "failed"],
        transitions=BACKLOG_WORKFLOW_TRANSITIONS,
    )
