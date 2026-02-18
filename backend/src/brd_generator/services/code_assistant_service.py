"""Code Assistant Service for answering questions about a codebase."""

from __future__ import annotations

import os
import re
import uuid
from enum import Enum
from typing import Any, Optional

from ..api.chat_models import ChatRequest, ChatResponse, Citation, RelatedEntity
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from ..utils.logger import get_logger

logger = get_logger(__name__)


class QuestionType(str, Enum):
    """Types of questions the assistant can handle."""
    STRUCTURAL = "structural"  # What classes/modules exist?
    FUNCTIONAL = "functional"  # How does X work?
    LOCATIONAL = "locational"  # Where is X defined?
    DEPENDENCY = "dependency"  # What depends on X? What does X depend on?
    PATTERN = "pattern"  # What patterns are used?
    GENERAL = "general"  # General questions


class CodeAssistantService:
    """
    Service for answering natural language questions about a codebase.

    Components:
    1. Query Analyzer - Classifies questions and extracts keywords
    2. Context Retriever - Queries Neo4j and reads files to gather context
    3. Response Generator - Uses LLM to generate answers with citations
    """

    def __init__(
        self,
        neo4j_client: Neo4jMCPClient,
        filesystem_client: FilesystemMCPClient,
        copilot_session: Any = None,
    ):
        """
        Initialize the Code Assistant Service.

        Args:
            neo4j_client: Client for Neo4j code graph queries
            filesystem_client: Client for reading source files
            copilot_session: Optional Copilot SDK session for LLM calls
        """
        self.neo4j_client = neo4j_client
        self.filesystem_client = filesystem_client
        self.copilot_session = copilot_session
        self._copilot_available = copilot_session is not None

        logger.info("CodeAssistantService initialized")
        if self._copilot_available:
            logger.info("Copilot SDK available for response generation")
        else:
            logger.warning("Copilot SDK not available, will use mock responses")

    async def answer_question(
        self,
        repository_id: str,
        request: ChatRequest,
        workspace_root: str,
    ) -> ChatResponse:
        """
        Answer a question about the codebase.

        Args:
            repository_id: ID of the repository to query
            request: Chat request with question
            workspace_root: Root path of the repository

        Returns:
            ChatResponse with answer, citations, and suggestions
        """
        logger.info(f"Processing question for repo {repository_id}: {request.question[:100]}...")

        # Step 1: Analyze the question
        question_type, keywords = self._analyze_question(request.question)
        logger.info(f"Question type: {question_type}, keywords: {keywords}")

        # Step 2: Retrieve relevant context from codebase
        context_items = await self._retrieve_context(
            repository_id=repository_id,
            question_type=question_type,
            keywords=keywords,
            workspace_root=workspace_root,
        )
        logger.info(f"Retrieved {len(context_items)} context items")

        # Step 3: Generate response with citations
        answer, citations, related_entities = await self._generate_response(
            question=request.question,
            question_type=question_type,
            context_items=context_items,
        )

        # Step 4: Generate follow-up suggestions
        follow_ups = self._generate_follow_up_suggestions(
            question=request.question,
            question_type=question_type,
            related_entities=related_entities,
        )

        # Generate conversation ID if not provided
        conversation_id = request.conversation_id or str(uuid.uuid4())

        return ChatResponse(
            answer=answer,
            citations=citations,
            related_entities=related_entities,
            follow_up_suggestions=follow_ups,
            conversation_id=conversation_id,
        )

    def _analyze_question(self, question: str) -> tuple[QuestionType, list[str]]:
        """
        Analyze the question to determine its type and extract keywords.

        Args:
            question: The natural language question

        Returns:
            Tuple of (question_type, keywords)
        """
        question_lower = question.lower()

        # Determine question type based on patterns
        if any(word in question_lower for word in ["what class", "what module", "what component", "list", "show me all", "what entities"]):
            question_type = QuestionType.STRUCTURAL
        elif any(word in question_lower for word in ["how does", "how is", "what happens when", "explain how"]):
            question_type = QuestionType.FUNCTIONAL
        elif any(word in question_lower for word in ["where is", "where are", "find", "locate", "which file"]):
            question_type = QuestionType.LOCATIONAL
        elif any(word in question_lower for word in ["depends on", "dependency", "uses", "calls", "imports", "what calls", "who calls"]):
            question_type = QuestionType.DEPENDENCY
        elif any(word in question_lower for word in ["pattern", "design", "architecture", "structure"]):
            question_type = QuestionType.PATTERN
        else:
            question_type = QuestionType.GENERAL

        # Extract keywords (nouns and identifiers)
        # Remove common question words
        stop_words = {"what", "how", "where", "is", "are", "the", "a", "an", "in", "on", "for", "to", "of", "does", "do", "this", "that", "which", "who", "when"}
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', question)
        keywords = [w for w in words if w.lower() not in stop_words and len(w) > 2]

        # Also look for quoted strings or CamelCase/snake_case identifiers
        quoted = re.findall(r'["\']([^"\']+)["\']', question)
        camel_case = re.findall(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', question)
        snake_case = re.findall(r'\b([a-z]+_[a-z_]+)\b', question)

        keywords.extend(quoted)
        keywords.extend(camel_case)
        keywords.extend(snake_case)

        # Deduplicate and limit
        seen = set()
        unique_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen:
                seen.add(kw_lower)
                unique_keywords.append(kw)

        return question_type, unique_keywords[:10]

    async def _retrieve_context(
        self,
        repository_id: str,
        question_type: QuestionType,
        keywords: list[str],
        workspace_root: str,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant code context based on question type.

        Args:
            repository_id: Repository ID
            question_type: Type of question
            keywords: Extracted keywords
            workspace_root: Repository workspace root

        Returns:
            List of context items with code snippets
        """
        context_items = []

        try:
            # Build and execute Neo4j queries based on question type
            if question_type == QuestionType.STRUCTURAL:
                context_items = await self._query_structural(keywords)
            elif question_type == QuestionType.LOCATIONAL:
                context_items = await self._query_locational(keywords)
            elif question_type == QuestionType.DEPENDENCY:
                context_items = await self._query_dependencies(keywords)
            elif question_type in [QuestionType.FUNCTIONAL, QuestionType.PATTERN, QuestionType.GENERAL]:
                # For these, search by keywords
                context_items = await self._query_by_keywords(keywords)

            # Fetch source code snippets for top results
            context_items = await self._enrich_with_source_code(
                context_items,
                workspace_root,
            )

        except Exception as e:
            logger.error(f"Error retrieving context: {e}")

        return context_items

    async def _query_structural(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Query for structural information (classes, modules, etc.)."""
        items = []

        # Query for classes/entities matching keywords
        for keyword in keywords[:3]:
            query = """
                MATCH (n)
                WHERE (n:Class OR n:Interface OR n:Module OR n:Function OR n:JavaClass OR n:SpringService OR n:SpringController)
                AND toLower(n.name) CONTAINS toLower($keyword)
                RETURN n.name as name, n.filePath as filePath, n.startLine as startLine,
                       n.endLine as endLine, labels(n)[0] as type, n.sourceCode as sourceCode
                LIMIT 10
            """
            result = await self.neo4j_client.query_code_structure(query, {"keyword": keyword})
            for node in result.get("nodes", []):
                items.append({
                    "name": node.get("name", "unknown"),
                    "file_path": node.get("filePath", ""),
                    "line_start": node.get("startLine", 1),
                    "line_end": node.get("endLine", 1),
                    "type": node.get("type", "unknown"),
                    "source_code": node.get("sourceCode", ""),
                })

        # If no keywords, get all major entities
        if not keywords:
            query = """
                MATCH (n)
                WHERE n:Class OR n:Interface OR n:Module OR n:JavaClass OR n:SpringService OR n:SpringController
                RETURN n.name as name, n.filePath as filePath, n.startLine as startLine,
                       n.endLine as endLine, labels(n)[0] as type, n.sourceCode as sourceCode
                LIMIT 20
            """
            result = await self.neo4j_client.query_code_structure(query, {})
            for node in result.get("nodes", []):
                items.append({
                    "name": node.get("name", "unknown"),
                    "file_path": node.get("filePath", ""),
                    "line_start": node.get("startLine", 1),
                    "line_end": node.get("endLine", 1),
                    "type": node.get("type", "unknown"),
                    "source_code": node.get("sourceCode", ""),
                })

        return items

    async def _query_locational(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Query for location of specific entities."""
        items = []

        for keyword in keywords[:5]:
            # Exact name match first
            query = """
                MATCH (n)
                WHERE n.name = $keyword OR toLower(n.name) = toLower($keyword)
                RETURN n.name as name, n.filePath as filePath, n.startLine as startLine,
                       n.endLine as endLine, labels(n)[0] as type, n.sourceCode as sourceCode
                LIMIT 5
            """
            result = await self.neo4j_client.query_code_structure(query, {"keyword": keyword})
            for node in result.get("nodes", []):
                items.append({
                    "name": node.get("name", "unknown"),
                    "file_path": node.get("filePath", ""),
                    "line_start": node.get("startLine", 1),
                    "line_end": node.get("endLine", 1),
                    "type": node.get("type", "unknown"),
                    "source_code": node.get("sourceCode", ""),
                })

            # Partial match if no exact match
            if not items:
                query = """
                    MATCH (n)
                    WHERE toLower(n.name) CONTAINS toLower($keyword)
                    RETURN n.name as name, n.filePath as filePath, n.startLine as startLine,
                           n.endLine as endLine, labels(n)[0] as type, n.sourceCode as sourceCode
                    LIMIT 10
                """
                result = await self.neo4j_client.query_code_structure(query, {"keyword": keyword})
                for node in result.get("nodes", []):
                    items.append({
                        "name": node.get("name", "unknown"),
                        "file_path": node.get("filePath", ""),
                        "line_start": node.get("startLine", 1),
                        "line_end": node.get("endLine", 1),
                        "type": node.get("type", "unknown"),
                        "source_code": node.get("sourceCode", ""),
                    })

        return items

    async def _query_dependencies(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Query for dependency relationships."""
        items = []

        for keyword in keywords[:3]:
            # Find what the entity imports/depends on (outgoing relationships)
            # Using actual Neo4j relationship types from the codebase
            query = """
                MATCH (source)-[r:JAVA_IMPORTS|HAS_DEPENDENCY|DEPENDS_ON_MODULE]->(target)
                WHERE source.name = $keyword OR toLower(source.name) CONTAINS toLower($keyword)
                RETURN source.name as sourceName, type(r) as relationType,
                       target.name as targetName, target.filePath as targetPath,
                       source.filePath as sourcePath, source.startLine as startLine,
                       source.endLine as endLine, source.sourceCode as sourceCode
                LIMIT 15
            """
            result = await self.neo4j_client.query_code_structure(query, {"keyword": keyword})
            for node in result.get("nodes", []):
                items.append({
                    "name": f"{node.get('sourceName', '')} -> {node.get('targetName', '')}",
                    "file_path": node.get("sourcePath", ""),
                    "line_start": node.get("startLine", 1),
                    "line_end": node.get("endLine", 1),
                    "type": f"imports ({node.get('relationType', 'unknown')})",
                    "source_code": node.get("sourceCode", ""),
                    "relation": node.get("relationType", ""),
                    "target": node.get("targetName", ""),
                })

            # Find what imports/depends on this entity (incoming relationships)
            # Note: Import names are fully qualified (e.g., com.example.ClassName)
            # so we check if target.name ends with the keyword or contains it
            query = """
                MATCH (source)-[r:JAVA_IMPORTS|HAS_DEPENDENCY|DEPENDS_ON_MODULE]->(target)
                WHERE target.name = $keyword
                   OR toLower(target.name) CONTAINS toLower($keyword)
                   OR target.name ENDS WITH ('.' + $keyword)
                RETURN source.name as sourceName, type(r) as relationType,
                       target.name as targetName, source.filePath as sourcePath,
                       source.startLine as startLine, source.endLine as endLine,
                       source.sourceCode as sourceCode
                LIMIT 15
            """
            result = await self.neo4j_client.query_code_structure(query, {"keyword": keyword})
            for node in result.get("nodes", []):
                items.append({
                    "name": f"{node.get('sourceName', '')} -> {node.get('targetName', '')}",
                    "file_path": node.get("sourcePath", ""),
                    "line_start": node.get("startLine", 1),
                    "line_end": node.get("endLine", 1),
                    "type": f"imported by ({node.get('relationType', 'unknown')})",
                    "source_code": node.get("sourceCode", ""),
                    "relation": node.get("relationType", ""),
                    "source": node.get("sourceName", ""),
                })

            # Find class-method relationships (what methods a class has)
            query = """
                MATCH (cls)-[r:HAS_METHOD]->(method)
                WHERE cls.name = $keyword OR toLower(cls.name) CONTAINS toLower($keyword)
                RETURN cls.name as sourceName, type(r) as relationType,
                       method.name as targetName, cls.filePath as sourcePath,
                       method.startLine as startLine, method.endLine as endLine,
                       method.sourceCode as sourceCode
                LIMIT 10
            """
            result = await self.neo4j_client.query_code_structure(query, {"keyword": keyword})
            for node in result.get("nodes", []):
                items.append({
                    "name": f"{node.get('sourceName', '')}.{node.get('targetName', '')}",
                    "file_path": node.get("sourcePath", ""),
                    "line_start": node.get("startLine", 1),
                    "line_end": node.get("endLine", 1),
                    "type": f"has method ({node.get('relationType', 'unknown')})",
                    "source_code": node.get("sourceCode", ""),
                    "relation": node.get("relationType", ""),
                    "target": node.get("targetName", ""),
                })

            # Find what class defines/contains this method
            query = """
                MATCH (cls)-[r:HAS_METHOD|DEFINES_CLASS]->(entity)
                WHERE entity.name = $keyword OR toLower(entity.name) CONTAINS toLower($keyword)
                RETURN cls.name as sourceName, type(r) as relationType,
                       entity.name as targetName, cls.filePath as sourcePath,
                       entity.startLine as startLine, entity.endLine as endLine,
                       entity.sourceCode as sourceCode
                LIMIT 10
            """
            result = await self.neo4j_client.query_code_structure(query, {"keyword": keyword})
            for node in result.get("nodes", []):
                items.append({
                    "name": f"{node.get('sourceName', '')} contains {node.get('targetName', '')}",
                    "file_path": node.get("sourcePath", ""),
                    "line_start": node.get("startLine", 1),
                    "line_end": node.get("endLine", 1),
                    "type": f"defined in ({node.get('relationType', 'unknown')})",
                    "source_code": node.get("sourceCode", ""),
                    "relation": node.get("relationType", ""),
                    "source": node.get("sourceName", ""),
                })

        return items

    async def _query_by_keywords(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Generic keyword search across entities."""
        items = []

        for keyword in keywords[:5]:
            query = """
                MATCH (n)
                WHERE toLower(n.name) CONTAINS toLower($keyword)
                   OR toLower(n.filePath) CONTAINS toLower($keyword)
                RETURN n.name as name, n.filePath as filePath, n.startLine as startLine,
                       n.endLine as endLine, labels(n)[0] as type, n.sourceCode as sourceCode
                LIMIT 10
            """
            result = await self.neo4j_client.query_code_structure(query, {"keyword": keyword})
            for node in result.get("nodes", []):
                items.append({
                    "name": node.get("name", "unknown"),
                    "file_path": node.get("filePath", ""),
                    "line_start": node.get("startLine", 1),
                    "line_end": node.get("endLine", 1),
                    "type": node.get("type", "unknown"),
                    "source_code": node.get("sourceCode", ""),
                })

        return items

    async def _enrich_with_source_code(
        self,
        items: list[dict[str, Any]],
        workspace_root: str,
    ) -> list[dict[str, Any]]:
        """Enrich context items with source code if not already present."""
        enriched = []
        seen_paths = set()

        for item in items:
            file_path = item.get("file_path", "")
            if not file_path or file_path in seen_paths:
                # Skip duplicates
                if item.get("source_code"):
                    enriched.append(item)
                continue

            seen_paths.add(file_path)

            # If source code is already present, use it
            if item.get("source_code"):
                enriched.append(item)
                continue

            # Try to read the file
            try:
                # Construct full path
                full_path = file_path
                if not file_path.startswith(workspace_root):
                    full_path = os.path.join(workspace_root, file_path.lstrip("/"))

                # Read the file content
                content = await self.filesystem_client.read_file(full_path)

                if content:
                    # Extract relevant lines
                    lines = content.split("\n")
                    start = max(0, (item.get("line_start", 1) or 1) - 1)
                    end = min(len(lines), (item.get("line_end", start + 20) or start + 20))

                    # Get surrounding context (5 lines before and after)
                    context_start = max(0, start - 5)
                    context_end = min(len(lines), end + 5)

                    snippet = "\n".join(lines[context_start:context_end])
                    item["source_code"] = snippet
                    item["line_start"] = context_start + 1
                    item["line_end"] = context_end

            except Exception as e:
                logger.debug(f"Could not read file {file_path}: {e}")

            enriched.append(item)

        return enriched[:20]  # Limit to top 20 items

    async def _generate_response(
        self,
        question: str,
        question_type: QuestionType,
        context_items: list[dict[str, Any]],
    ) -> tuple[str, list[Citation], list[RelatedEntity]]:
        """
        Generate a response with citations using the LLM.

        Args:
            question: Original question
            question_type: Type of question
            context_items: Retrieved context

        Returns:
            Tuple of (answer, citations, related_entities)
        """
        # Build citations from context
        citations = []
        for i, item in enumerate(context_items[:10], 1):
            citations.append(Citation(
                id=str(i),
                file_path=item.get("file_path", ""),
                line_start=item.get("line_start", 1),
                line_end=item.get("line_end", 1),
                snippet=item.get("source_code", "")[:500] if item.get("source_code") else "",
                entity_name=item.get("name", ""),
                relevance_score=1.0 - (i * 0.05),  # Simple scoring based on order
            ))

        # Extract related entities
        related_entities = []
        seen_names = set()
        for item in context_items:
            name = item.get("name", "")
            if name and name not in seen_names:
                seen_names.add(name)
                related_entities.append(RelatedEntity(
                    name=name,
                    type=item.get("type", "unknown"),
                    file_path=item.get("file_path", ""),
                ))

        related_entities = related_entities[:10]

        # Generate answer
        if self._copilot_available:
            answer = await self._generate_llm_answer(question, question_type, context_items, citations)
        else:
            answer = self._generate_mock_answer(question, question_type, context_items, citations)

        return answer, citations, related_entities

    async def _generate_llm_answer(
        self,
        question: str,
        question_type: QuestionType,
        context_items: list[dict[str, Any]],
        citations: list[Citation],
    ) -> str:
        """Generate answer using LLM with citations."""
        # Build context string for LLM
        context_text = ""
        for i, item in enumerate(context_items[:10], 1):
            context_text += f"\n[{i}] {item.get('type', 'unknown')}: {item.get('name', 'unknown')}\n"
            context_text += f"    File: {item.get('file_path', 'unknown')}\n"
            context_text += f"    Lines: {item.get('line_start', '?')}-{item.get('line_end', '?')}\n"
            if item.get("source_code"):
                snippet = item["source_code"][:300]
                context_text += f"    Code:\n    ```\n{snippet}\n    ```\n"

        prompt = f"""You are a code assistant answering questions about a codebase.

Question: {question}

Question Type: {question_type.value}

Context from codebase:
{context_text}

Instructions:
1. Answer the question based on the provided context
2. Use inline citations like [1], [2], etc. to reference the code snippets
3. Be specific and reference actual file paths and entity names
4. If the context doesn't contain enough information, say so
5. Keep the answer concise but comprehensive

Provide your answer:"""

        try:
            import asyncio

            if hasattr(self.copilot_session, 'send_and_wait'):
                message_options = {"prompt": prompt}
                event = await asyncio.wait_for(
                    self.copilot_session.send_and_wait(message_options, timeout=60),
                    timeout=60,
                )

                if event:
                    return self._extract_content(event)

            # Fallback to basic response if LLM fails
            return self._generate_mock_answer(question, question_type, context_items, citations)

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return self._generate_mock_answer(question, question_type, context_items, citations)

    def _extract_content(self, event: Any) -> str:
        """Extract text content from a session event."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                if hasattr(data, 'message') and hasattr(data.message, 'content'):
                    return str(data.message.content)
                if hasattr(data, 'content'):
                    return str(data.content)
                if hasattr(data, 'text'):
                    return str(data.text)

            if hasattr(event, 'content'):
                return str(event.content)
            if hasattr(event, 'text'):
                return str(event.text)

            return str(event)
        except Exception:
            return ""

    def _generate_mock_answer(
        self,
        question: str,
        question_type: QuestionType,
        context_items: list[dict[str, Any]],
        citations: list[Citation],
    ) -> str:
        """Generate a mock answer when LLM is not available."""
        if not context_items:
            return "I couldn't find relevant code for your question. Please try rephrasing or asking about different entities."

        # Build answer based on question type
        if question_type == QuestionType.STRUCTURAL:
            entity_list = []
            for i, item in enumerate(context_items[:10], 1):
                entity_list.append(f"- **{item.get('name', 'unknown')}** ({item.get('type', 'unknown')}) - defined in `{item.get('file_path', 'unknown')}` [**{i}**]")
            return f"Based on the codebase analysis, here are the relevant entities:\n\n" + "\n".join(entity_list)

        elif question_type == QuestionType.LOCATIONAL:
            locations = []
            for i, item in enumerate(context_items[:5], 1):
                locations.append(f"- **{item.get('name', 'unknown')}** is defined in `{item.get('file_path', 'unknown')}` at lines {item.get('line_start', '?')}-{item.get('line_end', '?')} [**{i}**]")
            return f"I found the following locations:\n\n" + "\n".join(locations)

        elif question_type == QuestionType.DEPENDENCY:
            deps = []
            for i, item in enumerate(context_items[:10], 1):
                if item.get("relation"):
                    deps.append(f"- {item.get('name', '')} ({item.get('relation', '')}) [**{i}**]")
                else:
                    deps.append(f"- **{item.get('name', 'unknown')}** in `{item.get('file_path', 'unknown')}` [**{i}**]")
            return f"Here are the dependency relationships I found:\n\n" + "\n".join(deps)

        else:
            # General response
            items = []
            for i, item in enumerate(context_items[:5], 1):
                snippet_preview = ""
                if item.get("source_code"):
                    snippet_preview = f"\n  ```\n  {item['source_code'][:150]}...\n  ```"
                items.append(f"**{item.get('name', 'unknown')}** ({item.get('type', 'unknown')}) in `{item.get('file_path', 'unknown')}` [**{i}**]{snippet_preview}")

            return f"Based on the codebase, I found the following relevant code:\n\n" + "\n\n".join(items)

    def _generate_follow_up_suggestions(
        self,
        question: str,
        question_type: QuestionType,
        related_entities: list[RelatedEntity],
    ) -> list[str]:
        """Generate follow-up question suggestions."""
        suggestions = []

        # Add entity-specific suggestions
        for entity in related_entities[:3]:
            if entity.type in ["Class", "JavaClass", "SpringService", "SpringController"]:
                suggestions.append(f"What methods does {entity.name} have?")
                suggestions.append(f"What depends on {entity.name}?")
            elif entity.type in ["Function", "Method"]:
                suggestions.append(f"What calls {entity.name}?")
                suggestions.append(f"How is {entity.name} implemented?")

        # Add generic follow-ups based on question type
        if question_type == QuestionType.STRUCTURAL:
            suggestions.append("What are the main dependencies between these components?")
            suggestions.append("Show me the class hierarchy")
        elif question_type == QuestionType.DEPENDENCY:
            suggestions.append("What patterns are used in this codebase?")
            suggestions.append("Which components are most connected?")
        elif question_type == QuestionType.LOCATIONAL:
            suggestions.append("What other files are related to this?")

        # Deduplicate and limit
        seen = set()
        unique = []
        for s in suggestions:
            if s.lower() not in seen:
                seen.add(s.lower())
                unique.append(s)

        return unique[:5]
