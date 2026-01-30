"""
BRD Generator - Main Entry Point

Command-line interface for generating Business Requirements Documents
from codebase context using MCP servers and LLM synthesis.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown

from .models.request import BRDRequest
from .models.output import BRDOutput
from .core.generator import BRDGenerator
from .utils.logger import get_logger, setup_logging

console = Console()
logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="brd-generator",
        description="Generate Business Requirements Documents from codebase context",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate BRD from feature description
  brd-generator --feature "Add user authentication with OAuth2"

  # Generate BRD with specific components
  brd-generator --feature "Add caching layer" --components api,database

  # Generate from JSON request file
  brd-generator --request-file request.json

  # Output to file
  brd-generator --feature "Add logging" --output brd.md
        """
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--feature", "-f",
        type=str,
        help="Feature description to generate BRD for"
    )
    input_group.add_argument(
        "--request-file", "-r",
        type=Path,
        help="Path to JSON file containing BRD request"
    )

    # Generation options
    parser.add_argument(
        "--scope", "-s",
        type=str,
        choices=["minimal", "standard", "full"],
        default="full",
        help="Scope of context gathering (default: full)"
    )
    parser.add_argument(
        "--components", "-c",
        type=str,
        help="Comma-separated list of affected components"
    )
    parser.add_argument(
        "--no-similar",
        action="store_true",
        help="Disable searching for similar features"
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)"
    )

    # Output options
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for multiple files (BRD, epics, stories)"
    )

    # Configuration options
    parser.add_argument(
        "--neo4j-url",
        type=str,
        help="Neo4j MCP server URL (overrides env)"
    )
    parser.add_argument(
        "--filesystem-url",
        type=str,
        help="Filesystem MCP server URL (overrides env)"
    )

    # Verbosity options
    parser.add_argument(
        "--verbose", "-v",
        action="count",
        default=0,
        help="Increase verbosity (use -vv for debug)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress all output except results"
    )

    return parser.parse_args()


def build_request(args: argparse.Namespace) -> BRDRequest:
    """Build BRD request from CLI arguments or file."""
    if args.request_file:
        # Load request from JSON file
        try:
            with open(args.request_file, 'r') as f:
                data = json.load(f)
            return BRDRequest(**data)
        except FileNotFoundError:
            console.print(f"[red]Error:[/red] Request file not found: {args.request_file}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            console.print(f"[red]Error:[/red] Invalid JSON in request file: {e}")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to parse request file: {e}")
            sys.exit(1)

    # Build request from CLI arguments
    components = None
    if args.components:
        components = [c.strip() for c in args.components.split(",")]

    return BRDRequest(
        feature_description=args.feature,
        scope=args.scope,
        affected_components=components,
        include_similar_features=not args.no_similar,
        output_format=args.format
    )


def write_output(
    output: BRDOutput,
    output_path: Optional[Path],
    output_dir: Optional[Path],
    output_format: str
) -> None:
    """Write output to file(s) or stdout."""
    if output_dir:
        # Write multiple files
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write BRD
        brd_path = output_dir / "brd.md"
        with open(brd_path, 'w') as f:
            f.write(output.brd.to_markdown())
        console.print(f"[green]✓[/green] BRD written to {brd_path}")

        # Write epics
        if output.epics:
            epics_dir = output_dir / "epics"
            epics_dir.mkdir(exist_ok=True)
            for i, epic in enumerate(output.epics, 1):
                epic_path = epics_dir / f"epic_{i}.md"
                with open(epic_path, 'w') as f:
                    f.write(epic.to_markdown())
            console.print(f"[green]✓[/green] {len(output.epics)} epics written to {epics_dir}")

        # Write user stories
        if output.user_stories:
            stories_dir = output_dir / "stories"
            stories_dir.mkdir(exist_ok=True)
            for i, story in enumerate(output.user_stories, 1):
                story_path = stories_dir / f"story_{i}.md"
                with open(story_path, 'w') as f:
                    f.write(story.to_markdown())
            console.print(f"[green]✓[/green] {len(output.user_stories)} stories written to {stories_dir}")

        # Write summary JSON
        summary_path = output_dir / "summary.json"
        with open(summary_path, 'w') as f:
            json.dump({
                "brd_title": output.brd.title,
                "epic_count": len(output.epics),
                "story_count": len(output.user_stories),
                "generation_metadata": output.metadata
            }, f, indent=2, default=str)
        console.print(f"[green]✓[/green] Summary written to {summary_path}")

    elif output_path:
        # Write single file
        if output_format == "json":
            content = output.model_dump_json(indent=2)
        else:
            content = output.brd.to_markdown()
            if output.epics:
                content += "\n\n---\n\n# Epics\n\n"
                for epic in output.epics:
                    content += epic.to_markdown() + "\n\n---\n\n"
            if output.user_stories:
                content += "\n\n---\n\n# User Stories\n\n"
                for story in output.user_stories:
                    content += story.to_markdown() + "\n\n---\n\n"

        with open(output_path, 'w') as f:
            f.write(content)
        console.print(f"[green]✓[/green] Output written to {output_path}")

    else:
        # Write to stdout
        if output_format == "json":
            print(output.model_dump_json(indent=2))
        else:
            console.print(Markdown(output.brd.to_markdown()))


async def run_generation(args: argparse.Namespace) -> int:
    """Run the BRD generation process."""
    # Build request
    request = build_request(args)

    if not args.quiet:
        console.print(Panel(
            f"[bold]Feature:[/bold] {request.feature_description}\n"
            f"[bold]Scope:[/bold] {request.scope}\n"
            f"[bold]Components:[/bold] {request.affected_components or 'Auto-detect'}",
            title="BRD Generation Request",
            border_style="blue"
        ))

    # Initialize generator
    generator = BRDGenerator()

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            disable=args.quiet
        ) as progress:
            # Initialize
            task = progress.add_task("Initializing MCP clients...", total=None)
            await generator.initialize()
            progress.update(task, description="[green]✓[/green] MCP clients connected")

            # Generate
            progress.update(task, description="Gathering codebase context...")
            output = await generator.generate(request)
            progress.update(task, description="[green]✓[/green] Generation complete")

        # Write output
        write_output(
            output,
            args.output,
            args.output_dir,
            request.output_format
        )

        if not args.quiet:
            console.print(Panel(
                f"[bold green]Success![/bold green]\n\n"
                f"Generated:\n"
                f"  • 1 BRD document\n"
                f"  • {len(output.epics)} epics\n"
                f"  • {len(output.backlogs)} user stories",
                title="Generation Complete",
                border_style="green"
            ))

        return 0

    except Exception as e:
        logger.exception("Generation failed")
        console.print(f"[red]Error:[/red] {e}")
        return 1

    finally:
        await generator.cleanup()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Setup logging based on verbosity
    if args.verbose >= 2:
        setup_logging("DEBUG")
    elif args.verbose >= 1:
        setup_logging("INFO")
    elif args.quiet:
        setup_logging("ERROR")
    else:
        setup_logging("WARNING")

    # Run async generation
    try:
        return asyncio.run(run_generation(args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
