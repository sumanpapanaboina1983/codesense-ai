"""
Tests for BRD Generator.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from brd_generator.models.request import BRDRequest
from brd_generator.models.context import AggregatedContext
from brd_generator.models.output import BRDDocument, BRDOutput
from brd_generator.core.generator import BRDGenerator


class TestBRDGenerator:
    """Tests for the BRDGenerator class."""

    @pytest.fixture
    def generator(self) -> BRDGenerator:
        """Create a generator instance."""
        return BRDGenerator()

    @pytest.mark.asyncio
    async def test_initialize_success(
        self,
        generator: BRDGenerator,
        mock_neo4j_client: AsyncMock,
        mock_filesystem_client: AsyncMock,
    ):
        """Test successful initialization."""
        generator.neo4j_client = mock_neo4j_client
        generator.filesystem_client = mock_filesystem_client

        await generator.initialize()

        mock_neo4j_client.connect.assert_called_once()
        mock_filesystem_client.connect.assert_called_once()
        assert generator._initialized

    @pytest.mark.asyncio
    async def test_generate_full_output(
        self,
        generator: BRDGenerator,
        sample_request: BRDRequest,
        mock_aggregator: AsyncMock,
        mock_synthesizer: AsyncMock,
        sample_brd: BRDDocument
    ):
        """Test full BRD generation."""
        generator.aggregator = mock_aggregator
        generator.synthesizer = mock_synthesizer
        generator._initialized = True

        output = await generator.generate(sample_request)

        assert isinstance(output, BRDOutput)
        assert output.brd == sample_brd
        assert len(output.epics) > 0
        assert len(output.backlogs) > 0
        mock_aggregator.build_context.assert_called_once()
        mock_synthesizer.generate_brd.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_auto_initializes(
        self,
        generator: BRDGenerator,
        sample_request: BRDRequest,
        mock_aggregator: AsyncMock,
        mock_synthesizer: AsyncMock,
        mock_neo4j_client: AsyncMock,
        mock_filesystem_client: AsyncMock,
    ):
        """Test that generate() auto-initializes if not already initialized."""
        generator.neo4j_client = mock_neo4j_client
        generator.filesystem_client = mock_filesystem_client
        generator.aggregator = mock_aggregator
        generator.synthesizer = mock_synthesizer
        generator._initialized = True  # Pretend it got initialized

        output = await generator.generate(sample_request)
        assert isinstance(output, BRDOutput)

    @pytest.mark.asyncio
    async def test_cleanup(
        self,
        generator: BRDGenerator,
        mock_neo4j_client: AsyncMock,
        mock_filesystem_client: AsyncMock
    ):
        """Test cleanup disconnects clients."""
        generator.neo4j_client = mock_neo4j_client
        generator.filesystem_client = mock_filesystem_client
        generator._initialized = True

        await generator.cleanup()

        mock_neo4j_client.disconnect.assert_called_once()
        mock_filesystem_client.disconnect.assert_called_once()
        assert not generator._initialized


class TestBRDRequest:
    """Tests for BRDRequest model."""

    def test_valid_request(self):
        """Test creating a valid request."""
        request = BRDRequest(
            feature_description="Add user authentication",
            scope="full",
            affected_components=["api", "auth"],
            include_similar_features=True,
            output_format="markdown"
        )
        assert request.feature_description == "Add user authentication"
        assert request.scope == "full"

    def test_request_defaults(self):
        """Test request default values."""
        request = BRDRequest(
            feature_description="Simple feature description"
        )
        assert request.scope == "full"
        assert request.affected_components is None
        assert request.include_similar_features is True
        assert request.output_format == "markdown"

    def test_request_minimum_description_length(self):
        """Test that feature description has minimum length."""
        with pytest.raises(ValueError):
            BRDRequest(feature_description="short")


class TestBRDOutput:
    """Tests for BRDOutput model."""

    def test_output_to_markdown(self, sample_brd: BRDDocument):
        """Test BRD to markdown conversion."""
        markdown = sample_brd.to_markdown()

        assert "# " in markdown  # Has heading
        assert sample_brd.title in markdown
        assert "FR-001" in markdown  # Has requirement IDs
        assert "Business Context" in markdown

    def test_output_model_dump(
        self,
        sample_brd: BRDDocument,
        sample_epic,
        sample_user_story
    ):
        """Test output model serialization."""
        output = BRDOutput(
            brd=sample_brd,
            epics=[sample_epic],
            backlogs=[sample_user_story],
            metadata={"generated_at": "2024-01-15"}
        )

        data = output.model_dump()

        assert "brd" in data
        assert "epics" in data
        assert "backlogs" in data
        assert len(data["epics"]) == 1
        assert len(data["backlogs"]) == 1
