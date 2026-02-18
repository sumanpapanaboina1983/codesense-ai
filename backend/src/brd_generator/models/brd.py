"""BRD Refinement Data Models.

This module defines data models for:
- BRD sections with refinement tracking
- Refined BRD with version history
- Refinement requests (section and global)
- Audit history responses
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class BRDStatus(str, Enum):
    """Status of a BRD in the workflow."""
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    EXPORTED = "exported"


class FeedbackType(str, Enum):
    """Type of feedback provided."""
    SECTION = "section"
    GLOBAL = "global"


# =============================================================================
# BRD Section Models
# =============================================================================

class BRDSection(BaseModel):
    """Individual BRD section with refinement tracking."""

    name: str = Field(..., description="Section name/title")
    content: str = Field(..., description="Section content in markdown")
    section_order: int = Field(0, description="Order of this section in BRD")

    # Refinement tracking
    refinement_count: int = Field(0, ge=0, description="Number of refinements")
    last_feedback: Optional[str] = Field(None, description="Last feedback applied")
    last_refined_at: Optional[datetime] = Field(None, description="When last refined")


class RefinementEntry(BaseModel):
    """Single refinement audit entry."""

    version: int = Field(..., ge=1, description="Version number after refinement")
    timestamp: datetime = Field(default_factory=datetime.now)
    feedback_type: FeedbackType = Field(..., description="section or global")
    feedback_target: Optional[str] = Field(
        None,
        description="Section name if section-level feedback"
    )
    user_feedback: str = Field(..., min_length=1, description="User's feedback text")
    changes_summary: str = Field(
        ...,
        description="LLM-generated summary of what changed"
    )
    sections_affected: list[str] = Field(
        default_factory=list,
        description="List of section names that were modified"
    )

    # Diff information
    section_diffs: Optional[dict[str, dict[str, str]]] = Field(
        None,
        description="Dict of {section_name: {before: str, after: str}}"
    )


# =============================================================================
# Refined BRD Model
# =============================================================================

class RefinedBRD(BaseModel):
    """BRD with refinement metadata and history tracking."""

    # Core identification
    id: str = Field(..., description="Unique BRD identifier (e.g., 'BRD-1234')")
    title: str = Field(..., min_length=5, max_length=500)
    version: str = Field("1.0", description="BRD version string")
    repository_id: str = Field(..., description="Source repository ID")

    # Structured content
    sections: list[BRDSection] = Field(
        default_factory=list,
        description="List of BRD sections"
    )

    # Full markdown (may differ from structured sections)
    markdown: str = Field(..., description="Full BRD content in markdown")

    # Generation metadata
    mode: str = Field("draft", description="'draft' or 'verified'")
    confidence_score: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="Verification confidence (verified mode only)"
    )
    verification_report: Optional[dict] = Field(
        None,
        description="Full verification report if available"
    )

    # Refinement tracking
    refinement_count: int = Field(0, ge=0, description="Total refinements applied")
    last_feedback: Optional[str] = Field(None, description="Most recent feedback")
    refinement_history: list[RefinementEntry] = Field(
        default_factory=list,
        description="History of all refinements"
    )

    # Session tracking for linked artifacts
    session_id: Optional[str] = Field(None, description="Generation session ID")

    # Status
    status: BRDStatus = Field(BRDStatus.DRAFT)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(None)

    def get_section(self, section_name: str) -> Optional[BRDSection]:
        """Get a section by name."""
        for section in self.sections:
            if section.name.lower() == section_name.lower():
                return section
        return None

    def update_section(self, section_name: str, new_content: str) -> bool:
        """Update a section's content. Returns True if found and updated."""
        for i, section in enumerate(self.sections):
            if section.name.lower() == section_name.lower():
                self.sections[i].content = new_content
                self.sections[i].refinement_count += 1
                self.sections[i].last_refined_at = datetime.now()
                return True
        return False


# =============================================================================
# Request Models
# =============================================================================

class RefineBRDSectionRequest(BaseModel):
    """Request to refine a specific BRD section."""

    brd_id: str = Field(..., description="ID of the BRD to refine")
    section_name: str = Field(..., description="Name of the section to refine")
    current_content: str = Field(..., description="Current section content")
    user_feedback: str = Field(
        ...,
        min_length=5,
        description="User feedback for refinement"
    )
    full_brd_context: str = Field(
        ...,
        description="Full BRD markdown for context"
    )
    repository_id: str = Field(..., description="Repository ID for context")

    # Optional session tracking
    session_id: Optional[str] = Field(None, description="Session ID if tracking")

    # Optional: Project context
    project_context: Optional[dict] = Field(None, description="Project context dict")


class RefineEntireBRDRequest(BaseModel):
    """Request to apply global feedback to entire BRD."""

    brd_id: str = Field(..., description="ID of the BRD to refine")
    current_brd: RefinedBRD = Field(..., description="Current BRD state")
    global_feedback: str = Field(
        ...,
        min_length=5,
        description="Global feedback to apply"
    )
    repository_id: str = Field(..., description="Repository ID for context")

    # Optional session tracking
    session_id: Optional[str] = Field(None, description="Session ID if tracking")

    # Optional: Limit to specific sections
    target_sections: Optional[list[str]] = Field(
        None,
        description="Specific sections to target (None = all)"
    )

    # Optional: Project context
    project_context: Optional[dict] = Field(None, description="Project context dict")


# =============================================================================
# Response Models
# =============================================================================

class RefineBRDSectionResponse(BaseModel):
    """Response from section refinement."""

    success: bool = True
    brd_id: str
    section_name: str
    refined_section: BRDSection
    changes_summary: str

    # Diff info
    before_content: str
    after_content: str

    # Updated BRD (if requested)
    updated_brd: Optional[RefinedBRD] = None


class RefineEntireBRDResponse(BaseModel):
    """Response from global BRD refinement."""

    success: bool = True
    brd_id: str
    refined_brd: RefinedBRD
    changes_summary: str
    sections_affected: list[str]

    # Diff info per section
    section_diffs: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Dict of {section_name: {before: str, after: str}}"
    )


# =============================================================================
# Audit History Response Models
# =============================================================================

class ArtifactHistoryEntry(BaseModel):
    """Single entry in artifact history."""

    id: str
    artifact_type: str  # 'brd', 'epic', 'backlog'
    artifact_id: str
    version: int
    action: str  # 'created', 'refined'

    # Feedback info
    user_feedback: Optional[str] = None
    feedback_scope: Optional[str] = None
    feedback_target: Optional[str] = None
    changes_summary: Optional[str] = None

    # Sections changed
    sections_changed: list[str] = Field(default_factory=list)

    # Metadata
    model_used: Optional[str] = None
    generation_mode: Optional[str] = None
    confidence_score: Optional[float] = None

    # Timestamps
    created_at: datetime
    created_by: Optional[str] = None


class ArtifactHistoryResponse(BaseModel):
    """Response containing artifact history."""

    success: bool = True
    artifact_type: str
    artifact_id: str
    total_versions: int
    current_version: int
    history: list[ArtifactHistoryEntry]


class SessionHistoryResponse(BaseModel):
    """Response containing full session history (BRD → EPICs → Backlogs)."""

    success: bool = True
    session_id: str
    repository_id: str
    feature_description: str
    status: str

    # Linked artifact IDs
    brd_id: str
    epic_ids: list[str] = Field(default_factory=list)
    backlog_ids: list[str] = Field(default_factory=list)

    # Combined history across all artifacts
    history: list[ArtifactHistoryEntry] = Field(default_factory=list)

    # Summary stats
    total_refinements: int
    brd_refinements: int
    epic_refinements: int
    backlog_refinements: int

    # Timestamps
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class VersionDiffResponse(BaseModel):
    """Response containing diff between two versions."""

    success: bool = True
    artifact_type: str
    artifact_id: str
    version1: int
    version2: int

    # Section-level diffs
    section_diffs: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Dict of {section_name: {before: str, after: str}}"
    )

    # Full content diffs
    content_before: Optional[str] = None
    content_after: Optional[str] = None

    # Changes between versions
    sections_added: list[str] = Field(default_factory=list)
    sections_removed: list[str] = Field(default_factory=list)
    sections_modified: list[str] = Field(default_factory=list)

    # Feedback that triggered changes
    feedback_applied: list[str] = Field(default_factory=list)
