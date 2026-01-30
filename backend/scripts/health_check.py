#!/usr/bin/env python3
"""
Health check script for BRD Generator services.

Verifies connectivity to:
- Neo4j MCP Server
- Filesystem MCP Server
- Copilot SDK
"""

import asyncio
import os
import sys

from rich.console import Console
from rich.table import Table

console = Console()


async def check_neo4j_mcp():
    """Check Neo4j MCP server connectivity."""
    import httpx

    url = os.getenv("NEO4J_MCP_URL", "http://localhost:8001")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            if response.status_code == 200:
                return True, "Connected"
            return False, f"Status {response.status_code}"
    except httpx.ConnectError:
        return False, "Connection refused"
    except Exception as e:
        return False, str(e)


async def check_filesystem_mcp():
    """Check Filesystem MCP server connectivity."""
    import httpx

    url = os.getenv("FILESYSTEM_MCP_URL", "http://localhost:8002")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            if response.status_code == 200:
                return True, "Connected"
            return False, f"Status {response.status_code}"
    except httpx.ConnectError:
        return False, "Connection refused"
    except Exception as e:
        return False, str(e)


async def check_copilot_sdk():
    """Check Copilot SDK availability."""
    try:
        from copilot import CopilotClient
        return True, "SDK available"
    except ImportError:
        return False, "SDK not installed"
    except Exception as e:
        return False, str(e)


async def check_neo4j_direct():
    """Check direct Neo4j connectivity."""
    try:
        from neo4j import AsyncGraphDatabase

        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")

        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        try:
            await driver.verify_connectivity()
            return True, "Connected"
        finally:
            await driver.close()
    except Exception as e:
        return False, str(e)


async def main():
    """Run all health checks."""
    console.print("\n[bold]BRD Generator Health Check[/bold]\n")

    # Run checks concurrently
    results = await asyncio.gather(
        check_neo4j_mcp(),
        check_filesystem_mcp(),
        check_copilot_sdk(),
        check_neo4j_direct(),
        return_exceptions=True
    )

    # Build results table
    table = Table(title="Service Status")
    table.add_column("Service", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")

    services = [
        "Neo4j MCP Server",
        "Filesystem MCP Server",
        "Copilot SDK",
        "Neo4j Direct"
    ]

    all_healthy = True
    for service, result in zip(services, results):
        if isinstance(result, Exception):
            status = "[red]ERROR[/red]"
            details = str(result)
            all_healthy = False
        elif result[0]:
            status = "[green]✓ OK[/green]"
            details = result[1]
        else:
            status = "[red]✗ FAIL[/red]"
            details = result[1]
            all_healthy = False

        table.add_row(service, status, details)

    console.print(table)

    # Environment info
    console.print("\n[bold]Environment:[/bold]")
    console.print(f"  NEO4J_MCP_URL: {os.getenv('NEO4J_MCP_URL', 'http://localhost:8001')}")
    console.print(f"  FILESYSTEM_MCP_URL: {os.getenv('FILESYSTEM_MCP_URL', 'http://localhost:8002')}")
    console.print(f"  NEO4J_URI: {os.getenv('NEO4J_URI', 'bolt://localhost:7687')}")

    if all_healthy:
        console.print("\n[bold green]All services healthy![/bold green]\n")
        return 0
    else:
        console.print("\n[bold red]Some services are unhealthy.[/bold red]\n")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
