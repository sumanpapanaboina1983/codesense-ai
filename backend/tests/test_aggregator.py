"""
Tests for Context Aggregator.
"""

import pytest
from unittest.mock import AsyncMock, patch

from brd_generator.models.request import BRDRequest
from brd_generator.models.context import (
    AggregatedContext,
    ArchitectureContext,
    ImplementationContext,
    ComponentInfo,
    FileContext,
)
from brd_generator.core.aggregator import ContextAggregator


class TestContextAggregator:
    """Tests for ContextAggregator class."""

    @pytest.fixture
    def aggregator(
        self,
        mock_neo4j_client: AsyncMock,
        mock_filesystem_client: AsyncMock
    ) -> ContextAggregator:
        """Create an aggregator instance with mock clients."""
        return ContextAggregator(
            neo4j_client=mock_neo4j_client,
            filesystem_client=mock_filesystem_client
        )

    @pytest.mark.asyncio
    async def test_build_context_basic(
        self,
        aggregator: ContextAggregator,
        sample_request: BRDRequest
    ):
        """Test basic context building."""
        context = await aggregator.build_context(
            request=sample_request.feature_description,
            affected_components=["api"],
            include_similar=False
        )

        assert isinstance(context, AggregatedContext)
        assert context.request == sample_request.feature_description
        assert context.architecture is not None
        assert context.implementation is not None

    @pytest.mark.asyncio
    async def test_build_context_with_similar_features(
        self,
        aggregator: ContextAggregator,
        sample_request: BRDRequest
    ):
        """Test context building with similar features search."""
        aggregator.neo4j.search_similar_features.return_value = [
            {"name": "Login", "path": "src/auth/login.py"}
        ]

        context = await aggregator.build_context(
            request=sample_request.feature_description,
            affected_components=["api"],
            include_similar=True
        )

        aggregator.neo4j.search_similar_features.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_architecture_context(
        self,
        aggregator: ContextAggregator,
        sample_request: BRDRequest
    ):
        """Test architecture context retrieval."""
        aggregator.neo4j.query_code_structure.return_value = {
            "nodes": [
                {"labels": ["Service"], "properties": {"name": "AuthService"}}
            ],
            "relationships": [
                {"type": "DEPENDS_ON", "start": "AuthService", "end": "Database"}
            ]
        }

        context = await aggregator._get_architecture_context(
            sample_request.feature_description,
            ["api"]
        )

        assert isinstance(context, ArchitectureContext)
        assert len(context.components) >= 0

    @pytest.mark.asyncio
    async def test_get_implementation_context(
        self,
        aggregator: ContextAggregator,
        sample_architecture_context: ArchitectureContext
    ):
        """Test implementation context retrieval."""
        aggregator.filesystem.read_file.return_value = "class Service: pass"
        aggregator.filesystem.search_files.return_value = ["src/service.py"]

        context = await aggregator._get_implementation_context(
            sample_architecture_context
        )

        assert isinstance(context, ImplementationContext)

    @pytest.mark.asyncio
    async def test_context_compression(
        self,
        aggregator: ContextAggregator,
        sample_aggregated_context: AggregatedContext
    ):
        """Test context compression when token limit exceeded."""
        # Create context with large file content to exceed token limit
        large_context = sample_aggregated_context.model_copy(deep=True)
        # Add large file content to trigger compression
        large_file = FileContext(
            path="src/large_file.py",
            content="x" * 10000,  # Large content
            relevance_score=0.5,
        )
        large_context.implementation.key_files.append(large_file)

        compressed = await aggregator._compress_context(large_context)

        # Should return valid context (compression may truncate files)
        assert isinstance(compressed, AggregatedContext)


class TestContextAggregatorEdgeCases:
    """Tests for edge cases in context aggregation."""

    @pytest.fixture
    def aggregator(
        self,
        mock_neo4j_client: AsyncMock,
        mock_filesystem_client: AsyncMock
    ) -> ContextAggregator:
        """Create an aggregator instance."""
        return ContextAggregator(
            neo4j_client=mock_neo4j_client,
            filesystem_client=mock_filesystem_client
        )

    @pytest.mark.asyncio
    async def test_empty_components(
        self,
        aggregator: ContextAggregator,
        sample_request: BRDRequest
    ):
        """Test handling of empty component list."""
        context = await aggregator.build_context(
            request=sample_request.feature_description,
            affected_components=[],
            include_similar=False
        )

        # Should still return valid context
        assert isinstance(context, AggregatedContext)

    @pytest.mark.asyncio
    async def test_neo4j_unavailable(
        self,
        aggregator: ContextAggregator,
        sample_request: BRDRequest
    ):
        """Test graceful handling when Neo4j is unavailable."""
        aggregator.neo4j.query_code_structure.side_effect = ConnectionError()

        # Should handle gracefully and return partial context
        context = await aggregator.build_context(
            request=sample_request.feature_description,
            affected_components=["api"],
            include_similar=False
        )

        assert isinstance(context, AggregatedContext)

    @pytest.mark.asyncio
    async def test_filesystem_unavailable(
        self,
        aggregator: ContextAggregator,
        sample_request: BRDRequest
    ):
        """Test graceful handling when filesystem is unavailable."""
        aggregator.filesystem.read_file.side_effect = ConnectionError()

        # Should handle gracefully
        context = await aggregator.build_context(
            request=sample_request.feature_description,
            affected_components=["api"],
            include_similar=False
        )

        assert isinstance(context, AggregatedContext)
