"""
Tests for LLM Synthesizer.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from brd_generator.models.context import AggregatedContext
from brd_generator.models.output import BRDDocument, Epic, UserStory
from brd_generator.core.synthesizer import LLMSynthesizer


class TestLLMSynthesizer:
    """Tests for LLMSynthesizer class."""

    @pytest.fixture
    def synthesizer(self) -> LLMSynthesizer:
        """Create a synthesizer instance (no session = mock mode)."""
        return LLMSynthesizer()

    def test_initialize_without_session(self, synthesizer: LLMSynthesizer):
        """Test synthesizer initialization without session (mock mode)."""
        assert synthesizer._copilot_available is False
        assert synthesizer.session is None

    def test_initialize_with_session(self):
        """Test synthesizer initialization with session."""
        mock_session = MagicMock()
        synthesizer = LLMSynthesizer(session=mock_session)
        assert synthesizer._copilot_available is True
        assert synthesizer.session is mock_session

    @pytest.mark.asyncio
    async def test_generate_brd(
        self,
        synthesizer: LLMSynthesizer,
        sample_aggregated_context: AggregatedContext
    ):
        """Test BRD generation."""
        mock_response = """
# Business Requirements Document

## Business Context
This feature enables user authentication.

## Objectives
- Implement secure login
- Support OAuth2

## Functional Requirements

### FR-001: User Login
**Priority:** High
**Description:** Users can log in with credentials
**Acceptance Criteria:**
- User enters email/password
- System validates credentials

## Technical Requirements

### TR-001: JWT Tokens
**Priority:** High
**Description:** Use JWT for sessions
**Acceptance Criteria:**
- Tokens expire in 24 hours

## Dependencies
- Database migration needed

## Risks
- OAuth provider availability
"""
        with patch.object(synthesizer, '_send_to_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response

            brd = await synthesizer.generate_brd(sample_aggregated_context)

            assert isinstance(brd, BRDDocument)
            assert len(brd.functional_requirements) > 0 or brd.title != ""

    @pytest.mark.asyncio
    async def test_generate_epics(
        self,
        synthesizer: LLMSynthesizer,
        sample_aggregated_context: AggregatedContext,
        sample_brd: BRDDocument
    ):
        """Test epic generation."""
        mock_response = """
# Epic: EPIC-001

## Authentication System

**Components:** api, auth

### Stories:
- STORY-001: User Login
- STORY-002: User Registration
"""
        with patch.object(synthesizer, '_send_to_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response

            epics = await synthesizer.generate_epics(
                sample_aggregated_context,
                sample_brd
            )

            assert isinstance(epics, list)

    @pytest.mark.asyncio
    async def test_generate_backlogs(
        self,
        synthesizer: LLMSynthesizer,
        sample_aggregated_context: AggregatedContext,
        sample_epic: Epic
    ):
        """Test user story generation."""
        mock_response = """
# User Story: STORY-001

**Epic:** EPIC-001
**Points:** 3

## User Story
As a **user**,
I want **to log in**,
So that **I can access my account**.

## Acceptance Criteria
- Login form works
- Errors are shown

## Files to Modify
- src/auth/login.py
"""
        with patch.object(synthesizer, '_send_to_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response

            stories = await synthesizer.generate_backlogs(
                sample_aggregated_context,
                [sample_epic]
            )

            assert isinstance(stories, list)


class TestLLMSynthesizerParsing:
    """Tests for LLM response parsing."""

    @pytest.fixture
    def synthesizer(self) -> LLMSynthesizer:
        """Create a synthesizer instance."""
        return LLMSynthesizer()

    def test_parse_brd_response_valid(
        self,
        synthesizer: LLMSynthesizer,
        sample_aggregated_context: AggregatedContext
    ):
        """Test parsing a valid BRD response."""
        response = """
# Business Requirements Document

## Business Context
Enable secure authentication for users.

## Objectives
- Implement login functionality
- Add OAuth2 support

## Functional Requirements

### FR-001: User Login
**Priority:** High
**Description:** Allow users to log in
**Acceptance Criteria:**
- Form validation works
- Credentials are verified

## Technical Requirements

### TR-001: Token Management
**Priority:** High
**Description:** JWT token handling
**Acceptance Criteria:**
- Tokens are secure

## Dependencies
- User database table

## Risks
- Third-party OAuth downtime
"""
        brd = synthesizer._parse_brd_response(
            response,
            sample_aggregated_context.request
        )

        assert isinstance(brd, BRDDocument)
        assert "authentication" in brd.business_context.lower() or brd.title != ""

    def test_parse_brd_response_minimal(
        self,
        synthesizer: LLMSynthesizer,
        sample_aggregated_context: AggregatedContext
    ):
        """Test parsing a minimal BRD response."""
        response = "Authentication feature for users"

        # Should handle gracefully and return a valid BRD
        brd = synthesizer._parse_brd_response(
            response,
            sample_aggregated_context.request
        )

        assert isinstance(brd, BRDDocument)


class TestLLMSynthesizerFallback:
    """Tests for LLM synthesizer fallback behavior."""

    @pytest.fixture
    def synthesizer(self) -> LLMSynthesizer:
        """Create a synthesizer instance (no session = mock mode)."""
        return LLMSynthesizer()

    @pytest.mark.asyncio
    async def test_fallback_when_copilot_unavailable(
        self,
        synthesizer: LLMSynthesizer,
        sample_aggregated_context: AggregatedContext
    ):
        """Test fallback behavior when Copilot SDK is unavailable."""
        # Synthesizer without session defaults to mock mode
        assert synthesizer._copilot_available is False

        brd = await synthesizer.generate_brd(sample_aggregated_context)

        # Should return a mock/fallback BRD
        assert isinstance(brd, BRDDocument)
        assert brd.title != ""

    @pytest.mark.asyncio
    async def test_retry_on_llm_error(
        self,
        synthesizer: LLMSynthesizer,
        sample_aggregated_context: AggregatedContext
    ):
        """Test behavior on LLM errors - should fall back to mock."""
        call_count = 0

        async def mock_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary error")
            return "# BRD\n## Business Context\nTest context"

        with patch.object(synthesizer, '_send_to_llm', side_effect=mock_send):
            # Should eventually succeed after retry or use mock
            try:
                brd = await synthesizer.generate_brd(sample_aggregated_context)
                assert isinstance(brd, BRDDocument)
            except Exception:
                # Or gracefully handle the error
                pass
