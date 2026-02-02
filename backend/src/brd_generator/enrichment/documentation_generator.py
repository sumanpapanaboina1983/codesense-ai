"""Documentation Generator.

Generates documentation for undocumented code entities using LLM.
Supports multiple documentation styles:
- JSDoc (JavaScript/TypeScript)
- JavaDoc (Java)
- Docstrings (Python)
- XML Documentation (C#)
- GoDoc (Go)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


class DocumentationStyle(str, Enum):
    """Supported documentation styles."""
    JSDOC = "jsdoc"
    JAVADOC = "javadoc"
    DOCSTRING = "docstring"
    XMLDOC = "xmldoc"
    GODOC = "godoc"


@dataclass
class EntityContext:
    """Context information for an entity to document."""
    entity_id: str
    entity_name: str
    file_path: str
    language: str
    kind: str  # Function, Method, Class, etc.
    signature: Optional[str] = None
    parameters: list[dict[str, str]] = None
    return_type: Optional[str] = None
    source_code: Optional[str] = None
    parent_class: Optional[str] = None
    dependencies: list[str] = None
    start_line: int = 0
    end_line: int = 0

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = []
        if self.dependencies is None:
            self.dependencies = []


@dataclass
class GeneratedDocumentation:
    """Generated documentation for an entity."""
    entity_id: str
    entity_name: str
    file_path: str
    documentation: str
    insert_line: int
    insert_column: int
    style: DocumentationStyle


class DocumentationGenerator:
    """Generates documentation for code entities using LLM."""

    # Documentation templates by style
    TEMPLATES = {
        DocumentationStyle.JSDOC: {
            "function": '''/**
 * {description}
 *{params}
 * @returns {{{return_type}}} {return_description}
 *{throws}
 * @example
 * {example}
 */''',
            "class": '''/**
 * {description}
 *{type_params}
 * @class
 * @example
 * {example}
 */''',
        },
        DocumentationStyle.JAVADOC: {
            "method": '''/**
 * {description}
 *{params}
 * @return {return_description}
 *{throws}
 */''',
            "class": '''/**
 * {description}
 *{type_params}
 * @author Generated
 * @version 1.0
 */''',
        },
        DocumentationStyle.DOCSTRING: {
            "function": '''"""
{description}

Args:
{params}

Returns:
    {return_type}: {return_description}

Raises:
{throws}

Example:
    >>> {example}
"""''',
            "class": '''"""
{description}

Attributes:
{attributes}

Example:
    >>> {example}
"""''',
        },
        DocumentationStyle.XMLDOC: {
            "method": '''/// <summary>
/// {description}
/// </summary>
{params}
/// <returns>{return_description}</returns>
{throws}''',
            "class": '''/// <summary>
/// {description}
/// </summary>
{type_params}''',
        },
        DocumentationStyle.GODOC: {
            "function": '''// {name} {description}
//
// Parameters:
{params}
//
// Returns:
//   {return_description}''',
        },
    }

    # LLM prompts for documentation generation
    DOC_GENERATION_PROMPT = '''Generate documentation for the following {language} {kind}:

Name: {name}
Signature: {signature}
Source Code:
```{language}
{source_code}
```

Context:
- Parent class/module: {parent}
- Dependencies used: {dependencies}

Generate a clear, concise documentation that includes:
1. A brief description of what this {kind} does
2. Parameter descriptions (if applicable)
3. Return value description (if applicable)
4. Any exceptions/errors that might be thrown
5. A brief usage example

Format the documentation in {style} style.

Documentation:'''

    def __init__(self, copilot_session: Any = None):
        """Initialize the documentation generator.

        Args:
            copilot_session: Optional Copilot session for LLM-based generation.
        """
        self.copilot_session = copilot_session

    async def generate_documentation(
        self,
        entity: EntityContext,
        style: DocumentationStyle = DocumentationStyle.JSDOC,
        include_examples: bool = True,
        include_params: bool = True,
        include_returns: bool = True,
        include_throws: bool = True,
    ) -> GeneratedDocumentation:
        """Generate documentation for a single entity.

        Args:
            entity: Context information about the entity to document.
            style: Documentation style to use.
            include_examples: Whether to include usage examples.
            include_params: Whether to include parameter descriptions.
            include_returns: Whether to include return value description.
            include_throws: Whether to include exception information.

        Returns:
            GeneratedDocumentation with the generated content.
        """
        logger.info(f"Generating {style.value} documentation for {entity.entity_name}")

        if self.copilot_session:
            # Use LLM for intelligent documentation generation
            documentation = await self._generate_with_llm(
                entity, style, include_examples, include_params, include_returns, include_throws
            )
        else:
            # Fall back to template-based generation
            documentation = self._generate_from_template(
                entity, style, include_examples, include_params, include_returns, include_throws
            )

        return GeneratedDocumentation(
            entity_id=entity.entity_id,
            entity_name=entity.entity_name,
            file_path=entity.file_path,
            documentation=documentation,
            insert_line=entity.start_line,
            insert_column=0,
            style=style,
        )

    async def generate_batch(
        self,
        entities: list[EntityContext],
        style: DocumentationStyle = DocumentationStyle.JSDOC,
        **options,
    ) -> list[GeneratedDocumentation]:
        """Generate documentation for multiple entities.

        Args:
            entities: List of entity contexts to document.
            style: Documentation style to use.
            **options: Additional options passed to generate_documentation.

        Returns:
            List of GeneratedDocumentation objects.
        """
        results = []
        for entity in entities:
            try:
                doc = await self.generate_documentation(entity, style, **options)
                results.append(doc)
            except Exception as e:
                logger.error(f"Failed to generate documentation for {entity.entity_name}: {e}")
                # Continue with other entities
        return results

    async def _generate_with_llm(
        self,
        entity: EntityContext,
        style: DocumentationStyle,
        include_examples: bool,
        include_params: bool,
        include_returns: bool,
        include_throws: bool,
    ) -> str:
        """Generate documentation using LLM."""
        prompt = self.DOC_GENERATION_PROMPT.format(
            language=entity.language,
            kind=entity.kind.lower(),
            name=entity.entity_name,
            signature=entity.signature or entity.entity_name,
            source_code=entity.source_code or "// Source code not available",
            parent=entity.parent_class or "None",
            dependencies=", ".join(entity.dependencies) if entity.dependencies else "None",
            style=style.value,
        )

        try:
            response = await self.copilot_session.send_message(prompt)
            return self._extract_documentation(response, style)
        except Exception as e:
            logger.warning(f"LLM generation failed, falling back to template: {e}")
            return self._generate_from_template(
                entity, style, include_examples, include_params, include_returns, include_throws
            )

    def _generate_from_template(
        self,
        entity: EntityContext,
        style: DocumentationStyle,
        include_examples: bool,
        include_params: bool,
        include_returns: bool,
        include_throws: bool,
    ) -> str:
        """Generate documentation from templates."""
        template_kind = "function" if entity.kind in ["Function", "Method"] else "class"
        templates = self.TEMPLATES.get(style, self.TEMPLATES[DocumentationStyle.JSDOC])
        template = templates.get(template_kind, templates.get("function", ""))

        # Build parameter documentation
        params_doc = ""
        if include_params and entity.parameters:
            params_doc = self._format_params(entity.parameters, style)

        # Build return documentation
        return_type = entity.return_type or "void"
        return_desc = f"The result of {entity.entity_name}"

        # Build throws documentation
        throws_doc = ""
        if include_throws:
            throws_doc = self._format_throws(style)

        # Build example
        example = f"{entity.entity_name}()" if include_examples else ""

        # Format template
        doc = template.format(
            description=f"Performs the {entity.entity_name} operation.",
            params=params_doc,
            return_type=return_type,
            return_description=return_desc,
            throws=throws_doc,
            example=example,
            type_params="",
            attributes="",
            name=entity.entity_name,
        )

        return doc.strip()

    def _format_params(self, params: list[dict[str, str]], style: DocumentationStyle) -> str:
        """Format parameters for the given documentation style."""
        if not params:
            return ""

        lines = []
        for param in params:
            name = param.get("name", "param")
            ptype = param.get("type", "any")
            desc = param.get("description", f"The {name} parameter")

            if style == DocumentationStyle.JSDOC:
                lines.append(f" * @param {{{ptype}}} {name} - {desc}")
            elif style == DocumentationStyle.JAVADOC:
                lines.append(f" * @param {name} {desc}")
            elif style == DocumentationStyle.DOCSTRING:
                lines.append(f"    {name} ({ptype}): {desc}")
            elif style == DocumentationStyle.XMLDOC:
                lines.append(f'/// <param name="{name}">{desc}</param>')
            elif style == DocumentationStyle.GODOC:
                lines.append(f"//   {name}: {desc}")

        return "\n".join(lines)

    def _format_throws(self, style: DocumentationStyle) -> str:
        """Format throws/raises documentation."""
        if style == DocumentationStyle.JSDOC:
            return " * @throws {Error} If an error occurs"
        elif style == DocumentationStyle.JAVADOC:
            return " * @throws Exception if an error occurs"
        elif style == DocumentationStyle.DOCSTRING:
            return "    Exception: If an error occurs"
        elif style == DocumentationStyle.XMLDOC:
            return '/// <exception cref="Exception">If an error occurs</exception>'
        return ""

    def _extract_documentation(self, response: str, style: DocumentationStyle) -> str:
        """Extract documentation from LLM response."""
        # Look for documentation block markers
        if style == DocumentationStyle.JSDOC or style == DocumentationStyle.JAVADOC:
            if "/**" in response and "*/" in response:
                start = response.index("/**")
                end = response.index("*/") + 2
                return response[start:end]
        elif style == DocumentationStyle.DOCSTRING:
            if '"""' in response:
                parts = response.split('"""')
                if len(parts) >= 3:
                    return '"""' + parts[1] + '"""'
        elif style == DocumentationStyle.XMLDOC:
            if "/// <summary>" in response:
                lines = []
                in_doc = False
                for line in response.split("\n"):
                    if "/// <summary>" in line:
                        in_doc = True
                    if in_doc:
                        lines.append(line)
                        if "</returns>" in line or "</summary>" in line:
                            if not any(tag in line for tag in ["<param", "<returns", "<exception"]):
                                break
                return "\n".join(lines)

        # Fall back to returning the whole response
        return response.strip()


# Factory function
def create_documentation_generator(copilot_session: Any = None) -> DocumentationGenerator:
    """Create a documentation generator instance.

    Args:
        copilot_session: Optional Copilot session for LLM-based generation.

    Returns:
        DocumentationGenerator instance.
    """
    return DocumentationGenerator(copilot_session)
