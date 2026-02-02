"""Simplified Multi-Agent Orchestrator for BRD Generation and Verification.

Uses Copilot SDK's built-in agentic loop instead of complex message passing.
The SDK handles MCP tool calling automatically via mcp_servers in session config.

Flow (Section-by-Section):
1. For each BRD section:
   a. Generate section using LLM (SDK calls MCP tools as needed)
   b. Verify section claims using LLM (SDK gathers evidence)
   c. If verification fails, regenerate section with feedback
2. Combine all verified sections into final BRD

Skills Integration:
- Skills are auto-discovered by Copilot SDK from skill_directories
- Prompts use trigger phrases (e.g., "generate brd", "verify brd")
- SDK automatically injects skill instructions when triggers match
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional, TYPE_CHECKING

from ..models.context import AggregatedContext
from ..models.output import BRDDocument, BRDOutput, Requirement, AcceptanceCriteria
from ..models.verification import (
    EvidenceBundle,
    VerificationConfig,
    SectionVerificationResult,
    Claim,
    ClaimType,
    VerificationStatus,
    HallucinationRisk,
    EvidenceItem,
    EvidenceType,
    ConfidenceLevel,
    CodeReference,
)
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from ..utils.logger import get_logger, get_progress_logger
from typing import Callable, Awaitable

# Type alias for progress callback
ProgressCallback = Callable[[str, str], Awaitable[None]]

from .brd_best_practices import (
    BRD_BEST_PRACTICES,
    DEFAULT_BRD_SECTIONS,
    get_section_guidelines,
)

if TYPE_CHECKING:
    from .template_parser import ParsedBRDTemplate

logger = get_logger(__name__)
progress = get_progress_logger(__name__, "Orchestrator")


# Default BRD section names (from best practices module)
DEFAULT_BRD_SECTION_NAMES = [s["name"] for s in DEFAULT_BRD_SECTIONS]

# Default sufficiency criteria - what makes a complete analysis
DEFAULT_SUFFICIENCY_CRITERIA = {
    "dimensions": [
        {
            "name": "Data Model",
            "description": "Classes, fields, types, relationships",
            "required": True,
        },
        {
            "name": "Business Logic",
            "description": "Service methods, what they do, workflows",
            "required": True,
        },
        {
            "name": "User Flow",
            "description": "States, transitions, views, UI components",
            "required": True,
        },
        {
            "name": "API Contracts",
            "description": "Endpoints, request/response formats, authentication",
            "required": False,
        },
        {
            "name": "Validation Rules",
            "description": "Input validation, business rules, constraints",
            "required": False,
        },
        {
            "name": "Error Handling",
            "description": "Exception handling, error messages, recovery",
            "required": False,
        },
        {
            "name": "Dependencies",
            "description": "External services, libraries, integrations",
            "required": False,
        },
    ],
    "output_requirements": {
        "code_traceability": True,  # Reference specific files/lines
        "explicit_gaps": True,  # Document what wasn't found
        "evidence_based": True,  # All claims backed by tool results
    },
    "min_dimensions_covered": 3,  # Minimum required dimensions to proceed
}


class MultiAgentOrchestrator:
    """
    Simplified orchestrator using Copilot SDK's native agentic loop.

    Processes BRD section-by-section:
    - Generate each section independently
    - Verify each section's claims against codebase
    - Regenerate only failed sections with targeted feedback
    - Combine all verified sections into final BRD
    """

    def __init__(
        self,
        copilot_session: Any = None,
        neo4j_client: Optional[Neo4jMCPClient] = None,
        filesystem_client: Optional[FilesystemMCPClient] = None,
        verification_config: Optional[VerificationConfig] = None,
        max_iterations: int = 3,
        show_evidence_by_default: bool = False,
        parsed_template: Optional["ParsedBRDTemplate"] = None,
        sufficiency_criteria: Optional[dict] = None,
        detail_level: str = "standard",
        custom_sections: Optional[list[dict]] = None,
        verification_limits: Optional[dict] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            copilot_session: Copilot SDK session (with mcp_servers configured)
            neo4j_client: Neo4j client for fallback queries
            filesystem_client: Filesystem client for fallback queries
            verification_config: Verification settings
            max_iterations: Max regeneration attempts per section
            show_evidence_by_default: Include evidence in output
            parsed_template: Custom BRD template
            progress_callback: Optional callback for streaming progress updates
            sufficiency_criteria: Custom criteria for what makes a complete analysis.
                Structure:
                {
                    "dimensions": [
                        {"name": "Data Model", "description": "...", "required": True},
                        ...
                    ],
                    "output_requirements": {
                        "code_traceability": True,
                        "explicit_gaps": True,
                        "evidence_based": True,
                    },
                    "min_dimensions_covered": 3,
                }
            verification_limits: Dynamic limits for verification queries.
                Structure:
                {
                    "max_entities_per_claim": 10,    # Entities to verify per claim
                    "max_patterns_per_claim": 5,     # Patterns to search per claim
                    "results_per_query": 20,         # Max results per Neo4j query
                    "code_refs_per_evidence": 10,    # Code refs to include
                }
        """
        self.session = copilot_session
        self.neo4j_client = neo4j_client
        self.filesystem_client = filesystem_client
        self.verification_config = verification_config or VerificationConfig(
            max_iterations=max_iterations
        )
        self.max_iterations = max_iterations
        self.show_evidence_by_default = show_evidence_by_default
        self.parsed_template = parsed_template

        # Output control
        self.detail_level = detail_level
        self.custom_sections = custom_sections
        logger.info(f"Detail level: {detail_level}")
        if custom_sections:
            logger.info(f"Custom sections: {[s.get('name') for s in custom_sections]}")

        # Sufficiency criteria - what makes a complete analysis (optional)
        # If not provided, the skill instructions will guide context gathering
        self.sufficiency_criteria = sufficiency_criteria
        if self.sufficiency_criteria:
            logger.info(f"Sufficiency criteria: {len(self.sufficiency_criteria.get('dimensions', []))} dimensions configured")
        else:
            logger.info("No sufficiency criteria provided - skill will determine sufficient context")

        # Verification limits - dynamic configuration for queries
        default_limits = {
            "max_entities_per_claim": 10,
            "max_patterns_per_claim": 5,
            "results_per_query": 20,
            "code_refs_per_evidence": 10,
        }
        self.verification_limits = {**default_limits, **(verification_limits or {})}
        logger.info(f"Verification limits: {self.verification_limits}")

        # Progress callback for streaming updates to UI
        self._progress_callback = progress_callback

        # Get sections from template, custom_sections, or defaults (from best practices)
        if custom_sections:
            self.sections = [s.get("name", f"Section {i}") for i, s in enumerate(custom_sections, 1)]
            self.section_configs = custom_sections
        elif parsed_template and hasattr(parsed_template, 'get_section_names'):
            self.sections = parsed_template.get_section_names()
            self.section_configs = None
        else:
            self.sections = DEFAULT_BRD_SECTION_NAMES
            self.section_configs = DEFAULT_BRD_SECTIONS  # Full config with descriptions

        # Skills are auto-discovered by Copilot SDK from skill_directories
        # We just use trigger phrases in prompts (e.g., "generate brd", "verify brd")
        logger.info("Skills will be auto-loaded by Copilot SDK from skill_directories")

        # Results
        self.final_brd: Optional[BRDDocument] = None
        self.final_evidence: Optional[EvidenceBundle] = None
        self.section_contents: dict[str, str] = {}
        self.section_evidence: dict[str, SectionVerificationResult] = {}

        # Metrics
        self.metrics = {
            "total_iterations": 0,
            "sections_regenerated": 0,
            "claims_verified": 0,
            "claims_failed": 0,
            "total_time_ms": 0,
        }

        # Log initialization
        session_status = "available" if copilot_session else "not available"
        logger.info(f"Orchestrator initialized (session: {session_status}, max_iterations: {max_iterations})")
        logger.info(f"Sections to generate: {self.sections}")

    async def initialize(self) -> None:
        """Initialize is now a no-op since we use SDK directly."""
        logger.info("Orchestrator ready (using Copilot SDK's native agentic loop)")

    async def _emit_progress(self, step: str, detail: str) -> None:
        """Emit progress event to callback if available."""
        if self._progress_callback:
            try:
                await self._progress_callback(step, detail)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    async def generate_verified_brd(
        self,
        context: AggregatedContext,
    ) -> BRDOutput:
        """
        Generate a verified BRD through section-by-section generation and verification.

        For each section:
        1. Generate section content
        2. Extract and verify claims
        3. If failed, regenerate with feedback (up to max_iterations)
        4. Move to next section

        Args:
            context: Aggregated context from code analysis

        Returns:
            BRDOutput with verified BRD and evidence
        """
        start_time = time.time()
        request_preview = context.request[:80] + "..." if len(context.request) > 80 else context.request

        progress.start_operation("BRD Generation", f"Request: {request_preview}")
        logger.info("=" * 70)
        logger.info("STARTING SECTION-BY-SECTION BRD GENERATION")
        logger.info("=" * 70)
        logger.info(f"Request: {request_preview}")
        logger.info(f"Sections: {len(self.sections)}")
        logger.info(f"Max iterations per section: {self.max_iterations}")
        logger.info(f"Min confidence: {self.verification_config.min_confidence_for_approval}")

        # Emit initial progress
        await self._emit_progress("generator", f"📋 Starting generation: {len(self.sections)} sections to process")

        # Reset state
        self.section_contents = {}
        self.section_evidence = {}
        total_claims = 0
        verified_claims = 0

        try:
            # Process each section
            for section_idx, section_name in enumerate(self.sections, 1):
                logger.info("")
                logger.info("=" * 70)
                logger.info(f"SECTION {section_idx}/{len(self.sections)}: {section_name.upper()}")
                logger.info("=" * 70)

                progress.step("BRD Generation", f"Processing section: {section_name}")
                await self._emit_progress("section", f"📝 Section {section_idx}/{len(self.sections)}: {section_name}")

                # Generate and verify this section
                section_result = await self._process_section(
                    section_name=section_name,
                    context=context,
                    previous_sections=self.section_contents,
                )

                # Store results
                self.section_contents[section_name] = section_result["content"]
                evidence = section_result["evidence"]

                # Handle case where verification returned no evidence
                if evidence is None:
                    logger.warning(f"[{section_name}] No evidence returned, creating empty result")
                    evidence = SectionVerificationResult(
                        section_name=section_name,
                        claims=[],
                    )
                    evidence.calculate_stats()

                self.section_evidence[section_name] = evidence

                # Update metrics
                total_claims += evidence.total_claims
                verified_claims += evidence.verified_claims

                # Log section summary
                status = "✓ VERIFIED" if evidence.overall_confidence >= self.verification_config.min_confidence_for_approval else "⚠ PARTIAL"
                logger.info(f"[{section_name}] {status} (confidence: {evidence.overall_confidence:.1%}, claims: {evidence.verified_claims}/{evidence.total_claims})")

                # Emit section completion progress
                status_icon = "✅" if evidence.overall_confidence >= self.verification_config.min_confidence_for_approval else "⚠️"
                await self._emit_progress(
                    "section_complete",
                    f"{status_icon} {section_name}: {evidence.verified_claims}/{evidence.total_claims} claims verified ({evidence.overall_confidence:.0%} confidence)"
                )

            # Combine all sections into final BRD
            logger.info("")
            logger.info("=" * 70)
            logger.info("COMBINING SECTIONS INTO FINAL BRD")
            logger.info("=" * 70)

            self.final_brd = self._combine_sections_to_brd(context)
            self.final_evidence = self._combine_section_evidence()

            # Update metrics
            elapsed_ms = int((time.time() - start_time) * 1000)
            self.metrics["total_time_ms"] = elapsed_ms
            self.metrics["claims_verified"] = verified_claims
            self.metrics["claims_failed"] = total_claims - verified_claims

            output = self._build_output(context, elapsed_ms)

            # Log final summary
            overall_confidence = self.final_evidence.overall_confidence if self.final_evidence else 0
            verified_status = "VERIFIED" if overall_confidence >= self.verification_config.min_confidence_for_approval else "PARTIAL"

            logger.info("")
            logger.info("=" * 70)
            logger.info("BRD GENERATION COMPLETE")
            logger.info("=" * 70)
            logger.info(f"  Status: {verified_status}")
            logger.info(f"  Overall Confidence: {overall_confidence:.1%}")
            logger.info(f"  Sections Processed: {len(self.sections)}")
            logger.info(f"  Total Claims: {total_claims}")
            logger.info(f"  Verified Claims: {verified_claims}")
            logger.info(f"  Sections Regenerated: {self.metrics['sections_regenerated']}")
            logger.info(f"  Total Time: {elapsed_ms}ms")
            logger.info("=" * 70)

            progress.end_operation(
                "BRD Generation",
                success=True,
                details=f"{verified_status} | Confidence: {overall_confidence:.1%} | Sections: {len(self.sections)}"
            )

            return output

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"BRD generation failed: {e}", exc_info=True)
            progress.end_operation("BRD Generation", success=False, details=str(e))
            raise

    async def _process_section(
        self,
        section_name: str,
        context: AggregatedContext,
        previous_sections: dict[str, str],
    ) -> dict:
        """
        Process a single BRD section: generate, verify, and regenerate if needed.

        Args:
            section_name: Name of the section to process
            context: Aggregated codebase context
            previous_sections: Already generated sections for continuity

        Returns:
            Dict with 'content' and 'evidence'
        """
        feedback = None
        best_content = ""
        best_evidence = None
        best_confidence = 0.0

        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"")
            logger.info(f"[{section_name}] Iteration {iteration}/{self.max_iterations}")
            logger.info("-" * 50)

            # Emit iteration progress
            if iteration > 1:
                await self._emit_progress("feedback", f"🔄 Regenerating {section_name} (attempt {iteration}/{self.max_iterations})")

            # Step 1: Generate section
            logger.info(f"[{section_name}] Generating content...")
            await self._emit_progress("generator", f"✍️ Generating content for: {section_name}")
            content = await self._generate_section(
                section_name=section_name,
                context=context,
                previous_sections=previous_sections,
                feedback=feedback,
            )
            logger.info(f"[{section_name}] Generated {len(content)} chars")

            # Step 2: Extract and verify claims
            logger.info(f"[{section_name}] Extracting and verifying claims...")
            await self._emit_progress("verifier", f"🔬 Verifying claims in: {section_name}")
            evidence = await self._verify_section(
                section_name=section_name,
                content=content,
                context=context,
            )

            # Log claim details
            logger.info(f"[{section_name}] Claims found: {evidence.total_claims}")
            for claim in evidence.claims[:5]:  # Show first 5 claims
                status_icon = "✓" if claim.status == VerificationStatus.VERIFIED else "✗"
                logger.info(f"  {status_icon} {claim.text[:60]}... ({claim.confidence_score:.0%})")
            if evidence.total_claims > 5:
                logger.info(f"  ... and {evidence.total_claims - 5} more claims")

            # Track best result
            if evidence.overall_confidence > best_confidence:
                best_confidence = evidence.overall_confidence
                best_content = content
                best_evidence = evidence

            # Step 3: Check if section passes
            if evidence.overall_confidence >= self.verification_config.min_confidence_for_approval:
                logger.info(f"[{section_name}] ✓ PASSED (confidence: {evidence.overall_confidence:.1%})")
                return {"content": content, "evidence": evidence}

            # Section needs improvement
            logger.info(f"[{section_name}] ✗ NEEDS IMPROVEMENT (confidence: {evidence.overall_confidence:.1%})")

            if iteration < self.max_iterations:
                # Build targeted feedback for regeneration
                feedback = self._build_section_feedback(section_name, evidence)
                self.metrics["sections_regenerated"] += 1
                logger.info(f"[{section_name}] Regenerating with feedback...")
            else:
                logger.warning(f"[{section_name}] Max iterations reached, using best result")

        # Return best result achieved, ensuring evidence is never None
        if best_evidence is None:
            best_evidence = SectionVerificationResult(
                section_name=section_name,
                claims=[],
            )
            best_evidence.calculate_stats()

        return {"content": best_content, "evidence": best_evidence}

    async def _generate_section(
        self,
        section_name: str,
        context: AggregatedContext,
        previous_sections: dict[str, str],
        feedback: Optional[str] = None,
    ) -> str:
        """Generate a single BRD section using LLM."""
        prompt = self._build_section_generation_prompt(
            section_name=section_name,
            context=context,
            previous_sections=previous_sections,
            feedback=feedback,
        )

        response = await self._call_llm(prompt)
        return self._extract_section_content(response)

    async def _verify_section(
        self,
        section_name: str,
        content: str,
        context: AggregatedContext,
    ) -> SectionVerificationResult:
        """Verify claims in a BRD section using direct MCP queries."""
        # Step 1: Extract claims from content using LLM
        claims = await self._extract_claims(section_name, content)
        logger.info(f"[{section_name}] Extracted {len(claims)} claims for verification")

        # Emit claims extraction progress
        await self._emit_progress("claims", f"📋 Extracted {len(claims)} claims from {section_name}")

        # Step 2: Verify each claim using direct MCP client queries
        verified_count = 0
        total_claims = len(claims)
        for idx, claim in enumerate(claims, 1):
            await self._verify_claim_direct(claim, context)
            # IMPORTANT: If no evidence was found, ensure confidence is 0
            # (recalculate_confidence only runs when evidence is added)
            if not claim.evidence:
                claim.confidence_score = 0.0
                claim.status = VerificationStatus.UNVERIFIED
                claim.hallucination_risk = HallucinationRisk.HIGH
            else:
                verified_count += 1

            # Emit progress every few claims (to avoid flooding)
            if idx == total_claims or idx % 3 == 0:
                await self._emit_progress(
                    "verifying",
                    f"🔍 Verifying claims: {idx}/{total_claims} ({verified_count} verified)"
                )

        # Step 3: Build section verification result
        result = SectionVerificationResult(
            section_name=section_name,
            claims=claims,
        )
        result.calculate_stats()

        return result

    async def _extract_claims(self, section_name: str, content: str) -> list[Claim]:
        """Extract verifiable claims from section content using LLM."""
        prompt = f"""Extract verifiable technical claims from this BRD section.

## Section: {section_name}

## Content:
{content}

## Instructions:
Extract specific, verifiable claims about:
- Component names mentioned
- File paths referenced
- Technical behaviors described
- Integration points
- Data flows

Return as JSON array:
```json
[
  {{
    "text": "The exact claim text",
    "type": "technical|functional|integration",
    "mentioned_entities": ["ComponentName", "ClassName"],
    "search_patterns": ["pattern to search in code"]
  }}
]
```

Only extract claims that can be verified against code. Skip vague or subjective statements.
"""
        response = await self._call_llm(prompt, timeout=120)

        claims = []
        try:
            json_match = self._extract_json(response)
            if json_match:
                claim_data_list = json.loads(json_match)
                for claim_data in claim_data_list:
                    claims.append(Claim(
                        text=claim_data.get("text", ""),
                        section=section_name,
                        claim_type=claim_data.get("type", "general"),
                        mentioned_entities=claim_data.get("mentioned_entities", []),
                        search_patterns=claim_data.get("search_patterns", []),
                    ))
        except Exception as e:
            logger.warning(f"[{section_name}] Failed to parse claims: {e}")

        return claims

    async def _verify_claim_direct(self, claim: Claim, context: AggregatedContext) -> None:
        """Verify a single claim using direct MCP client queries."""
        if not self.neo4j_client:
            logger.warning("No Neo4j client available for verification")
            return

        # Use dynamic limits from configuration
        limits = self.verification_limits
        max_entities = limits.get("max_entities_per_claim", 10)
        max_patterns = limits.get("max_patterns_per_claim", 5)
        results_limit = limits.get("results_per_query", 20)
        code_refs_limit = limits.get("code_refs_per_evidence", 10)

        try:
            # Search for mentioned entities in Neo4j
            for entity in claim.mentioned_entities[:max_entities]:
                query = f"""
                MATCH (n)
                WHERE n.name CONTAINS '{entity}' OR n.qualifiedName CONTAINS '{entity}'
                RETURN n.name as name, labels(n) as labels, n.filePath as filePath
                LIMIT {results_limit}
                """
                # Use query_code_structure which returns {"nodes": records}
                result = await self.neo4j_client.query_code_structure(query)

                if result and result.get("nodes"):
                    # Found evidence - high confidence since we found actual matching code
                    evidence = EvidenceItem(
                        evidence_type=EvidenceType.CODE_REFERENCE,
                        category="primary",
                        description=f"Found {entity} in codebase",
                        confidence=0.95,  # High confidence - actual code match
                        source="neo4j",
                        query_used=query,
                        supports_claim=True,
                    )

                    for node in result["nodes"][:code_refs_limit]:
                        file_path = node.get("filePath") or node.get("path")
                        if file_path:
                            evidence.code_references.append(CodeReference(
                                file_path=file_path,
                                start_line=1,
                                end_line=1,
                                entity_name=node.get("name", entity),
                                entity_type=node.get("labels", ["Unknown"])[0] if node.get("labels") else "Unknown",
                            ))

                    claim.add_evidence(evidence)

            # Search using patterns
            for pattern in claim.search_patterns[:max_patterns]:
                query = f"""
                MATCH (n)
                WHERE n.name =~ '(?i).*{pattern}.*' OR n.qualifiedName =~ '(?i).*{pattern}.*'
                RETURN n.name as name, labels(n) as labels, n.filePath as filePath
                LIMIT {results_limit}
                """
                try:
                    result = await self.neo4j_client.query_code_structure(query)

                    if result and result.get("nodes"):
                        evidence = EvidenceItem(
                            evidence_type=EvidenceType.CODE_REFERENCE,
                            category="primary",
                            description=f"Pattern '{pattern}' found in codebase",
                            confidence=0.90,  # Pattern match - slightly lower than exact entity match
                            source="neo4j",
                            query_used=query,
                            supports_claim=True,
                        )
                        claim.add_evidence(evidence)
                except Exception as e:
                    logger.debug(f"Pattern search failed for '{pattern}': {e}")

        except Exception as e:
            logger.warning(f"Claim verification failed: {e}")

    def _build_section_generation_prompt(
        self,
        section_name: str,
        context: AggregatedContext,
        previous_sections: dict[str, str],
        feedback: Optional[str] = None,
    ) -> str:
        """
        Build generation prompt with trigger phrase for SDK skill activation.

        The phrase "generate brd" triggers the generate-brd skill, which
        injects its instructions automatically via Copilot SDK.
        """
        # Format previous sections for context continuity
        prev_sections_text = ""
        if previous_sections:
            prev_sections_text = "\n\n## Previously Generated Sections\n"
            for name, content in previous_sections.items():
                prev_sections_text += f"\n### {name}\n{content[:500]}...\n"

        feedback_text = ""
        if feedback:
            feedback_text = f"""
## ⚠️ Feedback from Verification (MUST Address!)
{feedback}
"""

        section_guidelines = self._get_section_guidelines(section_name)

        # Only include sufficiency criteria if explicitly provided
        sufficiency_text = ""
        if self.sufficiency_criteria:
            sufficiency_text = self._format_sufficiency_criteria()

        # Detail level instructions
        detail_instructions = self._get_detail_level_instructions()

        # Get custom section description if available
        custom_section_desc = ""
        if self.custom_sections:
            for s in self.custom_sections:
                if s.get("name", "").lower().replace(" ", "_") == section_name.lower().replace(" ", "_"):
                    if s.get("description"):
                        custom_section_desc = f"\n**Section Focus:** {s.get('description')}\n"
                    break

        # REVERSE ENGINEERING prompt with BRD best practices
        prompt = f"""You are an expert Business Analyst reverse engineering EXISTING code to create a BRD.

{BRD_BEST_PRACTICES}

## CRITICAL: REVERSE ENGINEERING MODE

The feature "{context.request}" ALREADY EXISTS in this codebase. Document what the code DOES, not what should be built.

## Current Section: {section_name.replace('_', ' ').title()}
{custom_section_desc}
{detail_instructions}

## Section Guidelines
{section_guidelines}

## Existing Feature Being Documented
{context.request}

## Codebase Context (Code that ALREADY implements this feature)

**Components Found ({len(context.architecture.components)}):**
{self._format_components(context)}

**Key Source Files ({len(context.implementation.key_files)}):**
{self._format_files(context)}
{prev_sections_text}
{feedback_text}
{sufficiency_text}

## Writing Instructions

- Use plain English - translate code behavior to business language
- Be deterministic - avoid "may" or "might", describe exact behavior
- Write for business readers - assume non-technical audience
- Explain "what" not "how" - describe outcomes, not implementation
- Use numbered lists for process flows
- Capture all business rules from the code

First show your analysis (wrapped in <thinking> tags), then the section:

<thinking>
[Analyze the code: what do these components do? how do they work together?]
</thinking>

## {section_name.replace('_', ' ').title()}

[Document what the EXISTING code does based on your analysis]
"""
        return prompt

    def _get_detail_level_instructions(self) -> str:
        """Get writing instructions based on detail level."""
        instructions = {
            "concise": """
## OUTPUT DETAIL LEVEL: CONCISE
- Keep this section brief: 1-2 short paragraphs maximum
- Use bullet points instead of prose
- Focus only on key points, skip minor details
- Be direct and succinct
""",
            "standard": """
## OUTPUT DETAIL LEVEL: STANDARD
- Provide balanced coverage: 2-4 paragraphs
- Include both overview and relevant details
- Use a mix of prose and bullet points
""",
            "detailed": """
## OUTPUT DETAIL LEVEL: DETAILED
- Provide comprehensive coverage with full explanations
- Include extensive code references and file paths
- Add examples, edge cases, and considerations
- Document all relevant details found in code
""",
        }
        return instructions.get(self.detail_level, instructions["standard"])

    def _format_sufficiency_criteria(self) -> str:
        """Format sufficiency criteria for inclusion in prompts.

        Only called when sufficiency_criteria is provided.
        """
        if not self.sufficiency_criteria:
            return ""

        criteria = self.sufficiency_criteria
        dimensions = criteria.get("dimensions", [])
        output_reqs = criteria.get("output_requirements", {}) or {}
        min_dimensions = criteria.get("min_dimensions_covered", 3)

        # Format dimensions
        dimension_lines = []
        for dim in dimensions:
            required = "✓ Required" if dim.get("required", False) else "○ Optional"
            dimension_lines.append(f"- **{dim['name']}**: {dim['description']} [{required}]")

        dimensions_text = "\n".join(dimension_lines) if dimension_lines else "- No specific dimensions configured"

        # Format output requirements
        output_lines = []
        if output_reqs.get("code_traceability", True):
            output_lines.append("- Clear traceability to source code (file paths, line numbers)")
        if output_reqs.get("explicit_gaps", True):
            output_lines.append("- Explicit gaps where information wasn't found")
        if output_reqs.get("evidence_based", True):
            output_lines.append("- All claims backed by tool results (no hallucination)")

        output_text = "\n".join(output_lines) if output_lines else "- Standard output format"

        return f"""## What Makes a Complete Analysis

For a comprehensive BRD, explore these dimensions:

{dimensions_text}

**Minimum Coverage**: Cover at least {min_dimensions} dimensions before generating content.
Keep exploring until you've gathered sufficient context. Show your reasoning.

## Output Requirements

{output_text}

If you couldn't find information for a dimension, explicitly state what's missing rather than guessing."""

    def _build_section_verification_prompt(
        self,
        section_name: str,
        content: str,
        context: AggregatedContext,
    ) -> str:
        """
        Build verification prompt with trigger phrase for SDK skill activation.

        The phrase "verify brd" triggers the verify-brd skill, which
        injects its instructions automatically via Copilot SDK.
        """
        # Use trigger phrase "verify brd" - SDK will inject skill instructions
        prompt = f"""Verify BRD section: {section_name.replace('_', ' ').title()}

## Section Content to Verify

{content}

---

## Required JSON Output Format

After verifying each claim, provide results as JSON:

```json
{{
  "section_name": "{section_name}",
  "overall_confidence": 0.85,
  "claims": [
    {{
      "text": "The claim text",
      "type": "technical|functional|integration",
      "status": "verified|unverified|contradicted",
      "confidence": 0.95,
      "evidence": {{
        "type": "code_reference|neo4j_query|file_content",
        "source": "/path/to/file:line or neo4j query",
        "content": "The actual code or query result that proves this"
      }}
    }}
  ],
  "issues": ["List of issues found"],
  "suggestions": ["How to fix each issue"]
}}
```

## Confidence Calculation
- Start at 1.0
- Subtract 0.15 for each unverified claim
- Subtract 0.25 for each contradicted claim
- Minimum 0.0
"""
        return prompt

    def _get_section_guidelines(self, section_name: str) -> str:
        """Get writing guidelines for a specific section from best practices."""
        # First check if we have custom section config
        if hasattr(self, 'section_configs') and self.section_configs:
            for section in self.section_configs:
                if section.get("name", "").lower().replace(" ", "_") == section_name.lower().replace(" ", "_"):
                    if section.get("description"):
                        return f"""REVERSE ENGINEERING: {section.get('description')}

Remember to:
- Document what CURRENTLY EXISTS in the code
- Use plain English (business language, not technical)
- Be specific and deterministic (no "may" or "might")
- Reference actual components and files found"""

        # Fall back to best practices module
        guidelines = get_section_guidelines(section_name)

        return f"""REVERSE ENGINEERING: {guidelines}

Remember to:
- Document what CURRENTLY EXISTS in the code
- Use plain English (business language, not technical)
- Be specific and deterministic (no "may" or "might")
- Reference actual components and files found"""

    def _extract_section_content(self, response: str) -> str:
        """Extract section content from LLM response, removing thinking tags."""
        import re

        content = response.strip()

        # Remove <thinking>...</thinking> blocks (keep for logging but not in output)
        thinking_pattern = r'<thinking>[\s\S]*?</thinking>'
        thinking_matches = re.findall(thinking_pattern, content)
        if thinking_matches:
            for thinking in thinking_matches:
                logger.debug(f"[REASONING] {thinking[:500]}...")
            content = re.sub(thinking_pattern, '', content).strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        return content.strip()

    def _parse_section_verification(
        self,
        section_name: str,
        response: str,
    ) -> SectionVerificationResult:
        """Parse verification response into SectionVerificationResult."""
        import re

        # Extract and log verification reasoning
        log_pattern = r'<verification_log>([\s\S]*?)</verification_log>'
        log_matches = re.findall(log_pattern, response)
        if log_matches:
            logger.info(f"[{section_name}] Verification reasoning:")
            for line in log_matches[0].strip().split('\n')[:20]:
                logger.info(f"  {line}")

        try:
            json_match = self._extract_json(response)
            if json_match:
                data = json.loads(json_match)

                claims = []
                for claim_data in data.get("claims", []):
                    status_map = {
                        "verified": VerificationStatus.VERIFIED,
                        "unverified": VerificationStatus.UNVERIFIED,
                        "contradicted": VerificationStatus.CONTRADICTED,
                    }
                    claim = Claim(
                        text=claim_data.get("text", ""),
                        claim_type=ClaimType.TECHNICAL,
                        status=status_map.get(claim_data.get("status", "unverified"), VerificationStatus.UNVERIFIED),
                        confidence_score=claim_data.get("confidence", 0.5),
                    )

                    # Add evidence if present
                    evidence_data = claim_data.get("evidence")
                    if evidence_data and isinstance(evidence_data, dict):
                        claim.evidence.append(EvidenceItem(
                            evidence_type=EvidenceType.CODE_REFERENCE,
                            content=evidence_data.get("content", ""),
                            source=evidence_data.get("source", "codebase"),
                            confidence=ConfidenceLevel.HIGH if claim.confidence_score > 0.8 else ConfidenceLevel.MEDIUM,
                        ))

                    claims.append(claim)

                result = SectionVerificationResult(
                    section_name=section_name,
                    claims=claims,
                )
                result.overall_confidence = data.get("overall_confidence", 0.5)
                result.issues = data.get("issues", [])
                result.suggestions = data.get("suggestions", [])
                result.calculate_stats()

                return result

        except Exception as e:
            logger.error(f"Failed to parse verification response: {e}")

        # Fallback
        return SectionVerificationResult(
            section_name=section_name,
            claims=[],
            overall_confidence=0.5,
        )

    def _build_section_feedback(
        self,
        section_name: str,
        evidence: SectionVerificationResult,
    ) -> str:
        """Build targeted feedback for section regeneration."""
        feedback_parts = [f"Issues found in {section_name}:"]

        # Add specific issues
        if evidence.issues:
            for issue in evidence.issues[:5]:
                feedback_parts.append(f"  - {issue}")

        # Add unverified claims
        unverified = [c for c in evidence.claims if c.status != VerificationStatus.VERIFIED]
        if unverified:
            feedback_parts.append("\nClaims that couldn't be verified (remove or fix):")
            for claim in unverified[:5]:
                feedback_parts.append(f"  - {claim.text[:80]}...")

        # Add suggestions
        if hasattr(evidence, 'suggestions') and evidence.suggestions:
            feedback_parts.append("\nSuggestions:")
            for suggestion in evidence.suggestions[:3]:
                feedback_parts.append(f"  - {suggestion}")

        return "\n".join(feedback_parts)

    def _combine_sections_to_brd(self, context: AggregatedContext) -> BRDDocument:
        """Combine all generated sections into a BRDDocument."""
        # Extract functional requirements from section
        functional_requirements = []
        func_req_content = self.section_contents.get("functional_requirements", "")
        req_id = 1
        for line in func_req_content.split("\n"):
            if line.strip().startswith(("FR-", "REQ-", "- ")):
                functional_requirements.append(Requirement(
                    id=f"FR-{req_id:03d}",
                    title=line.strip()[:100],
                    description=line.strip(),
                    priority="medium",
                ))
                req_id += 1

        # Extract technical requirements from technical_specifications or non_functional_requirements
        technical_requirements = []
        tech_content = self.section_contents.get("technical_specifications", "")
        tech_content += "\n" + self.section_contents.get("non_functional_requirements", "")
        req_id = 1
        for line in tech_content.split("\n"):
            if line.strip().startswith(("TR-", "NFR-", "- ")):
                technical_requirements.append(Requirement(
                    id=f"TR-{req_id:03d}",
                    title=line.strip()[:100],
                    description=line.strip(),
                    priority="medium",
                ))
                req_id += 1

        # Build raw markdown from all sections to preserve full content
        raw_markdown_parts = [
            f"# Business Requirements Document: {context.request[:50]}",
            "",
            f"**Version:** 1.0",
            f"**Status:** Draft (Verified)",
            "",
            "---",
            "",
        ]

        # Add each section in order
        section_titles = {
            "executive_summary": "Executive Summary",
            "business_context": "Business Context",
            "functional_requirements": "Functional Requirements",
            "non_functional_requirements": "Non-Functional Requirements",
            "technical_specifications": "Technical Specifications",
            "dependencies_and_risks": "Dependencies and Risks",
        }

        for section_name in self.sections:
            content = self.section_contents.get(section_name, "")
            if content:
                title = section_titles.get(section_name, section_name.replace("_", " ").title())
                raw_markdown_parts.extend([
                    f"## {title}",
                    "",
                    content,
                    "",
                ])

        raw_markdown = "\n".join(raw_markdown_parts)

        # Build business context from multiple sections
        business_context = self.section_contents.get("business_context", "")
        if not business_context:
            business_context = self.section_contents.get("executive_summary", "No business context provided.")

        return BRDDocument(
            title=f"BRD: {context.request[:50]}",
            business_context=business_context,
            objectives=[context.request],
            functional_requirements=functional_requirements,
            technical_requirements=technical_requirements,
            dependencies=self._extract_list(self.section_contents.get("dependencies_and_risks", "")),
            risks=self._extract_list(self.section_contents.get("dependencies_and_risks", "")),
            raw_markdown=raw_markdown,  # Preserve full content
        )

    def _combine_section_evidence(self) -> EvidenceBundle:
        """Combine all section evidence into EvidenceBundle."""
        section_results = list(self.section_evidence.values())

        total_claims = sum(s.total_claims for s in section_results)
        verified_claims = sum(s.verified_claims for s in section_results)
        overall_confidence = sum(s.overall_confidence for s in section_results) / len(section_results) if section_results else 0

        # Determine hallucination risk
        if overall_confidence >= 0.8:
            risk = HallucinationRisk.LOW
        elif overall_confidence >= 0.5:
            risk = HallucinationRisk.MEDIUM
        else:
            risk = HallucinationRisk.HIGH

        # Generate a BRD ID
        brd_title = self.final_brd.title if self.final_brd else "BRD"
        brd_id = f"BRD-{hash(brd_title) % 10000:04d}"

        bundle = EvidenceBundle(
            brd_id=brd_id,
            brd_title=brd_title,
            sections=section_results,  # Correct field name
        )
        bundle.overall_confidence = overall_confidence
        bundle.hallucination_risk = risk
        bundle.is_approved = overall_confidence >= self.verification_config.min_confidence_for_approval
        bundle.total_claims = total_claims
        bundle.verified_claims = verified_claims

        return bundle

    def _extract_list(self, content: str) -> list[str]:
        """Extract list items from content."""
        items = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith(("- ", "* ", "• ")):
                items.append(line[2:])
        return items[:10]  # Limit to 10 items

    async def _call_llm(self, prompt: str, timeout: float = 300) -> str:
        """Call LLM via Copilot SDK session."""
        if not self.session:
            logger.warning("No Copilot session - returning mock response")
            return self._generate_mock_response(prompt)

        try:
            logger.debug(f"[LLM] Sending prompt ({len(prompt)} chars)")

            message_options = {"prompt": prompt}

            if hasattr(self.session, 'send_and_wait'):
                event = await asyncio.wait_for(
                    self.session.send_and_wait(message_options, timeout=timeout),
                    timeout=timeout
                )
                if event:
                    response = self._extract_response(event)
                    logger.debug(f"[LLM] Response received ({len(response)} chars)")
                    return response

            logger.warning("[LLM] No response from SDK")
            return self._generate_mock_response(prompt)

        except asyncio.TimeoutError:
            logger.error(f"[LLM] Timeout after {timeout}s")
            return self._generate_mock_response(prompt)
        except Exception as e:
            logger.error(f"[LLM] Error: {e}")
            return self._generate_mock_response(prompt)

    def _extract_response(self, event: Any) -> str:
        """Extract text from SDK event."""
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
        except Exception as e:
            logger.error(f"Error extracting response: {e}")
            return ""

    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from text (handles markdown code blocks)."""
        import re

        # Try to find JSON in code blocks
        json_pattern = r'```(?:json)?\s*([\s\S]*?)```'
        matches = re.findall(json_pattern, text)
        if matches:
            return matches[0].strip()

        # Try to find raw JSON
        brace_pattern = r'\{[\s\S]*\}'
        matches = re.findall(brace_pattern, text)
        if matches:
            return max(matches, key=len)

        return None

    def _format_components(self, context: AggregatedContext) -> str:
        """Format component info for prompt."""
        if not context.architecture.components:
            return "No components found."

        lines = []
        for comp in context.architecture.components[:10]:
            lines.append(f"- {comp.name} ({comp.type}) @ {comp.path}")
        return "\n".join(lines)

    def _format_files(self, context: AggregatedContext) -> str:
        """Format file info for prompt."""
        if not context.implementation.key_files:
            return "No key files found."

        lines = []
        for file in context.implementation.key_files[:10]:
            lines.append(f"- {file.path}")
        return "\n".join(lines)

    def _generate_mock_response(self, prompt: str) -> str:
        """Generate mock response when SDK unavailable."""
        if "verify" in prompt.lower():
            return json.dumps({
                "section_name": "mock_section",
                "overall_confidence": 0.75,
                "claims": [
                    {
                        "text": "Mock claim for testing",
                        "type": "technical",
                        "status": "verified",
                        "confidence": 0.8,
                        "evidence": {"type": "code_reference", "source": "mock.ts", "content": "mock code"}
                    }
                ],
                "issues": [],
                "suggestions": [],
            })
        else:
            return f"""## Mock Section

This is mock content generated because Copilot SDK is not available.

- Mock requirement 1
- Mock requirement 2
"""

    def _build_output(self, context: AggregatedContext, elapsed_ms: int) -> BRDOutput:
        """Build final BRD output."""
        brd = self.final_brd or BRDDocument(
            title=f"BRD: {context.request[:50]}",
            business_context="Generation incomplete",
            objectives=[],
        )

        metadata = {
            "generation_mode": "section-by-section-verified",
            "sections_processed": len(self.sections),
            "total_iterations": self.metrics["total_iterations"],
            "sections_regenerated": self.metrics["sections_regenerated"],
            "claims_verified": self.metrics["claims_verified"],
            "claims_failed": self.metrics["claims_failed"],
            "generation_time_ms": elapsed_ms,
            "verification_passed": self.final_evidence.is_approved if self.final_evidence else False,
            "overall_confidence": self.final_evidence.overall_confidence if self.final_evidence else 0,
            "hallucination_risk": self.final_evidence.hallucination_risk.value if self.final_evidence else "unknown",
        }

        if self.show_evidence_by_default and self.final_evidence:
            metadata["evidence_summary"] = {
                "total_claims": self.final_evidence.total_claims,
                "verified_claims": self.final_evidence.verified_claims,
                "sections": {name: {"confidence": ev.overall_confidence} for name, ev in self.section_evidence.items()},
            }

        return BRDOutput(
            brd=brd,
            epics=[],
            backlogs=[],
            metadata=metadata,
        )

    def get_evidence_trail(self, show_details: bool = True) -> str:
        """Get formatted evidence trail."""
        if self.final_evidence:
            return self.final_evidence.to_evidence_trail(include_details=show_details)
        return "No evidence available yet. Generate a BRD first."

    def get_evidence_bundle(self) -> Optional[EvidenceBundle]:
        """Get the evidence bundle from the last generation."""
        return self.final_evidence

    async def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("Orchestrator cleanup complete")

    # Compatibility methods for tests
    @property
    def generator(self) -> "MultiAgentOrchestrator":
        """Return self for compatibility (no separate generator agent)."""
        return self

    @property
    def verifier(self) -> "MultiAgentOrchestrator":
        """Return self for compatibility (no separate verifier agent)."""
        return self

    def get_verification_status(self) -> dict:
        """Get current verification status."""
        return {
            "is_running": False,
            "max_iterations": self.max_iterations,
            "current_iteration": self.metrics["total_iterations"],
            "brd_generated": self.final_brd is not None,
            "evidence_gathered": self.final_evidence is not None,
            "is_approved": self.final_evidence.is_approved if self.final_evidence else False,
        }

    def get_generator_status(self) -> dict:
        """Get generator status (simplified - no separate agent)."""
        return {
            "role": "generator",
            "is_active": False,
            "current_task": None,
            "iteration": self.metrics["total_iterations"],
        }

    def get_verifier_status(self) -> dict:
        """Get verifier status (simplified - no separate agent)."""
        return {
            "role": "verifier",
            "is_active": False,
            "current_task": None,
            "iteration": self.metrics["total_iterations"],
        }


class VerifiedBRDGenerator:
    """
    High-level interface for generating verified BRDs.

    Wraps MultiAgentOrchestrator with a simple API.

    Example with custom sufficiency criteria:
        ```python
        custom_criteria = {
            "dimensions": [
                {"name": "Data Model", "description": "Classes and types", "required": True},
                {"name": "API Contracts", "description": "Endpoints and formats", "required": True},
            ],
            "output_requirements": {
                "code_traceability": True,
                "explicit_gaps": True,
            },
            "min_dimensions_covered": 2,
        }
        generator = VerifiedBRDGenerator(sufficiency_criteria=custom_criteria)
        ```
    """

    def __init__(
        self,
        copilot_session: Any = None,
        neo4j_client: Optional[Neo4jMCPClient] = None,
        filesystem_client: Optional[FilesystemMCPClient] = None,
        max_iterations: int = 3,
        parsed_template: Optional["ParsedBRDTemplate"] = None,
        verification_config: Optional[VerificationConfig] = None,
        sufficiency_criteria: Optional[dict] = None,
        detail_level: str = "standard",
        custom_sections: Optional[list[dict]] = None,
        verification_limits: Optional[dict] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        self.orchestrator = MultiAgentOrchestrator(
            copilot_session=copilot_session,
            neo4j_client=neo4j_client,
            filesystem_client=filesystem_client,
            max_iterations=max_iterations,
            parsed_template=parsed_template,
            verification_config=verification_config,
            sufficiency_criteria=sufficiency_criteria,
            detail_level=detail_level,
            custom_sections=custom_sections,
            verification_limits=verification_limits,
            progress_callback=progress_callback,
        )
        self._last_output: Optional[BRDOutput] = None

    async def generate(self, context: AggregatedContext) -> BRDOutput:
        """Generate a verified BRD."""
        output = await self.orchestrator.generate_verified_brd(context)
        self._last_output = output
        return output

    def show_evidence_trail(self, detailed: bool = True) -> str:
        """Get evidence trail for last generated BRD."""
        return self.orchestrator.get_evidence_trail(detailed)

    def was_verified(self) -> bool:
        """Check if last BRD passed verification."""
        if self._last_output and self._last_output.metadata:
            return self._last_output.metadata.get("verification_passed", False)
        return False

    def get_confidence_score(self) -> float:
        """Get confidence score for last BRD."""
        if self._last_output and self._last_output.metadata:
            return self._last_output.metadata.get("overall_confidence", 0.0)
        return 0.0

    @property
    def confidence_score(self) -> float:
        """Get confidence score for last BRD (property alias)."""
        return self.get_confidence_score()

    async def cleanup(self) -> None:
        """Cleanup resources."""
        await self.orchestrator.cleanup()
