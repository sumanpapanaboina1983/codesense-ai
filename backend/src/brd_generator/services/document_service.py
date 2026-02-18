"""Document Service for BRD, EPIC, and Backlog CRUD operations.

This service provides:
- BRD storage and retrieval with relationships
- EPIC management with parent BRD linking
- Backlog item management with parent EPIC linking
- Pagination, filtering, and sorting
- Export functionality
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from ..database.models import (
    BRDDB,
    EpicDB,
    BacklogDB,
    RepositoryDB,
    DocumentStatus,
    EpicPriority,
    BacklogItemType,
)
from ..database.config import get_async_session
from ..utils.logger import get_logger

logger = get_logger(__name__)


class DocumentService:
    """Service for managing BRD, EPIC, and Backlog documents.

    Provides CRUD operations with support for hierarchical relationships:
    BRD (1) -> EPICs (many) -> Backlogs (many per EPIC)
    """

    def __init__(self):
        """Initialize the document service."""
        self._brd_counter = 0

    # =========================================================================
    # BRD Number Generation
    # =========================================================================

    async def _generate_brd_number(self) -> str:
        """Generate the next BRD number (BRD-0001 format)."""
        async with get_async_session() as session:
            # Get the highest existing BRD number
            result = await session.execute(
                select(BRDDB.brd_number)
                .order_by(desc(BRDDB.created_at))
                .limit(1)
            )
            last_number = result.scalar_one_or_none()

            if last_number:
                # Extract number from BRD-XXXX format
                try:
                    num = int(last_number.split("-")[1])
                    return f"BRD-{num + 1:04d}"
                except (IndexError, ValueError):
                    pass

            return "BRD-0001"

    async def _generate_epic_number(self, brd_id: str) -> str:
        """Generate the next EPIC number for a BRD (EPIC-001 format)."""
        async with get_async_session() as session:
            result = await session.execute(
                select(func.count(EpicDB.id))
                .where(EpicDB.brd_id == brd_id)
            )
            count = result.scalar_one() or 0
            return f"EPIC-{count + 1:03d}"

    async def _generate_backlog_number(self, epic_id: str, item_type: str) -> str:
        """Generate the next backlog number (STORY-001, TASK-001, etc.)."""
        prefix_map = {
            "user_story": "STORY",
            "task": "TASK",
            "spike": "SPIKE",
            "bug": "BUG",
        }
        prefix = prefix_map.get(item_type, "ITEM")

        async with get_async_session() as session:
            result = await session.execute(
                select(func.count(BacklogDB.id))
                .where(BacklogDB.epic_id == epic_id)
            )
            count = result.scalar_one() or 0
            return f"{prefix}-{count + 1:03d}"

    # =========================================================================
    # BRD CRUD Operations
    # =========================================================================

    async def create_brd(
        self,
        repository_id: str,
        title: str,
        feature_description: str,
        markdown_content: str,
        sections: Optional[list[dict]] = None,
        mode: str = "draft",
        confidence_score: Optional[float] = None,
        verification_report: Optional[dict] = None,
    ) -> BRDDB:
        """Create a new BRD document.

        Args:
            repository_id: Repository this BRD belongs to
            title: BRD title
            feature_description: Original feature description
            markdown_content: Full markdown content
            sections: Parsed sections list
            mode: Generation mode (draft/verified)
            confidence_score: Verification confidence
            verification_report: Full verification report

        Returns:
            Created BRDDB instance
        """
        brd_number = await self._generate_brd_number()

        async with get_async_session() as session:
            brd = BRDDB(
                id=str(uuid4()),
                brd_number=brd_number,
                title=title,
                feature_description=feature_description,
                markdown_content=markdown_content,
                sections=sections,
                repository_id=repository_id,
                mode=mode,
                confidence_score=confidence_score,
                verification_report=verification_report,
                status=DocumentStatus.DRAFT,
                version=1,
            )
            session.add(brd)
            await session.commit()
            await session.refresh(brd)

            logger.info(f"Created BRD: {brd_number} - {title}")
            return brd

    async def list_brds(
        self,
        repository_id: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BRDDB], int]:
        """List BRDs with optional filters.

        Args:
            repository_id: Filter by repository
            status: Filter by status
            search: Search in title/description
            limit: Max results
            offset: Skip results

        Returns:
            Tuple of (BRD list, total count)
        """
        async with get_async_session() as session:
            # Build base query
            query = select(BRDDB).options(
                selectinload(BRDDB.repository),
                selectinload(BRDDB.epics).selectinload(EpicDB.backlogs),
            )
            count_query = select(func.count(BRDDB.id))

            # Apply filters
            conditions = []
            if repository_id:
                conditions.append(BRDDB.repository_id == repository_id)
            if status:
                conditions.append(BRDDB.status == DocumentStatus(status))
            if search:
                search_pattern = f"%{search}%"
                conditions.append(
                    or_(
                        BRDDB.title.ilike(search_pattern),
                        BRDDB.feature_description.ilike(search_pattern),
                        BRDDB.brd_number.ilike(search_pattern),
                    )
                )

            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))

            # Get total count
            result = await session.execute(count_query)
            total = result.scalar_one()

            # Apply ordering and pagination
            query = query.order_by(desc(BRDDB.created_at)).offset(offset).limit(limit)

            result = await session.execute(query)
            brds = list(result.scalars().unique().all())

            return brds, total

    async def get_brd(self, brd_id: str) -> Optional[BRDDB]:
        """Get a BRD by ID with all relationships loaded."""
        async with get_async_session() as session:
            result = await session.execute(
                select(BRDDB)
                .options(
                    selectinload(BRDDB.repository),
                    selectinload(BRDDB.epics).selectinload(EpicDB.backlogs),
                )
                .where(BRDDB.id == brd_id)
            )
            return result.scalar_one_or_none()

    async def get_brd_by_number(self, brd_number: str) -> Optional[BRDDB]:
        """Get a BRD by its number (e.g., BRD-0001)."""
        async with get_async_session() as session:
            result = await session.execute(
                select(BRDDB)
                .options(
                    selectinload(BRDDB.repository),
                    selectinload(BRDDB.epics).selectinload(EpicDB.backlogs),
                )
                .where(BRDDB.brd_number == brd_number)
            )
            return result.scalar_one_or_none()

    async def update_brd(
        self,
        brd_id: str,
        title: Optional[str] = None,
        markdown_content: Optional[str] = None,
        sections: Optional[list[dict]] = None,
        status: Optional[str] = None,
        confidence_score: Optional[float] = None,
        verification_report: Optional[dict] = None,
    ) -> Optional[BRDDB]:
        """Update a BRD document.

        Args:
            brd_id: BRD ID to update
            title: New title
            markdown_content: Updated markdown
            sections: Updated sections
            status: New status
            confidence_score: Updated confidence
            verification_report: Updated verification report

        Returns:
            Updated BRDDB or None if not found
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(BRDDB).where(BRDDB.id == brd_id)
            )
            brd = result.scalar_one_or_none()

            if not brd:
                return None

            if title is not None:
                brd.title = title
            if markdown_content is not None:
                brd.markdown_content = markdown_content
                brd.version += 1
                brd.refinement_count += 1
            if sections is not None:
                brd.sections = sections
            if status is not None:
                brd.status = DocumentStatus(status)
            if confidence_score is not None:
                brd.confidence_score = confidence_score
            if verification_report is not None:
                brd.verification_report = verification_report

            await session.commit()
            await session.refresh(brd)

            logger.info(f"Updated BRD: {brd.brd_number}")
            return brd

    async def update_brd_status(
        self,
        brd_id: str,
        status: str,
    ) -> Optional[BRDDB]:
        """Update BRD status (approve, archive, etc.)."""
        return await self.update_brd(brd_id, status=status)

    async def delete_brd(self, brd_id: str) -> bool:
        """Delete a BRD and all its EPICs/Backlogs (cascade).

        Args:
            brd_id: BRD ID to delete

        Returns:
            True if deleted, False if not found
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(BRDDB).where(BRDDB.id == brd_id)
            )
            brd = result.scalar_one_or_none()

            if not brd:
                return False

            brd_number = brd.brd_number
            await session.delete(brd)
            await session.commit()

            logger.info(f"Deleted BRD: {brd_number}")
            return True

    # =========================================================================
    # EPIC CRUD Operations
    # =========================================================================

    async def list_all_epics(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[EpicDB], int]:
        """List all EPICs with optional filters.

        Args:
            status: Filter by status
            search: Search in title/description
            limit: Max results
            offset: Skip results

        Returns:
            Tuple of (EPIC list, total count)
        """
        async with get_async_session() as session:
            # Build base query with eager loading (including BRD's repository)
            query = select(EpicDB).options(
                selectinload(EpicDB.brd).selectinload(BRDDB.repository),
                selectinload(EpicDB.backlogs),
            )
            count_query = select(func.count(EpicDB.id))

            # Apply filters
            conditions = []
            if status:
                conditions.append(EpicDB.status == DocumentStatus(status))
            if search:
                search_pattern = f"%{search}%"
                conditions.append(
                    or_(
                        EpicDB.title.ilike(search_pattern),
                        EpicDB.description.ilike(search_pattern),
                        EpicDB.epic_number.ilike(search_pattern),
                    )
                )

            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))

            # Get total count
            result = await session.execute(count_query)
            total = result.scalar_one()

            # Apply ordering and pagination
            query = query.order_by(desc(EpicDB.updated_at)).offset(offset).limit(limit)

            result = await session.execute(query)
            epics = list(result.scalars().unique().all())

            return epics, total

    async def save_epics_for_brd(
        self,
        brd_id: str,
        epics_data: list[dict],
    ) -> list[EpicDB]:
        """Save multiple EPICs for a BRD.

        Args:
            brd_id: Parent BRD ID
            epics_data: List of EPIC data dicts

        Returns:
            List of created EpicDB instances
        """
        async with get_async_session() as session:
            # Verify BRD exists
            result = await session.execute(
                select(BRDDB).where(BRDDB.id == brd_id)
            )
            brd = result.scalar_one_or_none()
            if not brd:
                raise ValueError(f"BRD not found: {brd_id}")

            created_epics = []
            for i, epic_data in enumerate(epics_data):
                epic_number = await self._generate_epic_number(brd_id)

                epic = EpicDB(
                    id=str(uuid4()),
                    epic_number=epic_number,
                    brd_id=brd_id,
                    title=epic_data.get("title", ""),
                    description=epic_data.get("description", ""),
                    business_value=epic_data.get("business_value"),
                    objectives=epic_data.get("objectives", []),
                    acceptance_criteria=epic_data.get("acceptance_criteria", []),
                    affected_components=epic_data.get("affected_components", []),
                    depends_on=epic_data.get("depends_on", []),
                    status=DocumentStatus.DRAFT,
                    display_order=i,
                )
                session.add(epic)
                created_epics.append(epic)

            await session.commit()

            # Re-fetch all EPICs with relationships loaded to avoid detached session issues
            epic_ids = [epic.id for epic in created_epics]
            result = await session.execute(
                select(EpicDB)
                .options(
                    selectinload(EpicDB.backlogs),
                    selectinload(EpicDB.brd),
                )
                .where(EpicDB.id.in_(epic_ids))
                .order_by(EpicDB.display_order)
            )
            loaded_epics = list(result.scalars().all())

            logger.info(f"Saved {len(loaded_epics)} EPICs for BRD {brd.brd_number}")
            return loaded_epics

    async def get_epics_for_brd(self, brd_id: str) -> list[EpicDB]:
        """Get all EPICs for a BRD."""
        async with get_async_session() as session:
            result = await session.execute(
                select(EpicDB)
                .options(selectinload(EpicDB.backlogs))
                .where(EpicDB.brd_id == brd_id)
                .order_by(EpicDB.display_order)
            )
            return list(result.scalars().all())

    async def get_epic(self, epic_id: str) -> Optional[EpicDB]:
        """Get an EPIC by ID with backlogs loaded."""
        async with get_async_session() as session:
            result = await session.execute(
                select(EpicDB)
                .options(
                    selectinload(EpicDB.backlogs),
                    selectinload(EpicDB.brd),
                )
                .where(EpicDB.id == epic_id)
            )
            return result.scalar_one_or_none()

    async def update_epic(
        self,
        epic_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        business_value: Optional[str] = None,
        objectives: Optional[list] = None,
        acceptance_criteria: Optional[list] = None,
        status: Optional[str] = None,
    ) -> Optional[EpicDB]:
        """Update an EPIC."""
        async with get_async_session() as session:
            result = await session.execute(
                select(EpicDB).where(EpicDB.id == epic_id)
            )
            epic = result.scalar_one_or_none()

            if not epic:
                return None

            if title is not None:
                epic.title = title
            if description is not None:
                epic.description = description
            if business_value is not None:
                epic.business_value = business_value
            if objectives is not None:
                epic.objectives = objectives
            if acceptance_criteria is not None:
                epic.acceptance_criteria = acceptance_criteria
            if status is not None:
                epic.status = DocumentStatus(status)

            epic.refinement_count += 1
            await session.commit()
            await session.refresh(epic)

            return epic

    async def delete_epic(self, epic_id: str) -> bool:
        """Delete an EPIC and all its backlogs."""
        async with get_async_session() as session:
            result = await session.execute(
                select(EpicDB).where(EpicDB.id == epic_id)
            )
            epic = result.scalar_one_or_none()

            if not epic:
                return False

            await session.delete(epic)
            await session.commit()

            logger.info(f"Deleted EPIC: {epic.epic_number}")
            return True

    # =========================================================================
    # Backlog CRUD Operations
    # =========================================================================

    async def save_backlogs_for_epic(
        self,
        epic_id: str,
        backlogs_data: list[dict],
    ) -> list[BacklogDB]:
        """Save multiple backlog items for an EPIC.

        Args:
            epic_id: Parent EPIC ID
            backlogs_data: List of backlog item data dicts

        Returns:
            List of created BacklogDB instances
        """
        async with get_async_session() as session:
            # Verify EPIC exists
            result = await session.execute(
                select(EpicDB).where(EpicDB.id == epic_id)
            )
            epic = result.scalar_one_or_none()
            if not epic:
                raise ValueError(f"EPIC not found: {epic_id}")

            created_backlogs = []
            for i, item_data in enumerate(backlogs_data):
                item_type = item_data.get("item_type", "user_story")
                backlog_number = await self._generate_backlog_number(epic_id, item_type)

                backlog = BacklogDB(
                    id=str(uuid4()),
                    backlog_number=backlog_number,
                    epic_id=epic_id,
                    title=item_data.get("title", ""),
                    description=item_data.get("description", ""),
                    item_type=BacklogItemType(item_type),
                    as_a=item_data.get("as_a"),
                    i_want=item_data.get("i_want"),
                    so_that=item_data.get("so_that"),
                    acceptance_criteria=item_data.get("acceptance_criteria", []),
                    technical_notes=item_data.get("technical_notes"),
                    files_to_modify=item_data.get("files_to_modify", []),
                    files_to_create=item_data.get("files_to_create", []),
                    priority=EpicPriority(item_data.get("priority", "medium")),
                    story_points=item_data.get("story_points"),
                    status=DocumentStatus.DRAFT,
                    display_order=i,
                )
                session.add(backlog)
                created_backlogs.append(backlog)

            await session.commit()

            for backlog in created_backlogs:
                await session.refresh(backlog)

            logger.info(f"Saved {len(created_backlogs)} backlogs for EPIC {epic.epic_number}")
            return created_backlogs

    async def get_backlogs_for_epic(self, epic_id: str) -> list[BacklogDB]:
        """Get all backlogs for an EPIC."""
        async with get_async_session() as session:
            result = await session.execute(
                select(BacklogDB)
                .where(BacklogDB.epic_id == epic_id)
                .order_by(BacklogDB.display_order)
            )
            return list(result.scalars().all())

    async def list_all_backlogs(
        self,
        status: Optional[str] = None,
        item_type: Optional[str] = None,
        priority: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BacklogDB], int]:
        """List all backlogs with optional filters."""
        async with get_async_session() as session:
            query = select(BacklogDB).options(
                selectinload(BacklogDB.epic),
            )

            # Apply filters
            if status:
                query = query.where(BacklogDB.status == DocumentStatus(status))
            if item_type:
                query = query.where(BacklogDB.item_type == item_type)
            if priority:
                query = query.where(BacklogDB.priority == EpicPriority(priority))
            if search:
                search_filter = or_(
                    BacklogDB.title.ilike(f"%{search}%"),
                    BacklogDB.description.ilike(f"%{search}%"),
                )
                query = query.where(search_filter)

            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar() or 0

            # Apply pagination and ordering
            query = query.order_by(BacklogDB.updated_at.desc())
            query = query.offset(offset).limit(limit)

            result = await session.execute(query)
            backlogs = list(result.scalars().all())

            return backlogs, total

    async def get_backlog(self, backlog_id: str) -> Optional[BacklogDB]:
        """Get a backlog item by ID."""
        async with get_async_session() as session:
            result = await session.execute(
                select(BacklogDB)
                .options(selectinload(BacklogDB.epic))
                .where(BacklogDB.id == backlog_id)
            )
            return result.scalar_one_or_none()

    async def update_backlog(
        self,
        backlog_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        acceptance_criteria: Optional[list] = None,
        priority: Optional[str] = None,
        story_points: Optional[int] = None,
        status: Optional[str] = None,
    ) -> Optional[BacklogDB]:
        """Update a backlog item."""
        async with get_async_session() as session:
            result = await session.execute(
                select(BacklogDB).where(BacklogDB.id == backlog_id)
            )
            backlog = result.scalar_one_or_none()

            if not backlog:
                return None

            if title is not None:
                backlog.title = title
            if description is not None:
                backlog.description = description
            if acceptance_criteria is not None:
                backlog.acceptance_criteria = acceptance_criteria
            if priority is not None:
                backlog.priority = EpicPriority(priority)
            if story_points is not None:
                backlog.story_points = story_points
            if status is not None:
                backlog.status = DocumentStatus(status)

            backlog.refinement_count += 1
            await session.commit()
            await session.refresh(backlog)

            return backlog

    async def delete_backlog(self, backlog_id: str) -> bool:
        """Delete a backlog item."""
        async with get_async_session() as session:
            result = await session.execute(
                select(BacklogDB).where(BacklogDB.id == backlog_id)
            )
            backlog = result.scalar_one_or_none()

            if not backlog:
                return False

            await session.delete(backlog)
            await session.commit()

            logger.info(f"Deleted backlog: {backlog.backlog_number}")
            return True

    # =========================================================================
    # Export Operations
    # =========================================================================

    async def export_brd(
        self,
        brd_id: str,
        format: str = "md",
    ) -> Optional[str]:
        """Export a BRD in the specified format.

        Args:
            brd_id: BRD ID to export
            format: Export format ('md' or 'html')

        Returns:
            Exported content string or None if not found
        """
        brd = await self.get_brd(brd_id)
        if not brd:
            return None

        if format == "md":
            return brd.markdown_content
        elif format == "html":
            # Simple markdown to HTML conversion
            import markdown
            return markdown.markdown(
                brd.markdown_content,
                extensions=["tables", "fenced_code"],
            )
        else:
            return brd.markdown_content

    async def export_brd_with_children(
        self,
        brd_id: str,
        format: str = "md",
    ) -> Optional[str]:
        """Export a BRD with all EPICs and Backlogs.

        Args:
            brd_id: BRD ID to export
            format: Export format

        Returns:
            Complete export content
        """
        brd = await self.get_brd(brd_id)
        if not brd:
            return None

        content_parts = [brd.markdown_content]

        if brd.epics:
            content_parts.append("\n\n---\n\n# EPICs\n")

            for epic in brd.epics:
                content_parts.append(f"\n## {epic.epic_number}: {epic.title}\n")
                content_parts.append(f"\n{epic.description}\n")

                if epic.objectives:
                    content_parts.append("\n### Objectives\n")
                    for obj in epic.objectives:
                        content_parts.append(f"- {obj}\n")

                if epic.backlogs:
                    content_parts.append("\n### Backlog Items\n")
                    for backlog in epic.backlogs:
                        content_parts.append(
                            f"\n#### {backlog.backlog_number}: {backlog.title}\n"
                        )
                        content_parts.append(
                            f"**Type:** {backlog.item_type.value} | "
                            f"**Points:** {backlog.story_points or 'TBD'}\n"
                        )
                        content_parts.append(f"\n{backlog.description}\n")

        full_content = "".join(content_parts)

        if format == "html":
            import markdown
            return markdown.markdown(full_content, extensions=["tables", "fenced_code"])

        return full_content

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_brd_stats(self, repository_id: Optional[str] = None) -> dict:
        """Get BRD statistics, optionally filtered by repository."""
        async with get_async_session() as session:
            base_query = select(BRDDB)
            if repository_id:
                base_query = base_query.where(BRDDB.repository_id == repository_id)

            # Total BRDs
            result = await session.execute(
                select(func.count(BRDDB.id)).select_from(
                    base_query.subquery()
                )
            )
            total_brds = result.scalar_one()

            # By status
            result = await session.execute(
                select(BRDDB.status, func.count(BRDDB.id))
                .group_by(BRDDB.status)
            )
            by_status = {str(row[0].value): row[1] for row in result}

            return {
                "total_brds": total_brds,
                "by_status": by_status,
            }
