"""BRD Refinement Agent - Refines BRD sections based on user feedback.

This agent handles:
1. Single section refinement with targeted feedback
2. Global BRD refinement affecting multiple sections
3. Change summarization for audit trail
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable, Optional

from ..models.brd import (
    BRDSection,
    RefinedBRD,
    RefinementEntry,
    RefineBRDSectionRequest,
    RefineEntireBRDRequest,
    RefineBRDSectionResponse,
    RefineEntireBRDResponse,
    FeedbackType,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Prompt Templates
# =============================================================================

SECTION_REFINEMENT_SYSTEM_PROMPT = """You are an expert Business Analyst and Technical Writer. Your task is to refine a specific section of a Business Requirements Document (BRD) based on user feedback.

## Your Responsibilities:
1. Incorporate the user's feedback into the section
2. Maintain consistency with the rest of the BRD
3. Preserve the section's purpose and structure
4. Improve clarity, accuracy, and completeness
5. Keep technical accuracy while ensuring business readability

## Output Format:
Respond with the refined section content only, in markdown format. Do not include the section header - just the content.

## Guidelines:
- Address all points raised in the feedback
- Maintain the same level of detail as the original
- Keep consistent terminology with the full BRD
- Preserve any existing code references or technical details
- Do not add information not supported by the context
"""

SECTION_REFINEMENT_USER_PROMPT = """## Section to Refine: {section_name}

## Current Section Content:
{current_content}

## User Feedback:
{user_feedback}

## Full BRD Context (for reference):
{brd_context}

## Instructions:
Refine the section above based on the user feedback. Maintain consistency with the full BRD context.

Respond with the refined section content in markdown format only (no section header, no JSON).
"""

GLOBAL_REFINEMENT_SYSTEM_PROMPT = """You are an expert Business Analyst and Technical Writer. Your task is to refine an entire Business Requirements Document (BRD) based on global user feedback.

## Your Responsibilities:
1. Apply the feedback consistently across all relevant sections
2. Maintain document coherence and flow
3. Preserve section structure and ordering
4. Ensure terminology consistency throughout
5. Keep all existing code references and technical details

## Output Format:
Respond with a JSON object containing the refined sections:
```json
{
  "sections": [
    {
      "name": "Section Name",
      "content": "Refined section content in markdown..."
    }
  ],
  "changes_summary": "Brief summary of changes made"
}
```

## Guidelines:
- Apply feedback to ALL sections where relevant
- If feedback only applies to specific sections, only modify those
- Keep sections in the same order
- Preserve section names exactly
- Maintain technical accuracy
"""

GLOBAL_REFINEMENT_USER_PROMPT = """## Current BRD Sections:
{sections_json}

## Global User Feedback:
{global_feedback}

## Instructions:
Apply the global feedback to all relevant sections of the BRD. Maintain consistency and coherence across the document.

{target_sections_instruction}

Respond with a JSON object containing the refined sections array and a changes_summary.
"""

CHANGES_SUMMARY_PROMPT = """Compare these two versions of a BRD section and summarize the key changes in 1-2 sentences:

## Section: {section_name}

## Before:
{before_content}

## After:
{after_content}

## User Feedback Applied:
{feedback}

Provide a concise summary of what changed and why.
"""


class BRDRefinementAgent:
    """Agent for refining BRD based on user feedback.

    Supports both section-level and global refinement with
    change tracking for audit purposes.
    """

    def __init__(
        self,
        copilot_session: Any = None,
        config: dict[str, Any] = None,
    ):
        """Initialize the BRD Refinement Agent.

        Args:
            copilot_session: Copilot SDK session for LLM access
            config: Agent configuration
        """
        self.session = copilot_session
        self.config = config or {}

        logger.info("BRDRefinementAgent initialized")

    async def refine_section(
        self,
        request: RefineBRDSectionRequest,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> RefineBRDSectionResponse:
        """Refine a single BRD section with user feedback.

        Args:
            request: The refinement request
            progress_callback: Optional callback for progress updates

        Returns:
            RefineBRDSectionResponse with refined section
        """
        logger.info(f"Refining BRD section: {request.section_name}")

        if progress_callback:
            progress_callback(f"Refining section: {request.section_name}...")

        # Build the prompt
        prompt = self._build_section_refinement_prompt(request)

        if progress_callback:
            progress_callback("Applying feedback with AI...")

        # Call LLM
        response = await self._send_to_llm(prompt)

        if progress_callback:
            progress_callback("Parsing refined content...")

        # Parse the refined content
        refined_content = self._clean_response(response)

        # Create refined section
        refined_section = BRDSection(
            name=request.section_name,
            content=refined_content,
            refinement_count=1,  # Will be updated by caller
            last_feedback=request.user_feedback,
            last_refined_at=datetime.now(),
        )

        # Generate changes summary
        changes_summary = await self.summarize_changes(
            request.section_name,
            request.current_content,
            refined_content,
            request.user_feedback,
        )

        if progress_callback:
            progress_callback(f"Section '{request.section_name}' refined successfully")

        return RefineBRDSectionResponse(
            success=True,
            brd_id=request.brd_id,
            section_name=request.section_name,
            refined_section=refined_section,
            changes_summary=changes_summary,
            before_content=request.current_content,
            after_content=refined_content,
        )

    async def refine_entire_brd(
        self,
        request: RefineEntireBRDRequest,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> RefineEntireBRDResponse:
        """Apply global feedback to entire BRD.

        Args:
            request: The refinement request with global feedback
            progress_callback: Optional callback for progress updates

        Returns:
            RefineEntireBRDResponse with refined BRD
        """
        logger.info(f"Refining entire BRD: {request.brd_id}")

        if progress_callback:
            progress_callback("Applying global feedback to BRD...")

        # Build the prompt
        prompt = self._build_global_refinement_prompt(request)

        if progress_callback:
            progress_callback("Processing all sections with AI...")

        # Call LLM
        response = await self._send_to_llm(prompt)

        if progress_callback:
            progress_callback("Parsing refined sections...")

        # Parse the response
        refined_data = self._parse_global_refinement_response(response)

        # Build refined sections
        section_diffs = {}
        sections_affected = []
        refined_sections = []

        original_sections = {s.name.lower(): s for s in request.current_brd.sections}

        for section_data in refined_data.get("sections", []):
            section_name = section_data.get("name", "Unknown")
            new_content = section_data.get("content", "")

            # Find original section
            original_key = section_name.lower()
            original_section = original_sections.get(original_key)
            original_content = original_section.content if original_section else ""
            original_refinement_count = original_section.refinement_count if original_section else 0

            # Check if content changed
            if new_content != original_content:
                sections_affected.append(section_name)
                section_diffs[section_name] = {
                    "before": original_content,
                    "after": new_content,
                }

            refined_sections.append(BRDSection(
                name=section_name,
                content=new_content,
                section_order=len(refined_sections),
                refinement_count=original_refinement_count + (1 if new_content != original_content else 0),
                last_feedback=request.global_feedback if new_content != original_content else None,
                last_refined_at=datetime.now() if new_content != original_content else None,
            ))

        # Build refined BRD
        refined_brd = RefinedBRD(
            id=request.current_brd.id,
            title=request.current_brd.title,
            version=request.current_brd.version,
            repository_id=request.current_brd.repository_id,
            sections=refined_sections,
            markdown=self._sections_to_markdown(refined_sections, request.current_brd.title),
            mode=request.current_brd.mode,
            confidence_score=request.current_brd.confidence_score,
            verification_report=request.current_brd.verification_report,
            refinement_count=request.current_brd.refinement_count + 1,
            last_feedback=request.global_feedback,
            refinement_history=[
                *request.current_brd.refinement_history,
                RefinementEntry(
                    version=request.current_brd.refinement_count + 1,
                    timestamp=datetime.now(),
                    feedback_type=FeedbackType.GLOBAL,
                    feedback_target=None,
                    user_feedback=request.global_feedback,
                    changes_summary=refined_data.get("changes_summary", "Applied global feedback"),
                    sections_affected=sections_affected,
                    section_diffs=section_diffs,
                ),
            ],
            session_id=request.current_brd.session_id,
            status=request.current_brd.status,
            created_at=request.current_brd.created_at,
            updated_at=datetime.now(),
        )

        changes_summary = refined_data.get("changes_summary", f"Modified {len(sections_affected)} sections")

        if progress_callback:
            progress_callback(f"BRD refined: {len(sections_affected)} sections modified")

        return RefineEntireBRDResponse(
            success=True,
            brd_id=request.brd_id,
            refined_brd=refined_brd,
            changes_summary=changes_summary,
            sections_affected=sections_affected,
            section_diffs=section_diffs,
        )

    async def summarize_changes(
        self,
        section_name: str,
        old_content: str,
        new_content: str,
        feedback: str,
    ) -> str:
        """Generate human-readable summary of changes.

        Args:
            section_name: Name of the section
            old_content: Content before refinement
            new_content: Content after refinement
            feedback: User feedback applied

        Returns:
            Brief summary of changes
        """
        # For simple changes, generate summary without LLM
        if old_content == new_content:
            return "No changes made"

        # Calculate rough change metrics
        old_words = len(old_content.split())
        new_words = len(new_content.split())
        word_diff = new_words - old_words

        if abs(word_diff) < 10:
            change_type = "refined"
        elif word_diff > 50:
            change_type = "significantly expanded"
        elif word_diff < -50:
            change_type = "condensed"
        elif word_diff > 0:
            change_type = "expanded"
        else:
            change_type = "shortened"

        # Simple summary
        summary = f"Section '{section_name}' was {change_type}"

        # Add feedback context if short
        if len(feedback) < 100:
            summary += f" based on feedback: \"{feedback}\""
        else:
            summary += " based on user feedback"

        return summary

    def _build_section_refinement_prompt(self, request: RefineBRDSectionRequest) -> str:
        """Build the section refinement prompt."""
        # Truncate BRD context if too long
        max_context_length = 8000
        brd_context = request.full_brd_context
        if len(brd_context) > max_context_length:
            brd_context = brd_context[:max_context_length] + "\n...[truncated for length]..."

        return f"""{SECTION_REFINEMENT_SYSTEM_PROMPT}

{SECTION_REFINEMENT_USER_PROMPT.format(
    section_name=request.section_name,
    current_content=request.current_content,
    user_feedback=request.user_feedback,
    brd_context=brd_context,
)}"""

    def _build_global_refinement_prompt(self, request: RefineEntireBRDRequest) -> str:
        """Build the global refinement prompt."""
        # Format sections as JSON for the prompt
        sections_data = [
            {"name": s.name, "content": s.content}
            for s in request.current_brd.sections
        ]
        sections_json = json.dumps(sections_data, indent=2)

        # Handle target sections
        if request.target_sections:
            target_instruction = f"Only modify these sections: {', '.join(request.target_sections)}"
        else:
            target_instruction = "Apply the feedback to all sections where relevant."

        return f"""{GLOBAL_REFINEMENT_SYSTEM_PROMPT}

{GLOBAL_REFINEMENT_USER_PROMPT.format(
    sections_json=sections_json,
    global_feedback=request.global_feedback,
    target_sections_instruction=target_instruction,
)}"""

    def _parse_global_refinement_response(self, response: str) -> dict:
        """Parse global refinement response into structured data."""
        try:
            # Extract JSON from response
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                # Try to find JSON object directly
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = response.strip()

            data = json.loads(json_str)

            # Validate structure
            if "sections" not in data:
                logger.warning("Response missing 'sections' key")
                return {"sections": [], "changes_summary": "Failed to parse response"}

            return data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse global refinement response: {e}")
            return {"sections": [], "changes_summary": f"Parse error: {e}"}

    def _clean_response(self, response: str) -> str:
        """Clean LLM response by removing code blocks and extra formatting."""
        # Remove markdown code blocks
        cleaned = re.sub(r'```(?:markdown|md)?\s*', '', response)
        cleaned = re.sub(r'```\s*$', '', cleaned)

        # Remove leading/trailing whitespace
        cleaned = cleaned.strip()

        return cleaned

    def _sections_to_markdown(self, sections: list[BRDSection], title: str) -> str:
        """Convert sections list to full markdown document."""
        lines = [f"# {title}", ""]

        for section in sections:
            lines.append(f"## {section.name}")
            lines.append("")
            lines.append(section.content)
            lines.append("")

        return "\n".join(lines)

    async def _send_to_llm(self, prompt: str) -> str:
        """Send prompt to LLM via Copilot SDK."""
        if not self.session:
            logger.warning("No Copilot session, returning mock response")
            return self._generate_mock_response()

        try:
            import asyncio

            message_options = {"prompt": prompt}

            if hasattr(self.session, 'send_and_wait'):
                event = await asyncio.wait_for(
                    self.session.send_and_wait(message_options, timeout=120),
                    timeout=120
                )
                if event:
                    return self._extract_from_event(event)

            if hasattr(self.session, 'send'):
                await self.session.send(message_options)
                return await self._wait_for_response(120)

        except Exception as e:
            logger.error(f"LLM error: {e}")

        return self._generate_mock_response()

    def _extract_from_event(self, event: Any) -> str:
        """Extract text content from a Copilot event."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                if hasattr(data, 'message') and hasattr(data.message, 'content'):
                    return str(data.message.content)
                if hasattr(data, 'content'):
                    return str(data.content)
                if hasattr(data, 'text'):
                    return str(data.text)

            if hasattr(event, 'content'):
                return str(event.content)
            if hasattr(event, 'text'):
                return str(event.text)

            return str(event)
        except Exception as e:
            logger.error(f"Error extracting from event: {e}")
            return ""

    async def _wait_for_response(self, timeout: float) -> str:
        """Wait for LLM response by polling."""
        import asyncio
        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return ""

            try:
                messages = self.session.get_messages()
                for msg in reversed(messages):
                    if hasattr(msg, 'data'):
                        data = msg.data
                        if hasattr(data, 'role') and data.role == 'assistant':
                            return self._extract_from_event(msg)
            except Exception:
                pass

            await asyncio.sleep(1.0)

    def _generate_mock_response(self) -> str:
        """Generate mock response for testing."""
        return """This section has been refined based on your feedback.

The key changes include:
- Improved clarity and structure
- Added more specific details
- Addressed the concerns raised in the feedback

The content now better aligns with the overall BRD objectives and maintains consistency with other sections."""
