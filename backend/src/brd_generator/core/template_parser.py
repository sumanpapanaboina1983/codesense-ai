"""
Template Parser - Dynamically parse BRD templates using LLM.

This module allows users to upload any BRD template format and the system
will understand the structure, sections, and content expectations dynamically.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BRDSection:
    """A section extracted from a BRD template."""

    name: str  # e.g., "Feature Overview", "Functional Requirements"
    order: int  # Section order in the template
    description: str  # What this section should contain
    content_guidelines: list[str] = field(default_factory=list)  # Writing guidelines
    format_hints: list[str] = field(default_factory=list)  # Format requirements (table, list, etc.)
    examples: list[str] = field(default_factory=list)  # Example content from template
    is_required: bool = True
    is_diagram: bool = False  # Whether this section expects a diagram


@dataclass
class ParsedBRDTemplate:
    """A fully parsed BRD template."""

    template_name: str = "Custom BRD Template"
    purpose: str = ""  # Overall purpose of the BRD
    writing_guidelines: list[str] = field(default_factory=list)  # General writing guidelines
    sections: list[BRDSection] = field(default_factory=list)
    raw_template: str = ""  # Original template text

    def get_section_names(self) -> list[str]:
        """Get ordered list of section names."""
        return [s.name for s in sorted(self.sections, key=lambda x: x.order)]

    def get_section(self, name: str) -> Optional[BRDSection]:
        """Get a section by name (case-insensitive)."""
        name_lower = name.lower()
        for section in self.sections:
            if section.name.lower() == name_lower:
                return section
        return None

    def to_generation_prompt(self) -> str:
        """Convert parsed template to a prompt for BRD generation."""
        lines = [
            "# BRD Template Structure",
            "",
            f"## Purpose",
            self.purpose or "Generate a comprehensive Business Requirements Document.",
            "",
        ]

        if self.writing_guidelines:
            lines.append("## Writing Guidelines")
            for guideline in self.writing_guidelines:
                lines.append(f"- {guideline}")
            lines.append("")

        lines.append("## Sections to Generate")
        lines.append("")

        for section in sorted(self.sections, key=lambda x: x.order):
            lines.append(f"### {section.order}. {section.name}")
            lines.append(f"**Description:** {section.description}")

            if section.content_guidelines:
                lines.append("**Content Guidelines:**")
                for guideline in section.content_guidelines:
                    lines.append(f"  - {guideline}")

            if section.format_hints:
                lines.append("**Format:**")
                for hint in section.format_hints:
                    lines.append(f"  - {hint}")

            if section.examples:
                lines.append("**Example:**")
                for example in section.examples[:2]:  # Limit examples
                    lines.append(f"  > {example[:200]}")

            lines.append("")

        return "\n".join(lines)


class BRDTemplateParser:
    """
    Parse BRD templates dynamically using LLM.

    This allows users to upload any BRD template format and the system
    will understand the structure and content expectations.
    """

    # Prompt for LLM to parse the template
    TEMPLATE_PARSING_PROMPT = """
Analyze the following BRD (Business Requirements Document) template and extract its structure.

## Template Content:
{template_content}

## Instructions:

Parse this template and extract:

1. **Purpose**: What is the overall purpose of this BRD template?

2. **Writing Guidelines**: Any general writing guidelines or best practices mentioned.

3. **Sections**: For each section in the template, extract:
   - Section name (exactly as written)
   - Section order (1, 2, 3, ...)
   - Description of what this section should contain
   - Content guidelines (what to include, how to write)
   - Format hints (should it be a table? list? diagram?)
   - Example content if provided
   - Whether it's required or optional
   - Whether it expects a diagram (Mermaid, PlantUML, etc.)

## Output Format (JSON):

```json
{{
  "template_name": "Name of the template",
  "purpose": "Overall purpose description",
  "writing_guidelines": [
    "Guideline 1",
    "Guideline 2"
  ],
  "sections": [
    {{
      "name": "Section Name",
      "order": 1,
      "description": "What this section should contain",
      "content_guidelines": ["Guideline 1", "Guideline 2"],
      "format_hints": ["Use bullet points", "Include table"],
      "examples": ["Example content from template"],
      "is_required": true,
      "is_diagram": false
    }}
  ]
}}
```

Extract ALL sections from the template. Be thorough and capture the exact structure.
Output ONLY valid JSON, no other text.
"""

    def __init__(self, copilot_session: Any = None):
        """
        Initialize the template parser.

        Args:
            copilot_session: Copilot SDK session for LLM access
        """
        self.session = copilot_session
        self._copilot_available = copilot_session is not None

    async def parse_template(self, template_content: str) -> ParsedBRDTemplate:
        """
        Parse a BRD template using LLM.

        Args:
            template_content: The raw template text

        Returns:
            ParsedBRDTemplate with extracted structure
        """
        logger.info(f"Parsing BRD template ({len(template_content)} chars)")

        if not template_content or len(template_content.strip()) < 50:
            logger.warning("Template content too short, using default structure")
            return self._get_default_template()

        # Build the parsing prompt
        prompt = self.TEMPLATE_PARSING_PROMPT.format(
            template_content=template_content[:15000]  # Limit to avoid token issues
        )

        # Send to LLM via Copilot SDK
        response = await self._send_to_llm(prompt)

        # Parse the JSON response
        parsed = self._parse_llm_response(response, template_content)

        logger.info(f"Parsed template with {len(parsed.sections)} sections")
        return parsed

    async def _send_to_llm(self, prompt: str) -> str:
        """Send prompt to LLM via Copilot SDK."""
        if not self._copilot_available or not self.session:
            logger.warning("Copilot session not available, using rule-based parsing")
            return ""

        try:
            import asyncio

            message_options = {"prompt": prompt}
            logger.info(f"Sending template parsing prompt to LLM ({len(prompt)} chars)")

            # Use send_and_wait if available
            if hasattr(self.session, 'send_and_wait'):
                event = await asyncio.wait_for(
                    self.session.send_and_wait(message_options, timeout=120),
                    timeout=120
                )
                if event:
                    return self._extract_from_event(event)

            # Fallback to send()
            if hasattr(self.session, 'send'):
                await self.session.send(message_options)
                return await self._wait_for_response(120)

            return ""

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return ""

    def _extract_from_event(self, event: Any) -> str:
        """Extract text content from a Copilot event."""
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
            logger.error(f"Error extracting from event: {e}")
            return ""

    async def _wait_for_response(self, timeout: float) -> str:
        """Wait for LLM response by polling messages."""
        import asyncio

        start_time = asyncio.get_event_loop().time()
        poll_interval = 1.0

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return ""

            try:
                messages = self.session.get_messages()
                for msg in reversed(messages):
                    if hasattr(msg, 'data'):
                        data = msg.data
                        if hasattr(data, 'role') and data.role == 'assistant':
                            return self._extract_from_event(msg)
            except Exception:
                pass

            await asyncio.sleep(poll_interval)

    def _parse_llm_response(
        self,
        response: str,
        original_template: str
    ) -> ParsedBRDTemplate:
        """Parse the LLM JSON response into ParsedBRDTemplate."""
        if not response:
            # Fallback to rule-based parsing
            return self._parse_template_rule_based(original_template)

        try:
            # Extract JSON from response (might have markdown code blocks)
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find raw JSON
                json_str = response.strip()

            data = json.loads(json_str)

            # Build ParsedBRDTemplate
            template = ParsedBRDTemplate(
                template_name=data.get("template_name", "Custom BRD Template"),
                purpose=data.get("purpose", ""),
                writing_guidelines=data.get("writing_guidelines", []),
                raw_template=original_template,
            )

            # Parse sections
            for section_data in data.get("sections", []):
                section = BRDSection(
                    name=section_data.get("name", "Unknown Section"),
                    order=section_data.get("order", 99),
                    description=section_data.get("description", ""),
                    content_guidelines=section_data.get("content_guidelines", []),
                    format_hints=section_data.get("format_hints", []),
                    examples=section_data.get("examples", []),
                    is_required=section_data.get("is_required", True),
                    is_diagram=section_data.get("is_diagram", False),
                )
                template.sections.append(section)

            return template

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            return self._parse_template_rule_based(original_template)
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return self._parse_template_rule_based(original_template)

    def _parse_template_rule_based(self, template_content: str) -> ParsedBRDTemplate:
        """
        Fallback: Parse template using rule-based approach.

        Looks for markdown headers (##, ###) to identify sections.
        """
        logger.info("Using rule-based template parsing")

        template = ParsedBRDTemplate(
            template_name="Custom BRD Template",
            raw_template=template_content,
        )

        # Extract purpose from beginning of document
        purpose_match = re.search(
            r'(?:purpose|overview|introduction)[:\s]*\n+(.*?)(?=\n#|\n\*\*|\Z)',
            template_content,
            re.IGNORECASE | re.DOTALL
        )
        if purpose_match:
            template.purpose = purpose_match.group(1).strip()[:500]

        # Extract writing guidelines from tables or lists
        guidelines_section = re.search(
            r'(?:writing guidelines?|best practices?|guidelines?)[:\s]*\n+(.*?)(?=\n##|\Z)',
            template_content,
            re.IGNORECASE | re.DOTALL
        )
        if guidelines_section:
            # Extract from table or bullet points
            guidelines_text = guidelines_section.group(1)
            # Match table rows or bullet points
            guidelines = re.findall(r'[✅\-\*]\s*(.+?)(?:\s*\||\n|$)', guidelines_text)
            template.writing_guidelines = [g.strip() for g in guidelines if g.strip()][:10]

        # Find all sections (## or ### headers)
        # Pattern: ## 1. Section Name or ### Section Name
        section_pattern = r'#{2,3}\s*(?:\d+\.?\s*)?(?:🎯|📋|📑|👥|🔄|🧭|⚠|✅|🧱)?\s*(\d+\.?\s*)?(.+?)(?:\n|$)'
        header_matches = list(re.finditer(section_pattern, template_content))

        for i, match in enumerate(header_matches):
            section_number = match.group(1)
            section_name = match.group(2).strip()

            # Skip meta sections like "Purpose", "Writing Guidelines"
            if any(skip in section_name.lower() for skip in [
                'purpose', 'writing', 'guideline', 'structure', 'practice'
            ]):
                continue

            # Get content until next section
            start = match.end()
            end = header_matches[i + 1].start() if i + 1 < len(header_matches) else len(template_content)
            section_content = template_content[start:end].strip()

            # Extract description (first paragraph or sentence)
            desc_match = re.match(r'^[*\s]*(.+?)(?:\n\n|\n\*|\n-|$)', section_content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else ""
            description = re.sub(r'\*+', '', description)  # Remove bold markers

            # Check for format hints
            format_hints = []
            if re.search(r'\|.*\|.*\|', section_content):
                format_hints.append("Use table format")
            if re.search(r'^\s*[\d\-\*]', section_content, re.MULTILINE):
                format_hints.append("Use numbered or bulleted list")
            if re.search(r'```mermaid|```plantuml|sequenceDiagram', section_content, re.IGNORECASE):
                format_hints.append("Include diagram (Mermaid/PlantUML)")

            # Extract examples
            examples = []
            example_match = re.search(r'(?:example|format example)[:\s]*\n*(.*?)(?=\n##|\n\*\*[A-Z]|\Z)', section_content, re.IGNORECASE | re.DOTALL)
            if example_match:
                example_text = example_match.group(1).strip()
                # Get first few lines as example
                example_lines = [l.strip() for l in example_text.split('\n') if l.strip()][:3]
                examples = example_lines

            # Determine order
            order = int(re.sub(r'\D', '', section_number)) if section_number else i + 1

            # Check if diagram section
            is_diagram = bool(re.search(r'diagram|sequence|flow|mermaid|plantuml', section_name.lower()))

            # Check if optional
            is_required = 'optional' not in section_name.lower()

            section = BRDSection(
                name=section_name,
                order=order,
                description=description[:500],
                content_guidelines=self._extract_guidelines_from_content(section_content),
                format_hints=format_hints,
                examples=examples,
                is_required=is_required,
                is_diagram=is_diagram,
            )
            template.sections.append(section)

        # If no sections found, create default structure
        if not template.sections:
            template = self._get_default_template()
            template.raw_template = template_content

        return template

    def _extract_guidelines_from_content(self, content: str) -> list[str]:
        """Extract content guidelines from section content."""
        guidelines = []

        # Look for "should", "must", bullet points with instructions
        patterns = [
            r'(?:should|must|can|will)\s+(.+?)(?:\.|$)',
            r'[•\-\*]\s*(.+?)(?:\n|$)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches[:5]:
                clean = match.strip()
                if len(clean) > 10 and len(clean) < 200:
                    guidelines.append(clean)

        return guidelines[:5]

    def _get_default_template(self) -> ParsedBRDTemplate:
        """Return a default BRD template structure."""
        return ParsedBRDTemplate(
            template_name="Default BRD Template",
            purpose="Document business requirements and technical implementation details for stakeholders and developers.",
            writing_guidelines=[
                "Use plain English, avoid unnecessary jargon",
                "Be specific and deterministic, avoid vague phrases",
                "Include technical implementation details for development planning",
                "Capture all business rules explicitly with code references",
                "Use numbered lists for process flows",
                "Reference actual component names, file paths, and entity fields",
            ],
            sections=[
                BRDSection(
                    name="Feature Overview",
                    order=1,
                    description="A plain English summary of what the feature enables from a business standpoint.",
                    content_guidelines=[
                        "Answer: What problem does this solve?",
                        "Answer: Who benefits from this feature?",
                        "Keep it high-level and business-focused",
                        "Mention key entry points (JSPs, WebFlows) at the end",
                    ],
                    format_hints=["Use paragraphs", "End with key components list"],
                ),
                BRDSection(
                    name="Functional Requirements",
                    order=2,
                    description="Describe what the system must do in terms of business behavior.",
                    content_guidelines=[
                        "Use simple, active statements",
                        "Start with 'The system must...'",
                        "Group similar requirements under subheadings",
                    ],
                    format_hints=["Use bulleted list"],
                ),
                BRDSection(
                    name="Business Validations and Rules",
                    order=3,
                    description="Capture all logic constraints and business rules.",
                    content_guidelines=[
                        "Explain what is allowed, required, or blocked",
                        "Express rules in business terms",
                        "Include all conditional logic",
                    ],
                    format_hints=["Use bulleted list"],
                ),
                BRDSection(
                    name="Actors and System Interactions",
                    order=4,
                    description="List all user roles or systems that interact with this functionality.",
                    content_guidelines=[
                        "Use business-facing terms (Customer, Agent, etc.)",
                        "Describe each actor's role in the process",
                    ],
                    format_hints=["Use table format"],
                ),
                BRDSection(
                    name="Business Process Flow",
                    order=5,
                    description="Describe step-by-step how the feature works from initiation to resolution.",
                    content_guidelines=[
                        "Use numbered lists for linear flows",
                        "Use 'if...then...' for conditionals",
                        "Cover happy path and error scenarios",
                    ],
                    format_hints=["Use numbered list"],
                ),
                BRDSection(
                    name="Sequence Diagram",
                    order=6,
                    description="Visual representation of the flow between system components.",
                    content_guidelines=[
                        "Show interaction between UI, controllers, services, and data layer",
                        "Use actual component names from the codebase",
                        "Include key method calls",
                    ],
                    format_hints=["Use Mermaid sequenceDiagram syntax"],
                    is_diagram=True,
                ),
                BRDSection(
                    name="Technical Architecture",
                    order=7,
                    description="Component inventory organized by implementation layer for development planning.",
                    content_guidelines=[
                        "List all UI components (JSP pages) with file paths",
                        "List all WebFlow definitions with state names",
                        "List all Controllers/Actions with key methods",
                        "List all Services/Builders/Validators",
                        "List all DAOs/Repositories with entity associations",
                        "Show the flow: UI → WebFlow → Controller → Service → DAO → Entity",
                    ],
                    format_hints=[
                        "Use tables with Name | Path | Description columns",
                        "Group by layer: UI Layer, Flow Layer, Controller Layer, Service Layer, Data Layer",
                    ],
                ),
                BRDSection(
                    name="Data Model",
                    order=8,
                    description="Entity definitions with fields, data types, and relationships for database planning.",
                    content_guidelines=[
                        "List each entity with its purpose",
                        "Show all fields with their data types",
                        "Include validation annotations (@NotNull, @Size, @Range)",
                        "Document relationships between entities (FK references)",
                        "Note any database constraints",
                    ],
                    format_hints=[
                        "Use table format: Field | Type | Constraints | Description",
                        "Group related entities together",
                        "Include entity relationship summary",
                    ],
                ),
                BRDSection(
                    name="Implementation Mapping",
                    order=9,
                    description="End-to-end mapping from UI to database for each major operation.",
                    content_guidelines=[
                        "Map each UI action to its implementation path",
                        "Show: UI Field → Controller Method → Service Method → DAO Method → Entity Field",
                        "Include validation checkpoints in the flow",
                        "Document where business rules are enforced",
                    ],
                    format_hints=[
                        "Use flow diagrams or tables",
                        "Example: 'Save Legal Entity' → LegalEntityWizardAction.saveEntity() → LegalEntityBuilder.build() → LeslegalEntityDao.persist() → LeslegalEntity",
                    ],
                ),
                BRDSection(
                    name="Assumptions and Constraints",
                    order=10,
                    description="State conditions assumed by the system and any limitations.",
                    content_guidelines=[
                        "List what is assumed to be true",
                        "Document scope limitations",
                        "Note any exclusions",
                        "Include technical constraints (frameworks, patterns used)",
                    ],
                    format_hints=["Use bulleted list"],
                ),
                BRDSection(
                    name="Acceptance Criteria",
                    order=11,
                    description="List business-facing pass/fail conditions for feature completion.",
                    content_guidelines=[
                        "Make criteria measurable and actionable",
                        "Include success metrics",
                        "Cover edge cases",
                    ],
                    format_hints=["Use bulleted list"],
                ),
            ],
        )
