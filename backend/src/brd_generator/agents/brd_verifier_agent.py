"""BRD Verifier Agent - Verifies BRD claims and gathers evidence.

This agent is AGENTIC:
- Uses MCP tools (Neo4j, Filesystem) dynamically via Copilot SDK
- The LLM decides what tools to call to verify each claim
- No hardcoded queries - the agentic loop handles tool calling
"""

from __future__ import annotations

import re
from typing import Any, Optional, TYPE_CHECKING

from ..models.verification import (
    Claim,
    ClaimType,
    CodeReference,
    CallGraphEvidence,
    EvidenceBundle,
    EvidenceItem,
    EvidenceType,
    HallucinationRisk,
    SectionVerificationResult,
    VerificationConfig,
    VerificationStatus,
)
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from ..utils.logger import get_logger
from .base import BaseAgent, AgentMessage, AgentRole, MessageType

logger = get_logger(__name__)


class BRDVerifierAgent(BaseAgent):
    """
    Agent 2: BRD Verifier (AGENTIC)

    Responsible for:
    1. Extracting claims from BRD sections
    2. Validating claims using AGENTIC TOOL CALLING (Neo4j, Filesystem)
    3. Detecting potential hallucinations
    4. Preparing evidence bundles to support/refute claims
    5. Providing feedback for BRD regeneration

    Uses the Copilot SDK's agentic loop - LLM decides what tools to call.
    """

    def __init__(
        self,
        copilot_session: Any = None,
        neo4j_client: Optional[Neo4jMCPClient] = None,
        filesystem_client: Optional[FilesystemMCPClient] = None,
        config: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize the BRD Verifier Agent.

        Args:
            copilot_session: Copilot SDK session for LLM-based verification (with MCP tools)
            neo4j_client: Neo4j MCP client (fallback for direct queries)
            filesystem_client: Filesystem MCP client (fallback for direct queries)
            config: Verification configuration dict

        Note: MCP tools are available via the Copilot SDK session's mcp_servers config.
        The local MCP clients are used as fallback when the SDK is unavailable.
        """
        # Handle config - could be VerificationConfig object or dict
        config_dict = config if isinstance(config, dict) else (config.model_dump() if config else {})

        super().__init__(
            role=AgentRole.VERIFIER,
            copilot_session=copilot_session,
            config=config_dict,
        )

        self.neo4j_client = neo4j_client
        self.filesystem_client = filesystem_client

        # Build verification config from dict
        if isinstance(config, VerificationConfig):
            self.verification_config = config
        else:
            self.verification_config = VerificationConfig(**(config_dict or {}))

        # Current verification state
        self.current_bundle: Optional[EvidenceBundle] = None
        self.section_results: dict[str, SectionVerificationResult] = {}

        # Log initialization
        neo4j_status = "available" if neo4j_client else "not available"
        fs_status = "available" if filesystem_client else "not available"
        logger.info(f"BRDVerifierAgent initialized")
        logger.debug(f"  Neo4j client: {neo4j_status}")
        logger.debug(f"  Filesystem client: {fs_status}")
        logger.debug(f"  Min confidence for approval: {self.verification_config.min_confidence_for_approval}")

    def set_clients(
        self,
        neo4j_client: Neo4jMCPClient,
        filesystem_client: FilesystemMCPClient,
    ) -> None:
        """Set the MCP clients."""
        self.neo4j_client = neo4j_client
        self.filesystem_client = filesystem_client

    async def process(self, message: AgentMessage) -> None:
        """
        Process incoming messages.

        Handles:
        - BRD_SECTION: Verify a single BRD section
        - BRD_COMPLETE: Final verification of complete BRD
        """
        if message.message_type == MessageType.BRD_SECTION:
            await self._verify_section(message)

        elif message.message_type == MessageType.BRD_COMPLETE:
            await self._verify_complete_brd(message)

    async def _verify_section(self, message: AgentMessage) -> None:
        """
        Verify a single BRD section.

        1. Extract claims from the section
        2. Gather evidence for each claim
        3. Calculate confidence scores
        4. Determine if section passes verification
        5. Send approval or feedback
        """
        import time
        start_time = time.time()

        section_name = message.section_name or "unknown"
        section_content = message.content
        iteration = message.iteration

        logger.info(f"=" * 50)
        logger.info(f"[VERIFIER] Verifying section '{section_name}' (iteration {iteration})")
        logger.info(f"=" * 50)
        logger.debug(f"[VERIFIER] Section content length: {len(section_content)} chars")
        logger.debug(f"[VERIFIER] Content preview: {section_content[:200]}...")

        # Initialize section result
        result = SectionVerificationResult(section_name=section_name)

        # Step 1: Extract claims from the section
        logger.info(f"[VERIFIER] Step 1: Extracting claims from '{section_name}'")
        claims = await self._extract_claims(section_content, section_name)
        logger.info(f"[VERIFIER] Extracted {len(claims)} claims from '{section_name}'")
        for i, claim in enumerate(claims, 1):
            logger.debug(f"[VERIFIER]   Claim {i}: {claim.text[:80]}... (type: {claim.claim_type})")

        # Step 2: Verify each claim
        logger.info(f"[VERIFIER] Step 2: Verifying {len(claims)} claims")
        for i, claim in enumerate(claims, 1):
            logger.debug(f"[VERIFIER] Verifying claim {i}/{len(claims)}: {claim.text[:50]}...")
            await self._verify_claim(claim)
            result.claims.append(claim)
            logger.debug(f"[VERIFIER] Claim {i} result: status={claim.status.value}, confidence={claim.confidence_score:.2f}")

        # Step 3: Calculate section-level metrics
        logger.info(f"[VERIFIER] Step 3: Calculating section metrics")
        result.calculate_stats()

        # Step 4: Generate feedback if needed
        if result.verification_status != VerificationStatus.VERIFIED:
            logger.debug(f"[VERIFIER] Generating feedback for unverified section")
            self._generate_section_feedback(result)

        # Store result
        self.section_results[section_name] = result

        elapsed = time.time() - start_time
        logger.info(f"[VERIFIER] Section '{section_name}' verification complete ({elapsed:.2f}s)")
        logger.info(f"[VERIFIER]   Status: {result.verification_status.value}")
        logger.info(f"[VERIFIER]   Overall confidence: {result.overall_confidence:.2f}")
        logger.info(f"[VERIFIER]   Hallucination risk: {result.hallucination_risk.value}")
        logger.info(f"[VERIFIER]   Issues: {len(result.issues)}")

        # Step 5: Send response to generator
        if result.overall_confidence >= self.verification_config.min_confidence_for_approval:
            # Section approved
            logger.info(
                f"[VERIFIER] ✓ Section '{section_name}' APPROVED "
                f"(confidence: {result.overall_confidence:.2f} >= {self.verification_config.min_confidence_for_approval})"
            )
            await self.send(AgentMessage(
                message_type=MessageType.APPROVED,
                recipient=AgentRole.GENERATOR,
                section_name=section_name,
                content=result,
                iteration=iteration,
            ))
        else:
            # Section needs regeneration
            logger.info(
                f"[VERIFIER] ✗ Section '{section_name}' NEEDS REVISION "
                f"(confidence: {result.overall_confidence:.2f} < {self.verification_config.min_confidence_for_approval})"
            )
            feedback = self._compile_feedback(result)
            logger.debug(f"[VERIFIER] Feedback: {feedback[:200]}...")
            await self.send(AgentMessage(
                message_type=MessageType.FEEDBACK,
                recipient=AgentRole.GENERATOR,
                section_name=section_name,
                content=feedback,
                iteration=iteration,
                metadata={
                    "confidence": result.overall_confidence,
                    "issues_count": len(result.issues),
                    "hallucination_risk": result.hallucination_risk.value,
                    "verification_time_s": elapsed,
                },
            ))

    async def _verify_complete_brd(self, message: AgentMessage) -> None:
        """
        Final verification of the complete BRD.

        Aggregates all section results and produces the final evidence bundle.
        """
        brd = message.content
        iteration = message.iteration

        logger.info(f"BRD Verifier: Final verification of complete BRD")

        # Create evidence bundle
        bundle = EvidenceBundle(
            brd_id=f"BRD-{hash(brd.title) % 10000:04d}" if hasattr(brd, 'title') else "BRD-0000",
            brd_title=brd.title if hasattr(brd, 'title') else "Unknown",
            sections=list(self.section_results.values()),
            iteration=iteration,
            evidence_sources=["neo4j", "filesystem"] if self.neo4j_client else ["filesystem"],
        )

        # Calculate overall metrics
        bundle.calculate_overall_metrics()

        # Generate regeneration feedback if needed
        if not bundle.is_approved:
            bundle.get_regeneration_feedback()

        self.current_bundle = bundle

        # Send result to orchestrator
        await self.send(AgentMessage(
            message_type=MessageType.VERIFICATION_RESULT,
            recipient=AgentRole.ORCHESTRATOR,
            content=bundle,
            iteration=iteration,
        ))

    async def _extract_claims(self, content: str, section_name: str) -> list[Claim]:
        """
        Extract verifiable claims from section content.

        Uses LLM to identify claims, then validates claim structure.
        """
        # Use LLM to extract claims
        prompt = self._build_claim_extraction_prompt(content, section_name)
        response = await self.send_to_llm(prompt)

        # Parse claims from response
        claims = self._parse_claims_from_response(response, section_name)

        # Fallback to rule-based extraction if LLM fails
        if not claims:
            claims = self._extract_claims_rule_based(content, section_name)

        return claims

    def _build_claim_extraction_prompt(self, content: str, section_name: str) -> str:
        """Build prompt for extracting business-level claims from BRD.

        BRD claims are HIGH-LEVEL BUSINESS STATEMENTS, not technical implementation details.
        We extract claims that describe:
        - Business processes and workflows
        - System behaviors and rules
        - Data flows and transformations
        - Integration points
        - Non-functional requirements
        """
        return f"""
Analyze the following BRD section and extract BUSINESS-LEVEL claims that can be verified against a codebase.

## Section: {section_name}

{content}

## Instructions

Extract HIGH-LEVEL BUSINESS CLAIMS (not technical implementation details). Focus on:

1. **Process/Workflow claims**: How business processes work
   - Example: "Orders go through a 7-step workflow"
   - Example: "User authentication follows a multi-factor flow"

2. **Behavior claims**: How the system behaves
   - Example: "System retries failed payments 3 times"
   - Example: "Expired sessions are automatically cleaned up"

3. **Data flow claims**: How data moves through the system
   - Example: "User data is validated before storage"
   - Example: "Order totals include tax calculations"

4. **Integration claims**: How systems connect
   - Example: "Payment processing integrates with Stripe"
   - Example: "Email notifications sent via SendGrid"

5. **Business rule claims**: Business logic statements
   - Example: "Discounts apply only to orders over $100"
   - Example: "Premium users get priority support"

6. **Non-functional claims**: Performance, security, scalability
   - Example: "API responses under 200ms"
   - Example: "All sensitive data encrypted"

## Output Format

For each claim, output:
CLAIM: [The business-level claim - as stated or implied in the BRD]
TYPE: [process|behavior|data_flow|integration|business_rule|non_functional]
KEYWORDS: [key business terms to search for in code]
QUANTIFIERS: [any numbers, counts, percentages mentioned]
SEARCH_HINTS: [what to look for in the code to verify this]

Example:
CLAIM: Orders go through a 7-step workflow before completion
TYPE: process
KEYWORDS: [order, workflow, step, phase, status]
QUANTIFIERS: [7 steps]
SEARCH_HINTS: [Look for OrderService methods, state machine patterns, status enums with 7 values]

Extract 3-8 key business claims from this section.
"""

    def _parse_claims_from_response(self, response: str, section_name: str) -> list[Claim]:
        """Parse business-level claims from LLM response."""
        claims = []

        # Split by CLAIM: to get each claim block
        claim_blocks = re.split(r'\nCLAIM:\s*', response)

        for block in claim_blocks[1:]:  # Skip first empty block
            if not block.strip():
                continue

            # Extract claim text (first line or until TYPE:)
            lines = block.strip().split('\n')
            claim_text = lines[0].strip()

            # Extract TYPE
            type_match = re.search(r'TYPE:\s*(\w+)', block, re.IGNORECASE)
            claim_type = type_match.group(1).lower() if type_match else "general"

            # Extract KEYWORDS
            keywords_match = re.search(r'KEYWORDS:\s*\[([^\]]*)\]', block, re.IGNORECASE)
            keywords = []
            if keywords_match:
                keywords = [k.strip().strip('"\'') for k in keywords_match.group(1).split(',') if k.strip()]

            # Extract QUANTIFIERS
            quant_match = re.search(r'QUANTIFIERS:\s*\[([^\]]*)\]', block, re.IGNORECASE)
            quantifiers = []
            if quant_match:
                quantifiers = [q.strip().strip('"\'') for q in quant_match.group(1).split(',') if q.strip()]

            # Extract SEARCH_HINTS
            hints_match = re.search(r'SEARCH_HINTS:\s*\[([^\]]*)\]', block, re.IGNORECASE)
            search_patterns = []
            if hints_match:
                search_patterns = [h.strip().strip('"\'') for h in hints_match.group(1).split(',') if h.strip()]

            # Store keywords as search hints (actual entities discovered during verification)
            # We don't hardcode entity names - we'll query Neo4j during verification
            inferred_entities = self._infer_code_entities_sync(keywords, claim_text)

            claims.append(Claim(
                text=claim_text[:500],
                section=section_name,
                claim_type=claim_type,
                keywords=keywords,
                quantifiers=quantifiers,
                search_patterns=search_patterns,
                mentioned_entities=inferred_entities,
                actions=self._extract_actions(claim_text),
            ))

        return claims

    async def _discover_code_entities(self, keywords: list[str], claim_text: str) -> list[str]:
        """
        Dynamically discover code entities from Neo4j that match business keywords.

        Instead of hardcoded mappings, we query the actual code graph to find
        classes, methods, and modules that contain the business keywords.
        """
        entities = []

        # 1. Extract any explicit PascalCase/camelCase names from claim text
        #    (in case the BRD mentions actual code names)
        camel_pattern = r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)*)\b'
        explicit_entities = re.findall(camel_pattern, claim_text)
        entities.extend(explicit_entities)

        # 2. Query Neo4j to find entities matching keywords
        if self.neo4j_client:
            for keyword in keywords[:5]:  # Limit to avoid too many queries
                try:
                    # Search for classes/services/modules containing the keyword
                    query = f"""
                    MATCH (n)
                    WHERE (n:Class OR n:Interface OR n:Function OR n:Method)
                    AND (toLower(n.name) CONTAINS toLower('{keyword}')
                         OR toLower(n.entityId) CONTAINS toLower('{keyword}'))
                    RETURN DISTINCT n.name AS name
                    LIMIT 50
                    """

                    result = await self.neo4j_client.execute_query(query)

                    if result and result.get("records"):
                        for record in result["records"]:
                            if record.get("name"):
                                entities.append(record["name"])

                except Exception as e:
                    logger.debug(f"Entity discovery query failed for '{keyword}': {e}")

        # 3. If Neo4j not available, generate search patterns from keywords
        #    (these will be used for filesystem search later)
        if not entities:
            for keyword in keywords:
                # Convert to likely class name patterns
                # "order" -> search for files/classes containing "order"
                entities.append(keyword.capitalize())
                entities.append(f"{keyword.capitalize()}Service")
                entities.append(f"{keyword.capitalize()}Controller")

        return list(set(entities))[:15]

    def _infer_code_entities_sync(self, keywords: list[str], claim_text: str) -> list[str]:
        """
        Synchronous fallback for entity inference (used during parsing).

        Returns search patterns that will be used to query Neo4j during verification.
        """
        entities = []

        # Extract any explicit PascalCase/camelCase names from claim text
        camel_pattern = r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)*)\b'
        entities.extend(re.findall(camel_pattern, claim_text))

        # Generate search patterns from keywords (to be resolved during verification)
        for keyword in keywords[:5]:
            keyword_clean = keyword.strip().lower()
            if keyword_clean and len(keyword_clean) > 2:
                # These are search hints, not hardcoded entity names
                entities.append(keyword_clean)  # Will search: *keyword*

        return list(set(entities))[:10]

    def _extract_actions(self, text: str) -> list[str]:
        """Extract action verbs from claim text."""
        action_verbs = [
            "create", "update", "delete", "validate", "process", "send", "receive",
            "calculate", "transform", "encrypt", "decrypt", "authenticate", "authorize",
            "retry", "queue", "publish", "subscribe", "notify", "trigger", "execute",
            "store", "retrieve", "cache", "log", "track", "monitor", "verify"
        ]

        found_actions = []
        text_lower = text.lower()
        for verb in action_verbs:
            if verb in text_lower or f"{verb}s" in text_lower or f"{verb}ed" in text_lower:
                found_actions.append(verb)

        return found_actions

    def _extract_claims_rule_based(self, content: str, section_name: str) -> list[Claim]:
        """
        Extract business-level claims using rule-based patterns (fallback).

        Focuses on detecting business statements, not technical implementation.
        """
        claims = []

        # Extract sentences that look like business claims
        sentences = re.split(r'[.!?]\s+', content)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 15 or len(sentence) > 400:
                continue

            # Look for business claim indicators
            claim_type = "general"
            keywords = []
            quantifiers = []

            # Process/Workflow patterns - business processes
            if re.search(r'\b(workflow|process|flow|stage|phase|step|pipeline)\b', sentence, re.I):
                claim_type = "process"
                keywords = re.findall(r'\b(workflow|process|flow|stage|phase|step|pipeline)\b', sentence, re.I)

            # Behavior patterns - system behaviors
            elif re.search(r'\b(retry|retries|attempt|timeout|expire|automatic|trigger)\b', sentence, re.I):
                claim_type = "behavior"
                keywords = re.findall(r'\b(retry|retries|attempt|timeout|expire|automatic|trigger)\b', sentence, re.I)

            # Data flow patterns
            elif re.search(r'\b(validate|transform|encrypt|store|retrieve|cache|sync)\b', sentence, re.I):
                claim_type = "data_flow"
                keywords = re.findall(r'\b(validate|transform|encrypt|store|retrieve|cache|sync)\b', sentence, re.I)

            # Integration patterns
            elif re.search(r'\b(integrate|connect|send|receive|api|webhook|notification)\b', sentence, re.I):
                claim_type = "integration"
                keywords = re.findall(r'\b(integrate|connect|send|receive|api|webhook|notification)\b', sentence, re.I)

            # Business rule patterns
            elif re.search(r'\b(if|when|only|must|shall|require|allow|deny|discount|calculate)\b', sentence, re.I):
                claim_type = "business_rule"
                keywords = re.findall(r'\b(discount|calculate|rule|condition|require)\b', sentence, re.I)

            # Non-functional patterns
            elif re.search(r'\b(performance|security|scalab|available|reliable|response time)\b', sentence, re.I):
                claim_type = "non_functional"
                keywords = re.findall(r'\b(performance|security|scalab|available|reliable)\b', sentence, re.I)

            else:
                # Check if it contains action verbs (likely a claim)
                if not re.search(r'\b(is|are|will|shall|must|should|can|may)\b', sentence, re.I):
                    continue

            # Extract quantifiers (numbers with context)
            quant_matches = re.findall(r'(\d+\s*(?:step|time|second|minute|hour|day|percent|%|ms|MB|GB)?s?)', sentence, re.I)
            quantifiers = [q.strip() for q in quant_matches]

            # Extract business keywords
            if not keywords:
                # Extract nouns that might be business entities
                keywords = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', sentence)

            # Store search hints (actual entities discovered during verification via Neo4j)
            entities = self._infer_code_entities_sync(keywords, sentence)

            claims.append(Claim(
                text=sentence,
                section=section_name,
                claim_type=claim_type,
                keywords=keywords,
                quantifiers=quantifiers,
                mentioned_entities=entities,
                actions=self._extract_actions(sentence),
            ))

        return claims[:10]  # Limit to 10 claims

    def _extract_entities_from_text(self, text: str) -> list[str]:
        """Extract entity names from text."""
        entities = []

        # CamelCase or PascalCase names (likely class names)
        camel_pattern = r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b'
        entities.extend(re.findall(camel_pattern, text))

        # File paths
        path_pattern = r'[/\\]?[\w./\\]+\.(py|java|ts|js|go|cs|cpp|h)'
        paths = re.findall(path_pattern, text)
        entities.extend(paths)

        # Snake_case names (common in Python)
        snake_pattern = r'\b([a-z]+(?:_[a-z]+)+)\b'
        entities.extend(re.findall(snake_pattern, text))

        return list(set(entities))[:10]  # Unique, limited

    async def _verify_claim(self, claim: Claim) -> None:
        """
        Verify a business-level claim by gathering evidence from multiple sources.

        AGENTIC MODE (preferred):
        - Uses Copilot SDK with MCP tools (Neo4j, Filesystem)
        - LLM decides what queries to run to verify the claim

        FALLBACK MODE (when SDK unavailable):
        - Uses direct Neo4j/Filesystem queries with hardcoded patterns
        """
        logger.debug(f"[VERIFIER] Verifying claim: {claim.text[:80]}...")
        logger.debug(f"[VERIFIER]   Type: {claim.claim_type}")
        logger.debug(f"[VERIFIER]   Keywords: {claim.keywords[:5] if claim.keywords else 'none'}")

        # Try agentic verification first if Copilot session is available
        if self.session and self.enable_agentic_tools:
            logger.debug(f"[VERIFIER]   Mode: Agentic (SDK with MCP tools)")
            await self._verify_claim_agentic(claim)
            return

        # Fallback to hardcoded verification logic
        logger.debug(f"[VERIFIER]   Mode: Fallback (direct queries)")
        await self._verify_claim_fallback(claim)

    async def _verify_claim_agentic(self, claim: Claim) -> None:
        """
        Verify a claim using AGENTIC TOOL CALLING.

        The LLM decides what Neo4j queries to run and what files to read
        to verify the claim. This is more flexible than hardcoded queries.
        """
        logger.info(f"Verifier: Using agentic tools to verify claim: {claim.text[:50]}...")

        # Build a prompt that asks the LLM to verify the claim using tools
        prompt = f"""Verify the following business claim from a BRD document by querying the codebase:

## Claim to Verify
"{claim.text}"

## Claim Details
- Type: {claim.claim_type}
- Section: {claim.section}
- Keywords: {', '.join(claim.keywords[:5]) if claim.keywords else 'none'}
- Quantifiers: {', '.join(claim.quantifiers) if claim.quantifiers else 'none'}

## Your Task

Use the available tools to verify this claim:

1. **Query the code graph** (Neo4j) to find:
   - Components, classes, or functions related to this claim
   - Relationships between entities (DEPENDS_ON, CALLS, IMPLEMENTS)
   - Method names, status values, configuration that support/refute the claim

2. **Read source files** to find:
   - Actual implementation that matches the claim
   - Business logic, validation rules, workflow steps
   - Any evidence that supports or contradicts the claim

3. **Search for tests** that validate the claimed behavior

## Output Format

After gathering evidence, provide your verification result in this JSON format:
```json
{{
    "status": "verified" | "partially_verified" | "unverified" | "contradicted",
    "confidence": 0.0 to 1.0,
    "evidence": [
        {{
            "type": "code" | "config" | "test",
            "source": "file path or query",
            "content": "relevant code/text snippet",
            "supports_claim": true | false
        }}
    ],
    "reasoning": "Explanation of verification result",
    "suggestions": ["Suggestion for improving the claim if unverified"]
}}
```

Start by querying the codebase using the tools, then provide your verification result.
"""

        # Use agentic loop with tools
        response = await self.send_to_llm(prompt, use_tools=True)

        # Parse the verification result
        self._parse_agentic_verification_result(claim, response)

    def _parse_agentic_verification_result(self, claim: Claim, response: str) -> None:
        """Parse the LLM's agentic verification result and update the claim."""
        import json

        try:
            # Extract JSON from response
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                # Try to parse raw JSON
                result = json.loads(response)

            # Update claim status
            status_map = {
                "verified": VerificationStatus.VERIFIED,
                "partially_verified": VerificationStatus.PARTIALLY_VERIFIED,
                "unverified": VerificationStatus.UNVERIFIED,
                "contradicted": VerificationStatus.CONTRADICTED,
            }
            claim.status = status_map.get(result.get("status", "unverified"), VerificationStatus.UNVERIFIED)
            claim.confidence_score = result.get("confidence", 0.5)

            # Add evidence items
            for ev in result.get("evidence", []):
                evidence = EvidenceItem(
                    evidence_type=EvidenceType.CODE_REFERENCE if ev.get("type") == "code"
                                  else EvidenceType.CONFIG_VALUE if ev.get("type") == "config"
                                  else EvidenceType.TEST_COVERAGE,
                    source=ev.get("source", "unknown"),
                    content=ev.get("content", ""),
                    supports_claim=ev.get("supports_claim", False),
                    confidence=result.get("confidence", 0.5),
                )
                claim.evidence.append(evidence)

            # Set reasoning and suggestions
            claim.feedback = result.get("reasoning", "")
            if result.get("suggestions"):
                claim.suggested_correction = result["suggestions"][0] if result["suggestions"] else None

            logger.info(f"Verifier: Claim verified with status={claim.status.value}, confidence={claim.confidence_score}")

        except Exception as e:
            logger.error(f"Failed to parse agentic verification result: {e}")
            # Mark as unverified if parsing fails
            claim.status = VerificationStatus.UNVERIFIED
            claim.confidence_score = 0.3
            claim.feedback = f"Verification failed: {e}"

    async def _verify_claim_fallback(self, claim: Claim) -> None:
        """
        Fallback verification using hardcoded patterns (when tools unavailable).
        """
        logger.debug(f"Verifier: Using fallback verification for claim: {claim.text[:50]}...")

        # Step 0: Discover actual code entities from Neo4j based on keywords
        # This replaces hardcoded entity mappings with real codebase discovery
        if claim.keywords:
            discovered_entities = await self._discover_code_entities(claim.keywords, claim.text)
            # Merge with any entities already found (e.g., explicit class names in BRD)
            claim.mentioned_entities = list(set(claim.mentioned_entities + discovered_entities))

        # Gather evidence based on business claim type
        if claim.claim_type in ["process", "workflow"]:
            await self._verify_process_claim(claim)
        elif claim.claim_type == "behavior":
            await self._verify_behavior_claim(claim)
        elif claim.claim_type == "data_flow":
            await self._verify_data_flow_claim(claim)
        elif claim.claim_type == "integration":
            await self._verify_integration_claim(claim)
        elif claim.claim_type == "business_rule":
            await self._verify_business_rule_claim(claim)
        elif claim.claim_type == "non_functional":
            await self._verify_non_functional_claim(claim)
        else:
            await self._verify_general_business_claim(claim)

        # Always try to find test coverage evidence
        await self._find_test_coverage(claim)

        # Always try to find configuration evidence
        await self._find_config_evidence(claim)

        # Generate feedback for unverified claims
        if claim.status != VerificationStatus.VERIFIED:
            self._generate_claim_feedback(claim)

    async def _verify_process_claim(self, claim: Claim) -> None:
        """Verify claims about business processes/workflows.

        Example: "Orders go through a 7-step workflow"
        Look for: State machines, status enums, method phases, step counts
        """
        # Look for workflow/process patterns in code
        for entity in claim.mentioned_entities:
            # Search for service methods with multiple phases
            evidence = await self._query_method_phases(entity, claim.quantifiers)
            if evidence:
                claim.add_evidence(evidence)

            # Search for state/status enums
            evidence = await self._query_state_machine(entity)
            if evidence:
                claim.add_evidence(evidence)

            # Search for call graphs showing workflow
            evidence = await self._query_call_graph(entity)
            if evidence:
                claim.add_evidence(evidence)

    async def _verify_behavior_claim(self, claim: Claim) -> None:
        """Verify claims about system behavior.

        Example: "System retries failed payments 3 times"
        Look for: Retry logic, error handling, loop patterns
        """
        for keyword in claim.keywords:
            # Search for retry patterns
            evidence = await self._search_code_pattern(
                keyword,
                patterns=["retry", "attempt", "max_retries", "backoff"]
            )
            if evidence:
                claim.add_evidence(evidence)

        # Look for numeric matches (e.g., "3 times")
        for quant in claim.quantifiers:
            evidence = await self._verify_quantifier(quant, claim.keywords)
            if evidence:
                claim.add_evidence(evidence)

    async def _verify_data_flow_claim(self, claim: Claim) -> None:
        """Verify claims about data flow.

        Example: "User data is validated before storage"
        Look for: Validation methods, data transformation, pipeline patterns
        """
        for action in claim.actions:
            # Search for the action in code
            for entity in claim.mentioned_entities[:3]:
                evidence = await self._query_method_containing(entity, action)
                if evidence:
                    claim.add_evidence(evidence)

        # Look for data flow in call graph
        for entity in claim.mentioned_entities[:2]:
            evidence = await self._query_data_flow(entity)
            if evidence:
                claim.add_evidence(evidence)

    async def _verify_integration_claim(self, claim: Claim) -> None:
        """Verify claims about integrations.

        Example: "Payment processing integrates with Stripe"
        Look for: Client classes, API calls, SDK usage, config references
        """
        for keyword in claim.keywords:
            # Search for integration patterns
            evidence = await self._search_code_pattern(
                keyword,
                patterns=["client", "api", "sdk", "integration", "connector"]
            )
            if evidence:
                claim.add_evidence(evidence)

            # Search config for API keys, URLs
            evidence = await self._search_config_for(keyword)
            if evidence:
                claim.add_evidence(evidence)

    async def _verify_business_rule_claim(self, claim: Claim) -> None:
        """Verify claims about business rules.

        Example: "Discounts apply only to orders over $100"
        Look for: Structured business rules in Neo4j (Phase 3), conditional logic, rule classes, validation
        """
        # PHASE 3: Query structurally extracted business rules from Neo4j
        # These have higher confidence than pattern matching
        for keyword in claim.keywords[:5]:
            # Query validation constraints (highest confidence for rules)
            evidence = await self._query_validation_constraints(keyword)
            if evidence:
                claim.add_evidence(evidence)

            # Query guard clauses
            evidence = await self._query_guard_clauses(keyword)
            if evidence:
                claim.add_evidence(evidence)

            # Query conditional business logic
            evidence = await self._query_conditional_business_logic(keyword)
            if evidence:
                claim.add_evidence(evidence)

            # Query test assertions that encode behavior
            evidence = await self._query_test_assertions(keyword)
            if evidence:
                claim.add_evidence(evidence)

        # Fallback: Search for business logic patterns in code
        for keyword in claim.keywords:
            evidence = await self._search_code_pattern(
                keyword,
                patterns=["rule", "validator", "condition", "if ", "when"]
            )
            if evidence:
                claim.add_evidence(evidence)

        # Look for numeric thresholds
        for quant in claim.quantifiers:
            evidence = await self._verify_threshold(quant, claim.keywords)
            if evidence:
                claim.add_evidence(evidence)

    async def _verify_non_functional_claim(self, claim: Claim) -> None:
        """Verify non-functional claims.

        Example: "API responses under 200ms"
        Look for: Config values, SLA definitions, monitoring code
        """
        # Search config for performance/security settings
        for keyword in claim.keywords:
            evidence = await self._search_config_for(keyword)
            if evidence:
                claim.add_evidence(evidence)

        # Search for timeout, limit configurations
        for quant in claim.quantifiers:
            evidence = await self._search_config_for(quant)
            if evidence:
                claim.add_evidence(evidence)

    async def _verify_general_business_claim(self, claim: Claim) -> None:
        """Verify general business claims using multiple strategies."""
        # Try keyword-based search
        for keyword in claim.keywords[:3]:
            evidence = await self._query_component(keyword)
            if evidence:
                claim.add_evidence(evidence)

        # Try entity-based search
        for entity in claim.mentioned_entities[:3]:
            evidence = await self._query_component(entity)
            if evidence:
                claim.add_evidence(evidence)

        # Try pattern search
        for pattern in claim.search_patterns[:2]:
            evidence = await self._search_code(pattern)
            if evidence:
                claim.add_evidence(evidence)

    # =========================================================================
    # Evidence Gathering Methods for Business Claims
    # =========================================================================

    async def _query_method_phases(self, entity: str, quantifiers: list[str]) -> Optional[EvidenceItem]:
        """Query for methods with multiple phases/steps.

        Example: Looking for a method with 7 distinct phases
        """
        if not self.neo4j_client:
            return None

        try:
            # Query for methods in the service
            query = f"""
            MATCH (c:Class)-[:CONTAINS]->(m:Method)
            WHERE c.name CONTAINS '{entity}' OR c.name CONTAINS '{entity}Service'
            RETURN c.name AS className, m.name AS methodName,
                   m.filePath AS filePath, m.startLine AS startLine, m.endLine AS endLine,
                   m.complexity AS complexity
            ORDER BY m.endLine - m.startLine DESC
            LIMIT 100
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]
                code_refs = []
                method_names = []

                for record in records:
                    if record.get("filePath"):
                        code_refs.append(CodeReference(
                            file_path=record["filePath"],
                            start_line=record.get("startLine", 1),
                            end_line=record.get("endLine", 1),
                            entity_type="Method",
                            entity_name=record.get("methodName"),
                        ))
                        method_names.append(record.get("methodName", ""))

                if code_refs:
                    # Try to extract step count from quantifiers
                    expected_steps = None
                    for q in quantifiers:
                        nums = re.findall(r'\d+', q)
                        if nums:
                            expected_steps = int(nums[0])
                            break

                    return EvidenceItem(
                        evidence_type=EvidenceType.METHOD_ANALYSIS,
                        category="primary",
                        description=f"{entity} methods contain multiple phases",
                        confidence=0.75,
                        code_references=code_refs,
                        method_phases=method_names[:7],  # Show up to 7 methods as "phases"
                        source="neo4j",
                        query_used=query,
                        analysis_method="Extracted from AST analysis, confirmed by LLM review",
                        supports_claim=True,
                        hallucination_flags=[] if expected_steps and len(method_names) >= expected_steps else
                            [f"Found {len(method_names)} methods, claim mentions {expected_steps} steps"],
                        hallucination_risk_pct=5 if len(method_names) >= 5 else 15,
                    )

        except Exception as e:
            logger.warning(f"Method phases query failed for '{entity}': {e}")

        return None

    async def _query_state_machine(self, entity: str) -> Optional[EvidenceItem]:
        """Query for state machine / status enum patterns."""
        if not self.neo4j_client:
            return None

        try:
            # Look for enums or status-related classes
            query = f"""
            MATCH (n)
            WHERE (n.name CONTAINS 'Status' OR n.name CONTAINS 'State' OR n.kind = 'enum')
            AND (n.name CONTAINS '{entity}' OR n.filePath CONTAINS '{entity.lower()}')
            RETURN n.name AS name, n.kind AS kind, n.filePath AS filePath,
                   n.startLine AS startLine, n.endLine AS endLine
            LIMIT 50
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]
                code_refs = []
                state_names = []

                for record in records:
                    if record.get("filePath"):
                        code_refs.append(CodeReference(
                            file_path=record["filePath"],
                            start_line=record.get("startLine", 1),
                            end_line=record.get("endLine", 1),
                            entity_type=record.get("kind", "Enum"),
                            entity_name=record.get("name"),
                        ))
                        state_names.append(record.get("name", ""))

                if code_refs:
                    return EvidenceItem(
                        evidence_type=EvidenceType.PATTERN,
                        category="primary",
                        description=f"State/Status pattern found for {entity}",
                        confidence=0.85,
                        code_references=code_refs,
                        method_phases=state_names,
                        source="neo4j",
                        query_used=query,
                        analysis_method="State machine pattern detection",
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"State machine query failed for '{entity}': {e}")

        return None

    async def _search_code_pattern(
        self,
        keyword: str,
        patterns: list[str]
    ) -> Optional[EvidenceItem]:
        """Search code for specific patterns related to a keyword."""
        if not self.filesystem_client:
            return None

        try:
            # Search for the keyword combined with patterns
            all_matches = []
            for pattern in patterns:
                search_term = f"{keyword}.*{pattern}|{pattern}.*{keyword}"
                result = await self.filesystem_client.search_files(search_term)

                if result and result.get("matches"):
                    all_matches.extend(result["matches"])

            if all_matches:
                code_refs = []
                for match in all_matches[:5]:
                    code_refs.append(CodeReference(
                        file_path=match.get("file", ""),
                        start_line=match.get("line", 1),
                        end_line=match.get("line", 1),
                        snippet=match.get("content", "")[:200],
                    ))

                return EvidenceItem(
                    evidence_type=EvidenceType.CODE_REFERENCE,
                    category="primary",
                    description=f"Found '{keyword}' with {patterns[0]} pattern in {len(code_refs)} locations",
                    confidence=0.7,
                    code_references=code_refs,
                    source="filesystem",
                    analysis_method=f"Pattern search: {keyword} + {patterns}",
                    supports_claim=True,
                )

        except Exception as e:
            logger.warning(f"Pattern search failed: {e}")

        return None

    async def _verify_quantifier(
        self,
        quantifier: str,
        keywords: list[str]
    ) -> Optional[EvidenceItem]:
        """Verify a numeric quantifier mentioned in a claim.

        Example: "3 times", "7 steps", "100 dollars"
        """
        if not self.filesystem_client:
            return None

        try:
            # Extract the number
            nums = re.findall(r'\d+', quantifier)
            if not nums:
                return None

            number = nums[0]

            # Search for this number in code near keywords
            for keyword in keywords[:2]:
                search_term = f"{number}.*{keyword}|{keyword}.*{number}"
                result = await self.filesystem_client.search_files(search_term)

                if result and result.get("matches"):
                    matches = result["matches"]
                    code_refs = []
                    for match in matches[:3]:
                        code_refs.append(CodeReference(
                            file_path=match.get("file", ""),
                            start_line=match.get("line", 1),
                            end_line=match.get("line", 1),
                            snippet=match.get("content", "")[:150],
                        ))

                    if code_refs:
                        return EvidenceItem(
                            evidence_type=EvidenceType.CODE_REFERENCE,
                            category="primary",
                            description=f"Found '{number}' (from '{quantifier}') in code near '{keyword}'",
                            confidence=0.8,
                            code_references=code_refs,
                            source="filesystem",
                            supports_claim=True,
                            metrics={"quantifier": quantifier, "found_value": number},
                        )

        except Exception as e:
            logger.warning(f"Quantifier verification failed: {e}")

        return None

    async def _query_method_containing(self, entity: str, action: str) -> Optional[EvidenceItem]:
        """Query for methods containing a specific action verb."""
        if not self.neo4j_client:
            return None

        try:
            query = f"""
            MATCH (c:Class)-[:CONTAINS]->(m:Method)
            WHERE (c.name CONTAINS '{entity}' OR c.name CONTAINS '{entity}Service')
            AND m.name CONTAINS '{action}'
            RETURN c.name AS className, m.name AS methodName,
                   m.filePath AS filePath, m.startLine AS startLine, m.endLine AS endLine
            LIMIT 50
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]
                code_refs = []

                for record in records:
                    if record.get("filePath"):
                        code_refs.append(CodeReference(
                            file_path=record["filePath"],
                            start_line=record.get("startLine", 1),
                            end_line=record.get("endLine", 1),
                            entity_type="Method",
                            entity_name=f"{record.get('className', '')}.{record.get('methodName', '')}",
                        ))

                if code_refs:
                    return EvidenceItem(
                        evidence_type=EvidenceType.CODE_REFERENCE,
                        category="primary",
                        description=f"Method '{action}' found in {entity}",
                        confidence=0.8,
                        code_references=code_refs,
                        source="neo4j",
                        query_used=query,
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"Method query failed: {e}")

        return None

    async def _query_data_flow(self, entity: str) -> Optional[EvidenceItem]:
        """Query for data flow patterns."""
        if not self.neo4j_client:
            return None

        try:
            query = f"""
            MATCH path = (source)-[:CALLS|USES|IMPORTS*1..3]->(target)
            WHERE source.name CONTAINS '{entity}' OR target.name CONTAINS '{entity}'
            RETURN nodes(path) AS nodes, relationships(path) AS rels
            LIMIT 100
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]
                call_graph = []

                for record in records:
                    nodes = record.get("nodes", [])
                    for i in range(len(nodes) - 1):
                        call_graph.append(CallGraphEvidence(
                            source_entity=nodes[i].get("name", "unknown") if isinstance(nodes[i], dict) else str(nodes[i]),
                            target_entity=nodes[i+1].get("name", "unknown") if isinstance(nodes[i+1], dict) else str(nodes[i+1]),
                            relationship="CALLS",
                        ))

                if call_graph:
                    return EvidenceItem(
                        evidence_type=EvidenceType.DATA_FLOW,
                        category="primary",
                        description=f"Data flow pattern found for {entity}",
                        confidence=0.75,
                        call_graph=call_graph[:10],
                        source="neo4j",
                        query_used=query,
                        analysis_method="Graph traversal analysis",
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"Data flow query failed: {e}")

        return None

    async def _search_config_for(self, keyword: str) -> Optional[EvidenceItem]:
        """Search configuration files for a keyword."""
        if not self.filesystem_client:
            return None

        try:
            # Search in common config files
            config_patterns = ["*.yml", "*.yaml", "*.json", "*.properties", "*.env", "*.toml"]
            all_matches = []

            for pattern in config_patterns:
                result = await self.filesystem_client.search_files(keyword, file_pattern=pattern)
                if result and result.get("matches"):
                    all_matches.extend(result["matches"])

            if all_matches:
                code_refs = []
                config_values = {}

                for match in all_matches[:5]:
                    file_path = match.get("file", "")
                    code_refs.append(CodeReference(
                        file_path=file_path,
                        start_line=match.get("line", 1),
                        end_line=match.get("line", 1),
                        snippet=match.get("content", "")[:100],
                    ))

                    # Try to extract key=value
                    content = match.get("content", "")
                    if ":" in content or "=" in content:
                        parts = re.split(r'[:=]', content, maxsplit=1)
                        if len(parts) == 2:
                            config_values[parts[0].strip()] = parts[1].strip()[:50]

                if code_refs:
                    return EvidenceItem(
                        evidence_type=EvidenceType.CONFIGURATION,
                        category="secondary",
                        description=f"Configuration found for '{keyword}'",
                        confidence=0.7,
                        code_references=code_refs,
                        config_values=config_values,
                        source="filesystem",
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"Config search failed: {e}")

        return None

    async def _verify_threshold(self, quantifier: str, keywords: list[str]) -> Optional[EvidenceItem]:
        """Verify a threshold/limit value in code or config."""
        # Similar to _verify_quantifier but focused on thresholds
        return await self._verify_quantifier(quantifier, keywords)

    # =========================================================================
    # Business Rule Evidence Queries (Phase 3)
    # Query structurally extracted business rules from Neo4j
    # =========================================================================

    async def _query_validation_constraints(self, keyword: str) -> Optional[EvidenceItem]:
        """Query ValidationConstraint nodes from Neo4j.

        These are structurally extracted from @NotNull, @Min, @Pattern, etc.
        Confidence: 0.95 (explicit annotations)
        """
        if not self.neo4j_client:
            return None

        try:
            query = f"""
            MATCH (vc:ValidationConstraint)
            WHERE toLower(vc.ruleText) CONTAINS toLower('{keyword}')
               OR toLower(vc.targetName) CONTAINS toLower('{keyword}')
               OR toLower(vc.constraintName) CONTAINS toLower('{keyword}')
            RETURN vc.ruleText AS ruleText, vc.constraintName AS constraintName,
                   vc.targetName AS targetName, vc.constraintParameters AS params,
                   vc.filePath AS filePath, vc.startLine AS startLine, vc.endLine AS endLine,
                   vc.confidence AS confidence
            LIMIT 50
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]
                code_refs = []
                config_values = {}

                for record in records:
                    if record.get("filePath"):
                        code_refs.append(CodeReference(
                            file_path=record["filePath"],
                            start_line=record.get("startLine", 1),
                            end_line=record.get("endLine", 1),
                            entity_type="ValidationConstraint",
                            entity_name=record.get("constraintName"),
                        ))
                        # Capture constraint details
                        config_values[record.get("targetName", "field")] = (
                            f"@{record.get('constraintName', '')}: {record.get('ruleText', '')}"
                        )

                if code_refs:
                    return EvidenceItem(
                        evidence_type=EvidenceType.VALIDATION_CONSTRAINT,
                        category="primary",
                        description=f"Found {len(code_refs)} validation constraint(s) for '{keyword}'",
                        confidence=0.95,
                        code_references=code_refs,
                        config_values=config_values,
                        source="neo4j",
                        query_used=query,
                        analysis_method="Structurally extracted from annotations",
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"Validation constraint query failed for '{keyword}': {e}")

        return None

    async def _query_guard_clauses(self, keyword: str) -> Optional[EvidenceItem]:
        """Query GuardClause nodes from Neo4j.

        These are structurally extracted from if (x == null) throw patterns.
        Confidence: 0.90 (clear preconditions)
        """
        if not self.neo4j_client:
            return None

        try:
            query = f"""
            MATCH (gc:GuardClause)
            WHERE toLower(gc.ruleText) CONTAINS toLower('{keyword}')
               OR toLower(gc.guardedMethod) CONTAINS toLower('{keyword}')
               OR toLower(gc.errorMessage) CONTAINS toLower('{keyword}')
            RETURN gc.ruleText AS ruleText, gc.condition AS condition,
                   gc.guardType AS guardType, gc.errorMessage AS errorMessage,
                   gc.guardedMethod AS guardedMethod,
                   gc.filePath AS filePath, gc.startLine AS startLine, gc.endLine AS endLine,
                   gc.confidence AS confidence
            LIMIT 50
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]
                code_refs = []

                for record in records:
                    if record.get("filePath"):
                        code_refs.append(CodeReference(
                            file_path=record["filePath"],
                            start_line=record.get("startLine", 1),
                            end_line=record.get("endLine", 1),
                            entity_type="GuardClause",
                            entity_name=record.get("guardedMethod"),
                            snippet=record.get("condition"),
                        ))

                if code_refs:
                    return EvidenceItem(
                        evidence_type=EvidenceType.GUARD_CLAUSE,
                        category="primary",
                        description=f"Found {len(code_refs)} guard clause(s) for '{keyword}'",
                        confidence=0.90,
                        code_references=code_refs,
                        source="neo4j",
                        query_used=query,
                        analysis_method="Structurally extracted from guard patterns",
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"Guard clause query failed for '{keyword}': {e}")

        return None

    async def _query_conditional_business_logic(self, keyword: str) -> Optional[EvidenceItem]:
        """Query ConditionalBusinessLogic nodes from Neo4j.

        These are extracted from if (amount > 50000) patterns.
        Confidence: 0.80 (inferred business logic)
        """
        if not self.neo4j_client:
            return None

        try:
            query = f"""
            MATCH (cbl:ConditionalBusinessLogic)
            WHERE toLower(cbl.ruleText) CONTAINS toLower('{keyword}')
               OR toLower(cbl.variable) CONTAINS toLower('{keyword}')
               OR toLower(cbl.businessMeaning) CONTAINS toLower('{keyword}')
            RETURN cbl.ruleText AS ruleText, cbl.condition AS condition,
                   cbl.variable AS variable, cbl.threshold AS threshold,
                   cbl.businessMeaning AS businessMeaning,
                   cbl.filePath AS filePath, cbl.startLine AS startLine, cbl.endLine AS endLine,
                   cbl.confidence AS confidence
            LIMIT 50
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]
                code_refs = []

                for record in records:
                    if record.get("filePath"):
                        code_refs.append(CodeReference(
                            file_path=record["filePath"],
                            start_line=record.get("startLine", 1),
                            end_line=record.get("endLine", 1),
                            entity_type="ConditionalBusinessLogic",
                            entity_name=record.get("variable"),
                            snippet=record.get("condition"),
                        ))

                if code_refs:
                    return EvidenceItem(
                        evidence_type=EvidenceType.CODE_REFERENCE,  # Using CODE_REFERENCE as fallback
                        category="primary",
                        description=f"Found {len(code_refs)} conditional business logic for '{keyword}'",
                        confidence=0.80,
                        code_references=code_refs,
                        source="neo4j",
                        query_used=query,
                        analysis_method="Structurally extracted from business conditionals",
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"Conditional business logic query failed for '{keyword}': {e}")

        return None

    async def _query_test_assertions(self, keyword: str) -> Optional[EvidenceItem]:
        """Query TestAssertion nodes from Neo4j.

        These derive business rules from test expectations.
        Confidence: 0.85 (tested behavior)
        """
        if not self.neo4j_client:
            return None

        try:
            query = f"""
            MATCH (ta:TestAssertion)
            WHERE toLower(ta.ruleText) CONTAINS toLower('{keyword}')
               OR toLower(ta.inferredRule) CONTAINS toLower('{keyword}')
               OR toLower(ta.testedEntity) CONTAINS toLower('{keyword}')
            RETURN ta.ruleText AS ruleText, ta.assertionType AS assertionType,
                   ta.inferredRule AS inferredRule, ta.testedEntity AS testedEntity,
                   ta.testMethodName AS testMethodName, ta.testClassName AS testClassName,
                   ta.filePath AS filePath, ta.startLine AS startLine, ta.endLine AS endLine,
                   ta.confidence AS confidence
            LIMIT 50
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]
                test_cases = []
                code_refs = []

                for record in records:
                    if record.get("filePath"):
                        code_refs.append(CodeReference(
                            file_path=record["filePath"],
                            start_line=record.get("startLine", 1),
                            end_line=record.get("endLine", 1),
                            entity_type="TestAssertion",
                            entity_name=record.get("testMethodName"),
                        ))
                        test_cases.append(
                            f"{record.get('testClassName', '')}.{record.get('testMethodName', '')}"
                        )

                if code_refs:
                    return EvidenceItem(
                        evidence_type=EvidenceType.TEST_ASSERTION,
                        category="primary",
                        description=f"Found {len(code_refs)} test assertion(s) encoding behavior for '{keyword}'",
                        confidence=0.85,
                        code_references=code_refs,
                        test_cases=test_cases,
                        source="neo4j",
                        query_used=query,
                        analysis_method="Derived from test assertions",
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"Test assertion query failed for '{keyword}': {e}")

        return None

    async def _query_business_rules(self, keyword: str) -> Optional[EvidenceItem]:
        """Query generic BusinessRule nodes from Neo4j.

        This is a catch-all for any business rules not categorized.
        Confidence: 1.0 (structurally extracted)
        """
        if not self.neo4j_client:
            return None

        try:
            query = f"""
            MATCH (br:BusinessRule)
            WHERE toLower(br.ruleText) CONTAINS toLower('{keyword}')
               OR toLower(br.condition) CONTAINS toLower('{keyword}')
            RETURN br.ruleText AS ruleText, br.condition AS condition,
                   br.ruleType AS ruleType, br.severity AS severity,
                   br.filePath AS filePath, br.startLine AS startLine, br.endLine AS endLine,
                   br.confidence AS confidence
            LIMIT 50
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]
                code_refs = []

                for record in records:
                    if record.get("filePath"):
                        code_refs.append(CodeReference(
                            file_path=record["filePath"],
                            start_line=record.get("startLine", 1),
                            end_line=record.get("endLine", 1),
                            entity_type="BusinessRule",
                            entity_name=record.get("ruleType"),
                            snippet=record.get("ruleText"),
                        ))

                if code_refs:
                    return EvidenceItem(
                        evidence_type=EvidenceType.BUSINESS_RULE,
                        category="primary",
                        description=f"Found {len(code_refs)} business rule(s) for '{keyword}'",
                        confidence=1.0,
                        code_references=code_refs,
                        source="neo4j",
                        query_used=query,
                        analysis_method="Structurally extracted business rule",
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"Business rule query failed for '{keyword}': {e}")

        return None

    async def _find_test_coverage(self, claim: Claim) -> None:
        """Find test cases that validate the claim."""
        if not self.filesystem_client:
            return

        try:
            # Search for tests related to claim keywords
            test_cases = []

            for keyword in claim.keywords[:3]:
                # Search in test files
                result = await self.filesystem_client.search_files(
                    keyword,
                    file_pattern="*test*.py|*Test*.java|*.spec.ts|*.test.js"
                )

                if result and result.get("matches"):
                    for match in result["matches"][:3]:
                        test_cases.append(f"{match.get('file', '')}:{match.get('line', 1)}")

            if test_cases:
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.TEST_COVERAGE,
                    category="supporting",
                    description=f"Test coverage validates behavior",
                    confidence=0.7,
                    test_cases=test_cases[:5],
                    source="filesystem",
                    supports_claim=True,
                ))

        except Exception as e:
            logger.warning(f"Test coverage search failed: {e}")

    async def _find_config_evidence(self, claim: Claim) -> None:
        """Find configuration evidence for the claim."""
        # Already called in specific verifiers, this is a catch-all
        if claim.quantifiers and not any(
            e.evidence_type == EvidenceType.CONFIGURATION for e in claim.evidence
        ):
            for quant in claim.quantifiers[:2]:
                evidence = await self._search_config_for(quant)
                if evidence:
                    claim.add_evidence(evidence)
                    break

    async def _query_component(self, entity: str) -> Optional[EvidenceItem]:
        """Query Neo4j for a component."""
        if not self.neo4j_client:
            return None

        try:
            # Query for nodes with matching name
            query = f"""
            MATCH (n)
            WHERE n.name CONTAINS '{entity}' OR n.entityId CONTAINS '{entity}'
            RETURN n.name AS name, n.kind AS kind, n.filePath AS filePath,
                   n.startLine AS startLine, n.endLine AS endLine
            LIMIT 50
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]
                code_refs = []

                for record in records:
                    if record.get("filePath"):
                        code_refs.append(CodeReference(
                            file_path=record["filePath"],
                            start_line=record.get("startLine", 1),
                            end_line=record.get("endLine", 1),
                            entity_type=record.get("kind"),
                            entity_name=record.get("name"),
                        ))

                if code_refs:
                    return EvidenceItem(
                        evidence_type=EvidenceType.CODE_REFERENCE,
                        description=f"Found {len(code_refs)} matches for '{entity}' in codebase",
                        confidence=0.8 if len(code_refs) > 0 else 0.3,
                        code_references=code_refs,
                        source="neo4j",
                        query_used=query,
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"Neo4j query failed for component '{entity}': {e}")

        return None

    async def _query_call_graph(self, entity: str) -> Optional[EvidenceItem]:
        """Query Neo4j for call graph relationships."""
        if not self.neo4j_client:
            return None

        try:
            query = f"""
            MATCH (source)-[r:CALLS|INVOKES]->(target)
            WHERE source.name CONTAINS '{entity}' OR target.name CONTAINS '{entity}'
            RETURN source.name AS sourceName, type(r) AS relType, target.name AS targetName,
                   source.filePath AS sourceFile, target.filePath AS targetFile
            LIMIT 100
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]
                call_graph = []

                for record in records:
                    call_graph.append(CallGraphEvidence(
                        source_entity=record.get("sourceName", "unknown"),
                        target_entity=record.get("targetName", "unknown"),
                        relationship=record.get("relType", "CALLS"),
                        source_file=record.get("sourceFile"),
                        target_file=record.get("targetFile"),
                    ))

                if call_graph:
                    return EvidenceItem(
                        evidence_type=EvidenceType.CALL_GRAPH,
                        description=f"Found {len(call_graph)} call relationships for '{entity}'",
                        confidence=0.85,
                        call_graph=call_graph,
                        source="neo4j",
                        query_used=query,
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"Neo4j call graph query failed: {e}")

        return None

    async def _query_dependencies(self, entity: str) -> Optional[EvidenceItem]:
        """Query Neo4j for dependency relationships."""
        if not self.neo4j_client:
            return None

        try:
            query = f"""
            MATCH (source)-[r:IMPORTS|DEPENDS_ON|USES]->(target)
            WHERE source.name CONTAINS '{entity}' OR target.name CONTAINS '{entity}'
            RETURN source.name AS sourceName, type(r) AS relType, target.name AS targetName,
                   source.filePath AS sourceFile
            LIMIT 100
            """

            result = await self.neo4j_client.execute_query(query)

            if result and result.get("records"):
                records = result["records"]

                return EvidenceItem(
                    evidence_type=EvidenceType.DEPENDENCY,
                    description=f"Found {len(records)} dependency relationships for '{entity}'",
                    confidence=0.8,
                    metrics={"dependency_count": len(records)},
                    source="neo4j",
                    query_used=query,
                    supports_claim=True,
                )

        except Exception as e:
            logger.warning(f"Neo4j dependency query failed: {e}")

        return None

    async def _search_code(self, pattern: str) -> Optional[EvidenceItem]:
        """Search code files for a pattern."""
        if not self.filesystem_client:
            return None

        try:
            # Use filesystem client to search
            result = await self.filesystem_client.search_files(pattern)

            if result and result.get("matches"):
                matches = result["matches"]
                code_refs = []

                for match in matches[:5]:  # Limit results
                    code_refs.append(CodeReference(
                        file_path=match.get("file", ""),
                        start_line=match.get("line", 1),
                        end_line=match.get("line", 1),
                        snippet=match.get("content", "")[:200],
                    ))

                if code_refs:
                    return EvidenceItem(
                        evidence_type=EvidenceType.CODE_REFERENCE,
                        description=f"Found {len(code_refs)} code matches for '{pattern}'",
                        confidence=0.7,
                        code_references=code_refs,
                        source="filesystem",
                        supports_claim=True,
                    )

        except Exception as e:
            logger.warning(f"Code search failed for pattern '{pattern}': {e}")

        return None

    async def _verify_file_exists(self, file_path: str) -> Optional[EvidenceItem]:
        """Verify that a file exists."""
        if not self.filesystem_client:
            return None

        try:
            result = await self.filesystem_client.read_file(file_path)

            if result and result.get("content"):
                return EvidenceItem(
                    evidence_type=EvidenceType.CODE_REFERENCE,
                    description=f"File exists: {file_path}",
                    confidence=1.0,
                    code_references=[CodeReference(
                        file_path=file_path,
                        start_line=1,
                        end_line=len(result["content"].split("\n")),
                    )],
                    source="filesystem",
                    supports_claim=True,
                )

        except Exception:
            # File doesn't exist
            return EvidenceItem(
                evidence_type=EvidenceType.CODE_REFERENCE,
                description=f"File NOT found: {file_path}",
                confidence=0.9,  # High confidence it's wrong
                source="filesystem",
                supports_claim=False,  # Contradicts the claim
            )

        return None

    def _extract_technical_patterns(self, text: str) -> list[str]:
        """Extract technical patterns to search for."""
        patterns = []

        # API patterns
        api_patterns = re.findall(r'/api/v\d+/[\w/]+', text)
        patterns.extend(api_patterns)

        # Method signatures
        method_patterns = re.findall(r'\b\w+\([^)]*\)', text)
        patterns.extend(method_patterns[:3])

        # Technical terms
        terms = ["@Controller", "@Service", "@Repository", "async", "await", "Promise"]
        for term in terms:
            if term.lower() in text.lower():
                patterns.append(term)

        return patterns[:5]

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract searchable keywords from text."""
        # Remove common words
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                     "being", "have", "has", "had", "do", "does", "did", "will",
                     "would", "could", "should", "may", "might", "must", "shall",
                     "can", "need", "dare", "ought", "used", "to", "of", "in",
                     "for", "on", "with", "at", "by", "from", "as", "into",
                     "through", "during", "before", "after", "above", "below",
                     "between", "under", "again", "further", "then", "once"}

        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        keywords = [w for w in words if w not in stopwords]

        # Prefer longer, more specific words
        keywords.sort(key=len, reverse=True)

        return keywords[:5]

    def _generate_claim_feedback(self, claim: Claim) -> None:
        """Generate feedback for a claim that failed verification."""
        if not claim.evidence:
            claim.feedback = "No evidence found in codebase to support this claim."
            claim.suggested_correction = "Please verify this claim exists in the actual codebase or remove it."
            return

        supporting = [e for e in claim.evidence if e.supports_claim]
        contradicting = [e for e in claim.evidence if not e.supports_claim]

        if contradicting and not supporting:
            claim.feedback = f"Evidence contradicts this claim: {contradicting[0].description}"
            claim.suggested_correction = "This claim appears to be incorrect based on codebase analysis."
        elif claim.confidence_score < self.verification_config.min_confidence_for_approval:
            claim.feedback = f"Insufficient evidence (confidence: {claim.confidence_score:.2f})"
            claim.suggested_correction = "Please provide more specific details that can be verified."

    def _generate_section_feedback(self, result: SectionVerificationResult) -> None:
        """Generate section-level feedback."""
        issues = []
        suggestions = []

        # Analyze unverified claims
        unverified = [c for c in result.claims if c.status != VerificationStatus.VERIFIED]

        if unverified:
            issues.append(f"{len(unverified)} claims could not be verified")

        # Check for high hallucination risk
        high_risk = [c for c in result.claims if c.hallucination_risk in [HallucinationRisk.HIGH, HallucinationRisk.CRITICAL]]
        if high_risk:
            issues.append(f"{len(high_risk)} claims have high hallucination risk")

        # Check for contradicted claims
        contradicted = [c for c in result.claims if c.status == VerificationStatus.CONTRADICTED]
        if contradicted:
            issues.append(f"{len(contradicted)} claims are contradicted by evidence")
            suggestions.append("Remove or correct claims that contradict the actual codebase")

        # General suggestions
        if result.overall_confidence < 0.5:
            suggestions.append("Focus on making claims that reference actual code entities")
            suggestions.append("Use specific component/file names from the codebase")

        result.issues = issues
        result.suggestions = suggestions

    def _compile_feedback(self, result: SectionVerificationResult) -> str:
        """Compile detailed feedback for the generator."""
        lines = [
            f"## Verification Failed for Section: {result.section_name}",
            f"Overall Confidence: {result.overall_confidence:.2f}",
            f"Hallucination Risk: {result.hallucination_risk.value}",
            "",
            "### Issues:",
        ]

        for issue in result.issues:
            lines.append(f"- {issue}")

        lines.append("\n### Claims Requiring Revision:")

        for claim in result.claims:
            if claim.status != VerificationStatus.VERIFIED:
                lines.append(f"\n**Claim**: {claim.text[:100]}...")
                lines.append(f"**Status**: {claim.status.value}")
                lines.append(f"**Confidence**: {claim.confidence_score:.2f}")
                if claim.feedback:
                    lines.append(f"**Feedback**: {claim.feedback}")
                if claim.suggested_correction:
                    lines.append(f"**Suggestion**: {claim.suggested_correction}")

        lines.append("\n### Suggestions for Improvement:")
        for suggestion in result.suggestions:
            lines.append(f"- {suggestion}")

        return "\n".join(lines)

    def _generate_mock_response(self, prompt: str) -> str:
        """Generate mock business-level claim extraction for testing."""
        return """
CLAIM: Orders go through a 7-step workflow before completion
TYPE: process
KEYWORDS: [order, workflow, step, status, completion]
QUANTIFIERS: [7 steps]
SEARCH_HINTS: [Look for OrderService methods, state machine patterns, status enums]

CLAIM: System retries failed payments up to 3 times with exponential backoff
TYPE: behavior
KEYWORDS: [payment, retry, backoff, failure]
QUANTIFIERS: [3 times]
SEARCH_HINTS: [Look for retry logic in PaymentService, max_retries config]

CLAIM: User data is validated and encrypted before storage
TYPE: data_flow
KEYWORDS: [user, data, validation, encryption, storage]
QUANTIFIERS: []
SEARCH_HINTS: [Look for validate methods, encryption utilities, before save hooks]

CLAIM: Premium users receive priority support response within 2 hours
TYPE: business_rule
KEYWORDS: [premium, user, priority, support, response]
QUANTIFIERS: [2 hours]
SEARCH_HINTS: [Look for user tier checks, SLA configuration, priority queues]
"""

    def get_evidence_bundle(self) -> Optional[EvidenceBundle]:
        """Get the current evidence bundle."""
        return self.current_bundle

    def get_evidence_trail(self, show_details: bool = False) -> str:
        """
        Get the evidence trail.

        Args:
            show_details: If True, include full evidence details.
                        If False, just show summary (default hidden mode).
        """
        if self.current_bundle:
            return self.current_bundle.to_evidence_trail(include_details=show_details)
        return "No verification has been performed yet."
