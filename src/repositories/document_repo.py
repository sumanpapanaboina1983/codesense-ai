"""
Document repository for managing document data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from src.core.constants import DocumentType, VerificationStatus
from src.core.logging import get_logger
from src.domain.document import Document
from src.repositories.base import BaseRepository

logger = get_logger(__name__)


class InMemoryDocumentRepository(BaseRepository[Document]):
    """
    In-memory document repository for development/testing.
    """

    def __init__(self) -> None:
        self._documents: dict[str, Document] = {}

    async def get(self, id: str) -> Optional[Document]:
        """Get a document by ID."""
        return self._documents.get(id)

    async def save(self, entity: Document) -> Document:
        """Save a document."""
        entity.updated_at = datetime.utcnow()
        self._documents[entity.id] = entity
        logger.debug("Document saved", document_id=entity.id, type=entity.type.value)
        return entity

    async def delete(self, id: str) -> bool:
        """Delete a document by ID."""
        if id in self._documents:
            del self._documents[id]
            logger.debug("Document deleted", document_id=id)
            return True
        return False

    async def list(
        self,
        filters: Optional[dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Document]:
        """List documents with optional filters."""
        documents = list(self._documents.values())

        if filters:
            if "session_id" in filters:
                documents = [d for d in documents if d.session_id == filters["session_id"]]
            if "type" in filters:
                doc_type = filters["type"]
                if isinstance(doc_type, str):
                    doc_type = DocumentType(doc_type)
                documents = [d for d in documents if d.type == doc_type]
            if "parent_document_id" in filters:
                documents = [d for d in documents if d.parent_document_id == filters["parent_document_id"]]
            if "verification_status" in filters:
                status = filters["verification_status"]
                if isinstance(status, str):
                    status = VerificationStatus(status)
                documents = [d for d in documents if d.verification_status == status]

        # Sort by created_at descending
        documents.sort(key=lambda d: d.created_at, reverse=True)

        return documents[offset : offset + limit]

    async def exists(self, id: str) -> bool:
        """Check if a document exists."""
        return id in self._documents

    async def get_by_session(self, session_id: str) -> list[Document]:
        """Get all documents for a session."""
        return [
            d for d in self._documents.values()
            if d.session_id == session_id
        ]

    async def get_children(self, parent_id: str) -> list[Document]:
        """Get child documents of a parent document."""
        return [
            d for d in self._documents.values()
            if d.parent_document_id == parent_id
        ]

    async def get_hierarchy(self, root_id: str) -> list[Document]:
        """Get all documents in a hierarchy starting from root."""
        result: list[Document] = []
        queue = [root_id]

        while queue:
            current_id = queue.pop(0)
            doc = self._documents.get(current_id)
            if doc:
                result.append(doc)
                children = await self.get_children(current_id)
                queue.extend([c.id for c in children])

        return result


class PostgresDocumentRepository(BaseRepository[Document]):
    """
    PostgreSQL document repository for production.
    """

    def __init__(self, connection_pool: Any) -> None:
        """
        Initialize with a database connection pool.

        Args:
            connection_pool: AsyncPG connection pool
        """
        self.pool = connection_pool

    async def get(self, id: str) -> Optional[Document]:
        """Get a document by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, type, title, content, session_id, parent_document_id,
                       component_name, verification_status, confidence_score,
                       metadata, created_at, updated_at
                FROM documents
                WHERE id = $1
                """,
                id,
            )

            if row:
                return self._row_to_document(row)

            return None

    async def save(self, entity: Document) -> Document:
        """Save a document."""
        entity.updated_at = datetime.utcnow()

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (
                    id, type, title, content, session_id, parent_document_id,
                    component_name, verification_status, confidence_score,
                    metadata, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    verification_status = EXCLUDED.verification_status,
                    confidence_score = EXCLUDED.confidence_score,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                """,
                entity.id,
                entity.type.value,
                entity.title,
                entity.content,
                entity.session_id,
                entity.parent_document_id,
                entity.component_name,
                entity.verification_status.value,
                entity.confidence_score,
                entity.metadata,
                entity.created_at,
                entity.updated_at,
            )

        return entity

    async def delete(self, id: str) -> bool:
        """Delete a document by ID."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM documents WHERE id = $1",
                id,
            )
            return result == "DELETE 1"

    async def list(
        self,
        filters: Optional[dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Document]:
        """List documents with optional filters."""
        query = "SELECT * FROM documents WHERE 1=1"
        params: list[Any] = []

        if filters:
            if "session_id" in filters:
                query += f" AND session_id = ${len(params) + 1}"
                params.append(filters["session_id"])
            if "type" in filters:
                query += f" AND type = ${len(params) + 1}"
                doc_type = filters["type"]
                params.append(doc_type.value if isinstance(doc_type, DocumentType) else doc_type)
            if "parent_document_id" in filters:
                query += f" AND parent_document_id = ${len(params) + 1}"
                params.append(filters["parent_document_id"])

        query += f" ORDER BY created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        params.extend([limit, offset])

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [self._row_to_document(row) for row in rows]

    async def exists(self, id: str) -> bool:
        """Check if a document exists."""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM documents WHERE id = $1)",
                id,
            )
            return result

    async def get_by_session(self, session_id: str) -> list[Document]:
        """Get all documents for a session."""
        return await self.list(filters={"session_id": session_id})

    async def get_children(self, parent_id: str) -> list[Document]:
        """Get child documents of a parent document."""
        return await self.list(filters={"parent_document_id": parent_id})

    def _row_to_document(self, row: Any) -> Document:
        """Convert a database row to a Document."""
        return Document(
            id=row["id"],
            type=DocumentType(row["type"]),
            title=row["title"],
            content=row["content"],
            session_id=row["session_id"],
            parent_document_id=row["parent_document_id"],
            component_name=row["component_name"],
            verification_status=VerificationStatus(row["verification_status"]),
            confidence_score=row["confidence_score"],
            metadata=row["metadata"] or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
