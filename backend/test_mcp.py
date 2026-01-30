#!/usr/bin/env python3
"""
Test script for MCP server integration with Copilot SDK.

Usage:
    python test_mcp.py

Environment variables:
    - GH_TOKEN or GITHUB_TOKEN: GitHub token for Copilot authentication
"""

import asyncio
import sys

from copilot import CopilotClient, MCPServerConfig
from copilot.generated.session_events import SessionEventType


async def main():
    """Test MCP server integration with Copilot SDK."""
    print("Starting MCP integration test...")

    client = CopilotClient()
    await client.start()

    # Configure MCP servers
    mcp_servers: dict[str, MCPServerConfig] = {
        "filesystem": {
            "type": "stdio",
            "command": "/opt/homebrew/bin/npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                "/Users/suman.papanaboina/workspaces"
            ],
            "tools": ["*"]
        },
        "cnx-code-graph": {
            "type": "stdio",
            "command": "/Users/suman.papanaboina/Downloads/neo4j-mcp_Darwin_arm64/neo4j-mcp",
            "args": [],
            "tools": ["*"],
            "timeout": 30000,
            "env": {
                "NEO4J_URI": "bolt://localhost:7687",
                "NEO4J_USERNAME": "neo4j",
                "NEO4J_PASSWORD": "test@123",
                "NEO4J_DATABASE": "codegraph",
                "NEO4J_READ_ONLY": "true"
            }
        }
    }

    session = await client.create_session({
        "model": "gpt-4.1",
        "streaming": True,
        "skill_directories": ".github/skills",
        "mcp_servers": mcp_servers
    })

    def handle_event(event):
        if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            sys.stdout.write(event.data.delta_content)
            sys.stdout.flush()
        elif event.type == SessionEventType.SESSION_IDLE:
            print()
        elif event.type == SessionEventType.TOOL_EXECUTION_START:
            print("TOOL_EXECUTION_START")
            print(event)
        elif event.type == SessionEventType.TOOL_EXECUTION_COMPLETE:
            print("TOOL_EXECUTION_COMPLETE")

    session.on(handle_event)

    await session.send_and_wait({
        "prompt": "get neo4j schema"
    })

    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
