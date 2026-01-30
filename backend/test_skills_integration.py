"""Test Skills Integration with Copilot SDK.

This script tests the skill-based BRD generation flow:
1. Loads skills from YAML files
2. Matches request to appropriate skill
3. Shows what MCP tools would be available
4. Demonstrates the agentic flow
"""

import asyncio
import os
from pathlib import Path

# Set up environment for testing
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "password")
os.environ.setdefault("NEO4J_DATABASE", "codegraph")

from src.brd_generator.core.skill_loader import SkillLoader
from src.brd_generator.core.generator import BRDGenerator
from src.brd_generator.models.request import BRDRequest


def test_skill_loading():
    """Test that skills are loaded correctly."""
    print("=" * 60)
    print("TEST 1: Skill Loading")
    print("=" * 60)

    loader = SkillLoader()
    skills = loader.load_skills()

    print(f"\nLoaded {len(skills)} skills:")
    for name, skill in skills.items():
        print(f"\n  📋 {name}")
        print(f"     Triggers: {skill.triggers[:3]}...")
        print(f"     MCP Servers: {skill.mcp_servers}")
        print(f"     Tools: {[t.name for t in skill.tools]}")

    return loader


def test_skill_matching(loader: SkillLoader):
    """Test skill matching for various requests."""
    print("\n" + "=" * 60)
    print("TEST 2: Skill Matching")
    print("=" * 60)

    test_requests = [
        "Generate a BRD for user authentication feature",
        "Create BRD for payment processing",
        "Verify the BRD claims against codebase",
        "Generate epics from the approved BRD",
        "Create user stories for the payment epic",
        "Help me with something unrelated",
    ]

    print("\nMatching requests to skills:\n")
    for request in test_requests:
        skill = loader.match_skill(request)
        if skill:
            print(f"  ✅ '{request[:40]}...'")
            print(f"     → Matched: {skill.name}")
            print(f"     → MCP Servers: {skill.mcp_servers}")
        else:
            print(f"  ❌ '{request[:40]}...'")
            print(f"     → No skill matched")
        print()


def test_session_config(loader: SkillLoader):
    """Test building session config with skills (Copilot SDK format)."""
    print("=" * 60)
    print("TEST 3: Session Configuration (Copilot SDK Format)")
    print("=" * 60)

    # Mock MCP servers config (MCPServerConfig format)
    mcp_servers = {
        "neo4j-code-graph": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@neo4j-contrib/mcp-neo4j"],
            "tools": ["*"],
        },
        "filesystem": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
            "tools": ["*"],
        },
    }

    # Copilot SDK SessionConfig format:
    # - skill_directories: List[str] - directories to load skills from
    # - disabled_skills: List[str] - skill names to disable
    # The SDK loads skills dynamically from YAML files in these directories

    session_config = {
        "model": "claude-sonnet-4.5",  # Copilot SDK model format
        "streaming": True,
        "mcp_servers": mcp_servers,
        "skill_directories": [str(loader.skills_dir)],  # List[str]
    }

    print("\nCopilot SDK SessionConfig:")
    print(f"  model: {session_config['model']}")
    print(f"  streaming: {session_config['streaming']}")
    print(f"  mcp_servers: {list(session_config['mcp_servers'].keys())}")
    print(f"  skill_directories: {session_config['skill_directories']}")

    print("\n  Skills that will be loaded from directory:")
    skills = loader.get_skills_for_session()
    for skill in skills:
        print(f"    - {skill['name']}: {len(skill['triggers'])} triggers, {len(skill['tools'])} tools")

    print("\n  Sample skill (generate-brd):")
    for skill in skills:
        if skill['name'] == 'generate-brd':
            print(f"    Name: {skill['name']}")
            print(f"    Triggers: {skill['triggers'][:3]}...")
            print(f"    MCP Servers: {skill['mcp_servers']}")
            print(f"    Tools: {[t['name'] for t in skill['tools']]}")
            print(f"    Instructions: {skill['instructions'][:100]}...")
            break


async def test_generator_initialization():
    """Test BRD Generator initialization with skills."""
    print("\n" + "=" * 60)
    print("TEST 4: Generator Initialization")
    print("=" * 60)

    try:
        generator = BRDGenerator(
            workspace_root=Path.cwd(),
            copilot_model="claude-sonnet-4-5",
        )

        print("\nGenerator created:")
        print(f"  Workspace: {generator.workspace_root}")
        print(f"  Model: {generator.copilot_model}")
        print(f"  Skills Dir: {generator.skill_loader.skills_dir}")

        # Load skills
        generator.skill_loader.load_skills()
        print(f"  Skills Loaded: {list(generator.skill_loader.skills.keys())}")

        # Show what would happen with initialization
        print("\n  MCP Servers that would be registered:")
        mcp_config = generator._build_mcp_servers_config()
        for name, config in mcp_config.items():
            print(f"    - {name}: {config['command']} {' '.join(config['args'][:2])}...")

        print("\n  ✅ Generator ready (not fully initialized - would need Copilot SDK)")

    except Exception as e:
        print(f"\n  ⚠️  Generator creation issue: {e}")
        print("     (This is expected if Copilot SDK is not fully configured)")


async def test_brd_generation_flow():
    """Test the BRD generation flow (mock mode)."""
    print("\n" + "=" * 60)
    print("TEST 5: BRD Generation Flow (Simulated)")
    print("=" * 60)

    # Create a sample request - note: must contain trigger words
    request = BRDRequest(
        feature_description="Generate BRD for user authentication with OAuth2 and JWT tokens",
        affected_components=["AuthService", "UserController", "TokenManager"],
    )

    print(f"\nSample Request:")
    print(f"  Feature: {request.feature_description}")
    print(f"  Components: {request.affected_components}")

    # Show what skill would be matched
    loader = SkillLoader()
    loader.load_skills()
    skill = loader.match_skill(request.feature_description)

    if skill:
        print(f"\n  ✅ Matched Skill: {skill.name}")
        print(f"  MCP Servers: {skill.mcp_servers}")
        print(f"  Available Tools:")
        for tool in skill.tools:
            print(f"    - {tool.name}: {tool.description[:50]}...")

        print(f"\n  Skill Instructions (excerpt):")
        instructions_lines = skill.instructions.split('\n')[:10]
        for line in instructions_lines:
            print(f"    {line}")
        print("    ...")

        print("\n  🔄 AGENTIC FLOW THAT WOULD EXECUTE:")
        print("  " + "-" * 50)
        print("    1. User Request → Copilot SDK")
        print("       'Generate BRD for user authentication...'")
        print()
        print("    2. Skill Matching (Copilot SDK)")
        print(f"       Matched: '{skill.name}' skill")
        print(f"       Triggers: {skill.triggers[:2]}...")
        print()
        print("    3. MCP Servers Activated")
        for server in skill.mcp_servers:
            print(f"       ✓ {server}")
        print()
        print("    4. LLM Receives Prompt + Tools + Instructions")
        print("       - Skill instructions loaded")
        print(f"       - {len(skill.tools)} tools available")
        print()
        print("    5. LLM AGENTIC LOOP (decides what tools to call):")
        print("       ┌─────────────────────────────────────────────┐")
        print("       │ LLM: 'I need to understand the codebase...' │")
        print("       │                                             │")
        print("       │ → Tool Call: query_code_structure           │")
        print("       │   Query: MATCH (c:Class) WHERE              │")
        print("       │          c.name CONTAINS 'Auth' RETURN c    │")
        print("       │                                             │")
        print("       │ ← Result: [AuthService, AuthController,     │")
        print("       │           TokenManager, JWTValidator]       │")
        print("       │                                             │")
        print("       │ → Tool Call: get_component_dependencies     │")
        print("       │   Component: AuthService                    │")
        print("       │                                             │")
        print("       │ ← Result: {upstream: [UserRepo, TokenRepo], │")
        print("       │           downstream: [APIGateway]}         │")
        print("       │                                             │")
        print("       │ → Tool Call: read_file                      │")
        print("       │   Path: src/services/auth_service.py        │")
        print("       │                                             │")
        print("       │ ← Result: <file contents>                   │")
        print("       │                                             │")
        print("       │ LLM: 'Now I have enough context...'         │")
        print("       └─────────────────────────────────────────────┘")
        print()
        print("    6. LLM Generates BRD with REAL code context")
        print("       - References actual classes: AuthService, TokenManager")
        print("       - Lists real dependencies from code graph")
        print("       - Includes file paths from filesystem")
        print()
        print("    7. Verifier Agent (verify-brd skill)")
        print("       - Extracts claims from generated BRD")
        print("       - Uses tools to verify each claim")
        print("       - Returns confidence score + evidence")
    else:
        print("\n  ❌ No skill matched for this request")
        print("     Tip: Request should contain trigger words like 'generate brd'")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  SKILLS INTEGRATION TEST")
    print("=" * 60 + "\n")

    # Test 1: Skill Loading
    loader = test_skill_loading()

    # Test 2: Skill Matching
    test_skill_matching(loader)

    # Test 3: Session Config
    test_session_config(loader)

    # Test 4: Generator Initialization
    asyncio.run(test_generator_initialization())

    # Test 5: BRD Generation Flow
    asyncio.run(test_brd_generation_flow())

    print("\n" + "=" * 60)
    print("  ALL TESTS COMPLETE")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
