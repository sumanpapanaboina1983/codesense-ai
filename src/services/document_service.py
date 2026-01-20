"""
Document service for managing document lifecycle.
"""

from datetime import datetime
from typing import Any, Optional

from src.core.constants import DocumentType, VerificationStatus, WorkflowStatus
from src.core.exceptions import DocumentNotFoundError, ValidationError
from src.core.logging import get_logger
from src.domain.document import Document
from src.orchestration.workflow_engine import WorkflowContext, WorkflowEngine, WorkflowResult
from src.orchestration.workflows import BacklogWorkflow, BRDWorkflow, EpicWorkflow

logger = get_logger(__name__)


class DocumentService:
    """
    Service for managing document generation and retrieval.
    """

    def __init__(
        self,
        workflow_engine: WorkflowEngine,
        document_repository: Optional[Any] = None,
    ) -> None:
        """
        Initialize the document service.

        Args:
            workflow_engine: Workflow engine for document generation
            document_repository: Repository for document storage
        """
        self.workflow_engine = workflow_engine
        self.document_repository = document_repository

        # Register workflows
        self._register_workflows()

        # In-memory cache for documents (should be replaced with repository)
        self._documents: dict[str, Document] = {}

    def _register_workflows(self) -> None:
        """Register all document generation workflows."""
        self.workflow_engine.register_workflow(BRDWorkflow)
        self.workflow_engine.register_workflow(EpicWorkflow)
        self.workflow_engine.register_workflow(BacklogWorkflow)

        logger.info(
            "Registered workflows",
            workflows=self.workflow_engine.list_registered_workflows()
        )

    async def generate_brd(
        self,
        session_id: str,
        component_name: str,
        codebase_path: str = "/codebase",
        preferences: Optional[dict[str, Any]] = None,
    ) -> WorkflowResult:
        """
        Generate a Business Requirements Document.

        Args:
            session_id: Session ID
            component_name: Component to analyze
            codebase_path: Path to codebase
            preferences: User preferences for generation

        Returns:
            Workflow result with generated BRD
        """
        logger.info(
            "Generating BRD",
            session_id=session_id,
            component=component_name,
        )

        context = WorkflowContext(
            session_id=session_id,
            codebase_path=codebase_path,
            component_name=component_name,
            preferences=preferences or {},
        )

        result = await self.workflow_engine.execute_workflow("brd", context)

        # Store document if generation succeeded
        if result.status == WorkflowStatus.COMPLETED and result.document:
            await self._store_document(result.document)

        return result

    async def generate_epics(
        self,
        session_id: str,
        brd_document_id: str,
        codebase_path: str = "/codebase",
        preferences: Optional[dict[str, Any]] = None,
    ) -> WorkflowResult:
        """
        Generate Epics from a BRD.

        Args:
            session_id: Session ID
            brd_document_id: Parent BRD document ID
            codebase_path: Path to codebase
            preferences: User preferences for generation

        Returns:
            Workflow result with generated Epics
        """
        logger.info(
            "Generating Epics",
            session_id=session_id,
            brd_id=brd_document_id,
        )

        # Load the BRD content
        brd_document = await self.get_document(brd_document_id)
        if not brd_document:
            raise DocumentNotFoundError(
                document_id=brd_document_id,
                message=f"BRD document not found: {brd_document_id}",
            )

        context = WorkflowContext(
            session_id=session_id,
            codebase_path=codebase_path,
            parent_document_id=brd_document_id,
            preferences=preferences or {},
            metadata={"brd_content": brd_document.content},
        )

        result = await self.workflow_engine.execute_workflow("epic", context)

        # Store documents if generation succeeded
        if result.status == WorkflowStatus.COMPLETED:
            if result.document:
                await self._store_document(result.document)
            # Store additional epics from artifacts
            for artifact in result.artifacts:
                if artifact.get("type") == "epic" and artifact.get("document"):
                    doc_data = artifact["document"]
                    doc = Document(**doc_data)
                    await self._store_document(doc)

        return result

    async def generate_backlog(
        self,
        session_id: str,
        epic_id: str,
        codebase_path: str = "/codebase",
        preferences: Optional[dict[str, Any]] = None,
    ) -> WorkflowResult:
        """
        Generate Backlog Items from an Epic.

        Args:
            session_id: Session ID
            epic_id: Parent Epic ID
            codebase_path: Path to codebase
            preferences: User preferences for generation

        Returns:
            Workflow result with generated Backlog Items
        """
        logger.info(
            "Generating Backlog Items",
            session_id=session_id,
            epic_id=epic_id,
        )

        # Load the Epic content
        epic_document = await self.get_document(epic_id)
        if not epic_document:
            raise DocumentNotFoundError(
                document_id=epic_id,
                message=f"Epic document not found: {epic_id}",
            )

        context = WorkflowContext(
            session_id=session_id,
            codebase_path=codebase_path,
            parent_document_id=epic_id,
            preferences=preferences or {},
            metadata={"epic_content": epic_document.content},
        )

        result = await self.workflow_engine.execute_workflow("backlog", context)

        # Store documents if generation succeeded
        if result.status == WorkflowStatus.COMPLETED:
            if result.document:
                await self._store_document(result.document)
            # Store additional items from artifacts
            for artifact in result.artifacts:
                if artifact.get("type") == "backlog_item" and artifact.get("document"):
                    doc_data = artifact["document"]
                    doc = Document(**doc_data)
                    await self._store_document(doc)

        return result

    async def get_document(self, document_id: str) -> Optional[Document]:
        """
        Get a document by ID.

        Args:
            document_id: Document ID

        Returns:
            Document if found, None otherwise
        """
        # Try in-memory cache first
        if document_id in self._documents:
            return self._documents[document_id]

        # Try repository if available
        if self.document_repository:
            return await self.document_repository.get(document_id)

        return None

    async def list_documents(
        self,
        session_id: Optional[str] = None,
        document_type: Optional[DocumentType] = None,
        parent_document_id: Optional[str] = None,
    ) -> list[Document]:
        """
        List documents with optional filters.

        Args:
            session_id: Filter by session
            document_type: Filter by type
            parent_document_id: Filter by parent document

        Returns:
            List of matching documents
        """
        documents = list(self._documents.values())

        if session_id:
            documents = [d for d in documents if d.session_id == session_id]

        if document_type:
            documents = [d for d in documents if d.type == document_type]

        if parent_document_id:
            documents = [d for d in documents if d.parent_document_id == parent_document_id]

        return sorted(documents, key=lambda d: d.created_at, reverse=True)

    async def update_document(
        self,
        document_id: str,
        content: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Document:
        """
        Update a document.

        Args:
            document_id: Document ID
            content: New content (optional)
            title: New title (optional)
            metadata: Additional metadata (optional)

        Returns:
            Updated document
        """
        document = await self.get_document(document_id)
        if not document:
            raise DocumentNotFoundError(
                document_id=document_id,
                message=f"Document not found: {document_id}",
            )

        if content is not None:
            document.content = content
            document.verification_status = VerificationStatus.PENDING

        if title is not None:
            document.title = title

        if metadata:
            document.metadata.update(metadata)

        document.updated_at = datetime.utcnow()

        await self._store_document(document)
        return document

    async def delete_document(self, document_id: str) -> bool:
        """
        Delete a document.

        Args:
            document_id: Document ID

        Returns:
            True if deleted, False if not found
        """
        if document_id in self._documents:
            del self._documents[document_id]

            if self.document_repository:
                await self.document_repository.delete(document_id)

            logger.info("Document deleted", document_id=document_id)
            return True

        return False

    async def get_document_hierarchy(
        self,
        root_document_id: str
    ) -> dict[str, Any]:
        """
        Get the full document hierarchy starting from a root document.

        Args:
            root_document_id: Root document ID (typically a BRD)

        Returns:
            Hierarchical structure of documents
        """
        root = await self.get_document(root_document_id)
        if not root:
            raise DocumentNotFoundError(
                document_id=root_document_id,
                message=f"Root document not found: {root_document_id}",
            )

        # Build hierarchy
        hierarchy = {
            "document": root.dict(),
            "children": [],
        }

        # Find child documents (Epics for BRD, Backlog Items for Epic)
        children = await self.list_documents(parent_document_id=root_document_id)

        for child in children:
            child_hierarchy = await self.get_document_hierarchy(child.id)
            hierarchy["children"].append(child_hierarchy)

        return hierarchy

    async def export_document(
        self,
        document_id: str,
        format: str = "markdown"
    ) -> str:
        """
        Export a document in the specified format.

        Args:
            document_id: Document ID
            format: Export format (markdown, json, html)

        Returns:
            Exported document content
        """
        document = await self.get_document(document_id)
        if not document:
            raise DocumentNotFoundError(
                document_id=document_id,
                message=f"Document not found: {document_id}",
            )

        if format == "markdown":
            return self._export_markdown(document)
        elif format == "json":
            return document.json(indent=2)
        elif format == "html":
            return self._export_html(document)
        else:
            raise ValidationError(
                field="format",
                message=f"Unsupported export format: {format}",
            )

    def _export_markdown(self, document: Document) -> str:
        """Export document as Markdown."""
        lines = [
            f"# {document.title}",
            "",
            f"**Type:** {document.type.value}",
            f"**ID:** {document.id}",
            f"**Created:** {document.created_at.isoformat()}",
            f"**Verification:** {document.verification_status.value} ({document.confidence_score:.0%})",
            "",
            "---",
            "",
            document.content,
        ]

        return "\n".join(lines)

    def _export_html(self, document: Document) -> str:
        """Export document as HTML."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{document.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .metadata {{ color: #666; font-size: 0.9em; }}
        .content {{ margin-top: 20px; }}
    </style>
</head>
<body>
    <h1>{document.title}</h1>
    <div class="metadata">
        <p><strong>Type:</strong> {document.type.value}</p>
        <p><strong>ID:</strong> {document.id}</p>
        <p><strong>Verification:</strong> {document.verification_status.value} ({document.confidence_score:.0%})</p>
    </div>
    <hr>
    <div class="content">
        {self._markdown_to_html(document.content)}
    </div>
</body>
</html>"""

        return html

    def _markdown_to_html(self, content: str) -> str:
        """Simple Markdown to HTML conversion."""
        # Basic conversion - in production, use a proper Markdown library
        import re

        html = content

        # Headers
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)

        # Bold and italic
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)

        # Lists
        html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)

        # Paragraphs
        html = re.sub(r"\n\n", r"</p><p>", html)
        html = f"<p>{html}</p>"

        return html

    async def _store_document(self, document: Document) -> None:
        """Store a document."""
        self._documents[document.id] = document

        if self.document_repository:
            await self.document_repository.save(document)

        logger.info(
            "Document stored",
            document_id=document.id,
            type=document.type.value,
        )
