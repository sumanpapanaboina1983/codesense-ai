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
        temperature: float = 0.0,
        seed: Optional[int] = None,
        claims_per_section: int = 5,
        default_section_words: Optional[int] = None,
        skip_verification: bool = False,
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
            temperature: LLM temperature (0.0-1.0, lower = more consistent). Default 0.0.
            seed: Optional seed for reproducible outputs
            claims_per_section: Target number of claims to extract per section (default: 5)
            default_section_words: Default target word count per section (None = no limit)
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

        # Consistency controls for reproducible outputs
        self.temperature = max(0.0, min(1.0, temperature))  # Clamp to 0-1
        self.seed = seed
        logger.info(f"Consistency settings: temperature={self.temperature}, seed={self.seed}")

        # Claim extraction and section length controls
        self.claims_per_section = max(3, min(15, claims_per_section))  # Clamp to 3-15
        # Only clamp if explicitly set, otherwise None means no limit
        if default_section_words is not None:
            self.default_section_words = max(100, min(5000, default_section_words))  # Clamp to 100-5000
        else:
            self.default_section_words = None  # No length restriction
        logger.info(f"Content controls: claims_per_section={self.claims_per_section}, default_section_words={self.default_section_words or 'unlimited'}")

        # Draft mode - skip verification for faster generation
        self.skip_verification = skip_verification
        if skip_verification:
            logger.info("DRAFT MODE: Verification will be skipped (single-pass generation)")
        else:
            logger.info("VERIFIED MODE: Claims will be verified against codebase")

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
        # DRAFT MODE: Skip verification loop, just generate once
        if self.skip_verification:
            logger.info(f"[{section_name}] DRAFT MODE: Generating content (no verification)")
            await self._emit_progress("generator", f"✍️ Generating content for: {section_name}")

            content = await self._generate_section(
                section_name=section_name,
                context=context,
                previous_sections=previous_sections,
                feedback=None,
            )
            logger.info(f"[{section_name}] Generated {len(content)} chars")

            # Create empty evidence (no verification in draft mode)
            evidence = SectionVerificationResult(
                section_name=section_name,
                claims=[],
            )
            evidence.calculate_stats()

            return {"content": content, "evidence": evidence}

        # VERIFIED MODE: Full verification loop
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
        """Extract verifiable claims from section content using LLM.

        Uses self.claims_per_section to ensure consistent claim counts.
        """
        target_claims = self.claims_per_section

        prompt = f"""Extract exactly {target_claims} verifiable technical claims from this BRD section.

## Section: {section_name}

## Content:
{content}

## Instructions:
Extract EXACTLY {target_claims} specific, verifiable claims. Prioritize the most important claims.

Focus on claims about:
- Component names and their responsibilities
- File paths and code locations
- Technical behaviors and business rules
- Integration points and APIs
- Data flows and transformations

Return as JSON array with exactly {target_claims} claims:
```json
[
  {{
    "text": "The exact claim text from the BRD",
    "type": "technical|functional|integration|business_rule",
    "mentioned_entities": ["ComponentName", "ClassName", "MethodName"],
    "search_patterns": ["pattern to search in code"],
    "priority": 1
  }}
]
```

IMPORTANT:
- Return exactly {target_claims} claims, no more, no less
- Order by priority (1 = most important)
- Skip vague or subjective statements
- Each claim should be specific enough to verify against code
"""
        response = await self._call_llm(prompt, timeout=120)

        claims = []
        try:
            json_match = self._extract_json(response)
            if json_match:
                parsed = json.loads(json_match)

                # Handle different response formats
                claim_data_list = []
                if isinstance(parsed, list):
                    claim_data_list = parsed
                elif isinstance(parsed, dict):
                    # Maybe the LLM wrapped claims in an object
                    claim_data_list = parsed.get("claims", [])
                    if not claim_data_list and "text" in parsed:
                        # Single claim returned as object
                        claim_data_list = [parsed]

                # Take exactly the target number of claims
                for claim_data in claim_data_list[:target_claims]:
                    if not isinstance(claim_data, dict):
                        continue
                    text = claim_data.get("text", "")
                    if not text:
                        continue
                    claims.append(Claim(
                        text=text,
                        section=section_name,
                        claim_type=claim_data.get("type", "general"),
                        mentioned_entities=claim_data.get("mentioned_entities", []) if isinstance(claim_data.get("mentioned_entities"), list) else [],
                        search_patterns=claim_data.get("search_patterns", []) if isinstance(claim_data.get("search_patterns"), list) else [],
                    ))

                # If we got fewer claims than requested, log it
                if len(claims) < target_claims:
                    logger.info(f"[{section_name}] Extracted {len(claims)} claims (target: {target_claims})")
        except json.JSONDecodeError as e:
            logger.warning(f"[{section_name}] Invalid JSON in claims response: {e}")
        except Exception as e:
            logger.warning(f"[{section_name}] Failed to parse claims: {type(e).__name__}: {e}")

        return claims

    async def _verify_claim_direct(self, claim: Claim, context: AggregatedContext) -> None:
        """Verify a single claim using direct MCP client queries and fetch actual code."""
        if not self.neo4j_client:
            logger.warning("No Neo4j client available for verification")
            return

        # Use dynamic limits from configuration
        limits = self.verification_limits
        max_entities = limits.get("max_entities_per_claim", 10)
        max_patterns = limits.get("max_patterns_per_claim", 5)
        results_limit = limits.get("results_per_query", 20)
        code_refs_limit = limits.get("code_refs_per_evidence", 5)

        code_snippets_found = []

        try:
            # Search for mentioned entities in Neo4j - get detailed code info
            for entity in claim.mentioned_entities[:max_entities]:
                # Query for methods/classes with their code locations
                query = f"""
                MATCH (n)
                WHERE n.name CONTAINS '{entity}' OR n.qualifiedName CONTAINS '{entity}'
                OPTIONAL MATCH (n)-[:CONTAINS|DECLARES|HAS_METHOD]->(m)
                RETURN n.name as name, labels(n) as labels, n.filePath as filePath,
                       n.startLine as startLine, n.endLine as endLine,
                       n.sourceCode as sourceCode, n.body as body,
                       collect(DISTINCT m.name) as members
                LIMIT {results_limit}
                """
                result = await self.neo4j_client.query_code_structure(query)

                if result and result.get("nodes"):
                    for node in result["nodes"][:code_refs_limit]:
                        file_path = node.get("filePath") or node.get("path")
                        if not file_path:
                            continue

                        entity_name = node.get("name", entity)
                        entity_type = node.get("labels", ["Unknown"])[0] if node.get("labels") else "Unknown"
                        start_line = node.get("startLine", 1) or 1
                        end_line = node.get("endLine", start_line + 10) or start_line + 10

                        # Try to get actual code snippet
                        snippet = node.get("sourceCode") or node.get("body")
                        if not snippet and self.filesystem_client:
                            try:
                                # Translate Neo4j path to backend filesystem path
                                # Neo4j stores: /app/repos/... but backend has: /codebase/...
                                actual_file_path = file_path
                                if file_path.startswith("/app/repos/"):
                                    actual_file_path = file_path.replace("/app/repos/", "/codebase/", 1)

                                # Fetch code from file
                                file_content = await self.filesystem_client.read_file(actual_file_path)
                                if file_content:
                                    lines = file_content.split('\n')
                                    # Get lines around the entity (±10 lines for context)
                                    start_idx = max(0, start_line - 1)
                                    end_idx = min(len(lines), end_line + 5)
                                    snippet = '\n'.join(lines[start_idx:end_idx])
                            except Exception as e:
                                logger.debug(f"Could not read file {file_path}: {e}")

                        # Add entity even without snippet (partial evidence)
                        # Having file location is valuable for verification
                        code_snippets_found.append({
                            "file_path": file_path,
                            "start_line": start_line,
                            "end_line": end_line,
                            "snippet": snippet[:500] if snippet else f"[Entity found: {entity_name} in {file_path}:{start_line}]",
                            "entity_name": entity_name,
                            "entity_type": entity_type,
                            "members": node.get("members", []),
                            "has_full_snippet": bool(snippet),  # Track if we have actual code
                        })

            # Search using patterns for additional evidence
            for pattern in claim.search_patterns[:max_patterns]:
                query = f"""
                MATCH (n)
                WHERE n.name =~ '(?i).*{pattern}.*' OR n.qualifiedName =~ '(?i).*{pattern}.*'
                RETURN n.name as name, labels(n) as labels, n.filePath as filePath,
                       n.startLine as startLine, n.endLine as endLine,
                       n.sourceCode as sourceCode
                LIMIT {results_limit}
                """
                try:
                    result = await self.neo4j_client.query_code_structure(query)
                    if result and result.get("nodes"):
                        for node in result["nodes"][:2]:  # Limit pattern results
                            file_path = node.get("filePath")
                            if not file_path:
                                continue
                            snippet = node.get("sourceCode")
                            entity_name = node.get("name", pattern)
                            start_line = node.get("startLine", 1) or 1
                            end_line = node.get("endLine", 10) or 10
                            # Add entity even without snippet (partial evidence)
                            code_snippets_found.append({
                                "file_path": file_path,
                                "start_line": start_line,
                                "end_line": end_line,
                                "snippet": snippet[:500] if snippet else f"[Pattern match: {entity_name} in {file_path}:{start_line}]",
                                "entity_name": entity_name,
                                "entity_type": node.get("labels", ["Code"])[0] if node.get("labels") else "Code",
                                "has_full_snippet": bool(snippet),
                            })
                except Exception as e:
                    logger.debug(f"Pattern search failed for '{pattern}': {e}")

            # If we found code, use LLM to explain how it supports the claim
            if code_snippets_found:
                # Check how many have full snippets vs just entity locations
                full_snippet_count = sum(1 for s in code_snippets_found if s.get("has_full_snippet", True))
                has_any_full_snippets = full_snippet_count > 0

                # Only call LLM if we have actual code snippets to analyze
                if has_any_full_snippets:
                    explanation = await self._explain_code_evidence(claim.text, code_snippets_found[:3])
                else:
                    # Partial evidence - entities found but no code snippets
                    entity_names = [s["entity_name"] for s in code_snippets_found[:3]]
                    explanation = {
                        "supports": True,
                        "summary": f"Code entities found: {', '.join(entity_names)}. Located in codebase but source code not available for detailed analysis.",
                        "explanation": "Entities matching the claim were found in the code graph. Their presence indicates the functionality exists, though detailed code analysis was not possible.",
                    }

                # Adjust confidence based on evidence quality
                if explanation.get("supports"):
                    if has_any_full_snippets:
                        base_confidence = 0.9  # Full evidence with code
                    else:
                        base_confidence = 0.6  # Partial evidence - entities found but no snippets
                else:
                    base_confidence = 0.4 if has_any_full_snippets else 0.3

                evidence = EvidenceItem(
                    evidence_type=EvidenceType.CODE_REFERENCE,
                    category="primary",
                    description=explanation.get("summary", "Code found that implements this functionality"),
                    confidence=base_confidence,
                    source="neo4j",
                    supports_claim=explanation.get("supports", True),
                    notes=explanation.get("explanation"),
                )

                # Add code references with per-snippet explanations
                for i, snippet_info in enumerate(code_snippets_found[:code_refs_limit]):
                    snippet_explanation = None
                    if explanation.get("snippet_explanations") and i < len(explanation["snippet_explanations"]):
                        snippet_explanation = explanation["snippet_explanations"][i]

                    evidence.code_references.append(CodeReference(
                        file_path=snippet_info["file_path"],
                        start_line=snippet_info["start_line"],
                        end_line=snippet_info["end_line"],
                        snippet=snippet_info["snippet"],
                        entity_name=snippet_info["entity_name"],
                        entity_type=snippet_info["entity_type"],
                    ))
                    # Store explanation in notes if not already set
                    if snippet_explanation and not evidence.notes:
                        evidence.notes = snippet_explanation

                claim.add_evidence(evidence)
            else:
                logger.debug(f"No code snippets found for claim: {claim.text[:50]}...")

        except Exception as e:
            logger.warning(f"Claim verification failed: {e}")

    async def _explain_code_evidence(self, claim_text: str, code_snippets: list[dict]) -> dict:
        """Use LLM to explain how code snippets support the claim."""
        if not code_snippets:
            return {"supports": False, "summary": "No code found", "explanation": None}

        # Format code snippets for the prompt
        snippets_text = ""
        for i, snippet in enumerate(code_snippets, 1):
            snippets_text += f"""
### Code {i}: {snippet['entity_name']} ({snippet['entity_type']})
File: {snippet['file_path']}:{snippet['start_line']}-{snippet['end_line']}
```
{snippet['snippet'][:400]}
```
"""

        prompt = f"""Analyze if this code supports the following claim from a BRD.

## Claim:
"{claim_text}"

## Code Found:
{snippets_text}

## Task:
1. Does this code implement/support the claim? (yes/no)
2. Provide a brief summary (1 sentence) of how the code supports this claim
3. For each code snippet, explain specifically what part implements the claim

Return as JSON:
```json
{{
  "supports": true,
  "summary": "Brief summary of how code implements the claim",
  "explanation": "Detailed explanation of the implementation",
  "snippet_explanations": [
    "Explanation for code 1",
    "Explanation for code 2"
  ]
}}
```
"""
        try:
            response = await self._call_llm(prompt, timeout=60)
            json_match = self._extract_json(response)
            if json_match:
                return json.loads(json_match)
        except Exception as e:
            logger.debug(f"Failed to get code explanation: {e}")

        return {
            "supports": True,
            "summary": f"Found {len(code_snippets)} code location(s) related to this claim",
            "explanation": None,
            "snippet_explanations": []
        }

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

        # Get custom section description and target word count if available
        custom_section_desc = ""
        target_words = self.default_section_words  # Use instance default
        if self.custom_sections:
            for s in self.custom_sections:
                if s.get("name", "").lower().replace(" ", "_") == section_name.lower().replace(" ", "_"):
                    if s.get("description"):
                        custom_section_desc = f"\n**Section Focus:** {s.get('description')}\n"
                    if s.get("target_words"):
                        target_words = s.get("target_words")
                    break

        # Also check section_configs for target_words
        if hasattr(self, 'section_configs') and self.section_configs:
            for s in self.section_configs:
                if isinstance(s, dict) and s.get("name", "").lower().replace(" ", "_") == section_name.lower().replace(" ", "_"):
                    if s.get("target_words"):
                        target_words = s.get("target_words")
                    break

        # Only add word count instruction if target_words is explicitly set
        word_count_instruction = ""
        if target_words:
            word_count_instruction = f"\n**Target Length:** Approximately {target_words} words for this section.\n"

        # Check for auto-generated content from feature flow extraction
        # This content comes from actual code graph traversal and should be preserved
        auto_generated_content, auto_gen_instructions = self._get_auto_generated_content(
            section_name, context
        )

        # REVERSE ENGINEERING prompt with BRD best practices
        prompt = f"""You are an expert Business Analyst reverse engineering EXISTING code to create a BRD.

{BRD_BEST_PRACTICES}

## CRITICAL: REVERSE ENGINEERING MODE

The feature "{context.request}" ALREADY EXISTS in this codebase. Document what the code DOES, not what should be built.

## Current Section: {section_name.replace('_', ' ').title()}
{custom_section_desc}{word_count_instruction}
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

{self._format_menu_items(context)}

{self._format_sub_features(context)}

{self._format_validation_chains(context)}

{self._format_cross_feature_context(context)}

{self._format_enriched_business_rules(context)}

{self._format_enhanced_context(context)}
{prev_sections_text}
{feedback_text}
{sufficiency_text}
{auto_generated_content}
{auto_gen_instructions}

## Writing Instructions

- Use plain English - translate code behavior to business language
- Be deterministic - avoid "may" or "might", describe exact behavior
- Write for business readers - assume non-technical audience
- Explain "what" not "how" - describe outcomes, not implementation
- Use numbered lists for process flows
- Capture all business rules from the code

### Using the Enhanced Context

1. **Code Snippets**: Use the provided code snippets to understand exact implementation details. Reference specific lines when describing business logic.

2. **Security Rules**: Include security requirements from @PreAuthorize, @Secured, and @RolesAllowed annotations. Document required roles and access control rules.

3. **Error Messages**: Use actual error messages to document validation rules and user feedback. These are from real .properties files and throw statements.

4. **Flow Transitions**: Use the parsed transition conditions to document business decision points. The conditions show when and why state changes occur.

5. **Form Fields**: Document user input fields with their labels, validation rules, and required status. Use actual field names from JSP forms.

6. **Method Implementations**: Reference the method code to accurately describe business logic. Do NOT invent behavior - describe what the code ACTUALLY does.

First show your analysis (wrapped in <thinking> tags), then the section:

<thinking>
[Analyze the code: what do these components do? how do they work together?]
</thinking>

## {section_name.replace('_', ' ').title()}

[Document what the EXISTING code does based on your analysis]
"""
        return prompt

    def _get_auto_generated_content(
        self,
        section_name: str,
        context: AggregatedContext,
    ) -> tuple[str, str]:
        """Get auto-generated content for sections that have pre-extracted data.

        For Technical Architecture, Implementation Mapping, and Data Model sections,
        we have pre-generated content from actual code graph traversal via FeatureFlowService.
        This content should be PRESERVED and enhanced by the LLM, not replaced.

        Args:
            section_name: Name of the section being generated
            context: Aggregated context containing feature flows and pre-generated content

        Returns:
            Tuple of (auto_generated_content, instructions_for_llm)
        """
        name_lower = section_name.lower().replace(" ", "_")

        # Technical Architecture section - inject pre-generated layered architecture
        if "technical_architecture" in name_lower or ("technical" in name_lower and "architecture" in name_lower):
            if context.technical_architecture:
                logger.info(f"[{section_name}] Injecting auto-generated Technical Architecture from code traversal")
                return (
                    f"""
## 🔧 AUTO-GENERATED CONTENT (from code graph traversal)

The following architecture was extracted by tracing actual code paths from UI to database.
**File paths and line numbers are from real code - DO NOT modify them.**

{context.technical_architecture}
""",
                    """
## ⚠️ CRITICAL INSTRUCTIONS FOR THIS SECTION

1. **PRESERVE** all auto-generated file paths, line numbers, and component references exactly as shown
2. The layered structure (UI → Flow → Controller → Service → DAO → Database) is accurate from code traversal
3. You may **ADD** additional context such as:
   - Business purpose of each layer/component
   - How data flows between layers
   - Error handling and validation points
   - Dependencies between components
4. **DO NOT** invent new file paths or line numbers
5. **DO NOT** remove or modify the existing code references
6. Format the content for readability while preserving all technical references
"""
                )

        # Implementation Mapping section - inject pre-generated operation-to-code mapping
        if "implementation_mapping" in name_lower or ("implementation" in name_lower and "mapping" in name_lower):
            if context.implementation_mapping:
                logger.info(f"[{section_name}] Injecting auto-generated Implementation Mapping from code traversal")
                return (
                    f"""
## 🔧 AUTO-GENERATED CONTENT (from code graph traversal)

The following mapping was extracted by tracing actual code execution paths.
**File paths and line numbers are from real code - DO NOT modify them.**

{context.implementation_mapping}
""",
                    """
## ⚠️ CRITICAL INSTRUCTIONS FOR THIS SECTION

1. **PRESERVE** all auto-generated table rows with file paths and line numbers exactly as shown
2. The Operation-to-Implementation table shows actual code locations from graph traversal
3. You may **ADD**:
   - Additional operations discovered from code analysis
   - Explanatory text about how to read the mapping
   - Business context for each operation
4. **DO NOT** modify existing file:line references - they are from actual code traversal
5. **DO NOT** invent new file paths or make up line numbers
6. Ensure the table format is preserved and readable
"""
                )

        # Data Model section - extract from feature flows if available
        if "data_model" in name_lower or ("data" in name_lower and "model" in name_lower):
            if context.feature_flows:
                data_model_content = self._extract_data_model_from_flows(context)
                if data_model_content:
                    logger.info(f"[{section_name}] Injecting extracted Data Model from feature flows")
                    return (
                        f"""
## 🔧 AUTO-GENERATED CONTENT (from SQL operations in code)

The following data model was extracted from actual SQL operations found in the codebase.

{data_model_content}
""",
                        """
## ⚠️ CRITICAL INSTRUCTIONS FOR THIS SECTION

1. The table and column information was extracted from actual SQL operations in the code
2. You may **ADD**:
   - Entity class information if visible in the context
   - Relationship descriptions based on code analysis
   - Validation annotations observed in entity classes
   - Business meaning of each table/column
3. **DO NOT** invent tables or columns not found in the code
4. Preserve the extracted database structure accurately
"""
                    )

        # Frontend Components section - extract UI/JSP/WebFlow info from feature flows
        if "frontend_components" in name_lower or ("frontend" in name_lower and "component" in name_lower):
            if context.feature_flows:
                frontend_content = self._extract_frontend_content_from_flows(context)
                if frontend_content:
                    logger.info(f"[{section_name}] Injecting extracted Frontend Components from feature flows")
                    return (
                        f"""
## 🔧 AUTO-GENERATED CONTENT (from code graph traversal)

The following UI components were extracted from actual code paths in the codebase.
**File paths and line numbers are from real code - DO NOT modify them.**

{frontend_content}
""",
                        """
## ⚠️ CRITICAL INSTRUCTIONS FOR THIS SECTION

1. **PRESERVE** all auto-generated file paths, line numbers, and component references exactly as shown
2. The JSP pages, form fields, and WebFlow states are from actual code traversal
3. You may **ADD**:
   - Business purpose of each UI component
   - User experience flow descriptions
   - Field-level validation requirements in business terms
   - Client-side interaction patterns
4. **DO NOT** invent new file paths or line numbers
5. **DO NOT** remove or modify existing code references
6. Add context about what business function each UI element serves
"""
                    )

        # Backend Services section - extract controller/service info from feature flows
        if "backend_services" in name_lower or ("backend" in name_lower and "service" in name_lower):
            if context.feature_flows:
                backend_content = self._extract_backend_content_from_flows(context)
                if backend_content:
                    logger.info(f"[{section_name}] Injecting extracted Backend Services from feature flows")
                    return (
                        f"""
## 🔧 AUTO-GENERATED CONTENT (from code graph traversal)

The following backend components were extracted from actual code paths in the codebase.
**File paths and line numbers are from real code - DO NOT modify them.**

{backend_content}
""",
                        """
## ⚠️ CRITICAL INSTRUCTIONS FOR THIS SECTION

1. **PRESERVE** all auto-generated class names, method signatures, and line numbers exactly as shown
2. The controller/service/validator mappings are from actual code traversal
3. You may **ADD**:
   - Business rules implemented by each method (in business terms)
   - Data transformations performed
   - Error handling and validation logic descriptions
   - Dependency relationships between services
4. **DO NOT** invent new method signatures or line numbers
5. **DO NOT** remove or modify existing code references
6. Explain what business logic each service method implements
"""
                    )

        # Persistence Layer section - extract DAO/SQL info from feature flows
        if "persistence_layer" in name_lower or ("persistence" in name_lower and "layer" in name_lower):
            if context.feature_flows:
                persistence_content = self._extract_persistence_content_from_flows(context)
                if persistence_content:
                    logger.info(f"[{section_name}] Injecting extracted Persistence Layer from feature flows")
                    return (
                        f"""
## 🔧 AUTO-GENERATED CONTENT (from code graph traversal)

The following persistence layer components were extracted from actual code paths in the codebase.
**File paths, line numbers, and SQL operations are from real code - DO NOT modify them.**

{persistence_content}
""",
                        """
## ⚠️ CRITICAL INSTRUCTIONS FOR THIS SECTION

1. **PRESERVE** all auto-generated DAO classes, entity mappings, and SQL operations exactly as shown
2. The database operations and field mappings are from actual code traversal
3. You may **ADD**:
   - Business meaning of each database table and column
   - Data integrity rules and constraints explanation
   - Transaction boundary descriptions
   - Audit field usage and purpose
4. **DO NOT** invent new tables, columns, or SQL operations
5. **DO NOT** remove or modify existing database references
6. Explain what business data each table/entity represents
"""
                    )

        # No auto-generated content for this section
        return ("", "")

    def _extract_data_model_from_flows(self, context: AggregatedContext) -> str:
        """Extract data model information from feature flows.

        Args:
            context: Aggregated context containing feature flows

        Returns:
            Markdown string describing the data model
        """
        if not context.feature_flows:
            return ""

        sections = []
        sections.append("### Database Tables\n")
        sections.append("*Tables and columns extracted from SQL operations in the code*\n")

        # Collect unique tables and their columns
        tables: dict[str, dict] = {}  # table_name -> {columns, operations, source}

        for flow_dict in context.feature_flows:
            # Handle both dict and object representations
            sql_ops = flow_dict.get("sql_operations", []) if isinstance(flow_dict, dict) else getattr(flow_dict, "sql_operations", [])

            for op in sql_ops:
                if isinstance(op, dict):
                    table = op.get("table_name", "unknown")
                    columns = op.get("columns", [])
                    op_type = op.get("statement_type", "UNKNOWN")
                    source = op.get("source_location", "")
                else:
                    table = getattr(op, "table_name", "unknown")
                    columns = getattr(op, "columns", [])
                    op_type = getattr(op, "statement_type", "UNKNOWN")
                    source = getattr(op, "source_location", "")

                if table and table != "unknown":
                    if table not in tables:
                        tables[table] = {"columns": set(), "operations": set(), "sources": set()}
                    tables[table]["columns"].update(columns if columns else [])
                    tables[table]["operations"].add(op_type)
                    if source:
                        tables[table]["sources"].add(source)

        if tables:
            sections.append("\n| Table | Columns | Operations | Source |")
            sections.append("|-------|---------|------------|--------|")
            for table_name, info in sorted(tables.items()):
                cols = ", ".join(sorted(info["columns"])[:5])  # Limit columns shown
                if len(info["columns"]) > 5:
                    cols += f" (+{len(info['columns']) - 5} more)"
                ops = ", ".join(sorted(info["operations"]))
                sources = ", ".join(list(info["sources"])[:2])  # Limit sources shown
                sections.append(f"| {table_name} | {cols} | {ops} | {sources} |")
        else:
            sections.append("\n*No SQL operations found in the traced code paths.*")

        # Add data mappings section if available
        data_mappings_found = False
        for flow_dict in context.feature_flows:
            mappings = flow_dict.get("data_mappings", []) if isinstance(flow_dict, dict) else getattr(flow_dict, "data_mappings", [])
            if mappings:
                data_mappings_found = True
                break

        if data_mappings_found:
            sections.append("\n### Field Mappings\n")
            sections.append("*UI field to database column mappings*\n")
            sections.append("\n| Entity Field | DB Column | DB Table | Data Type |")
            sections.append("|--------------|-----------|----------|-----------|")

            for flow_dict in context.feature_flows:
                mappings = flow_dict.get("data_mappings", []) if isinstance(flow_dict, dict) else getattr(flow_dict, "data_mappings", [])
                for dm in mappings[:10]:  # Limit to 10 mappings
                    if isinstance(dm, dict):
                        entity_field = dm.get("entity_field", "-")
                        db_column = dm.get("db_column", "-")
                        db_table = dm.get("db_table", "-")
                        data_type = dm.get("data_type", "-")
                    else:
                        entity_field = getattr(dm, "entity_field", "-")
                        db_column = getattr(dm, "db_column", "-")
                        db_table = getattr(dm, "db_table", "-")
                        data_type = getattr(dm, "data_type", "-")
                    sections.append(f"| {entity_field} | {db_column} | {db_table} | {data_type} |")

        return "\n".join(sections)

    def _format_layer_context(self, context: AggregatedContext, layer: str) -> str:
        """Format layer-organized components for prompts.

        Args:
            context: Aggregated context containing feature flows and components
            layer: One of 'frontend', 'backend', 'persistence'

        Returns:
            Markdown string describing components in the specified layer
        """
        if not context.feature_flows:
            return ""

        sections = []

        for flow_dict in context.feature_flows:
            flow_name = flow_dict.get("entry_point", "Unknown") if isinstance(flow_dict, dict) else getattr(flow_dict, "entry_point", "Unknown")
            layers = flow_dict.get("layers", {}) if isinstance(flow_dict, dict) else getattr(flow_dict, "layers", {})

            if not layers:
                continue

            layer_data = layers.get(layer, {})
            if not layer_data:
                continue

            components = layer_data.get("components", []) if isinstance(layer_data, dict) else getattr(layer_data, "components", [])

            if components:
                sections.append(f"\n### {flow_name}\n")
                for comp in components[:15]:  # Limit components per flow
                    if isinstance(comp, dict):
                        name = comp.get("name", "Unknown")
                        comp_type = comp.get("type", "Component")
                        file_path = comp.get("file_path", "")
                        line = comp.get("line", "")
                        methods = comp.get("methods", [])
                    else:
                        name = getattr(comp, "name", "Unknown")
                        comp_type = getattr(comp, "type", "Component")
                        file_path = getattr(comp, "file_path", "")
                        line = getattr(comp, "line", "")
                        methods = getattr(comp, "methods", [])

                    location = f"{file_path}:{line}" if file_path and line else file_path or "-"
                    sections.append(f"- **{name}** ({comp_type}) @ `{location}`")

                    if methods:
                        for method in methods[:5]:
                            if isinstance(method, dict):
                                method_name = method.get("name", "")
                                method_line = method.get("line", "")
                                signature = method.get("signature", "")
                            else:
                                method_name = getattr(method, "name", "")
                                method_line = getattr(method, "line", "")
                                signature = getattr(method, "signature", "")
                            if method_name:
                                sig_str = f": `{signature}`" if signature else ""
                                sections.append(f"  - `{method_name}()` line {method_line}{sig_str}")

        return "\n".join(sections) if sections else f"*No {layer} components found in feature flows.*"

    def _extract_frontend_content_from_flows(self, context: AggregatedContext) -> str:
        """Extract UI components from feature flows.

        Args:
            context: Aggregated context containing feature flows

        Returns:
            Markdown string describing frontend components
        """
        if not context.feature_flows:
            return ""

        sections = []
        sections.append("### JSP Pages / Views\n")
        sections.append("| Page | File Path | Purpose | WebFlow State |")
        sections.append("|------|-----------|---------|---------------|")

        jsp_pages = []
        form_fields = []
        webflow_states = []

        for flow_dict in context.feature_flows:
            # Extract UI layer components
            layers = flow_dict.get("layers", {}) if isinstance(flow_dict, dict) else getattr(flow_dict, "layers", {})
            ui_layer = layers.get("ui", {}) or layers.get("frontend", {}) or layers.get("view", {})

            if ui_layer:
                components = ui_layer.get("components", []) if isinstance(ui_layer, dict) else getattr(ui_layer, "components", [])
                for comp in components:
                    if isinstance(comp, dict):
                        name = comp.get("name", "")
                        file_path = comp.get("file_path", "")
                        purpose = comp.get("purpose", comp.get("description", "-"))
                        state = comp.get("webflow_state", "-")
                    else:
                        name = getattr(comp, "name", "")
                        file_path = getattr(comp, "file_path", "")
                        purpose = getattr(comp, "purpose", getattr(comp, "description", "-"))
                        state = getattr(comp, "webflow_state", "-")

                    if name and (name.endswith(".jsp") or "View" in name or "Form" in name):
                        jsp_pages.append(f"| {name} | {file_path} | {purpose[:50]} | {state} |")

            # Extract form fields from data mappings
            data_mappings = flow_dict.get("data_mappings", []) if isinstance(flow_dict, dict) else getattr(flow_dict, "data_mappings", [])
            for dm in data_mappings:
                if isinstance(dm, dict):
                    ui_field = dm.get("ui_field", dm.get("entity_field", ""))
                    field_type = dm.get("field_type", dm.get("data_type", "text"))
                    required = dm.get("required", "-")
                    validations = dm.get("validations", "-")
                else:
                    ui_field = getattr(dm, "ui_field", getattr(dm, "entity_field", ""))
                    field_type = getattr(dm, "field_type", getattr(dm, "data_type", "text"))
                    required = getattr(dm, "required", "-")
                    validations = getattr(dm, "validations", "-")

                if ui_field:
                    form_fields.append({
                        "name": ui_field,
                        "type": field_type,
                        "required": required,
                        "validations": validations
                    })

            # Extract WebFlow states
            flow_states = flow_dict.get("flow_states", []) if isinstance(flow_dict, dict) else getattr(flow_dict, "flow_states", [])
            for state in flow_states:
                if isinstance(state, dict):
                    state_name = state.get("name", "")
                    state_view = state.get("view", "-")
                    transitions = state.get("transitions", [])
                else:
                    state_name = getattr(state, "name", "")
                    state_view = getattr(state, "view", "-")
                    transitions = getattr(state, "transitions", [])

                if state_name:
                    webflow_states.append({
                        "name": state_name,
                        "view": state_view,
                        "transitions": transitions
                    })

        # Add JSP pages
        if jsp_pages:
            sections.extend(jsp_pages[:10])
        else:
            sections.append("| *No JSP pages found* | - | - | - |")

        # Add form fields section
        if form_fields:
            sections.append("\n### Form Fields\n")
            sections.append("| Field Name | Type | Required | Validations |")
            sections.append("|------------|------|----------|-------------|")
            for field in form_fields[:15]:
                sections.append(f"| {field['name']} | {field['type']} | {field['required']} | {field['validations']} |")

        # Add WebFlow states section
        if webflow_states:
            sections.append("\n### WebFlow Navigation\n")
            sections.append("| State | View | Transitions |")
            sections.append("|-------|------|-------------|")
            for state in webflow_states[:10]:
                trans_str = ", ".join(str(t) for t in state["transitions"][:3]) if state["transitions"] else "-"
                sections.append(f"| {state['name']} | {state['view']} | {trans_str} |")

        # Add layer context
        layer_content = self._format_layer_context(context, "frontend")
        if layer_content and "*No frontend" not in layer_content:
            sections.append("\n### Additional UI Components\n")
            sections.append(layer_content)

        return "\n".join(sections)

    def _extract_backend_content_from_flows(self, context: AggregatedContext) -> str:
        """Extract controller/service info from feature flows.

        Args:
            context: Aggregated context containing feature flows

        Returns:
            Markdown string describing backend components
        """
        if not context.feature_flows:
            return ""

        sections = []
        controllers = []
        services = []
        validators = []

        for flow_dict in context.feature_flows:
            layers = flow_dict.get("layers", {}) if isinstance(flow_dict, dict) else getattr(flow_dict, "layers", {})

            # Extract controller layer
            controller_layer = layers.get("controller", {}) or layers.get("action", {})
            if controller_layer:
                components = controller_layer.get("components", []) if isinstance(controller_layer, dict) else getattr(controller_layer, "components", [])
                for comp in components:
                    if isinstance(comp, dict):
                        name = comp.get("name", "")
                        file_path = comp.get("file_path", "")
                        methods = comp.get("methods", [])
                    else:
                        name = getattr(comp, "name", "")
                        file_path = getattr(comp, "file_path", "")
                        methods = getattr(comp, "methods", [])

                    for method in methods[:5]:
                        if isinstance(method, dict):
                            method_name = method.get("name", "")
                            signature = method.get("signature", f"{method_name}()")
                            start_line = method.get("start_line", method.get("line", "-"))
                            end_line = method.get("end_line", "-")
                            purpose = method.get("purpose", "-")
                        else:
                            method_name = getattr(method, "name", "")
                            signature = getattr(method, "signature", f"{method_name}()")
                            start_line = getattr(method, "start_line", getattr(method, "line", "-"))
                            end_line = getattr(method, "end_line", "-")
                            purpose = getattr(method, "purpose", "-")

                        lines = f"{start_line}-{end_line}" if end_line != "-" else str(start_line)
                        controllers.append({
                            "class": name,
                            "method": method_name,
                            "signature": signature,
                            "lines": lines,
                            "purpose": purpose,
                            "file": file_path
                        })

            # Extract service layer
            service_layer = layers.get("service", {}) or layers.get("business", {})
            if service_layer:
                components = service_layer.get("components", []) if isinstance(service_layer, dict) else getattr(service_layer, "components", [])
                for comp in components:
                    if isinstance(comp, dict):
                        name = comp.get("name", "")
                        file_path = comp.get("file_path", "")
                        methods = comp.get("methods", [])
                        interface = comp.get("interface", "-")
                    else:
                        name = getattr(comp, "name", "")
                        file_path = getattr(comp, "file_path", "")
                        methods = getattr(comp, "methods", [])
                        interface = getattr(comp, "interface", "-")

                    for method in methods[:5]:
                        if isinstance(method, dict):
                            method_name = method.get("name", "")
                            start_line = method.get("start_line", method.get("line", "-"))
                            end_line = method.get("end_line", "-")
                            business_rules = method.get("business_rules", "-")
                        else:
                            method_name = getattr(method, "name", "")
                            start_line = getattr(method, "start_line", getattr(method, "line", "-"))
                            end_line = getattr(method, "end_line", "-")
                            business_rules = getattr(method, "business_rules", "-")

                        lines = f"{start_line}-{end_line}" if end_line != "-" else str(start_line)
                        services.append({
                            "interface": interface,
                            "implementation": name,
                            "method": method_name,
                            "lines": lines,
                            "business_rules": business_rules,
                            "file": file_path
                        })

            # Extract validators/builders
            validator_layer = layers.get("validator", {}) or layers.get("builder", {})
            if validator_layer:
                components = validator_layer.get("components", []) if isinstance(validator_layer, dict) else getattr(validator_layer, "components", [])
                for comp in components:
                    if isinstance(comp, dict):
                        name = comp.get("name", "")
                        file_path = comp.get("file_path", "")
                        methods = comp.get("methods", [])
                    else:
                        name = getattr(comp, "name", "")
                        file_path = getattr(comp, "file_path", "")
                        methods = getattr(comp, "methods", [])

                    for method in methods[:3]:
                        if isinstance(method, dict):
                            method_name = method.get("name", "")
                            purpose = method.get("purpose", "-")
                            lines = method.get("line", "-")
                        else:
                            method_name = getattr(method, "name", "")
                            purpose = getattr(method, "purpose", "-")
                            lines = getattr(method, "line", "-")

                        validators.append({
                            "class": name,
                            "method": method_name,
                            "purpose": purpose,
                            "lines": lines,
                            "file": file_path
                        })

        # Build output sections
        sections.append("### Controller/Action Layer\n")
        if controllers:
            sections.append("| Class | Method | Signature | Lines | Purpose |")
            sections.append("|-------|--------|-----------|-------|---------|")
            for ctrl in controllers[:10]:
                sections.append(f"| {ctrl['class']} | {ctrl['method']} | `{ctrl['signature'][:40]}` | {ctrl['lines']} | {ctrl['purpose'][:30]} |")
        else:
            sections.append("*No controller methods found in feature flows.*")

        sections.append("\n### Service Layer\n")
        if services:
            sections.append("| Interface | Implementation | Method | Lines | Business Rules |")
            sections.append("|-----------|----------------|--------|-------|----------------|")
            for svc in services[:10]:
                sections.append(f"| {svc['interface']} | {svc['implementation']} | {svc['method']} | {svc['lines']} | {svc['business_rules'][:30] if isinstance(svc['business_rules'], str) else '-'} |")
        else:
            sections.append("*No service methods found in feature flows.*")

        if validators:
            sections.append("\n### Builder/Validator Classes\n")
            sections.append("| Class | Method | Purpose | Lines |")
            sections.append("|-------|--------|---------|-------|")
            for val in validators[:8]:
                sections.append(f"| {val['class']} | {val['method']} | {val['purpose'][:40]} | {val['lines']} |")

        # Add layer context for additional backend components
        layer_content = self._format_layer_context(context, "backend")
        if layer_content and "*No backend" not in layer_content:
            sections.append("\n### Additional Backend Components\n")
            sections.append(layer_content)

        return "\n".join(sections)

    def _extract_persistence_content_from_flows(self, context: AggregatedContext) -> str:
        """Extract DAO/SQL info from feature flows.

        Args:
            context: Aggregated context containing feature flows

        Returns:
            Markdown string describing persistence layer components
        """
        if not context.feature_flows:
            return ""

        sections = []
        daos = []
        entities = []
        sql_operations = []
        field_mappings = []

        for flow_dict in context.feature_flows:
            layers = flow_dict.get("layers", {}) if isinstance(flow_dict, dict) else getattr(flow_dict, "layers", {})

            # Extract DAO layer
            dao_layer = layers.get("dao", {}) or layers.get("repository", {}) or layers.get("persistence", {})
            if dao_layer:
                components = dao_layer.get("components", []) if isinstance(dao_layer, dict) else getattr(dao_layer, "components", [])
                for comp in components:
                    if isinstance(comp, dict):
                        name = comp.get("name", "")
                        file_path = comp.get("file_path", "")
                        methods = comp.get("methods", [])
                    else:
                        name = getattr(comp, "name", "")
                        file_path = getattr(comp, "file_path", "")
                        methods = getattr(comp, "methods", [])

                    for method in methods[:5]:
                        if isinstance(method, dict):
                            method_name = method.get("name", "")
                            purpose = method.get("purpose", "-")
                            lines = method.get("line", "-")
                        else:
                            method_name = getattr(method, "name", "")
                            purpose = getattr(method, "purpose", "-")
                            lines = getattr(method, "line", "-")

                        daos.append({
                            "class": name,
                            "method": method_name,
                            "purpose": purpose,
                            "file_path": file_path,
                            "lines": lines
                        })

            # Extract entity layer
            entity_layer = layers.get("entity", {}) or layers.get("model", {})
            if entity_layer:
                components = entity_layer.get("components", []) if isinstance(entity_layer, dict) else getattr(entity_layer, "components", [])
                for comp in components:
                    if isinstance(comp, dict):
                        name = comp.get("name", "")
                        table = comp.get("table", comp.get("table_name", "-"))
                        file_path = comp.get("file_path", "")
                        annotations = comp.get("annotations", [])
                    else:
                        name = getattr(comp, "name", "")
                        table = getattr(comp, "table", getattr(comp, "table_name", "-"))
                        file_path = getattr(comp, "file_path", "")
                        annotations = getattr(comp, "annotations", [])

                    annotations_str = ", ".join(annotations[:3]) if annotations else "@Entity"
                    entities.append({
                        "entity": name,
                        "table": table,
                        "file_path": file_path,
                        "annotations": annotations_str
                    })

            # Extract SQL operations
            sql_ops = flow_dict.get("sql_operations", []) if isinstance(flow_dict, dict) else getattr(flow_dict, "sql_operations", [])
            for op in sql_ops:
                if isinstance(op, dict):
                    stmt_type = op.get("statement_type", "UNKNOWN")
                    table = op.get("table_name", "-")
                    columns = op.get("columns", [])
                    source = op.get("source_location", op.get("source_method", "-"))
                    line = op.get("line", "-")
                else:
                    stmt_type = getattr(op, "statement_type", "UNKNOWN")
                    table = getattr(op, "table_name", "-")
                    columns = getattr(op, "columns", [])
                    source = getattr(op, "source_location", getattr(op, "source_method", "-"))
                    line = getattr(op, "line", "-")

                columns_str = ", ".join(columns[:5]) if columns else "*"
                if len(columns) > 5:
                    columns_str += f" (+{len(columns) - 5} more)"

                sql_operations.append({
                    "type": stmt_type,
                    "table": table,
                    "columns": columns_str,
                    "source": source,
                    "line": line
                })

            # Extract field mappings
            data_mappings = flow_dict.get("data_mappings", []) if isinstance(flow_dict, dict) else getattr(flow_dict, "data_mappings", [])
            for dm in data_mappings:
                if isinstance(dm, dict):
                    entity_field = dm.get("entity_field", "-")
                    db_column = dm.get("db_column", "-")
                    data_type = dm.get("data_type", "-")
                    constraints = dm.get("constraints", "-")
                    validations = dm.get("validations", "-")
                else:
                    entity_field = getattr(dm, "entity_field", "-")
                    db_column = getattr(dm, "db_column", "-")
                    data_type = getattr(dm, "data_type", "-")
                    constraints = getattr(dm, "constraints", "-")
                    validations = getattr(dm, "validations", "-")

                field_mappings.append({
                    "entity_field": entity_field,
                    "db_column": db_column,
                    "data_type": data_type,
                    "constraints": constraints,
                    "validations": validations
                })

        # Build output sections
        sections.append("### DAO/Repository Classes\n")
        if daos:
            sections.append("| Class | Method | Purpose | File Path | Lines |")
            sections.append("|-------|--------|---------|-----------|-------|")
            for dao in daos[:10]:
                sections.append(f"| {dao['class']} | {dao['method']} | {dao['purpose'][:30]} | {dao['file_path']} | {dao['lines']} |")
        else:
            sections.append("*No DAO/Repository classes found in feature flows.*")

        sections.append("\n### Entity Classes\n")
        if entities:
            sections.append("| Entity | Table | File Path | Key Annotations |")
            sections.append("|--------|-------|-----------|-----------------|")
            for ent in entities[:10]:
                sections.append(f"| {ent['entity']} | {ent['table']} | {ent['file_path']} | {ent['annotations']} |")
        else:
            sections.append("*No Entity classes found in feature flows.*")

        sections.append("\n### SQL Operations\n")
        if sql_operations:
            sections.append("| Statement Type | Table | Columns | Source Method | Line |")
            sections.append("|----------------|-------|---------|---------------|------|")
            for sql in sql_operations[:15]:
                sections.append(f"| {sql['type']} | {sql['table']} | {sql['columns']} | {sql['source']} | {sql['line']} |")
        else:
            sections.append("*No SQL operations found in feature flows.*")

        if field_mappings:
            sections.append("\n### Field-to-Column Mapping\n")
            sections.append("| Entity Field | DB Column | Data Type | Constraints | Validations |")
            sections.append("|--------------|-----------|-----------|-------------|-------------|")
            for fm in field_mappings[:15]:
                sections.append(f"| {fm['entity_field']} | {fm['db_column']} | {fm['data_type']} | {fm['constraints']} | {fm['validations']} |")

        # Add layer context for additional persistence components
        layer_content = self._format_layer_context(context, "persistence")
        if layer_content and "*No persistence" not in layer_content:
            sections.append("\n### Additional Persistence Components\n")
            sections.append(layer_content)

        return "\n".join(sections)

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
        """Extract section content from LLM response, removing thinking tags and duplicate headings."""
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

        # Remove ALL leading markdown headings (## or #) - they will be added by _combine_sections_to_brd
        # This prevents duplicate headings when sections are combined
        lines = content.strip().split('\n')

        # Keep removing heading lines until we hit actual content
        while lines:
            first_line = lines[0].strip()
            # Check if it's a heading line (starts with # symbols)
            if re.match(r'^#{1,4}\s+', first_line):
                lines = lines[1:]
                # Also remove any blank lines after the heading
                while lines and not lines[0].strip():
                    lines = lines[1:]
            else:
                break

        content = '\n'.join(lines)
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

        # Call calculate_overall_metrics to properly set overall_status based on section results
        bundle.calculate_overall_metrics()

        # Override with our calculated values if needed (for consistency)
        if bundle.overall_confidence < overall_confidence:
            bundle.overall_confidence = overall_confidence
        bundle.hallucination_risk = risk
        if overall_confidence >= self.verification_config.min_confidence_for_approval:
            bundle.is_approved = True

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
        """Call LLM via Copilot SDK session with consistency controls."""
        if not self.session:
            logger.warning("No Copilot session - returning mock response")
            return self._generate_mock_response(prompt)

        try:
            logger.debug(f"[LLM] Sending prompt ({len(prompt)} chars), temp={self.temperature}")

            # Build message options with consistency controls
            message_options = {
                "prompt": prompt,
                "temperature": self.temperature,
            }

            # Add seed if specified for reproducibility
            if self.seed is not None:
                message_options["seed"] = self.seed

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

    def _format_menu_items(self, context: AggregatedContext) -> str:
        """Format menu items for prompt."""
        if not context.menu_items:
            return ""

        lines = ["**Menu Items:**"]
        for item in context.menu_items[:10]:
            lines.append(f"- **{item.label}** ({item.name})")
            lines.append(f"  - URL: {item.url}")
            lines.append(f"  - Flow: {item.flow_id}")
            if item.required_roles:
                lines.append(f"  - Roles: {', '.join(item.required_roles)}")
        return "\n".join(lines)

    def _format_sub_features(self, context: AggregatedContext) -> str:
        """Format sub-features (screens) for prompt."""
        if not context.sub_features:
            return ""

        lines = ["**Sub-Features (Screens):**"]
        for sf in context.sub_features[:15]:
            lines.append(f"\n**{sf.title}** ({sf.screen_type})")
            lines.append(f"- Screen ID: {sf.screen_id}")
            if sf.action_class:
                lines.append(f"- Action Class: `{sf.action_class}`")
            if sf.action_methods:
                lines.append(f"- Methods: {', '.join(sf.action_methods[:5])}")
            if sf.jsps:
                lines.append(f"- JSPs: {', '.join(sf.jsps[:3])}")
            if sf.transitions_to:
                lines.append(f"- Transitions to: {', '.join(sf.transitions_to[:3])}")
        return "\n".join(lines)

    def _format_validation_chains(self, context: AggregatedContext) -> str:
        """Format validation chains for prompt."""
        if not context.validation_chains:
            return ""

        lines = ["**Validation Chains:**"]
        for chain in context.validation_chains[:5]:
            lines.append(f"\n**Entry Point:** `{chain.entry_point}`")
            lines.append(f"- Total Rules: {chain.total_rules}")
            if chain.validated_fields:
                lines.append(f"- Validated Fields: {', '.join(chain.validated_fields[:10])}")
            lines.append("- Steps:")
            for step in chain.validation_steps[:5]:
                lines.append(f"  {step.order}. [{step.step_type}] `{step.class_name}`")
                if step.rules:
                    for rule in step.rules[:3]:
                        lines.append(f"     - {rule}")
        return "\n".join(lines)

    def _format_cross_feature_context(self, context: AggregatedContext) -> str:
        """Format cross-feature dependencies for prompt."""
        if not context.cross_feature_context:
            return ""

        cfc = context.cross_feature_context
        lines = ["**Cross-Feature Dependencies:**"]

        if cfc.shared_entities:
            lines.append("\n*Shared Entities:*")
            for entity, features in list(cfc.shared_entities.items())[:5]:
                lines.append(f"- `{entity}` used by: {', '.join(features[:3])}")

        if cfc.shared_services:
            lines.append("\n*Shared Services:*")
            for service, features in list(cfc.shared_services.items())[:5]:
                lines.append(f"- `{service}` used by: {', '.join(features[:3])}")

        if cfc.dependencies:
            lines.append("\n*Dependencies:*")
            for dep in cfc.dependencies[:5]:
                lines.append(f"- {dep.source_feature} → {dep.target_feature}")
                lines.append(f"  Type: {dep.relationship_type}, Component: {dep.shared_component}")
                lines.append(f"  Impact: {dep.implication}")

        if cfc.impact_summary:
            lines.append(f"\n*Impact Summary:* {cfc.impact_summary}")

        return "\n".join(lines)

    def _format_enriched_business_rules(self, context: AggregatedContext) -> str:
        """Format enriched business rules for prompt."""
        if not context.enriched_business_rules:
            return ""

        lines = ["**Business Rules with Feature Context:**"]
        for rule in context.enriched_business_rules[:10]:
            rule_type = rule.get("rule_type", "validation")
            description = rule.get("description", "")
            source_class = rule.get("source_class", "")
            source_method = rule.get("source_method", "")
            condition = rule.get("condition", "")
            feature_ctx = rule.get("feature_context", {})

            lines.append(f"\n**Rule:** {description}")
            lines.append(f"- Type: {rule_type}")
            if source_class:
                lines.append(f"- Source: `{source_class}.{source_method}`")
            if condition:
                lines.append(f"- Condition: {condition}")
            if feature_ctx:
                if feature_ctx.get("menu_item"):
                    lines.append(f"- Menu Item: {feature_ctx['menu_item']}")
                if feature_ctx.get("screen"):
                    lines.append(f"- Screen: {feature_ctx['screen']}")

        return "\n".join(lines)

    # =========================================================================
    # Phase 11: Enhanced Context Formatters
    # =========================================================================

    def _format_code_snippets(self, context: AggregatedContext) -> str:
        """Format code snippets for prompt."""
        if not context.code_snippets:
            return ""

        lines = ["**Code Implementation Details:**"]
        for snippet in context.code_snippets[:10]:
            lines.append(snippet.to_markdown())
            lines.append("")

        return "\n".join(lines)

    def _format_security_rules(self, context: AggregatedContext) -> str:
        """Format security rules for prompt."""
        if not context.security_rules:
            return ""

        lines = ["**Security & Access Control:**"]
        for rule in context.security_rules[:15]:
            lines.append(rule.to_markdown())

        return "\n".join(lines)

    def _format_error_messages(self, context: AggregatedContext) -> str:
        """Format error messages for prompt."""
        if not context.error_messages:
            return ""

        lines = ["**Error Messages & Validation Feedback:**"]
        for err in context.error_messages[:20]:
            lines.append(err.to_markdown())

        return "\n".join(lines)

    def _format_transition_conditions(self, context: AggregatedContext) -> str:
        """Format transition conditions for prompt."""
        if not context.transition_conditions:
            return ""

        lines = ["**Flow Transitions & Business Rules:**"]
        for cond in context.transition_conditions[:15]:
            lines.append(cond.to_markdown())

        return "\n".join(lines)

    def _format_form_field_details(self, context: AggregatedContext) -> str:
        """Format form field details for prompt."""
        if not context.form_field_details:
            return ""

        lines = ["**UI Form Fields & Validation:**"]
        lines.append("| Field | Label | Type/Validation |")
        lines.append("|-------|-------|-----------------|")
        for field in context.form_field_details[:30]:
            lines.append(field.to_markdown())

        return "\n".join(lines)

    def _format_enhanced_methods(self, context: AggregatedContext) -> str:
        """Format enhanced methods for prompt."""
        if not context.enhanced_methods:
            return ""

        lines = ["**Key Method Implementations:**"]
        for method in context.enhanced_methods[:8]:
            lines.append(method.to_markdown())
            lines.append("\n---\n")

        return "\n".join(lines)

    def _format_enhanced_context(self, context: AggregatedContext) -> str:
        """Format all enhanced context fields for prompt."""
        sections = []

        code_snippets = self._format_code_snippets(context)
        if code_snippets:
            sections.append(code_snippets)

        security = self._format_security_rules(context)
        if security:
            sections.append(security)

        errors = self._format_error_messages(context)
        if errors:
            sections.append(errors)

        transitions = self._format_transition_conditions(context)
        if transitions:
            sections.append(transitions)

        form_fields = self._format_form_field_details(context)
        if form_fields:
            sections.append(form_fields)

        enhanced_methods = self._format_enhanced_methods(context)
        if enhanced_methods:
            sections.append(enhanced_methods)

        if sections:
            return "\n## Extracted Business Logic (from actual code)\n\n" + "\n\n".join(sections)
        return ""

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
        temperature: float = 0.0,
        seed: Optional[int] = None,
        claims_per_section: int = 5,
        default_section_words: Optional[int] = None,
        skip_verification: bool = False,
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
            temperature=temperature,
            seed=seed,
            claims_per_section=claims_per_section,
            default_section_words=default_section_words,
            skip_verification=skip_verification,
        )
        self._last_output: Optional[BRDOutput] = None
        self._skip_verification = skip_verification

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
