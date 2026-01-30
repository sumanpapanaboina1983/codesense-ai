#!/usr/bin/env python3
"""
Run an example BRD generation.

This script demonstrates how to use the BRD Generator programmatically.
"""

import asyncio
import json
from pathlib import Path

from brd_generator.models.request import BRDRequest
from brd_generator.core.generator import BRDGenerator


async def run_example():
    """Run an example BRD generation."""
    # Create request
    request = BRDRequest(
        feature_description="Add a user notification system with email and push notification support",
        scope="standard",
        affected_components=["api", "notifications", "email"],
        include_similar_features=True,
        output_format="markdown"
    )

    print("=" * 60)
    print("BRD Generator Example")
    print("=" * 60)
    print(f"\nFeature: {request.feature_description}")
    print(f"Scope: {request.scope}")
    print(f"Components: {request.affected_components}")
    print()

    # Initialize generator
    generator = BRDGenerator()

    try:
        print("Initializing...")
        await generator.initialize()

        print("Generating BRD...")
        output = await generator.generate(request)

        # Print results
        print("\n" + "=" * 60)
        print("GENERATED BRD")
        print("=" * 60)
        print(output.brd.to_markdown())

        print("\n" + "=" * 60)
        print(f"EPICS ({len(output.epics)})")
        print("=" * 60)
        for epic in output.epics:
            print(f"\n{epic.id}: {epic.title}")
            print(f"  Components: {', '.join(epic.components_affected)}")
            print(f"  Stories: {len(epic.story_ids)}")

        print("\n" + "=" * 60)
        print(f"USER STORIES ({len(output.user_stories)})")
        print("=" * 60)
        for story in output.user_stories:
            print(f"\n{story.id}: {story.title}")
            print(f"  As a {story.as_a}")
            print(f"  I want {story.i_want}")
            print(f"  So that {story.so_that}")
            print(f"  Points: {story.story_points}")

        # Save to file
        output_path = Path("example_output.md")
        with open(output_path, "w") as f:
            f.write(output.brd.to_markdown())
        print(f"\n\nFull output saved to: {output_path}")

    except Exception as e:
        print(f"Error: {e}")
        raise

    finally:
        await generator.cleanup()


async def run_from_file():
    """Run BRD generation from a JSON request file."""
    examples_dir = Path(__file__).parent.parent / "examples"
    request_file = examples_dir / "sample_request.json"

    if not request_file.exists():
        print(f"Request file not found: {request_file}")
        return

    with open(request_file) as f:
        data = json.load(f)

    request = BRDRequest(**data)

    print(f"Loaded request from: {request_file}")
    print(f"Feature: {request.feature_description}")

    generator = BRDGenerator()

    try:
        await generator.initialize()
        output = await generator.generate(request)
        print("\nGeneration complete!")
        print(f"BRD Title: {output.brd.title}")
        print(f"Epics: {len(output.epics)}")
        print(f"Stories: {len(output.user_stories)}")

    finally:
        await generator.cleanup()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--from-file":
        asyncio.run(run_from_file())
    else:
        asyncio.run(run_example())
