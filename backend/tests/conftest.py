"""
Pytest fixtures for BRD Generator tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from brd_generator.models.request import BRDRequest
from brd_generator.models.context import (
    AggregatedContext,
    ArchitectureContext,
    ImplementationContext,
    ComponentInfo,
    FileContext,
)
from brd_generator.models.output import (
    AcceptanceCriteria,
    BRDDocument,
    Epic,
    UserStory,
    Requirement,
)
from brd_generator.mcp_clients.neo4j_client import Neo4jMCPClient
from brd_generator.mcp_clients.filesystem_client import FilesystemMCPClient
from brd_generator.core.aggregator import ContextAggregator
from brd_generator.core.synthesizer import LLMSynthesizer
from brd_generator.core.generator import BRDGenerator


@pytest.fixture
def sample_request() -> BRDRequest:
    """Create a sample BRD request."""
    return BRDRequest(
        feature_description="Add user authentication with OAuth2 support",
        scope="standard",
        affected_components=["api", "auth", "database"],
        include_similar_features=True,
        output_format="markdown"
    )


@pytest.fixture
def sample_component() -> ComponentInfo:
    """Create a sample component info."""
    return ComponentInfo(
        name="AuthService",
        type="service",
        path="src/services/auth.py",
        dependencies=["UserRepository", "TokenManager"],
    )


@pytest.fixture
def sample_file_context() -> FileContext:
    """Create a sample file context."""
    return FileContext(
        path="src/services/auth.py",
        content="class AuthService:\n    def authenticate(self, user, password):\n        pass",
        summary="Authentication service class",
        relevance_score=0.9,
    )


@pytest.fixture
def sample_architecture_context(sample_component: ComponentInfo) -> ArchitectureContext:
    """Create a sample architecture context."""
    return ArchitectureContext(
        components=[sample_component],
        api_contracts=[],
        data_models=[],
        dependencies={"AuthService": ["UserRepository", "TokenManager"]}
    )


@pytest.fixture
def sample_implementation_context(sample_file_context: FileContext) -> ImplementationContext:
    """Create a sample implementation context."""
    return ImplementationContext(
        key_files=[sample_file_context],
        patterns=["singleton", "repository"],
    )


@pytest.fixture
def sample_aggregated_context(
    sample_request: BRDRequest,
    sample_architecture_context: ArchitectureContext,
    sample_implementation_context: ImplementationContext
) -> AggregatedContext:
    """Create a sample aggregated context."""
    return AggregatedContext(
        request=sample_request.feature_description,
        architecture=sample_architecture_context,
        implementation=sample_implementation_context,
        similar_features=[],
    )


@pytest.fixture
def sample_requirement() -> Requirement:
    """Create a sample requirement."""
    return Requirement(
        id="FR-001",
        title="User Login",
        description="Users should be able to log in using email and password",
        priority="high",
        acceptance_criteria=[
            AcceptanceCriteria(criterion="User can enter email and password"),
            AcceptanceCriteria(criterion="System validates credentials"),
            AcceptanceCriteria(criterion="User is redirected to dashboard on success"),
        ]
    )


@pytest.fixture
def sample_brd(sample_requirement: Requirement) -> BRDDocument:
    """Create a sample BRD document."""
    return BRDDocument(
        title="User Authentication Feature",
        version="1.0",
        business_context="Enable secure user authentication for the platform",
        objectives=["Implement secure login", "Support OAuth2"],
        functional_requirements=[sample_requirement],
        technical_requirements=[
            Requirement(
                id="TR-001",
                title="Token-based Auth",
                description="Use JWT tokens for session management",
                priority="high",
                acceptance_criteria=[
                    AcceptanceCriteria(criterion="JWT tokens expire in 24 hours")
                ]
            )
        ],
        dependencies=["Database migration for user table"],
        risks=["OAuth2 provider availability"]
    )


@pytest.fixture
def sample_epic() -> Epic:
    """Create a sample epic."""
    return Epic(
        id="EPIC-001",
        title="User Authentication",
        description="Implement complete user authentication system",
        components=["api", "auth"],
        estimated_effort="medium",
        stories=["STORY-001", "STORY-002"]
    )


@pytest.fixture
def sample_user_story() -> UserStory:
    """Create a sample user story."""
    return UserStory(
        id="STORY-001",
        epic_id="EPIC-001",
        title="User Login Form",
        description="Implement a login form for users to authenticate",
        as_a="registered user",
        i_want="to log in with my email and password",
        so_that="I can access my account",
        acceptance_criteria=[
            AcceptanceCriteria(criterion="Login form has email and password fields"),
            AcceptanceCriteria(criterion="Submit button triggers authentication"),
            AcceptanceCriteria(criterion="Error message shown for invalid credentials"),
        ],
        estimated_points=3,
        files_to_modify=["src/components/LoginForm.tsx", "src/api/auth.ts"]
    )


@pytest.fixture
def mock_neo4j_client() -> AsyncMock:
    """Create a mock Neo4j MCP client."""
    client = AsyncMock(spec=Neo4jMCPClient)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.health_check = AsyncMock(return_value=True)
    client.query_code_structure = AsyncMock(return_value={"nodes": [], "relationships": []})
    client.get_component_dependencies = AsyncMock(return_value={"dependencies": []})
    client.get_api_contracts = AsyncMock(return_value=[])
    client.search_similar_features = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_filesystem_client() -> AsyncMock:
    """Create a mock Filesystem MCP client."""
    client = AsyncMock(spec=FilesystemMCPClient)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.health_check = AsyncMock(return_value=True)
    client.read_file = AsyncMock(return_value="file content")
    client.list_directory = AsyncMock(return_value=[])
    client.search_files = AsyncMock(return_value=[])
    client.get_file_info = AsyncMock(return_value={})
    return client


@pytest.fixture
def mock_aggregator(sample_aggregated_context: AggregatedContext) -> AsyncMock:
    """Create a mock context aggregator."""
    aggregator = AsyncMock(spec=ContextAggregator)
    aggregator.build_context = AsyncMock(return_value=sample_aggregated_context)
    return aggregator


@pytest.fixture
def mock_synthesizer(
    sample_brd: BRDDocument,
    sample_epic: Epic,
    sample_user_story: UserStory
) -> AsyncMock:
    """Create a mock LLM synthesizer."""
    synthesizer = AsyncMock(spec=LLMSynthesizer)
    synthesizer.initialize = AsyncMock()
    synthesizer.generate_brd = AsyncMock(return_value=sample_brd)
    synthesizer.generate_epics = AsyncMock(return_value=[sample_epic])
    synthesizer.generate_backlogs = AsyncMock(return_value=[sample_user_story])
    return synthesizer
