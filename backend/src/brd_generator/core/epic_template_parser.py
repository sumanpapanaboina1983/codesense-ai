"""EPIC and Backlog Template Parser.

Parses custom templates to extract:
- Field structure and order
- Content guidelines per field
- Length hints
- Format requirements
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from ..models.epic import EpicFieldConfig, BacklogFieldConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedEpicTemplate:
    """Parsed EPIC template with extracted fields and guidelines."""
    template_name: str = "Custom EPIC Template"
    purpose: str = ""
    writing_guidelines: list[str] = field(default_factory=list)
    fields: list[EpicFieldConfig] = field(default_factory=list)
    raw_template: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "template_name": self.template_name,
            "purpose": self.purpose,
            "writing_guidelines": self.writing_guidelines,
            "fields": [f.model_dump() for f in self.fields],
            "raw_template": self.raw_template,
        }


@dataclass
class ParsedBacklogTemplate:
    """Parsed Backlog template with extracted fields and guidelines."""
    template_name: str = "Custom Backlog Template"
    purpose: str = ""
    writing_guidelines: list[str] = field(default_factory=list)
    fields: list[BacklogFieldConfig] = field(default_factory=list)
    item_types: list[str] = field(default_factory=lambda: ["user_story", "task", "spike"])
    raw_template: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "template_name": self.template_name,
            "purpose": self.purpose,
            "writing_guidelines": self.writing_guidelines,
            "fields": [f.model_dump() for f in self.fields],
            "item_types": self.item_types,
            "raw_template": self.raw_template,
        }


# Default EPIC fields with typical word counts
DEFAULT_EPIC_FIELDS = [
    EpicFieldConfig(field_name="title", enabled=True, target_words=20),
    EpicFieldConfig(field_name="description", enabled=True, target_words=150),
    EpicFieldConfig(field_name="business_value", enabled=True, target_words=100),
    EpicFieldConfig(field_name="objectives", enabled=True, target_words=50),
    EpicFieldConfig(field_name="acceptance_criteria", enabled=True, target_words=30),
    EpicFieldConfig(field_name="technical_notes", enabled=True, target_words=80),
]

# Default Backlog fields with typical word counts (Option B - Moderate with Testing)
DEFAULT_BACKLOG_FIELDS = [
    BacklogFieldConfig(field_name="description", enabled=True, target_words=150),
    BacklogFieldConfig(field_name="acceptance_criteria", enabled=True, target_words=50),
    BacklogFieldConfig(field_name="pre_conditions", enabled=True, target_words=30),
    BacklogFieldConfig(field_name="post_conditions", enabled=True, target_words=30),
    BacklogFieldConfig(field_name="testing_approach", enabled=True, target_words=80),
    BacklogFieldConfig(field_name="edge_cases", enabled=True, target_words=50),
]


class EpicBacklogTemplateParser:
    """Parser for EPIC and Backlog templates.

    Uses LLM to understand template structure and extract:
    - Required fields
    - Word count suggestions
    - Format guidelines
    """

    EPIC_PARSING_PROMPT = """Analyze this EPIC template and extract the field structure.

## Template Content:
{template_content}

## Task:
Identify all fields that an EPIC should contain based on this template.
For each field, provide:
1. The field name (lowercase, snake_case, e.g., "description", "business_value", "objectives")
2. Whether it's enabled/required
3. Suggested word count
4. Any specific guidelines from the template

Standard EPIC fields include: title, description, business_value, objectives, acceptance_criteria, technical_notes, affected_components

Return as JSON:
```json
{{
  "template_name": "Template Name",
  "purpose": "Brief description of template purpose",
  "writing_guidelines": ["Guideline 1", "Guideline 2"],
  "fields": [
    {{
      "field_name": "description",
      "enabled": true,
      "target_words": 150,
      "guidelines": "Should include context and scope"
    }},
    {{
      "field_name": "business_value",
      "enabled": true,
      "target_words": 100,
      "guidelines": "Focus on business impact"
    }}
  ]
}}
```
"""

    BACKLOG_PARSING_PROMPT = """Analyze this Backlog/User Story template and extract the field structure.

## Template Content:
{template_content}

## Task:
Identify all fields that a backlog item should contain based on this template.
For each field, provide:
1. The field name (lowercase, snake_case)
2. Whether it's enabled/required
3. Suggested word count
4. Any specific guidelines from the template

Standard backlog fields include: title, description, as_a, i_want, so_that, acceptance_criteria, technical_notes, files_to_modify, files_to_create

Also identify which item types are supported: user_story, task, spike, bug

Return as JSON:
```json
{{
  "template_name": "Template Name",
  "purpose": "Brief description of template purpose",
  "writing_guidelines": ["Guideline 1", "Guideline 2"],
  "item_types": ["user_story", "task", "spike"],
  "fields": [
    {{
      "field_name": "description",
      "enabled": true,
      "target_words": 80,
      "guidelines": "Clear and actionable"
    }},
    {{
      "field_name": "acceptance_criteria",
      "enabled": true,
      "target_words": 30,
      "guidelines": "Testable conditions"
    }}
  ]
}}
```
"""

    def __init__(self, copilot_session: Any = None):
        """Initialize the parser.

        Args:
            copilot_session: Copilot SDK session for LLM access
        """
        self.session = copilot_session

    async def parse_epic_template(self, template: str) -> ParsedEpicTemplate:
        """Parse EPIC template using LLM.

        Args:
            template: The template content to parse

        Returns:
            ParsedEpicTemplate with extracted fields and guidelines
        """
        if not template or not template.strip():
            return self._get_default_epic_template()

        if not self.session:
            logger.warning("No Copilot session, using fallback parsing")
            return self._parse_epic_template_fallback(template)

        try:
            prompt = self.EPIC_PARSING_PROMPT.format(template_content=template[:4000])
            response = await self._send_to_llm(prompt)
            parsed = self._extract_epic_fields(response, template)
            return parsed
        except Exception as e:
            logger.error(f"Failed to parse EPIC template with LLM: {e}")
            return self._parse_epic_template_fallback(template)

    async def parse_backlog_template(self, template: str) -> ParsedBacklogTemplate:
        """Parse Backlog template using LLM.

        Args:
            template: The template content to parse

        Returns:
            ParsedBacklogTemplate with extracted fields and guidelines
        """
        if not template or not template.strip():
            return self._get_default_backlog_template()

        if not self.session:
            logger.warning("No Copilot session, using fallback parsing")
            return self._parse_backlog_template_fallback(template)

        try:
            prompt = self.BACKLOG_PARSING_PROMPT.format(template_content=template[:4000])
            response = await self._send_to_llm(prompt)
            parsed = self._extract_backlog_fields(response, template)
            return parsed
        except Exception as e:
            logger.error(f"Failed to parse Backlog template with LLM: {e}")
            return self._parse_backlog_template_fallback(template)

    def _extract_epic_fields(self, response: str, template: str) -> ParsedEpicTemplate:
        """Extract EPIC fields from LLM response."""
        try:
            # Extract JSON from response
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                json_match = re.search(r'\{[\s\S]*\}', response)
                json_str = json_match.group(0) if json_match else "{}"

            data = json.loads(json_str)

            fields = []
            for f in data.get("fields", []):
                fields.append(EpicFieldConfig(
                    field_name=f.get("field_name", "unknown"),
                    enabled=f.get("enabled", True),
                    target_words=f.get("target_words", 100),
                    guidelines=f.get("guidelines"),
                ))

            return ParsedEpicTemplate(
                template_name=data.get("template_name", "Custom EPIC Template"),
                purpose=data.get("purpose", ""),
                writing_guidelines=data.get("writing_guidelines", []),
                fields=fields if fields else DEFAULT_EPIC_FIELDS.copy(),
                raw_template=template,
            )

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to extract EPIC fields: {e}")
            return self._parse_epic_template_fallback(template)

    def _extract_backlog_fields(self, response: str, template: str) -> ParsedBacklogTemplate:
        """Extract Backlog fields from LLM response."""
        try:
            # Extract JSON from response
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                json_match = re.search(r'\{[\s\S]*\}', response)
                json_str = json_match.group(0) if json_match else "{}"

            data = json.loads(json_str)

            fields = []
            for f in data.get("fields", []):
                fields.append(BacklogFieldConfig(
                    field_name=f.get("field_name", "unknown"),
                    enabled=f.get("enabled", True),
                    target_words=f.get("target_words", 50),
                    guidelines=f.get("guidelines"),
                ))

            return ParsedBacklogTemplate(
                template_name=data.get("template_name", "Custom Backlog Template"),
                purpose=data.get("purpose", ""),
                writing_guidelines=data.get("writing_guidelines", []),
                fields=fields if fields else DEFAULT_BACKLOG_FIELDS.copy(),
                item_types=data.get("item_types", ["user_story", "task", "spike"]),
                raw_template=template,
            )

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to extract Backlog fields: {e}")
            return self._parse_backlog_template_fallback(template)

    def _parse_epic_template_fallback(self, template: str) -> ParsedEpicTemplate:
        """Fallback regex-based parsing for EPIC templates.

        This method dynamically extracts ALL section headers from the template
        and creates field configurations for each one.
        """
        fields = []
        guidelines = []
        seen_fields = set()

        # Map common names to standardized field names and default word counts
        field_map = {
            "title": ("title", 20),
            "description": ("description", 150),
            "overview": ("overview", 150),
            "summary": ("summary", 100),
            "business value": ("business_value", 100),
            "value": ("business_value", 100),
            "objectives": ("objectives", 50),
            "goals": ("goals", 50),
            "acceptance criteria": ("acceptance_criteria", 30),
            "criteria": ("acceptance_criteria", 30),
            "technical": ("technical_notes", 80),
            "technical notes": ("technical_notes", 80),
            "notes": ("notes", 80),
            "components": ("components", 40),
            "technical components": ("technical_components", 40),
            "dependencies": ("dependencies", 50),
            "priority": ("priority", 20),
            "effort": ("effort", 20),
            "success metrics": ("success_metrics", 80),
            "metrics": ("metrics", 80),
            "user stories": ("user_stories", 100),
            "stories": ("stories", 100),
            "requirements": ("requirements", 100),
            "scope": ("scope", 100),
            "risks": ("risks", 80),
            "assumptions": ("assumptions", 80),
            "constraints": ("constraints", 80),
        }

        # Look for markdown section headers (## and ### only, skip # which is usually the title)
        section_pattern = r'^(#{2,3})\s+(.+?)(?:\s*\{words?:\s*(\d+)\})?\s*$'
        for line in template.split('\n'):
            match = re.match(section_pattern, line.strip())
            if match:
                header_level = len(match.group(1))  # 2 for ##, 3 for ###
                original_name = match.group(2).strip()
                name_lower = original_name.lower()
                words = int(match.group(3)) if match.group(3) else None

                # Skip generic section names
                if name_lower in ["epic template", "template", "epic", "backlog item template"]:
                    continue

                # Check if this matches a known field pattern
                matched = False
                for key, (field_name, default_words) in field_map.items():
                    if key in name_lower:
                        if field_name not in seen_fields:
                            fields.append(EpicFieldConfig(
                                field_name=field_name,
                                enabled=True,
                                target_words=words or default_words,
                            ))
                            seen_fields.add(field_name)
                        matched = True
                        break

                # If no match, create a field using the original section name
                if not matched:
                    # Convert to snake_case field name
                    field_name = re.sub(r'[^\w\s]', '', name_lower)
                    field_name = re.sub(r'\s+', '_', field_name.strip())

                    if field_name and field_name not in seen_fields:
                        # Estimate words based on section content or use default
                        default_words = 100 if len(original_name) > 10 else 50
                        fields.append(EpicFieldConfig(
                            field_name=field_name,
                            enabled=True,
                            target_words=words or default_words,
                        ))
                        seen_fields.add(field_name)

        # Extract guidelines from template comments or intro sections
        guideline_pattern = r'[-*]\s*(.+)'
        for match in re.finditer(guideline_pattern, template[:1000]):
            text = match.group(1).strip()
            if len(text) > 10 and len(text) < 200:
                guidelines.append(text)

        return ParsedEpicTemplate(
            template_name="Custom EPIC Template",
            purpose="User-provided EPIC template",
            writing_guidelines=guidelines[:5],
            fields=fields if fields else DEFAULT_EPIC_FIELDS.copy(),
            raw_template=template,
        )

    def _parse_backlog_template_fallback(self, template: str) -> ParsedBacklogTemplate:
        """Fallback regex-based parsing for Backlog templates.

        This method dynamically extracts ALL section headers from the template
        and creates field configurations for each one.
        """
        fields = []
        guidelines = []
        item_types = ["user_story"]
        seen_fields = set()

        # Map common names to standardized field names and default word counts
        field_map = {
            "title": ("title", 20),
            "description": ("description", 80),
            "story": ("description", 80),
            "overview": ("overview", 80),
            "acceptance criteria": ("acceptance_criteria", 30),
            "criteria": ("acceptance_criteria", 30),
            "technical": ("technical_notes", 50),
            "technical notes": ("technical_notes", 50),
            "notes": ("notes", 50),
            "files": ("files_to_modify", 20),
            "implementation": ("implementation", 80),
            "testing": ("testing", 50),
            "story points": ("story_points", 10),
            "priority": ("priority", 10),
            "dependencies": ("dependencies", 30),
        }

        # Look for markdown section headers (## and ### only, skip # which is usually the title)
        section_pattern = r'^(#{2,3})\s+(.+?)(?:\s*\{words?:\s*(\d+)\})?\s*$'
        for line in template.split('\n'):
            match = re.match(section_pattern, line.strip())
            if match:
                header_level = len(match.group(1))  # 2 for ##, 3 for ###
                original_name = match.group(2).strip()
                name_lower = original_name.lower()
                words = int(match.group(3)) if match.group(3) else None

                # Skip generic section names
                if name_lower in ["backlog item template", "backlog template", "template", "epic template"]:
                    continue

                # Check if this matches a known field pattern
                matched = False
                for key, (field_name, default_words) in field_map.items():
                    if key in name_lower:
                        if field_name not in seen_fields:
                            fields.append(BacklogFieldConfig(
                                field_name=field_name,
                                enabled=True,
                                target_words=words or default_words,
                            ))
                            seen_fields.add(field_name)
                        matched = True
                        break

                # If no match, create a field using the original section name
                if not matched:
                    # Convert to snake_case field name
                    field_name = re.sub(r'[^\w\s]', '', name_lower)
                    field_name = re.sub(r'\s+', '_', field_name.strip())

                    if field_name and field_name not in seen_fields:
                        default_words = 80 if len(original_name) > 10 else 50
                        fields.append(BacklogFieldConfig(
                            field_name=field_name,
                            enabled=True,
                            target_words=words or default_words,
                        ))
                        seen_fields.add(field_name)

        # Check for item type mentions
        template_lower = template.lower()
        if "task" in template_lower:
            item_types.append("task")
        if "spike" in template_lower:
            item_types.append("spike")
        if "bug" in template_lower:
            item_types.append("bug")

        # Check for user story format requirement
        has_user_story_format = "as a" in template_lower and "i want" in template_lower

        # Extract guidelines
        guideline_pattern = r'[-*]\s*(.+)'
        for match in re.finditer(guideline_pattern, template[:1000]):
            text = match.group(1).strip()
            if len(text) > 10 and len(text) < 200:
                guidelines.append(text)

        return ParsedBacklogTemplate(
            template_name="Custom Backlog Template",
            purpose="User-provided Backlog template",
            writing_guidelines=guidelines[:5],
            fields=fields if fields else DEFAULT_BACKLOG_FIELDS.copy(),
            item_types=list(set(item_types)),
            raw_template=template,
        )

    def _get_default_epic_template(self) -> ParsedEpicTemplate:
        """Get default EPIC template."""
        return ParsedEpicTemplate(
            template_name="Default EPIC Template",
            purpose="Standard EPIC structure with business value focus",
            writing_guidelines=[
                "Focus on business outcomes rather than implementation details",
                "Ensure each EPIC is independently valuable",
                "Keep descriptions clear and actionable",
            ],
            fields=DEFAULT_EPIC_FIELDS.copy(),
            raw_template="",
        )

    def _get_default_backlog_template(self) -> ParsedBacklogTemplate:
        """Get default Backlog template."""
        return ParsedBacklogTemplate(
            template_name="Default User Story Template",
            purpose="Comprehensive user story structure with testing and implementation guidance",
            writing_guidelines=[
                "Use 'As a... I want... So that...' format for user stories",
                "Write comprehensive descriptions (2-3 paragraphs)",
                "Include at least 5-7 specific, testable acceptance criteria",
                "Document pre-conditions and post-conditions",
                "Include testing approach with unit, integration, and manual tests",
                "Identify edge cases and error scenarios",
                "Provide implementation guidance for developers",
                "Keep stories small enough to complete in one sprint",
            ],
            fields=DEFAULT_BACKLOG_FIELDS.copy(),
            item_types=["user_story"],
            raw_template="",
        )

    async def _send_to_llm(self, prompt: str) -> str:
        """Send prompt to LLM via Copilot SDK."""
        if not self.session:
            return ""

        try:
            import asyncio

            message_options = {"prompt": prompt}

            if hasattr(self.session, 'send_and_wait'):
                event = await asyncio.wait_for(
                    self.session.send_and_wait(message_options, timeout=60),
                    timeout=60
                )
                if event:
                    return self._extract_from_event(event)

            if hasattr(self.session, 'send'):
                await self.session.send(message_options)
                return ""

        except Exception as e:
            logger.error(f"LLM error during template parsing: {e}")

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
