"""Test that Copilot SDK actually loads and uses our skills.

This test requires:
1. Copilot SDK installed: pip install github-copilot-sdk
2. Valid Copilot authentication (GitHub Copilot subscription)
"""

import asyncio
import os
from pathlib import Path

# Set up environment
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "password")
os.environ.setdefault("NEO4J_DATABASE", "codegraph")

# Get skills directory
SKILLS_DIR = Path(__file__).parent / "src" / "brd_generator" / "skills"


def test_sdk_available():
    """Test 1: Check if Copilot SDK is available."""
    print("=" * 60)
    print("TEST 1: Copilot SDK Availability")
    print("=" * 60)

    try:
        from copilot import CopilotClient
        from copilot.types import SessionConfig
        print("  ✅ Copilot SDK imported successfully")
        print(f"     CopilotClient: {CopilotClient}")
        print(f"     SessionConfig keys: {SessionConfig.__annotations__.keys()}")
        return True
    except ImportError as e:
        print(f"  ❌ Copilot SDK not available: {e}")
        print("     Install with: pip install github-copilot-sdk")
        return False


def test_session_config_type():
    """Test 2: Verify SessionConfig accepts our keys."""
    print("\n" + "=" * 60)
    print("TEST 2: SessionConfig Type Validation")
    print("=" * 60)

    try:
        from copilot.types import SessionConfig

        # Check what keys SessionConfig accepts
        annotations = SessionConfig.__annotations__
        print("\n  SessionConfig accepted keys:")
        for key, type_hint in annotations.items():
            print(f"    - {key}: {type_hint}")

        # Check our required keys
        required_keys = ["model", "streaming", "mcp_servers", "skill_directories"]
        print("\n  Checking our required keys:")
        for key in required_keys:
            if key in annotations:
                print(f"    ✅ {key} is valid")
            else:
                print(f"    ❌ {key} NOT in SessionConfig!")

        return True
    except Exception as e:
        print(f"  ⚠️ Could not check SessionConfig: {e}")
        return False


async def test_session_creation():
    """Test 3: Actually create a session with skills."""
    print("\n" + "=" * 60)
    print("TEST 3: Session Creation with Skills")
    print("=" * 60)

    try:
        from copilot import CopilotClient

        # Create client
        client = CopilotClient()
        print("  ✅ CopilotClient created")

        # Start client
        await client.start()
        print("  ✅ CopilotClient started")

        # Build session config with skills
        # Use claude-sonnet-4 (more widely available than 4.5)
        session_config = {
            "model": "claude-sonnet-4",
            "streaming": True,
            "skill_directories": [str(SKILLS_DIR)],
        }

        print(f"\n  Session config:")
        print(f"    model: {session_config['model']}")
        print(f"    skill_directories: {session_config['skill_directories']}")

        # Create session
        session = await client.create_session(session_config)
        print(f"  ✅ Session created: {session}")

        # Check if session has skills info
        if hasattr(session, 'skills'):
            print(f"  ✅ Session has skills: {session.skills}")
        if hasattr(session, 'available_skills'):
            print(f"  ✅ Available skills: {session.available_skills}")

        # Try to list available tools/skills
        if hasattr(session, 'list_skills'):
            skills = await session.list_skills()
            print(f"  ✅ Skills loaded by SDK: {skills}")
        elif hasattr(session, 'get_available_tools'):
            tools = await session.get_available_tools()
            print(f"  ✅ Available tools: {tools}")

        # Cleanup
        await session.destroy()
        await client.stop()
        print("  ✅ Session and client cleaned up")

        return True

    except Exception as e:
        print(f"  ❌ Session creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_skill_matching_with_sdk():
    """Test 4: Send a request and see if SDK matches skill."""
    print("\n" + "=" * 60)
    print("TEST 4: Skill Matching via SDK")
    print("=" * 60)

    try:
        from copilot import CopilotClient

        client = CopilotClient()
        await client.start()

        # Try claude-sonnet-4 (more widely available)
        # Include MCP servers so skills can use tools
        session_config = {
            "model": "claude-sonnet-4",
            "streaming": True,
            "skill_directories": [str(SKILLS_DIR)],
            "mcp_servers": {
                "filesystem": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", str(SKILLS_DIR.parent.parent)],
                    "tools": ["*"],
                },
            },
        }

        session = await client.create_session(session_config)
        print("  ✅ Session created with skill_directories")

        # Send a request that should match generate-brd skill
        test_prompt = "Generate a BRD for user authentication feature"
        print(f"\n  Sending: '{test_prompt}'")

        # Use send_and_wait to get response
        response = await session.send_and_wait(
            {"prompt": test_prompt},
            timeout=30000
        )

        print(f"\n  Response type: {type(response)}")
        print(f"  Response.type: {response.type}")

        # Inspect the data object
        if hasattr(response, 'data') and response.data:
            print("\n  Response.data attributes:")
            data = response.data
            for attr in dir(data):
                if not attr.startswith('_'):
                    try:
                        val = getattr(data, attr)
                        if not callable(val) and val is not None:
                            val_str = str(val)[:300] if len(str(val)) > 300 else str(val)
                            print(f"    {attr}: {val_str}")
                    except Exception as e:
                        print(f"    {attr}: <error: {e}>")

            # Check for message content in common locations
            if hasattr(data, 'message'):
                print(f"\n  ✅ Message: {data.message}")
            if hasattr(data, 'content'):
                content = str(data.content)[:500]
                print(f"\n  ✅ Content: {content}")
            if hasattr(data, 'text'):
                print(f"\n  ✅ Text: {data.text[:500] if data.text else None}")

        # Check for tool requests
        if hasattr(response.data, 'tool_requests') and response.data.tool_requests:
            print(f"\n  ✅ Tool requests: {len(response.data.tool_requests)} tools called")
            for tr in response.data.tool_requests:
                print(f"     - {tr}")
        else:
            print(f"\n  ℹ️  No tool requests (LLM answered directly without tools)")

        # Check for skill info
        if hasattr(response, 'skill'):
            print(f"\n  ✅ Skill used: {response.skill}")
        if hasattr(response.data, 'skill') if response.data else False:
            print(f"\n  ✅ Skill in data: {response.data.skill}")

        await session.destroy()
        await client.stop()
        return True

    except Exception as e:
        print(f"  ❌ Skill matching test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  COPILOT SDK SKILL INTEGRATION TEST")
    print("=" * 60)
    print(f"\n  Skills directory: {SKILLS_DIR}")
    print(f"  Skills exist: {SKILLS_DIR.exists()}")

    if SKILLS_DIR.exists():
        skills_files = list(SKILLS_DIR.glob("*.yaml"))
        print(f"  Skill files found: {[f.name for f in skills_files]}")

    # Test 1: SDK availability
    sdk_available = test_sdk_available()

    if not sdk_available:
        print("\n" + "=" * 60)
        print("  TESTS INCOMPLETE - Copilot SDK not installed")
        print("=" * 60)
        return

    # Test 2: SessionConfig type
    test_session_config_type()

    # Test 3: Session creation
    await test_session_creation()

    # Test 4: Skill matching - auth already worked in test 3
    await test_skill_matching_with_sdk()

    print("\n" + "=" * 60)
    print("  TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
