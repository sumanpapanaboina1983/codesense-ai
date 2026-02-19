"""Business logic models for extracted business rules.

This module defines models for business rules extracted from code AST,
including validation constraints, guard clauses, conditional logic,
and test assertions.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class BusinessRuleType(str, Enum):
    """Types of business rules extracted from code."""

    VALIDATION_CONSTRAINT = "validation_constraint"
    GUARD_CLAUSE = "guard_clause"
    CONDITIONAL_LOGIC = "conditional_logic"
    ERROR_MESSAGE = "error_message"
    TEST_ASSERTION = "test_assertion"


class RuleSeverity(str, Enum):
    """Severity levels for business rules."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ConditionOperator(str, Enum):
    """Operators used in rule conditions."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    LESS_THAN_OR_EQUALS = "less_than_or_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    MATCHES = "matches"
    NOT_NULL = "not_null"
    IS_NULL = "is_null"
    IS_EMPTY = "is_empty"
    NOT_EMPTY = "not_empty"
    IN_RANGE = "in_range"
    CUSTOM = "custom"


class CodeLocation(BaseModel):
    """Location of code in a source file."""

    file_path: str
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0

    def to_string(self) -> str:
        """Format as file:line reference."""
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


class ExtractedBusinessRule(BaseModel):
    """A business rule extracted from code.

    This is the base model for all extracted rules, providing
    common fields for rule identification and traceability.
    """

    id: str = Field(description="Unique identifier for this rule")
    entity_id: str = Field(description="Entity ID matching Neo4j node")
    rule_type: BusinessRuleType = Field(description="Type of business rule")
    rule_text: str = Field(description="Human-readable rule description")
    condition: str = Field(description="The condition being enforced")
    consequence: Optional[str] = Field(
        default=None,
        description="What happens if rule is violated"
    )
    severity: RuleSeverity = Field(
        default=RuleSeverity.ERROR,
        description="Rule severity"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        default=0.8,
        description="Confidence score for extraction"
    )

    # Location information
    location: CodeLocation = Field(description="Code location of the rule")
    language: str = Field(description="Programming language")

    # Context information
    containing_class: Optional[str] = Field(
        default=None,
        description="Class containing this rule"
    )
    containing_method: Optional[str] = Field(
        default=None,
        description="Method containing this rule"
    )

    # Metadata
    extracted_at: datetime = Field(default_factory=datetime.now)
    source: str = Field(
        default="ast_analysis",
        description="How the rule was extracted"
    )

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {
            "entityId": self.entity_id,
            "ruleType": self.rule_type.value,
            "ruleText": self.rule_text,
            "condition": self.condition,
            "consequence": self.consequence,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "filePath": self.location.file_path,
            "startLine": self.location.start_line,
            "endLine": self.location.end_line,
            "language": self.language,
            "containingClass": self.containing_class,
            "containingMethod": self.containing_method,
            "extractedAt": self.extracted_at.isoformat(),
        }


class ValidationConstraint(BaseModel):
    """A validation constraint extracted from annotations.

    Examples:
    - @NotNull on a field
    - @Min(100) on a parameter
    - Pydantic Field(ge=0)
    """

    id: str
    entity_id: str
    constraint_name: str = Field(
        description="Constraint name (NotNull, Min, Max, etc.)"
    )
    annotation_text: str = Field(description="Full annotation text")
    target_name: str = Field(description="Field/parameter being constrained")
    target_type: str = Field(description="field, parameter, or class")
    constraint_parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Constraint parameters (min, max, message, etc.)"
    )
    message_template: Optional[str] = Field(
        default=None,
        description="Error message template"
    )
    groups: list[str] = Field(
        default_factory=list,
        description="Validation groups"
    )
    framework: str = Field(
        default="unknown",
        description="Validation framework (javax.validation, Pydantic, etc.)"
    )
    rule_text: str = Field(description="Human-readable rule text")
    confidence: float = Field(ge=0.0, le=1.0, default=0.95)

    # Location
    location: CodeLocation

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {
            "entityId": self.entity_id,
            "constraintName": self.constraint_name,
            "annotationText": self.annotation_text,
            "targetName": self.target_name,
            "targetType": self.target_type,
            "constraintParameters": str(self.constraint_parameters),
            "messageTemplate": self.message_template,
            "framework": self.framework,
            "ruleText": self.rule_text,
            "confidence": self.confidence,
            "filePath": self.location.file_path,
            "startLine": self.location.start_line,
            "endLine": self.location.end_line,
        }


class GuardClause(BaseModel):
    """A guard clause extracted from code.

    Examples:
    - if (x == null) throw new IllegalArgumentException
    - Preconditions.checkNotNull(x, "x must not be null")
    """

    id: str
    entity_id: str
    condition: str = Field(description="The guard condition")
    operator: ConditionOperator = Field(description="Condition operator")
    left_operand: str = Field(description="Variable being checked")
    right_operand: Optional[str] = Field(
        default=None,
        description="Value being compared to"
    )
    guard_type: str = Field(
        description="null_check, bounds_check, state_check, type_check"
    )
    exception_type: Optional[str] = Field(
        default=None,
        description="Exception thrown on violation"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message"
    )
    is_precondition: bool = Field(
        default=True,
        description="Whether this is a method precondition"
    )
    guarded_method: str = Field(description="Method being guarded")
    rule_text: str = Field(description="Human-readable rule text")
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)

    # Location
    location: CodeLocation

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {
            "entityId": self.entity_id,
            "condition": self.condition,
            "operator": self.operator.value,
            "leftOperand": self.left_operand,
            "rightOperand": self.right_operand,
            "guardType": self.guard_type,
            "exceptionType": self.exception_type,
            "errorMessage": self.error_message,
            "isPrecondition": self.is_precondition,
            "guardedMethod": self.guarded_method,
            "ruleText": self.rule_text,
            "confidence": self.confidence,
            "filePath": self.location.file_path,
            "startLine": self.location.start_line,
            "endLine": self.location.end_line,
        }


class ConditionalBusinessLogic(BaseModel):
    """Conditional business logic extracted from if/else.

    Examples:
    - if (amount > 50000) { applyPremiumDiscount() }
    - if (status == "ACTIVE") { processOrder() }
    """

    id: str
    entity_id: str
    condition: str = Field(description="The business condition")
    operator: ConditionOperator = Field(description="Condition operator")
    variable: str = Field(description="Variable being checked")
    threshold: Optional[str] = Field(
        default=None,
        description="Threshold value for comparisons"
    )
    then_branch: str = Field(description="Then branch summary")
    else_branch: Optional[str] = Field(
        default=None,
        description="Else branch summary"
    )
    business_meaning: Optional[str] = Field(
        default=None,
        description="Inferred business meaning"
    )
    business_keywords: list[str] = Field(
        default_factory=list,
        description="Business keywords found"
    )
    rule_text: str = Field(description="Human-readable rule text")
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)

    # Location
    location: CodeLocation

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {
            "entityId": self.entity_id,
            "condition": self.condition,
            "operator": self.operator.value,
            "variable": self.variable,
            "threshold": self.threshold,
            "thenBranch": self.then_branch,
            "elseBranch": self.else_branch,
            "businessMeaning": self.business_meaning,
            "businessKeywords": self.business_keywords,
            "ruleText": self.rule_text,
            "confidence": self.confidence,
            "filePath": self.location.file_path,
            "startLine": self.location.start_line,
            "endLine": self.location.end_line,
        }


class TestAssertion(BaseModel):
    """A test assertion that encodes expected behavior.

    Examples:
    - assertEquals(100, order.getMinAmount())
    - assertThrows(ValidationException.class, () -> service.process(invalid))
    """

    id: str
    entity_id: str
    assertion_type: str = Field(
        description="assertEquals, assertTrue, assertThrows, etc."
    )
    expected_value: Optional[str] = Field(
        default=None,
        description="Expected value in assertion"
    )
    actual_expression: str = Field(description="Expression being tested")
    test_method_name: str = Field(description="Test method name")
    test_class_name: str = Field(description="Test class name")
    tested_entity: Optional[str] = Field(
        default=None,
        description="Entity being tested"
    )
    test_framework: str = Field(
        default="unknown",
        description="Test framework (JUnit, pytest, Jest, etc.)"
    )
    inferred_rule: str = Field(
        description="Business rule inferred from test"
    )
    rule_text: str = Field(description="Human-readable rule text")
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)

    # Location
    location: CodeLocation

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {
            "entityId": self.entity_id,
            "assertionType": self.assertion_type,
            "expectedValue": self.expected_value,
            "actualExpression": self.actual_expression,
            "testMethodName": self.test_method_name,
            "testClassName": self.test_class_name,
            "testedEntity": self.tested_entity,
            "testFramework": self.test_framework,
            "inferredRule": self.inferred_rule,
            "ruleText": self.rule_text,
            "confidence": self.confidence,
            "filePath": self.location.file_path,
            "startLine": self.location.start_line,
            "endLine": self.location.end_line,
        }


class BusinessLogicContext(BaseModel):
    """Aggregated business logic context for BRD generation.

    This contains all extracted business rules from the codebase,
    organized by type for easy querying by BRD agents.
    """

    # Extracted rules by type
    business_rules: list[ExtractedBusinessRule] = Field(
        default_factory=list,
        description="Generic business rules"
    )
    validation_constraints: list[ValidationConstraint] = Field(
        default_factory=list,
        description="Validation constraints from annotations"
    )
    guard_clauses: list[GuardClause] = Field(
        default_factory=list,
        description="Guard clauses from code"
    )
    conditional_logic: list[ConditionalBusinessLogic] = Field(
        default_factory=list,
        description="Conditional business logic"
    )
    test_assertions: list[TestAssertion] = Field(
        default_factory=list,
        description="Test assertions encoding behavior"
    )

    # Metadata
    total_rules: int = Field(default=0, description="Total rules extracted")
    extraction_timestamp: datetime = Field(default_factory=datetime.now)
    source_files_analyzed: int = Field(
        default=0,
        description="Number of source files analyzed"
    )
    languages_detected: list[str] = Field(
        default_factory=list,
        description="Languages found in codebase"
    )

    def calculate_totals(self) -> None:
        """Calculate total rules count."""
        self.total_rules = (
            len(self.business_rules) +
            len(self.validation_constraints) +
            len(self.guard_clauses) +
            len(self.conditional_logic) +
            len(self.test_assertions)
        )

    def get_rules_for_entity(self, entity_name: str) -> list[dict[str, Any]]:
        """Get all rules related to an entity.

        Args:
            entity_name: Name of class, method, or field

        Returns:
            List of rules mentioning this entity
        """
        results = []
        entity_lower = entity_name.lower()

        for rule in self.business_rules:
            if (entity_lower in rule.rule_text.lower() or
                entity_lower in (rule.containing_class or "").lower() or
                entity_lower in (rule.containing_method or "").lower()):
                results.append({
                    "type": "business_rule",
                    "rule_text": rule.rule_text,
                    "confidence": rule.confidence,
                    "location": rule.location.to_string(),
                })

        for constraint in self.validation_constraints:
            if (entity_lower in constraint.target_name.lower() or
                entity_lower in constraint.rule_text.lower()):
                results.append({
                    "type": "validation_constraint",
                    "rule_text": constraint.rule_text,
                    "confidence": constraint.confidence,
                    "constraint": constraint.constraint_name,
                    "location": constraint.location.to_string(),
                })

        for guard in self.guard_clauses:
            if (entity_lower in guard.guarded_method.lower() or
                entity_lower in guard.rule_text.lower()):
                results.append({
                    "type": "guard_clause",
                    "rule_text": guard.rule_text,
                    "confidence": guard.confidence,
                    "location": guard.location.to_string(),
                })

        for cond in self.conditional_logic:
            if (entity_lower in cond.variable.lower() or
                entity_lower in cond.rule_text.lower()):
                results.append({
                    "type": "conditional_logic",
                    "rule_text": cond.rule_text,
                    "confidence": cond.confidence,
                    "condition": cond.condition,
                    "location": cond.location.to_string(),
                })

        for assertion in self.test_assertions:
            if (entity_lower in (assertion.tested_entity or "").lower() or
                entity_lower in assertion.rule_text.lower()):
                results.append({
                    "type": "test_assertion",
                    "rule_text": assertion.rule_text,
                    "confidence": assertion.confidence,
                    "test_method": assertion.test_method_name,
                    "location": assertion.location.to_string(),
                })

        return results

    def search_rules(
        self,
        keyword: str,
        min_confidence: float = 0.5
    ) -> list[dict[str, Any]]:
        """Search rules by keyword.

        Args:
            keyword: Keyword to search for
            min_confidence: Minimum confidence threshold

        Returns:
            List of matching rules
        """
        results = []
        keyword_lower = keyword.lower()

        # Search all rule types
        for constraint in self.validation_constraints:
            if (keyword_lower in constraint.rule_text.lower() and
                constraint.confidence >= min_confidence):
                results.append({
                    "type": "validation_constraint",
                    "rule_text": constraint.rule_text,
                    "confidence": constraint.confidence,
                    "target": constraint.target_name,
                    "constraint": constraint.constraint_name,
                })

        for guard in self.guard_clauses:
            if (keyword_lower in guard.rule_text.lower() and
                guard.confidence >= min_confidence):
                results.append({
                    "type": "guard_clause",
                    "rule_text": guard.rule_text,
                    "confidence": guard.confidence,
                    "method": guard.guarded_method,
                })

        for cond in self.conditional_logic:
            if (keyword_lower in cond.rule_text.lower() and
                cond.confidence >= min_confidence):
                results.append({
                    "type": "conditional_logic",
                    "rule_text": cond.rule_text,
                    "confidence": cond.confidence,
                    "condition": cond.condition,
                })

        for assertion in self.test_assertions:
            if (keyword_lower in assertion.rule_text.lower() and
                assertion.confidence >= min_confidence):
                results.append({
                    "type": "test_assertion",
                    "rule_text": assertion.rule_text,
                    "confidence": assertion.confidence,
                    "test": f"{assertion.test_class_name}.{assertion.test_method_name}",
                })

        # Sort by confidence
        results.sort(key=lambda x: x["confidence"], reverse=True)

        return results

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of extracted business logic."""
        self.calculate_totals()

        return {
            "total_rules": self.total_rules,
            "by_type": {
                "validation_constraints": len(self.validation_constraints),
                "guard_clauses": len(self.guard_clauses),
                "conditional_logic": len(self.conditional_logic),
                "test_assertions": len(self.test_assertions),
                "other_rules": len(self.business_rules),
            },
            "source_files_analyzed": self.source_files_analyzed,
            "languages": self.languages_detected,
            "extraction_timestamp": self.extraction_timestamp.isoformat(),
        }


# Evidence weights for business rule types
BUSINESS_RULE_EVIDENCE_WEIGHTS = {
    "business_rule": 1.0,
    "validation_constraint": 0.95,
    "guard_clause": 0.90,
    "test_assertion": 0.85,
    "conditional_logic": 0.80,
}
