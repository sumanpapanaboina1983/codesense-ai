#!/usr/bin/env python3
"""
Test script for BRD generation with MCP servers.

This script demonstrates:
1. Registering Neo4j and Filesystem MCP servers with Copilot SDK
2. Using the MCP servers to query code graph and read files
3. Generating a BRD using the context from MCP servers

Usage:
    python test_brd_with_mcp.py

Environment variables:
    - GH_TOKEN or GITHUB_TOKEN: GitHub token for Copilot authentication
    - NEO4J_URI: Neo4j connection URI (default: bolt://localhost:7687)
    - NEO4J_USER: Neo4j username (default: neo4j)
    - NEO4J_PASSWORD: Neo4j password (default: password)
    - NEO4J_DATABASE: Neo4j database (default: codegraph)
    - CODEBASE_ROOT: Path to codebase (default: current directory)
"""

import asyncio
import os
import sys
from pathlib import Path

from copilot import CopilotClient, MCPServerConfig
from copilot.generated.session_events import SessionEventType


def get_mcp_servers_config() -> dict[str, MCPServerConfig]:
    """Build MCP servers configuration from environment."""
    codebase_root = os.getenv("CODEBASE_ROOT", str(Path.cwd()))
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    neo4j_database = os.getenv("NEO4J_DATABASE", "codegraph")

    return {
        "filesystem": {
            "type": "stdio",
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                codebase_root
            ],
            "tools": ["*"],
            "timeout": 30000
        },
        "neo4j-code-graph": {
            "type": "stdio",
            "command": "npx",
            "args": [
                "-y",
                "@neo4j-contrib/mcp-neo4j"
            ],
            "tools": ["*"],
            "timeout": 30000,
            "env": {
                "NEO4J_URI": neo4j_uri,
                "NEO4J_USERNAME": neo4j_user,
                "NEO4J_PASSWORD": neo4j_password,
                "NEO4J_DATABASE": neo4j_database,
                "NEO4J_READ_ONLY": "true"
            }
        }
    }


async def main():
    """Main test function."""
    print("=" * 60)
    print("BRD Generation with MCP Servers Test")
    print("=" * 60)

    print("\n1. Initializing Copilot SDK client...")
    client = CopilotClient()
    await client.start()
    print("   Client started successfully")

    # Get MCP configuration
    mcp_servers = get_mcp_servers_config()
    print(f"\n2. Configuring MCP servers:")
    for name, config in mcp_servers.items():
        print(f"   - {name}: {config['command']} {' '.join(config['args'][:2])}...")

    # Find skills directory
    skills_dir = None
    for path in [
        Path.cwd() / ".github" / "skills",
        Path.home() / ".github" / "skills",
        Path("/home/appuser/.github/skills"),
    ]:
        if path.exists():
            skills_dir = str(path)
            break

    print(f"\n3. Creating session with MCP servers...")
    session_config = {
        "model": os.getenv("COPILOT_MODEL", "gpt-4.1"),
        "streaming": True,
        "mcp_servers": mcp_servers,
    }

    if skills_dir:
        session_config["skill_directories"] = skills_dir
        print(f"   Skills directory: {skills_dir}")

    session = await client.create_session(session_config)
    print("   Session created successfully")

    # Set up event handler
    response_text = ""
    tools_executed = []

    def handle_event(event):
        nonlocal response_text

        if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            sys.stdout.write(event.data.delta_content)
            sys.stdout.flush()
            response_text += event.data.delta_content

        elif event.type == SessionEventType.SESSION_IDLE:
            print()  # New line after response

        elif event.type == SessionEventType.TOOL_EXECUTION_START:
            tool_name = getattr(event.data, 'name', 'unknown')
            tools_executed.append(tool_name)
            print(f"\n[Tool started: {tool_name}]")

        elif event.type == SessionEventType.TOOL_EXECUTION_COMPLETE:
            print(f"[Tool completed]")

    session.on(handle_event)

    # Test 1: Query available tools
    print("\n4. Testing: List available MCP tools")
    print("-" * 40)
    await session.send_and_wait({
        "prompt": "What MCP tools are available to you? List the tools from filesystem and neo4j-code-graph servers."
    })

    # Test 2: Query code graph
    print("\n\n5. Testing: Query Neo4j code graph")
    print("-" * 40)
    await session.send_and_wait({
        "prompt": """Use the neo4j-code-graph MCP server to:
1. First get the database schema
2. Then query for the top 5 components in the codebase

Show me the Cypher queries you execute and the results."""
    })

    # Test 3: Read a file
    print("\n\n6. Testing: Read file with filesystem MCP")
    print("-" * 40)
    await session.send_and_wait({
        "prompt": """Use the filesystem MCP server to:
1. List the files in the root directory
2. Read the README.md or pyproject.toml if they exist

Show me what you find."""
    })

    # Test 4: Generate BRD (if generate-brd skill is available)
    print("\n\n7. Testing: BRD Generation (using available context)")
    print("-" * 40)
    await session.send_and_wait({
        "prompt": """Based on the codebase structure you've seen, generate a brief BRD outline for:
"Add a caching layer to improve API response times"

Use the neo4j-code-graph tools to find relevant components and the filesystem tools to read key files.
Provide:
1. Affected components (from code graph)
2. Key files to modify
3. High-level functional requirements (3-5)
4. Technical requirements (2-3)
"""
    })

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Tools executed: {len(tools_executed)}")
    for tool in tools_executed:
        print(f"  - {tool}")

    # Cleanup
    print("\n8. Cleaning up...")
    await client.stop()
    print("   Done!")


if __name__ == "__main__":
    asyncio.run(main())
