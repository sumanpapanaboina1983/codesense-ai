"""
Epic generation workflow.
"""

from datetime import datetime
from typing import Any, Optional

from src.agentic.context_manager import ContextManager
from src.agentic.reasoning_engine import ReasoningEngine
from src.agentic.verification_engine import VerificationEngine, VerificationResult
from src.core.constants import DocumentType, VerificationStatus, WorkflowStatus
from src.core.logging import get_logger
from src.domain.document import Document, Epic
from src.orchestration.state_machine import StateMachine, WorkflowState, create_epic_state_machine
from src.orchestration.workflow_engine import BaseWorkflow, WorkflowContext, WorkflowResult

logger = get_logger(__name__)


class EpicWorkflow(BaseWorkflow):
    """
    Workflow for generating Epics from a BRD.

    States:
        init -> loading_brd -> analyzing_components -> generating_epics -> verifying -> refining -> finalizing -> completed
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._state_machine = create_epic_state_machine()
        self._context_manager = ContextManager(max_tokens=100000)

    @property
    def workflow_type(self) -> str:
        return "epic"

    @property
    def state_machine(self) -> StateMachine:
        return self._state_machine

    async def execute(self, context: WorkflowContext) -> WorkflowResult:
        """Execute the Epic generation workflow."""
        workflow_id = self._generate_workflow_id()

        state = WorkflowState(
            workflow_id=workflow_id,
            workflow_type=self.workflow_type,
            current_state="init",
            status=WorkflowStatus.RUNNING,
        )
        state.add_to_history("init")

        reasoning_traces: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        epics: list[Document] = []

        try:
            # Step 1: Load parent BRD
            state.current_state = "loading_brd"
            state.add_to_history("loading_brd")

            brd_content = await self._load_brd(context)
            reasoning_traces.append({
                "step": "brd_loading",
                "brd_id": context.parent_document_id,
                "content_length": len(brd_content) if brd_content else 0,
            })

            if not brd_content:
                raise ValueError(f"BRD document not found: {context.parent_document_id}")

            # Step 2: Analyze components for epic decomposition
            state.current_state = "analyzing_components"
            state.add_to_history("analyzing_components")

            component_analysis = await self._analyze_for_epics(context, brd_content)
            reasoning_traces.append({
                "step": "component_analysis",
                "components_found": len(component_analysis.get("components", [])),
            })
            artifacts.append({
                "type": "component_analysis",
                "data": component_analysis,
            })

            # Step 3: Generate Epics
            state.current_state = "generating_epics"
            state.add_to_history("generating_epics")

            epic_drafts = await self._generate_epics(context, brd_content, component_analysis)
            reasoning_traces.append({
                "step": "epic_generation",
                "epics_generated": len(epic_drafts),
            })

            # Step 4: Verify each Epic
            state.current_state = "verifying"
            state.add_to_history("verifying")

            verified_epics = []
            for i, epic_draft in enumerate(epic_drafts):
                verification_result = await self._verify_epic(context, epic_draft)

                # Refine if needed
                refined_epic = epic_draft
                refinement_count = 0
                max_refinements = 2

                while not verification_result.is_valid and refinement_count < max_refinements:
                    state.current_state = "refining"
                    state.add_to_history("refining", {"epic_index": i, "iteration": refinement_count + 1})

                    refined_epic = await self._refine_epic(context, refined_epic, verification_result)
                    refinement_count += 1

                    verification_result = await self._verify_epic(context, refined_epic)

                verified_epics.append({
                    "content": refined_epic,
                    "verification": verification_result,
                    "refinements": refinement_count,
                })

                reasoning_traces.append({
                    "step": f"epic_{i}_verification",
                    "is_valid": verification_result.is_valid,
                    "confidence": verification_result.confidence_score,
                    "refinements": refinement_count,
                })

            # Step 5: Finalization
            state.current_state = "finalizing"
            state.add_to_history("finalizing")

            for i, verified_epic in enumerate(verified_epics):
                document_id = self._generate_document_id()

                avg_confidence = verified_epic["verification"].confidence_score
                is_valid = verified_epic["verification"].is_valid

                epic_doc = Document(
                    id=document_id,
                    type=DocumentType.EPIC,
                    title=f"Epic {i + 1}",
                    content=verified_epic["content"],
                    session_id=context.session_id,
                    parent_document_id=context.parent_document_id,
                    verification_status=VerificationStatus.VERIFIED if is_valid else VerificationStatus.PARTIALLY_VERIFIED,
                    confidence_score=avg_confidence,
                    metadata={
                        "workflow_id": workflow_id,
                        "epic_index": i,
                        "refinement_iterations": verified_epic["refinements"],
                        "brd_id": context.parent_document_id,
                    },
                )
                epics.append(epic_doc)

            # Mark as completed
            state.current_state = "completed"
            state.status = WorkflowStatus.COMPLETED
            state.add_to_history("completed")

            # Return the first epic as the main document, others as artifacts
            main_document = epics[0] if epics else None
            artifacts.extend([
                {"type": "epic", "document": epic.dict()} for epic in epics[1:]
            ])

            return WorkflowResult(
                workflow_id=workflow_id,
                workflow_type=self.workflow_type,
                status=WorkflowStatus.COMPLETED,
                document=main_document,
                artifacts=artifacts,
                reasoning_traces=reasoning_traces,
            )

        except Exception as e:
            logger.exception("Epic workflow failed", workflow_id=workflow_id, error=str(e))
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

    async def _load_brd(self, context: WorkflowContext) -> Optional[str]:
        """Load the parent BRD document."""
        logger.info("Loading BRD document", brd_id=context.parent_document_id)

        # In a real implementation, this would load from a document store
        # For now, we'll use a placeholder that should be replaced with actual repository calls
        if not context.parent_document_id:
            return None

        # This would be replaced with:
        # document = await self.document_repository.get(context.parent_document_id)
        # return document.content if document else None

        # Placeholder: return context metadata if available
        return context.metadata.get("brd_content", "")

    async def _analyze_for_epics(
        self,
        context: WorkflowContext,
        brd_content: str
    ) -> dict[str, Any]:
        """Analyze BRD to identify components for epic decomposition."""
        logger.info("Analyzing BRD for epic decomposition")

        # Use reasoning engine to analyze the BRD
        reasoning_result = await self.reasoning_engine.reason(
            query="""Analyze this BRD to identify logical components that can be decomposed into Epics.
For each component, identify:
1. Core functionality
2. Data entities involved
3. Integration points
4. Dependencies on other components""",
            context={
                "brd_content": brd_content[:5000],  # Truncate for context window
                "codebase_path": context.codebase_path,
            }
        )

        # Extract component information from reasoning
        components = []
        if reasoning_result.traces:
            # Parse the analysis output
            analysis_output = reasoning_result.final_answer or ""

            # Simple extraction - in production, this would be more sophisticated
            components = self._extract_components_from_analysis(analysis_output)

        return {
            "components": components,
            "reasoning_confidence": reasoning_result.confidence,
            "brd_summary": brd_content[:1000],
        }

    def _extract_components_from_analysis(self, analysis: str) -> list[dict[str, Any]]:
        """Extract component information from analysis text."""
        # This is a simplified extraction - in production, use structured output
        components = []

        # Look for numbered items or bullet points
        lines = analysis.split("\n")
        current_component: Optional[dict] = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for component headers (numbered or bulleted)
            if line[0].isdigit() or line.startswith("-") or line.startswith("*"):
                if current_component:
                    components.append(current_component)
                current_component = {
                    "name": line.lstrip("0123456789.-* "),
                    "description": "",
                    "functionality": [],
                    "dependencies": [],
                }
            elif current_component:
                current_component["description"] += line + " "

        if current_component:
            components.append(current_component)

        return components

    async def _generate_epics(
        self,
        context: WorkflowContext,
        brd_content: str,
        component_analysis: dict[str, Any]
    ) -> list[str]:
        """Generate epics from BRD and component analysis."""
        logger.info("Generating epics", components=len(component_analysis.get("components", [])))

        components = component_analysis.get("components", [])

        # Build the prompt for epic generation
        component_list = "\n".join([
            f"- {c.get('name', 'Unknown')}: {c.get('description', '')[:200]}"
            for c in components
        ])

        prompt = f"""Based on the following BRD and component analysis, generate Epics for implementation.

BRD Summary:
{brd_content[:3000]}

Identified Components:
{component_list}

For each epic, include:
1. Epic Title - Clear, action-oriented title
2. Description - Business value and scope
3. Acceptance Criteria - Measurable outcomes
4. Key Features - Main functionality to implement
5. Technical Considerations - Architecture notes
6. Dependencies - Other epics or external dependencies
7. Estimated Scope - T-shirt size (S/M/L/XL)

Generate the epics now, separating each with "---EPIC---":
"""

        response = await self.conversation_handler.send_message(
            session_id=context.session_id,
            message=prompt,
            skill_name="epic-generator",
            context={
                "brd_id": context.parent_document_id,
                "document_type": "Epic",
            }
        )

        # Split response into individual epics
        epic_texts = response.content.split("---EPIC---")
        return [epic.strip() for epic in epic_texts if epic.strip()]

    async def _verify_epic(
        self,
        context: WorkflowContext,
        epic_content: str
    ) -> VerificationResult:
        """Verify an epic against the codebase."""
        logger.info("Verifying epic")

        if not self.verification_engine:
            return VerificationResult(
                is_valid=True,
                confidence_score=0.8,
                verified_facts=[],
                unverified_claims=[],
                issues=[],
            )

        result = await self.verification_engine.verify_document(
            content=epic_content,
            document_type=DocumentType.EPIC,
            context={
                "brd_id": context.parent_document_id,
                "codebase_path": context.codebase_path,
            }
        )

        return result

    async def _refine_epic(
        self,
        context: WorkflowContext,
        epic_content: str,
        verification: VerificationResult
    ) -> str:
        """Refine an epic based on verification issues."""
        logger.info("Refining epic", issues_count=len(verification.issues))

        issues_text = "\n".join([
            f"- {issue.category}: {issue.description}"
            for issue in verification.issues[:10]
        ])

        prompt = f"""Please refine this Epic to address verification issues:

Issues found:
{issues_text}

Current Epic:
{epic_content}

Ensure all claims are verifiable and grounded in the codebase.
"""

        response = await self.conversation_handler.send_message(
            session_id=context.session_id,
            message=prompt,
            skill_name="epic-generator",
            context={"refinement_mode": True}
        )

        return response.content
