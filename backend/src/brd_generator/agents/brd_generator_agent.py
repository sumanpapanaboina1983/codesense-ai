"""BRD Generator Agent - Generates BRD sections iteratively.

This agent is:
1. TEMPLATE-DRIVEN: Sections come from the parsed BRD template
2. AGENTIC: Uses MCP tools (Neo4j, Filesystem) dynamically via Copilot SDK

The LLM decides what tools to call to gather context for each section.
No hardcoded queries - the agentic loop handles tool calling.
"""

from __future__ import annotations

import re
from typing import Any, Optional, TYPE_CHECKING

from ..models.context import AggregatedContext
from ..models.output import BRDDocument, Requirement, AcceptanceCriteria
from ..models.verification import EvidenceBundle, SectionVerificationResult
from ..utils.logger import get_logger
from .base import BaseAgent, AgentMessage, AgentRole, MessageType

if TYPE_CHECKING:
    from ..core.template_parser import ParsedBRDTemplate, BRDSection

logger = get_logger(__name__)


class BRDGeneratorAgent(BaseAgent):
    """
    Agent 1: BRD Generator (Template-Driven)

    Responsible for:
    1. Generating BRD sections based on the PARSED TEMPLATE (no hardcoded sections!)
    2. Following the template's section structure, guidelines, and format requirements
    3. Incorporating feedback from the Verifier agent
    4. Regenerating sections that fail verification
    5. Producing the final verified BRD

    The BRD structure comes entirely from the template:
    - Section names and order from template
    - Content guidelines from template
    - Format requirements from template
    """

    def __init__(
        self,
        copilot_session: Any = None,
        context: Optional[AggregatedContext] = None,
        parsed_template: Optional["ParsedBRDTemplate"] = None,
        config: dict[str, Any] = None,
    ):
        """
        Initialize the BRD Generator Agent.

        Args:
            copilot_session: Copilot SDK session for LLM access (with MCP tools)
            context: Aggregated context from code analysis
            parsed_template: The PARSED BRD template that defines sections
            config: Agent configuration

        Note: MCP tools are available via the Copilot SDK session's mcp_servers config.
        """
        super().__init__(
            role=AgentRole.GENERATOR,
            copilot_session=copilot_session,
            config=config or {},
        )

        self.context = context
        self.parsed_template = parsed_template
        self.current_brd: Optional[BRDDocument] = None
        self.sections_generated: dict[str, str] = {}
        self.sections_approved: set[str] = set()
        self.regeneration_count: dict[str, int] = {}
        self.max_regenerations = config.get("max_regenerations", 3) if config else 3

        # Log initialization
        logger.info(f"BRDGeneratorAgent initialized")
        logger.debug(f"  Max regenerations: {self.max_regenerations}")
        logger.debug(f"  Template: {'set' if parsed_template else 'default'}")
        logger.debug(f"  Context: {'set' if context else 'not set'}")

    def set_context(self, context: AggregatedContext) -> None:
        """Set the code analysis context."""
        self.context = context

    def set_template(self, parsed_template: "ParsedBRDTemplate") -> None:
        """Set the parsed BRD template that defines section structure."""
        self.parsed_template = parsed_template
        logger.info(f"Template set with {len(parsed_template.sections)} sections")

    def get_section_names(self) -> list[str]:
        """Get the list of section names from the template."""
        if self.parsed_template:
            return self.parsed_template.get_section_names()
        # Fallback to default if no template
        return ["Feature Overview", "Functional Requirements", "Acceptance Criteria"]

    async def process(self, message: AgentMessage) -> None:
        """
        Process incoming messages.

        Handles:
        - START: Begin BRD generation
        - FEEDBACK: Incorporate feedback and regenerate
        - APPROVED: Mark section as approved
        """
        if message.message_type == MessageType.START:
            await self._start_generation(message)

        elif message.message_type == MessageType.FEEDBACK:
            await self._handle_feedback(message)

        elif message.message_type == MessageType.APPROVED:
            await self._handle_approval(message)

        elif message.message_type == MessageType.VERIFICATION_RESULT:
            await self._handle_verification_result(message)

    async def _start_generation(self, message: AgentMessage) -> None:
        """Start the BRD generation process."""
        logger.info("=" * 60)
        logger.info("BRD Generator: Starting generation")
        logger.info("=" * 60)

        if not self.context:
            logger.error("No context set for BRD generation")
            await self.send(AgentMessage(
                message_type=MessageType.ERROR,
                recipient=AgentRole.ORCHESTRATOR,
                content="No context available for BRD generation",
            ))
            return

        # Log context summary
        logger.info(f"Context summary:")
        logger.info(f"  Request: {self.context.request[:80]}...")
        if self.context.architecture:
            logger.info(f"  Components: {len(self.context.architecture.components)}")
        if self.context.implementation:
            logger.info(f"  Key files: {len(self.context.implementation.key_files)}")

        # Reset state
        self.sections_generated = {}
        self.sections_approved = set()
        self.regeneration_count = {}
        self.current_brd = None
        logger.debug("Generation state reset")

        # Get sections from parsed template (template-driven!)
        section_names = self.get_section_names()
        logger.info(f"BRD Generator: Will generate {len(section_names)} sections from template")
        logger.info(f"  Sections: {section_names}")

        # Generate sections one by one based on template
        for i, section_name in enumerate(section_names, 1):
            logger.info(f"Generating section {i}/{len(section_names)}: {section_name}")
            await self._generate_section(section_name, message.iteration)

    async def _generate_section(
        self,
        section_name: str,
        iteration: int,
        feedback: Optional[str] = None,
    ) -> None:
        """
        Generate a single BRD section.

        Args:
            section_name: Name of the section to generate
            iteration: Current iteration number
            feedback: Optional feedback from previous verification
        """
        import time
        start_time = time.time()

        regen_count = self.regeneration_count.get(section_name, 0) + 1
        logger.info(f"[GENERATOR] Section '{section_name}' (iteration {iteration}, regen #{regen_count})")

        if feedback:
            logger.info(f"[GENERATOR] Regenerating with feedback: {feedback[:100]}...")

        # Track regeneration count
        self.regeneration_count[section_name] = regen_count

        # Build the prompt
        logger.debug(f"[GENERATOR] Building prompt for '{section_name}'")
        prompt = self._build_section_prompt(section_name, feedback)
        logger.debug(f"[GENERATOR] Prompt length: {len(prompt)} chars")

        # Generate using LLM
        logger.info(f"[GENERATOR] Calling LLM for '{section_name}'...")
        response = await self.send_to_llm(prompt)

        elapsed = time.time() - start_time
        logger.info(f"[GENERATOR] Section '{section_name}' generated ({len(response)} chars, {elapsed:.2f}s)")
        logger.debug(f"[GENERATOR] Response preview: {response[:200]}...")

        # Store the generated section
        self.sections_generated[section_name] = response

        # Send to verifier for validation
        logger.info(f"[GENERATOR] Sending '{section_name}' to verifier")
        await self.send(AgentMessage(
            message_type=MessageType.BRD_SECTION,
            recipient=AgentRole.VERIFIER,
            section_name=section_name,
            content=response,
            iteration=iteration,
            metadata={
                "feature_description": self.context.request if self.context else "",
                "regeneration_count": self.regeneration_count[section_name],
                "generation_time_s": elapsed,
            },
        ))

    def _build_section_prompt(
        self,
        section_name: str,
        feedback: Optional[str] = None,
    ) -> str:
        """
        Build the prompt for generating a BRD section.

        This is TEMPLATE-DRIVEN - the prompt is built from the parsed template's
        section description, content guidelines, and format hints.

        Args:
            section_name: Name of the section to generate
            feedback: Optional feedback from verification failure

        Returns:
            The prompt string
        """
        # Get section definition from template
        section_prompt = self._build_template_section_prompt(section_name)

        # Add context information
        context_info = self._build_context_info()

        # Add feedback if regenerating
        feedback_section = ""
        if feedback:
            feedback_section = f"""
## IMPORTANT: Previous Version Failed Verification

The previous version of this section had issues. Please address the following feedback:

{feedback}

Make sure to:
1. Only include claims that can be verified from the codebase
2. Reference actual components, files, and patterns from the code analysis
3. Be specific and accurate - avoid generic statements
"""

        # Add already approved sections for context
        approved_context = self._build_approved_sections_context()

        # Build tool instructions if tools are available
        tool_instructions = self._build_tool_instructions()

        return f"""{section_prompt}

## Feature Request
{self.context.request if self.context else "No feature description provided"}

{tool_instructions}

## Code Analysis Context (Initial)
{context_info}

{feedback_section}

{approved_context}

## Guidelines for Generating This Section

1. **Use Tools First**: Query the codebase using available tools to gather accurate information
2. **Be Specific**: Reference actual component names, file paths, and code patterns discovered via tools
3. **Be Verifiable**: Only make claims based on evidence from tool queries
4. **Be Accurate**: Use information from tool results, not assumptions
5. **Be Concise**: Focus on essential information relevant to this section

Generate the {section_name} section now:
"""

    def _build_tool_instructions(self) -> str:
        """Build instructions about available MCP tools.

        MCP tools are available via the Copilot SDK session's mcp_servers config.
        The SDK handles tool execution automatically.
        """
        if not self.session:
            return ""

        return """
## Available Tools (USE THESE!)

You have access to the following tools to gather accurate information from the codebase:

### Code Graph Tools (Neo4j)
- **query_code_structure**: Execute Cypher queries to find components, classes, functions, relationships
  Example: MATCH (c:Class)-[:DEPENDS_ON]->(d) WHERE c.name CONTAINS 'Order' RETURN c, d
- **get_component_dependencies**: Get upstream/downstream dependencies of a component
- **search_similar_features**: Find similar features in the codebase

### Filesystem Tools
- **read_file**: Read source code files to understand implementation details
- **list_directory**: List files in a directory
- **search_files**: Search for files matching a pattern (e.g., **/*.py, **/order*.ts)
- **get_file_info**: Get metadata about a file

**IMPORTANT**: Use these tools to gather REAL context before writing the section.
Do NOT make assumptions - query the codebase to get accurate information.
"""

    def _build_template_section_prompt(self, section_name: str) -> str:
        """
        Build the prompt from the parsed template section definition.

        This replaces the hardcoded prompts - everything comes from the template!
        """
        # Get section from template
        section = None
        if self.parsed_template:
            section = self.parsed_template.get_section(section_name)

        if not section:
            # Fallback for unknown sections
            return f"# Generate {section_name}\n\nWrite the {section_name} section for this BRD."

        # Build prompt from template section definition
        lines = [
            f"# Generate: {section.name}",
            "",
            f"## What This Section Should Contain",
            section.description if section.description else f"Write the {section.name} section.",
            "",
        ]

        # Add content guidelines from template
        if section.content_guidelines:
            lines.append("## Content Guidelines")
            for guideline in section.content_guidelines:
                lines.append(f"- {guideline}")
            lines.append("")

        # Add format requirements from template
        if section.format_hints:
            lines.append("## Format Requirements")
            for hint in section.format_hints:
                lines.append(f"- {hint}")
            lines.append("")

        # Add examples from template
        if section.examples:
            lines.append("## Examples from Template")
            for example in section.examples[:2]:  # Limit examples
                lines.append(f"> {example}")
            lines.append("")

        # Special handling for diagram sections
        if section.is_diagram:
            lines.append("## Diagram Requirements")
            lines.append("- Include a Mermaid or PlantUML diagram")
            lines.append("- Use proper diagram syntax")
            lines.append("")

        # Add general writing guidelines from template
        if self.parsed_template and self.parsed_template.writing_guidelines:
            lines.append("## Writing Guidelines")
            for guideline in self.parsed_template.writing_guidelines[:5]:
                lines.append(f"- {guideline}")
            lines.append("")

        return "\n".join(lines)


    def _build_context_info(self) -> str:
        """Build context information string from aggregated context."""
        if not self.context:
            return "No code analysis context available."

        lines = []

        # Architecture info
        if self.context.architecture:
            arch = self.context.architecture
            lines.append("### Architecture")
            if arch.components:
                lines.append(f"Components: {len(arch.components)}")
                for comp in arch.components[:5]:  # First 5
                    lines.append(f"  - {comp.name} ({comp.type})")
            if arch.api_contracts:
                lines.append(f"API Contracts: {len(arch.api_contracts)}")
            if arch.dependencies:
                lines.append(f"Dependencies: {len(arch.dependencies)}")

        # Implementation info
        if self.context.implementation:
            impl = self.context.implementation
            lines.append("\n### Implementation Files")
            if impl.key_files:
                for kf in impl.key_files[:5]:  # First 5
                    lines.append(f"  - {kf.path}")

        # Similar features
        if self.context.similar_features:
            lines.append("\n### Similar Features Found")
            for sf in self.context.similar_features[:3]:
                lines.append(f"  - {sf}")

        return "\n".join(lines) if lines else "Limited context available."

    def _build_approved_sections_context(self) -> str:
        """Build context from already approved sections."""
        if not self.sections_approved:
            return ""

        lines = ["## Previously Approved Sections (for reference)"]

        for section_name in self.sections_approved:
            if section_name in self.sections_generated:
                content = self.sections_generated[section_name]
                # Truncate long content
                if len(content) > 500:
                    content = content[:500] + "..."
                lines.append(f"\n### {section_name.replace('_', ' ').title()}")
                lines.append(content)

        return "\n".join(lines)

    async def _handle_feedback(self, message: AgentMessage) -> None:
        """Handle feedback from the verifier and regenerate section."""
        section_name = message.section_name
        feedback = message.content

        if not section_name:
            logger.warning("Received feedback without section name")
            return

        logger.info(f"BRD Generator: Received feedback for '{section_name}'")

        # Check regeneration limit
        current_count = self.regeneration_count.get(section_name, 0)
        if current_count >= self.max_regenerations:
            logger.warning(
                f"BRD Generator: Max regenerations ({self.max_regenerations}) "
                f"reached for '{section_name}'"
            )
            # Mark as approved anyway with warning
            self.sections_approved.add(section_name)
            await self._check_completion(message.iteration)
            return

        # Regenerate the section with feedback
        await self._generate_section(
            section_name,
            message.iteration,
            feedback=feedback,
        )

    async def _handle_approval(self, message: AgentMessage) -> None:
        """Handle section approval from the verifier."""
        section_name = message.section_name

        if section_name:
            logger.info(f"BRD Generator: Section '{section_name}' approved")
            self.sections_approved.add(section_name)

        await self._check_completion(message.iteration)

    async def _handle_verification_result(self, message: AgentMessage) -> None:
        """Handle full verification result from verifier."""
        evidence_bundle: EvidenceBundle = message.content

        if evidence_bundle.is_approved:
            # BRD is complete and verified
            logger.info("BRD Generator: Full BRD approved!")
            await self._finalize_brd(message.iteration)
        else:
            # Need to regenerate failed sections
            for section_name in evidence_bundle.sections_to_regenerate:
                section_result = next(
                    (s for s in evidence_bundle.sections if s.section_name == section_name),
                    None
                )
                if section_result:
                    await self._generate_section(
                        section_name,
                        message.iteration,
                        feedback=self._extract_feedback_from_result(section_result),
                    )

    def _extract_feedback_from_result(self, result: SectionVerificationResult) -> str:
        """Extract actionable feedback from verification result."""
        feedback_parts = [
            f"Section Status: {result.verification_status.value}",
            f"Confidence: {result.overall_confidence:.2f}",
            f"Hallucination Risk: {result.hallucination_risk.value}",
            "",
            "Issues Found:",
        ]

        for issue in result.issues:
            feedback_parts.append(f"- {issue}")

        feedback_parts.append("\nClaims Needing Revision:")

        for claim in result.claims:
            if claim.feedback:
                feedback_parts.append(f"- {claim.text[:50]}...")
                feedback_parts.append(f"  Feedback: {claim.feedback}")
                if claim.suggested_correction:
                    feedback_parts.append(f"  Suggestion: {claim.suggested_correction}")

        if result.suggestions:
            feedback_parts.append("\nSuggestions:")
            for suggestion in result.suggestions:
                feedback_parts.append(f"- {suggestion}")

        return "\n".join(feedback_parts)

    async def _check_completion(self, iteration: int) -> None:
        """Check if all sections are approved and finalize if so."""
        # Get required sections from template (template-driven!)
        required_sections = set(self.get_section_names())
        if required_sections.issubset(self.sections_approved):
            logger.info("BRD Generator: All sections approved!")
            await self._finalize_brd(iteration)

    async def _finalize_brd(self, iteration: int) -> None:
        """Finalize and send the complete BRD."""
        logger.info("BRD Generator: Finalizing BRD")

        # Build the BRD document from approved sections
        brd = self._build_brd_document()
        self.current_brd = brd

        # Send complete BRD to orchestrator
        await self.send(AgentMessage(
            message_type=MessageType.BRD_COMPLETE,
            recipient=AgentRole.ORCHESTRATOR,
            content=brd,
            iteration=iteration,
            metadata={
                "sections_count": len(self.sections_approved),
                "total_regenerations": sum(self.regeneration_count.values()),
            },
        ))

    def _build_brd_document(self) -> BRDDocument:
        """
        Build the BRDDocument from generated sections.

        This is template-driven - sections are matched by name patterns
        rather than hardcoded keys.
        """
        # Find sections by pattern matching (template-driven)
        func_reqs_content = self._find_section_content([
            "functional requirements", "functional", "requirements"
        ])
        tech_reqs_content = self._find_section_content([
            "technical requirements", "technical", "non-functional"
        ])
        objectives_content = self._find_section_content([
            "objectives", "goals", "success criteria"
        ])
        dependencies_content = self._find_section_content([
            "dependencies", "assumptions", "constraints"
        ])
        risks_content = self._find_section_content([
            "risks", "risk", "concerns", "challenges"
        ])
        business_context_content = self._find_section_content([
            "business context", "overview", "feature overview", "background", "introduction"
        ])

        # Parse into structured data
        func_reqs = self._parse_requirements(func_reqs_content, "FR")
        tech_reqs = self._parse_requirements(tech_reqs_content, "TR")
        objectives = self._parse_list(objectives_content)
        dependencies = self._parse_list(dependencies_content)
        risks = self._parse_list(risks_content)

        return BRDDocument(
            title=f"BRD: {self.context.request[:50] if self.context else 'Feature Request'}",
            business_context=business_context_content,
            objectives=objectives,
            functional_requirements=func_reqs,
            technical_requirements=tech_reqs,
            dependencies=dependencies,
            risks=risks,
        )

    def _find_section_content(self, patterns: list[str]) -> str:
        """
        Find section content by matching patterns against generated section names.

        This allows template-driven section names to map to the BRD output structure.
        """
        for section_name, content in self.sections_generated.items():
            section_lower = section_name.lower()
            for pattern in patterns:
                if pattern in section_lower:
                    return content
        return ""

    def _parse_requirements(self, content: str, prefix: str) -> list[Requirement]:
        """Parse requirements from generated content."""
        requirements = []

        # Pattern: FR-001: Title or TR-001: Title
        pattern = rf"({prefix}-\d+):\s*(.+?)(?={prefix}-\d+:|$)"
        matches = re.findall(pattern, content, re.DOTALL)

        for req_id, req_content in matches:
            lines = req_content.strip().split("\n")
            title = lines[0].strip() if lines else "Untitled"

            # Extract description
            desc_match = re.search(
                r"Description:\s*(.+?)(?=Priority:|Acceptance|Components|$)",
                req_content, re.DOTALL
            )
            description = desc_match.group(1).strip() if desc_match else req_content[:200]

            # Extract priority
            priority_match = re.search(r"Priority:\s*(High|Medium|Low)", req_content, re.IGNORECASE)
            priority = priority_match.group(1).lower() if priority_match else "medium"

            # Extract acceptance criteria
            ac_list = []
            ac_match = re.search(r"Acceptance Criteria:(.+?)(?=Priority:|Components|$)", req_content, re.DOTALL)
            if ac_match:
                for line in ac_match.group(1).split("\n"):
                    line = line.strip().lstrip("-").strip()
                    if line:
                        ac_list.append(AcceptanceCriteria(criterion=line))

            requirements.append(Requirement(
                id=req_id,
                title=title,
                description=description,
                priority=priority,
                acceptance_criteria=ac_list,
            ))

        # Fallback if no requirements found
        if not requirements:
            items = self._parse_list(content)
            for i, item in enumerate(items, 1):
                requirements.append(Requirement(
                    id=f"{prefix}-{i:03d}",
                    title=item[:100],
                    description=item,
                    priority="medium",
                ))

        return requirements

    def _parse_list(self, content: str) -> list[str]:
        """Parse a bulleted/numbered list from content."""
        items = []
        for line in content.split("\n"):
            line = line.strip()
            # Remove bullet points and numbers
            line = re.sub(r"^[\d\.\-\*\•]+\s*", "", line)
            if line and len(line) > 3:  # Skip very short lines
                items.append(line)
        return items

    def _generate_mock_response(self, prompt: str) -> str:
        """Generate mock response for testing without LLM."""
        if "executive_summary" in prompt.lower():
            return """
This feature implements the requested functionality based on the code analysis.
It will impact the core business processes and improve user experience.
The technical approach leverages existing patterns in the codebase.
Key stakeholders include product, engineering, and operations teams.
"""
        elif "business_context" in prompt.lower():
            return """
The current system lacks the requested capability, creating friction for users.
This gap results in manual workarounds and reduced efficiency.
Implementing this feature will address customer feedback and competitive requirements.
Expected outcomes include improved user satisfaction and operational efficiency.
"""
        elif "functional_requirements" in prompt.lower():
            return """
FR-001: Core Feature Implementation
Description: Implement the primary feature functionality as described
Priority: High
Acceptance Criteria:
- Feature is accessible from the main interface
- Feature processes inputs correctly
- Feature produces expected outputs

FR-002: User Interface Updates
Description: Update UI to support the new feature
Priority: Medium
Acceptance Criteria:
- UI elements are intuitive and accessible
- Feedback is provided for user actions
"""
        elif "technical_requirements" in prompt.lower():
            return """
TR-001: API Endpoint Implementation
Description: Create new API endpoints for the feature
Priority: High
Components Affected: API Gateway, Core Service

TR-002: Database Schema Updates
Description: Update database schema to support new data
Priority: High
Components Affected: Database, ORM Layer
"""
        elif "objectives" in prompt.lower():
            return """
1. Deliver the core feature functionality within the specified timeline
2. Achieve 95% test coverage for new code
3. Maintain system performance within acceptable thresholds
4. Ensure backward compatibility with existing integrations
"""
        elif "dependencies" in prompt.lower():
            return """
- Authentication Service: Required for user authorization
- Database: Schema updates needed before implementation
- API Gateway: Route configuration updates
- Frontend Framework: UI component compatibility
"""
        elif "risks" in prompt.lower():
            return """
RISK-001: Integration Complexity
Description: Integration with existing systems may be complex
Impact: Medium
Probability: Medium
Mitigation: Early integration testing and incremental approach

RISK-002: Performance Impact
Description: New feature may affect system performance
Impact: High
Probability: Low
Mitigation: Performance testing and optimization
"""
        else:
            return """
Acceptance Criteria for Feature Completion:
1. All functional requirements implemented and tested
2. All technical requirements met
3. Performance benchmarks achieved
4. Security review passed
5. Documentation completed
"""

    def get_current_brd(self) -> Optional[BRDDocument]:
        """Get the current BRD document."""
        return self.current_brd

    def get_section_status(self) -> dict[str, Any]:
        """Get status of all sections (from template)."""
        return {
            section: {
                "generated": section in self.sections_generated,
                "approved": section in self.sections_approved,
                "regeneration_count": self.regeneration_count.get(section, 0),
            }
            for section in self.get_section_names()
        }
