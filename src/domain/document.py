"""
Document domain model for BRDs, Epics, and Backlogs.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.core.constants import DocumentType, VerificationStatus


class VerificationResult(BaseModel):
    """Verification results for a document."""

    status: VerificationStatus = Field(default=VerificationStatus.UNVERIFIED)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    verified_claims: int = Field(default=0)
    total_claims: int = Field(default=0)

    evidence: list[dict[str, Any]] = Field(default_factory=list)
    hallucination_flags: list[str] = Field(default_factory=list)

    verified_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True

    @property
    def verification_rate(self) -> float:
        """Calculate verification rate."""
        if self.total_claims == 0:
            return 0.0
        return self.verified_claims / self.total_claims


class Document(BaseModel):
    """Generated document domain model."""

    document_id: str = Field(..., description="Unique document identifier")
    session_id: str = Field(..., description="Associated session ID")
    document_type: DocumentType = Field(..., description="Type of document")

    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Document content (Markdown)")

    verification: VerificationResult = Field(default_factory=VerificationResult)

    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Parent references
    parent_document_id: Optional[str] = Field(
        default=None, description="Parent document ID (for epics from BRD)"
    )

    class Config:
        use_enum_values = True

    @property
    def is_verified(self) -> bool:
        """Check if document is fully verified."""
        return self.verification.status == VerificationStatus.VERIFIED

    @property
    def has_hallucinations(self) -> bool:
        """Check if document has hallucination flags."""
        return len(self.verification.hallucination_flags) > 0

    def update_content(self, content: str) -> None:
        """Update document content."""
        self.content = content
        self.updated_at = datetime.utcnow()

    def set_verification(self, result: VerificationResult) -> None:
        """Set verification result."""
        self.verification = result
        self.updated_at = datetime.utcnow()


class AcceptanceCriterion(BaseModel):
    """Single acceptance criterion in Given-When-Then format."""

    id: str = Field(..., description="Criterion ID")
    given: str = Field(..., description="Given condition")
    when: str = Field(..., description="When action")
    then: str = Field(..., description="Then outcome")
    and_clauses: list[str] = Field(default_factory=list, description="Additional AND clauses")

    test_method: str = Field(default="unit", description="Test method (unit/integration/e2e)")
    verification_code: Optional[str] = Field(
        default=None, description="Location in codebase"
    )

    def to_string(self) -> str:
        """Convert to string format."""
        result = f"GIVEN {self.given}\nWHEN {self.when}\nTHEN {self.then}"
        for clause in self.and_clauses:
            result += f"\nAND {clause}"
        return result


class TechnicalNotes(BaseModel):
    """Technical notes for epics and backlogs."""

    components: list[str] = Field(default_factory=list)
    integration_points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class Epic(BaseModel):
    """Epic domain model."""

    epic_id: str = Field(..., description="Unique epic identifier")
    document_id: str = Field(..., description="Parent BRD document ID")

    title: str = Field(..., description="Epic title")
    user_story: str = Field(..., description="User story format")
    description: str = Field(default="", description="Detailed description")

    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    technical_notes: TechnicalNotes = Field(default_factory=TechnicalNotes)

    story_points: int = Field(default=0, ge=0)
    dependencies: list[str] = Field(default_factory=list, description="Dependent epic IDs")

    verification: VerificationResult = Field(default_factory=VerificationResult)
    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class BacklogItem(BaseModel):
    """Backlog item (user story) domain model."""

    item_id: str = Field(..., description="Unique item identifier")
    epic_id: str = Field(..., description="Parent epic ID")

    title: str = Field(..., description="Item title")
    description: str = Field(default="", description="Detailed description")

    acceptance_criteria: list[str] = Field(
        default_factory=list, description="Simplified acceptance criteria"
    )

    technical_details: dict[str, Any] = Field(
        default_factory=lambda: {
            "files_to_modify": [],
            "classes_affected": [],
            "methods_to_implement": [],
            "dependencies": [],
        }
    )

    story_points: int = Field(default=0, ge=0, le=13)
    definition_of_done: list[str] = Field(default_factory=list)

    verification: VerificationResult = Field(default_factory=VerificationResult)
    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True
