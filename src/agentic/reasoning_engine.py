"""
Multi-step reasoning engine for the Agentic Harness.
Implements chain-of-thought reasoning like a senior engineer.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from src.agentic.prompts.reasoning import REASONING_PROMPTS
from src.copilot.sdk_client import CopilotSDKClient, CopilotResponse
from src.core.constants import ReasoningStep
from src.core.logging import get_logger
from src.mcp.tool_registry import MCPToolRegistry

logger = get_logger(__name__)


@dataclass
class ReasoningTrace:
    """Record of a single reasoning step."""

    step: ReasoningStep
    input: dict[str, Any]
    thought_process: str
    output: dict[str, Any]
    confidence: float  # 0.0 to 1.0
    supporting_evidence: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=lambda: datetime.utcnow().timestamp())
    tokens_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step": self.step.value,
            "input": self.input,
            "thought_process": self.thought_process,
            "output": self.output,
            "confidence": self.confidence,
            "supporting_evidence": self.supporting_evidence,
            "timestamp": self.timestamp,
            "tokens_used": self.tokens_used,
        }


@dataclass
class ReasoningResult:
    """Complete reasoning result."""

    task: str
    traces: list[ReasoningTrace] = field(default_factory=list)
    final_answer: dict[str, Any] = field(default_factory=dict)
    overall_confidence: float = 0.0
    total_tokens: int = 0
    success: bool = True
    error: Optional[str] = None

    def add_trace(self, trace: ReasoningTrace) -> None:
        """Add a reasoning trace."""
        self.traces.append(trace)
        self.total_tokens += trace.tokens_used

    def get_trace(self, step: ReasoningStep) -> Optional[ReasoningTrace]:
        """Get trace for a specific step."""
        for trace in self.traces:
            if trace.step == step:
                return trace
        return None


class ReasoningEngine:
    """
    Multi-step reasoning engine that thinks like a senior engineer.

    Implements a structured reasoning process:
    1. UNDERSTAND - Comprehend the task
    2. ANALYZE - Analyze available context
    3. DECOMPOSE - Break into sub-tasks
    4. EXECUTE - Execute with tools
    5. VERIFY - Verify results
    6. SYNTHESIZE - Produce final answer
    """

    def __init__(
        self,
        copilot_client: CopilotSDKClient,
        tool_registry: MCPToolRegistry,
        confidence_threshold: float = 0.7,
        max_retries: int = 2,
    ) -> None:
        """
        Initialize the reasoning engine.

        Args:
            copilot_client: Copilot SDK client
            tool_registry: MCP tool registry
            confidence_threshold: Minimum confidence to proceed
            max_retries: Max retries for low-confidence results
        """
        self.copilot_client = copilot_client
        self.tool_registry = tool_registry
        self.confidence_threshold = confidence_threshold
        self.max_retries = max_retries

    async def reason_about_task(
        self,
        task: str,
        context: dict[str, Any],
        depth: int = 3,
    ) -> ReasoningResult:
        """
        Execute multi-step reasoning about a task.

        Args:
            task: The task to reason about
            context: Context information (session, codebase, etc.)
            depth: Reasoning depth (1-5)

        Returns:
            Complete reasoning result with traces
        """
        result = ReasoningResult(task=task)

        logger.info("Starting reasoning", task=task[:50], depth=depth)

        try:
            # Step 1: Understand the task
            understanding = await self._understand_task(task, context)
            result.add_trace(understanding)

            if understanding.confidence < self.confidence_threshold:
                logger.warning("Low confidence in understanding", confidence=understanding.confidence)

            # Step 2: Analyze the context
            analysis = await self._analyze_context(understanding.output, context)
            result.add_trace(analysis)

            # Step 3: Decompose into sub-tasks
            decomposition = await self._decompose_problem(analysis.output, depth)
            result.add_trace(decomposition)

            # Step 4: Execute sub-tasks
            execution = await self._execute_subtasks(decomposition.output, context)
            result.add_trace(execution)

            # Step 5: Verify results
            verification = await self._verify_results(execution.output, context)
            result.add_trace(verification)

            # Step 6: Synthesize final answer
            synthesis = await self._synthesize_answer(
                understanding.output,
                execution.output,
                verification.output,
            )
            result.add_trace(synthesis)

            result.final_answer = synthesis.output
            result.overall_confidence = self._calculate_overall_confidence(result.traces)

            logger.info(
                "Reasoning complete",
                task=task[:50],
                confidence=result.overall_confidence,
                tokens=result.total_tokens,
            )

        except Exception as e:
            logger.error("Reasoning failed", task=task[:50], error=str(e))
            result.success = False
            result.error = str(e)

        return result

    async def _understand_task(
        self,
        task: str,
        context: dict[str, Any],
    ) -> ReasoningTrace:
        """
        Step 1: Understand the task - extract intent, requirements, constraints.
        """
        prompt = REASONING_PROMPTS["understand"].format(task=task)

        # Create conversation for this reasoning step
        conv_id = await self.copilot_client.create_conversation(
            system_prompt="You are analyzing a task to understand its requirements.",
            skills=["senior-engineer-analysis"],
        )

        response = await self.copilot_client.send_message(
            message=prompt,
            conversation_id=conv_id,
        )

        # Parse the understanding from response
        understanding = self._parse_understanding(response.message)

        return ReasoningTrace(
            step=ReasoningStep.UNDERSTAND,
            input={"task": task, "context_keys": list(context.keys())},
            thought_process=response.message,
            output=understanding,
            confidence=self._assess_confidence(response.message),
            tokens_used=response.tokens_used,
        )

    async def _analyze_context(
        self,
        understanding: dict[str, Any],
        context: dict[str, Any],
    ) -> ReasoningTrace:
        """
        Step 2: Analyze available context - identify info and gaps.
        """
        prompt = REASONING_PROMPTS["analyze"].format(
            understanding=understanding,
            context=context,
        )

        conv_id = await self.copilot_client.create_conversation(
            system_prompt="You are analyzing context to identify available information and gaps.",
            skills=["codebase-analyzer"],
        )

        # Include tools for context analysis
        tools = self.tool_registry.get_tool_definitions(categories=["neo4j"])

        response = await self.copilot_client.send_message(
            message=prompt,
            conversation_id=conv_id,
            tools=tools,
        )

        # Process any tool calls
        evidence = []
        if response.tool_calls:
            for tool_call in response.tool_calls:
                tool_result = await self.tool_registry.execute(
                    tool_call.function_name,
                    tool_call.arguments,
                )
                evidence.append(f"{tool_call.function_name}: {tool_result}")
                await self.copilot_client.add_tool_result(
                    conv_id, tool_call.id, tool_result
                )

        analysis = self._parse_analysis(response.message)

        return ReasoningTrace(
            step=ReasoningStep.ANALYZE,
            input={"understanding": understanding},
            thought_process=response.message,
            output=analysis,
            confidence=self._assess_confidence(response.message),
            supporting_evidence=evidence,
            tokens_used=response.tokens_used,
        )

    async def _decompose_problem(
        self,
        analysis: dict[str, Any],
        depth: int,
    ) -> ReasoningTrace:
        """
        Step 3: Decompose into sub-tasks.
        """
        prompt = REASONING_PROMPTS["decompose"].format(
            analysis=analysis,
            depth=depth,
        )

        conv_id = await self.copilot_client.create_conversation(
            system_prompt="You are breaking down a complex task into manageable sub-tasks.",
            skills=["senior-engineer-analysis"],
        )

        response = await self.copilot_client.send_message(
            message=prompt,
            conversation_id=conv_id,
        )

        decomposition = self._parse_decomposition(response.message)

        return ReasoningTrace(
            step=ReasoningStep.DECOMPOSE,
            input={"analysis": analysis, "depth": depth},
            thought_process=response.message,
            output=decomposition,
            confidence=self._assess_confidence(response.message),
            tokens_used=response.tokens_used,
        )

    async def _execute_subtasks(
        self,
        decomposition: dict[str, Any],
        context: dict[str, Any],
    ) -> ReasoningTrace:
        """
        Step 4: Execute sub-tasks using tools.
        """
        results = []
        evidence = []

        subtasks = decomposition.get("subtasks", [])

        for subtask in subtasks:
            subtask_result = await self._execute_single_subtask(subtask, context)
            results.append(subtask_result)
            if "evidence" in subtask_result:
                evidence.extend(subtask_result["evidence"])

        return ReasoningTrace(
            step=ReasoningStep.EXECUTE,
            input={"decomposition": decomposition},
            thought_process=f"Executed {len(subtasks)} subtasks",
            output={"results": results, "subtask_count": len(subtasks)},
            confidence=self._calculate_execution_confidence(results),
            supporting_evidence=evidence,
        )

    async def _execute_single_subtask(
        self,
        subtask: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single subtask."""
        conv_id = await self.copilot_client.create_conversation(
            system_prompt="Execute the following subtask and return results.",
            skills=["codebase-analyzer"],
        )

        tools = self.tool_registry.get_tool_definitions()

        response = await self.copilot_client.send_message(
            message=f"Execute: {subtask.get('description', str(subtask))}",
            conversation_id=conv_id,
            tools=tools,
        )

        # Collect tool results as evidence
        evidence = []
        while response.tool_calls:
            for tool_call in response.tool_calls:
                result = await self.tool_registry.execute(
                    tool_call.function_name,
                    tool_call.arguments,
                )
                evidence.append(str(result))
                await self.copilot_client.add_tool_result(
                    conv_id, tool_call.id, result
                )

            response = await self.copilot_client.send_message(
                message="",
                conversation_id=conv_id,
                tools=tools,
            )

        return {
            "subtask": subtask,
            "result": response.message,
            "evidence": evidence,
        }

    async def _verify_results(
        self,
        execution: dict[str, Any],
        context: dict[str, Any],
    ) -> ReasoningTrace:
        """
        Step 5: Verify results against ground truth.
        """
        prompt = REASONING_PROMPTS["verify"].format(
            execution=execution,
            context=context,
        )

        conv_id = await self.copilot_client.create_conversation(
            system_prompt="You verify claims against the codebase. Flag any hallucinations.",
            skills=["verification"],
        )

        tools = self.tool_registry.get_tool_definitions()

        response = await self.copilot_client.send_message(
            message=prompt,
            conversation_id=conv_id,
            tools=tools,
        )

        verification = self._parse_verification(response.message)

        return ReasoningTrace(
            step=ReasoningStep.VERIFY,
            input={"execution": execution},
            thought_process=response.message,
            output=verification,
            confidence=verification.get("confidence", 0.5),
            tokens_used=response.tokens_used,
        )

    async def _synthesize_answer(
        self,
        understanding: dict[str, Any],
        execution: dict[str, Any],
        verification: dict[str, Any],
    ) -> ReasoningTrace:
        """
        Step 6: Synthesize final answer from all steps.
        """
        prompt = REASONING_PROMPTS["synthesize"].format(
            understanding=understanding,
            execution=execution,
            verification=verification,
        )

        conv_id = await self.copilot_client.create_conversation(
            system_prompt="Synthesize a final, verified answer from the reasoning steps.",
            skills=["senior-engineer-analysis"],
        )

        response = await self.copilot_client.send_message(
            message=prompt,
            conversation_id=conv_id,
        )

        synthesis = self._parse_synthesis(response.message)

        return ReasoningTrace(
            step=ReasoningStep.SYNTHESIZE,
            input={
                "understanding": understanding,
                "execution": execution,
                "verification": verification,
            },
            thought_process=response.message,
            output=synthesis,
            confidence=self._assess_confidence(response.message),
            tokens_used=response.tokens_used,
        )

    def _parse_understanding(self, message: str) -> dict[str, Any]:
        """Parse understanding from Copilot response."""
        return {
            "intent": self._extract_section(message, "intent"),
            "requirements": self._extract_list(message, "requirements"),
            "constraints": self._extract_list(message, "constraints"),
            "raw": message,
        }

    def _parse_analysis(self, message: str) -> dict[str, Any]:
        """Parse analysis from Copilot response."""
        return {
            "available_info": self._extract_list(message, "available"),
            "gaps": self._extract_list(message, "gaps"),
            "raw": message,
        }

    def _parse_decomposition(self, message: str) -> dict[str, Any]:
        """Parse decomposition from Copilot response."""
        return {
            "subtasks": self._extract_list(message, "subtasks"),
            "dependencies": self._extract_list(message, "dependencies"),
            "raw": message,
        }

    def _parse_verification(self, message: str) -> dict[str, Any]:
        """Parse verification from Copilot response."""
        return {
            "verified_claims": self._extract_list(message, "verified"),
            "unverified_claims": self._extract_list(message, "unverified"),
            "confidence": self._assess_confidence(message),
            "raw": message,
        }

    def _parse_synthesis(self, message: str) -> dict[str, Any]:
        """Parse synthesis from Copilot response."""
        return {
            "answer": message,
            "key_points": self._extract_list(message, "key points"),
        }

    def _extract_section(self, text: str, section: str) -> str:
        """Extract a section from text."""
        # Simple extraction - could be enhanced with better parsing
        lower_text = text.lower()
        if section.lower() in lower_text:
            start = lower_text.find(section.lower())
            # Find next newline or section
            end = text.find("\n\n", start)
            if end == -1:
                end = len(text)
            return text[start:end].strip()
        return ""

    def _extract_list(self, text: str, keyword: str) -> list[str]:
        """Extract a list of items from text."""
        items = []
        lines = text.split("\n")
        in_section = False

        for line in lines:
            if keyword.lower() in line.lower():
                in_section = True
                continue
            if in_section:
                line = line.strip()
                if line.startswith("-") or line.startswith("*") or line.startswith("•"):
                    items.append(line[1:].strip())
                elif line.startswith(("1.", "2.", "3.", "4.", "5.")):
                    items.append(line[2:].strip())
                elif not line:
                    in_section = False

        return items

    def _assess_confidence(self, message: str) -> float:
        """Assess confidence from message content."""
        # Simple heuristic based on language
        confidence = 0.7  # Base confidence

        low_confidence_markers = [
            "might", "possibly", "unclear", "uncertain", "not sure",
            "may", "could be", "perhaps", "seems"
        ]
        high_confidence_markers = [
            "definitely", "certainly", "confirmed", "verified",
            "clearly", "evidently", "found"
        ]

        lower_message = message.lower()

        for marker in low_confidence_markers:
            if marker in lower_message:
                confidence -= 0.1

        for marker in high_confidence_markers:
            if marker in lower_message:
                confidence += 0.1

        return max(0.0, min(1.0, confidence))

    def _calculate_execution_confidence(self, results: list[dict]) -> float:
        """Calculate confidence from execution results."""
        if not results:
            return 0.0

        # Check for successful tool executions
        successful = sum(1 for r in results if r.get("evidence"))
        return successful / len(results)

    def _calculate_overall_confidence(self, traces: list[ReasoningTrace]) -> float:
        """Calculate overall confidence from all traces."""
        if not traces:
            return 0.0

        # Weighted average with verification step having more weight
        weights = {
            ReasoningStep.UNDERSTAND: 0.15,
            ReasoningStep.ANALYZE: 0.15,
            ReasoningStep.DECOMPOSE: 0.10,
            ReasoningStep.EXECUTE: 0.20,
            ReasoningStep.VERIFY: 0.25,
            ReasoningStep.SYNTHESIZE: 0.15,
        }

        weighted_sum = 0.0
        total_weight = 0.0

        for trace in traces:
            weight = weights.get(trace.step, 0.1)
            weighted_sum += trace.confidence * weight
            total_weight += weight

        return weighted_sum / total_weight if total_weight > 0 else 0.0
