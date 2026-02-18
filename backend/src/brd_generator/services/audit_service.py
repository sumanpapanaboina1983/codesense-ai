"""Audit Service for tracking artifact history with linked sessions.

This service provides:
- Session management for linking BRD → EPICs → Backlogs
- Recording of artifact generation and refinement
- Section-level diff computation
- Audit history retrieval
- Configurable retention with cleanup
"""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import (
    GenerationSessionDB,
    ArtifactHistoryDB,
    AuditConfigDB,
    ArtifactType,
    ArtifactAction,
    FeedbackScope,
    SessionStatus,
)
from ..database.config import get_async_session
from ..models.brd import (
    ArtifactHistoryEntry,
    ArtifactHistoryResponse,
    SessionHistoryResponse,
    VersionDiffResponse,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


class AuditService:
    """Service for tracking artifact history with linked sessions.

    Provides comprehensive audit trail for BRD, EPIC, and Backlog
    artifacts with section-level diffs and configurable retention.
    """

    def __init__(self):
        """Initialize the audit service."""
        self._default_retention_days = 30

    # =========================================================================
    # Session Management
    # =========================================================================

    async def create_session(
        self,
        repository_id: str,
        brd_id: str,
        feature_description: str,
    ) -> str:
        """Create a new linked generation session.

        Args:
            repository_id: Repository this session is for
            brd_id: BRD document ID
            feature_description: Feature being documented

        Returns:
            Session ID
        """
        async for session in get_async_session():
            db_session = GenerationSessionDB(
                id=str(uuid4()),
                repository_id=repository_id,
                brd_id=brd_id,
                feature_description=feature_description,
                status=SessionStatus.ACTIVE,
                epic_ids=[],
                backlog_ids=[],
            )
            session.add(db_session)
            await session.commit()

            logger.info(f"Created generation session: {db_session.id} for BRD {brd_id}")
            return db_session.id

    async def get_session(self, session_id: str) -> Optional[GenerationSessionDB]:
        """Get a session by ID."""
        async for session in get_async_session():
            result = await session.execute(
                select(GenerationSessionDB).where(GenerationSessionDB.id == session_id)
            )
            return result.scalar_one_or_none()

    async def update_session(
        self,
        session_id: str,
        epic_ids: Optional[list[str]] = None,
        backlog_ids: Optional[list[str]] = None,
        status: Optional[SessionStatus] = None,
    ) -> Optional[GenerationSessionDB]:
        """Update a session with linked artifacts."""
        async for session in get_async_session():
            result = await session.execute(
                select(GenerationSessionDB).where(GenerationSessionDB.id == session_id)
            )
            db_session = result.scalar_one_or_none()

            if not db_session:
                return None

            if epic_ids is not None:
                db_session.epic_ids = epic_ids
            if backlog_ids is not None:
                db_session.backlog_ids = backlog_ids
            if status is not None:
                db_session.status = status
                if status == SessionStatus.COMPLETED:
                    db_session.completed_at = datetime.utcnow()

            await session.commit()
            await session.refresh(db_session)
            return db_session

    async def add_epic_to_session(self, session_id: str, epic_id: str) -> bool:
        """Add an EPIC ID to a session."""
        async for session in get_async_session():
            result = await session.execute(
                select(GenerationSessionDB).where(GenerationSessionDB.id == session_id)
            )
            db_session = result.scalar_one_or_none()

            if not db_session:
                return False

            if db_session.epic_ids is None:
                db_session.epic_ids = []
            if epic_id not in db_session.epic_ids:
                db_session.epic_ids = [*db_session.epic_ids, epic_id]
                await session.commit()

            return True

    async def add_backlog_to_session(self, session_id: str, backlog_id: str) -> bool:
        """Add a backlog ID to a session."""
        async for session in get_async_session():
            result = await session.execute(
                select(GenerationSessionDB).where(GenerationSessionDB.id == session_id)
            )
            db_session = result.scalar_one_or_none()

            if not db_session:
                return False

            if db_session.backlog_ids is None:
                db_session.backlog_ids = []
            if backlog_id not in db_session.backlog_ids:
                db_session.backlog_ids = [*db_session.backlog_ids, backlog_id]
                await session.commit()

            return True

    # =========================================================================
    # Recording Generation and Refinement
    # =========================================================================

    async def record_generation(
        self,
        artifact_type: str,
        artifact_id: str,
        content: dict,
        repository_id: str,
        session_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        mode: str = "draft",
        model: Optional[str] = None,
        confidence_score: Optional[float] = None,
        created_by: Optional[str] = None,
    ) -> str:
        """Record initial artifact generation with session link.

        Args:
            artifact_type: 'brd', 'epic', or 'backlog'
            artifact_id: Unique artifact identifier
            content: Full artifact content as dict
            repository_id: Repository ID
            session_id: Optional session ID for linking
            parent_id: Parent artifact ID (BRD for EPICs, EPIC for Backlogs)
            mode: 'draft' or 'verified'
            model: LLM model used
            confidence_score: Verification confidence
            created_by: User identifier

        Returns:
            History entry ID
        """
        retention_days = await self.get_retention_days()

        async for session in get_async_session():
            history_entry = ArtifactHistoryDB(
                id=str(uuid4()),
                session_id=session_id,
                artifact_type=ArtifactType(artifact_type),
                artifact_id=artifact_id,
                version=1,
                action=ArtifactAction.CREATED,
                content_snapshot=content,
                repository_id=repository_id,
                parent_artifact_id=parent_id,
                model_used=model,
                generation_mode=mode,
                confidence_score=confidence_score,
                created_by=created_by,
                expires_at=datetime.utcnow() + timedelta(days=retention_days),
            )
            session.add(history_entry)

            # Update session refinement count if session exists
            if session_id:
                result = await session.execute(
                    select(GenerationSessionDB).where(GenerationSessionDB.id == session_id)
                )
                db_session = result.scalar_one_or_none()
                if db_session:
                    # Link artifact to session
                    if artifact_type == "epic":
                        db_session.add_epic(artifact_id)
                    elif artifact_type == "backlog":
                        db_session.add_backlog(artifact_id)

            await session.commit()

            logger.info(f"Recorded generation: {artifact_type}:{artifact_id} v1")
            return history_entry.id

    async def record_refinement(
        self,
        artifact_type: str,
        artifact_id: str,
        previous_content: dict,
        new_content: dict,
        user_feedback: str,
        feedback_scope: str,  # 'global' or 'section'
        feedback_target: Optional[str] = None,
        session_id: Optional[str] = None,
        repository_id: Optional[str] = None,
        model: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> str:
        """Record refinement with section-level diffs.

        Args:
            artifact_type: 'brd', 'epic', or 'backlog'
            artifact_id: Unique artifact identifier
            previous_content: Content before refinement
            new_content: Content after refinement
            user_feedback: Feedback that triggered refinement
            feedback_scope: 'global' or 'section'
            feedback_target: Section name if section-level
            session_id: Optional session ID for linking
            repository_id: Repository ID
            model: LLM model used
            created_by: User identifier

        Returns:
            History entry ID
        """
        retention_days = await self.get_retention_days()

        # Get current version
        current_version = await self._get_latest_version(artifact_type, artifact_id)
        new_version = current_version + 1

        # Compute section diffs
        section_diffs = await self.compute_section_diff(
            previous_content,
            new_content,
        )

        # Extract sections that changed
        sections_changed = list(section_diffs.keys())

        # Generate changes summary
        changes_summary = self._generate_changes_summary(section_diffs, user_feedback)

        async for session in get_async_session():
            history_entry = ArtifactHistoryDB(
                id=str(uuid4()),
                session_id=session_id,
                artifact_type=ArtifactType(artifact_type),
                artifact_id=artifact_id,
                version=new_version,
                action=ArtifactAction.REFINED,
                content_snapshot=new_content,
                sections_changed=sections_changed,
                section_diffs=section_diffs,
                user_feedback=user_feedback,
                feedback_scope=FeedbackScope(feedback_scope),
                feedback_target=feedback_target,
                changes_summary=changes_summary,
                repository_id=repository_id,
                model_used=model,
                created_by=created_by,
                expires_at=datetime.utcnow() + timedelta(days=retention_days),
            )
            session.add(history_entry)

            # Update session refinement count if session exists
            if session_id:
                result = await session.execute(
                    select(GenerationSessionDB).where(GenerationSessionDB.id == session_id)
                )
                db_session = result.scalar_one_or_none()
                if db_session:
                    db_session.total_refinements += 1
                    if artifact_type == "brd":
                        db_session.brd_refinements += 1
                    elif artifact_type == "epic":
                        db_session.epic_refinements += 1
                    elif artifact_type == "backlog":
                        db_session.backlog_refinements += 1

            await session.commit()

            logger.info(
                f"Recorded refinement: {artifact_type}:{artifact_id} "
                f"v{current_version} -> v{new_version}"
            )
            return history_entry.id

    async def _get_latest_version(
        self,
        artifact_type: str,
        artifact_id: str,
    ) -> int:
        """Get the latest version number for an artifact."""
        async for session in get_async_session():
            result = await session.execute(
                select(func.max(ArtifactHistoryDB.version)).where(
                    and_(
                        ArtifactHistoryDB.artifact_type == ArtifactType(artifact_type),
                        ArtifactHistoryDB.artifact_id == artifact_id,
                    )
                )
            )
            max_version = result.scalar_one_or_none()
            return max_version or 0

    # =========================================================================
    # History Retrieval
    # =========================================================================

    async def get_artifact_history(
        self,
        artifact_type: str,
        artifact_id: str,
    ) -> ArtifactHistoryResponse:
        """Get complete history for an artifact with section diffs.

        Args:
            artifact_type: 'brd', 'epic', or 'backlog'
            artifact_id: Unique artifact identifier

        Returns:
            ArtifactHistoryResponse with all versions
        """
        async for session in get_async_session():
            result = await session.execute(
                select(ArtifactHistoryDB)
                .where(
                    and_(
                        ArtifactHistoryDB.artifact_type == ArtifactType(artifact_type),
                        ArtifactHistoryDB.artifact_id == artifact_id,
                    )
                )
                .order_by(ArtifactHistoryDB.version.asc())
            )
            entries = result.scalars().all()

            history = [
                ArtifactHistoryEntry(
                    id=str(entry.id),
                    artifact_type=entry.artifact_type.value,
                    artifact_id=entry.artifact_id,
                    version=entry.version,
                    action=entry.action.value,
                    user_feedback=entry.user_feedback,
                    feedback_scope=entry.feedback_scope.value if entry.feedback_scope else None,
                    feedback_target=entry.feedback_target,
                    changes_summary=entry.changes_summary,
                    sections_changed=entry.sections_changed or [],
                    model_used=entry.model_used,
                    generation_mode=entry.generation_mode,
                    confidence_score=entry.confidence_score,
                    created_at=entry.created_at,
                    created_by=entry.created_by,
                )
                for entry in entries
            ]

            current_version = max((e.version for e in history), default=0)

            return ArtifactHistoryResponse(
                success=True,
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                total_versions=len(history),
                current_version=current_version,
                history=history,
            )

    async def get_session_history(
        self,
        session_id: str,
    ) -> Optional[SessionHistoryResponse]:
        """Get full pipeline history: BRD → EPICs → Backlogs.

        Args:
            session_id: Generation session ID

        Returns:
            SessionHistoryResponse with combined history
        """
        async for session in get_async_session():
            # Get session
            result = await session.execute(
                select(GenerationSessionDB).where(GenerationSessionDB.id == session_id)
            )
            db_session = result.scalar_one_or_none()

            if not db_session:
                return None

            # Get all history entries for this session
            result = await session.execute(
                select(ArtifactHistoryDB)
                .where(ArtifactHistoryDB.session_id == session_id)
                .order_by(ArtifactHistoryDB.created_at.asc())
            )
            entries = result.scalars().all()

            history = [
                ArtifactHistoryEntry(
                    id=str(entry.id),
                    artifact_type=entry.artifact_type.value,
                    artifact_id=entry.artifact_id,
                    version=entry.version,
                    action=entry.action.value,
                    user_feedback=entry.user_feedback,
                    feedback_scope=entry.feedback_scope.value if entry.feedback_scope else None,
                    feedback_target=entry.feedback_target,
                    changes_summary=entry.changes_summary,
                    sections_changed=entry.sections_changed or [],
                    model_used=entry.model_used,
                    generation_mode=entry.generation_mode,
                    confidence_score=entry.confidence_score,
                    created_at=entry.created_at,
                    created_by=entry.created_by,
                )
                for entry in entries
            ]

            return SessionHistoryResponse(
                success=True,
                session_id=session_id,
                repository_id=str(db_session.repository_id),
                feature_description=db_session.feature_description,
                status=db_session.status.value,
                brd_id=db_session.brd_id,
                epic_ids=db_session.epic_ids or [],
                backlog_ids=db_session.backlog_ids or [],
                history=history,
                total_refinements=db_session.total_refinements,
                brd_refinements=db_session.brd_refinements,
                epic_refinements=db_session.epic_refinements,
                backlog_refinements=db_session.backlog_refinements,
                created_at=db_session.created_at,
                updated_at=db_session.updated_at,
                completed_at=db_session.completed_at,
            )

    async def get_version_diff(
        self,
        artifact_type: str,
        artifact_id: str,
        version1: int,
        version2: int,
    ) -> Optional[VersionDiffResponse]:
        """Get diff between two versions of an artifact.

        Args:
            artifact_type: 'brd', 'epic', or 'backlog'
            artifact_id: Unique artifact identifier
            version1: First version (older)
            version2: Second version (newer)

        Returns:
            VersionDiffResponse with section-level diffs
        """
        async for session in get_async_session():
            # Get both versions
            result = await session.execute(
                select(ArtifactHistoryDB).where(
                    and_(
                        ArtifactHistoryDB.artifact_type == ArtifactType(artifact_type),
                        ArtifactHistoryDB.artifact_id == artifact_id,
                        ArtifactHistoryDB.version.in_([version1, version2]),
                    )
                )
            )
            versions = {entry.version: entry for entry in result.scalars().all()}

            if version1 not in versions or version2 not in versions:
                return None

            entry1 = versions[version1]
            entry2 = versions[version2]

            # Compute diff if not already stored
            if entry2.section_diffs:
                section_diffs = entry2.section_diffs
            else:
                section_diffs = await self.compute_section_diff(
                    entry1.content_snapshot or {},
                    entry2.content_snapshot or {},
                )

            # Determine sections added, removed, modified
            sections1 = set(self._extract_section_names(entry1.content_snapshot))
            sections2 = set(self._extract_section_names(entry2.content_snapshot))

            sections_added = list(sections2 - sections1)
            sections_removed = list(sections1 - sections2)
            sections_modified = list(section_diffs.keys())

            # Collect feedback that was applied between versions
            feedback_applied = []
            result = await session.execute(
                select(ArtifactHistoryDB.user_feedback).where(
                    and_(
                        ArtifactHistoryDB.artifact_type == ArtifactType(artifact_type),
                        ArtifactHistoryDB.artifact_id == artifact_id,
                        ArtifactHistoryDB.version > version1,
                        ArtifactHistoryDB.version <= version2,
                        ArtifactHistoryDB.user_feedback.isnot(None),
                    )
                )
            )
            for row in result:
                if row[0]:
                    feedback_applied.append(row[0])

            return VersionDiffResponse(
                success=True,
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                version1=version1,
                version2=version2,
                section_diffs=section_diffs,
                sections_added=sections_added,
                sections_removed=sections_removed,
                sections_modified=sections_modified,
                feedback_applied=feedback_applied,
            )

    # =========================================================================
    # Diff Computation
    # =========================================================================

    async def compute_section_diff(
        self,
        old_content: dict,
        new_content: dict,
    ) -> dict[str, dict[str, str]]:
        """Compute section-level before/after diff.

        Args:
            old_content: Previous content dict
            new_content: New content dict

        Returns:
            Dict of {section_name: {before: str, after: str}}
        """
        section_diffs = {}

        # Extract sections from both
        old_sections = self._extract_sections(old_content)
        new_sections = self._extract_sections(new_content)

        # Compare each section
        all_sections = set(old_sections.keys()) | set(new_sections.keys())

        for section_name in all_sections:
            old_text = old_sections.get(section_name, "")
            new_text = new_sections.get(section_name, "")

            if old_text != new_text:
                section_diffs[section_name] = {
                    "before": old_text,
                    "after": new_text,
                }

        return section_diffs

    def _extract_sections(self, content: dict) -> dict[str, str]:
        """Extract sections from content dict.

        Handles various content structures:
        - {"sections": [...]}
        - {"markdown": "..."}
        - Direct section dict
        """
        sections = {}

        if not content:
            return sections

        # Handle sections list
        if "sections" in content and isinstance(content["sections"], list):
            for section in content["sections"]:
                if isinstance(section, dict):
                    name = section.get("name", section.get("title", "Unknown"))
                    text = section.get("content", section.get("text", ""))
                    sections[name] = text

        # Handle markdown content - parse sections from headers
        elif "markdown" in content:
            markdown = content["markdown"]
            sections = self._parse_markdown_sections(markdown)

        # Handle direct dict with section names as keys
        else:
            for key, value in content.items():
                if isinstance(value, str) and key not in ["id", "title", "version"]:
                    sections[key] = value
                elif isinstance(value, dict) and "content" in value:
                    sections[key] = value["content"]

        return sections

    def _parse_markdown_sections(self, markdown: str) -> dict[str, str]:
        """Parse sections from markdown headers."""
        sections = {}
        current_section = None
        current_content = []

        for line in markdown.split("\n"):
            # Match ## or ### headers
            header_match = re.match(r"^(#{1,3})\s+(?:\d+\.?\s*)?(.+)$", line)
            if header_match:
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()

                current_section = header_match.group(2).strip()
                current_content = []
            elif current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    def _extract_section_names(self, content: Optional[dict]) -> list[str]:
        """Extract section names from content."""
        if not content:
            return []
        return list(self._extract_sections(content).keys())

    def _generate_changes_summary(
        self,
        section_diffs: dict[str, dict[str, str]],
        user_feedback: str,
    ) -> str:
        """Generate a human-readable summary of changes."""
        if not section_diffs:
            return "No changes detected"

        sections_modified = list(section_diffs.keys())
        summary_parts = []

        if len(sections_modified) == 1:
            summary_parts.append(f"Modified '{sections_modified[0]}' section")
        else:
            summary_parts.append(f"Modified {len(sections_modified)} sections: {', '.join(sections_modified)}")

        if user_feedback:
            # Truncate long feedback
            feedback_preview = user_feedback[:100] + "..." if len(user_feedback) > 100 else user_feedback
            summary_parts.append(f"Based on feedback: \"{feedback_preview}\"")

        return ". ".join(summary_parts)

    # =========================================================================
    # Retention Management
    # =========================================================================

    async def get_retention_days(self) -> int:
        """Get configured retention period (default: 30 days)."""
        async for session in get_async_session():
            result = await session.execute(
                select(AuditConfigDB).where(AuditConfigDB.config_key == "retention_days")
            )
            config = result.scalar_one_or_none()

            if config:
                try:
                    return int(config.config_value)
                except ValueError:
                    pass

            return self._default_retention_days

    async def set_retention_days(self, days: int) -> None:
        """Update retention period configuration.

        Args:
            days: Number of days to retain history
        """
        if days < 1:
            raise ValueError("Retention days must be at least 1")

        async for session in get_async_session():
            result = await session.execute(
                select(AuditConfigDB).where(AuditConfigDB.config_key == "retention_days")
            )
            config = result.scalar_one_or_none()

            if config:
                config.config_value = str(days)
            else:
                config = AuditConfigDB(
                    config_key="retention_days",
                    config_value=str(days),
                    description="Number of days to retain audit history before cleanup",
                )
                session.add(config)

            await session.commit()
            logger.info(f"Updated retention period to {days} days")

    async def cleanup_expired_history(self) -> int:
        """Delete history records past retention period.

        Returns:
            Count of records deleted
        """
        async for session in get_async_session():
            # Delete expired history entries
            result = await session.execute(
                delete(ArtifactHistoryDB).where(
                    ArtifactHistoryDB.expires_at < datetime.utcnow()
                )
            )
            deleted_count = result.rowcount

            # Delete orphaned sessions (completed and all history expired)
            # This is a more complex query - for now just log
            await session.commit()

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired audit records")

            return deleted_count

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def get_artifact_at_version(
        self,
        artifact_type: str,
        artifact_id: str,
        version: int,
    ) -> Optional[dict]:
        """Get artifact content at a specific version.

        Args:
            artifact_type: 'brd', 'epic', or 'backlog'
            artifact_id: Unique artifact identifier
            version: Version number

        Returns:
            Content snapshot dict or None
        """
        async for session in get_async_session():
            result = await session.execute(
                select(ArtifactHistoryDB).where(
                    and_(
                        ArtifactHistoryDB.artifact_type == ArtifactType(artifact_type),
                        ArtifactHistoryDB.artifact_id == artifact_id,
                        ArtifactHistoryDB.version == version,
                    )
                )
            )
            entry = result.scalar_one_or_none()
            return entry.content_snapshot if entry else None
