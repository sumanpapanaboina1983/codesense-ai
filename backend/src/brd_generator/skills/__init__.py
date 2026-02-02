"""BRD Generator Skills for Copilot SDK.

Skills are defined in .md files with YAML frontmatter and loaded by the Copilot SDK.
The actual skill files are in .github/skills/ directory (not this package).

Skill Format (SKILL.md):
---
name: skill-name
description: What the skill does
---
# Skill Instructions
Detailed instructions in markdown...

Available Skills (in .github/skills/):
- generate-brd.md: Generate a Business Requirements Document
- reflect.md: Pause and reason about current state
- plan-task.md: Decompose complex tasks into steps
- generate-epics-from-brd.md: Generate Epics from approved BRD
- generate-backlogs-from-epics.md: Generate backlogs from Epics
- create-jira-issues.md: Create Jira issues from backlogs

Note: This package is kept for backwards compatibility.
The actual skills directory is configured via:
- MCP_SKILLS_DIR environment variable
- .github/skills/ directory in the project
- ~/.github/skills/ for user-level skills
"""

import os
from pathlib import Path


def get_skills_directory() -> Path:
    """
    Get the path to the skills directory.

    Checks in order:
    1. MCP_SKILLS_DIR environment variable
    2. .github/skills in the project root
    3. User home .github/skills

    Returns:
        Path to the skills directory
    """
    # Check environment variable first
    env_skills = os.getenv("MCP_SKILLS_DIR")
    if env_skills:
        path = Path(env_skills)
        if path.exists():
            return path

    # Check project .github/skills
    project_skills = Path(__file__).parent.parent.parent.parent / ".github" / "skills"
    if project_skills.exists():
        return project_skills

    # Check user home
    home_skills = Path.home() / ".github" / "skills"
    if home_skills.exists():
        return home_skills

    # Fallback to project location (even if it doesn't exist)
    return project_skills


def list_available_skills() -> list[str]:
    """List available skill names from the skills directory."""
    skills_dir = get_skills_directory()
    if not skills_dir.exists():
        return []

    skills = []
    for f in skills_dir.iterdir():
        if f.suffix == ".md" and f.stem != "README":
            skills.append(f.stem)
    return sorted(skills)
