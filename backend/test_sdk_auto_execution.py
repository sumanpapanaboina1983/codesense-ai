"""
Test: Does Copilot SDK auto-execute tools when passed to create_session()?

This test verifies whether we can remove the manual agentic loop.

Run with:
    cd backend
    python test_sdk_auto_execution.py

Expected behavior:
- If SDK auto-executes tools passed to create_session(), we can simplify base.py
- If not, we need to keep the manual loop but can enhance with planning/reflection
"""
import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Try to import Copilot SDK
try:
    from copilot import CopilotClient
    from copilot.tools import define_tool
    COPILOT_SDK_AVAILABLE = True
except ImportError:
    COPILOT_SDK_AVAILABLE = False
    print("WARNING: Copilot SDK not installed. Install with: pip install github-copilot-sdk")

from pydantic import BaseModel


# =============================================================================
# Test 1: Custom tool auto-execution
# =============================================================================

class CalculatorParams(BaseModel):
    """Parameters for calculator tool."""
    operation: str
    a: int
    b: int


# Track if tool was executed
tool_execution_tracker = {"calculator_executed": False, "calculator_result": None}


if COPILOT_SDK_AVAILABLE:
    @define_tool(description="Perform math operations (add, subtract, multiply, divide)", params_type=CalculatorParams)
    async def calculator(params: CalculatorParams) -> dict:
        """Calculator tool that tracks execution."""
        global tool_execution_tracker
        tool_execution_tracker["calculator_executed"] = True

        result = None
        if params.operation == "add":
            result = params.a + params.b
        elif params.operation == "subtract":
            result = params.a - params.b
        elif params.operation == "multiply":
            result = params.a * params.b
        elif params.operation == "divide":
            result = params.a / params.b if params.b != 0 else "Error: division by zero"
        else:
            result = f"Unknown operation: {params.operation}"

        tool_execution_tracker["calculator_result"] = result
        return {"result": result}


async def test_auto_execution_with_tools_in_session():
    """
    Test 1: Pass tools to create_session() - should auto-execute.

    According to the SDK documentation, when tools are passed to create_session(),
    the SDK should handle tool calling automatically.
    """
    if not COPILOT_SDK_AVAILABLE:
        print("SKIP: Copilot SDK not available")
        return None

    global tool_execution_tracker
    tool_execution_tracker = {"calculator_executed": False, "calculator_result": None}

    print("\n" + "=" * 60)
    print("TEST 1: @define_tool auto-execution (tools in create_session)")
    print("=" * 60)

    client = CopilotClient()
    await client.start()

    try:
        # Pass tools to create_session (NOT send_and_wait)
        # This is the KEY configuration for SDK auto-execution
        session = await client.create_session({
            "model": os.getenv("COPILOT_MODEL", "claude-sonnet-4"),
            "streaming": True,
            "tools": [calculator],  # Tools in session config
        })

        # Simple call without tools - SDK should auto-execute if LLM calls the tool
        event = await session.send_and_wait({
            "prompt": "What is 15 + 27? Use the calculator tool to compute this."
        })

        print(f"Tool executed: {tool_execution_tracker['calculator_executed']}")
        print(f"Tool result: {tool_execution_tracker['calculator_result']}")
        print(f"Response type: {type(event)}")

        # Try to extract response content
        if hasattr(event, 'data'):
            data = event.data
            if hasattr(data, 'message') and hasattr(data.message, 'content'):
                print(f"Response content: {data.message.content[:200]}...")
            elif hasattr(data, 'content'):
                print(f"Response content: {str(data.content)[:200]}...")
        elif hasattr(event, 'content'):
            print(f"Response content: {str(event.content)[:200]}...")
        else:
            print(f"Raw event: {event}")

        await session.destroy()

        return tool_execution_tracker["calculator_executed"]

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        await client.stop()


async def test_auto_execution_with_tools_in_send():
    """
    Test 2: Pass tools to send_and_wait() - manual loop style.

    This is the current implementation in base.py.
    We want to see if behavior differs from Test 1.
    """
    if not COPILOT_SDK_AVAILABLE:
        print("SKIP: Copilot SDK not available")
        return None

    global tool_execution_tracker
    tool_execution_tracker = {"calculator_executed": False, "calculator_result": None}

    print("\n" + "=" * 60)
    print("TEST 2: @define_tool execution (tools in send_and_wait)")
    print("=" * 60)

    client = CopilotClient()
    await client.start()

    try:
        # Create session WITHOUT tools
        session = await client.create_session({
            "model": os.getenv("COPILOT_MODEL", "claude-sonnet-4"),
            "streaming": True,
        })

        # Get tool definitions for send_and_wait
        # The SDK provides a way to get tool definitions
        tool_definitions = []
        if hasattr(calculator, '_tool_definition'):
            tool_definitions.append(calculator._tool_definition)
        elif hasattr(calculator, 'get_definition'):
            tool_definitions.append(calculator.get_definition())
        else:
            # Manual definition based on @define_tool decorator
            tool_definitions.append({
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Perform math operations (add, subtract, multiply, divide)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {"type": "string"},
                            "a": {"type": "integer"},
                            "b": {"type": "integer"}
                        },
                        "required": ["operation", "a", "b"]
                    }
                }
            })

        # Pass tools to send_and_wait (current approach)
        event = await session.send_and_wait({
            "prompt": "What is 15 + 27? Use the calculator tool to compute this.",
            "tools": tool_definitions,
        })

        print(f"Tool executed: {tool_execution_tracker['calculator_executed']}")
        print(f"Tool result: {tool_execution_tracker['calculator_result']}")
        print(f"Response type: {type(event)}")

        # Check if response contains tool_calls (manual execution needed)
        has_tool_calls = False
        if hasattr(event, 'data'):
            data = event.data
            if hasattr(data, 'message') and hasattr(data.message, 'tool_calls'):
                has_tool_calls = bool(data.message.tool_calls)
            elif hasattr(data, 'tool_calls'):
                has_tool_calls = bool(data.tool_calls)
        elif hasattr(event, 'tool_calls'):
            has_tool_calls = bool(event.tool_calls)

        print(f"Response has tool_calls: {has_tool_calls}")

        if has_tool_calls:
            print("NOTE: Tool calls present means manual execution is needed!")

        await session.destroy()

        # Return True if tool was auto-executed, False if manual execution needed
        return tool_execution_tracker["calculator_executed"]

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        await client.stop()


async def test_mcp_server_auto_execution():
    """
    Test 3: MCP server tools - should auto-execute.

    MCP servers configured in create_session() should have their tools
    auto-executed by the SDK.
    """
    if not COPILOT_SDK_AVAILABLE:
        print("SKIP: Copilot SDK not available")
        return None

    print("\n" + "=" * 60)
    print("TEST 3: MCP server tool auto-execution")
    print("=" * 60)

    client = CopilotClient()
    await client.start()

    try:
        # Create session with filesystem MCP server
        session = await client.create_session({
            "model": os.getenv("COPILOT_MODEL", "claude-sonnet-4"),
            "streaming": True,
            "mcp_servers": {
                "filesystem": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
                    "tools": ["*"],
                    "timeout": 30000
                }
            }
        })

        # Ask to list files - should trigger filesystem MCP tool
        event = await session.send_and_wait({
            "prompt": "List the Python files in the current directory. Use the filesystem tool to do this."
        })

        print(f"Response type: {type(event)}")

        # Try to extract response content
        response_content = ""
        if hasattr(event, 'data'):
            data = event.data
            if hasattr(data, 'message') and hasattr(data.message, 'content'):
                response_content = str(data.message.content)
            elif hasattr(data, 'content'):
                response_content = str(data.content)
        elif hasattr(event, 'content'):
            response_content = str(event.content)

        # Check if response contains file listing (tool was called)
        contains_files = any(ext in response_content.lower() for ext in ['.py', '.yaml', '.json', 'requirements'])
        print(f"Response appears to contain file listing: {contains_files}")
        print(f"Response preview: {response_content[:300]}...")

        await session.destroy()

        return contains_files

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        await client.stop()


async def test_run_agent_task_method():
    """
    Test 4: Check if SDK has run_agent_task or similar method.

    The plan mentions using session.run_agent_task() for native agentic execution.
    Let's verify if this method exists.
    """
    if not COPILOT_SDK_AVAILABLE:
        print("SKIP: Copilot SDK not available")
        return None

    print("\n" + "=" * 60)
    print("TEST 4: Check for run_agent_task() method")
    print("=" * 60)

    client = CopilotClient()
    await client.start()

    try:
        session = await client.create_session({
            "model": os.getenv("COPILOT_MODEL", "claude-sonnet-4"),
            "streaming": True,
        })

        # Check available methods on session
        session_methods = [m for m in dir(session) if not m.startswith('_')]
        print(f"Session methods: {session_methods}")

        # Check for agentic methods
        agentic_methods = [m for m in session_methods if any(
            keyword in m.lower() for keyword in ['agent', 'run', 'execute', 'task', 'tool']
        )]
        print(f"Potentially agentic methods: {agentic_methods}")

        # Check for mode/config options
        if hasattr(session, 'config'):
            print(f"Session config: {session.config}")

        await session.destroy()

        has_agent_method = 'run_agent_task' in session_methods or 'run' in session_methods
        return has_agent_method

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        await client.stop()


async def main():
    """Run all tests and summarize results."""
    print("=" * 60)
    print("Copilot SDK Auto-Execution Tests")
    print("=" * 60)
    print(f"SDK Available: {COPILOT_SDK_AVAILABLE}")
    print(f"Model: {os.getenv('COPILOT_MODEL', 'claude-sonnet-4')}")

    if not COPILOT_SDK_AVAILABLE:
        print("\nCannot run tests - Copilot SDK not installed")
        print("Install with: pip install github-copilot-sdk")
        return

    results = {}

    # Test 1: Tools in create_session
    results["tools_in_session"] = await test_auto_execution_with_tools_in_session()

    # Test 2: Tools in send_and_wait
    results["tools_in_send"] = await test_auto_execution_with_tools_in_send()

    # Test 3: MCP server auto-execution
    results["mcp_auto_exec"] = await test_mcp_server_auto_execution()

    # Test 4: Check for run_agent_task
    results["has_agent_method"] = await test_run_agent_task_method()

    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)

    for test_name, result in results.items():
        status = "PASS" if result is True else ("FAIL" if result is False else "UNKNOWN")
        print(f"  {test_name}: {status}")

    print("\n" + "-" * 60)
    print("RECOMMENDATIONS:")
    print("-" * 60)

    if results.get("tools_in_session") is True:
        print("  - SDK auto-executes tools when passed to create_session()")
        print("  - SIMPLIFY base.py: Remove manual agentic loop")
        print("  - Pass tools to session config instead of send_and_wait()")
    elif results.get("tools_in_send") is False:
        print("  - SDK does NOT auto-execute tools in send_and_wait()")
        print("  - KEEP manual agentic loop in base.py")
        print("  - Consider passing tools to create_session() instead")
    else:
        print("  - Results inconclusive - test manually")

    if results.get("mcp_auto_exec") is True:
        print("  - MCP server tools ARE auto-executed")
        print("  - No changes needed for MCP server config")

    if results.get("has_agent_method") is True:
        print("  - SDK has run_agent_task() or similar method")
        print("  - Consider using this for simpler agent implementation")


if __name__ == "__main__":
    asyncio.run(main())
