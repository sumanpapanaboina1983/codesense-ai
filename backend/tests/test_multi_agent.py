"""Tests for Multi-Agent BRD Architecture."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from brd_generator.models.verification import (
    Claim,
    ClaimType,
    CodeReference,
    EvidenceBundle,
    EvidenceItem,
    EvidenceType,
    HallucinationRisk,
    SectionVerificationResult,
    VerificationConfig,
    VerificationStatus,
)
from brd_generator.agents.base import AgentMessage, AgentRole, MessageType
from brd_generator.agents.brd_generator_agent import BRDGeneratorAgent
from brd_generator.agents.brd_verifier_agent import BRDVerifierAgent
from brd_generator.core.multi_agent_orchestrator import (
    MultiAgentOrchestrator,
    VerifiedBRDGenerator,
)


# =============================================================================
# Test Verification Models
# =============================================================================

class TestVerificationModels:
    """Tests for verification data models."""

    def test_code_reference(self):
        """Test CodeReference model."""
        ref = CodeReference(
            file_path="/src/services/user.ts",
            start_line=10,
            end_line=50,
            snippet="class UserService { }",
            entity_type="Class",
            entity_name="UserService",
        )

        assert ref.loc == 41
        assert "user.ts:10-50" in ref.to_string()
        assert "[41 LOC]" in ref.to_string()

    def test_evidence_item_confidence_level(self):
        """Test EvidenceItem confidence level calculation."""
        high = EvidenceItem(
            evidence_type=EvidenceType.CODE_REFERENCE,
            description="Test",
            confidence=0.9,
        )
        assert high.confidence_level.value == "high"

        medium = EvidenceItem(
            evidence_type=EvidenceType.CODE_REFERENCE,
            description="Test",
            confidence=0.6,
        )
        assert medium.confidence_level.value == "medium"

        low = EvidenceItem(
            evidence_type=EvidenceType.CODE_REFERENCE,
            description="Test",
            confidence=0.4,
        )
        assert low.confidence_level.value == "low"

    def test_claim_confidence_recalculation(self):
        """Test Claim confidence recalculation with evidence."""
        claim = Claim(
            text="The UserService handles authentication",
            section="technical_requirements",
        )

        # Initially unverified
        assert claim.status == VerificationStatus.UNVERIFIED
        assert claim.confidence_score == 0.0

        # Add supporting evidence
        claim.add_evidence(EvidenceItem(
            evidence_type=EvidenceType.CODE_REFERENCE,
            description="Found UserService class",
            confidence=0.9,
            supports_claim=True,
        ))

        # Should now be verified
        assert claim.confidence_score > 0.5
        assert claim.status in [VerificationStatus.VERIFIED, VerificationStatus.PARTIALLY_VERIFIED]

    def test_claim_with_contradicting_evidence(self):
        """Test Claim with contradicting evidence."""
        claim = Claim(
            text="The system uses MySQL database",
            section="technical_requirements",
        )

        # Add contradicting evidence
        claim.add_evidence(EvidenceItem(
            evidence_type=EvidenceType.CODE_REFERENCE,
            description="Found PostgreSQL configuration",
            confidence=0.95,
            supports_claim=False,
        ))

        assert claim.status == VerificationStatus.CONTRADICTED
        assert claim.hallucination_risk == HallucinationRisk.CRITICAL

    def test_section_verification_result(self):
        """Test SectionVerificationResult statistics."""
        result = SectionVerificationResult(section_name="business_context")

        # Add claims
        verified_claim = Claim(text="Claim 1", section="business_context")
        verified_claim.add_evidence(EvidenceItem(
            evidence_type=EvidenceType.CODE_REFERENCE,
            description="Evidence",
            confidence=0.9,
            supports_claim=True,
        ))

        unverified_claim = Claim(text="Claim 2", section="business_context")

        result.claims = [verified_claim, unverified_claim]
        result.calculate_stats()

        assert result.total_claims == 2
        assert result.verified_claims == 1
        assert result.unverified_claims == 1

    def test_evidence_bundle_overall_metrics(self):
        """Test EvidenceBundle overall metrics calculation."""
        bundle = EvidenceBundle(
            brd_id="BRD-0001",
            brd_title="Test BRD",
        )

        # Add sections
        section1 = SectionVerificationResult(section_name="section1")
        section1.total_claims = 5
        section1.verified_claims = 4
        section1.overall_confidence = 0.8
        section1.verification_status = VerificationStatus.PARTIALLY_VERIFIED

        section2 = SectionVerificationResult(section_name="section2")
        section2.total_claims = 3
        section2.verified_claims = 3
        section2.overall_confidence = 0.95
        section2.verification_status = VerificationStatus.VERIFIED

        bundle.sections = [section1, section2]
        bundle.calculate_overall_metrics()

        assert bundle.total_claims == 8
        assert bundle.verified_claims == 7
        assert bundle.overall_confidence > 0.7

    def test_evidence_bundle_regeneration_feedback(self):
        """Test EvidenceBundle regeneration feedback generation."""
        bundle = EvidenceBundle(
            brd_id="BRD-0001",
            brd_title="Test BRD",
        )

        # Add section with issues
        section = SectionVerificationResult(section_name="requirements")
        section.verification_status = VerificationStatus.UNVERIFIED
        section.overall_confidence = 0.3
        section.issues = ["Insufficient evidence", "Possible hallucination"]
        section.suggestions = ["Reference actual code components"]

        claim = Claim(
            text="The system uses advanced AI",
            section="requirements",
            feedback="No evidence of AI in codebase",
            suggested_correction="Remove AI claim or specify actual technology",
        )
        claim.status = VerificationStatus.UNVERIFIED
        section.claims = [claim]

        bundle.sections = [section]

        feedback = bundle.get_regeneration_feedback()

        assert "requirements" in feedback
        assert "Insufficient evidence" in feedback
        assert bundle.sections_to_regenerate == ["requirements"]


# =============================================================================
# Test BRD Generator Agent
# =============================================================================

class TestBRDGeneratorAgent:
    """Tests for BRD Generator Agent."""

    @pytest.fixture
    def mock_context(self):
        """Create mock aggregated context."""
        from brd_generator.models.context import (
            AggregatedContext,
            ArchitectureContext,
            ImplementationContext,
            ComponentInfo,
            KeyFileInfo,
        )

        return AggregatedContext(
            request="Add user authentication feature",
            architecture=ArchitectureContext(
                components=[
                    ComponentInfo(name="UserService", type="service"),
                    ComponentInfo(name="AuthController", type="controller"),
                ],
                api_contracts=[],
                dependencies=[],
            ),
            implementation=ImplementationContext(
                key_files=[
                    KeyFileInfo(path="/src/services/user.ts"),
                    KeyFileInfo(path="/src/controllers/auth.ts"),
                ],
            ),
            similar_features=[],
        )

    @pytest.mark.asyncio
    async def test_generator_initialization(self):
        """Test Generator Agent initialization."""
        agent = BRDGeneratorAgent()

        assert agent.role == AgentRole.GENERATOR
        assert agent.current_brd is None
        assert len(agent.sections_generated) == 0

    @pytest.mark.asyncio
    async def test_generator_mock_response(self):
        """Test Generator Agent mock response generation."""
        agent = BRDGeneratorAgent()

        # Test different section prompts
        exec_prompt = "Generate executive_summary section"
        response = agent._generate_mock_response(exec_prompt)
        assert "feature" in response.lower() or "business" in response.lower()

        func_prompt = "Generate functional_requirements section"
        response = agent._generate_mock_response(func_prompt)
        assert "FR-" in response

    @pytest.mark.asyncio
    async def test_generator_section_status(self, mock_context):
        """Test Generator Agent section status tracking."""
        agent = BRDGeneratorAgent(context=mock_context)

        status = agent.get_section_status()

        assert "executive_summary" in status
        assert status["executive_summary"]["generated"] is False
        assert status["executive_summary"]["approved"] is False


# =============================================================================
# Test BRD Verifier Agent
# =============================================================================

class TestBRDVerifierAgent:
    """Tests for BRD Verifier Agent."""

    @pytest.mark.asyncio
    async def test_verifier_initialization(self):
        """Test Verifier Agent initialization."""
        agent = BRDVerifierAgent()

        assert agent.role == AgentRole.VERIFIER
        assert agent.current_bundle is None

    @pytest.mark.asyncio
    async def test_verifier_claim_extraction_mock(self):
        """Test Verifier Agent mock claim extraction."""
        agent = BRDVerifierAgent()

        response = agent._generate_mock_response("Extract claims from section")

        assert "CLAIM:" in response
        assert "TYPE:" in response

    def test_verifier_entity_extraction(self):
        """Test entity extraction from text."""
        agent = BRDVerifierAgent()

        text = "The UserService class in /src/services/user_service.py handles authentication"
        entities = agent._extract_entities_from_text(text)

        assert "UserService" in entities
        assert any("user_service" in e for e in entities)

    def test_verifier_keyword_extraction(self):
        """Test keyword extraction from text."""
        agent = BRDVerifierAgent()

        text = "The authentication service validates user credentials against the database"
        keywords = agent._extract_keywords(text)

        assert "authentication" in keywords
        assert "validates" in keywords
        assert "the" not in keywords  # Stopword

    def test_verifier_technical_pattern_extraction(self):
        """Test technical pattern extraction."""
        agent = BRDVerifierAgent()

        text = "The API endpoint /api/v1/users uses @Controller annotation"
        patterns = agent._extract_technical_patterns(text)

        assert "/api/v1/users" in patterns
        assert "@Controller" in patterns


# =============================================================================
# Test Multi-Agent Orchestrator
# =============================================================================

class TestMultiAgentOrchestrator:
    """Tests for Multi-Agent Orchestrator."""

    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self):
        """Test Orchestrator initialization."""
        orchestrator = MultiAgentOrchestrator(max_iterations=3)

        await orchestrator.initialize()

        assert orchestrator.generator is not None
        assert orchestrator.verifier is not None
        assert orchestrator.max_iterations == 3

    @pytest.mark.asyncio
    async def test_orchestrator_cleanup(self):
        """Test Orchestrator cleanup."""
        orchestrator = MultiAgentOrchestrator()
        await orchestrator.initialize()

        await orchestrator.cleanup()

        # Should not raise exceptions

    def test_orchestrator_verification_status(self):
        """Test Orchestrator verification status."""
        orchestrator = MultiAgentOrchestrator(max_iterations=3)

        status = orchestrator.get_verification_status()

        assert status["is_running"] is False
        assert status["max_iterations"] == 3
        assert status["brd_generated"] is False


# =============================================================================
# Test Verified BRD Generator
# =============================================================================

class TestVerifiedBRDGenerator:
    """Tests for high-level Verified BRD Generator."""

    @pytest.mark.asyncio
    async def test_generator_initialization(self):
        """Test VerifiedBRDGenerator initialization."""
        generator = VerifiedBRDGenerator(max_iterations=2)

        assert generator.orchestrator is not None
        assert generator.orchestrator.max_iterations == 2

    def test_generator_no_evidence_trail_before_generation(self):
        """Test evidence trail unavailable before generation."""
        generator = VerifiedBRDGenerator()

        trail = generator.show_evidence_trail()
        assert "No evidence available" in trail

    def test_generator_confidence_score_before_generation(self):
        """Test confidence score before generation."""
        generator = VerifiedBRDGenerator()

        score = generator.get_confidence_score()
        assert score == 0.0

    def test_generator_was_verified_before_generation(self):
        """Test was_verified before generation."""
        generator = VerifiedBRDGenerator()

        verified = generator.was_verified()
        assert verified is False


# =============================================================================
# Test Agent Messages
# =============================================================================

class TestAgentMessages:
    """Tests for agent message handling."""

    def test_message_creation(self):
        """Test AgentMessage creation."""
        message = AgentMessage(
            message_type=MessageType.BRD_SECTION,
            sender=AgentRole.GENERATOR,
            recipient=AgentRole.VERIFIER,
            section_name="executive_summary",
            content="This is the executive summary...",
            iteration=1,
        )

        assert message.message_type == MessageType.BRD_SECTION
        assert message.section_name == "executive_summary"
        assert message.iteration == 1

    def test_message_metadata(self):
        """Test AgentMessage metadata."""
        message = AgentMessage(
            message_type=MessageType.VERIFICATION_RESULT,
            sender=AgentRole.VERIFIER,
            recipient=AgentRole.ORCHESTRATOR,
            metadata={
                "confidence": 0.85,
                "claims_verified": 10,
            },
        )

        assert message.metadata["confidence"] == 0.85


# =============================================================================
# Test Evidence Trail Formatting
# =============================================================================

class TestEvidenceTrailFormatting:
    """Tests for evidence trail formatting."""

    def test_evidence_trail_basic_format(self):
        """Test basic evidence trail formatting."""
        bundle = EvidenceBundle(
            brd_id="BRD-0001",
            brd_title="Test BRD",
            overall_confidence=0.85,
            overall_status=VerificationStatus.VERIFIED,
            hallucination_risk=HallucinationRisk.LOW,
            total_claims=10,
            verified_claims=8,
            evidence_sources=["neo4j", "filesystem"],
        )

        trail = bundle.to_evidence_trail(include_details=False)

        assert "EVIDENCE TRAIL" in trail
        assert "BRD-0001" in trail
        assert "0.85" in trail
        assert "neo4j" in trail

    def test_evidence_trail_with_details(self):
        """Test evidence trail with full details."""
        bundle = EvidenceBundle(
            brd_id="BRD-0001",
            brd_title="Test BRD",
        )

        # Add a section with claims and evidence
        section = SectionVerificationResult(section_name="requirements")

        claim = Claim(
            text="The system uses UserService for authentication",
            section="requirements",
        )
        claim.add_evidence(EvidenceItem(
            evidence_type=EvidenceType.CODE_REFERENCE,
            description="Found UserService class",
            confidence=0.9,
            code_references=[CodeReference(
                file_path="/src/services/user.ts",
                start_line=10,
                end_line=50,
            )],
        ))

        section.claims = [claim]
        section.calculate_stats()
        bundle.sections = [section]
        bundle.calculate_overall_metrics()

        trail = bundle.to_evidence_trail(include_details=True)

        assert "requirements" in trail.lower()
        assert "UserService" in trail
        assert "user.ts" in trail


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for multi-agent system."""

    @pytest.mark.asyncio
    async def test_full_verification_flow_mock(self):
        """Test full verification flow with mocks."""
        # This test verifies the flow works without actual LLM/Neo4j

        orchestrator = MultiAgentOrchestrator(
            max_iterations=1,  # Quick test
        )

        await orchestrator.initialize()

        # Verify agents are ready
        gen_status = orchestrator.get_generator_status()
        ver_status = orchestrator.get_verifier_status()

        assert gen_status["role"] == "generator"
        assert ver_status["role"] == "verifier"

        await orchestrator.cleanup()
