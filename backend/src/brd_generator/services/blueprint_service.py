"""Business Logic Blueprint Generation Service.

Generates comprehensive Business Logic Blueprint documents from code analysis.
Follows the hierarchical structure: Menu -> Sub-Menu -> Screen -> Fields/Actions.
"""

import asyncio
from datetime import datetime
from typing import Any, Optional, List, Dict
from uuid import uuid4

from ..utils.logger import get_logger
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..queries.blueprint_queries import (
    GET_MENU_HIERARCHY,
    GET_SCREEN_DETAILS,
    GET_SCREEN_FIELDS,
    GET_SCREEN_ACTIONS,
    GET_SCREEN_VALIDATIONS,
    GET_SECURITY_RULES_FOR_SCREEN,
    GET_ERROR_MESSAGES_FOR_SCREEN,
    GET_DATA_TABLES_FOR_SCREEN,
    GET_FEATURE_BLUEPRINT_CONTEXT,
)

logger = get_logger(__name__)


# =============================================================================
# Business Logic Blueprint Prompts
# =============================================================================

BLUEPRINT_MASTER_PROMPT = """You are generating a comprehensive Business Logic Blueprint document.
This document must capture every business rule, field behavior, user flow, and behavioral dependency
in plain natural language with zero technical jargon or code references.

## Document Requirements
- Technology-agnostic: No database tables, API endpoints, framework references, or code snippets
- Exhaustive: Every field, every button, every rule, every edge case
- Plain language only: Business terminology from the user's perspective
- Precise conditions: Don't say "some fields may be required" - say exactly which fields under what conditions

## Output Format
Generate the documentation in Markdown format with clear hierarchical structure.
"""

SCREEN_BLUEPRINT_PROMPT = """Generate a Business Logic Blueprint section for this screen.

## Screen Information
- **Screen Name:** {screen_name}
- **Menu Path:** {menu_path}
- **Flow:** {flow_name}

## Screen Context
{screen_context}

## Fields on This Screen
{fields_info}

## Actions/Buttons on This Screen
{actions_info}

## Validation Rules
{validations_info}

## Security/Access Control
{security_info}

## Error Messages
{error_messages}

## Data Tables/Grids
{tables_info}

## Instructions
Based on the information above, generate comprehensive documentation following this structure:

### 1. Screen Purpose & Overview
- What is this screen for in business terms?
- When would a user navigate here?
- What is the entry point?

### 2. Roles & Access Control
- Which roles can access this screen?
- What can each role see vs. do?
- Any role-based field visibility differences?

### 3. Field-by-Field Detail
For each field, document:
| Field | Label | Type | Required | Validation | Default | Conditional Behavior |

### 4. Action-by-Action Flow
For each action (Save, Delete, Submit, etc.):
- Pre-conditions
- Step-by-step what happens
- Validations that run
- Error handling
- What user sees after completion

### 5. Business Rules
- Any calculations or derivations
- Cross-field dependencies
- Conditional requirements

### 6. Error Handling
- Error conditions and messages
- Recovery paths for users

Output ONLY the markdown documentation, no additional explanation.
"""

FEATURE_OVERVIEW_PROMPT = """Generate a Business Logic Blueprint overview for this feature.

## Feature Information
- **Feature Name:** {feature_name}
- **Menu Path:** {menu_path}
- **Total Screens:** {screen_count}

## Feature Context
{feature_context}

## Sub-Screens/Sub-Features
{sub_screens}

## Instructions
Generate an overview section that:
1. Describes the overall purpose of this feature
2. Lists all sub-screens and their relationships
3. Describes the typical user workflows
4. Notes any cross-screen dependencies

Output ONLY the markdown documentation.
"""


# =============================================================================
# Blueprint Service
# =============================================================================

class BlueprintService:
    """Service for generating Business Logic Blueprint documents."""

    def __init__(self, neo4j_client: Neo4jMCPClient, llm_session: Any = None):
        """Initialize the blueprint service.

        Args:
            neo4j_client: Neo4j client for querying code graph
            llm_session: Copilot SDK session for LLM generation
        """
        self.neo4j_client = neo4j_client
        self.llm_session = llm_session
        self._llm_available = llm_session is not None

        if self._llm_available:
            logger.info("BlueprintService initialized with LLM support")
        else:
            logger.warning("BlueprintService initialized without LLM - limited functionality")

    async def generate_full_blueprint(
        self,
        repository_id: str,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Generate complete Business Logic Blueprint for entire codebase.

        Args:
            repository_id: Repository to generate blueprint for
            progress_callback: Optional callback for progress updates

        Returns:
            Dict containing the full blueprint document and metadata
        """
        logger.info(f"Starting full blueprint generation for repository: {repository_id}")
        start_time = datetime.utcnow()

        sections = []
        total_screens = 0
        total_fields = 0
        total_rules = 0

        # Step 1: Get menu hierarchy
        if progress_callback:
            await progress_callback("Fetching menu hierarchy", "Loading application structure...")

        menu_hierarchy = await self._get_menu_hierarchy(repository_id)
        logger.info(f"Found {len(menu_hierarchy)} top-level menus")

        # Step 2: Process each menu item
        for menu in menu_hierarchy:
            menu_name = menu.get("label", "Unknown Menu")
            if progress_callback:
                await progress_callback("Processing menu", f"Processing: {menu_name}")

            menu_section = await self._generate_menu_section(repository_id, menu, progress_callback)
            sections.append(menu_section)

            total_screens += menu_section.get("screen_count", 0)
            total_fields += menu_section.get("field_count", 0)
            total_rules += menu_section.get("rule_count", 0)

        # Step 3: Assemble final document
        if progress_callback:
            await progress_callback("Assembling document", "Combining all sections...")

        document = self._assemble_blueprint_document(sections, repository_id)

        end_time = datetime.utcnow()
        generation_time = (end_time - start_time).total_seconds()

        return {
            "document": document,
            "metadata": {
                "repository_id": repository_id,
                "generated_at": end_time.isoformat(),
                "generation_time_seconds": generation_time,
                "total_menus": len(menu_hierarchy),
                "total_screens": total_screens,
                "total_fields": total_fields,
                "total_rules": total_rules,
                "sections": len(sections),
            }
        }

    async def generate_feature_blueprint(
        self,
        repository_id: str,
        feature_name: str,
        menu_path: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Generate Business Logic Blueprint for a specific feature.

        Args:
            repository_id: Repository ID
            feature_name: Name of the feature (e.g., "Point Maintenance")
            menu_path: Optional menu path to the feature

        Returns:
            Dict containing the feature blueprint and metadata
        """
        logger.info(f"Generating blueprint for feature: {feature_name}")

        # Find the feature in the menu hierarchy
        context = await self._get_feature_context(repository_id, feature_name)

        if not context:
            return {
                "error": f"Feature '{feature_name}' not found in repository",
                "suggestions": await self._get_similar_features(repository_id, feature_name)
            }

        # Generate blueprint for all screens in this feature
        screens = context.get("screens", [])
        screen_sections = []

        for screen in screens:
            screen_section = await self._generate_screen_section(repository_id, screen)
            screen_sections.append(screen_section)

        # Generate feature overview
        overview = await self._generate_feature_overview(context, screen_sections)

        # Assemble feature document
        document = self._assemble_feature_document(overview, screen_sections, feature_name)

        return {
            "document": document,
            "metadata": {
                "feature_name": feature_name,
                "menu_path": menu_path or context.get("menu_path", []),
                "screen_count": len(screens),
                "generated_at": datetime.utcnow().isoformat(),
            }
        }

    async def _get_menu_hierarchy(self, repository_id: str) -> List[Dict]:
        """Fetch the menu hierarchy from the knowledge graph."""
        result = await self.neo4j_client.execute_query(
            GET_MENU_HIERARCHY,
            {"repositoryId": repository_id}
        )
        return result if result else []

    async def _get_feature_context(self, repository_id: str, feature_name: str) -> Optional[Dict]:
        """Get context for a specific feature."""
        result = await self.neo4j_client.execute_query(
            GET_FEATURE_BLUEPRINT_CONTEXT,
            {"repositoryId": repository_id, "featureName": feature_name}
        )
        return result[0] if result else None

    async def _generate_menu_section(
        self,
        repository_id: str,
        menu: Dict,
        progress_callback: Optional[callable] = None
    ) -> Dict:
        """Generate blueprint section for a menu item and its children."""
        menu_name = menu.get("label", "Unknown")
        sub_menus = menu.get("children", [])

        sub_sections = []
        screen_count = 0
        field_count = 0
        rule_count = 0

        for sub_menu in sub_menus:
            sub_name = sub_menu.get("label", "Unknown")
            if progress_callback:
                await progress_callback("Processing sub-menu", f"{menu_name} > {sub_name}")

            screens = sub_menu.get("screens", [])

            for screen in screens:
                screen_section = await self._generate_screen_section(repository_id, screen)
                sub_sections.append(screen_section)

                screen_count += 1
                field_count += screen_section.get("field_count", 0)
                rule_count += screen_section.get("rule_count", 0)

        return {
            "menu_name": menu_name,
            "sub_sections": sub_sections,
            "screen_count": screen_count,
            "field_count": field_count,
            "rule_count": rule_count,
            "content": self._format_menu_section(menu_name, sub_sections),
        }

    async def _generate_screen_section(self, repository_id: str, screen: Dict) -> Dict:
        """Generate blueprint section for a single screen."""
        screen_id = screen.get("screenId") or screen.get("entityId")
        screen_name = screen.get("name") or screen.get("title", "Unknown Screen")

        # Fetch all context for this screen
        fields = await self._get_screen_fields(repository_id, screen_id)
        actions = await self._get_screen_actions(repository_id, screen_id)
        validations = await self._get_screen_validations(repository_id, screen_id)
        security_rules = await self._get_security_rules(repository_id, screen_id)
        error_messages = await self._get_error_messages(repository_id, screen_id)
        data_tables = await self._get_data_tables(repository_id, screen_id)

        # Build context for LLM
        screen_context = {
            "screen_name": screen_name,
            "screen_id": screen_id,
            "flow_name": screen.get("flowId", ""),
            "menu_path": screen.get("menuPath", []),
            "fields": fields,
            "actions": actions,
            "validations": validations,
            "security_rules": security_rules,
            "error_messages": error_messages,
            "data_tables": data_tables,
        }

        # Generate documentation
        if self._llm_available:
            content = await self._generate_screen_content_with_llm(screen_context)
        else:
            content = self._generate_screen_content_template(screen_context)

        return {
            "screen_name": screen_name,
            "screen_id": screen_id,
            "field_count": len(fields),
            "rule_count": len(validations),
            "content": content,
        }

    async def _generate_screen_content_with_llm(self, context: Dict) -> str:
        """Generate screen documentation using LLM."""
        prompt = SCREEN_BLUEPRINT_PROMPT.format(
            screen_name=context["screen_name"],
            menu_path=" > ".join(context.get("menu_path", [])),
            flow_name=context.get("flow_name", ""),
            screen_context=self._format_screen_context(context),
            fields_info=self._format_fields_for_prompt(context["fields"]),
            actions_info=self._format_actions_for_prompt(context["actions"]),
            validations_info=self._format_validations_for_prompt(context["validations"]),
            security_info=self._format_security_for_prompt(context["security_rules"]),
            error_messages=self._format_errors_for_prompt(context["error_messages"]),
            tables_info=self._format_tables_for_prompt(context["data_tables"]),
        )

        try:
            response = await self._send_to_llm(prompt)
            return response if response else self._generate_screen_content_template(context)
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return self._generate_screen_content_template(context)

    def _generate_screen_content_template(self, context: Dict) -> str:
        """Generate screen documentation using template (fallback)."""
        screen_name = context["screen_name"]
        fields = context["fields"]
        actions = context["actions"]
        validations = context["validations"]
        security_rules = context["security_rules"]

        content = f"""## {screen_name}

### Purpose & Overview
This screen allows users to manage {screen_name.lower().replace('_', ' ')}.

### Roles & Access Control
"""
        if security_rules:
            for rule in security_rules:
                content += f"- {rule.get('description', 'Access controlled')}\n"
        else:
            content += "- Standard user access required\n"

        content += "\n### Field Details\n\n"
        content += "| Field | Type | Required | Validation |\n"
        content += "|-------|------|----------|------------|\n"

        for field in fields:
            field_name = field.get("label") or field.get("name", "Unknown")
            field_type = field.get("type", "text")
            required = "Yes" if field.get("required") else "No"
            validation = field.get("validationRules", "-")
            if isinstance(validation, dict):
                validation = ", ".join(f"{k}: {v}" for k, v in validation.items())
            content += f"| {field_name} | {field_type} | {required} | {validation} |\n"

        content += "\n### Actions\n\n"
        for action in actions:
            action_name = action.get("name") or action.get("label", "Action")
            content += f"#### {action_name}\n"
            content += f"- Triggers: {action.get('event', 'form submission')}\n"
            content += f"- Validations: {action.get('validations', 'Standard validation')}\n\n"

        content += "\n### Validation Rules\n\n"
        for validation in validations:
            content += f"- {validation.get('description', validation.get('ruleText', 'Validation rule'))}\n"

        return content

    async def _generate_feature_overview(self, context: Dict, screen_sections: List[Dict]) -> str:
        """Generate overview section for a feature."""
        feature_name = context.get("featureName", "Feature")
        screens = context.get("screens", [])

        if self._llm_available:
            prompt = FEATURE_OVERVIEW_PROMPT.format(
                feature_name=feature_name,
                menu_path=" > ".join(context.get("menu_path", [])),
                screen_count=len(screens),
                feature_context=str(context),
                sub_screens="\n".join([f"- {s['screen_name']}" for s in screen_sections]),
            )
            response = await self._send_to_llm(prompt)
            if response:
                return response

        # Template fallback
        return f"""# {feature_name}

## Overview
This feature provides functionality for {feature_name.lower().replace('_', ' ')}.

## Screens
{chr(10).join([f"- **{s['screen_name']}**: {s.get('field_count', 0)} fields, {s.get('rule_count', 0)} rules" for s in screen_sections])}

## Workflow
Users typically access this feature through the main menu and proceed through the screens in sequence.
"""

    # =============================================================================
    # Query Helper Methods
    # =============================================================================

    async def _get_screen_fields(self, repository_id: str, screen_id: str) -> List[Dict]:
        """Get fields for a screen."""
        result = await self.neo4j_client.execute_query(
            GET_SCREEN_FIELDS,
            {"repositoryId": repository_id, "screenId": screen_id}
        )
        return result if result else []

    async def _get_screen_actions(self, repository_id: str, screen_id: str) -> List[Dict]:
        """Get actions for a screen."""
        result = await self.neo4j_client.execute_query(
            GET_SCREEN_ACTIONS,
            {"repositoryId": repository_id, "screenId": screen_id}
        )
        return result if result else []

    async def _get_screen_validations(self, repository_id: str, screen_id: str) -> List[Dict]:
        """Get validations for a screen."""
        result = await self.neo4j_client.execute_query(
            GET_SCREEN_VALIDATIONS,
            {"repositoryId": repository_id, "screenId": screen_id}
        )
        return result if result else []

    async def _get_security_rules(self, repository_id: str, screen_id: str) -> List[Dict]:
        """Get security rules for a screen."""
        result = await self.neo4j_client.execute_query(
            GET_SECURITY_RULES_FOR_SCREEN,
            {"repositoryId": repository_id, "screenId": screen_id}
        )
        return result if result else []

    async def _get_error_messages(self, repository_id: str, screen_id: str) -> List[Dict]:
        """Get error messages for a screen."""
        result = await self.neo4j_client.execute_query(
            GET_ERROR_MESSAGES_FOR_SCREEN,
            {"repositoryId": repository_id, "screenId": screen_id}
        )
        return result if result else []

    async def _get_data_tables(self, repository_id: str, screen_id: str) -> List[Dict]:
        """Get data tables for a screen."""
        result = await self.neo4j_client.execute_query(
            GET_DATA_TABLES_FOR_SCREEN,
            {"repositoryId": repository_id, "screenId": screen_id}
        )
        return result if result else []

    async def _get_similar_features(self, repository_id: str, feature_name: str) -> List[str]:
        """Get similar feature names for suggestions."""
        # Full-text search for similar features
        query = """
        CALL db.index.fulltext.queryNodes('menu_fulltext_search', $searchTerm)
        YIELD node, score
        WHERE score > 0.5
        RETURN node.label as name, score
        ORDER BY score DESC
        LIMIT 5
        """
        result = await self.neo4j_client.execute_query(
            query,
            {"searchTerm": feature_name}
        )
        return [r["name"] for r in result] if result else []

    # =============================================================================
    # Formatting Helper Methods
    # =============================================================================

    def _format_screen_context(self, context: Dict) -> str:
        """Format screen context for LLM prompt."""
        return f"""
Screen ID: {context.get('screen_id')}
Flow: {context.get('flow_name')}
Total Fields: {len(context.get('fields', []))}
Total Actions: {len(context.get('actions', []))}
Total Validations: {len(context.get('validations', []))}
Security Rules: {len(context.get('security_rules', []))}
"""

    def _format_fields_for_prompt(self, fields: List[Dict]) -> str:
        """Format fields for LLM prompt."""
        if not fields:
            return "No fields extracted."

        lines = []
        for field in fields:
            line = f"- **{field.get('label') or field.get('name')}**: "
            line += f"Type: {field.get('type', 'text')}, "
            line += f"Required: {field.get('required', False)}"
            if field.get('validationRules'):
                line += f", Validation: {field['validationRules']}"
            if field.get('selectOptions'):
                line += f", Options: {len(field['selectOptions'])} choices"
            if field.get('defaultValue'):
                line += f", Default: {field['defaultValue']}"
            lines.append(line)

        return "\n".join(lines)

    def _format_actions_for_prompt(self, actions: List[Dict]) -> str:
        """Format actions for LLM prompt."""
        if not actions:
            return "No actions extracted."

        lines = []
        for action in actions:
            line = f"- **{action.get('name') or action.get('label')}**: "
            line += f"Event: {action.get('event', 'click')}"
            if action.get('method'):
                line += f", Calls: {action['method']}"
            lines.append(line)

        return "\n".join(lines)

    def _format_validations_for_prompt(self, validations: List[Dict]) -> str:
        """Format validations for LLM prompt."""
        if not validations:
            return "No validation rules extracted."

        lines = []
        for val in validations:
            desc = val.get('description') or val.get('ruleText', 'Validation rule')
            target = val.get('targetName', '')
            lines.append(f"- {desc}" + (f" (on {target})" if target else ""))

        return "\n".join(lines)

    def _format_security_for_prompt(self, security_rules: List[Dict]) -> str:
        """Format security rules for LLM prompt."""
        if not security_rules:
            return "No explicit security rules extracted."

        lines = []
        for rule in security_rules:
            line = f"- {rule.get('annotationType', 'Security')}: "
            if rule.get('roles'):
                line += f"Roles: {', '.join(rule['roles'])}"
            if rule.get('expression'):
                line += f"Expression: {rule['expression']}"
            if rule.get('ruleDescription'):
                line += f" - {rule['ruleDescription']}"
            lines.append(line)

        return "\n".join(lines)

    def _format_errors_for_prompt(self, error_messages: List[Dict]) -> str:
        """Format error messages for LLM prompt."""
        if not error_messages:
            return "No error messages extracted."

        lines = []
        for err in error_messages:
            key = err.get('messageKey', 'error')
            text = err.get('messageText', 'Error occurred')
            lines.append(f"- {key}: \"{text}\"")

        return "\n".join(lines)

    def _format_tables_for_prompt(self, tables: List[Dict]) -> str:
        """Format data tables for LLM prompt."""
        if not tables:
            return "No data tables/grids on this screen."

        lines = []
        for table in tables:
            line = f"- **{table.get('id', 'Table')}**: "
            columns = table.get('columns', [])
            line += f"{len(columns)} columns"
            if columns:
                col_names = [c.get('header', 'Column') for c in columns[:5]]
                line += f" ({', '.join(col_names)}...)" if len(columns) > 5 else f" ({', '.join(col_names)})"
            if table.get('paginated'):
                line += ", Paginated"
            if table.get('selectable'):
                line += ", Selectable"
            lines.append(line)

        return "\n".join(lines)

    def _format_menu_section(self, menu_name: str, sub_sections: List[Dict]) -> str:
        """Format a menu section with all its sub-sections."""
        content = f"# {menu_name}\n\n"

        for section in sub_sections:
            content += section.get("content", "")
            content += "\n\n---\n\n"

        return content

    def _assemble_blueprint_document(self, sections: List[Dict], repository_id: str) -> str:
        """Assemble the final blueprint document."""
        doc = f"""# Business Logic Blueprint

**Repository:** {repository_id}
**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

---

## Table of Contents

"""
        # Build TOC
        for i, section in enumerate(sections, 1):
            menu_name = section.get("menu_name", "Section")
            doc += f"{i}. [{menu_name}](#{menu_name.lower().replace(' ', '-')})\n"

        doc += "\n---\n\n"

        # Add all sections
        for section in sections:
            doc += section.get("content", "")
            doc += "\n\n"

        return doc

    def _assemble_feature_document(
        self,
        overview: str,
        screen_sections: List[Dict],
        feature_name: str
    ) -> str:
        """Assemble a feature-specific blueprint document."""
        doc = f"""# {feature_name} - Business Logic Blueprint

**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

---

{overview}

---

"""
        for section in screen_sections:
            doc += section.get("content", "")
            doc += "\n\n---\n\n"

        return doc

    async def _send_to_llm(self, prompt: str, timeout: float = 120) -> Optional[str]:
        """Send a prompt to the LLM."""
        if not self.llm_session:
            return None

        try:
            message_options = {"prompt": prompt}

            # Get response from LLM session
            response = await asyncio.wait_for(
                self.llm_session.send_message(message_options),
                timeout=timeout
            )

            if hasattr(response, 'content'):
                return response.content
            return str(response)

        except asyncio.TimeoutError:
            logger.error("LLM request timed out")
            return None
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            return None


# =============================================================================
# Service Instance Management
# =============================================================================

_blueprint_service: Optional[BlueprintService] = None


def get_blueprint_service() -> BlueprintService:
    """Get or create the blueprint service singleton."""
    global _blueprint_service
    if _blueprint_service is None:
        from ..mcp_clients.neo4j_client import get_neo4j_client
        neo4j_client = get_neo4j_client()
        _blueprint_service = BlueprintService(neo4j_client)
    return _blueprint_service


def set_blueprint_service(service: BlueprintService):
    """Set the blueprint service (for testing or custom configuration)."""
    global _blueprint_service
    _blueprint_service = service
