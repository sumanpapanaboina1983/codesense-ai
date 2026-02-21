// src/analyzer/parsers/validation-chain-extractor.ts

import {
    AstNode,
    RelationshipInfo,
    ValidationChainNode,
    EnrichedBusinessRuleNode,
    InstanceCounter,
} from '../types.js';
import { generateEntityId, generateInstanceId } from '../parser-utils.js';
import { createContextLogger } from '../../utils/logger.js';

const logger = createContextLogger('ValidationChainExtractor');

/**
 * Extracts validation chains from action methods through services to entities.
 * This provides the full validation flow for business rule documentation.
 */
export class ValidationChainExtractor {
    private instanceCounter: InstanceCounter = { count: 0 };
    private now: string = new Date().toISOString();

    // Common validation annotation patterns
    private readonly validationAnnotations = [
        { pattern: /@NotNull/g, type: 'required', severity: 'error' as const },
        { pattern: /@NotEmpty/g, type: 'required', severity: 'error' as const },
        { pattern: /@NotBlank/g, type: 'required', severity: 'error' as const },
        { pattern: /@Size\s*\([^)]+\)/g, type: 'length', severity: 'error' as const },
        { pattern: /@Min\s*\([^)]+\)/g, type: 'range', severity: 'error' as const },
        { pattern: /@Max\s*\([^)]+\)/g, type: 'range', severity: 'error' as const },
        { pattern: /@Pattern\s*\([^)]+\)/g, type: 'format', severity: 'error' as const },
        { pattern: /@Email/g, type: 'format', severity: 'error' as const },
        { pattern: /@Past/g, type: 'date', severity: 'error' as const },
        { pattern: /@Future/g, type: 'date', severity: 'error' as const },
        { pattern: /@Positive/g, type: 'range', severity: 'error' as const },
        { pattern: /@PositiveOrZero/g, type: 'range', severity: 'error' as const },
        { pattern: /@Negative/g, type: 'range', severity: 'error' as const },
        { pattern: /@Valid/g, type: 'nested', severity: 'error' as const },
    ];

    // Guard clause patterns
    private readonly guardPatterns = [
        { pattern: /if\s*\(\s*(\w+)\s*==\s*null\s*\)\s*(?:throw|return)/g, type: 'null_check' },
        { pattern: /if\s*\(\s*(\w+)\s*\.isEmpty\(\)\s*\)\s*(?:throw|return)/g, type: 'empty_check' },
        { pattern: /Objects\.requireNonNull\s*\(/g, type: 'null_check' },
        { pattern: /Assert\.\w+\s*\(/g, type: 'assertion' },
        { pattern: /Preconditions\.check\w+\s*\(/g, type: 'precondition' },
    ];

    /**
     * Extract validation chain from an action method.
     */
    extractValidationChain(
        actionClassName: string,
        actionMethodName: string,
        methodContent: string,
        relatedValidators: string[],
        relatedEntities: string[]
    ): ValidationChainNode {
        const validationSteps: ValidationChainNode['properties']['validationSteps'] = [];
        const validatedFields: string[] = [];
        let order = 1;

        // Step 1: Extract action-level validations (guard clauses)
        const actionGuards = this.extractGuardClauses(methodContent);
        if (actionGuards.length > 0) {
            validationSteps.push({
                order: order++,
                type: 'action',
                className: actionClassName,
                methodName: actionMethodName,
                rules: actionGuards.map(g => g.description),
            });
            validatedFields.push(...actionGuards.map(g => g.field).filter(f => f));
        }

        // Step 2: Add service-level validations (validator calls)
        for (const validator of relatedValidators) {
            validationSteps.push({
                order: order++,
                type: 'validator',
                className: validator,
                methodName: 'validate',
                rules: [`Validation via ${validator}`],
            });
        }

        // Step 3: Entity validations would be added here when entities are parsed
        for (const entity of relatedEntities) {
            validationSteps.push({
                order: order++,
                type: 'entity',
                className: entity,
                rules: [`Entity constraints on ${entity}`],
            });
        }

        const chainNode: ValidationChainNode = {
            id: generateInstanceId(this.instanceCounter, 'validationchain', `${actionClassName}.${actionMethodName}`),
            entityId: generateEntityId('validationchain', `${actionClassName}:${actionMethodName}`),
            kind: 'ValidationChain',
            name: `${actionClassName}.${actionMethodName}`,
            filePath: '',
            startLine: 0,
            endLine: 0,
            startColumn: 0,
            endColumn: 0,
            language: 'Java',
            createdAt: this.now,
            properties: {
                entryPoint: `${actionClassName}.${actionMethodName}`,
                validationSteps,
                totalRules: validationSteps.reduce((sum, step) => sum + step.rules.length, 0),
                validatedFields: [...new Set(validatedFields)],
            },
        };

        return chainNode;
    }

    /**
     * Extract guard clauses from method content.
     */
    private extractGuardClauses(methodContent: string): Array<{
        type: string;
        field: string;
        description: string;
    }> {
        const guards: Array<{ type: string; field: string; description: string }> = [];

        for (const { pattern, type } of this.guardPatterns) {
            let match;
            while ((match = pattern.exec(methodContent)) !== null) {
                const field = match[1] || '';
                guards.push({
                    type,
                    field,
                    description: `${type.replace('_', ' ')} for ${field || 'parameter'}`,
                });
            }
        }

        return guards;
    }

    /**
     * Enrich a business rule with feature context.
     */
    enrichBusinessRule(
        rule: AstNode,
        featureContext: {
            menuItem?: string;
            screen?: string;
            action?: string;
            subFeature?: string;
        }
    ): EnrichedBusinessRuleNode {
        const enrichedRule: EnrichedBusinessRuleNode = {
            id: generateInstanceId(this.instanceCounter, 'enrichedbusinessrule', rule.name),
            entityId: generateEntityId('enrichedbusinessrule', rule.entityId),
            kind: 'EnrichedBusinessRule',
            name: rule.name,
            filePath: rule.filePath,
            startLine: rule.startLine,
            endLine: rule.endLine,
            startColumn: rule.startColumn,
            endColumn: rule.endColumn,
            language: rule.language,
            createdAt: this.now,
            properties: {
                ruleType: this.inferRuleType(rule),
                ruleDescription: this.generateRuleDescription(rule),
                sourceMethod: rule.properties?.sourceMethod || '',
                sourceClass: rule.properties?.sourceClass || '',
                condition: rule.properties?.condition || '',
                errorMessage: rule.properties?.errorMessage,
                affectsFields: rule.properties?.affectsFields || [],
                triggeredBy: this.inferTriggers(rule, featureContext),
                dependencies: [],
                severity: rule.properties?.severity || 'error',
                featureContext,
                confidence: rule.properties?.confidence || 0.8,
            },
        };

        return enrichedRule;
    }

    /**
     * Extract validation annotations from entity field content.
     */
    extractFieldValidations(fieldContent: string, fieldName: string): Array<{
        annotationType: string;
        ruleType: string;
        severity: 'error' | 'warning' | 'info';
        parameters?: Record<string, string>;
    }> {
        const validations: Array<{
            annotationType: string;
            ruleType: string;
            severity: 'error' | 'warning' | 'info';
            parameters?: Record<string, string>;
        }> = [];

        for (const { pattern, type, severity } of this.validationAnnotations) {
            let match;
            while ((match = pattern.exec(fieldContent)) !== null) {
                const annotation = match[0];
                const parameters = this.parseAnnotationParameters(annotation);

                validations.push({
                    annotationType: annotation.split('(')[0].replace('@', ''),
                    ruleType: type,
                    severity,
                    parameters,
                });
            }
        }

        return validations;
    }

    /**
     * Parse parameters from an annotation string.
     */
    private parseAnnotationParameters(annotation: string): Record<string, string> | undefined {
        const params: Record<string, string> = {};
        const paramMatch = annotation.match(/\(([^)]+)\)/);

        if (!paramMatch) return undefined;

        const paramString = paramMatch[1];
        const pairs = paramString.split(',');

        for (const pair of pairs) {
            const [key, value] = pair.split('=').map(s => s.trim());
            if (key && value) {
                params[key] = value.replace(/["']/g, '');
            } else if (key && !value) {
                // Single value annotation like @Size(50)
                params['value'] = key;
            }
        }

        return Object.keys(params).length > 0 ? params : undefined;
    }

    /**
     * Infer rule type from rule node.
     */
    private inferRuleType(
        rule: AstNode
    ): 'validation' | 'constraint' | 'calculation' | 'workflow' | 'authorization' | 'guard' {
        const kind = rule.kind?.toLowerCase() || '';
        const name = rule.name?.toLowerCase() || '';

        if (kind.includes('guard') || name.includes('guard')) return 'guard';
        if (kind.includes('validation') || name.includes('valid')) return 'validation';
        if (kind.includes('constraint') || name.includes('constraint')) return 'constraint';
        if (kind.includes('auth') || name.includes('security')) return 'authorization';
        if (name.includes('calc') || name.includes('compute')) return 'calculation';

        return 'validation';
    }

    /**
     * Generate human-readable rule description.
     */
    private generateRuleDescription(rule: AstNode): string {
        const condition = rule.properties?.condition || '';
        const targetName = rule.properties?.targetName || rule.name;

        if (condition) {
            return `Rule: ${condition} on ${targetName}`;
        }

        return `Business rule for ${targetName}`;
    }

    /**
     * Infer what triggers this rule based on context.
     */
    private inferTriggers(
        rule: AstNode,
        featureContext: { action?: string }
    ): string[] {
        const triggers: string[] = [];
        const action = featureContext.action?.toLowerCase() || '';

        if (action.includes('save') || action.includes('create')) {
            triggers.push('save', 'create');
        }
        if (action.includes('update') || action.includes('edit')) {
            triggers.push('update');
        }
        if (action.includes('delete') || action.includes('remove')) {
            triggers.push('delete');
        }
        if (action.includes('validate') || action.includes('check')) {
            triggers.push('validate');
        }

        return triggers.length > 0 ? triggers : ['save', 'update'];
    }
}

export default ValidationChainExtractor;
