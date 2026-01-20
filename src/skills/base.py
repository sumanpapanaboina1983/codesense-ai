"""
Base skill class and skill definition data structures.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SkillDefinition:
    """
    Definition of a GitHub Copilot Skill loaded from YAML.

    Skills are prompt templates that augment Copilot's capabilities
    for specific tasks like codebase analysis or document generation.
    """

    name: str
    version: str
    description: str
    prompt: str
    required_tools: list[str] = field(default_factory=list)
    verification_rules: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_count(self) -> int:
        """Number of required tools."""
        return len(self.required_tools)

    @property
    def has_verification_rules(self) -> bool:
        """Check if skill has verification rules."""
        return len(self.verification_rules) > 0

    def get_prompt_with_context(self, context: Optional[dict[str, Any]] = None) -> str:
        """
        Get the prompt with optional context variables substituted.

        Args:
            context: Dictionary of context variables

        Returns:
            Formatted prompt string
        """
        if not context:
            return self.prompt

        prompt = self.prompt
        for key, value in context.items():
            prompt = prompt.replace(f"{{{key}}}", str(value))

        return prompt

    def validate(self) -> list[str]:
        """
        Validate the skill definition.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.name:
            errors.append("Skill name is required")

        if not self.version:
            errors.append("Skill version is required")

        if not self.prompt:
            errors.append("Skill prompt is required")

        if len(self.prompt) < 50:
            errors.append("Skill prompt is too short (min 50 characters)")

        return errors


@dataclass
class SkillCategory:
    """Category grouping for skills."""

    name: str
    description: str
    skills: list[str] = field(default_factory=list)


# Predefined skill categories
SKILL_CATEGORIES = {
    "analysis": SkillCategory(
        name="analysis",
        description="Skills for analyzing codebase structure and patterns",
        skills=["codebase-analyzer", "architecture-mapper"],
    ),
    "document": SkillCategory(
        name="document",
        description="Skills for generating documentation artifacts",
        skills=["brd-generator", "epic-generator", "backlog-generator"],
    ),
    "verification": SkillCategory(
        name="verification",
        description="Skills for verifying and validating generated content",
        skills=["verification", "acceptance-criteria"],
    ),
    "reasoning": SkillCategory(
        name="reasoning",
        description="Skills for advanced reasoning and problem solving",
        skills=["senior-engineer-analysis"],
    ),
}


def get_skills_by_category(category: str) -> list[str]:
    """
    Get skill names by category.

    Args:
        category: Category name

    Returns:
        List of skill names in the category
    """
    if category in SKILL_CATEGORIES:
        return SKILL_CATEGORIES[category].skills
    return []


def get_all_categories() -> list[str]:
    """Get all category names."""
    return list(SKILL_CATEGORIES.keys())
