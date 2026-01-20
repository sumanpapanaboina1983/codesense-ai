"""
System-wide constants for the AI Accelerator.
"""

from enum import Enum


# =============================================================================
# Enums
# =============================================================================


class MessageRole(str, Enum):
    """Message roles in conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class SessionStatus(str, Enum):
    """Session lifecycle states."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class DocumentType(str, Enum):
    """Types of documents that can be generated."""

    BRD = "brd"
    EPIC = "epic"
    BACKLOG = "backlog"


class VerificationStatus(str, Enum):
    """Verification status for generated content."""

    VERIFIED = "verified"
    PARTIAL = "partial"
    UNVERIFIED = "unverified"


class ReasoningStep(str, Enum):
    """Steps in the reasoning engine."""

    UNDERSTAND = "understand"
    ANALYZE = "analyze"
    DECOMPOSE = "decompose"
    EXECUTE = "execute"
    VERIFY = "verify"
    SYNTHESIZE = "synthesize"


class WorkflowStatus(str, Enum):
    """Workflow execution states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FactType(str, Enum):
    """Types of facts for verification."""

    ENTITY_EXISTS = "entity_exists"
    HAS_CAPABILITY = "has_capability"
    DEPENDS_ON = "depends_on"
    CALLS = "calls"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    USES_TECHNOLOGY = "uses_technology"


# =============================================================================
# API Constants
# =============================================================================

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"

# Default pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# WebSocket
WS_HEARTBEAT_INTERVAL = 30  # seconds
WS_MESSAGE_MAX_SIZE = 1024 * 1024  # 1MB

# =============================================================================
# Copilot Constants
# =============================================================================

# Default skills always included
DEFAULT_SKILLS = ["senior-engineer-analysis"]

# Skill mappings for different task types
SKILL_MAPPINGS = {
    "brd": ["codebase-analyzer", "brd-generator", "verification"],
    "epic": ["codebase-analyzer", "architecture-mapper", "epic-generator", "acceptance-criteria", "verification"],
    "backlog": ["codebase-analyzer", "backlog-generator", "acceptance-criteria", "verification"],
    "analyze": ["codebase-analyzer", "architecture-mapper"],
}

# Token limits
DEFAULT_MAX_TOKENS = 4096
CONTEXT_RESERVED_TOKENS = 1000  # Reserved for system prompt

# =============================================================================
# Neo4j Query Constants
# =============================================================================

# Node labels in the graph
NODE_LABELS = {
    "CLASS": "Class",
    "METHOD": "Method",
    "INTERFACE": "Interface",
    "COMPONENT": "Component",
    "MODULE": "Module",
    "FRONTEND": "Frontend",
    "BACKEND": "Backend",
}

# Relationship types in the graph
RELATIONSHIP_TYPES = {
    "EXTENDS": "EXTENDS",
    "IMPLEMENTS": "IMPLEMENTS",
    "DEPENDS_ON": "DEPENDS_ON",
    "CALLS": "CALLS",
    "CONTAINS": "CONTAINS",
    "INTEGRATES_WITH": "INTEGRATES_WITH",
}

# Default query depth for traversal
DEFAULT_GRAPH_DEPTH = 2
MAX_GRAPH_DEPTH = 5

# =============================================================================
# Verification Constants
# =============================================================================

# Confidence thresholds
CONFIDENCE_HIGH = 0.9  # Both graph and code verify
CONFIDENCE_CODE_ONLY = 0.85  # Only code verifies (ground truth)
CONFIDENCE_GRAPH_ONLY = 0.75  # Only graph verifies
CONFIDENCE_INDIRECT = 0.5  # Indirect evidence
CONFIDENCE_NONE = 0.0  # No evidence

# Verification verdicts
VERDICT_VERIFIED = "VERIFIED"
VERDICT_PARTIAL = "PARTIAL"
VERDICT_HALLUCINATION = "HALLUCINATION"

# =============================================================================
# Document Generation Constants
# =============================================================================

# BRD sections
BRD_SECTIONS = [
    "Executive Summary",
    "Business Context",
    "Functional Requirements",
    "Non-Functional Requirements",
    "Success Criteria",
]

# Epic structure
EPIC_STORY_POINT_RANGE = (5, 21)  # Fibonacci-ish range for epics

# Backlog item structure
BACKLOG_STORY_POINT_RANGE = (1, 8)  # Smaller range for backlog items

# =============================================================================
# Cache Keys
# =============================================================================

CACHE_PREFIX = "ai_accelerator"
SESSION_CACHE_KEY = f"{CACHE_PREFIX}:session:{{session_id}}"
CONTEXT_CACHE_KEY = f"{CACHE_PREFIX}:session:{{session_id}}:context"
MESSAGES_CACHE_KEY = f"{CACHE_PREFIX}:session:{{session_id}}:messages"
ANALYSIS_CACHE_KEY = f"{CACHE_PREFIX}:analysis:{{component}}:{{depth}}"

# =============================================================================
# File Patterns
# =============================================================================

# Common service/component suffixes for entity detection
CLASS_SUFFIXES = ("Service", "Controller", "Repository", "Manager", "Handler", "Factory", "Provider")
COMPONENT_SUFFIXES = ("Component", "Module", "Plugin")

# File patterns for different languages
FILE_PATTERNS = {
    "java": "**/*.java",
    "python": "**/*.py",
    "javascript": "**/*.js",
    "typescript": "**/*.ts",
    "go": "**/*.go",
}
