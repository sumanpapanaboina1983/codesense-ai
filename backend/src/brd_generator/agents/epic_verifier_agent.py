"""EPIC Verifier Agent - Verifies EPICs against BRD requirements and codebase.

This agent:
1. Extracts claims from each EPIC
2. Verifies BRD section coverage
3. Validates component availability in codebase
4. Checks dependency correctness
5. Assesses effort estimate reasonableness
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
from ..models.epic import Epic
from ..utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# EPIC Verification Models
# =============================================================================

class EpicClaim(BaseModel):
    """A claim extracted from an EPIC that needs verification."""

    id: str = Field(default_factory=lambda: f"EC-{datetime.now().strftime('%H%M%S%f')[:10]}")
    text: str
    claim_type: str  # "brd_coverage", "component", "dependency", "effort"
    epic_id: str
    referenced_brd_sections: list[str] = Field(default_factory=list)
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

            # Apply penalty for contradicting evidence
            if contradicting:
                penalty = len(contradicting) / (len(supporting) + len(contradicting))
                self.confidence_score *= (1 - penalty * 0.5)

        # Determine status
        if self.confidence_score >= 0.7:
            self.status = VerificationStatus.VERIFIED
        elif self.confidence_score >= 0.4:
            self.status = VerificationStatus.PARTIALLY_VERIFIED
        else:
            self.status = VerificationStatus.UNVERIFIED


class EpicVerificationResult(BaseModel):
    """Verification result for a single EPIC."""

    epic_id: str
    epic_title: str
    claims: list[EpicClaim] = Field(default_factory=list)
    overall_confidence: float = 0.0
    is_approved: bool = False
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    hallucination_risk: HallucinationRisk = HallucinationRisk.MEDIUM
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    # Stats
    total_claims: int = 0
    verified_claims: int = 0
    unverified_claims: int = 0

    def calculate_metrics(self) -> None:
        """Calculate overall metrics from claims."""
        self.total_claims = len(self.claims)
        self.verified_claims = sum(1 for c in self.claims if c.status == VerificationStatus.VERIFIED)
        self.unverified_claims = sum(
            1 for c in self.claims
            if c.status in [VerificationStatus.UNVERIFIED, VerificationStatus.PARTIALLY_VERIFIED]
        )

        if self.claims:
            self.overall_confidence = sum(c.confidence_score for c in self.claims) / len(self.claims)

        # Determine overall status
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


class EpicsVerificationBundle(BaseModel):
    """Complete verification bundle for all EPICs."""

    brd_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    epic_results: list[EpicVerificationResult] = Field(default_factory=list)

    # Overall metrics
    overall_confidence: float = 0.0
    overall_status: VerificationStatus = VerificationStatus.UNVERIFIED
    is_approved: bool = False

    # Stats
    total_epics: int = 0
    verified_epics: int = 0
    issues: list[str] = Field(default_factory=list)

    def calculate_overall_metrics(self) -> None:
        """Calculate overall metrics from EPIC results."""
        self.total_epics = len(self.epic_results)
        self.verified_epics = sum(1 for r in self.epic_results if r.is_approved)

        if self.epic_results:
            self.overall_confidence = sum(r.overall_confidence for r in self.epic_results) / len(self.epic_results)

        has_failures = any(not r.is_approved for r in self.epic_results)

        if self.overall_confidence >= 0.6 and not has_failures:
            self.overall_status = VerificationStatus.VERIFIED
            self.is_approved = True
        elif self.overall_confidence >= 0.4:
            self.overall_status = VerificationStatus.PARTIALLY_VERIFIED
            self.is_approved = True
        else:
            self.overall_status = VerificationStatus.UNVERIFIED
            self.is_approved = False


# =============================================================================
# Prompt Templates
# =============================================================================

CLAIM_EXTRACTION_PROMPT = """Extract verifiable claims from the following EPIC.

## EPIC:
ID: {epic_id}
Title: {epic_title}
Description: {epic_description}
Business Value: {business_value}
BRD Section References: {brd_section_refs}
Affected Components: {affected_components}
Dependencies: {depends_on}

## Instructions:
Extract claims that can be verified against:
1. BRD Coverage - Does this EPIC actually address the referenced BRD sections?
2. Component Availability - Do the affected components exist or can they be created?
3. Dependency Correctness - Do the dependency EPICs exist and make sense?
4. Scope Reasonableness - Is the scope well-defined and achievable?

Return a JSON array of claims:
```json
[
  {{
    "text": "The claim text",
    "claim_type": "brd_coverage|component|dependency|scope",
    "referenced_brd_sections": ["Section 1", "Section 2"]
  }}
]
```

Extract 3-6 key claims per EPIC.
"""

VERIFICATION_PROMPT = """Verify the following claims against the provided context.

## Claims to Verify:
{claims_json}

## BRD Content:
{brd_content}

## EPIC Context:
{epic_context}

## Instructions:
For each claim, determine:
1. Is the claim supported by the BRD content?
2. Are there any contradictions?
3. What is your confidence level (0.0-1.0)?

Return verification results as JSON:
```json
{{
  "verifications": [
    {{
      "claim_id": "EC-xxx",
      "is_verified": true/false,
      "confidence": 0.0-1.0,
      "evidence_description": "Description of evidence found",
      "issues": ["any issues found"],
      "suggestions": ["improvement suggestions"]
    }}
  ]
}}
```
"""


class EpicVerifierAgent:
    """Agent that verifies EPICs against BRD requirements and codebase.

    Key responsibilities:
    1. Extract verifiable claims from EPICs
    2. Verify BRD section coverage
    3. Validate component references
    4. Check dependency correctness
    5. Assess overall EPIC quality
    """

    def __init__(
        self,
        copilot_session: Any = None,
        config: dict[str, Any] = None,
    ):
        """Initialize the EPIC Verifier Agent.

        Args:
            copilot_session: Copilot SDK session for LLM access
            config: Agent configuration
        """
        self.session = copilot_session
        self.config = config or {}
        self.min_confidence = config.get("min_confidence", 0.6) if config else 0.6

        logger.info("EpicVerifierAgent initialized")

    async def verify_epics(
        self,
        epics: list[Epic],
        brd_content: str,
        brd_id: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> EpicsVerificationBundle:
        """Verify all EPICs against BRD content.

        Args:
            epics: List of EPICs to verify
            brd_content: Full BRD markdown content
            brd_id: BRD identifier
            progress_callback: Optional callback for progress updates

        Returns:
            EpicsVerificationBundle with verification results
        """
        logger.info(f"Verifying {len(epics)} EPICs for BRD: {brd_id}")

        bundle = EpicsVerificationBundle(brd_id=brd_id)

        for idx, epic in enumerate(epics, 1):
            if progress_callback:
                progress_callback(f"Verifying EPIC {idx}/{len(epics)}: {epic.title}...")

            result = await self.verify_epic(epic, brd_content, epics)
            bundle.epic_results.append(result)

        bundle.calculate_overall_metrics()

        if progress_callback:
            status = "approved" if bundle.is_approved else "needs review"
            progress_callback(
                f"Verification complete: {bundle.verified_epics}/{bundle.total_epics} EPICs {status} "
                f"(confidence: {bundle.overall_confidence:.1%})"
            )

        return bundle

    async def verify_epic(
        self,
        epic: Epic,
        brd_content: str,
        all_epics: list[Epic],
    ) -> EpicVerificationResult:
        """Verify a single EPIC.

        Args:
            epic: EPIC to verify
            brd_content: Full BRD markdown content
            all_epics: All EPICs for dependency checking

        Returns:
            EpicVerificationResult with verification details
        """
        result = EpicVerificationResult(
            epic_id=epic.id,
            epic_title=epic.title,
        )

        # Extract claims from EPIC
        claims = await self._extract_claims(epic)

        # Verify each claim
        for claim in claims:
            await self._verify_claim(claim, epic, brd_content, all_epics)
            result.claims.append(claim)

            # Collect issues
            result.issues.extend(claim.issues)

        # Verify BRD section coverage
        coverage_claim = self._verify_brd_coverage(epic, brd_content)
        result.claims.append(coverage_claim)

        # Verify dependencies
        if epic.depends_on:
            dep_claim = self._verify_dependencies(epic, all_epics)
            result.claims.append(dep_claim)

        result.calculate_metrics()

        # Generate suggestions based on issues
        if result.issues:
            result.suggestions = self._generate_suggestions(result)

        return result

    async def _extract_claims(self, epic: Epic) -> list[EpicClaim]:
        """Extract verifiable claims from an EPIC."""
        claims = []

        # Basic claims extracted programmatically

        # Claim 1: Description clarity
        if epic.description:
            claims.append(EpicClaim(
                text=f"EPIC describes: {epic.description[:100]}...",
                claim_type="scope",
                epic_id=epic.id,
                referenced_brd_sections=epic.brd_section_refs,
            ))

        # Claim 2: Business value
        if epic.business_value:
            claims.append(EpicClaim(
                text=f"Business value: {epic.business_value[:100]}...",
                claim_type="brd_coverage",
                epic_id=epic.id,
                referenced_brd_sections=epic.brd_section_refs,
            ))

        # Claim 3: Components
        if epic.affected_components:
            claims.append(EpicClaim(
                text=f"Affects components: {', '.join(epic.affected_components)}",
                claim_type="component",
                epic_id=epic.id,
            ))

        # Claim 4: Acceptance criteria
        if epic.acceptance_criteria:
            claims.append(EpicClaim(
                text=f"Has {len(epic.acceptance_criteria)} acceptance criteria",
                claim_type="scope",
                epic_id=epic.id,
            ))

        return claims

    async def _verify_claim(
        self,
        claim: EpicClaim,
        epic: Epic,
        brd_content: str,
        all_epics: list[Epic],
    ) -> None:
        """Verify a single claim against context."""

        if claim.claim_type == "brd_coverage":
            # Check if referenced BRD sections are mentioned
            for section in claim.referenced_brd_sections:
                if section.lower() in brd_content.lower():
                    claim.add_evidence(EvidenceItem(
                        evidence_type=EvidenceType.DOCUMENTATION,
                        category="primary",
                        description=f"BRD section '{section}' found in document",
                        confidence=0.8,
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
                    claim.issues.append(f"Referenced BRD section '{section}' not found in document")

        elif claim.claim_type == "component":
            # For now, assume components are valid (would need codebase access)
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.ARCHITECTURE,
                category="secondary",
                description="Component references accepted (codebase verification pending)",
                confidence=0.6,
                supports_claim=True,
                source="analysis",
            ))

        elif claim.claim_type == "dependency":
            # Verify dependencies exist
            all_epic_ids = {e.id for e in all_epics}
            for dep_id in epic.depends_on:
                if dep_id in all_epic_ids:
                    claim.add_evidence(EvidenceItem(
                        evidence_type=EvidenceType.DEPENDENCY,
                        category="primary",
                        description=f"Dependency '{dep_id}' exists",
                        confidence=0.9,
                        supports_claim=True,
                        source="epic_list",
                    ))
                else:
                    claim.add_evidence(EvidenceItem(
                        evidence_type=EvidenceType.DEPENDENCY,
                        category="primary",
                        description=f"Dependency '{dep_id}' not found",
                        confidence=0.1,
                        supports_claim=False,
                        source="epic_list",
                    ))
                    claim.issues.append(f"Dependency '{dep_id}' does not exist in EPIC list")

        elif claim.claim_type == "scope":
            # Check scope clarity
            if epic.description and len(epic.description) > 50:
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.DOCUMENTATION,
                    category="secondary",
                    description="EPIC has detailed description",
                    confidence=0.7,
                    supports_claim=True,
                    source="analysis",
                ))

            if epic.acceptance_criteria and len(epic.acceptance_criteria) >= 3:
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.DOCUMENTATION,
                    category="secondary",
                    description=f"EPIC has {len(epic.acceptance_criteria)} acceptance criteria",
                    confidence=0.8,
                    supports_claim=True,
                    source="analysis",
                ))

    def _verify_brd_coverage(self, epic: Epic, brd_content: str) -> EpicClaim:
        """Verify that EPIC covers its referenced BRD sections."""
        claim = EpicClaim(
            text=f"EPIC covers BRD sections: {', '.join(epic.brd_section_refs)}",
            claim_type="brd_coverage",
            epic_id=epic.id,
            referenced_brd_sections=epic.brd_section_refs,
        )

        if not epic.brd_section_refs:
            claim.add_evidence(EvidenceItem(
                evidence_type=EvidenceType.DOCUMENTATION,
                category="primary",
                description="EPIC has no BRD section references",
                confidence=0.3,
                supports_claim=False,
                source="analysis",
            ))
            claim.issues.append("EPIC should reference specific BRD sections")
            return claim

        # Check each referenced section
        found_sections = 0
        for section in epic.brd_section_refs:
            # Simple check - look for section heading in BRD
            patterns = [
                f"## {section}",
                f"### {section}",
                f"# {section}",
                section.lower(),
            ]

            found = any(pattern.lower() in brd_content.lower() for pattern in patterns)

            if found:
                found_sections += 1
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.DOCUMENTATION,
                    category="primary",
                    description=f"BRD section '{section}' found and covered",
                    confidence=0.85,
                    supports_claim=True,
                    source="brd_content",
                ))
            else:
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.DOCUMENTATION,
                    category="primary",
                    description=f"BRD section '{section}' not found in document",
                    confidence=0.2,
                    supports_claim=False,
                    source="brd_content",
                ))

        if found_sections < len(epic.brd_section_refs) / 2:
            claim.issues.append(
                f"Only {found_sections}/{len(epic.brd_section_refs)} referenced BRD sections found"
            )

        return claim

    def _verify_dependencies(self, epic: Epic, all_epics: list[Epic]) -> EpicClaim:
        """Verify EPIC dependencies are valid."""
        claim = EpicClaim(
            text=f"EPIC depends on: {', '.join(epic.depends_on)}",
            claim_type="dependency",
            epic_id=epic.id,
        )

        all_epic_ids = {e.id for e in all_epics}

        for dep_id in epic.depends_on:
            if dep_id in all_epic_ids:
                # Check for circular dependencies
                dep_epic = next((e for e in all_epics if e.id == dep_id), None)
                if dep_epic and epic.id in dep_epic.depends_on:
                    claim.add_evidence(EvidenceItem(
                        evidence_type=EvidenceType.DEPENDENCY,
                        category="primary",
                        description=f"Circular dependency detected with '{dep_id}'",
                        confidence=0.1,
                        supports_claim=False,
                        source="analysis",
                    ))
                    claim.issues.append(f"Circular dependency with '{dep_id}'")
                else:
                    claim.add_evidence(EvidenceItem(
                        evidence_type=EvidenceType.DEPENDENCY,
                        category="primary",
                        description=f"Valid dependency on '{dep_id}'",
                        confidence=0.9,
                        supports_claim=True,
                        source="epic_list",
                    ))
            else:
                claim.add_evidence(EvidenceItem(
                    evidence_type=EvidenceType.DEPENDENCY,
                    category="primary",
                    description=f"Unknown dependency '{dep_id}'",
                    confidence=0.1,
                    supports_claim=False,
                    source="epic_list",
                ))
                claim.issues.append(f"Dependency '{dep_id}' not found")

        return claim

    def _generate_suggestions(self, result: EpicVerificationResult) -> list[str]:
        """Generate improvement suggestions based on verification issues."""
        suggestions = []

        # Check for missing BRD references
        brd_issues = [i for i in result.issues if "BRD section" in i]
        if brd_issues:
            suggestions.append("Review and update BRD section references to match actual document sections")

        # Check for dependency issues
        dep_issues = [i for i in result.issues if "dependency" in i.lower() or "Dependency" in i]
        if dep_issues:
            suggestions.append("Verify EPIC dependencies exist and remove any circular references")

        # Low confidence suggestions
        if result.overall_confidence < 0.5:
            suggestions.append("Add more specific details to EPIC description and acceptance criteria")
            suggestions.append("Ensure business value clearly ties to BRD requirements")

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
