"""
Dynamic skill injection for GitHub Copilot conversations.
"""

from typing import Any, Optional

from src.copilot.sdk_client import CopilotSDKClient
from src.core.logging import get_logger
from src.skills.registry import SkillRegistry, get_skill_registry

logger = get_logger(__name__)


class SkillInjector:
    """
    Handles dynamic injection of skills into Copilot conversations.

    Skills are injected by augmenting the system prompt with skill
    definitions, enabling context-aware capabilities.
    """

    def __init__(
        self,
        copilot_client: CopilotSDKClient,
        skill_registry: Optional[SkillRegistry] = None,
    ) -> None:
        """
        Initialize the skill injector.

        Args:
            copilot_client: Copilot SDK client
            skill_registry: Skill registry (uses global if not provided)
        """
        self.copilot_client = copilot_client
        self.registry = skill_registry or get_skill_registry()
        self._registered_skills: set[str] = set()

    def register_skills(self, skill_names: Optional[list[str]] = None) -> None:
        """
        Register skills with the Copilot client.

        Args:
            skill_names: Skills to register (all available if None)
        """
        names = skill_names or self.registry.list_available()

        for name in names:
            prompt = self.registry.get_prompt(name)
            if prompt:
                self.copilot_client.register_skill_prompt(name, prompt)
                self._registered_skills.add(name)

        logger.info(
            "Registered skills with Copilot",
            count=len(self._registered_skills),
        )

    def select_and_register(self, task: str) -> list[str]:
        """
        Select appropriate skills for a task and register them.

        Args:
            task: Task description

        Returns:
            List of selected skill names
        """
        skills = self.registry.select_skills_for_task(task)

        for name in skills:
            if name not in self._registered_skills:
                prompt = self.registry.get_prompt(name)
                if prompt:
                    self.copilot_client.register_skill_prompt(name, prompt)
                    self._registered_skills.add(name)

        return skills

    async def create_conversation_with_skills(
        self,
        base_prompt: str,
        task: str,
        additional_skills: Optional[list[str]] = None,
    ) -> str:
        """
        Create a conversation with automatically selected skills.

        Args:
            base_prompt: Base system prompt
            task: Task description for skill selection
            additional_skills: Extra skills to include

        Returns:
            Conversation ID
        """
        # Auto-select skills based on task
        selected_skills = self.select_and_register(task)

        # Add any additional skills
        if additional_skills:
            for skill in additional_skills:
                if skill not in selected_skills:
                    selected_skills.append(skill)
                    if skill not in self._registered_skills:
                        prompt = self.registry.get_prompt(skill)
                        if prompt:
                            self.copilot_client.register_skill_prompt(skill, prompt)
                            self._registered_skills.add(skill)

        # Create conversation
        conversation_id = await self.copilot_client.create_conversation(
            system_prompt=base_prompt,
            skills=selected_skills,
        )

        logger.info(
            "Created skill-enhanced conversation",
            conversation_id=conversation_id,
            skills=selected_skills,
        )

        return conversation_id

    async def inject_skills_into_conversation(
        self,
        conversation_id: str,
        skill_names: list[str],
    ) -> None:
        """
        Inject additional skills into an existing conversation.

        Args:
            conversation_id: Conversation ID
            skill_names: Skills to inject
        """
        # Ensure skills are registered
        for name in skill_names:
            if name not in self._registered_skills:
                prompt = self.registry.get_prompt(name)
                if prompt:
                    self.copilot_client.register_skill_prompt(name, prompt)
                    self._registered_skills.add(name)

        # Inject into conversation
        await self.copilot_client.inject_skills(conversation_id, skill_names)

    def get_required_tools_for_skills(
        self,
        skill_names: list[str],
    ) -> list[str]:
        """
        Get the tools required by a set of skills.

        Args:
            skill_names: Skill names

        Returns:
            List of required tool names
        """
        return self.registry.get_required_tools(skill_names)

    def get_combined_prompt_for_skills(
        self,
        skill_names: list[str],
    ) -> str:
        """
        Get the combined prompt text for multiple skills.

        Args:
            skill_names: Skill names

        Returns:
            Combined prompt text
        """
        return self.registry.get_combined_prompt(skill_names)

    def get_registered_skills(self) -> list[str]:
        """Get list of registered skill names."""
        return list(self._registered_skills)


class SkillRouter:
    """
    Routes tasks to appropriate skills based on analysis.
    """

    def __init__(
        self,
        skill_registry: Optional[SkillRegistry] = None,
    ) -> None:
        """
        Initialize the skill router.

        Args:
            skill_registry: Skill registry (uses global if not provided)
        """
        self.registry = skill_registry or get_skill_registry()

        # Keywords for skill routing
        self._keyword_mappings: dict[str, list[str]] = {
            "brd": ["brd-generator", "codebase-analyzer", "verification"],
            "business requirement": ["brd-generator", "codebase-analyzer", "verification"],
            "epic": ["epic-generator", "codebase-analyzer", "architecture-mapper", "acceptance-criteria", "verification"],
            "backlog": ["backlog-generator", "codebase-analyzer", "acceptance-criteria", "verification"],
            "user stor": ["backlog-generator", "acceptance-criteria", "verification"],
            "analyze": ["codebase-analyzer", "architecture-mapper"],
            "understand": ["codebase-analyzer", "architecture-mapper"],
            "architecture": ["architecture-mapper", "codebase-analyzer"],
            "verify": ["verification"],
            "validate": ["verification"],
            "acceptance": ["acceptance-criteria"],
        }

    def route(self, task: str) -> dict[str, Any]:
        """
        Route a task to appropriate skills and tools.

        Args:
            task: Task description

        Returns:
            Dictionary with routing information
        """
        task_lower = task.lower()

        # Find matching keywords
        matched_keywords = []
        selected_skills = set(["senior-engineer-analysis"])  # Always include

        for keyword, skills in self._keyword_mappings.items():
            if keyword in task_lower:
                matched_keywords.append(keyword)
                selected_skills.update(skills)

        # Get required tools
        skill_list = list(selected_skills)
        required_tools = self.registry.get_required_tools(skill_list)

        return {
            "task": task,
            "matched_keywords": matched_keywords,
            "skills": skill_list,
            "required_tools": required_tools,
            "skill_count": len(skill_list),
        }

    def get_document_type(self, task: str) -> Optional[str]:
        """
        Determine the document type from the task.

        Args:
            task: Task description

        Returns:
            Document type (brd, epic, backlog) or None
        """
        task_lower = task.lower()

        if "brd" in task_lower or "business requirement" in task_lower:
            return "brd"
        elif "epic" in task_lower:
            return "epic"
        elif "backlog" in task_lower or "user stor" in task_lower:
            return "backlog"

        return None

    def is_document_generation(self, task: str) -> bool:
        """Check if task is a document generation task."""
        return self.get_document_type(task) is not None

    def is_analysis_task(self, task: str) -> bool:
        """Check if task is an analysis task."""
        task_lower = task.lower()
        analysis_keywords = ["analyze", "understand", "explore", "examine", "investigate"]
        return any(kw in task_lower for kw in analysis_keywords)
