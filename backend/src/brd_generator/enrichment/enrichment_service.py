"""Enrichment Service.

Orchestrates documentation and test generation for codebases.
Integrates with Neo4j for entity discovery and LLM for content generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .documentation_generator import (
    DocumentationGenerator,
    DocumentationStyle,
    EntityContext,
    GeneratedDocumentation,
)
from .test_generator import (
    TestGenerator,
    TestFramework,
    TestType,
    FunctionContext,
    GeneratedTest,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EnrichmentResult:
    """Result from an enrichment operation."""
    success: bool
    entities_processed: int
    entities_enriched: int
    entities_skipped: int
    generated_content: list[dict]
    errors: list[dict]
    enrichment_type: str  # "documentation" or "testing"


class EnrichmentService:
    """Orchestrates codebase enrichment operations.

    This service coordinates between:
    - Neo4j graph database for entity discovery
    - LLM (via Copilot session) for content generation
    - Documentation and Test generators for creating enrichments
    """

    def __init__(
        self,
        neo4j_client: Any = None,
        copilot_session: Any = None,
    ):
        """Initialize the enrichment service.

        Args:
            neo4j_client: Neo4j client for querying code graph.
            copilot_session: Copilot session for LLM-based generation.
        """
        self.neo4j_client = neo4j_client
        self.copilot_session = copilot_session

        # Initialize generators
        self.doc_generator = DocumentationGenerator(copilot_session)
        self.test_generator = TestGenerator(copilot_session)

    async def enrich_documentation(
        self,
        repository_id: str,
        entity_ids: list[str] | str,
        style: DocumentationStyle = DocumentationStyle.JSDOC,
        include_examples: bool = True,
        include_parameters: bool = True,
        include_returns: bool = True,
        include_throws: bool = True,
        max_entities: int = 50,
    ) -> EnrichmentResult:
        """Generate documentation for undocumented entities.

        Args:
            repository_id: Repository to enrich.
            entity_ids: Specific entity IDs or "all-undocumented".
            style: Documentation style to use.
            include_examples: Include usage examples.
            include_parameters: Include parameter descriptions.
            include_returns: Include return value descriptions.
            include_throws: Include exception information.
            max_entities: Maximum entities to process.

        Returns:
            EnrichmentResult with generated documentation.
        """
        logger.info(f"Starting documentation enrichment for repository: {repository_id}")

        try:
            # Get entities to document
            if entity_ids == "all-undocumented":
                entities = await self._fetch_undocumented_entities(repository_id, max_entities)
            else:
                entities = await self._fetch_entities_by_ids(repository_id, entity_ids)

            logger.info(f"Found {len(entities)} entities to document")

            if not entities:
                return EnrichmentResult(
                    success=True,
                    entities_processed=0,
                    entities_enriched=0,
                    entities_skipped=0,
                    generated_content=[],
                    errors=[],
                    enrichment_type="documentation",
                )

            # Generate documentation
            generated_docs: list[GeneratedDocumentation] = []
            errors: list[dict] = []

            for entity in entities:
                try:
                    doc = await self.doc_generator.generate_documentation(
                        entity=entity,
                        style=style,
                        include_examples=include_examples,
                        include_params=include_parameters,
                        include_returns=include_returns,
                        include_throws=include_throws,
                    )
                    generated_docs.append(doc)
                except Exception as e:
                    logger.error(f"Failed to generate documentation for {entity.entity_name}: {e}")
                    errors.append({
                        "entity_id": entity.entity_id,
                        "error": str(e),
                    })

            # Convert to result format
            generated_content = [
                {
                    "entity_id": doc.entity_id,
                    "entity_name": doc.entity_name,
                    "file_path": doc.file_path,
                    "content": doc.documentation,
                    "insert_position": {
                        "line": doc.insert_line,
                        "column": doc.insert_column,
                    },
                    "content_type": "documentation",
                    "is_new_file": False,
                }
                for doc in generated_docs
            ]

            return EnrichmentResult(
                success=True,
                entities_processed=len(entities),
                entities_enriched=len(generated_docs),
                entities_skipped=len(errors),
                generated_content=generated_content,
                errors=errors,
                enrichment_type="documentation",
            )

        except Exception as e:
            logger.exception("Documentation enrichment failed")
            return EnrichmentResult(
                success=False,
                entities_processed=0,
                entities_enriched=0,
                entities_skipped=0,
                generated_content=[],
                errors=[{"entity_id": "unknown", "error": str(e)}],
                enrichment_type="documentation",
            )

    async def enrich_tests(
        self,
        repository_id: str,
        entity_ids: list[str] | str,
        framework: str = "jest",
        test_types: list[str] = None,
        include_mocks: bool = True,
        include_edge_cases: bool = True,
        max_entities: int = 20,
    ) -> EnrichmentResult:
        """Generate tests for untested entities.

        Args:
            repository_id: Repository to enrich.
            entity_ids: Specific entity IDs or "all-untested".
            framework: Test framework to use.
            test_types: Types of tests to generate.
            include_mocks: Include mock setup.
            include_edge_cases: Include edge case tests.
            max_entities: Maximum entities to process.

        Returns:
            EnrichmentResult with generated tests.
        """
        logger.info(f"Starting test enrichment for repository: {repository_id}")

        try:
            # Parse test types
            if test_types is None:
                test_types = [TestType.UNIT]
            else:
                test_types = [TestType(t) for t in test_types]

            # Parse framework
            try:
                test_framework = TestFramework(framework.lower())
            except ValueError:
                test_framework = TestFramework.JEST

            # Get entities to test
            if entity_ids == "all-untested":
                entities = await self._fetch_untested_entities(repository_id, max_entities)
            else:
                entities = await self._fetch_function_entities_by_ids(repository_id, entity_ids)

            logger.info(f"Found {len(entities)} entities to test")

            if not entities:
                return EnrichmentResult(
                    success=True,
                    entities_processed=0,
                    entities_enriched=0,
                    entities_skipped=0,
                    generated_content=[],
                    errors=[],
                    enrichment_type="testing",
                )

            # Generate tests
            generated_tests: list[GeneratedTest] = []
            errors: list[dict] = []

            for entity in entities:
                try:
                    test = await self.test_generator.generate_tests(
                        entity=entity,
                        framework=test_framework,
                        test_types=test_types,
                        include_mocks=include_mocks,
                        include_edge_cases=include_edge_cases,
                    )
                    generated_tests.append(test)
                except Exception as e:
                    logger.error(f"Failed to generate tests for {entity.entity_name}: {e}")
                    errors.append({
                        "entity_id": entity.entity_id,
                        "error": str(e),
                    })

            # Convert to result format
            generated_content = [
                {
                    "entity_id": test.entity_id,
                    "entity_name": test.entity_name,
                    "file_path": test.test_file_path,
                    "content": test.test_code,
                    "insert_position": {
                        "line": 0,
                        "column": 0,
                    },
                    "content_type": "test",
                    "is_new_file": True,
                }
                for test in generated_tests
            ]

            return EnrichmentResult(
                success=True,
                entities_processed=len(entities),
                entities_enriched=len(generated_tests),
                entities_skipped=len(errors),
                generated_content=generated_content,
                errors=errors,
                enrichment_type="testing",
            )

        except Exception as e:
            logger.exception("Test enrichment failed")
            return EnrichmentResult(
                success=False,
                entities_processed=0,
                entities_enriched=0,
                entities_skipped=0,
                generated_content=[],
                errors=[{"entity_id": "unknown", "error": str(e)}],
                enrichment_type="testing",
            )

    # =========================================================================
    # Neo4j Query Methods
    # =========================================================================

    async def _fetch_undocumented_entities(
        self,
        repository_id: str,
        limit: int,
    ) -> list[EntityContext]:
        """Fetch undocumented public entities from Neo4j."""
        if not self.neo4j_client:
            logger.warning("No Neo4j client available, returning empty list")
            return []

        query = """
            MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
            MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION|DEFINES_CLASS*1..2]->(n)
            WHERE (n:Function OR n:Method OR n:Class OR n:JavaMethod OR n:JavaClass)
              AND (n.isExported = true OR n.visibility = 'public')
              AND (n.hasDocumentation IS NULL OR n.hasDocumentation = false)
            RETURN n.entityId as entityId, n.name as name, n.filePath as filePath,
                   labels(n)[0] as kind, n.language as language,
                   n.signature as signature, n.startLine as startLine,
                   n.endLine as endLine, n.parameters as parameters,
                   n.returnType as returnType
            LIMIT $limit
        """

        try:
            result = await self.neo4j_client.runTransaction(
                query,
                {"repositoryId": repository_id, "limit": limit},
                "READ",
                "EnrichmentService"
            )

            entities = []
            for record in (result.records or []):
                entities.append(EntityContext(
                    entity_id=record.get("entityId"),
                    entity_name=record.get("name"),
                    file_path=record.get("filePath"),
                    language=record.get("language") or "unknown",
                    kind=record.get("kind"),
                    signature=record.get("signature"),
                    start_line=record.get("startLine") or 0,
                    end_line=record.get("endLine") or 0,
                    parameters=record.get("parameters"),
                    return_type=record.get("returnType"),
                ))
            return entities

        except Exception as e:
            logger.error(f"Failed to fetch undocumented entities: {e}")
            return []

    async def _fetch_entities_by_ids(
        self,
        repository_id: str,
        entity_ids: list[str],
    ) -> list[EntityContext]:
        """Fetch specific entities by their IDs."""
        if not self.neo4j_client:
            return []

        query = """
            MATCH (n)
            WHERE n.entityId IN $entityIds
            RETURN n.entityId as entityId, n.name as name, n.filePath as filePath,
                   labels(n)[0] as kind, n.language as language,
                   n.signature as signature, n.startLine as startLine,
                   n.endLine as endLine, n.parameters as parameters,
                   n.returnType as returnType
        """

        try:
            result = await self.neo4j_client.runTransaction(
                query,
                {"entityIds": entity_ids},
                "READ",
                "EnrichmentService"
            )

            entities = []
            for record in (result.records or []):
                entities.append(EntityContext(
                    entity_id=record.get("entityId"),
                    entity_name=record.get("name"),
                    file_path=record.get("filePath"),
                    language=record.get("language") or "unknown",
                    kind=record.get("kind"),
                    signature=record.get("signature"),
                    start_line=record.get("startLine") or 0,
                    end_line=record.get("endLine") or 0,
                    parameters=record.get("parameters"),
                    return_type=record.get("returnType"),
                ))
            return entities

        except Exception as e:
            logger.error(f"Failed to fetch entities by IDs: {e}")
            return []

    async def _fetch_untested_entities(
        self,
        repository_id: str,
        limit: int,
    ) -> list[FunctionContext]:
        """Fetch untested critical functions from Neo4j."""
        if not self.neo4j_client:
            return []

        query = """
            MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
            MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
            WHERE (fn:Function OR fn:Method OR fn:JavaMethod)
              AND (fn.stereotype IN ['Controller', 'Service'] OR fn.entryPointType IS NOT NULL)
            OPTIONAL MATCH (test)-[:TESTS|COVERS]->(fn)
            WITH fn, count(test) as testCount
            WHERE testCount = 0
            RETURN fn.entityId as entityId, fn.name as name, fn.filePath as filePath,
                   labels(fn)[0] as kind, fn.language as language,
                   fn.signature as signature, fn.startLine as startLine,
                   fn.endLine as endLine, fn.parameters as parameters,
                   fn.returnType as returnType, fn.isAsync as isAsync,
                   fn.isStatic as isStatic, fn.visibility as visibility
            LIMIT $limit
        """

        try:
            result = await self.neo4j_client.runTransaction(
                query,
                {"repositoryId": repository_id, "limit": limit},
                "READ",
                "EnrichmentService"
            )

            entities = []
            for record in (result.records or []):
                entities.append(FunctionContext(
                    entity_id=record.get("entityId"),
                    entity_name=record.get("name"),
                    file_path=record.get("filePath"),
                    language=record.get("language") or "unknown",
                    kind=record.get("kind"),
                    signature=record.get("signature"),
                    parameters=record.get("parameters") or [],
                    return_type=record.get("returnType"),
                    is_async=record.get("isAsync") or False,
                    is_static=record.get("isStatic") or False,
                    visibility=record.get("visibility") or "public",
                ))
            return entities

        except Exception as e:
            logger.error(f"Failed to fetch untested entities: {e}")
            return []

    async def _fetch_function_entities_by_ids(
        self,
        repository_id: str,
        entity_ids: list[str],
    ) -> list[FunctionContext]:
        """Fetch specific function entities by their IDs."""
        if not self.neo4j_client:
            return []

        query = """
            MATCH (fn)
            WHERE fn.entityId IN $entityIds
              AND (fn:Function OR fn:Method OR fn:JavaMethod)
            RETURN fn.entityId as entityId, fn.name as name, fn.filePath as filePath,
                   labels(fn)[0] as kind, fn.language as language,
                   fn.signature as signature, fn.startLine as startLine,
                   fn.endLine as endLine, fn.parameters as parameters,
                   fn.returnType as returnType, fn.isAsync as isAsync,
                   fn.isStatic as isStatic, fn.visibility as visibility
        """

        try:
            result = await self.neo4j_client.runTransaction(
                query,
                {"entityIds": entity_ids},
                "READ",
                "EnrichmentService"
            )

            entities = []
            for record in (result.records or []):
                entities.append(FunctionContext(
                    entity_id=record.get("entityId"),
                    entity_name=record.get("name"),
                    file_path=record.get("filePath"),
                    language=record.get("language") or "unknown",
                    kind=record.get("kind"),
                    signature=record.get("signature"),
                    parameters=record.get("parameters") or [],
                    return_type=record.get("returnType"),
                    is_async=record.get("isAsync") or False,
                    is_static=record.get("isStatic") or False,
                    visibility=record.get("visibility") or "public",
                ))
            return entities

        except Exception as e:
            logger.error(f"Failed to fetch function entities by IDs: {e}")
            return []


# Factory function
def create_enrichment_service(
    neo4j_client: Any = None,
    copilot_session: Any = None,
) -> EnrichmentService:
    """Create an enrichment service instance.

    Args:
        neo4j_client: Neo4j client for querying code graph.
        copilot_session: Copilot session for LLM-based generation.

    Returns:
        EnrichmentService instance.
    """
    return EnrichmentService(neo4j_client, copilot_session)
