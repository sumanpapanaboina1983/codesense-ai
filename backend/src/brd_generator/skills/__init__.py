"""BRD Generator Skills for Copilot SDK.

Skills are defined in YAML files and loaded dynamically by the Copilot SDK.
Each skill:
- Has trigger patterns for automatic matching
- References MCP servers for tool access
- Contains instructions for the LLM

Available Skills:
- generate-brd: Generate a Business Requirements Document
- verify-brd: Verify BRD claims against codebase
- generate-epics: Generate Epics from approved BRD
- generate-stories: Generate User Stories from Epics
"""

from pathlib import Path

SKILLS_DIR = Path(__file__).parent

SKILL_FILES = [
    "generate-brd.yaml",
    "verify-brd.yaml",
    "generate-epics.yaml",
    "generate-stories.yaml",
]


def get_skills_directory() -> Path:
    """Get the path to the skills directory."""
    return SKILLS_DIR


def list_available_skills() -> list[str]:
    """List available skill names."""
    return [f.replace(".yaml", "") for f in SKILL_FILES]
