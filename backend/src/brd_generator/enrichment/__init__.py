"""Codebase Enrichment Module.

This module provides functionality for enriching codebases with:
- Auto-generated documentation (JSDoc, JavaDoc, docstrings, etc.)
- Auto-generated test skeletons (unit tests, integration tests)

The enrichment process uses LLM to analyze code context and generate
appropriate documentation and tests based on the code structure.
"""

from .documentation_generator import DocumentationGenerator
from .test_generator import TestGenerator
from .enrichment_service import EnrichmentService

__all__ = [
    "DocumentationGenerator",
    "TestGenerator",
    "EnrichmentService",
]
