"""LLM synthesis using GitHub Copilot SDK."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..models.context import AggregatedContext
from ..models.output import (
    BRDDocument,
    Epic,
    UserStory,
    Requirement,
    AcceptanceCriteria,
    JiraCreationResult,
)
from ..utils.logger import get_logger, get_progress_logger
from .brd_best_practices import (
    BRD_BEST_PRACTICES,
    DEFAULT_BRD_SECTIONS,
    build_reverse_engineering_prompt,
    get_section_guidelines,
)

logger = get_logger(__name__)
progress = get_progress_logger(__name__, "LLMSynthesizer")

# Default timeout for LLM responses (5 minutes)
LLM_TIMEOUT_SECONDS = 300


@dataclass
class TemplateConfig:
    """
    Configuration for BRD output templates.

    Allows users to customize output format to match organizational standards.
    """
    # Template content (loaded from file or provided directly)
    brd_template: str = ""
    epic_template: str = ""
    story_template: str = ""

    # Custom sections to include
    custom_sections: list[str] = field(default_factory=list)

    # Organization-specific fields
    organization_name: str = ""
    document_prefix: str = "BRD"
    require_approvals: bool = True
    approval_roles: list[str] = field(default_factory=lambda: ["Product Owner", "Tech Lead"])

    # Output format preferences
    include_code_references: bool = True
    include_file_paths: bool = True
    include_cypher_queries: bool = False  # Include Neo4j queries used
    max_requirements_per_section: int = 10

    # Risk assessment
    include_risk_matrix: bool = True
    risk_levels: list[str] = field(default_factory=lambda: ["High", "Medium", "Low"])


class LLMSynthesizer:
    """
    Synthesizes BRD/Epics/Backlogs using GitHub Copilot SDK.

    Combines:
    - Skill-based approach: LLM uses MCP tools (Neo4j, Filesystem) autonomously
    - Template-controlled output: User-defined templates for organizational standards

    Uses the Copilot SDK session with the correct MessageOptions API.
    Falls back to mock responses if Copilot is unavailable.
    """

    def __init__(
        self,
        session: Any = None,
        templates_dir: Optional[Path] = None,
        model: str = "gpt-4o",  # Default to GPT-4o (works on all Copilot tiers)
        template_config: Optional[TemplateConfig] = None,
    ):
        """
        Initialize the LLM Synthesizer.

        Args:
            session: Copilot SDK session
            templates_dir: Directory containing template files
            model: LLM model to use
            template_config: Configuration for output templates

        Note: MCP tools are available via the Copilot SDK session's mcp_servers config.
        """
        self.session = session
        self.templates_dir = templates_dir or self._get_templates_dir()
        self.model = model
        self.template_config = template_config or TemplateConfig()
        self._copilot_available = session is not None

        # Load templates
        self._load_templates()

        if self._copilot_available:
            logger.info(f"LLM Synthesizer initialized with Copilot SDK session (model: {model})")
        else:
            logger.warning("LLM Synthesizer initialized without Copilot - mock mode active")

    def _get_templates_dir(self) -> Path:
        """Get templates directory from env or default."""
        env_dir = os.getenv("BRD_TEMPLATES_DIR")
        if env_dir:
            return Path(env_dir)
        return Path(__file__).parent.parent / "templates"

    def _load_templates(self) -> None:
        """Load templates from files if not provided in config."""
        if not self.template_config.brd_template:
            self.template_config.brd_template = self._load_template("brd-template.md")
        if not self.template_config.epic_template:
            self.template_config.epic_template = self._load_template("epic-template.md")
        if not self.template_config.story_template:
            self.template_config.story_template = self._load_template("backlog-template.md")

    async def generate_brd_with_skill(
        self,
        feature_request: str,
        affected_components: Optional[list[str]] = None,
    ) -> BRDDocument:
        """
        Generate BRD using skills - SDK handles everything.

        SKILLS-ONLY ARCHITECTURE:
        1. Send a simple prompt that triggers the generate-brd skill
        2. The skill (loaded by SDK from skill_directories) instructs the LLM to:
           - Get Neo4j schema
           - Search for relevant components
           - Read source files
           - Generate comprehensive BRD
        3. The SDK automatically routes MCP tool calls to configured servers
        4. LLM returns the complete BRD with real codebase context

        No manual context aggregation - the skill handles everything in one session.

        Args:
            feature_request: The feature to generate BRD for
            affected_components: Optional list of known affected components

        Returns:
            BRDDocument generated by the LLM with real codebase context
        """
        progress.start_operation("LLM.generate_brd_with_skill", "Skills-only BRD generation")

        if not self._copilot_available:
            logger.warning("[SKILL-BRD] Copilot SDK not available, using mock")
            progress.warning("Copilot SDK not available, returning mock BRD")
            return self._create_mock_brd(feature_request)

        # Build a simple prompt that triggers the generate-brd skill
        # The skill file (.github/skills/generate-brd.md) has full instructions
        components_hint = ""
        if affected_components:
            components_hint = f"\n\nKnown affected components: {', '.join(affected_components)}"

        # Simple trigger prompt - skill provides the detailed instructions
        prompt = f"""Generate BRD for: {feature_request}{components_hint}"""

        logger.info(f"[SKILL-BRD] Triggering generate-brd skill with prompt ({len(prompt)} chars)")
        logger.info(f"[SKILL-BRD] Prompt: {prompt}")

        progress.step("generate_brd", "Triggering skill - SDK handles MCP tools")

        # Send prompt - SDK will:
        # 1. Match to generate-brd skill
        # 2. Inject skill instructions
        # 3. LLM uses MCP tools to gather context
        # 4. LLM generates BRD
        response = await self._send_with_event_logging(prompt)

        # Parse response into BRDDocument
        progress.step("generate_brd", "Parsing BRD from response")
        brd = self._parse_brd_response(response, feature_request)

        progress.end_operation("LLM.generate_brd_with_skill", success=True, details=f"Generated: {brd.title}")
        return brd

    async def generate_brd_direct(
        self,
        feature_request: str,
        affected_components: Optional[list[str]] = None,
    ) -> BRDDocument:
        """Alias for generate_brd_with_skill for backward compatibility."""
        return await self.generate_brd_with_skill(feature_request, affected_components)

    async def generate_brd_with_context(
        self,
        context: "AggregatedContext",
        feature_request: str,
        detail_level: str = "standard",
        custom_sections: Optional[list[dict]] = None,
        default_section_words: int = 300,
    ) -> BRDDocument:
        """
        Generate BRD using pre-gathered context (CONTEXT-FIRST approach).

        This approach:
        1. Receives context already gathered by the aggregator
        2. Passes context explicitly to LLM
        3. LLM generates BRD based on provided context

        More reliable than skills-only because:
        - Context is explicitly included in prompt
        - No dependency on skill matching
        - Context gathering is visible in logs

        Args:
            context: Pre-gathered context from aggregator
            feature_request: The feature to generate BRD for
            detail_level: 'concise', 'standard', or 'detailed'
            custom_sections: Optional list of custom section definitions
            default_section_words: Default target word count per section (100-2000)

        Returns:
            BRDDocument generated with explicit context
        """
        progress.start_operation("LLM.generate_brd_with_context", "Context-first BRD generation")

        if not self._copilot_available:
            logger.warning("[CONTEXT-BRD] Copilot SDK not available, using mock")
            return self._create_mock_brd(feature_request)

        # Build context summary
        components_text = ""
        if context.architecture.components:
            comp_list = [f"- {c.name} ({c.type}): {c.path}" for c in context.architecture.components[:20]]
            components_text = "### Components Found\n" + "\n".join(comp_list)

        files_text = ""
        if context.implementation.key_files:
            file_list = [f"- {f.path}: {f.relevance}" for f in context.implementation.key_files[:15]]
            files_text = "### Key Source Files\n" + "\n".join(file_list)

        similar_text = ""
        if context.similar_features:
            similar_text = "### Similar Features\n" + ", ".join(context.similar_features[:10])

        schema_text = ""
        if context.schema:
            labels = ", ".join(context.schema.component_labels[:10]) if context.schema.component_labels else "N/A"
            rels = ", ".join(context.schema.dependency_relationships[:10]) if context.schema.dependency_relationships else "N/A"
            schema_text = f"### Codebase Schema\nComponent types: {labels}\nRelationships: {rels}"

        # Detail level instructions
        detail_instructions = self._get_detail_level_instructions(detail_level)

        # Build sections template with target word counts
        sections_template = self._build_sections_template(custom_sections, context, default_section_words)

        # Build prompt with explicit context - REVERSE ENGINEERING existing code
        prompt = f"""You are an expert Business Analyst reverse engineering an EXISTING feature to create a BRD.

{BRD_BEST_PRACTICES}

## CRITICAL: REVERSE ENGINEERING MODE

The feature "{feature_request}" ALREADY EXISTS in this codebase. Your task is to:
1. Analyze the existing implementation from the provided context
2. Document what the code ACTUALLY DOES in BUSINESS terms (not technical)
3. Extract the business logic and requirements that were ALREADY IMPLEMENTED
4. Create a BRD that describes the CURRENT IMPLEMENTATION for business stakeholders

## Existing Feature to Document
{feature_request}

## Codebase Analysis (Components & Files that ALREADY IMPLEMENT this feature)

{schema_text}

{components_text}

{files_text}

{similar_text}

{detail_instructions}

## Writing Instructions

- Use plain English - translate code behavior to business language
- Be deterministic - avoid "may" or "might", describe exact behavior
- Write for business readers - assume non-technical audience
- Explain "what" not "how" - describe outcomes, not implementation
- Use numbered lists for process flows
- Include actual business rules extracted from code

OUTPUT THE FULL BRD DOCUMENT IN MARKDOWN FORMAT.

{sections_template}

CRITICAL: Document what EXISTS, not what should be built. Reference actual components: {', '.join([c.name for c in context.architecture.components[:15]])}"""

        logger.info(f"[CONTEXT-BRD] Sending prompt with context ({len(prompt)} chars)")
        logger.info(f"[CONTEXT-BRD] Context: {len(context.architecture.components)} components, {len(context.implementation.key_files)} files")

        progress.step("generate_brd", "Sending context + prompt to LLM")

        response = await self._send_to_llm(prompt)

        progress.step("generate_brd", "Parsing BRD from response")
        brd = self._parse_brd_response(response, feature_request)

        progress.end_operation("LLM.generate_brd_with_context", success=True, details=f"Generated: {brd.title}")
        return brd

    async def generate_brd(
        self,
        context: AggregatedContext,
        use_skill: bool = True,
    ) -> BRDDocument:
        """
        Generate BRD from context (legacy method - kept for compatibility).

        For the simplified flow, use generate_brd_direct() instead.

        Args:
            context: Aggregated context from MCP servers
            use_skill: If True, use simple prompt to trigger automatic skill selection.
                      If False, use template-based approach with detailed prompts.
        """
        # If using skill-based approach, delegate to simplified method
        if use_skill and self._copilot_available:
            return await self.generate_brd_direct(context.request)

        # Template-based approach (fallback)
        approach = "template-based"
        progress.start_operation("LLM.generate_brd", f"Using {approach} approach")

        progress.step("generate_brd", "Building template-based prompt")
        response = await self._generate_brd_with_template(context)

        # Parse response into BRDDocument
        progress.step("generate_brd", "Parsing LLM response into BRD document")
        brd = self._parse_brd_response(response, context.request)

        progress.end_operation("LLM.generate_brd", success=True, details=f"Generated: {brd.title}")
        return brd

    async def _generate_brd_with_skill(self, context: AggregatedContext) -> str:
        """
        Generate BRD using automatic skill selection WITH template-controlled output.

        Combines:
        - Skill-based: LLM uses MCP tools (Neo4j, Filesystem) to gather context
        - Template-controlled: Output follows user-defined template format

        The prompt:
        1. Triggers skill matching for MCP tool usage
        2. Includes template for output format control
        3. Includes organizational preferences
        """
        # Build template instructions
        template_instructions = self._build_template_instructions()

        # Build prompt that combines skill triggering + template control
        prompt = f"""Generate a BRD for the following feature:

{context.request}

## Instructions

1. **Analyze the codebase** using the available MCP tools:
   - Use Neo4j code graph to find affected components, classes, and dependencies
   - Use filesystem tools to read relevant source files and understand patterns

2. **Generate the BRD** following the EXACT template format below.

{template_instructions}

## Important Guidelines

- Use the MCP tools to gather REAL context from the codebase before writing
- Reference actual component names, file paths, and code patterns discovered
- Follow the template structure EXACTLY for organizational compliance
- Include specific file paths that need modification
- Be concrete and actionable in requirements
"""

        progress.info("Sending skill-based prompt to LLM with template control")
        return await self._send_to_llm(prompt)

    def _get_detail_level_instructions(self, detail_level: str) -> str:
        """Get writing instructions based on detail level."""
        instructions = {
            "concise": """
## OUTPUT DETAIL LEVEL: CONCISE
- Keep each section brief: 1-2 short paragraphs maximum
- Use bullet points instead of prose where possible
- Focus only on key points, skip minor details
- No lengthy explanations - be direct and succinct
- Target total length: ~2-3 pages
""",
            "standard": """
## OUTPUT DETAIL LEVEL: STANDARD
- Provide balanced coverage: 2-4 paragraphs per major section
- Include both overview and relevant details
- Use a mix of prose and bullet points
- Include examples where helpful
- Target total length: ~5-8 pages
""",
            "detailed": """
## OUTPUT DETAIL LEVEL: DETAILED
- Provide comprehensive coverage with full explanations
- Include extensive code references and file paths
- Document all acceptance criteria thoroughly
- Include technical implementation details
- Add examples, edge cases, and considerations
- Target total length: ~10-15+ pages
""",
        }
        return instructions.get(detail_level, instructions["standard"])

    def _build_sections_template(
        self,
        custom_sections: Optional[list[dict]],
        context: "AggregatedContext",
        default_section_words: int = 300,
    ) -> str:
        """Build sections template for BRD output.

        Args:
            custom_sections: User-defined sections with name, description, and target_words
            context: Aggregated context for component references
            default_section_words: Default target word count per section (used if not specified per-section)

        Returns:
            Formatted sections template for the prompt
        """
        # Use custom sections if provided, otherwise use defaults from best practices
        sections_to_use = custom_sections if custom_sections else DEFAULT_BRD_SECTIONS

        sections_text = "# Business Requirements Document (Reverse Engineered)\n\n"

        for i, section in enumerate(sections_to_use, 1):
            name = section.get("name", f"Section {i}")
            description = section.get("description", "")
            required = section.get("required", True)
            # Get target words: use section-specific if provided, otherwise use default
            target_words = section.get("target_words", default_section_words)

            sections_text += f"## {i}. {name}\n"

            # Add target length instruction
            sections_text += f"**Target Length:** Approximately {target_words} words for this section.\n\n"

            if description:
                # Use the description as guidance
                sections_text += f"**Guidelines:** {description}\n\n"
            else:
                # Get default guidelines from best practices
                default_desc = get_section_guidelines(name)
                sections_text += f"**Guidelines:** {default_desc}\n\n"

            if not required:
                sections_text += "_Optional section - include only if relevant to the feature_\n\n"

            # Inject auto-generated content for Section 7 (Technical Architecture), Section 8 (Data Model),
            # and Section 9 (Implementation Mapping)
            # These are generated from actual code graph traversal via FeatureFlowService
            auto_generated_content = None
            section_instructions = ""

            name_lower = name.lower()
            if "technical architecture" in name_lower and context.technical_architecture:
                auto_generated_content = context.technical_architecture
                section_instructions = """
**LLM Instructions for Technical Architecture:**
1. PRESERVE all auto-generated file paths, line numbers, and component references
2. The layered structure (UI → Controller → Service → DAO → Database) is accurate from code traversal
3. You may ADD additional context such as:
   - Business purpose of each component
   - Dependencies between layers
   - Error handling paths
4. DO NOT modify the auto-generated file paths or line numbers - they are from actual code
"""
                logger.info(f"[SYNTHESIZER] Injecting auto-generated Technical Architecture for Section {i}")

            elif "implementation mapping" in name_lower and context.implementation_mapping:
                auto_generated_content = context.implementation_mapping
                section_instructions = """
**LLM Instructions for Implementation Mapping:**
1. PRESERVE all auto-generated table rows with file paths and line numbers
2. The Operation-to-Implementation table shows actual code locations
3. You may ADD additional operations discovered from code analysis
4. You may ADD explanatory text about how to read the mapping
5. DO NOT modify existing file:line references - they are from actual code traversal
"""
                logger.info(f"[SYNTHESIZER] Injecting auto-generated Implementation Mapping for Section {i}")

            elif "data model" in name_lower:
                # Try to extract data model from feature flows if available
                if context.feature_flows:
                    data_model_content = self._extract_data_model_from_flows(context)
                    if data_model_content:
                        auto_generated_content = data_model_content
                        section_instructions = """
**LLM Instructions for Data Model:**
1. The table and column information was extracted from actual SQL operations in the code
2. You may ADD entity class information if visible in the context
3. You may ADD relationship descriptions based on code analysis
4. You may ADD validation annotations observed in entity classes
"""
                        logger.info(f"[SYNTHESIZER] Injecting extracted Data Model for Section {i}")

            if auto_generated_content:
                sections_text += f"""
---
**AUTO-GENERATED CONTENT** *(from code graph traversal - DO NOT MODIFY file paths/line numbers)*

{auto_generated_content}

{section_instructions}
---

"""
            else:
                sections_text += "[Document this section based on code analysis]\n\n"

        return sections_text

    def _extract_data_model_from_flows(self, context: "AggregatedContext") -> str:
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

        # Collect all tables and operations from feature flows
        tables: dict[str, dict] = {}  # table_name -> {columns, operations, source}

        for flow_dict in context.feature_flows:
            # Handle both dict and object representations
            sql_ops = flow_dict.get("sql_operations", []) if isinstance(flow_dict, dict) else getattr(flow_dict, "sql_operations", [])

            for op in sql_ops:
                if isinstance(op, dict):
                    table_name = op.get("table_name", "unknown")
                    columns = op.get("columns", [])
                    statement_type = op.get("statement_type", "UNKNOWN")
                    source_class = op.get("source_class", "")
                    source_method = op.get("source_method", "")
                else:
                    table_name = getattr(op, "table_name", "unknown")
                    columns = getattr(op, "columns", [])
                    statement_type = getattr(op, "statement_type", "UNKNOWN")
                    source_class = getattr(op, "source_class", "")
                    source_method = getattr(op, "source_method", "")

                if table_name not in tables:
                    tables[table_name] = {
                        "columns": set(),
                        "operations": set(),
                        "sources": [],
                    }

                tables[table_name]["columns"].update(columns if columns else [])
                tables[table_name]["operations"].add(statement_type)
                if source_class and source_method:
                    tables[table_name]["sources"].append(f"{source_class}.{source_method}()")

        if tables:
            # Generate table for each database table
            for table_name, info in tables.items():
                sections.append(f"#### Table: `{table_name}`\n")
                sections.append(f"**Operations:** {', '.join(sorted(info['operations']))}\n")

                if info["columns"]:
                    sections.append("| Column | Inferred Type | Constraints |")
                    sections.append("|--------|---------------|-------------|")
                    for col in sorted(info["columns"]):
                        # Basic type inference from column naming conventions
                        inferred_type = self._infer_column_type(col)
                        constraints = self._infer_constraints(col)
                        sections.append(f"| `{col}` | {inferred_type} | {constraints} |")
                    sections.append("")

                if info["sources"]:
                    sources = list(set(info["sources"]))[:3]  # Limit to 3 sources
                    sections.append(f"**Accessed by:** {', '.join(f'`{s}`' for s in sources)}\n")
        else:
            sections.append("*No database tables extracted from code analysis*\n")

        # Add data mappings section if available
        data_mappings_found = False
        for flow_dict in context.feature_flows:
            mappings = flow_dict.get("data_mappings", []) if isinstance(flow_dict, dict) else getattr(flow_dict, "data_mappings", [])
            if mappings:
                data_mappings_found = True
                break

        if data_mappings_found:
            sections.append("### Entity Field Mappings\n")
            sections.append("*Maps entity fields to database columns*\n")
            sections.append("| Entity Field | DB Column | Required | Validations |")
            sections.append("|--------------|-----------|----------|-------------|")

            for flow_dict in context.feature_flows:
                mappings = flow_dict.get("data_mappings", []) if isinstance(flow_dict, dict) else getattr(flow_dict, "data_mappings", [])
                for dm in mappings[:10]:  # Limit to 10 mappings
                    if isinstance(dm, dict):
                        entity_field = dm.get("entity_field", "-")
                        db_column = dm.get("db_column", "-")
                        is_required = "Yes" if dm.get("is_required") else "No"
                        validations = ", ".join(dm.get("validation_rules", [])[:2]) or "-"
                    else:
                        entity_field = getattr(dm, "entity_field", "-")
                        db_column = getattr(dm, "db_column", "-")
                        is_required = "Yes" if getattr(dm, "is_required", False) else "No"
                        validation_rules = getattr(dm, "validation_rules", [])
                        validations = ", ".join(validation_rules[:2]) if validation_rules else "-"

                    sections.append(f"| `{entity_field}` | `{db_column}` | {is_required} | {validations} |")
            sections.append("")

        return "\n".join(sections)

    def _infer_column_type(self, column_name: str) -> str:
        """Infer column type from naming conventions."""
        col_lower = column_name.lower()

        if col_lower.endswith("_id") or col_lower == "id":
            return "NUMBER/BIGINT"
        elif col_lower.endswith("_date") or col_lower.endswith("_time") or col_lower.endswith("_at"):
            return "TIMESTAMP"
        elif col_lower.startswith("is_") or col_lower.startswith("has_") or col_lower.endswith("_flag"):
            return "BOOLEAN/CHAR(1)"
        elif col_lower.endswith("_amount") or col_lower.endswith("_price") or col_lower.endswith("_total"):
            return "DECIMAL"
        elif col_lower.endswith("_count") or col_lower.endswith("_number") or col_lower.endswith("_qty"):
            return "INTEGER"
        elif col_lower.endswith("_code") or col_lower.endswith("_status"):
            return "VARCHAR(50)"
        elif col_lower.endswith("_name") or col_lower.endswith("_title"):
            return "VARCHAR(255)"
        elif col_lower.endswith("_description") or col_lower.endswith("_text") or col_lower.endswith("_notes"):
            return "TEXT/CLOB"
        else:
            return "VARCHAR"

    def _infer_constraints(self, column_name: str) -> str:
        """Infer constraints from column naming conventions."""
        col_lower = column_name.lower()
        constraints = []

        if col_lower == "id" or col_lower.endswith("_id") and not col_lower.startswith("fk_"):
            if col_lower == "id" or col_lower == column_name.split("_")[0] + "_id":
                constraints.append("PK")

        if col_lower.startswith("fk_") or (col_lower.endswith("_id") and col_lower != "id"):
            constraints.append("FK")

        if col_lower in ("created_date", "created_at", "created_by", "updated_date", "updated_at", "updated_by"):
            constraints.append("AUDIT")

        return ", ".join(constraints) if constraints else "-"

    def _build_template_instructions(self) -> str:
        """Build template instructions for LLM output format control."""
        config = self.template_config

        # Start with the base template
        instructions = f"""## Output Template (MUST FOLLOW THIS FORMAT)

{config.brd_template if config.brd_template else self._get_default_brd_template()}
"""

        # Add organizational customizations
        if config.organization_name:
            instructions += f"""
## Organization: {config.organization_name}
- Document prefix: {config.document_prefix}
"""

        # Add section preferences
        if config.custom_sections:
            instructions += f"""
## Additional Sections Required:
{chr(10).join(f'- {section}' for section in config.custom_sections)}
"""

        # Add approval requirements
        if config.require_approvals and config.approval_roles:
            instructions += f"""
## Approval Section Required:
Include approval lines for: {', '.join(config.approval_roles)}
"""

        # Add output preferences
        instructions += f"""
## Output Preferences:
- Include code/file references: {config.include_code_references}
- Include file paths to modify: {config.include_file_paths}
- Include risk matrix: {config.include_risk_matrix}
- Max requirements per section: {config.max_requirements_per_section}
"""

        if config.include_risk_matrix:
            instructions += f"""
## Risk Matrix Format:
| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
Use risk levels: {', '.join(config.risk_levels)}
"""

        return instructions

    def _get_default_brd_template(self) -> str:
        """Return default BRD template if none loaded."""
        return """
# Business Requirements Document: {TITLE}

**Version:** 1.0
**Date:** {DATE}
**Status:** Draft

---

## 1. Executive Summary
{BUSINESS_CONTEXT}

## 2. Business Objectives
{OBJECTIVES}

## 3. Scope

### 3.1 In Scope (Functional Requirements)
{FUNCTIONAL_REQUIREMENTS}

### 3.2 Out of Scope
{OUT_OF_SCOPE}

## 4. Technical Requirements
{TECHNICAL_REQUIREMENTS}

### 4.1 Affected Components
{AFFECTED_COMPONENTS}

### 4.2 Files to Modify
{SOURCE_FILES}

## 5. Dependencies
{DEPENDENCIES}

## 6. Risk Assessment
{RISKS}

## 7. Acceptance Criteria
{ACCEPTANCE_CRITERIA}

---

## Approval
| Role | Name | Signature | Date |
|------|------|-----------|------|
| Product Owner | | | |
| Tech Lead | | | |
"""

    async def _generate_brd_with_template(self, context: AggregatedContext) -> str:
        """
        Generate BRD using template-based approach with detailed prompts.

        This approach:
        1. Pre-gathers context using aggregator
        2. Loads templates
        3. Builds detailed prompts
        4. Sends to LLM with all context embedded
        """
        # Load template
        template = self._load_template("brd-template.md")
        analysis_prompt = self._load_prompt("analysis-prompt.txt")

        # Stage 1: Analysis
        analysis = await self._analyze_context(context, analysis_prompt)

        # Stage 2: BRD Generation
        brd_prompt = self._build_brd_prompt(context, analysis, template)

        progress.info("Sending template-based prompt to LLM")
        return await self._send_to_llm(brd_prompt)

    async def generate_epics_from_brd(
        self,
        brd: BRDDocument,
        use_skill: bool = True,
    ) -> list[Epic]:
        """
        PHASE 2: Generate Epics from an approved BRD.

        This generates Epics only (no stories). Stories are generated
        separately in Phase 3 after user approves the Epics.

        Args:
            brd: The approved BRD document
            use_skill: If True, use skill-based approach

        Returns:
            List of Epics
        """
        progress.start_operation("LLM.generate_epics", f"From BRD: {brd.title[:40]}...")

        if use_skill and self._copilot_available:
            progress.step("generate_epics", "Building epics prompt from BRD")
            prompt = self._build_epics_only_prompt(brd)
            progress.step("generate_epics", "Sending to LLM")
            response = await self._send_to_llm(prompt)
            progress.step("generate_epics", "Parsing epic response")
            epics = self._parse_epics_only_response(response)
        else:
            progress.step("generate_epics", "Generating basic epics (fallback mode)")
            epics = self._generate_basic_epics(brd)

        progress.end_operation("LLM.generate_epics", success=True, details=f"{len(epics)} epics generated")
        return epics

    def _build_epics_only_prompt(self, brd: BRDDocument) -> str:
        """Build prompt for generating Epics only (no stories)."""
        func_reqs = "\n".join(
            f"- {req.id}: {req.title}" for req in brd.functional_requirements[:10]
        )
        tech_reqs = "\n".join(
            f"- {req.id}: {req.title}" for req in brd.technical_requirements[:10]
        )

        return f"""Generate Epics from the following approved BRD.

## Approved BRD: {brd.title}

### Business Context
{brd.business_context}

### Functional Requirements
{func_reqs}

### Technical Requirements
{tech_reqs}

### Dependencies
{chr(10).join(f'- {dep}' for dep in brd.dependencies)}

---

## Instructions

1. **Analyze the codebase** using MCP tools to understand component relationships
2. **Group requirements into Epics** (2-4 Epics, each deliverable in 2-4 weeks)
3. **Define Epic dependencies** based on code analysis
4. **Do NOT generate User Stories** - those will be generated in the next phase

## Output Format

For each Epic:
```
EPIC-XXX: [Title]
Description: [Brief description - 2-3 sentences]
Components: [component1, component2]
Priority: [High/Medium/Low]
Effort: [Small/Medium/Large]
Blocked By: [EPIC-XXX or None]
Requirements: [FR-001, FR-002, TR-001]
```

Generate 2-4 Epics that cover all requirements from the BRD.
"""

    def _parse_epics_only_response(self, response: str) -> list[Epic]:
        """Parse response into Epics (no stories)."""
        epics = []
        epic_pattern = r"EPIC-(\d+):\s*(.+?)(?=EPIC-\d+:|$)"
        matches = re.findall(epic_pattern, response, re.DOTALL)

        for match in matches:
            epic_id = f"EPIC-{match[0]}"
            content = match[1].strip()

            title = content.split("\n")[0].strip()

            desc_match = re.search(r"Description:\s*(.+?)(?=Components:|Priority:|Effort:|Blocked By:|Requirements:|$)", content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else title

            comp_match = re.search(r"Components:\s*\[?([^\]]+)\]?", content)
            components = []
            if comp_match:
                components = [c.strip() for c in comp_match.group(1).split(",")]

            priority_match = re.search(r"Priority:\s*(High|Medium|Low)", content, re.IGNORECASE)
            priority = priority_match.group(1).lower() if priority_match else "medium"

            effort_match = re.search(r"Effort:\s*(Small|Medium|Large)", content, re.IGNORECASE)
            effort = effort_match.group(1).lower() if effort_match else "medium"

            blocked_match = re.search(r"Blocked By:\s*(.+?)(?=Requirements:|$)", content)
            blocked_by = []
            if blocked_match:
                blocked_str = blocked_match.group(1).strip()
                if blocked_str.lower() != "none":
                    blocked_by = re.findall(r"EPIC-\d+", blocked_str)

            epics.append(Epic(
                id=epic_id,
                title=title,
                description=description,
                components=components,
                estimated_effort=effort,
                priority=priority,
                blocked_by=blocked_by,
            ))

        if not epics:
            epics = self._generate_basic_epics_from_title(response)

        return epics

    def _generate_basic_epics_from_title(self, response: str) -> list[Epic]:
        """Fallback: generate basic epics from response text."""
        return [Epic(
            id="EPIC-001",
            title="Core Implementation",
            description="Implement the core functionality as per BRD requirements",
            components=[],
            estimated_effort="medium",
            priority="high",
        )]

    async def generate_backlogs_from_epics(
        self,
        epics: list[Epic],
        use_skill: bool = True,
    ) -> list[UserStory]:
        """
        PHASE 3: Generate User Stories (Backlogs) from approved Epics.

        Args:
            epics: List of approved Epics
            use_skill: If True, use skill-based approach

        Returns:
            List of User Stories
        """
        progress.start_operation("LLM.generate_backlogs", f"From {len(epics)} Epics")

        all_stories = []
        for i, epic in enumerate(epics, 1):
            progress.step("generate_backlogs", f"Generating stories for Epic {i}/{len(epics)}: {epic.id}", current=i, total=len(epics))

            if use_skill and self._copilot_available:
                prompt = self._build_backlogs_prompt(epic)
                progress.info(f"Sending prompt for {epic.id} to LLM")
                response = await self._send_to_llm(prompt)
                stories = self._parse_stories_response(response, epic.id)
            else:
                stories = self._generate_basic_stories_for_epic(epic)

            progress.info(f"Generated {len(stories)} stories for {epic.id}")
            all_stories.extend(stories)
            epic.stories = [s.id for s in stories]

        progress.end_operation("LLM.generate_backlogs", success=True, details=f"{len(all_stories)} stories generated")
        return all_stories

    def _build_backlogs_prompt(self, epic: Epic) -> str:
        """Build prompt for generating Stories from an Epic."""
        return f"""Generate User Stories for the following approved Epic.

## Epic: {epic.id} - {epic.title}

### Description
{epic.description}

### Components Affected
{chr(10).join(f'- {c}' for c in epic.components) or '- To be determined from code analysis'}

### Priority
{epic.priority}

---

## Instructions

1. **Analyze the codebase** using MCP tools to understand:
   - Classes and methods in affected components
   - Existing patterns to follow
   - Test coverage requirements

2. **Create 3-5 User Stories** that:
   - Are completable in 1-3 days each
   - Have clear acceptance criteria
   - Include specific files to modify
   - Define dependencies between stories

## Output Format

For each Story:
```
STORY-XXX: [Title]
Epic: {epic.id}
As a [role], I want [capability], so that [benefit].
Description: [Detailed description]
Acceptance Criteria:
- [Criterion 1]
- [Criterion 2]
Files to Modify:
- path/to/file.py - [what to change]
Files to Create:
- path/to/new_file.py - [purpose]
Blocked By: [STORY-XXX or None]
Points: [1/2/3/5/8]
```

Generate 3-5 Stories for this Epic.
"""

    def _generate_basic_stories_for_epic(self, epic: Epic) -> list[UserStory]:
        """Fallback: generate basic stories for an epic."""
        base_num = int(epic.id.split("-")[1]) * 100
        return [
            UserStory(
                id=f"STORY-{base_num + 1:03d}",
                epic_id=epic.id,
                title=f"Implement core functionality for {epic.title}",
                description=f"Implement the main feature described in {epic.id}",
                as_a="user",
                i_want="the core functionality implemented",
                so_that="I can use the feature",
                acceptance_criteria=[AcceptanceCriteria(criterion="Feature works as expected")],
                estimated_points=5,
            ),
            UserStory(
                id=f"STORY-{base_num + 2:03d}",
                epic_id=epic.id,
                title=f"Add tests for {epic.title}",
                description=f"Add unit and integration tests for {epic.id}",
                as_a="developer",
                i_want="comprehensive test coverage",
                so_that="the feature is reliable",
                acceptance_criteria=[AcceptanceCriteria(criterion="Test coverage > 80%")],
                estimated_points=3,
                blocked_by=[f"STORY-{base_num + 1:03d}"],
            ),
        ]

    # Legacy method for backward compatibility
    async def generate_epics(
        self,
        context: AggregatedContext,
        brd: BRDDocument,
        use_skill: bool = True,
    ) -> list[Epic]:
        """Legacy: Generate epics from BRD and context."""
        return await self.generate_epics_from_brd(brd, use_skill)

    # Legacy method for backward compatibility
    async def generate_backlogs(
        self,
        context: AggregatedContext,
        epics: list[Epic],
        use_skill: bool = True,
    ) -> list[UserStory]:
        """Legacy: Generate user stories from epics."""
        return await self.generate_backlogs_from_epics(epics, use_skill)

    async def generate_epics_and_stories_from_brd(
        self,
        brd: BRDDocument,
        use_skill: bool = True,
    ) -> tuple[list[Epic], list[UserStory]]:
        """
        PHASE 2: Generate Epics and User Stories from an approved BRD.

        This uses the generate-epics-from-brd skill to create a complete
        breakdown with dependencies.

        Args:
            brd: The approved BRD document
            use_skill: If True, use skill-based approach

        Returns:
            Tuple of (epics, stories)
        """
        logger.info(f"Generating Epics and Stories from BRD: {brd.title}")

        if use_skill and self._copilot_available:
            # Use skill-based approach with template control
            prompt = self._build_epics_from_brd_prompt(brd)
            response = await self._send_to_llm(prompt)

            # Parse the response into epics and stories
            epics, stories = self._parse_epics_and_stories_response(response, brd)
        else:
            # Fallback: Simple generation
            epics = self._generate_basic_epics(brd)
            stories = self._generate_basic_stories(epics, brd)

        logger.info(f"Generated {len(epics)} Epics and {len(stories)} Stories")
        return epics, stories

    def _build_epics_from_brd_prompt(self, brd: BRDDocument) -> str:
        """Build prompt for generating Epics and Stories from BRD."""
        # Format requirements
        func_reqs = "\n".join(
            f"- {req.id}: {req.title}" for req in brd.functional_requirements[:10]
        )
        tech_reqs = "\n".join(
            f"- {req.id}: {req.title}" for req in brd.technical_requirements[:10]
        )

        return f"""Generate Epics and User Stories from the following approved BRD.

## Approved BRD: {brd.title}

### Business Context
{brd.business_context}

### Objectives
{chr(10).join(f'- {obj}' for obj in brd.objectives)}

### Functional Requirements
{func_reqs}

### Technical Requirements
{tech_reqs}

### Dependencies
{chr(10).join(f'- {dep}' for dep in brd.dependencies)}

### Risks
{chr(10).join(f'- {risk}' for risk in brd.risks)}

---

## Instructions

1. **Analyze the codebase** using MCP tools to understand component dependencies
2. **Group requirements into Epics** (2-4 Epics, each deliverable in 2-4 weeks)
3. **Break each Epic into User Stories** (3-5 stories per Epic, each 1-3 days)
4. **Define dependencies** between stories based on code analysis
5. **Estimate story points** (1, 2, 3, 5, 8 scale)

## Output Format

For each Epic:
```
EPIC-XXX: [Title]
Description: [Brief description]
Components: [component1, component2]
Priority: [High/Medium/Low]
Effort: [Small/Medium/Large]
```

For each Story within the Epic:
```
STORY-XXX: [Title]
Epic: EPIC-XXX
As a [role], I want [capability], so that [benefit].
Description: [Detailed description]
Acceptance Criteria:
- [Criterion 1]
- [Criterion 2]
Files to Modify:
- path/to/file.py
Blocked By: [STORY-XXX or None]
Points: [1-8]
```

## Guidelines
- Every BRD requirement must map to at least one story
- Stories should be small enough to complete in 1-3 days
- Include specific file paths from code analysis
- Define clear dependencies between stories
"""

    def _parse_epics_and_stories_response(
        self,
        response: str,
        brd: BRDDocument,
    ) -> tuple[list[Epic], list[UserStory]]:
        """Parse response into Epics and Stories with dependencies."""
        epics = []
        stories = []

        # Parse Epics
        epic_pattern = r"EPIC-(\d+):\s*(.+?)(?=EPIC-\d+:|STORY-\d+:|$)"
        epic_matches = re.findall(epic_pattern, response, re.DOTALL)

        for match in epic_matches:
            epic_id = f"EPIC-{match[0]}"
            content = match[1].strip()

            title = content.split("\n")[0].strip()

            desc_match = re.search(r"Description:\s*(.+?)(?=Components:|Priority:|Effort:|$)", content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else title

            comp_match = re.search(r"Components:\s*\[?([^\]]+)\]?", content)
            components = []
            if comp_match:
                components = [c.strip() for c in comp_match.group(1).split(",")]

            priority_match = re.search(r"Priority:\s*(High|Medium|Low)", content, re.IGNORECASE)
            priority = priority_match.group(1).lower() if priority_match else "medium"

            effort_match = re.search(r"Effort:\s*(Small|Medium|Large)", content, re.IGNORECASE)
            effort = effort_match.group(1).lower() if effort_match else "medium"

            epics.append(Epic(
                id=epic_id,
                title=title,
                description=description,
                components=components,
                estimated_effort=effort,
                priority=priority,
            ))

        # Parse Stories
        story_pattern = r"STORY-(\d+):\s*(.+?)(?=STORY-\d+:|$)"
        story_matches = re.findall(story_pattern, response, re.DOTALL)

        for match in story_matches:
            story_id = f"STORY-{match[0]}"
            content = match[1].strip()

            lines = content.split("\n")
            title = lines[0].strip()

            # Find Epic
            epic_match = re.search(r"Epic:\s*(EPIC-\d+)", content)
            epic_id = epic_match.group(1) if epic_match else (epics[0].id if epics else "EPIC-001")

            # Parse user story format
            as_a_match = re.search(r"As a\s+(.+?),", content)
            i_want_match = re.search(r"I want\s+(.+?),", content)
            so_that_match = re.search(r"so that\s+(.+?)(?:\.|$)", content)

            as_a = as_a_match.group(1) if as_a_match else "user"
            i_want = i_want_match.group(1) if i_want_match else "this functionality"
            so_that = so_that_match.group(1) if so_that_match else "I can achieve my goal"

            # Parse description
            desc_match = re.search(r"Description:\s*(.+?)(?=Acceptance Criteria:|Files to Modify:|Blocked By:|Points:|$)", content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else content[:200]

            # Parse acceptance criteria
            ac_section = re.search(r"Acceptance Criteria:(.+?)(?=Files to Modify:|Blocked By:|Points:|$)", content, re.DOTALL)
            acceptance_criteria = []
            if ac_section:
                for line in ac_section.group(1).split("\n"):
                    line = line.strip().lstrip("-").strip()
                    if line:
                        acceptance_criteria.append(AcceptanceCriteria(criterion=line))

            # Parse files to modify
            files_match = re.search(r"Files to Modify:(.+?)(?=Blocked By:|Points:|$)", content, re.DOTALL)
            files_to_modify = []
            if files_match:
                for line in files_match.group(1).split("\n"):
                    line = line.strip().lstrip("-").strip()
                    if line and "/" in line:
                        files_to_modify.append(line.split()[0])

            # Parse dependencies
            blocked_match = re.search(r"Blocked By:\s*(.+?)(?=Points:|$)", content)
            blocked_by = []
            if blocked_match:
                blocked_str = blocked_match.group(1).strip()
                if blocked_str.lower() != "none":
                    blocked_by = re.findall(r"STORY-\d+", blocked_str)

            # Parse points
            points_match = re.search(r"Points:\s*(\d+)", content)
            points = int(points_match.group(1)) if points_match else 3

            stories.append(UserStory(
                id=story_id,
                epic_id=epic_id,
                title=title,
                description=description,
                as_a=as_a,
                i_want=i_want,
                so_that=so_that,
                acceptance_criteria=acceptance_criteria,
                files_to_modify=files_to_modify,
                blocked_by=blocked_by,
                estimated_points=points,
            ))

        # Link stories to epics
        for epic in epics:
            epic.stories = [s.id for s in stories if s.epic_id == epic.id]

        # Fallback if no epics/stories parsed
        if not epics:
            epics = self._generate_basic_epics(brd)
        if not stories:
            stories = self._generate_basic_stories(epics, brd)

        return epics, stories

    def _generate_basic_epics(self, brd: BRDDocument) -> list[Epic]:
        """Generate basic epics from BRD requirements."""
        epics = []

        # Group by functional areas
        if brd.functional_requirements:
            epics.append(Epic(
                id="EPIC-001",
                title="Core Functionality",
                description="Implement core functional requirements",
                components=[],
                estimated_effort="medium",
                priority="high",
            ))

        if brd.technical_requirements:
            epics.append(Epic(
                id="EPIC-002",
                title="Technical Implementation",
                description="Implement technical requirements and infrastructure",
                components=[],
                estimated_effort="medium",
                priority="medium",
            ))

        return epics or [Epic(
            id="EPIC-001",
            title="Implementation",
            description=f"Implement {brd.title}",
            components=[],
            estimated_effort="medium",
            priority="medium",
        )]

    def _generate_basic_stories(
        self,
        epics: list[Epic],
        brd: BRDDocument,
    ) -> list[UserStory]:
        """Generate basic stories from BRD requirements."""
        stories = []
        story_num = 1

        # Create stories from functional requirements
        for i, req in enumerate(brd.functional_requirements[:5]):
            epic_id = epics[0].id if epics else "EPIC-001"
            stories.append(UserStory(
                id=f"STORY-{story_num:03d}",
                epic_id=epic_id,
                title=req.title,
                description=req.description,
                as_a="user",
                i_want=req.title.lower(),
                so_that="I can use this functionality",
                acceptance_criteria=[AcceptanceCriteria(criterion=ac.criterion) for ac in req.acceptance_criteria],
                estimated_points=3,
            ))
            story_num += 1

        # Create stories from technical requirements
        for i, req in enumerate(brd.technical_requirements[:3]):
            epic_id = epics[1].id if len(epics) > 1 else (epics[0].id if epics else "EPIC-001")
            stories.append(UserStory(
                id=f"STORY-{story_num:03d}",
                epic_id=epic_id,
                title=req.title,
                description=req.description,
                as_a="developer",
                i_want=req.title.lower(),
                so_that="the system works correctly",
                estimated_points=5,
            ))
            story_num += 1

        return stories

    async def create_jira_issues(
        self,
        epics: list[Epic],
        stories: list[UserStory],
        project_key: str,
        use_skill: bool = True,
    ) -> JiraCreationResult:
        """
        PHASE 3: Create Epics and Stories in JIRA.

        Uses the create-jira-issues skill with Atlassian MCP server.

        Args:
            epics: List of approved Epics
            stories: List of approved User Stories
            project_key: JIRA project key
            use_skill: If True, use skill-based approach

        Returns:
            JiraCreationResult with created issue details
        """
        logger.info(f"Creating JIRA issues in project: {project_key}")

        if use_skill and self._copilot_available:
            # Use skill-based approach
            prompt = self._build_jira_creation_prompt(epics, stories, project_key)
            response = await self._send_to_llm(prompt)

            # Parse the response
            result = self._parse_jira_creation_response(response, epics, stories, project_key)
        else:
            # Return error - JIRA creation requires MCP tools
            result = JiraCreationResult(
                project_key=project_key,
                errors=[{
                    "issue": "Configuration",
                    "error": "JIRA creation requires Copilot SDK with Atlassian MCP server"
                }],
            )

        return result

    def _build_jira_creation_prompt(
        self,
        epics: list[Epic],
        stories: list[UserStory],
        project_key: str,
    ) -> str:
        """Build prompt for creating JIRA issues."""
        # Format epics
        epics_text = ""
        for epic in epics:
            epics_text += f"""
EPIC: {epic.id}
Title: {epic.title}
Description: {epic.description}
Components: {', '.join(epic.components)}
Priority: {epic.priority}
Effort: {epic.estimated_effort}
"""

        # Format stories
        stories_text = ""
        for story in stories:
            stories_text += f"""
STORY: {story.id}
Epic: {story.epic_id}
Title: {story.title}
User Story: As a {story.as_a}, I want {story.i_want}, so that {story.so_that}.
Description: {story.description}
Acceptance Criteria:
{chr(10).join(f'- {ac.criterion}' for ac in story.acceptance_criteria)}
Files to Modify: {', '.join(story.files_to_modify) or 'None'}
Blocked By: {', '.join(story.blocked_by) or 'None'}
Points: {story.estimated_points or 3}
"""

        return f"""Create JIRA issues for the following Epics and Stories.

## JIRA Project: {project_key}

## Epics to Create
{epics_text}

## Stories to Create
{stories_text}

---

## Instructions

1. **Verify project exists** using jira_get_projects
2. **Create Epics first** using jira_create_issue
   - Issue type: Epic
   - Add labels: ["brd-generated", "EPIC-XXX"]
3. **Create Stories** and link to Epics
   - Issue type: Story
   - Link to parent Epic
   - Add story points
4. **Create issue links** for dependencies (blocks/is blocked by)
5. **Add technical notes as comments** for each story

## Expected Output

Report the JIRA keys created for each Epic and Story:
- EPIC-001 → PROJ-101
- STORY-001 → PROJ-102
- etc.

Report any errors encountered.
"""

    def _parse_jira_creation_response(
        self,
        response: str,
        epics: list[Epic],
        stories: list[UserStory],
        project_key: str,
    ) -> JiraCreationResult:
        """Parse JIRA creation response and update Epic/Story objects."""
        created_epics = []
        created_stories = []
        links = []
        errors = []

        # Look for JIRA key assignments in response
        # Pattern: EPIC-001 → PROJ-101 or EPIC-001 -> PROJ-101
        key_pattern = r"(EPIC-\d+|STORY-\d+)\s*[→\->]+\s*([A-Z]+-\d+)"
        matches = re.findall(key_pattern, response)

        jira_keys = {local_id: jira_key for local_id, jira_key in matches}

        # Update epics with JIRA keys
        for epic in epics:
            epic_copy = epic.model_copy()
            if epic.id in jira_keys:
                epic_copy.jira_key = jira_keys[epic.id]
                epic_copy.jira_status = "created"
            else:
                epic_copy.jira_status = "pending"
            created_epics.append(epic_copy)

        # Update stories with JIRA keys
        for story in stories:
            story_copy = story.model_copy()
            if story.id in jira_keys:
                story_copy.jira_key = jira_keys[story.id]
                story_copy.jira_status = "created"
            else:
                story_copy.jira_status = "pending"
            created_stories.append(story_copy)

        # Look for link creations
        link_pattern = r"([A-Z]+-\d+)\s+(?:blocks|is blocked by)\s+([A-Z]+-\d+)"
        link_matches = re.findall(link_pattern, response, re.IGNORECASE)
        for from_key, to_key in link_matches:
            links.append({"from": from_key, "type": "blocks", "to": to_key})

        # Look for errors
        error_pattern = r"Error:?\s*(.+?)(?=\n|$)"
        error_matches = re.findall(error_pattern, response, re.IGNORECASE)
        for error_msg in error_matches:
            errors.append({"issue": "Unknown", "error": error_msg.strip()})

        return JiraCreationResult(
            project_key=project_key,
            epics_created=created_epics,
            stories_created=created_stories,
            links_created=links,
            errors=errors,
            metadata={
                "total_epics": len(created_epics),
                "total_stories": len(created_stories),
                "total_links": len(links),
                "failed_count": len(errors),
            },
        )

    async def cleanup(self):
        """Cleanup resources."""
        pass  # Session cleanup is handled by the generator

    async def _send_with_event_logging(self, prompt: str) -> str:
        """
        Send prompt to LLM via Copilot SDK with detailed event logging.

        This method streams events from the SDK session to capture:
        - MCP tool invocations (Neo4j queries, file reads)
        - Tool results
        - LLM thinking/reasoning steps
        - Final response

        Args:
            prompt: The prompt to send

        Returns:
            The final LLM response text
        """
        if not self._copilot_available or not self.session:
            logger.warning("[EVENT-STREAM] No Copilot session, using mock")
            return self._generate_mock_response(prompt)

        logger.info("=" * 80)
        logger.info("[EVENT-STREAM] Starting event-logged request")
        logger.info(f"[EVENT-STREAM] Prompt ({len(prompt)} chars):\n{prompt}")
        logger.info("=" * 80)

        try:
            message_options = {"prompt": prompt}

            # Check if session supports event streaming
            if hasattr(self.session, 'send_and_stream'):
                logger.info("[EVENT-STREAM] Using send_and_stream for event capture")
                return await self._stream_events(message_options)

            elif hasattr(self.session, 'send_and_wait'):
                # Use send_and_wait but try to get events
                logger.info("[EVENT-STREAM] Using send_and_wait (limited event capture)")
                event = await asyncio.wait_for(
                    self.session.send_and_wait(message_options, timeout=LLM_TIMEOUT_SECONDS),
                    timeout=LLM_TIMEOUT_SECONDS,
                )

                if event:
                    self._log_event(event)
                    return self._extract_from_event(event)
                else:
                    logger.warning("[EVENT-STREAM] No event received")
                    return ""

            else:
                logger.warning("[EVENT-STREAM] No streaming method available")
                return await self._send_to_llm(prompt)

        except asyncio.TimeoutError:
            logger.error(f"[EVENT-STREAM] Timeout after {LLM_TIMEOUT_SECONDS}s")
            return self._generate_mock_response(prompt)
        except Exception as e:
            logger.error(f"[EVENT-STREAM] Error: {e}")
            import traceback
            logger.error(f"[EVENT-STREAM] Traceback:\n{traceback.format_exc()}")
            return self._generate_mock_response(prompt)

    async def _stream_events(self, message_options: dict) -> str:
        """Stream events from SDK and log each one."""
        final_response = ""
        tool_calls = []

        try:
            async for event in self.session.send_and_stream(message_options):
                event_type = type(event).__name__
                logger.info(f"[EVENT] Type: {event_type}")

                # Log event details
                self._log_event(event)

                # Track tool calls
                if self._is_tool_call_event(event):
                    tool_info = self._extract_tool_call_info(event)
                    if tool_info:
                        tool_calls.append(tool_info)
                        logger.info(f"[MCP-TOOL-CALL] {tool_info}")

                # Track tool results
                if self._is_tool_result_event(event):
                    result_info = self._extract_tool_result_info(event)
                    if result_info:
                        logger.info(f"[MCP-TOOL-RESULT] {result_info[:500]}...")

                # Accumulate final response
                if self._is_content_event(event):
                    content = self._extract_content_from_event(event)
                    if content:
                        final_response += content

        except Exception as e:
            logger.error(f"[EVENT-STREAM] Error during streaming: {e}")

        logger.info("=" * 80)
        logger.info(f"[EVENT-STREAM] Complete. Tool calls made: {len(tool_calls)}")
        for i, tc in enumerate(tool_calls, 1):
            logger.info(f"[EVENT-STREAM]   {i}. {tc}")
        logger.info(f"[EVENT-STREAM] Response length: {len(final_response)} chars")
        logger.info("=" * 80)

        return final_response

    def _log_event(self, event: Any) -> None:
        """Log details of a session event."""
        try:
            event_type = type(event).__name__

            # Log event type and available attributes
            attrs = [a for a in dir(event) if not a.startswith('_')]
            logger.info(f"[EVENT-DETAIL] {event_type} attributes: {attrs[:10]}")

            # Try to extract key information
            if hasattr(event, 'data'):
                data = event.data
                data_attrs = [a for a in dir(data) if not a.startswith('_')]
                logger.info(f"[EVENT-DETAIL] data attributes: {data_attrs[:10]}")

                # Check for tool call
                if hasattr(data, 'tool_call') or hasattr(data, 'tool_name'):
                    tool_name = getattr(data, 'tool_name', None) or getattr(data, 'name', None)
                    tool_input = getattr(data, 'tool_input', None) or getattr(data, 'input', None)
                    logger.info(f"[EVENT-DETAIL] TOOL CALL: {tool_name}")
                    if tool_input:
                        logger.info(f"[EVENT-DETAIL] TOOL INPUT: {str(tool_input)[:500]}")

                # Check for tool result
                if hasattr(data, 'tool_result') or hasattr(data, 'result'):
                    result = getattr(data, 'tool_result', None) or getattr(data, 'result', None)
                    logger.info(f"[EVENT-DETAIL] TOOL RESULT: {str(result)[:500]}")

                # Check for content
                if hasattr(data, 'content'):
                    logger.info(f"[EVENT-DETAIL] CONTENT: {str(data.content)[:200]}...")

                # Check for message
                if hasattr(data, 'message'):
                    msg = data.message
                    if hasattr(msg, 'content'):
                        logger.info(f"[EVENT-DETAIL] MESSAGE CONTENT: {str(msg.content)[:200]}...")
                    if hasattr(msg, 'tool_calls'):
                        logger.info(f"[EVENT-DETAIL] MESSAGE TOOL_CALLS: {msg.tool_calls}")

        except Exception as e:
            logger.debug(f"[EVENT-DETAIL] Error logging event: {e}")

    def _is_tool_call_event(self, event: Any) -> bool:
        """Check if event represents a tool call."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                return (
                    hasattr(data, 'tool_call') or
                    hasattr(data, 'tool_name') or
                    (hasattr(data, 'type') and 'tool' in str(data.type).lower())
                )
            return False
        except Exception:
            return False

    def _is_tool_result_event(self, event: Any) -> bool:
        """Check if event represents a tool result."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                return (
                    hasattr(data, 'tool_result') or
                    hasattr(data, 'result') or
                    (hasattr(data, 'type') and 'result' in str(data.type).lower())
                )
            return False
        except Exception:
            return False

    def _is_content_event(self, event: Any) -> bool:
        """Check if event contains content."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                return hasattr(data, 'content') or hasattr(data, 'text')
            return False
        except Exception:
            return False

    def _extract_tool_call_info(self, event: Any) -> Optional[str]:
        """Extract tool call information from event."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                tool_name = getattr(data, 'tool_name', None) or getattr(data, 'name', 'unknown')
                tool_input = getattr(data, 'tool_input', None) or getattr(data, 'input', {})
                return f"{tool_name}: {str(tool_input)[:200]}"
            return None
        except Exception:
            return None

    def _extract_tool_result_info(self, event: Any) -> Optional[str]:
        """Extract tool result information from event."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                result = getattr(data, 'tool_result', None) or getattr(data, 'result', None)
                if result:
                    return str(result)
            return None
        except Exception:
            return None

    def _extract_content_from_event(self, event: Any) -> Optional[str]:
        """Extract content from event."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                if hasattr(data, 'content'):
                    return str(data.content)
                if hasattr(data, 'text'):
                    return str(data.text)
            return None
        except Exception:
            return None

    def _create_mock_brd(self, feature_request: str) -> "BRDDocument":
        """Create a mock BRD when SDK is not available."""
        from datetime import datetime
        return BRDDocument(
            id=f"BRD-MOCK-{hash(feature_request) % 10000:04d}",
            title=f"BRD: {feature_request}",
            version="1.0",
            created_at=datetime.now(),
            business_context="[Mock] Copilot SDK not available. This is a placeholder BRD.",
            objectives=["Review with actual codebase analysis"],
            functional_requirements=[
                Requirement(
                    id="FR-MOCK-001",
                    title="Placeholder requirement",
                    description="Actual requirements need Copilot SDK with MCP tools",
                    priority="high",
                    acceptance_criteria=[],
                )
            ],
            technical_requirements=[],
            dependencies=[],
            risks=["Mock BRD - needs real analysis"],
        )

    async def _send_to_llm(self, prompt: str) -> str:
        """Send prompt to LLM via Copilot SDK session."""
        if not self._copilot_available or not self.session:
            progress.warning("Copilot session not available. Using mock response.")
            logger.warning("[LLM-MOCK] Falling back to mock response - no Copilot session")
            return self._generate_mock_response(prompt)

        try:
            # Log the prompt being sent
            logger.info(f"[LLM-PROMPT] Sending prompt to LLM ({len(prompt)} chars)")
            logger.info(f"[LLM-PROMPT] Prompt preview:\n{prompt[:1000]}...")
            progress.info(f"Sending prompt to LLM ({len(prompt)} chars, timeout={LLM_TIMEOUT_SECONDS}s)")

            # Send message using SDK session with correct MessageOptions format
            response = await asyncio.wait_for(
                self._send_to_session(prompt),
                timeout=LLM_TIMEOUT_SECONDS,
            )

            if response:
                logger.info(f"[LLM-RESPONSE] Received response ({len(response)} chars)")
                logger.info(f"[LLM-RESPONSE] Response preview:\n{response[:1000]}...")
                progress.info(f"LLM response received: {len(response)} chars")
                return response
            else:
                progress.warning("Empty response from Copilot, using mock")
                logger.warning("[LLM-MOCK] Empty response from Copilot - falling back to mock")
                return self._generate_mock_response(prompt)

        except asyncio.TimeoutError:
            progress.error(f"LLM response timed out after {LLM_TIMEOUT_SECONDS}s")
            logger.error(f"[LLM-TIMEOUT] Response timed out after {LLM_TIMEOUT_SECONDS}s")
            return self._generate_mock_response(prompt)
        except Exception as e:
            progress.error(f"Copilot call failed: {e}")
            logger.error(f"[LLM-ERROR] Copilot call failed: {e}")
            return self._generate_mock_response(prompt)

    async def _send_to_session(self, prompt: str) -> str:
        """Send message to Copilot SDK session using correct API."""
        try:
            # Build MessageOptions with prompt key
            message_options = {"prompt": prompt}
            logger.info("[SDK-SESSION] Building message options for Copilot SDK")
            progress.debug(f"Building message options for Copilot SDK")

            # Use send_and_wait for synchronous response (it's async)
            if hasattr(self.session, 'send_and_wait'):
                logger.info("[SDK-SESSION] Calling session.send_and_wait()...")
                progress.info("Calling session.send_and_wait()...")
                # send_and_wait is an async method - await it directly
                event = await self.session.send_and_wait(message_options, timeout=LLM_TIMEOUT_SECONDS)

                if event:
                    # Extract content from SessionEvent
                    logger.info(f"[SDK-SESSION] Received event type: {type(event).__name__}")
                    logger.info(f"[SDK-SESSION] Event attributes: {dir(event)}")
                    progress.debug(f"Received event type: {type(event).__name__}")
                    return self._extract_from_event(event)
                else:
                    logger.warning("[SDK-SESSION] send_and_wait returned None")
                    progress.warning("send_and_wait returned None")

            # Fallback to send() method
            if hasattr(self.session, 'send'):
                progress.info("Using fallback send() method...")
                # send() is also async
                message_id = await self.session.send(message_options)
                progress.info(f"Message sent, ID: {message_id}")

                # Wait for response by polling get_messages
                return await self._wait_for_response(message_id)

            progress.error("No suitable send method found on session")
            return ""

        except Exception as e:
            progress.error(f"Error sending to Copilot session: {e}")
            raise

    def _extract_from_event(self, event: Any) -> str:
        """Extract text content from a SessionEvent."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                # Check for message content
                if hasattr(data, 'message') and hasattr(data.message, 'content'):
                    return str(data.message.content)
                if hasattr(data, 'content'):
                    return str(data.content)
                if hasattr(data, 'text'):
                    return str(data.text)

            # Try direct attributes
            if hasattr(event, 'content'):
                return str(event.content)
            if hasattr(event, 'text'):
                return str(event.text)

            # Convert to string as last resort
            logger.warning(f"Unknown event format: {type(event)}")
            return str(event)

        except Exception as e:
            logger.error(f"Error extracting from event: {e}")
            return ""

    async def _wait_for_response(self, message_id: str) -> str:
        """Wait for a response to a sent message by polling get_messages."""
        start_time = asyncio.get_event_loop().time()
        poll_interval = 1.0

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > LLM_TIMEOUT_SECONDS:
                logger.warning("Timeout waiting for response")
                return ""

            try:
                messages = self.session.get_messages()
                # Look for a response event
                for msg in reversed(messages):
                    if hasattr(msg, 'data'):
                        data = msg.data
                        # Check if this is a response to our message
                        if hasattr(data, 'message_type') and 'assistant' in str(data.message_type).lower():
                            return self._extract_from_event(msg)
                        if hasattr(data, 'role') and data.role == 'assistant':
                            return self._extract_from_event(msg)
                        # Check for completion event
                        if hasattr(data, 'type') and 'completion' in str(data.type).lower():
                            return self._extract_from_event(msg)

            except Exception as e:
                logger.warning(f"Error polling messages: {e}")

            await asyncio.sleep(poll_interval)

    def _generate_mock_response(self, prompt: str) -> str:
        """Generate mock response for testing without LLM."""
        if "business requirements" in prompt.lower() or "brd" in prompt.lower():
            return """
## Business Context
This feature addresses the need for improved functionality.

## Objectives
1. Enhance user experience
2. Improve system performance
3. Maintain backward compatibility

## Functional Requirements
FR-001: The system shall provide the requested functionality.
FR-002: The system shall validate all inputs.

## Technical Requirements
TR-001: The implementation shall follow existing patterns.
TR-002: The solution shall be scalable.

## Dependencies
- Existing authentication system
- Database infrastructure

## Risks
- Integration complexity
- Testing coverage requirements
"""
        elif "epic" in prompt.lower():
            return """
EPIC-001: Core Implementation
- Description: Implement the core functionality
- Components: main-service, database
- Effort: medium

EPIC-002: Integration
- Description: Integrate with existing systems
- Components: api-gateway, auth-service
- Effort: small
"""
        else:
            return """
STORY-001: As a user, I want to use the new feature, so that I can improve my workflow.
Acceptance Criteria:
- Feature is accessible from main menu
- Feature works as expected
"""

    async def _analyze_context(
        self,
        context: AggregatedContext,
        analysis_prompt: str,
    ) -> str:
        """First stage: analyze the context."""
        components_json = json.dumps(
            [c.model_dump() for c in context.architecture.components],
            indent=2,
        )

        prompt = analysis_prompt.format(
            request=context.request,
            components=components_json,
            files_count=len(context.implementation.key_files),
        )

        response = await self._send_to_llm(prompt)
        return response

    def _build_brd_prompt(
        self,
        context: AggregatedContext,
        analysis: str,
        template: str,
    ) -> str:
        """Build the BRD generation prompt."""
        file_summaries = []
        for fc in context.implementation.key_files[:5]:
            file_summaries.append(f"- {fc.path}: {len(fc.content)} chars")

        return f"""
Generate a comprehensive Business Requirements Document for the following feature request.

Feature Request: {context.request}

Analysis:
{analysis}

Architecture Context:
- Components: {len(context.architecture.components)}
- API Contracts: {len(context.architecture.api_contracts)}
- Dependencies: {len(context.architecture.dependencies)}

Key Files:
{chr(10).join(file_summaries) or "No files analyzed"}

Similar Features Found: {', '.join(context.similar_features) or 'None'}

Template to follow:
{template if template else 'Standard BRD format'}

Generate the BRD with:
1. Business Context - Why this feature is needed
2. Objectives - Clear, measurable goals
3. Functional Requirements - What the system should do (use FR-XXX format)
4. Technical Requirements - How it should be implemented (use TR-XXX format)
5. Dependencies - What this feature depends on
6. Risks - Potential issues and mitigation strategies

Be specific and reference actual component names when possible.
"""

    def _build_epics_prompt(
        self,
        context: AggregatedContext,
        brd: BRDDocument,
    ) -> str:
        """Build prompt for epic generation."""
        requirements_summary = []
        for req in brd.functional_requirements[:5]:
            requirements_summary.append(f"- {req.id}: {req.title}")

        return f"""
Based on the following BRD, generate Epics that group related work.

Feature: {brd.title}

Business Context: {brd.business_context[:500]}

Key Requirements:
{chr(10).join(requirements_summary)}

Components Involved: {', '.join(c.name for c in context.architecture.components)}

Generate 2-4 Epics in this format:
EPIC-XXX: Title
- Description: Brief description
- Components: comma-separated list
- Effort: small/medium/large

Focus on logical groupings that can be delivered incrementally.
"""

    def _build_stories_prompt(
        self,
        context: AggregatedContext,
        epic: Epic,
    ) -> str:
        """Build prompt for user story generation."""
        return f"""
Generate User Stories for the following Epic.

Epic: {epic.title}
Description: {epic.description}
Components: {', '.join(epic.components)}

Generate 3-5 User Stories in this format:
STORY-XXX: Title
As a [role], I want [capability], so that [benefit].
Acceptance Criteria:
- Criterion 1
- Criterion 2
Technical Notes: Implementation hints

Make stories small enough to complete in 1-3 days.
"""

    def _parse_brd_response(self, response: str, request: str) -> BRDDocument:
        """Parse LLM response into BRDDocument, preserving raw markdown."""
        business_context = self._extract_section(response, "Business Context") or request
        objectives = self._extract_list(response, "Objectives")
        func_reqs = self._extract_requirements(response, "Functional Requirements", "FR")
        tech_reqs = self._extract_requirements(response, "Technical Requirements", "TR")
        dependencies = self._extract_list(response, "Dependencies")
        risks = self._extract_list(response, "Risks")

        return BRDDocument(
            title=f"BRD: {request[:50]}",
            business_context=business_context,
            objectives=objectives,
            functional_requirements=func_reqs,
            technical_requirements=tech_reqs,
            dependencies=dependencies,
            risks=risks,
            raw_markdown=response,  # Preserve full LLM-generated markdown
        )

    def _parse_epics_response(self, response: str) -> list[Epic]:
        """Parse LLM response into Epics."""
        epics = []
        epic_pattern = r"EPIC-(\d+):\s*(.+?)(?=EPIC-\d+:|$)"
        matches = re.findall(epic_pattern, response, re.DOTALL)

        for match in matches:
            epic_id = f"EPIC-{match[0]}"
            content = match[1].strip()
            lines = content.split("\n")
            title = lines[0].strip() if lines else "Untitled Epic"

            desc_match = re.search(r"Description:\s*(.+?)(?=Components:|Effort:|$)", content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else content[:200]

            comp_match = re.search(r"Components:\s*(.+?)(?=Effort:|$)", content)
            components = []
            if comp_match:
                components = [c.strip() for c in comp_match.group(1).split(",")]

            effort_match = re.search(r"Effort:\s*(small|medium|large)", content, re.IGNORECASE)
            effort = effort_match.group(1).lower() if effort_match else "medium"

            epics.append(Epic(
                id=epic_id,
                title=title,
                description=description,
                components=components,
                estimated_effort=effort,
            ))

        if not epics:
            epics.append(Epic(
                id="EPIC-001",
                title="Core Implementation",
                description="Implement the core functionality",
                components=[],
                estimated_effort="medium",
            ))

        return epics

    def _parse_stories_response(self, response: str, epic_id: str) -> list[UserStory]:
        """Parse LLM response into UserStories."""
        stories = []
        story_pattern = r"STORY-(\d+):\s*(.+?)(?=STORY-\d+:|$)"
        matches = re.findall(story_pattern, response, re.DOTALL)

        for match in matches:
            story_id = f"STORY-{match[0]}"
            content = match[1].strip()
            lines = content.split("\n")
            title = lines[0].strip() if lines else "Untitled Story"

            as_a_match = re.search(r"As a\s+(.+?),", content)
            i_want_match = re.search(r"I want\s+(.+?),", content)
            so_that_match = re.search(r"so that\s+(.+?)(?:\.|$)", content)

            as_a = as_a_match.group(1) if as_a_match else "user"
            i_want = i_want_match.group(1) if i_want_match else "this functionality"
            so_that = so_that_match.group(1) if so_that_match else "I can achieve my goal"

            ac_section = re.search(r"Acceptance Criteria:(.+?)(?:Technical Notes:|$)", content, re.DOTALL)
            acceptance_criteria = []
            if ac_section:
                for line in ac_section.group(1).split("\n"):
                    line = line.strip().lstrip("-").strip()
                    if line:
                        acceptance_criteria.append(AcceptanceCriteria(criterion=line))

            tech_notes_match = re.search(r"Technical Notes:\s*(.+?)$", content, re.DOTALL)
            tech_notes = tech_notes_match.group(1).strip() if tech_notes_match else None

            stories.append(UserStory(
                id=story_id,
                epic_id=epic_id,
                title=title,
                description=content[:500],
                as_a=as_a,
                i_want=i_want,
                so_that=so_that,
                acceptance_criteria=acceptance_criteria,
                technical_notes=tech_notes,
            ))

        if not stories:
            stories.append(UserStory(
                id=f"STORY-{epic_id.split('-')[1]}01",
                epic_id=epic_id,
                title="Implement core functionality",
                description="Implement the main feature",
                as_a="user",
                i_want="to use the new feature",
                so_that="I can improve my workflow",
                acceptance_criteria=[
                    AcceptanceCriteria(criterion="Feature works as expected"),
                ],
            ))

        return stories

    def _extract_section(self, text: str, section_name: str) -> str:
        """Extract a section from the response."""
        pattern = rf"(?:##?\s*\d*\.?\s*)?{section_name}[:\s]*\n+(.*?)(?=(?:##?\s*\d*\.?\s*\w)|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _extract_list(self, text: str, section_name: str) -> list[str]:
        """Extract a bulleted list from a section."""
        section = self._extract_section(text, section_name)
        if not section:
            return []

        items = []
        for line in section.split("\n"):
            line = line.strip()
            line = re.sub(r"^[\d\.\-\*]+\s*", "", line)
            if line:
                items.append(line)

        return items

    def _extract_requirements(
        self,
        text: str,
        section_name: str,
        prefix: str,
    ) -> list[Requirement]:
        """Extract requirements from a section."""
        section = self._extract_section(text, section_name)
        if not section:
            return []

        requirements = []
        req_pattern = rf"({prefix}-\d+):\s*(.+?)(?={prefix}-\d+:|$)"
        matches = re.findall(req_pattern, section, re.DOTALL)

        for req_id, content in matches:
            lines = content.strip().split("\n")
            title = lines[0].strip() if lines else "Untitled"
            description = "\n".join(lines[1:]).strip() if len(lines) > 1 else title

            requirements.append(Requirement(
                id=req_id,
                title=title,
                description=description,
                priority="medium",
            ))

        if not requirements:
            items = self._extract_list(text, section_name)
            for i, item in enumerate(items, 1):
                requirements.append(Requirement(
                    id=f"{prefix}-{i:03d}",
                    title=item[:100],
                    description=item,
                    priority="medium",
                ))

        return requirements

    def _load_template(self, filename: str) -> str:
        """Load template file."""
        path = self.templates_dir / filename
        if not path.exists():
            logger.warning(f"Template not found: {filename}")
            return ""
        return path.read_text()

    def _load_prompt(self, filename: str) -> str:
        """Load prompt file."""
        prompts_dir = self.templates_dir.parent / "prompts"
        path = prompts_dir / filename
        if not path.exists():
            logger.warning(f"Prompt not found: {filename}")
            return """
Analyze the following feature request and codebase context:

Feature Request: {request}

Architecture Components:
{components}

Files Available: {files_count}

Provide:
1. Scope assessment (which components affected)
2. Integration points identified
3. Similar existing features (if any)
4. Key technical challenges
5. Recommended implementation approach

Be specific and reference actual component names and file paths.
"""
        return path.read_text()
