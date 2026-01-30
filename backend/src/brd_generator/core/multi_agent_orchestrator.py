"""Multi-Agent Orchestrator for BRD Generation and Verification.

AGENTIC ARCHITECTURE:
- Generator Agent uses tools (Neo4j, Filesystem) to dynamically gather context
- Verifier Agent uses tools to validate claims against codebase
- No hardcoded queries - LLM decides what to query via agentic loop
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional, TYPE_CHECKING

from ..agents.base import AgentMessage, AgentRole, MessageType
from ..agents.brd_generator_agent import BRDGeneratorAgent
from ..agents.brd_verifier_agent import BRDVerifierAgent
from ..models.context import AggregatedContext
from ..models.output import BRDDocument, BRDOutput
from ..models.verification import EvidenceBundle, VerificationConfig
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from .tool_registry import ToolRegistry
from .skill_loader import SkillLoader
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from .template_parser import ParsedBRDTemplate

logger = get_logger(__name__)


class MultiAgentOrchestrator:
    """
    Orchestrates the multi-agent BRD generation and verification process.

    Flow:
    1. Generator creates BRD sections iteratively
    2. Verifier extracts claims and validates against codebase
    3. If verification fails, feedback is sent to Generator for regeneration
    4. Loop continues until BRD passes verification or max iterations reached

    Evidence Trail:
    - Hidden by default
    - Can be retrieved on request via get_evidence_trail()
    """

    def __init__(
        self,
        copilot_session: Any = None,
        neo4j_client: Optional[Neo4jMCPClient] = None,
        filesystem_client: Optional[FilesystemMCPClient] = None,
        verification_config: Optional[VerificationConfig] = None,
        max_iterations: int = 3,
        show_evidence_by_default: bool = False,
        parsed_template: Optional["ParsedBRDTemplate"] = None,
    ):
        """
        Initialize the Multi-Agent Orchestrator.

        Args:
            copilot_session: Copilot SDK session for LLM access
            neo4j_client: Neo4j MCP client for code graph queries
            filesystem_client: Filesystem MCP client for file access
            verification_config: Configuration for verification process
            max_iterations: Maximum number of generator-verifier iterations
            show_evidence_by_default: If True, include evidence in output
            parsed_template: Parsed BRD template for template-driven generation
        """
        self.copilot_session = copilot_session
        self.neo4j_client = neo4j_client
        self.filesystem_client = filesystem_client
        self.verification_config = verification_config or VerificationConfig(
            max_iterations=max_iterations
        )
        self.max_iterations = max_iterations
        self.show_evidence_by_default = show_evidence_by_default
        self.parsed_template = parsed_template

        # Tool Registry for agentic tool calling
        self.tool_registry: Optional[ToolRegistry] = None

        # Skill Loader for dynamic skill matching
        self.skill_loader = SkillLoader()

        # Agents
        self.generator: Optional[BRDGeneratorAgent] = None
        self.verifier: Optional[BRDVerifierAgent] = None

        # State
        self.current_iteration = 0
        self.is_running = False
        self.final_brd: Optional[BRDDocument] = None
        self.final_evidence: Optional[EvidenceBundle] = None

        # Message routing
        self._message_handlers = {
            MessageType.BRD_SECTION: self._route_to_verifier,
            MessageType.BRD_COMPLETE: self._handle_brd_complete,
            MessageType.FEEDBACK: self._route_to_generator,
            MessageType.APPROVED: self._route_to_generator,
            MessageType.VERIFICATION_RESULT: self._handle_verification_result,
            MessageType.ERROR: self._handle_error,
        }

        # Metrics
        self.metrics = {
            "total_iterations": 0,
            "sections_regenerated": 0,
            "claims_verified": 0,
            "claims_failed": 0,
            "total_time_ms": 0,
        }

    async def initialize(self) -> None:
        """Initialize the agents with SKILLS and AGENTIC TOOL CALLING support."""
        logger.info("Initializing Multi-Agent Orchestrator with skills and agentic tools")

        # Load skills
        self.skill_loader.load_skills()
        logger.info(f"Loaded skills: {list(self.skill_loader.skills.keys())}")

        # Get skill instructions for each agent
        generator_skill = self.skill_loader.get_skill("generate-brd")
        verifier_skill = self.skill_loader.get_skill("verify-brd")

        # Create Tool Registry for agentic tool calling
        if self.neo4j_client and self.filesystem_client:
            self.tool_registry = ToolRegistry(
                neo4j_client=self.neo4j_client,
                filesystem_client=self.filesystem_client,
            )
            logger.info("Tool Registry created with Neo4j and Filesystem tools")
        else:
            logger.warning("No MCP clients available - agents will run without tools")

        # Create Generator Agent with tools, template, and skill instructions
        generator_config = {
            "max_regenerations": self.max_iterations,
            "enable_agentic_tools": True,
            "max_tool_iterations": 15,
        }
        if generator_skill:
            generator_config["skill_instructions"] = generator_skill.instructions
            logger.info(f"Generator using skill: {generator_skill.name}")

        self.generator = BRDGeneratorAgent(
            copilot_session=self.copilot_session,
            tool_registry=self.tool_registry,
            parsed_template=self.parsed_template,
            config=generator_config,
        )

        if self.parsed_template:
            logger.info(f"Generator initialized with template: {len(self.parsed_template.sections)} sections")
        else:
            logger.info("Generator initialized with default template")

        # Create Verifier Agent with tools and skill instructions
        verifier_config = {
            "enable_agentic_tools": True,
            "max_tool_iterations": 10,
        }
        if hasattr(self.verification_config, '__dict__'):
            verifier_config.update(self.verification_config.__dict__)
        if verifier_skill:
            verifier_config["skill_instructions"] = verifier_skill.instructions
            logger.info(f"Verifier using skill: {verifier_skill.name}")

        self.verifier = BRDVerifierAgent(
            copilot_session=self.copilot_session,
            tool_registry=self.tool_registry,
            neo4j_client=self.neo4j_client,
            filesystem_client=self.filesystem_client,
            config=verifier_config,
        )

        logger.info("Multi-Agent Orchestrator initialized with skills and agentic tool support")

    async def generate_verified_brd(
        self,
        context: AggregatedContext,
    ) -> BRDOutput:
        """
        Generate a verified BRD through the multi-agent process.

        This is the main entry point for BRD generation.

        Args:
            context: Aggregated context from code analysis

        Returns:
            BRDOutput with verified BRD and optional evidence trail
        """
        if not self.generator or not self.verifier:
            await self.initialize()

        start_time = time.time()
        logger.info("Starting multi-agent BRD generation")

        # Set context for generator
        self.generator.set_context(context)

        # Reset state
        self.current_iteration = 0
        self.final_brd = None
        self.final_evidence = None
        self.is_running = True

        try:
            # Run the agent loop
            await self._run_agent_loop()

            # Build output
            elapsed_ms = int((time.time() - start_time) * 1000)
            self.metrics["total_time_ms"] = elapsed_ms

            output = self._build_output(context, elapsed_ms)

            logger.info(
                f"Multi-agent BRD generation complete in {elapsed_ms}ms "
                f"({self.metrics['total_iterations']} iterations)"
            )

            return output

        finally:
            self.is_running = False

    async def _run_agent_loop(self) -> None:
        """
        Run the agent communication loop.

        Generator and Verifier exchange messages until:
        1. BRD is fully verified and approved
        2. Maximum iterations reached
        3. An error occurs
        """
        self.current_iteration = 1
        self.metrics["total_iterations"] = 0

        # Start the generator
        await self.generator.deliver(AgentMessage(
            message_type=MessageType.START,
            sender=AgentRole.ORCHESTRATOR,
            recipient=AgentRole.GENERATOR,
            iteration=self.current_iteration,
        ))

        # Process messages until complete
        while self.is_running and self.current_iteration <= self.max_iterations:
            # Check for generator output
            gen_message = await self.generator.get_outgoing()
            if gen_message:
                await self._handle_message(gen_message)

            # Check for verifier output
            ver_message = await self.verifier.get_outgoing()
            if ver_message:
                await self._handle_message(ver_message)

            # Small delay to prevent busy waiting
            await asyncio.sleep(0.01)

            # Check if we're done
            if self.final_brd and self.final_evidence:
                if self.final_evidence.is_approved:
                    logger.info("BRD approved by verifier")
                    break
                elif self.current_iteration >= self.max_iterations:
                    logger.warning(f"Max iterations ({self.max_iterations}) reached")
                    break
                else:
                    # Start next iteration
                    self.current_iteration += 1
                    self.metrics["total_iterations"] = self.current_iteration

    async def _handle_message(self, message: AgentMessage) -> None:
        """Route and handle a message from an agent."""
        handler = self._message_handlers.get(message.message_type)
        if handler:
            await handler(message)
        else:
            logger.warning(f"No handler for message type: {message.message_type}")

    async def _route_to_verifier(self, message: AgentMessage) -> None:
        """Route a message to the verifier agent."""
        message.recipient = AgentRole.VERIFIER
        await self.verifier.deliver(message)

        # Process the message
        await self.verifier._handle_message(message)

    async def _route_to_generator(self, message: AgentMessage) -> None:
        """Route a message to the generator agent."""
        message.recipient = AgentRole.GENERATOR
        await self.generator.deliver(message)

        # Track regenerations
        if message.message_type == MessageType.FEEDBACK:
            self.metrics["sections_regenerated"] += 1

        # Process the message
        await self.generator._handle_message(message)

    async def _handle_brd_complete(self, message: AgentMessage) -> None:
        """Handle completed BRD from generator."""
        self.final_brd = message.content
        logger.info("Received complete BRD from generator")

        # Send to verifier for final check
        await self._route_to_verifier(message)

    async def _handle_verification_result(self, message: AgentMessage) -> None:
        """Handle verification result from verifier."""
        self.final_evidence = message.content

        # Update metrics
        if self.final_evidence:
            self.metrics["claims_verified"] = self.final_evidence.verified_claims
            self.metrics["claims_failed"] = (
                self.final_evidence.total_claims - self.final_evidence.verified_claims
            )

        if self.final_evidence and self.final_evidence.is_approved:
            logger.info("BRD verification passed!")
            self.is_running = False
        else:
            logger.info(
                f"BRD verification failed (confidence: "
                f"{self.final_evidence.overall_confidence:.2f if self.final_evidence else 0})"
            )

            # Check if we should retry
            if self.current_iteration < self.max_iterations:
                # Send feedback to generator for another iteration
                if self.final_evidence and self.final_evidence.sections_to_regenerate:
                    await self._route_to_generator(AgentMessage(
                        message_type=MessageType.VERIFICATION_RESULT,
                        sender=AgentRole.VERIFIER,
                        recipient=AgentRole.GENERATOR,
                        content=self.final_evidence,
                        iteration=self.current_iteration + 1,
                    ))

    async def _handle_error(self, message: AgentMessage) -> None:
        """Handle error messages."""
        logger.error(f"Agent error: {message.content}")
        self.is_running = False

    def _build_output(self, context: AggregatedContext, elapsed_ms: int) -> BRDOutput:
        """Build the final BRD output."""
        # Use final BRD or create a basic one
        if self.final_brd:
            brd = self.final_brd
        else:
            brd = BRDDocument(
                title=f"BRD: {context.request[:50]}",
                business_context="Generation incomplete",
                objectives=[],
            )

        # Build metadata
        metadata = {
            "generation_mode": "multi-agent-verified",
            "total_iterations": self.metrics["total_iterations"],
            "sections_regenerated": self.metrics["sections_regenerated"],
            "claims_verified": self.metrics["claims_verified"],
            "claims_failed": self.metrics["claims_failed"],
            "generation_time_ms": elapsed_ms,
            "verification_passed": self.final_evidence.is_approved if self.final_evidence else False,
            "overall_confidence": self.final_evidence.overall_confidence if self.final_evidence else 0,
            "hallucination_risk": self.final_evidence.hallucination_risk.value if self.final_evidence else "unknown",
        }

        # Include evidence summary if configured
        if self.show_evidence_by_default and self.final_evidence:
            metadata["evidence_summary"] = {
                "total_claims": self.final_evidence.total_claims,
                "verified_claims": self.final_evidence.verified_claims,
                "needs_sme_review": self.final_evidence.claims_needing_sme,
                "evidence_sources": self.final_evidence.evidence_sources,
            }

        return BRDOutput(
            brd=brd,
            epics=[],  # Generated separately
            backlogs=[],  # Generated separately
            metadata=metadata,
        )

    def get_evidence_trail(self, show_details: bool = True) -> str:
        """
        Get the evidence trail for the generated BRD.

        By default, evidence trail is hidden. Call this method to retrieve it.

        Args:
            show_details: If True, include full evidence details.
                        If False, just show summary.

        Returns:
            Formatted evidence trail string
        """
        if self.final_evidence:
            return self.final_evidence.to_evidence_trail(include_details=show_details)
        return "No evidence available. Run generate_verified_brd() first."

    def get_evidence_bundle(self) -> Optional[EvidenceBundle]:
        """Get the raw evidence bundle object."""
        return self.final_evidence

    def get_verification_status(self) -> dict[str, Any]:
        """Get the current verification status."""
        return {
            "is_running": self.is_running,
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
            "brd_generated": self.final_brd is not None,
            "verification_complete": self.final_evidence is not None,
            "is_approved": self.final_evidence.is_approved if self.final_evidence else False,
            "overall_confidence": self.final_evidence.overall_confidence if self.final_evidence else 0,
            "metrics": self.metrics,
        }

    def get_generator_status(self) -> dict[str, Any]:
        """Get the generator agent's status."""
        if self.generator:
            return {
                **self.generator.get_status(),
                "section_status": self.generator.get_section_status(),
            }
        return {"status": "not initialized"}

    def get_verifier_status(self) -> dict[str, Any]:
        """Get the verifier agent's status."""
        if self.verifier:
            return self.verifier.get_status()
        return {"status": "not initialized"}

    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self.generator:
            await self.generator.stop()
        if self.verifier:
            await self.verifier.stop()
        logger.info("Multi-Agent Orchestrator cleaned up")


class VerifiedBRDGenerator:
    """
    High-level interface for generating verified BRDs.

    This is the recommended way to generate BRDs with verification.
    It wraps the MultiAgentOrchestrator and provides a simple API.

    Supports TEMPLATE-DRIVEN generation:
    - Pass a parsed_template to customize BRD sections
    - Without a template, uses default section structure
    """

    def __init__(
        self,
        copilot_session: Any = None,
        neo4j_client: Optional[Neo4jMCPClient] = None,
        filesystem_client: Optional[FilesystemMCPClient] = None,
        max_iterations: int = 3,
        parsed_template: Optional["ParsedBRDTemplate"] = None,
    ):
        """
        Initialize the Verified BRD Generator.

        Args:
            copilot_session: Copilot SDK session for LLM access
            neo4j_client: Neo4j MCP client for code graph queries
            filesystem_client: Filesystem MCP client for file access
            max_iterations: Maximum verification iterations
            parsed_template: Parsed BRD template for template-driven generation
        """
        self.orchestrator = MultiAgentOrchestrator(
            copilot_session=copilot_session,
            neo4j_client=neo4j_client,
            filesystem_client=filesystem_client,
            max_iterations=max_iterations,
            parsed_template=parsed_template,
        )

        self._last_output: Optional[BRDOutput] = None

    async def generate(
        self,
        context: AggregatedContext,
    ) -> BRDOutput:
        """
        Generate a verified BRD.

        Args:
            context: Aggregated context from code analysis

        Returns:
            BRDOutput with verified BRD
        """
        output = await self.orchestrator.generate_verified_brd(context)
        self._last_output = output
        return output

    def show_evidence_trail(self, detailed: bool = True) -> str:
        """
        Get the evidence trail for the last generated BRD.

        This is the method to call when user requests to see the evidence.

        Args:
            detailed: If True, show full evidence details

        Returns:
            Formatted evidence trail
        """
        return self.orchestrator.get_evidence_trail(show_details=detailed)

    def get_confidence_score(self) -> float:
        """Get the overall confidence score."""
        evidence = self.orchestrator.get_evidence_bundle()
        return evidence.overall_confidence if evidence else 0.0

    def was_verified(self) -> bool:
        """Check if the BRD passed verification."""
        evidence = self.orchestrator.get_evidence_bundle()
        return evidence.is_approved if evidence else False

    def get_claims_needing_review(self) -> list[dict[str, Any]]:
        """Get claims that need SME review."""
        evidence = self.orchestrator.get_evidence_bundle()
        if not evidence:
            return []

        claims_to_review = []
        for section in evidence.sections:
            for claim in section.claims:
                if claim.needs_sme_review:
                    claims_to_review.append({
                        "section": section.section_name,
                        "claim": claim.text,
                        "reason": claim.sme_review_reason,
                        "confidence": claim.confidence_score,
                    })

        return claims_to_review

    async def cleanup(self) -> None:
        """Cleanup resources."""
        await self.orchestrator.cleanup()
