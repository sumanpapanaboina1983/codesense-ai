"""Verification models for BRD claim validation and evidence gathering."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    """Types of evidence that can support a claim."""

    # Primary Evidence (Code)
    CODE_REFERENCE = "code_reference"  # Direct reference to code
    CALL_GRAPH = "call_graph"  # Function/method call relationships
    DATA_FLOW = "data_flow"  # Data flow analysis
    METHOD_ANALYSIS = "method_analysis"  # Method phases/steps analysis
    TEST_COVERAGE = "test_coverage"  # Test coverage data
    AST_ANALYSIS = "ast_analysis"  # AST-based structural analysis

    # Secondary Evidence (Configuration/Architecture)
    CONFIGURATION = "configuration"  # Config files (yml, json, properties)
    DEPENDENCY = "dependency"  # Dependency relationships
    ARCHITECTURE = "architecture"  # Architectural patterns
    PATTERN = "pattern"  # Design pattern detection

    # Supporting Evidence
    DOCUMENTATION = "documentation"  # Existing documentation
    METRICS = "metrics"  # Code metrics (complexity, LOC, etc.)
    SIMILAR_FEATURE = "similar_feature"  # Similar existing implementation


class ClaimType(str, Enum):
    """Types of business-level claims in a BRD."""

    # Process/Workflow claims
    PROCESS = "process"  # "Orders go through a 7-step workflow"
    WORKFLOW = "workflow"  # "User authentication follows OAuth2 flow"
    BEHAVIOR = "behavior"  # "System retries failed payments 3 times"

    # Data claims
    DATA_FLOW = "data_flow"  # "User data flows from API to database"
    DATA_VALIDATION = "data_validation"  # "All inputs are validated before processing"
    DATA_TRANSFORMATION = "data_transformation"  # "Prices are converted to cents"

    # Integration claims
    INTEGRATION = "integration"  # "System integrates with Stripe for payments"
    API_CONTRACT = "api_contract"  # "API returns paginated results"
    EVENT_DRIVEN = "event_driven"  # "Order completion triggers email notification"

    # Non-functional claims
    PERFORMANCE = "performance"  # "Response time under 200ms"
    SECURITY = "security"  # "All data encrypted at rest"
    SCALABILITY = "scalability"  # "Handles 1000 concurrent users"

    # Business logic claims
    BUSINESS_RULE = "business_rule"  # "Discount applies only to orders over $100"
    CALCULATION = "calculation"  # "Tax calculated based on shipping address"
    STATE_MACHINE = "state_machine"  # "Order status transitions: pending -> confirmed -> shipped"

    # General
    GENERAL = "general"  # Uncategorized claims


class ConfidenceLevel(str, Enum):
    """Confidence level for evidence."""

    HIGH = "high"  # >= 0.8
    MEDIUM = "medium"  # >= 0.5
    LOW = "low"  # >= 0.3
    INSUFFICIENT = "insufficient"  # < 0.3


class VerificationStatus(str, Enum):
    """Status of claim verification."""

    VERIFIED = "verified"  # Claim is supported by evidence
    PARTIALLY_VERIFIED = "partially_verified"  # Some evidence found
    UNVERIFIED = "unverified"  # No evidence found
    CONTRADICTED = "contradicted"  # Evidence contradicts claim
    NEEDS_SME_REVIEW = "needs_sme_review"  # Requires expert review


class HallucinationRisk(str, Enum):
    """Risk level for hallucination."""

    NONE = "none"  # No hallucination detected
    LOW = "low"  # Minor discrepancies
    MEDIUM = "medium"  # Some unsupported claims
    HIGH = "high"  # Significant unsupported content
    CRITICAL = "critical"  # Major hallucination detected


class CodeReference(BaseModel):
    """Reference to a specific code location."""

    file_path: str
    start_line: int
    end_line: int
    snippet: Optional[str] = None  # Relevant code snippet
    language: Optional[str] = None
    entity_type: Optional[str] = None  # Class, Method, Function, etc.
    entity_name: Optional[str] = None

    @property
    def loc(self) -> int:
        """Lines of code in this reference."""
        return self.end_line - self.start_line + 1

    def to_string(self) -> str:
        """Format as file:line reference."""
        return f"{self.file_path}:{self.start_line}-{self.end_line} [{self.loc} LOC]"


class CallGraphEvidence(BaseModel):
    """Evidence from call graph analysis."""

    source_entity: str  # Caller
    target_entity: str  # Callee
    relationship: str  # CALLS, IMPORTS, etc.
    source_file: Optional[str] = None
    target_file: Optional[str] = None
    call_count: int = 1


class EvidenceItem(BaseModel):
    """A single piece of evidence supporting or contradicting a claim.

    Evidence is categorized as:
    - Primary Evidence (Code): Direct code analysis, call graphs, method analysis
    - Secondary Evidence (Configuration): Config files, environment settings
    - Supporting Evidence: Tests, documentation, metrics
    """

    id: str = Field(default_factory=lambda: f"EV-{datetime.now().strftime('%H%M%S%f')[:10]}")
    evidence_type: EvidenceType
    category: str = "primary"  # primary, secondary, supporting
    description: str
    confidence: float = Field(ge=0.0, le=1.0)  # 0-1 confidence score

    # Evidence details based on type
    code_references: list[CodeReference] = Field(default_factory=list)
    call_graph: list[CallGraphEvidence] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

    # Additional evidence details
    method_phases: list[str] = Field(default_factory=list)  # For workflow claims: list of phases/steps
    config_values: dict[str, str] = Field(default_factory=dict)  # For config evidence
    test_cases: list[str] = Field(default_factory=list)  # Test case names that validate

    # Source information
    source: str = ""  # Where evidence came from (neo4j, filesystem, ast, llm)
    query_used: Optional[str] = None  # Cypher query or grep pattern used
    analysis_method: Optional[str] = None  # How evidence was gathered

    # Verification
    supports_claim: bool = True  # True if evidence supports, False if contradicts
    notes: Optional[str] = None

    # Hallucination check for this evidence
    hallucination_flags: list[str] = Field(default_factory=list)  # Any concerns
    hallucination_risk_pct: float = 0.0  # 0-100% risk

    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Get confidence level from score."""
        if self.confidence >= 0.8:
            return ConfidenceLevel.HIGH
        elif self.confidence >= 0.5:
            return ConfidenceLevel.MEDIUM
        elif self.confidence >= 0.3:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.INSUFFICIENT


class Claim(BaseModel):
    """A claim extracted from BRD content that needs verification.

    BRD claims are business-level statements, not technical implementation details.
    Examples:
    - "Orders go through a 7-step workflow"
    - "System retries failed payments 3 times"
    - "All user data is encrypted at rest"
    """

    id: str = Field(default_factory=lambda: f"CLM-{datetime.now().strftime('%H%M%S%f')[:10]}")
    text: str  # The claim text (business-level statement)
    section: str  # BRD section where claim appears
    claim_type: str = "general"  # See ClaimType enum

    # Business-level keywords/concepts extracted from the claim
    keywords: list[str] = Field(default_factory=list)  # Key business terms
    quantifiers: list[str] = Field(default_factory=list)  # Numbers, counts, percentages
    actions: list[str] = Field(default_factory=list)  # Verbs describing behavior

    # Entities that might be mentioned (for code correlation)
    mentioned_entities: list[str] = Field(default_factory=list)  # Inferred classes, methods
    mentioned_files: list[str] = Field(default_factory=list)
    mentioned_components: list[str] = Field(default_factory=list)

    # Verification search hints
    search_patterns: list[str] = Field(default_factory=list)  # Patterns to search in code
    expected_code_patterns: list[str] = Field(default_factory=list)  # What to look for

    # Verification results
    evidence: list[EvidenceItem] = Field(default_factory=list)
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    confidence_score: float = 0.0
    hallucination_risk: HallucinationRisk = HallucinationRisk.MEDIUM

    # SME review flag
    needs_sme_review: bool = False
    sme_review_reason: Optional[str] = None

    # Feedback for regeneration
    feedback: Optional[str] = None
    suggested_correction: Optional[str] = None

    def add_evidence(self, evidence: EvidenceItem) -> None:
        """Add evidence and recalculate confidence."""
        self.evidence.append(evidence)
        self._recalculate_confidence()

    def _recalculate_confidence(self) -> None:
        """Recalculate overall confidence based on evidence."""
        if not self.evidence:
            self.confidence_score = 0.0
            self.status = VerificationStatus.UNVERIFIED
            self.hallucination_risk = HallucinationRisk.HIGH
            return

        # Calculate weighted average of supporting evidence
        supporting = [e for e in self.evidence if e.supports_claim]
        contradicting = [e for e in self.evidence if not e.supports_claim]

        if contradicting and not supporting:
            self.confidence_score = 0.0
            self.status = VerificationStatus.CONTRADICTED
            self.hallucination_risk = HallucinationRisk.CRITICAL
            return

        if supporting:
            # Weight by evidence type importance
            weights = {
                EvidenceType.CODE_REFERENCE: 1.0,
                EvidenceType.CALL_GRAPH: 0.9,
                EvidenceType.DATA_FLOW: 0.85,
                EvidenceType.DEPENDENCY: 0.8,
                EvidenceType.ARCHITECTURE: 0.75,
                EvidenceType.TEST_COVERAGE: 0.7,
                EvidenceType.METRICS: 0.65,
                EvidenceType.DOCUMENTATION: 0.6,
                EvidenceType.PATTERN: 0.55,
                EvidenceType.SIMILAR_FEATURE: 0.5,
            }

            weighted_sum = sum(
                e.confidence * weights.get(e.evidence_type, 0.5)
                for e in supporting
            )
            total_weight = sum(
                weights.get(e.evidence_type, 0.5) for e in supporting
            )

            self.confidence_score = weighted_sum / total_weight if total_weight > 0 else 0.0

            # Apply penalty for contradicting evidence
            if contradicting:
                penalty = len(contradicting) / (len(supporting) + len(contradicting))
                self.confidence_score *= (1 - penalty * 0.5)

        # Determine status
        if self.confidence_score >= 0.8:
            self.status = VerificationStatus.VERIFIED
            self.hallucination_risk = HallucinationRisk.NONE
        elif self.confidence_score >= 0.5:
            self.status = VerificationStatus.PARTIALLY_VERIFIED
            self.hallucination_risk = HallucinationRisk.LOW
        elif self.confidence_score >= 0.3:
            self.status = VerificationStatus.UNVERIFIED
            self.hallucination_risk = HallucinationRisk.MEDIUM
            self.needs_sme_review = True
            self.sme_review_reason = "Insufficient evidence found"
        else:
            self.status = VerificationStatus.UNVERIFIED
            self.hallucination_risk = HallucinationRisk.HIGH
            self.needs_sme_review = True
            self.sme_review_reason = "Very low confidence - potential hallucination"


class SectionVerificationResult(BaseModel):
    """Verification result for a BRD section."""

    section_name: str
    claims: list[Claim] = Field(default_factory=list)
    overall_confidence: float = 0.0
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    hallucination_risk: HallucinationRisk = HallucinationRisk.MEDIUM

    # Aggregated stats
    total_claims: int = 0
    verified_claims: int = 0
    unverified_claims: int = 0
    contradicted_claims: int = 0
    needs_sme_review: int = 0

    # Feedback
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    def calculate_stats(self) -> None:
        """Calculate aggregated statistics from claims."""
        self.total_claims = len(self.claims)
        self.verified_claims = sum(
            1 for c in self.claims if c.status == VerificationStatus.VERIFIED
        )
        self.unverified_claims = sum(
            1 for c in self.claims if c.status in [
                VerificationStatus.UNVERIFIED,
                VerificationStatus.PARTIALLY_VERIFIED
            ]
        )
        self.contradicted_claims = sum(
            1 for c in self.claims if c.status == VerificationStatus.CONTRADICTED
        )
        self.needs_sme_review = sum(1 for c in self.claims if c.needs_sme_review)

        # Calculate overall confidence
        if self.claims:
            self.overall_confidence = sum(c.confidence_score for c in self.claims) / len(self.claims)

        # Determine overall status
        if self.contradicted_claims > 0:
            self.verification_status = VerificationStatus.CONTRADICTED
            self.hallucination_risk = HallucinationRisk.CRITICAL
        elif self.verified_claims == self.total_claims:
            self.verification_status = VerificationStatus.VERIFIED
            self.hallucination_risk = HallucinationRisk.NONE
        elif self.verified_claims > 0:
            self.verification_status = VerificationStatus.PARTIALLY_VERIFIED
            self.hallucination_risk = HallucinationRisk.LOW if self.overall_confidence >= 0.6 else HallucinationRisk.MEDIUM
        else:
            self.verification_status = VerificationStatus.UNVERIFIED
            self.hallucination_risk = HallucinationRisk.HIGH


class EvidenceBundle(BaseModel):
    """Complete evidence bundle for a BRD verification."""

    brd_id: str
    brd_title: str
    created_at: datetime = Field(default_factory=datetime.now)

    # Section results
    sections: list[SectionVerificationResult] = Field(default_factory=list)

    # Overall metrics
    overall_confidence: float = 0.0
    overall_status: VerificationStatus = VerificationStatus.UNVERIFIED
    hallucination_risk: HallucinationRisk = HallucinationRisk.MEDIUM

    # Aggregated stats
    total_claims: int = 0
    verified_claims: int = 0
    claims_needing_sme: int = 0

    # Evidence sources used
    evidence_sources: list[str] = Field(default_factory=list)  # neo4j, filesystem, etc.
    queries_executed: int = 0
    files_analyzed: int = 0

    # For iteration control
    iteration: int = 1
    is_approved: bool = False

    # Feedback for generator
    regeneration_feedback: Optional[str] = None
    sections_to_regenerate: list[str] = Field(default_factory=list)

    def calculate_overall_metrics(self) -> None:
        """Calculate overall metrics from section results."""
        if not self.sections:
            return

        # Aggregate from sections
        self.total_claims = sum(s.total_claims for s in self.sections)
        self.verified_claims = sum(s.verified_claims for s in self.sections)
        self.claims_needing_sme = sum(s.needs_sme_review for s in self.sections)

        # Overall confidence
        if self.sections:
            self.overall_confidence = sum(
                s.overall_confidence for s in self.sections
            ) / len(self.sections)

        # Overall status
        if all(s.verification_status == VerificationStatus.VERIFIED for s in self.sections):
            self.overall_status = VerificationStatus.VERIFIED
            self.hallucination_risk = HallucinationRisk.NONE
            self.is_approved = True
        elif any(s.verification_status == VerificationStatus.CONTRADICTED for s in self.sections):
            self.overall_status = VerificationStatus.CONTRADICTED
            self.hallucination_risk = HallucinationRisk.CRITICAL
        elif self.overall_confidence >= 0.7:
            self.overall_status = VerificationStatus.PARTIALLY_VERIFIED
            self.hallucination_risk = HallucinationRisk.LOW
            self.is_approved = True  # Good enough
        else:
            self.overall_status = VerificationStatus.UNVERIFIED
            self.hallucination_risk = HallucinationRisk.HIGH if self.overall_confidence < 0.3 else HallucinationRisk.MEDIUM

    def get_regeneration_feedback(self) -> str:
        """Generate feedback for BRD regeneration."""
        feedback_parts = []

        for section in self.sections:
            if section.verification_status in [
                VerificationStatus.UNVERIFIED,
                VerificationStatus.CONTRADICTED
            ]:
                self.sections_to_regenerate.append(section.section_name)

                feedback_parts.append(f"\n## Section: {section.section_name}")
                feedback_parts.append(f"Status: {section.verification_status.value}")
                feedback_parts.append(f"Confidence: {section.overall_confidence:.2f}")

                # Add specific claim issues
                for claim in section.claims:
                    if claim.status != VerificationStatus.VERIFIED:
                        feedback_parts.append(f"\n### Claim: {claim.text[:100]}...")
                        feedback_parts.append(f"Issue: {claim.feedback or 'Insufficient evidence'}")
                        if claim.suggested_correction:
                            feedback_parts.append(f"Suggestion: {claim.suggested_correction}")

                if section.issues:
                    feedback_parts.append("\n### Issues:")
                    for issue in section.issues:
                        feedback_parts.append(f"- {issue}")

                if section.suggestions:
                    feedback_parts.append("\n### Suggestions:")
                    for suggestion in section.suggestions:
                        feedback_parts.append(f"- {suggestion}")

        self.regeneration_feedback = "\n".join(feedback_parts)
        return self.regeneration_feedback

    def to_evidence_trail(self, include_details: bool = True) -> str:
        """
        Generate human-readable evidence trail.

        Args:
            include_details: If True, include full evidence details.
                           If False, just show summary (default hidden mode).
        """
        lines = [
            "=" * 60,
            "EVIDENCE TRAIL",
            "=" * 60,
            "",
            f"BRD: {self.brd_title}",
            f"Generated: {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Iteration: {self.iteration}",
            "",
            "SUMMARY",
            "-" * 40,
            f"Overall Confidence: {self.overall_confidence:.2f} ({self._confidence_label()})",
            f"Verification Status: {self.overall_status.value}",
            f"Hallucination Risk: {self.hallucination_risk.value}",
            "",
            f"Total Claims: {self.total_claims}",
            f"Verified Claims: {self.verified_claims} ({self._percentage(self.verified_claims, self.total_claims)}%)",
            f"Claims Needing SME Review: {self.claims_needing_sme}",
            "",
            f"Evidence Sources: {', '.join(self.evidence_sources)}",
            f"Queries Executed: {self.queries_executed}",
            f"Files Analyzed: {self.files_analyzed}",
            "",
        ]

        if include_details:
            for section in self.sections:
                lines.extend(self._format_section_evidence(section))

        lines.append("=" * 60)
        return "\n".join(lines)

    def _format_section_evidence(self, section: SectionVerificationResult) -> list[str]:
        """Format evidence for a single section in a tree-like structure."""
        lines = [
            f"\nSECTION: {section.section_name}",
            "-" * 40,
            f"Confidence: {section.overall_confidence:.2f}",
            f"Status: {section.verification_status.value}",
            "",
        ]

        for idx, claim in enumerate(section.claims, 1):
            # Format claim header
            lines.append(f"BRD CLAIM #{idx}: \"{claim.text}\"")
            lines.append("EVIDENCE TRAIL:")

            # Group evidence by category
            primary = [e for e in claim.evidence if e.category == "primary"]
            secondary = [e for e in claim.evidence if e.category == "secondary"]
            supporting = [e for e in claim.evidence if e.category == "supporting"]

            # Primary Evidence (Code)
            if primary:
                lines.append("├─ Primary Evidence (Code)")
                for i, ev in enumerate(primary):
                    prefix = "│ ├─" if i < len(primary) - 1 else "│ └─"
                    lines.append(f"{prefix} {ev.description}")

                    # Code references
                    for ref in ev.code_references:
                        lines.append(f"│ │ └─ File: {ref.file_path}:{ref.start_line}-{ref.end_line} [{ref.loc} LOC]")

                    # Call graph
                    if ev.call_graph:
                        call_chain = " → ".join([cg.source_entity for cg in ev.call_graph[:6]])
                        if ev.call_graph:
                            call_chain += f" → {ev.call_graph[-1].target_entity}"
                        lines.append(f"│ │ └─ Call Graph shows: {call_chain}")
                        lines.append(f"│ │   └─ {ev.analysis_method or 'Extracted from AST analysis'}")

                    # Method phases
                    if ev.method_phases:
                        phases = " → ".join(ev.method_phases)
                        lines.append(f"│ │ └─ Phases: {phases}")

                    # Test coverage
                    if ev.test_cases:
                        lines.append(f"│ └─ Test coverage validates each step")
                        for tc in ev.test_cases[:3]:
                            lines.append(f"│   └─ {tc}")
                lines.append("│")

            # Secondary Evidence (Configuration)
            if secondary:
                lines.append("├─ Secondary Evidence (Configuration)")
                for i, ev in enumerate(secondary):
                    prefix = "│ ├─" if i < len(secondary) - 1 else "│ └─"
                    lines.append(f"{prefix} {ev.description}")

                    # Config values
                    if ev.config_values:
                        for key, val in list(ev.config_values.items())[:3]:
                            lines.append(f"│ │ └─ {key}: {val}")

                    # Code references for config
                    for ref in ev.code_references:
                        lines.append(f"│   └─ {ref.file_path}")
                lines.append("│")

            # Confidence and Hallucination Check
            conf_label = "HIGH" if claim.confidence_score >= 0.8 else "MEDIUM" if claim.confidence_score >= 0.5 else "LOW"
            lines.append(f"└─ CONFIDENCE SCORE: {claim.confidence_score:.2f} ({conf_label})")

            # Rationale
            if claim.evidence:
                rationale_parts = []
                if primary:
                    rationale_parts.append("Code structure is clear")
                if secondary:
                    rationale_parts.append("Config values match code")
                if supporting:
                    rationale_parts.append("Tests confirm behavior")
                lines.append(f"   Rationale: {'. '.join(rationale_parts) or 'Based on available evidence'}.")

            # Hallucination check
            lines.append("")
            lines.append("   HALLUCINATION CHECK:")

            # Collect all hallucination flags from evidence
            all_flags = []
            for ev in claim.evidence:
                all_flags.extend(ev.hallucination_flags)

            if not all_flags and claim.confidence_score >= 0.7:
                lines.append("   ├─ ✓ Evidence supports claim accurately")
                lines.append("   ├─ ✓ No contradicting evidence found")
            elif claim.hallucination_risk == HallucinationRisk.NONE:
                lines.append("   ├─ ✓ All claims verified against code")
            elif claim.hallucination_risk == HallucinationRisk.LOW:
                lines.append("   ├─ ✓ Most claims verified")
                if all_flags:
                    for flag in all_flags[:2]:
                        lines.append(f"   ├─ ⚠ {flag}")
            else:
                lines.append("   ├─ ✗ Some claims lack sufficient evidence")
                for flag in all_flags[:3]:
                    lines.append(f"   │ └─ {flag}")

            # Calculate total risk
            total_risk = sum(e.hallucination_risk_pct for e in claim.evidence) / max(len(claim.evidence), 1)
            lines.append(f"   └─ Risk: {total_risk:.0f}% (semantic interpretation)")
            lines.append(f"   └─ FINAL CONFIDENCE: {claim.confidence_score:.2f}")

            if claim.needs_sme_review:
                lines.append("")
                lines.append(f"   [!] SME REVIEW REQUIRED: {claim.sme_review_reason}")

            lines.append("")
            lines.append("")

        return lines

    def _confidence_label(self) -> str:
        """Get human-readable confidence label."""
        if self.overall_confidence >= 0.8:
            return "HIGH"
        elif self.overall_confidence >= 0.5:
            return "MEDIUM"
        elif self.overall_confidence >= 0.3:
            return "LOW"
        else:
            return "INSUFFICIENT"

    def _percentage(self, part: int, total: int) -> int:
        """Calculate percentage."""
        return int((part / total * 100) if total > 0 else 0)


class VerificationConfig(BaseModel):
    """Configuration for verification process."""

    # Thresholds
    min_confidence_for_approval: float = 0.7
    min_evidence_per_claim: int = 1
    max_iterations: int = 3

    # What to verify
    verify_components: bool = True
    verify_workflows: bool = True
    verify_dependencies: bool = True
    verify_technical_claims: bool = True
    verify_file_references: bool = True

    # Evidence sources
    use_neo4j: bool = True
    use_filesystem: bool = True
    use_similar_features: bool = True

    # Output
    show_evidence_by_default: bool = False
    include_code_snippets: bool = True
    max_snippet_lines: int = 10
