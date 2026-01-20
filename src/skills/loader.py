"""
Skill loader - reads YAML skill definitions and makes them available.
"""

from pathlib import Path
from typing import Any, Optional

import yaml

from src.core.config import settings
from src.core.exceptions import SkillNotFoundError
from src.core.logging import get_logger
from src.skills.base import SkillDefinition

logger = get_logger(__name__)


class SkillLoader:
    """
    Loads and manages GitHub Copilot Skills from YAML files.

    Skills are loaded lazily on first access and cached for performance.
    """

    def __init__(
        self,
        skills_directory: Optional[str] = None,
    ) -> None:
        """
        Initialize the skill loader.

        Args:
            skills_directory: Path to directory containing skill YAML files
        """
        self.skills_dir = Path(skills_directory or settings.skills_directory)
        self._loaded_skills: dict[str, SkillDefinition] = {}
        self._load_attempted: set[str] = set()

    def _yaml_path(self, skill_name: str) -> Path:
        """Get the YAML file path for a skill."""
        return self.skills_dir / f"{skill_name}.yaml"

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """
        Load and parse a YAML file.

        Args:
            path: Path to YAML file

        Returns:
            Parsed YAML content
        """
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_skill(self, skill_name: str) -> SkillDefinition:
        """
        Load a single skill by name.

        Args:
            skill_name: Name of the skill (without .yaml extension)

        Returns:
            Loaded SkillDefinition

        Raises:
            SkillNotFoundError: If skill file doesn't exist
        """
        # Check cache first
        if skill_name in self._loaded_skills:
            return self._loaded_skills[skill_name]

        yaml_path = self._yaml_path(skill_name)

        if not yaml_path.exists():
            self._load_attempted.add(skill_name)
            raise SkillNotFoundError(skill_name)

        try:
            data = self._load_yaml(yaml_path)

            skill = SkillDefinition(
                name=data["name"],
                version=data["version"],
                description=data["description"],
                prompt=data["prompt"],
                required_tools=data.get("required_tools", []),
                verification_rules=data.get("verification_rules", []),
                examples=data.get("examples", []),
                metadata=data.get("metadata", {}),
            )

            # Validate
            errors = skill.validate()
            if errors:
                logger.warning(
                    "Skill validation warnings",
                    skill=skill_name,
                    errors=errors,
                )

            # Cache the skill
            self._loaded_skills[skill_name] = skill
            self._load_attempted.add(skill_name)

            logger.debug(
                "Loaded skill",
                skill=skill_name,
                version=skill.version,
            )

            return skill

        except yaml.YAMLError as e:
            logger.error(
                "Failed to parse skill YAML",
                skill=skill_name,
                error=str(e),
            )
            raise SkillNotFoundError(skill_name) from e

        except KeyError as e:
            logger.error(
                "Missing required field in skill YAML",
                skill=skill_name,
                field=str(e),
            )
            raise SkillNotFoundError(skill_name) from e

    def load_all_skills(self) -> dict[str, SkillDefinition]:
        """
        Load all skills from the skills directory.

        Returns:
            Dictionary mapping skill names to definitions
        """
        if not self.skills_dir.exists():
            logger.warning("Skills directory not found", path=str(self.skills_dir))
            return {}

        for yaml_file in self.skills_dir.glob("*.yaml"):
            skill_name = yaml_file.stem
            try:
                self.load_skill(skill_name)
            except SkillNotFoundError:
                continue  # Already logged

        logger.info(
            "Loaded all skills",
            count=len(self._loaded_skills),
        )

        return self._loaded_skills.copy()

    def get_skill(self, skill_name: str) -> Optional[SkillDefinition]:
        """
        Get a skill, loading it if necessary.

        Args:
            skill_name: Name of the skill

        Returns:
            SkillDefinition or None if not found
        """
        try:
            return self.load_skill(skill_name)
        except SkillNotFoundError:
            return None

    def get_skill_prompt(self, skill_name: str) -> str:
        """
        Get the prompt text for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Skill prompt text

        Raises:
            SkillNotFoundError: If skill not found
        """
        skill = self.load_skill(skill_name)
        return skill.prompt

    def get_required_tools(self, skill_names: list[str]) -> list[str]:
        """
        Get all required tools for a list of skills.

        Args:
            skill_names: List of skill names

        Returns:
            Deduplicated list of required tool names
        """
        tools: set[str] = set()

        for skill_name in skill_names:
            skill = self.get_skill(skill_name)
            if skill:
                tools.update(skill.required_tools)

        return list(tools)

    def get_loaded_skills(self) -> list[str]:
        """Get list of currently loaded skill names."""
        return list(self._loaded_skills.keys())

    def get_available_skills(self) -> list[str]:
        """
        Get list of all available skill names (from YAML files).

        Returns:
            List of skill names
        """
        if not self.skills_dir.exists():
            return []

        return [f.stem for f in self.skills_dir.glob("*.yaml")]

    def reload_skill(self, skill_name: str) -> SkillDefinition:
        """
        Force reload a skill from disk.

        Args:
            skill_name: Name of the skill

        Returns:
            Reloaded SkillDefinition
        """
        # Clear from cache
        self._loaded_skills.pop(skill_name, None)
        self._load_attempted.discard(skill_name)

        # Reload
        return self.load_skill(skill_name)

    def reload_all(self) -> dict[str, SkillDefinition]:
        """
        Force reload all skills from disk.

        Returns:
            Dictionary of all skills
        """
        self._loaded_skills.clear()
        self._load_attempted.clear()

        return self.load_all_skills()

    def skill_exists(self, skill_name: str) -> bool:
        """
        Check if a skill exists (either loaded or on disk).

        Args:
            skill_name: Name of the skill

        Returns:
            True if skill exists
        """
        if skill_name in self._loaded_skills:
            return True

        return self._yaml_path(skill_name).exists()
