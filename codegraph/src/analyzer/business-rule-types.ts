// src/analyzer/business-rule-types.ts
// Business Rule Extraction Types - Structural extraction of business rules from code AST

import { AstNode, AnnotationInfo } from './types.js';

// =============================================================================
// Business Rule Node Types
// =============================================================================

/**
 * Rule type categories for business rules extracted from code.
 */
export type BusinessRuleType =
    | 'validation_constraint'    // @NotNull, @Min, Pydantic Field(ge=0)
    | 'guard_clause'             // if (x == null) throw, if (!valid) return error
    | 'conditional_logic'        // if (amount > 50000), if (status == 'ACTIVE')
    | 'error_message'            // Exception messages encoding business rules
    | 'test_assertion';          // assertEquals, assertThrows encoding expected behavior

/**
 * Severity levels for business rules.
 */
export type RuleSeverity = 'error' | 'warning' | 'info';

/**
 * Condition operators for rule conditions.
 */
export type ConditionOperator =
    | 'equals'
    | 'not_equals'
    | 'greater_than'
    | 'less_than'
    | 'greater_than_or_equals'
    | 'less_than_or_equals'
    | 'contains'
    | 'not_contains'
    | 'matches'
    | 'not_null'
    | 'is_null'
    | 'is_empty'
    | 'not_empty'
    | 'in_range'
    | 'custom';

/**
 * Base interface for all business rule nodes.
 */
export interface BusinessRuleNode extends AstNode {
    kind: 'BusinessRule';
    properties: {
        /** Type of business rule */
        ruleType: BusinessRuleType;
        /** Human-readable rule text/description */
        ruleText: string;
        /** The condition being checked (e.g., "amount > 0") */
        condition: string;
        /** Consequence if rule is violated */
        consequence?: string;
        /** Target field/parameter this rule applies to */
        targetName?: string;
        /** Target type (field, parameter, return value) */
        targetType?: 'field' | 'parameter' | 'return' | 'method' | 'class';
        /** Rule severity */
        severity: RuleSeverity;
        /** Error message if rule is violated */
        errorMessage?: string;
        /** Confidence score for extraction (0-1) */
        confidence: number;
        /** Method/class this rule is defined in */
        containingMethod?: string;
        /** Class containing this rule */
        containingClass?: string;
    };
}

/**
 * Validation constraint node - extracted from annotations like @NotNull, @Min, etc.
 */
export interface ValidationConstraintNode extends AstNode {
    kind: 'ValidationConstraint';
    properties: {
        /** Constraint name (e.g., NotNull, Min, Max, Size, Pattern) */
        constraintName: string;
        /** Full annotation text */
        annotationText: string;
        /** Target field/parameter name */
        targetName: string;
        /** Target type */
        targetType: 'field' | 'parameter';
        /** Constraint parameters (e.g., {min: 1, max: 100}) */
        constraintParameters: Record<string, string | number | boolean>;
        /** Error message template */
        messageTemplate?: string;
        /** Validation groups if specified */
        groups?: string[];
        /** Framework/library (javax.validation, jakarta.validation, Pydantic, etc.) */
        framework: string;
        /** Human-readable rule text */
        ruleText: string;
        /** Confidence score */
        confidence: number;
    };
}

/**
 * Guard clause node - extracted from precondition checks like if (x == null) throw.
 */
export interface GuardClauseNode extends AstNode {
    kind: 'GuardClause';
    properties: {
        /** The condition being checked */
        condition: string;
        /** Operator used in condition */
        operator: ConditionOperator;
        /** Left operand (usually field/parameter name) */
        leftOperand: string;
        /** Right operand (value being compared to) */
        rightOperand?: string;
        /** Type of guard (null check, bounds check, state check) */
        guardType: 'null_check' | 'bounds_check' | 'state_check' | 'type_check' | 'custom';
        /** Exception type thrown */
        exceptionType?: string;
        /** Error message */
        errorMessage?: string;
        /** Whether this is a precondition (at method start) */
        isPrecondition: boolean;
        /** Method being guarded */
        guardedMethod: string;
        /** Human-readable rule text */
        ruleText: string;
        /** Confidence score */
        confidence: number;
    };
}

/**
 * Conditional business logic node - extracted from if/else with business conditions.
 */
export interface ConditionalBusinessLogicNode extends AstNode {
    kind: 'ConditionalBusinessLogic';
    properties: {
        /** The business condition (e.g., "amount > 50000") */
        condition: string;
        /** Operator used */
        operator: ConditionOperator;
        /** Variable/field being checked */
        variable: string;
        /** Threshold/comparison value */
        threshold?: string | number;
        /** Then branch summary */
        thenBranch: string;
        /** Else branch summary (if exists) */
        elseBranch?: string;
        /** Business meaning (inferred) */
        businessMeaning?: string;
        /** Whether this appears to be a business rule vs technical logic */
        isBusinessRule: boolean;
        /** Keywords suggesting business logic */
        businessKeywords: string[];
        /** Human-readable rule text */
        ruleText: string;
        /** Confidence score */
        confidence: number;
    };
}

/**
 * Test assertion node - derived rules from test cases.
 */
export interface TestAssertionNode extends AstNode {
    kind: 'TestAssertion';
    properties: {
        /** Assertion type (assertEquals, assertTrue, assertThrows, etc.) */
        assertionType: string;
        /** Expected value */
        expectedValue?: string;
        /** Actual expression being tested */
        actualExpression: string;
        /** Test method name */
        testMethodName: string;
        /** Test class name */
        testClassName: string;
        /** Method/class being tested (if determinable) */
        testedEntity?: string;
        /** Framework (JUnit, pytest, Jest, etc.) */
        testFramework: string;
        /** Inferred business rule from test */
        inferredRule: string;
        /** Human-readable rule text */
        ruleText: string;
        /** Confidence score */
        confidence: number;
    };
}

// =============================================================================
// Detection Result Types
// =============================================================================

/**
 * Result from business rule detection for a single file.
 */
export interface BusinessRuleDetectionResult {
    /** File path */
    filePath: string;
    /** All detected business rule nodes */
    rules: BusinessRuleNode[];
    /** Validation constraint nodes */
    validationConstraints: ValidationConstraintNode[];
    /** Guard clause nodes */
    guardClauses: GuardClauseNode[];
    /** Conditional business logic nodes */
    conditionalLogic: ConditionalBusinessLogicNode[];
    /** Test assertion nodes */
    testAssertions: TestAssertionNode[];
    /** Total rules detected */
    totalRulesDetected: number;
    /** Detection metadata */
    metadata: {
        language: string;
        parserVersion: string;
        detectionTimestamp: string;
    };
}

// =============================================================================
// Language-Specific Detection Patterns
// =============================================================================

/**
 * Java validation annotation patterns.
 */
export const JAVA_VALIDATION_ANNOTATIONS = [
    // Jakarta/Javax Validation
    'NotNull', 'NotEmpty', 'NotBlank',
    'Min', 'Max', 'Size', 'Range',
    'Pattern', 'Email', 'URL',
    'Positive', 'PositiveOrZero', 'Negative', 'NegativeOrZero',
    'Past', 'PastOrPresent', 'Future', 'FutureOrPresent',
    'Valid', 'Validated',
    // Custom validation
    'AssertTrue', 'AssertFalse',
    // Lombok
    'NonNull',
] as const;

/**
 * Java guard clause patterns (Guava, Objects, etc.).
 */
export const JAVA_GUARD_PATTERNS = [
    // Guava Preconditions
    'Preconditions.checkNotNull',
    'Preconditions.checkArgument',
    'Preconditions.checkState',
    'Preconditions.checkElementIndex',
    // Java Objects
    'Objects.requireNonNull',
    'Objects.requireNonNullElse',
    // Apache Commons
    'Validate.notNull',
    'Validate.notEmpty',
    'Validate.isTrue',
    // Spring Assert
    'Assert.notNull',
    'Assert.hasText',
    'Assert.isTrue',
    'Assert.state',
] as const;

/**
 * Python validation patterns.
 */
export const PYTHON_VALIDATION_PATTERNS = [
    // Pydantic Field constraints
    'Field(gt=', 'Field(ge=', 'Field(lt=', 'Field(le=',
    'Field(min_length=', 'Field(max_length=',
    'Field(regex=', 'Field(pattern=',
    // Pydantic validators
    '@validator', '@field_validator', '@model_validator',
    // Attrs
    '@attrs.validators',
    // Cerberus
    'schema = {',
] as const;

/**
 * TypeScript/JavaScript validation patterns.
 */
export const TYPESCRIPT_VALIDATION_PATTERNS = [
    // class-validator
    '@IsNotEmpty', '@IsEmail', '@IsString', '@IsNumber',
    '@Min', '@Max', '@Length', '@Matches',
    '@IsOptional', '@IsArray', '@ValidateNested',
    // Zod
    'z.string()', 'z.number()', 'z.boolean()',
    '.min(', '.max(', '.positive()', '.negative()',
    '.email()', '.url()', '.regex(',
    // Yup
    'yup.string()', 'yup.number()', 'yup.boolean()',
    '.required()', '.min(', '.max(',
    // io-ts
    't.string', 't.number', 't.boolean',
] as const;

/**
 * Go validation patterns.
 */
export const GO_VALIDATION_PATTERNS = [
    // Standard error returns
    'errors.New(', 'fmt.Errorf(',
    // go-playground/validator
    'validate:"required"', 'validate:"min=', 'validate:"max=',
    'validate:"email"', 'validate:"url"',
] as const;

/**
 * C# validation patterns.
 */
export const CSHARP_VALIDATION_PATTERNS = [
    // Data Annotations
    '[Required]', '[StringLength', '[Range',
    '[RegularExpression', '[EmailAddress]', '[Url]',
    '[Compare', '[MinLength', '[MaxLength',
    // FluentValidation
    'RuleFor(', '.NotNull()', '.NotEmpty()',
    '.MinimumLength(', '.MaximumLength(', '.Matches(',
] as const;

// =============================================================================
// JSP/Spring Form Validation Patterns
// =============================================================================

/**
 * JSP form validation patterns.
 */
export const JSP_VALIDATION_PATTERNS = {
    /** HTML5 validation attributes */
    HTML5_REQUIRED: /required(?:="[^"]*")?/gi,
    HTML5_PATTERN: /pattern="([^"]+)"/gi,
    HTML5_MIN: /min="([^"]+)"/gi,
    HTML5_MAX: /max="([^"]+)"/gi,
    HTML5_MINLENGTH: /minlength="(\d+)"/gi,
    HTML5_MAXLENGTH: /maxlength="(\d+)"/gi,
    HTML5_TYPE_EMAIL: /type="email"/gi,
    HTML5_TYPE_NUMBER: /type="number"/gi,
    HTML5_TYPE_DATE: /type="date"/gi,

    /** Spring form tags with validation */
    SPRING_FORM_ERRORS: /<form:errors\s+path="([^"]+)"[^>]*>/gi,
    SPRING_BIND: /<spring:bind\s+path="([^"]+)"[^>]*>/gi,
    SPRING_HAS_ERRORS: /<c:if\s+test="\${[^}]*errors[^}]*}"[^>]*>/gi,

    /** Form field with validation classes */
    VALIDATION_CLASS: /class="[^"]*(?:required|error|invalid|validate)[^"]*"/gi,

    /** JSTL conditional validation */
    JSTL_VALIDATION_IF: /<c:if\s+test="\${([^}]+)}"[^>]*>/gi,
    JSTL_WHEN: /<c:when\s+test="\${([^}]+)}"[^>]*>/gi,

    /** EL expressions with validation logic */
    EL_NOT_EMPTY: /\${not\s+empty\s+([^}]+)}/gi,
    EL_EMPTY: /\${empty\s+([^}]+)}/gi,
    EL_COMPARISON: /\${([^}]+)\s*(==|!=|>|<|>=|<=)\s*([^}]+)}/gi,
} as const;

/**
 * Spring form tag validation attributes.
 */
export const SPRING_FORM_VALIDATION_TAGS = [
    'form:errors',      // Display validation errors
    'form:input',       // Input with path binding
    'form:select',      // Select with path binding
    'form:checkbox',    // Checkbox with path binding
    'form:radiobutton', // Radio with path binding
    'form:password',    // Password with path binding
    'form:textarea',    // Textarea with path binding
] as const;

/**
 * JSP business rule source types.
 */
export type JSPRuleSource =
    | 'html5_validation'      // HTML5 required, pattern, min, max
    | 'spring_form_errors'    // <form:errors path="...">
    | 'spring_bind'           // <spring:bind path="...">
    | 'jstl_conditional'      // <c:if>, <c:when>, <c:choose>
    | 'el_expression'         // ${not empty x}, ${x > 0}
    | 'form_action';          // Form action with validation

// =============================================================================
// Spring WebFlow Business Rule Patterns
// =============================================================================

/**
 * WebFlow decision and transition patterns.
 */
export const WEBFLOW_RULE_PATTERNS = {
    /** Decision state conditions */
    DECISION_IF: /<if\s+test="([^"]+)"\s+then="([^"]+)"(?:\s+else="([^"]+)")?[^>]*>/gi,

    /** Transition guards/conditions */
    TRANSITION_ON: /<transition\s+on="([^"]+)"[^>]*to="([^"]+)"[^>]*>/gi,
    TRANSITION_CONDITION: /condition="([^"]+)"/gi,

    /** Evaluate expressions with validation */
    EVALUATE_EXPRESSION: /<evaluate\s+expression="([^"]+)"[^>]*>/gi,

    /** Action state evaluations */
    ACTION_RESULT: /result="([^"]+)"/gi,

    /** Security constraints */
    SECURED_ATTRIBUTES: /<secured\s+attributes="([^"]+)"[^>]*>/gi,

    /** Variable declarations with types */
    VAR_DECLARATION: /<var\s+name="([^"]+)"(?:\s+class="([^"]+)")?[^>]*>/gi,

    /** Set expressions */
    SET_EXPRESSION: /<set\s+name="([^"]+)"\s+value="([^"]+)"[^>]*>/gi,

    /** Validator references */
    VALIDATOR_REFERENCE: /validator="([^"]+)"/gi,

    /** Binding model */
    BINDER_BINDING: /<binding\s+property="([^"]+)"(?:\s+required="([^"]+)")?[^>]*>/gi,
} as const;

/**
 * WebFlow state types that can contain business rules.
 */
export const WEBFLOW_STATE_TYPES = [
    'view-state',
    'action-state',
    'decision-state',
    'subflow-state',
    'end-state',
] as const;

/**
 * WebFlow business rule source types.
 */
export type WebFlowRuleSource =
    | 'decision_state'        // <decision-state> with <if> conditions
    | 'transition_guard'      // <transition on="..." condition="...">
    | 'evaluate_expression'   // <evaluate expression="validator.validate(...)">
    | 'security_constraint'   // <secured attributes="ROLE_ADMIN">
    | 'binding_constraint'    // <binding property="..." required="true">
    | 'set_expression';       // <set name="..." value="...">

/**
 * WebFlow-specific business rule node.
 */
export interface WebFlowBusinessRuleNode extends AstNode {
    kind: 'BusinessRule';
    properties: {
        ruleType: BusinessRuleType;
        ruleText: string;
        condition: string;
        consequence?: string;
        targetName?: string;
        targetType?: 'state' | 'transition' | 'flow' | 'variable';
        severity: RuleSeverity;
        errorMessage?: string;
        confidence: number;
        /** WebFlow-specific: source of the rule */
        webflowSource: WebFlowRuleSource;
        /** WebFlow-specific: state ID if applicable */
        stateId?: string;
        /** WebFlow-specific: transition event if applicable */
        transitionEvent?: string;
        /** WebFlow-specific: flow ID */
        flowId?: string;
    };
}

/**
 * JSP-specific business rule node.
 */
export interface JSPBusinessRuleNode extends AstNode {
    kind: 'BusinessRule';
    properties: {
        ruleType: BusinessRuleType;
        ruleText: string;
        condition: string;
        consequence?: string;
        targetName?: string;
        targetType?: 'form_field' | 'form' | 'page';
        severity: RuleSeverity;
        errorMessage?: string;
        confidence: number;
        /** JSP-specific: source of the rule */
        jspSource: JSPRuleSource;
        /** JSP-specific: form name/ID if applicable */
        formId?: string;
        /** JSP-specific: servlet path */
        servletPath?: string;
    };
}

// =============================================================================
// Relationship Types for Business Rules
// =============================================================================

/**
 * Relationship types for business rule nodes.
 */
export const BUSINESS_RULE_RELATIONSHIPS = [
    'VALIDATES_FIELD',      // ValidationConstraint -> Field
    'GUARDS_METHOD',        // GuardClause -> Method
    'ENFORCES_RULE',        // Method -> BusinessRule
    'TESTS_RULE',           // TestAssertion -> BusinessRule
    'DERIVED_FROM',         // BusinessRule -> Source (annotation, if statement, etc.)
    'APPLIES_TO_PARAMETER', // ValidationConstraint -> Parameter
    'THROWS_ON_VIOLATION',  // GuardClause -> Exception type
] as const;

// =============================================================================
// Helper Types
// =============================================================================

/**
 * Extracted constraint parameter.
 */
export interface ConstraintParameter {
    name: string;
    value: string | number | boolean;
    type: 'string' | 'number' | 'boolean' | 'expression';
}

/**
 * Pattern match result for rule detection.
 */
export interface RulePatternMatch {
    pattern: string;
    match: string;
    startLine: number;
    endLine: number;
    confidence: number;
    metadata?: Record<string, any>;
}

/**
 * Business rule extraction configuration.
 */
export interface BusinessRuleExtractionConfig {
    /** Whether to extract validation annotations */
    extractValidationAnnotations: boolean;
    /** Whether to extract guard clauses */
    extractGuardClauses: boolean;
    /** Whether to extract conditional logic */
    extractConditionalLogic: boolean;
    /** Whether to extract error messages */
    extractErrorMessages: boolean;
    /** Whether to extract test assertions */
    extractTestAssertions: boolean;
    /** Minimum confidence threshold for rule inclusion */
    minConfidence: number;
    /** Custom patterns to detect */
    customPatterns?: string[];
}

/**
 * Default extraction configuration.
 */
export const DEFAULT_EXTRACTION_CONFIG: BusinessRuleExtractionConfig = {
    extractValidationAnnotations: true,
    extractGuardClauses: true,
    extractConditionalLogic: true,
    extractErrorMessages: true,
    extractTestAssertions: true,
    minConfidence: 0.5,
};
