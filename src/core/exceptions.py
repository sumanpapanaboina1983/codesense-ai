"""
Custom exception hierarchy for the AI Accelerator system.
Provides structured error handling with proper HTTP status codes.
"""

from typing import Any, Optional


class AIAcceleratorError(Exception):
    """Base exception for all AI Accelerator errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        details: Optional[dict[str, Any]] = None,
        status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


# =============================================================================
# Configuration Errors (400-499 range for client, 500 for server config)
# =============================================================================


class ConfigurationError(AIAcceleratorError):
    """Error in application configuration."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            details=details,
            status_code=500,
        )


# =============================================================================
# Validation Errors (400)
# =============================================================================


class ValidationError(AIAcceleratorError):
    """Request validation failed."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details=details,
            status_code=400,
        )


class InvalidRequestError(ValidationError):
    """Invalid request parameters."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        details = {"field": field} if field else {}
        super().__init__(message=message, details=details)
        self.code = "INVALID_REQUEST"


# =============================================================================
# Authentication/Authorization Errors (401, 403)
# =============================================================================


class AuthenticationError(AIAcceleratorError):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(
            message=message,
            code="AUTHENTICATION_REQUIRED",
            status_code=401,
        )


class AuthorizationError(AIAcceleratorError):
    """Authorization failed - insufficient permissions."""

    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(
            message=message,
            code="AUTHORIZATION_FAILED",
            status_code=403,
        )


# =============================================================================
# Not Found Errors (404)
# =============================================================================


class NotFoundError(AIAcceleratorError):
    """Requested resource not found."""

    def __init__(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        msg = message or f"{resource_type} not found"
        if resource_id:
            msg = f"{resource_type} with ID '{resource_id}' not found"

        super().__init__(
            message=msg,
            code="NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": resource_id},
            status_code=404,
        )


class SessionNotFoundError(NotFoundError):
    """Session not found."""

    def __init__(self, session_id: str) -> None:
        super().__init__(resource_type="Session", resource_id=session_id)
        self.code = "SESSION_NOT_FOUND"


class DocumentNotFoundError(NotFoundError):
    """Document not found."""

    def __init__(self, document_id: str) -> None:
        super().__init__(resource_type="Document", resource_id=document_id)
        self.code = "DOCUMENT_NOT_FOUND"


class SkillNotFoundError(NotFoundError):
    """Skill definition not found."""

    def __init__(self, skill_name: str) -> None:
        super().__init__(resource_type="Skill", resource_id=skill_name)
        self.code = "SKILL_NOT_FOUND"


# =============================================================================
# External Service Errors (502, 503)
# =============================================================================


class ExternalServiceError(AIAcceleratorError):
    """Error communicating with external service."""

    def __init__(
        self,
        service_name: str,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=f"{service_name} error: {message}",
            code="EXTERNAL_SERVICE_ERROR",
            details={"service": service_name, **(details or {})},
            status_code=502,
        )


class Neo4jError(ExternalServiceError):
    """Error communicating with Neo4j."""

    def __init__(self, message: str, query: Optional[str] = None) -> None:
        details = {"query": query} if query else {}
        super().__init__(service_name="Neo4j", message=message, details=details)
        self.code = "NEO4J_ERROR"


class CopilotError(ExternalServiceError):
    """Error communicating with GitHub Copilot."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(service_name="GitHub Copilot", message=message, details=details)
        self.code = "COPILOT_ERROR"


class MCPError(ExternalServiceError):
    """Error communicating with MCP server."""

    def __init__(
        self,
        mcp_type: str,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(service_name=f"MCP ({mcp_type})", message=message, details=details)
        self.code = "MCP_ERROR"


class RedisError(ExternalServiceError):
    """Error communicating with Redis."""

    def __init__(self, message: str) -> None:
        super().__init__(service_name="Redis", message=message)
        self.code = "REDIS_ERROR"


class DatabaseError(ExternalServiceError):
    """Error communicating with database."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(service_name="Database", message=message, details=details)
        self.code = "DATABASE_ERROR"


# =============================================================================
# Business Logic Errors (422)
# =============================================================================


class BusinessLogicError(AIAcceleratorError):
    """Business logic validation failed."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="BUSINESS_LOGIC_ERROR",
            details=details,
            status_code=422,
        )


class VerificationError(BusinessLogicError):
    """Verification of claims failed."""

    def __init__(
        self,
        message: str,
        unverified_claims: Optional[list[str]] = None,
        confidence: Optional[float] = None,
    ) -> None:
        details = {}
        if unverified_claims:
            details["unverified_claims"] = unverified_claims
        if confidence is not None:
            details["confidence"] = confidence

        super().__init__(message=message, details=details)
        self.code = "VERIFICATION_FAILED"


class HallucinationDetectedError(VerificationError):
    """Hallucination detected in generated content."""

    def __init__(self, claims: list[str]) -> None:
        super().__init__(
            message="Generated content contains unverified claims",
            unverified_claims=claims,
        )
        self.code = "HALLUCINATION_DETECTED"


class WorkflowError(BusinessLogicError):
    """Error during workflow execution."""

    def __init__(
        self,
        workflow_name: str,
        step: Optional[str] = None,
        message: str = "Workflow execution failed",
    ) -> None:
        details = {"workflow": workflow_name}
        if step:
            details["step"] = step

        super().__init__(message=message, details=details)
        self.code = "WORKFLOW_ERROR"


# =============================================================================
# Rate Limiting Errors (429)
# =============================================================================


class RateLimitError(AIAcceleratorError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: Optional[int] = None) -> None:
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after

        super().__init__(
            message="Rate limit exceeded. Please try again later.",
            code="RATE_LIMIT_EXCEEDED",
            details=details,
            status_code=429,
        )


# =============================================================================
# Context Management Errors
# =============================================================================


class ContextOverflowError(AIAcceleratorError):
    """Context window overflow."""

    def __init__(self, current_tokens: int, max_tokens: int) -> None:
        super().__init__(
            message="Context window overflow - conversation too long",
            code="CONTEXT_OVERFLOW",
            details={"current_tokens": current_tokens, "max_tokens": max_tokens},
            status_code=422,
        )


# =============================================================================
# Timeout Errors (504)
# =============================================================================


class TimeoutError(AIAcceleratorError):
    """Operation timed out."""

    def __init__(self, operation: str, timeout_seconds: int) -> None:
        super().__init__(
            message=f"Operation '{operation}' timed out after {timeout_seconds} seconds",
            code="TIMEOUT",
            details={"operation": operation, "timeout_seconds": timeout_seconds},
            status_code=504,
        )
