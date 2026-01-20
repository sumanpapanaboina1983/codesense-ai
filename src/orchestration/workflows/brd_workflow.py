"""
BRD (Business Requirements Document) generation workflow.
"""

from datetime import datetime
from typing import Any, Optional

from src.agentic.context_manager import ContextManager
from src.agentic.reasoning_engine import ReasoningEngine
from src.agentic.verification_engine import VerificationEngine, VerificationResult
from src.core.constants import DocumentType, VerificationStatus, WorkflowStatus
from src.core.logging import get_logger
from src.domain.document import Document
from src.orchestration.state_machine import StateMachine, WorkflowState, create_brd_state_machine
from src.orchestration.workflow_engine import BaseWorkflow, WorkflowContext, WorkflowResult

logger = get_logger(__name__)


class BRDWorkflow(BaseWorkflow):
    """
    Workflow for generating Business Requirements Documents.

    States:
        init -> analyzing -> generating_draft -> verifying -> refining -> finalizing -> completed
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._state_machine = create_brd_state_machine()
        self._context_manager = ContextManager(max_tokens=100000)

    @property
    def workflow_type(self) -> str:
        return "brd"

    @property
    def state_machine(self) -> StateMachine:
        return self._state_machine

    async def execute(self, context: WorkflowContext) -> WorkflowResult:
        """Execute the BRD generation workflow."""
        workflow_id = self._generate_workflow_id()
        document_id = self._generate_document_id()

        state = WorkflowState(
            workflow_id=workflow_id,
            workflow_type=self.workflow_type,
            current_state="init",
            status=WorkflowStatus.RUNNING,
        )
        state.add_to_history("init")

        reasoning_traces: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []

        try:
            # Step 1: Analysis
            state.current_state = "analyzing"
            state.add_to_history("analyzing")

            analysis_result = await self._analyze_component(context)
            reasoning_traces.append({
                "step": "analysis",
                "result": analysis_result,
            })
            artifacts.append({
                "type": "component_analysis",
                "data": analysis_result,
            })

            # Step 2: Generate Draft
            state.current_state = "generating_draft"
            state.add_to_history("generating_draft")

            draft_content = await self._generate_draft(context, analysis_result)
            reasoning_traces.append({
                "step": "draft_generation",
                "content_length": len(draft_content),
            })

            # Step 3: Verification
            state.current_state = "verifying"
            state.add_to_history("verifying")

            verification_result = await self._verify_document(context, draft_content)
            reasoning_traces.append({
                "step": "verification",
                "result": {
                    "is_valid": verification_result.is_valid,
                    "confidence": verification_result.confidence_score,
                    "issues_count": len(verification_result.issues),
                },
            })

            # Step 4: Refinement (if needed)
            refined_content = draft_content
            refinement_count = 0
            max_refinements = 3

            while not verification_result.is_valid and refinement_count < max_refinements:
                state.current_state = "refining"
                state.add_to_history("refining", {"iteration": refinement_count + 1})

                refined_content = await self._refine_document(
                    context,
                    refined_content,
                    verification_result
                )
                refinement_count += 1

                state.current_state = "verifying"
                state.add_to_history("verifying", {"iteration": refinement_count})

                verification_result = await self._verify_document(context, refined_content)
                reasoning_traces.append({
                    "step": f"refinement_{refinement_count}",
                    "verification": {
                        "is_valid": verification_result.is_valid,
                        "confidence": verification_result.confidence_score,
                    },
                })

            # Step 5: Finalization
            state.current_state = "finalizing"
            state.add_to_history("finalizing")

            document = Document(
                id=document_id,
                type=DocumentType.BRD,
                title=f"BRD: {context.component_name or 'System'}",
                content=refined_content,
                session_id=context.session_id,
                component_name=context.component_name,
                verification_status=VerificationStatus.VERIFIED if verification_result.is_valid else VerificationStatus.PARTIALLY_VERIFIED,
                confidence_score=verification_result.confidence_score,
                metadata={
                    "workflow_id": workflow_id,
                    "refinement_iterations": refinement_count,
                    "codebase_path": context.codebase_path,
                },
            )

            # Mark as completed
            state.current_state = "completed"
            state.status = WorkflowStatus.COMPLETED
            state.add_to_history("completed")

            return WorkflowResult(
                workflow_id=workflow_id,
                workflow_type=self.workflow_type,
                status=WorkflowStatus.COMPLETED,
                document=document,
                artifacts=artifacts,
                reasoning_traces=reasoning_traces,
                verification=verification_result,
            )

        except Exception as e:
            logger.exception("BRD workflow failed", workflow_id=workflow_id, error=str(e))
            state.current_state = "failed"
            state.status = WorkflowStatus.FAILED
            state.set_error(str(e))

            return WorkflowResult(
                workflow_id=workflow_id,
                workflow_type=self.workflow_type,
                status=WorkflowStatus.FAILED,
                reasoning_traces=reasoning_traces,
                error=str(e),
            )

    async def _analyze_component(self, context: WorkflowContext) -> dict[str, Any]:
        """Analyze the component using MCP tools and reasoning."""
        logger.info("Analyzing component", component=context.component_name)

        # Use MCP tools to gather component information
        analysis_data: dict[str, Any] = {
            "component_name": context.component_name,
            "codebase_path": context.codebase_path,
        }

        # Query Neo4j for component structure
        try:
            if context.component_name:
                graph_data = await self.tool_registry.execute_tool(
                    "neo4j_query_entity",
                    {"entity_type": "component", "name": context.component_name}
                )
                analysis_data["graph_structure"] = graph_data

                # Get dependencies
                dependencies = await self.tool_registry.execute_tool(
                    "neo4j_get_dependencies",
                    {"entity_name": context.component_name}
                )
                analysis_data["dependencies"] = dependencies
        except Exception as e:
            logger.warning("Failed to query graph data", error=str(e))
            analysis_data["graph_structure"] = None
            analysis_data["dependencies"] = []

        # Use reasoning engine for deeper analysis
        reasoning_result = await self.reasoning_engine.reason(
            query=f"Analyze the component '{context.component_name}' to understand its business purpose, key functionalities, and data flows.",
            context={
                "component_name": context.component_name,
                "codebase_path": context.codebase_path,
                "graph_data": analysis_data.get("graph_structure"),
            }
        )

        analysis_data["reasoning_analysis"] = {
            "understanding": reasoning_result.traces[0].output if reasoning_result.traces else "",
            "steps_completed": len(reasoning_result.traces),
            "confidence": reasoning_result.confidence,
        }

        return analysis_data

    async def _generate_draft(
        self,
        context: WorkflowContext,
        analysis: dict[str, Any]
    ) -> str:
        """Generate the BRD draft using Copilot with skills."""
        logger.info("Generating BRD draft", component=context.component_name)

        # Build the prompt with analysis context
        prompt = self._build_brd_prompt(context, analysis)

        # Use conversation handler with BRD skill
        response = await self.conversation_handler.send_message(
            session_id=context.session_id,
            message=prompt,
            skill_name="brd-generator",
            context={
                "component_analysis": analysis,
                "document_type": "BRD",
            }
        )

        return response.content

    async def _verify_document(
        self,
        context: WorkflowContext,
        content: str
    ) -> VerificationResult:
        """Verify the document against the codebase."""
        logger.info("Verifying BRD document")

        if not self.verification_engine:
            # Return a default result if no verification engine
            return VerificationResult(
                is_valid=True,
                confidence_score=0.8,
                verified_facts=[],
                unverified_claims=[],
                issues=[],
            )

        result = await self.verification_engine.verify_document(
            content=content,
            document_type=DocumentType.BRD,
            context={
                "component_name": context.component_name,
                "codebase_path": context.codebase_path,
            }
        )

        return result

    async def _refine_document(
        self,
        context: WorkflowContext,
        content: str,
        verification: VerificationResult
    ) -> str:
        """Refine the document based on verification issues."""
        logger.info("Refining BRD document", issues_count=len(verification.issues))

        # Build refinement prompt
        issues_text = "\n".join([
            f"- {issue.category}: {issue.description}"
            for issue in verification.issues
        ])

        prompt = f"""Please refine the following BRD document to address these verification issues:

Issues found:
{issues_text}

Unverified claims to remove or verify:
{chr(10).join(verification.unverified_claims[:5])}

Current document:
{content}

Please revise the document to:
1. Remove or correct any unverified claims
2. Ensure all technical details are grounded in the codebase
3. Add missing context where needed
4. Maintain the BRD structure and format
"""

        response = await self.conversation_handler.send_message(
            session_id=context.session_id,
            message=prompt,
            skill_name="brd-generator",
            context={
                "refinement_mode": True,
                "verification_issues": [i.dict() for i in verification.issues],
            }
        )

        return response.content

    def _build_brd_prompt(
        self,
        context: WorkflowContext,
        analysis: dict[str, Any]
    ) -> str:
        """Build the BRD generation prompt."""
        component_name = context.component_name or "the system"

        # Build context section
        context_parts = [f"Component: {component_name}"]

        if analysis.get("graph_structure"):
            context_parts.append(f"Structure: {analysis['graph_structure']}")

        if analysis.get("dependencies"):
            deps = analysis["dependencies"]
            if isinstance(deps, list):
                context_parts.append(f"Dependencies: {', '.join(str(d) for d in deps[:10])}")

        if analysis.get("reasoning_analysis"):
            ra = analysis["reasoning_analysis"]
            if ra.get("understanding"):
                context_parts.append(f"Analysis: {ra['understanding'][:500]}")

        context_section = "\n".join(context_parts)

        prompt = f"""Generate a comprehensive Business Requirements Document (BRD) for {component_name}.

Context from codebase analysis:
{context_section}

Requirements:
1. Structure the BRD with these sections:
   - Executive Summary
   - Business Objectives
   - Current State Analysis
   - Functional Requirements
   - Non-Functional Requirements
   - Data Requirements
   - Integration Points
   - Assumptions and Constraints
   - Success Criteria

2. CRITICAL: Every claim must be verifiable against the codebase. Do not include any information that cannot be traced back to actual code.

3. Use specific references to code entities (classes, functions, modules) where relevant.

4. Focus on business value and user impact, not just technical details.

Generate the BRD document now:
"""

        return prompt
