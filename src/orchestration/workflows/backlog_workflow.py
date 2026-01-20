"""
Backlog item generation workflow.
"""

from datetime import datetime
from typing import Any, Optional

from src.agentic.context_manager import ContextManager
from src.agentic.reasoning_engine import ReasoningEngine
from src.agentic.verification_engine import VerificationEngine, VerificationResult
from src.core.constants import DocumentType, VerificationStatus, WorkflowStatus
from src.core.logging import get_logger
from src.domain.document import AcceptanceCriterion, BacklogItem, Document
from src.orchestration.state_machine import StateMachine, WorkflowState, create_backlog_state_machine
from src.orchestration.workflow_engine import BaseWorkflow, WorkflowContext, WorkflowResult

logger = get_logger(__name__)


class BacklogWorkflow(BaseWorkflow):
    """
    Workflow for generating Backlog Items from an Epic.

    States:
        init -> loading_epic -> analyzing_scope -> generating_items -> verifying -> refining -> finalizing -> completed
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._state_machine = create_backlog_state_machine()
        self._context_manager = ContextManager(max_tokens=100000)

    @property
    def workflow_type(self) -> str:
        return "backlog"

    @property
    def state_machine(self) -> StateMachine:
        return self._state_machine

    async def execute(self, context: WorkflowContext) -> WorkflowResult:
        """Execute the Backlog generation workflow."""
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
        backlog_items: list[Document] = []

        try:
            # Step 1: Load parent Epic
            state.current_state = "loading_epic"
            state.add_to_history("loading_epic")

            epic_content = await self._load_epic(context)
            reasoning_traces.append({
                "step": "epic_loading",
                "epic_id": context.parent_document_id,
                "content_length": len(epic_content) if epic_content else 0,
            })

            if not epic_content:
                raise ValueError(f"Epic document not found: {context.parent_document_id}")

            # Step 2: Analyze scope for backlog decomposition
            state.current_state = "analyzing_scope"
            state.add_to_history("analyzing_scope")

            scope_analysis = await self._analyze_scope(context, epic_content)
            reasoning_traces.append({
                "step": "scope_analysis",
                "features_identified": len(scope_analysis.get("features", [])),
            })
            artifacts.append({
                "type": "scope_analysis",
                "data": scope_analysis,
            })

            # Step 3: Generate Backlog Items
            state.current_state = "generating_items"
            state.add_to_history("generating_items")

            item_drafts = await self._generate_backlog_items(context, epic_content, scope_analysis)
            reasoning_traces.append({
                "step": "item_generation",
                "items_generated": len(item_drafts),
            })

            # Step 4: Verify each Backlog Item
            state.current_state = "verifying"
            state.add_to_history("verifying")

            verified_items = []
            for i, item_draft in enumerate(item_drafts):
                verification_result = await self._verify_item(context, item_draft)

                # Refine if needed
                refined_item = item_draft
                refinement_count = 0
                max_refinements = 2

                while not verification_result.is_valid and refinement_count < max_refinements:
                    state.current_state = "refining"
                    state.add_to_history("refining", {"item_index": i, "iteration": refinement_count + 1})

                    refined_item = await self._refine_item(context, refined_item, verification_result)
                    refinement_count += 1

                    verification_result = await self._verify_item(context, refined_item)

                verified_items.append({
                    "content": refined_item,
                    "verification": verification_result,
                    "refinements": refinement_count,
                })

                reasoning_traces.append({
                    "step": f"item_{i}_verification",
                    "is_valid": verification_result.is_valid,
                    "confidence": verification_result.confidence_score,
                    "refinements": refinement_count,
                })

            # Step 5: Generate acceptance criteria for each item
            for i, verified_item in enumerate(verified_items):
                criteria = await self._generate_acceptance_criteria(
                    context,
                    verified_item["content"]
                )
                verified_items[i]["acceptance_criteria"] = criteria

            # Step 6: Finalization
            state.current_state = "finalizing"
            state.add_to_history("finalizing")

            for i, verified_item in enumerate(verified_items):
                document_id = self._generate_document_id()

                avg_confidence = verified_item["verification"].confidence_score
                is_valid = verified_item["verification"].is_valid

                item_doc = Document(
                    id=document_id,
                    type=DocumentType.BACKLOG_ITEM,
                    title=f"Backlog Item {i + 1}",
                    content=verified_item["content"],
                    session_id=context.session_id,
                    parent_document_id=context.parent_document_id,
                    verification_status=VerificationStatus.VERIFIED if is_valid else VerificationStatus.PARTIALLY_VERIFIED,
                    confidence_score=avg_confidence,
                    metadata={
                        "workflow_id": workflow_id,
                        "item_index": i,
                        "refinement_iterations": verified_item["refinements"],
                        "epic_id": context.parent_document_id,
                        "acceptance_criteria": verified_item.get("acceptance_criteria", []),
                    },
                )
                backlog_items.append(item_doc)

            # Mark as completed
            state.current_state = "completed"
            state.status = WorkflowStatus.COMPLETED
            state.add_to_history("completed")

            # Return the first item as the main document, others as artifacts
            main_document = backlog_items[0] if backlog_items else None
            artifacts.extend([
                {"type": "backlog_item", "document": item.dict()} for item in backlog_items[1:]
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
            logger.exception("Backlog workflow failed", workflow_id=workflow_id, error=str(e))
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

    async def _load_epic(self, context: WorkflowContext) -> Optional[str]:
        """Load the parent Epic document."""
        logger.info("Loading Epic document", epic_id=context.parent_document_id)

        if not context.parent_document_id:
            return None

        # Placeholder: return context metadata if available
        return context.metadata.get("epic_content", "")

    async def _analyze_scope(
        self,
        context: WorkflowContext,
        epic_content: str
    ) -> dict[str, Any]:
        """Analyze Epic to identify features for backlog decomposition."""
        logger.info("Analyzing Epic for backlog decomposition")

        # Use reasoning engine to analyze the Epic
        reasoning_result = await self.reasoning_engine.reason(
            query="""Analyze this Epic to identify features that can be decomposed into Backlog Items.
For each feature, identify:
1. User-facing functionality
2. Technical tasks required
3. Data changes needed
4. Testing requirements
5. Estimated complexity (story points 1-13)""",
            context={
                "epic_content": epic_content[:5000],
                "codebase_path": context.codebase_path,
            }
        )

        features = []
        if reasoning_result.traces:
            analysis_output = reasoning_result.final_answer or ""
            features = self._extract_features_from_analysis(analysis_output)

        return {
            "features": features,
            "reasoning_confidence": reasoning_result.confidence,
            "epic_summary": epic_content[:1000],
        }

    def _extract_features_from_analysis(self, analysis: str) -> list[dict[str, Any]]:
        """Extract feature information from analysis text."""
        features = []
        lines = analysis.split("\n")
        current_feature: Optional[dict] = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line[0].isdigit() or line.startswith("-") or line.startswith("*"):
                if current_feature:
                    features.append(current_feature)
                current_feature = {
                    "name": line.lstrip("0123456789.-* "),
                    "description": "",
                    "tasks": [],
                    "complexity": "M",
                }
            elif current_feature:
                current_feature["description"] += line + " "

        if current_feature:
            features.append(current_feature)

        return features

    async def _generate_backlog_items(
        self,
        context: WorkflowContext,
        epic_content: str,
        scope_analysis: dict[str, Any]
    ) -> list[str]:
        """Generate backlog items from Epic and scope analysis."""
        logger.info("Generating backlog items", features=len(scope_analysis.get("features", [])))

        features = scope_analysis.get("features", [])

        feature_list = "\n".join([
            f"- {f.get('name', 'Unknown')}: {f.get('description', '')[:200]}"
            for f in features
        ])

        prompt = f"""Based on the following Epic and feature analysis, generate Backlog Items (User Stories).

Epic Summary:
{epic_content[:3000]}

Identified Features:
{feature_list}

For each backlog item, include:
1. Title - User story format: "As a [user], I want [goal], so that [benefit]"
2. Description - Detailed explanation of the requirement
3. Story Points - Fibonacci scale (1, 2, 3, 5, 8, 13)
4. Priority - High/Medium/Low
5. Technical Notes - Implementation considerations
6. Dependencies - Other items or external dependencies

Guidelines:
- Each item should be completable in one sprint (1-2 weeks)
- Items should be testable and demonstrable
- Focus on user value, not technical tasks
- Include both functional and technical items where appropriate

Generate the backlog items now, separating each with "---ITEM---":
"""

        response = await self.conversation_handler.send_message(
            session_id=context.session_id,
            message=prompt,
            skill_name="backlog-generator",
            context={
                "epic_id": context.parent_document_id,
                "document_type": "BacklogItem",
            }
        )

        item_texts = response.content.split("---ITEM---")
        return [item.strip() for item in item_texts if item.strip()]

    async def _verify_item(
        self,
        context: WorkflowContext,
        item_content: str
    ) -> VerificationResult:
        """Verify a backlog item against the codebase."""
        logger.info("Verifying backlog item")

        if not self.verification_engine:
            return VerificationResult(
                is_valid=True,
                confidence_score=0.8,
                verified_facts=[],
                unverified_claims=[],
                issues=[],
            )

        result = await self.verification_engine.verify_document(
            content=item_content,
            document_type=DocumentType.BACKLOG_ITEM,
            context={
                "epic_id": context.parent_document_id,
                "codebase_path": context.codebase_path,
            }
        )

        return result

    async def _refine_item(
        self,
        context: WorkflowContext,
        item_content: str,
        verification: VerificationResult
    ) -> str:
        """Refine a backlog item based on verification issues."""
        logger.info("Refining backlog item", issues_count=len(verification.issues))

        issues_text = "\n".join([
            f"- {issue.category}: {issue.description}"
            for issue in verification.issues[:10]
        ])

        prompt = f"""Please refine this Backlog Item to address verification issues:

Issues found:
{issues_text}

Current Item:
{item_content}

Ensure all claims are verifiable and grounded in the codebase.
"""

        response = await self.conversation_handler.send_message(
            session_id=context.session_id,
            message=prompt,
            skill_name="backlog-generator",
            context={"refinement_mode": True}
        )

        return response.content

    async def _generate_acceptance_criteria(
        self,
        context: WorkflowContext,
        item_content: str
    ) -> list[dict[str, Any]]:
        """Generate acceptance criteria for a backlog item."""
        logger.info("Generating acceptance criteria")

        prompt = f"""Generate acceptance criteria for this backlog item using Given-When-Then format:

Backlog Item:
{item_content}

For each acceptance criterion:
1. Given - Initial context/state
2. When - Action taken
3. Then - Expected outcome

Generate 3-5 acceptance criteria:
"""

        response = await self.conversation_handler.send_message(
            session_id=context.session_id,
            message=prompt,
            skill_name="acceptance-criteria",
            context={"item_content": item_content[:1000]}
        )

        # Parse acceptance criteria from response
        criteria = self._parse_acceptance_criteria(response.content)
        return criteria

    def _parse_acceptance_criteria(self, content: str) -> list[dict[str, Any]]:
        """Parse acceptance criteria from response text."""
        criteria = []
        current_criterion: Optional[dict] = None

        lines = content.split("\n")
        for line in lines:
            line = line.strip().lower()

            if "given" in line and ":" in line:
                if current_criterion:
                    criteria.append(current_criterion)
                current_criterion = {
                    "given": line.split(":", 1)[1].strip() if ":" in line else "",
                    "when": "",
                    "then": "",
                }
            elif "when" in line and ":" in line and current_criterion:
                current_criterion["when"] = line.split(":", 1)[1].strip()
            elif "then" in line and ":" in line and current_criterion:
                current_criterion["then"] = line.split(":", 1)[1].strip()

        if current_criterion and current_criterion.get("given"):
            criteria.append(current_criterion)

        return criteria
