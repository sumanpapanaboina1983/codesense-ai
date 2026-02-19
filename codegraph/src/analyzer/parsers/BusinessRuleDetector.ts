// src/analyzer/parsers/BusinessRuleDetector.ts
// Business Rule Detector - Pattern-based AST analysis for extracting business rules

import Parser from 'tree-sitter';
import { createContextLogger } from '../../utils/logger.js';
import { AstNode, RelationshipInfo, InstanceCounter, AnnotationInfo } from '../types.js';
import {
    BusinessRuleNode,
    ValidationConstraintNode,
    GuardClauseNode,
    ConditionalBusinessLogicNode,
    TestAssertionNode,
    BusinessRuleDetectionResult,
    BusinessRuleExtractionConfig,
    DEFAULT_EXTRACTION_CONFIG,
    ConditionOperator,
    RuleSeverity,
    JAVA_VALIDATION_ANNOTATIONS,
    JAVA_GUARD_PATTERNS,
    JSP_VALIDATION_PATTERNS,
    WEBFLOW_RULE_PATTERNS,
    JSPRuleSource,
    WebFlowRuleSource,
} from '../business-rule-types.js';
import { generateInstanceId, generateEntityId } from '../parser-utils.js';

const logger = createContextLogger('BusinessRuleDetector');

// Helper to get node text safely
function getNodeText(node: Parser.SyntaxNode | null | undefined): string {
    return node?.text ?? '';
}

// Helper to get location
function getNodeLocation(node: Parser.SyntaxNode): { startLine: number; endLine: number; startColumn: number; endColumn: number } {
    return {
        startLine: node.startPosition.row + 1,
        endLine: node.endPosition.row + 1,
        startColumn: node.startPosition.column,
        endColumn: node.endPosition.column,
    };
}

/**
 * Business Rule Detector - Extracts business rules from AST using pattern matching.
 *
 * Supports detection of:
 * - Validation annotations (@NotNull, @Min, @Pattern, etc.)
 * - Guard clauses (if (x == null) throw, Preconditions.checkNotNull)
 * - Conditional business logic (if (amount > 50000))
 * - Error messages encoding business rules
 * - Test assertions (assertEquals, assertThrows)
 */
export class BusinessRuleDetector {
    private instanceCounter: InstanceCounter = { count: 0 };
    private now: string = new Date().toISOString();
    private config: BusinessRuleExtractionConfig;
    private language: string;
    private filePath: string;

    // Accumulated results
    private rules: BusinessRuleNode[] = [];
    private validationConstraints: ValidationConstraintNode[] = [];
    private guardClauses: GuardClauseNode[] = [];
    private conditionalLogic: ConditionalBusinessLogicNode[] = [];
    private testAssertions: TestAssertionNode[] = [];
    private relationships: RelationshipInfo[] = [];

    constructor(
        filePath: string,
        language: string,
        config: Partial<BusinessRuleExtractionConfig> = {}
    ) {
        this.filePath = filePath;
        this.language = language;
        this.config = { ...DEFAULT_EXTRACTION_CONFIG, ...config };
    }

    /**
     * Detect all business rules from a syntax tree.
     */
    detectAll(rootNode: Parser.SyntaxNode, sourceText: string): BusinessRuleDetectionResult {
        logger.debug(`[BusinessRuleDetector] Starting detection for ${this.filePath}`);

        // Reset state
        this.rules = [];
        this.validationConstraints = [];
        this.guardClauses = [];
        this.conditionalLogic = [];
        this.testAssertions = [];
        this.relationships = [];
        this.instanceCounter.count = 0;
        this.now = new Date().toISOString();

        // Traverse and detect
        this.traverseAndDetect(rootNode, sourceText);

        const result: BusinessRuleDetectionResult = {
            filePath: this.filePath,
            rules: this.rules,
            validationConstraints: this.validationConstraints,
            guardClauses: this.guardClauses,
            conditionalLogic: this.conditionalLogic,
            testAssertions: this.testAssertions,
            totalRulesDetected:
                this.rules.length +
                this.validationConstraints.length +
                this.guardClauses.length +
                this.conditionalLogic.length +
                this.testAssertions.length,
            metadata: {
                language: this.language,
                parserVersion: '1.0.0',
                detectionTimestamp: this.now,
            },
        };

        logger.info(
            `[BusinessRuleDetector] Detection complete for ${this.filePath}. ` +
            `Rules: ${result.totalRulesDetected} ` +
            `(constraints: ${this.validationConstraints.length}, ` +
            `guards: ${this.guardClauses.length}, ` +
            `conditionals: ${this.conditionalLogic.length}, ` +
            `assertions: ${this.testAssertions.length})`
        );

        return result;
    }

    /**
     * Get detected relationships.
     */
    getRelationships(): RelationshipInfo[] {
        return this.relationships;
    }

    /**
     * Get all detected nodes (for adding to file parse result).
     */
    getAllNodes(): AstNode[] {
        return [
            ...this.rules,
            ...this.validationConstraints,
            ...this.guardClauses,
            ...this.conditionalLogic,
            ...this.testAssertions,
        ];
    }

    // =========================================================================
    // Traversal
    // =========================================================================

    private traverseAndDetect(node: Parser.SyntaxNode, sourceText: string, context?: DetectionContext): void {
        const ctx = context || { currentClass: null, currentMethod: null };

        // Update context based on node type
        if (this.language === 'Java') {
            if (node.type === 'class_declaration' || node.type === 'interface_declaration') {
                const nameNode = node.childForFieldName('name');
                ctx.currentClass = getNodeText(nameNode);
            } else if (node.type === 'method_declaration' || node.type === 'constructor_declaration') {
                const nameNode = node.childForFieldName('name');
                ctx.currentMethod = getNodeText(nameNode);
            }
        }

        // Detect based on node type
        this.detectFromNode(node, sourceText, ctx);

        // Recurse into children
        for (const child of node.namedChildren) {
            this.traverseAndDetect(child, sourceText, { ...ctx });
        }
    }

    private detectFromNode(node: Parser.SyntaxNode, sourceText: string, context: DetectionContext): void {
        switch (this.language) {
            case 'Java':
                this.detectJavaRules(node, sourceText, context);
                break;
            case 'Python':
                this.detectPythonRules(node, sourceText, context);
                break;
            case 'TypeScript':
            case 'JavaScript':
                this.detectTypeScriptRules(node, sourceText, context);
                break;
            case 'Go':
                this.detectGoRules(node, sourceText, context);
                break;
            case 'C#':
                this.detectCSharpRules(node, sourceText, context);
                break;
        }
    }

    // =========================================================================
    // Java Detection
    // =========================================================================

    private detectJavaRules(node: Parser.SyntaxNode, sourceText: string, context: DetectionContext): void {
        // Detect validation annotations on fields and parameters
        if (this.config.extractValidationAnnotations) {
            if (node.type === 'field_declaration') {
                this.detectJavaFieldValidation(node, context);
            } else if (node.type === 'formal_parameter') {
                this.detectJavaParameterValidation(node, context);
            }
        }

        // Detect guard clauses in method bodies
        if (this.config.extractGuardClauses) {
            if (node.type === 'if_statement') {
                this.detectJavaGuardClause(node, context);
            } else if (node.type === 'method_invocation') {
                this.detectJavaGuardMethod(node, context);
            }
        }

        // Detect conditional business logic
        if (this.config.extractConditionalLogic) {
            if (node.type === 'if_statement') {
                this.detectJavaConditionalLogic(node, context);
            }
        }

        // Detect test assertions
        if (this.config.extractTestAssertions) {
            if (node.type === 'method_invocation') {
                this.detectJavaTestAssertion(node, context);
            }
        }
    }

    private detectJavaFieldValidation(node: Parser.SyntaxNode, context: DetectionContext): void {
        const location = getNodeLocation(node);

        // Find modifiers which contain annotations
        for (const child of node.namedChildren) {
            if (child.type === 'modifiers') {
                for (const modifier of child.namedChildren) {
                    if (modifier.type === 'marker_annotation' || modifier.type === 'annotation') {
                        const annotation = this.parseJavaValidationAnnotation(modifier, 'field', context);
                        if (annotation) {
                            this.validationConstraints.push(annotation);
                        }
                    }
                }
            }
        }
    }

    private detectJavaParameterValidation(node: Parser.SyntaxNode, context: DetectionContext): void {
        const location = getNodeLocation(node);
        const paramName = getNodeText(node.childForFieldName('name'));

        // Check for annotations on the parameter
        for (const child of node.namedChildren) {
            if (child.type === 'marker_annotation' || child.type === 'annotation') {
                const annotation = this.parseJavaValidationAnnotation(child, 'parameter', context, paramName);
                if (annotation) {
                    this.validationConstraints.push(annotation);
                }
            }
        }
    }

    private parseJavaValidationAnnotation(
        annotationNode: Parser.SyntaxNode,
        targetType: 'field' | 'parameter',
        context: DetectionContext,
        targetName?: string
    ): ValidationConstraintNode | null {
        const location = getNodeLocation(annotationNode);
        const annotationText = getNodeText(annotationNode);
        const annotationName = annotationText.replace(/^@/, '').split('(')[0] || '';

        // Check if this is a known validation annotation
        if (!JAVA_VALIDATION_ANNOTATIONS.includes(annotationName as any)) {
            return null;
        }

        // Parse annotation parameters
        const constraintParameters = this.parseAnnotationParameters(annotationNode);

        // Generate rule text
        const ruleText = this.generateValidationRuleText(annotationName, constraintParameters, targetName || '');

        const entityId = generateEntityId(
            'validationconstraint',
            `${this.filePath}:${annotationName}:${location.startLine}`
        );

        return {
            id: generateInstanceId(
                this.instanceCounter,
                'validationconstraint',
                annotationName,
                { line: location.startLine, column: location.startColumn }
            ),
            entityId,
            kind: 'ValidationConstraint',
            name: `${annotationName}_${targetName || 'field'}`,
            filePath: this.filePath,
            language: this.language,
            ...location,
            createdAt: this.now,
            properties: {
                constraintName: annotationName,
                annotationText,
                targetName: targetName || '',
                targetType,
                constraintParameters,
                framework: 'javax.validation',
                ruleText,
                confidence: 0.95,
            },
        };
    }

    private parseAnnotationParameters(annotationNode: Parser.SyntaxNode): Record<string, string | number | boolean> {
        const params: Record<string, string | number | boolean> = {};

        // Find annotation_argument_list
        for (const child of annotationNode.namedChildren) {
            if (child.type === 'annotation_argument_list') {
                for (const arg of child.namedChildren) {
                    if (arg.type === 'element_value_pair') {
                        const key = getNodeText(arg.childForFieldName('key'));
                        const valueNode = arg.childForFieldName('value');
                        const value = getNodeText(valueNode);

                        // Try to parse numeric values
                        const numValue = parseFloat(value);
                        if (!isNaN(numValue) && value === String(numValue)) {
                            params[key] = numValue;
                        } else if (value === 'true' || value === 'false') {
                            params[key] = value === 'true';
                        } else {
                            params[key] = value.replace(/"/g, '');
                        }
                    } else {
                        // Single value annotation like @Min(5)
                        const value = getNodeText(arg);
                        const numValue = parseFloat(value);
                        if (!isNaN(numValue)) {
                            params['value'] = numValue;
                        } else {
                            params['value'] = value.replace(/"/g, '');
                        }
                    }
                }
            }
        }

        return params;
    }

    private detectJavaGuardClause(node: Parser.SyntaxNode, context: DetectionContext): void {
        const location = getNodeLocation(node);
        const conditionNode = node.childForFieldName('condition');
        const condition = getNodeText(conditionNode);

        // Check if this is a guard clause pattern (null check followed by throw)
        const consequenceNode = node.childForFieldName('consequence');
        if (!consequenceNode) return;

        const consequenceText = getNodeText(consequenceNode);

        // Must throw an exception or return to be a guard
        const isGuard =
            consequenceText.includes('throw ') ||
            consequenceText.includes('return;') ||
            consequenceText.includes('return null') ||
            consequenceText.includes('return false');

        if (!isGuard) return;

        // Parse the condition
        const guardInfo = this.parseGuardCondition(condition);
        if (!guardInfo) return;

        // Extract error message if throwing
        let errorMessage: string | undefined;
        let exceptionType: string | undefined;
        if (consequenceText.includes('throw ')) {
            const throwMatch = consequenceText.match(/throw\s+new\s+(\w+)\s*\(\s*"([^"]+)"/);
            if (throwMatch) {
                exceptionType = throwMatch[1];
                errorMessage = throwMatch[2];
            }
        }

        const entityId = generateEntityId(
            'guardclause',
            `${this.filePath}:${context.currentMethod}:${location.startLine}`
        );

        const ruleText = this.generateGuardRuleText(guardInfo, errorMessage);

        const guardNode: GuardClauseNode = {
            id: generateInstanceId(
                this.instanceCounter,
                'guardclause',
                `guard_${location.startLine}`,
                { line: location.startLine, column: location.startColumn }
            ),
            entityId,
            kind: 'GuardClause',
            name: `Guard_${guardInfo.leftOperand}`,
            filePath: this.filePath,
            language: this.language,
            ...location,
            createdAt: this.now,
            properties: {
                condition,
                operator: guardInfo.operator,
                leftOperand: guardInfo.leftOperand,
                rightOperand: guardInfo.rightOperand,
                guardType: guardInfo.guardType,
                exceptionType,
                errorMessage,
                isPrecondition: location.startLine <= (context.methodStartLine || 0) + 5,
                guardedMethod: context.currentMethod || '',
                ruleText,
                confidence: 0.9,
            },
        };

        this.guardClauses.push(guardNode);
    }

    private detectJavaGuardMethod(node: Parser.SyntaxNode, context: DetectionContext): void {
        const location = getNodeLocation(node);
        const methodText = getNodeText(node);

        // Check if this is a known guard method
        const guardPattern = JAVA_GUARD_PATTERNS.find(pattern =>
            methodText.includes(pattern.split('.')[1] || pattern)
        );

        if (!guardPattern) return;

        // Extract the arguments
        const argsNode = node.childForFieldName('arguments');
        const args = argsNode ? getNodeText(argsNode) : '';

        // Parse guard information
        const guardInfo = this.parseGuardMethodCall(guardPattern, args);
        if (!guardInfo) return;

        const entityId = generateEntityId(
            'guardclause',
            `${this.filePath}:${context.currentMethod}:${location.startLine}`
        );

        const guardNode: GuardClauseNode = {
            id: generateInstanceId(
                this.instanceCounter,
                'guardclause',
                `guard_${location.startLine}`,
                { line: location.startLine, column: location.startColumn }
            ),
            entityId,
            kind: 'GuardClause',
            name: `Guard_${guardPattern}`,
            filePath: this.filePath,
            language: this.language,
            ...location,
            createdAt: this.now,
            properties: {
                condition: methodText,
                operator: guardInfo.operator,
                leftOperand: guardInfo.leftOperand,
                rightOperand: guardInfo.rightOperand,
                guardType: guardInfo.guardType,
                errorMessage: guardInfo.errorMessage,
                isPrecondition: true,
                guardedMethod: context.currentMethod || '',
                ruleText: guardInfo.ruleText,
                confidence: 0.95,
            },
        };

        this.guardClauses.push(guardNode);
    }

    private detectJavaConditionalLogic(node: Parser.SyntaxNode, context: DetectionContext): void {
        const location = getNodeLocation(node);
        const conditionNode = node.childForFieldName('condition');
        const condition = getNodeText(conditionNode);

        // Skip simple null checks (these are guard clauses)
        if (condition.includes('== null') || condition.includes('!= null')) {
            return;
        }

        // Look for business logic patterns
        const businessInfo = this.analyzeBusinessCondition(condition);
        if (!businessInfo.isBusinessRule) return;

        // Get branch summaries
        const consequenceNode = node.childForFieldName('consequence');
        const alternativeNode = node.childForFieldName('alternative');

        const entityId = generateEntityId(
            'conditionalbusinesslogic',
            `${this.filePath}:${context.currentMethod}:${location.startLine}`
        );

        const conditionalNode: ConditionalBusinessLogicNode = {
            id: generateInstanceId(
                this.instanceCounter,
                'conditionalbusinesslogic',
                `cond_${location.startLine}`,
                { line: location.startLine, column: location.startColumn }
            ),
            entityId,
            kind: 'ConditionalBusinessLogic',
            name: `Condition_${businessInfo.variable}`,
            filePath: this.filePath,
            language: this.language,
            ...location,
            createdAt: this.now,
            properties: {
                condition,
                operator: businessInfo.operator,
                variable: businessInfo.variable,
                threshold: businessInfo.threshold,
                thenBranch: this.summarizeBranch(consequenceNode),
                elseBranch: alternativeNode ? this.summarizeBranch(alternativeNode) : undefined,
                businessMeaning: businessInfo.businessMeaning,
                isBusinessRule: true,
                businessKeywords: businessInfo.keywords,
                ruleText: businessInfo.ruleText,
                confidence: businessInfo.confidence,
            },
        };

        this.conditionalLogic.push(conditionalNode);
    }

    private detectJavaTestAssertion(node: Parser.SyntaxNode, context: DetectionContext): void {
        const location = getNodeLocation(node);
        const methodText = getNodeText(node);

        // Check for test assertion methods
        const assertionPatterns = [
            'assertEquals', 'assertNotEquals',
            'assertTrue', 'assertFalse',
            'assertNull', 'assertNotNull',
            'assertThrows', 'assertDoesNotThrow',
            'assertThat', 'assertAll',
        ];

        const assertionType = assertionPatterns.find(p => methodText.includes(p));
        if (!assertionType) return;

        // Check if we're in a test class/method
        const isTestContext =
            context.currentClass?.includes('Test') ||
            context.currentMethod?.startsWith('test') ||
            context.currentMethod?.includes('should');

        if (!isTestContext) return;

        // Parse assertion
        const assertionInfo = this.parseTestAssertion(assertionType, node);
        if (!assertionInfo) return;

        const entityId = generateEntityId(
            'testassertion',
            `${this.filePath}:${context.currentMethod}:${location.startLine}`
        );

        const assertionNode: TestAssertionNode = {
            id: generateInstanceId(
                this.instanceCounter,
                'testassertion',
                `assert_${location.startLine}`,
                { line: location.startLine, column: location.startColumn }
            ),
            entityId,
            kind: 'TestAssertion',
            name: `Assert_${assertionType}`,
            filePath: this.filePath,
            language: this.language,
            ...location,
            createdAt: this.now,
            properties: {
                assertionType,
                expectedValue: assertionInfo.expected,
                actualExpression: assertionInfo.actual,
                testMethodName: context.currentMethod || '',
                testClassName: context.currentClass || '',
                testedEntity: assertionInfo.testedEntity,
                testFramework: 'JUnit',
                inferredRule: assertionInfo.inferredRule,
                ruleText: assertionInfo.ruleText,
                confidence: 0.85,
            },
        };

        this.testAssertions.push(assertionNode);
    }

    // =========================================================================
    // Python Detection (Stub - to be expanded)
    // =========================================================================

    private detectPythonRules(node: Parser.SyntaxNode, sourceText: string, context: DetectionContext): void {
        // TODO: Implement Python detection (Pydantic, attrs, etc.)
        // Placeholder for Phase 3 implementation
    }

    // =========================================================================
    // TypeScript Detection (Stub - to be expanded)
    // =========================================================================

    private detectTypeScriptRules(node: Parser.SyntaxNode, sourceText: string, context: DetectionContext): void {
        // TODO: Implement TypeScript detection (class-validator, Zod, etc.)
        // Placeholder for Phase 3 implementation
    }

    // =========================================================================
    // Go Detection (Stub - to be expanded)
    // =========================================================================

    private detectGoRules(node: Parser.SyntaxNode, sourceText: string, context: DetectionContext): void {
        // TODO: Implement Go detection (error returns, validator tags)
        // Placeholder for Phase 5 implementation
    }

    // =========================================================================
    // C# Detection (Stub - to be expanded)
    // =========================================================================

    private detectCSharpRules(node: Parser.SyntaxNode, sourceText: string, context: DetectionContext): void {
        // TODO: Implement C# detection (Data Annotations, FluentValidation)
        // Placeholder for Phase 5 implementation
    }

    // =========================================================================
    // Helper Methods
    // =========================================================================

    private generateValidationRuleText(
        constraintName: string,
        params: Record<string, string | number | boolean>,
        targetName: string
    ): string {
        switch (constraintName) {
            case 'NotNull':
            case 'NonNull':
                return `${targetName} must not be null`;
            case 'NotEmpty':
                return `${targetName} must not be empty`;
            case 'NotBlank':
                return `${targetName} must not be blank`;
            case 'Min':
                return `${targetName} must be at least ${params.value || params.min || '?'}`;
            case 'Max':
                return `${targetName} must be at most ${params.value || params.max || '?'}`;
            case 'Size':
                return `${targetName} size must be between ${params.min || 0} and ${params.max || '?'}`;
            case 'Range':
                return `${targetName} must be between ${params.min || 0} and ${params.max || '?'}`;
            case 'Pattern':
                return `${targetName} must match pattern ${params.regexp || params.value || '?'}`;
            case 'Email':
                return `${targetName} must be a valid email address`;
            case 'Positive':
                return `${targetName} must be positive`;
            case 'PositiveOrZero':
                return `${targetName} must be zero or positive`;
            case 'Negative':
                return `${targetName} must be negative`;
            case 'NegativeOrZero':
                return `${targetName} must be zero or negative`;
            case 'Past':
                return `${targetName} must be in the past`;
            case 'Future':
                return `${targetName} must be in the future`;
            default:
                return `${targetName} must satisfy ${constraintName} constraint`;
        }
    }

    private parseGuardCondition(condition: string): GuardConditionInfo | null {
        // Null check patterns
        if (condition.includes('== null')) {
            const match = condition.match(/(\w+)\s*==\s*null/);
            if (match) {
                return {
                    leftOperand: match[1]!,
                    operator: 'is_null',
                    guardType: 'null_check',
                };
            }
        }

        if (condition.includes('!= null')) {
            const match = condition.match(/(\w+)\s*!=\s*null/);
            if (match) {
                return {
                    leftOperand: match[1]!,
                    operator: 'not_null',
                    guardType: 'null_check',
                };
            }
        }

        // Bounds check patterns
        const boundsMatch = condition.match(/(\w+)\s*([<>]=?)\s*(\d+)/);
        if (boundsMatch) {
            const opMap: Record<string, ConditionOperator> = {
                '<': 'less_than',
                '<=': 'less_than_or_equals',
                '>': 'greater_than',
                '>=': 'greater_than_or_equals',
            };
            return {
                leftOperand: boundsMatch[1]!,
                operator: opMap[boundsMatch[2]!] || 'custom',
                rightOperand: boundsMatch[3],
                guardType: 'bounds_check',
            };
        }

        // Boolean/state check
        if (condition.startsWith('!')) {
            const varName = condition.replace(/^!/, '').trim();
            return {
                leftOperand: varName,
                operator: 'equals',
                rightOperand: 'false',
                guardType: 'state_check',
            };
        }

        return null;
    }

    private parseGuardMethodCall(pattern: string, args: string): GuardMethodInfo | null {
        const argsClean = args.replace(/[()]/g, '');
        const argParts = argsClean.split(',').map(a => a.trim());

        if (pattern.includes('checkNotNull') || pattern.includes('requireNonNull')) {
            return {
                leftOperand: argParts[0] || '',
                operator: 'not_null',
                guardType: 'null_check',
                errorMessage: argParts[1]?.replace(/"/g, ''),
                ruleText: `${argParts[0]} must not be null`,
            };
        }

        if (pattern.includes('checkArgument') || pattern.includes('isTrue')) {
            return {
                leftOperand: argParts[0] || '',
                operator: 'equals',
                rightOperand: 'true',
                guardType: 'state_check',
                errorMessage: argParts[1]?.replace(/"/g, ''),
                ruleText: `Argument check: ${argParts[0]}`,
            };
        }

        if (pattern.includes('checkState') || pattern.includes('state')) {
            return {
                leftOperand: argParts[0] || '',
                operator: 'equals',
                rightOperand: 'true',
                guardType: 'state_check',
                errorMessage: argParts[1]?.replace(/"/g, ''),
                ruleText: `State check: ${argParts[0]}`,
            };
        }

        return null;
    }

    private generateGuardRuleText(guardInfo: GuardConditionInfo, errorMessage?: string): string {
        if (errorMessage) {
            return errorMessage;
        }

        switch (guardInfo.guardType) {
            case 'null_check':
                return guardInfo.operator === 'is_null'
                    ? `${guardInfo.leftOperand} must be null`
                    : `${guardInfo.leftOperand} must not be null`;
            case 'bounds_check':
                return `${guardInfo.leftOperand} must be ${guardInfo.operator.replace(/_/g, ' ')} ${guardInfo.rightOperand}`;
            case 'state_check':
                return `State check on ${guardInfo.leftOperand}`;
            default:
                return `Guard on ${guardInfo.leftOperand}`;
        }
    }

    private analyzeBusinessCondition(condition: string): BusinessConditionInfo {
        // Business keywords suggesting this is a business rule
        const businessKeywords = [
            'amount', 'price', 'total', 'balance', 'quantity', 'count',
            'status', 'state', 'type', 'category', 'level', 'tier',
            'discount', 'tax', 'fee', 'rate', 'percent', 'threshold',
            'limit', 'max', 'min', 'premium', 'standard', 'active',
            'enabled', 'approved', 'pending', 'expired', 'valid',
        ];

        const conditionLower = condition.toLowerCase();
        const foundKeywords = businessKeywords.filter(k => conditionLower.includes(k));

        if (foundKeywords.length === 0) {
            return { isBusinessRule: false, confidence: 0, keywords: [], variable: '', operator: 'custom', ruleText: '' };
        }

        // Parse the condition
        let variable = '';
        let operator: ConditionOperator = 'custom';
        let threshold: string | number | undefined;
        let businessMeaning = '';

        // Numeric comparison
        const numMatch = condition.match(/(\w+)\s*([<>]=?|==|!=)\s*(\d+(?:\.\d+)?)/);
        if (numMatch) {
            variable = numMatch[1]!;
            threshold = parseFloat(numMatch[3]!);
            const opMap: Record<string, ConditionOperator> = {
                '<': 'less_than',
                '<=': 'less_than_or_equals',
                '>': 'greater_than',
                '>=': 'greater_than_or_equals',
                '==': 'equals',
                '!=': 'not_equals',
            };
            operator = opMap[numMatch[2]!] || 'custom';
            businessMeaning = `When ${variable} is ${numMatch[2]} ${threshold}`;
        }

        // Status/enum comparison
        const statusMatch = condition.match(/(\w+)\s*==\s*["']?(\w+)["']?/);
        if (!numMatch && statusMatch) {
            variable = statusMatch[1]!;
            threshold = statusMatch[2];
            operator = 'equals';
            businessMeaning = `When ${variable} is ${threshold}`;
        }

        const ruleText = businessMeaning || `Condition on ${variable || condition}`;

        return {
            isBusinessRule: true,
            confidence: Math.min(0.5 + foundKeywords.length * 0.1, 0.9),
            keywords: foundKeywords,
            variable,
            operator,
            threshold,
            businessMeaning,
            ruleText,
        };
    }

    private summarizeBranch(branchNode: Parser.SyntaxNode | null): string {
        if (!branchNode) return '';

        const text = getNodeText(branchNode);

        // Try to extract meaningful action
        if (text.includes('return')) {
            const returnMatch = text.match(/return\s+([^;]+)/);
            if (returnMatch) return `returns ${returnMatch[1]?.substring(0, 50)}`;
        }

        if (text.includes('throw')) {
            const throwMatch = text.match(/throw\s+new\s+(\w+)/);
            if (throwMatch) return `throws ${throwMatch[1]}`;
        }

        // Method calls
        const callMatch = text.match(/(\w+)\s*\([^)]*\)/);
        if (callMatch) return `calls ${callMatch[1]}`;

        return text.substring(0, 50).replace(/\s+/g, ' ').trim();
    }

    private parseTestAssertion(assertionType: string, node: Parser.SyntaxNode): TestAssertionInfo | null {
        const argsNode = node.childForFieldName('arguments');
        if (!argsNode) return null;

        const args = argsNode.namedChildren;
        let expected: string | undefined;
        let actual = '';
        let testedEntity: string | undefined;

        switch (assertionType) {
            case 'assertEquals':
            case 'assertNotEquals':
                if (args.length >= 2) {
                    expected = getNodeText(args[0]);
                    actual = getNodeText(args[1]);
                }
                break;
            case 'assertTrue':
            case 'assertFalse':
                if (args.length >= 1) {
                    actual = getNodeText(args[0]);
                    expected = assertionType === 'assertTrue' ? 'true' : 'false';
                }
                break;
            case 'assertNull':
            case 'assertNotNull':
                if (args.length >= 1) {
                    actual = getNodeText(args[0]);
                    expected = assertionType === 'assertNull' ? 'null' : 'not null';
                }
                break;
            case 'assertThrows':
                if (args.length >= 2) {
                    expected = getNodeText(args[0]); // Exception class
                    actual = getNodeText(args[1]); // Lambda or method ref
                }
                break;
        }

        // Try to identify tested entity from actual expression
        const entityMatch = actual.match(/(\w+)\.(\w+)\s*\(/);
        if (entityMatch) {
            testedEntity = `${entityMatch[1]}.${entityMatch[2]}`;
        }

        const inferredRule = this.inferRuleFromAssertion(assertionType, expected, actual);
        const ruleText = `Test expects: ${inferredRule}`;

        return {
            expected,
            actual,
            testedEntity,
            inferredRule,
            ruleText,
        };
    }

    private inferRuleFromAssertion(type: string, expected: string | undefined, actual: string): string {
        switch (type) {
            case 'assertEquals':
                return `${actual} should equal ${expected}`;
            case 'assertNotEquals':
                return `${actual} should not equal ${expected}`;
            case 'assertTrue':
                return `${actual} should be true`;
            case 'assertFalse':
                return `${actual} should be false`;
            case 'assertNull':
                return `${actual} should be null`;
            case 'assertNotNull':
                return `${actual} should not be null`;
            case 'assertThrows':
                return `${actual} should throw ${expected}`;
            default:
                return `${actual} should satisfy ${type}`;
        }
    }

    // =========================================================================
    // JSP Business Rule Detection (Text-based)
    // =========================================================================

    /**
     * Detect business rules from JSP content (text-based, no tree-sitter).
     * Call this directly from the JSP parser.
     */
    detectJSPRules(content: string, servletPath?: string): BusinessRuleDetectionResult {
        logger.debug(`[BusinessRuleDetector] Starting JSP detection for ${this.filePath}`);

        // Reset state
        this.rules = [];
        this.validationConstraints = [];
        this.guardClauses = [];
        this.conditionalLogic = [];
        this.testAssertions = [];
        this.relationships = [];
        this.instanceCounter.count = 0;
        this.now = new Date().toISOString();

        const lines = content.split('\n');

        // Detect HTML5 validation attributes
        this.detectJSPHTML5Validation(content, lines);

        // Detect Spring form validation tags
        this.detectJSPSpringFormValidation(content, lines);

        // Detect JSTL conditionals with business logic
        this.detectJSPJSTLConditionals(content, lines);

        // Detect EL expressions with validation logic
        this.detectJSPELExpressions(content, lines);

        const result: BusinessRuleDetectionResult = {
            filePath: this.filePath,
            rules: this.rules,
            validationConstraints: this.validationConstraints,
            guardClauses: this.guardClauses,
            conditionalLogic: this.conditionalLogic,
            testAssertions: this.testAssertions,
            totalRulesDetected:
                this.rules.length +
                this.validationConstraints.length +
                this.guardClauses.length +
                this.conditionalLogic.length,
            metadata: {
                language: 'JSP',
                parserVersion: '1.0.0',
                detectionTimestamp: this.now,
            },
        };

        logger.info(
            `[BusinessRuleDetector] JSP detection complete for ${this.filePath}. ` +
            `Rules: ${result.totalRulesDetected}`
        );

        return result;
    }

    private detectJSPHTML5Validation(content: string, lines: string[]): void {
        // Detect required fields
        let match;
        const requiredPattern = /<input[^>]*\s+name="([^"]+)"[^>]*required[^>]*>/gi;
        while ((match = requiredPattern.exec(content)) !== null) {
            const fieldName = match[1] || 'field';
            const lineNum = this.getLineNumber(content, match.index);

            this.validationConstraints.push(this.createJSPValidationConstraint(
                'Required',
                fieldName,
                `${fieldName} is required`,
                lineNum,
                'html5_validation',
                { required: true }
            ));
        }

        // Detect pattern validation
        const patternPattern = /<input[^>]*\s+name="([^"]+)"[^>]*pattern="([^"]+)"[^>]*>/gi;
        while ((match = patternPattern.exec(content)) !== null) {
            const fieldName = match[1] || 'field';
            const pattern = match[2] || '';
            const lineNum = this.getLineNumber(content, match.index);

            this.validationConstraints.push(this.createJSPValidationConstraint(
                'Pattern',
                fieldName,
                `${fieldName} must match pattern: ${pattern}`,
                lineNum,
                'html5_validation',
                { pattern }
            ));
        }

        // Detect min/max validation
        const minMaxPattern = /<input[^>]*\s+name="([^"]+)"[^>]*(?:min="([^"]+)"|max="([^"]+)")+[^>]*>/gi;
        while ((match = minMaxPattern.exec(content)) !== null) {
            const fieldName = match[1] || 'field';
            const min = match[2];
            const max = match[3];
            const lineNum = this.getLineNumber(content, match.index);

            if (min) {
                this.validationConstraints.push(this.createJSPValidationConstraint(
                    'Min',
                    fieldName,
                    `${fieldName} must be at least ${min}`,
                    lineNum,
                    'html5_validation',
                    { min }
                ));
            }
            if (max) {
                this.validationConstraints.push(this.createJSPValidationConstraint(
                    'Max',
                    fieldName,
                    `${fieldName} must be at most ${max}`,
                    lineNum,
                    'html5_validation',
                    { max }
                ));
            }
        }

        // Detect minlength/maxlength
        const lengthPattern = /<input[^>]*\s+name="([^"]+)"[^>]*(?:minlength="(\d+)"|maxlength="(\d+)")+[^>]*>/gi;
        while ((match = lengthPattern.exec(content)) !== null) {
            const fieldName = match[1] || 'field';
            const minLength = match[2];
            const maxLength = match[3];
            const lineNum = this.getLineNumber(content, match.index);

            if (minLength || maxLength) {
                this.validationConstraints.push(this.createJSPValidationConstraint(
                    'Length',
                    fieldName,
                    `${fieldName} length must be ${minLength ? `at least ${minLength}` : ''} ${maxLength ? `at most ${maxLength}` : ''}`.trim(),
                    lineNum,
                    'html5_validation',
                    { minLength, maxLength }
                ));
            }
        }

        // Detect type=email
        const emailPattern = /<input[^>]*\s+name="([^"]+)"[^>]*type="email"[^>]*>/gi;
        while ((match = emailPattern.exec(content)) !== null) {
            const fieldName = match[1] || 'email';
            const lineNum = this.getLineNumber(content, match.index);

            this.validationConstraints.push(this.createJSPValidationConstraint(
                'Email',
                fieldName,
                `${fieldName} must be a valid email address`,
                lineNum,
                'html5_validation',
                { type: 'email' }
            ));
        }
    }

    private detectJSPSpringFormValidation(content: string, lines: string[]): void {
        let match;

        // Detect <form:errors path="...">
        const errorsPattern = /<form:errors\s+path="([^"]+)"[^>]*>/gi;
        while ((match = errorsPattern.exec(content)) !== null) {
            const fieldPath = match[1] || '';
            const lineNum = this.getLineNumber(content, match.index);

            // This indicates server-side validation exists for this field
            this.validationConstraints.push(this.createJSPValidationConstraint(
                'ServerValidation',
                fieldPath,
                `${fieldPath} has server-side validation (errors displayed via form:errors)`,
                lineNum,
                'spring_form_errors',
                { errorPath: fieldPath }
            ));
        }

        // Detect <spring:bind path="..."> with errors
        const bindPattern = /<spring:bind\s+path="([^"]+)"[^>]*>/gi;
        while ((match = bindPattern.exec(content)) !== null) {
            const bindPath = match[1] || '';
            const lineNum = this.getLineNumber(content, match.index);

            // Check if there's error handling nearby
            const surroundingContent = content.substring(
                Math.max(0, match.index - 100),
                Math.min(content.length, match.index + 500)
            );

            if (surroundingContent.includes('status.error') || surroundingContent.includes('errors')) {
                this.validationConstraints.push(this.createJSPValidationConstraint(
                    'SpringBind',
                    bindPath,
                    `${bindPath} is bound with validation (spring:bind with error handling)`,
                    lineNum,
                    'spring_bind',
                    { bindPath }
                ));
            }
        }
    }

    private detectJSPJSTLConditionals(content: string, lines: string[]): void {
        let match;

        // Detect <c:if test="${condition}">
        const cifPattern = /<c:if\s+test="\${([^}]+)}"[^>]*>/gi;
        while ((match = cifPattern.exec(content)) !== null) {
            const condition = match[1] || '';
            const lineNum = this.getLineNumber(content, match.index);

            // Analyze if this is a business rule
            const businessInfo = this.analyzeJSPCondition(condition);
            if (businessInfo.isBusinessRule) {
                this.conditionalLogic.push(this.createJSPConditionalLogic(
                    condition,
                    businessInfo,
                    lineNum,
                    'jstl_conditional'
                ));
            }
        }

        // Detect <c:when test="${condition}">
        const cwhenPattern = /<c:when\s+test="\${([^}]+)}"[^>]*>/gi;
        while ((match = cwhenPattern.exec(content)) !== null) {
            const condition = match[1] || '';
            const lineNum = this.getLineNumber(content, match.index);

            const businessInfo = this.analyzeJSPCondition(condition);
            if (businessInfo.isBusinessRule) {
                this.conditionalLogic.push(this.createJSPConditionalLogic(
                    condition,
                    businessInfo,
                    lineNum,
                    'jstl_conditional'
                ));
            }
        }
    }

    private detectJSPELExpressions(content: string, lines: string[]): void {
        let match;

        // Detect ${not empty x} - required field check
        const notEmptyPattern = /\${not\s+empty\s+([^}]+)}/gi;
        while ((match = notEmptyPattern.exec(content)) !== null) {
            const fieldExpr = match[1]?.trim() || '';
            const lineNum = this.getLineNumber(content, match.index);

            // Extract field name from expression like "form.fieldName"
            const fieldName = fieldExpr.split('.').pop() || fieldExpr;

            this.guardClauses.push(this.createJSPGuardClause(
                `not empty ${fieldExpr}`,
                fieldName,
                'not_empty',
                `${fieldName} must not be empty`,
                lineNum,
                'el_expression'
            ));
        }

        // Detect ${empty x} - empty check
        const emptyPattern = /\${empty\s+([^}]+)}/gi;
        while ((match = emptyPattern.exec(content)) !== null) {
            const fieldExpr = match[1]?.trim() || '';
            const lineNum = this.getLineNumber(content, match.index);
            const fieldName = fieldExpr.split('.').pop() || fieldExpr;

            this.guardClauses.push(this.createJSPGuardClause(
                `empty ${fieldExpr}`,
                fieldName,
                'is_empty',
                `${fieldName} is empty check`,
                lineNum,
                'el_expression'
            ));
        }

        // Detect comparison expressions ${x > 0}, ${x == 'value'}
        const comparisonPattern = /\${([a-zA-Z_.]+)\s*(==|!=|>|<|>=|<=|eq|ne|gt|lt|ge|le)\s*(['"]?[^}'"]+['"]?)}/gi;
        while ((match = comparisonPattern.exec(content)) !== null) {
            const leftOperand = match[1]?.trim() || '';
            const operator = match[2] || '';
            const rightOperand = match[3]?.trim().replace(/['"]/g, '') || '';
            const lineNum = this.getLineNumber(content, match.index);

            const fieldName = leftOperand.split('.').pop() || leftOperand;
            const businessInfo = this.analyzeJSPCondition(`${leftOperand} ${operator} ${rightOperand}`);

            if (businessInfo.isBusinessRule) {
                this.conditionalLogic.push(this.createJSPConditionalLogic(
                    `${leftOperand} ${operator} ${rightOperand}`,
                    businessInfo,
                    lineNum,
                    'el_expression'
                ));
            }
        }
    }

    private createJSPValidationConstraint(
        constraintName: string,
        targetName: string,
        ruleText: string,
        lineNum: number,
        source: JSPRuleSource,
        params: Record<string, any>
    ): ValidationConstraintNode {
        const entityId = generateEntityId(
            'validationconstraint',
            `${this.filePath}:${constraintName}:${targetName}:${lineNum}`
        );

        return {
            id: generateInstanceId(
                this.instanceCounter,
                'validationconstraint',
                `${constraintName}_${targetName}`,
                { line: lineNum, column: 0 }
            ),
            entityId,
            kind: 'ValidationConstraint',
            name: `${constraintName}_${targetName}`,
            filePath: this.filePath,
            language: 'JSP',
            startLine: lineNum,
            endLine: lineNum,
            startColumn: 0,
            endColumn: 0,
            createdAt: this.now,
            properties: {
                constraintName,
                annotationText: `${source}:${constraintName}`,
                targetName,
                targetType: 'field',
                constraintParameters: params,
                framework: 'JSP/HTML5',
                ruleText,
                confidence: source === 'spring_form_errors' ? 0.95 : 0.85,
            },
        };
    }

    private createJSPGuardClause(
        condition: string,
        targetName: string,
        operator: ConditionOperator,
        ruleText: string,
        lineNum: number,
        source: JSPRuleSource
    ): GuardClauseNode {
        const entityId = generateEntityId(
            'guardclause',
            `${this.filePath}:jsp:${lineNum}`
        );

        return {
            id: generateInstanceId(
                this.instanceCounter,
                'guardclause',
                `guard_${lineNum}`,
                { line: lineNum, column: 0 }
            ),
            entityId,
            kind: 'GuardClause',
            name: `Guard_${targetName}`,
            filePath: this.filePath,
            language: 'JSP',
            startLine: lineNum,
            endLine: lineNum,
            startColumn: 0,
            endColumn: 0,
            createdAt: this.now,
            properties: {
                condition,
                operator,
                leftOperand: targetName,
                guardType: operator === 'is_empty' || operator === 'not_empty' ? 'null_check' : 'state_check',
                isPrecondition: false,
                guardedMethod: 'JSP_page',
                ruleText,
                confidence: 0.80,
            },
        };
    }

    private createJSPConditionalLogic(
        condition: string,
        businessInfo: BusinessConditionInfo,
        lineNum: number,
        source: JSPRuleSource
    ): ConditionalBusinessLogicNode {
        const entityId = generateEntityId(
            'conditionalbusinesslogic',
            `${this.filePath}:jsp:${lineNum}`
        );

        return {
            id: generateInstanceId(
                this.instanceCounter,
                'conditionalbusinesslogic',
                `cond_${lineNum}`,
                { line: lineNum, column: 0 }
            ),
            entityId,
            kind: 'ConditionalBusinessLogic',
            name: `Condition_${businessInfo.variable || condition.substring(0, 20)}`,
            filePath: this.filePath,
            language: 'JSP',
            startLine: lineNum,
            endLine: lineNum,
            startColumn: 0,
            endColumn: 0,
            createdAt: this.now,
            properties: {
                condition,
                operator: businessInfo.operator,
                variable: businessInfo.variable,
                threshold: businessInfo.threshold,
                thenBranch: 'conditional display/action',
                businessMeaning: businessInfo.businessMeaning,
                isBusinessRule: true,
                businessKeywords: businessInfo.keywords,
                ruleText: businessInfo.ruleText,
                confidence: businessInfo.confidence,
            },
        };
    }

    private analyzeJSPCondition(condition: string): BusinessConditionInfo {
        // Business keywords for JSP/web context
        const businessKeywords = [
            'user', 'role', 'permission', 'auth', 'logged', 'admin',
            'status', 'state', 'type', 'category', 'level',
            'amount', 'price', 'total', 'balance', 'quantity', 'count',
            'active', 'enabled', 'disabled', 'valid', 'invalid',
            'error', 'success', 'warning', 'message',
            'empty', 'null', 'size', 'length',
        ];

        const conditionLower = condition.toLowerCase();
        const foundKeywords = businessKeywords.filter(k => conditionLower.includes(k));

        if (foundKeywords.length === 0) {
            return {
                isBusinessRule: false,
                confidence: 0,
                keywords: [],
                variable: '',
                operator: 'custom',
                ruleText: '',
            };
        }

        // Parse the condition
        let variable = '';
        let operator: ConditionOperator = 'custom';
        let threshold: string | number | undefined;

        // Extract variable from common patterns
        const varMatch = condition.match(/([a-zA-Z_.]+)\s*(==|!=|>|<|>=|<=|eq|ne|gt|lt|ge|le)/);
        if (varMatch) {
            variable = varMatch[1] || '';
            const op = varMatch[2];
            const opMap: Record<string, ConditionOperator> = {
                '==': 'equals', 'eq': 'equals',
                '!=': 'not_equals', 'ne': 'not_equals',
                '>': 'greater_than', 'gt': 'greater_than',
                '<': 'less_than', 'lt': 'less_than',
                '>=': 'greater_than_or_equals', 'ge': 'greater_than_or_equals',
                '<=': 'less_than_or_equals', 'le': 'less_than_or_equals',
            };
            operator = opMap[op || ''] || 'custom';
        }

        // Check for empty/not empty
        if (condition.includes('not empty')) {
            variable = condition.replace(/not\s+empty\s*/i, '').trim();
            operator = 'not_empty';
        } else if (condition.includes('empty')) {
            variable = condition.replace(/empty\s*/i, '').trim();
            operator = 'is_empty';
        }

        const ruleText = `When ${condition}`;

        return {
            isBusinessRule: true,
            confidence: Math.min(0.5 + foundKeywords.length * 0.1, 0.85),
            keywords: foundKeywords,
            variable,
            operator,
            threshold,
            businessMeaning: ruleText,
            ruleText,
        };
    }

    // =========================================================================
    // Spring WebFlow Business Rule Detection (XML-based)
    // =========================================================================

    /**
     * Detect business rules from Spring WebFlow XML content.
     * Call this directly from the WebFlow parser.
     */
    detectWebFlowRules(content: string, flowId?: string): BusinessRuleDetectionResult {
        logger.debug(`[BusinessRuleDetector] Starting WebFlow detection for ${this.filePath}`);

        // Reset state
        this.rules = [];
        this.validationConstraints = [];
        this.guardClauses = [];
        this.conditionalLogic = [];
        this.testAssertions = [];
        this.relationships = [];
        this.instanceCounter.count = 0;
        this.now = new Date().toISOString();

        const lines = content.split('\n');

        // Detect decision state conditions
        this.detectWebFlowDecisionStates(content, lines, flowId);

        // Detect transition guards/conditions
        this.detectWebFlowTransitionGuards(content, lines, flowId);

        // Detect evaluate expressions with validation
        this.detectWebFlowEvaluateExpressions(content, lines, flowId);

        // Detect security constraints
        this.detectWebFlowSecurityConstraints(content, lines, flowId);

        // Detect binding constraints
        this.detectWebFlowBindingConstraints(content, lines, flowId);

        const result: BusinessRuleDetectionResult = {
            filePath: this.filePath,
            rules: this.rules,
            validationConstraints: this.validationConstraints,
            guardClauses: this.guardClauses,
            conditionalLogic: this.conditionalLogic,
            testAssertions: this.testAssertions,
            totalRulesDetected:
                this.rules.length +
                this.validationConstraints.length +
                this.guardClauses.length +
                this.conditionalLogic.length,
            metadata: {
                language: 'SpringWebFlow',
                parserVersion: '1.0.0',
                detectionTimestamp: this.now,
            },
        };

        logger.info(
            `[BusinessRuleDetector] WebFlow detection complete for ${this.filePath}. ` +
            `Rules: ${result.totalRulesDetected}`
        );

        return result;
    }

    private detectWebFlowDecisionStates(content: string, lines: string[], flowId?: string): void {
        let match;

        // Find decision-state elements
        const decisionStatePattern = /<decision-state\s+id="([^"]+)"[^>]*>([\s\S]*?)<\/decision-state>/gi;
        while ((match = decisionStatePattern.exec(content)) !== null) {
            const stateId = match[1] || '';
            const stateContent = match[2] || '';
            const lineNum = this.getLineNumber(content, match.index);

            // Find <if> conditions within
            const ifPattern = /<if\s+test="([^"]+)"\s+then="([^"]+)"(?:\s+else="([^"]+)")?[^>]*\/?>/gi;
            let ifMatch;
            while ((ifMatch = ifPattern.exec(stateContent)) !== null) {
                const condition = ifMatch[1] || '';
                const thenTarget = ifMatch[2] || '';
                const elseTarget = ifMatch[3];

                this.conditionalLogic.push(this.createWebFlowConditionalLogic(
                    condition,
                    stateId,
                    thenTarget,
                    elseTarget,
                    lineNum,
                    flowId,
                    'decision_state'
                ));
            }
        }
    }

    private detectWebFlowTransitionGuards(content: string, lines: string[], flowId?: string): void {
        let match;

        // Find transitions with conditions
        const transitionPattern = /<transition\s+on="([^"]+)"[^>]*to="([^"]+)"[^>]*(?:condition="([^"]+)")?[^>]*\/?>/gi;
        while ((match = transitionPattern.exec(content)) !== null) {
            const event = match[1] || '';
            const toState = match[2] || '';
            const condition = match[3];
            const lineNum = this.getLineNumber(content, match.index);

            if (condition) {
                this.guardClauses.push(this.createWebFlowGuardClause(
                    condition,
                    event,
                    toState,
                    lineNum,
                    flowId,
                    'transition_guard'
                ));
            }
        }

        // Also check for if conditions within transitions
        const transitionIfPattern = /<transition[^>]*>[\s\S]*?<if\s+test="([^"]+)"[^>]*\/>[\s\S]*?<\/transition>/gi;
        while ((match = transitionIfPattern.exec(content)) !== null) {
            const condition = match[1] || '';
            const lineNum = this.getLineNumber(content, match.index);

            if (condition) {
                this.guardClauses.push(this.createWebFlowGuardClause(
                    condition,
                    'transition',
                    'conditional',
                    lineNum,
                    flowId,
                    'transition_guard'
                ));
            }
        }
    }

    private detectWebFlowEvaluateExpressions(content: string, lines: string[], flowId?: string): void {
        let match;

        // Find evaluate expressions (often contain validation logic)
        const evaluatePattern = /<evaluate\s+expression="([^"]+)"(?:\s+result="([^"]+)")?[^>]*\/?>/gi;
        while ((match = evaluatePattern.exec(content)) !== null) {
            const expression = match[1] || '';
            const result = match[2];
            const lineNum = this.getLineNumber(content, match.index);

            // Check if this looks like validation
            const isValidation = /validate|valid|check|verify|assert/i.test(expression);
            const isBusinessLogic = this.containsBusinessKeywords(expression);

            if (isValidation || isBusinessLogic) {
                const ruleText = this.parseEvaluateExpression(expression);

                this.rules.push(this.createWebFlowBusinessRule(
                    expression,
                    ruleText,
                    lineNum,
                    flowId,
                    'evaluate_expression',
                    isValidation ? 0.90 : 0.75
                ));
            }
        }
    }

    private detectWebFlowSecurityConstraints(content: string, lines: string[], flowId?: string): void {
        let match;

        // Find secured elements
        const securedPattern = /<secured\s+attributes="([^"]+)"[^>]*\/?>/gi;
        while ((match = securedPattern.exec(content)) !== null) {
            const attributes = match[1] || '';
            const lineNum = this.getLineNumber(content, match.index);

            // Find the parent state
            const precedingContent = content.substring(0, match.index);
            const stateMatch = precedingContent.match(/<(?:view-state|action-state|subflow-state)\s+id="([^"]+)"/g);
            const parentState = stateMatch ? stateMatch[stateMatch.length - 1]?.match(/id="([^"]+)"/)?.[1] : 'flow';

            this.rules.push(this.createWebFlowBusinessRule(
                `secured: ${attributes}`,
                `Access to ${parentState || 'state'} requires: ${attributes}`,
                lineNum,
                flowId,
                'security_constraint',
                0.95
            ));
        }
    }

    private detectWebFlowBindingConstraints(content: string, lines: string[], flowId?: string): void {
        let match;

        // Find binding elements with required attribute
        const bindingPattern = /<binding\s+property="([^"]+)"(?:\s+required="([^"]+)")?[^>]*\/?>/gi;
        while ((match = bindingPattern.exec(content)) !== null) {
            const property = match[1] || '';
            const required = match[2];
            const lineNum = this.getLineNumber(content, match.index);

            if (required === 'true') {
                this.validationConstraints.push(this.createWebFlowValidationConstraint(
                    'Required',
                    property,
                    `${property} is required in form binding`,
                    lineNum,
                    flowId,
                    'binding_constraint'
                ));
            }
        }

        // Find binder with binding children
        const binderPattern = /<binder>([\s\S]*?)<\/binder>/gi;
        while ((match = binderPattern.exec(content)) !== null) {
            const binderContent = match[1] || '';
            const baseLineNum = this.getLineNumber(content, match.index);

            // Parse bindings within
            let bindingMatch;
            const innerBindingPattern = /<binding\s+property="([^"]+)"(?:[^>]*converter="([^"]+)")?[^>]*\/?>/gi;
            while ((bindingMatch = innerBindingPattern.exec(binderContent)) !== null) {
                const property = bindingMatch[1] || '';
                const converter = bindingMatch[2];

                if (converter) {
                    this.validationConstraints.push(this.createWebFlowValidationConstraint(
                        'TypeConversion',
                        property,
                        `${property} uses converter: ${converter}`,
                        baseLineNum,
                        flowId,
                        'binding_constraint'
                    ));
                }
            }
        }
    }

    private createWebFlowConditionalLogic(
        condition: string,
        stateId: string,
        thenTarget: string,
        elseTarget: string | undefined,
        lineNum: number,
        flowId: string | undefined,
        source: WebFlowRuleSource
    ): ConditionalBusinessLogicNode {
        const entityId = generateEntityId(
            'conditionalbusinesslogic',
            `${this.filePath}:${stateId}:${lineNum}`
        );

        // Analyze the condition
        const businessInfo = this.analyzeWebFlowCondition(condition);

        return {
            id: generateInstanceId(
                this.instanceCounter,
                'conditionalbusinesslogic',
                `decision_${stateId}`,
                { line: lineNum, column: 0 }
            ),
            entityId,
            kind: 'ConditionalBusinessLogic',
            name: `Decision_${stateId}`,
            filePath: this.filePath,
            language: 'SpringWebFlow',
            startLine: lineNum,
            endLine: lineNum,
            startColumn: 0,
            endColumn: 0,
            createdAt: this.now,
            properties: {
                condition,
                operator: businessInfo.operator,
                variable: businessInfo.variable,
                threshold: businessInfo.threshold,
                thenBranch: `transitions to ${thenTarget}`,
                elseBranch: elseTarget ? `transitions to ${elseTarget}` : undefined,
                businessMeaning: `Decision state ${stateId}: ${condition}`,
                isBusinessRule: true,
                businessKeywords: businessInfo.keywords,
                ruleText: `If ${condition} then go to ${thenTarget}${elseTarget ? `, else go to ${elseTarget}` : ''}`,
                confidence: 0.90,
            },
        };
    }

    private createWebFlowGuardClause(
        condition: string,
        event: string,
        toState: string,
        lineNum: number,
        flowId: string | undefined,
        source: WebFlowRuleSource
    ): GuardClauseNode {
        const entityId = generateEntityId(
            'guardclause',
            `${this.filePath}:${event}:${lineNum}`
        );

        return {
            id: generateInstanceId(
                this.instanceCounter,
                'guardclause',
                `guard_${event}_${lineNum}`,
                { line: lineNum, column: 0 }
            ),
            entityId,
            kind: 'GuardClause',
            name: `Guard_${event}`,
            filePath: this.filePath,
            language: 'SpringWebFlow',
            startLine: lineNum,
            endLine: lineNum,
            startColumn: 0,
            endColumn: 0,
            createdAt: this.now,
            properties: {
                condition,
                operator: 'custom',
                leftOperand: event,
                rightOperand: toState,
                guardType: 'state_check',
                isPrecondition: true,
                guardedMethod: `transition_${event}`,
                ruleText: `Transition on '${event}' to '${toState}' requires: ${condition}`,
                confidence: 0.90,
            },
        };
    }

    private createWebFlowBusinessRule(
        condition: string,
        ruleText: string,
        lineNum: number,
        flowId: string | undefined,
        source: WebFlowRuleSource,
        confidence: number
    ): BusinessRuleNode {
        const entityId = generateEntityId(
            'businessrule',
            `${this.filePath}:${source}:${lineNum}`
        );

        return {
            id: generateInstanceId(
                this.instanceCounter,
                'businessrule',
                `rule_${lineNum}`,
                { line: lineNum, column: 0 }
            ),
            entityId,
            kind: 'BusinessRule',
            name: `Rule_${source}_${lineNum}`,
            filePath: this.filePath,
            language: 'SpringWebFlow',
            startLine: lineNum,
            endLine: lineNum,
            startColumn: 0,
            endColumn: 0,
            createdAt: this.now,
            properties: {
                ruleType: source === 'security_constraint' ? 'guard_clause' : 'conditional_logic',
                ruleText,
                condition,
                severity: source === 'security_constraint' ? 'error' : 'warning',
                confidence,
            },
        };
    }

    private createWebFlowValidationConstraint(
        constraintName: string,
        targetName: string,
        ruleText: string,
        lineNum: number,
        flowId: string | undefined,
        source: WebFlowRuleSource
    ): ValidationConstraintNode {
        const entityId = generateEntityId(
            'validationconstraint',
            `${this.filePath}:${constraintName}:${targetName}:${lineNum}`
        );

        return {
            id: generateInstanceId(
                this.instanceCounter,
                'validationconstraint',
                `${constraintName}_${targetName}`,
                { line: lineNum, column: 0 }
            ),
            entityId,
            kind: 'ValidationConstraint',
            name: `${constraintName}_${targetName}`,
            filePath: this.filePath,
            language: 'SpringWebFlow',
            startLine: lineNum,
            endLine: lineNum,
            startColumn: 0,
            endColumn: 0,
            createdAt: this.now,
            properties: {
                constraintName,
                annotationText: `webflow:${source}`,
                targetName,
                targetType: 'field',
                constraintParameters: {},
                framework: 'SpringWebFlow',
                ruleText,
                confidence: 0.90,
            },
        };
    }

    private analyzeWebFlowCondition(condition: string): BusinessConditionInfo {
        // WebFlow conditions often use SpEL
        const businessKeywords = [
            'user', 'role', 'permission', 'auth', 'logged', 'admin',
            'status', 'state', 'type', 'valid', 'invalid',
            'amount', 'total', 'count', 'size',
            'success', 'error', 'result',
        ];

        const conditionLower = condition.toLowerCase();
        const foundKeywords = businessKeywords.filter(k => conditionLower.includes(k));

        let variable = '';
        let operator: ConditionOperator = 'custom';
        let threshold: string | number | undefined;

        // Parse SpEL expression
        const spelMatch = condition.match(/([a-zA-Z_.()]+)\s*(==|!=|>|<|>=|<=)\s*(['"]?[^'"]+['"]?)/);
        if (spelMatch) {
            variable = spelMatch[1] || '';
            const op = spelMatch[2];
            threshold = spelMatch[3]?.replace(/['"]/g, '');
            const opMap: Record<string, ConditionOperator> = {
                '==': 'equals',
                '!=': 'not_equals',
                '>': 'greater_than',
                '<': 'less_than',
                '>=': 'greater_than_or_equals',
                '<=': 'less_than_or_equals',
            };
            operator = opMap[op || ''] || 'custom';
        }

        return {
            isBusinessRule: foundKeywords.length > 0 || spelMatch !== null,
            confidence: Math.min(0.6 + foundKeywords.length * 0.1, 0.90),
            keywords: foundKeywords,
            variable,
            operator,
            threshold,
            businessMeaning: condition,
            ruleText: condition,
        };
    }

    private parseEvaluateExpression(expression: string): string {
        // Convert SpEL expression to readable rule
        // e.g., "orderValidator.validate(order)" -> "Order must pass validation"

        if (expression.includes('validate')) {
            const match = expression.match(/(\w+)Validator\.validate\((\w+)\)/i);
            if (match) {
                return `${match[2]} must pass ${match[1]} validation`;
            }
            return `Validation: ${expression}`;
        }

        if (expression.includes('.')) {
            // Bean method call
            return `Execute: ${expression}`;
        }

        return expression;
    }

    private containsBusinessKeywords(text: string): boolean {
        const keywords = [
            'validate', 'check', 'verify', 'process', 'calculate',
            'save', 'update', 'delete', 'create', 'submit',
            'approve', 'reject', 'cancel', 'complete',
        ];
        const textLower = text.toLowerCase();
        return keywords.some(k => textLower.includes(k));
    }

    private getLineNumber(content: string, index: number): number {
        return content.substring(0, index).split('\n').length;
    }
}

// =========================================================================
// Supporting Types
// =========================================================================

interface DetectionContext {
    currentClass: string | null;
    currentMethod: string | null;
    methodStartLine?: number;
}

interface GuardConditionInfo {
    leftOperand: string;
    operator: ConditionOperator;
    rightOperand?: string;
    guardType: 'null_check' | 'bounds_check' | 'state_check' | 'type_check' | 'custom';
}

interface GuardMethodInfo extends GuardConditionInfo {
    errorMessage?: string;
    ruleText: string;
}

interface BusinessConditionInfo {
    isBusinessRule: boolean;
    confidence: number;
    keywords: string[];
    variable: string;
    operator: ConditionOperator;
    threshold?: string | number;
    businessMeaning?: string;
    ruleText: string;
}

interface TestAssertionInfo {
    expected?: string;
    actual: string;
    testedEntity?: string;
    inferredRule: string;
    ruleText: string;
}
