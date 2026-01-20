"""
Skill registry - manages skill discovery, registration, and selection.
"""

from typing import Any, Optional

from src.core.constants import DEFAULT_SKILLS, SKILL_MAPPINGS
from src.core.logging import get_logger
from src.skills.base import SkillDefinition, get_skills_by_category
from src.skills.loader import SkillLoader

logger = get_logger(__name__)


class SkillRegistry:
    """
    Central registry for managing GitHub Copilot Skills.

    Provides skill discovery, selection, and composition capabilities.
    """

    def __init__(
        self,
        skill_loader: Optional[SkillLoader] = None,
    ) -> None:
        """
        Initialize the skill registry.

        Args:
            skill_loader: SkillLoader instance (creates one if not provided)
        """
        self.loader = skill_loader or SkillLoader()
        self._initialized = False

    def initialize(self) -> None:
        """
        Initialize the registry by loading all available skills.
        """
        if self._initialized:
            return

        self.loader.load_all_skills()
        self._initialized = True

        logger.info(
            "Skill registry initialized",
            available_skills=len(self.loader.get_loaded_skills()),
        )

    def get_skill(self, skill_name: str) -> Optional[SkillDefinition]:
        """
        Get a skill by name.

        Args:
            skill_name: Name of the skill

        Returns:
            SkillDefinition or None
        """
        return self.loader.get_skill(skill_name)

    def get_skills(self, skill_names: list[str]) -> list[SkillDefinition]:
        """
        Get multiple skills by name.

        Args:
            skill_names: List of skill names

        Returns:
            List of found SkillDefinitions
        """
        skills = []
        for name in skill_names:
            skill = self.get_skill(name)
            if skill:
                skills.append(skill)
        return skills

    def get_prompt(self, skill_name: str) -> Optional[str]:
        """
        Get the prompt for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Skill prompt or None
        """
        skill = self.get_skill(skill_name)
        return skill.prompt if skill else None

    def get_combined_prompt(
        self,
        skill_names: list[str],
        separator: str = "\n\n---\n\n",
    ) -> str:
        """
        Get combined prompts from multiple skills.

        Args:
            skill_names: List of skill names
            separator: Text to insert between skill prompts

        Returns:
            Combined prompt string
        """
        prompts = []
        for name in skill_names:
            prompt = self.get_prompt(name)
            if prompt:
                prompts.append(f"## Skill: {name}\n\n{prompt}")

        return separator.join(prompts)

    def get_required_tools(self, skill_names: list[str]) -> list[str]:
        """
        Get all required tools for a list of skills.

        Args:
            skill_names: List of skill names

        Returns:
            Deduplicated list of required tools
        """
        return self.loader.get_required_tools(skill_names)

    def select_skills_for_task(self, task: str) -> list[str]:
        """
        Analyze a task and select appropriate skills.

        Args:
            task: Task description

        Returns:
            List of recommended skill names
        """
        task_lower = task.lower()
        skills = list(DEFAULT_SKILLS)  # Always include defaults

        # Check for document generation tasks
        if "brd" in task_lower or "business requirement" in task_lower:
            skills.extend(SKILL_MAPPINGS.get("brd", []))

        elif "epic" in task_lower:
            skills.extend(SKILL_MAPPINGS.get("epic", []))

        elif "backlog" in task_lower or "user stor" in task_lower:
            skills.extend(SKILL_MAPPINGS.get("backlog", []))

        # Check for analysis tasks
        elif "analyze" in task_lower or "understand" in task_lower:
            skills.extend(SKILL_MAPPINGS.get("analyze", []))

        # Check for architecture tasks
        elif "architecture" in task_lower or "structure" in task_lower:
            skills.extend(["codebase-analyzer", "architecture-mapper"])

        # Check for verification tasks
        elif "verify" in task_lower or "validate" in task_lower:
            skills.extend(["verification"])

        # Deduplicate while preserving order
        seen = set()
        unique_skills = []
        for skill in skills:
            if skill not in seen:
                seen.add(skill)
                unique_skills.append(skill)

        logger.debug(
            "Selected skills for task",
            task=task[:50],
            skills=unique_skills,
        )

        return unique_skills

    def get_skills_by_category(self, category: str) -> list[str]:
        """
        Get skills by category.

        Args:
            category: Category name

        Returns:
            List of skill names in the category
        """
        return get_skills_by_category(category)

    def list_available(self) -> list[str]:
        """List all available skill names."""
        return self.loader.get_available_skills()

    def list_loaded(self) -> list[str]:
        """List all currently loaded skill names."""
        return self.loader.get_loaded_skills()

    def get_skill_info(self, skill_name: str) -> Optional[dict[str, Any]]:
        """
        Get detailed information about a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Dictionary with skill info or None
        """
        skill = self.get_skill(skill_name)
        if not skill:
            return None

        return {
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
            "required_tools": skill.required_tools,
            "verification_rules": skill.verification_rules,
            "has_examples": len(skill.examples) > 0,
        }

    def validate_skill_combination(
        self,
        skill_names: list[str],
    ) -> tuple[bool, list[str]]:
        """
        Validate a combination of skills.

        Args:
            skill_names: List of skill names to validate

        Returns:
            Tuple of (is_valid, list of issues)
        """
        issues = []

        for name in skill_names:
            if not self.loader.skill_exists(name):
                issues.append(f"Skill not found: {name}")

        # Check for conflicting skills (if any defined)
        # This is a placeholder for future conflict detection

        return len(issues) == 0, issues


# Singleton instance
_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Get the global skill registry instance."""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _registry.initialize()
    return _registry
