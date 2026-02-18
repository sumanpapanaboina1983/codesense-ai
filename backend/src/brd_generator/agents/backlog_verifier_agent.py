"""Backlog Verifier Agent - Verifies backlog items against EPICs, BRD, and codebase.

This agent:
1. Extracts claims from each backlog item
2. Verifies implementability with current codebase
3. Validates traceability to EPICs and BRD
4. Checks file references
5. Assesses acceptance criteria testability
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from ..models.verification import (
    EvidenceType,
    EvidenceItem,
    CodeReference,
    VerificationStatus,
    HallucinationRisk,
    ConfidenceLevel,
)
from ..models.epic import Epic, BacklogItem
from ..utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Backlog Verification Models
# =============================================================================

class BacklogClaim(BaseModel):
    """A claim extracted from a backlog item that needs verification."""

    id: str = Field(default_factory=lambda: f"BC-{datetime.now().strftime('%H%M%S%f')[:10]}")
    text: str
    claim_type: str  # "implementability", "traceability", "testability", "file_ref"
    item_id: str
    epic_id: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence_score: float = 0.0
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    issues: list[str] = Field(default_factory=list)

    def add_evidence(self, evidence: EvidenceItem) -> None:
        """Add evidence and recalculate confidence."""
        self.evidence.append(evidence)
        self._recalculate_confidence()

    def _recalculate_confidence(self) -> None:
        """Recalculate confidence based on evidence."""
        if not self.evidence:
            self.confidence_score = 0.0
            self.status = VerificationStatus.UNVERIFIED
            return

        supporting = [e for e in self.evidence if e.supports_claim]
        contradicting = [e for e in self.evidence if not e.supports_claim]

        if contradicting and not supporting:
            self.confidence_score = 0.0
            self.status = VerificationStatus.CONTRADICTED
            return

        if supporting:
            self.confidence_score = sum(e.confidence for e in supporting) / len(supporting)

            if contradicting:
                penalty = len(contradicting) / (len(supporting) + len(contradicting))
                self.confidence_score *= (1 - penalty * 0.5)

        if self.confidence_score >= 0.7:
            self.status = VerificationStatus.VERIFIED
        elif self.confidence_score >= 0.4:
            self.status = VerificationStatus.PARTIALLY_VERIFIED
        else:
            self.status = VerificationStatus.UNVERIFIED


class BacklogVerificationResult(BaseModel):
    """Verification result for a single backlog item."""

    item_id: str
    item_title: str
    epic_id: str
    claims: list[BacklogClaim] = Field(default_factory=list)
    overall_confidence: float = 0.0
    is_approved: bool = False
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    hallucination_risk: HallucinationRisk = HallucinationRisk.MEDIUM
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    # Stats
    total_claims: int = 0
    verified_claims: int = 0

    def calculate_metrics(self) -> None:
        """Calculate overall metrics from claims."""
        self.total_claims = len(self.claims)
        self.verified_claims = sum(1 for c in self.claims if c.status == VerificationStatus.VERIFIED)

        if self.claims:
            self.overall_confidence = sum(c.confidence_score for c in self.claims) / len(self.claims)

        has_contradictions = any(c.status == VerificationStatus.CONTRADICTED for c in self.claims)

        if has_contradictions:
            self.verification_status = VerificationStatus.CONTRADICTED
            self.hallucination_risk = HallucinationRisk.HIGH
            self.is_approved = False
        elif self.overall_confidence >= 0.7:
            self.verification_status = VerificationStatus.VERIFIED
            self.hallucination_risk = HallucinationRisk.NONE
            self.is_approved = True
        elif self.overall_confidence >= 0.4:
            self.verification_status = VerificationStatus.PARTIALLY_VERIFIED
            self.hallucination_risk = HallucinationRisk.LOW
            self.is_approved = True
        else:
            self.verification_status = VerificationStatus.UNVERIFIED
            self.hallucination_risk = HallucinationRisk.MEDIUM
            self.is_approved = False


class BacklogsVerificationBundle(BaseModel):
    """Complete verification bundle for all backlog items."""

    brd_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    item_results: list[BacklogVerificationResult] = Field(default_factory=list)

    # Overall metrics
    overall_confidence: float = 0.0
    overall_status: VerificationStatus = VerificationStatus.UNVERIFIED
    is_approved: bool = False

    # Stats
    total_items: int = 0
    verified_items: int = 0
    items_by_epic: dict[str, int] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)

    def calculate_overall_metrics(self) -> None:
        """Calculate overall metrics from item results."""
        self.total_items = len(self.item_results)
        self.verified_items = sum(1 for r in self.item_results if r.is_approved)

        # Group by EPIC
        for result in self.item_results:
            self.items_by_epic[result.epic_id] = self.items_by_epic.get(result.epic_id, 0) + 1

        if self.item_results:
            self.overall_confidence = sum(r.overall_confidence for r in self.item_results) / len(self.item_results)

        has_failures = any(not r.is_approved for r in self.item_results)
        failure_rate = (self.total_items - self.verified_items) / max(self.total_items, 1)

        # Allow up to 20% failure rate
        if self.overall_confidence >= 0.6 and failure_rate <= 0.2:
            self.overall_status = VerificationStatus.VERIFIED
            self.is_approved = True
        elif self.overall_confidence >= 0.4:
            self.overall_status = VerificationStatus.PARTIALLY_VERIFIED
            self.is_approved = True
        else:
            self.overall_status = VerificationStatus.UNVERIFIED
            self.is_approved = False


class BacklogVerifierAgent:
    """Agent that verifies backlog items against EPICs, BRD, and codebase.

    Key responsibilities:
    1. Verify backlog items trace back to EPICs and BRD
    2. Check implementability based on codebase structure
    3. Validate file references
    4. Assess acceptance criteria testability
    """

    def __init__(
        self,
        copilot_session: Any = None,
        config: dict[str, Any] = None,
    ):
        """Initialize the Backlog Verifier Agent.

        Args:
            copilot_session: Copilot SDK session for LLM access
            config: Agent configuration
        """
        self.session = copilot_session
        self.config = config or {}
        self.min_confidence = config.get("min_confidence", 0.6) if config else 0.6

        logger.info("BacklogVerifierAgent initialized")

    async def verify_backlogs(
        self,
        items: list[BacklogItem],
        epics: list[Epic],
        brd_content: str,
        brd_id: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> BacklogsVerificationBundle:
        """Verify all backlog items against EPICs and BRD.

        Args:
            items: List of backlog items to verify
            epics: List of EPICs for traceability checking
            brd_content: Full BRD markdown content
            brd_id: BRD identifier
            progress_callback: Optional callback for progress updates

        Returns:
            BacklogsVerificationBundle with verification results
        """
        logger.info(f"Verifying {len(items)} backlog items for BRD: {brd_id}")

        bundle = BacklogsVerificationBundle(brd_id=brd_id)

        for idx, item in enumerate(items, 1):
            if progress_callback:
                progress_callback(f"Verifying item {idx}/{len(items)}: {item.title[:50]}...")

            epic = next((e for e in epics if e.id == item.epic_id), None)
            result = await self.verify_item(item, epic, brd_content, epics)
            bundle.item_results.append(result)

        bundle.calculate_overall_metrics()

        if progress_callback:
            status = "approved" if bundle.is_approved else "needs review"
            progress_callback(
                f"Verification complete: {bundle.verified_items}/{bundle.total_items} items {status} "
                f"(confidence: {bundle.overall_confidence:.1%})"
            )

        return bundle

    async def verify_item(
        self,
        item: BacklogItem,
        epic: Optional[Epic],
        brd_content: str,
        all_epics: list[Epic],
    ) -> BacklogVerificationResult:
        """Verify a single backlog item.

        Args:
            item: Backlog item to verify
            epic: Parent EPIC (if found)
            brd_content: Full BRD markdown content
            all_epics: All EPICs for context

        Returns:
            BacklogVerificationResult with verification details
        """
        result = BacklogVerificationResult(
            item_id=item.id,
            item_title=item.title,
            epic_id=item.epic_id,
        )

        # Verify traceability to EPIC
        trace_claim = self._verify_epic_traceability(item, epic)
        result.claims.append(trace_claim)
        result.issues.extend(trace_claim.issues)

        # Verify BRD traceability
        brd_claim = self._verify_brd_traceability(item, brd_content)
        result.claims.append(brd_claim)
        result.issues.extend(brd_claim.issues)

        # Verify implementability
        impl_claim = self._verify_implementability(item)
        result.claims.append(impl_claim)
        result.issues.extend(impl_claim.issues)

        # Verify acceptance criteria testability
        test_claim = self._verify_testability(item)
        result.claims.append(test_claim)
        result.issues.extend(test_claim.issues)

        # Verify file references if present
        if item.files_to_modify or item.files_to_create:
            file_claim = self._verify_file_references(item)
            result.claims.append(file_claim)
            result.issues.extend(file_claim.issues)

        result.calculate_metrics()

        # Generate suggestions
        if result.issues:
            result.suggestions = self._generate_suggestions(result, item)

        return result

    def _verify_epic_traceability(
        self,
        item: BacklogItem,
        epic: Optional[Epic],
    ) -> BacklogClaim:
        """Verify that item traces back to its EPIC."""
        claim = BacklogClaim(
            text=f"Item traces to EPIC: {item.epic_id}",
            claim_type="traceability",
            item_id=item.id,
            epic_id=item.epic_id,
        )

        if not epic:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.DEPENDENCY,
                category="primary",
                description=f"Parent EPIC '{item.epic_id}' not found",
                confidence=0.1,
                supports_claim=False,
                source="epic_list",
            ))
            claim.issues.append(f"Parent EPIC '{item.epic_id}' does not exist")
            return claim

        # Check if item aligns with EPIC scope
        claim.add_evidence(EvidenceItem(
            evidence_type=EvidenceType.DEPENDENCY,
            category="primary",
            description=f"Item linked to EPIC '{epic.title}'",
            confidence=0.9,
            supports_claim=True,
            source="epic_list",
        ))

        # Check for keyword overlap between item and EPIC
        epic_keywords = set(epic.title.lower().split() + epic.description.lower().split()[:20])
        item_keywords = set(item.title.lower().split() + item.description.lower().split()[:20])

        # Remove common words
        common_words = {'the', 'a', 'an', 'and', 'or', 'to', 'for', 'of', 'in', 'on', 'is', 'are', 'be', 'as', 'with'}
        epic_keywords -= common_words
        item_keywords -= common_words

        overlap = epic_keywords & item_keywords
        overlap_ratio = len(overlap) / max(len(item_keywords), 1)

        if overlap_ratio >= 0.2:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.DOCUMENTATION,
                category="secondary",
                description=f"Item content aligns with EPIC scope ({len(overlap)} shared terms)",
                confidence=0.7,
                supports_claim=True,
                source="analysis",
            ))
        elif overlap_ratio < 0.1:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.DOCUMENTATION,
                category="secondary",
                description="Item may not align with EPIC scope (low keyword overlap)",
                confidence=0.4,
                supports_claim=True,
                source="analysis",
            ))
            claim.issues.append("Item content may not align well with parent EPIC scope")

        return claim

    def _verify_brd_traceability(
        self,
        item: BacklogItem,
        brd_content: str,
    ) -> BacklogClaim:
        """Verify that item traces back to BRD requirements."""
        claim = BacklogClaim(
            text=f"Item traces to BRD sections: {', '.join(item.brd_section_refs) if item.brd_section_refs else 'none'}",
            claim_type="traceability",
            item_id=item.id,
            epic_id=item.epic_id,
        )

        if not item.brd_section_refs:
            # Check if item content relates to BRD
            item_keywords = set(item.title.lower().split() + item.description.lower().split()[:30])
            brd_keywords = set(brd_content.lower().split()[:200])

            common_words = {'the', 'a', 'an', 'and', 'or', 'to', 'for', 'of', 'in', 'on', 'is', 'are', 'be', 'as', 'with'}
            item_keywords -= common_words
            brd_keywords -= common_words

            overlap = item_keywords & brd_keywords

            if len(overlap) >= 3:
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.DOCUMENTATION,
                    category="secondary",
                    description=f"Item content relates to BRD ({len(overlap)} shared terms)",
                    confidence=0.6,
                    supports_claim=True,
                    source="analysis",
                ))
            else:
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.DOCUMENTATION,
                    category="secondary",
                    description="No explicit BRD section references",
                    confidence=0.5,
                    supports_claim=True,
                    source="analysis",
                ))
            return claim

        # Verify each referenced section
        found_sections = 0
        for section in item.brd_section_refs:
            patterns = [
                f"## {section}",
                f"### {section}",
                section.lower(),
            ]

            found = any(pattern.lower() in brd_content.lower() for pattern in patterns)

            if found:
                found_sections += 1
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.DOCUMENTATION,
                    category="primary",
                    description=f"BRD section '{section}' found",
                    confidence=0.85,
                    supports_claim=True,
                    source="brd_content",
                ))
            else:
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.DOCUMENTATION,
                    category="primary",
                    description=f"BRD section '{section}' not found",
                    confidence=0.3,
                    supports_claim=False,
                    source="brd_content",
                ))

        if found_sections < len(item.brd_section_refs) / 2:
            claim.issues.append(
                f"Only {found_sections}/{len(item.brd_section_refs)} BRD section references verified"
            )

        return claim

    def _verify_implementability(self, item: BacklogItem) -> BacklogClaim:
        """Verify that item is implementable."""
        claim = BacklogClaim(
            text=f"Item is implementable: {item.title}",
            claim_type="implementability",
            item_id=item.id,
            epic_id=item.epic_id,
        )

        # Check description completeness
        if len(item.description) >= 50:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.DOCUMENTATION,
                category="secondary",
                description="Item has adequate description",
                confidence=0.7,
                supports_claim=True,
                source="analysis",
            ))
        else:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.DOCUMENTATION,
                category="secondary",
                description="Item description may be too brief",
                confidence=0.4,
                supports_claim=True,
                source="analysis",
            ))
            claim.issues.append("Item description should be more detailed")

        # Check for user story format
        if item.item_type == "user_story":
            if item.as_a and item.i_want and item.so_that:
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.DOCUMENTATION,
                    category="secondary",
                    description="User story format is complete (As a/I want/So that)",
                    confidence=0.8,
                    supports_claim=True,
                    source="analysis",
                ))
            else:
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.DOCUMENTATION,
                    category="secondary",
                    description="User story format incomplete",
                    confidence=0.5,
                    supports_claim=True,
                    source="analysis",
                ))
                claim.issues.append("User story should have complete As a/I want/So that format")

        # Check for technical notes
        if item.technical_notes:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.DOCUMENTATION,
                category="secondary",
                description="Item includes technical implementation notes",
                confidence=0.75,
                supports_claim=True,
                source="analysis",
            ))

        return claim

    def _verify_testability(self, item: BacklogItem) -> BacklogClaim:
        """Verify that acceptance criteria are testable."""
        claim = BacklogClaim(
            text=f"Acceptance criteria are testable ({len(item.acceptance_criteria)} criteria)",
            claim_type="testability",
            item_id=item.id,
            epic_id=item.epic_id,
        )

        if not item.acceptance_criteria:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.DOCUMENTATION,
                category="primary",
                description="No acceptance criteria defined",
                confidence=0.2,
                supports_claim=False,
                source="analysis",
            ))
            claim.issues.append("Item must have acceptance criteria for testability")
            return claim

        # Check acceptance criteria quality
        testable_criteria = 0
        for criterion in item.acceptance_criteria:
            # Testable criteria typically have specific, measurable language
            testable_keywords = ['should', 'must', 'will', 'displays', 'shows', 'returns',
                               'validates', 'when', 'given', 'then', 'able to', 'can']

            is_testable = any(kw in criterion.lower() for kw in testable_keywords)
            has_specifics = len(criterion) > 20  # Not too vague

            if is_testable and has_specifics:
                testable_criteria += 1

        ratio = testable_criteria / len(item.acceptance_criteria)

        if ratio >= 0.8:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.DOCUMENTATION,
                category="primary",
                description=f"Most acceptance criteria appear testable ({testable_criteria}/{len(item.acceptance_criteria)})",
                confidence=0.85,
                supports_claim=True,
                source="analysis",
            ))
        elif ratio >= 0.5:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.DOCUMENTATION,
                category="primary",
                description=f"Some acceptance criteria may need refinement ({testable_criteria}/{len(item.acceptance_criteria)} testable)",
                confidence=0.6,
                supports_claim=True,
                source="analysis",
            ))
        else:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.DOCUMENTATION,
                category="primary",
                description=f"Many acceptance criteria lack testable specifics ({testable_criteria}/{len(item.acceptance_criteria)} testable)",
                confidence=0.35,
                supports_claim=True,
                source="analysis",
            ))
            claim.issues.append("Acceptance criteria should be more specific and testable")

        return claim

    def _verify_file_references(self, item: BacklogItem) -> BacklogClaim:
        """Verify file references are reasonable."""
        claim = BacklogClaim(
            text=f"File references: {len(item.files_to_modify)} to modify, {len(item.files_to_create)} to create",
            claim_type="file_ref",
            item_id=item.id,
            epic_id=item.epic_id,
        )

        # Check file paths look reasonable
        all_files = item.files_to_modify + item.files_to_create

        valid_extensions = ['.py', '.ts', '.tsx', '.js', '.jsx', '.java', '.go', '.rs',
                          '.rb', '.php', '.cs', '.cpp', '.c', '.h', '.css', '.scss',
                          '.html', '.yaml', '.yml', '.json', '.xml', '.sql', '.md']

        valid_files = sum(
            1 for f in all_files
            if any(f.endswith(ext) for ext in valid_extensions) or '/' in f
        )

        if valid_files == len(all_files) and all_files:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.CODE_REFERENCE,
                category="secondary",
                description=f"All {len(all_files)} file references have valid extensions/paths",
                confidence=0.7,
                supports_claim=True,
                source="analysis",
            ))
        elif valid_files > 0:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.CODE_REFERENCE,
                category="secondary",
                description=f"{valid_files}/{len(all_files)} file references appear valid",
                confidence=0.5,
                supports_claim=True,
                source="analysis",
            ))
        else:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.CODE_REFERENCE,
                category="secondary",
                description="File references may not be valid paths",
                confidence=0.3,
                supports_claim=False,
                source="analysis",
            ))
            claim.issues.append("File references should include valid file paths")

        return claim

    def _generate_suggestions(
        self,
        result: BacklogVerificationResult,
        item: BacklogItem,
    ) -> list[str]:
        """Generate improvement suggestions based on verification issues."""
        suggestions = []

        # Traceability issues
        trace_issues = [i for i in result.issues if "EPIC" in i or "BRD" in i]
        if trace_issues:
            suggestions.append("Update traceability references to link to correct EPIC and BRD sections")

        # Description issues
        if any("description" in i.lower() for i in result.issues):
            suggestions.append("Add more detail to the item description")

        # Acceptance criteria issues
        if any("acceptance criteria" in i.lower() for i in result.issues):
            suggestions.append("Make acceptance criteria more specific and measurable")

        # User story format
        if any("user story" in i.lower() for i in result.issues):
            suggestions.append("Complete the user story with As a/I want/So that format")

        return suggestions

    async def _send_to_llm(self, prompt: str) -> str:
        """Send prompt to LLM via Copilot SDK."""
        if not self.session:
            logger.warning("No Copilot session, returning empty response")
            return "{}"

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

        return "{}"

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
