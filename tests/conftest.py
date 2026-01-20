"""
Pytest configuration and fixtures.
"""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
from httpx import AsyncClient

from src.main import app


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_session_id() -> str:
    """Sample session ID for testing."""
    return "sess_test123456"


@pytest.fixture
def sample_document_id() -> str:
    """Sample document ID for testing."""
    return "doc_test123456"


@pytest.fixture
def sample_codebase_path() -> str:
    """Sample codebase path for testing."""
    return "/test/codebase"
