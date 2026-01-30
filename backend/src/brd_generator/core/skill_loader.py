"""Skill Loader for Copilot SDK.

Loads skill definitions from YAML files and registers them with the
Copilot SDK session. Skills are matched dynamically based on user requests.

Architecture:
1. Skills are defined in YAML files (skills/*.yaml)
2. Each skill has triggers, MCP servers, tools, and instructions
3. Copilot SDK matches user requests to skills based on triggers
4. When a skill is matched, its MCP servers and tools become available
5. The LLM uses the skill's instructions to complete the task
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SkillTool:
    """Tool definition within a skill."""
    name: str
    description: str


@dataclass
class SkillDefinition:
    """Parsed skill definition from YAML."""
    name: str
    description: str
    triggers: list[str]
    mcp_servers: list[str]
    tools: list[SkillTool]
    instructions: str

    def matches_request(self, request: str) -> bool:
        """Check if this skill matches a user request (case-insensitive)."""
        request_lower = request.lower()
        # Check if any trigger words are in the request
        for trigger in self.triggers:
            trigger_lower = trigger.lower()
            # Match if trigger is contained in request
            if trigger_lower in request_lower:
                return True
            # Also match individual words from trigger
            trigger_words = trigger_lower.split()
            if len(trigger_words) > 1:
                # Check if all words from trigger are in request
                if all(word in request_lower for word in trigger_words):
                    return True
        return False

    def to_copilot_format(self) -> dict[str, Any]:
        """Convert to Copilot SDK skill format."""
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "mcp_servers": self.mcp_servers,
            "tools": [{"name": t.name, "description": t.description} for t in self.tools],
            "instructions": self.instructions,
        }


class SkillLoader:
    """
    Loads and manages skills for Copilot SDK.

    Skills enable the LLM to:
    1. Access specific MCP servers based on the task
    2. Use task-specific tools
    3. Follow structured instructions

    The Copilot SDK dynamically matches requests to skills and
    makes the appropriate tools available.
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        """
        Initialize the skill loader.

        Args:
            skills_dir: Directory containing skill YAML files.
                       Defaults to the skills/ directory in this package.
        """
        if skills_dir:
            self.skills_dir = skills_dir
        else:
            # Default to package skills directory
            self.skills_dir = Path(__file__).parent.parent / "skills"

        self.skills: dict[str, SkillDefinition] = {}
        self._loaded = False

    def load_skills(self) -> dict[str, SkillDefinition]:
        """
        Load all skill definitions from YAML files.

        Returns:
            Dictionary of skill name to SkillDefinition.
        """
        if self._loaded:
            return self.skills

        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return {}

        for yaml_file in self.skills_dir.glob("*.yaml"):
            try:
                skill = self._load_skill_file(yaml_file)
                if skill:
                    self.skills[skill.name] = skill
                    logger.info(f"Loaded skill: {skill.name} ({len(skill.triggers)} triggers)")
            except Exception as e:
                logger.error(f"Failed to load skill {yaml_file}: {e}")

        self._loaded = True
        logger.info(f"Loaded {len(self.skills)} skills from {self.skills_dir}")
        return self.skills

    def _load_skill_file(self, path: Path) -> Optional[SkillDefinition]:
        """Load a single skill from a YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)

        if not data:
            return None

        # Parse tools
        tools = []
        for tool_data in data.get("tools", []):
            tools.append(SkillTool(
                name=tool_data.get("name", ""),
                description=tool_data.get("description", ""),
            ))

        return SkillDefinition(
            name=data.get("name", path.stem),
            description=data.get("description", ""),
            triggers=data.get("triggers", []),
            mcp_servers=data.get("mcp_servers", []),
            tools=tools,
            instructions=data.get("instructions", ""),
        )

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """Get a skill by name."""
        if not self._loaded:
            self.load_skills()
        return self.skills.get(name)

    def match_skill(self, request: str) -> Optional[SkillDefinition]:
        """
        Find the best matching skill for a request.

        This is used when the Copilot SDK doesn't do automatic matching,
        or when we want to pre-select a skill.

        Args:
            request: User's request text.

        Returns:
            Best matching SkillDefinition or None.
        """
        if not self._loaded:
            self.load_skills()

        for skill in self.skills.values():
            if skill.matches_request(request):
                logger.info(f"Matched skill '{skill.name}' for request")
                return skill

        return None

    def get_skills_for_session(self) -> list[dict[str, Any]]:
        """
        Get all skills in Copilot SDK session format.

        This can be passed to the session configuration.
        """
        if not self._loaded:
            self.load_skills()

        return [skill.to_copilot_format() for skill in self.skills.values()]

    def get_mcp_servers_for_skill(self, skill_name: str) -> list[str]:
        """Get MCP server names needed for a skill."""
        skill = self.get_skill(skill_name)
        if skill:
            return skill.mcp_servers
        return []

    def get_instructions_for_skill(self, skill_name: str) -> str:
        """Get instructions for a skill."""
        skill = self.get_skill(skill_name)
        if skill:
            return skill.instructions
        return ""

    def build_session_config(
        self,
        mcp_servers_config: dict[str, Any],
        skill_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Build session configuration with skills.

        Args:
            mcp_servers_config: Base MCP servers configuration.
            skill_name: Optional specific skill to activate.

        Returns:
            Session configuration dictionary.
        """
        config = {
            "mcp_servers": mcp_servers_config,
            "skills": self.get_skills_for_session(),
        }

        # If a specific skill is requested, include its instructions
        if skill_name:
            skill = self.get_skill(skill_name)
            if skill:
                config["system_instructions"] = skill.instructions
                logger.info(f"Activated skill: {skill_name}")

        return config
