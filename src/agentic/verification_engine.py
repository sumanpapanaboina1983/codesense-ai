"""
Verification engine for zero-hallucination enforcement.
Every claim must be traceable to graph or source code.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from src.core.constants import (
    CONFIDENCE_CODE_ONLY,
    CONFIDENCE_GRAPH_ONLY,
    CONFIDENCE_HIGH,
    CONFIDENCE_INDIRECT,
    CONFIDENCE_NONE,
    FactType,
    VerificationStatus,
    VERDICT_HALLUCINATION,
    VERDICT_PARTIAL,
    VERDICT_VERIFIED,
)
from src.core.logging import get_logger
from src.mcp.filesystem_client import FilesystemMCPClient
from src.mcp.neo4j_client import Neo4jMCPClient

logger = get_logger(__name__)


@dataclass
class VerifiedFact:
    """A single verified fact."""

    fact: str
    fact_type: FactType
    verified: bool
    confidence: float
    graph_evidence: Optional[dict[str, Any]] = None
    code_evidence: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact": self.fact,
            "type": self.fact_type.value,
            "verified": self.verified,
            "confidence": self.confidence,
            "evidence": {
                "graph": self.graph_evidence,
                "code": self.code_evidence,
            },
        }


@dataclass
class VerificationResult:
    """Result of verification."""

    verified: bool
    confidence: float
    evidence: list[str] = field(default_factory=list)
    hallucination_flags: list[str] = field(default_factory=list)
    graph_support: dict[str, Any] = field(default_factory=dict)
    code_support: dict[str, Any] = field(default_factory=dict)
    facts: list[VerifiedFact] = field(default_factory=list)
    verdict: str = VERDICT_VERIFIED

    @property
    def status(self) -> VerificationStatus:
        """Get verification status enum."""
        if self.verdict == VERDICT_VERIFIED:
            return VerificationStatus.VERIFIED
        elif self.verdict == VERDICT_PARTIAL:
            return VerificationStatus.PARTIAL
        return VerificationStatus.UNVERIFIED


@dataclass
class ExtractedFact:
    """A fact extracted from a claim."""

    text: str
    fact_type: FactType
    entity: Optional[str] = None
    entity_type: Optional[str] = None
    target: Optional[str] = None
    relationship: Optional[str] = None


class FactExtractor:
    """
    Extracts verifiable facts from natural language claims.
    """

    # Patterns for entity detection
    CAMEL_CASE_PATTERN = re.compile(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b')

    # Class suffixes
    CLASS_SUFFIXES = ('Service', 'Controller', 'Repository', 'Manager', 'Handler', 'Factory')
    COMPONENT_SUFFIXES = ('Component', 'Module', 'Plugin')

    def extract_facts(self, claim: str) -> list[ExtractedFact]:
        """
        Extract verifiable facts from a claim.

        Args:
            claim: Natural language claim

        Returns:
            List of extracted facts
        """
        facts = []

        # Extract entity existence facts
        entities = self._extract_entities(claim)
        for entity in entities:
            facts.append(ExtractedFact(
                text=f"{entity['name']} exists",
                fact_type=FactType.ENTITY_EXISTS,
                entity=entity['name'],
                entity_type=entity['type'],
            ))

        # Extract relationships
        relationships = self._extract_relationships(claim)
        for rel in relationships:
            facts.append(ExtractedFact(
                text=f"{rel['source']} {rel['type']} {rel['target']}",
                fact_type=FactType(rel['type']),
                entity=rel['source'],
                target=rel['target'],
                relationship=rel['type'],
            ))

        # Extract capabilities
        capabilities = self._extract_capabilities(claim)
        for cap in capabilities:
            facts.append(ExtractedFact(
                text=f"{cap['entity']} has capability: {cap['capability']}",
                fact_type=FactType.HAS_CAPABILITY,
                entity=cap['entity'],
            ))

        return facts

    def _extract_entities(self, text: str) -> list[dict[str, str]]:
        """Extract entity names from text."""
        entities = []

        # Find CamelCase words (likely class/component names)
        matches = self.CAMEL_CASE_PATTERN.findall(text)

        for match in matches:
            if match.endswith(self.CLASS_SUFFIXES):
                entity_type = 'Class'
            elif match.endswith(self.COMPONENT_SUFFIXES):
                entity_type = 'Component'
            else:
                entity_type = 'Unknown'

            entities.append({"name": match, "type": entity_type})

        return entities

    def _extract_relationships(self, text: str) -> list[dict[str, str]]:
        """Extract relationships between entities."""
        relationships = []
        text_lower = text.lower()

        # Pattern: "X calls Y"
        if "calls" in text_lower:
            match = re.search(r'(\w+)\s+calls\s+(\w+)', text, re.IGNORECASE)
            if match:
                relationships.append({
                    "type": "calls",
                    "source": match.group(1),
                    "target": match.group(2),
                })

        # Pattern: "X depends on Y"
        if "depends on" in text_lower:
            match = re.search(r'(\w+)\s+depends\s+on\s+(\w+)', text, re.IGNORECASE)
            if match:
                relationships.append({
                    "type": "depends_on",
                    "source": match.group(1),
                    "target": match.group(2),
                })

        # Pattern: "X extends Y"
        if "extends" in text_lower:
            match = re.search(r'(\w+)\s+extends\s+(\w+)', text, re.IGNORECASE)
            if match:
                relationships.append({
                    "type": "extends",
                    "source": match.group(1),
                    "target": match.group(2),
                })

        # Pattern: "X implements Y"
        if "implements" in text_lower:
            match = re.search(r'(\w+)\s+implements\s+(\w+)', text, re.IGNORECASE)
            if match:
                relationships.append({
                    "type": "implements",
                    "source": match.group(1),
                    "target": match.group(2),
                })

        return relationships

    def _extract_capabilities(self, text: str) -> list[dict[str, str]]:
        """Extract capabilities/behaviors."""
        capabilities = []

        # Verbs indicating behavior
        verbs = ['authenticates', 'validates', 'processes', 'handles', 'manages',
                 'creates', 'updates', 'deletes', 'retrieves', 'stores']

        text_lower = text.lower()

        for verb in verbs:
            if verb in text_lower:
                # Find entity before verb
                match = re.search(rf'(\w+)\s+{verb}', text, re.IGNORECASE)
                if match:
                    capabilities.append({
                        "entity": match.group(1),
                        "capability": verb,
                    })

        return capabilities


class VerificationEngine:
    """
    Zero-hallucination enforcement engine.
    Verifies claims against the code graph and source files.
    """

    def __init__(
        self,
        neo4j_client: Neo4jMCPClient,
        filesystem_client: FilesystemMCPClient,
        confidence_threshold: float = 0.7,
    ) -> None:
        """
        Initialize the verification engine.

        Args:
            neo4j_client: Neo4j MCP client
            filesystem_client: Filesystem MCP client
            confidence_threshold: Minimum confidence for verified status
        """
        self.neo4j = neo4j_client
        self.filesystem = filesystem_client
        self.confidence_threshold = confidence_threshold
        self.fact_extractor = FactExtractor()

    async def verify_claim(
        self,
        claim: str,
        context: Optional[dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Verify a single claim against the codebase.

        Args:
            claim: The claim to verify
            context: Optional context for verification

        Returns:
            VerificationResult with evidence and confidence
        """
        logger.debug("Verifying claim", claim=claim[:50])

        # Extract verifiable facts
        facts = self.fact_extractor.extract_facts(claim)

        if not facts:
            logger.warning("No verifiable facts extracted", claim=claim[:50])
            return VerificationResult(
                verified=False,
                confidence=CONFIDENCE_INDIRECT,
                hallucination_flags=["No verifiable facts found in claim"],
                verdict=VERDICT_PARTIAL,
            )

        # Verify each fact
        verified_facts = []
        evidence = []
        hallucination_flags = []

        for fact in facts:
            verified_fact = await self._verify_fact(fact)
            verified_facts.append(verified_fact)

            if verified_fact.verified:
                if verified_fact.graph_evidence:
                    evidence.append(f"Graph: {verified_fact.graph_evidence}")
                if verified_fact.code_evidence:
                    evidence.append(f"Code: {verified_fact.code_evidence}")
            else:
                hallucination_flags.append(f"Unverified: {fact.text}")

        # Calculate overall confidence
        if verified_facts:
            avg_confidence = sum(f.confidence for f in verified_facts) / len(verified_facts)
        else:
            avg_confidence = CONFIDENCE_NONE

        # Determine verdict
        verified_count = sum(1 for f in verified_facts if f.verified)
        if verified_count == len(verified_facts):
            verdict = VERDICT_VERIFIED
        elif verified_count > 0:
            verdict = VERDICT_PARTIAL
        else:
            verdict = VERDICT_HALLUCINATION

        return VerificationResult(
            verified=avg_confidence >= self.confidence_threshold,
            confidence=avg_confidence,
            evidence=evidence,
            hallucination_flags=hallucination_flags,
            facts=verified_facts,
            verdict=verdict,
        )

    async def _verify_fact(self, fact: ExtractedFact) -> VerifiedFact:
        """Verify a single extracted fact."""
        graph_result = await self._verify_against_graph(fact)
        code_result = await self._verify_against_code(fact)

        # Calculate confidence based on evidence
        confidence = self._calculate_confidence(graph_result, code_result)
        verified = confidence >= self.confidence_threshold

        return VerifiedFact(
            fact=fact.text,
            fact_type=fact.fact_type,
            verified=verified,
            confidence=confidence,
            graph_evidence=graph_result if graph_result.get("found") else None,
            code_evidence=code_result if code_result.get("found") else None,
        )

    async def _verify_against_graph(self, fact: ExtractedFact) -> dict[str, Any]:
        """Verify a fact against the Neo4j graph."""
        try:
            if fact.fact_type == FactType.ENTITY_EXISTS:
                result = await self.neo4j.verify_entity_exists(
                    fact.entity,
                    fact.entity_type or "Class",
                )
                return {"found": result, "source": "graph", "entity": fact.entity}

            elif fact.fact_type in (FactType.CALLS, FactType.DEPENDS_ON,
                                    FactType.EXTENDS, FactType.IMPLEMENTS):
                result = await self.neo4j.verify_relationship_exists(
                    fact.entity,
                    fact.target,
                    fact.relationship.upper(),
                )
                return {
                    "found": result,
                    "source": "graph",
                    "relationship": f"{fact.entity}->{fact.target}",
                }

            return {"found": False, "reason": "Unsupported fact type for graph"}

        except Exception as e:
            logger.error("Graph verification failed", fact=fact.text, error=str(e))
            return {"found": False, "error": str(e)}

    async def _verify_against_code(self, fact: ExtractedFact) -> dict[str, Any]:
        """Verify a fact against source code."""
        try:
            if fact.fact_type == FactType.ENTITY_EXISTS and fact.entity:
                # Try to find files containing the entity
                patterns = [
                    f"**/*{fact.entity}*.java",
                    f"**/*{fact.entity}*.py",
                    f"**/*{fact.entity}*.ts",
                ]

                for pattern in patterns:
                    files = await self.filesystem.find_files(pattern)
                    if files:
                        # Read the first matching file
                        content = await self.filesystem.read_file(files[0])
                        if fact.entity in content.content:
                            return {
                                "found": True,
                                "source": "code",
                                "file": files[0],
                            }

                return {"found": False, "reason": "Entity not found in code"}

            elif fact.fact_type == FactType.HAS_CAPABILITY and fact.entity:
                # Search for capability keywords in files
                files = await self.filesystem.find_files(f"**/*{fact.entity}*.*")
                for file_path in files[:5]:  # Check first 5 files
                    try:
                        content = await self.filesystem.read_file(file_path)
                        # Simple capability check
                        if any(kw in content.content.lower() for kw in
                               ['authenticate', 'validate', 'process', 'handle']):
                            return {
                                "found": True,
                                "source": "code",
                                "file": file_path,
                            }
                    except Exception:
                        continue

                return {"found": False, "reason": "Capability not found in code"}

            return {"found": False, "reason": "Unsupported fact type for code"}

        except Exception as e:
            logger.error("Code verification failed", fact=fact.text, error=str(e))
            return {"found": False, "error": str(e)}

    def _calculate_confidence(
        self,
        graph_result: dict[str, Any],
        code_result: dict[str, Any],
    ) -> float:
        """Calculate confidence from verification results."""
        graph_found = graph_result.get("found", False)
        code_found = code_result.get("found", False)

        if graph_found and code_found:
            return CONFIDENCE_HIGH
        elif code_found:
            return CONFIDENCE_CODE_ONLY
        elif graph_found:
            return CONFIDENCE_GRAPH_ONLY
        else:
            return CONFIDENCE_NONE

    async def verify_document(
        self,
        document: dict[str, Any],
        doc_type: str,
    ) -> VerificationResult:
        """
        Verify an entire document.

        Args:
            document: Document content
            doc_type: Type of document (brd, epic, backlog)

        Returns:
            VerificationResult for the entire document
        """
        content = document.get("content", "")
        if isinstance(content, dict):
            content = str(content)

        # Split into claims (sentences or bullet points)
        claims = self._split_into_claims(content)

        all_evidence = []
        all_flags = []
        all_facts = []
        total_confidence = 0.0

        for claim in claims:
            result = await self.verify_claim(claim)
            all_evidence.extend(result.evidence)
            all_flags.extend(result.hallucination_flags)
            all_facts.extend(result.facts)
            total_confidence += result.confidence

        avg_confidence = total_confidence / len(claims) if claims else 0.0

        # Determine overall verdict
        if avg_confidence >= self.confidence_threshold and not all_flags:
            verdict = VERDICT_VERIFIED
        elif avg_confidence >= self.confidence_threshold * 0.5:
            verdict = VERDICT_PARTIAL
        else:
            verdict = VERDICT_HALLUCINATION

        return VerificationResult(
            verified=avg_confidence >= self.confidence_threshold,
            confidence=avg_confidence,
            evidence=all_evidence,
            hallucination_flags=all_flags,
            facts=all_facts,
            verdict=verdict,
        )

    def _split_into_claims(self, content: str) -> list[str]:
        """Split content into individual claims."""
        claims = []

        # Split by sentences
        sentences = re.split(r'[.!?]\s+', content)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20:  # Ignore very short fragments
                claims.append(sentence)

        # Also extract bullet points
        bullet_points = re.findall(r'^[-*•]\s*(.+)$', content, re.MULTILINE)
        claims.extend(bullet_points)

        return claims

    def detect_hallucinations(
        self,
        claim: str,
        verification: VerificationResult,
    ) -> list[str]:
        """
        Detect hallucinations in a claim based on verification.

        Args:
            claim: The original claim
            verification: Verification result

        Returns:
            List of hallucination flags
        """
        flags = []

        if not verification.verified:
            flags.append(f"Unverified claim: {claim[:100]}")

        if verification.confidence < self.confidence_threshold:
            flags.append(f"Low confidence ({verification.confidence:.2f}): {claim[:100]}")

        if not verification.evidence:
            flags.append(f"No supporting evidence: {claim[:100]}")

        return flags
